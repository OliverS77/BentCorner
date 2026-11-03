"""Scan page tiles (Qt Quick): the scan (log + its cards in one tile), the last and the biggest hit, the status line
and the stats as tiles over the camera image.

Tiles sit in a grid between the nav bar and the bottom bar (COLS × ROWS cells), can be moved and resized in grid
steps (positions per tile in settings["scan_tiles"]). The tile drawer (dock key, or the key on every tile) hides and
shows them ("shown"); a hidden tile takes no room in the grid. The page is the stream: the bars and the tiles' keys
go after a few seconds without the mouse (Oliver's review .101 c3 – no separate stream view any more); the studio is
its own mode (qstudio.py).

Data come from the session (scanner/core.py: snapshot() at every change, cards_view() when rev changes); the tiles
edit it in place (setSessionField: name, paid, packs planned, tags) – no edit mode, no save button."""
import time

from PySide6 import QtCore

from scanner.common import BASE
from system.i18n import tr
from ui.scanlook import eur

COLS, ROWS = 16, 13
KEYS = ("status", "session", "hit", "top", "stats")   # "session" = the scan tile (log + cards, one tile since .102)
# where the tiles sit at first (column, row, width, height in cells) and whether they're shown at all (the stats only
# when picked in the tile drawer)
DEFAULT = {"status": {"c": 6, "r": 0, "w": 4, "h": 1, "shown": True},
           "session": {"c": 0, "r": 0, "w": 4, "h": 12, "shown": True},
           "hit": {"c": 12, "r": 0, "w": 4, "h": 5, "shown": True},
           "top": {"c": 12, "r": 6, "w": 4, "h": 5, "shown": True},
           "stats": {"c": 5, "r": 3, "w": 6, "h": 7, "shown": False}}
# smallest width, height in cells – only the floor: the page keeps each tile at least as big as its content needs
# for its purpose (pixels, ScanTiles.qml lim – it depends on the window size) and raises a smaller stored size (fit)
MIN = {"status": (2, 1), "session": (3, 3), "hit": (2, 1), "top": (2, 1), "stats": (3, 2)}
CARDS_MAX = 60   # the list shows at most this many (the tile scrolls; the Logs tab has all of them)
SECTIONS = {"set": False}   # the scan tile's parts that fold: open (True) or folded


def scan_title():
    """"SCAN° – Pokémon": the brand and the open game (its display name) – the scan tile, the status tile and a new
    log's name."""
    import games
    key = games.current().key
    return "SCAN° – " + {"lorcana": "Disney Lorcana"}.get(key, games.nick_of(key))


UNDO_S = 15      # "Scan ended · Undo" stays this long


def _overlaps(a, b):
    return a["c"] < b["c"] + b["w"] and b["c"] < a["c"] + a["w"] and a["r"] < b["r"] + b["h"] and b["r"] < a["r"] + a["h"]


def layout_of(settings):
    """The saved layout, completed and clamped to the grid (old or broken entries fall back to the default)."""
    saved = settings.get("scan_tiles") if isinstance(settings.get("scan_tiles"), dict) else {}
    out, new = {}, []
    for k in KEYS:
        t = dict(DEFAULT[k])
        s = saved.get(k) if isinstance(saved.get(k), dict) else {}
        if saved and not s:
            new.append(k)
        for f in ("c", "r", "w", "h"):
            if isinstance(s.get(f), int):
                t[f] = s[f]
        if isinstance(s.get("shown"), bool):
            t["shown"] = s["shown"]
        mw, mh = MIN[k]
        t["w"] = max(mw, min(COLS, t["w"]))
        t["h"] = max(mh, min(ROWS, t["h"]))
        t["c"] = max(0, min(COLS - t["w"], t["c"]))
        t["r"] = max(0, min(ROWS - t["h"], t["r"]))
        out[k] = t
    # a tile that came with an update (the biggest hit): into a free place of the own layout – else in the drawer
    for i, k in enumerate(new):
        if out[k]["shown"]:   # the other new ones not placed yet take no room
            lay = dict(out, **{n: dict(out[n], shown=False) for n in new[i + 1:]})
            spot = find_spot(lay, k, out[k]["w"], out[k]["h"])
            out[k] = dict(out[k], c=spot[0], r=spot[1]) if spot else dict(out[k], shown=False)
    return out


