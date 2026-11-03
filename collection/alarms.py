"""Price alerts – set in the "Trade" tab:
    Wishlist:     "Let me know when the card drops below X €" (cheapest printing; above Y € works too)
    Trade cards:  "Let me know when my card rises above Y €" (exactly this printing, foil if applicable)
Checked after every price update (also in the system tray, once a day); notification as a Windows notification or
a hint in the window. Only reported when the limit is crossed, not again every day.

Stored in the settings:
    price_alarms: [{"kind": "wish"|"trade", "name", "sid" (trade only), "set", "foil", "below", "above", "hit",
                    "src", "basis", "finish", "psid"}]
    list_alarms:  [{"lkind", "lid", "drop" (%), "rise" (%), "base": {card: price when created}, "hit": {card: bool},
                    "src", "basis", "finish"}]
                  – a whole list: reports every card that dropped by drop % or rose by rise % since creation
Which price counts (selectable per alert):
    src     "cm" Cardmarket (trend, €) | "tcg" TCGplayer (market, $ – converted to €) | "both" both – whichever
            reaches the desired price first counts (drop: the cheaper one, rise: the more expensive one)
    basis   "day" daily price | "avg7" / "avg30" average of the last 7 or 30 days (from the price history)
    finish  "any" normal, otherwise foil | "n" normal only | "f" foil only (trade cards: like your copy)
    psid    wish card: exactly this printing instead of the cheapest one
"""
import json

from cards import carddb
from cards import currency
from system.i18n import tr


def eur(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".") if v is not None else "–"


def key_of(a):
    return (a.get("kind") or "wish", a["sid"] if a.get("kind") == "trade" else a["name"], bool(a.get("foil"))
            if a.get("kind") == "trade" else False)


def _game():   # key of the open game (games.current_key) – a name of its own so tests can replace it
    import games
    return games.current_key()


def game_of(a):
    """Game of an alert – older alerts (from before multiple games) belong to Magic."""
    return a.get("game") or "mtg"


def all_alarms(settings):
    """All card alerts of all games (for writing back)."""
    out = []
    for a in settings.get("price_alarms") or []:
        if not a.get("name"):
            continue
        if not a.get("kind"):  # older alerts (bell on a printing): carry on as a wish by name
            a = dict(a, kind="wish")
        out.append(a)
    return out


def alarms(settings):
    """Card alerts of the open game (the other games stay stored but do not mix in)."""
    g = _game()
    return [a for a in all_alarms(settings) if game_of(a) == g]


def hits_of_game(settings, key):
    """Triggered alerts of one game (cards + lists) – for the overview of lists by game."""
    n = sum(1 for a in all_alarms(settings) if game_of(a) == key and a.get("hit"))
    n += sum(sum(1 for v in (a.get("hit") or {}).values() if v)
             for a in list_alarms(settings, every=True) if game_of(a) == key)
    return n


def find(settings, kind, name=None, sid=None, foil=False):
    for a in alarms(settings):
        if a["kind"] != kind:
            continue
        if kind == "wish" and a["name"] == name:
            return a
        if kind == "trade" and a.get("sid") == sid and bool(a.get("foil")) == bool(foil):
            return a
    return None


def put(settings, alarm, below, above):
    """Set/change an alert; below and above None = delete."""
    k, g = key_of(alarm), _game()
    lst = [a for a in all_alarms(settings) if not (game_of(a) == g and key_of(a) == k)]
    if below is not None or above is not None:
        lst.append(dict(alarm, below=below, above=above, hit=False, game=g))
    settings["price_alarms"] = lst


def text_of(a):
    """"below 2,00 €" / "above 10,00 €" – for tables."""
    if not a:
        return ""
    parts = ([tr(f"below {eur(a['below'])}")] if a.get("below") is not None else []) + \
            ([tr(f"above {eur(a['above'])}")] if a.get("above") is not None else [])
    return " · ".join(parts)


