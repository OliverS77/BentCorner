"""Program start: logging, threads, look, the Qt application and the main window – moved from app.py
unchanged (docs/APP-SPLIT.md, phase C). app.main() calls main(MainWindow)."""
import json
import logging
import os
import sys
import threading
import time

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
import cv2
import numpy as np

from scanner import ocrscan
from scanner.common import BASE
from system import datahome
from ui import iconkit, look, setupui
from ui.scanlook import refresh_color_consts


log = logging.getLogger("booster")   # the same logger as app.py
SETTINGS_FILE = BASE / "settings.json"
AFTER_WAIT = 30   # s a restarted instance waits for the previous one to end (--after=<pid>)


def _saved():
    """settings.json as a dict – {} when missing, broken or not an object (review 08.11. F2: never a crash at start)."""
    try:
        d = json.loads(SETTINGS_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def saved_language():
    """Language from the settings. Brand new (no settings yet): English – the first-run setup asks first, with
    flags."""
    if not SETTINGS_FILE.exists():
        return "en"
    lang = _saved().get("language", "de")
    return lang if isinstance(lang, str) else "de"


def apply_look(app):
    """Base colours and font of the application (for the tray icon menu and as a default for Qt Quick)."""
    f = look.text_font()
    f.setPointSizeF(11 * look.scale())
    app.setFont(f)
    pal = QtGui.QPalette()
    colors = {
        QtGui.QPalette.Window: "#0b0e1a", QtGui.QPalette.WindowText: "#eef1ff", QtGui.QPalette.Base: "#0b0e1a",
        QtGui.QPalette.AlternateBase: "#141931", QtGui.QPalette.Text: "#eef1ff", QtGui.QPalette.Button: "#1b2033",
        QtGui.QPalette.ButtonText: "#eef1ff", QtGui.QPalette.Highlight: "#1f5f6b",
        QtGui.QPalette.HighlightedText: "#ffffff", QtGui.QPalette.ToolTipBase: "#161b30",
        QtGui.QPalette.ToolTipText: "#eef1ff", QtGui.QPalette.PlaceholderText: "#6c7390",
        QtGui.QPalette.Mid: "#2c3352", QtGui.QPalette.Dark: "#070912", QtGui.QPalette.Light: "#3a4260",
        QtGui.QPalette.Link: "#62f2ff", QtGui.QPalette.BrightText: "#ff5bd6",
    }
    for role, col in colors.items():
        pal.setColor(role, QtGui.QColor(look._color_map.get(col, col)))
    for role in (QtGui.QPalette.Text, QtGui.QPalette.ButtonText, QtGui.QPalette.WindowText):
        pal.setColor(QtGui.QPalette.Disabled, role, QtGui.QColor("#5a6078"))
    app.setPalette(pal)


def setup_threads():
    """Protect the UI from computing background threads: otherwise Python only hands over the lock (GIL) every 5 ms –
    each of the UI's many small Python calls (QML ↔ Python) thus waited up to 5 ms while e.g. prices
    were being read in: animations stuttered. 0.5 ms costs the background hardly anything."""
    sys.setswitchinterval(0.0005)


LOG = "bentcorner.log"
PREVIOUS_LOG = "bentcorner-previous.log"   # the log of the start before (a crash only shows after the restart)


def keep_previous_log(base=None):
    """The last start's log becomes bentcorner-previous.log (one generation) – instead of being overwritten."""
    base = BASE if base is None else base
    try:
        if (base / LOG).exists():
            os.replace(base / LOG, base / PREVIOUS_LOG)
    except OSError:   # held by something (an editor, a second start): then it's overwritten as before
        pass


def setup_logging():
    keep_previous_log()
    logging.basicConfig(filename=BASE / LOG, filemode="w", encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    sys.excepthook = lambda *exc: log.error("Unexpected error", exc_info=exc)
    threading.excepthook = lambda a: log.error("Error in thread %s", a.thread.name,
                                               exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    log.info("Start, OpenCV %s, folder %s", cv2.__version__, BASE)
    try:   # hard crash (e.g. in Qt or the AI library): location of all threads to crash.log
        import faulthandler
        global _crash_file
        _crash_file = open(BASE / "crash.log", "a", encoding="utf-8")
        _crash_file.write(f"\n--- Start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)
    except OSError:
        pass


def main(MainWindow):   # the window class from app.py – not importable here (app runs as __main__)
    setup_threads()
    if sys.platform == "win32":  # own ID for the taskbar: it then shows our window icon instead of a
        try:                      # cached icon and groups all Bent°Corner windows together
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OliverS77.BentCorner")
        except Exception:
            pass
    # Without a real graphics driver Direct3D would be emulated on the CPU (WARP: 3–4 cores busy, on weak
    # machines ~30 frames/s). Qt Quick's software renderer is built for this: ~60 frames/s at 10–20 % of one core.
    if not any(os.environ.get(k) for k in ("QT_QUICK_BACKEND", "QSG_RHI_BACKEND", "QSG_RHI_PREFER_SOFTWARE_RENDERER")):
        from system import hwinfo
        if hwinfo.hardware_gpu() is False:
            os.environ["QT_QUICK_BACKEND"] = "software"
    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Bent°Corner")
    app.setStyle("Fusion")
    iconkit.follow_system(app)  # window icon for all windows (Library, dialogs, welcome) – light/dark like Windows
    try:  # load the appearance before all windows (fonts, corners, colours)
        look.load(_saved())
    except (OSError, ValueError, TypeError, AttributeError):
        look.load({})
    look.install_color_hook()
    refresh_color_consts()
    look.register_fonts()
    apply_look(app)
    try:  # accessibility layer off (caused crashes with Qt Quick) – unless explicitly wanted
        if not _saved().get("accessibility"):
            from ui import uiaguard
            uiaguard.install(app)
    except (OSError, ValueError):
        from ui import uiaguard
        uiaguard.install(app)
    if saved_language() == "de":  # Qt's own texts (file browser, colour picker …) in German
        tr_qt = QtCore.QTranslator(app)
        if tr_qt.load("qtbase_de", QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.TranslationsPath)):
            app.installTranslator(tr_qt)
            app._qt_translator = tr_qt
    # Only once per Windows user (ui/tray.py): before anything else – also before the first-run setup – and after a
    # restart only once the old instance is really gone (--after=<pid>; it never gets ended by force, lead 03.11.)
    from ui import tray
    after = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--after=")), "")
    if after.isdigit():
        from system import wipe
        if not wipe._wait_for(int(after), AFTER_WAIT):
            setup_logging()
            log.warning("Restart: the previous Bent°Corner (PID %s) is still running after %d s – this start stops "
                        "instead of running a second program on the same data", after, AFTER_WAIT)
            sys.exit(1)
    if "--move-data" not in sys.argv and "--selftest-ocr" not in sys.argv:
        if not tray.acquire():
            tray.show_other()
            sys.exit(0)  # already running (e.g. in the tray): that one now shows its window
        tray.claim()
    if "--move-data" in sys.argv:  # move the data folder (started by the program itself), then restart normally
        sys.exit(setupui.run_mover(sys.argv))
    if datahome.FIRST_RUN:  # first start: welcome, choose the data folder
        dlg = setupui.quick_first_run()
        if dlg is None:  # Qt Quick doesn't start here (then the program itself wouldn't work either)
            log.error("First-run setup: Qt Quick does not start")
            sys.exit(1)
        if not dlg.accepted:
            sys.exit(0)   # installer.json stays: closed without finishing, the next first start still takes it
        if datahome.installer_ours():
            datahome.drop_installer()   # setup 0.9.9: taken (or not usable) – gone either way
        home = dlg.result_home
        datahome.set_home(home)
        games_on = dlg.result_games or ["mtg"]
        # Language packs always included (better everything there than a card not recognised); the rest of the setup
        # (profile, friends, numbers, background) follows in the program window while the database loads (onboarding.py)
        first = {"scan_mode": "ai", "first_setup": True, "language": dlg.result_lang,
                 "game": games_on[0], "games_on": games_on, "onboarding": "profile",
                 "setup_steps": int(getattr(dlg, "result_steps", 5))}   # „Step n of m“ in the program window
        settings_file = home / "settings.json"
        if not settings_file.exists():
            settings_file.write_text(json.dumps(first, ensure_ascii=False), "utf-8")
        # restart once: all paths depend on the data folder, language and game are only settled now
        setupui.relaunch()
        sys.exit(0)
    if datahome.installer_ours():   # an existing user: an installer.json is never read, only removed (lead 13.11.)
        datahome.drop_installer()
    setup_logging()
    if os.environ.get("QT_QUICK_BACKEND") == "software":
        log.info("UI renders in software (no graphics driver found, or set that way)")
    from system import datastore
    try:  # one-off: switch German folder names in the data folder to English (backup first)
        if datastore.migrate_english():
            log.info("Data folder switched to English names")
    except Exception:
        log.exception("Renaming the data folder failed")
    try:  # quiet backup of personal data (at most every 6 hours, the last 7 are kept)
        datastore.maybe_snapshot()
    except Exception:
        log.exception("Silent backup failed")
    try:  # formerly bundled sample friends and lists no longer exist (after the backup, so reversible)
        from collection import trade
        if trade.drop_examples():
            log.info("Sample friends/lists removed")
    except Exception:
        log.exception("Removing samples failed")
    # Quit only via request_quit (saving; closing the window can also mean "to the tray")
    app.setQuitOnLastWindowClosed(False)
    app.main_window = MainWindow()  # shows the program window (scanning) itself
    if "--selftest-ocr" in sys.argv:  # test of the .exe: loads text recognition and reads a test image
        def ocr_test():
            try:
                img = np.full((200, 600, 3), 255, np.uint8)
                cv2.putText(img, "FRA EN 0157", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
                log.info("OCR self-test: %s", ocrscan.run(img, use_cls=True)[0])
            except Exception:
                log.exception("OCR self-test")
            app.main_window.force_quit = True
            app.main_window.request_quit()
        QtCore.QTimer.singleShot(6000, ocr_test)
    if "--selftest-restart" in sys.argv:  # test: check restarting the .exe (language change) without clicking
        sys.argv.remove("--selftest-restart")
        QtCore.QTimer.singleShot(8000, app.main_window.restart)
    code = app.exec()
    # Everything is already saved (request_quit). After that don't let all Qt objects be cleaned up one by one: Python
    # deletes them in random order, then Qt Quick parts access already deleted ones (crash on exit).
    try:
        from scanner import aiworker
        aiworker.stop()   # also stop the AI process (otherwise it also ends itself as soon as we're gone)
    except Exception:  # noqa: BLE001
        pass
    logging.shutdown()
    for stream in (sys.stdout, sys.stderr):  # in the .exe without a console neither exists (None)
        try:
            stream.flush()
        except Exception:  # noqa: BLE001
            pass
    from ui import uiaguard
    uiaguard.hard_exit(code)
