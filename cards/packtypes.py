"""Pack types (Play Booster, Collector Booster, Commander deck, promo …) and session tags.

Every pack in a session has a type. Per type you can set whether it "counts as a pack" in the statistics
(avg. value per pack, pack values, number of packs) – the card value always counts toward the total. Custom types can
be created (settings["pack_types"]). Tags are attached to the session (e.g. "Fair", "Shop in town").
"""
DEFAULT = "booster"
DEFAULT_TYPES = [
    {"key": "booster", "name": "Booster", "counts": True},
    {"key": "play", "name": "Play Booster", "counts": True},
    {"key": "collector", "name": "Collector Booster", "counts": True},
    {"key": "set", "name": "Set Booster", "counts": True},
    {"key": "draft", "name": "Draft Booster", "counts": True},
    {"key": "jumpstart", "name": "Jumpstart Booster", "counts": True},
    {"key": "prerelease", "name": "Prerelease Pack", "counts": True},
    {"key": "secretlair", "name": "Secret Lair", "counts": False},
    {"key": "commander", "name": "Commander-Deck (Precon)", "counts": False},
    {"key": "deck", "name": "Anderes Deck", "counts": False},
    {"key": "promo", "name": "Promo / Beilage", "counts": False},
    {"key": "other", "name": "Sonstiges", "counts": False},
    {"key": "trade", "name": "Tausch", "counts": False},          # single-card sessions (trades with friends)
    {"key": "purchase", "name": "Einzelkauf", "counts": False},   # … and purchased single cards
]
SINGLES = ("trade", "purchase")


def types(settings):
    """All types: the game's built-in ones (with any changed settings) + custom ones, in a fixed order."""
    import games
    saved = {t["key"]: t for t in settings.get("pack_types") or []}
    out = []
    for t in games.current().pack_types or DEFAULT_TYPES:
        s = saved.pop(t["key"], {})
        out.append({"key": t["key"], "name": s.get("name") or t["name"], "counts": s.get("counts", t["counts"]),
                    "builtin": True})
    builtin_elsewhere = set()   # don't show other games' built-in types as "custom"
    for k, _n, ready in games.GAMES:
        if ready:
            builtin_elsewhere |= {t["key"] for t in games.load(k).pack_types or DEFAULT_TYPES}
    for t in saved.values():
        if t.get("name") and t["key"] not in builtin_elsewhere:
            out.append({"key": t["key"], "name": t["name"], "counts": bool(t.get("counts", True)), "builtin": False})
    return out


def save_types(settings, items):
    settings["pack_types"] = [{"key": t["key"], "name": t["name"], "counts": bool(t["counts"])} for t in items]


def by_key(settings):
    return {t["key"]: t for t in types(settings)}


def name(settings, key):
    if key == "import":
        from system.i18n import tr
        return tr("Import")
    t = by_key(settings).get(key or DEFAULT)
    return t["name"] if t else (key or DEFAULT)


def counts(settings, key):
    t = by_key(settings).get(key or DEFAULT)
    return True if t is None else t["counts"]


def new_key(settings, label):
    """Key for a custom type, built from its name."""
    import re
    base = "u_" + (re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "typ")
    keys = {t["key"] for t in types(settings)}
    key, n = base, 2
    while key in keys:
        key, n = f"{base}_{n}", n + 1
    return key


def all_tags(sessions):
    """All used tags (for suggestions), most frequent first."""
    count = {}
    for s in sessions:
        for t in (s.get("info") or {}).get("tags") or []:
            count[t] = count.get(t, 0) + 1
    return [t for t, _ in sorted(count.items(), key=lambda kv: (-kv[1], kv[0].lower()))]
