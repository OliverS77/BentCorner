"""Trade page – "your lists": ListsBackend, moved out of ui/qtrade.py unchanged (docs/TRADE-SPLIT.md).
In QML as tradeLists; the host (TradeBackend) keeps shared state, helpers and signals."""
from PySide6 import QtCore

from ui.qtrade import carddb, db_image, tr, trade   # shared helpers of the trade page


class ListsBackend(QtCore.QObject):
    """Part of the trade page (docs/TRADE-SPLIT.md), in QML as tradeLists (alias tl): moved from TradeBackend
    unchanged – shared state, helpers and signals stay with the host (TradeBackend)."""
    changed = QtCore.Signal()   # forwarded from TradeBackend.changed (notify of the moved properties)
    listsChanged = QtCore.Signal()   # forwarded from TradeBackend.listsChanged (notify of the moved properties)
    entriesChanged = QtCore.Signal()   # forwarded from TradeBackend.entriesChanged (notify of the moved properties)
    LIST_SORTS = (("added", "Recently added"), ("name", "Name"), ("price", "Preis"), ("set", "Set"),
                  ("count", "Anzahl"))

    def __init__(self, host):
        super().__init__(host)
        self.host, self.ctrl, self.page = host, host.ctrl, host.page
        for name in ('changed', 'listsChanged', 'entriesChanged'):   # the host's signal also refreshes the moved properties
            getattr(host, name).connect(getattr(self, name))

    @QtCore.Property(QtCore.QObject, constant=True)
    def wantsLib(self):
        return self.host.wants_b

    @QtCore.Property("QVariantList", notify=listsChanged)
    def lists(self):
        out = []
        items = self.ctrl.collection.items
        for kind, title, sub in (("wish", tr("WISHLISTS"), tr("What you're looking for – friends see it if you send it.")),
                                 ("have", tr("TRADE LISTS"), tr("Cards from your collection you'd give away.")),
                                 ("custom", tr("OWN LISTS"), tr("For everything else – binders, ideas, cards for a project. Just for you, friends don't see them."))):
            cards = []
            for x in trade.lists(kind):
                main = x["id"] in (trade.MAIN_WISH, trade.MAIN_HAVE)
                if kind in ("wish", "custom"):
                    total = sum(int(w.get("count", 1)) for w in trade.wishes([x["id"]]))
                else:
                    total = sum(k for _, k in trade.have_items(items, [x["id"]]))
                cards.append({"lid": x["id"], "name": tr(x["name"]) if main else x["name"],
                              "example": bool(x.get("example")),
                              "info": tr(f"{total} cards") + (" · " + tr("automatic") if x.get("rule") else ""),
                              "main": main})
            out.append({"kind": kind, "title": title, "sub": sub, "cards": cards,
                        "add": {"wish": tr("New wishlist"), "have": tr("New trade list")}.get(
                            kind, tr("New own list"))})
        return out

    @QtCore.Property(bool, notify=listsChanged)
    def wishDecks(self):
        return bool(self.ctrl.settings.get("wish_decks", True))

    @QtCore.Slot(bool)
    def setWishDecks(self, on):
        self.ctrl.settings.update(wish_decks=on)
        self.ctrl.settings_changed()
        self.host.listsChanged.emit()

    @QtCore.Slot(str, str)
    def openList(self, kind, lid):
        self.page.open_list(kind, lid)

    @QtCore.Slot(str, str)
    def newListNamed(self, kind, name):
        self.newListFull(kind, name, "", False)

    @QtCore.Slot(str, str, str, bool)
    def newListFull(self, kind, name, game, shared):
        """'+ New list' – name, game and private/shared come from the tile (no dialog). In the open game the list
        is open afterwards; for another game it is ready there (without switching)."""
        import games
        if not (name or "").strip():
            return
        here = not game or game == games.current().key
        lid = trade.add_list(kind, name.strip(), shared=shared, game=None if here else game)
        if here:
            self.page.open_list(kind, lid)
        else:
            self.page.toast(tr(f"“{name.strip()}” is now waiting in {games.name_of(game)}."))
        lb = self.host._lib()
        if lb is not None:
            lb.changed.emit()
        self.host.listsChanged.emit()

    @QtCore.Property("QVariantList", notify=listsChanged)
    def listGames(self):
        """Games to choose from when creating: only the ones the user has (the open one first). One = no choice."""
        import games
        cur = games.current().key
        out = [{"key": cur, "text": games.SHORT.get(cur, cur.upper()), "tip": games.name_of(cur)}]
        for key, gname, ready in games.GAMES:
            if ready and key != cur and games.mine(key).exists():
                out.append({"key": key, "text": games.SHORT.get(key, key.upper()), "tip": gname})
        return out

    @QtCore.Slot(str, str, str, bool)
    def reorderList(self, kind, src, target, after):
        """Drag a tile onto the edge of another = change the order (onto the middle = merge)."""
        trade.reorder_list(kind, src, target, after)
        self._lists_touched()

    def _lists_touched(self):
        lb = self.host._lib()
        if lb is not None:
            lb.changed.emit()
        self.host.listsChanged.emit()
        self.host.entriesChanged.emit()
        relay = getattr(self.ctrl, "relay_auto_lists", None)
        if relay is not None:   # lay out shared lists again right away (does nothing by itself without friends)
            try:
                relay()
            except Exception:  # noqa: BLE001
                pass

    @QtCore.Slot(str, str, str)
    def renameListTo(self, kind, lid, name):
        if (name or "").strip():   # the default lists too (review .101 – like in the library)
            trade.rename_list(kind, lid, name.strip())
            lb = self.host._lib()
            if lb is not None:
                lb.changed.emit()
            self.host.listsChanged.emit()

    def _list_value_art(self, kind, entries):
        """(value of the list, image of the most valuable card, artist of that image)."""
        from collection import alarms
        if not entries or not carddb.exists():
            return 0.0, "", ""
        best, value = None, 0.0
        if kind in ("wish", "custom"):
            cheap = alarms.cheapest({e["name"] for e in entries})
            for e in entries:
                pn, pf = cheap.get(e["name"], (None, None))
                pr = pn if pn is not None else (pf or 0)
                value += (pr or 0) * e["count"]
                if best is None or (pr or 0) > best[1]:
                    best = (e, pr or 0)
            row = carddb.by_names([best[0]["name"]]).get(best[0]["name"].lower()) if best else None
        else:
            from collection.collection import price as item_price, scryfall_id
            by_uid = {it["uid"]: it for it in self.ctrl.collection.items}
            sid = None
            for e in entries:
                it = by_uid.get(e.get("uid"))
                pr = (item_price(it) or 0) if it else 0
                value += pr * e["count"]
                if it is not None and (best is None or pr > best[1]):
                    best, sid = (e, pr), scryfall_id(it["id"])
            row = carddb.cards_by_ids({sid}).get(sid) if sid else None
        return value, db_image(row) if row else "", (row or {}).get("artist") or ""

    @QtCore.Slot(str, str, result="QVariantList")
    def listMenu(self, kind, lid):
        """The "⋯" menu of a list – the same as in the library, plus the price alert for the list."""
        lb = self.host._lib()
        items = list(lb.listMenu(kind, lid)) if lb is not None else []
        items[0:0] = [{"text": tr("Open"), "key": "open"}, {"text": tr("Price alert for the list …"), "key": "alarm"},
                      {"sep": True}]
        return items

    @QtCore.Slot(str, str, str)
    def listAction(self, kind, lid, key):
        if key == "open":
            self.openList(kind, lid)
            return
        if key == "alarm":
            self.host.alarms_b.listAlarm(kind, lid)
            return
        lb = self.host._lib()
        if lb is not None:
            lb.listAction(kind, lid, key)
        self.host.listsChanged.emit()

    @QtCore.Property(str, notify=entriesChanged)
    def listTitle(self):
        return self.page.list_panel.title

    @QtCore.Property(str, notify=entriesChanged)
    def listInfo(self):
        return self.page.list_panel.info

    @QtCore.Property(str, notify=entriesChanged)
    def listHint(self):
        return self.page.list_panel.hint

    @QtCore.Property("QVariantList", constant=True)
    def listSorts(self):
        return [{"key": k, "text": tr(t)} for k, t in self.LIST_SORTS]

    @QtCore.Property(str, notify=entriesChanged)
    def listSort(self):
        return (self.ctrl.settings.get("list_sort") or ["added", "desc"])[0]

    @QtCore.Property(str, notify=entriesChanged)
    def listSortDir(self):
        return (self.ctrl.settings.get("list_sort") or ["added", "desc"])[1]

    @QtCore.Slot(str)
    def setListSort(self, k):
        self.setListSortDir(k, self.host._natural(k))

    @QtCore.Property(bool, notify=entriesChanged)
    def listSortReversed(self):
        k, d = self.ctrl.settings.get("list_sort") or ["added", "desc"]
        return d != self.host._natural(k)

    @QtCore.Slot()
    def toggleListSortDir(self):
        k, d = self.ctrl.settings.get("list_sort") or ["added", "desc"]
        self.setListSortDir(k, "asc" if d == "desc" else "desc")

    @QtCore.Slot(str, str)
    def setListSortDir(self, k, d):
        self.ctrl.settings["list_sort"] = [k, d]
        self.ctrl.settings_changed()
        self.host.entriesChanged.emit()

    @QtCore.Slot()
    def backToLists(self):
        self.page.open_me()

    @QtCore.Slot(str, result="QVariantList")
    def listsOf(self, game):
        """My wishlists and own lists in a game (for "To your list …" of a card from that game)."""
        if not game:
            return []
        return [{"id": x["id"], "name": x["name"] or tr("Wishlist"), "kind": x["kind"]}
                for x in trade.game_overview(game) if x["kind"] in ("wish", "custom")]

    @QtCore.Slot(str, int, str)
    def foreignToList(self, sec, i, lid):
        """Put a card from their collection (any game) on my list of THAT game – without switching."""
        import games
        r = self.host.friends_b._foreign_row(sec, i)
        lst = next((x for x in self.listsOf(r["game"]) if x["id"] == lid), None) if r else None
        if r is None or lst is None:
            return
        trade.add_wish_in(r["game"], r["name"], r["set"] or None, r["number"] or None, list_id=lid)
        self.page.toast(tr(f"“{r['name']}” is now on “{lst['name']}” ({games.nick_of(r['game'])})"))
