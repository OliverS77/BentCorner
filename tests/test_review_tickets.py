"""Review 08.11.2026 (Prüfkette Schritt 1, library's area): tickets from outside – image, photo, mailbox.
T1/T2: the game and the ids become parts of file paths – only known games and short tokens; T5: a profile-ID prefix
only from the pixel code's length on; T6: counts, lengths, amounts in range; T4: a trade is never taken over by a
sender who isn't its partner. In memory; no image, no network.

    python -m unittest tests/test_review_tickets.py
"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from collection import offers, ticket

ME, FRIEND = "a1b2c3d4e5f6a7b8", "f0e1d2c3b4a5f6e7"


def good():
    return {"v": 1, "id": "ab12cd34", "t": 1, "f": [FRIEND, "Alex"], "o": [ME, "Oli"],
            "a": [["neo", "12", "en", 0, 2, "Card"]], "b": [], "x": "ab12cd34", "n": 1, "k": "o", "m": 0, "g": "mtg"}


class ValidTest(unittest.TestCase):
    def test_a_normal_ticket(self):
        self.assertTrue(ticket.valid(good()))

    def test_game_is_never_a_path(self):
        for g in ("//attacker/share", "C:/Windows", "../../x", "mtg/../../x", "\\\\host\\s"):
            t = good()
            t["g"] = g
            self.assertFalse(ticket.valid(t), g)
            t = good()
            t["a"][0] += ["", g]
            self.assertFalse(ticket.valid(t), "card game " + g)

    def test_ids_are_short_tokens(self):
        for bad in ("../x", "a/b", "x" * 41, "", "a b"):
            t = good()
            t["id"] = bad
            self.assertFalse(ticket.valid(t), bad)
            t = good()
            t["x"] = bad
            self.assertFalse(ticket.valid(t), "x " + bad)

    def test_counts_lengths_amounts(self):
        for change in (lambda t: t["a"][0].__setitem__(4, 10 ** 9), lambda t: t["a"][0].__setitem__(4, 0),
                       lambda t: t["a"][0].__setitem__(5, "n" * 201), lambda t: t["f"].__setitem__(1, "N" * 81),
                       lambda t: t["a"][0].__setitem__(1, "../1"), lambda t: t.__setitem__("m", 10 ** 12),
                       lambda t: t.__setitem__("n", "1"), lambda t: t.__setitem__("a", [["neo", "1", "en", 0, 1]] * 2001),
                       lambda t: t.__setitem__("f", ["x"]), lambda t: t["a"][0].__setitem__(3, "x" * 10 ** 6),
                       lambda t: t["a"][0].__setitem__(3, 7)):
            t = copy.deepcopy(good())
            change(t)
            self.assertFalse(ticket.valid(t))

    def test_short_profile_prefix_is_no_match(self):
        t = good()
        t["o"] = [ME[:1], "Oli"]
        self.assertIsNone(ticket.side(t, ME))                  # „a“ is nobody (T5)
        t["o"] = [ME[:ticket.ID_LEN], "Oli"]
        self.assertIsNotNone(ticket.side(t, ME))               # the pixel code's prefix still works

    def test_the_pixel_code_form_passes(self):
        # the pixel code carries short profile IDs and no card names (ports 08.11.): still a valid ticket
        import json
        t = ticket.new((ME + "c9", "Oli"), (FRIEND + "d8", "Alex"),
                       [{"set": "neo", "number": "12", "count": 2, "name": "Card", "foil": True}], [], trade_id="ab12cd34")
        pix = ticket._expand(json.loads(json.dumps(ticket._compact(t))))
        self.assertEqual(len(pix["f"][0]), ticket.ID_LEN)
        self.assertTrue(ticket.valid(pix))
        self.assertIsNotNone(ticket.side(pix, FRIEND + "d8"))

    def test_broken_game_list_in_the_pixel_code(self):
        t = good()
        t["ga"] = "oops"
        self.assertEqual(ticket._expand(t)["a"], good()["a"])   # dropped, no crash (T6)


class MarkupTest(unittest.TestCase):
    """T3: no markup in ticket names (they reach rich-text labels); links open only https/mailto."""

    def test_names_without_markup(self):
        for change in (lambda t: t["f"].__setitem__(1, "<a href='file:///C:/'>x</a>"),
                       lambda t: t["o"].__setitem__(1, "a>b"),
                       lambda t: t["a"][0].__setitem__(5, "<img src='http://x/y'>")):
            t = copy.deepcopy(good())
            change(t)
            self.assertFalse(ticket.valid(t))

    def test_links_only_https_or_mail(self):
        root = Path(__file__).resolve().parent.parent / "qml" / "components"
        for name in ("MirrorNode.qml", "DetailView.qml", "OrbitSlider.qml"):
            qml = (root / name).read_text("utf-8")
            for line in qml.splitlines():
                if "onLinkActivated" in line and "openUrlExternally" in line:
                    self.assertIn("/^(https:|mailto:)/i.test(", line, name)


if __name__ == "__main__":
    unittest.main()
