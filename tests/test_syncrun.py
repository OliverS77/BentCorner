"""The desktop sync run (collection/syncrun.py) between two devices over a vault in memory that behaves like the
server's (version counter, 409 on an old base, 413 when full, a snap replaces everything before it). No network,
no real data: every document lives in a temp folder.

    python -m unittest tests/test_syncrun.py
"""
import base64
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

from collection import syncops, syncrun
from net.vault import VaultError

SEED = base64.b64encode(b"\x07" * 32).decode()


class FakeVault:
    """The server's /v1/vault rules, in memory."""

    def __init__(self, max_bytes=3_000_000):
        self.version, self.items, self.max = 0, [], max_bytes
        self.now = None
        self.puts = 0
        self.deleted = None   # Gordon's deletion note (Weg B): get answers {"deleted": t} until a new put

    def server_ms(self):
        return self.now

    def get(self, settings, since):
        if self.deleted:   # like Gordon's box (040ed43): the normal empty answer plus the field
            return {"version": 0, "snap": 0, "size": 0, "items": [], "deleted": self.deleted}
        return {"version": self.version, "items": [i for i in self.items if i["seq"] > since]}

    def delete(self, when=1793600000):
        """/v1/vault/del: everything gone, only the note stays."""
        self.items, self.version, self.deleted = [], 0, when

    def put(self, settings, kind, base, data):
        if base != self.version:
            raise VaultError(409, "version", {"version": self.version})
        if kind == "add" and sum(len(i["data"]) for i in self.items) + len(data) > self.max:
            raise VaultError(413, "full", {"compact": True})
        self.version += 1
        self.puts += 1
        self.deleted = None   # a new backup: the server forgets its note
        if kind == "snap":
            self.items = []
        self.items.append({"seq": self.version, "kind": kind, "data": data, "t": 0})
        return {"version": self.version}


class Docs(syncrun.Docs):
    """The documents of one device in a temp folder (one game, "mtg")."""

    def __init__(self, settings, root):
        super().__init__(settings, ["mtg"])
        self.root = pathlib.Path(root)

    def path(self, game, *parts):
        return self.root.joinpath(game, *parts)


def deck(did, name, cards, **extra):
    return dict({"id": did, "name": name, "format": "modern", "notes": "", "commanders": [], "pinned": [],
                 "tokens": {}, "created": 1793500000.0, "updated": 1793500000.0,
                 "cards": [{"sid": s, "count": n, "board": "main"} for s, n in cards]}, **extra)


