"""Card images for Qt Quick: image://cards/<key> – loaded in the background, just like libview.ImageLoader
(first the local file, then the cache, otherwise a download – which is then stored there).

Whoever wants to show an image registers beforehand where it comes from: register(key, local, url, cache[, fallback]).
QML asks for the desired width via sourceSize; Qt Quick keeps the finished images in memory itself.
"""
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6 import QtCore, QtGui, QtQml, QtQuick

from cards import library

_sources = {}
_mem = {}  # finished images (e.g. the large image of the detail view) – key -> QImage
_keep = {}  # finished images that stay (card backs, small icons)
_lock = threading.Lock()
_pool = ThreadPoolExecutor(6, thread_name_prefix="qbilder")


def register(key, local=None, url=None, cache=None, fallback=None):
    import games
    if games.current().images_off:   # game unlocked only locally: no image from the net (placeholder with the name)
        url = None
    with _lock:
        _sources[key] = (local, url, cache, fallback)
    return "image://cards/" + key


def put(key, image):
    """Provide a finished image -> image://cards/<key> (older ones drop out after a while)."""
    with _lock:
        _mem[key] = image
        while len(_mem) > 40:
            _mem.pop(next(iter(_mem)))
    return "image://cards/" + key


def keep(key, image):
    """Like put, but does not drop out (for a few small images, e.g. card backs)."""
    with _lock:
        _keep[key] = image
    return "image://cards/" + key


def drop(key):
    with _lock:
        _keep.pop(key, None)
        _mem.pop(key, None)


CORNER = 0.053   # corner radius of the card images relative to the width (like CardTile.radius)


