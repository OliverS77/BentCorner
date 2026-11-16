"""Data packs: what not everyone needs isn't in the .exe but comes from our own server on demand.

    mtg       Magic: index of all cards (fingerprints-all.npz) + names in all languages (langs.tsv.gz, from
              MTGJSON, MIT) – the card database itself still comes directly from Scryfall (their rules forbid
              redistributing it); carddb attaches the languages to it
    yugioh    Yu-Gi-Oh!: card database (YGOPRODeck, tools/build_yugioh_db.py) + index of all cards; the images
              live individually under packs/yugioh/img/ and img-small/ (self-hosted, as YGOPRODeck requires)
    pokemon   Pokémon: card database (TCGdex, MIT) + index of all cards + cm_fix.json (marketplace corrections,
              tools/fix_pokemon_market.py)

On the server: <BASE_URL>/packs/packs.json (+ .sig, signed with the release key like the update manifest)
and per pack the files under <BASE_URL>/packs/<pack>/<file>. Publishing: tools/publish_packs.py.
In the data folder they end up under data/packs/<pack>/ – carddb and fingerprint look there first (then in the
.exe, or in models/ during development). Downloaded in chunks and resumable (<file>.part), then checksummed.
What belongs to the selected games gets downloaded (setup, game switch).
"""
import hashlib
import importlib.util
import json
import logging
import pathlib

from cards import datakeys
from scanner.common import DATA
from system.i18n import tr

log = logging.getLogger(__name__)
PACKS = {
    # extra cardback.npy: the card back's fingerprint (scanner/fingerprint.py drops index entries that only show it);
    # without it nothing is filtered, so "installed" doesn't wait for it
    # extra fingerprints-add.npz (Magic, Yu-Gi-Oh!): the new cards since the main index (docs/FP-ADD-FORMAT.md) – only
    # used when it belongs to the main index next to it (scanner/fingerprint.Index), never needed for "installed"
    "mtg": {"name": "Magic-Daten", "dir": "mtg", "files": ["fingerprints-all.npz", "langs.tsv.gz", "setnames.json"],
            "extra": ["cardback.npy", "fingerprints-add.npz"]},
    "pokemon": {"name": "Pokémon-Daten", "dir": "pokemon", "files": ["cards.sqlite", "fingerprints-all.npz", "cm_fix.json",
                                                            "setnames.json"]},
    # extra: comes along (packs.json lists it), but "installed" doesn't depend on it – ygo-locale.sqlite (OCG/Asia/
    # Spanish prints, CC BY-SA, own file on purpose) is merged locally by games/yugioh.merge_extra when it is there
    "yugioh": {"name": "Yu-Gi-Oh!-Daten", "dir": "yugioh", "files": ["cards.sqlite", "fingerprints-all.npz"],
               "extra": ["ygo-locale.sqlite", "fingerprints-add.npz"]},
    **__import__("games").extra("PACKS", {}),   # private games (games/extras.py)
}
# only games whose description is part of this program: a pack installed earlier for a game this program doesn't
# have then simply stays unused instead of loading the game
PACKS = {k: v for k, v in PACKS.items() if importlib.util.find_spec(f"games.{k}") is not None}
ROOT = DATA / "packs"


class PackError(Exception):
    pass


class PackMissing(PackError):
    """The server doesn't have this pack (yet) – e.g. a new game until the release that ships it: a note, no error."""


def folder(key):
    return ROOT / PACKS[key]["dir"]


def file_of(key, name):
    """Path of a pack file if it is there (complete) – otherwise None."""
    p = folder(key) / name
    return p if p.exists() else None


def path_of(key, name):
    """Pack file: in the data folder (downloaded) or – during development – in models/. None if nowhere."""
    import sys
    import games
    p = folder(key) / name
    if p.exists():
        return p
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1])) / "models"
    q = base / games.load(key).subdir / name
    return q if q.exists() else None


_INSTALLED = {}        # key -> (folder, time checked, bool) – see installed
INSTALLED_TTL = 5.0   # s


def installed(key):
    """All files of the pack in the data folder? Remembered for INSTALLED_TTL (asked per friend and page while
    opening the trade page); download() forgets it at once, so "not installed yet" never sticks."""
    import time
    f = folder(key)
    hit = _INSTALLED.get(key)
    now = time.monotonic()
    if hit and hit[0] == f and now - hit[1] < INSTALLED_TTL:
        return hit[2]
    ok = all((f / n).exists() for n in PACKS[key]["files"])
    _INSTALLED[key] = (f, now, ok)
    return ok


def forget_installed(key=None):
    """A pack was installed or removed: check again next time."""
    if key is None:
        _INSTALLED.clear()
    else:
        _INSTALLED.pop(key, None)


def bundled(key):
    """Is the pack (still) bundled in the program? In development everything is in models/ – nothing to download."""
    import sys
    import games
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1])) / "models"
    sub = base / games.load(key).subdir
    return all((sub / f).exists() for f in PACKS[key]["files"])


