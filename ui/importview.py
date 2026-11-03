"""The "Import/Export" tab (between Decks and Trade), laid out like the settings: the kinds on the left, the form on
the right. Everything that comes into the app or leaves it, in one place.

Import:

    Decklist             – link (via Commander Spellbook) or text → new deck
    Collection           – CSV/text from other apps (ManaBox, Moxfield, Deckbox, Dragon Shield …) → own collection
    Wishlist             – paste card names or a file → wishlist
    Your ID              – copy your own ID / enter a friend's ID (server exchange, relay.py)
    A friend's collection – Bent°Corner file or CSV → friend library (trade)
    Set packages         – recognition data + images (.zip) → sets

Export:
    Share decks          – commander, name, bracket as an image (playgroup)
    Decklist             – text for Moxfield/Arena: clipboard or file
    Collection           – CSV for ManaBox, Moxfield, Deckbox, Excel
    For friends          – trade file (formerly a separate window in the trade tab)
    Share session        – recap as an image
    Trade offer          – the offer from the trade tab as an image
    Backup               – back up / restore everything personal

Other pages jump straight to the matching entry (ctrl.show_import(key) or ctrl.go_export(key, …)).
No widgets: ImportPage holds the state, qimport shows it as a form.
"""
import re
import time
from pathlib import Path

from PySide6 import QtCore, QtGui

import games
from cards import carddb
from system import datastore
from collection import decks
from ui import qdialogs
from ui import qstate
from collection import trade
from system.i18n import tr

TABS = [("deck", "◆", "Deckliste", "Link von Moxfield, Archidekt … oder eine Textliste – wird ein neues Deck"),
        ("collection", "▦", "Sammlung", "CSV oder Textliste aus ManaBox, Moxfield, Deckbox, Dragon Shield … – "
                                         "kommt in deine Sammlung"),
        ("wishlist", "☆", "Wunschliste", "Kartennamen einfügen oder eine Datei laden – kommt auf die Wunschliste"),
        ("friend_code", "#", "Deine ID", "Deine ID weitergeben, die ID eines Freundes eintragen – dann gleicht "
                                          "sich alles von selbst über den Server ab"),
        ("friend", "⇄", "Sammlung eines Freundes", "Datei eines Freundes ohne ID (Bent°Corner-Datei oder CSV) – "
                                                    "für den Tausch"),
        ("sets", "◈", "Set-Pakete", "Erkennungsdaten und Bilder (.zip) von jemand anderem – ohne Download")]
EXPORT_TABS = [
    ("share_decks", "▣", "Deck-Übersicht als Bild", "Commander, Name und geschätztes Bracket als Bild – für deine "
                                                     "Playgroup"),
    ("deck_export", "◆", "Deckliste exportieren", "Text für Moxfield, Arena & Co. – Zwischenablage oder Datei"),
    ("coll_export", "▦", "Sammlung exportieren", "CSV für ManaBox, Moxfield, Deckbox oder Excel"),
    ("friend_export", "⇄", "Für Freunde", "Tausch-Datei: deine Tauschlisten, Wünsche und auf Wunsch deine Bibliothek"),
    ("session_share", "☰", "Log teilen", "Recap eines Logs als Bild – Packs, Wert, beste Hits"),
    ("offer", "⇆", "Tauschangebot", "Das Angebot aus Orbit als Bild")]
# Backups (once by hand, restore, automatic) live only under Settings → Backup (STREAMLINE §4)
_ALL = {t[0]: t for t in TABS + EXPORT_TABS}
# four areas: what you own · decks · trading with friends · sharing (images)
GROUPS = [("YOUR COLLECTION", [_ALL[k] for k in ("collection", "coll_export", "sets")]),
          ("DECKS & LOGS",   # a session is a "log" since .73 (03.11.)
           [_ALL[k] for k in ("deck", "deck_export", "share_decks", "session_share")]),
          ("TAUSCH & FREUNDE", [_ALL[k] for k in ("friend_code", "friend", "friend_export", "wishlist", "offer")])]
_NUM = re.compile(r"^\s*(\d+)\s*[xX]?\s+(.+)$")


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _name_ok(full, name):
    """Does the name from the file match this card? Every face counts – including the back of a double-faced card
    ("Fully-Grown Treefolk" = back of "Plant a Sapling // Fully-Grown Treefolk"; that is how the scanner stores it
    when it recognises the back)."""
    full = (full or "").lower()
    return name in (full, *(x.strip() for x in full.split(" // ")))


def _missing(r, why):
    """Row not found -> {name, set, number, count, why} (shown at the top during import)."""
    return {"name": r[5] or (r[6] if len(r) > 6 and r[6] else "?"), "set": (r[0] or "").upper(),   # ID line: show the ID
            "number": r[1] or "", "count": r[4] or 1, "why": why}


