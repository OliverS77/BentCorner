"""Maintain the data folder: English folder names (one-time rename), silent backups, trash and
backup copies.

Layout (all names in English, the UI stays multilingual):
  settings.json
  data/my-data/        collection.json, decks.json, sessions/, friends/, wishlist.json, lists.json, trash/
  data/card-data/      cards.sqlite, price-history.sqlite, exchange-rates.json, thumbs/, large/, details/, online/
  data/card-images/    card images per set
  data/recognition/    recognition data per set
  data/backups/        silent backups (the last 7) and the backup made before a rename
  data/scan-data/      misrecognized cards (crop + line of text) – local only
Only my-data and settings.json are truly personal – the rest can be downloaded again at any time.
"""
import json
import os
import pathlib
import shutil
import time
import zipfile

from scanner.common import BASE, DATA, MINE

SETTINGS = BASE / "settings.json"
BACKUPS = DATA / "backups"
AUTO = BACKUPS / "auto"
TRASH = MINE / "trash"
KEEP_AUTO = 7
TRASH_DAYS = 60   # Oliver 29.10.: entries stay 60 days, then they're gone for good
BACKUP_PREFIX = "BentCorner backup"

# old (German) names -> new ones, relative to data/ – order matters (folders first, then what is inside them)
RENAMES = [
    ("bilder", "card-images"), ("erkennung", "recognition"), ("kartendaten", "card-data"), ("sammlung", "my-data"),
    ("ki_geraet.json", "ai-device.json"),
    ("card-data/gross", "card-data/large"), ("card-data/vorschau", "card-data/thumbs"),
    ("card-data/preisverlauf.sqlite", "card-data/price-history.sqlite"),
    ("card-data/wechselkurse.json", "card-data/exchange-rates.json"),
    ("my-data/sammlung.json", "my-data/collection.json"), ("my-data/freunde", "my-data/friends"),
    ("my-data/wunschliste.json", "my-data/wishlist.json"), ("my-data/listen.json", "my-data/lists.json"),
]
PATH_FIX = ("data/bilder/", "data/card-images/")  # image paths stored as text in JSON files


def _merge_move(old, new, spare=None):
    """Move old to new; if new already exists, the contents are merged (existing items stay).
    A file that exists under both names moves to spare (backup) – otherwise the old name would remain
    and the migration would run again on every start."""
    if not old.exists():
        return
    if not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        os.replace(old, new)
        return
    if old.is_dir() and new.is_dir():
        for child in list(old.iterdir()):
            _merge_move(child, new / child.name, spare / child.name if spare is not None else None)
        try:
            old.rmdir()
        except OSError:
            pass
    elif old.is_file() and spare is not None:
        try:
            spare.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old, spare if not spare.exists() else spare.with_name(f"{spare.stem}-{int(time.time())}{spare.suffix}"))
        except OSError:
            pass


def _fix_paths(root):
    """data/bilder/… -> data/card-images/… in all JSON files under root."""
    old, new = PATH_FIX
    for f in root.rglob("*.json") if root.exists() else []:
        try:
            text = f.read_text("utf-8")
        except OSError:
            continue
        if old in text:
            f.write_text(text.replace(old, new), "utf-8")


def rename_layout(data_dir, settings_file=None):
    """Switch old German names in a data folder (or an old backup) to the English ones."""
    spare = data_dir / "backups" / "old-names"
    for old, new in RENAMES:
        _merge_move(data_dir / old, data_dir / new, spare / old)
    for sub in ("recognition", "my-data"):
        _fix_paths(data_dir / sub)
    if settings_file is not None and settings_file.exists():
        try:
            text = settings_file.read_text("utf-8")
            if PATH_FIX[0] in text:
                settings_file.write_text(text.replace(*PATH_FIX), "utf-8")
        except OSError:
            pass


def migrate_english():
    """Once at startup: rename German folder names – back up the personal data first. -> True if migrated."""
    if not any((DATA / old).exists() for old, _ in RENAMES[:5]):
        return False
    mine = DATA / "sammlung"
    if mine.exists():
        dest = BACKUPS / f"before-english-names-{time.strftime('%Y-%m-%d_%H-%M-%S')}"
        shutil.copytree(mine, dest / "my-data", dirs_exist_ok=True)
        if SETTINGS.exists():
            shutil.copy2(SETTINGS, dest / "settings.json")
    rename_layout(DATA, SETTINGS)
    return True


