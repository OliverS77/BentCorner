"""State without widgets: small data objects in place of the former status lines, progress bars and choice lists.

The program logic writes into them as usual (setText, setValue, addItem …); the Qt Quick pages read the values and
refresh as soon as something changes (watch). That way the logic stays unchanged, but there are no more invisible
widgets that only hold values.
"""
_watchers = []


def watch(fn):
    """fn() is called after every change (e.g. form.soon)."""
    _watchers.append(fn)


def _changed():
    for fn in list(_watchers):
        try:
            fn()
        except RuntimeError:  # target already torn down
            pass


class _Base:
    """Shared no-op display calls (style, wrapping …) – QML draws those now."""
    def __init__(self):
        self._visible, self._tip, self._enabled = True, "", True

    def setVisible(self, on):
        if bool(on) != self._visible:
            self._visible = bool(on)
            _changed()

    def isVisible(self):
        return self._visible

    def show(self):
        self.setVisible(True)

    def hide(self):
        self.setVisible(False)

    def setEnabled(self, on):
        if bool(on) != self._enabled:
            self._enabled = bool(on)
            _changed()

    def isEnabled(self):
        return self._enabled

    def setToolTip(self, t):
        self._tip = t or ""

    def toolTip(self):
        return self._tip

    def _noop(self, *a, **k):
        return None

    setStyleSheet = setWordWrap = setTextFormat = setContentsMargins = setTextInteractionFlags = _noop
    setMinimumHeight = setMinimumWidth = setFixedWidth = updateGeometry = update = blockSignals = _noop
    setOpenExternalLinks = setAlignment = _noop


class Text(_Base):
    """Instead of QLabel for a status line."""

    def __init__(self, text=""):
        super().__init__()
        self._text = text

    def setText(self, t):
        t = "" if t is None else str(t)
        if t != self._text:
            self._text = t
            _changed()

    def text(self):
        return self._text

    def clear(self):
        self.setText("")


class Progress(_Base):
    """Instead of QProgressBar."""

    def __init__(self):
        super().__init__()
        self._visible = False
        self._min, self._max, self._value, self._format = 0, 0, 0, ""

    def setRange(self, lo, hi):
        self._min, self._max = lo, hi
        _changed()

    def setValue(self, v):
        if v != self._value:
            self._value = v
            _changed()

    def setFormat(self, f):
        if f != self._format:
            self._format = f
            _changed()

    def value(self):
        return self._value

    def minimum(self):
        return self._min

    def maximum(self):
        return self._max

    def format(self):
        return self._format

    def text(self):
        return self._format.replace("%p", str(round(100 * (self._value - self._min) / max(1, self._max - self._min))))


class Choice(_Base):
    """Instead of QComboBox, where the logic uses the selection as state (camera list, resolution)."""

    def __init__(self):
        super().__init__()
        self._items, self._index = [], -1

    def clear(self):
        self._items, self._index = [], -1
        _changed()

    def addItem(self, text, data=None):
        self._items.append((str(text), data))
        if self._index < 0:
            self._index = 0
        _changed()

    def addItems(self, texts):
        for t in texts:
            self.addItem(t)

    def count(self):
        return len(self._items)

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, i):
        i = int(i)
        if -1 <= i < len(self._items) and i != self._index:
            self._index = i
            _changed()

    def currentText(self):
        return self._items[self._index][0] if 0 <= self._index < len(self._items) else ""

    def currentData(self):
        return self._items[self._index][1] if 0 <= self._index < len(self._items) else None

    def setCurrentText(self, t):
        i = self.findText(t)
        if i >= 0:
            self.setCurrentIndex(i)

    def findText(self, t):
        return next((i for i, (x, _) in enumerate(self._items) if x == t), -1)

    def findData(self, d):
        return next((i for i, (_, x) in enumerate(self._items) if x == d), -1)

    def items(self):
        return [t for t, _ in self._items]


class Flag(_Base):
    """Instead of QCheckBox, where the logic uses the check mark as state."""

    def __init__(self, on=False):
        super().__init__()
        self._on = bool(on)

    def setChecked(self, on):
        if bool(on) != self._on:
            self._on = bool(on)
            _changed()

    def isChecked(self):
        return self._on


class Panel(_Base):
    """Instead of a floating window (QFrame) above the camera view: visible/hidden and position. parent is the
    view (for the size); the window is drawn in Qt Quick."""

    def __init__(self, parent=None):
        super().__init__()
        self._parent, self._visible = parent, False
        self._rect = (0, 0, 0, 0)

    def parent(self):
        return self._parent

    parentWidget = parent

    def isHidden(self):
        return not self._visible

    def setGeometry(self, x, y, w, h):
        r = (int(x), int(y), int(w), int(h))
        if r != self._rect:
            self._rect = r
            _changed()

    def geometry(self):
        from PySide6 import QtCore
        return QtCore.QRect(*self._rect)

    def raise_(self):
        return None

    setFocus = raise_
