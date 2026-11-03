"""Binder view (qml/components/BinderView.qml): flip through spreads, search cards, fill pockets, move them,
leave gaps. Edit your own binders; friends' binders are view-only (from what they put on display, relay.py).
Data: binders.py.
"""
import time

from PySide6 import QtCore, QtGui

from collection import binders
from cards import carddb
from ui import qdialogs
from system.i18n import tr


class BinderBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.b = None            # open binder (dict)
        self.readonly = False    # a friend's binder
        self.owner = ""          # the friend's name
        self.spread = 0          # spread (0 = pages 1–2)
        self.hl = -1             # highlighted pocket (search)
        self._owned_ro = None    # friend: {(set, nr): 1} from what is on display
        self._lib_b = None       # library right of the binder (as in the deck builder) – only created when editing
        self._lib_core = None
        self.drop_hl = -1        # pocket under a dragged card
        self.game = None         # binder of another game (view only, without switching)

    # ---------- open ----------
    def open(self, bid):
        self.host = "profile"
        self.b, self.readonly, self.owner, self.spread, self.hl = binders.get(bid), False, "", 0, -1
        self._owned_ro, self.game, self.friend_game = None, None, None
        if self._lib_core is not None:   # library alongside: the collection may have changed since (scans …)
            self._lib_core.refresh()
        self.changed.emit()

    def open_other(self, game, bid):
        """View a binder (click on the tile) – any game, without switching: data from its folders, images from
        its card database. "Edit" opens it for editing (other game: with switching)."""
        import games
        f = games.mine(game) / "binders.json"
        try:
            items = __import__("json").loads(f.read_text("utf-8")).get("binders") or []
        except (OSError, ValueError):
            items = []
        b = next((x for x in items if x["id"] == bid), None)
        if b is None:
            return
        self.b, self.readonly, self.spread, self.hl, self.game = b, True, 0, -1, game
        self.host = "profile"
        self.friend_game = None
        self.owner = games.nick_of(game)
        self._owned_ro = binders.owned_map(games.collection_items(game))
        self.changed.emit()

    def _db(self, sids):
        """Card database rows – of the open game or of the game whose binder is currently open."""
        if not sids:
            return {}
        if self.game or getattr(self, "friend_game", None):
            return carddb.cards_by_ids(sids, game=self.game or self.friend_game)
        return carddb.cards_by_ids(sids) if carddb.exists() else {}

    def open_friend(self, payload, owner, game=None):
        """A friend's binder (relay: share_payload) – view only; "have" is stated by the friend. game: from
        another game (images from its card database, without switching)."""
        import games
        slots, owned = [], {}
        other = game if game and game != games.current().key else None
        keys = [(s[0], s[1]) for s in payload.get("slots") or [] if s]
        try:
            rows = carddb.by_prints(keys, game=other) if other else (carddb.by_prints(keys) if carddb.exists() else {})
        except Exception:  # noqa: BLE001 – game not installed
            rows = {}
        for s in payload.get("slots") or []:
            if not s:
                slots.append(None)
                continue
            r = rows.get((str(s[0]).lower(), str(s[1]))) or {}
            slots.append({"sid": r.get("id") or "", "set": str(s[0]).lower(), "number": str(s[1]), "lang": s[2],
                          "foil": bool(s[3]), "name": r.get("name") or "?"})
            if len(s) > 4 and s[4]:
                owned[(str(s[0]).lower(), str(s[1]))] = 1
        self.b = {"id": payload.get("id"), "name": payload.get("name") or tr("Binders"), "cols": payload.get("cols", 3),
                  "rows": payload.get("rows", 3), "slots": slots}
        self.readonly, self.owner, self.spread, self.hl, self._owned_ro = True, owner, 0, -1, owned
        self.host = "profile"
        self.game = None
        self.friend_game = other   # images from this game (_db)
        self.changed.emit()

    @QtCore.Slot()
    def close(self):
        self.b = None
        self.host = "profile"
        self.changed.emit()
        pb = getattr(self.ctrl, "shell", None) and self.ctrl.shell.backends.get("profile")
        if pb is not None:
            pb.refresh()
        back, self.back_to = self.back_to, ""
        if back:   # e.g. opened from trade: "Back" leads there again
            self.ctrl.stream.show_page(back)

    back_to = ""   # page from which the binder was opened (qprofile.openBinder)
    host = "profile"   # page that shows it: "profile" – or "trade" (opened there: shown right in the trade, no page switch)

    def show_in(self, page):
        """Opened from the trade: show it there (Back = straight back, no detour via the profile)."""
        self.host = "trade" if page == "trade" else "profile"
        self.back_to = ""
        self.changed.emit()
        return self.host == "trade"

    @QtCore.Property(str, notify=changed)
    def hostPage(self):
        return self.host

    def _owned(self):
        if self._owned_ro is not None:
            return self._owned_ro
        return binders.owned_map(self.ctrl.collection.items)

    def _save(self):
        if self.b is not None and not self.readonly:
            binders.put(self.b)
        self.changed.emit()

    # ---------- Library alongside ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def libView(self):
        """Library view on the right (search, advanced search, detail and comparison) – as in the deck builder."""
        if self._lib_b is None:
            from ui.qlibrary import LibraryBackend
            from ui.tradeview import TradeLibrary

            class BinderLibrary(TradeLibrary):
                """Next to the binder: 1–6 cards per row, with detail view 1–4, with comparison 1–3."""
                START = {"full": 1, "medium": 1, "small": 1, "full_c": 1, "medium_c": 1, "small_c": 1}
                HI = {"full": 6, "medium": 4, "small": 3, "full_c": 6, "medium_c": 4, "small_c": 3}
                COLS_KEY = "binder_cols_area"
            core = BinderLibrary(self.ctrl, modes=("mine", "all"))
            self._lib_b = LibraryBackend(self.ctrl, core, "binder_detail_w", main=False)
            self._lib_core = core
            core.refresh()
        return self._lib_b

    @QtCore.Slot(int)
    def addFromGrid(self, i):
        """Double-click in the library: into the next free pocket."""
        self.dropFromGrid(i, -1)

    @QtCore.Slot(int, int)
    def insertFromGrid(self, i, pos):
        """Card dragged from the library between two pockets: insert at position pos, the rest moves along."""
        self.dropFromGrid(i, pos, True)

    @QtCore.Slot(int, int)
    def dropFromGrid(self, i, slot, insert=False):
        """Put a library card (row i) into pocket slot (-1 = next free one) – occupied pocket: replace."""
        if self.b is None or self.readonly or self._lib_b is None:
            return
        row = self._lib_b.row(i)
        if row is None:
            return
        db = row.get("db")
        if db is None:
            r = carddb.cards_by_ids({row["sid"]}).get(row["sid"]) if carddb.exists() else None
            db = r
        if db is None:
            return
        s = binders.slot_of(db, row.get("lang") or "en", bool(row.get("foil")))
        if slot >= 0 and insert:
            binders.insert_at(self.b, slot, s)
        elif slot >= 0:
            binders.set_slot(self.b, slot, s)
        else:
            binders.add_cards(self.b, [s])
        self.drop_hl = -1
        # flip to the pocket so you can see where the card landed
        idx = slot if slot >= 0 else next((k for k in range(len(self.b["slots"]) - 1, -1, -1)
                                           if self.b["slots"][k] and self.b["slots"][k]["sid"] == s["sid"]), 0)
        self.spread = idx // binders.per_page(self.b) // 2
        self.hl = idx
        self._save()

    # ---------- for QML ----------
    @QtCore.Property(bool, notify=changed)
    def isOpen(self):
        return self.b is not None

    @QtCore.Property(bool, notify=changed)
    def readOnly(self):
        return self.readonly

    @QtCore.Property(str, notify=changed)
    def title(self):
        if self.b is None:
            return ""
        if self.game:   # viewing: "Name" or "Name · Pokémon" (other game)
            import games
            return self.b["name"] + ("" if self.game == games.current().key else " · " + self.owner)
        return (tr(f"{self.owner}'s binder") + " · " if self.readonly and self.owner else "") + self.b["name"]

    @QtCore.Property(str, notify=changed)
    def info(self):
        if self.b is None:
            return ""
        have, n = binders.progress(self.b, self._owned())
        p = binders.pages(self.b)
        a = self.spread * 2 + 1
        txt = tr(f"Page {a}–{min(a + 1, p)} of {p}") + " · " + tr(f"{have} of {n} cards owned")
        if n and have == n:
            txt += " · ✓ " + tr("complete")
        return txt

    @QtCore.Property(bool, notify=changed)
    def canEdit(self):
        """Own binder, currently only viewed -> "Edit" button."""
        return self.b is not None and bool(self.game)

    @QtCore.Property(str, notify=changed)
    def editText(self):
        import games
        if not self.game or self.game == games.current().key:
            return tr("Edit")
        return tr(f"Edit in {games.nick_of(self.game)}")

    @QtCore.Slot()
    def edit(self):
        """From viewing to editing: immediately in the open game, otherwise switch to the game first."""
        import games
        if self.b is None or not self.game:
            return
        game, bid = self.game, self.b["id"]
        # editing always happens in the profile (same editor as Profile → Edit binder); opened from the trade:
        # „Back“ leads there again (close() -> back_to)
        came = "trade" if self.host == "trade" else (self.back_to or "")

        def to_editor():
            self.open(bid)
            self.back_to = came
            if self.ctrl.stream.page != "profile":
                self.ctrl.stream.show_page("profile", back=True)
        if game == games.current().key:
            to_editor()
            return
        if not self.ctrl.switch_game(game, then=to_editor):
            self.ctrl.stream_toast(tr("Can't switch right now – wait for the running tasks first."))

    @QtCore.Property(int, notify=changed)
    def cols(self):
        return int((self.b or {}).get("cols") or 3)

    @QtCore.Property(int, notify=changed)
    def rows(self):
        return int((self.b or {}).get("rows") or 3)

    @QtCore.Property(bool, notify=changed)
    def canPrev(self):
        return self.spread > 0

    @QtCore.Property(bool, notify=changed)
    def canNext(self):
        """Own binder: one more empty spread is always possible (filling it grows the binder by itself)."""
        if self.b is None:
            return False
        last = binders.pages(self.b) // 2 - 1
        return self.spread < last + (0 if self.readonly else 1)

    @QtCore.Property("QVariantMap", notify=changed)
    def stats(self):
        """For the bar below the binder: pages, cards, owned, value."""
        if self.b is None:
            return {}
        owned = self._owned()
        have, n = binders.progress(self.b, owned)
        sids = {s["sid"] for s in self.b.get("slots") or [] if s and s.get("sid")}
        rows = self._db(sids)
        prices = {}
        for sid, r in rows.items():
            prices[sid] = r.get("eur") if r.get("eur") is not None else r.get("eur_foil")
        total, have_v = binders.value(self.b, owned, prices)
        pages = max(binders.pages(self.b), self.spread * 2 + 2)
        a = self.spread * 2 + 1
        return {"page": tr(f"Page {a}–{a + 1} of {pages}"), "cards": tr(f"{n} cards"),
                "have": tr(f"{have} owned") + (" · ✓ " + tr("complete") if n and have == n else ""),
                "missing": tr(f"{n - have} missing") if n - have else "",
                "value": _eur(total), "haveValue": _eur(have_v)}

    @QtCore.Property(float, notify=changed)
    def split(self):
        return float(self.ctrl.settings.get("binder_split") or 0.46)

    @QtCore.Slot(float)
    def setSplit(self, f):
        self.ctrl.settings["binder_split"] = round(max(0.3, min(0.8, float(f))), 3)
        self.ctrl.settings_changed()
        self.changed.emit()

    @QtCore.Property("QVariantList", notify=changed)
    def pagesData(self):
        """The two pages of the spread: [[{index, empty, name, img, have, hl, setLine} …], […]]."""
        if self.b is None:
            return []
        from ui.qlibrary import card_source
        per = binders.per_page(self.b)
        owned = self._owned()
        slots = self.b.get("slots") or []
        sids = {s["sid"] for s in slots if s and s.get("sid")}
        db = self._db(sids)
        lib = getattr(self.ctrl, "library_win", None)
        out = []
        for page in (self.spread * 2, self.spread * 2 + 1):
            cells = []
            for k in range(per):
                i = page * per + k
                s = slots[i] if i < len(slots) else None
                if not s:
                    cells.append({"index": i, "empty": True, "name": "", "img": "", "have": False, "hl": i in (self.hl, self.drop_hl),
                                  "setLine": ""})
                    continue
                img = ""
                r = db.get(s.get("sid"))
                if r is not None and self.game:   # other game: image from its database
                    from ui.qtrade import db_image_of
                    img = db_image_of(r, self.game)
                elif r is not None and lib is not None:
                    try:
                        row = lib.row_from_db(r)
                        row["lang"] = s.get("lang") or "en"
                        img = card_source(row, own_lang=True, width=300)
                    except Exception:  # noqa: BLE001 – without image: name in the card outline
                        img = ""
                cells.append({"index": i, "empty": False, "name": s.get("name") or "", "img": img,
                              "have": bool(owned.get((s["set"], s["number"]))), "hl": i in (self.hl, self.drop_hl),
                              "setLine": f"{s['set'].upper()} #{s['number']}" + (" · Foil" if s.get("foil") else "")})
            out.append(cells)
        return out

    # ---------- flip, search ----------
    @QtCore.Slot()
    def prev(self):
        self.spread = max(0, self.spread - 1)
        self.hl = -1
        self.changed.emit()

    @QtCore.Slot()
    def next(self):
        if self.canNext:
            self.spread += 1
            self.hl = -1
            self.changed.emit()

    @QtCore.Slot(str)
    def find(self, text):
        """Search in the binder: flip to the first matching card and highlight it (again: the next one)."""
        text = (text or "").strip().lower()
        if self.b is None or not text:
            self.hl = -1
            self.changed.emit()
            return
        slots = self.b.get("slots") or []
        hits = [i for i, s in enumerate(slots) if s and (text in (s.get("name") or "").lower()
                                                         or text == f"{s['set']} {s['number']}")]
        if not hits:
            self.hl = -1
            self.ctrl.stream_toast(tr("Not in this binder"))
            self.changed.emit()
            return
        nxt = next((i for i in hits if i > self.hl), hits[0])
        self.hl = nxt
        self.spread = nxt // binders.per_page(self.b) // 2
        self.changed.emit()

    # ---------- edit ----------
    @QtCore.Slot(int, int)
    def moveSlot(self, i, j):
        """Card dragged onto a card (or empty pocket): the two swap places."""
        if self.b is not None and not self.readonly and i != j and i >= 0 and j >= 0:
            binders.move(self.b, i, j)
            self.hl = j
            self._save()

    @QtCore.Slot(int, int)
    def insertSlot(self, i, j):
        """Dragged between two pockets: the card takes place j, everything after it moves one along (gaps too)."""
        if self.b is not None and not self.readonly and i >= 0 and j >= 0:
            binders.move_to(self.b, i, j)
            self.hl = j - 1 if j > i else j
            self._save()

    @QtCore.Slot(int)
    def takeOut(self, i):
        """Dragged out of the binder: the pocket becomes empty (Ctrl+Z brings the card back)."""
        if self.b is not None and not self.readonly and 0 <= i < len(self.b.get("slots") or []) and self.b["slots"][i]:
            binders.remove_slot(self.b, i)
            self.hl = -1
            self._save()
            self.ctrl.stream_toast(tr("Taken out of the binder – Ctrl+Z brings it back"))

    @QtCore.Slot(int)
    def click(self, i):
        """Click without dragging: show the card (own binder: detail view alongside); empty pocket: insert a card."""
        if self.b is None:
            return
        slots = self.b.get("slots") or []
        s = slots[i] if 0 <= i < len(slots) else None
        if not s:
            if not self.readonly:
                self.add_dialog(at=i)
            return
        if self.game:   # binder of another game: view only (the detail view belongs to the open game)
            self.hl = i
            self.changed.emit()
            return
        if self.readonly or self._lib_core is None:
            self._show_card(s)
            return
        db = carddb.cards_by_ids({s["sid"]}) if carddb.exists() else {}
        if s["sid"] in db:
            row = self._lib_core.row_from_db(db[s["sid"]])
            row["lang"] = s.get("lang") or "en"
            self._lib_core.show_card_row(row)
            self.hl = i
            self.changed.emit()

    def _show_card(self, s):
        lib = getattr(self.ctrl, "library_win", None)
        db = carddb.cards_by_ids({s["sid"]}) if carddb.exists() else {}
        if lib is not None and s["sid"] in db:
            self.ctrl.stream.show_page("library", back=True)
            lib.show_row(lib.row_from_db(db[s["sid"]])) if hasattr(lib, "show_row") else None

    @QtCore.Slot()
    def addDialog(self):
        self.add_dialog()

    def add_dialog(self, at=None):
        """Search and insert cards: single printings – or all printings of a card (e.g. all Pikachus)."""
        if self.b is None or self.readonly:
            return
        st = {"q": "", "res": [], "picked": set()}

        def search(t):
            st["q"] = t
            st["res"] = list(carddb.search(t, limit=120, sort="set", no_tokens=True)) if t.strip() else []
            st["picked"] = set()

        def build(ui, d):
            items = [ui.row([ui.edit(st["q"], lambda t: (search(t), d.refresh()), key="bq",
                                     live=lambda t: st.update(q=t), placeholder=tr("Card name, e.g. Sol Ring")),
                             ui.button(tr("Suchen"), lambda: (search(st["q"]), d.refresh()))])]
            if st["res"]:
                names = sorted({r["name"] for r in st["res"]})
                rows = [{"text": f"{r['name']} · {r['set_code'].upper()} #{r['number']} · {r.get('set_name') or ''}",
                         "checkable": True, "checked": r["id"] in st["picked"]} for r in st["res"]]
                items.append(ui.list(rows, on_check=lambda k, on: (st["picked"].add(st["res"][k]["id"]) if on else
                                                                  st["picked"].discard(st["res"][k]["id"])),
                                     h=320, multi=True))
                items.append(ui.row([
                    ui.button(tr(f"Add all {len(st['res'])} prints") if len(names) == 1 else
                              tr(f"Add all {len(st['res'])} results"), lambda: d.close("all")),
                    ui.stretch(), ui.button(tr("Cancel"), lambda: d.close(None)),
                    ui.button(tr("Add selected"), lambda: d.close("picked"), active=True)]))
            elif st["q"].strip():
                items.append(ui.note(tr(f"No card found for “{st['q'].strip()}” – enter only the card name (e.g. Sol Ring).")))
            else:
                items.append(ui.note(tr("Enter a card name (e.g. Sol Ring) – then “Add all prints”: missing cards appear greyed out as gaps. Single cards: just drag them from the library on the right into a pocket.")))
            return ui.col(items, spacing=10)
        res = qdialogs.show(tr("Cards into the binder"), build, wide=True)
        if res == "all":
            rows = st["res"]
        elif res == "picked":
            rows = [r for r in st["res"] if r["id"] in st["picked"]]
        else:
            return
        rows = sorted(rows, key=lambda r: (r.get("released") or "", r["set_code"], carddb.number_key(r["number"])))
        binders.add_cards(self.b, rows, at=at)
        self._save()

    @QtCore.Slot(str, result=bool)
    def renameTo(self, name):
        """Click on the binder's name in its head (review .101): renamed right there."""
        if self.b is None or (self.readonly and not self.game) or not name.strip():
            return False
        self.b["name"] = name.strip()[:60]
        if self.game:   # only viewed (other game too): straight into its file
            rename_in(self.game, self.b["id"], self.b["name"])
            self.changed.emit()
        else:
            self._save()
        return True

    @QtCore.Slot()
    def rename(self):
        if self.b is None or (self.readonly and not self.game):
            return
        name = qdialogs.get_text(tr("Rename binder"), tr("Name:"), self.b["name"])
        if name and name.strip():
            self.b["name"] = name.strip()[:60]
            if self.game:   # only viewed (other game too): straight into its file
                rename_in(self.game, self.b["id"], self.b["name"])
                self.changed.emit()
            else:
                self._save()

    @QtCore.Slot()
    def remove(self):
        if self.b is None or self.readonly:
            return
        if qdialogs.question(tr("Delete binder"), tr(f"Delete “{self.b['name']}”? Your cards stay in the collection."), danger=True):
            binders.remove(self.b["id"])
            self.close()

    @QtCore.Slot()
    def share(self):
        """Share the binder with friends (6 months, encrypted, keeps itself up to date afterwards) – like the chip."""
        import games
        from net import relay
        if self.b is None or self.readonly:
            return
        s = self.ctrl.settings
        if not relay.enabled(s) or not relay.ok_friends(s):
            self.ctrl.stream_toast(tr("To share, first turn on the exchange in your profile and add friends."))
            return
        self.b["shared"] = True
        binders.put(self.b)
        share_put(self.ctrl, games.current().key, self.b)

    @QtCore.Slot()
    def missingToWishlist(self):
        """Put the binder's missing cards on the wish list (exactly this printing)."""
        from collection import trade
        if self.b is None or self.readonly:
            return
        miss = binders.missing(self.b, self._owned())
        for s in miss:
            trade.add_wish(s["name"], 1, s["set"], s["number"])
        self.ctrl.trade_changed()
        self.ctrl.stream_toast(tr(f"{len(miss)} missing cards added to the wish list"))


