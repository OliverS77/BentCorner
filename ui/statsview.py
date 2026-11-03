"""Stats with hierarchy: three tabs (Sessions · Trade · Collection), each with one big key statement at the top
(number + sentence with context), four key figures below and numbered sections that each answer a question
("01 Is opening worth it?"). Data only (no widget): everything is shown by qstats.py in Qt Quick,
the charts via qcharts/ChartView.

Sessions:   balance, value per session, value vs. spending, pack types, pack values, rarities, highlights and a
            single session in detail (pack by pack).
Trade:      trade stock and its value, what's missing from the wishlist and who has it, which friend fits best.
Collection: value, composition (rarity, language, sets), where the value lies.
"""
import time

from cards import carddb
from collection import collection as coll_mod
from collection import decks
from cards import packtypes
from collection import trade
from scanner import core
from ui.charts import (AMBER, CYAN, GREEN, INK, MUTED, PINK, RED, RARITY_COLORS, Card, Cumulative, Donut, HBars,
                    Histogram, KpiRow, RarityDonut, SessionBars, _Sized, filter_sessions, summarize)
from system.i18n import tr
from collection import alarms as alarms_mod

LANG_COLORS = ["#62f2ff", "#ff5bd6", "#ffb347", "#46d17a", "#c08cff", "#ff8a3d", "#8fb6ff", "#e7c35a", "#aab1c8"]
LANG_NAMES = {"en": "Englisch", "de": "Deutsch", "ja": "Japanisch", "fr": "Französisch", "it": "Italienisch",
              "es": "Spanisch", "pt": "Portugiesisch", "ru": "Russisch", "ko": "Koreanisch", "zhs": "Chinesisch (vereinf.)",
              "zht": "Chinesisch (trad.)", "ph": "Phyrexianisch", "th": "Thai", "id": "Indonesisch"}


def _singles_fact(fmt):
    """Trades & purchases (single-card sessions): cards, value, spending."""
    from collection import sessions
    ss = [x for x in sessions.load_all() if sessions.is_singles(x) and x["stats"]["cards"]]
    cards = sum(x["stats"]["cards"] for x in ss)
    value = sum(x["stats"]["total"] for x in ss)
    paid = sum(x["stats"].get("paid") or 0 for x in ss)
    return (tr("Trades & purchases"), tr(f"{cards} cards · {fmt(value)}") + (tr(f" · paid {fmt(paid)}") if paid else ""))


def _one(template, n):
    """"In <b>1</b> log …" instead of "… logs" (its own text with its own German, like the web's st_say_*1)."""
    return template.replace("In <b>{n}</b> logs", "In <b>1</b> log") if n == 1 else template


def _pct(v):
    return ("+" if v >= 0 else "−") + f"{abs(v):.0f} %"


# ---------- building blocks ----------

def _fin(entry):
    """Suffix " · Reverse Holo", " · Foil" … after the name (finish per game, finishes.py) – "" for the plain one."""
    from cards import finishes
    try:
        lb = finishes.full_label(entry) if entry.get("id") else ("Foil" if entry.get("foil") else "")
    except Exception:  # noqa: BLE001
        lb = "Foil" if entry.get("foil") else ""
    return f" · {tr(lb)}" if lb else ""

class Hero(_Sized):
    """A tab's key statement: small heading, big number, a sentence with context – brief facts on the right."""

    def __init__(self):
        self.kicker, self.sentence, self.facts = "", "", []
        self._value, self._fmt, self._color = 0.0, str, INK
        self.h = 170

    def set_content(self, kicker, value, fmt, color, sentence, facts):
        """facts: [(label, value text)]"""
        self.kicker = kicker.upper()
        self._value, self._fmt, self._color = value, fmt, color
        self.sentence, self.facts = sentence, list(facts)


class SectionHead(_Sized):
    """Section header: number · question, below it a sentence on what it's about."""

    def __init__(self, number, question, note=""):
        self.number, self.question, self.note = number, question, note
        self.h = 54 if note else 34


class PackBars(Card):
    """One session pack by pack: bar per pack, hit packs highlighted, line = your average per pack."""

    def __init__(self):
        super().__init__(tr("Pack by pack"), tr("Line = your average across all logs"))
        self.rows, self.avg, self.hit = [], 0.0, 10.0

    def set_data(self, rows, avg, hit):
        """rows: [(value, best card, price of the best)]"""
        self.rows, self.avg, self.hit = rows, avg, hit


