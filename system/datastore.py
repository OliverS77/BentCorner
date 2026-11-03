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
import shutil
import time

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


def _personal_items():
    return personal_roots()


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
    import json
    import zipfile
    zip_path = os.fspath(zip_path)
    tmp = zip_path + ".partial"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as z:
        for p, name in personal_roots():
            if p.is_file():
                z.write(p, name)
                continue
            for f in p.rglob("*"):
                rel = f.relative_to(p)
                if f.is_file() and "trash" not in rel.parts and not f.name.endswith((".tmp", ".partial")):
                    z.write(f, f"{name}/{rel.as_posix()}")
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
    """At startup: only if the last silent backup is older than min_hours."""
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


def unpack_zip(zip_path):
    """Unpack a ZIP backup to data/restore-zip (only files inside it, no paths leading outside). -> folder"""
    import zipfile
    out = DATA / "restore-zip"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    root = out.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            target = (out / info.filename).resolve()
            # really inside (not just the same text prefix: "../restore-zip-x/…" would pass a startswith check)
            if not target.is_relative_to(root) or target == root or info.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return out


def backup_info(folder):
    """Is folder a backup (including an old one with German names)? -> description or None."""
    if str(folder).lower().endswith(".zip"):
        try:
            folder = unpack_zip(folder)
        except (OSError, ValueError, __import__("zipfile").BadZipFile):
            return None
    mine = folder / "my-data" if (folder / "my-data").exists() else folder / "sammlung"
    if not mine.exists() and (folder / "data").exists():  # whole old data folder
        return backup_info(folder / "data")
    if not mine.exists():
        return None
    coll = mine / "collection.json" if (mine / "collection.json").exists() else mine / "sammlung.json"
    n = 0
    try:
        n = sum(int(it.get("count", 1)) for it in json.loads(coll.read_text("utf-8")).get("items", []))
    except (OSError, ValueError, AttributeError):
        pass
    sess = len(list((mine / "sessions").glob("*.json"))) if (mine / "sessions").exists() else 0
    others = [g for g in sorted((folder / "games").iterdir()) if (g / "my-data").is_dir()] \
        if (folder / "games").is_dir() else []
    return {"folder": folder, "mine": mine, "cards": n, "sessions": sess, "games": others,
            "settings": (folder / "settings.json") if (folder / "settings.json").exists() else None}


def restore_backup(folder):
    """Restore a backup: first silently back up the current state, then replace my-data (+ settings).
    Old backups with German names are migrated along the way. -> True"""
    info = backup_info(folder)
    if info is None:
        return False
    snapshot("before-restore")
    for g in info.get("games") or []:   # other games (backups from v0.8.5 on)
        dest = DATA / "games" / g.name / "my-data"
        tmpg = DATA / "restore-tmp-game"
        shutil.rmtree(tmpg, ignore_errors=True)
        shutil.copytree(g / "my-data", tmpg)
        if (dest / "trash").exists():
            shutil.move(str(dest / "trash"), str(tmpg / "trash"))
        shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmpg, dest)
    mine_target = DATA / "my-data"
    tmp = DATA / "restore-tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(info["mine"], tmp / ("my-data" if info["mine"].name == "my-data" else "sammlung"))
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
    if info["settings"] is not None:
        text = info["settings"].read_text("utf-8").replace(*PATH_FIX)
        SETTINGS.write_text(text, "utf-8")
    shutil.rmtree(DATA / "restore-zip", ignore_errors=True)
    return True


def personal_size():
    """Size of the personal data in bytes (for display)."""
    total = 0
    for p, _ in _personal_items():
        if p.is_file():
            total += p.stat().st_size
        elif p.exists():
            total += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return total