def needed(settings):
    """Packs that belong to the selected games and are still missing."""
    import games
    keys = set(settings.get("games_on") or []) | {games.current().key}
    keys = {k for k in keys if games.released(k) or k in games.unlocked()}   # never for a withdrawn game
    return [k for k in PACKS if k in keys and not installed(k) and not bundled(k)]


# approx. download size of the packs (for "Download about … MB?" and the setup): the files of packs.json, 2026-10-29
PACK_MB = {"mtg": 101, "pokemon": 62, "yugioh": 186}
MTG_DB_MB = 110                         # Magic card data from Scryfall (the languages are in the pack)


def game_ready(key):
    """Is a game ready to go? Magic: card database (Scryfall) + recognition pack; others: their pack."""
    from scanner.common import DATA
    import games
    pack_ok = key not in PACKS or installed(key) or bundled(key)
    if key == "mtg":
        return pack_ok and (games.folders("mtg", DATA)["ref"] / "cards.sqlite").exists()
    return pack_ok


def full_download_mb(key):
    """The whole download of a game on a fresh install (MB, rough): its pack, for Magic plus Scryfall's card data."""
    return PACK_MB.get(key, 0) + (MTG_DB_MB if key == "mtg" else 0)


def game_download_mb(key):
    """What would still need downloading for a game (MB, rough)."""
    from scanner.common import DATA
    import games
    mb = 0 if (key not in PACKS or installed(key) or bundled(key)) else PACK_MB.get(key, 0)
    if key == "mtg" and not (games.folders("mtg", DATA)["ref"] / "cards.sqlite").exists():
        mb += MTG_DB_MB
    return mb


def base_url():
    from net import updater
    return updater.BASE_URL + "/packs"


def manifest():
    """packs.json from the server, signature verified. -> {pack: {"files": [{"name", "size", "sha256"}], ...}}"""
    from net import netpolite
    from net import updater
    try:
        r = netpolite.get(base_url() + "/packs.json", timeout=20)
        s = netpolite.get(base_url() + "/packs.json.sig", timeout=20)
    except Exception as e:  # noqa: BLE001
        raise PackError(tr(f"Server not reachable: {e}")) from e
    if r.status_code != 200 or s.status_code != 200:
        raise PackError(tr(f"Packs not found on the server ({r.status_code})"))
    if not updater.verify(r.content, s.text):
        raise PackError(tr("Pack list not genuinely signed – nothing loaded"))
    release = json.loads(r.content.decode("utf-8")).get("packs") or {}
    return datakeys.merge(release, _data_listing())


