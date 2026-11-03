"""Card database (offline): all English Scryfall prints in SQLite, with full-text search,
plus a language index (which print exists in which languages).

    data/kartendaten/cards.sqlite

Source is Scryfall's bulk downloads ("Bulk Data"), which are meant exactly for this:
    default_cards  (~75 MB)  -> table cards + full-text index cards_fts
    Languages: from the Magic data pack (packs.py, langs.tsv.gz from MTGJSON) -> table langs (import_langs) –
    no longer from Scryfall's all_cards (2 GB)
Files are downloaded first and then read line by line (little memory).
Updating builds a new database alongside and swaps it in at the end.
"""
import contextlib
import functools
import gzip
import json
import pathlib
import sqlite3
import threading
import time


from scanner.common import REF
from net import netpolite

DB_PATH = REF / "cards.sqlite"
HEADERS = {"User-Agent": netpolite.UA, "Accept": "application/json"}
LANG_NAMES = {"en": "EN", "de": "DE", "fr": "FR", "it": "IT", "es": "ES", "pt": "PT", "ja": "JP", "ko": "KR",
              "ru": "RU", "zhs": "CS", "zht": "CT", "th": "TH", "id": "ID", "he": "HE", "la": "LA", "grc": "GR", "ar": "AR", "sa": "SA",
              "ph": "PH", "qya": "QY"}

SCHEMA = """
CREATE TABLE cards (
    id TEXT PRIMARY KEY, oracle_id TEXT, name TEXT, lang TEXT, set_code TEXT, set_name TEXT,
    number TEXT, rarity TEXT, released TEXT, type_line TEXT, oracle_text TEXT, mana_cost TEXT, cmc REAL,
    colors TEXT, color_identity TEXT, keywords TEXT, artist TEXT, flavor_text TEXT,
    power TEXT, toughness TEXT, loyalty TEXT, layout TEXT, finishes TEXT, booster INTEGER,
    eur REAL, eur_foil REAL, usd REAL, usd_foil REAL,
    img_normal TEXT, img_small TEXT, faces TEXT, legalities TEXT, edhrec_rank INTEGER,
    reserved INTEGER, game_changer INTEGER, promo_types TEXT, frame_effects TEXT, border_color TEXT,
    full_art INTEGER, flavor_name TEXT
);
CREATE TABLE langs (set_code TEXT, number TEXT, lang TEXT, id TEXT, name TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""
INDEXES = """
CREATE INDEX cards_set ON cards(set_code, number);
CREATE INDEX cards_name ON cards(name);
CREATE INDEX cards_oracle ON cards(oracle_id);
CREATE INDEX langs_print ON langs(set_code, number);
CREATE VIRTUAL TABLE cards_fts USING fts5(
    name, type_line, oracle_text, keywords, artist, flavor_text, flavor_name,
    content='cards', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2');
INSERT INTO cards_fts(cards_fts) VALUES ('rebuild');
"""


def _drop_empty(path):
    """An empty file is no card database: an earlier open of a missing one created it (sqlite3.connect makes the file)
    – and then the game counted as having one and never built it (Lorcana, 0.9.2.54). Delete it -> the build runs."""
    try:
        if path.stat().st_size == 0:
            path.unlink()
    except OSError:
        pass


def exists():
    _drop_empty(DB_PATH)
    if DB_PATH.exists():
        if DB_PATH not in _upgrade_checked:
            _upgrade_checked.add(DB_PATH)
            _from_bundle(upgrade=True)
            _merge_extra()
        return True
    if _from_bundle():
        _upgrade_checked.add(DB_PATH)
        _merge_extra()
        return True
    return False


def _merge_extra():
    """Data the game keeps apart from the data pack's database (Yu-Gi-Oh!: ygo-locale.sqlite) into the local one –
    after each install/upgrade and once per start (games.<game>.merge_extra; checks itself whether anything is new)."""
    import games
    g = games.current()
    if g.merge_extra is None:
        return
    try:
        if g.merge_extra(DB_PATH):
            _meta_cache.clear()
            global _SET_CODES
            _SET_CODES = None
    except Exception:  # noqa: BLE001 – never block the database because of it
        __import__("logging").getLogger("booster").exception("Merging extra card data")


_upgrade_checked = set()


def _bundle_src():
    import sys
    import games
    key = games.current().key
    if key == "mtg":
        return None
    from cards import packs   # first the loaded data pack (data/packs/<game>/), then the program or dev folder
    pack = packs.file_of(key, "cards.sqlite") if key in packs.PACKS else None
    if pack:
        return pack
    src = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1])) / "models" / key / "cards.sqlite"
    return src if src.exists() else None


def _build_of(path):
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            r = con.execute("SELECT value FROM meta WHERE key = 'pk_build'").fetchone()
        finally:
            con.close()
        return int(r[0]) if r else 0
    except (sqlite3.Error, ValueError):
        return 0


def _from_bundle(upgrade=False):
    """Copy the game's bundled card database (models/<game>/cards.sqlite, e.g. Pokémon – small enough to
    ship) into the data folder on first use. upgrade=True: only if the bundled one is newer
    (meta.pk_build, see tools/build_pokemon_db.py) – then keeping the old one's prices. -> True if it is there now."""
    import shutil
    src = _bundle_src()
    if src is None:
        return False
    if upgrade and _build_of(src) <= _build_of(DB_PATH):
        return False
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = DB_PATH.with_name("cards.bundle.sqlite")
        shutil.copyfile(src, tmp)
        if upgrade:   # keep the current prices of the old database
            con = sqlite3.connect(tmp)
            try:
                con.execute("ATTACH DATABASE ? AS old", (str(DB_PATH),))
                con.execute("UPDATE cards SET (eur, eur_foil, usd, usd_foil) = (SELECT o.eur, o.eur_foil, o.usd, "
                            "o.usd_foil FROM old.cards o WHERE o.id = cards.id) WHERE id IN (SELECT id FROM old.cards "
                            "WHERE eur IS NOT NULL OR eur_foil IS NOT NULL OR usd IS NOT NULL OR usd_foil IS NOT NULL)")
                con.commit()
                con.execute("DETACH DATABASE old")
            finally:
                con.close()
        tmp.replace(DB_PATH)
        _meta_cache.clear()
        global _SET_CODES
        _SET_CODES = None
        return True
    except (OSError, sqlite3.Error):
        log_ = __import__("logging").getLogger("booster")
        log_.exception("Installing bundled card database")
        return False


_SET_CODES = None


def set_codes():
    """All set codes (lowercase) – for search ("sos 123")."""
    global _SET_CODES
    if _SET_CODES is None:
        try:
            with connection() as con:
                _SET_CODES = {r[0] for r in con.execute("SELECT DISTINCT set_code FROM cards")}
        except Exception:  # noqa: BLE001 – no database
            return set()
    return _SET_CODES


def path_of(game=None):
    """Database of the open game – or of another one (read only)."""
    import games
    if not game or game == games.current().key:
        return DB_PATH
    from scanner.common import DATA
    return games.folders(game, DATA)["ref"] / "cards.sqlite"


def _has(game=None):
    if not game or path_of(game) == DB_PATH:
        return exists()
    _drop_empty(path_of(game))
    return path_of(game).exists()


def _open(path, **kw):
    """Open an existing card database – never create one (a missing file raises sqlite3.OperationalError instead of
    leaving an empty file behind, see _drop_empty). Checked beforehand instead of a mode=rw URI: a data folder on a
    network drive (\\\\server\\share) would become a URI with a host, which SQLite refuses. Every writer replaces the
    file in one step (temporary file + replace), so it can't vanish between the check and the open."""
    if not pathlib.Path(path).exists():
        raise sqlite3.OperationalError(f"no card database: {path}")
    return sqlite3.connect(path, **kw)


