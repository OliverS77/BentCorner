"""Pokémon TCG – data from TCGdex (api.tcgdex.net, free, no key; images from assets.tcgdex.net).

TCGdex asks for nothing specific, but mentions that running it costs money – hence conservative (netpolite):
card database in pages of 100 cards via GraphQL (~220 requests, a few minutes), prices and finishes only for sets
that are actually loaded (one request per card), images once and then from disk.

The card database has the same format as Magic's (carddb.SCHEMA) – so search, library and sessions work without
special cases. A few Magic columns stay empty (mana cost, colors …), type_line holds
"Pokémon — Stage 1 — Fire" or "Trainer — Item".
"""
import json
import sqlite3
import time

from system.i18n import tr
from .base import Game, cardmarket_entry, cardmarket_guide, tcgplayer_point, tcgplayer_table, write_hist

API = "https://api.tcgdex.net/v2"
CM_GUIDE = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"   # 6 = Pokémon
TCG_PRICES = "pokemon-tcgplayer.json.gz"   # on our server (server/prices fetches TCGCSV once for everyone)
GQL = API + "/graphql"
PAGE = 100
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
_FIELDS = ("id localId name hp types stage illustrator rarity category trainerType energyType image description "
           "set{id} variants{normal reverse holo firstEdition}")


def _net():
    from net import netpolite
    return netpolite


def _gql(query):
    r = _net().post(GQL, json={"query": query}, headers=HEADERS, timeout=60)
    r.raise_for_status()
    d = r.json()
    if d.get("errors"):
        raise RuntimeError(d["errors"][0].get("message") or tr("TCGdex error"))
    return d["data"]


