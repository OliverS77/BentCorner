"""Sessions in Qt Quick (qml/pages/SessionsPage.qml).

The logic stays in the program (app.py: refresh_stats, show_session_detail, stats_apply …); the table and the pack
list live there as data (sess_rows, sess_packs). This object passes them on to QML, "Edit session" as a form from
the draft ctrl.sess_draft (qform), card detail via qdetail, "Change card" via the shared card window
(qcardsearch).
"""
from PySide6 import QtCore

from ui import qform
from ui import qstate
from system.i18n import tr
from collection import sessions
import time
from ui.qtrade import _wrap, plain_detail


class RowModel(QtCore.QAbstractListModel):
    """The log's pack/card rows for the ListView (one role, "modelData": the row's dict – the delegate stays as it
    was). QML reads only the rows on screen; a change sends just the rows that differ (one card switched to foil:
    one row), a different list a reset. Before, the whole list went to QML as one array on every change – with
    3000 cards ~1.6 s per click."""
    ROLE = QtCore.Qt.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []

    def roleNames(self):
        return {self.ROLE: b"modelData"}

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if role == self.ROLE and 0 <= index.row() < len(self._rows):
            return self._rows[index.row()]
        return None

    def set_rows(self, rows):
        old = self._rows
        if len(rows) != len(old) or any(a.get("pi") != b.get("pi") or a.get("ci") != b.get("ci")
                                        for a, b in zip(old, rows)):
            self.beginResetModel()
            self._rows = rows
            self.endResetModel()
            return
        self._rows = rows
        for i, (a, b) in enumerate(zip(old, rows)):
            if a != b:
                ix = self.index(i)
                self.dataChanged.emit(ix, ix, [self.ROLE])