# ---------- Silent backups ----------
def personal_roots():
    """Everything personal of ALL games: [(path, name in the backup)] – Magic data/my-data, the other games
    data/games/<game>/my-data, plus settings.json. (MINE is only the currently open game.)"""
    out = [(DATA / "my-data", "my-data")]
    games_dir = DATA / "games"
    if games_dir.exists():
        for g in sorted(games_dir.iterdir()):
            if (g / "my-data").is_dir():
                out.append((g / "my-data", f"games/{g.name}/my-data"))
    out.append((DATA / "collectibles", "collectibles"))   # tickets & co. (collectibles.py)
    out.append((SETTINGS, "settings.json"))
    return [(p, name) for p, name in out if p.exists()]


def personal_files():
    """Every file a backup holds: (path, name in the backup, path inside its root – "" for a single file like
    settings.json), sorted. Without the trash and half-written files (.tmp/.partial). The ZIP and the checksum of the
    automatic backup both walk this – one rule for what counts as "personal"."""
    for p, name in personal_roots():
        if p.is_file():
            yield p, name, ""
            continue
        for f in sorted(x for x in p.rglob("*") if x.is_file()):
            rel = f.relative_to(p).as_posix()
            if "trash" in rel.split("/") or f.name.endswith((".tmp", ".partial")):
                continue
            yield f, name, rel


def _copy_personal(dest):
    for p, name in personal_roots():
        if p.is_dir():
            shutil.copytree(p, dest / name, ignore=shutil.ignore_patterns("trash"), dirs_exist_ok=True)
        else:
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest / name)


def write_zip(zip_path, manifest=None, level=6):
    """Everything personal of all games as one ZIP file (for stick/cloud: one file syncs more cleanly than
    hundreds). Write under .partial first, then rename – an aborted backup is never the newest file.
    manifest: a dict written as manifest.json (time, checksum … – autobackup)."""
    import zipfile
    zip_path = os.fspath(zip_path)
    tmp = zip_path + ".partial"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as z:
        for f, name, rel in personal_files():
            z.write(f, f"{name}/{rel}" if rel else name)
        z.writestr("README.txt", README)
        if manifest:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    os.replace(tmp, zip_path)
    return zip_path


README = ("Bent°Corner backup – your collection, logs, decks, friends, lists and settings (all games).\n"
          "Restore it in Bent°Corner: Settings → Backup → Restore backup … (the ZIP file or the unpacked "
          "folder).\nCard images and card data are not included – the app downloads them again.\n")


def snapshot(reason="auto"):
    """Copy of everything personal (without trash) to data/backups/auto/<time>; the last 7 are kept."""
    if not personal_roots():
        return None
    dest = AUTO / time.strftime("%Y-%m-%d_%H-%M-%S")
    try:
        _copy_personal(dest)
        (dest / "reason.txt").write_text(reason, "utf-8")
    except OSError:
        return None
    old = sorted(p for p in AUTO.iterdir() if p.is_dir())
    for p in old[:-KEEP_AUTO]:
        shutil.rmtree(p, ignore_errors=True)
    return dest


def snapshots():
    return sorted((p for p in AUTO.iterdir() if p.is_dir()), reverse=True) if AUTO.exists() else []


def maybe_snapshot(min_hours=6):
    """At startup: only if the last silent backup is older than min_hours. The 30-day remove copies are pruned too."""
    try:
        prune_removed()
    except OSError:
        pass
    last = snapshots()
    if last and time.time() - last[0].stat().st_mtime < min_hours * 3600:
        return None
    return snapshot("start")


# ---------- Trash ----------
def trash_put(kind, title, data):
    """Keep deleted items (TRASH_DAYS). kind: session | deck | friend | cards."""
    TRASH.mkdir(parents=True, exist_ok=True)
    stamp = time.time()
    entry = {"kind": kind, "title": title, "deleted": stamp, "data": data}
    name = f"{int(stamp * 1000)}-{kind}.json"
    (TRASH / name).write_text(json.dumps(entry, ensure_ascii=False), "utf-8")
    return name


