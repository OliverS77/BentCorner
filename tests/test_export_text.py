"""„Mit Kartentext“ in our own CSV (Oliver 05.11., legal's conditions, collection/exporttext.py): the plain export
stays byte for byte as before, the extra columns per game with "Quelle" last, Lorcana without text and source, a game
without columns not at all, the YGOJSON licence for ygo-locale prints, decks as CSV, "Share collection" without rules text for
Lorcana and otherwise only with its source. Only temporary files.

    python -m unittest tests/test_export_text.py
"""
import csv
import hashlib
import io
import pathlib
import tempfile
import unittest

from cards import conditions
from collection import collection as coll
from collection import decks
from collection import exporttext
from collection import trade

GROUPS = [
    {"id": "aaaa-1_0", "sid": "aaaa-1", "name": "Lightning Bolt", "set": "2X2", "number": "117", "lang": "de",
     "foil": True, "rarity": "uncommon", "eur": 0.3, "eur_foil": 1.125, "count": 3, "last": 1700000000.5,
     "cond": "light_played"},
    {"id": "bbbb-2_0", "sid": "bbbb-2", "name": "Kozilek, the Great \"Distortion\"", "set": "ogw", "number": "4",
     "lang": "ja", "foil": False, "rarity": "mythic", "eur": 12.345, "eur_foil": None, "count": 1, "last": 1710000000},
    {"id": "cccc-3_0", "sid": "cccc-3", "name": "Fire; Ice", "set": "MH2", "number": "290", "lang": "zht",
     "foil": False, "rarity": "special", "eur": None, "eur_foil": None, "count": 2, "last": 1720000000,
     "cond": "graded", "grade_by": "PSA", "grade": "10"},
]
SETS = {"2x2": "Double Masters 2022", "mh2": "Modern Horizons 2"}
# sha256 of collection.export_csv(GROUPS, …, SETS) from qtquick 024a88af (before the card text option)
GOLDEN = {"excel": "2408c957fe5b6192b2dad6caca5b0c7d81a40ccf1ab546f86a45b239822edfc4",
          "manabox": "a9def8598757f94523264d32a70adef96c31cce1328288488be586456efc6abb"}
ROWS = {
    "aaaa-1": {"name": "Lightning Bolt", "type_line": "Instant", "mana_cost": "{R}", "cmc": 1.0, "colors": "R",
               "oracle_text": "Lightning Bolt deals 3 damage to any target.", "power": None, "toughness": None,
               "loyalty": None, "set_code": "2x2", "set_name": "Double Masters 2022", "number": "117", "rarity": "uncommon"},
    "bbbb-2": {"name": "Delver of Secrets // Insectile Aberration", "type_line": "Creature — Human Wizard // Creature — Human Insect",
               "mana_cost": "{U}", "cmc": 1.0, "colors": "U", "oracle_text": "At the beginning …\nTransform it.\n// Flying",
               "power": None, "toughness": None, "loyalty": None, "set_code": "ogw", "number": "4", "rarity": "common"},
    "cccc-3": {"name": "Fire; Ice", "type_line": "Instant // Instant", "mana_cost": "{1}{R} // {1}{U}", "cmc": 4.0,
               "colors": "UR", "oracle_text": "Fire deals 2 damage …; // Tap target permanent.", "power": "2",
               "toughness": "3", "loyalty": None, "set_code": "mh2", "number": "290", "rarity": "uncommon"},
}


def read(path):
    raw = pathlib.Path(path).read_bytes()
    return raw, list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))


