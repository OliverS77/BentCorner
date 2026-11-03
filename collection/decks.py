"""Decks: saving (data/my-data/decks.json), text import/export and analysis.

A deck: {"id", "name", "format", "commanders": [scryfall-id …], "cards": [{"sid", "count", "board"}],
"tokens": {token: counter}, "created", "updated", "notes"}. board = "main" | "side" | "maybe".
The analysis (curve, colors, types, roles, tokens, bracket, warnings) works on the rows of the
card database.
"""
import json
import re
import time
import uuid

import games
from scanner.common import MINE

_G = games.current()   # formats, card types and deck sizes come from the game description

FILE = MINE / "decks.json"
FORMATS = list(_G.formats)
DECK_SIZE = dict(_G.deck_size)
TYPE_ORDER = list(_G.type_order)


def _game_changed():
    global _G
    _G = games.current()
    FORMATS[:] = list(_G.formats)
    DECK_SIZE.clear()
    DECK_SIZE.update(_G.deck_size)
    TYPE_ORDER[:] = list(_G.type_order)
BASIC_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes", "Snow-Covered Plains",
               "Snow-Covered Island", "Snow-Covered Swamp", "Snow-Covered Mountain", "Snow-Covered Forest",
               "Snow-Covered Wastes"}
ROLE_HELP = {   # role keys stay German: identifiers in deck analyses and deck sharing (shown via tr(), legacy_de)
    "Ramp": "more mana: mana rocks and dorks, cards that fetch lands from the library or put extra lands into play",
    "Kartenziehen": "cards that let you draw (extra) cards",
    "Removal": "removes one thing: destroy, exile, damage to a creature/planeswalker, bounce to hand",
    "Board Wipes": "clears many at once: “destroy all …”, “exile all …”, damage to each creature",
    "Tutoren": "searches your library for a specific card (land search counts as ramp)",
    "Kartenauswahl": "sets up the right cards on top: scry, surveil, look at and reorder the top cards (e.g. "
                     "Brainstorm, Ponder) – the little brother of tutors",
}
BRACKETS = {1: "Exhibition", 2: "Core", 3: "Upgraded", 4: "Optimized", 5: "cEDH"}


# ---------- Saving ----------
def load():
    try:
        return json.loads(FILE.read_text("utf-8")).get("decks", [])
    except (OSError, ValueError):
        return []


def save(decks):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    from system import undo
    undo.before_write(FILE, "Decks")
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"decks": decks}, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(FILE)


def new_deck(name, fmt=None):
    fmt = fmt or _G.default_format or "casual"
    now = time.time()
    return {"id": uuid.uuid4().hex[:12], "name": name, "format": fmt, "commanders": [], "cards": [], "tokens": {},
            "created": now, "updated": now, "notes": ""}


def add_card(deck, sid, count=1, board="main"):
    for c in deck["cards"]:
        if c["sid"] == sid and c.get("board", "main") == board:
            c["count"] = max(0, c["count"] + count)
            break
    else:
        if count > 0:
            deck["cards"].append({"sid": sid, "count": count, "board": board})
    deck["cards"] = [c for c in deck["cards"] if c["count"] > 0]
    deck["updated"] = time.time()


def all_ids(deck):
    return set(deck.get("commanders", [])) | {c["sid"] for c in deck["cards"]}


# ---------- Text ----------
_SECTION = re.compile(r"^(?:pok[eé]mon|trainers?|energy|total cards)\s*:\s*\d+$", re.I)
# Pokémon TCG Live: "4 Pikachu ex OBF 63" – set abbreviation + number after the name (no brackets)
_TRAILING_PRINT = re.compile(r"^(.+?)\s+([A-Z][A-Za-z0-9-]{1,6})\s+([A-Za-z0-9-]+)$")   # name, abbreviation, number
_LINE = re.compile(r"^\s*(\d+)\s*[xX]?\s+(.+?)\s*(?:\(([A-Za-z0-9]{1,6})\)\s*([\w\-★]+)?)?\s*(?:\*[FE]\*)?\s*$")
#                                                       {1,6}: Lorcana sets are "1" … "14" – "Hades - King of Olympus (1) 5"
# simulator lists of games with card IDs: "4xAB01-016" – count, "x", card ID, no spaces
_ID_LINE = re.compile(r"^(\d+)x([A-Za-z]{1,5}\d{0,2}-\d{2,4}(?:_[a-z]\d+)?)$")
_TAGS = re.compile(r"\s*\[([^\]]*)\]")      # Archidekt: categories "[Ramp]", "[Sideboard]", "[Maybeboard{noDeck}]"
_COLOR = re.compile(r"\s*\^[^^]*\^")         # Archidekt: color tags "^Have,#37d67a^"


