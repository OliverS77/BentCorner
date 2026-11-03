"""Page switching and windows in the stream (StreamWindow) – logic only, Qt Quick draws.
Moved from app.py (re-exported there)."""
import time

from PySide6 import QtCore

from system.i18n import tr
from ui.librarycore import LibraryCore
from ui.panels import CardPanel, StatsPanel
from ui.scanview import ScanView


class StreamWindow(QtCore.QObject):
    """Page switching and windows in the stream (search/edit card, stream info, statistics) – logic only.
    Everything is drawn in Qt Quick; quickshell hooks window commands (show, fullscreen, hide) and the
    navigation in here."""

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.back_from = None  # page you jumped here from (for "← Back to …")
        self.view = ScanView(ctrl, stream=True)
        self.pages, self.page = {"scan"}, "scan"
        # windows in the middle of the stream
        self.ctrl, self.edit_index = ctrl, None
        self.edit_pack = None   # the card being edited sits in this pack (index in session.packs; None = the current one)
        self.card_panel = CardPanel(ctrl, self)
        self.card_panel.chosen.connect(self.card_chosen)
        self.card_panel.removed.connect(self.card_removed)
        self.card_panel.closeRequested.connect(self.close_card_panel)
        self.card_panel.hovered.connect(self._search_hover)
        self._reveal = QtCore.QTimer(self, singleShot=True, timeout=self._reveal_panel)
        self.stats_panel = StatsPanel(ctrl, self.view)
        self.panels = (self.card_panel, self.stats_panel)

    def resized(self):
        """The scan view has a new size: re-place open windows in the stream."""
        for panel in self.panels:
            if panel.isVisible():
                panel.place()

    # --- Windows (quickshell hooks in here; without the Qt Quick UI nothing happens) ---
    def set_badge(self, key, on):
        """Hint dot on a navigation item."""

    def isVisible(self):
        return False

    def isMinimized(self):
        return False

    def showFullScreen(self):
        pass

    showMaximized = showNormal = show = hide = raise_ = activateWindow = showFullScreen

    # --- Pages and navigation ---
    def add_page(self, key):
        self.pages.add(key)

    def ensure_page(self, key):
        """Create the page if it doesn't exist yet (without switching to it)."""
        ctrl = self.ctrl
        if key == "import" and "import" not in self.pages:
            from ui.importview import ImportPage
            ctrl.import_page = ImportPage(ctrl)  # data; shown by qimport (Qt Quick)
            self.add_page("import")
        if key == "library" and "library" not in self.pages:
            ctrl.library_win = LibraryCore(ctrl)  # logic; drawn by Qt Quick (qlibrary)
            self.add_page("library")
        if key == "trade" and "trade" not in self.pages:
            from ui.tradeview import TradePage
            ctrl.trade_page = TradePage(ctrl)
            self.add_page("trade")  # logic in TradePage; drawn by Qt Quick
        if key == "profile" and "profile" not in self.pages:
            self.add_page("profile")   # Profile: name, card back, ID, friends of all games, backup (qprofile)
        if key == "testing" and "testing" not in self.pages:
            self.add_page("testing")  # Play: being rebuilt, until then "Coming soon" (Qt Quick)
        if key == "decks" and "decks" not in self.pages:
            from collection.deckcore import DeckPage
            ctrl.deck_page = DeckPage(ctrl)  # logic; drawn by Qt Quick (qdecks)
            self.add_page("decks")

    def go_back(self):
        key = self.back_from
        if key:
            self.show_page(key)

    def show_page(self, key, tab=None, animate=True, back=False):
        """Switch page: "scan", "library" or "settings" (tab = tab in the settings part).
        back=True: jumped here from another page (quick link) -> the tab you came from gets an outline and arrow in the
        navigation (click = back); the mouse's back button works too."""
        ctrl = self.ctrl
        self.ensure_page(key)
        if back and key != self.page:
            self.back_from = self.page
        elif not back and key != self.page:
            self.back_from = None
        self.set_badge(key, False)  # page opened: hint dot seen
        if key == "settings":   # … except the backup lamp: it follows its rule, not a look (Oliver, 29.10.)
            from system import autobackup
            if autobackup.lamp(ctrl.settings):
                self.set_badge("settings", True)
        changed = key != self.page
        if key != "scan":   # scanning only counts with a card (the program starts there)
            from net import anonstats
            anonstats.mark(key)
        if key != "scan":
            self.close_all()
            ctrl.overlay.hover = None
        if key == "settings" and tab is not None:   # a link into the settings: old search away, the target pulses
            sb = getattr(getattr(ctrl, "shell", None), "backends", {}).get("settings")
            sb.arrive(tab) if sb is not None else ctrl.show_settings(tab)
        self.page = key
        if key == "library" and changed:
            ctrl.library_win.enter()
        if key == "decks" and changed:
            ctrl.deck_page.enter()
        if key == "trade" and changed:
            ctrl.trade_page.enter()
        if key in ("stats", "sessions") and changed:
            ctrl.refresh_stats()
        # Tick: smooth on the scan page (camera image), otherwise a calm pulse is enough (saves CPU time)
        ctrl.timer.setInterval(16 if key == "scan" else 120)

    def bring_up(self):
        """Show the scan page without changing fullscreen/size."""
        if self.page != "scan":
            self.show_page("scan")
        if self.isMinimized():
            self.showNormal()
        elif not self.isVisible():
            self.show()
        self.raise_()

    def close_all(self):
        self.only(None)

    def only(self, panel):
        for other in self.panels:
            if other is not panel and other.isVisible():
                if other is self.card_panel:
                    self.close_card_panel()
                else:
                    other.hide()

    def flip_in_card_panel(self):
        """Show card search/edit – the pack list stays (search rises from the bar, edit
        slides out beside the list; Qt Quick does the movement)."""
        panel = self.card_panel
        panel.place()
        panel.show()

    def _reveal_panel(self):
        self.card_panel.place()
        self.ctrl.overlay.flip = None

    def _search_hover(self, card):
        """A card of the card search under the mouse: its preview beside the search window."""
        self.ctrl.overlay.panel_hover, self.ctrl.overlay.hover_list = card, False

    def close_card_panel(self):
        ov = self.ctrl.overlay
        self._reveal.stop()
        ov.panel_hover = None
        if not ov.panel_open and self.card_panel.isHidden():
            ov.flip = None
            return
        self.card_panel.hide()  # Qt Quick fades it out (the pack list was there the whole time)
        ov.panel_open = False
        ov.flip = None

    def overlay_action(self, action, idx):
        session = self.ctrl.session
        if action == "gear":
            self.open_edit(idx)
        elif action == "foil":
            session.toggle_foil(idx)
        elif action == "cond":
            session.toggle_cond(idx)
        elif action == "out":
            session.toggle_out(idx)
        elif action == "remove":
            pack = self.ctrl.snap.get("pack") or []
            if 0 <= idx < len(pack):
                self.ctrl.removed_soon(pack[idx])
            session.undo(idx)
        elif action == "search":
            self.open_add()
        elif action == "newpack":
            self.ctrl.new_pack()
        elif action == "session":   # session window (as from the bar): end, new, type, info
            self.open_info()
        elif action == "undonewpack":
            self.ctrl.session.undo_new_pack()
        elif action == "info":
            self.open_info()
        elif action == "stats":
            self.open_stats()
        elif action == "bighit":
            self.ctrl.overlay.play_next_idle(time.monotonic())
        elif action == "hitmode":
            self.ctrl.toggle_hit_mode()
        elif action == "pause":
            self.ctrl.toggle_pause()
        elif action == "flip":
            self.ctrl.overlay.toggle_back(time.monotonic())

    def open_edit(self, idx, pack=None):
        """Edit a card: idx in the current pack – or in session.packs[pack] (the scan tile's list: any pack)."""
        cards = self._pack_cards(pack)
        if not 0 <= idx < len(cards):
            return
        self.bring_up()
        self.only(self.card_panel)
        self.edit_index, self.edit_pack = idx, pack
        label = tr(f" · card {idx + 1}") if pack is None else tr(f" · pack {pack + 1}, card {idx + 1}")
        self.card_panel.open_edit(cards[idx], label)
        self.flip_in_card_panel()

    def _pack_cards(self, pack):
        if pack is None:
            return self.ctrl.snap.get("pack") or []
        sess = self.ctrl.session
        with sess.lock:
            return list(sess.packs[pack]["cards"]) if 0 <= pack < len(sess.packs) else []

    def edit_entry(self):
        """The card being edited (None: none, or it is gone)."""
        if self.edit_index is None:
            return None
        cards = self._pack_cards(self.edit_pack)
        return cards[self.edit_index] if 0 <= self.edit_index < len(cards) else None

    def open_add(self):
        self.bring_up()
        self.only(self.card_panel)
        self.edit_index = self.edit_pack = None
        self.card_panel.open_add()
        self.flip_in_card_panel()

    def open_info(self):
        """The session window – the scan page (qscan) puts its own here."""

    def open_stats(self):
        self.bring_up()
        self.only(self.stats_panel)
        self.stats_panel.open()

    def card_chosen(self, card, foil, lang):
        fin, ed = self.card_panel.finish or None, self.card_panel.edition
        if self.card_panel.question is not None:   # the scanner's question: it counts the answer itself (no add_manual)
            self.card_panel.answer(card, lang)
            self.close_card_panel()
            return
        if self.edit_index is None:
            self.ctrl.session.add_manual(card, foil, lang, finish=fin, edition=ed or None)
            self.ctrl.added_by_hand(card)
        else:
            old = self.edit_entry()
            self.ctrl.session.replace(card, self.edit_index, p=self.edit_pack, foil=foil, lang=lang, finish=fin, edition=ed)
            cond = self.card_panel.cond
            if old is not None and cond is not None and cond != (self.card_panel.edit_orig or {}).get("cond"):
                self.ctrl.session.set_card(old.get("added"), cond=cond)   # the condition chosen in the window
            self.ctrl.scan_correction(old, card)
        self.close_card_panel()

    def card_removed(self):
        if self.edit_index is not None:
            e = self.edit_entry()
            if e is not None:
                if getattr(self.card_panel, "wrong_scan", False):   # "Wrongly recognised": surely a mistake
                    self.ctrl.scan_removed(e)
                else:                                               # "Remove": maybe one
                    self.ctrl.removed_soon(e)
            self.ctrl.session.undo(self.edit_index, p=self.edit_pack)
        self.card_panel.wrong_scan = False
        self.close_card_panel()
