"""
Action handlers — generic simulation engine.

All NPC interactions go through handle_talk / handle_ask / handle_accuse /
handle_build_rapport. No NPC-specific logic lives here.
"""

from __future__ import annotations
from typing import Optional

from game_state import GameState, STATE
from npc import resolve_npc, npc_roster, NPC


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------

def _response(
    message: str,
    state: GameState,
    *,
    hint: Optional[str] = None,
    event: Optional[str] = None,
) -> dict:
    r: dict = {
        "message": message,
        "time": state.clock.description(),
        "case_status": state.case.status,
    }
    if hint:
        r["hint"] = hint
    if event:
        r["event"] = event
    return r


def _npc_not_found(name_hint: Optional[str], state: GameState) -> dict:
    roster = npc_roster(state.npcs)
    who = f'"{name_hint}"' if name_hint else "anyone"
    return _response(
        f"You don't see {who} around. People you know of:\n{roster}",
        state,
        hint="Try: 'talk to Tom', 'talk to Petra', 'talk to Nour'",
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_help(state: GameState, parsed: dict) -> dict:
    roster = npc_roster(state.npcs)
    msg = (
        "Detective's handbook:\n"
        "  look around                    — survey your surroundings\n"
        "  go to <place>                  — travel somewhere\n"
        "  talk to <NPC name>             — approach an NPC\n"
        "  ask <NPC name> about <topic>   — question an NPC on a subject\n"
        "  accuse <NPC name>              — make an accusation\n"
        "  be nice to <NPC name>          — build rapport\n"
        "  pick up <item>                 — collect a clue\n"
        "  examine <item>                 — study a clue\n"
        "  wait                           — advance the clock\n"
        "  status                         — review case progress\n"
        "  solve case                     — attempt to close the case\n"
        "  reset                          — start over\n\n"
        f"People you know of:\n{roster}"
    )
    return _response(msg, state)


def handle_status(state: GameState, parsed: dict) -> dict:
    summary = state.case.summary()
    clue_list = "\n  ".join(summary["clues_found"]) if summary["clues_found"] else "none yet"

    # --- Tier 1: confirmed truths ---
    truth_lines = [f"  [{t.source_type.upper()}] {t.description}" for t in state.truth_events]
    truth_section = "\n".join(truth_lines)

    # --- Tier 2: active rumors ---
    active = state.active_rumors()
    noise_count = len(state.noise_rumors())
    rumor_lines = []
    for r in sorted(active, key=lambda x: x.credibility, reverse=True):
        known_n = len([x for x in r.known_by if x != "player"])
        distort_tag = f" [~{r.distortion_level}% distorted]" if r.distortion_level > 25 else ""
        rumor_lines.append(
            f"  • (cred:{r.credibility:3d}) \"{r.content[:65]}{'...' if len(r.content) > 65 else ''}\" "
            f"— {known_n} NPCs know{distort_tag}"
        )
    rumor_section = "\n".join(rumor_lines) if rumor_lines else "  none circulating"
    noise_note = f"  ({noise_count} low-credibility rumor{'s' if noise_count != 1 else ''} suppressed as noise)\n" if noise_count else ""

    # --- Tier 3: NPC beliefs ---
    npc_sections = []
    for npc in state.npcs.values():
        bsummary = npc.belief_system.summary()
        dominant = bsummary["dominant_beliefs"]
        belief_lines = "\n    ".join(
            f"[{b['confidence']:3d}%] {b['statement'][:70]}{'...' if len(b['statement']) > 70 else ''}"
            for b in dominant
        ) if dominant else "no strong beliefs yet"
        npc_sections.append(
            f"  {npc.name} (mood:{npc.mood} stress:{npc.stress} suspicion:{npc.suspicion})\n"
            f"    Beliefs ({bsummary['strong_count']} strong / {bsummary['moderate_count']} moderate / "
            f"{bsummary['weak_count']} weak):\n"
            f"    {belief_lines}"
        )

    msg = (
        f"=== {summary['title']} ===\n"
        f"Victim: {summary['victim']}  |  Status: {summary['status'].upper()}\n"
        f"Time: {state.clock.description()}\n\n"
        f"[TIER 1] Confirmed Truths ({len(state.truth_events)}):\n{truth_section}\n\n"
        f"[TIER 2] Active Rumors ({len(active)}):\n{noise_note}{rumor_section}\n\n"
        f"[TIER 3] NPC Beliefs:\n" + "\n\n".join(npc_sections) + "\n\n"
        f"Clues collected:\n  {clue_list}"
    )
    return _response(msg, state)


def handle_reset(state: GameState, parsed: dict) -> dict:
    state.reset()
    return _response(
        "The case files shuffle back into the drawer. A new investigation begins.\n\n"
        f"Case: {state.case.title}\n"
        f"Victim: {state.case.victim}\n\n"
        "Type 'help' to see available commands.",
        state,
        event="game_reset",
    )


def handle_wait(state: GameState, parsed: dict) -> dict:
    old = state.clock.period
    state.clock.advance()
    new = state.clock.period

    # NPCs passively recover stress over time
    for npc in state.npcs.values():
        npc.shift_stress(-5)
        npc.shift_mood(2)

    flavour = {
        "morning":   "The sun climbs higher. The streets stir to life.",
        "afternoon": "Shadows shorten. The town bustles.",
        "evening":   "Dusk settles in. Lanterns flicker on.",
        "night":     "Silence falls. Somewhere a dog barks at the dark.",
    }
    msg = (
        f"Time passes... {old.capitalize()} gives way to {new}.\n"
        f"{flavour[new]}\n"
        f"It is now {state.clock.description()}."
    )
    return _response(msg, state, event="time_advanced")


def handle_time(state: GameState, parsed: dict) -> dict:
    return _response(f"It is {state.clock.description()}.", state)


def handle_go(state: GameState, parsed: dict) -> dict:
    dest = (parsed.get("topic") or "").strip()
    if not dest:
        return _response(
            "Go where? Name a destination.",
            state,
            hint="Try: 'go to The Rusty Anchor', 'go to the marina', 'go to the manor'",
        )

    descriptions = {
        "pub":            "The Rusty Anchor — low beams, sawdust floor, stale beer. Tom Baker hunches over a corner table.",
        "rusty anchor":   "The Rusty Anchor — low beams, sawdust floor, stale beer. Tom Baker hunches over a corner table.",
        "manor":          "Hargrove Manor looms against the grey sky. Police tape cordons the east wing. Muddy footprints cross the lawn.",
        "hargrove manor": "Hargrove Manor looms against the grey sky. Police tape cordons the east wing. Muddy footprints cross the lawn.",
        "east wing":      "The east wing reeks of must. A wall safe hangs open — the ledger inside is disturbed. On the floor: a torn note and a gold pocket watch.",
        "garden":         "The manor garden is quiet. Muddy footprints cut across the lawn toward the gate.",
        "marina":         "The Island Marina. Petra Vance is at the dock office, clipboard in hand.",
        "harbour":        "The Island Marina. Petra Vance is at the dock office, clipboard in hand.",
        "harbor":         "The Island Marina. Petra Vance is at the dock office, clipboard in hand.",
        "cafe":           "The Harbour Cafe. Nour Saleh is behind the counter, wiping down the espresso machine.",
        "harbour cafe":   "The Harbour Cafe. Nour Saleh is behind the counter, wiping down the espresso machine.",
        "police station": "The inspector drums his fingers. 'Bring hard evidence and I'll make an arrest. Suspicion alone won't do.'",
        "market":         "The market square. Townsfolk speak in hushed voices. The murder is on everyone's lips.",
    }

    dest_lower = dest.lower()
    for key, desc in descriptions.items():
        if key in dest_lower:
            return _response(f"You head to {dest.title()}.\n\n{desc}", state, event="location_change")

    return _response(
        f"You make your way toward {dest} but find little of obvious interest.",
        state,
        hint="Known places: pub, manor, east wing, marina, cafe, police station",
    )


def handle_look(state: GameState, parsed: dict) -> dict:
    topic = (parsed.get("topic") or "").strip().lower()

    if not topic:
        roster = npc_roster(state.npcs)
        return _response(
            "You survey your surroundings. The investigation spans:\n"
            "  • The Rusty Anchor pub\n"
            "  • Hargrove Manor (east wing — scene of the crime)\n"
            "  • The Island Marina\n"
            "  • The Harbour Cafe\n"
            "  • The police station\n\n"
            f"People you can speak to:\n{roster}\n\n"
            f"Time: {state.clock.description()}",
            state,
            hint="Try: 'go to east wing', 'talk to Tom', 'ask Petra about the boat'",
        )

    if any(k in topic for k in ("footprint", "mud", "track")):
        desc = state.case.add_clue("footprints")
        if desc:
            return _response(f"You crouch and study the tracks.\nClue found: {desc}", state, event="clue_found")
        return _response("The muddy footprints lead toward the garden gate — you've already noted them.", state)

    if any(k in topic for k in ("safe", "east wing")):
        return _response(
            "The wall safe is open. Inside: a disturbed ledger. On the floor: a torn note and a gold pocket watch.\n"
            "Try: 'pick up ledger', 'pick up note', 'pick up pocket watch'",
            state,
        )

    return _response(f"You examine {topic} carefully but notice nothing new.", state)


# ---------------------------------------------------------------------------
# Generic NPC interaction
# ---------------------------------------------------------------------------

def handle_talk(state: GameState, parsed: dict) -> dict:
    npc_hint = parsed.get("npc_hint") or ""
    npc = resolve_npc(npc_hint, state.npcs)
    if not npc:
        return _npc_not_found(npc_hint or None, state)

    state.clock.advance()
    greeting = npc.greet(state.clock.description())

    topics = _available_topics(npc)
    hint_text = f"You can ask {npc.name} about: {topics}" if topics else None

    return _response(greeting, state, hint=hint_text, event="time_advanced")


def handle_ask(state: GameState, parsed: dict) -> dict:
    import social_sim
    npc_hint = parsed.get("npc_hint") or ""
    topic = (parsed.get("topic") or "").strip()

    npc = resolve_npc(npc_hint, state.npcs)
    if not npc:
        return _npc_not_found(npc_hint or None, state)

    if not topic:
        return _response(
            f"Ask {npc.name} about what?",
            state,
            hint=f"Try: 'ask {npc.name} about [topic]'",
        )

    state.clock.advance()
    response_text, clue_id = npc.respond_to_topic(topic, state.clock.description())

    event = "time_advanced"
    clue_note = ""
    if clue_id:
        desc = state.case.add_clue(clue_id)
        if desc:
            clue_note = f"\n\n[Clue recorded: {desc}]"
            event = "clue_found"

    # Repeated questioning generates gossip that propagates through the network
    social_sim.inject_player_rumor(
        action="ask",
        npc_hint=npc_hint,
        topic=topic,
        acting_npc=npc,
        all_rumors=state.rumors,
        npc_registry=state.npcs,
        game_time=state.clock.description(),
    )

    return _response(
        f"{npc.name}: {response_text}{clue_note}",
        state,
        event=event,
    )


def handle_accuse(state: GameState, parsed: dict) -> dict:
    import social_sim
    npc_hint = parsed.get("npc_hint") or ""
    npc = resolve_npc(npc_hint, state.npcs)
    if not npc:
        return _npc_not_found(npc_hint or None, state)

    state.clock.advance()
    response_text = npc.receive_accusation(state.clock.description())

    # Accusation always creates an island-wide rumor immediately
    social_sim.inject_player_rumor(
        action="accuse",
        npc_hint=npc_hint,
        topic=None,
        acting_npc=npc,
        all_rumors=state.rumors,
        npc_registry=state.npcs,
        game_time=state.clock.description(),
    )

    return _response(response_text, state, event="accusation_made")


def handle_build_rapport(state: GameState, parsed: dict) -> dict:
    npc_hint = parsed.get("npc_hint") or ""

    if npc_hint:
        npc = resolve_npc(npc_hint, state.npcs)
        if not npc:
            return _npc_not_found(npc_hint, state)
        response_text = npc.receive_compliment(state.clock.description())
        return _response(response_text, state, event="rapport_built")

    # No target — list everyone
    roster = npc_roster(state.npcs)
    return _response(
        f"Who do you want to be kind to?\n{roster}",
        state,
        hint="Try: 'be nice to Tom', 'buy Petra a drink'",
    )


# ---------------------------------------------------------------------------
# Case handlers
# ---------------------------------------------------------------------------

def handle_solve(state: GameState, parsed: dict) -> dict:
    success, msg = state.case.try_solve()
    event = "case_solved" if success else "solve_attempt"
    return _response(msg, state, event=event)


def handle_case(state: GameState, parsed: dict) -> dict:
    return handle_status(state, parsed)


# ---------------------------------------------------------------------------
# Clue handlers
# ---------------------------------------------------------------------------

def handle_collect_clue(state: GameState, parsed: dict) -> dict:
    clue_id = parsed.get("topic")
    if not clue_id:
        return _response("Pick up what, exactly?", state)
    desc = state.case.add_clue(clue_id)
    if desc:
        return _response(f"You pick it up carefully.\nClue added: {desc}", state, event="clue_found")
    if clue_id in state.case.clues_found:
        return _response("You already have that.", state)
    return _response("You don't see that here.", state)


def handle_examine_clue(state: GameState, parsed: dict) -> dict:
    clue_id = parsed.get("topic")
    if not clue_id:
        return _response("Examine what?", state)
    desc = state.case.add_clue(clue_id)
    if desc:
        return _response(f"You study it closely.\nClue found: {desc}", state, event="clue_found")
    known = state.case.ALL_CLUES.get(clue_id)
    if known and clue_id in state.case.clues_found:
        return _response(f"You re-examine it: {known}", state)
    return _response("You don't have that clue, or it isn't here right now.", state)


def handle_unknown(state: GameState, parsed: dict) -> dict:
    raw = parsed.get("raw", "")
    return _response(
        f"Not sure how to '{raw}'. Type 'help' for available commands.",
        state,
        hint="help",
    )


# ---------------------------------------------------------------------------
# Helper: list available topics for an NPC (unrevealed items within reach)
# ---------------------------------------------------------------------------

def _available_topics(npc: NPC) -> str:
    """Return a comma-separated hint of topics the NPC might discuss."""
    reachable = []
    for item in npc.knowledge:
        if not item.revealed:
            reachable.append(item.topic_keys[0])
    if not reachable:
        return "nothing new"
    return ", ".join(reachable[:4])


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

HANDLERS = {
    "help":          handle_help,
    "status":        handle_status,
    "reset":         handle_reset,
    "wait":          handle_wait,
    "time":          handle_time,
    "go":            handle_go,
    "look":          handle_look,
    "talk":          handle_talk,
    "ask":           handle_ask,
    "accuse":        handle_accuse,
    "build_rapport": handle_build_rapport,
    "collect_clue":  handle_collect_clue,
    "examine_clue":  handle_examine_clue,
    "solve":         handle_solve,
    "case":          handle_case,
    "unknown":       handle_unknown,
}


def dispatch(raw_input: str) -> dict:
    import social_sim
    from command_parser import parse
    parsed = parse(raw_input)
    STATE.command_count += 1
    handler = HANDLERS.get(parsed["action"], handle_unknown)
    result = handler(STATE, parsed)

    # Run background social tick — NPCs gossip, rumors decay, beliefs update
    updated_rumors, tick_logs = social_sim.tick(
        npcs=STATE.npcs,
        all_rumors=STATE.rumors,
        game_time=STATE.clock.description(),
        day=STATE.clock.day,
    )
    STATE.rumors = updated_rumors
    if tick_logs:
        STATE.social_log.extend(tick_logs)
        STATE.social_log = STATE.social_log[-50:]   # bounded ring buffer

    return result
