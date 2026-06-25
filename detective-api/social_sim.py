"""
Social simulation tick engine.

Called once per player command. Runs 0–2 background NPC conversations,
propagating memory events and rumors through the NPC graph.

Conversation eligibility: two NPCs can "chat" if they share a location
cluster (proximity model) OR if enough time has passed for one to have
visited the other.

Effect application: when an NPC receives a rumor:
  - their suspicion of the rumor's subject shifts
  - their mood and stress shift
  - certain KnowledgeItems may be unlocked or suppressed
"""

from __future__ import annotations
import random
import logging
from typing import Optional

from npc import NPC
from rumor import Rumor, RumorEffect, mutate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Location proximity clusters
# NPCs in the same cluster can talk without travel overhead.
# ---------------------------------------------------------------------------

LOCATION_CLUSTERS: list = [
    {"The Rusty Anchor pub", "The Harbour Cafe"},       # town-centre cluster
    {"The Island Marina", "The Harbour Cafe"},           # harbour cluster
    {"Hargrove Manor", "garden", "east wing"},           # estate cluster
]


def _are_proximate(a: NPC, b: NPC, day: int) -> bool:
    """Two NPCs can meet if they share a cluster, or later in the day (word travels)."""
    loc_a = a.location.lower()
    loc_b = b.location.lower()
    for cluster in LOCATION_CLUSTERS:
        cluster_lower = {c.lower() for c in cluster}
        if any(loc_a in c for c in cluster_lower) and any(loc_b in c for c in cluster_lower):
            return True
    # After day 1, news travels island-wide
    return day > 1


# ---------------------------------------------------------------------------
# Effect application
# ---------------------------------------------------------------------------

