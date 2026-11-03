"""Trade in Qt Quick (qml/pages/TradePage.qml).

The logic lives in tradeview.TradePage: friends, lists, suggestions, import, offer as an image. This object
passes its state on to QML and forwards clicks to it. The library views in the trade page (list editor, "Wants",
"Has", "Library of …") run through qlibrary.LibraryBackend – the same view as the library. The two
columns in the "Swap" tab (tradelib.Browser) are passed on by BrowserBackend.
"""
from PySide6 import QtCore

from cards import carddb
from cards import library
from ui import quickimages
from collection import trade
from system import userprofile
from system.i18n import tr
from ui.librarycore import THUMBS, _esc
from ui.qlibrary import LibraryBackend, back_image
from collection.tradelib import LANG_SHORT, eur


def _wrap(obj, name, after):
    orig = getattr(obj, name)

    def fn(*a, **k):
        res = orig(*a, **k)
        after()
        return res
    setattr(obj, name, fn)


def db_image(db, lang="en"):
    """Card image from a row of the card database -> image://cards/…"""
    if not db:
        return ""
    sid = db["id"]
    url = db.get("img_normal") or library.image_url(db["set_code"], db["number"], "en", "normal")
    return quickimages.register(f"{sid}_en_n", THUMBS / f"{sid}_en_n.jpg", url, THUMBS / f"{sid}_en_n.jpg")


def db_image_of(db, game):
    """Card image from the database of any game (other game: image address from that game's database)."""
    import games
    if not db:
        return ""
    if not game or game == games.current().key:
        return db_image(db)
    url = db.get("img_normal")
    if not url and game == "mtg":   # Magic: images come from Scryfall (other games: only what the database has –
        from games import mtg       # their image_url reads the open game's database)
        url = mtg.GAME.image_url(db["set_code"], db["number"])
    if not url:
        return ""
    key = f"{game}_{db['id']}_en_n"
    return quickimages.register(key, THUMBS / f"{key}.jpg", url, THUMBS / f"{key}.jpg")


def games_key():
    import games
    return games.current().key


def has_image(r, game=None):
    """Does the printing have an image? Magic: always (Scryfall), other games: only with an image address in the DB."""
    import games
    return bool(r) and ((game or games.current().key) == "mtg" or bool(r.get("img_normal")))


def plain_detail(det):
    """Detail view outside the library (DetailHost): transitions of the old view off – QML animates itself."""
    if det.morph is not None:
        det.morph.run = lambda apply, *a, then=None, **k: (apply(), then() if then else None)
    if det.slide is not None:
        sl = det.slide
        sl.open_orig, sl.close_orig = sl.open, sl.close
        sl.open = lambda animate=True: sl.open_orig(False)
        sl.close = lambda animate=True: sl.close_orig(False)



def _fin_chip(r):
    """Chip with the finish ("Reverse Holo", "Foil") – empty for the plain one."""
    from cards import finishes
    try:
        lb = finishes.full_label(r) if r.get("id") and r.get("finishes") is not None else ("Foil" if r.get("foil") else "")
    except Exception:  # noqa: BLE001
        lb = "Foil" if r.get("foil") else ""
    return [tr(lb)] if lb else []

class BrowserBackend(QtCore.QObject):
    """One column in the "Swap" tab: cards with search, filter chips, grid/list and checkmarks."""
    changed = QtCore.Signal()

    def __init__(self, browser, parent=None):
        super().__init__(parent)
        self.b = browser
        self._title = ""
        browser.changed.connect(self.changed.emit)

    @QtCore.Property(str, notify=changed)
    def title(self):
        return self._title

    def set_title(self, t):
        self._title = t
        self.changed.emit()

    @QtCore.Property("QVariantList", notify=changed)
    def rows(self):
        out = []
        for i, r in enumerate(self.b.rows):
            extra = f"{r['set']} #{r['number']}"
            if (r.get("lang") or "en") != "en":
                extra += " · " + LANG_SHORT.get(r.get("lang"), str(r.get("lang")).upper())
            if r.get("foil"):
                extra += " · Foil"
            tags = list(r.get("tags") or [])
            if r.get("pinned_name"):
                tags.append(tr("exactly this version") if r.get("pinned_match") else tr("other version"))
            out.append({"i": i, "name": r["name"], "setLine": extra, "count": int(r.get("count") or 1),
                        "price": eur(None if r.get("price") is None else r["price"] * int(r.get("count") or 1)),
                        "img": db_image_of(r.get("db"), r.get("game")), "checked": bool(r.get("checked")),
                        "tags": " · ".join(tags), "chips": [f"{int(r.get('count') or 1)}×"]
                        + _fin_chip(r)})
        return out

    @QtCore.Property(bool, constant=True)
    def checkable(self):
        return bool(self.b.checkable)

    @QtCore.Property(str, notify=changed)
    def mode(self):
        return self.b.mode

    @QtCore.Slot(str)
    def setMode(self, m):
        self.b.set_mode(m)

    @QtCore.Property(str, notify=changed)
    def search(self):
        return self.b.search

    @QtCore.Slot(str)
    def setSearch(self, t):
        self.b.set_search(t)

    @QtCore.Property("QVariantList", notify=changed)
    def filters(self):
        return [{"key": k, "text": label, "on": k in self.b.active, "pin": k == "pin"} for k, label, _ in self.b.filters]

    @QtCore.Slot(str)
    def toggleFilter(self, key):
        self.b._chip(key, key not in self.b.active)

    @QtCore.Property(str, notify=changed)
    def info(self):
        return self.b.info

    @QtCore.Property(str, notify=changed)
    def emptyText(self):
        return self.b.empty

    @QtCore.Slot(int)
    def toggle(self, i):
        rows = self.b.rows
        if 0 <= i < len(rows):
            self.b.toggle(rows[i])

    @QtCore.Slot(bool)
    def checkAll(self, on):
        self.b.check_all(on)

    @QtCore.Slot(int)
    def click(self, i):
        rows = self.b.rows
        if 0 <= i < len(rows):
            self.b.clicked.emit(rows[i])


