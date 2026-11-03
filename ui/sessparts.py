"""The "Edit card" view under sessions lies over the detail view (which closes for it, as does an open comparison);
afterwards the detail view reappears – with the changed card. The search itself is ui.panels.CardPanel,
drawn by CardSearch.qml (sessions page in Qt Quick)."""
from PySide6 import QtCore

from system.i18n import tr


class EditPage(QtCore.QObject):
    def __init__(self, ctrl, panel_cls):
        super().__init__(ctrl)
        self.ctrl, self._visible = ctrl, False
        self.panel = panel_cls(ctrl, self, in_stream=False)  # logic; drawn by CardSearch.qml
        self.panel.chosen.connect(self._chosen)
        self.panel.removed.connect(self._removed)
        self.panel.closeRequested.connect(lambda: self.close_page())
        self.target, self.had_detail = None, False

    def isVisible(self):
        return self._visible

    def isHidden(self):
        return not self._visible

    def open(self, sid, pi, ci, entry):
        c = self.ctrl
        c.sess_host.close_compare(animate=False)
        if not self._visible:
            self.had_detail = c.sess_card.isVisible()
        self.target = (sid, pi, ci)
        packs = len(getattr(c, "sess_packs", []) or []) > 1 or not any(pk.get("plain") for pk in getattr(c, "sess_packs", []) or [])
        self.panel.open_edit(entry, tr(f" · pack {pi + 1}") if packs else "")   # scanning cards: no pack number
        if self.had_detail:
            c.sess_card.hide()
        self._visible = True

    def close_page(self, entry=None, show_detail=None):
        """entry: changed card (for the detail view afterwards); show_detail=False: detail view stays closed."""
        c = self.ctrl
        if not self._visible:
            return
        back = self.had_detail if show_detail is None else (show_detail and self.had_detail)
        self._visible = False
        if back:
            if entry is not None:
                c.sess_card.show_row(c.sess_host.row_for_entry(entry))
            c.sess_card.show()
        elif not c.sess_card.isVisible():
            c.sess_card.show_row(None)
        c.sess_host.update_marks()
        self.target = None

    def _chosen(self, card, foil, lang):
        sid, pi, ci = self.target
        fin, ed = self.panel.finish or None, self.panel.edition
        self.ctrl.stats_apply(sid, lambda s: s.replace(card, ci, pi, foil, lang, finish=fin, edition=ed))
        try:
            entry = self.ctrl.session_obj(sid).to_dict()["packs"][pi]["cards"][ci]
        except (IndexError, KeyError):
            entry = None
        self.close_page(entry)

    def _removed(self):
        sid, pi, ci = self.target
        self.ctrl.stats_apply(sid, lambda s: s.undo(ci, pi))
        self.close_page(show_detail=False)
