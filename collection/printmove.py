"""Prints that left the card database – and came back. Every reference in the personal data of the game (collection,
sessions, trash, binders, decks, lists, friends …):

  away   points to a print the database no longer has -> the English print of the same card – same set and number
         where it exists (DABL-JP001 -> DABL-EN001), else the same set, else the card's first print; the language stays
         as an attribute and the old print as "from_print" (Yu-Gi-Oh! 0.9.3: the OCG/Asian/Spanish prints from YGOJSON
         left cards.sqlite, Oliver 25.10.2026)
  back   the old print is in the database again (Yu-Gi-Oh! 0.9.4: ygo-locale.sqlite, merged on the user's PC) -> back to
         it: from "from_print", else from the backup the move made (collection by uid, other files by position), else
         – only for a card in Japanese, Korean or Spanish – the JP/KR/SP print with the same set and number. Always
         only to a print of the same card (same passcode), never guessed from the name.

Runs once per state of the database (games.<game>.heal_prints: data pack build + merged extra file), before the
session and collection are loaded; the data is backed up first. Nothing is deleted: what can't be matched stays.
"""
import json
import logging
import re
import shutil
import sqlite3
import time

import games
from cards import carddb
from scanner.common import DATA, image_rel

log = logging.getLogger("booster")

MARK = ".prints-checked.json"   # in the game's my-data: {"state": database state last checked (_state)}
BACKUP = "before-print-move-"   # data/backups/before-print-move-<game>-<time>/my-data
ID_KEYS = ("id", "sid", "psid")
_ID = re.compile(r"^([a-z0-9]+-[^\s_]+?)(_\d+)?$")   # "dabl-jp001_0" -> print, face
_LOCALE = re.compile(r"^(JP|JA|KR|SP|AE)(.+)$")                 # "JP001-SR" -> "JP", "001-SR"
LOCALE_LANG = {"JP": "ja", "JA": "ja", "KR": "ko", "SP": "es", "AE": "en"}
LANG_PREFIX = {"ja": "jp", "ko": "kr", "es": "sp"}   # card language -> number prefix of its print (way back)


def _walk(x, fn):
    if isinstance(x, dict):
        fn(x)
        for v in x.values():
            _walk(v, fn)
    elif isinstance(x, list):
        for v in x:
            _walk(v, fn)


def _replace(x, moved):
    """Every string that is a moved ID (as a value, list item or key) -> the new ID."""
    if isinstance(x, dict):
        return {moved.get(k, k) if isinstance(k, str) else k: _replace(v, moved) for k, v in x.items()}
    if isinstance(x, list):
        return [_replace(v, moved) for v in x]
    return moved.get(x, x) if isinstance(x, str) else x


def target(con, name, sid, where=""):
    """English print for the removed print sid ("dabl-jp001-sr") of the card name -> database row or None.
    Checked on all 108 319 removed Yu-Gi-Oh! prints: every one resolves, none to another card (same passcode).
    where: extra condition (" AND …") – prints of the data pack only, not merged ones."""
    set_code, _, number = sid.partition("-")
    rows = [dict(r) for r in con.execute(f"SELECT * FROM cards WHERE name = ?{where} ORDER BY released, rowid", (name,))]
    same = [r for r in rows if r["set_code"] == set_code]
    m = _LOCALE.match(number.upper())
    if m:
        want = "EN" + m.group(2)
        for n in (want, want.split("-")[0]):   # same rarity, else the set's base print
            hit = next((r for r in same if r["number"].upper() == n), None)
            if hit is not None:
                return hit
    return (same or rows or [None])[0]


def _lang_of(sid):
    m = _LOCALE.match(sid.partition("-")[2].upper())
    return LOCALE_LANG.get(m.group(1)) if m else None


def _print_of(d, k):
    """The print a reference names -> regex match or None. "id" counts only on a card entry (with set or number) –
    a deck or binder named like a card must never become one."""
    v = d.get(k)
    if not isinstance(v, str) or (k == "id" and "set" not in d and "number" not in d):
        return None
    return _ID.match(v)


