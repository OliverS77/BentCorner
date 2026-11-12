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
        o1 = syncops.op(a, "mtg/deckcards", "d1|s1|main", d={"n": 2}, create=True)
        w.now += 1000
        o2 = syncops.op(a, "mtg/deckcards", "d1|s1|main", d={"n": 1})
        o3 = syncops.op(b, "mtg/deckcards", "d1|s1|main", d={"n": 1})
        return [o1, o2, o3], ["mtg/deckcards"]
    case("counter_adds", "+1 on two devices = +2", counter)

    def delete_vs_add(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "mtg/deckcards", "d1|s1|main", d={"n": 1}, create=True)
        w.now += 1000
        o2 = syncops.op(a, "mtg/deckcards", "d1|s1|main", delete=1)   # A saw 1 and deleted
        o3 = syncops.op(b, "mtg/deckcards", "d1|s1|main", d={"n": 1})  # B added one meanwhile
        return [o1, o2, o3], ["mtg/deckcards"]
    case("delete_vs_add", "A deletes (saw 1), B adds 1 at the same time: 1 left", delete_vs_add)

    def card_group(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "mtg/binderslots", "b1|0", s={"sid": "x_0", "lang": "en", "foil": False}, create=True)
        w.now += 1000
        o2 = syncops.op(a, "mtg/binderslots", "b1|0", s={"sid": "y_0", "lang": "en", "foil": False})
        w.now += 1
        o3 = syncops.op(b, "mtg/binderslots", "b1|0", s={"sid": "x_0", "lang": "de", "foil": True})
        return [o1, o2, o3], ["mtg/binderslots"]
    case("card_is_one_field", "a binder pocket's card + language + foil change together: the later op wins whole",
         card_group)

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
    card = {"sid": "x_0", "lang": "en", "foil": False}
    raw = [("new, gone, unchanged", "mtg/decks", {"a": {"name": "A"}, "b": {"name": "B"}},
            {"b": {"name": "B"}, "c": {"name": "C", "format": "modern"}}, None),
           ("a changed field and a field set to null", "mtg/decks", {"a": {"name": "A", "format": "x", "note": "n"}},
            {"a": {"name": "A2", "format": "x", "note": None}}, None),
           ("derived fields stay out", "mtg/decks", {"a": {"name": "A", "price": 3}},
            {"a": {"name": "A", "price": 4}, "b": {"name": "B", "price": 1}}, ["name"]),
           ("counted: create with count, delta, delete with the count seen", "mtg/deckcards",
            {"k1": {"n": 2}, "k2": {"n": 1}, "k3": {"n": 4}},
            {"k1": {"n": 5}, "k3": {"n": 4}, "k4": {"n": 1}}, None),
           ("group: foil only -> the whole card", "mtg/binderslots", {"b|0": {**card}},
            {"b|0": {**card, "foil": True}}, None),
           ("counted: created with no count", "mtg/havecards", {}, {"k": {}}, None),
           ("keys in code point order", "mtg/lists", {}, {"é": {"name": 1}, "z": {"name": 2}, "Z": {"name": 3},
                                                          "🃏": {"name": 4}, "￿": {"name": 5}}, None)]
    out = []
    for about, kind, old, new, fields in raw:
        w = _Fake()
        out.append({"about": about, "kind": kind, "old": old, "new": new, "fields": fields,
                    "ops": syncops.diff_ops(w.clock("aaaa"), kind, old, new, fields)})
    return out