class ExportText(unittest.TestCase):
    def setUp(self):
        conditions.bind({})
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def export(self, fmt, text=None, name="c.csv"):
        p = self.dir / name
        coll.export_csv(GROUPS, p, fmt, SETS, text)
        return p

    def test_plain_export_is_byte_for_byte_as_before(self):
        for fmt, want in GOLDEN.items():
            self.assertEqual(hashlib.sha256(self.export(fmt).read_bytes()).hexdigest(), want, fmt)

    def test_the_option_never_touches_foreign_formats(self):
        text = {"game": "mtg", "rows": ROWS}
        for fmt in ("manabox", "moxfield"):
            self.assertEqual(self.export(fmt, text, "a.csv").read_bytes(), self.export(fmt, None, "b.csv").read_bytes())

    def test_magic_columns_and_source_last(self):
        _, rows = read(self.export("excel", {"game": "mtg", "rows": ROWS}))
        self.assertEqual(rows[0][12:], ["Typ", "Manakosten", "Manawert", "Farben", "Stärke/Widerstand", "Loyalität",
                                        "Kartentext", "Quelle"])
        bolt = dict(zip(rows[0], rows[1]))
        self.assertEqual((bolt["Typ"], bolt["Manakosten"], bolt["Manawert"], bolt["Farben"]), ("Instant", "{R}", "1", "R"))
        self.assertEqual(bolt["Quelle"], "Daten: Scryfall · Kartentext © Wizards of the Coast")
        self.assertTrue(all(r[-1] == exporttext.SOURCE["mtg"] for r in rows[1:]))   # on every row
        dfc = dict(zip(rows[0], rows[2]))
        self.assertIn(" // ", dfc["Typ"])        # both faces, as the database joins them
        self.assertIn("\n", dfc["Kartentext"])   # line breaks stay inside the cell
        self.assertEqual(dict(zip(rows[0], rows[3]))["Stärke/Widerstand"], "2/3")

    def test_lorcana_only_colour_and_cost_without_source(self):
        rows = {"aaaa-1": {"colors": "AS", "cmc": 5.0, "oracle_text": "secret", "type_line": "Character"}}
        _, out = read(self.export("excel", {"game": "lorcana", "rows": rows}))
        self.assertEqual(out[0][12:], ["Farbe", "Kosten"])
        self.assertEqual(out[1][12:], ["Amber, Sapphire", "5"])
        self.assertNotIn("secret", "".join(sum(out, [])))

    def test_a_game_without_columns_is_left_out(self):
        self.assertFalse(exporttext.allowed("newgame"))
        a = self.export("excel", {"game": "newgame", "rows": ROWS}, "a.csv").read_bytes()
        self.assertEqual(a, self.export("excel", None, "b.csv").read_bytes())   # the plain file, nothing more

    def test_yugioh_attribute_names_and_ygojson_only_for_locale_prints(self):
        rows = {"aaaa-1": {"type_line": "Monster — Effect", "colors": "L", "cmc": 4.0, "power": "1800",
                           "toughness": "1000", "loyalty": None, "oracle_text": "text"},
                "bbbb-2": {"type_line": "Spell — Quick-Play", "colors": "", "cmc": None, "oracle_text": "x"}}
        _, out = read(self.export("excel", {"game": "yugioh", "rows": rows, "locale": {"bbbb-2"}}))
        a, b = dict(zip(out[0], out[1])), dict(zip(out[0], out[2]))
        self.assertEqual((a["Attribut"], a["Stufe/Rang/Link"], a["ATK"], a["DEF"]), ("Licht", "4", "1800", "1000"))
        self.assertEqual(a["Quelle"], "Daten: YGOPRODeck · Kartentext © Konami")
        self.assertEqual(b["Quelle"], "Daten: YGOPRODeck · Kartentext © Konami · Yugipedia via YGOJSON, CC BY-SA 4.0, "
                                      "creativecommons.org/licenses/by-sa/4.0")

    def test_pokemon_hp_and_source(self):
        rows = {"aaaa-1": {"type_line": "Pokémon — Stage 1 — Fire", "power": "120", "colors": "R", "oracle_text": "Burn"}}
        _, out = read(self.export("excel", {"game": "pokemon", "rows": rows}))
        a = dict(zip(out[0], out[1]))
        self.assertEqual((a["KP"], a["Energietyp"], a["Kartentext"]), ("120", "Feuer", "Burn"))
        self.assertTrue(a["Quelle"].startswith("Daten: TCGdex (MIT)"))

    def test_deck_csv_sections_and_text(self):
        deck = {"commanders": ["aaaa-1"], "cards": [{"sid": "cccc-3", "count": 2}, {"sid": "bbbb-2", "count": 1, "board": "side"}]}
        p = self.dir / "d.csv"
        self.assertEqual(decks.to_csv(deck, ROWS, p), 3)
        raw, out = read(p)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(out[0], ["Anzahl", "Bereich", "Name", "Set", "Setname", "Nummer", "Seltenheit", "Karten-ID"])
        self.assertEqual([r[:3] for r in out[1:]], [["1", "Commander", "Lightning Bolt"], ["2", "Deck", "Fire; Ice"],
                                                    ["1", "Sideboard", "Delver of Secrets // Insectile Aberration"]])
        decks.to_csv(deck, ROWS, p, {"game": "mtg"})
        _, out = read(p)
        self.assertEqual(out[0][-1], "Quelle")
        decks.to_csv(deck, ROWS, p, {"game": "newgame"})
        self.assertEqual(read(p)[1][0][-1], "Karten-ID")   # a game without columns: the plain deck table

    def test_share_collection_rules_text(self):
        p = self.dir / "s.csv"
        trade.export_custom(GROUPS, p, ["name", "type", "text"], ROWS, "mtg")
        out = read(p)[1]
        self.assertEqual(out[0], ["Name", "Typ", "Regeltext", "Quelle"])
        self.assertEqual(out[1][-1], exporttext.SOURCE["mtg"])
        for game in ("lorcana",):   # the private additions' game: in their own private tests
            trade.export_custom(GROUPS, p, ["name", "type", "text"], ROWS, game)
            self.assertEqual(read(p)[1][0], ["Name"], game)
            self.assertNotIn("text", [k for k, _ in trade.columns_for(game)])
        trade.export_custom(GROUPS, p, ["name", "mv"], ROWS, "mtg")   # without rules text: no source column
        self.assertEqual(read(p)[1][0], ["Name", "Manawert"])

    def test_share_collection_wish_rows_only_name_set_count(self):
        p = self.dir / "w.csv"
        wish = dict(GROUPS[0], wish=True, sid="bbbb-2")
        trade.export_custom([GROUPS[0], wish], p, ["count", "name", "set", "lang", "price", "mv", "type", "text"], ROWS, "mtg")
        head, own, w = read(p)[1]
        self.assertEqual(own[-1], exporttext.SOURCE["mtg"])
        self.assertTrue(own[head.index("Regeltext")])
        self.assertEqual(dict(zip(head, w)), {"Anzahl": "3", "Name": "Lightning Bolt", "Set": "2X2", "Sprache": "", "Preis": "",
                                              "Manawert": "", "Typ": "", "Regeltext": "", "Quelle": ""})

    def test_friend_file_wishes_carry_no_card_data(self):
        """The friend file (.bentcorner) holds wish lists – name, count, set, number only, never type or text."""
        data = trade.build_export({"id": "x", "name": "Alex"}, [], "none", [{"name": "Opt", "count": 2, "set": "xln",
                                                                             "number": "65", "oracle_text": "Scry 1."}])
        self.assertEqual(data["w"], [["Opt", 2, "xln", "65"]])

    def test_yugioh_link_rating_empty_not_zero(self):
        rows = {"aaaa-1": {"type_line": "Monster — Link — Cyberse", "colors": "D", "cmc": 0.0, "power": "2300"},
                "bbbb-2": {"type_line": "Monster — Effect", "colors": "D", "cmc": 0.0, "power": "0"}}
        _, out = read(self.export("excel", {"game": "yugioh", "rows": rows}))
        link, lvl0 = dict(zip(out[0], out[1])), dict(zip(out[0], out[2]))
        self.assertEqual(link["Stufe/Rang/Link"], "")
        self.assertEqual(lvl0["Stufe/Rang/Link"], "0")   # a real level 0 stays


if __name__ == "__main__":
    unittest.main()
