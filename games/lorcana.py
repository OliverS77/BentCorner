"""Disney Lorcana TCG – card data from LorcanaJSON (lorcanajson.org: static files, no key).

LorcanaJSON asks to check metadata.json (generatedOn) before downloading again and to prefer the zipped files; no
limits are stated, so we stay careful (netpolite). The data comes from the official Lorcana app and is "used under
Ravensburger's Community Code Policy" – nothing may be charged for it. Whether we may ship it in a data pack is not
clarified (the user decides) – so the app can also build the database itself from the four zipped files (EN DE FR
IT, ~5 MB): build_db() is used by both tools/build_lorcana_db.py and download_db().

The card database has carddb.SCHEMA's format, columns as in Magic:
    id "<set>-<number>" ("1-5", enchanted "1-205", promos by their grouping "p1-12", variants "3-4a")
    name = full name "Hades - King of Olympus" (copies in a deck are counted by it), oracle_id = simpleName
    type_line "Character — Storyborn · Hero · Princess", "Action — Song"
    oracle_text = card text, cmc = ink cost, colors = inks (letters, see INKS), keywords = keyword abilities
    power/toughness = strength/willpower, loyalty = lore, mana_cost = move cost (Locations)
    layout "landscape" for Locations, frame_effects "inkable", promo_types = promo grouping ("P1")
    legalities {"core": "legal", "infinity": "legal"} – only the formats the card is allowed in right now
Extra tables: images (per language: the official image addresses), formats (allowedInFormats with dates),
ext (Cardmarket / TCGplayer product numbers), limits (maxCopiesInDeck), langs (names in DE FR IT), set_names (set
names in EN DE FR IT – the quick search finds "das erste kapitel hades").

Images: the official Ravensburger addresses (api.lorcana.ravensburger.com), per language – not in any data pack;
the app gets them through our image mirror (/dl/lorcana, net/netpolite.MIRROR), each fetched once from Ravensburger.
"""
import io
import json
import re
import sqlite3
import time
import zipfile

from system.i18n import tr
from .base import Game, daily_prices

FILES = "https://lorcanajson.org/files/current"
LANGS = ("en", "de", "fr", "it")
CM_GUIDE = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_19.json"   # 19 = Lorcana
TCG_PRICES = "lorcana-tcgplayer.json.gz"   # on our price server (server/prices fetches TCGCSV 71 once for everyone)
BUILD = "2"   # meta.pk_build – higher = newer (2: table set_names); an older database is rebuilt once
# Inks -> letters in cards.colors (palette); dual-ink cards carry both
INKS = (("Amber", "A"), ("Amethyst", "M"), ("Emerald", "E"), ("Ruby", "R"), ("Sapphire", "S"), ("Steel", "T"))
ORIGINS = ("Storyborn", "Dreamborn", "Floodborn")
PROMO_NAMES = {"P1": "Promos 1", "P2": "Promos 2", "P3": "Promos 3", "P4": "Promos 4", "PD1": "Disney100 Promos",
               "D23": "D23 Promos", "C1": "Challenge Promos 1", "C2": "Challenge Promos 2", "DIS": "Disneyland Promos",
               "RPH": "Ravensburger Promos", "CC1": "Convention Promos"}
# Symbols in the card text (LorcanaJSON uses the in-game glyphs) – most fonts don't have them
SYMBOLS = {"⬡": "{I}", "◊": "{L}", "¤": "{S}", "⛉": "{W}", "⟳": "{E}"}


def _net():
    from net import netpolite
    return netpolite


def _text(c):
    """Card text: one line per ability (the line breaks inside a section are only the printed wrapping)."""
    parts = [" ".join(s.split()) for s in c.get("fullTextSections") or []]
    text = "\n".join(p for p in parts if p)
    for k, v in SYMBOLS.items():
        text = text.replace(k, v)
    return text


def _type_line(c):
    subs = list(c.get("subtypes") or [])
    return c.get("type", "") + (" — " + " · ".join(subs) if subs else "")


def _inks(c):
    letters = dict(INKS)
    names = c.get("colors") or [x for x in (c.get("color") or "").split("-") if x]
    return "".join(letters[n] for n in names if n in letters)


