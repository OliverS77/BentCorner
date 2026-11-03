"""Advanced search for Magic, Pokémon and Yu-Gi-Oh!: every section filters exactly what it says
(carddb._filters through carddb.matching_ids) – with each game's own columns (Lorcana: tests/test_lorcana.py).

    python -m unittest tests/test_search_filters.py
"""
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

import games
from cards import carddb
from games import mtg, pokemon, yugioh


def card(cid, name, type_line, **kw):
    legal = kw.pop("legal", ())
    return dict({"id": cid, "name": name, "lang": "en", "set_code": kw.pop("set_code", "tst"), "number": cid,
                 "type_line": type_line, "oracle_text": "", "keywords": "", "colors": "", "color_identity": "",
                 "rarity": "common", "layout": "normal", "booster": 1, "finishes": "nonfoil", "promo_types": "",
                 "frame_effects": "", "legalities": json.dumps({f: "legal" for f in legal})}, **kw)


class _GameDB(unittest.TestCase):
    GAME = None
    ROWS = ()

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = pathlib.Path(cls.tmp.name) / "cards.sqlite"
        con = sqlite3.connect(cls.db)
        con.executescript(carddb.SCHEMA)
        cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
        con.executemany(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [tuple(r.get(c) for c in cols) for r in cls.ROWS])
        con.executescript(carddb.INDEXES)
        con.commit()
        con.close()
        cls.patches = [mock.patch.object(carddb, "DB_PATH", cls.db), mock.patch.object(games, "_current", cls.GAME)]
        for p in cls.patches:
            p.start()
        carddb._upgrade_checked.add(cls.db)

    @classmethod
    def tearDownClass(cls):
        for p in cls.patches:
            p.stop()
        carddb._upgrade_checked.discard(cls.db)
        cls.tmp.cleanup()

    def ids(self, text="", **f):
        return set(carddb.matching_ids(text, **f))


class MagicSearch(_GameDB):
    GAME = mtg.GAME
    ROWS = (
        card("m1", "Llanowar Elves", "Creature — Elf Druid", colors="G", color_identity="G", cmc=1, power="1",
             toughness="1", oracle_text="{T}: Add {G}.", legal=("standard", "modern"), rarity="common"),
        card("m2", "Serra Angel", "Creature — Angel", colors="W", cmc=5, power="4", toughness="4",
             keywords="Flying, Vigilance", legal=("modern",), rarity="uncommon"),
        card("m3", "Niv-Mizzet, Parun", "Legendary Creature — Dragon Wizard", colors="UR", cmc=6, power="5",
             toughness="5", keywords="Flying", legal=("modern",), rarity="rare"),
        card("m4", "Lightning Bolt", "Instant", colors="R", cmc=1, oracle_text="deals 3 damage", legal=("modern",)),
        card("m5", "Sol Ring", "Artifact", cmc=1, legal=("commander",), rarity="uncommon"),
    )

    def test_colors(self):
        self.assertEqual(self.ids(colors="R"), {"m3", "m4"})
        self.assertEqual(self.ids(colors="R", color_mode="exact"), {"m4"})
        self.assertEqual(self.ids(colors="UR", color_mode="exact"), {"m3"})

    def test_types_supertypes_subtypes_keywords(self):
        self.assertEqual(self.ids(types=["Creature"]), {"m1", "m2", "m3"})
        self.assertEqual(self.ids(supertypes=["Legendary"]), {"m3"})
        self.assertEqual(self.ids(subtypes=["Elf"]), {"m1"})
        self.assertEqual(self.ids(keywords=["Flying"]), {"m2", "m3"})
        self.assertEqual(self.ids(types=["Creature"], not_keywords=["Flying"]), {"m1"})

    def test_values_rarity_format_text(self):
        self.assertEqual(self.ids(ranges={"mv": (5, None)}), {"m2", "m3"})
        self.assertEqual(self.ids(ranges={"pow": (4, 4)}), {"m2"})
        self.assertEqual(self.ids(rarities=["uncommon"]), {"m2", "m5"})
        self.assertEqual(self.ids(formats=["standard"]), {"m1"})
        self.assertEqual(self.ids(texts=[("oracle", "damage", False)]), {"m4"})


class PokemonSearch(_GameDB):
    GAME = pokemon.GAME
    ROWS = (
        card("p1", "Pikachu", "Pokémon — Basic — Lightning", colors="L", power="70", cmc=1, promo_types="G",
             legal=("standard", "expanded")),
        card("p2", "Charizard ex", "Pokémon — Stage2 — Fire", colors="R", power="330", cmc=2, promo_types="H",
             keywords="ex", legal=("standard", "expanded")),
        card("p3", "Professor's Research", "Trainer — Supporter", promo_types="", legal=("expanded",)),
        card("p4", "Basic Fire Energy", "Energy — Normal", colors="R", legal=("standard", "expanded")),
    )

    def test_types_stage_energy(self):
        self.assertEqual(self.ids(types=["Trainer"]), {"p3"})
        self.assertEqual(self.ids(supertypes=["Stage2"]), {"p2"})
        self.assertEqual(self.ids(supertypes=["Supporter"]), {"p3"})
        self.assertEqual(self.ids(colors="R"), {"p2", "p4"})

    def test_regulation_marks(self):
        self.assertEqual(self.ids(regulation=["H"]), {"p2"})
        self.assertEqual(self.ids(regulation=["G", "H"]), {"p1", "p2"})
        self.assertEqual(self.ids(regulation=["-"]), {"p3", "p4"})          # cards without a mark
        self.assertEqual(self.ids(not_regulation=["G", "-"]), {"p2"})

    def test_hp_retreat_format(self):
        self.assertEqual(self.ids(ranges={"pow": (100, None)}), {"p2"})     # HP
        self.assertEqual(self.ids(ranges={"mv": (2, 2)}), {"p2"})           # retreat cost
        self.assertEqual(self.ids(formats=["standard"]), {"p1", "p2", "p4"})


class YugiohSearch(_GameDB):
    GAME = yugioh.GAME
    ROWS = (
        card("y1", "Blue-Eyes White Dragon", "Monster — Normal — Dragon", colors="L", power="3000", toughness="2500",
             cmc=8, keywords="Blue-Eyes"),
        card("y2", "Ash Blossom & Joyous Spring", "Monster — Effect — Tuner — Zombie", colors="F", power="0",
             toughness="1800", cmc=3),
        card("y3", "Accesscode Talker", "Monster — Effect — Link — Cyberse", colors="D", power="2300", cmc=4),
        card("y4", "Pot of Prosperity", "Spell — Normal"),
        card("y5", "Infinite Impermanence", "Trap — Normal"),
    )

    def test_kind_frame_attribute_archetype(self):
        self.assertEqual(self.ids(types=["Monster"]), {"y1", "y2", "y3"})
        self.assertEqual(self.ids(types=["Spell", "Trap"]), {"y4", "y5"})
        self.assertEqual(self.ids(supertypes=["Tuner"]), {"y2"})
        self.assertEqual(self.ids(supertypes=["Link"]), {"y3"})
        self.assertEqual(self.ids(colors="L"), {"y1"})                      # attribute LIGHT
        self.assertEqual(self.ids(keywords=["Blue-Eyes"]), {"y1"})          # archetype

    def test_atk_def_level(self):
        self.assertEqual(self.ids(ranges={"pow": (2500, None)}), {"y1"})
        self.assertEqual(self.ids(ranges={"tou": (1800, 1800)}), {"y2"})
        self.assertEqual(self.ids(ranges={"mv": (7, None)}), {"y1"})


if __name__ == "__main__":
    unittest.main()
