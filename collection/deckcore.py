"""Deck building without widgets: overview (tiles, folders), editor (search, results, upgrades, alternatives, deck list,
deck info, detail with deck buttons), Bent°Corner suggestion and deck comparison – as state and logic.

Everything is drawn in Qt Quick (qdecks.py / DecksPage.qml, qdeckedit.py / DeckEditor.qml, qdeckmore.py /
DeckCompare.qml, DeckSuggest.qml); the logic is the same as it used to be in deckview.py.
"""
import collections
import copy
import html
import math
import re
import threading
import time

from PySide6 import QtCore, QtGui
from PySide6.QtCore import Qt

from cards import alternatives
from cards import carddb
from ui import charts
from cards import combos
from cards import currency
from collection import decks
from cards import library
from ui import qdialogs
from collection import suggest
from collection.collection import scryfall_id
from system.i18n import tr
from system import i18n
from ui.librarycore import THUMBS, CompareState, DetailState, ImageLoader, LibraryCore, run_async
from ui.searchbox import CountSection, Mode, SearchBox, Steps
from games import mtg as _mtg

MANA = _mtg.GAME.color_hex   # Magic's mana colors (the deck page always draws W U B R G C)
TYPE_NAMES = dict(decks.TYPE_ORDER)


def _game_changed():
    TYPE_NAMES.clear()
    TYPE_NAMES.update(decks.TYPE_ORDER)
CYAN_C = "#62f2ff"
FOLDER_COLORS = [("#62f2ff", "Cyan"), ("#ffb347", "Bernstein"), ("#ff5bd6", "Pink"), ("#46d17a", "Grün"),
                 ("#ff4d5e", "Rot"), ("#a78bfa", "Violett"), ("#4a90d9", "Blau"), ("#eef1ff", "Weiß"),
                 ("#8a91a8", "Grau")]
LOOSE = ""  # key for "No folder" (None = all decks)


def eur(v):
    return currency.fmt(v)


def pips_html(colors):
    import games
    g = games.current()
    if not colors:
        return f"<span style='color:#8a91a8'>{tr("colorless")}</span>" if g.key == "mtg" else ""
    hexes = g.color_hex
    return " ".join(f"<span style='color:{hexes[c]}; font-size:16px'>●</span>" for c in colors if c in hexes)


def _price(r):
    if r is None:
        return ""
    v = r.get("eur") if r.get("eur") is not None else r.get("eur_foil")
    return eur(v) if v is not None else ""


class _Text:
    """Text with visibility (instead of QLabel)."""

    def __init__(self, text=""):
        self._text, self._visible, self._tip = text, True, ""

    def text(self):
        return self._text

    def setText(self, t):
        self._text = t or ""

    def toolTip(self):
        return self._tip

    def setToolTip(self, t):
        self._tip = t or ""

    def isHidden(self):
        return not self._visible

    def isVisible(self):
        return self._visible

    def setVisible(self, on):
        self._visible = bool(on)

    def show(self):
        self._visible = True

    def hide(self):
        self._visible = False


# ---------- Upgrade mode (Qt Quick): one row = one swap ----------
class UpgradeModel(QtCore.QAbstractListModel):
    """Rows for UpgradeList.qml: per suggestion the card going out (or a free slot) and the new one."""
    ROLES = ("outName", "outImg", "outPrice", "hasOut", "inName", "inImg", "inPrice", "why", "done", "choosing",
             "options")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []  # {"in", "out", "why", "options", "done", "choosing", "did"}
        self.img_url = lambda r: ""

    def roleNames(self):
        return {Qt.UserRole + i: name.encode() for i, name in enumerate(self.ROLES)}

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role):
        if not index.isValid() or not 0 <= index.row() < len(self.items):
            return None
        x, key = self.items[index.row()], self.ROLES[role - Qt.UserRole] if role >= Qt.UserRole else None
        o, i = x.get("out"), x["in"]
        return {"outName": o["name"] if o else "", "outImg": self.img_url(o), "outPrice": _price(o),
                "hasOut": o is not None, "inName": i["name"], "inImg": self.img_url(i), "inPrice": _price(i),
                "why": "\n".join(x.get("why") or []), "done": bool(x.get("done")),
                "choosing": bool(x.get("choosing")),
                "options": [{"name": w["name"], "price": _price(w), "current": o is not None and w["name"] == o["name"]}
                            for w in x.get("options") or []]}.get(key)

    def set_items(self, items):
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def changed(self, i):
        if 0 <= i < len(self.items):
            idx = self.index(i)
            self.dataChanged.emit(idx, idx)

    def refresh_images(self):
        if self.items:
            self.dataChanged.emit(self.index(0), self.index(len(self.items) - 1))


class UpgradeBridge(QtCore.QObject):
    """Actions from QML: select a row, swap/undo, pick a different out-card."""

    def __init__(self, results):
        super().__init__(results)
        self.panel = results

    @QtCore.Slot(int)
    def select(self, i):
        self.panel.select_upgrade(i)

    @QtCore.Slot(int)
    def act(self, i):
        self.panel.act_upgrade(i)

    @QtCore.Slot(int)
    def toggleChoose(self, i):
        m = self.panel.up_model
        if 0 <= i < len(m.items):
            for k, x in enumerate(m.items):  # only one picker open at a time
                if x.get("choosing") and k != i:
                    x["choosing"] = False
                    m.changed(k)
            m.items[i]["choosing"] = not m.items[i].get("choosing")
            m.changed(i)
            self.panel.select_upgrade(i)

    @QtCore.Slot(str, result="QVariantList")
    def deckChoices(self, q):
        """Search in the out-card picker: all cards in the deck whose name matches (at most 12)."""
        ed = self.panel.editor
        q = (q or "").strip().lower()
        if ed.deck is None or not q:
            return []
        out, seen = [], set()
        for c in ed.deck["cards"]:
            r = ed.rows.get(c["sid"])
            if r is None or r["name"] in seen or q not in r["name"].lower():
                continue
            seen.add(r["name"])
            out.append({"sid": c["sid"], "name": r["name"], "price": _price(r)})
        out.sort(key=lambda x: (not x["name"].lower().startswith(q), x["name"]))
        return out[:12]

    @QtCore.Slot(int, str)
    def chooseOutSid(self, i, sid):
        """Take a specific card out of the deck (via search or dragged from the deck list onto the row)."""
        m = self.panel.up_model
        ed = self.panel.editor
        if not 0 <= i < len(m.items) or m.items[i].get("done"):
            return
        r = ed.rows.get(sid)
        if r is None:
            return
        x = m.items[i]
        opts = list(x.get("options") or [])
        if all(o.get("id") != r.get("id") for o in opts):
            opts.append(r)
        x["options"], x["out"], x["choosing"] = opts, r, False
        m.changed(i)
        self.panel.select_upgrade(i, force=True)

    @QtCore.Slot(int, int)
    def chooseOut(self, i, j):
        m = self.panel.up_model
        if not 0 <= i < len(m.items) or m.items[i].get("done"):
            return
        x = m.items[i]
        x["out"] = x["options"][j] if 0 <= j < len(x.get("options") or []) else None
        x["choosing"] = False
        m.changed(i)
        self.panel.select_upgrade(i, force=True)


# ---------- Search results on the left ----------
class Results(QtCore.QObject):
    """Editor search results (same search as the library), cards from the deck info (subset),
    alternatives to a card or upgrades from the collection (swap rows)."""
    changed = QtCore.Signal()

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.rows, self.hint, self.subset = [], "", False
        self.up_model, self.up_view, self.up_current = UpgradeModel(self), False, -1
        self.up_model.img_url = self._up_img
        self.up_bridge = UpgradeBridge(self)
        self.token = 0

    def _set(self, rows=None, hint=None):
        if rows is not None:
            self.rows = list(rows)
        if hint is not None:
            self.hint = hint
        self.changed.emit()

    def show_subset(self, label, rows):
        """Show cards from the deck (click in the deck info) – until the next search."""
        self.token += 1  # discard the running search
        self.subset = True
        self._set(sorted(rows, key=lambda r: (r.get("cmc") or 0, r["name"])),
                  f"<b style='color:#eef1ff'>{label}</b>&nbsp;&nbsp;" + tr(f"{len(rows)} cards from the deck"))

    # --- Upgrade mode ---
    def _up_img(self, r):
        """Image URL of a card for QML (loads in the background; when done -> loader.ready -> show again)."""
        if r is None or self.editor.page.art(r) is None:
            return ""
        from ui import quickui
        return quickui.file_url(THUMBS / f"{r['id']}_en_n.jpg")

    def set_upgrade_view(self, on):
        """Upgrade mode: swap rows instead of the card grid."""
        self.up_view = bool(on)
        if not on:
            self.up_current = -1
        self.editor.set_upgrade_layout(on)
        self.changed.emit()

    def select_upgrade(self, i, force=False):
        m = self.up_model
        if not 0 <= i < len(m.items) or (i == self.up_current and not force):
            return
        self.up_current = i
        x = m.items[i]
        self.editor.show_upgrade_pair(x.get("out"), x["in"])
        self.changed.emit()

    def act_upgrade(self, i):
        """Swap (left out, right in) – or undo."""
        m, ed = self.up_model, self.editor
        if not 0 <= i < len(m.items) or ed.deck is None:
            return
        x = m.items[i]
        if not x.get("done"):
            if x.get("out") is not None:
                ed.remove_one(x["out"])
            ed.add(x["in"])
            x["done"], x["did"] = True, x.get("out")
        else:
            ed.remove_one(x["in"])
            if x.get("did") is not None:
                ed.rows.setdefault(x["did"]["id"], x["did"])
                ed.add(x["did"], exact=True)
            x["done"], x["did"] = False, None
        x["choosing"] = False
        m.changed(i)
        self.select_upgrade(i, force=True)

    def run(self):
        self.subset = False
        ed = self.editor
        deck = ed.deck
        if deck is None:
            return
        if not carddb.exists():
            self._set([], tr("Card search needs the card database (Settings → Card data)."))
            return
        bar = ed.bar
        bar.refresh_chips()
        f, text = bar.filters()
        f.update(no_tokens=True, one_per_name=True)
        fmt = deck.get("format")
        if fmt and fmt not in decks._G.open_formats:
            f.setdefault("formats", []).append(fmt)
        ident = ed.analysis.get("identity") if ed.analysis else ""
        if fmt == "commander" and deck.get("commanders") and bar.ident.isChecked():
            f["identity"] = ident
        owned_ids = ed.page.owned_id
        ids = None
        if ed.mode == "mine":
            ids = set(owned_ids)
        owned = f.pop("owned", None)
        if owned:
            match = {sid for sid, n in owned_ids.items() if CountSection.matches(n, *owned)}
            ids = match if ids is None else ids & match
        if ids is not None:
            f["only_ids"] = list(ids)
            f.pop("one_per_name")  # show own printings, not the newest
        sort = ed.sort.currentData()
        if sort == "auto":   # Magic: popular on EDHREC; other games: newest first
            sort = "relevance" if text else ("edhrec" if "brew" in decks._G.deck_extras else "new")
        self.token += 1
        token = self.token
        if ed.upgrade_mode:
            self._run_upgrades(token)
            return
        if self.up_view:
            self.set_upgrade_view(False)
        if ed.alt is not None:
            target, wanted = ed.alt, set(ed.alt_kinds)
            in_deck = {r["name"] for r in ed.rows.values()} if ed.deck else set()
            # Alternatives: from your collection, only ones you don't have (yet), or all cards
            which, owned_names = ed.alt_owned, set(ed.page.owned_name)
            fa = {k: v for k, v in f.items() if k != "only_ids"}
            if which == "mine":
                fa["only_ids"] = list(owned_ids)
                fa.pop("one_per_name", None)

            def alt_work():
                pool = carddb.search(text, limit=4000, sort="edhrec", **fa)
                seen, rows = set(), []
                for r in pool:
                    if r["name"] not in seen and not (which == "missing" and r["name"] in owned_names):
                        seen.add(r["name"])
                        rows.append(r)
                ranked = alternatives.rank(target, rows, wanted, in_deck)[:150]
                for r, score, kinds in ranked:
                    r["_why"] = " · ".join(tr(lbl) for k, lbl in alternatives.KINDS if k in kinds)
                return [r for r, _, _ in ranked]
            run_async(self, alt_work, lambda res, err: self.show(token, res, err, text, alt=target))
            return

        def work():
            rows = carddb.search(text, limit=150, sort=sort, reverse=bool(getattr(ed, "sort_rev", False)), **f)
            seen, out = set(), []
            for r in rows:  # one printing per card (the first = most relevant / newest)
                if r["name"] not in seen:
                    seen.add(r["name"])
                    out.append(r)
            return out[:150]

        run_async(self, work, lambda res, err: self.show(token, res, err, text))

    def _run_upgrades(self, token):
        """Upgrades from the collection (suggest.upgrades) – in the background, EDHREC if reachable."""
        ed = self.editor
        deck, rows, analysis = ed.deck, dict(ed.rows), dict(ed.analysis or {})
        owned = ed.page.free_owned(deck.get("id"))
        self._set(hint=tr("Looking for upgrades in your collection …"))

        def work():
            pool = suggest.owned_rows(owned)
            out = suggest.upgrades(deck, rows, analysis, pool, online=ed.page.ctrl.settings.get("deck_online", True))
            return [{"in": x["row"], "out": x.get("out"), "why": list(x["why"]), "options": x.get("options") or []}
                    for x in out]
        run_async(self, work, lambda res, err: self.show(token, res, err, "", upgrades=True))

    def show(self, token, res, err, text, alt=None, upgrades=False):
        if token != self.token:
            return
        if upgrades:
            self.set_upgrade_view(True)
            self.up_current = -1
            self.up_model.set_items(res or [])
            self._set(hint=tr(f"{len(res or [])} upgrades from your collection") + " · "
                      + tr("one swap per row: left out, right in") if not err else
                      tr(f"Search not possible: {err}"))
            if res:
                QtCore.QTimer.singleShot(0, lambda: self.select_upgrade(0))
            return
        if err:
            hint = tr(f"Search not possible: {err}")
        elif alt is not None:
            where = {"mine": tr("from your collection"), "missing": tr("that you don't have yet")}.get(
                self.editor.alt_owned, tr("from all cards"))
            hint = tr(f"{len(res or [])} alternatives") + f" {where} · " + tr("most similar first")
        elif not text and self.editor.sort.currentData() == "auto" and not res and self.editor.mode == "mine":
            hint = tr("Nothing in your collection yet – “All cards” shows everything.")
        elif not text and self.editor.sort.currentData() == "auto":
            hint = tr("Popular on EDHREC – matching the deck. Search above or open the advanced search.")                 if "brew" in decks._G.deck_extras else tr("Newest cards first – search above or open the advanced search.")
        else:
            hint = tr(f"{len(res or [])} cards")
        self._set(res or [], hint)


