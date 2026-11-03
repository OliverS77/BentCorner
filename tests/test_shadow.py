"""The library rebuilt from the logs alone, with the fields the sync carries (collection/shadow.py, docs/SYNC-PLAN.md
§3b): lines must carry finish/edition/grading, old migration lines are filled in, the shadow compare finds what the
logs can't rebuild.

    python -m unittest discover -t . -s tests -p test_shadow.py
"""
import json
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from collection import collection, logsum, manual, sessions, shadow
from tests.test_logsum import card, scan_log


class Shadow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.patches = [mock.patch.object(sessions, "SESSIONS", self.root / "sessions"),
                        mock.patch.object(collection, "FILE", self.root / "collection.json")]
        for p in self.patches:
            p.start()
        self.coll = collection.Collection()
        self.t = time.mktime((2026, 10, 27, 12, 0, 0, 0, 0, -1))

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def state(self):
        self.coll.save()
        return shadow.read(self.root)

    def test_scan_and_hand_rebuild_exactly(self):
        log = scan_log("2026-10-27_12-00-00", ["A", "B"], self.t)
        sessions.save(log)
        self.coll.sync_session(log)
        it = self.coll.add(card("C"), lang="de", finish="etched", edition="1st")
        manual.record(it, 1, when=self.t + 200)
        self.assertEqual(shadow.compare(*self.state()), [])

    def test_edit_line_carries_the_new_value(self):
        it = self.coll.add(card("C"), finish="nonfoil")
        manual.record(it, 1, when=self.t)
        self.coll.update(it["uid"], finish="foil", foil=True)
        manual.record_edit(dict(it), {"finish": ["nonfoil", "foil"], "foil": [False, True]}, when=self.t + 10)
        self.assertEqual(shadow.compare(*self.state()), [])
        line = manual.lines(manual.day_id(self.t))[-1]
        self.assertEqual(line["finish"], "foil")

    def test_migration_lines_carry_finish(self):
        it = self.coll.add(card("C"), finish="holo", edition="1st")   # from before every change was written down
        items, logs, book = self.state()
        mig = logsum.migration(items, logs, book, self.t)
        self.assertEqual((mig["packs"][0]["cards"][0]["finish"], mig["packs"][0]["cards"][0]["edition"]),
                         ("holo", "1st"))
        manual.save(mig)
        self.assertEqual(shadow.compare(*shadow.read(self.root)), [])
        self.assertTrue(it)

    def test_old_migration_lines_are_filled(self):
        it = self.coll.add(card("C"), finish="holo")
        items, logs, book = self.state()
        mig = logsum.migration(items, logs, book, self.t)
        for ln in mig["packs"][0]["cards"]:   # as written before 0.9.7.17
            ln.pop("finish", None)
        manual.save(mig)
        items, logs, book = shadow.read(self.root)
        self.assertEqual([d[1] for d in shadow.compare(items, logs, book)], ["finish"])
        changed = shadow.fill_variant(items, logs)
        self.assertEqual([d["id"] for d in changed], [mig["id"]])
        self.assertEqual(shadow.compare(items, logs, book), [])
        self.assertEqual(shadow.fill_variant(items, logs), [])   # second run: nothing left
        self.assertTrue(it)

    def test_fill_takes_the_value_before_a_later_edit(self):
        it = self.coll.add(card("C"), finish="holo")
        items, logs, book = self.state()
        mig = logsum.migration(items, logs, book, self.t)
        mig["packs"][0]["cards"][0].pop("finish")
        manual.save(mig)
        self.coll.update(it["uid"], finish="reverse")
        manual.record_edit(dict(it, finish="reverse"), {"finish": ["holo", "reverse"]}, when=self.t + 50)
        items, logs, book = self.state()
        shadow.fill_variant(items, logs)
        line = next(ln for d in logs if d["id"] == mig["id"] for ln in d["packs"][0]["cards"])
        self.assertEqual(line["finish"], "holo")
        self.assertEqual(shadow.compare(items, logs, book), [])

    def test_compare_finds_a_field_the_logs_dont_know(self):
        it = self.coll.add(card("C"))
        manual.record(it, 1, when=self.t)
        self.coll.update(it["uid"], cond="played")   # past the logs (no record_edit)
        diffs = shadow.compare(*self.state())
        self.assertEqual([(d[1], d[2], d[3]) for d in diffs], [("cond", "near_mint", "played")])

    def test_report_reads_a_folder(self):
        log = scan_log("2026-10-27_12-00-00", ["A"], self.t)
        sessions.save(log)
        self.coll.sync_session(log)
        self.coll.update(self.coll.items[0]["uid"], trade=1)
        self.coll.save()
        rep = shadow.report(self.root)
        self.assertEqual((rep["entries"], rep["copies"], rep["differ"], rep["trade_only"]), (1, 1, 0, 1))
        json.dumps(rep)


if __name__ == "__main__":
    unittest.main()
