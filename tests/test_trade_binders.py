"""Binders, trade offers, bookings, tickets and wish/trade lists – the pure logic and the save/load round trips
(collection/binders.py, offers.py, bookings.py, ticket.py, trade.py). Every file constant points into a temp folder,
collectibles.archive and undo.before_write are replaced; no UI, no network.

    python -m unittest tests/test_trade_binders.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import numpy as np

from collection import binders, bookings, collectibles, offers, sessions, ticket, trade
from collection import collection as coll_mod
from scanner import common
from system import datastore, undo


class _Mine(unittest.TestCase):
    """Temp data folder; all personal files of these modules point into it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data = pathlib.Path(self._tmp.name) / "data"
        self.mine = self.data / "my-data"
        self.archived = []
        m = self.mine
        self.p = [mock.patch.object(common, "DATA", self.data),
                  mock.patch.object(undo, "before_write", lambda path, label="": None),
                  mock.patch.object(collectibles, "archive",
                                    lambda t, event, img=None, info=None: self.archived.append((t["id"], event))),
                  mock.patch.object(binders, "MINE", m), mock.patch.object(binders, "FILE", m / "binders.json"),
                  mock.patch.object(offers, "MINE", m), mock.patch.object(offers, "FILE", m / "offers.json"),
                  mock.patch.object(bookings, "MINE", m), mock.patch.object(bookings, "FILE", m / "bookings.json"),
                  mock.patch.object(bookings, "PENDING", m / "pending-trades.json"),
                  mock.patch.object(sessions, "SESSIONS", m / "sessions"),
                  mock.patch.object(coll_mod, "MINE", m), mock.patch.object(coll_mod, "FILE", m / "collection.json"),
                  mock.patch.object(trade, "MINE", m), mock.patch.object(trade, "FRIENDS", m / "friends"),
                  mock.patch.object(trade, "WISH_FILE", m / "wishlist.json"),
                  mock.patch.object(trade, "LISTS_FILE", m / "lists.json"),
                  mock.patch.object(datastore, "TRASH", m / "trash"),
                  mock.patch.object(ticket, "_game", lambda: "mtg")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        self._tmp.cleanup()

    def assert_only_in_temp(self):
        root = pathlib.Path(self._tmp.name)
        self.assertEqual({p.name for p in root.iterdir()} - {"data"}, set())


def _row(n, set_code="abc"):
    return {"id": f"sid{n}", "set_code": set_code, "number": str(n), "name": f"Card {n}"}


class Binders(_Mine):
    def test_round_trip_create_update_remove(self):
        b = binders.new("  My Binder  ", 3, 3)
        self.assertEqual((b["name"], len(b["slots"])), ("My Binder", 18))   # one spread = 2 pages
        other = binders.new("", 2, 2)
        self.assertEqual(other["name"], "Binder")
        b["name"] = "Renamed"
        binders.put(b)
        self.assertEqual(binders.get(b["id"])["name"], "Renamed")
        self.assertEqual([x["id"] for x in binders.load()], [b["id"], other["id"]])
        binders.remove(b["id"])
        self.assertEqual([x["id"] for x in binders.load()], [other["id"]])
        self.assertIsNone(binders.get(b["id"]))
        self.assertFalse((self.mine / "binders.tmp").exists())
        self.assert_only_in_temp()

    def test_broken_file_reads_as_empty(self):
        self.mine.mkdir(parents=True)
        (self.mine / "binders.json").write_text("{not json", "utf-8")
        self.assertEqual(binders.load(), [])

    def test_add_cards_fills_gaps_and_grows_whole_spreads(self):
        b = {"id": "b", "name": "x", "cols": 2, "rows": 2, "slots": [None] * 8}
        binders.set_slot(b, 1, binders.slot_of(_row(0)))
        binders.add_cards(b, [_row(i) for i in range(1, 9)])
        names = [s and s["name"] for s in b["slots"]]
        self.assertEqual(names[:3], ["Card 1", "Card 0", "Card 2"])     # free slot 0 first, slot 1 untouched
        self.assertEqual(len(b["slots"]), 16)                           # 9 cards -> two spreads of 8
        self.assertEqual(binders.pages(b), 4)
        self.assertEqual(b["slots"][0]["set"], "abc")
        self.assertEqual(binders.pages({"cols": 3, "rows": 3, "slots": [None] * 10}), 2)   # always even

    def test_move_insert_remove(self):
        b = {"id": "b", "name": "x", "cols": 2, "rows": 1, "slots": ["A", "B", "C", None]}
        binders.move(b, 0, 2)
        self.assertEqual(b["slots"], ["C", "B", "A", None])
        binders.move_to(b, 0, 3)                                        # drag C between A and the gap
        self.assertEqual(b["slots"], ["B", "A", "C", None])
        binders.insert_at(b, 0, "N")                                    # trailing gap absorbs the shift
        self.assertEqual(b["slots"], ["N", "B", "A", "C"])
        binders.remove_slot(b, 1)
        self.assertEqual(b["slots"], ["N", None, "A", "C"])
        binders.remove_slot(b, 1, close=True)
        self.assertEqual(b["slots"], ["N", "A", "C", None])
        binders.insert_gap(b, 0)
        self.assertEqual(b["slots"], [None, "N", "A", "C", None, None, None, None])

    def test_value_progress_missing_share(self):
        b = {"id": "b", "name": "x", "cols": 2, "rows": 1, "slots": []}
        binders.add_cards(b, [_row(1), _row(2), binders.slot_of(_row(3), lang="de", foil=True)])
        owned = binders.owned_map([{"set": "ABC", "number": "1", "count": 2}, {"set": "abc", "number": "1"},
                                   {"set": "abc", "number": "3", "count": 1}])
        self.assertEqual(owned[("abc", "1")], 3)
        self.assertEqual(binders.progress(b, owned), (2, 3))
        self.assertEqual([s["number"] for s in binders.missing(b, owned)], ["2"])
        self.assertEqual(binders.value(b, owned, {"sid1": 1.5, "sid2": 10.0, "sid3": 2.0}), (13.5, 3.5))
        sh = binders.share_payload(b, owned)
        self.assertEqual(sh["slots"][:3], [["abc", "1", "en", 0, 1], ["abc", "2", "en", 0, 0],
                                           ["abc", "3", "de", 1, 1]])
        self.assertIsNone(sh["slots"][3])
        self.assertNotIn("Card 1", json.dumps(sh))                       # no names go out


class Tickets(_Mine):
    ME, BEN = ("me-profile-id-123456", "Me"), ("ben-profile-id-654321", "Ben")

    def test_new_fields_and_side(self):
        t = ticket.new(self.ME, self.BEN, [{"set": "ABC", "number": 1, "foil": True, "count": 2, "name": "X"}],
                       [["xyz", "7", "de", 0, 1, "Y"]], money=1.235)
        self.assertEqual(t["a"], [["abc", "1", "en", 1, 2, "X"]])
        self.assertEqual((t["x"], t["n"], t["k"], t["m"], t["g"]), (t["id"], 1, "o", 124, "mtg"))
        self.assertEqual(len(ticket.label(t)), 9)
        give, get, partner = ticket.side(t, self.ME[0])
        self.assertEqual((give, get, partner), (t["a"], t["b"], list(self.BEN)))
        give, get, partner = ticket.side(t, self.BEN[0])
        self.assertEqual((give, get, partner), (t["b"], t["a"], list(self.ME)))
        self.assertIsNone(ticket.side(t, "someone-else"))
        self.assertEqual(ticket.money_from_me(t, self.ME[0]), 1.24)          # I pay
        self.assertEqual(ticket.money_from_me(t, self.BEN[0]), -1.24)        # Ben receives
        short = dict(t, o=[self.BEN[0][:ticket.ID_LEN], "Ben"])              # pixel code keeps only the ID start
        self.assertIsNotNone(ticket.side(short, self.BEN[0]))
        self.assertEqual(ticket.kind({"v": 1}), "f")                         # old tickets: closing

    def test_mixed_game_ticket(self):
        t = ticket.new(self.ME, self.BEN, [["a", "1", "en", 0, 1, "", "pokemon"], ["b", "2", "en", 0, 1, "", "pokemon"]],
                       [["c", "3", "en", 0, 1]])
        self.assertEqual(t["g"], "pokemon")                                  # game with the most cards
        self.assertEqual(t["a"][0], ["a", "1", "en", 0, 1, ""])              # own game: 7th field dropped
        self.assertEqual(t["b"][0][6], "mtg")
        self.assertEqual(ticket.games_in(t), ["pokemon", "mtg"])

    def test_pixel_code_round_trip(self):
        t = ticket.new(self.ME, self.BEN, [["abc", "12", "en", 1, 3, "Long Card Name"]],
                       [["xyz", "7a", "ja", 0, 1, "Other", "pokemon"]], trade_id="trade1", version=2, kind="f",
                       money=-4.5)
        lay = ticket.RECEIPT
        rows, bitlist = ticket.bits(t, lay)
        h = ticket.band_height(rows, lay) + 40
        img = np.zeros((h, lay.W), np.uint8)
        for i, bit in enumerate(bitlist):
            if bit:
                x, y, m = ticket.module_rect(i, h, lay)
                img[y:y + m, x:x + m] = 255
        back = ticket.decode_gray(img)
        self.assertIsNotNone(back)
        self.assertEqual(back["a"], [c[:5] for c in t["a"]])                 # names are not in the pixel code
        self.assertEqual(back["b"][0][:5], t["b"][0][:5])
        self.assertEqual(back["b"][0][6], "pokemon")
        self.assertEqual((back["x"], back["n"], back["k"], back["m"]), ("trade1", 2, "f", -450))
        self.assertEqual(back["f"][0], self.ME[0][:ticket.ID_LEN])
        self.assertIsNone(ticket.decode_gray(np.zeros((300, lay.W), np.uint8)))   # blank image: nothing


class Offers(_Mine):
    def test_offer_counter_accept(self):
        me, ben = ("me", "Me"), ("ben", "Ben")
        t1 = ticket.new(me, ben, [["abc", "1", "en", 0, 1]], [])
        o = offers.record_sent(t1)
        self.assertEqual((o["status"], o["partner"], len(o["versions"])), ("sent", ["ben", "Ben"], 1))
        t2 = ticket.new(ben, me, [], [["abc", "1", "en", 0, 1]], trade_id=t1["x"], version=2)
        offers.record_received(t2, ben)
        offers.record_received(t2, ben)                                       # read in twice: one version
        o = offers.get(t1["x"])
        self.assertEqual(o["status"], "received")
        self.assertEqual([v["n"] for v in o["versions"]], [1, 2])
        self.assertEqual(offers.latest(o)["id"], t2["id"])
        offers.set_status(t1["x"], "accepted")
        self.assertEqual(offers.get(t1["x"])["status"], "accepted")
        self.assertEqual(self.archived, [(t1["id"], "sent"), (t2["id"], "received"), (t2["id"], "received")])

    def test_open_offers_first(self):
        a = ticket.new(("me", "Me"), ("a", "A"), [], [])
        b = ticket.new(("me", "Me"), ("b", "B"), [], [])
        offers.record_sent(a)
        offers.record_sent(b)
        offers.set_status(b["x"], "declined")
        offers.set_status(a["x"], "sent")
        self.assertEqual([o["id"] for o in offers.sorted_offers()], [a["x"], b["x"]])
        self.assertEqual(offers.load()[0]["status"], "sent")


class Bookings(_Mine):
    def coll(self, *items):
        c = coll_mod.Collection()
        c.items = [dict(uid=u, set=s, number=n, lang="en", foil=False, count=k, **extra)
                   for u, s, n, k, extra in items]
        return c

    def test_plan_prefers_trade_copies_and_reports_short(self):
        c = self.coll(("old", "abc", "1", 1, {"added": 1}), ("tr", "abc", "1", 1, {"added": 5, "trade": 1}),
                      ("ses", "abc", "1", 2, {"added": 2, "src": "s/1"}))
        take, short = bookings.plan(c, [["ABC", "1", "en", 0, 3], ["zzz", "9", "en", 1, 2]])
        self.assertEqual(take, [(0, "tr", 1), (0, "old", 1), (0, "ses", 1)])   # trade copy, manual, then session
        self.assertEqual(short, [["zzz", "9", "en", 1, 2]])
        take, _ = bookings.plan(c, [["abc", "1", "en", 0, 1]], prefer={0: "ses"})
        self.assertEqual(take, [(0, "ses", 1)])

    def test_book_and_cancel_round_trip(self):
        c = self.coll(("a", "abc", "1", 2, {"src": "s1/0.5"}), ("b", "abc", "2", 1, {}))
        t = {"id": "t1"}
        b = bookings.book_trade(c, t, [["abc", "1", "en", 0, 2], ["abc", "2", "en", 0, 1], ["abc", "3", "en", 0, 1]],
                                [], ["ben", "Ben"])
        self.assertEqual(c.items, [])
        self.assertEqual(c.hidden, {"s1/0.5"})                     # session copy will not come back with the session
        self.assertEqual(len(b["short"]), 1)
        self.assertIsNone(b["session"])
        self.assertEqual(bookings.by_ticket("t1")["id"], b["id"])
        self.assertEqual(self.archived, [("t1", "booked")])
        saved = json.loads((self.mine / "collection.json").read_text("utf-8"))
        self.assertEqual(saved["items"], [])
        self.assertTrue(bookings.cancel(c, b["id"]))
        self.assertEqual(sorted((it["uid"], it["count"]) for it in c.items), [("a", 2), ("b", 1)])
        self.assertEqual(c.hidden, set())
        self.assertEqual(bookings.load(), [])
        self.assertFalse(bookings.cancel(c, b["id"]))              # only once
        self.assert_only_in_temp()

    def test_cancel_adds_back_to_remaining_copy(self):
        c = self.coll(("a", "abc", "1", 3, {}))
        b = bookings.book_trade(c, {"id": "t2"}, [["abc", "1", "en", 0, 2]], [], ["ben", "Ben"])
        self.assertEqual(c.get("a")["count"], 1)
        bookings.cancel(c, b["id"])
        self.assertEqual(c.get("a")["count"], 3)

    def test_prices_of(self):
        db = {("abc", "1"): {"eur": 1.0, "eur_foil": 3.0}, ("abc", "2"): {"eur": 2.0, "eur_foil": None},
              ("abc", "3"): {"eur": None}}
        cards = [["ABC", "1", "en", 1, 2], ["abc", "1", "en", 0, 1], ["abc", "2", "en", 1, 1], ["abc", "3", "en", 0, 1],
                 ["zzz", "1", "en", 0, 1]]
        self.assertEqual(bookings.prices_of(cards, db), (9.0, 2))   # foil without foil price: normal price

    def test_pending_queue(self):
        t = {"id": "mix1"}
        bookings.add_pending("mtg", t, [["a", "1", "en", 0, 1]], [], ["ben", "Ben"], [])
        bookings.add_pending("mtg", t, [["a", "1", "en", 0, 1]], [], ["ben", "Ben"], [])   # same ticket once
        bookings.add_pending("pokemon", {"id": "mix2"}, [], [], ["ben", "Ben"], [])
        self.assertTrue((self.data / "games" / "pokemon" / "my-data" / "pending-trades.json").exists())
        got = bookings.take_pending()
        self.assertEqual([x["ticket"]["id"] for x in got], ["mix1"])
        self.assertEqual(bookings.take_pending(), [])              # emptied
        self.assert_only_in_temp()


class WishesListsFriends(_Mine):
    def test_wishes_merge_count_remove(self):
        trade.add_wish("Sol Ring")
        trade.add_wish("Sol Ring", 2)
        trade.add_wish("Sol Ring", 1, "c21", "263")
        self.assertEqual([(w["set"], w["count"]) for w in trade.wishes()], [(None, 3), ("c21", 1)])
        trade.set_wish_count("Sol Ring||", trade.MAIN_WISH, 5)
        self.assertEqual(trade.wishes()[0]["count"], 5)
        trade.set_pinned("Sol Ring|c21|263", trade.MAIN_WISH, False)  # unpinned: merged into "any version"
        self.assertEqual([(w["set"], w["count"]) for w in trade.wishes()], [(None, 6)])
        trade.set_wish_count("Sol Ring||", trade.MAIN_WISH, 0)
        self.assertEqual(trade.wishes(), [])

    def test_lists_and_their_wishes(self):
        self.assertEqual([x["id"] for x in trade.lists("wish")], [trade.MAIN_WISH])
        lid = trade.add_list("wish", "  Commander  ", shared=True)
        own = trade.add_list("custom", "Mine", shared=True)
        self.assertTrue(trade.is_shared(next(x for x in trade.lists("wish") if x["id"] == lid)))
        self.assertFalse(trade.is_shared(trade.lists("custom")[0]))       # own lists always private
        trade.add_wish("A", list_id=lid)
        trade.add_wish("B", list_id=own)
        trade.add_wish("C")
        self.assertEqual(sorted(w["name"] for w in trade.wishes()), ["A", "C"])   # own lists are not wishes
        self.assertEqual([w["name"] for w in trade.wishes([own])], ["B"])
        trade.rename_list("wish", lid, "EDH")
        self.assertEqual(trade.lists("wish")[1]["name"], "EDH")
        self.assertEqual(trade.kind_of(own), "custom")
        trade.remove_list("wish", trade.MAIN_WISH)                         # default list stays
        trade.remove_list("wish", lid)
        self.assertEqual([x["id"] for x in trade.lists("wish")], [trade.MAIN_WISH])
        self.assertEqual(sorted(w["name"] for w in trade.wishes(raw=True)), ["B", "C"])

    def test_friend_round_trip_and_trash(self):
        trade.save_friend({"id": "f1", "name": "<PySide6.QtQml.QJSValue object>", "imported": 1,
                           "cards": [["a", "1", "en", 0, 2, "X"], ["b", "2", "en", 0, 1, "X"], ["c", "3", "en", 0, 1]],
                           "file": "ignored"})
        trade.save_friend({"id": "f2", "name": "Ben", "imported": 2, "cards": []})
        fr = trade.friends()
        self.assertEqual([d["id"] for d in fr], ["f2", "f1"])                # newest first
        self.assertEqual(fr[1]["name"], "")                                  # old bug repaired
        self.assertEqual(trade.friend_cards_by_name(fr[1]), {"X": 3})
        trade.rename_friend("f1", "  Anna  ")
        self.assertEqual(trade.friend("f1")["name"], "Anna")
        trade.remove_friend("f1")
        self.assertIsNone(trade.friend("f1"))
        trashed = [e for _, e in datastore.trash_list()]
        self.assertEqual([(e["kind"], e["title"]) for e in trashed], [("friend", "Anna")])
        self.assert_only_in_temp()


if __name__ == "__main__":
    unittest.main()
