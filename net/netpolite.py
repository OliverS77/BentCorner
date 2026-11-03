"""Polite networking: every request to a third-party service goes through here – with a per-service gap, an honest
User-Agent and a pause when a service reports "too many requests" (HTTP 429).

Where published rules exist, they apply; where not, we deliberately stay slow – better the user waits a
few seconds than a free service blocks the app. Please register new services here.

Read on 2026-10-20 (re-read when the services change):
- Scryfall (scryfall.com/docs/api): User-Agent with app name + version AND Accept header mandatory. Limits:
  /cards/search, /cards/named, /cards/random, /cards/collection 2/s (500 ms), /cards/manifest 10/min, otherwise 10/s;
  *.scryfall.io unlimited. 429 = 30 s block, ignoring it = ban. Large amounts via bulk data, cache the data.
  Data: not behind payment/account/subscription, do not merely redistribute or mirror ("repackage, republish, proxy"),
  the app must add value, no Scryfall logo / no implied endorsement. Images: do not cover or crop copyright and artist,
  do not distort, do not blur/sharpen/desaturate/recolor, no own watermarks;
  for image crops (art_crop) credit artist + copyright elsewhere in the same view.
- Moxfield: no public API, access only on request (support@moxfield.com) → link import OFF.
- Archidekt (archidekt.com/terms): forbids "automated searches, requests, or queries" → link import OFF.
- Commander Spellbook: community project, code MIT, no API rules of their own published → sparingly, only on click.
- EDHREC (edhrec.com/terms, read 2026-10-26): forbids "automated searches, requests, or queries" – same clause as
  Archidekt → OFF (cards/edhrec.py ALLOWED); only data already in the cache is used. Permission asked (backlog).
- EDHTop16: "robust API", no rules published (questions via their Discord) → 2 s.
- MTGJSON: MIT license, attribution (Zach Halpern) + ship the license text.
- TCGdex: free and open source, running it costs them money → take it easy. TCGCSV: sample code uses a 0.25 s gap.
- Frankfurter: no quotas, abuse gets throttled, local caching explicitly welcome.
- Cardmarket: price files are public daily files – at most once a day per game.
- YGOPRODeck (ygoprodeck.com/api-guide, read 2026-10-23): at most 20 requests/s (otherwise blocked for 1 h), store
  data locally, fetch images only ONCE and host them yourself (do not hotlink continuously) – that is why only
  tools/build_yugioh_db.py downloads there; the app gets Yu-Gi-Oh images from our server.
- New games (read 2026-10-25, see docs/new-games/):
  LorcanaJSON (lorcanajson.org): static files, no limits published – check the small metadata.json first and only
  re-download when it changed, prefer the zipped files ("to save bandwidth"); no license for the data. robots.txt
  has "Disallow: /files/" (against crawlers): we never crawl, only fetch the documented download files by name.
  Lorcast (lorcast.com/docs/api): 50–100 ms between requests, otherwise 429 / ban; cache at least 24 h; English only.
  Lorcana images (api.lorcana.ravensburger.com): official host, no rules published – images once, then cached;
  since 2026-10-26 via our mirror (MIRROR), so Ravensburger sees each image only once.
  RiftHunt (api.rifthunt.com): bulk at most once a day, < 10 requests/s, attribution wanted, no affiliate links.
  Riftcodex (api.riftcodex.com): free, at most 100 requests/min. Riot CDN (cmsassets.rgpub.io): card images.
  Riot API (developer.riotgames.com/policies/riftbound): own registered key, which must NOT be in the app ("may not
  be included in your code, especially if you plan on distributing a binary") → only our tools/server call it;
  only assets from the Riot API, no middle-man, no metagame data.
- After a 429 some services block for longer (TCGCSV 10 min, YGOPRODeck 1 h): COOL_429. Big daily files are only
  fetched when they changed: first the small "changed?" file (Scryfall bulk updated_at, MTGJSON Meta.json, TCGCSV
  last-updated.txt, YGOPRODeck checkDBVer, LorcanaJSON metadata.json), otherwise a conditional request (ETag /
  If-Modified-Since, cond_headers + remember) – 304 = nothing downloaded.
  User (2026-10-25): never strain the big publishers – the new hosts get generous gaps (rather slow than fast), one
  request at a time, everything cached; a server error (5xx) pauses that service for at least 30 s, like a 429.
"""
import contextlib
import logging
import os
import threading
import time
from urllib.parse import urlparse, urlunparse

