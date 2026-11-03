"""Lorcana collector line (scanner): "5/204 • EN • 1" and the promo forms -> set + number + language as in the database.

    python -m unittest tests/test_lorcana_footer.py
"""
import pathlib
import unittest

from games import lorcana
from games.lorcana import footer_parse

RAW = pathlib.Path(__file__).resolve().parents[1] / "data" / "fp_build" / "lorcana" / "raw"


class Footer(unittest.TestCase):
    def check(self, text, code, number, lang="en"):
        self.assertEqual(footer_parse(text), {"set": code, "number": number, "lang": lang}, text)

    def test_all_shapes(self):
        self.check("5/204 • EN • 1", "1", "5")
        self.check("205/204 • DE • 1", "1", "205", "de")          # Enchanted
        self.check("8/P1 • EN • 1", "p1", "8")                   # promo grouping instead of the set size
        self.check("1/31 • FR • Q1", "q1", "1", "fr")            # Illumineer's Quest
        self.check("1/PD1 • EN • 11", "pd1", "1")
        self.check("1/DIS • IT • 4", "dis", "1", "it")
        self.check("4a/204 • EN • 3", "3", "4a")                 # variants
        self.check("24A/P2 • EN • 7", "p2", "24a")
        self.check("1 TFC • EN • 1/P1", "p1", "1")
        self.check("3/D23 • EN • 2", "d23", "3")

    def test_ocr_noise(self):
        self.check("5/204 · EN · 1", "1", "5")
        self.check("5/204*EN*1", "1", "5")
        self.check("5 / 204 - DE - 1", "1", "5", "de")
        self.check("Alex Accorsi 5/204 • EN • 1", "1", "5")      # artist line read with it
        self.check("5O/204 • EN • 1", "1", "50")                 # O read instead of 0
        self.check("032/204 • EN • 3", "3", "32")
        # seen on the scan bench: the 0 of the set size read as D, the leading 0 of "01/D23" too, "1TFC" without space
        self.check("> Therese Vildefall 1/2D4 · EN · 5", "5", "1")
        self.check("Fedenico Maria Cugliari 1/2D4-EN-8", "8", "1")
        self.check("NicholasKole D1/D23-EN-1", "d23", "1")
        self.check("Illus. Nicholas Kole 1TFC - EN - 1/P1", "p1", "1")
        self.check("4d/204 • EN • 3", "3", "4d")                 # a trailing d stays a variant letter

    def test_no_guessing(self):
        for text in ("", "EN • Q3", "5/204", "5/204 • XX • 1", "Shift 6 (You may pay 6",
                     "AD1/204 • EN • 1",                          # D inside a word: no leading 0
                     "1/D2D • EN • 1"):                           # D only stands for 0 in a set size that starts with a digit
            self.assertIsNone(footer_parse(text), text)

    @unittest.skipUnless(RAW.exists(), "LorcanaJSON raw files not here (tools/build_lorcana_db.py)")
    def test_every_card_of_the_source(self):
        """Every collector line of LorcanaJSON (EN DE FR IT) gives exactly the print's set + number."""
        n = 0
        for lg in lorcana.LANGS:
            f = RAW / f"allCards-{lg}.json.zip"
            if not f.exists():
                continue
            for c in lorcana.read_zip(f.read_bytes())["cards"]:
                if c.get("number") is None:
                    continue
                code, num = lorcana._ident(c)
                got = footer_parse(c["fullIdentifier"])
                self.assertEqual((got or {}).get("set"), code, c["fullIdentifier"])
                self.assertEqual((got or {}).get("number"), num.lstrip("0") or "0", c["fullIdentifier"])
                self.assertEqual((got or {}).get("lang"), lg, c["fullIdentifier"])
                n += 1
        self.assertGreater(n, 10000)


class ReadPick(unittest.TestCase):
    """aiscan._read_pick for games with footer_parse: only an exact set + number hit counts."""

    def pick(self, read, near):
        from unittest import mock
        from scanner import aiscan
        with mock.patch.object(aiscan.games, "current", return_value=lorcana.GAME), \
                mock.patch.object(aiscan.LiveScanner, "read_footer", return_value=read):
            return aiscan.LiveScanner._read_pick(None, near)

    def test_exact_only(self):
        a = {"id": "1-5_0", "set": "1", "number": "5"}
        b = {"id": "1-15_0", "set": "1", "number": "15"}   # "1" and "5" appear in "15" – must not count
        c = {"id": "p1-5_0", "set": "P1", "number": "5"}
        near = [(0.9, b, 0), (0.8, c, 1), (0.7, a, 2)]
        self.assertEqual(self.pick({"set": "1", "number": "5", "lang": "en"}, near), (a, 2))
        self.assertEqual(self.pick({"set": "p1", "number": "5", "lang": "en"}, near), (c, 1))
        self.assertIsNone(self.pick({"set": "2", "number": "5", "lang": "en"}, near))
        self.assertIsNone(self.pick(None, near))


