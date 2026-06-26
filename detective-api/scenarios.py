"""
Scenario system — load different investigative situations without changing core systems.

Each Scenario is a named configuration that produces fresh NPC, truth, and rumor
instances via factory callables.  Loading a scenario resets the full game state and
populates it with the scenario's data; all existing epistemic systems (salience,
contradiction detection, social sim, investigation board) operate unchanged.

Registry
--------
SCENARIOS   — dict[id: str, Scenario]
load_scenario(name: str) -> GameState

Scenario IDs (case-insensitive aliases accepted)
------------------------------------------------
hargrove_affair   — default story (Eleanor Voss murder)
harbor_fuel       — Scenario A: Harbor Fuel Discrepancy
missing_tourist   — Scenario B: Missing Tourist
election_scandal  — Scenario C: Election Scandal
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import uuid

# Daily life types — imported lazily inside builders to avoid circular import at module load
def _dl():
    from daily_life import Schedule, Occupation, Relationship, PersonalGoal
    return Schedule, Occupation, Relationship, PersonalGoal


# ---------------------------------------------------------------------------
# Scenario dataclass
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    id: str                       # canonical slug
    name: str                     # display name
    description: str              # one-paragraph synopsis
    case_title: str               # shown in /state case.title
    case_victim: str              # shown in /state case.victim
    build_npcs: Callable          # () -> dict[str, NPC]
    build_truths: Callable        # () -> list[TruthEvent]
    build_rumors: Callable        # () -> list[Rumor]
    aliases: list = None          # additional names that resolve to this scenario

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []


# ---------------------------------------------------------------------------
# Helpers — shared across scenario builders
# ---------------------------------------------------------------------------

def _rumor(content, source_npc_id, subjects, credibility=70, known_by=None):
    """Convenience factory for seed rumors."""
    from rumor import Rumor
    if known_by is None:
        known_by = [source_npc_id]
    return Rumor(
        id=uuid.uuid4().hex[:8],
        content=content,
        original_content=content,
        source_npc_id=source_npc_id,
        subjects=subjects,
        credibility=credibility,
        distortion_level=0,
        known_by=known_by,
    )


def _truth(id_, description, subject_ids, source_type="system", confidence=100):
    from truth import TruthEvent
    return TruthEvent(
        id=id_,
        description=description,
        source_type=source_type,
        confidence=confidence,
        subject_ids=subject_ids,
    )


def _npc(id_, name, location, role, mood=55, stress=30, suspicion=15, knowledge=None):
    from npc import NPC
    return NPC(
        id=id_,
        name=name,
        location=location,
        role=role,
        mood=mood,
        stress=stress,
        suspicion=suspicion,
        knowledge=knowledge or [],
    )


def _ki(topic_keys, content, suspicion_max=65, mood_min=20, stress_max=80, clue_id=None):
    from npc import KnowledgeItem
    return KnowledgeItem(
        topic_keys=topic_keys,
        content=content,
        suspicion_max=suspicion_max,
        mood_min=mood_min,
        stress_max=stress_max,
        case_clue_id=clue_id,
    )


# ---------------------------------------------------------------------------
# Scenario A — Harbor Fuel Discrepancy
# ---------------------------------------------------------------------------

def _harbor_npcs():
    petra = _npc(
        "petra_vance", "Petra Vance", "Island Marina",
        "Marina Manager",
        mood=45, stress=55, suspicion=30,
        knowledge=[
            _ki(["ledger", "accounts", "discrepancy", "money", "fuel", "shortfall"],
                '"The accounts are reconciled monthly by the harbour authority, not me. '
                'I manage berths and scheduling. Reg Coyle signs off the fuel invoices."',
                suspicion_max=70, mood_min=20),
            _ki(["reg", "coyle", "harbor master", "harbour master", "signing"],
                '"Reg has been harbour master for eleven years. He\'s always handled the '
                'fuel procurement. I wouldn\'t know where to start with those numbers."',
                suspicion_max=75, mood_min=15),
            _ki(["cctv", "camera", "footage", "maintenance", "october"],
                '"The camera was down for a scheduled firmware update. Standard procedure. '
                'I submitted the maintenance request myself — the form is on file."',
                suspicion_max=60, mood_min=30),
            _ki(["kay", "devereux", "supplier", "delivery", "vendor"],
                '"Kay Devereux has supplied the marina for three years. No complaints until '
                'now. She seemed surprised when I told her about the discrepancy."',
                suspicion_max=80, mood_min=25),
        ]
    )

    reg = _npc(
        "reg_coyle", "Reg Coyle", "Harbour Office",
        "Harbour Master",
        mood=40, stress=65, suspicion=50,
        knowledge=[
            _ki(["fuel", "delivery", "october", "ledger", "240"],
                '"I signed for the delivery myself. Two hundred and forty litres, on '
                'the third of October. Everything matched the order form."',
                suspicion_max=60, mood_min=30),
            _ki(["debt", "money", "owe", "gambling", "bookmaker"],
                '"Those are personal matters. Nothing to do with harbour business."',
                suspicion_max=40, mood_min=50),
            _ki(["pub", "rusty anchor", "anchor", "tuesday", "evening"],
                '"I pop in for a pint now and then. Same as everyone on the island."',
                suspicion_max=55, mood_min=20),
            _ki(["signature", "invoice", "sign", "paperwork"],
                '"I sign what arrives. If the volume\'s off, that\'s the supplier\'s problem, '
                'not mine."',
                suspicion_max=70, mood_min=15, clue_id="signed_invoice"),
        ]
    )

    kay = _npc(
        "kay_devereux", "Kay Devereux", "Harbour Cafe",
        "Fuel Supplier Representative",
        mood=60, stress=40, suspicion=20,
        knowledge=[
            _ki(["delivery", "volume", "litre", "amount", "october", "quantity"],
                '"Our delivery records show two hundred and forty litres dispatched. '
                'The pump meter logs are timestamped — I can pull them if needed."',
                suspicion_max=80, mood_min=15),
            _ki(["port callow", "previous", "complaint", "client", "other"],
                '"Port Callow was a completely different situation. That client had a '
                'faulty meter. Our equipment here passed inspection in September."',
                suspicion_max=70, mood_min=20),
            _ki(["invoice", "payment", "money", "shortfall", "discrepancy"],
                '"We were paid in full, on time. Whatever the discrepancy is, it\'s '
                'internal to the marina — not on our end."',
                suspicion_max=80, mood_min=15, clue_id="supplier_invoice"),
            _ki(["reg", "coyle", "sign", "harbour master"],
                '"Reg was there when we unloaded. He watched the whole thing and '
                'signed without hesitation."',
                suspicion_max=80, mood_min=20),
        ]
    )

    Schedule, Occupation, Relationship, PersonalGoal = _dl()

    petra.schedule = Schedule(morning=["marina"], afternoon=["marina"],
                              evening=["home"],   night=["home"])
    petra.occupation = Occupation("Marina Manager", "Island Harbour Authority",
                                  "medium", "medium")
    petra.relationships = [
        Relationship("reg_coyle",   "Reg Coyle",   "business", 55, "direct working relationship"),
        Relationship("kay_devereux","Kay Devereux", "business", 35, "fuel supply contract"),
    ]
    petra.goals = [
        PersonalGoal("protect_reputation", "Protect professional reputation", "social",    urgency=65),
        PersonalGoal("earn_money",         "Keep marina financially solvent",  "financial", urgency=40),
    ]

    reg.schedule = Schedule(morning=["harbour_office"], afternoon=["harbour_office"],
                            evening=["pub"],            night=["home"])
    reg.occupation = Occupation("Harbour Master", "Island Harbour Authority",
                                "medium", "medium")
    reg.relationships = [
        Relationship("petra_vance", "Petra Vance", "business", 50, "direct line manager"),
        Relationship("kay_devereux","Kay Devereux", "business", 40, "supplier contact"),
    ]
    reg.goals = [
        PersonalGoal("hide_mistake",       "Conceal involvement in shortfall", "criminal", urgency=80),
        PersonalGoal("protect_reputation", "Maintain standing as harbour master","social",  urgency=70),
    ]

    kay.schedule = Schedule(morning=["marina"],  afternoon=["cafe"],
                            evening=["home"],    night=["home"])
    kay.occupation = Occupation("Fuel Supplier Representative", "Callow Marine Supplies",
                                "medium", "medium")
    kay.relationships = [
        Relationship("reg_coyle",   "Reg Coyle",   "business", 45, "key client contact"),
        Relationship("petra_vance", "Petra Vance", "business", 30, "account manager"),
    ]
    kay.goals = [
        PersonalGoal("protect_reputation","Clear supplier's name",         "social",    urgency=60),
        PersonalGoal("earn_money",        "Retain island marina contract", "financial", urgency=50),
    ]

    return {"petra_vance": petra, "reg_coyle": reg, "kay_devereux": kay}


def _harbor_truths():
    return [
        _truth("truth_fuel_discrepancy",
               "Marina fuel account ledger shows a £4,200 discrepancy in the October "
               "harbour records — 240 litres were invoiced but only 192 litres are "
               "accounted for in the usage log.",
               ["marina", "ledger", "reg_coyle"]),
        _truth("truth_delivery_signed",
               "Harbour authority delivery log confirms 240 litres were received and "
               "signed for by Reg Coyle at the harbour dock on 3 October.",
               ["marina", "reg_coyle"],
               source_type="environmental", confidence=95),
        _truth("truth_cctv_offline",
               "Marina CCTV maintenance request submitted by Petra Vance on 2 October "
               "— camera offline from 18:00 on 3 October until 09:00 on 4 October.",
               ["marina", "petra_vance"],
               source_type="environmental", confidence=90),
    ]


def _harbor_rumors():
    return [
        _rumor(
            "Reg Coyle was seen at The Rusty Anchor pub until well after midnight on "
            "October 3rd — the same evening he claims to have personally supervised "
            "the fuel delivery at the harbour dock.",
            "petra_vance",
            ["reg_coyle"],
            credibility=74,
            known_by=["petra_vance", "kay_devereux"],
        ),
        _rumor(
            "Word is that Reg Coyle owes a considerable sum to people around the island. "
            "He has been seen in hushed conversations near the marina office at odd hours.",
            "kay_devereux",
            ["reg_coyle"],
            credibility=62,
        ),
        _rumor(
            "Petra Vance was seen adjusting entries in the marina ledger late on a "
            "Tuesday evening, after everyone else had left the harbour office.",
            "reg_coyle",
            ["petra_vance", "marina"],
            credibility=58,
        ),
        _rumor(
            "The fuel supplier's previous client in Port Callow raised a nearly identical "
            "discrepancy claim last year — and it was quietly settled out of court.",
            "reg_coyle",
            ["kay_devereux"],
            credibility=50,
        ),
    ]


# ---------------------------------------------------------------------------
# Scenario B — Missing Tourist
# ---------------------------------------------------------------------------

def _tourist_npcs():
    tom_r = _npc(
        "tom_renner", "Tom Renner", "The Rusty Anchor",
        "Pub Landlord",
        mood=55, stress=35, suspicion=10,
        knowledge=[
            _ki(["daniel", "marsh", "tourist", "man", "visitor"],
                '"He sat in that corner booth on Thursday. Ordered a pint of bitter, '
                'barely touched it. Seemed nervous — kept checking his phone."',
                suspicion_max=80, mood_min=20),
            _ki(["argument", "arguing", "row", "fight", "local"],
                '"There was a word exchanged, yes. A man I didn\'t recognise — not a '
                'regular. Voices were raised, then the stranger left quickly."',
                suspicion_max=65, mood_min=30, clue_id="pub_argument"),
            _ki(["stranger", "unknown", "other man", "who"],
                '"Short, dark coat, spoke with an accent — not from the island. '
                'I only saw his back as he left."',
                suspicion_max=70, mood_min=25),
            _ki(["last seen", "leave", "left", "when", "time"],
                '"Daniel left around half nine. Said something about needing fresh air. '
                'I assumed he was heading back to the hotel."',
                suspicion_max=80, mood_min=15),
        ]
    )

    sienna = _npc(
        "sienna_ward", "Sienna Ward", "Harbour View Hotel",
        "Hotel Owner",
        mood=40, stress=60, suspicion=20,
        knowledge=[
            _ki(["check out", "checkout", "hotel", "left", "room"],
                '"Daniel Marsh checked out on Saturday morning — two days before his '
                'booked departure. Paid in cash, which was unusual. Seemed in a hurry."',
                suspicion_max=75, mood_min=15, clue_id="early_checkout"),
            _ki(["luggage", "bags", "belongings", "suitcase"],
                '"He took everything. The room was stripped. No note, nothing left behind."',
                suspicion_max=80, mood_min=20),
            _ki(["phone", "call", "contact", "message"],
                '"He received a call Friday evening — I heard him in the corridor. '
                'His voice was very low and then he went quiet for a long time."',
                suspicion_max=65, mood_min=30),
            _ki(["ferry", "boat", "travel", "leave island"],
                '"I assumed he got the Saturday ferry. But you\'re saying he didn\'t?"',
                suspicion_max=80, mood_min=15),
        ]
    )

    pascal = _npc(
        "pascal_dubois", "Pascal Dubois", "Island Marina",
        "Fisherman",
        mood=50, stress=25, suspicion=15,
        knowledge=[
            _ki(["cliffs", "east", "alone", "figure", "dusk", "walking"],
                '"I was hauling pots late Thursday. Saw a man walking toward the east '
                'cliffs. City shoes — wrong footwear for the path up there. I thought '
                'nothing of it at the time."',
                suspicion_max=80, mood_min=15),
            _ki(["marina", "dock", "harbour", "boat", "morning", "friday"],
                '"Early Friday, someone matching that description was at the harbour. '
                'Watching the boats but not approaching any of them."',
                suspicion_max=75, mood_min=20, clue_id="marina_sighting"),
            _ki(["stranger", "dark coat", "argument", "pub"],
                '"The man from the pub? I\'ve seen him before — he came off the mail '
                'ferry about a week ago. Not a tourist."',
                suspicion_max=65, mood_min=30),
        ]
    )

    Schedule, Occupation, Relationship, PersonalGoal = _dl()

    tom_r.schedule = Schedule(morning=["pub"],   afternoon=["pub"],
                              evening=["pub"],   night=["pub"])
    tom_r.occupation = Occupation("Pub Landlord", "The Rusty Anchor",
                                  "medium", "medium")
    tom_r.relationships = [
        Relationship("sienna_ward",  "Sienna Ward",  "business",    45, "island trade — tourists stay at her hotel"),
        Relationship("pascal_dubois","Pascal Dubois", "friendship",  55, "fishing trade friends"),
    ]
    tom_r.goals = [
        PersonalGoal("earn_money",         "Keep the pub profitable",       "financial", urgency=45),
        PersonalGoal("protect_reputation", "Protect pub's safe reputation", "social",    urgency=40),
    ]

    sienna.schedule = Schedule(morning=["hotel"], afternoon=["hotel"],
                               evening=["hotel"], night=["home"])
    sienna.occupation = Occupation("Hotel Owner", "Harbour View Hotel",
                                   "medium", "high")
    sienna.relationships = [
        Relationship("tom_renner",   "Tom Renner",   "business",  40, "tourist referrals"),
        Relationship("pascal_dubois","Pascal Dubois", "acquaintance", 20, "occasional boat trips"),
    ]
    sienna.goals = [
        PersonalGoal("protect_reputation","Protect hotel's reputation",   "social",    urgency=72),
        PersonalGoal("hide_mistake",      "Not get blamed for disappearance","criminal",urgency=55),
    ]

    pascal.schedule = Schedule(morning=["marina"],  afternoon=["marina"],
                               evening=["pub"],     night=["home"])
    pascal.occupation = Occupation("Fisherman", "Self (fishing vessel)",
                                   "low", "low")
    pascal.relationships = [
        Relationship("tom_renner", "Tom Renner", "friendship", 60, "regular at the pub"),
        Relationship("sienna_ward","Sienna Ward", "acquaintance", 15, "sees her at harbour events"),
    ]
    pascal.goals = [
        PersonalGoal("earn_money",  "Maintain fishing livelihood",  "financial", urgency=40),
        PersonalGoal("help_friend", "Look out for Tom's interests", "personal",  urgency=20),
    ]

    return {"tom_renner": tom_r, "sienna_ward": sienna, "pascal_dubois": pascal}


def _tourist_truths():
    return [
        _truth("truth_hotel_checkout",
               "Hotel records show Daniel Marsh checked out of Harbour View Hotel on "
               "Saturday morning, two days before his scheduled departure flight.",
               ["daniel_marsh"],
               source_type="environmental", confidence=100),
        _truth("truth_ferry_manifest",
               "Ferry company manifest confirms Daniel Marsh did not board any ferry "
               "on Saturday or Sunday — the only two departure days after checkout.",
               ["daniel_marsh", "marina"],
               source_type="system", confidence=95),
        _truth("truth_cash_payment",
               "Hotel receipt shows Daniel Marsh paid his full bill in cash on Saturday "
               "morning, contrary to his original booking which was credit-card guaranteed.",
               ["daniel_marsh"],
               source_type="environmental", confidence=100),
    ]


def _tourist_rumors():
    return [
        _rumor(
            "Daniel Marsh was seen in a heated argument with an unknown man at "
            "The Rusty Anchor pub on Thursday night — voices raised, the stranger "
            "left first and did not return.",
            "tom_renner",
            ["daniel_marsh"],
            credibility=76,
            known_by=["tom_renner", "sienna_ward"],
        ),
        _rumor(
            "A figure matching Daniel Marsh was spotted walking alone toward the "
            "harbour dock early on Friday morning, watching the boats without "
            "approaching any of them.",
            "pascal_dubois",
            ["daniel_marsh", "marina"],
            credibility=65,
        ),
        _rumor(
            "Someone saw a man matching the tourist's description climbing the "
            "east cliffs path at dusk on Thursday — wearing city shoes, not "
            "walking gear.",
            "pascal_dubois",
            ["daniel_marsh"],
            credibility=60,
            known_by=["pascal_dubois", "sienna_ward"],
        ),
        _rumor(
            "Word is that Daniel Marsh came to the island to meet someone specific — "
            "a contact he refused to name when he checked in.",
            "sienna_ward",
            ["daniel_marsh"],
            credibility=55,
        ),
    ]


# ---------------------------------------------------------------------------
# Scenario C — Election Scandal
# ---------------------------------------------------------------------------

def _election_npcs():
    pike = _npc(
        "alderman_pike", "Alderman Pike", "Council Chambers",
        "Incumbent Council Leader",
        mood=35, stress=70, suspicion=75,
        knowledge=[
            _ki(["call", "phone", "nadia", "cross", "contact"],
                '"I categorically did not call the returning officer\'s office before '
                'the count. Any suggestion otherwise is a political smear."',
                suspicion_max=50, mood_min=25),
            _ki(["ward 3", "ballot", "box", "unsupervised", "count"],
                '"Every procedural step was followed. The returning officer oversaw '
                'everything. I wasn\'t even in the building during the count."',
                suspicion_max=55, mood_min=20),
            _ki(["marina", "election night", "where", "vehicle"],
                '"I was at campaign headquarters on election night, as anyone on my '
                'team will confirm."',
                suspicion_max=45, mood_min=30),
            _ki(["transport", "bus", "voters", "polling station"],
                '"Offering transport to the polls is entirely legal and common practice. '
                'We helped elderly residents who couldn\'t otherwise reach the station."',
                suspicion_max=65, mood_min=15),
        ]
    )

    nadia = _npc(
        "nadia_cross", "Nadia Cross", "Council Chambers",
        "Returning Officer",
        mood=40, stress=75, suspicion=40,
        knowledge=[
            _ki(["call", "phone", "pike", "contact", "thirty minutes", "before"],
                '"I receive many calls on election night. I can\'t comment on '
                'specific communications without checking the official log."',
                suspicion_max=50, mood_min=20),
            _ki(["ward 3", "ballot", "box", "gap", "twenty minutes", "unsupervised"],
                '"There was a brief period — entirely within normal parameters — '
                'where the boxes were in the secure staging area. I was present."',
                suspicion_max=55, mood_min=25, clue_id="ward3_gap"),
            _ki(["47", "ballots", "after closing", "late", "closing time"],
                '"Those ballots were from postal voters whose envelopes arrived in '
                'time. The legislation allows for a grace period. It was lawful."',
                suspicion_max=60, mood_min=20),
            _ki(["pressure", "told", "instructed", "told to", "directive"],
                '"This interview is over."',
                suspicion_max=25, mood_min=60),
        ]
    )

    jack = _npc(
        "jack_varro", "Jack Varro", "Harbour Cafe",
        "Local Journalist",
        mood=65, stress=40, suspicion=10,
        knowledge=[
            _ki(["count", "tally", "numbers", "figures", "supervisor"],
                '"A count supervisor — wouldn\'t give me a name — said the Ward 3 '
                'tally sheet total didn\'t match the number of ballot papers in the box. '
                'Off by eleven, he said."',
                suspicion_max=80, mood_min=20, clue_id="tally_discrepancy"),
            _ki(["phone", "call", "nadia", "pike", "record", "log"],
                '"I submitted a freedom-of-information request for all calls to '
                'the returning officer\'s office on election night. Still waiting."',
                suspicion_max=80, mood_min=20),
            _ki(["marina", "pike", "election night", "vehicle", "seen"],
                '"Three separate sources put Pike\'s campaign vehicle at the marina '
                'hall around 9 pm — right when Ward 3 boxes were being moved."',
                suspicion_max=75, mood_min=20, clue_id="pike_marina_sighting"),
            _ki(["pub", "celebrating", "early", "anchor", "pike"],
                '"He was at the pub by 8:45 pm, champagne out, victory speech ready. '
                'The result wasn\'t called until 10:30."',
                suspicion_max=80, mood_min=15),
        ]
    )

    Schedule, Occupation, Relationship, PersonalGoal = _dl()

    pike.schedule = Schedule(morning=["council_chambers"], afternoon=["council_chambers"],
                             evening=["pub"],              night=["home"])
    pike.occupation = Occupation("Alderman / Council Leader", "Island Council",
                                 "high", "high")
    pike.relationships = [
        Relationship("nadia_cross", "Nadia Cross", "business", 60, "returning officer — institutional authority"),
        Relationship("jack_varro",  "Jack Varro",  "rivalry",  70, "hostile press coverage"),
    ]
    pike.goals = [
        PersonalGoal("protect_reputation", "Maintain political legitimacy",    "social",    urgency=85),
        PersonalGoal("hide_mistake",       "Suppress evidence of interference","criminal",  urgency=78),
        PersonalGoal("seek_promotion",     "Secure second term unopposed",      "social",    urgency=60),
    ]

    nadia.schedule = Schedule(morning=["council_chambers"], afternoon=["council_chambers"],
                              evening=["home"],             night=["home"])
    nadia.occupation = Occupation("Returning Officer", "Electoral Commission (Island)",
                                  "medium", "high")
    nadia.relationships = [
        Relationship("alderman_pike","Alderman Pike", "business", 55, "electoral authority relationship"),
        Relationship("jack_varro",  "Jack Varro",    "rivalry",  40, "press scrutiny"),
    ]
    nadia.goals = [
        PersonalGoal("protect_reputation","Defend impartiality of election",   "social",   urgency=80),
        PersonalGoal("hide_mistake",      "Conceal procedural irregularities", "criminal", urgency=65),
    ]

    jack.schedule = Schedule(morning=["cafe"],   afternoon=["harbour_office"],
                             evening=["pub"],    night=["home"])
    jack.occupation = Occupation("Journalist", "The Island Courier",
                                 "low", "medium")
    jack.relationships = [
        Relationship("alderman_pike","Alderman Pike", "rivalry",  75, "investigative target"),
        Relationship("nadia_cross", "Nadia Cross",   "rivalry",  35, "reluctant source"),
    ]
    jack.goals = [
        PersonalGoal("seek_promotion",     "Break the election story nationally","social",   urgency=75),
        PersonalGoal("protect_reputation", "Maintain journalistic credibility",  "social",   urgency=55),
        PersonalGoal("help_friend",        "Expose injustice for Drummond",      "personal", urgency=60),
    ]

    return {"alderman_pike": pike, "nadia_cross": nadia, "jack_varro": jack}


def _election_truths():
    return [
        _truth("truth_official_count",
               "Official ballot count certified by the returning officer: "
               "Pike 312 votes, Drummond 298 votes — Pike declared winner by 14.",
               ["alderman_pike", "election"],
               source_type="system", confidence=100),
        _truth("truth_late_ballots",
               "Station log shows 47 ballots were processed after the official "
               "closing time of 22:00, all attributed to the Ward 3 postal batch.",
               ["election", "nadia_cross"],
               source_type="environmental", confidence=95),
        _truth("truth_ward3_tally",
               "Independent count supervisor's record shows Ward 3 tally sheet "
               "total is 11 higher than the number of ballot papers physically "
               "counted in the box.",
               ["election", "nadia_cross"],
               source_type="npc", confidence=80),
    ]


def _election_rumors():
    return [
        _rumor(
            "Alderman Pike's campaign vehicle was seen at the marina hall around "
            "9 pm on election night — precisely when the Ward 3 ballot boxes were "
            "being transferred to the staging area.",
            "jack_varro",
            ["alderman_pike", "marina"],
            credibility=72,
            known_by=["jack_varro", "nadia_cross"],
        ),
        _rumor(
            "Pike was spotted at The Rusty Anchor pub with champagne before 9 pm "
            "on election night — hours before the result was officially declared.",
            "jack_varro",
            ["alderman_pike"],
            credibility=68,
            known_by=["jack_varro"],
        ),
        _rumor(
            "Nadia Cross received a phone call from Pike's campaign office thirty "
            "minutes before the final count was announced — a call she has not "
            "publicly acknowledged.",
            "jack_varro",
            ["nadia_cross", "alderman_pike"],
            credibility=65,
        ),
        _rumor(
            "A count supervisor says the Ward 3 ballot figures don't match the "
            "tally sheet — eleven votes unaccounted for in the final reconciliation.",
            "jack_varro",
            ["election", "nadia_cross"],
            credibility=70,
            known_by=["jack_varro", "alderman_pike"],
        ),
        _rumor(
            "Pike's campaign paid for a minibus to transport voters to the polling "
            "station — selecting pickup points exclusively in wards that historically "
            "favour his party.",
            "nadia_cross",
            ["alderman_pike", "election"],
            credibility=60,
        ),
    ]


# ---------------------------------------------------------------------------
# Default scenario — The Hargrove Affair (wraps existing builders)
# ---------------------------------------------------------------------------

def _hargrove_npcs():
    from npc import build_npc_registry
    return build_npc_registry()


def _hargrove_truths():
    from truth import build_seed_truths
    return build_seed_truths()


def _hargrove_rumors():
    from rumor import build_seed_rumors
    return build_seed_rumors()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

SCENARIOS: dict = {
    "hargrove_affair": Scenario(
        id="hargrove_affair",
        name="The Hargrove Affair",
        description=(
            "Eleanor Voss has been found dead in the east wing of Hargrove Manor. "
            "The island is rife with rumour. Reginald Hargrove is the prime suspect "
            "but has yet to be located. Gather evidence, expose contradictions, "
            "and close the case."
        ),
        case_title="The Hargrove Affair",
        case_victim="Eleanor Voss",
        build_npcs=_hargrove_npcs,
        build_truths=_hargrove_truths,
        build_rumors=_hargrove_rumors,
        aliases=["hargrove", "default", "eleanor"],
    ),

    "harbor_fuel": Scenario(
        id="harbor_fuel",
        name="Harbor Fuel Discrepancy",
        description=(
            "£4,200 is missing from the Island Marina's October fuel account. "
            "The delivery was signed for in full. The CCTV was conveniently offline. "
            "Three people were in a position to move the money — only one of them "
            "has a gambling debt."
        ),
        case_title="Harbor Fuel Discrepancy",
        case_victim="Marina Fuel Fund",
        build_npcs=_harbor_npcs,
        build_truths=_harbor_truths,
        build_rumors=_harbor_rumors,
        aliases=["harbor", "harbour", "fuel", "marina discrepancy"],
    ),

    "missing_tourist": Scenario(
        id="missing_tourist",
        name="Missing Tourist",
        description=(
            "Daniel Marsh, a tourist, checked out of his hotel two days early and "
            "never boarded a ferry. Three witnesses place him in three different "
            "locations on Thursday night. One of those accounts must be false — "
            "but which one, and why?"
        ),
        case_title="Missing Tourist",
        case_victim="Daniel Marsh (missing)",
        build_npcs=_tourist_npcs,
        build_truths=_tourist_truths,
        build_rumors=_tourist_rumors,
        aliases=["tourist", "missing", "daniel", "marsh"],
    ),

    "election_scandal": Scenario(
        id="election_scandal",
        name="Election Scandal",
        description=(
            "Alderman Pike won the island council election by 14 votes. A count "
            "supervisor says the Ward 3 tally sheet doesn't add up. Pike's vehicle "
            "was near the ballot boxes at the critical moment — and he was seen "
            "celebrating before the result was declared."
        ),
        case_title="Election Scandal",
        case_victim="Democratic Process",
        build_npcs=_election_npcs,
        build_truths=_election_truths,
        build_rumors=_election_rumors,
        aliases=["election", "scandal", "pike", "vote", "ballot"],
    ),
}

# Flat alias → id lookup built at import time
_ALIAS_MAP: dict = {}
for _sid, _s in SCENARIOS.items():
    _ALIAS_MAP[_sid] = _sid
    for _a in _s.aliases:
        _ALIAS_MAP[_a.lower()] = _sid


def resolve_scenario(name: str):
    """Return Scenario for name/alias (case-insensitive) or None."""
    return SCENARIOS.get(_ALIAS_MAP.get(name.lower().strip()))


def load_scenario(name: str):
    """
    Resolve and return the Scenario for name/alias.
    Raises ValueError if the name is not recognised.

    Callers are responsible for applying the scenario to the live state;
    use state.load_from_scenario(scenario) to mutate in place, or
    GameState.from_scenario(scenario) to get a fresh object.
    """
    scenario = resolve_scenario(name)
    if not scenario:
        known = ", ".join(s.name for s in SCENARIOS.values())
        raise ValueError(f"Unknown scenario '{name}'. Available: {known}")
    return scenario