def connect(game=None):
    con = _open(path_of(game) if game else DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


@contextlib.contextmanager
def connection(game=None, plain=False):
    """connect() as a with block: closed at the end, also on errors. No automatic commit – commit() as before.
    plain=True: a bare connection like sqlite3.connect(DB_PATH) (rows as tuples, e.g. for set comparisons)."""
    con = _open(DB_PATH) if plain else connect(game)
    try:
        yield con
    finally:
        con.close()


def status():
    """Summary for the settings: number of cards/language entries, last update, size."""
    if not exists():
        return None
    with connection() as con:
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        return {"cards": int(meta.get("cards", 0)), "langs": int(meta.get("langs", 0)),
                "updated": float(meta.get("updated", 0)), "size": DB_PATH.stat().st_size}


def delete():
    for p in (DB_PATH, DB_PATH.with_suffix(".sqlite-journal")):
        p.unlink(missing_ok=True)


# ---------- Download / import ----------
def _bulk_info():
    r = netpolite.get("https://api.scryfall.com/bulk-data", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return {b["type"]: b for b in r.json()["data"]}


def _built_from(db_path):
    """meta of an existing card database ({"bulk": Scryfall updated_at, "cards", "langs"}) – {} if there is none."""
    if not db_path.exists():
        return {}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return dict(con.execute("SELECT k, v FROM meta WHERE k IN ('bulk', 'cards', 'langs')"))
        finally:
            con.close()
    except sqlite3.Error:
        return {}


def _download(url, size, path, label, progress):
    """Download a file with progress (in MB) – resumable: the partial file is <file>.part, next to it
    <file>.src with the URL. App closed, network lost: next time it resumes at the same point (as long as
    Scryfall offers the same file). Already fully downloaded (same URL): not again."""
    part, src = path.with_name(path.name + ".part"), path.with_name(path.name + ".src")
    same = src.exists() and src.read_text("utf-8").strip() == url
    if same and path.exists():
        return
    if not same:
        part.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        src.write_text(url, "utf-8")
    have = part.stat().st_size if part.exists() else 0
    headers = dict(HEADERS, Range=f"bytes={have}-") if have else HEADERS
    with netpolite.get(url, headers=headers, stream=True, timeout=60) as r:
        if have and r.status_code == 416:   # already complete
            part.replace(path)
            return
        r.raise_for_status()
        if have and r.status_code != 206:   # server cannot resume: start over
            have = 0
        total = have + int(r.headers.get("Content-Length") or 0) or int(size or 0)
        done = have
        with open(part, "ab" if have else "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                done += len(chunk)
                progress(f"{label}: herunterladen …", done >> 20, total >> 20)
    part.replace(path)


def _drop_download(path):
    """Done processing: remove the downloaded file along with its marker files."""
    for p in (path, path.with_name(path.name + ".part"), path.with_name(path.name + ".src")):
        p.unlink(missing_ok=True)


def _lines(path, label, progress, every=5000):
    """Lines of a .jsonl.gz file as dicts; progress by (compressed) MB read."""
    total = path.stat().st_size
    with open(path, "rb") as raw, gzip.GzipFile(fileobj=raw) as gz:
        for n, line in enumerate(gz):
            if n % every == 0:
                progress(f"{label}: einlesen …", raw.tell() >> 20, total >> 20)
            line = line.strip()
            if line:
                yield json.loads(line)


def _price(v):
    return float(v) if v not in (None, "") else None


def _row(c):
    faces = c.get("card_faces") or []
    img = c.get("image_uris") or (faces[0].get("image_uris") if faces and faces[0].get("image_uris") else {}) or {}
    face_list = [{
        "name": f.get("name"), "mana_cost": f.get("mana_cost"), "type_line": f.get("type_line"),
        "oracle_text": f.get("oracle_text"), "flavor_text": f.get("flavor_text"),
        "img_normal": (f.get("image_uris") or {}).get("normal"), "img_small": (f.get("image_uris") or {}).get("small"),
    } for f in faces]

    def joined(key):
        v = c.get(key)
        if v:
            return v
        parts = [f.get(key) for f in faces if f.get(key)]
        return " // ".join(parts) if parts else None
    pr = c.get("prices") or {}
    legal = c.get("legalities") or {}
    return (
        c["id"], c.get("oracle_id") or (faces[0].get("oracle_id") if faces else None), c["name"], c.get("lang"),
        c["set"], c.get("set_name"), c["collector_number"], c.get("rarity"), c.get("released_at"),
        joined("type_line"), joined("oracle_text"), joined("mana_cost"), c.get("cmc"),
        "".join(c.get("colors") or []), "".join(c.get("color_identity") or []),
        ", ".join(c.get("keywords") or []), c.get("artist"), joined("flavor_text"),
        c.get("power"), c.get("toughness"), c.get("loyalty"), c.get("layout"),
        ",".join(c.get("finishes") or []), int(bool(c.get("booster"))),
        _price(pr.get("eur")), _price(pr.get("eur_foil")), _price(pr.get("usd")), _price(pr.get("usd_foil")),
        img.get("normal"), img.get("small"), json.dumps(face_list, ensure_ascii=False) if face_list else None,
        json.dumps({k: v for k, v in legal.items() if v == "legal"}), c.get("edhrec_rank"),
        int(bool(c.get("reserved"))), int(bool(c.get("game_changer"))),
        ",".join(c.get("promo_types") or []), ",".join(c.get("frame_effects") or []), c.get("border_color"),
        int(bool(c.get("full_art"))), joined("flavor_name"),
    )


def download(progress=lambda text, done, total: None, languages=True, game=None):
    """Rebuild the card database. -> (number of cards, number of language entries)"""
    _indexed.clear()  # new database: recreate the name indexes on next use
    import games
    g = games.load(game) if game else games.current()
    if g.download_db is not None:   # other game (Pokémon …): own source, same format
        _meta_cache.clear()
        if g.db_target:   # takes the target file: another game's download never hits the open one
            from scanner.common import DATA
            return g.download_db(progress, games.folders(g.key, DATA)["ref"] / "cards.sqlite" if game else DB_PATH)
        return g.download_db(progress)
    # target game's folder – fixed for this download so a game switch midway doesn't mix anything up
    from scanner.common import DATA
    ref = games.folders(g.key, DATA)["ref"] if game else REF
    db_path = ref / "cards.sqlite"
    ref.mkdir(parents=True, exist_ok=True)
    progress("Kartendatenbank: Scryfall fragen …", 0, 0)
    bulk = _bulk_info()
    made = _built_from(db_path)
    if made and made.get("bulk") and made["bulk"] == bulk["default_cards"].get("updated_at"):
        # Scryfall's file hasn't changed since this database was built: nothing to download (a schema change that
        # needs a rebuild must clear "bulk" in meta)
        return int(made.get("cards") or 0), int(made.get("langs") or 0)
    tmp_db = db_path.with_name("cards.new.sqlite")
    tmp_db.unlink(missing_ok=True)
    con = sqlite3.connect(tmp_db)
    con.executescript(SCHEMA)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    n_cards = n_langs = 0
    try:
        src = bulk["default_cards"]
        gz = ref / "default_cards.jsonl.gz"
        _download(src["jsonl_download_uri"], src.get("compressed_size"), gz, "Kartendaten", progress)
        batch = []
        for c in _lines(gz, "Kartendaten", progress):
            if "paper" not in (c.get("games") or []):
                continue  # skip online-only cards (Arena/MTGO)
            batch.append(_row(c))
            if len(batch) >= 2000:
                con.executemany(f"INSERT OR REPLACE INTO cards VALUES ({','.join('?' * 40)})", batch)
                n_cards += len(batch)
                batch = []
        if batch:
            con.executemany(f"INSERT OR REPLACE INTO cards VALUES ({','.join('?' * 40)})", batch)
            n_cards += len(batch)

        n_langs = _import_langs(con, progress)   # all languages from the pack (if still missing: later, import_langs)

        progress("Kartendatenbank: Suchindex aufbauen …", 0, 0)
        con.executescript(INDEXES)
        con.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)",
                        [("cards", str(n_cards)), ("langs", str(n_langs)), ("updated", str(time.time())),
                         ("languages", "1" if n_langs else "0"), ("bulk", src.get("updated_at") or "")])
        con.commit()
    finally:
        con.close()
    tmp_db.replace(db_path)
    for name in ("default_cards.jsonl.gz", "all_cards.jsonl.gz"):   # only now: resumable up to here
        _drop_download(ref / name)
    return n_cards, n_langs


def _import_langs(con, progress=lambda text, done, total: None):
    """Languages from the Magic pack into an (open) database: per print the English row from cards, plus every
    other language (set and number via the card's Scryfall ID). -> number of rows (0 = pack file missing)."""
    import gzip
    from cards import packs
    path = packs.path_of("mtg", "langs.tsv.gz")
    if path is None:
        return 0
    progress("Kartendatenbank: Sprachen …", 0, 0)
    where = {r[0]: (r[1], r[2]) for r in con.execute("SELECT id, set_code, number FROM cards")}
    con.execute("DELETE FROM langs")
    con.execute("INSERT INTO langs SELECT set_code, number, COALESCE(lang, 'en'), id, name FROM cards")
    n = con.execute("SELECT COUNT(*) FROM langs").fetchone()[0]
    batch = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            main_sid, lang, sid, name = line.rstrip("\n").split("\t", 3)
            pos = where.get(main_sid)
            if pos is None:
                continue
            batch.append((pos[0], pos[1], lang, sid, name))
            if len(batch) >= 5000:
                con.executemany("INSERT INTO langs VALUES (?,?,?,?,?)", batch)
                n += len(batch)
                batch = []
    if batch:
        con.executemany("INSERT INTO langs VALUES (?,?,?,?,?)", batch)
        n += len(batch)
    return n


def import_langs(db_path=None, progress=lambda text, done, total: None):
    """Add languages to an existing Magic database afterwards (pack arrived after the database). -> count"""
    path = db_path or DB_PATH
    if not path.exists():
        return 0
    con = sqlite3.connect(path)
    try:
        n = _import_langs(con, progress)
        if n:
            con.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", [("langs", str(n)), ("languages", "1")])
            con.commit()
    finally:
        con.close()
    _meta_cache.clear()
    _printed.update(idx=None, keys=None, blob=None, starts=None)
    return n


# ---------- Queries ----------
_meta_cache = {}


def norm_number(number, zero="0"):
    """Collector number for comparing: without leading zeros ("007" -> "7", "0123a" -> "123a"); only zeros (or
    nothing) -> zero – "0" as a rule, "" where an all-zero number must not match a read "0"."""
    return str(number or "").lstrip("0") or zero


def number_key(number):
    """Sort key for collector numbers in natural order ("2" before "10", "12a" next to "12")."""
    digits = "".join(ch for ch in str(number) if ch.isdigit())
    return int(digits) if digits else 0, str(number)


def has_languages():
    """Database present and with a language index?"""
    if not exists():
        return False
    mtime = DB_PATH.stat().st_mtime
    if _meta_cache.get("mtime") != mtime:
        with connection() as con:
            meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        _meta_cache.update(mtime=mtime, langs=int(meta.get("langs", 0)))
    return _meta_cache["langs"] > 0


def has_flavor_names():
    """Database with flavor names ("The Imperial City of Archades" for Wall of Omens)? Older versions lack the
    column – then without them until the next update."""
    if not exists():
        return False
    mtime = DB_PATH.stat().st_mtime
    if _meta_cache.get("flavor_mtime") != mtime:
        with connection() as con:
            cols = {r[1] for r in con.execute("PRAGMA table_info(cards)")}
        _meta_cache.update(flavor_mtime=mtime, flavor="flavor_name" in cols)
    return _meta_cache["flavor"]


def name_col():
    """SQL for "name" including the flavor name, if present."""
    return "(c.name || ' ' || COALESCE(c.flavor_name, ''))" if has_flavor_names() else "c.name"


def fts_terms(text):
    return " ".join(f'"{t}"*' for t in text.replace('"', " ").split())


_TYPE_RANK = ("CASE WHEN c.type_line LIKE '%Creature%' THEN 1 WHEN c.type_line LIKE '%Planeswalker%' THEN 2 "
              "WHEN c.type_line LIKE '%Instant%' THEN 3 WHEN c.type_line LIKE '%Sorcery%' THEN 4 "
              "WHEN c.type_line LIKE '%Artifact%' THEN 5 WHEN c.type_line LIKE '%Enchantment%' THEN 6 "
              "WHEN c.type_line LIKE '%Battle%' THEN 7 WHEN c.type_line LIKE '%Land%' THEN 8 ELSE 9 END")
_COLOR_RANK = ("CASE WHEN c.colors = '' THEN 7 WHEN length(c.colors) > 1 THEN 6 "
               "ELSE instr('WUBRG', c.colors) END")
_RARITY_RANK = ("CASE c.rarity WHEN 'mythic' THEN 0 WHEN 'special' THEN 1 WHEN 'rare' THEN 2 "
                "WHEN 'uncommon' THEN 3 WHEN 'common' THEN 4 ELSE 5 END")
SORTS = {
    "relevance": None,
    "name": "c.name, c.released DESC",
    "price": "COALESCE(c.eur, c.eur_foil, 0) DESC, c.name",
    "set": "c.released DESC, c.set_code, CAST(c.number AS INTEGER), c.number",
    "new": "c.released DESC, c.name",
    "type": f"{_TYPE_RANK}, c.name",
    "mv": "c.cmc, c.name",
    "color": f"{_COLOR_RANK}, c.colors, c.name",
    "rarity": f"{_RARITY_RANK}, c.name",
    "edhrec": "COALESCE(c.edhrec_rank, 9999999), c.name",
}
CARD_TYPES = ["Creature", "Land", "Artifact", "Enchantment", "Planeswalker", "Instant", "Sorcery", "Battle", "Kindred"]
SUPERTYPES = ["Legendary", "Basic", "Snow", "World"]
_MTG_TYPES, _MTG_SUPER = list(CARD_TYPES), list(SUPERTYPES)
SUPER_LABELS = {}   # word in the type line -> display label (Pokémon: "Stage1" -> "Phase 1")


def _game_changed():
    """Game switched: card types of the advanced search, clear caches (different database)."""
    global _SET_CODES
    g = __import__("games").current()
    if g.card_types is not None:   # other game: its card types for the advanced search
        sup = list(g.supertypes)
        CARD_TYPES[:], SUPERTYPES[:] = list(g.card_types), [s[0] if isinstance(s, tuple) else s for s in sup]
        SUPER_LABELS.clear()
        SUPER_LABELS.update({s[0]: s[1] for s in sup if isinstance(s, tuple)})
    else:
        CARD_TYPES[:], SUPERTYPES[:] = list(_MTG_TYPES), list(_MTG_SUPER)
        SUPER_LABELS.clear()
    _SET_CODES = None
    _indexed.clear()
    _meta_cache.clear()
    _printed.update(idx=None, keys=None, blob=None, starts=None)
    for f in list(globals().values()):
        if hasattr(f, "cache_clear"):
            f.cache_clear()
    prewarm_printed()   # prepare the names in all languages of the new game right away

@functools.lru_cache(maxsize=1)
def regulation_marks():
    """Regulation marks in the card database (Pokémon: A … J, other games' blocks 1 … 5, X – single characters in
    promo_types), sorted."""
    try:
        with connection() as con:
            rows = con.execute("SELECT DISTINCT promo_types FROM cards WHERE length(promo_types) = 1").fetchall()
        return tuple(sorted(r[0] for r in rows if r[0] and r[0].isalnum()))
    except Exception:  # noqa: BLE001 – no database yet
        return ()


NO_SUPERTYPE = "-"  # "no supertype" entry of the advanced search
FORMAT_KEYS = ["standard", "pioneer", "modern", "legacy", "vintage", "commander", "pauper"]
TEXT_FIELDS = {"oracle": "c.oracle_text", "name": "c.name", "type": "c.type_line", "flavor": "c.flavor_text",
               "artist": "c.artist", "keyword": "c.keywords"}
RANGE_COLS = {"mv": "c.cmc", "pow": "c.power", "tou": "c.toughness", "price": "COALESCE(c.eur, c.eur_foil)",
              "loy": "c.loyalty", "move": "c.mana_cost",   # loy: Yu-Gi-Oh! pendulum scale, Lorcana lore;
              "year": "CAST(substr(c.released, 1, 4) AS INTEGER)"}   # move: Lorcana move cost (Locations);
#                                                          year: release year of the print (year:1999, "glurak 1999")


def _any_all(conds, mode):
    return "(" + (" AND " if mode == "all" else " OR ").join(conds) + ")"


def _filters(filters):
    """Filters -> (SQL conditions, parameters).
    set_code; colors ("WU", "C" = colorless, "M" = multicolor) with color_mode ("any" = contains all selected,
    "exact" = exactly these, "atmost" = at most these); types/subtypes/keywords (lists) with *_mode "any"/"all";
    supertypes (all required); rarities; formats (legal in all); ranges {"mv"/"pow"/"tou"/"price": (min, max)};
    texts [(field, text, exclude?)]; only_ids/exclude_ids; no_tokens."""
    where, args = [], []
    if filters.get("set_code"):
        where.append("c.set_code = ?")
        args.append(filters["set_code"].lower())
    codes = [c.lower() for c in filters.get("set_codes") or []]
    if codes:
        marks = ",".join("?" * len(codes))
        where.append(f"c.set_code IN ({marks})")
        args += codes
        if filters.get("sets_mode") == "and" and len(codes) > 1:  # card printed in all selected sets
            where.append(f"c.oracle_id IN (SELECT oracle_id FROM cards WHERE set_code IN ({marks}) "
                         "GROUP BY oracle_id HAVING COUNT(DISTINCT set_code) = ?)")
            args += codes + [len(codes)]
    if filters.get("rarity"):
        where.append("c.rarity = ?")
        args.append(filters["rarity"])
    if filters.get("rarities"):
        where.append(f"c.rarity IN ({','.join('?' * len(filters['rarities']))})")
        args += list(filters["rarities"])

    cols = filters.get("colors") or ""
    mode = filters.get("color_mode") or "any"
    g = __import__("games").current()
    pal, spec = g.palette, g.color_specials   # Magic: WUBRG + C/M as special buttons; Pokémon: energy types
    wubrg = [c for c in cols if c in pal]
    if "C" in cols and "C" in spec:
        where.append("c.colors = ''" if not wubrg or mode == "exact" else
                     "(c.colors = '' OR " + " AND ".join("instr(c.colors, ?) > 0" for _ in wubrg) + ")")
        if wubrg and mode != "exact":
            args += wubrg
            wubrg = []
    if "M" in cols and "M" in spec:
        where.append("length(c.colors) >= 2")
    if wubrg:
        if mode == "atmost":
            outside = [c for c in pal if c not in wubrg]
            where += ["instr(c.colors, ?) = 0" for _ in outside]
            args += outside
        else:
            where += ["instr(c.colors, ?) > 0" for _ in wubrg]
            args += wubrg
            if mode == "exact":
                where.append("length(c.colors) = ?")
                args.append(len(wubrg))

    if filters.get("type"):  # free-text part of the type line (old interface)
        for t in filters["type"].split():
            where.append("c.type_line LIKE ?")
            args.append(f"%{t}%")
    padded = "(' ' || replace(replace(c.type_line, '—', ' '), '//', ' ') || ' ')"
    flags = g.flag_terms   # supertypes that aren't words in the type line (Lorcana: Inkable)

    def term(t):
        return flags[t] if t in flags else f"{padded} LIKE ?"
    for key in ("types", "supertypes"):
        if filters.get(key):
            where.append(_any_all([term(t) for t in filters[key]],
                                  filters.get(f"{key}_mode") or ("all" if key == "supertypes" else "any")))
            args += [f"% {t} %" for t in filters[key] if t not in flags]
    sub = "(' ' || replace(substr(c.type_line, instr(c.type_line, '—') + 1), '//', ' ') || ' ')"
    kws = "(', ' || COALESCE(c.keywords, '') || ', ')"
    if filters.get("subtypes"):
        where.append("instr(c.type_line, '—') > 0 AND "
                     + _any_all([f"{sub} LIKE ?" for _ in filters["subtypes"]], filters.get("subtypes_mode")))
        args += [f"% {t} %" for t in filters["subtypes"]]
    if filters.get("keywords"):
        where.append(_any_all([f"{kws} LIKE ?" for _ in filters["keywords"]], filters.get("keywords_mode")))
        args += [f"%, {k}, %" for k in filters["keywords"]]
    for fmt in filters.get("formats") or []:
        where.append("c.legalities LIKE ?")
        args.append(f'%"{fmt}"%')
    if filters.get("number"):  # collector number (leading zeros ignored): "001" = #1 from every set
        # digits only ("13"): also matches numbers with a letter prefix (Yu-Gi-Oh! "EN013", Pokémon "TG13")
        where.append("(upper(ltrim(c.number, '0')) = upper(ltrim(?, '0')) OR (? NOT GLOB '*[^0-9]*' AND "
                     "c.number GLOB '[A-Za-z]*[0-9]' AND "
                     "ltrim(substr(c.number, length(rtrim(c.number, '0123456789')) + 1), '0') = ltrim(?, '0')))")
        args += [str(filters["number"])] * 3
    if g.variant_numbers and not filters.get("only_ids") and "-" not in str(filters.get("number") or ""):
        # Yu-Gi-Oh!: rarities are separate prints (EN008-UR …) – once per set number in search lists; the
        # rarity is picked in the card's prints (own cards: all the ones you have)
        where.append("instr(c.number, '-') = 0")
    for key, op in (("regulation", "IN"), ("not_regulation", "NOT IN")):   # Pokémon regulation mark (promo_types)
        if filters.get(key):
            marks = ["" if m == "-" else m for m in filters[key]]   # "-" = cards without a mark
            where.append(f"COALESCE(c.promo_types, '') {op} ({','.join('?' * len(marks))})")
            args += marks
    if filters.get("formats_any"):  # legal in at least one of them (advanced search: on/off per format)
        where.append(_any_all(["c.legalities LIKE ?" for _ in filters["formats_any"]], "any"))
        args += [f'%"{fmt}"%' for fmt in filters["formats_any"]]
    # exclude (red ✕ in the advanced search): none of them may match
    for key in ("not_types", "not_supertypes"):
        for t in filters.get(key) or []:
            if t == NO_SUPERTYPE:  # "no supertype" excluded: at least one supertype required
                where.append(_any_all([f"{padded} LIKE ?" for _ in SUPERTYPES], "any"))
                args += [f"% {s} %" for s in SUPERTYPES]
                continue
            if t in flags:
                where.append(f"NOT ({flags[t]})")
                continue
            where.append(f"COALESCE({padded}, '') NOT LIKE ?")
            args.append(f"% {t} %")
    for t in filters.get("not_subtypes") or []:
        where.append(f"(COALESCE(instr(c.type_line, '—'), 0) = 0 OR {sub} NOT LIKE ?)")
        args.append(f"% {t} %")
    for k in filters.get("not_keywords") or []:
        where.append(f"{kws} NOT LIKE ?")
        args.append(f"%, {k}, %")
    if filters.get("not_rarities"):
        where.append(f"COALESCE(c.rarity, '') NOT IN ({','.join('?' * len(filters['not_rarities']))})")
        args += list(filters["not_rarities"])
    for fmt in filters.get("not_formats") or []:
        where.append("COALESCE(c.legalities, '') NOT LIKE ?")
        args.append(f'%"{fmt}"%')
    for key, (lo, hi) in (filters.get("ranges") or {}).items():
        col = RANGE_COLS[key]
        if key in ("pow", "tou", "loy", "move"):
            where.append(f"{col} GLOB '[0-9]*'")
            col = f"CAST({col} AS REAL)"
        if lo is not None:
            where.append(f"{col} >= ?")
            args.append(lo)
        if hi is not None:
            where.append(f"{col} <= ?")
            args.append(hi)
    for field, text, negate in filters.get("texts") or []:
        col = name_col() if field == "name" else TEXT_FIELDS[field]
        where.append(f"COALESCE({col}, '') {'NOT ' if negate else ''}LIKE ?")
        args.append(f"%{text}%")
    for key, op in (("only_ids", "IN"), ("exclude_ids", "NOT IN")):
        if filters.get(key) is not None:
            ids = list(filters[key])
            where.append(f"c.id {op} ({','.join('?' * len(ids))})" if ids else ("0" if op == "IN" else "1"))
            args += ids
    if filters.get("identity") is not None:  # color identity within the commander's colors (deck building)
        for col in "WUBRG":
            if col not in filters["identity"]:
                where.append("instr(COALESCE(c.color_identity, ''), ?) = 0")
                args.append(col)
    if filters.get("one_per_name"):  # one print per card (newest from boosters) – e.g. deck-building suggestions
        where.append("c.id IN (SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY name ORDER BY booster DESC, "
                     "released DESC) AS rn FROM cards WHERE layout NOT IN ('art_series', 'token', "
                     "'double_faced_token', 'emblem', 'reversible_card')) WHERE rn = 1)")
    if filters.get("no_tokens"):
        where.append("c.layout NOT IN ('art_series', 'token', 'double_faced_token', 'emblem')")
    for sql, xs in filters.get("where_sql") or []:   # ready conditions, e.g. the Group-by branch ("All cards")
        where.append(sql)
        args += list(xs)
    return where, args


# ---------- Names in other languages ("Schicksal" finds "Fate of the Sun-Cryst") ----------
_printed = {"idx": None, "keys": None, "busy": False}
_printed_lock = threading.Lock()


def _build_printed():
    """Printed names in all languages -> English card names (once ~2–3 s, then ~5 ms per search)."""
    try:
        with connection() as con:
            rows = con.execute("SELECT l.name, c.name FROM langs l JOIN cards c ON c.set_code = l.set_code AND "
                               "c.number = l.number WHERE l.name IS NOT NULL AND l.lang != 'en'").fetchall()
        idx = {}
        for printed, en in rows:
            if printed and printed != en:
                idx.setdefault(printed.lower(), set()).add(en)
        _printed.update(idx=idx, keys=list(idx), **_blob(list(idx)))
    except Exception:  # noqa: BLE001 – no language index: English names only
        _printed.update(idx={}, keys=[], **_blob([]))
    finally:
        _printed["busy"] = False


def _blob(keys):
    """All printed names in one string (one per line) + where each starts: a search word is found by the regex engine
    in C instead of a Python loop over ~190 000 names (Magic: 213 ms per keystroke in the main thread, survey 0.9.3.18)."""
    starts, pos = [], 0
    for k in keys:
        starts.append(pos)
        pos += len(k) + 1
    return {"blob": "\n".join(keys), "starts": starts}


def prewarm_printed():
    """Build the index of printed names in the background (at startup)."""
    with _printed_lock:
        if _printed["idx"] is not None or _printed["busy"] or not exists():
            return
        _printed["busy"] = True
    threading.Thread(target=_build_printed, daemon=True).start()


def names_by_printed(text, limit=300):
    """English card names whose printed name (e.g. German) contains all words of the search text."""
    words = text.lower().split()
    if not words or sum(len(w) for w in words) < 3 or any(c in text for c in ':<>="'):
        return []
    if _printed["idx"] is None:
        # never silently search English only: in the search thread wait until the index is ready (Pokémon ~0.2 s,
        # Magic with languages ~2–3 s); in the main thread only if it is small – otherwise it keeps building in
        # the background
        main = threading.current_thread() is threading.main_thread()
        prewarm_printed()
        if main and __import__("games").current().online_details:   # Magic: the large index, ~2–3 s
            return []
        for _ in range(200):
            if _printed["idx"] is not None:
                break
            time.sleep(0.025)
        if _printed["idx"] is None:
            return []
    import bisect
    import re
    keys, starts, blob = _printed["keys"], _printed.get("starts"), _printed.get("blob")
    if blob is None:   # an index set from outside (tests): its keys in one string first
        _printed.update(_blob(keys))
        starts, blob = _printed["starts"], _printed["blob"]
    longest, rest = max(words, key=len), words
    out, last = set(), -1
    for m in re.finditer(re.escape(longest), blob):   # in key order, like the loop over the keys before
        i = bisect.bisect_right(starts, m.start()) - 1
        if i == last:
            continue
        last = i
        k = keys[i]
        if all(w in k for w in rest):
            out |= _printed["idx"][k]
            if len(out) >= limit:
                break
    return sorted(out)


def flip_order(order):
    """Reverse an ORDER BY list (each part ASC <-> DESC; commas inside parentheses stay, e.g. instr('WUBRG', …))."""
    parts, depth, cur = [], 0, ""
    for ch in order:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    parts.append(cur.strip())
    out = []
    for t in parts:
        if t.upper().endswith(" DESC"):
            out.append(t[:-5])
        elif t.upper().endswith(" ASC"):
            out.append(t[:-4] + " DESC")
        else:
            out.append(t + " DESC")
    return ", ".join(out)


def search(text="", limit=200, offset=0, sort="relevance", reverse=False, **filters):
    """Full-text search (name, type, rules text, keywords, artist, flavor) + filters. Printed names in other
    languages count too (appended at the end). reverse: reversed sort order."""
    rows = _search(text, limit, offset, sort, reverse=reverse, **filters)
    alt = names_by_printed(text) if text.strip() and offset == 0 and len(rows) < limit else []
    if alt:
        seen = {r["id"] for r in rows}
        with connection() as con:
            where, args = _filters(filters)
            where = where + [f"c.name IN ({','.join('?' * len(alt))})"]
            sql = (f"SELECT c.* FROM cards c WHERE {' AND '.join(where)} "
                   f"ORDER BY {SORTS.get(sort) or 'c.name, c.released DESC'} LIMIT ?")
            rows += [dict(r) for r in con.execute(sql, args + alt + [limit - len(rows)]) if r["id"] not in seen]
    return rows


def name_rank(row, text):
    """How well the NAME matches the search text: 0 exactly, 1 starts with it, 2 has all its words, 3 only through
    rules text, type, artist … ("Energy Switch 75" – Energy Switch before Klink, whose text says energy and switch)."""
    t = " ".join(str(text or "").lower().split())
    names = [str(row.get(k) or "").lower() for k in ("name", "flavor_name") if row.get(k)]
    if not t or not names:
        return 3
    if t in names:
        return 0
    if any(n.startswith(t) for n in names):
        return 1
    words = t.split()
    return 2 if any(all(w in n for w in words) for n in names) else 3


def _search(text="", limit=200, offset=0, sort="relevance", reverse=False, **filters):
    rev = flip_order if reverse else (lambda o: o)
    with connection() as con:
        where, args = _filters(filters)
        if text.strip():
            # relevance: the name first – exactly, then its start, then all words in it (name_rank) – only then hits
            # through other text (bm25 weights: name, type, rules text, keywords, artist, flavor)
            flavor = has_flavor_names()
            words = text.strip().split()
            all_in = " AND ".join("(c.name LIKE ?" + (" OR c.flavor_name LIKE ?)" if flavor else ")") for _ in words)
            order = SORTS.get(sort) or (
                ("(LOWER(c.name) = LOWER(?) OR LOWER(c.flavor_name) = LOWER(?)) DESC, " if flavor else
                 "(LOWER(c.name) = LOWER(?)) DESC, ")
                + ("(c.name LIKE ? OR c.flavor_name LIKE ?) DESC, " if flavor else "(c.name LIKE ?) DESC, ")
                + f"({all_in}) DESC, "
                + "(c.layout IN ('art_series', 'token', 'double_faced_token', 'emblem')), "
                + ("bm25(cards_fts, 12.0, 3.0, 1.0, 3.0, 4.0, 0.5, 12.0), " if flavor else
                   "bm25(cards_fts, 12.0, 3.0, 1.0, 3.0, 4.0, 0.5), ") + "c.released DESC")
            sql = ("SELECT c.* FROM cards_fts f JOIN cards c ON c.rowid = f.rowid WHERE cards_fts MATCH ?"
                   + "".join(" AND " + w for w in where) + f" ORDER BY {rev(order)} LIMIT ? OFFSET ?")
            k = 2 if flavor else 1
            extra = ([text.strip()] * k + [text.strip() + "%"] * k
                     + [f"%{w}%" for w in words for _ in range(k)]) if not SORTS.get(sort) else []
            return [dict(r) for r in con.execute(sql, [fts_terms(text)] + args + extra + [limit, offset])]
        sql = "SELECT c.* FROM cards c" + (" WHERE " + " AND ".join(where) if where else "")
        sql += f" ORDER BY {rev(SORTS.get(sort) or SORTS['name'])} LIMIT ? OFFSET ?"
        return [dict(r) for r in con.execute(sql, args + [limit, offset])]


def matching_ids(text="", **filters):
    """Scryfall IDs of all cards matching search text + filters (for searching your own collection)."""
    with connection() as con:
        where, args = _filters(filters)
        if text.strip():
            sql = ("SELECT c.id FROM cards_fts f JOIN cards c ON c.rowid = f.rowid WHERE cards_fts MATCH ?"
                   + "".join(" AND " + w for w in where))
            ids = {r[0] for r in con.execute(sql, [fts_terms(text)] + args)}
            alt = names_by_printed(text)  # also printed names in other languages
            if alt:
                sql = (f"SELECT c.id FROM cards c WHERE c.name IN ({','.join('?' * len(alt))})"
                       + "".join(" AND " + w for w in where))
                ids |= {r[0] for r in con.execute(sql, alt + args)}
            return ids
        sql = "SELECT c.id FROM cards c" + (" WHERE " + " AND ".join(where) if where else "")
        return {r[0] for r in con.execute(sql, args)}


def _base(text, filters):
    """FROM and WHERE of a search like _search (full text or not) -> (from_sql, where, args)."""
    where, args = _filters(filters)
    if text.strip():
        return ("cards_fts f JOIN cards c ON c.rowid = f.rowid", ["cards_fts MATCH ?"] + where,
                [fts_terms(text)] + args)
    return "cards c", where, args


def group_counts(text, expr, expr_args=(), **filters):
    """Group by in "All cards" (Oliver, after 0.9.2): the branches of one level in SQL instead of loading every card –
    [(value, prints, sum of prices, set name, released)] of the cards matching text + filters. expr: the branch of a
    card as an SQL expression on c (ui/grouping.sql_expr)."""
    with connection() as con:
        src, where, args = _base(text, filters)
        sql = (f"SELECT {expr} AS v, COUNT(*), SUM(COALESCE(c.eur, c.eur_foil, 0)), MAX(c.set_name), MAX(c.released) "
               f"FROM {src}" + (" WHERE " + " AND ".join(where) if where else "") + " GROUP BY v")
        return [tuple(r) for r in con.execute(sql, list(expr_args) + args)]


def distinct_counts(text, exprs, **filters):
    """How many branches each expression would have (the suggestions "branch on by …") – one pass for all."""
    if not exprs:
        return []
    with connection() as con:
        src, where, args = _base(text, filters)
        cols = ", ".join(f"COUNT(DISTINCT {e})" for e, _ in exprs)
        sql = f"SELECT {cols} FROM {src}" + (" WHERE " + " AND ".join(where) if where else "")
        return list(con.execute(sql, [a for _, xs in exprs for a in xs] + args).fetchone())


_FRONT = "lower(CASE WHEN instr(name, ' // ') > 0 THEN substr(name, 1, instr(name, ' // ') - 1) ELSE name END)"
_indexed = set()


def _name_indexes(con):
    """Indexes for case-insensitive and front-face name lookup (once, ~1 s)."""
    if DB_PATH in _indexed:
        return
    try:
        con.execute("CREATE INDEX IF NOT EXISTS cards_lname ON cards(lower(name))")
        con.execute(f"CREATE INDEX IF NOT EXISTS cards_front ON cards({_FRONT})")
        con.commit()
        _indexed.add(DB_PATH)
    except sqlite3.Error:  # e.g. read-only: then just slower
        _indexed.add(DB_PATH)


# sets whose cards aren't really playable (Magic, from Scryfall's set types): gold border (World Championship decks),
# Collectors' Edition (CED/CEI), oversized and display cards ("memorabilia"), tokens, minigames, Vanguard, Un-/holiday
# cards ("funny"). Other games: by the set's name (Jumbo / oversized cards), where their data has one.
UNPLAYABLE_SET_TYPES = ("memorabilia", "token", "minigame", "vanguard", "funny")
UNPLAYABLE_NAMES = ("%jumbo%", "%oversize%", "%world championship%", "%collectors' edition%")


@functools.lru_cache(maxsize=1)
def _unplayable_sets():
    try:
        sets = json.loads((REF / "scryfall_sets.json").read_text("utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(sorted(str(s.get("code") or "").lower() for s in sets if s.get("type") in UNPLAYABLE_SET_TYPES))


def cheapest_ids_for_names(names):
    """{name (lower case): id of its cheapest PLAYABLE print} – a wish for "any version" shows only that one (Oliver,
    review .90: someone wishing for any version means a normal card – not a gold-bordered World Championship copy,
    an oversized one or a placeholder; only if there is nothing else, that one). No tokens/art series at all; without
    any price: the newest print."""
    exact = list(dict.fromkeys(n.strip() for n in names if n and n.strip()))
    if not exact or not exists():
        return {}
    import games
    bad_sets = _unplayable_sets() if games.current().key == "mtg" else ()
    unplayable = ("(COALESCE(border_color, '') = 'gold' OR "
                  + " OR ".join("LOWER(COALESCE(set_name, '')) LIKE ?" for _ in UNPLAYABLE_NAMES)
                  + (f" OR LOWER(set_code) IN ({','.join('?' * len(bad_sets))})" if bad_sets else "") + ")")
    out = {}
    with connection() as con:
        for i in range(0, len(exact), 300):
            part = exact[i:i + 300]
            for name, sid in con.execute(
                    f"SELECT name, id FROM cards WHERE name IN ({','.join('?' * len(part))}) "
                    f"AND layout NOT IN ('art_series', 'token', 'double_faced_token', 'emblem') "
                    f"ORDER BY {unplayable}, COALESCE(eur, eur_foil, 1e9), released DESC",
                    part + list(UNPLAYABLE_NAMES) + list(bad_sets)):
                out.setdefault(name.lower(), sid)
    return out


def ids_for_names(names):
    """All print ids for card names (no tokens/art series) – e.g. "All cards" limited to a wishlist's cards."""
    exact = list(dict.fromkeys(n.strip() for n in names if n and n.strip()))
    if not exact or not exists():
        return []
    out = []
    with connection() as con:
        for i in range(0, len(exact), 300):
            part = exact[i:i + 300]
            out += [r[0] for r in con.execute(
                f"SELECT id FROM cards WHERE name IN ({','.join('?' * len(part))}) "
                f"AND layout NOT IN ('art_series', 'token', 'double_faced_token', 'emblem')", part)]
    return out


def ids_for_prints(prints):
    """Print ids for (set, number, lang) – the print in that language if the database has it, otherwise the English
    one (or any). Lists show exactly these prints instead of every print of the name."""
    want = {}
    for sc, num, lang in prints:
        if sc and num:
            want.setdefault(((sc or "").lower(), str(num)), set()).add(lang or "en")
    if not want or not exists():
        return []
    out = []
    with connection() as con:
        for (sc, num), langs in want.items():
            rows = con.execute("SELECT id, lang FROM cards WHERE set_code = ? AND number = ?", (sc, num)).fetchall()
            by = {}
            for i, lg in rows:
                by.setdefault(lg or "en", i)
            for lg in langs:
                pick = by.get(lg) or by.get("en") or (rows[0][0] if rows else None)
                if pick and pick not in out:
                    out.append(pick)
    return out


_TOTALS = {}   # database path -> {set code: printed set size}


def printed_total(set_code):
    """The set size printed on the cards ("43/62") – only where the data has it reliably (Pokémon: TCGdex
    cardCount.official, table set_ext.official from tools/build_pokemon_db.py). None otherwise (Magic: newer cards
    show none, Yu-Gi-Oh!: none, an older database: not yet)."""
    if DB_PATH not in _TOTALS:
        try:
            with connection() as con:
                _TOTALS[DB_PATH] = {str(c).lower(): int(n) for c, n in
                                    con.execute("SELECT set_code, official FROM set_ext WHERE official > 0")}
        except sqlite3.Error:   # no such table/column
            _TOTALS[DB_PATH] = {}
    return _TOTALS[DB_PATH].get(str(set_code).lower())


def set_by_abbr(abbr):
    """Official set abbreviation ("OBF", Pokémon TCG Live lists) -> set code ("sv03") or None. Only games whose
    database knows abbreviations (table set_ext.abbr, tools/build_pokemon_db.py)."""
    try:
        with connection() as con:
            r = con.execute("SELECT set_code FROM set_ext WHERE abbr = ? COLLATE NOCASE", (abbr,)).fetchone()
    except sqlite3.Error:   # no such table/column (other games, older database)
        return None
    return r[0] if r else None


# the print a name stands for: booster prints first, then the newest – and on a tie (same set and date, e.g. the
# Islands ECL 270/275/280) the lower collector number, then the number as text, then the id: a fixed choice instead of
# the database's order (03.11.; the web's logic/importresolve.js does the same)
_NAME_ORDER = "booster DESC, released DESC, CAST(number AS INTEGER), number, id"


def by_names(names):
    """{name (lowercase): row} – per name the newest normal print (for deck import). Also front-face names of
    double-faced cards ("Delver of Secrets" finds "Delver of Secrets // Insectile Aberration")."""
    exact = list(dict.fromkeys(n.strip() for n in names if n and n.strip()))
    names = [n.lower() for n in exact]
    out = {}
    if not names or not exists():
        return out
    with connection() as con:
        # 1) fast via the index: names spelled exactly like this (the usual case)
        for i in range(0, len(exact), 300):
            part = exact[i:i + 300]
            rows = con.execute(
                f"SELECT * FROM cards WHERE name IN ({','.join('?' * len(part))}) "
                f"AND layout NOT IN ('art_series', 'token', 'double_faced_token', 'emblem') "
                f"ORDER BY {_NAME_ORDER}", part)
            for r in rows:
                d = dict(r)
                full = d["name"].lower()
                out.setdefault(full, d)
                out.setdefault(full.split(" // ")[0], d)
        # 2) the rest (different spelling, front face of a double-faced card) – via two expression indexes
        #    created on first use (otherwise the whole database would have to be read every time)
        names = [n for n in names if n not in out]
        if names:
            _name_indexes(con)
        for expr in ("lower(name)", _FRONT):
            names = [n for n in names if n not in out]
            for i in range(0, len(names), 300):
                part = names[i:i + 300]
                rows = con.execute(
                    f"SELECT *, {_FRONT} AS front FROM cards WHERE {expr} IN ({','.join('?' * len(part))}) "
                    f"AND layout NOT IN ('art_series', 'token', 'double_faced_token', 'emblem') "
                    f"ORDER BY {_NAME_ORDER}", part)
                for r in rows:
                    d = dict(r)
                    for key in (d["name"].lower(), d.pop("front")):
                        out.setdefault(key, d)
    return out


def cards_by_ids(ids, game=None):
    """{id: row} for many IDs at once (game: from another game's database)."""
    ids, out = list(ids), {}
    if not ids or not _has(game):
        return out
    with connection(game) as con:
        for i in range(0, len(ids), 500):
            part = ids[i:i + 500]
            for r in con.execute(f"SELECT * FROM cards WHERE id IN ({','.join('?' * len(part))})", part):
                out[r["id"]] = dict(r)
    return out


def suggest_names(text, game=None, limit=8):
    """Card names while typing – also in other languages ("glurak" -> Charizard), each name once.
    -> [(English name, typed/found name)]. Fast: names only, no full rows."""
    text = (text or "").strip()
    if len(text) < 2 or not _has(game):
        return []
    out, seen = [], set()
    with connection(game) as con:
        for pat in (text + "%", "% " + text + "%", "%" + text + "%"):
            q = ("SELECT DISTINCT name, name FROM cards WHERE name LIKE ? AND layout NOT IN ('token', "
                 "'double_faced_token', 'emblem', 'art_series') ORDER BY length(name) LIMIT ?")
            rows = list(con.execute(q, (pat, limit * 3)))
            try:   # names in other languages (table langs: print -> printed name)
                rows += list(con.execute("SELECT DISTINCT c.name, l.name FROM langs l JOIN cards c ON c.id = l.id "
                                         "WHERE l.name LIKE ? ORDER BY length(l.name) LIMIT ?", (pat, limit * 3)))
            except sqlite3.Error:
                pass
            for en, shown in rows:
                if en and en not in seen:
                    seen.add(en)
                    out.append((en, shown or en))
                if len(out) >= limit:
                    return out
    return out


def by_prints(keys, game=None):
    """{(set_code lowercase, number): row} for many prints at once (e.g. a friend's library).
    game: from another game's database (mixed trades, price alerts across all games)."""
    keys, out = list(dict.fromkeys((str(sc).lower(), str(n)) for sc, n in keys)), {}
    if not keys or not _has(game):
        return out
    with connection(game) as con:
        by_set = {}
        for sc, n in keys:
            by_set.setdefault(sc, []).append(n)
        for sc, nums in by_set.items():
            for i in range(0, len(nums), 400):
                part = nums[i:i + 400]
                for r in con.execute(f"SELECT * FROM cards WHERE set_code = ? AND number IN "
                                     f"({','.join('?' * len(part))})", [sc] + part):
                    out[(sc, r["number"])] = dict(r)
    return out


def _cached(name, compute):
    """Cache the result of a slow evaluation (reading the whole table) next to the database,
    valid until the database is next updated."""
    path = REF / name
    stamp = DB_PATH.stat().st_mtime
    try:
        data = json.loads(path.read_text("utf-8"))
        if data.get("db") == stamp:
            return data["value"]
    except (OSError, ValueError):
        pass
    value = compute()
    try:
        path.write_text(json.dumps({"db": stamp, "value": value}, ensure_ascii=False), "utf-8")
    except OSError:
        pass
    return value


def all_sets(cached_only=False):
    """[(code, name, release date, count)] newest first. cached_only: only if already computed."""
    if not exists():
        return []
    if cached_only:
        try:
            data = json.loads((REF / "sets_cache.json").read_text("utf-8"))
            return [tuple(x) for x in data["value"]] if data.get("db") == DB_PATH.stat().st_mtime else None
        except (OSError, ValueError):
            return None

    def compute():
        with connection() as con:
            return [list(r) for r in con.execute(
                "SELECT set_code, set_name, MAX(released), COUNT(*) FROM cards GROUP BY set_code ORDER BY 3 DESC")]
    return [tuple(x) for x in _cached("sets_cache.json", compute)]


def vocabulary(cached_only=False):
    """Subtypes and keywords of all cards with frequency: {"subtypes": [[name, n]], "keywords": [[name, n]]}."""
    if not exists():
        return None
    if cached_only:
        try:
            data = json.loads((REF / "vocab_cache.json").read_text("utf-8"))
            return data["value"] if data.get("db") == DB_PATH.stat().st_mtime else None
        except (OSError, ValueError):
            return None

    sep = getattr(__import__("games").current(), "subtype_sep", None)   # e.g. a type of several words is one type

    def compute():
        subs, kws = {}, {}
        with connection() as con:
            for type_line, keywords in con.execute("SELECT type_line, keywords FROM cards"):
                for part in (type_line or "").split("//"):
                    if "—" in part:
                        tail = part.split("—", 1)[1]
                        for t in ([x.strip() for x in tail.split(sep) if x.strip()] if sep else tail.split()):
                            if t not in ("—", "·"):   # separators (Yu-Gi-Oh! "—", Lorcana "·")
                                subs[t] = subs.get(t, 0) + 1
                for k in (keywords or "").split(", "):
                    if k:
                        kws[k] = kws.get(k, 0) + 1
        order = lambda d: sorted(([k, v] for k, v in d.items()), key=lambda t: (-t[1], t[0]))  # noqa: E731
        return {"subtypes": order(subs), "keywords": order(kws)}
    return _cached("vocab_cache.json", compute)


def print_likeliness(row, pick=None, foil=False):
    """Sort key "most likely print first" (print question, other versions in the edit view): the image match's
    pick, then prints that exist in this finish (prerelease promos: foil only), booster prints before promos /
    The List, then cheaper (more of them around), then newer. row: card database row or entry."""
    r = dict(row)
    code = str(r.get("set_code") or r.get("set") or "").lower()
    rid = str(r.get("id") or "").rsplit("_", 1)[0]
    fin = r.get("finishes") or ""
    fin = fin.split(",") if isinstance(fin, str) else list(fin)
    other_finish = bool(fin) and ("foil" not in fin and "etched" not in fin if foil else "nonfoil" not in fin)
    promo = bool(r.get("promo_types")) or code == "plst" or (
        __import__("games").current().key == "mtg" and len(code) == 4 and code.startswith("p"))
    price = r.get("eur_foil" if foil else "eur") or r.get("eur") or r.get("usd") or 1e9
    newer = "".join(chr(0x10FFFF - ord(c)) for c in str(r.get("released") or ""))
    return (pick is None or rid != str(pick).rsplit("_", 1)[0], other_finish, not r.get("booster"), promo, price, newer)


def entry_from_row(r):
    """Database row -> card as in the set files (front face)."""
    from scanner.common import image_rel
    faces = json.loads(r["faces"]) if r.get("faces") else []
    per_face = bool(faces and faces[0].get("img_normal"))  # double-faced: entries per face
    return {
        "id": f"{r['id']}_0", "name": faces[0]["name"] if per_face else r["name"],
        "set": r["set_code"].upper(), "number": r["number"], "rarity": r.get("rarity") or "",
        # .get: a short row (aiscan.as_row – the scanner's candidates) has no prices/finishes – never a crash for that
        "booster": bool(r.get("booster")), "finishes": (r.get("finishes") or "").split(",") if r.get("finishes") else [],
        "eur": r.get("eur"), "eur_foil": r.get("eur_foil"), "img": image_rel(r["set_code"], r["number"], 0),
        "url": __import__("games").current().card_url(r["set_code"], r["number"]), "thumb": r.get("img_small") or "",
        **({"flavor_name": r["flavor_name"]} if r.get("flavor_name") else {}),
        **({"plang": r["lang"]} if r.get("lang") and r["lang"] != "en" else {}),   # print language (Pokémon: JP sets)
    }


def languages(set_code, number):
    """Languages this exact print exists in: [(language code, display label, Scryfall ID, printed name)]."""
    if not exists():
        return []
    with connection() as con:
        rows = con.execute("SELECT lang, id, name FROM langs WHERE set_code = ? AND number = ? ORDER BY rowid",
                           (set_code.lower(), number)).fetchall()
        # each language once: Pokémon data has es and es-mx both as "es" – the first row is Spain
        first = {}
        for r in rows:
            first.setdefault(r["lang"], (r["lang"], r["id"], r["name"]))
        if first and "en" not in first:   # Pokémon …: English is the card itself, not a row in langs
            en = con.execute("SELECT id, name FROM cards WHERE set_code = ? AND number = ? LIMIT 1",
                             (set_code.lower(), number)).fetchone()
            if en is not None:
                first["en"] = ("en", en["id"], en["name"])
    order = list(LANG_NAMES)
    rows = sorted(first.values(), key=lambda r: order.index(r[0]) if r[0] in order else 99)
    return [(lang, LANG_NAMES.get(lang, lang.upper()), sid, name) for lang, sid, name in rows]


_printed_of = {}   # (set, number, lang) -> printed name or None, read for a whole list at once (printed_names_for)


def lacks_language(set_code, number, lang):
    """Does the database know this print's languages, but not this one? Then there is no image in it to fetch (The
    List, promos, showcase … rarely exist in German) – never ask the source. False if it knows no languages for the
    print (a new set) or there is no database: then ask as before."""
    if lang in (None, "", "en"):
        return False
    try:
        known = {code for code, *_ in languages(str(set_code).lower(), str(number))}
    except Exception:  # noqa: BLE001
        return False
    return bool(known) and lang not in known


def printed_names_for(prints):
    """printed_name for many prints [(set_code, number, lang)] in one database connection – a log of 1000 cards
    in other languages opened one connection per card before (~0.2 s)."""
    want = {(s.lower(), str(n), l) for s, n, l in prints if l and l != "en" and s} - set(_printed_of)
    if not want or not exists():
        return
    try:
        with connection() as con:
            for k in want:
                r = con.execute("SELECT name FROM langs WHERE set_code = ? AND number = ? AND lang = ? AND name IS NOT NULL",
                                k).fetchone()
                _printed_of[k] = r[0] if r else None
    except Exception:  # noqa: BLE001 – no language index: printed_name answers None as before
        pass


@functools.lru_cache(maxsize=8192)
def printed_name(set_code, number, lang):
    """Printed name of this print in a language (e.g. "Das Schicksal des Sonnen-Gespinsts") or None."""
    if not lang or lang == "en" or not set_code:
        return None
    k = (set_code.lower(), str(number), lang)
    if k in _printed_of:
        return _printed_of[k]
    if not exists():
        return None
    try:
        with connection() as con:
            r = con.execute("SELECT name FROM langs WHERE set_code = ? AND number = ? AND lang = ? AND name IS NOT NULL",
                            (set_code.lower(), str(number), lang)).fetchone()
    except Exception:  # noqa: BLE001 – no language index
        return None
    return r[0] if r else None


def card(card_id):
    with connection() as con:
        r = con.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return dict(r) if r else None


# starting directly in another game: its card types from the start (otherwise "Type ≠ Land" would show in search)
if __import__("games").current().card_types is not None:
    _game_changed()
