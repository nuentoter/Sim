"""
Social simulation tick engine — with epistemic discipline.

Each tick:
  1. Run 0–2 background NPC conversations.
     - Speakers prioritise high-credibility rumors.
     - Rumors below NOISE_THRESHOLD are never shared.
  2. Apply rumor decay to every rumor:
     - BASE_DECAY per tick, offset by REINFORCE_AMOUNT for each share this tick.
     - Rumors that fall to or below NOISE_THRESHOLD stop propagating.
  3. Decay NPC beliefs whose source rumor has gone to noise.
  4. Return a log of what happened.
"""

from __future__ import annotations
import random
import logging
from typing import Optional

from npc import NPC
from rumor import Rumor, RumorEffect, mutate, NOISE_THRESHOLD, REINFORCE_AMOUNT, BASE_DECAY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Location proximity
# ---------------------------------------------------------------------------

LOCATION_CLUSTERS: list = [
    {"The Rusty Anchor pub", "The Harbour Cafe"},
    {"The Island Marina", "The Harbour Cafe"},
    {"Hargrove Manor", "garden", "east wing"},
]


def _are_proximate(a: NPC, b: NPC, day: int) -> bool:
    loc_a = a.location.lower()
    loc_b = b.location.lower()
    for cluster in LOCATION_CLUSTERS:
        cl = {c.lower() for c in cluster}
        if any(loc_a in c for c in cl) and any(loc_b in c for c in cl):
            return True
    return day > 1


# ---------------------------------------------------------------------------
# Effect application
# ---------------------------------------------------------------------------

