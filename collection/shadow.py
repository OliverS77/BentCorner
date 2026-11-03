"""The library rebuilt from the logs alone – copies and the fields the sync carries (docs/SYNC-PLAN.md §3, §3b).

logsum.py checks the copies; for the sync a device that only has the logs must also know each copy's language,
finish, condition … This module rebuilds that and compares it with collection.json. It only reads (a folder given as
an argument, never the module paths), so it can run on a copy of real data: the shadow run before the logs lead.

Rebuilt per key (logsum._key: src for log cards, "uid:<uid>" for cards added by hand):
  - a log card (log ended, collection not False, not "out", not in a "gone" list): the card entry as it is in its
    log now (a change of language/condition … is written into the log card, scanner.core.set_card);
  - a "By hand" line: delta on the key; the fields of the newest line on that uid (its card as it was then), an
    "edit" line's after-values on top;
  - a trade booking: "taken" copies off.
"""
import json
import pathlib

from collection import logsum

SYNC_FIELDS = ("id", "lang", "foil", "finish", "edition", "cond", "grade_by", "grade", "cond_note")


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


def read(mine):
    """-> (collection items, logs incl. hidden, bookings) from a my-data folder."""
    mine = pathlib.Path(mine)

    def load(p, key, default):
        try:
            return json.loads(p.read_text("utf-8")).get(key, default) if p.exists() else default
        except (OSError, ValueError):
            return default
    items = load(mine / "collection.json", "items", [])
    logs = []
    for f in sorted((mine / "sessions").glob("*.json")) if (mine / "sessions").exists() else []:
        try:
            logs.append(json.loads(f.read_text("utf-8")))
        except (OSError, ValueError):
            continue
    return items, logs, load(mine / "bookings.json", "bookings", [])


def rebuild(items, logs, bookings):
    """-> {key: fields + "count"} from the logs (count = logsum.expected; fields as above). items only tell which key a
    uid has (a hand delta on a log card counts on its src) – their fields are never used."""
    counts = logsum.expected(items, logs, bookings)
    by_uid = {it.get("uid"): logsum._key(it) for it in items}
    gone = {k for d in logs if (d.get("info") or {}).get("kind") == "manual" for k in d.get("gone") or ()}
    out = {}
    for d in logs:   # log cards
        info = d.get("info") or {}
        if info.get("kind") == "manual" or d.get("collection") is False or not d.get("ended"):
            continue
        prefix = d["id"] + "/"
        for pk in d.get("packs") or []:
            for e in pk.get("cards") or []:
                k = prefix + repr(e.get("added", 0))
                if not e.get("out") and k not in gone:
                    out[k] = fields_of(e)
    hand = []
    for d in logs:   # "By hand" lines, oldest first
        if (d.get("info") or {}).get("kind") == "manual":
            for pk in d.get("packs") or []:
                hand += [ln for ln in pk.get("cards") or [] if ln.get("uid")]
    hand.sort(key=lambda ln: ln.get("added") or 0)
    for ln in hand:
        uid = ln["uid"]
        k = by_uid.get(uid) or ln.get("src") or logsum._key(ln.get("item") or {"uid": uid})
        if k.startswith("uid:") and (ln.get("delta") or 0) > 0:
            out[k] = fields_of(ln)
        if ln.get("edit"):
            f = out.setdefault(k, fields_of(ln))
            for fk, (_before, after) in ln["edit"].items():
                if fk in SYNC_FIELDS:
                    f[fk] = _norm(fk, after)
    res = {}
    for k, n in counts.items():
        if n > 0:
            res[k] = dict(out.get(k) or {}, count=n)
    return res


def actual(items):
    """-> {key: fields + count} from collection.json (two entries on one key: counts added, first one's fields)."""
    out = {}
    for it in items:
        k = logsum._key(it)
        if k in out:
            out[k]["count"] += int(it.get("count", 1))
        else:
            out[k] = dict(fields_of(it), count=int(it.get("count", 1)))
    return out


def compare(items, logs, bookings):
    """-> [(key, field, from logs, in the collection)] for every difference."""
    want, have = rebuild(items, logs, bookings), actual(items)
    diffs = []
    for k in sorted(set(want) | set(have)):
        w, h = want.get(k), have.get(k)
        if w is None or h is None:
            diffs.append((k, "count", (w or {}).get("count", 0), (h or {}).get("count", 0)))
            continue
        for f in ("count",) + SYNC_FIELDS:
            if f in w and w[f] != h.get(f):
                diffs.append((k, f, w[f], h.get(f)))
    return diffs


def fill_variant(items, logs):
    """Lines written before 0.9.7.17 by the one-off migration (logsum.migration) and by record_edit lack the copy's
    finish/edition/grading. Fill them in, so the logs alone rebuild the copy: the value the copy had right after
    the line – the "before" of the next edit line on that field, else the collection's value now. Only fills
    empty fields of hand lines, never overwrites. -> the logs that changed (the caller saves them)."""
    from collection.manual import VARIANT
    by_uid = {it.get("uid"): it for it in items}
    hand = []
    for d in logs:
        if (d.get("info") or {}).get("kind") == "manual":
            for pk in d.get("packs") or []:
                hand += [(ln, d) for ln in pk.get("cards") or [] if ln.get("uid")]
    hand.sort(key=lambda x: x[0].get("added") or 0)
    changed = []
    for i, (ln, d) in enumerate(hand):
        it = by_uid.get(ln["uid"])
        if it is None or ln.get("delta", 0) < 0:   # gone, or a removal (its "item" keeps the whole entry)
            continue
        for k in VARIANT:
            if ln.get(k) or not it.get(k):
                continue
            later = next((x[0]["edit"][k] for x in hand[i + 1:]
                          if x[0]["uid"] == ln["uid"] and k in (x[0].get("edit") or {})), None)
            val = later[0] if later is not None else it[k]
            if val:
                ln[k] = val
                if not any(c is d for c in changed):
                    changed.append(d)
    return changed


def report(mine, fill=False):
    """fill: first fill_variant in memory (what the repair would give) – nothing is written."""
    items, logs, bookings = read(mine)
    filled = len(fill_variant(items, logs)) if fill else 0
    diffs = compare(items, logs, bookings)
    by_field = {}
    for _k, f, _w, _h in diffs:
        by_field[f] = by_field.get(f, 0) + 1
    return {"entries": len(items), "copies": sum(int(it.get("count", 1)) for it in items), "logs": len(logs),
            "differ": len({d[0] for d in diffs}), "filled_logs": filled, "by_field": by_field,
            "trade_only": sum(1 for it in items if it.get("trade")),
            "examples": [{"key": k, "field": f, "logs": w, "collection": h} for k, f, w, h in diffs]}
