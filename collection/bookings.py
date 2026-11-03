"""Bookings: what leaves or enters the collection through trades (data/my-data/bookings.json).

A trade is booked once and can be undone:
  - given cards: copies are taken out of the collection. If they come from a session, the collection remembers
    that ("hidden") – if the session is later removed from the library and added back, the traded card does
    NOT come back (no +1), and nothing can drop below 0 either (only what is there gets removed).
  - received cards: a singles session "Tausch mit …" (Sessions → Trade/Purchase), from there into the collection.
Each booking remembers which copies it took – undoing puts exactly those back.

Booking: {"id", "t", "kind": "trade", "ticket", "partner": [ID, name], "give": [card], "get": [card],
"taken": [{"uid", "n", "item"}], "short": [card] (missing at booking time), "session": session ID}
"""
import json
import time
import uuid

from collection import sessions
from scanner.common import MINE
from system.i18n import tr

FILE = MINE / "bookings.json"
PENDING = MINE / "pending-trades.json"   # parts of mixed trades for THIS game, booked the next time it opens


def load():
    try:
        d = json.loads(FILE.read_text("utf-8")) if FILE.exists() else {}
    except (OSError, ValueError):
        d = {}
    return d.get("bookings") or []


def _save(items):
    from system import undo
    MINE.mkdir(parents=True, exist_ok=True)
    undo.before_write(FILE, "Tausch")
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "bookings": items}, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(FILE)


def by_ticket(ticket_id):
    return next((b for b in load() if ticket_id and b.get("ticket") == ticket_id), None)


def _key(c):
    """Card [set, number, language, foil, …] -> comparison key."""
    return str(c[0] or "").lower(), str(c[1] or ""), c[2] or "en", bool(c[3])


def _item_key(it):
    return str(it.get("set") or "").lower(), str(it.get("number") or ""), it.get("lang") or "en", bool(it.get("foil"))


def plan(coll, give, prefer=None):
    """Which copies would a trade take? prefer: {card index: uid} (exactly this copy first).
    -> ([(card index, uid, count)], [missing cards with count])"""
    take, short = [], []
    used = {}
    for i, c in enumerate(give):
        want = int(c[4] or 1)
        k = _key(c)
        cands = [it for it in coll.items if _item_key(it) == k]
        uid0 = (prefer or {}).get(i)
        # first the chosen copy, then trade cards, then manually added ones, then the oldest
        cands.sort(key=lambda it: (it.get("uid") != uid0, not it.get("trade"), bool(it.get("src")),
                                   it.get("added") or 0))
        for it in cands:
            free = int(it.get("count", 1)) - used.get(it["uid"], 0)
            if want <= 0 or free <= 0:
                continue
            n = min(want, free)
            take.append((i, it["uid"], n))
            used[it["uid"]] = used.get(it["uid"], 0) + n
            want -= n
        if want > 0:
            short.append(list(c[:4]) + [want] + list(c[5:6]))
    return take, short


def _entries(get, cards_db):
    """Received cards -> session entries (one per copy). cards_db: {(set, number): row} from carddb."""
    from cards import carddb
    from scanner import core
    now = time.time()
    out, missing = [], []
    for c in get:
        r = cards_db.get((str(c[0]).lower(), str(c[1])))
        if r is None:
            missing.append(c)
            continue
        for _ in range(max(1, int(c[4] or 1))):
            e = dict(carddb.entry_from_row(r), foil=bool(c[3]), added=now + len(out) * 0.001)
            e.pop("thumb", None)
            core.Session._set_lang(e, c[2] or "en")
            e["price"] = core.price_of(e)
            out.append(e)
    return out, missing


