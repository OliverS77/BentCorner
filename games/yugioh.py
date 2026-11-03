"""Yu-Gi-Oh! TCG – card data from YGOPRODeck (db.ygoprodeck.com, free, no key).

The card database (format like carddb.SCHEMA) is built by tools/build_yugioh_db.py and comes as a data pack from
our server – YGOPRODeck wants data stored locally and images self-hosted (not hotlinked continuously).
That's why img_normal/img_small point to our server (<BASE_URL>/packs/yugioh/img/<passcode>.jpg).

Printings: one per set number and rarity (LOB-EN001 -> set "lob", number "EN001"; further rarities of the same
number with a suffix: "EN001-UR"). Search lists show one per set number (variant_numbers), the rarities are in
the card's printings; the rarity is shown everywhere instead of "Normal". Edition: 1st Edition. Deck building
"coming soon". Columns as in Magic:
type_line "Monster — Effect — Dragon", oracle_text = card text, power/toughness = ATK/DEF, cmc = level/rank/link,
colors = attribute (D L E W F A V), keywords = archetype, loyalty = pendulum scale, frame_effects = frame.
"""
import json
import logging
import sqlite3
import time

from system.i18n import tr
from .base import Game

log = logging.getLogger("booster")

API = "https://db.ygoprodeck.com/api/v7"


def _num(v):
    try:
        v = float(v)
        return round(v, 2) if v > 0 else None
    except (TypeError, ValueError):
        return None


