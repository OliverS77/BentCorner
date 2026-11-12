"""The first start like a new user, offscreen, from the source – every setup step as a picture (lead 04.11.2026).

    python tools/ui-tests/erststart.py <test folder> <local copy> <out> [--lang de] [--fill [--copies <dir> …]]

Test folders only (BC_STARTER_LOCAL/ROAMING/DOCUMENTS under <test folder>, emptied before – it must be a folder named
"erststart-test*" that is no junction); downloads come from <local copy> (BC_LOCAL_DL, net/netpolite.py). Without
--fill every connection except 127.0.0.1 is refused – the run proves the copy is complete. With --fill a missing
request is fetched once (tools/local_dl.py, our server with "X-BC-Check: 1"); --copies: folders with pack files to
take instead (a COPY of an installed app's data/packs – only read).
Part 1 (language, storage location, games) and part 2 (profile … finish) run as two processes, like the real restart.
"""
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _safe_test_dir(p):
    p = pathlib.Path(p).resolve()
    if not p.name.startswith("erststart-test") or len(p.parts) < 3:
        sys.exit(f"refused: {p} is not an erststart-test folder")
    for q in [p] + list(p.parents)[:2]:
        if q.exists() and (q.is_symlink() or os.path.isjunction(q)):
            sys.exit(f"refused: {q} is a link")
    return p


def main():
    args = sys.argv[1:]
    test, local, out = _safe_test_dir(args[0]), pathlib.Path(args[1]).resolve(), pathlib.Path(args[2]).resolve()
    lang = args[args.index("--lang") + 1] if "--lang" in args else "de"
    fill = "--fill" in args
    copies = [a for i, a in enumerate(args) if i and args[i - 1] == "--copies"]
    if test.exists():
        shutil.rmtree(test)
    for d in ("local", "roaming", "docs"):
        (test / d).mkdir(parents=True)
    out.mkdir(parents=True, exist_ok=True)
    local.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, BC_STARTER_LOCAL=str(test / "local"), BC_STARTER_ROAMING=str(test / "roaming"),
               BC_STARTER_DOCUMENTS=str(test / "docs"), BC_LOCAL_DL=str(local), BC_CHECK="1",
               QT_QPA_PLATFORM="offscreen", BC_ERST=json.dumps({"out": str(out), "lang": lang, "fill": fill,
                                                                 "copies": copies, "test": str(test)}))
    env.pop("BC_HOME", None)
    py = sys.executable
    t0 = time.time()
    r1 = subprocess.run([py, __file__, "--part", "1"], env=env, cwd=ROOT, timeout=600)
    home = test / "docs" / "BentCorner"
    if r1.returncode != 0 or not (home / "settings.json").exists():
        sys.exit(f"part 1 failed ({r1.returncode})")
    r2 = subprocess.run([py, __file__, "--part", "2"], env=dict(env, BC_HOME=str(home)), cwd=ROOT, timeout=3600)
    print(f"done in {time.time() - t0:.0f} s, part 2: {r2.returncode}")
    sys.exit(r2.returncode)


# ---------- inside the two app processes ----------
def _guard(cfg):
    if cfg["fill"]:
        from tools import local_dl
        local_dl.fill(os.environ["BC_LOCAL_DL"], cfg["copies"])
        from net import netpolite
        real = netpolite._local_response
        stats = pathlib.Path(cfg["out"]) / f"fill-part{sys.argv[-1]}.json"

        def counted(*a, **k):
            try:
                return real(*a, **k)
            finally:
                local_dl.save_stats(stats)
        netpolite._local_response = counted
        return
    connect = socket.socket.connect

    def local_only(self, addr):
        host = addr[0] if isinstance(addr, tuple) else str(addr)
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise OSError("offline first-start test: no network")
        return connect(self, addr)
    socket.socket.connect = local_only


def _common(cfg):
    _guard(cfg)
    from PySide6 import QtNetwork
    from ui import tray
    tray.set_autostart = lambda on: None   # (an isolated run never writes the registry anyway – belt and braces)
    tray.listen = lambda on_show: QtNetwork.QLocalServer()
    try:
        from scanner import camera
        camera.camera_names = lambda: []
    except ImportError:
        pass


