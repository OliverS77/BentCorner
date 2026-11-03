"""Magic: The Gathering – the first (and so far only complete) game description.

Card data and images from Scryfall (carddb), price history from MTGJSON (pricehist), deck rules in decks/deckcore.
What is here used to be scattered across several files; those files now get it from here.
"""
import re

from system.i18n import tr
from .base import Game

# Prerelease date stamp: gold, bottom right of the art ("22–23 April 2017", Japanese walkers "2019年4月27—28日").
# OCR runs month and year together ("23APR12017") – month + year is enough; a year alone is not (© lines …).
# Measured on 279 reference images × 8 bench kinds: found in about half of the stamped frames, 0 of 1814 others.
DATE_BAND = (0.50, 0.44, 0.97, 0.60)   # x0, y0, x1, y1 of the straightened card
_DATE_STAMP = re.compile(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z0-9]{0,4}\s*(19|20)\d\d"
                         r"|(19|20)\d\d\s*年\s*\d{1,2}\s*月")


def date_stamp_in(text):
    """OCR text of DATE_BAND -> is it a prerelease date stamp?"""
    return _DATE_STAMP.search((text or "").upper()) is not None


class Magic(Game):
    key = "mtg"
    subdir = ""   # models/ and data/fp_build/ directly, not in a subfolder (from before there were other games)
    price_source = "mtgjson"   # MTGJSON today/history + Scryfall bulk – not the daily Cardmarket guide
    name = "Magic: The Gathering"
    short = "mtg"
    # Marketplaces: Cardmarket game folder, TCGplayer category, search word for eBay/Kleinanzeigen
    market = {"cardmarket": "Magic", "tcgplayer": "magic", "search_word": "mtg"}
    # Deck formats (deck building) – order = selection list
    formats = (("commander", "Commander"), ("standard", "Standard"), ("pioneer", "Pioneer"), ("modern", "Modern"),
               ("legacy", "Legacy"), ("vintage", "Vintage"), ("pauper", "Pauper"),
               ("constructed", "Constructed (60)"), ("limited", "Limited (40)"), ("casual", "Casual / free"))
    default_format = "commander"
    # simple formats without a legality list: Constructed (≥ 60) and Limited (≥ 40), each at most 4 per card
    open_formats = ("", "casual", "constructed", "limited")
    playtest = {"hand": 7, "mulligan": "london"}   # London mulligan: draw 7, put one card per mulligan on the bottom
    deck_size = {"commander": 100}
    # Legalities on the card (Scryfall keys): short for the search, long for the detail view
    legal_short = (("standard", "Standard"), ("pioneer", "Pioneer"), ("modern", "Modern"), ("legacy", "Legacy"),
                   ("vintage", "Vintage"), ("commander", "Commander"), ("pauper", "Pauper"))
    legal_long = (("standard", "Standard"), ("pioneer", "Pioneer"), ("modern", "Modern"), ("legacy", "Legacy"),
                  ("vintage", "Vintage"), ("commander", "Commander"), ("oathbreaker", "Oathbreaker"),
                  ("pauper", "Pauper"), ("paupercommander", "Pauper EDH"), ("penny", "Penny Dreadful"),
                  ("brawl", "Brawl"), ("standardbrawl", "Standard Brawl"), ("historic", "Historic"),
                  ("timeless", "Timeless"), ("alchemy", "Alchemy"), ("explorer", "Explorer"),
                  ("gladiator", "Gladiator"), ("duel", "Duel Commander"), ("premodern", "Premodern"),
                  ("oldschool", "Old School"), ("predh", "PreDH"), ("future", "Future"))
    type_order = (("Creature", "Kreaturen"), ("Planeswalker", "Planeswalker"), ("Battle", "Schlachten"),
                  ("Instant", "Spontanzauber"), ("Sorcery", "Hexereien"), ("Artifact", "Artefakte"),
                  ("Enchantment", "Verzauberungen"), ("Land", "Länder"))
    rarities = (("common", "Common"), ("uncommon", "Uncommon"), ("rare", "Rare"), ("mythic", "Mythic"),
                ("special", "Special"), ("bonus", "Bonus"))
    finishes = (("nonfoil", "Normal"), ("foil", "Foil"), ("etched", "Etched Foil"), ("glossy", "Glossy"))
    adv_search = True
    deck_extras = ("commander", "brew", "tokens", "combos")   # deck building extras only for Magic
    card_px = (336, 468)   # 63 × 88 mm
    colors = ("W", "U", "B", "R", "G", "C", "M")   # color filter of the search (C colorless, M multicolor)
    # advanced search: colors need room for 7 buttons + 3 mode keys; sets get by with the short OR/AND
    adv_stretch = {"sets": 2.6, "colors": 3.4}

    online_details = True            # rulings and all prints from Scryfall; without a card database: web search
    text_recognition = True          # name + collector line read and looked up (ocrscan) – besides the AI
    print_check_after_count = False  # the print is settled before counting (aiscan.resolve_print, otherwise ask)
    stamp_check = True               # … except prerelease promos: same art + collector line, only the date stamp differs

    def print_twins(self, con, entry):
        """The List (plst "MKM-123"): the original print plus a small symbol bottom left – same art, same collector
        line, the scanner can't read the symbol (yet). The prerelease twin is foil-only: not counted as foil -> not
        a candidate (and with foil, _stamp_check reads the stamp)."""
        row = con.execute("SELECT * FROM cards WHERE set_code = 'plst' AND number = ?",
                          (f"{entry['set'].upper()}-{entry['number']}",)).fetchone()
        return [dict(row)] if row else []

    def stamped_twin(self, con, entry):
        """The prerelease promo of the counted print: same name and artist, set "p" + set, the same digits in the
        number (Scryfall: 97 -> 97s, 234★ -> 234s★ – the printed collector line is the same), promo_types
        "datestamped". Exactly one, otherwise None (foil-only, so the art group without foil never offers it)."""
        num = re.sub(r"\D", "", str(entry["number"]))
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM cards WHERE name = ? AND set_code = ? AND promo_types LIKE '%datestamped%' AND artist = "
            "(SELECT artist FROM cards WHERE set_code = ? AND number = ?)",
            (entry["name"], "p" + entry["set"].lower(), entry["set"].lower(), str(entry["number"])))]
        rows = [r for r in rows if num and re.sub(r"\D", "", r["number"]) == num]
        return rows[0] if len(rows) == 1 else None

    def has_stamp(self, card):
        import cv2
        from scanner import ocrscan   # _lines runs the OCR under the GPU lock (fingerprint._run_lock)
        small = cv2.resize(card, (ocrscan.W, ocrscan.H), interpolation=cv2.INTER_AREA)
        return date_stamp_in(" ".join(t[0] for t in ocrscan._lines(ocrscan._box(small, DATE_BAND))))

    def same_image_prints(self, con, entry, index, allow_foil=False):
        """Same name + same artist (Scryfall: reprints keep their artwork) – foil-only prints too (prerelease "46s",
        special foils): a print the scanner can't tell apart is never counted silently (aiscan.resolve_print decides
        or asks). Double-faced cards: the entry carries the face's name, the database the whole one ("A // B")."""
        own = con.execute("SELECT artist, name FROM cards WHERE set_code = ? AND number = ?",
                          (entry["set"].lower(), str(entry["number"]))).fetchone()
        artist = own["artist"] if own else None
        name = own["name"] if own else entry["name"]
        q = "SELECT * FROM cards WHERE name = ?" + (" AND artist = ?" if artist else "")
        return [dict(r) for r in con.execute(q, (name, artist) if artist else (name,))]

    # ---------- Sets and images from Scryfall (cards/library.py asks the game) ----------
    def bundled_sets(self):
        import json
        import pathlib
        import sys
        base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1]))
        try:
            return json.loads((base / "setliste.json").read_text("utf-8"))
        except (OSError, ValueError):
            return []

    def cached_sets(self):
        """The saved copy of Scryfall's set list, otherwise the bundled one – never the network."""
        import json
        from cards import library
        try:
            data = json.loads(library.CATALOG.read_text("utf-8"))
            if data:
                return data
        except (OSError, ValueError):
            pass
        return self.bundled_sets()

    def sets_catalog(self, max_age=7 * 24 * 3600):
        """All paper sets from Scryfall. Cached; max_age=0 forces a fresh query (~1 s)."""
        import json
        import requests
        from cards import library
        cached = []
        if library.CATALOG.exists():
            try:
                cached = json.loads(library.CATALOG.read_text("utf-8"))
            except ValueError:
                pass
        fresh = cached and "type" in cached[0] and library.catalog_age() < max_age
        if fresh:
            return cached
        try:
            sets = [{"code": s["code"], "name": s["name"], "released": s.get("released_at", ""),
                     "count": s.get("card_count", 0), "type": s.get("set_type", ""),
                     "parent": s.get("parent_set_code")}
                    for s in library._get(f"{library.API}/sets")["data"] if not s.get("digital") and s.get("card_count")]
            library.REF.mkdir(parents=True, exist_ok=True)
            library.CATALOG.write_text(json.dumps(sets, ensure_ascii=False), "utf-8")
            return sets
        except (requests.RequestException, OSError, ValueError):
            return cached or self.bundled_sets()

    def set_info(self, code):
        """(name, parent set code or None) from Scryfall."""
        import requests
        from cards import library
        try:
            s = library._get(f"{library.API}/sets/{code}")
            return s["name"], s.get("parent_set_code")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                raise RuntimeError(tr(f"There is no set with the code “{code}” on Scryfall.")) from None
            raise

    def set_cards(self, code, progress=lambda text, done, total: None):
        """Cards of a set -> [(entry as in the set files, image URL)] – one Scryfall search."""
        from cards import library
        raw = library.search(f"e:{code}")
        if not raw:
            raise RuntimeError(tr(f"Scryfall has no cards for {code.upper()}."))
        return [p for c in raw for p in library.card_entries(c)]

    def print_languages_online(self, set_code, number):
        from cards import carddb
        from cards import library
        from net import netpolite
        r = netpolite.get(f"{library.API}/cards/search", headers=library.HEADERS, timeout=20,
                          params={"q": f'e:{set_code} cn:"{number}" lang:any', "unique": "prints",
                                  "include_multilingual": "true"})
        if r.status_code == 404:
            return []
        r.raise_for_status()
        order = list(carddb.LANG_NAMES)
        rows = sorted(r.json().get("data", []), key=lambda c: order.index(c["lang"]) if c["lang"] in order else 99)
        return [(c["lang"], carddb.LANG_NAMES.get(c["lang"], c["lang"].upper()), c["id"],
                 c.get("printed_name") or c["name"]) for c in rows]

    def fetch_lang_print(self, entry, lang, target, missing):
        """Scryfall: the printing in that language with the images of all its faces -> the image matching
        entry's face (the front face if a face isn't available separately)."""
        from cards import library
        from net import netpolite
        from scanner.common import BASE, image_rel, lang_img
        r = netpolite.get(f"{library.API}/cards/{entry['set'].lower()}/{entry['number']}/{lang}",
                          headers=library.HEADERS, timeout=20)
        if r.status_code == 404:
            raise LookupError(missing)
        r.raise_for_status()
        c = r.json()
        faces = [c] if "image_uris" in c else [f for f in c.get("card_faces", []) if "image_uris" in f]
        for fi, f in enumerate(faces):
            path = BASE / lang_img(image_rel(c["set"], c["collector_number"], fi), lang)
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(library.fetch_bytes(f["image_uris"]["normal"]))
        if not (BASE / target).exists():  # face not available separately in this language -> front face
            target = lang_img(image_rel(c["set"], c["collector_number"], 0), lang)
        return target if (BASE / target).exists() else None

    def image_url(self, set_code, number, lang="en", version="normal", face=0):
        """Image straight from Scryfall (the API redirects to the image) – for cards without a local image and for
        other languages. face=1: the back of a double-faced card."""
        import requests
        url = f"https://api.scryfall.com/cards/{str(set_code).lower()}/{requests.utils.quote(str(number))}"
        if lang and lang != "en":
            url += f"/{lang}"
        return url + f"?format=image&version={version}" + ("&face=back" if face else "")

    def card_url(self, set_code, number):
        """The card's page at the data source."""
        return f"https://scryfall.com/card/{str(set_code).lower()}/{number}"

    @property
    def data(self):
        from cards import carddb
        return carddb

    @property
    def prices(self):
        from cards import pricehist
        return pricehist

    def card_type(self, row):
        front = (row.get("type_line") or "").split("//")[0]
        for key, _ in self.type_order:
            if key in front:
                return key
        return "Other"


GAME = Magic()
