"""A withdrawn game (games.WITHDRAWN – here a made-up "paused" game): never offered, not even unlocked on this PC;
saved as the active game it falls back to Magic and its collection stays untouched; no data pack is fetched for it.

    python -m unittest tests/test_game_withdrawn.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import games
from cards import packs


PAUSED = "paused"   # a made-up game that has been withdrawn


class Withdrawn(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(games, "GAMES", games.GAMES + ((PAUSED, "Paused Game", False),)),
                  mock.patch.object(games, "WITHDRAWN", {PAUSED})):
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name)
        self.settings = self.home / "settings.json"

    def write(self, **kw):
        self.settings.write_text(json.dumps(kw), "utf-8")

    def test_not_released_and_not_offered(self):
        self.assertIn(PAUSED, games.WITHDRAWN)
        self.assertFalse(games.released(PAUSED))
        with mock.patch.object(games, "unlocked", lambda settings_file=None: set()):
            c = next(c for c in games.choices() if c["key"] == PAUSED)
        self.assertFalse(c["ready"])

    def test_local_unlock_does_not_bring_it_back(self):
        self.write(game=PAUSED, unlock_games=[PAUSED])
        self.assertEqual(games.unlocked(self.settings), set())
        self.assertEqual(games.active_key(self.settings), "mtg")

    def test_saved_active_game_falls_back_collection_untouched(self):
        mine = games.folders(PAUSED, self.home / "data")["mine"]
        mine.mkdir(parents=True)
        coll = mine / "collection.json"
        coll.write_text(json.dumps({"items": [{"id": "AB01-001", "count": 2}]}), "utf-8")
        before = coll.read_bytes()
        self.write(game=PAUSED)
        self.assertEqual(games.active_key(self.settings), "mtg")
        self.assertEqual(coll.read_bytes(), before)
        self.assertEqual(json.loads(self.settings.read_text("utf-8"))["game"], PAUSED)   # nothing rewritten

    def test_no_pack_for_it(self):
        with mock.patch.object(packs, "installed", lambda k: False), \
                mock.patch.object(packs, "bundled", lambda k: False), \
                mock.patch.object(games, "unlocked", lambda settings_file=None: set()), \
                mock.patch.dict(packs.PACKS, {PAUSED: {"name": "Paused", "dir": PAUSED, "files": ["cards.sqlite"]}}):
            need = packs.needed({"games_on": [PAUSED, "pokemon"]})
        self.assertNotIn(PAUSED, need)
        self.assertIn("pokemon", need)

    def test_not_in_the_studio(self):
        from ui import qstudio
        self.assertNotIn(PAUSED, [k for k, _n in qstudio._games()])
