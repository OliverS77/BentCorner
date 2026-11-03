"""Binders: collection albums per game (data/…/my-data/binders.json) – curated, freely arranged, with gaps.

A binder: {"id", "name", "cols", "rows", "slots": [slot …], "created", "updated"}
Slot: None (empty) or {"sid": card database ID, "set", "number", "lang", "foil", "name"} – whether you own the card
follows from the collection (owned); otherwise it is "still missing" (greyed out). Pages follow from the number of
slots (cols × rows per page); the view always shows two pages side by side (spread).
Sharing: put out like the lists (relay.board_put, slot "binder-<id>") – friends see the gaps.
"""
import json
import time
import uuid

from scanner.common import MINE

FILE = MINE / "binders.json"
SIZES = ((3, 3), (4, 3), (2, 2))   # 9-, 12- and 4-pocket pages (like real binder sleeves)


def load():
    try:
        return json.loads(FILE.read_text("utf-8")).get("binders") or []
    except (OSError, ValueError):
        return []


def save(items):
    from system import undo
    MINE.mkdir(parents=True, exist_ok=True)
    undo.before_write(FILE, "Binder")
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "binders": items}, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(FILE)


def get(bid):
    return next((b for b in load() if b["id"] == bid), None)


def put(b):
    items = load()
    b["updated"] = time.time()
    for i, x in enumerate(items):
        if x["id"] == b["id"]:
            items[i] = b
            break
    else:
        items.append(b)
    save(items)
    return b


def new(name, cols=3, rows=3):
    now = time.time()
    b = {"id": uuid.uuid4().hex[:10], "name": (name or "").strip()[:60] or "Binder", "cols": int(cols),
         "rows": int(rows), "slots": [None] * (int(cols) * int(rows) * 2), "created": now, "updated": now}
    return put(b)


def remove(bid):
    save([b for b in load() if b["id"] != bid])


def per_page(b):
    return int(b.get("cols") or 3) * int(b.get("rows") or 3)


def pages(b):
    """Number of pages (always even – spreads)."""
    n = max(1, -(-len(b.get("slots") or []) // per_page(b)))
    return n + (n % 2)


def slot_of(row, lang="en", foil=False):
    """Slot from a card database row."""
    return {"sid": row.get("id") or row.get("sid"), "set": str(row.get("set_code") or row.get("set") or "").lower(),
            "number": str(row.get("number") or ""), "lang": lang or "en", "foil": bool(foil),
            "name": row.get("name") or ""}


def _grow(b, n):
    """At least n slots, padded to whole spreads."""
    spread = per_page(b) * 2
    slots = b.setdefault("slots", [])
    target = -(-max(n, 1) // spread) * spread
    slots.extend([None] * (target - len(slots)))


def add_cards(b, rows, at=None):
    """Insert cards: from slot at (default: the first free one, or the end) – existing slots do not shift,
    free slots are filled."""
    slots = b.setdefault("slots", [])
    i = at if at is not None else next((k for k, s in enumerate(slots) if s is None), len(slots))
    for r in rows:
        while i < len(slots) and slots[i] is not None:
            i += 1
        _grow(b, i + 1)
        slots[i] = r if isinstance(r, dict) and "sid" in r else slot_of(r)
        i += 1
    _grow(b, len(slots))
    return b


def set_slot(b, i, slot):
    _grow(b, i + 1)
    b["slots"][i] = slot
    return b


def move(b, i, j):
    """Slot i to j (swaps with the content of j)."""
    _grow(b, max(i, j) + 1)
    s = b["slots"]
    s[i], s[j] = s[j], s[i]
    return b


def _trim_tail(b, n):
    """After an insert: remove up to n empty slots at the end again (so the page count does not grow needlessly)."""
    s = b["slots"]
    while n > 0 and s and s[-1] is None:
        s.pop()
        n -= 1


def move_to(b, i, j):
    """Insert slot i at position j (dragged between two slots): everything in between shifts by one – gaps
    shift along. j = position before the move."""
    _grow(b, max(i, j) + 1)
    s = b["slots"]
    if i == j or i + 1 == j:
        return b
    x = s.pop(i)
    s.insert(j - 1 if j > i else j, x)
    _grow(b, len(s))
    return b


def insert_at(b, j, slot):
    """Insert a new card at position j, the rest shifts by one (gaps included)."""
    _grow(b, j + 1)
    b["slots"].insert(j, slot)
    _trim_tail(b, 1)
    _grow(b, len(b["slots"]))
    return b


def value(b, owned, prices):
    """(value of all cards in the binder, value of the owned ones) in € – prices: {sid: price}."""
    total = have = 0.0
    for s in b.get("slots") or []:
        if not s:
            continue
        p = prices.get(s.get("sid")) or 0
        total += p
        if owned.get((s["set"], s["number"])):
            have += p
    return total, have


def insert_gap(b, i):
    """Insert an empty slot at position i (the rest shifts by one)."""
    b.setdefault("slots", []).insert(i, None)
    _grow(b, len(b["slots"]))
    return b


def remove_slot(b, i, close=False):
    """Empty a slot (close: take it out, the rest moves up)."""
    if 0 <= i < len(b.get("slots") or []):
        if close:
            b["slots"].pop(i)
        else:
            b["slots"][i] = None
    _grow(b, len(b["slots"]))
    return b


def owned_map(items):
    """{(set, number): count} of the collection – whether a slot is "owned" (language/foil ignored: the card is there)."""
    out = {}
    for it in items:
        k = (str(it.get("set") or "").lower(), str(it.get("number") or ""))
        out[k] = out.get(k, 0) + int(it.get("count", 1))
    return out


def progress(b, owned):
    """(owned, cards in the binder) – empty slots do not count."""
    cards = [s for s in b.get("slots") or [] if s]
    have = sum(1 for s in cards if owned.get((s["set"], s["number"])))
    return have, len(cards)


def missing(b, owned):
    return [s for s in b.get("slots") or [] if s and not owned.get((s["set"], s["number"]))]


def share_payload(b, owned):
    """For friends (put out): slots compact as [set, number, language, foil, owned?] or None – without names."""
    return {"v": 1, "kind": "binder", "id": b["id"], "name": b["name"], "cols": b.get("cols", 3),
            "rows": b.get("rows", 3),
            "slots": [None if s is None else [s["set"], s["number"], s.get("lang") or "en", int(bool(s.get("foil"))),
                                              1 if owned.get((s["set"], s["number"])) else 0]
                      for s in b.get("slots") or []]}
