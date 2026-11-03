"""Owned prints the card database doesn't have (any more) – e.g. Yu-Gi-Oh! JP/ES/KR prints after the data change
without YGOJSON – stay in "Meine Sammlung": listed, findable by name, shown with the image of another print of the
same card (ui/librarycore.LibraryCore.mine_rows). Run against a small real card database in a temp folder.

    python -m unittest tests/test_lost_prints.py
"""
import pathlib
import sqlite3
import tempfile
import types
import unittest
from unittest import mock

from cards import carddb
from ui import librarycore


def make_db(path):
    con = sqlite3.connect(path)
    con.executescript(carddb.SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
    rows = [
        dict(id="lob-en001", name="Blue-Eyes White Dragon", lang="en", set_code="lob", number="EN001",
             rarity="ultra rare", type_line="Normal Monster", img_normal="https://img/89631139.jpg",
             img_small="https://img/s/89631139.jpg", layout="normal", booster=1, released="2002-03-08"),
        dict(id="lob-en005", name="Dark Magician", lang="en", set_code="lob", number="EN005", rarity="ultra rare",
             type_line="Normal Monster", img_normal="https://img/46986414.jpg", img_small="https://img/s/46986414.jpg",
             layout="normal", booster=1, released="2002-03-08"),
    ]
    con.executemany(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [tuple(r.get(c) for c in cols) for r in rows])
    con.executescript(carddb.INDEXES)
    con.commit()
    con.close()


def group(sid, name, set_code, number, lang):
    return {"sid": sid, "id": sid, "name": name, "set": set_code, "number": number, "lang": lang, "foil": False,
            "count": 1, "img": f"data/card-images/{set_code}/{number}_0.jpg", "last": 1.0, "rarity": "ultra rare",
            "finishes": ["nonfoil"], "booster": True, "eur": None, "eur_foil": None, "url": ""}


OWNED = [
    group("lob-en001", "Blue-Eyes White Dragon", "LOB", "EN001", "en"),     # in the database
    group("sdk-jp001", "Blue-Eyes White Dragon", "SDK", "JP001", "ja"),     # gone: JP print (YGOJSON)
    group("lob-sp001", "Blue-Eyes White Dragon", "LOB", "SP001", "es"),     # gone: ES print
    group("sdk-kr002", "Gone Forever Dragon", "SDK", "KR002", "ko"),        # gone, and no other print of the card
]


def stub(text=""):
    """Just what mine_rows needs of the library (no window)."""
    s = types.SimpleNamespace(
        coll=types.SimpleNamespace(groups=lambda: [dict(g) for g in OWNED]),
        filters=lambda: ({}, text), lang_filter=types.SimpleNamespace(selected=lambda: set(), mode=lambda: "or"),
        foil_only=types.SimpleNamespace(mode="all"), owned_cache={}, other_game_rows=lambda *a: [],
        extra_filter=None, _list_filter=lambda: (None, None), ctrl=types.SimpleNamespace(settings={}),
        sort=types.SimpleNamespace(currentData=lambda: "set"), sort_reverse=lambda: False)
    s.row_from_group = lambda g, dbrow, stand=None: librarycore.LibraryCore.row_from_group(s, g, dbrow, stand)
    return s


class LostPrints(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = pathlib.Path(self.tmp.name) / "cards.sqlite"
        make_db(db)
        self.patch = mock.patch.object(carddb, "DB_PATH", db)
        self.patch.start()
        carddb._upgrade_checked.add(db)   # no bundled database to compare with
        for f in (carddb.by_names, carddb.cards_by_ids):
            if hasattr(f, "cache_clear"):
                f.cache_clear()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def rows(self, text=""):
        return {r["sid"]: r for r in librarycore.LibraryCore.mine_rows(stub(text))}

    def test_lost_prints_stay_in_the_collection(self):
        self.assertEqual(set(self.rows()), {g["sid"] for g in OWNED})

    def test_lost_print_shows_the_image_of_another_print(self):
        rows = self.rows()
        for sid in ("sdk-jp001", "lob-sp001"):
            with self.subTest(sid=sid):
                self.assertIsNone(rows[sid]["db"])
                self.assertEqual(rows[sid]["normal"], "https://img/89631139.jpg")
                self.assertEqual(rows[sid]["thumb"], "https://img/s/89631139.jpg")
                self.assertEqual((rows[sid]["set"], rows[sid]["number"], rows[sid]["lang"]),
                                 next((g["set"], g["number"], g["lang"]) for g in OWNED if g["sid"] == sid))
        self.assertIsNone(rows["sdk-kr002"]["normal"])   # no other print: no image, but listed

    def test_lost_prints_are_found_by_name(self):
        self.assertEqual(set(self.rows("blue-eyes")), {"lob-en001", "sdk-jp001", "lob-sp001"})
        self.assertEqual(set(self.rows("forever")), {"sdk-kr002"})
        self.assertEqual(set(self.rows("magician")), set())   # not owned


if __name__ == "__main__":
    unittest.main()
