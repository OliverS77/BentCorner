"""Trading: friends' libraries, wishlist, trade cards, export/import.

Files (all in data/my-data, formerly data/sammlung):
  friends/<profile-id>.json  a friend's library (read only, never mixed with your own)
  wishlist.json              your own wishes: [{"name", "count", "set", "number", "note", "added", "list"}]
  lists.json                 lists: {"wish": [{"id", "name"}], "have": [{"id", "name", "items": {uid: count}}]}
Trade cards: field "trade" (count) on the entries of your own collection = the list "Tauschkarten" (id "trade").
Further own lists (e.g. "duplicate Commander cards") count per collection entry (uid). Multiple
wishlists: every wish has "list" (default "main"). On export the selected lists are merged.

Export file ".bentcorner": compressed JSON (zlib) with a magic marker, profile (ID, name, card back), timestamp and
cards as short lists [set, number, language, foil, count, name]. 1,000 different cards ≈ 10 KB – fits into
any messenger. On import the ID identifies whose library it is (update instead of duplicate).
Also readable: CSV from ManaBox, Moxfield, Deckbox, Archidekt etc. (columns are detected from the header).
"""
import csv
import io
import json
import pathlib
import re
import time
import uuid
import zlib

from scanner.common import MINE
from system.i18n import tr

FRIENDS = MINE / "friends"


def friends_folder(game):
    """Folder with the friends' lists of a game: the open game's (FRIENDS) or another game's. Only known games – the
    game comes from friends over the net ("../.." must never become a folder)."""
    import games
    if game not in {k for k, *_ in games.GAMES}:
        raise ValueError(f"unknown game {str(game)[:20]!r}")
    return FRIENDS if game == games.current().key else games.mine(game, "friends")


SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")   # friend/list ids become file names: harmless characters only


def friend_path(folder, fid):
    """<folder>/<fid>.json – only for harmless ids and only inside the folder. Ids come from friends over the net:
    "../settings", "C:/x" or a NUL byte must never reach the disk. -> Path, ValueError otherwise."""
    fid = str(fid or "")
    if not SAFE_ID.fullmatch(fid):
        raise ValueError(f"invalid friend id {fid[:20]!r}")
    folder = pathlib.Path(folder)
    f = folder / f"{fid}.json"
    if f.resolve().parent != folder.resolve():
        raise ValueError(f"friend file outside its folder: {fid[:20]!r}")
    return f
WISH_FILE = MINE / "wishlist.json"
LISTS_FILE = MINE / "lists.json"
MAIN_WISH, MAIN_HAVE = "main", "trade"
MAGIC = b"BENTCORNER1\n"
EXT = ".bentcorner"


# ---------- Friends ----------
def _repair(d):
    """Fix old bugs: a name that was stored as "<PySide6.QtQml.QJSValue …>" (input fields before
    v0.7.23) becomes empty – "Friend" is shown instead, renaming works via the menu."""
    if str(d.get("name") or "").startswith("<PySide6."):
        d["name"] = ""
        save_friend(d)
    return d


def friends():
    """All imported libraries, newest first."""
    out = []
    if FRIENDS.exists():
        for f in FRIENDS.glob("*.json"):
            try:
                d = _repair(json.loads(f.read_text("utf-8")))
                d["file"] = str(f)
                out.append(d)
            except (OSError, ValueError):
                continue
    return sorted(out, key=lambda d: -(d.get("imported") or 0))


def set_friend_folder(fid, folder):
    d = friend(fid)
    if d:
        d["folder"] = folder or ""
        save_friend(d)


def set_friend_folder_in(game, fid, folder):
    """Set a friend's folder in another game (without switching) – directly in that game's friend file."""
    import games
    if game == games.current().key:
        set_friend_folder(fid, folder)
        return
    if game not in {k for k, *_ in games.GAMES} or not SAFE_ID.fullmatch(str(fid or "")):
        return
    f = friend_path(games.mine(game) / "friends", fid)
    try:
        d = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return
    d["folder"] = folder or ""
    f.write_text(json.dumps(d, ensure_ascii=False), "utf-8")


def friend(fid):
    try:
        return json.loads(friend_path(FRIENDS, fid).read_text("utf-8"))
    except (OSError, ValueError):
        return None


def save_friend(d):
    FRIENDS.mkdir(parents=True, exist_ok=True)
    d = {k: v for k, v in d.items() if k != "file"}
    from system import undo
    f = friend_path(FRIENDS, d.get("id"))   # ValueError for ids from outside that aren't harmless
    undo.before_write(f, "Freunde")
    f.write_text(json.dumps(d, ensure_ascii=False), "utf-8")


def remove_friend(fid):
    try:
        from system import datastore
        d = friend(fid)
        if d is not None:  # 30 days in the trash
            datastore.trash_put("friend", d.get("name") or "?", d)
    except Exception:  # noqa: BLE001 – the trash is a bonus, deleting works regardless
        pass
    try:
        friend_path(FRIENDS, fid).unlink()
    except (OSError, ValueError):
        pass


def rename_friend(fid, name):
    d = friend(fid)
    if d:
        d["name"] = str(name).strip()[:40] or d.get("name") or ""
        save_friend(d)


def friend_cards_by_name(d):
    """{card name: count} of a friend's library (all printings combined)."""
    out = {}
    for c in d.get("cards") or []:
        name = c[5] if len(c) > 5 else None
        if name:
            out[name] = out.get(name, 0) + int(c[4] or 1)
    return out


def holders(active_ids):
    """{card name: [(friend ID, name, card back, count)]} for the activated friends (chips)."""
    out = {}
    for d in friends():
        if d["id"] not in active_ids:
            continue
        for name, n in friend_cards_by_name(d).items():
            out.setdefault(name, []).append((d["id"], d.get("name") or "?", d.get("back"), n))
    return out


# ---------- Wishlist ----------
def wishes(list_ids=None, raw=False):
    """Wishes – all of them (without the cards of own lists) or only those of the given lists. Own lists ("custom")
    live in the same file but are not wishes (friends, export and "Looking for" don't see them).
    raw=True: really everything – always read this way when changing and writing back (save_wishes)."""
    try:
        items = json.loads(WISH_FILE.read_text("utf-8")).get("items", [])
    except (OSError, ValueError):
        return []
    if list_ids is None:
        if raw:
            return items
        custom = {x["id"] for x in _read_lists()["custom"]}
        return [w for w in items if (w.get("list") or MAIN_WISH) not in custom] if custom else items
    ids = set(list_ids)
    return [w for w in items if (w.get("list") or MAIN_WISH) in ids]


