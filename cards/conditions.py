"""Condition of a copy – as on Cardmarket or TCGplayer, the same for all games.

Every copy (card in a session, collection entry) carries
    "cond"       key of the fine Cardmarket scale (KEYS below) or "graded" / "other" – missing on old
                 entries: counts as Near Mint (prices are always Near Mint prices anyway)
    "grade_by"   only for "graded": PSA, BGS, CGC …
    "grade"      only for "graded": grade as text ("10", "9.5")
    "cond_note"  only for "other": free text (e.g. "Proxy", "signed")

The scale shown is that of the marketplace you use (Settings → Condition, default: same as the shop links –
euro/German Cardmarket, otherwise TCGplayer). TCGplayer has only 5 grades; the mapping is rough, as usual:
    Cardmarket  MT  NM  EX  GD  LP  PL  PO
    TCGplayer   NM  NM  LP  LP  MP  HP  DMG
Entering in TCGplayer grades stores the matching Cardmarket grade (NM→NM, LP→EX, MP→LP, HP→PL,
DMG→PO) – so everything stays on one scale and can be sorted.
"""

KEYS = ("mint", "near_mint", "excellent", "good", "light_played", "played", "poor")   # best → worst
DEFAULT = "near_mint"
GRADERS = ("PSA", "BGS", "CGC", "SGC", "TAG", "ACE", "Beckett")

CARDMARKET = [("mint", "MT", "Mint"), ("near_mint", "NM", "Near Mint"), ("excellent", "EX", "Excellent"),
              ("good", "GD", "Good"), ("light_played", "LP", "Light Played"), ("played", "PL", "Played"),
              ("poor", "PO", "Poor")]
TCGPLAYER = [("near_mint", "NM", "Near Mint"), ("excellent", "LP", "Lightly Played"),
             ("light_played", "MP", "Moderately Played"), ("played", "HP", "Heavily Played"),
             ("poor", "DMG", "Damaged")]
# fine grade -> grade on the TCGplayer scale
_TO_TCG = {"mint": "near_mint", "near_mint": "near_mint", "excellent": "excellent", "good": "excellent",
           "light_played": "light_played", "played": "played", "poor": "poor"}
SCALES = (("auto", "Wie mein Haupt-Shop"), ("cardmarket", "Cardmarket (MT · NM · EX · GD · LP · PL · PO)"),
          ("tcgplayer", "TCGplayer (NM · LP · MP · HP · DMG)"))

_settings = {}


def bind(settings):
    """Remember the app settings (scale, default when scanning)."""
    global _settings
    _settings = settings


_scale_memo = {}


def scale_key(settings=None):
    s = (settings if settings is not None else _settings) or {}
    want = s.get("cond_scale") or "auto"
    if want in ("cardmarket", "tcgplayer"):
        return want
    # "Like my shop": main shop from the settings (otherwise by language/currency) – asked 4–5 times per library row,
    # so remembered by exactly what shoplinks.primary looks at
    from system import i18n
    k = (s.get("main_shop"), tuple(s.get("shops_off") or ()), s.get("currency", "EUR"), i18n.LANG)
    hit = _scale_memo.get(k)
    if hit is None:
        from cards import shoplinks
        hit = _scale_memo[k] = shoplinks.primary(s)
    return hit


def scale(settings=None):
    """[(key, abbreviation, name)] of the displayed scale, best → worst."""
    return CARDMARKET if scale_key(settings) == "cardmarket" else TCGPLAYER


def default():
    """Condition of newly scanned/added cards (Settings → Condition; default Near Mint)."""
    d = (_settings or {}).get("cond_default") or DEFAULT
    return d if d in KEYS else DEFAULT


def of(entry):
    """Stored condition – old entries without one count as Near Mint."""
    c = (entry or {}).get("cond") or DEFAULT
    return c if c in KEYS or c in ("graded", "other") else DEFAULT


def _shown(c):
    """Fine grade -> grade of the displayed scale (TCGplayer merges some)."""
    return _TO_TCG.get(c, c) if scale_key() == "tcgplayer" else c


def short(entry):
    """"NM", "EX", "PSA 10", "Proxy" … – abbreviation in the user's scale."""
    c = of(entry)
    if c == "graded":
        return " ".join(x for x in ((entry.get("grade_by") or "Graded"), str(entry.get("grade") or "")) if x)
    if c == "other":
        note = (entry.get("cond_note") or "").strip()
        return note[:12] if note else "Other"
    k = _shown(c)
    return next((s for key, s, _ in scale() if key == k), "NM")


def name(entry):
    c = of(entry)
    if c in ("graded", "other"):
        return short(entry)
    k = _shown(c)
    return next((n for key, _, n in scale() if key == k), "Near Mint")