def parse_text(text):
    """Deck list (Moxfield/Arena/MTGO) -> [(count, name, set, number, board)]. Board from headings:
    Commander, Sideboard, Maybeboard."""
    out, board = [], "main"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower().strip("/#: ")
        if low in ("commander", "commanders", "kommandeur"):
            board = "commander"
            continue
        if low in ("sideboard", "side", "side deck"):
            board = "side"
            continue
        if low in ("main deck", "extra deck"):   # Yu-Gi-Oh!: the Extra Deck follows from the card kind
            board = "main"
            continue
        if low in ("maybeboard", "maybe", "considering"):
            board = "maybe"
            continue
        if low in ("deck", "mainboard", "main", "companion"):
            board = "main"
            continue
        if _SECTION.match(line):   # Pokémon TCG Live headings ("Pokémon: 12", "Total Cards: 60") – no cards
            continue
        tags = [t.lower() for t in _TAGS.findall(line)]
        line = _COLOR.sub("", _TAGS.sub("", line)).strip()
        where = board
        if any(t.startswith("commander") for t in tags):
            where = "commander"
        elif any(t.startswith("sideboard") for t in tags):
            where = "side"
        elif any(t.startswith("maybeboard") for t in tags):
            where = "maybe"
        m = _ID_LINE.match(line)
        if m:   # the card ID stands in for the name – import_from looks it up by ID
            base, _, variant = m.group(2).partition("_")   # IDs: "OP05-118", parallels "OP05-118_p1"
            out.append((int(m.group(1)), base.upper() + ("_" + variant.lower() if variant else ""), "", "", where))
            continue
        m = _LINE.match(line)
        if m:
            out.append((int(m.group(1)), m.group(2).strip(), (m.group(3) or "").lower(), m.group(4) or "", where))
        else:  # no count = 1
            out.append((1, line, "", "", where))
    return out


def to_text(deck, rows):
    lines = []
    if deck.get("commanders"):
        lines.append("Commander")
        lines += [f"1 {rows[sid]['name']} ({rows[sid]['set_code'].upper()}) {rows[sid]['number']}"
                  for sid in deck["commanders"] if sid in rows]
        lines.append("")
        lines.append("Deck")
    for board, title in (("main", None), ("side", "Sideboard"), ("maybe", "Maybeboard")):
        cards = [c for c in deck["cards"] if c.get("board", "main") == board and c["sid"] in rows]
        if not cards:
            continue
        if title:
            lines += ["", title]
        for c in sorted(cards, key=lambda c: rows[c["sid"]]["name"]):
            r = rows[c["sid"]]
            lines.append(f"{c['count']} {r['name']} ({r['set_code'].upper()}) {r['number']}")
    return "\n".join(lines)


# ---------- Analysis ----------
def role_label(key):
    """A deck role as shown: Magic's "Ramp" and "Removal" stay English – de.py translates these words with another
    game's meaning (Lorcana "Tinte beschleunigen", Yu-Gi-Oh! "Entfernen"); every other role goes through tr()."""
    from system.i18n import tr
    return key if _G.key == "mtg" and key in ("Ramp", "Removal") else tr(key)


def _type(r):
    return _G.card_type(r)


_TOKEN = re.compile(r"create[s]? (?:a|an|one|two|three|four|five|six|x|that many|\w+ number of) "
                    r"((?:tapped |legendary |snow |[0-9x*]+/[0-9x*]+ )*[^.,;]*?) tokens?", re.I)
