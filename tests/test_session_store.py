"""Sessions on disk (collection/sessions.py) and the counters of a session per game (scanner/core._counts: the two
rarity levels and the third counter – foil, or the game's own kind).

    python -m unittest tests/test_session_store.py
"""
import pathlib
import tempfile
import time
import unittest
from unittest import mock

import games
from collection import sessions
from games import lorcana, mtg, pokemon, yugioh
from scanner import core


def entry(rarity, foil=False, cid="x"):
    return {"id": cid, "rarity": rarity, "foil": foil}


class Counters(unittest.TestCase):
    def counts(self, game, cards):
        with mock.patch.object(games, "current", lambda: game):
            return core._counts(cards)

    def test_magic(self):
        cards = [entry("mythic"), entry("rare", True), entry("rare"), entry("common", True)]
        self.assertEqual(self.counts(mtg.GAME, cards), {"mythic": 1, "rare": 2, "foil": 2})

    def test_each_game_counts_its_own_levels(self):
        top = {g: g.counter_tiers[0][1][0] for g in (pokemon.GAME, yugioh.GAME, lorcana.GAME)}
        second = {g: g.counter_tiers[1][1][0] for g in top}
        for g in top:
            with self.subTest(game=g.key):
                cards = [entry(top[g].upper()), entry(second[g]), entry(second[g]), entry("common")]
                got = self.counts(g, cards)
                self.assertEqual((got["mythic"], got["rare"]), (1, 2))   # case doesn't matter

class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(sessions, "SESSIONS", pathlib.Path(self.tmp.name) / "sessions")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def session(self, sid, started, cards=1, ended=None, **info):
        return {"id": sid, "started": started, "ended": ended, "info": info,
                "packs": [{"opened": started, "cards": [{"id": f"c{i}"} for i in range(cards)]}]}

    def test_save_load_delete(self):
        d = self.session("s1", 1.0)
        sessions.save(d)
        self.assertTrue(sessions.exists("s1"))
        self.assertEqual(sessions.load("s1"), d)
        sessions.delete("s1")
        self.assertFalse(sessions.exists("s1"))
        sessions.delete("s1")   # twice is fine

    def test_load_all_newest_first_and_skips_broken_files(self):
        for sid, t in (("a", 1.0), ("b", 3.0), ("c", 2.0)):
            sessions.save(self.session(sid, t))
        (sessions.SESSIONS / "broken.json").write_text("{not json", "utf-8")
        self.assertEqual([s["id"] for s in sessions.load_all()], ["b", "c", "a"])

    def test_latest_open_resumes_and_ends_empty_ones(self):
        sessions.save(self.session("old", 1.0))
        sessions.save(self.session("done", 3.0, ended=4.0))
        sessions.save(self.session("empty", 5.0, cards=0))
        self.assertEqual(sessions.latest_open()["id"], "old")
        self.assertEqual(sessions.load("empty")["ended"], 5.0)   # started, never used: quietly ended

    def test_kinds_in_statistics(self):
        imp, singles, normal = self.session("i", 1), self.session("s", 1, kind="singles"), self.session("n", 1)
        imp["info"] = {"import": True}   # own import (Import/Export → Collection)
        self.assertEqual([sessions.counts_in_stats(d) for d in (imp, singles, normal)], [False, False, True])
        self.assertTrue(sessions.is_import(imp) and sessions.is_singles(singles))

    def test_core_session_saves_and_reloads_identically(self):
        s = core.Session()
        s._price_later = lambda e: None
        s.add_manual({"id": "t1", "name": "A", "set": "TST", "number": "1", "rarity": "rare", "eur": 2.5,
                      "eur_foil": None, "img": "data/card-images/tst/1_0.jpg", "finishes": ["nonfoil"],
                      "booster": True})
        d = s.to_dict()
        sessions.save(d)
        again = core.Session(data=sessions.load(d["id"]))
        self.assertEqual(again.to_dict()["stats"], d["stats"])
        self.assertLess(abs(again.started - time.time()), 60)


if __name__ == "__main__":
    unittest.main()


class SaveLater(unittest.TestCase):
    """sessions.save_later (Log page): written a moment later in the background, read back meanwhile from memory,
    flush() at quitting writes what is pending, a save() of the same log replaces it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(sessions, "SESSIONS", pathlib.Path(self.tmp.name) / "sessions")
        self.p.start()

    def tearDown(self):
        sessions.flush()
        self.p.stop()
        self.tmp.cleanup()

    def session(self, sid, cards=3, **info):
        return {"id": sid, "started": 1.0, "ended": 2.0, "info": info,
                "packs": [{"opened": 1.0, "cards": [{"id": f"c{i}", "foil": False} for i in range(cards)]}]}

    def file(self, sid):
        import json
        return json.loads((sessions.SESSIONS / f"{sid}.json").read_text("utf-8"))

    def test_pending_is_read_back_and_written_later(self):
        sessions.save(self.session("s"))
        changed = self.session("s")
        changed["packs"][0]["cards"][1]["foil"] = True
        with mock.patch.object(sessions, "SAVE_LATER_MS", 60000):   # not by the timer in this test
            sessions.save_later(changed)
            self.assertTrue(self.file("s")["packs"][0]["cards"][1]["foil"] is False)   # not on disk yet
            self.assertTrue(sessions.load("s")["packs"][0]["cards"][1]["foil"])           # but read back
            self.assertTrue([x for x in sessions.load_all() if x["id"] == "s"][0]["packs"][0]["cards"][1]["foil"])
            got = sessions.load("s")
            got["packs"][0]["cards"].append({"id": "x"})   # a caller changing its copy leaves the pending state alone
            self.assertEqual(len(sessions.load("s")["packs"][0]["cards"]), 3)
            sessions.flush()
        self.assertTrue(self.file("s")["packs"][0]["cards"][1]["foil"])
        self.assertFalse(list(sessions.SESSIONS.glob("*.tmp")))   # written through .tmp + replace, nothing left

    def test_timer_writes_by_itself(self):
        with mock.patch.object(sessions, "SAVE_LATER_MS", 30):
            sessions.save_later(self.session("t", title="later"))
            for _ in range(100):
                if (sessions.SESSIONS / "t.json").exists():
                    break
                time.sleep(0.02)
        self.assertEqual(self.file("t")["info"]["title"], "later")

    def test_save_now_replaces_pending_and_delete_drops_it(self):
        with mock.patch.object(sessions, "SAVE_LATER_MS", 60000):
            sessions.save_later(self.session("u", title="old"))
            sessions.save(self.session("u", title="new"))
            sessions.flush()
            self.assertEqual(self.file("u")["info"]["title"], "new")
            sessions.save_later(self.session("v"))
            self.assertTrue(sessions.exists("v"))
            sessions.delete("v")
            sessions.flush()
            self.assertFalse(sessions.exists("v"))
