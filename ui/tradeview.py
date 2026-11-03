"""The "Trade" page.

The sidebar on the left: you at the top (name, edit, import, export), your friends below (collapsible). The eye on a
friend marks cards he/she has in the trade view (in your lists).
Click your name: your wishlists and trade lists; click a list: the list on the left, the library on the right
(the same view as the library) – drag & drop cards in or back.
Click a friend: Trade · Wants · Library at the top (the selected tab stays when switching friends):
  Trade     what you get / give – selectable and deselectable, shareable as an image
  Wants     what he/she is looking for
  Library   his/her library in the library view, with extra chips

Everything is drawn in Qt Quick (qml/pages/TradePage.qml, qtrade.py). Only the logic lives here; the only widgets left
are the library views in the trade page (TradeLibrary, DetailSide) – they go away with the library rework.
"""
import time

from PySide6 import QtCore

from cards import carddb
from collection import decks
import games
from collection import trade
from system import userprofile
from system.i18n import tr
from scanner.common import image_rel
from ui.librarycore import DetailHost, LibraryCore
from collection.tradelib import Browser, offer_image
from ui import qdialogs


def eur(v):
    return "–" if v is None else f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------- Card backs as chips ----------
_backs = {}


def back_pm(back, height):
    key = (back, height)
    if key not in _backs:
        _backs[key] = userprofile.back_pixmap(back, height, border="#0b0e1a")
        if len(_backs) > 200:
            _backs.pop(next(iter(_backs)))
    return _backs[key]


# ---------- Card source: a friend's library (for the library view) ----------

def pinned_rows(rows, pinned, have_any=()):
    """The friend's rows for my pinned wants (pinned: {(name, set, number): n}). The exact version first, then other
    versions only for what is still missing – the wanted count is used up across all of them, never counted twice.
    Names in have_any are already in the trade as "any version"."""
    need = {}
    for (nm, _, _), n in pinned.items():
        need[nm] = need.get(nm, 0) + n
    rows = [r for r in rows if r["name"] not in have_any]
    key = lambda r: (r["name"], r["set"].lower(), r["number"])
    out = []
    for exact in (True, False):
        for r in rows:
            if (key(r) in pinned) != exact:
                continue
            n = min(r["count"], pinned[key(r)] if exact else need.get(r["name"], 0), need.get(r["name"], 0))
            if n > 0:
                need[r["name"]] -= n
                out.append(dict(r, count=n, pinned_name=True, pinned_match=exact))
    return out

class FriendSource:
    """Provides a friend's cards the same way as your own collection (groups/owned/summary/items/rev), so the
    library view (search, advanced search, sliders, detail, comparison) can show them unchanged."""

    def __init__(self, d):
        self.rev = 0
        cards = [c for c in d.get("cards") or [] if len(c) > 5]
        db = carddb.by_prints([(c[0], c[1]) for c in cards]) if carddb.exists() else {}
        self._groups, self.items = [], []
        merged = {}
        for c in cards:
            r = db.get((str(c[0]).lower(), str(c[1])))
            sid = r["id"] if r else f"{c[0]}-{c[1]}"
            key = (sid, c[2] or "en", bool(c[3]))
            g = merged.get(key)
            if g is None:
                g = merged[key] = {
                    "id": f"{sid}_0", "sid": sid, "name": c[5], "set": str(c[0]).upper(), "number": str(c[1]),
                    "rarity": (r or {}).get("rarity"), "lang": c[2] or "en", "foil": bool(c[3]), "count": 0,
                    "items": [], "last": 0, "img": image_rel(str(c[0]), str(c[1]), 0),
                    "eur": (r or {}).get("eur"), "eur_foil": (r or {}).get("eur_foil"),
                    "url": games.current().card_url(c[0], c[1])}
            g["count"] += int(c[4] or 1)
        self._groups = list(merged.values())
        self.items = [{"lang": g["lang"], "count": g["count"]} for g in self._groups]

    def groups(self):
        return [dict(g) for g in self._groups]

    def owned(self):
        out = {}
        for g in self._groups:
            out[g["sid"]] = out.get(g["sid"], 0) + g["count"]
        return out


class WantsSource(FriendSource):
    """What a friend is looking for – as cards (per name the newest printing from the database)."""

    def __init__(self, d):
        self.rev = 0
        wants = d.get("wants") or []
        db = carddb.by_names([w[0] for w in wants]) if carddb.exists() else {}
        self._groups = []
        for w in wants:
            r = db.get(str(w[0]).lower())
            sc, num = ((r["set_code"], r["number"]) if r else ("", ""))
            sid = r["id"] if r else f"want-{w[0]}"
            self._groups.append({"id": f"{sid}_0", "sid": sid, "name": w[0], "set": sc.upper(), "number": num,
                                 "rarity": (r or {}).get("rarity"), "lang": "en", "foil": False,
                                 "count": int(w[1] or 1), "items": [], "last": 0,
                                 "img": image_rel(sc, num, 0) if r else "", "eur": (r or {}).get("eur"),
                                 "eur_foil": (r or {}).get("eur_foil"),
                                 "url": games.current().card_url(sc, num) if r else None})
        self.items = [{"lang": "en", "count": g["count"]} for g in self._groups]


MIME_CARD = "application/x-bentcorner-tradecard"  # card from the library view into a list
MIME_ENTRY = "application/x-bentcorner-listentry"  # entry back out of a list (= remove)



class TradeLibrary(LibraryCore):
    """The library view in the trade page: with its own card source (friend) or the collection, without set progress.
    chips: [(key, label, check function(row))] as extra filters (drawn in Qt Quick),
    exclusive: pairs that exclude each other."""
    detail_context = "library"

    def __init__(self, ctrl, source=None, modes=("mine",), holders=False):
        super().__init__(ctrl)
        self.source, self.show_holders = source, holders
        self.drag_mime = None
        self.done_btn.hide()
        if "all" not in modes:
            self.mine_btn.hide()
            self.all_btn.hide()
        elif "mine" not in modes:
            self.mine_btn.hide()
        self.chip_defs, self.chip_on, self.chip_excl, self.chip_btns = [], set(), [], {}
        # don't hide lands in the trade page (library default) – friends look for and have lands too
        types = self.bar.sec_types
        types.default_off = ()
        types.reset(emit=False)

    def escape(self):
        if self.compare.isVisible():
            self.close_compare()
        elif self.detail_open:
            self.close_detail()

    def set_chips(self, chips, exclusive=()):
        self.chip_defs, self.chip_excl = chips, [set(x) for x in exclusive]
        self.chip_on &= {k for k, _, _ in chips}
        self.chip_btns = {k: True for k, _, _ in chips}  # which chips exist (qlibrary.extraChips)
        self._apply_chips()

    def _chip(self, key, on):
        if on:
            self.chip_on.add(key)
            for group in self.chip_excl:  # "I'm missing" and "I have it too" exclude each other
                if key in group:
                    self.chip_on -= group - {key}
        else:
            self.chip_on.discard(key)
        self._apply_chips()
        self.refresh()

    def _apply_chips(self):
        tests = [fn for k, _, fn in self.chip_defs if k in self.chip_on]
        self.extra_filter = (lambda r: all(t(r) for t in tests)) if tests else None

    def set_source(self, source):
        self.source = source
        self.seen_rev = -1
        if self.detail_open:
            self.close_detail()


