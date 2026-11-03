"""Forms for Qt Quick – without widgets.

A Form describes its appearance anew from the data on every refresh: build(ui) uses the building blocks of UI
(text, button, checkbox, selection, number, input, list, table, chart …, plus row/column/form/group) to build a
tree; inputs from QML call the given Python function directly. Drawing is done with the same QML building blocks
by qml/components/Mirror.qml / MirrorNode.qml (interface: tree, rev, val, act).

    def build(ui):
        return ui.col([
            ui.label(tr("Hello")),
            ui.check(tr("Show prices"), s["prices"], lambda on: s.update(prices=on)),
            ui.row([ui.button(tr("OK"), ok, primary=True), ui.stretch()]),
        ])
    form = Form(build)            # form.refresh() after data changes from outside (otherwise: after every input)

Typed text survives a refresh (draft per input field, key key=…) until Enter/focus lost.
"""
import logging

from PySide6 import QtCore, QtQml

log = logging.getLogger(__name__)

CONTAINERS = {"row", "col", "form", "grid", "group", "formrow", "tabs", "scroll"}


def _split(nodes, path, vals):
    """Tree -> (structure, values). Structure = only kind + key + children (rarely changes); values per key =
    everything else (texts, checkboxes, numbers, images …). That way QML only rebuilds on a new structure – values
    change in place (focus, mouse grab and scrolling text stay)."""
    out = []
    for i, nd in enumerate(nodes):
        if not isinstance(nd, dict):
            out.append(nd)
            continue
        k = f"{path}/{i}"
        t = nd.get("t", "")
        shape = {"t": t, "k": k}
        val = {key: v for key, v in nd.items() if not (t in CONTAINERS and key in ("items", "cells", "label", "field"))}
        val["k"] = k
        if t in CONTAINERS:
            if "items" in nd:
                shape["items"] = _split(nd["items"], k, vals)
            if "cells" in nd:
                shape["cells"] = [{"r": c["r"], "c": c["c"], "node": _split([c["node"]], f"{k}c{j}", vals)[0]}
                                  for j, c in enumerate(nd["cells"])]
                shape["cols"] = nd.get("cols", 1)
            for side in ("label", "field"):
                if nd.get(side):
                    shape[side] = _split([nd[side]], f"{k}{side[0]}", vals)[0]
        vals[k] = val
        out.append(shape)
    return out


class _Tree(QtCore.QObject):
    """Tree for QML: tree = structure (new only on a different structure), val(k) = values of a building block (rev
    counts value changes). Subclasses provide the tree in _read()."""
    changed = QtCore.Signal()
    valuesChanged = QtCore.Signal()
    valsChanged = QtCore.Signal("QVariantMap")   # {key: True} – only these building blocks re-read their values

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tree, self._vals, self._rev, self._vjson = [], {}, 0, {}

    @QtCore.Slot()
    def refresh(self):
        import json
        tree = self._read()
        vals = {}
        shape = _split(tree, "", vals)
        skey = json.dumps(shape, sort_keys=True, default=str)
        vjson = {k: json.dumps(v, sort_keys=True, default=str) for k, v in vals.items()}
        keys = {k: True for k, j in vjson.items() if self._vjson.get(k) != j}
        if keys or len(vjson) != len(self._vjson):
            # per key: a slider step re-reads one building block in QML, not all of them (review of a tester log:
            # 250–300 ms per step in the camera dialog, every node of the form re-read and re-laid out)
            self._vjson, self._vals = vjson, vals
            self._rev += 1
            self.valuesChanged.emit()
            if keys:
                self.valsChanged.emit(keys)
        if skey != getattr(self, "_skey", None):  # QML only rebuilds on a new structure
            self._skey, self._tree = skey, shape
            self.changed.emit()

    def _read(self):
        return []

    @QtCore.Property("QVariantList", notify=changed)
    def tree(self):
        return self._tree

    @QtCore.Property(int, notify=valuesChanged)
    def rev(self):
        return self._rev

    @QtCore.Slot(str, result="QVariantMap")
    def val(self, k):
        return self._vals.get(k) or {}


