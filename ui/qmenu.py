"""Menus without widgets: the same handling as QMenu (addAction, addSeparator, addMenu, exec), shown as the light
menu page in the Qt Quick window (qdialogs.menu / SheetLayer + MenuCard). exec doesn't wait – every item has its own
callback function.

    m = qmenu.Menu()
    m.addAction(tr("Open"), lambda: …)
    act = m.addAction(tr("Built")); act.setCheckable(True); act.setChecked(on); act.toggled.connect(…)
    m.addSeparator()
    m.exec(QtGui.QCursor.pos())
"""
from PySide6 import QtGui


class _Signal:
    def __init__(self):
        self._fns = []

    def connect(self, fn):
        self._fns.append(fn)

    def emit(self, *args):
        for fn in list(self._fns):
            try:
                fn(*args)
            except TypeError:
                fn()


class Action:
    def __init__(self, text="", fn=None):
        self._text, self._checkable, self._checked, self._enabled, self._visible = text, False, False, True, True
        self.triggered, self.toggled = _Signal(), _Signal()
        self.separator, self.menu, self._data, self._tip = False, None, None, ""
        if fn is not None:
            self.triggered.connect(fn)

    # QAction-like
    def text(self):
        return self._text

    def setText(self, t):
        self._text = t

    def setCheckable(self, on):
        self._checkable = bool(on)

    def setChecked(self, on):
        self._checked = bool(on)

    def isChecked(self):
        return self._checked

    def setEnabled(self, on):
        self._enabled = bool(on)

    def isEnabled(self):
        return self._enabled

    def setVisible(self, on):
        self._visible = bool(on)

    def isVisible(self):
        return self._visible

    def setToolTip(self, t):
        self._tip = t

    def data(self):
        return self._data

    def isSeparator(self):
        return self.separator

    def trigger(self):
        if self._checkable:
            self._checked = not self._checked
            self.toggled.emit(self._checked)
        self.triggered.emit(self._checked)


class Menu:
    def __init__(self, parent=None, title=""):
        self.title = title
        self._actions = []
        self._on_hide, self._on_show = [], []

    def addAction(self, *args):
        """addAction(text), addAction(text, function), addAction(icon, text, function)."""
        if args and isinstance(args[0], QtGui.QIcon):
            args = args[1:]
        text = args[0] if args else ""
        fn = args[1] if len(args) > 1 else None
        a = Action(text, fn)
        self._actions.append(a)
        return a

    def addSeparator(self):
        a = Action()
        a.separator = True
        self._actions.append(a)
        return a

    def addMenu(self, title):
        sub = Menu(title=title)
        a = Action(title)
        a.menu = sub
        self._actions.append(a)
        return sub

    def actions(self):
        return list(self._actions)

    def on_show(self, fn):
        self._on_show.append(fn)

    def exec(self, pos=None, *_):
        """Show the menu: always as the light menu in the window (sheet, no pop-out), its card at pos (a point on the
        screen, like QMenu.exec) – without one where the mouse is."""
        return self.sheet(at=pos)

    popup = exec

    def sheet(self, title=None, *, parent=None, at=None):
        """The same menu as a light page in the window (qdialogs.menu) instead of a list at the mouse: narrow,
        checkable entries by brightness (on = lit, no ticks), a submenu opens over it as its own page ("←" back).
        An entry closes the menu (and the menus it came from) and then runs (so it may open the next dialog)."""
        from ui import qdialogs
        title = title if title is not None else self.title
        acts = [a for a in self._actions if a.isVisible()]
        items = [{"text": a.text().replace("&", ""), "enabled": a.isEnabled(), "sep": a.isSeparator(),
                  "checkable": a._checkable, "on": a.isChecked() if a._checkable else None, "sub": a.menu is not None,
                  "tip": a._tip}
                 for a in acts]
        for fn in self._on_show:
            fn()

        def close_all(d):
            while d is not None:
                d.close()
                d = d.parent_menu

        def pick(i):
            if not 0 <= i < len(acts):
                return
            a = acts[i]
            if a.isSeparator() or not a.isEnabled():
                return
            if a.menu is not None:
                a.menu.sheet(a.text().replace("&", ""), parent=dlg)
                return
            close_all(dlg)
            for fn in self._on_hide:
                fn()
            a.trigger()
        dlg = qdialogs.menu(title or "", items, pick, parent=parent, at=at)
        return None
