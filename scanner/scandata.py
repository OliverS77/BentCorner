"""Scan data: collect misrecognized cards so that recognition can improve later.

Something is saved only when you correct a recognized card or explicitly click "Wrongly recognized" – and then
only the crop of the card (not the whole
camera image, so no faces or rooms) plus one line of text: what was recognized and what is correct.
About 20–30 KB per card, at most 20 MB – the oldest then drop out. Everything stays on this computer until you
click "Send" yourself (for now: save a ZIP file and pass it on yourself).

  data/scan-data/<time>.jpg   card crop
  data/scan-data/log.jsonl    one line per correction
"""
import collections
import json
import shutil
import threading
import time
import zipfile

from scanner.common import DATA

DIR = DATA / "scan-data"
LOG = DIR / "log.jsonl"
LIMIT = 20 * 1024 * 1024
KEEP_RECENT = 80   # this many recently counted cards are kept in memory (only until a correction)
MAX_SIDE = 420     # side length of the saved crop

_recent = collections.OrderedDict()  # added -> (jpg bytes, detection info)
_lock = threading.Lock()


def _brief(e):
    return {k: e.get(k) for k in ("name", "set", "number", "lang", "id")} if e else None


def remember(added, crop, entry, how=None):
    """On counting: keep the crop (BGR image of the card) in memory for a while – it is only written on a
    correction."""
    if crop is None or getattr(crop, "size", 0) == 0:
        return
    try:
        import cv2
        h, w = crop.shape[:2]
        s = MAX_SIDE / max(h, w)
        if s < 1:
            crop = cv2.resize(crop, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 82])
    except Exception:  # noqa: BLE001 – collecting is a bonus, scanning comes first
        return
    if not ok:
        return
    with _lock:
        _recent[added] = (buf.tobytes(), {"detected": _brief(entry), "how": how})
        while len(_recent) > KEEP_RECENT:
            _recent.popitem(last=False)


def correction(added, old, new):
    """A card was corrected: store the crop + a line of text. -> True if something was saved."""
    with _lock:
        got = _recent.pop(added, None)
    if got is None or not new or (old or {}).get("id") == new.get("id"):
        return False
    jpg, info = got
    DIR.mkdir(parents=True, exist_ok=True)
    name = f"{int(time.time() * 1000)}.jpg"
    try:
        (DIR / name).write_bytes(jpg)
        line = {"file": name, "time": int(time.time()), "detected": info["detected"] or _brief(old),
                "corrected": _brief(new), "how": info.get("how")}
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        return False
    trim()
    return True


def removed(added, old, sure="ja"):
    """A card was counted by mistake: store the crop + a line ("extra"). sure: how certain it is a mistake –
    "ja" (button "Wrongly recognized"), "auto" (the scanner noticed it itself: A, B, A) or "vielleicht" (deleted
    shortly after the scan – may also be intentional; evaluate with care).
    Only while the crop is still in memory (the recently counted cards). -> True if saved."""
    with _lock:
        got = _recent.pop(added, None)
    if got is None:
        return False
    jpg, info = got
    DIR.mkdir(parents=True, exist_ok=True)
    name = f"{int(time.time() * 1000)}.jpg"
    try:
        (DIR / name).write_bytes(jpg)
        line = {"file": name, "time": int(time.time()), "detected": info["detected"] or _brief(old),
                "corrected": None, "extra": True, "sure": sure, "how": info.get("how")}
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        return False
    trim()
    return True


def _images():
    return sorted(DIR.glob("*.jpg")) if DIR.exists() else []


def stats():
    """-> (count, bytes)"""
    files = _images()
    size = sum(f.stat().st_size for f in files) + (LOG.stat().st_size if LOG.exists() else 0)
    return len(files), size


def trim(limit=LIMIT):
    """Over the limit: delete the oldest images (and their lines)."""
    files = _images()
    total = sum(f.stat().st_size for f in files)
    gone = set()
    while files and total > limit:
        f = files.pop(0)
        total -= f.stat().st_size
        f.unlink(missing_ok=True)
        gone.add(f.name)
    if gone and LOG.exists():
        keep = [ln for ln in LOG.read_text("utf-8").splitlines() if ln.strip() and json.loads(ln).get("file") not in gone]
        LOG.write_text("".join(ln + "\n" for ln in keep), "utf-8")


def make_zip(path):
    """Everything as a ZIP (to pass on). -> number of images"""
    files = _images()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:  # JPEGs do not compress any further
        for f in files:
            z.write(f, f.name)
        if LOG.exists():
            z.write(LOG, LOG.name)
    return len(files)


def clear():
    """Delete everything – no confirmation fuss: gone is gone."""
    with _lock:
        _recent.clear()
    shutil.rmtree(DIR, ignore_errors=True)