def _apply_effect(receiver: NPC, effect: RumorEffect, npc_registry: dict):
    if effect.suspicion_delta:
        receiver.shift_suspicion(effect.suspicion_delta // 2)
    if effect.mood_delta:
        receiver.shift_mood(effect.mood_delta)
    if effect.stress_delta:
        receiver.shift_stress(effect.stress_delta)
    for topic_key in effect.unlock_topics:
        for item in receiver.knowledge:
            if item.matches(topic_key):
                item.suspicion_max = min(100, item.suspicion_max + 15)
                item.mood_min = max(0, item.mood_min - 10)
    for topic_key in effect.block_topics:
        for item in receiver.knowledge:
            if item.matches(topic_key):
                item.suspicion_max = max(0, item.suspicion_max - 20)


# ---------------------------------------------------------------------------
# NPC conversation
# ---------------------------------------------------------------------------

def _npc_conversation(
    speaker: NPC,
    listener: NPC,
    all_rumors: list,
    npc_registry: dict,
    game_time: str,
    shared_this_tick: set,       # mutable: rumor ids shared this tick (for reinforcement)
    salience_map: Optional[dict] = None,  # {rumor_id: score 0-100}
) -> Optional[str]:
    """
    Attempt one rumor share from speaker → listener.
    Only active (above noise threshold) rumors are eligible.
    High-salience rumors are preferred via weighted selection.
    Returns a log string or None.
    """
    eligible = [
        r for r in all_rumors
        if r.credibility > NOISE_THRESHOLD
        and speaker.id in r.known_by
        and listener.id not in r.known_by
    ]

    if not eligible:
        _share_memory_event(speaker, listener, game_time)
        return None

    # Salience-weighted selection:
    #   weight = credibility × (0.5 + salience/100)
    #   score 0  → 0.5×  (slower spread)
    #   score 50 → 1.0×  (neutral)
    #   score 100 → 1.5× (faster spread)
    if salience_map:
        weights = [r.credibility * (0.5 + salience_map.get(r.id, 50) / 100) for r in eligible]
    else:
        weights = [r.credibility for r in eligible]

    rumor_to_share = random.choices(eligible, weights=weights, k=1)[0]

    # Mutate through speaker's lens
    mutated = mutate(rumor_to_share, receiver_stress=speaker.stress, receiver_suspicion=speaker.suspicion)
    mutated.known_by.append(listener.id)

    # Persist mutation back to canonical pool
    for i, r in enumerate(all_rumors):
        if r.id == rumor_to_share.id:
            all_rumors[i] = mutated
            break

    # Track for reinforcement
    shared_this_tick.add(mutated.id)

    # Listener receives the rumor
    listener.heard_rumors.append(mutated)
    snippet = mutated.content[:80] + ("..." if len(mutated.content) > 80 else "")
    listener.remember("heard_rumor", f'Heard from {speaker.name}: "{snippet}"', game_time, weight=2)

    # Belief formation — listener derives a belief from this rumor
    listener.belief_system.update_from_rumor(mutated, listener.suspicion, game_time)

    # Apply rumor effects to listener's axes
    for effect in mutated.effects:
        _apply_effect(listener, effect, npc_registry)

    log = (
        f"[SOCIAL] {speaker.name} → {listener.name}: "
        f"\"{mutated.content[:55]}{'...' if len(mutated.content) > 55 else ''}\" "
        f"(cred:{mutated.credibility} distort:{mutated.distortion_level})"
    )
    logger.debug(log)
    return log


def _share_memory_event(speaker: NPC, listener: NPC, game_time: str):
    notable = [e for e in speaker.memory if e.weight >= 2]
    if not notable:
        return
    event = random.choice(notable)
    listener.shift_stress(random.randint(1, 3))
    listener.remember("hearsay", f"Heard informally from {speaker.name} (re: {event.event_type})", game_time, weight=1)


# ---------------------------------------------------------------------------
# Player-action rumor injection
# ---------------------------------------------------------------------------

def inject_player_rumor(
    action: str,
    npc_hint: Optional[str],
    topic: Optional[str],
    acting_npc: Optional[NPC],
    all_rumors: list,
    npc_registry: dict,
    game_time: str,
):
    from rumor import Rumor, RumorEffect
    import uuid

    if action == "accuse" and acting_npc:
        content = f"The detective publicly accused {acting_npc.name} of being involved in Eleanor's death."
        effects = [RumorEffect(subject_id=acting_npc.id, suspicion_delta=15, mood_delta=-8, stress_delta=10)]
        r = Rumor(
            id=str(uuid.uuid4())[:8],
            content=content,
            original_content=content,
            source_npc_id="player",
            subjects=[acting_npc.id],
            credibility=80,
            distortion_level=0,
            effects=effects,
        )
        r.known_by = ["player"]
        all_rumors.append(r)
        acting_npc.heard_rumors.append(r)
        acting_npc.receive_accusation(game_time)
        # Propagate immediately to one witness
        others = [n for n in npc_registry.values() if n.id != acting_npc.id]
        if others:
            witness = random.choice(others)
            witness.heard_rumors.append(r)
            witness.belief_system.update_from_rumor(r, witness.suspicion, game_time)
            _apply_effect(witness, effects[0], npc_registry)
            r.known_by.append(witness.id)

    elif action == "ask" and acting_npc and topic:
        if acting_npc.times_questioned() >= 2:
            content = f"The detective has been pressing {acting_npc.name} about {topic}."
            r = Rumor(
                id=str(uuid.uuid4())[:8],
                content=content,
                original_content=content,
                source_npc_id="player",
                subjects=[acting_npc.id],
                credibility=65,
                distortion_level=5,
                effects=[RumorEffect(subject_id=acting_npc.id, stress_delta=4)],
            )
            r.known_by = ["player"]
            all_rumors.append(r)


# ---------------------------------------------------------------------------
# Rumor lifecycle — decay, reinforcement, pruning
# ---------------------------------------------------------------------------

def _apply_decay(all_rumors: list, shared_this_tick: set) -> list:
    """
    Apply credibility decay to all rumors for one tick.
    Rumors shared this tick receive a reinforcement offset.
    Returns the updated list (noise entries kept but flagged, old noise pruned).
    """
    surviving = []
    for rumor in all_rumors:
        rumor.age += 1

        if rumor.id in shared_this_tick:
            # Corroboration: multiple shares slow the decay this tick
            delta = REINFORCE_AMOUNT - BASE_DECAY      # net: +1
        else:
            delta = -BASE_DECAY

        # Player-injected rumors decay faster (they're hot takes)
        if rumor.source_npc_id == "player":
            delta -= 1

        rumor.credibility = max(0, min(100, rumor.credibility + delta))

        # Prune: very old noise that no one is talking about
        is_noise = rumor.credibility <= NOISE_THRESHOLD
        is_ancient = rumor.age > 30
        is_isolated = len(rumor.known_by) <= 1
        if is_noise and is_ancient and is_isolated:
            continue   # drop silently
        surviving.append(rumor)

    return surviving


def _decay_npc_beliefs(npcs: dict, active_rumor_ids: set):
    """Tell each NPC's BeliefSystem which rumors are still active so it can decay stale ones."""
    for npc in npcs.values():
        npc.belief_system.decay_rumor_beliefs(active_rumor_ids)


# ---------------------------------------------------------------------------
# Truth broadcast — propagate TruthEvents to NPC beliefs when player finds them
# ---------------------------------------------------------------------------

def broadcast_truth(truth_event, npcs: dict, game_time: str):
    """
    When a truth is directly uncovered (e.g. via clue collection), broadcast
    it to all NPCs so they can form high-confidence beliefs from it.
    """
    for npc in npcs.values():
        npc.belief_system.update_from_truth(truth_event, game_time)


# ---------------------------------------------------------------------------
# Main tick
# ---------------------------------------------------------------------------

def tick(
    npcs: dict,
    all_rumors: list,
    game_time: str,
    day: int,
    n_conversations: Optional[int] = None,
    salience_map: Optional[dict] = None,
) -> tuple:
    """
    Run the social simulation for one command tick.

    Returns:
        (updated_rumors: list, log_entries: list[str])
    """
    if n_conversations is None:
        n_conversations = random.choices([0, 1, 2], weights=[40, 40, 20])[0]

    logs: list = []
    shared_this_tick: set = set()
    npc_list = list(npcs.values())

    for _ in range(n_conversations):
        if len(npc_list) < 2:
            break
        speaker, listener = random.sample(npc_list, 2)

        if not _are_proximate(speaker, listener, day):
            continue

        # Stressed or highly suspicious NPCs gossip less
        gossip_chance = 1.0 - (speaker.stress / 200) - (speaker.suspicion / 300)
        if random.random() > gossip_chance:
            continue

        log = _npc_conversation(speaker, listener, all_rumors, npcs, game_time, shared_this_tick, salience_map)
        if log:
            logs.append(log)

    # Apply decay + pruning
    updated_rumors = _apply_decay(all_rumors, shared_this_tick)

    # Sync NPC beliefs with the now-active rumor set
    active_ids = {r.id for r in updated_rumors if r.credibility > NOISE_THRESHOLD}
    _decay_npc_beliefs(npcs, active_ids)

    # Passive NPC recovery
    for npc in npcs.values():
        npc.shift_stress(-1)
        npc.shift_mood(1)

    return updated_rumors, logs
