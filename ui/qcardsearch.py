"""'Search / edit card' in Qt Quick (qml/components/CardSearch.qml) – in the stream (scan page) and under
Sessions → Edit card. The logic lives in ui.panels.CardPanel (no widget): search in the loaded sets, Scryfall,
languages, foil, back face, add/replace/remove. This object passes its state on to QML."""
from PySide6 import QtCore

from ui import quickimages
from collection.collection import lang_short
from scanner.common import BASE


class CardSearchBackend(QtCore.QObject):
    changed = QtCore.Signal()
    resultsChanged = QtCore.Signal()
    closeRequested = QtCore.Signal()

    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.p = panel
        panel.changed.connect(self.changed.emit)
        panel.results_changed.connect(self.resultsChanged.emit)
        panel.results_changed.connect(self.changed.emit)  # the selected row changes the card at the top
        panel.closeRequested.connect(self.closeRequested.emit)

    # ---------- Header + selection ----------
    @QtCore.Property(str, notify=changed)
    def title(self):
        return self.p.title

    @QtCore.Property(bool, constant=True)
    def inStream(self):
        return bool(self.p.in_stream)

    @QtCore.Property(bool, notify=changed)
    def hasCard(self):
        return self.p.sel is not None

    @QtCore.Property(str, notify=changed)
    def name(self):
        return self.p.name

    @QtCore.Property(str, notify=changed)
    def meta(self):
        return self.p.meta

    @QtCore.Property(str, notify=changed)
    def details(self):
        """Artist · rarity · type line (panels.CardPanel.card_details)."""
        return self.p.details

    @QtCore.Property(str, notify=changed)
    def rules(self):
        """Start of the rules text, cut with "…"."""
        return self.p.rules

    # ---------- the scanner's question (panels.CardPanel.open_question) ----------
    @QtCore.Property(str, notify=changed)
    def questionKind(self):
        """"print" / "lang" while the scanner asks here, otherwise ""."""
        return (self.p.question or {}).get("kind", "")

    @QtCore.Property(str, notify=changed)
    def questionText(self):
        """What the search field was filled with – unchanged, the digits 1–9 pick (afterwards they are typed)."""
        return (self.p.question or {}).get("text", "")

    @QtCore.Property(str, notify=changed)
    def camImage(self):
        """The card lying there, cut from the camera image – to compare."""
        return (self.p.question or {}).get("cam") or ""

    @QtCore.Property(str, notify=changed)
    def loupeImage(self):
        """Stamp twins: where the stamp sits, enlarged from the camera image."""
        return (self.p.question or {}).get("loupe") or ""

    @QtCore.Property(str, notify=changed)
    def questionNote(self):
        return (self.p.question or {}).get("note") or ""

    @QtCore.Slot(int, result=bool)
    def pickNumber(self, n):
        """1–9 in the question: print – the n-th row is taken; language – the n-th language key."""
        q = self.p.question
        if q is None or n < 1:
            return False
        if q["kind"] == "lang":
            langs = [x for x in self.langs if x.get("enabled") is not False]
            if n <= len(langs):
                self.p.lang_picked(langs[n - 1]["code"])
                return True
            return False
        if n <= len(self.p.results):
            self.p.set_row(n - 1)
            self.p.confirm()
            return True
        return False

    @QtCore.Slot(result=bool)
    def nextFinish(self):
        """F in the question (the name still as filled in): the shown card's next finish – taken with the answer."""
        return self.p.question is not None and self.p.next_finish()

    @QtCore.Property(str, constant=True)
    def searchHint(self):
        """Placeholder of the search field: what it finds in this game (name, artist, year)."""
        from ui.searchbox import card_search_placeholder
        return card_search_placeholder()

    @QtCore.Property(str, notify=changed)
    def price(self):
        return self.p.price

    @QtCore.Property(str, notify=changed)
    def previewText(self):
        return self.p.preview_text

    @QtCore.Property(str, notify=changed)
    def preview(self):
        p = self.p
        card = p.sel
        if card is None:
            return ""
        ov = p.ctrl.overlay
        back = ov.other_face(card)
        shown = back if (back is not None and ov.show_back) else card
        if p.lang != "en":
            from scanner.common import lang_img
            if (BASE / lang_img(shown["img"], p.lang)).exists():
                shown = dict(shown, img=lang_img(shown["img"], p.lang))
        local = BASE / shown["img"] if shown.get("img") else None
        if local is not None and local.exists():
            return quickimages.register(f"csl_{shown['img']}", local, None, None)
        if p.sel_url:
            return quickimages.register(f"cso_{abs(hash(p.sel_url))}", None, p.sel_url, None)
        return ""

    @QtCore.Property(bool, notify=changed)
    def foil(self):
        return self.p.foil

    @QtCore.Slot(bool)
    def setFoil(self, on):
        self.p.set_foil(on)

    # ---------- Condition (only when editing in the stream): click = next grade ----------
    def _entry(self):
        st = getattr(self.p.ctrl, "stream", None)
        if not self.p.in_stream or self.p.editing is None or st is None:
            return None
        return st.edit_entry()

    @QtCore.Property(str, notify=changed)
    def condText(self):
        from cards import conditions
        if self._entry() is None or self.p.cond is None:
            return ""
        return f"{conditions.short(self.p.cond)} · {conditions.name(self.p.cond)}"

    @QtCore.Slot()
    def nextCond(self):
        """Next grade – only in this window; saved with "Replace" (Oliver: nothing saves by itself)."""
        from cards import conditions
        if self._entry() is not None and self.p.cond is not None:
            conditions.apply(self.p.cond, conditions.next_key(self.p.cond))
            self.changed.emit()

    @QtCore.Property(bool, notify=changed)
    def editDirty(self):
        """Editing with a change not saved yet: "Replace" is shown inverted."""
        return self.p.edit_dirty()

    @QtCore.Property("QVariantList", notify=changed)
    def finishOptions(self):
        """Finishes of the selected printing: [{key, text, on}] – per game (finishes.py)."""
        from cards import finishes
        p = self.p
        if p.sel is None:
            return []
        return [{"key": o["key"], "text": o["label"], "on": o["key"] == p.finish} for o in finishes.options(p.sel)]

    @QtCore.Property("QVariantList", notify=changed)
    def editionOptions(self):
        """Editions that exist for the printing (Pokémon: 1st Edition) – empty if none."""
        from cards import finishes
        p = self.p
        if p.sel is None:
            return []
        return [{"key": x["key"], "text": x["label"], "on": x["key"] == p.edition} for x in finishes.editions(p.sel)]

    @QtCore.Property(str, notify=changed)
    def editionHint(self):
        """The chosen print exists as a 1st Edition (Pokémon WotC sets) and it isn't set: where to look – SCAN° doesn't
        read the stamp (yet), the user decides. "" otherwise."""
        from cards import finishes
        import games
        p = self.p
        if p.sel is None or games.current().key != "pokemon" or p.edition == "1st":
            return ""
        if any(x["key"] == "1st" for x in finishes.editions(p.sel)):
            from system.i18n import tr
            return tr("1st Edition? Stamp to the left below the picture")
        return ""

    @QtCore.Slot(str)
    def setFinish(self, key):
        self.p.set_finish(key)

    @QtCore.Slot(str)
    def toggleEdition(self, key):
        self.p.set_edition("" if self.p.edition == key else key)

    @QtCore.Property(bool, notify=changed)
    def webSearch(self):
        """Magic: "Scryfall" button; other games: "All sets" (card database)."""
        return self.p.web_search()

    @QtCore.Property("QVariantList", notify=changed)
    def langs(self):
        p = self.p
        if not p.langs_shown:
            return []
        shown, seen = [], set()
        for c, short, _x, printed in p.langs or [(p.lang, lang_short(p.lang), None, None)]:
            if c not in seen:   # the same printing can appear several times per language (e.g. two JP entries)
                seen.add(c)
                shown.append((c, short, printed))
        only = len(shown) < 2   # only one language: selected, but greyed out (nothing to choose)
        return [{"code": c, "text": short, "tip": printed or short, "on": c == p.lang or only, "enabled": not only}
                for c, short, printed in shown]

    @QtCore.Property(str, notify=changed)
    def langNote(self):
        return self.p.lang_note

    @QtCore.Slot(str)
    def pickLang(self, code):
        self.p.lang_picked(code)

    @QtCore.Property(bool, notify=changed)
    def backShown(self):
        return self.p.back_shown

    @QtCore.Property(bool, notify=changed)
    def backOn(self):
        return self.p.back_on

    @QtCore.Slot()
    def toggleBack(self):
        self.p.toggle_back()

    # ---------- Buttons ----------
    @QtCore.Property(str, notify=changed)
    def okText(self):
        return self.p.ok_text

    @QtCore.Property(bool, notify=changed)
    def okEnabled(self):
        return self.p.ok_enabled

    @QtCore.Slot()
    def confirm(self):
        self.p.confirm()

    @QtCore.Property(bool, notify=changed)
    def removeShown(self):
        return self.p.remove_shown

    @QtCore.Slot()
    def remove(self):
        self.p.wrong_scan = False
        self.p.removed.emit()

    @QtCore.Slot()
    def wrongScan(self):
        """'Wrongly recognized': remove the card and log it as a scanner miss in the scan data (only on an explicit
        click – plain removing doesn't mean it was misrecognized)."""
        self.p.wrong_scan = True
        self.p.removed.emit()

    @QtCore.Slot()
    def close(self):
        self.p.closeRequested.emit()

    # ---------- Search ----------
    @QtCore.Property(str, notify=changed)
    def search(self):
        return self.p.search

    @QtCore.Slot(str)
    def setSearch(self, t):
        self.p.set_search(t)  # short pause, then search (like when typing)

    @QtCore.Slot()
    def enter(self):
        self.p.enter()

    @QtCore.Slot()
    def searchOnline(self):
        self.p.search_online(self.p.search.strip())

    @QtCore.Slot(int)
    def move(self, d):
        p = self.p
        if p.results:
            p.set_row(max(0, min(len(p.results) - 1, p.row + d)))

    @QtCore.Property(str, notify=changed)
    def info(self):
        return self.p.info

    @QtCore.Property(int, notify=resultsChanged)
    def current(self):
        return self.p.row

    @QtCore.Property("QVariantList", notify=resultsChanged)
    def results(self):
        p, out = self.p, []
        ov = p.ctrl.overlay
        for i, (card, url) in enumerate(p.results):
            name, sub = p.row_text(card, url is not None)
            img = ""
            local = BASE / card["img"] if card.get("img") else None
            if local is not None and local.exists():   # on disk: always that one (also when the result has an address)
                img = quickimages.register(f"csl_{card['img']}", local, None, None)
            elif card.get("thumb"):
                img = quickimages.register(f"cst_{abs(hash(card['thumb']))}", None, card["thumb"], None)
            else:   # not on disk, no address in the data (Pokémon …): the small image from the game's source / mirror
                small = self._small_url(card)
                if small:
                    img = quickimages.register(f"css_{abs(hash(small))}", None, small, None)
            out.append({"i": i, "name": name, "sub": sub, "img": img, "back": ov.other_face(card) is not None})
        return out

    @staticmethod
    def _small_url(card):
        """Small image of a result row that isn't on disk – None if the game has no address for it."""
        from cards import library
        try:
            return library.image_url(card["set"], card["number"], "en", "small")
        except Exception:  # noqa: BLE001
            return None

    @QtCore.Slot(int)
    def select(self, i):
        self.p.set_row(i)

    @QtCore.Slot(int)
    def pick(self, i):
        """Double click: select and apply."""
        self.p.set_row(i)
        self.p.confirm()

    _over = None   # what the large preview currently shows: row number, -2 = image at the top, None = nothing

    @QtCore.Slot(int)
    def hover(self, i):
        if i < 0:
            self._over = None
            self.p.hovered.emit(None)
        else:
            self._over = i
            self.p.hover_row(i)

    @QtCore.Slot(int)
    def unhover(self, i):
        """Mouse leaves row i (or -2 = image at the top). When moving down, the new row reports "in" BEFORE the
        old one reports "out" – only clear if the preview still belongs to this row."""
        if self._over == i:
            self._over = None
            # the scanner's question: back to the selected print (to compare with the card), else nothing
            self.p.hovered.emit(self.p.hover_card(self.p.sel) if self.p.question is not None and self.p.sel else None)

    @QtCore.Slot()
    def hoverPreview(self):
        if self.p.sel is not None:
            self._over = -2
            self.p.hovered.emit(self.p.hover_card(self.p.sel))

    @QtCore.Slot(int)
    def toggleRowBack(self, i):
        self.p.toggle_back_row(i)