_RAMP = re.compile(r"(add \{|add one mana|add two mana|search your library for (?:a|up to \w+) (?:basic )?"
                   r"(?:land|forest|plains|island|swamp|mountain)|put (?:a|up to \w+) land card)", re.I)
_DRAW = re.compile(r"draws? (?:a|an|one|two|three|x|that many|\w+) cards?|draw cards", re.I)
_REMOVAL = re.compile(r"(destroy|exile) (?:target|up to one target|another target)|deals? \d+ damage to (?:any|"
                      r"target) (?:target|creature|planeswalker)|return target (?:nonland )?permanent to its owner",
                      re.I)
_WIPE = re.compile(r"(destroy|exile) all|each creature gets -|deals? \d+ damage to each creature", re.I)
# card selection: look at and order the top cards (Scry, Surveil, Brainstorm, Ponder …) – the tutor's little brother
_SELECT = re.compile(r"\bscry \d|\bsurveil \d|look at the top \w+ cards?|put (?:\w+ )?cards? from your hand on top "
                     r"of your library|on top of your library in any order|rearrange", re.I)
_TUTOR = re.compile(r"search your library for (?:a|an|up to \w+) (?!basic land|land|forest|plains|island|swamp|"
                    r"mountain)[^.]*card", re.I)
_EXTRA_TURN = re.compile(r"takes? an extra turn", re.I)
_MLD = re.compile(r"destroy all lands|destroy all nonbasic lands|each player sacrifices (?:all|x|\w+) lands", re.I)


def card_roles(r, t=None):
    """Roles of a card, estimated from the rules text: Ramp, Kartenziehen, Removal, Board Wipes, Tutoren (keys)."""
    t = t or _type(r)
    text = r.get("oracle_text") or ""
    roles = []
    if t != "Land" and _RAMP.search(text):
        roles.append("Ramp")
    if _DRAW.search(text):
        roles.append("Kartenziehen")
    if _WIPE.search(text):
        roles.append("Board Wipes")
    elif _REMOVAL.search(text):
        roles.append("Removal")
    if _TUTOR.search(text):
        roles.append("Tutoren")
    if _SELECT.search(text):
        roles.append("Kartenauswahl")
    return roles


