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


# ---------------------------------------------------------------------------
# Subject resolution — maps player-typed names to canonical subject_ids
# ---------------------------------------------------------------------------

SUBJECT_MAP: dict = {
    "tom": "tom_baker", "baker": "tom_baker", "tom baker": "tom_baker",
    "petra": "marina_manager", "vance": "marina_manager", "marina manager": "marina_manager",
    "nour": "cafe_owner", "saleh": "cafe_owner", "nour saleh": "cafe_owner",
    "hargrove": "hargrove", "reginald": "hargrove", "reginald hargrove": "hargrove",
    "eleanor": "eleanor", "eleanor voss": "eleanor", "voss": "eleanor",
    "marina": "marina",
    "manor": "hargrove",
    "ledger": "ledger",
    "watch": "hargrove", "pocket watch": "hargrove",
    "boat": "marina", "skiff": "marina",
    "letters": "hargrove",
}


def _resolve_subject(hint: Optional[str]) -> Optional[str]:
    if not hint:
        return None
    key = hint.lower().strip()
    # Exact lookup first
    if key in SUBJECT_MAP:
        return SUBJECT_MAP[key]
    # Partial match
    for k, v in SUBJECT_MAP.items():
        if k in key or key in k:
            return v
    return key   # pass through as-is (may match subject_ids directly)


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
        "Investigation reasoning:\n"
        "  overview                       — high-level digest of top evidence\n"
        "  focus <subject>                — lock investigation emphasis on subject\n"
        "  analyze <subject>              — all evidence about a subject\n"
        "  contradictions [subject]       — list detected conflicts\n"
        "  profile <NPC name>             — full epistemic breakdown of an NPC\n"
        "  link <evidence_id> to <id>     — connect two pieces of evidence\n\n"
        "Scenarios:\n"
        "  scenario list                  — list available investigations\n"
        "  scenario load <id>             — load a different scenario\n\n"
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
    state.board.record_interaction(npc.id, state.command_count)

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

    # Record interaction for salience recency — both NPC and any topic-matching rumors
    state.board.record_interaction(npc.id, state.command_count)
    topic_lower = topic.lower()
    for r in state.rumors:
        if topic_lower in r.content.lower() or any(topic_lower in s for s in r.subjects):
            state.board.record_interaction(r.id, state.command_count)

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
# Investigation reasoning handlers
# ---------------------------------------------------------------------------

def handle_analyze(state: GameState, parsed: dict) -> dict:
    """Aggregate all evidence (truths, rumors, beliefs, contradictions) for a subject."""
    subject_key = _resolve_subject(parsed.get("topic"))
    if not subject_key:
        return _response(
            "Analyze what? Try: 'analyze tom', 'analyze hargrove', 'analyze eleanor'.",
            state,
        )

    data = state.board.analyze_subject(
        subject_key, state.truth_events, state.rumors, state.npcs
    )

    # Format truths
    truth_lines = [f"  [TRUTH] {t['description'][:90]}" for t in data["confirmed_truths"]]
    truth_section = "\n".join(truth_lines) or "  none on record"

    # Format active rumors
    rumor_lines = [
        f"  [RUMOR cred:{r['credibility']:3d}] {r['content'][:80]}"
        for r in data["active_rumors"]
    ]
    rumor_section = "\n".join(rumor_lines) or "  none circulating"

    # Format contradictions
    contra_lines = [
        f"  [CONFLICT sev:{c['severity']}] {c['description']}"
        for c in data["contradictions"]
    ]
    contra_section = "\n".join(contra_lines) or "  none detected"

    # Format NPC beliefs
    belief_lines = []
    for npc_name, beliefs in data["npc_beliefs"].items():
        for b in beliefs:
            belief_lines.append(f"  {npc_name} [{b['confidence']}%]: {b['statement'][:75]}")
    belief_section = "\n".join(belief_lines) or "  no NPC beliefs formed yet"

    # Format manual links
    link_lines = [f"  {l['from']} → {l['to']} ({l['reasoning'][:50]})" for l in data["manual_links"]]
    link_section = "\n".join(link_lines) if link_lines else "  none"

    label = subject_key.replace("_", " ").title()
    msg = (
        f"=== Analysis: {label} ===\n\n"
        f"Confirmed Truths:\n{truth_section}\n\n"
        f"Active Rumors:\n{rumor_section}\n\n"
        f"Contradictions:\n{contra_section}\n\n"
        f"NPC Beliefs:\n{belief_section}\n\n"
        f"Linked Evidence:\n{link_section}"
    )
    return _response(msg, state)


