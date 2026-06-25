"""
Game state management for the text-based detective game.
All state is held in-memory and shared across requests.
"""

from dataclasses import dataclass, field
from typing import Optional
import time as time_module

# ---------------------------------------------------------------------------
# Time system
# ---------------------------------------------------------------------------

TIME_PERIODS = ["morning", "afternoon", "evening", "night"]

@dataclass
class GameClock:
    period_index: int = 0   # index into TIME_PERIODS
    day: int = 1

    @property
    def period(self) -> str:
        return TIME_PERIODS[self.period_index % len(TIME_PERIODS)]

    def advance(self):
        self.period_index += 1
        if self.period_index % len(TIME_PERIODS) == 0:
            self.day += 1

    def description(self) -> str:
        return f"Day {self.day}, {self.period.capitalize()}"


# ---------------------------------------------------------------------------
# NPC — Tom Baker
# ---------------------------------------------------------------------------

@dataclass
class TomBaker:
    name: str = "Tom Baker"
    location: str = "The Rusty Anchor pub"
    mood: str = "nervous"
    trust: int = 0                     # 0–100; unlocks dialogue tiers
    has_alibi: bool = False
    alibi_revealed: bool = False
    clue_revealed: bool = False
    times_spoken_to: int = 0

    def greet(self) -> str:
        if self.times_spoken_to == 0:
            return (
                f"{self.name} looks up from his drink. "
                "\"I don't want any trouble. What do you want?\""
            )
        if self.trust >= 50:
            return f"{self.name} gives you a cautious nod. \"Back again, detective?\""
        return f"{self.name} eyes you warily. \"What now?\""

    def respond(self, topic: str) -> str:
        self.times_spoken_to += 1

        # Normalise: strip leading "about ", "the ", etc.
        import re
        topic = re.sub(r"^(about|the|a)\s+", "", topic.lower().strip())

        if any(k in topic for k in ("alibi", "where were you", "whereabouts")):
            if self.trust < 20:
                return (
                    "\"None of your business,\" he mutters, "
                    "staring into his glass."
                )
            if not self.alibi_revealed:
                self.alibi_revealed = True
                self.has_alibi = True
                return (
                    "He sighs. \"Fine. I was here all night — "
                    "Maggie the barmaid can vouch for me. "
                    "Now leave me alone.\""
                )
            return "\"I already told you — I was here. Ask Maggie.\""

        if any(k in topic for k in ("victim", "eleanor", "voss", "dead woman")):
            if self.trust < 10:
                return "\"I barely knew her,\" he snaps."
            if not self.clue_revealed:
                self.clue_revealed = True
                return (
                    "He lowers his voice. \"Eleanor had enemies. "
                    "She was skimming money from the Hargrove estate — "
                    "I saw the ledger myself. Check the east wing safe.\""
                )
            return "\"The ledger. East wing safe. I've said enough.\""

        if any(k in topic for k in ("hargrove", "estate")):
            return (
                "\"The Hargroves run this town. "
                "Poking around there is dangerous, detective.\""
            )

        if any(k in topic for k in ("maggie", "barmaid")):
            return (
                "\"Maggie works most nights. "
                "She'll confirm I didn't leave the pub.\""
            )

        if any(k in topic for k in ("hello", "hi", "hey", "talk")):
            return self.greet()

        return "He shrugs. \"Can't help you with that.\""

    def build_trust(self, amount: int = 10):
        self.trust = min(100, self.trust + amount)

    def status(self) -> dict:
        return {
            "name": self.name,
            "location": self.location,
            "mood": self.mood,
            "trust": self.trust,
            "alibi_revealed": self.alibi_revealed,
            "clue_revealed": self.clue_revealed,
        }


# ---------------------------------------------------------------------------
# Case system
# ---------------------------------------------------------------------------

@dataclass
class Case:
    title: str = "The Hargrove Affair"
    victim: str = "Eleanor Voss"
    status: str = "open"          # open | solved | cold
    clues_found: list = field(default_factory=list)
    suspects_cleared: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    # All clues in the game
    ALL_CLUES = {
        "torn_note":    "A torn note reading 'Meet me at midnight — H'.",
        "ledger":       "A leather ledger showing irregular withdrawals from the Hargrove estate.",
        "pocket_watch": "A gold pocket watch engraved 'To R.H. — with gratitude'.",
        "footprints":   "Muddy footprints leading from the east wing to the garden gate.",
        "witness_msg":  "Tom Baker's account placing himself at The Rusty Anchor all night.",
    }

    SOLVE_REQUIRED = {"ledger", "witness_msg", "pocket_watch"}

    def add_clue(self, clue_id: str) -> Optional[str]:
        if clue_id in self.ALL_CLUES and clue_id not in self.clues_found:
            self.clues_found.append(clue_id)
            return self.ALL_CLUES[clue_id]
        return None

    def try_solve(self) -> str:
        found = set(self.clues_found)
        missing = self.SOLVE_REQUIRED - found
        if missing:
            readable = ", ".join(k.replace("_", " ") for k in missing)
            return f"You don't have enough evidence yet. You still need: {readable}."
        self.status = "solved"
        return (
            "Case solved! The evidence points to Reginald Hargrove. "
            "The gold pocket watch, the tampered ledger, and the midnight note "
            "all tie back to him. You call the inspector. Justice will be served."
        )

    def summary(self) -> dict:
        return {
            "title": self.title,
            "victim": self.victim,
            "status": self.status,
            "clues_found": [self.ALL_CLUES[c] for c in self.clues_found],
            "clue_ids": self.clues_found,
            "suspects_cleared": self.suspects_cleared,
        }


# ---------------------------------------------------------------------------
# Master game state (singleton)
# ---------------------------------------------------------------------------

class GameState:
    def __init__(self):
        self.clock = GameClock()
        self.tom = TomBaker()
        self.case = Case()
        self.started_at = time_module.time()
        self.command_count = 0

    def reset(self):
        self.__init__()

    def to_dict(self) -> dict:
        return {
            "time": self.clock.description(),
            "case": self.case.summary(),
            "tom_baker": self.tom.status(),
            "commands_issued": self.command_count,
        }


# Global singleton — Flask is single-process in dev mode
STATE = GameState()
