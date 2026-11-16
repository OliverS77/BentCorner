"""lead 14.11.2026 after Oliver's slow evening: (a) the stall reporter also writes how long a stall really took and,
for a long one, where the main thread is after LONG; (b) a new card database of a game that is NOT open is taken over
in the background (pack job), not later at the game switch in the UI thread.

    python -m unittest tests.test_lagfix
"""
import pathlib
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest import mock

from cards import carddb
from ui import lagwatch


class StallReport(unittest.TestCase):
    def test_start_long_and_end_lines(self):
        patches = [mock.patch.object(lagwatch, "LIMIT", 0.05), mock.patch.object(lagwatch, "LONG", 0.3),
                   mock.patch.object(lagwatch, "END", 0.2), mock.patch.object(lagwatch, "_main_id", threading.get_ident())]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        lagwatch._beat = time.monotonic()
        t = threading.Thread(target=lagwatch._watch, daemon=True)
        with self.assertLogs("lagwatch", "WARNING") as logs:
            t.start()
            time.sleep(0.6)   # no heartbeat: a stall of ~0.6 s
            for _ in range(6):   # heartbeat again
                lagwatch._beat = time.monotonic()
                time.sleep(0.05)
        text = "\n".join(logs.output)
        self.assertIn("UI blocked for", text)
        self.assertIn("UI still blocked after", text)
        self.assertIn("UI blocked – ended after", text)
        self.assertGreaterEqual(lagwatch.ends[-1], 0.5)
        lagwatch._beat = time.monotonic() + 3600   # park the watcher thread (daemon) – it never reports again here


def make_db(path, build, prices):
    con = sqlite3.connect(path)
    con.executescript(carddb.SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
    for sid, eur in prices.items():
        row = dict(id=sid, name="Card " + sid, set_code="x", number="1", lang="en", layout="normal", booster=1, eur=eur)
        con.execute(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    tuple(row.get(c) for c in cols))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('pk_build', ?)", (str(build),))
    con.commit()
    con.close()


def build_of(path):
    con = sqlite3.connect(path)
    try:
        return int(con.execute("SELECT value FROM meta WHERE key='pk_build'").fetchone()[0])
    finally:
        con.close()


class BackgroundTakeover(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.pack = self.tmp / "packs" / "yugioh" / "cards.sqlite"
        self.db = self.tmp / "games" / "yugioh" / "card-data" / "cards.sqlite"
        for p in (self.pack, self.db):
            p.parent.mkdir(parents=True)
        make_db(self.pack, 8, {"a": None, "b": None, "c": None})
        make_db(self.db, 7, {"a": 1.5, "b": None})
        from cards import packs
        import games
        for p in (mock.patch.object(packs, "file_of", lambda key, name: self.pack if key == "yugioh" else None),
                  mock.patch.object(games, "folders", lambda key, data: {"ref": self.db.parent}),
                  mock.patch.object(games, "current", lambda: games.load("mtg")),
                  mock.patch("games.yugioh.YuGiOh.merge_extra", lambda self, db: 0)):
            p.start()
            self.addCleanup(p.stop)

    def test_other_game_taken_over_keeping_prices(self):
        self.assertTrue(carddb.prepare_game("yugioh"))
        self.assertEqual(build_of(self.db), 8)
        con = sqlite3.connect(self.db)
        eur = dict(con.execute("SELECT id, eur FROM cards"))
        con.close()
        self.assertEqual(eur, {"a": 1.5, "b": None, "c": None})   # the user's price stays, the new print is there
        self.assertFalse(carddb.prepare_game("yugioh"))   # nothing newer any more – the switch finds nothing to do

    def test_open_game_and_first_install_untouched(self):
        import games
        with mock.patch.object(games, "current", lambda: games.load("yugioh")):
            self.assertFalse(carddb.prepare_game("yugioh"))   # its database is in use: the old way at the switch
        self.assertEqual(build_of(self.db), 7)
        self.db.unlink()
        self.assertFalse(carddb.prepare_game("yugioh"))   # first install: at the switch, nothing to keep
        self.assertFalse(self.db.exists())

    def test_the_open_game_never_copies_at_the_same_time(self):
        """the lock: a switch during the background copy waits, then finds the database already newer"""
        self.assertIsInstance(carddb._bundle_lock, type(threading.Lock()))
        with carddb._bundle_lock:
            t = threading.Thread(target=carddb.prepare_game, args=("yugioh",))
            t.start()
            time.sleep(0.2)
            self.assertEqual(build_of(self.db), 7)   # waits for the lock
        t.join(5)
        self.assertEqual(build_of(self.db), 8)


if __name__ == "__main__":
    unittest.main()
