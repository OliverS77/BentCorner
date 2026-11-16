"""lead 14.11.2026 after Oliver's slow evening (the UI waited for the card database while a background job wrote ~545,000
language rows into it): (1) the name indexes count as made only when they are, (2) new Magic languages go into a COPY
that is swapped in when the database is free – never a half copy, also not after a crash, (3) a new Magic index with
cards the card database doesn't know plans a Scryfall refresh within the next hour. No network.

    python -m unittest tests.test_dbquiet
"""
import gzip
import pathlib
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

import numpy as np

from cards import carddb
from system import jobqueue


def make_db(path, ids=("a", "b")):
    con = sqlite3.connect(path)
    con.executescript(carddb.SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
    for sid in ids:
        row = dict(id=sid, name="Card " + sid, set_code="x", number=sid, lang="en", layout="normal", booster=1)
        con.execute(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    tuple(row.get(c) for c in cols))
    con.commit()
    con.close()


def langs_of(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM langs WHERE lang = 'de'").fetchone()[0]
    finally:
        con.close()


class NameIndexes(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.db = self.tmp / "cards.sqlite"
        make_db(self.db)
        for p in (mock.patch.object(carddb, "DB_PATH", self.db), mock.patch.object(carddb, "_indexed", set()),
                  mock.patch.object(carddb, "_index_failed", {})):
            p.start()
            self.addCleanup(p.stop)

    def test_busy_is_tried_again_later_not_never(self):
        con = mock.Mock()
        con.execute.side_effect = lambda sql, *a: (_ for _ in ()).throw(sqlite3.OperationalError("database is locked")) \
            if sql.startswith("CREATE") else None
        carddb._name_indexes(con)
        self.assertNotIn(self.db, carddb._indexed)
        n = con.execute.call_count
        carddb._name_indexes(con)   # within the minute: no new try
        self.assertEqual(con.execute.call_count, n)
        with mock.patch.object(carddb, "INDEX_RETRY", 0.0):
            real = sqlite3.connect(self.db)
            carddb._name_indexes(real)   # free now: made
            real.close()
        self.assertIn(self.db, carddb._indexed)
        con = sqlite3.connect(self.db)
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        con.close()
        self.assertTrue({"cards_lname", "cards_front"} <= names)

    def test_read_only_counts_as_done(self):
        con = mock.Mock()
        con.execute.side_effect = lambda sql, *a: (_ for _ in ()).throw(
            sqlite3.OperationalError("attempt to write a readonly database")) if sql.startswith("CREATE") else None
        carddb._name_indexes(con)
        self.assertIn(self.db, carddb._indexed)


class LanguageCopy(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.db = self.tmp / "cards.sqlite"
        make_db(self.db)
        self.pack = self.tmp / "langs.tsv.gz"
        with gzip.open(self.pack, "wt", encoding="utf-8") as f:
            f.write("a\tde\ta-de\tKarte A\nb\tde\tb-de\tKarte B\n")
        from cards import packs
        p = mock.patch.object(packs, "path_of", lambda key, name: self.pack)
        p.start()
        self.addCleanup(p.stop)
        self.pending = self.tmp / carddb.LANGS_PENDING
        self.part = self.tmp / (carddb.LANGS_PENDING + ".part")

    def test_copy_then_swap(self):
        self.assertEqual(carddb.rebuild_langs(self.db), "done")
        self.assertEqual(langs_of(self.db), 2)
        self.assertFalse(self.pending.exists() or self.part.exists())

    def test_broken_off_build_leaves_nothing(self):
        before = self.db.read_bytes()
        with mock.patch.object(carddb, "_import_langs", side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            carddb.rebuild_langs(self.db)
        self.assertFalse(self.pending.exists() or self.part.exists())
        self.assertEqual(self.db.read_bytes(), before)

    def test_crash_leftover_part_removed_at_start(self):
        self.part.write_bytes(b"half")
        self.assertIsNone(carddb.start_cleanup(self.db))
        self.assertFalse(self.part.exists())

    def test_database_changed_meanwhile_copy_dropped(self):
        real_swap = carddb.swap_langs

        def write_first(db):   # a price job writes between the copy and the swap
            time.sleep(0.02)
            con = sqlite3.connect(self.db)
            con.execute("UPDATE cards SET eur = 1.0 WHERE id = 'a'")
            con.commit()
            con.close()
            return real_swap(db)
        with mock.patch.object(carddb, "swap_langs", write_first):
            self.assertEqual(carddb.rebuild_langs(self.db), "stale")
        self.assertFalse(self.pending.exists())
        self.assertEqual(langs_of(self.db), 0)   # nothing overwritten – the price stays, the job builds again

    def test_busy_waits_for_the_next_start(self):
        real_replace = pathlib.Path.replace

        def locked(self_, target):
            if self_.name == carddb.LANGS_PENDING:
                raise PermissionError("in use")
            return real_replace(self_, target)
        with mock.patch.object(pathlib.Path, "replace", locked):
            self.assertEqual(carddb.rebuild_langs(self.db), "busy")
        self.assertTrue(self.pending.exists())
        self.assertEqual(langs_of(self.db), 0)
        self.assertEqual(carddb.start_cleanup(self.db), "done")   # next start, before anything opens it
        self.assertEqual(langs_of(self.db), 2)


class Refresh(unittest.TestCase):
    def test_index_missing(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        make_db(tmp / "cards.sqlite", ids=("a", "b"))
        np.savez(tmp / "fp.npz", ids=np.array(["a_0", "b_0", "b_1", "c_0", "d_0"]), vecs=np.zeros((5, 2)))
        self.assertEqual(carddb.index_missing(tmp / "fp.npz", tmp / "cards.sqlite"), 2)

    def queue(self):
        q = jobqueue.JobQueue.__new__(jobqueue.JobQueue)
        q.settings, q.jobs, q.current = {}, [], None
        q.settings_changed = lambda: None
        q.enqueued = []
        q.enqueue = lambda kind, code=None, **kw: q.enqueued.append((kind, code, kw.get("for")))
        return q

    def test_planned_within_the_hour_then_once(self):
        q = self.queue()
        q.mtg_db_schedule(244)
        due = q.settings["mtg_db_due"]
        self.assertTrue(time.time() + 50 < due <= time.time() + jobqueue.MTG_REFRESH_SPREAD + 1)
        self.assertFalse(q.mtg_db_due_check())   # not yet
        q.settings["mtg_db_due"] = time.time() - 1
        q.jobs = [{"kind": "carddb", "code": "db"}]
        self.assertFalse(q.mtg_db_due_check())   # a card database job is running: wait
        q.jobs = []
        self.assertTrue(q.mtg_db_due_check())
        self.assertEqual(q.enqueued, [("carddb", "db-mtg", "mtg")])
        self.assertNotIn("mtg_db_due", q.settings)
        self.assertFalse(q.mtg_db_due_check())   # only once

    def test_threshold(self):
        self.assertEqual(jobqueue.MTG_REFRESH_MIN, 100)
        self.assertLessEqual(jobqueue.MTG_REFRESH_SPREAD, 3600)


if __name__ == "__main__":
    unittest.main()