def update_in(game, bid, **fields):
    """Set fields of a binder – also in another game, without switching (straight into its binders.json).
    "updated" stays (sharing is not a change to the binder). -> the binder or None"""
    import json
    import games
    if game == games.current().key:
        items = binders.load()
        b = next((x for x in items if x.get("id") == bid), None)
        if b is not None:
            b.update(fields)
            binders.save(items)
        return b
    f = games.mine(game) / "binders.json"
    try:
        data = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    hit = None
    for b in data.get("binders") or []:
        if b.get("id") == bid:
            b.update(fields)
            hit = b
    if hit is not None:
        f.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    return hit


def share_put(ctrl, game, b, quiet=False):
    """Put a binder on display for friends (encrypted, to the same friends as the lists) – in the background."""
    import hashlib
    import json
    import games
    from net import relay
    s = ctrl.settings
    items = ctrl.collection.items if game == games.current().key else games.collection_items(game)
    payload = binders.share_payload(b, binders.owned_map(items))
    aud = relay.state(s).get("audience") or {}
    codes = relay.audience_codes(s, aud.get("mode") or "all", aud.get("codes") or ())
    fp = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    relay.state(s).setdefault("binder_fp", {})[f"{game}/binder-{b['id']}"] = fp
    ctrl._relay_bg("binder_put_quiet" if quiet else "binder_put",
                   lambda: relay.board_put(s, game, f"binder-{b['id']}", payload, codes, title=b.get("name") or ""))


