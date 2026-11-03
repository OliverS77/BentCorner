"""Yu-Gi-Oh! prints from ygo-locale.sqlite (Japan, Korea, Asia, Spain) have no image of their own: the detail view says
"Image: English print" – and only for those prints.

    python -m unittest tests/test_locale_image_note.py
"""
import types
import unittest
from unittest import mock

import games
from locales import de
from ui import librarycore


class LocaleImageNote(unittest.TestCase):
    def check(self, sid, locale_ids, game_has_hook=True):
        game = types.SimpleNamespace()
        if game_has_hook:
            game.locale_print = lambda s: s in locale_ids
        me = types.SimpleNamespace(row={"sid": sid})
        with mock.patch.object(games, "current", lambda: game):
            return librarycore.DetailState._locale_print(me)

    def test_locale_print_with_face_suffix(self):
        self.assertTrue(self.check("kc01-jp001_0", {"kc01-jp001"}))

    def test_english_print_has_no_note(self):
        self.assertFalse(self.check("kc01-en001_0", {"kc01-jp001"}))

    def test_games_without_locale_prints(self):
        self.assertFalse(self.check("swsh3-136_0", set(), game_has_hook=False))

    def test_translated(self):
        self.assertEqual(de.TEXTS["Image: English print"], "Bild: englischer Druck")


if __name__ == "__main__":
    unittest.main()
