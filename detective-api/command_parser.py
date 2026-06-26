"""
Command parser — NPC-agnostic.

Instead of hardcoding NPC names in regex rules, the parser extracts a
raw `npc_hint` string and a `topic` string from the input. Handlers then
use npc.resolve_npc() against the live registry to find the target NPC.

Parsed result dict keys:
  action    str   — one of the action constants below
  npc_hint  str | None  — NPC name fragment typed by player
  topic     str | None  — subject of the question/action
  raw       str   — original unmodified input
"""

import re


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


# ---------------------------------------------------------------------------
# Talk/ask extraction helpers
# ---------------------------------------------------------------------------

# Patterns that signal "talk to <someone>"
_TALK_RE = re.compile(
    r"\b(?:talk to|speak to|speak with|approach|greet|chat with|meet)\s+(.+)", re.I
)

# Patterns that signal "ask <someone> about <topic>"
_ASK_RE = re.compile(
    r"\b(?:ask|question|interrogate)\s+(.+?)\s+about\s+(.+)", re.I
)

# "accuse <someone>" or "<someone> did it"
_ACCUSE_RE = re.compile(
    r"\b(?:accuse|blame|arrest|it was|suspect)\s+(.+)", re.I
)

# "compliment / be nice to / buy a drink for <someone>"
_NICE_RE = re.compile(
    r"\b(?:compliment|buy.*?drink.*?for|offer.*?drink.*?to|be kind to|be nice to)\s+(.+)", re.I
)

# Movement: "go to / visit / head to <place>"
_GO_RE = re.compile(
    r"\b(?:go to|travel to|visit|head to|walk to)\s+(.+)", re.I
)

# Clue collection: "pick up / grab / take <item>"
_COLLECT_RE = re.compile(
    r"\b(?:pick up|grab|take|collect)\s+(?:the\s+)?(.+)", re.I
)

# Clue examination: "examine / look at / read <item>"
_EXAMINE_RE = re.compile(
    r"\b(?:examine|look at|read|study|inspect)\s+(?:the\s+)?(.+)", re.I
)

# Known clue keywords → canonical clue IDs
_CLUE_MAP = {
    "note": "torn_note", "letter": "torn_note", "paper": "torn_note", "torn note": "torn_note",
    "ledger": "ledger", "book": "ledger", "record": "ledger", "account book": "ledger",
    "watch": "pocket_watch", "pocket watch": "pocket_watch", "gold watch": "pocket_watch",
    "footprint": "footprints", "footprints": "footprints", "mud": "footprints", "tracks": "footprints",
    "safe": "ledger",   # opening the safe yields the ledger
    "skiff": "unregistered_skiff", "boat": "unregistered_skiff", "vessel": "unregistered_skiff",
}


def _match_clue(text: str) -> str | None:
    t = text.lower().strip()
    for keyword, clue_id in _CLUE_MAP.items():
        if keyword in t:
            return clue_id
    return None



# ---------------------------------------------------------------------------
# Investigation command patterns
# ---------------------------------------------------------------------------

# "analyze <subject>" / "investigate <subject>" / "focus on <subject>"
_ANALYZE_RE = re.compile(
    r"\b(?:analyze|analyse|investigate|focus on|what do we know about)\s+(.+)", re.I
)

# "link <source_id> to <target_id>"
_LINK_RE = re.compile(
    r"\blink\s+(\S+)\s+to\s+(\S+)", re.I
)

# "contradictions [subject]" / "conflicts [subject]" / "inconsistencies [subject]"
_CONTRA_RE = re.compile(
    r"\b(?:contradictions?|conflicts?|inconsistenc(?:y|ies))\b(?:\s+(.+))?", re.I
)

# "profile <npc>" / "assess <npc>" / "evaluate <npc>"
_PROFILE_RE = re.compile(
    r"\b(?:profile|assess|evaluate|breakdown of|report on)\s+(.+)", re.I
)


