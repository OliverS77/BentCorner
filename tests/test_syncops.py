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
        old = {"k1": {"id": "a_0", "foil": False, "lang": "en", "finish": None, "n": 2, "name": "A"},
               "k2": {"id": "b_0", "foil": False, "lang": "en", "finish": None, "n": 1, "name": "B"}}
        new = {"k1": {"id": "a_0", "foil": True, "lang": "en", "finish": None, "n": 3, "name": "A"},
               "k3": {"id": "c_0", "foil": False, "lang": "de", "finish": None, "n": 4, "name": "C"}}
        fields = ("id", "foil", "lang", "finish", "n")   # "name" is derived: never synced
        st = syncops.State()
        for o in syncops.diff_ops(self.c, "mtg/deckcards", {}, old, fields):
            st.apply(o)
        self.now[0] += 1
        ops = syncops.diff_ops(self.c, "mtg/deckcards", old, new, fields)
        k1 = next(o for o in ops if o["k"] == "k1")
        self.assertEqual(k1["d"], {"n": 1})                                  # a delta, not an overwrite
        self.assertEqual(set(k1["s"]), {"id", "foil", "lang", "finish"})     # the print group whole
        for o in ops:
            st.apply(o)
        strip = {k: {f: v for f, v in e.items() if f != "name"} for k, e in new.items()}
        self.assertEqual(st.view("mtg/deckcards"), strip)

    def test_no_change_no_op(self):
        doc = {"d1": {"name": "x"}}
        self.assertEqual(syncops.diff_ops(self.c, "mtg/decks", doc, json.loads(json.dumps(doc))), [])

    def test_floats_refused(self):
        with self.assertRaises(ValueError):
            syncops.checksum({"k": {"eur": 1.5}})


if __name__ == "__main__":
    unittest.main()
