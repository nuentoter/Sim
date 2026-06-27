"""
Simple game clock — tracks day and time-of-day period.
"""

PERIODS = ["morning", "afternoon", "evening", "night"]


class GameClock:
    def __init__(self, day: int = 1, period: str = "morning"):
        self.day = day
        self.period = period

    def advance(self):
        idx = PERIODS.index(self.period)
        if idx == len(PERIODS) - 1:
            self.day += 1
            self.period = PERIODS[0]
        else:
            self.period = PERIODS[idx + 1]

    def description(self) -> str:
        return f"Day {self.day}, {self.period.capitalize()}"

    def to_dict(self) -> dict:
        return {"day": self.day, "period": self.period, "description": self.description()}
