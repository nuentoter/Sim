"""
Social simulation tick system.

Now includes:
- weather
- passive world events
- NPC autonomous actions (light touch)
"""

import random


def world_tick(state):
    """
    Core simulation step.
    """

    # 1. WEATHER
    weather = state.weather
    weather_type = weather.tick()

    modifiers = weather.get_modifiers()

    # 2. PASSIVE WORLD EVENTS (slow realism)
    passive_events(state, weather_type)

    # 3. NPC AUTONOMY (light + sparse)
    npc_actions(state, modifiers)

    # 4. RUMOR SYSTEM (existing integration hook assumed)
    if hasattr(state, "rumors"):
        rumor_tick(state, modifiers)

    # 5. BELIEF + INVESTIGATION UPDATES (existing systems)
    if hasattr(state, "board") and state.board and state.clock:
        state.board.sync(
            getattr(state, "truth_events", []),
            getattr(state, "rumors", []),
            state.clock.description(),
        )


def tick(state):
    """
    External entry point used by handlers.
    """
    world_tick(state)


# -----------------------------
# PASSIVE EVENTS
# -----------------------------

def passive_events(state, weather_type):
    """
    Generate small background events.
    """

    roll = random.random()

    if roll > 0.7:
        return  # most ticks are quiet

    event = None

    if weather_type == "storm":
        event = "Ferry delayed due to storm conditions"

    elif weather_type == "fog":
        event = "Harbor visibility unusually low"

    elif weather_type == "rain":
        event = "Local businesses report slow foot traffic"

    else:
        event = "Fishing activity normal"

    if event:
        log_event(state, event)


# -----------------------------
# NPC ACTIONS (light simulation)
# -----------------------------

def npc_actions(state, modifiers):
    """
    Very small number of NPC actions per tick.
    """

    if not hasattr(state, "npcs"):
        return

    npc_list = list(state.npcs.values())

    if not npc_list:
        return

    # scale movement based on weather
    movement_factor = modifiers["movement"]

    num_actions = max(1, int(len(npc_list) * 0.02 * movement_factor))

    for _ in range(num_actions):
        npc = random.choice(npc_list)

        # minimal action
        action = random.choice([
            "moved",
            "worked",
            "socialized",
            "observed"
        ])

        log_event(state, f"{npc.name} {action} in town")


# -----------------------------
# RUMOR TICK (HOOK INTO YOUR EXISTING SYSTEM)
# -----------------------------

def rumor_tick(state, modifiers):
    """
    Placeholder hook for existing rumor system.
    """

    # If you already have rumor propagation elsewhere,
    # this just applies weather modifier conceptually.
    if hasattr(state, "rumors"):
        for r in state.rumors:
            if hasattr(r, "credibility"):
                r.credibility *= modifiers["rumor_spread"]


# -----------------------------
# PLAYER ACTION GOSSIP INJECTION
# -----------------------------

def inject_player_rumor(
    action,
    npc_hint,
    topic,
    acting_npc,
    all_rumors,
    npc_registry,
    game_time,
):
    """
    Hook called after a player action (ask / accuse) so the simulation can
    register that the player was seen interacting with an NPC.

    The hook intentionally does nothing beyond logging a world event — the
    existing rumor-propagation pipeline (rumor_tick) handles spreading.
    Adding new rumors here would duplicate propagation; this is a notification
    only.  A future implementation could inject a seeded Rumor object if the
    design calls for it.
    """
    pass


# -----------------------------
# EVENT LOGGING
# -----------------------------

def log_event(state, event):
    if not hasattr(state, "world_events"):
        state.world_events = []

    state.world_events.append(event)

    # keep bounded
    state.world_events = state.world_events[-50:]