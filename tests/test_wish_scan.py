"""Wish card hit on the scan page + the scan sounds' volume (0.9.9, Oliver via Gordon 14.11.2026, lead's order):
the "wish" sound before all others, level 7 = exactly the sound of before, off stays off, the bar's texts, Undo per
list and "U" afterwards only for the lists still out (lead 14.11.)."""
import unittest

from scanner import scansound
from scanner.wishbar import WishBar
from tests import test_wishhit as tw


class Sound(unittest.TestCase):
    def test_wish_first(self):
        self.assertEqual(scansound.kind_for(80.0, 0.5, wish=True), "wish")
        self.assertEqual(scansound.kind_for(80.0, 0.5), "rare")
        self.assertEqual(scansound.kind_for(1.0, 0.5), "hit")
        self.assertEqual(scansound.kind_for(None, 0.5), "tick")
        self.assertIn("wish", scansound.NOTES)

    def test_level_7_is_the_sound_of_before(self):
        self.assertEqual(scansound.DEFAULT_LEVEL, 7)
        self.assertEqual(scansound.gain(7), 1.0)
        tick = scansound.NOTES["tick"]
        self.assertEqual(scansound._render(tick, scansound.gain(7)), scansound._render(tick))   # byte for byte

    def test_levels_rise_and_off_is_silent(self):
        g = [scansound.gain(i) for i in range(scansound.LEVELS + 1)]
        self.assertEqual(g[0], 0.0)
        self.assertEqual(g, sorted(g))
        self.assertEqual(len(set(g)), len(g))
        self.assertIsNone(scansound.path("tick", 0))
        quiet = scansound._render(scansound.NOTES["tick"], scansound.gain(2))
        self.assertLess(max(abs(int.from_bytes(quiet[i:i + 2], "little", signed=True)) for i in range(0, len(quiet), 2)),
                        32767 * 0.8 * scansound.gain(2) + 2)

    def test_old_settings(self):
        self.assertEqual(scansound.level_of({}), 7)
        self.assertEqual(scansound.level_of({"scan_sounds": True}), 7)
        self.assertEqual(scansound.level_of({"scan_sounds": False}), 0)   # whoever switched off stays off
        self.assertEqual(scansound.level_of({"scan_volume": 3, "scan_sounds": True}), 3)
        self.assertEqual(scansound.level_of({"scan_volume": 0}), 0)
        self.assertEqual(scansound.level_of({"scan_volume": 99}), 10)
        self.assertEqual(scansound.level_of({"scan_volume": "x"}), 7)


class Lib:
    """library's collection.wishhit, as agreed: hit(card, settings) / undo(token, list_id=None)."""

    def __init__(self, lists=(), removed=True, friends=()):
        self.r = {"lists": [dict(x) for x in lists], "removed": removed, "undo": {"t": 1} if removed else None,
                  "friends": list(friends)}
        self.calls = []

    def hit(self, card, settings):
        return self.r

    def undo(self, token, list_id=None):
        self.calls.append(list_id)
        return 1


L1 = {"id": 11, "name": "Modern", "n": 1}
L2 = {"id": 12, "name": "Commander", "n": 2}
L3 = {"id": 13, "name": "Binder", "n": 1}


def bar(lib):
    return WishBar(lib.hit, lib.undo)


