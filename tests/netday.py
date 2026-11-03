"""A "typical day" on the network (test plan 1.12, 2026-10-26): the app runs invisibly in a temporary data
folder (never the user's), every request goes to a fake internet (404, nothing leaves the PC) and netpolite logs
it. Steps: start (price update at start), library, open 30 details, a manual price update. Afterwards per service:
number of requests, smallest gap between two starts, how many ran at the same time – checked against
netpolite.POLICY/PATHS (gap) and SERIAL (one at a time).

    python tests/netday.py <card-data folder with cards.sqlite> [out.json] [--switches-off]

<card-data>: a COPY of reference data (e.g. work\\perf-review\\data\\card-data) – copied once more into the temp
folder; the temp folder is deleted afterwards. --switches-off: friends, usage numbers, team messages, studio off –
then no request may go to our own server at all (test plan 1.11, point 2).
Exit code 0 = all within the rules, 1 = violations (listed), 2 = the run itself failed.
"""
import json
import os
import pathlib
import shutil
import socket
import sys
import tempfile
import threading
import time

WT = pathlib.Path(__file__).resolve().parents[1]
SRC = pathlib.Path(sys.argv[1]).resolve()
OUT = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
OFF = "--switches-off" in sys.argv
for old in pathlib.Path(tempfile.gettempdir()).glob("bc-netday-*"):   # leftovers (Windows keeps the DB open to the end)
    if time.time() - old.stat().st_mtime > 3600:
        shutil.rmtree(old, ignore_errors=True)
HOME = pathlib.Path(tempfile.mkdtemp(prefix="bc-netday-"))
(HOME / "data" / "card-data").mkdir(parents=True)   # <home>/settings.json, <home>/data/card-data (common.DATA)
for name in ("cards.sqlite", "scryfall_sets.json", "sets_cache.json"):
    if (SRC / name).exists():
        shutil.copy2(SRC / name, HOME / "data" / "card-data" / name)
settings = {"first_setup": False, "language": "en", "game": "mtg", "price_update": "start",
            "stats_share": False, "tray_mode": False}
if OFF:
    settings.update({"team_messages": False, "updates": False, "studio_consent": False, "studio_auto": False})
(HOME / "settings.json").write_text(json.dumps(settings), "utf-8")

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["BC_HOME"] = str(HOME)
os.chdir(WT)
sys.path.insert(0, str(WT))
sys.argv = [str(WT / "app.py")]

_connect = socket.socket.connect


def _local_only(self, addr):   # belt and braces: nothing may leave the PC even if a request slips past the fake
    host = addr[0] if isinstance(addr, tuple) else str(addr)
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise OSError("netday: offline")
    return _connect(self, addr)


socket.socket.connect = _local_only

import requests  # noqa: E402
from requests.structures import CaseInsensitiveDict  # noqa: E402


def fake_request(method, url, **kw):
    """The fake internet: every service answers 404 after 30 ms (a real round trip takes about that long)."""
    time.sleep(0.03)
    r = requests.models.Response()
    r.status_code, r.url, r._content, r._content_consumed = 404, url, b"", True
    r.headers = CaseInsensitiveDict()
    r.request = requests.Request(method, url).prepare()
    return r


requests.request = fake_request
from net import netpolite  # noqa: E402
netpolite.requests.request = fake_request
netpolite.log_start()

from PySide6 import QtCore, QtNetwork  # noqa: E402
from ui import tray  # noqa: E402
tray.other_instance = lambda: False
tray.listen = lambda on_show: QtNetwork.QLocalServer()
tray.set_autostart = lambda on: None
import app  # noqa: E402
from scanner import camera  # noqa: E402
from ui import qdialogs  # noqa: E402


def _ask(title, text, buttons=None, **kw):   # questions: always "no"/cancel
    if kw.get("on_close"):
        QtCore.QTimer.singleShot(0, lambda: kw["on_close"](None))


qdialogs.ask = _ask
app.MainWindow.ask_continue_session = lambda self: None
camera.camera_names = lambda: []   # camera choice (scanner/scan_ctl.py) and Camera itself
RESULT = {"steps": [], "home": str(HOME), "switches_off": OFF}