def analyze(deck, rows, owned=None, owned_names=None, online=None):
    """Analysis of a deck. rows = {sid: card database row}; owned = {sid: count} from the collection;
    owned_names = {name: count} (other printings of the same card)."""
    owned, owned_names = owned or {}, owned_names or {}
    if _G.deck_rules is not None:   # other game: rules and key figures from the game description
        return analyze_generic(deck, rows, owned, owned_names)
    main = [(c, rows[c["sid"]]) for c in deck["cards"] if c.get("board", "main") == "main" and c["sid"] in rows]
    cmdrs = [rows[s] for s in deck.get("commanders", []) if s in rows]
    everything = [(1, r) for r in cmdrs] + [(c["count"], r) for c, r in main]
    total = sum(n for n, _ in everything)
    out = {"count": total, "size": DECK_SIZE.get(deck.get("format")), "curve": [0] * 8, "curve_creatures": [0] * 8,
           "types": {}, "colors": {c: 0 for c in "WUBRGC"}, "producers": {c: 0 for c in "WUBRGC"},
           "roles": {"Ramp": 0, "Kartenziehen": 0, "Kartenauswahl": 0, "Removal": 0, "Board Wipes": 0, "Tutoren": 0},
           "role_cards": {"Ramp": [], "Kartenziehen": [], "Kartenauswahl": [], "Removal": [], "Board Wipes": [],
                          "Tutoren": []},
           "tokens": {}, "price": 0.0, "missing_price": 0.0, "owned": 0, "missing": [], "warnings": [],
           "identity": "", "game_changers": [], "avg_mv": 0.0, "lands": 0,
           # cards per group (database rows) – a click in the deck info shows them
           "type_rows": {}, "curve_rows": [[] for _ in range(8)], "color_rows": {c: [] for c in "WUBRGC"},
           "role_rows": {"Ramp": [], "Kartenziehen": [], "Kartenauswahl": [], "Removal": [], "Board Wipes": [],
                         "Tutoren": []}}
    ident = set()
    for r in cmdrs:
        ident |= set(r.get("color_identity") or "")
    out["identity"] = "".join(c for c in "WUBRG" if c in ident)
    mv_sum = mv_n = 0
    for n, r in everything:
        t = _type(r)
        out["types"][t] = out["types"].get(t, 0) + n
        out["type_rows"].setdefault(t, []).append(r)
        text = r.get("oracle_text") or ""
        if t == "Land":
            out["lands"] += n
            for c in "WUBRGC":
                if "{" + c + "}" in text or (c == "C" and "{C}" in text):
                    out["producers"][c] += n
        else:
            mv = int(r.get("cmc") or 0)
            out["curve"][min(mv, 7)] += n
            out["curve_rows"][min(mv, 7)].append(r)
            if t == "Creature":
                out["curve_creatures"][min(mv, 7)] += n
            mv_sum += (r.get("cmc") or 0) * n
            mv_n += n
            for sym in re.findall(r"\{([^}]+)\}", r.get("mana_cost") or ""):
                for c in "WUBRGC":
                    if c in sym.split("/"):
                        out["colors"][c] += n
                        if r not in out["color_rows"][c]:
                            out["color_rows"][c].append(r)
        roles = card_roles(r, t)
        for role in roles:
            out["roles"][role] += n
            out["role_cards"][role].append(r["name"])
            out["role_rows"][role].append(r)
        for m in _TOKEN.finditer(text):
            name = re.sub(r"\s+", " ", m.group(1)).strip()
            name = re.sub(r"^(tapped|legendary|snow) ", "", name, flags=re.I).strip()
            if re.match(r"^(or more|of (those|that)|that|those|such|copies|a copy|the)\b", name, re.I):
                continue  # "one or more tokens", "copies of …" – not a token type of its own
            if name and len(name) < 60:
                key = name[0].upper() + name[1:]
                out["tokens"].setdefault(key, [])
                if r["name"] not in out["tokens"][key]:
                    out["tokens"][key].append(r["name"])
        if r.get("game_changer"):
            out["game_changers"].append(r["name"])
        price = r.get("eur") if r.get("eur") is not None else r.get("eur_foil")
        have = owned.get(r["id"], 0) or owned_names.get(r["name"], 0)
        out["price"] += (price or 0) * n
        got = min(n, have)
        out["owned"] += got
        if got < n:
            out["missing"].append((r["name"], n - got))
            out["missing_price"] += (price or 0) * (n - got)
        if _EXTRA_TURN.search(text):
            out.setdefault("extra_turns", []).append(r["name"])
        if _MLD.search(text):
            out.setdefault("mld", []).append(r["name"])
    out["avg_mv"] = mv_sum / mv_n if mv_n else 0.0
    names = {rows[s]["name"].split(" // ")[0] for s in all_ids(deck) if s in rows}
    out["combos"] = [(x, y) for x, y in COMBOS if x in names and y in names]
    out["online"] = online or {}  # {"csb": Commander Spellbook, "cedh": EDHTop16} – see combos.py
    out["bracket"], out["bracket_reasons"] = bracket(deck, out)
    out["warnings"] = warnings(deck, rows, out, cmdrs)
    return out