# ---------- Collector line (bottom left): "5/204 • EN • 1", promos "8/P1 • EN • 1" or "1 TFC • EN • 2/P1" ----------
# OCR reads the bullet "•" as ·, *, -, e … or not at all – hence "anything that isn't a letter or digit" between the
# parts. Number: digits (an O read for a 0 is fine) + an optional variant letter (4a, 24A); a leading 0 read as D
# ("D1/D23" for "01/D23") too. Set size: digits (base sets, quests; a 0 read as O or D: "2D4") or the promo grouping
# (P1, PD1, D23, DIS …), which then IS the set. The old promo form "1 TFC • EN • 2/P1" names the base set first and
# then number/grouping (OCR often drops the space: "1TFC").
_SEP = r"[^A-Za-z0-9]+"
_LANGS = {"EN": "en", "DE": "de", "FR": "fr", "IT": "it", "JA": "ja", "JP": "ja"}
_NUM = r"\d[\dOo]{0,2}"
_TOTAL = r"\d[\dOoD]{0,2}"   # set size: only decides which part names the set – never the card itself
_FOOT = re.compile(rf"(?<![A-Za-z0-9])((?:D(?=\d))?{_NUM}[A-Ea-e]?)\s*/\s*([A-Za-z]{{1,3}}\d{{0,3}}|{_TOTAL}){_SEP}"
                   rf"([A-Za-z]{{2}}){_SEP}([QqPp]?\d{{1,2}})(?![A-Za-z0-9])")
_FOOT_PROMO = re.compile(rf"(?<![A-Za-z0-9])\d{{1,2}}\s*[A-Za-z]{{2,4}}{_SEP}([A-Za-z]{{2}}){_SEP}({_NUM})\s*/\s*"
                         rf"([A-Za-z]{{1,3}}\d{{0,2}})(?![A-Za-z0-9])")


def _letters(s):
    """Only the letters, upper case ("Hades - King of Olympus" -> "HADESKINGOFOLYMPUS") – for comparing OCR text."""
    return re.sub(r"[^A-ZÀ-Ý]", "", (s or "").upper())


def _digits(s):
    """OCR mix-ups in a part that can only hold digits: O → 0, I/l → 1."""
    return s.translate(str.maketrans("OoIl", "0011"))


def footer_parse(text):
    """Collector line read by OCR -> {"set", "number", "lang"} (as in the card database: set "1", "q1", "p1"; number
    "5", "4a") or None. Exact on purpose – the scanner counts only exact set + number hits."""
    m = _FOOT_PROMO.search(text or "")
    if m:
        lang, number, code = m.group(1).upper(), _digits(m.group(2)), m.group(3).upper()
    else:
        m = _FOOT.search(text or "")
        if not m:
            return None
        number, total, lang, set_no = m.group(1), m.group(2).upper(), m.group(3).upper(), m.group(4).upper()
        if number[0] == "D":   # leading 0 read as D ("D1/D23")
            number = "0" + number[1:]
        if number[-1].isalpha() and number[-1] not in "Oo":   # variant letter (4a)
            number = _digits(number[:-1]) + number[-1].lower()
        else:
            number = _digits(number)
        numeric = _digits(total).isdigit() or (total[0].isdigit() and _digits(total.replace("D", "0")).isdigit())
        code = set_no if numeric else total   # set size -> the set is the last part ("1", "Q1")
    if lang not in _LANGS:
        return None
    from cards import carddb
    return {"set": code.lower(), "number": carddb.norm_number(number), "lang": _LANGS[lang]}


def _ident(c):
    """(set code, number) of a print: promos by their grouping (P1 …), the variant letter at the number (4a)."""
    grp = c.get("promoGrouping") or ""
    return (grp or str(c["setCode"])).lower(), f"{c['number']}{(c.get('variant') or '').lower()}"


def _finishes(c):
    ft = set(c.get("foilTypes") or [])
    out = (["nonfoil"] if "None" in ft or not ft else []) + (["foil"] if ft - {"None"} else [])
    return ",".join(out)


def _legal(c):
    return {fmt.lower(): "legal" for fmt, v in (c.get("allowedInFormats") or {}).items() if v.get("allowed")}


