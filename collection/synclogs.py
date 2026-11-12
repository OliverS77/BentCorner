"""The collection in the sync: the logs are the source (docs/web/SYNC-LOGS.md, SYNC-PLAN §3b) – the pure core, no files.

The library itself is never synced. What travels are the logs (scans, imports, „By hand“, trades), the trade bookings
and the trade marks; every device computes the library from them with the same rules as collection/logsum.py (copies)
and collection/shadow.py (fields per copy). The web app has the same rules in JS; both are checked against
docs/web/synclog-vectors.json (tools/make_synclog_vectors.py).

Four kinds of entries (syncops: last writer wins per field, a removed entry is a tombstone):
  logs        <log id>                 the log's head: kind, title, started, ended, collection, hidden, info, packs
  logrows     <log id>|<added µs>      one card of a log, or one line „By hand“
              <log id>|gone|<lib key>  a log card that left without a line (the „gone“ list of a „By hand“ log)
  bookings    <booking id>             a trade booking: when, what it took (lib key + copies), the booking itself
  trademarks  <lib key>                copies marked for trading (the entry's "trade"), only while > 0

Library keys: a log card is its row key "<log>|<added µs>" (on the desktop: src "<log>/<repr(added)>"); a copy added
by hand is "uid:<uid>". Times are whole numbers (no floats in the checksum): µs/ms = floor(t × 10⁶ / 10³ + 0.5) – the
same IEEE steps in Python and JS (Python's round() rounds .5 to even, JS's Math.round up: never use them here).
Prices are whole cents. What only one side reads back as a whole (a log's info, a booking, the entry a removal
saved) travels as a JSON text – carried as it is, never re-encoded, so it needs no common float format.
"""
import hashlib
import json
import math

from collection import syncops

CARD = ("id", "name", "set", "number", "lang", "foil", "finish", "edition", "cond", "grade_by", "grade", "cond_note",
        "from_print")
SYNC_FIELDS = ("id", "lang", "foil", "finish", "edition", "cond", "grade_by", "grade", "cond_note")  # = shadow
LOCAL_INFO = ("active",)       # the running log on this device – never synced
KINDS = ("logs", "logrows", "bookings", "trademarks")


def us(t):
    return int(math.floor(float(t) * 1e6 + 0.5))


def ms(t):
    return int(math.floor(float(t) * 1e3 + 0.5)) if t not in (None, "") else None


def cents(x):
    return int(math.floor(float(x) * 100 + 0.5)) if x not in (None, "") else None


def text(obj):
    """A JSON text of a whole object (floats allowed – it is carried, never compared field by field)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def row_key(sid, added):
    return f"{sid}|{us(added)}"


def key_of_src(src):
    """Desktop src "<log>/<repr(added)>" -> the library key "<log>|<added µs>" (None stays None)."""
    if not src:
        return None
    sid, _, added = str(src).rpartition("/")
    try:
        return row_key(sid, float(added))
    except ValueError:
        return None


def lib_key(item):
    """A collection entry -> its library key (logsum._key in the synced form)."""
    return key_of_src(item.get("src")) or "uid:" + str(item.get("uid"))


def log_kind(d):
    info = d.get("info") or {}
    if info.get("kind") == "manual":
        return "manual"
    if info.get("import"):
        return "import"
    return info.get("kind") or "packs"


def _clean(e):
    return {k: v for k, v in e.items() if v is not None}


def _card(e):
    out = {k: e.get(k) for k in CARD if e.get(k) not in (None, "")}
    out["lang"] = e.get("lang") or "en"
    out["foil"] = bool(e.get("foil"))
    return out


def _plain(v):
    """An edit's before/after value without floats (fields are text/bools; a stray number goes as text)."""
    return str(v) if isinstance(v, float) else v


