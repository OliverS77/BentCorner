"""The scanner's question keeps a finish chosen in it (0.9.6 users: language + Reverse Holo set together – only the
language arrived). The answer takes finish and edition along when they were changed in the window, never when they
were left alone (the card keeps what it has); F in the question switches the finish; Esc after F takes nothing.

    python -m unittest tests/test_question_finish.py
"""
import collections
import types
import unittest
from unittest import mock

from cards import finishes
from scanner.recognizer import Recognizer
from scanner.scan_ctl import ScanControl
from ui import qcardsearch
from ui.panels import CardPanel

OPTS = [{"key": "normal", "label": "Normal", "foil": False}, {"key": "holo", "label": "Holo", "foil": True},
        {"key": "reverse", "label": "Reverse Holo", "foil": True}]


def entry(**kw):
    return dict({"id": "dp1-103_0", "name": "Turtwig", "set": "DP1", "number": "103", "lang": "en", "foil": False,
                 "eur": 0.2, "eur_foil": 0.9, "img": "x.jpg", "added": 7.0}, **kw)


def fake_select(self, card, url):   # the real one asks the card database and Scryfall
    self.sel, self.sel_url = card, url
    if card is not None and (self.editing is None or self.finish not in [o["key"] for o in OPTS]):
        self.finish = OPTS[0]["key"]
        self.foil = False


class Base(unittest.TestCase):
    def setUp(self):
        ctrl = types.SimpleNamespace(settings={"card_lang": "en"},
                                     overlay=types.SimpleNamespace(panel_rect=None, other_face=lambda c: None,
                                                                   show_back=False, card_by_id={}))
        self.p = CardPanel(ctrl, in_stream=False)
        for target, name, fn in ((CardPanel, "select", fake_select), (CardPanel, "hover_row", lambda self, r: None),
                                 (CardPanel, "_row_of", lambda self, card: {}),
                                 (finishes, "options", lambda card: OPTS)):
            patch = mock.patch.object(target, name, fn)
            patch.start()
            self.addCleanup(patch.stop)
        self.answers = []

    def done(self, card, lang, how):
        self.answers.append((card and card["id"], lang, how))

    def backend(self):   # kept: it listens to the panel's signals
        self.cs = qcardsearch.CardSearchBackend(self.p)
        return self.cs

    def ask_lang(self, **kw):
        self.p.open_question("lang", self.done, entry=entry(**kw))


class LanguageQuestion(Base):
    def test_language_key_takes_the_finish_along(self):
        self.ask_lang()
        self.p.set_finish("reverse")
        self.p.lang_picked("de")
        self.assertEqual(self.answers, [("dp1-103_0", "de", {"finish": "reverse", "edition": ""})])

    def test_take_takes_the_finish_along(self):
        self.ask_lang()
        self.p.set_finish("holo")
        self.p.lang = "fr"
        self.p.answer(self.p.sel, self.p.lang)   # what streamwindow.card_chosen does on "Take" / Enter
        self.assertEqual(self.answers, [("dp1-103_0", "fr", {"finish": "holo", "edition": ""})])

    def test_field_counts_as_filled_in(self):   # 1–9 and F in the field only work while it holds this text
        self.ask_lang()
        self.assertEqual(self.backend().questionText, "Turtwig")

    def test_untouched_finish_is_left_alone(self):
        self.ask_lang(finish="holo", foil=True)
        self.assertEqual(self.p.finish, "holo")   # the window shows what the card is now – not "Normal"
        self.p.lang_picked("de")
        self.assertEqual(self.answers, [("dp1-103_0", "de", {})])

    def test_f_switches_on_from_the_cards_finish_and_keeps_the_edition(self):
        self.ask_lang(finish="holo", foil=True, edition="1st")
        cs = self.backend()
        self.assertTrue(cs.nextFinish())
        self.assertEqual((self.p.finish, self.p.foil), ("reverse", True))
        self.assertTrue(cs.nextFinish())
        self.assertEqual((self.p.finish, self.p.foil), ("normal", False))
        self.p.lang_picked("de")
        self.assertEqual(self.answers, [("dp1-103_0", "de", {"finish": "normal", "edition": "1st"})])

    def test_esc_after_f_takes_nothing(self):
        self.ask_lang()
        self.assertTrue(self.backend().nextFinish())
        self.p._visible = True
        self.p.hide()   # Esc / ✕
        self.assertEqual(self.answers, [(None, None, {})])

    def test_f_does_nothing_outside_a_question(self):
        self.ask_lang()
        self.p.answer(None, None)
        self.assertFalse(self.backend().nextFinish())

    def test_controller_sets_language_and_finish_on_the_counted_card(self):
        calls = []
        c = types.SimpleNamespace(session=types.SimpleNamespace(id=1, set_card=lambda added, **kw: calls.append(
            (added, kw))), recognizer=types.SimpleNamespace(pending=None, lang_ask={"added": 7.0, "entry": entry(),
                                                                                     "img": None}))
        panel = types.SimpleNamespace()
        panel.open_question = lambda kind, done, **kw: setattr(panel, "done", done)
        c.stream = types.SimpleNamespace(card_panel=panel, bring_up=lambda: None, only=lambda w: None,
                                         flip_in_card_panel=lambda: None)
        c._question_window = ScanControl._question_window.__get__(c)
        with mock.patch("scanner.scan_ctl.print_has_languages", lambda e: True):
            self.assertTrue(ScanControl._open_question(c, "lang"))
        panel.done(entry(), "de", {"finish": "reverse", "edition": ""})
        self.assertEqual(calls, [(7.0, {"lang": "de"}), (7.0, {"finish": "reverse", "edition": ""})])
        calls.clear()
        panel.done(entry(), "de", {})   # finish untouched: only the language
        self.assertEqual(calls, [(7.0, {"lang": "de"})])


