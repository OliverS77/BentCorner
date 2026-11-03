"""Where the data lives: collection, sessions, settings, card data and card images (the "data folder").

Order:
  1. If data already sits next to the .exe (settings.json or data/), the program counts as portable – as before.
  2. Otherwise the folder chosen at first start; a small file in the user profile remembers it
     (Windows: %APPDATA%\\BentCorner\\datenordner.json).
  3. If neither exists, it is the first start: suggestion Documents\\BentCorner, the welcome window asks.
During development (without .exe) the data sits next to the scripts as always.

All paths in the program are relative to this folder (e.g. data/card-images/fin/18_0.jpg) – that is why it can be
moved without the collection or sessions changing.

Test start "like the first time" (BentCorner.exe --first-run-test, also during development): the real data and the
pointer file stay untouched. Everything lives in a throwaway folder (%TEMP%\\BentCorner-Erststart-Test); the suggestions
"Documents" and "Next to the program" point there too, and the choice is remembered in a separate test pointer file.
Every new test start begins from scratch; only the restart in the middle of setup (--continue-test) continues.
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile

FROZEN = getattr(sys, "frozen", False)
# The .exe you start: the launcher (launcher/) places the actual program once per version in
# "Bent°Corner Essentials" and starts it from there – and tells it via BENTCORNER_EXE where the launcher itself is.
# Restart, update and autostart always go through this file; the data folder "next to the program" sits beside it.
EXE = pathlib.Path(os.environ.get("BENTCORNER_EXE") or sys.executable).resolve() if FROZEN else None
APP_DIR = EXE.parent if FROZEN else pathlib.Path(__file__).resolve().parents[1]
TEST = "--first-run-test" in sys.argv
TEST_ROOT = pathlib.Path(tempfile.gettempdir()) / "BentCorner-Erststart-Test"
# Isolated test run of the exe (never Oliver's real folders): the same switches as the launcher (Launcher.cs) –
# BC_STARTER_ROAMING replaces %APPDATA% (datenordner.json), BC_STARTER_DOCUMENTS replaces "Documents" (only the
# suggestion on a first start), BC_STARTER_LOCAL is read by the launcher. Unset = nothing changes.
ISOLATED = any(os.environ.get(v, "").strip() for v in ("BC_STARTER_LOCAL", "BC_STARTER_ROAMING", "BC_STARTER_DOCUMENTS"))


def _env_dir(name):
    v = os.environ.get(name, "").strip()
    return pathlib.Path(v) if v else None


def _config_dir():
    if _env_dir("BC_STARTER_ROAMING"):
        return _env_dir("BC_STARTER_ROAMING") / "BentCorner"
    if sys.platform == "win32":
        return pathlib.Path(os.environ.get("APPDATA") or pathlib.Path.home() / "AppData" / "Roaming") / "BentCorner"
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library" / "Application Support" / "BentCorner"
    return pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config") / "bentcorner"


POINTER = _config_dir() / ("datenordner-test.json" if TEST else "datenordner.json")


def documents():
    """The "Documents" folder (on Windows also when it is redirected, e.g. to OneDrive)."""
    if _env_dir("BC_STARTER_DOCUMENTS"):
        return _env_dir("BC_STARTER_DOCUMENTS")
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
            docs = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(docs), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                return pathlib.Path(path)
        except Exception:
            pass
    return pathlib.Path.home() / "Documents"


DEFAULT = TEST_ROOT / "Dokumente" / "BentCorner" if TEST else documents() / "BentCorner"
PORTABLE = TEST_ROOT / "Neben-dem-Programm" if TEST else APP_DIR   # suggestion "next to the program"


def has_data(folder):
    folder = pathlib.Path(folder)
    return (folder / "settings.json").exists() or (folder / "data").is_dir()


def _resolve():
    """-> (data folder, first start?)"""
    if TEST:
        if "--continue-test" not in sys.argv:   # new test start: remove everything from last time
            POINTER.unlink(missing_ok=True)
            shutil.rmtree(TEST_ROOT, ignore_errors=True)
        try:
            p = pathlib.Path(json.loads(POINTER.read_text("utf-8"))["home"])
            if p.is_dir():
                return p, False
        except (OSError, ValueError, KeyError):
            pass
        return DEFAULT, True
    if not FROZEN:
        # during development: BC_HOME = a different data folder (e.g. a sanitized copy of real data for measuring)
        if os.environ.get("BC_HOME"):
            return pathlib.Path(os.environ["BC_HOME"]), False
        return APP_DIR, False
    if has_data(APP_DIR):
        return APP_DIR, False
    try:
        p = pathlib.Path(json.loads(POINTER.read_text("utf-8"))["home"])
        if p.is_dir():
            return p, False
    except (OSError, ValueError, KeyError):
        pass
    return DEFAULT, True


def program():
    """What is called to (re)start: the .exe you start (the launcher), Python during development."""
    return str(EXE) if FROZEN else sys.executable


def restart_args():
    """Extra args for a program restart: in a test start, stay in the test (otherwise it would be the real data)."""
    return ["--first-run-test", "--continue-test"] if TEST else []


def set_home(folder):
    """Remember the chosen data folder for the next starts."""
    POINTER.parent.mkdir(parents=True, exist_ok=True)
    POINTER.write_text(json.dumps({"home": str(pathlib.Path(folder).resolve())}, ensure_ascii=False), "utf-8")


HOME, FIRST_RUN = _resolve()
