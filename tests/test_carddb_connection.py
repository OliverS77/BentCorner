"""carddb.connection(): the with block every card database access uses – closed afterwards (also on errors), rows
by column name, plain=True as bare tuples (set comparisons in the price updates), no automatic commit.

    python -m unittest tests/test_carddb_connection.py
"""
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

from cards import carddb


class Connection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "cards.sqlite"
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE t (a, b)")
        con.execute("INSERT INTO t VALUES (1, 'x')")
        con.commit()
        con.close()
        self.patch = mock.patch.object(carddb, "DB_PATH", self.db)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def closed(self, con):
        with self.assertRaises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")

    def test_rows_by_name_and_closed_afterwards(self):
        with carddb.connection() as con:
            row = con.execute("SELECT a, b FROM t").fetchone()
            self.assertEqual((row["a"], row["b"]), (1, "x"))
        self.closed(con)

    def test_closed_on_errors_too(self):
        with self.assertRaises(ZeroDivisionError):
            with carddb.connection() as con:
                1 / 0
        self.closed(con)

    def test_plain_rows_are_tuples(self):
        with carddb.connection(plain=True) as con:
            self.assertEqual(set(con.execute("SELECT a, b FROM t")), {(1, "x")})

    def test_no_automatic_commit(self):
        with carddb.connection() as con:
            con.execute("INSERT INTO t VALUES (2, 'y')")
        with carddb.connection() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)


class NeverCreates(unittest.TestCase):
    """A missing card database is never created by opening it – an empty file made the game count as having one,
    so it never built it and the set list crashed the game switch (Lorcana, 0.9.2.54)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "cards.sqlite"
        self.patches = [mock.patch.object(carddb, "DB_PATH", self.db),
                        mock.patch.object(carddb, "_from_bundle", return_value=False)]   # no bundled database
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_missing_raises_and_leaves_no_file(self):
        for plain in (False, True):
            with self.assertRaises(sqlite3.OperationalError):
                with carddb.connection(plain=plain):
                    pass
            self.assertFalse(self.db.exists())

    def test_empty_file_counts_as_missing_and_goes(self):
        self.db.write_bytes(b"")
        self.assertFalse(carddb.exists())
        self.assertFalse(self.db.exists())

    def test_empty_file_of_another_game_goes_too(self):
        other = pathlib.Path(self.tmp.name) / "other.sqlite"
        other.write_bytes(b"")
        with mock.patch.object(carddb, "path_of", return_value=other):
            self.assertFalse(carddb._has("lorcana"))
        self.assertFalse(other.exists())

    def test_real_database_stays(self):
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE meta (key, value)")
        con.commit()
        con.close()
        self.assertTrue(carddb.exists())
        with carddb.connection() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM meta").fetchone()[0], 0)


class SwitchWithoutDatabase(unittest.TestCase):
    """The game switch reads the set list (app._switch_now -> library.cached_sets): for every game that takes it from
    its card database, a missing, empty or unfinished database means no sets – never an error."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "cards.sqlite"
        self.patches = [mock.patch.object(carddb, "DB_PATH", self.db),
                        mock.patch.object(carddb, "_from_bundle", return_value=False)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def local_games(self):
        import games
        from games import base
        out = []
        for key, _name, ready in games.GAMES:
            if not ready:   # no game description yet (Riftbound)
                continue
            g = games.load(key)
            if type(g).sets_catalog is base.Game.sets_catalog:   # Magic/Pokémon ask their online source instead
                out.append(g)
        self.assertTrue(out)
        return out

    def check(self):
        for g in self.local_games():
            with self.subTest(game=g.key):
                self.assertEqual(g.cached_sets(), [])
                self.assertEqual(g.set_cards("abc"), [])

    def test_missing(self):
        self.check()
        self.assertFalse(self.db.exists())

    def test_empty_file(self):
        self.db.write_bytes(b"")
        self.check()

    def test_unfinished_database(self):   # a file without the cards table
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE meta (key, value)")
        con.commit()
        con.close()
        with self.assertLogs("booster", "ERROR"):
            self.check()


if __name__ == "__main__":
    unittest.main()