def _data_listing():
    """New card data signed by the server's data key (cards/datakeys.py) – None if there is none or it doesn't pass:
    then packs.json alone counts, as before."""
    from net import netpolite
    from net import updater
    if not datakeys.keys():
        datakeys.refresh(updater.BASE_URL)   # first time: the release manifest says which data keys count
    if not datakeys.keys():
        return None
    try:
        r = netpolite.get(f"{base_url()}/{datakeys.DATA_NAME}", timeout=20)   # packs-data2.json (v2, "path")
        s = netpolite.get(f"{base_url()}/{datakeys.DATA_NAME}.sig", timeout=20)
    except Exception:  # noqa: BLE001
        return None
    if r.status_code != 200 or s.status_code != 200:
        return None
    try:
        return datakeys.verify_data(r.content, s.text)
    except datakeys.DataRejected as e:
        log.warning("Card data of the data key refused: %s", e)
        return None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _known(key):
    """Checksums of the downloaded files (recorded by download) – {file: sha256}."""
    try:
        return json.loads((folder(key) / ".files.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def allowed_names(key, entry):
    """Names a pack entry may list: the release list for packs.json; for a data entry the data key's hard list, plus –
    for the files it doesn't name and packs.json keeps (datakeys.merge "rel_names") – only names of the release list."""
    if entry.get("src") != "data":
        return datakeys.release_names(key)
    rel = set(datakeys.release_names(key))
    return (*datakeys.DATA_FILES.get(key, ()), *(n for n in entry.get("rel_names") or () if n in rel))


def outdated(key, entry=None):
    """Files of an installed pack that are newer on the server (different checksum). -> [name]"""
    entry = entry if entry is not None else manifest().get(key) or {}
    known = _known(key)
    out = []
    names = allowed_names(key, entry)
    for f in entry.get("files") or []:
        if not isinstance(f, dict) or f.get("name") not in names:
            continue   # never a path from the listing
        p = folder(key) / f["name"]
        if not p.exists():
            out.append(f["name"])
            continue
        have = known.get(f["name"])
        if have is None:   # older install without the checksum list: compute once
            have = known[f["name"]] = _sha256(p)
        if f.get("sha256") and have != f["sha256"]:
            out.append(f["name"])
    _remember(key, known)
    return out


def _remember(key, known):
    try:
        folder(key).mkdir(parents=True, exist_ok=True)
        (folder(key) / ".files.json").write_text(json.dumps(known), "utf-8")
    except OSError:
        pass


def download(key, progress=lambda text, done, total: None):
    """Download a pack (resumable), verify it, move it into place. progress(text, MB done, MB total)."""
    from net import netpolite
    entry = manifest().get(key)
    if not entry:
        raise PackMissing(tr(f"Pack “{key}” doesn't exist on the server"))
    dest = folder(key)
    files = entry.get("files") or []
    # what comes from the server is foreign, whichever key signed it: only the program's own file names, sizes within
    # the limits (cards/datakeys.py) – the data key only the games and files of its hard list
    names = allowed_names(key, entry)
    try:
        datakeys.check_files(key, files, names)
    except datakeys.DataRejected as e:
        raise PackError(tr(f"Pack list refused ({e})")) from None
    dest.mkdir(parents=True, exist_ok=True)
    # download compressed where the server offers a .gz (card databases: ~1/5 of the size), otherwise the file itself
    total = sum(int((f.get("gz") or f).get("size") or 0) for f in files)
    done = 0
    for f in files:
        name, size, want = f["name"], int(f.get("size") or 0), f.get("sha256")
        target = dest / name
        if target.resolve().parent != dest.resolve():
            raise PackError(tr(f"Pack list refused ({name})"))
        known = _known(key)
        if target.exists() and target.stat().st_size == size and (not want or known.get(name, want) == want):
            done += int((f.get("gz") or f).get("size") or 0)   # already there and unchanged
            continue
        gz = f.get("gz") if isinstance(f.get("gz"), dict) else None
        # on the server: the hashed name ("path", checked by datakeys.check_files) or the fixed one; here always `name`
        dl_name = (gz.get("path") or gz["name"]) if gz else (f.get("path") or name)
        dl_size, dl_want = (int(gz.get("size") or 0), gz.get("sha256")) if gz else (size, want)
        part = dest / (dl_name + ".part")
        have = part.stat().st_size if part.exists() else 0
        if have > dl_size:
            part.unlink()
            have = 0
        url = f"{base_url()}/{PACKS[key]['dir']}/{dl_name}"
        headers = {"Range": f"bytes={have}-"} if have else {}
        with netpolite.get(url, headers=headers, stream=True, timeout=60) as r:
            if have and r.status_code == 416:
                pass
            else:
                r.raise_for_status()
                if have and r.status_code != 206:   # server doesn't resume: start over
                    have = 0
                with open(part, "ab" if have else "wb") as out:
                    got = have
                    for chunk in r.iter_content(1 << 20):
                        got += len(chunk)
                        if got > dl_size:   # more than the signed size: never written to the end
                            break
                        out.write(chunk)
                        progress(f"{PACKS[key]['name']}: herunterladen …", (done + got) >> 20, total >> 20)
        if dl_want and _sha256(part) != dl_want:
            part.unlink(missing_ok=True)
            raise PackError(tr(f"{name}: checksum mismatch – please download again"))
        if gz:   # decompress, then verify the decompressed file
            import gzip
            import shutil
            progress(f"{PACKS[key]['name']}: auspacken …", (done + dl_size) >> 20, total >> 20)
            raw = dest / (name + ".unpack")
            room = min(size, datakeys.limit_of(name))
            with gzip.open(part, "rb") as fi, open(raw, "wb") as fo:
                while block := fi.read(1 << 20):   # counted: a small .gz can unpack to anything (gz bomb)
                    room -= len(block)
                    if room < 0:
                        break
                    fo.write(block)
            part.unlink(missing_ok=True)
            if room < 0:
                raw.unlink(missing_ok=True)
                raise PackError(tr(f"{name}: larger than announced – not used"))
            if want and _sha256(raw) != want:
                raw.unlink(missing_ok=True)
                raise PackError(tr(f"{name}: checksum mismatch – please download again"))
            part = raw
        size = dl_size
        try:
            datakeys.probe(name, part)
        except datakeys.DataRejected as e:
            part.unlink(missing_ok=True)
            raise PackError(tr(f"{name}: not a valid data file ({e}) – not used")) from None
        part.replace(target)
        known = _known(key)
        known[name] = want or _sha256(target)
        _remember(key, known)
        done += size
        log.info("Pack %s: %s downloaded (%s MB)", key, name, size >> 20)
    drop_stale_add(key)
    forget_installed(key)
    return len(files)


ADD_NAME = "fingerprints-add.npz"


def drop_stale_add(key):
    """A fingerprint add-on whose base isn't the main index next to it (a new full index came) is of no use any more:
    delete it (scanner/fingerprint.Index would ignore it anyway). -> True if one was deleted."""
    add, base = folder(key) / ADD_NAME, folder(key) / "fingerprints-all.npz"
    if not add.exists():
        return False
    try:
        import numpy as np
        with np.load(add, allow_pickle=False) as z:
            want = json.loads(str(z["meta"])).get("base")
    except (OSError, ValueError, KeyError):
        want = None
    known = _known(key)
    have = known.get("fingerprints-all.npz") or (_sha256(base) if base.exists() else None)
    if want and want == have:
        return False
    add.unlink(missing_ok=True)
    known.pop(ADD_NAME, None)
    _remember(key, known)
    log.info("Pack %s: fingerprint add-on of another main index removed", key)
    return True
