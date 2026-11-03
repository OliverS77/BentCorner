"""Lists in the Qt Quick window (qml/components/PopupLayer.qml): menus from qmenu and other short choice lists –
inside the program window instead of a separate small window.
"""
from PySide6 import QtCore


_host = None


def host():
    """The list display in the Qt Quick window (for qmenu) – None without a Qt Quick UI."""
    return _host


class Popups(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, shell):
        super().__init__(shell)
        self.shell = shell
        self._items, self._pos, self._cb, self._kind = [], (0.0, 0.0, 200.0), None, ""

    # ---------- internal ----------
    def to_window(self, gpos):
        """Screen point -> point in the Qt Quick window."""
        qw = self.shell.window
        if qw is None:
            return 200.0, 200.0
        p = qw.mapFromGlobal(gpos)
        return float(max(0, p.x())), float(max(0, p.y()))

    def show_list(self, kind, items, pos, cb):
        self._show(kind, items, pos, cb)

    def _show(self, kind, items, pos, cb):
        self._kind, self._items, self._pos, self._cb = kind, items, pos, cb
        self.changed.emit()

    @QtCore.Slot(int)
    def pick(self, i):
        cb, self._cb = self._cb, None
        self._items = []
        self.changed.emit()
        if cb is not None:
            cb(i)

    @QtCore.Slot()
    def close(self):
        if self._cb is not None:
            self.pick(-1)

    @QtCore.Property("QVariantList", notify=changed)
    def items(self):
        return self._items

    @QtCore.Property(str, notify=changed)
    def kind(self):
        return self._kind

    @QtCore.Property(float, notify=changed)
    def px(self):
        return self._pos[0]

    @QtCore.Property(float, notify=changed)
    def py(self):
        return self._pos[1]

    @QtCore.Property(float, notify=changed)
    def pw(self):
        return self._pos[2]


def install(shell):
    """Create the list display in the Qt Quick window (menus from qmenu, choice lists)."""
    global _host
    _host = Popups(shell)
    return _host