class TradeBackend(QtCore.QObject):
    changed = QtCore.Signal()      # view, friend, tab
    railChanged = QtCore.Signal()  # left sidebar
    alarmChanged = QtCore.Signal()  # price alert editor in a row, open/closed
    listsChanged = QtCore.Signal()  # "your lists" overview
    entriesChanged = QtCore.Signal()  # list in the editor
    sumChanged = QtCore.Signal()   # calculation in the "Swap" tab
    detailChanged = QtCore.Signal()

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        # the list editor's rows, made once per change: every row of the ListView reads entries[index] – built anew on
        # each read (alerts, sorting, for "price" a database query) scrolling a long list stalled for up to 0.7 s
        # (review .101). Connected first, so the cache is gone before anything reads the new state.
        self._entries = None
        for sig in (self.entriesChanged, self.alarmChanged):
            sig.connect(self._drop_entries)
        ctrl.stream.ensure_page("trade")
        self.page = page = ctrl.trade_page
        # hints at the bottom: in the Qt Quick window instead of the invisible label
        page.toast = lambda text, ms=4500: ctrl.shell.show_toast(text) if getattr(ctrl, "shell", None) else None
        # library views in the trade page
        self.ed_b = LibraryBackend(ctrl, page.ed_lib, "trade_ed_detail_w", main=False)
        self.wants_b = LibraryBackend(ctrl, page.f_wants, "trade_wants_detail_w", main=False)
        self.has_b = LibraryBackend(ctrl, page.f_has, "trade_has_detail_w", main=False)
        self.flib_b = LibraryBackend(ctrl, page.f_lib, "trade_lib_detail_w", main=False)
        for b in (self.ed_b, self.wants_b, self.has_b, self.flib_b):
            b.install_collapse_hook()
        from ui.qtrade_alarms import AlarmsBackend   # the parts import helpers from this module: import here
        from ui.qtrade_friends import FriendsBackend
        from ui.qtrade_lists import ListsBackend
        self.lists_b = ListsBackend(self)   # "your lists" (docs/TRADE-SPLIT.md) – in QML as tradeLists
        self.alarms_b = AlarmsBackend(self)   # "Price alerts" folder and alert editors – in QML as tradeAlarms
        self.friends_b = FriendsBackend(self)   # friends sidebar, a friend's view (all games), sync – tradeFriends
        # "Swap" tab
        self.get_b = BrowserBackend(page.get_browser, self)
        self.give_b = BrowserBackend(page.give_browser, self)
        side = page.trade_side
        plain_detail(side.host)
        from ui.qdetail import DetailBackend
        self.tdet_b = DetailBackend(ctrl, side.host, side.card, self)
        self.tcmp_b = DetailBackend(ctrl, side.host, side.cmp, self)
        aside = page.alarm_side   # detail view in the "Price alerts" folder
        plain_detail(aside.host)
        self.adet_b = DetailBackend(ctrl, aside.host, aside.card, self)
        self.acmp_b = DetailBackend(ctrl, aside.host, aside.cmp, self)
        for name in ("open_detail", "hide_detail", "show_compare", "close_compare", "update_marks"):
            if hasattr(aside.host, name):
                _wrap(aside.host, name, self.detailChanged.emit)
        self._open_alarms = []   # open editors (stay open until you close them yourself)
        self._alarm_opts = {}    # per open editor: src / basis / finish / psid (not saved yet)
        self._alarm_rev = 0
        for name in ("open_detail", "hide_detail", "show_compare", "close_compare", "update_marks"):
            if hasattr(side.host, name):
                _wrap(side.host, name, self.detailChanged.emit)
        # follow the page's state
        page.changed.connect(self.changed.emit)
        page.rail_changed.connect(self.railChanged.emit)
        page.lists_changed.connect(self.listsChanged.emit)
        page.list_panel.changed.connect(self.entriesChanged.emit)
        page.sum_changed.connect(self.sumChanged.emit)
        _wrap(page, "fill_trade", self._trade_titles)
        hc = page.holders_changed

        def holders_changed():
            self._drop_entries()
            hc()
            self.ed_b.holders_changed()
        page.holders_changed = holders_changed

    # ---------- View ----------
    @QtCore.Property(str, notify=changed)
    def view(self):
        return self.page.view

    @QtCore.Property(QtCore.QObject, constant=True)
    def edLib(self):
        return self.ed_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def hasLib(self):
        return self.has_b

    # ---------- Left sidebar ----------
    @QtCore.Property(str, notify=railChanged)
    def current(self):
        return self.page.rail_current or ""

    @QtCore.Property(str, notify=railChanged)
    def currentId(self):
        """The friend being shown (plain ID, from whichever game) – for the highlight in the sidebar."""
        return (self.page.friend_id or "") if self.page.view == "friend" else ""

    @QtCore.Property(str, notify=railChanged)
    def meName(self):
        return userprofile.ensure(self.ctrl.settings).get("name") or tr("You")

    @QtCore.Property(str, notify=railChanged)
    def meBack(self):
        return back_image(userprofile.ensure(self.ctrl.settings).get("back"))

    # ---------- Friends: folders (as in the deck builder) and sorting ----------
    def _folders(self):
        return [""] + [f for f in self.ctrl.settings.get("friend_folders") or [] if f]

    @QtCore.Slot(str)
    def showFolder(self, key):
        """List folder clicked in the sidebar: show your lists, exactly this folder."""
        self.page.open_me()
        self.setFolder(key)

    @QtCore.Slot()
    def openMe(self):
        self.page.open_me()

    @QtCore.Slot()
    def editProfile(self):
        self.ctrl.stream.show_page("profile", back=True)

    # ---------- Bent°Corner Orbit: the quiet line at the top of the page ----------
    @QtCore.Slot(result="QVariantMap")
    def orbitLine(self):
        """{text: "Near Orbit · prices and alerts on, friends off", full: bool} – asked when the page shows."""
        from system import orbit
        return {"text": orbit.describe(self.ctrl.settings), "full": orbit.level(self.ctrl.settings) == "full"}

    @QtCore.Slot()
    def openOrbit(self):
        """"Change ›": the Orbit slider under Settings → Friends & privacy."""
        self.ctrl.stream.show_page("settings", back=True)
        self.ctrl.show_settings("privacy")

    # ---------- Overview: your lists ----------
    @QtCore.Property(str, notify=listsChanged)
    def gameKey(self):
        import games
        return games.current().key

    # ---------- Start page: folders (wishlists, trade lists, own lists, price alerts) with tiles ----------
    FOLDERS = (("wish", "Wunschlisten", "star", "Was du suchst – Freunde sehen das, wenn du es mitschickst."),
               ("have", "Tauschlisten", "trade", "Karten aus deiner Sammlung, die du hergeben würdest."),
               ("custom", "Eigene Listen", "bookmark", "Für alles andere – Binder, Ideen, Karten für ein Projekt. "
                                                       "Immer privat – Freunde sehen sie nicht."),
               ("offers", "Tauschangebote", "ticket", "Angebote und Gegenangebote als Tickets – annehmen, ändern, "
                                                    "ablehnen. Jeder Tausch hat eine Tausch-ID."),
               ("alarms", "Preisalarme", "bell", "Alerts for single cards and whole lists – reported after every "
                                                "price update (in the tray once a day)."),
               ("binders", "Binder", "binder", "Albums for all games: arrange cards freely, leave gaps for what's "
                                               "still missing – friends see what you're missing."))

    def _lib(self):
        return (getattr(self.ctrl, "shell", None) and self.ctrl.shell.backends.get("library")) or None

    @QtCore.Property(str, notify=listsChanged)
    def folder(self):
        f = self.ctrl.settings.get("trade_folder") or "wish"
        return f if f in {k for k, *_ in self.FOLDERS} else "wish"

    @QtCore.Slot(str)
    def setFolder(self, key):
        self.ctrl.settings["trade_folder"] = key
        self.listsChanged.emit()
        shell = getattr(self.ctrl, "shell", None)
        if shell is not None:   # game button: ∞ in the price alerts folder (all games)
            shell.navChanged.emit()

    @QtCore.Property("QVariantList", notify=listsChanged)
    def folders(self):
        from collection import alarms
        out = []
        for key, title, icon, sub in self.FOLDERS:
            if key == "offers":
                from collection import offers
                n = sum(1 for o in offers.load() if o["status"] in offers.OPEN)
            else:
                if key == "binders":
                    pb = self.ctrl.shell.backends.get("profile") if getattr(self.ctrl, "shell", None) else None
                    n = sum(1 for t in (pb.binderTiles if pb is not None else []) if not t.get("new"))
                elif key == "alarms":
                    st = self.ctrl.settings
                    ca, la = alarms.all_alarms(st), alarms.list_alarms(st, every=True)
                    hits = sum(1 for a in ca if a.get("hit")) + sum(1 for a in la if any((a.get("hit") or {}).values()))
                    n = f"{hits}/{len(ca) + len(la)}"
                else:
                    n = len(trade.lists(key))
            out.append({"key": key, "title": tr(title), "icon": icon, "sub": tr(sub), "count": n})
        return out

    @QtCore.Property(str, notify=listsChanged)
    def gameName(self):
        import games
        return games.name_of(games.current().key)

    @QtCore.Property("QVariantList", notify=listsChanged)
    def tiles(self):
        """Tiles of the selected folder: [{lid, name, info, value, art, example, main, alarm, friends}]."""
        from collection import alarms
        kind = self.folder
        if kind in ("alarms", "offers", "binders"):
            return []
        items = self.ctrl.collection.items
        hold = self.page.holders() if kind == "wish" else {}
        out = []
        for x in trade.lists(kind):
            lid = x["id"]
            entries = trade.list_entries(kind, lid, items)
            n = sum(e["count"] for e in entries)
            value, art, artist = self.lists_b._list_value_art(kind, entries)
            main = lid in (trade.MAIN_WISH, trade.MAIN_HAVE)
            friends = sum(1 for e in entries if hold.get(e["name"])) if hold else 0
            out.append({"lid": lid, "name": tr(x["name"]) if main else x["name"], "count": n,
                        "shared": trade.is_shared(x), "shareable": kind in trade.SHAREABLE, "auto": bool(x.get("rule")),
                        "info": tr(f"{n} cards") + (f" · {eur(value)}" if value else "")
                        + (" · " + tr("automatic") if x.get("rule") else ""),
                        "art": art, "artist": artist, "example": bool(x.get("example")), "main": main,
                        "alarm": alarms.find_list(self.ctrl.settings, lid) is not None,
                        "friends": tr(f"{friends} of them your friends have") if friends else ""})
        return out

    @QtCore.Property(str, notify=listsChanged)
    def undoText(self):
        lb = self._lib()
        return lb.undoText if lb is not None else ""

    @QtCore.Slot()
    def undo(self):
        lb = self._lib()
        if lb is not None:
            lb.undo()
        self.listsChanged.emit()

    # ---------- Price alerts: inline editing ----------
    @QtCore.Slot()
    def loadPriceHistory(self):
        if hasattr(self.ctrl, "enable_price_history"):
            self.ctrl.enable_price_history()
        self.alarmChanged.emit()

    def _open_add(self, key):
        if key and key not in self._open_alarms:
            self._open_alarms.append(key)
            self._alarm_opts[key] = {}

    def _close(self, key):
        if key in self._open_alarms:
            self._open_alarms.remove(key)
        self._alarm_opts.pop(key, None)

    # ---------- "Price alerts" folder: one table row (the folder itself: AlarmsBackend) ----------
    def _card_row(self, a, p, rows, rule, hit):
        from collection import alarms
        o = alarms.opts_of(a)
        if a["kind"] == "wish" and o["psid"]:
            r = rows.get(o["psid"]) or carddb.cards_by_ids({o["psid"]}).get(o["psid"])
            imgs = [db_image(r)] if r else []
            where = f"{(r or {}).get('set_code', '').upper()} #{(r or {}).get('number', '')}"
        elif a["kind"] == "wish":
            imgs = [db_image(r) for r in alarms.prints_by_price(a["name"], 30) if has_image(r)][:9]
            where = tr("cheapest printing")
        else:
            r = rows.get(a.get("sid")) or carddb.cards_by_ids({a.get("sid")}).get(a.get("sid"))
            imgs = [db_image(r)] if r else []
            where = f"{(a.get('set') or '').upper()}{' · Foil' if a.get('foil') else ''}"
        if alarms.opts_text(o):
            where += f" · {alarms.opts_text(o)}"
        return {"key": alarms.card_key(a), "section": a["kind"], "icon": "bell", "name": a["name"], "where": where,
                "now": alarms.eur(p), "nowVal": p if p is not None else -1.0, "rule": rule, "hit": hit,
                "imgs": [i for i in imgs if i], "draft": False}

    # ---------- Card from another game (or without a printing): simple card on the right, no switching ----------
    _foreign = None

    def _show_foreign(self, game, t, empty=False):
        from collection import alarms
        import games
        r = None
        if not empty:
            if t.get("kind") == "trade":
                r = carddb.cards_by_ids({t.get("sid")}, game=game).get(t.get("sid"))
            else:
                a = next((a for a in alarms.all_alarms(self.ctrl.settings)
                          if alarms.game_of(a) == game and a.get("name") == t.get("name") and a.get("kind") == t.get("kind")), {})
                psid = alarms.opts_of(a)["psid"] if a else ""
                rows = carddb.cards_by_ids({psid}, game=game) if psid else {}
                r = rows.get(psid) or next((x for x in alarms.prints_by_price(t.get("name"), 30, game=game)
                                            if has_image(x, game)), None)
        self.page.alarm_side.close()
        price = None
        if r:
            price = r.get("eur_foil") if t.get("foil") and r.get("eur_foil") is not None else r.get("eur")
        self._foreign = {"game": game, "chip": games.SHORT.get(game, game.upper()), "nick": games.nick_of(game),
                         "name": (r or {}).get("name") or t.get("name") or "?",
                         "img": db_image_of(r, game) if r and has_image(r, game) else "",
                         "line": (f"{str(r.get('set_name') or r.get('set_code') or '').strip()} · #{r.get('number')}" if r else
                                  tr("No printing with an image found")),
                         "price": eur(price) if price is not None else "–",
                         "other": game != games.current().key}
        self.detailChanged.emit()

    @QtCore.Property("QVariant", notify=detailChanged)
    def foreignCard(self):
        return self._foreign or {}

    @QtCore.Slot()
    def closeForeign(self):
        self._foreign = None
        self.detailChanged.emit()

    @QtCore.Slot()
    def foreignSwitch(self):
        """'Open in Pokémon': only switch now (the price alerts folder stays open)."""
        f = self._foreign or {}
        if f.get("other"):
            g = f["game"]
            self._foreign = None
            self.ctrl.switch_game(g, then=lambda: self.ctrl.show_alarms())

    # ---------- new alerts: fields expand within the page ----------
    # ---------- List editor ----------
    def _drop_entries(self):
        self._entries = None

    @QtCore.Property("QVariantList", notify=entriesChanged)
    def entries(self):
        if self._entries is None:
            self._entries = self._make_entries()
        return self._entries

    def _make_entries(self):
        from collection import alarms
        lp = self.page.list_panel
        hold = self.page.holders() if lp.kind == "wish" else {}
        st = self.ctrl.settings
        out = []
        for key, nm, extra, n, w in lp.entries():
            target = self.alarms_b._entry_alarm(lp.kind, w, nm)
            al = alarms.find(st, target["kind"], target.get("name"), target.get("sid"), target.get("foil")) \
                if target else None
            missing = lp.kind == "have" and isinstance(w, dict) and bool(w.get("missing"))
            h = hold.get(nm) or []
            if lp.kind in ("wish", "custom"):
                pinned = bool(w.get("set"))
                can = True
                tip = (tr("Pinned: exactly this version – click: choose another printing or add a version") if pinned
                       else tr("Any version – click: choose a printing (pin it or add as another version)"))
            else:
                pinned, can = True, False
                tip = tr("Printing not in your library") if missing else tr("Exactly this printing from your collection")
            plus = not (lp.kind == "have" and isinstance(w, dict) and not missing and n >= int(w.get("count", 1)))
            out.append({"key": str(key), "name": nm, "extra": extra, "count": n, "missing": missing, "plusOk": plus,
                        "pinned": pinned, "pinEnabled": can, "pinTip": tip,
                        "canAlarm": target is not None, "alarm": alarms.text_of(al) if al else "",
                        "alarmKey": alarms.card_key(target) if target else "",
                        "holders": [{"img": back_image(b[2]), "tip": f"{b[1]} ({b[3]}×)"} for b in h[:4]],
                        "_w": w})
        return self._sorted(out)

    # ---------- Sorting of the cards in the list editor ----------
    @staticmethod
    def _natural(k):
        # natural direction: newest / most expensive / most first, name and set ascending
        return "desc" if k in ("added", "price", "count") else "asc"

    def _sorted(self, out):
        from collection import alarms
        k, d = self.ctrl.settings.get("list_sort") or ["added", "desc"]
        ws = [e.pop("_w") for e in out]
        if k == "name":
            key = [(e["name"].lower(), e["extra"]) for e in out]
        elif k == "count":
            key = [(e["count"], e["name"].lower()) for e in out]
        elif k == "set":
            key = []
            for e, w in zip(out, ws):
                sc = str((w or {}).get("set") or "").lower() if isinstance(w, dict) else ""
                num = str((w or {}).get("number") or "") if isinstance(w, dict) else ""
                key.append((sc or "~", int("".join(ch for ch in num if ch.isdigit()) or 0), e["name"].lower()))
        elif k == "price":
            prints = alarms.prints_of([e["name"] for e in out])
            key = []
            for e, w in zip(out, ws):
                w = w if isinstance(w, dict) else {}
                rows = prints.get(e["name"], [])
                sc, num = str(w.get("set") or "").lower(), str(w.get("number") or "")
                if sc:
                    rows = [r for r in rows if str(r.get("set_code") or "").lower() == sc
                            and str(r.get("number") or "") == num] or rows
                vals = [v for r in rows for v in ((r.get("eur_foil"),) if w.get("foil") else (r.get("eur"), r.get("eur_foil")))
                        if v is not None]
                key.append((min(vals) if vals else -1, e["name"].lower()))
        else:   # added
            key = [(float((w or {}).get("added") or 0) if isinstance(w, dict) else 0, e["name"].lower())
                   for e, w in zip(out, ws)]
        order = sorted(range(len(out)), key=lambda i: key[i], reverse=d == "desc")
        return [out[i] for i in order]

    def _key(self, key):
        """Key from QML back to the list's key (collection: uid may be a number)."""
        for e in self.page.list_panel.entries():
            if str(e[0]) == key:
                return e
        return None

    # ---------- Choose a printing (pin on a want) ----------
    @QtCore.Property(str, notify=entriesChanged)
    def printPick(self):
        return self.__dict__.get("_print_pick", "")

    @QtCore.Slot(str)
    def openPrintPick(self, key):
        """Pin: open/close the strip of all printings below the row."""
        self._print_pick = "" if key == self.printPick else key
        self.entriesChanged.emit()

    @QtCore.Property("QVariantList", notify=entriesChanged)
    def printPickRows(self):
        """All printings of the card in the open row (cheapest first); marked = pinned printing."""
        from collection import alarms
        e = self._key(self.printPick) if self.printPick else None
        if e is None:
            return []
        w = e[4] if isinstance(e[4], dict) else {}
        rows = alarms.prints_of([e[1]]).get(e[1], [])
        rows.sort(key=lambda r: (r.get("eur") is None, r.get("eur") or 0))
        cur = (str(w.get("set") or "").lower(), str(w.get("number") or ""))
        return [{"id": r["id"], "set": (r.get("set_code") or "").upper(), "number": r.get("number") or "",
                 "sname": r.get("set_name") or "",
                 "img": db_image(r), "price": eur(r.get("eur") if r.get("eur") is not None else r.get("eur_foil")),
                 "mark": "main" if (r.get("set_code"), str(r.get("number"))) == cur else "", "date": ""}
                for r in rows[:400]]

    @QtCore.Slot(str, str, str)
    def pickPrint(self, key, sid, mode):
        """mode "pin": set this entry to exactly that printing · "add": add the printing as another row ·
        "any": back to any version."""
        e = self._key(key)
        if e is None:
            return
        lp = self.page.list_panel
        if mode == "any":
            trade.set_pinned(e[0], lp.lid, False)
        else:
            r = carddb.cards_by_ids({sid}).get(sid)
            if r is None:
                return
            sc, num = r["set_code"], r["number"]
            lp._last_print[e[1]] = (sc, num)
            if mode == "add":
                trade.add_wish(e[1], 1, sc, num, list_id=lp.lid)
            else:
                trade.set_pinned(e[0], lp.lid, True, sc, num)
        self._print_pick = ""
        lp.fill()
        self.entriesChanged.emit()

    @QtCore.Slot(str, int)
    def change(self, key, delta):
        e = self._key(key)
        if e is not None:
            self.page.list_panel.change(e[0], None if delta == 0 else delta)

    @QtCore.Slot(str)
    def entryClicked(self, key):
        e = self._key(key)
        if e is not None:
            self.page.show_list_card(self.page.list_panel.kind, e)

    @QtCore.Slot(int)
    def addFromGrid(self, i):
        row = self.ed_b.row(i)
        if row is not None:
            self.page.list_panel.add_row(row)

    # ---------- Friend ----------
    # ---------- Note on a friend: only on your side, never shared (settings, by their profile ID) ----------
    syncChanged = QtCore.Signal()

    # ---------- Friend across games: their games, plain view for games that aren't open right now ----------
    # ---------- "Swap" tab ----------
    def _trade_titles(self):
        who = self.friends_b._friend().get("name") or "?"
        self.get_b.set_title(tr(f"You get from {who}"))
        self.give_b.set_title(tr(f"You give {who}"))

    @QtCore.Property(QtCore.QObject, constant=True)
    def getSide(self):
        return self.get_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def giveSide(self):
        return self.give_b

    @QtCore.Property(str, notify=sumChanged)
    def tradeSum(self):
        return self.page.trade_sum

    @QtCore.Property(bool, notify=sumChanged)
    def priced(self):
        """Prices in the trade (not in Orbit's Core) – without them no money button."""
        return self.page.priced()

    @QtCore.Property(bool, notify=sumChanged)
    def canOffer(self):
        return self.page.can_offer

    @QtCore.Slot()
    def shareOffer(self):
        self.page.share_offer()

    @QtCore.Slot()
    def bookOffer(self):
        self.page.book_offer()

    @QtCore.Slot()
    def moneyDialog(self):
        from ui import qdialogs
        st = {"v": float(getattr(self.page, "trade_money", 0.0) or 0.0)}

        def build(ui, d):
            return ui.col([
                ui.note(tr("Money in the trade: + you pay extra, − you get money. It's printed on the ticket.")),
                ui.note(tr("Bent°Corner handles no payments – you settle the amount yourselves.")),   # legal 03.11.
                ui.form([(tr("Amount"), ui.spin(st["v"], -100000, 100000, lambda v: st.update(v=float(v)),
                                               decimals=2, suffix=" €"))]),
                ui.row([ui.button(tr("No money"), lambda: (st.update(v=0.0), d.close("ok"))), ui.stretch(),
                        ui.button(tr("Cancel"), lambda: d.close(None)),
                        ui.button(tr("Apply"), lambda: d.close("ok"), active=True)]),
            ], spacing=10)
        if qdialogs.show(tr("Money in the trade"), build) == "ok":
            self.page.set_money(st["v"])

    @QtCore.Property(float, notify=sumChanged)
    def money(self):
        return float(getattr(self.page, "trade_money", 0.0) or 0.0)

    @QtCore.Property(str, notify=sumChanged)
    def offerCtx(self):
        """Is an offer currently being revised? Then "Share counter-offer (version n)"."""
        ctx = getattr(self.page, "offer_ctx", None)
        return f"{ctx['x'].upper()} · v{int(ctx['n']) + 1}" if ctx else ""

    # ---------- Trade offers (folder) ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def offersForm(self):
        if getattr(self, "_offers_form", None) is None:
            from ui.qform import Form
            self._offers_form = Form(self._build_offers)
        return self._offers_form

    def offers_refresh(self, open_folder=False):
        if getattr(self, "_offers_form", None) is not None:
            self._offers_form.soon()
        if open_folder and hasattr(self, "setFolder"):
            self.setFolder("offers")
        self.listsChanged.emit()

    def _build_offers(self, ui):
        from collection import offers
        from collection import ticket
        me = __import__("system.userprofile", fromlist=["userprofile"]).ensure(self.ctrl.settings).get("id")
        items = offers.sorted_offers()
        if not items:
            return ui.col([ui.note(tr("No trade offers yet. In a trade with a friend: check cards → “Share as ticket”. A ticket from someone else: Import friend … (choose the image) or New log → Trade ticket."))])
        rows = []
        for o in items:
            t = offers.latest(o)
            sd = ticket.side(t, me) if t else None
            give, get = (sd[0], sd[1]) if sd else ([], [])
            n_give, n_get = sum(int(c[4] or 1) for c in give), sum(int(c[4] or 1) for c in get)
            money = ticket.money_from_me(t, me) if t else 0
            cash = (" · " + tr(f"you pay {eur(money)}") if money > 0 else " · " + tr(f"you get {eur(-money)}")) \
                if abs(money) >= 0.01 else ""
            head = (f"<b>{_esc(o['partner'][1] or '?')}</b> · {tr(offers.STATUS_TEXT.get(o['status'], o['status']))}"
                    f" · v{int((t or {}).get('n') or 1)}")
            sub = (tr(f"you give {n_give}, you get {n_get}") + cash + " · " + tr("Trade ID") + " "
                   + o["id"].upper() + " · " + __import__("time").strftime("%d.%m.%Y %H:%M",
                                                                            __import__("time").localtime(o["updated"])))
            btns = []
            oid = o["id"]
            if o["status"] == "received":
                btns += [ui.button(tr("Accept"), lambda oid=oid: self._offer_do("accept", oid), active=True),
                         ui.button(tr("Counteroffer …"), lambda oid=oid: self._counter_dialog(oid)),
                         ui.button(tr("Decline"), lambda oid=oid: self._offer_do("decline", oid))]
            elif o["status"] == "sent":
                btns += [ui.button(tr("Show ticket"), lambda oid=oid: self._offer_do("show", oid)),
                         ui.button(tr("Change …"), lambda oid=oid: self._counter_dialog(oid)),
                         ui.button(tr("Withdraw"), lambda oid=oid: self._offer_do("withdraw", oid))]
            else:
                btns += [ui.button(tr("Show ticket"), lambda oid=oid: self._offer_do("show", oid))]
            rows.append(ui.group("", [ui.label(head), ui.note(sub), ui.row(btns + [ui.stretch()])]))
        return ui.col(rows, spacing=10)

    def _offer_do(self, what, oid):
        from collection import offers
        page = self.page
        if what == "accept":
            page.accept_offer(oid)
        elif what == "decline":
            page.decline_offer(oid)
        elif what == "withdraw":
            page.withdraw_offer(oid)
        elif what == "show":
            o = offers.get(oid)
            if o is not None:
                page.show_ticket(offers.latest(o))
        self.offers_refresh()

    def _counter_dialog(self, oid):
        """Change a counter-offer or your own offer: count per card (0 = out), money; "Add cards" via the
        friend's trade tab."""
        from collection import offers
        from collection import ticket
        from ui import qdialogs
        o = offers.get(oid)
        if o is None:
            return
        t = offers.latest(o)
        me = __import__("system.userprofile", fromlist=["userprofile"]).ensure(self.ctrl.settings).get("id")
        sd = ticket.side(t, me)
        if sd is None:
            return
        give = [list(c) for c in sd[0]]
        get = [list(c) for c in sd[1]]
        st = {"money": ticket.money_from_me(t, me)}

        def build(ui, d):
            def side_rows(cards):
                return [(f"{c[5] if len(c) > 5 else ''} · {str(c[0]).upper()} #{c[1]}" + (" · Foil" if c[3] else ""),
                         ui.spin(int(c[4] or 0), 0, 99, lambda v, c=c: c.__setitem__(4, int(v)))) for c in cards]
            return ui.col([
                ui.label(tr(f"Trade with {o['partner'][1] or '?'} · Trade ID {oid.upper()}"), big=True),
                ui.label(tr("You give"), bold=True), ui.form(side_rows(give)) if give else ui.note(tr("nothing")),
                ui.label(tr("You get"), bold=True), ui.form(side_rows(get)) if get else ui.note(tr("nothing")),
                ui.form([(tr("Money (+ you pay, − you get)"),
                          ui.spin(float(st["money"]), -100000, 100000, lambda v: st.update(money=float(v)),
                                  decimals=2, suffix=" €"))]),
                ui.row([ui.button(tr("Add cards (Orbit) …"),
                                  lambda: (d.close(None), self.page.edit_offer_in_trade(oid))),
                        ui.stretch(), ui.button(tr("Cancel"), lambda: d.close(None)),
                        ui.button(tr("Share as ticket"), lambda: d.close("share"), active=True)]),
            ], spacing=10)
        if qdialogs.show(tr("Change trade offer"), build, wide=True) == "share":
            new = self.page.counter_offer(oid, give, get, st["money"])
            if new is not None:
                self.page.show_ticket(new)
        self.offers_refresh()

    @QtCore.Property(QtCore.QObject, constant=True)
    def tradeDetail(self):
        return self.tdet_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def tradeCompare(self):
        return self.tcmp_b

    @QtCore.Property(bool, notify=detailChanged)
    def tradeDetailOpen(self):
        return not self.page.trade_side.card.isHidden()

    @QtCore.Property(bool, notify=detailChanged)
    def tradeCompareOpen(self):
        side = self.page.trade_side
        return not side.card.isHidden() and not side.cmp.isHidden()

    @QtCore.Property(int, notify=detailChanged)
    def tradeDetailWidth(self):
        return int(self.ctrl.settings.get("trade_detail_w") or 520)

    @QtCore.Slot()
    def tradeEscape(self):
        side = self.page.trade_side
        if not side.cmp.isHidden():
            side.host.close_compare()
        else:
            side.close()
        self.detailChanged.emit()
