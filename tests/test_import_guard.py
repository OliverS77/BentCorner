"""Import into the wrong game (Oliver, 30.10.2026): a Magic export imported while Yu-Gi-Oh! was open turned "Forest" and
"Mountain" into the YGO field spells of the same name. Now (collection/importguard, ui/importview.resolve):
the file is rated against every game set up here, a line with a set the open game doesn't know is never matched by
its name alone – unless the file as a whole is that game's (a brand-new set) – and a better game is only offered.

    python -m unittest tests/test_import_guard.py
"""
import pathlib
import sqlite3
import tempfile
import types
import unittest
from unittest import mock

from cards import carddb
from collection import decks
from collection import importguard
from ui import importview

MTG = [("one-276", "Forest", "one", "276"), ("one-275", "Mountain", "one", "275"), ("lea-161", "Lightning Bolt", "lea", "161"),
       ("one-1", "Abaddon the Despoiler", "one", "1"), ("one-2", "Atraxa, Grand Unifier", "one", "2")]
YGO = [("ss03-enb17", "Forest", "ss03", "ENB17"), ("ss02-ena14", "Mountain", "ss02", "ENA14"),
       ("lob-001", "Blue-Eyes White Dragon", "lob", "001"), ("lob-005", "Dark Magician", "lob", "005")]


def make_db(path, rows):
    con = sqlite3.connect(path)
    con.executescript(carddb.SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
    con.executemany(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [tuple(dict(id=i, name=n, set_code=s, number=num, lang="en", layout="normal", booster=1,
                                rarity="common", released="2023-01-01").get(c) for c in cols) for i, n, s, num in rows])
    con.executescript(carddb.INDEXES)
    con.commit()
    con.close()


def csv_row(name, set_code="", number="", sid=""):
    """A row as trade.parse_csv makes it: [set, nr, lang, foil, n, name, (Scryfall ID)]."""
    return [set_code, number, "en", 0, 1, name] + ([sid] if sid else [])


class ImportGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.dbs = {"mtg": root / "mtg.sqlite", "yugioh": root / "ygo.sqlite"}
        make_db(self.dbs["mtg"], MTG)
        make_db(self.dbs["yugioh"], YGO)
        self.use("yugioh")
        importguard._index.clear()

    def use(self, key):
        """Open game = key (its database is carddb.DB_PATH)."""
        g = types.SimpleNamespace(key=key, name=key, card_url=lambda s, n: "")
        for p in (mock.patch("games.current", lambda: g),
                  mock.patch("games.choices", lambda: [{"key": k, "ready": True} for k in self.dbs]),
                  mock.patch.object(carddb, "path_of", lambda k=None: self.dbs[k or key]),
                  mock.patch.object(carddb, "DB_PATH", self.dbs[key]),
                  mock.patch.object(carddb, "exists", lambda: True),
                  mock.patch.object(carddb, "_SET_CODES", None)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_magic_file_in_yugioh(self):

        rows = [csv_row("Forest", "one", "276"), csv_row("Mountain", "one", "275"), csv_row("Lightning Bolt", "lea", "161"),
                csv_row("Abaddon the Despoiler", "one", "1")]
        v = importguard.verdict(importview.guard_items(rows))
        self.assertEqual((v["other"], v["other_ok"], v["n"], v["ok"], v["fits"], v["few"]), ("mtg", 4, 4, 0, False, True))
        cards, missing = importview.resolve(rows)
        self.assertEqual(cards, [])   # never the YGO "Forest"/"Mountain"
        self.assertEqual(len(missing), 4)
        self.assertIn("ONE", missing[0]["why"])
        self.assertIn("another game", missing[0]["why"])

    def test_same_game_new_set_by_name(self):
        """A brand-new set the database doesn't know yet: the file is Magic's, so the name alone may decide."""

        self.use("mtg")
        rows = [csv_row("Forest", "one", "276"), csv_row("Mountain", "one", "275"), csv_row("Lightning Bolt", "lea", "161"),
                csv_row("Abaddon the Despoiler", "one", "1"), csv_row("Atraxa, Grand Unifier", "zzz", "9")]
        v = importguard.verdict(importview.guard_items(rows))
        self.assertTrue(v["fits"])
        self.assertIsNone(v["other"])
        cards, missing = importview.resolve(rows, fits=v["fits"])
        self.assertEqual([c[0]["id"] for c in cards][-1], "one-2_0")
        self.assertEqual([c[5] for c in cards], [False, False, False, False, True])   # the last one: "name only"
        self.assertEqual(missing, [])

    def test_text_list_without_sets(self):
        """No sets at all: nothing tells the games apart – names in both count the same, the open game wins."""
        items = [("Forest", "", "", ""), ("Mountain", "", "", "")]
        v = importguard.verdict(items)
        self.assertIsNone(v["other"])
        self.assertTrue(v["fits"])
        v = importguard.verdict(items + [("Lightning Bolt", "", "", ""), ("Atraxa, Grand Unifier", "", "", "")])
        self.assertEqual((v["other"], v["ok"], v["few"]), ("mtg", 2, False))   # 4 of 4 in Magic, 2 of 4 here

    def test_few_found(self):
        v = importguard.verdict([("Blue-Eyes White Dragon", "lob", "001", ""), ("Nope", "lob", "999", ""),
                                 ("Nada", "", "", ""), ("Nix", "", "", "")])
        self.assertEqual((v["ok"], v["n"], v["few"], v["other"], v["fits"]), (1, 4, True, None, False))

    def test_scryfall_id_counts_for_magic(self):
        v = importguard.verdict([("Forest", "", "", "one-276"), ("Mountain", "", "", "one-275")])
        self.assertEqual(v["other"], "mtg")

    def test_deck_import_rule(self):
        """Deck lists (collection/deckcore.import_from): "Forest (ONE) 276" in Yu-Gi-Oh! is not the field spell."""

        parsed = decks.parse_text("20 Forest (ONE) 276\n2 Blue-Eyes White Dragon")
        found = {n: importguard.name_only_ok(s, False) for _, n, s, *_ in parsed}
        self.assertEqual(found, {"Forest": False, "Blue-Eyes White Dragon": True})


if __name__ == "__main__":
    unittest.main()
