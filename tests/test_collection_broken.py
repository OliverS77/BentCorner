"""A damaged collection.json (performance 06.11.2026): an entry without a card id made the start fail ("Unexpected
error" in collection.summary). Now such entries are skipped and counted in the log – and kept: every save writes them
back unchanged, nothing is changed or deleted without a word.

    python -m unittest tests/test_collection_broken.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import collection as coll

GOOD = {"id": "0000579f-7b35-4ed3-b44c-db2a538066fe_0", "name": "Lightning Bolt", "set": "LEA", "number": "161",
        "lang": "en", "count": 2, "uid": "u1"}
BROKEN = [{"name": "Kaputt", "count": 1}, {"id": None, "count": 3}, {"id": "", "count": 1}, "Müll", 42]


class BrokenEntries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = pathlib.Path(self.tmp.name) / "collection.json"
        self.file.write_text(json.dumps({"version": 1, "items": [BROKEN[0], GOOD] + BROKEN[1:], "hidden": []},
                                        ensure_ascii=False), "utf-8")
        self.ps = [mock.patch.object(coll, "FILE", self.file), mock.patch.object(coll, "MINE", pathlib.Path(self.tmp.name)),
                   mock.patch("system.undo.before_write")]
        for p in self.ps:
            p.start()

    def tearDown(self):
        for p in self.ps:
            p.stop()
        self.tmp.cleanup()

    def test_start_works_and_counts_them(self):
        with self.assertLogs("booster", "WARNING") as logs:
            c = coll.Collection()
        self.assertEqual(c.items, [GOOD])
        self.assertIn("5 entries without a card id skipped", "\n".join(logs.output))
        s = c.summary()                                   # the place that failed before
        self.assertEqual((s["cards"], s["unique"]), (2, 1))
        self.assertEqual(len(coll.groups_of(c.items)), 1)

    def test_nothing_is_lost_on_save(self):
        with self.assertLogs("booster", "WARNING"):
            c = coll.Collection()
        c.items[0]["count"] = 3
        c.save()
        saved = json.loads(self.file.read_text("utf-8"))["items"]
        self.assertEqual(saved[0]["count"], 3)
        self.assertEqual(saved[1:], BROKEN)               # the broken entries: unchanged, all of them
        with self.assertLogs("booster", "WARNING"):
            c.reload()
        self.assertEqual(len(c.items), 1)
        self.assertEqual(c.broken, BROKEN)

    def test_other_games_read_only(self):
        import games
        with mock.patch.object(games, "mine", return_value=self.file), self.assertLogs("booster", "WARNING"):
            self.assertEqual(games.collection_items("pokemon"), [GOOD])

    def test_a_sound_file_stays_quiet(self):
        self.file.write_text(json.dumps({"items": [GOOD]}), "utf-8")
        with self.assertNoLogs("booster", "WARNING"):
            self.assertEqual(coll.Collection().items, [GOOD])


if __name__ == "__main__":
    unittest.main()
