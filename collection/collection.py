"""Your own collection: data/my-data/collection.json

Each copy (or each stack of identical copies) is one entry:
    {"uid", "id" (as in the set files, e.g. <scryfall-id>_0), "name", "set", "number", "rarity",
     "finishes", "eur", "eur_foil", "img" (English image), "lang", "foil", "count", "added",
     optional "finish"/"edition" (finish/edition per game, finishes.py – missing: derived from "foil"),
     optional "cond" (+ "grade_by"/"grade"/"cond_note"): condition, conditions.py – missing: Near Mint,
     "src": "<session-id>/<added>" or None (added by hand)}

Scanned cards come in via sync_session(): every card of a session is exactly one entry with src.
If the card is replaced/removed in the session, the collection follows on the next save.
Session cards removed from the collection end up in "hidden" so they don't reappear – not even when the
session is taken out of the collection and added again. Trades are booked by bookings.py.
"""
import json
import threading
import time
import uuid

from cards import conditions
from scanner.common import MINE

FILE = MINE / "collection.json"
CARD_KEYS = ("id", "name", "set", "number", "rarity", "finishes", "booster", "eur", "eur_foil", "img", "url")
# display abbreviations as commonly used on Scryfall/Cardmarket
ALL_LANGS = [("en", "EN", "English"), ("de", "DE", "Deutsch"), ("fr", "FR", "Français"), ("it", "IT", "Italiano"),
             ("es", "ES", "Español"), ("pt", "PT", "Português"), ("ja", "JP", "日本語"), ("ko", "KR", "한국어"),
             ("ru", "RU", "Русский"), ("zhs", "CS", "简体中文"), ("zht", "CT", "繁體中文"), ("th", "TH", "ไทย"),
             ("id", "ID", "Bahasa Indonesia")]
LANG_SHORT = {code: short for code, short, _ in ALL_LANGS}
_MTG_LANGS = ("en", "de", "fr", "it", "es", "pt", "ja", "ko", "ru", "zhs", "zht")


def _langs_of_game():
    import games
    want = games.current().languages or _MTG_LANGS
    return [x for x in ALL_LANGS if x[0] in want]


LANGS = _langs_of_game()   # languages of the active game (updated in place – others import the list)


def _game_changed():
    LANGS[:] = _langs_of_game()


def lang_short(code):
    return LANG_SHORT.get(code or "en", (code or "en").upper())


def scryfall_id(card_id):
    """<scryfall-id>_<face> -> <scryfall-id>"""
    sid, _, face = card_id.rpartition("_")
    return sid if face.isdigit() and sid else card_id


def price(item):
    return item.get("eur_foil") if item.get("foil") else item.get("eur")


def variant_key(it):
    """What distinguishes a copy from the same printing: foil price, finish, edition, condition."""
    c = it.get("cond")   # fast path for the common case (runs for every card in the collection)
    return (bool(it.get("foil")), it.get("finish") or "", it.get("edition") or "",
            "near_mint" if not c or c == "near_mint" else conditions.ident(it))


def groups_of(items):
    """Entries -> groups (same card + language + finish/edition), see Collection.groups."""
    out = {}
    for it in items:
        key = (scryfall_id(it["id"]), it.get("lang") or "en") + variant_key(it)
        g = out.get(key)
        if g is None:
            g = out[key] = dict(it, sid=key[0], count=0, items=[], last=0)
        g["count"] += it.get("count", 1)
        g["items"].append(it)
        g["last"] = max(g["last"], it.get("added") or 0)
    return list(out.values())


