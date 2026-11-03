"""Automatic backup: everything personal (all games) silently as a ZIP to up to three places – USB stick, external
drive, cloud folder (OneDrive, Google Drive, Dropbox … – whatever appears as a folder on the PC). Bent°Corner stores
nothing on its side; this makes sure a broken PC does not cost you the collection.

settings["autobackup"] = {"on": True, "every": "change" | "daily" | "weekly",
                          "targets": [{"path", "ok" (time of the last backup), "error", "tried", "sum"}]}
- Runs in the background: at startup, and when something has changed since then (collection, session, import …)
  after the configured interval – "change" (the default for new setups since 0.9.2.99): 2 minutes after the last
  change. Only when the content really differs from the last backup at that target (checksum, "sum"). No window,
  no notice – only the status in Settings → Backup. Never alongside a running camera/scan or the game (the caller
  waits); the worker thread runs in Windows' background mode (CPU and disk at low priority).
- Closing the app: one last backup if something changed, at most 8 s – otherwise caught up at the next start.
- Target not present right now (stick not plugged in): skipped and caught up as soon as it is back.
- Kept per target: the last 5 backups, at most one per hour – a new one within the same hour replaces the last
  (Oliver, 29.10.: enough with a backup after every change; older ones only cost space on the stick).
- Each ZIP carries manifest.json (time, checksum, app version; address and vault version for the later sync).
"""
import datetime
import os
import pathlib
import threading
import time

FOLDER = "BentCorner backups"
MAX_TARGETS = 3
QUIET = 120                 # "change": back up once the data has been still this long (seconds)
EVERY = {"change": QUIET, "daily": 20 * 3600, "weekly": 6.5 * 86400}
EVERY_NAMES = (("change", "nach jeder Änderung (2 Minuten danach)"), ("daily", "täglich"), ("weekly", "wöchentlich"))
EXIT_LIMIT = 8.0            # closing the app: at most this long for the last backup
KEEP = 5                    # backups kept per target (at most one per hour)
STALE = 14 * 86400          # this long without a backup at a target: notice on the profile
CLOUD_HINTS = ("onedrive", "dropbox", "google drive", "googledrive", "my drive", "meine ablage", "icloud", "nextcloud",
               "pcloud", "mega", "box")
_lock = threading.Lock()


def cfg(settings):
    c = settings.setdefault("autobackup", {})
    c.setdefault("on", True)
    c.setdefault("every", "change")   # new setups; existing ones keep what they had (it is stored)
    c.setdefault("targets", [])
    return c


def add_target(settings, path):
    c = cfg(settings)
    path = os.path.normpath(str(path))
    if any(os.path.normcase(t["path"]) == os.path.normcase(path) for t in c["targets"]):
        return False
    if len(c["targets"]) >= MAX_TARGETS:
        return False
    c["targets"].append({"path": path, "ok": 0, "error": "", "tried": 0, "added": time.time()})
    return True


def remove_target(settings, path):
    c = cfg(settings)
    c["targets"] = [t for t in c["targets"] if t["path"] != path]


def kind(path):
    """'cloud', 'other' (different drive: stick, external drive, network drive) or 'same' (same drive as the
    data – does not protect against a broken hard drive)."""
    from scanner import common
    low = str(path).lower()
    if any(h in low for h in CLOUD_HINTS):
        return "cloud"
    drive = os.path.splitdrive(os.path.abspath(path))[0].lower()
    data_drive = os.path.splitdrive(os.path.abspath(common.DATA))[0].lower()
    return "same" if drive and drive == data_drive else "other"


def available(path):
    """Is the target reachable right now? (stick plugged in, network drive present) – creates the subfolder."""
    p = pathlib.Path(path)
    if not p.exists():
        return False
    try:
        (p / FOLDER).mkdir(exist_ok=True)
        return True
    except OSError:
        return False


def due(settings, changed_since):
    """Should a backup run now? changed_since = time of the last change to the data (0 = unknown)."""
    c = cfg(settings)
    if not c["on"] or not c["targets"]:
        return False
    gap = EVERY.get(c["every"], EVERY["daily"])
    now = time.time()
    for t in c["targets"]:
        if not pathlib.Path(t["path"]).exists():   # stick not plugged in: not due, catch up later
            continue
        last = float(t.get("ok") or 0)
        if not last:
            return True
        if c["every"] == "change":   # once the data has been still for QUIET seconds after a change
            if changed_since == 0 or (changed_since > last and now - changed_since >= QUIET):
                return True
            continue
        if now - last >= gap and (changed_since == 0 or changed_since > last):
            return True
    return False


