"""Emergency switch per game: if a rights holder asks us to, a game can be switched off for everyone without a new
version. The switch lives in the signed update manifest (tools/publish_release.py, set with tools/owner.py):

    "games_off": {"<game>": {"de": "<reason>", "en": "<reason>"}}

The app reads it at every update check (net/updater.py → system/upkeep_ctl.py) and remembers the last state in
<data>/games-off.json – so a game stays off offline too, and comes back as soon as it is no longer in the list.
A switched-off game disappears from the game picker (games.choices: not ready), an open one is left for another game,
and none of its sources is asked any more (netpolite.BLOCKED) – nor its paths on our own server (mirror, data pack,
prices: netpolite.BLOCKED_OWN), so there is no way round it, not even the fallback when the mirror has a fault. The
user's own data (collection, decks, lists) stays untouched. On the server, owner.py also stops the image mirror of that
game (nginx answers 410 – the app takes a 410 as "switched off" too: no fallback, remembered).

Only the images of a game (Oliver/legal 16.11.2026): "images_off" in the manifest, same format, remembered in
<data>/images-off.json – data, prices and the collection keep working, Magic too may lose its images. A game that is
off or has its images off: its image hosts and image paths are blocked, and its image cache on disk is LOCKED (the
folders get the suffix ".off" – nothing is deleted; switched on again, everything is back without a new download).
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
    "pokemon": ("api.tcgdex.net", "assets.tcgdex.net", "images.pokemontcg.io"),
    "yugioh": ("db.ygoprodeck.com", "images.ygoprodeck.com"),
    "lorcana": ("lorcanajson.org", "api.lorcana.ravensburger.com", "api.lorcast.com", "cards.lorcast.io"),
    "riftbound": ("api.riftcodex.com", "cmsassets.rgpub.io", "api.rifthunt.com"),
    **extra("OFFSWITCH_HOSTS", {}),   # private games (games/extras.py)
}
# Only the card images of a game (images_off, and part of games_off): foreign hosts and paths on our own server
IMAGE_HOSTS = {
    "mtg": ("cards.scryfall.io",),
    "pokemon": ("assets.tcgdex.net", "images.pokemontcg.io"),
    "yugioh": ("images.ygoprodeck.com",),
    "lorcana": ("api.lorcana.ravensburger.com", "cards.lorcast.io"),
    "riftbound": ("cmsassets.rgpub.io",),
    **extra("OFFSWITCH_IMAGE_HOSTS", {}),
}
IMAGE_PATHS = {
    "pokemon": ("/dl/tcgdex/",),
    "lorcana": ("/dl/lorcana/",),
    "yugioh": ("/dl/packs/yugioh/img/",),
    **extra("OFFSWITCH_IMAGE_PATHS", {}),
}


def own_paths(key):
    """Everything of a game on our own server: its image mirror, its data pack, its prices."""
    return tuple(IMAGE_PATHS.get(key, ())) + (f"/dl/packs/{key}/", f"/dl/prices/{key}")


IMAGES_FILE = "images-off.json"
# shown at the placeholder when the manifest gives no reason – no claim why (legal 16.11.2026)
IMAGES_REASON = {
    "de": "Bilder von {game} sind vorübergehend abgeschaltet. Deine Sammlung und alle Daten bleiben.",
    "en": "{game} images are temporarily switched off. Your collection and all data stay.",
}
# Used when the manifest gives no reason – factual, no blame (wording 2026-10-26)
DEFAULT_REASON = {
    "de": "{game} ist vorübergehend nicht verfügbar – der Rechteinhaber hat uns gebeten, es abzuschalten. Kommt zurück, "
          "sobald es wieder erlaubt ist. Deine Sammlung bleibt erhalten.",
    "en": "{game} is temporarily unavailable – the rights holder asked us to switch it off. It will be back as soon as "
          "it's allowed again. Your collection is kept.",
}

_off = None   # {key: {"de", "en"}} – loaded once, then kept up to date by apply()
_img_off = None   # the same for images_off (images-off.json)
_blocked = set()
_blocked_own = set()


def _file(home=None, name=FILE_NAME):
    if home is None:
        from system import datahome
        home = datahome.HOME
    return pathlib.Path(home) / name


def _clean(games_off, magic=False):
    """Manifest value -> {key: {"de", "en"}}; only known games, Magic never (the fallback game must stay) – except
    for its images (magic=True, images_off)."""
    import games
    known = {k for k, _n, _r in games.GAMES} - ({games.DEFAULT} if not magic else set())
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


def _block(keys, image_keys=()):
    """netpolite.BLOCKED/BLOCKED_OWN follow the switches: hosts and own paths of switched-off games (and the image hosts
    and paths of games with their images off) in, of switched-on ones out again – only the ones this switch blocked
    itself (a game unlocked only locally or withdrawn blocks its own, games.current/block_withdrawn)."""
    from net import netpolite
    keys, image_keys = set(keys), set(image_keys) | set(keys)
    want = {h.lower() for k in keys for h in HOSTS.get(k, ())} | \
           {h.lower() for k in image_keys for h in IMAGE_HOSTS.get(k, ())}
    netpolite.unblock_hosts(_blocked - want)
    mine = {h for h in want - _blocked if h not in netpolite.BLOCKED}
    netpolite.block_hosts(mine)
    keep = (_blocked & want) | mine
    _blocked.clear()
    _blocked.update(keep)
    want_own = {p for k in keys for p in own_paths(k)} | {p for k in image_keys for p in IMAGE_PATHS.get(k, ())}
    if hasattr(netpolite, "unblock_own_paths"):
        netpolite.unblock_own_paths(_blocked_own - want_own)
        mine = {p for p in want_own - _blocked_own if p not in netpolite.BLOCKED_OWN}
        netpolite.block_own_paths(mine)
        keep = (_blocked_own & want_own) | mine
        _blocked_own.clear()
        _blocked_own.update(keep)


def _reblock():
    _block(_off or {}, _img_off or {})


# ---------- the image cache of a game is locked, not deleted ----------
LOCK_SUFFIX = ".off"


def _image_dirs(key, home=None):
    """The folders holding a game's card images on disk: card-images, and the grid/detail copies in card-data."""
    import games
    if home is None:
        from system import datahome
        home = datahome.HOME
    f = games.folders(key, pathlib.Path(home) / "data")
    return [f["images"], f["ref"] / "thumbs", f["ref"] / "large"]


