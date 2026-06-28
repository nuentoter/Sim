"""
InvestigationBoard — active reasoning layer with salience-driven prioritisation.

Four tiers:
  EvidenceLink    — directed connection between evidence items (player or system).
  Contradiction   — auto-detected location-slot conflict between two sources.
  Hypothesis      — evidence cluster per subject, rebuilt each tick.
  Salience scores — 0–100 composite score per entity; drives sort order and
                    social_sim propagation weights.

Salience formulas
-----------------
Rumor:
    base          = credibility × 0.4                (0–40)
    spread        = min(npc_known_count, 5) × 5      (0–25)
    interest      = distortion_level × 0.10          (0–10)
    contradiction  = +10 if rumor is in a contradiction
    player_recency = max(0, 10 – commands_since_touched) × 1.5
    age_decay      = max(0, 15 – rumor.age) × 0.5    (0–7.5, fades to 0 after 30 ticks)
    focus          = +20 if rumor.subjects ∩ focus_subject
    → clamp 0–100

Truth:
    base          = confidence × 0.5                 (50 for system truths)
    contradiction = +8 if truth is in a contradiction
    focus         = +20 if truth.subject_ids ∩ focus_subject

NPC:
    interaction   = min(times_questioned, 6) × 8     (0–48)
    suspicion     = suspicion × 0.15                 (0–15)
    richness      = min(belief_count, 4) × 4         (0–16)
    recency       = max(0, 10 – age_in_commands) × 1.5
    focus         = +20 if NPC id matches focus_subject

Contradiction:
    base          = severity × 20                    (20/40/60)
    entity_bonus  = avg(salience_of_sources) × 0.3
    focus         = +15 if focus_subject in subject_ids
    → clamp 0–100

Contradiction detection
-----------------------
Keyword-based location fingerprinting: each text is mapped to a canonical
location slot (pub | manor | marina | cafe). Two sources sharing a subject_id
but landing on different slots → contradiction.

Tom Baker case:
  truth_tom_pub → "Rusty Anchor all night" → pub
  seed rumor    → "near the manor late that evening" → manor
  → same subject, different slots → severity 3.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(v)))


LOCATION_SLOTS: dict = {
    "pub":    ["pub", "rusty anchor", "anchor", "barmaid", "maggie"],
    "manor":  ["manor", "hargrove manor", "east wing", "estate"],
    "marina": ["marina", "dock", "harbour", "harbor", "skiff"],
    "cafe":   ["cafe", "harbour cafe"],
}


def _location_slot(text: str) -> Optional[str]:
    t = text.lower()
    for slot, keywords in LOCATION_SLOTS.items():
        if any(k in t for k in keywords):
            return slot
    return None


def _shared(list_a: list, list_b: list) -> list:
    return [x for x in list_a if x in list_b]


def _excerpt(text: str, n: int = 80) -> str:
    return text[:n] + ("…" if len(text) > n else "")


# ---------------------------------------------------------------------------
# Salience scoring — pure functions, deterministic
# ---------------------------------------------------------------------------

def score_rumor(
    rumor,
    contradiction_source_ids: set,
    focus_subject: Optional[str],
    interaction_log: dict,
    command_count: int,
) -> int:
    npc_known      = len([x for x in rumor.known_by if x != "player"])
    base           = rumor.credibility * 0.4
    spread         = min(npc_known, 5) * 5
    interest       = rumor.distortion_level * 0.10
    contra_boost   = 10 if rumor.id in contradiction_source_ids else 0
    last           = interaction_log.get(rumor.id, 0)
    player_recency = max(0, 10 - (command_count - last)) * 1.5
    age_decay      = max(0, 15 - rumor.age) * 0.5   # fades to 0 after 30 ticks
    focus_boost    = 20 if focus_subject and focus_subject in rumor.subjects else 0
    return _clamp(base + spread + interest + contra_boost + player_recency + age_decay + focus_boost)


def score_truth(
    truth,
    contradiction_source_ids: set,
    focus_subject: Optional[str],
) -> int:
    base         = truth.confidence * 0.5
    contra_boost = 8 if truth.id in contradiction_source_ids else 0
    focus_boost  = 20 if focus_subject and focus_subject in truth.subject_ids else 0
    return _clamp(base + contra_boost + focus_boost)


def score_npc(
    npc,
    npc_id: str,
    focus_subject: Optional[str],
    interaction_log: dict,
    command_count: int,
) -> int:
    interaction  = min(npc.times_questioned(), 6) * 8
    suspicion    = npc.suspicion * 0.15
    richness     = min(len(npc.belief_system.beliefs), 4) * 4
    last         = interaction_log.get(npc_id, 0)
    recency      = max(0, 10 - (command_count - last)) * 1.5
    # Focus match: NPC's id or any belief subject overlaps with focus_subject
    focus_boost  = 0
    if focus_subject:
        if focus_subject == npc_id or focus_subject in npc_id:
            focus_boost = 20
        elif any(focus_subject in b.subject_ids for b in npc.belief_system.beliefs):
            focus_boost = 10
    return _clamp(interaction + suspicion + richness + recency + focus_boost)


def score_contradiction(
    c,
    rumor_scores: dict,
    truth_scores: dict,
    focus_subject: Optional[str],
) -> int:
    base = c.severity * 20
    sa = (rumor_scores if c.source_a_type == "rumor" else truth_scores).get(c.source_a_id, 0)
    sb = (rumor_scores if c.source_b_type == "rumor" else truth_scores).get(c.source_b_id, 0)
    entity_bonus = int((sa + sb) / 2 * 0.3)
    focus_boost  = 15 if focus_subject and focus_subject in c.subject_ids else 0
    return _clamp(base + entity_bonus + focus_boost)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EvidenceLink:
    id: str
    source_type: str    # "truth" | "rumor"
    source_id: str
    target_type: str
    target_id: str
    reasoning: str
    created_by: str     # "player" | "system"
    game_time: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": f"{self.source_type}:{self.source_id}",
            "to": f"{self.target_type}:{self.target_id}",
            "reasoning": self.reasoning,
            "created_by": self.created_by,
        }


@dataclass
class Contradiction:
    id: str
    source_a_type: str
    source_a_id: str
    source_a_excerpt: str
    source_b_type: str
    source_b_id: str
    source_b_excerpt: str
    subject_ids: list
    description: str
    severity: int           # 1=minor, 2=notable, 3=direct conflict
    detected_at: str
    salience: int = 0       # computed by board.compute_salience()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "salience": self.salience,
            "description": self.description,
            "source_a": f"[{self.source_a_type.upper()}] {self.source_a_excerpt}",
            "source_b": f"[{self.source_b_type.upper()}] {self.source_b_excerpt}",
            "subjects": self.subject_ids,
        }


@dataclass
class Hypothesis:
    id: str
    statement: str
    subject_ids: list
    supporting_ids: list
    contradicting_ids: list
    confidence: int
    salience: int = 0   # set by compute_salience()

    @property
    def evidence_score(self) -> int:
        return len(self.supporting_ids) * 10 - len(self.contradicting_ids) * 15

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "statement": self.statement,
            "subjects": self.subject_ids,
            "confidence": self.confidence,
            "salience": self.salience,
            "supporting_count": len(self.supporting_ids),
            "contradicting_count": len(self.contradicting_ids),
        }


# ---------------------------------------------------------------------------
# InvestigationBoard
# ---------------------------------------------------------------------------

class InvestigationBoard:
    def __init__(self):
        self.links: list = []            # list[EvidenceLink]
        self.contradictions: list = []   # list[Contradiction]
        self.hypotheses: list = []       # list[Hypothesis]
        self._seen_pairs: set = set()    # frozensets already checked for conflict

        # Focus system
        self.focus_subject: Optional[str] = None
        self.focus_history: list = []    # [(subject, game_time)]

        # Interaction recency log: {entity_id: command_count_when_last_touched}
        self.interaction_log: dict = {}

    # ------------------------------------------------------------------
    # Focus
    # ------------------------------------------------------------------

    def set_focus(self, subject: str, game_time: str):
        self.focus_subject = subject
        self.focus_history.append((subject, game_time))

    def clear_focus(self, game_time: str):
        if self.focus_subject:
            self.focus_history.append((None, game_time))
        self.focus_subject = None

    def record_interaction(self, entity_id: str, command_count: int):
        """Mark that the player directly interacted with an entity this command."""
        self.interaction_log[entity_id] = command_count

    # ------------------------------------------------------------------
    # Salience computation
    # ------------------------------------------------------------------

    def compute_salience(
        self,
        truth_events: list,
        rumors: list,
        npcs: dict,
        command_count: int,
    ) -> dict:
        """
        Compute salience scores for every entity.
        Returns {entity_id: score (0–100)}.
        Scores are also written back into Contradiction.salience and
        Hypothesis.salience for sorting.
        Deterministic: same inputs → same outputs.
        """
        from rumor import NOISE_THRESHOLD

        # Build the set of entity IDs involved in any contradiction
        contra_ids: set = set()
        for c in self.contradictions:
            contra_ids.add(c.source_a_id)
            contra_ids.add(c.source_b_id)

        # Score truths
        truth_scores: dict = {
            t.id: score_truth(t, contra_ids, self.focus_subject)
            for t in truth_events
        }

        # Score active rumors
        active_rumors = [r for r in rumors if r.credibility > NOISE_THRESHOLD]
        rumor_scores: dict = {
            r.id: score_rumor(r, contra_ids, self.focus_subject, self.interaction_log, command_count)
            for r in active_rumors
        }

        # Score NPCs
        npc_scores: dict = {
            npc_id: score_npc(npc, npc_id, self.focus_subject, self.interaction_log, command_count)
            for npc_id, npc in npcs.items()
        }

        # Score contradictions and write back
        for c in self.contradictions:
            c.salience = score_contradiction(c, rumor_scores, truth_scores, self.focus_subject)

        # Score hypotheses and write back (proxy via subject NPC score or truth score)
        for h in self.hypotheses:
            subject = h.subject_ids[0] if h.subject_ids else ""
            # Hypothesis salience = max salience of its supporting evidence
            sup_scores = [
                truth_scores.get(sid, rumor_scores.get(sid, 0))
                for sid in h.supporting_ids
            ]
            h.salience = max(sup_scores) if sup_scores else 0

        all_scores = {**truth_scores, **rumor_scores, **npc_scores}
        return all_scores

    # ------------------------------------------------------------------
    # Tick sync
    # ------------------------------------------------------------------

    def sync(self, truth_events: list, rumors: list, game_time: str):
        """
        Scan for new contradictions and rebuild hypotheses.
        Idempotent: each (id_a, id_b) pair is checked only once.
        """
        from rumor import NOISE_THRESHOLD
        active_rumors = [r for r in rumors if r.credibility > NOISE_THRESHOLD]

        # Truth vs active rumors
        for truth in truth_events:
            for rumor in active_rumors:
                shared = _shared(truth.subject_ids, rumor.subjects)
                if not shared:
                    continue
                pair = frozenset([truth.id, rumor.id])
                if pair in self._seen_pairs:
                    continue
                self._seen_pairs.add(pair)
                c = self._conflict(
                    truth.description, "truth", truth.id,
                    rumor.content, "rumor", rumor.id,
                    shared, game_time, truth_vs_rumor=True,
                )
                if c:
                    self.contradictions.append(c)

        # Rumor vs rumor
        for i, r1 in enumerate(active_rumors):
            for r2 in active_rumors[i + 1:]:
                shared = _shared(r1.subjects, r2.subjects)
                if not shared:
                    continue
                pair = frozenset([r1.id, r2.id])
                if pair in self._seen_pairs:
                    continue
                self._seen_pairs.add(pair)
                c = self._conflict(
                    r1.content, "rumor", r1.id,
                    r2.content, "rumor", r2.id,
                    shared, game_time, truth_vs_rumor=False,
                )
                if c:
                    self.contradictions.append(c)

        self._rebuild_hypotheses(truth_events, active_rumors)

    def _conflict(
        self,
        text_a: str, type_a: str, id_a: str,
        text_b: str, type_b: str, id_b: str,
        shared_subjects: list, game_time: str, truth_vs_rumor: bool,
    ) -> Optional[Contradiction]:
        slot_a = _location_slot(text_a)
        slot_b = _location_slot(text_b)
        if not (slot_a and slot_b and slot_a != slot_b):
            return None
        subject_label = " & ".join(s.replace("_", " ") for s in shared_subjects)
        severity = 3 if truth_vs_rumor else 2
        return Contradiction(
            id=uuid.uuid4().hex[:8],
            source_a_type=type_a, source_a_id=id_a,
            source_a_excerpt=_excerpt(text_a, 75),
            source_b_type=type_b, source_b_id=id_b,
            source_b_excerpt=_excerpt(text_b, 75),
            subject_ids=list(shared_subjects),
            description=(
                f"Conflicting placement of {subject_label}: "
                f"one source puts them at the {slot_a}, another at the {slot_b}."
            ),
            severity=severity,
            detected_at=game_time,
        )

    # ------------------------------------------------------------------
    # Hypothesis reconstruction
    # ------------------------------------------------------------------

    def _rebuild_hypotheses(self, truth_events: list, active_rumors: list):
        by_subject: dict = {}
        for t in truth_events:
            for s in t.subject_ids:
                by_subject.setdefault(s, {"truths": [], "rumors": [], "conflicts": []})
                by_subject[s]["truths"].append(t)
        for r in active_rumors:
            for s in r.subjects:
                by_subject.setdefault(s, {"truths": [], "rumors": [], "conflicts": []})
                by_subject[s]["rumors"].append(r)
        for c in self.contradictions:
            for s in c.subject_ids:
                if s in by_subject:
                    by_subject[s]["conflicts"].append(c)

        self.hypotheses = []
        for subject, ev in by_subject.items():
            n_truths   = len(ev["truths"])
            n_rumors   = len(ev["rumors"])
            n_conflicts = len(ev["conflicts"])
            if n_truths + n_rumors < 2:
                continue

            raw_conf = n_truths * 20 + n_rumors * 8 - n_conflicts * 14
            confidence = max(5, min(95, raw_conf))
            label = subject.replace("_", " ").title()

            self.hypotheses.append(Hypothesis(
                id=f"hyp_{subject}",
                statement=f"Evidence cluster: {label}",
                subject_ids=[subject],
                supporting_ids=[t.id for t in ev["truths"]] + [r.id for r in ev["rumors"]],
                contradicting_ids=[c.id for c in ev["conflicts"]],
                confidence=confidence,
            ))

        # Default sort by evidence_score; salience will be applied after compute_salience()
        self.hypotheses.sort(key=lambda h: h.evidence_score, reverse=True)

    # ------------------------------------------------------------------
    # Player commands
    # ------------------------------------------------------------------

    def add_link(
        self,
        source_type: str, source_id: str,
        target_type: str, target_id: str,
        reasoning: str, game_time: str,
        created_by: str = "player",
    ) -> EvidenceLink:
        link = EvidenceLink(
            id=uuid.uuid4().hex[:8],
            source_type=source_type, source_id=source_id,
            target_type=target_type, target_id=target_id,
            reasoning=reasoning, created_by=created_by,
            game_time=game_time,
        )
        self.links.append(link)
        return link

    def analyze_subject(
        self, subject_key: str,
        truth_events: list, rumors: list, npcs: dict,
    ) -> dict:
        from rumor import NOISE_THRESHOLD
        rel_truths = [t for t in truth_events if subject_key in t.subject_ids]
        rel_rumors = [r for r in rumors if subject_key in r.subjects and r.credibility > NOISE_THRESHOLD]
        rel_contra = [c for c in self.contradictions if subject_key in c.subject_ids]

        related_ids = {t.id for t in rel_truths} | {r.id for r in rel_rumors}
        rel_links = [l for l in self.links if l.source_id in related_ids or l.target_id in related_ids]

        npc_beliefs: dict = {}
        for npc in npcs.values():
            relevant = [b for b in npc.belief_system.beliefs if subject_key in b.subject_ids]
            if relevant:
                npc_beliefs[npc.name] = sorted(
                    [b.to_dict() for b in relevant], key=lambda b: b["confidence"], reverse=True
                )[:2]

        return {
            "subject": subject_key,
            "confirmed_truths": [t.to_dict() for t in rel_truths],
            "active_rumors": [r.to_dict() for r in sorted(rel_rumors, key=lambda r: r.credibility, reverse=True)],
            "contradictions": [c.to_dict() for c in sorted(rel_contra, key=lambda c: c.salience, reverse=True)],
            "manual_links": [l.to_dict() for l in rel_links],
            "npc_beliefs": npc_beliefs,
        }

    def get_contradictions_for(self, subject_key: Optional[str] = None) -> list:
        if subject_key:
            return [c for c in self.contradictions if subject_key in c.subject_ids]
        return list(self.contradictions)

    # ------------------------------------------------------------------
    # NPC profile + reliability
    # ------------------------------------------------------------------

    def npc_reliability(self, npcs: dict, truth_events: list) -> list:
        truth_subjects: set = {s for t in truth_events for s in t.subject_ids}
        result = []
        for npc in npcs.values():
            beliefs = npc.belief_system.beliefs
            if not beliefs:
                result.append({"npc": npc.name, "reliability": 50, "note": "no beliefs yet",
                                "belief_count": 0, "aligned": 0})
                continue
            aligned = sum(1 for b in beliefs if any(s in truth_subjects for s in b.subject_ids))
            score = int((aligned / len(beliefs)) * 100)
            result.append({"npc": npc.name, "reliability": score, "belief_count": len(beliefs),
                           "aligned": aligned, "note": "high" if score >= 70 else "moderate" if score >= 40 else "low"})
        result.sort(key=lambda x: x["reliability"], reverse=True)
        return result

    def npc_profile(self, npc, truth_events: list, rumors: list) -> dict:
        from rumor import NOISE_THRESHOLD
        truth_subjects: set = {s for t in truth_events for s in t.subject_ids}
        beliefs = sorted(npc.belief_system.beliefs, key=lambda b: b.confidence, reverse=True)
        b_aligned   = [b for b in beliefs if any(s in truth_subjects for s in b.subject_ids)]
        b_unaligned = [b for b in beliefs if b not in b_aligned]
        rumor_exposure = [r for r in npc.heard_rumors if r.credibility > NOISE_THRESHOLD]
        reliability = int((len(b_aligned) / len(beliefs)) * 100) if beliefs else 50
        return {
            "name": npc.name,
            "role": npc.role,
            "axes": {"mood": npc.mood, "stress": npc.stress, "suspicion": npc.suspicion},
            "reliability_score": reliability,
            "belief_summary": npc.belief_system.summary(),
            "beliefs_aligned_with_truth": [b.to_dict() for b in b_aligned[:4]],
            "beliefs_not_in_truth": [b.to_dict() for b in b_unaligned[:4]],
            "active_rumor_exposure": [
                {"content": r.content[:70], "credibility": r.credibility,
                 "distortion_level": r.distortion_level}
                for r in rumor_exposure[-5:]
            ],
            "knowledge_revealed": sum(1 for k in npc.knowledge if k.revealed),
            "knowledge_total": len(npc.knowledge),
        }

    # ------------------------------------------------------------------
    # Overview — high-level summary for "overview" command
    # ------------------------------------------------------------------

    def overview(self, truth_events: list, rumors: list, npcs: dict, command_count: int) -> dict:
        """
        Returns a digest optimised for cognitive clarity:
          - top 3 hypotheses by salience
          - top 2 contradictions by salience
          - most unstable NPC (highest ratio of weak:total beliefs)
          - most reliable NPC (best truth alignment)
        """
        # Salience must be fresh — recompute if not done this tick
        self.compute_salience(truth_events, rumors, npcs, command_count)

        top_hyp = sorted(self.hypotheses, key=lambda h: h.salience, reverse=True)[:3]
        top_contra = sorted(self.contradictions, key=lambda c: c.salience, reverse=True)[:2]

        # Most unstable NPC: highest ratio of (weak + moderate) / total beliefs
        unstable = []
        for npc in npcs.values():
            beliefs = npc.belief_system.beliefs
            if not beliefs:
                continue
            weak_ratio = sum(1 for b in beliefs if b.confidence < 60) / len(beliefs)
            unstable.append((npc.name, weak_ratio, len(beliefs)))
        unstable.sort(key=lambda x: x[1], reverse=True)
        most_unstable = [{"npc": n, "instability": round(r, 2), "belief_count": c}
                         for n, r, c in unstable[:2]]

        reliable = self.npc_reliability(npcs, truth_events)

        return {
            "focus": self.focus_subject,
            "top_hypotheses": [h.to_dict() for h in top_hyp],
            "top_contradictions": [c.to_dict() for c in top_contra],
            "most_unstable_beliefs": most_unstable,
            "most_reliable_sources": reliable[:2],
        }

    # ------------------------------------------------------------------
    # /state surface
    # ------------------------------------------------------------------

    def board_summary(self, npcs: dict, truth_events: list, all_rumors: list, command_count: int) -> dict:
        """
        Compute fresh salience then return top-5 of each category.
        Only this top-5 slice is exposed in /state; full data remains accessible
        via the query commands (analyze, contradictions, overview, profile).
        """
        self.compute_salience(truth_events, all_rumors, npcs, command_count)

        top_hyp = sorted(self.hypotheses, key=lambda h: h.salience, reverse=True)[:5]
        top_contra = sorted(self.contradictions, key=lambda c: c.salience, reverse=True)[:5]

        return {
            "focus": self.focus_subject,
            "active_hypotheses": [h.to_dict() for h in top_hyp],
            "strongest_contradictions": [c.to_dict() for c in top_contra],
            "most_reliable_sources": self.npc_reliability(npcs, truth_events)[:3],
            "total_links": len(self.links),
            "total_contradictions": len(self.contradictions),
            "total_hypotheses": len(self.hypotheses),
        }
