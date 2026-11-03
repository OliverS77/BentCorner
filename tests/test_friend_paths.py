"""Friend data never leaves its folder: ids and games come from friends over the net and become file/folder names.
"../settings", absolute paths, drive letters or a NUL byte must be refused – in trade.friend_path/friends_folder and
already when a list parcel arrives (relay.apply), before anything is written.

    python -m unittest tests/test_friend_paths.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import trade
from net import relay

BAD_IDS = ["../settings", "..\\settings", "C:/x", "C:\\x", "/etc/passwd", "a\0b", "", "a.b", "x" * 41, "a/b", "%2e%2e"]
GOOD_IDS = ["0f3a9c1e2b7d4e5fa6b7c8d9e0f1a2b3", "7F3A-21C9-0B44-E1D2", "p-ben", "list_1"]
BAD_GAMES = ["../..", "mtg/../..", "", "C:/", "..\\..", "nonsense"]
FRIEND = "A" * 16


class Paths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name) / "friends"
        self.dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_bad_ids_are_refused(self):
        for fid in BAD_IDS:
            with self.assertRaises(ValueError, msg=repr(fid)):
                trade.friend_path(self.dir, fid)

    def test_good_ids_stay_inside(self):
        for fid in GOOD_IDS:
            self.assertEqual(trade.friend_path(self.dir, fid).parent.resolve(), self.dir.resolve())

    def test_bad_games_are_refused(self):
        for game in BAD_GAMES:
            with self.assertRaises(ValueError, msg=repr(game)):
                trade.friends_folder(game)

    def test_save_and_read_refuse_bad_ids(self):
        with mock.patch.object(trade, "FRIENDS", self.dir):
            for fid in BAD_IDS:
                with self.assertRaises(ValueError, msg=repr(fid)):
                    trade.save_friend({"id": fid, "name": "x"})
                self.assertIsNone(trade.friend(fid))
                trade.remove_friend(fid)   # quietly nothing
            trade.save_friend({"id": "p-ok", "name": "ok"})
            self.assertEqual(trade.friend("p-ok")["name"], "ok")
        outside = [p for p in pathlib.Path(self.tmp.name).rglob("*") if p.is_file() and p.parent != self.dir]
        self.assertEqual(outside, [])

    def test_imported_file_with_strange_id_gets_a_new_one(self):
        out = trade.friend_from_import({"kind": "bentcorner", "data": {"id": "../../x", "c": [], "w": []}})
        self.assertRegex(out["id"], r"^[0-9a-f]{32}$")


class ListParcel(unittest.TestCase):
    """relay.apply: a list from an accepted friend with a crafted id/pid/game writes nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name) / "friends"
        self.s = {}
        self.p = [mock.patch.object(trade, "FRIENDS", self.dir),
                  mock.patch.object(relay, "fill_names", lambda d: None)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def friend(self, pid):
        relay.friends(self.s)[FRIEND] = {"status": "ok", "name": "Bene", "pid": pid, "sign_pk": "PK"}

    def parcel(self, body_id, game="mtg"):
        return relay.apply(self.s, {"from": FRIEND, "kind": "list", "_sign_pk": "PK", "game": game,
                                    "body": {"app": "BentCorner", "id": body_id, "c": [], "w": []}})

    def written(self):
        return [p for p in pathlib.Path(self.tmp.name).rglob("*") if p.is_file()]

    def test_crafted_ids_write_nothing(self):
        for bad in BAD_IDS:
            self.friend("")              # no pid known yet: then only the id check protects
            self.assertIsNone(self.parcel(bad), repr(bad))
            self.friend(bad)             # even if the crafted id came with the friend request
            self.assertIsNone(self.parcel(bad), repr(bad))
        self.assertEqual(self.written(), [])

    def test_crafted_game_writes_nothing(self):
        self.friend("p-ben")
        for game in [g for g in BAD_GAMES if g]:   # "" = older apps without a game field: means Magic (safe)
            self.assertIsNone(self.parcel("p-ben", game=game), repr(game))
        self.assertEqual(self.written(), [])

    def test_friend_request_drops_a_crafted_pid(self):
        person = relay._clean_person({"name": "x", "pid": "../../settings"})
        self.assertEqual(person["pid"], "")
        self.assertEqual(relay._clean_person({"pid": "p-ok"})["pid"], "p-ok")

    def test_normal_list_still_arrives(self):
        self.friend("p-ben")
        out = self.parcel("p-ben")
        self.assertEqual(out["kind"], "list")
        self.assertTrue((self.dir / "p-ben.json").exists())


if __name__ == "__main__":
    unittest.main()
