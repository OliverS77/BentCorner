"""Suggestions from your own collection – without a language model:

- upgrades(): better cards from the collection for an existing deck (EDHREC synergy with the commander, gaps in
  ramp/card draw/removal …, general popularity) – with a "take this out instead" suggestion
- commander_ideas(): commanders you own, sorted by how much of their typical deck (EDHREC) you already
  have; offline: how many good cards in their colors you have
- sixty_ideas(): 60-card decks (Standard, Pioneer, Modern, Casual): colors + theme (creature type or mechanic)
  for which your collection offers the most – purely from the card data
- draft_commander() / draft_sixty(): a rough draft from your cards to keep building on
"""
import collections

from cards import carddb
from collection import decks
from cards import edhrec
from system.i18n import tr

ROLE_TARGETS = {"commander": {"Ramp": 10, "Kartenziehen": 10, "Removal": 8, "Board Wipes": 3, "Kartenauswahl": 2},
                "sixty": {"Removal": 6, "Kartenziehen": 4}}
FORMATS_60 = [("standard", "Standard"), ("pioneer", "Pioneer"), ("modern", "Modern"), ("casual", "Casual (alles)")]
COLORS = "WUBRG"
COLOR_NAMES = {"W": "Weiß", "U": "Blau", "B": "Schwarz", "R": "Rot", "G": "Grün"}
BASICS = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
THEMES = [  # (name, test on the rules text/type) – mechanic themes for 60-card decks
    ("+1/+1-Marken", lambda r: "+1/+1 counter" in (r.get("oracle_text") or "")),
    ("Spielsteine", lambda r: "token" in (r.get("oracle_text") or "").lower()),
    ("Friedhof", lambda r: "graveyard" in (r.get("oracle_text") or "").lower()),
    ("Spontanzauber & Hexereien", lambda r: "instant or sorcery" in (r.get("oracle_text") or "").lower()),
    ("Fliegende Kreaturen", lambda r: "Flying" in (r.get("keywords") or "") and decks._type(r) == "Creature"),
    ("Lebenspunkte", lambda r: "gain" in (r.get("oracle_text") or "").lower()
     and "life" in (r.get("oracle_text") or "").lower()),
    ("Artefakte", lambda r: "Artifact" in (r.get("type_line") or "")),
    ("Verzauberungen", lambda r: "Enchantment" in (r.get("type_line") or "")),
]


# ---------- Helpers ----------
def quality(r):
    """General playing strength 0..1 from EDHREC popularity (no rank: rather weak)."""
    rank = r.get("edhrec_rank")
    return 1.0 / (1.0 + rank / 3000.0) if rank else 0.15


def legal(r, fmt):
    return fmt in (None, *decks._G.open_formats) or f'"{fmt}"' in (r.get("legalities") or "")


def in_identity(r, ident):
    return set(r.get("color_identity") or "") <= set(ident)


def is_basic(r):
    return "Basic" in (r.get("type_line") or "") and "Land" in (r.get("type_line") or "")


def owned_rows(owned_ids):
    """Your own cards as rows of the card database – one per name (the printing you own)."""
    rows = carddb.cards_by_ids(set(owned_ids)) if owned_ids else {}
    out = {}
    for sid, r in rows.items():
        if r["name"] not in out:
            out[r["name"]] = dict(r, _owned=owned_ids.get(sid, 1))
        else:
            out[r["name"]]["_owned"] = out[r["name"]].get("_owned", 1) + owned_ids.get(sid, 1)
    return list(out.values())


def _legendary_creature(r):
    tl = (r.get("type_line") or "").split(" // ")[0]
    return "Legendary" in tl and "Creature" in tl or "can be your commander" in (r.get("oracle_text") or "")