def trash_list():
    """-> [(file name, entry)] newest first; old ones (over TRASH_DAYS) are permanently deleted along the way."""
    out = []
    if not TRASH.exists():
        return out
    for f in TRASH.glob("*.json"):
        try:
            e = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if time.time() - e.get("deleted", 0) > TRASH_DAYS * 86400:
            f.unlink(missing_ok=True)
            continue
        out.append((f.name, e))
    out.sort(key=lambda t: -t[1].get("deleted", 0))
    return out


def trash_take(name):
    """Take an entry out of the trash (to restore it) – it disappears from the trash."""
    f = TRASH / name
    try:
        e = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    f.unlink(missing_ok=True)
    return e


def trash_drop(name=None):
    """Delete permanently: one entry or (name=None) everything."""
    for f in ([TRASH / name] if name else list(TRASH.glob("*.json")) if TRASH.exists() else []):
        f.unlink(missing_ok=True)


# ---------- Backup copy (e.g. to a USB stick) ----------
def create_backup(target_dir):
    """Folder "BentCorner backup <date>" in target_dir with everything personal. -> path"""
    dest = target_dir / f"{BACKUP_PREFIX} {time.strftime('%Y-%m-%d %H-%M')}"
    _copy_personal(dest)
    (dest / "README.txt").write_text(README, "utf-8")
    return dest


# a ZIP backup is personal data only (no card images) – far below these (review 08.11. F3: no zip bomb fills the disk)
ZIP_MAX_BYTES = 2 * 1024 ** 3
ZIP_MAX_FILES = 200_000
_unpacked = {}   # the ZIP last unpacked (path, size, mtime) – restoring right after the question doesn't unpack it again


def _zip_key(zip_path):
    st = pathlib.Path(zip_path).stat()
    return str(pathlib.Path(zip_path).resolve()), st.st_size, st.st_mtime


