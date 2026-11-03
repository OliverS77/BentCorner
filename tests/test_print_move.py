"""Prints that left the card database (Yu-Gi-Oh! without YGOJSON): references in the personal data move to the English
print of the same card and keep their language (collection.printmove) – nothing lost, nothing pointing nowhere.

    python -m unittest tests/test_print_move.py
"""
import json
import pathlib
import sqlite3
import tempfile
import types
import unittest
from unittest import mock

from cards import carddb
from collection import printmove


def make_db(path):
    con = sqlite3.connect(path)
    con.executescript(carddb.SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
    rows = [
        dict(id="dabl-en001", name="Ash Blossom & Joyous Spring", set_code="dabl", number="EN001", rarity="common",
             released="2022-01-01"),
        dict(id="dabl-en001-sr", name="Ash Blossom & Joyous Spring", set_code="dabl", number="EN001-SR",
             rarity="super rare", released="2022-01-01"),
        dict(id="mp22-en257", name="Ash Blossom & Joyous Spring", set_code="mp22", number="EN257", rarity="common",
             released="2022-06-01"),
        dict(id="lob-en001", name="Blue-Eyes White Dragon", set_code="lob", number="EN001", rarity="ultra rare",
             released="2002-03-08"),
    ]
    con.executemany(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [tuple(dict(r, lang="en", layout="normal", booster=1).get(c) for c in cols) for r in rows])
    con.execute("INSERT OR REPLACE INTO meta VALUES ('pk_build', '6')")
    con.commit()
    con.close()


def item(sid, name, set_code, number, **kw):
    return dict({"id": f"{sid}_0", "name": name, "set": set_code, "number": number, "rarity": "common",
                 "img": f"data/games/yugioh/card-images/{set_code.lower()}/{number}_0.jpg", "url": "", "count": 1,
                 "uid": sid}, **kw)


class PrintMove(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.db, self.mine = root / "cards.sqlite", root / "my-data"
        (self.mine / "sessions").mkdir(parents=True)
        make_db(self.db)
        g = types.SimpleNamespace(key="yugioh", heal_prints=True, card_url=lambda s, n: f"https://x/{s}/{n}")
        for p in (mock.patch.object(printmove.games, "current", lambda: g),
                  mock.patch.object(printmove.games, "load", lambda k: g),
                  mock.patch.object(printmove.games, "mine", lambda k: self.mine),
                  mock.patch.object(printmove.carddb, "path_of", lambda k=None: self.db),
                  mock.patch.object(printmove.carddb, "exists", lambda: True),
                  mock.patch.object(printmove, "DATA", root)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        (self.mine / name).write_text(json.dumps(data, ensure_ascii=False), "utf-8")

    def read(self, name):
        return json.loads((self.mine / name).read_text("utf-8"))

    def test_moves_to_english_print_and_keeps_language(self):
        items = [item("dabl-jp001", "Ash Blossom & Joyous Spring", "DABL", "JP001", lang="ja"),
                 item("dabl-jp001-sr", "Ash Blossom & Joyous Spring", "DABL", "JP001-SR", plang="ja"),
                 item("dabl-sp001-ur", "Ash Blossom & Joyous Spring", "DABL", "SP001-UR", lang="es"),   # no UR in EN
                 item("rc04-kr001", "Ash Blossom & Joyous Spring", "RC04", "KR001"),   # set not in EN: first print
                 item("lob-en001", "Blue-Eyes White Dragon", "LOB", "EN001", lang="de")]   # still there
        self.write("collection.json", {"items": items, "hidden": ["dabl-jp001_0"]})
        self.write("binders.json", {"binders": [{"id": "b1", "name": "Ash Blossom & Joyous Spring",
                                                 "slots": [{"sid": "dabl-jp001"}, {"sid": "lob-en001"}]}]})
        self.write("sessions/s.json", {"id": "s", "packs": [{"cards": [dict(items[0])]}]})
        self.assertEqual(printmove.heal(), 6)
        got = self.read("collection.json")
        self.assertEqual([(i["id"], i["set"], i["number"], i.get("lang")) for i in got["items"]], [
            ("dabl-en001_0", "DABL", "EN001", "ja"), ("dabl-en001-sr_0", "DABL", "EN001-SR", "ja"),
            ("dabl-en001_0", "DABL", "EN001", "es"), ("dabl-en001_0", "DABL", "EN001", "ko"),
            ("lob-en001_0", "LOB", "EN001", "de")])
        self.assertEqual(sum(i["count"] for i in got["items"]), 5)
        self.assertNotIn("plang", got["items"][1])
        self.assertTrue(got["items"][0]["img"].endswith("/dabl/EN001_0.jpg"))   # folder of the open game
        self.assertEqual(got["hidden"], ["dabl-en001_0"])
        binder = self.read("binders.json")["binders"][0]
        self.assertEqual(binder["id"], "b1")   # named like a card, but not a card entry
        self.assertEqual([s["sid"] for s in binder["slots"]], ["dabl-en001", "lob-en001"])
        self.assertEqual(self.read("sessions/s.json")["packs"][0]["cards"][0]["id"], "dabl-en001_0")
        backups = list((pathlib.Path(self.tmp.name) / "backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads((backups[0] / "my-data" / "collection.json").read_text("utf-8"))["items"][0]["id"],
                         "dabl-jp001_0")
        self.assertEqual(printmove.heal(), 0)   # once per database build

    def test_unknown_card_stays(self):
        items = [item("sdk-kr002", "Gone Forever Dragon", "SDK", "KR002", lang="ko")]
        self.write("collection.json", {"items": items})
        self.assertEqual(printmove.heal(), 0)
        self.assertEqual(self.read("collection.json")["items"], items)
        self.assertFalse((pathlib.Path(self.tmp.name) / "backups").exists())

    def test_other_games_untouched(self):
        self.write("collection.json", {"items": [item("dabl-jp001", "Ash Blossom & Joyous Spring", "DABL", "JP001")]})
        g = types.SimpleNamespace(key="pokemon", heal_prints=False)
        with mock.patch.object(printmove.games, "current", lambda: g):
            self.assertEqual(printmove.heal(), 0)
        self.assertEqual(self.read("collection.json")["items"][0]["id"], "dabl-jp001_0")


def add_locale(path):
    """The merged prints (games/yugioh.merge_extra): JP/SP prints of Ash Blossom, a JP print of another card on the
    same number, an AE print – and the passcodes (oracle_id) that tie them to their card."""
    con = sqlite3.connect(path)
    cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
    con.execute("UPDATE cards SET oracle_id = '14558127' WHERE name LIKE 'Ash Blossom%'")
    con.execute("UPDATE cards SET oracle_id = '89631139' WHERE name = 'Blue-Eyes White Dragon'")
    rows = [dict(id="dabl-jp001", name="Ash Blossom & Joyous Spring", oracle_id="14558127", set_code="dabl",
                 number="JP001", lang="ja"),
            dict(id="dabl-sp001", name="Ash Blossom & Joyous Spring", oracle_id="14558127", set_code="dabl",
                 number="SP001", lang="es"),
            dict(id="lob-jp001", name="Dark Magician", oracle_id="46986414", set_code="lob", number="JP001", lang="ja"),
            dict(id="rc04-ae001", name="Ash Blossom & Joyous Spring", oracle_id="14558127", set_code="rc04",
                 number="AE001", lang="en")]
    con.executemany(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [tuple(dict(r, layout="normal", booster=1, rarity="common").get(c) for c in cols) for r in rows])
    con.execute("CREATE TABLE locale_ids (id TEXT PRIMARY KEY) WITHOUT ROWID")
    con.executemany("INSERT INTO locale_ids VALUES (?)", [(r["id"],) for r in rows])
    con.execute("INSERT OR REPLACE INTO meta VALUES ('locale_merged', 'abc')")
    con.commit()
    con.close()


class PrintMoveBack(PrintMove):
    """The prints are back (ygo-locale.sqlite merged): entries return to them – only to a print of the same card."""

    def test_back_by_from_print_rule_and_backup(self):
        items = [item("dabl-en001", "Ash Blossom & Joyous Spring", "DABL", "EN001", lang="en",
                      from_print="rc04-ae001", uid="a"),                                 # AE: only via from_print
                 item("dabl-en001", "Ash Blossom & Joyous Spring", "DABL", "EN001", lang="ja", uid="b"),   # rule
                 item("dabl-en001", "Ash Blossom & Joyous Spring", "DABL", "EN001", lang="en", uid="c"),   # stays
                 item("lob-en001", "Blue-Eyes White Dragon", "LOB", "EN001", lang="ja", uid="d"),   # LOB-JP001 is
                 item("mp22-en257", "Ash Blossom & Joyous Spring", "MP22", "EN257", lang="es", uid="e"),   # another card
                 item("dabl-en001", "Ash Blossom & Joyous Spring", "DABL", "EN001", lang="en", uid="f")]   # backup
        self.write("collection.json", {"items": items})
        old = pathlib.Path(self.tmp.name) / "backups" / "before-print-move-yugioh-2026-10-30_08-00-00" / "my-data"
        old.mkdir(parents=True)
        (old / "collection.json").write_text(json.dumps({"items": [
            item("dabl-sp001", "Ash Blossom & Joyous Spring", "DABL", "SP001", lang="en", uid="f")]}), "utf-8")
        add_locale(self.db)
        self.assertEqual(printmove.heal(), 3)
        got = {i["uid"]: (i["id"], i["number"], i.get("lang"), "from_print" in i)
               for i in self.read("collection.json")["items"]}
        self.assertEqual(got, {"a": ("rc04-ae001_0", "AE001", "en", False), "b": ("dabl-jp001_0", "JP001", "ja", False),
                               "c": ("dabl-en001_0", "EN001", "en", False), "d": ("lob-en001_0", "EN001", "ja", False),
                               "e": ("mp22-en257_0", "EN257", "es", False), "f": ("dabl-sp001_0", "SP001", "en", False)})
        self.assertEqual(printmove.heal(), 0)   # once per database state

    def test_away_keeps_from_print(self):
        self.write("collection.json", {"items": [item("dabl-kr001", "Ash Blossom & Joyous Spring", "DABL", "KR001")]})
        self.assertEqual(printmove.heal(), 1)
        it = self.read("collection.json")["items"][0]
        self.assertEqual((it["id"], it["lang"], it["from_print"]), ("dabl-en001_0", "ko", "dabl-kr001"))


if __name__ == "__main__":
    unittest.main()