def save_wishes(items):
    MINE.mkdir(parents=True, exist_ok=True)
    from system import undo
    undo.before_write(WISH_FILE, "Wunschliste")
    WISH_FILE.write_text(json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=1), "utf-8")


def add_wish(name, count=1, set_code=None, number=None, note="", list_id=MAIN_WISH):
    if list_id == MAIN_WISH:
        _revive(MAIN_WISH)
    items = wishes(raw=True)
    for it in items:
        if it["name"] == name and (it.get("set") or None) == set_code and (it.get("list") or MAIN_WISH) == list_id                 and (not set_code or str(it.get("number") or "") == str(number or "")):
            it["count"] = int(it.get("count", 1)) + int(count)
            save_wishes(items)
            return items
    items.append({"name": name, "count": int(count), "set": set_code, "number": number, "note": note,
                  "added": time.time(), "list": list_id})
    save_wishes(items)
    return items


def add_wish_in(game, name, set_code=None, number=None, list_id=MAIN_WISH, count=1):
    """Put a card on a wish or own list of any game (without switching there) – e.g. from
    a friend's collection that belongs to another game. Same printing on the same list: count +1."""
    import games
    sc = (set_code or "").lower() or None
    num = number if sc else None
    if not game or game == games.current().key:
        return add_wish(name, count, sc, num, list_id=list_id)
    f = games.mine(game) / "wishlist.json"
    try:
        items = json.loads(f.read_text("utf-8")).get("items", [])
    except (OSError, ValueError):
        items = []
    me = next((w for w in items if w["name"] == name and (w.get("set") or None) == sc
               and str(w.get("number") or "") == str(num or "") and (w.get("list") or MAIN_WISH) == list_id), None)
    if me is not None:
        me["count"] = int(me.get("count", 1)) + int(count)
    else:
        items.append({"name": name, "count": int(count), "set": sc, "number": num, "note": "",
                      "added": time.time(), "list": list_id})
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=1), "utf-8")
    return items


def wish_key(w):
    """Key of a wish: name|set|number – without set/number = "any version"; a print with language/finish (e.g. from
    a log) gets |lang|foil on top, so a German foil and the English copy stay two entries."""
    key = f"{w['name']}|{(w.get('set') or '').lower()}|{w.get('number') or ''}"
    if w.get("set") and (w.get("lang") or w.get("foil")):
        key += f"|{w.get('lang') or 'en'}|{1 if w.get('foil') else 0}"
    return key


def set_pinned(key, list_id, pinned, set_code=None, number=None):
    """Pin/unpin a wish. Unpinning: becomes "any version" (and is merged with an existing one)."""
    items = wishes(raw=True)
    me = next((w for w in items if wish_key(w) == key and (w.get("list") or MAIN_WISH) == list_id), None)
    if me is None:
        return
    if pinned:
        me["set"], me["number"] = set_code, number
    else:
        me["set"] = me["number"] = None
        same = next((w for w in items if w is not me and w["name"] == me["name"] and not w.get("set")
                     and (w.get("list") or MAIN_WISH) == list_id), None)
        if same is not None:
            same["count"] = int(same.get("count", 1)) + int(me.get("count", 1))
            items.remove(me)
    save_wishes(items)


def set_wish_count(key, list_id, n):
    """Set the count of a wish (key as in wish_key) in a list – 0 removes it."""
    items = wishes(raw=True)
    for w in list(items):
        if wish_key(w) == key and (w.get("list") or MAIN_WISH) == list_id:
            if n > 0:
                w["count"] = int(n)
            else:
                items.remove(w)
    save_wishes(items)


def remove_wish(name, set_code=None, list_id=None):
    """Remove a wish – without set_code all printings of this card, without list_id from all lists."""
    items = [it for it in wishes(raw=True) if not (it["name"] == name and (set_code is None
                                                                   or (it.get("set") or None) == set_code)
                                           and (list_id is None or (it.get("list") or MAIN_WISH) == list_id))]
    save_wishes(items)
    return items


# ---------- Lists ----------
def _lists_file(game=None):
    """lists.json of the open game – or of another one (assign a list to another game when creating it)."""
    import games
    if not game or game == games.current().key:
        return LISTS_FILE
    return games.mine(game) / "lists.json"


def _read_lists(game=None):
    try:
        d = json.loads(_lists_file(game).read_text("utf-8"))
    except (OSError, ValueError):
        d = {}
    wish = [x for x in d.get("wish") or [] if x.get("id")]
    have = [x for x in d.get("have") or [] if x.get("id")]
    custom = [x for x in d.get("custom") or [] if x.get("id")]   # own lists (cards stored like wishes)
    # the default lists may be deleted (Oliver, review .101) – they come back by themselves as soon as something
    # lands on them again (a star on a card, a copy marked for trade)
    gone = [g for g in d.get("gone") or [] if g in (MAIN_WISH, MAIN_HAVE) and not _main_used(g, game)]
    if MAIN_WISH not in gone and not any(x["id"] == MAIN_WISH for x in wish):
        wish.insert(0, {"id": MAIN_WISH, "name": "Wunschliste"})
    if MAIN_HAVE not in gone and not any(x["id"] == MAIN_HAVE for x in have):
        have.insert(0, {"id": MAIN_HAVE, "name": "Tauschkarten"})
    out = {"wish": wish, "have": have, "custom": custom}
    if gone:
        out["gone"] = gone
    return out


def _revive(lid):
    """A deleted default list is wanted again (a card starred): it stays from now on."""
    try:
        d = json.loads(LISTS_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return
    if lid in (d.get("gone") or []):
        d["gone"] = [g for g in d["gone"] if g != lid]
        _write_lists(d)


_used_cache = {}   # (game, main id) -> (file state, used?) – read the big files again only when they change


def _main_used(lid, game=None):
    """Is there something on a deleted default list again? Wishlist: a wish without its own list; trade cards: a
    copy in the collection marked for trade."""
    folder = _lists_file(game).parent if game else MINE
    f = folder / ("wishlist.json" if lid == MAIN_WISH else "collection.json")
    sig, key = _file_sig(f), (str(f), lid)
    hit = _used_cache.get(key)
    if hit is not None and hit[0] == sig:
        return hit[1]
    try:
        items = json.loads(f.read_text("utf-8")).get("items", [])
    except (OSError, ValueError):
        items = []
    if lid == MAIN_WISH:
        used = any((w.get("list") or MAIN_WISH) == MAIN_WISH for w in items)
    else:
        used = any(int(it.get("trade") or 0) > 0 for it in items)
    _used_cache[key] = (sig, used)
    return used


def _write_lists(d, game=None):
    f = _lists_file(game)
    f.parent.mkdir(parents=True, exist_ok=True)
    if f == LISTS_FILE:
        from system import undo
        undo.before_write(LISTS_FILE, "Listen")
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1), "utf-8")


