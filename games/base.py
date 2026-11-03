"""What a game description must provide (base.Game). A game overrides only what differs for it.

The description bundles everything game-specific in one place; the rest of the code asks games.current() instead
of knowing Magic details itself. Fields:

    key, name, short          ID, name, abbreviation (for marketplace searches, e.g. "mtg")
    data                      card database (module with search, cards_by_ids, by_names, exists, …)
    prices                    price history (module with series, hint, …) – None = none
    market                    paths/search words for marketplaces (Cardmarket game, TCGplayer category, eBay word)
    formats, default_format   deck formats [(key, name)] and the default
    open_formats              formats without a legality list (every card allowed – rules only from deck_rules)
    type_order                order of card types in the decklist [(key, heading)]
    rarities                  rarities in order [(key, name)]
    finishes                  finishes (normal / Foil / …)
    legal_short, legal_long   legalities for search and detail view respectively [(key, name)]
    colors                    color codes for the search's color filter
    deck_size                 fixed deck sizes per format {format: cards}
    card_px                   card image size for recognition (the game's aspect ratio)
    card_url(set, number)     the card's page at the data source
    palette, color_specials   color filter: real colors/types (letters in cards.colors) and special buttons
                              (Magic: C colorless, M multicolor); color_hex/color_names for buttons and tooltips
    ranges, text_fields       value ranges [(key, name, decimals)] and text fields of the search
    adv_titles, adv_hidden    headings and hidden sections of the advanced search respectively
    supertypes                second type list of the search ([(word in the type line, name)], Magic: supertypes)
    languages                 languages of the printings (codes like collection.LANGS) – None: all, as in Magic
    deck_rules                deck rules (see deckrules.py): size, copies, exceptions, sideboard …
    flag_terms                supertypes that aren't words in the type line: {name: SQL condition} (Inkable)
    info_rows(row)            card values for the detail view (None = as for Pokémon)
    features                  which tabs already work (None = all)
    price_source              "daily": own daily prices (update_prices – Cardmarket guide + TCGplayer from our server),
                              the price history grows by itself; "mtgjson": Magic – prices from MTGJSON/Scryfall, the
                              90-day history loadable on request (settings show different tiles)
"""


