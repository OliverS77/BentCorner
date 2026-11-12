"""The sync change protocol (collection/syncops.py, docs/SYNC-PLAN.md §3): the fixed vectors (the web app checks the
same file), any order of arrival and doubled ops give the same state, the HLC never goes backwards and keeps a wrong
PC clock within 5 minutes, the save() diff turns two document states into ops, snapshots + later ops = all ops.

    python -m unittest discover -t . -s tests -p test_syncops.py
"""
import json
import pathlib
import random
import unittest

from collection import syncops

ROOT = pathlib.Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "docs" / "web" / "sync-vectors.json").read_text("utf-8"))


def run(ops, order=None, twice=False):
    st = syncops.State()
    seq = [ops[i] for i in order] if order else list(ops)
    for o in seq + (seq if twice else []):
        st.apply(json.loads(json.dumps(o)))
    return st


class Vectors(unittest.TestCase):
    def test_file_is_current(self):
        from tools import make_sync_vectors
        self.assertEqual(make_sync_vectors.build(), VECTORS)

    def test_every_order(self):
        rng = random.Random(5)
        for case in VECTORS["cases"]:
            for i in range(30):
                order = list(range(len(case["ops"])))
                rng.shuffle(order)
                st = run(case["ops"], order, twice=i % 2 == 1)
                for kind in case["view"]:
                    self.assertEqual(st.view(kind), case["view"][kind], (case["name"], order))
                    self.assertEqual(st.sum(kind), case["sum"][kind], case["name"])


class Random(unittest.TestCase):
    """Three devices edit decks, deck cards and binders at random; every order gives the same result."""

    def test_commutative(self):
        rng = random.Random(11)
        now = [1793600000000]
        clocks = {d: syncops.Clock(d, now=lambda: now[0]) for d in ("aaaa", "bbbb", "cccc")}
        kinds = ("mtg/decks", "mtg/deckcards", "mtg/binders")
        ops = []
        for _ in range(400):
            now[0] += rng.choice((0, 0, 1, 50, 1000))
            c = clocks[rng.choice(list(clocks))]
            kind, key = rng.choice(kinds), f"k{rng.randrange(6)}"
            r = rng.random()
            if kind.endswith("deckcards"):
                if r < 0.3:
                    o = syncops.op(c, kind, key, s={"id": f"c{rng.randrange(3)}_0", "foil": rng.random() < .5,
                                                     "lang": "en", "finish": None}, d={"n": 1}, create=True)
                elif r < 0.5:
                    o = syncops.op(c, kind, key, delete=rng.randrange(3))
                elif r < 0.8:
                    o = syncops.op(c, kind, key, d={"n": rng.choice((1, -1, 2))})
                else:
                    o = syncops.op(c, kind, key, s={"id": "z_0", "foil": True, "lang": "de", "finish": "foil"})
            else:
                if r < 0.3:
                    o = syncops.op(c, kind, key, s={"name": f"n{rng.randrange(9)}", "t": rng.randrange(3)}, create=True)
                elif r < 0.5:
                    o = syncops.op(c, kind, key, delete=True)
                else:
                    o = syncops.op(c, kind, key, s={rng.choice(("name", "t", "note")): rng.randrange(9)})
            ops.append(o)
        ref = run(ops)
        want = {k: ref.view(k) for k in kinds}
        self.assertTrue(any(want.values()))
        for _ in range(10):
            order = list(range(len(ops)))
            rng.shuffle(order)
            st = run(ops, order, twice=True)
            self.assertEqual({k: st.view(k) for k in kinds}, want)

    def test_snapshot_plus_later_ops(self):
        now = [1793600000000]
        a, b = syncops.Clock("aaaa", now=lambda: now[0]), syncops.Clock("bbbb", now=lambda: now[0])
        early = [syncops.op(a, "mtg/decks", "d1", s={"name": "x"}, create=True),
                 syncops.op(b, "mtg/decks", "d2", s={"name": "y"}, create=True)]
        now[0] += 10
        late = [syncops.op(a, "mtg/decks", "d1", s={"name": "x2"}), syncops.op(b, "mtg/decks", "d2", delete=True)]
        full = run(early + late)
        snap = json.loads(json.dumps(run(early).to_snap()))
        st = syncops.State.from_snap(snap)
        for o in early + late:   # replaying old ops again is harmless (covered by the snapshot)
            st.apply(o)
        self.assertEqual(st.view("mtg/decks"), full.view("mtg/decks"))
        self.assertEqual(st.view("mtg/decks"), {"d1": {"name": "x2"}})


