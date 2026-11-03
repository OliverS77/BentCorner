"""Import/Export in Qt Quick (qml/pages/ImportPage.qml): import/export entries on the left, the selected entry on the
right as a form (qform) built from the state of importview.ImportPage – no widgets."""
import html
import itertools
import time

from PySide6 import QtCore, QtGui

from collection import decks
from ui import qdialogs
from ui import qform
from ui import quickimages
from collection import trade
from system.i18n import tr

_img_n = itertools.count(1)


class ImportBackend(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        ctrl.stream.ensure_page("import")
        self.page = p = ctrl.import_page
        self._active = False
        self._imgs = {}
        self.form = qform.Form(self._build, self)
        p.changed.connect(self._page_changed)

    def _page_changed(self):
        if self._active:
            self.form.soon()
        self.changed.emit()

    @QtCore.Slot(bool)
    def setActive(self, on):
        self._active = bool(on)
        if on:
            self.form.refresh()

    # ---------- Building blocks ----------
    def _image(self, ui, img, width=760):
        """QImage -> image block (same image = same address)."""
        if img is None:
            return None
        key = self._imgs.get(id(img))
        if key is None:
            key = self._imgs[id(img)] = f"imp{next(_img_n)}"
            quickimages.put(key, img)
        w = min(width, img.width())
        return ui.image("image://cards/" + key, w, round(img.height() * w / max(1, img.width())))

    def _img_actions(self, ui, state, key, img_fn, name_fn):
        """Copy / save for an image; message goes to state[key]."""
        p = self.page

        def copy():
            state[key] = p.copy_image(img_fn())

        def save():
            msg = p.save_image(img_fn(), name_fn())
            if msg:
                state[key] = msg
        return ui.row([ui.button(tr("Copy"), copy, primary=True), ui.button(tr("Save …"), save),
                       ui.note(state.get(key) or tr("Copy and paste it e.g. into WhatsApp or Discord with Ctrl+V."))])

    @staticmethod
    def _card(ui, items):
        """The page content right next to the side bar – no frame (no boxes in boxes); parts inside are flat groups."""
        return ui.col(items, spacing=10)

    # ---------- Pages ----------
    def _build(self, ui):
        fn = getattr(self, "_p_" + self.page.current, None)
        return fn(ui) if fn else ui.col([])

    def _deck_items(self, selected):
        """All decks as small tiles (title card, name, format) – without folders, for picking with search."""
        from cards import carddb
        from collection import deckshare
        from cards import library
        from ui import quickimages
        from ui.librarycore import THUMBS
        ds = self.page._decks()
        ids = set()
        for d in ds:
            ids |= decks.all_ids(d)
        rows = carddb.cards_by_ids(ids) if carddb.exists() and ids else {}
        out = []
        # built decks first (those are the ones you take along), then alphabetical
        for d in sorted(ds, key=lambda d: (not d.get("built"), (d.get("name") or "").lower())):
            cov = deckshare.cover_rows(d, rows)
            r = cov[0] if cov else next((rows[c["sid"]] for c in d["cards"] if c["sid"] in rows), None)
            img = ""
            if r is not None:
                local = THUMBS / f"{r['id']}_en_n.jpg"
                url = r.get("img_normal") or library.image_url(r["set_code"], r["number"], "en", "normal")
                img = quickimages.register(f"{r['id']}_en_n", local, url, local)
            out.append({"id": d["id"], "name": d["name"], "img": img, "icon": "decks", "on": d["id"] in selected,
                        "sub": dict(decks.FORMATS).get(d.get("format"), "") + (" · " + tr("built") if d.get("built")
                                                                                   else "")})
        return out

    def _list_items(self, kind, selected):
        """Lists as tiles (image of the most valuable card, name, count)."""
        tb = getattr(self.ctrl, "shell", None)
        tb = tb.backends.get("trade") if tb is not None else None
        out = []
        for x in sorted(trade.lists(kind), key=lambda x: (x["id"] not in (trade.MAIN_WISH, trade.MAIN_HAVE),
                                                          (x.get("name") or "").lower())):
            entries = trade.list_entries(kind, x["id"], self.ctrl.collection.items)
            art = ""
            if tb is not None:
                try:
                    art = tb.lists_b._list_value_art(kind, entries)[1]
                except Exception:
                    art = ""
            name = tr(x["name"]) if x["id"] in (trade.MAIN_WISH, trade.MAIN_HAVE) else x["name"]
            out.append({"id": x["id"], "name": name, "img": art, "icon": "star" if kind == "wish" else "trade",
                        "sub": tr(f"{sum((e['count'] for e in entries))} cards"), "on": x["id"] in selected})
        return out

    def _list_lines(self, kind, lid):
        """Expanded list: [{text: "2× Name", sub: "SET #nr" / "any"}], sorted by name – the same print (name, set,
        number, language, foil) once with its count: "4× Sol Ring" instead of four rows (like the web, 03.11.)."""
        es = trade.merged_entries(trade.list_entries(kind, lid, self.ctrl.collection.items))
        out = []
        for e in sorted(es, key=lambda e: e["name"].lower()):
            sub = f"{str(e['set']).upper()} #{e['number']}" if e.get("set") else tr("any version")
            if e.get("foil"):
                sub += " · Foil"
            out.append({"text": f"{e['count']}× {e['name']}", "sub": sub})
        return out

    def _deck_lines(self, did):
        """Expanded deck: Commander, then deck, sideboard, maybeboard – each "1× Name" with printing."""
        from cards import carddb
        d = next((x for x in self.page._decks() if x["id"] == did), None)
        if d is None:
            return []
        rows = carddb.cards_by_ids(decks.all_ids(d)) if carddb.exists() else {}

        def line(sid, n, board=""):
            r = rows.get(sid) or {}
            sub = f"{(r.get('set_code') or '').upper()} #{r.get('number') or ''}" if r else ""
            if board:
                sub = (board + " · " + sub) if sub else board
            return {"text": f"{n}× {r.get('name') or '?'}", "sub": sub}
        out = [line(s, 1, tr("Commander")) for s in d.get("commanders", [])]
        labels = {"side": tr("Sideboard"), "maybe": tr("Maybeboard")}
        for b in ("main", "side", "maybe"):
            cs = [c for c in d["cards"] if c.get("board", "main") == b]
            cs.sort(key=lambda c: ((rows.get(c["sid"]) or {}).get("name") or "").lower())
            out += [line(c["sid"], c["count"], labels.get(b, "")) for c in cs]
        return out

    def _p_share_decks(self, ui):
        p = self.page
        lst = ui.picker(self._deck_items(p.share_ids), lambda i, on: p.toggle_share(i, on),
                        placeholder=tr("Search decks …"), tile_w=150, h=430)
        one = len([d for d in p._decks() if d["id"] in p.share_ids]) == 1
        cover = []
        if one:
            def toggle_cover():
                p.cover_open = not p.cover_open
                p.cover_filter = ""
            cover.append(ui.row([ui.label(p.cover_text, color="gray"),
                                 ui.button(tr("Change cover card …"), toggle_cover, active=p.cover_open)]))
            if p.cover_open:
                rows = p.cover_rows()

                def flt(t):
                    p.cover_filter = t
                cover.append(ui.edit(p.cover_filter, flt, key="coverq", live=flt,
                                     placeholder=tr("Search a card in the deck …")))
                cover.append(ui.list([{"text": t} for _, t in rows], on_click=lambda r: p.pick_cover(rows[r][0]),
                                     h=220))
        prev = self._image(ui, p.share_img, 1240) if p.share_img is not None else \
            ui.note(tr("Tick at least one deck above."))
        n = len([d for d in p._decks() if d["id"] in p.share_ids])

        def set_title(t):
            p.share_title = t
            p._share_timer.start()
        title = ui.form([(tr("Heading"), ui.edit(p.share_title, set_title, key="sharetitle", live=set_title,
                                                     placeholder=tr("My lineup") if n != 1 else tr("Deck name")))])
        return self._card(ui, [
            ui.note(tr("One deck: a big image with cover card, curve, roles and combos. Several decks: your lineup side by side. You write the message yourself in the chat.")),
            lst, title] + cover + [prev, self._img_actions(ui, p.__dict__, "share_info", lambda: p.share_img,
                                                      lambda: tr("My decks"))])

    def _p_deck_export(self, ui):
        p = self.page
        ds = p._decks()
        n = len([d for d in ds if d["id"] in p.dexp_ids])
        return self._card(ui, [
            ui.note(tr("Tick decks – as text that Moxfield, Archidekt, Arena and most other sites can import. Several decks: one file each.")),
            ui.checklist(self._deck_items(p.dexp_ids), lambda i, on: p.toggle_dexp(i, on), self._deck_lines,
                         key="dexp", placeholder=tr("Search decks …"), h=460),
            ui.row([ui.button(tr("Copy to clipboard"), p.dexp_clip, primary=True, enabled=n > 0),
                    ui.button(tr("Save as text file …") if n <= 1 else tr(f"Save {n} text files …"),
                              p.dexp_file, enabled=n > 0),
                    ui.note(p.dexp_info)]),
        ])

    def _p_coll_export(self, ui):
        from collection.collection import EXPORT_FORMATS
        p, ctrl = self.page, self.ctrl

        def fmt(v):
            ctrl.settings["export_format"] = v
            ctrl.settings_changed()
        return self._card(ui, [
            ui.note(tr("ManaBox/Moxfield: choose the CSV file under Import there. Excel: table with prices.")),
            ui.row([ui.seg([(k, tr(lb)) for k, lb in EXPORT_FORMATS], ctrl.settings["export_format"],
                           lambda k: (fmt(k), self.form.soon())),
                    ui.button(tr("Export collection …"), lambda: ctrl.export_collection(p.cexp_info), primary=True)]),
            ui.note(p.cexp_info.text()) if p.cexp_info.text() else None,
        ])

    def _p_friend_code(self, ui):
        """Your ID (= relay.my_code, formerly "friend code"): share your own, enter a friend's."""
        from net import relay
        ctrl = self.ctrl
        s = ctrl.settings
        if not relay.enabled(s):
            return self._card(ui, [
                ui.label(tr("Your ID"), bold=True, big=True),
                ui.note(tr("With IDs, friends sync on their own: shared lists and binders come via the Bent°Corner server, end-to-end encrypted. Exchange has to be switched on for that.")),
                ui.row([ui.stretch(), ui.button(tr("Turn on exchange …"), ctrl.relay_ask, primary=True)])])
        st = self.page.__dict__.setdefault("fcode", {"text": ""})

        def send():
            code = relay.norm(st["text"])
            if not code:
                ctrl.stream_toast(tr("That doesn't look like an ID (16 characters, e.g. 7F3A-21C9-0B44-E1D2)."))
                return
            ctrl.relay_add(code)
            st["text"] = ""             # relay_add reports the result itself
            self.page._changed()
        return self._card(ui, [
            ui.label(tr("Your ID"), bold=True, big=True),
            ui.note(tr("With your ID, friends find you – and we recognize your Studio contributions.")),
            ui.row([ui.label(tr("Your own ID is in your profile – to copy and share.")), ui.stretch(),
                    ui.button(tr("Open profile →"), lambda: ctrl.stream.show_page("profile", back=True))]),
            ui.group(tr("Enter a friend's ID"), flat=True, items=[
                ui.row([ui.edit(st["text"], lambda t: (st.update(text=t), send()), key="fcode",
                                live=lambda t: st.update(text=t), placeholder="XXXX-XXXX-XXXX-XXXX"),
                        ui.button(tr("Send request"), send, primary=True)])]),
            ui.note(tr("Friends with an ID sync automatically – shared lists and binders arrive on their own. You only need a file for friends without an ID (“A friend's collection” or “For friends”).")),
        ])

    def _p_friend_export(self, ui):
        p = self.page
        st = p.fexp or p._friend_state()
        p.fexp = st

        def toggle(key, ident, on):
            (st[key].add if on else st[key].discard)(ident)
        own = st["fmt"] == "bentcorner"
        def toggle_have(ident, on):
            toggle("have", ident, on)
            st["send_lists"] = bool(st["have"])   # trade lists go along as soon as one is ticked
        # trade lists and wishlists alike: checkbox in front, click the row = expand and look inside
        have = [ui.checklist(self._list_items("have", st["have"]), toggle_have,
                             lambda i: self._list_lines("have", i), key="fexp_have",
                             placeholder=tr("Search lists …"), h=320),
                ui.check(tr("Include my library (whole collection)"), st["all_cards"],
                         lambda on: st.update(all_cards=on), tip=tr("Shown under “… 's library” for your friend – to browse"))]
        wish = [ui.checklist(self._list_items("wish", st["wish"]), lambda i, on: toggle("wish", i, on),
                             lambda i: self._list_lines("wish", i), key="fexp_wish",
                             placeholder=tr("Search lists …"), h=320)]
        st["decks"] = False   # "Missing cards of my decks" is gone – put missing cards on a list in the deck builder
        cols = ui.grid([ui.check(tr(label), key in st["cols"], lambda on, k=key: toggle("cols", k, on))
                        for key, label in trade.COLUMNS], 4)
        return self._card(ui, [
            ui.label(tr("Share collection"), bold=True, big=True),
            ui.note(tr("The file is small enough for WhatsApp & co. Your friend imports it under “Trade” – send a new one later and their copy simply gets updated.")),
            ui.form([(tr("Format"), ui.combo([(k, tr(lb)) for k, lb in trade.TEXT_FORMATS], st["fmt"],
                                            lambda v: st.update(fmt=v)))]),
            ui.group(tr("Trade lists (what you offer – shown to your friend under “Has”)"), have, flat=True),
            ui.group(tr("Send wishes along (so they see what you're looking for)"), wish, flat=True) if own else None,
            ui.note(tr("Several lists are merged into one.")),
            ui.group(tr("Columns"), [cols], flat=True) if st["fmt"] == "excel" else None,
            ui.row([ui.stretch(), ui.button(tr("Save …"), p.friend_export, primary=True)]),
        ])

    def _p_session_share(self, ui):
        p = self.page
        opts = p.session_options()
        prev = self._image(ui, p.sshare_img) if p.sshare_img is not None else \
            ui.note(tr("No log with cards yet."))
        return self._card(ui, [
            ui.note(tr("Choose a log – the image shows packs, value, balance and the best hits.")),
            ui.list([{"text": t, "sel": k == p.sshare_sid} for k, t in opts],
                    on_click=lambda r: p.pick_session(opts[r][0]), h=200),
            prev,
            self._img_actions(ui, p.__dict__, "sshare_info", lambda: p.sshare_img,
                              lambda: ((p._sshare_d or {}).get("info", {}).get("title") or "opening")),
        ])

    def _p_offer(self, ui):
        p = self.page
        return self._card(ui, [
            ui.note(tr("In Orbit, tick cards with a friend and click “Offer as image …” – the image then shows up here.")) if p.offer_img is None else None,
            self._image(ui, p.offer_img),
            ui.note(tr("The ticket contains your names, profile IDs and the cards. Share it only with your trade partner, "
                       "not publicly.")) if p.offer_img is not None else None,   # legal 03.11.
            self._img_actions(ui, p.__dict__, "offer_info", lambda: p.offer_img, lambda: tr("Trade offer")),
        ])

    def _auto_backup(self, ui):
        """Automatic backup: lives in the settings – here only the status and the way there."""
        from system import autobackup
        ctrl = self.ctrl
        c = autobackup.cfg(ctrl.settings)
        last = max((float(t.get("ok") or 0) for t in c["targets"]), default=0)
        when = time.strftime("%d.%m.%Y %H:%M", time.localtime(last)) if last else tr("never")
        state = (tr(f"On – {len(c['targets'])} place(s), last {when}.") if c["on"] and c["targets"] else
                 tr("Not set up yet."))
        return self._card(ui, [
            ui.label(f"<b>{tr("Automatic backup")}</b>", rich=True),
            ui.note(tr("Backs up quietly in the background to up to three places (USB stick, drive, cloud folder) – set it up in the settings.") + " " + state),
            ui.row([ui.button(tr("Settings → Backup"),
                              lambda: ctrl.stream.show_page("settings", tab="backup", back=True)), ui.stretch()]),
        ])

    def _p_backup(self, ui):
        from system import datastore
        p = self.page
        info, auto = p.backup_info()
        return ui.col([
            self._card(ui, [
                ui.label(f"<b>{tr("Backup – once, by hand")}</b>", rich=True),
                ui.note(tr("A backup contains everything personal: collection, logs, decks, friends, lists and settings. Card images and card data are downloaded again when needed – they don't need to come along. Handy before moving to a new PC: just restore it there.")),
                ui.label(info),
                ui.row([ui.button(tr("Create backup …"), p.make_backup,
                                  tip=tr("Choose a folder, e.g. a USB stick – a folder “BentCorner backup <date>” is created there")),
                        ui.button(tr("Restore backup …"), p.restore_backup,
                                  tip=tr("Bring back a backup – your current state is saved automatically first")),
                        ui.button(tr("Open data folder"), lambda: QtGui.QDesktopServices.openUrl(
                            QtCore.QUrl.fromLocalFile(str(datastore.DATA)))), ui.stretch()]),
                ui.note(p.bk_msg) if p.bk_msg else None,
            ]),
            ui.group("", [self._auto_backup(ui)], flat=True),
            ui.group("", flat=True, items=[
                ui.label(f"<b>{tr("Silent backups")}</b><br>" + tr(
                    "On top of that, Bent°Corner puts a copy into the data folder under data/backups/auto on start (at most every 6 hours) – the last 7 are kept. That protects against crashes, not against a broken drive: that's what the backup above is for."), rich=True),
                ui.note(auto),
            ]),
        ], spacing=12)

    def _guard(self, ui, v, tab, anyway, what="file"):
        """The line when the file/list belongs to another game or few cards were found here: switch only by the button
        (collection.importguard) – never automatically. anyway: import as it is."""
        p = self.page
        line = p.guard_line(v, what)
        if not line:
            return None
        btns = [ui.stretch()]
        if v.get("other"):
            btns.append(ui.button(p.guard_switch_text(v), lambda: p.guard_switch(tab), primary=True))
        if anyway is not None:
            btns.append(ui.button(p.guard_anyway_text(v), anyway))
        return ui.group("", [ui.label(f"<span style='color:#ffb347'>{html.escape(line)}</span>", rich=True), ui.row(btns)],
                        flat=True)

    def _p_deck(self, ui):
        p = self.page
        st = p.deck

        def setter(key):
            return lambda t: st.update({key: t})
        url = ui.edit(st["url"], lambda t: (st.update(url=t), p.load_url()), key="deckurl", live=setter("url"),
                      placeholder=tr("Paste a link to a public deck list"))
        return self._card(ui, [
            ui.label(tr("Import deck list"), bold=True, big=True),
            ui.row([url, ui.button(tr("Load"), p.load_url, enabled=not st["loading"])]),
            ui.label(st["info"], color="gray"),
            ui.form([(tr("Name"), ui.edit(st["name"], setter("name"), key="deckname", live=setter("name"))),
                     (tr("Format"), ui.combo(decks.FORMATS, st["format"], setter("format")))]),
            ui.textarea(st["text"], setter("text"), key="decktext", live=setter("text"), h=280,
                        placeholder=tr("Paste a list, one card per line – e.g. from Moxfield, Archidekt or Arena:\n\nCommander\n1 Atraxa, Praetors' Voice\n\nDeck\n1 Sol Ring\n1 Arcane Signet\n30 Forest")),
            ui.row([ui.stretch(),
                    ui.button(tr("Clear"), lambda: (p.reset_deck(), self.form._drafts.clear()),
                              tip=tr("Reset link, list and name")),
                    ui.button(tr("Importieren"), lambda: (self.form._drafts.clear(), p.do_deck()), primary=True)]),
            self._guard(ui, p.deck_guard, "deck", lambda: (self.form._drafts.clear(), p.do_deck(anyway=True)), "list"),
        ])

    def _p_collection(self, ui):
        p = self.page
        rows = p.coll_rows()
        return self._card(ui, [
            ui.note(tr("Choose a file from another app (CSV or text list). Name, set, number, count, language and foil are recognized – the usual exports of ManaBox, Moxfield, Deckbox, Dragon Shield, Archidekt and Excel.")),
            ui.row([ui.button(tr("Choose file …"), p.pick_collection), ui.stretch()]),
            ui.label(p.coll_info, rich=True) if p.coll_info else None,
            self._guard(ui, p.coll_guard, "collection", p.do_collection if p._coll else None),
            ui.group("", [ui.label(p.missing_html(), rich=True)], flat=True) if p.coll_missing else None,
            ui.list([{"text": t, "enabled": ok} for t, ok in rows], h=300) if rows else None,
            # another game fits / few cards found: only "Import anyway (12 of 40)" above – no silent import
            ui.row([ui.stretch(), ui.button(tr("Add to collection"), p.do_collection, primary=True)])
            if p._coll and not p.guard_line(p.coll_guard) else None,
        ])

    def _p_wishlist(self, ui):
        p = self.page

        def text(t):
            p.wish_text = t

        def go(anyway=False):
            self.form._drafts.pop("wishtext", None)
            p.do_wishlist(anyway)

        def pick():
            p.pick_wishlist()
            self.form._drafts.pop("wishtext", None)
        return self._card(ui, [
            ui.note(tr("One card per line, optionally with a count (“2 Sol Ring”). Or load a file.")),
            ui.textarea(p.wish_text, text, key="wishtext", live=text, h=240,
                        placeholder="Sol Ring\n2 Arcane Signet\nRhystic Study"),
            ui.row([ui.button(tr("Load file …"), pick), ui.stretch(),
                    ui.button(tr("Add to wishlist"), go, primary=True)]),
            ui.label(p.wish_info, rich=True) if p.wish_info else None,
            self._guard(ui, p.wish_guard, "wishlist", lambda: go(True), "list"),
        ])

    def _p_friend(self, ui):
        return self._card(ui, [
            ui.note(tr("The file your friend saved under “Orbit → Export …” – or a CSV from another app. Bent°Corner recognizes a known collection and updates it; your own stays untouched.")),
            ui.row([ui.button(tr("Choose file …"), self.page.do_friend), ui.stretch()]),
        ])

    def _p_sets(self, ui):
        return self._card(ui, [
            ui.note(tr("Set packages (.zip) someone saved under Settings → Card data → “Export sets …”. The sets are recognizable right away – no download.")),
            ui.row([ui.button(tr("Choose set packages …"), self.ctrl.import_sets_dialog), ui.stretch()]),
        ])

    # ---------- for QML ----------
    @QtCore.Property("QVariantList", notify=changed)
    def groups(self):
        from ui import importview
        from system import autobackup
        warn = False   # the backup indicator light only shows in the settings now
        return [{"title": tr(g), "tabs": [{"key": k, "icon": i, "title": tr(t), "sub": tr(s), "badge": warn and k == "backup"}
                                          for k, i, t, s in tabs]}
                for g, tabs in importview.GROUPS]

    @QtCore.Property("QVariantMap", constant=True)
    def backupLink(self):
        """Backups live only in the settings (STREAMLINE §4) – the way there, at the foot of the side bar."""
        return {"title": tr("Settings → Backup"), "sub": tr("Automatic backup, one-off backup, restore and moving")}

    @QtCore.Slot()
    def openBackup(self):
        self.ctrl.stream.show_page("settings", tab="backup", back=True)

    @QtCore.Property(str, notify=changed)
    def current(self):
        return self.page.current

    @QtCore.Slot(str)
    def show(self, key):
        self.page.show_tab(key)
        self.form.set_build(self._build)

    @QtCore.Property(QtCore.QObject, constant=True)
    def mirror(self):
        return self.form
