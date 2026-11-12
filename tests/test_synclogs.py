"""The collection in the sync (collection/synclogs.py, docs/web/SYNC-LOGS.md): the synced form of the logs gives the
same library as today's rules (logsum + shadow) and as collection.json – every way a copy comes, goes or changes.

    python -m unittest discover -t . -s tests -p test_synclogs.py
"""
import json
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from collection import collection, manual, sessions, shadow, synclogs
from tests.test_logsum import card, scan_log


class Rules(unittest.TestCase):
    def test_times_are_whole_and_half_goes_up(self):
        self.assertEqual(synclogs.us(1793600000.25), 1793600000250000)
        self.assertEqual(synclogs.us(0.0000005), 1)       # .5 µs: up (Python's round() would give 0)
        self.assertEqual(synclogs.us(0.0000025), 3)       # and not to even
        self.assertEqual(synclogs.ms(1.0005), 1001)
        self.assertEqual(synclogs.cents(0.125), 13)
        self.assertIsNone(synclogs.ms(None))

    def test_src_and_key(self):
        self.assertEqual(synclogs.key_of_src("2026-11-06_22-41-07/1793600000.123456"),
                         "2026-11-06_22-41-07|1793600000123456")
        self.assertEqual(synclogs.key_of_src("import_x/1793600000.0"), "import_x|1793600000000000")
        self.assertEqual(synclogs.lib_key({"uid": "u1", "src": None}), "uid:u1")

    def test_no_floats_travel(self):
        log = scan_log("s1", ["A"], 1793600000.123)
        view = synclogs.explode([log], [], [])
        for kind in synclogs.KINDS:
            json.loads(json.dumps(view[kind]))
            for e in view[kind].values():
                self.assertNotIn("float", repr({k: type(v).__name__ for k, v in e.items()}))


