"""Settings in Qt Quick (qml/pages/SettingsPage.qml): sections on the left, the chosen section on the right as a
form (qform), built directly from settings and program state (qsetpages) – without widgets.

Search (field above the sections): every section is built and searched – hits show up live (switches work right in
the list); clicking a hit's heading opens its section and lights the row up briefly (node "flash", MirrorNode.qml)."""
import html
import re

from PySide6 import QtCore

from ui import qform
from ui import qsetpages
from ui import qstate
from system.i18n import tr

# Words people search for that the settings say differently (both languages; the search compares lower case)
SYNONYMS = {"tray": "infobereich", "taskleiste": "infobereich", "taskbar": "notification area",
            "system tray": "notification area", "autostart": "windows", "backup": "sicherung", "sichern": "sicherung",
            "datenschutz": "privatsphäre", "privacy": "privacy", "dunkel": "skin", "dark": "skin", "theme": "skin",
            "farbe": "skin", "schrift": "skin", "font": "skin", "kamera": "kamera", "webcam": "kamera",
            "preis": "preis", "price": "price", "alarm": "preisalarm", "freund": "freund", "friend": "friend",
            "update": "update", "version": "update", "sprache": "sprache", "language": "language",
            "ordner": "ordner", "folder": "folder", "lizenz": "drittanbieter", "license": "third-party",
            "ki": "anthropic", "ai": "anthropic",   # only the note on the code (About) – never SCAN°
            "session": "log", "sessions": "log", "sitzung": "log", "sitzungen": "log",   # the old names of the Log
            "logs": "log", "verlauf": "log", "history": "log", "stats": "statistik"}   # the tab „Logs & stats“
FLASH_MS = 2600   # how long a jumped-to row stays marked


def _text(node):
    """Everything a person can read on a node (and its children): labels, buttons, choices, tips – lower case."""
    out = []

    def walk(nd):
        if not isinstance(nd, dict):
            return
        for key in ("html", "text", "title", "tip", "placeholder"):
            v = nd.get(key)
            if isinstance(v, str) and v:
                out.append(v)
        if nd.get("t") == "combo":
            out.extend(str(x) for x in nd.get("items") or [])
        for key in ("items", "cells"):
            for c in nd.get(key) or []:
                walk(c.get("node") if isinstance(c, dict) and "node" in c and key == "cells" else c)
        for key in ("label", "field"):
            walk(nd.get(key))
    walk(node)
    return html.unescape(re.sub(r"<[^>]+>", " ", " ".join(out))).lower()


def _terms(query):
    q = query.strip().lower()
    return [t for t in {q, SYNONYMS.get(q, q)} if t]


def _hits(node, terms, group=""):
    """-> [(group title, node)] – the smallest parts of a section that match (a row of a group, a form row …)."""
    if not isinstance(node, dict):
        return []
    t = node.get("t")
    if t == "group":
        title = node.get("title") or group
        out = []
        for it in node.get("items") or []:
            out += _hits(it, terms, title)
        if not out and any(x in (node.get("title") or "").lower() for x in terms):   # heading matches: whole group
            out = [(title, it) for it in node.get("items") or []]
        return out
    if t == "scroll":   # long lists (patch history …) are reading matter, not settings
        return []
    if t in ("col", "form") or (t == "row" and any((c or {}).get("t") in ("group", "col") for c in node.get("items") or [])):
        out = []
        for it in node.get("items") or []:
            out += _hits(it, terms, group)
        return out
    if t in ("stretch", "space", "line", "camera", "game", "fortune", "image"):
        return []
    text = _text(node)
    return [(group, node)] if any(x in text for x in terms) else []


def _flatten(node, inside=False):
    """Design rule "no boxes in boxes": a group inside a group becomes a section (divider + heading)."""
    if not isinstance(node, dict):
        return
    if node.get("t") == "group":
        if inside:
            node["flat"] = True
        inside = True
    for key in ("items", "cells"):
        for c in node.get(key) or []:
            _flatten(c.get("node") if key == "cells" and isinstance(c, dict) else c, inside)
    for key in ("label", "field"):
        _flatten(node.get(key), inside)


