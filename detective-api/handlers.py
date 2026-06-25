"""
Action handlers — each function takes (state, parsed) and returns a response dict.
"""

from game_state import GameState, STATE
from typing import Optional


def _response(message: str, state: GameState, *, hint: Optional[str] = None, event: Optional[str] = None) -> dict:
    r = {
        "message": message,
        "time": state.clock.description(),
        "case_status": state.case.status,
    }
    if hint:
        r["hint"] = hint
    if event:
        r["event"] = event
    return r


# ---------------------------------------------------------------------------
# Individual handlers
# ---------------------------------------------------------------------------

def handle_help(state: GameState, parsed: dict) -> dict:
    msg = (
        "Detective's handbook:\n"
        "  look around / examine <place>  — inspect your surroundings\n"
        "  go to <place>                  — travel somewhere\n"
        "  talk to Tom / ask Tom about X  — speak with NPC Tom Baker\n"
        "  pick up <item>                 — collect a clue\n"
        "  examine <item>                 — study a clue you've found\n"
        "  wait / pass time               — advance the clock\n"
        "  status                         — review case progress\n"
        "  solve case                     — attempt to close the case\n"
        "  reset                          — start over"
    )
    return _response(msg, state, hint="Try: 'look around', 'go to The Rusty Anchor', 'talk to Tom'")


def handle_status(state: GameState, parsed: dict) -> dict:
    summary = state.case.summary()
    tom = state.tom.status()
    clue_list = "\n  ".join(summary["clues_found"]) if summary["clues_found"] else "none yet"
    msg = (
        f"=== {summary['title']} ===\n"
        f"Victim: {summary['victim']}  |  Status: {summary['status'].upper()}\n"
        f"Time: {state.clock.description()}\n\n"
        f"Clues collected:\n  {clue_list}\n\n"
        f"Tom Baker — trust: {tom['trust']}/100  |  mood: {tom['mood']}\n"
        f"  Alibi revealed: {tom['alibi_revealed']}\n"
        f"  Key information revealed: {tom['clue_revealed']}"
    )
    return _response(msg, state)


def handle_reset(state: GameState, parsed: dict) -> dict:
    state.reset()
    return _response(
        "The case files shuffle back into the drawer. A new investigation begins...\n\n"
        "Case: The Hargrove Affair\n"
        "Victim: Eleanor Voss, found dead in the east wing of Hargrove Manor.\n"
        "Your job: find the killer.\n\n"
        "Type 'help' for available commands.",
        state,
        event="game_reset"
    )


def handle_wait(state: GameState, parsed: dict) -> dict:
    old_period = state.clock.period
    state.clock.advance()
    new_period = state.clock.period
    flavour = {
        "morning":   "The sun climbs higher. The streets stir to life.",
        "afternoon": "Shadows shorten. The town bustle reaches its peak.",
        "evening":   "Dusk settles over the manor. Lanterns flicker on.",
        "night":     "Silence falls. Somewhere a dog barks at the dark.",
    }
    msg = (
        f"Time passes... {old_period.capitalize()} gives way to {new_period}.\n"
        f"{flavour[new_period]}\n"
        f"It is now {state.clock.description()}."
    )
    return _response(msg, state, event="time_advanced")


def handle_time(state: GameState, parsed: dict) -> dict:
    return _response(f"It is currently {state.clock.description()}.", state)


def handle_go(state: GameState, parsed: dict) -> dict:
    dest = (parsed.get("topic") or "").strip()
    if not dest:
        return _response("Go where? Specify a destination.", state, hint="Try: 'go to The Rusty Anchor'")

    descriptions = {
        "pub": (
            "The Rusty Anchor — low beams, sawdust floor, the smell of stale beer. "
            "Tom Baker hunches over a corner table, nursing a pint."
        ),
        "rusty anchor": (
            "The Rusty Anchor — low beams, sawdust floor, the smell of stale beer. "
            "Tom Baker hunches over a corner table, nursing a pint."
        ),
        "manor": (
            "Hargrove Manor rises against the grey sky. "
            "The east wing is cordoned off with police tape. "
            "You notice muddy footprints near the garden gate."
        ),
        "hargrove manor": (
            "Hargrove Manor rises against the grey sky. "
            "The east wing is cordoned off with police tape. "
            "You notice muddy footprints near the garden gate."
        ),
        "east wing": (
            "The east wing reeks of must and recent intrusion. "
            "A wall safe hangs open — the ledger inside has been disturbed. "
            "On the floor: a torn note and a gold pocket watch."
        ),
        "garden": (
            "The manor garden is quiet. "
            "Muddy footprints cut across the lawn toward the gate."
        ),
        "market": "The market square is busy. Townsfolk gossip but have little of use to offer.",
        "police station": (
            "The inspector taps his desk. "
            "'Bring me hard evidence and I'll make an arrest. "
            "Suspicion alone won't do.'"
        ),
    }

    for key, desc in descriptions.items():
        if key in dest.lower():
            return _response(f"You head to {dest.title()}.\n\n{desc}", state, event="location_change")

    return _response(
        f"You make your way toward {dest}, but find nothing of obvious interest.",
        state,
        hint="Try: manor, east wing, The Rusty Anchor, police station"
    )


