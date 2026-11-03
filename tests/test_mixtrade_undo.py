"""A mixed trade and Undo (ports' find, lead 03.11.2026; the same as the web's test/mixtrade.test.js cases 4 and 5):

- the other games' part waits in their pending-trades.json (bookings.add_pending). Undo right after booking takes back
  the open game's booking AND that waiting part – one step, never half a trade;
- once the waiting part is booked (its game was opened), the history is gone anyway: switching games clears it
  (app.switch_game → undo.clear("game")). Ctrl+Z then says why instead of a bare "Nothing to undo".

    python -m unittest tests/test_mixtrade_undo.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import bookings
from system import undo


class MixedTradeUndo(unittest.TestCase):
    def setUp(self):
        undo.clear()
        self.addCleanup(undo.clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def mine(self, key, *parts):
        return self.root / key / "my-data" / pathlib.Path(*parts) if parts else self.root / key / "my-data"

    def test_one_step_takes_back_the_waiting_part_too(self):
        coll = self.root / "mtg" / "my-data" / "collection.json"
        coll.parent.mkdir(parents=True)
        coll.write_text('{"items": ["bolt"]}', "utf-8")
        with mock.patch("games.mine", self.mine):
            # the open game's booking (the collection is saved through undo like every store) …
            undo.before_write(coll, "Collection")
            coll.write_text('{"items": []}', "utf-8")
            # … and the Pokémon part goes into the queue right after
            t = {"id": "c0ffee42", "t": 1762000000}
            bookings.add_pending("pokemon", t, [["base1", "4", "en", 0, 1, "Charizard"]], [], ["fr", "Fr"], [])
            pend = self.mine("pokemon", "pending-trades.json")
            self.assertEqual(len(json.loads(pend.read_text("utf-8"))["pending"]), 1)
            res = undo.undo()
        self.assertIsNotNone(res)
        self.assertEqual(json.loads(coll.read_text("utf-8"))["items"], ["bolt"], "the booking is back")
        self.assertFalse(pend.exists(), "Pokémon's part waits no more")
        self.assertIsNone(undo.undo(), "it was one step")

    def test_a_waiting_list_from_before_stays(self):
        pend = self.mine("pokemon", "pending-trades.json")
        pend.parent.mkdir(parents=True)
        old = {"version": 1, "pending": [{"ticket": {"id": "older"}}]}
        pend.write_text(json.dumps(old), "utf-8")
        with mock.patch("games.mine", self.mine):
            bookings.add_pending("pokemon", {"id": "new1"}, [], [], ["", ""], [])
            undo.undo()
        self.assertEqual(json.loads(pend.read_text("utf-8")), old)

    def test_after_a_game_switch_undo_says_why(self):
        f = self.root / "x.json"
        undo.before_write(f, "Collection")
        undo.clear("game")   # app.switch_game
        self.assertIsNone(undo.undo())
        self.assertEqual(undo.cleared_why(), "game")
        undo.before_write(f, "Collection")   # the next step: the reason goes
        self.assertEqual(undo.cleared_why(), "")


if __name__ == "__main__":
    unittest.main()