def _state(db):
    """What the check depends on: the data pack's build and the merged extra file (games.yugioh.merge_extra)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        meta = dict(con.execute("SELECT key, value FROM meta WHERE key IN ('pk_build', 'locale_merged')"))
    finally:
        con.close()
    return f"{meta.get('pk_build') or 0}|{meta.get('locale_merged') or ''}"


def _hints(mine, files, info, extra):
    """The old print of each entry from the backups printmove made before moving (oldest first): collection items by
    uid, everything else by position in the same file. -> {id(entry dict): old print} – only prints that are in
    the database again as merged ones (extra) and belong to the same card."""
    out = {}
    root = DATA / "backups"
    dirs = sorted(p / "my-data" for p in root.glob(f"{BACKUP}*") if (p / "my-data").is_dir()) if root.is_dir() else []

    def take(cur, old):
        for k in ("id", "sid"):
            mc, mo = _print_of(cur, k), _print_of(old, k)
            if not mc or not mo or id(cur) in out:
                continue
            x, y = mc.group(1), mo.group(1)
            if y != x and y in extra and x in info and info[y][0] == info[x][0]:
                out[id(cur)] = y

    def pair(cur, old):
        if isinstance(cur, dict) and isinstance(old, dict):
            take(cur, old)
            for k, v in cur.items():
                if k in old:
                    pair(v, old[k])
        elif isinstance(cur, list) and isinstance(old, list) and len(cur) == len(old):
            for a, b in zip(cur, old):
                pair(a, b)

    for d in dirs:
        for f, data in files.items():
            try:
                old = json.loads((d / f.relative_to(mine)).read_text("utf-8"))
            except (OSError, ValueError):
                continue
            if f.name == "collection.json":
                by_uid = {it.get("uid"): it for it in old.get("items") or [] if isinstance(it, dict) and it.get("uid")}
                for it in data.get("items") or []:
                    if isinstance(it, dict) and it.get("uid") in by_uid:
                        take(it, by_uid[it["uid"]])
            else:
                pair(data, old)
    return out


def _back(d, x, info, extra, hints):
    """Where an entry on the print x goes back to (a merged print of the same card) -> print or None."""
    if x in extra:
        return None
    fp = d.get("from_print")
    cands = [fp if isinstance(fp, str) else None, hints.get(id(d))]
    pre = LANG_PREFIX.get(d.get("lang") or "")
    set_code, _, number = x.partition("-")
    if pre and info.get(x, ("", ""))[1] == "en" and number.startswith("en"):
        cands.append(f"{set_code}-{pre}{number[2:]}")   # Japanese card on DABL-EN001 -> DABL-JP001
    for y in cands:
        if y and y != x and y in extra and y in info and info[y][0] == info[x][0]:
            return y
    return None


def _set_print(d, row, face, g):
    if "set" in d:
        d["set"] = row["set_code"].upper() if str(d["set"]).isupper() else row["set_code"]
    if "number" in d:
        d["number"] = row["number"]
    if "rarity" in d:
        d["rarity"] = row["rarity"] or ""
    if "img" in d:
        d["img"] = image_rel(row["set_code"], row["number"], int(face[1:] or 0))
    if d.get("url"):
        d["url"] = g.card_url(row["set_code"], row["number"])


def heal(key=None):
    """-> number of entries moved, away or back (0 if nothing to do)."""
    g = games.load(key) if key else games.current()
    if not getattr(g, "heal_prints", False):
        return 0
    mine = games.mine(g.key)
    if g.key == games.current().key:
        carddb.exists()   # installs a newer database from the data pack first and merges extra data (carddb)
    db = carddb.path_of(g.key)
    if not mine.is_dir() or db is None or not db.exists():
        return 0
    state = _state(db)
    mark = mine / MARK
    try:
        if json.loads(mark.read_text("utf-8")).get("state") == state:
            return 0
    except (OSError, ValueError):
        pass
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        info = {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, oracle_id, lang FROM cards")}
        has_extra = con.execute("SELECT 1 FROM sqlite_master WHERE name = 'locale_ids'").fetchone() is not None
        extra = {r[0] for r in con.execute("SELECT id FROM locale_ids")} if has_extra else set()
        where = " AND id NOT IN (SELECT id FROM locale_ids)" if has_extra else ""
        files, names, unknown = {}, {}, set()
        for f in mine.rglob("*.json"):
            try:
                files[f] = json.loads(f.read_text("utf-8"))
            except (OSError, ValueError):
                continue

            def note(d):
                for k in ID_KEYS:
                    m = _print_of(d, k)
                    if m and m.group(1) not in info:
                        unknown.add(m.group(1))
                        if isinstance(d.get("name"), str) and d["name"]:
                            names.setdefault(m.group(1), d["name"])
            _walk(files[f], note)
        away = {}
        for sid, name in names.items():
            row = target(con, name, sid, where)
            if row is not None:
                away[sid] = row
        hints = _hints(mine, files, info, extra) if extra else {}
        back = {}

        def plan(d):
            for k in ("id", "sid"):
                m = _print_of(d, k)
                if m and m.group(1) in info:
                    y = _back(d, m.group(1), info, extra, hints)
                    if y is not None:
                        back[id(d)] = y
        for data in files.values():
            _walk(data, plan)
        rows = {y: dict(con.execute("SELECT * FROM cards WHERE id = ?", (y,)).fetchone()) for y in set(back.values())}
    finally:
        con.close()
    left = len(unknown) - len(away)
    if not away and not back:
        _mark(mark, state)
        if left:
            log.warning("Prints no longer in the database: %d without a match – left as they are", left)
        return 0
    backup = DATA / "backups" / f"{BACKUP}{g.key}-{time.strftime('%Y-%m-%d_%H-%M-%S')}"
    shutil.copytree(mine, backup / "my-data", dirs_exist_ok=True)
    n_away = n_back = 0
    for f, data in files.items():
        moved, changed = {}, False

        def fix(d):
            nonlocal n_away, n_back, changed
            for k in ID_KEYS:
                m = _print_of(d, k)
                if not m:
                    continue
                face = m.group(2) or ""
                if k != "psid" and id(d) in back:   # way back: the old print is there again – only this entry (the
                    row = rows[back[id(d)]]         # English print it sat on stays right for the others)
                    d[k] = row["id"] + face
                    n_back += 1
                    changed = True
                    _set_print(d, row, face, g)
                    d.pop("from_print", None)
                    continue
                row = away.get(m.group(1))
                if row is None:
                    continue
                moved[d[k]] = d[k] = row["id"] + face
                if k == "psid":
                    continue
                n_away += 1
                lang = d.get("lang") or d.get("plang") or _lang_of(m.group(1))
                d.pop("plang", None)
                d.setdefault("from_print", m.group(1))   # the way back (other games ignore the field)
                _set_print(d, row, face, g)
                if lang and ("lang" in d or "set" in d):
                    d["lang"] = lang
        _walk(data, fix)
        if not moved and not changed:
            continue
        data = _replace(data, moved)   # gone IDs also in lists and as keys (hidden, binder slots …)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(f)
    _mark(mark, state)
    log.warning("Prints: %d entries moved to the English print (%d prints, %d without a match left as they are), "
                "%d back to their own print – backup %s", n_away, len(away), left, n_back, backup.name)
    return n_away + n_back


def _mark(mark, state):
    try:
        mark.write_text(json.dumps({"state": state, "checked": time.time()}), "utf-8")
    except OSError:
        pass
