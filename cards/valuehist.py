"""Collection value over time – from the price history (pricehist, Magic: the last 90 days from MTGJSON).

Each card only counts from the day you own it (date of its session – can be back-dated under Sessions –, otherwise
when it was added) and only from its first real price: nothing is back-filled (otherwise new sets would show up in the
curve with their high pre-order price weeks before release). After the last price, the last known one stays valid.
Price: Cardmarket (foil copies with the foil price), otherwise TCGplayer converted to euros; cards without any history
at today's price. We record nothing ourselves (only what the source publishes).

Grey line: your oldest cards in the period (what was already there on the first day with cards), carried forward –
shows the pure price development without additions. Additions: days on which cards were added (for chart markers).
"""
import datetime
import threading

from cards import currency
from cards import pricehist
from collection.collection import scryfall_id
from system.i18n import tr


def available():
    import games
    return games.current().price_source == "mtgjson" and pricehist.exists()


def _owned_since(it, starts):
    """Since when do you own this copy? Session date (src = "<session>/<added>"), otherwise "added"."""
    sess = (it.get("src") or "").split("/", 1)[0]
    ts = starts.get(sess) or it.get("added") or 0
    return datetime.date.fromtimestamp(ts) if ts else datetime.date(1970, 1, 1)


def collection_series(items, starts=None):
    """-> {"days", "values", "base", "adds": {day index: (cards, value)}, "flat"} or None (nothing there).
    starts: {session ID: start time} (default: load all sessions)."""
    if not items:
        return None
    if starts is None:
        from collection import sessions
        starts = {s.get("id"): s.get("started") for s in sessions.load_all()}
    groups = {}   # (sid, foil) -> {owned-since day: count}
    first = {}
    for it in items:
        key = (scryfall_id(it["id"]), bool(it.get("foil")))
        day = _owned_since(it, starts)
        g = groups.setdefault(key, {})
        g[day] = g.get(day, 0) + int(it.get("count", 1) or 1)
        first.setdefault(key[0], it)
    hist = pricehist.series_many([sid for sid, _ in groups])
    today = datetime.date.today()
    days = [today - datetime.timedelta(days=i) for i in range(pricehist.WINDOW - 1, -1, -1)]
    start = days[0]
    curves, flat = [], 0
    for (sid, foil), owned in groups.items():
        h = hist.get(sid) or {}
        pts = h.get("cf" if foil else "cn")
        usd = False
        if not pts:
            pts, usd = h.get("tf" if foil else "tn"), True
        if pts:
            daily = {d: (currency.from_usd(p) or 0) if usd else p for d, p in pts}
        else:   # no history: today's price, constant
            it = first.get(sid, {})
            price = it.get("eur_foil" if foil else "eur") or it.get("eur") or it.get("eur_foil") or 0
            daily = {start: float(price or 0)} if price else {}
            flat += sum(owned.values())
        if daily:
            curves.append((daily, owned))
    if not curves:
        return None

    def price_on(daily, d, state):
        """Price on day d: last known one (carried forward), none before the first price."""
        p = daily.get(d)
        if p is not None:
            state[0] = p
        return state[0]

    values = [0.0] * len(days)
    adds = {}
    owned_by_day = []   # per curve: count you already own on day i
    for daily, owned in curves:
        state = [None]
        first_day = min(daily)
        for d in sorted(k for k in daily if k < start):   # state at window start (for carrying forward)
            state[0] = daily[d]
        row = []
        for i, d in enumerate(days):
            n = sum(c for od, c in owned.items() if od <= d)
            p = price_on(daily, d, state) if d >= first_day else None
            row.append((n, p))
            if n and p:
                values[i] += n * p
        owned_by_day.append(row)
        for od, c in owned.items():   # mark additions within the period
            if od > start:
                i = (od - start).days
                if 0 <= i < len(days):
                    n0, v0 = adds.get(i, (0, 0.0))
                    p = row[i][1] or 0
                    adds[i] = (n0 + c, v0 + c * p)
    values = [round(v, 2) for v in values]
    if not any(values):
        return None
    # grey line: the oldest cards (already there on the first day with a value), then carried on without additions
    b = next(i for i, v in enumerate(values) if v)
    base = list(values)
    for i in range(b + 1, len(days)):
        total = 0.0
        for row in owned_by_day:
            n_then, _ = row[b]
            _, p = row[i]
            if n_then and p:
                total += n_then * p
        base[i] = round(total, 2)
    return {"days": days, "values": values, "base": base, "adds": adds, "flat": flat, "base_day": b}