class Device:
    def __init__(self, tmp, name, vault, clock):
        self.settings = {"relay": {"seed": SEED}, "profile": {"id": "p1", "name": name, "back": "b1"}}
        self.docs = Docs(self.settings, pathlib.Path(tmp) / name / "docs")
        self.home = pathlib.Path(tmp) / name
        self.vault, self.clock = vault, clock
        self.eng = self.new_engine()

    def new_engine(self):
        return syncrun.Engine(self.home, self.settings, self.docs, self.vault, now=self.clock)

    def decks(self):
        return {d["id"]: d for d in (self.docs.read("mtg", "decks.json") or {}).get("decks", [])}

    def save_decks(self, decks):
        self.docs.write("mtg", "decks.json", {"decks": decks})
        self.eng.record("mtg", "decks.json")

    def sync(self, answer="merge"):
        self.eng.fetch()
        if self.eng.meta.get("join_hold") and answer:   # both have data: these tests merge (the old behaviour)
            self.eng.join_answer(answer)
            self.eng.fetch()
        self.eng.write_back()
        self.eng.push()


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.t = [1793600000000]
        self.vault = FakeVault()
        clock = lambda: self.t[0]   # noqa: E731
        self.a = Device(self.tmp.name, "a", self.vault, clock)
        self.b = Device(self.tmp.name, "b", self.vault, clock)

    def tick(self, ms=1000):
        self.t[0] += ms

    def test_deletes_leave_the_vault_by_a_snap(self):
        """legal 06.11. (Datenschutz 5a): after a delete the vault's old adds still hold the values – a snap replaces
        them: the first delete at once, then at most once a day."""
        a = self.a
        a.docs.write("mtg", "decks.json", {"decks": [deck("d1", "Burn", [("s1", 3)]), deck("d2", "Elves", [("s2", 1)]),
                                                     deck("d3", "Tron", [("s3", 1)])]})
        a.eng.switch_on()
        a.sync()
        kinds = lambda: [i["kind"] for i in self.vault.items]   # noqa: E731
        self.tick()
        a.save_decks([deck("d2", "Elves", [("s2", 1)]), deck("d3", "Tron", [("s3", 1)])])
        a.sync()
        self.assertEqual(kinds(), ["snap"], "the first delete: a snap, nothing older left")
        self.tick(3600 * 1000)
        a.save_decks([deck("d3", "Tron", [("s3", 1)])])
        a.sync()
        self.assertEqual(kinds(), ["snap", "add"], "within a day: an add")
        self.tick(syncrun.DAY_MS)
        a.sync()
        self.assertEqual(kinds(), ["snap"], "a day later: compacted, even without a new change")
        from net import pairing
        pkg = syncops.unpack(pairing.vault_open_bytes(SEED, self.vault.items[0]["data"]))
        self.assertNotIn("Elves", json.dumps(pkg), "the deleted deck's name is nowhere in the vault")
        self.assertIn("Tron", json.dumps(pkg))

    def test_settings_documents_and_trades_travel(self):
        """Paket 2: price alarms, friends (with their shared boards), notes, open trades reach the other device; a
        board withdrawn on one device deletes the friend's stored list on the other (legal 06.11.)."""
        a, b = self.a, self.b
        a.settings.update(price_alarms=[{"game": "mtg", "kind": "wish", "name": "Bolt", "below": 1.5, "hit": True}],
                          friend_notes={"p1": "from the club"})
        a.settings["relay"]["friends"] = {"F1": {"name": "Max", "status": "ok", "pid": "p1", "sign_pk": "pk",
                                                 "boards": {"mtg/lists": {"key": "k1", "t": 5, "title": ""}}}}
        a.docs.write("mtg", "offers.json", {"offers": [{"id": "tr1", "partner": ["p1", "Max"], "status": "sent",
                                                        "versions": [{"v": 1}], "created": 1793600000.0,
                                                        "updated": 1793600000.0}]})
        a.eng.switch_on()
        a.sync()
        self.tick()
        b.eng.switch_on()
        b.sync()
        self.assertEqual(b.settings["price_alarms"][0]["below"], 1.5)
        self.assertNotIn("hit", b.settings["price_alarms"][0], "whether it was reported stays on A")
        self.assertEqual(b.settings["friend_notes"], {"p1": "from the club"})
        self.assertEqual(b.settings["relay"]["friends"]["F1"]["boards"]["mtg/lists"]["key"], "k1")
        self.assertEqual(b.docs.read("mtg", "offers.json")["offers"][0]["status"], "sent")
        self.tick()
        a.settings["relay"]["friends"]["F1"]["boards"] = {}   # the friend withdrew (board_gone on A)
        a.sync()
        self.tick()
        dropped = []
        from net import relay
        with mock.patch.object(relay, "_drop_list", lambda g, pid: dropped.append((g, pid)) or ("", True)),                 mock.patch.object(syncrun, "_from_relay", lambda g, pid: True):
            b.sync()
        self.assertEqual(dropped, [("mtg", "p1")])
        self.assertEqual(b.settings["relay"]["friends"]["F1"].get("boards"), {})

    def test_only_mailbox_lists_go_with_a_withdrawn_board(self):
        """ports 07.11.: a friend file the user imported himself (source not "relay") stays."""
        import tempfile
        from collection import trade
        with tempfile.TemporaryDirectory() as d:
            folder = pathlib.Path(d)
            with mock.patch.object(trade, "friends_folder", lambda g: folder):
                trade.friend_path(folder, "p1").write_text(json.dumps({"source": "relay"}), "utf-8")
                trade.friend_path(folder, "p2").write_text(json.dumps({"source": "csv"}), "utf-8")
                self.assertTrue(syncrun._from_relay("mtg", "p1"))
                self.assertFalse(syncrun._from_relay("mtg", "p2"))
                self.assertFalse(syncrun._from_relay("mtg", "p3"))

    def test_a_withdrawn_offer_is_withdrawn_everywhere_and_gone_from_the_vault(self):
        """legal (Weg a): an offer withdrawn on one device is „withdrawn“ on the other; deleted, nothing of it stays in
        the vault (purge kind: the next push is a snap without its values)."""
        a, b = self.a, self.b
        offer = {"id": "tr9", "partner": ["p1", "Max"], "status": "sent", "versions": [{"v": 1, "give": ["Bolt"]}],
                 "created": 1793600000.0, "updated": 1793600000.0}
        a.docs.write("mtg", "offers.json", {"offers": [offer]})
        a.eng.switch_on()
        a.sync()
        self.tick()
        b.eng.switch_on()
        b.sync()
        self.tick()
        a.docs.write("mtg", "offers.json", {"offers": [dict(offer, status="withdrawn", updated=1793600100.0)]})
        a.sync()
        self.tick()
        b.sync()
        self.assertEqual(b.docs.read("mtg", "offers.json")["offers"][0]["status"], "withdrawn")
        self.tick()
        b.docs.write("mtg", "offers.json", {"offers": []})   # cleared on B
        b.sync()
        self.tick()
        a.sync()
        self.assertEqual(a.docs.read("mtg", "offers.json")["offers"], [])
        from net import pairing
        kinds = [i["kind"] for i in self.vault.items]
        self.assertEqual(kinds[0], "snap", "the delete of a purge kind: a snap at once")
        everything = json.dumps([syncops.unpack(pairing.vault_open_bytes(SEED, i["data"])) for i in self.vault.items])
        self.assertNotIn("Bolt", everything, "nothing of the withdrawn offer left in the vault")
        self.assertNotIn("withdrawn", everything)

    def test_device_list(self):
        """lead 07.11.: every device lists itself; seen at most once a day; after „Gerät entfernen“ only this one."""
        a, b = self.a, self.b
        a.settings["device_name"] = "Olivers PC"
        b.settings["device_name"] = "Laptop"
        a.eng.switch_on()
        a.sync()
        b.eng.switch_on()
        b.sync()
        self.tick()
        a.sync()
        names = lambda d: [e["name"] for e in d.eng.devices()]   # noqa: E731
        self.assertEqual(names(a), ["Olivers PC", "Laptop"])
        self.assertTrue(a.eng.devices()[0]["me"])
        before = len(a.eng.pending)
        self.tick(3600 * 1000)
        a.eng.catch_up()
        self.assertEqual(len(a.eng.pending), before, "the same day: no new op")
        self.tick(syncrun.DAY_MS)
        a.eng.catch_up()
        self.assertGreater(len(a.eng.pending), before, "a new day: seen grows once")
        a.eng.drop_other_devices()
        self.assertEqual(names(a), ["Olivers PC"])

    def test_two_devices_meet_and_keep_everything(self):
        a, b = self.a, self.b
        a.docs.write("mtg", "decks.json", {"decks": [deck("d1", "Burn", [("s1", 3)])]})
        b.docs.write("mtg", "decks.json", {"decks": [deck("d1", "Burn", [("s1", 3)]), deck("d9", "Only B", [("s7", 2)],
                                                                                          local_view="grid")]})
        a.eng.switch_on()
        a.sync()                          # first device: everything seeded
        self.tick()
        b.eng.switch_on()
        b.sync()                          # second: only what the vault does not know
        self.tick()
        a.sync()
        for dev in (a, b):
            ds = dev.decks()
            self.assertEqual(sorted(ds), ["d1", "d9"])
            self.assertEqual(ds["d1"]["cards"], [{"sid": "s1", "count": 3, "board": "main"}])   # not 3 + 3
        self.assertEqual(b.decks()["d9"]["local_view"], "grid")   # B's local field stays
        self.assertNotIn("local_view", a.decks()["d9"])             # and never travels

    def test_edits_both_ways_and_a_conflict(self):
        a, b = self.a, self.b
        a.docs.write("mtg", "decks.json", {"decks": [deck("d1", "Burn", [("s1", 3)])]})
        a.eng.switch_on()
        a.sync()
        b.eng.switch_on()
        b.sync()
        self.tick()
        ds = a.decks()
        ds["d1"]["name"] = "Burn A"
        ds["d1"]["cards"][0]["count"] = 4               # A: +1
        a.save_decks(list(ds.values()))
        self.tick()
        ds = b.decks()
        ds["d1"]["notes"] = "from B"
        ds["d1"]["cards"].append({"sid": "s2", "count": 1, "board": "side"})
        b.save_decks(list(ds.values()))
        a.sync()
        b.sync()                                         # B: 409 inside, fetches A first, then sends
        a.sync()
        for dev in (a, b):
            d1 = dev.decks()["d1"]
            self.assertEqual((d1["name"], d1["notes"]), ("Burn A", "from B"))
            self.assertEqual(sorted((c["sid"], c["count"]) for c in d1["cards"]), [("s1", 4), ("s2", 1)])
        self.assertEqual(a.eng.state.sum("mtg/decks"), b.eng.state.sum("mtg/decks"))

    def test_409_fetches_then_sends(self):
        a, b = self.a, self.b
        a.eng.switch_on()
        a.sync()
        b.eng.switch_on()
        b.sync()
        self.tick()
        b.save_decks([deck("db", "B", [("s1", 1)])])
        b.eng.fetch()
        b.eng.write_back()
        a.save_decks([deck("da", "A", [("s2", 1)])])
        a.sync()                                  # A writes between B's fetch and B's push
        puts = self.vault.puts
        b.eng.push()                              # 409 inside: B pulls A's add, then sends
        self.assertEqual(self.vault.puts, puts + 1)
        b.sync()
        a.sync()
        self.assertEqual(sorted(a.decks()), ["da", "db"])
        self.assertEqual(sorted(b.decks()), ["da", "db"])

    def test_save_while_sending_neither_waits_nor_gets_lost(self):
        import threading
        a, b = self.a, self.b
        a.eng.switch_on()
        a.sync()
        b.eng.switch_on()
        b.sync()
        a.sync()   # A up to date (B sent its profile), so the push below gets no 409
        self.tick()
        a.save_decks([deck("d1", "first", [("s1", 1)])])
        done = []
        real_put = self.vault.put

        def put(settings, kind, base, data):
            # the main thread saves while the request is on its way: it must not wait for the network
            t = threading.Thread(target=lambda: done.append(a.save_decks(list(a.decks().values()) +
                                                                         [deck("d2", "meanwhile", [("s2", 1)])])))
            t.start()
            t.join(2)
            self.assertFalse(t.is_alive(), "record() waited for the network")
            self.vault.put = real_put
            return real_put(settings, kind, base, data)
        self.vault.put = put
        self.assertEqual(a.eng.push(), 2)                    # the ops of d1 (deck + card)
        self.assertEqual(len(a.eng.pending), 2)              # d2's stay for the next push
        a.sync()
        b.sync()
        self.assertEqual(sorted(b.decks()), ["d1", "d2"])

    def test_save_hook(self):
        a = self.a
        a.eng.switch_on()
        a.sync()
        calls = []
        self.addCleanup(setattr, syncrun, "ENGINE", None)
        self.addCleanup(setattr, syncrun, "ON_RECORD", None)
        syncrun.ENGINE, syncrun.ON_RECORD = a.eng, lambda: calls.append(1)
        doc = {"decks": [deck("d1", "Burn", [("s1", 1)])]}
        a.docs.write("mtg", "decks.json", doc)
        syncrun.saved(a.docs.path("mtg", "decks.json"), doc)            # as decks.save does
        self.assertEqual((len(a.eng.pending), calls), (2, [1]))
        syncrun.saved(pathlib.Path(self.tmp.name) / "elsewhere" / "decks.json", doc)   # not a game folder: nothing
        syncrun.saved(a.docs.path("mtg", "collection.json"), {})          # not synced: nothing
        self.assertEqual(len(a.eng.pending), 2)
        a.eng.record = None                                               # a broken engine never breaks a save
        syncrun.saved(a.docs.path("mtg", "decks.json"), doc)

    def test_wrong_checksum_heals(self):
        a, b = self.a, self.b
        a.eng.switch_on()
        a.sync()
        b.eng.switch_on()
        b.sync()
        self.tick()
        a.save_decks([deck("d1", "Burn", [("s1", 2)])])
        a.sync()
        from net import pairing
        item = self.vault.items[-1]               # a broken client: the same ops, a wrong sum
        pkg = syncops.unpack(pairing.vault_open_bytes(SEED, item["data"]))
        pkg["sum"] = {k: "0" * 64 for k in pkg["sum"]}
        item["data"] = pairing.vault_seal_bytes(SEED, syncops.pack(pkg))
        r = b.eng.fetch()
        self.assertTrue(r["healed"])
        b.eng.write_back()
        self.assertEqual(b.decks()["d1"]["cards"], [{"sid": "s1", "count": 2, "board": "main"}])

    def test_offline_change_and_restart(self):
        a, b = self.a, self.b
        a.docs.write("mtg", "decks.json", {"decks": [deck("d1", "Burn", [("s1", 3)])]})
        a.eng.switch_on()
        a.sync()
        b.eng.switch_on()
        b.sync()
        self.tick(3600_000)
        ds = b.decks()                                   # B offline: deleted the deck
        b.save_decks([d for d in ds.values() if d["id"] != "d1"])
        b.eng = b.new_engine()                           # program restarted: everything from disk
        b.sync()
        a.sync()
        self.assertEqual(a.decks(), {})

    def test_unrecorded_write_is_caught_up(self):
        a, b = self.a, self.b
        a.eng.switch_on()
        a.sync()
        b.eng.switch_on()
        b.sync()
        a.docs.write("mtg", "decks.json", {"decks": [deck("d2", "Restored", [("s3", 1)])]})   # e.g. undo, no record()
        a.sync()
        b.sync()
        self.assertEqual(sorted(b.decks()), ["d2"])

    def test_profile_is_global(self):
        a, b = self.a, self.b
        a.eng.switch_on()
        a.sync()
        b.eng.switch_on()
        b.sync()
        self.tick()
        a.settings["profile"]["name"] = "Oli"
        a.eng.record("*", syncrun.PROFILE)
        a.sync()
        b.sync()
        self.assertEqual(b.settings["profile"]["name"], "Oli")

    def test_full_vault_compacts_to_a_snap(self):
        self.vault.max = 3000
        a, b = self.a, self.b
        a.eng.switch_on()
        a.sync()
        b.eng.switch_on()
        b.sync()
        for i in range(6):
            self.tick()
            a.save_decks(list(a.decks().values()) + [deck(f"n{i}", "x" * 400, [("s1", 1)])])
            a.sync()
        self.assertEqual(self.vault.items[0]["kind"], "snap")   # the vault was compacted
        b.sync()
        self.assertEqual(len(b.decks()), 6)
        fresh = Device(self.tmp.name, "c", self.vault, lambda: self.t[0])   # a third device: from the snap
        fresh.settings["relay"]["seed"] = SEED
        fresh.eng.switch_on()
        fresh.sync()
        self.assertEqual(len(fresh.decks()), 6)

    def test_nothing_recorded_before_the_first_fetch(self):
        a = self.a
        a.eng.switch_on()
        a.docs.write("mtg", "decks.json", {"decks": [deck("d1", "Burn", [("s1", 3)])]})
        self.assertEqual(a.eng.record("mtg", "decks.json"), 0)   # not seeded yet: the seed takes it
        a.sync()
        self.assertEqual(list(a.eng.state.kinds["mtg/deckcards"]), ["d1|s1|main"])
        self.assertEqual(a.eng.state.view("mtg/deckcards")["d1|s1|main"], {"n": 3})   # once, not twice

    def test_foreign_identity_items_are_skipped(self):
        a = self.a
        a.eng.switch_on()
        a.sync()
        other = syncops.pack({"v": 1, "t": "add", "dev": "zzzz", "ops": []})
        from net import pairing
        self.vault.items.append({"seq": self.vault.version + 1, "kind": "add", "t": 0,
                                 "data": pairing.vault_seal_bytes(base64.b64encode(os.urandom(32)).decode(), other)})
        self.vault.version += 1
        a.sync()   # no exception: logged and skipped
        self.assertEqual(a.eng.meta["version"], self.vault.version)