def handle_contradictions(state: GameState, parsed: dict) -> dict:
    """List all detected contradictions, optionally filtered by subject."""
    subject_raw = parsed.get("topic")
    subject_key = _resolve_subject(subject_raw) if subject_raw else None

    contras = state.board.get_contradictions_for(subject_key)
    if not contras:
        scope = f" involving {subject_key.replace('_', ' ')}" if subject_key else ""
        return _response(
            f"No contradictions detected{scope} yet. Keep gathering evidence.",
            state,
        )

    sorted_c = sorted(contras, key=lambda c: c.severity, reverse=True)
    lines = []
    SEV_LABEL = {3: "MAJOR", 2: "NOTABLE", 1: "MINOR"}
    for c in sorted_c:
        lines.append(
            f"  [{SEV_LABEL.get(c.severity, '?')}] {c.description}\n"
            f"    A: {c.source_a_excerpt[:70]}\n"
            f"    B: {c.source_b_excerpt[:70]}"
        )

    scope = f" about {subject_key.replace('_', ' ')}" if subject_key else ""
    msg = f"=== Contradictions{scope} ({len(contras)}) ===\n\n" + "\n\n".join(lines)
    return _response(msg, state)


def handle_profile(state: GameState, parsed: dict) -> dict:
    """Full epistemic breakdown of one NPC."""
    npc = resolve_npc(parsed.get("npc_hint"), state.npcs)
    if not npc:
        return _npc_not_found(parsed.get("npc_hint"), state)

    prof = state.board.npc_profile(npc, state.truth_events, state.rumors)

    # Axes
    axes = prof["axes"]
    axes_line = f"mood:{axes['mood']}  stress:{axes['stress']}  suspicion:{axes['suspicion']}"

    # Beliefs
    bsummary = prof["belief_summary"]
    aligned_lines = [
        f"  [ALIGNED {b['confidence']:3d}%] {b['statement'][:80]}"
        for b in prof["beliefs_aligned_with_truth"]
    ] or ["  none yet"]
    other_lines = [
        f"  [UNVERIFIED {b['confidence']:3d}%] {b['statement'][:80]}"
        for b in prof["beliefs_not_in_truth"]
    ] or ["  none"]

    # Rumor exposure
    rumor_lines = [
        f"  cred:{r['credibility']:3d} distort:{r['distortion_level']:2d}% — {r['content'][:70]}"
        for r in prof["active_rumor_exposure"]
    ] or ["  not exposed to active rumors"]

    # --- Daily life section ---
    occ = getattr(npc, "occupation", None)
    occ_line = (
        f"{occ.title} @ {occ.employer} | income: {occ.income_level} | status: {occ.social_status}"
        if occ else "Unknown"
    )

    goals = getattr(npc, "goals", [])
    goal_lines = [
        f"  [{g.urgency_label()} {g.urgency:3d}] {g.label}  ({g.category})"
        for g in goals if g.active
    ] or ["  none on record"]

    schedule = getattr(npc, "schedule", None)
    sched_line = ""
    if schedule:
        sched_line = (
            f"\nSchedule: morning→{', '.join(schedule.morning) or '—'}"
            f"  afternoon→{', '.join(schedule.afternoon) or '—'}"
            f"  evening→{', '.join(schedule.evening) or '—'}"
            f"  night→{', '.join(schedule.night) or '—'}"
        )

    rels = getattr(npc, "relationships", [])
    rel_lines = [
        f"  {r.kind.capitalize()} with {r.target_name} (strength: {r.strength})"
        + (f" — {r.note}" if r.note else "")
        for r in rels
    ] or ["  none recorded"]

    recent_actions = getattr(npc, "daily_log", [])[-5:]
    activity_lines = [
        f"  {a.action_type.upper()} at {a.location}"
        + (f" with {a.target_name}" if a.target_name else "")
        + (f"  ({a.game_time})" if a.game_time else "")
        + ("  [goal-driven]" if a.goal_driven else "")
        for a in recent_actions
    ] or ["  no activity recorded yet"]

    msg = (
        f"=== Profile: {prof['name']} ===\n"
        f"Role: {prof['role']}\n"
        f"Location: {npc.location}\n"
        f"Occupation: {occ_line}"
        f"{sched_line}\n\n"
        f"Personal Goals:\n" + "\n".join(goal_lines) + "\n\n"
        f"Relationships:\n" + "\n".join(rel_lines) + "\n\n"
        f"Recent Activities:\n" + "\n".join(activity_lines) + "\n\n"
        f"── Investigation Data ──────────────────────────\n"
        f"State: {axes_line}\n"
        f"Reliability score: {prof['reliability_score']}/100\n"
        f"Knowledge shared: {prof['knowledge_revealed']}/{prof['knowledge_total']}\n\n"
        f"Beliefs ({bsummary['strong_count']}s / {bsummary['moderate_count']}m / {bsummary['weak_count']}w total):\n"
        f"  Truth-aligned:\n" + "\n".join(f"  {l}" for l in aligned_lines) + "\n"
        f"  Unverified:\n" + "\n".join(f"  {l}" for l in other_lines) + "\n\n"
        f"Active rumor exposure:\n" + "\n".join(rumor_lines)
    )
    return _response(msg, state, hint=f"Try: 'analyze {npc.name.split()[0].lower()}'")