def explode(logs, bookings, items=()):
    """The stored documents -> {kind: {key: entry}} with only synced fields.
    logs: all session dicts (hidden too); bookings: bookings.load(); items: the collection now – for the trade marks
    and to resolve the key of an old „By hand“ line that names neither src nor its entry (logsum.key_of_uid)."""
    by_uid = {it.get("uid"): lib_key(it) for it in items}
    out = {k: {} for k in KINDS}
    for d in logs:
        sid, kind = d["id"], log_kind(d)
        info = {k: v for k, v in (d.get("info") or {}).items() if k not in LOCAL_INFO}
        hid = d.get("hidden")
        out["logs"][sid] = _clean({
            "kind": kind, "title": (d.get("info") or {}).get("title") or "", "started": ms(d.get("started")),
            "ended": ms(d.get("ended")), "collection": d.get("collection") is not False,
            "hidden": {"at": ms(hid.get("at")), "kept": bool(hid.get("kept"))} if isinstance(hid, dict) else None,
            "info": text(info),
            "packs": [[ms(p.get("opened")), p.get("type") or ""] for p in d.get("packs") or []]})
        for pi, p in enumerate(d.get("packs") or []):
            for e in p.get("cards") or []:
                r = _card(e)
                if e.get("price") is not None:
                    r["price"] = cents(e["price"])
                if kind == "manual":
                    if e.get("uid") is not None:
                        r["uid"] = str(e["uid"])
                    r["delta"] = int(e.get("delta") or 0)
                    snap = e.get("item") or None
                    uid = e.get("uid")
                    r["key"] = (by_uid.get(uid) or key_of_src(e.get("src")) or (lib_key(snap) if snap else None)
                                or "uid:" + str(uid))
                    if e.get("src"):
                        r["src"] = key_of_src(e["src"])
                    if snap:
                        r["item"] = text(snap)
                    if e.get("edit"):
                        r["edit"] = {k: [_plain(v[0]), _plain(v[1])] for k, v in e["edit"].items()}
                    if e.get("why"):
                        r["why"] = e["why"]
                else:
                    r["pack"] = pi
                    if e.get("out"):
                        r["out"] = True
                out["logrows"][row_key(sid, e.get("added", 0))] = r
        if kind == "manual":
            for src in d.get("gone") or ():
                k = key_of_src(src) or str(src)
                out["logrows"][f"{sid}|gone|{k}"] = {"gone": True}
    for b in bookings:
        out["bookings"][b["id"]] = {
            "t": ms(b.get("t")),
            "taken": [[by_uid.get(tk.get("uid")) or (lib_key(tk["item"]) if tk.get("item") else
                                                     "uid:" + str(tk.get("uid"))), int(tk.get("n") or 0)]
                      for tk in b.get("taken") or []],
            "doc": text(b)}
    for it in items:
        n = int(it.get("trade") or 0)
        if n > 0:
            k = lib_key(it)
            out["trademarks"][k] = {"n": out["trademarks"].get(k, {}).get("n", 0) + n}
    return out


def _norm(k, v):
    if k == "lang":
        return v or "en"
    if k == "foil":
        return bool(v)
    if k == "cond":
        return v or "near_mint"
    return v or None


def fields_of(e):
    return {k: _norm(k, e.get(k)) for k in SYNC_FIELDS}


def expected(view):
    """-> {lib key: copies} (logsum.expected on the synced form; zero and below included)."""
    return _compute(view)[0]


def library(view):
    """-> {lib key: fields + "count" (+ "trade")} for every key with copies (shadow.rebuild on the synced form).
    view: {kind: {key: entry}} – State.view of each kind, or explode()."""
    counts, fields = _compute(view)
    marks = view.get("trademarks") or {}
    res = {}
    for k, n in counts.items():
        if n > 0:
            res[k] = dict(fields.get(k) or {}, count=n)
            t = int((marks.get(k) or {}).get("n") or 0)
            if t > 0:
                res[k]["trade"] = min(t, n)
    return res


def _compute(view):
    logs, rows = view.get("logs") or {}, view.get("logrows") or {}
    gone = set()
    for k, r in rows.items():
        sid, _, rest = k.partition("|")
        if r.get("gone") and (logs.get(sid) or {}).get("kind") == "manual" and rest.startswith("gone|"):
            gone.add(rest[5:])
    counts, fields, hand = {}, {}, []
    for k in sorted(rows):
        r = rows[k]
        sid, _, rest = k.partition("|")
        lg = logs.get(sid)
        if lg is None or r.get("gone") or rest.startswith("gone|"):
            continue
        if lg.get("kind") == "manual":
            hand.append((int(rest), k, r))
            continue
        if lg.get("collection") is False or lg.get("ended") is None or r.get("out") or k in gone:
            continue
        counts[k] = counts.get(k, 0) + 1
        fields[k] = fields_of(r)
    hand.sort(key=lambda x: (x[0], x[1]))
    for _t, _k, r in hand:
        if not r.get("uid"):
            continue
        key, delta = r.get("key") or "uid:" + r["uid"], int(r.get("delta") or 0)
        if delta:
            counts[key] = counts.get(key, 0) + delta
        if key.startswith("uid:") and delta > 0:
            fields[key] = fields_of(r)
        if r.get("edit"):
            f = fields.setdefault(key, fields_of(r))
            for fk, ba in r["edit"].items():
                if fk in SYNC_FIELDS:
                    f[fk] = _norm(fk, ba[1])
    for b in (view.get("bookings") or {}).values():
        for key, n in b.get("taken") or []:
            counts[key] = counts.get(key, 0) - int(n)
    return counts, fields


