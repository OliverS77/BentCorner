"""Disney Lorcana without network: card database from a small LorcanaJSON sample (games.lorcana.build_db), the
advanced search (every section filters what it says), the quick search "name number" / "name set" (Lorcana sets are
numbers too), deck lists in and out (Dreamborn / Inkdecks style, our own export) and the card limits.

    python -m unittest tests/test_lorcana.py
"""
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

import games
from cards import carddb
from collection import decks
from games import lorcana

RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "fp_build" / "lorcana" / "raw"
NOT_CORE = {"Core": {"allowed": False, "allowedUntilDate": "2025-09-05"}, "Infinity": {"allowed": True}}
BOTH = {"Core": {"allowed": True}, "Infinity": {"allowed": True}}
NONE = {"Core": {"allowed": False}, "Infinity": {"allowed": False}}


def lj(cid, set_code, number, name, version=None, type_="Character", color="Amber", cost=3, inkwell=True,
       rarity="Common", formats=None, **kw):
    """A card as in LorcanaJSON's allCards.json (only the fields build_db reads)."""
    c = {"id": cid, "setCode": set_code, "number": number, "name": name, "type": type_, "color": color, "cost": cost,
         "inkwell": inkwell, "rarity": rarity, "fullName": f"{name} - {version}" if version else name,
         "simpleName": (f"{name} {version}" if version else name).lower(), "foilTypes": ["None", "Silver"],
         "allowedInFormats": formats or BOTH, "fullTextSections": [], "artistsText": "Test Artist",
         "images": {"full": f"https://img.test/en/{cid}.jpg", "thumbnail": f"https://img.test/en/{cid}s.jpg"},
         "externalLinks": {"cardmarketId": 1000 + cid, "tcgPlayerId": 2000 + cid}}
    if type_ in ("Character", "Location"):
        c.update(willpower=kw.pop("willpower", 4), lore=kw.pop("lore", 1))
    if type_ == "Character":
        c.update(strength=kw.pop("strength", 2), version=version)
    c.update(kw)
    return c


CARDS = [
    lj(5, "1", 5, "Hades", "King of Olympus", cost=8, inkwell=False, rarity="Rare", formats=NOT_CORE, strength=6,
       willpower=7, subtypes=["Floodborn", "Villain", "King", "Deity"], keywordAbilities=["Shift"],
       fullTextSections=["Shift 6 (You may pay 6 ⬡ to play this on top of\none of your characters named Hades.)"]),
    lj(205, "1", 205, "Hades", "King of Olympus", cost=8, inkwell=False, rarity="Enchanted", formats=NOT_CORE,
       strength=6, willpower=7, subtypes=["Floodborn", "Villain", "King", "Deity"], foilTypes=["Lava"], baseId=5),
    lj(1001, "1", 1, "Mickey Mouse", "Brave Little Tailor", color="Ruby", cost=8, rarity="Special",
       promoGrouping="P1", subtypes=["Dreamborn", "Hero"], keywordAbilities=["Evasive"], lore=4),
    lj(468, "3", 32, "Never Land", "Mermaid Lagoon", type_="Location", cost=1, moveCost=1, willpower=4, lore=1),
    lj(400, "3", 4, "Dalmatian Puppy", "Tail Wagger", variant="a", maxCopiesInDeck=99, subtypes=["Storyborn", "Puppy"]),
    lj(128, "1", 128, "Be Prepared", type_="Action", color="Amethyst", cost=7, subtypes=["Song"],
       fullTextSections=["Banish all characters."]),
    lj(700, "7", 2, "Mulan", "Elite Archer", color="Amber-Steel", colors=["Amber", "Steel"], cost=6,
       subtypes=["Storyborn", "Hero", "Princess"]),
    lj(900, "Q1", 1, "Anna", "Ensnared Sister", color="", inkwell=True, rarity="Special", formats=NONE),
    lj(901, "Q1", None, "Hunny Pot"),                                    # token-like, no number: left out
    lj(300, "3", 100, "The Glass Slipper", type_="Item", color="Sapphire", maxCopiesInDeck=2),
    lj(301, "3", 101, "Microbots", type_="Item", color="Steel", maxCopiesInDeck=None),
    lj(710, "7", 50, "Stitch", "Rock Star", color="Steel", subtypes=["Floodborn", "Hero", "Alien"],
       keywordAbilities=["Shift"]),
]
SETS = {"1": {"name": "The First Chapter", "type": "expansion", "releaseDate": "2023-09-01"},
        "3": {"name": "Into the Inklands", "type": "expansion", "releaseDate": "2024-03-08"},
        "7": {"name": "Archazia's Island", "type": "expansion", "releaseDate": "2025-03-21"},
        "Q1": {"name": "Illumineer's Quest: Deep Trouble", "type": "quest", "releaseDate": "2024-05-31"}}