# ---------- List in the list editor ----------
class ListPanel(QtCore.QObject):
    """Entries of a list (wishlist or trade list): add (card from the library view), −/+, remove,
    pin (exactly this version). Signal changed: content changed (list refilled)."""
    changed = QtCore.Signal()

    def __init__(self, page):
        super().__init__(page)
        self.page, self.kind, self.lid = page, "wish", trade.MAIN_WISH
        self.title = self.info = self.hint = ""
        self._last_print = {}

    def set_list(self, kind, lid):
        self.kind, self.lid = kind, lid
        self.fill()

    def entries(self):
        """-> [(key, name, extra, count, entry)]. Wants: one row per version (pinned or any)."""
        if self.kind in ("wish", "custom"):
            out = {}
            for w in trade.wishes([self.lid]):
                key = trade.wish_key(w)
                extra = f"{(w.get('set') or '').upper()} #{w.get('number')}" if w.get("set") else tr("any version")
                e = out.setdefault(key, [key, w["name"], extra, 0, w])
                e[3] += int(w.get("count", 1))
            return [tuple(e) for e in sorted(out.values(), key=lambda e: (e[1], e[2]))]
        out = [(it["uid"], it["name"], f"{str(it.get('set') or '').upper()} #{it.get('number')}"
                + (" · Foil" if it.get("foil") else "") + (f" · {(it.get('lang') or 'en').upper()}"
                                                           if (it.get("lang") or "en") != "en" else ""), n, it)
               for it, n in trade.have_items(self.page.ctrl.collection.items, [self.lid])]
        names = trade.have_print_names(self.lid)
        for key, n in trade.have_prints(self.lid).items():  # printings that aren't in the collection (red)
            sc, num, lang, foil = (key.split("|") + ["", "", "en", "0"])[:4]
            extra = f"{sc.upper()} #{num}" + (" · Foil" if foil == "1" else "") + \
                (f" · {lang.upper()}" if lang != "en" else "")
            out.append((f"p:{key}", names.get(key, key), extra, n, {"missing": True, "set": sc, "number": num,
                                                                     "lang": lang, "foil": foil == "1"}))
        return sorted(out, key=lambda e: (e[1], e[2]))

    def fill(self):
        self.title = next((tr(x["name"]) if x["id"] in (trade.MAIN_WISH, trade.MAIN_HAVE) else x["name"]
                           for x in trade.lists(self.kind) if x["id"] == self.lid), "")
        self.info = tr(f"{sum((e[3] for e in self.entries()))} cards")
        self.hint = (tr("Drag cards here from the library on the right (or double-click). Drag back onto the grid = remove.") if self.kind in ("wish", "custom") else
                     tr("Drag cards here from your collection on the right (or double-click) – at most as many as you have. Drag back onto the grid = remove."))
        self.changed.emit()

    def change(self, key, delta):
        """delta: +1 / -1 / None (= remove entirely)."""
        if self.kind in ("wish", "custom"):
            items = trade.wishes(raw=True)
            mine = [w for w in items if trade.wish_key(w) == key and (w.get("list") or trade.MAIN_WISH) == self.lid]
            if not mine:
                return
            if delta is None or (delta < 0 and sum(int(w.get("count", 1)) for w in mine) <= 1):
                for w in mine:
                    items.remove(w)
            else:
                mine[0]["count"] = max(1, int(mine[0].get("count", 1)) + delta)
            trade.save_wishes(items)
        elif str(key).startswith("p:"):  # not your own printing
            pk = str(key)[2:]
            n = trade.have_prints(self.lid).get(pk, 0)
            trade.set_have_print(self.lid, pk, 0 if delta is None else max(0, n + delta))
        else:
            coll = self.page.ctrl.collection
            it = coll.get(key)
            if it is None:
                return
            n = trade.have_count(it, self.lid)
            n = 0 if delta is None else max(0, min(int(it.get("count", 1)), n + delta))
            if self.lid == trade.MAIN_HAVE:
                coll.update(key, trade=n)
                coll.save()
            else:
                trade.set_have(self.lid, key, n)
        self.fill()

    def toggle_pin(self, key, name, on):
        """Pin on: the version of this card that was dragged in last; pin off: any version."""
        last = self._last_print.get(name)
        if on and last is None:
            return
        trade.set_pinned(key, self.lid, on, *(last or (None, None)))
        self.fill()

    def add_row(self, row):
        """Add a card from the library view (row) – for wants pinned right away (exactly this printing)."""
        if self.kind in ("wish", "custom"):
            sc, num = (row.get("set") or "").lower() or None, row.get("number") or None
            self._last_print[row["name"]] = (sc, num)
            trade.add_wish(row["name"], 1, sc, num, list_id=self.lid)
        else:
            coll = self.page.ctrl.collection
            from collection.collection import scryfall_id
            cands = [it for it in coll.items if scryfall_id(it["id"]) == row.get("sid")
                     and (it.get("lang") or "en") == (row.get("lang") or "en") and bool(it.get("foil")) == bool(row.get("foil"))]
            for it in cands:
                n = trade.have_count(it, self.lid)
                if n < int(it.get("count", 1)):
                    if self.lid == trade.MAIN_HAVE:
                        coll.update(it["uid"], trade=n + 1)
                        coll.save()
                    else:
                        trade.set_have(self.lid, it["uid"], n + 1)
                    break
            else:  # not (or no longer) in the collection: remember as a printing – shows in red
                pk = f"{(row.get('set') or '').lower()}|{row.get('number') or ''}|{row.get('lang') or 'en'}|" \
                     f"{1 if row.get('foil') else 0}"
                trade.set_have_print(self.lid, pk, trade.have_prints(self.lid).get(pk, 0) + 1, row.get("name"))
                if not cands:
                    self.page.toast(tr("Printing not in your library – shown in red in the list."))
        self.fill()


# ---------- Detail view next to a card view ----------
class DetailSide(QtCore.QObject):
    """Clicking a card opens the detail view on the right (as in the library, with comparison and pin) – you
    stay in the same tab. Drawn in Qt Quick."""

    def __init__(self, owner, ctrl, ctx):
        super().__init__(owner)
        self.host = DetailHost(self, ctrl, ctx, on_close=self.close, width_key=f"{ctx}_detail_w")
        self.card, self.cmp = self.host.panel, self.host.compare

    def show(self, db, lang="en", foil=False):
        if not db:
            return
        row = self.host.row_from_db(db)
        row.update(lang=lang or "en", foil=bool(foil))
        self.host.open_detail(row)

    def close(self):
        self.host.hide_detail()




