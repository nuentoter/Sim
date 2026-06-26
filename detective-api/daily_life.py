"""
Daily Life Simulation Layer.

NPCs have goals, schedules, occupations, and relationships that drive autonomous
behaviour independent of player investigations.  Each social_sim tick calls
run_daily_tick(), which:

  1. Moves NPCs to their scheduled locations for the current time period.
  2. Generates social actions (socialize / cooperate / argue) between NPCs who
     share a location.
  3. Drives goal-urgency actions for NPCs with pressing personal goals.
  4. May generate organic rumors from notable actions.
  5. Logs every action into the NPC's bounded daily_log.

Keeps all existing epistemic systems (beliefs, contradictions, salience) unchanged.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import random
import uuid


# ---------------------------------------------------------------------------
# Canonical location map
# ---------------------------------------------------------------------------

LOCATION_DISPLAY: dict = {
    "pub":              "The Rusty Anchor",
    "marina":           "Island Marina",
    "cafe":             "Harbour Cafe",
    "home":             "home",
    "manor":            "Hargrove Manor",
    "harbour_office":   "Harbour Office",
    "council_chambers": "Council Chambers",
    "market":           "Market Square",
    "police_station":   "Police Station",
    "hotel":            "Harbour View Hotel",
}

# Reverse map — used to canonicalise display names coming from NPC.location
_DISPLAY_TO_KEY: dict = {v.lower(): k for k, v in LOCATION_DISPLAY.items()}
_DISPLAY_TO_KEY["the rusty anchor"] = "pub"
_DISPLAY_TO_KEY["the rusty anchor pub"] = "pub"
_DISPLAY_TO_KEY["rusty anchor"] = "pub"
_DISPLAY_TO_KEY["island marina"] = "marina"
_DISPLAY_TO_KEY["harbour cafe"] = "cafe"
_DISPLAY_TO_KEY["harbor cafe"] = "cafe"


def display_name(key: str) -> str:
    return LOCATION_DISPLAY.get(key, key.replace("_", " ").title())


def location_key(display: str) -> str:
    return _DISPLAY_TO_KEY.get(display.lower(), display.lower().replace(" ", "_"))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Schedule:
    """Preferred canonical location keys per time-of-day period."""
    morning:   list = field(default_factory=list)   # e.g. ["marina", "harbour_office"]
    afternoon: list = field(default_factory=list)
    evening:   list = field(default_factory=list)
    night:     list = field(default_factory=list)

    def preferred(self, period: str) -> list:
        return getattr(self, period.lower(), []) or ["home"]

    def to_dict(self) -> dict:
        return {
            "morning":   self.morning,
            "afternoon": self.afternoon,
            "evening":   self.evening,
            "night":     self.night,
        }


@dataclass
class Occupation:
    title:        str
    employer:     str
    income_level: str   # "low" | "medium" | "high"
    social_status: str  # "low" | "medium" | "high"

    def to_dict(self) -> dict:
        return {
            "title":        self.title,
            "employer":     self.employer,
            "income_level": self.income_level,
            "social_status": self.social_status,
        }


@dataclass
class Relationship:
    target_npc_id: str
    target_name:   str
    kind:          str    # "friendship" | "rivalry" | "family" | "business" | "romantic"
    strength:      int    # 0–100
    note:          str = ""

    def to_dict(self) -> dict:
        return {
            "with": self.target_name,
            "kind": self.kind,
            "strength": self.strength,
            "note": self.note,
        }


@dataclass
class PersonalGoal:
    id:       str
    label:    str
    category: str   # "financial" | "social" | "personal" | "criminal"
    urgency:  int   # 0–100; rises each tick
    active:   bool = True
    progress: int = 0   # 0–100

    def urgency_label(self) -> str:
        if self.urgency >= 80:
            return "CRITICAL"
        if self.urgency >= 60:
            return "URGENT"
        if self.urgency >= 40:
            return "HIGH"
        return "LOW"

    def to_dict(self) -> dict:
        return {
            "id":       self.id,
            "label":    self.label,
            "category": self.category,
            "urgency":  self.urgency,
            "urgency_label": self.urgency_label(),
            "active":   self.active,
            "progress": self.progress,
        }


@dataclass
class DailyLifeAction:
    action_type:  str   # "travel" | "work" | "socialize" | "argue" | "cooperate" | "idle"
    actor_id:     str
    actor_name:   str
    target_id:    Optional[str] = None
    target_name:  Optional[str] = None
    location:     str = ""
    description:  str = ""
    game_time:    str = ""
    goal_driven:  bool = False

    def to_dict(self) -> dict:
        d: dict = {
            "type":     self.action_type,
            "location": self.location,
            "description": self.description,
            "time":     self.game_time,
        }
        if self.target_name:
            d["with"] = self.target_name
        if self.goal_driven:
            d["goal_driven"] = True
        return d


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _log_action(npc, action: DailyLifeAction):
    """Append to the NPC's daily_log, keeping only the last 20 entries."""
    npc.daily_log.append(action)
    if len(npc.daily_log) > 20:
        npc.daily_log = npc.daily_log[-20:]
    npc.remember(
        "daily_action",
        action.description,
        action.game_time,
        weight=1,
    )


