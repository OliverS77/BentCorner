"""Charts for Qt Quick: describes the chart data (charts.py, statsview, deckview) as plain data for
qml/components/ChartView.qml – drawing happens natively in Qt Quick.

spec(w) -> dict or None (no known chart). Kinds:
  frame  tile with title, subtitle, toggle (modes) and content body:
         vbars (bars, optional line/horizontal lines/inner bars/values), line (trends), donut, hbars, empty
  kpis   key-figure tiles · hero (big number + sentence + facts) · section (section header)
  panel  small stream chart (ui.panels.Chart): tiles, vbars, line, donut, list
Colors come as ready-made values (current look, theme hooks) – QML doesn't need to convert anything.
"""
import time

from PySide6 import QtGui

from system.i18n import tr


def _c(x):
    """Color (name, QColor) -> "#rrggbb" or "#aarrggbb" in the current look."""
    q = x if isinstance(x, QtGui.QColor) else QtGui.QColor(x)
    return q.name(QtGui.QColor.HexArgb) if q.alpha() < 255 else q.name()


def _grid_labels(vmax, fmt, steps=4):
    return [fmt(vmax * i / steps) for i in range(steps + 1)]


def _date(ts, f="%d.%m."):
    return time.strftime(f, time.localtime(ts))


def spec(w):
    from ui import charts
    try:
        from ui import statsview
    except Exception:  # noqa: BLE001
        statsview = None
    name = type(w).__name__
    if isinstance(w, charts.KpiRow):
        return _kpis(w)
    if statsview is not None and isinstance(w, statsview.Hero):
        return _hero(w)
    if statsview is not None and isinstance(w, statsview.SectionHead):
        return {"kind": "section", "number": f"{w.number:02d}", "question": w.question, "note": w.note,
                "h": w.minimumHeight()}
    if isinstance(w, charts.Card):
        body = None
        if isinstance(w, charts.SessionBars):
            body = _session_bars(w)
        elif isinstance(w, charts.Cumulative):
            body = _cumulative(w)
        elif isinstance(w, charts.Donut):
            body = _donut(w)
        elif isinstance(w, charts.HBars):
            body = _hbars(w)
        elif isinstance(w, charts.Histogram):
            body = _histogram(w)
        elif statsview is not None and isinstance(w, statsview.PackBars):
            body = _pack_bars(w)
        elif name == "CurveChart":
            body = _curve(w)
        if body is None:
            return None
        return {"kind": "frame", "title": w.title, "sub": w.sub or "", "modes": list(w.modes), "mode": w.mode,
                "clickable": bool(w._clickable()), "body": body, "h": max(w.minimumHeight(), 200)}
    if name == "Chart" and hasattr(w, "kind") and hasattr(w, "data"):
        return _panel_chart(w)
    return None


# ---------- Tiles ----------
def _kpis(w):
    items = []
    for i, (title, value, fmt, color, extra) in enumerate(w.items):
        text = fmt(value) if isinstance(value, (int, float)) else str(value)
        items.append({"title": title, "text": text, "color": _c(color), "extra": extra or "", "first": i == 0})
    return {"kind": "kpis", "items": items, "h": w.minimumHeight()}


def _hero(w):
    v = w._value
    number = w._fmt(v) if isinstance(v, (int, float)) else str(v)
    facts = [{"label": str(a).upper(), "value": str(b)} for a, b in w.facts]
    return {"kind": "hero", "kicker": w.kicker, "number": number, "color": _c(w._color), "sentence": w.sentence,
            "facts": facts, "h": max(w.minimumHeight(), 150 + 36 * max(0, len(facts) - 3))}


# ---------- Tile contents ----------
def _money(w, v):
    from ui import charts
    return charts._money(v, w.fmt)


def _axis(w, vmax):
    from ui import charts
    return _grid_labels(vmax, lambda v: charts._short(v, w.fmt) if vmax >= 10 else charts._money(v, w.fmt))