def read_zip(blob):
    """Contents of an allCards.json.zip -> dict."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    return json.loads(z.read(next(n for n in z.namelist() if n.endswith(".json"))))


def build_db(data, out, progress=lambda text, done, total: None):
    """Card database from LorcanaJSON's allCards per language ({"en": {...}, "de": {...}, …}; English must be
    there – it has all cards, the others are subsets with the same IDs). -> number of prints."""
    from cards import carddb
    en = data["en"]
    sets = en.get("sets") or {}
    by_id = {c["id"]: c for c in en.get("cards") or []}
    other = {lg: {c["id"]: c for c in (d or {}).get("cards") or []} for lg, d in data.items() if lg != "en"}
    rows, imgs, fmts, ext, limits, langs = [], [], [], [], [], []
    seen = set()
    for n, c in enumerate(by_id.values(), 1):
        if n % 500 == 0:
            progress(tr("Card database: converting …"), n, len(by_id))
        if c.get("number") is None:
            continue   # token-like cards without a number
        sc, num = _ident(c)
        sid = f"{sc}-{num}"
        if sid in seen:
            continue
        seen.add(sid)
        st = sets.get(str(c["setCode"])) or {}
        grp = c.get("promoGrouping") or ""
        rar = (c.get("rarity") or "").lower()
        img = c.get("images") or {}
        rows.append({
            "id": sid, "oracle_id": c.get("simpleName") or c["fullName"].lower(), "name": c["fullName"], "lang": "en",
            "set_code": sc, "set_name": PROMO_NAMES.get(grp, f"Promos {grp}") if grp else st.get("name") or sc.upper(),
            "number": num, "rarity": rar, "released": st.get("releaseDate") or "", "type_line": _type_line(c),
            "oracle_text": _text(c), "mana_cost": str(c["moveCost"]) if c.get("moveCost") is not None else None,
            "cmc": c.get("cost"), "colors": _inks(c), "color_identity": _inks(c),
            "keywords": ", ".join(c.get("keywordAbilities") or []), "artist": c.get("artistsText"),
            "flavor_text": c.get("flavorText"),
            "power": str(c["strength"]) if c.get("strength") is not None else None,
            "toughness": str(c["willpower"]) if c.get("willpower") is not None else None,
            "loyalty": str(c["lore"]) if c.get("lore") is not None else None,
            "layout": "landscape" if c.get("type") == "Location" else "normal", "finishes": _finishes(c),
            "booster": 0 if grp or rar == "special" or st.get("type") == "quest" else 1,
            "img_normal": img.get("full"), "img_small": img.get("thumbnail"), "legalities": json.dumps(_legal(c)),
            "reserved": 0, "game_changer": 0, "promo_types": grp, "frame_effects": "inkable" if c.get("inkwell") else "",
            "border_color": "", "full_art": 1 if rar in ("enchanted", "iconic") else 0})
        imgs.append((sid, "en", img.get("full"), img.get("thumbnail")))
        langs.append((sc, num, "en", sid, c["fullName"]))
        for lg, cards in other.items():
            o = cards.get(c["id"])
            if o:
                oi = o.get("images") or {}
                imgs.append((sid, lg, oi.get("full"), oi.get("thumbnail")))
                langs.append((sc, num, lg, sid, o.get("fullName") or c["fullName"]))
        for fmt, v in (c.get("allowedInFormats") or {}).items():
            fmts.append((sid, fmt.lower(), 1 if v.get("allowed") else 0, v.get("allowedUntilDate"),
                         v.get("bannedSinceDate")))
        links = c.get("externalLinks") or {}
        if links.get("cardmarketId") or links.get("tcgPlayerId"):
            ext.append((sid, "", links.get("cardmarketId"), links.get("tcgPlayerId"), None))
        if "maxCopiesInDeck" in c:
            limits.append((sid, c["maxCopiesInDeck"]))   # None = any number
    set_names = sorted({(str(code).lower(), lg, s["name"]) for lg, d in data.items()
                        for code, s in ((d or {}).get("sets") or {}).items() if s.get("name")})
    progress(tr("Card database: building search index …"), 0, 0)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".new.sqlite")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        con.executescript(carddb.SCHEMA)
        cols = [r[1] for r in con.execute("PRAGMA table_info(cards)")]
        con.executemany(f"INSERT INTO cards ({','.join(cols)}) VALUES ({','.join(':' + k for k in cols)})",
                        [{k: r.get(k) for k in cols} for r in rows])
        con.executescript("CREATE TABLE images (sid TEXT, lang TEXT, full TEXT, thumb TEXT);"
                          "CREATE TABLE formats (sid TEXT, fmt TEXT, allowed INTEGER, until TEXT, banned_since TEXT);"
                          "CREATE TABLE ext (sid TEXT, variant TEXT, cm INTEGER, tcg INTEGER, tcg_group INTEGER);"
                          "CREATE TABLE limits (sid TEXT PRIMARY KEY, copies INTEGER);"
                          "CREATE TABLE set_names (code TEXT, lang TEXT, name TEXT);")
        con.executemany("INSERT INTO set_names VALUES (?,?,?)", set_names)
        con.executemany("INSERT INTO images VALUES (?,?,?,?)", imgs)
        con.executemany("INSERT INTO formats VALUES (?,?,?,?,?)", fmts)
        con.executemany("INSERT INTO ext VALUES (?,?,?,?,?)", ext)
        con.executemany("INSERT INTO limits VALUES (?,?)", limits)
        con.executemany("INSERT INTO langs VALUES (?,?,?,?,?)", langs)
        con.executescript(carddb.INDEXES)
        con.executescript("CREATE INDEX images_sid ON images(sid, lang); CREATE INDEX formats_sid ON formats(sid);"
                          "CREATE INDEX ext_sid ON ext(sid);")
        made = {lg: (d or {}).get("metadata", {}).get("generatedOn", "") for lg, d in data.items()}
        con.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)",
                        [("cards", str(len(rows))), ("langs", str(len(langs))), ("languages", "1"),
                         ("pk_build", BUILD), ("updated", str(time.time())), ("source", "LorcanaJSON"),
                         ("generated", json.dumps(made))])
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()
    tmp.replace(out)
    return len(rows)


class Lorcana(Game):
    key = "lorcana"
    name = "Disney Lorcana"
    short = "lorcana"
    market = {"cardmarket": "Lorcana", "tcgplayer": "lorcana-tcg", "search_word": "lorcana"}
    formats = (("core", "Core"), ("infinity", "Infinity"), ("casual", "Casual / free"))
    default_format = "core"
    legal_short = (("core", "Core"), ("infinity", "Infinity"))
    legal_long = legal_short
    type_order = (("Character", "Characters"), ("Action", "Actions"), ("Item", "Items"), ("Location", "Locations"))
    card_types = ("Character", "Action", "Item", "Location")
    rarities = (("common", "Common"), ("uncommon", "Uncommon"), ("rare", "Rare"), ("super rare", "Super Rare"),
                ("legendary", "Legendary"), ("epic", "Epic"), ("enchanted", "Enchanted"), ("iconic", "Iconic"),
                ("special", "Special / Promo"))
    palette = "".join(k for _, k in INKS)
    search_example = "i:amber t:song"
    data_note = ("All cards with inks, classifications, Core/Infinity legality and names in EN DE FR IT – Bent°Corner "
                 "builds it itself from LorcanaJSON (a few MB, loaded again only when something changed). Card images "
                 "come one by one from Ravensburger while you browse.")
    color_hint = "Double-click an ink = exactly this one, again = without this ink"
    deck_tagline = "Build Core or Infinity decks – with ink curve, rules check and ownership"
    counter_tiers = (("Enchanted", ("enchanted", "iconic", "epic")), ("Legendary", ("legendary",)))
    deck_sources = ("Dreamborn", "Inkdecks")
    color_words = {**{n.lower(): k for n, k in INKS},   # i:amber, i:amber,steel – also the German ink names
                   "bernstein": "A", "smaragd": "E", "rubin": "R", "saphir": "S", "stahl": "T"}
    color_specials = ""
    color_hex = {"A": "#f2b230", "M": "#8a4fb0", "E": "#2f9a4c", "R": "#d23a3a", "S": "#2f8fd0", "T": "#9aa3ad"}
    color_names = {k: n for n, k in INKS}
    ranges = (("mv", "Cost", 0), ("pow", "Strength", 0), ("tou", "Willpower", 0), ("loy", "Lore", 0),
              ("move", "Movement", 0), ("price", "Price (€)", 2))   # Movement = move cost (short: label column)
    text_fields = (("oracle", "Card text"), ("name", "Name"), ("type", "Type line"), ("keyword", "Keywords"),
                   ("flavor", "Flavor text"), ("artist", "Artist"))
    adv_titles = {"colors": "Ink", "super": "Traits", "kw": "Keywords", "sub": "Classifications",
                  "format": "Format"}
    adv_hints = {"sub": "e.g. Hero, Princess, Pirate", "kw": "e.g. Evasive, Shift, Ward"}
    # widths: ink needs room for its three mode keys, values for German "Willenskraft", classifications for the title
    adv_stretch = {"sets": 2.6, "colors": 3.5, "range": 3.6, "sub": 3.0}
    adv_hidden = ()
    supertypes = tuple((o, o) for o in ORIGINS) + (("Song", "Song"), ("Inkable", "Inkable"))
    supertypes_mode = "all"
    supertypes_none = False
    # supertypes that aren't words in the type line: SQL condition instead (carddb._filters)
    flag_terms = {"Inkable": "COALESCE(c.frame_effects, '') LIKE '%inkable%'"}
    lib_types_off = ()
    # printed in EN DE FR IT (IT since set 3) and JA (since 2025, Takara Tomy) – no source has Japanese data:
    # JA only for cards in the collection
    languages = ("en", "de", "fr", "it", "ja")
    lang_pack = "bundled"   # names and images in DE FR IT are part of the database
    # images come from the publisher's server, one by one per user: only what's visible (+ a little ahead), never
    # whole sets
    prefetch_ahead = 36
    bulk_images = False
    adv_search = True
    finishes = (("nonfoil", "Normal"), ("foil", "Cold Foil"))
    FINISHES = (("nonfoil", "Normal", "N", False), ("foil", "Cold Foil", "F", True))
    foil_word = "Foil"
    colors = ()
    pack_types = [
        {"key": "booster", "name": "Booster", "counts": True},
        {"key": "lor_display", "name": "Booster Display (24)", "counts": False},
        {"key": "lor_trove", "name": "Illumineer's Trove", "counts": False},
        {"key": "lor_gift", "name": "Gift Set", "counts": False},
        {"key": "lor_starter", "name": "Starter Deck", "counts": False},
        {"key": "lor_quest", "name": "Illumineer's Quest", "counts": False},
        {"key": "promo", "name": "Promo / insert", "counts": False},
        {"key": "other", "name": "Other", "counts": False},
        {"key": "trade", "name": "Trade", "counts": False},
        {"key": "purchase", "name": "Single purchase", "counts": False},
    ]
    # Language detection: name + version on the band below the art; the bottom line "5/204 • EN • 1" names the
    # language itself (scanner work follows)
    lang_layout = {"name": (0.06, 0.55, 0.94, 0.66), "words": [], "type_words": {}, "partial": True}
    # Scanner: where the collector line sits on the straightened card – ((x0, y0, x1, y1), degrees clockwise to read
    # it). Measured on the official images (1468 × 2048, the same layout for Enchanted/Epic/Iconic): line at 96–98.5 %
    # of the height, 4–19 % of the width. Generous, because the scanner straightens the card with ~4 % margin (dark
    # borders) – the artist line read with it doesn't bother footer_parse. Locations are stored upright too, turned
    # 90°: their line runs down the right edge – or along the top left if the card lies the other way round.
    footer_bands = (((0.0, 0.89, 0.5, 1.0), 0),)
    # A number line closer than 5 % to the band's edge may be cut off (scan bench: tilted Enchanted 9-240 read twice as
    # "40/204 • EN • 9", line at 3.1–3.4 %) – then the print's name must be on the card (footer_confirm). Measured on
    # all 288 bench frames: right reads that start that close always show their name; the closest right read without
    # a readable name (thumb over it) starts at 7.4 %.
    footer_margin = 0.05
    NAME_BAND = (0.0, 0.42, 1.0, 0.75)   # name + version (+ classifications) – on the upright card, landscape too
    _classes = None

    def footer_confirm(self, card, got, degrees):
        """Is a word of the print's name or version (English or the read language, at least 4 letters, not a
        classification like "Princess") in the card's name area? ~130 ms OCR, only for reads close to the edge."""
        import cv2
        from cards import carddb
        from scanner import ocrscan
        sid = f"{got['set']}-{got['number']}"
        try:
            with carddb.connection() as con:
                names = [r[0] for r in con.execute("SELECT name FROM langs WHERE id = ? AND lang IN ('en', ?)",
                                                   (sid, got.get("lang") or "en"))]
                if Lorcana._classes is None:
                    Lorcana._classes = {_letters(w) for (tl,) in con.execute("SELECT DISTINCT type_line FROM cards")
                                        for w in re.split(r"[\s·—]+", tl or "")}
        except sqlite3.Error:
            return False
        words = {w for w in (_letters(x) for n in names for x in re.split(r"[\s\-–,'’.!?]+", n))
                 if len(w) >= 4 and w not in Lorcana._classes}
        turn = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
        view = cv2.rotate(card, turn[degrees]) if degrees in turn else card   # upright (Locations: wide)
        text = _letters(" ".join(t[0] for t in ocrscan._lines(ocrscan._box(view, self.NAME_BAND))))
        return any(w in text for w in words)

    def footer_needs_confirm(self, got):
        """A variant letter (4b, 24a) counts only with the name on the card: OCR reads 8 as B and 0 as D ("48/204" ->
        "4B/204" names the existing card 3-4b) – no fallback to the digits, the next frame reads again."""
        return got["number"][-1:].isalpha()
    footer_bands_landscape = (((0.89, 0.78, 1.0, 1.0), 90), ((0.0, 0.0, 0.11, 0.22), 270))

    @staticmethod
    def footer_parse(text):
        return footer_parse(text)
    card_px = (336, 468)   # 63 × 88 mm like Magic
    features = {"scan", "sessions", "library", "decks", "testing", "trade", "import"}
    # Deck building (decks.analyze_generic, decks.rule_warnings) – official rules: at least 60 cards, at most 4 per full
    # name (name + version; exceptions in limits: maxCopiesInDeck), at most 2 inks, no sideboard. Core rotates,
    # Infinity has all sets – both with their own ban list (allowedInFormats); a reprint makes older prints legal
    deck_rules = {
        "core": {"size": 60, "exact": False, "copies": 4, "legal": "core", "max_colors": 2, "colors_word": "inks"},
        "infinity": {"size": 60, "exact": False, "copies": 4, "legal": "infinity", "max_colors": 2,
                     "colors_word": "inks"},
        "casual": {"size": 60, "exact": False, "copies": 4, "max_colors": 2, "colors_word": "inks"},
    }
    deck_cost_column = False
    # Test: 7 cards; once, any number of them face down on the bottom, draw as many, shuffle; the first player doesn't
    # draw on turn 1; cards go face down into the inkwell
    playtest = {"hand": 7, "mulligan": "bottom_any", "inkwell": True}

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

    def info_rows(self, row):
        """Card values for the detail view: [(label, value)]."""
        out = []
        if row.get("type_line"):
            out.append((tr("Card type"), row["type_line"]))
        if row.get("cmc") is not None:
            out.append((tr("Cost"), f"{row['cmc']:g}"))
        out.append((tr("Inkwell"), tr("yes") if "inkable" in (row.get("frame_effects") or "") else tr("no")))
        if row.get("colors"):
            names = dict((k, n) for n, k in INKS)
            out.append((tr("Ink"), " · ".join(tr(names[x]) for x in row["colors"] if x in names)))
        for key, label in (("power", "Strength"), ("toughness", "Willpower"), ("loyalty", "Lore"),
                           ("mana_cost", "Move cost")):
            if row.get(key):
                out.append((tr(label), str(row[key])))
        return out

    # ---------- Deck building ----------
    def deck_curve(self):
        """Ink cost 1 … 7+ – highlighted: the inkable cards (they can also go into the inkwell)."""
        labels = ["1", "2", "3", "4", "5", "6", "7+"]

        def bin_(r):
            if r.get("cmc") is None:
                return None, False
            return max(0, min(6, int(r["cmc"]) - 1)), "inkable" in (r.get("frame_effects") or "")
        return {"title": "Ink cost", "sub": "", "labels": labels, "inner": "Inkable", "bin": bin_}

    def deck_roles(self):
        import re
        return {
            "Draw": (re.compile(r"\bdraws? (?:a|an|\d+|that many|cards?)", re.I), "draws extra cards"),
            "Removal": (re.compile(r"\b(?:banish|return (?:chosen|an?|that|all) [^.]*?(?:character|item|location)s? "
                                   r"to (?:their|its) (?:player's|owner's) hand)", re.I),
                        "banishes cards or returns them to the hand"),
            "Ramp": (re.compile(r"into (?:your|their) inkwell|additional (?:ink|card into your inkwell)", re.I),
                     "puts extra cards into the inkwell"),
            "Lore": (re.compile(r"gains? \d+ lore|\+\d+ \{L\}", re.I), "gains lore or gives more lore"),
        }

    def deck_kpis(self, a):
        t = a["types"]
        return [("Cards", a["count"], "at least 60"), ("Characters", t.get("Character", 0), ""),
                ("Actions", t.get("Action", 0), ""), ("Items", t.get("Item", 0), ""),
                ("Locations", t.get("Location", 0), "")]

    def deck_name_key(self, row):
        return row.get("name") or ""

    _limits = None

    def _limit_of(self, row):
        """maxCopiesInDeck of the card: missing = the usual 4, None = any number (Lorcana.limits table)."""
        if Lorcana._limits is None:
            from cards import carddb
            try:
                with carddb.connection() as con:
                    Lorcana._limits = {n: k for n, k in con.execute(
                        "SELECT c.name, l.copies FROM limits l JOIN cards c ON c.id = l.sid")}
            except sqlite3.Error:
                Lorcana._limits = {}
        return Lorcana._limits.get(row.get("name"), 4)

    def deck_unlimited(self, row):
        return self._limit_of(row) is None   # e.g. Microbots

    def deck_copy_limit(self, row):
        k = self._limit_of(row)
        return k if k not in (None, 4) else None   # Dalmatian Puppy 99, The Glass Slipper 2

    def deck_legal_names(self, names, fmt):
        """Legal by full name: if any print of the card is allowed in the format, older prints are too (reprints)."""
        from cards import carddb
        names = sorted({n for n in names if n})
        if not names or not carddb.exists():
            return set()
        with carddb.connection() as con:
            rows = con.execute(f"SELECT DISTINCT name FROM cards WHERE name IN ({','.join('?' * len(names))}) "
                               f"AND legalities LIKE ?", names + [f'%"{fmt}"%']).fetchall()
        return {r[0] for r in rows}

    def playtest_groups(self):
        return super().playtest_groups() + [("Inkable", lambda r: "inkable" in (r.get("frame_effects") or ""))]

    _img = {}

    def image_url(self, set_code, number, lang="en", version="normal"):
        """Official image (Ravensburger) of the print in that language – None if there is none."""
        from cards import carddb
        sid = f"{str(set_code).lower()}-{str(number).lower()}"
        key = (sid, lang or "en")
        if key not in self._img:
            try:
                with carddb.connection() as con:
                    r = con.execute("SELECT full, thumb FROM images WHERE sid = ? AND lang = ?", key).fetchone()
            except sqlite3.Error:
                r = None
            self._img[key] = tuple(r) if r else None
        r = self._img[key]
        if not r:
            return None
        return r[1] if version == "small" else r[0]

    def set_names(self):
        """Set names in every language of the source: {code: {lang: name}} (quick search "das erste kapitel")."""
        from cards import carddb
        out = {}
        try:
            with carddb.connection() as con:
                for code, lg, name in con.execute("SELECT code, lang, name FROM set_names"):
                    out.setdefault(code, {})[lg] = name
        except sqlite3.Error:   # older database without the table
            pass
        return out

    # ---------- Set list: from the card database (Game.sets_catalog) ----------
    def set_type(self, code, promo_types):
        return "promo" if promo_types else ("quest" if code.startswith("q") else "expansion")

    # ---------- Card database ----------
    db_target = True   # download_db takes the target file (carddb.download)

    def download_db(self, progress=lambda text, done, total: None, db=None):
        """From the data pack if there is one, otherwise straight from LorcanaJSON (four zipped files) – only when
        metadata.json says something changed (generatedOn), as LorcanaJSON asks. The zipped files stay next to the
        database (lorcanajson/, ~5 MB): a newer BUILD of ours rebuilds from them without downloading again, and a
        change in one language loads only that one. db = target file (default: the open game's). -> (cards, 0)"""
        from cards import carddb
        db = db or carddb.DB_PATH
        current = db == carddb.DB_PATH
        if current and carddb._from_bundle():
            n = carddb.status() or {}
            return n.get("cards", 0), 0
        net = _net()
        old, built = {}, 0
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                meta = dict(con.execute("SELECT key, value FROM meta WHERE key IN ('generated', 'pk_build')"))
                old, built = json.loads(meta.get("generated") or "{}"), int(meta.get("pk_build") or 0)
            finally:
                con.close()
        except (sqlite3.Error, ValueError):
            old, built = {}, 0
        cache = db.parent / "lorcanajson"
        cache.mkdir(parents=True, exist_ok=True)
        data, changed = {}, not db.exists() or built < int(BUILD)
        for i, lg in enumerate(LANGS):
            progress(tr("Card database: asking LorcanaJSON …"), i, len(LANGS))
            r = net.get(f"{FILES}/{lg}/metadata.json", timeout=30)
            r.raise_for_status()
            made = r.json().get("generatedOn", "")
            kept = cache / f"allCards-{lg}.json.zip"
            if made and made == old.get(lg) and kept.exists():
                try:
                    data[lg] = read_zip(kept.read_bytes())   # unchanged: from our copy, nothing downloaded
                    continue
                except (OSError, ValueError, zipfile.BadZipFile):
                    pass
            if made and made == old.get(lg) and not changed:
                continue   # unchanged and the database is current: nothing to do for this language
            changed = True
            r = net.get(f"{FILES}/{lg}/allCards.json.zip", timeout=300, headers={"Accept": "application/zip"})
            if lg != "en" and r.status_code == 404:
                continue   # a language missing: then without it
            r.raise_for_status()
            data[lg] = read_zip(r.content)
            kept.write_bytes(r.content)
        if not changed:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                return con.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 0
            finally:
                con.close()
        for lg in LANGS:   # only some languages changed and no copy of the others: load them too (one database)
            if lg not in data:
                r = net.get(f"{FILES}/{lg}/allCards.json.zip", timeout=300, headers={"Accept": "application/zip"})
                if r.ok:
                    data[lg] = read_zip(r.content)
                    (cache / f"allCards-{lg}.json.zip").write_bytes(r.content)
        if "en" not in data:
            raise RuntimeError(tr("LorcanaJSON: the English card list is missing."))
        new = db.with_name("cards.lorcanajson.sqlite")
        n = build_db(data, new, progress)
        if db.exists():   # keep today's prices until the next price update
            con = sqlite3.connect(new)
            try:
                con.execute("ATTACH DATABASE ? AS old", (str(db),))
                con.execute("UPDATE cards SET (eur, eur_foil, usd, usd_foil) = (SELECT o.eur, o.eur_foil, o.usd, "
                            "o.usd_foil FROM old.cards o WHERE o.id = cards.id) WHERE id IN (SELECT id FROM old.cards)")
                con.commit()
                con.execute("DETACH DATABASE old")
            except sqlite3.Error:
                pass
            finally:
                con.close()
        new.replace(db)
        if current:
            carddb._meta_cache.clear()
            carddb._SET_CODES = None
            self._img.clear()
        return n, 0

    # ---------- Daily prices: Cardmarket price guide (once a day) + TCGplayer via our price server ----------
    def update_prices(self, progress=lambda text, done, total: None, sets=None):
        """Cardmarket's daily file for Lorcana (all cards, idProduct = cardmarketId) and TCGplayer from our own
        price server (TCGCSV 71, built daily for everyone – the app never asks TCGCSV). Without the server file
        (not deployed yet / offline) just without TCGplayer. -> (prints with Cardmarket price, with TCGplayer)"""
        from cards import carddb
        with carddb.connection() as con:
            try:
                ext = con.execute("SELECT sid, cm, tcg FROM ext").fetchall()   # cm = cardmarketId, tcg = tcgPlayerId
            except sqlite3.Error:
                ext = []
        return daily_prices(ext, CM_GUIDE, TCG_PRICES, ("Cold Foil", "Holofoil"), progress)   # foil: Cold Foil first


GAME = Lorcana()
