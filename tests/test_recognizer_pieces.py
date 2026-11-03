"""Pieces of the recognizer that work without a camera or GPU: collector numbers (carddb.norm_number), reading the
collector line against the candidates (aiscan.LiveScanner._read_pick, text recognition stubbed), the language vote
(langcheck.vote) and prints with the same image per game (games.<g>.same_image_prints via aiscan.art_group).

    python -m unittest tests/test_recognizer_pieces.py
"""
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

import numpy as np

import games
from cards import carddb
from games import mtg, pokemon, yugioh
from scanner import aiscan
from scanner import langcheck
from scanner import ocrscan


class Numbers(unittest.TestCase):
    def test_norm_number(self):
        for raw, want in (("007", "7"), ("0123a", "123a"), ("EN055", "EN055"), (12, "12"), ("0", "0"), ("000", "0"),
                          ("", "0"), (None, "0"), ("12★", "12★")):
            with self.subTest(raw=raw):
                self.assertEqual(carddb.norm_number(raw), want)

    def test_number_key_sorts_naturally(self):
        nums = ["10", "2", "12a", "001", "12", "EN005", "★", 7]
        self.assertEqual(sorted(nums, key=carddb.number_key), ["★", "001", "2", "EN005", 7, "10", "12", "12a"])

    def test_all_zero_can_stay_empty(self):
        # where "000" must not match a read "0" (hybrid, ocrscan): zero=""
        self.assertEqual(carddb.norm_number("000", ""), "")
        self.assertEqual(carddb.norm_number("007", ""), "7")


def cand(set_code, number, name="Card", cid=None):
    return (0.9, {"id": cid or f"{set_code.lower()}-{number}", "set": set_code, "number": number, "name": name}, 0)


class ReadPick(unittest.TestCase):
    """The collector line read from the card decides among the fingerprint candidates – exactly one must fit."""

    def pick(self, text, near, game=mtg.GAME):
        img = np.zeros((468, 336, 3), np.uint8)
        with mock.patch.object(games, "current", lambda: game), mock.patch.object(ocrscan, "available", lambda: True), \
                mock.patch.object(ocrscan, "_lines", lambda part: [(text, 0.9)]):
            hit = aiscan.LiveScanner._read_pick(img, near)
        return hit[0]["id"] if hit else None

    def test_pokemon_number_over_total(self):
        near = [cand("SV03", "055"), cand("SV03", "125"), cand("SV04", "055", cid="other")]
        self.assertIsNone(self.pick("055/191", near, pokemon.GAME))   # 055 in two sets: not unique
        self.assertEqual(self.pick("125/197", near, pokemon.GAME), "sv03-125")

    def test_yugioh_set_code_in_one_piece(self):
        near = [cand("RA05", "EN085"), cand("LOB", "EN001"), cand("SDK", "EN001")]
        self.assertEqual(self.pick("RA05-EN085", near, yugioh.GAME), "ra05-EN085")
        self.assertIsNone(self.pick("XXXX-EN001", near, yugioh.GAME))   # EN001 in two sets, no set code read

    def test_magic_set_code_and_number(self):
        near = [cand("MKM", "123"), cand("MKM", "12"), cand("OTJ", "123")]
        self.assertEqual(self.pick("R 0123 MKM EN", near), "mkm-123")
        self.assertIsNone(self.pick("nothing readable", near))

    def test_same_print_twice_counts_once(self):
        near = [cand("MKM", "123"), cand("MKM", "123", cid="mkm-123-again")]
        self.assertIn(self.pick("MKM 0123", near), ("mkm-123", "mkm-123-again"))


class LanguageVote(unittest.TestCase):
    def test_vote(self):
        self.assertEqual(langcheck.vote([("de", 90)]), "de")              # one very clear reading
        self.assertEqual(langcheck.vote([("de", 70), ("de", 66)]), "de")  # two agreeing readings
        self.assertIsNone(langcheck.vote([("de", 70), ("fr", 70)]))
        self.assertIsNone(langcheck.vote([]))


