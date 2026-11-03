"""Detail and compare view in Qt Quick (qml/components/DetailView.qml).

Reads a librarycore.DetailState: it loads data, images, languages and prints and builds the texts of the
sections (prices, card, legality, print, rulings …) – this module hands them to QML. Inputs (language, flip,
section open/close, compare print, pin …) go back to it.
"""
import itertools

from PySide6 import QtCore

from cards import conditions
from ui import qform
from ui import quickimages
from system.i18n import tr
from cards import library
from ui.librarycore import FOLDS, THUMBS, eur
from ui.searchbox import merged_order

_counter = itertools.count(1)



def _finish_fields(ui, it, do, ctrl):
    """Finish (and edition, where there is one) of an owned copy – per game (finishes.py): Magic Non-Foil/Foil/
    Etched, Pokémon Normal/Holo/Reverse Holo + 1st Edition."""
    from cards import finishes
    opts = finishes.options(it)
    # Finish as plain text without a frame (only the condition is outlined – two different properties);
    # several finishes: a click switches to the next one
    keys = [o["key"] for o in opts]
    cur = finishes.current(it)
    label = next((tr(o["label"]) for o in opts if o["key"] == cur), tr(opts[0]["label"]))
    nxt = keys[(keys.index(cur) + 1) % len(keys)] if cur in keys else keys[0]
    out = [ui.tag(label, do(lambda it=it, k=nxt: ctrl.collection_change(it, finish=k)), plain=True,
                  tip=tr("Finish of this copy – click: next"))
           if len(opts) > 1 else ui.tag(label, plain=True)]
    for ed in finishes.editions(it):
        out.append(ui.check(tr(ed["label"]), it.get("edition") == ed["key"],
                            do(lambda on, it=it, k=ed["key"]: ctrl.collection_change(it, edition=k if on else ""))))
    return out

def cond_tag(ui, cur, set_cond):
    """Condition as an outlined abbreviation – a click cycles through (scale, then Graded, Other)."""
    from cards import conditions
    nxt = conditions.cycle_key(cur)
    return ui.tag(conditions.short(cur), lambda: set_cond({"cond": nxt, "grade_by": cur.get("grade_by") or "PSA",
                                                           "grade": cur.get("grade"), "cond_note": cur.get("cond_note")}),
                  tip=tr("Condition: {name} – click to switch (prices are always for Near Mint)")
                  .format(name=conditions.name(cur)))


def cond_extra(ui, cur, set_cond, key="c"):
    """Graded: company + grade, Other: free text – its own line below the copy (otherwise [])."""
    from cards import conditions
    shown = conditions.shown_key(cur)
    if shown == "graded":
        return [ui.label(tr("Graded:"), color="gray", fixed=True),
                ui.combo(list(conditions.GRADERS), cur.get("grade_by") or "PSA",
                         lambda g: set_cond({"cond": "graded", "grade_by": g, "grade": cur.get("grade")}),
                         tip=tr("Graded by?")),
                ui.edit(cur.get("grade") or "", lambda v: set_cond({"cond": "graded", "grade_by": cur.get("grade_by"),
                                                                      "grade": v}),
                        key=key + "grade", placeholder=tr("Grade, e.g. 10")), ui.stretch()]
    if shown == "other":
        return [ui.label(tr("Other:"), color="gray", fixed=True),
                ui.edit(cur.get("cond_note") or "", lambda v: set_cond({"cond": "other", "cond_note": v}),
                        key=key + "note", placeholder=tr("e.g. proxy, signed, misprint")), ui.stretch()]
    return []


SCRYFALL_NOTE = "Shop links come from Scryfall and may carry Scryfall's partner code. Bent°Corner earns nothing from them."
DIRECT_NOTE = "Shop links lead straight to the shops' own pages, without a partner code. Bent°Corner earns nothing from them."


