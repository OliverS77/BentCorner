"""Yu-Gi-Oh!: the OCG/Asian/Spanish prints ship as their own file (ygo-locale.sqlite, CC BY-SA – never inside
cards.sqlite) and are merged into the LOCAL database on the user's PC (games/yugioh.merge_extra): own rows with the
data and image of the card's first print, no price; once per file, again when the file changes.

    python -m unittest tests/test_ygo_locale.py
"""
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

from cards import carddb
from games import yugioh

LOCALE_SCHEMA = """
CREATE TABLE prints (id TEXT PRIMARY KEY, oracle_id TEXT, set_code TEXT, set_name TEXT, number TEXT, rarity TEXT,
                     released TEXT, lang TEXT, promo_types TEXT);
CREATE TABLE langs (set_code TEXT, number TEXT, lang TEXT, id TEXT, name TEXT);
CREATE TABLE variants (sid TEXT, type TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def make_db(path):
    con = sqlite3.connect(path)
    con.executescript(carddb.SCHEMA)
    con.execute("CREATE TABLE variants (sid TEXT, type TEXT)")
    cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
    rows = [dict(id="mp22-en257", name="Ash Blossom & Joyous Spring", oracle_id="14558127", set_code="mp22",
                 number="EN257", rarity="common", released="2022-06-01", eur=0.5, usd=0.6, oracle_text="first",
                 img_normal="https://x/img/14558127.jpg"),
            dict(id="dabl-en001", name="Ash Blossom & Joyous Spring", oracle_id="14558127", set_code="dabl",
                 number="EN001", rarity="secret rare", released="2023-01-01", oracle_text="second",
                 img_normal="https://x/img/14558127.jpg")]
    con.executemany(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [tuple(dict(r, lang="en", layout="normal", booster=1).get(c) for c in cols) for r in rows])
    con.executemany("INSERT INTO langs VALUES (?,?,?,?,?)", [("mp22", "EN257", "de", "mp22-en257", "Aschenblüte")])
    con.commit()
    con.close()


def make_locale(path, prints):
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.executescript(LOCALE_SCHEMA)
    con.executemany("INSERT INTO prints VALUES (?,?,?,?,?,?,?,?,?)", prints)
    con.executemany("INSERT INTO langs VALUES (?,?,?,?,?)",
                    [(p[2], p[4], p[7], p[0], "灰流うらら") for p in prints if p[7] == "ja"] +
                    [("mp22", "EN257", "ja", "mp22-en257", "灰流うらら")])
    con.executemany("INSERT INTO variants VALUES (?,?)", [(p[0], "Secret Rare") for p in prints])
    con.commit()
    con.close()


JP = ("macr-jp036", "14558127", "macr", "Maximum Crisis", "JP036", "secret rare", "2017-01-14", "ja", "ScR")
SP = ("dabl-sp001", "14558127", "dabl", None, "SP001", "common", None, "es", "C")


class LocaleMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.db, self.loc = root / "cards.sqlite", root / "ygo-locale.sqlite"
        make_db(self.db)
        make_locale(self.loc, [JP])
        p = mock.patch("cards.packs.path_of", lambda key, name: self.loc if name == "ygo-locale.sqlite" else None)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def q(self, sql, *a):
        con = sqlite3.connect(self.db)
        try:
            return con.execute(sql, a).fetchall()
        finally:
            con.close()

    def test_merge_once_then_again_on_new_file(self):
        self.assertEqual(yugioh.GAME.merge_extra(self.db), 1)
        row = self.q("SELECT name, set_name, number, lang, released, oracle_text, img_normal, eur, usd FROM cards "
                     "WHERE id = 'macr-jp036'")[0]
        self.assertEqual(row, ("Ash Blossom & Joyous Spring", "Maximum Crisis", "JP036", "ja", "2017-01-14", "first",
                               "https://x/img/14558127.jpg", None, None))   # data + image of the first print, no price
        self.assertEqual(self.q("SELECT id FROM locale_ids"), [("macr-jp036",)])
        self.assertEqual(sorted(self.q("SELECT lang, id FROM langs WHERE lang = 'ja'")),
                         [("ja", "macr-jp036"), ("ja", "mp22-en257")])
        self.assertEqual(self.q("SELECT type FROM variants WHERE sid = 'macr-jp036'"), [("Secret Rare",)])
        self.assertEqual(yugioh.GAME.merge_extra(self.db), 0)   # same file: nothing
        make_locale(self.loc, [SP])                             # a newer file: the old merge goes, the new comes
        self.assertEqual(yugioh.GAME.merge_extra(self.db), 1)
        self.assertEqual(self.q("SELECT id, set_name, released FROM cards WHERE id IN ('macr-jp036', 'dabl-sp001')"),
                         [("dabl-sp001", None, "2022-06-01")])  # no own set name/date: the base print's
        self.assertEqual(self.q("SELECT count(*) FROM langs WHERE lang = 'ja'"), [(1,)])   # only the card name left
        self.assertEqual(self.q("SELECT count(*) FROM langs WHERE lang = 'de'"), [(1,)])   # YGOPRODeck names stay
        self.assertEqual(self.q("SELECT count(*) FROM cards"), [(3,)])

    def test_without_file_nothing(self):
        with mock.patch("cards.packs.path_of", lambda key, name: None):
            self.assertEqual(yugioh.GAME.merge_extra(self.db), 0)
        self.assertEqual(self.q("SELECT count(*) FROM cards"), [(2,)])


if __name__ == "__main__":
    unittest.main()