def parse(raw_input: str) -> dict:
    norm = _normalize(raw_input)

    # --- meta ---
    if re.search(r"\b(help|commands|what can i do)\b", norm):
        return _r("help", raw=raw_input)
    if re.search(r"\b(status|state|progress|inventory|notebook)\b", norm):
        return _r("status", raw=raw_input)
    if re.search(r"\b(reset|restart|new game)\b", norm):
        return _r("reset", raw=raw_input)

    # --- scenario management ---
    m = re.search(r"\bscenario\s+(.*)", norm)
    if m:
        return _r("scenario", topic=m.group(1).strip(), raw=raw_input)

    # --- investigation reasoning ---
    if re.search(r"\b(overview|big picture|what matters|what do i know|summarize|summary)\b", norm):
        return _r("overview", raw=raw_input)

    m = _LINK_RE.search(norm)
    if m:
        return _r("link", topic=f"{m.group(1).strip()}|||{m.group(2).strip()}", raw=raw_input)

    m = _CONTRA_RE.search(norm)
    if m:
        subject = m.group(1).strip() if m.group(1) else None
        return _r("contradictions", topic=subject, raw=raw_input)

    m = _PROFILE_RE.search(norm)
    if m:
        return _r("profile", npc_hint=m.group(1).strip(), raw=raw_input)

    m = _ANALYZE_RE.search(norm)
    if m:
        return _r("analyze", topic=m.group(1).strip(), raw=raw_input)

    # Focus: "focus <subject>" / "focus on <subject>" / "unfocus" / "clear focus"
    if re.search(r"\b(unfocus|clear focus|remove focus|no focus)\b", norm):
        return _r("focus", topic=None, raw=raw_input)
    m = re.search(r"\b(?:focus on|focus)\s+(.+)", norm)
    if m:
        return _r("focus", topic=m.group(1).strip(), raw=raw_input)

    # --- time ---
    if re.search(r"\b(wait|pass time|sleep|rest|advance time)\b", norm):
        return _r("wait", raw=raw_input)
    if re.search(r"\b(time|clock|what time|when is it)\b", norm):
        return _r("time", raw=raw_input)

    # --- case ---
    if re.search(r"\b(?:solve|close|conclude)\b.+\b(?:case|mystery|investigation)\b", norm):
        return _r("solve", raw=raw_input)
    if re.search(r"\b(?:case|investigation|mystery)\b", norm):
        return _r("case", raw=raw_input)

    # --- look / survey ---
    if re.search(r"\b(?:look around|survey|overview|where am i)\b", norm):
        return _r("look", raw=raw_input)
    m = re.search(r"\b(?:look at|examine|inspect|search)\s+(?:the\s+)?(.+)", norm)
    if m:
        topic = m.group(1).strip()
        clue_id = _match_clue(topic)
        if clue_id:
            return _r("examine_clue", topic=clue_id, raw=raw_input)
        return _r("look", topic=topic, raw=raw_input)

    # --- movement ---
    m = _GO_RE.search(norm)
    if m:
        return _r("go", topic=m.group(1).strip(), raw=raw_input)

    # --- clue collection ---
    m = _COLLECT_RE.search(norm)
    if m:
        clue_id = _match_clue(m.group(1))
        if clue_id:
            return _r("collect_clue", topic=clue_id, raw=raw_input)

    # --- clue examination ---
    m = _EXAMINE_RE.search(norm)
    if m:
        clue_id = _match_clue(m.group(1))
        if clue_id:
            return _r("examine_clue", topic=clue_id, raw=raw_input)

    # --- NPC: accusation ---
    m = _ACCUSE_RE.search(norm)
    if m:
        return _r("accuse", npc_hint=m.group(1).strip(), raw=raw_input)

    # --- NPC: compliment / build rapport ---
    m = _NICE_RE.search(norm)
    if m:
        return _r("build_rapport", npc_hint=m.group(1).strip(), raw=raw_input)
    # bare "buy a drink" or "be kind" without a name
    if re.search(r"\b(?:buy.+drink|offer.+drink|be kind|be nice|compliment)\b", norm):
        return _r("build_rapport", raw=raw_input)

    # --- NPC: ask <name> about <topic> ---
    m = _ASK_RE.search(norm)
    if m:
        return _r("ask", npc_hint=m.group(1).strip(), topic=m.group(2).strip(), raw=raw_input)

    # --- NPC: talk to <name> ---
    m = _TALK_RE.search(norm)
    if m:
        return _r("talk", npc_hint=m.group(1).strip(), raw=raw_input)

    # --- bare NPC name typed alone or with extra words ---
    # e.g. "Tom" / "find Petra" / "where is Nour"
    _BARE_NAME_RE = re.compile(
        r"\b(tom(?: baker)?|baker|petra(?: vance)?|vance|nour(?: saleh)?|saleh"
        r"|marina(?: manager)?|cafe(?: owner)?|barista)\b", re.I
    )
    m = _BARE_NAME_RE.search(norm)
    if m:
        return _r("talk", npc_hint=m.group(0).strip(), raw=raw_input)

    return _r("unknown", raw=raw_input)


def _r(action: str, *, npc_hint: str = None, topic: str = None, raw: str = "") -> dict:
    return {"action": action, "npc_hint": npc_hint, "topic": topic, "raw": raw}
