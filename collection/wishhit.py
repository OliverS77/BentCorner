"""Wishlist hits while scanning (lead/Gordon/legal 14.11.2026, 0.9.9): a counted card is checked against all own
wishlists and taken off every list whose "Remove automatically when scanning" is on (per list in lists.json,
default on – Oliver/lead 14.11.; trade.scan_removes); friends' shared wishlists
(their files already on this PC) only give names back.

    r = hit(card, settings)   # card: the counted entry – name, set, number (lang/foil/id are ignored)
    -> {"lists": [{"id", "name", "n", "removed"}], "removed": bool, "undo": token | None,
        "friends": [{"name", "lists": []}]}
    undo(token, list_id=None) # puts exactly the removed amount back (None: all lists, else only that one; a list
                              # already put back is never added twice) -> number of wishes changed

Rules:
- a wish with set + number counts only for that print (language/foil of the wish don't matter – lead 14.11.);
  a wish with only a name counts for every print. Only wishlists (kind "wish"), never own lists ("custom").
- per list one wish is lowered: count > 1 → minus 1, else the wish goes; the exact print before a name-only wish.
- removing and undo both go through trade.save_wishes – the normal Ctrl+Z step and the normal sync recording
  (syncrun.saved → syncops), so other devices see both. Undo is a normal change that ADDS the removed amount back
  (Gordon 14.11.): whatever changed in between stays; a list deleted in between is not brought back.
- friends (legal 14.11.): read from the friends' files of the open game at every call – a friendship ended or a
  share withdrawn deletes that file (net/relay.py), so there are no hits from it any more. Nothing is sent or stored.
  "lists" stays empty: a friend's file only has the wants of all their shared lists merged (trade.export) – the
  list names never reach this PC, and sending them would be a change in what is shared (legal first).

Speed (scanner calls it on the UI thread when counting): the wishlist, the lists and each friend file are parsed
again only when the file changed (mtime/size); a miss costs a few stat calls.
"""
import json
import pathlib

from collection import trade
from system.i18n import tr

_cache = {}   # path -> ((mtime_ns, size), parsed)


def _sig(path):
    try:
        st = path.stat()
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def _parsed(path, parse):
    sig = _sig(path)
    if sig is None:
        _cache.pop(str(path), None)
        return None
    hit_ = _cache.get(str(path))
    if hit_ and hit_[0] == sig:
        return hit_[1]
    try:
        val = parse(json.loads(path.read_text("utf-8")))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    _cache[str(path)] = (sig, val)
    return val


def _norm(s):
    return str(s or "").strip().casefold()


def _matches(name, set_code, number, card):
    """name/set/number of a wish (or a friend's want) against the counted card."""
    if _norm(name) != _norm(card.get("name")):
        return False
    if not set_code:
        return True                                        # name only: every print
    return (_norm(set_code) == _norm(card.get("set"))
            and str(number or "").strip().lower() == str(card.get("number") or "").strip().lower())


def _game():
    import games
    return games.current().key


def _wish_lists():
    """[(id, shown name, removes when scanning)] of the open game's wishlists (the default list's name translated)."""
    out = []
    for x in trade.lists("wish"):
        main = x["id"] == trade.MAIN_WISH
        out.append((x["id"], tr(x["name"]) if main else x["name"], trade.scan_removes(x)))
    return out


def _same(w, row):
    return (w.get("name") == row["name"] and (w.get("set") or None) == (row.get("set") or None)
            and str(w.get("number") or "") == str(row.get("number") or "")
            and (w.get("lang") or None) == (row.get("lang") or None) and bool(w.get("foil")) == bool(row.get("foil"))
            and (w.get("list") or trade.MAIN_WISH) == row["list"])


