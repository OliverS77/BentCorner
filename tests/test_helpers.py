"""Small shared helpers from the cleanup round (CLEANUP lines 45, 47): games.mine, trade.friends_folder,
games.current_key – and no hand-built "my-data of another game" paths left.

    python -m unittest tests/test_helpers.py
"""
import pathlib
import re
import unittest
from unittest import mock

import games
from collection import trade
from scanner import common

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Helpers(unittest.TestCase):
    def test_mine(self):
        self.assertEqual(games.mine("pokemon"), games.folders("pokemon", common.DATA)["mine"])
        self.assertEqual(games.mine("pokemon", "friends", "x.json"),
                         games.folders("pokemon", common.DATA)["mine"] / "friends" / "x.json")
        self.assertEqual(games.mine("mtg", "binders.json"), common.DATA / "my-data" / "binders.json")

    def test_friends_folder(self):
        with mock.patch.object(games, "current", lambda: mock.Mock(key="mtg")):
            self.assertEqual(trade.friends_folder("mtg"), trade.FRIENDS)   # open game: the (patchable) constant
            self.assertEqual(trade.friends_folder("pokemon"), games.mine("pokemon", "friends"))

    def test_current_key(self):
        with mock.patch.object(games, "current", lambda: mock.Mock(key="lorcana")):
            self.assertEqual(games.current_key(), "lorcana")

    def test_no_hand_built_paths_left(self):
        bad = re.compile(r'folders\([^)]*DATA\)\["mine"\]')
        for p in ROOT.rglob("*.py"):
            rel = p.relative_to(ROOT).as_posix()
            if rel.startswith((".venv/", "build/", "dist/", "tools/", "tests/")) or rel == "games/__init__.py":
                continue
            self.assertIsNone(bad.search(p.read_text("utf-8", errors="replace")), rel)


if __name__ == "__main__":
    unittest.main()
