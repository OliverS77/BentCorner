"""Price history (Cardmarket in €, TCGplayer in $) from MTGJSON.

First import: AllPrices.json.xz (~47 MB, last 90 days). After that AllPricesToday.json.xz (~4 MB) daily – the
history stays a window of WINDOW days (as much as MTGJSON itself publishes; we don't record beyond what the source
provides). The 1.2 GB JSON file is read as a stream (little memory).
Stored per Scryfall ID: one compressed record, only days with a price change + the last day:
{"e": last day, "cn"/"cf"/"tn"/"tf": [[day, price], …]}  (c = Cardmarket, t = TCGplayer, n = normal, f = foil;
day = days since 1970-01-01).
"""
import csv
import datetime
import io
import json
import lzma
import sqlite3
import time
import zlib


from scanner.common import REF
from net import netpolite

DB = REF / "price-history.sqlite"
BASE = "https://mtgjson.com/api/v5/"
SERIES = (("cn", "cardmarket", "normal"), ("cf", "cardmarket", "foil"),
          ("tn", "tcgplayer", "normal"), ("tf", "tcgplayer", "foil"))
_EPOCH = datetime.date(1970, 1, 1)
WINDOW = 90   # days – no longer than the source itself (MTGJSON: 90 days)


def day_of(s):
    return (datetime.date.fromisoformat(s) - _EPOCH).days


def date_of(day):
    return _EPOCH + datetime.timedelta(days=int(day))


def today():
    return (datetime.date.today() - _EPOCH).days


def exists():
    return DB.exists()


def _connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS hist (sid TEXT PRIMARY KEY, data BLOB) WITHOUT ROWID")
        con.execute("CREATE TABLE IF NOT EXISTS ids (uuid TEXT PRIMARY KEY, sid TEXT) WITHOUT ROWID")
        con.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    except sqlite3.Error:
        con.close()   # broken file: don't keep it locked (Windows) – delete() must be able to remove it
        raise
    return con


def _pack(d):
    return zlib.compress(json.dumps(d, separators=(",", ":")).encode("utf-8"), 9)


def _unpack(b):
    return json.loads(zlib.decompress(b).decode("utf-8"))


def _changes(points):
    """Sorted [(day, price)] -> only the changes (the last day is kept via "e")."""
    out = []
    for d, p in points:
        if not out or out[-1][1] != p:
            out.append([d, p])
    return out


def _window(points, end):
    """Only the last WINDOW days: the price valid on the window's first day is moved up to that day."""
    cut = end - WINDOW + 1
    if not points or points[0][0] >= cut:
        return points
    before = [q for q in points if q[0] < cut]
    inside = [q for q in points if q[0] >= cut]
    if not inside or inside[0][0] > cut:
        inside = [[cut, before[-1][1]]] + inside
    return inside


def _merge(old, new):
    """Merge two records (new points win), then trim to the window."""
    out = {"e": max(old.get("e", 0), new.get("e", 0))}
    for key, *_ in SERIES:
        pts = {}
        for src in (old, new):
            for d, p in src.get(key) or []:
                pts[d] = p
        if pts:
            out[key] = _window(_changes(sorted(pts.items())), out["e"])
    return out


def _entry(paper):
    """MTGJSON "paper" entry -> our record (full daily list, not yet compacted)."""
    out, last = {}, 0
    for key, shop, finish in SERIES:
        series = (((paper.get(shop) or {}).get("retail") or {}).get(finish)) or {}
        if series:
            pts = sorted((day_of(d), round(float(p), 2)) for d, p in series.items() if p is not None)
            if pts:
                out[key] = _changes(pts)
                last = max(last, pts[-1][0])
    if out:
        out["e"] = last
    return out


