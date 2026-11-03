"""Decks in Qt Quick (qml/pages/DecksPage.qml).

The overview (tiles, folder bar, New deck, Built chip, dragging onto folders) is QML; the logic lives in
deckcore.DeckPage. The editor is qdeckedit.py, comparison and suggestion qdeckmore.py.
"""
from PySide6 import QtCore

from collection import decks
from ui import quickimages
from system.i18n import tr
from cards import library
from collection.deckcore import FOLDER_COLORS, LOOSE, eur
from ui.librarycore import THUMBS

ALL, LOOSE_KEY = "*", "~"


class DecksBackend(QtCore.QObject):
    changed = QtCore.Signal()
    selChanged = QtCore.Signal()   # Selection – its own signal so the tiles are not recreated

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        ctrl.stream.ensure_page("decks")
        self.page = page = ctrl.deck_page
        self.LOOSE = LOOSE
        self._t = QtCore.QTimer(self, singleShot=True, interval=0, timeout=self.changed.emit)
        self._sel, self._selecting = [], False   # selected decks (ids, in click order), selection mode
        page.changed.connect(self.soon)
        page.loader.ready.connect(lambda _: self.soon())
        from ui.qdeckedit import DeckEditorBackend
        self.editor_b = DeckEditorBackend(ctrl, page, self)
        from ui.qdeckmore import BrewBackend, CompareBackend, SuggestBackend
        self.compare_b = CompareBackend(ctrl, page, self)
        self.suggest_b = SuggestBackend(ctrl, page, self)
        self.brew_b = BrewBackend(ctrl, page, self.suggest_b, self)
        page.suggest.start = self._brew_start(page.suggest.start)

    def soon(self):
        if not self._t.isActive():
            self._t.start()

    # ---------- View ----------
    @QtCore.Property(str, notify=changed)
    def view(self):
        return self.page.view

    @QtCore.Property(QtCore.QObject, constant=True)
    def editor(self):
        return self.editor_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def compareView(self):
        return self.compare_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def suggestView(self):
        return self.suggest_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def brew(self):
        return self.brew_b

    def _brew_start(self, fn):
        def start():
            fn()
            self.brew_b.enter()
        return start

    @QtCore.Slot()
    def escape(self):
        p = self.page
        if self.view != "overview":
            p.show_overview()

    # ---------- Tiles ----------
    def _art(self, r):
        if r is None:
            return ""
        local = THUMBS / f"{r['id']}_en_n.jpg"
        url = r.get("img_normal") or library.image_url(r["set_code"], r["number"], "en", "normal")
        return quickimages.register(f"{r['id']}_en_n", local, url, local)

    @QtCore.Property("QVariantList", notify=changed)
    def tiles(self):
        out = []
        for i, (deck, info) in enumerate(self.page.tiles):
            kind = deck.get("_tile")
            if kind:
                out.append({"i": i, "kind": kind})
                continue
            size = info.get("size")
            out.append({"i": i, "kind": "deck", "id": deck["id"], "name": deck["name"], "built": bool(deck.get("built")),
                        "fmt": dict(decks.FORMATS).get(deck.get("format"), deck.get("format") or ""),
                        "count": f"{info.get('count', 0)}" + (f" / {size}" if size else ""),
                        "price": eur(info.get("price") or 0), "identity": info.get("identity") or "",
                        "bracket": info.get("bracket") or 0, "art": self._art(info.get("art_row")),
                        "artist": (info.get("art_row") or {}).get("artist") or "",
                        "folder": deck.get("folder") or ""})
        return out

    def _deck(self, i):
        rows = self.page.tiles
        return rows[i][0] if 0 <= i < len(rows) and not rows[i][0].get("_tile") else None

    @QtCore.Slot(int, int)
    def openTile(self, i, half):
        rows = self.page.tiles
        if not 0 <= i < len(rows):
            return
        obj = rows[i][0]
        kind = obj.get("_tile")
        if kind == "new":
            if half == 0:
                self.page.show_suggest()
            elif half == 2:
                self.importDeck()
            else:
                self.page.new_deck()
        elif kind is None:
            self.page.open_deck(obj)
        self.soon()

    @QtCore.Slot(int)
    def toggleBuilt(self, i):
        d = self._deck(i)
        if d is not None:
            self.page.set_built(d, not d.get("built"))

    @QtCore.Slot(int, str)
    def moveDeck(self, i, key):
        d = self._deck(i)
        if d is not None:
            folder = None if key in (ALL, LOOSE_KEY, "") else key
            if (d.get("folder") or None) != folder:
                self.page.move_deck(d, folder)

    @QtCore.Slot(int)
    def duplicate(self, i):
        d = self._deck(i)
        if d is not None:
            self.page.duplicate_version(d)

    @QtCore.Slot(int)
    def compareWith(self, i):
        d = self._deck(i)
        if d is not None:
            self.page.compare_with(d)

    @QtCore.Slot(int)
    def deleteDeck(self, i):
        d = self._deck(i)
        if d is not None:
            self.page.ask_delete(d)

    @QtCore.Slot(int)
    def newFolderWith(self, i):
        d = self._deck(i)
        if d is not None:
            self.page.new_folder(d)

    @QtCore.Slot(int, float, float)
    def deckMenuAt(self, i, gx, gy):
        """deckMenu with the card at (gx, gy) – the click point on the screen."""
        self.deckMenu(i, QtCore.QPoint(round(gx), round(gy)))

    @QtCore.Slot(int)
    def deckMenu(self, i, at=None):
        """Right click on a deck: its actions as a menu in the window (Auswahl = Helligkeit for "Built"), at the click
        (at: a point on the screen; without one where the mouse is)."""
        from ui import qmenu
        d = self._deck(i)
        if d is None:
            return
        m = qmenu.Menu()
        m.addAction(tr("Open"), lambda: self.openTile(i, -1))
        m.addSeparator()
        move = m.addMenu(tr("Move to folder"))
        for f in self.folders:
            if f["editable"]:
                a = move.addAction(f["name"], lambda k=f["key"]: self.moveDeck(i, k))
                a.setEnabled(f["key"] != (d.get("folder") or ""))
        if d.get("folder"):
            move.addAction(tr("No folder"), lambda: self.moveDeck(i, "~"))
        move.addAction(tr("New folder …"), lambda: self.newFolderWith(i))
        m.addSeparator()
        m.addAction(tr("Duplicate as new version"), lambda: self.duplicate(i))
        m.addAction(tr("Compare with …"), lambda: self.compareWith(i))
        built = m.addAction(tr("Built (cards in use)"), lambda: self.toggleBuilt(i))
        built.setCheckable(True)
        built.setChecked(bool(d.get("built")))
        m.addSeparator()
        m.addAction(tr("Delete …"), lambda: self.deleteDeck(i))
        m.sheet(d.get("name") or tr("Deck"), at=at)

    # ---------- Folders ----------
    @QtCore.Property("QVariantList", notify=changed)
    def folders(self):
        p = self.page
        colors = self.ctrl.settings.get("deck_folder_colors") or {}
        cur = p.folder
        out = [{"key": ALL, "name": tr("All decks"), "color": "#8e8e8e", "count": len(p.decks), "sel": cur is None,
                "editable": False}]
        for f in p.folders():
            out.append({"key": f, "name": f, "color": colors.get(f, "#d0d0d0"),
                        "count": sum(1 for d in p.decks if d.get("folder") == f), "sel": cur == f, "editable": True})
        loose = sum(1 for d in p.decks if not d.get("folder"))
        if loose and p.folders():
            out.append({"key": LOOSE_KEY, "name": tr("No folder"), "color": "#4f4f4f", "count": loose,
                        "sel": cur == self.LOOSE, "editable": False})
        return out

    @QtCore.Property("QVariantList", constant=True)
    def colors(self):
        return [{"color": c, "label": tr(lab)} for c, lab in FOLDER_COLORS]

    @QtCore.Slot(str)
    def setFolder(self, key):
        self.page.set_folder(None if key == ALL else self.LOOSE if key == LOOSE_KEY else key)

    @QtCore.Slot(str, str, str)
    def saveFolder(self, old, name, color):
        name = name.strip()
        if not name:
            return
        if old:
            self.page.rename_folder(old, name)
        else:
            self.page.add_folder(name)
        if color:
            self.page.set_color(name, color)
        self.soon()

    @QtCore.Slot(str, str)
    def setColor(self, key, color):
        self.page.set_color(key, color)

    @QtCore.Slot(str)
    def deleteFolder(self, key):
        self.page.delete_folder(key)

    @QtCore.Slot(result=str)
    def nextColor(self):
        used = set((self.ctrl.settings.get("deck_folder_colors") or {}).values())
        return next((c for c, _ in FOLDER_COLORS if c not in used), FOLDER_COLORS[0][0])

    @QtCore.Property(bool, notify=changed)
    def sidebarOpen(self):
        return bool(self.ctrl.settings.get("deck_sidebar_open", True))

    @QtCore.Slot()
    def toggleSidebar(self):
        self.ctrl.settings["deck_sidebar_open"] = not self.sidebarOpen
        self.ctrl.settings_changed()
        self.soon()

    @QtCore.Property(str, notify=changed)
    def crumb(self):
        f = self.page.folder
        if f == self.LOOSE:
            return tr("No folder")
        return f or ""

    @QtCore.Property(str, notify=changed)
    def crumbColor(self):
        f = self.page.folder
        return (self.ctrl.settings.get("deck_folder_colors") or {}).get(f, "#d0d0d0") if f else ""

    @QtCore.Property(bool, notify=changed)
    def empty(self):
        return not self.page.decks and not self.page.folder

    @QtCore.Property(bool, notify=changed)
    def hasDecks(self):
        return bool(self.page.decks)

    # ---------- Texts of the game (Magic: Commander, Moxfield …; Lorcana: Core/Infinity, Dreamborn …) ----------
    @QtCore.Property(bool, notify=changed)
    def canSuggest(self):
        """Deck suggestions from the collection – Magic only so far (deck_extras "brew")."""
        import games
        return "brew" in games.current().deck_extras

    @QtCore.Property(str, notify=changed)
    def tagline(self):
        import games
        return tr(games.current().deck_tagline)

    @QtCore.Property(str, notify=changed)
    def emptyText(self):
        import games
        src = ", ".join(games.current().deck_sources)
        if self.canSuggest:
            return tr(f"No decks yet. Build one yourself, get one suggested from your collection – or bring a decklist from {src} & co.")
        return tr(f"No decks yet. Build one yourself – or bring a decklist from {src} & co.")

    @QtCore.Property(str, notify=changed)
    def importHint(self):
        import games
        return tr(f"{', '.join(games.current().deck_sources)}, text …")

    # ---------- Header ----------
    @QtCore.Slot()
    def importDeck(self):
        self.page.import_deck()

    @QtCore.Slot()
    def share(self):
        self.ctrl.go_export("share_decks")

    # ---------- Select several decks (for import/export) ----------
    def _sel_ids(self):
        have = {d["id"] for d in self.page.decks}
        return [i for i in self._sel if i in have]

    @QtCore.Property("QVariantList", notify=selChanged)
    def selected(self):
        return self._sel_ids()

    @QtCore.Property(bool, notify=selChanged)
    def selecting(self):
        return self._selecting or bool(self._sel_ids())

    @QtCore.Slot(str)
    def toggleSelect(self, did):
        self._sel = [i for i in self._sel if i != did] if did in self._sel else self._sel + [did]
        self.selChanged.emit()

    @QtCore.Slot()
    def startSelect(self):
        self._selecting = True
        self.selChanged.emit()

    @QtCore.Slot()
    def selectAll(self):
        """Select all decks of the shown folder."""
        ids = [t.get("id") for t, _ in self.page.tiles if not t.get("_tile")]
        self._sel = list(dict.fromkeys(self._sel + [i for i in ids if i]))
        self._selecting = True
        self.selChanged.emit()

    @QtCore.Property(bool, notify=selChanged)
    def allSelected(self):
        ids = [t.get("id") for t, _ in self.page.tiles if not t.get("_tile")]
        return bool(ids) and all(i in self._sel for i in ids)

    @QtCore.Slot()
    def selectNone(self):
        """The "None" button: clear the selection but stay in selection mode."""
        self._sel = []
        self._selecting = True
        self.selChanged.emit()

    @QtCore.Slot()
    def clearSelect(self):
        self._sel, self._selecting = [], False
        self.selChanged.emit()

    @QtCore.Slot(str)
    def exportTo(self, key):
        """Import/export menu: go to the matching sub-item – the selected decks are already chosen there."""
        ids = self._sel_ids()
        if not ids:
            cur = self.page.decks[0]["id"] if self.page.decks else None
            ids = [cur] if cur and key == "deck_export" else []
        self.ctrl.go_export(key, deck_ids=ids, deck_id=ids[0] if ids else None)

    @QtCore.Slot(str, str)
    def reorderDeck(self, src, before):
        """Reorder a deck by dragging: src goes before before (in the folder's shown order)."""
        if not src or not before or src == before:
            return
        shown = [t.get("id") for t, _ in self.page.tiles if not t.get("_tile")]
        if src not in shown or before not in shown:
            return
        shown.remove(src)
        shown.insert(shown.index(before), src)
        old = [i for i in self.ctrl.settings.get("deck_order") or [] if i not in shown]
        self.ctrl.settings["deck_order"] = shown + old
        self.ctrl.settings_changed()
        self.page.fill_overview()

    @QtCore.Slot()
    def newDeck(self):
        self.page.new_deck()

    @QtCore.Slot()
    def suggest(self):
        self.page.show_suggest()