class EmptiedVault(unittest.TestCase):
    """SYNC-PLAN §6 (lead 06.11.): the vault emptied on the server (another device deleted it, the test instance was
    emptied) – never silently on: nothing is sent until the user says "back it up again", then one snap."""
    setUp, tick = Run.setUp, Run.tick

    def test_asks_instead_of_carrying_on(self):
        a = self.a
        a.eng.switch_on()
        a.save_decks([deck("d1", "Burn", [("s1", 3)])])
        a.sync()
        self.assertGreater(self.vault.version, 0)
        self.vault.items, self.vault.version = [], 0          # emptied on the server
        self.tick()
        a.save_decks([deck("d1", "Burn", [("s1", 4)])])
        puts = self.vault.puts
        with self.assertRaises(syncrun.VaultEmptied):
            a.sync()
        self.assertEqual(self.vault.puts, puts, "nothing sent before the user decides")
        self.assertEqual(self.vault.items, [])
        self.assertGreater(a.eng.meta["version"], 0, "this device's state untouched")
        with self.assertRaises(syncrun.VaultEmptied):        # and it keeps asking, it doesn't carry on by itself
            a.sync()

    def test_back_it_up_again_sends_one_snap_others_get_everything(self):
        a = self.a
        a.eng.switch_on()
        a.save_decks([deck("d1", "Burn", [("s1", 3)]), deck("d2", "Elves", [("s2", 4)])])
        a.sync()
        self.vault.items, self.vault.version = [], 0
        with self.assertRaises(syncrun.VaultEmptied):
            a.sync()
        a.eng.restore_vault()
        a.sync()
        self.assertEqual([i["kind"] for i in self.vault.items], ["snap"])
        b = self.b
        b.settings["relay"]["seed"] = SEED
        b.eng.switch_on()
        b.sync()
        self.assertEqual(sorted(b.decks()), ["d1", "d2"])


