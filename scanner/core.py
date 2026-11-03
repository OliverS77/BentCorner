"""Card recognition and pack management (session, packs, cards) for app.py."""
import collections
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from scanner.common import BASE, features, lang_img, make_orb, prep

CARD_ASPECT = 63 / 88
# Memory against double counting: the last 2 counted cards. If one of them shows up again, it only counts once
# it has been gone this long (s) – short recognition dropouts (fingers, glare) do not count twice,
# real duplicates (two identical cards in a row) do.
RECENT_CARDS = 2
REAPPEAR_SECONDS = 1.5
# Spread the search over half as many cores as there are logical processors (2 to 12)
SEARCH_THREADS = max(2, min(12, (os.cpu_count() or 4) // 2))
# "Looks like a playing card": measured, cards have >= ~900 keypoints and > 2 % edges,
# an empty table/hand <= ~120 keypoints and < 0.5 % edges
GATE_KEYPOINTS = 300
GATE_EDGES = 0.01


def zone_rect(zone, fw, fh):
    """zone = (center x, center y, width) as fractions of the image size -> pixel rectangle."""
    cx, cy, wf = zone
    w = int(wf * fw)
    h = int(w / CARD_ASPECT)
    x, y = int(cx * fw - w / 2), int(cy * fh - h / 2)
    x, y = max(0, min(x, fw - w)), max(0, min(y, fh - h))
    return x, y, w, min(h, fh)


# ---------- Recognition ----------
class Matcher:
    def __init__(self, cards, pts, des, min_inliers):
        """pts/des: the features per card from library.load_library(). At least one card required."""
        self.cards, self.pts, self.des = cards, pts, des
        self.orb = make_orb(1000)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.min_inliers = min_inliers
        # LSH search index, split across several cores (measured with 2,143 cards: 12 shards 4.5x faster
        # than one index, same hit rate even with fingers/poor light). key_size 16 per shard is
        # enough because each shard holds only a fraction of the features, and it saves RAM.
        index = [i for i, d in enumerate(self.des) if len(d)]
        n = min(SEARCH_THREADS, max(1, len(index)))
        self.shards = []
        for k in range(n):
            part = index[k::n]
            fl = cv2.FlannBasedMatcher(dict(algorithm=6, table_number=8, key_size=16, multi_probe_level=1),
                                       dict(checks=32))
            fl.add([self.des[i] for i in part])
            fl.train()
            self.shards.append((fl, np.array(part)))
        self.pool = ThreadPoolExecutor(n, thread_name_prefix="suche")
        self._miss_thumb = None  # last image searched in vain (no card found)

    def close(self):
        self.pool.shutdown(wait=False)

    def _votes(self, qd):
        def one(shard):
            fl, part = shard
            v = np.zeros(len(self.des), np.int32)
            hits = [m[0].imgIdx for m in fl.knnMatch(qd, k=1) if m and m[0].distance < 55]
            np.add.at(v, part[hits], 1)
            return v
        return sum(self.pool.map(one, self.shards))

    def _verify(self, qp, qd, i):
        """Inliers for a single card (homography + RANSAC)."""
        good = [m[0] for m in self.bf.knnMatch(qd, self.des[i], k=2)
                if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
        if len(good) < 10:
            return 0
        _, mask = cv2.findHomography(qp[[m.queryIdx for m in good]], self.pts[i][[m.trainIdx for m in good]],
                                     cv2.RANSAC, 6.0)
        return int(mask.sum()) if mask is not None else 0

    def match(self, crop, last=None):
        """-> (card index or None, inliers, mode). Mode: "leer" (no card in the frame, nothing searched),
        "kurz" (last card confirmed, 1 core), "gleich" (unchanged, already searched in vain), "voll" (full search)."""
        gray = prep(crop)
        qp, qd = features(self.orb, gray)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 50, 150).mean() / 255
        if len(qd) < GATE_KEYPOINTS or edges < GATE_EDGES:
            self._miss_thumb = None
            return None, 0, "leer"
        if last is not None:
            inl = self._verify(qp, qd, last)
            if inl >= self.min_inliers:
                return last, inl, "kurz"
        thumb = cv2.resize(gray, (32, 44), interpolation=cv2.INTER_AREA).astype(np.int16)
        if self._miss_thumb is not None and np.abs(thumb - self._miss_thumb).mean() < 6:
            return None, 0, "gleich"
        idx, inl = self._search(qp, qd)
        self._miss_thumb = thumb if idx is None else None
        return idx, inl, "voll"

    def _search(self, qp, qd):
        # 1) Fast preselection: matching against all cards (in parallel), votes per card
        votes = self._votes(qd)
        scored = []
        for i in np.argsort(-votes)[:6]:
            if votes[i] < 4:
                break
            good = [m[0] for m in self.bf.knnMatch(qd, self.des[i], k=2)
                    if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
            scored.append((len(good), int(i), good))
        scored.sort(key=lambda t: -t[0])

        # Check the top candidates geometrically (homography + RANSAC)
        results = []
        for n, i, good in scored[:5]:
            if n < 10:
                break
            src = qp[[m.queryIdx for m in good]]
            dst = self.pts[i][[m.trainIdx for m in good]]
            _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 6.0)
            results.append((int(mask.sum()) if mask is not None else 0, i))
        if not results:
            return None, 0
        best = max(r[0] for r in results)
        if best < self.min_inliers:
            return None, best
        # Same artwork in several printings (e.g. promo stamp): prefer the booster version
        close = [r for r in results if r[0] >= 0.85 * best]
        close.sort(key=lambda r: (not self.cards[r[1]]["booster"], -r[0]))
        return close[0][1], close[0][0]


# ---------- Pack / Session ----------
INFO_DEFAULTS = {"title": "", "product": "", "sets": [], "packs_planned": 0, "paid": 0.0, "notes": "",
                 "pack_type": "booster", "tags": []}  # pack_type = type of new packs, tags = session categories


# what a session is (info["kind"]): "cards" = scanning cards (the default of new sessions – one list, no packs shown),
# "packs" = opening boosters (a conscious choice: pack by pack, Ø per pack, best pack), "singles" = trade/purchase.
# "manual" = the day's changes by hand (collection/manual.py: lines with "delta" ±n), "import" = one import run.
# Saved sessions without a kind are from before "cards" existed: packs, as they always were.
KINDS = ("cards", "packs", "singles", "manual", "import")
SCAN_KINDS = ("cards", "packs", "singles")   # what a scan session can be switched to


def kind_of(info):
    k = (info or {}).get("kind")
    return k if k in KINDS else "packs"


def is_trade(info):
    """A trade log: "I give this" is possible – however it was made (New log → Scan a trade sets trade_scan; the tile's
    kind Singles with What = Trade only the pack type). 03.11.2026: always (before: only trade_scan)."""
    info = info or {}
    return bool(info.get("trade_scan") or (kind_of(info) == "singles" and info.get("pack_type") == "trade"))


def trade_end_text(info, packs):
    """The sentence before ending a trade log with cards given away (they leave the collection, no Undo) – "" if none."""
    from system.i18n import tr
    n = sum(1 for p in packs for e in p.get("cards", []) if e.get("out")) if is_trade(info) else 0
    if not n:
        return ""
    who = ((info or {}).get("title") or "").strip() or tr("your trade partner")
    return (tr(f"1 card goes to {who} and leaves your collection – this can't be undone.") if n == 1 else
            tr(f"{n} cards go to {who} and leave your collection – this can't be undone."))


def has_packs(info):
    """Packs are counted and shown only when opening boosters."""
    return kind_of(info) == "packs"


def price_of(entry):
    return entry["eur_foil"] if entry["foil"] else entry["eur"]


def _n(e):
    """copies a line stands for: 1 for a scanned card, ±n for a change by hand (collection/manual.py)"""
    return int(e.get("delta", 1))


def pack_total(pack):
    return round(sum((e["price"] or 0) * _n(e) for e in pack["cards"]), 2)


def session_stats(packs, info):
    """Key figures of a session (also for saved sessions in the statistics)."""
    # scanning cards, singles (trade, purchase): one list – no packs, no average per pack, no best pack
    opened = [p for p in packs if p["cards"]] if has_packs(info) else []
    totals = [pack_total(p) for p in packs]
    total = round(sum(totals), 2)
    all_cards = [e for p in packs for e in p["cards"]]
    gained = [e for e in all_cards if _n(e) > 0]   # taken out by hand: no hit, no counter
    priced = [e for e in gained if e["price"] is not None]
    best_i = max(range(len(packs)), key=lambda i: totals[i]) if opened else None
    paid = float(info.get("paid") or 0)
    return {
        "packs": len(opened),
        "cards": sum(_n(e) for e in all_cards),
        "total": total,
        "avg_pack": round(total / len(opened), 2) if opened else 0.0,
        "best_pack": {"number": best_i + 1, "total": totals[best_i]} if best_i is not None else None,
        "biggest_hit": dict(max(priced, key=lambda e: e["price"])) if priced else None,
        "counts": _counts(gained),
        "paid": paid,
        "profit": round(total - paid, 2) if paid else None,
    }


def _counts(cards):
    """Counters of a session: the game's two rarity levels (keys "mythic"/"rare" as before – Lorcana: Enchanted+ /
    Legendary, Pokémon: Ultra+ / Rare …) and the third counter under "foil" (foil cards; other games: e.g. parallels)."""
    import games
    g = games.current()
    (_, top), (_, second) = g.counter_tiers
    rar = [(e.get("rarity") or "").lower() for e in cards]
    return {"mythic": sum(r in top for r in rar), "rare": sum(r in second for r in rar),
            "foil": sum(bool(g.counter_third(e)) for e in cards)}


class Session:
    """A stream session: all packs with their cards (price at the time of opening) and stream info.
    packs[-1] is the current pack. Every change increments rev; app.py then saves the file."""

    def __init__(self, cards=(), data=None):
        self.cards = list(cards)
        self.lock = threading.Lock()
        data = data or {}
        now = time.time()
        self.id = data.get("id") or time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(now))
        self.started = data.get("started", now)
        self.ended = data.get("ended")
        self.to_collection = data.get("collection")  # chosen when ending: add the cards to the collection?
        self.info = dict(INFO_DEFAULTS, **data.get("info", {}))
        self.info["tags"] = list(self.info.get("tags") or [])  # separate list per session
        if not data.get("id"):   # a new session scans cards; saved ones keep theirs (none = packs, see kind_of)
            self.info.setdefault("kind", "cards")
        self.packs = data.get("packs") or [{"opened": now, "cards": [], "type": self.info.get("pack_type")}]
        self.current = None
        self.last_counted = None
        self.last_auto = None     # last AUTOMATICALLY counted card (scan, not by hand) – for the scan sounds
        self.recent = collections.deque(maxlen=RECENT_CARDS)  # [{"id", "seen"}] of the recently counted cards
        self.rev = 0
        self.autostarted = 0.0    # time at which the first card started the session by itself
        self.default_lang = "en"  # language of newly scanned cards (settings)

    def scan_lang_for(self, card):
        """The language this log scans in (Scan tile → Settings → Language, info["scan_lang"]; None = all) – only if
        this print exists in it (the card database knows its languages); else None and the default applies."""
        want = self.info.get("scan_lang")
        if not want:
            return None
        from cards import carddb
        try:
            if carddb.exists() and carddb.lacks_language(card["set"], card["number"], want):
                return None
        except Exception:  # noqa: BLE001
            pass
        return want

    # --- Save / load ---
    def to_dict(self):
        with self.lock:
            return {"id": self.id, "started": self.started, "ended": self.ended, "collection": self.to_collection,
                    "info": dict(self.info),
                    "packs": [{"opened": p["opened"], "type": p.get("type") or "booster",
                               "cards": [dict(e) for e in p["cards"]]} for p in self.packs],
                    "stats": session_stats(self.packs, self.info)}

    @property
    def pack(self):
        return self.packs[-1]["cards"]

    # --- Recognition ---
    @staticmethod
    def _set_lang(entry, lang):
        """Set a card's language; if the image of the language version already exists, the overlay shows it right away
        (otherwise app.py downloads it and calls set_image)."""
        en_img = entry.get("img_en") or entry["img"]
        entry["lang"] = lang or "en"
        entry.pop("img_en", None)
        entry["img"] = en_img
        if entry["lang"] != "en":
            entry["img_en"] = en_img
            local = lang_img(en_img, entry["lang"])
            if (BASE / local).exists():
                entry["img"] = local

    @property
    def active(self):
        """Is the session running? New sessions only begin via "New session" (info["active"] = False until then);
        saved sessions without the entry count as running."""
        return self.info.get("active", True) is not False

    def _autostart(self, now):
        """No session started yet: the first card starts it (kind as configured, default: scanning cards) –
        the app reports it (autostarted) and saves."""
        if not self.active:
            self.info["active"] = True
            self.started = now
            self.autostarted = now

    def _add(self, card, foil=None, lang=None, finish=None, edition=None, cond=None):
        from cards import conditions
        from cards import finishes
        self._autostart(time.time())
        entry = dict(card, foil=False, added=time.time())
        for k in ("cond", "grade_by", "grade", "cond_note"):   # never take these from the card dict
            entry.pop(k, None)
        entry.update(cond or {"cond": conditions.default()})   # condition: default from the settings (NM)
        # finish per game (finishes.py): as given, otherwise from foil, otherwise the printing's base finish
        finishes.apply(entry, finish or finishes.default_for(card, foil))
        if edition:
            entry["edition"] = edition
        entry.pop("thumb", None)
        # an Asian print (Pokémon: own sets) brings its language – the default language is for western prints
        self._set_lang(entry, lang or card.get("plang") or self.scan_lang_for(card) or self.default_lang)
        entry["price"] = price_of(entry)
        if not self.pack:
            self.packs[-1]["opened"] = entry["added"]  # the pack begins with its first card
        self.pack.append(entry)
        self.current, self.last_counted = entry, card["id"]
        self.rev += 1
        if entry.get("eur") is None and entry.get("eur_foil") is None:
            self._price_later(entry)
        from net import anonstats
        anonstats.mark("scan", scans=1)   # only with consent: "scanned today" + rough amount

    def _price_later(self, entry):
        """Card without a price (e.g. Pokémon from the bundled index – the card database has no prices):
        ask the game for the price in the background and fill it in."""
        import games
        look = games.current().price_lookup
        if look is None:
            return

        def work():
            try:
                res = look(entry["id"])
            except Exception:  # noqa: BLE001 – no network: then no price
                return
            if not res:
                return
            with self.lock:
                entry["eur"], entry["eur_foil"] = res
                entry["price"] = price_of(entry)
                self.rev += 1
        threading.Thread(target=work, daemon=True).start()

    def on_card(self, card, lang=None, force=False, foil=None):
        """Recognized card (dict from the card list); the same card only counts again after an empty frame.
        lang: language read by OCR (otherwise the default language). force: definitely another card
        (e.g. the same printing in another language right after) – counts despite the same ID."""
        with self.lock:
            now = time.time()
            if force:
                self._add(card, foil, lang)
                self.last_auto = self.current
                self.recent.append({"id": card["id"], "seen": now})
                return
            known = next((r for r in self.recent if r["id"] == card["id"]), None)
            if known is not None:
                gap, known["seen"] = now - known["seen"], now
                if card["id"] == self.last_counted or gap < REAPPEAR_SECONDS:
                    return  # same card, only gone briefly: do not count again
            elif card["id"] == self.last_counted:
                return
            self._add(card, foil, lang)
            self.last_auto = self.current
            self.recent.append({"id": card["id"], "seen": now})

    def add_manual(self, card, foil=None, lang=None, finish=None, edition=None, cond=None):
        with self.lock:
            self._add(card, foil, lang, finish, edition, cond)

    def on_empty(self):
        with self.lock:
            if self.current is not None or self.last_counted is not None:
                self.current, self.last_counted = None, None
                self.rev += 1

    def new_pack(self):
        with self.lock:
            if self.pack and has_packs(self.info):   # scanning cards, singles: everything in one list
                self.packs.append({"opened": time.time(), "cards": [], "type": self.info.get("pack_type")})
            self.current, self.last_counted = None, None
            self.rev += 1

    def cards_view(self):
        """All cards of the session, newest first, each with its pack (1-based) and its place in that pack (idx) –
        for the scan page's list (not in snapshot(): that runs on every change)."""
        with self.lock:
            return [dict(e, pack=pi + 1, idx=ci) for pi, p in reversed(list(enumerate(self.packs)))
                    for ci, e in reversed(list(enumerate(p["cards"])))]

    def set_kind(self, kind):
        """Switch what the session is -> False when not possible (to "cards" with more than one pack: the packs
        would be lost from view – merge them first)."""
        if kind not in SCAN_KINDS or kind_of(self.info) not in SCAN_KINDS:
            return False
        with self.lock:
            if kind != "packs" and len(self.packs) > 1:
                return False
            self.info["kind"] = kind
            self.rev += 1
        return True

    def set_info(self, **kw):
        with self.lock:
            self.info.update(kw)
            self.rev += 1

    def set_pack_type(self, key, p=None):
        """Set a pack's type (p=None: current pack – then also the default for the next packs)."""
        with self.lock:
            self.packs[-1 if p is None else p]["type"] = key
            if p is None or p == len(self.packs) - 1:
                self.info["pack_type"] = key
            self.rev += 1

    # --- Editing (p = pack index, i = card index; None = current pack / last card) ---
    def _entry(self, p, i):
        cards = self.packs[-1 if p is None else p]["cards"]
        return cards, (len(cards) - 1 if i is None else i)

    def undo(self, i=None, p=None):
        """Removes a card (default: the last one of the current pack)."""
        with self.lock:
            cards, i = self._entry(p, i)
            if not cards:
                return
            e = cards.pop(i)
            if e is self.current:
                self.current = None
            self.last_counted = None
            # forget the removed card so it can be scanned again right away
            for r in [r for r in self.recent if r["id"] == e["id"]]:
                self.recent.remove(r)
            self.rev += 1

    def put_back(self, e, i, p):
        """Undo of a removal (the scan list's ✕): the very same entry back at its place."""
        with self.lock:
            if 0 <= p < len(self.packs):
                cards = self.packs[p]["cards"]
                cards.insert(min(max(0, i), len(cards)), e)
                self.rev += 1

    def duplicate(self, i=None, p=None):
        """Count the same card once more (same printing, language, foil) – right after it. For several identical
        cards in a row: scan once, then count up."""
        with self.lock:
            cards, i = self._entry(p, i)
            if not cards:
                return
            e = dict(cards[i], added=time.time())
            cards.insert(i + 1, e)
            self.rev += 1

    def toggle_foil(self, i=None, p=None):
        """F / button in the list: to the printing's next finish (Magic non-foil ↔ foil, Pokémon normal → holo →
        reverse holo → normal …)."""
        from cards import finishes
        with self.lock:
            cards, i = self._entry(p, i)
            if cards:
                e = cards[i]
                finishes.apply(e, finishes.next_key(e))
                e["price"] = price_of(e)
                self.rev += 1

    def toggle_cond(self, i=None, p=None):
        """Z / button in the list: next condition grade (NM → EX → … on the user's scale)."""
        from cards import conditions
        with self.lock:
            cards, i = self._entry(p, i)
            if cards:
                e = cards[i]
                conditions.apply(e, conditions.next_key(e))
                self.rev += 1

    def toggle_out(self, i=None, p=None):
        """Trade scan: mark a card as "giving away" (or unmark it) -> new state or None."""
        with self.lock:
            cards, i = self._entry(p, i)
            if not cards:
                return None
            e = cards[i]
            e["out"] = not e.get("out")
            if not e["out"]:
                e.pop("out")
            self.rev += 1
            return bool(e.get("out"))

    def replace(self, card, i=None, p=None, foil=None, lang=None, finish=None, edition=None):
        """Replace a misrecognized card with another one (without foil/lang given, both are kept)."""
        from cards import finishes
        with self.lock:
            cards, i = self._entry(p, i)
            if not cards:
                return
            old = cards[i]
            if foil is None and finish is None:
                foil = old["foil"] if (old["foil"] and card.get("eur_foil") is not None) else card["finishes"] == ["foil"]
                finish = old.get("finish")   # same finish, if the new printing has it
            e = dict(card, foil=bool(foil), added=old.get("added", time.time()))
            e.pop("finish", None)
            e.pop("edition", None)
            if not (finish and finishes.apply(e, finish)):
                finishes.apply(e, finishes.default_for(card, foil))
            from cards import conditions
            e.update(conditions.fields(old))   # different printing, same copy: condition stays
            ed = edition if edition is not None else old.get("edition")
            if ed and any(x["key"] == ed for x in finishes.editions(e)):
                e["edition"] = ed
            e.pop("thumb", None)
            e.pop("img_en", None)
            self._set_lang(e, lang or old.get("lang") or "en")
            e["price"] = price_of(e)
            cards[i] = e
            if old is self.current:
                self.current = e
            self.last_counted = None
            self.rev += 1

    def replace_added(self, added, card):
        """Correct the printing of an already counted card (answer to the follow-up question)."""
        pos = self.find(added)
        if pos is not None:
            self.replace(card, i=pos[1], p=pos[0])

    def find(self, added):
        """(pack index, card index) of the card with this timestamp, or None."""
        for pi, pack in enumerate(self.packs):
            for ci, e in enumerate(pack["cards"]):
                if e.get("added") == added:
                    return pi, ci
        return None

    def set_card(self, added, lang=None, foil=None, finish=None, edition=None, cond=None):
        """Change a card's language/foil/finish/edition/condition (e.g. from the library). edition "" = none.
        cond: condition fields ({"cond": …, "grade_by": …}, conditions.py)."""
        from cards import finishes
        with self.lock:
            pos = self.find(added)
            if pos is None:
                return False
            e = self.packs[pos[0]]["cards"][pos[1]]
            if lang is not None:
                self._set_lang(e, lang)
            if finish is not None:
                finishes.apply(e, finish)
                e["price"] = price_of(e)
            elif foil is not None:
                e["foil"] = bool(foil)
                e.pop("finish", None)
                e["price"] = price_of(e)
            if edition is not None:
                if edition and any(x["key"] == edition for x in finishes.editions(e)):   # only where it exists
                    e["edition"] = edition
                else:
                    e.pop("edition", None)
            if cond is not None:
                from cards import conditions
                conditions.apply(e, cond.get("cond"), cond.get("grade_by"), cond.get("grade"), cond.get("cond_note"))
            self.rev += 1
            return True

    def note_edit(self, added, changes):
        """Note a change made from the library on the log card: {field: [before, after]} – shown as a grey line
        under it in the log (logs as the library's source: the change is where the copy came from)."""
        if not changes:
            return False
        with self.lock:
            pos = self.find(added)
            if pos is None:
                return False
            e = self.packs[pos[0]]["cards"][pos[1]]
            e.setdefault("edits", []).append({"t": time.time(), "changes": {k: list(v) for k, v in changes.items()}})
            self.rev += 1
            return True

    def set_image(self, added, lang, img):
        """Fill in the downloaded image of the language version (only if the language still matches)."""
        with self.lock:
            pos = self.find(added)
            if pos is None:
                return
            e = self.packs[pos[0]]["cards"][pos[1]]
            if e.get("lang") == lang and img and e["img"] != img:
                e["img"] = img
                if self.current is not None and self.current.get("added") == added:
                    self.current = e
                self.rev += 1

    def remove_entry(self, entry):
        """Remove exactly this entry (scanner miscount). -> True if it was still there."""
        with self.lock:
            for p in self.packs:
                for i, e in enumerate(p["cards"]):
                    if e is entry:
                        p["cards"].pop(i)
                        if e is self.current:
                            self.current = None
                        self.last_counted = None
                        for rr in [rr for rr in self.recent if rr["id"] == e["id"]]:
                            self.recent.remove(rr)
                        self.rev += 1
                        return True
            return False

    def undo_new_pack(self):
        """Accidental "New pack": back to the previous pack while the new one is still empty. -> True if so."""
        with self.lock:
            if len(self.packs) > 1 and not self.packs[-1]["cards"]:
                self.packs.pop()
                self.current, self.last_counted = None, None
                self.rev += 1
                return True
            return False

    def merge_into_previous(self, p):
        """Merge pack p into the pack before it (cards ended up in the wrong, new pack). -> True if so."""
        with self.lock:
            if 0 < p < len(self.packs):
                self.packs[p - 1]["cards"].extend(self.packs[p]["cards"])
                self.packs.pop(p)
                self.current, self.last_counted = None, None
                self.rev += 1
                return True
            return False

    def delete_pack(self, p):
        with self.lock:
            if len(self.packs) > 1 or self.packs[0]["cards"]:
                self.packs.pop(p)
                if not self.packs:
                    self.packs = [{"opened": time.time(), "cards": [], "type": self.info.get("pack_type")}]
                self.current, self.last_counted = None, None
                self.rev += 1

    def reprice(self, cards):
        """After a price update: take over the new card list, refresh the prices in the current pack."""
        with self.lock:
            by_id = {c["id"]: c for c in cards}
            for e in self.pack:
                if e["id"] in by_id:
                    c = by_id[e["id"]]
                    e["eur"], e["eur_foil"] = c["eur"], c["eur_foil"]
                    e["price"] = price_of(e)
            self.cards = cards
            self.rev += 1

    def snapshot(self):
        with self.lock:
            stats = session_stats(self.packs, self.info)
            return {
                "rev": self.rev,
                "current": dict(self.current) if self.current else None,
                "pack": [dict(e) for e in self.pack],
                "pack_number": len(self.packs),
                "singles": self.info.get("kind") == "singles",
                "kind": kind_of(self.info),
                "packs_shown": has_packs(self.info),
                "can_cards": len(self.packs) <= 1,   # packs -> cards only while there's at most one pack
                "pack_type": self.packs[-1].get("type") or self.info.get("pack_type") or "booster",
                "pack_total": pack_total(self.packs[-1]),
                "session_total": stats["total"],
                "stats": stats,
                "info": dict(self.info),
            }