def place(layout, key, c, r, w, h):
    """Move/resize one tile -> the new layout, or None when it would leave the grid or cover another (shown) tile."""
    mw, mh = MIN[key]
    if w < mw or h < mh or c < 0 or r < 0 or c + w > COLS or r + h > ROWS:
        return None
    new = dict(layout[key], c=c, r=r, w=w, h=h)
    if new.get("shown", True) and any(_overlaps(new, t) for k, t in layout.items() if k != key and t.get("shown", True)):
        return None
    return dict(layout, **{key: new})


def find_spot(layout, key, w, h):
    """A free place for this tile at this size -> (c, r), nearest to where it is stored; None when nothing is free."""
    t = layout[key]
    spots = [(c, r) for r in range(ROWS - h + 1) for c in range(COLS - w + 1)]
    spots.sort(key=lambda p: abs(p[0] - t["c"]) + abs(p[1] - t["r"]))
    for c, r in spots:
        if place(layout, key, c, r, w, h) is not None:
            return c, r
    return None


def fit(layout, key, min_w, min_h):
    """A stored size below what the content needs (older layouts, a larger window before): raised to it – in place
    when there is room, else at the nearest free place -> the new layout, or None when nothing changes or fits."""
    t = layout[key]
    w, h = max(t["w"], min(COLS, min_w)), max(t["h"], min(ROWS, min_h))
    if (w, h) == (t["w"], t["h"]):
        return None
    c, r = min(t["c"], COLS - w), min(t["r"], ROWS - h)
    new = place(layout, key, c, r, w, h)
    if new is None:
        spot = find_spot(layout, key, w, h)
        new = place(layout, key, spot[0], spot[1], w, h) if spot else None
    return new


def shown_at(layout, key, on, min_w, min_h):
    """The tile drawer: hide a tile, or show it again – where it was, else at the nearest free place, else at its
    smallest size -> the new layout, or None when there is no room for it."""
    t = layout[key]
    if not on:
        return dict(layout, **{key: dict(t, shown=False)})
    lay = dict(layout, **{key: dict(t, shown=True)})
    for w, h in ((t["w"], t["h"]), (max(MIN[key][0], min_w), max(MIN[key][1], min_h))):
        w, h = min(COLS, w), min(ROWS, h)
        new = place(lay, key, min(t["c"], COLS - w), min(t["r"], ROWS - h), w, h)
        if new is not None:
            return new
        spot = find_spot(lay, key, w, h)
        if spot:
            return place(lay, key, spot[0], spot[1], w, h)
    return None


def money(text):
    """'32,50 €' / '32.5' / '' -> 32.5 / 0.0; None when it isn't a number."""
    t = str(text or "").replace("€", "").replace(" ", "").strip()
    if not t:
        return 0.0
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return None
    return round(v, 2) if v >= 0 else None


def _img(e):
    p = BASE / e["img"] if e.get("img") else None
    return QtCore.QUrl.fromLocalFile(str(p)).toString() if p and p.exists() else ""


def _cond(e):
    try:
        from cards import conditions
        return conditions.short(e) if e.get("cond") else ""
    except Exception:   # an unknown condition never breaks the list
        return e.get("cond") or ""


def _finish(e):
    """The copy's finish as the game knows it (cards/finishes.py): its word, the special part for the list ("" for the
    plain one) and how many the printing has – never "Normal" for a print that has no Normal (Pokémon holo-only)."""
    try:
        from cards import finishes
        return tr(finishes.option(e)["label"]), tr(finishes.full_label(e)), len(finishes.options(e))
    except Exception:   # an unknown game/printing never breaks the list
        return (tr("Foil"), tr("Foil"), 2) if e.get("foil") else (tr("Normal"), "", 2)


