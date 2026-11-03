"""Collection by hand and Undo/Redo: adding the same card counts it together, other finishes/languages are their own
entries, removing hides session copies; undo() writes the previous file back and redo() the newer one
(collection/collection.py, system/undo.py). The collection file points into a temp folder; no UI, no network.

    python -m unittest tests/test_collection_undo.py
"""
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import collection as coll_mod
from system import undo

CARD = {"id": "c1", "name": "Sol Ring", "set": "cmm", "number": "1", "rarity": "uncommon", "eur": 1.0}
OTHER = {"id": "c2", "name": "Arcane Signet", "set": "cmm", "number": "2", "rarity": "common", "eur": 0.5}


class _Temp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        mine = pathlib.Path(self._tmp.name) / "my-data"
        self.p = [mock.patch.object(coll_mod, "MINE", mine),
                  mock.patch.object(coll_mod, "FILE", mine / "collection.json"),
                  mock.patch.object(undo, "GROUP_S", 0.0)]   # every save is its own step
        for p in self.p:
            p.start()
        undo.clear()

    def tearDown(self):
        undo.clear()
        for p in reversed(self.p):
            p.stop()
        self._tmp.cleanup()

    def counts(self, c):
        return sorted((it["id"], it["lang"], it["foil"], it["count"]) for it in c.items)


class ByHand(_Temp):
    def test_same_card_counts_together_other_finish_or_language_apart(self):
        c = coll_mod.Collection()
        a = c.add(CARD)
        self.assertIs(c.add(CARD, count=2), a)
        c.add(CARD, foil=True)
        c.add(CARD, lang="de")
        c.add(OTHER)
        self.assertEqual(self.counts(c), [("c1", "de", False, 1), ("c1", "en", False, 3), ("c1", "en", True, 1),
                                          ("c2", "en", False, 1)])

    def test_set_count_and_remove(self):
        c = coll_mod.Collection()
        a = c.add(CARD, count=3)
        c.set_count(a["uid"], 1)
        self.assertEqual(c.get(a["uid"])["count"], 1)
        c.remove(a["uid"])
        self.assertIsNone(c.get(a["uid"]))
        self.assertEqual(c.hidden, set())   # a card by hand just goes

    def test_removing_a_session_copy_keeps_it_hidden(self):
        c = coll_mod.Collection()
        c.items = [dict(CARD, uid="s", lang="en", foil=False, count=1, src="sess/0.5")]
        c.remove("s")
        self.assertEqual(c.items, [])
        self.assertEqual(c.hidden, {"sess/0.5"})   # does not come back with the session

    def test_save_and_load_round_trip(self):
        c = coll_mod.Collection()
        self.assertTrue(c.is_new)
        c.add(CARD, count=2)
        c.save()
        again = coll_mod.Collection()
        self.assertFalse(again.is_new)
        self.assertEqual(self.counts(again), [("c1", "en", False, 2)])


class UndoRedo(_Temp):
    def test_undo_and_redo_restore_the_file(self):
        c = coll_mod.Collection()
        c.add(CARD)
        c.save()                                   # step 1: no file -> one Sol Ring
        c.add(OTHER, count=4)
        c.save()                                   # step 2: + four Arcane Signets
        files, label = undo.undo()
        self.assertEqual(files, [coll_mod.FILE])
        self.assertTrue(label)
        c.reload()
        self.assertEqual(self.counts(c), [("c1", "en", False, 1)])
        undo.redo()
        c.reload()
        self.assertEqual(self.counts(c), [("c1", "en", False, 1), ("c2", "en", False, 4)])
        undo.undo()
        undo.undo()                                # back to before the first save: the file is gone
        self.assertFalse(coll_mod.FILE.exists())
        self.assertIsNone(undo.undo())             # nothing left

    def test_quiet_saves_are_no_step(self):
        c = coll_mod.Collection()
        c.add(CARD)
        with undo.quiet():
            c.save()
        self.assertIsNone(undo.undo())

    def test_only_the_last_steps_are_kept(self):
        c = coll_mod.Collection()
        for n in range(undo.MAX + 3):
            c.add(CARD)
            c.save()
        steps = 0
        while undo.undo():
            steps += 1
        self.assertEqual(steps, undo.MAX)


if __name__ == "__main__":
    unittest.main()
