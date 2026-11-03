"""Windows in the stream without widgets: search/edit card (CardPanel), statistics
(StatsPanel) with small charts (Chart). Moved from app.py (re-exported there)."""
import collections
import logging
import threading
import time
import traceback

from PySide6 import QtCore, QtGui

import games
from cards import carddb, library
from collection import sessions
from collection.collection import lang_short
from scanner import hybrid
from scanner.common import BASE
from scanner.core import has_packs, pack_total
from system.i18n import tr
from ui import qstate, scanlook
from ui.librarycore import run_async
from ui.scanlook import TIER_COLOR, eur, rarity_text, tier


class CardPanel(QtCore.QObject):
    """"Search / edit card" without a widget: chosen card (price, foil, language, back), search field and
    result list (loaded sets + Scryfall). When editing, the other versions of the same card come first.
    Shown by Qt Quick (qcardsearch.py / CardSearch.qml) – in the stream where the pack list is, under Sessions
    as a page on the right (sessparts.EditPage)."""
    chosen = QtCore.Signal(object, bool, str)   # card, foil, language
    removed = QtCore.Signal()
    closeRequested = QtCore.Signal()
    hovered = QtCore.Signal(object)        # card under the mouse (big preview) or None
    changed = QtCore.Signal()              # header, selection, texts
    results_changed = QtCore.Signal()      # result list or selected row
    _online = QtCore.Signal(int, object, str, bool)   # search number, results, error, append?
    _ready = QtCore.Signal(object, str)               # card after the image download

    def __init__(self, ctrl, parent=None, in_stream=True):
        super().__init__(parent)
        self.ctrl, self.in_stream = ctrl, in_stream
        self.token, self.results, self.sel, self.sel_url, self.editing = 0, [], None, None, None
        self._twins_of, self._twins = None, set()   # edit view: prints with the same image (confusion)
        self.row = -1                      # selected row of the result list
        self.lang, self.lang_token = ctrl.settings["card_lang"], 0
        self.langs, self.langs_shown, self.lang_note = [], False, ""
        self.title = self.name = self.meta = self.price = self.info = self.search = ""
        self.details = self.rules = ""
        self.preview_text = tr("Click a card\nbelow")
        self.ok_text, self.ok_enabled, self.remove_shown = tr("Add"), False, False
        self.back_shown = self.back_on = False
        self.foil, self.foil_enabled = False, False
        self.finish, self.edition = "", ""   # chosen finish / edition (finishes.py) – goes out with "chosen"
        self.finish_set = False              # changed in the window (a question's answer takes it along)
        self._visible, self._rect = False, QtCore.QRect()
        self.timer = QtCore.QTimer(self, singleShot=True, interval=180, timeout=self.search_local)
        self._online.connect(self.on_online)
        self._ready.connect(lambda card, err: self.chosen.emit(card, self.foil, self.lang))

    def _ch(self):
        self.changed.emit()

    # --- visible / position (in the stream: above the pack list) ---
    def isVisible(self):
        return self._visible

    def isHidden(self):
        return not self._visible

    def show(self):
        if not self._visible:
            self._visible = True
            if self.in_stream:
                self.ctrl.overlay.panel_rect = QtCore.QRect(self._rect)
            self._ch()

    def hide(self):
        if self.question is not None:   # closed without an answer (Esc, ✕, another window): skip
            self.answer(None, None)
        if self._visible:
            caller = " < ".join(f"{f.name}:{f.lineno}" for f in reversed(traceback.extract_stack(limit=4)[:-1]))
            logging.getLogger("scan").info("card window closes (%s)", caller)
            self._visible = False
            if self.in_stream:
                self.ctrl.overlay.panel_rect = None
            self.hovered.emit(None)
            self._ch()

    def geometry(self):
        return QtCore.QRect(self._rect)

    def place(self):
        """On the scan page: search and edit in the middle above the bar (search rises from the bar, edit slides in
        from the side – Qt Quick); the tiles stay where they are."""
        view = self.ctrl.stream.view   # size of the scan view (like info/statistics)
        pw, ph = view.width(), view.height()
        bottom = ph - 96                       # above the bar
        top = max(72, bottom - 880)            # search and edit: results need height
        want = 640 if self.editing is not None else 860   # search: more results at a glance (Oliver's review c3)
        w = max(340, min(want, int(pw * 0.48)))
        rect = QtCore.QRect(int((pw - w) / 2), int(top), int(w), int(bottom - top))
        self.ctrl.overlay.panel_rect = rect if self._visible else None
        if rect != self._rect:
            self._rect = rect
            self._ch()

    def hover_card(self, card):
        """Card for the big preview; price and finish as selected. If the image is still missing, the overlay loads it
        (placeholder card until then) – also for results only found online."""
        if card is None or not card.get("img"):
            return None
        foil = self.foil if card is self.sel else card["eur"] is None
        out = dict(card, foil=foil, price=card.get("eur_foil") if foil else card["eur"])
        if card is self.sel and self.finish:
            out["finish"] = self.finish
            if self.edition:
                out["edition"] = self.edition
        return out

    def hover_row(self, row):
        if 0 <= row < len(self.results):
            self.hovered.emit(self.hover_card(self.results[row][0]))

    def front_of(self, card):
        """Front face of a double-faced card (there are entries per face)."""
        sid, _, face = card["id"].rpartition("_")
        if face not in ("", "0"):
            return self.ctrl.overlay.card_by_id.get(f"{sid}_0", card)
        return card

    def toggle_back_row(self, row):
        """⟲ in a row: turn this card's preview to the other face."""
        self.ctrl.overlay.toggle_back(time.monotonic())
        self.back_on = self.ctrl.overlay.show_back
        if self.sel is not None:
            self.select(self.sel, self.sel_url)
        self.hover_row(row)
        self.results_changed.emit()

    # --- Question while scanning: which print, which language (Oliver 2026-10-30: one way – this search) ---
    question = None   # {"kind": "print"|"lang", "done": fn(card or None, language or None, how), "star": {ids}, "rows",
    #                    "text": the name filled in, "cam", "loupe", "note", "entry"} – answered exactly once (answer)

    def open_question(self, kind, done, rows=(), star=(), name="", cam=None, loupe=None, note="", entry=None,
                      lang=None):
        """The scanner asks. print: rows = the candidates (database rows, the most likely first, ★ = matches the
        camera image), chosen with "Take" / Enter / 1–9 – the scanner counts it (no add_manual). lang: entry = the
        counted card, the language keys are the question. Esc / ✕ = skip. Typing searches all prints as usual."""
        self.answer(None, None)
        self.editing = None
        self.question = {"kind": kind, "done": done, "star": set(star), "rows": {}, "text": name, "cam": cam,
                         "loupe": loupe, "note": note, "entry": entry}
        self.remove_shown = False
        self.finish_set = False
        if kind == "print":
            self.lang = lang or self.ctrl.settings["card_lang"]
            self.title, self.ok_text = tr(f"Which version? · {name}"), tr("Take")
            out = []
            for r in rows:
                if "booster" not in r:   # a short row (aiscan.as_row): the full one from the database
                    try:
                        r = carddb.card(str(r["id"])) or r
                    except Exception:  # noqa: BLE001
                        pass
                e = carddb.entry_from_row(r)
                e["img_normal"] = hybrid.image_url(r)
                self.question["rows"][e["id"]] = r
                out.append((e, e["img_normal"] if not (BASE / e["img"]).exists() else None))
            self.search = name
            self.fill(out, False)
            same = sum(1 for e, _u in out if e["id"] in self.question["star"])
            self.info = (tr(f"★ {same} matching the camera image · {len(out)} printings – 1–9, Enter, F = finish, Esc = skip")
                         if same else tr(f"{len(out)} printings – 1–9, Enter, F = finish, Esc = skip"))
        else:
            self.lang = lang or entry.get("lang") or "en"
            self.title, self.ok_text = tr(f"Which language? · {entry['name']}"), tr("Take")
            self.search = self.question["text"] = entry["name"]   # filled in: 1–9 and F work while it stands
            self.fill([(entry, None)], False)
            from cards import finishes
            if self.sel is not None and finishes.current(entry) in [o["key"] for o in finishes.options(self.sel)]:
                self.finish = finishes.current(entry)   # what the counted card is now (F pressed before, …)
                self.foil = bool(entry.get("foil"))
                self.edition = entry.get("edition") or ""
                self.show_price()
            self.finish_set = False
            self.info = tr("Counted – only the language is unclear: pick it (1–9), Enter keeps it, F = finish, Esc = skip")
        self._show()
        self.hover_row(0)   # the suggestion large beside the search right away – to compare without hovering

    cond, edit_orig = None, None   # editing: the condition chosen here, and what the card was (edit_dirty)

    def edit_dirty(self):
        """Editing: something differs from the card in the pack (print, finish, edition, language, condition) – not
        saved until "Replace", closing drops it."""
        o = self.edit_orig
        if self.editing is None or o is None or self.sel is None:
            return False
        return (self.sel.get("id") != o["id"] or (self.finish or "") != (o["finish"] or "") or self.edition != o["edition"]
                or self.lang != o["lang"] or self.cond != o["cond"])

    def answer(self, card, lang):
        """The question's answer (card or None = skip) – exactly once; the window closes separately. how: the finish
        and edition chosen in the window ({} = untouched: the card keeps what it has)."""
        q, self.question = self.question, None
        if q is not None:
            how = {"finish": self.finish or None, "edition": self.edition} if card is not None and self.finish_set else {}
            try:
                q["done"](card, lang, how)
            except Exception:  # noqa: BLE001 – the window must still close
                logging.getLogger("scan").exception("Answering the scanner's question")

    def question_row(self, card):
        """The database row of a candidate (the scanner counts from it), else one made from the chosen card."""
        q = self.question or {}
        return q.get("rows", {}).get(card.get("id")) or {"_entry": card, "set_code": str(card["set"]).lower()}

    # --- Opening ---
    def open_add(self):
        self.answer(None, None)
        self.editing = None
        self.lang = self.ctrl.settings["card_lang"]
        self.title, self.ok_text, self.remove_shown = tr("Search card"), tr("Add"), False
        self.search = ""
        self.fill([], False)
        self.select(None, None)
        self.info = tr("Type a name, click a card, “Add”.")
        self._show()

    def open_edit(self, entry, pack_label=""):
        """entry = card from the pack. Below: other versions of this card."""
        self.answer(None, None)
        self.editing = entry
        self.lang = entry.get("lang") or "en"
        self.title, self.ok_text, self.remove_shown = tr(f"Edit card{pack_label}"), tr("Replace"), True
        self.search = entry["name"]
        others = [c for c in self.ctrl.cards if c["name"] == entry["name"]]
        others.sort(key=lambda c: (c["id"] != entry["id"], self.confusion(c)))
        if not any(c["id"] == entry["id"] for c in others):
            others.insert(0, {k: v for k, v in entry.items() if k not in ("foil", "price", "added")})
        self.fill([(c, None) for c in others], False, select_first=False)
        self.select_row_for(entry["id"])
        from cards import conditions, finishes
        self.foil = bool(entry["foil"])
        self.finish, self.edition = finishes.current(entry), entry.get("edition") or ""
        self.cond = dict(conditions.fields(entry)) or {"cond": conditions.of(entry)}   # saved only with "Replace"
        self.edit_orig = {"id": entry["id"], "finish": self.finish, "edition": self.edition, "lang": self.lang,
                          "cond": dict(self.cond)}
        self.show_price()
        self.info = (tr(f"{len(others)} versions in the loaded sets · searching Scryfall for more …")
                     if self.web_search() else
                     tr(f"{len(others)} versions in the loaded sets · searching all sets for more …"))
        self.search_online(f'!"{entry["name"]}"', append=True)
        self._show()

    def _show(self):
        if self.in_stream:
            self.place()  # showing is handled by the stream window
        self._ch()

    # --- Search ---
    def set_search(self, text):
        """Search field changed (typing): wait briefly, then search the loaded sets."""
        if text != self.search:
            self.search = text
            self.timer.start()
            self._ch()

    def search_local(self):
        q = self.search.strip().lower()
        if not self.web_search() and len(q) >= 2 and carddb.exists():
            self.search_online(self.search.strip())
            return
        self.token += 1
        if len(q) < 2:
            self.fill([], False)
            self.info = tr("Type at least 2 letters.")
            self._ch()
            return
        words = q.split()
        res, seen = [], set()
        from ui.searchbox import split_print_query
        code, num, rest = split_print_query(q)  # "fic 0019", "fic#19" …
        alt = set(carddb.names_by_printed(q)) if carddb.exists() else set()  # name in another language
        for c in self.ctrl.cards:
            if code and num:
                hit = c["set"].lower() == code and carddb.norm_number(c["number"], "") == carddb.norm_number(num, "")
            else:
                hit = all(w in c["name"].lower() for w in words) or c["name"] in alt
            if hit:
                c = self.front_of(c)  # back face found -> show the front (⟲ flips)
                if c["id"] not in seen:
                    seen.add(c["id"])
                    res.append(c)
        res.sort(key=lambda c: (not c["name"].lower().startswith(q), not c["booster"], c["name"], c["set"]))
        self.fill([(c, None) for c in res[:60]], False)
        self.info = ((tr("1 match in the loaded sets.") if len(res) == 1 else tr(f"{len(res)} matches in the loaded sets.")) if res else
                     tr("Not in the loaded sets – Enter searches Scryfall.") if self.web_search() else
                     tr("Not in the loaded sets – Enter searches all sets."))
        self._ch()

    def confusion(self, c):
        """Sort key of the other versions while editing: what the scanner most likely mixed up first – the same image
        or the same collector number in another set (promo, prerelease "97s", The List "AKH-97"), then the most likely print
        (carddb.print_likeliness: booster before promo, matching finish, cheaper, newer)."""
        e = self.editing or {}

        def core(number):   # "97s" -> 97, The List "AKH-97" -> 97 (the set code in front isn't part of it)
            return "".join(ch for ch in str(number or "").rsplit("-", 1)[-1] if ch.isdigit())
        num = core(e.get("number"))
        if self._twins_of != e.get("id"):   # same image (the scanner's art group: Pokémon/Lorcana reprints)
            self._twins_of, self._twins = e.get("id"), set()
            try:
                from scanner import aiscan
                group, _ = aiscan.uncertain_prints(e, getattr(self.ctrl.recognizer, "fp_index", None))
                self._twins = {str(r["id"]) for r in group}
            except Exception:  # noqa: BLE001 – without a card database / index: by number only
                pass
        twin = (str(c.get("id") or "").rsplit("_", 1)[0] in self._twins
                or bool(num) and core(c.get("number")) == num)
        return not twin, carddb.print_likeliness(c, foil=bool(e.get("foil")))

    @staticmethod
    def web_search():
        """Search across all sets: the card database on disk (every game, all languages, set names and
        numbers) – only Magic without a card database asks Scryfall (online)."""
        return games.current().online_details and not carddb.exists()

    @staticmethod
    def search_db(q, limit=60):
        """All sets from the card database -> [(entry, image URL)]; !"Name" = exactly this name."""
        exact = q.startswith('!"') and q.endswith('"')
        text = q[2:-1] if exact else q
        if not carddb.exists():
            raise RuntimeError(tr("Card database missing"))
        code, num, filters = None, None, {}
        if not exact:
            from ui.searchbox import apply_criterion, parse_query, split_print_query, split_year
            crit, text = parse_query(text)   # a:"rebecca guay", year>=2020 … like in the library
            for c in crit:
                apply_criterion(filters, *c)
            year, text = split_year(text)    # "glurak 1999": prints released in 1999
            if year:
                filters.setdefault("ranges", {})["year"] = (year, year)
            code, num, rest = split_print_query(text)
            words = text.split()
            if not (code or num) and len(words) >= 2:   # "Pikachu ex2": name + set code
                codes = carddb.set_codes()
                hit = next((w for w in (words[-1], words[0]) if w.lower() in codes), None)
                if hit:
                    code, rest = hit.lower(), " ".join(w for w in words if w is not hit)
        if code or num:
            rows = carddb.search(rest, limit=limit * 3, sort="set" if code else "new", **filters,
                                 **({"set_code": code} if code else {}), **({"number": num} if num else {}))
        else:   # free text also finds the artist ("guay", "pikachu arita") – ranked below hits in the name
            rows = carddb.search(text, limit=limit * 3, **filters)
        if exact:
            rows = [r for r in rows if r["name"].lower() == text.lower()]
        words = rest if (code or num) else text
        g = games.current()
        url = g.image_url   # Pokémon: images from TCGdex (the database has no address)
        out = [(carddb.name_rank(r, words), carddb.entry_from_row(r),
                hybrid.image_url(r) or (url(r["set_code"], r["number"]) if url else None)) for r in rows]
        # hits in the name always first ("Energy Switch 75": not Klink through its rules text – the number only
        # narrows down), within them prints with an image first (special prints without one at the end)
        out.sort(key=lambda reu: (reu[0], reu[2] is None))
        out = [(e, u) for _r, e, u in out]
        return out[:limit]

    def search_online(self, q, append=False):
        if len(q) < 2:
            return
        self.token += 1
        token = self.token
        web = self.web_search()
        if not append:
            self.info = tr(f"Searching Scryfall for “{q}” …") if web else tr(f"Searching all sets for “{q}” …")
            self._ch()

        def work():
            try:
                res = library.search_online(q, limit=60) if web else self.search_db(q)
                self._online.emit(token, res, "", append)
            except Exception as e:
                self._online.emit(token, [], str(e), append)
        threading.Thread(target=work, daemon=True).start()

    def on_online(self, token, res, err, append):
        if token != self.token:
            return
        web = self.web_search()
        if append:
            have = {c["id"] for c, _ in self.results}
            new = [(c, u) for c, u in res if c["id"] not in have]
            self.results += new
            if self.editing is not None:   # most likely mix-ups first: the card itself, then twins, then the rest
                chosen = self.results[self.row][0]["id"] if 0 <= self.row < len(self.results) else None
                first = [cu for cu in self.results if cu[0]["id"] == self.editing["id"]]
                self.results = first + sorted((cu for cu in self.results if cu[0]["id"] != self.editing["id"]),
                                              key=lambda cu: self.confusion(cu[0]))
                self.row = next((i for i, (c, _) in enumerate(self.results) if c["id"] == chosen), self.row)
            if web:
                self.info = (tr(f"{len(self.results)} versions · {len(new)} of them only on Scryfall (online).")
                             if not err else tr(f"Scryfall unreachable: {err}"))
            else:
                self.info = (tr(f"{len(self.results)} versions · {len(new)} of them from sets not downloaded.")
                             if not err else err)
            self.results_changed.emit()
            self._ch()
            return
        self.fill(res, True)
        if web:
            self.info = (f"Scryfall: {err}" if err else (tr("1 match on Scryfall.") if len(res) == 1 else tr(f"{len(res)} matches on Scryfall.")) if res else
                         tr("Nothing found on Scryfall either."))
        else:
            self.info = (err if err else (tr("1 match in all sets.") if len(res) == 1 else tr(f"{len(res)} matches in all sets.")) if res else
                         tr("Nothing found in all sets either."))
        self._ch()

    def enter(self):
        """Enter: take the selected card; if nothing is found locally, search on Scryfall."""
        if self.timer.isActive():
            self.timer.stop()
            self.search_local()
        if self.sel is not None and self.row >= 0:
            self.confirm()
        else:
            self.search_online(self.search.strip())

    # --- List ---
    def fill(self, results, online, select_first=True):
        self.results = list(results)
        self.row = -1
        if self.results and select_first:
            self.set_row(0)
        elif not self.results and self.editing is None:
            self.select(None, None)
        self.results_changed.emit()

    @staticmethod
    def price_text(card):
        if card["eur"] is not None:
            return eur(card["eur"])
        return f"{eur(card['eur_foil'])} (Foil)" if card.get("eur_foil") is not None else tr("no price")

    def row_text(self, card, online):
        """Two lines of a result row: name, below it what tells the prints apart – "BASE3 · Fossil · 1999 · #43/62 ·
        Uncommon · 2,62 €" (a long set name only in the info field above; the line never wraps, it is cut at the end).
        online (image not on disk yet) isn't shown: it means nothing to the user."""
        r = self._row_of(card)
        name = (r.get("set_name") or "").strip()
        star = "★ " if self.question is not None and card.get("id") in self.question["star"] else ""
        return star + card["name"], " · ".join(x for x in (
            card["set"], name if 0 < len(name) <= 22 else "", (r.get("released") or "")[:4], self.number_text(card),
            rarity_text(card["rarity"]), self.price_text(card)) if x)

    @staticmethod
    def number_text(card):
        """"#43/62" as printed – the set size only where the data has it reliably (carddb.printed_total)."""
        try:
            total = carddb.printed_total(card["set"]) if carddb.exists() else None
        except Exception:  # noqa: BLE001
            total = None
        num = str(card["number"])
        return f"#{num}/{total}" if total and num.isdigit() and int(num) <= total else f"#{num}"

    _rows = {}

    def _row_of(self, card):
        """The card's database row (set name, year …) – remembered, the list asks for every row."""
        key = str(card.get("id") or "").rsplit("_", 1)[0]
        if key not in self._rows:
            try:
                self._rows[key] = (carddb.card(key) if carddb.exists() else None) or {}
            except Exception:  # noqa: BLE001
                self._rows[key] = {}
            if len(self._rows) > 400:
                self._rows.clear()
        return self._rows[key]

    def select_row_for(self, card_id):
        for row, (c, _) in enumerate(self.results):
            if c["id"] == card_id:
                self.set_row(row)
                return

    def set_row(self, row):
        if 0 <= row < len(self.results) and row != self.row:
            self.row = row
            self.select(*self.results[row])
            self.results_changed.emit()

    # --- Selection at the top ---
    def select(self, card, url):
        self.sel, self.sel_url = card, url
        self.ok_enabled = card is not None
        if card is None:
            self.back_shown = self.langs_shown = False
            self.preview_text = tr("Click a card\nbelow")
            self.name = self.meta = self.price = self.details = self.rules = ""
            self.foil_enabled = False
            self._ch()
            return
        back = self.ctrl.overlay.other_face(card)
        self.back_shown = back is not None
        self.back_on = self.ctrl.overlay.show_back
        self.preview_text = "" if url is None else tr("loading …")
        self.name = card["name"]
        self.meta, self.details, self.rules = self.card_details(card)
        from cards import finishes
        opts = finishes.options(card)
        self.foil_enabled = len(opts) > 1
        keys = [o["key"] for o in opts]
        if self.editing is None or self.finish not in keys:   # new card: base finish; editing: keep it
            self.finish = keys[0]
        if self.edition and not any(x["key"] == self.edition for x in finishes.editions(card)):
            self.edition = ""
        self.foil = bool(next(o for o in opts if o["key"] == self.finish)["foil"])
        self.show_price()
        self.request_langs(card)
        self._ch()

    def set_foil(self, on):
        if self.foil_enabled and bool(on) != self.foil:
            self.foil, self.finish_set = bool(on), True
            self.show_price()
            self._ch()

    def set_finish(self, key):
        """Choose a finish (buttons "Normal · Holo · Reverse Holo" or "Non-Foil · Foil · Etched")."""
        from cards import finishes
        if self.sel is None:
            return
        o = next((o for o in finishes.options(self.sel) if o["key"] == key), None)
        if o is not None:
            self.finish, self.foil, self.finish_set = key, bool(o["foil"]), True
            self.show_price()
            self._ch()

    def set_edition(self, key):
        self.edition, self.finish_set = key or "", True
        self._ch()

    def next_finish(self):
        """F in a question: the shown card's next finish (Normal → Holo → Reverse Holo …), taken with the answer.
        -> False if there is nothing to switch."""
        from cards import finishes
        if self.sel is None:
            return False
        keys = [o["key"] for o in finishes.options(self.sel)]
        if len(keys) < 2:
            return False
        self.set_finish(keys[(keys.index(self.finish) + 1) % len(keys)] if self.finish in keys else keys[0])
        self.hovered.emit(self.hover_card(self.sel))   # the big preview shows it
        return True

    # --- Language ---
    def request_langs(self, card):
        self.langs_shown, self.langs, self.lang_note = True, [], tr("Looking up languages …")
        self.lang_token += 1
        token = self.lang_token
        run_async(self, lambda: library.print_languages(card["set"], card["number"]),
                  lambda res, err: self.on_langs(token, res))

    def on_langs(self, token, res):
        if token != self.lang_token:
            return
        if res and not any(c == self.lang for c, *_ in res):
            self.info = tr(f"This printing doesn't exist in {lang_short(self.lang)} – English chosen.")
            self.lang = "en"
        self.langs = list(res or [])
        # none known: Magic asks Scryfall – then it was offline; the other games only know their card data
        self.lang_note = "" if res else (tr("Languages unknown (offline)") if games.current().online_details
                                         else tr("No other languages known for this print"))
        self._ch()

    def lang_picked(self, code):
        self.lang = code
        if self.question is not None and self.question["kind"] == "lang":   # that was the question: done
            self.answer(self.sel, code)
            self.closeRequested.emit()
            return
        if self.sel is not None:
            self.select(self.sel, self.sel_url)

    def toggle_back(self):
        self.ctrl.overlay.toggle_back(time.monotonic())
        self.select(self.sel, self.sel_url)
        if self.sel is not None:
            self.hovered.emit(self.hover_card(self.sel))  # the big preview turns along with it

    @staticmethod
    def card_details(card):
        """What tells prints apart while searching (no hovering there) -> (set line, details, rules text):
        "Diamond & Pearl Promos (DP1 #112) · 2007", "Artist: … · Rare · Trainer – Supporter", the first rules text
        (cut with "…"). Fields without a value are left out – a card from Scryfall (online) only has set and number."""
        where = f"{card['set']} {CardPanel.number_text(card)}"
        try:
            r = carddb.card(str(card.get("id") or "").rsplit("_", 1)[0]) if carddb.exists() else None
        except Exception:  # noqa: BLE001 – no database: set and number as before
            r = None
        r = r or {}
        year = (r.get("released") or "")[:4]
        meta = " · ".join(x for x in (f"{r['set_name']} ({where})" if r.get("set_name") else where, year) if x)
        artist = (r.get("artist") or "").strip()
        details = " · ".join(x for x in (tr(f"Artist: {artist}") if artist else "", rarity_text(card.get("rarity")),
                                         (r.get("type_line") or "").strip()) if x)
        text = " ".join((r.get("oracle_text") or "").split())
        rules = text if len(text) <= 160 else text[:157].rsplit(" ", 1)[0] + " …"
        return meta, details, rules

    def show_price(self):
        c = self.sel
        if c is None:
            return
        from cards import finishes
        opts = finishes.options(c)
        n = tr("–") if c["eur"] is None else eur(c["eur"])
        f = "–" if c.get("eur_foil") is None else eur(c["eur_foil"])
        active = c.get("eur_foil") if self.foil else c["eur"]
        big = tr("no price") if active is None else eur(active)
        base = next((o["label"] for o in opts if not o["foil"]), None)
        shiny = [o["label"] for o in opts if o["foil"]]   # share the foil price (Holo, Reverse Holo, pattern …)
        parts = ([f"{tr(base)} {n}"] if base else []) + ([f"{' / '.join(tr(x) for x in shiny[:2])} {f}"] if shiny else [])
        self.price = (f"<span style='font-size:26px; font-weight:700'>{big}</span>"
                      f"<br><span style='color:#8a91a8'>{' · '.join(parts)}</span>")

    def confirm(self):
        card = self.sel
        if card is None:
            return
        card = {k: v for k, v in card.items() if k != "thumb"}
        if self.sel_url is None or (BASE / card["img"]).exists():
            self.chosen.emit(card, self.foil, self.lang)
            return
        self.info = tr("Loading card image …")
        self._ch()
        url = self.sel_url

        def work():
            try:
                self._ready.emit(library.fetch_image(card, url), "")
            except Exception as e:
                self._ready.emit(card, str(e))
        threading.Thread(target=work, daemon=True).start()