DOCS = {   # a stored document per kind, as the desktop holds it after reading (floats: epoch seconds)
    "lists": {"wish": [{"id": "main", "name": "Wishlist"}], "have": [{"id": "trade", "name": "Trade"},
              {"id": "h1", "name": "Bulk", "shared": True, "items": {"u1": 2}, "prints": {"mh2|267|en|1": 1},
               "print_names": {"mh2|267|en|1": "Counterspell"}}], "custom": [{"id": "c1", "name": "Ideas", "example": True}]},
    "wishcards": {"version": 1, "items": [
        {"name": "Lightning Bolt", "count": 2, "set": None, "number": None, "note": "any", "added": 1793600000.5},
        {"name": "Counterspell", "count": 1, "set": "MH2", "number": "267", "lang": "de", "foil": True, "note": "",
         "added": 1793600001.25, "list": "c1"}]},
    "decks": {"decks": [{"id": "d1", "name": "Burn", "format": "modern", "commanders": [], "notes": "",
              "cards": [{"sid": "s1", "count": 4, "board": "main"}, {"sid": "s2", "count": 2, "board": "side"},
                        {"sid": "s3", "count": 0, "board": "main"}],
              "tokens": {"goblin": 2}, "created": 1793600000.0, "updated": 1793700000.0, "pinned": ["s2", "s1"],
              "folder": "Modern"}]},
    "binders": {"version": 1, "binders": [{"id": "b1", "name": "Rares", "cols": 3, "rows": 3, "created": 1793600000.0,
                "updated": 1793700000.0, "slots": [None, {"sid": "s1", "set": "m10", "number": "146", "lang": "de",
                                                          "foil": False, "name": "Lightning Bolt"}, None]}]},
    "friends": {"0123456789ABCDEF": {"name": "Max", "back": "v3;x", "pid": "p1", "sign_pk": "pk", "status": "ok",
                                     "t": 1793600000.0, "boards": {"mtg/lists": {}, "mtg/b-1": {
                                         "key": "k1", "t": 1793600000, "title": "Rares", "until": 1794800000,
                                         "fetched": 1793600050}}}},
    "friendlibs": {"p1": {"id": "p1", "name": "Max (club)", "folder": "Club", "cards": [["m10", "146"]], "imported": 1.5}},
    "friendnotes": {"p1": "met at the club", "p2": ""},
    "friendfolders": ["Club", "Family"],
    "profile": {"id": "abc", "name": "Oliver", "back": "v3;y"},
    "offers": {"offers": [
        {"id": "tr1", "partner": ["p1", "Max"], "status": "sent", "created": 1793600000.0, "updated": 1793600100.5,
         "versions": [{"v": 1, "give": [["m10", "146", "en", False]], "get": [], "eur": 1.5}]},
        {"id": "tr2", "partner": ["p2", "Eva"], "status": "received", "created": 1793500000.0,
         "updated": 1793500000.0, "versions": [{"v": 1, "give": [], "get": [["sv1", "1", "en", False]]}]}]},
    "pending": {"version": 1, "pending": [
        {"ticket": {"id": "tk1", "v": 2}, "give": [], "get": [["sv1", "1", "en", False]], "partner": ["p1", "Max"],
         "foreign": [], "t": 1793600000.25},
        {"ticket": {"id": "tk2"}, "give": [["m10", "146", "en", False]], "get": [], "partner": ["p2", "Eva"],
         "foreign": ["pokemon"], "t": 1793600001.0}]},
    "alarms": [{"game": "mtg", "kind": "wish", "name": "Ragavan", "set": None, "foil": False, "below": 45.5,
                "src": "cm", "basis": "day", "finish": "any", "hit": True},
               {"game": "pokemon", "kind": "trade", "name": "Pikachu", "sid": "sv1-1", "set": "SV1", "foil": True,
                "above": 12.0, "src": "both", "basis": "avg7", "finish": "f"}],
    "listalarms": [{"game": "mtg", "lkind": "wish", "lid": "main", "drop": 10.0, "rise": None, "src": "cm",
                    "basis": "day", "finish": "any", "base": {"Bolt": 1.5}, "hit": {"Bolt": False}}],
    "devices": {"a1b2": {"name": "Olivers PC", "kind": "pc", "seen": 1793577600000},
                "c3d4": {"name": "Pixel 8", "kind": "phone", "seen": 1793491200000}},
    "inbox": [{"id": "n1", "t": 1793600000.5, "title": "Hi", "text": "Welcome", "via": "news", "read": False},
              {"id": "n2", "t": 1793500000.0, "title": "Old", "text": "x", "via": "direct", "read": True}],
}
DOC_OF = {"havecards": "lists", "deckcards": "decks", "binderslots": "binders",
          "friendboards": "friends"}   # kinds sharing a file


def explode_cases():
    """explode(): every kind of the schema from its stored document -> {key: entry}."""
    return [{"kind": k, "doc": DOCS[DOC_OF.get(k, k)], "entries": syncops.explode(k, DOCS[DOC_OF.get(k, k)])}
            for k in syncops.SCHEMA]


