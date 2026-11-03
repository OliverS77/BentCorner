"""Bent°Corner Brew – deck helper: what can I build from my cards?

Choose a format, optionally colors, then a play style (archetype): each style shows how many of your cards fit it
and which colors they are in. This yields suggestions – commanders (your own first, otherwise popular ones you
don't have yet) or 60-card drafts – and with one click a rough draft in the deck builder.
Everything offline from the card data; only the rough draft of a commander deck queries EDHREC once (as before).
"""
import collections
import re

from cards import carddb
from collection import decks
from collection import suggest
from system.i18n import tr

COLORS = "WUBRG"


def _t(r):
    return (r.get("oracle_text") or "").lower()


def _tl(r):
    return r.get("type_line") or ""


def _kw(r):
    return r.get("keywords") or ""


def _creature(r):
    return decks._type(r) == "Creature"


# (key, name, explanation for beginners, test)
ARCHETYPES = [
    ("aggro", "Aggro", "Attack fast and cheap before your opponent can set up.",
     lambda r: _creature(r) and (r.get("cmc") or 0) <= 3 and ("Haste" in _kw(r) or _num(r.get("power")) >= 2)),
    ("voltron", "Voltron", "Suit up one creature with equipment and auras and win with it.",
     lambda r: "Equipment" in _tl(r) or ("Aura" in _tl(r) and "enchant creature" in _t(r))
     or "equipped creature" in _t(r) or "enchanted creature gets" in _t(r)),
    ("tokens", "Tokens (go wide)", "Make lots of small creatures and attack together.",
     lambda r: "create" in _t(r) and "token" in _t(r)),
    ("counters", "+1/+1 counters", "Grow creatures with counters – and multiply them.",
     lambda r: "+1/+1 counter" in _t(r) or "proliferate" in _t(r)),
    ("aristocrats", "Aristocrats", "Sacrifice your own creatures and profit from every death.",
     lambda r: "sacrifice" in _t(r) or ("dies" in _t(r) and "whenever" in _t(r))),
    ("graveyard", "Graveyard (reanimator)", "Fill your graveyard and bring cards back from it.",
     lambda r: "from your graveyard" in _t(r) or "mill" in _t(r) or "Flashback" in _kw(r)),
    ("spells", "Spellslinger", "Lots of instants and sorceries – every spell triggers something.",
     lambda r: decks._type(r) in ("Instant", "Sorcery") or "instant or sorcery" in _t(r)),
    ("artifacts", "Artifacts", "Collect artifacts that make each other stronger.",
     lambda r: "Artifact" in _tl(r) or "artifact you control" in _t(r) or "artifacts you control" in _t(r)),
    ("enchant", "Enchantments (enchantress)", "Play enchantments and draw cards for them.",
     lambda r: "Enchantment" in _tl(r) or "enchantment spell" in _t(r)),
    ("lifegain", "Lifegain", "Gain life and turn it into an advantage.",
     lambda r: "gain" in _t(r) and "life" in _t(r)),
    ("discard", "Discard", "Make your opponent discard until nothing is left.",
     lambda r: "discards" in _t(r) or ("discard" in _t(r) and ("opponent" in _t(r) or "target player" in _t(r)))),
    ("mill", "Mill", "Empty your opponent's library – whoever can't draw loses.",
     lambda r: "mill" in _t(r) or "into their graveyard" in _t(r)),
    ("control", "Control", "Answer everything (counter, destroy) and win late.",
     lambda r: "counter target" in _t(r) or "destroy all" in _t(r) or "destroy target" in _t(r)
     or "exile target" in _t(r)),
    ("ramp", "Ramp & big creatures", "Get lots of mana fast and play huge creatures.",
     lambda r: "search your library for a basic land" in _t(r) or ("add {" in _t(r) and decks._type(r) != "Land")
     or (_creature(r) and (r.get("cmc") or 0) >= 6)),
    ("landfall", "Landfall", "Every land you play triggers something.",
     lambda r: "landfall" in _t(r) or "whenever a land" in _t(r) or "play an additional land" in _t(r)),
    ("flyers", "Flyers", "Attack over your opponent's defenses.",
     lambda r: _creature(r) and "Flying" in _kw(r)),
    ("blink", "Blink", "Exile creatures briefly and return them – their effects happen again.",
     lambda r: "exile" in _t(r) and "return" in _t(r) and "battlefield" in _t(r)
     or "enters the battlefield" in _t(r) and _creature(r) and "when" in _t(r)),
    ("burn", "Burn", "Direct damage to creatures and opponents.",
     lambda r: "damage to any target" in _t(r) or "damage to each opponent" in _t(r)
     or ("deals" in _t(r) and "damage to target" in _t(r))),
    ("walkers", "Planeswalkers (superfriends)", "Protect several planeswalkers and use their abilities.",
     lambda r: "Planeswalker" in _tl(r) or "proliferate" in _t(r)),
]
BY_KEY = {k: (k, name, desc, test) for k, name, desc, test in ARCHETYPES}
_SAME_WORD = {"Discard"}   # the same word in German – tr("Discard") is the button "Verwerfen"


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _usable(pool, fmt):
    commander = fmt == "commander"
    return [r for r in pool if suggest.legal(r, "commander" if commander else fmt) and not suggest.is_basic(r)]


