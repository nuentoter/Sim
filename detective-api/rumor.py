"""
Rumor system — social information propagation.

A Rumor travels between NPCs, mutating slightly on each hop.
It carries subject metadata so the simulation can apply targeted
effects (suspicion shifts, mood shifts, topic gating) on receivers.

Mutation pipeline (called when NPC A shares with NPC B):
  1. Content is passed through a verb-escalation pass (distortion-weighted)
  2. Framing is added based on receiver's stress/suspicion
  3. Credibility decays; distortion level rises
  4. A new Rumor object is returned (originals are never mutated in-place)
"""

from __future__ import annotations
import random
import uuid
from dataclasses import dataclass, field
from typing import Optional

# Rumors at or below this credibility are "noise" — they stop propagating
# and are excluded from the active rumor surface shown to the player.
NOISE_THRESHOLD: int = 20

# Credibility is reinforced by this amount when the same rumor is shared
# between two NPCs in the same tick (corroboration effect).
REINFORCE_AMOUNT: int = 3

# Base credibility decay per tick (applied to all rumors every tick).
BASE_DECAY: int = 2


# ---------------------------------------------------------------------------
# Mutation vocabulary
# ---------------------------------------------------------------------------

# Pairs: (pattern_substring, [mild→escalated replacements])
# Applied probabilistically based on distortion_level.
VERB_ESCALATIONS: list = [
    ("was at",         ["was seen near",         "was lurking near",      "was sneaking around"]),
    ("saw",            ["witnessed",              "discovered",            "caught sight of"]),
    ("talked to",      ["was arguing with",       "confronted",            "had words with"]),
    ("went to",        ["slipped away to",        "crept toward",          "rushed off to"]),
    ("left",           ["fled",                   "disappeared from",      "slipped out of"]),
    ("was near",       ["was hovering around",    "was prowling near",     "was circling"]),
    ("spoke with",     ["was whispering with",    "was in a tense meeting with", "was seen with"]),
    ("knew",           ["was involved with",      "had dealings with",     "was connected to"]),
    ("found",          ["uncovered",              "stumbled upon",         "secretly obtained"]),
]

# Hedging prefixes added to low-credibility rumors
HEDGES = [
    "Word is that", "Apparently", "I heard that", "People are saying",
    "Someone told me", "There's talk that", "Rumour has it that",
    "I can't be sure, but", "Between you and me,",
]

# Intensifiers added when distortion is high
INTENSIFIERS = [
    "very late at night", "in secret", "without anyone knowing",
    "right before the murder", "suspiciously", "acting strangely",
    "in a rush", "looking terrified",
]


def _escalate_verbs(content: str, distortion: int) -> str:
    """Replace verbs based on distortion probability."""
    result = content
    for trigger, replacements in VERB_ESCALATIONS:
        if trigger in result.lower():
            # Probability of escalation rises with distortion
            if random.random() < distortion / 120:
                replacement = random.choice(replacements)
                # Case-aware replacement
                idx = result.lower().find(trigger)
                result = result[:idx] + replacement + result[idx + len(trigger):]
                break   # one escalation per mutation pass
    return result


def _add_hedge(content: str, credibility: int) -> str:
    """Wrap in hedging language when credibility is low."""
    if credibility < 55 and not any(h.lower() in content.lower() for h in HEDGES[:3]):
        hedge = random.choice(HEDGES)
        # Lowercase the first character of content after the hedge
        body = content[0].lower() + content[1:] if content else content
        return f"{hedge} {body}"
    return content


def _inject_intensifier(content: str, distortion: int) -> str:
    """Append a colour phrase when distortion is high enough."""
    if distortion > 55 and random.random() < 0.45:
        intensifier = random.choice(INTENSIFIERS)
        # Avoid duplicate injections
        if intensifier not in content:
            # Try to insert before the last period or at end
            if content.endswith("."):
                return content[:-1] + f", {intensifier}."
            return content + f" — {intensifier}"
    return content


# ---------------------------------------------------------------------------
# RumorEffect — what happens when an NPC hears this rumor
# ---------------------------------------------------------------------------

@dataclass
class RumorEffect:
    """
    Effects applied to NPCs when they hear a rumor.
    subject_id may be an NPC id OR a keyword like "hargrove"/"eleanor".
    """
    subject_id: str             # who the rumor is about
    suspicion_delta: int = 0    # shift applied to the HEARER's suspicion of subject
    mood_delta: int = 0         # shift to hearer's own mood
    stress_delta: int = 0       # shift to hearer's own stress
    unlock_topics: list = field(default_factory=list)   # topic_keys now more shareable
    block_topics: list = field(default_factory=list)    # topic_keys now less shareable