def _grab(win, cfg, name):
    win.grabWindow().save(str(pathlib.Path(cfg["out"]) / f"{cfg['lang']}-{name}.png"))


def part1(cfg):
    from system import datahome
    datahome.HOME, datahome.FIRST_RUN = datahome.DEFAULT, True   # the frozen exe decides this; the source never does
    _common(cfg)
    from PySide6 import QtCore, QtGui
    from ui import setupui
    setupui.relaunch = lambda: None
    init = setupui.FirstRunBackend.__init__

    def drive(b):
        win = next(w for w in QtGui.QGuiApplication.topLevelWindows() if w.isVisible())
        win.resize(1100, 760)
        steps = [lambda: b.setLang(cfg["lang"]), lambda: _grab(win, cfg, "01-sprache"),
                 b.next, lambda: _grab(win, cfg, "02-speicherort"),
                 b.next] + [(lambda k=k: b.toggleGame(k)) for k in setupui.READY] + [
                 lambda: _grab(win, cfg, "03-spiele"), b.go]

        def step():
            if steps:
                steps.pop(0)()
                QtCore.QTimer.singleShot(900, step)
        step()

    def _init(self):
        init(self)
        QtCore.QTimer.singleShot(2500, lambda: drive(self))
    setupui.FirstRunBackend.__init__ = _init
    sys.argv = [str(ROOT / "app.py")]
    import app
    app.main()


def part2(cfg):
    _common(cfg)
    from PySide6 import QtCore
    import app
    sys.argv = [str(ROOT / "app.py")]
    shots = {"seen": set(), "t0": time.time()}

    def tour():
        mw = QtCore.QCoreApplication.instance().main_window
        win = mw.shell.window
        win.showNormal()
        win.resize(1600, 1000)
        from system import orbit
        ob = mw.onboarding
        plan = [("04-profil", lambda: ob.go("friends")),
                ("05-orbit", lambda: (ob.st.__setitem__("orbit", "full"), ob.dlg.refresh())),
                ("06-orbit-ganz", lambda: (ob.st.__setitem__("orbit", orbit.level(mw.settings)), ob.go("stats"))),
                ("07-zahlen", lambda: ob.go("background")),
                ("08-hintergrund", lambda: ob.go("finish"))]

        def step():
            if plan:
                name, then = plan.pop(0)
                _grab(win, cfg, name)
                then()
                QtCore.QTimer.singleShot(1500, step)
                return
            wait()

        def wait():
            if ob._loading() or getattr(mw, "setup_error", ""):
                if "09" not in shots["seen"]:
                    QtCore.QTimer.singleShot(4000, lambda: _grab(win, cfg, "09-fertig-laedt"))
                    shots["seen"].add("09")
                if getattr(mw, "setup_error", ""):
                    _grab(win, cfg, "09-fehler")
                    return done(2)
                if time.time() - shots["t0"] > 3000:
                    return done(3)
                QtCore.QTimer.singleShot(2000, wait)
                return
            QtCore.QTimer.singleShot(2500, lambda: (_grab(win, cfg, "10-fertig"), ob.finish(),
                                                    QtCore.QTimer.singleShot(3500, lambda: (
                                                        _grab(win, cfg, "11-bibliothek"),
                                                        QtCore.QTimer.singleShot(15000, lambda: (
                                                            _grab(win, cfg, "12-bibliothek-spaeter"), done(0)))))))

        def done(code):
            mw.force_quit = True
            QtCore.QTimer.singleShot(1500, lambda: os._exit(code))
        step()

    init = app.MainWindow.__init__

    def _init(self, *a, **k):
        init(self, *a, **k)
        QtCore.QTimer.singleShot(9000, tour)
    app.MainWindow.__init__ = _init
    app.main()


if __name__ == "__main__":
    if "--part" in sys.argv:
        sys.path.insert(0, str(ROOT))
        os.chdir(ROOT)
        cfg = json.loads(os.environ["BC_ERST"])
        (part1 if sys.argv[sys.argv.index("--part") + 1] == "1" else part2)(cfg)
    else:
        main()
