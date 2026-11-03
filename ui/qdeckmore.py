"""Deck comparison and "Bent°Corner suggestion" in Qt Quick (qml/components/DeckCompare.qml, DeckSuggest.qml).

The logic lives in deckcore.CompareView and deckcore.SuggestPage; these objects pass lists, bars, assessment,
candidates and suggestions to QML and the clicks back.
"""
from PySide6 import QtCore

from ui import quickimages
from system.i18n import tr


def _img(r):
    if not r:
        return ""
    from cards import library
    from ui.librarycore import THUMBS
    local = THUMBS / f"{r['id']}_en_n.jpg"
    url = r.get("img_normal") or library.image_url(r["set_code"], r["number"], "en", "normal")
    return quickimages.register(f"{r['id']}_en_n", local, url, local)


class CompareBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, page, parent=None):
        super().__init__(parent)
        self.ctrl, self.page, self.v = ctrl, page, page.compare
        self.v.changed.connect(self.changed.emit)

    def _side(self, which):
        return self.v.a if which == "a" else self.v.b

    @QtCore.Property("QVariantList", notify=changed)
    def decks(self):
        return [{"key": str(i), "text": d["name"] + (f"  ·  📁 {d['folder']}" if d.get("folder") else "")}
                for i, d in enumerate(self.v.all_decks)]

    @QtCore.Property(str, notify=changed)
    def a(self):
        return str(self.v.index_of("a"))

    @QtCore.Property(str, notify=changed)
    def b(self):
        return str(self.v.index_of("b"))

    @QtCore.Slot(str, str)
    def pick(self, which, key):
        self.v.pick(which, int(key))

    @QtCore.Slot(str)
    def openEditor(self, which):
        d = self._side(which).deck
        if d:
            self.page.open_deck(d)

    @QtCore.Slot()
    def back(self):
        self.page.show_overview()

    @QtCore.Property(str, notify=changed)
    def infoA(self):
        return self.v.a.info

    @QtCore.Property(str, notify=changed)
    def infoB(self):
        return self.v.b.info

    @QtCore.Property("QVariantList", notify=changed)
    def rowsA(self):
        return self.v.a.rows

    @QtCore.Property("QVariantList", notify=changed)
    def rowsB(self):
        return self.v.b.rows

    @QtCore.Property(str, notify=changed)
    def verdict(self):
        return self.v.verdict

    @staticmethod
    def _bars(rows):
        out = []
        for label, a, b, ta, tb, better in rows:
            a, b = float(a or 0), float(b or 0)
            m = max(abs(a), abs(b), 1e-9)
            if better is None or a == b:
                sa = sb = better is None
            else:
                best = max(a, b) if better == "high" else min(a, b)
                sa, sb = a == best, b == best
            out.append({"label": label, "fa": min(1.0, abs(a) / m), "fb": min(1.0, abs(b) / m), "ta": ta, "tb": tb,
                        "sa": bool(sa), "sb": bool(sb)})
        return out

    @QtCore.Property("QVariantList", notify=changed)
    def power(self):
        return self._bars(self.v.power)

    @QtCore.Property("QVariantList", notify=changed)
    def stats(self):
        return self._bars(self.v.stats)

    @QtCore.Property(str, notify=changed)
    def note(self):
        return self.v.note


class SuggestBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, page, parent=None):
        super().__init__(parent)
        self.ctrl, self.page, self.s = ctrl, page, page.suggest
        self._own, self._kind = [], ""
        self._t = QtCore.QTimer(self, singleShot=True, interval=0, timeout=self.changed.emit)
        s = self.s
        old_start = s.start

        def start():
            self._kind = ""
            old_start()
        s.start = start
        s.changed.connect(self._t.start)
        page.loader.ready.connect(lambda _k: self._t.start())
        self._own_t = QtCore.QTimer(self, singleShot=True, interval=250, timeout=self._own_find)

    @QtCore.Slot()
    def back(self):
        self.page.show_overview()

    @QtCore.Property("QVariantList", constant=True)
    def kinds(self):
        return [{"key": k, "text": tr(label)} for k, label in self.s.KINDS]

    @QtCore.Property(str, notify=changed)
    def kind(self):
        return self._kind

    @QtCore.Slot(str)
    def run(self, kind):
        self._kind = kind
        self.s.run(kind)

    @QtCore.Property(str, notify=changed)
    def status(self):
        return self.s.status.text()

    # Commander candidates
    @QtCore.Property(bool, notify=changed)
    def picking(self):
        return bool(self.s.picking)

    @QtCore.Property("QVariantList", notify=changed)
    def picks(self):
        return [{"i": i, "text": r["name"].split(" // ")[0], "on": on, "tip": tip}
                for i, (on, r, tip) in enumerate(self.s.picks)]

    @QtCore.Slot(int)
    def togglePick(self, i):
        self.s.toggle_pick(i)

    @QtCore.Slot()
    def check(self):
        self.s.check()

    @QtCore.Property(str, constant=True)
    def checkMax(self):
        from collection import suggest
        return str(suggest.CHECK_MAX)

    # own commander (search in the card database)
    @QtCore.Slot(str)
    def setOwnSearch(self, t):
        self._own_text = t
        self._own_t.start()

    def _own_find(self):
        from cards import carddb
        from collection import suggest
        text = (getattr(self, "_own_text", "") or "").strip()
        self._own = []
        if len(text) >= 2 and carddb.exists():
            rows = carddb.search(text, limit=60, sort="edhrec", no_tokens=True, one_per_name=True,
                                 formats=["commander"])
            self._own = [r for r in rows if suggest._legendary_creature(r)][:10]
            self._own_none = not self._own
        else:
            self._own_none = False
        self._t.start()

    @QtCore.Property("QVariantList", notify=changed)
    def ownHits(self):
        owned = {r["name"] for r in getattr(self.s, "pool", [])}
        return [{"i": i, "text": r["name"].split(" // ")[0] + ("  ✓" if r["name"] in owned else ""),
                 "tip": tr("✓ = you already own it") if r["name"] in owned else
                 tr("You don't own it (yet) – the deck is still built from your cards")}
                for i, r in enumerate(self._own)]

    @QtCore.Property(bool, notify=changed)
    def ownNone(self):
        return bool(getattr(self, "_own_none", False))

    @QtCore.Slot(int)
    def ownPick(self, i):
        if 0 <= i < len(self._own):
            self.s.check([self._own[i]])

    # Suggestions
    @QtCore.Property("QVariantList", notify=changed)
    def ideas(self):
        out = []
        for i, (idea, kind) in enumerate(self.s.ideas):
            title, info, art = self.s.idea_view(idea, kind)
            out.append({"i": i, "title": title, "info": info, "img": _img(art)})
        return out

    @QtCore.Slot(int)
    def pickIdea(self, i):
        if 0 <= i < len(self.s.ideas):
            self.s.pick(i, self.kind or self.s.ideas[i][1])


