"""Card images on disk (data/card-images): overview, cleanup, size limit for the image cache.

Groups:
  sets     – images of downloaded recognition sets (deleted via "Manage sets")
  library  – cards in the library (collection), including language versions
  sessions – cards from saved sessions (statistics, history)
  cache    – everything else: loaded by the scanner for comparison, viewed while browsing
The image cache is emptied by age (oldest first; time = last use/modification of the file).
"""
import json
import os
import pathlib
import threading
import time

import requests

from scanner.common import IMAGES, IMAGES_REL, MINE, lang_img
from net import netpolite

HEADERS = {"User-Agent": netpolite.UA}
_lock = threading.Lock()
_offline_until = 0.0


def protected(collection_items, installed_codes):
    """-> (library paths, session paths, set folders) as sets of relative paths or set codes."""
    lib = set()
    for it in collection_items:
        img = it.get("img")
        if img:
            lib.add(img)
            if it.get("lang"):
                lib.add(lang_img(img, it["lang"]))
    sess = set()
    for f in (MINE / "sessions").glob("*.json") if (MINE / "sessions").exists() else []:
        try:
            data = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        for pack in data.get("packs", []):
            for c in pack.get("cards", []):
                img = c.get("img")
                if img:
                    sess.add(img)
                    if c.get("lang"):
                        sess.add(lang_img(img, c["lang"]))
    return lib, sess, {c.lower() for c in installed_codes}


def classify(collection_items, installed_codes):
    """-> {group: [(path, bytes, mtime)]} for all images in data/card-images."""
    lib, sess, sets = protected(collection_items, installed_codes)
    out = {"sets": [], "library": [], "sessions": [], "cache": []}
    if not IMAGES.exists():
        return out
    # Build the path relative to the program folder straight from the folder tree (no resolve() per file – with
    # thousands of images that cost almost a second). scandir: on Windows, size and date come with the listing, without
    # a separate call per file (13 600 images: 34 instead of 292 ms – holds the GIL shorter, the UI doesn't stutter)
    stack = [(str(IMAGES), IMAGES_REL)]
    while stack:
        root, folder = stack.pop()
        try:
            entries = list(os.scandir(root))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    stack.append((e.path, f"{folder}/{e.name}"))
                    continue
                if not e.name.lower().endswith(".jpg"):
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            rel = f"{folder}/{e.name}"
            code = rel.split("/")[2] if rel.count("/") >= 3 else ""
            group = ("library" if rel in lib else "sessions" if rel in sess else
                     "sets" if code in sets else "cache")
            out[group].append((pathlib.Path(e.path), st.st_size, st.st_mtime))
    return out



def summary(groups):
    return {k: (len(v), sum(b for _, b, _ in v)) for k, v in groups.items()}


def delete(files):
    """Delete files, clean up empty folders. -> bytes deleted."""
    freed = 0
    dirs = set()
    for p, size, _ in files:
        try:
            p.unlink()
            freed += size
            dirs.add(p.parent)
        except OSError:
            pass
    for d in sorted(dirs, key=lambda d: -len(d.parts)):
        try:
            if d != IMAGES and not any(d.iterdir()):
                d.rmdir()
                if d.parent != IMAGES and not any(d.parent.iterdir()):
                    d.parent.rmdir()
        except OSError:
            pass
    return freed


def enforce_limit(groups, limit_mb):
    """Limit the image cache to limit_mb: oldest images go first (first in, first out)."""
    cache = sorted(groups["cache"], key=lambda t: t[2])
    total = sum(b for _, b, _ in cache)
    limit = limit_mb * 1024 * 1024
    drop = []
    for item in cache:
        if total <= limit:
            break
        drop.append(item)
        total -= item[1]
    return delete(drop) if drop else 0


def touch(path):
    """Image was used -> counts as new (survives cleanup longer)."""
    try:
        os.utime(path, None)
    except OSError:
        pass


def is_missing(key):
    """Image (URL or path) found missing within the last hour? – one memory for all (netpolite)."""
    return netpolite.is_missing(key)


def mark_missing(key):
    netpolite.mark_missing(key)


def _images_off():
    import games
    return games.current().images_off


def offline():
    return time.time() < _offline_until


_by_url = {}   # image address -> a file on disk with it (prints sharing one image: fetched once)


def _same_image_on_disk(url):
    """A file on disk that already holds this address – this session's downloads, or (games with shared images,
    Yu-Gi-Oh!) another print with the same address in the card database. -> path or None"""
    known = _by_url.get(url)
    if known is not None and known.exists():
        return known
    import games
    g = games.current()
    if not g.shared_images:
        return None
    try:
        from cards import carddb
        from scanner.common import BASE, image_rel
        with carddb.connection() as con:
            rows = con.execute("SELECT set_code, number FROM cards WHERE img_normal = ? LIMIT 200", (url,)).fetchall()
        for r in rows:
            p = BASE / image_rel(r["set_code"], r["number"], 0)
            if p.exists():
                _by_url[url] = p
                return p
    except Exception:  # noqa: BLE001 – no card database: download as before
        pass
    return None


def fetch(path, url, timeout=8):
    """Download and save an image. Without internet: don't retry for a minute. An image already on disk under another
    print with the same address is copied instead (Game.shared_images). -> True if available."""
    global _offline_until
    path = pathlib.Path(path)
    if path.exists():
        touch(path)
        return True
    if url and not _images_off():
        same = _same_image_on_disk(url)
        if same is not None and same != path:
            import shutil
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(same, path)
            return True
    if not url or offline() or netpolite.is_missing(url) or _images_off():
        return False
    try:
        r = netpolite.get(url, headers=HEADERS, timeout=timeout)
        netpolite.note_missing(url, r)
        r.raise_for_status()
    except requests.ConnectionError:
        _offline_until = time.time() + 60
        return False
    except requests.RequestException:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(r.content)
    os.replace(tmp, path)
    _by_url[url] = path
    return True
