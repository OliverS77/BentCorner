"""python -m locales.check finds no English text without German (tr() on English + locales/de.py) – and a game name
in an f-string ("Switch to {games.nick_of(…)}") counts as translated when the games-only rule knows every game."""
import re
import unittest

from locales import check, de


class Check(unittest.TestCase):
    def test_every_text_has_german(self):
        self.assertEqual([f"{n}:{line} {t!r}" for n, line, t, _ in check.missing(de)], [])

    def test_game_placeholder(self):
        rules = [re.compile(p) for p, _ in de.RULES]
        self.assertTrue(check._als_spiel("Switch to 1", rules))
        self.assertFalse(check._als_spiel("Switch to 1 now and then", rules))   # no rule for that: still missing
        self.assertFalse(check._als_spiel("Switch to Full Orbit", rules))       # no placeholder: not this path


if __name__ == "__main__":
    unittest.main()