class BrewBackend(QtCore.QObject):
    """Bent°Corner Brew (brew.py): format, colors, play style -> suggestions -> rough draft in the deck builder."""
    changed = QtCore.Signal()
    resultsChanged = QtCore.Signal()

    def __init__(self, ctrl, page, suggest_b, parent=None):
        super().__init__(parent)
        self.ctrl, self.page, self.sg = ctrl, page, suggest_b
        self._fmt, self._colors, self._key = "commander", "", ""
        self._pool, self._pool_key, self._ov = None, None, None
        self._results, self._busy, self._token = [], False, 0

    # ---------- Collection ----------
    def _get_pool(self):
        from collection import suggest
        key = (getattr(self.ctrl.collection, "rev", 0), len(self.page.owned_id))
        if self._pool is None or key != self._pool_key:
            self._pool = suggest.owned_rows(self.page.free_owned())
            self._pool_key = key
        return self._pool

    def _overview(self):
        from collection import brew
        if self._ov is None:
            self._ov = brew.overview(self._get_pool(), self._fmt, self._colors)
        return self._ov

    def _reset(self):
        self._ov = None
        self.changed.emit()

    @QtCore.Slot()
    def enter(self):
        self._pool, self._ov, self._results = None, None, []
        self.changed.emit()
        self.resultsChanged.emit()

    # ---------- Selection ----------
    @QtCore.Property(str, notify=changed)
    def fmt(self):
        return self._fmt

    @QtCore.Slot(str)
    def setFmt(self, f):
        self._fmt = f
        self._reset()

    @QtCore.Property(str, notify=changed)
    def colors(self):
        return self._colors

    @QtCore.Slot(str)
    def toggleColor(self, c):
        cur = set(self._colors)
        (cur.discard if c in cur else cur.add)(c)
        self._colors = "".join(x for x in "WUBRG" if x in cur)
        self._reset()

    @QtCore.Slot()
    def clearColors(self):
        self._colors = ""
        self._reset()

    @QtCore.Property(str, notify=changed)
    def key(self):
        return self._key

    @QtCore.Slot(str)
    def setKey(self, k):
        self._key = "" if k == self._key else k
        self.changed.emit()

    @QtCore.Property("QVariantMap", notify=changed)
    def counts(self):
        ov = self._overview()
        return dict(ov["per_color"], total=ov["total"])

    @QtCore.Property("QVariantList", notify=changed)
    def archetypes(self):
        ov = self._overview()
        top = max([a["count"] for a in ov["archetypes"]] + [1])
        return [dict(a, frac=a["count"] / top, sel=a["key"] == self._key) for a in ov["archetypes"]]

    @QtCore.Property(bool, notify=changed)
    def empty(self):
        return not self.page.owned_id

    @QtCore.Property(str, notify=changed)
    def warning(self):
        """Anything odd about the collection (e.g. cards missing from the card database) – shown above suggestions."""
        from collection import brew
        key = (getattr(self.ctrl.collection, "rev", 0), len(self.page.owned_id))
        if getattr(self, "_warn_key", None) != key:  # only re-check when the collection has changed
            try:
                warn = [t for lvl, t in brew.diagnose(self.page.owned_id, [], self._fmt) if lvl == "warn"]
            except Exception:  # noqa: BLE001
                warn = []
            self._warn_key, self._warn = key, "<br>".join("⚠ " + t for t in warn)
        return self._warn

    # ---------- Suggestions ----------
    @QtCore.Property(bool, notify=resultsChanged)
    def busy(self):
        return self._busy

    @QtCore.Property("QVariantList", notify=resultsChanged)
    def results(self):
        return [{k: v for k, v in x.items() if k != "data"} for x in self._results]

    @QtCore.Slot()
    def run(self):
        from collection import brew
        from ui.librarycore import run_async
        self.sg.s._clear()  # clear "Surprise me" results
        self._token += 1
        token, fmt, colors, key = self._token, self._fmt, self._colors, self._key or None
        pool = self._get_pool()
        self._busy, self._results = True, []
        self.resultsChanged.emit()

        def work():
            if fmt == "commander":
                return brew.commander_ideas(pool, colors, key)
            return brew.sixty_ideas(pool, fmt, colors, key)
        run_async(self, work, lambda res, err: self._done(token, res, err))

    @QtCore.Slot()
    def surprise(self):
        """The previous way: Bent°Corner searches by itself (commander with EDHREC check, 60-card by color + theme)."""
        self._results = []
        self.resultsChanged.emit()
        self.sg.run(self._fmt)

    def _done(self, token, res, err):
        from collection import suggest
        if token != self._token:
            return
        self._busy = False
        out = []
        for x in res or []:
            if self._fmt == "commander":
                r = x["row"]
                info = tr(f"{x['fit']} matching cards from your collection in its colors")
                if x["fit"] < 40:  # too little for a whole deck: better say so beforehand
                    info += "<br><span style='color:#d9b46a'>" + tr("Not enough for a full deck yet – the draft will be incomplete.") + "</span>"
                if x["examples"]:
                    info += "<br><span style='color:#8e8e8e'>" + tr("e.g. ") + ", ".join(x["examples"]) + "</span>"
                out.append({"title": r["name"].split(" // ")[0], "info": info, "img": _img(r),
                            "tag": tr("you own it") if x["owned_cmdr"] else tr("you don't own it yet"),
                            "owned": bool(x["owned_cmdr"]), "data": x})
            else:
                art = x["cards"][0] if x["cards"] else None
                info = tr(f"{x['count']} matching cards in your collection")
                if x.get("theme"):
                    info += "<br>" + tr(f"{x['theme_n']} of them for {x['theme']}")
                out.append({"title": suggest.idea_title(x), "info": info, "img": _img(art), "tag": "",
                            "owned": True, "data": x})
        self._results = out
        self.resultsChanged.emit()
        if err:
            self.sg.s._set_status(tr(f"Suggestions not possible: {err}"))
        elif not out:
            from collection import brew
            why = brew.diagnose_html(self.page.free_owned(), self._get_pool(), self._fmt, self._colors)
            self.sg.s._set_status(tr("Your collection doesn't have enough for that yet – drop a color or the play style.") + ("<br>" + why if why else ""))
        else:
            self.sg.s._set_status(tr("“Create deck” builds a rough draft from your cards (plus basic lands) – then fine-tune it in the deck builder."))

    @QtCore.Slot(int)
    def pick(self, i):
        from collection import brew
        from collection import decks
        from collection import suggest
        if not 0 <= i < len(self._results):
            return
        x, page = self._results[i]["data"], self.page
        pool = self._get_pool()
        # the style as the list shows it (brew.overview): German through tr – a tribe is translated already, "Discard" stays
        name = brew.archetype(self._key)[1] if self._key else ""
        style = name if not self._key or self._key.startswith("tribe:") or name in brew._SAME_WORD else tr(name)
        if self._fmt == "commander":
            cmdr, cards = suggest.draft_commander(x["row"], pool, online=page.ctrl.settings.get("deck_online", True),
                                                  bonus=brew.bonus(self._key or None))
            name = cmdr["name"].split(" // ")[0].split(",")[0] + " · " + (style or tr("Suggestion"))
            d = decks.new_deck(name, "commander")
            d["commanders"] = [cmdr["id"]]
        else:
            cards = suggest.draft_sixty(x, pool)
            d = decks.new_deck(suggest.idea_title(x) + " · " + tr("Suggestion"), self._fmt)
        for r, n in cards:
            decks.add_card(d, r["id"], n)
        if page.folder:
            d["folder"] = page.folder
        page.decks.append(d)
        page.save()
        page.open_deck(d)
        size = 100 if self._fmt == "commander" else 60
        have = sum(n for _, n in cards) + (1 if self._fmt == "commander" else 0)
        if have < size:
            page.toast(tr(f"Draft: {have} of {size} cards – {size - have} missing. Fill up in the deck builder: ⬆ Upgrades or “All cards” (including cards you don't own yet)."), 6500)
        else:
            page.toast(tr("Rough draft created – from your cards only. Fill gaps and fine-tune in the deck builder (⬆ Upgrades, ⇄ Alternatives)."), 4500)