def cheapest(names):
    """{name: (cheapest € price normal, cheapest foil price)} across all printings."""
    out = {}
    if not names or not carddb.exists():
        return out
    with carddb.connection() as con:
        names = list(names)
        for i in range(0, len(names), 300):
            part = names[i:i + 300]
            for r in con.execute(f"SELECT name, MIN(eur), MIN(eur_foil) FROM cards WHERE name IN "
                                 f"({','.join('?' * len(part))}) GROUP BY name", part):
                out[r[0]] = (r[1], r[2])
    return out


SOURCES = (("cm", "Cardmarket"), ("tcg", "TCGplayer"), ("both", "beide"))
BASES = (("day", "Tagespreis"), ("avg7", "Ø 7 Tage"), ("avg30", "Ø 30 Tage"))
FINISHES = (("any", "normal, sonst Foil"), ("n", "nur normal"), ("f", "nur Foil"))
_LAYOUTS = "layout NOT IN ('art_series', 'token', 'double_faced_token', 'emblem')"


def opts_of(a):
    """Which price counts – with defaults for older alerts."""
    trade_ = a.get("kind") == "trade"
    return {"src": a.get("src") or "cm", "basis": a.get("basis") or "day",
            "finish": ("f" if a.get("foil") else "n") if trade_ else (a.get("finish") or "any"),
            "psid": a.get("sid") if trade_ else (a.get("psid") or None), "dir": "up" if trade_ else "down"}


def opts_text(o):
    """"Cardmarket · Ø 7 days" – empty for the defaults."""
    parts = ([] if o["src"] == "cm" else ["Cardmarket + TCGplayer"] if o["src"] == "both"
             else [dict(SOURCES)[o["src"]]])
    if o["basis"] != "day":
        parts.append(tr(dict(BASES)[o["basis"]]))
    if o["finish"] == "f":
        parts.append("Foil")
    return " · ".join(parts)


def _value(row, hist, o):
    """Price of a printing by source, finish and basis (in €)."""
    if o["src"] == "both":   # both sources: drop -> the cheaper one counts, rise -> the more expensive one
        vals = [v for v in (_value(row, hist, dict(o, src=s)) for s in ("cm", "tcg")) if v is not None]
        return (max if o.get("dir") == "up" else min)(vals) if vals else None
    for f in (("n", "f") if o["finish"] == "any" else (o["finish"],)):
        if o["basis"] == "day":
            v = (row or {}).get(("eur" if o["src"] == "cm" else "usd") + ("_foil" if f == "f" else ""))
        else:
            pts = ((hist or {}).get(("c" if o["src"] == "cm" else "t") + f) or [])[-(7 if o["basis"] == "avg7" else 30):]
            v = sum(x for _, x in pts) / len(pts) if pts else None
        if v is not None:
            return currency.from_usd(v) if o["src"] == "tcg" else v
    return None


def prints_of(names):
    """{name: [rows of all printings]} – one query for many names."""
    out = {}
    names = list(dict.fromkeys(n for n in names if n))
    if not names or not carddb.exists():
        return out
    with carddb.connection() as con:
        for i in range(0, len(names), 300):
            part = names[i:i + 300]
            for r in con.execute(f"SELECT * FROM cards WHERE name IN ({','.join('?' * len(part))}) AND {_LAYOUTS}", part):
                out.setdefault(r["name"], []).append(dict(r))
    return out


def prices(targets):
    """targets: [(key, alert)] -> {key: (price in € or None, id of the printing)} – for wish cards without a
    fixed printing, the cheapest printing according to the chosen rules."""
    opts = {k: opts_of(a) for k, a in targets}
    exact = {o["psid"] for o in opts.values() if o["psid"]}
    rows = carddb.cards_by_ids(exact) if exact and carddb.exists() else {}
    by_name = prints_of({a["name"] for k, a in targets if not opts[k]["psid"]})
    hist = {}
    if any(o["basis"] != "day" for o in opts.values()):
        from cards import pricehist
        sids = set(exact) | {r["id"] for k, a in targets if opts[k]["basis"] != "day" and not opts[k]["psid"]
                             for r in by_name.get(a["name"], [])}
        hist = pricehist.series_many(sids)
    out = {}
    for k, a in targets:
        o = opts[k]
        cands = ([rows[o["psid"]]] if o["psid"] in rows else []) if o["psid"] else by_name.get(a["name"], [])
        best = (None, cands[0]["id"] if cands else None)   # no price: still a printing to show
        for r in cands:
            v = _value(r, hist.get(r["id"]), o)
            if v is not None and (best[0] is None or v < best[0]):
                best = (v, r["id"])
        out[k] = best
    return out