def diff_doc_cases():
    """diff_doc(): a whole document old -> new: the ops (create_only fields only in creates, derived/local never)."""
    old = DOCS["decks"]
    new = json.loads(json.dumps(old))
    d = new["decks"][0]
    d.update(name="Burn 2", updated=1793800000.0)                 # updated is local: no op for it
    d["cards"][0]["count"] = 3
    d["cards"].append({"sid": "s9", "count": 1, "board": "maybe"})
    new["decks"].append({"id": "d2", "name": "New", "format": "casual", "commanders": [], "cards": [],
                         "tokens": {}, "created": 1793800000.0, "updated": 1793800000.0, "notes": ""})
    out = []
    for kind in ("decks", "deckcards"):
        w = _Fake()
        ops, snap = syncops.diff_doc(w.clock("aaaa"), "mtg", kind, old, new)
        out.append({"kind": kind, "game": "mtg", "old": old, "new": new, "ops": ops, "snap": snap})
    w = _Fake()   # a global kind: "c" is "*/profile" whatever game is open
    old_p, new_p = DOCS["profile"], dict(DOCS["profile"], name="Oli")
    ops, snap = syncops.diff_doc(w.clock("aaaa"), "pokemon", "profile", old_p, new_p)
    out.append({"kind": "profile", "game": "pokemon", "old": old_p, "new": new_p, "ops": ops, "snap": snap})
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


def mutate(kind, entries):
    """Delete one entry, change one field of another, add a new one (a clone with a new key)."""
    spec = syncops.SCHEMA[kind]
    m = json.loads(json.dumps(entries))
    keys = sorted(m)
    if len(keys) > 1:
        del m[keys[0]]
    key = keys[-1]
    e = m[key]
    if spec.get("counted"):
        e[spec["counted"]] += 1
    for f in spec.get("fields", []) + [x for _n, ms in spec.get("groups", []) for x in ms]:
        if f in ("kind", "pos") or f not in e:
            continue
        v = e[f]
        if f in ("doc", "versions"):   # JSON texts: change the content, keep it JSON
            obj = json.loads(v)
            e[f] = syncops._text(obj + ["z"] if isinstance(obj, list) else {**obj, "z": 1})
            break
        e[f] = (not v) if isinstance(v, bool) else v + 1 if isinstance(v, int) else v + "!" \
            if isinstance(v, str) else v + ["z"] if isinstance(v, list) else {**v, "z": 1}
        break
    if key == "me":
        return m
    new = json.loads(json.dumps(e))
    if kind == "binderslots":
        b, i = key.split("|")
        nk = f"{b}|{int(i) + 7}"
    elif kind == "deckcards":
        d, sid, board = key.split("|")
        nk = f"{d}|{sid}x|{board}"
    elif kind == "wishcards":
        new["name"] += " II"
        nk = f"{key.split('|', 1)[0]}|{syncops.wish_key(new)}"
    elif kind == "pending":   # the key is the ticket id inside the doc
        nk = key + "x"
        doc = json.loads(new["doc"])
        doc["ticket"] = dict(doc.get("ticket") or {}, id=nk)
        new["doc"] = syncops._text(doc)
    else:
        nk = key + "x"
    m[nk] = new
    return m


def implode_cases():
    """implode(): per kind the stored document, a view (one entry deleted, one changed, one added) and the document
    implode makes of it – only what differs changes, derived/local fields and untouched entries stay. A file with two
    kinds goes through both, the outer one first."""
    out = []
    for k in syncops.SCHEMA:
        doc = DOCS[DOC_OF.get(k, k)]
        view = mutate(k, syncops.explode(k, doc))
        out.append({"kind": k, "doc": doc, "view": view, "out": syncops.implode(k, doc, view)})
    return out


