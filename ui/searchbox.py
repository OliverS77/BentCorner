"""Search of the Library and the deck builder – without widgets.

Search field (with syntax), advanced search in sections (sets, colors, display/deck options, values, ownership, text ·
card type, supertype, subtype, keywords, rarity, legal in) and chips of the active filters with "Undo".
Everything is drawn in Qt Quick (qadvsearch.py / AdvSearch.qml, chips via qlibrary.read_chips).
SearchBox.filters() returns the filters for carddb – exactly like the widget class of the same name in libview did.
"""
import datetime
import re
import time

from PySide6 import QtCore, QtGui

from cards import carddb
import games
from cards import library
from collection.collection import ALL_LANGS, LANGS, lang_short
from system.i18n import tr

RARITY = {k: v for k, v in games.current().rarities if k != "bonus"}   # filter: "Bonus" is too rare
COLOR_CODES = tuple(games.current().palette + games.current().color_specials)


def _game_changed():
    """Game switched: values of the advanced search from the game description (lists updated in place – other
    modules have imported them)."""
    global COLOR_CODES
    g = games.current()
    RARITY.clear()
    RARITY.update({k: v for k, v in g.rarities if k != "bonus"})
    COLOR_CODES = tuple(g.palette + g.color_specials)
    RANGES[:] = [tuple(r) for r in g.ranges]
    TEXT_FIELD_LABELS[:] = [tuple(t) for t in g.text_fields]


def adv_title(key, default):
    """Heading of an advanced-search section – the game can rename it (Pokémon: "Energietyp")."""
    return tr(games.current().adv_titles.get(key) or default)


def adv_hint(key):
    """Example in an advanced-search input field – per game (games.<game>.adv_hints)."""
    g = games.current()
    return tr(g.adv_hints.get(key) or type(g).__mro__[-2].adv_hints.get(key, ""))


def eur(v):
    return "–" if v is None else f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------- small states (instead of button, checkbox, selection list) ----------
class Toggle(QtCore.QObject):
    """On/off with text and tooltip (instead of QCheckBox / QToolButton). Signal toggled(on)."""
    toggled = QtCore.Signal(bool)

    def __init__(self, text="", checked=False, tip="", parent=None):
        super().__init__(parent)
        self._text, self._on, self._tip, self._hidden, self._enabled = text, bool(checked), tip, False, True
        self.props = {}

    def text(self):
        return self._text

    def setText(self, t):
        self._text = t

    def toolTip(self):
        return self._tip

    def setToolTip(self, t):
        self._tip = t or ""

    def isChecked(self):
        return self._on

    def setChecked(self, on):
        on = bool(on)
        if on != self._on:
            self._on = on
            self.toggled.emit(on)

    def toggle(self):
        self.setChecked(not self._on)

    def click(self):
        self.toggle()

    def isHidden(self):
        return self._hidden

    def setVisible(self, on):
        self._hidden = not on

    def hide(self):
        self._hidden = True

    def show(self):
        self._hidden = False

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, on):
        self._enabled = bool(on)

    def property(self, name):
        return self.props.get(name)

    def setProperty(self, name, value):
        self.props[name] = value


class Mode(QtCore.QObject):
    """Choice from [(label, value)] (instead of QComboBox). Signal currentIndexChanged(i)."""
    currentIndexChanged = QtCore.Signal(int)

    def __init__(self, items=(), parent=None):
        super().__init__(parent)
        self.items, self._i, self._enabled, self._tip = list(items), 0 if items else -1, True, ""

    def addItem(self, label, data=None):
        self.items.append((label, data))
        if self._i < 0:
            self._i = 0

    def currentIndex(self):
        return self._i

    def setCurrentIndex(self, i):
        i = int(i)
        if 0 <= i < len(self.items) and i != self._i:
            self._i = i
            self.currentIndexChanged.emit(i)

    def currentData(self):
        return self.items[self._i][1] if 0 <= self._i < len(self.items) else None

    def currentText(self):
        return self.items[self._i][0] if 0 <= self._i < len(self.items) else ""

    def findData(self, d):
        return next((i for i, (_, x) in enumerate(self.items) if x == d), -1)

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, on):
        self._enabled = bool(on)

    def setToolTip(self, t):
        self._tip = t


class Tri(QtCore.QObject):
    """Advanced-search entry: 0 = off, 1 = required (check), 2 = exclude (red ✕). binary: only on ⇄ off.
    prev = state before the first click of a double click."""
    stateChanged = QtCore.Signal(int)

    def __init__(self, label, binary=False, parent=None):
        super().__init__(parent)
        self.label, self.binary, self.state, self.prev = label, binary, 0, 0

    def text(self):
        return self.label

    def set_state(self, state, emit=True):
        state = int(state)
        if state == self.state:
            return
        self.state = state
        if emit:
            self.stateChanged.emit(state)

    def click(self):
        self.set_state((2 if self.state == 1 else 1) if self.binary else (self.state + 1) % 3)


class Number(QtCore.QObject):
    """Number with "not set" = -1 (instead of QDoubleSpinBox)."""
    valueChanged = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._v = -1.0

    def value(self):
        return self._v

    def setValue(self, v):
        v = float(v)
        if v != self._v:
            self._v = v
            self.valueChanged.emit(v)


class Steps(QtCore.QObject):
    """Slider in steps (instead of StepSlider): value, set_value(n)."""
    valueChanged = QtCore.Signal(int)

    def __init__(self, lo, hi, value, parent=None):
        super().__init__(parent)
        self.lo, self.hi, self.value = lo, hi, value

    def set_value(self, n, emit=True):
        n = max(self.lo, min(self.hi, int(n)))
        if n != self.value:
            self.value = n
            if emit:
                self.valueChanged.emit(n)


# ---------- Sections ----------
class Section(QtCore.QObject):
    """Advanced-search section: the check in the header (check) switches it on/off – the selection inside stays –,
    "Reset" resets it. toggle=False: always active (display/deck options)."""
    changed = QtCore.Signal()

    def __init__(self, title, toggle=True):
        super().__init__()
        self.toggle = toggle
        self.check = Toggle(title, False, tr("Section on/off – the selection inside is kept"), self)
        self.check.toggled.connect(lambda _: self.changed.emit())
        self._enabled = True

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, on):
        if bool(on) != self._enabled:
            self._enabled = bool(on)
            self.changed.emit()

    @property
    def active(self):
        return self.check.isChecked() or not self.toggle

    def touched(self):
        """Entry changed: switch the section on if something is selected."""
        if self.has_selection() and not self.check.isChecked():
            self.check.setChecked(True)  # emits changed
        else:
            self.changed.emit()

    def mode_choice(self):
        m = Mode([(tr("at least one of them"), "any"), (tr("all at once"), "all")], self)
        m.currentIndexChanged.connect(lambda _: self.changed.emit())
        return m

    # by subclasses
    def has_selection(self):
        return False

    def reset(self):
        pass

    def chips(self, *_):
        return []


def _state_chips(prefix, items, unset):
    """Chips for checks ("Type: Creature") and exclusions ("Type: ≠ Land")."""
    return [(f"{prefix}: {'≠ ' if state == 2 else ''}{label}", lambda v=value: unset(v))
            for value, label, state in items if state]


class CheckSection(Section):
    keep_active = True  # active from the start (and after "Clear all filters") – without a selection it filters nothing

    def __init__(self, title, items, columns=1, mode=False):
        super().__init__(title)
        self.columns = columns
        self.boxes = {}
        for value, label in items:
            cb = Tri(label, parent=self)
            cb.stateChanged.connect(lambda _: self.touched())
            self.boxes[value] = (cb, label)
        self.mode = self.mode_choice() if mode else None
        self.check.setChecked(True)

    def values(self):
        return [v for v, (cb, _) in self.boxes.items() if cb.state == 1]

    def excluded(self):
        return [v for v, (cb, _) in self.boxes.items() if cb.state == 2]

    def has_selection(self):
        return any(cb.state for cb, _ in self.boxes.values())

    def set_value(self, value, state=1):
        """state: 1/True = check, 2 = exclude, 0/False = off."""
        if value in self.boxes:
            self.boxes[value][0].set_state(int(state))

    def reset(self):
        for cb, _ in self.boxes.values():
            cb.set_state(0, emit=False)
        self.changed.emit()

    def solo(self, value, cycle=False):
        """Double click: only this entry (check, all others ✕). Again: all except this one (✕, the others
        neutral or, for types, on). Like "Solo" on a mixing desk or Alt-clicking the eye in Photoshop."""
        if value not in self.boxes:
            return
        me = self.boxes[value][0]
        rest = 1 if me.binary else 0
        others = [cb for v, (cb, _) in self.boxes.items() if v != value]
        only = cycle and me.prev == 1 and all(cb.state == 2 for cb in others)
        me.set_state(2 if only else 1, emit=False)
        for cb in others:
            cb.set_state(rest if only else 2, emit=False)
        self.touched()

    def chips(self, prefix):
        return _state_chips(prefix, [(v, label, cb.state) for v, (cb, label) in self.boxes.items()],
                            lambda v: self.set_value(v, 0))


