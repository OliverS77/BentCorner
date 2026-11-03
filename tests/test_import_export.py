"""Import/export round trip: collection → file (ManaBox, Moxfield, Excel, Deckbox, text) → import → same state;
deck → text → deck; foreign deck lists (Moxfield/Arena, Archidekt, Pokémon TCG Live, Yu-Gi-Oh!) parse as expected.
Known, intended losses are tested as such (Moxfield/Deckbox have no Scryfall ID, Moxfield merges two conditions).

    python -m unittest tests/test_import_export.py
"""
import pathlib
import tempfile
import unittest

from collection import collection as coll
from collection import decks, trade

GROUPS = [
    {"count": 4, "name": "Lightning Bolt", "set": "2x2", "number": "117", "lang": "en", "foil": False,
     "rarity": "uncommon", "sid": "11111111-aaaa-4bbb-8ccc-000000000001", "cond": "near_mint", "eur": 1.5},
    {"count": 1, "name": "Sol Ring", "set": "c21", "number": "263", "lang": "de", "foil": True, "rarity": "uncommon",
     "sid": "11111111-aaaa-4bbb-8ccc-000000000002", "cond": "excellent", "eur_foil": 3.25},
    {"count": 2, "name": "Ragavan, Nimble Pilferer", "set": "mh2", "number": "138", "lang": "ja", "foil": False,
     "rarity": "mythic", "sid": "11111111-aaaa-4bbb-8ccc-000000000003", "cond": "light_played", "eur": 40.0},
    {"count": 1, "name": "Fire // Ice", "set": "mh2", "number": "290★", "lang": "fr", "foil": True, "rarity": "rare",
     "sid": "11111111-aaaa-4bbb-8ccc-000000000004", "cond": "poor"},
]


def core(row):
    """[set, nr, lang, foil, n, name, …] -> the part every format must keep."""
    return tuple(row[:6])


def expected(groups):
    return [(g["set"].lower(), g["number"], g["lang"], 1 if g["foil"] else 0, g["count"], g["name"]) for g in groups]


class CollectionRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def through(self, export, name):
        path = self.dir / name
        export(GROUPS, path)
        return trade.read_file(path)

    def test_manabox_keeps_everything(self):
        got = self.through(lambda g, p: coll.export_csv(g, p, "manabox"), "c.csv")
        self.assertEqual(got["kind"], "csv")
        rows = got["data"]
        self.assertEqual([core(r) for r in rows], expected(GROUPS))
        self.assertEqual([r[6] for r in rows], [g["sid"] for g in GROUPS])                # exact printing
        self.assertEqual([r[7] if len(r) > 7 else "near_mint" for r in rows], [g["cond"] for g in GROUPS])

    def test_excel_keeps_everything(self):
        rows = self.through(lambda g, p: coll.export_csv(g, p, "excel"), "c.csv")["data"]
        self.assertEqual([core(r) for r in rows], expected(GROUPS))
        self.assertEqual([r[6] for r in rows], [g["sid"] for g in GROUPS])

    def test_moxfield_without_id(self):
        rows = self.through(lambda g, p: coll.export_csv(g, p, "moxfield"), "c.csv")["data"]
        self.assertEqual([core(r) for r in rows], expected(GROUPS))
        # Moxfield's scale is coarser: Excellent and Good both become "Lightly Played" -> Excellent on import
        conds = [r[7] if len(r) > 7 else "near_mint" for r in rows]
        self.assertEqual(conds, ["near_mint", "excellent", "light_played", "poor"])

    def test_deckbox(self):
        rows = self.through(trade.export_deckbox, "c.csv")["data"]
        self.assertEqual([core(r) for r in rows], expected(GROUPS))

    def test_text_list(self):
        got = self.through(trade.export_text, "c.txt")
        self.assertEqual(got["kind"], "text")
        # a text list knows no language: everything comes back as English (intended – Arena/MTGO format)
        self.assertEqual([core(r) for r in got["data"]],
                         [(s, n, "en", f, c, name) for s, n, _l, f, c, name in expected(GROUPS)])

    def test_semicolon_and_sep_hint(self):
        text = "sep=;\nAnzahl;Name;Set;Nummer;Sprache;Foil\n3;Opt;eld;59;Deutsch;ja\n"
        self.assertEqual([core(r) for r in trade.parse_csv(text)], [("eld", "59", "de", 1, 3, "Opt")])

    def test_unknown_format(self):
        p = self.dir / "x.bin"
        p.write_bytes(b"\x00\x01 nothing")
        with self.assertRaises(ValueError):
            trade.read_file(p)


ROWS = {
    "cmd": {"id": "cmd", "name": "Atraxa, Praetors' Voice", "set_code": "cm2", "number": "10"},
    "a": {"id": "a", "name": "Sol Ring", "set_code": "c21", "number": "263"},
    "b": {"id": "b", "name": "Arcane Signet", "set_code": "cmr", "number": "297"},
    "s": {"id": "s", "name": "Swords to Plowshares", "set_code": "sta", "number": "10"},
    "m": {"id": "m", "name": "Cyclonic Rift", "set_code": "rtr", "number": "35"},
}


DECK = {"commanders": ["cmd"], "cards": [{"sid": "a", "count": 1, "board": "main"},
                                         {"sid": "b", "count": 1, "board": "main"},
                                         {"sid": "s", "count": 2, "board": "side"},
                                         {"sid": "m", "count": 1, "board": "maybe"}]}