class Game:
    key = ""
    name = ""
    short = ""
    data = None
    prices = None
    price_source = "daily"
    market = {}
    formats = ()
    default_format = ""
    open_formats = ("", "casual")
    type_order = ()
    rarities = ()
    finishes = (("nonfoil", "Normal"), ("foil", "Foil"))
    adv_search = False   # advanced search (per-game filters) ready? Otherwise "Coming soon" over it
    foil_word = "Foil"   # second finish in prices and chart (Pokémon: "Reverse Holo")
    # Language detection while scanning (langcheck): None = Magic layout; otherwise {"name": band, "words": [bands],
    # "type_words": {language: [words]}, "partial": name may be part of the line read}
    lang_layout = None
    price_trend_word = True   # price line "Cardmarket Trend Foil" (False: "Cardmarket Reverse Holo")
    legal_short = ()
    legal_long = ()
    colors = ()
    deck_size = {}
    card_px = (336, 468)   # card image for recognition (63:88, common format)
    # ---- Optional parts: None/False/() = the game doesn't have it (asked as `g.update_prices is not None` …) ----
    download_db = None        # (progress[, db]) -> (cards, languages): own card source instead of Scryfall's bulk files
    merge_extra = None        # (db path) -> after the data pack's database is installed: add data kept apart (YGO)
    db_target = False         # download_db takes the target file (a download for another game never hits the open one)
    update_prices = None      # (progress, sets=None) -> (with Cardmarket price, with TCGplayer price): daily prices
    market_fix = None         # () -> marketplace corrections from the data pack (Pokémon: cm_fix.json)
    heal_prints = False       # prints may leave the database: references move to the English print (printmove)
    price_lookup = None       # (card ID) -> (eur, eur_foil) or None: price of a single card while scanning (Pokémon)
    variants_of = None        # (sid) -> finishes of a print from the source data (Pokémon: normal, holo, reverse …)
    image_url = None          # (set, number, lang, version) -> image address of a print in a language
    rarity_short = None       # (rarity name) -> short form for a chip ("Ultra Rare" -> "UR", Yu-Gi-Oh!)
    card_types = None         # advanced search: card types (None = Magic's, carddb.CARD_TYPES)
    supertypes = ()           # advanced search: second type list [(word in the type line, name)]
    flag_terms = {}           # supertypes that aren't words in the type line: {name: SQL condition} (Inkable)
    variant_numbers = False   # rarities as separate prints with a suffix on the number (Yu-Gi-Oh!)
    pack_types = None         # pack types of the sessions [{key, name, counts}] (None = Magic's, packtypes.py)
    footer_parse = None       # (collector line text) -> {"set", "number", "lang"} or None: the scanner reads it
    footer_bands = ()         # where the collector line sits on the straightened card ((x0, y0, x1, y1)[, degrees])
    footer_bands_landscape = ()   # the same for landscape cards lying turned on the straightened image

    @property
    def subdir(self):
        """Subfolder of the game in models/ and data/fp_build/ ("" = directly there, Magic)."""
        return self.key
    palette = "WUBRG"
    color_specials = "CM"
    color_hex = {"W": "#f4ecc8", "U": "#4a90d9", "B": "#8c7f86", "R": "#e0553d", "G": "#3f9b5a", "C": "#b6b6b6",
                 "M": "#d7b46a"}
    color_names = {}
    ranges = (("mv", "Manawert", 0), ("pow", "Stärke", 0), ("tou", "Widerstand", 0), ("price", "Preis (€)", 2))
    text_fields = (("oracle", "Regeltext"), ("name", "Name"), ("type", "Typzeile"), ("keyword", "Keyword-Text"),
                   ("flavor", "Flavor-Text"), ("artist", "Künstler"))
    adv_titles = {}
    adv_hidden = ()
    regulation_marks = ()   # advanced search: regulation marks (Pokémon: A … J, column promo_types) – none: section hidden
    adv_stretch = {}        # advanced search: widths of the sections that differ from SearchBox.STRETCH
    adv_hints = {"sub": "e.g. Elf, Human, Dragon", "kw": "e.g. Flying, Trample"}   # examples in the input fields
    supertypes_mode = "all"     # supertypes: all selected required (Magic); "any" = one of them
    supertypes_none = True      # entry "no supertype"
    lib_types_off = ("Land",)   # library: these card types off initially
    languages = None
    # Language pack (Settings → Card data): "download" = separate download, can be removed/loaded (Magic:
    # Scryfall language index); "bundled" = built into the shipped database (Pokémon)
    lang_pack = "download"
    lang_images = True   # are there card images in the other languages? (Yu-Gi-Oh!: English only)
    # Image servers that must be spared (Lorcana: the publisher's own): the library preloads only this many tiles
    # from the first visible one (None = the whole result list), and nothing loads whole sets of images at once
    # (set download, scanner preloading) when bulk_images is False
    prefetch_ahead = None
    bulk_images = True
    # several prints share one image address (Yu-Gi-Oh!: one image per passcode): imgcache.fetch then takes an image
    # already on disk under another print instead of downloading the same file again
    shared_images = False
    # No card images at all (set by games.current() for a game that is only unlocked locally, not released): no
    # image request leaves the program – tiles show name and number, the detail its text. image_hosts: the game's
    # image servers, blocked in netpolite then (also addresses straight from the card database).
    images_off = False
    image_hosts = ()
    # search field: example syntax in the placeholder (must work in this game) and words for c:/i: (Lorcana i:amber)
    search_example = 'k:flying o:"draw a card"'
    color_words = {}
    # hint under the color buttons of the advanced search (games without Magic's C/M buttons)
    color_hint = "Double-click a color = exactly this one, again = without this color"
    # Settings → card data: what the card database tile says about where the data comes from (English, tr())
    data_note = ("Needed for: library “All cards”, search and advanced search, deck building, print matching. Comes with "
                 "the game's data (Scryfall, about 110 MB) – with all languages.")
    # scanner, collector line (footer_parse games): a line that starts closer than this to the band's edge (share of
    # the band width) may be cut off (digits missing) – it then needs footer_confirm; 0 = no check
    footer_margin = 0.0

    def footer_confirm(self, card, got, degrees):
        """A collector line read close to the edge: does the rest of the card agree with the print it names?
        card = straightened card (scanner working size), got = footer_parse result, degrees = rotation of the band
        that was read. Default: no further check (only games with footer_margin get here)."""
        return True

    def footer_needs_confirm(self, got):
        """Does this read need footer_confirm wherever it sits (e.g. Lorcana: a variant letter "4b" – OCR also makes
        it out of "48")? Default: no."""
        return False

    # Counters on the scan page / stream (session stats keys "mythic", "rare", "foil" – kept for saved data): the two
    # rarity levels worth counting [(label, rarities)] and the word for the third counter (foil cards)
    counter_tiers = (("Mythic", ("mythic",)), ("Rare", ("rare",)))
    counter_foil = "Foil"

    def counter_third(self, entry):
        """Does a counted card go into the third counter? Default: foil cards (other games: e.g. parallels)."""
        return bool(entry.get("foil"))
    # Decks page: subtitle and where deck lists usually come from (import)
    deck_tagline = "Build Commander or other formats – with curve, bracket, tokens and ownership"
    deck_sources = ("Moxfield", "Archidekt")
    deck_rules = None
    features = None

    def card_url(self, set_code, number):
        return ""

    def card_type(self, row):
        """Card type key of a row (for the decklist groups)."""
        return "Other"

    def counter_labels(self):
        """The three counter names of the scan page / stream: top level, second level, foil."""
        return self.counter_tiers[0][0], self.counter_tiers[1][0], self.counter_foil

    def set_names(self):
        """Set names in other languages for the quick search: {code: {lang: name}} – {} = only the English names of
        the card database (Magic: from the data pack, setnames.json)."""
        return {}

    def info_rows(self, row):
        """Card values for the detail view [(label, value)] from a card database row – None: the default (type
        line, HP, weakness, retreat as for Pokémon)."""
        return None

    def finish_info(self, row):
        """Finishes of a printing for the card image toggle -> (["nonfoil", "foil"] etc., {"n": text, "f": text}).
        row = library row (with "card" and "sid")."""
        fin = (row.get("card") or {}).get("finishes") or []
        out = (["nonfoil"] if "nonfoil" in fin else []) + (["foil"] if ("foil" in fin or "etched" in fin) else [])
        return out or ["nonfoil", "foil"], {"n": "Non-Foil", "f": "Foil"}

    # Finishes of a printing (finishes.py): first = base finish; foil = uses the foil price
    FINISHES = (("nonfoil", "Non-Foil", "N", False), ("foil", "Foil", "F", True), ("etched", "Etched", "E", True))

    def finish_options(self, card):
        """Magic (and default): as in the card data – Non-Foil, Foil, Etched."""
        fin = card.get("finishes") or []
        keys = [k for k, *_ in self.FINISHES if k in fin] or ["nonfoil", "foil"]
        return [{"key": k, "label": lb, "short": sh, "foil": f} for k, lb, sh, f in self.FINISHES if k in keys]

    def editions(self, card):
        """Editions that exist for the printing (Pokémon: 1st Edition) – Magic: none."""
        return []

    def price_estimated(self, sid):
        """Euro price only converted (e.g. from TCGplayer, as Cardmarket is missing)? Then "≈" is shown in front."""
        return False

    def format_name(self, key):
        return dict(self.formats).get(key, key or "")

    # ---------- Deck building (only for games with deck_rules; Magic uses decks.analyze) ----------
    deck_extras = ()   # Magic extras in deck building: "commander", "brew", "tokens", "combos"

    def deck_curve(self):
        """The "curve" of the deck info: {"title", "sub", "labels", "inner" (name of the highlighted subset),
        "bin": row -> (bin or None, highlighted?)}."""
        return {"title": "Kurve", "sub": "", "labels": [], "inner": "", "bin": lambda r: (None, False)}

    def deck_roles(self):
        """Roles in the deck: {name: (regex on the rules text, explanation)}."""
        return {}

    def deck_kpis(self, a):
        """Key figures at the top: [(name, value, subtitle)]."""
        return [("Karten", a["count"], "")]

    def deck_unlimited(self, row):
        """Card without copy limit (Magic: basic lands, Pokémon: basic Energy)?"""
        return False

    def deck_name_key(self, row):
        """What copies are counted by (name; for Pokémon without the set suffix)."""
        return row.get("name") or ""

    deck_cost_column = True   # deck list: "Cost" column (Magic mana cost) – other games have no such cost

    def deck_zone(self, row):
        """Zone of a card on the main board (Yu-Gi-Oh!: "extra" for Fusion/Synchro/Xyz/Link) – "main" otherwise."""
        return "main"

    # ---------- Sets and images (cards/library.py asks the game) ----------
    def sets_catalog(self, max_age=7 * 24 * 3600):
        """All sets [{code, name, released, count, type, parent}] – standard: from the card database (Magic and
        Pokémon ask their online source instead)."""
        import sqlite3
        from cards import carddb
        if not carddb.exists():
            return []
        try:   # a broken/unfinished database must never stop the game switch (app._switch_now) – no sets then
            with carddb.connection() as con:
                rows = con.execute("SELECT set_code, set_name, MIN(released), COUNT(*), MIN(promo_types) FROM cards "
                                   "GROUP BY set_code").fetchall()
        except sqlite3.Error:
            __import__("logging").getLogger("booster").exception("Set list from the card database")
            return []
        return [{"code": c, "name": n or c.upper(), "released": rel or "", "count": k, "type": self.set_type(c, promo),
                 "parent": None} for c, n, rel, k, promo in rows]

    def set_type(self, code, promo_types):
        """Kind of a set for sorting the set list ("expansion", "promo" … see library.TYPE_RANK; "" = no kinds)."""
        return ""

    def set_info(self, code):
        """(name, parent set) of a set."""
        for s in self.sets_catalog():
            if s["code"].lower() == code.lower():
                return s["name"], None
        from system.i18n import tr
        raise RuntimeError(tr(f"There is no set with the code “{code}”."))

    def set_cards(self, code, progress=lambda text, done, total: None):
        """Cards of a set -> [(entry as in the set files, image URL)] – standard: from the card database."""
        import sqlite3
        from cards import carddb
        if not carddb.exists():
            return []
        try:
            with carddb.connection() as con:
                rows = [dict(r) for r in con.execute("SELECT * FROM cards WHERE set_code = ? ORDER BY number",
                                                     (code.lower(),))]
        except sqlite3.Error:
            __import__("logging").getLogger("booster").exception("Set cards from the card database")
            return []
        return [(carddb.entry_from_row(r), r["img_normal"]) for r in rows if r.get("img_normal")]

    def bundled_sets(self):
        """Set list shipped with the app (first start without internet) – only Magic has one."""
        return []

    def cached_sets(self):
        """Set list available instantly without network."""
        return self.sets_catalog(max_age=10 ** 12)

    def print_languages_online(self, set_code, number):
        """Languages of a printing from an online service when the card database doesn't know them -> [(code,
        display name, ID, printed name)] – only Magic asks Scryfall."""
        return []

    def fetch_lang_print(self, entry, lang, target, missing):
        """Download the image of a printing in another language to BASE/target -> target. The game's own image
        address in that language (library.image_url); missing: the message if there is none."""
        from cards import library
        from net import netpolite
        from scanner.common import BASE
        url = library.image_url(entry["set"], entry["number"], lang, "normal")
        r = netpolite.get(url, headers={"User-Agent": library.HEADERS["User-Agent"]}, timeout=20) if url else None
        if r is None or r.status_code == 404 or not r.content.startswith((b"\xff\xd8", b"\x89PNG", b"RIFF")):
            raise LookupError(missing)
        r.raise_for_status()
        (BASE / target).parent.mkdir(parents=True, exist_ok=True)
        (BASE / target).write_bytes(r.content)
        return target

    # card details (rulings, all prints …) and the search across all sets come from an online service (Magic:
    # Scryfall – its card database is large, languages separate); False = everything from the local card database
    online_details = False

    # ---------- Scanner ----------
    text_recognition = False         # full text recognition (name + collector line -> card database) – Magic only
    # same artwork in several prints: count the image match's pick right away, read the collector line afterwards in
    # the background (app._print_check) – Magic settles the print before counting (aiscan.resolve_print)
    print_check_after_count = True
    # a special print that only a stamp on the card tells apart (same art, same collector line – Magic: prerelease
    # date stamp): checked after counting, in the background (Recognizer._stamp_check)
    stamp_check = False
    # The user's rule: if the print isn't certain, ask (never count blindly). Several prints with the counted
    # image -> the collector line must decide before counting, otherwise the print question (aiscan.sure_print).
    # False = the old way (count the image match's pick, correct afterwards).
    print_ask = True

    def print_twins(self, con, entry):
        """Prints the scanner can't tell from entry by image or collector line (Magic: The List) -> [row]."""
        return []

    def narrow_twins(self, card, entry, rows):
        """Of the counted print and its twins (rows), the ones that fit what the card itself shows (card: the
        straightened card image or None) – e.g. the language of the name. Default: all of them. -> [row]"""
        return rows

    def stamped_twin(self, con, entry):
        """The one stamped special print of the counted print -> row, or None (none, or several = no change)."""
        return None

    def has_stamp(self, card):
        """Does the straightened card show that stamp?"""
        return False

    def same_image_prints(self, con, entry, index, allow_foil=False):
        """All prints with the same image as `entry` (card database connection con) -> [row], [] = only this one.
        Here (Pokémon, Lorcana …): same name + artist often means a completely different image – so only
        prints whose fingerprints are (almost) the same, and only of the same language group (Japanese vs. western
        prints: the image match tells them apart, the number often doesn't)."""
        from scanner.aiscan import ART_SAME, ASIAN
        me = con.execute("SELECT * FROM cards WHERE set_code = ? AND number = ?",
                         (entry["set"].lower(), str(entry["number"]))).fetchone()
        if me is None:
            return []
        rows = [dict(r) for r in con.execute("SELECT * FROM cards WHERE name = ? AND artist IS ?",
                                             (me["name"], me["artist"]))]
        mine = index.vector(f"{me['id']}_0") if index is not None else None
        if mine is None:
            return []
        asia = (me["lang"] or "en") in ASIAN

        def same(r):
            v = index.vector(f"{r['id']}_0")
            return v is not None and ((r["lang"] or "en") in ASIAN) == asia and float(v @ mine) >= ART_SAME
        rows = [r for r in rows if r["id"] == me["id"] or same(r)]
        return rows if len(rows) > 1 else []

    # ---------- Test (solo playtest, collection/playtest.py) ----------
    playtest = {"hand": 7, "mulligan": None}

    def playtest_groups(self):
        """Card groups for the opening-hand chances: [(name, predicate)] – card types and the deck functions
        (deck_roles), plus what the game adds (Basic Pokémon …)."""
        out = [(label, lambda r, k=key: self.card_type(r) == k) for key, label in self.type_order]
        out += [(name, lambda r, rx=rx: bool(rx.search(r.get("oracle_text") or "")))
                for name, (rx, _help) in self.deck_roles().items()]
        return out

    def playtest_basic(self, row):
        """Pokémon mulligan: does this card make a hand playable (a Basic Pokémon)? Other games: always."""
        return True

    def deck_copy_limit(self, row):
        """The card's own copy limit instead of the format's (Lorcana: maxCopiesInDeck) – None = the usual."""
        return None

    def deck_ban_limit(self, row):
        """Banlist: allowed copies of this card (0 forbidden, 1 limited, 2 semi-limited) or None = normal."""
        return None

    def deck_legal_names(self, names, fmt):
        """Names legal in the format regardless of the printing (Pokémon: a reprint makes older prints legal) – or
        None = judge every printing by its own legalities."""
        return None