def _download(name, progress, label):
    """Download a file from MTGJSON into memory (with progress)."""
    r = netpolite.get(BASE + name, stream=True, timeout=60)
    r.raise_for_status()
    total = int(r.headers.get("content-length") or 0)
    buf, done = io.BytesIO(), 0
    for chunk in r.iter_content(1 << 20):
        buf.write(chunk)
        done += len(chunk)
        progress(label, done // (1 << 20), max(1, total // (1 << 20)))
    buf.seek(0)
    return buf


def _build_date():
    """MTGJSON builds its files once a day; the tiny Meta.json names the current build. -> date or None (offline)."""
    try:
        r = netpolite.get(BASE + "Meta.json", timeout=20)
        r.raise_for_status()
        return (r.json().get("data") or {}).get("date") or None
    except Exception:  # noqa: BLE001 – offline / changed format: then simply download as before
        return None


def _seen(con, date, what):
    """Was this MTGJSON build already read for `what` ("prices": today's prices for the library, "hist": the
    history)? Then there is nothing new to download."""
    return bool(date) and dict(con.execute("SELECT k, v FROM meta")).get("mtgjson_" + what) == date


def _note(con, date, *what):
    for w in what if date else ():
        con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", ("mtgjson_" + w, date))
    con.commit()


def _load_ids(con, progress):
    raw = _download("csv/cardIdentifiers.csv.xz", progress, "Price history: loading card mapping …")
    rows = csv.reader(io.TextIOWrapper(lzma.open(raw), "utf-8", newline=""))
    head = next(rows)
    iu, isid = head.index("uuid"), head.index("scryfallId")
    pairs = [(r[iu], r[isid]) for r in rows if len(r) > isid and r[isid]]
    con.execute("DELETE FROM ids")
    con.executemany("INSERT OR REPLACE INTO ids VALUES (?, ?)", pairs)
    con.execute("INSERT OR REPLACE INTO meta VALUES ('ids', ?)", (str(time.time()),))
    con.commit()
    return dict(pairs)


def _stream_entries(fileobj, progress, label, total):
    """(uuid, entry) from a large MTGJSON price file, card by card (without reading it all in)."""
    dec = json.JSONDecoder()
    text = lzma.open(fileobj, "rt", encoding="utf-8")
    buf, pos, eof, n = "", 0, False, 0

    def more():
        nonlocal buf, pos, eof
        chunk = text.read(1 << 20)
        if not chunk:
            eof = True
        buf = buf[pos:] + chunk
        pos = 0

    while '"data":{' not in buf and not eof:
        more()
    pos = buf.index('"data":{') + len('"data":{')
    while True:
        while True:  # skip separators
            if pos >= len(buf):
                if eof:
                    return
                more()
                continue
            ch = buf[pos]
            if ch in " \n\r\t,":
                pos += 1
            elif ch == "}":
                return
            else:
                break
        try:
            key, p = dec.raw_decode(buf, pos)
            p = buf.index(":", p) + 1
            value, p = dec.raw_decode(buf, p)
        except (ValueError, json.JSONDecodeError):
            if eof:
                return
            more()
            continue
        pos = p
        n += 1
        if n % 2000 == 0:
            progress(label, n, total)
        if pos > (4 << 20):
            buf, pos = buf[pos:], 0
        yield key, value


def full_import(progress):
    """Load the complete history (90 days). -> number of cards with history."""
    con = _connect()
    try:
        ids = _load_ids(con, progress)
        raw = _download("AllPrices.json.xz", progress, "Preisverlauf herunterladen …")
        batch, n = {}, 0
        con.execute("DELETE FROM hist")
        for uuid, value in _stream_entries(raw, progress, "Preisverlauf einlesen …", len(ids)):
            sid = ids.get(uuid)
            if not sid:
                continue
            e = _entry(value.get("paper") or {})
            if not e:
                continue
            batch[sid] = _merge(batch[sid], e) if sid in batch else e
            if len(batch) >= 5000:
                n += _write(con, batch, merge=True)  # the same card can occur several times
                batch = {}
        n += _write(con, batch, merge=True)
        con.execute("INSERT OR REPLACE INTO meta VALUES ('updated', ?)", (str(today()),))
        con.execute("INSERT OR REPLACE INTO meta VALUES ('full', ?)", (str(time.time()),))
        con.commit()
        return n
    finally:
        con.close()


def _write(con, batch, merge=False):
    if not batch:
        return 0
    if merge:
        old = {}
        keys = list(batch)
        for i in range(0, len(keys), 500):
            part = keys[i:i + 500]
            q = "SELECT sid, data FROM hist WHERE sid IN (%s)" % ",".join("?" * len(part))
            for sid, data in con.execute(q, part):
                old[sid] = _unpack(data)
        batch = {sid: _merge(old[sid], e) if sid in old else e for sid, e in batch.items()}
    con.executemany("INSERT OR REPLACE INTO hist VALUES (?, ?)", [(s, _pack(e)) for s, e in batch.items()])
    con.commit()
    return len(batch)


def daily_update(progress):
    """Append today's prices (AllPricesToday, ~4 MB). If too much is missing or there is nothing yet: full import.
    -> (number of cards, "voll"/"heute")."""
    st = status()
    if not st or st["updated"] < today() - 60:
        return full_import(progress), "voll"
    con = _connect()
    try:
        ids = dict(con.execute("SELECT uuid, sid FROM ids"))
        stamp = float(dict(con.execute("SELECT k, v FROM meta")).get("ids") or 0)
        date = _build_date()
        if _seen(con, date, "hist"):   # MTGJSON hasn't built a new file since the last time: nothing new to add
            return 0, "heute"
        if not ids or time.time() - stamp > 7 * 86400:  # new cards: refresh the ID mapping weekly
            ids = _load_ids(con, progress)
        raw = _download("AllPricesToday.json.xz", progress, "Loading today's prices …")
        batch = {}
        for uuid, value in _stream_entries(raw, progress, "Heutige Preise einlesen …", len(ids)):
            sid = ids.get(uuid)
            e = _entry(value.get("paper") or {}) if sid else None
            if e:
                batch[sid] = _merge(batch[sid], e) if sid in batch else e
        n = _write(con, batch, merge=True)
        con.execute("INSERT OR REPLACE INTO meta VALUES ('updated', ?)", (str(today()),))
        con.commit()
        _note(con, date, "hist")
        return n, "heute"
    finally:
        con.close()


_CURRENT = {"cn": "eur", "cf": "eur_foil", "tn": "usd", "tf": "usd_foil"}


def _current(e):
    """Last price of each series in a record -> {"eur", "eur_foil", "usd", "usd_foil"}."""
    return {name: e[key][-1][1] for key, name in _CURRENT.items() if e.get(key)}


def today_prices(progress, history=False):
    """Current prices of ALL cards from MTGJSON – one download (AllPricesToday, ~4 MB) instead of requests per set.
    Cardmarket = trend price (€), TCGplayer = market price ($); the same values Scryfall shows.
    history=True: also extend the price history (or load it in full once if it is missing or outdated).
    -> {scryfall-id: {"eur", "eur_foil", "usd", "usd_foil"}}"""
    if history:
        st = status()
        if not st or st["updated"] < today() - 60:
            full_import(progress)  # last day of the history = today's prices
            con = _connect()
            try:
                return {sid: _current(_unpack(data)) for sid, data in con.execute("SELECT sid, data FROM hist")}
            finally:
                con.close()
    con = _connect()
    try:
        ids = dict(con.execute("SELECT uuid, sid FROM ids"))
        stamp = float(dict(con.execute("SELECT k, v FROM meta")).get("ids") or 0)
        date = _build_date()
        if _seen(con, date, "prices"):   # same MTGJSON build as last time: prices already in – nothing to load
            return {}
        if not ids or time.time() - stamp > 7 * 86400:  # new cards: refresh the ID mapping weekly
            ids = _load_ids(con, progress)
        raw = _download("AllPricesToday.json.xz", progress, "Loading today's prices …")
        batch = {}
        for uuid, value in _stream_entries(raw, progress, "Heutige Preise einlesen …", len(ids)):
            sid = ids.get(uuid)
            e = _entry(value.get("paper") or {}) if sid else None
            if e:
                batch[sid] = _merge(batch[sid], e) if sid in batch else e
        if history:
            _write(con, batch, merge=True)
            con.execute("INSERT OR REPLACE INTO meta VALUES ('updated', ?)", (str(today()),))
            con.commit()
        _note(con, date, "prices", *(("hist",) if history else ()))
        return {sid: _current(e) for sid, e in batch.items()}
    finally:
        con.close()


_status_cache = {}


def status():
    """{"cards", "updated" (day), "size"} or None. Cached until the file changes (counting the ~100,000 entries
    took ~0.3 s in the foreground every time a card was opened)."""
    if not exists():
        return None
    try:
        key = (str(DB), DB.stat().st_mtime, DB.stat().st_size)
    except OSError:
        return None
    if _status_cache.get("key") == key:
        return _status_cache["value"]
    value = _status_uncached()
    _status_cache.update(key=key, value=value)
    return value


def _status_uncached():
    try:
        con = _connect()
        try:
            n = con.execute("SELECT COUNT(*) FROM hist").fetchone()[0]
            meta = dict(con.execute("SELECT k, v FROM meta"))
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if not n:
        return None
    return {"cards": n, "updated": int(meta.get("updated") or 0), "size": DB.stat().st_size}


def hint(settings, eta=None):
    """Instead of a chart (no history available): {"text", "canLoad", "until"} – until = expected finish (ms since
    1970, 0 = unknown); eta = seconds until done (from the queue) or None if nothing is loading right now."""
    from system.i18n import tr
    import games
    if games.current().price_source == "daily":   # history builds up from the daily Cardmarket prices
        return {"text": tr("No price history for this card yet – it builds up with the daily prices from Cardmarket."), "canLoad": False, "until": 0}
    if not settings.get("price_history"):
        return {"text": tr("No price history yet. Load once: about 47 MB from MTGJSON (last 90 days), then about 4 MB daily."), "canLoad": True, "until": 0}
    st = status()
    if eta is not None or not st or not st.get("cards"):
        until = int((time.time() + eta) * 1000) if eta is not None else 0
        return {"text": tr("Loading price history"), "canLoad": False, "until": until, "loading": True}
    return {"text": tr("No price history for this printing yet."), "canLoad": False, "until": 0}


def series(sid):
    """History of one card: {"cn": [(date, price)…], …} at daily resolution up to the last day, or None."""
    if not exists():
        return None
    try:
        con = sqlite3.connect(DB, timeout=5)
        try:
            row = con.execute("SELECT data FROM hist WHERE sid = ?", (sid,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    d = _unpack(row[0])
    end = d.get("e", 0)
    out = {}
    for key, *_ in SERIES:
        pts = _window(d.get(key) or [], end)
        if not pts:
            continue
        full = []
        for i, (day, price) in enumerate(pts):
            nxt = pts[i + 1][0] if i + 1 < len(pts) else end + 1
            full += [(date_of(x), price) for x in range(day, max(day + 1, nxt))]
        out[key] = full
    return out or None


def series_many(sids):
    """Like series(), but for many cards with one query. -> {sid: history}"""
    sids = list(dict.fromkeys(sids))
    if not sids or not exists():
        return {}
    raw = {}
    try:
        con = sqlite3.connect(DB, timeout=5)
        try:
            for i in range(0, len(sids), 500):
                part = sids[i:i + 500]
                for sid, data in con.execute(f"SELECT sid, data FROM hist WHERE sid IN ({','.join('?' * len(part))})",
                                             part):
                    raw[sid] = data
        finally:
            con.close()
    except sqlite3.Error:
        return {}
    out = {}
    for sid, blob in raw.items():
        d = _unpack(blob)
        end = d.get("e", 0)
        res = {}
        for key, *_ in SERIES:
            pts = _window(d.get(key) or [], end)
            if not pts:
                continue
            full = []
            for i, (day, price) in enumerate(pts):
                nxt = pts[i + 1][0] if i + 1 < len(pts) else end + 1
                full += [(date_of(x), price) for x in range(day, max(day + 1, nxt))]
            res[key] = full
        if res:
            out[sid] = res
    return out


def delete():
    DB.unlink(missing_ok=True)