def card_row(e):
    """One card for QML: name, set · number · condition · finish/language, price, image."""
    lang = (e.get("lang") or "en").upper()
    bits = [(e.get("set") or "").upper(), str(e.get("number") or "")]
    cond = _cond(e)
    if cond:
        bits.append(cond)
    finish, fancy, n_fin = _finish(e)
    if fancy:
        bits.append(fancy)
    if lang != "EN":
        bits.append(lang)
    price = e.get("price")
    return {"name": e.get("name") or "", "sub": " · ".join(b for b in bits if b), "price": eur(price) if price is not None else "–",
            "priceShort": f"{price:.2f}".replace(".", ",") if price is not None else "–",
            "img": _img(e), "pack": int(e.get("pack") or 1), "idx": int(e.get("idx") or 0),
            "set": (e.get("set") or "").upper(), "setName": e.get("set_name") or "", "number": str(e.get("number") or ""),
            "cond": cond, "foil": bool(e.get("foil")), "lang": lang,
            "finish": finish, "fancy": fancy, "finishes": n_fin}


def pack_list(view, current):
    """Opening boosters: the scan's cards per pack, newest pack first -> [{n, cards, total, rows}]. The pack being
    opened is always there (also while still empty); empty older packs are left out."""
    out = []
    for e in view:   # cards_view: newest first, so the packs come newest first too
        n = int(e.get("pack") or 1)
        if not out or out[-1]["n"] != n:
            out.append({"n": n, "cards": 0, "sum": 0.0, "rows": []})
        out[-1]["cards"] += 1
        out[-1]["sum"] += e.get("price") or 0.0
        out[-1]["rows"].append(card_row(e))
    if not any(p["n"] == current for p in out):
        out.insert(0, {"n": current, "cards": 0, "sum": 0.0, "rows": []})
    for p in out:
        p["total"] = eur(p.pop("sum"))
    return out


# ---------- the filtered scan's sets (session.info["sets"]: [{code, name}], code "" = free text, shown only) ----------
def set_key(s):
    return s.get("code") or s["name"]


def set_roots(catalog):
    """code -> the code of its whole set (the set itself, or the set it belongs to: Commander, tokens, promos …)."""
    by_code = {s["code"]: s for s in catalog}
    out = {}
    for s in catalog:
        cur, seen = s, set()
        while cur.get("parent") and cur["parent"] in by_code and cur["code"] not in seen:
            seen.add(cur["code"])
            cur = by_code[cur["parent"]]
        out[s["code"]] = cur["code"]
    return out


def _group_key(s, roots):
    return roots.get(s["code"], s["code"]) if s.get("code") else s["name"]


def set_family(code, catalog):
    """A whole set: the set and all its parts (Commander, tokens, promos …) -> [{code, name}], the set first."""
    roots = set_roots(catalog)
    root = roots.get(code, code)
    fam = [{"code": s["code"], "name": s["name"]} for s in catalog if roots.get(s["code"]) == root]
    fam.sort(key=lambda s: s["code"] != root)
    return fam or [{"code": code, "name": code.upper()}]


def set_groups(sets, catalog):
    """The chosen sets as whole sets for the tile: [{key, label, name, n}] – n = how many parts are in it."""
    roots, by_code = set_roots(catalog), {s["code"]: s for s in catalog}
    out, at = [], {}
    for s in sets:
        key = _group_key(s, roots)
        if key in at:
            out[at[key]]["n"] += 1
            continue
        at[key] = len(out)
        name = by_code[key]["name"] if key in by_code else s["name"]
        out.append({"key": key, "label": key.upper() if s.get("code") else s["name"], "name": name, "n": 1})
    return out


def sets_without(sets, key, catalog):
    """The list without one whole set (key from set_groups)."""
    roots = set_roots(catalog)
    return [s for s in sets if _group_key(s, roots) != key]


def sets_flipped(sets, entry, catalog):
    """The menu's click: a whole set in -> out (with all its parts), out -> in; free text as it stands."""
    if not entry.get("code"):
        return sets_toggled(sets, entry)
    roots = set_roots(catalog)
    if roots.get(entry["code"], entry["code"]) in {_group_key(s, roots) for s in sets}:
        return sets_without(sets, roots.get(entry["code"], entry["code"]), catalog)
    have = {s.get("code") for s in sets}
    return list(sets) + [s for s in set_family(entry["code"], catalog) if s["code"] not in have]


def sets_toggled(sets, entry):
    """The list with entry ({code, name}) switched: in -> out, out -> in (at the end)."""
    key = set_key(entry)
    if any(set_key(s) == key for s in sets):
        return [s for s in sets if set_key(s) != key]
    if not entry.get("code") and entry["name"].lower() in {s["name"].lower() for s in sets}:
        return list(sets)
    return list(sets) + [{"code": entry.get("code") or "", "name": entry["name"]}]


