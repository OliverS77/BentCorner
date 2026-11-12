"""Trade offers: every ticket-based trade has a trade ID and versions (offer, counter-offer …) –
data/my-data/offers.json. Independent of the lists; the booking itself is done by bookings.py.

Offer: {"id" (trade ID), "partner": [profile ID, name], "status", "versions": [ticket …], "created", "updated"}
Status: "sent" (I sent the latest version) · "received" (the latest came from the other side) ·
"accepted" (accepted, closing ticket sent/read in) · "declined" (declined) · "withdrawn" (withdrawn) ·
"closing" (the friend accepted – their closing ticket came through the mailbox, mine to book; ports 06.11.2026)
game: every function works on the open game's file; a ticket from the mailbox for another game goes straight into
that game's file (game=…) – no switching of the game for a parcel.
"""
import json
import time

from scanner.common import MINE

FILE = MINE / "offers.json"
OPEN = ("sent", "received", "closing")
STATUS_TEXT = {"sent": "Gesendet – wartet auf Antwort", "received": "Erhalten – deine Antwort",
               "accepted": "Abgeschlossen", "declined": "Abgelehnt", "withdrawn": "Zurückgezogen",
               "closing": "Angenommen – buchen"}


def undelivered(o):
    """A ticket of mine the mailbox couldn't deliver (full 507, refused 403): the row says so (lead 07.11.)."""
    m = o.get("mail") or {}
    return bool(m) and not m.get("ok") and o.get("status") in OPEN


def status_text(o):
    """The row's state: "Not delivered" instead of "waiting for an answer" while the mailbox couldn't deliver it – only
    in the view, the stored status stays "sent". Delivered or only shared as an image: as before (lead 07.11.)."""
    if o.get("status") == "sent" and undelivered(o):
        return "Not delivered"
    return STATUS_TEXT.get(o.get("status"), o.get("status"))


def _file(game=None):
    if game:
        import games
        if game != games.current().key:
            return games.mine(game, "offers.json")
    return FILE


def load(game=None):
    f = _file(game)
    try:
        return json.loads(f.read_text("utf-8")).get("offers") or [] if f.exists() else []
    except (OSError, ValueError):
        return []


def _save(items, game=None):
    from system import undo
    f = _file(game)
    f.parent.mkdir(parents=True, exist_ok=True)
    undo.before_write(f, "Tauschangebot")
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "offers": items}, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(f)


def get(trade_id, game=None):
    return next((o for o in load(game) if o["id"] == trade_id), None)


def _same(a, b):
    """The same profile – the pixel code carries only the start of an ID."""
    a, b = str(a), str(b)
    return a == b or (min(len(a), len(b)) >= 12 and (a.startswith(b) or b.startswith(a)))


def _put(t, partner, status, game=None):
    items = load(game)
    tid = t.get("x") or t["id"]
    o = next((x for x in items if x["id"] == tid), None)
    now = time.time()
    if o is not None and partner and partner[0] and (o.get("partner") or ["", ""])[0] \
            and not _same(o["partner"][0], partner[0]):
        return o   # someone else's trade ID (review 08.11. T4): never taken over by another sender
    if o is None:
        o = {"id": tid, "partner": list(partner), "status": status, "versions": [], "created": now}
        items.append(o)
    if not any(v["id"] == t["id"] for v in o["versions"]):
        o["versions"].append(t)
    o["versions"].sort(key=lambda v: (int(v.get("n") or 1), v.get("t") or 0))
    o.update(status=status, updated=now, partner=list(partner) if partner and partner[1] else o["partner"])
    _save(items, game)
    from collection import collectibles
    collectibles.archive(t, status, info={"partner": o["partner"]})
    return o


def record_sent(t):
    """I shared an offer (or counter-offer) as a ticket."""
    return _put(t, t.get("o") or ["", ""], "sent")


def record_received(t, partner):
    """Read in an offer from the other side (not booked yet)."""
    return _put(t, partner, "received")


def set_status(trade_id, status, game=None):
    items = load(game)
    for o in items:
        if o["id"] == trade_id:
            o.update(status=status, updated=time.time())
    _save(items, game)


def from_mailbox(t, my_id):
    """A ticket a friend sent through the mailbox (net/relay.py checked: issued by them, to me) -> what happened:
    "received" (offer / counter-offer, filed under Trade offers), "closing" (they accepted: their closing ticket waits
    for me to book it), or None (nothing to do: old version, already booked, or not readable)."""
    from collection import ticket
    sd = ticket.side(t, my_id)
    if sd is None:
        return None
    g = ticket.game_of(t)
    tid = t.get("x") or t["id"]
    o = get(tid, g)
    if o is not None and any(v["id"] == t["id"] for v in o["versions"]):
        return None   # already here (the same ticket as an image, or sent twice)
    if ticket.kind(t) == "o":
        if o is not None and o["status"] in ("accepted", "declined", "withdrawn"):
            return None   # this trade is over on my side
        _put(t, sd[2], "received", g)
        return "received"
    if o is not None and o["status"] == "accepted":
        return None
    _put(t, sd[2], "closing", g)
    return "closing"


def set_mail(trade_id, info, game=None):
    """How sending through the mailbox went (shown as a quiet line in the offer): {"ok", "status", "t"}"""
    items = load(game)
    for o in items:
        if o["id"] == trade_id:
            o["mail"] = dict(info)
    _save(items, game)


def gone_from_mailbox(trade_id, friend_pid, why="withdrawn"):
    """The friend withdrew their offer or declined mine (ticket_gone): the open trade is marked "withdrawn" /
    "declined" – in whichever game it lies. -> True if one was marked"""
    import games
    for key, _name, _ready in games.GAMES:
        if not games.mine(key).is_dir():
            continue
        o = get(trade_id, key)
        if o is not None and o["status"] in OPEN and (o.get("partner") or ["", ""])[0] == friend_pid:
            set_status(trade_id, "declined" if why == "declined" else "withdrawn", key)
            return True
    return False


def latest(o):
    return (o.get("versions") or [None])[-1]


def sorted_offers():
    """Open ones first, then by last change."""
    return sorted(load(), key=lambda o: (o["status"] not in OPEN, -(o.get("updated") or 0)))
