"""Overlay probe: is the scan overlay still pixel-identical after a change (e.g. code moved out of app.py)?

Run it on the base AND on the branch, then compare (twice each, for the noise floor):
    set BC_HOME=<fresh COPY of a data folder with a Lorcana database>   (settings.json: "game": "lorcana", seen_version =
                                                                       the version under test – else "What's new" covers it)
    <own venv>\\python tools\\ui-tests\\overlay_probe.py <base worktree>   <out>\\a-base
    <own venv>\\python tools\\ui-tests\\overlay_probe.py <branch worktree> <out>\\a-split
    … the same again into <out>\\b-base and <out>\\b-split (each run on a fresh copy: the probe books into the session)
    python tools\\ui-tests\\compare_probe.py <out>\\a-base <out>\\a-split [<out>\\b-base <out>\\b-split]
Never on real data, never from dev\\.venv (other chats build there), never with --first-run-test/--continue-test.

What it does: runs the real app offscreen and offline, books 5 fake hits through the real booking path
(Recognizer._ai_book; one ≥ 50 € = Biggest Hit, one foil via MainWindow.toggle_foil), 2 packs, then
  * renders the stream overlay deterministically: its own Overlay instance gets the real session snapshots with fixed
    times and paints into an image at fixed animation times (3 frames per hit, then Biggest Hit frames),
  * takes window shots of: scan page, card edit + card search in the stream, stream info, stream statistics,
    pack types sheet, end session dialog (cancelled – nothing is saved).
probe.log in the out folder lists the booked cards and every step (ERROR lines = a step failed).
"""
import os
import pathlib
import socket
import sys
import traceback

WT = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.chdir(WT)
sys.path.insert(0, str(WT))
sys.argv = [str(WT / "app.py")]
assert os.environ.get("BC_HOME"), "BC_HOME must point to a temp copy of a data folder"

_connect = socket.socket.connect


def _local_only(self, addr):   # offline: Scryfall, server & co. are left alone
    host = addr[0] if isinstance(addr, tuple) else str(addr)
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise OSError("probe: offline")
    return _connect(self, addr)


socket.socket.connect = _local_only
socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(OSError("probe: offline"))

from PySide6 import QtCore, QtGui, QtNetwork  # noqa: E402
from ui import tray  # noqa: E402
tray.other_instance = lambda: False
tray.listen = lambda on_show: QtNetwork.QLocalServer()
tray.set_autostart = lambda on: None
import app  # noqa: E402
from scanner import camera  # noqa: E402
from ui import qdialogs  # noqa: E402

LOG = open(OUT / "probe.log", "w", encoding="utf-8")


def note(*a):
    print(*a, file=LOG, flush=True)


open_dialogs = []
_orig_open = qdialogs._open


def _open(d, wait):   # remember open sheets so the probe can close them again
    open_dialogs.append(d)
    return _orig_open(d, wait)


qdialogs._open = _open
app.MainWindow.ask_continue_session = lambda self: None
camera.camera_names = lambda: []   # no camera choice (scanner/scan_ctl.py)

W, H = 1600, 900
T0 = 1000.0   # fixed clock for the probe's own overlay
PRICES = [(0.3, 0.9), (1.2, 3.0), (3.5, 7.0), (75.0, 140.0), (0.8, 2.4)]   # 4th = Biggest Hit (≥ 50 €)
FOIL_INDEX = 4                                                            # 5th card: foil via toggle_foil


def entries(n):
    from cards import carddb
    with carddb.connection() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM cards WHERE number GLOB '[0-9]*' ORDER BY set_code, "
                                             "CAST(number AS INTEGER) LIMIT ?", (n * 7,))]
    rows = rows[::7][:n]   # a few different cards
    out = []
    for r, (eur, foil) in zip(rows, PRICES):
        e = carddb.entry_from_row(r)
        e["eur"], e["eur_foil"] = eur, foil
        out.append(e)
    return out


def render(ov, now, name):
    img = QtGui.QImage(W, H, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QtGui.QColor(20, 20, 20))
    p = QtGui.QPainter(img)
    try:
        ov.paint(p, QtCore.QRectF(0, 0, W, H), now, 1.0)
    finally:
        p.end()
    img.save(str(OUT / f"{name}.png"))