class CutOff(unittest.TestCase):
    """A card held at an angle, partly outside the picture: the collector line starts right at the band's edge – the
    front of the number may be missing ("240/204" -> "40/204", scan bench: Enchanted 9-240, kind "tilted"). No read."""

    def read(self, lines, confirmed=False):
        import numpy as np
        from unittest import mock
        from scanner import aiscan, ocrscan
        card = np.full((978, 700, 3), 200, np.uint8)
        with mock.patch.object(aiscan.games, "current", return_value=lorcana.GAME), \
                mock.patch.object(ocrscan, "available", return_value=True), \
                mock.patch.object(lorcana.GAME, "footer_confirm", return_value=confirmed), \
                mock.patch.object(ocrscan, "_lines", side_effect=[lines, [], []]):   # text only in the normal band
            return aiscan.LiveScanner.read_footer(card)

    def test_line_at_the_edge_is_no_read(self):
        w = 350   # band width at the scanner's working size (0.5 × 700)
        self.assertIsNone(self.read([("Juan Diego Leon", 0.9, 10, 0.037 * w, 12), ("40/204-EN-9", 0.9, 30, 0.034 * w, 12)]))

    def test_line_at_the_edge_counts_when_the_name_confirms(self):
        w = 350
        self.assertEqual(self.read([("240/204-EN-9", 0.9, 30, 0.034 * w, 12)], confirmed=True),
                         {"set": "9", "number": "240", "lang": "en"})

    def test_normal_line_reads(self):
        w = 350
        self.assertEqual(self.read([("Juan Diego Leon", 0.9, 10, 0.109 * w, 12), ("240/204 - EN · 9", 0.9, 30, 0.106 * w, 12)]),
                         {"set": "9", "number": "240", "lang": "en"})

    def test_variant_letter_needs_the_name(self):
        """OCR reads 8 as B: "48/204" -> "4B/204" names the existing variant 3-4b. Only with its name on the card."""
        w = 350
        line = [("4B/204 • EN • 3", 0.9, 30, 0.106 * w, 12)]
        self.assertIsNone(self.read(line))                                     # name doesn't fit: no read, no 3-48
        self.assertEqual(self.read(line, confirmed=True), {"set": "3", "number": "4b", "lang": "en"})
        self.assertEqual(self.read([("48/204 • EN • 3", 0.9, 30, 0.106 * w, 12)]),
                         {"set": "3", "number": "48", "lang": "en"})        # plain number: as before


class Corners(unittest.TestCase):
    """A card held at an angle is a trapezoid. find_card_boxed(corners=True) straightens it by its own four corners
    (the rotated rectangle cuts the corners off); _footer_only uses that only as a second attempt when the first read
    finds no print (scan bench lorcana-footer: + hits, 0 false)."""

    def tilted_frame(self):
        import cv2
        import numpy as np
        card = np.full((978, 700, 3), 230, np.uint8)
        card[900:960, 20:120] = 0   # a mark in the bottom-left corner, where the collector line is
        frame = np.full((720, 1280, 3), 40, np.uint8)
        src = np.float32([[0, 0], [699, 0], [699, 977], [0, 977]])
        dst = np.float32([[530, 150], [790, 130], [810, 560], [490, 580]])   # top narrower: leaning back
        cv2.warpPerspective(card, cv2.getPerspectiveTransform(src, dst), (1280, 720), frame,
                            borderMode=cv2.BORDER_TRANSPARENT)
        return frame, (480, 120, 340, 470)

    def test_corners_keep_the_corner(self):
        from scanner import ocrscan
        frame, rect = self.tilted_frame()
        found = ocrscan.find_card_boxed(frame, rect, corners=True)
        self.assertEqual(len(found), 1)
        img = found[0][0]
        h, w = img.shape[:2]

        def patch(y0, y1, x0, x1):
            return img[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)].mean()
        # every corner is card, not background (the rectangle shows background top left: measured 40 vs 230)
        for y0, x0 in ((0.03, 0.03), (0.03, 0.92), (0.94, 0.92)):
            self.assertGreater(patch(y0, y0 + 0.03, x0, x0 + 0.05), 180, (y0, x0))
        self.assertLess(patch(0.925, 0.98, 0.04, 0.17), 80)   # the mark bottom left, upright

    def run_footer(self, reads):
        """_footer_only with stubbed finding/reading: reads = what read_footer returns, one per call."""
        import numpy as np
        from unittest import mock
        from scanner import aiscan, ocrscan
        live = aiscan.LiveScanner.__new__(aiscan.LiveScanner)
        calls = []

        def find(frame, rect, corners=False):
            calls.append(corners)
            return [(np.zeros((978, 700, 3), np.uint8), (0, 0, 10, 10))]

        rows = {"5": {"name": "Ariel", "set_code": "1", "number": "5"}}
        with mock.patch.object(ocrscan, "find_card_boxed", side_effect=find), \
                mock.patch.object(aiscan.LiveScanner, "read_footer", side_effect=reads), \
                mock.patch.object(aiscan.hybrid, "row_by_print", side_effect=lambda s, n: rows.get(n)), \
                mock.patch("cards.carddb.entry_from_row", side_effect=lambda r: {"id": "1-" + r["number"]}):
            live._footer_only(np.zeros((720, 1280, 3), np.uint8), (0, 0, 100, 140))
            live._foot_job.join(5)
        return calls, live._foot_reads[-1][1]

    def test_second_attempt_only_without_a_print(self):
        hit = {"set": "1", "number": "5", "lang": "en"}
        self.assertEqual(self.run_footer([hit]), ([False], {"id": "1-5", "img_normal": None}))   # read: no 2nd try
        self.assertEqual(self.run_footer([None, hit]), ([False, True], {"id": "1-5", "img_normal": None}))
        self.assertEqual(self.run_footer([{"set": "1", "number": "6", "lang": "en"}, None])[1], None)   # no print


if __name__ == "__main__":
    unittest.main()