def free_added(cards, t):
    """A new line's "added": t, moved on by 1 µs while another line of the log has the same µs (its row key must be
    unique – a float step of 1e-6 alone can land in the same µs, 29.10. migration log)."""
    taken = {us(c.get("added", 0)) for c in cards}
    while us(t) in taken:
        t = (us(t) + 1) / 1e6
    return t


def spread(logs, items=(), hidden=None, bookings=()):
    """Switching the sync on (once): lines of one log that share a µs (written before free_added) get their own – each
    later one moves to the next free µs. Every reference moves along: collection src, hidden, the "gone" lists, the
    src of lines „By hand“ and of the entries they saved, the entries bookings took. Changes the given objects in
    place. -> the ids of the logs that changed (the caller saves them, the collection and the bookings)."""
    moved, changed = {}, []
    for d in logs:
        cards = sorted((e for p in d.get("packs") or [] for e in p.get("cards") or []),
                       key=lambda e: float(e.get("added", 0)))
        last = None
        for e in cards:
            u = us(e.get("added", 0))
            if last is not None and u <= last:
                old = e.get("added", 0)
                e["added"] = (last + 1) / 1e6
                while us(e["added"]) <= last:
                    e["added"] += 1e-7
                moved[f"{d['id']}/{old!r}"] = f"{d['id']}/{e['added']!r}"
                if d["id"] not in changed:
                    changed.append(d["id"])
                u = us(e["added"])
            last = u
    if not moved:
        return changed

    def fix(obj, field="src"):
        if isinstance(obj, dict) and obj.get(field) in moved:
            obj[field] = moved[obj[field]]
            return True
        return False

    for it in items:
        fix(it)
    if hidden is not None:
        for s in [s for s in hidden if s in moved]:
            hidden.discard(s)
            hidden.add(moved[s])
    for d in logs:
        hit = False
        if d.get("gone"):
            new = [moved.get(s, s) for s in d["gone"]]
            hit = new != d["gone"]
            d["gone"] = new
        for p in d.get("packs") or []:
            for e in p.get("cards") or []:
                hit = fix(e) | fix(e.get("item")) | hit
        if hit and d["id"] not in changed:
            changed.append(d["id"])
    for b in bookings:
        for tk in b.get("taken") or []:
            fix(tk.get("item"))
    return changed


# ---------- the desktop's side: log ids, writing back, the collection recomputed ----------
TEXTS = ("info", "doc", "item")


def _parsed(x):
    """An entry (or {key: entry}) with its JSON texts read – for comparing contents: Python writes 1793600000.0 where
    JS writes 1793600000 (ports 07.11.); the same content must not be written back again and again."""
    if isinstance(x, dict):
        return {k: (json.loads(v) if k in TEXTS and isinstance(v, str) else _parsed(v)) for k, v in x.items()}
    return x


def same(a, b):
    return a == b or _parsed(a) == _parsed(b)


SUFFIX = [""]      # "_<dev>" while the sync is on (syncrun sets it): new logs get it – ids unique per device


def new_id(base):
    """A new log's id: base ("2026-11-07_10-00-00", "import_…", "manual_2026-11-07" …) + this device's suffix while
    the sync is on (SYNC-LOGS §2) – without the sync exactly as before."""
    return base + SUFFIX[0]


def _src_map(logs):
    """{lib key: desktop src} of every log card here – this device's own spelling of each card's added."""
    return {row_key(d["id"], e.get("added", 0)): f"{d['id']}/{e.get('added', 0)!r}"
            for d in logs for p in d.get("packs") or [] for e in p.get("cards") or []}


def src_of(key, srcs):
    """lib key -> desktop src (this device's spelling if the card is here, else from the µs)."""
    if not key or key.startswith("uid:"):
        return None
    if key in srcs:
        return srcs[key]
    sid, _, u = key.rpartition("|")
    return f"{sid}/{int(u) / 1e6!r}"


def _fix_src(obj, srcs):
    if isinstance(obj, dict) and obj.get("src"):
        obj["src"] = src_of(key_of_src(obj["src"]), srcs) or obj["src"]
    return obj