class TypeSection(CheckSection):
    """Card types: each type on (check) or off (red ✕) – off = hidden. Default and "Reset": all on except
    default_off. Double click on a type = show only that one."""
    keep_active = True

    def __init__(self, title, items, columns=2, default_off=("Land",)):
        super().__init__(title, items, columns=columns, mode=False)
        self.default_off = tuple(default_off)
        for cb, _ in self.boxes.values():
            cb.binary = True
        self.reset(emit=False)
        self.check.setChecked(True)

    def values(self):
        return []  # no "required" – only exclusions

    def reset(self, *_, emit=True):
        for v, (cb, _) in self.boxes.items():
            cb.set_state(2 if v in self.default_off else 1, emit=False)
        if emit:
            self.changed.emit()

    def set_value(self, value, state=1):
        """1 = on, 2 = off; 0 (e.g. chip removed) = on again."""
        if value in self.boxes:
            self.boxes[value][0].set_state(2 if int(state) == 2 else 1)

    def has_selection(self):
        return any(cb.state == 2 for cb, _ in self.boxes.values())

    def chips(self, prefix):
        off = [(v, label) for v, (cb, label) in self.boxes.items() if cb.state == 2]
        on = [(v, label) for v, (cb, label) in self.boxes.items() if cb.state != 2]
        if off and len(off) > len(self.boxes) / 2 and on:  # mostly off: better show what is left
            def drop(v):
                if sum(1 for cb, _ in self.boxes.values() if cb.state != 2) <= 1:
                    self.reset()  # the last one – then everything again
                else:
                    self.set_value(v, 2)
            return [(f"{prefix}: {label}", lambda v=v: drop(v)) for v, label in on]
        return _state_chips(prefix, [(v, label, 2) for v, label in off], lambda v: self.set_value(v, 1))


class FormatSection(TypeSection):
    """Legal in: each format on/off, start: all on (= no filter). Otherwise: legal in at least one of the checked."""

    def any_of(self):
        on = [v for v, (cb, _) in self.boxes.items() if cb.state != 2]
        if len(on) == len(self.boxes):
            return None
        return on or ["-"]  # none on: nothing matches

    def excluded(self):
        return []

    def chips(self, prefix):
        on = self.any_of()
        if on is None:
            return []
        labels = {v: label for v, (_, label) in self.boxes.items()}

        def drop(v):  # take out only this format; the last one -> all again (= no filter)
            if sum(1 for cb, _ in self.boxes.values() if cb.state != 2) <= 1:
                self.reset()
            else:
                self.set_value(v, 2)
        return [(f"{prefix}: {labels.get(v, v)}", lambda v=v: drop(v)) for v in on if v in labels] or \
            [(f"{prefix}: {tr('keins')}", self.reset)]


class ListSection(Section):
    """Long list (subtypes, keywords): suggestions while typing (qadvsearch.listSuggest), selection as a tag –
    1 = required, 2 = exclude. "-Name" + Enter excludes."""

    def __init__(self, title, placeholder):
        super().__init__(title)
        self.placeholder = placeholder
        self.mode = self.mode_choice()
        self.states, self.vocab = {}, []  # name -> 1 (required) / 2 (exclude), in click order

    def set_vocab(self, vocab):
        self.vocab = vocab

    def values(self):
        return [n for n, s in self.states.items() if s == 1]

    def excluded(self):
        return [n for n, s in self.states.items() if s == 2]

    def has_selection(self):
        return bool(self.states)

    def set_value(self, name, state=1):
        """state: 1/True = required, 2 = exclude, 0/False = off."""
        state = int(state)
        if state:
            self.states[name] = state
        else:
            self.states.pop(name, None)
        self.touched()

    def reset(self):
        self.states = {}
        self.changed.emit()

    def chips(self, prefix):
        return _state_chips(prefix, [(n, n, s) for n, s in self.states.items()], lambda n: self.set_value(n, 0))


RANGES = [tuple(r) for r in games.current().ranges]   # [(key, name, decimal places)] – per game


class RangeSection(Section):
    def __init__(self):
        super().__init__(tr("Values"))
        self.spins = {}
        for key, _, _ in RANGES:
            pair = [Number(self), Number(self)]
            for sp in pair:
                sp.valueChanged.connect(lambda _: self.touched())
            self.spins[key] = pair

    def ranges(self):
        out = {}
        for key, (lo, hi) in self.spins.items():
            a = lo.value() if lo.value() >= 0 else None
            b = hi.value() if hi.value() >= 0 else None
            if a is not None or b is not None:
                out[key] = (a, b)
        return out

    def has_selection(self):
        return bool(self.ranges())

    def set_range(self, key, lo=None, hi=None):
        a, b = self.spins[key]
        for sp, v in ((a, lo), (b, hi)):
            sp.blockSignals(True)
            sp.setValue(-1 if v is None else v)
            sp.blockSignals(False)
        self.touched()

    def reset(self):
        for a, b in self.spins.values():
            for sp in (a, b):
                sp.blockSignals(True)
                sp.setValue(-1)
                sp.blockSignals(False)
        self.changed.emit()

    def chips(self):
        out = []
        for key, (lo, hi) in self.ranges().items():
            label = tr(dict((k, lab) for k, lab, _ in RANGES)[key]).replace(" (€)", "")
            fmt = (lambda v: eur(v)) if key == "price" else (lambda v: f"{v:g}")
            if lo is not None and hi is not None:
                text = f"{label} {fmt(lo)}" if lo == hi else f"{label} {fmt(lo)}–{fmt(hi)}"
            elif lo is not None:
                text = f"{label} ≥ {fmt(lo)}"
            else:
                text = f"{label} ≤ {fmt(hi)}"
            out.append((text, lambda k=key: self.set_range(k)))
        return out


TEXT_FIELD_LABELS = [tuple(t) for t in games.current().text_fields]


class CountSection(Section):
    """How many copies of the card you own: slider 1 · 2 · 3 · 4 · 4+ and "at least" / "exactly" (4 = exactly or at
    least four, 4+ = more than four – some people want exactly one playset)."""
    LABELS = ["1", "2", "3", "4", "4+"]
    MORE = 5   # step "4+"

    def __init__(self):
        super().__init__(tr("Besitz"))
        self.slider = Steps(1, self.MORE, 1, self)
        self.slider.valueChanged.connect(lambda _: self._touch())
        self.mode = Mode([(tr("at least"), "min"), (tr("exactly"), "exact")], self)
        self.mode.currentIndexChanged.connect(lambda _: self._touch())

    def _touch(self):
        if not self.check.isChecked():
            self.check.setChecked(True)
        else:
            self.changed.emit()

    def has_selection(self):
        return True

    def owned(self):
        return self.slider.value, self.mode.currentData()

    @classmethod
    def matches(cls, count, n, mode):
        if n >= cls.MORE:   # "4+": more than four
            return count > 4
        if mode == "exact":
            return count == n
        return count >= n

    def reset(self):
        self.slider.set_value(1, emit=False)
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(0)
        self.mode.blockSignals(False)
        self.changed.emit()

    def chips(self):
        n, mode = self.owned()
        if n >= self.MORE:
            return [(tr("Owned > 4×"), lambda: self.check.setChecked(False))]
        sign = "=" if mode == "exact" else "≥"
        return [(tr(f"Owned {sign} {n}×"), lambda: self.check.setChecked(False))]


class SetSection(Section):
    """Sets (several possible); from two sets on: OR = in one of them, AND = printed in all of them."""

    def __init__(self):
        super().__init__(tr("Sets"))
        self.codes, self.db_items = [], []
        self.source = lambda: []  # set list (Scryfall catalog), set by the SearchBox
        self.mode = Mode([(tr("Sets: OR (in one of them)"), "or"), (tr("Sets: AND (in all)"), "and")], self)
        self.mode.setEnabled(False)
        self.mode.currentIndexChanged.connect(lambda _: self.changed.emit())

    def fill(self, items):
        """Sets from the card database (fallback if the Scryfall set list is missing)."""
        self.db_items = items

    def sets(self):
        cat = self.source()
        if cat:
            return cat
        return [{"code": c, "name": n, "released": "", "count": 0, "type": "", "parent": None}
                for c, n in self.db_items]

    def add_codes(self, codes):
        for code in codes:
            if code not in self.codes:
                self.codes.append(code)
        self._update()
        self.touched()

    def set_set(self, code, on=True):
        code = code.lower()
        if on and code not in self.codes:
            self.codes.append(code)
        elif not on and code in self.codes:
            self.codes.remove(code)
        self._update()
        self.touched()

    def _update(self):
        self.mode.setEnabled(len(self.codes) > 1)

    def has_selection(self):
        return bool(self.codes)

    def reset(self):
        self.codes = []
        self._update()
        self.changed.emit()