def sets_summary(sets):
    """What the session window shows: one set by name, several by code (free text by name)."""
    if len(sets) == 1:
        return sets[0]["name"]
    return " · ".join(s["code"].upper() if s.get("code") else s["name"] for s in sets)


def pick_sets(ctrl, on_change=None):
    """The light menu with every whole set (chosen ones first and lit, then the newest): a click switches the set with
    all its parts (Commander, tokens, promos … – Oliver's review c6), typing filters, a text that matches nothing is
    taken as it stands (e.g. "Final Fantasy"). Every switch is saved right away (the scanner reads the codes at each
    scan and preloads their images)."""
    from ui import qdialogs
    sess = ctrl.session
    catalog = list(ctrl.catalog_sets)
    roots, by_code = set_roots(catalog), {s["code"]: s for s in catalog}
    chosen = set_groups(list(sess.info.get("sets") or []), catalog)
    have = {g["key"] for g in chosen}
    heads = sorted((s for s in catalog if roots.get(s["code"]) == s["code"]),
                   key=lambda s: s.get("released") or "", reverse=True)
    entries = [{"code": g["key"], "name": g["name"]} if g["key"] in by_code else {"code": "", "name": g["name"]}
               for g in chosen]
    entries += [{"code": s["code"], "name": s["name"]} for s in heads if s["code"] not in have]
    items = [{"text": f"{e['code'].upper()}  {e['name']}" if e.get("code") else e["name"], "checkable": True,
              "on": set_key(e) in have} for e in entries]

    def flip(i):
        sess.set_info(sets=sets_flipped(list(sess.info.get("sets") or []), entries[i], catalog))
        if on_change:
            on_change()

    def text(t):
        t = (t or "").strip()
        if t:
            entries.append({"code": "", "name": t})
            flip(len(entries) - 1)
    return qdialogs.menu(tr("Only these sets"), items, flip, multi=True, on_text=text,
                         on_close=lambda _r: on_change and on_change())


def scan_lang_name(code):
    """The log's language for the scan tile: "Deutsch", "" = all languages."""
    from collection.collection import ALL_LANGS
    return next((name for c, _short, name in ALL_LANGS if c == code), "") if code else ""


