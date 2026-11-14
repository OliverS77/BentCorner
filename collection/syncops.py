"""Change protocol of the sync (docs/SYNC-PLAN.md §3) – the pure core, no files, no network. The web app has the
same rules in JS; both are checked against docs/web/sync-vectors.json (tools/make_sync_vectors.py).

For the documents that are not logs (lists, binders, decks, deck cards, friends, profile – the library itself is the
sum of the logs, §3b). A change is one small op:

    {"o": "<dev>.<ms>.<n>",      unique: device (4 chars, random per installation) + its clock
     "h": [ms, n, "<dev>"],      Hybrid Logical Clock: wall ms, never backwards; n breaks ties; then the device
     "c": "decks",               the document kind (with the game: "mtg/decks")
     "k": "<key>",               the entry
     "a": 1,                     optional: creates the entry (carries every field in "s")
     "s": {"name": "…"},         set fields – last writer wins PER FIELD (by "h"); a MAX field: the larger value
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
import math
import secrets
import time
import zlib

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
        self.takeover = None  # {"dev", "at" ms}: the last „keep this device's data“ (SYNC-LOGS §4), carried on; "device": "pc"|"phone"

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
        base = _base(kind)
        if "x" in o:
            if ent["dead"] is None or h > _hkey(ent["dead"]):
                ent["dead"] = hl
                if base in PURGE:   # the delete takes every older value with it (whatever came first)
                    ent["f"] = {n: v for n, v in ent["f"].items() if _hkey(v[0]) > h}
            if base in COUNTED:
                ent["gone"] += int(o["x"])
        else:   # a create or a change: the entry lives (from its create on)
            if ent["alive"] is None or h > _hkey(ent["alive"]):
                ent["alive"] = hl
        for k, v in (o.get("d") or {}).items():
            ent["cnt"][k] = ent["cnt"].get(k, 0) + int(v)
        if o.get("s") and not (base in PURGE and ent["dead"] is not None and h <= _hkey(ent["dead"])):
            mx = MAXF.get(base, ())
            for name, fields in _groups(kind, o["s"]):
                cur = ent["f"].get(name)
                if name in mx:   # the larger value wins (ties: the later clock) – never goes back
                    if cur is None or _max_key(fields[name], h) > _max_key(cur[1][name], _hkey(cur[0])):
                        ent["f"][name] = [hl, fields]
                elif cur is None or h > _hkey(cur[0]):
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
        out = {"v": 1, "kinds": self.kinds, "top": self.top}
        if self.takeover:
            out["takeover"] = dict(self.takeover)
        return out

    def purge(self):
        """Before a snap goes up (legal, Datenschutz 5a): an entry that is not there keeps no values – fields gone, a
        counter only its net number (what later deltas add to; no content). Its clocks stay, so a late older op
        still loses against the delete. -> entries purged."""
        n = 0
        for kind, ents in self.kinds.items():
            cf = COUNTED.get(_base(kind))
            for key, e in ents.items():
                if self.present(kind, key) or (not e["f"] and not e["gone"] and set(e["cnt"]) <= {cf}):
                    continue
                net = (e["cnt"].get(cf, 0) - e["gone"]) if cf else 0
                e["f"], e["cnt"], e["gone"] = {}, ({cf: net} if cf and net else {}), 0
                n += 1
        return n

    @classmethod
    def from_snap(cls, snap):
        st = cls()
        st.kinds = json.loads(json.dumps(snap["kinds"]))
        st.top = {d: list(h) for d, h in (snap.get("top") or {}).items()}
        st.base = {d: list(h) for d, h in st.top.items()}
        st.takeover = dict(snap["takeover"]) if snap.get("takeover") else None
        return st


def _max_key(v, h):
    """Order of a MAX field's values: None lowest, then numbers / booleans (False < True), ties by the clock."""
    return (v is not None, v if isinstance(v, (int, float, bool)) else 0, h)


def _groups(kind, s):
    """Fields of an op -> [(field name, {field: value})]: a group counts as ONE field."""
    left = dict(s)
    out = []
    for name, members in GROUPS.get(_base(kind), ()):
        if any(m in left for m in members):
            out.append((name, {m: left.pop(m, None) for m in members}))
    out += [(k, {k: v}) for k, v in left.items()]
    return out