# Known two-card combos (infinite or instant win) – a small, hand-picked selection.
# Anything else (three cards, engines, commander combos …) is not detected by the estimate.
COMBOS = [
    ("Thassa's Oracle", "Demonic Consultation"), ("Thassa's Oracle", "Tainted Pact"),
    ("Isochron Scepter", "Dramatic Reversal"), ("Exquisite Blood", "Sanguine Bond"),
    ("Exquisite Blood", "Vito, Thorn of the Dusk Rose"), ("Kiki-Jiki, Mirror Breaker", "Zealous Conscripts"),
    ("Kiki-Jiki, Mirror Breaker", "Pestermite"), ("Kiki-Jiki, Mirror Breaker", "Deceiver Exarch"),
    ("Kiki-Jiki, Mirror Breaker", "Felidar Guardian"), ("Splinter Twin", "Pestermite"),
    ("Splinter Twin", "Deceiver Exarch"), ("Saheeli Rai", "Felidar Guardian"),
    ("Heliod, Sun-Crowned", "Walking Ballista"), ("Mikaeus, the Unhallowed", "Triskelion"),
    ("Devoted Druid", "Vizier of Remedies"), ("Dualcaster Mage", "Twinflame"), ("Dualcaster Mage", "Heat Shimmer"),
    ("Basalt Monolith", "Rings of Brighthearth"), ("Basalt Monolith", "Kinnan, Bonder Prodigy"),
    ("Food Chain", "Eternal Scourge"), ("Food Chain", "Misthollow Griffin"), ("Niv-Mizzet, Parun", "Curiosity"),
    ("Niv-Mizzet, the Firemind", "Curiosity"), ("Peregrine Drake", "Deadeye Navigator"),
    ("Painter's Servant", "Grindstone"), ("Worldgorger Dragon", "Animate Dead"),
    ("Bloodchief Ascension", "Mindcrank"), ("Sword of the Meek", "Thopter Foundry"),
    ("Dockside Extortionist", "Temur Sabertooth"), ("Auriok Salvagers", "Lion's Eye Diamond"),
    ("Godo, Bandit Warlord", "Helm of the Host"), ("Walking Ballista", "Mikaeus, the Unhallowed"),
    ("Underworld Breach", "Brain Freeze"), ("Chatterfang, Squirrel General", "Pitiless Plunderer"),
    ("Sanguine Bond", "Vito, Thorn of the Dusk Rose"), ("Marwyn, the Nurturer", "Umbral Mantle"),
    ("Grim Monolith", "Power Artifact"), ("Basalt Monolith", "Power Artifact"),
    ("Witherbloom Apprentice", "Chain of Smog"), ("Ghave, Guru of Spores", "Ashnod's Altar"),
]


def bracket(deck, a):
    """Commander bracket (1–5), roughly estimated from the official criteria: game changers, mass land destruction,
    extra turns, tutors. Combos cannot be detected reliably."""
    reasons = []
    gc = len(a["game_changers"])
    level = 2
    if gc:
        reasons.append(f"{gc} Game Changers: " + ", ".join(a["game_changers"][:6]))
    else:
        reasons.append("no Game Changers")
    if 1 <= gc <= 3:
        level = 3
    if gc > 3:
        level = 4
        reasons.append("more than 3 Game Changers → at least bracket 4")
    if a.get("mld"):
        level = max(level, 4)
        reasons.append("Mass land denial: " + ", ".join(a["mld"][:4]))
    turns = a.get("extra_turns") or []
    if len(turns) >= 2:
        level = max(level, 4)
        reasons.append("several extra turns: " + ", ".join(turns[:4]))
    elif turns:
        level = max(level, 3)
        reasons.append("Extra turn: " + turns[0])
    tut = a["roles"]["Tutoren"]
    if tut >= 3 and level < 3:
        level = 3
        reasons.append(f"{tut} tutors → rather bracket 3")
    elif tut:
        reasons.append(f"{tut} tutors")
    online = a.get("online") or {}
    csb = online.get("csb")
    if csb is not None:  # Commander Spellbook: real combo database instead of the small list
        inc = csb.get("included") or []
        if inc:
            level = max(level, 3)
            reasons.append(f"Commander Spellbook: {len(inc)} combo{'s' if len(inc) > 1 else ''} in the deck ("
                           + "; ".join(" + ".join(c["cards"]) for c in inc[:3]) + ") → at least bracket 3")
        else:
            reasons.append("Commander Spellbook: no complete combo in the deck")
        if csb.get("tag") == "R":
            level = max(level, 4)
            reasons.append("Commander Spellbook rates the deck “Ruthless” (cEDH-level combos) → at least bracket 4")
    else:
        combos = a.get("combos") or []
        if combos:
            level = max(level, 3)
            reasons.append("known two-card combo: " + "; ".join(f"{x} + {y}" for x, y in combos[:3]) +
                           " → at least bracket 3 (rather 4 if played early)")
    cedh = online.get("cedh") or {}
    if cedh.get("count", 0) >= 50:
        wr = cedh.get("winRate", 0) * 100
        stats = f"EDHTop16, 12 months: {cedh['count']} decks, win rate {wr:.0f} %"
        if wr >= 22:  # in a four-player pod 25 % is average
            reasons.append(f"Commander is strong in cEDH ({stats}) – bracket 5 is possible with an optimized list")
        else:
            reasons.append(f"Commander is played in cEDH but performs below average ({stats}; average in a "
                           f"four-player pod: 25 %)")
    if level == 2:
        reasons.append("Bracket 1 (Exhibition) is agreed at the table – technically the deck looks like a 2")
    if csb is None:
        reasons.append("Offline, combos come only from a small list of known pairs – online, Commander Spellbook "
                       "checks them all")
    return level, reasons