class Bar(unittest.TestCase):
    def test_nothing_without_a_hit(self):
        b = WishBar(lambda c, s: {"lists": [], "removed": False, "friends": []}, None)
        self.assertFalse(b.check({"name": "X"}, {}))
        self.assertEqual(b.view(), {})
        self.assertFalse(WishBar(lambda c, s: None, None).check({"name": "X"}, {}))

    def test_library_error_never_stops_scanning(self):
        def boom(c, s):
            raise RuntimeError("x")
        b = WishBar(boom, None)
        with self.assertLogs("scanner.wishbar", "ERROR"):
            self.assertFalse(b.check({"name": "X"}, {}))
        self.assertEqual(b.view(), {})

    def test_one_list_undo_once(self):
        lib = Lib([L1])
        b = bar(lib)
        self.assertTrue(b.check({"name": "X"}, {}))
        v = b.view()
        self.assertEqual((v["head"], v["text"], v["link"], v["linkKind"]),
                         ("Orbit", "Wish card hit – removed from Modern", "Undo", "undo"))
        self.assertTrue(b.undo())
        self.assertFalse(b.undo())                                  # once
        self.assertEqual(lib.calls, [None])
        self.assertEqual((b.view()["link"], b.view()["linkKind"]), ("Undone", ""))

    def test_several_lists_details(self):
        b = bar(Lib([L1, L2, L3]))
        b.check({"name": "X"}, {})
        v = b.view()
        self.assertEqual((v["text"], v["link"], v["linkKind"]), ("Wish card hit – removed from 3 lists", "Details", "details"))
        self.assertEqual([(r["name"], r["link"]) for r in v["lists"]],
                         [("Modern", "Undo"), ("Commander", "Undo"), ("Binder", "Undo")])

    def test_one_list_then_U_only_the_rest(self):
        """lead 14.11.: first one list on its own (Details), then "U" – only the lists still out, none twice."""
        lib = Lib([L1, L2, L3])
        b = bar(lib)
        entry = {"name": "X"}
        b.check(entry, {})
        self.assertTrue(b.undo("12"))                               # Details: Commander
        self.assertEqual([r["undone"] for r in b.view()["lists"]], [False, True, False])
        self.assertFalse(b.undo("12"))                              # not twice
        self.assertTrue(b.card_removed(entry))                      # U
        self.assertEqual(lib.calls, [12, 11, 13])                   # library's own ids, Commander only once
        self.assertFalse(b.card_removed(entry))
        self.assertEqual(lib.calls, [12, 11, 13])

    def test_U_alone_undoes_everything_at_once(self):
        lib = Lib([L1, L2])
        b = bar(lib)
        entry = {"name": "X"}
        b.check(entry, {})
        self.assertFalse(b.card_removed({"name": "X"}))             # another card (same content, not the same one)
        self.assertTrue(b.card_removed(entry))
        self.assertEqual(lib.calls, [None])

    def test_next_hit_replaces(self):
        lib = Lib([L1])
        b = bar(lib)
        first = {"name": "X"}
        b.check(first, {})
        s1 = b.view()["serial"]
        b.check({"name": "Y"}, {})
        self.assertEqual(b.view()["serial"], s1 + 1)
        self.assertFalse(b.card_removed(first))                     # Undo held only until the next hit
        self.assertEqual(lib.calls, [])

    def test_auto_remove_off(self):
        b = bar(Lib([L1], removed=False))
        b.check({"name": "X"}, {})
        v = b.view()
        self.assertEqual((v["text"], v["link"], v["linkKind"]), ("Wish card hit – on Modern", "", ""))
        self.assertFalse(b.undo())
        b = bar(Lib([L1, L2], removed=False))
        b.check({"name": "X"}, {})
        v = b.view()
        self.assertEqual((v["text"], v["linkKind"]), ("Wish card hit – on 2 lists", "details"))
        self.assertEqual([r["link"] for r in v["lists"]], ["", ""])

    def test_mixed_per_list(self):
        """library 14.11.: auto-remove is set per list – each list says "removed"; Undo only where something went."""
        lib = Lib([dict(L1, removed=True), dict(L2, removed=False), dict(L3, removed=False)])
        b = bar(lib)
        entry = {"name": "X"}
        b.check(entry, {})
        v = b.view()
        self.assertEqual((v["text"], v["linkKind"]), ("Wish card hit – removed from 1 list, on 2 more", "details"))
        self.assertEqual([r["link"] for r in v["lists"]], ["Undo", "", ""])
        self.assertEqual([r["note"] for r in v["lists"]], ["", "stays", "stays"])   # why no Undo (lead 14.11.)
        self.assertFalse(b.undo("12"))                              # nothing was taken from Commander
        self.assertTrue(b.card_removed(entry))                      # U: only Modern
        self.assertEqual(lib.calls, [None])
        lib = Lib([dict(L1, removed=True), dict(L2, removed=True), dict(L3, removed=False)])
        b = bar(lib)
        b.check(entry, {})
        self.assertEqual(b.view()["text"], "Wish card hit – removed from 2 lists, on 1 more")
        self.assertTrue(b.undo("11"))
        self.assertTrue(b.card_removed(entry))
        self.assertEqual(lib.calls, [11, 12])                       # never the list that kept its wish
        lib = Lib([dict(L1, removed=False)], removed=False)
        b = bar(lib)
        b.check(entry, {})
        self.assertEqual((b.view()["text"], b.view()["link"]), ("Wish card hit – on Modern", ""))

    def test_friends(self):
        b = bar(Lib([], removed=False, friends=[{"name": "Kim", "lists": ["Modern wants"]}]))
        self.assertTrue(b.check({"name": "X"}, {}))                 # a friend's wish alone is a hit too
        v = b.view()
        self.assertEqual((v["text"], v["friendText"], v["friendLink"]), ("", "Kim is looking for this card", ""))
        b = bar(Lib([L1], friends=[{"name": "Kim", "lists": ["A", "B"]}, {"name": "Jo", "lists": []}, "Ali"]))
        b.check({"name": "X"}, {})
        v = b.view()
        self.assertEqual((v["friendText"], v["friendLink"]), ("3 friends are looking for this card", "Details"))
        self.assertEqual(v["friends"], [{"name": "Kim", "lists": "A, B"}, {"name": "Jo", "lists": ""},
                                        {"name": "Ali", "lists": ""}])

    def test_no_library_yet(self):
        b = WishBar(None, None)
        if b._hit is None:
            self.assertFalse(b.check({"name": "X"}, {}))


