"""A game unlocked only on this PC ("unlock_games" in settings.json): choosable, but without card images – not a
single request to its image servers – and the release (games.GAMES) stays unchanged.

    python -m unittest tests/test_local_unlock.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import requests

import games
from cards import imgcache
from net import netpolite


class LocalUnlock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = pathlib.Path(self.tmp.name) / "settings.json"
        # Lorcana as the not-yet-released game (the release list is patched here only for the test)
        unreleased = tuple((k, n, r and k != "lorcana") for k, n, r in games.GAMES)
        patch = mock.patch.object(games, "GAMES", unreleased)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(games, "WITHDRAWN", set())   # withdrawn (test_game_withdrawn.py) – not here
        patch.start()
        self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()
        netpolite.BLOCKED.clear()
        games._current = None

    def write(self, **kw):
        self.settings.write_text(json.dumps(kw), "utf-8")

    def test_not_released_game_needs_the_local_unlock(self):
        self.assertFalse(games.released("lorcana"))
        self.write(game="lorcana")
        self.assertEqual(games.active_key(self.settings), "mtg")
        self.write(game="lorcana", unlock_games=["lorcana", "nonsense"])
        self.assertEqual(games.unlocked(self.settings), {"lorcana"})
        self.assertEqual(games.active_key(self.settings), "lorcana")
        self.assertFalse(games.released("lorcana"))   # the release list itself doesn't change

    def test_unlocked_game_loads_no_images(self):
        from games import lorcana
        self.write(game="lorcana", unlock_games=["lorcana"])
        key = games.active_key(self.settings)
        with mock.patch.object(games, "active_key", lambda: key), \
                mock.patch.object(type(lorcana.GAME), "image_hosts", ("images.example.test",)):
            games._current = None
            g = games.current()
        try:
            self.assertEqual(g.key, "lorcana")
            self.assertTrue(g.images_off)
            self.assertIn("images.example.test", netpolite.BLOCKED)
            with mock.patch.object(netpolite, "_request", side_effect=AssertionError("request sent")):
                with self.assertRaises(requests.RequestException):
                    netpolite.get("https://images.example.test/cards/AB01-001.png")
                target = pathlib.Path(self.tmp.name) / "x.png"
                self.assertFalse(imgcache.fetch(target, "https://example.org/any.png"))
                self.assertFalse(target.exists())
        finally:
            g.images_off = False   # the game object is shared – leave it as it was for other tests

    def test_released_game_unchanged(self):
        games._current = None
        with mock.patch.object(games, "active_key", lambda: "pokemon"):
            g = games.current()
        self.assertFalse(g.images_off)
        self.assertEqual(netpolite.BLOCKED, set())


if __name__ == "__main__":
    unittest.main()