def unpack_zip(zip_path):
    """Unpack a ZIP backup to data/restore-zip (only files inside it, no paths leading outside; at most
    ZIP_MAX_FILES files and ZIP_MAX_BYTES in all – else ValueError, nothing left behind). -> folder"""
    import zipfile
    out = DATA / "restore-zip"
    key = _zip_key(zip_path)
    if _unpacked.get("key") == key and out.is_dir():
        return out
    _unpacked.clear()
    shutil.rmtree(out, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        infos = z.infolist()
        if len(infos) > ZIP_MAX_FILES or sum(i.file_size for i in infos) > ZIP_MAX_BYTES:
            raise ValueError("backup ZIP too large")
        out.mkdir(parents=True)
        root = out.resolve()
        try:
            _unzip(z, infos, out, root)
        except BaseException:
            shutil.rmtree(out, ignore_errors=True)
            raise
    _unpacked["key"] = key
    return out


def drop_unpacked():
    """The question was answered with no (or it wasn't a backup): the unpacked ZIP goes."""
    _unpacked.clear()
    shutil.rmtree(DATA / "restore-zip", ignore_errors=True)


def _unzip(z, infos, out, root):
    written = 0
    for info in infos:
        target = (out / info.filename).resolve()
        # really inside (not just the same text prefix: "../restore-zip-x/…" would pass a startswith check)
        if not target.is_relative_to(root) or target == root or info.is_dir():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with z.open(info) as src, open(target, "wb") as dst:
            while True:   # counted while writing too – the sizes in the directory could lie
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                written += len(chunk)
                if written > ZIP_MAX_BYTES:
                    raise ValueError("backup ZIP too large")
                dst.write(chunk)


def backup_info(folder):
    """Is folder a backup (including an old one with German names)? -> description or None."""
    if str(folder).lower().endswith(".zip"):
        try:
            folder = unpack_zip(folder)
        except (OSError, ValueError, zipfile.BadZipFile):
            return None
    mine = folder / "my-data" if (folder / "my-data").exists() else folder / "sammlung"
    if not mine.exists() and (folder / "data").exists():  # whole old data folder
        return backup_info(folder / "data")
    if not mine.exists():
        return None
    coll = mine / "collection.json" if (mine / "collection.json").exists() else mine / "sammlung.json"
    n = 0
    try:
        n = sum(int(it.get("count", 1) or 1) for it in json.loads(coll.read_text("utf-8")).get("items", []))
    except (OSError, ValueError, AttributeError, TypeError):   # review 08.11. F7: "count": null
        pass
    sess = len(list((mine / "sessions").glob("*.json"))) if (mine / "sessions").exists() else 0
    others = [g for g in sorted((folder / "games").iterdir()) if (g / "my-data").is_dir()] \
        if (folder / "games").is_dir() else []
    return {"folder": folder, "mine": mine, "cards": n, "sessions": sess, "games": others,
            "settings": (folder / "settings.json") if (folder / "settings.json").exists() else None}


def restorable_settings(text, current=None):
    """The settings of a backup, as far as they may come along (review 08.11. F1): only a JSON object; what belongs
    to THIS device stays this device's – where automatic backups go, the last backup's path and the server address
    (a backup from someone else must not send backups or traffic elsewhere). The identity comes along – that's the
    move to a new PC. -> dict, or None (nothing usable: the current settings stay)"""
    try:
        new = json.loads(text)
    except ValueError:
        return None
    if not isinstance(new, dict):
        return None
    cur = current if isinstance(current, dict) else {}
    for key in DEVICE_SETTINGS:
        if key in cur:
            new[key] = cur[key]
        else:
            new.pop(key, None)
    for k, v in cur.items():   # a remove copy has no codes/keys (D): this device keeps its own
        if _secret(k) and k not in new:
            new[k] = v
    relay = new.get("relay")
    if isinstance(relay, dict):
        url = (cur.get("relay") or {}).get("url") if isinstance(cur.get("relay"), dict) else None
        if url:
            relay["url"] = url
        else:
            relay.pop("url", None)
    elif "relay" in new:
        new.pop("relay")
    return new


# this device's own settings – never taken from a backup (review 08.11. F1)
DEVICE_SETTINGS = ("autobackup", "last_backup", "last_backup_path", "device_name")


def _other_identity(current, new):
    """The backup brings another identity (F1, performance 08.11.): this device's keys and sync state belong to the old
    one – they go (devkey.json, sync/ next to settings.json), and so do the device-list marks in the settings; the device
    then signs in like a new device of that identity."""
    from net import devkeys
    if devkeys.identity_of(current) == devkeys.identity_of(new):
        return
    devkeys.device_bits_off(new)
    devkeys.drop_device_state(SETTINGS.parent)


class RestoreError(Exception):
    """The current state couldn't be saved first – nothing was changed (review 08.11. F4)."""


def restore_backup(folder):
    """Restore a backup: first silently back up the current state, then replace my-data, the other games, the
    tickets (collectibles) and the settings. Old backups with German names are migrated along the way.
    Without that safety copy nothing happens (RestoreError); an error halfway puts the safety copy back and is
    raised again (review 08.11. F4). -> True, or False when folder isn't a backup."""
    from system import autobackup
    info = backup_info(folder)
    if info is None:
        return False
    # never next to the automatic backup (review 08.11. F10): it could pack a half-restored state
    if not autobackup._lock.acquire(timeout=autobackup.RESTORE_WAIT):
        drop_unpacked()
        raise RestoreError("an automatic backup is still running")
    try:
        _restore(info)
    finally:
        autobackup._lock.release()
    return True


def _restore(info):
    from system import autobackup
    safe = snapshot("before-restore")
    if safe is None and personal_roots():
        drop_unpacked()
        raise RestoreError("the current state couldn't be saved first")
    try:
        _apply(info, own=False)
        restore_extra(info["folder"])
    except Exception:
        if safe is not None:
            back = backup_info(safe)
            if back is not None:
                _apply(back, own=True)
        drop_unpacked()
        raise
    drop_unpacked()
    autobackup.restored = True   # until the restart: no backup of the restored state (the closing one neither)


def _linked(p):
    """A symlink or an NTFS junction (needs no admin) – a backup folder may point anywhere with one."""
    p = pathlib.Path(p)
    try:
        return p.is_symlink() or p.is_junction()
    except OSError:
        return True


def _skip_links(folder, names):
    """copytree's ignore: never follow a link or junction inside a backup (review 08.11. F6) – otherwise a backup on a
    stick could copy e.g. the Documents folder into my-data and from there into every later backup."""
    return [n for n in names if _linked(pathlib.Path(folder) / n)]


def _copy_backup(src, dst):
    """A folder of a backup to dst – without links/junctions, not even as the folder itself."""
    if _linked(src):
        raise ValueError("a folder in the backup is a link")   # → "couldn't be restored – previous state is back"
    shutil.copytree(src, dst, ignore=_skip_links)


def _apply(info, own):
    """Put a backup's contents in place. own: our own safety copy (settings as they were, nothing filtered)."""
    for g in info.get("games") or []:   # other games (backups from v0.8.5 on)
        dest = DATA / "games" / g.name / "my-data"
        tmpg = DATA / "restore-tmp-game"
        shutil.rmtree(tmpg, ignore_errors=True)
        _copy_backup(g / "my-data", tmpg)
        if (dest / "trash").exists():
            shutil.move(str(dest / "trash"), str(tmpg / "trash"))
        shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmpg, dest)
    mine_target = DATA / "my-data"
    tmp = DATA / "restore-tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    _copy_backup(info["mine"], tmp / ("my-data" if info["mine"].name == "my-data" else "sammlung"))
    rename_layout(tmp)  # sammlung.json -> collection.json etc.
    trash = mine_target / "trash"
    keep_trash = DATA / "restore-trash"
    if trash.exists():
        shutil.move(str(trash), str(keep_trash))
    shutil.rmtree(mine_target, ignore_errors=True)
    os.replace(tmp / "my-data", mine_target)
    shutil.rmtree(tmp, ignore_errors=True)
    if keep_trash.exists():
        shutil.move(str(keep_trash), str(trash))
    coll = info["folder"] / "collectibles"   # the tickets were backed up but never restored (review 08.11. F8)
    if coll.is_dir():
        tmpc = DATA / "restore-tmp-collectibles"
        shutil.rmtree(tmpc, ignore_errors=True)
        _copy_backup(coll, tmpc)
        shutil.rmtree(DATA / "collectibles", ignore_errors=True)
        os.replace(tmpc, DATA / "collectibles")
    if info["settings"] is not None and (own or not _linked(info["settings"])):   # a linked settings.json: never
        text = info["settings"].read_text("utf-8").replace(*PATH_FIX)
        if own:
            SETTINGS.write_text(text, "utf-8")
            return
        try:
            current = json.loads(SETTINGS.read_text("utf-8")) if SETTINGS.exists() else {}
        except (OSError, ValueError):
            current = {}
        new = restorable_settings(text, current)
        if new is not None:
            _other_identity(current, new)
            SETTINGS.write_text(json.dumps(new, indent=1, ensure_ascii=False), "utf-8")