def lists(kind):
    """kind "wish" | "have" | "custom" -> [{"id", "name", ...}] (the default list always first)."""
    return _read_lists()[kind]


def game_overview(key):
    """Lists of ANOTHER game, read only (without switching): [{"kind", "id", "name", "count"}] – for the overview
    of lists by game. Automatic trade lists are not counted here (only the game itself can do that)."""
    import games
    mine = games.mine(key)
    sig = tuple(_file_sig(mine / n) for n in ("lists.json", "wishlist.json", "collection.json"))
    hit = _overview_cache.get(key)
    if hit is not None and hit[0] == sig:   # unchanged: don't read again (trade/alerts ask often)
        return [dict(r) for r in hit[1]]

    def read(name, default):
        try:
            return json.loads((mine / name).read_text("utf-8"))
        except (OSError, ValueError):
            return default
    d = read("lists.json", {})
    items = read("wishlist.json", {}).get("items", [])
    coll = read("collection.json", {}).get("items", [])
    out = []
    for kind in ("wish", "custom", "have"):
        rows = [x for x in d.get(kind) or [] if x.get("id")]
        main = {"wish": MAIN_WISH, "have": MAIN_HAVE}.get(kind)
        if main and not any(x["id"] == main for x in rows):
            rows.insert(0, {"id": main, "name": "Wunschliste" if kind == "wish" else "Tauschkarten"})
        for x in rows:
            lid = x["id"]
            if kind in ("wish", "custom"):
                n = sum(int(w.get("count", 1)) for w in items if (w.get("list") or MAIN_WISH) == lid)
            elif lid == MAIN_HAVE:
                n = sum(min(int(it.get("trade") or 0), int(it.get("count", 1))) for it in coll)
            else:
                n = sum((x.get("items") or {}).values()) if not x.get("rule") else None
            out.append({"kind": kind, "id": lid, "name": x.get("name") or "", "count": n,
                        "main": lid in (MAIN_WISH, MAIN_HAVE)})
    _overview_cache[key] = (sig, out)
    return [dict(r) for r in out]


_overview_cache = {}   # game -> (file states, overview) – re-read other games only when their files change


def _file_sig(f):
    try:
        st = f.stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def add_list(kind, name, example=False, rule=None, shared=False, game=None, top=False):
    """New list. rule (trade lists only): automatic list – {"filters", "text", "keep", "no_decks"}; its
    content is computed from the collection (rule_counts) and keeps itself up to date.
    shared: shared with friends (otherwise private – default). game: create in another game (without switching).
    top: first of its kind, above the default list (the library's list column – Oliver, review .101)."""
    d = _read_lists(game)
    lid = uuid.uuid4().hex[:10]
    entry = {"id": lid, "name": name.strip() or {"have": "Liste", "custom": "Liste"}.get(kind, "Wunschliste")}
    if kind == "have":
        entry["items"] = {}
        if rule:
            entry["rule"] = rule
    if example:
        entry["example"] = True
    if shared and kind in SHAREABLE:
        entry["shared"] = True
    if top:   # the very first of its kind – above the default list too (Oliver, review .101)
        d[kind].insert(0, entry)
    else:
        d[kind].append(entry)
    _write_lists(d, game)
    return lid


SHAREABLE = ("wish", "have")   # own lists always stay private


def is_shared(x):
    """List visible to friends? Default: private (also for all older lists)."""
    return bool(x.get("shared"))


def set_shared(kind, lid, on):
    d = _read_lists()
    for x in d[kind]:
        if x["id"] == lid:
            if on and kind in SHAREABLE:
                x["shared"] = True
            else:
                x.pop("shared", None)
    _write_lists(d)


def reorder_list(kind, src, target, after=False):
    """Move list src before (or after) list target – the order is the one in lists.json."""
    d = _read_lists()
    rows = d[kind]
    x = next((x for x in rows if x["id"] == src), None)
    if x is None or src == target:
        return
    rows.remove(x)
    i = next((i for i, y in enumerate(rows) if y["id"] == target), len(rows) - (1 if after else 0))
    rows.insert(i + (1 if after else 0), x)
    _write_lists(d)


def rename_list(kind, lid, name):
    d = _read_lists()
    for x in d[kind]:
        if x["id"] == lid and name.strip():
            x["name"] = name.strip()
    _write_lists(d)


def remove_list(kind, lid, coll=None):
    """Delete a list. The list's wishes go with it. The default lists only with coll (deleted on purpose in the
    library, review .101): then there simply is none until something lands on it again – trade cards: the copies are
    no longer marked for trade."""
    if lid in (MAIN_WISH, MAIN_HAVE) and coll is None:
        return
    if lid == MAIN_HAVE:
        clear_list(kind, lid, coll)
    d = _read_lists()
    d[kind] = [x for x in d[kind] if x["id"] != lid]
    if lid in (MAIN_WISH, MAIN_HAVE):
        d["gone"] = sorted(set(d.get("gone") or []) | {lid})
    _write_lists(d)
    if kind in ("wish", "custom"):
        save_wishes([w for w in wishes(raw=True) if (w.get("list") or MAIN_WISH) != lid])


# ---------- Copy, move, merge lists ----------
def kind_of(lid):
    """Kind of a list ("wish" | "have" | "custom") or None."""
    d = _read_lists()
    return next((k for k in ("wish", "have", "custom") if any(x["id"] == lid for x in d[k])), None)


def merged_entries(entries):
    """The same print (name, set, number, language, foil) once with the summed count – in the order first seen
    ("4× Sol Ring" instead of four rows in an opened list, like the web, 03.11.)."""
    out, at = [], {}
    for e in entries:
        k = (e["name"], e.get("set"), e.get("number"), e.get("lang"), bool(e.get("foil")))
        if k in at:
            at[k]["count"] += e["count"]
        else:
            at[k] = dict(e)
            out.append(at[k])
    return out