def guard_items(rows):
    """Rows as in resolve -> [(name, set, number, ID)] for collection.importguard."""
    return [(r[5] or "", r[0] or "", r[1] or "", r[6] if len(r) > 6 and isinstance(r[6], str) else "") for r in rows]


def resolve(rows, fits=None):
    """[[set, nr, lang, foil, n, name, (Scryfall ID), (condition)]] -> [(card, language, foil, count, condition,
    by name only)], [not found] –
    exact printing via the Scryfall ID, otherwise if set and number match, otherwise the same name in the set,
    otherwise the newest printing of the name. Each row is resolved on its own (rows without a number used to share
    the key "set + empty number" – then all cards of a set turned into the last card of that set).
    The name alone only for a row whose set the game knows (or that has none) – or if the file as a whole is this
    game's (fits, collection.importguard: a brand-new set the database doesn't know yet). Never across games: a
    Magic "Forest" never becomes the Yu-Gi-Oh! field spell "Forest"."""
    from collection import importguard
    if fits is None:
        fits = importguard.verdict(guard_items(rows))["fits"]
    out, missing = [], []
    if not carddb.exists():
        return out, [_missing(r, tr("No card database – load it first (Settings → Card data)."))
                     for r in rows]
    exact = {}  # row number -> card row
    with carddb.connection() as con:
        for i, r in enumerate(rows):
            name = (r[5] or "").strip().lower()
            hit = None
            if len(r) > 6 and r[6]:
                hit = con.execute("SELECT * FROM cards WHERE id = ?", (r[6],)).fetchone()
                if hit is not None and name and not _name_ok(hit["name"], name):
                    hit = None
            if hit is None and not r[0]:
                continue
            if hit is None and r[1]:
                hit = con.execute("SELECT * FROM cards WHERE set_code = ? AND number = ?",
                                  (r[0].lower(), str(r[1]))).fetchone()
                if hit is not None and name and not _name_ok(hit["name"], name):
                    hit = None  # number doesn't match the name: the name wins
            if hit is None and name:  # same name in the same set
                hit = con.execute("SELECT * FROM cards WHERE set_code = ? AND (lower(name) = ? OR lower(name) LIKE ? "
                                  "OR lower(name) LIKE ?) ORDER BY booster DESC LIMIT 1",
                                  (r[0].lower(), name, name + " // %", "% // " + name)).fetchone()
            if hit is not None:
                exact[i] = dict(hit)
    by_name = carddb.by_names([r[5] for i, r in enumerate(rows) if i not in exact])
    known_sets = None
    nick = games.nick_of(games.current().key)
    for i, r in enumerate(rows):
        row = exact.get(i)
        named = row is None
        sid = r[6] if len(r) > 6 and isinstance(r[6], str) else ""
        if row is None and not importguard.name_only_ok(r[0], fits, sid=sid):
            code = (r[0] or "").upper()
            missing.append(_missing(r, tr(f"The set {code} isn't a {nick} set – this line belongs to another game. "
                                          "It won't be imported.")))
            continue
        if row is None:
            row = by_name.get((r[5] or "").lower())
        if row is None:
            if known_sets is None:
                known_sets = carddb.set_codes() or set()
            code = (r[0] or "").lower()
            if code and known_sets and code not in known_sets:
                why = tr(f"Your card database doesn't know the set {code.upper()} yet – update the card database (Settings → Card data) and import again.")
            else:
                why = tr("The card database doesn't know this name – usually a playtest/special card our card data doesn't list, or a typo in the name. It won't be imported.")
            missing.append(_missing(r, why))
            continue
        out.append((carddb.entry_from_row(row), r[2] or "en", bool(r[3]), max(1, int(r[4] or 1)),
                    r[7] if len(r) > 7 and isinstance(r[7], str) else None, named))
    return out, missing


