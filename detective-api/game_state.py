"""
Master game state — clock, NPC registry, and case.
No NPC-specific logic lives here; see npc.py and case.py.
"""

from __future__ import annotations
from dataclasses import dataclass
import time as time_module

from npc import NPC, build_npc_registry
from case import Case


# ---------------------------------------------------------------------------
# Time system
# ---------------------------------------------------------------------------

TIME_PERIODS = ["morning", "afternoon", "evening", "night"]


@dataclass
class GameClock:
    period_index: int = 0
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
# GameState
# ---------------------------------------------------------------------------

class GameState:
    def __init__(self):
        self.clock = GameClock()
        self.npcs: dict = build_npc_registry()   # {npc_id: NPC}
        self.case = Case()
        self.started_at = time_module.time()
        self.command_count = 0

    def reset(self):
        self.__init__()

    def to_dict(self) -> dict:
        return {
            "time": self.clock.description(),
            "case": self.case.summary(),
            "npcs": {npc_id: npc.status() for npc_id, npc in self.npcs.items()},
            "commands_issued": self.command_count,
        }


# Global singleton
STATE = GameState()