def _move_into(src, dst):
    """Files of src that dst doesn't have yet go there; src is removed when empty (unlocking while new files came)."""
    import os
    import shutil
    for p in sorted(src.rglob("*"), reverse=True):
        q = dst / p.relative_to(src)
        if p.is_file():
            if not q.exists():
                q.parent.mkdir(parents=True, exist_ok=True)
                os.replace(p, q)
            else:
                p.unlink(missing_ok=True)
        elif p.is_dir():
            try:
                p.rmdir()
            except OSError:
                pass
    shutil.rmtree(src, ignore_errors=True)


def lock_images(locked, home=None):
    """Every game in `locked`: its image folders renamed to <name>.off (nobody finds a file in them – not the image
    provider, not Qt reading a file directly, not a share image); every other game: renamed back. A folder in use
    (Windows) is retried at the next start. -> [(folder, error)] that couldn't be done now"""
    import games
    import os
    failed = []
    for key in {k for k, _n, _r in games.GAMES} | set(extra("OFFSWITCH_HOSTS", {})):
        for d in _image_dirs(key, home):
            off = d.with_name(d.name + LOCK_SUFFIX)
            try:
                if key in locked:
                    if d.exists() and not off.exists():
                        os.replace(d, off)
                    elif d.exists():   # locked already, new files meanwhile: into the locked folder
                        _move_into(d, off)
                elif off.exists():
                    if not d.exists():
                        os.replace(off, d)
                    else:
                        _move_into(off, d)
            except OSError as e:
                failed.append((d, e))
                log.warning("Image folder %s not %slocked now: %s", d, "" if key in locked else "un", e)
    return failed


def images_locked(key, home=None):
    """Are this game's images off (images_off or the whole game off)?"""
    return key in images_off(home) or key in off(home)


def images_off(home=None):
    """{key: {"de", "en"}} of the games whose images are switched off (as last seen in the manifest)."""
    global _img_off
    if home is not None:
        try:
            return _clean(json.loads(_file(home, IMAGES_FILE).read_text("utf-8")), magic=True)
        except (OSError, ValueError):
            return {}
    if _img_off is None:
        try:
            _img_off = _clean(json.loads(_file(name=IMAGES_FILE).read_text("utf-8")), magic=True)
        except (OSError, ValueError, ImportError):
            _img_off = {}
        off()
        _reblock()
    return _img_off


def image_reason(key, lang=None):
    """The note at the placeholder: the manifest's reason, otherwise the plain default (no claim why)."""
    import games
    if lang is None:
        from system import i18n
        lang = "de" if i18n.LANG == "de" else "en"
    why = (images_off().get(key) or {}).get(lang) or IMAGES_REASON.get(lang, IMAGES_REASON["en"])
    return why.replace("{game}", games.nick_of(key))


def startup():
    """At start (before any image is shown): blocks and the cache lock follow the remembered state."""
    try:
        locked = set(off()) | set(images_off())
        lock_images(locked)
    except Exception:  # noqa: BLE001 – a switch must never stop the start
        log.exception("Emergency switch at start")


def apply_images(images_off_value, home=None):
    """New images_off state from the manifest. -> (newly off, on again)"""
    global _img_off
    new = _clean(images_off_value, magic=True)
    old = images_off(home)
    went_off = [k for k in new if k not in old]
    back = [k for k in old if k not in new]
    if new != old:
        try:
            f = _file(home, IMAGES_FILE)
            if new:
                f.write_text(json.dumps(new, ensure_ascii=False, indent=1), "utf-8")
            else:
                f.unlink(missing_ok=True)
        except OSError as e:
            log.warning("images-off.json not written: %s", e)
        log.info("Emergency switch (images): off %s, back on %s", went_off, back)
    if home is None:
        _img_off = new
        _reblock()
        if went_off or back:
            lock_images(set(off()) | set(new))
    return went_off, back


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
        _block(_off, _img_off or {})
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
        _block(new, images_off())
        if went_off or back:
            lock_images(set(new) | set(images_off()))
    return went_off, back
