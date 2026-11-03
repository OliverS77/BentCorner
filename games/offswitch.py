"""Emergency switch per game: if a rights holder asks us to, a game can be switched off for everyone without a new
version. The switch lives in the signed update manifest (tools/publish_release.py, set with tools/owner.py):

    "games_off": {"<game>": {"de": "<reason>", "en": "<reason>"}}

The app reads it at every update check (net/updater.py → system/upkeep_ctl.py) and remembers the last state in
<data>/games-off.json – so a game stays off offline too, and comes back as soon as it is no longer in the list.
A switched-off game disappears from the game picker (games.choices: not ready), an open one is left for another game,
and none of its sources is asked any more (netpolite.BLOCKED). The user's own data (collection, decks, lists) stays
untouched. On the server, owner.py also stops the image mirror of that game (nginx answers 410).
"""
import json
import logging
import pathlib

from games import extra

log = logging.getLogger("booster")

FILE_NAME = "games-off.json"
# Everything a game's card data and images come from (not shared services like Cardmarket/TCGCSV): asked by nobody
# while the game is off – also not through a friend's library of that game.
HOSTS = {
    "lorcana": ("lorcanajson.org", "api.lorcana.ravensburger.com", "api.lorcast.com", "cards.lorcast.io"),
    "riftbound": ("api.riftcodex.com", "cmsassets.rgpub.io", "api.rifthunt.com"),
    **extra("OFFSWITCH_HOSTS", {}),   # private games (games/extras.py)
}
# Used when the manifest gives no reason – factual, no blame (wording 2026-10-26)
DEFAULT_REASON = {
    "de": "{game} ist vorübergehend nicht verfügbar – der Rechteinhaber hat uns gebeten, es abzuschalten. Kommt zurück, "
          "sobald es wieder erlaubt ist. Deine Sammlung bleibt erhalten.",
    "en": "{game} is temporarily unavailable – the rights holder asked us to switch it off. It will be back as soon as "
          "it's allowed again. Your collection is kept.",
}

_off = None   # {key: {"de", "en"}} – loaded once, then kept up to date by apply()
_blocked = set()


def _file(home=None):
    if home is None:
        from system import datahome
        home = datahome.HOME
    return pathlib.Path(home) / FILE_NAME


def _clean(games_off):
    """Manifest value -> {key: {"de", "en"}}; only known games, Magic never (the fallback game must stay)."""
    import games
    known = {k for k, _n, _r in games.GAMES} - {games.DEFAULT}
    out = {}
    if not isinstance(games_off, dict):
        return out
    for key, why in games_off.items():
        if key not in known:
            continue
        if isinstance(why, str):
            why = {"de": why, "en": why}
        why = why if isinstance(why, dict) else {}
        out[key] = {lang: str(why.get(lang) or "")[:400] for lang in ("de", "en")}
    return out


def _block(keys):
    """netpolite.BLOCKED follows the switch: hosts of switched-off games in, of switched-on ones out again – only the
    ones this switch blocked itself (a game unlocked only locally blocks its image hosts on its own, games.current)."""
    from net import netpolite
    want = {h for k in keys for h in HOSTS.get(k, ())}
    netpolite.unblock_hosts(_blocked - want)
    mine = {h for h in want - _blocked if h not in netpolite.BLOCKED}
    netpolite.block_hosts(mine)
    keep = (_blocked & want) | mine
    _blocked.clear()
    _blocked.update(keep)


def off(home=None):
    """{key: {"de", "en"}} of the switched-off games (as last seen in the manifest)."""
    global _off
    if home is not None:   # explicit folder (games.active_key with its own settings file, tests): not cached
        try:
            return _clean(json.loads(_file(home).read_text("utf-8")))
        except (OSError, ValueError):
            return {}
    if _off is None:
        try:
            _off = _clean(json.loads(_file().read_text("utf-8")))
        except (OSError, ValueError, ImportError):
            _off = {}
        _block(_off)
    return _off


def is_off(key, home=None):
    return key in off(home)


def reason(key, lang=None):
    """The text users see: reason from the manifest, otherwise the default sentence."""
    import games
    if lang is None:
        from system import i18n
        lang = "de" if i18n.LANG == "de" else "en"
    why = (off().get(key) or {}).get(lang) or DEFAULT_REASON.get(lang, DEFAULT_REASON["en"])
    return why.replace("{game}", games.nick_of(key))


def apply(games_off, home=None):
    """New state from the manifest. -> (newly switched off, switched on again) – both lists of game keys."""
    global _off
    new = _clean(games_off)
    old = off(home) if home is not None else off()
    went_off = [k for k in new if k not in old]
    back = [k for k in old if k not in new]
    if new != old:
        try:
            f = _file(home)
            if new:
                f.write_text(json.dumps(new, ensure_ascii=False, indent=1), "utf-8")
            else:
                f.unlink(missing_ok=True)
        except OSError as e:
            log.warning("games-off.json not written: %s", e)
        log.info("Emergency switch: off %s, back on %s", went_off, back)
    if home is None:
        _off = new
        _block(new)
    return went_off, back
