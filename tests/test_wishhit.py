"""Wishlist hits while scanning (collection/wishhit.py, lead/Gordon/legal 14.11.2026). Temp folders only – no real
data, no network; the sync test runs two devices over the in-memory vault of tests/test_syncrun.py (never the box).

    python -m unittest tests/test_wishhit.py
"""
import json
import pathlib
import socket
import tempfile
import time
import unittest
import urllib.request
from unittest import mock

from collection import syncrun, trade, wishhit
from system import undo as sysundo


def wish(name, count=1, set_code=None, number=None, lst="main", **extra):
    w = {"name": name, "count": count, "note": "", "added": 1793500000.0, "list": lst}
    if set_code:
        w.update(set=set_code, number=number)
    w.update(extra)
    return w


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.mine(self.root / "mine")
        self.friends = self.root / "friends"
        self.friends.mkdir()
        for p in (mock.patch.object(wishhit, "_game", lambda: "mtg"),
                  mock.patch.object(trade, "friends_folder", lambda game: self.friends)):
            p.start()
            self.addCleanup(p.stop)
        wishhit._cache.clear()
        self.addCleanup(wishhit._cache.clear)
        self.addCleanup(sysundo.clear)

    def mine(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        for name, val in (("MINE", folder), ("WISH_FILE", folder / "wishlist.json"),
                          ("LISTS_FILE", folder / "lists.json")):
            p = mock.patch.object(trade, name, val)
            p.start()
            self.addCleanup(p.stop)

    def put(self, items, lists=None):
        trade.WISH_FILE.write_text(json.dumps({"version": 1, "items": items}), "utf-8")
        if lists is not None:
            trade.LISTS_FILE.write_text(json.dumps(lists), "utf-8")

    def now(self):
        return sorted((w["name"], w.get("set"), w.get("list"), w["count"]) for w in trade.wishes(raw=True))

    def friend(self, fid, name, wants):
        f = self.friends / f"{fid}.json"
        f.write_text(json.dumps({"id": fid, "name": name, "cards": [], "wants": wants}), "utf-8")
        return f


BOLT = {"name": "Lightning Bolt", "set": "M10", "number": "146", "lang": "de", "foil": True, "id": "x1"}


class Match(Base):
    def test_exact_print_only_that_print(self):
        self.put([wish("Lightning Bolt", 1, "2x2", "117")])
        r = wishhit.hit(BOLT, {})
        self.assertEqual((r["lists"], r["removed"], r["undo"]), ([], False, None))
        self.assertEqual(self.now(), [("Lightning Bolt", "2x2", "main", 1)])

    def test_name_only_every_print_and_case(self):
        self.put([wish("lightning bolt", 2)])
        r = wishhit.hit(BOLT, {})
        self.assertTrue(r["removed"])
        self.assertEqual([(x["id"], x["n"]) for x in r["lists"]], [("main", 2)])
        self.assertEqual(self.now(), [("lightning bolt", None, "main", 1)])     # 2 → 1

    def test_wish_with_language_foil_counts_for_the_print(self):
        self.put([wish("Lightning Bolt", 1, "m10", "146", lang="ja", foil=False)])   # lead 14.11.: set+number decide
        self.assertTrue(wishhit.hit(BOLT, {})["removed"])
        self.assertEqual(self.now(), [])

    def test_several_lists_all_lowered_custom_lists_never(self):
        lists = {"wish": [{"id": "w2", "name": "Commander"}], "custom": [{"id": "c1", "name": "Doubles"}]}
        self.put([wish("Lightning Bolt"), wish("Lightning Bolt", 3, lst="w2"), wish("Lightning Bolt", lst="c1")], lists)
        r = wishhit.hit(BOLT, {})
        self.assertEqual(sorted(x["id"] for x in r["lists"]), ["main", "w2"])
        self.assertEqual(self.now(), [("Lightning Bolt", None, "c1", 1), ("Lightning Bolt", None, "w2", 2)])

    def test_one_per_list_exact_print_first(self):
        self.put([wish("Lightning Bolt", 2), wish("Lightning Bolt", 1, "M10", "146")])
        wishhit.hit(BOLT, {})
        self.assertEqual(self.now(), [("Lightning Bolt", None, "main", 2)])     # the exact one went, name-only stays

    def test_switch_off_reports_but_keeps(self):
        self.put([wish("Lightning Bolt")], {"wish": [{"id": "main", "name": "Wunschliste", "scan_keep": True}]})
        r = wishhit.hit(BOLT, {})
        self.assertEqual((len(r["lists"]), r["removed"], r["undo"]), (1, False, None))
        self.assertFalse(r["lists"][0]["removed"])
        self.assertEqual(self.now(), [("Lightning Bolt", None, "main", 1)])

    def test_list_a_on_b_off(self):
        """lead 14.11.: A on, B off → A −1, B unchanged, the hit reports both."""
        self.put([wish("Lightning Bolt", 2, lst="wa"), wish("Lightning Bolt", 2, lst="wb")],
                 {"wish": [{"id": "wa", "name": "A"}, {"id": "wb", "name": "B"}]})
        trade.set_scan_remove("wb", False)
        r = wishhit.hit(BOLT, {})
        self.assertEqual([(x["id"], x["removed"]) for x in r["lists"]], [("wa", True), ("wb", False)])
        self.assertEqual(self.now(), [("Lightning Bolt", None, "wa", 1), ("Lightning Bolt", None, "wb", 2)])
        self.assertEqual(wishhit.undo(r["undo"], "wb"), 0)                      # nothing taken from B
        self.assertEqual(wishhit.undo(r["undo"]), 1)
        self.assertEqual(self.now(), [("Lightning Bolt", None, "wa", 2), ("Lightning Bolt", None, "wb", 2)])

    def test_setting_default_on_stored_only_when_off(self):
        self.put([], {"wish": [{"id": "wa", "name": "A"}]})
        self.assertTrue(trade.scan_removes(trade.lists("wish")[1]))
        trade.set_scan_remove("wa", False)
        self.assertEqual(json.loads(trade.LISTS_FILE.read_text("utf-8"))["wish"][-1].get("scan_keep"), True)
        trade.set_scan_remove("wa", True)
        self.assertNotIn("scan_keep", json.loads(trade.LISTS_FILE.read_text("utf-8"))["wish"][-1])

    def test_nothing_without_a_name_or_a_file(self):
        self.assertEqual(wishhit.hit({}, {})["lists"], [])
        self.assertEqual(wishhit.hit(BOLT, {})["lists"], [])                      # no wishlist.json yet

    def test_scanned_twice_lowered_twice(self):
        self.put([wish("Lightning Bolt", 2)])
        wishhit.hit(BOLT, {})
        wishhit.hit(BOLT, {})
        self.assertEqual(self.now(), [])


class Undo(Base):
    def test_undo_puts_back_exactly(self):
        self.put([wish("Lightning Bolt", 1, note="for Burn"), wish("Shock", 2)])
        before = trade.wishes(raw=True)
        r = wishhit.hit(BOLT, {})
        self.assertEqual(wishhit.undo(r["undo"]), 1)
        self.assertEqual(sorted(trade.wishes(raw=True), key=lambda w: w["name"]),
                         sorted(before, key=lambda w: w["name"]))                # note and date back too

    def test_a_change_in_between_stays(self):
        self.put([wish("Lightning Bolt", 3), wish("Shock")])
        r = wishhit.hit(BOLT, {})                                                # 3 → 2
        trade.set_wish_count("Lightning Bolt||", "main", 5)                      # by hand meanwhile
        trade.add_wish("Opt")
        wishhit.undo(r["undo"])
        self.assertEqual(self.now(), [("Lightning Bolt", None, "main", 6), ("Opt", None, "main", 1),
                                      ("Shock", None, "main", 1)])

    def test_lowered_then_deleted_by_hand_stays_deleted(self):
        self.put([wish("Lightning Bolt", 2)])
        r = wishhit.hit(BOLT, {})
        trade.remove_wish("Lightning Bolt")
        self.assertEqual(wishhit.undo(r["undo"]), 0)
        self.assertEqual(self.now(), [])

    def test_a_deleted_list_is_not_brought_back(self):
        self.put([wish("Lightning Bolt", lst="w2")], {"wish": [{"id": "w2", "name": "Commander"}]})
        r = wishhit.hit(BOLT, {})
        self.put([], {"wish": []})
        self.assertEqual(wishhit.undo(r["undo"]), 0)
        self.assertEqual(self.now(), [])
        self.assertNotIn("w2", [x["id"] for x in trade.lists("wish")])

    def test_foreign_or_broken_token(self):
        self.put([wish("Lightning Bolt")])
        r = wishhit.hit(BOLT, {})
        self.assertEqual(wishhit.undo(None), 0)
        self.assertEqual(wishhit.undo({"v": 2}), 0)
        self.assertEqual(wishhit.undo(dict(r["undo"], game="pokemon")), 0)      # another game's token
        self.assertEqual(self.now(), [])

    def test_per_list_and_never_twice(self):
        lists = {"wish": [{"id": "wa", "name": "A"}, {"id": "wb", "name": "B"}]}
        self.put([wish("Lightning Bolt", lst="wa"), wish("Lightning Bolt", 2, lst="wb")], lists)
        r = wishhit.hit(BOLT, {})
        self.assertEqual(wishhit.undo(r["undo"], "wb"), 1)                      # only B
        self.assertEqual(self.now(), [("Lightning Bolt", None, "wb", 2)])        # A stays removed
        self.assertEqual(wishhit.undo(r["undo"], "wb"), 0)                      # B a second time: nothing
        self.assertEqual(wishhit.undo(r["undo"]), 1)                            # "all": only A is left
        self.assertEqual(wishhit.undo(r["undo"]), 0)
        self.assertEqual(self.now(), [("Lightning Bolt", None, "wa", 1), ("Lightning Bolt", None, "wb", 2)])
        self.assertEqual(wishhit.undo(r["undo"], "nope"), 0)

    def test_one_ctrl_z_step(self):
        sysundo.clear()
        self.put([wish("Lightning Bolt")])
        wishhit.hit(BOLT, {})
        self.assertIsNotNone(sysundo.undo())                                     # the normal undo step exists
        self.assertEqual(self.now(), [("Lightning Bolt", None, "main", 1)])


class Friends(Base):
    def test_names_exact_and_name_only(self):
        self.friend("f1", "Anna", [["Lightning Bolt", 1, "", ""]])
        self.friend("f2", "Ben", [["Lightning Bolt", 1, "2X2", "117"]])
        self.friend("f3", "Cleo", [["Lightning Bolt", 2, "m10", "146"]])
        self.friend("f4", "Dan", [["Shock", 1]])                                 # relay rows: [name, count]
        fr = wishhit.hit(BOLT, {})["friends"]
        self.assertEqual(sorted(x["name"] for x in fr), ["Anna", "Cleo"])
        self.assertEqual([x["lists"] for x in fr], [[], []])                     # list names never reach this PC

    def test_share_ended_no_more_hits(self):
        f = self.friend("f1", "Anna", [["Lightning Bolt", 1]])
        self.assertEqual(wishhit.hit(BOLT, {})["friends"], [{"name": "Anna", "lists": []}])
        f.unlink()                                                               # relay.py deletes the file
        self.assertEqual(wishhit.hit(BOLT, {})["friends"], [])
        self.assertEqual(wishhit._cache.get(str(f)), None)                       # nothing kept of it
        self.friend("f1", "Anna", [])                                            # wants withdrawn, friend stays
        self.assertEqual(wishhit.hit(BOLT, {})["friends"], [])

    def test_stays_local(self):
        f = self.friend("f1", "Anna", [["Lightning Bolt", 1]])
        self.put([wish("Lightning Bolt")])
        before = f.read_bytes(), sorted(p.name for p in self.friends.iterdir())
        boom = mock.Mock(side_effect=AssertionError("network"))
        with mock.patch.object(urllib.request, "urlopen", boom), mock.patch.object(socket.socket, "connect", boom):
            r = wishhit.hit(BOLT, {})
            wishhit.undo(r["undo"])
        self.assertEqual([x["name"] for x in r["friends"]], ["Anna"])
        self.assertEqual((f.read_bytes(), sorted(p.name for p in self.friends.iterdir())), before)
        boom.assert_not_called()


class Speed(Base):
    def test_fast_enough_for_the_ui_thread(self):
        """scanner calls hit() when counting (~5 ms budget): a miss is a few stat calls; a hit writes once."""
        self.put([wish(f"Card {i}", 2) for i in range(500)] + [wish("Lightning Bolt", 50)])
        for i in range(20):
            self.friend(f"f{i}", f"F{i}", [[f"Want {j}", 1] for j in range(200)])
        wishhit.hit({"name": "Nothing"}, {})                                     # warm the cache
        t = time.perf_counter()
        for _ in range(50):
            wishhit.hit({"name": "Nothing"}, {})
        miss = (time.perf_counter() - t) / 50
        t = time.perf_counter()
        for _ in range(10):
            wishhit.hit(BOLT, {})
        hit_ = (time.perf_counter() - t) / 10
        print(f"\nwishhit: miss {miss * 1000:.2f} ms, hit+write {hit_ * 1000:.2f} ms")
        self.assertLess(miss, 0.02)                                              # generous: the PC runs other work
        self.assertLess(hit_, 0.2)


class Sync(Base):
    """Required (Gordon 14.11.): hit → undo → sync – both devices have exactly the old state."""

    def test_hit_undo_sync_two_devices(self):
        from tests.test_syncrun import Device, FakeVault
        t = [1793600000000]
        vault = FakeVault()
        a = Device(self.tmp.name, "a", vault, lambda: t[0])
        b = Device(self.tmp.name, "b", vault, lambda: t[0])
        start = [wish("Lightning Bolt", 2), wish("Shock", 1, "M10", "151"), wish("Opt", 1, note="x")]
        a.docs.write("mtg", "wishlist.json", {"version": 1, "items": start})
        a.eng.switch_on()
        a.sync()
        t[0] += 1000
        b.eng.switch_on()
        b.sync()

        def state(dev):
            return sorted((w["name"], w.get("set"), w.get("list"), w["count"], w.get("note", ""))
                          for w in (dev.docs.read("mtg", "wishlist.json") or {}).get("items", []))
        old = state(a)
        self.assertEqual(state(b), old)
        p = mock.patch.object(syncrun, "ENGINE", a.eng)
        p.start()
        self.addCleanup(p.stop)
        self.mine(a.docs.path("mtg", "x").parent)                              # device A's own wishlist
        wishhit._cache.clear()

        t[0] += 1000
        r = wishhit.hit(BOLT, {})                                                # Bolt 2 → 1
        r2 = wishhit.hit({"name": "Shock", "set": "m10", "number": "151"}, {})   # Shock gone
        a.sync()
        t[0] += 1000
        b.sync()
        self.assertIn(("Lightning Bolt", None, "main", 1, ""), state(b))
        self.assertNotIn("Shock", [s[0] for s in state(b)])

        t[0] += 1000
        wishhit.undo(r2["undo"])
        wishhit.undo(r["undo"])
        a.sync()
        t[0] += 1000
        b.sync()
        t[0] += 1000
        a.sync()
        self.assertEqual(state(a), old)
        self.assertEqual(state(b), old)
        self.assertEqual(a.eng.state.sum("mtg/wishcards"), b.eng.state.sum("mtg/wishcards"))

    def test_the_list_setting_travels(self):
        from collection import syncops
        from tests.test_syncrun import Device, FakeVault
        t = [1793600000000]
        vault = FakeVault()
        a = Device(self.tmp.name, "a", vault, lambda: t[0])
        b = Device(self.tmp.name, "b", vault, lambda: t[0])
        a.docs.write("mtg", "lists.json", {"wish": [{"id": "wa", "name": "A"}, {"id": "wb", "name": "B"}]})
        a.eng.switch_on()
        a.sync()
        t[0] += 1000
        b.eng.switch_on()
        b.sync()
        d = a.docs.read("mtg", "lists.json")
        d["wish"][1]["scan_keep"] = True                                         # B off on device A
        a.docs.write("mtg", "lists.json", d)
        a.eng.record("mtg", "lists.json")
        t[0] += 1000
        a.sync()
        t[0] += 1000
        b.sync()
        got = {x["id"]: x.get("scan_keep") for x in b.docs.read("mtg", "lists.json")["wish"]}
        self.assertEqual(got, {"wa": None, "wb": True})
        # a list with the default writes nothing new: no field, no op for lists that never changed
        self.assertNotIn("scan_keep", syncops.explode("lists", {"wish": [{"id": "wa", "name": "A"}]})["wa"])


if __name__ == "__main__":
    unittest.main()