# ---------- page ----------
class StatsPage:
    """Stats (tabs Sessions · Trade · Collection) as data. layout(tab) describes the arrangement."""
    TABS = (("sessions", "Logs"), ("trade", "Tausch"), ("collection", "Sammlung"))

    def __init__(self, fmt=None, settings=None, on_save=None, price_now=None, ctrl=None):
        self.fmt = fmt or (lambda v: f"{v:.2f} €".replace(".", ","))
        self.settings = settings if settings is not None else {}
        self.on_save, self.price_now, self.ctrl = on_save or (lambda: None), price_now or (lambda ids: {}), ctrl
        self.all, self.dirty = [], {"trade": True, "collection": True}
        self.filtered, self.tags_all, self.types_present = [], [], []
        self.filter_text, self.filter_note, self.pick_sid, self.pick_options = "", "", None, []
        # pack figures only from opening boosters (sessions.counts_for_packs): any such session at all (pack-type
        # filter) · any after the filter (pack charts) · the session in detail is one (pack by pack)
        self.has_packs, self.packs_on, self.detail_packs = False, False, False
        self.listeners = []  # fn() after new data (Qt Quick page)
        # Sessions
        self.s_hero, self.s_kpis = Hero(), KpiRow()
        self.s_bars, self.s_cum = SessionBars(), Cumulative()
        self.s_types = HBars(tr("Avg. value per pack by type"), CYAN)
        self.s_types.sub = tr("Hover: today and change")
        self.s_hist, self.s_rarity = Histogram(), RarityDonut()
        self.s_sets = HBars(tr("Avg. value per pack by set"), CYAN)
        self.s_sets.sub = tr("Sets with at least 2 packs")
        self.s_pulls = HBars(tr("Top pulls"), PINK)
        self.s_best = HBars(tr("Strongest logs"), GREEN)
        self.s_best.sub = tr("by card value")
        for c in (self.s_pulls, self.s_best):
            c.setMinimumHeight(340)
        self.s_one_kpis, self.s_packs = KpiRow(), PackBars()
        self.s_one_pulls = HBars(tr("Best cards of this log"), PINK)
        # Trade
        self.t_hero, self.t_kpis = Hero(), KpiRow()
        self.t_friends = HBars(tr("You get from …"), GREEN)
        self.t_friends.sub = tr("Hover: what you give for it")
        self.t_missing = HBars(tr("Most expensive missing cards"), AMBER)
        self.t_missing.setMinimumHeight(340)
        self.t_where = Donut(tr("Where can you get them?"))
        self.t_top = HBars(tr("Most valuable trade cards"), CYAN)
        self.t_top.setMinimumHeight(340)
        self.t_rarity = Donut(tr("Trade cards by rarity"))
        # Collection
        self.c_hero, self.c_kpis = Hero(), KpiRow()
        self.c_rarity, self.c_langs = Donut(tr("Rarities")), Donut(tr("Languages"))
        self.c_sets = HBars(tr("Cards per set"), CYAN, money=False)
        self.c_top = HBars(tr("Most valuable cards"), PINK)
        self.c_top.setMinimumHeight(340)
        self.c_hist = Histogram(tr("Card values"), tr("how many cards in which value range"),
                                unit=tr("Cards"), per=tr("€ per card"),
                                edges=[0, 0.5, 1, 2, 5, 10, 20, 50, 100, float("inf")])
        self.c_setval = HBars(tr("Value per set"), GREEN)
        self.c_value = None   # value history (valuehist, computed in the background) – tile for ChartView
        self.tab = "sessions"
        self.show_tab(self.settings.get("stats_tab") or "sessions", save=False)

    def layout(self, tab):
        """Arrangement of a tab: [("hero", H) | ("kpis", K) | ("section", n, question, sentence) | ("full", chart) |
        ("pair", chart, chart) | ("pick",)]."""
        if tab == "trade":
            return [("hero", self.t_hero), ("kpis", self.t_kpis),
                    ("section", 1, tr("Who matches you?"),
                     tr("Per friend: what you could get (your wants) and what they want from you.")),
                    ("full", self.t_friends),
                    ("section", 2, tr("What are you still missing?"),
                     tr("Wishlist (and missing deck cards) – and where to get them.")),
                    ("pair", self.t_missing, self.t_where),
                    ("section", 3, tr("What can you offer?"), tr("Your cards marked for trade.")),
                    ("pair", self.t_top, self.t_rarity)]
        if tab == "collection":
            value = [("section", 1, tr("How is the value developing?"),
                      tr("The last 90 days: each card from the day you own it (log date). Dashed: your oldest cards without additions – pure price development.")),
                     ("raw", self.c_value)] if self.c_value else []
            o = 1 if value else 0   # section numbers move up
            return [("hero", self.c_hero), ("kpis", self.c_kpis)] + value + [
                    ("section", 1 + o, tr("What is your collection made of?"), tr("Rarities, languages and the biggest sets.")),
                    ("pair", self.c_rarity, self.c_langs), ("full", self.c_sets),
                    ("section", 2 + o, tr("Where is the value?"),
                     tr("The most valuable cards and how the value is spread.")),
                    ("pair", self.c_top, self.c_hist), ("full", self.c_setval)]
        if not self.packs_on:   # only scanning cards: no pack figures, no pack charts
            return [("hero", self.s_hero), ("kpis", self.s_kpis),
                    ("section", 1, tr("Is it worth it?"),
                     tr("Card value vs. what you paid – per log and over time.")),
                    ("full", self.s_bars), ("pair", self.s_cum, self.s_rarity),
                    ("section", 2, tr("What were the highlights?"), tr("The best cards and the strongest logs.")),
                    ("pair", self.s_pulls, self.s_best),
                    ("section", 3, tr("One log in detail"), tr("Its best cards – and how it compares.")),
                    ("pick",), ("kpis", self.s_one_kpis), ("full", self.s_one_pulls)]
        detail = ("pair", self.s_packs, self.s_one_pulls) if self.detail_packs else ("full", self.s_one_pulls)
        return [("hero", self.s_hero), ("kpis", self.s_kpis),
                ("section", 1, tr("Is opening worth it?"),
                 tr("Card value when opened vs. what you paid – per log and over time.")),
                ("full", self.s_bars), ("pair", self.s_cum, self.s_types),
                ("section", 2, tr("What's in the packs?"),
                 tr("How the packs are spread and which rarities they contain.")),
                ("pair", self.s_hist, self.s_rarity), ("full", self.s_sets),
                ("section", 3, tr("What were the highlights?"), tr("The best cards and the strongest logs.")),
                ("pair", self.s_pulls, self.s_best),
                ("section", 4, tr("One log in detail"),
                 tr("Pack by pack – and how it compares to your average.") if self.detail_packs else
                 tr("Its best cards – and how it compares.")),
                ("pick",), ("kpis", self.s_one_kpis), detail]

    def _notify(self):
        for fn in list(self.listeners):
            fn()

    # --- tabs ---
    def show_tab(self, key, save=True):
        if key not in dict(self.TABS):
            key = "sessions"
        self.tab = key
        if save:
            self.settings["stats_tab"] = key
            self.on_save()
        if key == "trade" and self.dirty["trade"]:
            self.update_trade()
        elif key == "collection" and self.dirty["collection"]:
            self.update_collection()
        self._notify()

    # --- filter (Sessions) ---
    def selection(self):
        f = self.settings.get("stats_filter") or {}
        types = f.get("types")
        if types is None:  # default: only types that count as a pack
            types = [t["key"] for t in packtypes.types(self.settings) if t["counts"]]
        return set(types), list(f.get("tags") or [])

    def store(self, types, tags):
        self.settings["stats_filter"] = {"types": sorted(types), "tags": list(tags)}
        self.on_save()
        self.update_sessions()

    def reset_filter(self):
        self.settings.pop("stats_filter", None)
        self.on_save()
        self.update_sessions()

    def type_toggled(self, key, on):
        types, tags = self.selection()
        (types.add if on else types.discard)(key)
        self.store(types, tags)

    def tag_toggled(self, tag, on):
        types, tags = self.selection()
        tags = [t for t in tags if t != tag] + ([tag] if on else [])
        self.store(types, tags)

    def tags_picked(self, picked):
        types, _ = self.selection()
        self.store(types, picked)

    # --- data ---
    def set_sessions(self, all_sessions):
        self.all = all_sessions
        self.dirty = {"trade": True, "collection": True}
        self.update_sessions()
        if self.tab == "trade":
            self.update_trade()
        elif self.tab == "collection":
            self.update_collection()

    def _now_prices(self, sessions):
        from ui.charts import _sid
        ids = {_sid(c["id"]) for s in sessions for p in s["packs"] for c in p["cards"] if c.get("id")}
        try:
            return self.price_now(ids) or {}
        except Exception:
            return {}

    @staticmethod
    def _card_now(c, prices):
        from ui.charts import _sid
        pr = prices.get(_sid(c.get("id")))
        if not pr:
            return c.get("price") or 0
        eur_n, eur_f = pr
        val = eur_f if c.get("foil") else eur_n
        if val is None:
            val = eur_n if eur_n is not None else eur_f
        return val if val is not None else (c.get("price") or 0)

    def update_sessions(self):
        from collection import sessions
        fmt = self.fmt
        types_sel, tags_sel = self.selection()
        known = packtypes.by_key(self.settings)
        pk_all = [s for s in self.all if sessions.counts_for_packs(s)]   # opening boosters: the pack figures
        rest = [s for s in self.all if not sessions.counts_for_packs(s)]  # scanning cards: one list, no pack types
        self.has_packs = bool(pk_all)
        present = []
        for sess in pk_all:
            for pk in sess.get("packs", []):
                k = pk.get("type") or packtypes.DEFAULT
                if pk.get("cards") and k not in present:
                    present.append(k)
        order = [t["key"] for t in packtypes.types(self.settings)]
        present.sort(key=lambda k: order.index(k) if k in order else 99)
        self.types_present = [(k, tr(known[k]["name"]) if k in known else k,
                               tr("counts as pack") if packtypes.counts(self.settings, k) else
                               tr("doesn't count as a pack by default")) for k in present]
        self.tags_all = packtypes.all_tags(self.all)
        self.filter_note = (tr("Without a selected tag all logs count; with tags only logs that have one of them.")
                            if self.tags_all else tr("You assign tags in the stream info (Scan) or under “Logs & stats” – e.g. “Convention” or “Local game store”."))
        type_names = [tr(known[k]["name"]) if k in known else k for k in present if k in types_sel]
        if self.has_packs:
            summary = tr("Filter: ") + (", ".join(type_names) if type_names else tr("no types"))
            if tags_sel:
                summary += "  ·  " + ", ".join(tags_sel)
        else:   # no pack types to pick – only tags
            summary = tr("Filter: ") + (", ".join(tags_sel) if tags_sel else tr("all logs"))
        self.filter_text = summary + "  ▾"

        sig = (sorted(types_sel), list(tags_sel), self.settings.get("hit"),
               [(s["id"], s["stats"]["cards"], round(s["stats"]["total"], 2), (s.get("info") or {}).get("paid"),
                 (s.get("info") or {}).get("title"), (s.get("info") or {}).get("kind")) for s in self.all])
        if sig == getattr(self, "_sig_s", None):
            self._notify()
            return
        self._sig_s = sig
        pdata = filter_sessions(pk_all, types_sel, tags_sel)   # the pack type filter only applies to packs
        data = pdata + filter_sessions(rest, None, tags_sel)
        self.filtered = data
        self.packs_on = bool(pdata)
        d, dp = summarize(data), summarize(pdata)   # dp: pack figures (Ø per pack, hit rate, pack values, sets)
        for c in (self.s_bars, self.s_cum, self.s_types, self.s_hist, self.s_rarity, self.s_sets, self.s_pulls,
                  self.s_best, self.s_packs, self.s_one_pulls):
            c.fmt = fmt
        n = len(d["sessions"])
        hit = float(self.settings.get("hit") or 10)
        prices = self._now_prices(data)
        now = sum(self._card_now(c, prices) for s in data for p in s["packs"] for c in p["cards"]) if prices else None
        change = (now / d["total"] - 1) * 100 if d["total"] and now is not None else None
        avg = dp["total"] / dp["packs"] if dp["packs"] else 0.0
        packs_hit = sum(1 for s in pdata for p in s["packs"] if p["cards"] and
                        max((c.get("price") or 0) for c in p["cards"]) >= hit)
        rate = packs_hit / dp["packs"] * 100 if dp["packs"] else 0.0
        cards_hit = sum(1 for s in data for p in s["packs"] for c in p["cards"] if (c.get("price") or 0) >= hit)
        best = d["pulls"][0] if d["pulls"] else None
        # key statement
        if not n:
            self.s_hero.set_content(tr("Logs"), tr("No logs yet"), str, MUTED,
                                    tr("As soon as you scan cards, you'll see how it's going here: value, balance, highlights."), [])
        elif d["paid"]:
            profit = d["paid_total"] - d["paid"]
            ratio = d["paid_total"] / d["paid"] * 100 - 100
            self.s_hero.set_content(
                tr("Balance"), abs(profit), lambda v, s=profit: ("+" if s >= 0 else "−") + fmt(v),
                GREEN if profit >= 0 else RED,
                (tr(_one("In <b>{n}</b> logs you opened <b>{packs}</b> packs and pulled cards worth <b>{value}</b>. Where you entered what you paid, that is ", n))
                 if self.packs_on else
                 tr(_one("In <b>{n}</b> logs you scanned <b>{cards}</b> cards worth <b>{value}</b>. Where you entered what you paid, that is ", n)))
                .format(n=n, packs=d["packs"], cards=d["cards"], value=fmt(d["total"])) +
                (f"<b style='color:{GREEN if ratio >= 0 else RED}'>{_pct(ratio)}</b> " +
                 (tr("more than you paid.") if ratio >= 0 else tr("less than you paid."))),
                self._session_facts(d, now, change, best))
        else:
            self.s_hero.set_content(
                tr("Value pulled"), d["total"], fmt, CYAN,
                (tr(_one("In <b>{n}</b> logs you opened <b>{packs}</b> packs with <b>{cards}</b> cards. Enter what you paid "
                         "in the log (scan page: the Log tile, or here in the list) – then your balance shows up here.", n))
                 if self.packs_on else
                 tr(_one("In <b>{n}</b> logs you scanned <b>{cards}</b> cards. Enter what you paid in the log (scan "
                         "page: the Log tile, or here in the list) – then your balance shows up here.", n)))
                .format(n=n, packs=d["packs"], cards=d["cards"]),
                self._session_facts(d, now, change, best))
        first = [
            (tr("Ø per pack"), avg, fmt, CYAN, tr(f"across {dp['packs']} packs")),
            (tr("Hit rate"), rate, lambda v: f"{v:.0f} %", PINK,
             tr(f"{packs_hit} packs with a card worth {fmt(hit)}+")),
        ] if self.packs_on else [   # no packs: per card instead of per pack
            (tr("Ø per card"), d["total"] / d["cards"] if d["cards"] else 0.0, fmt, CYAN, tr(f"{d['cards']} cards")),
            (tr("Hits"), cards_hit, lambda v: str(round(v)), PINK, tr("cards worth {value}+").format(value=fmt(hit))),
        ]
        self.s_kpis.set_items(first + [
            (tr("Value today"), now if now is not None else "–", fmt if now is not None else str,
             (GREEN if (change or 0) >= 0 else RED) if change is not None else MUTED,
             (_pct(change) + tr(" since opening")) if change is not None else tr("needs the card database")),
            (tr("Best pull"), best[0] if best else "–", fmt if best else str, AMBER, best[1] if best else ""),
        ])
        self.s_bars.set_data(d["sessions"])
        now_by = {s["id"]: sum(self._card_now(c, prices) for pk in s["packs"] for c in pk["cards"])
                  for s in data} if prices else None
        self.s_cum.set_data(d["sessions"], now_by)
        # per type (all types, tag filter applies)
        rows = {}
        all_t = filter_sessions(pk_all, None, tags_sel)
        prices_t = self._now_prices(all_t)
        for s in all_t:
            for p in s["packs"]:
                k = p.get("type") or packtypes.DEFAULT
                r = rows.setdefault(k, [0, 0.0, 0.0])
                r[0] += 1
                r[1] += sum(c.get("price") or 0 for c in p["cards"])
                r[2] += sum(self._card_now(c, prices_t) for c in p["cards"])
        type_rows = []
        for k, (np_, then, nowv) in sorted(rows.items(), key=lambda kv: -kv[1][1] / kv[1][0]):
            ch = (nowv / then - 1) * 100 if then and prices_t else None
            extra = tr(f"{np_} packs · today avg. {fmt(nowv / np_)}") + (f" ({_pct(ch)})" if ch is not None else "")
            type_rows.append((tr(known[k]["name"]) if k in known else k, then / np_, extra))
        self.s_types.set_rows(type_rows[:8])
        self.s_hist.set_data(dp["pack_values"])
        self.s_rarity.set_data(d["rarity"], d["foil"])
        sets = {}
        for s in pdata:
            for p in s["packs"]:
                if not p["cards"]:
                    continue
                codes = [(c.get("set") or "?").upper() for c in p["cards"]]
                code = max(set(codes), key=codes.count)
                e = sets.setdefault(code, [0, 0.0])
                e[0] += 1
                e[1] += sum(c.get("price") or 0 for c in p["cards"])
        set_rows = [(code, tot / k, tr(f"{k} packs · total {fmt(tot)}")) for code, (k, tot) in sets.items() if k >= 2]
        self.s_sets.set_rows(sorted(set_rows, key=lambda r: -r[1])[:10])
        self.s_pulls.set_rows([(name + (_fin(foil) if isinstance(foil, dict) else (" ✦" if foil else "")), price,
                                f"{code} · {time.strftime('%d.%m.%Y', time.localtime(ts))}")
                               for price, name, code, ts, foil in d["pulls"][:10]])
        best_s = sorted(d["sessions"], key=lambda s: -s["stats"]["total"])[:8]
        self.s_best.set_rows([(self._session_label(s, short=True), s["stats"]["total"],
                               tr(f"{s['stats']['packs']} packs · avg. {fmt(s['stats']['avg_pack'])}") if s["stats"]["packs"]
                               else tr(f"{s['stats']['cards']} cards"))
                              for s in best_s])
        # session selection
        self.pick_options = [(s["id"], self._session_label(s) + f"   ·   {fmt(s['stats']['total'])}")
                             for s in sorted(data, key=lambda s: -s.get("started", 0))]
        if self.pick_sid not in [k for k, _ in self.pick_options]:
            self.pick_sid = self.pick_options[0][0] if self.pick_options else None
        self._overall_avg = avg
        self.show_session_detail()

    def _session_facts(self, d, now, change, best):
        fmt = self.fmt
        facts = ([(tr("Logs"), str(len(d["sessions"])))] + ([(tr("Packs"), str(d["packs"]))] if self.packs_on else [])
                 + [(tr("Cards"), str(d["cards"]))])
        if d["sessions"]:
            first = time.strftime("%m/%Y", time.localtime(d["sessions"][0].get("started", 0)))
            facts.append((tr("Since"), first))
        return facts

    @staticmethod
    def _session_label(s, short=False):
        info = s.get("info") or {}
        date = time.strftime("%d.%m.%Y" if not short else "%d.%m.%y", time.localtime(s.get("started", 0)))
        title = info.get("title") or info.get("product") or ""
        return f"{date}  {title}".strip()

    def pick_session(self, sid):
        self.pick_sid = sid
        self.show_session_detail()

    def show_session_detail(self):
        sid = self.pick_sid
        s = next((x for x in getattr(self, "filtered", []) if x["id"] == sid), None)
        fmt = self.fmt
        self.detail_packs = s is not None and core.has_packs(s.get("info"))
        if s is None:
            self.s_one_kpis.set_items([])
            self.s_packs.set_data([], 0, 10)
            self.s_one_pulls.set_rows([])
            self._notify()
            return
        hit = float(self.settings.get("hit") or 10)
        rows = []
        cards = []
        for p in s["packs"]:
            if not p["cards"]:
                continue
            best = max(p["cards"], key=lambda c: c.get("price") or 0)
            rows.append((sum(c.get("price") or 0 for c in p["cards"]), best.get("name"), best.get("price")))
            cards += p["cards"]
        st = s["stats"]
        overall = getattr(self, "_overall_avg", 0.0)
        if self.detail_packs:   # opening boosters: pack by pack, Ø per pack vs. your average
            avg = st["avg_pack"]
            vs = (avg / overall - 1) * 100 if overall else None
            hits = sum(1 for r in rows if (r[2] or 0) >= hit)
            first = [
                (tr("Value"), st["total"], fmt, CYAN, tr(f"{st['packs']} packs · {st['cards']} cards")),
                (tr("Ø per pack"), avg, fmt, (GREEN if (vs or 0) >= 0 else RED) if vs is not None else INK,
                 (_pct(vs) + tr(" vs. your average")) if vs is not None else ""),
                (tr("Hits"), hits, lambda v: str(round(v)), PINK, tr(f"Packs with a card worth {fmt(hit)}+")),
            ]
        else:                   # scanning cards: one list – value, Ø per card, hits per card
            hits = sum(1 for c in cards if (c.get("price") or 0) >= hit)
            first = [
                (tr("Value"), st["total"], fmt, CYAN, tr(f"{st['cards']} cards")),
                (tr("Ø per card"), st["total"] / st["cards"] if st["cards"] else 0.0, fmt, INK, ""),
                (tr("Hits"), hits, lambda v: str(round(v)), PINK, tr("cards worth {value}+").format(value=fmt(hit))),
            ]
        self.s_one_kpis.set_items(first + [
            (tr("Balance"), abs(st["profit"]) if st.get("profit") is not None else "–",
             (lambda v, p=st.get("profit"): ("+" if p >= 0 else "−") + fmt(v)) if st.get("profit") is not None else str,
             (GREEN if st["profit"] >= 0 else RED) if st.get("profit") is not None else MUTED,
             tr("Stake ") + fmt(st["paid"]) if st.get("paid") else tr("no spending entered")),
        ])
        self.s_packs.set_data(rows if self.detail_packs else [], overall, hit)
        from collection import share   # copies of the same card once: "4× Lightning Bolt" (03.11.)
        top = share.grouped(sorted((c for c in cards if c.get("price")), key=lambda c: -c["price"]))[:8]
        self.s_one_pulls.set_rows([((f"{c['n']}× " if c["n"] > 1 else "") + c.get("name", "?") + _fin(c), c["price"],
                                    f"{(c.get('set') or '').upper()} · {(c.get('rarity') or '').capitalize()}")
                                   for c in top])
        self._notify()

    # --- Trade ---
    def _collection_items(self):
        c = getattr(self.ctrl, "collection", None)
        return list(c.items) if c is not None else []

    def update_trade(self):
        self.dirty["trade"] = False
        fmt = self.fmt
        items = self._collection_items()
        owned = {}
        for it in items:
            owned[it["name"]] = owned.get(it["name"], 0) + int(it.get("count", 1))
        # what I want: wishlist + (if enabled) missing deck cards
        want = {}
        for w in trade.wishes():
            want[w["name"]] = want.get(w["name"], 0) + int(w.get("count", 1))
        if self.settings.get("wish_decks", True):
            try:
                dl = decks.load()
                sids = {c["sid"] for d in dl for c in d.get("cards") or []} | \
                    {s for d in dl for s in d.get("commanders") or []}
                rows = carddb.cards_by_ids(sids) if carddb.exists() else {}
                for name, e in trade.deck_needs(dl, rows, owned).items():
                    want[name] = max(want.get(name, 0), e["need"])
            except Exception:
                pass
        friends = trade.friends()
        sig = (want, [(d["id"], d.get("name"), len(d.get("cards") or []), len(d.get("wants") or [])) for d in friends],
               [(it.get("name"), it.get("count"), it.get("trade"), coll_mod.price(it)) for it in items],
               len(alarms_mod.alarms(self.settings)))
        if sig == getattr(self, "_sig_t", None):
            self._notify()
            return
        self._sig_t = sig
        missing = {n: max(0, k - owned.get(n, 0)) for n, k in want.items()}
        missing = {n: k for n, k in missing.items() if k > 0}
        names = set(missing) | {w[0] for d in friends for w in d.get("wants") or []}
        db = carddb.by_names(list(names)) if carddb.exists() and names else {}
        price = {}
        for n in names:
            r = db.get(n.lower())
            if r:
                price[n] = r.get("eur") if r.get("eur") is not None else r.get("eur_foil")
        holders = trade.holders({d["id"] for d in friends})
        # trade stock
        tradeable = trade.have_items(items)  # all own lists, merged
        t_value = sum((coll_mod.price(it) or 0) * n for it, n in tradeable)
        t_count = sum(n for _, n in tradeable)
        miss_value = sum((price.get(n) or 0) * k for n, k in missing.items())
        avail = {n: k for n, k in missing.items() if holders.get(n)}
        avail_value = sum((price.get(n) or 0) * k for n, k in avail.items())
        alarms = alarms_mod.alarms(self.settings)   # only the open game
        hits = sum(1 for a in alarms if a.get("hit"))
        # per friend
        friend_rows = []
        for d in friends:
            res = trade.proposal(items, missing, d, owned, price, tradeable)
            if res["get"] or res["give"]:
                friend_rows.append((d.get("name") or "?", res["get_sum"],
                                    tr(f"{sum((n for _, n, _ in res['get']))} cards · you give {fmt(res['give_sum'])} ({sum((n for _, n, _ in res['give']))} cards)")))
        friend_rows.sort(key=lambda r: -r[1])
        best_friend = friend_rows[0] if friend_rows else None
        # key statement
        if not t_count and not missing and not friends:
            self.t_hero.set_content(tr("Trade"), tr("Nothing to trade yet"), str, MUTED,
                                    tr("Mark cards for trade in the “Orbit” tab, put cards on your wishlist or import a friend's list – then you'll see here what fits together."), [])
        else:
            sent = tr(f"You marked <b>{t_count}</b> cards for trade. ")
            if missing:
                sent += tr(f"You're missing <b>{sum(missing.values())}</b> cards worth about <b>{fmt(miss_value)}</b>")
                sent += (tr(f" – your friends have <b>{sum(avail.values())}</b> of them worth about <b>{fmt(avail_value)}</b>.") if avail else tr("."))
            if best_friend:
                sent += tr(f" Best match right now: <b>{best_friend[0]}</b>.")
            self.t_hero.set_content(
                tr("Trade stock"), t_value, fmt, CYAN, sent,
                [(tr("For trade"), str(t_count)), (tr("Fehlen dir"), str(sum(missing.values()))),
                 (tr("Friends"), str(len(friends))), _singles_fact(fmt), (tr("Price alerts"), f"{len(alarms)}" +
                                                      (f"  <span style='color:{AMBER}'>· {hits} "
                                                       + tr("triggered") + "</span>" if hits else ""))])
        self.t_kpis.set_items([
            (tr("Trade stock"), t_value, fmt, CYAN, tr(f"{t_count} cards marked")),
            (tr("Wishlist"), miss_value, fmt, AMBER, tr(f"{sum(missing.values())} cards missing")),
            (tr("At friends"), avail_value, fmt, GREEN, tr(f"{sum(avail.values())} of your missing cards")),
            (tr("Best partner"), best_friend[0] if best_friend else "–", str, INK,
             (tr("you get ") + fmt(best_friend[1])) if best_friend else tr("import a friend's list")),
        ])
        for c in (self.t_friends, self.t_missing, self.t_top):
            c.fmt = fmt
        self.t_friends.set_rows(friend_rows[:10])
        self.t_friends.setFixedHeight(max(150, 74 + 30 * len(friend_rows[:10])))
        miss_rows = sorted(((n, (price.get(n) or 0) * k, ", ".join(f"{nm} ({c}×)" for _, nm, _, c in holders.get(n, []))
                             or tr("none of your friends has it")) for n, k in missing.items()), key=lambda r: -r[1])
        self.t_missing.set_rows([r for r in miss_rows if r[1] > 0][:10])
        self.t_where.set_parts([(tr("at friends"), sum(avail.values()), GREEN),
                                (tr("missing everywhere"), sum(missing.values()) - sum(avail.values()), AMBER)],
                               center=sum(avail.values()) / max(1, sum(missing.values())) * 100,
                               center_label=tr("available"), center_color=GREEN)
        top = sorted(tradeable, key=lambda t: -(coll_mod.price(t[0]) or 0))[:10]
        self.t_top.set_rows([(it["name"] + _fin(it), (coll_mod.price(it) or 0) * n,
                              f"{n}× · {(it.get('set') or '').upper()}") for it, n in top])
        rar = {}
        for it, n in tradeable:
            r = it.get("rarity") or "common"
            rar[r] = rar.get(r, 0) + n
        self.t_rarity.set_parts([(label, rar.get(k, 0), col) for k, label, col in RARITY_COLORS],
                                center=t_count, center_fmt=lambda v: str(round(v)), center_label=tr("Cards"),
                                center_color=INK)
        self._notify()

    # --- Collection ---
    def update_collection(self):
        self.dirty["collection"] = False
        fmt = self.fmt
        items = self._collection_items()
        sig = [(it.get("name"), it.get("set"), it.get("count"), it.get("lang"), it.get("foil"), coll_mod.price(it))
               for it in items]
        if sig == getattr(self, "_sig_c", None):
            self._notify()
            return
        self._sig_c = sig
        total = n_cards = foils = 0
        unique = set()
        rar, langs, sets, setval, values = {}, {}, {}, {}, []
        best = None
        for it in items:
            k = int(it.get("count", 1))
            pr = coll_mod.price(it) or 0
            total += pr * k
            n_cards += k
            foils += k if it.get("foil") else 0
            unique.add(it.get("name"))
            r = it.get("rarity") or "common"
            rar[r] = rar.get(r, 0) + k
            lg = it.get("lang") or "en"
            langs[lg] = langs.get(lg, 0) + k
            code = (it.get("set") or "?").upper()
            sets[code] = sets.get(code, 0) + k
            setval[code] = setval.get(code, 0.0) + pr * k
            values += [pr] * k
            if pr and (best is None or pr > best[0]):
                best = (pr, it.get("name"), code, it.get("foil"))
        if not n_cards:
            self.c_hero.set_content(tr("Collection"), tr("Still empty"), str, MUTED,
                                    tr("Scan packs or import your collection – then you'll see here what it's worth and what it's made of."), [])
        else:
            top10 = sum(sorted(values, reverse=True)[:10])
            # "your ten most valuable cards" only when there are more than ten different ones (03.11.)
            self.c_hero.set_content(
                tr("Collection value"), total, fmt, CYAN,
                (tr(f"<b>{n_cards}</b> cards, <b>{len(unique)}</b> unique, from <b>{len(sets)}</b> sets. Your ten most valuable cards make up <b>{top10 / total * 100:.0f} %</b> of the value.")
                 if len(unique) > 10 else
                 tr(f"<b>{n_cards}</b> cards, <b>{len(unique)}</b> unique, from <b>{len(sets)}</b> sets."))
                if total else tr(f"<b>{n_cards}</b> cards from <b>{len(sets)}</b> sets."),
                [(tr("Card") if n_cards == 1 else tr("Cards"), str(n_cards)), (tr("Unique"), str(len(unique))),
                 (tr("Set") if len(sets) == 1 else tr("Sets"), str(len(sets))),
                 (tr("Foil") if foils == 1 else tr("Foils"), str(foils)),
                 (tr("Language") if len(langs) == 1 else tr("Languages"), str(len(langs)))])
        self.c_kpis.set_items([
            (tr("Avg. per card"), total / n_cards if n_cards else 0, fmt, CYAN, tr("across all cards")),
            (tr("Most valuable card"), best[0] if best else "–", fmt if best else str, PINK,
             best[1] if best else ""),
            (tr("Foil share"), foils / n_cards * 100 if n_cards else 0, lambda v: f"{v:.0f} %", AMBER,
             tr("1 foil") if foils == 1 else tr(f"{foils} foils")),
            (tr("Not English"), (n_cards - langs.get("en", 0)) / n_cards * 100 if n_cards else 0,
             lambda v: f"{v:.0f} %", GREEN, tr("1 language") if len(langs) == 1 else tr(f"{len(langs)} languages")),
        ])
        self.c_rarity.set_parts([(label, rar.get(k, 0), col) for k, label, col in RARITY_COLORS],
                                center=n_cards, center_fmt=lambda v: str(round(v)), center_label=tr("Cards"),
                                center_color=INK)
        lang_parts = sorted(langs.items(), key=lambda kv: -kv[1])
        self.c_langs.set_parts([(tr(LANG_NAMES.get(k, k.upper())), n, LANG_COLORS[i % len(LANG_COLORS)])
                                for i, (k, n) in enumerate(lang_parts[:8])],
                               center=len(langs), center_fmt=lambda v: str(round(v)), center_label=tr("Languages"),
                               center_color=INK)
        for c in (self.c_sets, self.c_top, self.c_hist, self.c_setval):
            c.fmt = fmt
        self.c_sets.set_rows([(code, k, "") for code, k in sorted(sets.items(), key=lambda kv: -kv[1])[:10]])
        top = sorted(items, key=lambda it: -(coll_mod.price(it) or 0))[:10]
        self.c_top.set_rows([(it["name"] + _fin(it), coll_mod.price(it) or 0,
                              f"{(it.get('set') or '').upper()} · {LANG_NAMES.get(it.get('lang') or 'en', '')}")
                             for it in top if coll_mod.price(it)])
        self.c_hist.set_data(values)
        self.c_setval.set_rows([(code, v, tr(f"{sets[code]} cards"))
                                for code, v in sorted(setval.items(), key=lambda kv: -kv[1])[:10] if v > 0])
        self._value_refresh(items)
        self._notify()

    def _value_refresh(self, items):
        """Recompute the value history (Magic only – it needs the price history), in the background."""
        from cards import valuehist
        if not items or not valuehist.available():
            self.c_value = None
            return

        def done(res):
            self.c_value = valuehist.chart_spec(res, h=300) if res else None
            self._notify()
        valuehist.compute_async(items, done)
