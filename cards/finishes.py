"""Finishes (Foil, Holo, Reverse Holo, Etched …) and editions (1st Edition) – per game, decoupled from the rest.

Every copy (card in a session, collection entry) carries
    "foil"     price switch as before: foil price (eur_foil) yes/no – so prices, statistics, exports and
               trading (also with friends on older versions) keep working unchanged
    "finish"   which finish exactly (the game's key, e.g. "reverse") – missing on old entries: derived from
               "foil", nothing needs to be rewritten
    "edition"  e.g. "1st" (only where the printing has one), otherwise missing

The game says which finishes a printing has: games.<game>.finish_options(card) -> [{"key", "label",
"short", "foil"}] (first = base finish), editions(card) -> [{"key", "label", "short"}]. A new game with
its own variants (stamps, alt art …) simply brings its own lists.
"""
import games

_cache = {}


def _key(card):
    from collection.collection import scryfall_id
    return games.current().key, scryfall_id(card.get("id") or ""), tuple(card.get("finishes") or ())


def options(card):
    """Finishes of this printing (cached – needed while painting)."""
    k = _key(card)
    hit = _cache.get(k)
    if hit is None:
        try:
            hit = games.current().finish_options(card) or []
        except Exception:  # noqa: BLE001
            hit = []
        if not hit:
            hit = [{"key": "nonfoil", "label": "Non-Foil", "short": "N", "foil": False},
                   {"key": "foil", "label": "Foil", "short": "F", "foil": True}]
        _cache[k] = hit
    return hit


def editions(card):
    k = ("ed",) + _key(card)
    hit = _cache.get(k)
    if hit is None:
        try:
            hit = _cache[k] = games.current().editions(card) or []
        except Exception:  # noqa: BLE001
            hit = _cache[k] = []
    return hit


def current(entry):
    """Finish key of this copy – stored or derived from "foil"."""
    opts = options(entry)
    keys = [o["key"] for o in opts]
    f = entry.get("finish")
    if f in keys:
        return f
    if entry.get("foil"):
        foils = [o["key"] for o in opts if o["foil"]]
        for pref in ("reverse", "foil"):   # old "Foil" entries: Pokémon = Reverse Holo, Magic = Foil
            if pref in foils:
                return pref
        return foils[0] if foils else keys[0]
    plain = [o["key"] for o in opts if not o["foil"]]
    return plain[0] if plain else keys[0]


def option(entry):
    key = current(entry)
    return next(o for o in options(entry) if o["key"] == key)


def label(entry):
    """Finish as a word for display – "" for the plain one (Non-Foil, Normal). Yu-Gi-Oh!: the rarity."""
    o = option(entry)
    return "" if o["label"] in ("Non-Foil", "Normal") else o["label"]


def short(entry):
    return option(entry)["short"]


def apply(entry, key):
    """Set the finish (+ matching price switch). If the printing doesn't have it: do nothing. -> changed?"""
    o = next((o for o in options(entry) if o["key"] == key), None)
    if o is None:
        return False
    entry["finish"], entry["foil"] = key, bool(o["foil"])
    return True


def next_key(entry):
    """Next finish when cycling (F, button in the list): e.g. Normal → Holo → Reverse Holo → Normal."""
    keys = [o["key"] for o in options(entry)]
    i = keys.index(current(entry))
    return keys[(i + 1) % len(keys)]


def default_for(card, foil=None):
    """Finish of a newly counted card: foil=None -> base finish, otherwise the first matching one."""
    opts = options(card)
    if foil is None:
        return opts[0]["key"]
    return current(dict(card, foil=bool(foil), finish=None))


def edition_label(entry):
    e = entry.get("edition")
    if not e:
        return ""
    return next((x["label"] for x in editions(entry) if x["key"] == e), e)


def full_label(entry):
    """"Reverse Holo · 1st Edition" – everything special about this copy ("" if nothing)."""
    return " · ".join(x for x in (label(entry), edition_label(entry)) if x)


def clear_cache():
    _cache.clear()