def _fits(r, colors):
    """Does the card fit the chosen colors? (Colorless always does.)"""
    if not colors:
        return True
    return set(r.get("color_identity") or "") <= set(colors)


def tribes(pool, n=4, at_least=8):
    """Most common creature types in the collection -> additional archetypes "Tribal: …"."""
    c = collections.Counter()
    for r in pool:
        if _creature(r) and "—" in _tl(r):
            for t in _tl(r).split(" // ")[0].split("—")[-1].split():
                c[t] += 1
    return [(t, k) for t, k in c.most_common(n) if k >= at_least]


def archetype(key):
    """(key, name, explanation, test) – also "tribe:Elf"."""
    if key.startswith("tribe:"):
        t = key[6:]
        return (key, tr(f"Tribal: {t}"), tr(f"Lots of {t} creatures that make each other stronger."),
                lambda r, t=t: t in _tl(r) or t.lower() in _t(r))
    return BY_KEY.get(key)


def overview(pool, fmt, colors=""):
    """For each archetype: how many of your cards fit (in the chosen colors) and which colors they
    are in. -> {"total", "per_color": {W: n …}, "archetypes": [{"key", "name", "desc", "count", "colors",
    "examples"}]}"""
    usable = [r for r in _usable(pool, fmt) if _fits(r, colors)]
    per_color = {c: sum(1 for r in _usable(pool, fmt) if c in (r.get("colors") or "")) for c in COLORS}
    per_color["C"] = sum(1 for r in _usable(pool, fmt) if not r.get("colors"))
    keys = [a[0] for a in ARCHETYPES] + [f"tribe:{t}" for t, _ in tribes(usable)]
    out = []
    for key in keys:
        _, name, desc, test = archetype(key)
        # with a color choice only cards of those colors count (colorless ones fit everywhere and would drown out all)
        hits = [r for r in usable if test(r) and (not colors or r.get("colors"))]
        if not hits:
            continue
        col = collections.Counter(c for r in hits for c in (r.get("colors") or ""))
        top = sorted(hits, key=lambda r: -suggest.quality(r))[:3]
        out.append({"key": key, "name": name if name in _SAME_WORD else tr(name), "desc": tr(desc),
                    "count": len(hits),
                    "colors": "".join(c for c, _ in col.most_common(3)), "examples": [r["name"] for r in top]})
    out.sort(key=lambda x: -x["count"])
    return {"total": len(usable), "per_color": per_color, "archetypes": out}


# ---------- Suggestions ----------
def _identity_ok(ident, colors):
    """Commander matching the color choice: exactly these colors (e.g. mono-green = only green commanders)."""
    return not colors or set(ident) == set(colors)


def commander_ideas(pool, colors="", key=None, top=5):
    """Commanders for color/style: your own first, then popular ones (EDHREC rank) from the card database that you
    don't have yet. -> [{"row", "owned_cmdr", "fit", "examples"}]"""
    test = archetype(key)[3] if key else None
    usable = _usable(pool, "commander")
    names = {r["name"] for r in pool}

    def score(c):
        ident = c.get("color_identity") or ""
        fit = [r for r in usable if r["name"] != c["name"] and suggest.in_identity(r, ident)
               and (test is None or test(r))]
        self_bonus = 4.0 if test is not None and test(c) else 0.0
        return sum(suggest.quality(r) for r in fit) + self_bonus + suggest.quality(c) * 3, fit

    cands = [c for c in usable if suggest._legendary_creature(c) and _identity_ok(c.get("color_identity") or "", colors)]
    if len(cands) < top and carddb.exists():  # too few of your own: add popular ones (offline from the database)
        seen = {c["name"] for c in cands}
        extra = carddb.search("", limit=400, sort="edhrec", no_tokens=True, one_per_name=True,
                              formats=["commander"])
        for r in extra:
            if r["name"] in seen or not suggest._legendary_creature(r):
                continue
            if _identity_ok(r.get("color_identity") or "", colors):
                cands.append(r)
                seen.add(r["name"])
            if len(cands) >= top * 4:
                break
    out = []
    for c in cands:
        s, fit = score(c)
        owned = c["name"] in names
        out.append({"row": c, "owned_cmdr": owned, "fit": len(fit), "score": s + (2.0 if owned else 0.0),
                    "examples": [r["name"] for r in sorted(fit, key=lambda r: -suggest.quality(r))[:3]]})
    out.sort(key=lambda x: -x["score"])
    return out[:top]