def content_sum():
    """SHA-256 over everything personal that a backup holds – without settings.json (the backup itself writes its
    time there) and without the trash: equal sum = nothing new to back up."""
    import hashlib
    from system import datastore
    h = hashlib.sha256()
    for p, name in datastore.personal_roots():
        if name == "settings.json":
            continue
        files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file())
        for f in files:
            rel = f.relative_to(p).as_posix() if f != p else ""
            if "trash" in rel.split("/") or f.name.endswith((".tmp", ".partial")):
                continue
            try:
                data = f.read_bytes()
            except OSError:
                continue
            h.update(f"{name}/{rel}|{len(data)}|".encode())
            h.update(data)
    return h.hexdigest()


def _prune(folder):
    """Keep the last KEEP backups, at most one per hour: within an hour only the newest stays (a new backup in the
    same hour replaces the one before)."""
    files = sorted((f for f in folder.glob("BentCorner backup *.zip")), key=lambda f: f.stat().st_mtime, reverse=True)
    hours = {}
    for f in files:   # sorted newest first: the first one per hour is its newest
        hours.setdefault(datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H"), f)
    keep = {f for _, f in sorted(hours.items(), reverse=True)[:KEEP]}
    for f in files:
        if f not in keep:
            try:
                f.unlink()
            except OSError:
                pass
    for f in folder.glob("*.partial"):   # leftovers from aborted runs
        try:
            if time.time() - f.stat().st_mtime > 3600:
                f.unlink()
        except OSError:
            pass


def run(settings, force=False, only_changed=True):
    """Back up (call in a background thread). -> [(path, ok?, text)]. force: even if not due. only_changed: skip a
    target whose last backup has exactly this content (checksum) – "Back up now" by hand passes False."""
    from system import datastore
    c = cfg(settings)
    out = []
    if not _lock.acquire(blocking=False):
        return out
    try:
        gap = EVERY.get(c["every"], EVERY["daily"])
        zip_tmp = None
        total = None
        for t in c["targets"]:
            now = time.time()
            if not force and t.get("ok") and now - float(t["ok"]) < gap:
                continue
            if only_changed and t.get("sum"):
                total = total or content_sum()
                if t["sum"] == total:   # nothing new since the last backup there
                    continue
            t["tried"] = now
            if not available(t["path"]):
                t["error"] = "nicht erreichbar"
                out.append((t["path"], False, t["error"]))
                continue
            folder = pathlib.Path(t["path"]) / FOLDER
            name = f"BentCorner backup {time.strftime('%Y-%m-%d %H-%M')}.zip"
            try:
                if zip_tmp is None:   # pack once, then copy to all targets
                    import tempfile
                    total = total or content_sum()
                    zip_tmp = pathlib.Path(tempfile.gettempdir()) / f"bentcorner-backup-{os.getpid()}.zip"
                    datastore.write_zip(zip_tmp, manifest=_manifest(settings, total))
                import shutil
                part = folder / (name + ".partial")
                shutil.copyfile(zip_tmp, part)
                os.replace(part, folder / name)
                _prune(folder)
                t["ok"], t["error"], t["sum"] = time.time(), "", total
                out.append((t["path"], True, name))
            except OSError as e:
                t["error"] = str(e)[:120]
                out.append((t["path"], False, t["error"]))
        if zip_tmp is not None:
            try:
                zip_tmp.unlink()
            except OSError:
                pass
    finally:
        _lock.release()
    return out


def _manifest(settings, total):
    """What §4 of docs/SYNC-PLAN.md needs to judge a backup later: when, which content, which address/vault version."""
    import version
    address = None
    if (settings.get("relay") or {}).get("seed"):   # only an identity that exists – never create one here
        try:
            from net import relay
            address = relay.my_code(settings)
        except Exception:  # noqa: BLE001 – no PyNaCl …: the backup works without it
            address = None
    return {"v": 1, "time": time.time(), "sum": total, "app": version.VERSION,
            "address": address, "vault_version": settings.get("vault_version")}


def background_thread():
    """The calling thread at low priority (Windows: background mode – CPU and disk I/O), so a scan never feels it."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetThreadPriority(k.GetCurrentThread(), 0x00010000)   # THREAD_MODE_BACKGROUND_BEGIN
    except (OSError, AttributeError):
        pass


UNSAVED_GRACE = 30 * 60     # new data may stay without a backup this long before the exclamation mark appears


def last_change():
    """Time of the last change to data that cannot be downloaded again (collection, sessions, decks, lists,
    trades …) – taken from the file times so it is still correct after a restart. The trash does not count."""
    from system import undo
    from system import datastore
    newest = float(undo.LAST_WRITE[0] or 0)
    for p, name in datastore.personal_roots():
        if name == "settings.json":
            continue
        try:
            for f in p.rglob("*.json") if p.is_dir() else [p]:
                if "trash" in f.parts:
                    continue
                newest = max(newest, f.stat().st_mtime)
        except OSError:
            pass
    return newest


# The lamp on "Backup" (Settings button + tab) – Oliver, 29.10.: outside Full Orbit it stays on even after you have looked
# at the section; in Full Orbit it goes out once you were there and could read that the online backup is deleted 6 months
# after last use. The online backup comes with the sync plan (docs/SYNC-PLAN.md) – until then Full = Near/Core.
ONLINE_BACKUP = False
# Oliver, 29.10.: the lamp goes out as soon as a backup target is set up – it then runs in the background, "that's it".
# The same drive is allowed (a second disk or an external one that shows up as a local drive is enough for many): only a
# hint, the lamp still goes out. It comes back only if no backup has worked for 14 days (stick gone, folder missing) –
# that is an error, not a missing set-up. False = always on outside Full Orbit (the first reading of the rule).
LOCAL_OK_CLEARS = True


def _failing(c, now):
    """No backup has worked anywhere for 14 days – counted from the last success, or from setting the target up."""
    oks = [float(t.get("ok") or 0) for t in c["targets"] if t.get("ok")]
    since = max(oks) if oks else min(float(t.get("added") or t.get("tried") or now) for t in c["targets"])
    return now - since > STALE


def lamp(settings):
    """Is the lamp on "Backup" lit? (attention() still gives the hint text – e.g. "same drive" – without lighting it)."""
    from system import orbit
    if ONLINE_BACKUP and orbit.level(settings) == "full":
        return not settings.get("backup_online_seen")
    if settings.get("backup_risk_ok"):   # "I know the risk": stop reminding
        return False
    c = cfg(settings)
    if not c["on"] or not c["targets"]:
        return True
    return _failing(c, time.time()) if LOCAL_OK_CLEARS else True


def attention(settings):
    """Notice on the profile needed? -> text or "". No target outside this drive, a target not reached for a long
    time, or something new was added since the last backup (e.g. a session) that is not backed up anywhere yet."""
    c = cfg(settings)
    if settings.get("backup_risk_ok"):   # "I know the risk" (Settings → Backup): stop reminding
        return ""
    if not c["on"] or not c["targets"]:
        return "Noch keine automatische Sicherung an einem zweiten Ort (Stick, Platte oder Cloud-Ordner)."
    offsite = [t for t in c["targets"] if kind(t["path"]) != "same"]
    if not offsite:
        return "Dieses Ziel liegt auf derselben Festplatte wie Bent°Corner – fällt sie aus, sind beide weg."
    now = time.time()
    if not any(t.get("ok") for t in offsite):
        return "Am zweiten Ort wurde noch keine Sicherung geschrieben (Stick nicht gesteckt?)."
    if not any(t.get("ok") and now - float(t["ok"]) < STALE for t in offsite):
        return "Seit über 14 Tagen konnte keine Sicherung geschrieben werden (Stick nicht gesteckt?)."
    last_ok = max(float(t.get("ok") or 0) for t in offsite)
    changed = last_change()
    if changed > last_ok + 60 and now - changed > UNSAVED_GRACE:
        return "Seit der letzten Sicherung ist Neues dazugekommen (z. B. ein Log) – noch nirgends gesichert."
    return ""