import requests

import version
from games import extra
from system import contacts

log = logging.getLogger("booster")

# honest and reachable: the project page and the contact address (the GitHub repo is private – a 404 for the services)
UA = f"BentCorner/{version.VERSION} (free fan project; {contacts.SITE}/; {contacts.MAIL})"
# Our own tests don't count in the download statistics (Oliver 03.11.2026): with BC_CHECK=1 or in an isolated test run
# (BC_STARTER_* test folders, system/datahome.ISOLATED) every request to our own server carries "X-BC-Check: 1".
# Normal installations never set either, so they never send it.
CHECK_HEADER = ("X-BC-Check", "1")


def test_run():
    from system import datahome
    return os.environ.get("BC_CHECK", "").strip() == "1" or datahome.ISOLATED

# Minimum gap between two requests to the same service (seconds)
# our own server: its names come from system/contacts.py only (forks set their own there)
_OWN_NAMES = (urlparse(contacts.SERVER).hostname, urlparse(contacts.SERVER_OLD).hostname)
POLICY = {
    "api.scryfall.com": 0.12,                # Scryfall: 50–100 ms – we take a bit more
    "cards.scryfall.io": 0.0,                # images: unlimited according to Scryfall
    "svgs.scryfall.io": 0.0,
    "data.scryfall.io": 0.0,                 # bulk data (one file)
    "json.edhrec.com": 2.0,                  # terms forbid automated requests: off (cards/edhrec.py ALLOWED)
    "backend.commanderspellbook.com": 1.0,   # no public rules: careful
    "edhtop16.com": 2.0,
    "api2.moxfield.com": 2.0,                # only on an explicit import
    "archidekt.com": 1.0,
    "mtgjson.com": 1.0,
    "api.tcgdex.net": 0.35,                  # Pokémon: free, but "expensive to run" – take it easy
    "assets.tcgdex.net": 0.1,
    "images.pokemontcg.io": 1.0,             # Pokémon EN images missing at TCGdex: only tools/fill_pokemon_ptcgio.py, once
    "raw.githubusercontent.com": 1.0,        # pokemontcg.io set and card lists (GitHub), only that tool
    "downloads.s3.cardmarket.com": 0.5,      # Cardmarket daily files (one per game and day, in chunks)
    "tcgcsv.com": 0.3,                       # TCGCSV: sample code uses a 0.25 s gap
    "db.ygoprodeck.com": 0.3,                # YGOPRODeck: max. 20/s allowed – we stay far below
    "images.ygoprodeck.com": 0.1,            # images only once (tool), afterwards from our server
    "lorcanajson.org": 2.0,                  # Lorcana data: static files, no rules – metadata.json first
    "api.lorcast.com": 0.5,                  # Lorcana: 50–100 ms required – we take far more
    "cards.lorcast.io": 0.25,
    "api.lorcana.ravensburger.com": 0.25,    # official Lorcana images: CDN (max-age 1 week), each image once, one at a time
    "rifthunt.com": 0.5,                     # Riftbound: < 10/s, bulk at most once a day
    "api.rifthunt.com": 0.5,                 # RiftHunt API host (the bulk files live here)
    "api.riftcodex.com": 1.0,                # Riftbound: at most 100/min
    "cmsassets.rgpub.io": 0.25,              # Riot CDN (Riftbound card images)
    "americas.api.riotgames.com": 1.5,       # Riot API: only tools/server (the key never goes into the app)
    "europe.api.riotgames.com": 1.5,
    "api.frankfurter.dev": 1.0,              # exchange rates: once a day is enough
    "api.frankfurter.app": 1.0,
    **{h: 0.2 for h in _OWN_NAMES},          # our own mailbox (relay.py), also under its former name (fallback,
                                             # see OLD_HOSTS) – the server sets the limits
    **extra("NET_POLICY", {}),               # private games (games/extras.py) bring their own rules
}
# stricter limits for individual paths (service, path prefix) -> gap
PATHS = {
    ("api.scryfall.com", "/cards/search"): 0.55,
    ("api.scryfall.com", "/cards/named"): 0.55,
    ("api.scryfall.com", "/cards/random"): 0.55,
    ("api.scryfall.com", "/cards/collection"): 0.55,
    ("api.scryfall.com", "/cards/manifest"): 6.5,
    **{(h, p): g for h in _OWN_NAMES for p, g in (
        ("/dl/packs/", 0.02),      # our own card images (Yu-Gi-Oh) – our server
        ("/dl/tcgdex/", 0.05),     # Pokémon images via our mirror (≤ 20/s per IP)
        ("/dl/lorcana/", 0.05))},  # Lorcana images via our mirror
    **extra("NET_PATHS", {}),
}
# Card images of Pokémon and Disney Lorcana come via our mirror (the server fetches each image once from the source
# and keeps it for a year; towards the publishers' hosts one request at a time, ≥ 0.25 s Ravensburger) – the source
# sees each image only once instead of once per user (user decision 2026-10-26). If the mirror fails for one image:
# directly from the source (slowly, see FALLBACK_GAP), never in bulk.
MIRROR = {"assets.tcgdex.net": contacts.SERVER + "/dl/tcgdex",
          "api.lorcana.ravensburger.com": contacts.SERVER + "/dl/lorcana",
          **extra("NET_MIRROR", {})}
