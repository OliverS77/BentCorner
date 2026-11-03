"""The library as the sum of all logs (docs/SYNC-PLAN.md §3b, Oliver 29.10.: the logs are the source).

Every copy in the collection must come from a log line:
  - a scan / import / trade-in log (sessions.py, collection not False): each card entry is one copy, keyed by its
    "src" (<session-id>/<repr(added)>) – exactly as Collection.sync_session takes it over;
  - a change by hand (manual.py, the day's "Manual" log, and the one-off migration log): "delta" on a collection
    entry (+ added, - taken out);
  - a trade booking (bookings.py): "taken" copies leave the collection.
A log counts once it has ended (its cards come into the library then – the running one doesn't count yet). A log card
that had already left the library without a line (the old way, before .102) is in a "By hand" log's "gone" list: it
counts 0 – so the migration never needs a line with minus copies.
count(key) = copies from logs + all deltas on that key − all taken. key = src for log cards, "uid:<uid>" for cards
added by hand. This module only computes and compares – it changes nothing. (Field changes – condition, language …
– follow in their log entry; here only the copies count.)
"""


def _key(item):
    return item.get("src") or "uid:" + str(item.get("uid"))


def expected(items, logs, bookings):
    """-> {key: copies} from the logs. items: the collection entries now (to know which key a uid has – a delta on a
    scanned card counts on its src); logs: all session dicts (hidden ones too); bookings: bookings.load()."""
    by_uid = {it.get("uid"): _key(it) for it in items}
    gone = {k for d in logs if (d.get("info") or {}).get("kind") == "manual" for k in d.get("gone") or ()}
    out = {}

    def add(key, n):
        out[key] = out.get(key, 0) + n

    def key_of_uid(uid, snapshot=None, src=None):
        if uid in by_uid:
            return by_uid[uid]
        if src:        # the line says which log card it changed
            return src
        if snapshot:   # the entry is gone (taken out): its saved state says where it came from
            return _key(snapshot)
        return "uid:" + str(uid)

    for d in logs:
        info = d.get("info") or {}
        if info.get("kind") == "manual":
            for pk in d.get("packs") or []:
                for ln in pk.get("cards") or []:
                    if ln.get("uid") and ln.get("delta"):
                        add(key_of_uid(ln["uid"], ln.get("item"), ln.get("src")), int(ln["delta"]))
            continue
        if d.get("collection") is False or not d.get("ended"):   # = sync_session: a log's cards come when it ends
            continue
        prefix = d["id"] + "/"
        for pk in d.get("packs") or []:
            for e in pk.get("cards") or []:
                k = prefix + repr(e.get("added", 0))
                if not e.get("out") and k not in gone:
                    add(k, 1)
    for b in bookings:
        for tk in b.get("taken") or []:
            add(key_of_uid(tk.get("uid"), tk.get("item")), -int(tk.get("n") or 0))
    return out


def actual(items):
    """-> {key: copies} in the collection now."""
    out = {}
    for it in items:
        k = _key(it)
        out[k] = out.get(k, 0) + int(it.get("count", 1))
    return out


def diff(items, logs, bookings):
    """-> {key: (from logs, in the collection)} where they differ (0 = none). Empty = the library is exactly the sum
    of its logs."""
    want, have = expected(items, logs, bookings), actual(items)
    return {k: (max(0, want.get(k, 0)), have.get(k, 0)) for k in set(want) | set(have)
            if max(0, want.get(k, 0)) != have.get(k, 0)}


# ---------- the one-off migration: what the logs can't explain yet becomes one "By hand" log ----------
MIGRATION_PREFIX = "manual_migrated_"


