"""Card games: Bent°Corner doesn't know a game directly, only through a game description (games.<game>).

Shared by all games: collection, sessions, lists, trades, alerts, UI. Different per game – and therefore in the
description: data source (card database, sets, images), prices, card fields, search, deck rules and formats,
recognition while scanning, marketplaces.

The active game is stored in the settings ("game", default Magic). Switching happens at startup (like the language:
restart), because every game has its own data:
    Magic        data/card-data, data/card-images, data/recognition, data/my-data   (as before – nothing moves)
    others       data/games/<game>/card-data …, data/games/<game>/my-data
"""
import json
import pathlib

from . import base

# Private additions (games/extras.py – not part of the public source): further games and what belongs to them
# (sources, network rules, notices …). Every part asks extra() for its share; without the module all of it is empty.
try:
    from . import extras as _extras
except ImportError:
    _extras = None


def extra(name, default=None):
    """A part of the private additions (games/extras.py), or `default` – the public program has none."""
    return getattr(_extras, name, default) if _extras is not None else default


def _with_extras(games):
    """The public games plus the private ones, each at its place ("after": key)."""
    out = list(games)
    for after, entry in extra("GAMES", ()):
        i = next((n + 1 for n, g in enumerate(out) if g[0] == after), len(out))
        out.insert(i, entry)
    return tuple(out)


# Order = order on the start screen. ready = a working game description exists.
GAMES = _with_extras((
    ("mtg", "Magic: The Gathering", True),
    ("pokemon", "Pokémon TCG", True),
    ("yugioh", "Yu-Gi-Oh! TCG", True),
    ("lorcana", "Disney Lorcana", True),
    ("riftbound", "Riftbound", False),
))
DEFAULT = "mtg"
# Withdrawn games: not even unlocked on this PC ("unlock_games") – a saved active game falls back to Magic, its
# collection (data/games/<game>/my-data) stays untouched.
WITHDRAWN = set(extra("WITHDRAWN", set()))
MIX_ENABLED = False   # mix several games (library) – off for now: always exactly one game (code kept for later)


def unlocked(settings_file=None):
    """Games unlocked only on this PC ("unlock_games" in settings.json, no switch in the UI): a game that isn't
    released yet can be chosen there – without card images (Game.images_off) and without anything published."""
    try:
        if settings_file is None:
            from system import datahome
            settings_file = pathlib.Path(datahome.HOME) / "settings.json"
        keys = json.loads(pathlib.Path(settings_file).read_text("utf-8")).get("unlock_games") or []
    except (OSError, ValueError, ImportError):
        return set()
    return {k for k, _n, _r in GAMES if k in keys and k not in WITHDRAWN}


def released(key):
    return any(k == key and r for k, _, r in GAMES)


def choices():
    """For the start screen: [{key, name, ready, off}] – ready also for a game unlocked on this PC; a game switched off
    by the emergency switch (offswitch.py) is never ready, "off" = True."""
    from games import offswitch
    local, gone = unlocked(), offswitch.off()
    return [{"key": k, "name": n, "ready": (r or k in local) and k not in gone, "off": k in gone} for k, n, r in GAMES]


def active_key(settings_file=None):
    """Active game from the settings – unknown, not (yet) ready or switched off (offswitch.py): Magic."""
    from games import offswitch
    key = DEFAULT
    try:
        if settings_file is None:
            from system import datahome
            settings_file = pathlib.Path(datahome.HOME) / "settings.json"
        key = json.loads(pathlib.Path(settings_file).read_text("utf-8")).get("game") or DEFAULT
    except (OSError, ValueError, ImportError):
        key = DEFAULT
    if settings_file is not None and offswitch.is_off(key, home=pathlib.Path(settings_file).parent):
        return DEFAULT
    return key if released(key) or key in unlocked(settings_file) else DEFAULT


def folders(key, data_dir):
    """Folders of a game: {"ref", "images", "recog", "mine"} – Magic as before, others under data/games/<game>."""
    data_dir = pathlib.Path(data_dir)
    root = data_dir if key == DEFAULT else data_dir / "games" / key
    return {"ref": root / "card-data", "images": root / "card-images", "recog": root / "recognition",
            "mine": root / "my-data"}


SHORT = {"mtg": "MTG", "pokemon": "PKM", "yugioh": "YGO", "lorcana": "LOR", "riftbound": "RB", **extra("SHORT", {})}


NICK = {"mtg": "Magic", "pokemon": "Pokémon", "yugioh": "Yu-Gi-Oh!", "lorcana": "Lorcana", "riftbound": "Riftbound",
        **extra("NICK", {})}


def nick_of(key):
    """Short name for running text ("Annas Pokémon-Bibliothek")."""
    return NICK.get(key) or name_of(key)


def name_of(key):
    return next((n for k, n, _ in GAMES if k == key), key)


def shown(settings):
    """Which games are currently shown: without "mix" only the active one, otherwise the enabled ones (the active one
    always included, only ready games)."""
    act = current().key
    if not settings.get("games_mix") or not MIX_ENABLED:
        return [act]
    on = set(settings.get("games_on") or []) | {act}
    return [k for k, _, r in GAMES if r and k in on]


def label(settings):
    """Text on the game button: "Magic", "Magic + Pokémon", "Alle Spiele"."""
    keys = shown(settings)
    ready = [k for k, _, r in GAMES if r]
    if len(keys) > 1 and len(keys) == len(ready):
        return "Alle Spiele"
    return " + ".join(nick_of(k) for k in keys)


def current_key():
    """Key of the open game ("mtg", "pokemon" …)."""
    return current().key


def mine(key, *parts):
    """A game's personal data folder (my-data) or a file in it – also for a game other than the open one:
    mine("pokemon", "binders.json")."""
    from scanner.common import DATA
    return folders(key, DATA)["mine"].joinpath(*parts)


def collection_items(key):
    """Collection of another game – read-only (for the mixed library). [] if there is none."""
    f = mine(key, "collection.json")
    try:
        return json.loads(f.read_text("utf-8")).get("items") or []
    except (OSError, ValueError):
        return []


_current = None


def current():
    """Description of the active game (base.Game)."""
    global _current
    if _current is None:
        _current = load(active_key())
        if not released(_current.key):   # unlocked only on this PC: no image requests at all
            _current.images_off = True
            from net import netpolite
            netpolite.block_hosts(_current.image_hosts)
    return _current


def load(key):
    if key == "mtg":
        from . import mtg
        return mtg.GAME
    if key == "pokemon":
        from . import pokemon
        return pokemon.GAME
    if key == "yugioh":
        from . import yugioh
        return yugioh.GAME
    if key == "lorcana":
        from . import lorcana
        return lorcana.GAME
    loader = extra("LOADERS", {}).get(key)   # a private game (games/extras.py)
    if loader is not None:
        try:
            return loader()
        except ImportError:   # its description isn't part of this program
            raise KeyError(key) from None
    raise KeyError(key)