def warnings(deck, rows, a, cmdrs):
    out = []
    fmt = deck.get("format")
    if fmt == "commander":
        if not cmdrs:
            out.append("No commander chosen yet (right-click a card → As commander)")
        for r in cmdrs:
            tl = r.get("type_line") or ""
            if not ("Legendary" in tl and "Creature" in tl) and "can be your commander" not in (r.get("oracle_text")
                                                                                              or ""):
                out.append(f"{r['name']} is not a legendary creature")
        if a["count"] != 100:
            out.append(f"{a['count']} of 100 cards")
        ident = set(a["identity"])
        seen = {}
        for c in deck["cards"]:
            if c.get("board", "main") != "main" or c["sid"] not in rows:
                continue
            r = rows[c["sid"]]
            if cmdrs and not set(r.get("color_identity") or "") <= ident:
                out.append(f"{r['name']} doesn't match the color identity")
            seen[r["name"]] = seen.get(r["name"], 0) + c["count"]
        for name, n in seen.items():
            text = next((rows[c["sid"]].get("oracle_text") or "" for c in deck["cards"]
                         if c["sid"] in rows and rows[c["sid"]]["name"] == name), "")
            if n > 1 and name not in BASIC_NAMES and "any number of cards named" not in text:
                out.append(f"{name} appears {n}× (Commander: each card only once)")
        for r in cmdrs:
            if '"commander"' not in (r.get("legalities") or ""):
                out.append(f"{r['name']} is not legal in Commander")
    elif fmt in ("standard", "pioneer", "modern", "legacy", "vintage", "pauper", "constructed", "limited"):
        least = 40 if fmt == "limited" else 60
        if a["count"] < least:
            out.append(f"{a['count']} of at least {least} cards")
        seen = {}
        for c in deck["cards"]:
            if c.get("board", "main") == "main" and c["sid"] in rows:
                r = rows[c["sid"]]
                seen[r["name"]] = seen.get(r["name"], 0) + c["count"]
                if fmt not in _G.open_formats and f'"{fmt}"' not in (r.get("legalities") or ""):
                    out.append(f"{r['name']} is not legal in {fmt.title()}")
        for name, n in seen.items():
            if n > 4 and name not in BASIC_NAMES:
                out.append(f"{name} appears {n}× (at most 4)")
    return list(dict.fromkeys(out))


