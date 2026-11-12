"""„Bent°Corner löschen“ – the part on this PC (labs/installer/PLAN.md § 5, texts legal 03.11.2026): the collection and
settings, never anything else.

    plan(settings) -> Plan            what would go, what stays, the latest backup and whether it goes along
    remember_backup(settings, path)   note a backup made by hand („Sicherung jetzt erstellen“) – latest_backup
                                      counts it as long as it is still there
    start_after_exit(plan)            hand the plan to `BentCorner.exe --wipe-local <file>`: it waits until this program
                                      has ended (open databases can't be deleted on Windows), then deletes
    wipe(plan) -> [errors]            the deleting itself (also used by the tests – only on test folders)
    main()                            the `--wipe-local` process

Deleted are exactly: settings.json and data/ in the data folder (collection, card data, images, silent backups),
%APPDATA%\\BentCorner (where the data folder is noted) and %LOCALAPPDATA%\\BentCorner (launcher notes). The data folder
itself only goes when it is empty afterwards – other files in it stay. Backups in other folders (automatic backup
targets) always stay; legal: the text says "will be kept" only for those.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

from scanner.common import BASE
from system import datahome, datastore


@dataclass
class Plan:
    folder: str                                   # the data folder (shown in the texts)
    delete: list = field(default_factory=list)    # paths that go
    backup: str = ""                              # the latest backup (file), "" = none
    backup_time: float = 0.0
    backup_goes: bool = False                     # it lies in a path that goes (legal: say so, offer "Save elsewhere")
    tidy: list = field(default_factory=list)      # folders removed afterwards only if empty

    def to_json(self):
        return json.dumps(self.__dict__, ensure_ascii=False)


def _local_home():
    v = os.environ.get("BC_STARTER_LOCAL", "").strip()
    return pathlib.Path(v) if v else pathlib.Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "BentCorner"


# What the starter (Launcher.cs: LocalHome) and the first start (setupui._note) put into the local home
LOCAL_OURS = re.compile(r"^(Bent°Corner Essentials|essentials(-[0-9a-f]{16})?\.txt|starter\.log|firstrun\.log"
                        r"|inst-[0-9a-f]{16})$")


def _local_targets():
    """-> (paths that go, folder removed if empty). %LOCALAPPDATA%\\BentCorner is ours as a whole; a folder named by
    BC_STARTER_LOCAL (test copies – or someone setting it from outside, lead 06.11.) only with our own entries in it,
    so an environment variable can never point "Delete Bent°Corner" at a foreign folder."""
    home = _local_home()
    if not os.environ.get("BC_STARTER_LOCAL", "").strip():
        return [home], []
    if not home.is_dir():
        return [], []
    return sorted(p for p in home.iterdir() if LOCAL_OURS.match(p.name)), [home]


def _inside(path, parents):
    p = os.path.normcase(os.path.abspath(path))
    return any(p == os.path.normcase(os.path.abspath(q)) or p.startswith(os.path.normcase(os.path.abspath(q)) + os.sep)
               for q in parents)


def remember_backup(settings, path):
    """A backup made by hand into a folder of the user's choice: where and when (settings) – latest_backup knows it."""
    settings["last_backup"] = time.time()
    settings["last_backup_path"] = str(path)


def latest_backup(settings):
    """(path, time) of the newest backup we know of – silent ones in data/backups, the automatic backup targets and
    the last one made by hand (remember_backup) while it still exists."""
    from system import autobackup
    found = []
    if pathlib.Path(datastore.BACKUPS).is_dir():
        found += [(f, f.stat().st_mtime) for f in pathlib.Path(datastore.BACKUPS).rglob("*.zip")]
    for t in autobackup.cfg(settings).get("targets", []):
        folder = pathlib.Path(t["path"]) / autobackup.FOLDER
        if folder.is_dir():
            found += [(f, f.stat().st_mtime) for f in folder.glob("BentCorner backup *.zip")]
    hand = settings.get("last_backup_path")
    if hand and pathlib.Path(hand).exists():
        found.append((pathlib.Path(hand), float(settings.get("last_backup") or pathlib.Path(hand).stat().st_mtime)))
    best = max(found, key=lambda x: x[1], default=None)
    return (str(best[0]), best[1]) if best else ("", 0.0)


def plan(settings):
    base = pathlib.Path(BASE)
    local, tidy = _local_targets()
    delete = [str(p) for p in (base / "settings.json", base / "data", datahome._config_dir(), *local) if p.exists()]
    backup, when = latest_backup(settings)
    return Plan(folder=str(base), delete=delete, backup=backup, backup_time=when,
                backup_goes=bool(backup) and _inside(backup, delete), tidy=[str(d) for d in tidy])


def wipe(p):
    """Delete the planned paths; -> list of problems (empty = everything gone). The data folder goes if empty."""
    errors = []
    for path in p.delete:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.exists(path):
                os.remove(path)
        except OSError as e:
            errors.append(f"{path}: {e}")
    for folder in [*p.tidy, p.folder]:
        try:
            if os.path.isdir(folder) and not os.listdir(folder):
                os.rmdir(folder)
        except OSError:
            pass
    return errors


def start_after_exit(p):
    """Write the plan and start `--wipe-local`; it waits for this process to end, then deletes."""
    f = pathlib.Path(tempfile.gettempdir()) / f"bentcorner-wipe-{os.getpid()}.json"
    f.write_text(p.to_json(), "utf-8")
    exe = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(pathlib.Path(__file__).parents[1] / "app.py")]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([*exe, "--wipe-local", str(f), str(os.getpid())], creationflags=flags, close_fds=True)


def _wait_for(pid, seconds=60):
    """Wait until process `pid` has ended (never os.kill(pid, 0): on Windows that sends Ctrl+C). -> ended?"""
    if sys.platform == "win32":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
        if not h:
            return True   # gone already
        try:
            return k32.WaitForSingleObject(h, int(seconds * 1000)) == 0
        finally:
            k32.CloseHandle(h)
    end = time.time() + seconds
    while time.time() < end:
        try:
            os.kill(pid, 0)   # POSIX: signal 0 only checks
        except OSError:
            return True
        time.sleep(0.5)
    return False


def main():
    """`--wipe-local <plan file> <pid>`: wait for the program to end, delete, leave a short note in %TEMP%."""
    i = sys.argv.index("--wipe-local")
    plan_file, pid = pathlib.Path(sys.argv[i + 1]), int(sys.argv[i + 2])
    p = Plan(**json.loads(plan_file.read_text("utf-8")))
    # only what this process would plan itself: a plan file written by someone else deletes nothing foreign
    own = plan({})
    p.delete = [x for x in p.delete if x in own.delete]
    p.tidy = [x for x in p.tidy if x in own.tidy]
    p.folder = own.folder
    _wait_for(pid)
    errors = []
    for _ in range(5):   # a virus scanner or the indexer may hold a file for a moment
        errors = wipe(p)
        if not errors:
            break
        time.sleep(2)
    note = pathlib.Path(tempfile.gettempdir()) / "bentcorner-wipe-result.txt"
    note.write_text("ok\n" if not errors else "\n".join(errors) + "\n", "utf-8")
    plan_file.unlink(missing_ok=True)
    raise SystemExit(0 if not errors else 1)
