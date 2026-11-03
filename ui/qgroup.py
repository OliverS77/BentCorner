"""Group by in the Library (Oliver, 29.10.): the button between "Advanced search" and the sorting opens a strip in
place (no pop-up) – the chain of properties, the saved groupings and the tree. Logic: ui/grouping.py; the grid's filter
sits in LibraryCore.mine_rows (group_chain / group_path).

Smooth with big collections (1887+ Magic cards): the tree is counted at most every 250 ms (not on every key press of
the search), from the rows the library has built anyway – while the strip is open or something is grouped (the
chips in the chip row show the numbers even with the strip closed).
"All cards" (Oliver, after 0.9.2): the card database isn't loaded for it – every level is one GROUP BY in SQL, counted
in the background (a newer count makes an older one void); the grid stays page by page with the branch as an SQL
condition (LibraryCore.db_rows).
Chips and switch (Oliver, 30.10.): the full chain stays here – levels can be switched off (grey: they stay in the
path but don't filter) and the whole grouping can be off (the normal list, the path kept). The library only gets the
levels that work (lib.group_chain / group_path); the tree shows those levels.
Remembered per game: the last grouping with its branch (settings "group_last") and the saved ones ("group_saved").
"""
from PySide6 import QtCore

import games
from system.i18n import tr
from ui import grouping

SAVED_CHIPS = 5   # saved groupings shown as chips at the top – the rest in the strip