def migration(items, logs, bookings, when, card_of=None):
    """-> a log of kind "manual" whose lines make the library exactly the sum of its logs (or None: nothing to do).
    Plus lines: for copies that came by hand before every change was written down or from logs deleted with "keep
    cards". A log card that left without a line (the old "hidden") goes into the log's "gone" list instead (expected
    counts it 0) – never a minus line for those (.102: a minus migration log looked like a loss).
    A minus on a copy added by hand (uid key: its lines say more than the library has – "+1 by hand" taken back with
    Undo) is a minus line with the card as its newest line by hand had it (03.11.2026: skipping it left a gap of
    1 and a warning at every logs check). card_of is kept for callers (no longer needed)."""
    from collection.collection import CARD_KEYS, price
    from cards import conditions
    gap = diff(items, logs, bookings)
    if not gap:
        return None
    by_key = {}
    for it in items:
        by_key.setdefault(_key(it), it)
    last = {}   # uid -> its newest line by hand (the card as it was, for a minus line when the copy is gone)
    for d in logs:
        if (d.get("info") or {}).get("kind") == "manual":
            for pk in d.get("packs") or []:
                for ln in pk.get("cards") or []:
                    u = ln.get("uid")
                    if u and (str(u) not in last or (ln.get("added") or 0) >= (last[str(u)].get("added") or 0)):
                        last[str(u)] = ln
    lines, gone, t = [], [], when
    for k in sorted(gap):
        want, have = gap[k]
        delta = have - want
        it = by_key.get(k)
        if delta < 0 and not k.startswith("uid:"):
            gone.append(k)   # a log card no longer (or less often) in the library
            continue
        src = it if it is not None else last.get(k[4:])
        if src is None:   # a uid no line knows (can't happen: its want came from a line)
            continue
        line = {kk: src.get(kk) for kk in CARD_KEYS}
        line.update(lang=src.get("lang") or "en", foil=bool(src.get("foil")), delta=delta,
                    uid=it["uid"] if it is not None else src["uid"],
                    price=price(it) if it is not None else src.get("price"), added=t, migrated=True)
        from collection.manual import copy_variant
        copy_variant(src, line)
        line.update(conditions.fields(src) or {"cond": src.get("cond") or conditions.DEFAULT})
        lines.append(line)
        t += 1e-6
    if not lines and not gone:
        return None
    sid = MIGRATION_PREFIX + __import__("time").strftime("%Y-%m-%d", __import__("time").localtime(when))
    d = {"id": sid, "started": when - 1, "ended": when, "collection": False,
         "info": {"kind": "manual", "title": "", "migrated": when, "active": False},
         "packs": [{"opened": when, "type": "manual", "cards": lines}]}
    if gone:
        d["gone"] = gone
    return d


def hand_items(logs, bookings, have_uids=()):
    """Rebuild the copies added by hand from the "By hand" lines (collection.json lost): [entry] – those with a uid
    not in have_uids. The lines carry the card as it was, so the entry comes back as it was (count = sum of its
    deltas minus what trades took)."""
    from collection.collection import CARD_KEYS
    acc, card = {}, {}
    for d in logs:
        if (d.get("info") or {}).get("kind") != "manual":
            continue
        for pk in d.get("packs") or []:
            for ln in pk.get("cards") or []:
                uid = ln.get("uid")
                if not uid or not ln.get("delta") or str(uid).startswith("gone:"):
                    continue
                snap = ln.get("item") or {}
                if ln.get("src") or snap.get("src"):   # a scanned card changed by hand: it lives through its log
                    continue
                acc[uid] = acc.get(uid, 0) + int(ln["delta"])
                if uid not in card or ln.get("delta", 0) > 0:
                    card[uid] = ln
    for b in bookings:
        for tk in b.get("taken") or []:
            if tk.get("uid") in acc:
                acc[tk["uid"]] -= int(tk.get("n") or 0)
    out = []
    for uid, n in acc.items():
        if n <= 0 or uid in have_uids:
            continue
        ln = card[uid]
        it = {k: ln.get(k) for k in CARD_KEYS}
        for k in ("lang", "foil", "finish", "edition", "cond", "grade_by", "grade", "cond_note"):
            if ln.get(k) is not None:
                it[k] = ln[k]
        it.update(uid=uid, count=n, added=ln.get("added"), src=None)
        out.append(it)
    return out


def repair(coll, logs, bookings):
    """collection.json was lost and sync_session has put the log cards back (one copy each): bring every count to
    the sum of the logs – changes by hand on log cards, trades – and add the copies that came by hand. -> number of
    entries changed. (Normal operation never needs this: there the collection and its logs move together.)"""
    want = expected(coll.items, logs, bookings)
    n = 0
    with coll.lock:
        keep = []
        for it in coll.items:
            w = want.get(_key(it))
            if w is None or w == int(it.get("count", 1)):
                keep.append(it)
                continue
            n += 1
            if w > 0:
                it["count"] = w
                keep.append(it)
            elif it.get("src"):
                coll.hidden.add(it["src"])
        have = {it["uid"] for it in keep}
        for it in hand_items(logs, bookings, have):
            keep.append(it)
            n += 1
        coll.items = keep
        coll.rev += 1
    return n
