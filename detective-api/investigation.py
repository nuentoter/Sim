"""
InvestigationBoard — active reasoning layer.

Three structures:
  EvidenceLink    — a directed connection between two evidence items.
                    Created by the player ("link X to Y") or automatically
                    by the system when it detects corroboration.
  Contradiction   — auto-detected conflict between two sources that share
                    a subject but make incompatible claims.
  Hypothesis      — a weighted interpretive statement derived from the
                    current evidence graph.  Rebuilt every tick via sync().

Contradiction detection strategy
---------------------------------
We use a keyword-based location fingerprint.  Each truth/rumor text is mapped
to a canonical location slot (pub | manor | marina | cafe | …).  If two
sources share a subject and name incompatible locations we register a conflict.

This covers the key tension in The Hargrove Affair:
  truth_tom_pub  → "Rusty Anchor all night"    → slot: pub
  seed rumor     → "near the manor that evening" → slot: manor
  → same subject tom_baker, different slots → severity-3 contradiction.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import uuid


# ---------------------------------------------------------------------------
# Location slot fingerprinting
# ---------------------------------------------------------------------------

LOCATION_SLOTS: dict = {
    "pub":    ["pub", "rusty anchor", "anchor", "barmaid", "maggie"],
    "manor":  ["manor", "hargrove manor", "east wing", "estate"],
    "marina": ["marina", "dock", "harbour", "harbor", "skiff"],
    "cafe":   ["cafe", "harbour cafe"],
}


def _location_slot(text: str) -> Optional[str]:
    """Return the canonical location slot for the first location keyword found."""
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
    severity: int       # 1=minor, 2=notable, 3=direct conflict
    detected_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
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
    supporting_ids: list    # truth/rumor IDs that support this hypothesis
    contradicting_ids: list # contradiction IDs that undermine it
    confidence: int         # 0–100

    @property
    def evidence_score(self) -> int:
        return len(self.supporting_ids) * 10 - len(self.contradicting_ids) * 15

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "statement": self.statement,
            "subjects": self.subject_ids,
            "confidence": self.confidence,
            "supporting_count": len(self.supporting_ids),
            "contradicting_count": len(self.contradicting_ids),
        }


# ---------------------------------------------------------------------------
# InvestigationBoard
# ---------------------------------------------------------------------------

class InvestigationBoard:
    def __init__(self):
        self.links: list = []           # list[EvidenceLink]
        self.contradictions: list = []  # list[Contradiction]
        self.hypotheses: list = []      # list[Hypothesis]
        self._seen_pairs: set = set()   # frozensets already checked for conflict

    # ------------------------------------------------------------------
    # Tick sync — call once per command from dispatch()
    # ------------------------------------------------------------------

    def sync(self, truth_events: list, rumors: list, game_time: str):
        """
        Scan for new contradictions between all truths and active rumors.
        Idempotent: each (id_a, id_b) pair is only checked once.
        Also rebuilds hypotheses from the current evidence graph.
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

        # Active rumor vs active rumor
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

        # Rebuild hypotheses each tick
        self._rebuild_hypotheses(truth_events, active_rumors)

    def _conflict(
        self,
        text_a: str, type_a: str, id_a: str,
        text_b: str, type_b: str, id_b: str,
        shared_subjects: list, game_time: str,
        truth_vs_rumor: bool,
    ) -> Optional[Contradiction]:
        """
        Return a Contradiction if the two texts make incompatible location claims,
        otherwise None.
        """
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
        """
        One hypothesis per subject that has at least two pieces of evidence.
        Confidence is driven by truth count vs contradiction weight.
        """
        # Index evidence by subject
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
            n_truths = len(ev["truths"])
            n_rumors = len(ev["rumors"])
            n_conflicts = len(ev["conflicts"])
            if n_truths + n_rumors < 2:
                continue

            raw_conf = n_truths * 20 + n_rumors * 8 - n_conflicts * 14
            confidence = max(5, min(95, raw_conf))

            supporting_ids = [t.id for t in ev["truths"]] + [r.id for r in ev["rumors"]]
            contradicting_ids = [c.id for c in ev["conflicts"]]
            label = subject.replace("_", " ").title()

            self.hypotheses.append(Hypothesis(
                id=f"hyp_{subject}",
                statement=f"Evidence cluster: {label}",
                subject_ids=[subject],
                supporting_ids=supporting_ids,
                contradicting_ids=contradicting_ids,
                confidence=confidence,
            ))

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
        """Return all evidence touching subject_key, partitioned by tier."""
        from rumor import NOISE_THRESHOLD
        rel_truths  = [t for t in truth_events if subject_key in t.subject_ids]
        rel_rumors  = [r for r in rumors if subject_key in r.subjects and r.credibility > NOISE_THRESHOLD]
        rel_contra  = [c for c in self.contradictions if subject_key in c.subject_ids]

        # Index evidence IDs that are related to this subject so we can surface links
        related_evidence_ids = (
            {t.id for t in rel_truths} |
            {r.id for r in rel_rumors}
        )
        rel_links = [
            l for l in self.links
            if l.source_id in related_evidence_ids or l.target_id in related_evidence_ids
        ]

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
            "contradictions": [c.to_dict() for c in sorted(rel_contra, key=lambda c: c.severity, reverse=True)],
            "manual_links": [l.to_dict() for l in rel_links],
            "npc_beliefs": npc_beliefs,
        }

    def get_contradictions_for(self, subject_key: Optional[str] = None) -> list:
        """Return contradictions, optionally filtered to those involving subject_key."""
        if subject_key:
            return [c for c in self.contradictions if subject_key in c.subject_ids]
        return list(self.contradictions)

    def npc_reliability(self, npcs: dict, truth_events: list) -> list:
        """
        Rank NPCs by belief-to-truth alignment.

        A belief is "aligned" if it shares at least one subject_id with any
        confirmed truth.  Reliability = aligned_beliefs / total_beliefs * 100.
        NPCs with zero beliefs get a neutral 50 score pending more data.
        """
        truth_subjects: set = {s for t in truth_events for s in t.subject_ids}
        result = []
        for npc in npcs.values():
            beliefs = npc.belief_system.beliefs
            if not beliefs:
                result.append({
                    "npc": npc.name, "reliability": 50,
                    "note": "no beliefs yet",
                    "belief_count": 0, "aligned": 0,
                })
                continue
            aligned = sum(1 for b in beliefs if any(s in truth_subjects for s in b.subject_ids))
            score = int((aligned / len(beliefs)) * 100)
            result.append({
                "npc": npc.name,
                "reliability": score,
                "belief_count": len(beliefs),
                "aligned": aligned,
                "note": "high" if score >= 70 else "moderate" if score >= 40 else "low",
            })
        result.sort(key=lambda x: x["reliability"], reverse=True)
        return result

    def npc_profile(self, npc, truth_events: list, rumors: list) -> dict:
        """
        Full epistemic breakdown of one NPC for the 'profile' command.
        """
        from rumor import NOISE_THRESHOLD
        truth_subjects: set = {s for t in truth_events for s in t.subject_ids}

        beliefs = sorted(npc.belief_system.beliefs, key=lambda b: b.confidence, reverse=True)
        b_aligned  = [b for b in beliefs if any(s in truth_subjects for s in b.subject_ids)]
        b_unaligned = [b for b in beliefs if b not in b_aligned]

        rumor_exposure = [r for r in npc.heard_rumors if r.credibility > NOISE_THRESHOLD]
        reliability = (
            int((len(b_aligned) / len(beliefs)) * 100) if beliefs else 50
        )

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
    # /state surface
    # ------------------------------------------------------------------

    def board_summary(self, npcs: dict, truth_events: list) -> dict:
        top_hypotheses = [h.to_dict() for h in self.hypotheses[:4]]
        by_severity = sorted(self.contradictions, key=lambda c: c.severity, reverse=True)
        return {
            "active_hypotheses": top_hypotheses,
            "strongest_contradictions": [c.to_dict() for c in by_severity[:3]],
            "most_reliable_sources": self.npc_reliability(npcs, truth_events)[:3],
            "total_links": len(self.links),
            "total_contradictions": len(self.contradictions),
        }
