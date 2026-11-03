"""Library in Qt Quick (qml/pages/LibraryPage.qml).

The logic lives in librarycore.LibraryCore: search, filters, sorting, grouping, collection changes,
detail rows. This object passes its state to QML (grid, chips, status) and the clicks from QML back to it.
"""
import html
import re

from PySide6 import QtCore
from PySide6.QtCore import Qt

from cards import carddb
from ui import quickimages
from ui import look
from collection.collection import lang_short
from system.i18n import tr
from cards import library
from scanner.common import BASE, lang_img
from ui.librarycore import SORT_NATURAL, THUMBS, chip_texts, detail_width, display, eur, sets_text

SORTS = [("relevance", "Beste Treffer"), ("count", "Anzahl"), ("name", "Name"), ("price", "Preis"), ("set", "Set"),
         ("new", "Neueste"),
         ("type", "Kartentyp"), ("mv", "Manawert"), ("color", "Farbe"), ("rarity", "Seltenheit")]
SORT_DESC = {
    "relevance": "Mit Suchtext: Treffer im Namen zuerst, dann Typzeile, Regeltext, Künstler … Ohne Suchtext: "
                 "alphabetisch.",
    "count": "deine Sammlung: meiste Exemplare zuerst, bei gleicher Anzahl alphabetisch",
    "name": "alphabetisch nach Kartenname",
    "price": "nach Preis der Karte",
    "set": "nach Erscheinen des Sets, darin nach Kartennummer",
    "new": "Sammlung: zuletzt hinzugefügt · alle Karten: zuletzt erschienen",
    "type": "Kreatur, Planeswalker, Spontanzauber, Hexerei, Artefakt, Verzauberung, Schlacht, Land",
    "mv": "nach Manawert",
    "color": "Weiß, Blau, Schwarz, Rot, Grün, mehrfarbig, farblos",
    "rarity": "Mythic, Rare, Uncommon, Common",
}


def card_source(row, own_lang=False, width=480):
    """Image source of a tile (like LibraryWindow._thumb_src) -> image://cards/… (loads in the background)."""
    lang = row.get("lang") if own_lang else "en"
    lang = lang or "en"
    version = "normal" if width > 160 else "small"
    if version == "small":   # only one size at the source (some games): one key, so the image is fetched only once
        def url_of(v):
            return (row.get("normal" if v == "normal" else "thumb") if lang == "en" else None) \
                or library.image_url(row["set"], row["number"], lang, v)
        small_url = url_of("small")
        if small_url and small_url == url_of("normal"):
            version = "normal"
    key = f"{row['sid']}_{lang}_{version[0]}"
    if quickimages.ROUND_DIR is None:
        quickimages.ROUND_DIR = THUMBS / "rund"   # pre-rounded tiles (WebP) – Qt loads them without Python
    done = quickimages.round_url(key)
    if done:   # pre-rounded tile already there (known in memory): no need to look for its sources on disk
        return done
    local = BASE / lang_img(row["img"], lang) if row.get("img") else None
    url = (row.get("normal" if version == "normal" else "thumb") if lang == "en" else None) \
        or library.image_url(row["set"], row["number"], lang, version)
    cache = THUMBS / f"{row['sid']}_{lang}_{version[0]}.jpg"
    small = THUMBS / f"{row['sid']}_{lang}_s.jpg"
    if version == "normal" and not cache.exists() and not (local and local.exists()) and small.exists():
        # small image already there (e.g. from the offline pack): use it instead of fetching the large one from the net
        src = quickimages.register(key + "_o", small, None, None)
        return quickimages.round_url(key + "_o") or src
    if url and quickimages.missing_at_source(url) and not cache.exists() and not (local and local.exists()):
        return ""   # the source has none (a remembered 404): NoImage right away, no request on every scroll
    src = quickimages.register(key, local, url, cache)
    return quickimages.round_url(key) or src


_backs = {}


def back_image(back):
    """Card back (profile/friend) as an image for QML -> image://cards/back_…"""
    key = f"back_{back}"
    if key not in _backs:
        from system import userprofile
        _backs[key] = quickimages.keep(key, userprofile.back_pixmap(back, 88, border="#0b0e1a").toImage())
    return _backs[key]


