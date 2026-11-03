"""The library as the sum of its logs (collection/logsum.py, docs/SYNC-PLAN.md §3b): every way a copy comes or goes
leaves a line, the one-off migration closes what older versions didn't write down, a lost collection.json comes
back from the logs alone, a log in the trash is hidden (never just gone) and keeps its cards while it says so.

    python -m unittest discover -t . -s tests -p test_logsum.py
"""
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from collection import collection, logsum, manual, sessions


def card(name, eur=1.0):
    return {"id": f"{name}-id_0", "name": name, "set": "tst", "number": "1", "rarity": "rare",
            "finishes": ["nonfoil", "foil"], "booster": True, "eur": eur, "eur_foil": eur * 2, "img": "x.jpg", "url": ""}


def scan_log(sid, names, when):
    """A finished scan log with one card entry per name (as Session.to_dict writes it)."""
    cards = [dict(card(n), lang="en", foil=False, added=when + i, price=1.0) for i, n in enumerate(names)]
    return {"id": sid, "started": when, "ended": when + 100, "info": {"title": sid},
            "packs": [{"opened": when, "type": None, "cards": cards}]}


class _Home(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.patches = [mock.patch.object(sessions, "SESSIONS", root / "sessions"),
                        mock.patch.object(collection, "FILE", root / "collection.json")]
        for p in self.patches:
            p.start()
        self.coll = collection.Collection()
        self.t = time.mktime((2026, 10, 27, 12, 0, 0, 0, 0, -1))

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def logs(self):
        return sessions.load_all(include_hidden=True)

    def gap(self, bookings=()):
        return logsum.diff(self.coll.items, self.logs(), list(bookings))

    def scan(self, sid, names):
        d = scan_log(sid, names, self.t)
        sessions.save(d)
        self.coll.sync_session(d)
        return d

    def add(self, c, n=1):   # = app.collection_add
        it = self.coll.add(c, "en", False, n)
        return manual.record(it, n, self.t + 5)

    def count(self, it, n):  # = app.collection_count
        before = dict(self.coll.get(it["uid"]))
        self.coll.set_count(it["uid"], n)
        return manual.record(before, max(0, n) - int(before.get("count", 1)), self.t + 6)


class Sum(_Home):
    def test_scans_and_changes_by_hand_add_up(self):
        self.scan("s1", ["A", "B", "C"])
        self.add(card("D"), 2)
        b = next(it for it in self.coll.items if it["name"] == "B")
        self.count(b, 3)                                     # a scanned card: two more by hand
        c = next(it for it in self.coll.items if it["name"] == "C")
        self.count(c, 0)                                     # a scanned card taken out
        self.assertEqual(self.gap(), {})
        self.assertEqual(sum(logsum.actual(self.coll.items).values()), 1 + 3 + 2)

    def test_a_copy_without_a_line_is_a_gap(self):
        self.scan("s1", ["A"])
        self.coll.add(card("X"), "en", False, 1)             # past the logs (as before manual.py)
        self.assertEqual(list(self.gap().values()), [(0, 1)])

    def test_trade_taken_counts(self):
        self.scan("s1", ["A", "B"])
        a = next(it for it in self.coll.items if it["name"] == "A")
        self.coll.set_count(a["uid"], 0)                     # as bookings.book_trade does
        book = [{"taken": [{"uid": a["uid"], "n": 1, "item": dict(a)}]}]
        self.assertEqual(self.gap(book), {})


class Migration(_Home):
    def test_closes_every_gap_and_stays_closed(self):
        d = self.scan("s1", ["A", "B", "C"])
        self.coll.add(card("X"), "en", False, 2)             # by hand, no line
        b = next(it for it in self.coll.items if it["name"] == "B")
        self.coll.items.remove(b)                            # gone the old way: only "hidden"
        self.coll.hidden.add(b["src"])
        self.coll.detach_session("s1")                       # log deleted with "keep cards" (old)
        sessions.delete("s1")
        self.assertTrue(self.gap())
        mig = logsum.migration(self.coll.items, self.logs(), [], self.t + 1000)
        manual.hide_gone(self.coll, mig)
        sessions.save(mig)
        self.assertEqual(self.gap(), {})
        self.assertTrue(manual.is_manual(mig) and mig["info"]["migrated"])
        # and a rebuild from the logs alone gives the same library
        before = logsum.actual(self.coll.items)
        fresh = collection.Collection.__new__(collection.Collection)
        fresh.items, fresh.hidden, fresh.rev, fresh.lock = [], set(self.coll.hidden), 0, self.coll.lock
        for x in self.logs():
            if x.get("ended") and x.get("collection") is not False:
                fresh.sync_session(x)
        logsum.repair(fresh, self.logs(), [])
        self.assertEqual(logsum.actual(fresh.items), before)
        self.assertIsNotNone(d)

    def test_only_plus_lines_a_card_gone_the_old_way_is_listed(self):
        self.scan("s1", ["A", "B"])
        self.coll.add(card("X"), "en", False, 1)
        b = next(it for it in self.coll.items if it["name"] == "B")
        self.coll.items.remove(b)                            # the old way: only "hidden", no line
        self.coll.hidden.add(b["src"])
        mig = logsum.migration(self.coll.items, self.logs(), [], self.t + 1000)
        self.assertEqual([ln["delta"] for ln in mig["packs"][0]["cards"]], [1])   # X – nothing with minus
        self.assertEqual(mig["gone"], [b["src"]])
        sessions.save(mig)
        self.assertEqual(self.gap(), {})

    def test_running_log_doesnt_count_and_the_net_stays_quiet(self):
        """.102: a booster log still running at the migration (its cards not in the library yet) came out as
        −14 cards in the migration log, and the safety net put +14 into the day's log when it ended."""
        self.scan("s1", ["A"])
        run = dict(scan_log("s2", ["P", "Q", "R"], self.t + 10), ended=None)   # running: nothing in the library yet
        sessions.save(run)
        mig = logsum.migration(self.coll.items, self.logs(), [], self.t + 1000)
        self.assertIsNone(mig)
        run["ended"] = self.t + 2000                         # ends: its cards come in
        sessions.save(run)
        self.coll.sync_session(run)
        self.assertEqual(self.gap(), {})                     # the net has nothing to do
        self.assertEqual(manual.close_gap(self.coll, self.logs(), [], "check", self.t + 3000), 0)

    def test_old_gone_lines_fold_into_the_list(self):
        """0.9.2.102–104 wrote "gone" minus lines without a card (id/name None) – the statistics stumbled over them.
        fold_gone moves them into the log's "gone" list: the same sum, no line without a card."""
        self.scan("s1", ["A", "B"])
        b = next(it for it in self.coll.items if it["name"] == "B")
        self.coll.items.remove(b)
        self.coll.hidden.add(b["src"])
        old = {"id": "manual_2026-10-29", "started": self.t, "ended": self.t, "collection": False,
               "info": {"kind": "manual", "title": "", "active": True},
               "packs": [{"opened": self.t, "type": "manual", "cards": [
                   {"id": None, "name": None, "delta": -1, "added": self.t, "uid": "gone:" + b["src"],
                    "item": {"src": b["src"], "id": None, "name": None}, "why": "matched to the library"}]}]}
        sessions.save(old)
        self.assertEqual(self.gap(), {})                     # the old way already added up …
        self.assertTrue(manual.fold_gone(old))
        sessions.save(old)
        self.assertEqual(self.gap(), {})                     # … and still does
        self.assertEqual(old["packs"][0]["cards"], [])
        self.assertEqual(old["gone"], [b["src"]])
        self.assertFalse(manual.fold_gone(old))             # once only

    def test_nothing_to_do(self):
        self.scan("s1", ["A"])
        self.assertIsNone(logsum.migration(self.coll.items, self.logs(), [], self.t))


class Rebuild(_Home):
    def test_lost_collection_comes_back_from_the_logs(self):
        self.scan("s1", ["A", "B"])
        self.add(card("D"), 2)
        b = next(it for it in self.coll.items if it["name"] == "B")
        self.count(b, 4)
        a = next(it for it in self.coll.items if it["name"] == "A")
        self.coll.set_count(a["uid"], 0)
        book = [{"taken": [{"uid": a["uid"], "n": 1, "item": dict(a)}]}]
        before = logsum.actual(self.coll.items)
        fresh = collection.Collection.__new__(collection.Collection)
        fresh.items, fresh.hidden, fresh.rev, fresh.lock = [], set(), 0, self.coll.lock
        for x in self.logs():
            if x.get("ended") and x.get("collection") is not False:
                fresh.sync_session(x)
        logsum.repair(fresh, self.logs(), book)
        self.assertEqual(logsum.actual(fresh.items), before)
        d = next(it for it in fresh.items if it["name"] == "D")
        self.assertEqual((d["count"], d["src"]), (2, None))


class Trash(_Home):
    def test_hidden_log_keeps_its_cards_and_is_not_listed(self):
        self.scan("s1", ["A", "B"])
        sessions.hide("s1", kept=True)
        self.assertEqual([d["id"] for d in sessions.load_all()], [])
        self.assertEqual([d["id"] for d in sessions.hidden_all()], ["s1"])
        self.assertEqual(self.gap(), {})                     # still the source of A and B
        sessions.unhide("s1")
        self.assertEqual([d["id"] for d in sessions.load_all()], ["s1"])

    def test_hidden_with_cards_leaves_the_library(self):
        self.scan("s1", ["A"])
        self.coll.remove_session("s1")
        d = sessions.hide("s1", kept=False)
        self.assertIs(d["collection"], False)
        self.assertEqual(self.gap(), {})

    def test_for_good_after_60_days_turns_kept_cards_into_lines(self):
        self.scan("s1", ["A", "B"])
        sessions.hide("s1", kept=True)
        with mock.patch.object(time, "time", return_value=time.time() + 61 * 86400):
            due = sessions.due_for_good()
        self.assertEqual([d["id"] for d in due], ["s1"])
        held = [dict(it) for it in self.coll.items if (it.get("src") or "").startswith("s1/")]   # = app.log_for_good
        self.coll.detach_session("s1")
        for it in held:
            manual.record(dict(it, src=None), int(it.get("count", 1)), self.t + 9, why="for good")
        sessions.delete("s1")
        self.assertEqual(self.gap(), {})

    def test_close_gap_writes_lines_with_why(self):
        self.scan("s1", ["A"])
        self.coll.add(card("X"), "en", False, 1)
        n = manual.close_gap(self.coll, self.logs(), [], "undone", self.t + 50)
        self.assertEqual(n, 1)
        self.assertEqual(self.gap(), {})
        ln = manual.lines(manual.day_id(self.t + 50))[-1]
        self.assertEqual((ln["delta"], ln["why"]), (1, "undone"))

    def test_edit_line_keeps_the_copies(self):
        self.add(card("D"), 1)
        it = self.coll.items[0]
        manual.record_edit(dict(it, cond="LP"), {"cond": ["NM", "LP"]}, self.t + 7)
        self.assertEqual(self.gap(), {})
        ln = manual.lines(manual.day_id(self.t + 7))[-1]
        self.assertEqual((ln["delta"], ln["edit"]), (0, {"cond": ["NM", "LP"]}))


if __name__ == "__main__":
    unittest.main()