def tcgplayer_table(net, cache, name):
    """TCGplayer prices of one game from our own price server (server/prices, file `name`, e.g.
    "pokemon-tcgplayer.json.gz"): {group: {product: {subTypeName: market $ or None}}}. TCGCSV asks not to be queried
    from user apps, so the server fetches it once a day for everyone – never TCGCSV directly. Kept in `cache`, asked
    at most once a day and conditionally (ETag – an unchanged file is not downloaded again). Never raises: server
    unreachable = the last cached file (stale=True, no new history point); nothing cached = {}. -> (table, stale)"""
    import gzip
    import json
    import os
    import time
    from net import updater

    def read():
        return json.loads(gzip.decompress(cache.read_bytes())).get("g") or {}
    try:
        if time.time() - cache.stat().st_mtime < 20 * 3600:
            return read(), False
    except (OSError, ValueError):
        pass
    try:
        from net import netpolite
        r = net.get(f"{updater.BASE_URL}/prices/{name}", headers=netpolite.cond_headers(cache), timeout=60)
        if r.status_code == 304:   # same file as our copy: nothing downloaded, check again in a day
            os.utime(cache)
            return read(), False
        r.raise_for_status()
        table = json.loads(gzip.decompress(r.content)).get("g") or {}
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(cache.name + ".tmp")
        tmp.write_bytes(r.content)
        tmp.replace(cache)
        netpolite.remember(cache, r)
        return table, False
    except Exception:  # noqa: BLE001 – offline / file missing on the server: keep the last state
        try:
            return read(), True
        except (OSError, ValueError):
            return {}, True


