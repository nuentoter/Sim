"""
Master game state — clock, NPC registry, case, rumor pool, and truth layer.

Epistemic tiers in to_dict():
  confirmed_truths  — TruthEvents (absolute, system-generated)
  active_rumors     — Rumors with credibility > NOISE_THRESHOLD
  noise             — count of rumors below threshold (noise, not shown in detail)
  npc_beliefs       — per-NPC BeliefSystem summary (dominant beliefs only)
"""

from __future__ import annotations
from dataclasses import dataclass
import time as time_module

from npc import build_npc_registry
from case import Case
from rumor import build_seed_rumors, NOISE_THRESHOLD
from truth import build_seed_truths
from investigation import InvestigationBoard


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
        self.npcs: dict = build_npc_registry()        # {npc_id: NPC}
        self.case = Case()
        self.rumors: list = build_seed_rumors()       # global mutable rumor pool
        self.truth_events: list = build_seed_truths() # immutable canonical facts
        self.board: InvestigationBoard = InvestigationBoard()
        self.started_at = time_module.time()
        self.command_count = 0
        self.social_log: list = []                    # ring-buffered background event log
        self.scenario_id: str = "hargrove_affair"

    def reset(self):
        self.__init__()

    @classmethod
    def from_scenario(cls, scenario) -> "GameState":
        """Create a fresh GameState pre-populated with a scenario's data."""
        state = cls.__new__(cls)
        state._apply_scenario(scenario)
        return state

    def load_from_scenario(self, scenario):
        """
        Reset this GameState in-place for a new scenario.

        Mutates self so that all existing references (including app.py's
        module-level STATE binding) see the new scenario data immediately.
        """
        self._apply_scenario(scenario)

    def _apply_scenario(self, scenario):
        """Shared setup used by both from_scenario and load_from_scenario."""
        self.clock = GameClock()
        self.case = Case(title=scenario.case_title, victim=scenario.case_victim)
        self.npcs = scenario.build_npcs()
        self.truth_events = scenario.build_truths()
        self.rumors = scenario.build_rumors()
        self.board = InvestigationBoard()
        self.started_at = time_module.time()
        self.command_count = 0
        self.social_log = []
        self.scenario_id = scenario.id

    # --- Epistemic helpers ---

    def active_rumors(self) -> list:
        """Rumors above the noise threshold — still propagating."""
        return [r for r in self.rumors if r.credibility > NOISE_THRESHOLD]

    def noise_rumors(self) -> list:
        """Rumors that have decayed below the noise threshold."""
        return [r for r in self.rumors if r.credibility <= NOISE_THRESHOLD]

    def to_dict(self) -> dict:
        active = self.active_rumors()
        noise_count = len(self.noise_rumors())

        return {
            "time": self.clock.description(),
            "case": self.case.summary(),

            # Tier 1 — verified facts
            "confirmed_truths": [t.to_dict() for t in self.truth_events],

            # Tier 2 — active rumors (above noise floor)
            "active_rumors": [r.to_dict() for r in active],
            "noise_rumor_count": noise_count,

            # Tier 3 — NPC derived beliefs (summaries only)
            "npc_beliefs": {
                npc_id: npc.belief_system.summary()
                for npc_id, npc in self.npcs.items()
            },

            # Tier 4 — investigation board (reasoning layer, salience-filtered top-5)
            "investigation_board": self.board.board_summary(
                self.npcs, self.truth_events, self.rumors, self.command_count
            ),

            # Raw NPC state (axes + memory)
            "npcs": {npc_id: npc.status() for npc_id, npc in self.npcs.items()},

            "social_log": self.social_log[-10:],
            "commands_issued": self.command_count,
            "scenario_id": getattr(self, "scenario_id", "hargrove_affair"),
        }


# Global singleton
STATE = GameState()