def list_entries(kind, lid, items):
    """Content of a list, uniform: [{"name", "set", "number", "count", "lang", "foil", "uid"}]
    (items = collection, for trade lists)."""
    if kind in ("wish", "custom"):
        return [{"name": w["name"], "set": w.get("set"), "number": w.get("number"), "count": int(w.get("count", 1)),
                 "lang": w.get("lang"), "foil": bool(w.get("foil")), "uid": None} for w in wishes([lid])]
    out = [{"name": it["name"], "set": (it.get("set") or "").lower() or None, "number": it.get("number"),
            "count": n, "lang": it.get("lang") or "en", "foil": bool(it.get("foil")), "uid": it.get("uid")}
           for it, n in have_items(items, [lid])]
    names = have_print_names(lid)
    for pk, n in have_prints(lid).items():
        sc, num, lang, foil = (pk.split("|") + ["", "", "en", "0"])[:4]
        out.append({"name": names.get(pk, ""), "set": sc or None, "number": num or None, "count": int(n),
                    "lang": lang or "en", "foil": foil == "1", "uid": None})
    return [e for e in out if e["name"] and e["count"] > 0]


def put_entries(kind, lid, entries, coll):
    """Put entries (as in list_entries) into a list – counts are added. Trade lists: own copies (as
    many as there are), the rest as a printing (red, "not in the collection")."""
    if kind in ("wish", "custom"):
        items = wishes(raw=True)
        for e in entries:
            sc = (e.get("set") or "").lower() or None
            num = e.get("number") if sc else None
            # a print keeps its language and finish ("As list" from a log: a German foil is not the English copy)
            lang = (e.get("lang") or None) if sc else None
            foil = bool(e.get("foil")) if sc else False
            me = next((w for w in items if w["name"] == e["name"] and (w.get("set") or None) == sc
                       and str(w.get("number") or "") == str(num or "") and (w.get("lang") or None) == lang
                       and bool(w.get("foil")) == foil and (w.get("list") or MAIN_WISH) == lid), None)
            if me is not None:
                me["count"] = int(me.get("count", 1)) + int(e["count"])
            else:
                w = {"name": e["name"], "count": int(e["count"]), "set": sc, "number": num, "note": "",
                     "added": time.time(), "list": lid}
                if lang:
                    w["lang"] = lang
                if foil:
                    w["foil"] = True
                items.append(w)
        save_wishes(items)
        return
    d = _read_lists()
    entry = next((x for x in d["have"] if x["id"] == lid), None)
    if entry is None:
        return
    owned = {it["uid"]: it for it in coll.items}
    for e in entries:
        left = int(e["count"])
        cands = [owned[e["uid"]]] if e.get("uid") in owned else [
            it for it in coll.items if it["name"] == e["name"]
            and (not e.get("set") or (it.get("set") or "").lower() == (e.get("set") or "").lower())
            and (not e.get("number") or str(it.get("number") or "") == str(e.get("number")))]
        for it in cands:
            if left <= 0:
                break
            have = have_count(it, lid)
            room = int(it.get("count", 1)) - have
            if room <= 0:
                continue
            add = min(room, left)
            left -= add
            if lid == MAIN_HAVE:
                coll.update(it["uid"], trade=have + add)
            else:
                entry.setdefault("items", {})[it["uid"]] = have + add
        if left > 0 and e.get("set"):
            pk = f"{(e.get('set') or '').lower()}|{e.get('number') or ''}|{e.get('lang') or 'en'}|" \
                 f"{1 if e.get('foil') else 0}"
            pr = entry.setdefault("prints", {})
            pr[pk] = int(pr.get(pk, 0)) + left
            entry.setdefault("print_names", {})[pk] = e["name"]
    _write_lists(d)
    if lid == MAIN_HAVE:
        coll.save()


def clear_list(kind, lid, coll):
    """Empty a list (the list itself stays)."""
    if kind in ("wish", "custom"):
        save_wishes([w for w in wishes(raw=True) if (w.get("list") or MAIN_WISH) != lid])
        return
    if lid == MAIN_HAVE:
        for it in coll.items:
            if int(it.get("trade") or 0):
                coll.update(it["uid"], trade=0)
        coll.save()
    d = _read_lists()
    for x in d["have"]:
        if x["id"] == lid:
            x["items"], x["prints"], x["print_names"] = {}, {}, {}
    _write_lists(d)


def copy_list(kind, lid, coll, to_kind=None, name=None):
    """Copy of a list (also into another kind: wish, trade, own list) -> new id."""
    to_kind = to_kind or kind
    src = next((x for x in lists(kind) if x["id"] == lid), None)
    if src is None:
        return None
    new = add_list(to_kind, name or src["name"])
    put_entries(to_kind, new, list_entries(kind, lid, coll.items), coll)
    return new


def move_list(kind, lid, to_kind, coll):
    """Move a list into another kind (default lists are copied and emptied) -> new id."""
    if to_kind == kind:
        return lid
    new = copy_list(kind, lid, coll, to_kind)
    if lid in (MAIN_WISH, MAIN_HAVE):
        clear_list(kind, lid, coll)
    else:
        remove_list(kind, lid)
    return new


def merge_lists(kind, lid, into_kind, into_lid, coll):
    """Put list lid into into_lid and delete it afterwards (default lists: only empty them)."""
    if (kind, lid) == (into_kind, into_lid):
        return
    put_entries(into_kind, into_lid, list_entries(kind, lid, coll.items), coll)
    if lid in (MAIN_WISH, MAIN_HAVE):
        clear_list(kind, lid, coll)
    else:
        remove_list(kind, lid)


