"""The collection in the desktop sync run (collection/syncrun.py + synclogs.py, docs/web/SYNC-LOGS.md): two devices
over the in-memory vault of test_syncrun, every document in a temp folder.

lead 07.11.: the transition (doubled µs moved apart, „By hand“ logs with the device id) never runs with the switch
off, runs at the first sync, makes a silent backup first and is atomic – an abort leaves the old files whole.

    python -m unittest tests/test_synclogs_run.py
"""
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import manual, synclogs, syncrun
from tests.test_logsum import card, scan_log
from tests.test_syncrun import FakeVault, SEED

T = 1793600000.0


class LogDocs(syncrun.Docs):
    def __init__(self, settings, root):
        super().__init__(settings, ["mtg"])
        self.root = pathlib.Path(root)
        self.backups = []

    def path(self, game, *parts):
        return self.root.joinpath(game, *parts)

    def card_of(self, game):
        return lambda cid: {"img": f"{cid}.jpg", "rarity": "rare"}

    def backup(self, reason):
        dest = self.root.parent / f"backup-{len(self.backups)}"
        dest.mkdir(parents=True)
        self.backups.append(reason)
        return dest


class Device:
    def __init__(self, tmp, name, vault, clock):
        self.settings = {"relay": {"seed": SEED}, "profile": {"id": "p1", "name": name}}
        self.home = pathlib.Path(tmp) / name
        self.docs = LogDocs(self.settings, self.home / "docs")
        self.vault, self.clock = vault, clock
        self.eng = syncrun.Engine(self.home, self.settings, self.docs, vault, now=clock)

    def mine(self, *parts):
        return self.docs.path("mtg", *parts)

    def save_log(self, d):
        p = self.mine("sessions", f"{d['id']}.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d), "utf-8")

    def save_coll(self, items, hidden=()):
        self.mine().mkdir(parents=True, exist_ok=True)
        self.mine("collection.json").write_text(json.dumps({"version": 1, "items": items, "hidden": list(hidden)}),
                                                "utf-8")

    def data(self):
        return self.docs.read_logs("mtg")

    def library(self):
        d = self.data()
        return synclogs.library(synclogs.explode(d["logs"], d["bookings"], d["items"]))

    def coll(self):
        return synclogs.items_now(self.data()["items"])

    def sync(self, answer="merge"):
        self.eng.fetch()
        if self.eng.meta.get("join_hold") and answer:   # both have data: these tests merge (the old behaviour)
            self.eng.join_answer(answer)
            self.eng.fetch()
        self.eng.write_back()
        self.eng.push()

    def files(self):
        return {str(p.relative_to(self.mine())): p.read_text("utf-8") for p in self.mine().rglob("*") if p.is_file()}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.t = [int(T * 1000)]
        self.vault = FakeVault()
        clock = lambda: self.t[0]   # noqa: E731
        self.a = Device(self.tmp.name, "a", self.vault, clock)
        self.b = Device(self.tmp.name, "b", self.vault, clock)
        self.addCleanup(lambda: synclogs.SUFFIX.__setitem__(0, ""))

    def tick(self, ms=1000):
        self.t[0] += ms

    def scan(self, dev, sid, names, when=T):
        log = scan_log(sid, names, when)
        dev.save_log(log)
        items = dev.data()["items"]
        for i, e in enumerate(log["packs"][0]["cards"]):
            items.append(dict(card(e["name"]), uid=f"{dev.home.name}{sid[-2:]}{i}", lang="en", foil=False, count=1,
                              added=e["added"], src=f"{sid}/{e['added']!r}", cond="near_mint"))
        dev.save_coll(items, dev.data()["hidden"])
        return log


class SwitchOff(Base):
    def test_off_nothing_changes_and_ids_stay(self):
        self.scan(self.a, "2026-11-07_10-00-00", ["A"])
        before = self.a.files()
        self.assertEqual(manual.day_id(T), "manual_" + manual.time.strftime("%Y-%m-%d", manual.time.localtime(T)))
        self.a.eng.write_back()              # never switched on: not seeded – nothing runs
        self.assertEqual(self.a.files(), before)
        self.assertEqual(synclogs.SUFFIX[0], "")
        self.assertEqual(self.a.docs.backups, [])

    def test_on_new_ids_carry_the_device_and_off_again_not(self):
        self.a.eng.switch_on()
        dev = self.a.eng.meta["dev"]
        self.assertTrue(manual.day_id(T).endswith("_" + dev))
        self.assertEqual(synclogs.new_id("import_x"), "import_x_" + dev)
        self.a.eng.switch_off()
        self.assertEqual(synclogs.new_id("import_x"), "import_x")


class Transition(Base):
    def old_data(self, dev):
        log = self.scan(dev, "2026-11-07_10-00-00", ["A", "B"])
        f = dict(card("F"), uid="uf", lang="en", foil=False, count=3, added=T + 5, src=None, cond="near_mint")
        lines = [dict(card("F"), uid="uf", delta=1, lang="en", foil=False, cond="near_mint", price=1.0,
                      added=T + 5 + i * 2e-7) for i in range(3)]          # three lines in one µs (an old log)
        dev.save_log({"id": "manual_2026-11-07", "started": T, "ended": T + 6, "collection": False,
                      "info": {"kind": "manual", "title": ""},
                      "packs": [{"opened": T, "type": "manual", "cards": lines}]})
        items = dev.data()["items"] + [f]
        dev.save_coll(items)
        return log

    def test_first_sync_moves_doubles_renames_and_backs_up_once(self):
        a = self.a
        self.old_data(a)
        lib_before = a.coll()
        a.eng.switch_on()
        a.sync()
        dev = a.eng.meta["dev"]
        names = sorted(p.name for p in a.mine("sessions").glob("*.json"))
        self.assertEqual(names, sorted(["2026-11-07_10-00-00.json", f"manual_2026-11-07_{dev}.json"]))
        man = json.loads(a.mine("sessions", f"manual_2026-11-07_{dev}.json").read_text("utf-8"))
        self.assertEqual(len({synclogs.us(c["added"]) for c in man["packs"][0]["cards"]}), 3)
        self.assertEqual(a.docs.backups, ["before-sync-logs"])
        self.assertEqual(a.coll(), lib_before)
        self.assertEqual(a.library(), a.coll())
        self.assertFalse(list(a.mine().rglob("*.sync-new")))
        files = a.files()
        self.tick()
        a.sync()                                                    # once is enough
        self.assertEqual(a.files(), files)
        self.assertEqual(a.docs.backups, ["before-sync-logs"])

    def test_abort_before_the_mark_leaves_the_old_files(self):
        a = self.a
        self.old_data(a)
        before = a.files()
        a.eng.switch_on()
        real = syncrun._write

        def crash(p, obj):
            if pathlib.Path(p).name == "commit":
                raise OSError("power gone")
            return real(p, obj)
        with mock.patch.object(syncrun, "_write", crash):
            with self.assertRaises(OSError):
                a.sync()
        self.assertEqual({k: v for k, v in a.files().items() if not k.endswith(".sync-new")}, before)
        syncrun.Engine(a.home, a.settings, a.docs, a.vault, now=a.clock)     # the next start throws the rest away
        self.assertEqual(a.files(), before)

    def test_abort_after_the_mark_is_finished_at_the_next_start(self):
        a = self.a
        self.old_data(a)
        a.eng.switch_on()
        real = os.replace
        calls = []

        def crash(src, dst):
            if str(src).endswith(".sync-new"):   # moving the new contents in, after the mark
                calls.append(dst)
                if len(calls) == 2:
                    raise OSError("power gone")
            return real(src, dst)
        with mock.patch.object(syncrun.os, "replace", crash):
            with self.assertRaises(OSError):
                a.sync()
        self.assertEqual(len(calls), 2)
        syncrun.Engine(a.home, a.settings, a.docs, a.vault, now=a.clock)
        dev = a.eng.meta["dev"]
        self.assertTrue(a.mine("sessions", f"manual_2026-11-07_{dev}.json").exists())
        self.assertFalse(a.mine("sessions", "manual_2026-11-07.json").exists())
        self.assertFalse(list(a.mine().rglob("*.sync-new")))
        self.assertEqual(a.library(), a.coll())

    def test_no_backup_no_change(self):
        a = self.a
        self.old_data(a)
        before = a.files()
        a.eng.switch_on()
        with mock.patch.object(a.docs, "backup", lambda reason: None):
            with self.assertRaises(OSError):
                a.sync()
        self.assertEqual(a.files(), before)


class TwoDevices(Base):
    def test_a_scan_and_a_hand_add_reach_b(self):
        a, b = self.a, self.b
        self.scan(a, "2026-11-07_10-00-00", ["A", "B"])
        a.eng.switch_on()
        a.sync()
        self.tick()
        b.eng.switch_on()
        b.sync()
        self.assertEqual(b.coll(), a.coll())
        self.assertEqual(b.library(), b.coll())
        self.assertEqual({it["img"] for it in b.data()["items"]}, {"A-id_0.jpg", "B-id_0.jpg"})
        for d in b.data()["logs"]:   # the log list reads the figures and every card's price (07.11. find)
            self.assertIn("stats", d)
            self.assertTrue(all("price" in e for p in d["packs"] for e in p["cards"]))

    def test_language_changed_on_b_arrives_on_a(self):
        a, b = self.a, self.b
        log = self.scan(a, "2026-11-07_10-00-00", ["A"])
        a.eng.switch_on()
        a.sync()
        self.tick()
        b.eng.switch_on()
        b.sync()
        self.tick()
        bl = json.loads(b.mine("sessions", f"{log['id']}.json").read_text("utf-8"))
        bl["packs"][0]["cards"][0]["lang"] = "de"
        b.save_log(bl)
        items = b.data()["items"]
        items[0]["lang"] = "de"
        b.save_coll(items)
        b.sync()
        self.tick()
        a.sync()
        self.assertEqual([it["lang"] for it in a.data()["items"]], ["de"])
        self.assertEqual(a.library(), a.coll())

    def test_the_same_second_on_both_devices(self):
        a, b = self.a, self.b
        self.scan(a, "2026-11-07_10-00-00", ["A"])
        self.scan(b, "2026-11-07_10-00-00", ["B"], when=T + 0.5)    # an old log of B, same id, other cards
        a.eng.switch_on()
        a.sync()
        self.tick()
        b.eng.switch_on()
        b.sync()
        self.tick()
        a.sync()
        names = lambda d: sorted(it["name"] for it in d.data()["items"])   # noqa: E731
        self.assertEqual(names(a), ["A", "B"])
        self.assertEqual(names(b), ["A", "B"])
        self.assertEqual(a.coll(), b.coll())



class TakeOver(Base):
    """SYNC-LOGS §4 / legal 06.11.: a device that takes another state sets its own aside first – never lost."""

    def setUp(self):
        super().setUp()
        from collection import syncaside
        p = mock.patch.object(syncaside, "root", lambda: pathlib.Path(self.tmp.name) / "beiseite")
        p.start()
        self.addCleanup(p.stop)
        self.aside = syncaside

    def both(self):
        a, b = self.a, self.b
        self.scan(a, "2026-11-07_10-00-00", ["A"])
        self.scan(b, "2026-11-07_11-00-00", ["B"], when=T + 3600)
        a.eng.switch_on()
        a.sync()
        self.tick()
        b.eng.switch_on()
        b.sync()
        self.tick()
        a.sync()
        names = lambda d: sorted(it["name"] for it in d.data()["items"])   # noqa: E731
        self.assertEqual(names(a), ["A", "B"])
        return names

    def test_keep_mine_elsewhere_sets_this_device_aside(self):
        a, b = self.a, self.b
        names = self.both()
        self.scan(a, "2026-11-07_12-00-00", ["C"], when=T + 7200)   # A's change, not sent yet
        b.mine("sessions", "2026-11-07_10-00-00.json").unlink()      # B keeps a state without A's log
        items = [it for it in b.data()["items"] if it["name"] != "A"]
        b.save_coll(items)
        b.eng.keep_mine("pc")
        b.sync()
        self.tick()
        a.sync()
        self.assertEqual(names(a), ["B"], "A took B's state 1:1")
        got = self.aside.list_all()
        self.assertEqual([(e["why"], e["other"]) for e in got], [("takeover", "pc")])
        kept = self.aside.folder(got[0]["id"]) / "games" / "mtg" / "sessions"
        self.assertEqual(sorted(p.name for p in kept.iterdir()),
                         ["2026-11-07_10-00-00.json", "2026-11-07_11-00-00.json", "2026-11-07_12-00-00.json"])
        self.assertEqual(a.eng.pending, [])
        self.tick()
        a.sync()
        self.assertEqual(len(self.aside.list_all()), 1, "the same takeover only once")
        self.assertEqual(names(a), ["B"])

    def test_more_than_90_days_away_takes_the_vault(self):
        a, b = self.a, self.b
        names = self.both()
        a.eng.meta["fetched_at"] -= 91 * syncrun.DAY_MS   # A was away for 91 days, B wasn't
        self.scan(b, "2026-11-07_13-00-00", ["D"], when=T + 9000)
        b.sync()
        self.scan(a, "2026-11-07_14-00-00", ["E"], when=T + 9500)   # A's own, never sent
        a.sync()
        self.assertEqual(names(a), ["A", "B", "D"])
        got = self.aside.list_all()
        self.assertEqual([e["why"] for e in got], ["offline"])
        kept = self.aside.folder(got[0]["id"]) / "games" / "mtg" / "sessions"
        self.assertIn("2026-11-07_14-00-00.json", {p.name for p in kept.iterdir()})

    def test_two_keep_mine_at_once_ask_again(self):
        a, b = self.a, self.b
        self.both()
        a.eng.keep_mine("pc")
        b.eng.keep_mine("phone")
        b.sync()                                  # B first
        self.tick()
        a.eng.push()
        self.assertTrue(a.eng.meta.get("join_again"))
        self.assertNotIn("takeover_out", a.eng.meta)


class Join(TakeOver):
    """Oliver 06.11.: joining with data on BOTH sides asks (three equal buttons); one side empty never asks."""

    def setup_two(self):
        a, b = self.a, self.b
        self.scan(a, "2026-11-07_10-00-00", ["A"])
        self.scan(b, "2026-11-07_11-00-00", ["B"], when=T + 3600)
        a.eng.switch_on()
        a.sync()
        self.tick()
        b.eng.switch_on()
        b.eng.meta["join_other"] = "phone"
        here = b.eng._counts_here   # U6 (11.11.): equal numbers merge without asking – one deck more here, so it asks
        b.eng._counts_here = lambda: dict(here(), decks=here()["decks"] + 1)
        b.eng.fetch()
        hold = b.eng.meta.get("join_hold")
        self.assertEqual((hold["other"], hold["here"]["cards"], hold["there"]["cards"]), ("phone", 1, 1))
        self.assertEqual(b.eng.write_back(), [])
        self.assertEqual(b.eng.push(), 0)
        self.assertEqual(self.vault.version, 1, "nothing sent before the choice")
        return a, b

    def names(self, d):
        return sorted(it["name"] for it in d.data()["items"])

    def test_merge(self):
        a, b = self.setup_two()
        b.eng.join_answer("merge")
        b.sync(answer=None)
        self.tick()
        a.sync()
        self.assertEqual((self.names(a), self.names(b)), (["A", "B"], ["A", "B"]))

    def test_theirs(self):
        a, b = self.setup_two()
        b.eng.join_answer("theirs")
        b.sync(answer=None)
        self.assertEqual(self.names(b), ["A"])
        got = self.aside.list_all()
        self.assertEqual([(e["why"], e["other"]) for e in got], [("theirs", "phone")])
        self.tick()
        a.sync()
        self.assertEqual(self.names(a), ["A"], "B sent nothing of its own")

    def test_mine(self):
        a, b = self.setup_two()
        b.eng.join_answer("mine")
        b.sync(answer=None)
        self.tick()
        a.sync()
        self.assertEqual((self.names(a), self.names(b)), (["B"], ["B"]))
        self.assertEqual([e["why"] for e in self.aside.list_all()], ["takeover"])

    def test_cancel(self):
        a, b = self.setup_two()
        b.eng.join_answer("")
        self.assertFalse(b.eng.on())
        self.assertEqual(self.vault.version, 1)

    def test_one_side_empty_never_asks(self):
        a, b = self.a, self.b
        self.scan(a, "2026-11-07_10-00-00", ["A"])
        a.eng.switch_on()
        a.sync()
        self.tick()
        b.eng.switch_on()
        b.eng.fetch()
        self.assertIsNone(b.eng.meta.get("join_hold"))


class FreshDevice(Base):
    def test_a_device_without_a_folder_for_the_game_gets_its_collection(self):
        """ports 07.11.: a freshly paired device without its own files for a game only the vault has."""
        a, b = self.a, self.b
        b.docs.games = lambda: [g for g in ["mtg"] if b.mine().is_dir()]   # like games.mine(k).is_dir()
        self.scan(a, "2026-11-07_10-00-00", ["A", "B"])
        a.eng.switch_on()
        a.sync()
        self.tick()
        self.assertFalse(b.mine().exists())
        b.eng.switch_on()
        b.sync()
        self.assertEqual(sorted(it["name"] for it in b.data()["items"]), ["A", "B"])
        self.assertEqual(b.library(), b.coll())

if __name__ == "__main__":
    unittest.main()
