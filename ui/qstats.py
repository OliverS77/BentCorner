"""Stats in Qt Quick (qml/pages/StatsPage.qml): tabs Sessions · Trade · Collection, filters and the tab's content
as a form (qform) directly from the data (statsview.StatsPage) – charts native (qcharts/ChartView)."""
from PySide6 import QtCore

from ui import qcharts
from ui import qform
from system.i18n import tr


class StatsBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.sp = sp = ctrl.stats_page
        self._open, self._active = False, False
        # one form per tab, made on its first visit and then kept (QML keeps the built tab too, only hidden): going
        # back to a tab shows what is there instead of building the whole page anew (~0.35 s until it showed)
        self.forms = {k: qform.Form(None, self) for k, _ in self.sp.TABS}
        self.seen = {self.sp.tab}
        self.forms[self.sp.tab].set_build(lambda ui: self._build_body(ui, self.sp.tab))
        self.filt = qform.Form(self._build_filter, self)
        sp.listeners.append(self._data)

    def _data(self):
        if self._active:
            self.forms[self.sp.tab].soon()   # the others when they show again
            self.filt.soon()
        self.changed.emit()

    @QtCore.Slot(bool)
    def setActive(self, on):
        self._active = bool(on)
        if on:
            self.forms[self.sp.tab].refresh()
            self.filt.refresh()

    # ---------- content ----------
    def _chart(self, ui, obj):
        return ui.chart(qcharts.spec(obj), lambda v, o=obj: qcharts.act(o, v))

    def _build_body(self, ui, tab):
        sp = self.sp
        out = []
        for entry in sp.layout(tab):
            kind = entry[0]
            if kind in ("hero", "kpis", "full"):
                out.append(self._chart(ui, entry[1]))
            elif kind == "section":
                from ui import statsview
                out.append(ui.space(6))
                out.append(self._chart(ui, statsview.SectionHead(*entry[1:])))
            elif kind == "pair":
                out.append(ui.row([self._chart(ui, entry[1]), self._chart(ui, entry[2])], spacing=14))
            elif kind == "raw" and entry[1]:   # finished tile (e.g. value history of the collection)
                out.append(ui.chart(entry[1], lambda v: None))
            elif kind == "pick" and sp.pick_options:
                out.append(ui.row([ui.combo(sp.pick_options, sp.pick_sid, sp.pick_session), ui.stretch()]))
        return ui.col(out, spacing=12)

    # ---------- filter (Sessions tab only) ----------
    def _build_filter(self, ui):
        sp = self.sp
        types_sel, tags_sel = sp.selection()
        many = len(sp.tags_all) > 10
        shown = [t for t in sp.tags_all if t in tags_sel] if many else sp.tags_all
        type_row = None if not sp.has_packs else ui.row([ui.label(tr("Pack types"), bold=True, color="gray", fixed=True)]
                          + [ui.button(label, lambda k=k: sp.type_toggled(k, k not in types_sel), tip=tip,
                                       active=k in types_sel) for k, label, tip in sp.types_present]
                          + [ui.stretch(), ui.button(tr("Default"), sp.reset_filter,
                                                     tip=tr("Only types that count as packs (setting in “Pack types …”), no tags"))], spacing=6)
        tag_row = ui.row([ui.label(tr("Tags"), bold=True, color="gray", fixed=True)]
                         + [ui.button(t, lambda t=t: sp.tag_toggled(t, t not in tags_sel), active=t in tags_sel)
                            for t in shown] + [ui.stretch()], spacing=6) if shown else None
        tag_add = ui.tags([], [t for t in sp.tags_all if t not in tags_sel],
                          lambda tags: sp.tags_picked(list(tags_sel) + [t for t in tags if t not in tags_sel]),
                          placeholder=tr("Search a tag and add it as a filter …")) if many else None
        return ui.col([type_row, tag_row, tag_add, ui.note(sp.filter_note)], spacing=8)

    # ---------- for QML ----------
    @QtCore.Property("QVariantList", constant=True)
    def tabs(self):
        return [{"key": k, "text": tr(t)} for k, t in self.sp.TABS]

    @QtCore.Property(str, notify=changed)
    def tab(self):
        return self.sp.tab

    @QtCore.Slot(str)
    def setTab(self, key):
        self.sp.show_tab(key)
        if key != "sessions":
            self._open = False
        key = self.sp.tab
        f = self.forms[key]
        if key not in self.seen:
            self.seen.add(key)
            f.set_build(lambda ui, k=key: self._build_body(ui, k))
        else:
            f.refresh()   # the same structure: only changed values go to QML (nothing is rebuilt)
        self.changed.emit()

    @QtCore.Property(bool, notify=changed)
    def filterShown(self):
        return self.sp.tab == "sessions" and bool(self.sp.all)

    @QtCore.Property(bool, notify=changed)
    def hasPacks(self):
        """Any session that opens boosters? Only then pack types (filter) and pack figures."""
        return bool(self.sp.has_packs)

    @QtCore.Property(bool, notify=changed)
    def filterOpen(self):
        return self._open

    @QtCore.Property(str, notify=changed)
    def filterText(self):
        return self.sp.filter_text

    @QtCore.Slot()
    def toggleFilter(self):
        self._open = not self._open
        self.filt.refresh()
        self.changed.emit()

    @QtCore.Property("QVariantList", notify=changed)
    def seenTabs(self):
        return [k for k, _ in self.sp.TABS if k in self.seen]

    @QtCore.Slot(str, result=QtCore.QObject)
    def bodyOf(self, key):
        return self.forms.get(key)

    @QtCore.Property(QtCore.QObject, constant=True)
    def filter(self):
        return self.filt