class ImportPage(QtCore.QObject):
    """Import/export as data (shown by qimport as a form): state per entry, logic as before."""
    changed = QtCore.Signal()
    url_done = QtCore.Signal(object, object, str)  # decklist from a link (background thread)

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.ctrl = ctrl
        self.keys = [t[0] for _, tabs in GROUPS for t in tabs]
        self.current, self._ctx = "deck", {}
        self.offer_img, self._share_tries = None, 0
        # Share decks
        self.share_ids, self.share_img, self.share_info = set(), None, ""
        self.share_title = ""   # custom heading for the image (empty = "My Lineup" or the deck name)
        self.cover_open, self.cover_filter, self._cover_deck, self._cover_rows, self.cover_text = False, "", None, {}, ""
        self._share_timer = QtCore.QTimer(self, singleShot=True, interval=150, timeout=self._share_render)
        # export decklist / export collection
        self.dexp_id, self.dexp_ids, self.dexp_info = None, set(), ""
        self.cexp_info = qstate.Text()
        # For friends
        self.fexp = None
        # Share session
        self.sshare_sid, self.sshare_img, self._sshare_d, self.sshare_info = None, None, None, ""
        self.offer_info = ""
        # Backup
        self.bk_msg = ""
        # Import decklist
        self.deck = {"url": "", "name": tr("New deck"), "format": decks.FORMATS[0][0], "text": "", "loading": False,
                     "info": tr("Links go through Commander Spellbook (card names only). Moxfield/Archidekt: use “Export” as text there and paste it below – with exact printings.")}
        self.url_done.connect(self._url_done)
        # Import collection
        self._coll, self.coll_info, self.coll_missing = [], "", []
        self._coll_rows, self.coll_guard = None, None   # the file's rows, collection.importguard.verdict
        # Wishlist
        self.wish_text, self.wish_info, self.wish_guard = "", "", None
        self.deck_guard = None

    # --- Which game does the file belong to (collection.importguard) – the switch only by the button ---
    @staticmethod
    def guard_line(v, what="file"):
        """The line above the import: another game fits the file better / only few cards found here. "" = all well."""
        if not v:
            return ""
        if v["other"]:
            g, k, n = games.nick_of(v["other"]), v["other_ok"], v["n"]
            return (tr(f"This file looks like {g} ({k} of {n} cards found there) – import it there?") if what == "file"
                    else tr(f"This list looks like {g} ({k} of {n} cards found there) – import it there?"))
        if v["few"]:
            g, k, n = games.nick_of(v["game"]), v["ok"], v["n"]
            return tr(f"Only {k} of {n} cards were found in {g} – check the list before importing.")
        return ""

    @staticmethod
    def guard_switch_text(v):
        return tr(f"Switch to {games.nick_of(v['other'])}") if v and v.get("other") else ""

    @staticmethod
    def guard_anyway_text(v):
        return tr(f"Import anyway ({v['ok']} of {v['n']})") if v else ""

    def guard_switch(self, tab):
        """Button "Switch to Magic": switch the game, then read the same file/list there again (nothing is imported
        until the user clicks import)."""
        v = {"collection": self.coll_guard, "deck": self.deck_guard, "wishlist": self.wish_guard}.get(tab)
        if not v or not v.get("other"):
            return

        def again():
            if tab == "collection" and self._coll_rows is not None:
                self._read_collection(self._coll_rows)
            elif tab == "deck":
                self.deck_guard = None
            elif tab == "wishlist":
                self.wish_guard = None
            self.ctrl.show_import(tab)
            self._changed()
        if not self.ctrl.switch_game(v["other"], then=again):
            self.ctrl.stream_toast(tr("Switching the game isn't possible right now – try again in a moment."))

    def _changed(self):
        self.changed.emit()

    def show_tab(self, key, **ctx):
        """Open an entry – ctx: deck_ids (share decks), deck_id (decklist), sid (session), img (offer)."""
        if key not in self.keys:
            return
        self._ctx = ctx
        if "img" in ctx:
            self.offer_img = ctx["img"]
        self.current = key
        fill = {"share_decks": self.fill_share_decks, "deck_export": self.fill_deck_export,
                "session_share": self.fill_session_share}.get(key)
        if fill is not None:
            fill()
        if key == "friend_export" and self.fexp is None:
            self.fexp = self._friend_state()
        self._ctx = {}
        self._changed()

    def _decks(self):
        page = getattr(self.ctrl, "deck_page", None)
        lst = list(page.decks) if page is not None else decks.load()
        return sorted(lst, key=lambda d: -d.get("updated", 0))

    # ========== Images: copy / save ==========
    @staticmethod
    def copy_image(img):
        if img is not None:
            QtGui.QGuiApplication.clipboard().setImage(img)
            return tr("✓ Copied – now paste it (Ctrl+V).")
        return ""

    @staticmethod
    def save_image(img, name):
        if img is None:
            return ""
        safe = re.sub(r"[^\w\- ]+", "", name)[:60] or "bentcorner"
        path = qdialogs.save_file(tr("Save image"), f"{safe}.png", "PNG (*.png)")
        if path:
            img.save(path, "PNG")
            return tr("✓ Saved: ") + path
        return ""

    # --- Share decks (image) ---
    def fill_share_decks(self):
        self.ctrl.stream.ensure_page("decks")  # card images come via the Decks page's image loader
        pre = set((self._ctx or {}).get("deck_ids") or [])
        if pre:
            self.share_ids = pre
        self._share_tries = 0
        self._share_render()

    def toggle_share(self, did, on):
        (self.share_ids.add if on else self.share_ids.discard)(did)
        self._share_timer.start()

    def cover_rows(self):
        """Cards of the selected deck for the title card -> [(sid, text)] (first row = default)."""
        d, rows = self._cover_deck, self._cover_rows
        if d is None:
            return []
        q = self.cover_filter.strip().lower()
        out = [("", "↺  " + tr("Default (commander or suggestion)"))]
        seen = set()
        for sid in list(d.get("commanders", [])) + [c["sid"] for c in d.get("cards", [])]:
            r = rows.get(sid)
            if r is None or r["name"] in seen or (q and q not in r["name"].lower()):
                continue
            seen.add(r["name"])
            out.append((sid, ("✓  " if d.get("cover") == sid else "") + r["name"]))
        return out

    def pick_cover(self, sid):
        d = self._cover_deck
        if d is None:
            return
        if sid:
            d["cover"] = sid
        else:
            d.pop("cover", None)
        page = getattr(self.ctrl, "deck_page", None)
        if page is not None:
            page.save()
            page.fill_overview()  # the tile shows the same title card
        self.cover_open = False
        self._share_tries = 0
        self._share_render()

    def _share_render(self):
        from cards import combos
        from collection import deckshare
        from system import userprofile
        chosen = [d for d in self._decks() if d["id"] in self.share_ids]
        if len(chosen) != 1:
            self.cover_open = False
        if not chosen:
            self.share_img = None
            self._changed()
            return
        all_ids = set()
        for d in chosen:
            all_ids |= decks.all_ids(d) | ({d["cover"]} if d.get("cover") else set())
        rows = carddb.cards_by_ids(all_ids) if carddb.exists() else {}
        page = getattr(self.ctrl, "deck_page", None)
        if page is not None and not hasattr(page, "owned_id"):
            page.update_owned()
        owned = getattr(page, "owned_id", None) or {}
        owned_names = getattr(page, "owned_name", None) or {}
        items, missing = [], False
        for d in chosen:
            a = decks.analyze(d, rows, owned, owned_names)
            covers = deckshare.cover_rows(d, rows)
            n_combos = len(a.get("combos") or [])
            try:
                cm, main = combos.deck_lists(d, rows)
                found = combos.cached_find(cm, main) if cm else None  # only from the cache, without internet
                if found and found.get("included") is not None:
                    n_combos = len(found["included"])
            except Exception:  # noqa: BLE001
                pass
            items.append({"name": d["name"], "format": dict(decks.FORMATS).get(d.get("format"), ""),
                          "bracket": a.get("bracket") if d.get("format") == "commander" else None,
                          "covers": covers,
                          "identity": a.get("identity") or "".join(c for c in "WUBRG" if a["colors"].get(c)),
                          "curve": a.get("curve"), "roles": a.get("roles"), "combos": n_combos,
                          "game_changers": a.get("game_changers"), "count": a.get("count"), "size": a.get("size"),
                          "price": a.get("price"), "avg_mv": a.get("avg_mv"),
                          "owned_pct": round(100 * a["owned"] / a["count"]) if a.get("count") else None,
                          "built": bool(d.get("built"))})
            for r in covers:
                if page is not None and page.art(r) is None:
                    missing = True
        if len(chosen) == 1:
            d = chosen[0]
            self._cover_deck, self._cover_rows = d, rows
            cov = items[0]["covers"]
            how = tr("own choice") if d.get("cover") else tr("Commander") if d.get("commanders") else tr("Suggestion")
            self.cover_text = tr("Cover card: ") + (" + ".join(r["name"] for r in cov) or "–") + f"  ({how})"

        def art_for(row):
            return page.art(row) if page is not None and row is not None else None
        self.share_img = deckshare.render(items, art_for, userprofile.ensure(self.ctrl.settings), self.share_title)
        self._changed()
        if missing and self._share_tries < 16:  # images still loading: redraw shortly
            self._share_tries += 1
            QtCore.QTimer.singleShot(500, self._share_render)

    # --- Export decklist ---
    def fill_deck_export(self):
        ctx = self._ctx or {}
        ids = [d["id"] for d in self._decks()]
        pre = [i for i in (ctx.get("deck_ids") or []) if i in ids]
        if not pre and ctx.get("deck_id") in ids:
            pre = [ctx["deck_id"]]
        if pre:
            self.dexp_ids = set(pre)
        self.dexp_ids &= set(ids)
        if not self.dexp_ids and ids:
            self.dexp_ids = {self.dexp_id if self.dexp_id in ids else ids[0]}
        self.dexp_id = next((i for i in ids if i in self.dexp_ids), None)
        self.dexp_info = ""

    def toggle_dexp(self, did, on=None):
        on = (did not in self.dexp_ids) if on is None else on
        (self.dexp_ids.add if on else self.dexp_ids.discard)(did)
        self.dexp_info = ""
        self._changed()

    def _dexp_texts(self):
        """[(deck, text)] of the selected decks (order as in the list)."""
        out = []
        for d in self._decks():
            if d["id"] in self.dexp_ids:
                rows = carddb.cards_by_ids(decks.all_ids(d)) if carddb.exists() else {}
                out.append((d, decks.to_text(d, rows)))
        return out

    def dexp_clip(self):
        items = self._dexp_texts()
        if not items:
            return
        if len(items) == 1:
            QtGui.QGuiApplication.clipboard().setText(items[0][1])
            self.dexp_info = tr("✓ In the clipboard – e.g. paste it in Moxfield under “Import”.")
        else:  # several: one after another, each with the deck name as a heading
            QtGui.QGuiApplication.clipboard().setText("\n\n".join(f"// {d['name']}\n{t}" for d, t in items))
            self.dexp_info = tr(f"✓ {len(items)} decklists on the clipboard – Moxfield & co. import one deck at a time, so paste them one by one.")

    def dexp_file(self):
        items = self._dexp_texts()
        if not items:
            return
        if len(items) == 1:
            d, text = items[0]
            path = qdialogs.save_file(tr("Export deck"), f"{d['name']}.txt", tr("Text (*.txt)"))
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                self.dexp_info = tr("✓ Saved: ") + path
            return
        folder = qdialogs.get_dir(tr("Folder for the decklists"))
        if not folder:
            return
        import pathlib
        base, used = pathlib.Path(folder), set()
        for d, text in items:
            stem = re.sub(r'[<>:"/\\|?*]+', "", d["name"]).strip()[:80] or "deck"
            path, n = base / f"{stem}.txt", 2
            while path.exists() or path in used:
                path, n = base / f"{stem} ({n}).txt", n + 1
            used.add(path)
            path.write_text(text, "utf-8")
        self.dexp_info = tr(f"✓ {len(items)} decklists saved in ") + str(base)

    # --- For friends (trade file) ---
    def _friend_state(self):
        return {"fmt": trade.TEXT_FORMATS[0][0], "send_lists": True,
                "have": {x["id"] for x in trade.lists("have") if x["id"] == trade.MAIN_HAVE},
                "all_cards": False, "wish": {x["id"] for x in trade.lists("wish") if not x.get("example")},
                "decks": True, "cols": set(trade.PRESET_COLUMNS["excel"])}

    def friend_export(self):
        """Save the trade file (Bent°Corner, ManaBox, Moxfield, Deckbox, text, Excel)."""
        from system import userprofile
        st = self.fexp
        self.ctrl.stream.ensure_page("trade")
        tpage = self.ctrl.trade_page
        fmt, library = st["fmt"], st["all_cards"]
        chosen = sorted(st["have"]) if st["send_lists"] else []
        if fmt == "bentcorner":  # trade lists in "c", library separately – or only the library
            what = "lists" if chosen else "all" if library else "none"
        else:  # other formats only know a single list
            what = "all" if library else "lists" if chosen else "none"
        if what == "none" and fmt != "bentcorner":
            qdialogs.info(tr("Export"), tr("Please choose the whole collection or at least one list."))
            return
        ctrl = self.ctrl
        prof = userprofile.ensure(ctrl.settings)
        name = prof.get("name") or tr("Mine")
        ext = {"bentcorner": trade.EXT, "text": ".txt"}.get(fmt, ".csv")
        kind = {"all": tr("Collection"), "lists": tr("Trade cards"), "none": tr("Wishlist")}[what]
        path = qdialogs.save_file(tr("Export"), f"{name} – {kind}{ext}", f"*{ext}")
        if not path:
            return
        items = ctrl.collection.items
        try:
            have = trade.have_items(items, chosen) if what == "lists" else None
            if fmt == "bentcorner":
                missing = tpage.deck_missing() if st["decks"] else None
                wl = sorted(st["wish"])
                data = trade.build_export(prof, items, what, trade.wishes(wl) if wl else None, missing, have,
                                          library=library)
                trade.write_bentcorner(path, data)
                n = len(data["c"])
                ctrl.relay_send_lists(data)   # mailbox on: also to all friends (in the background)
            else:
                groups = tpage.export_groups(None if what == "all" else have)
                if fmt in ("manabox", "moxfield"):
                    from collection import collection
                    n = collection.export_csv(groups, path, fmt)
                elif fmt == "deckbox":
                    n = trade.export_deckbox(groups, path)
                elif fmt == "text":
                    n = trade.export_text(groups, path)
                else:
                    cols = [k for k, _ in trade.COLUMNS if k in st["cols"]] or ["count", "name"]
                    db = carddb.cards_by_ids({g["sid"] for g in groups}) if carddb.exists() else {}
                    n = trade.export_custom(groups, path, cols, db)
        except OSError as e:
            qdialogs.warn(tr("Export"), tr(f"Couldn't save: {e}"))
            return
        tpage.toast(tr(f"Exported: {n} entries → {path}"))

    # --- Share session ---
    def session_options(self):
        from collection import sessions
        out = []
        for d in sessions.load_all():
            if not (d.get("stats") or {}).get("cards") or sessions.is_import(d):
                continue
            when = time.strftime("%d.%m.%Y", time.localtime(d.get("started", 0)))
            out.append((d["id"], f"{when}   ·   {(d.get('info') or {}).get('title') or tr("untitled")}"
                                 f"   ·   {d['stats'].get('packs', 0)} Packs"))
        return out

    def fill_session_share(self):
        cur = (self._ctx or {}).get("sid") or self.sshare_sid
        ids = [k for k, _ in self.session_options()]
        self.sshare_sid = cur if cur in ids else (ids[0] if ids else None)
        self._sshare_render()

    def pick_session(self, sid):
        self.sshare_sid = sid
        self._sshare_render()

    def _sshare_render(self):
        from collection import sessions
        from collection import share
        sid = self.sshare_sid
        if not sid:
            self.sshare_img = None
            return
        obj = self.ctrl.session_obj(sid) if hasattr(self.ctrl, "session_obj") else None
        d = obj.to_dict() if obj is not None else sessions.load(sid)
        self._sshare_d = d
        self.sshare_img = share.render(d, self.ctrl.settings)
        self._changed()

    # --- Backup ---
    def backup_info(self):
        n = sum(int(it.get("count", 1)) for it in self.ctrl.collection.items)
        size = datastore.personal_size() / 1024 / 1024
        last = self.ctrl.settings.get("last_backup")
        when = time.strftime("%d.%m.%Y %H:%M", time.localtime(last)) if last else tr("never")
        snaps = datastore.snapshots()
        auto = tr(f"{len(snaps)} silent backups") + (
            " · " + tr("last") + " " + time.strftime("%d.%m.%Y %H:%M", time.localtime(snaps[0].stat().st_mtime))
            if snaps else "")
        return tr(f"Your data: {n} cards · {size:.1f} MB · last backup: {when}"), auto

    def make_backup(self):
        folder = qdialogs.get_dir(tr("Where should the backup go?"), "")
        if not folder:
            return
        import pathlib
        self.ctrl.save_collection()
        self.ctrl.save_settings()
        from ui.busy import busy
        try:
            with busy(self.ctrl, tr("Backing up …")):
                dest = datastore.create_backup(pathlib.Path(folder))
        except OSError as e:
            self.bk_msg = tr(f"Couldn't back up: {e}")
            return
        self.ctrl.settings["last_backup"] = time.time()
        self.ctrl.settings_changed()
        self.bk_msg = tr("✓ Backed up: ") + str(dest)

    def restore_backup(self):
        import pathlib
        what = qdialogs.ask(tr("Restore backup"), tr("What do you want to restore?"),
                            [("cancel", tr("Cancel"), ""), ("dir", tr("Folder"), ""),
                             ("zip", tr("ZIP file (automatic backup)"), "active")])
        if what == "zip":
            folder = qdialogs.open_file(tr("Choose backup (ZIP file)"), "", "*.zip")
        elif what == "dir":
            folder = qdialogs.get_dir(tr("Choose backup"), "")
        else:
            return
        if not folder:
            return
        info = datastore.backup_info(pathlib.Path(folder))
        if info is None:
            self.bk_msg = tr("This is not a Bent°Corner backup (the my-data folder is missing).")
            return
        if not qdialogs.question(tr("Restore backup"),
                                 tr(f"Restore the backup with {info['cards']} cards and {info['sessions']} logs?\n\nYour current state is saved automatically first (data/backups/auto). Bent°Corner restarts afterwards.")):
            return
        from ui.busy import busy
        with busy(self.ctrl, tr("Restoring backup …")):
            ok = datastore.restore_backup(pathlib.Path(folder))
        if ok:
            self.ctrl.restart_after_restore()

    # --- Import decklist ---
    def load_url(self):
        from collection import deckimport
        import threading
        st = self.deck
        url = st["url"].strip() or st["text"].strip()
        if not deckimport.is_url(url):
            st["info"] = tr("That doesn't look like a link.")
            return
        st["loading"], st["info"] = True, tr("Loading deck list …")

        def work():
            try:
                self.url_done.emit(url, deckimport.fetch(url), "")
            except Exception as e:  # noqa: BLE001 – offline, private, unknown site …
                self.url_done.emit(url, None, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _url_done(self, url, res, err):
        st = self.deck
        st["loading"] = False
        if err or not res:
            st["info"] = f"<span style='color:#ff8a8a'>{tr("Loading failed")}: {tr(err)}</span>"
        else:
            st["text"] = res["text"]
            if res.get("name"):
                st["name"] = res["name"]
            if res.get("format") in dict(decks.FORMATS):
                st["format"] = res["format"]
            n = sum(int(ln.split(" ", 1)[0]) for ln in res["text"].splitlines() if ln[:1].isdigit())
            msg = tr(f"{n} cards loaded from {res['source']} – check and “Import”.")
            st["info"] = f"<span style='color:#46d17a'>✓ {msg}</span>"
        self._changed()

    def reset_deck(self):
        self.deck.update(url="", text="", name=tr("New deck"))

    def do_deck(self, anyway=False):
        from collection import deckimport
        st = self.deck
        if deckimport.is_url(st["text"].strip()):  # link pasted into the text field: load it first
            st["url"] = st["text"].strip()
            self.load_url()
            return
        name, fmt, text = st["name"], st["format"], st["text"]
        if not text.strip():
            self.reset_deck()
            return
        from collection import importguard
        v = importguard.verdict([(n, s or "", num or "", "") for _, n, s, num, *_ in decks.parse_text(text)])
        if (v["other"] or v["few"]) and not anyway:   # another game / few cards here: say so, import only on a click
            self.deck_guard = v
            self._changed()
            return
        self.reset_deck()
        self.deck_guard = None
        self.ctrl.stream.show_page("decks", back=True)
        self.ctrl.deck_page.import_from(name, fmt, text, fits=v["fits"])

    # --- Collection ---
    def pick_collection(self):
        path = qdialogs.open_file(tr("Import collection"),
                                  "", tr("Collections (*.csv *.txt *.bentcorner);;All files (*)"))
        if not path:
            return
        try:
            parsed = trade.read_file(path)
        except (OSError, ValueError) as e:
            self.coll_info = f"<span style='color:#ff8a8a'>{tr(f"Couldn't read the file: {e}")}</span>"
            return
        rows = parsed["data"].get("c", []) if parsed["kind"] == "bentcorner" else parsed["data"]
        self.coll_name = Path(path).name
        self._read_collection(rows)

    def _read_collection(self, rows):
        from collection import importguard
        self._coll_rows = rows
        self.coll_guard = v = importguard.verdict(guard_items(rows))
        cards, missing = resolve(rows, fits=v["fits"])
        self._coll, self.coll_missing = cards, missing
        n = sum(x[3] for x in cards)
        self.coll_info = (tr(f"<b>{n}</b> cards recognized ({len(cards)} entries)")
                          + (f" · <span style='color:#ffb347'>{tr(f"{len(missing)} not found")}</span>"
                             if missing else ""))

    def missing_html(self):
        """Cards not found – at the top, one by one, with a reason (otherwise they hide at the end of the list)."""
        if not self.coll_missing:
            return ""
        groups = {}   # same reason (e.g. a whole set of another game): the cards one after another, the reason once
        for m in self.coll_missing[:200]:
            where = " · ".join(x for x in (m["set"], f"#{m['number']}" if m["number"] else "") if x)
            groups.setdefault(m["why"], []).append(
                f"<b>{_esc(m['name'])}</b>"
                + (f" <span style='color:#8e8e8e'>({_esc(where)}, {m['count']}×)</span>" if where else ""))
        lines = [", ".join(cards) + f"<br><span style='color:#b0b0b0'>{_esc(why)}</span>"
                 for why, cards in groups.items()]
        more = len(self.coll_missing) - 200
        return ("<span style='color:#ffb347'><b>" + tr("Not found – won't be imported:") + "</b></span><br>"
                + "<br><br>".join(lines) + (f"<br>… {more}" if more > 0 else ""))

    def coll_rows(self):
        from cards import conditions
        out = [(f"{k}× {card['name']}  ·  {card['set']} #{card['number']}  ·  {lang.upper()}"
                + ("  ·  Foil" if foil else "") + (f"  ·  {conditions.short({'cond': cond})}" if cond else "")
                + (f"  ·  {tr('name only')}" if named else ""), True)
               for card, lang, foil, k, cond, named in self._coll[:500]]

        return out

    def do_collection(self):
        """Import into your own collection – as its own entry under Sessions ("Import: file"): there it can be removed
        from the collection like a session or deleted entirely. It does not count in statistics."""
        from scanner import core
        from collection import sessions
        coll = self.ctrl.collection
        if not self._coll:
            return
        now = time.time()
        sid = "import_" + time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(now))
        while (sessions.SESSIONS / f"{sid}.json").exists():
            sid += "b"
        entries = []
        for card, lang, foil, k, cond, _named in self._coll:
            for _ in range(max(1, int(k))):
                e = dict(card, foil=bool(foil), added=now + len(entries) * 0.001)  # unique per copy
                e["cond"] = cond or "near_mint"   # from the file – otherwise Near Mint (as before)
                e.pop("thumb", None)
                core.Session._set_lang(e, lang or "en")
                e["price"] = core.price_of(e)
                entries.append(e)
        title = tr("Import: ") + (getattr(self, "coll_name", "") or tr("Collection"))
        sess = core.Session(getattr(self.ctrl, "cards", None) or (),
                            {"id": sid, "started": now, "ended": now, "collection": True,
                             "info": {"title": title, "import": True, "kind": "import", "pack_type": "import"},
                             "packs": [{"opened": now, "cards": entries, "type": "import"}]})
        d = sess.to_dict()
        sessions.save(d)
        coll.sync_session(d)
        coll.save()
        n = len(entries)
        self._coll, self.coll_missing, self._coll_rows, self.coll_guard = [], [], None, None
        self.coll_info = (f"<span style='color:#46d17a'>✓ {tr(f"{n} cards are now in your collection.")}</span> "
                          + tr("The import is listed under Logs & stats – you can remove it there."))
        refresh = getattr(self.ctrl, "refresh_stats", None)
        if refresh is not None:
            refresh()
        lib = getattr(self.ctrl, "library_win", None)
        if lib is not None:
            lib.refresh(keep=True)

    # --- Wishlist ---
    def pick_wishlist(self):
        path = qdialogs.open_file(tr("Load wishlist"), "", tr("Lists (*.txt *.csv);;All files (*)"))
        if not path:
            return
        try:
            parsed = trade.read_file(path)
            rows = parsed["data"].get("c", []) if parsed["kind"] == "bentcorner" else parsed["data"]
            self.wish_text = "\n".join(f"{r[4]} {r[5]}" for r in rows)
        except (OSError, ValueError):
            try:
                self.wish_text = open(path, encoding="utf-8-sig", errors="replace").read()
            except OSError as e:
                self.wish_info = f"<span style='color:#ff8a8a'>{tr(f"Couldn't read the file: {e}")}</span>"

    def do_wishlist(self, anyway=False):
        from collection import importguard
        lines, sets = [], []
        for raw in self.wish_text.splitlines():
            m_set = re.search(r"\s*\(([A-Za-z0-9]{2,6})\)\s*[\w\-★]*\s*$", raw.strip())
            line = raw.strip()[:m_set.start()] if m_set else raw.strip()   # strip "(SET) 123"
            if not line or line.lower().strip("/#: ") in ("deck", "commander", "sideboard", "maybeboard"):
                continue
            m = _NUM.match(line)
            lines.append((int(m.group(1)), m.group(2).strip()) if m else (1, line))
            sets.append(m_set.group(1) if m_set else "")
        if not lines:
            return
        v = importguard.verdict([(name, s, "", "") for (_, name), s in zip(lines, sets)])
        if (v["other"] or v["few"]) and not anyway:   # another game / few cards here: say so, import only on a click
            self.wish_guard = v
            return
        self.wish_guard = None
        found = carddb.by_names([n for _, n in lines]) if carddb.exists() else {}
        items = trade.wishes(raw=True)
        added, missing = 0, []
        for (n, name), set_code in zip(lines, sets):
            r = found.get(name.lower()) if importguard.name_only_ok(set_code, v["fits"]) else None
            if r is None and carddb.exists():
                missing.append(name)
                continue
            real = r["name"] if r else name
            hit = next((w for w in items if w["name"] == real and (w.get("list") or trade.MAIN_WISH) == trade.MAIN_WISH), None)
            if hit:
                hit["count"] = max(int(hit.get("count", 1)), n)
            else:
                items.append({"name": real, "count": n, "set": None, "number": None, "note": "", "added": time.time()})
            added += 1
        trade.save_wishes(items)
        page = getattr(self.ctrl, "trade_page", None)
        if page is not None:
            page.fill_wishes()
        self.wish_text = ""
        self.wish_info = (f"<span style='color:#46d17a'>✓ {tr(f"{added} cards on the wishlist.")}</span>"
                          + (f"<br><span style='color:#ffb347'>{tr("Not found: ")}"
                             f"{', '.join(missing[:12])}</span>" if missing else ""))

    # --- Friend ---
    def do_friend(self):
        stream = self.ctrl.stream
        stream.ensure_page("trade")
        page = self.ctrl.trade_page
        if page.import_dialog() is not None:  # created/updated: continue there
            stream.show_page("trade", back=True)
