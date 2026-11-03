"""EDHREC – what the community plays with a commander (for upgrades and deck suggestions).

EDHREC has no official API; we read the same data their site loads (json.edhrec.com) –
sparingly: only on click, at most every 2 s (netpolite), cached for four weeks. Without internet: the cache –
or nothing (then the caller works offline with its own estimates).

OFF since 2026-10-26: EDHREC's terms (edhrec.com/terms) forbid "automated searches, requests, or queries" – the same
clause as Archidekt. Until EDHREC allows it (request in the backlog), ALLOWED stays False: only what is already in
the cache is used, nothing is fetched.

commander(name) -> {"cards": {name: {"inclusion": 0..1, "synergy": -1..1, "decks": n}}, "types": {...}} or None
"""
import json
import re
import time
import unicodedata

from net import netpolite
from scanner.common import REF

CACHE = REF / "online" / "edhrec"
URL = "https://json.edhrec.com/pages/commanders/{}.json"
ALLOWED = False   # EDHREC's terms forbid automated requests – switch on only with their permission
MAX_AGE = 28 * 86400  # four weeks – the data changes slowly, and EDHREC should get little load from us
_mem = {}


def slug(name):
    """"Atraxa, Praetors' Voice" -> "atraxa-praetors-voice" (double-faced cards: front face only)."""
    name = name.split(" // ")[0]
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"['’,.!?:\"]", "", name.lower())
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def _parse(d):
    cards = {}
    for lst in (d.get("container") or {}).get("json_dict", {}).get("cardlists") or []:
        for cv in lst.get("cardviews") or []:
            name, pot = cv.get("name"), cv.get("potential_decks") or 0
            if not name or not pot:
                continue
            cards[name] = {"inclusion": (cv.get("num_decks") or 0) / pot, "synergy": cv.get("synergy") or 0.0,
                           "decks": cv.get("num_decks") or 0, "list": lst.get("header") or ""}
    types = {k: d.get(k) for k in ("creature", "instant", "sorcery", "artifact", "enchantment", "planeswalker",
                                   "land", "basic", "nonbasic") if isinstance(d.get(k), (int, float))}
    return {"cards": cards, "types": types}


def cached(name):
    """Only from the cache (even if stale) – never goes online."""
    s = slug(name)
    if s in _mem:
        return _mem[s]
    path = CACHE / f"{s}.json"
    try:
        d = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    out = _parse(d)
    _mem[s] = out
    return out


def commander(name, timeout=12, online=True):
    """Data for a commander: fresh (at most four weeks old, MAX_AGE) or from the cache."""
    s = slug(name)
    path = CACHE / f"{s}.json"
    try:
        fresh = path.exists() and time.time() - path.stat().st_mtime < MAX_AGE
    except OSError:
        fresh = False
    if fresh or not online or not ALLOWED or netpolite.cooling(URL):  # off / pausing us: cache only
        return cached(name)
    try:
        r = netpolite.get(URL.format(s), timeout=timeout)
        if r.status_code == 404:
            return None  # not a (known) commander
        r.raise_for_status()
        d = r.json()
    except Exception:  # noqa: BLE001 – offline / site changed: cache
        return cached(name)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, ensure_ascii=False), "utf-8")
    except OSError:
        pass
    out = _parse(d)
    _mem[s] = out
    return out