class Chart:
    """Small chart in overlay style (data only; drawn by ChartView.qml via qcharts).
    kind: "bars" (values, labels, highlight, lines), "pairs" (a, b, labels), "line" (values, labels, hline),
          "donut" (parts: [(label, value, color)]), "tiles" (items: [(label, text, color)]), "list" (rows)."""

    def __init__(self, kind, title="", height=200):
        self.kind, self.title, self.data, self.h = kind, title, {}, height

    def set(self, **data):
        self.data = data

    def minimumHeight(self):
        return self.h


class StatsPanel(qstate.Panel):
    """Extended statistics in the stream: tabs "This session" and "Total", with charts (data only; shown as a
    form by qscan)."""
    RARITY_COLORS = [("Common", "common", QtGui.QColor("#8a91a8")), ("Uncommon", "uncommon", QtGui.QColor("#b8c4d6")),
                     ("Rare", "rare", QtGui.QColor("#e7c35a")), ("Mythic", "mythic", QtGui.QColor("#ff8a3d")),
                     ("Sonstige", None, QtGui.QColor("#62f2ff"))]

    def __init__(self, ctrl, parent):
        super().__init__(parent)
        self.ctrl = ctrl
        self.tab = 0
        # This session
        self.s_tiles = Chart("tiles", height=86)
        self.s_packs = Chart("bars", tr("Value per pack"), 210)
        self.s_curve = Chart("line", tr("Value over all cards"), 210)
        self.s_rarity = Chart("donut", tr("Rarities"), 190)
        self.s_top = Chart("list", tr("Top 5 cards"), 190)
        # Total
        self.g_tiles = Chart("tiles", height=86)
        self.g_sessions = Chart("pairs", tr("Value and spent per log"), 220)
        self.g_avg = Chart("line", tr("Ø value per pack by log"), 190)
        self.g_sets = Chart("bars", tr("Card value by set"), 200)
        self.g_top = Chart("list", tr("Top 10 of all time"), 320)
        # pack figures only when opening boosters: this session is one · any saved one is (sessions.counts_for_packs)
        self.s_has_packs, self.g_has_packs = False, False

    def layout(self):
        """Layout of the selected tab: charts or (chart, chart) side by side – the pack charts only with packs."""
        if self.tab == 1:
            return [self.g_tiles, self.g_sessions, (self.g_avg, self.g_sets) if self.g_has_packs else self.g_sets,
                    self.g_top]
        return [self.s_tiles] + ([self.s_packs] if self.s_has_packs else []) + [self.s_curve, (self.s_rarity, self.s_top)]

    def place(self):
        pw, ph = self.parent().width(), self.parent().height()
        # keep distance to the bar at the top: otherwise closing (✕ at the top) opens the navigation
        top = 84   # room at the bottom for the scan window's bar
        w, h = min(1040, pw - 40), max(300, ph - top - 96)
        self.setGeometry((pw - w) // 2, top, w, h)

    def open(self):
        self.refresh()
        self.place()
        self.show()

    @staticmethod
    def _profit_color(v):
        return QtGui.QColor("#6dff9c") if v >= 0 else QtGui.QColor("#ff6b6b")

    def refresh(self):
        self.ctrl.save_session()
        cur = self.ctrl.session.to_dict()
        st, info = cur["stats"], cur["info"]
        # the session's kind straight from the session (the snapshot's "packs_shown" is the same, only older)
        self.s_has_packs = has_packs(info)
        packs = [pk for pk in cur["packs"] if pk["cards"]]
        cards = [e for pk in packs for e in pk["cards"]]
        profit = st["profit"]
        self.s_tiles.set(items=[
            (tr("Value"), eur(st["total"]), scanlook.INK), (tr("Spent"), eur(st["paid"]) if st["paid"] else tr("–"), scanlook.MUTED),
            (tr("Balance"), tr("–") if profit is None else ("+" if profit >= 0 else "−") + eur(abs(profit)),
             scanlook.MUTED if profit is None else self._profit_color(profit))]
            + ([(tr("Ø per pack"), eur(st["avg_pack"]), scanlook.CYAN), (tr("Packs"), str(st["packs"]), scanlook.INK)]
               if self.s_has_packs else [])
            + [(tr("Cards"), str(st["cards"]), scanlook.INK)])
        totals = [pack_total(pk) for pk in packs] if self.s_has_packs else []   # scanning cards: no pack by pack
        lines = []
        if totals:
            lines.append((st["avg_pack"], scanlook.CYAN, f"Ø {eur(st['avg_pack'])}"))
        n_paid = int(info.get("packs_planned") or 0) or len(packs)
        if st["paid"] and n_paid:
            lines.append((st["paid"] / n_paid, QtGui.QColor("#ff6b6b"), tr(f"Cost/pack {eur(st['paid'] / n_paid)}")))
        best = max(range(len(totals)), key=lambda i: totals[i]) if totals else None
        self.s_packs.set(values=totals, labels=[f"#{i + 1}" for i in range(len(totals))], highlight=best, lines=lines)
        cum, run = [], 0.0
        for e in cards:
            run += e["price"] or 0
            cum.append(round(run, 2))
        self.s_curve.set(values=cum, hline=st["paid"] or None,
                         labels=[tr("first card"), tr(f"Card {len(cum)}")] if cum else None)
        counts = collections.Counter(e["rarity"] for e in cards)
        parts = []
        for label, key, col in self.RARITY_COLORS:
            n = counts.get(key, 0) if key else sum(v for r, v in counts.items()
                                                   if r not in ("common", "uncommon", "rare", "mythic"))
            parts.append((label, n, col))
        self.s_rarity.set(parts=parts)
        top = sorted((e for e in cards if e["price"] is not None), key=lambda e: -e["price"])[:5]
        hit = self.ctrl.settings["hit"]
        self.s_top.set(rows=[(e["name"] + (tr(" · foil") if e["foil"] else ""), f"{e['set']} #{e['number']}",
                              eur(e["price"]), TIER_COLOR[tier(e["price"], hit)]) for e in top])

        # Total across all saved sessions (oldest first)
        all_s = [s for s in sessions.load_all() if s["stats"]["cards"] and sessions.counts_in_stats(s)]
        all_s.sort(key=lambda s: s["started"])
        pk_s = [s for s in all_s if sessions.counts_for_packs(s)]   # pack figures: only opening boosters
        self.g_has_packs = bool(pk_s)
        tot = sum(s["stats"]["total"] for s in all_s)
        n_packs = sum(s["stats"]["packs"] for s in pk_s)
        pk_tot = sum(s["stats"]["total"] for s in pk_s)
        paid_s = [s for s in all_s if s["stats"]["paid"]]
        paid = sum(s["stats"]["paid"] for s in paid_s)
        g_profit = sum(s["stats"]["total"] for s in paid_s) - paid if paid_s else None
        g_packs = [(tr("Packs"), str(n_packs), scanlook.INK)] if self.g_has_packs else []
        g_per_pack = [(tr("Ø per pack"), eur(pk_tot / n_packs) if n_packs else tr("–"), scanlook.CYAN)] if self.g_has_packs else []
        self.g_tiles.set(items=[(tr("Logs"), str(len(all_s)), scanlook.INK)] + g_packs + [
            ("Gesamtwert", eur(tot), scanlook.INK),
            (tr("Spent"), eur(paid) if paid else tr("–"), scanlook.MUTED),
            (tr("Balance"), tr("–") if g_profit is None else ("+" if g_profit >= 0 else "−") + eur(abs(g_profit)),
             scanlook.MUTED if g_profit is None else self._profit_color(g_profit))] + g_per_pack)
        labels = [time.strftime("%d.%m.", time.localtime(s["started"])) for s in all_s]
        self.g_sessions.set(a=[s["stats"]["total"] for s in all_s], b=[s["stats"]["paid"] for s in all_s],
                            labels=labels)
        pk_labels = [time.strftime("%d.%m.", time.localtime(s["started"])) for s in pk_s]
        self.g_avg.set(values=[s["stats"]["avg_pack"] for s in pk_s],
                       labels=[pk_labels[0], pk_labels[-1]] if pk_labels else None)
        by_set = collections.defaultdict(float)
        every = []
        for s in all_s:
            for pk in s["packs"]:
                for e in pk["cards"]:
                    by_set[e["set"]] += e["price"] or 0
                    every.append((e, s))
        sets_sorted = sorted(by_set.items(), key=lambda kv: -kv[1])[:10]
        self.g_sets.set(values=[round(v, 2) for _, v in sets_sorted], labels=[k for k, _ in sets_sorted],
                        highlight=0 if sets_sorted else None)
        best10 = sorted((t for t in every if t[0]["price"] is not None), key=lambda t: -t[0]["price"])[:10]
        self.g_top.set(rows=[(e["name"] + (tr(" · foil") if e["foil"] else ""),
                              f"{e['set']} #{e['number']} · {time.strftime('%d.%m.%Y', time.localtime(s['started']))}",
                              eur(e["price"]), TIER_COLOR[tier(e["price"], hit)]) for e, s in best10])
        qstate._changed()