class SameAsToday(unittest.TestCase):
    """explode -> library == collection.json == shadow.rebuild (keys in the synced form)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.patches = [mock.patch.object(sessions, "SESSIONS", self.root / "sessions"),
                        mock.patch.object(collection, "FILE", self.root / "collection.json")]
        for p in self.patches:
            p.start()
        self.coll = collection.Collection()
        self.t = time.mktime((2026, 10, 27, 12, 0, 0, 0, 0, -1))
        self.bookings = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def check(self):
        self.coll.save()
        items, logs, _b = shadow.read(self.root)
        view = synclogs.explode(logs, self.bookings, items)
        lib = synclogs.library(view)
        self.assertEqual(lib, synclogs.items_now(items))
        old = {(synclogs.key_of_src(k) if not k.startswith("uid:") else k): v
               for k, v in shadow.rebuild(items, logs, self.bookings).items()}
        self.assertEqual({k: {f: x for f, x in v.items() if f != "trade"} for k, v in lib.items()}, old)
        return view, lib

    def scan(self, sid, names, when, **kw):
        log = scan_log(sid, names, when)
        log.update(kw)
        sessions.save(log)
        self.coll.sync_session(log)
        return log

    def test_scans_hand_edits_removals_bookings_marks(self):
        self.scan("2026-10-27_12-00-00", ["A", "B", "C"], self.t)
        imp = scan_log("import_1", ["D", "E"], self.t + 50)
        for i, e in enumerate(imp["packs"][0]["cards"]):
            e["added"] = self.t + 50 + i * 0.001        # the import's 1-ms steps
        imp["info"]["import"] = True
        sessions.save(imp)
        self.coll.sync_session(imp)
        hand = self.coll.add(card("F"), lang="de", finish="etched", edition="1st")
        manual.record(hand, 1, when=self.t + 200)
        manual.record(hand, 1, when=self.t + 200)          # same instant: +1 µs
        self.coll.set_count(hand["uid"], 2)
        self.coll.update(hand["uid"], lang="fr")
        manual.record_edit(dict(hand, lang="fr"), {"lang": ["de", "fr"]}, when=self.t + 210)
        b = next(it for it in self.coll.items if it["name"] == "B")   # a scanned copy taken out by hand
        manual.record(b, -1, when=self.t + 220)
        self.coll.set_count(b["uid"], 0)
        self.coll.hidden.add(b["src"])
        c = next(it for it in self.coll.items if it["name"] == "C")   # traded away
        self.bookings.append({"id": "bk1", "t": self.t + 230, "taken": [{"uid": c["uid"], "n": 1, "item": dict(c)}]})
        self.coll.set_count(c["uid"], 0)
        self.coll.hidden.add(c["src"])
        a = next(it for it in self.coll.items if it["name"] == "A")
        self.coll.update(a["uid"], trade=1)
        view, lib = self.check()
        self.assertEqual(lib[synclogs.lib_key(a)]["trade"], 1)
        self.assertEqual(lib["uid:" + hand["uid"]]["lang"], "fr")
        self.assertEqual(lib["uid:" + hand["uid"]]["count"], 2)
        self.assertEqual(len([k for k in view["logrows"] if k.startswith("import_1|")]), 2)

    def test_running_log_out_cards_and_a_log_out_of_the_library(self):
        self.scan("s1", ["A"], self.t)
        run = scan_log("s2", ["B"], self.t + 10)
        run["ended"] = None
        sessions.save(run)
        trade = scan_log("s3", ["C", "D"], self.t + 20)
        trade["packs"][0]["cards"][1]["out"] = True
        sessions.save(trade)
        self.coll.sync_session(trade)
        off = scan_log("s4", ["E"], self.t + 30)
        off["collection"] = False
        sessions.save(off)
        _view, lib = self.check()
        self.assertEqual(sorted(v["count"] for v in lib.values()), [1, 1])

    def test_gone_list(self):
        log = self.scan("s1", ["A", "B"], self.t)
        src = f"s1/{log['packs'][0]['cards'][1]['added']!r}"
        self.coll.items = [it for it in self.coll.items if it["src"] != src]
        self.coll.hidden.add(src)
        day = {"id": "manual_2026-10-27", "started": self.t, "ended": self.t, "collection": False,
               "info": {"kind": "manual", "title": ""}, "packs": [{"opened": self.t, "type": "manual", "cards": []}],
               "gone": [src]}
        sessions.save(day)
        view, _lib = self.check()
        self.assertIn(f"manual_2026-10-27|gone|{synclogs.key_of_src(src)}", view["logrows"])

    def test_lines_in_the_same_instant_get_their_own_us(self):
        it = self.coll.add(card("F"))
        for _ in range(40):   # float steps of 1e-6 alone landed in one µs (the 29.10. migration log)
            manual.record(it, 1, when=self.t + 0.3)
        self.coll.set_count(it["uid"], 40)
        cards = manual.lines(manual.day_id(self.t))
        self.assertEqual(len({synclogs.us(c["added"]) for c in cards}), 40)
        self.check()

    def test_spread_moves_doubles_and_every_reference(self):
        log = self.scan("s1", ["A", "B", "C"], self.t)
        cards = log["packs"][0]["cards"]
        cards[1]["added"] = cards[0]["added"] + 2e-7          # same µs as A (an old log)
        cards[2]["added"] = cards[0]["added"] + 4e-7
        sessions.save(log)
        self.coll.items = []
        self.coll.sync_session(log)
        b = next(it for it in self.coll.items if it["name"] == "B")
        c = next(it for it in self.coll.items if it["name"] == "C")
        manual.record(b, -1, when=self.t + 5)                 # its line + saved entry name B's src
        self.coll.set_count(b["uid"], 0)
        self.coll.hidden.add(b["src"])
        self.bookings.append({"id": "bk", "t": self.t, "taken": [{"uid": c["uid"], "n": 1, "item": dict(c)}]})
        self.coll.set_count(c["uid"], 0)
        self.coll.hidden.add(c["src"])
        self.coll.save()
        items, logs, _b = shadow.read(self.root)
        self.assertEqual(len(synclogs.explode(logs, [], items)["logrows"]), 3)    # two rows lost
        hidden = set(self.coll.hidden)
        changed = synclogs.spread(logs, items, hidden, self.bookings)
        self.assertIn("s1", changed)
        self.assertTrue(any(x.startswith("manual_") for x in changed))
        for d in logs:
            sessions.save(d)
        self.coll.items, self.coll.hidden = items, hidden
        view, lib = self.check()
        self.assertEqual(len([k for k in view["logrows"] if k.startswith("s1|")]), 3)
        self.assertEqual(sum(v["count"] for v in lib.values()), 1)
        self.assertEqual(len({synclogs.us(e["added"]) for e in sessions.load("s1")["packs"][0]["cards"]}), 3)
        self.assertEqual(synclogs.spread(logs, items, hidden, self.bookings), [])   # once is enough

    def test_undo_of_a_field_change_goes_into_the_logs(self):
        """Sync on, after an undo (SYNC-LOGS §5): the collection went back, the logs follow – a hand copy by an edit
        line back, a scanned copy by its log card."""
        import app
        from scanner.core import Session
        log = self.scan("s1", ["A"], self.t)
        hand = self.coll.add(card("F"), lang="de")
        manual.record(hand, 1, when=self.t + 10)
        a = next(it for it in self.coll.items if it["src"])
        # the change (logs + collection) …
        manual.record_edit(dict(hand, lang="fr"), {"lang": ["de", "fr"]}, when=self.t + 20)
        lg = sessions.load("s1")
        lg["packs"][0]["cards"][0]["lang"] = "it"
        sessions.save(lg)
        # … and the undo: only collection.json goes back (system/undo.py)
        self.coll.save()
        items, logs, _b = shadow.read(self.root)
        self.assertEqual(len(shadow.compare(items, logs, [])), 2)
        win = type("W", (), {})()
        win.collection, win.cards = self.coll, []
        win.session = Session([], {"id": "running", "started": self.t, "packs": []})
        with mock.patch.object(app.sessions, "SESSIONS", self.root / "sessions"):
            n = app.MainWindow.logs_fields_check(win)
        self.assertEqual(n, 2)
        items, logs, _b = shadow.read(self.root)
        self.assertEqual(shadow.compare(items, logs, []), [])
        self.assertEqual(manual.lines(manual.day_id())[-1]["why"], app.tr("undone"))   # today's log
        self.assertEqual(sessions.load("s1")["packs"][0]["cards"][0]["lang"], a["lang"])
        self.check()

    def test_old_hand_line_without_src_on_a_scanned_copy(self):
        """Lines from before src was written: the key comes from the collection (items) once, at explode."""
        self.scan("s1", ["A"], self.t)
        a = self.coll.items[0]
        manual.record(dict(a, src=None), 1, when=self.t + 5)   # an old line: no src
        self.coll.set_count(a["uid"], 2)
        view, lib = self.check()
        row = next(r for k, r in view["logrows"].items() if k.startswith("manual_"))
        self.assertEqual(row["key"], synclogs.lib_key(a))
        self.assertEqual(lib[synclogs.lib_key(a)]["count"], 2)


class TwoDevices(unittest.TestCase):
    """What device A does arrives on B as ops; B writes it back (implode) and recomputes its collection (reconcile):
    B's collection is then exactly the library – and the same as A's."""

    def setUp(self):
        from collection import syncops
        self.so = syncops
        self.t = 1793600000.0
        self.now = [int(self.t * 1000)]
        self.A = {"logs": [], "bookings": [], "items": [], "hidden": set(),
                  "clock": syncops.Clock("aaaa", now=lambda: self.now[0])}
        self.B = {"logs": [], "bookings": [], "items": [], "hidden": set(),
                  "clock": syncops.Clock("bbbb", now=lambda: self.now[0])}
        self.state = syncops.State()
        self.db = {card(n)["id"]: dict(card(n), img=f"{n}.jpg") for n in "ABCDEFG"}

    def view(self, dev):
        return synclogs.explode(dev["logs"], dev["bookings"], dev["items"])

    def change(self, dev, fn):
        old = self.view(dev)
        fn(dev)
        new = self.view(dev)
        self.now[0] += 1000
        for kind in synclogs.KINDS:
            for o in self.so.diff_ops(dev["clock"], f"mtg/{kind}", old[kind], new[kind]):
                self.state.apply(o)

    def take(self, dev):
        """dev fetches: write back + recompute, then it must be exactly the library."""
        view = {k: self.state.view(f"mtg/{k}") for k in synclogs.KINDS}
        changed, deleted, book = synclogs.implode(dev["logs"], dev["bookings"], dev["items"], view,
                                                  card_of=self.db.get)
        logs = {d["id"]: d for d in dev["logs"]}
        logs.update(changed)
        for sid in deleted:
            logs.pop(sid, None)
        dev["logs"] = list(logs.values())
        if book is not None:
            dev["bookings"] = book
        lib = synclogs.library(view)
        synclogs.reconcile(dev["items"], dev["hidden"], lib, view, dev["logs"], card_of=self.db.get)
        self.assertEqual(synclogs.items_now(dev["items"]), lib)
        again = synclogs.implode(dev["logs"], dev["bookings"], dev["items"], view)
        self.assertEqual(again, ({}, [], None), "written back once: nothing differs any more")
        return lib

    def scan_on_a(self, sid, names):
        log = scan_log(sid, names, self.t)

        def do(dev):
            dev["logs"].append(log)
            for i, e in enumerate(log["packs"][0]["cards"]):
                dev["items"].append(dict(card(e["name"]), uid=f"{sid[-4:]}{i}", lang="en", foil=False, count=1,
                                         added=e["added"], src=f"{sid}/{e['added']!r}", cond="near_mint"))
        self.change(self.A, do)
        return log

    def test_a_scan_log_arrives_with_its_cards(self):
        self.scan_on_a("2026-11-07_10-00-00_aaaa", ["A", "B"])
        lib = self.take(self.B)
        self.assertEqual(len(self.B["logs"]), 1)
        self.assertEqual(sorted(it["name"] for it in self.B["items"]), ["A", "B"])
        self.assertEqual(self.B["items"][0]["img"], "A.jpg")      # derived from B's own card data
        self.assertEqual(lib, synclogs.items_now(self.A["items"]))

    def test_hand_add_edit_trade_mark_and_booking(self):
        self.scan_on_a("2026-11-07_10-00-00_aaaa", ["A", "B"])
        self.take(self.B)
        f = dict(card("F"), uid="uf", lang="de", foil=False, count=1, added=self.t + 5, src=None, cond="near_mint")
        day = {"id": "manual_2026-11-07_aaaa", "started": self.t, "ended": self.t + 6, "collection": False,
               "info": {"kind": "manual", "title": ""}, "packs": [{"opened": self.t, "type": "manual", "cards": [
                   dict(card("F"), uid="uf", delta=1, lang="de", foil=False, cond="near_mint", added=self.t + 5,
                        price=1.0),
                   dict(card("F"), uid="uf", delta=0, lang="fr", foil=False, cond="near_mint", added=self.t + 6,
                        price=1.0, edit={"lang": ["de", "fr"]})]}]}
        self.change(self.A, lambda d: (d["logs"].append(day), d["items"].append(dict(f, lang="fr")),
                                       d["items"][0].update(trade=1)))
        b_item = dict(self.A["items"][1])
        self.change(self.A, lambda d: (d["bookings"].append({"id": "bk", "t": self.t + 9, "taken": [
            {"uid": b_item["uid"], "n": 1, "item": b_item}]}), d["items"].pop(1), d["hidden"].add(b_item["src"])))
        lib = self.take(self.B)
        names = {it["name"]: it for it in self.B["items"]}
        self.assertEqual(sorted(names), ["A", "F"])
        self.assertEqual((names["F"]["lang"], names["F"]["uid"], names["A"]["trade"]), ("fr", "uf", 1))
        self.assertIn(synclogs.src_of(synclogs.lib_key(b_item), {}) or "", self.B["hidden"] | {""})
        self.assertEqual(lib, synclogs.items_now(self.A["items"]))

    def test_a_log_deleted_for_good_keeps_its_cards_on_b(self):
        log = self.scan_on_a("2026-11-07_10-00-00_aaaa", ["A", "B"])
        self.take(self.B)

        def forget(d):
            d["logs"].remove(log)
            for it in d["items"]:
                it["src"] = None
            d["logs"].append({"id": "manual_2026-11-07_aaaa", "started": self.t, "ended": self.t + 50,
                              "collection": False, "info": {"kind": "manual", "title": ""},
                              "packs": [{"opened": self.t, "type": "manual", "cards": [
                                  dict(card(it["name"]), uid=it["uid"], delta=1, lang="en", foil=False,
                                       cond="near_mint", added=self.t + 50 + i * 1e-6, price=1.0)
                                  for i, it in enumerate(d["items"])]}]})
        self.change(self.A, forget)
        lib = self.take(self.B)
        self.assertEqual([d["id"] for d in self.B["logs"]], ["manual_2026-11-07_aaaa"])
        self.assertEqual(sorted(k for k in lib), sorted("uid:" + it["uid"] for it in self.A["items"]))
        self.assertTrue(all(it["src"] is None for it in self.B["items"]))

    def test_unchanged_documents_stay_untouched(self):
        log = scan_log("s1", ["A"], self.t)
        log["info"]["active"] = True
        items = [dict(card("A"), uid="u", lang="en", foil=False, count=1, added=self.t, src=f"s1/{self.t!r}")]
        view = synclogs.explode([log], [], items)
        self.assertEqual(synclogs.implode([log], [], items, view), ({}, [], None))
        view["logrows"][synclogs.row_key("s1", self.t)]["lang"] = "de"
        changed, _d, _b = synclogs.implode([log], [], items, view, skip=("s1",))
        self.assertEqual(changed, {}, "the running log is never written back")
        changed, _d, _b = synclogs.implode([log], [], items, view)
        self.assertEqual(changed["s1"]["packs"][0]["cards"][0]["lang"], "de")
        self.assertTrue(changed["s1"]["info"]["active"], "local info stays")
        self.assertEqual(changed["s1"]["packs"][0]["cards"][0]["img"], "x.jpg", "what isn't synced stays")


class Echo(unittest.TestCase):
    def test_the_same_content_written_by_js_is_not_written_back(self):
        """ports 07.11.: JS writes 1793600000 where Python writes 1793600000.0 – the same content, no rewrite."""
        log = scan_log("s1", ["A"], 1793600000.0)
        log["info"]["paid"] = 5.0
        items = [dict(card("A"), uid="u", lang="en", foil=False, count=1, added=1793600000.0,
                      src="s1/1793600000.0")]
        view = synclogs.explode([log], [], items)
        view["logs"]["s1"]["info"] = view["logs"]["s1"]["info"].replace("5.0", "5")
        self.assertNotEqual(view["logs"]["s1"]["info"], synclogs.explode([log], [], items)["logs"]["s1"]["info"])
        self.assertEqual(synclogs.implode([log], [], items, view), ({}, [], None))


class Arrived(unittest.TestCase):
    def test_a_card_without_price_arrives_with_price_none_and_figures(self):
        """07.11. find: the log list reads every card's "price" (None allowed) – a missing one broke it."""
        from scanner import core
        log = scan_log("s1", ["A", "B"], 1793600000.0)
        log["packs"][0]["cards"][0]["price"] = None
        view = synclogs.explode([log], [], [])
        changed, _d, _b = synclogs.implode([], [], [], view)
        cards = changed["s1"]["packs"][0]["cards"]
        self.assertEqual([c.get("price", "missing") for c in cards], [None, 1.0])
        core.session_stats(changed["s1"]["packs"], changed["s1"]["info"])