# ---------- other games: analysis based on the game description ----------
def analyze_generic(deck, rows, owned, owned_names):
    """Like analyze, but without Magic knowledge: card types (type_order), colors = the game's palette (cards per
    type), "curve" = the game's deck_curve, roles = deck_roles, key figures = deck_kpis, notes = deck_rules."""
    g = _G
    main = [(c, rows[c["sid"]]) for c in deck["cards"] if c.get("board", "main") == "main" and c["sid"] in rows]
    everything = [(c["count"], r) for c, r in main]
    total = sum(n for n, _ in everything)
    rules = g.deck_rules.get(deck.get("format")) or {}
    curve_meta = g.deck_curve()
    nb = len(curve_meta["labels"])
    roles = g.deck_roles()
    pal = g.palette
    out = {"count": total, "size": rules.get("size"), "curve": [0] * nb, "curve_creatures": [0] * nb,
           "curve_rows": [[] for _ in range(nb)], "curve_meta": curve_meta,
           "types": {}, "type_rows": {}, "colors": {c: 0 for c in pal}, "color_rows": {c: [] for c in pal},
           "producers": {}, "roles": {k: 0 for k in roles}, "role_cards": {k: [] for k in roles},
           "role_rows": {k: [] for k in roles}, "role_help": {k: v[1] for k, v in roles.items()},
           "tokens": {}, "price": 0.0, "missing_price": 0.0, "owned": 0, "missing": [], "warnings": [],
           "identity": "", "game_changers": [], "avg_mv": 0.0, "lands": 0, "combos": [], "online": {},
           "bracket": None, "bracket_reasons": []}
    if rules.get("size_main"):   # Yu-Gi-Oh!: Main Deck / Extra Deck / Side Deck counted separately
        lo, hi = rules["size_main"]
        z = {"main": 0, "extra": 0, "side": 0}
        for n, r in everything:
            z[g.deck_zone(r)] = z.get(g.deck_zone(r), 0) + n
        z["side"] = sum(c["count"] for c in deck["cards"] if c.get("board") == "side" and c["sid"] in rows)
        out["zones"] = z
        out["total"] = z["main"] + z["extra"]   # all cards of the deck (owned share, missing)
        out["count"], out["size"] = z["main"], f"{lo}–{hi}"
        out["size_ok"] = lo <= z["main"] <= hi
    if rules.get("leader"):   # games with a Leader: it (and DON!!) doesn't count towards the deck size
        out["count"] = sum(n for n, r in everything if g.deck_zone(r) == "main")
        out["total"] = total
    for n, r in everything:
        t = _type(r)
        out["types"][t] = out["types"].get(t, 0) + n
        out["type_rows"].setdefault(t, []).append(r)
        for c in dict.fromkeys(r.get("colors") or ""):
            if c in out["colors"]:
                out["colors"][c] += n
                out["color_rows"][c].append(r)
        b, inner = curve_meta["bin"](r)
        if b is not None:
            out["curve"][b] += n
            out["curve_rows"][b].append(r)
            if inner:
                out["curve_creatures"][b] += n
        text = r.get("oracle_text") or ""
        for role, (rx, _help) in roles.items():
            if rx.search(text):
                out["roles"][role] += n
                out["role_cards"][role].append(r["name"])
                out["role_rows"][role].append(r)
        price = r.get("eur") if r.get("eur") is not None else r.get("eur_foil")
        have = owned.get(r["id"], 0) or owned_names.get(r["name"], 0)
        out["price"] += (price or 0) * n
        got = min(n, have)
        out["owned"] += got
        if got < n:
            out["missing"].append((r["name"], n - got))
            out["missing_price"] += (price or 0) * (n - got)
    out["kpis"] = g.deck_kpis(out)
    out["identity"] = "".join(c for c in pal if out["colors"][c])   # header line: types in the deck
    out["warnings"] = rule_warnings(deck, rows, rules, g)
    return out