# only these paths go through the mirror (a source host that also serves pages our tools read: those never)
MIRROR_PATH = {"api.lorcana.ravensburger.com": "/images/", **extra("NET_MIRROR_PATH", {})}
DEFAULT = 0.5
SERVER_HOST = urlparse(contacts.SERVER).hostname
# Former names of our own server (SERVER_OLD until 0.9.1). URLs with them (built into older data,
# e.g. Yu-Gi-Oh! images in the data pack) are asked under SERVER_HOST first; the old name is only the fallback when
# SERVER_HOST does not answer or reports trouble (FAILOVER) – a 404 or 410 (emergency switch) counts as an answer.
OLD_HOSTS = {urlparse(contacts.SERVER_OLD).hostname}
FAILOVER = (502, 503, 504)
FAILOVER_CONNECT = 5.0   # s: connect timeout of the first try at the new name
FAILOVER_REST = 300.0    # s: after a connection failure of the new name, use the old one directly
_new_down_until = [0.0]
OWN = {SERVER_HOST} | OLD_HOSTS   # our own server: its errors lead to the fallback, not to a pause
# minimum pause after a 429 per service (their own block time) – a Retry-After header takes precedence
COOL_429 = {"tcgcsv.com": 600.0, "db.ygoprodeck.com": 3600.0, "images.ygoprodeck.com": 3600.0}
# Mirror says 404 (it only knows some paths – older servers no capitals, i.e. no Japanese "ja/SV/SV10/…"): then
# directly from the source, but slowly, never for bulk downloads (mirror_only) and never twice for a missing image
FALLBACK_GAP = 1.0
# strictly one request at a time (user rule 2026-10-25 for big publishers' sites): the next one starts only after the
# previous one has finished, plus the gap – several image threads then simply wait their turn
SERIAL = {"api.lorcana.ravensburger.com", "cmsassets.rgpub.io", "images.ygoprodeck.com", "assets.tcgdex.net",
          "cards.lorcast.io", "lorcanajson.org", *extra("NET_SERIAL", ())}   # Scryfall's image host is explicitly unlimited
