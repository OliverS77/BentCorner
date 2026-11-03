"""Online knowledge for deck building – cached so it stays visible offline.

Commander Spellbook (commanderspellbook.com, community-maintained combo database):
    find(): combos that are fully in the deck, and "near combos" (exactly one card missing) – plus the bracket
    of the whole deck (Ruthless, Spicy, Powerful, Oddball, Core, Exhibition).
EDHTop16 (edhtop16.com, results of cEDH tournaments):
    cedh(): how often a commander is played in tournaments and how it performs (win rate, top-cut rate).

Cache: data/kartendaten/online/ – Spellbook per deck list (if the list changes, it is queried again),
EDHTop16 per commander for 7 days.
"""
import hashlib
import json
import time

from scanner.common import REF
from net import netpolite

CACHE = REF / "online"
SPELLBOOK = "https://backend.commanderspellbook.com"
EDHTOP16 = "https://edhtop16.com/api/graphql"
UA = {"User-Agent": netpolite.UA}   # netpolite sets it anyway – one source of truth
CEDH_DAYS = 7
# Deck bracket from Commander Spellbook (abbreviation -> name, explanation)
TAGS = {"R": ("Ruthless", "Kombos auf Turnier-/cEDH-Niveau"), "S": ("Spicy", "schnelle, starke Kombos"),
        "P": ("Powerful", "starke Synergien, aber keine frühen Siegkombos"),
        "O": ("Oddball", "ungewöhnliche, eher langsame Kombos"), "C": ("Core", "typisches Gelegenheitsspiel"),
        "E": ("Exhibition", "Themen- und Spaßdecks"), "B": ("Banned", "enthält gebannte Karten")}


def _cache_path(kind, key):
    return CACHE / f"{kind}_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}.json"


def _load(path, max_age=None):
    try:
        d = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if max_age is not None and time.time() - d.get("t", 0) > max_age:
        return None
    return d


def _save(path, d):
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, ensure_ascii=False), "utf-8")
    except OSError:
        pass


def _variant(v, deck_names):
    """Spellbook variant -> small dict for display."""
    cards = [u["card"]["name"] for u in v.get("uses", [])]
    lower = {n.lower() for n in deck_names}
    return {"id": v.get("id"), "cards": cards,
            "missing": [c for c in cards if c.lower() not in lower and c.split(" // ")[0].lower() not in lower],
            "produces": [p["feature"]["name"] for p in v.get("produces", [])][:4],
            "description": v.get("description") or "", "prereq": v.get("easyPrerequisites") or "",
            "tag": v.get("bracketTag") or "", "popularity": v.get("popularity") or 0,
            "url": f"https://commanderspellbook.com/combo/{v.get('id')}/"}


def cached_find(commanders, main):
    """Cached result for exactly this list (or the last one for this deck) – without internet."""
    return _load(_cache_path("csb", _deck_key(commanders, main)))


def _deck_key(commanders, main):
    return json.dumps([sorted(commanders), sorted(main.items())], ensure_ascii=False)


def find(commanders, main, timeout=25):
    """Combos for a deck: commanders [names], main {name: count}. -> {"included", "almost", "tag", "t"} or
    raises an exception (offline). The result is cached."""
    body = {"commanders": [{"card": n, "quantity": 1} for n in commanders],
            "main": [{"card": n, "quantity": q} for n, q in main.items()]}
    r = netpolite.post(f"{SPELLBOOK}/find-my-combos", json=body, headers=UA, timeout=timeout)
    r.raise_for_status()
    res = r.json().get("results") or {}
    names = list(commanders) + list(main)
    included = [_variant(v, names) for v in res.get("included") or []]
    almost = [_variant(v, names) for v in res.get("almostIncluded") or []]
    almost = [a for a in almost if len(a["missing"]) == 1]
    almost.sort(key=lambda a: -a["popularity"])
    tag = ""
    try:  # bracket of the whole deck
        rb = netpolite.post(f"{SPELLBOOK}/estimate-bracket", json=body, headers=UA, timeout=timeout)
        if rb.ok:
            tag = rb.json().get("bracketTag") or ""
    except Exception:  # noqa: BLE001 – combos matter more than the bracket
        pass
    out = {"included": included, "almost": almost[:40], "tag": tag, "t": time.time()}
    _save(_cache_path("csb", _deck_key(commanders, main)), out)
    return out


def cached_cedh(commanders):
    return _load(_cache_path("cedh", " / ".join(sorted(commanders))))


def cedh(commanders, timeout=20):
    """cEDH tournament data (EDHTop16, last year) for the commander(s) -> {"name", "count", "winRate",
    "conversionRate", "metaShare", "topCuts", "t"} or {"count": 0} (never in tournaments). Cached for 7 days."""
    key = " / ".join(sorted(commanders))
    path = _cache_path("cedh", key)
    hit = _load(path, CEDH_DAYS * 86400)
    if hit is not None:
        return hit
    query = ("query($n:String!){ commander(name:$n){ name stats(filters:{timePeriod: ONE_YEAR})"
             "{ count topCuts conversionRate metaShare winRate } } }")
    out = {"count": 0, "t": time.time()}
    # Partners: EDHTop16 writes "A / B" (alphabetical); individually as fallback
    for name in ([key] if len(commanders) > 1 else []) + list(commanders):
        r = netpolite.post(EDHTOP16, json={"query": query, "variables": {"n": name}}, headers=UA, timeout=timeout)
        r.raise_for_status()
        c = (r.json().get("data") or {}).get("commander")
        if c and c.get("stats") and c["stats"].get("count"):
            out = dict(c["stats"], name=c["name"], t=time.time())
            break
    _save(path, out)
    return out


def deck_lists(deck, rows):
    """Deck -> (commander names, {main deck name: count}) for the queries."""
    cm = [rows[s]["name"] for s in deck.get("commanders", []) if s in rows]
    main = {}
    for c in deck["cards"]:
        if c.get("board", "main") == "main" and c["sid"] in rows:
            n = rows[c["sid"]]["name"]
            main[n] = main.get(n, 0) + c["count"]
    return cm, main