def shop_note(price_html, from_scryfall):
    """legal 02.11.: exactly one sentence on where the shop links come from – and only when the prices show at least
    one link (no price, no link: no sentence). from_scryfall: the links are Scryfall's purchase_uris."""
    if "<a " not in (price_html or ""):
        return ""
    return tr(SCRYFALL_NOTE) if from_scryfall else tr(DIRECT_NOTE)


class DetailBackend(QtCore.QObject):
    changed = QtCore.Signal()
    imageChanged = QtCore.Signal()
    listsChanged = QtCore.Signal()
    revealRequested = QtCore.Signal(str)

    def __init__(self, ctrl, lib, panel, parent=None):
        super().__init__(parent)
        self.ctrl, self.lib, self.p = ctrl, lib, panel
        self._img_url, self._img_mode, self._img_gen = "", "in", 0
        self._img_ident = None     # (show_row call, print, side) of the image shown last
        self.quiet_next = False    # swap the next image silently (side swap: the views slide by themselves)
        self.own = qform.Form(self._build_own, self)      # "Your copies" (data: panel.own_view)
        self._t = QtCore.QTimer(self, singleShot=True, interval=0, timeout=self._emit)
        self._hook()

    # ---------- attach to the hidden view ----------
    def _hook(self):
        p = self.p

        def wrap(obj, name, after):
            orig = getattr(obj, name)

            def fn(*a, **k):
                res = orig(*a, **k)
                after()
                return res
            setattr(obj, name, fn)
        for name in ("show_row", "fill_text", "refresh_owned", "update_star", "update_add_btn", "fill_prints",
                     "apply_order", "apply_hidden", "set_add_cond"):
            wrap(p, name, self.soon)
        wrap(p, "refresh_lists", self._lists)
        self._prints_pending = False  # new card, prints not there yet: QML keeps their space free
        orig_show = p.show_row

        def show_row(row, *a, **k):  # set beforehand: fill_prints often already runs inside show_row
            self._prints_pending = row is not None
            return orig_show(row, *a, **k)
        p.show_row = show_row
        wrap(p, "fill_prints", lambda: setattr(self, "_prints_pending", False))
        wrap(p.langbar, "set_langs", self.soon)
        wrap(p.langbar, "set_current", self.soon)
        wrap(p.lang_note, "set_html", self.soon)   # „No ES image online – showing EN“ under the languages
        for f in p.folds.values():
            wrap(f, "set_sub", self.soon)
            wrap(f, "set_open", self.soon)
        img = p.image
        wrap(img, "setPixmap", self._picture)
        wrap(img, "replace_pixmap", lambda: self._picture(quiet=True))
        wrap(img, "setText", self._picture_text)
        wrap(img, "set_loading", self._picture_text)
        wrap(img, "set_missing", self._picture_text)   # also later (image server failed / no answer) -> NoImage
        wrap(p.price_chart, "set_card", self.soon)

    def soon(self):
        if not self._t.isActive():
            self._t.start()

    def _emit(self):
        self.own.refresh()
        self.changed.emit()

    def _lists(self):
        self.listsChanged.emit()
        self.soon()

    # ---------- "My Lists" (MyLists.qml) ----------
    @QtCore.Property("QVariantList", notify=listsChanged)
    def myLists(self):
        opened = self.__dict__.setdefault("_open_my", set())
        out = []
        for sec in getattr(self.p, "lists_data", []) or []:
            out.append(dict(sec, lists=[dict(x, open=x["key"] in opened) for x in sec["lists"]]))
        return out

    @QtCore.Slot(str)
    def listDo(self, fid):
        f = (getattr(self.p, "list_fns", None) or {}).get(fid)
        if f is not None:
            f()

    @QtCore.Slot(str)
    def toggleMyList(self, key):
        opened = self.__dict__.setdefault("_open_my", set())
        (opened.discard if key in opened else opened.add)(key)
        self.listsChanged.emit()

    @QtCore.Slot(str)
    def newMyList(self, kind):
        self.p._new_list(kind)

    @QtCore.Property(bool, notify=listsChanged)
    def canAlarm(self):
        return hasattr(self.ctrl, "show_alarms")

    @QtCore.Slot()
    def openAlarms(self):
        if hasattr(self.ctrl, "show_alarms"):
            self.ctrl.show_alarms()

    @QtCore.Property(bool, notify=listsChanged)
    def alarm(self):
        """Is there a price alert for exactly this print? Wishlist card "cheapest print": any print; "exactly one
        print": only this one; trade card: your copy."""
        from collection import alarms
        r = self.p.row
        if not r:
            return False
        a = alarms.find(self.ctrl.settings, "wish", r["name"], None, None)
        if a is not None and (not alarms.opts_of(a)["psid"] or alarms.opts_of(a)["psid"] == r.get("sid")):
            return True
        return any(x["kind"] == "trade" and x.get("sid") == r.get("sid") for x in alarms.alarms(self.ctrl.settings))

    @QtCore.Slot()
    def alarmForCard(self):
        """Bell: go to the "Trade" tab (price alerts) and set/change the alert for this card right away."""
        from collection import alarms
        r = self.p.row
        if r is None or not hasattr(self.ctrl, "show_alarms"):
            return
        # Foil shown: the alert watches the foil price right away
        opts = {"psid": r.get("sid")} if r.get("sid") else {}   # exactly this print (not "cheapest")
        if self.p.is_foil() and len(self.p.finish_options()) > 1:
            opts["finish"] = "f"
        self.ctrl.show_alarms(alarms.card_key({"kind": "wish", "name": r["name"]}), opts or None)
        self.listsChanged.emit()

    # ---------- "Your copies" ----------
    def _build_own(self, ui):
        from collection.collection import lang_short
        from ui.librarycore import source_text
        p, ctrl = self.p, self.ctrl
        if p.row is None:
            return ui.col([])
        rows = []

        def do(fn):  # change, then re-read the list of copies
            return lambda *a: (fn(*a), p.refresh_owned())
        for it, codes in p.own_view:
            set_c = do(lambda c, it=it: ctrl.collection_change(it, cond=c))
            # two rows per copy (one did not fit the width): top origin, quantity, ✕ – below language,
            # finish, condition (abbreviation to cycle through); Graded/Other get their fields in a third row
            head = [ui.label(source_text(it), color="gray"), ui.stretch()]
            if it.get("src"):
                head.append(ui.label("1×", fixed=True, tip=tr("Scanned card – one copy")))
            else:
                head.append(ui.spin(it.get("count", 1), 1, 999, do(lambda v, it=it: ctrl.collection_count(it, v)),
                                    suffix="×"))
            head.append(ui.button("✕", do(lambda it=it: ctrl.collection_count(it, 0)),
                                  tip=tr("Remove from collection") + (tr(" (the log statistics stay unchanged)") if it.get("src") else "")))
            parts = [ui.combo([(c, lang_short(c)) for c in codes], it.get("lang", "en"),
                              do(lambda c, it=it: ctrl.collection_change(it, lang=c)),
                              tip=tr("Language of this copy")),
                     ] + _finish_fields(ui, it, do, ctrl) + [cond_tag(ui, it, set_c), ui.stretch()]
            extra = cond_extra(ui, it, set_c, key=f"c{it['uid']}")
            rows.append(ui.col([ui.row(head, spacing=6), ui.row(parts, spacing=6)]
                               + ([ui.row(extra, spacing=6)] if extra else []), spacing=4))
        if not p.own_view:
            rows.append(ui.note(tr("Not in the collection yet.")))
        elif p.own_total:
            rows.append(ui.note(p.own_total))

        def count(v):
            p.add_n = int(v)
        from cards import finishes
        opts = finishes.options(p.row["card"])
        akeys = [o["key"] for o in opts]
        acur = p.add_finish if p.add_finish in akeys else akeys[0]
        alabel = next(tr(o["label"]) for o in opts if o["key"] == acur)
        add_fin = (ui.tag(alabel, lambda k=akeys[(akeys.index(acur) + 1) % len(akeys)]: p.set_add_finish(k), plain=True,
                          tip=tr("Finish of the card you're adding – click: next"))
                   if len(opts) > 1 else ui.tag(alabel, plain=True))
        # Edition when adding (Yu-Gi-Oh!/Pokémon: 1st Edition) – on/off, applies to the cards you add
        eds = [ui.check(tr(ed["label"]), p.add_edition == ed["key"],
                        lambda on, k=ed["key"]: p.set_add_edition(k if on else ""),
                        tip=tr("Edition of the cards you add"))
               for ed in finishes.editions(p.row["card"])]
        add_c = p.add_cond or {"cond": conditions.default()}
        rows.append(ui.line())
        rows.append(ui.row([ui.spin(p.add_n, 1, 999, count, suffix="×"), add_fin] + eds +
                           [cond_tag(ui, add_c, p.set_add_cond), ui.stretch()], spacing=6))
        extra = cond_extra(ui, add_c, p.set_add_cond, key="addc")
        if extra:
            rows.append(ui.row(extra, spacing=6))
        rows.append(ui.row([ui.stretch(), ui.button(p.add_text or tr("Add"), p.add, primary=True)]))
        return ui.col(rows, spacing=6)

    def _picture(self, quiet=False):
        src = self.p.src_pm
        if src is None or src.isNull():
            return
        key = f"detail{next(_counter)}"
        self._img_url = quickimages.put(key, src.toImage())
        p = self.p
        ident = (p.token, (p.row or {}).get("sid"), p.face) if p.row is not None else None
        mode = p.image.mode or "in"
        # the same card in a better resolution (or automatically in the default language): swap silently, don't
        # fly it in again
        if mode == "quiet" or self.quiet_next or (ident is not None and ident == self._img_ident
                                                   and mode in ("in", "fade")):
            quiet = True
        if ident is not None:
            self._img_ident = ident
        self.quiet_next = False
        if not quiet:
            self._img_mode = mode
            self._img_gen += 1
        self.imageChanged.emit()

    def _picture_text(self):
        if self.p.image.pm is None and self._img_url:
            # new card without an image (still loading / notice): don't keep the old one – show its placeholder
            self._img_url, self._img_ident = "", None
            self._img_mode = "fade"
            self._img_gen += 1
        self.imageChanged.emit()

    # ---------- Header ----------
    @QtCore.Property(bool, notify=changed)
    def hasRow(self):
        return self.p.row is not None

    @QtCore.Property(bool, constant=True)
    def isCompare(self):
        return bool(self.p.compare)

    @QtCore.Property(str, notify=changed)
    def titleHtml(self):
        return self.p.title.html or ""

    @QtCore.Property(str, notify=changed)
    def altHtml(self):
        return self.p.alt_names.html or ""

    @QtCore.Property(str, notify=changed)
    def setLine(self):
        return self.p.set_line.html or ""

    @QtCore.Property(bool, notify=changed)
    def star(self):
        return bool(getattr(self.p.star_btn, "active", False))

    @QtCore.Property(bool, notify=changed)
    def rulings(self):
        return not getattr(self.p.rules_btn, "empty", True)

    @QtCore.Property(bool, notify=changed)
    def canPin(self):
        return not self.p.pin_btn.isHidden()

    @QtCore.Property(bool, notify=changed)
    def pinned(self):
        return self.p.pin_btn.isChecked()

    @QtCore.Property(bool, notify=changed)
    def canClose(self):
        return not self.p.close_btn.isHidden()

    @QtCore.Slot(bool)
    def setPinned(self, on):
        if self.p.compare:
            self.p.pin_btn.click()  # ⇄ swap sides
        else:
            self.p.pin_btn.setChecked(on)
        self.soon()

    @QtCore.Slot()
    def close(self):
        self.p.close_btn.click()

    @QtCore.Slot()
    def showLists(self):
        self.revealFold("lists")

    @QtCore.Slot()
    def showRulings(self):
        if self.rulings:
            self.revealFold("rulings")

    # ---------- Image ----------
    @QtCore.Property(str, notify=imageChanged)
    def imageUrl(self):
        return self._img_url if self.p.row is not None else ""

    @QtCore.Property(str, notify=imageChanged)
    def imageMode(self):
        return self._img_mode

    @QtCore.Property(int, notify=imageChanged)
    def imageGen(self):
        return self._img_gen

    @QtCore.Property(str, notify=imageChanged)
    def imageText(self):
        return self.p.image.text or ""

    @QtCore.Property(str, notify=imageChanged)
    def loadingName(self):
        return (self.p.image.loading_name or "").strip()

    @QtCore.Property(bool, notify=imageChanged)
    def imageMissing(self):
        return bool(getattr(self.p.image, "missing", False))

    @QtCore.Property(bool, notify=changed)
    def foil(self):
        return bool(self.p.image.foil)

    @QtCore.Property(str, notify=changed)
    def holo(self):
        """Pokémon: where the holo shine sits – "holo" (art window only), "reverse" (everywhere but the art) or ""
        (Magic or a normal card: as before, foil = whole card). Provisional, art window fixed for modern cards."""
        import games
        if self.p.row is None or games.current().key == "mtg":
            return ""
        try:
            labels = self.p.finish_labels()
            shown = labels.get("f") if self.p.is_foil() else labels.get("n")
        except Exception:  # noqa: BLE001
            return ""
        return {"Reverse Holo": "reverse", "Holo": "holo"}.get(shown or "", "")

    @QtCore.Slot(str)
    def searchArtist(self, name):
        """All cards by this artist: Library → All cards with a:"Name" (becomes the chip "Artist: …")."""
        lib = getattr(self.ctrl, "library_win", None)
        if lib is None or not hasattr(lib, "bar") or not name.strip():
            return
        lib.set_mode("all")
        lib.search.setText(f'a:"{name.strip()}"')
        lib.bar.commit_syntax()
        shell = getattr(self.ctrl, "shell", None)
        if shell is not None and hasattr(shell, "pick"):
            shell.pick("library", 0)

    # ---------- Condition at the top next to "Non-Foil | Foil" ----------
    def _cond_target(self):
        """-> (entry, set) – one owned copy: its condition; none: the condition for adding; several:
        (None, None) (then the abbreviation shows the range and leads to "In your collection")."""
        from cards import conditions
        p, ctrl = self.p, self.ctrl
        if len(p.own_view) == 1:
            it = p.own_view[0][0]
            return it, lambda c: (ctrl.collection_change(it, cond=c), p.refresh_owned())
        if not p.own_view:
            return (p.add_cond or {"cond": conditions.default()}), p.set_add_cond
        return None, None

    @QtCore.Property(str, notify=changed)
    def condTag(self):
        from cards import conditions
        p = self.p
        if p.row is None:
            return ""
        cur, _ = self._cond_target()
        if cur is not None:
            return conditions.short(cur)
        its = sorted((it for it, _ in p.own_view), key=conditions.rank)
        a, b = conditions.short(its[0]), conditions.short(its[-1])
        return a if a == b else f"{a}–{b}"

    @QtCore.Property(str, notify=changed)
    def condTip(self):
        from cards import conditions
        cur, _ = self._cond_target()
        if cur is None:
            return tr("Condition of your copies – click to show them")
        what = tr("of your copy") if self.p.own_view else tr("of the cards you add")
        return tr("Condition {what}: {name} – click to switch (prices are always for Near Mint)").format(
            what=what, name=conditions.name(cur))

    @QtCore.Slot()
    def cycleCond(self):
        from cards import conditions
        cur, setter = self._cond_target()
        if cur is None:
            self.revealFold("own")
            return
        setter({"cond": conditions.cycle_key(cur), "grade_by": cur.get("grade_by") or "PSA",
                "grade": cur.get("grade"), "cond_note": cur.get("cond_note")})
        self.soon()

    @QtCore.Property("QVariantMap", notify=changed)
    def finishInfo(self):
        """Finishes of the print and which one is currently shown (for "Non-Foil | Foil")."""
        if self.p.row is None:
            return {}
        import games
        # Yu-Gi-Oh!: every rarity is a print of its own – cycle through them at the top right (like Non-Foil | Foil),
        # the rarities of the same set number (EN008, EN008-UR, -ScR …)
        g = games.current()
        single = bool(g.variant_numbers)
        out = {"options": self.p.finish_options(), "foil": self.p.is_foil(), "labels": self.p.finish_labels(),
               "only": not single, "tip": ""}
        if single:
            out["variants"] = self._variants(g)
        return out

    def _variants(self, g):
        """Rarities of the same set number: [{sid, t (abbreviation), tip (name), on}] – empty if there is only one."""
        from cards import carddb
        r = self.p.row or {}
        db = r.get("db") or {}
        sc, num = (db.get("set_code") or str(r.get("set") or "")).lower(), str(db.get("number") or r.get("number") or "")
        base = num.split("-")[0]
        if not sc or not base or not carddb.exists():
            return []
        with carddb.connection() as con:
            rows = con.execute("SELECT id, rarity FROM cards WHERE set_code = ? AND (number = ? OR number LIKE ?) "
                               "ORDER BY rowid", (sc, base, base + "-%")).fetchall()
        if len(rows) < 2:
            return []
        out = []
        for sid, rar in rows:
            name = dict(g.rarities).get((rar or "").lower()) or (rar or "").title()
            out.append({"sid": sid, "t": g.rarity_short(name) if g.rarity_short is not None else name, "tip": name,
                        "on": sid == r.get("sid")})
        return out

    @QtCore.Slot(str)
    def showVariant(self, sid):
        """Show another rarity of the same number (Yu-Gi-Oh!, top right)."""
        from ui.librarycore import LibraryCore
        lib = self.lib
        fn = getattr(lib, "row_for_print", None)
        row = fn({"id": sid}) if fn else LibraryCore.row_for_print(lib, {"id": sid})
        if row is not None:
            self.p.show_row(row)
            self.soon()

    @QtCore.Slot(bool)
    def setFoilView(self, on):
        self.p.set_view_foil(on)
        self.soon()

    @QtCore.Property(bool, notify=changed)
    def canFlip(self):
        return not self.p.flip.isHidden()

    @QtCore.Property(bool, notify=changed)
    def flipped(self):
        return self.p.flip.isChecked()

    @QtCore.Slot()
    def flip(self):
        self.p.flip.click()

    @QtCore.Property("QVariantList", notify=changed)
    def langs(self):
        bar = self.p.langbar
        shown = bar.langs or ([(bar.current, bar.current.upper(), None, None)] if self.p.row is not None else [])
        return [{"code": c, "short": s, "printed": pr or "", "current": c == bar.current} for c, s, _, pr in shown]

    @QtCore.Slot(str)
    def pickLang(self, code):
        self.p.langbar.pick(code)
        self.changed.emit()

    @QtCore.Property(str, notify=changed)
    def langHint(self):
        return getattr(self.p.langbar, "hint", "") or ""

    @QtCore.Property(int, notify=changed)
    def langHintRev(self):
        return int(getattr(self.p.langbar, "hint_rev", 0))

    @QtCore.Property(str, notify=changed)
    def langNote(self):
        return self.p.lang_note.text() or ""

    # ---------- Sections ----------
    @QtCore.Property("QVariantList", notify=changed)
    def folds(self):
        p = self.p
        hidden = p.hidden_folds()
        titles = dict(FOLDS)
        out = []
        for key in p.fold_order:
            f = p.folds[key]
            if key in hidden or (p.row is None):
                continue
            if f.isHidden() and key not in ("prints",):
                continue
            html = ""
            if key == "text":
                html = p.text.text()
            elif key in p.labels:
                html = p.labels[key].text()
            elif key == "prints":
                html = p.prints_empty.text() if not p.prints_empty.isHidden() else ""
            boxes = ""
            if key == "text":  # QML draws the rules-text boxes (per card face) itself – without the old table
                import re
                parts = re.findall(r"<td[^>]*>(.*?)</td>", html, re.S)
                if parts:
                    boxes, html = "\x01".join(parts), ""
            out.append({"key": key, "title": tr(titles[key]), "sub": f.head.sub or "",
                        "closedSub": getattr(f.head, "closed_sub", "") or "", "open": bool(f.is_open),
                        "html": html, "chart": key == "prices" and not p.price_chart.isHidden(), "boxes": boxes})
        return out

    @QtCore.Property("QVariantList", notify=changed)
    def allFolds(self):
        """For the ☰ menu: all sections in order, with on/off."""
        hidden = self.p.hidden_folds()
        titles = dict(FOLDS)
        return [{"key": k, "title": tr(titles[k]), "shown": k not in hidden} for k in self.p.fold_order]

    @QtCore.Slot(str, bool)
    def setFold(self, key, on):
        self.lib.set_fold(key, on)
        self.soon()

    @QtCore.Slot(str)
    def revealFold(self, key):
        self.p.reveal_fold(key)
        self.soon()
        self.revealRequested.emit(key)

    @QtCore.Slot("QVariantList", "QVariantList")
    def setLayout(self, order, hidden):
        self.p.set_layout_prefs(merged_order(list(order), [k for k, _ in FOLDS]), set(hidden))
        self.soon()

    # ---------- All prints ----------
    @QtCore.Property(bool, notify=changed)
    def sameSet(self):
        return bool(getattr(self.ctrl, "_same_set", False))

    @QtCore.Slot(bool)
    def setSameSet(self, on):
        """The "Same set" filter: only alternate prints from the shown card's set (for both detail and compare)."""
        self.ctrl._same_set = bool(on)
        self.soon()

    @QtCore.Property("QVariantList", notify=changed)
    def prints(self):
        rows = self.p.strip.model_.rows if not self.p.strip.isHidden() else []
        if self.sameSet and self.p.row is not None:
            cur = str(self.p.row.get("set") or "").lower()
            rows = [pr for pr in rows if str(pr.get("set") or "").lower() == cur]
        marks = self.p.strip.marks
        out = []
        for pr in rows:
            sid = pr["id"]
            url = quickimages.register(f"{sid}_en_s", THUMBS / f"{sid}_en_s.jpg", pr.get("img")
                                       or library.image_url(pr["set"], pr["number"], "en", "small"),
                                       THUMBS / f"{sid}_en_s.jpg")
            price = pr.get("eur") if pr.get("eur") not in (None, "") else pr.get("eur_foil")
            try:
                price = eur(float(price)) if price not in (None, "") else ""
            except (TypeError, ValueError):
                price = ""
            out.append({"id": sid, "set": (pr.get("set") or "").upper(), "number": pr.get("number") or "",
                        "img": url, "price": price, "mark": marks.get(sid, ""), "date": pr.get("date") or ""})
        return out

    @QtCore.Property(int, notify=changed)
    def rowKey(self):
        """Changes with every newly shown card (QML then fades the sections in together)."""
        return int(self.p.token)

    @QtCore.Property(bool, notify=changed)
    def printsLoading(self):
        return bool(self._prints_pending and self.p.row is not None)

    @QtCore.Property(str, notify=changed)
    def printsNote(self):
        return self.p.prints_empty.text() if not self.p.prints_empty.isHidden() else ""

    @QtCore.Slot(str)
    def pickPrint(self, sid):
        pr = next((x for x in self.p.strip.model_.rows if x["id"] == sid), None)
        if pr is not None:
            self.p._print_picked(pr)

    # ---------- Price history ----------
    @QtCore.Property("QVariantMap", notify=changed)
    def chart(self):
        c = self.p.price_chart
        if c.isHidden() or not c.data:
            return {}
        lines = []
        for name, shop, foil, dim, pts, unit in c.lines_all():   # normal + foil; selected finish bold
            lines.append({"name": name, "shop": shop, "foil": foil, "dim": dim, "unit": unit,
                          "pts": [[QtCore.QDateTime(QtCore.QDate(d.year, d.month, d.day), QtCore.QTime(12, 0))
                                   .toMSecsSinceEpoch(), float(v), float(o)] for d, v, o in pts]})
        has = {k: any(c.data.get(s + k) for s in "ct") for k in "nf"}
        return {"lines": lines, "days": c.days, "finish": c.finish, "both": all(has.values()),
                "ranges": [{"days": d, "text": tr(t)} for d, t in c.RANGES]}

    @QtCore.Property("QVariantList", notify=changed)
    def shops(self):
        """More marketplaces (eBay, Kleinanzeigen) for the shown card and finish – Cardmarket and TCGplayer
        are already listed right next to their prices."""
        from cards import shoplinks
        if self.p.row is None:
            return []
        card = dict(self.p.row["card"], **{k: v for k, v in ((self.p.full or {}).get("card") or {}).items()
                                            if k in ("purchase_uris", "set_name")})
        return [m for m in shoplinks.market_links(card, self.ctrl.settings, foil=self.p.is_foil())
                if m["key"] not in ("cardmarket", "tcgplayer")]

    @QtCore.Property(str, notify=changed)
    def shopNote(self):
        """The one small note on the shop links under the prices – "" when no link is shown there (legal 02.11.)."""
        if self.p.row is None or "prices" not in self.p.labels:
            return ""
        return shop_note(self.p.labels["prices"].text(), self.shopsFromScryfall)

    @QtCore.Property(bool, notify=changed)
    def shopsFromScryfall(self):
        """The Cardmarket/TCGplayer links at the prices are Scryfall's purchase_uris (Magic) – only then the note on
        Scryfall's partner code (legal 02.11.); otherwise they are our own searches by name."""
        if self.p.row is None:
            return False
        uris = ((self.p.full or {}).get("card") or {}).get("purchase_uris") or self.p.row["card"].get("purchase_uris") or {}
        return bool(uris.get("cardmarket") or uris.get("tcgplayer"))

    @QtCore.Property("QVariantMap", notify=changed)
    def phHint(self):
        """No chart: why not – and whether the history can be loaded from here."""
        from cards import pricehist
        if not self.p.price_chart.isHidden():
            return {}
        eta = self.ctrl.ph_eta() if hasattr(self.ctrl, "ph_eta") else None
        return pricehist.hint(self.ctrl.settings, eta)

    @QtCore.Slot()
    def loadHistory(self):
        if hasattr(self.ctrl, "enable_price_history"):
            self.ctrl.enable_price_history()
        self.soon()

    @QtCore.Slot(str)
    def setFinish(self, k):
        self.p.set_view_foil(k == "f")   # Normal/Foil on the chart = the same switch as on the card image
        self.soon()

    @QtCore.Slot(int)
    def setRange(self, days):
        self.p.price_chart.set_range(days)
        self.ctrl.settings_changed()
        self.soon()

    # ---------- Forms: owned copies, My Lists ----------
    @QtCore.Property(QtCore.QObject, constant=True)
    def ownForm(self):
        return self.own

    @QtCore.Property(str, notify=changed)
    def note(self):
        return self.p.note.text() or ""