def _apply_effect(receiver: NPC, effect: RumorEffect, npc_registry: dict):
    """Apply a RumorEffect to the receiving NPC."""
    # Suspicion: shift receiver's suspicion OF the subject
    # If subject is another NPC, shift receiver's internal suspicion
    # (We track suspicion as a property of the NPC themselves — simplification:
    # a receiver's overall suspicion shifts, weighted by how much they care about the subject)
    if effect.suspicion_delta:
        receiver.shift_suspicion(effect.suspicion_delta // 2)

    if effect.mood_delta:
        receiver.shift_mood(effect.mood_delta)

    if effect.stress_delta:
        receiver.shift_stress(effect.stress_delta)

    # Unlock/block KnowledgeItems by adjusting their thresholds
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
# Single NPC-to-NPC conversation
# ---------------------------------------------------------------------------

def _npc_conversation(
    speaker: NPC,
    listener: NPC,
    all_rumors: list,
    npc_registry: dict,
    game_time: str,
) -> Optional[str]:
    """
    Simulate one background conversation between speaker and listener.
    Returns a log string describing what happened, or None if nothing occurred.
    """
    # Pick what to share: a rumor the speaker knows but listener does not
    shareable_rumors = [
        r for r in all_rumors
        if speaker.id in r.known_by and listener.id not in r.known_by
    ]

    if not shareable_rumors:
        # Nothing new to share — speaker may still gossip about a memory
        _share_memory_event(speaker, listener, game_time)
        return None

    # Share the most credible rumor available
    rumor_to_share = max(shareable_rumors, key=lambda r: r.credibility)

    # Mutate the rumor as it passes through the speaker's lens
    mutated = mutate(
        rumor_to_share,
        receiver_stress=speaker.stress,
        receiver_suspicion=speaker.suspicion,
    )
    mutated.known_by.append(listener.id)

    # Update the canonical rumor in the registry
    for i, r in enumerate(all_rumors):
        if r.id == rumor_to_share.id:
            all_rumors[i] = mutated
            break

    # Listener receives and reacts to the rumor
    listener.heard_rumors.append(mutated)
    listener.remember(
        "heard_rumor",
        f"Heard from {speaker.name}: \"{mutated.content[:80]}...\"" if len(mutated.content) > 80
        else f"Heard from {speaker.name}: \"{mutated.content}\"",
        game_time,
        weight=2,
    )

    # Apply effects
    for effect in mutated.effects:
        _apply_effect(listener, effect, npc_registry)

    log = (
        f"[SOCIAL] {speaker.name} told {listener.name}: "
        f"\"{mutated.content[:60]}{'...' if len(mutated.content) > 60 else ''}\" "
        f"(cred:{mutated.credibility} distort:{mutated.distortion_level})"
    )
    logger.debug(log)
    return log


def _share_memory_event(speaker: NPC, listener: NPC, game_time: str):
    """Speaker shares a notable memory as informal conversation."""
    notable = [e for e in speaker.memory if e.weight >= 2]
    if not notable:
        return
    event = random.choice(notable)
    # Convert to a rumor-like influence: mild suspicion increase toward subject
    listener.shift_stress(random.randint(1, 4))
    listener.remember(
        "hearsay",
        f"Heard informally from {speaker.name} (re: {event.event_type})",
        game_time,
        weight=1,
    )


# ---------------------------------------------------------------------------
# Player-action → rumor injection
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
    """
    When the player performs an action (especially accusation or major questioning),
    generate a rumor about it that will propagate through the network.
    """
    from rumor import Rumor, RumorEffect
    import uuid

    if action == "accuse" and acting_npc:
        content = f"The detective publicly accused {acting_npc.name} of being involved in Eleanor's death."
        effects = [
            RumorEffect(
                subject_id=acting_npc.id,
                suspicion_delta=15,
                mood_delta=-8,
                stress_delta=10,
            )
        ]
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
        # The accusation is immediately known by all NPCs present
        r.known_by = ["player"]
        all_rumors.append(r)
        # The accused NPC and one random other NPC hear it immediately
        acting_npc.heard_rumors.append(r)
        acting_npc.receive_accusation(game_time)
        others = [n for n in npc_registry.values() if n.id != acting_npc.id]
        if others:
            witness = random.choice(others)
            witness.heard_rumors.append(r)
            _apply_effect(witness, effects[0], npc_registry)
            r.known_by.append(witness.id)

    elif action == "ask" and acting_npc and topic:
        # Intensive questioning creates gossip
        if acting_npc.times_questioned() >= 2:
            content = (
                f"The detective has been asking {acting_npc.name} a lot of questions "
                f"about {topic}."
            )
            r = Rumor(
                id=str(uuid.uuid4())[:8],
                content=content,
                original_content=content,
                source_npc_id="player",
                subjects=[acting_npc.id],
                credibility=70,
                distortion_level=5,
                effects=[RumorEffect(subject_id=acting_npc.id, stress_delta=5)],
            )
            r.known_by = ["player"]
            all_rumors.append(r)


# ---------------------------------------------------------------------------
# Main tick
# ---------------------------------------------------------------------------

def tick(
    npcs: dict,
    all_rumors: list,
    game_time: str,
    day: int,
    n_conversations: Optional[int] = None,
) -> list:
    """
    Run background social simulation for one command tick.

    Args:
        npcs:          NPC registry {id: NPC}
        all_rumors:    mutable list of all Rumor objects (modified in-place)
        game_time:     current clock description string
        day:           current day number (affects proximity)
        n_conversations: override number of conversations (default: 0–2 random)

    Returns:
        list of log strings describing what happened this tick
    """
    if n_conversations is None:
        n_conversations = random.choices([0, 1, 2], weights=[40, 40, 20])[0]

    logs = []
    npc_list = list(npcs.values())

    for _ in range(n_conversations):
        if len(npc_list) < 2:
            break
        # Pick two distinct NPCs
        speaker, listener = random.sample(npc_list, 2)

        # Proximity check
        if not _are_proximate(speaker, listener, day):
            continue

        # NPCs who are very stressed or suspicious are less likely to gossip
        gossip_chance = 1.0 - (speaker.stress / 200) - (speaker.suspicion / 300)
        if random.random() > gossip_chance:
            continue

        log = _npc_conversation(speaker, listener, all_rumors, npcs, game_time)
        if log:
            logs.append(log)

        # Age all rumors
    for rumor in all_rumors:
        rumor.age += 1
        # Very old rumors lose credibility slowly
        if rumor.age > 10:
            rumor.credibility = max(0, rumor.credibility - 1)

    return logs
