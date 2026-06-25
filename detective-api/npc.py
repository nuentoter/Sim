"""
Generic NPC simulation engine.

Each NPC carries three continuous state axes:
  mood       0–100  (0 = devastated/hostile, 100 = elated/warm)
  stress     0–100  (0 = perfectly calm,     100 = panicking)
  suspicion  0–100  (0 = fully trusting,     100 = deeply suspicious of player)

Responses are assembled from tone modifiers derived from those axes plus
KnowledgeItems that encode what each NPC knows and under what conditions
they will share it.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

@dataclass
class MemoryEvent:
    event_type: str   # greeted | questioned | accused | revealed | player_hostile | complimented
    description: str
    game_time: str
    weight: int = 1   # higher = more salient; future use for prioritised recall

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "description": self.description,
            "game_time": self.game_time,
            "weight": self.weight,
        }


# ---------------------------------------------------------------------------
# Knowledge items
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeItem:
    """A piece of information an NPC holds and may share."""
    topic_keys: list       # keywords that trigger this item
    content: str           # what the NPC says when they share it
    # Reveal thresholds — all must pass for the NPC to share freely
    suspicion_max: int = 65   # won't share if suspicion above this
    mood_min: int = 20        # won't share if mood below this
    stress_max: int = 80      # won't share if stress above this
    revealed: bool = False    # has been shared at least once
    # Optional clue to register in the Case when revealed
    case_clue_id: Optional[str] = None

    def matches(self, topic: str) -> bool:
        t = topic.lower()
        return any(k in t for k in self.topic_keys)

    def can_reveal(self, npc: "NPC") -> bool:
        return (
            npc.suspicion <= self.suspicion_max
            and npc.mood >= self.mood_min
            and npc.stress <= self.stress_max
        )


# ---------------------------------------------------------------------------
# Tone modifiers — derive the "voice" of an NPC from their current state
# ---------------------------------------------------------------------------

def _mood_tone(mood: int) -> str:
    if mood >= 65:
        return "warm"
    if mood >= 35:
        return "neutral"
    return "cold"


def _stress_tone(stress: int) -> str:
    if stress >= 70:
        return "frantic"
    if stress >= 40:
        return "tense"
    return "calm"


def _suspicion_tone(suspicion: int) -> str:
    if suspicion >= 65:
        return "guarded"
    if suspicion >= 35:
        return "cautious"
    return "open"


# Tone → prefix snippets injected before knowledge content
_MOOD_PREFIX = {
    "warm":    ["Relaxing slightly, {name} says,", "{name} leans in with a faint smile.", "\"Sure, I can tell you that.\""],
    "neutral": ["{name} considers for a moment.", "{name} shrugs.", ""],
    "cold":    ["{name} glares at you.", "\"What do you want?\" {name} mutters.", "{name} turns away slightly."],
}

_STRESS_PREFIX = {
    "frantic": ["With a trembling voice,", "Glancing around nervously,", "Their words come in a rush —"],
    "tense":   ["After a pause,", "Keeping their voice low,", ""],
    "calm":    ["", "", ""],
}

_SUSPICION_PREFIX = {
    "guarded": ["\"Why do you want to know that?\"", "\"I'm not sure I should say...\"", "\"Keep this between us.\""],
    "cautious": ["\"I suppose I can tell you.\"", "\"Don't go spreading this around.\"", ""],
    "open":     ["", "", ""],
}

# Refusal lines bucketed by (suspicion_tone, mood_tone)
_REFUSAL_LINES = {
    ("guarded", "cold"):    "\"Get away from me. I'm not answering that.\"",
    ("guarded", "neutral"): "\"That's none of your business.\"",
    ("guarded", "warm"):    "\"Look, I like you, but I'm not ready to talk about that.\"",
    ("cautious", "cold"):   "\"I'd rather not get into it.\"",
    ("cautious", "neutral"): "\"Not something I want to discuss right now.\"",
    ("cautious", "warm"):   "\"Maybe later. Not the right time.\"",
    ("open", "cold"):       "\"I don't know anything about that.\"",
    ("open", "neutral"):    "\"Sorry, can't help you there.\"",
    ("open", "warm"):       "\"Wish I could help, but I really don't know.\"",
}

_GREETING_LINES = {
    ("warm", "calm", "open"):     "waves you over with a genuine smile. \"Good to see you. What can I do for you?\"",
    ("warm", "calm", "cautious"): "nods cautiously but warmly. \"Detective. What brings you here?\"",
    ("warm", "calm", "guarded"):  "watches you carefully despite a polite expression. \"Yes?\"",
    ("warm", "tense", "open"):    "manages a smile, though something is clearly on their mind. \"What is it?\"",
    ("warm", "tense", "cautious"):"glances around before addressing you. \"Yes, detective?\"",
    ("warm", "frantic", "open"):  "looks flustered. \"I barely have a moment — what do you need?\"",
    ("neutral", "calm", "open"):  "acknowledges you with a nod. \"Detective.\"",
    ("neutral", "calm", "cautious"): "eyes you carefully. \"What do you want?\"",
    ("neutral", "calm", "guarded"):  "folds their arms. \"I wondered when you'd show up.\"",
    ("neutral", "tense", "open"):  "looks distracted but turns to you. \"Yes?\"",
    ("neutral", "tense", "cautious"): "glances up with an unreadable expression. \"Make it quick.\"",
    ("neutral", "frantic", "open"): "speaks quickly. \"Not a great time, but go ahead.\"",
    ("cold", "calm", "open"):     "barely looks up. \"What.\"",
    ("cold", "calm", "cautious"): "stiffens as you approach. \"What do you want now?\"",
    ("cold", "calm", "guarded"):  "turns away slightly. \"I have nothing to say to you.\"",
    ("cold", "tense", "open"):    "snaps. \"What do you want?\"",
    ("cold", "tense", "guarded"): "\"Go away.\"",
    ("cold", "frantic", "open"):  "\"I can't deal with this right now.\"",
}


def _get_greeting(npc: "NPC") -> str:
    key = (_mood_tone(npc.mood), _stress_tone(npc.stress), _suspicion_tone(npc.suspicion))
    line = _GREETING_LINES.get(key)
    if line is None:
        # Fallback: walk down to simpler key
        line = _GREETING_LINES.get((_mood_tone(npc.mood), "calm", _suspicion_tone(npc.suspicion)),
               _GREETING_LINES.get((_mood_tone(npc.mood), "calm", "open"), "looks up at you."))
    return f"{npc.name} {line}"


def _build_reveal(npc: "NPC", item: KnowledgeItem) -> str:
    import random
    mt = _mood_tone(npc.mood)
    st = _stress_tone(npc.stress)
    su = _suspicion_tone(npc.suspicion)

    parts = []
    sp = random.choice(_SUSPICION_PREFIX[su]).format(name=npc.name)
    if sp:
        parts.append(sp)
    tp = random.choice(_STRESS_PREFIX[st]).format(name=npc.name)
    if tp:
        parts.append(tp)
    mp = random.choice(_MOOD_PREFIX[mt]).format(name=npc.name)
    if mp:
        parts.append(mp)

    prefix = " ".join(parts).strip()
    content = item.content
    return f"{prefix} {content}".strip() if prefix else content


def _build_refusal(npc: "NPC") -> str:
    mt = _mood_tone(npc.mood)
    su = _suspicion_tone(npc.suspicion)
    key = (su, mt)
    return _REFUSAL_LINES.get(key, "\"I can't help you with that.\"")


# ---------------------------------------------------------------------------
# NPC class
# ---------------------------------------------------------------------------

@dataclass
class NPC:
    id: str                     # registry key e.g. "tom_baker"
    name: str
    location: str
    role: str                   # human-readable role description
    mood: int = 50
    stress: int = 30
    suspicion: int = 0
    memory: list = field(default_factory=list)        # list[MemoryEvent]
    knowledge: list = field(default_factory=list)     # list[KnowledgeItem]
    heard_rumors: list = field(default_factory=list)  # list[Rumor] received via social sim

    # --- Memory helpers ---

    def remember(self, event_type: str, description: str, game_time: str, weight: int = 1):
        self.memory.append(MemoryEvent(event_type, description, game_time, weight))
        # Keep memory bounded; retain highest-weight events when trimming
        if len(self.memory) > 50:
            self.memory.sort(key=lambda e: e.weight, reverse=True)
            self.memory = self.memory[:50]

    def recent_memory(self, n: int = 5) -> list:
        return self.memory[-n:]

    def was_accused(self) -> bool:
        return any(e.event_type == "accused" for e in self.memory)

    def times_questioned(self) -> int:
        return sum(1 for e in self.memory if e.event_type == "questioned")

    # --- State mutations ---

    def shift_mood(self, delta: int):
        self.mood = max(0, min(100, self.mood + delta))

    def shift_stress(self, delta: int):
        self.stress = max(0, min(100, self.stress + delta))

    def shift_suspicion(self, delta: int):
        self.suspicion = max(0, min(100, self.suspicion + delta))

    # --- Dialogue engine ---

    def greet(self, game_time: str) -> str:
        self.remember("greeted", f"Player approached {self.name}", game_time)
        # Being greeted raises suspicion slightly each repeated time
        if self.times_questioned() > 2:
            self.shift_suspicion(3)
        return _get_greeting(self)

    def respond_to_topic(self, topic: str, game_time: str) -> tuple:
        """
        Returns (response_text: str, clue_id: str | None).
        Logs the interaction to memory and adjusts NPC state.
        """
        self.remember("questioned", f"Player asked about '{topic}'", game_time)
        self.shift_stress(4)        # being questioned is stressful
        self.shift_suspicion(2)     # each question raises suspicion slightly

        # Search knowledge base
        for item in self.knowledge:
            if item.matches(topic):
                if item.can_reveal(self):
                    text = _build_reveal(self, item)
                    clue_id = None
                    if not item.revealed:
                        item.revealed = True
                        clue_id = item.case_clue_id
                        self.remember("revealed", f"Revealed knowledge about '{topic}'", game_time, weight=3)
                        self.shift_mood(-5)   # sharing secrets is draining
                    else:
                        text += " (You've heard this before.)"
                    return text, clue_id
                else:
                    # NPC knows but won't say
                    self.shift_suspicion(5)
                    return _build_refusal(self), None

        # NPC has no relevant knowledge
        return _build_refusal(self), None

    def receive_accusation(self, game_time: str) -> str:
        self.remember("accused", "Player accused them", game_time, weight=5)
        self.shift_suspicion(25)
        self.shift_stress(20)
        self.shift_mood(-20)
        if self.suspicion >= 65:
            return f"{self.name} recoils. \"How DARE you accuse me! Get out of my sight!\""
        return f"{self.name} goes pale. \"Are you seriously suggesting I had something to do with this?\""

    def receive_compliment(self, game_time: str) -> str:
        self.remember("complimented", "Player was kind / bought a drink", game_time, weight=2)
        self.shift_mood(12)
        self.shift_suspicion(-8)
        self.shift_stress(-5)
        return f"{self.name} seems to relax a little. \"Thanks. I appreciate that.\""

    # --- Serialisation ---

    def status(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "role": self.role,
            "mood": self.mood,
            "stress": self.stress,
            "suspicion": self.suspicion,
            "memory_count": len(self.memory),
            "recent_memory": [e.to_dict() for e in self.recent_memory(3)],
            "knowledge_revealed": sum(1 for k in self.knowledge if k.revealed),
            "knowledge_total": len(self.knowledge),
            "heard_rumors_count": len(self.heard_rumors),
            "heard_rumors": [
                {"content": r.content, "credibility": r.credibility,
                 "distortion_level": r.distortion_level, "source": r.source_npc_id}
                for r in self.heard_rumors[-3:]
            ],
        }


# ---------------------------------------------------------------------------
# NPC factory — define all starting NPCs here
# ---------------------------------------------------------------------------

def build_npc_registry() -> dict:
    """Returns {npc_id: NPC} for all NPCs in the simulation."""

    # --- Tom Baker ---
    tom = NPC(
        id="tom_baker",
        name="Tom Baker",
        location="The Rusty Anchor pub",
        role="Pub regular, occasional odd-jobber",
        mood=35,
        stress=55,
        suspicion=20,
    )
    tom.knowledge = [
        KnowledgeItem(
            topic_keys=["alibi", "where were you", "whereabouts", "night of"],
            content=(
                "\"I was here all night,\" he says at last. "
                "\"Maggie the barmaid can vouch for me. I never left the pub.\""
            ),
            suspicion_max=60,
            mood_min=25,
            stress_max=85,
            case_clue_id="witness_msg",
        ),
        KnowledgeItem(
            topic_keys=["eleanor", "victim", "voss", "dead woman", "murdered"],
            content=(
                "He lowers his voice. "
                "\"Eleanor was skimming money from the Hargrove estate — "
                "I saw the ledger myself once. Check the east wing safe.\""
            ),
            suspicion_max=50,
            mood_min=30,
            stress_max=75,
            case_clue_id=None,
        ),
        KnowledgeItem(
            topic_keys=["hargrove", "manor", "estate", "reginald"],
            content=(
                "\"The Hargroves run this town. "
                "Poking around there is dangerous, detective. Be careful.\""
            ),
            suspicion_max=70,
            mood_min=20,
            stress_max=90,
        ),
        KnowledgeItem(
            topic_keys=["maggie", "barmaid", "bar"],
            content=(
                "\"Maggie works most nights. She'll confirm I didn't leave the pub. "
                "Good woman.\""
            ),
            suspicion_max=80,
            mood_min=15,
            stress_max=90,
        ),
    ]

    # --- Marina Manager ---
    marina = NPC(
        id="marina_manager",
        name="Petra Vance",
        location="The Island Marina",
        role="Marina manager",
        mood=55,
        stress=30,
        suspicion=5,
    )
    marina.knowledge = [
        KnowledgeItem(
            topic_keys=["boat", "vessel", "night crossing", "sea", "harbour", "harbor"],
            content=(
                "\"There was an unregistered skiff that went out the night Eleanor died. "
                "Around midnight. I logged it but didn't report it — I should have.\""
            ),
            suspicion_max=70,
            mood_min=30,
            stress_max=80,
            case_clue_id="unregistered_skiff",
        ),
        KnowledgeItem(
            topic_keys=["hargrove", "reginald", "estate owner"],
            content=(
                "\"Reginald Hargrove keeps a private mooring at the far end. "
                "He was very particular about who got near it.\""
            ),
            suspicion_max=75,
            mood_min=25,
            stress_max=85,
        ),
        KnowledgeItem(
            topic_keys=["eleanor", "voss", "victim"],
            content=(
                "\"I saw Eleanor at the marina two days before she died. "
                "She was arguing with someone — couldn't make out who.\""
            ),
            suspicion_max=65,
            mood_min=35,
            stress_max=80,
        ),
    ]

    # --- Cafe Owner ---
    cafe = NPC(
        id="cafe_owner",
        name="Nour Saleh",
        location="The Harbour Cafe",
        role="Cafe owner, town gossip hub",
        mood=65,
        stress=20,
        suspicion=5,
    )
    cafe.knowledge = [
        KnowledgeItem(
            topic_keys=["gossip", "rumour", "rumor", "town", "island", "people"],
            content=(
                "\"Everyone's been on edge since the murder. "
                "The Hargroves used to have friends everywhere — now even their closest allies "
                "are keeping their distance.\""
            ),
            suspicion_max=90,
            mood_min=10,
            stress_max=90,
        ),
        KnowledgeItem(
            topic_keys=["eleanor", "voss", "victim", "murdered woman"],
            content=(
                "\"Eleanor came in every Thursday morning. "
                "Last Thursday she seemed frightened — kept watching the door. "
                "Left half her coffee.\""
            ),
            suspicion_max=80,
            mood_min=20,
            stress_max=85,
        ),
        KnowledgeItem(
            topic_keys=["note", "letter", "message", "midnight"],
            content=(
                "\"I overheard Eleanor mention a letter once — she said it was a summons, "
                "not an invitation. I didn't ask more.\""
            ),
            suspicion_max=60,
            mood_min=40,
            stress_max=75,
            case_clue_id="torn_note",
        ),
        KnowledgeItem(
            topic_keys=["hargrove", "reginald", "estate"],
            content=(
                "\"Reginald Hargrove hasn't been in since Eleanor died. "
                "That man always had black coffee and stayed exactly forty minutes.\""
            ),
            suspicion_max=85,
            mood_min=15,
            stress_max=90,
        ),
    ]

    return {
        "tom_baker": tom,
        "marina_manager": marina,
        "cafe_owner": cafe,
    }


# ---------------------------------------------------------------------------
# Name → registry key lookup helpers
# ---------------------------------------------------------------------------

# Aliases that map player-typed names to registry IDs
NPC_ALIASES: dict = {
    "tom": "tom_baker",
    "tom baker": "tom_baker",
    "baker": "tom_baker",
    "petra": "marina_manager",
    "petra vance": "marina_manager",
    "marina": "marina_manager",
    "marina manager": "marina_manager",
    "manager": "marina_manager",
    "nour": "cafe_owner",
    "nour saleh": "cafe_owner",
    "saleh": "cafe_owner",
    "cafe owner": "cafe_owner",
    "cafe": "cafe_owner",
    "barista": "cafe_owner",
}


def resolve_npc(name_fragment: str, registry: dict) -> Optional[NPC]:
    """Find an NPC from a partial name typed by the player."""
    frag = name_fragment.lower().strip()
    npc_id = NPC_ALIASES.get(frag)
    if npc_id:
        return registry.get(npc_id)
    # Fuzzy: check if fragment appears in any NPC name or id
    for npc in registry.values():
        if frag in npc.name.lower() or frag in npc.id:
            return npc
    return None


def npc_roster(registry: dict) -> str:
    """Human-readable list of NPCs and their locations."""
    lines = []
    for npc in registry.values():
        lines.append(f"  • {npc.name} ({npc.role}) — {npc.location}")
    return "\n".join(lines)
