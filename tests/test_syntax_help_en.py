"""The search field's syntax help (ui/searchbox.SYNTAX_HELP, a German key) has its English in locales/legacy_de.py –
line for line. library added "year:" to the German only, so English showed the German help (03.11.2026)."""
import unittest

from locales import legacy_de
from ui.searchbox import SYNTAX_HELP


class SyntaxHelpEnglish(unittest.TestCase):
    def test_english_exists_with_the_same_lines(self):
        self.assertIn(SYNTAX_HELP, legacy_de.TEXTS)
        en = legacy_de.TEXTS[SYNTAX_HELP]
        self.assertEqual(len(en.split("\n")), len(SYNTAX_HELP.split("\n")))
        self.assertIn("year:1999", en)


if __name__ == "__main__":
    unittest.main()
