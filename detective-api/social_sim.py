"""
Social simulation tick system.

Now includes:
- weather
- passive world events
- NPC autonomous actions (light touch)
"""

import random
from rumor import NOISE_THRESHOLD


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
    Applies weather-based credibility decay to all rumors, then propagates
    each above-noise rumor to NPCs not yet in known_by (~20 % chance per
    tick).  Effects are applied exactly once per NPC per rumor — known_by
    is the single source of truth for "has received".
    """
    if not hasattr(state, "rumors"):
        return

    npcs = getattr(state, "npcs", {})

    for r in state.rumors:
        if not hasattr(r, "credibility"):
            continue

        # Existing behaviour: weather modifier decays credibility each tick.
        r.credibility *= modifiers["rumor_spread"]

        # Noise-level rumors stop propagating.
        if r.credibility <= NOISE_THRESHOLD:
            continue

        # Propagate to NPCs not yet in known_by; apply effects exactly once.
        for npc_id, npc in npcs.items():
            if npc_id in r.known_by:
                continue                     # already received — skip
            if random.random() > 0.20:
                continue                     # ~20 % spread chance per tick
            r.known_by.append(npc_id)
            npc.heard_rumors.append(r)
            for effect in r.effects:
                npc.shift_suspicion(effect.suspicion_delta)
                npc.shift_mood(effect.mood_delta)
                npc.shift_stress(effect.stress_delta)


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
    Inject a player-action-derived rumor into the social network.

    ask    — fires only when an NPC has been questioned more than once;
             islanders notice the detective repeatedly interrogating someone
             and it becomes gossip. Appended to all_rumors so rumor_tick
             picks it up naturally on the next social simulation step.

    accuse — fires unconditionally; accusations are public, dramatic events
             that spread island-wide immediately. All NPCs are marked as
             knowing the rumor at creation time.

    Rumors created here follow the same Rumor dataclass contract as
    scenario-seeded rumors and pass through the same mutate() pipeline.
    """
    from rumor import Rumor, RumorEffect
    import uuid

    if action == "ask":
        # Only generate gossip after repeated questioning — first contact is
        # unremarkable; being questioned multiple times is island news.
        if acting_npc.times_questioned() < 2:
            return
        topic_str = topic or "something"
        content = (
            f"Someone has been asking {acting_npc.name} pointed questions "
            f"about {topic_str} — and not for the first time."
        )
        subjects = [acting_npc.id]
        if topic:
            subjects.append(topic.lower().replace(" ", "_"))
        rumor = Rumor(
            id=str(uuid.uuid4())[:8],
            content=content,
            original_content=content,
            source_npc_id=acting_npc.id,
            subjects=subjects,
            credibility=65,
            distortion_level=0,
            age=0,
            known_by=[acting_npc.id],
            effects=[
                RumorEffect(
                    subject_id=acting_npc.id,
                    suspicion_delta=5,
                    stress_delta=3,
                )
            ],
        )
        all_rumors.append(rumor)

    elif action == "accuse":
        # Accusations are public events — every NPC on the island hears
        # about it immediately (high credibility, no distortion yet).
        content = f"Someone openly accused {acting_npc.name} in front of witnesses."
        rumor = Rumor(
            id=str(uuid.uuid4())[:8],
            content=content,
            original_content=content,
            source_npc_id=acting_npc.id,
            subjects=[acting_npc.id],
            credibility=85,
            distortion_level=0,
            age=0,
            known_by=list(npc_registry.keys()),
            effects=[
                RumorEffect(
                    subject_id=acting_npc.id,
                    suspicion_delta=20,
                    stress_delta=10,
                    mood_delta=-10,
                )
            ],
        )
        all_rumors.append(rumor)


# -----------------------------
# EVENT LOGGING
# -----------------------------

def log_event(state, event):
    if not hasattr(state, "world_events"):
        state.world_events = []

    state.world_events.append(event)

    # keep bounded
    state.world_events = state.world_events[-50:]