# ---------- D (Oliver/lead 12.11.): a device taken out of the sync empties itself – after a 30-day copy ----------
REMOVED = BACKUPS / "before-remove"
REMOVED_DAYS = 30
# what is personal beyond personal_roots(): set aside (syncaside), the Studio's own photos, misrecognized crops
EXTRA_DIRS = ("beiseite", "studio", "scan-data")
# never in the copy (codes/keys/identity – lead 12.11.); on restoring it they stay this device's
SECRET_KEYS = ("relay", "phone_token")
SECRET_PREFIX = ("sync_", "guard", "pair")
# what the emptied device forgets of its settings (its look, language, games and card data stay)
PERSONAL_KEYS = ("profile", "device_name")


def _secret(k):
    return k in SECRET_KEYS or k.startswith(SECRET_PREFIX)


def _trash_dirs():
    """[(trash folder, name in the copy)] of all games."""
    out = [(DATA / "my-data" / "trash", "my-data")] if (DATA / "my-data" / "trash").is_dir() else []
    games_dir = DATA / "games"
    if games_dir.is_dir():
        out += [(g / "my-data" / "trash", f"games-{g.name}") for g in sorted(games_dir.iterdir())
                if (g / "my-data" / "trash").is_dir()]
    return out


def remove_copy(now=None):
    """The copy BEFORE emptying (lead 12.11.): everything that goes – collection, logs, decks, lists, binders, friends,
    set aside, the trash, the Studio's photos, earlier automatic copies and the settings WITHOUT codes/keys – to
    data/backups/before-remove/<time>; restorable like a backup (Settings → Backup) for REMOVED_DAYS days, then
    gone (prune_removed). -> the folder, or None: nothing was emptied, nothing may be (the caller shows an error)."""
    now = time.time() if now is None else now
    dest = REMOVED / time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(now))
    try:
        dest.mkdir(parents=True, exist_ok=False)
        _copy_personal(dest)
        (dest / "my-data").mkdir(exist_ok=True)   # a backup needs it (backup_info) – also with other games only
        for src, name in _trash_dirs():
            shutil.copytree(src, dest / "extra" / "trash" / name, dirs_exist_ok=True)
        for name in EXTRA_DIRS:
            if (DATA / name).is_dir():
                shutil.copytree(DATA / name, dest / "extra" / name, dirs_exist_ok=True)
        sf = dest / "settings.json"
        if sf.exists():
            cur = json.loads(sf.read_text("utf-8"))
            if isinstance(cur, dict):
                sf.write_text(json.dumps({k: v for k, v in cur.items() if not _secret(k)}, indent=1,
                                         ensure_ascii=False), "utf-8")
        (dest / "removed.json").write_text(json.dumps({"made": now, "until": now + REMOVED_DAYS * 86400}), "utf-8")
        # earlier states (the automatic copies & co.) are moved INTO the copy: they leave with it after 30 days
        if BACKUPS.is_dir():
            for p in list(BACKUPS.iterdir()):
                if p != REMOVED and p.is_dir():
                    (dest / "earlier").mkdir(exist_ok=True)
                    shutil.move(str(p), str(dest / "earlier" / p.name))
    except (OSError, ValueError):
        shutil.rmtree(dest, ignore_errors=True)
        return None
    return dest