def current_prices(lst):
    """{key_of(alert): current price}."""
    res = prices([(key_of(a), a) for a in lst])
    return {k: v[0] for k, v in res.items()}


def price_facts(sid):
    """Everything we know about a printing's prices: [{label, value, sub}] – daily prices of both sources,
    averages, low/high of the last 30 days."""
    if not sid or not carddb.exists():
        return []
    r = carddb.cards_by_ids({sid}).get(sid) or {}
    out = []

    def usd(v):
        if v is None:
            return "–"
        return f"{eur(currency.from_usd(v))}  ({eur(v)[:-2]} $)"
    out.append({"label": "Cardmarket", "value": eur(r.get("eur")), "sub": tr("Trend · normal")})
    out.append({"label": "Cardmarket", "value": eur(r.get("eur_foil")), "sub": tr("Trend · foil")})
    out.append({"label": "TCGplayer", "value": usd(r.get("usd")), "sub": tr("Market · normal")})
    out.append({"label": "TCGplayer", "value": usd(r.get("usd_foil")), "sub": tr("Market · foil")})
    from cards import pricehist
    h = pricehist.series(sid) or {}
    for key, shop, fin in (("cn", "Cardmarket", "normal"), ("cf", "Cardmarket", "Foil"),
                           ("tn", "TCGplayer", "normal"), ("tf", "TCGplayer", "Foil")):
        pts = [x for _, x in (h.get(key) or [])]
        if not pts:
            continue
        conv = (lambda v: currency.from_usd(v)) if key[0] == "t" else (lambda v: v)
        last7, last30 = pts[-7:], pts[-30:]
        out.append({"label": shop, "sub": tr(f"{fin} · Ø 7 / Ø 30 days"),
                    "value": f"{eur(conv(sum(last7) / len(last7)))} / {eur(conv(sum(last30) / len(last30)))}"})
        out.append({"label": shop, "sub": tr(f"{fin} · low / high 30 days"),
                    "value": f"{eur(conv(min(last30)))} / {eur(conv(max(last30)))}"})
    return out


def price_table(sid, days=30, rows=("now", "avg", "range"), fins=("n", "f"), settings=None):
    """Price table for the alert editor: Cardmarket on the left, TCGplayer on the right, per section (current,
    Ø 7 / Ø N days, low / high N days) rows for normal / foil. -> {"cols": [{"key", "title", "url", "groups":
    [{"title", "rows": [{"label", "value"}]}]}]}"""
    if not sid or not carddb.exists():
        return {"cols": []}
    from cards import pricehist
    from cards import shoplinks
    r = carddb.cards_by_ids({sid}).get(sid) or {}
    h = pricehist.series(sid) or {}
    links = {m["key"]: m["url"] for m in shoplinks.market_links(r, settings)} if r else {}
    fin_label = {"n": tr("normal"), "f": tr("Foil")}
    days = max(1, int(days))

    def money(v, usd):
        if v is None:
            return "–"
        return f"{eur(currency.from_usd(v))}  ({eur(v)[:-2]} $)" if usd else eur(v)
    cols = []
    for shop, title, now_title, usd, now_keys in (("c", "Cardmarket", tr("Trend"), False, {"n": "eur", "f": "eur_foil"}),
                                                  ("t", "TCGplayer", tr("Market"), True, {"n": "usd", "f": "usd_foil"})):
        conv = (lambda v: currency.from_usd(v)) if usd else (lambda v: v)
        groups = []
        if "now" in rows:
            groups.append({"title": now_title, "rows": [{"label": fin_label[f], "value": money(r.get(now_keys[f]), usd)}
                                                       for f in ("n", "f") if f in fins]})
        hist = {f: [x for _, x in (h.get(shop + f) or [])] for f in ("n", "f")}
        if "avg" in rows:
            title_avg = tr("Ø 7 days") if days == 7 else tr(f"Ø 7 / Ø {days} days")
            rr = []
            for f in ("n", "f"):
                if f not in fins:
                    continue
                pts = hist[f]
                if not pts:
                    rr.append({"label": fin_label[f], "value": "–"})
                    continue
                a7 = eur(conv(sum(pts[-7:]) / len(pts[-7:])))
                an = eur(conv(sum(pts[-days:]) / len(pts[-days:])))
                rr.append({"label": fin_label[f], "value": a7 if days == 7 else f"{a7} / {an}"})
            groups.append({"title": title_avg, "rows": rr})
        if "range" in rows:
            rr = []
            for f in ("n", "f"):
                if f not in fins:
                    continue
                pts = hist[f][-days:]
                rr.append({"label": fin_label[f],
                           "value": f"{eur(conv(min(pts)))} / {eur(conv(max(pts)))}" if pts else "–"})
            groups.append({"title": tr(f"Low / high {days} days"), "rows": rr})
        cols.append({"key": "cardmarket" if shop == "c" else "tcgplayer", "title": title,
                     "url": links.get("cardmarket" if shop == "c" else "tcgplayer", ""), "groups": groups})
    return {"cols": cols}