def daily_file(net, url, cache, progress=None):
    """A source's daily file (Cardmarket price guide …): downloaded at most once a day – later calls on the same day
    ("on every start", "on close", a game switch) read the local copy `cache`. -> bytes"""
    import time
    try:
        if time.strftime("%Y-%m-%d", time.localtime(cache.stat().st_mtime)) == time.strftime("%Y-%m-%d"):
            return cache.read_bytes()
    except OSError:
        pass
    raw = net.get_large(url, headers={"Accept": "application/json"}, progress=progress)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(cache.name + ".tmp")
        tmp.write_bytes(raw)
        tmp.replace(cache)
    except OSError:
        pass
    return raw


# ---------- Daily prices (shared by the games with a Cardmarket price guide) ----------
def cardmarket_guide(url, progress=lambda text, done, total: None):
    """{idProduct: row} of Cardmarket's daily price guide (one file per game, at most once a day – daily_file)."""
    import json
    from cards import carddb
    from net import netpolite
    from system.i18n import tr
    label = tr("Prices: loading the Cardmarket price guide …")
    progress(label, 0, 0)
    raw = daily_file(netpolite, url, carddb.DB_PATH.parent / "cardmarket-guide.json",
                     progress=lambda d, t: progress(label, d >> 20, t >> 20))
    return {g["idProduct"]: g for g in (json.loads(raw).get("priceGuides") or [])}