def probe():
    mw = QtCore.QCoreApplication.instance().main_window
    shell = mw.shell
    shell.window.showNormal()
    shell.window.resize(1600, 960)
    steps = []

    def shot(name):
        def go():
            shell.window.grabWindow().save(str(OUT / f"{name}.png"))
            note("shot", name)
        return go

    # --- 1) book the hits through the real path, render the overlay at fixed times ---
    def book():
        mw.stream.show_page("scan")
        rec = mw.recognizer
        note("recognizer session is main session:", rec.session is mw.session)
        ov = app.Overlay(mw.settings)
        ov.card_by_id = mw.overlay.card_by_id
        cards = entries(len(PRICES))
        note("cards:", [(c["set"], c["number"], c["name"]) for c in cards])
        t = T0
        for i, e in enumerate(cards):
            if i == 3:
                mw.new_pack()   # pack 2 starts with the Biggest Hit
            cur = rec._ai_book(dict(e), force=True)
            note("booked", i, e["name"], "->", None if cur is None else (cur.get("price"), cur.get("foil")))
            if i == FOIL_INDEX:
                mw.toggle_foil()   # last card -> foil (button / key F)
            snap = mw.session.snapshot()
            ov.update(snap, t)
            for k, dt in enumerate((0.1, 0.45, 1.5)):
                ov.update(snap, t + dt)
                render(ov, t + dt, f"ov-hit{i + 1}-{k + 1}")
            t += 10.0
        # Biggest Hit: its entrance and an idle animation
        for k, dt in enumerate((0.3, 1.0, 2.2, 1.2 + 0.5)):
            ov.update(snap, t + dt)
            render(ov, t + dt, f"ov-bighit-{k + 1}")
        ov.update(snap, t + 30)
        render(ov, t + 30, "ov-calm")
        note("pack", snap["pack_number"], "cards", len(snap["pack"]), "total", snap["stats"].get("cards"))

    steps += [(9000, book), (2500, shot("01-scan-page"))]

    # --- 2) windows in the stream ---
    steps += [(10, lambda: mw.stream.open_edit(1)), (2500, shot("02-edit-card")),
              (10, mw.stream.close_card_panel), (1200, lambda: mw.stream.open_add()),
              (300, lambda: mw.stream.card_panel.set_search("Mickey")),
              (2500, shot("03-card-search")),
              (10, mw.stream.close_card_panel), (1200, mw.stream.open_info), (2500, shot("04-stream-info")),
              (10, mw.stream.close_all), (1200, mw.stream.open_stats), (2500, shot("05-stream-stats")),
              (10, mw.stream.close_all)]

    # --- 3) sheets: pack types, end session (cancelled -> nothing changes) ---
    def close_last():
        d = open_dialogs[-1] if open_dialogs else None
        note("closing", d and d.title)
        if d is not None:
            d.close(None)

    def sheet(fn, name):
        def go():
            QtCore.QTimer.singleShot(2500, shot(name))
            QtCore.QTimer.singleShot(2700, close_last)
            fn()   # waits in its own event loop until close_last
            run_next()
        return go

    steps += [(1200, sheet(mw.edit_pack_types, "06-pack-types")),
              (1200, sheet(lambda: mw.new_session(ask=False), "07-end-session"))]

    def finish():
        note("done")
        LOG.flush()
        os._exit(0)

    def run_next():
        if not steps:
            QtCore.QTimer.singleShot(500, finish)
            return
        delay, fn = steps.pop(0)

        def call():
            try:
                fn()
            except Exception:
                note("ERROR", traceback.format_exc())
            if getattr(fn, "__name__", "") != "go" or not fn.__qualname__.startswith("probe.<locals>.sheet"):
                run_next()
        QtCore.QTimer.singleShot(delay, call)
    run_next()


_orig = app.MainWindow.__init__


def _init(self, *a, **k):
    _orig(self, *a, **k)
    if self.shell and self.shell.window is not None:
        self.shell.window.resize(1600, 960)
    QtCore.QTimer.singleShot(0, probe)
    QtCore.QTimer.singleShot(240000, lambda: os._exit(3))   # emergency brake


app.MainWindow.__init__ = _init
app.main()
