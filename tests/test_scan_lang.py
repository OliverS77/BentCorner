"""The language of a log (Oliver 2026-11-01: per scan round, for every game, not the library – Scan tile → Settings →
Language). New cards come in it when their print exists in it; when SCAN° can't read the language clearly it takes the
log's language instead of asking – but a reading that clearly shows another language (>= 85) still wins, and a card
that doesn't exist in it is never forced into it (0 falsely sure stays the first rule).

    python -m unittest tests/test_scan_lang.py
"""
import types
import unittest
from unittest import mock

from scanner import core
from scanner.recognizer import Recognizer
from ui import scantiles


def card(**kw):
    return dict({"id": "dp1-103_0", "name": "Turtwig", "set": "DP1", "number": "103", "finishes": ["nonfoil"],
                 "eur": 0.2, "eur_foil": None, "img": "x.jpg"}, **kw)


class NewCards(unittest.TestCase):
    def setUp(self):
        self.s = core.Session()
        self.s.default_lang = "en"
        for name, fn in (("exists", lambda: True), ("lacks_language", lambda st, nr, lg: (st, lg) == ("PROMO", "de"))):
            patch = mock.patch(f"cards.carddb.{name}", fn)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch("net.anonstats.mark", lambda *a, **k: None)
        patch.start()
        self.addCleanup(patch.stop)

    def lang_of_new(self, c, lang=None):
        self.s.add_manual(c, lang=lang)
        return self.s.current["lang"]

    def test_all_languages_keeps_the_default(self):
        self.assertEqual(self.lang_of_new(card()), "en")

    def test_the_logs_language_for_new_cards(self):
        self.s.set_info(scan_lang="de")
        self.assertEqual(self.lang_of_new(card()), "de")

    def test_a_print_without_that_language_keeps_the_default(self):
        self.s.set_info(scan_lang="de")
        self.assertEqual(self.lang_of_new(card(set="PROMO")), "en")

    def test_a_read_or_asian_language_wins(self):
        self.s.set_info(scan_lang="de")
        self.assertEqual(self.lang_of_new(card(), lang="fr"), "fr")
        self.assertEqual(self.lang_of_new(card(id="sv1-1_0", plang="ja")), "ja")


class UnclearLanguage(unittest.TestCase):
    def rec(self, scan_lang="de", lacks=False):
        taken = []
        sess = types.SimpleNamespace(info={"scan_lang": scan_lang}, find=lambda added: (0, 0))
        sess.scan_lang_for = lambda c: core.Session.scan_lang_for(sess, c)
        r = types.SimpleNamespace(session=sess, _set_lang_checked=lambda e, a, lg: taken.append(lg))
        patches = [mock.patch("cards.carddb.exists", lambda: True),
                   mock.patch("cards.carddb.lacks_language", lambda st, nr, lg: lacks)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return r, taken

    NAMES = {"en": "Turtwig", "de": "Chelast", "fr": "Tortipouss"}

    def take(self, r, votes, names=None):
        return Recognizer._take_log_lang(r, card(), 1.0, names or self.NAMES, votes)

    def test_unclear_takes_the_logs_language(self):
        r, taken = self.rec()
        self.assertTrue(self.take(r, [("de", 60), ("en", 55)]))
        self.assertEqual(taken, ["de"])

    def test_no_reading_at_all_takes_it_too(self):
        r, taken = self.rec()
        self.assertTrue(self.take(r, []))
        self.assertEqual(taken, ["de"])

    def test_a_clear_other_reading_wins(self):
        r, taken = self.rec()
        self.assertFalse(self.take(r, [("fr", 91), ("de", 40)]))
        self.assertEqual(taken, [])

    def test_never_forced_into_a_language_the_card_lacks(self):
        r, taken = self.rec(lacks=True)
        self.assertFalse(self.take(r, [("de", 60)]))
        r, taken = self.rec()
        self.assertFalse(self.take(r, [], names={"en": "Turtwig", "fr": "Tortipouss"}))
        self.assertEqual(taken, [])

    def test_all_languages_asks_as_before(self):
        r, taken = self.rec(scan_lang=None)
        self.assertFalse(self.take(r, [("de", 60)]))


class Tile(unittest.TestCase):
    def test_names(self):
        self.assertEqual(scantiles.scan_lang_name("de"), "Deutsch")
        self.assertEqual(scantiles.scan_lang_name(None), "")


if __name__ == "__main__":
    unittest.main()
