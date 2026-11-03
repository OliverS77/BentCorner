"""Test in Qt Quick (qml/pages/TestPage.qml): pick a deck, see the exact chances of the opening hand (groups and single
cards, collection/playtest.py) – or play it alone on the table (shuffle, opening hand by the game's rules, mulligan,
draw, prize cards, drag cards between hand, play area and discard pile). Rules: games.<game>.playtest. The deck picker
and the chances are a form (qform), the table is drawn in QML from the lists below."""
from PySide6 import QtCore

from cards import carddb
from collection import decks
from collection import playtest
from ui import qform
from system.i18n import tr

TURNS = (2, 3)   # columns after the opening hand
_BACKS = {}


def pct(p):
    return f"{p * 100:.0f} %" if p >= 0.0995 or p == 0 else f"{p * 100:.1f} %"


def library(deck):
    """-> (library rows one per copy, Extra Deck rows) of the main board (Yu-Gi-Oh!: Extra Deck apart; games with a Leader:
    the Leader and DON!! cards aren't part of the library – see TestBackend.leader())."""
    g = decks._G
    ids = decks.all_ids(deck)
    rows = carddb.cards_by_ids(ids) if ids and carddb.exists() else {}
    lib, extra = [], []
    for c in deck["cards"]:
        r = rows.get(c["sid"])
        if r is None or c.get("board", "main") != "main" or g.deck_zone(r) in ("leader", "don"):
            continue
        (extra if g.deck_zone(r) == "extra" else lib).extend([r] * c["count"])
    return lib, extra


_CHANCES = {}   # (game, deck id, cards) -> numbers – the deck info refreshes every 0.7 s, the deck rarely changes


def _chance_data(deck):
    g = decks._G
    key = (g.key, deck.get("id"), tuple((c["sid"], c["count"], c.get("board", "main")) for c in deck["cards"]))
    if key not in _CHANCES:
        _CHANCES.clear()
        lib, extra = library(deck)
        rules = dict(g.playtest)
        counts = {}
        for r in lib:   # counted like the deck rules (by card ID where different cards share a name)
            k = g.deck_name_key(r)
            label = r["name"] if k == r["name"] else f"{r['name']} ({k})"
            counts[label] = counts.get(label, 0) + 1
        basics = sum(1 for r in lib if g.playtest_basic(r)) if rules.get("mulligan") == "basic" else None
        _CHANCES[key] = (lib, extra, rules, counts, basics)
    return _CHANCES[key]


def chance_items(ui, deck):
    """The opening-hand chances of a deck as form parts (Deck info, under the tokens): groups and single cards.
    Singleton decks (Commander: every card once – the chances are all the same) only show the rows that say something:
    the groups, cards with several copies (basic lands) and one row for all the single ones. None: no cards."""
    g = decks._G
    lib, extra, rules, counts, basics = _chance_data(deck)
    if not lib:
        return None
    facts = [tr(f"{len(lib)} cards in the deck"), tr(f"opening hand {rules.get('hand', 7)}")]
    if rules.get("prizes"):
        facts.append(tr(f"{rules['prizes']} prize cards"))
    if extra:
        facts.append(tr(f"Extra Deck {len(extra)}"))
    if rules.get("draw_first"):
        facts.append(tr("first player draws on turn 1"))
    notes = [ui.label(" · ".join(facts), color="gray")]
    if basics is not None:   # Pokémon: chance of having to show and redraw
        p = 1 - playtest.p_at_least(len(lib), basics, rules.get("hand", 7))
        notes.append(ui.label(tr(f"Chance of a mulligan (no Basic Pokémon in the opening hand): {pct(p)}"),
                              color="#ffb347" if p > 0.15 else "gray"))
    # short heads: the deck info is a narrow column – the names need the room (the note below explains the columns)
    nums = ["×", tr("Hand")] + [tr(f"Turn {t}") for t in TURNS]
    head = [(tr("Group"), True)] + nums
    groups = playtest.group_stats(lib, rules, [(tr(n), f) for n, f in g.playtest_groups()], TURNS)
    g_rows = [[x["name"], x["count"]] + [pct(p) for p in x["p"]] for x in groups]
    ones = [n for n, k in counts.items() if k == 1]
    singleton = len(ones) >= 0.8 * len(counts)
    many = sorted(((n, k) for n, k in counts.items() if not singleton or k > 1), key=lambda kv: (-kv[1], kv[0]))
    c_rows = [[name, k] + [pct(p) for p in playtest.chances(len(lib), k, rules, TURNS)] for name, k in many]
    if singleton and ones:   # all the single copies have the same chance: one row
        c_rows.append([tr(f"Each other card ({len(ones)})"), 1] + [pct(p) for p in playtest.chances(len(lib), 1, rules, TURNS)])
    c_head = [(tr("Card"), True)] + nums
    return [ui.col(notes, spacing=4),
            ui.table(head, g_rows, h=min(420, 34 + 30 * len(g_rows))) if g_rows else None,
            ui.label(f"<b>{tr('Single cards')}</b>", rich=True),
            ui.table(c_head, c_rows, h=min(520, 34 + 30 * len(c_rows))),
            ui.note(tr("× = cards in the deck, Hand = in the opening hand, Turn 2/3 = seen by then. Exact chances "
                       "(hypergeometric) without mulligans, searching or other effects."))]


class TestBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.deck_id = None
        self._active = False
        self.view = "table"   # the chances moved into the deck info (Oliver, review .72) – here only the table
        self.game = None        # playtest.Goldfish of the picked deck
        self._game_key = None   # (deck id, updated) the game was dealt from
        self.body_f = qform.Form(self._build, self)

    @QtCore.Slot(bool)
    def setActive(self, on):
        self._active = bool(on)
        if on:
            self.body_f.refresh()

    @QtCore.Property(QtCore.QObject, constant=True)
    def body(self):
        return self.body_f

    # ---------- data ----------
    def _decks(self):
        page = getattr(self.ctrl, "deck_page", None)
        return list(getattr(page, "decks", None) or (decks.load() if carddb.exists() else []))

    def pick(self, deck_id):
        self.deck_id = deck_id
        self.game = None
        self.body_f.refresh()
        self._table()

    @staticmethod
    def library(deck):
        return library(deck)

    @staticmethod
    def leader(deck):
        """Games with a Leader: the deck's Leader (row) or None."""
        g = decks._G
        ids = decks.all_ids(deck)
        rows = carddb.cards_by_ids(ids) if ids and carddb.exists() else {}
        return next((rows[c["sid"]] for c in deck["cards"] if c["sid"] in rows and c.get("board", "main") == "main"
                     and g.deck_zone(rows[c["sid"]]) == "leader"), None)

    # ---------- table (solo game) ----------
    def _deck(self):
        all_decks = self._decks()
        return next((d for d in all_decks if d["id"] == self.deck_id), None)

    def _table(self):
        """Deal a game for the picked deck if there is none yet (or the deck changed) – then tell QML."""
        deck = self._deck()
        key = (deck["id"], deck.get("updated")) if deck else None
        if self.view == "table" and deck is not None and (self.game is None or key != self._game_key):
            g = decks._G
            lib, extra = self.library(deck)
            self.game = playtest.Goldfish(lib, g.playtest, extra=extra, basic=g.playtest_basic,
                                          leader=self.leader(deck)) if lib else None
            self._game_key = key
        self.changed.emit()

    @staticmethod
    def _img(r):
        from cards import library
        from ui import quickimages
        from ui.librarycore import THUMBS
        local = THUMBS / f"{r['id']}_en_n.jpg"
        url = r.get("img_normal") or library.image_url(r["set_code"], r["number"], "en", "normal")
        return quickimages.register(f"{r['id']}_en_n", local, url, local)

    def _cards(self, zone):
        game = self.game
        return [{"i": i, "name": r["name"], "img": self._img(r)} for i, r in enumerate(getattr(game, zone, []))] \
            if game is not None else []

    @QtCore.Property(str, notify=changed)
    def mode(self):
        return self.view

    @QtCore.Slot(str)
    def setView(self, v):
        self.view = "table"
        self.body_f.refresh()
        self._table()

    @QtCore.Property(bool, notify=changed)
    def hasGame(self):
        return self.game is not None

    @QtCore.Property("QVariantList", notify=changed)
    def hand(self):
        return self._cards("hand")

    @QtCore.Property("QVariantList", notify=changed)
    def play(self):
        return self._cards("play")

    @QtCore.Property("QVariantList", notify=changed)
    def active(self):
        return self._cards("active")

    @QtCore.Property("QVariantList", notify=changed)
    def bench(self):
        return self._cards("bench")

    @QtCore.Property(int, notify=changed)
    def benchSize(self):
        """Pokémon: places on the Bench (0 = the game has no Active/Bench zones)."""
        return int(decks._G.playtest.get("bench", 0)) if self.game else 0

    @QtCore.Property("QVariantList", notify=changed)
    def discard(self):
        return self._cards("discard")

    @QtCore.Property("QVariantList", notify=changed)
    def inkwell(self):
        """Lorcana: the inkwell – face down (the card back of your profile)."""
        return [dict(c, img=self.back) for c in self._cards("inkwell")]

    @QtCore.Property(bool, notify=changed)
    def hasInkwell(self):
        return bool(self.game) and bool(decks._G.playtest.get("inkwell"))

    @QtCore.Property("QVariantList", notify=changed)
    def extra(self):
        return self._cards("extra")

    @QtCore.Property(int, notify=changed)
    def libraryCount(self):
        return len(self.game.library) if self.game else 0

    @QtCore.Property(int, notify=changed)
    def prizeCount(self):
        return len(self.game.prizes) if self.game else 0

    @QtCore.Property(int, notify=changed)
    def toBottom(self):
        return self.game.to_bottom if self.game else 0

    @QtCore.Property(bool, notify=changed)
    def canMulligan(self):
        return bool(self.game) and self.game.can_mulligan()

    @QtCore.Property(str, notify=changed)
    def mulliganText(self):
        """Lorcana: "Done" while cards are being picked for the bottom."""
        return tr("Done") if self.game is not None and self.game.choosing else tr("Mulligan")

    @QtCore.Property(bool, notify=changed)
    def picking(self):
        return self.game is not None and self.game.choosing

    @QtCore.Property(str, notify=changed)
    def back(self):
        """Card back of your profile (face-down cards: library, prize cards)."""
        from system import userprofile
        from ui import quickimages
        b = userprofile.ensure(self.ctrl.settings).get("back")
        key = f"tback_{b}"
        if key not in _BACKS:
            _BACKS[key] = quickimages.keep(key, userprofile.back_pixmap(b, 240).toImage())
        return _BACKS[key]

    @QtCore.Property(str, notify=changed)
    def status(self):
        game = self.game
        if game is None:
            return ""
        parts = [tr(f"Turn {game.turn}"), tr(f"{len(game.library)} cards in the library")]
        if game.to_bottom:
            parts.append(tr(f"Click {game.to_bottom} card(s) in your hand to put them on the bottom"))
        elif game.choosing:   # Lorcana mulligan
            parts.append(tr(f"Click the cards to put on the bottom ({len(game.aside)} chosen) – then “Done”"))
        elif game.mulligans and decks._G.playtest.get("mulligan") == "bottom_any":
            parts.append(tr(f"Mulligan: {game.swapped} card(s) swapped"))
        elif game.mulligans and decks._G.playtest.get("mulligan") == "basic":
            parts.append(tr(f"{game.mulligans}× no Basic Pokémon – your opponent may draw {game.mulligans} extra"))
        elif game.mulligans:
            parts.append(tr(f"Mulligan {game.mulligans}×"))
        if decks._G.playtest.get("don"):   # games with DON!!
            parts.append(tr(f"DON!! {game.don} of {decks._G.playtest['don']}"))
        return "   ·   ".join(parts)

    @QtCore.Property(str, notify=changed)
    def prizeLabel(self):
        """Face-down zone: Prize cards (Pokémon) or Life (games with a Leader)."""
        return tr("Life") if decks._G.playtest.get("life") else tr("Prize cards")

    @QtCore.Slot()
    def newGame(self):
        if self.game is not None:
            self.game.new_game()
        else:
            self._table()
        self.changed.emit()

    @QtCore.Slot()
    def draw(self):
        if self.game is not None:
            self.game.draw()
            self.changed.emit()

    @QtCore.Slot()
    def nextTurn(self):
        if self.game is not None:
            self.game.next_turn()
            self.changed.emit()

    @QtCore.Slot()
    def mulligan(self):
        if self.game is not None:
            self.game.mulligan()
            self.changed.emit()

    @QtCore.Slot(int)
    def handClicked(self, i):
        """London mulligan: a click puts the card on the bottom (while cards still have to go); Lorcana: sets it aside."""
        if self.game is not None and (self.game.to_bottom or self.game.choosing):
            self.game.put_back(i)
            self.changed.emit()

    @QtCore.Slot(int)
    def takePrize(self, i):
        if self.game is not None:
            self.game.take_prize(i)
            self.changed.emit()

    @QtCore.Slot(str, int, str)
    def move(self, zone_from, i, zone_to):
        if self.game is not None and self.game.move(zone_from, i, zone_to):
            self.changed.emit()

    # ---------- form ----------
    def _build(self, ui):
        all_decks = self._decks()
        if not all_decks:
            # 4.3 (STREAMLINE-INVENTUR): no dead end – straight to Decks / Import, with „← back“ to Play
            return ui.col([ui.note(tr("No decks yet – build one under “Decks” or import a list, then test it here.")),
                           ui.row([ui.button(tr("Decks"), lambda: self.ctrl.stream.show_page("decks", back=True)),
                                   ui.button(tr("Import deck list"), lambda: self.ctrl.show_import("deck")),
                                   ui.stretch()])])
        if self.deck_id not in {d["id"] for d in all_decks}:
            # the most recently changed deck WITH cards (an empty "New deck" only if all are empty)
            self.deck_id = max(all_decks, key=lambda d: (bool(d.get("cards")), d.get("updated", 0)))["id"]
        deck = next(d for d in all_decks if d["id"] == self.deck_id)
        picker = ui.row([ui.button(d["name"], lambda i=d["id"]: self.pick(i), active=d["id"] == self.deck_id)
                         for d in sorted(all_decks, key=lambda d: -d.get("updated", 0))[:14]] + [ui.stretch()],
                        spacing=6)
        lib, extra = self.library(deck)
        if not lib:
            return ui.col([picker, ui.note(tr("This deck has no cards yet."))], spacing=12)
        return ui.col([picker], spacing=0)   # the table itself is QML – here only the deck picker