def seed_cases():
    """seed_ops(): switching the sync on – the vault's ops are applied first ("vault"), then the device records its
    documents against it ("ops", device bbbb from T0 + 1000): unknown entries as creates, known ones only the
    difference (fields as a change, counters as a delta), the same ones not at all."""
    w = _Fake()
    a = w.clock("aaaa")
    doc = DOCS["decks"]
    vault = []
    for kind in ("decks", "deckcards"):
        vault += syncops.seed_ops(a, "mtg", kind, {"decks": doc["decks"][:1]})[0]
    st = syncops.State()
    for o in vault:
        st.apply(o)
    w.now += 1000
    b = w.clock("bbbb")
    d1 = json.loads(json.dumps(doc["decks"][0]))
    d1["name"] += " (here)"                       # the same key, another name: a change with this clock
    d1["cards"][0]["count"] += 1                  # another count: a delta, never the sum
    mine = dict(doc, decks=[d1] + doc["decks"][1:] + [dict(doc["decks"][0], id="d7", name="Only here")])
    out = []
    for kind in ("decks", "deckcards"):
        ops, snap = syncops.seed_ops(b, "mtg", kind, mine, st)
        out.append({"kind": kind, "game": "mtg", "doc": mine, "ops": ops, "snap": snap})
    return {"vault": vault, "cases": out, "counters": seed_counter_cases()}


def seed_counter_cases():
    """Counters at switching on: the seed is the delta to the vault as fetched. "late": what A did after B fetched
    (before B's seed arrived). Every order of base + late + seeded gives n."""
    out = []
    for name, late_op, n in (("a_adds_2", {"d": {"n": 2}}, 6), ("a_deletes_seen_3", {"delete": 3}, 1),
                             ("nothing", None, 4)):
        w = _Fake()
        a, b = w.clock("aaaa"), w.clock("bbbb")
        deck = {"id": "d1", "name": "Burn", "cards": [{"sid": "s1", "count": 3, "board": "main"}]}
        base = []
        for kind in ("decks", "deckcards"):
            base += syncops.seed_ops(a, "mtg", kind, {"decks": [deck]})[0]
        st = syncops.State()
        for o in base:
            st.apply(o)
        w.now += 1000
        late = [syncops.op(a, "mtg/deckcards", "d1|s1|main", **late_op)] if late_op else []
        mine = {"decks": [dict(deck, cards=[{"sid": "s1", "count": 4, "board": "main"}])]}
        seeded = syncops.seed_ops(b, "mtg", "deckcards", mine, st)[0]
        out.append({"name": name, "base": base, "late": late, "doc": mine, "seeded": seeded, "n": n})
    return out


def vault_cases():
    """The vault packages (SYNC-PLAN §3): per package its canonical JSON and a packed sample (zlib, Base64) – zlib bytes
    of two compressors may differ, so the web checks unpack(sample) == json and unpack(own pack) == json, never the
    bytes. sealed_b64: the add sealed with vault_seal_bytes (seed and nonce of pairing-vectors.json)."""
    import base64
    from net import pairing
    pair = json.loads((ROOT / "docs" / "web" / "pairing-vectors.json").read_text("utf-8"))
    w = _Fake()
    a = w.clock("aaaa")
    st = syncops.State()
    mine = [syncops.op(a, "mtg/decks", "d1", s={"name": "Elfen – grün"}, create=True),
            syncops.op(a, "mtg/deckcards", "d1|abc|main", d={"n": 4}, create=True)]
    for o in mine:
        st.apply(o)
    [add] = syncops.add_packages("aaaa", mine, st)
    snap = syncops.snap_package("aaaa", st, T0 + 1000)

    def one(data):
        obj = syncops.unpack(data)
        return {"json": syncops.canonical(obj), "zlib_b64": base64.b64encode(data).decode()}
    return {"add": {**one(add), "sealed_b64": pairing.vault_seal_bytes(pair["seed_b64"], add,
                                                                       bytes.fromhex(pair["nonce_hex"]))},
            "snap": one(snap), "pack_v": syncops.PACK_V, "add_max": syncops.ADD_MAX, "unpack_max": syncops.UNPACK_MAX}


