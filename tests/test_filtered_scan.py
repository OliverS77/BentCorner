"""Filtered scan ("Only these sets", Oliver's review c5): which sets the scanner filters by, and the index part in RAM.
Run: python -m unittest discover -t . -s tests -p "test_filtered_scan.py" """
import contextlib
import types
import unittest
from unittest import mock

import numpy as np

from scanner import fingerprint
from scanner.recognizer import Recognizer


def _rec(kind, sets):
    return types.SimpleNamespace(session=types.SimpleNamespace(info={"kind": kind, "sets": sets}))


class FocusSets(unittest.TestCase):
    def test_boosters_and_cards_any_number(self):
        sets = [{"code": "FIN", "name": "Final Fantasy"}, {"code": "dsk", "name": "Duskmourn"},
                {"code": "fdn", "name": "Foundations"}]
        self.assertEqual(Recognizer.focus_sets(_rec("packs", sets)), ("dsk", "fdn", "fin"))
        self.assertEqual(Recognizer.focus_sets(_rec("cards", sets)), ("dsk", "fdn", "fin"))

    def test_none_for_singles_free_text_or_nothing(self):
        self.assertEqual(Recognizer.focus_sets(_rec("singles", [{"code": "fin", "name": "x"}])), ())
        self.assertEqual(Recognizer.focus_sets(_rec("packs", [{"code": "", "name": "Final Fantasy"}])), ())
        self.assertEqual(Recognizer.focus_sets(_rec("cards", [])), ())


class IndexPart(unittest.TestCase):
    def setUp(self):
        rnd = np.random.default_rng(3)
        idx = fingerprint.Index.__new__(fingerprint.Index)
        idx.ids = [f"{s}{i}_0" for s in ("a", "b") for i in range(6)]
        mat = rnd.normal(size=(12, 8)).astype(np.float32)
        idx.mat = mat / np.linalg.norm(mat, axis=1, keepdims=True)
        idx.cards = {cid: {"id": cid.rpartition("_")[0], "name": cid, "set": cid[0], "img": ""} for cid in idx.ids}
        self.idx = idx

    @contextlib.contextmanager
    def _db(self):
        con = mock.MagicMock()
        con.execute.side_effect = lambda q, key: [(cid.rpartition("_")[0],) for cid in self.idx.ids if cid[0] in key]
        yield con

    def test_part_of_the_chosen_sets(self):
        with mock.patch("cards.carddb.exists", return_value=True), mock.patch("cards.carddb.connection", self._db):
            rows = self.idx.rows_of_sets(["B"])
            entries = self.idx.preload_sets(["b"])
        self.assertEqual(list(rows), list(range(6, 12)))
        self.assertEqual(len(entries), 6)
        vec = self.idx.mat[8:9] + 0.01
        found = self.idx.search_many(vec, 3, rows=rows)[0]
        self.assertTrue(all(e["set"] == "b" for e, _ in found))
        self.assertEqual(found[0][0]["id"], "b2")
        full = self.idx.search_many(vec, 3)[0]   # the full search (the check) is unchanged
        self.assertEqual(full[0][0]["id"], "b2")

    def test_one_choice_at_a_time(self):
        with mock.patch("cards.carddb.exists", return_value=True), mock.patch("cards.carddb.connection", self._db):
            first = self.idx.rows_of_sets(["a"])
            self.idx.rows_of_sets(["b"])
        self.assertEqual(len(self.idx._focus_rows), 1)
        found = self.idx.search_many(self.idx.mat[:1], 2, rows=first)[0]   # an old choice still works (cut out)
        self.assertEqual(found[0][0]["id"], "a0")


if __name__ == "__main__":
    unittest.main()