class Rename(unittest.TestCase):
    def test_rename_moves_every_reference(self):
        log = scan_log("2026-11-07_10-00-00", ["A", "B"], 1793600000.0)
        src = f"2026-11-07_10-00-00/{log['packs'][0]['cards'][0]['added']!r}"
        day = {"id": "manual_x", "info": {"kind": "manual"}, "gone": [src],
               "packs": [{"cards": [{"uid": "u", "delta": -1, "src": src, "item": {"src": src}}]}]}
        items = [{"uid": "u1", "src": src}, {"uid": "u2", "src": None, "from_session": "2026-11-07_10-00-00"}]
        hidden = {src}
        book = [{"session": "2026-11-07_10-00-00", "taken": [{"item": {"src": src}}]}]
        synclogs.rename_log([log, day], items, hidden, book, "2026-11-07_10-00-00", "2026-11-07_10-00-00_aaaa")
        new = "2026-11-07_10-00-00_aaaa/" + src.partition("/")[2]
        self.assertEqual((log["id"], day["gone"], day["packs"][0]["cards"][0]["src"],
                          day["packs"][0]["cards"][0]["item"]["src"], items[0]["src"], items[1]["from_session"],
                          hidden, book[0]["session"], book[0]["taken"][0]["item"]["src"]),
                         ("2026-11-07_10-00-00_aaaa", [new], new, new, new, "2026-11-07_10-00-00_aaaa", {new},
                          "2026-11-07_10-00-00_aaaa", new))