def finish(code=None):
    log = netpolite.log_stop()
    RESULT["requests"] = log
    RESULT["summary"], RESULT["violations"] = evaluate(log)
    text = json.dumps(RESULT, indent=1, default=str)
    if OUT:
        OUT.write_text(text, "utf-8")
    print(json.dumps({"summary": RESULT["summary"], "violations": RESULT["violations"]}, indent=1), flush=True)
    shutil.rmtree(HOME, ignore_errors=True)
    os._exit(code if code is not None else (1 if RESULT["violations"] else 0))


def evaluate(log):
    """Per host: count, smallest start gap, max. at the same time – against the rules."""
    by = {}
    for e in log:
        by.setdefault(e["host"], []).append(e)
    summary, bad = {}, []
    for host, es in sorted(by.items()):
        es.sort(key=lambda e: e["start"])
        gaps = [b["start"] - a["start"] for a, b in zip(es, es[1:])]
        conc = max(sum(1 for o in es if o["start"] < e["end"] and o["end"] > e["start"]) for e in es)
        summary[host] = {"n": len(es), "min_gap": round(min(gaps), 3) if gaps else None, "max_parallel": conc,
                         "paths": sorted({e["path"].rsplit("/", 1)[0] + "/…" for e in es})[:6]}
        for a, b in zip(es, es[1:]):
            need = netpolite._gap("https://" + host + b["path"], host)
            if b["start"] - a["start"] < need * 0.9:
                bad.append(f"{host}: two requests {b['start'] - a['start']:.3f} s apart (rule: {need} s)")
                break
        if host in netpolite.SERIAL and conc > 1:
            bad.append(f"{host}: {conc} requests at the same time (rule: one at a time)")
        if OFF and host in netpolite.OWN:   # needed downloads (packs, price files, images) are fine – the mailbox
            # (friends, usage numbers, news, studio) and the update check are not
            box = sorted({e["path"] for e in es if e["path"].startswith(("/v1/", "/dl/manifest"))})
            if box:
                bad.append(f"{host}: {len(box)} mailbox/update paths although every switch is off: "
                           + ", ".join(box[:5]))
        if host not in netpolite.POLICY and host not in netpolite.OWN:
            bad.append(f"{host}: not registered in netpolite.POLICY (gets the default {netpolite.DEFAULT} s)")
    return summary, bad


def day():
    mw = QtCore.QCoreApplication.instance().main_window
    lib = mw.shell.backends.get("library")
    mw.shell.window.showNormal()   # offscreen, but it has to be shown or nothing is drawn (and no image asked for)
    mw.shell.window.resize(1600, 960)
    steps = [("library", lambda: mw.stream.show_page("library"), 3000), ("all_cards", lambda: lib.setMode("all"), 3000),
             ("search", lambda: lib.setSearch("dragon"), 5000),
             ("check", lambda: RESULT.update(library={"mode": lib.mode, "rows": lib.lib.model.rowCount()}), 100)]
    for i in range(30):
        steps += [(f"detail_{i}", lambda i=i: lib.open(i), 1500), (f"close_{i}", lambda: lib.escape(), 300)]
    steps += [("prices", lambda: mw.enqueue("prices", "prices"), 20000), ("idle", lambda: None, 15000)]

    def nxt():
        if not steps:
            finish()
            return
        name, fn, wait = steps.pop(0)
        RESULT["steps"].append(name)
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            RESULT.setdefault("step_errors", []).append(f"{name}: {e!r}")
        QtCore.QTimer.singleShot(wait, nxt)
    nxt()


_orig_init = app.MainWindow.__init__


def _init(self, *a, **k):
    _orig_init(self, *a, **k)
    QtCore.QTimer.singleShot(20000, day)        # start: give the startup jobs (price update) their time
    threading.Timer(600, lambda: finish(2)).start()   # safety net: never hang longer than 10 minutes


app.MainWindow.__init__ = _init
app.main()
