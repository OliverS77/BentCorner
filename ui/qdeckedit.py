"""Deck editor in Qt Quick (qml/components/DeckEditor.qml).

The logic lives in deckcore.DeckEditor: changing the deck, saving, search (SearchBox as in the library),
alternatives, upgrades, analysis. This object passes header, search, results, detail with the deck buttons,
deck list and deck info (form from deckcore.StatsPanel, charts native) to QML and the clicks back.
Dragging between results and deck list is handled by QML itself.
"""
import re

from PySide6 import QtCore, QtGui

from ui import qcharts
from ui import qform
from ui import quickimages
from ui import qmenu
from system.i18n import tr
from ui.qlibrary import back_image, read_chips


def _mana(cost):
    from collection.deckcore import MANA
    out = []
    for sym in re.findall(r"\{([^}]+)\}", cost or ""):
        base = sym.split("/")[0]
        out.append({"s": sym if len(sym) <= 2 else sym[0], "c": MANA.get(base, "#c9c9c9")})
    return out


class DeckEditorBackend(QtCore.QObject):
    changed = QtCore.Signal()        # Header, mode, tabs, panes
    chipsChanged = QtCore.Signal()
    resultsChanged = QtCore.Signal()
    listChanged = QtCore.Signal()
    splitChanged = QtCore.Signal()   # Pane layout (upgrade view: its own)
    detailChanged = QtCore.Signal()  # Detail/comparison open, deck buttons

    def __init__(self, ctrl, page, parent=None):
        super().__init__(parent)
        self.ctrl, self.page = ctrl, page
        self.ed = ed = page.editor
        self._chips, self._chip_fns, self._collapsing = [], {}, set()
        self._soon = {}
        # Search
        from ui.qadvsearch import AdvBackend
        self.adv_b = AdvBackend(ctrl, ed.bar, self)
        bar = ed.bar
        bar.chips_changed.connect(self._read_chips)
        old_adv = bar.update_adv_btn
        bar.update_adv_btn = lambda: (old_adv(), self.later(self.changed))
        # Detail + comparison (library detail view in the deck builder)
        from ui.qdetail import DetailBackend
        self.det_b = DetailBackend(ctrl, ed.lib, ed.detail, self)
        self.cmp_b = DetailBackend(ctrl, ed.lib, ed.compare, self)
        # Deck, list, results
        ed.changed_sig.connect(lambda: self.later(self.changed))
        ed.list_changed.connect(lambda: self.later(self.listChanged))
        ed.detail_changed.connect(lambda: self.later(self.detailChanged))
        ed.results.changed.connect(lambda: (self.later(self.resultsChanged), self.later(self.changed)))
        self.resultsChanged.connect(self.splitChanged)   # Upgrade view on/off: different layout
        page.loader.ready.connect(lambda _k: (self.later(self.resultsChanged), ed.results.up_model.refresh_images()
                                              if ed.results.up_view else None))
        # Deck info: form from the data (deckcore.StatsPanel)
        self.stats_m = qform.Form(self._build_stats, self)
        ed.stats.listeners.append(lambda: self.stats_m.soon() if self.ed.tab == 1 else None)
        self._tick = QtCore.QTimer(self, interval=700, timeout=self._refresh_stats)
        self._read_chips()

    def _build_stats(self, ui):
        st = self.ed.stats

        def chart(obj):
            return ui.chart(qcharts.spec(obj), lambda v, o=obj: qcharts.act(o, v))

        def tile(title, items):   # heading with a divider – the charts around have no frames either
            return ui.group(title, [x for x in items if x], flat=True)
        tokens = [ui.row([ui.label(name, tip=tr("by: ") + ", ".join(src)),
                          ui.label(", ".join(src[:2]) + (" …" if len(src) > 2 else ""), color="gray", px=11),
                          ui.button("−", lambda n=name: st.bump_token(n, -1)),
                          ui.label(str(st.token_count(name)), bold=True, px=15, fixed=True),
                          ui.button("+", lambda n=name: st.bump_token(n, +1))]) for name, src in st.tokens]
        from ui import qtesting
        chances = qtesting.chance_items(ui, self.ed.deck) if self.ed.deck else None
        return ui.col([
            chart(st.kpis), chart(st.kpis2),
            ui.group("", [ui.label(st.bracket_html, rich=True)], flat=True) if st.bracket_html else None,
            tile(tr("Combos (Commander Spellbook)"), [ui.label(st.combo_html, rich=True)]) if st.combo_shown else None,
            ui.row([chart(st.curve), chart(st.colors)], spacing=12),
            ui.row([chart(st.types), chart(st.roles)], spacing=12),
            tile(tr("What counts where?"), [ui.label(st.roles_html, rich=True)]),
            tile(tr("Tokens"), tokens or [ui.note(tr("No cards that create tokens."))])
            if "tokens" in __import__("games").current().deck_extras else None,
            tile(tr("Chances"), chances) if chances else None,   # moved here from "Play" (Oliver, review .72)
            tile(tr("Hinweise"), [ui.label(st.warn_html, rich=True)]),
            tile(tr("Missing from collection"), [ui.label(st.missing_html, rich=True)]) if st.missing_html else None,
        ], spacing=12)

    def later(self, sig):
        """Emit the signal batched at the end of the event loop."""
        key = id(sig)
        t = self._soon.get(key)
        if t is None:
            t = self._soon[key] = QtCore.QTimer(self, singleShot=True, interval=0, timeout=sig.emit)
        if not t.isActive():
            t.start()

    def _refresh_stats(self):
        if self.ed.tab == 1:
            self.stats_m.refresh()

    @QtCore.Slot(bool)
    def setActive(self, on):
        self._tick.start() if on else self._tick.stop()

    # ---------- Header ----------
    @QtCore.Property(str, notify=changed)
    def name(self):
        return self.ed.deck["name"] if self.ed.deck else ""

    @QtCore.Slot(str)
    def setName(self, t):
        self.ed.rename(t)

    @QtCore.Property("QVariantList", constant=True)
    def formats(self):
        from collection import decks
        return [{"key": k, "text": tr(label)} for k, label in decks.FORMATS]

    @QtCore.Property(str, notify=changed)
    def format(self):
        return self.ed.format or ""

    @QtCore.Slot(str)
    def setFormat(self, key):
        if key != self.ed.format:
            self.ed.set_format(key)

    @QtCore.Property(str, notify=changed)
    def summary(self):
        return self.ed.summary

    @QtCore.Property(str, notify=changed)
    def summaryTip(self):
        return self.ed.summary_tip

    # ---------- Missing cards → list ----------
    def _missing(self):
        """{name: missing count} of the open deck (every version counts as owned)."""
        from collection import trade
        ed = self.ed
        if ed.deck is None:
            return {}
        need = trade.deck_needs([ed.deck], ed.rows, getattr(self.page, "owned_name", {}) or {})
        return {name: e["missing"] for name, e in need.items() if e["missing"] > 0}

    @QtCore.Property(int, notify=changed)
    def missingCount(self):
        return sum(self._missing().values())

    @QtCore.Slot(result="QVariantList")
    def missingTargets(self):
        """Wish lists and own lists, plus "New list" (then called "Missing: deck name", can be renamed later)."""
        from collection import trade
        out = [{"text": tr(f"{self.missingCount} missing cards to …"), "enabled": False}]
        for kind, head in (("wish", tr("Wishlists")), ("custom", tr("Own lists"))):
            lst = trade.lists(kind)
            if not lst:
                continue
            out.append({"text": head, "enabled": False})
            for x in lst:
                main = x["id"] in (trade.MAIN_WISH, trade.MAIN_HAVE)
                out.append({"text": tr(x["name"]) if main else x["name"], "key": f"{kind}:{x['id']}", "indent": True})
        out += [{"sep": True}, {"text": tr("New wishlist “Missing: …”"), "key": "new"}]
        return out

    @QtCore.Slot(str)
    def missingTo(self, key):
        from collection import trade
        miss = self._missing()
        if not miss:
            return
        if key == "new":
            kind, lid = "wish", trade.add_list("wish", tr(f"Missing: {self.ed.name or 'Deck'}")[:60])
        else:
            kind, lid = key.split(":", 1)
        entries = [{"name": n, "set": None, "number": None, "count": c, "lang": "en", "foil": False, "uid": None}
                   for n, c in sorted(miss.items())]
        trade.put_entries(kind, lid, entries, self.ctrl.collection)
        name = next((x["name"] for x in trade.lists(kind) if x["id"] == lid), "")
        shell = getattr(self.ctrl, "shell", None)
        if shell is not None:
            shell.show_toast(tr(f"{sum(miss.values())} cards → “{tr(name)}”"))
        page = getattr(self.ctrl, "trade_page", None)
        if page is not None:
            page.fill_wishes()

    @QtCore.Property(QtCore.QObject, constant=True)
    def listsLib(self):
        """The library's lists column – the same lists, here in the deck builder too."""
        shell = getattr(self.ctrl, "shell", None)
        return shell.backends.get("library") if shell is not None else None

    def _row_entry(self, k, count=None):
        x = self.ed.list_rows[k] if 0 <= k < len(self.ed.list_rows) else None
        if not x or x.get("head"):
            return None
        r = x["r"]
        return {"name": r["name"], "set": (r.get("set_code") or "").lower() or None, "number": r.get("number"),
                "count": int(count if count is not None else 1), "lang": "en", "foil": False, "uid": None}

    def _put(self, kind, lid, entries):
        from collection import trade
        if not entries:
            return
        trade.put_entries(kind, lid, entries, self.ctrl.collection)
        name = next((x["name"] for x in trade.lists(kind) if x["id"] == lid), "")
        shell = getattr(self.ctrl, "shell", None)
        if shell is not None:
            n = sum(e["count"] for e in entries)
            shell.show_toast(tr(f"“{entries[0]['name']}” → {tr(name)}") if len(entries) == 1
                             else tr(f"{n} cards → “{tr(name)}”"))
        lb = self.listsLib
        if lb is not None:
            lb.changed.emit()
        page = getattr(self.ctrl, "trade_page", None)
        if page is not None:
            page.fill_wishes()

    @QtCore.Slot(int, str, str)
    def rowToList(self, k, kind, lid):
        """Deck list row dragged onto a list: exactly this printing is added."""
        e = self._row_entry(k)
        if e:
            self._put(kind, lid, [e])

    @QtCore.Slot(str, "QVariantList", str)
    def rowsTo(self, key, ks, why):
        """The "→ List ▾" button: all shown rows (missing or in other decks) onto a list; key "new" = new
        wish list with a meaningful name. Missing cards are added in the missing count."""
        from collection import trade
        rows = self.ed.list_rows
        entries = []
        for k in ks:
            k = int(k)
            x = rows[k] if 0 <= k < len(rows) else None
            if not x or x.get("head"):
                continue
            e = self._row_entry(k, x.get("n") or 1)
            if e:
                # missing (and not pinned): any version will do
                if (why == "missing" or (why == "both" and x.get("own") == "✗")) and not x.get("pinned"):
                    e["set"] = e["number"] = None
                entries.append(e)
        if not entries:
            return
        if key == "new":
            title = tr(f"Missing: {self.ed.name or 'Deck'}") if why == "missing" else tr(f"For {self.ed.name or 'Deck'}")
            kind, lid = "wish", trade.add_list("wish", title[:60])
        else:
            kind, lid = key.split(":", 1)
        self._put(kind, lid, entries)

    @QtCore.Property(bool, notify=changed)
    def dirty(self):
        return bool(self.ed.dirty)

    @QtCore.Property(bool, notify=changed)
    def built(self):
        return bool(self.ed.built)

    @QtCore.Slot()
    def toggleBuilt(self):
        on = not self.ed.built
        self.ed.built = on
        self.page.set_built(self.ed.orig or self.ed.deck, on)
        self.changed.emit()

    @QtCore.Slot()
    def save(self):
        self.ed.save_deck()
        self.changed.emit()

    @QtCore.Slot()
    def discard(self):
        self.ed.discard()

    @QtCore.Slot()
    def back(self):
        self.page.show_overview()

    @QtCore.Slot()
    def exportMenu(self):
        ed = self.ed
        m = qmenu.Menu()
        m.addAction(tr("To clipboard (Moxfield/Arena text)"), ed.export_clipboard)
        m.addAction(tr("Share as image …"), lambda: ed._to_export("share_decks"))
        m.addAction(tr("More options (Import/Export) …"), lambda: ed._to_export("deck_export"))
        m.sheet(tr("Export"))   # a page in the window, not a list at the mouse

    @QtCore.Slot()
    def versionsMenu(self):
        ed = self.ed
        if ed.deck is None:
            return
        m = qmenu.Menu()
        m.addAction(tr("Save changes as a new version (original stays)") if ed.dirty
                    else tr("Duplicate as new version"), ed.save_as_version)
        m.addAction(tr("Compare with …"), lambda: self.page.compare_with(ed.deck))
        self.page.folder_submenu(m, ed.orig or ed.deck)
        m.sheet(tr("Versions"))

    @QtCore.Slot()
    def deleteDeck(self):
        self.ed.delete()

    # ---------- Search ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def adv(self):
        return self.adv_b

    @QtCore.Property(str, notify=changed)
    def searchText(self):
        return self.ed.bar.search.text()

    @QtCore.Slot(str)
    def setSearch(self, t):
        bar = self.ed.bar
        if t != bar.search.text():
            bar.search.setText(t)
            bar.timer.start()

    @QtCore.Slot()
    def commitSearch(self):
        self.ed.bar.commit_syntax()

    @QtCore.Property(str, notify=changed)
    def placeholder(self):
        return self.ed.bar.search.placeholderText()

    @QtCore.Property("QVariantList", constant=True)
    def sorts(self):
        return [{"key": data, "text": label} for label, data in self.ed.sort.items]

    @QtCore.Property(str, notify=changed)
    def sort(self):
        return self.ed.sort.currentData() or "auto"

    @QtCore.Slot(str)
    def setSort(self, key):
        i = self.ed.sort.findData(key)
        if i >= 0:
            self.ed.sort.setCurrentIndex(i)
        self.changed.emit()

    @QtCore.Property(bool, notify=changed)
    def sortReversed(self):
        return bool(getattr(self.ed, "sort_rev", False))

    @QtCore.Slot()
    def toggleSortDir(self):
        """Arrow on the sort button: reverse the order (↓ normal, ↑ reversed)."""
        self.ed.sort_rev = not getattr(self.ed, "sort_rev", False)
        self.ed.results.run()
        self.changed.emit()

    @QtCore.Property(str, notify=changed)
    def mode(self):
        return self.ed.mode

    @QtCore.Slot(str)
    def setMode(self, m):
        self.ed.set_mode(m)
        self.changed.emit()

    @QtCore.Property(int, notify=detailChanged)
    def columns(self):
        return int(self.ed.columns())

    @QtCore.Property(int, notify=detailChanged)
    def colMin(self):
        return self.ed.START[self.ed.area()]

    @QtCore.Slot(int)
    def setColumns(self, n):
        self.ed.set_columns(int(n))
        self.detailChanged.emit()

    def _read_chips(self):
        self._chips, self._chip_fns = read_chips(self.ed.bar, self._collapsing)
        self.chipsChanged.emit()

    @QtCore.Property("QVariantList", notify=chipsChanged)
    def chips(self):
        """Search chips – plus the deck list filters as their own group "Deck list" (click = filter off)."""
        lf = self.__dict__.get("_lf") or set()
        if not lf:
            return self._chips
        texts = {"missing": "✗  " + tr("fehlen"), "inuse": "⚑  " + tr("in other decks")}
        vals = [{"cid": "dl:" + k, "text": texts[k], "kind": "", "neg": False, "collapsing": False}
                for k in ("missing", "inuse") if k in lf]
        return list(self._chips) + [{"id": "dl", "key": "Deckliste|", "title": tr("Deck list"), "values": vals,
                                     "titleId": "", "coverId": "dl:all", "grey": False, "clear": False,
                                     "collapsing": False}]

    @QtCore.Slot(str)
    def chip(self, cid):
        if cid.startswith("dl:"):
            lf = self.__dict__.setdefault("_lf", set())
            if cid == "dl:all":
                lf.clear()
            else:
                lf.discard(cid[3:])
            self.chipsChanged.emit()
            return
        fn = self._chip_fns.get(cid)
        if fn is not None:
            fn()

    @QtCore.Property("QVariantList", notify=chipsChanged)
    def listFilter(self):
        return sorted(self.__dict__.get("_lf") or set())

    @QtCore.Slot(str)
    def toggleListFilter(self, k):
        """Filter the deck list: missing / in other decks (both at once = both). "missing" on: search all cards –
        you don't own the missing ones, after all."""
        lf = self.__dict__.setdefault("_lf", set())
        if k in lf:
            lf.discard(k)
        else:
            lf.add(k)
            if k == "missing" and self.ed.mode != "all":
                self.setMode("all")
        self.chipsChanged.emit()

    # Alternatives
    @QtCore.Property(bool, notify=changed)
    def altOpen(self):
        return self.ed.alt is not None

    @QtCore.Property(str, notify=changed)
    def altLabel(self):
        return (tr("Which alternatives?") + f" <span style='color:#6c7390'>"
                f"({tr("none selected = all, several = all must match")})</span>") if self.ed.alt else ""

    @QtCore.Property("QVariantList", notify=changed)
    def altKinds(self):
        from cards import alternatives
        return [{"key": k, "text": tr(label), "on": k in self.ed.alt_kinds, "tip": tr(alternatives.KIND_HELP[k])}
                for k, label in alternatives.KINDS]

    @QtCore.Property("QVariantList", constant=True)
    def altOwnedOptions(self):
        return [{"key": "mine", "text": tr("In my collection")}, {"key": "missing", "text": tr("Don't have")},
                {"key": "all", "text": tr("All cards")}]

    @QtCore.Property(str, notify=changed)
    def altOwned(self):
        return self.ed.alt_owned

    @QtCore.Slot(str)
    def setAltOwned(self, key):
        self.ed.set_alt_owned(key)

    # Autocomplete
    @QtCore.Slot(str, result="QVariantList")
    def suggestNames(self, text):
        return self.ed.suggest_names(text)

    @QtCore.Slot(str)
    def pickName(self, name):
        self.ed.pick_name(name)

    @QtCore.Slot(str)
    def toggleAltKind(self, key):
        self.ed.toggle_alt_kind(key)
        self.changed.emit()

    # ---------- Results ----------
    @QtCore.Property(str, notify=resultsChanged)
    def hint(self):
        return self.ed.results.hint

    @QtCore.Property(bool, notify=resultsChanged)
    def subset(self):
        return bool(self.ed.results.subset)

    @QtCore.Slot()
    def backToSearch(self):
        self.ed.results.run()

    @QtCore.Property("QVariantList", notify=resultsChanged)
    def results(self):
        from collection.deckcore import eur, usage_chips
        from ui.librarycore import chip_texts, display
        ed, page = self.ed, self.page
        disp = display(self.ctrl.settings)
        variants = getattr(page, "owned_variants", {})
        hold_all = self.ctrl.trade_holders() if hasattr(self.ctrl, "trade_holders") else {}
        here = (ed.orig or ed.deck or {}).get("name")
        out = []
        for i, r in enumerate(ed.results.rows):
            var = variants.get(r["name"]) or []
            price = r.get("eur") if r.get("eur") is not None else r.get("eur_foil")
            hold = hold_all.get(r["name"]) or []
            out.append({"i": i, "sid": r["id"], "name": r["name"], "price": eur(price) if price is not None else "–",
                        "img": self._img(r), "inDeck": ed.deck_count(r["name"]), "why": r.get("_why") or "",
                        "chips": chip_texts({"variants": var, "count": sum(v[0] for v in var)}, disp, "mine")
                        if var else [],
                        "holders": [{"img": back_image(h[2]), "tip": f"{h[1]} ({h[3]}×)"} for h in hold[:4]],
                        "decks": usage_chips(self.ctrl, r, exclude=here)})
        return out

    def _img(self, r):
        from cards import library
        from ui.librarycore import THUMBS
        local = THUMBS / f"{r['id']}_en_n.jpg"
        url = r.get("img_normal") or library.image_url(r["set_code"], r["number"], "en", "normal")
        return quickimages.register(f"{r['id']}_en_n", local, url, local)

    def _row(self, i):
        rows = self.ed.results.rows
        return rows[i] if 0 <= i < len(rows) else None

    @QtCore.Slot(int)
    def showResult(self, i):
        r = self._row(i)
        if r is not None:
            self.ed.show_card(r)

    @QtCore.Slot(int)
    def addResult(self, i):
        r = self._row(i)
        if r is not None:
            self.ed.add(r)

    @QtCore.Slot(int)
    def removeResult(self, i):
        r = self._row(i)
        if r is not None:
            self.ed.remove_one(r)

    @QtCore.Slot(int, str)
    def dropResult(self, i, board):
        """Result dragged into the deck list (board: row it was dropped on)."""
        r = self._row(i)
        if r is not None:
            self.ed.add(r, board=board if board in ("side", "maybe") else "main")

    @QtCore.Slot(int)
    def resultMenu(self, i):
        r = self._row(i)
        if r is None:
            return
        ed = self.ed
        m = qmenu.Menu()
        m.addAction(tr("Show details"), lambda: ed.show_card(r))
        if "commander" in __import__("games").current().deck_extras:
            m.addAction(tr("As commander"), lambda: ed.set_commander(r))
        m.addAction(tr("To sideboard"), lambda: ed.add(r, board="side"))
        m.addAction(tr("To maybeboard"), lambda: ed.add(r, board="maybe"))
        m.addSeparator()
        m.addAction(tr("Add exactly this printing"), lambda: ed.add(r, exact=True))
        m.exec(QtGui.QCursor.pos())

    # Upgrade mode
    @QtCore.Property(bool, notify=changed)
    def upgradeMode(self):
        return bool(self.ed.upgrade_mode)

    @QtCore.Slot()
    def toggleUpgrades(self):
        self.ed.set_upgrades(not self.ed.upgrade_mode)
        self.changed.emit()

    @QtCore.Property(bool, notify=resultsChanged)
    def upgradeView(self):
        return bool(self.ed.results.up_view)

    @QtCore.Property(QtCore.QObject, constant=True)
    def upModel(self):
        return self.ed.results.up_model

    @QtCore.Property(QtCore.QObject, constant=True)
    def upBridge(self):
        return self.ed.results.up_bridge

    @QtCore.Property(int, notify=resultsChanged)
    def upCurrent(self):
        return int(self.ed.results.up_current)

    @QtCore.Property("QVariantMap", constant=True)
    def upTexts(self):
        return {"swap": tr("Swap"), "undo": tr("Undo"), "add": tr("Add"), "free": tr("free slot"),
                "swapped": tr("swapped"), "otherOut": tr("swap out another card …"), "closeChoice": tr("done"),
                "noneOut": tr("none – just add (free slot)"),
                "empty": tr("No upgrades found – your collection has nothing that makes this deck better.")}

    # ---------- Detail + comparison ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def detail(self):
        return self.det_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def compare(self):
        return self.cmp_b

    @QtCore.Property(bool, notify=detailChanged)
    def detailOpen(self):
        return not self.ed.detail.isHidden()

    @QtCore.Property(bool, notify=detailChanged)
    def compareOpen(self):
        return not self.ed.detail.isHidden() and not self.ed.compare.isHidden() and not self.ed.slide.closing

    def _acts(self, which):
        return self.ed.cmp_actions if which == "compare" else self.ed.actions

    @QtCore.Property("QVariantMap", notify=detailChanged)
    def detailActs(self):
        return self._actions("detail")

    @QtCore.Property("QVariantMap", notify=detailChanged)
    def compareActs(self):
        return self._actions("compare")

    def _actions(self, which):
        a = self._acts(which)
        if a.card is None or self.ed.deck is None:
            return {"shown": False}
        alt = self.ed.alt is not None and self.ed.alt["id"] == a.card["id"]
        uses = self.page.built_usage((self.ed.deck or {}).get("id")).get(a.card["name"], [])
        return {"shown": True, "label": a.label, "print": a.print_shown, "cmdr": a.cmdr_shown, "alt": alt,
                "inUse": " · ".join(f"{d} ({n}×)" for d, n in uses)}

    @QtCore.Slot(str, str)
    def act(self, which, what):
        a, ed = self._acts(which), self.ed
        if a.card is None:
            return
        if what == "add":
            ed.add(a.card, exact=True)
        elif what == "cmdr":
            ed.set_commander(a.card, exact=True)
        elif what == "side":
            ed.add(a.card, board="side", exact=True)
        elif what == "print":
            ed.use_print(a.card)
        elif what == "alt":
            ed.set_alternatives(a.card)
        elif what == "more":
            self._card_menu(a.card)

    def _card_menu(self, r):
        """The "More …" button on the card in the detail view (instead of hover buttons on the row)."""
        ed = self.ed
        m = qmenu.Menu()
        if ed.deck_count(r["name"]):
            m.addAction(tr("One less in the deck"), lambda: ed.remove_one(r))
        m.addAction(tr("To maybeboard"), lambda: ed.add(r, board="maybe", exact=True))
        row = next((x for x in ed.list_rows if not x["head"] and x["sid"] == r["id"]), None)
        if row is not None:
            sid, board = row["sid"], row["board"]
            m.addSeparator()
            m.addAction(tr("Remove from deck"), lambda: ed.change(sid, board, -999))
            for b, label in (("main", tr("To deck")), ("side", tr("To sideboard")), ("maybe", tr("To maybeboard"))):
                if b != board and not (board == "commander" and b == "main"):
                    m.addAction(tr("Move: ") + label, lambda b=b: ed.move(sid, board, b))
        m.exec(QtGui.QCursor.pos())

    @QtCore.Slot()
    def escape(self):
        ed = self.ed
        if not ed.compare.isHidden():
            ed.close_compare()
        elif not ed.detail.isHidden() and not ed.upgrade_layout:
            ed.close_detail()
        else:
            self.page.show_overview()

    # ---------- Panes (order, widths) ----------
    @QtCore.Property("QVariantList", notify=changed)
    def order(self):
        return list(self.ed.order)

    # Upgrades are a format of their own (card pairs): own layout, remembered as the user drags it
    SPLITS = {"deck_split": {"cards": 0.6, "detail": 0.2, "list": 0.2},
              "deck_split_up": {"list": 0.26, "cards": 0.32, "detail": 0.42}}

    def _split_key(self):
        return "deck_split_up" if self.ed.results.up_view else "deck_split"

    @QtCore.Property("QVariantMap", notify=splitChanged)
    def split(self):
        key = self._split_key()
        frac = self.ctrl.settings.get(key) or self.SPLITS[key]
        return {k: float(frac.get(k, 0.2)) for k in ("cards", "detail", "list")}

    @QtCore.Property(float, notify=changed)
    def listsSplit(self):
        """Left column with lists: share of the lists at the top (rest = deck list)."""
        return float(self.ctrl.settings.get("deck_lists_top") or 0.45)

    @QtCore.Slot(float)
    def setListsSplit(self, f):
        self.ctrl.settings["deck_lists_top"] = round(max(0.1, min(0.9, float(f))), 4)
        self.ctrl.settings_changed()
        self.changed.emit()

    @QtCore.Slot("QVariantMap")
    def setSplit(self, frac):
        total = sum(float(v) for v in frac.values()) or 1.0
        self.ctrl.settings[self._split_key()] = {k: round(float(v) / total, 4) for k, v in frac.items()}
        self.ctrl.settings_changed()
        self.changed.emit()
        self.splitChanged.emit()

    # ---------- right: deck list / deck info ----------
    @QtCore.Property(int, notify=changed)
    def tab(self):
        return self.ed.tab

    @QtCore.Slot(int)
    def setTab(self, i):
        self.ed.show_tab(i)
        if i == 1:
            self.stats_m.refresh()

    @QtCore.Property(str, notify=listChanged)
    def commander(self):
        return "" if self.ed.cmdr.isHidden() else self.ed.cmdr.text()

    @QtCore.Property(str, notify=listChanged)
    def swapText(self):
        return self.ed.swap_text if self.ed.swap_shown else ""

    @QtCore.Slot()
    def useOwnedPrints(self):
        self.ed.use_owned_prints()

    @QtCore.Property("QVariantList", notify=listChanged)
    def deckList(self):
        ed = self.ed
        out = []
        for k, x in enumerate(ed.list_rows):
            if x["head"]:
                out.append({"k": k, "head": True, "text": x["text"]})
                continue
            out.append({"k": k, "head": False, "sid": x["sid"], "board": x["board"], "count": x["count"], "n": x["n"],
                        "name": x["name"], "mana": _mana(x["cost"]), "price": x["price"], "own": x["own"],
                        "ownColor": x["ownColor"], "ownTip": x["ownTip"],
                        "sel": (x["sid"], x["board"]) == ed.list_current, "alt": x["alt"],
                        "inUse": [{"deck": d, "n": n} for d, n in x["inUse"]],
                        "pinned": x["pinned"], "where": x["where"], "pick": f'{x["sid"]}|{x["board"]}' == self._pin_pick,
                        "holders": [{"img": back_image(h[2]), "tip": f"{h[1]} ({h[3]}×)"} for h in x["holders"][:3]]})
        return out

    # ---------- Pin: choose printing / pin it ----------
    _pin_pick = ""

    @QtCore.Slot(int)
    def openPinPick(self, k):
        """Pin on the row: open/close the strip of all printings below it."""
        x = self.ed.list_row(k)
        key = f'{x["sid"]}|{x["board"]}' if x is not None else ""
        self._pin_pick = "" if key == self._pin_pick else key
        self.listChanged.emit()

    @QtCore.Property("QVariantList", notify=listChanged)
    def pinRows(self):
        """All printings of the card in the open row (cheapest first); marked = pinned printing."""
        from collection import alarms
        from ui.qtrade import db_image
        from collection.tradelib import eur
        if not self._pin_pick:
            return []
        sid = self._pin_pick.split("|", 1)[0]
        r = self.ed.rows.get(sid)
        if r is None:
            return []
        rows = alarms.prints_of([r["name"]]).get(r["name"], [])
        rows.sort(key=lambda p: (p.get("eur") is None, p.get("eur") or 0))
        pin = self.ed.pinned(sid)
        return [{"id": p["id"], "set": (p.get("set_code") or "").upper(), "number": p.get("number") or "",
                 "sname": p.get("set_name") or "",
                 "img": db_image(p), "price": eur(p.get("eur") if p.get("eur") is not None else p.get("eur_foil")),
                 "mark": "main" if pin and p["id"] == sid else "", "date": ""} for p in rows[:400]]

    @QtCore.Slot(int, str)
    def pinPrint(self, k, new_sid):
        """Printing chosen from the strip (pinned), or "" = any version again."""
        x = self.ed.list_row(k)
        self._pin_pick = ""
        if x is not None:
            self.ed.pin_print(x["sid"], new_sid)
        self.listChanged.emit()

    @QtCore.Property(int, notify=listChanged)
    def inUseCount(self):
        """How many cards of this deck are also in other (built) decks?"""
        return sum(1 for x in self.ed.list_rows if not x["head"] and x["inUse"])

    @QtCore.Property("QVariantList", notify=listChanged)
    def listColumns(self):
        """Column headers; "" = column hidden (other games have no mana cost)."""
        cost = tr("Cost") if __import__("games").current().deck_cost_column else ""
        return ["", tr("Card"), cost, tr("Price"), tr("Besitz")]

    @QtCore.Property("QVariantList", notify=listChanged)
    def listSort(self):
        s = self.ed.list_sort
        return [int(s[0]), bool(s[1])] if s else [-1, False]

    @QtCore.Slot(int)
    def sortBy(self, col):
        self.ed.sort_list_by(col)

    @QtCore.Slot(int)
    def selectRow(self, k):
        self.ed.select_list_row(k)

    @QtCore.Slot(int, int)
    def changeRow(self, k, d):
        x = self.ed.list_row(k)
        if x is not None:
            self.ed.change(x["sid"], x["board"], d)

    @QtCore.Slot(int)
    def changeCurrent(self, d):
        x = self.ed.current_list_row()
        if x is not None:
            self.ed.change(x["sid"], x["board"], d)

    @QtCore.Slot(int)
    def dropRowOut(self, k):
        """Row dragged from the deck list onto the results: one fewer."""
        x = self.ed.list_row(k)
        if x is not None:
            self.ed.drop_out(f"{x['sid']}|{x['board']}")

    @QtCore.Property(QtCore.QObject, constant=True)
    def stats(self):
        return self.stats_m