# ---------- Alerts for whole lists ----------
def list_alarms(settings, every=False):
    """List alerts of the open game (every=True: of all games)."""
    lst = [a for a in settings.get("list_alarms") or [] if a.get("lid")]
    if every:
        return lst
    g = _game()
    return [a for a in lst if game_of(a) == g]


def find_list(settings, lid):
    return next((a for a in list_alarms(settings) if a["lid"] == lid), None)


def list_prices(lkind, lid, coll, opts=None):
    """{card key: current price} of a list – wish/custom: cheapest printing per name (pinned: exactly
    that one), trade: exactly your own printing. opts: src/basis/finish of the list alert."""
    from collection import trade
    o = {k: v for k, v in (opts or {}).items() if k in ("src", "basis", "finish") and v}
    entries = trade.list_entries(lkind, lid, coll.items if coll is not None else [])
    targets = []
    if lkind in ("wish", "custom"):
        pinned = carddb.by_prints({(e["set"], e["number"]) for e in entries if e.get("set") and e.get("number")}) \
            if carddb.exists() else {}
        for e in entries:
            row = pinned.get((str(e.get("set") or "").lower(), str(e.get("number") or "")))
            key = e["name"] + (f" ({str(e['set']).upper()} #{e['number']})" if row else "")
            targets.append((key, dict(o, kind="wish", name=e["name"], psid=row["id"] if row else None)))
    else:
        from collection.collection import scryfall_id
        by_uid = {it["uid"]: it for it in (coll.items if coll is not None else [])}
        for e in entries:
            it = by_uid.get(e.get("uid"))
            if it is None:
                continue
            key = f"{e['name']} ({(e.get('set') or '').upper()}{' · Foil' if e.get('foil') else ''})"
            targets.append((key, dict(o, kind="trade", name=e["name"], sid=scryfall_id(it["id"]),
                                      foil=bool(e.get("foil")), finish=None)))
    return {k: v[0] for k, v in prices(targets).items()}


def put_list(settings, lkind, lid, drop, rise, coll, opts=None):
    """Set/change a list alert (drop/rise in %; both None = delete). Base prices = now (according to opts)."""
    old = find_list(settings, lid) or {}
    o = {k: (opts or {}).get(k) or old.get(k) for k in ("src", "basis", "finish")}
    g = _game()   # the same list ID exists in every game (default lists) – replace only this game's one
    lst = [a for a in list_alarms(settings, every=True) if not (a["lid"] == lid and game_of(a) == g)]
    if drop is not None or rise is not None:
        base = {k: v for k, v in list_prices(lkind, lid, coll, o).items() if v is not None}
        lst.append(dict({k: v for k, v in o.items() if v}, lkind=lkind, lid=lid, drop=drop, rise=rise, base=base,
                        hit={}, game=_game()))
    settings["list_alarms"] = lst