def handle_link(state: GameState, parsed: dict) -> dict:
    """
    Manually link two evidence items.
    Parser encodes both IDs as "source_id|||target_id" in parsed["topic"].
    """
    raw_topic = parsed.get("topic", "")
    parts = raw_topic.split("|||")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return _response(
            "Usage: link <source_id> to <target_id>\n"
            "Example: link acced210 to truth_tom_pub",
            state,
        )

    src_id = parts[0].strip()
    tgt_id = parts[1].strip()

    # Determine types by looking them up in the evidence pool
    def _type_of(eid: str) -> str:
        if any(t.id == eid for t in state.truth_events):
            return "truth"
        if any(r.id == eid for r in state.rumors):
            return "rumor"
        return "unknown"

    src_type = _type_of(src_id)
    tgt_type = _type_of(tgt_id)

    if src_type == "unknown" or tgt_type == "unknown":
        unknown = src_id if src_type == "unknown" else tgt_id
        return _response(
            f"Evidence ID not found: '{unknown}'. "
            "Check rumor IDs in /state active_rumors or truth IDs starting with 'truth_'.",
            state,
        )

    link = state.board.add_link(
        src_type, src_id,
        tgt_type, tgt_id,
        reasoning="Player-established connection",
        game_time=state.clock.description(),
    )
    return _response(
        f"Link recorded: [{src_type}:{src_id}] → [{tgt_type}:{tgt_id}]\n"
        f"Link ID: {link.id}\n"
        "This connection will be included in future analysis.",
        state,
        event="link_created",
    )


# ---------------------------------------------------------------------------
# Scenario management
# ---------------------------------------------------------------------------

def handle_scenario(state: GameState, parsed: dict) -> dict:
    import scenarios as _sc

    topic = (parsed.get("topic") or "").strip().lower()

    # "scenario list" — show all available scenarios
    if not topic or topic == "list":
        lines = ["Available scenarios:", ""]
        for s in _sc.SCENARIOS.values():
            marker = " ◀ active" if s.id == getattr(state, "scenario_id", "hargrove_affair") else ""
            lines.append(f"  {s.id}{marker}")
            lines.append(f"    {s.name}")
            lines.append(f"    {s.description[:120]}{'…' if len(s.description) > 120 else ''}")
            lines.append("")
        lines.append("Usage: scenario load <id>")
        lines.append("       scenario load harbor_fuel")
        return _response("\n".join(lines), state)

    # "scenario load <name>"
    if topic.startswith("load "):
        name = topic[5:].strip()
    else:
        # allow "scenario harbor_fuel" as shorthand
        name = topic

    scenario = _sc.resolve_scenario(name)
    if not scenario:
        known = ", ".join(s.name for s in _sc.SCENARIOS.values())
        return _response(
            f"Unknown scenario '{name}'. Available: {known}",
            state,
            hint="Use 'scenario list' to see available scenarios.",
        )

    # Mutate the existing state object in-place.
    # app.py holds a direct reference to this object (from game_state import STATE),
    # so in-place mutation is the only way to make /state reflect the change.
    state.load_from_scenario(scenario)

    return _response(
        f"Scenario loaded: {scenario.name}\n\n"
        f"{scenario.description}\n\n"
        f"Case: {state.case.title}\n"
        f"NPCs: {', '.join(npc.name for npc in state.npcs.values())}\n"
        f"Starting truths: {len(state.truth_events)}\n"
        f"Starting rumors: {len(state.rumors)}\n\n"
        "All investigation systems reset. Type 'help' to begin.",
        state,
        event="scenario_loaded",
    )


# ---------------------------------------------------------------------------
# Focus + Overview
# ---------------------------------------------------------------------------

