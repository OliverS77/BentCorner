"""Stall reporter: notices when the UI (main thread) is blocked for a while and writes to the log where.

A timer in the main thread sets a heartbeat every 50 ms; a watcher thread checks it. If it is missing for longer than
LIMIT, it is noted once per stall: duration, the spot in the main thread (where it is busy computing) and which
background threads are currently working. That way stutter can also be found on other people's machines (send the log).
Costs practically nothing (one timestamp every 50 ms).
"""
import logging
import sys
import threading
import time
import traceback

from PySide6 import QtCore

log = logging.getLogger("lagwatch")
LIMIT = 0.25          # pauses at least this long are reported (seconds)
_beat = time.monotonic()
_main_id = None
events = []           # [(duration, spot in main thread, [background spots])] – for tests
stalls = []           # time.monotonic() per stall – for the hint "Performance could help" (Settings)


def _short(frame, n=4):
    """The last n calls from our own code (libraries only if nothing else would be visible)."""
    full = traceback.extract_stack(frame)
    st = [f for f in full if "site-packages" not in f.filename and "\\Lib\\" not in f.filename
          and "json" not in f.filename.rsplit("\\", 1)[-1]] or full
    return " < ".join(f"{f.filename.rsplit(chr(92), 1)[-1].rsplit('/', 1)[-1]}:{f.lineno} {f.name}"
                      for f in reversed(st[-n:]))


def _watch():
    reported = False
    while True:
        time.sleep(0.05)
        gap = time.monotonic() - _beat
        if gap < LIMIT:
            if reported:
                reported = False
            continue
        if reported:
            continue
        reported = True
        frames = sys._current_frames()
        main = frames.get(_main_id)
        where = _short(main) if main is not None else "?"
        busy = []
        for tid, fr in frames.items():
            if tid in (_main_id, threading.get_ident()):
                continue
            s = _short(fr, 5)
            if s and "sleep" not in s and "wait" not in s:
                busy.append(s)
        events.append((gap, where, busy))
        stalls.append(time.monotonic())
        log.warning("UI blocked for %.0f ms – main thread: %s | background: %s", gap * 1000, where,
                    " || ".join(busy[:4]) or "–")


def stalls_since(t0):
    """Stalls since time.monotonic() point t0 (the start itself doesn't count: something is always loading then)."""
    return sum(1 for t in stalls if t >= t0)


def start(parent):
    """Call in the main thread (e.g. in the main window)."""
    global _main_id, _timer, started
    _main_id = threading.get_ident()
    started = time.monotonic()

    def beat():
        global _beat
        _beat = time.monotonic()
    _timer = QtCore.QTimer(parent, interval=50, timeout=beat)
    _timer.start()
    threading.Thread(target=_watch, daemon=True, name="lagwatch").start()


_timer = None
started = None