class SessionsBackend(QtCore.QObject):
    changed = QtCore.Signal()       # table, selection, buttons
    detailChanged = QtCore.Signal()  # text, pack list
    panelChanged = QtCore.Signal()   # card detail / change card

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = c = ctrl
        # the trash reads every log file (sessions.hidden_all): once per change, not once per QML binding (6 times
        # per page switch, survey 0.9.3.18) – connected first, so it is dropped before QML reads anew
        self._trash = None
        self.changed.connect(self._drop_trash)
        self.form = qform.Form(self._build_form, self)
        qstate.watch(lambda: self.form.soon() if self._active else None)
        self._active = False
        plain_detail(c.sess_host)
        from ui.qdetail import DetailBackend
        self.det_b = DetailBackend(c, c.sess_host, c.sess_card, self)
        self.cmp_b = DetailBackend(c, c.sess_host, c.sess_cmp, self)
        for name in ("open_detail", "hide_detail", "show_compare", "close_compare", "update_marks"):
            _wrap(c.sess_host, name, self.panelChanged.emit)
        ed = c.sess_edit
        _wrap(ed, "open", self.panelChanged.emit)
        _wrap(ed, "close_page", self.panelChanged.emit)
        from ui.qcardsearch import CardSearchBackend
        self.card_b = CardSearchBackend(ed.panel, self)  # "Edit card" = the same window as when scanning
        # report changes in bulk (many paths lead there)
        self._soon = QtCore.QTimer(self, singleShot=True, interval=0, timeout=self._detail)
        self._rows = RowModel(self)
        self.detailChanged.connect(lambda: self._rows.set_rows(self._pack_rows()))
        c.sess_changed.connect(self._kick)
        self._tick = QtCore.QTimer(self, interval=700, timeout=self.form.refresh)

    def _kick(self, *_):
        self._soon.start()

    def _detail(self):
        self.form.refresh()
        self.detailChanged.emit()
        self.changed.emit()

    @QtCore.Slot(bool)
    def setActive(self, on):
        self._active = bool(on)
        self._tick.start() if on else self._tick.stop()
        if on:
            self.form.refresh()

    # ---------- "Edit session" ----------
    def _build_form(self, ui):
        from cards import packtypes
        c = self.ctrl
        dr = c.sess_draft
        if not dr.get("sid"):
            return ui.col([])
        if dr.get("kind") == "manual":   # nothing to edit – each line can be undone in the list below
            return ui.col([ui.label(tr("Changes by hand"), bold=True),
                           ui.note(tr("Everything you added or took out by hand on this day (not in a log). "
                                      "Each line can be undone on its own – the cards are already in your collection."))])
        types = [(t["key"], tr(t["name"])) for t in packtypes.types(c.settings)]
        if dr["mixed"]:
            types = [("_mixed", tr("mixed"))] + types

        def set_type(key):
            c.sess_set(mixed=key == "_mixed", **({} if key == "_mixed" else {"type": key}))

        def started(dt):
            c.sess_set(started=float(dt.toSecsSinceEpoch()))
        sid = dr["sid"]
        return ui.col([
            ui.label(tr("Edit log"), bold=True),
            ui.form([
                (tr("Date"), ui.datetime(QtCore.QDateTime.fromSecsSinceEpoch(int(dr["started"])), started)),
                (tr("Type"), ui.label(tr("Scan cards")) if dr.get("kind") == "cards"   # no packs, so no pack type
                 else ui.row([ui.combo(types, "_mixed" if dr["mixed"] else dr["type"], set_type,
                                       tip=tr("Pack type of all packs in this log (single packs: right-click in the list)")),
                              ui.button(tr("Types …"), c.edit_pack_types,
                                        tip=tr("Which pack types exist and which count as packs in the stats"))])),
                (tr("Title"), ui.edit(dr["title"], lambda t: c.sess_set(title=t), key=f"title{sid}",
                                      live=lambda t: c.sess_set(title=t), placeholder=tr("e.g. stream title"))),
                (tr("Einsatz"), ui.spin(dr["paid"], 0, 1_000_000, lambda v: c.sess_set(paid=v), decimals=2,
                                        suffix=" €", tip=tr("What you paid – used for the balance"))),
                (tr("Notizen"), ui.edit(dr["notes"], lambda t: c.sess_set(notes=t), key=f"notes{sid}",
                                        live=lambda t: c.sess_set(notes=t))),
                (tr("Tags"), ui.tags(dr["tags"], packtypes.all_tags(getattr(c, "stats_sessions", [])),
                                     lambda tags: c.sess_set(tags=tags))),
            ]),
            ui.button(tr("Save changes  ●") if dr["dirty"] else tr("Save changes"),
                      c.save_session_edit, active=dr["dirty"], enabled=dr["dirty"]),
        ], spacing=10)

    # ---------- table ----------
    def _visible_cols(self):
        hidden = self.ctrl.sess_hidden
        return [i for i in self._order() if i not in hidden]

    def _order(self):
        """Order of the columns – sorted in the ☰ menu above the table (review .101), new columns at the end."""
        n = len(self._labels())
        mine = [i for i in self.ctrl.settings.get("sess_order") or [] if isinstance(i, int) and 0 <= i < n]
        mine = list(dict.fromkeys(mine))
        return mine + [i for i in range(n) if i not in mine]

    def _labels(self):
        from app import SESS_COLUMNS
        return [tr(x) for x in SESS_COLUMNS]

    def _columns(self):
        """Visible columns – kept until language or hidden columns change: QML reads `columns` once per table cell."""
        from system import i18n
        everything = self.__dict__.get("_filter", "all") == "all"
        key = (i18n.LANG, tuple(sorted(self.ctrl.sess_hidden)), everything, tuple(self._order()))
        if self.__dict__.get("_cols_key") != key:
            labels = self._labels()
            # fit: as wide as the widest entry, never cut (date and the numbers); the others share the rest
            self._cols = [{"i": i, "text": labels[i], "w": self.WIDTHS[i] if i < len(self.WIDTHS) else 90,
                           "right": i >= 4, "fit": i >= 4 or i == 0} for i in self._visible_cols()]
            if everything:   # "All": which kind each log is (the switch above), right after the date
                self._cols.insert(1 if self._cols and self._cols[0]["i"] == 0 else 0,
                                  {"i": self.KIND, "text": tr("Kind"), "w": 90, "right": False, "fit": True})
            self._cols_key = key
        return self._cols

    WIDTHS = (130, 230, 150, 130, 70, 75, 90, 90, 90)  # column shares (QML distributes the width accordingly)
    KIND = -1   # the extra column "Kind" in the view "All" (not one of SESS_COLUMNS, not hideable)

    def _kind_text(self, row):
        return {"cards": tr("Cards"), "scan": tr("Booster"), "singles": tr("Trades & purchases"), "import": tr("Imports"),
                "manual": tr("By hand")}[self._cat(row)]

    @QtCore.Property("QVariantList", notify=changed)
    def columns(self):
        return self._columns()

    @QtCore.Property("QVariantList", notify=changed)
    def allColumns(self):
        hidden, req, labels = self.ctrl.sess_hidden, self.ctrl.SESS_REQUIRED, self._labels()
        return [{"i": i, "text": labels[i], "shown": i not in hidden, "fixed": i in req} for i in self._order()]

    @QtCore.Slot(int)
    def toggleColumn(self, i):
        self.ctrl.sess_set_column(i, i in self.ctrl.sess_hidden)

    @QtCore.Slot(int, int)
    def moveColumn(self, src, dst):
        """☰ menu: the column at position src (of allColumns) to position dst – the table follows at once."""
        order = self._order()
        if not (0 <= src < len(order) and 0 <= dst < len(order)) or src == dst:
            return
        order.insert(dst, order.pop(src))
        self.ctrl.settings["sess_order"] = order
        self.ctrl.settings_changed()
        self.changed.emit()

    @QtCore.Property("QVariantList", notify=changed)
    def rows(self):
        cols = [c["i"] for c in self._columns()]
        sel = self.ctrl.sess_sel
        f = self.__dict__.get("_filter", "all")
        return [{"r": r, "cells": [row["cells"][c] if c != self.KIND else {"text": self._kind_text(row), "color": "", "tip": ""}
                                   for c in cols], "sel": row["sid"] == sel, "imp": row.get("imp", False)}
                for r, row in enumerate(self.ctrl.sess_rows) if f == "all" or self._cat(row) == f]

    @staticmethod
    def _cat(row):
        if row.get("kind") == "manual":
            return "manual"
        if row.get("imp"):
            return "import"
        if row.get("singles"):
            return "singles"
        return "cards" if row.get("kind") == "cards" else "scan"

    # ---------- filter: all · scan sessions · imports ----------
    @QtCore.Property("QVariantList", notify=changed)
    def filters(self):
        rows = self.ctrl.sess_rows
        n = {k: sum(1 for r in rows if self._cat(r) == k) for k in ("cards", "scan", "singles", "import", "manual")}
        return [{"key": "all", "text": tr("Alle") + f"  {len(rows)}"},
                {"key": "cards", "text": tr("Cards") + f"  {n['cards']}"},
                {"key": "scan", "text": tr("Booster") + f"  {n['scan']}"},
                {"key": "singles", "text": tr("Trades & purchases") + f"  {n['singles']}"},
                {"key": "import", "text": tr("Imports") + f"  {n['import']}"},
                {"key": "manual", "text": tr("By hand") + f"  {n['manual']}"},
                {"key": "trash", "text": tr("Trash") + f"  {len(self.trash)}", "icon": "trash"}]

    @QtCore.Property(str, notify=changed)
    def filter(self):
        return self.__dict__.get("_filter", "all")

    @QtCore.Slot(str)
    def setFilter(self, key):
        self._filter = key
        self.changed.emit()

    @QtCore.Slot()
    def importCards(self):
        """Import button: straight to Import/Export → Collection (with "back to sessions")."""
        self.ctrl.show_import("collection")

    @QtCore.Slot()
    def toList(self):
        """"As list": create the list and show it right away in the Library – "← Sessions" leads back."""
        sid = self.ctrl.selected_session_id()
        if not sid:
            return
        lid = self.ctrl.session_to_list(sid, toast=False)
        if lid:
            self.ctrl.show_list("custom", lid, back=True)
            self.ctrl.stream_toast(tr("List created from the log"))

    @QtCore.Property(str, notify=changed)
    def undoText(self):
        u = self.ctrl.sess_undo
        return u[1] if u else ""

    @QtCore.Slot()
    def undo(self):
        self.ctrl.sess_do_undo()
        self.changed.emit()
        self.detailChanged.emit()

    @QtCore.Slot()
    def dropUndo(self):
        self.ctrl.sess_undo = None
        self.changed.emit()

    @QtCore.Property("QVariantList", notify=changed)
    def trash(self):
        """Trash – everything deleted (logs, packs, cards, decks, lists, friends …), restorable for 60 days.
        Logs aren't copies here: they are hidden in place (sessions.hide – the logs are the library's source).
        It lives here as its own tab next to "Imports" (no longer in Settings)."""
        if self._trash is None:
            self._trash = self._make_trash()
        return self._trash

    def _drop_trash(self):
        self._trash = None

    def _make_trash(self):
        from system import datastore
        rows = []
        for name, e in datastore.trash_list():
            rows.append((e.get("deleted", 0), {"name": name, "kind": tr(self.ctrl.TRASH_KINDS.get(e["kind"], e["kind"])),
                                              "title": e.get("title") or ""}))
        for d in sessions.hidden_all():
            at = (d.get("hidden") or {}).get("at", 0)
            info = d.get("info") or {}
            title = self.ctrl._manual_title(d) if info.get("kind") == "manual" else \
                (info.get("title") or time.strftime("%d.%m.%Y", time.localtime(d.get("started", 0))))
            rows.append((at, {"name": "log:" + d["id"], "kind": tr("Log"), "title": title}))
        rows.sort(key=lambda r: -r[0])
        return [dict(r, when=time.strftime("%d.%m. %H:%M", time.localtime(t))) for t, r in rows]

    @QtCore.Slot(str)
    def restoreTrash(self, name):
        from system import datastore
        if name.startswith("log:"):   # a hidden log: just show it again
            self.ctrl.log_unhide(name[4:])
            self.ctrl.fill_trash()
            self.changed.emit()
            self.detailChanged.emit()
            return
        e = datastore.trash_take(name)
        if e is not None:
            self.ctrl.trash_restore(e)
        self.ctrl.fill_trash()
        self.changed.emit()
        self.detailChanged.emit()

    @QtCore.Slot()
    def emptyTrash(self):
        self.ctrl.trash_empty()
        self.ctrl.fill_trash()
        self.changed.emit()

    @QtCore.Slot(str)
    def dropTrash(self, name):
        from system import datastore
        if name.startswith("log:"):
            self.ctrl.log_for_good(name[4:])
        else:
            datastore.trash_drop(name)
        self.ctrl.fill_trash()
        self.changed.emit()

    @QtCore.Slot(int)
    def select(self, r):
        rows = self.ctrl.sess_rows
        if not 0 <= r < len(rows):
            return
        sid = rows[r]["sid"]
        self.ctrl.sess_select(sid)
        try:  # import (often hundreds of cards): show collapsed – expand with a click
            if sid != self.ctrl.session.id and sessions.is_import(sessions.load(sid)):
                for pk in self.ctrl.sess_packs:
                    self.ctrl.sess_open.setdefault(pk["pi"], False)
                self.detailChanged.emit()
        except (OSError, ValueError):
            pass
        self.changed.emit()

    @QtCore.Property(bool, notify=changed)
    def hasSelection(self):
        return bool(self.ctrl.selected_session_id())

    @QtCore.Property(bool, notify=changed)
    def selectedRunning(self):
        """The running session is selected (delete only after ending it)."""
        return self.ctrl.selected_session_id() == self.ctrl.session.id

    @QtCore.Property(bool, notify=changed)
    def empty(self):
        return not self.ctrl.sess_rows

    # ---------- buttons ----------
    @QtCore.Slot()
    def newSession(self):
        self.ctrl.session_button()
        self.ctrl.refresh_stats()
        self.changed.emit()

    @QtCore.Property(bool, notify=changed)
    def sessionActive(self):
        return bool(self.ctrl.session.active)

    @QtCore.Slot()
    def toDeck(self):
        self.ctrl.session_to_deck()

    @QtCore.Property(str, notify=changed)
    def libText(self):
        return self.ctrl.sess_lib["text"]

    @QtCore.Property(str, notify=changed)
    def libTip(self):
        return self.ctrl.sess_lib["tip"]

    @QtCore.Property(bool, notify=changed)
    def libEnabled(self):
        return self.ctrl.sess_lib["enabled"]

    @QtCore.Property(bool, notify=changed)
    def libOn(self):
        """The log's cards are in the library – shown as a switch "in the library" (review .101)."""
        return bool(self.ctrl.sess_lib.get("on"))

    @QtCore.Slot()
    def toggleLibrary(self):
        self.ctrl.sess_toggle_library()
        self.changed.emit()

    @QtCore.Slot()
    def deleteSession(self):
        self.ctrl.stats_delete_session()

    @QtCore.Slot()
    def share(self):
        self.ctrl.share_session()

    @QtCore.Slot()
    def scan(self):
        self.ctrl.stream.show_page("scan")

    # ---------- edit + overview ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def editForm(self):
        return self.form

    @QtCore.Property(str, notify=detailChanged)
    def summary(self):
        return self.ctrl.sess_summary

    # ---------- pack list ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def packs(self):
        return self._rows

    def _pack_rows(self):
        out = []
        opened = self.ctrl.sess_open
        for pk in self.ctrl.sess_packs:
            pi, is_open = pk["pi"], opened.get(pk["pi"], True)
            out.append({"pi": pi, "ci": -1, "pack": True, "name": pk["name"], "type": pk["type"],
                        "typeColor": pk["typeColor"], "set": "", "price": pk["price"], "open": is_open,
                        "plain": bool(pk.get("plain"))})   # scanning cards: no pack type, no pack buttons
            if not is_open:
                continue
            # every card: the list (SessionsPage, a ListView) builds only the rows on screen, so a pack of thousands
            # costs no more to show than a small one (the old cap of 200 with "… and n more" is gone)
            for c in pk["cards"]:
                out.append({"pi": pi, "ci": c["ci"], "pack": False, "name": c["name"], "type": "", "typeColor": "",
                            "set": c["set"], "price": c["price"], "open": False, "fin": c.get("fin") or "F",
                            "note": c.get("note") or "",
                            "manual": bool(c.get("manual"))})   # by hand: only "undo" on the row
        foreign = getattr(self.ctrl, "sess_foreign", None) or []
        if foreign:   # mixed trade: what was added or removed in other games – greyed out, view only
            import games
            out.append({"pi": -1, "ci": -1, "pack": True, "foreign": True, "name": tr("From other games"),
                        "type": "", "typeColor": "", "set": "", "price": "", "open": True})
            for f in sorted(foreign, key=lambda f: str(f.get("g"))):
                arrow = "+" if f.get("dir") == "get" else "−"
                out.append({"pi": -1, "ci": -3, "pack": False, "foreign": True, "g": f.get("g") or "",
                            "tip": tr(f"Wechseln zu {games.nick_of(f.get('g'))}"),
                            "name": f"{arrow}{int(f.get('count') or 1)}  {f.get('name') or '?'}",
                            "type": "", "typeColor": "",
                            "set": f"{games.SHORT.get(f.get('g'), str(f.get('g') or '').upper())} · {f.get('set')} #{f.get('number')}"
                                   + (" · Foil" if f.get("foil") else ""),
                            "price": "", "open": False})
        return out

    @QtCore.Slot(str)
    def openForeign(self, game):
        """Greyed-out card (other game) clicked: switch there, show the session of the same ticket."""
        tid = getattr(self.ctrl, "sess_ticket", "")
        if game and tid:
            self.ctrl.show_ticket_session(game, tid)

    @staticmethod
    def _ci(ci):
        return None if ci < 0 else ci

    @QtCore.Slot(int)
    def togglePack(self, pi):
        op = self.ctrl.sess_open
        op[pi] = not op.get(pi, True)
        self.detailChanged.emit()

    @QtCore.Slot(int, int, int)
    def clickRow(self, pi, ci, col):
        """col 1 on a pack = choose type; card = detail view."""
        if ci == -2:
            return
        self.ctrl.pack_clicked(pi, self._ci(ci), col)

    @QtCore.Slot(int, int, str)
    def rowAction(self, pi, ci, action):
        if ci != -2:
            self.ctrl.sess_row_action(pi, self._ci(ci), action)

    @QtCore.Slot(int, int)
    def editCard(self, pi, ci):
        if ci >= 0:
            self.ctrl.sess_cur = (pi, ci)
            self.ctrl.stats_edit_card()

    # ---------- right: card detail / change card ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def detail(self):
        return self.det_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def compare(self):
        return self.cmp_b

    @QtCore.Property(bool, notify=panelChanged)
    def detailOpen(self):
        return not self.ctrl.sess_card.isHidden()

    @QtCore.Property(bool, notify=panelChanged)
    def compareOpen(self):
        return not self.ctrl.sess_card.isHidden() and not self.ctrl.sess_cmp.isHidden()

    @QtCore.Property(QtCore.QObject, constant=True)
    def cardSearch(self):
        return self.card_b

    @QtCore.Property(bool, notify=panelChanged)
    def editOpen(self):
        return not self.ctrl.sess_edit.isHidden()

    @QtCore.Property(int, notify=panelChanged)
    def panelWidth(self):
        return int(self.ctrl.settings.get("sess_card_w") or 560)

    @QtCore.Property(float, notify=panelChanged)
    def tableShare(self):
        """Share of the table next to the open log (the divider between them can be dragged)."""
        return float(self.ctrl.settings.get("log_table_share") or 5 / 11)

    @QtCore.Slot(float)
    def setTableShare(self, f):
        self.ctrl.settings["log_table_share"] = round(max(0.3, min(0.7, float(f))), 3)
        self.ctrl.settings_changed()
        self.panelChanged.emit()

    @QtCore.Slot(int)
    def setPanelWidth(self, w):
        self.ctrl.settings["sess_card_w"] = int(w)
        self.ctrl.settings_changed()
        self.panelChanged.emit()

    @QtCore.Slot()
    def escape(self):
        c = self.ctrl
        if not c.sess_edit.isHidden():
            c.sess_edit.close_page()
        elif not c.sess_cmp.isHidden():
            c.sess_host.close_compare()
        else:
            c.sess_close_card()
        self.panelChanged.emit()