# ---------- Upgrades for a deck ----------
def upgrades(deck, rows, analysis, pool, online=True, limit=60):
    """Better cards from your collection for this deck. -> [{"row", "score", "why": [..], "out": row|None}]"""
    fmt = deck.get("format")
    commander_fmt = fmt == "commander"
    ident = analysis.get("identity") or "WUBRG"
    in_deck = {rows[c["sid"]]["name"] for c in deck["cards"] if c["sid"] in rows}
    in_deck |= {rows[s]["name"] for s in deck.get("commanders", []) if s in rows}
    cmdrs = [rows[s]["name"] for s in deck.get("commanders", []) if s in rows]
    ed = edhrec.commander(cmdrs[0], online=online) if commander_fmt and cmdrs else None
    targets = ROLE_TARGETS["commander" if commander_fmt else "sixty"]
    have = (analysis.get("roles") or {})
    gaps = {role: t - have.get(role, 0) for role, t in targets.items() if t - have.get(role, 0) > 0}

    def score(r, why=None):
        s = quality(r)
        e = (ed or {}).get("cards", {}).get(r["name"]) if ed else None
        if e:
            s += 2.0 * e["inclusion"] + 3.0 * max(0.0, e["synergy"])
            if why is not None:
                why.append(tr(f"in {round(e['inclusion'] * 100)} % of {cmdrs[0].split(',')[0]} decks")
                           + (tr(f" · synergy {round(e['synergy'] * 100)} %") if e["synergy"] > 0.05 else ""))
        for role in decks.card_roles(r):
            if role in gaps:
                s += 0.4 + 0.1 * gaps[role]
                if why is not None:
                    why.append(tr("fills a gap:") + f" {decks.role_label(role)} ({have.get(role, 0)}/{targets[role]})")
        return s

    out = []
    for r in pool:
        if r["name"] in in_deck or is_basic(r) or not legal(r, fmt):
            continue
        if commander_fmt and not in_identity(r, ident):
            continue
        if not commander_fmt and not set(r.get("colors") or "") <= set(ident or "WUBRG"):
            continue
        why = []
        s = score(r, why)
        if not why:
            if quality(r) < 0.35:
                continue  # nothing speaks for the card
            why.append(tr("played a lot"))
        out.append({"row": r, "score": s, "why": why})
    out.sort(key=lambda x: -x["score"])
    out = out[:limit]
    # take out instead: the weakest card in the deck with the same role or the same type
    deck_rows = [rows[c["sid"]] for c in deck["cards"] if c.get("board", "main") == "main" and c["sid"] in rows
                 and decks._type(rows[c["sid"]]) != "Land"]
    weak = sorted(deck_rows, key=lambda r: score(r))
    used = set()
    for x in out:
        roles, t = set(decks.card_roles(x["row"])), decks._type(x["row"])
        fits = [w for w in weak if score(w) < x["score"] and (set(decks.card_roles(w)) & roles or decks._type(w) == t)]
        cand = next((w for w in fits if w["name"] not in used), None)
        if cand is not None:
            used.add(cand["name"])
            x["out"] = cand
        else:
            x["out"] = None
        # to choose from ("take out another card …"): the weakest matching ones, then the weakest overall
        seen, opts = set(), []
        for w in fits + weak:
            if w["name"] not in seen:
                seen.add(w["name"])
                opts.append(w)
            if len(opts) >= 6:
                break
        x["options"] = opts
    return out


# ---------- New commander decks ----------
COMMANDER_LANDS = 37  # lands in the rough draft (with commander + 62 spells = 100)
CHECK_MAX = 5  # at most this many commanders are checked in detail (EDHREC only from the cache – see cards/edhrec.py)


def commander_candidates(pool):
    """All commanders in your collection, pre-sorted offline: popularity (EDHREC rank from the Scryfall data that is
    already in the card database) and how many good cards in its colors you have. No request."""
    names = {r["name"]: r for r in pool}
    out = []
    for c in names.values():
        if not (_legendary_creature(c) and legal(c, "commander")):
            continue
        ident = c.get("color_identity") or ""
        fit = sum(quality(r) for r in names.values() if r is not c and in_identity(r, ident) and not is_basic(r)
                  and legal(r, "commander"))
        out.append({"row": c, "offline": min(1.0, fit / 40.0) * 0.6 + quality(c) * 0.4, "fit": fit})
    out.sort(key=lambda x: -x["offline"])
    return out


