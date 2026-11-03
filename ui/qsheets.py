"""Dialogs in the Qt Quick UI (qml/components/SheetLayer.qml): every confirmation, input, file/colour picker and
every custom dialog appears as a page inside the window ("← Back" and the title at the top) – a sidebar on the right
for questions while scanning. Content: a form (qform.Form) or file browser/colour picker (qfiles).

Opened via qdialogs (ask, question, get_text, open_file, show …).
"""
import time

from PySide6 import QtCore

FADE_MS = 170   # fade out on close (also in performance mode – a crossfade costs almost nothing)


class _Model(QtCore.QAbstractListModel):
    """The open dialogs for SheetLayer's Repeater – one row each, role "modelData" (the dict sheets() made). A row
    is added, changed and removed on its own: with a plain list as the model every open/close rebuilt ALL dialogs
    with their forms, the closing one too, just to fade it out (tester log 0.9.2: 300 ms per opening)."""
    ROLE = QtCore.Qt.UserRole + 1

    def __init__(self, host):
        super().__init__(host)
        self.host = host

    def roleNames(self):
        return {self.ROLE: b"modelData"}

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.host._open)

    def data(self, index, role):
        if role != self.ROLE or not 0 <= index.row() < len(self.host._open):
            return None
        return self.host._row(index.row(), time.monotonic())

    def touch(self, first=0):
        """Rows from `first` on: their data changed (closing, title, index after a removal)."""
        n = len(self.host._open)
        if first < n:
            self.dataChanged.emit(self.index(first), self.index(n - 1), [self.ROLE])


class Sheets(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._open = []  # dialogs (qdialogs.Dialog), the topmost last
        self._model = _Model(self)

    # ---------- qdialogs ----------
    def open(self, d):
        d._opened_t = time.monotonic()
        n = len(self._open)
        self._model.beginInsertRows(QtCore.QModelIndex(), n, n)
        self._open.append(d)
        self._model.endInsertRows()
        self.changed.emit()

    def closed(self, d):
        """Closed: leave it briefly and fade it out (QML), then really remove it. Clicks and keys go back to the page
        immediately (covering/active look at "closing")."""
        if d in self._open and not getattr(d, "_closing", False):
            d._closing = True
            # tell QML only after the current mouse event: if the dialog changes in the middle of the release,
            # Qt passes the release on to whatever is behind it (the click would go through)
            QtCore.QTimer.singleShot(0, lambda: self._changed(d))
            QtCore.QTimer.singleShot(FADE_MS + 30, lambda: self._remove(d))

    def _changed(self, d):
        if d in self._open:
            i = self._open.index(d)
            self._model.dataChanged.emit(self._model.index(i), self._model.index(i), [_Model.ROLE])
        self.changed.emit()

    def _remove(self, d):
        if d in self._open:
            i = self._open.index(d)
            self._model.beginRemoveRows(QtCore.QModelIndex(), i, i)
            self._open.remove(d)
            self._model.endRemoveRows()
            self._model.touch(i)   # the ones above moved down one: their index ("i") changed
            self.changed.emit()

    def retitle(self, d):
        self._changed(d)

    # ---------- for QML ----------
    def _row(self, i, now):
        d = self._open[i]
        return {"title": d.title, "mirror": d.form, "side": d.side, "i": i, "kind": d.kind, "tool": d.tool,
                "wide": int(d.wide), "keys": [{"seq": k, "notext": v[1]} for k, v in d.keys.items()],
                "closing": bool(getattr(d, "_closing", False)), "items": getattr(d, "items", None) or [],
                "sub": bool(getattr(d, "parent_menu", None)), "multi": bool(getattr(d, "multi", False)),
                "freeText": getattr(d, "take_text", None) is not None,
                "at": list(getattr(d, "at", None) or []),
                "fresh": now - getattr(d, "_opened_t", 0) < 0.25}

    @QtCore.Property("QVariantList", notify=changed)
    def sheets(self):
        now = time.monotonic()
        return [self._row(i, now) for i in range(len(self._open))]

    @QtCore.Property(QtCore.QObject, constant=True)
    def model(self):
        return self._model

    @QtCore.Slot(int, str)
    def key(self, i, seq):
        if 0 <= i < len(self._open):
            fn = self._open[i].keys.get(seq)
            if fn is not None:
                fn[0]()

    @QtCore.Slot(int, int)
    def pick(self, i, idx):
        """A menu sheet (kind "menu"): entry idx chosen."""
        if 0 <= i < len(self._open) and getattr(self._open[i], "pick", None):
            self._open[i].pick(idx)

    @QtCore.Slot(int, str)
    def text(self, i, t):
        """A menu sheet with free text (qdialogs.menu on_text): the typed text taken."""
        if 0 <= i < len(self._open) and getattr(self._open[i], "take_text", None):
            self._open[i].take_text(t)

    @QtCore.Slot(int)
    def back(self, i):
        if 0 <= i < len(self._open):
            self._open[i].back()

    @QtCore.Property(bool, notify=changed)
    def covering(self):
        return any(not d.side and not getattr(d, "_closing", False) for d in self._open)

    @QtCore.Property(bool, notify=changed)
    def opaque(self):
        """A dialog with its own (opaque) background is open: the window below is switched off (Main.qml covered) –
        not for menus (no veil, the page shows through) or side prompts (the page stays usable)."""
        return any(not d.side and d.kind != "menu" and not getattr(d, "_closing", False) for d in self._open)
