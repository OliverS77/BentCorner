"""Changes by hand as session entries (collection/manual.py): one session per day, each line its own undo, the
collection never takes these sessions over, old collections and sessions unchanged.

    python -m unittest discover -t . -s tests -p test_manual_history.py
"""
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from collection import collection, manual, sessions
from scanner import core


def card(name, eur=1.0, cid=None):
    return {"id": cid or f"{name}-id_0", "name": name, "set": "tst", "number": "1", "rarity": "rare",
            "finishes": ["nonfoil", "foil"], "booster": True, "eur": eur, "eur_foil": eur * 2, "img": "x.jpg", "url": ""}


class ByHand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.patches = [mock.patch.object(sessions, "SESSIONS", root / "sessions"),
                        mock.patch.object(collection, "FILE", root / "collection.json")]
        for p in self.patches:
            p.start()
        self.coll = collection.Collection()
        self.day = time.mktime((2026, 10, 27, 12, 0, 0, 0, 0, -1))

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def add(self, c, n=1, when=None):   # = app.collection_add
        it = self.coll.add(c, "en", False, n)
        return manual.record(it, n, when or self.day)

    def count(self, it, n, when=None):  # = app.collection_count
        before = dict(self.coll.get(it["uid"]))
        self.coll.set_count(it["uid"], n)
        return manual.record(before, max(0, n) - int(before.get("count", 1)), when or self.day)

    def test_one_session_per_day_with_one_line_per_change(self):
        self.add(card("A", 2.0), 3)
        a = self.coll.items[0]
        self.count(a, 1, self.day + 60)
        self.add(card("B", 5.0), 1, self.day + 86400)   # the next day
        d = sessions.load(manual.day_id(self.day))
        self.assertTrue(manual.is_manual(d) and sessions.is_manual(d))
        self.assertIs(d["collection"], False)
        self.assertEqual([(x["name"], x["delta"]) for x in d["packs"][0]["cards"]], [("A", 3), ("A", -2)])
        st = d["stats"]
        self.assertEqual((st["cards"], st["total"], st["packs"]), (1, 2.0, 0))   # +3 −2 at 2 €; no packs
        self.assertEqual(len(manual.lines(manual.day_id(self.day + 86400))), 1)

    def test_price_at_the_time_is_kept(self):
        line = self.add(card("A", 2.0))
        self.coll.reprice({"A-id": (9.0, 18.0)})
        self.assertEqual(line["price"], 2.0)
        self.assertEqual(manual.lines(manual.day_id(self.day))[0]["price"], 2.0)

    def test_undo_an_add_takes_exactly_those_copies_out(self):
        self.add(card("A"), 2)
        line = self.add(card("A"), 3)   # same card: counted together (5)
        self.assertEqual(manual.undo(self.coll, manual.day_id(self.day), line["added"]), ("ok", ""))
        self.assertEqual(self.coll.items[0]["count"], 2)
        self.assertEqual(len(manual.lines(manual.day_id(self.day))), 1)

    def test_undo_a_removal_brings_the_same_entry_back(self):
        self.add(card("A"), 2)
        it = dict(self.coll.items[0])
        line = self.count(it, 0)
        self.assertEqual(self.coll.items, [])
        self.assertEqual(manual.undo(self.coll, manual.day_id(self.day), line["added"])[0], "ok")
        self.assertEqual([(x["uid"], x["count"]) for x in self.coll.items], [(it["uid"], 2)])

    def test_undo_warns_when_the_card_moved_on(self):
        line = self.add(card("A"), 2)
        it = self.coll.items[0]
        self.coll.update(it["uid"], trade=2)   # marked for trading since
        state, why = manual.undo(self.coll, manual.day_id(self.day), line["added"])
        self.assertEqual(state, "moved")
        self.assertTrue(why)
        self.assertEqual(it["count"], 2)   # nothing done
        self.assertEqual(manual.undo(self.coll, manual.day_id(self.day), line["added"], force=True)[0], "ok")
        self.assertEqual(self.coll.items, [])

    def test_undo_when_the_card_is_gone(self):
        line = self.add(card("A"))
        self.coll.set_count(self.coll.items[0]["uid"], 0)
        self.assertEqual(manual.undo(self.coll, manual.day_id(self.day), line["added"])[0], "gone")

    def test_collection_never_takes_a_manual_session_over(self):
        self.add(card("A"))
        d = sessions.load(manual.day_id(self.day))
        self.assertFalse(self.coll.sync_session(d))
        self.assertEqual(len(self.coll.items), 1)

    def test_stats_membership(self):
        man = {"info": {"kind": "manual"}}
        imp_new, imp_old = {"info": {"kind": "import", "import": True}}, {"info": {"import": True}}
        self.assertTrue(sessions.counts_in_stats(man))   # value yes, pack figures no
        for d in (man, imp_new, imp_old):
            self.assertFalse(sessions.counts_for_packs(d))
        for d in (imp_new, imp_old):   # imports: in no statistics, as before
            self.assertFalse(sessions.counts_in_stats(d))
        self.assertTrue(sessions.is_import(imp_old) and sessions.is_import(imp_new))

    def test_scan_session_cant_become_manual(self):
        s = core.Session()
        self.assertFalse(s.set_kind("manual"))
        self.assertEqual(s.info["kind"], "cards")


if __name__ == "__main__":
    unittest.main()