def rank(entry):
    """For sorting: 0 = best condition … 6 = Poor; Graded before everything, Other at the very end."""
    c = of(entry)
    if c == "graded":
        return -1
    if c == "other":
        return 9
    return KEYS.index(c)


def is_plain(entry):
    """Near Mint (or, on the TCGplayer scale, anything shown as NM) – needs no chip on the tile."""
    c = of(entry)
    return c in KEYS and _shown(c) == _shown(DEFAULT) and (c != "mint" or scale_key() == "tcgplayer")


def next_key(entry):
    """Cycling (button in the scan list): next grade of the displayed scale, wrapping around after the last.
    Graded/Other start over at the default."""
    keys = [k for k, _, _ in scale()]
    c = of(entry)
    c = _shown(c) if c in KEYS else None
    if c not in keys:
        return default() if _shown(default()) in keys else keys[0]
    return keys[(keys.index(c) + 1) % len(keys)]


def cycle_key(entry):
    """Cycling in the detail view: all grades of the scale, then Graded, then Other, then wrap around."""
    keys = [k for k, _, _ in scale()] + ["graded", "other"]
    c = shown_key(entry)
    return keys[(keys.index(c) + 1) % len(keys)] if c in keys else keys[0]


def apply(entry, key, grade_by=None, grade=None, note=None):
    """Set the condition (clears the fields of the other kinds). -> changed?"""
    before = (entry.get("cond"), entry.get("grade_by"), entry.get("grade"), entry.get("cond_note"))
    for k in ("grade_by", "grade", "cond_note"):
        entry.pop(k, None)
    if key == "graded":
        entry["cond"] = "graded"
        entry["grade_by"] = (grade_by or "PSA").strip()[:12]
        entry["grade"] = str(grade or "").strip()[:6]
    elif key == "other":
        entry["cond"] = "other"
        entry["cond_note"] = (note or "").strip()[:40]
    else:
        entry["cond"] = key if key in KEYS else DEFAULT
    return before != (entry.get("cond"), entry.get("grade_by"), entry.get("grade"), entry.get("cond_note"))


def fields(entry):
    """The condition fields of an entry (for copying session → collection)."""
    return {k: entry.get(k) for k in ("cond", "grade_by", "grade", "cond_note") if entry.get(k) not in (None, "")}


def ident(entry):
    """What counts when merging identical copies."""
    c = of(entry)
    if c == "graded":
        return f"graded:{entry.get('grade_by') or ''}:{entry.get('grade') or ''}"
    if c == "other":
        return "other:" + (entry.get("cond_note") or "").strip().lower()
    return c


def shown_key(entry):
    """Key under which the selection list shows the condition (TCGplayer: merged grade)."""
    c = of(entry)
    return c if c in ("graded", "other") else _shown(c)


def choices(include_special=True):
    """For selection lists: [(key, text)] of the displayed scale (+ Graded, Other)."""
    out = [(k, f"{s} · {n}") for k, s, n in scale()]
    if include_special:
        out += [("graded", "Graded (PSA, BGS …)"), ("other", "Other")]
    return out


# ---------- Import / Export ----------
_IMPORT = {"mint": "mint", "mt": "mint", "m": "mint",
           "near mint": "near_mint", "near_mint": "near_mint", "nm": "near_mint", "nm/m": "near_mint",
           "excellent": "excellent", "ex": "excellent", "lightly played": "excellent", "slightly played": "excellent",
           "sp": "excellent",
           "good": "good", "gd": "good",
           "light played": "light_played", "light_played": "light_played", "moderately played": "light_played",
           "mp": "light_played", "played": "played", "pl": "played", "heavily played": "played", "hp": "played",
           "poor": "poor", "po": "poor", "damaged": "poor", "dmg": "poor", "dm": "poor"}


def from_text(text, source=""):
    """Condition from a CSV column (ManaBox, Moxfield, Cardmarket, TCGplayer …) -> key or None.
    "LP" is ambiguous: Lightly Played (= EX) on TCGplayer/Moxfield, Light Played on Cardmarket/ManaBox."""
    t = (text or "").strip().lower().replace("-", " ")
    if not t:
        return None
    if t == "lp":
        return "light_played" if source in ("cardmarket", "manabox") else "excellent"
    return _IMPORT.get(t)


def manabox(entry):
    c = of(entry)
    return c if c in KEYS else "near_mint"


_MOX = {"mint": "Mint", "near_mint": "Near Mint", "excellent": "Lightly Played", "good": "Lightly Played",
        "light_played": "Moderately Played", "played": "Heavily Played", "poor": "Damaged"}


def moxfield(entry):
    return _MOX.get(of(entry), "Near Mint")