# ---------- Page ----------
class TradePage(QtCore.QObject):
    """Logic of the trade page. View: view = "me" (your lists) | "editor" (one list) | "friend";
    for a friend friend_tab = trade | wants | has | library. host: invisible home of the library views."""
    FRIEND_TABS = (("trade", "Tauschen"), ("has", "Hat"), ("wants", "Sucht"), ("library", "Bibliothek"),
                   ("profile", "Profil"), ("note", "Notiz"))
    CARD_TABS = ("has", "wants", "library")   # tabs with cards: the game toggles choose which games they show
    changed = QtCore.Signal()       # view, friend, tab
    rail_changed = QtCore.Signal()  # left sidebar (profile, friends, selection, expanded/collapsed)
    lists_changed = QtCore.Signal()  # "your lists" overview
    sum_changed = QtCore.Signal()   # calculation in the "Swap" tab

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.ctrl = ctrl
        self.view, self.friend_tab = "me", "trade"
        self.friend_id, self.friend = None, None
        self.foreign = ""   # friend from another game (no switch, plain view): their key
        self.plain = []     # plain view: the game(s) shown (several = mixed); foreign = the first of them
        self.friend_toggles = {}   # friend ID -> games switched on at the top of the friend (this session)
        self.friend_multi = False   # ∞ beside the games: several at once (toggles) – off: one game (exclusive choice)
        self.friend_last = {}       # friend ID -> the game clicked last (stays when ∞ goes off)
        self.rail_compact = not ctrl.settings.get("trade_rail_open", True)
        self.rail_current = None
        self.has_note = self.lib_note = ""
        self.trade_sum, self.can_offer = "", False
        self.list_panel = ListPanel(self)
        self.list_panel.changed.connect(self.list_changed)
        self.get_browser = self._browser("get")
        self.give_browser = self._browser("give")
        # library views (still widgets): list editor, wants, has, library of …, detail in the Swap tab
        self.ed_lib = TradeLibrary(ctrl, modes=("mine", "all"), holders=True)
        self.f_wants = TradeLibrary(ctrl, source=None)
        self.f_has = TradeLibrary(ctrl, source=None)
        self.f_lib = TradeLibrary(ctrl, source=None)
        self.trade_side = DetailSide(self, ctrl, "trade")
        self.alarm_side = DetailSide(self, ctrl, "alarm")

    def _browser(self, key):
        b = Browser(self.ctrl.settings, f"trade_{key}", checkable=True, parent=self)
        b.checks_changed.connect(self.update_trade_sum)
        b.clicked.connect(lambda r: self.trade_side.show(r.get("db"), r.get("lang"), r.get("foil")))
        chips = [("checked", tr("checked only"), lambda r: bool(r.get("checked")))]
        if key == "get":
            chips.insert(0, ("pin", tr("Version"), lambda r: not r.get("pinned_name") or bool(r.get("pinned_match"))))
        b.set_filters(chips)
        return b

    def _show(self, view):
        self.view = view
        self.changed.emit()

    def tab_text(self, key):
        if key == "library":
            return tr(f"{(self.friend or {}).get('name') or '?'}'s library")
        return tr(dict(self.FRIEND_TABS)[key])

    # --- Enter / refresh ---
    def enter(self):
        self.refresh_me()
        self.fill_friends()
        if self.view == "friend" and self.foreign:
            d = self.foreign_file(self.foreign, self.friend_id)
            self.open_foreign(self.foreign, d) if d else self.open_me()
        elif self.view == "friend" and self.friend_id:
            self.open_friend(self.friend_id)
        elif self.view == "editor":
            self.list_panel.fill()
            self.ed_lib.enter()
        else:
            self.open_me()

    def refresh_me(self):
        self.rail_changed.emit()

    def show_tab(self, i):
        """Old interface (price alerts): show your lists."""
        self.open_me()

    def fill_wishes(self):
        if self.view == "me":
            self.lists_changed.emit()
        elif self.view == "editor":
            self.list_panel.fill()

    fill_mine = fill_wishes  # trade lists changed (card details → My lists)

    def holders(self):
        return self.ctrl.trade_holders(force=True)

    def libraries(self):
        """Library views in the trade page (for display settings)."""
        return [self.ed_lib, self.f_lib, self.f_has, self.f_wants]

    def holders_changed(self):
        self.ed_lib.changed.emit()
        if self.view == "editor":
            self.list_panel.fill()

    def active(self):
        return set(self.ctrl.settings.get("trade_active") or [])

    def fill_friends(self):
        if self.foreign:   # friend from another game: their file counts
            if self.foreign_file(self.foreign, self.friend_id) is None:
                self.friend_id = self.friend = None
                self.open_me()
        elif self.friend_id and trade.friend(self.friend_id) is None:
            self.friend_id = self.friend = None
            self.open_me()
        self.rail_changed.emit()

    # --- Sidebar ---
    def toggle_rail(self):
        self.rail_compact = not self.rail_compact
        self.ctrl.settings["trade_rail_open"] = not self.rail_compact
        self.rail_changed.emit()

    def _select(self, fid):
        self.rail_current = fid
        self.rail_changed.emit()

    # --- Your lists ---
    def open_me(self):
        self.foreign = ""
        self._select("me")
        self._show("me")
        self.lists_changed.emit()

    def open_list(self, kind, lid):
        self.list_kind, self.list_id = kind, lid
        self.list_panel.set_list(kind, lid)
        names = kind in ("wish", "custom")   # cards by name/printing (not only your own)
        self.ed_lib.set_mode("all" if names and carddb.exists() else "mine")
        self.ed_lib.mine_btn.setVisible(names)
        self.ed_lib.all_btn.setVisible(names)
        self._show("editor")
        self.ed_lib.enter()

    def list_changed(self):
        self.ed_lib.changed.emit()

    def new_list(self, kind):
        name, ok = qdialogs.get_text_ok(tr("New list"), tr("Name of the list:"))
        if ok and name.strip():
            lid = trade.add_list(kind, name)
            self.open_list(kind, lid)

    def rename_list(self, kind, lid):
        old = next((x["name"] for x in trade.lists(kind) if x["id"] == lid), "")
        name, ok = qdialogs.get_text_ok(tr("Rename"), tr("Name of the list:"), old)
        if ok and name.strip():
            trade.rename_list(kind, lid, name)
            self.lists_changed.emit()

    def show_list_card(self, kind, ent):
        """Entry clicked on the left: card in the detail view on the right (the exact printing, if known)."""
        key, name, _, _, w = ent
        db = None
        if carddb.exists():
            sc = num = None
            if kind in ("wish", "custom") and w.get("set"):
                sc, num = w.get("set"), w.get("number")
            elif kind == "have" and isinstance(w, dict):
                sc, num = w.get("set"), w.get("number")
            if sc and num:
                db = carddb.by_prints([(sc, num)]).get((str(sc).lower(), str(num)))
            if db is None:
                db = carddb.by_names([name]).get(name.lower())
        if db is None:
            return
        row = self.ed_lib.row_from_db(db)
        if isinstance(w, dict):
            row.update(lang=w.get("lang") or "en", foil=bool(w.get("foil")))
        self.ed_lib.show_card_row(row)

    # --- Friends ---
    def set_active(self, fid, on):
        act = self.active()
        (act.add if on else act.discard)(fid)
        self.ctrl.settings["trade_active"] = sorted(act)
        self.ctrl.settings_changed()
        self.ctrl.trade_changed()
        self.rail_changed.emit()

    def rename(self, d):
        name, ok = qdialogs.get_text_ok(tr("Rename"), tr("Name:"), d.get("name") or "")
        if ok and name.strip():
            trade.rename_friend(d["id"], name)
            self.fill_friends()
            if self.friend_id == d["id"]:
                self.open_friend(d["id"])
            self.ctrl.trade_changed()

    def remove(self, d):
        if qdialogs.question(tr("Remove"), tr(f"Remove {d.get('name') or tr('Freund')}'s library? Your own collection stays untouched.")):
            trade.remove_friend(d["id"])
            self.fill_friends()
            self.ctrl.trade_changed()

    def open_friend(self, fid):
        """Friend clicked on the left: Trade · Wants · Library at the top – the last selected tab stays."""
        d = trade.friend(fid)
        if d is None:
            return
        self.foreign, self.plain = "", []
        if getattr(self, "friend_id", None) != fid:   # different friend: no offer being edited anymore, no money
            self.offer_ctx, self.trade_money = None, 0.0
            self.extra_rows = {"get": [], "give": []}   # cards from other games (mixed trade)
        self.friend_id, self.friend = fid, d
        self._select(fid)
        lib = d.get("library")
        if lib is None and d.get("what") == "all":  # older files: the whole collection is in "cards"
            lib = d.get("cards")
        who = d.get("name") or "?"
        # only the library was sent: "Has" would be the same list – show a hint instead
        no_lists = d.get("what") in ("all", "none") or not d.get("cards")
        self.has_note = (tr(f"{who} didn't include any trade lists.") + (
            "\n" + tr(f"All cards are under “{who}'s library”.") if lib else "")) if no_lists else ""
        import games
        gname = games.nick_of(games.current().key)
        self.lib_note = "" if lib is not None else tr(
            f"{who}s {gname}-Bibliothek ist noch leer – sie erscheint hier, sobald {who} sie mit Freunden teilt.")
        self.f_has.set_source(FriendSource(d))
        self.f_lib.set_source(FriendSource({"cards": lib or []}))
        self.f_wants.set_source(WantsSource(d))
        self._show("friend")
        self.show_friend_tab(self.ctrl.settings.get("friend_tab") or "trade", save=False)

    @staticmethod
    def foreign_file(game, fid):
        """Friend file from another game (read, without switching) – or None."""
        from ui import qprofile
        return next((d for d in qprofile.friend_files(game) if d.get("id") == fid), None) if fid else None

    def open_foreign(self, game, d):
        """Show a friend in another game without switching the app: plain view of their cards (qtrade
        friendForeign). The trade in the open game stays as it is."""
        self.foreign, self.friend_id, self.friend = game, d["id"], d
        if game not in self.toggled_games(d["id"]):   # e.g. "open there": exactly that game
            self.friend_toggles[d["id"]] = [game]
        self.plain = [game]
        self._select(f"@{game}:{d['id']}")
        self._show("friend")
        self.show_friend_tab(self.ctrl.settings.get("friend_tab") or "trade", save=False)

    # --- Game toggles at the top of the friend ---
    def friend_games_of(self, fid):
        """The friend's games (they share something there): the open one first, then the others."""
        import games
        cur = games.current().key
        keys = [cur] if trade.friend(fid) is not None else []
        return keys + [k for k, _n, ready in games.GAMES
                       if ready and k != cur and self.foreign_file(k, fid) is not None]

    def toggled_games(self, fid):
        """Switched on – by default the open game (if they share it), otherwise their first game."""
        have = self.friend_games_of(fid)
        on = [k for k in self.friend_toggles.get(fid) or [] if k in have]
        return on or have[:1]

    def toggle_friend_game(self, key):
        fid = self.friend_id
        if not fid or key not in self.friend_games_of(fid):
            return
        on = self.toggled_games(fid)
        if not self.friend_multi:   # one game: the click chooses it, the one before goes off
            if on == [key]:
                return
            self.friend_last[fid] = key
            self.friend_toggles[fid] = [key]
            self.apply_friend_mode()
            return
        if key in on:
            if len(on) == 1:   # one game always stays on
                return
            on.remove(key)
        else:
            on.append(key)
            self.friend_last[fid] = key
        self.friend_toggles[fid] = on
        self.apply_friend_mode()

    def set_friend_multi(self, multi):
        """Multi-game view on: all their games at once (Oliver, review .101 – a2), the games become toggles. Off: only
        one stays – the one clicked last, else the first switched on."""
        self.friend_multi = bool(multi)
        fid = self.friend_id
        if not fid:
            return
        if self.friend_multi:
            self.friend_toggles[fid] = list(self.friend_games_of(fid))
            self.apply_friend_mode()
            return
        on = self.toggled_games(fid)
        if len(on) > 1:
            last = self.friend_last.get(fid)
            self.friend_toggles[fid] = [last if last in on else on[0]]
            self.apply_friend_mode()

    def _wants_plain(self, fid):
        import games
        if trade.friend(fid) is None:   # they share nothing in the open game
            return True
        return self.friend_tab in self.CARD_TABS and self.toggled_games(fid) != [games.current().key]

    def apply_friend_mode(self):
        """Full view of the open game – or the plain view (other game, several games mixed), from tab + toggles."""
        fid = self.friend_id
        if not fid:
            return
        if not self._wants_plain(fid):
            if self.foreign:
                self.open_friend(fid)
            else:
                self.changed.emit()
            return
        on = self.toggled_games(fid)
        shown = on if self.friend_tab in self.CARD_TABS else on[:1]
        d = next((x for x in (self.foreign_file(g, fid) for g in shown) if x is not None), None)
        if d is None:
            return
        self.plain, self.foreign, self.friend = list(shown), shown[0], d
        self._show("friend")

    def reopen_friend(self, fid, game):
        """After a game switch: stay with the same friend – now in the new game, if they share something there."""
        if game in self.friend_games_of(fid):
            self.friend_toggles[fid] = [game]
        if trade.friend(fid) is not None:
            self.open_friend(fid)
            return True
        on = self.toggled_games(fid)
        d = self.foreign_file(on[0], fid) if on else None
        if d is None:
            return False
        self.open_foreign(on[0], d)
        return True

    def show_friend_tab(self, key, save=True):
        keys = [k for k, _ in self.FRIEND_TABS]
        key = key if key in keys else "trade"
        self.friend_tab = key
        if save:
            self.ctrl.settings["friend_tab"] = key
            self.ctrl.settings_changed()
        if self.friend_id and (self.foreign or self._wants_plain(self.friend_id)):
            self.apply_friend_mode()   # plain view (other/several games) – or back to the full one
            if self.foreign:
                self.changed.emit()
                return
        fill = {"trade": self.fill_trade, "wants": self.fill_wants, "has": self.fill_has, "library": self.fill_flib,
                "profile": lambda: None, "note": lambda: None}[key]
        if not ((key == "has" and self.has_note) or (key == "library" and self.lib_note)):
            fill()  # hint instead of a view: nothing to fill
        self.changed.emit()

    # --- Data ---
    def owned_names(self):
        out = {}
        for it in self.ctrl.collection.items:
            out[it["name"]] = out.get(it["name"], 0) + it.get("count", 1)
        return out

    def deck_missing(self):
        dl = decks.load()
        sids = {c["sid"] for d in dl for c in d.get("cards") or []} | {s for d in dl for s in d.get("commanders") or []}
        rows = carddb.cards_by_ids(sids) if carddb.exists() else {}
        return trade.deck_needs(dl, rows, self.owned_names())

    def all_wanted(self, any_only=False):
        """All wants (all wishlists + missing deck cards if enabled), minus what you already have.
        any_only: only "any version" (pinned ones count separately when trading)."""
        owned = self.owned_names()
        out = {}
        for w in trade.wishes():
            if any_only and w.get("set"):
                continue
            out[w["name"]] = out.get(w["name"], 0) + int(w.get("count", 1))
        if self.ctrl.settings.get("wish_decks", True):
            try:
                for name, d in self.deck_missing().items():
                    out[name] = max(out.get(name, 0), d["need"])
            except Exception:
                pass
        return {n: k - owned.get(n, 0) for n, k in out.items() if k - owned.get(n, 0) > 0}

    def friend_rows(self, d, counts=None):
        cards = [c for c in d.get("cards") or [] if len(c) > 5 and (counts is None or c[5] in counts)]
        db = carddb.by_prints([(c[0], c[1]) for c in cards]) if carddb.exists() else {}
        rows, left = [], dict(counts or {})
        for c in cards:
            n = int(c[4] or 1)
            if counts is not None:
                n = min(n, left.get(c[5], 0))
                if n <= 0:
                    continue
                left[c[5]] -= n
            r = db.get((str(c[0]).lower(), str(c[1])))
            price = None
            if r:
                price = r.get("eur_foil") if c[3] and r.get("eur_foil") is not None else r.get("eur")
            rows.append({"key": f"{c[0]}|{c[1]}|{c[2]}|{c[3]}", "name": c[5], "set": str(c[0]).upper(),
                         "number": str(c[1]), "lang": c[2] or "en", "foil": bool(c[3]), "count": n, "price": price,
                         "db": r, "rarity": (r or {}).get("rarity"), "tags": []})
        return rows

    def my_rows(self, pairs):
        from collection.collection import price as item_price, scryfall_id
        db = carddb.cards_by_ids({scryfall_id(it["id"]) for it, _ in pairs}) if carddb.exists() else {}
        return [{"key": it.get("uid") or id(it), "name": it["name"], "set": str(it.get("set") or "").upper(),
                 "number": str(it.get("number") or ""), "lang": it.get("lang") or "en", "foil": bool(it.get("foil")),
                 "count": n, "price": item_price(it), "db": db.get(scryfall_id(it["id"])), "rarity": it.get("rarity"),
                 "tags": []} for it, n in pairs]

    # --- Trade ---
    def pinned_wants(self):
        """{(name, set, number): count} of pinned wants (minus exactly this printing in the collection)."""
        have = {}
        for it in self.ctrl.collection.items:
            k = (it["name"], str(it.get("set") or "").lower(), str(it.get("number") or ""))
            have[k] = have.get(k, 0) + int(it.get("count", 1))
        out = {}
        for w in trade.wishes():
            if w.get("set"):
                k = (w["name"], str(w["set"]).lower(), str(w.get("number") or ""))
                out[k] = out.get(k, 0) + int(w.get("count", 1))
        return {k: n - have.get(k, 0) for k, n in out.items() if n - have.get(k, 0) > 0}

    def fill_trade(self):
        d = getattr(self, "friend", None)
        if d is None:
            return
        pinned = self.pinned_wants()
        pinned_names = {k[0] for k in pinned}
        want = {n: k for n, k in self.all_wanted(any_only=True).items()}
        my_have = trade.have_items(self.ctrl.collection.items)
        res = trade.proposal(self.ctrl.collection.items, want, d, self.owned_names(), {}, my_have)
        get = self.friend_rows(d, counts={n: k for n, k, _ in res["get"]})
        have_any = {r["name"] for r in get}
        get += pinned_rows(self.friend_rows(d, counts={n: 99 for n in pinned_names}), pinned, have_any)
        left = {n: k for n, k, _ in res["give"]}
        pairs = []
        for it, n in my_have:
            k = min(n, left.get(it["name"], 0))
            if k > 0:
                pairs.append((it, k))
                left[it["name"]] -= k
        give = self.my_rows(pairs)
        for r in get + give:
            r["checked"] = True
        extra = getattr(self, "extra_rows", None) or {"get": [], "give": []}
        get += [dict(r) for r in extra["get"]]
        give += [dict(r) for r in extra["give"]]
        who = d.get("name") or "?"
        # Orbit's Core (no prices, legal 03.11.): by name instead of by price
        order = (lambda r: -(r["price"] or 0)) if self.priced() else (lambda r: (r["name"].lower(), r.get("set") or ""))
        self.get_browser.set_rows(sorted(get, key=order),
                                  tr(f"{who} has nothing from your wishlists."))
        self.give_browser.set_rows(sorted(give, key=order),
                                   tr(f"{who} doesn't want anything from your lists.") if d.get("wants") else
                                   tr(f"{who} didn't send a wishlist."))
        self.update_trade_sum()

    def add_other(self, game, side, card):
        """Put a card from another game into the trade (side "get": from the friend, "give": from me).
        card: [set, number, language, foil, count, name]. -> text for the message."""
        import games
        self.extra_rows = getattr(self, "extra_rows", None) or {"get": [], "give": []}
        key = f"{game}|{card[0]}|{card[1]}|{card[2]}|{card[3]}"
        rows = self.extra_rows[side]
        r = next((r for r in rows if r["key"] == key), None)
        if r is not None:
            r["count"] += 1
        else:
            db = carddb.by_prints([(card[0], card[1])], game=game).get((str(card[0]).lower(), str(card[1])))
            price = None
            if db:
                price = db.get("eur_foil") if card[3] and db.get("eur_foil") is not None else db.get("eur")
            rows.append({"key": key, "name": card[5] or f"{str(card[0]).upper()} #{card[1]}",
                         "set": str(card[0]).upper(), "number": str(card[1]), "lang": card[2] or "en",
                         "foil": bool(card[3]), "count": 1, "price": price, "db": db, "rarity": (db or {}).get("rarity"),
                         "tags": [games.SHORT.get(game, game.upper())], "game": game, "checked": True})
        self.fill_trade()
        return tr(f"{card[5]} ({games.nick_of(game)}) is in trade – tab “Swap”")

    def priced(self):
        """Prices in the trade – not in Orbit's Core (no € anywhere there, legal 03.11.)."""
        from system import orbit
        return orbit.prices_on(self.ctrl.settings)

    def update_trade_sum(self):
        get = self.get_browser.checked_rows()
        give = self.give_browser.checked_rows()
        gs = sum((r["price"] or 0) * r["count"] for r in get)
        vs = sum((r["price"] or 0) * r["count"] for r in give)
        money = float(getattr(self, "trade_money", 0.0) or 0.0)   # + = I pay extra
        diff = gs - vs - money
        self.can_offer = bool(get or give)
        if not self.get_browser.all_rows and not self.give_browser.all_rows:
            self.trade_sum = tr("Nothing matches right now.")
            self.sum_changed.emit()
            return
        if not self.priced():   # Orbit's Core: only the cards, no balance, no money
            def cards(rows):
                n = sum(r["count"] for r in rows)
                return tr("1 card") if n == 1 else tr(f"{n} cards")
            self.trade_sum = (tr(f"You get {cards(get)} · You give {cards(give)}")
                              + f"<span style='color:#8a91a8'>  ·  {tr("only checked cards")}</span>")
            self.sum_changed.emit()
            return
        bal = tr("even") if abs(diff) < 1 else (tr(f"you get {eur(diff)} more") if diff > 0
                                                         else tr(f"you give {eur(-diff)} more"))
        cash = (f" · {tr("you pay")} {eur(money)}" if money > 0 else f" · {tr("you get")} {eur(-money)}") \
            if abs(money) >= 0.01 else ""
        self.trade_sum = (f"<b>{tr("You get")}</b> {eur(gs)} · <b>{tr("You give")}</b> {eur(vs)}{cash} · "
                          f"<span style='color:#62f2ff'>{bal}</span>"
                          f"<span style='color:#8a91a8'>  ·  {tr("only checked cards")}</span>")
        self.sum_changed.emit()

    def current_ticket(self):
        """Trade ticket (offer) for the ticked cards – the same one as long as the selection and amount of money don't
        change. When revising an offer (counter-offer), same trade ID, next version."""
        from collection import ticket
        d = getattr(self, "friend", None)
        if d is None:
            return None
        prof = userprofile.ensure(self.ctrl.settings)
        give, get = self.give_browser.checked_rows(), self.get_browser.checked_rows()
        ctx = getattr(self, "offer_ctx", None) or {}
        money = float(getattr(self, "trade_money", 0.0) or 0.0) if self.priced() else 0.0   # Core: no money
        sig = (d.get("id"), tuple(tuple(ticket._card(r)) for r in give), tuple(tuple(ticket._card(r)) for r in get),
               money, ctx.get("x"), ctx.get("n"))
        if getattr(self, "_ticket_sig", None) != sig:
            self._ticket_sig = sig
            self._ticket = ticket.new((prof.get("id"), prof.get("name") or tr("Me")), (d.get("id"), d.get("name") or "?"),
                                      give, get, trade_id=ctx.get("x"), version=int(ctx.get("n") or 0) + 1,
                                      money=money)
        return self._ticket

    def set_money(self, value):
        """Amount of money in the trade (€): positive = I pay extra, negative = I receive money."""
        self.trade_money = float(value or 0)
        self.update_trade_sum()

    def share_offer(self):
        """'Share as ticket': offer (or counter-offer) as a ticket image – and remembered under "Trade offers"."""
        from collection import offers
        d = getattr(self, "friend", None)
        if d is None:
            return
        t = self.current_ticket()
        offers.record_sent(t)
        self.offer_ctx = None
        self.show_ticket(t)
        self.ctrl.trade_offers_changed()

    def show_ticket(self, t):
        """Ticket image in Import/Export → Trade offer (copy for WhatsApp, save as PNG)."""
        from collection import ticket
        prof = userprofile.ensure(self.ctrl.settings)
        me_id = prof.get("id")
        sd = ticket.side(t, me_id)
        give, get, partner = sd if sd else (t.get("a") or [], t.get("b") or [], t.get("o") or ["", ""])
        friend = trade.friend(partner[0]) or {}
        db = carddb.by_prints([(c[0], c[1]) for c in give + get]) if carddb.exists() else {}

        import games

        def rows(cards):
            out = []
            for c in cards:
                g = ticket.card_game(c, t)
                if g != ticket.game_of(t):
                    r = carddb.by_prints([(c[0], c[1])], game=g).get((str(c[0]).lower(), str(c[1])))
                    p = None if r is None else (r.get("eur_foil") if c[3] and r.get("eur_foil") is not None else r.get("eur"))
                    out.append({"name": f"{(c[5] if len(c) > 5 and c[5] else (r or {}).get('name') or '?')} · "
                                        f"{games.SHORT.get(g, g.upper())}",
                                "set": str(c[0]).upper(), "number": str(c[1]), "count": int(c[4] or 1), "price": p,
                                "lang": c[2] or "en", "foil": bool(c[3])})
                    continue
                r = db.get((str(c[0]).lower(), str(c[1])))
                p = None if r is None else (r.get("eur_foil") if c[3] and r.get("eur_foil") is not None else r.get("eur"))
                out.append({"name": (c[5] if len(c) > 5 and c[5] else (r or {}).get("name")) or "?",
                            "set": str(c[0]).upper(), "number": str(c[1]), "count": int(c[4] or 1), "price": p,
                            "lang": c[2] or "en", "foil": bool(c[3])})
            return out
        img = offer_image((prof.get("name") or tr("Me"), prof.get("back")), (partner[1] or "?", friend.get("back")),
                          rows(get), rows(give), t, priced=self.priced())
        from collection import collectibles
        collectibles.archive(t, "shown", img=img)
        self.ctrl.go_export("offer", img=img)

    def book_offer(self, answer=None):
        """'Book directly' (without a ticket): actually trade the ticked cards (collection, session "Trade with …")."""
        t = self.current_ticket()
        if t is None:
            return None
        t = dict(t, k="f")
        prefer = {i: r["key"] for i, r in enumerate(r for r in self.give_browser.checked_rows() if not r.get("game"))}
        return self.book_ticket(t, answer=answer, prefer=prefer)

    def receive_ticket(self, t, answer=None):
        """Scanned ticket: offer -> file under "Trade offers" (reply there); completion -> book."""
        import games
        from collection import offers
        from collection import ticket
        me = userprofile.ensure(self.ctrl.settings)
        sd = ticket.side(t, me.get("id"))
        if sd is None:
            names = " ⇄ ".join(x for x in ((t.get("f") or ["", ""])[1], (t.get("o") or ["", ""])[1]) if x)
            qdialogs.info(tr("Trade ticket"), tr(f"This ticket ({names}) wasn't issued to you."))
            return None
        g = ticket.game_of(t)
        bad = [x for x in ticket.games_in(t) if not any(c["key"] == x and c["ready"] for c in games.choices())]
        if bad:
            qdialogs.info(tr("Trade ticket"), tr(f"This ticket is (also) for {games.name_of(bad[0])} – this version can't handle that yet."))
            return None
        if g != games.current().key and ticket.kind(t) == "o":   # offer from another game: file it there
            if not any(c["key"] == g and c["ready"] for c in games.choices()):
                qdialogs.info(tr("Trade ticket"), tr(f"This ticket is for {games.name_of(g)} – this version can't do that yet."))
                return None
            self.toast(tr(f"Ticket for {games.name_of(g)} – switching game …"))
            self.ctrl.switch_game(g, then=lambda: self.ctrl.trade_page.receive_ticket(t, answer=answer))
            return None
        if ticket.kind(t) == "o" and sd[2] == (t.get("f") or ["", ""]):   # offer from the other party
            o = offers.record_received(t, sd[2])
            self.toast(tr(f"Trade offer from {sd[2][1] or '?'} received – Orbit → Trade offers"))
            self.ctrl.trade_offers_changed(open_folder=True)
            return o
        if ticket.kind(t) == "o":   # own offer scanned again: just remember it
            offers.record_sent(t)
            self.ctrl.trade_offers_changed(open_folder=True)
            return offers.get(t.get("x") or t["id"])
        return self.book_ticket(t, answer=answer)

    def book_ticket(self, t, answer=None, prefer=None, lists=(True, True)):
        """Book a completed trade – after a confirmation with an overview and the checkboxes "remove from trade list /
        remove from wishlist". answer (for tests): "book" | "cancel"; lists = preset of the checkboxes.
        -> booking or None."""
        from collection import bookings
        from collection import offers
        from collection import ticket
        me = userprofile.ensure(self.ctrl.settings)
        sd = ticket.side(t, me.get("id"))
        if sd is None:
            names = " ⇄ ".join(x for x in ((t.get("f") or ["", ""])[1], (t.get("o") or ["", ""])[1]) if x)
            qdialogs.info(tr("Trade ticket"), tr(f"This ticket ({names}) wasn't issued to you."))
            return None
        old = bookings.by_ticket(t.get("id"))
        if old is not None:
            qdialogs.info(tr("Trade ticket"), tr(f"Ticket Nº {ticket.label(t)} ist schon eingelöst ("
                                                 + time.strftime("%d.%m.%Y", time.localtime(old["t"])) + ")."))
            return None
        give, get, partner = sd
        import games
        cur = games.current().key
        here = lambda c: ticket.card_game(c, t) == cur   # noqa: E731
        other = {}   # game -> {"give": [...], "get": [...]}
        for side, cards in (("give", give), ("get", get)):
            for c in cards:
                if not here(c):
                    while len(c) < 6:
                        c.append("")
                    if not c[5]:
                        c[5] = f"{str(c[0]).upper()} #{c[1]}"
                    other.setdefault(ticket.card_game(c, t), {"give": [], "get": []})[side].append(c)
        give, get = [c for c in give if here(c)], [c for c in get if here(c)]
        db = carddb.by_prints([(c[0], c[1]) for c in give + get]) if carddb.exists() else {}
        for c in give + get:   # pixel code without card names: from the database
            if len(c) < 6 or not c[5]:
                r = db.get((str(c[0]).lower(), str(c[1])))
                while len(c) < 6:
                    c.append("")
                c[5] = (r or {}).get("name") or f"{str(c[0]).upper()} #{c[1]}"
        _, short = bookings.plan(self.ctrl.collection, give, prefer)
        gs, _ = bookings.prices_of(get, db)
        vs, _ = bookings.prices_of(give, db)
        money = ticket.money_from_me(t, me.get("id"))

        def lines(cards):
            out = [f"{int(c[4] or 1)}× {c[5]}  ·  {str(c[0]).upper()} #{c[1]}" + ("  ·  Foil" if c[3] else "")
                   for c in cards[:12]]
            if len(cards) > 12:
                out.append(tr(f"… and {len(cards) - 12} more"))
            return "\n".join(out) or tr("nothing")
        info = (tr(f"You get ({eur(gs)}):") + "\n" + lines(get) + "\n\n" + tr(f"You give ({eur(vs)}):") + "\n"
                + lines(give))
        if money:
            info += "\n\n" + (tr(f"You pay {eur(money)} on top.") if money > 0 else tr(f"You get {eur(-money)} on top."))
        if short:
            info += "\n\n" + tr("Not (or no longer) in your collection – skipped:") + "\n" + lines(short)
        if other:   # mixed trade: summary per game (only games that are affected)
            info = (f"<b>{games.nick_of(cur)}</b>\n" + info) if give or get else ""
            for g, part in other.items():
                gdb = carddb.by_prints([(c[0], c[1]) for c in part["give"] + part["get"]], game=g)
                ogs, _ = bookings.prices_of(part["get"], gdb)
                ovs, _ = bookings.prices_of(part["give"], gdb)
                info += (("\n\n" if info else "") + f"<b>{games.nick_of(g)}</b>\n"
                         + tr(f"You get ({eur(ogs)}):") + "\n" + lines(part["get"]) + "\n\n"
                         + tr(f"You give ({eur(ovs)}):") + "\n" + lines(part["give"]))
        opts = {"have": bool(lists[0]), "wish": bool(lists[1])}
        if answer is None:
            def build(ui, d):
                return ui.col([
                    ui.label(tr(f"Trade with {partner[1] or '?'} · Ticket Nº {ticket.label(t)}"), big=True),
                    ui.note(info.replace("\n", "<br>")),
                    ui.check(tr("Remove given cards from my trade lists"), opts["have"],
                             lambda on: opts.update(have=bool(on))),
                    ui.check(tr("Remove received cards from my wishlists"), opts["wish"],
                             lambda on: opts.update(wish=bool(on))),
                    ui.row([ui.stretch(), ui.button(tr("Cancel"), lambda: d.close("cancel")),
                            ui.button(tr("Book trade"), lambda: d.close("book"), active=True)]),
                ], spacing=10)
            answer = qdialogs.show(tr("Book trade"), build)
        if answer != "book":
            return None
        def cards_of(g, part):
            return [{"g": g, "dir": side, "name": c[5], "set": str(c[0]).upper(), "number": str(c[1]),
                     "count": int(c[4] or 1), "foil": bool(c[3])} for side in ("get", "give") for c in part[side]]
        parts = dict(other)
        if give or get:
            parts[cur] = {"give": give, "get": get}

        def foreign_of(skip):   # cards of the other games – shown greyed out in the session
            return [x for g, part in parts.items() if g != skip for x in cards_of(g, part)]
        b = None
        booked = []   # [(game, session ID)]
        if give or get or not other:   # only cards of other games: redeem nothing in the open game
            b = bookings.book_trade(self.ctrl.collection, t, give, get, partner, prefer=prefer, cards_db=db,
                                    foreign=foreign_of(cur))
            trade.after_trade(self.ctrl.collection, b.get("taken"), get, opts["have"], opts["wish"])
            self.ctrl.collection.save()
            booked.append((cur, b.get("session")))
        for g, part in other.items():   # the other games: book them right away too (without switching)
            ob = self.ctrl.book_in_game(g, t, part["give"], part["get"], partner, foreign_of(g), opts)
            if ob is None:   # not possible right now (a job is running): on the next opening
                bookings.add_pending(g, t, part["give"], part["get"], partner, foreign_of(g))
                booked.append((g, None))
            else:
                booked.append((g, ob.get("session")))
                b = b or dict(ob, game=g)
        if t.get("x") and offers.get(t["x"]) is not None:
            offers.set_status(t["x"], "accepted")
        self.ctrl.after_booking()
        self.ctrl.trade_offers_changed()
        self.receipt(t, partner, info, booked, quiet=answer is not None)
        return b

    def receipt(self, t, partner, info, booked, quiet=False):
        """Receipt after booking (wherever you are): what in which game – "To session" or OK."""
        import games
        from collection import ticket
        cur = games.current().key
        later = [g for g, sid in booked if sid is None and g != cur]
        text = info + ("\n\n" + tr("Will be booked the next time you open: ") + ", ".join(games.nick_of(g) for g in later)
                       if later else "")
        if quiet:
            return
        here = next(((g, sid) for g, sid in booked if g == cur and sid), None)
        if here:
            target, label = here, tr("Go to log")
        else:   # the open game isn't involved: go to the game with the most cards of this ticket
            order = ticket.games_in(t)
            target = next(((g, sid) for g in order for g2, sid in booked if g2 == g and sid), None)
            label = tr(f"Zu {games.nick_of(target[0])} wechseln") if target else ""
            if target:
                text += "\n\n" + tr(f"The log is in {games.nick_of(target[0])}.")
        buttons = ([("session", label, "")] if target else []) + [("ok", tr("OK"), "active")]

        def done(key):
            if key == "session" and target:
                self.ctrl.show_trade_session(*target)
        qdialogs.ask(tr(f"Ticket Nº {ticket.label(t)} was booked"),
                     tr(f"Trade with {partner[1] or '?'}") + "\n\n" + text.replace("<b>", "").replace("</b>", ""),
                     buttons, wait=False, on_close=done)

    def apply_pending(self):
        """Book pending parts of mixed trades for the currently open game. -> number of booked trades"""
        from collection import bookings
        import games
        if not carddb.exists():
            return 0
        n = 0
        for p in bookings.take_pending():
            t = p["ticket"]
            tid = t
            if bookings.by_ticket(tid["id"]) is not None:
                continue
            give, get = p.get("give") or [], p.get("get") or []
            db = carddb.by_prints([(c[0], c[1]) for c in give + get])
            b = bookings.book_trade(self.ctrl.collection, tid, give, get, p.get("partner") or ["", ""],
                                    cards_db=db, foreign=p.get("foreign"))
            trade.after_trade(self.ctrl.collection, b.get("taken"), get, True, True)
            n += 1
        if n:
            self.ctrl.collection.save()
            self.toast(tr(f"{n} trade part(s) booked for {games.nick_of(games.current().key)} – see Logs & stats"), 6000)
            self.ctrl.after_booking()
        return n

    # --- Trade offers: replies ---
    def accept_offer(self, trade_id, answer=None):
        """Accept an offer: create a completion ticket (for the other party to scan), book it on my side."""
        from collection import offers
        from collection import ticket
        o = offers.get(trade_id)
        if o is None:
            return None
        t = offers.latest(o)
        me = userprofile.ensure(self.ctrl.settings)
        sd = ticket.side(t, me.get("id"))
        if sd is None:
            return None
        give, get, partner = sd
        final = ticket.new((me.get("id"), me.get("name") or tr("Me")), (partner[0], partner[1]), give, get,
                           trade_id=o["id"], version=int(t.get("n") or 1), kind="f",
                           money=ticket.money_from_me(t, me.get("id")))
        b = self.book_ticket(final, answer=answer)
        if b is None:
            return None
        o2 = offers.get(trade_id)
        if o2 is not None:
            offers._put(final, partner, "accepted")
        if answer is None:
            self.show_ticket(final)   # to send back – then the other party books too
        return final

    def decline_offer(self, trade_id):
        from collection import offers
        offers.set_status(trade_id, "declined")
        self.ctrl.trade_offers_changed()

    def withdraw_offer(self, trade_id):
        from collection import offers
        offers.set_status(trade_id, "withdrawn")
        self.ctrl.trade_offers_changed()

    def counter_offer(self, trade_id, give=None, get=None, money=None):
        """Counter-offer: change cards/counts/money -> new version (same trade ID) as a ticket.
        give/get: changed lists from my point of view (None = as in the offer). -> new ticket"""
        from collection import offers
        from collection import ticket
        o = offers.get(trade_id)
        if o is None:
            return None
        t = offers.latest(o)
        me = userprofile.ensure(self.ctrl.settings)
        sd = ticket.side(t, me.get("id"))
        if sd is None:
            return None
        g0, r0, partner = sd
        give = [c for c in (g0 if give is None else give) if int(c[4] or 0) > 0]
        get = [c for c in (r0 if get is None else get) if int(c[4] or 0) > 0]
        new = ticket.new((me.get("id"), me.get("name") or tr("Me")), (partner[0], partner[1]), give, get,
                         trade_id=o["id"], version=int(t.get("n") or 1) + 1,
                         money=ticket.money_from_me(t, me.get("id")) if money is None else money)
        offers.record_sent(new)
        self.ctrl.trade_offers_changed()
        return new

    def edit_offer_in_trade(self, trade_id):
        """Counter-offer with other cards: open the friend in the trade tab – "Share as ticket" then becomes the next
        version of this trade."""
        from collection import offers
        o = offers.get(trade_id)
        if o is None:
            return False
        t = offers.latest(o)
        if trade.friend(o["partner"][0]) is None:
            qdialogs.info(tr("Trade offer"), tr("To add cards you need this friend's trade file (Import friend …). You can change counts and money directly."))
            return False
        self.open_friend(o["partner"][0])
        from collection import ticket
        me = userprofile.ensure(self.ctrl.settings).get("id")
        self.offer_ctx = {"x": o["id"], "n": int(t.get("n") or 1)}   # "Share as ticket" = next version
        self.trade_money = ticket.money_from_me(t, me)
        self.update_trade_sum()
        return True

    # --- Wants ---
    def fill_wants(self):
        owned = self.owned_names()
        my_have = {it["name"] for it, _ in trade.have_items(self.ctrl.collection.items)}
        self.f_wants.set_chips([("have", tr("I have"), lambda r: bool(owned.get(r["name"]))),
                                ("missing", tr("I don't have it"), lambda r: not owned.get(r["name"])),
                                ("list", tr("in my lists"), lambda r: r["name"] in my_have)],
                               exclusive=[("have", "missing")])
        self.f_wants.enter()

    # --- Has ---
    def fill_has(self):
        owned = self.owned_names()
        wishes = set(self.all_wanted())
        self.f_has.set_chips([("wish", "★ " + tr("on my wishlist"), lambda r: r["name"] in wishes),
                              ("missing", tr("I'm missing"), lambda r: not owned.get(r["name"])),
                              ("have", tr("I have it too"), lambda r: bool(owned.get(r["name"]))),
                              ("foil", "Foil", lambda r: bool(r["foil"]))],
                             exclusive=[("missing", "have")])
        self.f_has.enter()

    # --- Library ---
    def fill_flib(self):
        owned = self.owned_names()
        wishes = set(self.all_wanted())
        self.f_lib.set_chips([("wish", "★ " + tr("on my wishlist"), lambda r: r["name"] in wishes),
                              ("missing", tr("I'm missing"), lambda r: not owned.get(r["name"])),
                              ("have", tr("I have it too"), lambda r: bool(owned.get(r["name"]))),
                              ("foil", "Foil", lambda r: bool(r["foil"]))],
                             exclusive=[("missing", "have")])
        self.f_lib.enter()

    # --- Import ---
    def import_dialog(self):
        path = qdialogs.open_file(tr("Import a friend's collection"),
                                  "", tr("Collections and trade tickets (*.bentcorner *.csv *.txt *.png *.jpg *.jpeg *.webp);;All files (*)"))
        if path:
            return self.import_file(path)
        return None

    def import_file(self, path, name=None, answer=None, folder=None):
        """answer (for tests): "update" | "new" – otherwise asks if the friend already exists.
        An image is a trade ticket (ticket.py): booked after a confirmation."""
        from collection import ticket
        if ticket.is_ticket_file(path):
            t = ticket.read_image(path)
            if t is None:
                qdialogs.warn(tr("Trade ticket"), tr("This image doesn't contain a Bent°Corner trade ticket – or it was cropped. Best send the image unchanged."))
                return None
            return self.receive_ticket(t, answer=answer)
        try:
            parsed = trade.read_file(path)
        except (OSError, ValueError) as e:
            qdialogs.warn(tr("Importieren"), tr(f"Couldn't read the file: {e}"))
            return None
        as_new = False
        if parsed["kind"] == "bentcorner":
            d = parsed["data"]
            if d["id"] == userprofile.ensure(self.ctrl.settings)["id"]:
                qdialogs.info(tr("Importieren"), tr("That's your own collection 🙂"))
                return None
            from net import relay
            rf = next((f for f in relay.friends(self.ctrl.settings).values() if f.get("pid") == d["id"]), None)
            if rf is not None and rf.get("status") == "blocked":
                qdialogs.info(tr("Importieren"), tr("You blocked this person – their files can't be imported. You can unblock them in your profile."))
                return None
            if rf is not None and relay.shown_back(rf) is None:   # card back hidden: store the neutral one
                d["back"] = None
            old = trade.friend(d["id"])
            if old is not None:
                if answer is None:
                    answer = qdialogs.ask(tr("Importieren"),
                                          tr(f"This is {old.get('name')}'s collection – update it?"),
                                          [("cancel", tr("Cancel"), ""), ("new", tr("As a new library"), ""),
                                           ("update", tr("Refresh"), "active")])
                    if answer == "cancel":
                        answer = None
                if answer is None:
                    return None
                as_new = answer == "new"
        elif name is None:
            name, ok = qdialogs.get_text_ok(tr("Importieren"), tr("Whose collection is this?"))
            if not ok or not name.strip():
                return None
        d = trade.friend_from_import(parsed, name=name, as_new=as_new)
        folders = [f for f in self.ctrl.settings.get("friend_folders") or [] if f]
        if folders and d.get("previous") is None:   # newly added: into which folder? (only "General" → no question)
            pick = folder if folder is not None else qdialogs.ask(
                tr("Importieren"), tr(f"Which folder does {d['name']} go in?"),
                [("", tr("General"), "active")] + [(f, f, "") for f in folders])
            if pick:
                trade.set_friend_folder(d["id"], pick)
        n = sum(int(c[4] or 1) for c in d["cards"])
        diff = ""
        if d.get("previous") is not None:
            diff = tr(f" · before {d['previous']} different, now {len(d['cards'])}")
        self.toast(tr(f"{d['name']}: {n} cards, {len(d['wants'])} wishes loaded{diff}"))
        self.fill_friends()
        self.ctrl.trade_changed()
        self.open_friend(d["id"])
        return d

    # --- Export ---
    def export_groups(self, have=None):
        """have: [(entry, count)] from the selected lists – None = whole collection."""
        groups = self.ctrl.collection.groups()
        if have is None:
            return groups
        n_by_uid = {it["uid"]: n for it, n in have}
        out = []
        for g in groups:
            n = sum(n_by_uid.get(it["uid"], 0) for it in g["items"])
            if n > 0:
                out.append(dict(g, count=n))
        return out

    # --- Hint at the bottom ---
    def toast(self, text, ms=4500):
        shell = getattr(self.ctrl, "shell", None)
        if shell is not None:
            shell.show_toast(text)
