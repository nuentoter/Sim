"""
Core game state for Gull Island detective simulation.
Now includes:
- NPC registry
- Case state
- Rumors
- Investigation board
- Scenario tracking
- Weather system
"""

from weather import WeatherSystem
from clock import GameClock
from case import Case
from investigation import InvestigationBoard


class GameState:
    def __init__(self):
        # -----------------------------
        # CORE SIMULATION STATE
        # -----------------------------

        self.npcs = {}                 # id -> NPC
        self.case = None              # active case object
        self.clock = None             # time system (existing in your project)
        self.board = None             # investigation board

        # -----------------------------
        # SIMULATION LAYERS
        # -----------------------------

        self.rumors = []
        self.truth_events = []
        self.social_log = []

        # -----------------------------
        # WORLD SYSTEMS
        # -----------------------------

        self.weather = WeatherSystem()
        self.world_events = []

        # -----------------------------
        # META STATE
        # -----------------------------

        self.scenario_id = None
        self.command_count = 0

    # ------------------------------------------------------------
    # CORE UTILITIES
    # ------------------------------------------------------------

    def increment_command(self):
        self.command_count += 1

    def add_npc(self, npc):
        self.npcs[npc.id] = npc

    def get_npc(self, npc_id):
        return self.npcs.get(npc_id)

    # ------------------------------------------------------------
    # SCENARIO SUPPORT (kept compatible with your existing system)
    # ------------------------------------------------------------

    def load_from_scenario(self, scenario):
        """
        In-place reset + scenario load.
        Critical: preserves object reference for Flask app.
        """

        self.npcs = scenario.build_npcs()
        self.case = Case(title=scenario.case_title, victim=scenario.case_victim)
        self.clock = GameClock()
        self.board = InvestigationBoard()

        self.rumors = scenario.build_rumors()
        self.truth_events = scenario.build_truths()

        self.social_log = []
        self.world_events = []

        self.scenario_id = scenario.id
        self.command_count = 0

        # reset weather to calm baseline
        self.weather = WeatherSystem()

    def reset(self):
        """
        Reset to the default scenario (hargrove_affair).
        Keeps the same object reference so Flask handlers stay in sync.
        """
        import scenarios as _sc
        default = _sc.resolve_scenario("hargrove_affair")
        if default:
            self.load_from_scenario(default)

    @classmethod
    def from_scenario(cls, scenario):
        """
        Fresh instance constructor (for testing / isolation).
        """
        state = cls()
        state.load_from_scenario(scenario)
        return state

    # ------------------------------------------------------------
    # SERIALIZATION (for /state endpoint)
    # ------------------------------------------------------------

    def to_dict(self):
        return {
            "scenario_id": self.scenario_id,
            "command_count": self.command_count,

            # core systems
            "npcs": {k: v.status() for k, v in self.npcs.items()},
            "case": self.case.summary() if self.case else None,
            "clock": self.clock.to_dict() if self.clock else None,

            # simulation layers
            "rumors": [r.to_dict() for r in self.rumors] if self.rumors else [],
            "truth_events": [t.to_dict() for t in self.truth_events] if self.truth_events else [],

            # investigation
            "board": self.board.board_summary(
                self.npcs, self.truth_events, self.rumors, self.command_count
            ) if self.board else None,

            # world state
            "weather": self.weather.to_dict() if self.weather else None,
            "world_events": self.world_events[-50:] if self.world_events else []
        }

# ------------------------------------------------------------
# GLOBAL SINGLETON STATE (used by Flask app)
# ------------------------------------------------------------

STATE = GameState()