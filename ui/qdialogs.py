"""Dialogs without pop-up windows and without widgets: everything appears as a page in the program window
(qsheets/SheetLayer.qml).

As with exec() before, the caller waits for the result (own event loop):

    if qdialogs.question(tr("Delete deck"), tr("Really delete?")): …
    key = qdialogs.ask(tr("Unsaved"), text, [("save", tr("Save"), "active"), ("drop", tr("Discard"), "danger"),
                                             ("cancel", tr("Cancel"), "")])
    name = qdialogs.get_text(tr("New folder"), tr("Name:"))           # None = cancelled
    path = qdialogs.save_file(tr("Export"), "deck.txt", "Text (*.txt)")   # "" = cancelled
    result = qdialogs.show(tr("Title"), build)   # custom dialog: build(ui, dlg) – dlg.close(result) closes it

"← Back" or Esc close with None (or False/""). Without a program window (very early at startup) nothing is
shown and the cancel value is returned.
"""
import logging

from PySide6 import QtCore, QtGui

from system.i18n import tr

log = logging.getLogger(__name__)
_host = None   # qsheets.Sheets


def set_host(host):
    global _host
    _host = host


def host():
    return _host


class Dialog:
    """An open dialog. form: qform.Form (or mirror); kind "file"/"color" with tool (qfiles)."""

    def __init__(self, title, form=None, *, side=False, kind="", tool=None, wide=False, on_close=None):
        self.title, self.form, self.side, self.kind, self.tool, self.wide = title, form, side, kind, tool, wide
        self.on_close = on_close
        self.result, self.done = None, False
        self._loop = None
        self._on_back = None
        self.keys = {}  # keyboard shortcuts: "1" -> (function, only without a text field in focus)

    def key(self, seq, fn, no_text=True):
        """Keyboard shortcut in the dialog (e.g. "1" … "9"); no_text: not while typing into a text field.
        May also come after showing – the UI is then informed again (before, the keys were missing)."""
        self.keys[seq] = (fn, no_text)
        if _host is not None and not self.done and not getattr(self, "_keys_soon", False):
            # several keys in a row (1 … 9): the sheets are re-read once afterwards, not per key (each re-read
            # rebuilds the open sheets – 9× cost ~280 ms in the print question)
            self._keys_soon = True

            def tell():
                self._keys_soon = False
                if _host is not None and not self.done:
                    _host.retitle(self)
            QtCore.QTimer.singleShot(0, tell)

    def set_title(self, title):
        self.title = title
        if _host is not None:
            _host.retitle(self)

    def refresh(self):
        if self.form is not None:
            self.form.soon()

    def close(self, result=None):
        if self.done:
            return
        self.done, self.result = True, result
        if _host is not None:
            _host.closed(self)
        if self.on_close is not None:
            try:
                self.on_close(result)
            except Exception:  # noqa: BLE001
                log.exception("Closing dialog")
        if self._loop is not None:
            self._loop.quit()

    def back(self):
        """'← Back' / Esc."""
        if self._on_back is not None:
            self._on_back()
        else:
            self.close(None)

    def wait(self):
        """Wait until closed (like exec()). -> result."""
        if not self.done:
            self._loop = QtCore.QEventLoop()
            self._loop.exec()
            self._loop = None
        return self.result


def _open(d, wait):
    if _host is None:
        log.warning("Dialog “%s” without app window – skipped", d.title)
        d.close(None)
        return d.result if wait else d
    _host.open(d)
    return d.wait() if wait else d


def show(title, build, *, side=False, wait=True, wide=False, on_close=None, on_back=None):
    """Custom dialog. build(ui, dlg) -> node; dlg.close(result) closes it. wait=False -> dialog (open).
    wide: False = narrow (680 px), True = wide (1100 px) or a width in pixels."""
    from ui.qform import Form
    d = Dialog(title, side=side, wide=wide, on_close=on_close)
    d._on_back = on_back
    d.form = Form(lambda ui: build(ui, d))
    return _open(d, wait)