def entry_rows(kind, lid, coll):
    """Entries of a list for display: [{"key", "name", "extra", "count", "red"}] – key for change_entry."""
    out = []
    if kind in ("wish", "custom"):
        agg = {}
        for w in wishes([lid]):
            key = wish_key(w)
            extra = f"{(w.get('set') or '').upper()} #{w.get('number')}" if w.get("set") else ""
            if extra and w.get("foil"):
                extra += " · Foil"
            if extra and (w.get("lang") or "en") != "en":
                extra += f" · {w['lang'].upper()}"
            e = agg.setdefault(key, {"key": key, "name": w["name"], "count": 0, "red": False, "extra": extra})
            e["count"] += int(w.get("count", 1))
        out = list(agg.values())
    else:
        for it, n in have_items(coll.items, [lid]):
            extra = f"{str(it.get('set') or '').upper()} #{it.get('number')}" + (" · Foil" if it.get("foil") else "")
            if (it.get("lang") or "en") != "en":
                extra += f" · {(it.get('lang') or 'en').upper()}"
            out.append({"key": it["uid"], "name": it["name"], "extra": extra, "count": n, "red": False,
                        "max": int(it.get("count", 1))})   # + only up to the copies you have
        names = have_print_names(lid)
        for pk, n in have_prints(lid).items():
            sc, num, lang, foil = (pk.split("|") + ["", "", "en", "0"])[:4]
            out.append({"key": "p:" + pk, "name": names.get(pk, pk), "count": int(n), "red": True,
                        "extra": f"{sc.upper()} #{num}" + (" · Foil" if foil == "1" else "")})
    return sorted([e for e in out if e["count"] > 0], key=lambda e: (e["name"], e["extra"]))


def change_entry(kind, lid, key, delta, coll):
    """Change an entry of a list: delta +1 / -1 / None (= remove completely)."""
    if kind in ("wish", "custom"):
        items = wishes(raw=True)
        mine = [w for w in items if wish_key(w) == key and (w.get("list") or MAIN_WISH) == lid]
        if not mine:
            return
        if delta is None or (delta < 0 and sum(int(w.get("count", 1)) for w in mine) <= 1):
            for w in mine:
                items.remove(w)
        else:
            mine[0]["count"] = max(1, int(mine[0].get("count", 1)) + delta)
        save_wishes(items)
    elif str(key).startswith("p:"):
        pk = str(key)[2:]
        n = have_prints(lid).get(pk, 0)
        set_have_print(lid, pk, 0 if delta is None else max(0, n + delta))
    else:
        it = coll.get(key)
        if it is None:
            return
        n = have_count(it, lid)
        n = 0 if delta is None else max(0, min(int(it.get("count", 1)), n + delta))
        if lid == MAIN_HAVE:
            coll.update(key, trade=n)
            coll.save()
        else:
            set_have(lid, key, n)


def snapshot_lists(coll):
    """State of all lists (for "Undo" after merging/moving)."""
    def text(p):
        try:
            return p.read_text("utf-8")
        except OSError:
            return None
    return {"lists": text(LISTS_FILE), "wishes": text(WISH_FILE),
            "trade": {it["uid"]: int(it.get("trade") or 0) for it in coll.items}}


def restore_lists(snap, coll):
    for path, key in ((LISTS_FILE, "lists"), (WISH_FILE, "wishes")):
        if snap.get(key) is not None:
            MINE.mkdir(parents=True, exist_ok=True)
            path.write_text(snap[key], "utf-8")
    old = snap.get("trade") or {}
    for it in coll.items:
        n = old.get(it["uid"], 0)
        if int(it.get("trade") or 0) != n:
            coll.update(it["uid"], trade=n)
    coll.save()


# ---------- Automatic trade lists (rule instead of manual work) ----------
COLLECTION = [lambda: []]   # the app sets lambda: collection.items here (trade doesn't know the collection otherwise)
DECK_NAMES = [lambda: {}]   # {card name: count in decks} – for "exclude cards in decks"
_rule_cache = {}


def is_auto(lid):
    return any(x["id"] == lid and x.get("rule") for x in _read_lists()["have"])