# ---------- Deck buttons above a detail view ----------
class DeckActions:
    """In deck?, + Add to deck, As commander, Sideboard, Use this printing – for a detail view."""

    def __init__(self, editor):
        self.editor, self.card = editor, None
        self.label, self.print_shown, self.cmdr_shown = "", False, False

    def set_card(self, r):
        self.card = r
        self.update_state()

    def update_state(self):
        r, deck = self.card, self.editor.deck
        if r is None or deck is None:
            return
        same = sum(c["count"] for c in deck["cards"] if c["sid"] == r["id"]) + \
            (1 if r["id"] in deck.get("commanders", []) else 0)
        name_n = self.editor.deck_count(r["name"])
        txt = tr(f"In deck: <b>{name_n}×</b>") if name_n else f"<span style='color:#6c7390'>{tr("not in the deck")}</span>"
        if name_n and not same:
            txt += f" <span style='color:#ffb347'>{tr("(other printing)")}</span>"
        self.label = txt
        self.print_shown = bool(name_n) and not same
        self.cmdr_shown = deck.get("format") == "commander"


# ---------- Library detail view in the deck builder ----------
class DeckLib(QtCore.QObject):
    """Detail and compare view (librarycore.DetailState) in the deck builder."""
    detail_context = "deck"  # own order of the categories
    supports_pin = True       # like in the library: pin, ⇄ swap sides, close
    width_key = "deck_detail_w"

    def __init__(self, editor):
        super().__init__(editor)
        self.editor, self.ctrl, self.loader, self.mode = editor, editor.page.ctrl, editor.page.loader, "all"
        self.detail_pinned = False

    def row_from_db(self, r):
        return LibraryCore.row_from_db(self, r)

    def row_for_print(self, pr):
        return LibraryCore.row_for_print(self, pr)

    def detail_panels(self):
        return [p for p in (getattr(self.editor, "detail", None), getattr(self.editor, "compare", None)) if p]

    @property
    def owned_cache(self):
        return self.editor.page.owned_id

    def set_fold(self, key, on):
        """Fold state applies everywhere (library and deck builder)."""
        folded = set(self.ctrl.settings.get("detail_folded") or [])
        folded.discard(key) if on else folded.add(key)
        self.ctrl.settings["detail_folded"] = sorted(folded)
        self.ctrl.settings_changed()
        for panel in self.detail_panels():
            panel.set_fold(key, on)
        lib = getattr(self.ctrl, "library_win", None)
        if lib is not None:
            for panel in (lib.detail, lib.compare):
                panel.set_fold(key, on)

    def show_compare(self, pr):  # click on a printing: slides in on the left as a comparison
        self.editor.show_compare(pr)

    def print_picked(self, pr, panel):
        """Upgrade mode: another printing appears in the panel where it was clicked."""
        ed = self.editor
        if not ed.upgrade_layout:
            return False
        row = self.row_for_print(pr)
        r = row.get("db") or carddb.cards_by_ids({pr["id"]}).get(pr["id"])
        if r is not None:
            ed.rows.setdefault(r["id"], r)
            panel.show_row(self.row_from_db(r))
            (ed.cmp_actions if panel is ed.compare else ed.actions).set_card(r)
            self.update_marks()
            ed.detail_changed.emit()
        return True

    def close_compare(self):
        self.editor.close_compare()

    def close_detail(self):
        self.editor.close_detail()

    def swap_panels(self):  # ⇄ in the compare view
        self.editor.swap_detail()

    def update_marks(self):
        ed = self.editor
        marks = {}
        if ed.detail.row is not None:
            marks[ed.detail.row["sid"]] = "main"
        if ed.compare.isVisible() and ed.compare.row is not None:
            marks[ed.compare.row["sid"]] = "compare"
        for panel in self.detail_panels():
            panel.strip.set_marks(marks)

    def refresh(self, keep=False):  # card added to the collection
        self.editor.page.update_owned()
        self.editor.refresh()


# ---------- Deck info ----------
class CurveChart(charts.Card):
    """Mana curve: one bar per mana value (0 … 7+), creatures highlighted."""

    def __init__(self):
        super().__init__(tr("Mana curve"), tr("without lands"))
        self.curve, self.creatures = [0] * 8, [0] * 8
        self.labels, self.inner_label = None, ""   # other games: own buckets (e.g. Base · Phase 1 · Phase 2)
        self.setMinimumHeight(230)

    def set_data(self, curve, creatures, avg):
        self.title, self.labels = tr("Mana curve"), None
        self.curve, self.creatures = curve, creatures
        self.sub = tr(f"Ø {avg:.2f}".replace(".", ","))


class OnlineBridge(QtCore.QObject):
    """Result of the online lookup (background thread) back to the main thread."""
    done = QtCore.Signal(object, object, str)