def menu(title, items, on_pick, *, parent=None, multi=False, on_text=None, on_close=None, at=None):
    """A menu as a light sheet (kind "menu", SheetLayer.qml): narrow, Esc / a click beside it closes, arrow keys and
    Enter work, the first entry has the focus. items: [{text, enabled, checkable, on, sep, sub}]; on_pick(index) runs
    the entry. parent: the menu this one is a submenu of ("←" goes back to it).
    multi: several at once – on_pick(index) on every switch, the sheet stays open until Enter / "Done" / Esc / a click
    beside (on_close); typing filters; on_text(text): the typed text when nothing matches (Enter).
    at: where it opens, a point on the screen (x, y) – by default where the mouse is (the click that opened it); a
    submenu opens where its menu did. -> dialog"""
    d = Dialog(title, kind="menu", on_close=on_close)
    d.items, d.parent_menu, d.multi = items, parent, bool(multi)
    if at is None:
        at = parent.at if parent is not None and getattr(parent, "at", None) else QtGui.QCursor.pos()
    d.at = (at.x(), at.y()) if hasattr(at, "x") else tuple(at)
    d.pick = on_pick
    d.take_text = on_text
    return _open(d, False)


# ---------- Questions ----------
def ask(title, text, buttons=None, *, informative="", side=False, wait=True, on_close=None):
    """buttons: [(key, text, style)] – style "active" (highlighted), "danger" or "". -> key or None."""
    buttons = buttons or [("ok", tr("OK"), "active")]

    # a decision between alternatives (Oliver 2026-10-30): no main-action underline on any of them – it stays only
    # where there is one clear action (a lone "OK"; "Add", "Take", "Replace" in the forms). Enter picks nothing here.
    decision = len(buttons) > 1

    def build(ui, d):
        items = [ui.label(text, big=True)]
        if informative:
            items.append(ui.label(informative, color="gray"))
        row = [ui.stretch()]
        for key, label, style in buttons:
            row.append(ui.button(label, lambda k=key: d.close(k), primary=style == "active" and not decision,
                                 danger=style == "danger"))
        items.append(ui.space(4))
        items.append(ui.row(row))
        return ui.col(items, spacing=14)
    return show(title, build, side=side, wait=wait, on_close=on_close)


def question(title, text, *, yes=None, no=None, danger=False, informative="", default_no=False):
    """Yes/no. -> True on yes. default_no: "No" is preselected (Enter = no)."""
    if default_no:
        return ask(title, text, [("no", no or tr("No"), "active"), ("yes", yes or tr("Yes"), "danger" if danger else "")],
                   informative=informative) == "yes"
    return ask(title, text, [("no", no or tr("No"), ""), ("yes", yes or tr("Yes"), "danger" if danger else "active")],
               informative=informative) == "yes"


def info(title, text, informative=""):
    ask(title, text, informative=informative)


def warn(title, text, informative=""):
    ask(title, text, informative=informative)


error = warn


# ---------- Inputs ----------
def get_text(title, label, text="", *, placeholder="", ok=None):
    """-> entered text or None (cancelled)."""
    state = {"text": text}

    def build(ui, d):
        def accept(t=None):
            if t is not None:
                state["text"] = t
            d.close(state["text"])
        field = ui.edit(state["text"], accept, key="text", live=lambda t: state.update(text=t),
                        placeholder=placeholder)
        field["focus"] = True
        return ui.col([ui.label(label), field, ui.space(4),
                       ui.row([ui.stretch(), ui.button(tr("Cancel"), lambda: d.close(None)),
                               ui.button(ok or tr("OK"), accept, primary=True)])], spacing=10)
    return show(title, build)


def get_text_ok(title, label, text=""):
    """Like QInputDialog.getText used to: -> (text, ok)."""
    r = get_text(title, label, text)
    return (r or "", r is not None)


# ---------- Files and colors ----------
def _files(title, mode, filters, start):
    from ui import qfiles
    d = Dialog(title or tr("Choose file"), kind="file")
    d.tool = qfiles.FilesBackend(mode, filters, start, done=lambda paths, flt: d.close(paths or None))
    r = _open(d, True)
    return r or []


def open_file(title, directory="", filters=""):
    """-> path or "" (cancelled)."""
    r = _files(title, "open", filters, directory)
    return r[0] if r else ""


def open_files(title, directory="", filters=""):
    """-> [paths] (empty = cancelled)."""
    return _files(title, "many", filters, directory)


def save_file(title, path="", filters=""):
    """path: suggestion (folder and/or file name). -> target path or ""."""
    r = _files(title, "save", filters, path)
    return r[0] if r else ""


def get_dir(title, directory=""):
    """-> folder or ""."""
    r = _files(title, "dir", "", directory)
    return r[0] if r else ""


def get_color(initial="#ffffff", title=""):
    """-> "#rrggbb" or None."""
    from ui import qfiles
    d = Dialog(title or tr("Choose color"), kind="color")
    d.tool = qfiles.ColorBackend(initial, done=d.close)
    return _open(d, True)


# ---------- Transition: old QDialog via the mirror ----------
