"""0.9.7.21 – the texts of the small round after the web's decks (03.11.2026): the specific card counts before the
general rule, Magic's "Ramp"/"Removal" stay English, the trade log's title, singulars in the statistics."""
import unittest

from system import i18n


class SmallRoundTexts(unittest.TestCase):
    def setUp(self):
        self._lang = i18n.LANG
        i18n.set_language("de")

    def tearDown(self):
        i18n.set_language(self._lang)

    def test_card_counts_before_the_general_rule(self):
        tr = i18n.tr
        self.assertEqual(tr("63 of 100 cards"), "63 von 100 Karten")
        self.assertEqual(tr("55 of at least 60 cards"), "55 von mindestens 60 Karten")
        self.assertEqual(tr("12 cards"), "12 Karten")   # the general rule still works

    def test_trade_log_title_and_singulars(self):
        tr = i18n.tr
        self.assertEqual(tr("Trade with Anna"), "Tausch mit Anna")
        self.assertEqual(tr("1 foil"), "1 Foil")
        self.assertEqual(tr("1 language"), "1 Sprache")
        self.assertEqual(tr("Card selection"), "Kartenauswahl")
        self.assertEqual(tr("<b>5</b> cards, <b>5</b> unique, from <b>4</b> sets."),
                         "<b>5</b> Karten, <b>5</b> verschiedene, aus <b>4</b> Sets.")
        self.assertTrue(tr("In <b>1</b> log you scanned <b>{cards}</b> cards. Enter what you paid in the log (scan page: "
                           "the Log tile, or here in the list) – then your balance shows up here.").startswith("In <b>1</b> Log"))

    def test_magic_roles_stay_english(self):
        from collection import decks
        if decks._G.key != "mtg":
            self.skipTest("Magic is not the open game")
        self.assertEqual(decks.role_label("Ramp"), "Ramp")
        self.assertEqual(decks.role_label("Removal"), "Removal")
        self.assertEqual(decks.role_label("Kartenziehen"), i18n.tr("Kartenziehen"))


if __name__ == "__main__":
    unittest.main()