class Clock(unittest.TestCase):
    def test_never_backwards(self):
        now = [1000]
        c = syncops.Clock("aaaa", now=lambda: now[0])
        h1 = c.tick()
        now[0] = 500                      # the PC clock jumped back
        h2 = c.tick()
        self.assertGreater((h2[0], h2[1]), (h1[0], h1[1]))
        c.seen([9000, 3, "bbbb"])         # a newer op of another device
        self.assertGreater(tuple(c.tick()[:2]), (9000, 3))

    def test_server_offset_capped(self):
        c = syncops.Clock("aaaa", now=lambda: 1_000_000_000)
        c.set_server_time(1_000_000_000 + 3600_000)   # PC an hour behind
        self.assertEqual(c.offset, syncops.SKEW_MS)
        c.set_server_time(1_000_000_000 - 1000)
        self.assertEqual(c.offset, -1000)


class Diff(unittest.TestCase):
    def setUp(self):
        self.now = [1793600000000]
        self.c = syncops.Clock("aaaa", now=lambda: self.now[0])

    def test_diff_reaches_the_new_state(self):
        old = {"k1": {"n": 2}, "k2": {"n": 1}}
        new = {"k1": {"n": 3}, "k3": {"n": 4}}
        st = syncops.State()
        for o in syncops.diff_ops(self.c, "mtg/deckcards", {}, old):
            st.apply(o)
        self.now[0] += 1
        ops = syncops.diff_ops(self.c, "mtg/deckcards", old, new)
        k1 = next(o for o in ops if o["k"] == "k1")
        self.assertEqual(k1["d"], {"n": 1})                                  # a delta, not an overwrite
        for o in ops:
            st.apply(o)
        self.assertEqual(st.view("mtg/deckcards"), new)

    def test_group_goes_whole(self):
        old = {"b|0": {"sid": "a_0", "lang": "en", "foil": False, "name": "A"}}
        new = {"b|0": {"sid": "a_0", "lang": "en", "foil": True, "name": "A"}}
        ops = syncops.diff_ops(self.c, "mtg/binderslots", old, new, ("sid", "lang", "foil"))   # name: derived
        self.assertEqual(ops[0]["s"], {"sid": "a_0", "lang": "en", "foil": True})

    def test_no_change_no_op(self):
        doc = {"d1": {"name": "x"}}
        self.assertEqual(syncops.diff_ops(self.c, "mtg/decks", doc, json.loads(json.dumps(doc))), [])

    def test_floats_refused(self):
        with self.assertRaises(ValueError):
            syncops.checksum({"k": {"eur": 1.5}})