def cardmarket_entry(g, day):
    """One row of the guide -> ({"eur", "eur_foil"}, history entry or None). The history entry carries the averages
    of 30/7/1 days ago next to today's trend (write_hist keeps them only the first time)."""
    e = {}
    for key, sfx in (("cn", ""), ("cf", "-holo")):
        pts = [(day - 30, g.get("avg30" + sfx)), (day - 7, g.get("avg7" + sfx)), (day - 1, g.get("avg1" + sfx)),
               (day, g.get("trend" + sfx))]
        pts = [[d, round(float(p), 2)] for d, p in pts if p]
        if pts:
            e[key] = pts
    if e:
        e["e"] = day
    return {"eur": g.get("trend"), "eur_foil": g.get("trend-holo")}, (e or None)


def tcgplayer_point(prices, hist, sid, normal, foil, day, stale):
    """Enter TCGplayer $ (normal, foil) for a printing; a history point only from today's file (not when stale)."""
    p = prices.setdefault(sid, {})
    p["usd"], p["usd_foil"] = normal, foil
    e = hist.setdefault(sid, {"e": day})
    for key, v in (("tn", normal), ("tf", foil)):
        if v and not stale:
            e[key] = [[day, round(float(v), 2)]]


def write_prices(prices):
    """{sid: {"eur", "eur_foil", "usd", "usd_foil"}} into the card database (missing values keep the old ones)."""
    import time
    from cards import carddb
    with carddb.connection(plain=True) as con:
        con.executemany("UPDATE cards SET eur = COALESCE(?, eur), eur_foil = COALESCE(?, eur_foil), "
                        "usd = COALESCE(?, usd), usd_foil = COALESCE(?, usd_foil) WHERE id = ?",
                        [(p.get("eur"), p.get("eur_foil"), p.get("usd"), p.get("usd_foil"), sid)
                         for sid, p in prices.items()])
        con.execute("INSERT OR REPLACE INTO meta VALUES ('prices_fetched', ?)", (str(time.time()),))
        con.commit()


