"""
Weather system for Gull Island simulation.

Simple deterministic weather model:
- calm, rain, fog, storm
- slow transitions
- affects NPC mood, movement, and rumor behavior
"""

import random


WEATHER_STATES = ["calm", "rain", "fog", "storm"]


class WeatherSystem:
    def __init__(self):
        self.type = "calm"
        self.stability = 3
        self.history = []  # optional: track weather over time

    def to_dict(self):
        return {
            "type": self.type,
            "stability": self.stability,
            "history": self.history[-20:],  # last 20 states
        }

    def tick(self):
        """
        Advance weather state slowly and deterministically.
        """

        # decay stability
        self.stability -= 1

        if self.stability > 0:
            return self.type

        # transition
        roll = random.random()

        if self.type == "calm":
            new = "rain" if roll < 0.5 else "fog"

        elif self.type == "rain":
            new = "storm" if roll < 0.3 else "calm"

        elif self.type == "fog":
            new = "rain" if roll < 0.4 else "calm"

        elif self.type == "storm":
            new = "rain"

        else:
            new = "calm"

        # apply transition
        self.type = new
        self.stability = random.randint(2, 6)

        self.history.append(new)

        return self.type

    def get_modifiers(self):
        """
        Returns gameplay effects used by simulation.
        """

        if self.type == "calm":
            return {
                "mood": 0,
                "stress": 0,
                "movement": 1.0,
                "rumor_spread": 1.0
            }

        if self.type == "rain":
            return {
                "mood": -1,
                "stress": 0,
                "movement": 0.9,
                "rumor_spread": 1.0
            }

        if self.type == "fog":
            return {
                "mood": -1,
                "stress": 1,
                "movement": 0.8,
                "rumor_spread": 1.2
            }

        if self.type == "storm":
            return {
                "mood": -2,
                "stress": 2,
                "movement": 0.5,
                "rumor_spread": 0.7
            }

        return {
            "mood": 0,
            "stress": 0,
            "movement": 1.0,
            "rumor_spread": 1.0
        }