DE = {"metadata": {"generatedOn": "2026-10-23T11:25:33"},
      "sets": {"1": {"name": "Das Erste Kapitel"}, "3": {"name": "Die Tintenlande"}},
      "cards": [dict(lj(5, "1", 5, "Hades", "König des Olymps", rarity="Selten", color="Bernstein"),
                     images={"full": "https://img.test/de/5.jpg", "thumbnail": "https://img.test/de/5s.jpg"})]}
SAMPLE = {"en": {"metadata": {"generatedOn": "2026-10-16T16:43:42"}, "sets": SETS, "cards": CARDS}, "de": DE}


class _LorcanaDB(unittest.TestCase):
    """A Lorcana database in a temp folder, set as the open game's for the duration of the class."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = pathlib.Path(cls.tmp.name) / "cards.sqlite"
        cls.n = lorcana.build_db(SAMPLE, cls.db)
        cls.patches = [mock.patch.object(carddb, "DB_PATH", cls.db), mock.patch.object(carddb, "REF", cls.db.parent),
                       mock.patch.object(games, "_current", lorcana.GAME)]
        for p in cls.patches:
            p.start()
        carddb._upgrade_checked.add(cls.db)   # no data pack check: this database stays
        carddb._meta_cache.clear()
        carddb._SET_CODES = None
        lorcana.Lorcana._limits = None
        lorcana.Lorcana._img = {}

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        carddb._upgrade_checked.discard(cls.db)
        carddb._SET_CODES = None
        lorcana.Lorcana._limits = None
        cls.tmp.cleanup()

    def ids(self, text="", **f):
        return {i.rpartition("_")[0] if "_" in i else i for i in carddb.matching_ids(text, **f)}

    def row(self, sid):
        return carddb.cards_by_ids([sid])[sid]


class Build(_LorcanaDB):
    def test_prints_and_ids(self):
        self.assertEqual(self.n, 11)   # 12 cards, the one without a number left out
        self.assertEqual(self.ids(), {"1-5", "1-205", "p1-1", "3-32", "3-4a", "1-128", "7-2", "q1-1", "3-100",
                                      "3-101", "7-50"})

    def test_columns(self):
        h = self.row("1-5")
        self.assertEqual((h["name"], h["type_line"], h["cmc"], h["colors"], h["power"], h["toughness"],
                          h["loyalty"], h["frame_effects"], h["keywords"]),
                         ("Hades - King of Olympus", "Character — Floodborn · Villain · King · Deity", 8, "A", "6", "7",
                          "1", "", "Shift"))
        self.assertEqual(h["oracle_text"], "Shift 6 (You may pay 6 {I} to play this on top of one of your characters "
                                           "named Hades.)")   # symbol replaced, printed line break gone
        self.assertEqual(json.loads(h["legalities"]), {"infinity": "legal"})
        loc = self.row("3-32")
        self.assertEqual((loc["layout"], loc["mana_cost"], loc["frame_effects"]), ("landscape", "1", "inkable"))
        self.assertEqual(self.row("7-2")["colors"], "AT")                       # dual ink
        self.assertEqual(self.row("q1-1")["colors"], "")                        # quest: no ink
        self.assertEqual(self.row("1-205")["finishes"], "foil")                 # Enchanted: foil only
        self.assertEqual((self.row("p1-1")["set_name"], self.row("p1-1")["booster"]), ("Promos 1", 0))

    def test_languages_images_limits(self):
        con = sqlite3.connect(self.db)
        try:
            self.assertEqual(con.execute("SELECT name FROM langs WHERE id = '1-5' AND lang = 'de'").fetchone()[0],
                             "Hades - König des Olymps")
            self.assertEqual(dict(con.execute("SELECT sid, copies FROM limits")),
                             {"3-4a": 99, "3-100": 2, "3-101": None})
            self.assertEqual(con.execute("SELECT value FROM meta WHERE key = 'pk_build'").fetchone()[0], lorcana.BUILD)
        finally:
            con.close()
        self.assertEqual(lorcana.GAME.image_url("1", "5", "de"), "https://img.test/de/5.jpg")
        self.assertEqual(lorcana.GAME.image_url("1", "5", "en", "small"), "https://img.test/en/5s.jpg")
        self.assertIsNone(lorcana.GAME.image_url("1", "5", "fr"))               # no French image: none
        self.assertEqual(lorcana.GAME.set_names()["1"], {"en": "The First Chapter", "de": "Das Erste Kapitel"})

    @unittest.skipUnless((RAW / "allCards-en.json.zip").exists(), "LorcanaJSON raw files not here")
    def test_whole_source_plausible(self):
        """The real source (raw files of tools/build_lorcana_db.py): plausible card count, every set, the languages."""
        data = {lg: lorcana.read_zip((RAW / f"allCards-{lg}.json.zip").read_bytes()) for lg in lorcana.LANGS
                if (RAW / f"allCards-{lg}.json.zip").exists()}
        db = pathlib.Path(self.tmp.name) / "full.sqlite"
        n = lorcana.build_db(data, db)
        self.assertGreater(n, 3400)
        con = sqlite3.connect(db)
        try:
            sets = {r[0] for r in con.execute("SELECT DISTINCT set_code FROM cards")}
            self.assertTrue({str(i) for i in range(1, 15)} | {"q1", "p1"} <= sets, sets)
            langs = dict(con.execute("SELECT lang, COUNT(*) FROM langs GROUP BY lang"))
            self.assertEqual(langs["en"], n)
            self.assertGreater(langs["de"], 0.9 * n)
        finally:
            con.close()


class AdvancedSearch(_LorcanaDB):
    """Every section of the advanced search filters exactly what it says (carddb._filters with Lorcana's fields)."""

    def test_ink(self):
        self.assertEqual(self.ids(colors="A"), {"1-5", "1-205", "3-32", "3-4a", "7-2"})
        self.assertEqual(self.ids(colors="AT", color_mode="exact"), {"7-2"})
        self.assertEqual(self.ids(colors="T", color_mode="exact"), {"3-101", "7-50"})
        self.assertNotIn("7-2", self.ids(colors="A", color_mode="exact"))       # dual ink isn't "exactly Amber"

    def test_inkwell_and_traits(self):
        self.assertEqual(self.ids(supertypes=["Inkable"]) | self.ids(not_supertypes=["Inkable"]), self.ids())
        self.assertEqual(self.ids(not_supertypes=["Inkable"]), {"1-5", "1-205"})
        self.assertEqual(self.ids(supertypes=["Song"]), {"1-128"})
        self.assertEqual(self.ids(supertypes=["Floodborn", "Inkable"], supertypes_mode="all"), {"7-50"})

    def test_types_classifications_keywords(self):
        self.assertEqual(self.ids(types=["Location"]), {"3-32"})
        self.assertEqual(self.ids(types=["Item"]), {"3-100", "3-101"})
        self.assertEqual(self.ids(subtypes=["Villain"]), {"1-5", "1-205"})
        self.assertEqual(self.ids(keywords=["Shift"]), {"1-5", "7-50"})
        self.assertEqual(self.ids(not_keywords=["Shift"]) & {"1-5", "7-50"}, set())

    def test_values(self):
        self.assertEqual(self.ids(ranges={"mv": (8, None)}), {"1-5", "1-205", "p1-1"})
        self.assertEqual(self.ids(ranges={"pow": (6, 6)}), {"1-5", "1-205"})
        self.assertEqual(self.ids(ranges={"loy": (4, None)}), {"p1-1"})          # lore
        self.assertEqual(self.ids(ranges={"move": (1, 1)}), {"3-32"})            # move cost (Locations)

    def test_rarity_format_set_text(self):
        self.assertEqual(self.ids(rarities=["enchanted"]), {"1-205"})
        self.assertEqual(self.ids(formats=["core"]) & {"1-5", "1-205", "q1-1"}, set())
        self.assertIn("1-5", self.ids(formats=["infinity"]))
        self.assertEqual(self.ids(set_codes=["p1"]), {"p1-1"})
        self.assertEqual(self.ids(texts=[("oracle", "Banish all", False)]), {"1-128"})

    def test_search_syntax_ink_words(self):
        from ui import searchbox
        for q, want in (("i:amber t:song", set()), ("i:amethyst t:song", {"1-128"}), ("i:bernstein,stahl", {"7-2"}),
                        ("c=steel", {"3-101", "7-50"})):
            crit, rest = searchbox.parse_query(q)
            f = {}
            for key, value, neg, op in crit:
                searchbox.apply_criterion(f, key, value, neg, op)
            got = self.ids(rest, **f)
            self.assertEqual(got & want if q.startswith("i:bernstein") else got, want, q)


class QuickSearch(_LorcanaDB):
    """"Name number" / "name set" – Lorcana sets are numbers too: one number = the card number, two = as printed
    ("5/204 • EN • 1": number, then set)."""

    def split(self, text):
        from ui import searchbox
        searchbox._SET_NAMES["key"] = None   # set names of this database
        return searchbox.split_print_query(text)

    def find(self, text):
        code, num, rest = self.split(text)
        f = dict(**({"set_code": code} if code else {}), **({"number": num} if num else {}))
        return [r["id"] for r in carddb.search(rest, limit=5, **f)]

    def test_name_number(self):
        self.assertEqual(self.split("hades 5"), (None, "5", "hades"))
        self.assertEqual(self.find("hades 5"), ["1-5"])
        self.assertEqual(self.find("hades 205"), ["1-205"])

    def test_name_number_set_as_printed(self):
        self.assertEqual(self.split("hades 5 1"), ("1", "5", "hades"))
        self.assertEqual(self.find("mickey p1 1"), ["p1-1"])
        self.assertEqual(self.find("mickey 1 p1"), ["p1-1"])

    def test_set_names_in_both_languages(self):
        self.assertEqual(self.split("hades the first chapter")[0], "1")
        self.assertEqual(self.split("das erste kapitel hades")[0], "1")
        self.assertEqual(set(self.find("hades das erste kapitel")), {"1-5", "1-205"})


class DeckLists(_LorcanaDB):
    def test_own_export_round_trip(self):
        """Our export ("4 Hades - King of Olympus (1) 5") comes back with the exact print – set codes of one
        character ("1") included."""
        rows = carddb.cards_by_ids(["1-5", "3-4a", "p1-1", "1-128"])
        deck = {"cards": [{"sid": "1-5", "count": 4}, {"sid": "3-4a", "count": 12}, {"sid": "p1-1", "count": 1},
                          {"sid": "1-128", "count": 2, "board": "side"}]}
        parsed = decks.parse_text(decks.to_text(deck, rows))
        self.assertEqual(sorted(parsed), sorted([(4, "Hades - King of Olympus", "1", "5", "main"),
                                                 (12, "Dalmatian Puppy - Tail Wagger", "3", "4a", "main"),
                                                 (1, "Mickey Mouse - Brave Little Tailor", "p1", "1", "main"),
                                                 (2, "Be Prepared", "1", "128", "side")]))

    def test_dreamborn_inkdecks_lists(self):
        """Dreamborn and Inkdecks export "count full name" lines – every name is found in the database."""
        text = "4 Hades - King of Olympus\n4 Mulan - Elite Archer\n2 Be Prepared\n3 The Glass Slipper\n" \
               "10 Microbots\n"
        parsed = decks.parse_text(text)
        self.assertEqual([(n, name) for n, name, *_ in parsed],
                         [(4, "Hades - King of Olympus"), (4, "Mulan - Elite Archer"), (2, "Be Prepared"),
                          (3, "The Glass Slipper"), (10, "Microbots")])
        found = carddb.by_names([name for _, name, *_ in parsed])
        self.assertEqual(len(found), 5, found.keys())

    def test_card_limits_from_the_source(self):
        g = lorcana.GAME
        self.assertTrue(g.deck_unlimited(self.row("3-101")))                       # Microbots: any number
        self.assertEqual(g.deck_copy_limit(self.row("3-100")), 2)                 # The Glass Slipper
        self.assertEqual(g.deck_copy_limit(self.row("3-4a")), 99)                 # Dalmatian Puppy
        self.assertIsNone(g.deck_copy_limit(self.row("1-5")))                     # the usual 4
        self.assertEqual(g.deck_legal_names({"Hades - King of Olympus", "Stitch - Rock Star"}, "core"),
                         {"Stitch - Rock Star"})


class Counters(unittest.TestCase):
    """Scan page / stream counters per game: Lorcana counts Enchanted (+ Iconic, Epic) and Legendary, Magic stays
    Mythic / Rare – stored under the same keys as before."""

    def test_levels(self):
        from games import mtg
        from scanner import core
        cards = [{"rarity": r, "foil": f} for r, f in (("enchanted", 1), ("iconic", 0), ("legendary", 0),
                                                        ("mythic", 1), ("rare", 0), ("common", 0))]
        with mock.patch.object(games, "_current", lorcana.GAME):
            self.assertEqual(core._counts(cards), {"mythic": 2, "rare": 1, "foil": 2})
            self.assertEqual(lorcana.GAME.counter_labels(), ("Enchanted", "Legendary", "Foil"))
        with mock.patch.object(games, "_current", mtg.GAME):
            self.assertEqual(core._counts(cards), {"mythic": 1, "rare": 1, "foil": 2})
            self.assertEqual(mtg.GAME.counter_labels(), ("Mythic", "Rare", "Foil"))


if __name__ == "__main__":
    unittest.main()
