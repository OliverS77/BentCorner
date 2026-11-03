"""Changes by hand as session entries: every card added to or taken out of the collection outside the scanner
(library, detail view, compare view …) becomes a line in the day's session of kind "manual" – one session per day
("Changed by hand · 27.10."), saved like every session (sessions.py).

A line: the card as it was (name, set, number, language, finish …), its price at that moment, "delta" (+n added,
-n taken out), "uid" of the collection entry and "added" (the line's own key, as in scan sessions). A removed entry
also keeps the whole collection entry ("item") – so taking the removal back brings exactly that entry back.

The collection is already changed when a line is written: these sessions never go into the collection themselves
(info kind "manual", "collection": False; Collection.sync_session skips them). Each line can be taken back on its own
(undo): it reverts exactly that change and says when the card has moved on since (traded away, fewer left, in a
deck) – then only with force.
"""
import time

from cards import conditions
from collection import sessions
from collection.collection import CARD_KEYS, price
from system.i18n import tr

KIND = "manual"


def day_id(when=None):
    return "manual_" + time.strftime("%Y-%m-%d", time.localtime(when or time.time()))


def is_manual(d):
    return (d.get("info") or {}).get("kind") == KIND


def _load_day(sid, when):
    try:
        return sessions.load(sid)
    except (OSError, ValueError):
        return {"id": sid, "started": when, "ended": when, "collection": False,
                "info": {"kind": KIND, "title": "", "active": True},
                "packs": [{"opened": when, "type": KIND, "cards": []}]}


def _save(d):
    from scanner import core
    d["stats"] = core.session_stats(d["packs"], d["info"])
    sessions.save(d)


save = _save   # a whole „By hand“ log (the migration log): with its figures, like every session

VARIANT = ("finish", "edition", "grade_by", "grade", "cond_note")


def copy_variant(item, line):
    """The copy's finish/edition/grading onto a line (only if set) – the logs must be able to rebuild the copy
    (collection/shadow.py)."""
    for k in VARIANT:
        if item.get(k):
            line[k] = item[k]


def record(item, delta, when=None, why=""):
    """One change by hand: collection entry `item` (as it is/was) changed by `delta` copies (+ added, - taken out).
    why: a short note shown under the line (e.g. "undone"). -> the line written (or None for delta 0)."""
    delta = int(delta)
    if not delta:
        return None
    now = when or time.time()
    d = _load_day(day_id(now), now)
    line = {k: item.get(k) for k in CARD_KEYS}
    line.update(lang=item.get("lang") or "en", foil=bool(item.get("foil")), uid=item.get("uid"), delta=delta,
                price=price(item), added=now)
    if item.get("src"):   # a scanned card: the line belongs to its log card (logsum – the library is the logs' sum)
        line["src"] = item["src"]
    copy_variant(item, line)
    line.update(conditions.fields(item) or {"cond": item.get("cond") or conditions.DEFAULT})
    if delta < 0:
        line["item"] = dict(item)   # taken out: the whole entry, to bring it back as it was
    if why:
        line["why"] = why
    cards = d["packs"][0]["cards"]
    while any(c.get("added") == line["added"] for c in cards):   # two changes in the same instant
        line["added"] += 1e-6
    cards.append(line)
    d["ended"] = max(d.get("ended") or now, now)
    _save(d)
    return line


def lines(sid):
    try:
        return list(sessions.load(sid)["packs"][0]["cards"])
    except (OSError, ValueError, KeyError, IndexError):
        return []