_serial = {h: threading.Lock() for h in SERIAL}
_local = threading.local()
# The ONE memory for missing images (imgcache.is_missing/mark_missing use it too): URL or image path -> time it was
# found missing. Asked again after an hour at the earliest (new sets fill up) – every repaint would ask otherwise.
_missing_at = {}
MISSING_TTL = 3600.0
# A real 404 from the source lasts longer and survives a restart: images the source doesn't have (Japanese prints,
# new promos) were asked again after every start and every hour while scrolling (tester log 0.9.2: hundreds). Asked
# again only after LASTING_DAYS – the source may still add them.
LASTING_DAYS = 3
LASTING_MAX = 20000          # entries kept at most (the oldest drop out)
_lasting = None              # URL -> time.time() of the 404, loaded on first use
_lasting_save = [None]       # pending threading.Timer
_lasting_lock = threading.Lock()


def _lasting_file():
    from system import datahome
    return datahome.HOME / "data" / "cache" / "missing-images.json"


def _lasting_map():
    global _lasting
    if _lasting is None:
        import json
        gone = {}
        try:
            raw = json.loads(_lasting_file().read_text("utf-8"))
            cut = time.time() - LASTING_DAYS * 86400
            gone = {u: float(t) for u, t in raw.items() if isinstance(t, (int, float)) and t > cut}
        except (OSError, ValueError, AttributeError):
            pass
        _lasting = gone
    return _lasting


def _save_lasting():
    import json
    with _lasting_lock:
        _lasting_save[0] = None
        data = dict(_lasting_map())
    try:
        f = _lasting_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":")), "utf-8")
        tmp.replace(f)
    except OSError:
        pass


def is_missing(key):
    """Was this image (URL or path) found missing – within the last hour, or (a real 404) within LASTING_DAYS? Then
    don't ask again."""
    t = _missing_at.get(key)
    if t is not None and time.monotonic() - t < MISSING_TTL:
        return True
    with _lasting_lock:
        g = _lasting_map().get(key)
    return g is not None and time.time() - g < LASTING_DAYS * 86400


def mark_missing(key):
    _missing_at[key] = time.monotonic()


def mark_lasting(url):
    """The source answered 404: remember it for LASTING_DAYS, also over restarts (saved a few seconds later, in one go)."""
    mark_missing(url)
    with _lasting_lock:
        gone = _lasting_map()
        gone[url] = time.time()
        while len(gone) > LASTING_MAX:
            gone.pop(next(iter(gone)))
        if _lasting_save[0] is None:
            _lasting_save[0] = threading.Timer(5.0, _save_lasting)
            _lasting_save[0].daemon = True
            _lasting_save[0].start()


def note_missing(url, r):
    """After an image request: remember a 404."""
    if getattr(r, "status_code", None) == 404:
        mark_lasting(url)


_log = None   # test switch (log_start): every request as {host, path, method, start, end, status}


def log_start():
    """Request log for tests: from now on every request is noted (log_stop returns them)."""
    global _log
    _log = []


def log_stop():
    """End the request log. -> [{"host", "path", "method", "start", "end", "status", "thread"}]"""
    global _log
    out, _log = _log or [], None
    return out


def _request(method, url, host, **kw):
    """requests.request – noted in the test log if it is on."""
    if _log is None:
        return requests.request(method, url, **kw)
    t0 = time.monotonic()
    status = None
    try:
        r = requests.request(method, url, **kw)
        status = r.status_code
        return r
    finally:
        _log.append({"host": host, "path": urlparse(url).path or "/", "method": method, "start": t0,
                     "end": time.monotonic(), "status": status, "thread": threading.get_ident()})
_lock = threading.Lock()
_next = {}       # service -> earliest time for the next request
_cool = {}       # service -> blocked until (after 429)


def _host(url):
    return (urlparse(url).hostname or "").lower()


BLOCKED = set()   # hosts the program must not contact at all (images of a game unlocked only locally)


def block_hosts(hosts):
    BLOCKED.update(h.lower() for h in hosts)


def unblock_hosts(hosts):
    """Emergency switch (games/offswitch.py) turned a game back on: its sources may be asked again."""
    BLOCKED.difference_update(h.lower() for h in hosts)


def _gap(url, host):
    path = urlparse(url).path or "/"
    for (h, p), g in PATHS.items():
        if h == host and path.startswith(p):
            return g
    return POLICY.get(host, DEFAULT)