class CardGridModel(QtCore.QAbstractListModel):
    """Tiles for the grid – mirrored from LibraryWindow.model."""
    ROLES = ("key", "name", "price", "setLine", "chips", "img", "dim", "nameColor", "count", "foil",
             "decks", "cond", "pending", "picked", "tile")
    # what a tile shows, in one call (role "tile"): every role read from QML is a call into Python that needs the GIL –
    # with the camera running each one can wait several ms (tester log: 250–300 ms per rebuild with 11 roles a tile)
    TILE = ("name", "price", "setLine", "chips", "cond", "img", "pending", "dim", "nameColor", "decks")
    imageReady = QtCore.Signal(str)   # slow image server: the preload queue has fetched an image (any thread)

    def __init__(self, backend):
        super().__init__(backend)
        self.b = backend
        self.rows = []
        self._tiles = {}   # row -> the "tile" dict (dropped on every change of the rows or their images)
        # connected first, so it runs before the views: whoever reports a change (holders, prices, images …), the
        # tiles in that range are computed anew – only "picked" alone leaves them (it isn't part of the tile)
        self.dataChanged.connect(self._drop_tiles)
        # slow image servers (Lorcana): tiles show a placeholder until the queue has their image – then refresh the
        # image role, batched (several images a second would otherwise rebuild the tiles each time)
        self._ready_t = QtCore.QTimer(self, singleShot=True, interval=300)
        self._ready_t.timeout.connect(self._images_ready)
        self.imageReady.connect(lambda _key: self._ready_t.isActive() or self._ready_t.start())
        quickimages.on_ready(self.imageReady.emit)

    def picked_changed(self, keys):
        """Several cards chosen (ui/qselect.py): tell only the tiles whose state changed – in runs, so a lasso over
        2000 cards stays smooth."""
        if not keys or not self.rows:
            return
        role = [Qt.UserRole + self.ROLES.index("picked")]
        idx = [i for i, r in enumerate(self.rows) if (r.get("key") or r.get("sid")) in keys]
        start = prev = None
        for i in idx + [None]:
            if i is not None and prev is not None and i == prev + 1:
                prev = i
                continue
            if start is not None:
                self.dataChanged.emit(self.index(start), self.index(prev), role)
            start = prev = i

    def _drop_tiles(self, top, bottom, roles=()):
        if list(roles) == [Qt.UserRole + self.ROLES.index("picked")]:
            return
        for i in range(top.row(), bottom.row() + 1):
            self._tiles.pop(i, None)

    def _images_ready(self):
        if self.rows:
            self.dataChanged.emit(self.index(0), self.index(len(self.rows) - 1),
                                  [Qt.UserRole + self.ROLES.index(k) for k in ("img", "pending", "tile")])

    def roleNames(self):
        return {Qt.UserRole + i: n.encode() for i, n in enumerate(self.ROLES)}

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role):
        if not index.isValid() or role < Qt.UserRole:
            return None
        key = self.ROLES[role - Qt.UserRole]
        if key == "tile":
            i = index.row()
            t = self._tiles.get(i)
            if t is None:
                t = self._tiles[i] = {k: self._value(i, k) for k in self.TILE}
            return t
        return self._value(index.row(), key)

    def _value(self, i, key):
        r = self.rows[i]
        b = self.b
        if key == "key":
            return r.get("key") or r.get("sid")
        if key == "name":
            return r["name"]
        if key == "price":
            return eur(r["price"]) if r.get("price") is not None else ""
        if key == "setLine":
            return sets_text(r, b.disp)
        if key == "chips":
            texts = chip_texts(r, b.disp, "mine" if b.lib.mode == "altart" else b.lib.mode)
            if r.get("sid") in b.lib.list_any:   # a wish for any version: this tile is its cheapest copy
                texts = [tr("Any version")] + texts
            return texts
        if key == "cond":   # condition: its own box on the tile (only if not everything is Near Mint)
            from ui.librarycore import cond_chip
            return cond_chip(r) if b.lib.mode in ("mine", "altart") and b.lib.ctrl.settings.get("cond_chip", True) else ""
        if key == "img":
            return card_source(r, b.lib.mode in ("mine", "altart") and b.lib.own_lang.isChecked())
        if key == "pending":   # slow image server: still in the preload queue (quickimages.pending)
            t = self._tiles.get(i)
            src = (t or {}).get("img") or card_source(r, b.lib.mode in ("mine", "altart") and b.lib.own_lang.isChecked())
            return src.startswith("image://cards/") and quickimages.pending(src[len("image://cards/"):])
        if key == "dim":
            return b.lib.mode == "all" and not r.get("count") and b.lib.mark_owned.isChecked()
        if key == "picked":
            return (r.get("key") or r.get("sid")) in b.sel_b.keys
        if key == "nameColor":
            return look.rarity_color(r.get("rarity")) if look.RARITY_NAMES else ""
        if key == "count":
            return int(r.get("count") or 0)
        if key == "foil":
            return bool(r.get("foil"))
        if key == "decks":  # which decks the card is in (badge at the top left)
            from collection.deckcore import usage_chips
            return usage_chips(b.ctrl, r.get("db") or r)   # the card database row (collection rows carry it)
        return None

    def sync(self, rows, append=False):
        if append and len(rows) >= len(self.rows) and rows[:len(self.rows)] == self.rows:
            new = rows[len(self.rows):]
            if new:
                self.beginInsertRows(QtCore.QModelIndex(), len(self.rows), len(rows) - 1)
                self.rows = list(rows)   # rows before stay as they were: their tiles too
                self.prefetch()   # before the tiles exist: they ask whether their image is queued (pending)
                self.endInsertRows()
            return
        if len(rows) == len(self.rows) and all(a.get("key") == b.get("key") for a, b in zip(rows, self.rows)):
            # same cards (only quantity/price differ): update in place – no rebuild, scroll position stays. All tiles:
            # chips, deck badges, dimming and image also hang on state outside the row (lists, decks, switches)
            self.rows = list(rows)
            if rows:
                self.dataChanged.emit(self.index(0), self.index(len(rows) - 1))
            return
        self.beginResetModel()
        self._tiles = {}
        self.rows = list(rows)
        self.prefetch()   # before the tiles exist: they ask whether their image is queued (pending)
        self.endResetModel()

    def prefetch(self):
        """Preload images from the net in tile order (top first) – quickimages."""
        import games
        b = self.b
        own = b.lib.mode in ("mine", "altart") and b.lib.own_lang.isChecked()
        try:
            # key (not the URL: finished tiles are already files and need nothing more)
            quickimages.prefetch([quickimages.key_of(card_source(r, own)) or "" for r in self.rows[:1500]],
                                 ahead=games.current().prefetch_ahead)
        except Exception:  # noqa: BLE001 – preloading is a bonus
            pass


def read_chips(bar, collapsing=()):
    """Chip boxes of a search (searchbox.SearchBox.chips_data) -> (list for QML, {id: click})."""
    out, fns = [], {}
    for gi, g in enumerate(bar.chips_data):
        gid = f"g{gi}"
        if g["kind"] == "clear":
            text, fn, _, _ = g["values"][0]
            cid = gid + "x"
            fns[cid] = fn
            out.append({"id": gid, "key": "clear", "title": "", "values": [{"cid": cid, "text": text,
                                                                             "kind": "clear", "neg": False,
                                                                             "collapsing": False}],
                        "titleId": "", "coverId": "", "grey": False, "clear": True, "collapsing": False})
            continue
        vals = []
        for vi, (text, fn, kind, uid) in enumerate(g["values"]):
            vid = f"{gid}v{vi}"
            fns[vid] = fn or (lambda: None)
            vals.append({"cid": vid, "text": text, "kind": kind, "neg": text.startswith("≠"),
                         "collapsing": uid is not None and uid in bar.collapsing and not g["fading"]})
        tid = cid = ""
        if g["on_title"] is not None:
            tid = gid + "t"
            fns[tid] = g["on_title"]
        if g["undo_all"] is not None:
            cid = gid + "c"
            fns[cid] = g["undo_all"]
        title = g["title"] or ""
        key = title + "|" + (vals[0]["text"] if not title and vals else "")
        out.append({"id": gid, "key": key, "title": title, "values": vals, "titleId": tid, "coverId": cid,
                    "grey": bool(g["grey"]), "clear": False, "collapsing": bool(g["fading"])})
    return out, fns


