"""
Command parser: maps player free-text input to structured game actions.
Returns a (action, topic, extra) triple.
"""

import re


def _normalize(text: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


# ---------------------------------------------------------------------------
# Rules — each entry: (pattern, action, fixed_topic)
#
# Group convention:
#   Group 1  — verb/trigger phrase (never used as topic)
#   Group 2  — optional free-text topic (extracted only when present)
#
# If fixed_topic is not None, it's used as-is; regex groups are ignored.
# If fixed_topic is None, we try group 2 for the topic (never group 1).
# ---------------------------------------------------------------------------

RULES = [
    # --- meta ---
    (r"\b(help|commands|what can i do)\b",           "help",   None),
    (r"\b(status|state|progress|inventory)\b",        "status", None),
    (r"\b(reset|restart|new game)\b",                 "reset",  None),

    # --- time ---
    (r"\b(wait|pass time|sleep|rest|advance time)\b", "wait",   None),
    (r"\b(time|clock|what time|when is it)\b",        "time",   None),

    # --- movement ---
    (r"\b(?:go to|travel to|visit|head to)\s+(.+)",  "go",  None),

    # --- look / examine (no topic = overview; topic = specific object) ---
    (r"\b(?:look around|look)\b\s*(.*)?",            "look", None),
    (r"\b(?:examine|inspect|search)\b\s*(.*)?",      "look", None),

    # --- NPC Tom Baker: SPECIFIC topics come before the generic talk rule ---
    (r"\btom\b.*\b(alibi|where were you|whereabouts)\b",     "ask_tom", "alibi"),
    (r"\btom\b.*\b(victim|eleanor|voss|dead woman)\b",        "ask_tom", "victim"),
    (r"\btom\b.*\b(hargrove|estate)\b",                       "ask_tom", "hargrove"),
    (r"\btom\b.*\b(maggie|barmaid)\b",                        "ask_tom", "maggie"),

    # generic "ask Tom about X" — topic is the phrase after "about"
    (r"\b(?:ask|question)\b.+tom.+\babout\s+(.+)",            "ask_tom", None),
    (r"\btom.+\babout\s+(.+)",                                "ask_tom", None),

    # generic "talk to Tom" (no specific topic)
    (r"\b(?:talk to|speak to|speak with|approach)\b.+tom\b",  "talk_tom", None),
    (r"\btalk\b.+tom\b",                                       "talk_tom", None),
    (r"\btom\b",                                               "talk_tom", None),

    # --- clues: collect ---
    (r"\b(?:pick up|grab|take|collect)\b.+\b(note|letter|paper)\b",  "collect_clue", "torn_note"),
    (r"\b(?:pick up|grab|take|collect)\b.+\b(ledger|book|record)\b", "collect_clue", "ledger"),
    (r"\b(?:pick up|grab|take|collect)\b.+\b(watch|pocket watch)\b", "collect_clue", "pocket_watch"),

    # --- clues: examine ---
    (r"\b(?:examine|look at|read|check)\b.+\b(note|letter|paper)\b",         "examine_clue", "torn_note"),
    (r"\b(?:examine|look at|read|check)\b.+\b(ledger|book|record)\b",        "examine_clue", "ledger"),
    (r"\b(?:examine|look at|read|check)\b.+\b(watch|pocket watch)\b",        "examine_clue", "pocket_watch"),
    (r"\b(?:examine|look at|follow|check)\b.+\b(footprint|mud|track)\b",     "examine_clue", "footprints"),
    (r"\b(?:open|check|search)\b.+\b(safe|east wing safe)\b",                "examine_clue", "ledger"),

    # --- case ---
    (r"\b(?:solve|close|conclude)\b.+\b(?:case|mystery|investigation)\b",    "solve",  None),
    (r"\b(?:case|investigation|mystery)\b",                                    "case",   None),

    # --- trust building ---
    (r"\b(?:compliment|buy.+drink|offer.+drink|be kind|be nice)\b",          "build_trust", None),
]


def parse(raw_input: str) -> dict:
    """
    Returns dict: {action, topic, raw}
    """
    norm = _normalize(raw_input)

    for pattern, action, fixed_topic in RULES:
        m = re.search(pattern, norm)
        if m:
            if fixed_topic is not None:
                # Rule provides the topic explicitly
                topic = fixed_topic
            else:
                # Try to extract topic from group 1 (our convention: group 1 IS the topic
                # for single-group patterns that capture the object, not the verb)
                topic = None
                if m.lastindex and m.lastindex >= 1:
                    raw_group = m.group(1)
                    if raw_group:
                        candidate = raw_group.strip()
                        # Discard if it looks like a verb/trigger phrase
                        verbs = {"help", "commands", "what can i do", "status", "state",
                                 "progress", "inventory", "reset", "restart", "new game",
                                 "wait", "pass time", "sleep", "rest", "advance time",
                                 "time", "clock", "what time", "when is it",
                                 "look around", "look", "examine", "inspect", "search",
                                 "pick up", "grab", "take", "collect",
                                 "read", "check", "follow", "open",
                                 "solve", "close", "conclude", "case", "investigation", "mystery"}
                        if candidate.lower() not in verbs:
                            topic = candidate or None

            return {"action": action, "topic": topic, "raw": raw_input}

    return {"action": "unknown", "topic": norm, "raw": raw_input}