def list_rule(a):
    """"drops by 20 % · rises by 25 %"."""
    if not a:
        return ""
    parts = ([tr(f"drops by {a['drop']:.0f} %")] if a.get("drop") is not None else []) + \
            ([tr(f"rises by {a['rise']:.0f} %")] if a.get("rise") is not None else [])
    return " · ".join(parts)


def check_lists(settings, coll):
    """Check list alerts -> [(title, text)] newly triggered. New cards in the list get their base price."""
    from collection import trade
    out = []
    lst = list_alarms(settings, every=True)
    g = _game()
    for a in lst:
        if game_of(a) != g:   # lists of other games: this game does not know their prices
            continue
        name = next((x["name"] for x in trade.lists(a["lkind"]) if x["id"] == a["lid"]), None)
        if name is None:
            continue
        base, hit = a.setdefault("base", {}), a.setdefault("hit", {})
        for k, p in list_prices(a["lkind"], a["lid"], coll, a).items():
            if p is None:
                continue
            b = base.setdefault(k, p)
            low = a.get("drop") is not None and b > 0 and p <= b * (1 - a["drop"] / 100)
            high = a.get("rise") is not None and b > 0 and p >= b * (1 + a["rise"] / 100)
            if (low or high) and not hit.get(k):
                pct = (p / b - 1) * 100
                out.append((tr(f"Price alert – {tr(name)}"),
                            tr(f"{k} now costs {eur(p)} ({pct:+.0f} % since {eur(b)}).")))
            hit[k] = low or high
    settings["list_alarms"] = lst
    return out


def check(settings, coll=None):
    """After a price update: -> [(title, text)] of newly triggered alerts. Remembers what was already reported."""
    out = check_lists(settings, coll) if coll is not None else []
    every = all_alarms(settings)
    lst = [a for a in every if game_of(a) == _game()]
    pm = current_prices(lst)
    for a in lst:
        p = pm.get(key_of(a))
        if p is None:
            continue
        a["last"] = round(p, 2)
        low = a.get("below") is not None and p <= a["below"]
        high = a.get("above") is not None and p >= a["above"]
        if (low or high) and not a.get("hit"):
            label = f"{a['name']}" + (f" ({a['set']})" if a.get("set") else "")
            if low:
                text = tr(f"{label} now costs {eur(p)} – below your limit of {eur(a['below'])}.")
            else:
                text = tr(f"{label} now costs {eur(p)} – above your limit of {eur(a['above'])}.")
            out.append((tr("Price alert") if a["kind"] == "wish" else tr("Price alert – trade card"), text))
        a["hit"] = low or high
    settings["price_alarms"] = every
    return out


# ---------- Editing inline in the row (no dialog) ----------
# Keys: "list:<lkind>:<lid>" for whole lists, "card:<JSON>" for one card ({kind, name[, sid, foil, set]}).
def card_key(a):
    t = {"kind": a.get("kind") or "wish", "name": a["name"]}
    if t["kind"] == "trade":
        t.update(sid=a.get("sid"), foil=bool(a.get("foil")), set=a.get("set") or "")
    return "card:" + json.dumps(t, sort_keys=True, ensure_ascii=False)


def target_of(key):
    return json.loads(key[5:]) if key.startswith("card:") else None


NOTE_LIST = "Gemessen am Preis beim Anlegen des Alarms (neue Karten der Liste: ab dem ersten Prüfen). Jede Karte " \
            "meldet sich einmal, wenn sie die Grenze überschreitet."
NOTE_CARD = "Geprüft wird nach jedem Preis-Update – im Infobereich einmal am Tag, auch wenn das Fenster zu ist."