class ColorSection(Section):
    """Colors W U B R G, colorless (C), multicolored (M) with contains / exactly / at most."""

    def __init__(self):
        super().__init__(adv_title("colors", "Farben"))
        self.btns = {}
        g = games.current()
        for code in COLOR_CODES:
            tip = tr(g.color_names[code]) if code in g.color_names else (
                {"C": tr("colorless"), "M": tr("multicolored")}.get(code, tr(f"Farbe {code}")))
            if code in g.palette:
                tip += tr(" · double-click = exactly this color, again = without this color")
            b = Toggle(code, False, tip, self)
            b.toggled.connect(lambda _: self.touched())
            self.btns[code] = b
        self.mode = Mode([(tr("includes"), "any"), (tr("exactly"), "exact"), (tr("at most"), "atmost")], self)
        self.mode.currentIndexChanged.connect(lambda _: self.changed.emit())

    def colors(self):
        return "".join(c for c, b in self.btns.items() if b.isChecked())

    def has_selection(self):
        return bool(self.colors())

    def set_colors(self, colors, mode="any"):
        for code, b in self.btns.items():
            b.blockSignals(True)
            b.setChecked(code in colors)
            b.blockSignals(False)
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(max(0, self.mode.findData(mode)))
        self.mode.blockSignals(False)
        self.touched()

    def reset(self):
        for b in self.btns.values():
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        self.changed.emit()

    def chips(self):
        cols = self.colors()
        if not cols:
            return []
        pal = games.current().palette
        title = self.check.text()
        wubrg = "".join(c for c in cols if c in pal)
        if self.mode.currentData() == "atmost" and len(wubrg) == len(pal) - 1 and "M" not in cols:  # double click
            return [(title + tr(": without ") + next(c for c in pal if c not in wubrg), self.reset)]
        return [(tr(f"{title} {self.mode.currentText()}: {cols}"), self.reset)]


class LangChips(QtCore.QObject):
    """The "Only cards in …" filter: languages, several selectable (none selected = all). Languages that occur in
    the collection come first (order); the others are paler (present = "false")."""
    changed = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._mode, self._hidden = "or", False
        self.btns = {}
        for code, short, name in ALL_LANGS:   # buttons for all languages; the game's languages are shown (order)
            b = Toggle(short, False, name, self)
            b.toggled.connect(lambda _: self.changed.emit())
            self.btns[code] = b
        self.order = [c for c, *_ in LANGS]

    def isHidden(self):
        return self._hidden

    def setVisible(self, on):
        self._hidden = not on

    def selected(self):
        here = {c for c, *_ in LANGS}
        return {c for c, b in self.btns.items() if b.isChecked() and c in here}

    def mode(self):
        return self._mode

    def set_mode(self, mode):
        mode = "and" if mode == "and" else "or"
        if mode != self._mode:
            self._mode = mode
            self.changed.emit()

    def set_lang(self, code, on=True):
        if code in self.btns:
            self.btns[code].setChecked(on)

    def set_present(self, counts):
        """counts: {language: number of owned cards} – present ones first, with the count in the tooltip."""
        names = {c: n for c, _, n in LANGS}
        codes = [x for x, *_ in LANGS]
        self.order = sorted(codes, key=lambda c: (counts.get(c, 0) == 0, codes.index(c)))
        for c in self.order:
            b, n = self.btns[c], counts.get(c, 0)
            b.setProperty("present", "true" if n else "false")
            b.setToolTip(f"{names[c]} · {n} " + tr("Cards") if n else names[c] + " · " + tr("no cards of your own"))

    def reset(self):
        for b in self.btns.values():
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        self.changed.emit()


class FoilChoice(QtCore.QObject):
    """Foil: any / foil only / no foil. isChecked() = "foil only" (old interface)."""
    toggled = QtCore.Signal(bool)

    def __init__(self):
        super().__init__()
        self.mode, self._hidden = "any", False

    def set_mode(self, mode):
        mode = mode if mode in ("any", "only", "none") else "any"
        if mode != self.mode:
            self.mode = mode
            self.toggled.emit(self.isChecked())

    def isChecked(self):
        return self.mode == "only"

    def isHidden(self):
        return self._hidden

    def setVisible(self, on):
        self._hidden = not on

    def reset(self):
        self.set_mode("any")


class OptionSection(Section):
    """Settings without on/off (Library display or deck options)."""

    def __init__(self, title):
        super().__init__(title, toggle=False)
        self.items = []

    def add(self, item):
        self.items.append(item)
        return item

    def reset(self):
        for w in self.items:
            if isinstance(w, Toggle):
                w.setChecked(False)
            elif isinstance(w, LangChips):
                w.reset()
            elif isinstance(w, FoilChoice):
                w.blockSignals(True)
                w.reset()
                w.blockSignals(False)
        self.changed.emit()


class TextSection(Section):
    """Exact phrases: "Rules text contains …", also excluding ("does not contain")."""

    def __init__(self):
        super().__init__(tr("Text contains"))
        self.texts = []

    def add(self, field, text, neg=False):
        if (field, text, neg) not in self.texts:
            self.texts.append((field, text, neg))
        self.touched()

    def remove(self, entry):
        if entry in self.texts:
            self.texts.remove(entry)
        self.touched()

    def has_selection(self):
        return bool(self.texts)

    def reset(self):
        self.texts = []
        self.changed.emit()

    def chips(self):
        labels = dict(TEXT_FIELD_LABELS)
        return [((tr("without ") if neg else "") + f"{tr(labels[field])}: „{text}“", lambda e=(field, text, neg): self.remove(e))
                for field, text, neg in self.texts]


# ---------- Search syntax in the search field ----------
SYNTAX_HELP = (
    "Suchfeld-Syntax (Enter macht daraus Chips):\n"
    "  t:elf  t:creature  t:legendary   Typ / Untertyp / Übertyp\n"
    "  k:flying                         Keyword\n"
    "  o:\"draw a card\"                  Regeltext enthält\n"
    "  n:dragon  a:\"john avon\"  ft:…    Name / Künstler / Flavor-Text\n"
    "  c:rg  c=rg  c<=rg                Farben: enthält / genau / höchstens (w u b r g c m)\n"
    "  mv>=3  pow>4  tou<=2  eur<5      Manawert, Stärke, Widerstand, Preis\n"
    "  r:mythic  s:fin  f:modern        Seltenheit, Set, legal in Format\n"
    "  year:1999  year>=2020  … 1999    Erscheinungsjahr des Drucks\n"
    "  -o:flying  -t:land  -r:common    Minus davor = ausschließen (rotes ✕)\n"
    "Alles andere wird als freier Text in Name, Regeltext, Typ, Künstler … gesucht.")
_TOKEN = re.compile(r'(-?)([a-zA-Z]+)(>=|<=|:|=|>|<)("([^"]*)"|\S+)')
_KEYS = {"t": "type", "type": "type", "o": "oracle", "oracle": "oracle", "text": "oracle", "k": "kw", "kw": "kw",
         "keyword": "kw", "n": "name", "name": "name", "a": "artist", "artist": "artist", "ft": "flavor",
         "flavor": "flavor", "r": "rarity", "rarity": "rarity", "f": "format", "format": "format", "legal": "format",
         "s": "set", "e": "set", "set": "set", "c": "color", "color": "color", "i": "color", "ink": "color",
         "mv": "mv", "cmc": "mv",
         "pow": "pow", "power": "pow", "tou": "tou", "toughness": "tou", "eur": "price", "preis": "price",
         "price": "price", "year": "year", "jahr": "year"}
_RAR = {"c": "common", "u": "uncommon", "r": "rare", "m": "mythic", "s": "special"}


def parse_query(text):
    """Search text -> (list of criteria, remaining free text). Criterion: (kind, value, exclude?, operator)."""
    crit, rest, pos = [], [], 0
    for m in _TOKEN.finditer(text):
        key = _KEYS.get(m.group(2).lower())
        if key is None:
            continue
        rest.append(text[pos:m.start()])
        pos = m.end()
        value = m.group(5) if m.group(5) is not None else m.group(4)
        crit.append((key, value, m.group(1) == "-", m.group(3)))
    rest.append(text[pos:])
    return crit, " ".join("".join(rest).split())


_NUM = re.compile(r"^#?(\d{1,4}[a-z★]?)(?:/\d{1,4})?$", re.I)   # "7", "#7", "007/234" (as on the card)
# numbers with letters in front: Yu-Gi-Oh! "EN008" (from RA01-EN008), Pokémon "TG12", "SWSH286" – only count if the
# word is not a set code ("m21" stays the set)
_LNUM = re.compile(r"^#?([a-z]{1,4}\d{1,4}[a-z]?)$", re.I)


def _num_of(word, codes):
    """Word -> collector number or None (codes: known set codes, lowercase)."""
    m = _NUM.match(word)
    if m:
        return m.group(1)
    m = _LNUM.match(word)
    if m and word.lower().lstrip("#") not in codes:
        return m.group(1)
    return None
_SET_NAMES = {"key": None, "map": {}}