class UI:
    """Building blocks. Every method returns a node (dict); the Form remembers the callback functions."""

    def __init__(self, form):
        self._f = form
        self._n = 0

    def _id(self, fn=None, key=None):
        self._n += 1
        wid = f"f{self._n}"
        if fn is not None:
            self._f._cb[wid] = fn
        if key is not None:
            self._f._keys[wid] = key
        return wid

    # ---------- Texts ----------
    def label(self, html, *, color="", wrap=True, bold=False, big=False, px=0, tip="", rich=None, fixed=False, font=""):
        """color: color value, "gray" (muted) or "" (normal). fixed: in a row only as wide as the text.
        font: own font family (e.g. for a preview)."""
        html = "" if html is None else str(html)
        if rich is None:
            import re
            rich = ("<" in html and ">" in html) or bool(re.search(r"&(#\d+|[a-z]+);", html))
        return {"t": "label", "html": html, "rich": bool(rich), "wrap": wrap, "tip": tip, "color": color,
                "bold": bold, "big": big, "px": px, "fixed": fixed, "font": font}

    def title(self, text):
        return self.label(text, bold=True, big=True)

    def note(self, text):
        return self.label(text, color="gray")

    def slot_note(self, text):
        """Hint that comes and goes without changing the structure (empty = invisible). For hints below
        input fields: a new structure would rebuild the field and take away the focus mid-typing."""
        nd = self.note(text or "")
        nd["hidden"] = not text
        return nd

    # ---------- Inputs ----------
    def button(self, text, fn, *, tip="", danger=False, active=False, enabled=True, checkable=False, checked=False,
               glyph="", primary=False):
        """active = selected/on (sunken, e.g. segments); primary = main action (raised, light border)."""
        return {"t": "button", "id": self._id(lambda _v: fn()), "text": text, "enabled": enabled, "tip": tip,
                "checkable": checkable, "checked": checked, "danger": danger, "glyph": glyph, "active": active,
                "primary": primary}

    def seg(self, options, current, fn, *, tip=""):
        """Short choice (≤ 4 values) as a row of buttons, the chosen one bright (instead of a dropdown).
        options: [(value, text)] or [text]; fn(value)."""
        opts = [o if isinstance(o, (list, tuple)) else (o, o) for o in options]
        return self.row([self.button(str(label), lambda v=value: fn(v), active=value == current, tip=tip)
                         for value, label in opts] + [self.stretch()], spacing=6)

    def tag(self, text, fn=None, *, tip="", on=True, plain=False):
        """Outlined, transparent box with text (like the condition tags in the scan); with fn: click toggles.
        plain: without border – text only (e.g. the finish, so it doesn't look like the condition)."""
        return {"t": "tag", "id": self._id((lambda _v: fn()) if fn else None), "text": text, "tip": tip,
                "on": bool(on), "click": fn is not None, "plain": bool(plain)}

    def check(self, text, checked, fn, *, tip="", enabled=True):
        return {"t": "check", "id": self._id(lambda v: fn(bool(v))), "text": text, "checked": bool(checked),
                "enabled": enabled, "tip": tip}

    def combo(self, options, current, fn, *, tip="", enabled=True):
        """options: [(value, text)] or [text]; fn(value)."""
        opts = [o if isinstance(o, (list, tuple)) else (o, o) for o in options]
        values = [v for v, _ in opts]
        index = values.index(current) if current in values else (0 if opts else -1)
        return {"t": "combo", "id": self._id(lambda i: fn(values[int(i)]) if 0 <= int(i) < len(values) else None),
                "items": [str(t) for _, t in opts], "index": index, "enabled": enabled, "tip": tip}

    def spin(self, value, lo, hi, fn, *, step=1, suffix="", prefix="", decimals=0, tip="", enabled=True):
        cast = float if decimals else int
        return {"t": "spin", "id": self._id(lambda v: fn(cast(v))), "value": value, "min": lo, "max": hi,
                "step": step, "suffix": suffix, "prefix": prefix, "decimals": decimals, "enabled": enabled,
                "tip": tip}

    def edit(self, text, fn, *, key=None, live=None, placeholder="", tip="", enabled=True):
        """fn(text) on Enter/focus lost; live(text) on every keystroke (optional)."""
        wid = self._id(None, key)
        k = key or wid
        self._f._cb[wid] = lambda v, k=k: self._f._text(k, v, fn, live)
        shown = self._f._drafts.get(k, text)
        return {"t": "edit", "id": wid, "text": "" if shown is None else str(shown), "placeholder": placeholder,
                "enabled": enabled, "tip": tip}

    def textarea(self, text, fn, *, key=None, live=None, placeholder="", h=120, read_only=False, enabled=True):
        wid = self._id(None, key)
        k = key or wid
        self._f._cb[wid] = lambda v, k=k: self._f._text(k, v, fn, live)
        shown = self._f._drafts.get(k, text)
        return {"t": "textarea", "id": wid, "text": "" if shown is None else str(shown), "placeholder": placeholder,
                "readOnly": read_only, "h": h, "enabled": enabled}

    def slider(self, value, lo, hi, fn, *, tip="", enabled=True):
        return {"t": "slider", "id": self._id(lambda v: fn(int(v))), "value": value, "min": lo, "max": hi,
                "enabled": enabled, "tip": tip}

    def progress(self, value, lo=0, hi=100, text=""):
        return {"t": "progress", "value": value, "min": lo, "max": hi, "text": text}

    def list(self, items, *, on_click=None, on_double=None, on_check=None, h=200, multi=False):
        """items: [{"text", "sel", "checkable", "checked", "enabled", "tip"}]; callbacks receive the row."""
        rows = []
        for r, it in enumerate(items):
            rows.append({"row": r, "text": it.get("text", ""), "sel": bool(it.get("sel")),
                         "checkable": bool(it.get("checkable")), "checked": bool(it.get("checked")),
                         "enabled": it.get("enabled", True), "tip": it.get("tip", "")})

        def act(v):
            kind, row = v[0], int(v[1])
            if kind == "check" and on_check:
                on_check(row, bool(v[2]))
            elif kind == "double" and on_double:
                on_double(row)
            elif on_click:
                on_click(row)
        return {"t": "list", "id": self._id(act), "items": rows, "h": h, "multi": multi}

    def table(self, cols, rows, *, sel=-1, on_click=None, on_double=None, empty="", h=220):
        """cols: [title] or [(title, stretch)]; rows: [[text, …]]."""
        cs = [{"title": c[0], "stretch": bool(c[1])} if isinstance(c, (list, tuple)) else {"title": c, "stretch": False}
              for c in cols]
        if cs and not any(c["stretch"] for c in cs):
            cs[0]["stretch"] = True

        def act(v):
            kind, row = v[0], int(v[1])
            if kind == "double" and on_double:
                on_double(row)
            elif on_click:
                on_click(row)
        return {"t": "table", "id": self._id(act), "cols": cs, "rows": [[str(x) for x in r] for r in rows],
                "sel": sel, "empty": empty, "h": h}

    def chart(self, spec, fn=None):
        """spec: see qcharts; fn(["mode"|"pick", i])."""
        return {"t": "chart", "id": self._id((lambda v: fn(list(v))) if fn else None), "h": spec.get("h", 220),
                "spec": spec}

    def cards(self, items, fn, tile_h=230, current=-1):
        """Horizontal card strip: items [{"img", "text", "sub", "tip", "hi", "head"}] (head: small heading above the
        tile, e.g. the set where a new one starts); current: the marked tile, scrolled into view; fn(index)."""
        return {"t": "cards", "id": self._id(lambda v: fn(int(v))), "items": items, "th": tile_h, "cur": current}

    def swatch(self, color, fn, tip=""):
        """Clickable color swatch."""
        return {"t": "swatch", "id": self._id(lambda _v: fn()), "color": color, "tip": tip or color}

    def image(self, url, w, h, tip="", link=""):
        """link: click opens the address in the browser (e.g. the Buy-me-a-coffee sticker)."""
        return {"t": "image", "url": url, "w": w, "h": h, "tip": tip, "link": link}

    def camera(self, which="preview", h=0):
        """which: "preview" (camera + scan frame) or "overlay" (stream overlay, scaled down, clickable)."""
        return {"t": "camera", "lv": which, "h": h}

    def fortune(self, quote=""):
        """Fortune Card (FortuneCard.qml): a card to flip over, with a saying on it."""
        return {"t": "fortune", "quote": quote}

    def pixel(self, back, fn):
        """Paint the card back (always 28 × 40, free colors). Uploading an image isn't available for now
        (userprofile.from_image stays)."""
        from system import userprofile
        from system.i18n import tr
        return {"t": "pixel", "id": self._id(lambda v: fn(str(v[1]))), "back": userprofile.normalize(back),
                "presets": [{"key": k, "name": tr(n), "data": d} for k, n, d in userprofile.PRESETS]}

    def orbit(self, level, fn, *, compact=False, leave="", decide=None):
        """Bent°Corner Orbit slider (OrbitSlider.qml): three stops Core · Near Orbit · Full Orbit with the picture and
        three columns (name, short sentence, what you get / what goes out); fn(level index 0–2). leave: what leaving
        Full Orbit does – pass it while Full Orbit is on (a reserved place, fades in below Full). decide(leave: bool):
        the settings' "Leave Full Orbit? [Stay] [Leave]" in that same place."""
        from system import contacts, orbit
        from system.i18n import tr

        def act(v):
            if v[0] in ("stay", "leave"):
                if decide is not None:
                    decide(v[0] == "leave")
            else:
                fn(int(v[0]))
        return {"t": "orbit", "id": self._id(act), "level": int(level), "compact": compact, "leave": leave,
                "confirm": decide is not None, "leaveAsk": tr("Leave Full Orbit?"), "stay": tr("Stay"), "leaveBtn": tr("Leave"),
                "names": [tr(orbit.NAMES[k]) for k in orbit.LEVELS], "lines": [tr(orbit.SHORT[k]) for k in orbit.LEVELS],
                "points": [[tr(p) for p in orbit.POINTS[k]] for k in orbit.LEVELS],
                "outs": [tr(orbit.OUT[k]) for k in orbit.LEVELS], "foot": tr(orbit.FOOT),
                "more": tr("More about it"), "less": tr("Less"),
                # Full Orbit: the terms (exchange) and the age – visible in its column before you choose it
                "terms": tr("<a href='{url}'>Terms of use</a> · age 13+").replace("{url}", contacts.SITE + "/nutzung.html"),
                "privacy": tr("All details: <a href='{url}'>privacy policy</a>").replace("{url}", contacts.SITE + "/datenschutz.html")}

    def picker(self, items, fn, *, placeholder="", tile_w=96, h=360):
        """Selection as tiles with search: items [{id, name, sub, img, icon, on}]; fn(id, on)."""
        def act(v):
            if v[0] == "*":   # "All" / "None"
                for it in items:
                    if bool(it.get("on")) != bool(v[1]):
                        fn(str(it["id"]), bool(v[1]))
                return
            fn(str(v[0]), bool(v[1]))
        return {"t": "picker", "id": self._id(act), "items": items,
                "placeholder": placeholder, "tileW": tile_w, "h": h}

    def checklist(self, items, fn, contents=None, *, key="ck", placeholder="", h=420):
        """Selection as a list: a check mark in front, clicking the row expands it and shows the content
        (contents(id) -> [{"text", "sub"}]). items [{id, name, sub, img, on}]; fn(id, on). Search at the top (from 7
        entries) and All/None. The form remembers what is expanded (per key)."""
        opened = self._f.__dict__.setdefault("_ck_open", {}).setdefault(key, set())

        def act(v):
            if v[0] == "*":   # "All" / "None"
                for it in items:
                    if bool(it.get("on")) != bool(v[1]):
                        fn(str(it["id"]), bool(v[1]))
                return
            if v[0] == "open":
                i = str(v[1])
                (opened.discard if i in opened else opened.add)(i)
                return
            fn(str(v[0]), bool(v[1]))
        out = []
        for it in items:
            i = str(it["id"])
            row = dict(it, id=i, open=i in opened)
            if i in opened and contents is not None:
                try:
                    row["lines"] = list(contents(i) or [])[:300]
                except Exception:  # noqa: BLE001 – the content is only for viewing
                    log.exception("Content of a list")
                    row["lines"] = []
            out.append(row)
        return {"t": "checklist", "id": self._id(act), "items": out, "placeholder": placeholder, "h": h}

    def datetime(self, value, fn):
        """value/fn: QDateTime."""
        from system import i18n

        def act(v):
            dt = QtCore.QDateTime.fromString(str(v), "yyyy-MM-ddTHH:mm")
            if dt.isValid():
                fn(dt)
        return {"t": "datetime", "id": self._id(act), "value": value.toString("yyyy-MM-ddTHH:mm"),
                "loc": "en_US" if i18n.LANG == "en" else "de_DE"}

    def tags(self, tags, suggestions, fn, placeholder=""):
        """fn(new list)."""
        cur = list(tags)

        def act(v):
            kind, tag = v[0], str(v[1]).strip()
            if kind == "add" and tag and tag not in cur:
                fn(cur + [tag])
            elif kind == "remove":
                fn([t for t in cur if t != tag])
        return {"t": "tags", "id": self._id(act), "tags": cur, "suggestions": [s for s in suggestions if s not in cur],
                "placeholder": placeholder}

    # ---------- Layout ----------
    @staticmethod
    def _clean(items):
        return [i for i in items if i]

    def row(self, items, spacing=8):
        return {"t": "row", "items": self._clean(items), "spacing": spacing, "ml": 0}

    def col(self, items, spacing=6, w=1):
        """w: share of the width when the column sits in a row next to others (default 1 = equal width)."""
        return {"t": "col", "items": self._clean(items), "spacing": spacing, "ml": 0, "w": w}

    def scroll(self, items, h=300, spacing=6):
        """Column in an area of fixed height – longer content scrolls (with scrollbar)."""
        return {"t": "scroll", "items": self._clean(items), "spacing": spacing, "h": h, "ml": 0}

    def form(self, rows):
        """rows: [(label or node or None, field node)] – None rows are dropped."""
        out = []
        for r in rows:
            if not r:
                continue
            lab, field = r
            if isinstance(lab, str):
                lab = self.label(lab, wrap=False)
            out.append({"t": "formrow", "label": lab, "field": field})
        return {"t": "form", "items": out, "spacing": 8, "ml": 0}

    def grid(self, cells, cols):
        """cells: nodes row by row (cols per row)."""
        cl = [c for c in cells]
        return {"t": "grid", "cells": [{"r": i // cols, "c": i % cols, "node": n} for i, n in enumerate(cl) if n],
                "cols": cols, "spacing": 8, "ml": 0}

    def group(self, title, items, *, checked=None, fn=None, lamp=False, flat=False):
        """flat: no box – section with a divider line above (for columns that are already a window themselves)."""
        node = {"t": "group", "title": title, "items": self._clean(items)}
        if flat:
            node["flat"] = True
        if lamp:
            node["lamp"] = True   # orange hint light next to the heading (what triggers the glow)
        if checked is not None:
            node["id"] = self._id(lambda v: fn(bool(v)))
            node["checked"] = bool(checked)
        return node

    def tabs(self, names, index, fn, content):
        return {"t": "tabs", "id": self._id(lambda v: fn(int(v))), "tabs": list(names), "index": index,
                "items": self._clean([content])}

    def line(self):
        return {"t": "line"}

    def stretch(self):
        return {"t": "stretch"}

    def space(self, h=8):
        return {"t": "space", "h": h}


class Form(_Tree):
    """Form from build(ui)."""

    def __init__(self, build=None, parent=None):
        super().__init__(parent)
        self.build = build
        self._cb, self._keys, self._drafts = {}, {}, {}
        self._soon = QtCore.QTimer(self, singleShot=True, interval=0, timeout=self.refresh)
        if build is not None:
            self.refresh()

    def set_build(self, build):
        self.build = build
        self._drafts = {}
        self.refresh()

    def soon(self):
        """Refresh soon (several calls in a row = once)."""
        self._soon.start()

    def _read(self):
        self._cb, self._keys = {}, {}
        if self.build is None:
            return []
        try:
            node = self.build(UI(self))
        except Exception:  # noqa: BLE001 – an error while building must not empty the whole page
            log.exception("Building form")
            return getattr(self, "_last_good", [])
        tree = [n for n in (node if isinstance(node, list) else [node]) if n]
        self._last_good = tree
        return tree

    def _text(self, k, v, fn, live):
        if isinstance(v, (list, tuple)) and v and v[0] == "live":
            text = str(v[1])
            self._drafts[k] = text
            if live is not None:
                live(text)
                self.soon()
            return
        self._drafts.pop(k, None)
        if fn is not None:
            fn(str(v))

    @QtCore.Slot(str, "QVariant")
    def act(self, wid, value=None):
        fn = self._cb.get(wid)
        if fn is None:
            return
        if isinstance(value, QtQml.QJSValue):  # JS arrays ([kind, row, …]) arrive as QJSValue depending on the path
            value = value.toVariant()
        try:
            fn(value)
        except Exception:  # noqa: BLE001
            log.exception("Input in form")
        if not (isinstance(value, (list, tuple)) and value and value[0] == "live"):
            self.soon()