def handle_look(state: GameState, parsed: dict) -> dict:
    target = (parsed.get("topic") or "").strip().lower()

    if not target or target in ("around", "here", ""):
        return _response(
            "You survey your surroundings. The investigation spans:\n"
            "  • The Rusty Anchor pub — Tom Baker drinks here\n"
            "  • Hargrove Manor (east wing) — scene of the crime\n"
            "  • The manor garden — suspicious footprints\n"
            "  • The police station — the inspector awaits evidence\n\n"
            f"Time: {state.clock.description()}",
            state,
            hint="Try: 'go to east wing', 'talk to Tom'"
        )

    if "footprint" in target or "mud" in target or "track" in target:
        result = state.case.add_clue("footprints")
        if result:
            return _response(
                f"You crouch down and study the tracks carefully.\nClue found: {result}",
                state, event="clue_found"
            )
        return _response("The muddy footprints lead toward the garden gate.", state)

    if "safe" in target or "east wing" in target:
        return _response(
            "The wall safe is open. Inside you can see a disturbed ledger. "
            "On the floor: a torn note and a pocket watch.\n"
            "Try: 'pick up ledger', 'pick up note', 'pick up pocket watch'",
            state
        )

    return _response(f"You examine {target} carefully but find nothing new.", state)


def handle_talk_tom(state: GameState, parsed: dict) -> dict:
    topic = (parsed.get("topic") or "").strip().lower()
    state.clock.advance()   # conversation takes time

    greeting = state.tom.greet()

    if not topic or topic in ("", "tom", "baker", "tom baker"):
        state.tom.build_trust(5)
        return _response(
            greeting + "\n\nYou can ask Tom about: alibi, Eleanor (victim), Hargrove, Maggie.",
            state,
            hint="Try: 'ask Tom about alibi' or 'ask Tom about Eleanor'",
            event="time_advanced"
        )

    return handle_ask_tom(state, {**parsed, "topic": topic})


def handle_ask_tom(state: GameState, parsed: dict) -> dict:
    topic = (parsed.get("topic") or "").strip().lower()
    state.clock.advance()   # each conversation advances time

    # Build trust a little for every civil interaction
    state.tom.build_trust(8)

    response_text = state.tom.respond(topic)

    # If Tom revealed his alibi, register it as a clue
    if state.tom.alibi_revealed and "witness_msg" not in state.case.clues_found:
        state.case.add_clue("witness_msg")
        return _response(
            f"Tom Baker: {response_text}\n\n"
            "[Clue recorded: Tom Baker's alibi account]",
            state,
            event="clue_found"
        )

    return _response(f"Tom Baker: {response_text}", state, event="time_advanced")


def handle_collect_clue(state: GameState, parsed: dict) -> dict:
    clue_id = parsed.get("topic")
    if not clue_id:
        return _response("Pick up what, exactly?", state)

    result = state.case.add_clue(clue_id)
    if result:
        return _response(f"You pick it up carefully.\nClue added: {result}", state, event="clue_found")
    if clue_id in state.case.clues_found:
        return _response("You already have that.", state)
    return _response("You don't see that here.", state)


def handle_examine_clue(state: GameState, parsed: dict) -> dict:
    clue_id = parsed.get("topic")

    # Examining also collects the clue if it's at the scene
    result = state.case.add_clue(clue_id) if clue_id else None
    if result:
        return _response(f"You study it closely.\n{result}", state, event="clue_found")

    if clue_id in (state.case.clues_found or []):
        desc = state.case.ALL_CLUES.get(clue_id, "An interesting piece of evidence.")
        return _response(f"You re-examine it: {desc}", state)

    return _response("You don't have that clue yet, or it isn't here.", state)


def handle_solve(state: GameState, parsed: dict) -> dict:
    if state.case.status == "solved":
        return _response("The case is already closed. Well done, detective.", state)
    result = state.case.try_solve()
    return _response(result, state, event="solve_attempt")


def handle_case(state: GameState, parsed: dict) -> dict:
    return handle_status(state, parsed)


def handle_build_trust(state: GameState, parsed: dict) -> dict:
    state.tom.build_trust(15)
    state.tom.mood = "warmer"
    return _response(
        "You buy Tom a round. He accepts it with a gruff nod. "
        "He seems a little more willing to talk.",
        state,
        event="trust_built"
    )


def handle_unknown(state: GameState, parsed: dict) -> dict:
    raw = parsed.get("raw", "")
    return _response(
        f"You're not sure how to '{raw}'. Type 'help' for available commands.",
        state,
        hint="help"
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

HANDLERS = {
    "help":         handle_help,
    "status":       handle_status,
    "reset":        handle_reset,
    "wait":         handle_wait,
    "time":         handle_time,
    "go":           handle_go,
    "look":         handle_look,
    "talk_tom":     handle_talk_tom,
    "ask_tom":      handle_ask_tom,
    "collect_clue": handle_collect_clue,
    "examine_clue": handle_examine_clue,
    "solve":        handle_solve,
    "case":         handle_case,
    "build_trust":  handle_build_trust,
    "unknown":      handle_unknown,
}


def dispatch(raw_input: str) -> dict:
    from command_parser import parse
    parsed = parse(raw_input)
    STATE.command_count += 1
    handler = HANDLERS.get(parsed["action"], handle_unknown)
    return handler(STATE, parsed)