def commander_ideas(pool, chosen=None, online=True, progress=lambda done, total: None, stop=lambda: False):
    """Check the chosen commanders (otherwise the CHECK_MAX most promising) more closely: how much of their typical
    deck (EDHREC) you already have. -> [{"row", "coverage", "owned", "missing", "missing_eur", "online"}]"""
    names = {r["name"]: r for r in pool}
    cands = [x["row"] for x in commander_candidates(pool)[:CHECK_MAX]] if chosen is None else list(chosen)[:CHECK_MAX]
    out = []
    for i, c in enumerate(cands):
        if stop():
            break
        progress(i, len(cands))
        ed = edhrec.commander(c["name"], online=online)
        ident = c.get("color_identity") or ""
        if ed and ed["cards"]:
            top_cards = sorted(ed["cards"].items(), key=lambda kv: -kv[1]["inclusion"])[:100]
            total = sum(v["inclusion"] for _, v in top_cards) or 1
            have = [(n, v) for n, v in top_cards if n in names]
            cov = sum(v["inclusion"] for _, v in have) / total
            cov *= min(1.0, len(top_cards) / 60.0)  # short list (rare commander): less meaningful
            missing = [n for n, _ in top_cards if n not in names]
            out.append({"row": c, "coverage": cov, "owned": len(have), "missing": missing, "online": True})
        else:  # offline / unknown: how many good cards in its colors do you have?
            fit = [r for r in names.values() if r is not c and in_identity(r, ident) and not is_basic(r)
                   and legal(r, "commander")]
            cov = min(1.0, sum(quality(r) for r in fit) / 40.0)
            out.append({"row": c, "coverage": cov, "owned": len(fit), "missing": [], "online": False})
    progress(len(cands), len(cands))
    out.sort(key=lambda x: -x["coverage"])
    prices = _cheapest_prices({n for x in out for n in x["missing"]})
    for x in out:
        x["missing_eur"] = round(sum(prices.get(n, 0) for n in x["missing"]), 2)
    return out


def _cheapest_prices(names):
    if not names or not carddb.exists():
        return {}
    out = {}
    with carddb.connection() as con:
        names = list(names)
        for i in range(0, len(names), 300):
            part = names[i:i + 300]
            for n, p in con.execute(f"SELECT name, MIN(eur) FROM cards WHERE eur IS NOT NULL AND name IN "
                                    f"({','.join('?' * len(part))}) GROUP BY name", part):
                out[n] = p or 0
    return out


def draft_commander(commander, pool, online=True, bonus=None):
    """Rough draft: commander + 99 from your collection (EDHREC list first, then fill gaps, then lands).
    bonus(r) -> extra value (e.g. cards of a chosen play style, brew.py). -> (commander row, [(row, count)])"""
    ident = commander.get("color_identity") or ""
    ed = edhrec.commander(commander["name"], online=online)
    fit = [r for r in pool if r["name"] != commander["name"] and in_identity(r, ident) and legal(r, "commander")]
    lands = [r for r in fit if decks._type(r) == "Land" and not is_basic(r)]
    spells = [r for r in fit if decks._type(r) != "Land"]

    def val(r):
        e = (ed or {}).get("cards", {}).get(r["name"]) if ed else None
        return quality(r) + (2.0 * e["inclusion"] + 3.0 * max(0.0, e["synergy"]) if e else 0.0)             + (bonus(r) if bonus else 0.0)
    chosen, names = [], set()
    targets = dict(ROLE_TARGETS["commander"])
    by_val = sorted(spells, key=lambda r: -val(r))
    for role, n in targets.items():  # first the basic setup
        for r in by_val:
            if n <= 0:
                break
            if r["name"] not in names and role in decks.card_roles(r):
                chosen.append(r)
                names.add(r["name"])
                n -= 1
    for r in by_val:  # then the best/most synergistic cards
        if len(chosen) >= 63:
            break
        if r["name"] not in names:
            chosen.append(r)
            names.add(r["name"])
    # Lands: as many as a commander deck needs (≈ 37) – never fill the gap with basic lands. If the collection
    # does not offer enough, the draft stays shorter (the deck builder shows how many are missing).
    land_n = max(0, min(99 - len(chosen), COMMANDER_LANDS))
    picked = sorted(lands, key=lambda r: -val(r))[:max(0, min(len(lands), land_n - 12))]
    cards = [(r, 1) for r in chosen + picked]
    cards += _basics(ident, land_n - len(picked), chosen)
    return commander, cards