def implode(logs, bookings, items, view, card_of=None, skip=()):
    """The merged entries written back into this device's documents. Only what differs changes: a log whose head and
    rows are the same is not touched; a card here keeps its own added, prices, images. skip: log ids not to touch
    (this device's running log – it is written by the scanner).
    card_of(id) -> the card's data from the card database (rarity, images …; None: unknown) for cards new here.
    -> (changed {log id: document}, deleted [log id], bookings list or None if unchanged)"""
    import copy
    local = explode(logs, bookings, items)
    by_id = {d["id"]: d for d in logs}
    srcs = _src_map(logs)
    rows_by_log = {}
    for k, r in view.get("logrows", {}).items():
        rows_by_log.setdefault(k.partition("|")[0], {})[k] = r
    for k in view.get("logrows", {}):   # cards new here: their src from the µs
        srcs.setdefault(k, src_of(k, {}))
    lrows = {}
    for k, r in local["logrows"].items():
        lrows.setdefault(k.partition("|")[0], {})[k] = r
    changed, deleted = {}, []
    for sid in sorted(set(by_id) | set(view.get("logs", {}))):
        if sid in skip:
            continue
        head = view.get("logs", {}).get(sid)
        if head is None:
            if sid in by_id:
                deleted.append(sid)
            continue
        rows = rows_by_log.get(sid, {})
        if same(local["logs"].get(sid), head) and same(lrows.get(sid, {}), rows):
            continue
        old = by_id.get(sid)
        d = copy.deepcopy(old) if old else {"id": sid}
        info = json.loads(head.get("info") or "{}")
        for k in LOCAL_INFO:
            if k in (d.get("info") or {}):
                info[k] = d["info"][k]
            elif k == "active":
                info[k] = False
        d.update(started=(head.get("started") or 0) / 1e3, ended=head["ended"] / 1e3 if head.get("ended") else None,
                 collection=bool(head.get("collection", True)), info=info)
        if head.get("hidden"):
            d["hidden"] = {"at": head["hidden"]["at"] / 1e3, "kept": bool(head["hidden"].get("kept"))}
        else:
            d.pop("hidden", None)
        here = {row_key(sid, e.get("added", 0)): e for p in (old or {}).get("packs") or [] for e in p.get("cards") or []}
        packs = [{"opened": o / 1e3 if o is not None else None, "type": t or None} for o, t in head.get("packs") or []]
        if not packs:
            packs = [{"opened": d["started"], "type": None}]
        for p in packs:
            p["cards"] = []
        gone = []
        mine = lrows.get(sid, {})
        for k in sorted(rows, key=lambda k: (k.count("|"), k)):
            r = rows[k]
            if r.get("gone"):
                gone.append(src_of(k.split("|", 2)[2], srcs) or k.split("|", 2)[2])
                continue
            e = dict(here[k]) if k in here else None
            if e is None:
                e = {"added": int(k.rpartition("|")[2]) / 1e6}
                c = card_of(r.get("id")) if card_of and r.get("id") else None
                for f in ("rarity", "finishes", "booster", "eur", "eur_foil", "img", "url"):
                    if c and c.get(f) is not None:
                        e[f] = c[f]
            if not same(mine.get(k), r):
                for f in CARD + ("uid", "delta", "why", "out"):
                    if f in r:
                        e[f] = r[f]
                    else:
                        e.pop(f, None)
                e["lang"], e["foil"] = r.get("lang") or "en", bool(r.get("foil"))
                e["price"] = r["price"] / 100 if r.get("price") is not None else None   # every card has it (stats)
                if "src" in r:
                    e["src"] = src_of(r["src"], srcs)
                else:
                    e.pop("src", None)
                if r.get("item"):
                    e["item"] = _fix_src(json.loads(r["item"]), srcs)
                else:
                    e.pop("item", None)
                if r.get("edit"):
                    e["edit"] = {f: list(v) for f, v in r["edit"].items()}
                else:
                    e.pop("edit", None)
            pi = int(r.get("pack") or 0)
            while pi >= len(packs):
                packs.append({"opened": e["added"], "type": None, "cards": []})
            packs[pi]["cards"].append(e)
        for p in packs:
            p["cards"].sort(key=lambda e: float(e.get("added", 0)))
        d["packs"] = packs
        if gone:
            d["gone"] = gone
        else:
            d.pop("gone", None)
        changed[sid] = d
    new_book = None
    if not same(local["bookings"], view.get("bookings", {})):
        new_book = []
        for _bid, b in sorted(view.get("bookings", {}).items(), key=lambda kv: (kv[1].get("t") or 0, kv[0])):
            doc = json.loads(b["doc"])
            for tk in doc.get("taken") or []:
                _fix_src(tk.get("item"), srcs)
            new_book.append(doc)
    return changed, deleted, new_book


