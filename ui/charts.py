"""Data for the statistics charts (no widgets): key figures, value per session, value vs. spending, donuts, horizontal
bars, distributions. Drawn in Qt Quick (qml/components/ChartView.qml) from qcharts.spec(object).

Each chart holds its data and the selected toggle (mode); picked(i) reports a click on an entry –
only if someone is listening (then the entries are clickable).
"""
import math

from cards import packtypes
from system.i18n import tr

CYAN, TEAL, INK, MUTED, LINE = "#62f2ff", "#1f5f6b", "#eef1ff", "#8a91a8", "#2c3352"
GREEN, RED, AMBER, PINK = "#46d17a", "#ff4d5e", "#ffb347", "#ff5bd6"
RARITY_COLORS = [("mythic", "Mythic", "#ff8a3d"), ("rare", "Rare", "#e7c35a"), ("uncommon", "Uncommon", "#b8c7d9"),
                 ("common", "Common", "#6f7690"), ("special", "Special", PINK)]


def _money(v, fmt):
    return fmt(v) if fmt else f"{v:.2f} €"


def _short(v, fmt):
    """Axis label without decimals: 1.234 €."""
    s = _money(v, fmt)
    if "," not in s:
        return s
    num, rest = s.rsplit(",", 1)
    return f"{num} {rest.split(' ', 1)[1]}" if " " in rest else num


def _nice(v):
    if v <= 0:
        return 1.0
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * e:
            return m * e
    return 10 * e


# ---------- Data ----------
def summarize(all_sessions):
    """Key figures and series for the charts from the session dicts (sessions.load_all())."""
    ss = sorted([s for s in all_sessions if s["stats"]["cards"]], key=lambda s: s.get("started", 0))
    out = {"sessions": ss, "packs": 0, "cards": 0, "total": 0.0, "paid": 0.0, "paid_total": 0.0,
           "rarity": {}, "foil": 0, "pulls": [], "pack_values": [], "sets": {}}
    for s in ss:
        st = s["stats"]
        out["packs"] += st["packs"]
        out["cards"] += st["cards"]
        out["total"] += st["total"]
        if st.get("paid"):
            out["paid"] += st["paid"]
            out["paid_total"] += st["total"]
        for pack in s.get("packs", []):
            cards = pack.get("cards") or []
            if cards:
                out["pack_values"].append(sum((c.get("price") or 0) for c in cards))
            for c in cards:
                r = c.get("rarity") or "common"
                out["rarity"][r] = out["rarity"].get(r, 0) + 1
                out["foil"] += bool(c.get("foil"))
                code = (c.get("set") or "?").upper()
                out["sets"][code] = out["sets"].get(code, 0) + 1
                if c.get("price"):
                    out["pulls"].append((c["price"], c.get("name", "?"), code, s.get("started", 0), c))   # c: printing to show
    out["pulls"].sort(key=lambda t: -t[0])
    return out


def _sid(card_id):
    card_id = card_id or ""   # a log line without a card (old "gone" lines of 0.9.2.102–104 had id None)
    return card_id.rpartition("_")[0] if "_" in card_id else card_id


def filter_sessions(all_sessions, types=None, tags=None):
    """Restrict sessions to the selected pack types and tags (copies with recalculated key figures). The spend (paid)
    only counts if the whole session is included – otherwise the balance would be skewed."""
    from scanner.core import session_stats
    out = []
    for s in all_sessions:
        info = s.get("info") or {}
        if tags and not set(tags) & set(info.get("tags") or []):
            continue
        full = [p for p in s.get("packs", []) if p.get("cards")]
        packs = [p for p in full if types is None or (p.get("type") or packtypes.DEFAULT) in types]
        if not packs:
            continue
        info = dict(info, paid=info.get("paid") if len(packs) == len(full) else 0)
        out.append(dict(s, packs=packs, info=info, stats=session_stats(packs, info)))
    return out


# ---------- Building blocks (data only) ----------
class Signal:
    """Like a Qt signal, but without QObject: connect(fn), emit(…)."""

    def __init__(self):
        self._fns = []

    def connect(self, fn):
        self._fns.append(fn)

    def emit(self, *args):
        for fn in list(self._fns):
            fn(*args)

    def connected(self):
        return bool(self._fns)


class _Sized:
    """Height for rendering (instead of widget size)."""
    h = 260
    tip = ""

    def setMinimumHeight(self, h):
        self.h = h

    def setFixedHeight(self, h):
        self.h = h

    def minimumHeight(self):
        return self.h

    def setToolTip(self, t):
        self.tip = t


class Card(_Sized):
    """Chart tile with title and optional toggle (modes). picked(i): click on an entry."""

    def __init__(self, title, sub=""):
        self.title, self.sub, self.fmt = title, sub, None
        self.modes, self.mode, self.on_mode = [], 0, None
        self.picked = Signal()
        self.h = 260

    def set_modes(self, labels, mode=0, on_mode=None):
        """Toggle at the top right of the header (e.g. "Total · per pack")."""
        self.modes, self.mode, self.on_mode = list(labels), mode if mode < len(labels) else 0, on_mode

    def _clickable(self):
        return self.picked.connected()

    def restart(self):
        """Formerly: restart the build-up animation – Qt Quick now does that by itself on new data."""


class KpiRow(_Sized):
    """Key-figure tiles: [(title, value (number), formatter, color, extra)]."""

    def __init__(self):
        self.items, self.h = [], 96

    def set_items(self, items):
        self.items = items