def _rounded(img):
    """Card image with rounded (transparent) corners – once while loading in the background, instead of computing
    a graphics effect with its own image layer for every tile in the grid (that made scrolling stutter, cost memory)."""
    if img.isNull() or img.width() < 8:
        return img
    out = QtGui.QImage(img.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
    out.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(out)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
    path = QtGui.QPainterPath()
    r = max(2.0, img.width() * CORNER)
    path.addRoundedRect(QtCore.QRectF(0, 0, img.width(), img.height()), r, r)
    p.setClipPath(path)
    p.drawImage(0, 0, img)
    p.end()
    return out


# ---------- pre-rounded card images on disk (WebP) ----------
# Qt loads files itself in its loader thread – without any Python. Via the image provider (Python), every tile went
# through Python, and while an image was being decoded the UI waited (scrolling stuttered). Hence: round once
# and store as a small WebP file (ROUND_DIR); after that the tile shows the file directly (round_url).
ROUND_DIR = None   # set by qlibrary (next to the thumbnails)
ROUND_W = 480
_round_known = None


_UNSAFE = re.compile(r"[^\w.-]")
_round_names = {}   # key -> file name (the tiles ask again on every refresh – 1200 tiles: re.sub + Path ~50 ms)


def _round_name(key):
    name = _round_names.get(key)
    if name is None:
        name = _round_names[key] = _UNSAFE.sub("_", key) + ".webp"
    return name


def _round_path(key):
    return ROUND_DIR / _round_name(key)


def _round_set():
    global _round_known
    if _round_known is None:
        known = set()
        try:
            if ROUND_DIR is not None and ROUND_DIR.exists():
                import os
                known = {e.name for e in os.scandir(ROUND_DIR) if e.name.endswith(".webp")}
        except OSError:
            pass
        _round_known = known
    return _round_known


def _game_changed():
    """Game switched: ROUND_DIR now points (common.switch_game) to its folder – re-read the list."""
    global _round_known
    _round_known = None
    _round_urls.clear()


_round_urls = {}   # key -> (ROUND_DIR, file URL): every refresh asks again for all ~1200 tiles


def round_url(key):
    """File URL of the pre-rounded image – or "" (then the image provider loads it and creates the file)."""
    if ROUND_DIR is None:
        return ""
    hit = _round_urls.get(key)
    if hit is not None and hit[0] is ROUND_DIR:
        return hit[1]
    name = _round_name(key)
    if name in _round_set():
        url = QtCore.QUrl.fromLocalFile(str(ROUND_DIR / name)).toString()
        _round_urls[key] = (ROUND_DIR, url)
        return url
    return ""


def _save_round(key, img):
    """Store a rounded image (at most ROUND_W wide) as WebP."""
    if ROUND_DIR is None or img.isNull():
        return
    try:
        if img.width() > ROUND_W:
            img = img.scaledToWidth(ROUND_W, QtCore.Qt.SmoothTransformation)
        ROUND_DIR.mkdir(parents=True, exist_ok=True)
        p = _round_path(key)
        tmp = p.with_suffix(".part.webp")
        if img.save(str(tmp), "WEBP", 85):
            tmp.replace(p)
            _round_set().add(p.name)
    except OSError:
        pass


def _load(key, width):
    if key in _keep or key in _mem:
        return _load_raw(key, width)
    big = _rounded(_load_raw(key, max(width, ROUND_W)))
    if not big.isNull() and key in _sources:
        _save_round(key, big)   # next time Qt loads the file itself
    if 0 < width < big.width():
        return big.scaledToWidth(width, QtCore.Qt.SmoothTransformation)
    return big


def _load_raw(key, width):
    with _lock:
        mem = _mem.get(key)
        if mem is None:
            mem = _keep.get(key)
    if mem is not None:
        return mem.scaledToWidth(width, QtCore.Qt.SmoothTransformation) if 0 < width < mem.width() else mem
    with _lock:
        local, url, cache, fallback = _sources.get(key, (None, None, None, None))
    img = QtGui.QImage()
    try:
        for path in (local, cache):
            if path is not None and path.exists():
                reader = QtGui.QImageReader(str(path))
                size = reader.size()
                if width > 0 and size.width() > width:
                    reader.setScaledSize(QtCore.QSize(width, round(size.height() * width / size.width())))
                img = reader.read()
                if not img.isNull():
                    return img
        if url and cache is not None and _queued_only(key):
            return img   # slow image server: the preload queue brings it (in reading order) – placeholder until then
        if url and cache is not None and _wait_prefetch(key) and cache.exists():   # preload queue is loading it
            img = QtGui.QImage(str(cache))
            if not img.isNull():
                return img.scaledToWidth(width, QtCore.Qt.SmoothTransformation) if 0 < width < img.width() else img
        if url:
            data = _fetch(url)
            img.loadFromData(data)
            if not img.isNull() and cache is not None:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(data)
    except Exception:  # noqa: BLE001 – offline or image missing: placeholder stays
        img = QtGui.QImage()
        if url and missing_at_source(url):   # the source has none: the grids hand this tile "" from now on (NoImage)
            for cb in list(_ready_cbs):
                try:
                    cb(key)
                except Exception:  # noqa: BLE001
                    pass
    if img.isNull() and fallback is not None and fallback.exists():
        img.load(str(fallback))
    if not img.isNull() and width > 0 and img.width() > width:
        img = img.scaledToWidth(width, QtCore.Qt.SmoothTransformation)
    return img


def missing_at_source(url):
    """The source answered 404 for this image (netpolite remembers it for days) – show NoImage, don't ask."""
    from net import netpolite
    return netpolite.is_missing(url)


def _fetch(url):
    from ui.librarycore import _throttle
    _throttle(url)
    return library.fetch_bytes(url)


# ---------- preload queue: images from the net in card order (top first), 4 at a time ----------
# Qt takes images from its queue from the back (last requested = first) and only one after another – in the
# grid the cards at the bottom (out of view) thus came first. The library sets its order here (prefetch) and
# reports the first visible card while scrolling (prioritize); the queue loads into the cache, Qt then only
# reads from disk (or waits briefly for the image that is currently loading).
WORKERS = 4
SLOW_WORKERS = 2   # slow image servers (prefetch ahead set, Lorcana): fewer at once – the detail image gets its turn
_pf_cv = threading.Condition()
_pf = {"order": [], "keys": set(), "pos": 0, "busy": {}, "done": set(), "started": False, "ahead": None}
_ready_cbs = []


def on_ready(cb):
    """cb(key) after the preload queue fetched an image of a slow server (any thread) – the grids then show it."""
    _ready_cbs.append(cb)


def pending(key):
    """Is the image of this tile still waiting in the preload queue (slow image server)? Then the tile doesn't ask
    for it yet – it shows the loading light waves until on_ready."""
    if not _queued_only(key):   # in memory first: the disk is asked only for queued tiles (a cloud folder's stat is slow)
        return False
    with _lock:
        local, url, cache, _fb = _sources.get(key, (None, None, None, None))
    return bool(url) and cache is not None and not cache.exists() and not (local is not None and local.exists())


def _queued_only(key):
    """Slow image server: tiles in the preload order don't fetch themselves (Qt has one loading thread that asks
    from the bottom up and would wait on each one) – the queue fetches them top first and reports them (on_ready)."""
    with _pf_cv:   # done without an image (download failed): no longer queued – Qt tries itself, shows "no image"
        return bool(_pf["ahead"]) and key in _pf["keys"] and key not in _pf["done"]


def _needs_net(key):
    """Does the preload queue need to do something here? (fetch the image from the net or create the rounded file)"""
    local, url, cache, _fb = _sources.get(key, (None, None, None, None))
    if ROUND_DIR is not None and _round_name(key) not in _round_set():
        return bool(url) or (local is not None and local.exists()) or (cache is not None and cache.exists())
    return bool(url) and cache is not None and not cache.exists() and not (local is not None and local.exists())


def key_of(src):
    """Key for an image URL (image://cards/… or file of a rounded tile) – "" if unknown."""
    s = str(src or "")
    if s.startswith("image://cards/"):
        return s[len("image://cards/"):]
    if s.startswith("file:") and ROUND_DIR is not None:
        return ""   # already done
    return ""


def prefetch(keys, ahead=None):
    """Set the order (e.g. all tiles of the grid from top to bottom) – replaces the previous one. ahead: load only
    this many from the current position (first visible tile) – spares image servers (games.base.prefetch_ahead)."""
    keys = [k[len("image://cards/"):] if k.startswith("image://cards/") else k for k in keys if k]
    with _pf_cv:
        _pf["order"], _pf["pos"], _pf["ahead"], _pf["keys"] = keys, 0, ahead, set(keys)
        if not _pf["started"]:
            _pf["started"] = True
            for i in range(WORKERS):
                threading.Thread(target=_pf_worker, args=(i,), daemon=True, name=f"vorladen{i}").start()
        _pf_cv.notify_all()


def prioritize(index):
    """Continue from here (first visible card after scrolling)."""
    with _pf_cv:
        _pf["pos"] = max(0, min(int(index), len(_pf["order"])))
        _pf_cv.notify_all()


def _next_job(worker=0):
    """-> next key that must come from the net (from pos, then from the start), or None."""
    if _pf["ahead"] and worker >= SLOW_WORKERS:
        return None
    order, n = _pf["order"], len(_pf["order"])
    ahead = _pf["ahead"]
    window = range(_pf["pos"], min(n, _pf["pos"] + ahead)) if ahead else list(range(_pf["pos"], n)) + list(
        range(0, _pf["pos"]))
    for j in window:
        k = order[j]
        if k in _pf["done"] or k in _pf["busy"]:
            continue
        with _lock:
            need = _needs_net(k)
        if not need:
            _pf["done"].add(k)
            continue
        return k
    return None


def _pf_worker(worker=0):
    while True:
        with _pf_cv:
            key = _next_job(worker)
            while key is None:
                _pf_cv.wait()
                key = _next_job(worker)
            ev = _pf["busy"][key] = threading.Event()
        try:
            with _lock:
                _local, url, cache, _fb = _sources.get(key, (None, None, None, None))
            if url and cache is not None and not cache.exists() and not (_local is not None and _local.exists()):
                data = _fetch(url)
                if QtGui.QImage.fromData(data).isNull():
                    raise ValueError("kein Bild")
                cache.parent.mkdir(parents=True, exist_ok=True)
                tmp = cache.with_suffix(".part")
                tmp.write_bytes(data)
                tmp.replace(cache)
            if ROUND_DIR is not None and _round_name(key) not in _round_set():
                _save_round(key, _rounded(_load_raw(key, ROUND_W)))
        except Exception:  # noqa: BLE001 – offline or similar: Qt tries again itself when displaying
            pass
        finally:
            with _pf_cv:
                _pf["busy"].pop(key, None)
                _pf["done"].add(key)
            ev.set()
            if _pf["ahead"]:   # slow image server: the grid shows the image now (or "no image" if it failed)
                for cb in list(_ready_cbs):
                    cb(key)


def _wait_prefetch(key, timeout=20.0):
    """Is the preload queue loading this image right now? Then wait for it. -> True if it waited."""
    with _pf_cv:
        ev = _pf["busy"].get(key)
    if ev is None:
        return False
    ev.wait(timeout)
    return True


_alive = {}   # keep running responses until Qt deletes them itself – otherwise Python might clean them up
#              while Qt is still fetching the image (rare crash at startup: "access violation")


class _Response(QtQuick.QQuickImageResponse):
    def __init__(self, key, size):
        super().__init__()
        self._img = QtGui.QImage()
        rid = id(self)
        with _lock:
            _alive[rid] = self
        self.destroyed.connect(lambda *_: _forget(rid))
        width = size.width() if size.isValid() and size.width() > 0 else 0
        _pool.submit(self._run, key, width)

    def _run(self, key, width):
        try:
            self._img = _load(key, width)
        except Exception:  # noqa: BLE001
            self._img = QtGui.QImage()
        try:
            self.finished.emit()
        except RuntimeError:   # Qt has already discarded the request
            pass

    def textureFactory(self):
        return QtQuick.QQuickTextureFactory.textureFactoryForImage(self._img)

    def errorString(self):
        return "" if not self._img.isNull() else "kein Bild"


def _forget(rid):
    with _lock:
        _alive.pop(rid, None)


class CardImages(QtQuick.QQuickAsyncImageProvider):
    def requestImageResponse(self, key, size):
        return _Response(key, size)


class CardImagesSync(QtQuick.QQuickImageProvider):
    """Same images, but as a simple image provider: Qt calls requestImage in its own loader thread
    (ForceAsynchronousImageLoading) and gets a QImage back – no response objects whose lifetime Python and Qt
    would have to share."""
    def __init__(self):
        super().__init__(QtQml.QQmlImageProviderBase.Image,
                         QtQml.QQmlImageProviderBase.ForceAsynchronousImageLoading)

    def requestImage(self, key, size, requested):
        width = requested.width() if requested.isValid() and requested.width() > 0 else 0
        try:
            img = _load(key, width)
        except Exception:  # noqa: BLE001
            img = QtGui.QImage()
        if size is not None and not img.isNull():
            size.setWidth(img.width())
            size.setHeight(img.height())
        return img


def install(engine):
    """Default: the simple image provider (CardImagesSync). The one with response objects (CardImages) rarely crashed
    at startup ("access violation", 2 of 42 starts in testing, synchronous 0 of 30) – for comparison: BC_ASYNCIMG=1."""
    import os
    engine.addImageProvider("cards", CardImages() if os.environ.get("BC_ASYNCIMG") else CardImagesSync())