def _mark(node, terms, index=0):
    """The index-th node of the section that matches (the hit that was clicked) -> "flash" + "flashStay"
    (MirrorNode scrolls to it, blinks twice and keeps it marked until the mouse is over it – review .101, a7)."""
    found = _hits(node, terms)
    if found:
        found[min(index, len(found) - 1)][1].update(flash=True, flashStay=True)


ARRIVE = "\x00arrive"   # flash marker: came by a link – pulse the section's first block


def _mark_first(node):
    """Link into the settings: the section's first block (group, else first part) -> "flash"."""
    items = [it for it in (node.get("items") or []) if isinstance(it, dict) and it.get("t") not in ("space", "stretch", "line")]
    if not items:
        return
    group = next((it for it in items if it.get("t") == "group"), items[0])
    group["flash"] = True


class SettingsBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.state = {}  # state of the forms (search text, messages …), kept on refresh
        self._active = False
        self._query = ""   # settings search ("" = show the chosen section)
        self._count = {}   # page -> hits of the current search
        self._flash = ""   # term to light up after jumping from a hit
        self._flash_i = 0  # … which of the section's hits (the one clicked)
        self._flash_page = ""   # … in which section (a search hit stays marked until seen – not in other sections)
        self.form = qform.Form(self._build, self)
        # program state changes (progress, camera, pack …): refresh in bulk, only when visible
        self._later = QtCore.QTimer(self, singleShot=True, interval=120, timeout=self.form.refresh)
        self._unflash = QtCore.QTimer(self, singleShot=True, interval=FLASH_MS, timeout=self._flash_off)
        qstate.watch(self._state_changed)
        ctrl.settings_listeners.append(self._page_changed)
        self._tick = QtCore.QTimer(self, interval=1000, timeout=self.form.refresh)  # time/counter values

    def _build(self, ui):
        if self._query:
            return self._search(ui)
        node = qsetpages.build(self.ctrl.settings_page, ui, self)
        _flatten(node)
        if self._flash == ARRIVE:
            _mark_first(node)
        elif self._flash and self.ctrl.settings_page == self._flash_page:
            _mark(node, _terms(self._flash), self._flash_i)
        return node

    def _search(self, ui):
        """All sections, only the parts that match – live (switches work right here)."""
        from app import SETTINGS_PAGES
        terms = _terms(self._query)
        blocks, count = [], {}
        for key, _icon, title, _sub in SETTINGS_PAGES:
            if key == "game":
                continue
            try:
                found = _hits(qsetpages.build(key, ui, self), terms)
            except Exception:  # noqa: BLE001 – one broken section must not hide the others
                import logging
                logging.getLogger("booster").exception("Settings search in %s", key)
                continue
            if not found:
                continue
            count[key] = len(found)
            if blocks:   # between hits of different sections a divider, within one section only space
                blocks.append(ui.line())
            for i, (group, nd) in enumerate(found):   # per hit: path button ("General › Window"), the setting, space
                nd = {"t": "form", "items": [nd], "spacing": 8, "ml": 0} if nd.get("t") == "formrow" else nd
                path = tr(title) + (f"  ›  {group}" if group else "")
                box = ui.col([ui.row([ui.button(path, lambda k=key, n=i: self.jump(k, n), tip=tr("Open this section")),
                                      ui.stretch()]), nd], spacing=8)
                _flatten(box)
                blocks.append(box)
                blocks.append(ui.space(10))
        if count != self._count:
            self._count = count
            QtCore.QTimer.singleShot(0, self.changed.emit)   # hit counts next to the sections
        if not blocks:
            return ui.col([ui.note(tr(f"Nothing found for “{self._query}”."))])
        return ui.col(blocks + [ui.note(tr("Click a path to open its section – the switches work right here in the list."))],
                      spacing=10)

    def _state_changed(self):
        if self._active and not self._later.isActive():
            self._later.start()

    def _page_changed(self, _key):
        self.form.set_build(self._build)  # other section: discard drafts, rebuild
        self.changed.emit()

    def _flash_off(self):
        self._flash = ""
        self.form.refresh()

    def shell_theme(self):
        """Colours/fonts changed: pass them to Qt Quick immediately."""
        shell = getattr(self.ctrl, "shell", None)
        if shell is not None:
            shell.refresh_theme()

    @QtCore.Slot(bool)
    def setActive(self, on):
        self._active = bool(on)
        self._tick.start() if on else self._tick.stop()
        if on:
            if self.ctrl.settings_page == "sets":
                self.ctrl.image_store.refresh()
            self.form.refresh()

    @QtCore.Property("QVariantList", notify=changed)
    def pages(self):
        from app import SETTINGS_PAGES, SETTINGS_SECTIONS
        from system import autobackup
        warn = autobackup.lamp(self.ctrl.settings)   # backup missing: indicator light on the "Backup" tab
        u = getattr(self.ctrl, "updater", None)
        ready = bool(u is not None and u.state in ("ready", "available"))   # update available: indicator light on the "Updates" tab
        return [{"key": k, "icon": icon, "title": tr(t), "sub": tr(sub), "section": tr(SETTINGS_SECTIONS.get(k, "")),
                 "hits": self._count.get(k, 0) if self._query else -1,
                 "badge": (warn and k == "backup") or (ready and k == "updates")}
                for k, icon, t, sub in SETTINGS_PAGES]

    @QtCore.Property(str, notify=changed)
    def current(self):
        return "" if self._query else self.ctrl.settings_page

    @QtCore.Property(str, notify=changed)
    def query(self):
        return self._query

    @QtCore.Property(str, notify=changed)
    def heading(self):
        """Head of the right side while searching."""
        if not self._query:
            return ""
        n = sum(self._count.values())
        return tr(f"{n} hits for “{self._query}”") if n != 1 else tr(f"1 hit for “{self._query}”")

    @QtCore.Slot(str)
    def search(self, text):
        text = (text or "").strip()
        if text == self._query:
            return
        self._query = text
        if text:
            self._flash = ""   # a new search: the old hit's mark is done
        else:
            self._count = {}
        self.form.set_build(self._build)
        self.changed.emit()

    def jump(self, key, index=0):
        """Hit path clicked: leave the search, open the section and pulse the hit (the index-th of that section)."""
        self._flash, self._flash_i, self._flash_page = self._query, index, key
        self._query, self._count = "", {}
        self._unflash.stop()   # stays marked until the mouse was over it (flashSeen)
        if key == self.ctrl.settings_page:
            self.form.set_build(self._build)
            self.changed.emit()
        else:
            self.ctrl.show_settings(key)

    @QtCore.Slot()
    def flashSeen(self):
        """The mouse was over the marked search hit (MirrorNode): the mark has faded, a rebuild doesn't bring it back."""
        if self._flash != ARRIVE:
            self._flash = ""

    def arrive(self, key):
        """A link from elsewhere ("↗ Settings → Backup"): an old search is cleared, the section opens and its first
        block pulses once – you see where you landed."""
        self._query, self._count = "", {}
        self._flash, self._flash_i = ARRIVE, 0
        self._unflash.start()
        if key == self.ctrl.settings_page:
            self.form.set_build(self._build)
        else:
            self.ctrl.show_settings(key)
        self.changed.emit()

    @QtCore.Slot(str)
    def show(self, key):
        searching = bool(self._query)
        self._query, self._count = "", {}
        if searching and key == self.ctrl.settings_page:   # same section: no page change that would rebuild
            self.form.set_build(self._build)
        else:
            self.ctrl.show_settings(key)
        self.changed.emit()

    @QtCore.Property(QtCore.QObject, constant=True)
    def mirror(self):
        return self.form
