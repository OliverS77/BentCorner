"""First start (welcome + choose the data folder) and moving the data folder."""
import ctypes
import os
import pathlib
import shutil
import subprocess
import sys
import time

from PySide6 import QtCore, QtWidgets

from system import datahome
from system.i18n import tr

ITEMS = ("data", "settings.json", "bentcorner.log", "bentcorner-previous.log")  # what belongs to the data folder
READY = ("mtg", "pokemon", "yugioh", "lorcana")   # games with a tile on the setup page (order = order there)
def _clean(path):
    return str(pathlib.Path(path))


class _MiniShell(QtCore.QObject):
    """What the shared QML building blocks (Btn, DropList, FileBrowser …) need from "shell" – before the program."""

    @QtCore.Slot(str, result=str)
    def text(self, s):
        return tr(s)

    @QtCore.Slot(str, float, float)
    def tip(self, text, x, y):
        pass

    @QtCore.Property(bool, constant=True)
    def animate(self):
        return True

    @QtCore.Property(float, constant=True)
    def speed(self):
        return 1.0


class FirstRunBackend(QtCore.QObject):
    """First-run setup, part 1 (before the program): 0 language · 1 storage location · 2 games. After that it
    continues in the program window (onboarding.py) – where the card database already loads in the background."""
    changed = QtCore.Signal()
    browseChanged = QtCore.Signal()
    finished = QtCore.Signal()
    langChanged = QtCore.Signal()

    def __init__(self):
        super().__init__()
        from system import i18n
        # collections already on this PC (only looked at, nothing copied): then nothing is preselected – a new, empty
        # collection only by an explicit choice (lead 06.11.2026)
        self._found = self._look_for_existing()
        self._choice, self._other, self._error = ("" if self._found else "docs"), "", ""
        self._page, self._lang, self._games = 0, i18n.LANG, []
        self._browser = None
        self.result_home, self.result_lang, self.result_games, self.accepted = None, self._lang, [], False

    # ---------- steps ----------
    @QtCore.Property(int, notify=changed)
    def page(self):
        return self._page

    @QtCore.Slot()
    def back(self):
        self._page, self._error = max(0, self._page - 1), ""
        self.changed.emit()

    @QtCore.Slot()
    def next(self):
        if self._page == 1 and not self._check_folder():
            return
        if self._page == 1 and self._keeps_collection():   # an existing collection: it keeps its games
            self.go()
            return
        if self._page == 2:
            self.go()
            return
        self._page += 1
        self.changed.emit()

    # ---------- 0: language ----------
    @QtCore.Property(str, notify=changed)
    def lang(self):
        return self._lang

    @QtCore.Slot(str)
    def setLang(self, code):
        from system import i18n
        if code == self._lang:
            return
        self._lang = code
        i18n.set_language(code)
        self.changed.emit()
        self.langChanged.emit()   # QML rebuilds the page (all texts in the new language)

    # ---------- 2: games ----------
    @QtCore.Property("QVariantList", constant=True)
    def gameTiles(self):
        """[{key, name, back, ready, info}] – Magic, Pokémon, Yu-Gi-Oh!, Lorcana, then a "More coming soon" tile."""
        from cards import packs
        from system import userprofile

        def info(langs, key=None, mb=0):   # one pattern for all: card data (languages) + SCAN° – about N MB
            mb = max(10, round(packs.full_download_mb(key) / 10) * 10) if key else mb
            text = tr("Card data ({langs}) + SCAN° – about {mb} MB download") if key else                 tr("Card data ({langs}) from LorcanaJSON – about {mb} MB download")
            return text.replace("{langs}", langs).replace("{mb}", str(mb))
        return [
            {"key": "mtg", "name": "Magic: The Gathering", "back": userprofile.GAME_PRESETS["mtg"], "ready": True,
             "info": info(tr("all languages"), "mtg")},
            {"key": "pokemon", "name": "Pokémon TCG", "back": userprofile.GAME_PRESETS["pokemon"], "ready": True,
             "info": info(tr("all languages"), "pokemon")},
            {"key": "yugioh", "name": "Yu-Gi-Oh! TCG", "back": userprofile.GAME_PRESETS["yugioh"], "ready": True,
             "info": info("EN DE FR IT PT", "yugioh")},
            {"key": "lorcana", "name": "Disney Lorcana", "back": userprofile.GAME_PRESETS["lorcana"], "ready": True,
             "info": info("EN DE FR IT", mb=6)},
            {"key": "more", "name": tr("More games"), "back": "", "ready": False,
             "info": tr("More coming soon")}]

    @QtCore.Property("QVariantList", notify=changed)
    def games(self):
        return list(self._games)

    @QtCore.Slot(str)
    def toggleGame(self, key):
        if key not in READY:
            return
        self._games = [g for g in self._games if g != key] if key in self._games else self._games + [key]
        self.changed.emit()

    # ---------- 1: collections already there ----------
    @staticmethod
    def _note(text):
        """firstrun.log next to the starter notes (%LOCALAPPDATA%\\BentCorner or BC_STARTER_LOCAL): the program log
        only starts once the data folder is settled – this says what the first start offered and what was chosen."""
        try:
            d = datahome._local_home()
            d.mkdir(parents=True, exist_ok=True)
            with open(d / "firstrun.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
        except OSError:
            pass

    @classmethod
    def _look_for_existing(cls):
        try:
            found = datahome.existing()
        except Exception as e:  # noqa: BLE001 – a look around must never stop the setup
            cls._note(f"looking for existing collections failed: {type(e).__name__}: {e}")
            return []
        cls._note("found: " + ("; ".join(f"{e['path']} ({e['cards']} cards{'' if e['reachable'] else ', not reachable'})"
                                         for e in found) or "nothing"))
        return found

    @QtCore.Property("QVariantList", notify=changed)
    def found(self):
        """[{key, path, sub, reachable}] for the page – at most three (the remembered folder and the latest)."""
        out = []
        for i, e in enumerate(self._found[:3]):
            if not e["reachable"]:
                sub = tr("Can't be reached right now – is the drive plugged in?")
            else:
                when = time.strftime("%d.%m.%Y", time.localtime(e["changed"])) if e["changed"] else ""
                cards = tr("{n} cards").replace("{n}", f"{e['cards']:,}".replace(",", "."))
                sub = cards + (" · " + tr("last used {date}").replace("{date}", when) if when else "")
            out.append({"key": f"found:{i}", "path": _clean(e["path"]), "sub": sub, "reachable": e["reachable"]})
        return out

    @QtCore.Slot()
    def recheck(self):
        """[Check again] next to a collection that can't be reached (a drive plugged in in the meantime)."""
        self._found = self._look_for_existing()
        if self._choice.startswith("found:") and int(self._choice[6:]) >= len(self._found):
            self._choice = ""
        self.changed.emit()

    @QtCore.Property(bool, constant=True)
    def portableOk(self):
        """"Next to the program" only for a portable copy – an installed one deletes its folder on uninstalling."""
        return datahome.PORTABLE is not None

    @QtCore.Property(bool, notify=changed)
    def canGoOn(self):
        return self._page != 1 or self._choice != ""

    def _found_entry(self):
        if self._choice.startswith("found:"):
            i = int(self._choice[6:])
            return self._found[i] if i < len(self._found) else None
        return None

    def chosen(self):
        if self._choice.startswith("found:"):
            e = self._found_entry()
            return pathlib.Path(e["path"]) if e and e["reachable"] else None
        if self._choice == "other":
            return pathlib.Path(self._other) if self._other else None
        if self._choice == "port":
            return datahome.PORTABLE
        return datahome.DEFAULT if self._choice == "docs" else None

    def _keeps_collection(self):
        """The chosen folder already holds a collection (found, or picked by hand): it is used as it is – no games
        page, settings.json stays (startup.py never overwrites it)."""
        p = self.chosen()
        return p is not None and (p / "settings.json").exists()

    @QtCore.Property(str, notify=changed)
    def choice(self):
        return self._choice

    @QtCore.Slot(str)
    def setChoice(self, c):
        self._choice, self._error = c, ""
        self.changed.emit()

    @QtCore.Property(str, notify=changed)
    def other(self):
        return self._other

    @QtCore.Property(str, notify=changed)
    def error(self):
        return self._error

    @QtCore.Property(str, constant=True)
    def docsPath(self):
        return _clean(datahome.DEFAULT)

    @QtCore.Property(str, constant=True)
    def portPath(self):
        return _clean(datahome.PORTABLE) if datahome.PORTABLE is not None else ""

    # folder choice: the file browser in the same window
    @QtCore.Property(QtCore.QObject, notify=browseChanged)
    def browser(self):
        return self._browser

    @QtCore.Slot()
    def browse(self):
        from ui import qfiles
        self._browser = qfiles.FilesBackend("dir", "", self._other or str(datahome.documents()),
                                            done=self._browsed, parent=self)
        self.browseChanged.emit()

    def _browsed(self, paths, _filter=""):
        if paths:
            self._other, self._choice, self._error = _clean(paths[0]), "other", ""
        self._browser = None
        self.browseChanged.emit()
        self.changed.emit()

    def _check_folder(self):
        p = self.chosen()
        if p is None:
            if self._choice.startswith("found:"):
                self._error = tr("This folder can't be reached right now.")
                self.changed.emit()
            elif self._choice == "other":
                self.browse()
            return False
        if datahome.in_program(p):
            self._error = tr("This folder is deleted when Bent°Corner is uninstalled – please choose another one.")
            self.changed.emit()
            return False
        try:
            p.mkdir(parents=True, exist_ok=True)
            test = p / ".bentcorner-test"
            test.write_text("ok", "utf-8")
            test.unlink()
        except OSError as e:
            self._error = tr(f"Can't write to this folder: {e}")
            self.changed.emit()
            return False
        return True

    @QtCore.Slot()
    def go(self):
        if not self._check_folder() or not (self._games or self._keeps_collection()):
            return
        order = [g for g in READY if g in self._games]
        self.result_home, self.result_lang, self.result_games = self.chosen(), self._lang, order
        self._note(f"chosen: {self.result_home} ({'existing collection' if self._keeps_collection() else 'new'})")
        self.accepted = True
        self.finished.emit()

    @QtCore.Slot()
    def quit(self):
        self.finished.emit()


def quick_first_run():
    """First-run setup as a Qt Quick window. -> FirstRunBackend (accepted, result_home, result_lang, result_games) or
    None if Qt Quick doesn't start here."""
    try:
        from PySide6 import QtQml
        from ui import brand, quickui
        engine = QtQml.QQmlApplicationEngine()
        b, mini = FirstRunBackend(), _MiniShell()
        ctx = engine.rootContext()
        ctx.setContextProperty("T", quickui.palette())
        brand.expose(ctx)   # logo and the loading logo card – or neutral placeholders without brand/
        ctx.setContextProperty("shell", mini)
        ctx.setContextProperty("setup", b)
        engine.load(QtCore.QUrl.fromLocalFile(str(quickui.qml_dir() / "FirstRun.qml")))
        roots = engine.rootObjects()
        if not roots:
            return None
        win = roots[0]
        loop = QtCore.QEventLoop()
        b.finished.connect(loop.quit)
        # window closed with X: end the setup. Not via closing(QQuickCloseEvent) – PySide can't pass that event to a
        # Python slot (TypeError), the loop kept running and the program stayed on invisibly, holding the
        # single-instance lock (05.11.2026)
        win.visibleChanged.connect(lambda shown: shown or loop.quit())
        win.show()
        loop.exec()
        win.hide()
        b._engine, b._mini = engine, mini  # keep alive until here
        return b
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("First-run setup in Qt Quick")
        return None

# ---------- move the data folder (own process, while the program is closed) ----------
def start_move(old, new):
    """From the running program: start the move process. The program must quit afterwards."""
    args = ["--move-data", str(old), str(new), str(os.getpid())] + datahome.restart_args()
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    cmd = [sys.executable, *args] if getattr(sys, "frozen", False) else [sys.executable, sys.argv[0], *args]
    # (the actual program from "Essentials" – the move process doesn't need the launcher)
    subprocess.Popen(cmd, env=env, cwd=str(new), creationflags=flags, close_fds=True)


def _wait_for(pid, timeout=60):
    """Wait until the old program has quit (otherwise files are still open)."""
    if sys.platform != "win32":
        time.sleep(2)
        return
    SYNCHRONIZE = 0x00100000
    h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if h:
        ctypes.windll.kernel32.WaitForSingleObject(h, int(timeout * 1000))
        ctypes.windll.kernel32.CloseHandle(h)
    time.sleep(0.5)


def _files(root):
    for dirpath, _, names in os.walk(root):
        for n in names:
            yield pathlib.Path(dirpath) / n


class MoverBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._text, self._done, self._total, self._error = tr("Waiting for Bent°Corner to close …"), 0, 0, ""
        self.loop = None

    def set(self, text=None, done=None, total=None):
        if text is not None:
            self._text = text
        if done is not None:
            self._done = done
        if total is not None:
            self._total = total
        self.changed.emit()
        QtCore.QCoreApplication.processEvents()

    @QtCore.Property(str, notify=changed)
    def text(self):
        return self._text

    @QtCore.Property(int, notify=changed)
    def done(self):
        return self._done

    @QtCore.Property(int, notify=changed)
    def total(self):
        return self._total

    @QtCore.Property(str, notify=changed)
    def error(self):
        return self._error

    def fail(self, error):
        """Show the error and wait for "OK"."""
        self._error = tr(f"Moving failed – your data stays in the old place.\n\n{error}")
        self.changed.emit()
        self.loop = QtCore.QEventLoop()
        self.loop.exec()

    @QtCore.Slot()
    def ok(self):
        if self.loop is not None:
            self.loop.quit()


def _mover_window(app):
    """Small Qt Quick window for the move -> (backend, window) or (backend, None)."""
    b = MoverBackend()
    try:
        from PySide6 import QtQml
        from ui import brand, quickui
        engine = QtQml.QQmlApplicationEngine()
        mini = _MiniShell()
        ctx = engine.rootContext()
        ctx.setContextProperty("T", quickui.palette())
        brand.expose(ctx)   # logo and the loading logo card – or neutral placeholders without brand/
        ctx.setContextProperty("shell", mini)
        ctx.setContextProperty("mover", b)
        engine.load(QtCore.QUrl.fromLocalFile(str(quickui.qml_dir() / "Mover.qml")))
        roots = engine.rootObjects()
        if not roots:
            return b, None
        win = roots[0]
        win.show()
        b._engine, b._mini = engine, mini
        app.processEvents()
        return b, win
    except Exception:  # noqa: BLE001 – without a window: move silently
        import logging
        logging.getLogger(__name__).exception("Window “Move data folder”")
        return b, None


def run_mover(argv):
    """Entry point for `BentCorner.exe --move-data <old> <new> <pid>`: move the data, then restart normally."""
    i = argv.index("--move-data")
    old, new, pid = pathlib.Path(argv[i + 1]), pathlib.Path(argv[i + 2]), argv[i + 3]
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    from ui import iconkit
    app.setWindowIcon(iconkit.qicon())   # its own process: the mark for the taskbar like the main window
    ui, win = _mover_window(app)
    _wait_for(pid)
    error, moved = None, []
    items = [old / n for n in ITEMS if (old / n).exists()]
    same_drive = os.path.splitdrive(str(old.resolve()))[0].lower() == os.path.splitdrive(str(new.resolve()))[0].lower()
    try:
        new.mkdir(parents=True, exist_ok=True)
        if same_drive:  # same drive: just rename, done immediately
            for src in items:
                ui.set(tr(f"Moving {src.name} …"))
                shutil.move(str(src), str(new / src.name))
                moved.append(src.name)
            datahome.set_home(new)
        else:  # other drive: first copy everything (with progress), then switch over, then delete the original
            files = [f for src in items for f in ([src] if src.is_file() else _files(src))]
            ui.set(total=len(files))
            for n, f in enumerate(files):
                rel = f.relative_to(old)
                (new / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, new / rel)
                if n % 25 == 0:
                    ui.set(tr(f"Copying {n:,} of {len(files):,} files …").replace(",", "."), done=n)
            datahome.set_home(new)
            ui.set(tr("Cleaning up the old folder …"), total=0)
            for src in items:
                shutil.rmtree(src, ignore_errors=True) if src.is_dir() else src.unlink(missing_ok=True)
    except Exception as e:
        error = e
        if same_drive:  # move what was already moved back to the old location
            for name in moved:
                try:
                    shutil.move(str(new / name), str(old / name))
                except OSError:
                    pass
        else:  # remove the partial copy, the original is still complete
            for src in items:
                t = new / src.name
                shutil.rmtree(t, ignore_errors=True) if t.is_dir() else t.unlink(missing_ok=True)
    if error and win is not None:
        ui.fail(error)
    if win is not None:
        win.hide()
    # start Bent°Corner normally (now at the new or old location)
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    cmd = [datahome.program()] if getattr(sys, "frozen", False) else [sys.executable, argv[0]]
    cmd += datahome.restart_args() + [f"--after={os.getpid()}"]   # waits until this process is gone
    from ui import tray
    tray.release()
    subprocess.Popen(cmd, env=env, creationflags=flags, close_fds=True)
    return 0


def relaunch():
    """Restart the program (after the first start with a different data folder)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    cmd = [datahome.program()] if getattr(sys, "frozen", False) else [sys.executable, sys.argv[0]]
    cmd += datahome.restart_args() + [f"--after={os.getpid()}"]   # waits until this process is gone
    from ui import tray
    tray.release()
    subprocess.Popen(cmd, env=env, creationflags=flags, close_fds=True)
