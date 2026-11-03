"""The scanner's questions (which print, which language) are asked in the card search – one way, no window of its own
(Oliver 2026-10-30): the candidates as the result list, ★ first and selected, answered exactly once; Esc / closing =
skip; the choice is counted by the scanner (never add_manual); a busy search makes the question wait (key K).

    python -m unittest tests/test_ask_in_search.py
"""
import types
import unittest
from unittest import mock

from scanner.scan_ctl import ScanControl
from ui import panels
from ui.panels import CardPanel


def row(cid, set_code, number, name="Nubian Guard"):
    return {"id": cid, "name": name, "set_code": set_code, "number": number, "rarity": "common", "booster": 1,
            "finishes": "nonfoil", "eur": 0.1, "eur_foil": None, "img_small": None, "faces": None, "lang": "en"}


class Panel(unittest.TestCase):
    def setUp(self):
        ctrl = types.SimpleNamespace(settings={"card_lang": "en"},
                                     overlay=types.SimpleNamespace(panel_rect=None, other_face=lambda c: None,
                                                                   show_back=False))
        self.p = CardPanel(ctrl, in_stream=False)
        for name, fn in (("select", lambda self, card, url: setattr(self, "sel", card)),
                         ("hover_row", lambda self, r: None), ("_row_of", lambda self, card: {})):
            patch = mock.patch.object(CardPanel, name, fn)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(panels.hybrid, "image_url", lambda r: f"https://img/{r['id']}.jpg")
        patch.start()
        self.addCleanup(patch.stop)
        self.answers = []

    def ask(self):
        rows = [row("m19-10", "m19", "10"), row("akh-10", "akh", "10"), row("plst-AKH-10", "plst", "AKH-10")]
        self.p.open_question("print", lambda card, lang, how=None: self.answers.append((card and card["id"], lang)), rows=rows,
                             star={"m19-10_0", "akh-10_0"}, name="Nubian Guard")

    def test_candidates_star_first_selected(self):
        self.ask()
        self.assertEqual([e["id"] for e, _u in self.p.results], ["m19-10_0", "akh-10_0", "plst-AKH-10_0"])
        self.assertEqual(self.p.sel["id"], "m19-10_0")
        self.assertTrue(self.p.row_text(self.p.results[0][0], False)[0].startswith("★ "))
        self.assertFalse(self.p.row_text(self.p.results[2][0], False)[0].startswith("★"))
        self.assertIn("★ 2 matching the camera image · 3 printings", self.p.info)
        self.assertEqual(self.p.question_row(self.p.results[1][0])["set_code"], "akh")   # the database row

    def test_answered_once_and_closing_skips(self):
        self.ask()
        self.p.answer(self.p.results[1][0], "en")
        self.p.answer(None, None)
        self.assertEqual(self.answers, [("akh-10_0", "en")])
        self.ask()
        self.p._visible = True
        self.p.hide()   # Esc / ✕: skip
        self.assertEqual(self.answers[-1], (None, None))
        self.assertIsNone(self.p.question)

    def test_another_window_skips_the_question(self):
        self.ask()
        with mock.patch.object(CardPanel, "fill"), mock.patch.object(CardPanel, "_show"):
            self.p.open_add()
        self.assertEqual(self.answers, [(None, None)])

    def test_language_keys_answer(self):
        entry = {"id": "m19-10_0", "name": "Nubian Guard", "set": "M19", "number": "10", "lang": "en", "eur": 0.1, "eur_foil": None}
        self.p.open_question("lang", lambda card, lang, how=None: self.answers.append((card and card["id"], lang)), entry=entry)
        closed = []
        self.p.closeRequested.connect(lambda: closed.append(1))
        self.p.lang_picked("de")
        self.assertEqual((self.answers, closed), ([("m19-10_0", "de")], [1]))