def rule_warnings(deck, rows, rules, g):
    """Notes based on the game's deck_rules: size (exact/minimum), copies per name (exceptions: unlimited),
    maximums per keyword (e.g. ACE SPEC 1), required cards (e.g. a Basic Pokémon), legality."""
    out = []
    main = [(c["count"], rows[c["sid"]]) for c in deck["cards"] if c.get("board", "main") == "main" and c["sid"] in rows]
    side = [(c["count"], rows[c["sid"]]) for c in deck["cards"] if c.get("board") == "side" and c["sid"] in rows]
    total = sum(n for n, _ in main)
    leaders = []
    if rules.get("leader"):   # exactly one Leader, not counted; DON!! cards aren't part of the deck either
        leaders = [r for n, r in main for _ in range(n) if g.deck_zone(r) == "leader"]
        total = sum(n for n, r in main if g.deck_zone(r) == "main")
        if len(leaders) != 1:
            out.append(f"{len(leaders)} Leaders in the deck (exactly 1)")
        if rules.get("leader_colors") and len(leaders) == 1:
            own = set(leaders[0].get("colors") or "")
            off = sorted({r["name"] for n, r in main if g.deck_zone(r) == "main"
                          and not set(r.get("colors") or "") & own})
            for name in off[:8]:
                out.append(f"{name} doesn't match the Leader's colors")
    if rules.get("size_main"):   # zones (Yu-Gi-Oh!): Main Deck range, Extra Deck and Side Deck maximum
        lo, hi = rules["size_main"]
        n_main = sum(n for n, r in main if g.deck_zone(r) == "main")
        n_extra = total - n_main
        n_side = sum(n for n, _ in side)
        if not lo <= n_main <= hi:
            out.append(f"Main Deck: {n_main} cards (allowed: {lo}–{hi})")
        if rules.get("max_extra") is not None and n_extra > rules["max_extra"]:
            out.append(f"Extra Deck: {n_extra} cards (at most {rules['max_extra']})")
        if rules.get("max_side") is not None and n_side > rules["max_side"]:
            out.append(f"Side Deck: {n_side} cards (at most {rules['max_side']})")
    size = rules.get("size")
    if size:
        if rules.get("exact") and total != size:
            out.append(f"{total} of {size} cards")
        elif not rules.get("exact") and total < size:
            out.append(f"{total} of at least {size} cards")
    seen, sample = {}, {}
    for n, r in main + (side if rules.get("copies_all") else []):   # Yu-Gi-Oh!: 3 copies across all decks
        if g.deck_unlimited(r) or (leaders and g.deck_zone(r) != "main"):
            continue
        key = g.deck_name_key(r)
        seen[key] = seen.get(key, 0) + n
        sample.setdefault(key, r)
    copies = rules.get("copies")
    banned = []
    label = {k: (f"{r['name']} ({k})" if k != r.get("name") else k) for k, r in sample.items()}  # games that count by card ID
    for key, n in seen.items():
        name = label[key]
        ban = g.deck_ban_limit(sample[key]) if rules.get("banlist") else None
        own = g.deck_copy_limit(sample[key])   # the card's own limit (Lorcana: Dalmatian Puppy 99)
        if ban == 0:
            banned.append(name)
        elif ban is not None and n > ban:
            out.append(f"{name} appears {n}× (banlist: at most {ban})")
        elif own is not None:
            if n > own:
                out.append(f"{name} appears {n}× (at most {own})")
        elif copies and n > copies:
            out.append(f"{name} appears {n}× (at most {copies})")
    for name in sorted(banned):
        out.append(f"{name} is forbidden")
    for a, b in rules.get("banned_pairs") or ():   # these two may not be in the same deck
        keys = {g.deck_name_key(r) for _, r in main}
        if a in keys and b in keys:
            out.append(f"{a} and {b} may not be in the same deck")
    if rules.get("max_colors"):   # Lorcana: at most 2 inks (dual-ink cards count both)
        used = {c for _, r in main for c in (r.get("colors") or "") if c in g.palette}
        if len(used) > rules["max_colors"]:
            out.append(f"{len(used)} {rules.get('colors_word', 'colors')} in the deck (at most {rules['max_colors']})")
    for kw, limit, label in rules.get("limits") or ():
        n = sum(k for k, r in main if kw in [x.strip() for x in (r.get("keywords") or "").split(",")])
        if n > limit:
            out.append(f"{n} {label} cards (at most {limit} in the deck)")
    for test, text in rules.get("require") or ():
        if main and not any(test(r) for _, r in main):
            out.append(text)
    legal = rules.get("legal")
    if legal:
        by_name = g.deck_legal_names({r["name"] for _, r in main}, legal)   # Pokémon: legal by name (reprints)
        bad = sorted({r["name"] for _, r in main if not g.deck_unlimited(r)   # basic energy is always allowed
                      and (r["name"] not in by_name if by_name is not None
                           else f'"{legal}"' not in (r.get("legalities") or ""))})
        for name in bad[:12]:
            out.append(f"{name} is not legal in {g.format_name(deck.get('format'))}")
        if len(bad) > 12:
            out.append(f"… and {len(bad) - 12} more not legal")
    return list(dict.fromkeys(out))