class LibraryBackend(QtCore.QObject):
    changed = QtCore.Signal()        # state (mode, sorting, columns, status …)
    chipsChanged = QtCore.Signal()
    refreshed = QtCore.Signal(bool)  # new results (True = new search: cards fade in staggered)
    swapped = QtCore.Signal()  # detail and compare view have swapped (QML lets both slide past each other)
    selectRow = QtCore.Signal(int)
    renameAsked = QtCore.Signal(str, str)   # "Rename" in a list's menu: QML puts the name in place into a field
    valueChanged = QtCore.Signal()   # collection value history (expands at the bottom above the status line)

    def __init__(self, ctrl, lib=None, width_key="lib_detail_w", main=True):
        """lib: a LibraryCore (default: the Library); width_key: setting for the width of the
        detail view; main = the Library itself (set completion, hint for an empty collection)."""
        super().__init__(ctrl)
        self.ctrl, self.width_key, self.main = ctrl, width_key, main
        if lib is None:
            ctrl.stream.ensure_page("library")
            lib = ctrl.library_win
        self.lib = lib
        self._value_open, self._value_spec, self._value_busy = False, {}, False
        self.disp = display(ctrl.settings)
        self.grid = CardGridModel(self)
        self._chips, self._chip_fns = [], {}
        self._collapsing = set()
        # mirror the Library's results
        lib.model.reset.connect(lambda: self._sync(False))
        lib.model.appended.connect(lambda *_: self._sync(True))
        lib.status.changed.connect(self.changed.emit)
        lib.changed.connect(self.changed.emit)
        bar = lib.bar
        old_chips = bar.refresh_chips

        def refresh_chips():
            old_chips()
            self._read_chips()
        bar.refresh_chips = refresh_chips
        lib.refresh_chips = refresh_chips
        old_adv = bar.update_adv_btn

        def update_adv():
            old_adv()
            self.changed.emit()
        bar.update_adv_btn = update_adv
        lib.update_adv_btn = update_adv
        # transitions of the old Library off (it is invisible) – Qt Quick animates by itself
        lib.morph.run = lambda apply, anchor_row=None, swap=None, then=None: (apply(), then() if then else None)
        lib.veil_out = lambda: 0.0
        lib.slide.open_orig, lib.slide.close_orig = lib.slide.open, lib.slide.close
        lib.slide.open = lambda animate=True: lib.slide.open_orig(False)
        lib.slide.close = lambda animate=True: lib.slide.close_orig(False)
        # the old window is invisible – for its logic "visible" means: not explicitly hidden
        # (otherwise compare always counts as closed: wrong work area and thus the wrong card count in the slider)
        for panel in (lib.detail, lib.compare):
            panel.isVisible = lambda w=panel: not w.isHidden()
        # closing: only clear the content once the view has slid out (otherwise it slides out empty);
        # if a new card arrives first, the clearing is skipped
        for panel in (lib.detail, lib.compare):
            self._defer_clear(panel)
        # detail and compare view
        from ui.qadvsearch import AdvBackend
        self.adv_b = AdvBackend(ctrl, lib.bar, self)
        from ui.qgroup import GroupBackend
        self.group_b = GroupBackend(ctrl, lib, self)   # Group by (the tree between search and sorting)
        from ui.qselect import SelectBackend
        self.sel_b = SelectBackend(ctrl, lib, self)    # several cards chosen at once
        from ui.qcompletion import CompletionBackend
        self.comp_b = CompletionBackend(ctrl, lib, self)
        if main and lib.completion_open:
            self.comp_b.fill()
        from ui.qdetail import DetailBackend
        self.detail_b = DetailBackend(ctrl, lib, lib.detail, self)
        self.compare_b = DetailBackend(ctrl, lib, lib.compare, self)
        for name in ("show_detail", "close_detail", "open_beside", "show_compare", "close_compare", "_cmp_changed",
                     "show_card_row", "sync_slider", "swap_panels"):
            self._after(lib, name)
        orig_swap = lib.swap_panels

        def swap_panels():
            ok = lib.detail.row is not None and lib.compare.row is not None and not lib.compare.isHidden()
            if ok:  # the images don't fly in again – the views slide
                self.detail_b.quiet_next = self.compare_b.quiet_next = True
            res = orig_swap()
            if ok:  # update the content right away (otherwise the cards first swap back and forth, then it slides)
                for b in (self.detail_b, self.compare_b):
                    b._t.stop()
                    b._emit()
                self.changed.emit()
                self.swapped.emit()
            return res
        lib.swap_panels = swap_panels
        self._sync(False)
        self._read_chips()

    def _defer_clear(self, panel):
        orig = panel.show_row
        timer = QtCore.QTimer(self, singleShot=True)
        timer.timeout.connect(lambda: orig(None))

        def show_row(row):
            if row is None and panel.row is not None:
                try:
                    slow = max(1.0, float(self.ctrl.settings.get("anim_speed") or 1.0))
                except (TypeError, ValueError):
                    slow = 1.0
                timer.start(round(1700 * slow))
                return None
            timer.stop()
            return orig(row)
        panel.show_row = show_row

    def _after(self, obj, name):
        orig = getattr(obj, name)

        def fn(*a, **k):
            res = orig(*a, **k)
            self.changed.emit()
            return res
        setattr(obj, name, fn)

    @QtCore.Property(QtCore.QObject, constant=True)
    def adv(self):
        return self.adv_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def group(self):
        return self.group_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def sel(self):
        return self.sel_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def completion(self):
        return self.comp_b

    @QtCore.Property(bool, notify=changed)
    def completionOpen(self):
        return bool(self.main and self.lib.completion_open)

    @QtCore.Property(bool, constant=True)
    def isMain(self):
        return self.main

    @QtCore.Property(bool, notify=changed)
    def showMine(self):
        return not self.lib.mine_btn.isHidden()

    @QtCore.Property(bool, notify=changed)
    def showAll(self):
        return not self.lib.all_btn.isHidden()

    @QtCore.Slot()
    def toggleCompletion(self):
        self.lib.show_completion()
        if self.lib.completion_open:
            self.comp_b.fill()
        self.changed.emit()

    # ---------- Collection value history (Magic: last 90 days from the price history) ----------
    @QtCore.Property(bool, notify=changed)
    def valueAvailable(self):
        from cards import valuehist
        return bool(self.main and valuehist.available())

    @QtCore.Property(bool, notify=valueChanged)
    def valueOpen(self):
        return self._value_open

    @QtCore.Property("QVariantMap", notify=valueChanged)
    def valueChart(self):
        return self._value_spec

    @QtCore.Slot()
    def toggleValue(self):
        self.setValueOpen(not self._value_open)

    @QtCore.Slot(bool)
    def setValueOpen(self, on):
        if bool(on) == self._value_open:
            return
        self._value_open = bool(on)
        if self._value_open:
            self._value_spec = {"kind": "frame", "title": tr("Wert der Sammlung"), "sub": tr("calculating …"),
                                "modes": [], "mode": 0, "clickable": False, "h": 260,
                                "body": {"type": "empty", "text": tr("calculating …")}}
            self._value_calc()
        self.valueChanged.emit()

    @QtCore.Slot()
    def openStats(self):
        """The "More statistics" button: Statistics, "Collection" tab."""
        self.setValueOpen(False)
        self.ctrl.stream.show_page("stats", back=True)
        sb = (getattr(getattr(self.ctrl, "shell", None), "backends", None) or {}).get("stats")
        if sb is not None:
            sb.setTab("collection")   # also rebuilds the tab
        elif getattr(self.ctrl, "stats_page", None) is not None:
            self.ctrl.stats_page.show_tab("collection")

    def _value_calc(self):
        """Compute in the background (many cards × 90 days) – the Library stays smooth."""
        if self._value_busy:
            return
        self._value_busy = True
        from cards import valuehist
        valuehist.compute_async(self.lib.coll.items, self._value_done)

    def _value_done(self, res):
        from cards import valuehist
        self._value_busy = False
        self._value_spec = valuehist.chart_spec(res, h=260, sub_pad=40, link=tr("More statistics →"))   # room for the ✕
        self.valueChanged.emit()

    # ---------- Lists (left, share the column with set completion) ----------
    @QtCore.Property(bool, notify=changed)
    def listsOpen(self):
        return bool(self.main and self.lib.lists_open)

    @QtCore.Property(bool, notify=changed)
    def sideOpen(self):
        return bool(self.main and (self.lib.lists_open or self.lib.completion_open))

    @QtCore.Property(str, notify=changed)
    def sideTop(self):
        return self.lib.side_top

    @QtCore.Slot()
    def toggleLists(self):
        self.lib.show_lists()
        self.changed.emit()

    LIST_KINDS = (("wish", "Wunschlisten"), ("have", "Tauschlisten"), ("custom", "Eigene Listen"))

    @QtCore.Property("QVariantList", notify=changed)
    def lists(self):
        """Rows of the lists column: section headers {head, kind, name}, lists {kind, id, name, count, main, on, open}
        and – for expanded lists – their cards {entry, kind, id, key, name, extra, count, red}."""
        from collection import alarms
        import games
        from collection import trade
        sel = self.lib.list_sel
        wishes = trade.wishes(raw=True)
        items = self.ctrl.collection.items
        opened = getattr(self, "_open_lists", set())
        cur = games.current().key
        out = [None]   # header of the open game (filled in below once the numbers are in)
        n_lists = n_cards = 0
        for kind, title in self.LIST_KINDS:
            out.append({"head": True, "kind": kind, "name": tr(title)})
            for x in trade.lists(kind):
                lid = x["id"]
                if kind in ("wish", "custom"):
                    n = sum(int(w.get("count", 1)) for w in wishes if (w.get("list") or trade.MAIN_WISH) == lid)
                elif lid == trade.MAIN_HAVE:
                    n = sum(min(int(it.get("trade") or 0), int(it.get("count", 1))) for it in items)
                else:
                    n = sum(trade.have_counts(lid).values())
                main = lid in (trade.MAIN_WISH, trade.MAIN_HAVE)
                n_lists, n_cards = n_lists + 1, n_cards + (n or 0)
                is_open = (kind, lid) in opened
                out.append({"head": False, "kind": kind, "id": lid, "name": tr(x["name"]) if main else x["name"],
                            "count": n, "main": main, "on": sel == (kind, lid), "open": is_open,
                            "auto": bool(x.get("rule")), "shared": trade.is_shared(x),
                            "shareable": kind in trade.SHAREABLE and not x.get("example")})
                if is_open:
                    for e in trade.entry_rows(kind, lid, self.ctrl.collection):
                        out.append(dict(e, entry=True, head=False, kind=kind, id=lid,
                                        extra=e["extra"] or tr("any version"),
                                        pinnable=kind in ("wish", "custom"),
                                        pinned=kind in ("wish", "custom") and bool(e["key"].split("|")[1])))
        out[0] = self._game_head(cur, n_lists, n_cards, alarms.hits_of_game(self.ctrl.settings, cur), True, True)
        # only the open game – in mixed mode the lists show only the trade side
        return out

    @staticmethod
    def _game_head(key, n_lists, n_cards, hits, current, is_open):
        """Header row of a game in the lists column – you can see what is inside even when collapsed."""
        import games
        bits = [tr(f"{n_lists} lists") if n_lists != 1 else tr("1 list"), tr(f"{n_cards} cards")]
        # alerts separately: QML shows them as a link (bell + underlined) that jumps to Trade → Price alerts
        alerts = (tr("1 alert") if hits == 1 else tr(f"{hits} alerts")) if hits else ""
        return {"head": False, "entry": False, "gameHead": True, "game": key, "name": games.name_of(key),
                "summary": " · ".join(bits), "alerts": alerts, "current": current, "open": is_open}

    @QtCore.Slot(str)
    def toggleGameLists(self, key):
        """Expand/collapse other games in the lists column (remembered)."""
        shown = set(self.ctrl.settings.get("lists_games_open") or [])
        (shown.discard if key in shown else shown.add)(key)
        self.ctrl.settings["lists_games_open"] = sorted(shown)
        self.ctrl.settings_changed()
        self.changed.emit()

    @QtCore.Slot()
    def openAlarms(self):
        """„1 alert“ in the lists column: straight to Trade → Price alerts."""
        self.ctrl.show_alarms()

    @QtCore.Slot(str, str)
    def editList(self, kind, lid):
        """Arrow on a list: open it in Trade for editing (entries, versions, sharing)."""
        self.ctrl.stream.show_page("trade", back=True)
        tb = getattr(getattr(self.ctrl, "shell", None), "backends", {}).get("trade")
        if tb is not None:
            tb.lists_b.openList(kind, lid)   # lists: TRADE-SPLIT (ListsBackend)

    @QtCore.Slot(str, str, str)
    def openOtherList(self, key, kind, lid):
        """List of another game: switch to that game and show the Library there with exactly this list."""
        def show():
            self.ctrl.stream.show_page("library")
            if not self.lib.lists_open:
                self.lib.show_lists()
            self.lib.pick_list(kind, lid)
            self.changed.emit()
        if not self.ctrl.switch_game(key, then=show):
            self.ctrl.stream_toast(tr("Can't switch right now – wait for the running tasks first."))

    @QtCore.Slot(str, str)
    def toggleListOpen(self, kind, lid):
        opened = self.__dict__.setdefault("_open_lists", set())
        (opened.discard if (kind, lid) in opened else opened.add)((kind, lid))
        self.changed.emit()

    @QtCore.Slot(str, str, str, int)
    def changeEntry(self, kind, lid, key, delta):
        """−/+/✕ on a card in the lists column (delta 0 = remove entirely)."""
        from collection import trade
        trade.change_entry(kind, lid, key, None if delta == 0 else delta, self.ctrl.collection)
        self._lists_touched(kind, lid)

    @QtCore.Slot(str, str, str)
    def showEntry(self, kind, lid, key):
        """Click on a card of an expanded list (Oliver, review .90): the card in the detail view – and, if you own it,
        selected in your own library. If that list is picked, it stays and the card is selected in it (review .101);
        otherwise My Collection. Never off into "All cards"."""
        from collection import trade
        coll = self.ctrl.collection
        sc = num = lang = None
        foil, name, uid = None, "", None
        if kind in ("wish", "custom"):
            w = next((w for w in trade.wishes([lid]) if trade.wish_key(w) == key), None)
            if w is None:
                return
            name, sc, num = w["name"], w.get("set"), w.get("number")
            if sc and (w.get("lang") or w.get("foil")):
                lang, foil = w.get("lang") or "en", bool(w.get("foil"))
        elif key.startswith("p:"):   # a print on a trade list that isn't in the collection (red)
            sc, num, lang, f = (key[2:].split("|") + ["", "", "en", "0"])[:4]
            foil = f == "1"
            name = trade.have_print_names(lid).get(key[2:], "")
        else:
            it = next((it for it in coll.items if it.get("uid") == key), None)
            if it is None:
                return
            uid, name, sc, num = key, it["name"], it.get("set"), it.get("number")

        def same_print(it):
            if uid:
                return it.get("uid") == uid
            if sc:
                if str(it.get("set") or "").lower() != str(sc).lower() or str(it.get("number")) != str(num):
                    return False
                return lang is None or ((it.get("lang") or "en") == lang and bool(it.get("foil")) == foil)
            return (it.get("name") or "").lower() == name.lower()   # any version: any copy of the card

        lc = self.lib
        if lc.list_sel is not None:
            # a list is picked: stay in it and select the card there (Oliver, review .101)
            rows = lc.model.rows
            i = next((i for i, r in enumerate(rows)
                      if same_print(r) or any(same_print(it) for it in r.get("items") or [])), -1)
            if i >= 0:
                lc.show_detail(i)
                self.changed.emit()
                QtCore.QTimer.singleShot(0, lambda: self.selectRow.emit(i))
                return
        if any(same_print(it) for it in coll.items):
            if lc.list_sel is not None:
                lc.pick_list(*lc.list_sel)   # back to the whole library (keeps search and filters)
            if lc.mode != "mine":
                lc.set_mode("mine")
            rows = lc.model.rows
            i = next((i for i, r in enumerate(rows) if any(same_print(it) for it in r.get("items") or [])), -1)
            if i >= 0:
                lc.show_detail(i)
                self.changed.emit()
                QtCore.QTimer.singleShot(0, lambda: self.selectRow.emit(i))
                return
        # not owned (or hidden by search/filters): only the detail view, the library stays as it is
        db = None
        if carddb.exists():
            if sc and num:
                db = carddb.by_prints([(sc, num)]).get((str(sc).lower(), str(num)))
            if db is None and name:
                db = carddb.by_names([name]).get(name.lower())
        if db is None:
            return
        row = self.lib.row_from_db(db)
        if lang:
            row.update(lang=lang, foil=bool(foil))
        self.lib.show_card_row(row)
        self.changed.emit()

    def _lists_touched(self, kind=None, lid=None):
        if self.lib.list_sel is not None:
            self.lib.refresh(keep=True)
        page = getattr(self.ctrl, "trade_page", None)
        if page is not None and hasattr(page, "lists_changed"):
            page.lists_changed.emit()
        det = getattr(self.lib, "detail", None)
        if det is not None and det.row is not None:
            det.refresh_lists()
        self.changed.emit()

    @QtCore.Slot(int, str, str)
    def dropOnList(self, i, kind, lid):
        """Card dragged from the grid onto a list: exactly this print is added (trade list: an owned
        copy, otherwise red as a print)."""
        rows = self.lib.model.rows
        if 0 <= i < len(rows):
            self._drop_row(rows[i], kind, lid)

    @QtCore.Slot(bool, str, str)
    def dropShownOnList(self, compare, kind, lid):
        """The card of the detail view (compare: of the comparison) dragged onto a list – exactly this print."""
        p = self.lib.compare if compare else self.lib.detail
        if getattr(p, "row", None) is not None:
            self._drop_row(p.row, kind, lid)

    def _drop_row(self, r, kind, lid):
        from collection import trade
        e = {"name": r["name"], "set": (r.get("set") or "").lower() or None, "number": r.get("number"), "count": 1,
             "lang": r.get("lang") or "en", "foil": bool(r.get("foil")), "uid": None}
        trade.put_entries(kind, lid, [e], self.ctrl.collection)
        name = next((x["name"] for x in trade.lists(kind) if x["id"] == lid), "")
        self.ctrl.shell.show_toast(tr(f"“{r['name']}” → {tr(name)}")) if getattr(self.ctrl, "shell", None) else None
        self._lists_touched(kind, lid)

    # ---------- Manage lists ("⋯" menu on every list) ----------
    @QtCore.Slot(str, str, result="QVariantList")
    def listMenu(self, kind, lid):
        from collection import trade
        names = dict((k, tr(t)) for k, t in self.LIST_KINDS)
        out = [{"text": tr("Rename"), "key": "rename"},   # in place, also the default lists (review .101)
               {"text": tr("Copy"), "key": "copy"}]
        if kind in trade.SHAREABLE:
            x = next((x for x in trade.lists(kind) if x["id"] == lid), {})
            on = trade.is_shared(x)
            out.append({"sep": True})
            out.append({"text": tr("private"), "key": "share:0", "on": not on})
            out.append({"text": tr("shared with friends"), "key": "share:1", "on": on})
        out.append({"sep": True})
        out.append({"text": tr("Move to"), "enabled": False})
        for k, t in self.LIST_KINDS:
            if k != kind:
                out.append({"text": names[k], "key": f"move:{k}", "indent": True})
        others = [(k, x) for k, _ in self.LIST_KINDS for x in trade.lists(k) if (k, x["id"]) != (kind, lid)]
        if others:
            out.append({"text": tr("Merge with"), "enabled": False})
            for k, x in others:
                nm = tr(x["name"]) if x["id"] in (trade.MAIN_WISH, trade.MAIN_HAVE) else x["name"]
                out.append({"text": f"{nm}  ·  {names[k]}", "key": f"merge:{k}:{x['id']}", "indent": True})
        # no "Empty …" (Oliver, review .90): a list is deleted, its cards removed one by one – since review .101 also
        # the default wish and trade list (then there simply is none)
        out.append({"sep": True})
        out.append({"text": tr("Delete …"), "key": "delete"})
        return out

    @QtCore.Slot(str, str, str)
    def listAction(self, kind, lid, key):
        from ui import qdialogs
        from collection import trade
        coll = self.ctrl.collection
        x = next((x for x in trade.lists(kind) if x["id"] == lid), None)
        if x is None:
            return
        name = tr(x["name"]) if lid in (trade.MAIN_WISH, trade.MAIN_HAVE) else x["name"]
        if key == "rename":
            self.renameList(kind, lid)
            return
        if key == "delete":
            self.deleteList(kind, lid)
            return
        if key.startswith("share:"):
            trade.set_shared(kind, lid, key == "share:1")
            self.changed.emit()
            if hasattr(self.ctrl, "relay_auto_lists"):
                self.ctrl.relay_auto_lists()
            return
        snap = trade.snapshot_lists(coll)
        if key == "copy":
            trade.copy_list(kind, lid, coll, name=tr(f"{name} (copy)"))
            self._undo(snap, tr(f"“{name}” copied"))
        elif key.startswith("move:"):
            to = key[5:]
            if kind == "have" or to == "have":
                if not qdialogs.question(tr("Move list"), tr(
                        "Trade lists consist of your own copies, wish and own lists of card names or prints. Moving converts them – cards you don't have appear red as a print in a trade list. Move?")):
                    return
            new = trade.move_list(kind, lid, to, coll)
            if self.lib.list_sel == (kind, lid):
                self.lib.list_sel = (to, new)
            self._undo(snap, tr(f"“{name}” moved"))
        elif key.startswith("merge:"):
            _, to_kind, to_lid = key.split(":", 2)
            y = next((y for y in trade.lists(to_kind) if y["id"] == to_lid), None)
            if y is None:
                return
            target = tr(y["name"]) if to_lid in (trade.MAIN_WISH, trade.MAIN_HAVE) else y["name"]
            gone = tr("Afterwards it is deleted.") if lid not in (trade.MAIN_WISH, trade.MAIN_HAVE) else \
                tr("Afterwards it is empty.")
            if not qdialogs.question(tr("Merge lists"), tr(f"Move all cards from “{name}” into “{target}”?") + " " + gone, default_no=True):
                return
            trade.merge_lists(kind, lid, to_kind, to_lid, coll)
            if self.lib.list_sel == (kind, lid):
                self.lib.list_sel = (to_kind, to_lid)
            self._undo(snap, tr(f"“{name}” → “{target}” merged"))
        self.lib.refresh(keep=True)
        self._lists_touched()

    def _undo(self, snap, text):
        """After copy/move/merge/clear: "Undo" in the lists column for 12 s."""
        self._undo_snap, self._undo_text = snap, text
        t = self.__dict__.get("_undo_t")
        if t is None:
            t = self._undo_t = QtCore.QTimer(self, singleShot=True, interval=12000)
            t.timeout.connect(lambda: (setattr(self, "_undo_text", ""), self.changed.emit()))
        t.start()

    @QtCore.Property(str, notify=changed)
    def undoText(self):
        return self.__dict__.get("_undo_text", "")

    @QtCore.Slot()
    def undo(self):
        from collection import trade
        snap = self.__dict__.get("_undo_snap")
        if snap is None:
            return
        trade.restore_lists(snap, self.ctrl.collection)
        self._undo_snap, self._undo_text = None, ""
        sel = self.lib.list_sel
        if sel is not None and trade.kind_of(sel[1]) is None:
            self.lib.list_sel = None
        self.lib.refresh(keep=True)
        self._lists_touched()

    @QtCore.Property(str, notify=changed)
    def listName(self):
        sel = self.lib.list_sel
        if sel is None:
            return ""
        from collection import trade
        x = next((x for x in trade.lists(sel[0]) if x["id"] == sel[1]), None)
        return "" if x is None else (tr(x["name"]) if x["id"] in (trade.MAIN_WISH, trade.MAIN_HAVE) else x["name"])

    @QtCore.Slot(str, str)
    def pickList(self, kind, lid):
        self.lib.pick_list(kind, lid)
        self.changed.emit()

    @QtCore.Slot(str, str, bool)
    def setShared(self, kind, lid, on):
        """The "private" / "shared" chip on the list was clicked."""
        from collection import trade
        trade.set_shared(kind, lid, on)
        self.changed.emit()
        if hasattr(self.ctrl, "relay_auto_lists"):
            self.ctrl.relay_auto_lists()

    @QtCore.Slot(str, str, bool, result=str)
    def newListNamed(self, kind, name, shared):
        """List for the open game from the name field of the list bar – at the top of its section. -> its id."""
        from collection import trade
        if not (name or "").strip():
            return ""
        lid = trade.add_list(kind, name.strip(), shared=shared, top=True)
        self.changed.emit()
        return lid

    def _new_have_list(self):
        """New trade list: fill it by hand – or automatically from the current search (e.g. "Price from 100 €"),
        then it keeps itself up to date. Keep: X copies per card, exclude cards in decks."""
        import json as _json
        from ui import qdialogs
        from collection import trade
        f, text = self.lib.filters()
        f = {k: v for k, v in f.items() if k not in ("owned", "only_ids", "exclude_ids")}
        has_search = bool(text or any(v for v in f.values()))
        chips = ", ".join(t for g in self.lib.bar.chips_data for t, *_ in g.get("values") or [] if t)[:160]
        st = {"name": "", "auto": has_search, "keep": 0, "no_decks": True}

        def build(ui, d):
            rows = [(tr("Name"), ui.edit("", lambda t: st.update(name=t), live=lambda t: st.update(name=t),
                                         key="nl_name", placeholder=tr("e.g. Duplicates, Over €100, For Max")))]
            items = [ui.form(rows),
                     ui.check(tr("Automatic: all owned cards of the current search"), st["auto"],
                              lambda v: (st.update(auto=bool(v)), d.refresh()), enabled=has_search)]
            if not has_search:
                items.append(ui.note(tr("For an automatic list, first search or filter in the library (e.g. advanced search → Values → price from €100).")))
            elif st["auto"]:
                items += [ui.note(tr("Search: ") + (text + " · " if text else "") + (chips or tr("Filters"))),
                          ui.form([(tr("Keep per card"), ui.spin(st["keep"], 0, 99, lambda v: st.update(keep=v),
                                                                     suffix=tr(" pcs")))]),
                          ui.check(tr("Don't give away cards from my decks"), st["no_decks"],
                                   lambda v: st.update(no_decks=bool(v))),
                          ui.note(tr("The list keeps itself up to date: new matching cards are added, sold or traded ones drop out."))]
            items.append(ui.row([ui.stretch(), ui.button(tr("Cancel"), lambda: d.close(None)),
                                 ui.button(tr("Create"), lambda: d.close("ok"), active=True)]))
            return ui.col(items, spacing=10)
        if qdialogs.show(tr("New trade list"), build) != "ok" or not st["name"].strip():
            return
        rule = None
        if st["auto"] and has_search:
            rule = {"filters": _json.loads(_json.dumps(f, default=list)), "text": text, "keep": int(st["keep"]),
                    "no_decks": bool(st["no_decks"])}
        trade.add_list("have", st["name"].strip(), rule=rule)
        self.changed.emit()

    @QtCore.Slot(str, str)
    def renameList(self, kind, lid):
        """Menu "Rename": no dialog – the name becomes a field right where it stands (review .101)."""
        self.renameAsked.emit(kind, lid)

    @QtCore.Slot(str, str, str, result=bool)
    def renameListTo(self, kind, lid, name):
        from collection import trade
        if not name.strip() or not any(x["id"] == lid for x in trade.lists(kind)):
            return False
        trade.rename_list(kind, lid, name.strip())
        self.changed.emit()
        return True

    @QtCore.Slot(str, str)
    def deleteList(self, kind, lid):
        from ui import qdialogs
        from collection import trade
        x = next((x for x in trade.lists(kind) if x["id"] == lid), None)
        if x is None:
            return
        main = lid in (trade.MAIN_WISH, trade.MAIN_HAVE)
        name = tr(x["name"]) if main else x["name"]
        text = (tr(f"Delete “{name}”? Your copies stay in the collection – they are just no longer marked for trade.")
                if lid == trade.MAIN_HAVE else tr(f"Delete “{name}”? The cards in your collection stay."))
        if not qdialogs.question(tr("Delete list"), text, danger=True):
            return
        trade.remove_list(kind, lid, self.ctrl.collection if main else None)
        if self.lib.list_sel == (kind, lid):
            self.lib.pick_list(kind, lid)  # filters off
        self.changed.emit()

    @QtCore.Property(int, notify=changed)
    def completionWidth(self):
        return int(self.ctrl.settings.get("lib_completion_w") or detail_width())

    @QtCore.Property(float, notify=changed)
    def sideSplit(self):
        """Set completion + lists open: share of the upper pane."""
        return float(self.ctrl.settings.get("lib_side_split") or 0.5)

    @QtCore.Slot(float)
    def setSideSplit(self, f):
        self.ctrl.settings["lib_side_split"] = round(max(0.1, min(0.9, float(f))), 4)
        self.ctrl.settings_changed()
        self.changed.emit()

    @QtCore.Slot(int)
    def setCompletionWidth(self, w):
        self.ctrl.settings["lib_completion_w"] = int(w)
        self.ctrl.settings_changed()
        self.changed.emit()

    # ---------- Detail / compare ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def detail(self):
        return self.detail_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def compare(self):
        return self.compare_b

    @QtCore.Property(bool, notify=changed)
    def detailOpen(self):
        return bool(self.lib.detail_open)

    @QtCore.Property(bool, notify=changed)
    def compareOpen(self):
        return bool(self.lib.detail_open and not self.lib.compare.isHidden() and not self.lib.slide.closing)

    @QtCore.Property(int, notify=changed)
    def currentRow(self):
        return self.lib.current if self.lib.detail_open else -1

    @QtCore.Property(int, notify=changed)
    def detailWidth(self):
        return int(detail_width(self.ctrl.settings.get(self.width_key)))

    @QtCore.Slot(int)
    def setDetailWidth(self, w):
        self.ctrl.settings[self.width_key] = int(w)
        self.ctrl.settings_changed()
        self.changed.emit()

    @QtCore.Slot()
    def escape(self):
        if self.compareOpen:
            self.lib.close_compare(animate=False)
        elif self.lib.detail_open:
            self.lib.close_detail()
        self.changed.emit()

    # ---------- Grid ----------
    def _sync(self, append):
        self.disp = display(self.ctrl.settings)
        new_search = not append and getattr(self.lib, "appear_t0", None) is not None
        self.grid.sync(self.lib.model.rows, append)
        self.refreshed.emit(bool(new_search))
        self.changed.emit()

    @QtCore.Property(QtCore.QObject, constant=True)
    def model(self):
        return self.grid

    @QtCore.Slot(int)
    def open(self, i):
        """Card clicked -> detail view (Library logic; rendering follows in QML)."""
        if 0 <= i < self.lib.model.rowCount():
            self.lib.show_detail(i)
            self.changed.emit()

    @QtCore.Slot()
    def fetchMore(self):
        self.lib.fetch_more()

    @QtCore.Slot(int)
    def setViewRows(self, n):
        """How many rows the grid shows – "All cards" loads those and one more row at a time."""
        self.lib.view_rows = max(1, int(n))

    @QtCore.Slot(int)
    def viewTop(self, i):
        """Grid scrolled: preload images starting from the first visible card."""
        if i >= 0:
            quickimages.prioritize(i)

    # ---------- Header row ----------
    @QtCore.Property(str, notify=changed)
    def mode(self):
        return self.lib.mode

    @QtCore.Slot(str)
    def setMode(self, mode):
        self.lib.set_mode(mode)
        self.changed.emit()

    @QtCore.Property(bool, notify=changed)
    def altOnly(self):
        """My Collection with "alt-arts only" (Advanced search → Display) – the friendly sentence when it is empty."""
        return self.lib.alt_view()

    @QtCore.Property(str, notify=changed)
    def searchHint(self):
        """Placeholder of the search field – the syntax example of the open game (searchbox.search_placeholder)."""
        from ui.searchbox import search_placeholder
        return search_placeholder()

    @QtCore.Property(str, notify=changed)
    def searchText(self):
        return self.lib.search.text()

    @QtCore.Slot(str)
    def setSearch(self, text):
        if text != self.lib.search.text():
            self.lib.search.setText(text)
            self.lib.bar.timer.start()  # batched like when typing

    @QtCore.Slot()
    def commitSearch(self):
        self.lib.bar.commit_syntax()
        self.changed.emit()

    @QtCore.Property("QVariantList", constant=True)
    def sorts(self):
        return [{"key": k, "text": tr("Sortierung: " + t), "desc": tr(SORT_DESC[k])} for k, t in SORTS]

    @QtCore.Property(str, notify=changed)
    def sort(self):
        return self.lib.sort.currentData() or "relevance"

    @QtCore.Slot(str)
    def setSort(self, key):
        rev = self.lib.sort_reverse()
        self.lib.sort_dir = None  # new sorting: in its natural direction
        i = self.lib.sort.findData(key)
        if i >= 0 and i != self.lib.sort.currentIndex():
            self.lib.sort.setCurrentIndex(i)  # searches again
        elif rev:
            self.lib.refresh()  # the same one, but reversed before
        self.changed.emit()

    @QtCore.Property(str, notify=changed)
    def sortDir(self):
        return self.lib.sort_dir or SORT_NATURAL.get(self.sort, "asc")

    @QtCore.Property(bool, notify=changed)
    def sortReversed(self):
        """Arrow on the sort button: ↓ = normal order of the sorting, ↑ = reversed."""
        return bool(self.lib.sort_reverse())

    @QtCore.Slot()
    def toggleSortDir(self):
        nat = SORT_NATURAL.get(self.sort, "asc")
        self.lib.sort_dir = None if self.lib.sort_reverse() else ("asc" if nat == "desc" else "desc")
        self.lib.refresh()
        self.changed.emit()

    @QtCore.Slot(str, str)
    def setSortDir(self, key, d):
        """▲/▼ on an entry of the selection list: this sorting in this direction."""
        self.lib.sort_dir = d
        i = self.lib.sort.findData(key)
        if i >= 0 and i != self.lib.sort.currentIndex():
            self.lib.sort.setCurrentIndex(i)  # searches again
        else:
            self.lib.refresh()
        self.changed.emit()

    @QtCore.Property(int, notify=changed)
    def columns(self):
        return int(self.lib.columns())

    @QtCore.Property(int, notify=changed)
    def colMin(self):
        return self.lib.START[self.lib.area()]

    @QtCore.Property(int, notify=changed)
    def colMax(self):
        return self.lib.col_hi(self.lib.area())

    @QtCore.Slot(int)
    def setColumns(self, n):
        self.lib.cols_slider.set_value(int(n), emit=False)
        self.lib.set_columns(int(n))
        self.changed.emit()

    @QtCore.Property(str, notify=changed)
    def status(self):
        return self.lib.status.text()

    @QtCore.Property(bool, notify=changed)
    def hasDb(self):
        return carddb.exists()

    @QtCore.Property(bool, notify=changed)
    def emptyCollection(self):
        return not self.lib.coll.items

    # ---------- Extra chips (trade) and friends' card backs ----------
    @QtCore.Property("QVariantList", notify=changed)
    def extraChips(self):
        btns = getattr(self.lib, "chip_btns", None) or {}
        out = [{"key": k, "text": label, "on": k in self.lib.chip_on}
               for k, label, _ in getattr(self.lib, "chip_defs", []) if k in btns]
        return out

    LIST_ICONS = {"wish": "star", "have": "trade", "custom": "bookmark"}

    @QtCore.Property("QVariant", notify=changed)
    def listChip(self):
        """Bright chip at the front of the chip bar: the selected list (or None)."""
        if not (self.main and self.lib.list_sel is not None):
            return None
        return {"icon": self.LIST_ICONS.get(self.lib.list_sel[0], "lists"), "text": self.listName}

    @QtCore.Slot()
    def clearList(self):
        if self.lib.list_sel is not None:
            self.lib.pick_list(*self.lib.list_sel)
            self.changed.emit()

    # ---------- Editing the picked list right here (Oliver, review .62 – no detour via Trade) ----------
    def _cur(self):
        return self.lib.current_row() if self.lib.detail_open else None

    @QtCore.Property("QVariant", notify=changed)
    def listBar(self):
        """Tool row above the grid while a list is picked: name, total, private|shared, alert, the selected card's
        quantity on the list – or None."""
        if not (self.main and self.lib.list_sel is not None):
            return None
        from collection import alarms, trade
        kind, lid = self.lib.list_sel
        x = next((x for x in trade.lists(kind) if x["id"] == lid), None)
        if x is None:
            return None
        if kind == "have":
            total = sum(trade.have_counts(lid).values()) if lid != trade.MAIN_HAVE else sum(
                min(int(it.get("trade") or 0), int(it.get("count", 1))) for it in self.ctrl.collection.items)
        else:
            total = sum(int(w.get("count", 1)) for w in trade.wishes([lid]))
        cur = self._cur()
        key = self.lib.list_entry(cur) if cur is not None else None
        pinned = bool(key) and kind in ("wish", "custom") and bool(key.split("|")[1])   # name|set|number…
        # trade lists: one more only while an own copy has room (never offer more than you have)
        more = not (kind == "have" and key and cur is not None and not any(
            trade.have_count(it, lid) < int(it.get("count", 1)) for it in cur.get("items") or []))
        # cards on the list that search or filters hide – otherwise "13 on the list" and the tiles don't add up
        shown = sum(int(r.get("count") or 0) for r in self.lib.model.rows)
        hidden = 0 if self.lib.list_add or self.lib.more else max(0, total - shown)
        return {"hidden": hidden, "kind": kind, "lid": lid, "name": self.listName, "total": total,
                "main": lid in (trade.MAIN_WISH, trade.MAIN_HAVE), "auto": bool(x.get("rule")),
                "shareable": kind in trade.SHAREABLE and not x.get("example"), "shared": trade.is_shared(x),
                "alarm": alarms.find_list(self.ctrl.settings, lid) is not None, "adding": self.lib.list_add,
                "card": cur["name"] if cur is not None else "", "n": int(cur.get("count") or 0) if key else 0,
                "inList": key is not None, "pinnable": bool(key) and kind in ("wish", "custom"), "pinned": pinned,
                "more": more}

    @QtCore.Slot()
    def listPin(self):
        """Pin in the list's tool row: the selected card's wish to exactly this print – or back to any version."""
        from collection import trade
        cur = self._cur()
        if not (self.main and self.lib.list_sel is not None and cur is not None):
            return
        kind, lid = self.lib.list_sel
        key = self.lib.list_entry(cur)
        if not key or kind not in ("wish", "custom"):
            return
        if key.split("|")[1]:
            trade.set_pinned(key, lid, False)
            msg = tr(f"“{cur['name']}”: any version")
        else:
            trade.set_pinned(key, lid, True, str(cur.get("set") or "").lower(), str(cur.get("number") or ""))
            msg = tr(f"“{cur['name']}”: exactly this printing")
        if getattr(self.ctrl, "shell", None):
            self.ctrl.shell.show_toast(msg)
        self._lists_touched(kind, lid)

    @QtCore.Slot(str, str, str)
    def pinEntry(self, kind, lid, key):
        """Pin on a card in the lists column (review .101, like in the Orbit tab): exactly this print ↔ any version.
        "Any version" gets pinned to the print the library shows for it – the cheapest playable one."""
        from collection import trade
        if kind not in ("wish", "custom"):
            return
        name, sc = key.split("|")[:2]
        if sc:
            trade.set_pinned(key, lid, False)
            msg = tr(f"“{name}”: any version")
        else:
            cid = carddb.cheapest_ids_for_names([name]).get(name.lower()) if carddb.exists() else None
            row = carddb.cards_by_ids([cid]).get(cid) if cid else None
            if row is None:
                return
            trade.set_pinned(key, lid, True, str(row.get("set_code") or "").lower(), str(row.get("number") or ""))
            msg = tr(f"“{name}”: exactly this printing")
        if getattr(self.ctrl, "shell", None):
            self.ctrl.shell.show_toast(msg)
        self._lists_touched(kind, lid)

    @QtCore.Slot()
    def clearFilters(self):
        """"Clear all filters" in the list's tool row (with ↺ in the chip bar, like there)."""
        self.lib.bar._clear_with_undo()
        self.changed.emit()

    @QtCore.Slot(int)
    def listStep(self, delta):
        """−/+ for the selected card on the picked list (0 = take it off the list)."""
        from collection import trade
        cur, sel = self._cur(), self.lib.list_sel
        if cur is None or sel is None:
            return
        if delta > 0 and self.lib.list_entry(cur) is None:   # not on it yet: this exact print
            self.dropOnList(self.lib.current, *sel)
            return
        key = self.lib.list_entry(cur)
        if key is None:
            return
        if sel[0] == "have" and delta > 0:   # trade list: the next own copy with room
            its = [it for it in cur.get("items") or [] if trade.have_count(it, sel[1]) < int(it.get("count", 1))]
            if not its:
                return
            key = its[0]["uid"]
        trade.change_entry(sel[0], sel[1], key, None if delta == 0 else delta, self.ctrl.collection)
        self._lists_touched(*sel)

    @QtCore.Slot(bool)
    def listAdding(self, on):
        """"+ Search cards": the list filter rests, search and click a card, "+" puts it on the list; "Done" shows the
        list again."""
        if self.lib.list_sel is None:
            return
        self.lib.list_add = bool(on)
        kind, lid = self.lib.list_sel
        want = "all" if on else ("mine" if kind == "have" or (kind == "custom" and self.lib._list_owned(lid)) else "all")
        if self.lib.mode != want and (want == "mine" or carddb.exists()):
            self.lib.set_mode(want)
        else:
            self.lib.refresh()
        self.changed.emit()

    @QtCore.Slot()
    def listAlarm(self):
        """Bell in the tool row: the list's price alert lives in Trade → Price alerts – open its editor there."""
        sel = self.lib.list_sel
        tb = getattr(getattr(self.ctrl, "shell", None), "backends", {}).get("trade")
        if sel is None or tb is None:
            return
        self.ctrl.stream.show_page("trade", back=True)
        tb.alarms_b.listAlarm(*sel)

    @QtCore.Slot(str)
    def toggleExtra(self, key):
        if key in (getattr(self.lib, "chip_btns", None) or {}):
            self.lib._chip(key, key not in self.lib.chip_on)
            self.changed.emit()

    def holders_changed(self):
        if self.grid.rows:
            self.grid.dataChanged.emit(self.grid.index(0), self.grid.index(len(self.grid.rows) - 1))

    def row(self, i):
        rows = self.lib.model.rows
        return rows[i] if 0 <= i < len(rows) else None

    @QtCore.Property(str, constant=True)
    def syntaxHelp(self):
        from ui.searchbox import SYNTAX_HELP
        return tr(SYNTAX_HELP)

    @QtCore.Slot()
    def loadDb(self):
        self.lib.load_db()

    @QtCore.Slot()
    def openDisplay(self):
        self.ctrl.go_settings("display")

    @QtCore.Slot()
    def scanCards(self):
        self.ctrl.stream.show_page("scan", back=True)

    @QtCore.Slot()
    def importCollection(self):
        self.ctrl.show_import("collection")

    # ---------- Chips (read from the Library's search bar) ----------
    def _read_chips(self):
        """Chip boxes of the search bar -> list for QML. Clicks go back via ids to the real buttons."""
        self._chips, self._chip_fns = read_chips(self.lib.bar, self._collapsing)
        self.chipsChanged.emit()
        self.changed.emit()

    @QtCore.Property("QVariantList", notify=chipsChanged)
    def chips(self):
        return self._chips

    @QtCore.Slot(str)
    def chip(self, cid):
        fn = self._chip_fns.get(cid)
        if fn is not None:
            fn()

    def install_collapse_hook(self):
        """Formerly: tracked the hiding of the chip widgets. Today the chips, including hiding, are data in the search
        (searchbox.SearchBox.chips_data / collapsing)."""