def _get_relationship(npc, target_id: str) -> Optional[Relationship]:
    """Return the Relationship from npc to target_id, or None."""
    for r in npc.relationships:
        if r.target_npc_id == target_id:
            return r
    return None


def _social_action_type(rel: Optional[Relationship]) -> Optional[str]:
    """Pick an action type based on relationship, with probability gates."""
    if rel is None:
        return "socialize" if random.random() < 0.25 else None
    if rel.kind == "rivalry":
        return "argue" if random.random() < 0.35 else "socialize"
    if rel.kind == "friendship":
        return "socialize" if random.random() < 0.55 else None
    if rel.kind in ("business", "family"):
        return "cooperate" if random.random() < 0.45 else "socialize"
    return "socialize" if random.random() < 0.30 else None


_SOCIALIZE_TEMPLATES = [
    "{a} and {b} were seen chatting at {loc}.",
    "{a} caught up with {b} over at {loc}.",
    "{a} and {b} shared a conversation at {loc}.",
]
_ARGUE_TEMPLATES = [
    "{a} and {b} exchanged heated words at {loc}.",
    "{a} appeared to argue with {b} near {loc}.",
    "{a} had a visible disagreement with {b} at {loc}.",
]
_COOPERATE_TEMPLATES = [
    "{a} and {b} were working together at {loc}.",
    "{a} met with {b} at {loc} — appeared to be conducting business.",
    "{a} and {b} discussed matters at {loc}.",
]


def _describe_social(a_name, b_name, loc, action_type) -> str:
    if action_type == "argue":
        t = random.choice(_ARGUE_TEMPLATES)
    elif action_type == "cooperate":
        t = random.choice(_COOPERATE_TEMPLATES)
    else:
        t = random.choice(_SOCIALIZE_TEMPLATES)
    return t.format(a=a_name, b=b_name, loc=loc)


def _apply_social_effects(npc_a, npc_b, rel: Optional[Relationship], action_type: str):
    """Adjust NPC axes based on the social action."""
    if action_type == "argue":
        npc_a.shift_stress(6)
        npc_b.shift_stress(6)
        npc_a.shift_mood(-8)
        npc_b.shift_mood(-8)
        npc_a.shift_suspicion(4)
        npc_b.shift_suspicion(4)
    elif action_type == "socialize":
        npc_a.shift_mood(5)
        npc_b.shift_mood(5)
        npc_a.shift_stress(-3)
        npc_b.shift_stress(-3)
    elif action_type == "cooperate":
        npc_a.shift_stress(-2)
        npc_b.shift_stress(-2)


# Probability that a notable social action generates a rumor
_RUMOR_PROB = {
    "argue":     0.60,
    "cooperate": 0.30,   # only for unexpected pairs
    "socialize": 0.10,
}


def _maybe_life_rumor(
    npc_a, npc_b, rel: Optional[Relationship], action_type: str, location: str,
) -> Optional[str]:
    """
    Return organic rumor content if the action is notable enough to gossip about.
    Returns None if no rumor fires.
    """
    prob = _RUMOR_PROB.get(action_type, 0.0)

    # Unexpected pairing boosts probability
    if rel and rel.kind == "rivalry" and action_type == "cooperate":
        prob = 0.70   # rivals cooperating is very gossip-worthy

    if random.random() > prob:
        return None

    a, b, loc = npc_a.name, npc_b.name, location
    if action_type == "argue":
        templates = [
            f"{a} and {b} were seen in a heated argument at {loc}.",
            f"Word is that {a} and {b} had sharp words with each other at {loc}.",
            f"There was a visible row between {a} and {b} at {loc}.",
        ]
    elif action_type == "cooperate" and rel and rel.kind == "rivalry":
        templates = [
            f"{a} and {b} were unexpectedly seen together at {loc} — appearing to cooperate.",
            f"Despite their differences, {a} and {b} were spotted meeting at {loc}.",
        ]
    else:
        templates = [
            f"{a} and {b} were seen in close conversation at {loc}.",
            f"Someone noticed {a} talking quietly with {b} at {loc}.",
        ]
    return random.choice(templates)


def _make_life_rumor(content: str, source_npc, subject_npc):
    """Create a Rumor from observed daily-life behavior."""
    from rumor import Rumor
    return Rumor(
        id=uuid.uuid4().hex[:8],
        content=content,
        original_content=content,
        source_npc_id=source_npc.id,
        subjects=[subject_npc.id, source_npc.id],
        credibility=52,
        distortion_level=8,
        known_by=[source_npc.id],
    )


# ---------------------------------------------------------------------------
# Goal-driven behaviour
# ---------------------------------------------------------------------------

_GOAL_ACTION_MAP: dict = {
    "hide_mistake":       ("idle",      "looking distracted and avoiding eye contact"),
    "protect_reputation": ("socialize", "making a point of being seen and sociable"),
    "earn_money":         ("work",      "working extra hours"),
    "seek_promotion":     ("cooperate", "ingratiating themselves with anyone useful"),
    "help_friend":        ("socialize", "checking in on a friend"),
    "seek_revenge":       ("argue",     "picking fights and stirring conflict"),
}