def make_db(path, rows):
    path.unlink(missing_ok=True)   # a fresh database per call
    con = sqlite3.connect(path)
    con.executescript(carddb.SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
    con.executemany(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [tuple(r.get(c) for c in cols) for r in rows])
    con.commit()
    con.close()


def row(cid, name, set_code, number, **kw):
    return dict({"id": cid, "name": name, "set_code": set_code, "number": number, "lang": "en", "artist": "A",
                 "finishes": "nonfoil", "img_small": None}, **kw)


class FakeIndex:
    def __init__(self, vectors):
        self.v = {k: np.asarray(v, np.float32) / np.linalg.norm(v) for k, v in vectors.items()}

    def vector(self, cid):
        return self.v.get(cid)


class SameImage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "cards.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def group(self, game, rows, entry, index=None, allow_foil=False):
        make_db(self.db, rows)
        with mock.patch.object(carddb, "DB_PATH", self.db), mock.patch.object(games, "current", lambda: game):
            carddb._upgrade_checked.add(self.db)
            return sorted(r["id"] for r in aiscan.art_group(entry, allow_foil, index))

    def test_magic_same_name_and_artist_foil_only_too(self):
        """Foil-only prints with the same image (prerelease "46s", special foils) are twins as well – never counted
        silently as the regular print (Oliver 2026-10-29)."""
        rows = [row("a", "Bolt", "lea", "1"), row("b", "Bolt", "m10", "2"), row("c", "Bolt", "2x2", "3", artist="B"),
                row("d", "Bolt", "sld", "4", finishes="foil")]
        entry = {"name": "Bolt", "set": "LEA", "number": "1"}
        self.assertEqual(self.group(mtg.GAME, rows, entry), ["a", "b", "d"])
        self.assertEqual(self.group(mtg.GAME, rows, entry, allow_foil=True), ["a", "b", "d"])

    def test_magic_double_faced_by_its_whole_name(self):
        """The entry carries the face's name ("Cecil, Dark Knight"), the database the whole card's."""
        rows = [row("a", "Cecil, Dark Knight // Cecil, Redeemed Paladin", "fin", "380"),
                row("b", "Cecil, Dark Knight // Cecil, Redeemed Paladin", "fin", "525", finishes="foil")]
        entry = {"name": "Cecil, Dark Knight", "set": "FIN", "number": "380"}
        self.assertEqual(self.group(mtg.GAME, rows, entry), ["a", "b"])

    def test_stamp_twins(self):
        twins = aiscan._stamp_twins
        self.assertTrue(twins({"number": "46s", "set_code": "pfin"}, {"number": "46", "set_code": "fin"}))
        self.assertTrue(twins({"number": "92p", "set_code": "pdsk"}, {"number": "92", "set_code": "DSK"}))
        self.assertTrue(twins({"number": "232†", "set_code": "fin"}, {"number": "232", "set_code": "fin"}))
        self.assertFalse(twins({"number": "46", "set_code": "fin"}, {"number": "46", "set_code": "fin"}))   # itself
        self.assertFalse(twins({"number": "380", "set_code": "fin"}, {"number": "525", "set_code": "fin"}))
        self.assertFalse(twins({"number": "46s", "set_code": "pdsk"}, {"number": "46", "set_code": "fin"}))

    def test_yugioh_same_image_file(self):
        rows = [row("lob-en001", "BEWD", "lob", "EN001", img_small="x/89631139.jpg"),
                row("sdk-en001", "BEWD", "sdk", "EN001", img_small="x/89631139.jpg"),
                row("ct13-en008", "BEWD", "ct13", "EN008", img_small="x/89631140.jpg")]   # alternate artwork
        entry = {"name": "BEWD", "set": "LOB", "number": "EN001"}
        self.assertEqual(self.group(yugioh.GAME, rows, entry), ["lob-en001", "sdk-en001"])

    def test_pokemon_fingerprint_and_language_group(self):
        rows = [row("sv03-125", "Charizard ex", "sv03", "125"), row("sv03-223", "Charizard ex", "sv03", "223"),
                row("sv03-999", "Charizard ex", "sv03", "999"),
                row("jp-sv3-066", "Charizard ex", "jp-sv3", "066", lang="ja")]
        index = FakeIndex({"sv03-125_0": [1, 0, 0], "sv03-223_0": [0.99, 0.05, 0],   # same artwork
                           "sv03-999_0": [0, 1, 0],                                   # same artist, other artwork
                           "jp-sv3-066_0": [1, 0, 0]})                                 # same artwork, Japanese
        entry = {"name": "Charizard ex", "set": "SV03", "number": "125"}
        self.assertEqual(self.group(pokemon.GAME, rows, entry, index), ["sv03-125", "sv03-223"])
        self.assertEqual(self.group(pokemon.GAME, rows, entry, None), [])   # no index: no grouping

    def test_no_database_no_group(self):
        with mock.patch.object(carddb, "DB_PATH", self.db / "missing.sqlite"), \
                mock.patch.object(games, "current", lambda: pokemon.GAME):
            self.assertEqual(aiscan.art_group({"name": "x", "set": "a", "number": "1"}), [])


if __name__ == "__main__":
    unittest.main()