# ---------- The schema (labs/sync/SCHEMA-ENTWURF.md, lead 03.11.2026): what of each document is synced ----------
# Per kind: how a stored document splits into entries (explode), the entry key, the synced fields (last writer wins
# each), groups (several fields as ONE), the counter, fields only sent when an entry is created, derived fields (every
# device computes them from its own card data – never sent, not in the checksum) and local ones (stay on the device).
# The library itself is not here: it is the sum of the logs (SYNC-PLAN §3b). The web app reads this from the vectors
# (docs/web/sync-vectors.json "schema") and splits its documents the same way: the web keeps each deck (binder …)
# as its own document – it explodes the same entries from them (a deck document gone = the deck and its cards
# deleted). "global": not per game – the op's "c" is "*/<kind>" (one profile, not one per game).
SCHEMA = {
    "lists": {"file": "lists.json", "explode": "wish[] / have[] / custom[] -> one entry per list", "key": "id",
              "fields": ["kind", "name", "shared", "pos", "rule", "scan_keep"], "derived": ["example"]},
    "havecards": {"file": "lists.json", "explode": "have[].items {uid: n} and have[].prints {printkey: n}",
                  "key": "<list>|u|<uid>  /  <list>|p|<set|number|lang|foil>", "counted": "n",
                  "derived": ["print_names"]},
    "wishcards": {"file": "wishlist.json", "explode": "items[] -> one entry per wish",
                  "key": "<list>|<wish_key>", "fields": ["note"], "counted": "n",
                  "create_only": ["added", "name", "set", "number", "lang", "foil"]},
    "decks": {"file": "decks.json", "explode": "decks[] (web: one deck per document) -> one entry per deck", "key": "id",
              "fields": ["name", "format", "notes", "folder", "built", "cover", "version_of", "commanders", "pinned",
                         "tokens"], "create_only": ["created"], "local": ["updated"]},
    "deckcards": {"file": "decks.json", "explode": "decks[].cards[] (web: the deck document's cards[]) -> one per row",
                  "key": "<deck>|<sid>|<board>", "counted": "n"},
    "binders": {"file": "binders.json", "explode": "binders[] -> one entry per binder", "key": "id",
                "fields": ["name", "cols", "rows", "pos"], "create_only": ["created"], "local": ["updated"]},
    "binderslots": {"file": "binders.json", "explode": "binders[].slots[i] (only filled ones)", "key": "<binder>|<i>",
                    "groups": [["card", ["sid", "lang", "foil"]]], "derived": ["set", "number", "name"]},
    "friends": {"file": "settings.json relay.friends", "explode": "{address: friend}", "key": "address",
                "fields": ["status", "hide_back"], "groups": [["peer", ["name", "back", "pid", "sign_pk"]]],
                "local": ["t", "last_list", "last_change", "boards"], "after_pairing": True},
    "friendlibs": {"file": "my-data/friends/<pid>.json", "explode": "{pid: file} -> one entry per friend",
                   "key": "pid", "fields": ["name", "folder"],
                   "local": ["cards", "wants", "library", "imported", "previous", "date", "what", "source"],
                   "after_pairing": True},
    "friendnotes": {"file": "settings.json friend_notes", "explode": "{pid: note}", "key": "pid", "fields": ["note"],
                    "global": True, "after_pairing": True},
    "friendfolders": {"file": "settings.json friend_folders", "explode": "the folder list as one entry", "key": "me",
                      "fields": ["folders"], "global": True, "after_pairing": True},
    "profile": {"file": "settings.json profile", "explode": "the one profile", "key": "me",
                "fields": ["name", "back"], "create_only": ["id"], "global": True},
    # Weg (a) (legal/ports 06.11.): trades in progress and what friends shared travel too – "purge": a delete takes
    # every older value with it at once and an older change arriving later stays out (Datenschutz 5a)
    "offers": {"file": "offers.json", "explode": "offers[] -> one entry per trade", "key": "id",
               "fields": ["status", "partner", "versions", "updated"], "create_only": ["created"], "purge": True,
               "after_pairing": True},
    "pending": {"file": "pending-trades.json", "explode": "pending[] -> one entry per ticket", "key": "ticket id",
                "fields": ["doc"], "purge": True, "after_pairing": True},
    "friendboards": {"file": "settings.json relay.friends[].boards", "explode": "{address: {boards: {game/slot: …}}}",
                     "key": "<address>|<game>/<slot>", "groups": [["board", ["key", "t", "title", "until"]]],
                     "max": ["fetched"], "global": True, "purge": True, "after_pairing": True},
    "inbox": {"file": "settings.json inbox", "explode": "inbox[] -> one entry per message", "key": "id",
              "create_only": ["t", "title", "text", "via"], "max": ["read"], "global": True},
    # price alarms (collection/alarms.py; legal's list 06.11. – they were missing): the limits in whole cents; whether
    # one was reported ("hit") and a list alarm's starting prices ("base", they grow with the list) stay on the device
    "alarms": {"file": "settings.json price_alarms", "explode": "price_alarms[] -> one entry per alarm",
               "key": "<game>|<kind>|<name>|<set>|<sid>|<foil>|<psid>",
               "fields": ["below", "above", "src", "basis", "finish"], "local": ["hit"], "global": True},
    "listalarms": {"file": "settings.json list_alarms", "explode": "list_alarms[] -> one entry per list alarm",
                   "key": "<game>|<lkind>|<lid>", "fields": ["drop", "rise", "src", "basis", "finish"],
                   "local": ["base", "hit"], "global": True},
    # the own devices (lead 07.11.): each writes its own entry; "seen" (day, ms) only grows – Deine Geräte lists them,
    # the delete page asks only if there are others; after „Gerät entfernen“ only the removing device is left
    "devices": {"file": "sync meta (each device its own entry)", "explode": "{dev: {name, kind, seen}}",
                "key": "dev", "fields": ["name", "kind"], "max": ["seen"], "global": True},
}
# settings that always stay on the device (desktop and web): view state, this device's sync bookkeeping, backups
LOCAL_SETTINGS = ["friend_folders_closed", "friend_sort", "friend_sort_rev", "setup", "backup_last", "backup_risk_ok",
                  "sync_dev", "sync_clock", "sync_ops", "pending_trades", "orbit_age"]