def _session_bars(w):
    from ui import charts
    key = w.keys[w.mode] if w.mode < len(getattr(w, "keys", [])) else ("total", "pack", "euro")[min(w.mode, 2)]
    if not w.data:
        empty = tr("No data yet")
        if key == "euro" and w.raw:
            empty = tr("Enter what you paid in the log – then you'll see how much card value you get per euro.")
        return {"type": "empty", "text": empty}
    vmax = charts._nice(max(max(v, paid) for _, v, paid, _ in w.data))
    n = len(w.data)
    bars, line = [], []
    for i, (ts, v, paid, title) in enumerate(w.data):
        top = charts.GREEN if paid and v >= paid else charts.CYAN
        tip = [_date(ts, "%d.%m.%Y %H:%M") + (f" · {title}" if title else "")]
        if key == "euro":
            tip += [tr("Card value per euro paid: ") + _money(w, v),
                    tr("got more out than you paid") if v >= 1 else tr("got less out than you paid")]
        else:
            tip.append((tr("Avg. value per pack: ") if key == "pack" else tr("Value: ")) + _money(w, v))
            if paid:
                d = v - paid
                tip.append((tr("Paid per pack: ") if key == "pack" else tr("Stake: ")) + _money(w, paid)
                           + f"  ({'+' if d >= 0 else '−'}{_money(w, abs(d))})")
        bars.append({"v": v, "color": _c(top), "label": _date(ts) if n <= 12 or i % max(1, n // 8) == 0 else "",
                     "tip": tip})
        line.append(paid if paid else None)
    return {"type": "vbars", "vmax": vmax, "grid": _axis(w, vmax), "bars": bars, "bottom": _c(charts.TEAL),
            "maxw": 46, "line": {"vals": line, "color": _c(charts.AMBER), "dots": True} if any(line) else None}


def _cumulative(w):
    from ui import charts
    if len(w.pts) < 2:
        return {"type": "empty", "text": tr("No data yet")}
    vmax = charts._nice(max(max(v, pd) for _, v, pd in w.pts))
    tips = []
    for i, (ts, v, pd) in enumerate(w.pts):
        lines = [_date(ts, "%d.%m.%Y"), (tr("Total value today: ") if w.mode == 1 else tr("Total value when opened: "))
                 + _money(w, v)]
        if pd:
            d = v - pd
            lines += [tr("Spent: ") + _money(w, pd), tr("Balance: ") + ("+" if d >= 0 else "−") + _money(w, abs(d))]
        tips.append(lines)
    series = [{"vals": [v for _, v, _ in w.pts], "color": _c(charts.CYAN), "fill": True, "dash": False}]
    if w.pts[-1][2] > 0:
        series.append({"vals": [pd for _, _, pd in w.pts], "color": _c(charts.AMBER), "fill": False, "dash": True})
    return {"type": "line", "vmax": vmax, "grid": _axis(w, vmax), "series": series, "tips": tips, "skipFirst": True,
            "legend": [{"text": tr("Card value"), "color": _c(charts.CYAN)},
                       {"text": tr("Spent"), "color": _c(charts.AMBER)}]}


def _donut(w):
    if not w.total:
        return {"type": "empty", "text": tr("No data yet")}
    parts = [{"label": label, "n": n, "color": _c(col), "pct": f"{n / w.total * 100:.1f} %",
              "tip": [label, f"{n} {w.unit} · {n / w.total * 100:.1f} %"]} for label, n, col in w.parts]
    return {"type": "donut", "parts": parts, "total": w.total, "center": w.center_fmt(w.center),
            "centerLabel": w.center_label, "centerColor": _c(w.center_color)}


def _hbars(w):
    if not w.rows:
        return {"type": "empty", "text": tr("No data yet")}
    vmax = max(v for _, v, _ in w.rows) or 1
    from ui import charts
    rows = [{"label": label, "v": v, "text": (charts._money(v, w.fmt) if w.money else str(round(v))),
             "tip": [label, extra] if extra else []} for label, v, extra in w.rows]
    return {"type": "hbars", "vmax": vmax, "rows": rows, "color": _c(w.color), "bottom": _c(charts.TEAL)}


def _histogram(w):
    from ui import charts
    if not w.bins:
        return {"type": "empty", "text": tr("No data yet")}
    n = len(w.bins)
    bars = []
    for i, c in enumerate(w.bins):
        col = charts.PINK if i >= n - 2 and c else charts.CYAN
        bars.append({"v": c, "color": _c(col), "label": w._label(i), "value": str(c) if c else "",
                     "tip": [f"{w._label(i)} {w.per}", f"{c} {w.unit}"]})
    return {"type": "vbars", "vmax": max(w.bins) or 1, "grid": [], "bars": bars, "bottom": _c(charts.TEAL),
            "maxw": 999, "thin": True}


def _pack_bars(w):
    from ui import charts
    if not w.rows:
        return {"type": "empty", "text": tr("No data yet")}
    vmax = charts._nice(max(max(v for v, _, _ in w.rows), w.avg))
    n = len(w.rows)
    bars = []
    for i, (v, best, best_p) in enumerate(w.rows):
        tip = [tr(f"Pack {i + 1}") + ":  " + _money(w, v)]
        if best:
            tip.append(tr("Best card: ") + best + (f"  ({_money(w, best_p)})" if best_p else ""))
        if w.avg:
            from ui.statsview import _pct
            tip.append(tr("vs. your average: ") + _pct((v / w.avg - 1) * 100))
        bars.append({"v": v, "color": _c(charts.PINK if (best_p or 0) >= w.hit else charts.CYAN),
                     "label": str(i + 1) if n <= 24 or i % max(1, n // 12) == 0 else "", "tip": tip})
    return {"type": "vbars", "vmax": vmax, "grid": _axis(w, vmax), "bars": bars, "bottom": _c(charts.TEAL),
            "maxw": 38, "hlines": [{"v": w.avg, "color": _c(charts.AMBER), "label": ""}] if w.avg else []}


def _curve(w):
    if not any(w.curve):
        return {"type": "empty", "text": tr("No data yet")}
    vmax = max(w.curve) or 1
    cyan = _c(QtGui.QColor("#62f2ff"))
    labels = getattr(w, "labels", None)
    if labels:   # other game: own buckets (Pokémon: Basic · Stage 1 · Stage 2 …)
        inner = w.inner_label
        bars = [{"v": n, "color": cyan, "label": labels[i], "value": str(n) if n else "", "inner": w.creatures[i],
                 "tip": [labels[i], tr(f"{n} cards") + (f" · {w.creatures[i]} {inner}" if inner else "")]}
                for i, n in enumerate(w.curve)]
        legend = [{"text": inner, "color": _c(QtGui.QColor(70, 209, 122, 190))}] if inner else []
    else:
        bars = [{"v": n, "color": cyan, "label": "7+" if i == 7 else str(i), "value": str(n) if n else "",
                 "inner": w.creatures[i], "tip": [tr(f"Mana value {('7+' if i == 7 else i)}"),
                                                   tr(f"{n} cards · davon {w.creatures[i]} Kreaturen")]}
                for i, n in enumerate(w.curve)]
        legend = [{"text": tr("Creatures"), "color": _c(QtGui.QColor(70, 209, 122, 190))}]
    return {"type": "vbars", "vmax": vmax, "grid": [], "bars": bars, "bottom": _c(QtGui.QColor("#1f5f6b")),
            "maxw": 999, "inner": _c(QtGui.QColor(70, 209, 122, 150)), "legend": legend}


# ---------- small stream charts (ui.panels.Chart) ----------
def _panel_chart(w):
    d, k = w.data or {}, w.kind
    out = {"kind": "panel", "title": w.title, "h": w.minimumHeight()}
    if not d:
        out["body"] = {"type": "blank"}
        return out
    if k == "tiles":
        out["body"] = {"type": "tiles", "items": [{"label": a, "text": t, "color": _c(c)} for a, t, c in d["items"]]}
    elif k == "list":
        out["body"] = {"type": "list", "rows": [{"text": a, "sub": s, "price": p, "color": _c(c)}
                                                for a, s, p, c in d["rows"]]}
    elif k == "donut":
        parts = [(label, v, c) for label, v, c in d["parts"] if v]
        total = sum(v for _, v, _ in parts)
        out["body"] = {"type": "donut", "total": total, "center": str(total), "centerLabel": "",
                       "centerColor": "#f2f2f2",
                       "parts": [{"label": label, "n": v, "color": _c(c), "pct": f"{v / total * 100:.0f} %",
                                  "tip": [label, f"{v} · {v / total * 100:.0f} %"]} for label, v, c in parts]} \
            if total else {"type": "empty", "text": tr("No data yet")}
    elif k == "bars":
        vals = list(d.get("values") or [])
        if not vals:
            out["body"] = {"type": "empty", "text": tr("No data yet")}
            return out
        lines = d.get("lines", [])
        top = max(vals + [v for v, _, _ in lines] + [0.01]) * 1.12
        labels = d.get("labels", [])
        n = len(vals)
        import app
        hl = d.get("highlight")
        out["body"] = {"type": "vbars", "vmax": top, "grid": [f"{top * i / 4:.0f}" if top >= 10 else
                                                              f"{top * i / 4:.1f}" for i in range(5)],
                       "bars": [{"v": v, "color": _c(app.MAGENTA if i == hl else app.CYAN),
                                 "label": labels[i] if i < len(labels) and (n <= 16 or i % max(1, n // 12) == 0) else "",
                                 "tip": [labels[i] if i < len(labels) else "", f"{v:.2f}".replace(".", ",")]}
                                for i, v in enumerate(vals)],
                       "bottom": "#00000000", "maxw": 64,
                       "hlines": [{"v": v, "color": _c(c), "label": label} for v, c, label in lines]}
    elif k == "pairs":
        a, b, labels = d.get("a") or [], d.get("b") or [], d.get("labels", [])
        top = max(list(a) + list(b) + [0.01]) * 1.12
        import app
        out["body"] = {"type": "vbars", "vmax": top, "grid": [f"{top * i / 4:.0f}" for i in range(5)],
                       "pairs": [{"a": a[i], "b": b[i], "label": labels[i] if i < len(labels) else ""}
                                 for i in range(len(a))], "bars": [],
                       "colors": [_c(app.CYAN), "#ff6b6b"], "bottom": "#00000000", "maxw": 999,
                       "legend": [{"text": tr("Value"), "color": _c(app.CYAN)}, {"text": tr("Spent"),
                                                                                  "color": "#ff6b6b"}]}
    elif k == "line":
        vals, hline = list(d.get("values") or []), d.get("hline")
        if len(vals) < 2:
            out["body"] = {"type": "empty", "text": tr("Not enough data for a chart")}
            return out
        top = max(vals + ([hline] if hline else []) + [0.01]) * 1.12
        import app
        labels = d.get("labels") or []
        body = {"type": "line", "vmax": top, "grid": [f"{top * i / 4:.0f}" if top >= 10 else f"{top * i / 4:.1f}"
                                                       for i in range(5)],
                "series": [{"vals": vals, "color": _c(app.CYAN), "fill": True, "dash": False}],
                "tips": [[f"{v:.2f}".replace(".", ",")] for v in vals],
                "xlabels": [labels[0], labels[-1]] if labels else []}
        if hline:
            body["hlines"] = [{"v": hline, "color": "#ff6b6b", "label": tr(f"Spent {app.eur(hline)}")}]
            cross = next((i for i, v in enumerate(vals) if v >= hline), None)
            if cross is not None:
                body["marker"] = {"i": cross, "color": "#6dff9c", "label": tr(f"Break-even (card {cross + 1})")}
        out["body"] = body
    else:
        out["body"] = {"type": "blank"}
    return out


def act(w, value):
    """Click from QML: ["mode", i] = toggle in the header, ["pick", i] = entry clicked."""
    kind, i = value[0], int(value[1])
    if kind == "mode" and i != getattr(w, "mode", None):
        w.mode = i
        if getattr(w, "on_mode", None):
            w.on_mode(i)
        w.restart()
    elif kind == "pick" and w._clickable():
        w.picked.emit(i)