def handle_focus(state: GameState, parsed: dict) -> dict:
    topic = (parsed.get("topic") or "").strip()

    # "unfocus" / "clear focus" → topic will be None or empty
    if not topic:
        if state.board.focus_subject:
            old = state.board.focus_subject
            state.board.clear_focus(state.clock.description())
            return _response(
                f"Investigation focus on '{old.replace('_', ' ')}' cleared.\n"
                "All evidence is now weighted equally.",
                state, event="focus_cleared",
            )
        return _response(
            "No active focus. Use 'focus <subject>' to lock investigation emphasis.\n"
            "Examples: 'focus tom', 'focus hargrove', 'focus eleanor', 'focus marina'",
            state,
        )

    subject_key = _resolve_subject(topic)
    if not subject_key:
        # Fall back to topic as-is (allows focusing on any free-form subject)
        subject_key = topic.lower().replace(" ", "_")

    state.board.set_focus(subject_key, state.clock.description())
    return _response(
        f"Investigation focus locked: {subject_key.replace('_', ' ').title()}\n"
        "Related entities will rise in salience. Use 'overview' to see prioritised evidence.\n"
        "Use 'unfocus' to release.",
        state, event="focus_set",
    )


def handle_overview(state: GameState, parsed: dict) -> dict:
    ov = state.board.overview(
        state.truth_events, state.rumors, state.npcs, state.command_count
    )

    lines = ["=== Investigation Overview ===", ""]

    if ov["focus"]:
        lines.append(f"Active Focus: {ov['focus'].replace('_', ' ').title()}")
        lines.append("")

    # Top hypotheses
    lines.append("Top Hypotheses:")
    if ov["top_hypotheses"]:
        for h in ov["top_hypotheses"]:
            lines.append(
                f"  [{h['confidence']}% conf | salience {h['salience']}] "
                f"{h['statement']} "
                f"({h['supporting_count']} supporting, {h['contradicting_count']} contradicting)"
            )
    else:
        lines.append("  None yet — gather more evidence.")
    lines.append("")

    # Top contradictions
    lines.append("Key Contradictions:")
    if ov["top_contradictions"]:
        for c in ov["top_contradictions"]:
            lines.append(
                f"  [sev:{c['severity']} | salience {c['salience']}] {c['description']}"
            )
    else:
        lines.append("  No contradictions detected yet.")
    lines.append("")

    # Unstable beliefs
    lines.append("Most Uncertain NPCs:")
    if ov["most_unstable_beliefs"]:
        for item in ov["most_unstable_beliefs"]:
            pct = int(item["instability"] * 100)
            lines.append(
                f"  {item['npc']}: {pct}% weak beliefs across {item['belief_count']} total"
            )
    else:
        lines.append("  Insufficient belief data.")
    lines.append("")

    # Reliable sources
    lines.append("Most Reliable Sources:")
    if ov["most_reliable_sources"]:
        for src in ov["most_reliable_sources"]:
            lines.append(
                f"  {src['npc']}: {src['reliability']}% truth-aligned "
                f"({src['aligned']}/{src['belief_count']} beliefs)"
            )
    else:
        lines.append("  No reliability data yet.")

    return _response("\n".join(lines), state)


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
    "analyze":        handle_analyze,
    "contradictions": handle_contradictions,
    "profile":        handle_profile,
    "link":           handle_link,
    "focus":          handle_focus,
    "overview":       handle_overview,
    "scenario":       handle_scenario,
    "unknown":        handle_unknown,
}


def dispatch(raw_input: str) -> dict:
    import social_sim
    from command_parser import parse
    parsed = parse(raw_input)
    STATE.command_count += 1
    handler = HANDLERS.get(parsed["action"], handle_unknown)
    result = handler(STATE, parsed)

    # Compute salience before tick so social_sim can weight propagation
    salience_map = STATE.board.compute_salience(
        STATE.truth_events, STATE.rumors, STATE.npcs, STATE.command_count
    )

    # Run background social tick — NPCs gossip, rumors decay, beliefs update
    updated_rumors, tick_logs = social_sim.tick(
        npcs=STATE.npcs,
        all_rumors=STATE.rumors,
        game_time=STATE.clock.description(),
        day=STATE.clock.day,
        salience_map=salience_map,
    )
    STATE.rumors = updated_rumors
    if tick_logs:
        STATE.social_log.extend(tick_logs)
        STATE.social_log = STATE.social_log[-50:]   # bounded ring buffer

    # Sync investigation board — scan for new contradictions, rebuild hypotheses
    STATE.board.sync(STATE.truth_events, STATE.rumors, STATE.clock.description())

    return result