def _rest(path):
    r = _net().get(f"{API}/en/{path}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()



def _slug(text):
    return (text or "").strip().lower()


def _type_line(c):
    cat = c.get("category") or ""
    if cat == "Pokemon":
        parts = ["Pokémon", c.get("stage") or ""] + list(c.get("types") or [])
    elif cat == "Trainer":
        parts = ["Trainer", c.get("trainerType") or ""]
    elif cat == "Energy":
        parts = ["Energy", c.get("energyType") or ""]
    else:
        parts = [cat]
    return " — ".join(p for p in parts if p)


def _finishes(v):
    v = v or {}
    out = []
    if v.get("normal"):
        out.append("nonfoil")
    if v.get("holo") or v.get("reverse"):
        out.append("foil")      # Holo/Reverse Holo: stored as "Foil" in the collection for now
    if v.get("firstEdition"):
        out.append("firstedition")
    return out or ["nonfoil"]


class Pokemon(Game):
    key = "pokemon"
    name = "Pokémon TCG"
    short = "pokemon"
    market = {"cardmarket": "Pokemon", "tcgplayer": "pokemon", "search_word": "pokemon"}
    formats = (("standard", "Standard"), ("expanded", "Expanded"), ("casual", "Casual / free"))
    default_format = "standard"
    deck_size = {"standard": 60, "expanded": 60}
    legal_short = (("standard", "Standard"), ("expanded", "Expanded"))
    legal_long = legal_short
    type_order = (("Pokémon", "Pokémon"), ("Trainer", "Trainer"), ("Energy", "Energie"))
    rarities = (("common", "Common"), ("uncommon", "Uncommon"), ("rare", "Rare"), ("rare holo", "Rare Holo"),
                ("holo rare", "Holo Rare"), ("double rare", "Double Rare"), ("ultra rare", "Ultra Rare"),
                ("illustration rare", "Illustration Rare"), ("special illustration rare", "Special Illustration Rare"),
                ("hyper rare", "Hyper Rare"), ("mega hyper rare", "Mega Hyper Rare"), ("secret rare", "Secret Rare"),
                ("ace spec rare", "ACE SPEC Rare"), ("shiny rare", "Shiny Rare"), ("shiny ultra rare", "Shiny Ultra Rare"),
                ("radiant rare", "Radiant Rare"), ("amazing rare", "Amazing Rare"), ("holo rare v", "Holo Rare V"),
                ("holo rare vmax", "Holo Rare VMAX"), ("holo rare vstar", "Holo Rare VSTAR"),
                ("character rare", "Character Rare"), ("character super rare", "Character Super Rare"),
                ("promo", "Promo"), ("none", "–"))
    # Energy types (cards.colors, tools/build_pokemon_db.py): letters as commonly used on Cardmarket/Limitless
    palette = "GRWLPFDMNYC"
    color_specials = ""
    color_hex = {"G": "#4f9d4a", "R": "#e0553d", "W": "#3d8fd6", "L": "#f2c94c", "P": "#a65fc4", "F": "#b8733a",
                 "D": "#3b4a52", "M": "#9aa3ad", "N": "#b59b3a", "Y": "#e58fb8", "C": "#d9d6cf"}
    color_names = {"G": "Pflanze", "R": "Feuer", "W": "Wasser", "L": "Elektro", "P": "Psycho", "F": "Kampf",
                   "D": "Finsternis", "M": "Metall", "N": "Drache", "Y": "Fee", "C": "Farblos"}
    ranges = (("pow", "KP", 0), ("mv", "Rückzug", 0), ("price", "Preis (€)", 2))
    text_fields = (("oracle", "Attacken & Fähigkeiten"), ("name", "Name"), ("type", "Typzeile"),
                   ("keyword", "Merkmale"), ("flavor", "Pokédex-Text"), ("artist", "Illustrator"))
    adv_titles = {"colors": "Energietyp", "super": "Stufe / Art", "kw": "Merkmale"}
    adv_hidden = ("sub",)
    regulation_marks = tuple("ABCDEFGHIJ")   # printed bottom left; Standard rotates by these letters
    # widths ≈ what each section needs at 1600 px (title + "Reset", 11 energy circles, two columns stage / kind):
    # second row has six sections here (regulation mark)
    adv_hints = {"kw": "e.g. ex, ACE SPEC, Ability"}
    adv_stretch = {"sets": 1.9, "colors": 3.9, "opts": 2.3, "range": 2.2, "count": 2.4, "text": 2.5,
                   "types": 2.35, "super": 2.8, "kw": 2.3, "rarity": 2.45, "format": 2.2, "reg": 2.55}
    supertypes = (("Basic", "Basis"), ("Stage1", "Phase 1"), ("Stage2", "Phase 2"), ("VMAX", "VMAX"),
                  ("VSTAR", "VSTAR"), ("MEGA", "Mega"), ("BREAK", "BREAK"), ("Item", "Item"),
                  ("Supporter", "Unterstützer"), ("Stadium", "Stadion"), ("Tool", "Ausrüstung"),
                  ("Normal", "Basis-Energie"), ("Special", "Spezial-Energie"))
    supertypes_mode = "any"
    supertypes_none = False
    lib_types_off = ()
    # Languages of the printings: Western (DE FR IT ES PT) as language versions of the same card, Asian sets (JA KO ZH
    # TH ID) as separate sets – the languages in one list, as in Magic
    languages = ("en", "de", "fr", "it", "es", "pt", "ja", "ko", "zhs", "zht", "th", "id")
    lang_pack = "bundled"   # other languages are separate printings in the shipped database – not separable
    adv_search = True
    search_example = "t:supporter o:draw"
    data_note = ("All cards with attacks, types, legality, names in all languages (including Asian sets), marketplace "
                 "numbers and prices – comes as a data pack from the Bent°Corner server. “Download” gets the latest from "
                 "TCGdex (a few minutes).")
    deck_tagline = "Build Standard or Expanded decks – with evolution lines, rules check and ownership"
    counter_tiers = (("Ultra+", ("ultra rare", "illustration rare", "special illustration rare", "hyper rare",
                                 "mega hyper rare", "secret rare", "shiny ultra rare", "character super rare")),
                     ("Rare", ("rare", "rare holo", "holo rare", "double rare", "holo rare v", "holo rare vmax",
                               "holo rare vstar", "radiant rare", "amazing rare", "shiny rare", "character rare",
                               "ace spec rare")))
    counter_foil = "Holo"
    deck_sources = ("Pokémon TCG Live", "Limitless")
    finishes = (("nonfoil", "Normal"), ("foil", "Holo / Reverse Holo"), ("firstedition", "1st Edition"))
    colors = ()
    foil_word = "Reverse Holo"
    # Pack types of the sessions (keys booster/promo/other/trade/purchase as in Magic – the program uses those)
    pack_types = [
        {"key": "booster", "name": "Booster", "counts": True},
        {"key": "pk_blister", "name": "Blister", "counts": True},
        {"key": "pk_display", "name": "Booster-Display (36)", "counts": False},
        {"key": "pk_etb", "name": "Top-Trainer-Box", "counts": False},
        {"key": "pk_bundle", "name": "Booster-Bundle", "counts": False},
        {"key": "pk_tin", "name": "Tin", "counts": False},
        {"key": "pk_minitin", "name": "Mini-Tin", "counts": False},
        {"key": "pk_collection", "name": "Kollektion", "counts": False},
        {"key": "pk_premium", "name": "Premium-Kollektion", "counts": False},
        {"key": "pk_buildbattle", "name": "Build & Battle", "counts": False},
        {"key": "pk_deck", "name": "Themendeck", "counts": False},
        {"key": "promo", "name": "Promo / Beilage", "counts": False},
        {"key": "other", "name": "Sonstiges", "counts": False},
        {"key": "trade", "name": "Tausch", "counts": False},
        {"key": "purchase", "name": "Einzelkauf", "counts": False},
    ]
    # Language detection: name top left (next to "Basis"/"Phase 1", hence partial match), language words at the top
    # (stage, trainer kind) and at the bottom (weakness / resistance / retreat)
    lang_layout = {
        "name": (0.04, 0.025, 0.74, 0.10),
        "names": [(0.04, 0.025, 0.74, 0.10), (0.03, 0.02, 0.96, 0.20)],   # Pokémon at the top; Trainer: banner + name
        "words": [(0.03, 0.015, 0.40, 0.065), (0.03, 0.855, 0.97, 0.935)],
        "partial": True,
        "type_words": {
            "en": ["basic", "stage", "trainer", "supporter", "item", "stadium", "weakness", "resistance", "retreat"],
            "de": ["basis", "phase", "trainer", "unterstützer", "item", "stadion", "schwäche", "resistenz", "rückzug"],
            "fr": ["base", "niveau", "dresseur", "supporter", "objet", "stade", "faiblesse", "résistance", "retraite"],
            "it": ["base", "fase", "allenatore", "aiuto", "strumento", "stadio", "debolezza", "resistenza",
                   "ritirata"],
            "es": ["básico", "fase", "entrenador", "partidario", "objeto", "estadio", "debilidad", "resistencia",
                   "retirada"],
            "pt": ["básico", "estágio", "treinador", "apoiador", "item", "estádio", "fraqueza", "resistência",
                   "recuo"],
        },
    }
    price_trend_word = False   # price lines without "Trend" (too long otherwise: "Cardmarket Reverse Holo")
    card_types = ("Pokémon", "Trainer", "Energy")   # advanced search: card type
    card_px = (336, 468)   # 63 × 88 mm like Magic
    # Deck building (decks.analyze_generic, decks.rule_warnings) – official rules: 60 cards, at most 4 per name
    # (except basic Energy), at most 1 ACE SPEC and 1 Radiant Pokémon, at least one Basic Pokémon
    deck_rules = {
        "standard": {"size": 60, "exact": True, "copies": 4, "legal": "standard",
                     "limits": (("ACE SPEC", 1, "ACE SPEC"), ("Radiant", 1, "Radiant")),
                     "require": ((lambda r: (r.get("type_line") or "").startswith("Pokémon — Basic"),
                                  "Kein Basis-Pokémon im Deck"),)},
        "expanded": {"size": 60, "exact": True, "copies": 4, "legal": "expanded",
                     "limits": (("ACE SPEC", 1, "ACE SPEC"), ("Radiant", 1, "Radiant")),
                     "require": ((lambda r: (r.get("type_line") or "").startswith("Pokémon — Basic"),
                                  "Kein Basis-Pokémon im Deck"),)},
        "casual": {"size": 60, "exact": False, "copies": 4},
    }
    # what doesn't exist (yet) – those tabs show "coming soon"
    features = {"scan", "sessions", "library", "decks", "testing", "trade", "import"}

    @property
    def data(self):
        from cards import carddb
        return carddb

    prices = None

    # ---------- Deck building ----------
    _STAGES = ("Basic", "Stage1", "Stage2")

    def deck_curve(self):
        """Evolution lines instead of a mana curve: Basic · Stage 1 · Stage 2 · Mega/VMAX/VSTAR/BREAK; highlighted are
        the Pokémon with a rule box (ex, V, GX … – they give up two or three prize cards)."""
        labels = ["Basis", "Ph. 1", "Ph. 2", "Mega+"]

        def bin_(r):
            tl = r.get("type_line") or ""
            if not tl.startswith("Pokémon"):
                return None, False
            stage = tl.split(" — ")[1] if " — " in tl else ""
            i = self._STAGES.index(stage) if stage in self._STAGES else 3
            kw = [x.strip() for x in (r.get("keywords") or "").split(",")]
            return i, any(k in kw for k in ("ex", "EX", "V", "GX", "TAG TEAM-GX", "VMAX", "VSTAR", "MEGA"))
        return {"title": "Entwicklungen", "sub": "nur Pokémon", "labels": labels, "inner": "mit Regelbox",
                "bin": bin_}

    def deck_roles(self):
        import re
        return {
            "Karten ziehen": (re.compile(r"\bdraws? (?:\d+|a|an|that many|cards?)|draw cards until", re.I),
                              "zieht Karten nach (z. B. Professors Forschung, Iono)"),
            "Suche": (re.compile(r"search your deck for", re.I),
                      "holt bestimmte Karten aus dem Deck (Pokémon, Energie, Trainer)"),
            "Energie anlegen": (re.compile(r"attach (?:up to )?(?:a|an|\d+|that|any number of)[^.]*energy", re.I),
                                "legt zusätzlich Energie an (Energiebeschleunigung)"),
            "Wechseln": (re.compile(r"switch (?:your|this|1 of your|in 1 of)|switch it with", re.I),
                         "tauscht das Aktive Pokémon aus"),
            "Heilung": (re.compile(r"\bheal\b", re.I), "entfernt Schadensmarken"),
            "Stören": (re.compile(r"your opponent (?:shuffles|discards|reveals) (?:their|his or her) hand|"
                                  r"opponent's (?:hand|deck)", re.I),
                       "greift Hand oder Deck des Gegners an"),
        }

    def deck_kpis(self, a):
        t = a["types"]
        return [("Karten", a["count"], f"von {a['size']}" if a.get("size") else ""),
                ("Pokémon", t.get("Pokémon", 0), ""), ("Trainer", t.get("Trainer", 0), ""),
                ("Energie", t.get("Energy", 0), "")]

    _BASIC_ENERGY = None

    def deck_unlimited(self, row):
        """Basic Energy: type line "Energy — Normal" – older prints only have "Energy" (then by the name:
        "Lightning Energy", "Basic Fire Energy")."""
        import re
        tl = row.get("type_line") or ""
        if tl.startswith("Energy — Normal"):
            return True
        if tl.strip() == "Energy":
            if Pokemon._BASIC_ENERGY is None:
                Pokemon._BASIC_ENERGY = re.compile(r"(?:Basic )?(?:Grass|Fire|Water|Lightning|Psychic|Fighting|Darkness|"
                                                r"Metal|Fairy) Energy")
            return bool(Pokemon._BASIC_ENERGY.fullmatch(row.get("name") or ""))
        return False

    deck_cost_column = False
    # Test: 7 cards, no Basic Pokémon -> show, shuffle back, redraw (the opponent may draw one extra card each time);
    # then 6 prize cards face down; the first player draws on the first turn too
    playtest = {"hand": 7, "mulligan": "basic", "prizes": 6, "draw_first": True, "bench": 5}   # + Active spot

    def playtest_basic(self, row):
        return (row.get("type_line") or "").startswith("Pokémon — Basic")

    def playtest_groups(self):
        return [("Basic Pokémon", self.playtest_basic)] + super().playtest_groups()

    def deck_legal_names(self, names, fmt):
        """Legal by name: if any printing of the card is legal in the format, so are its older printings with the
        same name (official rule for reprints)."""
        from cards import carddb
        names = sorted({n for n in names if n})
        if not names or not carddb.exists():
            return set()
        with carddb.connection() as con:
            rows = con.execute(f"SELECT DISTINCT name FROM cards WHERE name IN ({','.join('?' * len(names))}) "
                               f"AND legalities LIKE ?", names + [f'%"{fmt}"%']).fetchall()
        return {r[0] for r in rows}

    def deck_name_key(self, row):
        return row.get("name") or ""

    def card_type(self, row):
        front = row.get("type_line") or ""
        for key, _ in self.type_order:
            if front.startswith(key):
                return key
        return "Other"

    def card_url(self, set_code, number):
        return ""

    _img_base = {}

    def image_url(self, set_code, number, lang="en", version="normal"):
        """Image at TCGdex – also in other languages (same address, different code: …/de/swsh/swsh3/136).
        None if TCGdex has no image for the card."""
        from cards import carddb
        key = (str(set_code).lower(), str(number))
        base = self._img_base.get(key, False)
        if base is False:
            # the whole set in one query (the library's preloading asks for 1500 tiles – one query each held the UI
            # for 250 ms, tester log 0.9.2); a card not in it is remembered as None too
            try:
                with carddb.connection() as con:
                    rows = con.execute("SELECT number, img_normal FROM cards WHERE set_code = ?", key[:1]).fetchall()
            except Exception:  # noqa: BLE001
                rows = []
            for num, img in rows:
                self._img_base.setdefault((key[0], str(num)), img.rsplit("/", 1)[0] if img else None)
            base = self._img_base.setdefault(key, None)
        if not base:
            return None
        if lang:   # language codes at TCGdex: zh-tw/zh-cn instead of zht/zhs
            parts = base.split("/")
            if len(parts) > 3:
                parts[3] = {"zht": "zh-tw", "zhs": "zh-cn"}.get(lang, lang)
                base = "/".join(parts)
        return base + ("/low.jpg" if version == "small" else "/high.jpg")

    def variants_of(self, sid):
        """Finishes according to the TCGdex source data (normal, reverse, holo, firstEdition …) – [] if unknown."""
        from cards import carddb
        try:
            with carddb.connection() as con:
                return [r[0] for r in con.execute("SELECT type FROM variants WHERE sid = ?", (sid,))]
        except Exception:  # noqa: BLE001 – older database without the table
            return []

    POKE_FINISHES = (("normal", "Normal", "N"), ("holo", "Holo", "H"), ("reverse", "Reverse Holo", "RH"))
    # Special patterns (TCGplayer lists them as separate products with the same number – tools/fix_pokemon_market.py)
    PATTERN_SHORT = {"pat:pokeball": "PB", "pat:masterball": "MB", "pat:energysymbol": "ES", "pat:cosmos": "CO",
                     "pat:crackedice": "CI"}
    _fix = None

    def market_fix(self):
        """Marketplace corrections from the data pack (cm_fix.json): {"fixed": {printing: Cardmarket no.}, "untrusted":
        [printing …], "patterns": {key: name}, "pk_build", …} – {} without a pack."""
        if Pokemon._fix is None:
            from cards import packs
            path = packs.path_of("pokemon", "cm_fix.json")
            try:
                Pokemon._fix = json.loads(path.read_text("utf-8")) if path else {}
            except (OSError, ValueError):
                Pokemon._fix = {}
        return Pokemon._fix

    def finish_options(self, card):
        """Normal / Holo / Reverse Holo – according to the printing's TCGdex variants (some exist in all three). Price:
        the base finish (Normal, Holo for holo-only cards) takes the normal price, the others the foil price
        (Cardmarket trend-holo)."""
        from collection.collection import scryfall_id
        all_types = self.variants_of(scryfall_id(card.get("id") or ""))
        types = set(all_types)
        if not types & {"normal", "holo", "reverse"}:   # no variants: from the finishes in the card data
            fin = card.get("finishes") or []
            types = {"normal"} if "nonfoil" in fin else set()
            if "foil" in fin:
                types.add("reverse" if "nonfoil" in fin else "holo")
        if types <= {"normal"} and (card.get("eur_foil") is not None or card.get("usd_foil") is not None):
            # Fallback: data only knows "Normal", but there is a foil price -> the card also exists as Holo
            # (Holo Rares) or Reverse Holo (everything else)
            types.add("holo" if "holo" in (card.get("rarity") or "").lower() else "reverse")
        keys = [k for k, *_ in self.POKE_FINISHES if k in types] or ["normal"]
        out = [{"key": k, "label": lb, "short": sh, "foil": k != keys[0]}
               for k, lb, sh in self.POKE_FINISHES if k in keys]
        names = self.market_fix().get("patterns") or {}
        for k in dict.fromkeys(t for t in all_types if t.startswith("pat:")):   # Poké Ball, Master Ball, Cosmos …
            out.append({"key": k, "label": names.get(k) or k[4:].title(), "short": self.PATTERN_SHORT.get(k, "SP"),
                        "foil": True})
        return out

    def editions(self, card):
        from collection.collection import scryfall_id
        if "firstEdition" in self.variants_of(scryfall_id(card.get("id") or "")) or \
                "firstedition" in (card.get("finishes") or []):
            return [{"key": "1st", "label": "1st Edition", "short": "1st"}]
        return []

    def finish_info(self, row):
        """Pokémon: the "normal" printing is Normal or (for holo cards) Holo; the second finish is Reverse Holo.
        Prices match this: Cardmarket trend = the printing itself, trend-holo = Reverse Holo."""
        types = set(self.variants_of(row.get("sid") or ""))
        if not types:   # no information: from the finishes in the card database
            fin = (row.get("card") or {}).get("finishes") or []
            types = ({"normal"} if "nonfoil" in fin else set()) | ({"reverse"} if "foil" in fin else set())
        base = "Holo" if "holo" in types and "normal" not in types else "Normal"
        second = "Reverse Holo" if "reverse" in types else ("Holo" if "holo" in types and "normal" in types else None)
        opts = ["nonfoil"] + (["foil"] if second else [])
        return opts, {"n": base, "f": second or "Reverse Holo"}

    # ---------- Set list ----------
    def sets_catalog(self, max_age=7 * 24 * 3600):
        """All sets [{code, name, released, count, type, parent}] – cached like in Magic."""
        from scanner.common import REF
        f = REF / "sets.json"
        cached = []
        try:
            cached = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            pass
        if cached and time.time() - f.stat().st_mtime < max_age:
            return cached
        try:
            data = _gql("{ sets(filters:{}) { id name releaseDate cardCount{official total} serie{id name} } }")
            sets = [{"code": s["id"], "name": s["name"], "released": s.get("releaseDate") or "",
                     "count": (s.get("cardCount") or {}).get("total") or 0, "type": (s.get("serie") or {}).get("name", ""),
                     "parent": None} for s in data["sets"] if (s.get("cardCount") or {}).get("total")
                    and (s.get("serie") or {}).get("id") != "tcgp"]   # TCG Pocket is digital – no cards to scan
            REF.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(sets, ensure_ascii=False), "utf-8")
            return sets
        except Exception:  # noqa: BLE001 – offline: whatever is there
            return cached

    def set_info(self, code):
        for s in self.sets_catalog():
            if s["code"].lower() == code.lower():
                return s["name"], None
        try:
            s = _rest(f"sets/{code}")
            return s["name"], None
        except Exception:  # noqa: BLE001
            raise RuntimeError(tr(f"There is no set with the code “{code}” on TCGdex.")) from None

    def set_cards(self, code, progress=lambda text, done, total: None):
        """Cards of a set with prices -> [(entry as in the set files, image URL)]."""
        from scanner.common import image_rel
        s = _rest(f"sets/{code}")
        brief = s.get("cards") or []
        out = []
        for n, b in enumerate(brief, 1):
            progress(f"{code.upper()}: loading card list and prices …", n, len(brief))
            if not b.get("image"):
                continue   # no image, no recognition
            try:
                c = _rest(f"cards/{b['id']}")
            except Exception:  # noqa: BLE001 – then without price/rarity
                c = dict(b)
            cm = (c.get("pricing") or {}).get("cardmarket") or {}
            if not cm:
                for vd in c.get("variants_detailed") or []:
                    cm = ((vd.get("pricing") or {}).get("cardmarket")) or {}
                    if cm:
                        break
            entry = {
                "id": f"{b['id']}_0", "name": c.get("name") or b.get("name"), "set": code.upper(),
                "number": str(b.get("localId")), "rarity": _slug(c.get("rarity")), "booster": True,
                "finishes": _finishes(c.get("variants")), "eur": cm.get("trend"), "eur_foil": cm.get("trend-holo"),
                "img": image_rel(code, str(b.get("localId")), 0), "url": "",
                "thumb": b["image"] + "/low.jpg",
            }
            out.append((entry, b["image"] + "/high.jpg"))
        return out

    def price_lookup(self, card_id):
        """(trend normal, trend holo) in € for a card – from the card database, otherwise one request to TCGdex
        (then remembered in the database so the library and next scans have it too). None without a price."""
        from cards import carddb
        sid = card_id.rpartition("_")[0] if card_id.rpartition("_")[2].isdigit() else card_id
        with carddb.connection() as con:
            row = con.execute("SELECT eur, eur_foil FROM cards WHERE id = ?", (sid,)).fetchone()
        if row is not None and (row[0] is not None or row[1] is not None):
            return row[0], row[1]
        c = _rest(f"cards/{sid}")
        cm = (c.get("pricing") or {}).get("cardmarket") or {}
        if not cm:
            for vd in c.get("variants_detailed") or []:
                cm = ((vd.get("pricing") or {}).get("cardmarket")) or {}
                if cm:
                    break
        eur, foil = cm.get("trend"), cm.get("trend-holo")
        if eur is None and foil is None:
            return None
        try:
            with carddb.connection(plain=True) as con:
                con.execute("UPDATE cards SET eur = ?, eur_foil = ? WHERE id = ?", (eur, foil, sid))
                con.commit()
        except sqlite3.Error:
            pass
        return eur, foil

    # ---------- Daily prices (Cardmarket price guide + TCGplayer via our price server) ----------
    def update_prices(self, progress=lambda text, done, total: None, sets=None):
        """Today's prices: Cardmarket provides one daily file per game (downloads.s3.cardmarket.com, ~16 MB,
        all cards), TCGplayer comes from our own price server (one file, built daily from TCGCSV – all sets or
        only `sets`). Matching via the marketplace numbers from the TCGdex source data (table ext, see
        tools/build_pokemon_db.py). Writes the prices into the card database and today's state into the
        price history (same format as Magic; the first time with the averages from 1/7/30 days ago).
        -> (cards with Cardmarket price, cards with TCGplayer price)"""
        from cards import carddb
        from cards import pricehist
        net = _net()
        guide = cardmarket_guide(CM_GUIDE, progress)
        with carddb.connection() as con:
            try:
                ext = con.execute("SELECT sid, variant, cm, tcg FROM ext").fetchall()
                set_tcg = dict(con.execute("SELECT set_code, tcg FROM set_ext"))
            except sqlite3.Error:
                ext, set_tcg = [], {}
        by_cm, by_tcg = {}, {}
        for sid, variant, cm, tcg in ext:
            if (variant or "").startswith("pat:"):   # special pattern: separate product, not the card's price
                continue
            if cm:
                by_cm.setdefault(sid, cm)
            if tcg:
                by_tcg.setdefault(tcg, set()).add(sid)
        day = pricehist.today()
        prices, hist = {}, {}
        for sid, cm in by_cm.items():
            g = guide.get(cm)
            if not g:
                continue
            prices[sid], e = cardmarket_entry(g, day)
            if e:
                hist[sid] = e
        n_cm = len(prices)
        # TCGplayer: one file from our price server (sets=None: all sets, otherwise only these)
        groups = sorted({g for s, g in set_tcg.items() if g and (sets is None or s in sets)})
        tcg, stale = tcgplayer_table(net, carddb.DB_PATH.parent / "tcgplayer-prices.json.gz", TCG_PRICES)
        n_tcg = 0
        new_variants = set()
        sub_type = {"Normal": "normal", "Holofoil": "holo", "Reverse Holofoil": "reverse",
                    "1st Edition Holofoil": "firstEdition", "1st Edition Normal": "firstEdition",
                    "Unlimited Holofoil": "holo"}
        for i, gid in enumerate(groups, 1):
            progress("Preise: TCGplayer (TCGCSV) …", i, len(groups))
            by_prod = {int(pid): sub for pid, sub in (tcg.get(str(gid)) or {}).items()}   # set without prices: {}
            for pid, sub in by_prod.items():
                for sid in by_tcg.get(pid, ()):
                    new_variants.update((sid, sub_type[s]) for s in sub if s in sub_type)
                    normal = sub.get("Normal") if sub.get("Normal") is not None else sub.get("Holofoil")
                    foil = sub.get("Reverse Holofoil") if sub.get("Reverse Holofoil") is not None else                         (sub.get("Holofoil") if sub.get("Normal") is not None else None)
                    tcgplayer_point(prices, hist, sid, normal, foil, day, stale)
                    n_tcg += 1
        progress("Preise eintragen …", 0, 0)
        from cards import currency
        untrusted = set(self.market_fix().get("untrusted") or [])
        for sid in untrusted:   # Cardmarket number at TCGdex ambiguous: convert euros from TCGplayer
            p = prices.get(sid)
            if p is None:
                continue
            p["eur"], p["eur_foil"] = currency.from_usd(p.get("usd")), currency.from_usd(p.get("usd_foil"))
            h = hist.get(sid)
            if h:
                h.pop("cn", None)
                h.pop("cf", None)
        with carddb.connection(plain=True) as con:
            con.executemany("UPDATE cards SET eur = COALESCE(?, eur), eur_foil = COALESCE(?, eur_foil), "
                            "usd = COALESCE(?, usd), usd_foil = COALESCE(?, usd_foil) WHERE id = ?",
                            [(p.get("eur"), p.get("eur_foil"), p.get("usd"), p.get("usd_foil"), sid)
                             for sid, p in prices.items() if sid not in untrusted])
            con.executemany("UPDATE cards SET eur = ?, eur_foil = ?, usd = COALESCE(?, usd), "
                            "usd_foil = COALESCE(?, usd_foil) WHERE id = ?",   # "no price" too, not the wrong one
                            [(p.get("eur"), p.get("eur_foil"), p.get("usd"), p.get("usd_foil"), sid)
                             for sid, p in prices.items() if sid in untrusted])
            if new_variants:   # finishes TCGplayer knows but TCGdex doesn't (e.g. Reverse Holo)
                have = set(con.execute("SELECT sid, type FROM variants"))
                con.executemany("INSERT INTO variants VALUES (?, ?)", sorted(new_variants - have))
            con.commit()
        from cards import finishes
        finishes.clear_cache()
        write_hist(hist, day)
        return n_cm, n_tcg

    @staticmethod
    def _keep_ext(con, carddb):
        """Take over marketplace numbers, finishes, names in other languages and prices from the previous (otherwise
        the shipped) database – TCGdex doesn't provide them in bulk via the API."""
        src = carddb.DB_PATH if carddb.DB_PATH.exists() else carddb._bundle_src()   # data pack or program
        if src is None or not src.exists():
            return
        con.commit()   # ATTACH doesn't work in the middle of a write
        con.execute("ATTACH DATABASE ? AS old", (str(src),))
        try:
            have = {r[0] for r in con.execute("SELECT name FROM old.sqlite_master WHERE type='table'")}
            for t in ("ext", "set_ext", "variants"):
                if t in have:
                    con.execute(f"CREATE TABLE {t} AS SELECT * FROM old.{t}")
            if "langs" in have:
                con.execute("INSERT INTO langs SELECT * FROM old.langs")
            con.execute("UPDATE cards SET eur = (SELECT o.eur FROM old.cards o WHERE o.id = cards.id), "
                        "eur_foil = (SELECT o.eur_foil FROM old.cards o WHERE o.id = cards.id), "
                        "usd = (SELECT o.usd FROM old.cards o WHERE o.id = cards.id), "
                        "usd_foil = (SELECT o.usd_foil FROM old.cards o WHERE o.id = cards.id)")
            # added from the source data (tools/build_pokemon_db.py): types, attacks, traits, legality …
            # and the Asian sets – the API doesn't provide these that way
            built = con.execute("SELECT value FROM old.meta WHERE key = 'pk_build'").fetchone()                 if "meta" in have else None
            if built:
                cols = ("colors", "oracle_text", "flavor_text", "keywords", "power", "cmc", "mana_cost",
                        "legalities", "promo_types", "type_line")
                con.execute(f"UPDATE cards SET ({', '.join(cols)}) = (SELECT {', '.join('o.' + c for c in cols)} "
                            "FROM old.cards o WHERE o.id = cards.id) WHERE id IN (SELECT id FROM old.cards)")
                con.execute("INSERT OR IGNORE INTO cards SELECT * FROM old.cards WHERE lang <> 'en'")
                con.execute("INSERT OR REPLACE INTO meta VALUES ('pk_build', ?)", (built[0],))
            con.commit()
        finally:
            con.execute("DETACH DATABASE old")

    # ---------- Card database ----------
    def download_db(self, progress=lambda text, done, total: None):
        """All cards (English) into a database in carddb's format. -> (cards, 0)"""
        from cards import carddb
        sets = {s["code"]: s for s in self.sets_catalog(max_age=0)}
        carddb.REF.mkdir(parents=True, exist_ok=True)
        tmp = carddb.DB_PATH.with_name("cards.new.sqlite")
        tmp.unlink(missing_ok=True)
        con = sqlite3.connect(tmp)
        con.executescript(carddb.SCHEMA)
        n, page = 0, 1
        total = sum(s.get("count") or 0 for s in sets.values()) or 22000
        try:
            while True:
                progress(tr("Card database: asking TCGdex …"), n, total)
                cards = _gql(f"{{ cards(pagination:{{page:{page},count:{PAGE}}}, filters:{{}}) {{ {_FIELDS} }} }}")["cards"]
                if not cards:
                    break
                rows = []
                for c in cards:
                    sc = (c.get("set") or {}).get("id") or ""
                    st = sets.get(sc)
                    if st is None:
                        continue   # e.g. TCG Pocket (digital)
                    img = c.get("image")
                    rows.append((
                        c["id"], c["name"], c["name"], "en", sc, st.get("name"), str(c.get("localId")),
                        _slug(c.get("rarity")), st.get("released"), _type_line(c), c.get("description"), None, None,
                        "", "", "", c.get("illustrator"), None, str(c["hp"]) if c.get("hp") else None, None, None,
                        "normal", ",".join(_finishes(c.get("variants"))), 1, None, None, None, None,
                        img + "/high.jpg" if img else None, img + "/low.jpg" if img else None, None, "{}", None,
                        0, 0, "", "", "", 0, None))
                con.executemany(f"INSERT OR REPLACE INTO cards VALUES ({','.join('?' * 40)})", rows)
                n += len(rows)
                if len(cards) < PAGE:
                    break
                page += 1
            progress("Kartendatenbank: Suchindex aufbauen …", 0, 0)
            self._keep_ext(con, carddb)
            con.executescript(carddb.INDEXES)
            n_l = con.execute("SELECT COUNT(*) FROM langs").fetchone()[0]
            con.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)",
                            [("cards", str(n)), ("langs", str(n_l)), ("updated", str(time.time())),
                             ("languages", "1" if n_l else "0")])
            con.commit()
        finally:
            con.close()
        tmp.replace(carddb.DB_PATH)
        return n, 0


GAME = Pokemon()