def _wait(host, gap):
    with _lock:
        now = time.monotonic()
        start = max(now, _next.get(host, 0.0), _cool.get(host, 0.0))
        _next[host] = start + gap
    if start > now:
        time.sleep(start - now)


@contextlib.contextmanager
def mirror_only():
    """Bulk downloads (e.g. whole sets in advance): only via the mirror, no direct fallback to the source."""
    old = getattr(_local, "mirror_only", False)
    _local.mirror_only = True
    try:
        yield
    finally:
        _local.mirror_only = old


def _not_found(url):
    r = requests.Response()
    r.status_code, r.url = 404, url
    return r


def retry_after(value):
    """Retry-After header -> seconds: a number ("120") or an HTTP date ("Wed, 21 Oct 2026 07:28:00 GMT"). 0 = none."""
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
    except (TypeError, ValueError, IndexError, OverflowError):
        return 0.0


def cooling(url):
    """Seconds a service is still paused (after "too many requests") – 0 = free."""
    return max(0.0, _cool.get(_host(url), 0.0) - time.monotonic())


def _with_host(url, host):
    return urlunparse(urlparse(url)._replace(netloc=host))


def _send(method, url, headers=None, **kw):
    """Our own server: under its current name first, the former name only as a fallback (OLD_HOSTS). The first try
    connects with a short timeout (FAILOVER_CONNECT) – a hanging new name must not cost 30 s per request; after a
    connection failure the old name is used directly for FAILOVER_REST seconds (then the new one is tried again)."""
    host = _host(url)
    if host not in OLD_HOSTS and host != SERVER_HOST:
        return _send_one(method, url, headers=headers, **kw)
    new, old = _with_host(url, SERVER_HOST), (url if host in OLD_HOSTS else _with_host(url, next(iter(OLD_HOSTS))))
    if time.monotonic() < _new_down_until[0]:   # new name failed a moment ago: straight to the old one
        try:
            return _send_one(method, old, headers=headers, **kw)
        except requests.RequestException:
            pass   # old name down too: give the new one its chance again
    t = kw.get("timeout", 30)
    first = dict(kw, timeout=t if isinstance(t, tuple) else (min(FAILOVER_CONNECT, t), t))   # read timeout unchanged
    try:
        r = _send_one(method, new, headers=headers, **first)
        _new_down_until[0] = 0.0
        if r.status_code not in FAILOVER:
            return r
        getattr(r, "close", lambda: None)()
    except requests.RequestException as e:
        if isinstance(e, (requests.ConnectionError, requests.ConnectTimeout)):
            _new_down_until[0] = time.monotonic() + FAILOVER_REST
        log.info("%s not reachable (%s) – trying %s", SERVER_HOST, e.__class__.__name__, _host(old))
    return _send_one(method, old, headers=headers, **kw)