class Vectors(unittest.TestCase):
    """docs/web/synclog-vectors.json is what the code computes now (the web checks the same file)."""

    def test_vectors_are_current(self):
        from tools import make_synclog_vectors
        root = pathlib.Path(__file__).resolve().parents[1]
        have = json.loads((root / "docs" / "web" / "synclog-vectors.json").read_text("utf-8"))
        self.assertEqual(json.loads(json.dumps(make_synclog_vectors.build(), sort_keys=True)), have)

    def test_every_case_from_its_data(self):
        from collection import syncops
        root = pathlib.Path(__file__).resolve().parents[1]
        vec = json.loads((root / "docs" / "web" / "synclog-vectors.json").read_text("utf-8"))
        for c in vec["explode"]:
            view = synclogs.explode(c["logs"], c["bookings"], c["items"])
            self.assertEqual(json.loads(json.dumps(view)), c["view"], c["name"])
            self.assertEqual(synclogs.checksum(synclogs.library(view)), c["sum"], c["name"])
        for c in vec["ops"]:
            st = syncops.State()
            for o in reversed(c["ops"]):
                st.apply(o)
            view = {k: st.view(f"{vec['game']}/{k}") for k in vec["kinds"]}
            self.assertEqual(synclogs.checksum(synclogs.library(view)), c["sum"], c["name"])


if __name__ == "__main__":
    unittest.main()