def reconcile(items, hidden, lib, view, logs, card_of=None):
    """The collection recomputed from the library (after foreign changes came in): counts, the synced fields and the
    trade marks set; copies only the library has are made (from their log card or newest line by hand); copies the
    library no longer has go (a log card's src into hidden, so Collection.sync_session doesn't bring it back).
    items/hidden are changed in place. -> number of entries changed."""
    import uuid
    srcs = _src_map(logs)
    by_key = {}
    for it in items:
        by_key.setdefault(lib_key(it), []).append(it)
    n = 0
    keep = []
    for k, its in by_key.items():
        want = lib.get(k)
        if want is None:
            n += len(its)
            for it in its:
                if it.get("src"):
                    hidden.add(it["src"])
            continue
        first = its[0]
        if len(its) > 1:
            n += len(its) - 1
        upd = {f: want[f] for f in SYNC_FIELDS if fields_of(first).get(f) != want[f]}
        if int(first.get("count", 1)) != want["count"]:
            upd["count"] = want["count"]
        if int(first.get("trade") or 0) != int(want.get("trade") or 0):
            upd["trade"] = int(want.get("trade") or 0)
        if upd:
            first.update(upd)
            n += 1
        keep.append(first)
    rows = view.get("logrows", {})
    hand = {}
    for rk, r in sorted(rows.items(), key=lambda kv: kv[0]):
        if r.get("uid") and r.get("key", "").startswith("uid:") and int(r.get("delta") or 0) > 0:
            hand[r["key"]] = (rk, r)
    for k, want in sorted(lib.items()):
        if k in by_key:
            continue
        src = None if k.startswith("uid:") else src_of(k, srcs)
        rk, r = (k, rows.get(k)) if src else hand.get(k, (None, None))
        if r is None:
            continue
        c = (card_of(r.get("id")) if card_of and r.get("id") else None) or {}
        it = {f: c.get(f) for f in ("rarity", "finishes", "booster", "eur", "eur_foil", "img", "url")}
        it.update({f: r.get(f) for f in ("id", "name", "set", "number")})
        it.update({f: v for f, v in want.items() if f in SYNC_FIELDS and v is not None})
        it.update(uid=k[4:] if k.startswith("uid:") else uuid.uuid4().hex[:12], count=want["count"],
                  added=int(rk.rpartition("|")[2]) / 1e6,
                  src=src)
        if want.get("trade"):
            it["trade"] = want["trade"]
        if src and r.get("pack") is not None:
            it["pack"] = int(r["pack"]) + 1
        if src:
            hidden.discard(src)
        keep.append(it)
        n += 1
    items[:] = keep
    return n


def rename_log(logs, items, hidden, bookings, old, new):
    """A log gets a new id (manual_… -> manual_…_<dev> once at switching on; a scan log whose id the vault already has
    from another device). Every reference moves along like in spread(). Changes the given objects in place."""
    pre = old + "/"

    def move(s):
        return new + "/" + s[len(pre):] if isinstance(s, str) and s.startswith(pre) else s

    def fix(obj):
        if isinstance(obj, dict) and obj.get("src"):
            obj["src"] = move(obj["src"])

    for d in logs:
        if d["id"] == old:
            d["id"] = new
        if d.get("gone"):
            d["gone"] = [move(s) for s in d["gone"]]
        for p in d.get("packs") or []:
            for e in p.get("cards") or []:
                fix(e)
                fix(e.get("item"))
    for it in items:
        fix(it)
        if it.get("from_session") == old:
            it["from_session"] = new
    if hidden is not None:
        for s in [s for s in hidden if s.startswith(pre)]:
            hidden.discard(s)
            hidden.add(move(s))
    for b in bookings:
        if b.get("session") == old:
            b["session"] = new
        for tk in b.get("taken") or []:
            fix(tk.get("item"))


def checksum(lib):
    return hashlib.sha256(syncops.canonical(lib).encode("utf-8")).hexdigest()


def items_now(items):
    """The collection now in the same form (shadow.actual in the synced form) – compared with library()."""
    out = {}
    for it in items:
        k = lib_key(it)
        if k in out:
            out[k]["count"] += int(it.get("count", 1))
        else:
            out[k] = dict(fields_of(it), count=int(it.get("count", 1)))
        t = int(it.get("trade") or 0)
        if t > 0:
            out[k]["trade"] = min(out[k].get("trade", 0) + t, out[k]["count"])
    return out