def friends_hit(card):
    """[{"name", "lists": []}] of friends whose shared wishlist (their file on this PC, open game) wants this card."""
    try:
        folder = trade.friends_folder(_game())
    except ValueError:
        return []
    names = []
    try:
        files = sorted(folder.glob("*.json"))
    except OSError:
        return []
    for f in files:
        d = _parsed(f, lambda d: {"name": d.get("name") or tr("Friend"),
                                   "wants": [w for w in d.get("wants") or [] if isinstance(w, list) and w]})
        if not d:
            continue
        for w in d["wants"]:
            if _matches(w[0], w[2] if len(w) > 2 else "", w[3] if len(w) > 3 else "", card):
                if d["name"] not in names:
                    names.append(d["name"])
                break
    here = {str(f) for f in files}
    for k in [k for k in _cache if pathlib.Path(k).parent == folder and k not in here]:
        del _cache[k]                                      # a friend gone: nothing of their file is kept
    return [{"name": n, "lists": []} for n in names]


def hit(card, settings):
    card = card or {}
    out = {"lists": [], "removed": False, "undo": None, "friends": friends_hit(card)}
    if not card.get("name"):
        return out
    items = _parsed(trade.WISH_FILE, lambda d: d.get("items", [])) or []
    lists = _wish_lists()
    ids = {lid for lid, _, _ in lists}
    best = {}   # list -> the wish to lower (exact print first)
    for w in items:
        lid = w.get("list") or trade.MAIN_WISH
        if lid not in ids or not _matches(w.get("name"), w.get("set"), w.get("number"), card):
            continue
        if lid not in best or (w.get("set") and not best[lid].get("set")):
            best[lid] = w
    if not best:
        return out
    out["lists"] = [{"id": lid, "name": name, "n": int(best[lid].get("count", 1) or 1), "removed": False}
                    for lid, name, _ in lists if lid in best]
    removing = {lid for lid, _, on in lists if on and lid in best}
    if not removing:
        return out
    raw = trade.wishes(raw=True)                           # fresh from disk – this is what gets written
    rows = []
    for lid, w in best.items():
        if lid not in removing:
            continue
        key = {"list": lid, "name": w.get("name"), "set": w.get("set") or None, "number": w.get("number") or None,
               "lang": w.get("lang") or None, "foil": bool(w.get("foil"))}
        me = next((x for x in raw if _same(x, key)), None)
        if me is None:
            continue
        n = int(me.get("count", 1) or 1)
        if n > 1:
            me["count"] = n - 1
            rows.append(dict(key, n=1, fields=None))
        else:
            raw.remove(me)
            rows.append(dict(key, n=1, fields=dict(me)))
    if not rows:
        return out
    trade.save_wishes(raw)
    done = {r["list"] for r in rows}
    for x in out["lists"]:
        x["removed"] = x["id"] in done
    out["removed"] = True
    out["undo"] = {"v": 1, "game": _game(), "rows": rows}
    return out


def undo(token, list_id=None):
    """Put back exactly what hit() removed – added to today's state, not the old state written back. list_id: only
    that list (the "Details" overlay, lead 14.11.); None: all lists not put back yet. The token remembers which
    lists are done ("done"), so the same list is never added twice."""
    if not isinstance(token, dict) or token.get("v") != 1 or token.get("game") != _game():
        return 0
    ids = {lid for lid, _, _ in _wish_lists()}
    done = token.setdefault("done", [])
    raw = trade.wishes(raw=True)
    n = 0
    for row in token.get("rows") or []:
        if row.get("list") in done or (list_id is not None and row.get("list") != list_id):
            continue
        done.append(row.get("list"))                       # tried once: never again (also when nothing came back)
        if row.get("list") not in ids:
            continue                                       # the list was deleted meanwhile: not brought back
        me = next((x for x in raw if _same(x, row)), None)
        if me is not None:
            me["count"] = int(me.get("count", 1) or 1) + int(row.get("n") or 1)
        elif row.get("fields"):
            raw.append(dict(row["fields"]))
        else:
            continue   # only lowered, then deleted by hand meanwhile: that change stays (Gordon 14.11.)
        n += 1
    if n:
        trade.save_wishes(raw)
    return n
