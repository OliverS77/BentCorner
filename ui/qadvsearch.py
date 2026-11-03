"""Advanced search in Qt Quick (qml/components/AdvSearch.qml) – for the library and deck builder.

The sections are searchbox objects (without widgets, they provide SearchBox.filters()); here their state is read
for QML and every input is passed on to them.
"""
import time

from PySide6 import QtCore, QtGui

import games
from cards import library
from collection.collection import LANGS
from system.i18n import tr
from ui.searchbox import RANGES, TEXT_FIELD_LABELS, CheckSection, ColorSection, CountSection, ListSection, \
    OptionSection, RangeSection, SetSection, TextSection

COLOR_HEX = {"W": "#f4ecc8", "U": "#4a90d9", "B": "#8c7f86", "R": "#e0553d", "G": "#3f9b5a", "C": "#b6b6b6",
             "M": "#d7b46a"}


class AdvBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, bar, parent=None):
        super().__init__(parent)
        self.ctrl, self.bar = ctrl, bar
        self._prev = {}
        self._last_click = None  # (target, time) – detect double clicks even if QML has rebuilt the checkboxes
        self._t = QtCore.QTimer(self, singleShot=True, interval=0, timeout=self.changed.emit)
        for sec in bar.sections:
            sec.changed.connect(self.soon)
        bar.changed.connect(self.soon)
        bar.adv_btn.toggled.connect(lambda _: self.soon())
        for name in ("lang_filter",):
            w = getattr(bar, name, None)
            if w is not None:
                w.changed.connect(self.soon)
        for name in ("foil_only", "own_lang", "missing", "mark_owned", "alt_only", "ident"):
            w = getattr(bar, name, None)
            if w is not None:
                w.toggled.connect(lambda _: self.soon())

    def soon(self):
        if not self._t.isActive():
            self._t.start()

    # ---------- State ----------
    @QtCore.Property(bool, notify=changed)
    def open(self):
        return self.bar.adv_btn.isChecked()

    @QtCore.Slot(bool)
    def setOpen(self, on):
        if on:
            self.bar.prepare()
        self.bar.adv_btn.setChecked(on)
        self.soon()

    @QtCore.Property(int, notify=changed)
    def panelHeight(self):
        return int(self.bar.adv_height())

    @QtCore.Slot(int)
    def setPanelHeight(self, h):
        self.ctrl.settings[f"adv_h_{self.bar.kind}"] = int(h)
        self.ctrl.settings_changed()
        self.soon()

    @QtCore.Property(str, notify=changed)
    def buttonText(self):
        t = self.bar.adv_btn.text()
        return t.replace("  ▴", "").replace("  ▾", "")

    @QtCore.Property("QVariantList", notify=changed)
    def sections(self):
        bar = self.bar
        out = []
        hidden = bar.hidden
        for key in bar.order:
            if key in hidden:   # section doesn't exist in this game (Pokémon: subtype)
                continue
            sec = bar.sec_by_key[key]
            d = {"key": key, "toggle": bool(sec.toggle), "active": bool(sec.active), "checked": sec.check.isChecked(),
                 "title": sec.check.text(), "stretch": bar.stretch(key), "enabled": sec.isEnabled()}
            if isinstance(sec, SetSection):
                d.update(kind="sets", codes=[c.upper() for c in sec.codes], mode=sec.mode.currentData() or "or",
                         modeEnabled=len(sec.codes) > 1)
            elif isinstance(sec, ColorSection):
                d.update(kind="colors", selected=sec.colors(), mode=sec.mode.currentData() or "any",
                         specials=bool(games.current().color_specials),   # Magic: C/M buttons (explained below)
                         hint=tr(games.current().color_hint),
                         colors=[{"code": c, "hex": games.current().color_hex.get(c, "#b6b6b6"), "tip": b.toolTip()}
                                 for c, b in sec.btns.items()])
            elif isinstance(sec, OptionSection):
                d.update(kind="opts", **self._opts())
            elif isinstance(sec, CheckSection):
                d.update(kind="tri", binary=bool(getattr(sec, "default_off", None) is not None),
                         items=[{"value": v, "label": label, "state": cb.state} for v, (cb, label) in sec.boxes.items()],
                         columns=max(1, sec.columns), mode=(sec.mode.currentData() if sec.mode is not None else ""))
            elif isinstance(sec, ListSection):
                d.update(kind="list", tags=[{"name": n, "state": s} for n, s in sec.states.items()],
                         mode=sec.mode.currentData() or "any", placeholder=sec.placeholder)
            elif isinstance(sec, RangeSection):
                d.update(kind="range", rows=[{"key": k, "label": tr(label), "dec": dec,
                                              "lo": sec.spins[k][0].value(), "hi": sec.spins[k][1].value()}
                                             for k, label, dec in RANGES])
            elif isinstance(sec, CountSection):
                d.update(kind="count", n=sec.slider.value, mode=sec.mode.currentData() or "min",
                         labels=list(sec.LABELS))
            elif isinstance(sec, TextSection):
                labels = dict(TEXT_FIELD_LABELS)
                d.update(kind="text", fields=[{"key": k, "text": tr(lab)} for k, lab in TEXT_FIELD_LABELS],
                         texts=[{"label": (tr("without ") if neg else "") + tr(labels[f]) + ": „" + t + "“"}
                                for f, t, neg in sec.texts])
            out.append(d)
        return out

    def _opts(self):
        bar = self.bar
        out = {"library": bar.kind == "library"}
        lf = getattr(bar, "lang_filter", None)
        if lf is not None:
            names = {c: n for c, _, n in LANGS}
            out["langsVisible"] = not lf.isHidden()
            out["langs"] = [{"code": c, "short": b.text(), "name": names.get(c, c), "sel": b.isChecked(),
                             "present": b.property("present") != "false"} for c, b in self._lang_order(lf)]
            out["langMode"] = lf.mode()
            fo = bar.foil_only
            out["foilVisible"] = not fo.isHidden()
            out["foil"] = fo.mode
            out["checks"] = [{"name": n, "text": getattr(bar, n).text(), "on": getattr(bar, n).isChecked(),
                              "tip": getattr(bar, n).toolTip()}
                             for n in ("own_lang", "missing", "mark_owned", "alt_only") if not getattr(bar, n).isHidden()]
        else:
            out["checks"] = [{"name": "ident", "text": bar.ident.text(), "on": bar.ident.isChecked(),
                              "tip": bar.ident.toolTip()}]
        return out

    @staticmethod
    def _lang_order(lf):
        return [(c, lf.btns[c]) for c in lf.order]

    # ---------- Inputs ----------
    def _sec(self, key):
        return self.bar.sec_by_key.get(key)

    @QtCore.Slot(str, bool)
    def toggleSection(self, key, on):
        self._sec(key).check.setChecked(on)

    @QtCore.Slot(str)
    def resetSection(self, key):
        self._sec(key).reset()

    @QtCore.Slot(str, str)
    def setMode(self, key, mode):
        sec = self._sec(key)
        combo = getattr(sec, "mode", None)
        if combo is not None:
            i = combo.findData(mode)
            if i >= 0:
                combo.setCurrentIndex(i)

    def _double(self, target):
        """Second click on the same target within the double-click time? (QML rebuilds the sections after every
        click – its own double-click counter then starts at 1 again.)"""
        now = time.monotonic()
        last, self._last_click = self._last_click, (target, now)
        limit = QtGui.QGuiApplication.styleHints().mouseDoubleClickInterval() / 1000
        if last is not None and last[0] == target and now - last[1] <= limit:
            self._last_click = None
            return True
        return False

    # Tri-state checkboxes
    @QtCore.Slot(str, str)
    def triClick(self, key, value):
        if self._double(("tri", key, value)):  # double click: only this one / again: all except this one
            self.triSolo(key, value)
            return
        sec = self._sec(key)
        cb = sec.boxes[value][0]
        self._prev[(key, value)] = cb.state
        cb.prev = cb.state
        cb.click()

    @QtCore.Slot(str, str)
    def triSolo(self, key, value):
        self._last_click = None
        sec = self._sec(key)
        cb = sec.boxes[value][0]
        cb.prev = self._prev.get((key, value), cb.state)
        sec.solo(value, cycle=True)

    # Colors
    @QtCore.Slot(str)
    def colorClick(self, code):
        if code in games.current().palette and self._double(("color", code)):  # double click: only this / again: all but this
            self.colorSolo(code)
            return
        sec = self.bar.sec_colors
        self._prev["colors"] = (sec.colors(), sec.mode.currentData())
        sec.btns[code].toggle()

    @QtCore.Slot(str)
    def colorSolo(self, code):
        self._last_click = None
        sec = self.bar.sec_colors
        if self._prev.get("colors") == (code, "exact"):
            sec.set_colors("".join(c for c in games.current().palette if c != code), "atmost")
        else:
            sec.set_colors(code, "exact")

    # Sets
    @QtCore.Slot(str, result="QVariantList")
    def setSuggest(self, text):
        sec = self.bar.sec_sets
        if not text.strip():
            return []
        done = set(sec.codes)
        out = []
        for root, fam in library.set_families(sec.sets() or [], text):
            missing = [m["code"] for m in fam if m["code"] not in done]
            if len(fam) > 1 and missing:
                out.append({"label": f"{root['name']} – {tr("Complete bundle")}", "codes": missing, "family": True,
                            "child": False, "done": False, "info": ""})
            for m in fam:
                yr = (m.get("released") or "")[:4]
                out.append({"label": f"{m['code'].upper()} {m['name']}", "codes": [m["code"]], "family": False,
                            "child": len(fam) > 1, "done": m["code"] in done,
                            "info": " · ".join(x for x in (m.get("type") or "", yr) if x)})
            if len(out) > 40:
                break
        return out

    @QtCore.Slot("QVariantList")
    def setAdd(self, codes):
        self.bar.sec_sets.add_codes([str(c) for c in codes])

    @QtCore.Slot(str)
    def setRemove(self, code):
        self.bar.sec_sets.set_set(code.lower(), False)

    @QtCore.Slot(str)
    def setEnter(self, text):
        sug = self.setSuggest(text)
        codes = sug[0]["codes"] if sug else ([text.strip().lower()] if text.strip() and " " not in text.strip()
                                             and len(text.strip()) <= 6 else [])
        if codes:
            self.setAdd(codes)

    # Lists (subtype, keywords)
    @QtCore.Slot(str, str, result="QVariantList")
    def listSuggest(self, key, text):
        sec = self._sec(key)
        q = text.strip().lstrip("-").strip().lower()
        if not q:
            return []
        hits = [(n, c) for n, c in sec.vocab if q in n.lower()]
        hits.sort(key=lambda t: (not t[0].lower().startswith(q), -t[1]))
        return [{"name": n, "count": f"{c:,}".replace(",", ".")} for n, c in hits[:12]]

    @QtCore.Slot(str, str, bool)
    def listAdd(self, key, name, neg):
        self._sec(key).set_value(name, 2 if neg else 1)

    @QtCore.Slot(str, str)
    def listEnter(self, key, text):
        sec = self._sec(key)
        neg = text.strip().startswith("-")
        sug = self.listSuggest(key, text)
        if sug:
            sec.set_value(sug[0]["name"], 2 if neg else 1)

    @QtCore.Slot(str, str)
    def listToggle(self, key, name):
        sec = self._sec(key)
        sec.set_value(name, 2 if sec.states.get(name) == 1 else 1)

    @QtCore.Slot(str, str)
    def listRemove(self, key, name):
        self._sec(key).set_value(name, 0)

    # Values
    @QtCore.Slot(str, int, float)
    def rangeSet(self, key, idx, value):
        sp = self.bar.sec_range.spins[key][idx]
        sp.setValue(value if value >= 0 else -1)

    # Ownership
    @QtCore.Slot(int)
    def countSet(self, n):
        self.bar.sec_count.slider.set_value(int(n))

    # Text
    @QtCore.Slot(str, str, bool)
    def textAdd(self, field, text, neg):
        text = text.strip().strip('"„“')
        if text:
            self.bar.sec_text.add(field, text, neg)

    # Display options
    @QtCore.Slot(str)
    def langToggle(self, code):
        lf = self.bar.lang_filter
        lf.btns[code].toggle()

    @QtCore.Slot(str)
    def setLangMode(self, mode):
        self.bar.lang_filter.set_mode(mode)

    @QtCore.Slot(str)
    def setFoil(self, mode):
        self.bar.foil_only.set_mode(mode)

    @QtCore.Slot(str, bool)
    def setCheck(self, name, on):
        getattr(self.bar, name).setChecked(on)

