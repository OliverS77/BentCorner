"""Set progress in Qt Quick (qml/components/CompletionPanel.qml) – data like completion.CompletionPanel."""

from PySide6 import QtCore

from cards import completion
from system.i18n import tr


class CompletionBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, lib, parent=None):
        super().__init__(parent)
        self.ctrl, self.lib = ctrl, lib
        self._rows, self._node, self._open_fams = [], None, set()

    # ---------- Data ----------
    def _sort_state(self):
        st = self.ctrl.settings.get("completion_sort")
        if isinstance(st, list) and len(st) == 2:
            return int(st[0]), bool(st[1])
        return 1, False

    @QtCore.Slot()
    def fill(self):
        mode = self.ctrl.settings.get("completion_mode") or "booster"
        data = completion.compute(self.ctrl.collection.items, mode)
        fams = completion.families(data, getattr(self.ctrl, "catalog_sets", None) or [])
        col, asc = self._sort_state()
        key = {0: lambda s: (s["name"] or "").lower(), 1: lambda s: s["have"] / max(1, s["total"]),
               2: lambda s: s["have"], 3: lambda s: s["missing_value"]}.get(col, lambda s: s["have"] / max(1, s["total"]))
        fams.sort(key=key, reverse=not asc)
        for f in fams:
            f["sets"].sort(key=key, reverse=not asc)
        self._fams = fams
        self._build()
        if self._node is None and fams:
            self._node = fams[0] if len(fams[0]["sets"]) > 1 else fams[0]["sets"][0]
        self.changed.emit()

    def _build(self):
        rows = []

        def row(node, label, level, fam_code=None):
            done = node["have"] >= node["total"]
            rows.append({"id": (fam_code or "") + "/" + node["code"], "label": label + ("  ✓" if done else ""),
                         "level": level, "have": node["have"], "total": node["total"],
                         "pct": round(node["have"] / max(1, node["total"]) * 100), "done": done,
                         "missing": completion.eur(node["missing_value"]) if node["missing_value"] else "–",
                         "expandable": fam_code is None and "sets" in node and len(node["sets"]) > 1,
                         "expanded": node["code"] in self._open_fams})
        for f in getattr(self, "_fams", []):
            if len(f["sets"]) == 1:
                s = f["sets"][0]
                row(s, f"{s['name']} ({s['code'].upper()})", 0)
                continue
            codes = ", ".join(s["code"].upper() for s in f["sets"])
            row(f, f"{f['name']} ({codes})", 0)
            if f["code"] in self._open_fams:
                for s in f["sets"]:
                    row(s, f"{s['name']} ({s['code'].upper()})", 1, f["code"])
        self._rows = rows

    def _find(self, rid):
        fam_code, _, code = rid.partition("/")
        for f in getattr(self, "_fams", []):
            if fam_code:
                if f["code"] == fam_code:
                    return next((s for s in f["sets"] if s["code"] == code), None)
            elif f["code"] == code:
                return f if len(f["sets"]) > 1 else f["sets"][0]
            elif len(f["sets"]) == 1 and f["sets"][0]["code"] == code:
                return f["sets"][0]
        return None

    @QtCore.Property("QVariantList", notify=changed)
    def rows(self):
        return self._rows

    @QtCore.Property(str, notify=changed)
    def mode(self):
        return self.ctrl.settings.get("completion_mode") or "booster"

    @QtCore.Property("QVariantList", constant=True)
    def modes(self):
        return [{"key": k, "text": tr(t)} for k, t in completion.MODES]

    @QtCore.Slot(str)
    def setMode(self, m):
        self.ctrl.settings["completion_mode"] = m
        self.ctrl.settings_changed()
        self.fill()

    @QtCore.Property(int, notify=changed)
    def sortCol(self):
        return self._sort_state()[0]

    @QtCore.Property(bool, notify=changed)
    def sortAsc(self):
        return self._sort_state()[1]

    @QtCore.Slot(int)
    def sortBy(self, col):
        cur, asc = self._sort_state()
        asc = (not asc) if col == cur else (col == 0)
        self.ctrl.settings["completion_sort"] = [col, asc]
        self.ctrl.settings_changed()
        self.fill()

    @QtCore.Slot(str)
    def toggle(self, rid):
        code = rid.partition("/")[2]
        self._open_fams.symmetric_difference_update({code})
        self._build()
        self.changed.emit()

    @QtCore.Slot(str)
    def select(self, rid):
        self._node = self._find(rid)
        self.changed.emit()

    @QtCore.Property(str, notify=changed)
    def selected(self):
        n = self._node
        return "" if n is None else n["code"]

    @QtCore.Property(str, notify=changed)
    def nodeTitle(self):
        n = self._node
        if n is None:
            return ""
        return (f"<b style='font-size:14px'>{n['name']}</b><br><span style='color:#8e8e8e'>"
                + tr(f"{len(n['missing'])} cards missing · {completion.eur(n['missing_value'])}") + " "
                + tr(f"(complete set: {completion.eur(n.get('total_value') or 0)})") + "</span>")

    @QtCore.Property("QVariantList", notify=changed)
    def missing(self):
        n = self._node
        if n is None:
            return []
        multi = "sets" in n
        out = []
        for m in n["missing"][:3000]:
            price = m["eur"] if m["eur"] is not None else m["eur_foil"]
            tag = f"{m['_set'].upper()} " if multi else ""
            out.append(f"{tag}#{m['number']}  {m['name']}" + (f"  ·  {completion.eur(price)}" if price else ""))
        return out or [tr("Complete! 🎉")]

    @QtCore.Property(int, notify=changed)
    def missingCount(self):
        n = self._node
        return 0 if n is None else len({m["name"] for m in n["missing"]})

    # ---------- Actions ----------
    @QtCore.Slot()
    def showInLibrary(self):
        if self._node is not None:
            self.lib.show_set(self._node["code"])

    def listTargets(self):
        """Menu "Missing → list": wishlists and own lists, plus "New own list …"."""
        from collection import trade
        out = []
        for kind, head in (("wish", tr("Wishlists")), ("custom", tr("Own lists"))):
            lst = trade.lists(kind)
            if not lst:
                continue
            out.append({"text": head, "enabled": False})
            for x in lst:
                main = x["id"] in (trade.MAIN_WISH, trade.MAIN_HAVE)
                out.append({"text": tr(x["name"]) if main else x["name"], "key": f"{kind}:{x['id']}", "indent": True})
        out += [{"sep": True}, {"text": tr("New own list …"), "key": "new"}]
        return out

    @QtCore.Slot(result="QVariantList")
    def missingTargets(self):
        return self.listTargets()

    @QtCore.Slot(str)
    def missingTo(self, key):
        """Missing cards of the selected set onto a list (exactly these printings)."""
        from collection import trade
        n = self._node
        if not n or not n["missing"]:
            return
        if key == "new":
            from ui import qdialogs
            name = qdialogs.get_text(tr("New list"), tr("Name of the list:"), tr(f"Missing from {n.get('name') or ''}").strip())
            if not name or not name.strip():
                return
            kind, lid = "custom", trade.add_list("custom", name.strip())
        else:
            kind, lid = key.split(":", 1)
        entries = [{"name": m["name"], "set": (m.get("_set") or n["code"] or "").lower() or None, "number": m["number"],
                    "count": 1, "lang": "en", "foil": False, "uid": None} for m in n["missing"]]
        have = {(w["name"], (w.get("set") or "").lower(), str(w.get("number") or "")) for w in trade.wishes([lid])}
        entries = [e for e in entries if (e["name"], e["set"] or "", str(e["number"] or "")) not in have]
        trade.put_entries(kind, lid, entries, self.ctrl.collection)
        name = next((x["name"] for x in trade.lists(kind) if x["id"] == lid), "")
        shell = getattr(self.ctrl, "shell", None)
        if shell is not None:
            shell.show_toast(tr(f"{len(entries)} cards → “{tr(name)}”"))
        page = getattr(self.ctrl, "trade_page", None)
        if page is not None:
            page.fill_wishes()
            page.lists_changed.emit()
        lb = shell.backends.get("library") if shell is not None else None
        if lb is not None:
            lb.changed.emit()

