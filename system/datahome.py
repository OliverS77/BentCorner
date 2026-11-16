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
# A test copy stays a test copy however it is started (Oliver 05.11.2026: a double click on the test exe used the real
# %LOCALAPPDATA% and the real single-instance lock and blocked his app). Erststart.cmd / Start.cmd write
# bc-testkopie.txt next to the test starter; the launcher copies it into "Bent°Corner Essentials". Only these keys,
# only when none of BC_STARTER_* is set already; a release install has no such file and nothing changes.
TEST_MARKER = "bc-testkopie.txt"
MARKER_KEYS = ("BC_STARTER_LOCAL", "BC_STARTER_ROAMING", "BC_STARTER_DOCUMENTS", "BC_LOCAL_DL", "BC_CHECK",
               "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")
STARTER_KEYS = MARKER_KEYS[:3]


def read_marker(path):
    """bc-testkopie.txt -> {key: value} (KEY=value lines, unknown keys ignored; folders must be absolute) or None."""
    try:
        text = pathlib.Path(path).read_text("utf-8-sig")
    except OSError:
        return None
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if sep and key in MARKER_KEYS:
            if key in STARTER_KEYS + ("BC_LOCAL_DL",) and not (value and os.path.isabs(value)):
                return None   # a broken marker isolates nothing – then rather none at all
            out[key] = value
    return out if all(out.get(k) for k in STARTER_KEYS) else None


def apply_marker(exe):
    """Started without the test switches? Look for bc-testkopie.txt next to the exe (launcher, or the program in
    "Bent°Corner Essentials") and one folder up (the program in its version folder) -> applied file or None."""
    if any(os.environ.get(k, "").strip() for k in STARTER_KEYS):
        return None
    exe = pathlib.Path(exe)
    for folder in (exe.parent, exe.parent.parent):
        found = read_marker(folder / TEST_MARKER)
        if found:
            os.environ.update(found)
            return folder / TEST_MARKER
    return None


MARKER = apply_marker(os.environ.get("BENTCORNER_EXE") or sys.executable) if FROZEN else None
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
# Setup 0.9.9 (lead 13.11./14.11.2026): the Inno installer writes the language and the storage location it asked for
# – {"v": 1, "lang": "de", "home": "…"} – only on a NEW installation (no datenordner.json yet). The app reads it on its
# first start (ui/setupui.py) and deletes it once the setup is done; an existing user deletes it unread (startup.py).
INSTALLER = _config_dir() / ("installer-test.json" if TEST else "installer.json")


def read_installer():
    """installer.json -> {"lang": code or None, "home": absolute Path or None}, or None (no file / unreadable).
    Only the language and the path are taken – nothing else. UTF-8 (also with a BOM); an old installer's ANSI file
    (Inno SaveStringToFile) still reads through the Windows code page."""
    try:
        raw = INSTALLER.read_bytes()
    except OSError:
        return None
    for enc in ("utf-8-sig", "mbcs" if sys.platform == "win32" else "cp1252", "cp1252"):
        try:
            d = json.loads(raw.decode(enc))
            break
        except (UnicodeDecodeError, ValueError, LookupError):
            continue
    else:
        return None
    if not isinstance(d, dict):
        return None
    import locales
    lang = d.get("lang") if d.get("lang") in {c for c, _ in locales.all_languages()} else None
    home = d.get("home")
    home = pathlib.Path(home) if isinstance(home, str) and home.strip() and os.path.isabs(home) else None
    return {"lang": lang, "home": home}


def installer_ours():
    """Is installer.json this copy's business? The installed program (an installer only ever writes it for itself) or
    a first-start test (installer-test.json); never a portable copy, never a source start (the real file)."""
    return TEST or (FROZEN and PORTABLE is None)


def drop_installer():
    """Delete installer.json (after the setup, or unread for an existing user). Never raises."""
    try:
        INSTALLER.unlink(missing_ok=True)
    except OSError:
        pass


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
# Installed by the setup (Inno: unins000.exe next to the program): the program folder is deleted on uninstalling – no
# data ever lives there, so no "next to the program" either (lead 06.11.2026)
INSTALLED = bool(FROZEN and (APP_DIR / "unins000.exe").exists())
PORTABLE = TEST_ROOT / "Neben-dem-Programm" if TEST else None if INSTALLED else APP_DIR   # "next to the program"


# folders only Bent°Corner puts into its data/ – a "data" folder without any of them isn't ours (review 08.11. F9:
# with D:\ chosen as the data folder, "Delete Bent°Corner" must never take an unrelated D:\data along)
OURS = ("my-data", "card-data", "card-images", "games")


def ours(data):
    """Is this data/ folder Bent°Corner's? (one of its own subfolders is in it)"""
    data = pathlib.Path(data)
    return data.is_dir() and any((data / n).is_dir() for n in OURS)


def has_data(folder):
    folder = pathlib.Path(folder)
    return (folder / "settings.json").exists() or (folder / "data").is_dir()


def in_program(folder):
    """Is `folder` the installed program's folder or inside it? (never a data folder: uninstalling deletes it)"""
    if not INSTALLED:
        return False
    try:
        f, a = pathlib.Path(folder).resolve(), APP_DIR.resolve()
    except OSError:
        return False
    return f == a or a in f.parents