class WithLibrary(tw.Base):
    """The bar on library's real collection/wishhit (temp folders – tests/test_wishhit.py's Base): one list undone
    in Details, then U – everything exactly back, nothing twice (lead 14.11.); a list set to keep stays as it was."""

    def test_details_then_U(self):
        b = self
        lists = {"wish": [{"id": "wa", "name": "A"}, {"id": "wb", "name": "B"}, {"id": "wc", "name": "C"}]}
        b.put([tw.wish("Lightning Bolt", lst="wa"), tw.wish("Lightning Bolt", 2, lst="wb"),
               tw.wish("Lightning Bolt", 3, lst="wc")], lists)
        tw.trade.set_scan_remove("wc", False)                       # C keeps its wish
        before = b.now()
        bar_ = WishBar()                                            # the real hit/undo
        entry = dict(tw.BOLT)
        self.assertTrue(bar_.check(entry, {}))
        v = bar_.view()
        self.assertEqual(v["text"], "Wish card hit – removed from 2 lists, on 1 more")
        self.assertEqual([(r["name"], r["link"]) for r in v["lists"]], [("A", "Undo"), ("B", "Undo"), ("C", "")])
        self.assertTrue(bar_.undo("wb"))                            # Details: B
        self.assertEqual(b.now(), [("Lightning Bolt", None, "wb", 2), ("Lightning Bolt", None, "wc", 3)])
        self.assertTrue(bar_.card_removed(entry))                   # U: only A is left
        self.assertEqual(b.now(), before)                           # exactly as before – B not twice, C untouched
        self.assertFalse(bar_.card_removed(entry))
        self.assertEqual(b.now(), before)


class Texts(unittest.TestCase):
    def test_german(self):
        from locales import de
        d = de.TEXTS if hasattr(de, "TEXTS") else None
        if d is None:
            d = next(v for v in vars(de).values() if isinstance(v, dict) and "Undo" in v)
        self.assertEqual(d["Wish card hit – removed from {list}"], "Wunschkarte getroffen – entfernt aus {list}")
        self.assertEqual(d["{n} friends are looking for this card"], "{n} Freunde suchen diese Karte")
        self.assertEqual(d["Sound"], "Ton")
        self.assertEqual(d["off"], "aus")


if __name__ == "__main__":
    unittest.main()