def undo(coll, sid, added, force=False):
    """Take one line back. -> ("ok", "") done, ("moved", why) the card moved on since (nothing done unless force),
    ("gone", why) nothing left to take back. The line leaves the session when done."""
    try:
        d = sessions.load(sid)
    except (OSError, ValueError):
        return "gone", tr("This change no longer exists.")
    cards = d["packs"][0]["cards"]
    line = next((c for c in cards if c.get("added") == added), None)
    if line is None:
        return "gone", tr("This change no longer exists.")
    delta = int(line.get("delta") or 0)
    it = coll.get(line.get("uid")) if line.get("uid") else None
    if delta > 0:   # added by hand: take those copies out again
        if it is None:
            return "gone", tr("The card is no longer in your collection.")
        have, trade = int(it.get("count", 1)), int(it.get("trade") or 0)
        why = (tr("Only {n} left in your collection.").format(n=have) if have < delta else
               tr("{n} of them are marked for trading.").format(n=trade) if trade > have - delta else "")
        if why and not force:
            return "moved", why
        coll.set_count(it["uid"], max(0, have - delta))
    else:           # taken out by hand: bring them back
        if it is not None:
            coll.set_count(it["uid"], int(it.get("count", 1)) - delta)
        elif line.get("item"):
            back = dict(line["item"])
            back["count"] = -delta
            coll.restore_items([back])
            if back.get("src"):
                coll.hidden.discard(back["src"])
        else:
            return "gone", tr("The card can't be brought back.")
    cards.remove(line)
    _save(d)
    return "ok", ""


def record_edit(item, changes, when=None):
    """A copy without a log of its own changed (condition, language, foil …): a line with delta 0 and what changed
    ({field: [before, after]}) – the copies stay, the change is written down. -> the line."""
    if not changes:
        return None
    now = when or time.time()
    d = _load_day(day_id(now), now)
    line = {k: item.get(k) for k in CARD_KEYS}
    line.update(lang=item.get("lang") or "en", foil=bool(item.get("foil")), uid=item.get("uid"), delta=0,
                price=price(item), added=now, edit={k: list(v) for k, v in changes.items()})
    copy_variant(item, line)
    line.update(conditions.fields(item) or {"cond": item.get("cond") or conditions.DEFAULT})
    cards = d["packs"][0]["cards"]
    while any(c.get("added") == line["added"] for c in cards):
        line["added"] += 1e-6
    cards.append(line)
    d["ended"] = max(d.get("ended") or now, now)
    _save(d)
    return line


def fold_gone(log):
    """0.9.2.102–104 wrote a log card that had left without a line as a minus line with no card (uid "gone:<src>",
    id/name None) – the statistics stumbled over them. They mean exactly what the log's "gone" list says now: move
    them there (the sum stays the same). -> True if the log changed (then save it)."""
    if (log.get("info") or {}).get("kind") != KIND:
        return False
    changed = False
    gone = list(log.get("gone") or [])
    for pk in log.get("packs") or []:
        keep = []
        for ln in pk.get("cards") or []:
            uid = str(ln.get("uid") or "")
            if uid.startswith("gone:") and int(ln.get("delta") or 0) < 0:
                src = (ln.get("item") or {}).get("src") or uid[5:]
                if src not in gone:
                    gone.append(src)
                changed = True
                continue
            keep.append(ln)
        pk["cards"] = keep
    if changed:
        log["gone"] = gone
    return changed


def hide_gone(coll, log):
    """Log cards a gap/migration log lists as gone ("gone", older: lines with uid "gone:…"): their src into
    "hidden", so sync_session doesn't bring them back."""
    for src in log.get("gone") or ():
        coll.hidden.add(src)
    for ln in log["packs"][0]["cards"]:
        src = (ln.get("item") or {}).get("src")
        if src and int(ln.get("delta") or 0) < 0 and str(ln.get("uid", "")).startswith("gone:"):
            coll.hidden.add(src)


def close_gap(coll, logs, bookings, why, when=None):
    """What differs between the library and the sum of its logs (logsum.diff) becomes lines in the day's log, each
    with why. -> lines written."""
    from collection import logsum
    now = when or time.time()
    gap_log = logsum.migration(coll.items, logs, bookings, now)
    if gap_log is None:
        return 0
    hide_gone(coll, gap_log)
    d = _load_day(day_id(now), now)
    if gap_log.get("gone"):
        d["gone"] = sorted(set(d.get("gone") or ()) | set(gap_log["gone"]))
    cards = d["packs"][0]["cards"]
    for ln in gap_log["packs"][0]["cards"]:
        ln.pop("migrated", None)
        ln["why"] = why
        while any(c.get("added") == ln["added"] for c in cards):
            ln["added"] += 1e-6
        cards.append(ln)
    d["ended"] = max(d.get("ended") or now, now)
    _save(d)
    return len(gap_log["packs"][0]["cards"])