def _goal_action(npc, goal: PersonalGoal, logs: list, game_time: str):
    action_type, flavor = _GOAL_ACTION_MAP.get(goal.id, ("idle", "thinking"))
    desc = f"{npc.name} was seen {flavor} — driven by their need to {goal.label.lower()}."
    action = DailyLifeAction(
        action_type=action_type, actor_id=npc.id, actor_name=npc.name,
        location=npc.location, description=desc, game_time=game_time, goal_driven=True,
    )
    _log_action(npc, action)

    # High-urgency hide_mistake: stress spike + maybe suspicious rumor
    if goal.id == "hide_mistake" and goal.urgency >= 75:
        npc.shift_stress(5)
        npc.shift_suspicion(3)

    logs.append(f"[DAILY-GOAL] {desc}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_daily_tick(npcs: dict, all_rumors: list, game_time: str, period: str) -> tuple:
    """
    Run the daily life simulation for one tick.

    Args:
        npcs       — {npc_id: NPC} registry
        all_rumors — current rumor pool (read-only in this function)
        game_time  — e.g. "Day 2, Evening"
        period     — "morning" | "afternoon" | "evening" | "night"

    Returns:
        (new_rumors: list[Rumor], logs: list[str])
    """
    new_rumors: list = []
    logs: list = []

    period_norm = period.lower()

    # ------------------------------------------------------------------
    # Phase 1 — Move NPCs to their scheduled locations
    # ------------------------------------------------------------------
    for npc in npcs.values():
        if not getattr(npc, "schedule", None):
            continue
        preferred = npc.schedule.preferred(period_norm)
        if not preferred:
            continue
        target_key = random.choice(preferred)
        target_display = display_name(target_key)
        if npc.location == target_display:
            continue

        old_loc = npc.location
        npc.location = target_display
        action = DailyLifeAction(
            action_type="travel",
            actor_id=npc.id, actor_name=npc.name,
            location=target_display,
            description=f"{npc.name} made their way from {old_loc} to {target_display}.",
            game_time=game_time,
        )
        _log_action(npc, action)
        logs.append(f"[DAILY] {action.description}")

    # ------------------------------------------------------------------
    # Phase 2 — Social actions between co-located NPCs
    # ------------------------------------------------------------------
    npc_list = list(npcs.values())
    already_acted: set = set()   # (id_a, id_b) pairs processed this tick

    for i, npc_a in enumerate(npc_list):
        for npc_b in npc_list[i + 1:]:
            if npc_a.location != npc_b.location:
                continue
            pair = frozenset([npc_a.id, npc_b.id])
            if pair in already_acted:
                continue
            already_acted.add(pair)

            rel_a = _get_relationship(npc_a, npc_b.id)
            action_type = _social_action_type(rel_a)
            if not action_type:
                continue

            desc = _describe_social(npc_a.name, npc_b.name, npc_a.location, action_type)

            for actor, target in ((npc_a, npc_b), (npc_b, npc_a)):
                action = DailyLifeAction(
                    action_type=action_type,
                    actor_id=actor.id, actor_name=actor.name,
                    target_id=target.id, target_name=target.name,
                    location=actor.location, description=desc, game_time=game_time,
                )
                _log_action(actor, action)

            _apply_social_effects(npc_a, npc_b, rel_a, action_type)
            logs.append(f"[DAILY] {desc}")

            rumor_content = _maybe_life_rumor(npc_a, npc_b, rel_a, action_type, npc_a.location)
            if rumor_content:
                # The "witness" is the less-involved party — pick the other NPC at random
                source = random.choice(npc_list)
                if source.id not in (npc_a.id, npc_b.id):
                    rumor = _make_life_rumor(rumor_content, source, npc_a)
                    new_rumors.append(rumor)
                    logs.append(f"[DAILY-RUMOR] {rumor_content[:80]}")

    # ------------------------------------------------------------------
    # Phase 3 — Goal-driven actions
    # ------------------------------------------------------------------
    for npc in npcs.values():
        goals = getattr(npc, "goals", [])
        if not goals:
            # Default work action if occupied
            if getattr(npc, "occupation", None):
                action = DailyLifeAction(
                    action_type="work", actor_id=npc.id, actor_name=npc.name,
                    location=npc.location,
                    description=f"{npc.name} went about their work.",
                    game_time=game_time,
                )
                _log_action(npc, action)
            continue

        urgent = [g for g in goals if g.active and g.urgency >= 60]
        if urgent:
            goal = max(urgent, key=lambda g: g.urgency)
            _goal_action(npc, goal, logs, game_time)
        elif getattr(npc, "occupation", None):
            action = DailyLifeAction(
                action_type="work", actor_id=npc.id, actor_name=npc.name,
                location=npc.location,
                description=f"{npc.name} went about their duties as {npc.occupation.title}.",
                game_time=game_time,
            )
            _log_action(npc, action)

        # Tick goal urgency — pressure builds each game command
        for goal in goals:
            if goal.active:
                goal.urgency = min(100, goal.urgency + 2)

    return new_rumors, logs