def _norm(s):
    """Make set names comparable: lowercase, "&"/punctuation removed – "Sonne & Mond" = "sonne mond"."""
    return " ".join(re.sub(r"[^\w]+", " ", (s or "").lower().replace("&", " ")).split())


def set_name_index():
    """{normalized set name: code} – English from the card database, other languages from the data pack
    (setnames.json: Magic from MTGJSON, Pokémon from TCGdex). Newest sets win on equal names."""
    import games
    from cards import packs
    key = (games.current().key, str(carddb.DB_PATH))
    if _SET_NAMES["key"] == key:
        return _SET_NAMES["map"]
    out = {}
    try:
        sets = carddb.all_sets() if carddb.exists() else []
    except Exception:  # noqa: BLE001
        sets = []
    for code, name, *_ in sets:
        n = _norm(name)
        if n and n not in out:
            out[n] = code.lower()
    g = games.current().key
    path = packs.path_of(g, "setnames.json") if g in packs.PACKS else None
    if path:
        try:
            import json
            for code, names in json.loads(path.read_text("utf-8")).items():
                for name in names.values():
                    n = _norm(name)
                    if n and n not in out:
                        out[n] = code.lower()
        except (OSError, ValueError):
            pass
    for code, names in games.current().set_names().items():   # e.g. Lorcana: names in EN DE FR IT from the database
        for name in names.values():
            n = _norm(name)
            if n and n not in out:
                out[n] = code.lower()
    _SET_NAMES.update(key=key, map=out)
    return out


def _is_card_name(text):
    """Is a card called that (in English or printed in another language)?"""
    if not carddb.exists():
        return False
    try:
        with carddb.connection() as con:   # case doesn't matter ("time spiral" = "Time Spiral")
            hit = con.execute("SELECT 1 FROM cards WHERE name = ? COLLATE NOCASE LIMIT 1", (text,)).fetchone()
        return bool(hit or any(n.lower() == text.lower() for n in carddb.names_by_printed(text, limit=5)))
    except Exception:  # noqa: BLE001
        return False


def split_set_name(text):
    """Matches "sonne mond 7", "final fantasy #7", "Pikachu sun moon", "Welten im Wandel 076/236" -> (code, number,
    rest) – a spelled-out set name in any language, anywhere in the search text. None if none matches. A one-word set
    name only counts with a number or on its own; if a card is named exactly like the set (e.g. "Time Spiral"), it
    stays a card search."""
    words = text.split()
    num = next((w for w in words if _NUM.match(w)), None)
    rem = _norm(" ".join(w for w in words if w is not num)).split()
    names = set_name_index() if rem else {}
    for size in range(len(rem), 0, -1):   # longest match first ("final fantasy commander" before "final fantasy")
        for i in range(len(rem) - size + 1):
            code = names.get(" ".join(rem[i:i + size]))
            if code is None:
                continue
            rest = rem[:i] + rem[i + size:]
            if size == 1 and not num and rest and not _is_card_name(" ".join(rest)):
                continue   # a single word is only a set if the rest is a card ("glurak grundset")
            if not rest and not num and _is_card_name(" ".join(rem)):
                return None   # a card has that name: card search
            return code, (_NUM.match(num).group(1) if num else None), " ".join(rest)
    return None


_YEAR = re.compile(r"^(19[89]\d|20\d\d)$")


def split_year(text):
    """Free text with a four-digit year -> (year, rest): "glurak 1999" = Glurak printed in 1999 (release year), also
    "1999" alone. Not if the whole text is (the start of) a card name ("1996 World Champion") or the year stands next
    to a set code ("sld 1999" = number 1999 of Secret Lair). -> (int or None, text)"""
    words = text.split()
    years = [w for w in words if _YEAR.match(w) and int(w) <= datetime.date.today().year + 1]
    if len(years) != 1:
        return None, text
    rest = [w for w in words if w is not years[0]]
    if carddb.exists():
        codes = carddb.set_codes()
        if any(w.lower().lstrip("#") in codes for w in rest) or _name_starts(text):
            return None, text
    return int(years[0]), " ".join(rest)


def split_print_query(text):
    """Free search text -> (set code or None, number or None, rest). "sos" alone = set, "001" / "001/236" = number
    from any set, "sos 123" = exactly this card, spelled-out set names in any language ("sonne mond 7") as well.
    A set CODE only counts alone or together with a number (otherwise e.g. "war of the spark" would be a set filter
    on the code "war") – whole set names, however, also next to a card name."""
    found = _split_code(text)
    if found[0] is None and found[1] is None:
        named = split_set_name(text)
        if named:
            return named
        mixed = _split_name_print(text)
        if mixed:
            return mixed
    return found


def _split_name_print(text):
    """Card name + number and/or set code in any order: "lucario 27", "27 lucario", "pikachu sv8",
    "glurak sv3 6" – for all games (the set is not always on the card, the number usually is). Only if the
    rest looks like the start of a card name and the whole text itself is not a card name ("Pikachu ex" stays
    a card search). -> (code or None, number or None, rest) or None"""
    words = text.split()
    if len(words) < 2 or not carddb.exists():
        return None
    codes = carddb.set_codes()
    code = num = None
    rest, digits = [], []
    for w in words:
        lw = w.lower().lstrip("#")
        if lw.isdigit() and lw in codes:   # Lorcana: sets are numbers too ("1" … "14") – decided below
            digits.append(lw)
        elif code is None and lw in codes:
            code = lw
        elif num is None and _NUM.match(w):
            num = _NUM.match(w).group(1)
        else:
            rest.append(w)
    if digits:   # one number alone = the card number; two = as printed "5/204 • EN • 1": number, then set
        if num is None and len(digits) == 1 and code is None:
            num = digits[0]
        elif num is None and code is None:
            num, code = digits[0], digits[1]
        elif code is None:
            code = digits[0]
        elif num is None:
            num = digits[0]
        rest += digits[2:]
    if not rest or (code is None and num is None):
        return None
    name = " ".join(rest)
    if _name_starts(text) or not _name_starts(name):
        return None
    return code, num, name


def _name_starts(text):
    """Does a card name start like this (in English or printed in another language, case-insensitive)?"""
    try:
        with carddb.connection() as con:
            like = text.replace("\\", "").replace("%", "").replace("_", "") + "%"
            hit = con.execute("SELECT 1 FROM cards WHERE name LIKE ? LIMIT 1", (like,)).fetchone()
        return bool(hit or carddb.names_by_printed(text, limit=1))
    except Exception:  # noqa: BLE001
        return False


def _split_code(text):
    words = text.split()
    if len(words) == 1 and carddb.exists():  # "fic#19", "fic19", "fic-0019": set and number in one word
        w = words[0].lower()
        codes = carddb.set_codes()
        for i in range(min(len(w) - 1, 6), 1, -1):  # longest matching set code first ("m21" before "m2")
            code, rest = w[:i], w[i:].lstrip("#-.")
            if code in codes and rest and _NUM.match(rest) and rest[0].isdigit():
                return code, _NUM.match(rest).group(1), ""
            if code in codes and rest and _LNUM.match(rest):   # "ra01-en008" (Yu-Gi-Oh!), "swshp-swsh286"
                return code, _LNUM.match(rest).group(1), ""
    if not words or len(words) > 2:
        return None, None, text
    codes = carddb.set_codes() if carddb.exists() else set()
    num = next((w for w in words if _num_of(w, codes)), None)
    other = [w for w in words if w is not num]
    if len(other) > 1:
        return None, None, text
    code = other[0].lower() if other and other[0].lower() in codes else None
    if other and code is None:  # word is not a set code: normal search (a number only counts together with a set)
        return None, None, text
    return code, _num_of(num, codes) if num else None, ""


def _cap(s):
    return s[:1].upper() + s[1:].lower()


def _to_float(v):
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def search_placeholder():
    """Placeholder of the search field – with an example that works in the open game (no artist field: no artist)."""
    if has_artist():
        return tr(f"Search: name, rules text, type, artist, year … or syntax like {games.current().search_example}")
    return tr(f"Search: name, rules text, type, year … or syntax like {games.current().search_example}")


def has_artist():
    """Does the open game's card database know artists (Yu-Gi-Oh!: no)?"""
    return any(k == "artist" for k, _n in games.current().text_fields)


def card_search_placeholder():
    """Placeholder of the card search while scanning (CardSearch.qml)."""
    return tr("Search card: name, artist, year …") if has_artist() else tr("Search card: name, year …")


def color_letters(value):
    """c:/i: value -> color letters: words of the game ("amber", "amber,steel") or letters as in Magic ("rg")."""
    g = games.current()
    words = [w for w in re.split(r"[,/+]", value.lower()) if w]
    if g.color_words and words and all(w in g.color_words for w in words):
        return "".join(g.color_words[w] for w in words)
    return "".join(ch for ch in value.upper() if ch in g.palette + g.color_specials)