SNAP_OPS = 500   # one save producing more ops than this for a kind (a big import): a snap of that kind instead
GROUPS = {k: tuple((n, tuple(m)) for n, m in v["groups"]) for k, v in SCHEMA.items() if v.get("groups")}
COUNTED = {k: v["counted"] for k, v in SCHEMA.items() if v.get("counted")}
MAXF = {k: frozenset(v["max"]) for k, v in SCHEMA.items() if v.get("max")}   # merged by the larger value, any order
PURGE = frozenset(k for k, v in SCHEMA.items() if v.get("purge"))


def _ms(t):
    """Timestamps as whole milliseconds – the checksum allows no floats."""
    return int(round(float(t) * 1000)) if t not in (None, "") else None


def wish_key(w):
    """The same as collection.trade.wish_key (tests compare them): name|set|number, + |lang|foil for a pinned print."""
    key = f"{w['name']}|{(w.get('set') or '').lower()}|{w.get('number') or ''}"
    if w.get("set") and (w.get("lang") or w.get("foil")):
        key += f"|{w.get('lang') or 'en'}|{1 if w.get('foil') else 0}"
    return key


def _clean(e):
    return {k: v for k, v in e.items() if v is not None}


def explode(kind, doc):
    """A stored document (as the app holds it after reading) -> {key: entry} with only schema fields."""
    doc = doc or {}
    out = {}
    if kind == "lists":
        for part in ("wish", "have", "custom"):
            for i, l in enumerate(doc.get(part) or []):
                out[l["id"]] = _clean({"kind": part, "name": l.get("name", ""), "shared": bool(l.get("shared")),
                                       "pos": i, "rule": l.get("rule"),
                                       "scan_keep": True if l.get("scan_keep") else None})   # wishhit, 14.11.
    elif kind == "havecards":
        for l in doc.get("have") or []:
            for uid, n in (l.get("items") or {}).items():
                out[f"{l['id']}|u|{uid}"] = {"n": int(n)}
            for pk, n in (l.get("prints") or {}).items():
                out[f"{l['id']}|p|{pk}"] = {"n": int(n)}
    elif kind == "wishcards":
        for w in doc.get("items") or []:
            out[f"{w.get('list') or 'main'}|{wish_key(w)}"] = _clean({
                "n": int(w.get("count", 1)), "note": w.get("note") or "", "added": _ms(w.get("added")),
                "name": w["name"], "set": w.get("set"), "number": w.get("number"), "lang": w.get("lang"),
                "foil": bool(w["foil"]) if "foil" in w else None})
    elif kind == "decks":
        for d in doc.get("decks") or []:
            out[d["id"]] = _clean({"name": d.get("name", ""), "format": d.get("format"), "notes": d.get("notes", ""),
                                   "folder": d.get("folder"), "built": d.get("built"), "cover": d.get("cover"),
                                   "version_of": d.get("version_of"), "commanders": list(d.get("commanders") or []),
                                   "pinned": sorted(d.get("pinned") or []), "tokens": dict(d.get("tokens") or {}),
                                   "created": _ms(d.get("created"))})
    elif kind == "deckcards":
        for d in doc.get("decks") or []:
            for c in d.get("cards") or []:
                if int(c.get("count", 0)) > 0:
                    out[f"{d['id']}|{c['sid']}|{c.get('board') or 'main'}"] = {"n": int(c["count"])}
    elif kind == "binders":
        for i, b in enumerate(doc.get("binders") or []):
            out[b["id"]] = _clean({"name": b.get("name", ""), "cols": b.get("cols"), "rows": b.get("rows"), "pos": i,
                                   "created": _ms(b.get("created"))})
    elif kind == "binderslots":
        for b in doc.get("binders") or []:
            for i, s in enumerate(b.get("slots") or []):
                if s:
                    out[f"{b['id']}|{i}"] = {"sid": s["sid"], "lang": s.get("lang") or "en", "foil": bool(s.get("foil"))}
    elif kind == "friends":
        for code, f in doc.items():
            out[code] = _clean({"status": f.get("status"), "hide_back": bool(f.get("hide_back")), "name": f.get("name"),
                                "back": f.get("back"), "pid": f.get("pid"), "sign_pk": f.get("sign_pk")})
    elif kind == "friendlibs":
        for pid, f in doc.items():
            out[pid] = _clean({"name": f.get("name"), "folder": f.get("folder")})
    elif kind == "friendnotes":
        for pid, note in doc.items():
            if note:
                out[pid] = {"note": note}
    elif kind == "friendfolders":
        if doc:
            out["me"] = {"folders": list(doc)}
    elif kind == "profile":
        if doc:
            out["me"] = _clean({"name": doc.get("name", ""), "back": doc.get("back"), "id": doc.get("id")})
    elif kind == "offers":
        for o in doc.get("offers") or []:
            out[o["id"]] = _clean({"status": o.get("status"), "partner": list(o.get("partner") or []),
                                   "versions": _text(o.get("versions") or []), "updated": _ms(o.get("updated")),
                                   "created": _ms(o.get("created"))})
    elif kind == "pending":
        for x in doc.get("pending") or []:
            tid = (x.get("ticket") or {}).get("id")
            if tid:
                out[str(tid)] = {"doc": _text(x)}
    elif kind == "friendboards":
        for code, f in doc.items():
            for gs, b in ((f or {}).get("boards") or {}).items():
                if b and b.get("key"):
                    out[f"{code}|{gs}"] = _clean({"key": b["key"], "t": int(b.get("t") or 0),
                                                  "title": b.get("title") or "",
                                                  "until": int(b["until"]) if b.get("until") is not None else None,
                                                  "fetched": int(b.get("fetched") or 0)})
    elif kind == "alarms":
        for a in doc or []:
            out[_alarm_key(a)] = _clean({"below": _cents(a.get("below")), "above": _cents(a.get("above")),
                                         "src": a.get("src"), "basis": a.get("basis"), "finish": a.get("finish")})
    elif kind == "listalarms":
        for a in doc or []:
            if a.get("lid"):
                out[_list_alarm_key(a)] = _clean({"drop": _cents(a.get("drop")), "rise": _cents(a.get("rise")),
                                                  "src": a.get("src"), "basis": a.get("basis"),
                                                  "finish": a.get("finish")})
    elif kind == "devices":
        for dev, e in (doc or {}).items():
            out[str(dev)] = _clean({"name": str(e.get("name") or "")[:60], "kind": e.get("kind") or "pc",
                                    "seen": int(e.get("seen") or 0)})
    elif kind == "inbox":
        for m in doc or []:
            if m.get("id"):
                out[str(m["id"])] = _clean({"t": _ms(m.get("t")), "title": m.get("title") or "",
                                            "text": m.get("text") or "", "via": m.get("via"),
                                            "read": bool(m.get("read"))})
    else:
        raise KeyError(kind)
    return out


