"""Set aside (collection/syncaside.py, SYNC-LOGS §4; legal/lead 07.11.): several states side by side, never replaced,
never deleted by themselves; restoring sets the current state aside first; only own data – nothing friends shared.

    python -m unittest tests/test_syncaside.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import syncaside


class Aside(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        p = mock.patch.object(syncaside, "root", lambda: root / "beiseite")
        p.start()
        self.addCleanup(p.stop)
        self.mine = {"mtg": root / "mtg" / "my-data"}
        self.settings = {"profile": {"name": "Oli"}, "price_alarms": [{"name": "Bolt", "below": 1.0}],
                         "list_alarms": [{"list": "w1", "below": 2.0}],
                         "relay": {"friends": {"F1": {"boards": {"mtg/lists": {"key": "secret"}}}}}}
        self.write("A")

    def write(self, deck):
        m = self.mine["mtg"]
        (m / "sessions").mkdir(parents=True, exist_ok=True)
        (m / "friends").mkdir(parents=True, exist_ok=True)
        (m / "decks.json").write_text(json.dumps({"decks": [{"id": deck, "name": deck}]}), "utf-8")
        (m / "collection.json").write_text(json.dumps({"items": [{"id": "x", "count": 3}]}), "utf-8")
        (m / "sessions" / f"s{deck}.json").write_text(json.dumps({"id": f"s{deck}"}), "utf-8")
        (m / "friends" / "p1.json").write_text(json.dumps({"name": "Max", "cards": [[1]]}), "utf-8")

    def test_two_times_two_states(self):
        a = syncaside.put(self.mine, self.settings, "theirs", "phone", now=1793600000)
        self.write("B")
        b = syncaside.put(self.mine, self.settings, "theirs", "phone", now=1793600000)   # the same second
        self.assertNotEqual(a, b)
        got = syncaside.list_all()
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["what"], {"decks": 1, "lists": 0, "binders": 0, "cards": 3})
        self.assertEqual({e["other"] for e in got}, {"phone"})

    def test_only_own_data(self):
        sid = syncaside.put(self.mine, self.settings, "takeover", "pc")
        f = syncaside.folder(sid)
        files = {str(p.relative_to(f)).replace("\\", "/") for p in f.rglob("*") if p.is_file()}
        self.assertNotIn("games/mtg/friends/p1.json", files)
        self.assertNotIn("secret", (f / "settings.json").read_text("utf-8"))
        self.assertIn("games/mtg/decks.json", files)
        self.assertIn("games/mtg/sessions/sA.json", files)
        self.assertEqual(json.loads((f / "settings.json").read_text("utf-8"))["profile"], {"name": "Oli"})

    def test_restore_sets_the_current_state_aside_and_never_brings_friend_data(self):
        old = syncaside.put(self.mine, self.settings, "offline")
        self.write("B")
        (self.mine["mtg"] / "friends" / "p1.json").unlink()   # the friend withdrew meanwhile
        self.settings["relay"]["friends"] = {}
        self.settings["profile"] = {"name": "Neu"}
        self.settings["list_alarms"] = []
        current = syncaside.restore(old, self.mine, self.settings)
        m = self.mine["mtg"]
        self.assertEqual(json.loads((m / "decks.json").read_text("utf-8"))["decks"][0]["id"], "A")
        self.assertEqual(sorted(p.name for p in (m / "sessions").iterdir()), ["sA.json"])
        self.assertFalse((m / "friends" / "p1.json").exists(), "a withdrawn friend's data never comes back")
        self.assertEqual(self.settings["relay"]["friends"], {})
        self.assertEqual(self.settings["profile"], {"name": "Oli"})
        self.assertEqual(self.settings["list_alarms"], [{"list": "w1", "below": 2.0}], "list alarms come back too")
        self.assertEqual(len(syncaside.list_all()), 2, "the old one stays, the current one is aside too")
        back = syncaside.folder(current)
        self.assertEqual(json.loads((back / "games" / "mtg" / "decks.json").read_text("utf-8"))["decks"][0]["id"],
                         "B")

    def trades(self, offer, ticket_id):
        m = self.mine["mtg"]
        (m / "offers.json").write_text(json.dumps({"version": 1, "offers": [{"id": offer, "status": "sent"}]}), "utf-8")
        (m / "pending-trades.json").write_text(json.dumps({"version": 1, "pending": [{
            "ticket": {"id": ticket_id, "f": ["pme", "Oli"], "o": ["pfriendx", "Max"], "m": 550,
                       "from": "ADDRFRIEND000001", "sign_pk": "KEYOFTHEFRIEND=", "box": "MAILBOXID9"},
            "give": [["M10", "146", "en", 0, 2, "Bolt", "mtg", {"addr": "ADDRFRIEND000001"}]], "get": [],
            "partner": ["pfriendx", "Max"], "foreign": {"game": "pokemon", "addr": "ADDRFRIEND000001"},
            "t": 1793600000}]}), "utf-8")

    def test_trades_and_list_alarms(self):
        """lead/legal 07.11.: list alarms and trade offers go aside and come back; open tickets only to look at and
        delete – the copy keeps the friend's name, the cards and the amount, NO keys, addresses or mailbox ids – and
        bringing a state back leaves this device's current tickets as they are."""
        self.trades("O1", "T1")
        sid = syncaside.put(self.mine, self.settings, "takeover")
        raw = (syncaside.folder(sid) / "games" / "mtg" / "pending-trades.json").read_text("utf-8")
        for secret in ("ADDRFRIEND000001", "KEYOFTHEFRIEND", "MAILBOXID9", "pfriendx", "foreign"):
            self.assertNotIn(secret, raw)
        self.assertEqual(syncaside.tickets(sid), {"mtg": [{"id": "T1", "partner": "Max", "t": 1793600000, "get": [],
                                                           "give": [["M10", "146", "en", 0, 2, "Bolt"]],
                                                           "money": 550}]})
        self.trades("O2", "T2")
        self.settings["list_alarms"] = []
        syncaside.restore(sid, self.mine, self.settings)
        m = self.mine["mtg"]
        self.assertEqual(json.loads((m / "offers.json").read_text("utf-8"))["offers"][0]["id"], "O1")
        self.assertEqual(self.settings["list_alarms"], [{"list": "w1", "below": 2.0}])
        now = json.loads((m / "pending-trades.json").read_text("utf-8"))["pending"]
        self.assertEqual(now[0]["ticket"]["id"], "T2", "open tickets are never brought back – the current ones stay")
        self.assertTrue(syncaside.ticket_delete(sid, "mtg", "T1"))
        self.assertEqual(syncaside.tickets(sid), {})
        self.assertFalse(syncaside.ticket_delete(sid, "mtg", "T1"))

    def test_a_failed_copy_leaves_no_half_state(self):
        with mock.patch.object(syncaside.shutil, "copytree", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                syncaside.put(self.mine, self.settings, "theirs")
        self.assertEqual(syncaside.list_all(), [])
        self.assertEqual(list(syncaside.root().iterdir()), [], "no half copy left")

    def test_delete_and_unknown_ids(self):
        sid = syncaside.put(self.mine, self.settings, "theirs")
        with self.assertRaises(KeyError):
            syncaside.folder("..")
        syncaside.delete(sid)
        self.assertEqual(syncaside.list_all(), [])


if __name__ == "__main__":
    unittest.main()


class TicketMoney(unittest.TestCase):
    def test_both_directions(self):
        """The amount keeps its direction (ticket.m in cents from the issuer f to o): + I pay, − I get."""
        import tempfile as tf
        with tf.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "pending-trades.json"
            rows = [{"ticket": {"id": "A", "f": ["pme", "Oli"], "m": 300}, "partner": ["pmax", "Max"]},
                    {"ticket": {"id": "B", "f": ["pmax", "Max"], "m": 300}, "partner": ["pmax", "Max"]}]
            p.write_text(json.dumps({"pending": rows}), "utf-8")
            got = {r["id"]: r["money"] for r in syncaside._tickets_of(p)}
        self.assertEqual(got, {"A": 300, "B": -300})