class DeckRoundTrip(unittest.TestCase):
    def test_text_round_trip(self):
        parsed = decks.parse_text(decks.to_text(DECK, ROWS))
        self.assertEqual(sorted((n, name, board) for n, name, _s, _nr, board in parsed), sorted([
            (1, "Atraxa, Praetors' Voice", "commander"), (1, "Sol Ring", "main"), (1, "Arcane Signet", "main"),
            (2, "Swords to Plowshares", "side"), (1, "Cyclonic Rift", "maybe")]))
        self.assertEqual(sorted((name, s, nr) for _n, name, s, nr, board in parsed if board != "commander"),
                         [("Arcane Signet", "cmr", "297"), ("Cyclonic Rift", "rtr", "35"), ("Sol Ring", "c21", "263"),
                          ("Swords to Plowshares", "sta", "10")])

    def test_commander_printing_survives(self):   # until 2026-10-26 the commander lost its printing
        parsed = decks.parse_text(decks.to_text(DECK, ROWS))
        self.assertIn((1, "Atraxa, Praetors' Voice", "cm2", "10", "commander"), parsed)

    def test_moxfield_arena_text(self):
        text = "Commander\n1 Atraxa, Praetors' Voice (CM2) 10\n\nDeck\n1x Sol Ring (C21) 263 *F*\n1 Arcane Signet\n" \
               "\nSideboard\n2 Swords to Plowshares (STA) 10"
        self.assertEqual(decks.parse_text(text), [
            (1, "Atraxa, Praetors' Voice", "cm2", "10", "commander"), (1, "Sol Ring", "c21", "263", "main"),
            (1, "Arcane Signet", "", "", "main"), (2, "Swords to Plowshares", "sta", "10", "side")])

    def test_archidekt_tags(self):
        text = "1x Sol Ring (c21) 263 [Ramp] ^Have,#37d67a^\n1x Atraxa, Praetors' Voice (cm2) 10 [Commander{top}]\n" \
               "1x Cyclonic Rift [Maybeboard{noDeck}]\n2x Swords to Plowshares [Sideboard]"
        boards = {name: board for _, name, _, _, board in decks.parse_text(text)}
        self.assertEqual(boards, {"Sol Ring": "main", "Atraxa, Praetors' Voice": "commander",
                                  "Cyclonic Rift": "maybe", "Swords to Plowshares": "side"})

    def test_pokemon_tcg_live(self):
        text = "Pokémon: 8\n4 Pikachu ex OBF 63\n4 Raichu SVI 51\n\nTrainer: 32\n4 Professor's Research SVI 189\n" \
               "\nEnergy: 20\n20 Basic Lightning Energy SVE 4\n\nTotal Cards: 60"
        parsed = decks.parse_text(text)
        self.assertEqual(sum(n for n, *_ in parsed), 32)   # headings are skipped, counts kept
        # set + number without brackets stay in the name; the import strips them by _TRAILING_PRINT
        names = [decks._TRAILING_PRINT.match(n).group(1) for _, n, *_ in parsed]
        self.assertEqual(names, ["Pikachu ex", "Raichu", "Professor's Research", "Basic Lightning Energy"])
        # … and their abbreviation + number lead to the exact printing (set_ext.abbr, carddb.set_by_abbr)
        self.assertEqual([decks._TRAILING_PRINT.match(n).group(2, 3) for _, n, *_ in parsed][:2],
                         [("OBF", "63"), ("SVI", "51")])

    def test_one_piece_simulator_list(self):
        # simulator lists: "4xOP01-016" – the card ID stands in for the name (looked up by ID)
        text = "1xOP01-001\n4xOP01-016\n4xop05-118_p1\n3x Island\n1 Xenagos, God of Revels"
        self.assertEqual(decks.parse_text(text), [
            (1, "OP01-001", "", "", "main"), (4, "OP01-016", "", "", "main"), (4, "OP05-118_p1", "", "", "main"),
            (3, "Island", "", "", "main"), (1, "Xenagos, God of Revels", "", "", "main")])

    def test_yugioh_list(self):
        text = "Main Deck\n3 Ash Blossom & Joyous Spring\n2 Pot of Prosperity\n\nExtra Deck\n1 Accesscode Talker\n" \
               "\nSide Deck\n2 Nibiru, the Primal Being"
        self.assertEqual(decks.parse_text(text), [
            (3, "Ash Blossom & Joyous Spring", "", "", "main"), (2, "Pot of Prosperity", "", "", "main"),
            (1, "Accesscode Talker", "", "", "main"), (2, "Nibiru, the Primal Being", "", "", "side")])


class CollectionTextList(unittest.TestCase):
    """Text list as a collection/wishlist (trade.parse_text) reads lines like deck lists (decks.parse_text) – until
    .21 it had its own pattern: Lorcana "(1) 5" and simulator lists "4xAB01-016" went in as a deck but not as a collection."""

    def test_same_lines_as_deck_lists(self):
        text = ("Deck\n4 Lightning Bolt (2X2) 117\n1 Sol Ring (C21) 263 *F*\n4 Hades - King of Olympus (1) 5\n"
                "4xOP01-016\n2x Swords to Plowshares [Removal] ^Have,#37d67a^\nmy notes\n\nSideboard\n3 Be Prepared")
        self.assertEqual(trade.parse_text(text), [
            ["2x2", "117", "en", 0, 4, "Lightning Bolt"], ["c21", "263", "en", 1, 1, "Sol Ring"],
            ["1", "5", "en", 0, 4, "Hades - King of Olympus"], ["", "", "en", 0, 4, "", "OP01-016"],
            ["", "", "en", 0, 2, "Swords to Plowshares"], ["", "", "en", 0, 3, "Be Prepared"]])

    def test_plain_text_is_no_card_list(self):
        self.assertEqual(trade.parse_text("just some text\nwithout counts"), [])

    def test_id_line_shown_when_missing(self):
        from ui import importview
        self.assertEqual(importview._missing(["", "", "en", 0, 4, "", "OP01-016"], "x")["name"], "OP01-016")


if __name__ == "__main__":
    unittest.main()