class Schema(unittest.TestCase):
    """The schema (labs/sync/SCHEMA-ENTWURF.md): wish keys like the app's, a big import is a snap, never a float."""

    def test_wish_key_like_the_app(self):
        from collection import trade
        for w in ({"name": "Bolt"}, {"name": "Bolt", "set": "M10", "number": "146"},
                  {"name": "Bolt", "set": "m10", "number": "146", "lang": "de", "foil": True},
                  {"name": "Bolt", "set": "m10", "number": "146", "foil": True}):
            self.assertEqual(syncops.wish_key(w), trade.wish_key(w), w)

    def test_big_import_is_a_snap(self):
        c = syncops.Clock("aaaa", now=lambda: 1793600000000)
        old = {"decks": [{"id": "d1", "cards": []}]}
        new = {"decks": [{"id": "d1", "cards": [{"sid": f"s{i}", "count": 1} for i in range(syncops.SNAP_OPS + 1)]}]}
        ops, snap = syncops.diff_doc(c, "mtg", "deckcards", old, new)
        self.assertTrue(snap)
        self.assertFalse(syncops.diff_doc(c, "mtg", "deckcards", old, {"decks": [{"id": "d1", "cards": [
            {"sid": "s1", "count": 1}]}]})[1])

    def test_every_entry_is_checksum_safe(self):
        for e in VECTORS["explode"]:
            syncops.canonical(e["entries"])   # raises on a float (timestamps go as whole ms)


class Implode(unittest.TestCase):
    """implode = the counterpart of explode: back into this device's document, only what differs changes."""

    def docs(self):
        from tools import make_sync_vectors as mv
        return {k: mv.DOCS[mv.DOC_OF.get(k, k)] for k in syncops.SCHEMA}

    def test_vectors(self):
        for c in VECTORS["implode"]:
            with self.subTest(kind=c["kind"]):
                self.assertEqual(syncops.implode(c["kind"], c["doc"], c["view"]), c["out"])

    def test_same_entries_same_document(self):
        for kind, doc in self.docs().items():
            with self.subTest(kind=kind):
                self.assertEqual(syncops.implode(kind, doc, syncops.explode(kind, doc)), doc)

    def test_explode_of_implode_is_the_view(self):
        from tools.make_sync_vectors import mutate
        for kind, doc in self.docs().items():
            with self.subTest(kind=kind):
                want = mutate(kind, syncops.explode(kind, doc))
                got = syncops.explode(kind, syncops.implode(kind, doc, want))
                drop_pos = lambda es: {k: {f: v for f, v in e.items() if f != "pos"}   # noqa: E731
                                       for k, e in syncops._wanted(kind, es).items()}
                self.assertEqual(drop_pos(got), drop_pos(want))
                if any("pos" in e for e in want.values()):   # positions are relative: the order is what counts
                    self.assertEqual(sorted(got, key=lambda k: (got[k]["pos"], k)),
                                     sorted(want, key=lambda k: (want[k]["pos"], k)))

    def test_local_fields_stay(self):
        docs = self.docs()
        decks = docs["decks"]
        want = syncops.explode("decks", decks)
        first = decks["decks"][0]["id"]
        want[first]["name"] = "Neu"
        out = syncops.implode("decks", decks, want)
        self.assertEqual(out["decks"][0]["name"], "Neu")
        self.assertEqual(out["decks"][0]["updated"], decks["decks"][0]["updated"])   # local
        self.assertEqual(out["decks"][0]["cards"], decks["decks"][0]["cards"])       # the other kind
        self.assertNotEqual(decks["decks"][0]["name"], "Neu")                          # input untouched

    def test_cards_of_a_missing_deck_stay_invisible(self):
        decks = self.docs()["decks"]
        want = syncops.explode("deckcards", decks)
        want["nodeck|s1|main"] = {"n": 2}
        self.assertEqual(syncops.implode("deckcards", decks, want), decks)