def form(settings, key, over=None):
    """The editor: a = drops (below), b = rises (above) – with defaults for new alerts (wish: cheaper,
    trade card: more expensive); plus what is watched and which price counts. over: changes in the open editor
    (src, basis, finish, psid) – not saved yet."""
    over = {k: v for k, v in (over or {}).items() if v is not None}
    seg = {"sources": [{"key": k, "text": tr(t)} for k, t in SOURCES],
           "bases": [{"key": k, "text": tr(t)} for k, t in BASES],
           "finishes": [{"key": k, "text": tr(t)} for k, t in FINISHES]}
    if key.startswith("list:"):
        _, lkind, lid = key.split(":", 2)
        old = find_list(settings, lid) or {}
        o = {"src": over.get("src") or old.get("src") or "cm", "basis": over.get("basis") or old.get("basis") or "day",
             "finish": over.get("finish") or old.get("finish") or "any"}
        wish = lkind in ("wish", "custom")
        pct = {"unit": " %", "step": 5, "from": 1, "to": 500, "dec": 0}
        return dict(seg, **o, key=key, list=True, kind=lkind, exists=bool(old), now="", note=tr(NOTE_LIST),
                    psid="", mode="list", sid="",
                    a=dict(pct, label=tr("a card drops by"), on=old.get("drop") is not None or (not old and wish),
                           value=old.get("drop") or 20.0),
                    b=dict(pct, label=tr("a card rises by"),
                           on=old.get("rise") is not None or (not old and not wish), value=old.get("rise") or 25.0))
    t = target_of(key)
    wish = t["kind"] == "wish"
    old = find(settings, t["kind"], t.get("name"), t.get("sid"), t.get("foil")) or {}
    a = dict(t, **{k: old.get(k) for k in ("src", "basis", "finish", "psid") if old.get(k)})
    for k in ("src", "basis", "finish"):
        if over.get(k):
            a[k] = over[k]
    if wish and "psid" in over:
        a["psid"] = over["psid"] or None
    o = opts_of(a)
    now, sid = prices([("x", a)])["x"]
    base = now or 1.0
    eur_ = {"unit": " €", "step": 0.5, "from": 0.01, "to": 100000, "dec": 2}
    o = dict(o, psid=o["psid"] or "")
    return dict(seg, **o, key=key, list=False, kind=t["kind"], exists=bool(old), now=eur(now), sid=sid or "",
                mode="print" if o["psid"] and wish else "cheapest", note=tr(NOTE_CARD),
                a=dict(eur_, label=tr("drops below"), on=old.get("below") is not None or (not old and wish),
                       value=old.get("below") or round(base * 0.8, 2)),
                b=dict(eur_, label=tr("rises above"), on=old.get("above") is not None or (not old and not wish),
                       value=old.get("above") or round(base * 1.25, 2)))


def save_form(settings, key, a_on, a, b_on, b, coll=None, opts=None):
    """Save the editor; both off = delete. opts: src/basis/finish/psid from the editor."""
    a, b = (float(a) if a_on else None), (float(b) if b_on else None)
    opts = opts or {}
    if key.startswith("list:"):
        _, lkind, lid = key.split(":", 2)
        put_list(settings, lkind, lid, a, b, coll, opts)
    else:
        t = target_of(key)
        old = find(settings, t["kind"], t.get("name"), t.get("sid"), t.get("foil")) or {}
        keep = {k: old.get(k) for k in ("src", "basis", "finish", "psid") if old.get(k)}
        keep.update({k: v for k, v in opts.items() if k in ("src", "basis", "finish", "psid")})
        if t["kind"] == "trade":
            keep.pop("psid", None)
            keep.pop("finish", None)
        put(settings, dict(t, **{k: v for k, v in keep.items() if v}), a, b)


def remove(settings, key, coll=None):
    save_form(settings, key, False, 0, False, 0, coll)


def prints_by_price(name, n=9, game=None):
    """Up to n printings of a card, cheapest first (for the stack with "cheapest printing"). game: other game."""
    if not carddb._has(game):
        return []
    with carddb.connection(game) as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM cards WHERE name = ? AND layout NOT IN ('art_series', 'token', 'double_faced_token', "
            "'emblem') ORDER BY COALESCE(eur, eur_foil, 1e9), released DESC LIMIT ?", (name, n))]