def share_withdraw(ctrl, game, bid):
    """Withdraw a shared binder: delete it from the server, friends delete their copy."""
    from net import relay
    s = ctrl.settings
    relay.state(s).setdefault("binder_fp", {}).pop(f"{game}/binder-{bid}", None)
    if relay.posted(s, game, f"binder-{bid}"):
        ctrl._relay_bg("binder_gone", lambda: relay.withdraw(s, game, f"binder-{bid}"))


def auto_share(ctrl, force=False):
    """Lists tick (every 5 min.): re-share shared binders if they have changed (including "have" through
    new cards) or the last state is older than one day. All games. force: re-share all of them now (new key –
    after blocking or removing a friend)."""
    import hashlib
    import json
    import games
    from net import relay
    s = ctrl.settings
    if not relay.enabled(s) or not relay.ok_friends(s):
        return
    fps = relay.state(s).setdefault("binder_fp", {})
    cur = games.current().key
    for key, _n, ready in games.GAMES:
        if not ready:
            continue
        if key == cur:
            items = binders.load()
        else:
            f = games.mine(key) / "binders.json"
            try:
                items = json.loads(f.read_text("utf-8")).get("binders") or [] if f.exists() else []
            except (OSError, ValueError):
                items = []
        for b in items:
            if not b.get("shared"):
                continue
            owned = binders.owned_map(ctrl.collection.items if key == cur else games.collection_items(key))
            fp = hashlib.sha256(json.dumps(binders.share_payload(b, owned), sort_keys=True).encode()).hexdigest()[:16]
            post = relay.posted(s, key, f"binder-{b['id']}") or {}
            old = time.time() - float(post.get("t") or 0) > 22 * 3600
            if force or not post or old or fps.get(f"{key}/binder-{b['id']}") != fp:
                share_put(ctrl, key, b, quiet=True)


def rename_in(game, bid, name):
    """Rename a binder of a (possibly different) game without switching – straight into its binders.json."""
    import json
    import games
    if game == games.current().key:
        b = binders.get(bid)
        if b is not None:
            b["name"] = name
            binders.put(b)
        return
    f = games.mine(game) / "binders.json"
    try:
        data = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return
    for b in data.get("binders") or []:
        if b.get("id") == bid:
            b["name"] = name
            b["updated"] = time.time()
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def _eur(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
