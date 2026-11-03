"""Trade page – the "Price alerts" folder and the alert editors: AlarmsBackend, moved out of ui/qtrade.py unchanged (docs/TRADE-SPLIT.md).
In QML as tradeAlarms; the host (TradeBackend) keeps shared state, helpers and signals."""
import json

from PySide6 import QtCore

from ui.qtrade import carddb, db_image, db_image_of, eur, games_key, has_image, tr, trade   # shared helpers of the trade page


class AlarmsBackend(QtCore.QObject):
    """Part of the trade page (docs/TRADE-SPLIT.md), in QML as tradeAlarms (alias ta): moved from TradeBackend
    unchanged – shared state, helpers and signals stay with the host (TradeBackend)."""
    alarmChanged = QtCore.Signal()   # forwarded from TradeBackend.alarmChanged (notify of the moved properties)
    detailChanged = QtCore.Signal()   # forwarded from TradeBackend.detailChanged (notify of the moved properties)
    listsChanged = QtCore.Signal()   # forwarded from TradeBackend.listsChanged (notify of the moved properties)
    entriesChanged = QtCore.Signal()   # forwarded from TradeBackend.entriesChanged (notify of the moved properties)
    # "Price alerts" folder: table in three sections
    ALARM_SECTIONS = (("list", "Whole lists", "Every card on the list reports when it drops or rises by this much"),
                      ("wish", "Wish cards", "Cheapest printing – any one"),
                      ("trade", "Trade cards", "Exactly your copy"))
    ALARM_SORTS = ("name", "where", "now", "rule")
    _alarm_q = ""

    def __init__(self, host):
        super().__init__(host)
        self.host, self.ctrl, self.page = host, host.ctrl, host.page
        for name in ('alarmChanged', 'detailChanged', 'listsChanged', 'entriesChanged'):   # the host's signal also refreshes the moved properties
            getattr(host, name).connect(getattr(self, name))

    @QtCore.Slot(str, str)
    def listAlarm(self, kind, lid):
        """Price alert for a list (menu on the tile): open the list, the editor expands at the top."""
        self.host.lists_b.openList(kind, lid)
        self.openAlarm(f"list:{kind}:{lid}")

    @property
    def _alarm_open(self):
        """Most recently opened editor (for places that only know about one)."""
        return self.host._open_alarms[-1] if self.host._open_alarms else ""

    @QtCore.Property("QVariantList", notify=alarmChanged)
    def alarmOpenKeys(self):
        return list(self.host._open_alarms)

    @QtCore.Property(int, notify=alarmChanged)
    def alarmRev(self):
        return self.host._alarm_rev

    def _alarm_touch(self):
        self.host._alarm_rev += 1
        self.host.alarmChanged.emit()

    @QtCore.Slot(str, int, result="QVariantMap")
    def alarmFormOf(self, key, rev=0):
        """Editor data of an open editor: limits, what is watched, which price – plus all printings
        (wanted card), the price table of the shown printing and its history. rev only for the QML binding."""
        from collection import alarms
        if not key or key not in self.host._open_alarms:
            return {}
        opts = self.host._alarm_opts.setdefault(key, {})
        f = alarms.form(self.ctrl.settings, key, opts)
        if not f["list"]:
            t = alarms.target_of(key)
            if t["kind"] == "wish":
                rows = alarms.prints_of([t["name"]]).get(t["name"], [])
                rows.sort(key=lambda r: (r.get("eur") is None, r.get("eur") or 0))
                f["prints"] = [{"id": r["id"], "set": (r.get("set_code") or "").upper(), "number": r.get("number") or "",
                                "sname": r.get("set_name") or "",
                                "img": db_image(r), "price": eur(r.get("eur") if r.get("eur") is not None else r.get("eur_foil")),
                                "mark": "main" if r["id"] == (f["psid"] or f["sid"]) else "", "date": ""}
                               for r in rows[:400]]
            f["facts"] = alarms.price_facts(f["sid"])
            f["table"] = alarms.price_table(f["sid"], 30, ["now", "avg", "range"], ["n", "f"], self.ctrl.settings)
            f["chart"] = self._alarm_chart(f["sid"], "f" if f["finish"] == "f" else "n",
                                           int(self.ctrl.settings.get("alarm_chart_days", 90)) or 90)
            if not f["chart"]:
                from cards import pricehist
                f["phHint"] = pricehist.hint(self.ctrl.settings,
                                             self.ctrl.ph_eta() if hasattr(self.ctrl, "ph_eta") else None)
            row = carddb.cards_by_ids({f["sid"]}).get(f["sid"]) if f["sid"] else None
            from cards import shoplinks
            f["shops"] = [m for m in shoplinks.market_links(row or {"name": t.get("name") or ""}, self.ctrl.settings,
                                                            foil=f.get("finish") == "f")
                          if m["key"] not in ("cardmarket", "tcgplayer")] if not f["list"] else []
            f["shown"] = (f"{(row.get('set_code') or '').upper()} #{row.get('number')} · {row.get('set_name') or ''}"
                          if row else "")
            fins = set(((row or {}).get("finishes") or "").split(",")) - {""}
            if fins and f.get("mode") == "print":   # exactly one printing: only what exists of it
                has_n, has_f = "nonfoil" in fins, bool(fins & {"foil", "etched"})
                f["finishes"] = [dict(x, disabled=(x["key"] == "n" and not has_n) or (x["key"] == "f" and not has_f))
                                 for x in f.get("finishes") or []]
        return f

    @QtCore.Slot(int)
    def setAlarmChartDays(self, days):
        self.ctrl.settings["alarm_chart_days"] = int(days)
        self.ctrl.settings_changed()
        self._alarm_touch()

    @QtCore.Slot(str)
    def alarmShowPrint(self, sid):
        """Printing clicked in the alert editor's strip: also show it in the detail view on the right."""
        row = carddb.cards_by_ids({sid}).get(sid) if sid else None
        if row:
            self.page.alarm_side.show(row, "en", False)
            self.host.detailChanged.emit()

    def _alarm_chart(self, sid, fin, days=90):
        """Price history as in the detail view (Cardmarket + TCGplayer converted, normal + foil); days 0 = all."""
        import datetime
        from cards import currency
        from cards import pricehist
        h = pricehist.series(sid) if sid else None
        if not h:
            return {}
        lines = []
        import games
        fw = tr(games.current().foil_word)
        for shop, name, col, f2 in (("c", "Cardmarket", "", "n"), ("t", "TCGplayer", "", "n"),
                                    ("c", f"Cardmarket {fw}", "", "f"), ("t", f"TCGplayer {fw}", "", "f")):
            pts = h.get(shop + f2) or []
            if not pts:
                continue
            cut = pts[-1][0] - datetime.timedelta(days=days) if days else None
            out = []
            for d, v in pts:
                if cut is not None and d < cut:
                    continue
                e = currency.from_usd(v) if shop == "t" else v
                if e is not None:
                    out.append([QtCore.QDateTime(QtCore.QDate(d.year, d.month, d.day), QtCore.QTime(12, 0))
                                .toMSecsSinceEpoch(), float(e), float(v)])
            if out:
                lines.append({"name": name, "shop": shop, "foil": f2 == "f", "dim": f2 != fin,
                              "unit": "$" if shop == "t" else "€", "pts": out})
        return {"lines": lines, "days": days, "finish": fin, "both": False,
                "ranges": [{"days": 30, "text": tr("30 d")}, {"days": 90, "text": tr("90 d")}]} \
            if lines else {}

    @QtCore.Slot(str, str, str)
    def setAlarmOptOf(self, key, k, v):
        """In an open editor: change src / basis / finish / psid (only saved with "Save")."""
        if key not in self.host._open_alarms:
            return
        opts = self.host._alarm_opts.setdefault(key, {})
        if k == "mode":
            k, v = "psid", "" if v == "cheapest" else (opts.get("psid") or self.alarmFormOf(key, 0).get("sid") or "")
        opts[k] = v
        self._alarm_touch()

    @QtCore.Slot(str)
    def openAlarm(self, key):
        """Open the inline editor (or close it if it is already open). Other open editors stay open – nothing
        gets lost; you close them yourself (Save / Cancel / ✎)."""
        if key in self.host._open_alarms:
            self.host._close(key)
        else:
            self.host._open_add(key)
        self._alarm_touch()
        self.host.listsChanged.emit()

    @QtCore.Slot(str)
    def closeAlarmOf(self, key):
        self.host._close(key)
        self._alarm_touch()
        self.host.listsChanged.emit()

    @QtCore.Slot(str, bool, float, bool, float)
    def saveAlarmOf(self, key, a_on, a, b_on, b):
        from collection import alarms
        if key not in self.host._open_alarms:
            return
        alarms.save_form(self.ctrl.settings, key, a_on, a, b_on, b, self.ctrl.collection,
                         self.host._alarm_opts.get(key) or {})
        self.ctrl.settings_changed()
        self.host._close(key)
        self._alarms_touched()

    @QtCore.Slot(str)
    def deleteAlarm(self, key):
        from collection import alarms
        alarms.remove(self.ctrl.settings, key, self.ctrl.collection)
        self.ctrl.settings_changed()
        self.host._close(key)
        self._alarms_touched()

    def _alarms_touched(self):
        self.host._alarm_rev += 1
        self.host.alarmChanged.emit()
        self.host.listsChanged.emit()
        self.host.entriesChanged.emit()

    def _alarm_rows(self):
        """Rows of all games: the open one in full (prices, images, editing), the others from what was saved –
        a click switches there. Remembered while nothing they come from changed (_alarm_key): building them asks the
        card database for every alert – that was ~12 % of opening a friend (every open_me)."""
        import games
        key = self._alarm_key()
        if key != getattr(self, "_rows_key", None):
            cur = games.current().key
            self._rows = [dict(r, game=cur, other=False) for r in self._alarm_rows_here()] + self._alarm_rows_other(cur)
            self._rows_key = key
        return [dict(r) for r in self._rows]   # alarmSections writes "chip" into its rows

    def _alarm_key(self):
        """Everything the rows come from: the alerts themselves (+ their hits), alerts being added, game and language,
        the collection (list values), the lists' files and the card databases (prices) of every game involved."""
        import hashlib
        import json
        import games
        from collection import alarms
        from system import i18n
        st = self.ctrl.settings
        mine = alarms.all_alarms(st) + alarms.list_alarms(st, every=True)
        involved = {games.current().key} | {alarms.game_of(a) for a in mine}

        def mtime(p):
            try:
                return p.stat().st_mtime_ns
            except OSError:
                return 0
        db = {g: carddb.path_of(g) for g in involved}   # prices: the database or its write-ahead log changes
        files = sorted((g, mtime(trade._lists_file(g)), mtime(db[g]), mtime(db[g].with_name(db[g].name + "-wal")))
                       for g in involved)
        blob = json.dumps([mine, sorted(self.host._open_alarms), files], sort_keys=True, default=str)
        return (self.host._alarm_rev, games.current().key, i18n.LANG, self.ctrl.collection.rev,
                hashlib.sha1(blob.encode()).hexdigest())

    def _alarm_rows_other(self, cur):
        from collection import alarms
        st = self.ctrl.settings
        out = []
        names = {"wish": tr("Wishlist"), "have": tr("Trade list"), "custom": tr("own list")}
        lists_of = {}
        for a in alarms.list_alarms(st, every=True):
            g = alarms.game_of(a)
            if g == cur:
                continue
            if g not in lists_of:
                lists_of[g] = {(r["kind"], r["id"]): r for r in trade.game_overview(g)}
            r = lists_of[g].get((a["lkind"], a["lid"]))
            if r is None:
                continue
            nhit = sum(1 for v in (a.get("hit") or {}).values() if v)
            out.append({"key": f"other:{g}:list:{a['lkind']}:{a['lid']}", "section": "list", "game": g, "other": True,
                        "icon": {"wish": "star", "have": "trade"}.get(a["lkind"], "bookmark"),
                        "name": tr(r["name"]) if r["main"] else r["name"],
                        "where": names.get(a["lkind"], "") + (tr(f" · {r['count']} cards") if r["count"] is not None else ""),
                        "now": "–", "nowVal": -1.0, "rule": alarms.list_rule(a) + (f" · {tr("triggered")}: {nhit}" if nhit else ""),
                        "hit": nhit > 0, "imgs": [], "draft": False})
        for a in alarms.all_alarms(st):
            g = alarms.game_of(a)
            if g == cur:
                continue
            last, imgs = a.get("last"), []
            try:
                if a["kind"] == "trade":
                    r = carddb.cards_by_ids({a.get("sid")}, game=g).get(a.get("sid"))
                    if r:
                        imgs = [db_image_of(r, g)] if has_image(r, g) else []
                        p = r.get("eur_foil") if a.get("foil") and r.get("eur_foil") is not None else r.get("eur")
                        last = last if last is not None else p   # most recently checked (with all corrections) first
                else:
                    rows = alarms.prints_by_price(a["name"], 30, game=g)
                    imgs = [db_image_of(r, g) for r in rows if has_image(r, g)][:9]
                    ps = [r.get("eur") for r in rows if r.get("eur") is not None]
                    last = last if last is not None else (min(ps) if ps else None)
            except Exception:  # noqa: BLE001 – the other game's database is missing
                pass
            where = f"{(a.get('set') or '').upper()}{' · Foil' if a.get('foil') else ''}" if a["kind"] == "trade" \
                else tr("cheapest printing")
            out.append({"key": f"other:{g}:card:" + alarms.card_key(a)[5:], "section": a["kind"], "game": g,
                        "other": True, "icon": "bell",
                        "name": a["name"], "where": where, "now": alarms.eur(last) if last is not None else "–",
                        "nowVal": float(last) if last is not None else -1.0, "rule": alarms.text_of(a),
                        "hit": bool(a.get("hit")), "imgs": [i for i in imgs if i], "draft": False})
        return out

    def _alarm_rows_here(self):
        from collection import alarms
        st = self.ctrl.settings
        names = {"wish": tr("Wishlist"), "have": tr("Trade list"), "custom": tr("own list")}
        out = []
        for a in alarms.list_alarms(st):
            x = next((x for x in trade.lists(a["lkind"]) if x["id"] == a["lid"]), None)
            if x is None:
                continue
            main = a["lid"] in (trade.MAIN_WISH, trade.MAIN_HAVE)
            entries = trade.list_entries(a["lkind"], a["lid"], self.ctrl.collection.items)
            value, art, _artist = self.host.lists_b._list_value_art(a["lkind"], entries)
            hits = sorted(k for k, v in (a.get("hit") or {}).items() if v)   # which cards triggered
            nhit = len(hits)
            out.append({"key": f"list:{a['lkind']}:{a['lid']}", "section": "list",
                        "icon": {"wish": "star", "have": "trade"}.get(a["lkind"], "bookmark"),
                        "name": tr(x["name"]) if main else x["name"],
                        "where": f"{names.get(a['lkind'], '')} · " + tr(f"{len(entries)} cards")
                        + (f" · {alarms.opts_text(alarms.opts_of(a))}" if alarms.opts_text(alarms.opts_of(a)) else ""),
                        "now": eur(value), "nowVal": value,
                        "rule": alarms.list_rule(a) + ((" · " + tr("triggered") + ": " + ", ".join(hits[:3])
                                                        + (f" +{nhit - 3}" if nhit > 3 else "")) if nhit else ""),
                        "hit": nhit > 0, "imgs": [art] if art else [], "draft": False})
        cards = alarms.alarms(st)
        pm = alarms.current_prices(cards)
        rows = carddb.cards_by_ids({a["sid"] for a in cards if a["kind"] == "trade"}) if carddb.exists() else {}
        for a in cards:
            p = pm.get(alarms.key_of(a))
            out.append(self.host._card_row(a, p, rows, alarms.text_of(a), bool(a.get("hit"))))
        for k in self.host._open_alarms:   # new alerts, not saved yet: show the row already
            if k.startswith("list:") or any(r["key"] == k for r in out):
                continue
            t = alarms.target_of(k)
            if t is not None:
                p = alarms.current_prices([t]).get(alarms.key_of(t))
                out.append(dict(self.host._card_row(t, p, rows, tr("new – not saved yet"), False), draft=True))
        return out

    @QtCore.Property("QVariantList", notify=listsChanged)
    def alarmSections(self):
        """[{key, title, sub, rows}] – only sections with rows. Sorting can be combined: column header (name,
        what, price, alert) – on top of that "by game" and "triggered first". Search and game chips filter."""
        import games
        st = self.ctrl.settings
        col, desc = self.alarmSort, bool(st.get("alarm_sort_desc"))
        if col == "now":
            key = (lambda r: r["nowVal"])
        elif col == "rule":   # rule: triggered first (▼), then by text
            key = (lambda r: (1 if r.get("hit") else 0, str(r.get("rule") or "").lower()))
        else:
            key = (lambda r: str(r.get(col) or "").lower())
        rows = self._alarm_rows()
        multi = len({r["game"] for r in rows}) > 1
        off = set(st.get("alarm_games_off") or [])
        q = self._alarm_q.strip().lower()
        rows = [r for r in rows if r["game"] not in off and (not q or q in (r["name"] + " " + r["where"]).lower())]
        rows = sorted(rows, key=key, reverse=desc)
        by = self.alarmSortBy
        if "hits" in by:
            rows.sort(key=lambda r: not r.get("hit"))
        if "game" in by:   # the open game first, then the others in the fixed order
            order = [games.current().key] + [k for k, *_ in games.GAMES]
            rows.sort(key=lambda r: order.index(r["game"]) if r["game"] in order else 99)
        for r in rows:
            r["chip"] = games.SHORT.get(r["game"], r["game"].upper()) if multi else ""
        out = []
        for sk, title, sub in self.ALARM_SECTIONS:
            part = [r for r in rows if r["section"] == sk]
            if part:
                out.append({"key": sk, "title": tr(title), "sub": tr(sub), "rows": part})
        return out

    @QtCore.Slot(str)
    def setAlarmQuery(self, q):
        self._alarm_q = q or ""
        self.host.listsChanged.emit()

    @QtCore.Property("QVariantList", notify=listsChanged)
    def alarmSortBy(self):
        """In addition to the column: "game" (by game) and/or "hits" (triggered first)."""
        return [k for k in self.ctrl.settings.get("alarm_sort_by") or [] if k in ("game", "hits")]

    @QtCore.Slot(str)
    def toggleAlarmSortBy(self, k):
        cur = self.alarmSortBy
        self.ctrl.settings["alarm_sort_by"] = [x for x in cur if x != k] if k in cur else cur + [k]
        self.ctrl.settings_changed()
        self.host.listsChanged.emit()

    @QtCore.Property("QVariantList", notify=listsChanged)
    def alarmGames(self):
        """Game chips above the table: only when there are alerts in more than one game. [{key, text, tip}]"""
        import games
        from collection import alarms
        st = self.ctrl.settings
        have = {alarms.game_of(a) for a in alarms.all_alarms(st) + alarms.list_alarms(st, every=True)}
        if len(have) < 2:
            return []
        return [{"key": k, "text": games.SHORT.get(k, k.upper()), "tip": n} for k, n, _ in games.GAMES if k in have]

    @QtCore.Property("QVariantList", notify=listsChanged)
    def alarmGamesOn(self):
        off = set(self.ctrl.settings.get("alarm_games_off") or [])
        return [g["key"] for g in self.alarmGames if g["key"] not in off]

    @QtCore.Slot(str)
    def toggleAlarmGame(self, k):
        off = list(self.ctrl.settings.get("alarm_games_off") or [])
        self.ctrl.settings["alarm_games_off"] = [x for x in off if x != k] if k in off else off + [k]
        self.ctrl.settings_changed()
        self.host.listsChanged.emit()

    @QtCore.Property(str, notify=listsChanged)
    def alarmSort(self):
        c = self.ctrl.settings.get("alarm_sort") or "name"
        return c if c in self.ALARM_SORTS else "name"

    @QtCore.Property(bool, notify=listsChanged)
    def alarmSortDesc(self):
        return bool(self.ctrl.settings.get("alarm_sort_desc"))

    @QtCore.Slot(str)
    def setAlarmSort(self, col):
        """Click on a column header: sort by it, a second click reverses."""
        st = self.ctrl.settings
        if col == self.alarmSort:
            st["alarm_sort_desc"] = not st.get("alarm_sort_desc")
        else:
            st["alarm_sort"], st["alarm_sort_desc"] = col, col in ("now", "rule")
        self.ctrl.settings_changed()
        self.host.listsChanged.emit()

    @QtCore.Slot(str)
    def alarmClicked(self, key):
        """Row clicked: card → detail view on the right (with comparison), list → open the list. Alert from
        another game: switch there, the price alerts folder stays open."""
        from collection import alarms
        if key.startswith("other:"):
            import games
            _, g, what, rest = key.split(":", 3)
            if what == "list":
                kind, lid = rest.split(":", 1)

                def show():
                    self.ctrl.stream.show_page("trade")
                    self.host.lists_b.openList(kind, lid)
                if not self.ctrl.switch_game(g, then=show):
                    self.page.toast(tr(f"Can't switch to {games.name_of(g)} right now – wait for the running tasks first."))
                return
            self.host._show_foreign(g, json.loads(rest))
            return
        if key.startswith("list:"):
            _, kind, lid = key.split(":", 2)
            self.host.lists_b.openList(kind, lid)
            return
        t = alarms.target_of(key)
        if t is None:
            return
        if t["kind"] == "trade":
            row = carddb.cards_by_ids({t.get("sid")}).get(t.get("sid"))
        else:   # the printing the alert currently follows (fixed, or the cheapest according to its rules)
            a = alarms.find(self.ctrl.settings, "wish", t["name"]) or t
            sid = alarms.prices([("x", a)])["x"][1]
            row = carddb.cards_by_ids({sid}).get(sid) if sid else (alarms.prints_by_price(t["name"], 1) or [None])[0]
        if row:
            self.host._foreign = None
            self.page.alarm_side.show(row, "en", bool(t.get("foil")))
        else:   # no printing at all in the database: empty card instead of the last one shown
            self.host._show_foreign(games_key(), t, empty=True)
        self.host.detailChanged.emit()

    @QtCore.Property(QtCore.QObject, constant=True)
    def alarmDetail(self):
        return self.host.adet_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def alarmCompare(self):
        return self.host.acmp_b

    @QtCore.Property(bool, notify=detailChanged)
    def alarmDetailOpen(self):
        return not self.page.alarm_side.card.isHidden()

    @QtCore.Property(bool, notify=detailChanged)
    def alarmCompareOpen(self):
        side = self.page.alarm_side
        return not side.card.isHidden() and not side.cmp.isHidden()

    @QtCore.Slot()
    def alarmEscape(self):
        side = self.page.alarm_side
        if not side.cmp.isHidden():
            side.host.close_compare()
        else:
            side.close()
        self.host.detailChanged.emit()

    @QtCore.Slot(str, result="QVariantList")
    def alarmSuggest(self, text):
        """Card names for typing (up to 8) – in all games the user has, and in every language; the English
        name is chosen (the same link on the platforms)."""
        import games
        text = (text or "").strip()
        if len(text) < 2:
            return []
        keys = [g["key"] for g in self.host.lists_b.listGames] or [games.current().key]
        multi = len(keys) > 1
        out = []
        for g in keys:
            try:
                hits = carddb.suggest_names(text, game=g, limit=8 if not multi else 5)
            except Exception:  # noqa: BLE001
                hits = []
            for en, shown in hits:
                info = (games.SHORT.get(g, g.upper()) if multi else "") + \
                    (("  ·  " if multi else "") + shown if shown.lower() != en.lower() else "")
                out.append({"name": en, "count": info, "game": g})
        return out[:10]

    @QtCore.Slot(str, str, result=str)
    def newCardAlarmIn(self, name, game):
        """Suggestion from another game chosen: switch there (loading time) and open the alert there."""
        import games
        if not game or game == games.current().key:
            return self.newCardAlarm(name)

        def then():
            self.ctrl.show_alarms()
            self.newCardAlarm(name)
        if not self.ctrl.switch_game(game, then=then):
            return tr("Can't switch right now – wait for the running tasks first.")
        return ""

    @QtCore.Slot(str, result=str)
    def newCardAlarm(self, name):
        """Card chosen: row with an open editor (not saved yet). -> error text or ""."""
        from collection import alarms
        name = (name or "").strip()
        if not name:
            return ""
        row = carddb.by_names([name]).get(name.lower()) if carddb.exists() else None
        if carddb.exists() and row is None:
            return tr(f"I don't know “{name}” – please use the exact card name.")
        self.host._open_add(alarms.card_key({"kind": "wish", "name": row["name"] if row else name}))
        self._alarm_touch()
        self.host.listsChanged.emit()
        return ""

    @QtCore.Property("QVariantList", notify=listsChanged)
    def alarmListChoices(self):
        """Lists without an alert – to click on for "+ Alert for a list"."""
        from collection import alarms
        names = {"wish": tr("Wishlist"), "have": tr("Trade list"), "custom": tr("own list")}
        import games
        have = {a["lid"] for a in alarms.list_alarms(self.ctrl.settings)}
        out = [{"key": f"list:{k}:{x['id']}", "kind": names[k], "chip": "",
                "name": tr(x["name"]) if x["id"] in (trade.MAIN_WISH, trade.MAIN_HAVE) else x["name"]}
               for k in ("wish", "have", "custom") for x in trade.lists(k) if x["id"] not in have]
        cur = games.current().key
        for g in [x["key"] for x in self.host.lists_b.listGames if x["key"] != cur]:
            taken = {(a["lkind"], a["lid"]) for a in alarms.list_alarms(self.ctrl.settings, every=True)
                     if alarms.game_of(a) == g}
            for r in trade.game_overview(g):
                if (r["kind"], r["id"]) not in taken:
                    out.append({"key": f"other:{g}:{r['kind']}:{r['id']}", "kind": names[r["kind"]],
                                "chip": games.SHORT.get(g, g.upper()),
                                "name": tr(r["name"]) if r["main"] else r["name"]})
        if out and any(o["chip"] for o in out):
            for o in out:
                o["chip"] = o["chip"] or games.SHORT.get(cur, cur.upper())
        return out

    @QtCore.Slot(str)
    def newListAlarm(self, key):
        """List chosen: create an alert with default values and open the editor in its row. List from another
        game: switch there (loading time) and create it there."""
        from collection import alarms
        if key.startswith("other:"):
            _, g, kind, lid = key.split(":", 3)

            def then():
                self.ctrl.show_alarms()
                self.newListAlarm(f"list:{kind}:{lid}")
            if not self.ctrl.switch_game(g, then=then):
                self.page.toast(tr("Can't switch right now – wait for the running tasks first."))
            return
        f = alarms.form(self.ctrl.settings, key)
        alarms.save_form(self.ctrl.settings, key, f["a"]["on"], f["a"]["value"], f["b"]["on"], f["b"]["value"],
                         self.ctrl.collection)
        self.ctrl.settings_changed()
        self.host._open_add(key)
        self._alarms_touched()

    def _entry_alarm(self, kind, w, nm):
        """Alert target of an entry: wishlist/own list by name, trade list exactly your own printing."""
        if kind in ("wish", "custom"):
            return {"kind": "wish", "name": nm}
        if isinstance(w, dict) and not w.get("missing") and w.get("id"):
            from collection.collection import scryfall_id
            card = w.get("card") or {}
            return {"kind": "trade", "name": nm, "sid": scryfall_id(w["id"]), "foil": bool(w.get("foil")),
                    "set": str(w.get("set") or card.get("set") or "").upper()}
        return None

    @QtCore.Slot(str)
    def entryAlarm(self, key):
        """Bell on an entry: set/change a price alert for exactly this card."""
        from collection import alarms
        e = self.host._key(key)
        if e is None:
            return
        target = self._entry_alarm(self.page.list_panel.kind, e[4], e[1])
        if target:
            self.openAlarm(alarms.card_key(target))
        self.host.entriesChanged.emit()

    @QtCore.Property(bool, notify=entriesChanged)
    def listAlarmOn(self):
        from collection import alarms
        return alarms.find_list(self.ctrl.settings, self.page.list_panel.lid) is not None

    @QtCore.Property(str, notify=entriesChanged)
    def editorAlarmKey(self):
        lp = self.page.list_panel
        return f"list:{lp.kind}:{lp.lid}"

    @QtCore.Slot()
    def editorListAlarm(self):
        self.openAlarm(self.editorAlarmKey)
        self.host.entriesChanged.emit()
