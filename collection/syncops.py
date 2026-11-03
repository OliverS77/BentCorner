"""Change protocol of the sync (docs/SYNC-PLAN.md §3) – the pure core, no files, no network. The web app has the
same rules in JS; both are checked against docs/web/sync-vectors.json (tools/make_sync_vectors.py).

For the documents that are not logs (lists, binders, decks, deck cards, friends, profile – the library itself is the
sum of the logs, §3b). A change is one small op:

    {"o": "<dev>.<ms>.<n>",      unique: device (4 chars, random per installation) + its clock
     "h": [ms, n, "<dev>"],      Hybrid Logical Clock: wall ms, never backwards; n breaks ties; then the device
     "c": "decks",               the document kind (with the game: "mtg/decks")
     "k": "<key>",               the entry
     "a": 1,                     optional: creates the entry (carries every field in "s")
     "s": {"name": "…"},         set fields – last writer wins PER FIELD (by "h")
     "d": {"n": 1},              add to counters – added up, never overwritten
     "x": 3}                     optional: delete (tombstone); for counted entries the count it saw when deleting

Merging (order of arrival never matters – every rule is commutative):
  - a field: the op with the highest h wins; a group of fields that only make sense together (GROUPS, e.g. a deck
    card's print + foil + language) is ONE field;
  - a counter: the sum of all deltas minus the counts the tombstones saw. A delete and a concurrent +1 → 1 left;
    the counted entry is there while that sum is > 0;
  - an entry without a counter: there once its create was seen, unless its newest op is a delete (a change after
    the delete brings it back – the later clock wins, SYNC-PLAN §3);
  - an op on a key whose create never came stays invisible (never a half entry) and goes with the next snapshot
    after TOMB_DAYS.

The state keeps per entry the winning (h, value) of every field, the counters and the newest create/delete. The
checksum (sum()) covers what the user sees: canonical JSON (sorted keys, no spaces, integers/strings only) of every
present entry, so two devices with the same ops have the same sum.
"""
import hashlib
import json
import secrets
import time

GROUPS = {"deckcards": (("print", ("id", "foil", "lang", "finish")),),
          "listcards": (("print", ("id", "foil", "lang", "finish")),)}
COUNTED = {"deckcards": "n", "listcards": "n"}   # kind -> its counter field
TOMB_DAYS = 90
SKEW_MS = 5 * 60 * 1000                           # the server's time corrects at most ±5 min


def new_device():
    return "".join(secrets.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(4))


def _base(kind):
    return kind.rpartition("/")[2]


class Clock:
    """Hybrid Logical Clock of one device: wall ms (+ the server offset, at most ±5 min), never backwards."""

    def __init__(self, device, ms=0, n=0, now=None):
        self.device, self.ms, self.n = device, ms, n
        self.offset = 0
        self._now = now or (lambda: int(time.time() * 1000))

    def set_server_time(self, server_ms):
        """vault/get and put give the server's time: correct a wrong PC clock, but never by more than 5 min."""
        self.offset = max(-SKEW_MS, min(SKEW_MS, int(server_ms) - self._now()))

    def tick(self):
        wall = self._now() + self.offset
        if wall > self.ms:
            self.ms, self.n = wall, 0
        else:
            self.n += 1
        return [self.ms, self.n, self.device]

    def seen(self, h):
        """An op of another device arrived: our clock never goes behind it."""
        if h[0] > self.ms or (h[0] == self.ms and h[1] > self.n):
            self.ms, self.n = h[0], h[1]


def _hkey(h):
    return (int(h[0]), int(h[1]), str(h[2]))


def op(clock, kind, key, s=None, d=None, create=False, delete=None):
    """A new op of this device. delete: True for an entry without a counter, the count seen for a counted one."""
    h = clock.tick()
    o = {"o": f"{h[2]}.{h[0]}.{h[1]}", "h": h, "c": kind, "k": key}
    if create:
        o["a"] = 1
    if s:
        o["s"] = dict(s)
    if d:
        o["d"] = {k: int(v) for k, v in d.items() if int(v)}
    if delete is not None and delete is not False:
        o["x"] = 1 if delete is True else int(delete)
    return o


