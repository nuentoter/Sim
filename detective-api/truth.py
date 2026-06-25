"""
Truth and Belief layer — investigative epistemology.

Three tiers of information:
  1. TruthEvent  — absolute verified facts; only the system creates these.
                   They never mutate or decay.
  2. Belief      — an NPC's probabilistic interpretation of a TruthEvent or
                   Rumor. Beliefs have confidence scores and can be updated
                   when new evidence arrives or old evidence weakens.
  3. Rumor       — social constructions (see rumor.py); may be false, distorted,
                   or exaggerated. Beliefs derived from rumors decay as the
                   underlying rumor decays.

Belief confidence formula when deriving from a Rumor:
    raw_conf = rumor.credibility * (1 - rumor.distortion_level / 200)
    receiver_bias = (receiver.suspicion - 50) / 500   # +/- 0.1 max
    confidence = clamp(raw_conf + raw_conf * receiver_bias, 0, 100)

Belief confidence when deriving from a TruthEvent:
    confidence = truth_event.confidence   (usually 100)
    (NPC's mood/stress can reduce their *access* to truths via dialogue,
    but beliefs formed from truths always carry the source confidence.)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import uuid


# ---------------------------------------------------------------------------
# TruthEvent — absolute, non-mutating facts
# ---------------------------------------------------------------------------

@dataclass
class TruthEvent:
    id: str
    description: str
    source_type: str        # "system" | "npc" | "player" | "environmental"
    confidence: int = 100   # always 100 for system-generated truths
    timestamp: str = ""     # game time string when established
    subject_ids: list = field(default_factory=list)   # NPC IDs or keywords

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "subject_ids": self.subject_ids,
        }


# ---------------------------------------------------------------------------
# Belief — NPC-level probabilistic interpretation
# ---------------------------------------------------------------------------

@dataclass
class Belief:
    statement: str          # what the NPC believes
    confidence: int         # 0–100 (their certainty in this statement)
    source_type: str        # "truth" | "rumor" | "direct_observation" | "inference"
    source_id: str          # TruthEvent.id, Rumor.id, or a free label
    subject_ids: list = field(default_factory=list)
    # If a newer observation updates this belief, we update in-place rather
    # than appending a duplicate.
    last_updated: str = ""

    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "confidence": self.confidence,
            "source_type": self.source_type,
            "subject_ids": self.subject_ids,
        }

    @property
    def tier(self) -> str:
        if self.confidence >= 75:
            return "strong"
        if self.confidence >= 40:
            return "moderate"
        return "weak"


# ---------------------------------------------------------------------------
# BeliefSystem — manages one NPC's belief collection
# ---------------------------------------------------------------------------

class BeliefSystem:
    """
    Attached to each NPC. Maintains a deduplicated, confidence-ordered list
    of that NPC's beliefs derived from truths, rumors, and observations.
    """

    def __init__(self):
        self.beliefs: list = []      # list[Belief]

    def _find(self, source_id: str) -> Optional[Belief]:
        for b in self.beliefs:
            if b.source_id == source_id:
                return b
        return None

    def update_from_truth(self, truth: TruthEvent, game_time: str):
        """Form or strengthen a belief from a verified TruthEvent."""
        existing = self._find(truth.id)
        if existing:
            # Truths only ever push confidence up
            existing.confidence = max(existing.confidence, truth.confidence)
            existing.last_updated = game_time
        else:
            self.beliefs.append(Belief(
                statement=truth.description,
                confidence=truth.confidence,
                source_type="truth",
                source_id=truth.id,
                subject_ids=list(truth.subject_ids),
                last_updated=game_time,
            ))
        self._trim()

    def update_from_rumor(self, rumor, receiver_suspicion: int, game_time: str):
        """
        Form or update a belief from a Rumor.
        Confidence is derived from the rumor's credibility and distortion level,
        modulated by the receiver's suspicion (suspicious NPCs amplify negative rumors).
        """
        raw = rumor.credibility * (1 - rumor.distortion_level / 200)
        bias = (receiver_suspicion - 50) / 500   # range: -0.1 … +0.1
        confidence = int(max(0, min(100, raw + raw * bias)))

        existing = self._find(rumor.id)
        if existing:
            # Blend: new observation may raise OR lower confidence
            existing.confidence = (existing.confidence + confidence) // 2
            existing.statement = rumor.content   # update to latest mutation
            existing.last_updated = game_time
        else:
            self.beliefs.append(Belief(
                statement=rumor.content,
                confidence=confidence,
                source_type="rumor",
                source_id=rumor.id,
                subject_ids=list(rumor.subjects),
                last_updated=game_time,
            ))
        self._trim()

    def update_from_observation(
        self, statement: str, subject_ids: list, confidence: int, game_time: str,
        obs_id: Optional[str] = None,
    ):
        """
        Record a belief from direct player-NPC dialogue (highest personal certainty).
        """
        sid = obs_id or f"obs_{uuid.uuid4().hex[:6]}"
        existing = self._find(sid)
        if existing:
            existing.confidence = max(existing.confidence, confidence)
            existing.last_updated = game_time
        else:
            self.beliefs.append(Belief(
                statement=statement,
                confidence=confidence,
                source_type="direct_observation",
                source_id=sid,
                subject_ids=subject_ids,
                last_updated=game_time,
            ))
        self._trim()

    def decay_rumor_beliefs(self, active_rumor_ids: set):
        """
        Reduce confidence of beliefs whose source rumor has gone stale.
        Called each tick by social_sim.
        """
        for belief in self.beliefs:
            if belief.source_type == "rumor" and belief.source_id not in active_rumor_ids:
                belief.confidence = max(0, belief.confidence - 4)
        self.beliefs = [b for b in self.beliefs if b.confidence > 0]

    def dominant(self, n: int = 3) -> list:
        """Return the n strongest beliefs."""
        return sorted(self.beliefs, key=lambda b: b.confidence, reverse=True)[:n]

    def summary(self) -> dict:
        dom = self.dominant(3)
        return {
            "belief_count": len(self.beliefs),
            "dominant_beliefs": [b.to_dict() for b in dom],
            "strong_count": sum(1 for b in self.beliefs if b.tier == "strong"),
            "moderate_count": sum(1 for b in self.beliefs if b.tier == "moderate"),
            "weak_count": sum(1 for b in self.beliefs if b.tier == "weak"),
        }

    def _trim(self):
        """Keep the belief list bounded; drop lowest-confidence entries."""
        if len(self.beliefs) > 30:
            self.beliefs.sort(key=lambda b: b.confidence, reverse=True)
            self.beliefs = self.beliefs[:30]


# ---------------------------------------------------------------------------
# Seed truths — absolute facts the system knows about the case
# ---------------------------------------------------------------------------

def build_seed_truths() -> list:
    """Returns list[TruthEvent] representing absolute facts of the case."""
    return [
        TruthEvent(
            id="truth_eleanor_dead",
            description="Eleanor Voss was found dead in the east wing of Hargrove Manor.",
            source_type="system",
            confidence=100,
            subject_ids=["eleanor", "hargrove"],
        ),
        TruthEvent(
            id="truth_time_of_death",
            description="The coroner places Eleanor's time of death between 11 pm and 1 am.",
            source_type="system",
            confidence=100,
            subject_ids=["eleanor"],
        ),
        TruthEvent(
            id="truth_ledger_exists",
            description=(
                "A ledger in the east wing safe records irregular withdrawals "
                "from the Hargrove estate funds."
            ),
            source_type="environmental",
            confidence=100,
            subject_ids=["hargrove", "ledger"],
        ),
        TruthEvent(
            id="truth_pocket_watch",
            description=(
                "A gold pocket watch engraved 'To R.H.' was found near Eleanor's body."
            ),
            source_type="environmental",
            confidence=100,
            subject_ids=["hargrove"],
        ),
        TruthEvent(
            id="truth_torn_note",
            description=(
                "A torn note reading 'Meet me at midnight — H' was found in the east wing."
            ),
            source_type="environmental",
            confidence=100,
            subject_ids=["hargrove", "eleanor"],
        ),
        TruthEvent(
            id="truth_hargrove_boat",
            description=(
                "Marina logs confirm Hargrove's registered vessel departed at 11:47 pm "
                "on the night of the murder."
            ),
            source_type="system",
            confidence=95,
            subject_ids=["hargrove", "marina"],
        ),
        TruthEvent(
            id="truth_tom_pub",
            description=(
                "Pub records and Maggie the barmaid's account confirm Tom Baker "
                "was at The Rusty Anchor all night."
            ),
            source_type="npc",
            confidence=85,
            subject_ids=["tom_baker"],
        ),
    ]
