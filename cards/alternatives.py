"""Alternatives to a card – no AI, just from the card data:

- rules text similarity (shared words and word pairs, the card's own name counts as "~", reminder text in
  parentheses doesn't count) – finds e.g. "Murder ↔ Hero's Downfall", "Llanowar Elves ↔ Elvish Mystic"
- same role (ramp, card draw, removal … – the same estimate as in the deck info)
- same card type, similar mana value

Categories to toggle on/off (several = all must match): KINDS.
"""
import re

from collection import decks

KINDS = [("role", "Gleiche Aufgabe"), ("stronger", "Stärker"), ("cheaper", "Günstiger"),
         ("text", "Ähnlicher Text"), ("type", "Gleicher Kartentyp"), ("mv", "Gleicher Manawert")]
KIND_HELP = {
    "role": "Erfüllt dieselbe Aufgabe im Deck (Ramp, Kartenziehen, Removal …)",
    "stronger": "Wird deutlich häufiger gespielt (EDHREC) und macht Ähnliches",
    "cheaper": "Kostet höchstens 80 % des Preises",
    "text": "Regeltext ist sehr ähnlich",
    "type": "Gleicher Kartentyp (Kreatur, Spontanzauber …)",
    "mv": "Manawert höchstens 1 auseinander",
}
_STOP = set("a an the of to and or in on at for with your you its it this that is are be as by from each any target "
            "may if then until end turn put into onto when whenever".split())
_REMINDER = re.compile(r"\([^)]*\)")
_cache = {}


def _words(r):
    key = r.get("id") or r.get("name")
    hit = _cache.get(key)
    if hit is not None:
        return hit
    text = (r.get("oracle_text") or "").lower()
    name = (r.get("name") or "").lower().split(" // ")[0]
    if name:
        text = text.replace(name, "~")
    text = _REMINDER.sub(" ", text)
    toks = [t for t in re.findall(r"[a-z~+/0-9{}-]+", text) if t not in _STOP]
    uni = set(toks)
    bi = {a + " " + b for a, b in zip(toks, toks[1:])}
    if len(_cache) > 60000:
        _cache.clear()
    _cache[key] = (uni, bi)
    return uni, bi


def text_sim(a, b):
    ua, ba = _words(a)
    ub, bb = _words(b)
    if not ua or not ub:
        return 0.0
    j1 = len(ua & ub) / len(ua | ub)
    j2 = len(ba & bb) / len(ba | bb) if ba and bb else 0.0
    return 0.4 * j1 + 0.6 * j2


def price(r):
    p = r.get("eur") if r.get("eur") is not None else r.get("eur_foil")
    return float(p) if p is not None else None


def analyze(target, r):
    """-> (score 0..1, {categories}) for card r as a replacement for target."""
    t_type, r_type = decks._type(target), decks._type(r)
    t_roles, r_roles = set(decks.card_roles(target, t_type)), set(decks.card_roles(r, r_type))
    ts = text_sim(target, r)
    role_j = len(t_roles & r_roles) / len(t_roles | r_roles) if t_roles and r_roles else 0.0
    same_type = t_type == r_type
    mv_d = abs((target.get("cmc") or 0) - (r.get("cmc") or 0))
    score = 0.5 * ts + 0.3 * role_j + 0.1 * same_type + 0.1 * max(0.0, 1 - mv_d / 3)
    kinds = set()
    if t_roles & r_roles:
        kinds.add("role")
    if ts >= 0.22:
        kinds.add("text")
    if same_type:
        kinds.add("type")
    if mv_d <= 1:
        kinds.add("mv")
    pt, pr = price(target), price(r)
    if pt is not None and pr is not None and pr <= pt * 0.8:
        kinds.add("cheaper")
    rt, rr = target.get("edhrec_rank"), r.get("edhrec_rank")
    if rr and (not rt or rr < rt * 0.6) and ("role" in kinds or ts >= 0.15):
        kinds.add("stronger")
    return score, kinds


def rank(target, rows, wanted=(), exclude_names=()):
    """Candidates sorted by similarity. wanted: categories that must all match (empty = all alternatives
    that have anything in common with the card at all). -> [(row, score, {categories})]"""
    skip = {n.lower() for n in exclude_names} | {(target.get("name") or "").lower()}
    t_land = decks._type(target) == "Land"
    out = []
    for r in rows:
        if (r.get("name") or "").lower() in skip:
            continue
        if (decks._type(r) == "Land") != t_land:  # lands only against lands
            continue
        score, kinds = analyze(target, r)
        if wanted and not set(wanted) <= kinds:
            continue
        if not wanted and score < 0.12 and "role" not in kinds:
            continue  # has nothing to do with the card
        out.append((r, score, kinds))
    out.sort(key=lambda t: (-t[1], t[0].get("edhrec_rank") or 10 ** 7))
    return out