def _basics(ident, n, spells):
    """n basic lands according to the color share of the mana costs."""
    if n <= 0:
        return []
    pips = collections.Counter()
    for r in spells:
        for c in COLORS:
            pips[c] += (r.get("mana_cost") or "").count("{" + c + "}")
    cols = [c for c in COLORS if c in ident] or ["W"]
    for c in cols:  # base share: even with few cards every color gets enough lands
        pips[c] += max(2, sum(pips.values()) // (2 * len(cols)))
    total = sum(pips[c] for c in cols) or len(cols)
    by_name = {}
    if carddb.exists():
        with carddb.connection() as con:
            for c in cols:
                r = con.execute("SELECT * FROM cards WHERE name = ? AND layout = 'normal' ORDER BY released DESC "
                                "LIMIT 1", (BASICS[c],)).fetchone()
                if r is not None:
                    by_name[BASICS[c]] = dict(r)
    out, left = [], n
    for i, c in enumerate(cols):
        k = left if i == len(cols) - 1 else max(1, round(n * (pips[c] or 1) / total))
        k = min(k, left)
        left -= k
        r = by_name.get(BASICS[c])
        if r and k > 0:
            out.append((r, k))
    return out


# ---------- New 60-card decks ----------
def sixty_ideas(pool, fmt="casual", top=5):
    """Colors + theme for which your collection has the most good cards. -> [{"colors", "theme", "cards",
    "score", "count"}]"""
    usable = [r for r in pool if legal(r, fmt) and decks._type(r) != "Land" and not is_basic(r)]
    combos = list(COLORS) + [a + b for i, a in enumerate(COLORS) for b in COLORS[i + 1:]]
    out = []
    for combo in combos:
        fit = [r for r in usable if set(r.get("colors") or "") <= set(combo)]
        colored = [r for r in fit if r.get("colors")]
        if len(colored) < 18 or (len(combo) == 2 and any(not any(c in (r.get("colors") or "") for r in colored)
                                                         for c in combo)):
            continue
        # theme: most common creature type or mechanic
        types = collections.Counter()
        for r in colored:  # theme only from colored cards (colorless ones fit everywhere)
            if decks._type(r) == "Creature":
                sub = (r.get("type_line") or "").split("—")[-1] if "—" in (r.get("type_line") or "") else ""
                for t in sub.split():
                    types[t] += 1
        themes = [(f"{t}", (lambda r, t=t: t in (r.get("type_line") or "")), n) for t, n in types.most_common(3)]
        themes += [(name, test, sum(1 for r in colored if test(r))) for name, test in THEMES]
        name, test, n = max(themes, key=lambda x: x[2]) if themes else ("", lambda r: False, 0)
        ranked = sorted(fit, key=lambda r: -(quality(r) + (0.6 if test(r) else 0) + (0.25 if r.get("colors") else 0)))
        deck, colorless = [], 0
        for r in ranked:  # colorless cards only as a supplement (otherwise all suggestions would look alike)
            if not r.get("colors"):
                if colorless >= 6:
                    continue
                colorless += 1
            deck.append(r)
            if len(deck) >= 36:
                break
        curve = collections.Counter(min(6, int(r.get("cmc") or 0)) for r in deck)
        curve_pen = max(0, curve.get(6, 0) - 4) * 0.3 + max(0, 6 - curve.get(1, 0) - curve.get(2, 0)) * 0.2
        score = sum(quality(r) for r in deck) + 0.15 * min(n, 20) - curve_pen
        out.append({"colors": combo, "theme": name if n >= 6 else "", "cards": deck, "score": score,
                    "count": len(fit), "theme_n": n})
    out.sort(key=lambda x: -x["score"])
    picked = []
    for x in out:  # varied ideas: hardly any overlap with those already chosen
        names = {r["name"] for r in x["cards"]}
        if all(len(names & {r["name"] for r in y["cards"]}) < 0.5 * len(names) for y in picked):
            picked.append(x)
        if len(picked) >= top:
            break
    return picked


def draft_sixty(idea, pool):
    """Rough draft of 60 cards: 36 spells (4 copies only if you have that many), 24 lands. -> [(row, count)]"""
    cards, n = [], 0
    for r in idea["cards"]:
        k = max(1, min(4, int(r.get("_owned") or 1)))
        k = min(k, 36 - n)
        if k <= 0:
            break
        cards.append((r, k))
        n += k
    combo = idea["colors"]
    lands = [r for r in pool if decks._type(r) == "Land" and not is_basic(r) and in_identity(r, combo)
             and set(r.get("color_identity") or "")][:6]
    cards += [(r, 1) for r in lands]
    cards += _basics(combo, 24 - len(lands), [r for r, _ in cards])
    return cards


def idea_title(idea):
    cols = " ".join(tr(COLOR_NAMES[c]) for c in idea["colors"])
    return cols + (f" · {tr(idea['theme'])}" if idea.get("theme") else "")