class Seed(unittest.TestCase):
    """Switching the sync on: the existing documents become creates once – only what the vault does not know yet."""

    @staticmethod
    def deck(did, name, cards):
        return {"id": did, "name": name, "format": "modern", "notes": "", "commanders": [], "pinned": [], "tokens": {},
                "created": 1793500000.0, "updated": 1793500000.0, "local_view": "grid",
                "cards": [{"sid": s, "count": n, "board": "main"} for s, n in cards]}

    def view_doc(self, st, game, doc):
        doc = syncops.implode("decks", doc, st.view(f"{game}/decks"))
        return syncops.implode("deckcards", doc, st.view(f"{game}/deckcards"))

    def test_existing_data_survives_the_first_foreign_package(self):
        now = [1793600000000]
        a = syncops.Clock("aaaa", now=lambda: now[0])
        b = syncops.Clock("bbbb", now=lambda: now[0])
        doc_a = {"decks": [self.deck("d1", "Burn", [("s1", 4)])]}
        # B had the same deck before (a copied file) and one of its own
        doc_b = {"decks": [self.deck("d1", "Burn", [("s1", 4)]), self.deck("d9", "Only B", [("s7", 2)])]}

        # A: the first device – everything is seeded, sent as an add
        sa = syncops.State()
        mine = []
        for kind in ("decks", "deckcards"):
            mine += syncops.seed_ops(a, "mtg", kind, doc_a)[0]
        for o in mine:
            sa.apply(o)
        [pkg] = syncops.add_packages("aaaa", mine, sa)

        # without seeding, B's own deck would be gone after the first foreign package
        st = syncops.State()
        for o in syncops.unpack(pkg)["ops"]:
            st.apply(o)
        self.assertNotIn("d9", [d["id"] for d in self.view_doc(st, "mtg", doc_b)["decks"]])

        # B switches on: fetch the vault first, then seed only what it does not know
        sb = syncops.State()
        for o in syncops.unpack(pkg)["ops"]:
            sb.apply(o)
        now[0] += 1000
        seeded = []
        for kind in ("decks", "deckcards"):
            seeded += syncops.seed_ops(b, "mtg", kind, doc_b, sb)[0]
        self.assertEqual(sorted({o["k"] for o in seeded}), ["d9", "d9|s7|main"])   # d1 is the vault's
        for o in seeded:
            sb.apply(o)
        out = self.view_doc(sb, "mtg", doc_b)
        decks = {d["id"]: d for d in out["decks"]}
        self.assertEqual(sorted(decks), ["d1", "d9"])
        self.assertEqual(decks["d1"]["cards"], [{"sid": "s1", "count": 4, "board": "main"}])   # not 4 + 4
        self.assertEqual(decks["d9"]["cards"], [{"sid": "s7", "count": 2, "board": "main"}])
        self.assertEqual(decks["d9"]["local_view"], "grid")                                     # local field stays
        self.assertEqual(out, doc_b)   # nothing lost, nothing changed

        # and A gets B's deck through B's add
        [pkg_b] = syncops.add_packages("bbbb", seeded, sb)
        for o in syncops.unpack(pkg_b)["ops"]:
            sa.apply(o)
        self.assertIs(syncops.check_add(sa, syncops.unpack(pkg_b)), True)
        self.assertEqual(sorted(d["id"] for d in self.view_doc(sa, "mtg", doc_a)["decks"]), ["d1", "d9"])

    def test_local_differences_are_not_lost(self):
        """lead 03.11.: the same key with other values – the phone has the card 4×, the vault 3×, the deck another
        name; and a deck the vault deleted is still here. Nothing local vanishes unasked."""
        now = [1793600000000]
        a = syncops.Clock("aaaa", now=lambda: now[0])
        b = syncops.Clock("bbbb", now=lambda: now[0])
        doc_a = {"decks": [self.deck("d1", "Burn", [("s1", 3)]), self.deck("d5", "Old", [("s5", 1)])]}
        sa = syncops.State()
        sent = []
        for kind in ("decks", "deckcards"):
            sent += syncops.seed_ops(a, "mtg", kind, doc_a)[0]
        now[0] += 500
        sent.append(syncops.op(a, "mtg/decks", "d5", delete=True))         # A deletes d5 after switching on
        sent.append(syncops.op(a, "mtg/deckcards", "d5|s5|main", delete=1))
        sent.append(syncops.op(a, "mtg/decks", "d1", s={"notes": "from A"}))   # B still has "" here
        for o in sent:
            sa.apply(o)
        [pkg] = syncops.add_packages("aaaa", sent, sa)

        doc_b = {"decks": [self.deck("d1", "Burn (phone)", [("s1", 4)]), self.deck("d5", "Old", [("s5", 1)])]}
        sb = syncops.State()
        for o in syncops.unpack(pkg)["ops"]:
            sb.apply(o)
        now[0] += 1000
        seeded = []
        for kind in ("decks", "deckcards"):
            seeded += syncops.seed_ops(b, "mtg", kind, doc_b, sb)[0]
        by = {o["k"]: o for o in seeded}
        # a change, no create – EVERY differing field, B's value wins: also notes, which A edited in the vault (the
        # price of "nothing local vanishes": switching on never knows which side is newer)
        self.assertEqual(by["d1"]["s"], {"name": "Burn (phone)", "notes": ""})
        self.assertNotIn("a", by["d1"])
        self.assertEqual(by["d1|s1|main"]["d"], {"n": 1})                       # 4 − 3, never 3 + 4
        self.assertEqual(by["d5"].get("a"), 1)                                 # deleted in the vault: here again
        for o in seeded:
            sb.apply(o)
        [pkg_b] = syncops.add_packages("bbbb", seeded, sb)
        for o in syncops.unpack(pkg_b)["ops"]:
            sa.apply(o)
        for st in (sa, sb):   # both devices end the same: the local values, nothing lost
            decks = {d["id"]: d for d in self.view_doc(st, "mtg", doc_b)["decks"]}
            self.assertEqual(sorted(decks), ["d1", "d5"])
            self.assertEqual(decks["d1"]["name"], "Burn (phone)")
            self.assertEqual(decks["d1"]["cards"], [{"sid": "s1", "count": 4, "board": "main"}])
            self.assertEqual(decks["d5"]["cards"], [{"sid": "s5", "count": 1, "board": "main"}])
        self.assertEqual(sa.sum("mtg/decks"), sb.sum("mtg/decks"))
        self.assertEqual(sa.sum("mtg/deckcards"), sb.sum("mtg/deckcards"))

    def test_counters_seed_a_delta(self):
        """Counters (lead/ports 03.11.): the seed is the delta to the vault as fetched – "this device has 4". What
        the other device changes meanwhile refers to the same base and adds up."""
        for name, a_then, expect in (
                ("A adds 2 meanwhile: 3 + 2 (A) + 1 (B)", lambda a: syncops.op(a, "mtg/deckcards", "d1|s1|main",
                                                                                d={"n": 2}), 6),
                ("A deletes meanwhile (saw 3): B's extra one stays", lambda a: syncops.op(a, "mtg/deckcards",
                                                                                      "d1|s1|main", delete=3), 1),
                ("nothing meanwhile", None, 4)):
            with self.subTest(name):
                now = [1793600000000]
                a = syncops.Clock("aaaa", now=lambda: now[0])
                b = syncops.Clock("bbbb", now=lambda: now[0])
                base = []
                for kind in ("decks", "deckcards"):
                    base += syncops.seed_ops(a, "mtg", kind, {"decks": [self.deck("d1", "Burn", [("s1", 3)])]})[0]
                sb = syncops.State()
                for o in base:
                    sb.apply(o)                                    # B fetched: the vault has 3
                now[0] += 1000
                late = [a_then(a)] if a_then else []               # A, before B's seed arrives
                seeded = syncops.seed_ops(b, "mtg", "deckcards", {"decks": [self.deck("d1", "Burn", [("s1", 4)])]},
                                          sb)[0]
                self.assertEqual([o.get("d") for o in seeded], [{"n": 1}])
                for order in (base + late + seeded, seeded + late + base, late + seeded + base):
                    st = syncops.State()
                    for o in order:
                        st.apply(o)
                    self.assertEqual(st.view("mtg/deckcards").get("d1|s1|main", {}).get("n"), expect)

    def test_global_kind_and_big_import(self):
        now = [1793600000000]
        a = syncops.Clock("aaaa", now=lambda: now[0])
        ops, snap = syncops.seed_ops(a, "pokemon", "profile", {"name": "Oli", "id": "p1"})
        self.assertEqual((ops[0]["c"], ops[0]["s"], snap), ("*/profile", {"name": "Oli", "id": "p1"}, False))
        big = {"decks": [self.deck("d1", "Big", [(f"s{i}", 1) for i in range(syncops.SNAP_OPS + 1)])]}
        self.assertTrue(syncops.seed_ops(a, "mtg", "deckcards", big)[1])