# ---------------------------------------------------------------------------
# Rumor
# ---------------------------------------------------------------------------

@dataclass
class Rumor:
    id: str
    content: str                     # current (possibly mutated) text
    original_content: str            # unchanged original for reference
    source_npc_id: str               # NPC who originated this rumor
    subjects: list = field(default_factory=list)   # NPC IDs or keyword strings referenced
    credibility: int = 70            # 0–100
    distortion_level: int = 0        # 0–100; rises with each hop
    age: int = 0                     # ticks elapsed since creation
    known_by: list = field(default_factory=list)   # NPC IDs that have received this rumor
    effects: list = field(default_factory=list)    # list[RumorEffect]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "original_content": self.original_content,
            "source_npc_id": self.source_npc_id,
            "subjects": self.subjects,
            "credibility": self.credibility,
            "distortion_level": self.distortion_level,
            "age": self.age,
            "known_by": self.known_by,
            "is_distorted": self.distortion_level > 30,
        }

    def is_about(self, target: str) -> bool:
        t = target.lower()
        return any(t in s.lower() or s.lower() in t for s in self.subjects)


# ---------------------------------------------------------------------------
# Mutation engine
# ---------------------------------------------------------------------------

def mutate(rumor: Rumor, receiver_stress: int, receiver_suspicion: int) -> Rumor:
    """
    Return a new Rumor with mutated content, increased distortion, and
    decayed credibility. The original rumor is not modified.
    """
    # Mutation intensity is driven by receiver state
    mutation_pressure = (receiver_stress + receiver_suspicion) / 2  # 0–100
    new_distortion = min(100, rumor.distortion_level + random.randint(5, 18))
    new_credibility = max(0, rumor.credibility - random.randint(3, 12))

    content = rumor.content

    # Apply mutation steps (probabilistically, skipped if low pressure)
    if random.random() < mutation_pressure / 100:
        content = _escalate_verbs(content, new_distortion)
    if random.random() < 0.55:
        content = _add_hedge(content, new_credibility)
    if new_distortion > 40:
        content = _inject_intensifier(content, new_distortion)

    return Rumor(
        id=rumor.id,                   # same rumor, different generation
        content=content,
        original_content=rumor.original_content,
        source_npc_id=rumor.source_npc_id,
        subjects=list(rumor.subjects),
        credibility=new_credibility,
        distortion_level=new_distortion,
        age=rumor.age,
        known_by=list(rumor.known_by),
        effects=list(rumor.effects),
    )


# ---------------------------------------------------------------------------
# Rumor factory — starting rumors seeded into the world
# ---------------------------------------------------------------------------

def build_seed_rumors() -> list:
    """Returns a list of Rumor objects that exist at game start."""

    r1 = Rumor(
        id=str(uuid.uuid4())[:8],
        content="Tom Baker was seen near the manor late that evening.",
        original_content="Tom Baker was seen near the manor late that evening.",
        source_npc_id="marina_manager",
        subjects=["tom_baker", "manor"],
        credibility=60,
        distortion_level=10,
        effects=[
            RumorEffect(
                subject_id="tom_baker",
                suspicion_delta=8,
                mood_delta=-3,
            )
        ],
    )
    r1.known_by = ["marina_manager"]

    r2 = Rumor(
        id=str(uuid.uuid4())[:8],
        content="Eleanor had been receiving letters from someone at the Hargrove estate.",
        original_content="Eleanor had been receiving letters from someone at the Hargrove estate.",
        source_npc_id="cafe_owner",
        subjects=["eleanor", "hargrove"],
        credibility=75,
        distortion_level=5,
        effects=[
            RumorEffect(
                subject_id="hargrove",
                suspicion_delta=5,
                mood_delta=-2,
            )
        ],
    )
    r2.known_by = ["cafe_owner"]

    r3 = Rumor(
        id=str(uuid.uuid4())[:8],
        content="Reginald Hargrove's private boat left the marina the night Eleanor died.",
        original_content="Reginald Hargrove's private boat left the marina the night Eleanor died.",
        source_npc_id="marina_manager",
        subjects=["hargrove", "marina"],
        credibility=85,
        distortion_level=0,
        effects=[
            RumorEffect(
                subject_id="hargrove",
                suspicion_delta=12,
                mood_delta=-5,
                stress_delta=5,
            )
        ],
    )
    r3.known_by = ["marina_manager"]

    return [r1, r2, r3]
