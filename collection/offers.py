"""Trade offers: every ticket-based trade has a trade ID and versions (offer, counter-offer …) –
data/my-data/offers.json. Independent of the lists; the booking itself is done by bookings.py.

Offer: {"id" (trade ID), "partner": [profile ID, name], "status", "versions": [ticket …], "created", "updated"}
Status: "sent" (I sent the latest version) · "received" (the latest came from the other side) ·
"accepted" (accepted, closing ticket sent/read in) · "declined" (declined) · "withdrawn" (withdrawn)
"""
import json
import time

from scanner.common import MINE

FILE = MINE / "offers.json"
OPEN = ("sent", "received")
STATUS_TEXT = {"sent": "Gesendet – wartet auf Antwort", "received": "Erhalten – deine Antwort",
               "accepted": "Abgeschlossen", "declined": "Abgelehnt", "withdrawn": "Zurückgezogen"}


def load():
    try:
        return json.loads(FILE.read_text("utf-8")).get("offers") or [] if FILE.exists() else []
    except (OSError, ValueError):
        return []


def _save(items):
    from system import undo
    MINE.mkdir(parents=True, exist_ok=True)
    undo.before_write(FILE, "Tauschangebot")
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "offers": items}, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(FILE)


def get(trade_id):
    return next((o for o in load() if o["id"] == trade_id), None)


def _put(t, partner, status):
    items = load()
    tid = t.get("x") or t["id"]
    o = next((x for x in items if x["id"] == tid), None)
    now = time.time()
    if o is None:
        o = {"id": tid, "partner": list(partner), "status": status, "versions": [], "created": now}
        items.append(o)
    if not any(v["id"] == t["id"] for v in o["versions"]):
        o["versions"].append(t)
    o["versions"].sort(key=lambda v: (int(v.get("n") or 1), v.get("t") or 0))
    o.update(status=status, updated=now, partner=list(partner) if partner and partner[1] else o["partner"])
    _save(items)
    from collection import collectibles
    collectibles.archive(t, status, info={"partner": o["partner"]})
    return o


def record_sent(t):
    """I shared an offer (or counter-offer) as a ticket."""
    return _put(t, t.get("o") or ["", ""], "sent")


def record_received(t, partner):
    """Read in an offer from the other side (not booked yet)."""
    return _put(t, partner, "received")


def set_status(trade_id, status):
    items = load()
    for o in items:
        if o["id"] == trade_id:
            o.update(status=status, updated=time.time())
    _save(items)


def latest(o):
    return (o.get("versions") or [None])[-1]


def sorted_offers():
    """Open ones first, then by last change."""
    return sorted(load(), key=lambda o: (o["status"] not in OPEN, -(o.get("updated") or 0)))
