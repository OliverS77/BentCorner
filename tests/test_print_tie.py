"""A print chosen by name (carddb.by_names – deck import, card lists) on a tie: same booster flag and date, e.g. the
Islands ECL 270/275/280. The lower collector number wins, whatever order the database holds them in (03.11.2026:
before, SQLite's order decided). Booster and date still come first.

    python -m unittest tests/test_print_tie.py
"""
import itertools
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

from cards import carddb


def card(cid, number, booster=1, released="2026-01-23", name="Island"):
    return dict(id=cid, name=name, lang="en", set_code="ecl", number=number, rarity="common",
                type_line="Basic Land — Island", layout="normal", booster=booster, released=released)


class PrintTie(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def by_names(self, rows, names=("Island",)):
        db = pathlib.Path(self.tmp.name) / f"cards{len(list(pathlib.Path(self.tmp.name).iterdir()))}.sqlite"
        con = sqlite3.connect(db)
        con.executescript(carddb.SCHEMA)
        cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
        con.executemany(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [tuple(r.get(c) for c in cols) for r in rows])
        con.executescript(carddb.INDEXES)
        con.commit()
        con.close()
        with mock.patch.object(carddb, "DB_PATH", db):
            carddb._upgrade_checked.add(db)
            if hasattr(carddb.by_names, "cache_clear"):
                carddb.by_names.cache_clear()
            return carddb.by_names(list(names))

    def test_lower_collector_number_on_a_tie_in_any_order(self):
        islands = [card("i280", "280"), card("i270", "270"), card("i275", "275")]
        for order in itertools.permutations(islands):
            with self.subTest(order=[c["number"] for c in order]):
                self.assertEqual(self.by_names(list(order))["island"]["id"], "i270")

    def test_number_compares_as_a_number(self):
        self.assertEqual(self.by_names([card("a", "1000"), card("b", "99")])["island"]["id"], "b")

    def test_booster_and_date_still_first(self):
        rows = [card("old", "1", released="2020-01-01"), card("new", "300"), card("promo", "2", booster=0, released="2027-01-01")]
        self.assertEqual(self.by_names(rows)["island"]["id"], "new")


if __name__ == "__main__":
    unittest.main()