def _cents(x):
    """A price limit / percentage as whole hundredths (no floats in the checksum); None stays None."""
    return int(math.floor(float(x) * 100 + 0.5)) if x not in (None, "") else None


def _alarm_key(a):
    return "|".join([a.get("game") or "mtg", a.get("kind") or "", a.get("name") or "", (a.get("set") or "").lower(),
                     str(a.get("sid") or ""), "1" if a.get("foil") else "0", str(a.get("psid") or "")])


def _list_alarm_key(a):
    return "|".join([a.get("game") or "mtg", a.get("lkind") or "", str(a.get("lid"))])


def _text(obj):
    """A JSON text of a whole object (floats allowed – carried as it is, compared by content: synclogs.same)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def synced_fields(kind):
    """Every field of an entry that travels: synced, groups, create_only and the counter (derived/local never)."""
    spec = SCHEMA[_base(kind)]
    out = set(spec.get("fields", [])) | {m for _n, ms in spec.get("groups", []) for m in ms}
    out |= set(spec.get("create_only", [])) | set(spec.get("max", []))
    return out | ({spec["counted"]} if spec.get("counted") else set())


def _wanted(kind, entries):
    keep = synced_fields(kind)
    return {k: {f: v for f, v in e.items() if f in keep and v is not None} for k, e in entries.items()}


def _secs(ms):
    return ms / 1000 if ms is not None else None


def _put(obj, field, value):
    """Set a document field – None removes it (explode reads a missing field as None)."""
    if value is None:
        obj.pop(field, None)
    else:
        obj[field] = value


def implode(kind, doc, view):
    """The counterpart of explode: the merged entries of one kind (State.view, or explode of another device) written
    back into this device's document. Only what differs changes – derived and local fields, unknown keys and the
    order of untouched entries stay; implode(kind, doc, explode(kind, doc)) == doc. A file with two kinds goes
    through both, the outer one first (lists -> havecards, decks -> deckcards, binders -> binderslots): entries
    whose outer one is gone stay invisible. -> a new document (doc is not changed)."""
    doc = json.loads(json.dumps(doc)) if doc is not None else None
    want, have = _wanted(kind, view), _wanted(kind, explode(kind, doc))

    def changed(key, fields):
        a, b = have.get(key, {}), want[key]
        return [f for f in fields if a.get(f) != b.get(f)]

    if kind == "lists":
        doc = doc if doc is not None else {}
        parts = ("wish", "have", "custom")
        by_id = {l["id"]: l for p in parts for l in doc.get(p) or []}
        new = {p: [] for p in parts}
        for key, e in sorted(want.items(), key=lambda kv: (kv[1].get("pos", 0), kv[0])):
            l = by_id.get(key) or ({"id": key, "items": {}, "prints": {}} if e.get("kind") == "have" else {"id": key})
            for f in changed(key, ("name", "shared", "rule", "scan_keep")):
                _put(l, f, e.get(f) if f != "shared" else bool(e.get(f)))
            new[e.get("kind") if e.get("kind") in parts else "custom"].append(l)
        for p in parts:
            if new[p] or p in doc:
                doc[p] = new[p]
    elif kind == "havecards":
        for l in (doc or {}).get("have") or []:
            for sect, tag in (("items", "u"), ("prints", "p")):
                pre = f"{l['id']}|{tag}|"
                cur = l.get(sect) or {}
                out = {k: want[pre + k]["n"] for k in cur if pre + k in want}
                out.update({key[len(pre):]: e["n"] for key, e in sorted(want.items())
                            if key.startswith(pre) and key[len(pre):] not in out})
                if out or sect in l:
                    l[sect] = out
    elif kind == "wishcards":
        doc = doc if doc is not None else {}
        items, seen = [], set()
        for w in doc.get("items") or []:
            key = f"{w.get('list') or 'main'}|{wish_key(w)}"
            if key not in want or key in seen:
                continue
            seen.add(key)
            e = want[key]
            for f in changed(key, ("n", "note", "added")):
                _put(w, {"n": "count"}.get(f, f), _secs(e.get(f)) if f == "added" else e.get(f))
            items.append(w)
        for key, e in sorted(want.items(), key=lambda kv: (kv[1].get("added") or 0, kv[0])):
            if key not in seen:
                w = {"name": e["name"], "count": e.get("n", 1), "set": e.get("set"), "number": e.get("number"),
                     "note": e.get("note", ""), "added": _secs(e.get("added")), "list": key.split("|", 1)[0]}
                for f in ("lang", "foil"):
                    if f in e:
                        w[f] = e[f]
                items.append(_clean(w))
        doc["items"] = items
    elif kind in ("decks", "binders"):
        doc = doc if doc is not None else {}
        listed = doc.get(kind) or []
        by_id = {x["id"]: x for x in listed}
        fields = [f for f in SCHEMA[kind]["fields"] if f != "pos"]
        out = []
        for key, e in want.items():
            x = by_id.get(key)
            if x is None:
                t = _secs(e.get("created"))
                x = ({"id": key, "cards": [], "created": t, "updated": t} if kind == "decks" else
                     {"id": key, "slots": [None] * (int(e.get("cols") or 3) * int(e.get("rows") or 3) * 2),
                      "created": t, "updated": t})
            for f in changed(key, fields + ["created"]):
                _put(x, f, _secs(e.get(f)) if f == "created" else e.get(f))
            out.append(x)
        order = {x["id"]: i for i, x in enumerate(listed)}
        if kind == "binders":   # the synced position decides; ties by id
            out.sort(key=lambda x: (want[x["id"]].get("pos", 0), x["id"]))
        else:                   # decks: their order here stays, new ones at the end (oldest first)
            out.sort(key=lambda x: (x["id"] not in order, order.get(x["id"], 0), want[x["id"]].get("created") or 0,
                                    x["id"]))
        doc[kind] = out
    elif kind == "deckcards":
        for d in (doc or {}).get("decks") or []:
            pre = f"{d['id']}|"
            rows, seen = [], set()
            for c in d.get("cards") or []:
                key = f"{pre}{c['sid']}|{c.get('board') or 'main'}"
                if int(c.get("count", 0)) <= 0:   # explode skips it (not synced) – it stays as it is
                    rows.append(c)
                elif key in want and key not in seen:
                    seen.add(key)
                    if int(c.get("count", 0)) != want[key]["n"]:
                        c["count"] = want[key]["n"]
                    rows.append(c)
            for key, e in sorted(want.items()):
                if key.startswith(pre) and key not in seen:
                    _deck, sid, board = key.split("|")
                    rows.append({"sid": sid, "board": board, "count": e["n"]})
            if rows or "cards" in d:
                d["cards"] = rows
    elif kind == "binderslots":
        for b in (doc or {}).get("binders") or []:
            pre = f"{b['id']}|"
            slots = list(b.get("slots") or [])
            mine = {int(key[len(pre):]): e for key, e in want.items() if key.startswith(pre)}
            grow = bool(mine) and max(mine) >= len(slots)
            if grow:
                slots += [None] * (max(mine) + 1 - len(slots))
            for i, s in enumerate(slots):
                e = mine.get(i)
                if e is None:
                    slots[i] = None
                elif not s or have.get(f"{pre}{i}") != e:
                    slots[i] = {"sid": e["sid"], "lang": e.get("lang", "en"), "foil": bool(e.get("foil"))}
            if grow:   # whole spreads, like binders._grow
                slots += [None] * (-len(slots) % max(1, int(b.get("cols") or 3) * int(b.get("rows") or 3) * 2))
            if slots or "slots" in b:
                b["slots"] = slots
    elif kind in ("friends", "friendlibs"):
        doc = doc if doc is not None else {}
        fields = SCHEMA[kind].get("fields", []) + [m for _n, ms in SCHEMA[kind].get("groups", []) for m in ms]
        out = {}
        for key in list(doc) + sorted(k for k in want if k not in doc):
            if key in want:
                x = doc.get(key) or {}
                for f in changed(key, fields):
                    _put(x, f, want[key].get(f))
                out[key] = x
        doc = out
    elif kind == "friendnotes":
        old = doc or {}   # an empty note is not synced (explode skips it) – it stays
        doc = {k: want[k]["note"] if k in want else old[k] for k in list(old) + sorted(want)
               if k in want or not old.get(k)}
    elif kind == "friendfolders":
        doc = list(want["me"]["folders"]) if "me" in want else []
    elif kind == "profile":
        if "me" in want:
            doc = doc if doc is not None else {}
            for f in changed("me", ("name", "back", "id")):
                _put(doc, f, want["me"].get(f))
    elif kind == "offers":
        doc = doc if doc is not None else {}
        listed = doc.get("offers") or []
        out, seen = [], set()
        for o in listed:
            if o["id"] in want:
                e = want[o["id"]]
                for f in changed(o["id"], ("status", "partner", "versions", "updated", "created")):
                    v = e.get(f)
                    _put(o, f, json.loads(v) if f == "versions" and v is not None else
                         _secs(v) if f in ("updated", "created") else v)
                out.append(o)
                seen.add(o["id"])
        for key, e in sorted(want.items(), key=lambda kv: (kv[1].get("created") or 0, kv[0])):
            if key not in seen:
                out.append(_clean({"id": key, "partner": e.get("partner") or ["", ""], "status": e.get("status"),
                                   "versions": json.loads(e["versions"]) if e.get("versions") else [],
                                   "created": _secs(e.get("created")), "updated": _secs(e.get("updated"))}))
        doc["offers"] = out
    elif kind == "pending":
        doc = doc if doc is not None else {}
        out, seen = [], set()
        for x in doc.get("pending") or []:
            tid = str((x.get("ticket") or {}).get("id") or "")
            if tid in want:
                out.append(x if not changed(tid, ("doc",)) else json.loads(want[tid]["doc"]))
                seen.add(tid)
        out += [json.loads(e["doc"]) for k, e in sorted(want.items()) if k not in seen]
        doc["pending"] = out
    elif kind == "friendboards":
        doc = doc if doc is not None else {}
        for code, f in doc.items():
            pre = f"{code}|"
            have_b = (f or {}).get("boards") or {}
            mine = {k[len(pre):]: e for k, e in want.items() if k.startswith(pre)}
            boards = {}
            for gs in list(have_b) + sorted(g for g in mine if g not in have_b):
                if gs in mine:
                    b = dict(have_b.get(gs) or {})
                    for fld in changed(pre + gs, ("key", "t", "title", "until", "fetched")):
                        _put(b, fld, mine[gs].get(fld))
                    boards[gs] = b
                elif not (have_b.get(gs) or {}).get("key"):   # explode skipped it (no key yet): stays
                    boards[gs] = have_b[gs]
            if boards or "boards" in (f or {}):
                f["boards"] = boards
    elif kind in ("alarms", "listalarms"):
        keyf = _alarm_key if kind == "alarms" else _list_alarm_key
        old = list(doc or [])
        out, seen = [], set()
        for a in old:
            k = keyf(a)
            if k in want and k not in seen:
                seen.add(k)
                a = dict(a)
                for f in changed(k, SCHEMA[kind]["fields"]):
                    v = want[k].get(f)
                    _put(a, f, v / 100 if isinstance(v, int) and f in ("below", "above", "drop", "rise") else v)
                out.append(a)
        for k in sorted(want):
            if k not in seen:
                parts = k.split("|")
                e = want[k]
                if kind == "alarms":
                    a = {"game": parts[0], "kind": parts[1], "name": parts[2], "set": parts[3] or None,
                         "sid": parts[4] or None, "foil": parts[5] == "1", "psid": parts[6] or None}
                else:
                    a = {"game": parts[0], "lkind": parts[1], "lid": parts[2]}
                for f in SCHEMA[kind]["fields"]:
                    v = e.get(f)
                    _put(a, f, v / 100 if isinstance(v, int) and f in ("below", "above", "drop", "rise") else v)
                out.append(_clean(a))
        doc = out
    elif kind == "devices":
        doc = {k: dict(want[k]) for k in sorted(want)}
    elif kind == "inbox":
        old = list(doc or [])
        out, seen = [], set()
        for m in old:
            mid = str(m.get("id") or "")
            if not mid:
                out.append(m)
            elif mid in want:
                if changed(mid, ("read",)):
                    m = dict(m, read=bool(want[mid].get("read")))
                out.append(m)
                seen.add(mid)
        for k, e in want.items():
            if k not in seen:
                out.append(_clean({"id": k, "t": _secs(e.get("t")), "title": e.get("title", ""),
                                   "text": e.get("text", ""), "via": e.get("via"), "read": bool(e.get("read"))}))
        out.sort(key=lambda m: -(m.get("t") or 0))
        doc = out
    else:
        raise KeyError(kind)
    return doc


def diff_doc(clock, game, kind, old_doc, new_doc):
    """save() hook for a whole document: explode old and new, diff by the schema -> (ops, snap?). create_only fields go
    with the create only; derived/local never. snap True: more than SNAP_OPS ops – send a snap of this kind instead."""
    spec = SCHEMA[kind]
    sync = set(spec.get("fields", [])) | {m for _n, ms in spec.get("groups", []) for m in ms} | set(spec.get("max", []))
    once = set(spec.get("create_only", []))
    old, new = explode(kind, old_doc), explode(kind, new_doc)
    where = "*" if spec.get("global") else game
    ops = diff_ops(clock, f"{where}/{kind}", old, new, fields=sync, create_fields=sync | once)
    return ops, len(ops) > SNAP_OPS


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


def seed_ops(clock, game, kind, doc, state=None):
    """Switching the sync on: what already stands in a document has no ops – without them the first foreign package
    would implode it away (not in the state = deleted). So once, at switching on, this device's documents are
    recorded against what the vault holds. state: this device's State after fetching the vault (None: an empty
    vault, the first device). Per entry of the document:
      - the vault does not have it (unknown, or deleted there) -> a create: nothing local vanishes unasked;
      - the vault has it -> only the difference: changed fields as a change with this device's clock (the later one
        wins, as always), a counter as a delta (here 4, vault 3 -> +1 = 4, never 3 + 4);
      - the same as in the vault -> nothing.
    Entries only in the vault stay untouched (seeding never deletes).
    Counters (lead/ports 03.11.): the delta to the vault AS FETCHED – it says "this device has 4"; what another device
    changes meanwhile refers to the same base and adds up (vault 3, A +2 meanwhile, here 4 -> 6 everywhere).
    Between switching on and this seed nothing is recorded (ports): a change recorded as a delta before the seed
    would be counted again by it – it is in the document, the seed takes it. -> (ops, snap?) like diff_doc."""
    spec = SCHEMA[kind]
    sync = set(spec.get("fields", [])) | {m for _n, ms in spec.get("groups", []) for m in ms} | set(spec.get("max", []))
    c = f"{'*' if spec.get('global') else game}/{kind}"
    local = explode(kind, doc)
    vault = {k: state.value(c, k) for k in local if state.present(c, k)} if state is not None else {}
    vault = {k: {f: v for f, v in e.items() if v is not None} for k, e in vault.items()}
    old = {k: vault[k] for k in local if k in vault}
    ops = diff_ops(clock, c, old, {k: dict(e) for k, e in local.items()}, fields=sync,
                   create_fields=sync | set(spec.get("create_only", [])))
    return ops, len(ops) > SNAP_OPS


def diff_ops(clock, kind, old, new, fields=None, create_fields=None):
    """The save() hook: two states of one document ({key: {field: value}}) -> the ops that lead from old to new.
    New entries -> a create with all fields; gone ones -> a delete (counted: with the count seen); changed fields ->
    one op per entry with the changed fields (a group whole); counters -> a delta (new − old), never an overwrite.
    fields: the synced fields (None = all) – derived ones (names, images, prices) stay out. create_fields: what a
    create carries (default: fields) – e.g. "created", sent once and never changed."""
    cf = COUNTED.get(_base(kind))
    out = []

    def pick(e, keep=fields):
        return {k: v for k, v in e.items() if (keep is None or k in keep) and k != cf}

    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        if a is None:
            d = {cf: int(b.get(cf, 0))} if cf else None
            out.append(op(clock, kind, key, s=pick(b, create_fields if create_fields is not None else fields), d=d,
                          create=True))
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


# ---------- What goes into the vault (SYNC-PLAN §3, ports/performance 03.11.2026) ----------
# The plaintext of one vault package, before vault_seal: zlib(UTF-8 of canonical(obj)) – sealed data no longer
# compresses. Two types, "t" inside the sealed content too (nobody can relabel an add as a snap from outside):
#   add   {"v":1,"t":"add","dev","ops":[own ops, ascending h],"top":{dev:h},"sum":{kind:sha256}}
#         ops: only the sender's OWN ops (State.covered() relies on one device's ops arriving in order). top/sum only
#         in the last part of a split add: the sender's State.top and State.sum(kind) of the kinds it touched, after
#         its ops. A receiver compares the sums only when its own top is EXACTLY that top afterwards (the same ops
#         seen) – otherwise (concurrent ops, own unsent ones) there is nothing to compare, never a false alarm.
#   snap  {"v":1,"t":"snap","dev","kinds","top","sum":{every kind}[,"takeover":{"dev","at"}]} – kinds/top =
#         State.to_snap() after compact() and purge() (an entry not there: no fields, a counter only net).
PACK_V = 1
ADD_MAX = 1_000_000          # bytes of one packed add (before sealing); more ops -> several adds in a row
UNPACK_MAX = 64_000_000      # unpacked bytes at most (a broken or hostile package never fills the memory)


class PackError(ValueError):
    """A package this version cannot read: damaged, or "newer" (a newer format – update the app)."""

    def __init__(self, msg, newer=False):
        super().__init__(msg)
        self.newer = newer


def pack(obj):
    return zlib.compress(canonical(obj).encode("utf-8"), 9)


def unpack(data):
    """Packed bytes (after vault_open) -> the package. PackError if damaged, too big or of an unknown version/type."""
    z = zlib.decompressobj()
    try:
        raw = z.decompress(data, UNPACK_MAX)
    except zlib.error as e:
        raise PackError(f"not a package: {e}") from None
    if z.unconsumed_tail or not z.eof:
        raise PackError("package too big or cut off")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except ValueError as e:
        raise PackError(f"not a package: {e}") from None
    if not isinstance(obj, dict) or obj.get("v") != PACK_V:
        raise PackError(f"package version {obj.get('v') if isinstance(obj, dict) else '?'}", newer=True)
    if obj.get("t") not in ("add", "snap"):
        raise PackError(f"package type {obj.get('t')}", newer=True)
    return obj


def add_packages(dev, ops, state, limit=ADD_MAX):
    """This device's new ops -> the add packages (packed bytes, in order; one put each). state: this device's
    State with these ops already applied. Several parts only when one would be bigger than limit."""
    ops = sorted(ops, key=lambda o: _hkey(o["h"]))
    for o in ops:
        if o["h"][2] != dev:
            raise ValueError(f"not an own op: {o['o']}")
        if o["o"] not in state.ids:
            raise ValueError(f"op not applied yet: {o['o']}")
    last = {"top": {d: list(h) for d, h in state.top.items()},
            "sum": {k: state.sum(k) for k in sorted({o["c"] for o in ops})}}

    def build(part, is_last):
        obj = {"v": PACK_V, "t": "add", "dev": dev, "ops": part}
        return pack({**obj, **last} if is_last else obj)

    out, todo = [], [ops]
    while todo:   # halve a part until it fits (order kept); one op always goes alone
        part = todo.pop(0)
        data = build(part, not todo)
        if len(data) > limit and len(part) > 1:
            todo[:0] = [part[:len(part) // 2], part[len(part) // 2:]]
            continue
        out.append(data)
    return out


def check_add(state, pkg):
    """After applying an add (and everything before it): True – the same as the sender, False – the same ops but a
    different result (heal: §3.4), None – not comparable (an earlier part, or this device has seen other ops)."""
    if "top" not in pkg:
        return None
    if {d: _hkey(h) for d, h in state.top.items()} != {d: _hkey(h) for d, h in pkg["top"].items()}:
        return None
    return all(state.sum(k) == s for k, s in pkg["sum"].items())


def snap_package(dev, state, now_ms, takeover=None):
    """The whole state as one snap (a copy, compacted: tombstones older than TOMB_DAYS go; purged: no values of
    entries that are not there). takeover: {"dev", "at"} when this snap is „keep this device's data“ – otherwise
    the state's last takeover goes on (SYNC-LOGS §4: every later snap carries it)."""
    st = State.from_snap(json.loads(json.dumps(state.to_snap())))
    st.compact(now_ms)
    st.purge()
    if takeover:
        st.takeover = {"dev": str(takeover["dev"]), "at": int(takeover["at"])}
        if takeover.get("device") in ("pc", "phone"):   # which kind of device took over (the text names it)
            st.takeover["device"] = takeover["device"]
    snap = st.to_snap()
    obj = {"v": PACK_V, "t": "snap", "dev": dev, "kinds": snap["kinds"], "top": snap["top"],
           "sum": {k: st.sum(k) for k in sorted(st.kinds)}}
    if st.takeover:
        obj["takeover"] = st.takeover
    return pack(obj)


def load_snap(pkg):
    """A snap package -> its State; PackError if a checksum does not match (then it is not taken)."""
    st = State.from_snap(pkg)
    bad = [k for k, s in (pkg.get("sum") or {}).items() if st.sum(k) != s]
    if bad:
        raise PackError(f"snap checksum differs: {bad}")
    return st