def write_hist(hist, day):
    """Today's points into the price history. The Cardmarket averages (30/7/1 days ago) only for printings that have
    no history yet – after that the real daily price counts."""
    from cards import pricehist
    hc = pricehist._connect()
    try:
        known = {row[0] for row in hc.execute("SELECT sid FROM hist")}
        for sid, e in hist.items():
            if sid in known:
                for key in ("cn", "cf"):
                    if e.get(key):
                        e[key] = [p for p in e[key] if p[0] == day]
        pricehist._write(hc, hist, merge=True)
        hc.execute("INSERT OR REPLACE INTO meta VALUES ('updated', ?)", (str(day),))
        hc.commit()
    finally:
        hc.close()


def daily_prices(ext, cm_url, tcg_file, foil_keys=("Foil",), progress=lambda text, done, total: None):
    """The usual daily prices of a game whose cards know their Cardmarket product and TCGplayer product (ext rows
    (sid, cm, tcg)): Cardmarket guide + TCGplayer from our price server -> card database + price history.
    foil_keys: TCGplayer subTypeNames that count as foil, in order of preference. -> (n Cardmarket, n TCGplayer)"""
    from cards import carddb
    from cards import pricehist
    from net import netpolite
    from system.i18n import tr
    day = pricehist.today()
    guide = cardmarket_guide(cm_url, progress)
    prices, hist = {}, {}
    for sid, cm, _tcg in ext:
        g = guide.get(cm) if cm else None
        if g:
            prices[sid], e = cardmarket_entry(g, day)
            if e:
                hist[sid] = e
    n_cm = len(prices)
    progress(tr("Prices: TCGplayer …"), 0, 0)
    tcg, stale = tcgplayer_table(netpolite, carddb.DB_PATH.parent / "tcgplayer-prices.json.gz", tcg_file)
    by_prod = {str(pid): sub for group in tcg.values() for pid, sub in (group or {}).items()}
    n_tcg = 0
    for sid, _cm, pid in ext:
        sub = by_prod.get(str(pid)) if pid else None
        if not sub:
            continue
        normal = sub.get("Normal")
        foil = next((sub[k] for k in foil_keys if sub.get(k) is not None), None)
        if normal is None and foil is None:
            continue
        tcgplayer_point(prices, hist, sid, normal, foil, day, stale)
        n_tcg += 1
    progress(tr("Entering prices …"), 0, 0)
    write_prices(prices)
    write_hist(hist, day)
    return n_cm, n_tcg