class Controller(unittest.TestCase):
    """scan_ctl: the question opens right away; a busy search makes it wait (status line, key K)."""

    def ctrl(self, busy=False):
        opened = []
        panel = types.SimpleNamespace(hidden=not busy, question=None)
        panel.isHidden = lambda: panel.hidden

        def open_question(kind, done, **kw):
            panel.question = {"kind": kind, "done": done, "entry": kw.get("entry") or {}}
            panel.hidden = False
            opened.append((kind, kw.get("name")))
        panel.open_question = open_question
        panel.question_row = lambda card: {"_entry": card, "set_code": card["set"].lower()}
        stream = types.SimpleNamespace(card_panel=panel, edit_index=None, edit_pack=None, opened=0,
                                       bring_up=lambda: None, only=lambda w: None, flip_in_card_panel=lambda: None)
        stream.open_add = lambda: setattr(stream, "opened", stream.opened + 1)
        resolved = []
        rec = types.SimpleNamespace(pending={"cands": [], "img": None, "r": {"name": "Nubian Guard"}},
                                    lang_ask=None, current=None, resolve=resolved.append, unknown_offer=None)
        c = types.SimpleNamespace(recognizer=rec, stream=stream, question_wait=None, search_offer=None)
        for name in ("question_check", "open_question", "_open_question", "_question_window", "add_card",
                     "open_offered_search"):
            setattr(c, name, getattr(ScanControl, name).__get__(c))
        info = {"rows": [], "star": set(), "name": "Nubian Guard", "cam": "", "loupe": "", "note": ""}
        patch = mock.patch("scanner.scan_ctl.scanui.print_question", lambda p: info)
        patch.start()
        self.addCleanup(patch.stop)
        return c, opened, resolved

    def test_opens_right_away_and_counts_through_the_scanner(self):
        c, opened, resolved = self.ctrl()
        c.question_check()
        self.assertEqual(opened, [("print", "Nubian Guard")])
        c.stream.card_panel.question["done"]({"id": "akh-10_0", "set": "AKH"}, "en", {})
        self.assertEqual(resolved, [{"_entry": {"id": "akh-10_0", "set": "AKH"}, "set_code": "akh"}])
        self.assertEqual(c.stream.opened, 0)   # never the plain "add" path (no add_manual, no double count)

    def test_busy_search_waits_then_k_opens_it(self):
        c, opened, _resolved = self.ctrl(busy=True)
        c.question_check()
        self.assertEqual((opened, c.question_wait), ([], "print"))
        c.stream.card_panel.hidden = True
        c.add_card()   # key K
        self.assertEqual(opened, [("print", "Nubian Guard")])
        self.assertIsNone(c.question_wait)


if __name__ == "__main__":
    unittest.main()


class OneLanguagePrint(unittest.TestCase):
    """A print that exists in one language only (Mystery Booster 2: English) – the language question doesn't come."""

    def test_only_with_a_choice(self):
        from scanner import scan_ctl
        with mock.patch.object(scan_ctl.carddb, "exists", lambda: True):
            with mock.patch.object(scan_ctl.carddb, "languages", lambda s, n: [("en", "English", "x", "Card")]):
                self.assertFalse(scan_ctl.print_has_languages({"set": "MB2", "number": "1"}))
            with mock.patch.object(scan_ctl.carddb, "languages", lambda s, n: [("en",), ("de",)]):
                self.assertTrue(scan_ctl.print_has_languages({"set": "FDN", "number": "1"}))
            with mock.patch.object(scan_ctl.carddb, "languages", lambda s, n: []):
                self.assertTrue(scan_ctl.print_has_languages({"set": "NEW", "number": "1"}))   # unknown: ask


class FirstEditionHint(unittest.TestCase):
    """A print that exists as a 1st Edition (Pokémon WotC sets): the search says where the stamp is."""

    def hint(self, edition, editions, game="pokemon"):
        from ui import qcardsearch
        p = types.SimpleNamespace(sel={"id": "base1-43_0"}, edition=edition)
        b = types.SimpleNamespace(p=p)
        with mock.patch("cards.finishes.editions", lambda card: editions), \
                mock.patch("games.current", lambda: types.SimpleNamespace(key=game)):
            return qcardsearch.CardSearchBackend.editionHint.fget(b)

    def test_only_when_it_exists_and_isnt_set(self):
        first = [{"key": "1st", "label": "1st Edition", "short": "1st"}]
        self.assertIn("1st Edition?", self.hint("", first))
        self.assertEqual(self.hint("1st", first), "")         # already set
        self.assertEqual(self.hint("", []), "")               # no 1st Edition of this print
        self.assertEqual(self.hint("", first, "mtg"), "")     # Pokémon only