class YuGiOh(Game):
    key = "yugioh"
    name = "Yu-Gi-Oh! TCG"
    short = "yugioh"
    market = {"cardmarket": "YuGiOh", "tcgplayer": "yugioh", "search_word": "yugioh"}
    formats = (("advanced", "Advanced"), ("casual", "Casual / free"))
    default_format = "advanced"
    shared_images = True   # one image per passcode for all its prints (152,729 prints, 13,962 images)
    # advanced search, section "Bannliste (TCG)" (banlist) – keys from tools/build_yugioh_db.py (legalities)
    legal_short = (("tcg_ok", "Erlaubt (3)"), ("tcg_semi", "Semi-Limitiert (2)"), ("tcg_limited", "Limitiert (1)"),
                   ("tcg_banned", "Verboten"))
    legal_long = (("advanced", "Advanced"),)
    type_order = (("Monster", "Monster"), ("Spell", "Zauber"), ("Trap", "Fallen"))
    rarities = (("common", "Common"), ("short print", "Short Print"), ("rare", "Rare"), ("super rare", "Super Rare"),
                ("ultra rare", "Ultra Rare"), ("ultimate rare", "Ultimate Rare"), ("secret rare", "Secret Rare"),
                ("ghost rare", "Ghost Rare"), ("gold rare", "Gold Rare"), ("premium gold rare", "Premium Gold Rare"),
                ("starlight rare", "Starlight Rare"), ("quarter century secret rare", "Quarter Century Secret Rare"),
                ("platinum secret rare", "Platinum Secret Rare"), ("prismatic secret rare", "Prismatic Secret Rare"),
                ("collector's rare", "Collector's Rare"))
    # Attributes (cards.colors, tools/build_yugioh_db.py)
    palette = "DLEWFAV"
    color_specials = ""
    color_hex = {"D": "#6b4f8f", "L": "#e8d36a", "E": "#9a7a4e", "W": "#3d8fd6", "F": "#e0553d", "A": "#4fae7a",
                 "V": "#d7b46a"}
    color_names = {"D": "Finsternis", "L": "Licht", "E": "Erde", "W": "Wasser", "F": "Feuer", "A": "Wind",
                   "V": "Göttlich"}
    ranges = (("pow", "ATK", 0), ("tou", "DEF", 0), ("mv", "Stufe / Rang / Link", 0), ("loy", "Pendelbereich", 0),
              ("price", "Preis (€)", 2))
    text_fields = (("oracle", "Kartentext"), ("name", "Name"), ("type", "Typzeile"), ("keyword", "Archetyp"))
    adv_titles = {"colors": "Attribut", "super": "Monsterart", "kw": "Archetyp", "sub": "Typ", "format": "Bannliste"}
    adv_hints = {"sub": "e.g. Dragon, Spellcaster, Quick-Play", "kw": "e.g. Blue-Eyes, Sky Striker"}
    adv_hidden = ()
    supertypes = (("Normal", "Normal"), ("Effect", "Effekt"), ("Fusion", "Fusion"), ("Ritual", "Ritual"),
                  ("Synchro", "Synchro"), ("XYZ", "Xyz"), ("Link", "Link"), ("Pendulum", "Pendel"),
                  ("Tuner", "Empfänger"))
    supertypes_mode = "any"
    supertypes_none = False
    lib_types_off = ()
    # names: EN DE FR IT PT from YGOPRODeck (cards.sqlite), ES JA KO ZH from YGOJSON (ygo-locale.sqlite, CC BY-SA,
    # merged on the user's PC – merge_extra). Without that file the four have no names, the language still works.
    languages = ("en", "de", "fr", "it", "pt", "es", "ja", "ko", "zhs")
    heal_prints = True      # entries follow prints that leave the database or come back (collection/printmove)
    lang_pack = "bundled"   # names in other languages are part of the shipped database
    lang_images = False     # images exist only in English
    adv_search = True       # advanced search like YGOPRODeck/Neuron (without link arrows – missing from the data)
    search_example = 't:spell k:"blue-eyes"'   # k: = archetype
    data_note = ("All cards with types, attributes, banlist, names in EN DE FR IT PT ES JA KO ZH, prints from Japan, "
                 "Korea, Asia and Spain and marketplace numbers – comes as a data pack from the Bent°Corner server "
                 "(data from YGOPRODeck; prints from Japan, Korea, Asia and Spain from YGOJSON/Yugipedia, CC BY-SA "
                 "4.0). “Download” takes it from the data pack again.")
    deck_tagline = "Build Advanced decks – Main, Extra and Side Deck with banlist and ownership"
    counter_tiers = (("Secret+", ("secret rare", "ultimate rare", "ghost rare", "starlight rare",
                                  "quarter century secret rare", "platinum secret rare", "prismatic secret rare",
                                  "collector's rare", "gold rare", "premium gold rare")),
                     ("Ultra", ("ultra rare",)))
    counter_foil = "Holo"
    deck_sources = ("YGOPRODeck", "Master Duel")
    finishes = (("nonfoil", "Normal"),)
    FINISHES = (("nonfoil", "Normal", "N", False),)   # finish = the printing's rarity (finish_options)
    variant_numbers = True   # rarities as separate printings with a suffix on the number (carddb: once in search lists)
    foil_word = "1st Edition"   # second price per printing (usd_foil) = TCGplayer for the 1st Edition
    colors = ()
    pack_types = [
        {"key": "booster", "name": "Booster", "counts": True},
        {"key": "ygo_display", "name": "Booster-Display", "counts": False},
        {"key": "ygo_structure", "name": "Structure Deck", "counts": False},
        {"key": "ygo_tin", "name": "Tin", "counts": False},
        {"key": "ygo_collection", "name": "Kollektion / Box", "counts": False},
        {"key": "promo", "name": "Promo / Beilage", "counts": False},
        {"key": "other", "name": "Sonstiges", "counts": False},
        {"key": "trade", "name": "Tausch", "counts": False},
        {"key": "purchase", "name": "Einzelkauf", "counts": False},
    ]
    # Language detection: name at the top in the name box; no language words (the type line is in square brackets in
    # the text box and differs per language – only the name for now)
    lang_layout = {"name": (0.06, 0.035, 0.80, 0.105), "words": [], "type_words": {}, "partial": True}
    price_trend_word = False
    card_types = ("Monster", "Spell", "Trap")
    card_px = (336, 490)   # 59 × 86 mm
    features = {"scan", "sessions", "library", "decks", "testing", "trade", "import"}
    # Deck building (decks.analyze_generic, decks.rule_warnings): Main Deck 40–60, Extra Deck and Side Deck at most 15,
    # at most 3 copies of a card across all of them, TCG banlist (forbidden / limited / semi-limited). The Extra Deck
    # isn't a board of its own: Fusion/Synchro/Xyz/Link monsters on the main board count as Extra Deck (deck_zone)
    deck_rules = {
        "advanced": {"size_main": (40, 60), "max_extra": 15, "max_side": 15, "copies": 3, "copies_all": True,
                     "banlist": True},
        "casual": {"size_main": (40, 60), "max_extra": 15, "max_side": 15, "copies": 3, "copies_all": True},
    }
    deck_cost_column = False
    _EXTRA = ("Fusion", "Synchro", "XYZ", "Link")
    playtest = {"hand": 5, "mulligan": None}   # 5 cards, no mulligan; the Extra Deck stays out of the shuffle

    def deck_zone(self, row):
        parts = [p.strip() for p in (row.get("type_line") or "").split("—")]
        return "extra" if len(parts) > 1 and parts[0] == "Monster" and parts[1] in self._EXTRA else "main"

    def deck_ban_limit(self, row):
        leg = row.get("legalities") or ""
        if '"tcg_banned"' in leg:
            return 0
        if '"tcg_limited"' in leg:
            return 1
        if '"tcg_semi"' in leg:
            return 2
        return None

    def deck_curve(self):
        """Levels of the Main Deck monsters: 1–4 (no tribute), 5–6 (one), 7+ (two) – highlighted: Tuners."""
        def bin_(r):
            tl = r.get("type_line") or ""
            if not tl.startswith("Monster") or self.deck_zone(r) == "extra" or r.get("cmc") is None:
                return None, False
            lv = r["cmc"] or 0
            return (0 if lv <= 4 else 1 if lv <= 6 else 2), "Tuner" in tl
        return {"title": "Levels", "sub": "Main Deck monsters", "labels": ["1–4", "5–6", "7+"], "inner": "Tuner",
                "bin": bin_}

    def deck_roles(self):
        import re
        return {
            "Draw": (re.compile(r"\bdraw (?:\d+|a|an|one|two|three) cards?|\bdraw cards?", re.I),
                     "draws extra cards"),
            "Search": (re.compile(r"add (?:1|one|up to \d+|2|two)\b[^.]*?from your (?:Deck|GY)[^.]*?to your hand",
                                  re.I), "adds cards from the Deck or GY to the hand"),
            "Special Summon": (re.compile(r"special summon", re.I), "Special Summons monsters"),
            "Negation": (re.compile(r"\bnegate", re.I), "negates effects, Summons or activations"),
            "Removal": (re.compile(r"\b(?:destroy|banish)\b[^.]*?(?:card|monster)", re.I),
                        "destroys or banishes cards"),
        }

    def deck_kpis(self, a):
        z, t = a.get("zones") or {}, a["types"]
        return [("Main Deck", z.get("main", 0), "40–60"), ("Extra Deck", z.get("extra", 0), "at most 15"),
                ("Side Deck", z.get("side", 0), "at most 15"), ("Monsters", t.get("Monster", 0), "")]

    def same_image_prints(self, con, entry, index, allow_foil=False):
        """One image per passcode, many prints: the same image file."""
        me = con.execute("SELECT * FROM cards WHERE set_code = ? AND number = ?",
                         (entry["set"].lower(), str(entry["number"]))).fetchone()
        if me is None or not me["img_small"]:
            return []
        rows = [dict(r) for r in con.execute("SELECT * FROM cards WHERE name = ? AND img_small = ?",
                                             (me["name"], me["img_small"]))]
        return rows if len(rows) > 1 else []

    def deck_name_key(self, row):
        return row.get("name") or ""

    @property
    def data(self):
        from cards import carddb
        return carddb

    prices = None

    def card_type(self, row):
        front = row.get("type_line") or ""
        for key, _ in self.type_order:
            if front.startswith(key):
                return key
        return "Other"

    def card_url(self, set_code, number):
        return ""

    def image_url(self, set_code, number, lang="en", version="normal"):
        """Image from our server (from the card database) – images exist only in English."""
        from cards import carddb
        try:
            with carddb.connection() as con:
                r = con.execute("SELECT img_normal, img_small FROM cards WHERE set_code = ? AND number = ?",
                                (str(set_code).lower(), str(number))).fetchone()
        except sqlite3.Error:
            return None
        if not r:
            return None
        return r[1] if version == "small" else r[0]

    _rar_cache = {}

    def rarity_of(self, card):
        """Rarity of a printing as a name ("Ultra Rare") – from the card or the card database."""
        rar = (card.get("rarity") or "").lower()
        if not rar:
            from collection.collection import scryfall_id
            sid = scryfall_id(card.get("id") or card.get("sid") or "")
            if sid not in self._rar_cache:
                from cards import carddb
                row = carddb.cards_by_ids([sid]).get(sid) if sid else None
                self._rar_cache[sid] = ((row or {}).get("rarity") or "").lower()
            rar = self._rar_cache[sid]
        return dict(self.rarities).get(rar) or rar.title() or "Normal"

    @staticmethod
    def rarity_short(name):
        """Short form: "Ultra Rare" -> "UR", "Secret Rare" -> "ScR" (as on the sellers' sites)."""
        special = {"Secret Rare": "ScR", "Ultimate Rare": "UtR", "Collector's Rare": "CR", "Short Print": "SP",
                   "Quarter Century Secret Rare": "QCSR", "Platinum Secret Rare": "PlScR",
                   "Prismatic Secret Rare": "PScR", "Premium Gold Rare": "PGR", "Starlight Rare": "StR"}
        return special.get(name) or "".join(w[0] for w in name.replace("'", "").split()).upper() or "N"

    def finish_options(self, card):
        name = self.rarity_of(card)
        return [{"key": "nonfoil", "label": name, "short": self.rarity_short(name), "foil": False}]

    def finish_info(self, row):
        name = self.rarity_of(row.get("card") or {"sid": row.get("sid"), "rarity": row.get("rarity")})
        return ["nonfoil"], {"n": name, "f": name}

    def editions(self, card):
        """1st Edition exists for almost all booster sets (TCGplayer lists it with its own price)."""
        return [{"key": "1st", "label": "1st Edition", "short": "1st"}]

    # ---------- Card database: comes as a data pack (tools/build_yugioh_db.py) ----------
    def download_db(self, progress=lambda text, done, total: None):
        """Reload = take over the database from the data pack (don't query YGOPRODeck for every user)."""
        from cards import carddb
        progress("Kartendatenbank: aus dem Datenpaket …", 0, 0)
        if not carddb._from_bundle():
            raise RuntimeError("Yu-Gi-Oh-Datenpaket fehlt – bitte unter Einstellungen → Kartendaten laden.")
        with carddb.connection() as con:
            n = con.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        return n, 0

    # ---------- Prices: daily from our own server (server/prices – fetches YGOPRODeck + TCGCSV once for all) ----------
    LOCALE = "ygo-locale.sqlite"

    def merge_extra(self, db):
        """The prints from YGOJSON (OCG Japan/Korea/Asia-English, Spanish) and the names JA/KO/ES/ZH ship as their own
        file in the data pack (ygo-locale.sqlite, CC BY-SA 4.0 – never inside our cards.sqlite, see
        tools/build_yugioh_db.py). Here, on the user's PC, they go into the local database: each print as its own row
        with the data and the (English) image of the card, no price, not in the full-text index. Once per file
        (meta locale_merged = its checksum); a newer data pack replaces the database, then it runs again. -> rows added"""
        import hashlib
        from cards import packs
        src = packs.path_of("yugioh", self.LOCALE)
        if src is None or not db.exists():
            return 0
        h = hashlib.sha256()
        with open(src, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        stamp = h.hexdigest()
        con = sqlite3.connect(db, timeout=30)
        try:
            if (con.execute("SELECT value FROM meta WHERE key = 'locale_merged'").fetchone() or [None])[0] == stamp:
                return 0
            con.execute("CREATE TABLE IF NOT EXISTS locale_ids (id TEXT PRIMARY KEY) WITHOUT ROWID")
            con.execute("ATTACH DATABASE ? AS loc", (str(src),))
            # an older merge (other file): out first – its rows, their variants and the extra names
            con.execute("DELETE FROM cards WHERE id IN (SELECT id FROM locale_ids)")
            con.execute("DELETE FROM variants WHERE sid IN (SELECT id FROM locale_ids)")
            con.execute("DELETE FROM langs WHERE id IN (SELECT id FROM locale_ids) OR lang IN "
                        "(SELECT DISTINCT lang FROM loc.langs WHERE lang NOT IN ('en', 'de', 'fr', 'it', 'pt'))")
            con.execute("DELETE FROM locale_ids")
            cols = [r[1] for r in con.execute("PRAGMA main.table_info(cards)")]
            own = {"id": "p.id", "set_code": "p.set_code", "set_name": "COALESCE(p.set_name, c.set_name)",
                   "number": "p.number", "rarity": "p.rarity", "released": "COALESCE(p.released, c.released)",
                   "lang": "p.lang", "promo_types": "p.promo_types", "eur": "NULL", "eur_foil": "NULL", "usd": "NULL",
                   "usd_foil": "NULL"}
            # the card's first print (as the data pack orders them) gives text, stats and image – like the old build
            con.execute("CREATE TEMP TABLE base AS SELECT oracle_id, MIN(rowid) AS r FROM main.cards "
                        "WHERE lang = 'en' GROUP BY oracle_id")
            n = con.execute(
                f"INSERT INTO main.cards ({','.join(cols)}) SELECT {','.join(own.get(k, 'c.' + k) for k in cols)} "
                "FROM loc.prints p JOIN temp.base b ON b.oracle_id = p.oracle_id JOIN main.cards c ON c.rowid = b.r "
                "WHERE p.id NOT IN (SELECT id FROM main.cards)").rowcount
            con.execute("INSERT OR IGNORE INTO locale_ids SELECT p.id FROM loc.prints p JOIN main.cards c ON c.id = p.id")
            con.execute("INSERT INTO variants SELECT v.sid, v.type FROM loc.variants v JOIN locale_ids i ON i.id = v.sid")
            con.execute("INSERT INTO langs SELECT l.* FROM loc.langs l WHERE l.id IN (SELECT id FROM main.cards)")
            con.execute("DROP TABLE temp.base")
            con.execute("INSERT OR REPLACE INTO meta VALUES ('locale_merged', ?)", (stamp,))
            con.commit()
            con.execute("DETACH DATABASE loc")
        finally:
            con.close()
        YuGiOh._locale = None
        log.info("Yu-Gi-Oh!: %d prints from %s added to the card database", n, self.LOCALE)
        return n

    _locale = None

    def locale_print(self, sid):
        """Is this print one of ygo-locale.sqlite (OCG/Asia/Spanish)? -> its image is the English print's."""
        if YuGiOh._locale is None:
            from cards import carddb
            try:
                with carddb.connection() as con:
                    YuGiOh._locale = {r[0] for r in con.execute("SELECT id FROM locale_ids")}
            except sqlite3.Error:
                YuGiOh._locale = set()
        return sid in YuGiOh._locale

    def update_prices(self, progress=lambda text, done, total: None, sets=None):
        """Daily prices from <BASE_URL>/prices/yugioh.json.gz: per printing Cardmarket € (base printing only, YGOPRODeck
        lists Cardmarket per card), TCGplayer $ and TCGplayer $ for 1st Edition. Without a Cardmarket price the app
        converts the TCGplayer price to euros and remembers that (price_est) – shown with "≈".
        -> (printings with euro price, printings with TCGplayer price)"""
        import gzip
        from cards import carddb
        from cards import currency
        from net import netpolite
        from cards import pricehist
        from net import updater
        progress("Preise: vom Bent°Corner-Server …", 0, 0)
        r = netpolite.get(updater.BASE_URL + "/prices/yugioh.json.gz", timeout=60)
        r.raise_for_status()
        data = json.loads(gzip.decompress(r.content))
        rows = data.get("p") or {}
        day = pricehist.today()
        currency.load()
        if currency.from_usd(1.0) is None:   # no rate yet (e.g. first price fetch in this game): fetch ECB rate
            currency.refresh(max_age=0)
        hist, est, n_eur, n_usd = {}, [], 0, 0
        with carddb.connection(plain=True) as con:
            con.execute("CREATE TABLE IF NOT EXISTS price_est (sid TEXT PRIMARY KEY)")
            con.execute("DELETE FROM price_est")
            # Cardmarket € comes from YGOPRODeck PER CARD (its cheapest print): only right for a card with exactly one
            # print – otherwise every print got it (Blue-Eyes LOB-001 at 0.02 €). Then € from the print's TCGplayer
            # price (≈) or none: rather no price than a wrong one (also against an older server sending it anyway)
            name_of = dict(con.execute("SELECT id, name FROM cards"))
            # prints of the data pack only: the merged ones (ygo-locale) carry no price and don't make a card "multi"
            con.execute("CREATE TABLE IF NOT EXISTS locale_ids (id TEXT PRIMARY KEY) WITHOUT ROWID")
            prints = dict(con.execute("SELECT name, COUNT(*) FROM cards WHERE id NOT IN (SELECT id FROM locale_ids) "
                                      "GROUP BY name"))
            known = set(name_of)
            upd = []
            for sid, vals in rows.items():
                if sid not in known or not isinstance(vals, list) or len(vals) < 2:
                    continue
                cm, usd = _num(vals[0]), _num(vals[1])
                usd1 = _num(vals[2]) if len(vals) > 2 else None
                eur = cm if prints.get(name_of[sid]) == 1 else None
                if eur is None and usd:
                    e = currency.from_usd(usd)
                    eur = round(e, 2) if e else None
                    if eur is not None:
                        est.append((sid,))
                upd.append((eur, usd, usd1, sid))
                n_eur += eur is not None
                n_usd += usd is not None
                h = {"e": day}
                if eur is not None:
                    h["cn"] = [[day, eur]]
                if usd is not None:
                    h["tn"] = [[day, usd]]
                hist[sid] = h
            if len(rows) > 1000:   # a full price list: prints of multi-print cards missing from it lose the per-card
                # price they may still carry (data pack, older price lists) – single-print cards keep theirs
                upd += [(None, None, None, sid) for sid in known - set(rows) if prints.get(name_of[sid], 0) > 1]
            con.executemany("UPDATE cards SET eur = ?, usd = ?, usd_foil = ? WHERE id = ?", upd)
            con.executemany("INSERT OR IGNORE INTO price_est VALUES (?)", est)
            con.execute("INSERT OR REPLACE INTO meta VALUES ('prices_fetched', ?)", (str(time.time()),))
            con.commit()
        YuGiOh._est = None
        multi = {sid for sid, name in name_of.items() if prints.get(name, 0) > 1}
        _clean_cm_history(multi, day)
        from .base import write_hist
        write_hist(hist, day)
        return n_eur, n_usd

    _est = None

    def price_estimated(self, sid):
        """Is this printing's euro price converted from TCGplayer (no Cardmarket price)? -> "≈" in front."""
        if YuGiOh._est is None:
            from cards import carddb
            try:
                with carddb.connection() as con:
                    YuGiOh._est = {r[0] for r in con.execute("SELECT sid FROM price_est")}
            except sqlite3.Error:
                YuGiOh._est = set()
        return sid in YuGiOh._est


CM_FIX = "ygo_cm_per_card_cleared"   # meta key in the price history: the one-time cleanup below has run


def _clean_cm_history(multi, day):
    """Once: the Cardmarket points recorded before the per-card fix (0.9.3) are wrong for cards with several prints –
    each print got the card's cheapest price. Drop them (before `day`) for those prints; TCGplayer points and cards
    with one print stay. A wrong history is worse than a short one. Backup of the file first."""
    import shutil
    from cards import pricehist
    if not pricehist.exists():
        return
    hc = pricehist._connect()
    try:
        if hc.execute("SELECT 1 FROM meta WHERE k = ?", (CM_FIX,)).fetchone():
            return
        hc.close()
        hc = None
        shutil.copy2(pricehist.DB, pricehist.DB.with_name("price-history.before-cm-fix.sqlite"))
        hc = pricehist._connect()
        fixed = []
        for sid, blob in hc.execute("SELECT sid, data FROM hist").fetchall():
            if sid not in multi:
                continue
            rec = pricehist._unpack(blob)
            keep = [pt for pt in rec.get("cn") or [] if pt[0] >= day]
            if keep == (rec.get("cn") or []):
                continue
            if keep:
                rec["cn"] = keep
            else:
                rec.pop("cn", None)
            fixed.append((pricehist._pack(rec), sid))
        hc.executemany("UPDATE hist SET data = ? WHERE sid = ?", fixed)
        hc.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (CM_FIX, str(day)))
        hc.commit()
        log.info("Price history: Cardmarket points before the fix removed for %d prints of multi-print cards",
                 len(fixed))
    finally:
        if hc is not None:
            hc.close()


GAME = YuGiOh()