def weg_a_cases():
    """Weg (a) (legal/ports 06.11.): a MAX field takes the larger value in any order (a board's "fetched", a message
    read on one device stays read); a purge kind (offers, pending, friendboards): the delete takes every older value
    with it, an older change arriving after it stays out, a newer one brings the entry back with only its own values."""
    out = []

    def case(name, about, build):
        w = _Fake()
        ops, kinds = build(w)
        views = []
        for order in (ops, list(reversed(ops))):
            st = syncops.State()
            for o in order:
                st.apply(o)
            views.append(({k: st.view(k) for k in kinds}, {k: st.sum(k) for k in kinds},
                          {k: {key: e["f"] for key, e in st.kinds.get(k, {}).items()} for k in kinds}))
        assert views[0] == views[1], name
        out.append({"name": name, "about": about, "ops": ops, "view": views[0][0], "sum": views[0][1],
                    "fields_kept": views[0][2]})

    def max_fetched(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "*/friendboards", "F1|mtg/lists", s={"key": "k", "t": 5, "title": "", "fetched": 100},
                        create=True)
        w.now += 1000
        o2 = syncops.op(b, "*/friendboards", "F1|mtg/lists", s={"fetched": 300})
        w.now += 1000
        o3 = syncops.op(a, "*/friendboards", "F1|mtg/lists", s={"fetched": 200})   # later, but smaller
        return [o1, o2, o3], ["*/friendboards"]
    case("max_fetched", "a board's fetched cursor: the larger value wins even against a later write", max_fetched)

    def max_read(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "*/inbox", "n1", s={"t": 1, "title": "Hi", "text": "x", "via": "news", "read": False},
                        create=True)
        w.now += 1000
        o2 = syncops.op(b, "*/inbox", "n1", s={"read": True})
        w.now += 1000
        o3 = syncops.op(a, "*/inbox", "n1", s={"read": False})
        return [o1, o2, o3], ["*/inbox"]
    case("max_read", "a message read on one device stays read everywhere", max_read)

    def purge(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "mtg/offers", "tr1", s={"status": "sent", "partner": ["p1", "Max"], "versions": "[1]",
                                                   "updated": 1}, create=True)
        w.now += 1000
        late = syncops.op(b, "mtg/offers", "tr1", s={"status": "received"})   # B, before it saw the delete
        w.now += 1000
        dele = syncops.op(a, "mtg/offers", "tr1", delete=True)
        return [o1, late, dele], ["mtg/offers"]
    case("purge_delete", "a deleted offer keeps no values; B's older change arriving after the delete stays out",
         purge)

    def purge_back(w):
        a, b = w.clock("aaaa"), w.clock("bbbb")
        o1 = syncops.op(a, "mtg/pending", "tk1", s={"doc": '{"a":1}'}, create=True)
        w.now += 1000
        dele = syncops.op(a, "mtg/pending", "tk1", delete=True)
        w.now += 1000
        back = syncops.op(b, "mtg/pending", "tk1", s={"doc": '{"b":2}'})        # newer than the delete
        return [o1, dele, back], ["mtg/pending"]
    case("purge_newer_change", "a change newer than the delete brings the entry back – with only its own values",
         purge_back)
    return out


def build():
    return {"about": "Test vectors of the sync change protocol (collection/syncops.py, docs/SYNC-PLAN.md §3). Apply "
                     "the ops of a case in ANY order (each op possibly twice): view and sum must be exactly these. "
                     "sum = sha256 hex of the view as JSON with sorted keys and no spaces (UTF-8, not ASCII-escaped). "
                     "clock/ops/diffs/compact/snap: the other functions step by step (fake wall clock from T0).",
            "schema": syncops.SCHEMA,
            "snap_ops": syncops.SNAP_OPS,
            "local_settings": syncops.LOCAL_SETTINGS,
            "groups": {k: [[n, list(m)] for n, m in v] for k, v in syncops.GROUPS.items()},
            "counted": syncops.COUNTED,
            "t0": T0,
            "tomb_days": syncops.TOMB_DAYS,
            "skew_ms": syncops.SKEW_MS,
            "cases": cases(),
            "clock": clock_steps(),
            "ops": op_cases(),
            "diffs": diff_cases(),
            "explode": explode_cases(),
            "diff_doc": diff_doc_cases(),
            "compact": compact_case(),
            "snap": snap_case(),
            "implode": implode_cases(),
            "seed": seed_cases(),
            "weg_a": weg_a_cases(),
            "max": {k: sorted(v) for k, v in syncops.MAXF.items()},
            "purge": sorted(syncops.PURGE),
            "vault": vault_cases()}


if __name__ == "__main__":
    out = ROOT / "docs" / "web" / "sync-vectors.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("written", out)
