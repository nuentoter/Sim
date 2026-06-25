"""
Case system — fully decoupled from NPC logic.

NPCs may reference case_clue_id on their KnowledgeItems; the handlers
are responsible for calling case.add_clue() when those items are revealed.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Case:
    title: str = "The Hargrove Affair"
    victim: str = "Eleanor Voss"
    status: str = "open"          # open | solved | cold
    clues_found: list = field(default_factory=list)   # list of clue_ids
    suspects_cleared: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    ALL_CLUES: dict = field(default_factory=lambda: {
        "torn_note":         "A torn note reading 'Meet me at midnight — H'.",
        "ledger":            "A leather ledger showing irregular withdrawals from the Hargrove estate.",
        "pocket_watch":      "A gold pocket watch engraved 'To R.H. — with gratitude'.",
        "footprints":        "Muddy footprints leading from the east wing to the garden gate.",
        "witness_msg":       "Tom Baker's account placing himself at The Rusty Anchor all night.",
        "unregistered_skiff":"An unregistered skiff that left the marina around midnight on the night of the murder.",
    })

    SOLVE_REQUIRED: set = field(default_factory=lambda: {"ledger", "witness_msg", "pocket_watch"})

    def add_clue(self, clue_id: str) -> Optional[str]:
        """Add a clue if not already collected. Returns description or None."""
        if clue_id and clue_id in self.ALL_CLUES and clue_id not in self.clues_found:
            self.clues_found.append(clue_id)
            return self.ALL_CLUES[clue_id]
        return None

    def try_solve(self) -> tuple:
        """Returns (success: bool, message: str)."""
        if self.status == "solved":
            return True, "The case is already closed."
        found = set(self.clues_found)
        missing = self.SOLVE_REQUIRED - found
        if missing:
            readable = ", ".join(k.replace("_", " ") for k in sorted(missing))
            return False, f"Not enough evidence. Still need: {readable}."
        self.status = "solved"
        return True, (
            "Case solved. The evidence points unambiguously to Reginald Hargrove. "
            "The pocket watch, the tampered ledger, and the midnight note all tie back to him. "
            "You place the call to the inspector. Justice will be served."
        )

    def summary(self) -> dict:
        return {
            "title": self.title,
            "victim": self.victim,
            "status": self.status,
            "clues_found": [self.ALL_CLUES.get(c, c) for c in self.clues_found],
            "clue_ids": list(self.clues_found),
            "suspects_cleared": list(self.suspects_cleared),
            "notes": list(self.notes),
        }