class GroupBackend(QtCore.QObject):
    changed = QtCore.Signal()
    treeChanged = QtCore.Signal()
    jumped = QtCore.Signal(int)   # a node was picked (level) – QML zooms into it

    def __init__(self, ctrl, lib, host):
        super().__init__(host)
        self.ctrl, self.lib, self.host = ctrl, lib, host
        self._open = False
        self._tree = {"root": {"cards": 0, "value": 0}, "cols": [], "next": [], "path": [], "here": {"cards": 0, "value": 0}}
        self._more = set()
        self._game = None
        self._gen = 0   # number of the newest count ("All cards": results of older ones are dropped)
        # the full grouping: chain of keys, the picked branch per level (None = none), levels switched off, all off
        self._chain, self._path, self._disabled, self._off = [], [], set(), False
        self._idx = []   # full index of each level the library gets (= each column of the tree)
        self._labels = {}   # (key, value) -> label of the branch (from the tree; for levels switched off)
        self._t = QtCore.QTimer(self, singleShot=True, interval=250, timeout=self._count)
        lib.model.reset.connect(self._later)
        host.changed.connect(self.changed)   # (mode, sorting: "enabled", the button)
        self._load()

    # ---------- remembered per game ----------
    def _gk(self):
        return games.current().key

    def _load(self):
        self._game = self._gk()
        last = (self.ctrl.settings.get("group_last") or {}).get(self._game) or {}
        valid = {k for k, _ in grouping.keys()}
        chain = list(last.get("chain") or [])
        path = list(last.get("path") or [])
        keep = [i for i, k in enumerate(chain) if k in valid]
        self._chain = [chain[i] for i in keep]
        self._path = [path[i] if i < len(path) else None for i in keep]
        self._disabled = {k for k in last.get("disabled") or [] if k in self._chain}
        self._off = bool(last.get("off"))
        self._push()

    def _store(self):
        last = dict(self.ctrl.settings.get("group_last") or {})
        last[self._gk()] = {"chain": list(self._chain), "path": list(self._path), "disabled": sorted(self._disabled),
                            "off": self._off}
        self.ctrl.settings["group_last"] = last
        self.ctrl.settings_changed()

    def _push(self):
        """The levels that work -> the library (lib.group_chain / group_path) and their full indexes (self._idx)."""
        while self._path and self._path[-1] is None:
            self._path.pop()
        self._path += [None] * (len(self._chain) - len(self._path))
        if self._off:
            self._idx = []
        else:
            self._idx = [i for i, k in enumerate(self._chain) if k not in self._disabled]
        chain = [self._chain[i] for i in self._idx]
        path = []
        for i in self._idx:
            if self._path[i] is None:
                break
            path.append(self._path[i])
        self.lib.group_chain, self.lib.group_path = chain, path

    def _apply(self, store=True):
        self._push()
        self.lib.refresh()
        self._count()
        # what the tree really kept – in "All cards" the count comes later and does this itself (_count_sql)
        if not self._all() and self._chain and self._take_tree_path(self._tree["path"]):
            self._push()
            self.lib.refresh()
            self._count()
        if store:
            self._store()
        self.changed.emit()
        self.host.changed.emit()

    def _take_tree_path(self, tpath):
        """What the tree really kept (a branch that doesn't exist under the new node is dropped) -> the full path."""
        changed = False
        for j, fi in enumerate(self._idx):   # (everything after the first gap is no longer picked either)
            v = tpath[j] if j < len(tpath) else None
            if self._path[fi] != v:
                self._path[fi], changed = v, True
        return changed

    # ---------- counting (debounced) ----------
    def _later(self):
        if self._gk() != self._game:   # another game: its own grouping
            self._load()
            self.changed.emit()
        if self._open or self._chain:
            self._t.start()

    def _all(self):
        return self.lib.mode == "all"

    def _keys(self):
        return grouping.keys(all_cards=self._all())

    def _count(self):
        self._t.stop()
        if not (self._open or self._chain) or self.lib.mode not in ("mine", "all"):
            return
        by = {"count": "count", "price": "value"}.get(self.lib.sort.currentData(), "natural")
        if self._all():
            self._count_sql(by)
            return
        self._show(grouping.tree(list(self.lib.group_base), self.lib.group_chain, self.lib.group_path, self._more, by))

    def _count_sql(self, by):
        from cards import carddb
        from ui.librarycore import run_async
        if not carddb.exists():
            return
        text, f = self.lib.db_query()
        chain, path, more = list(self.lib.group_chain), list(self.lib.group_path), set(self._more)
        self._gen += 1
        gen = self._gen

        def with_where(w):
            return dict(f, where_sql=list(f.get("where_sql") or []) + list(w))

        def work():
            return grouping.tree_sql(lambda e, a, w: carddb.group_counts(text, e, a, **with_where(w)),
                                     lambda exprs, w: carddb.distinct_counts(text, exprs, **with_where(w)),
                                     chain, path, more, by)

        def done(t, err):
            if gen != self._gen or not self._all():
                return   # a newer count is on its way (or the mode changed)
            if err is not None or t is None:
                return
            self._show(t)
            n = len(t["path"])
            if t["path"] != self.lib.group_path[:n] or (len(self.lib.group_path) > n and len(t["cols"]) > n):
                if self._take_tree_path(t["path"]):   # a branch that doesn't exist (any more) under the new node
                    self._push()
                    self._store()
                    self.lib.refresh()
                    self.changed.emit()
        run_async(self, work, done)

    def _show(self, t):
        for d, c in enumerate(t["cols"]):
            for n in c["nodes"]:
                n["valueText"] = _euro(n["value"])
                if n["on"]:
                    self._labels[(c["key"], n["v"])] = n["label"]
        t["root"]["valueText"] = _euro(t["root"]["value"])
        t["here"]["valueText"] = _euro(t["here"]["value"])
        self._tree = t
        self.treeChanged.emit()
        self.changed.emit()   # (the chips show the numbers of the tree)

    # ---------- for QML ----------
    @QtCore.Property(bool, notify=changed)
    def open(self):
        return self._open

    @QtCore.Property(bool, notify=changed)
    def enabled(self):
        return self.lib.mode in ("mine", "all")

    @QtCore.Property(bool, notify=changed)
    def active(self):
        """Something is grouped (a chain) – also while it is off."""
        return bool(self._chain)

    @QtCore.Property(bool, notify=changed)
    def on(self):
        return not self._off

    @QtCore.Property(str, notify=changed)
    def buttonText(self):
        """Always just "Group by" (Oliver, 30.10.: the path is in the chips, not in the button)."""
        return tr("Group by")

    @QtCore.Property("QVariantList", notify=changed)
    def chain(self):
        return [{"key": k, "label": grouping.label_of_key(k)} for k in self._chain]

    def _level(self, i):
        """Level i of the full chain: its property, the picked branch with its number, and whether it works."""
        k, v = self._chain[i], self._path[i] if i < len(self._path) else None
        col = self._idx.index(i) if i in self._idx else -1
        cards = None
        if col >= 0 and col < len(self._tree["cols"]):
            node = next((n for n in self._tree["cols"][col]["nodes"] if n["v"] == v), None)
            cards = node["cards"] if node else None
        level = grouping.label_of_key(k)
        label = self._labels.get((k, v), str(v) if v is not None else level)
        if v is not None and label.replace(".", "").replace("+", "").isdigit():
            label = f"{level} {label}"   # a bare number says nothing: "Mana value 3" (Oliver's example)
        return {"i": i, "key": k, "level": level, "picked": v is not None, "label": label,
                "cards": "" if cards is None else str(cards), "col": col,
                "grey": self._off or k in self._disabled, "disabled": k in self._disabled}

    @QtCore.Property("QVariantList", notify=changed)
    def levels(self):
        """Every level of the chain (breadcrumbs above the tree's columns)."""
        return [self._level(i) for i in range(len(self._chain))]

    @QtCore.Property("QVariantList", notify=changed)
    def chips(self):
        """The chips in the chip row: the picked levels (Enchantments 48 · Common 21 · Mana value 3 7) – as soon as the
        grouping filters something, also while the strip is closed; grey = switched off (or the whole grouping off)."""
        if not self.enabled:
            return []
        return [lv for lv in (self._level(i) for i in range(len(self._chain))) if lv["picked"]]

    @QtCore.Property("QVariant", notify=treeChanged)
    def tree(self):
        return self._tree

    @QtCore.Property("QVariantList", notify=changed)
    def keys(self):
        used = set(self._chain)
        return [{"key": k, "label": n, "used": k in used} for k, n in self._keys()]

    @QtCore.Property("QVariantList", notify=changed)
    def saved(self):
        """Saved groupings of this game: [{name, chain, on, chip}] – the first five are chips at the top."""
        mine = (self.ctrl.settings.get("group_saved") or {}).get(self._gk()) or []
        return [{"name": s.get("name") or "", "on": list(s.get("chain") or []) == self._chain,
                 "chip": i < SAVED_CHIPS} for i, s in enumerate(mine)]

    @QtCore.Property(bool, notify=changed)
    def isSaved(self):
        mine = (self.ctrl.settings.get("group_saved") or {}).get(self._gk()) or []
        return any(list(s.get("chain") or []) == self._chain for s in mine)

    @QtCore.Slot(bool)
    def setOpen(self, on):
        self._open = bool(on)
        self.changed.emit()
        if on:
            self._count()

    @QtCore.Slot(bool)
    def setOn(self, on):
        """The switch next to "Ungroup": off = the normal list, the path stays (all chips grey)."""
        if self._off == (not on):
            return
        self._off = not on
        self._apply()

    @QtCore.Slot(str)
    def addLevel(self, key):
        """"Branch on by …" / a property in the chain row: a new level at the end – its branches grow in."""
        if key in self._chain or key not in dict(self._keys()):
            return
        self._chain.append(key)
        self._path.append(None)
        self._off = False
        self._apply()

    @QtCore.Slot(int)
    def removeLevel(self, i):
        """× on a level: only this level goes (Enchantments › Common › Mana value 3 -> Enchantments › Mana value 3)."""
        if 0 <= i < len(self._chain):
            self._disabled.discard(self._chain[i])
            del self._chain[i]
            if i < len(self._path):
                del self._path[i]
            self._more = set()
            if not self._chain:
                self._off = False
            self._apply()

    @QtCore.Slot(int)
    def toggleLevel(self, i):
        """Switch a level off (grey: it stays in the path, but doesn't filter) – or on again."""
        if 0 <= i < len(self._chain):
            k = self._chain[i]
            (self._disabled.discard if k in self._disabled else self._disabled.add)(k)
            self._more = set()
            self._apply()

    @QtCore.Slot(int)
    def toLevel(self, i):
        """Click on a chip: back to this level (the levels after it are no longer picked)."""
        if 0 <= i < len(self._chain):
            self._path = self._path[:i + 1] + [None] * (len(self._chain) - i - 1)
            self._apply()
            self.jumped.emit(self._idx.index(i) if i in self._idx else -1)

    @QtCore.Slot(int, str)
    def pick(self, depth, v):
        """Click on a node (depth = column of the tree): its cards in the grid. A lit node (on the path) goes back
        there; a dimmed one jumps across – deeper levels stay where the new branch has them (the tree checks that)."""
        if not 0 <= depth < len(self._idx):
            return
        fi = self._idx[depth]
        if self._path[fi] == v:
            for j in self._idx[depth + 1:]:   # lit: back to this node
                self._path[j] = None
        else:
            self._path[fi] = v
        self._apply()
        self.jumped.emit(depth)

    @QtCore.Slot()
    def toRoot(self):
        """The root ("All N cards"): the whole collection again, the chain stays."""
        self._path = [None] * len(self._chain)
        self._apply()
        self.jumped.emit(-1)

    @QtCore.Slot(int)
    def showAll(self, depth):
        """"+ n more" ↔ "− show fewer" on a level."""
        (self._more.discard if depth in self._more else self._more.add)(depth)
        self._count()

    @QtCore.Slot()
    def clear(self):
        """Ungroup: the library as before (the real reset – the switch only pauses)."""
        self._chain, self._path, self._disabled, self._off, self._more = [], [], set(), False, set()
        self._apply()

    @QtCore.Slot()
    def toggleSave(self):
        """☆ Save this grouping (named after its chain) – or forget it again."""
        if not self._chain:
            return
        allg = dict(self.ctrl.settings.get("group_saved") or {})
        mine = list(allg.get(self._gk()) or [])
        hit = [s for s in mine if list(s.get("chain") or []) == self._chain]
        if hit:
            mine = [s for s in mine if s not in hit]
        else:
            mine.append({"name": " › ".join(grouping.label_of_key(k) for k in self._chain),
                         "chain": list(self._chain)})
        allg[self._gk()] = mine
        self.ctrl.settings["group_saved"] = allg
        self.ctrl.settings_changed()
        self.changed.emit()

    @QtCore.Slot(int)
    def useSaved(self, i):
        mine = (self.ctrl.settings.get("group_saved") or {}).get(self._gk()) or []
        if 0 <= i < len(mine):
            valid = {k for k, _ in grouping.keys()}
            self._chain = [k for k in mine[i].get("chain") or [] if k in valid]
            self._path = [None] * len(self._chain)
            self._disabled, self._off, self._more = set(), False, set()
            self._apply()

    @QtCore.Slot(int)
    def forgetSaved(self, i):
        allg = dict(self.ctrl.settings.get("group_saved") or {})
        mine = list(allg.get(self._gk()) or [])
        if 0 <= i < len(mine):
            mine.pop(i)
            allg[self._gk()] = mine
            self.ctrl.settings["group_saved"] = allg
            self.ctrl.settings_changed()
            self.changed.emit()


def _euro(v):
    from ui.librarycore import eur
    return eur(v)