class DeletedAndBackedUpAgain(unittest.TestCase):
    """Weg B (lead/legal/Gordon 06.11.) and ports' finding: deliberately deleted -> off, never "back it up?";
    emptied and already backed up anew by another device -> take that, never a second snap over it."""
    setUp, tick = Run.setUp, Run.tick

    def both_synced(self):
        a, b = self.a, self.b
        for d in (a, b):
            d.eng.switch_on()
        a.save_decks([deck("d1", "Burn", [("s1", 3)])])
        a.sync()
        b.sync()
        self.tick()
        b.save_decks([deck("d1", "Burn", [("s1", 3)]), deck("d2", "Elves", [("s2", 4)])])
        b.sync()
        a.sync()
        self.assertEqual(sorted(a.decks()), ["d1", "d2"])

    def test_a_vault_access_is_remembered(self):
        """legal/lead 07.11.: the 5-month warning counts from this device's last vault access (get or put)."""
        self.both_synced()
        seen = self.b.eng.meta.get("vault_seen")
        self.assertTrue(seen)
        self.tick(5000)
        self.b.sync()
        self.assertGreater(self.b.eng.meta["vault_seen"], seen)
        self.assertIsNone(syncrun.expiry(self.b.eng.meta, self.b.eng.meta["vault_seen"] + 1))

    def test_deleted_elsewhere_turns_off_without_asking(self):
        self.both_synced()
        self.vault.delete()
        puts = self.vault.puts
        with self.assertRaises(syncrun.VaultDeleted):
            self.b.sync()
        self.b.eng.deleted_elsewhere()
        self.assertFalse(self.b.eng.on())
        self.assertEqual(self.vault.puts, puts, "nothing sent – the deletion holds")
        self.assertEqual(sorted(self.b.decks()), ["d1", "d2"], "this device's data stays")

    def test_a_new_device_also_sees_the_deletion(self):
        self.vault.delete()
        self.b.eng.switch_on()
        with self.assertRaises(syncrun.VaultDeleted):
            self.b.sync()

    def test_switching_on_again_by_hand_backs_up_anew_and_clears_the_note(self):
        self.both_synced()
        self.vault.delete()
        with self.assertRaises(syncrun.VaultDeleted):
            self.b.sync()
        self.b.eng.deleted_elsewhere()
        self.b.eng.switch_on()   # the user's own choice
        self.b.sync()
        self.assertIsNone(self.vault.deleted, "the new backup made the server forget its note")
        self.assertEqual([i["kind"] for i in self.vault.items], ["snap"])

    def test_one_device_backs_up_again_the_other_takes_it_without_asking(self):
        self.both_synced()
        self.vault.items, self.vault.version = [], 0           # emptied without a note (server, test instance)
        with self.assertRaises(syncrun.VaultEmptied):
            self.a.sync()
        self.a.eng.restore_vault()
        self.a.sync()
        self.b.sync()                                          # older version than b had – but a snap: take it
        self.assertEqual(sorted(self.b.decks()), ["d1", "d2"])
        self.assertEqual([i["kind"] for i in self.vault.items], ["snap"])
        self.assertIsNone(self.b.eng.meta.get("aside_last"), "the same state: nothing to set aside")

    def test_backed_up_anew_without_what_this_device_had_sets_it_aside(self):
        """legal (way a, 07.11.): b synced a deck a never saw; a backs up anew – b's deck is not replaced silently:
        b's state goes aside first (the same line as after a takeover)."""
        self.both_synced()
        self.tick()
        self.b.save_decks([deck("d1", "Burn", [("s1", 3)]), deck("d2", "Elves", [("s2", 4)]),
                           deck("d3", "Mono", [("s3", 1)])])
        self.b.sync()                                          # d3 in the vault – a doesn't fetch it
        self.vault.items, self.vault.version = [], 0
        with self.assertRaises(syncrun.VaultEmptied):
            self.a.sync()
        self.a.eng.restore_vault()
        self.a.sync()
        self.b.sync()
        self.assertEqual(sorted(self.b.decks()), ["d1", "d2"], "the new backup is taken …")
        self.assertTrue(self.b.eng.meta.get("aside_last"), "… after b's state went aside")
        self.assertEqual(self.b.eng.meta.get("aside_last_why"), "takeover")

    def test_only_the_device_list_differs_nothing_aside(self):
        """ports 07.11.: a new „seen“ of the device that backs up anew (the next day) is no reason to set aside – the
        device list (and friends' data) never goes aside, so it isn't compared."""
        self.both_synced()
        self.tick(syncrun.DAY_MS + 1000)                      # the next day: a writes a new „seen“
        self.vault.items, self.vault.version = [], 0
        with self.assertRaises(syncrun.VaultEmptied):
            self.a.sync()
        self.a.eng.restore_vault()
        self.a.sync()
        self.b.sync()
        self.assertEqual(sorted(self.b.decks()), ["d1", "d2"])
        self.assertIsNone(self.b.eng.meta.get("aside_last"), "only the device list differed")

    def test_both_said_back_it_up_the_second_one_takes_the_first(self):
        self.both_synced()
        self.vault.items, self.vault.version = [], 0
        for d in (self.a, self.b):
            with self.assertRaises(syncrun.VaultEmptied):
                d.sync()
            d.eng.restore_vault()                              # both say yes
        self.a.sync()
        self.b.sync()
        self.assertEqual([i["kind"] for i in self.vault.items].count("snap"), 1, "never a second snap over the first")
        self.assertEqual(sorted(self.b.decks()), ["d1", "d2"])

    def test_race_the_other_backs_up_between_fetch_and_send(self):
        self.both_synced()
        self.vault.items, self.vault.version = [], 0
        for d in (self.a, self.b):
            with self.assertRaises(syncrun.VaultEmptied):
                d.sync()
        self.b.eng.restore_vault()
        self.b.eng.fetch()                                     # b still sees it empty …
        self.a.eng.restore_vault()
        self.a.sync()                                          # … a backs it up in between …
        self.b.eng.write_back()
        self.b.eng.push()                                      # … b's snap gets 409: takes a's instead
        self.assertEqual([i["kind"] for i in self.vault.items].count("snap"), 1)
        self.assertEqual(sorted(self.b.decks()), ["d1", "d2"])


class Switch(unittest.TestCase):
    """BC_SYNC only from the source: a built exe ignores it (lead 06.11. – nobody switches the sync on from outside)."""

    def test_source_run_with_env(self):
        with mock.patch.dict(os.environ, {"BC_SYNC": "1"}), mock.patch.object(syncrun, "SYNC_TEST", False):
            self.assertTrue(syncrun.available())

    def test_frozen_exe_ignores_env(self):
        with mock.patch.dict(os.environ, {"BC_SYNC": "1"}), mock.patch.object(syncrun, "SYNC_TEST", False), \
                mock.patch.object(sys, "frozen", True, create=True):
            self.assertFalse(syncrun.available())

    def test_off_without_anything(self):
        env = {k: v for k, v in os.environ.items() if k != "BC_SYNC"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(syncrun, "SYNC_TEST", False):
            self.assertFalse(syncrun.available())

    def test_repo_constant_is_off(self):
        """Only a test build sets SYNC_TEST, in its own copy – the repo (and so every release build) keeps False."""
        src = pathlib.Path(syncrun.__file__).read_text("utf-8").replace("\r\n", "\n")
        self.assertIn("\nSYNC_TEST = False\n", src)


if __name__ == "__main__":
    unittest.main()
