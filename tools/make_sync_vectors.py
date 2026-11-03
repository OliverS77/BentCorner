"""Writes docs/web/sync-vectors.json: fixed cases of the change protocol (collection/syncops.py, docs/SYNC-PLAN.md
§3). Each case: the ops (in the order they were made), the view and checksum every device must reach – whatever
order it applies them in. The web app's JS checks the same file.

    python tools/make_sync_vectors.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collection import syncops  # noqa: E402

T0 = 1793600000000   # fixed wall ms (2026-11-02)


class _Fake:
    """Clocks of fixed devices on a shared fake wall clock (ms)."""

    def __init__(self):
        self.now = T0

    def clock(self, dev):
        return syncops.Clock(dev, now=lambda: self.now)


def cases():
    out = []

    def case(name, about, build):
        w = _Fake()
        ops, kinds = build(w)
        st = syncops.State()
        for o in ops:
            st.apply(o)
        out.append({"name": name, "about": about, "ops": ops,
                    "view": {k: st.view(k) for k in kinds}, "sum": {k: st.sum(k) for k in kinds}})

    def fields(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "mtg/decks", "d1", s={"name": "Elves", "format": "commander"}, create=True)
        w.now += 1000
        o2 = syncops.op(a, "mtg/decks", "d1", s={"name": "Elves!"})
        o3 = syncops.op(b, "mtg/decks", "d1", s={"format": "modern"})
        return [o1, o2, o3], ["mtg/decks"]
    case("different_fields", "two devices change different fields of one entry: both stay", fields)

    def same_field(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "mtg/decks", "d1", s={"name": "A"}, create=True)
        w.now += 1000
        o2 = syncops.op(b, "mtg/decks", "d1", s={"name": "from B"})
        o3 = syncops.op(a, "mtg/decks", "d1", s={"name": "from A"})   # same ms, a < b: B wins the tie
        return [o1, o2, o3], ["mtg/decks"]
    case("same_field_tie", "same field, same ms and counter: the device id decides (bbbb > aaaa)", same_field)

    def counter(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "mtg/deckcards", "d1|s1|main", s={"id": "x_0", "foil": False, "lang": "en", "finish": None},
                        d={"n": 2}, create=True)
        w.now += 1000
        o2 = syncops.op(a, "mtg/deckcards", "d1|s1|main", d={"n": 1})
        o3 = syncops.op(b, "mtg/deckcards", "d1|s1|main", d={"n": 1})
        return [o1, o2, o3], ["mtg/deckcards"]
    case("counter_adds", "+1 on two devices = +2", counter)

    def delete_vs_add(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "mtg/deckcards", "d1|s1|main", s={"id": "x_0", "foil": False, "lang": "en", "finish": None},
                        d={"n": 1}, create=True)
        w.now += 1000
        o2 = syncops.op(a, "mtg/deckcards", "d1|s1|main", delete=1)   # A saw 1 and deleted
        o3 = syncops.op(b, "mtg/deckcards", "d1|s1|main", d={"n": 1})  # B added one meanwhile
        return [o1, o2, o3], ["mtg/deckcards"]
    case("delete_vs_add", "A deletes (saw 1), B adds 1 at the same time: 1 left", delete_vs_add)

    def print_group(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "mtg/deckcards", "k", s={"id": "x_0", "foil": False, "lang": "en", "finish": None},
                        d={"n": 1}, create=True)
        w.now += 1000
        o2 = syncops.op(a, "mtg/deckcards", "k", s={"id": "y_0", "foil": False, "lang": "en", "finish": None})
        w.now += 1
        o3 = syncops.op(b, "mtg/deckcards", "k", s={"id": "x_0", "foil": True, "lang": "de", "finish": "foil"})
        return [o1, o2, o3], ["mtg/deckcards"]
    case("print_is_one_field", "print + foil + language + finish change together: the later op wins whole",
         print_group)

    def delete_then_change(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "mtg/binders", "b1", s={"name": "Trade"}, create=True)
        w.now += 1000
        o2 = syncops.op(a, "mtg/binders", "b1", delete=True)
        w.now += 1000
        o3 = syncops.op(b, "mtg/binders", "b1", s={"name": "Trade 2"})   # changed after the delete: back
        o4 = syncops.op(a, "mtg/binders", "b2", s={"name": "Old"}, create=True)
        w.now += 1000
        o5 = syncops.op(b, "mtg/binders", "b2", s={"name": "Older"})
        w.now += 1
        o6 = syncops.op(a, "mtg/binders", "b2", delete=True)            # deleted after the change: gone
        return [o1, o2, o3, o4, o5, o6], ["mtg/binders"]
    case("later_clock_wins", "delete vs change: the later clock wins (b1 back, b2 gone)", delete_then_change)

    def orphan(w):
        a = w.clock("aaaa")
        o1 = syncops.op(a, "mtg/lists", "l9", s={"name": "half"})   # its create never came
        return [o1], ["mtg/lists"]
    case("no_half_entry", "a change on a key whose create never came stays invisible", orphan)
    return out


def clock_steps():
    """One device's clock on a fake wall clock: same ms, wall going back, a server time far off (clamped to ±5 min),
    an op of another device from the future. Each step: what happened and the clock after it."""
    w = _Fake()
    c = w.clock("aaaa")
    out = []

    def step(do, **kw):
        out.append({"do": do, **kw, "now": w.now, "after": [c.ms, c.n, c.offset]})

    step("tick", h=c.tick())
    step("tick", h=c.tick())                         # same ms: n + 1
    w.now -= 2000
    step("tick", h=c.tick())                         # the PC clock went back: never backwards
    w.now += 5000
    step("tick", h=c.tick())
    c.set_server_time(w.now + 3600 * 1000)
    step("server", server=w.now + 3600 * 1000)       # 1 h off: only +5 min
    step("tick", h=c.tick())
    c.set_server_time(w.now - 1000)
    step("server", server=w.now - 1000)
    c.seen([w.now + 10 ** 6, 7, "bbbb"])
    step("seen", seen=[w.now + 10 ** 6, 7, "bbbb"])
    step("tick", h=c.tick())
    c.seen([1, 0, "cccc"])                           # an old op: nothing changes
    step("seen", seen=[1, 0, "cccc"])
    return out


def op_cases():
    """op() for every kind of argument (each from a fresh clock "aaaa" at T0)."""
    args = [dict(kind="mtg/decks", key="d1", s={"name": "Ä ° 🃏"}, create=True),
            dict(kind="mtg/deckcards", key="d1|s1|main", d={"n": 2, "x": 0}),
            dict(kind="mtg/deckcards", key="k", d={"n": 0}),                     # all zero: "d" stays, empty
            dict(kind="mtg/binders", key="b1", delete=True),
            dict(kind="mtg/deckcards", key="k", delete=0),                       # counted, saw 0
            dict(kind="mtg/deckcards", key="k", delete=3, s={}),
            dict(kind="profile", key="me", delete=False, s={"name": None})]
    out = []
    for a in args:
        w = _Fake()
        kw = {k: v for k, v in a.items() if k not in ("kind", "key")}
        out.append({"args": a, "op": syncops.op(w.clock("aaaa"), a["kind"], a["key"], **kw)})
    return out


def diff_cases():
    """diff_ops(): two states of one document -> the ops (clock "aaaa" at T0, ticking per op)."""
    card = {"id": "x_0", "foil": False, "lang": "en", "finish": None}
    raw = [("new, gone, unchanged", "mtg/decks", {"a": {"name": "A"}, "b": {"name": "B"}},
            {"b": {"name": "B"}, "c": {"name": "C", "format": "modern"}}, None),
           ("a changed field and a field set to null", "mtg/decks", {"a": {"name": "A", "format": "x", "note": "n"}},
            {"a": {"name": "A2", "format": "x", "note": None}}, None),
           ("derived fields stay out", "mtg/decks", {"a": {"name": "A", "price": 3}},
            {"a": {"name": "A", "price": 4}, "b": {"name": "B", "price": 1}}, ["name"]),
           ("counted: create with count, delta, delete with the count seen", "mtg/deckcards",
            {"k1": {**card, "n": 2}, "k2": {**card, "n": 1}, "k3": {**card, "n": 4}},
            {"k1": {**card, "n": 5}, "k3": {**card, "n": 4, "lang": "de"}, "k4": {**card, "n": 1}}, None),
           ("counted: count down, foil only -> the whole print", "mtg/listcards", {"k": {**card, "n": 3}},
            {"k": {**card, "foil": True, "n": 1}}, None),
           ("counted: created with no count", "mtg/listcards", {}, {"k": {**card}}, None),
           ("keys in code point order", "mtg/lists", {}, {"é": {"name": 1}, "z": {"name": 2}, "Z": {"name": 3},
                                                          "🃏": {"name": 4}, "￿": {"name": 5}}, None)]
    out = []
    for about, kind, old, new, fields in raw:
        w = _Fake()
        out.append({"about": about, "kind": kind, "old": old, "new": new, "fields": fields,
                    "ops": syncops.diff_ops(w.clock("aaaa"), kind, old, new, fields)})
    return out


def compact_case():
    """compact(): entries gone (deleted, or a change whose create never came) for more than TOMB_DAYS are dropped."""
    w = _Fake()
    a = w.clock("aaaa")
    day = 86400 * 1000
    ops = [syncops.op(a, "mtg/binders", "old", s={"name": "x"}, create=True),
           syncops.op(a, "mtg/binders", "half", s={"name": "y"})]
    ops.append(syncops.op(a, "mtg/binders", "old", delete=True))
    w.now += 10 * day
    ops += [syncops.op(a, "mtg/binders", "new", s={"name": "z"}, create=True),
            syncops.op(a, "mtg/binders", "keep", s={"name": "k"}, create=True)]
    ops.append(syncops.op(a, "mtg/binders", "new", delete=True))
    st = syncops.State()
    for o in ops:
        st.apply(o)
    now = T0 + (syncops.TOMB_DAYS + 5) * day
    dropped = st.compact(now)
    return {"ops": ops, "now": now, "dropped": dropped, "kept": sorted(st.kinds["mtg/binders"]),
            "view": st.view("mtg/binders")}


def snap_case():
    """A snapshot and what comes after it: ops up to its top per device are covered, newer ones apply."""
    w = _Fake()
    a, b = w.clock("aaaa"), w.clock("bbbb")
    before = [syncops.op(a, "mtg/decks", "d1", s={"name": "A"}, create=True),
              syncops.op(b, "mtg/decks", "d2", s={"name": "B"}, create=True)]
    st = syncops.State()
    for o in before:
        st.apply(o)
    snap = json.loads(json.dumps(st.to_snap()))
    w.now += 1000
    after = [syncops.op(a, "mtg/decks", "d1", s={"name": "A2"}),
             syncops.op(syncops.Clock("cccc", now=lambda: w.now), "mtg/decks", "d3", s={"name": "C"}, create=True)]
    st2 = syncops.State.from_snap(snap)
    applied = [st2.apply(o) for o in before + after]
    return {"before": before, "snap": snap, "after": after, "applied": applied, "view": st2.view("mtg/decks"),
            "top": st2.top}


def build():
    return {"about": "Test vectors of the sync change protocol (collection/syncops.py, docs/SYNC-PLAN.md §3). Apply "
                     "the ops of a case in ANY order (each op possibly twice): view and sum must be exactly these. "
                     "sum = sha256 hex of the view as JSON with sorted keys and no spaces (UTF-8, not ASCII-escaped). "
                     "clock/ops/diffs/compact/snap: the other functions step by step (fake wall clock from T0).",
            "groups": {k: [[n, list(m)] for n, m in v] for k, v in syncops.GROUPS.items()},
            "counted": syncops.COUNTED,
            "t0": T0,
            "tomb_days": syncops.TOMB_DAYS,
            "skew_ms": syncops.SKEW_MS,
            "cases": cases(),
            "clock": clock_steps(),
            "ops": op_cases(),
            "diffs": diff_cases(),
            "compact": compact_case(),
            "snap": snap_case()}


if __name__ == "__main__":
    out = ROOT / "docs" / "web" / "sync-vectors.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("written", out)