class PrintQuestion(Base):
    def test_print_question_counts_with_the_chosen_finish(self):
        rows = [{"id": "dp1-103", "name": "Turtwig", "set_code": "dp1", "number": "103", "booster": 1,
                 "finishes": "nonfoil", "eur": 0.2, "eur_foil": 0.9, "img_small": None, "faces": None, "lang": "en"}]
        with mock.patch("ui.panels.hybrid.image_url", lambda r: "https://img/x.jpg"):
            self.p.open_question("print", self.done, rows=rows, star={"dp1-103_0"}, name="Turtwig")
        self.assertTrue(self.backend().nextFinish())
        self.p.answer(self.p.sel, "en")
        self.assertEqual(self.answers, [("dp1-103_0", "en", {"finish": "holo", "edition": ""})])

    def recognizer(self, ai):
        rec = types.SimpleNamespace(confirmed=collections.Counter(), counted=[])
        rec.pending = {"ai": ai, "force": True, "chosen_lang": "de", "chosen_how": {"finish": "reverse", "edition": ""},
                       "r": {}, "thumb": None, "lang": "en"}
        return rec

    def test_ai_mode_books_then_sets_the_finish(self):
        rec = self.recognizer(ai=True)
        rec._ai_count_chosen = lambda e, force, lang=None, how=None: rec.counted.append((e["id"], lang, how))
        Recognizer.resolve(rec, {"_entry": entry(), "set_code": "dp1"})
        self.assertEqual(rec.counted, [("dp1-103_0", "de", {"finish": "reverse", "edition": ""})])

        calls = []
        rec.session = types.SimpleNamespace(set_card=lambda added, **kw: calls.append((added, kw)))
        rec._ai_book = lambda e, force: dict(e)
        rec._remember_crop = lambda *a: None
        Recognizer._ai_count_chosen(rec, entry(), True, lang="de", how={"finish": "reverse", "edition": ""})
        self.assertEqual(calls, [(7.0, {"finish": "reverse", "edition": ""}), (7.0, {"lang": "de"})])

    def test_classic_count_sets_the_finish(self):
        calls = []
        cur = entry()
        sess = types.SimpleNamespace(current=None, set_card=lambda added, **kw: calls.append((added, kw)))
        sess.on_card = lambda e, lang: setattr(sess, "current", cur)
        rec = types.SimpleNamespace(session=sess, _mark_hit=lambda e: None)
        Recognizer._count(rec, entry(), "de", how={"finish": "reverse", "edition": ""})
        self.assertEqual(calls, [(7.0, {"finish": "reverse", "edition": ""})])


if __name__ == "__main__":
    unittest.main()