def book_trade(coll, t, give, get, partner, prefer=None, cards_db=None, foreign=None):
    """Book a trade (t: ticket). -> booking. Saves collection, session and bookings (one undo step).
    foreign: cards of the same trade from other games – shown greyed out in the session."""
    from scanner import core
    from system import undo
    take, short = plan(coll, give, prefer)
    taken = []
    for _i, uid, n in take:
        it = coll.get(uid)
        if it is None:
            continue
        taken.append({"uid": uid, "n": n, "item": dict(it)})
        coll.set_count(uid, int(it.get("count", 1)) - n)
    sid = None
    entries, missing = _entries(get, cards_db or {})
    if entries or foreign:
        now = time.time()
        sid = "trade_" + time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(now))
        while sessions.exists(sid):
            sid += "b"
        name = partner[1] if partner and len(partner) > 1 else ""
        sess = core.Session((), {"id": sid, "started": now, "ended": now, "collection": True,
                                 "info": {"title": tr(f"Trade with {name}").strip() if name else tr("Trade"),
                                          "kind": "singles", "pack_type": "trade", "ticket": t.get("id"),
                                          "foreign": list(foreign or [])},
                                 "packs": [{"opened": now, "cards": entries, "type": "trade"}]})
        d = sess.to_dict()
        undo.before_write(sessions.SESSIONS / f"{sid}.json", "Tausch")
        sessions.save(d)
        coll.sync_session(d)
    b = {"id": uuid.uuid4().hex[:10], "t": time.time(), "kind": "trade", "ticket": t.get("id"),
         "partner": list(partner or ["", ""]), "give": give, "get": get, "taken": taken, "short": short,
         "missing": missing, "session": sid}
    items = load()
    items.append(b)
    _save(items)
    coll.save()
    if not str(t.get("id") or "").startswith("session-"):
        from collection import collectibles
        collectibles.archive(t, "booked", info={"booking": b["id"], "session": sid, "short": len(short),
                                                "missing": len(missing)})
    return b


def add_pending(game, t, give, get, partner, foreign):
    """Queue part of a mixed trade for another game (booked as soon as that game is open)."""
    import games
    f = games.mine(game) / "pending-trades.json"
    try:
        items = json.loads(f.read_text("utf-8")).get("pending") or [] if f.exists() else []
    except (OSError, ValueError):
        items = []
    if any(x.get("ticket", {}).get("id") == t.get("id") for x in items):
        return
    items.append({"ticket": t, "give": give, "get": get, "partner": list(partner or ["", ""]), "foreign": foreign,
                  "t": time.time()})
    # in the same Undo step as the open game's booking (lead 03.11.): Undo takes the waiting part back too – never half
    # a trade (the web: bookings.bookMixed)
    from system import undo
    undo.before_write(f)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"version": 1, "pending": items}, ensure_ascii=False, indent=1), "utf-8")


def take_pending():
    """Fetch the queued trade parts of the open game (and empty the file). -> [dict]"""
    try:
        items = json.loads(PENDING.read_text("utf-8")).get("pending") or [] if PENDING.exists() else []
    except (OSError, ValueError):
        items = []
    if items:
        PENDING.unlink(missing_ok=True)
    return items


def cancel(coll, booking_id):
    """Undo a trade: given copies come back, trade session is removed. -> True if the booking existed."""
    from system import undo
    items = load()
    b = next((x for x in items if x.get("id") == booking_id), None)
    if b is None:
        return False
    for tk in b.get("taken") or []:
        it = coll.get(tk["uid"])
        if it is not None:
            coll.update(tk["uid"], count=int(it.get("count", 1)) + int(tk["n"]))
            continue
        old = dict(tk["item"], count=int(tk["n"]))
        if old.get("src"):
            coll.hidden.discard(old["src"])
        coll.restore_items([old])
    if b.get("session"):
        coll.remove_session(b["session"])
        undo.before_write(sessions.SESSIONS / f"{b['session']}.json", "Tausch")
        sessions.delete(b["session"])
    _save([x for x in items if x.get("id") != booking_id])
    coll.save()
    return True


def prices_of(cards, cards_db):
    """Total in € (trend) of the cards [set, number, language, foil, count] -> (total, number without a price)."""
    total, unknown = 0.0, 0
    for c in cards:
        r = cards_db.get((str(c[0]).lower(), str(c[1])))
        p = None if r is None else (r.get("eur_foil") if c[3] and r.get("eur_foil") is not None else r.get("eur"))
        if p is None:
            unknown += 1
        else:
            total += p * int(c[4] or 1)
    return round(total, 2), unknown