def removed_copies(now=None):
    """-> [{"folder", "made", "until"}] newest first – only those still within their 30 days."""
    now = time.time() if now is None else now
    out = []
    if REMOVED.is_dir():
        for p in REMOVED.iterdir():
            try:
                m = json.loads((p / "removed.json").read_text("utf-8"))
            except (OSError, ValueError):
                continue
            if float(m.get("until") or 0) > now:
                out.append({"folder": p, "made": float(m.get("made") or 0), "until": float(m["until"])})
    return sorted(out, key=lambda r: -r["made"])


def prune_removed(now=None):
    """At every start: copies older than their 30 days go for good (legal: it deletes itself)."""
    now = time.time() if now is None else now
    if not REMOVED.is_dir():
        return 0
    n = 0
    for p in list(REMOVED.iterdir()):
        try:
            until = float(json.loads((p / "removed.json").read_text("utf-8")).get("until") or 0)
        except (OSError, ValueError):
            until = p.stat().st_mtime + REMOVED_DAYS * 86400   # unreadable: by its age
        if until <= now:
            shutil.rmtree(p, ignore_errors=True)
            n += 1
    return n


def wipe_personal(settings):
    """Empties this device's personal data on disk (only after remove_copy() succeeded – the caller checks): my-data of
    every game, the tickets, set aside, the Studio's photos, the crops. settings (a dict, changed in place): the
    personal bits go; identity and sync are the caller's (a new identity, sync off). The program restarts afterwards
    without saving (restart_after_restore) – the state in memory must not write anything back."""
    for p, _name in personal_roots():
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    games_dir = DATA / "games"
    if games_dir.is_dir():
        for g in games_dir.iterdir():
            if (g / "my-data").is_dir():
                shutil.rmtree(g / "my-data", ignore_errors=True)
    for name in EXTRA_DIRS:
        shutil.rmtree(DATA / name, ignore_errors=True)
    (DATA / "my-data").mkdir(parents=True, exist_ok=True)
    for k in PERSONAL_KEYS:
        settings.pop(k, None)
    return settings


def restore_extra(folder):
    """A remove copy's extras back in place (set aside, Studio photos, crops, the trash) – merged, nothing replaced."""
    ex = pathlib.Path(folder) / "extra"
    if not ex.is_dir():
        return
    for name in EXTRA_DIRS:
        if (ex / name).is_dir():
            shutil.copytree(ex / name, DATA / name, dirs_exist_ok=True)
    tr_dir = ex / "trash"
    if tr_dir.is_dir():
        for t in tr_dir.iterdir():
            target = DATA / "my-data" / "trash" if t.name == "my-data" else \
                DATA / "games" / t.name[len("games-"):] / "my-data" / "trash"
            shutil.copytree(t, target, dirs_exist_ok=True)


def personal_size():
    """Size of the personal data in bytes (for display)."""
    total = 0
    for p, _ in personal_roots():
        if p.is_file():
            total += p.stat().st_size
        elif p.exists():
            total += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return total