class TilesBackend(QtCore.QObject):
    layoutChanged = QtCore.Signal()
    sessionChanged = QtCore.Signal()
    cardsChanged = QtCore.Signal()
    viewChanged = QtCore.Signal()   # the scan tile's folded parts, the tiles hint
    logPing = QtCore.Signal()   # "where are the log settings?" (Stats, older paths): the scan tile lights up briefly

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self._layout = layout_of(ctrl.settings)
        self._rev = None
        self._session = {}
        self._cards = []
        self._packs = []   # opening boosters: the list per pack (pack_list)
        self._ended = None   # "Scan ended · Undo": {"name", "until"} while it can be taken back
        self._removed = None   # "… removed · Undo": the card, its place and until when
        self._auto = (None, "")   # (session id, "Scan N")
        self._t = QtCore.QTimer(self, interval=200, timeout=self._poll)   # session changes (rev) – cheap: one int compare

    # ---------- active only while the scan page is shown ----------
    @QtCore.Slot(bool)
    def setActive(self, on):
        if on:
            self._poll()
            self._t.start()
        else:
            self._t.stop()

    def _poll(self):
        snap = getattr(self.ctrl, "snap", None) or {}
        sess = self.ctrl.session
        load = getattr(self.ctrl, "filtered_load", None)
        if self._ended and (time.time() > self._ended["until"] or sess.to_dict()["stats"]["cards"]):
            self._ended = None   # too late / the next log has begun: no undo any more
            self._rev = None
        if self._removed and time.time() > self._removed["until"]:
            self._removed = None
            self._rev = None
        key = (snap.get("rev"), sess.active, id(sess), load and (load["step"], load["done"]), bool(self._ended),
               bool(self._removed))
        if key == self._rev:
            return
        self._rev = key
        self._session = self._build_session(snap)
        view = sess.cards_view()
        self._cards = [card_row(e) for e in view[:CARDS_MAX]]
        self._packs = pack_list(view, int(snap.get("pack_number") or 1)) if snap.get("kind") == "packs" else []
        self.sessionChanged.emit()
        self.cardsChanged.emit()

    def _build_session(self, snap):
        sess = self.ctrl.session
        info = snap.get("info") or {}
        st = snap.get("stats") or {}
        paid = float(info.get("paid") or 0)
        profit = st.get("profit")
        kind = snap.get("kind") or "cards"
        started = getattr(sess, "started", None)
        since = time.strftime("%H:%M", time.localtime(started)) if started else ""
        meta = []
        if since and sess.active:
            meta.append(tr("since {t}").format(t=since))
        if st.get("cards"):
            meta.append(tr("{n} cards").format(n=int(st["cards"])))
        sets = [{"code": s.get("code") or "", "name": s["name"]} for s in (info.get("sets") or [])]
        return {"active": bool(sess.active), "kind": kind, "packsShown": bool(snap.get("packs_shown")),
                "canCards": bool(snap.get("can_cards", True)),
                "packTypeKey": snap.get("pack_type") or info.get("pack_type") or "",
                "sets": set_groups(sets, list(getattr(self.ctrl, "catalog_sets", None) or [])),
                "setsLoad": self._sets_load(),
                "ended": dict(self._ended) if self._ended else {},
                "removed": self._removed["name"] if self._removed else "",
                "notes": info.get("notes") or "", "autoName": self._auto_name(), "scanTitle": scan_title(),
                "name": info.get("title") or "", "meta": " · ".join(m for m in meta if m),
                "cards": int(st.get("cards") or 0), "value": eur(st.get("total") or 0.0),
                "paid": eur(paid) if paid else "", "balance": eur(profit) if profit is not None else "",
                "balanceNeg": profit is not None and profit < 0,
                "packNumber": int(snap.get("pack_number") or 1), "packsPlanned": int(info.get("packs_planned") or 0),
                "packTotal": eur(snap.get("pack_total") or 0.0), "packCards": len(snap.get("pack") or []),
                "packType": self._pack_type_name(snap.get("pack_type") or ""), "tags": " · ".join(info.get("tags") or []),
                "scanLang": scan_lang_name(info.get("scan_lang"))}

    def _auto_name(self):
        """A log without a name: "SCAN° – Pokémon" (the brand and the game; the line below says since when). Saved
        with the start time (endSession) – logs already saved keep their names."""
        return scan_title()

    def _sets_load(self):
        """The filtered scan loading its sets (scan_ctl.preload_filtered_sets): what, how far -> {} when done."""
        load = getattr(self.ctrl, "filtered_load", None)
        if not load:
            return {}
        what = {"memory": tr("Loading your sets …"), "features": tr("Preparing your sets for SCAN°"),
                "images": tr("Downloading missing pictures of your sets")}.get(load["step"], "")
        total = max(1, int(load["total"] or 0))
        return {"text": what, "count": f"{int(load['done'])} / {total}" if load["total"] else "",
                "frac": min(1.0, float(load["done"]) / total) if load["total"] else 0.0}

    def _pack_type_name(self, key):
        try:
            from cards import packtypes
            return next((tr(t["name"]) for t in packtypes.types(self.ctrl.settings) if t["key"] == key), key)
        except Exception:   # a missing type list never breaks the tile
            return key

    # ---------- data for the tiles ----------
    @QtCore.Property("QVariantMap", notify=sessionChanged)
    def session(self):
        return self._session

    @QtCore.Property("QVariantList", notify=cardsChanged)
    def cards(self):
        return self._cards

    @QtCore.Property("QVariantList", notify=cardsChanged)
    def packs(self):
        return self._packs

    @QtCore.Property("QVariantMap", notify=cardsChanged)
    def hit(self):
        """The last counted card (the newest of the session)."""
        if not self._cards:
            return {}
        h = dict(self._cards[0])
        e = self.ctrl.session.cards_view()[:1]
        price = e[0].get("price") if e else None
        h["isHit"] = price is not None and price >= float(self.ctrl.settings.get("hit") or 0.5)
        h["key"] = f"{h['pack']}:{h['idx']}:{h['name']}"
        top = ((getattr(self.ctrl, "snap", None) or {}).get("stats") or {}).get("biggest_hit") or {}
        h["isTop"] = bool(e) and top.get("added") is not None and top.get("added") == e[0].get("added")
        return h

    @QtCore.Property("QVariantMap", notify=cardsChanged)
    def top(self):
        """The biggest hit of the log: its most valuable card."""
        snap = getattr(self.ctrl, "snap", None) or {}
        e = (snap.get("stats") or {}).get("biggest_hit")
        if not e or e.get("price") is None:
            return {}
        h = card_row(e)
        h["isHit"] = True
        h["key"] = f"{e.get('id')}:{e.get('added')}"
        return h

    # ---------- the scan tile's view: folded parts, the tiles hint ----------
    @QtCore.Property("QVariantMap", notify=viewChanged)
    def view(self):
        s = self.ctrl.settings
        secs = dict(SECTIONS, **{k: v for k, v in (s.get("scan_sections") or {}).items() if k in SECTIONS})
        return {"sections": secs, "tilesHint": not s.get("scan_tiles_hint")}

    @QtCore.Slot(str, bool)
    def setSection(self, key, on):
        if key in SECTIONS:
            self.ctrl.settings["scan_sections"] = dict(self.ctrl.settings.get("scan_sections") or {}, **{key: bool(on)})
            self.ctrl.settings_changed()
            self.viewChanged.emit()

    @QtCore.Slot()
    def tilesHintSeen(self):
        """The tile drawer's first opening explained the tiles once: not again."""
        if not self.ctrl.settings.get("scan_tiles_hint"):
            self.ctrl.settings["scan_tiles_hint"] = True
            self.ctrl.settings_changed()
            self.viewChanged.emit()

    # ---------- inline editing (Enter / leaving the field saves) ----------
    @QtCore.Slot(str, str, result=bool)
    def setSessionField(self, field, value):
        sess = self.ctrl.session
        if field == "title":
            sess.set_info(title=value.strip())
        elif field == "paid":
            v = money(value)
            if v is None:
                return False
            sess.set_info(paid=v)
        elif field == "packs_planned":
            try:
                sess.set_info(packs_planned=max(0, int(value.strip() or 0)))
            except ValueError:
                return False
        elif field == "tags":
            sess.set_info(tags=[t.strip() for t in value.replace("·", ",").split(",") if t.strip()])
        elif field == "notes":
            sess.set_info(notes=value.strip())
        else:
            return False
        self._poll()
        return True

    @QtCore.Slot(str, result=bool)
    def setKind(self, kind):
        ok = bool(self.ctrl.set_session_kind(kind))
        self._poll()
        return ok

    @QtCore.Slot()
    def endSession(self):
        """"End scan": right away, no question – in the tile for a moment (UNDO_S) "✓ Saved in Logs – name · 22 cards
        · 137,18 €" with Open (that log in Logs) and Undo; nothing scanned: no log, a short note instead."""
        sess = self.ctrl.session
        st = sess.to_dict()["stats"]
        sid, n = sess.id, int(st.get("cards") or 0)
        # a trade log with cards given away: they leave the collection and it can't be undone – asked first
        # (03.11.; the only question before "End scan", it can't be taken back)
        from scanner import core
        from ui import qdialogs
        note = core.trade_end_text(getattr(sess, "info", {}), getattr(sess, "packs", None) or [])
        if note and qdialogs.ask(tr("End log"), note, [("no", tr("Cancel"), ""), ("yes", tr("Confirm"), "active")]) != "yes":
            return
        # without a name: "SCAN° – Pokémon 12:13" (the start time) – several logs of one day stay apart in Logs
        name = (sess.info.get("title") or "").strip() or (
            f"{self._auto_name()} {time.strftime('%H:%M', time.localtime(sess.started))}")
        undo = self.ctrl.end_session_now(name)
        if not n:
            self._ended = {"text": tr("Nothing scanned – no log saved"), "detail": "", "id": "", "undo": False,
                           "until": time.time() + 4}
        else:
            cards = tr("1 card") if n == 1 else tr(f"{n} cards")
            self._ended = {"text": tr("Saved in Logs"), "detail": f"{name} · {cards} · {eur(st.get('total') or 0.0)}",
                           "id": sid, "undo": bool(undo), "until": time.time() + UNDO_S}
        self._rev = None
        self._poll()

    @QtCore.Slot()
    def openEnded(self):
        """"Open" in the note after "End scan": Logs & stats with exactly that log."""
        sid = (self._ended or {}).get("id")
        if sid:
            import games
            self.ctrl.show_trade_session(games.current().key, sid)

    @QtCore.Slot()
    def undoEnd(self):
        self._ended = None
        self.ctrl.undo_end_session()
        self._rev = None
        self._poll()

    @QtCore.Slot(str)
    def searchCard(self, text):
        """The scan tile's search field: the card search opens (with what was typed)."""
        panel = self.ctrl.stream.card_panel
        if panel.isHidden() and not self.ctrl.overlay.panel_open:
            self.ctrl.add_card()
        if text.strip():
            panel.set_search(text.strip())

    @QtCore.Slot(str)
    def removeSet(self, key):
        """The ✕ on a set of the filtered scan: the whole set out."""
        sess = self.ctrl.session
        sess.set_info(sets=sets_without(list(sess.info.get("sets") or []), key, list(self.ctrl.catalog_sets)))
        self.ctrl.save_session()
        self._rev = None
        self._poll()

    @QtCore.Slot(int, int)
    def editCard(self, pack, idx):
        """A click on a card of the list: the card window to edit it (condition, finish, language, print …)."""
        if pack > 0:
            self.ctrl.stream.open_edit(idx, pack - 1)

    @QtCore.Slot(int, int)
    def removeCard(self, pack, idx):
        """The row's ✕: out of the scan right away – "Undo" in the tile for a moment (no question)."""
        sess = self.ctrl.session
        if pack <= 0:
            return
        with sess.lock:
            cards = sess.packs[pack - 1]["cards"] if pack <= len(sess.packs) else []
            e = cards[idx] if 0 <= idx < len(cards) else None
        if e is None:
            return
        self.ctrl.removed_soon(e)
        sess.undo(idx, p=pack - 1)
        self._removed = {"entry": e, "pack": pack - 1, "idx": idx, "name": e.get("name") or "",
                         "until": time.time() + UNDO_S}
        self.hoverCard(0, 0)
        self._rev = None
        self._poll()

    @QtCore.Slot()
    def undoRemove(self):
        r, self._removed = self._removed, None
        if r is not None:
            self.ctrl.session.put_back(r["entry"], r["idx"], r["pack"])
        self._rev = None
        self._poll()

    @QtCore.Slot(int, int)
    def cardCond(self, pack, idx):
        """The row's condition key: the next grade (NM → EX → … on the user's scale)."""
        if pack > 0:
            self.ctrl.session.toggle_cond(idx, p=pack - 1)
            self._rev = None
            self._poll()

    @QtCore.Slot(int, int)
    def cardFoil(self, pack, idx):
        """The row's finish key: the printing's next finish (Magic normal ↔ foil, Pokémon normal → holo → …)."""
        if pack > 0:
            self.ctrl.session.toggle_foil(idx, p=pack - 1)
            self._rev = None
            self._poll()

    _over = None   # (pack, idx) the big preview shows

    @QtCore.Slot(int, int)
    def hoverCard(self, pack, idx):
        """Mouse over a card of the list: the big preview (the page's top layer) shows it; pack 0 = none."""
        e = None
        if pack > 0:
            with self.ctrl.session.lock:
                packs = self.ctrl.session.packs
                if pack <= len(packs) and 0 <= idx < len(packs[pack - 1]["cards"]):
                    e = packs[pack - 1]["cards"][idx]
        self._over = (pack, idx) if e is not None else None
        self.ctrl.overlay.panel_hover, self.ctrl.overlay.hover_list = e, e is not None

    @QtCore.Slot(int, int)
    def unhoverCard(self, pack, idx):
        """The mouse leaves a card. Moving down the list, the next row reports "in" BEFORE this one reports "out" –
        only clear when the preview still belongs to this card."""
        if self._over == (pack, idx):
            self.hoverCard(0, 0)

    @QtCore.Slot()
    def pickPackType(self):
        """The pack type (opening boosters) / what it is (single cards): a menu where the click was; "Types …" edits
        the list."""
        from cards import packtypes
        from ui import qdialogs
        ctrl = self.ctrl
        types = packtypes.types(ctrl.settings)
        cur = self._session.get("packTypeKey") or ""
        items = [{"text": tr(t["name"]), "checkable": True, "on": t["key"] == cur} for t in types]
        items += [{"sep": True}, {"text": tr("Types …")}]

        def pick(i):
            if i < len(types):
                ctrl.session.set_pack_type(types[i]["key"])
                ctrl.save_session()
            elif i == len(types) + 1:
                ctrl.edit_pack_types()
            self._rev = None
            self._poll()
        qdialogs.menu(tr("Pack type"), items, pick)

    @QtCore.Slot()
    def pickScanLang(self):
        """The language of this log (Oliver 2026-11-01: per scan round, for every game, not the library): new cards
        come in it, and when SCAN° can't read the language clearly it takes this one instead of asking – a language it
        reads clearly still wins. A menu where the click was, with the languages of the active game."""
        from collection.collection import LANGS   # the languages the active game has
        from ui import qdialogs
        ctrl = self.ctrl
        cur = ctrl.session.info.get("scan_lang") or ""
        codes = [""] + [c for c, _s, _n in LANGS]
        items = [{"text": tr("All languages"), "checkable": True, "on": cur == ""}, {"sep": True}]
        items += [{"text": name, "checkable": True, "on": c == cur} for c, _s, name in LANGS]

        def pick(i):
            i = 0 if i == 0 else i - 1   # the line after "All languages"
            if 0 <= i < len(codes):
                ctrl.session.set_info(scan_lang=codes[i] or None)
                ctrl.save_session()
            self._rev = None
            self._poll()
        qdialogs.menu(tr("Language"), items, pick)

    @QtCore.Slot()
    def pickSets(self):
        """Preferred sets: the menu with every set (chosen ones lit), a click switches."""
        def changed():
            self._rev = None
            self._poll()
        pick_sets(self.ctrl, changed)

    def ping(self):
        """ctrl.stream.open_info (Stats "Log", older paths): the settings live in the log tile – it lights up."""
        self.logPing.emit()

    @QtCore.Slot()
    def newPack(self):
        self.ctrl.new_pack()
        self._poll()

    # ---------- the grid ----------
    @QtCore.Property("QVariantMap", notify=layoutChanged)
    def layout(self):
        return self._layout

    @QtCore.Property("QVariantMap", constant=True)
    def grid(self):
        return {"cols": COLS, "rows": ROWS, "min": {k: {"w": w, "h": h} for k, (w, h) in MIN.items()}}

    @QtCore.Slot(str, int, int, int, int, result=bool)
    def setTile(self, key, c, r, w, h):
        """Drop after moving/resizing -> False (and the tile goes back) when it doesn't fit there."""
        new = place(self._layout, key, c, r, w, h) if key in self._layout else None
        if new is None:
            self.layoutChanged.emit()   # QML snaps back to the stored place
            return False
        self._layout = new
        self._save()
        return True

    @QtCore.Slot(str, int, int)
    def fitTile(self, key, min_w, min_h):
        """The page knows what a tile's content needs (it depends on the window size): a smaller stored size grows."""
        new = fit(self._layout, key, min_w, min_h) if key in self._layout else None
        if new is not None:
            self._layout = new
            self._save()

    @QtCore.Slot(str, bool, int, int, result=bool)
    def setTileShown(self, key, on, min_w, min_h):
        """Tile drawer: hide / show a tile -> False when there is no room left for it (it stays hidden)."""
        new = shown_at(self._layout, key, on, min_w, min_h) if key in self._layout else None
        if new is None:
            self.layoutChanged.emit()
            self.ctrl.stream_toast(tr("No room for this tile – make another one smaller or hide it"))
            return False
        self._layout = new
        self._save()
        return True

    @QtCore.Slot()
    def resetLayout(self):
        self._layout = layout_of({})
        self._save()

    def _save(self):
        self.ctrl.settings["scan_tiles"] = {k: dict(v) for k, v in self._layout.items()}
        self.ctrl.settings_changed()
        self.layoutChanged.emit()