def apply_criterion(f, key, value, neg, op):
    """Apply a search-syntax criterion to the filter dict (live, without chips)."""
    if key in ("oracle", "name", "artist", "flavor"):
        f.setdefault("texts", []).append((key, value, neg))
    elif key == "type":
        v = _cap(value)
        k = "types" if v in carddb.CARD_TYPES else "supertypes" if v in carddb.SUPERTYPES else "subtypes"
        if neg:
            f.setdefault(f"not_{k}", []).append(v)
        else:
            f.setdefault(k, []).append(v)
            f.setdefault(f"{k}_mode", "all")
    elif key == "kw":
        if neg:
            f.setdefault("not_keywords", []).append(_cap(value))
        else:
            f.setdefault("keywords", []).append(_cap(value))
            f.setdefault("keywords_mode", "all")
    elif key == "rarity":
        f.setdefault("not_rarities" if neg else "rarities", []).append(
            _RAR.get(value.lower()[:1], value.lower()) if len(value) == 1 else value.lower())
    elif key == "format":
        f.setdefault("not_formats" if neg else "formats", []).append(value.lower())
    elif key == "set":
        f["set_codes"] = f.get("set_codes", []) + [value.lower()]
    elif key == "color":
        f["colors"] = color_letters(value)
        f["color_mode"] = {"=": "exact", "<=": "atmost", "<": "atmost"}.get(op, "any")
    elif key in ("mv", "pow", "tou", "price", "year"):
        v = _to_float(value)
        if v is None:
            return
        step = 0.01 if key == "price" else 1
        lo, hi = {">=": (v, None), ">": (v + step, None), "<=": (None, v), "<": (None, v - step)}.get(op, (v, v))
        f.setdefault("ranges", {})[key] = (lo, hi)


def reorder(order, key, target, before):
    """Move key before/after target."""
    order = [k for k in order if k != key]
    i = order.index(target) if target in order else len(order)
    order.insert(i if before else i + 1, key)
    return order


def merged_order(saved, keys):
    """Saved order, new keys appended at the end, vanished ones removed."""
    saved = [k for k in (saved or []) if k in keys]
    return saved + [k for k in keys if k not in saved]


def _base(title):
    """Title without the suffix in parentheses ("Sprache (UND)" -> "Sprache")."""
    return (title or "").split(" (")[0]


# ---------- State of a section (for "Undo") ----------
def _sec_get(sec):
    st = {"on": sec.check.isChecked()}
    mode = getattr(sec, "mode", None)
    if isinstance(mode, Mode):
        st["mode"] = mode.currentIndex()
    if hasattr(sec, "boxes"):
        st["boxes"] = {v: cb.state for v, (cb, _) in sec.boxes.items()}
    if isinstance(sec, ListSection):
        st["states"] = dict(sec.states)
    if isinstance(sec, SetSection):
        st["codes"] = list(sec.codes)
    if isinstance(sec, TextSection):
        st["texts"] = list(sec.texts)
    if isinstance(sec, RangeSection):
        st["spins"] = {k: (a.value(), b.value()) for k, (a, b) in sec.spins.items()}
    if isinstance(sec, CountSection):
        st["count"] = sec.slider.value
    if isinstance(sec, ColorSection):
        st["colors"] = {c: b.isChecked() for c, b in sec.btns.items()}
    return st


def _sec_set(sec, st):
    sec.blockSignals(True)
    try:
        mode = getattr(sec, "mode", None)
        if isinstance(mode, Mode) and "mode" in st:
            mode.blockSignals(True)
            mode.setCurrentIndex(st["mode"])
            mode.blockSignals(False)
        for v, state in (st.get("boxes") or {}).items():
            if v in sec.boxes:
                sec.boxes[v][0].set_state(state, emit=False)
        if isinstance(sec, ListSection) and "states" in st:
            sec.states = dict(st["states"])
        if isinstance(sec, SetSection) and "codes" in st:
            sec.codes = list(st["codes"])
            sec._update()
        if isinstance(sec, TextSection) and "texts" in st:
            sec.texts = list(st["texts"])
        if isinstance(sec, RangeSection):
            for k, (lo, hi) in (st.get("spins") or {}).items():
                for sp, v in zip(sec.spins[k], (lo, hi)):
                    sp.blockSignals(True)
                    sp.setValue(v)
                    sp.blockSignals(False)
        if isinstance(sec, CountSection) and "count" in st:
            sec.slider.set_value(st["count"], emit=False)
        if isinstance(sec, ColorSection):
            for c, on in (st.get("colors") or {}).items():
                sec.btns[c].blockSignals(True)
                sec.btns[c].setChecked(on)
                sec.btns[c].blockSignals(False)
        sec.check.blockSignals(True)
        sec.check.setChecked(st.get("on", sec.check.isChecked()))
        sec.check.blockSignals(False)
    finally:
        sec.blockSignals(False)


class SearchText(QtCore.QObject):
    """Text of the search field (instead of QLineEdit)."""
    textChanged = QtCore.Signal(str)

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self._text, self.placeholder = "", placeholder

    def text(self):
        return self._text

    def setText(self, t):
        t = t or ""
        if t != self._text:
            self._text = t
            self.textChanged.emit(t)

    def clear(self):
        self.setText("")

    def setPlaceholderText(self, t):
        self.placeholder = t

    def placeholderText(self):
        return self.placeholder