def rule_counts(x, items=None):
    """{uid: count} of an automatic list: all own cards that match the saved search; per card
    (name) "keep" copies stay – and, if desired, whatever is in decks. Cached briefly."""
    from cards import carddb
    from collection.collection import price as item_price, scryfall_id
    items = COLLECTION[0]() if items is None else items
    rule = x.get("rule") or {}
    key = (x["id"], json.dumps(rule, sort_keys=True, default=str), len(items),
           sum(int(it.get("count", 1)) for it in items), int(time.time() // 5))
    if key in _rule_cache:
        return _rule_cache[key]
    f = {k: v for k, v in (rule.get("filters") or {}).items() if k not in ("owned",)}
    rng = {k: tuple(v) for k, v in (f.pop("ranges", None) or {}).items()}
    lo, hi = rng.pop("price", (None, None))   # price: that of your own copy (foil, language …)
    if rng:
        f["ranges"] = rng
    text = rule.get("text") or ""
    sids = {scryfall_id(it["id"]) for it in items}
    ok = None
    if (text or any(v for k, v in f.items() if k not in ("no_tokens",))) and carddb.exists():
        try:
            ok = set(carddb.matching_ids(text, only_ids=list(sids), **f))
        except Exception:  # noqa: BLE001 – invalid search: empty
            ok = set()
    cand = []
    for it in items:
        if ok is not None and scryfall_id(it["id"]) not in ok:
            continue
        p = item_price(it)
        if (lo is not None and (p or 0) < lo) or (hi is not None and (p or 0) > hi):
            continue
        cand.append(it)
    keep = max(0, int(rule.get("keep") or 0))
    in_decks = DECK_NAMES[0]() if rule.get("no_decks") else {}
    by_name = {}
    for it in cand:
        by_name.setdefault(it.get("name") or "", []).append(it)
    out = {}
    for name, its in by_name.items():
        # keep the cheapest copies first (the valuable ones go into the trade)
        hold = keep + int(in_decks.get(name, 0))
        for it in sorted(its, key=lambda i: item_price(i) or 0):
            n = int(it.get("count", 1))
            take = min(n, hold)
            hold -= take
            if n - take > 0:
                out[it.get("uid")] = n - take
    if len(_rule_cache) > 50:
        _rule_cache.clear()
    _rule_cache[key] = out
    return out


def have_count(it, lid):
    """How many of this collection entry are in list lid."""
    if lid == MAIN_HAVE:
        return min(int(it.get("trade") or 0), int(it.get("count", 1)))
    for x in _read_lists()["have"]:
        if x["id"] == lid:
            src = rule_counts(x) if x.get("rule") else (x.get("items") or {})
            return min(int(src.get(it.get("uid"), 0)), int(it.get("count", 1)))
    return 0


def have_counts(lid):
    """{uid: count} of an own list (not for "Tauschkarten" – those are stored on the entries)."""
    for x in _read_lists()["have"]:
        if x["id"] == lid:
            return dict(rule_counts(x) if x.get("rule") else (x.get("items") or {}))
    return {}


def set_have(lid, uid, n):
    d = _read_lists()
    for x in d["have"]:
        if x["id"] == lid:
            items = x.setdefault("items", {})
            if n > 0:
                items[uid] = int(n)
            else:
                items.pop(uid, None)
    _write_lists(d)


def have_prints(lid):
    """{"set|number|lang|foil": count} – printings in a trade list that are not (yet) in the collection."""
    for x in _read_lists()["have"]:
        if x["id"] == lid:
            return dict(x.get("prints") or {})
    return {}


def have_print_names(lid):
    for x in _read_lists()["have"]:
        if x["id"] == lid:
            return dict(x.get("print_names") or {})
    return {}


def set_have_print(lid, key, n, name=None):
    d = _read_lists()
    for x in d["have"]:
        if x["id"] == lid:
            pr = x.setdefault("prints", {})
            names = x.setdefault("print_names", {})
            if n > 0:
                pr[key] = int(n)
                if name:
                    names[key] = name
            else:
                pr.pop(key, None)
                names.pop(key, None)
    _write_lists(d)


def have_items(items, list_ids=None):
    """Own cards from lists: [(entry, count)] – per entry the maximum across the lists (merged)."""
    d = _read_lists()["have"]
    ids = [x["id"] for x in d] if list_ids is None else list(list_ids)
    custom = {x["id"]: (rule_counts(x, items) if x.get("rule") else x.get("items") or {}) for x in d
              if x["id"] in ids}
    out = []
    for it in items:
        n = 0
        for lid in ids:
            if lid == MAIN_HAVE:
                n = max(n, int(it.get("trade") or 0))
            else:
                n = max(n, int(custom.get(lid, {}).get(it.get("uid"), 0)))
        n = min(n, int(it.get("count", 1)))
        if n > 0:
            out.append((it, n))
    return out


def deck_needs(deck_list, rows_by_id, owned_names):
    """Missing cards of all decks: {name: {"need", "have", "missing", "decks": [deck name]}}.
    A card that is in several decks counts once (the largest need) – it can be moved between decks."""
    out = {}
    for deck in deck_list:
        need = {}
        for sid in deck.get("commanders") or []:
            r = rows_by_id.get(sid)
            if r:
                need[r["name"]] = need.get(r["name"], 0) + 1
        for c in deck.get("cards") or []:
            if c.get("board", "main") != "main":
                continue
            r = rows_by_id.get(c["sid"])
            if r:
                need[r["name"]] = need.get(r["name"], 0) + int(c.get("count", 1))
        for name, n in need.items():
            have = owned_names.get(name, 0)
            if have >= n:
                continue
            e = out.setdefault(name, {"need": 0, "have": have, "missing": 0, "decks": []})
            e["need"] = max(e["need"], n)
            e["missing"] = max(0, e["need"] - have)
            e["decks"].append(deck.get("name") or "Deck")
    return out


# ---------- Trade cards ----------
def tradeable(items):
    """Own trade cards: [(entry, count)] – field "trade" on the collection entries."""
    return [(it, min(int(it.get("trade") or 0), int(it.get("count", 1)))) for it in items if it.get("trade")]


# ---------- Export ----------
def _card_row(it, count):
    return [it["set"].lower(), str(it["number"]), it.get("lang") or "en", 1 if it.get("foil") else 0, int(count),
            it["name"]]


def _merged(cards):
    merged = {}
    for c in cards:  # combine same card/language/foil
        key = (c[0], c[1], c[2], c[3])
        if key in merged:
            merged[key][4] += c[4]
        else:
            merged[key] = list(c)
    return list(merged.values())


def build_export(profile, items, what="all", wish_items=None, deck_missing=None, have=None, library=False):
    """-> dict for our own format. what: "all" (whole collection) | "trade" (trade cards only) | "lists" (have:
    [(entry, count)] from selected lists) | "none". library: additionally send the whole collection (field
    "lib"; with what="all" it is already in "c")."""
    if what == "lists":
        cards = [_card_row(it, n) for it, n in have or [] if n > 0]
    elif what == "trade":
        cards = [_card_row(it, n) for it, n in tradeable(items) if n > 0]
    elif what == "all":
        cards = [_card_row(it, it.get("count", 1)) for it in items]
    else:
        cards = []
    wants = []
    for w in wish_items or []:
        wants.append([w["name"], int(w.get("count", 1)), w.get("set") or "", w.get("number") or ""])
    for name, e in (deck_missing or {}).items():
        if e["missing"] > 0 and not any(x[0] == name for x in wants):
            wants.append([name, e["missing"], "", ""])
    out = {"v": 1, "app": "BentCorner", "id": profile["id"], "name": profile.get("name") or "",
           "back": profile.get("back"), "date": time.time(), "what": what, "c": _merged(cards), "w": wants}
    if library and what != "all":  # trade lists AND library: library separately (older versions only read "c")
        out["lib"] = _merged([_card_row(it, it.get("count", 1)) for it in items])
    return out


def write_bentcorner(path, data):
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(path, "wb") as f:
        f.write(MAGIC + zlib.compress(raw, 9))


TEXT_FORMATS = [("bentcorner", "Bent°Corner (for friends, with wishlist)"), ("manabox", "ManaBox (CSV)"),
                ("moxfield", "Moxfield (CSV)"), ("deckbox", "Deckbox (CSV)"), ("text", "Text list (Arena/MTGO)"),
                ("excel", "Excel spreadsheet (CSV)")]
COLUMNS = [("count", "Anzahl"), ("name", "Name"), ("set", "Set"), ("number", "Nummer"), ("lang", "Sprache"),
           ("foil", "Foil"), ("rarity", "Seltenheit"), ("price", "Preis"), ("mv", "Manawert"), ("type", "Typ"),
           ("text", "Regeltext")]
PRESET_COLUMNS = {"excel": ["count", "name", "set", "number", "lang", "foil", "rarity", "price"]}


def export_custom(groups, path, columns, db_rows=None):
    """CSV with freely chosen columns (semicolon, for Excel). db_rows: {sid: row} for mana value/type/text."""
    db_rows = db_rows or {}
    names = dict(COLUMNS)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([names[c] for c in columns])
        for g in groups:
            r = db_rows.get(g.get("sid")) or {}
            p = g.get("eur_foil") if g.get("foil") else g.get("eur")
            vals = {"count": g["count"], "name": g["name"], "set": g["set"], "number": g["number"],
                    "lang": (g.get("lang") or "en").upper(), "foil": "ja" if g.get("foil") else "",
                    "rarity": g.get("rarity") or "", "price": "" if p is None else f"{p:.2f}".replace(".", ","),
                    "mv": r.get("cmc", ""), "type": r.get("type_line", ""), "text": r.get("oracle_text", "")}
            w.writerow([vals[c] for c in columns])
    return len(groups)


def export_text(groups, path):
    """"4 Lightning Bolt (2X2) 117" – Arena/MTGO/Moxfield text."""
    lines = [f"{g['count']} {g['name']} ({g['set'].upper()}) {g['number']}" + (" *F*" if g.get("foil") else "")
             for g in groups]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return len(lines)


def export_deckbox(groups, path):
    lang = {"en": "English", "de": "German", "fr": "French", "it": "Italian", "es": "Spanish", "pt": "Portuguese",
            "ja": "Japanese", "ko": "Korean", "ru": "Russian", "zhs": "Chinese", "zht": "Traditional Chinese"}
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Count", "Tradelist Count", "Name", "Edition", "Card Number", "Condition", "Language", "Foil"])
        for g in groups:
            from cards import conditions
            w.writerow([g["count"], g.get("trade_count", 0), g["name"], g["set"].upper(), g["number"],
                        conditions.moxfield(g),
                        lang.get(g.get("lang") or "en", "English"), "foil" if g.get("foil") else ""])
    return len(groups)


# ---------- Import ----------
def read_file(path):
    """File -> {"kind": "bentcorner"|"csv"|"text", "data": …}. Raises ValueError for unknown formats."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(MAGIC):
        d = json.loads(zlib.decompress(raw[len(MAGIC):]).decode("utf-8"))
        if d.get("app") != "BentCorner" or not d.get("id"):
            raise ValueError(tr("Not a Bent°Corner file"))
        return {"kind": "bentcorner", "data": d}
    text = raw.decode("utf-8-sig", errors="replace")
    first = text.splitlines()[0] if text.strip() else ""
    if "," in first or ";" in first:
        return {"kind": "csv", "data": parse_csv(text)}
    cards = parse_text(text)
    if cards:
        return {"kind": "text", "data": cards}
    raise ValueError(tr("Format not recognized"))


_HEAD = {"name": ("name", "card name", "card", "kartenname"),
         # order matters: "Edition Code" before "Edition" (in Deckbox, "Edition" holds the set name)
         "set": ("set code", "edition code", "setcode", "set-code", "edition", "set"),
         "number": ("collector number", "card number", "number", "collector_number", "cn", "nummer", "nr", "nr.",
                    "kartennummer", "sammlernummer"),
         "count": ("quantity", "count", "qty", "amount", "anzahl", "menge"),
         "lang": ("language", "lang", "sprache"),
         "foil": ("foil", "printing", "finish"),
         "cond": ("condition", "zustand", "cond"),
         "sid": ("scryfall id", "scryfall-id", "scryfall_id", "scryfallid", "scryfall")}
_LANG_NAMES = {"english": "en", "german": "de", "deutsch": "de", "french": "fr", "italian": "it", "spanish": "es",
               "portuguese": "pt", "japanese": "ja", "korean": "ko", "russian": "ru", "chinese": "zhs",
               "chinese simplified": "zhs", "chinese traditional": "zht", "traditional chinese": "zht",
               "jp": "ja", "japanisch": "ja", "englisch": "en", "französisch": "fr", "italienisch": "it",
               "spanisch": "es", "kr": "ko", "cn": "zhs", "cs": "zhs", "ct": "zht"}


def parse_csv(text):
    """CSV from other apps (ManaBox, Moxfield, Deckbox, Archidekt, Excel export) -> [[set, nr, lang, foil, n, name]]."""
    lines = text.splitlines()
    if lines and lines[0].strip().lower().startswith("sep="):   # Excel hint "sep=," (e.g. Dragon Shield)
        sep = lines[0].strip()[4:5]
        text = "\n".join(lines[1:])
        lines = lines[1:]
    else:
        sep = ""
    if not lines:
        return []
    delim = sep or (";" if lines[0].count(";") > lines[0].count(",") else ",")
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return []
    head = [h.strip().lower() for h in rows[0]]
    col = {}
    for key, names in _HEAD.items():
        for n in names:
            if n in head:
                col[key] = head.index(n)
                break
    if "name" not in col:
        raise ValueError("Keine Spalte „Name“ gefunden")
    from cards import conditions
    # "LP" means Light Played on ManaBox/Cardmarket, Lightly Played on Moxfield/TCGplayer
    source = "manabox" if "manabox id" in head else ("cardmarket" if "cardmarket id" in head
                                                     or "idproduct" in head else "")
    out = []
    for r in rows[1:]:
        def val(k):
            i = col.get(k)
            return r[i].strip() if i is not None and i < len(r) else ""
        name = val("name")
        if not name:
            continue
        try:
            n = int(float(val("count") or 1))
        except ValueError:
            n = 1
        lang = val("lang").lower()
        lang = _LANG_NAMES.get(lang, lang if len(lang) <= 3 and lang else "en")
        foil = val("foil").lower() in ("foil", "etched", "true", "yes", "ja", "1", "x")
        row = [val("set").lower(), val("number"), lang or "en", 1 if foil else 0, max(1, n), name]
        cond = conditions.from_text(val("cond"), source)
        if val("sid") or cond:
            row.append(val("sid").lower())  # exact printing (e.g. from our own export)
        if cond:
            row.append(cond)   # condition (ManaBox near_mint, Moxfield "Lightly Played", Cardmarket "EX" …)
        out.append(row)
    return out


_FOIL = re.compile(r"\*[FE]\*\s*$")   # "*F*" foil, "*E*" etched (Moxfield/Arena)


def parse_text(text):
    """Text list -> [[set, nr, lang, foil, n, name(, print ID)]]. Read line by line like deck lists (decks.parse_text:
    "4 Lightning Bolt (2X2) 117 *F*", Lorcana sets of one character "(1) 5", Archidekt [tags]) – a simulator
    list "4xAB01-016" brings its print ID instead of a name. Only lines that start with a count are cards (otherwise any
    text file would be a card list)."""
    from collection import decks
    out = []
    for line in text.splitlines():
        if not re.match(r"^\s*\d", line):
            continue   # headings ("Deck", "Sideboard"), titles, notes
        parsed = decks.parse_text(line)
        if not parsed:
            continue
        n, name, code, number, _board = parsed[0]
        foil = 1 if _FOIL.search(line) else 0
        if decks._ID_LINE.match(line.strip()):
            out.append(["", "", "en", foil, n, "", name])   # exact print by its ID (importview.resolve)
        else:
            out.append([code, number, "en", foil, n, name])
    return out


def friend_from_import(parsed, name=None, fid=None, as_new=False):
    """Parsed file -> friend library (saved). Bent°Corner files keep their ID (update),
    unless as_new. Other formats get a new ID and the given name."""
    now = time.time()
    if parsed["kind"] == "bentcorner":
        d = parsed["data"]
        keep_id = not as_new and SAFE_ID.fullmatch(str(d.get("id") or ""))   # a strange id from a file: a new one
        out = {"id": d["id"] if keep_id else uuid.uuid4().hex, "name": name or d.get("name") or "Freund",
               "back": d.get("back"), "date": d.get("date") or now, "imported": now, "what": d.get("what"),
               "cards": d.get("c") or [], "wants": d.get("w") or [], "source": "bentcorner"}
        # library: its own field – or "c" if the whole collection was sent
        lib = d.get("lib") if d.get("lib") is not None else (d.get("c") if d.get("what") == "all" else None)
        if lib is not None:
            out["library"] = lib
    else:
        rows = [r[:7] for r in parsed["data"]]   # no condition (column 8 only exists on collection import)
        out = {"id": fid or uuid.uuid4().hex, "name": name or "Freund", "back": None, "date": now, "imported": now,
               "what": "all", "cards": rows, "wants": [], "source": parsed["kind"], "library": rows}
    old = friend(out["id"])
    if old and not as_new:
        out["name"] = name or old.get("name") or out["name"]  # a name you assigned yourself stays
        out["previous"] = len(old.get("cards") or [])
        out["folder"] = old.get("folder") or ""
    save_friend(out)
    return out


# ---------- Clean up examples ----------
def drop_examples():
    """Remove examples that used to ship (friends Mia, Jonas, Lea and the list "Beispiel-Wünsche") – they no longer
    exist; real friends and own lists stay untouched. -> number removed"""
    n = 0
    if FRIENDS.exists():
        for f in FRIENDS.glob("*.json"):
            try:
                d = json.loads(f.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            if d.get("example") or str(d.get("id") or "").startswith("example-"):
                try:
                    f.unlink()
                    n += 1
                except OSError:
                    pass
    for kind in ("wish", "have", "custom"):
        for x in [x for x in lists(kind) if x.get("example")]:
            remove_list(kind, x["id"])
            n += 1
    return n


# ---------- Trade proposal ----------
def proposal(my_items, my_wants, friend_d, owned_names, prices, my_have=None):
    """What matches?
    get:  the friend's cards that I want (wishlist + missing deck cards)
    give: my trade cards that they want (their wishlist from the file)
    prices: {name: price €}. -> {"get": [(name, count, price)], "give": [...], "get_sum", "give_sum"}"""
    theirs = friend_cards_by_name(friend_d)
    get = []
    for name, want in my_wants.items():
        n = min(want, theirs.get(name, 0))
        if n > 0:
            get.append((name, n, prices.get(name)))
    give = []
    mine = {}
    for it, n in (my_have if my_have is not None else tradeable(my_items)):
        mine[it["name"]] = mine.get(it["name"], 0) + n
    for w in friend_d.get("wants") or []:
        name, want = w[0], int(w[1] or 1)
        n = min(want, mine.get(name, 0))
        if n > 0:
            give.append((name, n, prices.get(name)))
    total = lambda rows: round(sum((p or 0) * n for _, n, p in rows), 2)  # noqa: E731
    return {"get": sorted(get, key=lambda t: -(t[2] or 0)), "give": sorted(give, key=lambda t: -(t[2] or 0)),
            "get_sum": total(get), "give_sum": total(give)}


# ---------- After a trade: update the lists ----------
def after_trade(coll, taken, got, from_have=True, from_wish=True):
    """Traded: remove given-away copies (taken: [{"uid", "n"}] from the booking) from trade cards and own
    trade lists, strike received cards (got: [set, number, language, foil, count, name]) from the wishlists
    – only the traded count each time (of 5 Sol Rings on the list, one goes away).
    -> (fewer trade list entries, fewer wishes)"""
    n_have = n_wish = 0
    if from_have and taken:
        by_uid = {}
        for tk in taken:
            by_uid[tk["uid"]] = by_uid.get(tk["uid"], 0) + int(tk.get("n") or 1)
        for uid, n in by_uid.items():
            it = coll.get(uid)
            if it is not None and int(it.get("trade") or 0) > 0:
                k = min(n, int(it["trade"]))
                coll.update(uid, trade=int(it["trade"]) - k)
                n_have += k
        d = _read_lists()
        changed = False
        for x in d["have"]:
            items = x.get("items") or {}
            for uid, n in by_uid.items():
                if uid in items:
                    left = int(items[uid]) - n
                    n_have += min(n, int(items[uid]))
                    if left > 0:
                        items[uid] = left
                    else:
                        items.pop(uid)
                    changed = True
        if changed:
            _write_lists(d)
    if from_wish and got:
        items = wishes(raw=True)
        custom = {x["id"] for x in _read_lists()["custom"]}
        changed = False
        for c in got:
            name, n = (c[5] if len(c) > 5 else ""), int(c[4] or 1)
            # exactly this printing first, then "any version"
            cands = sorted([w for w in items if w.get("name") == name and (w.get("list") or MAIN_WISH) not in custom],
                           key=lambda w: not (str(w.get("set") or "").lower() == str(c[0]).lower()
                                              and str(w.get("number") or "") == str(c[1])))
            for w in cands:
                if n <= 0:
                    break
                k = min(n, int(w.get("count", 1)))
                w["count"] = int(w.get("count", 1)) - k
                n -= k
                n_wish += k
                changed = True
        if changed:
            save_wishes([w for w in items if int(w.get("count", 1)) > 0])
    return n_have, n_wish
