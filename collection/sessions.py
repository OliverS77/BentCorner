"""Saved sessions: data/sessions/<id>.json, one file per stream session.

Contains all packs with cards (price at the time of opening), stream info (paid, title …) and
the key figures (stats). Saved on every change so nothing is lost after a crash.

save_later(): a change made on the Log page – the log is written a moment later in the background (a log of 3000
cards took ~0.2 s of the click). Until then load()/load_all() hand out the pending state, so nothing reads an old
file; every write goes through a .tmp file and a replace (a crash mid-write leaves the old log whole); flush() writes
what is pending at once – the app calls it when it quits, and at the interpreter's exit it runs as well.
"""
import atexit
import json
import logging
import threading
import time

from scanner.common import MINE

SESSIONS = MINE / "sessions"


def _path(sid):
    return SESSIONS / f"{sid}.json"


def save(data):
    """Write now (replaces a pending save_later of the same log)."""
    from system import undo
    undo.LAST_WRITE[0] = time.time()   # for the automatic backup
    with _writing:
        with _lock:
            _pending.pop(data["id"], None)
        _write_file(data)


def _write_file(data):
    SESSIONS.mkdir(parents=True, exist_ok=True)
    tmp = _path(data["id"]).with_suffix(".tmp")
    # compact: Python's fast (C) encoder only works without indent – with indent=1 a log of 3000 cards took ~0.2 s of
    # pure-Python encoding, holding the interpreter (also from the background write) so the window stuttered
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    for _ in range(5):  # Windows: the file may briefly be held by a virus scanner
        try:
            tmp.replace(_path(data["id"]))
            return
        except PermissionError:
            time.sleep(0.05)


SAVE_LATER_MS = 400   # quiet time after the last change before the background write
_pending = {}   # sid -> the log's dict, written soon (newest state)
_lock = threading.Lock()
_timer = None
_writing = threading.RLock()   # one write at a time (a flush or save waits for a running background write)


def _copy(d):
    """A copy the caller may change (a Session takes the packs and cards lists over) – the pending state stays as it
    was handed in; the same depth as Session.to_dict makes."""
    out = dict(d)
    for k in ("info", "stats"):
        if isinstance(out.get(k), dict):
            out[k] = dict(out[k])
    if isinstance(out.get("packs"), list):
        out["packs"] = [{**p, "cards": [dict(e) for e in p.get("cards") or []]} if isinstance(p, dict) else p
                        for p in out["packs"]]
    return out


def save_later(data):
    """Like save(), a moment later in the background (see the module text). data must not change afterwards (a fresh
    to_dict())."""
    global _timer
    from system import undo
    undo.LAST_WRITE[0] = time.time()   # for the automatic backup
    with _lock:
        _pending[data["id"]] = data
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(SAVE_LATER_MS / 1000, _write_pending)
        _timer.daemon = True
        _timer.start()


def _write_pending():
    with _writing:
        with _lock:
            todo = list(_pending.items())
        for sid, d in todo:
            try:
                _write_file(d)
            except OSError:
                logging.getLogger(__name__).exception("Log %s could not be saved", sid)
                continue
            with _lock:   # written – unless a newer state came meanwhile (that one is written by its own timer)
                if _pending.get(sid) is d:
                    del _pending[sid]


def flush():
    """Write everything pending now (quitting the program)."""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
    _write_pending()


atexit.register(flush)


def load(sid):
    with _lock:
        d = _pending.get(sid)
    if d is not None:
        return _copy(d)
    return json.loads(_path(sid).read_text("utf-8"))


def is_import(d):
    """Own import (Import/Export → Collection): one session per import run (kind "import"; older ones only carry
    info "import")."""
    info = d.get("info") or {}
    return bool(info.get("import")) or info.get("kind") == "import"


def is_manual(d):
    """The day's changes by hand (collection/manual.py)."""
    return (d.get("info") or {}).get("kind") == "manual"


def is_singles(d):
    """Singles session (trade, purchase): every card counts individually, no packs – not in the pack statistics."""
    return (d.get("info") or {}).get("kind") == "singles"


def counts_in_stats(d):
    """Counts in the value statistics (value, cards, biggest hit …)? Scanning cards, opening packs, changes by hand –
    not trades and purchases (singles: booked, not gained), not imports (a whole collection at once would swamp the
    session figures; as before)."""
    return not is_import(d) and not is_singles(d)


def counts_for_packs(d):
    """Counts in the pack figures (Ø per pack, best pack, pack by pack, by pack type)? Only opening boosters (saved
    sessions without a kind are packs, as they always were)."""
    from scanner import core
    return counts_in_stats(d) and core.has_packs(d.get("info"))


HIDE_DAYS = 60   # a log "in the trash" (hidden) this long, then it goes for good – oldest first


def is_hidden(d):
    """In the trash: hidden, not deleted (docs/SYNC-PLAN.md §3b – the logs are the library's source, so a log never
    just disappears). {"at": time, "kept": the cards stay in the library}"""
    return bool(d.get("hidden"))


def hide(sid, kept):
    """Put a log into the trash (it stays on disk, hidden). kept: its cards stay in the library (the log keeps
    counting for it) – else it is taken out of the library ("collection": False). -> the log dict or None."""
    try:
        d = load(sid)
    except (OSError, ValueError):
        return None
    d["hidden"] = {"at": time.time(), "kept": bool(kept)}
    if not kept:
        d["collection"] = False
    save(d)
    return d


def unhide(sid):
    """Back out of the trash. -> the log dict or None."""
    try:
        d = load(sid)
    except (OSError, ValueError):
        return None
    d.pop("hidden", None)
    save(d)
    return d


def hidden_all():
    """The logs in the trash, newest hidden first."""
    out = [d for d in load_all(include_hidden=True) if is_hidden(d)]
    out.sort(key=lambda d: (d.get("hidden") or {}).get("at", 0), reverse=True)
    return out


def due_for_good(now=None):
    """Hidden longer than HIDE_DAYS: [log] – oldest first (the caller turns their cards into lines, then deletes)."""
    now = now or time.time()
    old = [d for d in hidden_all() if now - (d.get("hidden") or {}).get("at", now) > HIDE_DAYS * 86400]
    return sorted(old, key=lambda d: d["hidden"]["at"])


def load_all(include_hidden=False):
    """All sessions, newest first – without the ones in the trash (hidden), unless include_hidden (the library's sum
    counts them too: a hidden log with kept cards still holds them)."""
    out = []
    with _lock:
        pending = dict(_pending)
    for f in SESSIONS.glob("*.json") if SESSIONS.exists() else []:
        if f.stem in pending:
            continue
        try:
            out.append(json.loads(f.read_text("utf-8")))
        except (OSError, ValueError):
            continue
    out += [_copy(d) for d in pending.values()]   # changed a moment ago, not written yet
    if not include_hidden:
        out = [d for d in out if not is_hidden(d)]
    out.sort(key=lambda s: s.get("started", 0), reverse=True)
    return out


def exists(sid):
    with _lock:
        if sid in _pending:
            return True
    return _path(sid).exists()


def delete(sid):
    with _writing:
        with _lock:
            _pending.pop(sid, None)
        _path(sid).unlink(missing_ok=True)


def latest_open():
    """The most recently started, unfinished session with cards (to resume after restart/crash). Open
    sessions without any cards (started, never used) are silently ended – otherwise an empty one "runs" forever."""
    for s in load_all():
        if s.get("ended"):
            continue
        if any(p.get("cards") for p in s.get("packs") or []):
            return s
        s["ended"] = s.get("started") or time.time()
        save(s)
    return None
