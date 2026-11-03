"""File picker and color picker in the program window (Qt Quick): qml/components/FileBrowser.qml and ColorPicker.qml.

Called via qdialogs (open_file, save_file, get_dir, get_color …). The result goes to done():
FilesBackend: done([paths], filter text) or done(None) on cancel; ColorBackend: done("#rrggbb") or done(None).
"""
import fnmatch
import os
import re
import string
import time
from pathlib import Path

from PySide6 import QtCore, QtGui

from system.i18n import tr


def _places():
    home = Path.home()
    out = []
    for name, p in ((tr("Desktop"), home / "Desktop"), (tr("Downloads"), home / "Downloads"),
                    (tr("Documents"), home / "Documents"), (tr("images"), home / "Pictures"),
                    (tr("Home folder"), home)):
        if p.is_dir():
            out.append({"name": name, "path": str(p)})
    try:
        from system import datahome
        d = Path(datahome.HOME)
        if d.is_dir():
            out.append({"name": tr("Bent°Corner data"), "path": str(d)})
    except Exception:  # noqa: BLE001 – without a data folder just leave it out
        pass
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            p = Path(f"{letter}:/")
            if p.exists():
                out.append({"name": f"{letter}:", "path": str(p), "drive": True})
    else:
        out.append({"name": "/", "path": "/", "drive": True})
    return out


def _size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024.0
    return ""


class FilesBackend(QtCore.QObject):
    changed = QtCore.Signal()     # folder/entries
    selChanged = QtCore.Signal()  # selection, file name – separate so the list isn't rebuilt on click
                                  # (otherwise the double click would get lost)

    def __init__(self, mode, filters="", start="", done=None, parent=None):
        """mode: "open" | "many" | "save" | "dir"; filters: "CSV (*.csv);;All (*)" or a list."""
        super().__init__(parent)
        self._done = done
        self._mode = mode
        if isinstance(filters, str):
            filters = [f for f in filters.split(";;") if f.strip()]
        self._filters = []
        for f in filters:
            m = re.search(r"\(([^)]*)\)", f)
            pats = (m.group(1) if m else f).split()
            self._filters.append({"text": f, "pats": [p.lower() for p in pats]})
        if not self._filters:
            self._filters = [{"text": tr("All files (*)"), "pats": ["*"]}]
        self._filter = 0
        start = str(start or "")
        name = ""
        p = Path(start).expanduser() if start else None
        if p is not None and not p.is_dir() and (p.suffix or not p.exists()):
            name = p.name
            p = p.parent if str(p.parent) not in ("", ".") else None
        if p is None or not p.is_dir():
            p = Path.home() / "Desktop" if (Path.home() / "Desktop").is_dir() else Path.home()
        self._dir, self._name, self._sel = p.resolve(), name, []
        self._entries = []
        self._read()

    # ---------- Reading the folder ----------
    def _match(self, name):
        pats = self._filters[self._filter]["pats"]
        low = name.lower()
        return any(p in ("*", "*.*") or fnmatch.fnmatch(low, p) for p in pats)

    def _read(self):
        dirs, files = [], []
        try:
            for e in os.scandir(self._dir):
                if e.name.startswith(".") or e.name.startswith("$"):
                    continue
                try:
                    if e.is_dir():
                        dirs.append({"name": e.name, "path": e.path, "dir": True, "size": "", "date": ""})
                    elif self._mode != "dir" and self._match(e.name):
                        st = e.stat()
                        files.append({"name": e.name, "path": e.path, "dir": False, "size": _size(st.st_size),
                                      "date": time.strftime("%d.%m.%Y %H:%M", time.localtime(st.st_mtime))})
                except OSError:
                    continue
        except OSError:
            pass
        dirs.sort(key=lambda x: x["name"].lower())
        files.sort(key=lambda x: x["name"].lower())
        self._entries = dirs + files
        self._sel = []
        self.changed.emit()
        self.selChanged.emit()

    # ---------- for QML ----------
    @QtCore.Property(str, constant=True)
    def mode(self):
        return self._mode

    @QtCore.Property(str, notify=changed)
    def path(self):
        return str(self._dir)

    @QtCore.Property("QVariantList", notify=changed)
    def crumbs(self):
        parts, p = [], self._dir
        while True:
            parts.append({"name": p.name or str(p), "path": str(p)})
            if p.parent == p:
                break
            p = p.parent
        return list(reversed(parts))

    @QtCore.Property("QVariantList", constant=True)
    def places(self):
        return _places()

    @QtCore.Property("QVariantList", notify=changed)
    def entries(self):
        return list(self._entries)

    @QtCore.Property("QVariantList", notify=selChanged)
    def selected(self):
        return list(self._sel)

    @QtCore.Property("QVariantList", constant=True)
    def filters(self):
        return [{"key": str(i), "text": f["text"]} for i, f in enumerate(self._filters)]

    @QtCore.Property(str, notify=changed)
    def filter(self):
        return str(self._filter)

    @QtCore.Slot(str)
    def setFilter(self, key):
        self._filter = max(0, min(len(self._filters) - 1, int(key)))
        self._read()

    @QtCore.Property(str, notify=selChanged)
    def fileName(self):
        return self._name

    @QtCore.Slot(str)
    def setFileName(self, t):
        if t != self._name:
            self._name = t
            self.selChanged.emit()  # "Save" only becomes clickable with a name

    @QtCore.Property(bool, notify=selChanged)
    def canAccept(self):
        if self._mode == "dir":
            return True
        if self._mode == "save":
            return bool(self._name.strip())
        return bool(self._sel)

    @QtCore.Property(str, constant=True)
    def acceptText(self):
        return {"dir": tr("Choose this folder"), "save": tr("Save"), "many": tr("Open"),
                "open": tr("Open")}[self._mode]

    @QtCore.Slot(str)
    def cd(self, path):
        p = Path(path)
        if p.is_dir():
            self._dir = p.resolve()
            self._read()

    @QtCore.Slot()
    def up(self):
        if self._dir.parent != self._dir:
            self.cd(str(self._dir.parent))

    @QtCore.Slot(str, bool)
    def click(self, path, add):
        """Click on an entry: select a file (Ctrl/Shift with "many" = add), only highlight folders."""
        p = Path(path)
        if p.is_dir():
            self._sel = [path]
        elif self._mode == "many" and add:
            self._sel = [s for s in self._sel if s != path] if path in self._sel else self._sel + [path]
        else:
            self._sel = [path]
            if self._mode == "save":
                self._name = p.name
        self.selChanged.emit()

    @QtCore.Slot(str)
    def open(self, path):
        """Double click: enter a folder, take a file immediately."""
        p = Path(path)
        if p.is_dir():
            self.cd(path)
            return
        self._sel = [path]
        if self._mode == "save":
            self._name = p.name
        self.accept()

    # ---------- new folder: like in Explorer – create immediately, type the name directly in the list ----------
    editingChanged = QtCore.Signal()

    @QtCore.Property(str, notify=editingChanged)
    def editing(self):
        """Path of the entry whose name is currently being typed in the list ("" = none)."""
        return getattr(self, "_editing", "")

    @QtCore.Property(str, notify=editingChanged)
    def error(self):
        return getattr(self, "_error", "")

    @QtCore.Slot()
    def newFolder(self):
        """Create a folder "New folder" (or "New folder (2)" …) and open it for renaming – without a question window
        (those don't exist before the program window, e.g. in the first-run setup)."""
        base = tr("New folder")
        target, n = self._dir / base, 2
        while target.exists():
            target, n = self._dir / f"{base} ({n})", n + 1
        try:
            target.mkdir()
        except OSError as e:
            self._error = tr(f"Couldn't create the folder: {e}")
            self.editingChanged.emit()
            return
        self._error = ""
        self._read()
        self._sel, self._editing = [str(target)], str(target)
        self.selChanged.emit()
        self.editingChanged.emit()

    @QtCore.Slot(str, str)
    def rename(self, path, name):
        """Name finished typing (Enter/focus lost). Empty or unchanged: stays as it is."""
        self._editing, self._error = "", ""
        name, old = name.strip(), Path(path)
        new = old.with_name(name) if name else old
        if name and new != old:
            try:
                old.rename(new)
            except OSError as e:
                self._error, new = tr(f"Couldn't rename: {e}"), old
        self._read()
        self._sel = [str(new)]
        self.selChanged.emit()
        self.editingChanged.emit()

    @QtCore.Slot()
    def accept(self):
        if self._mode == "dir":
            sel = [s for s in self._sel if Path(s).is_dir()]
            out = [sel[0] if sel else str(self._dir)]
        elif self._mode == "save":
            name = self._name.strip()
            if not name:
                return
            target = Path(name) if Path(name).is_absolute() else self._dir / name
            pats = self._filters[self._filter]["pats"]
            if not target.suffix and len(pats) == 1 and pats[0].startswith("*.") and pats[0] != "*.*":
                target = target.with_suffix(pats[0][1:])
            if target.exists():
                from ui import qdialogs
                if not qdialogs.question(tr("Overwrite?"), tr(f"“{target.name}” already exists – replace it?")):
                    return
            out = [str(target)]
        else:
            out = [s for s in self._sel if Path(s).is_file()]
            if not out:
                return
        if self._done:
            self._done(out, self._filters[self._filter]["text"])

    @QtCore.Slot()
    def cancel(self):
        if self._done:
            self._done(None, "")


class ColorBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, initial="#ffffff", done=None, parent=None):
        super().__init__(parent)
        self._done = done
        c = QtGui.QColor(initial)
        if not c.isValid():
            c = QtGui.QColor("#ffffff")
        self._h, self._s, self._v = max(0.0, c.hsvHueF()), c.hsvSaturationF(), c.valueF()

    @QtCore.Property(float, notify=changed)
    def hue(self):
        return self._h

    @QtCore.Property(float, notify=changed)
    def sat(self):
        return self._s

    @QtCore.Property(float, notify=changed)
    def val(self):
        return self._v

    @QtCore.Slot(float, float, float)
    def setHsv(self, h, s, v):
        self._h, self._s, self._v = max(0.0, min(1.0, h)), max(0.0, min(1.0, s)), max(0.0, min(1.0, v))
        self.changed.emit()

    @QtCore.Property(str, notify=changed)
    def hex(self):
        return QtGui.QColor.fromHsvF(self._h, self._s, self._v).name()

    @QtCore.Slot(str)
    def setHex(self, t):
        c = QtGui.QColor(t.strip() if t.strip().startswith("#") else "#" + t.strip())
        if c.isValid():
            self._h, self._s, self._v = max(0.0, c.hsvHueF()), c.hsvSaturationF(), c.valueF()
            self.changed.emit()

    @QtCore.Property("QVariantList", constant=True)
    def presets(self):
        return ["#f2f2f2", "#bdbdbd", "#8e8e8e", "#5e5e5e", "#2a2a2a", "#111111",
                "#e05555", "#e0913d", "#e7c35a", "#46d17a", "#3fb7b0", "#4a90d9", "#8a6ee0", "#d45ab0"]

    @QtCore.Slot()
    def accept(self):
        if self._done:
            self._done(QtGui.QColor.fromHsvF(self._h, self._s, self._v).name())

    @QtCore.Slot()
    def cancel(self):
        if self._done:
            self._done(None)