# ---------- The search ----------
class SearchBox(QtCore.QObject):
    """Search as in the Library: search field (with syntax), advanced search (expandable) and chips of the active
    filters. kind = "library" or "deck". Signal changed: filters changed (batched); chips_changed: chips are new."""
    changed = QtCore.Signal()
    chips_changed = QtCore.Signal()
    ROW1_H, ROW2_H = 245, 245
    ADV_MIN = 240    # minimum height of the open advanced search
    UNDO_HOLD = 2.5  # s: how long a removed chip stays grey with ↺
    FADE = 0.97      # s: grey chip fades out (0.5), waits (0.15), collapses (0.32) – like ChipBar.qml
    # relative widths ≈ what a section needs at 1600 px (title + "Reset" button, content); games can change them
    STRETCH = {"sets": 3, "colors": 3, "opts": 3, "range": 3, "count": 3, "text": 3, "types": 2.8, "super": 2.3,
               "sub": 2.4, "kw": 2.4, "rarity": 2.4, "format": 2.2, "reg": 2}

    def __init__(self, ctrl, kind="library"):
        super().__init__()
        self.ctrl, self.kind = ctrl, kind
        self.sets_loaded = self.vocab_loaded = False
        self.search = SearchText(search_placeholder(), self)
        self.adv_btn = Toggle("", False, "", self)
        self.adv_btn.toggled.connect(lambda _: self.update_adv_btn())
        self.sec_sets = SetSection()
        self.sec_sets.source = lambda: getattr(self.ctrl, "catalog_sets", None) or []
        self.sec_opts = OptionSection(tr("Display") if kind == "library" else tr("Deck"))
        g = self._game_sections()
        self.sec_colors, self.sec_types, self.sec_super = g["colors"], g["types"], g["super"]
        self.sec_sub = ListSection(adv_title("sub", "Untertyp"), adv_hint("sub"))
        self.sec_kw, self.sec_rarity, self.sec_range = g["kw"], g["rarity"], g["range"]
        self.sec_count = CountSection()
        self.sec_format = g["format"]
        self.sec_reg = g["reg"]
        self.sec_text = TextSection()
        self.sec_by_key = {"sets": self.sec_sets, "colors": self.sec_colors, "opts": self.sec_opts,
                           "range": self.sec_range, "count": self.sec_count, "text": self.sec_text,
                           "types": self.sec_types, "super": self.sec_super, "sub": self.sec_sub, "kw": self.sec_kw,
                           "rarity": self.sec_rarity, "format": self.sec_format, "reg": self.sec_reg}
        for sec in self.sec_by_key.values():
            sec.setParent(self)
            sec.changed.connect(self.filters_changed)
        self.order = merged_order(ctrl.settings.get("adv_order"), list(self.sec_by_key))
        self.sections = list(self.sec_by_key.values())
        self.adv_note = Toggle(tr("Advanced search needs the card database (Settings)."), parent=self)
        self.adv_note.hide()

        opt = self.sec_opts
        if kind == "library":
            self.lang_filter = LangChips()
            self.lang_filter.setParent(self)
            self.lang_filter.changed.connect(self.filters_changed)
            opt.add(self.lang_filter)
            self.foil_only = opt.add(FoilChoice())
            self.foil_only.setParent(self)
            self.own_lang = opt.add(Toggle(tr("images in own language"), False,
                                           tr("Default: all cards in English. Checked: owned copies in their language (images are loaded when needed)."), self))
            self.missing = opt.add(Toggle(tr("missing only"), False,
                                          tr("Only cards that are not in the collection yet (e.g. with a set filter)"),
                                          self))
            self.mark_owned = opt.add(Toggle(tr("dim missing"), False, "", self))
            # alt arts (Oliver, after 0.9.2): an option here instead of a tab at the top
            self.alt_only = opt.add(Toggle(tr("alt-arts only"), False,
                                           tr("Only alternative artworks by artists – they come via the Scan Studio "
                                              "(with the artists' permission)"), self))
            for w in (self.foil_only, self.missing, self.mark_owned, self.alt_only):
                w.toggled.connect(lambda _: self.filters_changed())
        else:
            self.ident = opt.add(Toggle(tr("matching color identity"), True,
                                        tr("Only cards matching the commander's color identity"), self))
            self.ident.toggled.connect(lambda _: self.filters_changed())

        self.timer = QtCore.QTimer(self, singleShot=True, interval=250, timeout=self.changed.emit)
        self.search.textChanged.connect(lambda _: self.timer.start())
        self.chips_data = []  # [{"title", "values": [(text, function, kind, uid)], "on_title", "grey", "undo_all"}]
        self.collapsing = set()  # uids (or ("g", uid) for whole boxes) that are currently fading out
        self._undo, self._cleared = [], None
        self.update_adv_btn()

    # --- Set list and vocabulary (computed once, then cached) ---
    def prepare(self):
        self.fill_sets()
        self.load_vocab()
        has_db = carddb.exists()
        self.sec_colors.setEnabled(has_db)
        self.adv_note.setVisible(self.adv_btn.isChecked() and not has_db)

    def fill_sets(self):
        if self.sets_loaded:
            return
        sets = carddb.all_sets(cached_only=True) if carddb.exists() else []
        if sets is None:  # first time: compute in the background, until then sets from collection/catalog
            from ui.librarycore import run_async
            run_async(self, carddb.all_sets, lambda res, err: self._fill_sets(res or []))
            sets = []
        self._fill_sets(sets)

    def _fill_sets(self, sets):
        if sets:
            self.sets_loaded = True
            items = [(c, n) for c, n, *_ in sets]
        else:
            names = {x["code"]: x["name"] for x in getattr(self.ctrl, "catalog_sets", None) or []}
            names.update({x["code"]: x["name"] for x in getattr(self.ctrl, "installed", None) or []})
            codes = sorted({it["set"].lower() for it in self.ctrl.collection.items} | set(names))
            items = [(c, names.get(c, c.upper())) for c in codes]
        self.sec_sets.fill(items)

    def load_vocab(self):
        if self.vocab_loaded or not carddb.exists():
            return
        voc = carddb.vocabulary(cached_only=True)
        if voc is None:
            from ui.librarycore import run_async
            run_async(self, carddb.vocabulary, lambda res, err: self._set_vocab(res))
        else:
            self._set_vocab(voc)

    def _set_vocab(self, voc):
        if not voc:
            return
        self.vocab_loaded = True
        self.sec_sub.set_vocab(voc["subtypes"])
        self.sec_kw.set_vocab(voc["keywords"])

    @property
    def set_codes(self):
        return self.sec_sets.codes

    def set_set(self, code, on=True):
        self.sec_sets.set_set(code, on)

    # --- Expand/collapse (Qt Quick animates) ---
    def section_dropped(self, key, target, before):
        self.order = reorder(self.order, key, target, before)
        self.ctrl.settings["adv_order"] = list(self.order)
        self.ctrl.settings_changed()
        other = self.other_box()
        if other is not None:  # Library and deck builder share the order
            other.order = list(self.order)
            other.changed.emit()

    def other_box(self):
        if self.kind == "library":
            page = getattr(self.ctrl, "deck_page", None)
            ed = getattr(page, "editor", None) if page is not None else None
            return getattr(ed, "bar", None)
        lib = getattr(self.ctrl, "library_win", None)
        return lib.bar if lib is not None else None

    def adv_height(self):
        saved = self.ctrl.settings.get(f"adv_h_{self.kind}")
        full = int(saved) if saved else self.ROW1_H + self.ROW2_H + 26
        return max(self.ADV_MIN, full)

    def _game_sections(self):
        """Sections whose content depends on the game (games.<game>: card_types, supertypes, rarities, legal_short,
        palette, ranges, adv_titles) – rebuilt at start and after every game switch."""
        g = games.current()
        off = tuple(t for t in g.lib_types_off if t in carddb.CARD_TYPES) if self.kind == "library" else ()
        sup = [(t, tr(carddb.SUPER_LABELS.get(t, t))) for t in carddb.SUPERTYPES]
        if g.supertypes_none:
            sup.append((carddb.NO_SUPERTYPE, tr("no supertype")))
        superdef = TypeSection(adv_title("super", "Übertyp"), sup, columns=2 if len(sup) > 6 else 1, default_off=())
        rng = RangeSection()
        rng.check.setText(adv_title("range", "Werte"))
        return {
            "colors": ColorSection(),
            "types": TypeSection(adv_title("types", "Kartentyp"), [(t, t) for t in carddb.CARD_TYPES], columns=2,
                                 default_off=off),
            "super": superdef,
            "kw": ListSection(adv_title("kw", "Keywords"), adv_hint("kw")),
            "rarity": TypeSection(adv_title("rarity", "Seltenheit"), list(RARITY.items()), columns=1, default_off=()),
            "range": rng,
            "format": FormatSection(adv_title("format", "Legal in"), [(k, n) for k, n in library.FORMATS],
                                    columns=1, default_off=()),
            "reg": TypeSection(adv_title("reg", "Reg. mark"),
                               [(m, m) for m in (carddb.regulation_marks() if g.regulation_marks and carddb.exists()
                                                 else ()) or g.regulation_marks] + [("-", tr("none"))],
                               columns=3,
                               default_off=()),
        }

    def stretch(self, key):
        """Relative width of a section (the game can change it: games.<game>.adv_stretch)."""
        return games.current().adv_stretch.get(key, self.STRETCH.get(key, 2))

    @property
    def hidden(self):
        """Sections the game doesn't have (Pokémon: no subtype; regulation marks only where the game has them)."""
        g = games.current()
        return set(g.adv_hidden) | (set() if g.regulation_marks else {"reg"})

    def rebuild_for_game(self):
        """Game switched: card types, supertypes, rarities, formats, colors, values of the new game (the old
        sections stay around as children – the UI may still hold references to them)."""
        new = self._game_sections()
        self.sec_sub.check.setText(adv_title("sub", "Untertyp"))
        self.sec_sub.placeholder = adv_hint("sub")
        lf = getattr(self, "lang_filter", None)
        if lf is not None:   # languages of the new game
            lf.order = [c for c, *_ in LANGS]
        attr = {"types": "sec_types", "super": "sec_super", "rarity": "sec_rarity", "format": "sec_format",
                "colors": "sec_colors", "kw": "sec_kw", "range": "sec_range", "reg": "sec_reg"}
        for k, sec in new.items():
            old = self.sec_by_key[k]
            try:
                old.changed.disconnect(self.filters_changed)
            except (RuntimeError, TypeError):
                pass
            sec.setParent(self)
            sec.changed.connect(self.filters_changed)
            self.sec_by_key[k] = sec
            setattr(self, attr[k], sec)
        self.sections = [self.sec_by_key[k] for k in self.sec_by_key]
        self.sets_loaded = self.vocab_loaded = False

    def update_adv_btn(self):
        n = sum(1 for sec in self.sections if sec.toggle and sec.active and sec.has_selection())
        self.adv_btn.setText(tr("Advanced search") + (f" ({n})" if n else "") + ("  ▴" if self.adv_btn.isChecked()
                                                                                    else "  ▾"))
        if self.adv_btn.isChecked():
            self.load_vocab()
        self.adv_note.setVisible(self.adv_btn.isChecked() and not carddb.exists())

    def filters_changed(self):
        self.update_adv_btn()
        self.timer.start()

    # --- Filters ---
    def filters(self, live=True):
        """All filters for carddb: advanced search and (live) syntax in the search field."""
        f = {}
        if self.sec_sets.active and self.sec_sets.codes:
            f["set_codes"], f["sets_mode"] = list(self.sec_sets.codes), self.sec_sets.mode.currentData()
        if self.sec_colors.active and self.sec_colors.colors():
            f["colors"], f["color_mode"] = self.sec_colors.colors(), self.sec_colors.mode.currentData()
        if self.sec_super.active and self.sec_super.values():
            f["supertypes"] = self.sec_super.values()
        for sec, key in ((self.sec_sub, "subtypes"), (self.sec_kw, "keywords")):
            if sec.active and sec.values():
                f[key], f[f"{key}_mode"] = sec.values(), sec.mode.currentData()
        if self.sec_rarity.active and self.sec_rarity.values():
            f["rarities"] = self.sec_rarity.values()
        if self.sec_format.active and self.sec_format.any_of() is not None:
            f["formats_any"] = self.sec_format.any_of()
        if self.sec_reg.active and "reg" not in self.hidden:
            if self.sec_reg.values():
                f["regulation"] = self.sec_reg.values()
            if self.sec_reg.excluded():
                f["not_regulation"] = self.sec_reg.excluded()
        for sec, key in ((self.sec_types, "types"), (self.sec_super, "supertypes"), (self.sec_sub, "subtypes"),
                         (self.sec_kw, "keywords"), (self.sec_rarity, "rarities"), (self.sec_format, "formats")):
            if sec.active and sec.excluded():
                f[f"not_{key}"] = sec.excluded()
        if self.sec_range.active and self.sec_range.ranges():
            f["ranges"] = dict(self.sec_range.ranges())
        if self.sec_text.active and self.sec_text.texts:
            f["texts"] = list(self.sec_text.texts)
        if self.sec_count.active:
            f["owned"] = self.sec_count.owned()
        text = self.search.text()
        if live:
            crit, text = parse_query(text)
            for c in crit:
                apply_criterion(f, *c)
            year, text = split_year(text)   # "glurak 1999"
            if year:
                f.setdefault("ranges", {})["year"] = (year, year)
            code, num, text = split_print_query(text)  # "sos", "001", "sos 123"
            if code:
                f["set_codes"] = sorted(set(f.get("set_codes") or []) | {code})
                f.setdefault("sets_mode", "or")
            if num:
                f["number"] = num
        return f, text.strip()

    def commit_syntax(self):
        """Enter in the search field: recognized syntax becomes chips (advanced search), the rest stays as text."""
        crit, rest = parse_query(self.search.text())
        code, num, _ = split_print_query(split_year(rest)[1])
        if code:  # "sos" / "sos 123": the set goes into the advanced search as a filter, the number stays in the field
            self.sec_sets.set_set(code)
            rest = num or ""
        keep = [f"{'-' if neg else ''}year{op}{value}" for key, value, neg, op in crit if key == "year"]
        if keep:   # the year has no chip: it stays in the field (and keeps filtering live)
            rest = " ".join([rest] + keep).strip()
        for key, value, neg, op in crit:
            if key in ("oracle", "name", "artist", "flavor"):
                self.sec_text.add(key, value, neg)
            elif key == "type":  # -t:land = red ✕
                v = _cap(value)
                if v in carddb.CARD_TYPES:  # t:creature = creatures only, -t:land = lands off
                    self.sec_types.set_value(v, 2) if neg else self.sec_types.solo(v)
                elif v in carddb.SUPERTYPES:  # t:legendary = legendary only
                    self.sec_super.set_value(v, 2) if neg else self.sec_super.solo(v)
                else:
                    self.sec_sub.set_value(v, 2 if neg else 1)
            elif key == "kw":
                self.sec_kw.set_value(_cap(value), 2 if neg else 1)
            elif key == "rarity":
                rar = _RAR.get(value.lower()[:1]) if len(value) == 1 else value.lower()
                self.sec_rarity.set_value(rar, 2) if neg else self.sec_rarity.solo(rar)
            elif key == "format":
                self.sec_format.set_value(value.lower(), 2) if neg else self.sec_format.solo(value.lower())
            elif key == "set":
                self.sec_sets.set_set(value.lower())
            elif key == "color":
                self.sec_colors.set_colors(color_letters(value), {"=": "exact", "<=": "atmost", "<": "atmost"}.get(op, "any"))
            elif key in ("mv", "pow", "tou", "price"):
                tmp = {}
                apply_criterion(tmp, key, value, neg, op)
                if "ranges" in tmp:
                    self.sec_range.set_range(key, *tmp["ranges"][key])
        if crit or code:
            self.search.blockSignals(True)
            self.search.setText(rest)
            self.search.blockSignals(False)
        self.timer.stop()
        self.changed.emit()

    # --- State of the search (for "Undo" on the chips) ---
    def snapshot(self):
        st = {"text": self.search.text(), "secs": {k: _sec_get(sec) for k, sec in self.sec_by_key.items()}}
        if callable(getattr(self, "extra_get", None)):
            st["extra"] = self.extra_get()  # state of the chips from outside (for ↺)
        lf = getattr(self, "lang_filter", None)
        if lf is not None:
            st["langs"], st["lang_mode"] = sorted(lf.selected()), lf.mode()
        fo = getattr(self, "foil_only", None)
        if isinstance(fo, FoilChoice):
            st["foil"] = fo.mode
        return st

    def restore(self, st):
        self.search.blockSignals(True)
        self.search.setText(st.get("text", ""))
        self.search.blockSignals(False)
        if "extra" in st and callable(getattr(self, "extra_set", None)):
            self.extra_set(st["extra"])
        for k, sec in self.sec_by_key.items():
            if k in st.get("secs", {}):
                _sec_set(sec, st["secs"][k])
        lf = getattr(self, "lang_filter", None)
        if lf is not None and "langs" in st:
            lf.blockSignals(True)
            for c, b in lf.btns.items():
                b.blockSignals(True)
                b.setChecked(c in st["langs"])
                b.blockSignals(False)
            lf.set_mode(st.get("lang_mode", "or"))
            lf.blockSignals(False)
        fo = getattr(self, "foil_only", None)
        if isinstance(fo, FoilChoice) and "foil" in st:
            fo.blockSignals(True)
            fo.set_mode(st["foil"])
            fo.blockSignals(False)
        self.update_adv_btn()
        self.timer.stop()
        self.changed.emit()
        self.refresh_chips()

    # --- Chips with "Undo" ---
    def _act(self, title, text, fn, group=False):
        """Chip clicked: filter immediately, the chip stays grey with ↺ for a moment (click = undo)."""
        self._touch_undos()
        snap = self.snapshot()
        groups = [g for g in self.chips_data if g.get("kind") == "group" and not g["grey"]]
        box = next((g for g in groups if _base(g["title"]) == _base(title)), None)
        all_texts = [v[0] for v in box["values"]] if box is not None else []
        pos = all_texts.index(text) if text in all_texts else len(all_texts)
        texts = [v[0] for v in box["values"] if v[2] == "value"] if box is not None else []
        if group:
            self._undo = [u for u in self._undo if _base(u["title"]) != _base(title)]
        gpos = groups.index(box) if box is not None else len(groups)
        fn()
        uid = object()
        entry = {"title": title, "text": text, "snap": snap, "group": group, "uid": uid, "pos": pos, "gpos": gpos,
                 "values": texts, "deadline": time.monotonic() + self.UNDO_HOLD}
        self._undo = [u for u in self._undo if not (u["title"] == title and u["text"] == text)]
        self._undo.append(entry)
        self.timer.stop()
        self.changed.emit()
        self.refresh_chips()
        QtCore.QTimer.singleShot(round(self.UNDO_HOLD * 1000), lambda: self._expire(entry))

    def _undo_entry(self, entry):
        self._touch_undos()
        self._undo = [u for u in self._undo if u is not entry]
        self.collapsing.discard(entry["uid"])
        self.restore(entry["snap"])

    def _touch_undos(self):
        """New click: all chips that are still grey get the full time again – those already fading come back.
        That way, when clicking away quickly, you never accidentally hit the wrong (shifted) chip."""
        until = time.monotonic() + self.UNDO_HOLD
        for u in self._undo:
            u["deadline"] = until
            if u.pop("collapsing", False):  # its timer has already run out: set it again
                self.collapsing.discard(u["uid"])
                QtCore.QTimer.singleShot(round(self.UNDO_HOLD * 1000), lambda u=u: self._expire(u))

    def _expire(self, entry):
        if entry not in self._undo or entry.get("collapsing"):
            return
        left = entry.get("deadline", 0) - time.monotonic()
        if left > 0.05:  # clicked again in the meantime: time restarts
            QtCore.QTimer.singleShot(round(left * 1000), lambda: self._expire(entry))
            return
        entry["collapsing"] = True  # fades out now (Qt Quick) – a quick click brings it back
        self.collapsing.add(entry["uid"])
        self.refresh_chips()

        def done():
            if not entry.get("collapsing"):
                return  # revived in the meantime (clicked again)
            self.collapsing.discard(entry["uid"])
            self._undo = [u for u in self._undo if u is not entry]
            self.refresh_chips()
        QtCore.QTimer.singleShot(round(self.FADE * 1000), done)

    def _clear_with_undo(self):
        """Clear all filters: all chips stay grey for a moment, only "Clear all filters" shows ↺."""
        self._touch_undos()
        groups = [(g["title"], [v[0] for v in g["values"]]) for g in self.chips_data if g.get("kind") == "group"]
        snap = self.snapshot()
        self._undo = []
        self.collapsing.clear()
        self.clear_all()
        self._cleared = {"snap": snap, "groups": groups, "uid": object()}
        self.refresh_chips()
        entry = self._cleared
        QtCore.QTimer.singleShot(round(self.UNDO_HOLD * 1000), lambda: self._expire_clear(entry))

    def _undo_clear(self):
        st, self._cleared = self._cleared, None
        if st:
            self.restore(st["snap"])

    def _expire_clear(self, entry):
        if self._cleared is not entry:
            return
        entry["fading"] = True
        self.refresh_chips()

        def done():
            if self._cleared is entry:
                self._cleared = None
            self.refresh_chips()
        QtCore.QTimer.singleShot(650, done)

    def refresh_chips(self):
        """Active filters as chips, one box with a title per filter kind. Click on a value = remove, click on the
        title = switch the group off (the selection stays). Both can be undone for a moment.
        Result in chips_data (data for qlibrary.read_chips)."""
        cleared = self._cleared
        if cleared is not None:  # just cleared everything: old chips grey, ↺ only on the clear chip
            out = []
            for title, texts in cleared["groups"]:
                out.append({"kind": "group", "title": title, "values": [(t, None, "grey", None) for t in texts],
                            "on_title": None, "grey": True, "undo_all": None, "fading": cleared.get("fading", False)})
            out.append({"kind": "group", "title": None,
                        "values": [(tr("Clear all filters"), self._undo_clear, "undo", cleared["uid"])],
                        "on_title": None, "grey": False, "undo_all": None, "fading": cleared.get("fading", False)})
            self.chips_data = out
            self.chips_changed.emit()
            return
        groups = []  # [(title, [(text, function)], group-off function)]

        def add(title, items, off=None):
            if items:
                groups.append((title, items, off))
        for title, items, off in (self.extra_chips() if callable(getattr(self, "extra_chips", None)) else []):
            add(title, items, off)  # chips from outside (deck builder: "Alternatives to …", "Upgrades")
        text = self.search.text().strip()
        if text:  # the search text as a chip – otherwise it's easy to miss that a search is still active
            add(tr("Suche"), [(text, lambda: self.search.clear())], lambda: self.search.clear())
        codes = self.sec_sets.codes if self.sec_sets.active else []
        items = []
        names = {x["code"]: x.get("name") or "" for x in self.sec_sets.sets()} if codes else {}
        for root, members, size in self.set_groups(codes):
            if len(members) > 1 and len(members) == size:  # complete pack = one chip, named like its main set
                # (Oliver's test of 0.9.2: "TRK bundle (4)" said nothing – now "Star Trek – Complete bundle (4)")
                name = names.get(root) or root.upper()
                items.append((f"{name} – {tr('Complete bundle')} ({size})", lambda m=members: self.remove_sets(m)))
            else:
                items += [(c.upper(), lambda c=c: self.sec_sets.set_set(c, False)) for c in members]
        if items:
            mode = tr("AND") if self.sec_sets.mode.currentData() == "and" else tr("OR")
            add(tr("Sets") + (f" ({mode})" if len(items) > 1 else ""), items,
                lambda: self.sec_sets.check.setChecked(False))
        if self.sec_colors.active:
            for t, fn in self.sec_colors.chips():
                title, _, val = t.partition(": ")
                add(title, [(val or t, fn)], lambda: self.sec_colors.check.setChecked(False))
        lf = getattr(self, "lang_filter", None)
        if lf is not None and not lf.isHidden() and lf.selected():
            sel = [c for c, *_ in LANGS if c in lf.selected()]
            mode = tr("AND") if lf.mode() == "and" else tr("OR")
            add(tr("Language") + (f" ({mode})" if len(sel) > 1 else ""),
                [(lang_short(c), lambda c=c: lf.set_lang(c, False)) for c in sel], lambda: lf.reset())
        ao = getattr(self, "alt_only", None)
        if ao is not None and not ao.isHidden() and ao.isChecked():
            add(tr("Alt-arts"), [(tr("only"), lambda: ao.setChecked(False))], lambda: ao.setChecked(False))
        fo = getattr(self, "foil_only", None)
        if isinstance(fo, FoilChoice) and not fo.isHidden() and fo.mode != "any":
            add(tr("Foil"), [(tr("only") if fo.mode == "only" else tr("kein"), lambda: fo.reset())], lambda: fo.reset())
        g = games.current()
        for sec, prefix in ((self.sec_types, tr("Type")), (self.sec_super, adv_title("super", "Übertyp")),
                            (self.sec_sub, tr("Subtype")), (self.sec_kw, tr(g.adv_titles.get("kw") or "Keyword")),
                            (self.sec_rarity, tr("Rarity")), (self.sec_format, tr("Legal")),
                            (self.sec_reg, adv_title("reg", "Reg. mark"))):
            if sec.active and not (sec is self.sec_sub and "sub" in self.hidden) and \
                    not (sec is self.sec_reg and "reg" in self.hidden):
                its = [(t.partition(": ")[2], fn) for t, fn in sec.chips(prefix)]
                mode = getattr(sec, "mode", None)
                inc = [t for t, _ in its if not t.startswith("≠")]
                title = prefix
                if mode is not None and len(inc) > 1:
                    title += " (" + (tr("AND") if mode.currentData() == "all" else tr("OR")) + ")"
                add(title, its, lambda sec=sec: sec.check.setChecked(False))
        for sec in (self.sec_range, self.sec_count, self.sec_text):
            if sec.active:
                for t, fn in sec.chips():
                    title, sep, val = t.partition(": ")
                    if sep:
                        add(title, [(val, fn)], lambda sec=sec: sec.check.setChecked(False))
                    else:
                        add(None, [(t, fn)], lambda sec=sec: sec.check.setChecked(False))
        # merge identical titles
        merged = []
        for title, items, off in groups:
            if title is not None and merged and merged[-1][0] == title:
                merged[-1][1].extend(items)
            else:
                merged.append((title, list(items), off))
        undo = list(self._undo)
        plan, n_active = [], 0
        for title, items, off in merged:
            vals = [(t, (lambda ti=title, tx=t, f=fn: self._act(ti, tx, f)), "value", None) for t, fn in items]
            n_active += len(items)
            for u in sorted(undo, key=lambda u: u.get("pos", 0)):
                if _base(u["title"]) == _base(title) and not u["group"]:  # back to its old place
                    vals.insert(min(u.get("pos", len(vals)), len(vals)),
                                (u["text"], (lambda u=u: self._undo_entry(u)), "undo", u["uid"]))
            on_title = (lambda ti=title, f=off: self._act(ti, "", f, group=True)) if off else None
            plan.append({"kind": "group", "title": title, "values": vals, "on_title": on_title, "grey": False,
                         "undo_all": None, "fading": False})
        titles = {_base(g["title"]) for g in plan}
        extra, orphans = [], {}
        for u in sorted(undo, key=lambda u: (u.get("gpos", 0), u.get("pos", 0))):
            if u["group"]:  # whole group off: values grey, ONE ↺ above the box
                texts = u.get("values") or [u["text"]]
                vals = [(t, None, "grey", u["uid"] if i == 0 else None) for i, t in enumerate(texts)]
                extra.append((u.get("gpos", 0), {"kind": "group", "title": u["title"], "values": vals,
                                                 "on_title": None, "grey": True,
                                                 "undo_all": (lambda u=u: self._undo_entry(u)),
                                                 "fading": u["uid"] in self.collapsing}))
            elif _base(u["title"]) not in titles:
                b = _base(u["title"])
                if b not in orphans:
                    orphans[b] = {"kind": "group", "title": u["title"], "values": [], "on_title": None, "grey": True,
                                  "undo_all": None, "fading": False}
                    extra.append((u.get("gpos", 0), orphans[b]))
                orphans[b]["values"].append((u["text"], (lambda u=u: self._undo_entry(u)), "undo", u["uid"]))
        for o in orphans.values():  # all values fade out = the whole box
            o["fading"] = all(v[3] in self.collapsing for v in o["values"])
        for gpos, item in extra:
            plan.insert(min(gpos, len(plan)), item)
        if n_active > 1:
            plan.append({"kind": "clear", "title": None, "values": [(tr("Clear all filters"),
                                                                     self._clear_with_undo, "clear", None)],
                         "on_title": None, "grey": False, "undo_all": None, "fading": False})
        self.chips_data = plan
        self.chips_changed.emit()

    def set_groups(self, codes):
        """Selected sets by family (main set): [(main set, [selected codes], size of the family)]."""
        by_code = {x["code"]: x for x in self.sec_sets.sets()}

        def root(code):
            seen = set()
            while by_code.get(code, {}).get("parent") in by_code and code not in seen:
                seen.add(code)
                code = by_code[code]["parent"]
            return code
        out, size = {}, {}
        for c in codes:
            out.setdefault(root(c), []).append(c)
        for c in by_code:
            r = root(c)
            if r in out:
                size[r] = size.get(r, 0) + 1
        return [(r, members, size.get(r, len(members))) for r, members in out.items()]

    def remove_sets(self, codes):
        self.sec_sets.codes = [c for c in self.sec_sets.codes if c not in codes]
        self.sec_sets._update()
        self.sec_sets.touched()

    def clear_all(self):
        for sec in self.sections:
            if not sec.toggle:
                continue  # display/deck options stay
            sec.blockSignals(True)
            sec.reset()
            sec.check.blockSignals(True)
            sec.check.setChecked(bool(getattr(sec, "keep_active", False)))  # card types: default (lands off) applies
            sec.check.blockSignals(False)
            sec.blockSignals(False)
        lf = getattr(self, "lang_filter", None)
        if lf is not None:  # language chips are a filter, even though they sit with the display options
            lf.blockSignals(True)
            lf.reset()
            lf.blockSignals(False)
        self.update_adv_btn()
        self.timer.stop()
        self.changed.emit()

    def isVisible(self):
        return True
