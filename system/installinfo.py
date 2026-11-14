"""The installed program (Inno Setup, labs/installer/PLAN.md): the move from the old starter, and the uninstaller.

    after_move(settings) -> bool       first start of the installed program: tidy up "Bent°Corner Essentials" (the
                                       old starter's program copies) and say once what changed -> True: show the note
    uninstaller() -> path | None       unins000.exe next to the program (installed copies only)
    start_uninstall(server_done)       „Bent°Corner löschen“: the uninstaller, told whether the server part is done

The data folder is never touched here. Essentials only goes when it holds nothing but the starter's own files
(version folders <version>-<time>, BentCorner.exe, current.txt, installation.txt); anything else -> it stays (log).
"""
import logging
import os
import pathlib
import re
import shutil
import subprocess
import sys

from system import datahome

log = logging.getLogger("booster")
ESSENTIALS = "Bent°Corner Essentials"
# bc-testkopie.txt: the marker an isolated test copy writes next to the program (datahome.apply_marker) – ours as well
# (lead 14.11.: otherwise a test copy's Essentials stays and the move note never shows)
OURS = re.compile(r"^(\d+\.\d+(\.\d+)*-\d{10}|BentCorner\.exe|BentCorner\.old\.exe|current\.txt|installation\.txt"
                  r"|bc-testkopie\.txt)$")
NOTE_KEY = "installed_note"   # settings: the note about the move was shown


def _program_dir():
    return pathlib.Path(sys.executable).resolve().parent


def installed():
    return getattr(sys, "frozen", False) and (_program_dir() / "unins000.exe").exists()


def _essentials_folders():
    local = os.environ.get("BC_STARTER_LOCAL", "").strip()
    local_home = pathlib.Path(local) if local else pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "BentCorner"
    return [pathlib.Path(datahome.HOME) / ESSENTIALS, local_home / ESSENTIALS]


def tidy_essentials():
    """Remove the old starter's program copies – only if the folder holds nothing else. -> folders removed"""
    gone = []
    for f in _essentials_folders():
        if not f.is_dir():
            continue
        others = [p.name for p in f.iterdir() if not OURS.match(p.name)]
        if others:
            log.info("Essentials kept (not only ours): %s – %s", f, others[:5])
            continue
        try:
            shutil.rmtree(f)
            gone.append(str(f))
        except OSError as e:
            log.info("Essentials not removed (%s): %s", e, f)
    return gone


def after_move(settings):
    """First start of an installed copy: tidy up, and True once – the note „Ab jetzt wird Bent°Corner richtig
    installiert …“ (legal 03.11.2026) is shown then."""
    if not installed():
        return False
    removed = tidy_essentials()
    if removed:
        log.info("Moved to the installer: removed %s", removed)
    if settings.get(NOTE_KEY):
        return False
    settings[NOTE_KEY] = True
    return bool(removed)   # only those who came from the starter get the note – a fresh install needs none


def uninstaller():
    u = _program_dir() / "unins000.exe"
    return u if installed() and u.exists() else None


def start_uninstall(server_done):
    """Start the uninstaller (its window) – server_done: „Bent°Corner löschen“ already did the server part, so its
    page shows no checkbox again. The program quits right after (the uninstaller waits for it)."""
    u = uninstaller()
    if u is None:
        return False
    args = [str(u)] + (["/BCSERVER=done"] if server_done else [])
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(args, creationflags=flags, close_fds=True)
    return True
