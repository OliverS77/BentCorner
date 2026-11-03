"""Trade page – friends sidebar, a friend's view across games, sync: FriendsBackend, moved out of ui/qtrade.py unchanged (docs/TRADE-SPLIT.md).
In QML as tradeFriends; the host (TradeBackend) keeps shared state, helpers and signals."""
import html

from PySide6 import QtCore

from ui.qtrade import back_image, carddb, db_image_of, eur, has_image, tr, trade   # shared helpers of the trade page


class FriendsBackend(QtCore.QObject):
    """Part of the trade page (docs/TRADE-SPLIT.md), in QML as tradeFriends (alias tf): moved from TradeBackend
    unchanged – shared state, helpers and signals stay with the host (TradeBackend)."""
    changed = QtCore.Signal()   # forwarded from TradeBackend.changed (notify of the moved properties)
    railChanged = QtCore.Signal()   # forwarded from TradeBackend.railChanged (notify of the moved properties)
    syncChanged = QtCore.Signal()   # forwarded from TradeBackend.syncChanged (notify of the moved properties)
    listsChanged = QtCore.Signal()   # forwarded from TradeBackend.listsChanged (notify of the moved properties)
    entriesChanged = QtCore.Signal()   # forwarded from TradeBackend.entriesChanged (notify of the moved properties)

    SORTS = (("name", "Name"), ("recent", "Recently imported"), ("cards", "Largest collection"))

    def __init__(self, host):
        super().__init__(host)
        self.host, self.ctrl, self.page = host, host.ctrl, host.page
        for name in ('changed', 'railChanged', 'syncChanged', 'listsChanged', 'entriesChanged'):   # the host's signal also refreshes the moved properties
            getattr(host, name).connect(getattr(self, name))

    @QtCore.Property(QtCore.QObject, constant=True)
    def friendLib(self):
        return self.host.flib_b

    @QtCore.Property(bool, notify=railChanged)
    def railOpen(self):
        return not self.page.rail_compact

    @QtCore.Slot()
    def toggleRail(self):
        self.page.toggle_rail()
        self.ctrl.settings_changed()

    @QtCore.Property(bool, notify=railChanged)
    def syncUnderstood(self):
        """Read „How does it work?“ under SYNC and ticked „I understand“: only then the two buttons work."""
        return bool(self.ctrl.settings.get("sync_understood"))

    @QtCore.Slot(bool)
    def setSyncUnderstood(self, on):
        self.ctrl.settings["sync_understood"] = bool(on)
        self.ctrl.settings_changed()
        self.host.railChanged.emit()

    @QtCore.Property("QVariantList", notify=railChanged)
    def friends(self):
        """Each friend ONCE, across all games: second line = their games as abbreviations ("MTG · PKM"). Friends who
        only exist in another game are listed just like the others – a click shows their cards there without switching
        (fid "@<game>:<id>")."""
        import games
        from ui import qprofile
        act = self.page.active()
        cur = games.current().key
        by_id = {}
        for d in trade.friends():
            by_id[d["id"]] = {"d": d, "games": [cur], "home": cur}
        for key, gname, ready in games.GAMES:
            if not ready or key == cur:
                continue
            for d in qprofile.friend_files(key):
                if not d.get("id") or d.get("example"):
                    continue
                e = by_id.setdefault(d["id"], {"d": d, "games": [], "home": key})
                e["games"].append(key)
        out = []
        for fid, e in by_id.items():
            d = e["d"]
            here = e["home"] == cur
            n = sum(int(c[4] or 1) for c in d.get("cards") or [] if isinstance(c, list) and len(c) > 4)
            nw = len(d.get("wants") or [])
            name = d.get("name") or tr("Friend")
            gl = " · ".join(games.SHORT.get(k, k.upper()) for k in sorted(e["games"], key=lambda k: k != cur))
            out.append({"fid": fid if here else f"@{e['home']}:{fid}", "id": fid, "name": name, "img": back_image(d.get("back")),
                        "info": gl, "example": bool(d.get("example")), "active": fid in act,
                        "folder": d.get("folder") or "", "n": n, "imported": d.get("imported") or 0, "other": not here,
                        "tip": f"{name} · {gl} · " + (tr(f"{n} cards · wants {nw}") if here else
                                                     tr(f"plays {games.name_of(e['home'])}"))})
        return out

    @QtCore.Property("QVariantList", notify=railChanged)
    def friendGroups(self):
        """[{folder, title, open, count, friends}] – first the friends without a folder (no heading), then the
        folders the user created. There are no predefined folders."""
        sort = self.ctrl.settings.get("friend_sort") or "name"   # default: alphabetical
        key = {"recent": lambda f: -f["imported"], "cards": lambda f: -f["n"]}.get(sort, lambda f: f["name"].lower())
        fr = sorted(self.friends, key=key, reverse=bool(self.ctrl.settings.get("friend_sort_rev")))
        closed = set(self.ctrl.settings.get("friend_folders_closed") or [])
        folders = self.host._folders()
        out = []
        for f in folders:   # "General" (folder "") always exists – everyone without their own folder goes there
            members = [x for x in fr if (x["folder"] if x["folder"] in folders else "") == f]
            out.append({"folder": f, "title": f or tr("General"), "open": f not in closed, "count": len(members),
                        "friends": members})
        return out

    @QtCore.Property(bool, notify=railChanged)
    def friendSortReversed(self):
        """Arrow next to the sort button: ↓ = normal (A–Z, newest, largest first), ↑ = reversed."""
        return bool(self.ctrl.settings.get("friend_sort_rev"))

    @QtCore.Slot()
    def toggleFriendSort(self):
        self.ctrl.settings["friend_sort_rev"] = not self.ctrl.settings.get("friend_sort_rev")
        self.ctrl.settings_changed()
        self.host.railChanged.emit()

    @QtCore.Slot(str)
    def toggleFriendFolder(self, folder):
        closed = set(self.ctrl.settings.get("friend_folders_closed") or [])
        (closed.discard if folder in closed else closed.add)(folder)
        self.ctrl.settings["friend_folders_closed"] = sorted(closed)
        self.ctrl.settings_changed()
        self.host.railChanged.emit()

    @QtCore.Slot(str)
    def newFriendFolderNamed(self, name):
        name = (name or "").strip()
        if name and name not in self.host._folders():
            self.ctrl.settings["friend_folders"] = self.host._folders()[1:] + [name]
            self.ctrl.settings_changed()
            self.host.railChanged.emit()

    @QtCore.Slot(str, str)
    def renameFriendTo(self, fid, name):
        if (name or "").strip():
            trade.rename_friend(fid, name)
            self.page.fill_friends()
            if self.page.friend_id == fid:
                self.page.open_friend(fid)
            self.ctrl.trade_changed()
            self.host.railChanged.emit()

    @QtCore.Slot(str, str)
    def renameFriendFolderTo(self, old, name):
        name = (name or "").strip()
        folders = self.host._folders()[1:]
        if not old or not name or name in folders or old not in folders:
            return
        self.ctrl.settings["friend_folders"] = [name if f == old else f for f in folders]
        for d in trade.friends():
            if (d.get("folder") or "") == old:
                trade.set_friend_folder(d["id"], name)
        self.ctrl.settings_changed()
        self.host.railChanged.emit()

    @QtCore.Slot(str, str, result="QVariantList")
    def railMenu(self, kind, ident):
        """Sidebar menus: kind "friend" (ident = fid), "folder" (folder name), "sort"."""
        if kind == "sort":
            cur = self.ctrl.settings.get("friend_sort") or "name"
            return [{"text": tr("Sort by"), "enabled": False}] + \
                [{"text": tr(t), "key": k, "on": k == cur, "indent": True} for k, t in self.SORTS]
        if kind == "folder":
            if not ident:
                return []
            return [{"text": tr("Rename …"), "key": "rename"},
                    {"text": tr("Delete folder (friends move to “General”)"), "key": "delete"}]
        d = trade.friend(ident) or {}
        cur = d.get("folder") or ""
        # instead of renaming: a note only you can see ("Note" tab on the friend)
        out = [{"text": tr("Note …"), "key": "note"}]
        if len(self.host._folders()) > 1:
            out += [{"sep": True}, {"text": tr("Move to folder"), "enabled": False}]
            out += [{"text": f or tr("no folder"), "key": "move:" + f, "indent": True, "on": f == cur,
                     "enabled": f != cur} for f in self.host._folders()]
        code = self._relay_code(ident)
        if code:
            from net import relay
            rf = relay.friends(self.ctrl.settings).get(code) or {}
            out += [{"sep": True},
                    {"text": tr("Show back") if rf.get("hide_back") else tr("Hide card back"), "key": "hideback"},
                    {"text": tr("Report …"), "key": "report"}]
            if rf.get("status") != "blocked":
                out.append({"text": tr("Block …"), "key": "block"})
        out += [{"sep": True}, {"text": tr("Remove …"), "key": "remove"}]
        return out

    def _relay_code(self, fid):
        """Mailbox code for a friend (via their profile ID) – only then is there a "Report" option."""
        from net import relay
        try:
            return next((c for c, f in relay.friends(self.ctrl.settings).items() if f.get("pid") == fid), None)
        except Exception:  # noqa: BLE001
            return None

    @QtCore.Slot(str, str, str)
    def railAction(self, kind, ident, key):
        from ui import qdialogs
        st = self.ctrl.settings
        if kind == "sort":
            st["friend_sort"] = key
        elif kind == "folder":
            folders = self.host._folders()[1:]
            if key == "rename":
                name = qdialogs.get_text(tr("Rename folder"), tr("New name:"), ident)
                if not name or not name.strip() or name.strip() in folders:
                    return
                st["friend_folders"] = [name.strip() if f == ident else f for f in folders]
                for d in trade.friends():
                    if (d.get("folder") or "") == ident:
                        trade.set_friend_folder(d["id"], name.strip())
            elif key == "delete":
                st["friend_folders"] = [f for f in folders if f != ident]
                for d in trade.friends():
                    if (d.get("folder") or "") == ident:
                        trade.set_friend_folder(d["id"], "")   # friends are then without a folder again
        else:
            if ident.startswith("@") and key.startswith("move:"):   # friend from another game: re-sort there
                game, _, fid = ident[1:].partition(":")
                trade.set_friend_folder_in(game, fid, key[5:])
                self.ctrl.settings_changed()
                self.page.fill_friends() if hasattr(self.page, "fill_friends") else None
                self.host.railChanged.emit()
                return
            d = trade.friend(ident)
            if not d:
                return
            if key == "note":
                self.page.open_friend(ident)
                self.page.show_friend_tab("note")
                self.ctrl.stream.show_page("trade", back=True)
            elif key in ("report", "block", "hideback"):
                from net import relay
                code = self._relay_code(ident)
                if not code:
                    return
                if key == "report":
                    self.ctrl.relay_report(code)
                elif key == "block":
                    self.ctrl.relay_block(code)   # asks first (sheet)
                else:
                    hidden = bool((relay.friends(st).get(code) or {}).get("hide_back"))
                    self.ctrl.relay_hide_back(code, not hidden)
            elif key == "remove":
                self.page.remove(d)
            elif key.startswith("move:"):
                trade.set_friend_folder(ident, key[5:])
        self.ctrl.settings_changed()
        self.page.fill_friends() if hasattr(self.page, "fill_friends") else None
        self.host.railChanged.emit()

    @QtCore.Slot(str)
    def openFriend(self, fid):
        if fid.startswith("@"):   # friend from another game: into that game (Oliver, review .101 – a2)
            key, _, real = fid[1:].partition(":")
            d = self.page.foreign_file(key, real)
            if d is None:
                return
            page, ctrl = self.page, self.ctrl

            def there():   # after the switch (the shuffling deck is the loading sign meanwhile)
                ctrl.stream.show_page("trade", back=True)
                if trade.friend(real) is not None:
                    page.open_friend(real)
                else:
                    page.open_foreign(key, d)
            if ctrl.switch_game(key, then=there):
                return
            ctrl.stream.show_page("trade", back=True)   # game can't be opened (not installed …): their cards here
            page.open_foreign(key, d)
            return
        self.page.open_friend(fid)

    @QtCore.Slot()
    def exportFriend(self):
        self.ctrl.go_export("friend_export")

    @QtCore.Slot()
    def importFriend(self):
        self.page.import_dialog()

    @QtCore.Property(bool, notify=listsChanged)
    def hasFriends(self):
        return bool(trade.friends())

    @QtCore.Slot(str, str, bool)
    def setShared(self, kind, lid, on):
        """List private / shared with friends (encrypted in the mailbox, visible only to friends). Set to
        private: share again right away – the old state with this list is thereby gone from the server."""
        trade.set_shared(kind, lid, on)
        self.host.lists_b._lists_touched()
        if not on:
            self.ctrl.relay_send_lists(quiet=True)

    @QtCore.Property(bool, notify=entriesChanged)
    def listShareable(self):
        return self.page.list_panel.kind in trade.SHAREABLE

    @QtCore.Property(bool, notify=entriesChanged)
    def listShared(self):
        lp = self.page.list_panel
        x = next((x for x in trade.lists(lp.kind) if x["id"] == lp.lid), None) if lp.kind else None
        return bool(x and trade.is_shared(x))

    @QtCore.Slot(bool)
    def setListShared(self, on):
        lp = self.page.list_panel
        self.setShared(lp.kind, lp.lid, on)

    def _friend(self):
        return getattr(self.page, "friend", None) or {}

    @QtCore.Property(str, notify=changed)
    def friendName(self):
        return self._friend().get("name") or "?"

    @QtCore.Property(str, notify=changed)
    def friendInfo(self):
        d = self._friend()
        n = sum(int(c[4] or 1) for c in d.get("cards") or [])
        return tr(f"{n} cards · wants {len(d.get('wants') or [])}")

    @QtCore.Property(str, notify=changed)
    def friendBack(self):
        return back_image(self._friend().get("back"))

    @QtCore.Property("QVariantList", notify=changed)
    def friendTabs(self):
        return [{"key": k, "text": self.page.tab_text(k)} for k, _ in self.page.FRIEND_TABS]

    @QtCore.Property(str, notify=changed)
    def friendTab(self):
        return self.page.friend_tab

    @QtCore.Property(str, notify=changed)
    def friendNote(self):
        fid = self.page.friend_id or ""
        return (self.ctrl.settings.get("friend_notes") or {}).get(fid, "")

    @QtCore.Slot(str)
    def setFriendNote(self, text):
        fid = self.page.friend_id or ""
        if not fid:
            return
        notes = dict(self.ctrl.settings.get("friend_notes") or {})
        text = (text or "")[:4000]
        if text.strip():
            notes[fid] = text
        else:
            notes.pop(fid, None)
        if notes != (self.ctrl.settings.get("friend_notes") or {}):
            self.ctrl.settings["friend_notes"] = notes
            self.ctrl.settings_changed()

    @QtCore.Slot(str)
    def setFriendTab(self, key):
        self._foreign_q = ""
        self.page.show_friend_tab(key)
        self._nav()

    def _wait(self, key):
        import time as _t
        return max(0, int(self.ctrl.SYNC_PAUSE - (_t.time() - float(self.ctrl.settings.get(key) or 0))))

    @QtCore.Property(int, notify=syncChanged)
    def shareWait(self):
        """Seconds until "Share with friends" works again (0 = now)."""
        return self._wait("share_last")

    @QtCore.Property(int, notify=syncChanged)
    def fetchWait(self):
        """Seconds until "Fetch from friends" works again (0 = now)."""
        return self._wait("fetch_last")

    def _tick(self):
        t = getattr(self, "_sync_t", None)
        if t is None:
            t = self._sync_t = QtCore.QTimer(self, interval=1000)
            t.timeout.connect(lambda: (self.host.syncChanged.emit(),
                                       t.stop() if self.shareWait <= 0 and self.fetchWait <= 0 else None))
        t.start()

    @QtCore.Slot()
    def shareNow(self):
        if self.ctrl.share_now():
            self._tick()
        self.host.syncChanged.emit()

    @QtCore.Slot()
    def fetchNow(self):
        if self.ctrl.fetch_now():
            self._tick()
        self.host.syncChanged.emit()

    @QtCore.Property("QVariantMap", notify=changed)
    def friendProfile(self):
        """The friend's "Binder" tab: card back, name and their displayed binders of all games – games you
        haven't installed are greyed out. (Sharing whole profiles comes later.)"""
        import games
        from cards import packs
        from net import relay
        d = self._friend()
        code = self._relay_code(d.get("id") or "")
        out = {"name": d.get("name") or "?", "back": back_image(d.get("back")), "binders": [], "shared": bool(code)}
        if not code:
            out["line"] = tr("Doesn't share a profile via the server – only the trade file.")
            return out
        s = self.ctrl.settings
        rf = relay.friends(s).get(code) or {}
        out["line"] = tr("Their shared binders – from all games")
        cur = games.current().key
        keys = [cur] + [k for k, _n, ready in games.GAMES if ready and k != cur]
        for g in keys:
            have = g == cur or packs.game_ready(g)
            for slot, title, _t, old in relay.friend_binders(s, code, g):
                out["binders"].append({"slot": slot, "title": title, "old": bool(old), "game": g,
                                       "icon": self._game_icon(g), "have": have,
                                       "tip": "" if have else tr(f"You don't have {games.nick_of(g)} installed")})
        out["backHidden"] = bool(rf.get("hide_back"))
        return out

    @staticmethod
    def _game_icon(key):
        from ui import quickshell
        return quickshell.Shell.game_icon(key)

    @QtCore.Slot(str, str)
    def openFriendBinder(self, slot, game=""):
        """Fetch the friend's binder and show it large (profile page, view only) – from any game, without switching."""
        import games
        from net import relay
        d = self._friend()
        code = self._relay_code(d.get("id") or "")
        if not code:
            return
        ctrl, nm, game = self.ctrl, d.get("name") or "?", game or games.current().key
        ctrl._relay_bg("binder_get", lambda: (relay.fetch_binder(ctrl.settings, code, game, slot), nm, game))

    @QtCore.Property(str, notify=changed)
    def foreign(self):
        return self.page.foreign if self.page.view == "friend" else ""

    @QtCore.Property("QVariantList", notify=changed)
    def friendGames(self):
        """Game toggles at the top of the friend: THEIR games – [{key, short, name, on, cards}] (QML sorts them like
        the game button at the top and adds installed/loading)."""
        import games
        fid = self.page.friend_id
        if not fid or self.page.view != "friend":
            return []
        on = self.page.toggled_games(fid)
        out = []
        for k in self.page.friend_games_of(fid):
            d = (self.page.friend if self.page.foreign == k else None) or self.page.foreign_file(k, fid) or {}
            n = sum(int(c[4] or 1) for c in (d.get("library") or d.get("cards") or []) if isinstance(c, list) and len(c) > 4)
            out.append({"key": k, "short": games.SHORT.get(k, k.upper()), "name": games.nick_of(k), "on": k in on,
                        "cards": n})
        return out

    @QtCore.Slot(str)
    def toggleFriendGame(self, key):
        self.page.toggle_friend_game(key)
        self._foreign_q = ""
        self._nav()

    @QtCore.Property(bool, notify=changed)
    def friendMulti(self):
        """∞ beside the friend's games: several at once (toggles) – off: one game, a click chooses it."""
        return self.page.friend_multi

    @QtCore.Slot(bool)
    def setFriendMulti(self, on):
        self.page.set_friend_multi(on)
        if not on:   # games may have gone off: a fresh search
            self._foreign_q = ""
        self.page.changed.emit()
        self._nav()

    def _nav(self):
        sh = getattr(self.ctrl, "shell", None)
        if sh is not None:
            sh._nav_all_games()   # ∞ on the game button while several games are mixed

    @QtCore.Property(bool, notify=changed)
    def friendMixed(self):
        """Several games at once (plain view): advanced search off, ∞ at the top."""
        return self.page.view == "friend" and len(self.page.plain) > 1 and self.page.friend_tab in self.page.CARD_TABS

    def _rows_of(self, game):
        """The friend's cards in one game: {"lib", "has", "wants"} – images and prices from that game's card database
        (as far as it is there, otherwise names only). Cached per game and friend file."""
        from cards import packs
        import games
        fid = self.page.friend_id
        d = (self.page.friend if self.page.foreign == game else None) or self.page.foreign_file(game, fid) or {}
        sig = (d.get("id"), d.get("updated"), len(d.get("cards") or []), len(d.get("library") or []))
        cache = getattr(self, "_foreign_cache", None) or {}
        hit = cache.get(game)
        if hit is not None and hit[0] == sig:
            return hit[1]
        lib = d.get("library")
        if lib is None and d.get("what") == "all":   # older files: the whole collection is in "cards"
            lib = d.get("cards")
        has = [] if lib is d.get("cards") else [c for c in d.get("cards") or [] if isinstance(c, list) and len(c) > 4]
        lib = [c for c in lib or [] if isinstance(c, list) and len(c) > 4]
        db = {}
        if packs.game_ready(game):
            try:
                db = carddb.by_prints({(c[0], c[1]) for c in lib + has}, game=game)
            except Exception:  # noqa: BLE001 – that game's database is still missing: names only
                db = {}
        chip = games.SHORT.get(game, game.upper())

        def row(c):
            r = db.get((str(c[0]).lower(), str(c[1])))
            name = (c[5] if len(c) > 5 and c[5] else None) or (r or {}).get("name") or f"{str(c[0]).upper()} #{c[1]}"
            price = None
            if r:
                price = r.get("eur_foil") if c[3] and r.get("eur_foil") is not None else r.get("eur")
            set_name = (r or {}).get("set_name") or str(c[0]).upper()
            facts = [f"{set_name} · #{c[1]}", (r or {}).get("rarity") or "",
                     tr("Language") + ": " + str(c[2] or "en").upper(), "Foil" if c[3] else "",
                     tr(f"{int(c[4] or 1)}× in their collection")]
            return {"game": game, "chip": chip, "name": name, "set": str(c[0]), "number": str(c[1]),
                    "lang": c[2] or "en", "foil": bool(c[3]), "count": int(c[4] or 1),
                    "img": db_image_of(r, game) if r and has_image(r, game) else "",
                    "info": f"{str(c[0]).upper()} #{c[1]}" + (" · Foil" if c[3] else "") + f" · {int(c[4] or 1)}×",
                    "setLine": f"{str(c[0]).upper()} #{c[1]}",
                    "facts": "<br>".join(html.escape(str(x[:1].upper() + x[1:])) for x in facts if x),
                    "price": eur(price) if price is not None else "", "setName": set_name}
        wants = [{"game": game, "chip": chip, "name": str(w[0]), "info": f"{int(w[1] or 1)}×", "img": "", "price": "",
                  "set": "", "number": "", "lang": "", "foil": False, "count": int(w[1] or 1), "setName": ""}
                 for w in d.get("wants") or [] if w]
        rows = {"lib": [row(c) for c in lib], "has": [row(c) for c in has], "wants": wants}
        cache[game] = (sig, rows)
        self._foreign_cache = cache
        return rows

    def _shown_rows(self):
        """Rows of the plain view: the tab's section of all switched-on games, filtered by the search."""
        from cards import packs
        sec = {"library": "lib", "has": "has", "wants": "wants"}.get(self.page.friend_tab, "lib")
        out = []
        for g in self.page.plain or ([self.page.foreign] if self.page.foreign else []):
            if packs.game_ready(g):
                out += self._rows_of(g)[sec]
        q = (getattr(self, "_foreign_q", "") or "").lower().strip()
        if q:
            out = [r for r in out if q in r["name"].lower() or q in r["setName"].lower()]
        out.sort(key=lambda r: r["name"].lower())
        self._shown_cache = out
        return sec, out

    @QtCore.Property("QVariant", notify=changed)
    def friendForeign(self):
        """Plain view (other game or several mixed): {games: [{game, nick, installed}], key, title, rows, more,
        empty, mixed, query} – the section of the open tab."""
        import games
        from cards import packs
        if not self.page.foreign or self.page.view != "friend":
            return {}
        shown = self.page.plain or [self.page.foreign]
        gs = [{"game": g, "nick": games.nick_of(g), "installed": packs.game_ready(g)} for g in shown]
        who = (self.page.friend or {}).get("name") or "?"
        sec, rows = self._shown_rows()
        title = {"lib": tr(f"{who}'s collection"), "has": tr("Has for trade"), "wants": tr("Wants")}[sec]
        nicks = " + ".join(g["nick"] for g in gs)
        lim = 1500 if sec == "wants" else 600
        q = getattr(self, "_foreign_q", "") or ""
        return {"game": shown[0], "nick": gs[0]["nick"], "games": gs,
                "installed": any(g["installed"] for g in gs), "missing": [g for g in gs if not g["installed"]],
                "key": sec, "title": title, "rows": rows[:lim], "more": max(0, len(rows) - lim),
                "mixed": len(shown) > 1, "query": q, "tab": self.page.friend_tab, "switchTip": self._switch_tip(),
                "empty": tr("No card matches the search.") if q else
                tr(f"{who} isn't sharing anything with you in {nicks} right now.")}

    def _switch_target(self):
        """Where „Advanced search“ leads in the plain view: the open game alone (if it is switched on) – otherwise
        switching to the first switched-on game. -> (game, switch needed?)"""
        import games
        cur = games.current().key
        shown = self.page.plain or ([self.page.foreign] if self.page.foreign else [])
        if cur in shown and self.page.friend_id and trade.friend(self.page.friend_id) is not None:
            return cur, False
        return (shown[0] if shown else ""), True

    def _switch_tip(self):
        import games
        game, switch = self._switch_target()
        if not game:
            return ""
        if not switch:
            return tr(f"Advanced search works with one game – click: show only {games.nick_of(game)} (full library)")
        return tr(f"Advanced search only in the open game – click: switch to {games.nick_of(game)} (stays with this friend)")

    @QtCore.Slot()
    def fullLibrary(self):
        """Click on the greyed-out „Advanced search“: full library with advanced search – in the open game right away
        (only that one switched on), otherwise the app switches to the friend's game and stays with the friend."""
        game, switch = self._switch_target()
        fid = self.page.friend_id
        if not game or not fid:
            return
        tab = self.page.friend_tab
        if not switch:
            self.page.friend_toggles[fid] = [game]
            self.page.apply_friend_mode()
            self._nav()
            return

        def after():
            self.ctrl.stream.show_page("trade")
            if self.page.reopen_friend(fid, game):
                self.page.show_friend_tab(tab)
            self._nav()
        if not self.ctrl.switch_game(game, then=after):
            self.page.toast(tr("Can't switch right now – wait for the running tasks first."))

    @QtCore.Slot(str)
    def setForeignQuery(self, q):
        self._foreign_q = q or ""
        self.host.changed.emit()

    @QtCore.Slot(str, result=str)
    def gameNick(self, game):
        import games
        return games.nick_of(game) if game else ""

    def _foreign_row(self, sec, i):
        rows = getattr(self, "_shown_cache", None)
        if rows is None:
            rows = self._shown_rows()[1]
        return rows[i] if 0 <= i < len(rows) else None

    @QtCore.Slot(str, int)
    def foreignToTrade(self, sec, i):
        """Put a card from their collection/"Has" (any game) into the trade – mixed ticket, you get it."""
        r = self._foreign_row(sec, i)
        if r is None or sec == "wants":
            return
        self.page.toast(self.page.add_other(r["game"], "get",
                                            [r["set"], r["number"], r["lang"], int(r["foil"]), 1, r["name"]]))

    @QtCore.Slot()
    def refreshForeign(self):
        """After a download: rebuild the view (now with images and prices)."""
        self._foreign_cache = None
        self.host.changed.emit()

    @QtCore.Property(str, notify=changed)
    def gameKeyNow(self):
        import games
        return games.current().key

    @QtCore.Property(str, notify=changed)
    def hasNote(self):
        return self.page.has_note

    @QtCore.Property(str, notify=changed)
    def libNote(self):
        return self.page.lib_note