class NeverOnlyTheText(unittest.TestCase):
    """Oliver 2026-10-30 (Haspiror): opening the question failed on a short candidate row (aiscan.as_row has no
    "booster") – the status line said "which version?" with no window and no [K]. Now: short rows work, and a failure
    leaves the [K] note."""

    def test_short_rows_open(self):
        ctrl = types.SimpleNamespace(settings={"card_lang": "en"},
                                     overlay=types.SimpleNamespace(panel_rect=None, other_face=lambda c: None,
                                                                   show_back=False))
        p = CardPanel(ctrl, in_stream=False)
        short = {"id": "dp1-73", "set_code": "dp1", "number": "73", "name": "Buneary", "set_name": "", "rarity": "",
                 "img_normal": None, "faces": None, "_entry": {}}
        with mock.patch.object(CardPanel, "select", lambda self, card, url: setattr(self, "sel", card)), \
                mock.patch.object(CardPanel, "hover_row", lambda self, r: None), \
                mock.patch.object(panels.hybrid, "image_url", lambda r: None), \
                mock.patch.object(panels.carddb, "card", lambda cid: None):
            p.open_question("print", lambda card, lang, how=None: None, rows=[short], star={"dp1-73_0"}, name="Buneary")
        self.assertEqual([e["id"] for e, _u in p.results], ["dp1-73_0"])

    def test_failure_leaves_the_k_note(self):
        from ui import qscan
        panel = types.SimpleNamespace(hidden=True, question=None)
        panel.isHidden = lambda: panel.hidden

        def boom(*a, **k):
            panel.question = {"kind": "print"}
            raise KeyError("booster")
        panel.open_question = boom
        stream = types.SimpleNamespace(card_panel=panel, bring_up=lambda: None, only=lambda w: None,
                                       edit_index=None, edit_pack=None, flip_in_card_panel=lambda: None)
        rec = types.SimpleNamespace(pending={"cands": []}, lang_ask=None, current=None)
        c = types.SimpleNamespace(recognizer=rec, stream=stream, question_wait=None, search_offer=None)
        for name in ("question_check", "open_question", "_open_question", "_question_window"):
            setattr(c, name, getattr(ScanControl, name).__get__(c))
        info = {"rows": [], "star": set(), "name": "Buneary", "cam": "", "loupe": "", "note": ""}
        with mock.patch("scanner.scan_ctl.scanui.print_question", lambda p: info):
            c.question_check()
            c.question_check()   # no retry loop on every tick
        self.assertIsNone(panel.question)
        self.assertEqual(c.question_wait, "print")
        self.assertEqual(qscan.scan_question(c), "print_wait")   # the status line shows [K]


class QuestionStays(unittest.TestCase):
    """Oliver 2026-10-30: an open question stays when the card is taken away (picked up for a closer look) or laid
    back; only a NEW, OTHER card recognized surely ends it (not counted, a note) – and recognition keeps running in the
    background meanwhile, so that card is noticed and then scanned as usual."""

    def rec(self, found=None):
        import numpy as np
        from scanner import recognizer
        r = recognizer.Recognizer.__new__(recognizer.Recognizer)
        r.settings = {"zone": None}
        r.pending = {"cands": [], "r": {"name": "Haspiror"}, "thumb": None, "lang": None, "ai": True}
        r.fp_index = object()
        r.prefer_sets, r.focus_sets = (lambda: ()), (lambda: ())
        r.live = types.SimpleNamespace(step=lambda *a, **k: found or {"status": "none"})
        r._ai_reset = lambda: None
        r.question_dropped = None
        r._ocr_last = None
        return r, recognizer, np

    def look(self, r, recognizer, frame):
        r._pend_next = 0.0
        with mock.patch.object(recognizer, "zone_rect", lambda z, w, h: (100, 50, 300, 380)):
            return r._pending_other_card(frame)

    def card_frame(self, np):
        f = np.full((480, 640, 3), 40, np.uint8)
        f[60:420, 110:390] = 200
        f[100:300, 140:360] = 30   # edges: a card is there
        return f

    def test_taken_away_keeps_the_question(self):
        r, recognizer, np = self.rec()
        self.assertFalse(self.look(r, recognizer, np.full((480, 640, 3), 40, np.uint8)))   # empty mat
        self.assertIsNotNone(r.pending)

    def test_same_card_back_keeps_it(self):
        r, recognizer, np = self.rec({"status": "ok", "entry": {"name": "Haspiror"}, "strength": 150, "how": ""})
        self.assertFalse(self.look(r, recognizer, self.card_frame(np)))
        self.assertIsNotNone(r.pending)

    def test_unsure_other_card_keeps_it(self):
        r, recognizer, np = self.rec({"status": "ok", "entry": {"name": "Pikachu"}, "strength": 60, "how": ""})
        self.assertFalse(self.look(r, recognizer, self.card_frame(np)))
        self.assertIsNotNone(r.pending)

    def test_other_card_ends_it(self):
        r, recognizer, np = self.rec({"status": "ok", "entry": {"name": "Pikachu"}, "strength": 150, "how": ""})
        self.assertTrue(self.look(r, recognizer, self.card_frame(np)))
        self.assertIsNone(r.pending)                 # _run_ai goes on: the new card is scanned as usual
        self.assertEqual(r.question_dropped, "Haspiror")


