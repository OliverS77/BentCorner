"""Several cards at once in the Library (Oliver's backlog, review .106). Only through the "Select" button (Oliver, after
0.9.3: nothing starts a choice by itself – Ctrl/Shift+click and a frame on free space did, and a click then chose instead
of opening the card): while it is on, a click chooses a card, Shift+click a range, a frame drawn on free space (lasso)
takes everything under it, Ctrl+A everything shown (after search, filters and the Group-by node). While it is off, a
click always opens the card. "Done", ✕, Esc, another page and every action end it.

The selection is a set of row keys (not indices – a refresh re-builds the rows): the grid asks only "is this key in it"
(role "picked", ui/qlibrary.CardGridModel) and is told just the rows that changed. While something is chosen, a row
slides in above the grid: "n cards chosen · value", To list ▾ · To deck ▾ · For trade · Change ▾ · To the trash,
right All / None / ✕. In "All cards" only To list and To deck (there are no own copies there).
"""
from PySide6 import QtCore

from system.i18n import tr


class SelectBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, lib, host):
        super().__init__(host)
        self.ctrl, self.lib, self.host = ctrl, lib, host
        self.keys = set()
        self._mode = False    # "Select" button (after 0.9.2): choosing stays on, even with nothing chosen
        self._anchor = None   # the last card clicked with Ctrl (Shift extends from there)
        lib.model.reset.connect(self._rows_changed)

    # ---------- helpers ----------
    def _rows(self):
        return self.lib.model.rows

    @staticmethod
    def _key(r):
        return r.get("key") or r.get("sid")

    def chosen(self):
        """The chosen rows, in grid order."""
        return [r for r in self._rows() if self._key(r) in self.keys]

    def _set(self, keys):
        old, self.keys = self.keys, set(keys)
        self.host.grid.picked_changed(old ^ self.keys)
        self.changed.emit()

    def _rows_changed(self):
        """New rows (search, filter, node): what is no longer shown is no longer chosen."""
        if self.keys:
            shown = {self._key(r) for r in self._rows()}
            if not self.keys <= shown:
                self._set(self.keys & shown)

    def mine(self):
        return self.lib.mode in ("mine", "altart")

    # ---------- for QML ----------
    @QtCore.Property(bool, notify=changed)
    def active(self):
        return self._mode

    @QtCore.Property(bool, notify=changed)
    def choosing(self):
        """The "Select" button is on (choosing without Ctrl/Shift)."""
        return self._mode

    @QtCore.Property(int, notify=changed)
    def count(self):
        return len(self.keys)

    @QtCore.Property(bool, notify=changed)
    def ownCopies(self):
        """Own copies (My Collection, alt arts): trade, change and the trash work – in "All cards" not."""
        return self.mine()

    @QtCore.Property(str, notify=changed)
    def info(self):
        rows = self.chosen()
        if not rows:
            return tr("Click cards to choose them")
        cards = sum(int(r.get("count") or 0) for r in rows) if self.mine() else len(rows)
        value = sum(float(r.get("price") or 0) * (int(r.get("count") or 0) if self.mine() else 1) for r in rows)
        from ui.librarycore import eur
        head = tr("1 card chosen") if cards == 1 else tr(f"{cards} cards chosen")
        return head + " · " + tr("value") + " " + eur(value)

    @QtCore.Property(bool, notify=changed)
    def accent(self):
        """The frame in orange instead of the text colour – only for the comparison picture (settings "sel_orange")."""
        return bool(self.ctrl.settings.get("sel_orange"))

    @QtCore.Property(bool, notify=changed)
    def allChosen(self):
        return bool(self._rows()) and len(self.keys) >= len(self._rows())

    @QtCore.Slot(int, int)
    def click(self, i, mods):
        """While choosing: this card in or out – Shift+click: the range from the last one. Otherwise nothing (the
        click opens the card)."""
        rows = self._rows()
        if not self._mode or not 0 <= i < len(rows):
            return
        k = self._key(rows[i])
        shift = bool(mods & QtCore.Qt.ShiftModifier.value)
        if shift and self._anchor is not None:
            a = next((j for j, r in enumerate(rows) if self._key(r) == self._anchor), i)
            lo, hi = sorted((a, i))
            self._set(self.keys | {self._key(r) for r in rows[lo:hi + 1]})
            return
        self._anchor = k
        self._set(self.keys ^ {k})

    @QtCore.Slot("QVariantList", bool)
    def lasso(self, indices, add):
        """The frame on the grid: these tiles (add = the ones chosen before stay, Ctrl held)."""
        if not self._mode:
            return
        rows = self._rows()
        ks = {self._key(rows[i]) for i in indices if isinstance(i, int) and 0 <= i < len(rows)}
        self._set((self._before | ks) if add else ks)

    @QtCore.Slot()
    def lassoStart(self):
        self._before = set(self.keys)

    @QtCore.Slot()
    def all(self):
        if self._mode:
            self._set({self._key(r) for r in self._rows()})

    @QtCore.Slot()
    def none(self):
        """"None": nothing chosen – with the "Select" button on, choosing goes on."""
        self._anchor = None
        self._set(set())

    @QtCore.Slot()
    def end(self):
        """✕ / Esc / "Done" / another page / an action done: the choice ends, a click opens a card again."""
        self._mode = False
        self.none()

    @QtCore.Slot()
    def toggleChoosing(self):
        """The "Select" button between the sorting and the size slider (like the deck builder's)."""
        if self._mode:
            self.end()
        else:
            self._mode = True
            self.changed.emit()

    # ---------- what you can do with them ----------
    def _toast(self, text):
        if getattr(self.ctrl, "shell", None):
            self.ctrl.shell.show_toast(text)

    def _entries(self, rows, each=False):
        """List entries of the chosen cards – exactly these prints (own copies: all of them if each)."""
        out = []
        for r in rows:
            n = int(r.get("count") or 1) if each and self.mine() else 1
            out.append({"name": r["name"], "set": (r.get("set") or "").lower() or None, "number": r.get("number"),
                        "count": n, "lang": r.get("lang") or "en", "foil": bool(r.get("foil")), "uid": None})
        return out

    @QtCore.Slot(result="QVariantList")
    def listTargets(self):
        """"To list ▾": every wish, trade and own list – key "kind:lid"."""
        from collection import trade
        out = []
        for kind, title in (("wish", "Wishlists"), ("have", "Trade lists"), ("custom", "Own lists")):
            xs = trade.lists(kind)
            if not xs:
                continue
            out.append({"text": tr(title), "enabled": False})
            for x in xs:
                main = x["id"] in (trade.MAIN_WISH, trade.MAIN_HAVE)
                out.append({"text": tr(x["name"]) if main else x["name"], "key": f"{kind}:{x['id']}", "indent": True,
                            "enabled": not x.get("rule")})
        return out

    @QtCore.Slot(str)
    def toList(self, key):
        from collection import trade
        kind, _, lid = key.partition(":")
        rows = self.chosen()
        if not rows or not lid:
            return
        trade.put_entries(kind, lid, self._entries(rows), self.ctrl.collection)
        name = next((x["name"] for x in trade.lists(kind) if x["id"] == lid), "")
        main = lid in (trade.MAIN_WISH, trade.MAIN_HAVE)
        self._toast(tr(f"{len(rows)} cards → {tr(name) if main else name}"))
        self.host._lists_touched(kind, lid)
        self.end()   # done: the choice ends (Oliver's test of 0.9.2) – a click opens the card again

    @QtCore.Slot()
    def toTrade(self):
        """"For trade": the chosen copies onto the trade list (each copy once – all copies of a tile)."""
        from collection import trade
        rows = self.chosen()
        if not rows or not self.mine():
            return
        trade.put_entries("have", trade.MAIN_HAVE, self._entries(rows, each=True), self.ctrl.collection)
        self._toast(tr(f"{len(rows)} cards marked for trade"))
        self.host._lists_touched("have", trade.MAIN_HAVE)
        self.end()

    @QtCore.Slot(result="QVariantList")
    def deckTargets(self):
        """"To deck ▾": the decks last changed first, then a new one."""
        ds = sorted(self._decks(), key=lambda d: -float(d.get("updated") or 0))
        out = [{"text": d.get("name") or "?", "key": d["id"]} for d in ds[:30]]
        return out + ([{"sep": True}] if out else []) + [{"text": tr("New deck"), "key": "new"}]

    def _decks(self):
        from collection import decks
        page = getattr(self.ctrl, "deck_page", None)
        return page.decks if page is not None else decks.load()

    @QtCore.Slot(str)
    def toDeck(self, did):
        """"To deck ▾": the chosen cards into a deck (main deck, one each – own copies: as many as you have)."""
        from collection import decks
        rows = self.chosen()
        if not rows:
            return
        page = getattr(self.ctrl, "deck_page", None)
        all_d = page.decks if page is not None else decks.load()
        if did == "new":
            d = decks.new_deck(tr("New deck"))
            all_d.append(d)
        else:
            d = next((x for x in all_d if x["id"] == did), None)
            if d is None:
                return
        for r in rows:
            sid = r.get("sid") or (r.get("db") or {}).get("id")
            if sid:
                decks.add_card(d, sid, int(r.get("count") or 1) if self.mine() else 1)
        if page is not None:
            page.save()
        else:
            decks.save(all_d)
        self._toast(tr(f"{len(rows)} cards → {d.get('name') or ''}"))
        self.end()

    @QtCore.Slot(result="QVariantList")
    def changeTargets(self):
        """"Change ▾": condition, language, finish – for all chosen copies."""
        import games
        from cards import conditions
        from collection.collection import LANGS
        out = [{"text": tr("Condition"), "enabled": False}]
        out += [{"text": f"{short} · {tr(name)}", "key": f"cond:{k}", "indent": True}
                for k, short, name in conditions.scale(self.ctrl.settings)]
        out += [{"sep": True}, {"text": tr("Finish"), "enabled": False},
                {"text": tr("Normal"), "key": "foil:0", "indent": True},
                {"text": games.current().foil_word, "key": "foil:1", "indent": True}]
        out += [{"sep": True}, {"text": tr("Language"), "enabled": False}]
        out += [{"text": f"{short} · {name}", "key": f"lang:{code}", "indent": True} for code, short, name in LANGS]
        return out

    @QtCore.Slot(str)
    def change(self, key):
        """Write the change into every chosen copy – with .102 each one leaves its grey line in its own log."""
        what, _, v = key.partition(":")
        rows = self.chosen()
        if not rows or not self.mine():
            return
        n = 0
        for r in rows:
            for it in list(r.get("items") or []):
                if what == "cond":
                    self.ctrl.collection_change(it, cond={"cond": v})
                elif what == "foil":
                    self.ctrl.collection_change(it, foil=v == "1")
                elif what == "lang":
                    self.ctrl.collection_change(it, lang=v)
                n += 1
        self._toast(tr(f"{n} copies changed"))
        self.end()

    @QtCore.Slot()
    def trash(self):
        """"To the trash": asks only if it is serious (more than one copy) – everything comes back from the trash."""
        from system import datastore
        from ui import qdialogs
        rows = self.chosen()
        items = [it for r in rows for it in (r.get("items") or [])]
        if not items or not self.mine():
            return
        copies = sum(int(it.get("count", 1)) for it in items)
        days = datastore.TRASH_DAYS
        if copies > 1 and not qdialogs.question(
                tr("To the trash"),
                tr(f"Put {copies} copies in the trash? They stay there for {days} days and can be restored (Logs → Trash)."),
                danger=True):
            return
        name = rows[0]["name"] if len(rows) == 1 else tr(f"{len(rows)} cards")
        datastore.trash_put("cards", name, {"items": [dict(it) for it in items]})   # one entry: back as one
        coll = self.ctrl.collection
        for it in items:
            before = dict(coll.get(it["uid"]) or it)
            coll.set_count(it["uid"], 0)
            self.ctrl._manual(before, -int(before.get("count", 1)))
        self.ctrl._coll_timer.start()
        self.end()
        self._toast(tr(f"{copies} copies in the trash – restore them under Logs → Trash"))
