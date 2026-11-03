"""The user's rule "if the print isn't certain, ask": aiscan.sure_print turns a hit whose image several prints share
into a print question unless the collector line decides, and carddb.print_likeliness puts the most likely print
first (the image match's pick, matching finish, booster before promo / The List, cheaper, newer).

    python -m unittest tests/test_print_ask.py
"""
import unittest
from unittest import mock

import games
from cards import carddb
from games import mtg, pokemon, yugioh
from scanner import aiscan


def row(cid, set_code, number, **kw):
    return dict({"id": cid, "set_code": set_code, "number": number, "name": "Card", "booster": 1, "finishes":
                 "nonfoil,foil", "promo_types": "", "eur": 1.0, "released": "2020-01-01"}, **kw)


class Likeliness(unittest.TestCase):
    def order(self, rows, **kw):
        with mock.patch.object(games, "current", lambda: mtg.GAME):
            return [r["id"] for r in sorted(rows, key=lambda r: carddb.print_likeliness(r, **kw))]

    def test_pick_first_then_booster_then_cheaper(self):
        rows = [row("promo", "pakh", "97s", promo_types="prerelease,datestamped", finishes="foil", eur=9),
                row("list", "plst", "AKH-97", booster=0), row("expensive", "akh", "97", eur=5),
                row("cheap", "m19", "97", eur=0.5)]
        self.assertEqual(self.order(rows), ["cheap", "expensive", "list", "promo"])
        self.assertEqual(self.order(rows, pick="list_0")[0], "list")   # the image match's pick comes first

    def test_finish_decides_foil_only_prints(self):
        rows = [row("normal", "akh", "97"), row("promo", "pakh", "97s", finishes="foil", booster=1)]
        self.assertEqual(self.order(rows)[0], "normal")
        self.assertEqual(self.order(rows, foil=True)[0], "normal")   # both exist in foil: booster/no promo decides
        rows = [row("normal", "akh", "97", finishes="nonfoil"), row("promo", "pakh", "97s", finishes="foil")]
        self.assertEqual(self.order(rows, foil=True)[0], "promo")

    def test_newer_breaks_ties(self):
        rows = [row("old", "a", "1", released="2001-01-01"), row("new", "b", "1", released="2024-01-01")]
        self.assertEqual(self.order(rows), ["new", "old"])


class SurePrint(unittest.TestCase):
    RES = {"status": "ok", "entry": {"id": "sv03-125_0", "name": "Card", "set": "SV03", "number": "125"},
           "img": None, "box": None, "how": "image"}

    def run_with(self, game, group, twins=False, read=None):
        aiscan._groups.clear()
        with mock.patch.object(games, "current", lambda: game), \
                mock.patch.object(aiscan, "uncertain_prints", lambda entry, index=None: (group, twins)), \
                mock.patch.object(aiscan, "resolve_generic",
                                  lambda *a: (read, " · collector line") if read else (a[3], "")):
            return aiscan.sure_print(None, dict(self.RES))

    def test_one_print_counts(self):
        self.assertEqual(self.run_with(pokemon.GAME, [row("sv03-125", "sv03", "125")])["status"], "ok")

    def test_collector_line_decides(self):
        group = [row("sv03-125", "sv03", "125"), row("sv03-223", "sv03", "223")]
        res = self.run_with(pokemon.GAME, group, read={"id": "sv03-223_0", "name": "Card"})
        self.assertEqual((res["status"], res["entry"]["id"]), ("ok", "sv03-223_0"))

    def test_unreadable_asks_with_the_pick_first(self):
        group = [row("sv03-223", "sv03", "223", eur=0.1), row("sv03-125", "sv03", "125", eur=9)]
        res = self.run_with(pokemon.GAME, group)
        self.assertEqual(res["status"], "ask")
        self.assertEqual(res["cands"][0][0]["id"], "sv03-125")   # the image match's pick, although dearer
        self.assertEqual(res["pick"], "sv03-125_0")

    def test_the_list_always_asks(self):
        group = [row("akh-97", "akh", "97"), row("plst-akh-97", "plst", "AKH-97", booster=0)]
        res = self.run_with(mtg.GAME, group, twins=True, read={"id": "akh-97_0", "name": "Card"})
        self.assertEqual(res["status"], "ask")   # the collector line is the same on both – never decides

    def test_yugioh_asks_too(self):   # the user: rather ask early than load 30 comparison images
        group = [row("lob-en001", "lob", "EN001"), row("sdk-en001", "sdk", "EN001")]
        self.assertEqual(self.run_with(yugioh.GAME, group)["status"], "ask")