def _selftest_home():
    """`--selftest-scan … --selftest-data=<folder>` (system/selftest.py, the Win10 test stick): exactly that folder –
    never next to the program, never the remembered or the suggested one, nothing written about it. None otherwise."""
    if "--selftest-scan" not in " ".join(sys.argv):
        return None
    v = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--selftest-data=")), "")
    if not v or not os.path.isabs(v):
        sys.exit("--selftest-scan needs --selftest-data=<absolute folder>")
    return pathlib.Path(v)


def _resolve():
    """-> (data folder, first start?)"""
    if _selftest_home() is not None:
        return _selftest_home(), False
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
    if has_data(APP_DIR) and not INSTALLED:
        return APP_DIR, False
    try:
        p = pathlib.Path(json.loads(POINTER.read_text("utf-8"))["home"])
        if p.is_dir() and not in_program(p):
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
    if in_program(folder):   # last line of defence: uninstalling would delete it
        raise ValueError(f"not a data folder (inside the installed program): {folder}")
    POINTER.parent.mkdir(parents=True, exist_ok=True)
    POINTER.write_text(json.dumps({"home": str(pathlib.Path(folder).resolve())}, ensure_ascii=False), "utf-8")


# ---------- Collections already on this PC (first start: never silently begin empty, lead 06.11.2026) ----------
_DESKTOP = (0xB4BFCC3A, 0xDB2C, 0x424C, (0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41))
_DOWNLOADS = (0x374DE290, 0x123F, 0x4565, (0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
SCAN_LIMIT = 300   # entries looked at per folder (Desktop, Downloads): a quick look, not a search of the disk


def _known_folder(guid, fallback):
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
            g = GUID(guid[0], guid[1], guid[2], (ctypes.c_ubyte * 8)(*guid[3]))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                return pathlib.Path(path)
        except Exception:
            pass
    return pathlib.Path.home() / fallback


def _local_home():
    """Where the old single-exe starter kept its notes (%LOCALAPPDATA%\\BentCorner, or BC_STARTER_LOCAL)."""
    return _env_dir("BC_STARTER_LOCAL") or pathlib.Path(os.environ.get("LOCALAPPDATA") or
                                                         pathlib.Path.home() / "AppData" / "Local") / "BentCorner"


def _read_path(file):
    try:
        v = pathlib.Path(file).read_text("utf-8-sig").strip().splitlines()[0].strip()
        return pathlib.Path(v) if v and os.path.isabs(v) else None
    except (OSError, IndexError):
        return None


def _candidates():
    """Places a collection may lie: the remembered folder, Documents, what the old starter noted (its "Essentials" lie
    right next to the data; installation.txt names the folder of the starter exe), %LOCALAPPDATA%\\BentCorner,
    and Desktop/Downloads one level deep. Only looked at – nothing leaves the PC, nothing is copied or moved."""
    out = []
    try:
        out.append(pathlib.Path(json.loads(POINTER.read_text("utf-8"))["home"]))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    out.append(DEFAULT)
    if TEST:   # first-start test: only its own throwaway folder (the starter notes are the real ones)
        return out
    local = _local_home()
    notes = sorted(local.glob("essentials-*.txt")) + [local / "essentials.txt"] if local.is_dir() else []
    for note in notes:
        ess = _read_path(note)
        if ess is not None:
            out.append(ess.parent)
            prog = _read_path(ess / "installation.txt")
            if prog is not None:
                out.append(prog)
    out.append(local)
    # a test copy (BC_STARTER_* folders) or a first-start test never looks at the real Desktop/Downloads – it would
    # offer the real collection
    bases = () if (TEST or ISOLATED) else (_known_folder(_DESKTOP, "Desktop"), _known_folder(_DOWNLOADS, "Downloads"))
    for base in bases:
        try:
            for n, sub in enumerate(base.iterdir()):
                if n >= SCAN_LIMIT:
                    break
                if sub.is_dir() and (sub / "settings.json").is_file():
                    out.append(sub)
        except OSError:
            pass
    return out


def card_count(folder):
    """Copies in a data folder's collections (all games) – for the line "… · 1.234 cards"."""
    n = 0
    data = pathlib.Path(folder) / "data"
    files = [data / "my-data" / "collection.json"] + sorted((data / "games").glob("*/my-data/collection.json"))
    for f in files:
        try:
            n += sum(int(it.get("count", 1)) for it in json.loads(f.read_text("utf-8")).get("items", []))
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    return n


def existing():
    """Collections already on this PC -> [{"path", "cards", "changed" (time of settings.json or 0), "reachable"}]:
    the remembered folder first (also when it can't be reached right now – a drive not plugged in), then the most
    recently used. Never the installed program's folder, never the first-start test folder."""
    remembered = None
    try:
        remembered = pathlib.Path(json.loads(POINTER.read_text("utf-8"))["home"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    seen, out = set(), []
    for c in _candidates():
        try:
            key = os.path.normcase(str(c.resolve()))
        except OSError:
            key = os.path.normcase(str(c))
        if key in seen or in_program(c) or TEST_ROOT in [c, *c.parents]:
            continue
        seen.add(key)
        reachable = c.is_dir()
        if reachable and not has_data(c):
            continue
        if not reachable and c != remembered:
            continue
        try:
            changed = (c / "settings.json").stat().st_mtime if reachable else 0
        except OSError:
            changed = 0
        out.append({"path": c, "cards": card_count(c) if reachable else 0, "changed": changed, "reachable": reachable})
    out.sort(key=lambda e: (e["path"] != remembered, -e["changed"]))
    return out


HOME, FIRST_RUN = _resolve()