def _money(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def chart_spec(res, title=None, h=260, sub_pad=0, link=""):
    """Tile for ChartView (kind frame / line) from collection_series(). The curve starts shortly before your first
    card in the period (it would be empty before that); additions on nearby days share one marker. sub_pad: space to
    the right of the subtitle (e.g. for an ✕)."""
    title = title or tr("Wert der Sammlung")
    if not res:
        return {"kind": "frame", "title": title, "sub": "", "modes": [], "mode": 0, "clickable": False, "h": h,
                "body": {"type": "empty", "text": tr("No data yet – this needs cards with price history.")}}
    c0 = max(0, res.get("base_day", 0) - 3)
    vals, base, days = res["values"][c0:], res["base"][c0:], res["days"][c0:]
    adds = {i - c0: x for i, x in res["adds"].items() if i >= c0}
    res = dict(res, base_day=res.get("base_day", 0) - c0)
    shown = [v for v in vals + base if v]
    lo, hi = min(shown), max(shown)
    span = max(1.0, hi - lo)
    floor = max(0.0, lo - span * 0.25)
    top = hi + span * 0.1

    def short(v):
        return f"{round(v):,} €".replace(",", ".")
    tips = []
    for i, (d, v) in enumerate(zip(days, vals)):
        lines = [d.strftime("%d.%m.%Y"), tr("Value: ") + _money(v)]
        if base[i] != v:
            lines.append(tr("older cards: ") + _money(base[i]))
        if i in adds:
            n, val = adds[i]
            lines.append(tr(f"+{n} cards added (worth {_money(val)} then)"))
        tips.append(lines)
    series = [{"vals": [max(0.0, v - floor) if v else 0.0 for v in vals], "color": "#62f2ff", "fill": True,
               "dash": False}]
    if any(base[i] != vals[i] for i in range(len(vals))):
        series.append({"vals": [max(0.0, v - floor) if v else 0.0 for v in base], "color": "#8a91a8", "fill": False,
                       "dash": True})
    v0 = vals[res.get("base_day", 0)]
    d = vals[-1] - v0
    sub = _money(vals[-1]) + "  ·  " + (tr("since ") + days[0].strftime("%d.%m.") if c0 else tr("last 90 days"))
    if base[-1] and base[-1] != vals[-1]:
        b0 = base[res.get("base_day", 0)]
        pct = (base[-1] - b0) / b0 * 100 if b0 else 0
        sub += "  ·  " + tr("older cards") + f" {'+' if pct >= 0 else '−'}{abs(pct):.1f} %".replace(".", ",")
    elif v0:
        pct = d / v0 * 100
        sub += f"  ·  {'+' if pct >= 0 else '−'}{abs(pct):.1f} %".replace(".", ",")
    if res["flat"]:
        sub += "  ·  " + (tr("1 card without history") if res["flat"] == 1 else
                          tr(f"{res['flat']} cards without history"))
    legend = [{"text": tr("Value"), "color": "#62f2ff"}]
    if len(series) > 1:
        legend.append({"text": tr("older cards without additions"), "color": "#8a91a8"})
    body = {"type": "line", "vmax": top - floor, "grid": [short(floor + (top - floor) * i / 4) for i in range(5)],
            "xlabels": [days[0].strftime("%d.%m."), days[-1].strftime("%d.%m.")], "series": series, "tips": tips,
            "skipFirst": False, "legend": legend,
            "vmarks": _marks(adds, len(days))}
    return {"kind": "frame", "title": title, "sub": sub, "modes": [], "mode": 0, "clickable": False, "h": h,
            "body": body, "subPad": sub_pad, "link": link}


def _marks(adds, n_days):
    """Additions -> markers; when they are close together (up to 4 % of the width), they share one with the sum."""
    gap = max(2, round(n_days * 0.04))
    out = []
    for i, (n, _) in sorted(adds.items()):
        if out and i - out[-1]["first"] <= gap:
            out[-1]["n"] += n
        else:
            out.append({"i": i, "first": i, "n": n})
    return [{"i": m["i"], "label": f"+{m['n']}"} for m in out]


_runner = None


def compute_async(items, done):
    """Compute in the background (many cards × 90 days); done(res) arrives on the main thread."""
    global _runner
    from PySide6 import QtCore
    if _runner is None:
        class Runner(QtCore.QObject):
            ready = QtCore.Signal(object, object)
        _runner = Runner()
        _runner.ready.connect(lambda fn, res: fn(res))
    items = [dict(it) for it in items]

    def work():
        try:
            res = collection_series(items)
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("Value history")
            res = None
        _runner.ready.emit(done, res)
    threading.Thread(target=work, daemon=True).start()