def sixty_ideas(pool, fmt, colors="", key=None, top=5):
    """60-card drafts for color/style. Without a color choice: the best one- and two-color combinations."""
    test = archetype(key)[3] if key else None
    name = archetype(key)[1] if key else ""
    usable = [r for r in _usable(pool, fmt) if decks._type(r) != "Land"]
    combos = [colors] if colors else list(COLORS) + [a + b for i, a in enumerate(COLORS) for b in COLORS[i + 1:]]
    out = []
    for combo in combos:
        fit = [r for r in usable if set(r.get("colors") or "") <= set(combo)]
        colored = [r for r in fit if r.get("colors")]
        if len(colored) < 12:
            continue
        n = sum(1 for r in colored if test(r)) if test else 0
        if test is not None and n < 6:
            continue
        ranked = sorted(fit, key=lambda r: -(suggest.quality(r) + (0.8 if test and test(r) else 0)
                                             + (0.25 if r.get("colors") else 0)))
        deck, colorless = [], 0
        for r in ranked:
            if not r.get("colors"):
                if colorless >= 6:
                    continue
                colorless += 1
            deck.append(r)
            if len(deck) >= 36:
                break
        score = sum(suggest.quality(r) for r in deck) + 0.2 * min(n, 24)
        out.append({"colors": combo, "theme": name, "cards": deck, "score": score, "count": len(fit), "theme_n": n})
    out.sort(key=lambda x: -x["score"])
    return out[:top]


def bonus(key):
    """Extra value for the rough draft: prefer cards of the chosen style."""
    if not key:
        return None
    test = archetype(key)[3]
    return lambda r: 1.5 if test(r) else 0.0


# ---------- Why does nothing come out? (diagnosis for the collection) ----------
FORMAT_NAMES = {"commander": "Commander", "standard": "Standard", "pioneer": "Pioneer", "modern": "Modern",
                "casual": "Casual"}


def diagnose(owned_ids, pool, fmt, colors=""):
    """Explains why the collection yields no suggestion (for format/colors) – and whether anything about the
    collection looks suspicious. owned_ids: {Scryfall ID: count} (your own cards), pool: your own cards as rows of
    the card database (one per name). -> [(level "warn"|"info", text)]"""
    out = []
    copies = sum(owned_ids.values())
    if owned_ids:
        known = carddb.cards_by_ids(set(owned_ids)) if carddb.exists() else {}
        unknown = [sid for sid in owned_ids if sid not in known]
        if len(unknown) >= max(5, len(owned_ids) * 0.05):
            n = sum(owned_ids[s] for s in unknown)
            out.append(("warn", tr(f"{n} cards of your collection ({len(unknown)} prints) are missing from the card database – it is probably outdated or the cards came in with wrong IDs (import). Update it under Settings → Card data.")))
    sel = [c for c in COLORS if c in (colors or "")]

    def in_colors(r):
        return not sel or set(r.get("colors") or "") <= set(sel)
    fmt_name = FORMAT_NAMES.get(fmt, fmt)
    colored = [r for r in pool if in_colors(r) and r.get("colors") and not suggest.is_basic(r)]
    names = len(colored)
    legal = [r for r in colored if suggest.legal(r, "commander" if fmt == "commander" else fmt)]
    copies_in = sum(r.get("_owned", 1) for r in colored)
    adj = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
    if len(sel) == 1:
        what = tr(f"{adj[sel[0]]} cards")
    elif sel:
        what = tr("Cards in ") + "".join(sel)
    else:
        what = tr("colored cards")
    what_dat = re.sub(r"e Karten$", "en Karten", what)   # German after "verschiedenen": weiße -> weißen Karten
    if copies_in and names <= copies_in / 3:
        out.append(("info", tr(f"You have {copies_in} {what}, but only {names} different ones – a deck counts each card only once (or at most 4×).")))
    if fmt not in decks._G.open_formats and names:
        if len(legal) < names / 3:
            out.append(("warn", tr(f"Of {names} different {what_dat} only {len(legal)} are legal in {fmt_name} – most come from older sets. Try “Casual” or an older format (Pioneer, Modern).")))
        else:
            out.append(("info", tr(f"{len(legal)} of {names} different {what_dat} are legal in {fmt_name}.")))
    usable = [r for r in legal if decks._type(r) != "Land"]
    need = 12 if fmt != "commander" else 40
    if names and len(usable) < need:
        out.append(("info", tr(f"A suggestion needs at least {need} different matching cards (without lands) – you have {len(usable)}.")))
    if not copies:
        out.append(("info", tr("Your collection is still empty.")))
    return out


def diagnose_html(owned_ids, pool, fmt, colors=""):
    """diagnose() as text for the status line (warnings highlighted)."""
    lines = []
    for level, text in diagnose(owned_ids, pool, fmt, colors):
        lines.append(f"<font color='#d9b46a'>⚠ {text}</font>" if level == "warn" else text)
    return "<br>".join(lines)