class StatsPanel:
    """Deck info as data (shown by qdeckedit as a form): key figures, bracket, combos, mana curve, colors,
    card types, functions, tokens, warnings, missing cards."""

    def __init__(self, editor):
        self.editor = editor
        self.listeners = []
        self.kpis, self.kpis2 = charts.KpiRow(), charts.KpiRow()
        self.kpis.setMinimumHeight(88)
        self.kpis2.setMinimumHeight(88)
        self.bracket_html, self.combo_html, self.combo_shown = "", "", False
        self.roles_html, self.warn_html, self.missing_html, self.tokens = "", "", "", []
        self.curve = CurveChart()
        self.colors = charts.Donut(tr("Colors"), unit=tr("mana symbols"))
        self.colors.setMinimumHeight(230)
        self.types = charts.HBars(tr("Card types"), CYAN_C, money=False)
        self.types.setMinimumHeight(290)
        self.roles = charts.HBars(tr("Functions"), "#ffb347", money=False)
        self.roles.setMinimumHeight(290)
        # click on a bar, label or donut slice: show those cards on the left in the card area
        self.curve.picked.connect(lambda i: self.pick("curve", i))
        self.colors.picked.connect(lambda i: self.pick("colors", i))
        self.types.picked.connect(lambda i: self.pick("types", i))
        self.roles.picked.connect(lambda i: self.pick("roles", i))
        self._pick_data = {}
        self.token_names = None

    def _notify(self):
        for fn in list(self.listeners):
            fn()

    def token_count(self, name):
        return self.editor.deck.get("tokens", {}).get(name, 0) if self.editor.deck else 0

    def bump_token(self, name, d):
        """Game counter: saved immediately, does not mark the deck as "unsaved"."""
        tokens = self.editor.deck.setdefault("tokens", {})
        tokens[name] = max(0, tokens.get(name, 0) + d)
        if self.editor.orig is not None:
            self.editor.orig.setdefault("tokens", {})[name] = tokens[name]
        self.editor.page.save_later()
        self._notify()

    def pick(self, kind, i):
        res = self.editor.results
        if getattr(self, "_active_pick", None) == (kind, i) and res.subset:
            self._active_pick = None
            res.run()  # clicked again: back to the search
            return
        self._active_pick = (kind, i)
        items = self._pick_data.get(kind) or []
        if 0 <= i < len(items):
            label, rows = items[i]
            seen, uniq = set(), []
            for r in rows:
                if r["id"] not in seen:
                    seen.add(r["id"])
                    uniq.append(r)
            res.show_subset(label, uniq)

    def set_online(self, deck, rows, online, status):
        """Combos (Commander Spellbook) and cEDH data (EDHTop16). status: "" | "loading" | "offline"."""
        commander = deck.get("format") == "commander"
        self.combo_shown = commander
        if not commander:
            return
        csb, cedh = online.get("csb"), online.get("cedh") or {}
        page = self.editor.page
        holders = page.ctrl.trade_holders() if hasattr(page.ctrl, "trade_holders") else {}
        parts = []
        if status == "loading" and csb is None:
            parts.append(f"<span style='color:#8a91a8'>{tr("Looking up combos on Commander Spellbook …")}</span>")
        elif csb is None:
            parts.append(f"<span style='color:#8a91a8'>{tr("Offline – combos and tournament data appear once there's an internet connection.")}</span>")
        else:
            tag = combos.TAGS.get(csb.get("tag") or "")
            if tag:
                parts.append(f"{tr("Category")}: <b style='color:#ffb347'>{tag[0]}</b> "
                             f"<span style='color:#8a91a8'>– {tr(tag[1])}</span>")
            inc = csb.get("included") or []
            if inc:
                parts.append(f"<b style='color:#46d17a'>{tr(f"{len(inc)} combos in the deck")}</b>")
                for c in inc[:12]:
                    parts.append(self._combo_line(c))
            else:
                parts.append(f"<span style='color:#aab1c8'>{tr("No complete combo in the deck.")}</span>")
            alm = csb.get("almost") or []
            if alm:
                parts.append(f"<br><b style='color:#62f2ff'>{tr("Near combos – exactly one card missing")}</b>")
                for c in alm[:10]:
                    miss = c["missing"][0]
                    own = page.owned_name.get(miss)
                    who = holders.get(miss) or []
                    hint = (f" <span style='color:#46d17a'>✓ {tr("in your collection")}</span>" if own else "") + \
                           (f" <span style='color:#ffb347'>· {tr("owned by")}: {', '.join(n for _, n, _, _ in who)}</span>"
                            if who else "")
                    parts.append(self._combo_line(c, f"{tr('fehlt')}: <b>{miss}</b>{hint}"))
                if len(alm) > 10:
                    parts.append(f"<span style='color:#6c7390'>{tr(f"… and {len(alm) - 10} more")}</span>")
            when = time.strftime("%d.%m.%Y", time.localtime(csb.get("t") or time.time()))
            parts.append(f"<br><span style='color:#6c7390'>{tr("Source")}: "
                         f"<a style='color:#62f2ff' href='https://commanderspellbook.com'>Commander Spellbook</a> · "
                         f"{tr("as of")} {when}{' · ' + tr('offline') if status == 'offline' else ''}</span>")
        if cedh.get("count"):
            parts.append(f"<br><b style='color:#62f2ff'>{tr("cEDH tournaments (EDHTop16, 12 months)")}</b><br>"
                         + tr(f"{cedh['count']} decks · win rate {cedh.get('winRate', 0) * 100:.1f} % · top cut {cedh.get('conversionRate', 0) * 100:.1f} % · meta share {cedh.get('metaShare', 0) * 100:.2f} %")
                         + f"<br><span style='color:#6c7390'>{tr("Win rate in a four-player pod: 25 % is average.")}"
                           "</span>")
        elif csb is not None and online.get("cedh") is not None:
            parts.append(f"<br><span style='color:#6c7390'>{tr("Hardly played in cEDH tournaments (EDHTop16).")}</span>")
        self.combo_html = "<br>".join(parts)
        self._notify()

    def _set_generic(self, a, deck):
        import games
        g = games.current()
        k = a["kpis"]

        def fmt(v):
            return str(round(v))
        self.kpis.set_items([(tr(name), v, fmt, CYAN_C if i == 0 else "#eef1ff", tr(sub)) for i, (name, v, sub) in
                             enumerate(k[:3])])
        total = a.get("total", a["count"])   # Yu-Gi-Oh!: count = Main Deck, total = Main + Extra
        own_share = a["owned"] / total * 100 if total else 0
        self.kpis2.set_items([
            (tr("Value"), a["price"], eur, CYAN_C, ""),
            (tr("Im Besitz"), own_share, lambda v: f"{v:.0f} %", "#46d17a", tr(f"{a['owned']} of {total}")),
            (tr("Still missing"), a["missing_price"], eur, "#ff5bd6", tr(f"{sum((n for _, n in a['missing']))} cards")),
        ] + [(tr(name), v, fmt, "#eef1ff", tr(sub)) for name, v, sub in k[3:4]])
        self.bracket_html = ""
        self.combo_shown = False
        cm = a["curve_meta"]
        self.curve.title = tr(cm["title"])
        self.curve.labels = [tr(x) for x in cm["labels"]]
        self.curve.inner_label = tr(cm["inner"])
        self.curve.curve, self.curve.creatures, self.curve.sub = a["curve"], a["curve_creatures"], tr(cm["sub"])
        self.colors.title = tr(g.adv_titles.get("colors") or "Farben")
        pal = [c for c in g.palette if a["colors"].get(c)]
        self.colors.set_parts([(tr(g.color_names.get(c, c)), a["colors"][c], g.color_hex.get(c, "#b6b6b6"))
                               for c in g.palette], sum(a["colors"].values()), center_fmt=fmt,
                              center_label=tr("Cards"), center_color=CYAN_C)
        types_sorted = sorted(a["types"].items(), key=lambda kv: -kv[1])
        names = dict(g.type_order)
        self.types.set_rows([(tr(names.get(t, t)), n, "") for t, n in types_sorted])
        self.roles.set_rows([(tr(r), n, ", ".join(a["role_cards"][r][:8]) + (" …" if len(a["role_cards"][r]) > 8
                                                                                else ""))
                             for r, n in a["roles"].items()])
        self._pick_data = {
            "types": [(tr(names.get(t, t)), a["type_rows"].get(t, [])) for t, _ in types_sorted],
            "roles": [(tr(r), a["role_rows"].get(r, [])) for r in a["roles"]],
            "curve": [(tr(lab), rows) for lab, rows in zip(cm["labels"], a["curve_rows"])],
            "colors": [(tr(g.color_names.get(c, c)), a["color_rows"].get(c, [])) for c in pal]}
        parts = []
        for r in a["roles"]:
            cards = a["role_cards"][r]
            parts.append(f"<p style='margin:0 0 8px 0'><b style='color:#ffb347'>{tr(r)}</b> "
                         f"<span style='color:#8a91a8'>– {tr(a['role_help'][r])}</span><br>"
                         + (", ".join(dict.fromkeys(cards)) if cards else
                            f"<span style='color:#6c7390'>{tr('keine')}</span>") + "</p>")
        self.roles_html = "".join(parts) + f"<p style='color:#6c7390'>{tr("Estimated from the card text.")}</p>"
        self.tokens = []
        if a["warnings"]:
            self.warn_html = "<br>".join(f"<span style='color:#ffb347'>⚠</span> {tr(w)}" for w in a["warnings"])
        else:
            self.warn_html = f"<span style='color:#46d17a; font-weight:700'>✓ {tr("Deck is legal")}</span>"
        if a["missing"]:
            items = ", ".join(f"{n}× {name}" if n > 1 else name for name, n in a["missing"][:40])
            more = len(a["missing"]) - 40
            self.missing_html = (f"<span style='color:#aab1c8'>{items}"
                                 f"{tr(f" … and {more} more") if more > 0 else ''}</span>")
        else:
            self.missing_html = (f"<span style='color:#46d17a'>{tr("All cards are in your collection.")}</span>"
                                 if a["count"] else "")
        self._notify()

    @staticmethod
    def _combo_line(c, extra=""):
        res = ", ".join(c["produces"][:2])
        tip = (c["description"] or "")[:900].replace("&", "&amp;").replace("<", "&lt;").replace("'", "&#39;") \
            .replace("\n", "<br>")
        return (f"<span title='{tip}'>• {' + '.join(c['cards'])} <span style='color:#8a91a8'>→ {res}</span>"
                f"{'<br>&nbsp;&nbsp;' + extra if extra else ''} <a style='color:#62f2ff' href='{c['url']}'>↗</a></span>")

    def set_analysis(self, a, deck):
        if a.get("kpis") is not None:   # other game: key figures, curve, types, functions from the game description
            return self._set_generic(a, deck)
        self.colors.title = tr("Colors")
        size = a["size"]
        own_share = a["owned"] / a["count"] * 100 if a["count"] else 0
        self.kpis.set_items([
            (tr("Cards"), a["count"], lambda v: f"{round(v)}" + (f" / {size}" if size else ""),
             "#46d17a" if size and a["count"] == size else CYAN_C, ""),
            (tr("Ø mana value"), a["avg_mv"], lambda v: f"{v:.2f}".replace(".", ","), "#eef1ff", tr("without lands")),
            (tr("Lands"), a["lands"], lambda v: str(round(v)), "#eef1ff", ""),
        ])
        self.kpis2.set_items([
            (tr("Value"), a["price"], eur, CYAN_C, ""),
            (tr("Im Besitz"), own_share, lambda v: f"{v:.0f} %", "#46d17a", tr(f"{a['owned']} of {a['count']}")),
            (tr("Still missing"), a["missing_price"], eur, "#ff5bd6", tr(f"{sum((n for _, n in a['missing']))} cards")),
        ])
        if deck.get("format") == "commander":
            lvl = a["bracket"]
            reasons = "".join(f"<li>{tr(x)}</li>" for x in a["bracket_reasons"])
            self.bracket_html = (
                f"<span style='font-size:13pt; font-weight:700; color:#62f2ff'>{tr('Bracket')}</span>"
                f"<span style='color:#8a91a8'>&nbsp;&nbsp;"
                f"{tr("(Deck info: estimated from card text and various sources)")}</span><br>"
                f"<span style='font-size:30px; font-weight:800; color:#ffb347'>{lvl}</span>"
                f"<span style='font-size:16px; color:#eef1ff'>&nbsp; {decks.BRACKETS[lvl]}</span>"
                f"<ul style='margin-left:-20px; color:#aab1c8'>{reasons}</ul>")
        else:
            self.bracket_html = ""
        self.curve.set_data(a["curve"], a["curve_creatures"], a["avg_mv"])
        names = {"W": tr("White"), "U": tr("Blue"), "B": tr("Black"), "R": tr("Red"), "G": tr("Green"),
                 "C": tr("Colorless")}
        total_sym = sum(a["colors"].values())
        self.colors.set_parts([(names[c], a["colors"][c], MANA[c]) for c in "WUBRGC"], total_sym,
                              center_fmt=lambda v: str(round(v)), center_label=tr("symbols"), center_color=CYAN_C)
        types_sorted = sorted(a["types"].items(), key=lambda kv: -kv[1])
        self.types.set_rows([(tr(TYPE_NAMES.get(k, k)), n, "") for k, n in types_sorted])
        self.roles.set_rows([(decks.role_label(k), n, ", ".join(a["role_cards"][k][:8]) + (" …" if len(a["role_cards"][k]) > 8
                                                                                else ""))
                             for k, n in a["roles"].items()])
        colors = [c for c in "WUBRGC" if a["colors"][c]]
        self._pick_data = {
            "types": [(tr(TYPE_NAMES.get(k, k)), a.get("type_rows", {}).get(k, [])) for k, _ in types_sorted],
            "roles": [(decks.role_label(k), a.get("role_rows", {}).get(k, [])) for k in a["roles"]],
            "curve": [(tr(f"Mana value {('7+' if i == 7 else i)}"), rows) for i, rows in
                      enumerate(a.get("curve_rows") or [[] for _ in range(8)])],
            "colors": [(names[c], a.get("color_rows", {}).get(c, [])) for c in colors]}
        parts = []
        for k in a["roles"]:
            cards = a["role_cards"][k]
            parts.append(f"<p style='margin:0 0 8px 0'><b style='color:#ffb347'>{decks.role_label(k)}</b> "
                         f"<span style='color:#8a91a8'>– {tr(decks.ROLE_HELP[k])}</span><br>"
                         + (", ".join(cards) if cards else f"<span style='color:#6c7390'>{tr('keine')}</span>")
                         + "</p>")
        note = tr("Estimated from the rules text – a card can be in several categories.")
        self.roles_html = "".join(parts) + f"<p style='color:#6c7390'>{note}</p>"
        self.tokens = sorted(a["tokens"].items())  # [(name, [sources])]
        if a["warnings"]:
            self.warn_html = "<br>".join(f"<span style='color:#ffb347'>⚠</span> {tr(w)}" for w in a["warnings"])
        else:
            self.warn_html = f"<span style='color:#46d17a; font-weight:700'>✓ {tr("Deck is legal")}</span>"
        if a["missing"]:
            items = ", ".join(f"{n}× {name}" if n > 1 else name for name, n in a["missing"][:40])
            more = len(a["missing"]) - 40
            self.missing_html = (f"<span style='color:#aab1c8'>{items}"
                                 f"{tr(f" … and {more} more") if more > 0 else ''}</span>")
        else:
            self.missing_html = (f"<span style='color:#46d17a'>{tr("All cards are in your collection.")}</span>"
                                 if a["count"] else "")
        self._notify()


# ---------- Editor ----------
class DeckEditor(QtCore.QObject):
    """Edit a deck: header (name, format, save …), search + results, detail (+ comparison) with
    deck buttons, deck list or deck info. Changes are only applied on save."""
    changed_sig = QtCore.Signal()   # header row, mode, tab, panels
    list_changed = QtCore.Signal()
    detail_changed = QtCore.Signal()
    START = {"full": 4, "detail": 3, "compare": 2}
    LIST_SORT_KEYS = {0: "count", 1: "name", 2: "cmc", 3: "price", 4: "own"}

    def __init__(self, page):
        super().__init__(page)
        self.page, self.deck, self.rows, self.analysis = page, None, {}, {}
        self.orig, self.dirty, self.mode = None, False, "mine"
        self.name, self.format = "", decks._G.default_format or "casual"
        self.summary, self.summary_tip, self.built = "", "", False
        self.bar = SearchBox(page.ctrl, "deck")
        self.bar.search.setPlaceholderText(tr("Search cards for the deck: name, rules text, type … or syntax like t:elf k:flying c<=wug mv<=3"))
        self.sort = Mode([(tr(label), key) for key, label in (
            ("auto", "Sortierung: automatisch"), ("edhrec", "Sortierung: EDHREC-Beliebtheit"),
            ("relevance", "Sortierung: Relevanz"), ("name", "Sortierung: Name"), ("price", "Sortierung: Preis"),
            ("mv", "Sortierung: Manawert"), ("type", "Sortierung: Kartentyp"), ("color", "Sortierung: Farbe"),
            ("rarity", "Sortierung: Seltenheit"), ("new", "Sortierung: Neueste"))], self)
        self.cols_slider = Steps(3, 8, self.area_columns("detail"), self)
        self.alt, self.alt_kinds, self.upgrade_mode, self.upgrade_layout = None, set(), False, False
        self.alt_owned = page.ctrl.settings.get("deck_alt_owned") or "mine"  # alternatives: mine | missing | all
        self.bar.extra_chips = self._extra_chips
        self.bar.extra_get = lambda: (self.alt, set(self.alt_kinds), self.upgrade_mode)
        self.bar.extra_set = self._extra_set
        self.results = Results(self)
        self.bar.changed.connect(self.results.run)
        self.sort_rev = False   # arrow on the sort button: ↑ = reversed
        self.sort.currentIndexChanged.connect(lambda _: (setattr(self, "sort_rev", False), self.results.run()))
        self.lib = DeckLib(self)
        self.compare = DetailState(self.lib, compare=True)
        self.detail = DetailState(self.lib)
        self.actions, self.cmp_actions = DeckActions(self), DeckActions(self)
        self.slide = CompareState(self.compare, self._cmp_closed, self)
        self.tab = 0
        self.cmdr = _Text()
        self.swap_text, self.swap_shown = "", False
        self.list_rows, self.list_current = [], None   # deck list for QML; selected row (sid, board)
        settings = page.ctrl.settings
        self.list_sort = settings.get("deck_list_sort") or None  # [column, descending]
        self.stats = StatsPanel(self)  # deck info (data; shown by qdeckedit)
        if not settings.get("deck_list_left"):  # new default (once): list left | cards | detail + comparison
            settings["deck_list_left"] = True
            settings["deck_panels"] = ["list", "cards", "detail"]
        self.apply_order(settings.get("deck_panels") or ["list", "cards", "detail"])

    def changed(self):
        """Deck changed (as before): mark as unsaved and recompute everything."""
        self.deck["updated"] = time.time()
        self.dirty = True
        hist = self.__dict__.setdefault("_hist", [])
        pos = self.__dict__.get("_hpos", len(hist) - 1)
        del hist[pos + 1:]
        hist.append(copy.deepcopy(self.deck))
        if len(hist) > 6:   # initial state + 5 steps
            del hist[0]
            self._hsaved = self.__dict__.get("_hsaved", 0) - 1
        self._hpos = len(hist) - 1
        self.update_dirty()
        self.refresh()

    def can_step(self, d):
        """Is there a step back (d=-1) or forward (d=1) in the editor?"""
        hist, pos = self.__dict__.get("_hist") or [], self.__dict__.get("_hpos", 0)
        return self.deck is not None and 0 <= pos + d < len(hist)

    def step(self, d):
        """Undo (-1) / redo (1) in the editor: restore a state from the history."""
        if not self.can_step(d):
            return False
        self._hpos += d
        self.deck = copy.deepcopy(self._hist[self._hpos])
        missing = decks.all_ids(self.deck) - set(self.rows)
        if missing:
            self.rows.update(carddb.cards_by_ids(missing))
        self.dirty = self._hpos != self.__dict__.get("_hsaved", 0)
        self.update_dirty()
        self.refresh()
        return True

    # --- Panels: order (saved; widths are managed by Qt Quick) ---
    def apply_order(self, order):
        if sorted(order) != ["cards", "detail", "list"]:
            order = ["list", "cards", "detail"]
        self.order = list(order)
        self.page.ctrl.settings["deck_panels"] = self.order
        self.changed_sig.emit()

    def swap_panels(self, a, b):
        """Swap two panels (handle at the top dragged)."""
        if a == b:
            return
        order = list(self.order)
        ia, ib = order.index(a), order.index(b)
        order[ia], order[ib] = b, a
        self.apply_order(order)

    def show_tab(self, i):
        self.tab = int(i)
        self.changed_sig.emit()

    # --- Load / show deck ---
    @property
    def card(self):
        return self.actions.card

    def set_mode(self, mode):
        self.mode = mode
        self.results.run()

    def open(self, deck):
        self.orig, self.deck, self.dirty = deck, copy.deepcopy(deck), False
        self._hist, self._hpos, self._hsaved = [copy.deepcopy(deck)], 0, 0   # undo in the editor
        self.alt, self.alt_kinds, self.upgrade_mode = None, set(), False  # other deck: alternatives/upgrades off
        self.built = bool(deck.get("built"))
        self.update_dirty()
        self.close_compare(animate=False)
        self.name = deck["name"]
        self.format = deck.get("format") or "casual"
        self.rows = carddb.cards_by_ids(decks.all_ids(deck))
        self.stats.token_names = None
        self.refresh()
        self.bar.prepare()
        self.bar.search.blockSignals(True)
        self.bar.search.clear()
        self.bar.search.blockSignals(False)
        self.results.run()
        first = next((self.rows[s] for s in deck.get("commanders", []) if s in self.rows), None)
        if first is None:  # no commander: first card of the list – the middle is never empty
            first = next((x["r"] for x in self.list_rows if not x["head"]), None)
        if first:
            self.show_card(first)
        else:
            self.detail.show_row(None)
            self.actions.set_card(None)
        self.changed_sig.emit()

    def online_lookup(self):
        """Combos/tournament data for the current list: immediately from the cache, fresh after a short pause."""
        deck = self.deck
        if deck is None or deck.get("format") != "commander" or not self.page.ctrl.settings.get("deck_online", True):
            self.online, self._online_key = {}, None
            return
        cm, main = combos.deck_lists(deck, self.rows)
        if not cm and len(main) < 10:
            self.online, self._online_key = {}, None
            return
        key = combos._deck_key(cm, main)
        if key == getattr(self, "_online_key", None):
            return
        self._online_key = key
        old = getattr(self, "online", None) or {}
        self.online = {"csb": combos.cached_find(cm, main) or old.get("csb"), "cedh": combos.cached_cedh(cm)
                       if cm else None}
        self._online_status = "loading"
        if not hasattr(self, "_online_timer"):
            self._online_timer = QtCore.QTimer(self, singleShot=True, interval=1500, timeout=self._fetch_online)
            self._online_bridge = OnlineBridge(self)
            self._online_bridge.done.connect(self._online_done)
        self._online_timer.start()

    def _fetch_online(self):
        key, deck = self._online_key, self.deck
        if key is None or deck is None:
            return
        cm, main = combos.deck_lists(deck, self.rows)
        bridge = self._online_bridge

        def work():
            out, status = {}, ""
            try:
                out["csb"] = combos.find(cm, main)
            except Exception:  # noqa: BLE001 – offline / service unreachable
                out["csb"], status = combos.cached_find(cm, main), "offline"
            try:
                out["cedh"] = combos.cedh(cm) if cm else None
            except Exception:  # noqa: BLE001
                out["cedh"] = combos.cached_cedh(cm) if cm else None
            bridge.done.emit(key, out, status)
        threading.Thread(target=work, daemon=True).start()

    def _online_done(self, key, out, status):
        if key != getattr(self, "_online_key", None) or self.deck is None:
            return  # the list has changed in the meantime
        self.online = out
        self._online_status = status
        self.refresh()

    def refresh(self):
        deck = self.deck
        if deck is None:
            return
        self.online_lookup()
        self.analysis = decks.analyze(deck, self.rows, self.page.owned_id, self.page.owned_name,
                                      online=getattr(self, "online", None))
        a = self.analysis
        size = a["size"]
        ok = a["size_ok"] if "size_ok" in a else (size and a["count"] == size)   # Yu-Gi-Oh!: range 40–60
        color = "#46d17a" if ok else "#62f2ff"
        extra = (f"&nbsp;&nbsp;<span style='color:#ffb347; font-weight:700'>{tr('Bracket')} {a['bracket']}</span>"
                 if deck.get("format") == "commander" else "")
        self.summary = (f"<span style='font-size:16px; font-weight:700; color:{color}'>{a['count']}"
                        f"{' / ' + str(size) if size else ''}</span>&nbsp;&nbsp;{pips_html(a['identity'])}"
                        f"&nbsp;&nbsp;<span style='color:#62f2ff'>{eur(a['price'])}</span>{extra}")
        self.summary_tip = (
            f"<b>{tr("Bracket (estimate)")} {a['bracket']} – {decks.BRACKETS[a['bracket']]}</b><ul>"
            + "".join(f"<li>{tr(x)}</li>" for x in a["bracket_reasons"]) + "</ul>"
            if deck.get("format") == "commander" else "")
        cm = [self.rows[s]["name"] for s in deck.get("commanders", []) if s in self.rows]
        if deck.get("format") == "commander":
            self.cmdr.setText(f"<span style='color:#8a91a8'>{tr('Commander')}:</span> "
                              f"<b style='font-size:14px'>{' + '.join(cm) if cm else tr("none yet")}</b>")
            self.cmdr.show()
        else:
            self.cmdr.hide()
        self.fill_list()
        self.stats.set_analysis(a, deck)
        self.stats.set_online(deck, self.rows, getattr(self, "online", None) or {},
                              getattr(self, "_online_status", ""))
        n = len(self.swappable())
        self.swap_text = tr(f"⇄  Switch {n} cards to your own printings")
        self.swap_shown = n > 0
        self.actions.update_state()
        self.cmp_actions.update_state()
        self.changed_sig.emit()
        self.detail_changed.emit()
        self.results.changed.emit()  # "in deck" on the results

    # --- Deck list ---
    def pinned(self, sid):
        """Printing pinned (exactly this one) – otherwise any printing of the card counts."""
        return self.deck is not None and sid in (self.deck.get("pinned") or [])

    def own_of(self, count, sid, usage):
        """Ownership of a row: ✓ exactly this printing (not pinned: any printing) · ≈ other printing ·
        ⚑ is in a built deck · ✗ missing."""
        r = self.rows[sid]
        have, other = self.page.owned_id.get(sid, 0), self.page.owned_name.get(r["name"], 0)
        if not self.pinned(sid):
            have = other
        used = sum(k for _, k in usage.get(r["name"], []))
        if bool(self.page.ctrl.settings.get("built_consumes", False)) and other >= count and other - used < count:
            return "⚑"
        return "✓" if have >= count else ("≈" if other >= count else (f"{max(have, other)}/{count}"
                                                                       if max(have, other) else "✗"))

    def list_sort_key(self, count, r, own):
        """Sort key within a group (no choice made: mana value, then name)."""
        price = r.get("eur") if r.get("eur") is not None else r.get("eur_foil")
        if not self.list_sort:
            return (r.get("cmc") or 0, r["name"])
        key = self.LIST_SORT_KEYS.get(self.list_sort[0])
        return {"count": (count, r["name"]), "name": (r["name"].lower(),), "cmc": (r.get("cmc") or 0, r["name"]),
                "price": ((price or 0) * count, r["name"]),
                "own": ({"✓": 0, "≈": 1}.get(own, 2), r["name"])}[key]

    def sort_list_by(self, col):
        """Click on a column header: sort by it, again = reversed (stays saved)."""
        if col not in self.LIST_SORT_KEYS:
            return
        if self.list_sort and self.list_sort[0] == col:
            self.list_sort = [col, not self.list_sort[1]]
        else:
            self.list_sort = [col, col in (3,)]  # price descending first, otherwise ascending
        self.page.ctrl.settings["deck_list_sort"] = self.list_sort
        self.fill_list()

    def fill_list(self):
        """Deck list by groups (commander, card types, sideboard, maybeboard) -> list_rows for QML."""
        deck, rows = self.deck, self.rows
        if deck is None:
            self.list_rows = []
            self.list_changed.emit()
            return
        groups = []
        cmdrs = [(1, s, "commander") for s in deck.get("commanders", []) if s in rows]
        if cmdrs:
            groups.append((tr("Commander"), cmdrs))
        main = [(c["count"], c["sid"], "main") for c in deck["cards"] if c.get("board", "main") == "main"
                and c["sid"] in rows]
        g = decks._G
        extra = [x for x in main if g.deck_zone(rows[x[1]]) == "extra"]   # Yu-Gi-Oh!: Extra Deck below
        main = [x for x in main if x not in extra]
        for key, label in decks.TYPE_ORDER + [("Other", "Sonstige")]:
            items = [x for x in main if decks._type(rows[x[1]]) == key]
            if items:
                groups.append((tr(label), items))
        if extra:
            groups.append((tr("Extra Deck"), extra))
        zones = any(r.get("size_main") for r in (g.deck_rules or {}).values())   # Yu-Gi-Oh!: "Side Deck"
        for board, label in (("side", "Side Deck" if zones else "Sideboard"), ("maybe", "Maybeboard")):
            items = [(c["count"], c["sid"], board) for c in deck["cards"] if c.get("board") == board
                     and c["sid"] in rows]
            if items:
                groups.append((tr(label), items))
        usage = self.page.built_usage(deck.get("id"))  # cards that are in other built decks
        holders_all = self.page.ctrl.trade_holders() if hasattr(self.page.ctrl, "trade_holders") else {}
        alt = self.alt["id"] if self.alt is not None else None
        out = []
        desc = bool(self.list_sort and self.list_sort[1])
        for label, items in groups:
            n = sum(x[0] for x in items)
            out.append({"head": True, "text": f"{label}  ({n})"})
            for count, sid, board in sorted(items, key=lambda x: self.list_sort_key(x[0], rows[x[1]],
                                                                                   self.own_of(x[0], x[1], usage)),
                                            reverse=desc):
                r = rows[sid]
                price = r.get("eur") if r.get("eur") is not None else r.get("eur_foil")
                own = self.own_of(count, sid, usage)
                tip = tr("✓ exactly this printing in the collection · ≈ other printing · ⚑ in a built deck · ✗ missing")
                pin = self.pinned(sid)
                if own == "⚑":
                    tip = tr("In a built deck: ") + ", ".join(f"{d} ({k}×)"
                                                                            for d, k in usage.get(r["name"], []))
                hold = []
                if own not in ("✓", "≈"):  # missing: which friends have it?
                    hold = holders_all.get(r["name"]) or []
                    if hold:
                        tip = tr("Missing – owned by: ") + ", ".join(f"{h[1]} ({h[3]}×)" for h in hold)
                out.append({"head": False, "sid": sid, "board": board, "count": f"{count}×", "n": count,
                            "name": r["name"], "cost": (r.get("mana_cost") or "").split(" // ")[0],
                            "price": eur((price or 0) * count), "own": own,
                            "ownColor": "#46d17a" if own in ("✓", "≈") else "#ffb347" if own == "⚑" else "#ff5bd6",
                            "ownTip": tip, "alt": sid == alt, "inUse": usage.get(r["name"], []), "holders": hold,
                            "pinned": pin, "where": (f"({(r.get('set_code') or '').upper()} #{r.get('number') or ''})"
                                                     if pin else tr("(any)")),
                            "r": r})
        self.list_rows = out
        self.list_changed.emit()

    def list_row(self, k):
        return self.list_rows[k] if 0 <= k < len(self.list_rows) and not self.list_rows[k]["head"] else None

    def select_list_row(self, k):
        x = self.list_row(k)
        if x is not None:
            self.list_current = (x["sid"], x["board"])
            self.show_card(x["r"])
            self.list_changed.emit()

    def current_list_row(self):
        return next((x for x in self.list_rows if not x["head"] and (x["sid"], x["board"]) == self.list_current), None)

    def deck_count(self, name):
        if self.deck is None:
            return 0
        n = sum(1 for s in self.deck.get("commanders", []) if s in self.rows and self.rows[s]["name"] == name)
        return n + sum(c["count"] for c in self.deck["cards"] if c.get("board", "main") == "main"
                       and c["sid"] in self.rows and self.rows[c["sid"]]["name"] == name)

    # --- Changes ---
    def update_dirty(self):
        self.changed_sig.emit()

    def save_as_version(self):
        """Current state (even unsaved) as a new version; the original stays as last saved."""
        new = self.page.duplicate_version(self.deck)
        self.dirty = False
        self.page.open_deck(new)

    def save_deck(self):
        if self.deck is None or not self.dirty:
            return
        self.orig.clear()
        self.orig.update(copy.deepcopy(self.deck))
        self.page.save()
        self.dirty = False
        self._hsaved = self.__dict__.get("_hpos", 0)
        self.update_dirty()
        self.page.toast(tr("Deck saved."), 2500)

    def discard(self):
        if self.orig is None:
            return
        card = self.card
        self.open(self.orig)
        if card is not None:
            self.show_card(card)

    def maybe_leave(self):
        """Ask when leaving with unsaved changes. -> True = carry on."""
        if self.deck is None or not self.dirty:
            return True
        answer = qdialogs.ask(tr("Deck not saved"), tr(f"“{self.deck['name']}” has unsaved changes."),
                              [("cancel", tr("Cancel"), ""), ("drop", tr("Discard"), "danger"),
                               ("save", tr("Save"), "active")],
                              informative=tr("Save, discard (back to the saved version) or keep editing?"))
        if answer == "save":
            self.save_deck()
            return True
        if answer == "drop":
            self.deck, self.dirty = copy.deepcopy(self.orig), False
            self.update_dirty()
            return True
        return False

    def remove_one(self, r):
        """Remove one copy of this card from the deck (preferably exactly this printing)."""
        cards = [c for c in self.deck["cards"] if c.get("board", "main") == "main"]
        hit = next((c for c in cards if c["sid"] == r["id"]), None) or \
            next((c for c in cards if self.rows.get(c["sid"], {}).get("name") == r["name"]), None)
        if hit is not None:
            decks.add_card(self.deck, hit["sid"], -1, "main")
            self.changed()

    def add(self, r, board="main", exact=False):
        """Add a card to the deck. exact=False: if you own another printing of it, yours goes in."""
        if self.deck is None or r is None:
            return
        if not exact:
            r = self.owned_print(r) or r
        self.rows[r["id"]] = r
        decks.add_card(self.deck, r["id"], 1, board)
        self.changed()

    def drop_out(self, data):
        """Row dragged from the deck list onto the results: one card fewer (commander: removed)."""
        if self.deck is None:
            return
        sid, board = data.split("|", 1)
        if board == "commander":
            if sid in self.deck.get("commanders", []):
                self.deck["commanders"].remove(sid)
                self.changed()
            return
        decks.add_card(self.deck, sid, -1, board)
        self.changed()

    def change(self, sid, board, d):
        """Deck list row: d cards more/fewer (-999 = remove entirely; commander: removed)."""
        if self.deck is None or sid is None:
            return
        if board == "commander":
            if d < 0 and sid in self.deck.get("commanders", []):
                self.deck["commanders"].remove(sid)
                self.changed()
            return
        decks.add_card(self.deck, sid, d, board)
        self.changed()

    def move(self, sid, old, new):
        if old == "commander":
            self.deck["commanders"].remove(sid)
            decks.add_card(self.deck, sid, 1, new)
        else:
            n = next((c["count"] for c in self.deck["cards"] if c["sid"] == sid and c.get("board", "main") == old), 0)
            decks.add_card(self.deck, sid, -n, old)
            decks.add_card(self.deck, sid, n, new)
        self.changed()

    def set_commander(self, r, exact=False):
        if self.deck is None or r is None:
            return
        if not exact:
            r = self.owned_print(r) or r
        self.rows[r["id"]] = r
        cm = self.deck.setdefault("commanders", [])
        if r["id"] in cm:
            return
        for c in self.deck["cards"]:  # take it out of the deck if already in it
            if c["sid"] == r["id"] and c.get("board", "main") == "main":
                decks.add_card(self.deck, r["id"], -1, "main")
                break
        if len(cm) >= 2 or (cm and "Partner" not in (r.get("keywords") or "") and "Background" not in
                            (r.get("type_line") or "") + (self.rows.get(cm[0], {}).get("oracle_text") or "")):
            cm.clear()  # second commander only with Partner/Background
        cm.append(r["id"])
        if self.format != "commander":
            self.set_format("commander", run=False)
        self.changed()
        self.results.run()  # color identity has changed

    def rename(self, name):
        name = (name or "").strip()
        if self.deck is not None and name and name != self.deck["name"]:
            self.name = self.deck["name"] = name
            self.changed()

    def set_format(self, key, run=True):
        self.format = key
        if self.deck is not None:
            self.deck["format"] = key
            if run:
                self.changed()
                self.results.run()

    def delete(self):
        if qdialogs.question(tr("Delete deck"), tr(f"Delete “{self.deck['name']}” for good?"),
                             yes=tr("Delete"), no=tr("Cancel"), danger=True):
            self.dirty = False
            self.page.delete_deck(self.orig)

    # --- Alternatives and upgrades (chips at the top, results on the left) ---
    def _extra_chips(self):
        out = []
        if self.alt is not None:
            out.append((tr("Alternatives to"), [(self.alt["name"], self.clear_alternatives)], self.clear_alternatives))
        if self.upgrade_mode:
            out.append((tr("Upgrades"), [(tr("from your collection"), lambda: self.set_upgrades(False))],
                        lambda: self.set_upgrades(False)))
        return out

    def _extra_set(self, state):
        alt, kinds, upgrade = state
        self.alt, self.alt_kinds, self.upgrade_mode = alt, set(kinds), upgrade
        self._sync_extra()

    def _sync_extra(self):
        self.fill_list()  # highlight of the alternatives card
        self.changed_sig.emit()

    def set_alternatives(self, r):
        """⇄ on a deck list row: cards by similarity to r – again (same card) = off."""
        if r is None or (self.alt is not None and self.alt["id"] == r["id"]):
            self.clear_alternatives()
            return
        self.alt, self.alt_kinds, self.upgrade_mode = r, set(), False
        self._sync_extra()
        self.results.run()

    def clear_alternatives(self):
        if self.alt is None:
            return
        self.alt, self.alt_kinds = None, set()
        self._sync_extra()
        self.results.run()

    def set_alt_owned(self, which):
        """Alternatives: from your collection (mine), only missing ones (missing) or all cards (all)."""
        if which in ("mine", "missing", "all") and which != self.alt_owned:
            self.alt_owned = which
            self.page.ctrl.settings["deck_alt_owned"] = which
            self.page.ctrl.settings_changed()
            self.results.run()
            self.changed_sig.emit()

    def suggest_names(self, text, limit=8):
        """Autocomplete: card names that start with or contain the typed text (own cards first).
        Syntax (k:, t: …) and too-short input: nothing."""
        q = (text or "").strip()
        if len(q) < 2 or not carddb.exists() or re.search(r"\w[:<>=]", q):
            return []
        try:
            rows = carddb.search(q, limit=40, sort="relevance", no_tokens=True, one_per_name=True)
        except Exception:  # noqa: BLE001 – search not possible (e.g. special characters)
            return []
        low = q.lower()
        hits = [r for r in rows if low in r["name"].lower()]
        owned = self.page.owned_name
        hits.sort(key=lambda r: (not r["name"].lower().startswith(low), not owned.get(r["name"]), len(r["name"])))
        return [{"name": r["name"], "owned": bool(owned.get(r["name"])), "sid": r["id"]} for r in hits[:limit]]

    def pick_name(self, name):
        """Name picked from autocomplete: show the card (own printing, if any) and search
        for it."""
        if not name:
            return
        found = carddb.by_names([name]).get(name.lower()) if carddb.exists() else None
        if found is not None:
            r = self.owned_print(found) or found
            self.show_card(r)
        self.bar.search.blockSignals(True)
        self.bar.search.setText(name)
        self.bar.search.blockSignals(False)
        self.bar.changed.emit()
        self.changed_sig.emit()

    def toggle_alt_kind(self, key):
        (self.alt_kinds.discard if key in self.alt_kinds else self.alt_kinds.add)(key)
        self.results.run()
        self.changed_sig.emit()

    def set_upgrades(self, on):
        self.upgrade_mode = bool(on)
        if on:
            self.alt = None
        self._sync_extra()
        self.results.run()

    # --- Detail view ---
    def show_card(self, r):
        """Show a card (card database row) large with all info. Pinned: the new card opens in the
        comparison beside it."""
        if r is None:
            return
        self.rows.setdefault(r["id"], r)
        if not self.detail.isVisible():
            self.detail.show()
            self.detail.show_row(self.lib.row_from_db(r))
            self.actions.set_card(r)
            self.sync_slider()
            self.lib.update_marks()
            self.detail_changed.emit()
            return
        if self.card is not None and self.card["id"] == r["id"] and self.detail.row is not None:
            return
        if self.lib.detail_pinned and self.detail.row is not None:
            self.open_beside(r)
            return
        self.close_compare(animate=False)  # other card: the comparison belongs to the old one
        self.detail.show_row(self.lib.row_from_db(r))
        self.actions.set_card(r)
        self.lib.update_marks()
        self.detail_changed.emit()

    def set_upgrade_layout(self, on):
        """Upgrade mode: comparison (left, out) and detail (right, in) are fixed – no pin, no ⇄,
        no closing. Afterwards back to normal."""
        self.upgrade_layout = bool(on)
        for btn in (self.detail.pin_btn, self.compare.pin_btn, self.detail.close_btn, self.compare.close_btn):
            btn.setVisible(not on)
        if on:
            self.detail.pin_btn.setChecked(False)
        elif self.compare.isVisible():
            self.close_compare()
        self.detail_changed.emit()

    def show_upgrade_pair(self, out_r, in_r):
        """A swap row was selected: on the left the card going out, on the right the new one – both large."""
        if in_r is None:
            return
        self.rows.setdefault(in_r["id"], in_r)
        if out_r is not None:
            self.rows.setdefault(out_r["id"], out_r)
        self.detail.show()
        self.detail.show_row(self.lib.row_from_db(in_r))
        self.actions.set_card(in_r)
        if out_r is not None:
            self.compare.show_row(self.lib.row_from_db(out_r))
            self.cmp_actions.set_card(out_r)
        else:  # free slot: the panel stays in place (nothing jumps), just without a card
            self.compare.show_empty(tr("free slot"))
            self.cmp_actions.set_card(None)
        self.slide.open()
        self.lib.update_marks()
        self.sync_slider()
        self.detail_changed.emit()

    def open_beside(self, r):
        """Pinned: card in the compare slot beside the pinned detail view."""
        if self.compare.isVisible() and self.compare.row is not None and self.compare.row["sid"] == r["id"]:
            return
        opening = not self.compare.isVisible()
        self.compare.show_row(self.lib.row_from_db(r))
        self.cmp_actions.set_card(r)
        if opening:
            self.slide.open()
            self.sync_slider()
        self.lib.update_marks()
        self.detail_changed.emit()

    def close_detail(self):
        """✕ of the detail view: detail (and comparison) close; a click on a card brings them back."""
        if not self.detail.isVisible():
            return
        self.detail.pin_btn.setChecked(False)  # closed: pin released
        self.slide.close(False)
        self.detail.hide()
        self.actions.set_card(None)
        self.sync_slider()
        self.detail_changed.emit()

    def swap_detail(self):
        """⇄: comparison and detail swap contents; afterwards the card in the detail view is pinned."""
        a, b = self.compare.row, self.detail.row
        if a is None or b is None or not self.compare.isVisible():
            return
        ca, cb = self.cmp_actions.card, self.actions.card
        self.detail.show_row(a)
        self.compare.show_row(b)
        self.actions.set_card(ca)
        self.cmp_actions.set_card(cb)
        self.lib.update_marks()
        self.detail.pin_btn.setChecked(True)
        self.detail_changed.emit()

    def show_compare(self, pr):
        """Another printing from "All printings": slides in on the left beside the detail view."""
        if self.detail.row is not None and pr["id"] == self.detail.row["sid"]:
            self.close_compare()
            return
        row = self.lib.row_for_print(pr)
        r = row.get("db") or carddb.cards_by_ids({pr["id"]}).get(pr["id"])
        if r is None:
            return
        self.rows.setdefault(r["id"], r)
        opening = not self.compare.isVisible()
        self.compare.show_row(self.lib.row_from_db(r))
        self.cmp_actions.set_card(r)
        if opening:
            self.slide.open()
            self.sync_slider()
        self.lib.update_marks()
        self.detail_changed.emit()

    def _cmp_closed(self):
        self.lib.update_marks()

    def close_compare(self, animate=True):
        if not self.compare.isVisible():
            return
        self.slide.close(False)
        self.sync_slider()
        self.detail_changed.emit()

    # --- Cards per row (slider) ---
    def area(self):
        if not self.detail.isVisible():
            return "full"  # detail view closed: more room for cards
        return "compare" if self.compare.isVisible() and not self.slide.closing else "detail"

    def area_columns(self, area):
        saved = self.page.ctrl.settings.get("deck_cols_area") or {}
        lo = self.START[area]
        return max(lo, min(lo + 5, int(saved.get(area, 3))))

    def columns(self):
        return self.cols_slider.value

    def sync_slider(self):
        area = self.area()
        lo = self.START[area]
        self.cols_slider.lo, self.cols_slider.hi = lo, lo + 5
        self.cols_slider.set_value(self.area_columns(area), emit=False)

    def set_columns(self, n):
        saved = dict(self.page.ctrl.settings.get("deck_cols_area") or {})
        saved[self.area()] = int(n)
        self.page.ctrl.settings["deck_cols_area"] = saved
        self.page.ctrl.settings_changed()
        self.cols_slider.set_value(int(n), emit=False)
        self.detail_changed.emit()

    def use_print(self, r):
        """Switch all copies of this card in the deck to this printing."""
        if r is None:
            return
        self.rows.setdefault(r["id"], r)
        self._swap({s: r["id"] for s, row in self.rows.items() if row["name"] == r["name"] and s != r["id"]})

    def owned_print(self, r):
        """Own printing of the same card (row) – or None."""
        if r is None or self.page.owned_id.get(r["id"]):
            return None
        sid = self.page.owned_pref.get(r["name"])
        if not sid:
            return None
        row = self.rows.get(sid) or carddb.cards_by_ids({sid}).get(sid)
        if row is not None:
            self.rows[sid] = row
        return row

    def swappable(self):
        if self.deck is None:
            return {}
        out = {}
        for sid in decks.all_ids(self.deck):
            r = self.rows.get(sid)
            if r is not None and not self.page.owned_id.get(sid) and self.page.owned_pref.get(r["name"]):
                out[sid] = self.page.owned_pref[r["name"]]
        return out

    def use_owned_prints(self):
        """Switch to own printings – pinned ones only after asking (the pin moves along)."""
        m = self.swappable()
        pins = [s for s in m if self.pinned(s)]
        if pins:
            ans = qdialogs.ask(tr("Heads up"),
                               tr("One of these cards is pinned to a specific print.") if len(pins) == 1 else
                               tr(f"{len(pins)} of these cards are pinned to a specific print."),
                               [("free", tr("Only unpinned ones"), ""), ("all", tr("Switch all"), "active")],
                               informative=tr("Switched pinned cards stay pinned – then to your print."))
            if ans is None:
                return
            if ans == "free":
                m = {s: v for s, v in m.items() if s not in pins}
        self._swap(m)

    def pin_print(self, sid, new_sid):
        """Pin on the deck row: new_sid = use exactly this printing (pinned) · "" = any printing again."""
        if self.deck is None:
            return
        pins = [s for s in self.deck.get("pinned") or [] if s != sid]
        if new_sid:
            if new_sid != sid:
                self._swap({sid: new_sid}, toast=False, refresh=False)
            pins.append(new_sid)
        self.deck["pinned"] = sorted(set(pins))
        self.changed()

    def _swap(self, mapping, toast=True, refresh=True):
        """Swap printings in the deck {old ID: new ID} (counts are merged)."""
        if not mapping or self.deck is None:
            return
        new_rows = carddb.cards_by_ids(set(mapping.values()) - set(self.rows))
        self.rows.update(new_rows)
        cm = self.deck.get("commanders", [])
        self.deck["commanders"] = [mapping.get(s, s) for s in cm]
        cards = []
        for c in self.deck["cards"]:
            sid = mapping.get(c["sid"], c["sid"])
            hit = next((x for x in cards if x["sid"] == sid and x.get("board", "main") == c.get("board", "main")), None)
            if hit:
                hit["count"] += c["count"]
            else:
                cards.append(dict(c, sid=sid))
        self.deck["cards"] = cards
        if self.deck.get("pinned"):
            self.deck["pinned"] = sorted({mapping.get(s, s) for s in self.deck["pinned"]})
        if refresh:
            self.changed()
        if toast:
            self.page.toast(tr(f"{len(mapping)} cards switched to your own printings."))

    # --- Export ---
    def export_clipboard(self):
        QtGui.QGuiApplication.clipboard().setText(decks.to_text(self.deck, self.rows))
        self.page.toast(tr("Deck list copied – paste it e.g. into Moxfield under “Import”."))

    def _to_export(self, key):
        """Go to the Import/Export tab – save first so the current state arrives there."""
        if self.deck is None:
            return
        if self.dirty:
            self.save_deck()
        did = (self.orig or self.deck)["id"]
        self.page.ctrl.go_export(key, deck_id=did, deck_ids=[did])


# ---------- Bent°Corner suggestion: new decks from your own collection ----------
class SuggestPage(QtCore.QObject):
    """Pick the kind of deck (commander or 60 cards), then the best candidates from your collection – commander with
    EDHREC data (estimated offline), 60-card decks purely from the card data."""
    KINDS = [("commander", "Commander")] + suggest.FORMATS_60
    changed = QtCore.Signal()

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.status = _Text()
        self.picking = False
        self.picks = []      # [[on?, row, tooltip]]
        self.ideas = []      # [(idea, kind)]
        self.pool = []
        self.token, self._prog = 0, None
        self._poll = QtCore.QTimer(self, interval=250, timeout=self._progress)

    def _set_status(self, t):
        self.status.setText(t)
        self.changed.emit()

    def start(self):
        self.picking = False
        self._clear()
        self._set_status(tr("Pick the kind of deck above – Bent°Corner then finds the five best candidates from your collection. Commander suggestions use EDHREC (online), otherwise an estimate."))

    def _clear(self):
        self.ideas = []
        self.changed.emit()

    def _progress(self):
        if self._prog:
            done, total = self._prog
            self._set_status(tr(f"Checking your commander candidates on EDHREC … ({done}/{total})"))

    def _fill_picks(self, cands):
        self.picks = [[i < suggest.CHECK_MAX, x["row"], tr(f"Offline estimate: {round(x['offline'] * 100)} %")]
                      for i, x in enumerate(cands)]
        self.changed.emit()

    def toggle_pick(self, i):
        if not 0 <= i < len(self.picks):
            return
        on = not self.picks[i][0]
        if on and sum(1 for p in self.picks if p[0]) >= suggest.CHECK_MAX:
            self._set_status(tr(f"At most {suggest.CHECK_MAX} at once – remove another one first."))
            return
        self.picks[i][0] = on
        self.changed.emit()

    def check(self, chosen=None):
        """Check the chosen commanders (at most 5) on EDHREC – in the background. chosen: own choice (search)."""
        if not isinstance(chosen, list):
            chosen = [r for on, r, _ in self.picks if on]
        chosen = chosen[:suggest.CHECK_MAX]
        if not chosen:
            self._set_status(tr("Pick at least one commander."))
            return
        self._clear()
        self.token += 1
        token = self.token
        online = self.page.ctrl.settings.get("deck_online", True)
        pool = self.pool
        self._prog = (0, len(chosen))
        self._progress()

        def work():
            ideas = suggest.commander_ideas(pool, chosen, online=online,
                                            progress=lambda d, t: setattr(self, "_prog", (d, t)),
                                            stop=lambda: token != self.token)
            return pool, ideas
        self._poll.start()
        run_async(self, work, lambda res, err: self.show(token, "commander", res, err))

    def run(self, kind):
        self._clear()
        self.token += 1
        token = self.token
        owned = self.page.free_owned()  # cards in built decks are used up
        if not owned:
            self._set_status(tr("Your collection is still empty – scan or import some cards first.")
                             if not self.page.owned_id else
                             tr("All your cards are already in built decks."))
            return
        self._set_status(tr("Looking for suggestions in your collection …"))
        self._prog = None
        if kind == "commander":  # pre-sort offline first (no request), then check at most 5 more closely
            self.pool = suggest.owned_rows(owned)
            cands = suggest.commander_candidates(self.pool)
            if not cands:
                self.picking = False
                self._set_status(tr("No legendary creatures in your collection – no commander, no suggestion."))
                return
            self._fill_picks(cands[:30])
            self.picking = True
            self.check()
            return
        self.picking = False

        def work():
            pool = suggest.owned_rows(owned)
            return pool, suggest.sixty_ideas(pool, kind)
        self._poll.start()
        run_async(self, work, lambda res, err: self.show(token, kind, res, err))

    def show(self, token, kind, res, err):
        if token != self.token:
            return
        self._poll.stop()
        self._prog = None
        self.page.background_done(tr("Deck suggestions are ready"),
                                  tr("Bent°Corner went through your collection – the suggestions are waiting in the Decks tab."), "suggest")
        if err or not res:
            self._set_status(tr(f"Suggestions not possible: {err}"))
            return
        self.pool, ideas = res
        if not ideas:
            from collection import brew
            why = brew.diagnose_html(self.page.free_owned(), self.pool, kind)
            self._set_status((tr("Your collection doesn't have enough for that yet.") if kind != "commander" else
                              tr("No legendary creatures in your collection – no commander, no suggestion."))
                             + ("<br>" + why if why else ""))
            return
        self.ideas = [(idea, "commander" if kind == "commander" else "sixty") for idea in ideas]
        self._set_status(tr("The best candidates from your collection – “Create deck” builds a rough draft from your cards only (plus basic lands) that you then refine in the deck builder."))

    @staticmethod
    def idea_view(idea, kind):
        """-> (title HTML, info HTML, image row) of an idea."""
        if kind == "commander":
            r = idea["row"]
            title = f"<b style='font-size:15px'>{html.escape(r['name'].split(' // ')[0])}</b>"
            cov = round(idea["coverage"] * 100)
            if idea.get("online"):
                info = (tr(f"You already have <b>{cov} %</b> of its typical deck ({idea['owned']} cards)")
                        + "<br>" + tr(f"{len(idea['missing'])} cards missing, about {eur(idea['missing_eur'])}"))
            else:
                info = tr(f"offline estimate: {idea['owned']} matching cards in its colors")
            return title, info, r
        title = f"<b style='font-size:15px'>{html.escape(suggest.idea_title(idea))}</b>"
        info = (tr(f"{idea['count']} matching cards in your collection")
                + (("<br>" + tr(f"Theme: {idea['theme_n']} cards")) if idea.get("theme") else ""))
        return title, info, idea["cards"][0] if idea["cards"] else None

    def pick(self, i, kind):
        if not 0 <= i < len(self.ideas):
            return
        idea, page = self.ideas[i][0], self.page
        if kind == "commander":
            cmdr, cards = suggest.draft_commander(idea["row"], self.pool,
                                                  online=page.ctrl.settings.get("deck_online", True))
            d = decks.new_deck(cmdr["name"].split(" // ")[0].split(",")[0] + " · " + tr("Suggestion"), "commander")
            d["commanders"] = [cmdr["id"]]
        else:
            cards = suggest.draft_sixty(idea, self.pool)
            d = decks.new_deck(suggest.idea_title(idea) + " · " + tr("Suggestion"), kind)
        for r, n in cards:
            decks.add_card(d, r["id"], n)
        if page.folder:
            d["folder"] = page.folder
        page.decks.append(d)
        page.save()
        page.open_deck(d)
        page.toast(tr("Rough draft created – from your cards only. Fill gaps and fine-tune in the deck builder (⬆ Upgrades, ⇄ Alternatives)."), 4500)


# ---------- Compare two decks ----------
class CompareSide:
    """One side of the comparison: chosen deck, key data, complete list by card type (rows for QML)."""

    def __init__(self, view):
        self.view, self.deck, self.info, self.rows = view, None, "", []

    def fill(self, a, counts, other, rows):
        deck = self.deck
        fmt = dict(decks.FORMATS).get(deck.get("format"), deck.get("format"))
        br = f" · {tr('Bracket')} <b style='color:#ffb347'>{a['bracket']}</b>" if deck.get("format") == "commander" \
            else ""
        cm = [rows[s]["name"] for s in deck.get("commanders", []) if s in rows]
        self.info = (f"<span style='color:#aab1c8'>{fmt} · {a['count']} {tr("Cards")} · {eur(a['price'])}{br}"
                     + (f"<br>{tr('Commander')}: <b>{' + '.join(cm)}</b>" if cm else "") + "</span>")
        by_name = {r["name"]: r for r in rows.values()}
        groups = {}
        for name, n in counts.items():
            r = by_name.get(name)
            t = decks._type(r) if r else "Other"
            groups.setdefault(t, []).append((name, n, r))
        out = []
        for key, label in decks.TYPE_ORDER + [("Other", "Sonstige")]:
            items = groups.get(key)
            if not items:
                continue
            out.append({"head": True, "count": "", "name": f"{tr(label)} ({sum(n for _, n, _ in items)})",
                        "price": "", "kind": "", "tip": ""})
            for name, n, r in sorted(items, key=lambda t: t[0]):
                o = other.get(name, 0)
                price = (r or {}).get("eur") if (r or {}).get("eur") is not None else (r or {}).get("eur_foil")
                kind = "only" if not o else ("diff" if o != n else "same")
                out.append({"head": False, "count": f"{n}", "price": eur(price) if price is not None else "–",
                            "name": name + (f"   ({o}× " + tr("in the other") + ")" if o and o != n else ""),
                            "kind": kind, "tip": tr("Only in this deck") if kind == "only" else ""})
        self.rows = out


class CompareView(QtCore.QObject):
    """Two decks side by side: lists left/right (switchable), in the middle properties and a rough
    strength comparison. There are no real win rates for private decks – the comparison is an estimate from tempo,
    interaction, card advantage and power."""
    changed = QtCore.Signal()

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.a, self.b = CompareSide(self), CompareSide(self)
        self.all_decks, self.verdict, self.note = [], "", ""
        self.power, self.stats = [], []  # [(label, A, B, text A, text B, better: "high"|"low"|None)]

    def open(self, a, b=None):
        self.all_decks = sorted(self.page.decks, key=lambda d: (d.get("folder") or "", d["name"].lower()))
        if b is None:  # default: another version of the same deck, otherwise the last edited one
            fam = a.get("version_of") or a["id"]
            others = [d for d in self.page.decks if d["id"] != a["id"]]
            others.sort(key=lambda d: (0 if (d.get("version_of") or d["id"]) == fam else 1, -d.get("updated", 0)))
            b = others[0] if others else a
        self.a.deck, self.b.deck = a, b
        self.refresh()

    def pick(self, which, i):
        if 0 <= i < len(self.all_decks):
            (self.a if which == "a" else self.b).deck = self.all_decks[i]
            self.refresh()

    def index_of(self, which):
        d = (self.a if which == "a" else self.b).deck
        return next((i for i, x in enumerate(self.all_decks) if d is not None and x["id"] == d["id"]), 0)

    @staticmethod
    def counts(d, rows):
        out = {}
        for s in d.get("commanders", []):
            if s in rows:
                out[rows[s]["name"]] = out.get(rows[s]["name"], 0) + 1
        for c in d["cards"]:
            if c.get("board", "main") == "main" and c["sid"] in rows:
                n = rows[c["sid"]]["name"]
                out[n] = out.get(n, 0) + c["count"]
        return out

    @staticmethod
    def scores(a, n_combos):
        """Rough scores 0..10 for the strength comparison (estimated from the list only)."""
        r = a["roles"]
        tempo = max(0.0, min(10.0, 10 - (a["avg_mv"] - 2.0) * 3 + r["Ramp"] * 0.25))
        inter = min(10.0, (r["Removal"] + 2 * r["Board Wipes"]) * 0.35)
        adv = min(10.0, r["Kartenziehen"] * 0.4)
        power = min(10.0, a.get("bracket", 2) * 1.6 + len(a["game_changers"]) * 0.6 + n_combos * 1.2
                    + r["Tutoren"] * 0.4)
        return tempo, inter, adv, power

    def refresh(self):
        da, db = self.a.deck, self.b.deck
        if da is None or db is None:
            return
        rows = carddb.cards_by_ids(decks.all_ids(da) | decks.all_ids(db)) if carddb.exists() else {}
        own = (self.page.owned_id, self.page.owned_name)
        aa, ab = decks.analyze(da, rows, *own), decks.analyze(db, rows, *own)
        ca, cb = self.counts(da, rows), self.counts(db, rows)
        self.a.fill(aa, ca, cb, rows)
        self.b.fill(ab, cb, ca, rows)
        combo_n = []
        for d in (da, db):
            cm, main = combos.deck_lists(d, rows)
            hit = combos.cached_find(cm, main) if d.get("format") == "commander" else None
            combo_n.append(len((hit or {}).get("included") or []))
        sa, sb = self.scores(aa, combo_n[0]), self.scores(ab, combo_n[1])
        names = (tr("Tempo"), tr("Interaction"), tr("Card advantage"), tr("Power"))
        one = (lambda v: f"{v:.1f}".replace(".", ",")) if i18n.LANG == "de" else (lambda v: f"{v:.1f}")
        self.power = [(n, x, y, one(x), one(y), "high") for n, x, y in zip(names, sa, sb)]
        weights = (0.3, 0.25, 0.2, 0.25)
        diff = sum(w * (x - y) for w, x, y in zip(weights, sa, sb))
        chance = 1 / (1 + math.exp(-diff * 0.9))
        same = sum(min(ca.get(n, 0), cb.get(n, 0)) for n in set(ca) | set(cb))
        lead = (tr("A looks stronger") if chance > 0.55 else tr("B looks stronger") if chance < 0.45
                else tr("pretty even"))
        self.verdict = (
            f"<span style='font-size:30px; font-weight:800; color:#f2f2f2'>{chance * 100:.0f} %</span>"
            f"<span style='font-size:18px; color:#6c7390'>&nbsp; : &nbsp;</span>"
            f"<span style='font-size:30px; font-weight:800; color:#9a9a9a'>{(1 - chance) * 100:.0f} %</span><br>"
            f"<b>{lead}</b><br><span style='color:#8a91a8'>"
            + tr(f"{same} cards in common · {aa['count'] - same} only in A · {ab['count'] - same} only in B")
            + "</span>")

        def row(label, x, y, fmt=lambda v: str(round(v)), better=None):
            return (label, x, y, fmt(x), fmt(y), better)
        self.stats = [
            row(tr("Bracket"), aa["bracket"], ab["bracket"]),
            row(tr("Value"), aa["price"], ab["price"], eur),
            row(tr("Ø mana value"), aa["avg_mv"], ab["avg_mv"], lambda v: f"{v:.2f}".replace(".", ","), "low"),
            row(tr("Lands"), aa["lands"], ab["lands"]),
            row(decks.role_label("Ramp"), aa["roles"]["Ramp"], ab["roles"]["Ramp"], better="high"),
            row(tr("Card draw"), aa["roles"]["Kartenziehen"], ab["roles"]["Kartenziehen"], better="high"),
            row(decks.role_label("Removal"), aa["roles"]["Removal"], ab["roles"]["Removal"], better="high"),
            row(tr("Board wipes"), aa["roles"]["Board Wipes"], ab["roles"]["Board Wipes"], better="high"),
            row(tr("Tutors"), aa["roles"]["Tutoren"], ab["roles"]["Tutoren"], better="high"),
            row(tr("Game Changers"), len(aa["game_changers"]), len(ab["game_changers"])),
            row(tr("Combos (Spellbook)"), combo_n[0], combo_n[1]),
            row(tr("Creatures"), aa["types"].get("Creature", 0), ab["types"].get("Creature", 0)),
            row(tr("Im Besitz"), aa["owned"], ab["owned"], better="high"),
        ]
        self.note = tr("The strength comparison is a rough estimate from the list: tempo (mana value, ramp), interaction (removal, wipes), card advantage (card draw) and power (bracket, Game Changers, combos, tutors). There are no real win rates for your own decks – play style, opponents and luck matter more at the table. Combos only if Spellbook has already checked the deck (deck info).")
        self.changed.emit()


# ---------- Page ----------
class DeckPage(QtCore.QObject):
    """The "Decks" page: overview of all decks (tiles, folders) or one deck in the editor, comparison, suggestion.
    view: overview | editor | compare | suggest."""
    changed = QtCore.Signal()

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.ctrl = ctrl
        self.decks = decks.load()
        self.loader = ImageLoader(self, keep=60)   # large preview images (480 px, ~1.3 MB each)
        self.owned_id, self.owned_name, self.owned_pref, self.owned_variants = {}, {}, {}, {}
        self.view = "overview"
        self._save = QtCore.QTimer(self, singleShot=True, interval=600, timeout=self.save)
        self.folder = ctrl.settings.get("deck_folder")  # None = all decks, "" = no folder, otherwise folder name
        self.tiles = []  # [(deck, info)] or ({"_tile": "new"}, {})
        self.init_folders()
        self.editor = DeckEditor(self)
        self.compare = CompareView(self)
        self.suggest = SuggestPage(self)

    def _show(self, view):
        self.view = view
        self.changed.emit()

    # --- Display ---
    def enter(self):
        self.update_owned()
        if self.view == "editor" and self.editor.deck is not None:
            self.editor.refresh()
        else:
            self.fill_overview()

    def update_owned(self):
        coll = self.ctrl.collection
        self.owned_id = coll.owned()
        names, per, var = {}, {}, {}
        for it in coll.items:
            names[it["name"]] = names.get(it["name"], 0) + it.get("count", 1)
            v = var.setdefault(it["name"], {})  # per name: count per language/foil (chips like in the library)
            k = (it.get("lang") or "en", bool(it.get("foil")))
            v[k] = v.get(k, 0) + it.get("count", 1)
            per.setdefault(it["name"], {})
            sid = scryfall_id(it["id"])
            per[it["name"]][sid] = per[it["name"]].get(sid, 0) + it.get("count", 1)
        self.owned_name = names
        self.owned_per = per  # {name: {sid: count}} – for "free" (minus built decks)
        self._usage_key = None
        self.owned_variants = {n: [(c, lang, foil) for (lang, foil), c in sorted(d.items(), key=lambda x: -x[1])]
                               for n, d in var.items()}
        # per card name the own printing you have the most of (for import/adding)
        self.owned_pref = {n: max(d, key=d.get) for n, d in per.items()}

    # --- Built decks: their cards are "used up" ---
    def built_usage(self, exclude=None):
        """{card name: [(deck name, count)]} of all decks marked as built (except exclude = deck ID)."""
        built = [d for d in self.decks if d.get("built")]
        key = tuple((d["id"], d.get("updated", 0), len(d["cards"])) for d in built)
        if key != getattr(self, "_usage_key", None):
            ids = set()
            for d in built:
                ids |= decks.all_ids(d)
            rows = carddb.cards_by_ids(ids) if ids and carddb.exists() else {}
            usage = []
            for d in built:
                names = collections.Counter()
                for c in d["cards"]:
                    if c["sid"] in rows:
                        names[rows[c["sid"]]["name"]] += c["count"]
                for sid in d.get("commanders", []):
                    if sid in rows:
                        names[rows[sid]["name"]] += 1
                usage.append((d["id"], d["name"], names))
            self._usage, self._usage_key = usage, key
        out = {}
        for did, dname, names in self._usage:
            if did == exclude:
                continue
            for n, k in names.items():
                out.setdefault(n, []).append((dname, k))
        return out

    def free_owned(self, exclude=None):
        """Own cards {sid: count}. Cards in built decks do NOT count as used up (for now, user request
        2026-10-09) – the deck builder only shows which real deck they are in (built_usage)."""
        if not self.ctrl.settings.get("built_consumes", False):
            return dict(self.owned_id)
        free = dict(self.owned_id)
        per = getattr(self, "owned_per", {})
        for name, uses in self.built_usage(exclude).items():
            need = sum(k for _, k in uses)
            for sid in per.get(name, {}):
                take = min(free.get(sid, 0), need)
                free[sid] = free.get(sid, 0) - take
                need -= take
                if need <= 0:
                    break
        return {sid: n for sid, n in free.items() if n > 0}

    def set_built(self, deck, on):
        """Mark a deck as "actually built" (or not) – saved without touching the deck changes."""
        for d in (deck, self.editor.deck, self.editor.orig):
            if d is not None and d.get("id") == deck.get("id"):
                d["built"] = bool(on)
        self.save()
        self._usage_key = None
        if self.view == "editor":
            self.editor.built = bool(on)
            self.editor.refresh()
        else:
            self.fill_overview()
        self.toast(tr("Marked as built – these cards now count as in use.") if on else
                   tr("No longer marked as built – the cards are free again."), 3000)

    def fill_overview(self):
        """Decks of the selected folder as tiles, with "+ New deck" first."""
        ids = set()
        for d in self.decks:
            ids |= decks.all_ids(d)
        rows = carddb.cards_by_ids(ids) if carddb.exists() else {}
        folders = self.folders()
        if self.folder not in (None, LOOSE) and self.folder not in folders:
            self.folder = None
        if self.folder is None:
            shown = list(self.decks)
        elif self.folder == LOOSE:
            shown = [d for d in self.decks if not d.get("folder")]
        else:
            shown = [d for d in self.decks if d.get("folder") == self.folder]
        items = [({"_tile": "new"}, {})]
        # custom order (set by dragging) first, all others by "last edited"
        order = {i: n for n, i in enumerate(self.ctrl.settings.get("deck_order") or [])}
        for d in sorted(shown, key=lambda d: (order.get(d["id"], 1e9), -d.get("updated", 0))):
            a = decks.analyze(d, rows, self.owned_id, self.owned_name)
            items.append((d, {"count": a["count"], "size": a["size"], "price": a["price"],
                              "identity": a["identity"] or "".join(c for c in "WUBRG" if a["colors"].get(c)),
                              "bracket": a["bracket"] if d.get("format") == "commander" else None,
                              "art_row": self._art_row(d, rows)}))
        self.tiles = items
        self.changed.emit()

    @staticmethod
    def _art_row(d, rows):
        """Tile image = cover card (own choice > commander > suggestion), like the share image."""
        from collection import deckshare
        cov = deckshare.cover_rows(d, rows)
        return cov[0] if cov else next((rows[c["sid"]] for c in d["cards"] if c["sid"] in rows), None)

    # --- Folders ---
    def folders(self):
        """Folder names (shared by all games); "Commander" only in games that have the format – or when a deck of
        this game is in it."""
        used = {d["folder"] for d in self.decks if d.get("folder")}
        names = set(self.ctrl.settings.get("deck_folders") or []) | used
        if "commander" not in dict(decks.FORMATS) and "Commander" not in used:
            names.discard("Commander")
        return sorted(names, key=str.lower)

    def init_folders(self):
        """Once: create the "Standard" and "Commander" folders and sort existing decks into them by format."""
        st = self.ctrl.settings
        if st.get("deck_folders_init"):
            return
        st["deck_folders_init"] = True
        st["deck_folders"] = sorted(set(st.get("deck_folders") or []) | {"Standard", "Commander"})
        cols = dict(st.get("deck_folder_colors") or {})
        cols.setdefault("Standard", "#62f2ff")
        cols.setdefault("Commander", "#ffb347")
        st["deck_folder_colors"] = cols
        moved = False
        for d in self.decks:
            if not d.get("folder") and d.get("format") in ("commander", "standard"):
                d["folder"] = "Commander" if d["format"] == "commander" else "Standard"
                moved = True
        if moved:
            self.save()
        self.ctrl.settings_changed()

    def add_folder(self, name):
        st = self.ctrl.settings
        st["deck_folders"] = sorted(set(st.get("deck_folders") or []) | {name})
        cols = dict(st.get("deck_folder_colors") or {})
        if name not in cols:  # next color still free
            used = set(cols.values())
            cols[name] = next((c for c, _ in FOLDER_COLORS if c not in used), FOLDER_COLORS[len(cols) % 9][0])
        st["deck_folder_colors"] = cols
        self.ctrl.settings_changed()
        self.fill_overview()
        return name

    def set_color(self, key, color):
        cols = dict(self.ctrl.settings.get("deck_folder_colors") or {})
        cols[key] = color
        self.ctrl.settings["deck_folder_colors"] = cols
        self.ctrl.settings_changed()
        self.fill_overview()

    def set_folder(self, key):
        self.folder = key
        self.ctrl.settings["deck_folder"] = key
        self.ctrl.settings_changed()
        self.fill_overview()

    def new_folder(self, deck=None):
        """New folder (with a deck: put it in right away)."""
        name, ok = qdialogs.get_text_ok(tr("New folder"), tr("Folder name:"))
        name = (name or "").strip()
        if not ok or not name:
            return None
        self.add_folder(name)
        if deck is not None:
            self.move_deck(deck, name)
        return name

    def rename_folder(self, key, name):
        if not name or name == key:
            return
        for d in self.decks:
            if d.get("folder") == key:
                d["folder"] = name
        st = self.ctrl.settings
        st["deck_folders"] = sorted((set(st.get("deck_folders") or []) - {key}) | {name})
        cols = dict(st.get("deck_folder_colors") or {})
        if key in cols:
            cols[name] = cols.pop(key)
        st["deck_folder_colors"] = cols
        if self.folder == key:
            self.folder = st["deck_folder"] = name
        self.ctrl.settings_changed()
        self.save()
        self.fill_overview()

    def delete_folder(self, key):
        for d in self.decks:
            if d.get("folder") == key:
                d.pop("folder", None)
        st = self.ctrl.settings
        st["deck_folders"] = [f for f in st.get("deck_folders") or [] if f != key]
        cols = dict(st.get("deck_folder_colors") or {})
        cols.pop(key, None)
        st["deck_folder_colors"] = cols
        if self.folder == key:
            self.folder = st["deck_folder"] = None
        self.ctrl.settings_changed()
        self.save()
        self.fill_overview()

    def move_deck(self, deck, folder):
        for d in self.decks:
            if d["id"] == deck["id"]:
                if folder:
                    d["folder"] = folder
                else:
                    d.pop("folder", None)
        ed = self.editor
        if ed.deck is not None and ed.deck["id"] == deck["id"]:  # open deck: update the copy in the editor too
            if folder:
                ed.deck["folder"] = folder
            else:
                ed.deck.pop("folder", None)
        self.save()
        self.fill_overview()
        self.toast(tr(f"“{deck['name']}” → {folder}") if folder else tr(f"“{deck['name']}” without folder"))

    def folder_submenu(self, menu, deck):
        sub = menu.addMenu(tr("Move to folder"))
        for f in self.folders():
            act = sub.addAction(f"📁 {f}", lambda f=f: self.move_deck(deck, f))
            act.setEnabled(deck.get("folder") != f)
        if deck.get("folder"):
            sub.addAction(tr("No folder"), lambda: self.move_deck(deck, None))
        sub.addSeparator()
        sub.addAction(tr("New folder …"), lambda: self.new_folder(deck))

    # --- Versions ---
    def duplicate_version(self, deck):
        """Copy as a new version ("Deck v2") in the same folder – for trying things out, the original stays."""
        new = copy.deepcopy(deck)
        m = re.match(r"^(.*?)\s+v(\d+)$", deck["name"])
        base, n = (m.group(1), int(m.group(2)) + 1) if m else (deck["name"], 2)
        taken = {d["name"] for d in self.decks}
        while f"{base} v{n}" in taken:
            n += 1
        now = time.time()
        new.update(id=decks.new_deck("")["id"], name=f"{base} v{n}", created=now, updated=now,
                   version_of=deck.get("version_of") or deck["id"])
        self.decks.append(new)
        self.save()
        self.fill_overview()
        self.toast(tr(f"New version: “{new['name']}”"))
        return new

    def compare_with(self, deck, parent=None):
        """Open the comparison: this deck on the left, another version or the last edited one on the right."""
        if len(self.decks) < 2:
            self.toast(tr("Comparing needs a second deck."))
            return
        if self.view == "editor" and not self.editor.maybe_leave():
            return
        self.save()
        self.update_owned()
        self.compare.open(deck)
        self._show("compare")

    def ask_delete(self, deck):
        if qdialogs.question(tr("Delete deck"), tr(f"Delete “{deck['name']}” for good?")):
            from system import datastore
            datastore.trash_put("deck", deck["name"], deck)  # 30 days in the trash
            self.decks = [d for d in self.decks if d["id"] != deck["id"]]
            self.save()
            self.fill_overview()

    def show_overview(self):
        if self.view == "editor" and not self.editor.maybe_leave():
            return
        self.save()
        self.fill_overview()
        self._show("overview")

    def open_deck(self, deck):
        self.update_owned()
        if not carddb.exists():
            self.toast(tr("For deck building, please load the card database first (Settings → Card data)."))
        self._show("editor")
        self.editor.open(deck)

    def background_done(self, title, text, view):
        """Background work done: if you aren't looking at the page right now, the "Decks" tab gets a dot and
        there is a Windows notification – you can keep using the app normally in the meantime."""
        ctrl = self.ctrl
        stream = getattr(ctrl, "stream", None)
        window = getattr(getattr(ctrl, "shell", None), "window", None)
        if stream is not None and stream.page == "decks" and self.view == view and window is not None \
                and window.isActive():
            return
        if stream is not None:
            stream.set_badge("decks", True)
        tray = getattr(ctrl, "tray", None)
        if tray is not None:
            try:
                tray.notify(title, text)
            except Exception:  # noqa: BLE001 – notifications are a bonus
                pass

    def show_suggest(self):
        import games
        if "brew" not in games.current().deck_extras:   # deck suggestions exist only for Magic (so far)
            self.toast(tr(f"Deck suggestions from your collection are coming later for {games.current().name} – here's an empty deck to build yourself."))
            self.new_deck()
            return
        if self.view == "editor" and not self.editor.maybe_leave():
            return
        self.suggest.start()
        self._show("suggest")

    def new_deck(self):
        d = decks.new_deck(tr("New deck"))
        if self.folder:
            d["folder"] = self.folder
        self.decks.append(d)
        self.save()
        self.open_deck(d)

    def import_deck(self):
        """The "Import" tab → deck list."""
        self.ctrl.show_import("deck")

    def import_from(self, name, fmt, text, fits=None):
        """Create a deck from a text list and open it (Import tab). -> deck or None. fits: the list as a whole is the
        open game's (collection.importguard) – otherwise a line with a set this game doesn't know is never matched
        by its name alone (a Magic "Forest (ONE) 276" never becomes the Yu-Gi-Oh! field spell)."""
        from collection import importguard
        if not carddb.exists():
            self.toast(tr("Importing needs the card database (Settings → Card data)."))
            return None
        parsed = decks.parse_text(text)
        if fits is None:
            fits = importguard.verdict([(n, s or "", num or "", "") for _, n, s, num, *_ in parsed])["fits"]
        found = carddb.by_names([n for _, n, *_ in parsed])
        # not found as a whole: maybe "Name SET NUMBER" without brackets (Pokémon TCG Live) – try the name alone
        trailing = {n: m for _, n, *_ in parsed if n.lower() not in found for m in [decks._TRAILING_PRINT.match(n)] if m}
        short = {n: m.group(1) for n, m in trailing.items()}
        if short:
            more = carddb.by_names(list(short.values()))
            for n, s in short.items():
                if s.lower() in more:
                    found[n.lower()] = more[s.lower()]
        by_id = carddb.cards_by_ids({n for _, n, *_ in parsed if n.lower() not in found})   # "4xOP01-016"
        for sid, r in by_id.items():
            found[sid.lower()] = r
        d = decks.new_deck(name.strip() or tr("Imported deck"), fmt)
        if self.folder:  # into the currently open folder
            d["folder"] = self.folder
        missing = []
        for count, name, set_code, number, board in parsed:
            r = found.get(name.lower()) if importguard.name_only_ok(set_code, fits) else None
            if set_code and number:  # exact printing, if given
                exact = carddb.search("", limit=1, set_code=set_code, texts=[("name", name, False)])
                exact = [x for x in exact if x["number"] == number] or exact
                r = exact[0] if exact else r
            elif name in trailing and r is not None:   # "Pikachu ex OBF 63": abbreviation -> set, then the number
                code = carddb.set_by_abbr(trailing[name].group(2))
                num = carddb.norm_number(trailing[name].group(3))
                exact = carddb.search("", limit=20, set_code=code, texts=[("name", r["name"], False)]) if code else []
                r = next((x for x in exact if carddb.norm_number(x["number"]) == num), r)
            if r is None:
                missing.append(name)
                continue
            if not (set_code and number) and not self.owned_id.get(r["id"]) and self.owned_pref.get(r["name"]):
                r = carddb.cards_by_ids({self.owned_pref[r["name"]]}).get(self.owned_pref[r["name"]]) or r
            if board == "commander":
                d["commanders"].append(r["id"])
            else:
                decks.add_card(d, r["id"], count, board)
        d["updated"] = time.time()   # filled just now (newest for lists sorted by "last changed")
        self.decks.append(d)
        self.save()
        self.open_deck(d)
        if missing:
            self.toast((tr("1 card not found: ") if len(missing) == 1 else tr(f"{len(missing)} cards not found: ")) + ", ".join(missing[:8])
                       + (" …" if len(missing) > 8 else ""), 7000)
        return d

    def delete_deck(self, deck):
        from system import datastore
        datastore.trash_put("deck", deck["name"], deck)  # 30 days in the trash
        self.decks = [d for d in self.decks if d["id"] != deck["id"]]
        self.editor.deck = None
        self.save()
        self.show_overview()

    def save_later(self):
        self._save.start()

    def save(self):
        try:
            decks.save(self.decks)
        except OSError:
            pass

    def toast(self, text, ms=4500):
        shell = getattr(self.ctrl, "shell", None)
        if shell is not None:
            shell.show_toast(text)

    # --- Images ---
    def art(self, r):
        """Large preview image of a card (loads into the cache in the background) – None while it is loading."""
        if r is None:
            return None
        local = THUMBS / f"{r['id']}_en_n.jpg"
        url = r.get("img_normal") or library.image_url(r["set_code"], r["number"], "en", "normal")
        return self.loader.get(f"{r['id']}_en_n480", 480, local, url, local)


# ---------- Which decks is a card in? (badges on cards in the library and deck builder) ----------
_USAGE = {"key": None, "map": {}}


def card_usage(ctrl):
    """{card name: [(deck name, count, built?)]} across all decks (main deck, commander, sideboard) –
    cached as long as nothing changes in the decks. Keyed like the deck rules count copies (games.<g>.deck_name_key:
    the name – or the card ID in games where different cards share names)."""
    page = getattr(ctrl, "deck_page", None)
    all_decks = page.decks if page is not None else decks.load()
    key = tuple((d["id"], d.get("updated", 0), len(d.get("cards") or []), bool(d.get("built")), d.get("name"))
                for d in all_decks)
    if key == _USAGE["key"]:
        return _USAGE["map"]
    ids = set()
    for d in all_decks:
        ids |= decks.all_ids(d)
    rows = carddb.cards_by_ids(ids) if ids and carddb.exists() else {}
    out = {}
    name_key = decks._G.deck_name_key
    for d in all_decks:
        names = collections.Counter()
        for c in d.get("cards") or []:
            if c["sid"] in rows and c.get("board", "main") != "maybe":
                names[name_key(rows[c["sid"]])] += c["count"]
        for sid in d.get("commanders", []):
            if sid in rows:
                names[name_key(rows[sid])] += 1
        for n, k in names.items():
            out.setdefault(n, []).append((d["name"], k, bool(d.get("built"))))
    _USAGE["key"], _USAGE["map"] = key, out
    return out


def usage_chips(ctrl, row, exclude=None):
    """For QML: [{"deck", "n", "built"}] of the decks containing this card (row: the card, exclude = deck name, e.g.
    the open deck)."""
    key = decks._G.deck_name_key(row)
    return [{"deck": d, "n": n, "built": b} for d, n, b in card_usage(ctrl).get(key, []) if d != exclude]