class Vault(unittest.TestCase):
    """The vault packages: add (own ops, top + sum in the last part), snap, unpack refuses what it cannot read."""

    def two(self):
        now = [1793600000000]
        a = syncops.Clock("aaaa", now=lambda: now[0])
        b = syncops.Clock("bbbb", now=lambda: now[0])
        return now, a, b

    def test_add_roundtrip_and_check(self):
        now, a, b = self.two()
        sa, sb = syncops.State(), syncops.State()
        mine = [syncops.op(a, "mtg/decks", "d1", s={"name": "Elves"}, create=True),
                syncops.op(a, "mtg/deckcards", "d1|x|main", d={"n": 4}, create=True)]
        for o in mine:
            sa.apply(o)
        [data] = syncops.add_packages("aaaa", mine, sa)
        pkg = syncops.unpack(data)
        self.assertEqual((pkg["t"], pkg["dev"], len(pkg["ops"])), ("add", "aaaa", 2))
        for o in pkg["ops"]:
            sb.apply(o)
        self.assertIs(syncops.check_add(sb, pkg), True)
        # B has an own unsent op: not comparable – never a false alarm
        sb.apply(syncops.op(b, "mtg/decks", "d2", s={"name": "B"}, create=True))
        self.assertIsNone(syncops.check_add(sb, pkg))
        # the same ops but a different result (a broken client): False -> heal
        bad = json.loads(json.dumps(pkg))
        bad["sum"]["mtg/decks"] = "0" * 64
        sc = syncops.State()
        for o in pkg["ops"]:
            sc.apply(o)
        self.assertIs(syncops.check_add(sc, bad), False)

    def test_only_own_applied_ops(self):
        now, a, b = self.two()
        st = syncops.State()
        o = syncops.op(b, "mtg/decks", "d1", s={"name": "x"}, create=True)
        st.apply(o)
        with self.assertRaises(ValueError):
            syncops.add_packages("aaaa", [o], st)
        with self.assertRaises(ValueError):
            syncops.add_packages("aaaa", [syncops.op(a, "mtg/decks", "d2", s={"name": "y"}, create=True)], st)

    def test_split_keeps_order_and_sum_only_last(self):
        now, a, _b = self.two()
        st = syncops.State()
        ops = []
        for i in range(300):
            ops.append(syncops.op(a, "mtg/decks", f"d{i}", s={"name": f"deck {i} " + "x" * 40}, create=True))
            now[0] += 7
        for o in ops:
            st.apply(o)
        parts = [syncops.unpack(p) for p in syncops.add_packages("aaaa", ops, st, limit=2000)]
        self.assertGreater(len(parts), 1)
        self.assertEqual([o["o"] for p in parts for o in p["ops"]], [o["o"] for o in ops])
        self.assertTrue(all("top" not in p and "sum" not in p for p in parts[:-1]))
        recv = syncops.State()
        for p in parts:
            for o in p["ops"]:
                recv.apply(o)
            r = syncops.check_add(recv, p)
        self.assertIs(r, True)

    def test_snap_roundtrip_compacts(self):
        now, a, b = self.two()
        st = syncops.State()
        for o in [syncops.op(a, "mtg/decks", "d1", s={"name": "A"}, create=True),
                  syncops.op(b, "mtg/deckcards", "d1|x|main", d={"n": 2}, create=True),
                  syncops.op(a, "mtg/decks", "gone", s={"name": "G"}, create=True),
                  syncops.op(a, "mtg/decks", "gone", delete=True)]:
            st.apply(o)
        later = 1793600000000 + (syncops.TOMB_DAYS + 1) * 86400 * 1000
        pkg = syncops.unpack(syncops.snap_package("aaaa", st, later))
        self.assertEqual(pkg["t"], "snap")
        self.assertNotIn("gone", pkg["kinds"]["mtg/decks"])
        self.assertIn("gone", st.kinds["mtg/decks"])           # the device's own state is not touched
        got = syncops.load_snap(pkg)
        for k in ("mtg/decks", "mtg/deckcards"):
            self.assertEqual(got.view(k), st.view(k))
        pkg["sum"]["mtg/decks"] = "0" * 64
        with self.assertRaises(syncops.PackError):
            syncops.load_snap(pkg)

    def test_vault_vectors(self):
        import base64
        from net import pairing
        v = VECTORS["vault"]
        seed = json.loads((ROOT / "docs" / "web" / "pairing-vectors.json").read_text("utf-8"))["seed_b64"]
        for name in ("add", "snap"):
            data = base64.b64decode(v[name]["zlib_b64"])
            self.assertEqual(syncops.canonical(syncops.unpack(data)), v[name]["json"])
            self.assertEqual(syncops.unpack(syncops.pack(json.loads(v[name]["json"]))), json.loads(v[name]["json"]))
        opened = pairing.vault_open_bytes(seed, v["add"]["sealed_b64"])
        self.assertEqual(syncops.canonical(syncops.unpack(opened)), v["add"]["json"])

    def test_unpack_refuses(self):
        with self.assertRaises(syncops.PackError) as e:
            syncops.unpack(syncops.pack({"v": 2, "t": "add"}))
        self.assertTrue(e.exception.newer)
        with self.assertRaises(syncops.PackError) as e:
            syncops.unpack(syncops.pack({"v": 1, "t": "other"}))
        self.assertTrue(e.exception.newer)
        for junk in (b"", b"not zlib", syncops.pack({"v": 1, "t": "add"})[:-3]):
            with self.assertRaises(syncops.PackError) as e:
                syncops.unpack(junk)
            self.assertFalse(e.exception.newer)
        bomb = __import__("zlib").compress(b" " * (syncops.UNPACK_MAX + 10))
        with self.assertRaises(syncops.PackError):
            syncops.unpack(bomb)



class WegA(unittest.TestCase):
    """Weg (a): MAX fields and purge kinds (legal/ports 06.11.), from the vectors – in every order."""

    def test_cases(self):
        want = {"max_fetched": ("*/friendboards", "F1|mtg/lists", {"fetched": 300}),
                "max_read": ("*/inbox", "n1", {"read": True}),
                "purge_delete": ("mtg/offers", "tr1", None),
                "purge_newer_change": ("mtg/pending", "tk1", {"doc": '{"b":2}'})}
        import itertools
        for c in VECTORS["weg_a"]:
            kind, key, fields = want[c["name"]]
            for order in itertools.permutations(c["ops"]):
                st = syncops.State()
                for o in order:
                    st.apply(o)
                v = st.value(kind, key)
                if fields is None:
                    self.assertIsNone(v, c["name"])
                    self.assertEqual(st.kinds[kind][key]["f"], {}, "no values kept")
                else:
                    self.assertEqual({k: v[k] for k in fields}, fields, c["name"])
                    if c["name"] == "purge_newer_change":
                        self.assertEqual(set(st.kinds[kind][key]["f"]), {"doc"})

if __name__ == "__main__":
    unittest.main()