class Collection:
    def __init__(self):
        self.lock = threading.Lock()
        self.items, self.hidden, self.rev = [], set(), 0
        self.is_new = not FILE.exists()
        if not self.is_new:
            try:
                data = json.loads(FILE.read_text("utf-8"))
                self.items, self.hidden = data.get("items", []), set(data.get("hidden", []))
            except (OSError, ValueError):
                pass

    def save(self):
        with self.lock:
            data = {"version": 1, "saved": time.time(), "items": [dict(i) for i in self.items],
                    "hidden": sorted(self.hidden)}
        MINE.mkdir(parents=True, exist_ok=True)
        from system import undo
        undo.before_write(FILE, "Sammlung")
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        for _ in range(5):
            try:
                tmp.replace(FILE)
                return
            except PermissionError:
                time.sleep(0.05)

    def reload(self):
        """After undo/redo: re-read the state from the file."""
        try:
            data = json.loads(FILE.read_text("utf-8")) if FILE.exists() else {}
        except (OSError, ValueError):
            return
        with self.lock:
            self.items, self.hidden = data.get("items", []), set(data.get("hidden", []))
            self.rev += 1

    @staticmethod
    def _from_card(card, lang, foil, count, src=None, added=None, finish=None, edition=None, cond=None):
        from cards import conditions
        item = {k: card.get(k) for k in CARD_KEYS}
        item.update(uid=uuid.uuid4().hex[:12], lang=lang or "en", foil=bool(foil), count=int(count),
                    added=added or time.time(), src=src)
        if finish:
            item["finish"] = finish
        if edition:
            item["edition"] = edition
        item.update(cond or {"cond": conditions.default()})
        if card.get("img_en"):
            item["img"] = card["img_en"]
        return item

    # --- Sessions ---
    def sync_session(self, sess):
        """Take over the cards of a session (dict as in sessions.py). -> True if something changed.
        Changes by hand (kind "manual") are already in the collection – never taken over."""
        if (sess.get("info") or {}).get("kind") == "manual":
            return False
        prefix = sess["id"] + "/"
        want = {}
        for pi, pack in enumerate(sess.get("packs", [])):
            for e in pack.get("cards", []):
                if e.get("out"):   # trade scan: "I'm giving this away" – does not go into the collection (gets booked)
                    continue
                want[prefix + repr(e.get("added", 0))] = (e, pi)
        changed = False
        with self.lock:
            keep = []
            have = set()
            for it in self.items:
                src = it.get("src")
                if not src or not src.startswith(prefix):
                    keep.append(it)
                    continue
                if src not in want:
                    changed = True  # removed in the session
                    continue
                e, pi = want[src]
                new = {k: e.get(k) for k in CARD_KEYS}
                if e.get("img_en"):
                    new["img"] = e["img_en"]
                new.update(lang=e.get("lang") or "en", foil=bool(e.get("foil")), pack=pi + 1)
                for k in ("finish", "edition", "cond", "grade_by", "grade", "cond_note", "from_print"):   # only if set
                    if e.get(k) or it.get(k):
                        new[k] = e.get(k)
                if any(it.get(k) != v for k, v in new.items()):
                    it.update(new)
                    changed = True
                have.add(src)
                keep.append(it)
            for src, (e, pi) in want.items():
                if src in have or src in self.hidden:
                    continue
                from cards import conditions
                item = self._from_card(e, e.get("lang"), e.get("foil"), 1, src, e.get("added"), e.get("finish"),
                                       e.get("edition"), conditions.fields(e) or {"cond": conditions.DEFAULT})
                item["pack"] = pi + 1
                if e.get("from_print"):   # the print it sat on before a move (collection/printmove) – the way back
                    item["from_print"] = e["from_print"]
                keep.append(item)
                changed = True
            if changed:
                self.items = keep
                self.rev += 1
        return changed

    def detach_session(self, sid):
        """Session is being deleted; its cards stay in the collection as standalone entries."""
        with self.lock:
            for it in self.items:
                if (it.get("src") or "").startswith(sid + "/"):
                    it["src"], it["from_session"] = None, sid
            self.rev += 1

    def restore_items(self, items):
        """From the trash: put entries back into the collection (same uid not twice)."""
        with self.lock:
            have = {it["uid"] for it in self.items}
            for it in items:
                if it.get("uid") not in have:
                    self.items.append(dict(it))
            self.rev += 1

    def remove_session(self, sid):
        """Take the session's cards out of the collection. "hidden" stays: individually removed or swapped cards
        don't come back when the session is later added to the collection again (otherwise it would show +1)."""
        with self.lock:
            self.items = [it for it in self.items if not (it.get("src") or "").startswith(sid + "/")]
            self.rev += 1

    # --- By hand ---
    def add(self, card, lang="en", foil=False, count=1, finish=None, edition=None, cond=None):
        """Add a card by hand; the same card/language/finish/condition is counted together.
        cond: condition fields ({"cond": …}, conditions.py) – missing: default from the settings."""
        from cards import conditions
        cond = cond or {"cond": conditions.default()}
        with self.lock:
            want = (bool(foil), finish or "", edition or "", conditions.ident(cond))
            for it in self.items:
                if not it.get("src") and it["id"] == card["id"] and it["lang"] == lang and variant_key(it) == want:
                    it["count"] += int(count)
                    self.rev += 1
                    return it
            item = self._from_card(card, lang, foil, count, finish=finish, edition=edition, cond=cond)
            self.items.append(item)
            self.rev += 1
            return item

    def get(self, uid):
        return next((it for it in self.items if it["uid"] == uid), None)

    def update(self, uid, **fields):
        with self.lock:
            it = self.get(uid)
            if it:
                it.update(fields)
                self.rev += 1
            return it

    def set_count(self, uid, n):
        with self.lock:
            it = self.get(uid)
            if not it:
                return
            if n > 0:
                it["count"] = int(n)
            else:
                self.items.remove(it)
                if it.get("src"):
                    self.hidden.add(it["src"])
            self.rev += 1

    def remove(self, uid):
        self.set_count(uid, 0)

    def reprice(self, prices):
        """prices: {scryfall-id: (eur, eur_foil)} – e.g. from the sets or the card database."""
        with self.lock:
            n = 0
            for it in self.items:
                p = prices.get(scryfall_id(it["id"]))
                if p and (it.get("eur"), it.get("eur_foil")) != p:
                    it["eur"], it["eur_foil"] = p
                    n += 1
            if n:
                self.rev += 1
            return n

    # --- Evaluation ---
    def groups(self):
        """Same card + language + foil combined (for library and export)."""
        with self.lock:
            return groups_of(self.items)

    def owned(self):
        """{scryfall-id: count} across all languages/foil."""
        out = {}
        with self.lock:
            for it in self.items:
                sid = scryfall_id(it["id"])
                out[sid] = out.get(sid, 0) + it.get("count", 1)
        return out

    def summary(self):
        with self.lock:
            n = sum(it.get("count", 1) for it in self.items)
            value = sum((price(it) or 0) * it.get("count", 1) for it in self.items)
            langs = {}
            for it in self.items:
                langs[it.get("lang") or "en"] = langs.get(it.get("lang") or "en", 0) + it.get("count", 1)
            unique = len({scryfall_id(it["id"]) for it in self.items})
        return {"cards": n, "unique": unique, "value": round(value, 2), "langs": langs}