class SessionBars(Card):
    """Value per session (bars), spend as a line with dots."""

    def __init__(self):
        super().__init__(tr("Value per log"), tr("bars = card value · line = spent"))
        self.raw, self.data = [], []
        self.keys = ["total", "pack", "euro"]
        self.set_modes([tr("Total"), tr("per pack"), tr("per € spent")], on_mode=lambda _: self._derive())

    def set_data(self, sessions):
        self.raw = [(s.get("started", 0), s["stats"]["total"], s["stats"].get("paid") or 0,
                     s["info"].get("title") or s["info"].get("product") or "", s["stats"].get("packs") or 0)
                    for s in sessions[-24:]]
        # "per pack" only when there are booster sessions (scanning cards has no packs)
        keys = ["total", "pack", "euro"] if any(k for *_, k in self.raw) else ["total", "euro"]
        if keys != self.keys:
            cur = self.keys[self.mode] if self.mode < len(self.keys) else "total"
            labels = {"total": tr("Total"), "pack": tr("per pack"), "euro": tr("per € spent")}
            self.keys = keys
            self.set_modes([labels[k] for k in keys], keys.index(cur) if cur in keys else 0, self.on_mode)
        self._derive()

    def _derive(self):
        """Total: value/spend · per pack: both divided by the packs · per € spent: card value per euro paid
        (line at 1 = break-even; only sessions with spend)."""
        key = self.keys[self.mode] if self.mode < len(self.keys) else "total"
        if key == "pack":
            self.data = [(ts, v / k, paid / k, title) for ts, v, paid, title, k in self.raw if k]
        elif key == "euro":
            self.data = [(ts, v / paid, 1.0, title) for ts, v, paid, title, k in self.raw if paid]
        else:
            self.data = [(ts, v, paid, title) for ts, v, paid, title, k in self.raw]


class Cumulative(Card):
    """Cumulative over time: card value (area) and spending (line)."""

    def __init__(self):
        super().__init__(tr("Value vs. spending over time"), tr("cumulative"))
        self.pts, self.series = [], ([], [])

    def set_data(self, sessions, now=None):
        """now: {session ID: today's card value} – enables the "when opened · today" toggle."""
        out = ([], [])
        for k in (0, 1):
            tot = paid = 0.0
            pts = [(0, 0.0, 0.0)] if sessions else []
            for s in sessions:
                v = s["stats"]["total"] if k == 0 or not now else now.get(s["id"], s["stats"]["total"])
                tot += v
                paid += s["stats"].get("paid") or 0
                pts.append((s.get("started", 0), tot, paid))
            out[k].extend(pts)
        self.series = out
        self.set_modes([tr("when opened"), tr("today")] if now else [], self.mode if now else 0,
                       on_mode=lambda _: self._pick())
        self._pick()

    def _pick(self):
        self.pts = self.series[self.mode] if self.series[self.mode] else self.series[0]


class Donut(Card):
    """Donut with shares, legend, key figure in the centre."""

    def __init__(self, title, unit=None):
        super().__init__(title)
        self.parts, self.total = [], 0
        self.center, self.center_fmt, self.center_label, self.center_color = 0.0, str, "", PINK
        self.unit = unit or tr("Cards")

    def set_parts(self, parts, center=0.0, center_fmt=lambda v: f"{v:.0f} %", center_label="", center_color=PINK):
        """parts: [(label, count, color)]"""
        self.parts = [x for x in parts if x[1]]
        self.total = sum(n for _, n, _ in self.parts)
        self.center, self.center_fmt, self.center_label = center, center_fmt, center_label
        self.center_color = center_color


class RarityDonut(Donut):
    def __init__(self):
        super().__init__(tr("Rarities"))

    def set_data(self, rarity, foil):
        parts = [(label, rarity.get(key, 0), col) for key, label, col in RARITY_COLORS]
        total = sum(rarity.values()) or 1
        self.sub = tr(f"{sum(rarity.values())} cards")
        self.set_parts(parts, foil / total * 100, center_label=tr("Foil"))


class HBars(Card):
    """Horizontal bars (top pulls, sets): [(label, value, extra)]."""

    def __init__(self, title, color=CYAN, money=True):
        super().__init__(title)
        self.rows, self.color, self.money = [], color, money

    def set_rows(self, rows):
        self.rows = rows


class Histogram(Card):
    """Distribution of values (default: pack values)."""

    def __init__(self, title=None, sub=None, unit=None, per=None, edges=None):
        super().__init__(title or tr("Pack values"), sub or tr("how many packs in which value range"))
        self.unit, self.per = unit or tr("Packs"), per or tr("€ per pack")
        self.base_edges = edges or [0, 1, 2, 3, 5, 7.5, 10, 15, 20, 30, 50, float("inf")]
        self.bins, self.edges, self.avg = [], [], 0.0

    def set_data(self, values):
        self.bins, self.edges = [], []
        if values:
            edges = list(self.base_edges)
            top = max(values)
            while len(edges) > 3 and edges[-2] > top * 1.2:
                edges.pop(-2)
            self.edges = edges
            self.bins = [sum(1 for v in values if edges[i] <= v < edges[i + 1]) for i in range(len(edges) - 1)]
            self.avg = sum(values) / len(values)
            self.sub = f"{len(values)} {self.unit}"

    def _label(self, i):
        a, b = self.edges[i], self.edges[i + 1]
        if b == float("inf"):
            return f"{a:g}+"
        return f"{a:g}–{b:g}"