def _send_one(method, url, headers=None, **kw):
    kw.setdefault("timeout", 30)   # never without: a hanging request would hold a SERIAL host's lock forever
    host = _host(url)
    if host in BLOCKED:
        raise requests.RequestException(f"{host}: blocked (game unlocked only locally, no images)")
    mirror = MIRROR.get(host) if method == "GET" else None
    if mirror and not (urlparse(url).path or "/").startswith(MIRROR_PATH.get(host, "/")):
        mirror = None
    fallback = False
    if mirror:
        if is_missing(url):   # missing at the source too (after the mirror's 404): not asked again for an hour
            return _not_found(url)
        only = getattr(_local, "mirror_only", False)   # bulk loading (whole sets): never at the source itself
        try:
            r = _send(method, mirror + urlparse(url).path, headers=headers, **kw)
            # 429 too (too fast): then the app waits – do not fall back to TCGdex. 404: see FALLBACK_GAP
            if only or (r.status_code < 500 and r.status_code != 404):
                return r
            fallback = r.status_code == 404
        except requests.RequestException:
            if only:
                raise   # mirror down during bulk loading: stop, rather than whole sets from TCGdex directly
            # otherwise (one image the user looks at): directly from the source
    h = {"User-Agent": UA}
    h.update(headers or {})
    h["User-Agent"] = UA  # always honest, with version number
    if host in OWN and test_run():
        h[CHECK_HEADER[0]] = CHECK_HEADER[1]
    if not any(k.lower() == "accept" for k in h):
        h["Accept"] = "application/json;q=0.9,*/*;q=0.8"   # Scryfall requires an Accept header
    gap = max(_gap(url, host), FALLBACK_GAP) if fallback else _gap(url, host)
    serial = _serial.get(host)
    if serial is not None:
        with serial:
            _wait(host, gap)
            r = _request(method, url, host, headers=h, **kw)
            with _lock:
                _next[host] = max(_next.get(host, 0.0), time.monotonic() + gap)   # gap counts from the end
    else:
        _wait(host, gap)
        r = _request(method, url, host, headers=h, **kw)
    if fallback and r.status_code == 404:
        mark_lasting(url)
    if r.status_code == 429:  # too many requests: stay quiet as long as the service says (at least one minute)
        pause = retry_after(r.headers.get("Retry-After"))
        pause = pause if pause > 0 else COOL_429.get(host, 60.0)
        if host in OWN:   # our own server (image limit): wait briefly, do not block the mailbox
            pause = 2.0
        with _lock:
            _cool[host] = time.monotonic() + pause
    elif r.status_code in (500, 502, 503, 504) and host not in OWN:   # service in trouble: leave it alone for a while
        try:
            pause = max(30.0, float(r.headers.get("Retry-After") or 0))
        except ValueError:
            pause = 30.0
        with _lock:
            _cool[host] = time.monotonic() + pause
    return r


def cond_headers(path):
    """Headers for a conditional request: the ETag / Last-Modified remembered for the local copy `path` (remember).
    No copy or nothing remembered: {} (= normal download)."""
    import json
    import pathlib
    path = pathlib.Path(path)
    try:
        if not path.exists():
            return {}
        m = json.loads(path.with_name(path.name + ".http").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    h = {}
    if m.get("etag"):
        h["If-None-Match"] = m["etag"]
    if m.get("modified"):
        h["If-Modified-Since"] = m["modified"]
    return h


def remember(path, r):
    """After a successful download into `path`: keep its ETag / Last-Modified next to it (<path>.http)."""
    import json
    import pathlib
    path = pathlib.Path(path)
    h = getattr(r, "headers", None) or {}
    m = {"etag": h.get("ETag"), "modified": h.get("Last-Modified")}
    try:
        if m["etag"] or m["modified"]:
            path.with_name(path.name + ".http").write_text(json.dumps(m), "utf-8")
    except OSError:
        pass


def get(url, **kw):
    return _send("GET", url, **kw)


def head(url, **kw):
    """HEAD (e.g. "does this image exist?") – same rules; never through the mirror (only GET is mirrored)."""
    return _send("HEAD", url, **kw)


def post(url, **kw):
    return _send("POST", url, **kw)


def get_large(url, chunk=1_500_000, tries=4, headers=None, progress=None):
    """Download a large file in chunks (Range requests) – some connections/servers cut long downloads after a few
    seconds (e.g. Cardmarket over VPN). Each chunk is retried if it breaks off. -> bytes"""
    out, pos, total = bytearray(), 0, None
    while total is None or pos < total:
        for attempt in range(tries):
            try:
                h = dict(headers or {}, Range=f"bytes={pos}-{pos + chunk - 1}")
                r = _send("GET", url, headers=h, timeout=60)
                if r.status_code == 200:   # server cannot do chunks: then take it all at once
                    return r.content
                r.raise_for_status()
                rng = r.headers.get("Content-Range", "")
                if total is None and "/" in rng:
                    total = int(rng.rsplit("/", 1)[1])
                out += r.content
                pos += len(r.content)
                if not r.content:
                    total = pos
                break
            except requests.RequestException:
                if attempt == tries - 1:
                    raise
                time.sleep(2 * (attempt + 1))
        if progress is not None and total:
            progress(pos, total)
    return bytes(out)