# ---------- Export ----------
EXPORT_FORMATS = [("manabox", "ManaBox (CSV)"), ("moxfield", "Moxfield (CSV)"), ("excel", "Excel spreadsheet (CSV)")]
MOXFIELD_LANG = {"en": "English", "de": "German", "fr": "French", "it": "Italian", "es": "Spanish",
                 "pt": "Portuguese", "ja": "Japanese", "ko": "Korean", "ru": "Russian",
                 "zhs": "Chinese Simplified", "zht": "Chinese Traditional"}


def export_csv(groups, path, fmt, set_names=None):
    """Collection (groups() or a selection of it) as CSV for ManaBox/Moxfield or Excel. -> number of rows"""
    import csv
    from cards import conditions
    set_names = set_names or {}
    rarity = {"common": "common", "uncommon": "uncommon", "rare": "rare", "mythic": "mythic"}
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        if fmt == "excel":  # German Excel: semicolon, comma as decimal separator
            w = csv.writer(f, delimiter=";")
            w.writerow(["Anzahl", "Name", "Set", "Setname", "Nummer", "Sprache", "Foil", "Seltenheit", "Zustand",
                        "Preis (€)", "Wert (€)", "Scryfall-ID"])
            for g in groups:
                p = price(g)
                w.writerow([g["count"], g["name"], g["set"], set_names.get(g["set"].lower(), ""), g["number"],
                            lang_short(g["lang"]), "ja" if g["foil"] else "", g.get("rarity") or "",
                            conditions.name(g), "" if p is None else f"{p:.2f}".replace(".", ","),
                            "" if p is None else f"{p * g['count']:.2f}".replace(".", ","), g["sid"]])
        elif fmt == "moxfield":
            w = csv.writer(f)
            w.writerow(["Count", "Tradelist Count", "Name", "Edition", "Condition", "Language", "Foil", "Tags",
                        "Last Modified", "Collector Number", "Alter", "Proxy", "Purchase Price"])
            for g in groups:
                w.writerow([g["count"], 0, g["name"], g["set"].lower(), conditions.moxfield(g),
                            MOXFIELD_LANG.get(g["lang"], "English"), "foil" if g["foil"] else "", "",
                            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(g.get("last") or time.time())),
                            g["number"], "False", "False", ""])
        else:  # ManaBox: matched unambiguously via the Scryfall ID
            w = csv.writer(f)
            w.writerow(["Name", "Set code", "Set name", "Collector number", "Foil", "Rarity", "Quantity",
                        "ManaBox ID", "Scryfall ID", "Purchase price", "Misprint", "Altered", "Condition",
                        "Language", "Purchase price currency"])
            for g in groups:
                p = price(g)
                w.writerow([g["name"], g["set"], set_names.get(g["set"].lower(), ""), g["number"],
                            "foil" if g["foil"] else "normal", rarity.get(g.get("rarity"), g.get("rarity") or ""),
                            g["count"], "", g["sid"], "" if p is None else f"{p:.2f}", "false", "false",
                            conditions.manabox(g), g["lang"], "EUR"])
    return len(groups)