class State:
    """The merged state of all ops seen: kind -> key -> entry. apply() in any order gives the same result."""

    def __init__(self):
        self.kinds = {}
        self.ids = set()      # op ids applied (a doubled op is harmless)
        self.top = {}         # device -> highest h seen (for "since" and the snapshot)
        self.base = {}        # device -> top of the snapshot this state started from (ops up to it are in it)

    def _entry(self, kind, key, make):
        ent = self.kinds.setdefault(kind, {}).get(key)
        if ent is None and make:
            ent = self.kinds[kind][key] = {"f": {}, "cnt": {}, "made": False, "alive": None, "dead": None, "gone": 0}
        return ent

    def apply(self, o):
        """-> True if new. Every op is kept in the entry (an op may arrive before the create it follows); whether the
        entry is THERE is decided only from what is kept, so the order of arrival never matters."""
        if o["o"] in self.ids or self.covered(o):
            return False
        self.ids.add(o["o"])
        h = _hkey(o["h"])
        dev = h[2]
        if dev not in self.top or h > _hkey(self.top[dev]):
            self.top[dev] = [h[0], h[1], h[2]]
        kind = o["c"]
        ent = self._entry(kind, o["k"], True)
        hl = list(h)
        if o.get("a"):
            ent["made"] = True
        if "x" in o:
            if ent["dead"] is None or h > _hkey(ent["dead"]):
                ent["dead"] = hl
            if _base(kind) in COUNTED:
                ent["gone"] += int(o["x"])
        else:   # a create or a change: the entry lives (from its create on)
            if ent["alive"] is None or h > _hkey(ent["alive"]):
                ent["alive"] = hl
        for k, v in (o.get("d") or {}).items():
            ent["cnt"][k] = ent["cnt"].get(k, 0) + int(v)
        if o.get("s"):
            for name, fields in _groups(kind, o["s"]):
                cur = ent["f"].get(name)
                if cur is None or h > _hkey(cur[0]):
                    ent["f"][name] = [hl, fields]
        return True

    def covered(self, o):
        """Older than (or as old as) what a snapshot already holds of its device – ops of one device arrive in order,
        so everything up to the snapshot's top for that device is in it."""
        base = self.base.get(o["h"][2])
        return bool(base) and _hkey(o["h"]) <= _hkey(base)

    def present(self, kind, key):
        ent = self._entry(kind, key, False)
        if ent is None or not ent["made"]:
            return False
        cf = COUNTED.get(_base(kind))
        if cf:
            return ent["cnt"].get(cf, 0) - ent["gone"] > 0
        return ent["alive"] is not None and (ent["dead"] is None or _hkey(ent["alive"]) > _hkey(ent["dead"]))

    def value(self, kind, key):
        """-> the entry as the user sees it ({field: value}, counters included) or None."""
        if not self.present(kind, key):
            return None
        ent = self.kinds[kind][key]
        out = {}
        for _name, (_h, fields) in sorted(ent["f"].items()):
            out.update(fields)
        cf = COUNTED.get(_base(kind))
        for k, v in ent["cnt"].items():
            out[k] = v - (ent["gone"] if k == cf else 0)
        return out

    def view(self, kind):
        return {k: self.value(kind, k) for k in sorted(self.kinds.get(kind, {})) if self.present(kind, k)}

    def sum(self, kind):
        return checksum(self.view(kind))

    def compact(self, now_ms):
        """For a snapshot: drop entries gone for more than TOMB_DAYS (deleted, or a change whose create never came) –
        a very late op of such an entry is ignored (covered by the snapshot's top), a device offline that long takes
        the snapshot instead of replaying. -> entries dropped."""
        cut = now_ms - TOMB_DAYS * 86400 * 1000
        n = 0
        for kind, ents in self.kinds.items():
            for key in [k for k, e in ents.items() if not self.present(kind, k)
                        and max([0] + [x[0] for x in (e["alive"], e["dead"]) if x]) < cut]:
                del ents[key]
                n += 1
        return n

    def to_snap(self):
        return {"v": 1, "kinds": self.kinds, "top": self.top}

    @classmethod
    def from_snap(cls, snap):
        st = cls()
        st.kinds = json.loads(json.dumps(snap["kinds"]))
        st.top = {d: list(h) for d, h in (snap.get("top") or {}).items()}
        st.base = {d: list(h) for d, h in st.top.items()}
        return st


def _groups(kind, s):
    """Fields of an op -> [(field name, {field: value})]: a group counts as ONE field."""
    left = dict(s)
    out = []
    for name, members in GROUPS.get(_base(kind), ()):
        if any(m in left for m in members):
            out.append((name, {m: left.pop(m, None) for m in members}))
    out += [(k, {k: v}) for k, v in left.items()]
    return out


def canonical(obj):
    """Sorted keys, no spaces, no floats (a float in synced data is an error: prices etc. are derived, never synced)."""
    def check(x):
        if isinstance(x, float):
            raise ValueError("float in synced data")
        if isinstance(x, dict):
            for v in x.values():
                check(v)
        elif isinstance(x, list):
            for v in x:
                check(v)
    check(obj)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def checksum(view):
    return hashlib.sha256(canonical(view).encode("utf-8")).hexdigest()


def diff_ops(clock, kind, old, new, fields=None):
    """The save() hook: two states of one document ({key: {field: value}}) -> the ops that lead from old to new.
    New entries -> a create with all fields; gone ones -> a delete (counted: with the count seen); changed fields ->
    one op per entry with the changed fields (a group whole); counters -> a delta (new − old), never an overwrite.
    fields: the synced fields (None = all) – derived ones (names, images, prices) stay out."""
    cf = COUNTED.get(_base(kind))
    out = []

    def pick(e):
        return {k: v for k, v in e.items() if (fields is None or k in fields) and k != cf}

    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        if a is None:
            d = {cf: int(b.get(cf, 0))} if cf else None
            out.append(op(clock, kind, key, s=pick(b), d=d, create=True))
            continue
        if b is None:
            out.append(op(clock, kind, key, delete=int(a.get(cf, 0)) if cf else True))
            continue
        pa, pb = pick(a), pick(b)
        changed = {k: pb.get(k) for k in set(pa) | set(pb) if pa.get(k) != pb.get(k)}
        for _name, members in GROUPS.get(_base(kind), ()):
            if any(m in changed for m in members):
                changed.update({m: pb.get(m) for m in members})
        d = {cf: int(b.get(cf, 0)) - int(a.get(cf, 0))} if cf and b.get(cf, 0) != a.get(cf, 0) else None
        if changed or d:
            out.append(op(clock, kind, key, s=changed or None, d=d))
    return out
