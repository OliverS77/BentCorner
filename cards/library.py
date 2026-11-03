"""Manage downloaded sets. Per set:

    data/recognition/<code>.json   {"code", "name", "updated", "descriptors", "cards": [...]}
    data/recognition/<code>.npz    pts, des, offsets (features of all cards back to back)
    data/card-images/<code>/<number>_<face>.jpg

Images are downloaded only once; downloading again only fetches the card list and prices.
"""
import json
import pathlib
import re
import time

import cv2
import numpy as np
import requests

from scanner.common import BASE, DATA, IMAGES, MINE, RECOG, REF, features, image_rel, lang_img, make_orb, prep
from net import netpolite
from system.i18n import tr

SETS = RECOG
HEADERS = {"User-Agent": netpolite.UA, "Accept": "application/json"}
API = "https://api.scryfall.com"

# Measured with 15 sets / 1.7 M features: features + split LSH search index ≈ 265 bytes per feature,
# card data ≈ 3.5 KB per card
RAM_PER_DESCRIPTOR = 265
RAM_PER_CARD = 3500


def _get(url, params=None):
    r = netpolite.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def search(query):
    url, params, cards = f"{API}/cards/search", {"q": query, "unique": "prints", "order": "set"}, []
    while url:
        r = netpolite.get(url, params=params, headers=HEADERS, timeout=30)
        if r.status_code == 404:
            break
        r.raise_for_status()
        data = r.json()
        cards += data["data"]
        url, params = data.get("next_page"), None
        time.sleep(0.12)  # Scryfall asks for at most ~10 requests/s
    return cards


def price(value):
    return float(value) if value not in (None, "") else None


# ---------- Set list from Scryfall (for the in-app search) ----------
CATALOG = REF / "scryfall_sets.json"

# Search order: main sets before Commander before special printings before promos/tokens
TYPE_RANK = {"expansion": 0, "core": 0, "masters": 1, "draft_innovation": 1, "commander": 2, "masterpiece": 3,
             "funny": 3, "starter": 3, "box": 4, "duel_deck": 4, "premium_deck": 4, "planechase": 4,
             "archenemy": 4, "from_the_vault": 4, "spellbook": 4, "arsenal": 4, "promo": 5, "token": 6,
             "memorabilia": 7, "minigame": 7, "vanguard": 7, "treasure_chest": 7, "alchemy": 8}


def catalog_age():
    """Seconds since the set list was last updated (None = never)."""
    return time.time() - CATALOG.stat().st_mtime if CATALOG.exists() else None


def bundled_sets():
    """Set list shipped with the app (fallback for the first start without internet) – only Magic has one."""
    return _game().bundled_sets()


def cached_sets():
    """Set list available instantly without network: the saved copy, otherwise the bundled one."""
    return _game().cached_sets()


def scryfall_sets(max_age=7 * 24 * 3600):
    """All sets of the open game (Magic: Scryfall's paper sets, cached; max_age=0 forces a fresh query)."""
    return _game().sets_catalog(max_age)


def rank_sets(sets, query, exclude=()):
    """Sets matching the input, most important first: the exact set, then its sub-sets
    (Commander, special printings, promos, tokens …), then other matches."""
    q = query.strip().lower()
    if not q:
        return []
    by_code = {s["code"]: s for s in sets}

    def root(s):
        seen = set()
        while s.get("parent") and s["parent"] in by_code and s["code"] not in seen:
            seen.add(s["code"])
            s = by_code[s["parent"]]
        return s["code"]

    heads = {s["code"] for s in sets if s["code"] == q or s["name"].lower() == q}
    words = q.split()
    out = []
    for s in sets:
        if s["code"] in exclude:
            continue
        name = s["name"].lower()
        name_words = re.findall(r"[\w']+", name)
        if s["code"] in heads:
            group = 0
        elif root(s) in heads or s.get("parent") in heads:
            group = 1
        elif name.startswith(q) or s["code"].startswith(q):
            group = 2
        elif all(any(w.startswith(x) for w in name_words) for x in words):
            group = 3
        else:
            continue
        out.append(((group, TYPE_RANK.get(s.get("type"), 5), -s.get("count", 0), s["released"]), s))
    out.sort(key=lambda t: t[0])
    return [s for _, s in out]


SET_TYPE_NAMES = {"expansion": "Hauptset", "core": "Hauptset", "masters": "Masters", "draft_innovation": "Draft",
                  "commander": "Commander", "masterpiece": "Masterpieces", "funny": "Fun", "starter": "Starter",
                  "box": "Box-Set", "duel_deck": "Duel Deck", "premium_deck": "Premium Deck",
                  "planechase": "Planechase", "archenemy": "Archenemy", "from_the_vault": "From the Vault",
                  "spellbook": "Spellbook", "arsenal": "Arsenal", "promo": "Promos", "token": "Tokens",
                  "memorabilia": "Extras", "minigame": "Minispiel", "vanguard": "Vanguard", "alchemy": "Alchemy",
                  "treasure_chest": "Treasure Chest"}


def set_suggestions(sets, query, done=(), info_fn=None):
    """Set search suggestions (the same everywhere): for each match first "Complete bundle" (main set + Commander,
    tokens, promos …), below it the individual sets. done: already loaded/chosen (✓, not added to the bundle again).
    -> [{"text", "codes", "family", "child", "done", "info"}]"""
    out = []
    if not (query or "").strip():
        return out
    done = set(done)
    for root, fam in set_families(sets or [], query):
        missing = [m["code"] for m in fam if m["code"] not in done]
        if len(fam) > 1 and missing:
            out.append({"text": f"{root['name']} – {tr("Complete bundle")}", "codes": missing, "family": True,
                        "child": False, "done": len(missing) < len(fam),
                        "info": info_fn(missing) if info_fn else ""})
        for m in fam:
            out.append({"text": f"{m['code'].upper()} {m['name']}", "codes": [m["code"]], "family": False,
                        "child": len(fam) > 1, "done": m["code"] in done,
                        "info": info_fn([m["code"]]) if info_fn and m["code"] not in done else "",
                        "year": (m.get("released") or "")[:4], "type": m.get("type") or ""})
    return out


def set_families(sets, query, exclude=(), limit=8):
    """Set search matches as families: [(main set, [all sets of the family])]. A family is the main set plus
    everything that points to it (Commander, tokens, promos, special printings …), most important first. exclude:
    codes that are no longer offered (e.g. already loaded)."""
    by_code = {s["code"]: s for s in sets}

    def root(s):
        seen = set()
        while s.get("parent") and s["parent"] in by_code and s["code"] not in seen:
            seen.add(s["code"])
            s = by_code[s["parent"]]
        return s["code"]

    members = {}
    for s in sets:
        members.setdefault(root(s), []).append(s)
    out, done = [], set()
    for s in rank_sets(sets, query):
        r = root(s)
        if r in done:
            continue
        done.add(r)
        fam = [m for m in members.get(r, [s]) if m["code"] not in exclude]
        if not fam:
            continue
        fam.sort(key=lambda m: (m["code"] != r, TYPE_RANK.get(m.get("type"), 5), m.get("released", ""), m["code"]))
        out.append((by_code.get(r, s), fam))
        if len(out) >= limit:
            break
    return out


def _game():
    """The open game's description – it knows its sets, card lists and image addresses (games/<game>.py)."""
    import games
    return games.current()


def set_info(code):
    """(name, parent set code or None)."""
    return _game().set_info(code)


# ---------- Reading ----------
def _meta(code):
    try:
        return json.loads((SETS / f"{code}.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None


_info_cache = {}  # path -> (mtime, info); the list gets redrawn often


def installed_sets():
    """List of downloaded sets with estimated RAM and disk usage."""
    out = []
    for f in sorted(SETS.glob("*.json")) if SETS.exists() else []:
        mtime = f.stat().st_mtime
        hit = _info_cache.get(f)
        if hit and hit[0] == mtime:
            out.append(hit[1])
            continue
        meta = _meta(f.stem)
        if not meta:
            continue
        n = len(meta["cards"])
        disk = sum(p.stat().st_size for p in (IMAGES / f.stem).glob("*.jpg"))
        disk += f.stat().st_size + (f.with_suffix(".npz").stat().st_size if f.with_suffix(".npz").exists() else 0)
        info = {
            "code": meta["code"], "name": meta["name"], "parent": meta.get("parent"), "count": n,
            "updated": meta.get("updated", 0),
            "ram": meta.get("descriptors", n * 800) * RAM_PER_DESCRIPTOR + n * RAM_PER_CARD,
            "disk": disk,
        }
        _info_cache[f] = (mtime, info)
        out.append(info)
    return out


def load_cards(exclude=()):
    """Only the card lists of all sets (without image features) – enough for AI mode and text recognition."""
    cards = []
    for f in sorted(SETS.glob("*.json")) if SETS.exists() else []:
        if f.stem in exclude:
            continue
        meta = _meta(f.stem)
        if meta and f.with_suffix(".npz").exists():
            cards += meta["cards"]
    return cards


def load_library(exclude=()):
    """All sets (except exclude) combined: (cards, pts, des) with one entry per card image."""
    cards, pts, des = [], [], []
    for f in sorted(SETS.glob("*.json")) if SETS.exists() else []:
        if f.stem in exclude:
            continue
        meta = _meta(f.stem)
        npz = f.with_suffix(".npz")
        if not meta or not npz.exists():
            continue
        with np.load(npz) as z:
            P, D, O = z["pts"], z["des"], z["offsets"]
        if len(O) - 1 != len(meta["cards"]):
            continue  # incomplete, rebuilt on the next download
        for i, c in enumerate(meta["cards"]):
            cards.append(c)
            pts.append(P[O[i]:O[i + 1]])
            des.append(D[O[i]:O[i + 1]])
    return cards, pts, des


# ---------- Single cards ----------


def card_entries(c):
    """Scryfall card -> [(entry as in the set files, image URL)], one per card face with an image."""
    faces = [c] if "image_uris" in c else [f for f in c.get("card_faces", []) if "image_uris" in f]
    out = []
    for fi, face in enumerate(faces):
        prices = c.get("prices", {})
        out.append(({
            "id": f"{c['id']}_{fi}",
            "name": face.get("name", c["name"]),
            "set": c["set"].upper(),
            "number": c["collector_number"],
            "rarity": c.get("rarity", ""),
            "booster": bool(c.get("booster", True)),
            "finishes": c.get("finishes", []),
            "eur": price(prices.get("eur")),
            "eur_foil": price(prices.get("eur_foil")),
            "img": image_rel(c["set"], c["collector_number"], fi),
            "url": c.get("scryfall_uri", ""),
            "thumb": face["image_uris"].get("small", ""),
        }, face["image_uris"]["normal"]))
    return out


def scryfall_query(text):
    """Prepare free search text for Scryfall: "fic 0019"/"fic#19" -> set:fic cn:19; a name in another
    language ("Schicksal des Sonnen") -> the matching English names (from the local language index)."""
    from cards import carddb
    from ui.searchbox import split_print_query, split_year
    year, plain = split_year(text)
    if year:   # "glurak 1999" -> Scryfall's own year filter
        return f"{scryfall_query(plain) if plain else ''} year={year}".strip()
    code, num, rest = split_print_query(text)
    if code and num:
        return f"set:{code} cn:{num.lstrip('0') or '0'}"
    if code and not rest:
        return f"set:{code}"
    names = carddb.names_by_printed(text, limit=12) if carddb.exists() else []
    if names:
        return " or ".join(f'!"{n}"' for n in names)
    return text


def search_online(text, limit=40):
    """Card search on Scryfall (all printings, newest first). -> [(entry, image URL)]"""
    try:
        text = scryfall_query(text)
    except Exception:  # noqa: BLE001 – then just search literally
        pass
    r = netpolite.get(f"{API}/cards/search", params={"q": text, "unique": "prints", "order": "released"},
                     headers=HEADERS, timeout=20)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    out = []
    for c in r.json()["data"]:
        faces = card_entries(c)
        if faces:
            out.append(faces[0])  # front face only; the flip button shows the back
        if len(out) >= limit:
            break
    return out


def fetch_image(entry, url):
    """Save the image of a card found online (for the overlay and statistics)."""
    path = BASE / entry["img"]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        img = netpolite.get(url, headers=HEADERS, timeout=30)
        img.raise_for_status()
        path.write_bytes(img.content)
    return entry


DETAILS = REF / "details"  # extra info per card (artist, printings, legality …), fetched once
import games as _games
FORMATS = list(_games.current().legal_short)   # legalities for search/filter (game description)


def _game_changed():
    FORMATS[:] = list(_games.current().legal_short)
    _info_cache.clear()


def card_details(entry):
    """Extra info from Scryfall for a card (cached in data/details)."""
    sid, _, face = entry["id"].rpartition("_")
    path = DETAILS / f"{sid}.json"
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except ValueError:
            pass
    c = _get(f"{API}/cards/{sid}")
    faces = c.get("card_faces") or []
    fi = int(face) if face.isdigit() else 0
    f = faces[fi] if fi < len(faces) else c
    legal = c.get("legalities", {})
    info = {
        "artist": f.get("artist") or c.get("artist"),
        "set_name": c.get("set_name"), "released_at": c.get("released_at"),
        "type_line": f.get("type_line") or c.get("type_line"),
        "flavor_text": f.get("flavor_text") or c.get("flavor_text"),
        "frame_effects": c.get("frame_effects") or [], "promo_types": c.get("promo_types") or [],
        "border_color": c.get("border_color"), "full_art": c.get("full_art"), "textless": c.get("textless"),
        "edhrec_rank": c.get("edhrec_rank"), "reserved": c.get("reserved"), "game_changer": c.get("game_changer"),
        "reprint": c.get("reprint"), "story_spotlight": c.get("story_spotlight"), "keywords": c.get("keywords") or [],
        "prices": c.get("prices") or {},
        "legal": [name for key, name in FORMATS if legal.get(key) == "legal"],
    }
    try:  # all printings of this card: count + first printing
        r = netpolite.get(c["prints_search_uri"] + "&dir=asc", headers=HEADERS, timeout=20)
        r.raise_for_status()
        prints = r.json()
        first = prints["data"][0]
        info.update(prints=prints.get("total_cards"), first_set=first.get("set_name"),
                    first_date=first.get("released_at"))
    except (requests.RequestException, KeyError, IndexError, ValueError):
        pass
    DETAILS.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info, ensure_ascii=False), "utf-8")
    return info


FULL = DETAILS / "komplett"  # everything Scryfall has on a printing (library detail view)


def card_full(sid, max_age=86400):
    """Full Scryfall record of a printing + rulings + printing history. Cached; refetched after one
    day (prices change daily), offline the old copy is kept."""
    path = FULL / f"{sid}.json"
    old = None
    if path.exists():
        try:
            old = json.loads(path.read_text("utf-8"))
            lst = (old.get("prints") or {}).get("list") or [{}]
            if time.time() - old.get("fetched", 0) < max_age and "img" in lst[0]:  # old version without thumbnails
                return old
        except ValueError:
            pass
    try:
        c = _get(f"{API}/cards/{sid}")
    except requests.RequestException:
        if old:
            return old
        raise
    info = {"card": c, "fetched": time.time(), "rulings": [], "prints": None}
    try:
        info["rulings"] = [{"date": x.get("published_at"), "text": x.get("comment"), "source": x.get("source")}
                           for x in _get(c["rulings_uri"]).get("data", [])]
    except (requests.RequestException, KeyError, ValueError):
        pass
    try:  # all printings of this card, oldest first
        pr = _get(c["prints_search_uri"] + "&dir=asc")
        def small(p):  # thumbnail straight from the image server (no API detour)
            uris = p.get("image_uris") or ((p.get("card_faces") or [{}])[0].get("image_uris")) or {}
            return uris.get("small")
        info["prints"] = {"total": pr.get("total_cards"), "list": [
            {"id": p["id"], "set": p["set"], "set_name": p.get("set_name"), "number": p.get("collector_number"),
             "date": p.get("released_at"), "rarity": p.get("rarity"), "eur": (p.get("prices") or {}).get("eur"),
             "eur_foil": (p.get("prices") or {}).get("eur_foil"), "finishes": p.get("finishes") or [],
             "img": small(p), "booster": p.get("booster")}
            for p in pr.get("data", [])]}
    except (requests.RequestException, KeyError, ValueError):
        pass
    FULL.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info, ensure_ascii=False), "utf-8")
    return info


def fetch_bytes(url):
    if netpolite.is_missing(url):   # answered 404 a moment ago – not again on every repaint
        raise requests.HTTPError(f"404 (remembered): {url}")
    r = netpolite.get(url, headers=HEADERS, timeout=20)
    netpolite.note_missing(url, r)
    r.raise_for_status()
    return r.content


# ---------- Writing ----------
def _save_features(code, pts, des):
    offsets = np.cumsum([0] + [len(d) for d in des])
    P = np.concatenate(pts) if pts else np.zeros((0, 2), np.float32)
    D = np.concatenate(des) if des else np.zeros((0, 32), np.uint8)
    tmp = SETS / f"{code}.tmp.npz"
    np.savez(tmp, pts=P, des=D, offsets=offsets)
    tmp.replace(SETS / f"{code}.npz")
    return len(D)


def _save_meta(meta):
    tmp = SETS / f"{meta['code']}.json.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(SETS / f"{meta['code']}.json")


def _fetch_image(url):
    """Download a card image – patiently: some image servers (TCGdex) briefly answer 503 while they are still
    generating an image. Then wait and retry, finally another format (.png or smaller)."""
    tries = [url]
    if url.endswith("/high.jpg"):
        tries += [url[:-4] + ".png", url[:-8] + "low.jpg"]
    r = None
    for u in tries:
        for wait in (0, 2, 5):
            if wait:
                time.sleep(wait)
            r = netpolite.get(u, headers=HEADERS, timeout=30)
            if r.status_code < 500 and r.status_code != 429:
                break
        if r.ok:
            return r.content
    r.raise_for_status()
    return r.content


def download_set(code, progress=lambda text, done, total: None):
    """Download a set (or update its prices). Returns (cards, of which priced)."""
    code = code.strip().lower()
    SETS.mkdir(parents=True, exist_ok=True)
    progress(f"{code.upper()}: loading card list …", 0, 0)   # translated where shown (app.on_progress)
    old = _meta(code)
    if old and "parent" in old:
        name, parent = old["name"], old["parent"]
    else:
        name, parent = set_info(code)
    if not _game().bulk_images:   # Lorcana: images one by one while browsing, never a whole set at once
        raise RuntimeError(tr("In this game, sets aren't downloaded as a whole – images load while you browse."))
    pairs = _game().set_cards(code, progress)   # Magic: Scryfall search, others: their own source
    if not pairs:
        raise RuntimeError(tr(f"There are no cards with images for {code.upper()}."))

    entries = []
    for n, (entry, url) in enumerate(pairs, 1):
        path = BASE / entry["img"]
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_fetch_image(url))
            time.sleep(0.05)
        entries.append(entry)
        progress(f"{code.upper()}: loading card images …", n, len(pairs))

    same_cards = (old and (SETS / f"{code}.npz").exists()
                  and [c["id"] for c in old["cards"]] == [e["id"] for e in entries])
    if same_cards:
        n_desc = old.get("descriptors", 0)
    else:
        orb, pts, des = make_orb(800), [], []
        for i, e in enumerate(entries):
            # imdecode instead of imread: on Windows OpenCV can't open paths with umlauts (e.g. "C:\Users\Jürgen")
            img = cv2.imdecode(np.fromfile(str(BASE / e["img"]), np.uint8), cv2.IMREAD_COLOR)
            p, d = features(orb, prep(img))
            pts.append(p)
            des.append(d)
            progress(f"{code.upper()}: Erkennungsmerkmale berechnen …", i + 1, len(entries))
        n_desc = _save_features(code, pts, des)
    _save_meta({"code": code, "name": name, "parent": parent, "updated": time.time(), "descriptors": n_desc,
                "cards": entries})

    priced = sum(1 for e in entries if e["eur"] is not None or e["eur_foil"] is not None)
    return len(entries), priced


def remove_set(code):
    import shutil
    code = code.lower()
    for p in (SETS / f"{code}.json", SETS / f"{code}.npz"):
        p.unlink(missing_ok=True)
    shutil.rmtree(IMAGES / code, ignore_errors=True)  # incl. language images (card-images/<set>/<lang>/)


OLD_IMG = re.compile(r"data/images/(?:online/)?([^/_]+)_(.+)_(\d+)\.jpg$")


def new_img_path(img):
    """Old image path (data/images/fin_115_0.jpg) -> new one (data/card-images/fin/115_0.jpg)."""
    m = OLD_IMG.match(img or "")
    return f"data/card-images/{m.group(1).lower()}/{m.group(2)}_{m.group(3)}.jpg" if m else img


def _fix_json_images(path, list_keys):
    """Rewrite image paths in a saved JSON file (set or session) to the new storage layout."""
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return
    changed = False

    def fix(entry):
        nonlocal changed
        if isinstance(entry, dict) and entry.get("img", "").startswith("data/images/"):
            entry["img"] = new_img_path(entry["img"])
            changed = True
    for key in list_keys:
        for e in data.get(key) or []:
            fix(e)
    for pk in data.get("packs") or []:
        for e in pk.get("cards", []):
            fix(e)
    st = data.get("stats") or {}
    fix(st.get("biggest_hit"))
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def migrate_layout():
    """Move from the old storage (data/sets, data/images, data/sessions …) to the new folder structure."""
    moves = [(DATA / "sets", RECOG), (DATA / "sessions", MINE / "sessions"), (DATA / "details", REF / "details")]
    for old, new in moves:
        if old.exists():
            new.mkdir(parents=True, exist_ok=True)
            for f in old.iterdir():
                target = new / f.name
                if not target.exists():
                    f.replace(target)
            try:
                old.rmdir()
            except OSError:
                pass
    if (DATA / "scryfall_sets.json").exists() and not CATALOG.exists():
        REF.mkdir(parents=True, exist_ok=True)
        (DATA / "scryfall_sets.json").replace(CATALOG)
    old_images = DATA / "images"
    if old_images.exists():
        for f in list(old_images.rglob("*.jpg")):
            rel = new_img_path("data/images/" + f.relative_to(old_images).as_posix())
            target = BASE / rel
            if rel.startswith("data/card-images/"):
                if target.exists():
                    f.unlink()  # the same card is already in the set folder
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    f.replace(target)
        for d in sorted(old_images.rglob("*"), reverse=True):
            if d.is_dir():
                try:
                    d.rmdir()
                except OSError:
                    pass
        try:
            old_images.rmdir()
        except OSError:
            pass
        for f in RECOG.glob("*.json") if RECOG.exists() else []:
            _fix_json_images(f, ["cards"])
        for f in (MINE / "sessions").glob("*.json") if (MINE / "sessions").exists() else []:
            _fix_json_images(f, [])


def migrate():
    """Take over old storage layouts: first split the very old one (data/cards.json + data/features.npz for all
    sets) into single sets, then move everything into the new folder structure."""
    _migrate_single_file()
    migrate_layout()


def _migrate_single_file():
    old_cards, old_npz = DATA / "cards.json", DATA / "features.npz"
    if not old_cards.exists() or not old_npz.exists():
        return
    cards = json.loads(old_cards.read_text("utf-8"))
    with np.load(old_npz) as z:
        pts = [z[f"p{i}"] for i in range(len(cards))]
        des = [z[f"d{i}"] for i in range(len(cards))]
    SETS.mkdir(parents=True, exist_ok=True)
    by_set = {}
    for i, c in enumerate(cards):
        by_set.setdefault(c["set"].lower(), []).append(i)
    for code, idx in by_set.items():
        if (SETS / f"{code}.json").exists():
            continue
        try:
            name = set_info(code)[0]
        except Exception:
            name = code.upper()
        n_desc = _save_features(code, [pts[i] for i in idx], [des[i] for i in idx])
        _save_meta({"code": code, "name": name, "updated": old_cards.stat().st_mtime,
                    "descriptors": n_desc, "cards": [cards[i] for i in idx]})
    old_cards.unlink()
    old_npz.unlink()


# ---------- Printings in other languages ----------
_lang_cache = {}  # (set, number) -> [(language code, display name, Scryfall ID, printed name)]


def print_languages(set_code, number, online=True):
    """Which languages does exactly this printing exist in? Card database first (offline), else Scryfall."""
    from cards import carddb
    key = (set_code.lower(), number)
    if key in _lang_cache:
        return _lang_cache[key]
    res = carddb.languages(*key) if carddb.has_languages() else []
    if not res and online:   # only Magic asks online (Scryfall)
        res = _game().print_languages_online(*key)
    if res:
        _lang_cache[key] = res
    return res


def fetch_lang_print(entry, lang):
    """Download a language version of a printing (images of all faces) -> image path matching entry's face.
    If the image is already on disk, nothing is downloaded. If the language doesn't exist: RuntimeError."""
    target = lang_img(entry.get("img_en") or entry["img"], lang)
    if (BASE / target).exists():
        return target
    from cards import carddb
    missing = f"No {carddb.LANG_NAMES.get(lang, lang.upper())} image of {entry['name']} online."
    if carddb.exists() and carddb.lacks_language(entry["set"], entry["number"], lang):
        raise LookupError(missing)   # the database knows its languages, this one isn't among them: don't ask
    return _game().fetch_lang_print(entry, lang, target, missing)


def image_url(set_code, number, lang="en", version="normal", face=0):
    """Image address of a printing for cards without a local image – from the game (Magic: Scryfall redirect,
    others: their card database / source; None = there is no image). face=1: back face (Magic)."""
    fn = _game().image_url
    if fn is None:
        return None
    return fn(set_code, number, lang, version, face) if face else fn(set_code, number, lang, version)


# ---------- Sharing sets ----------
def export_sets(codes, path, progress=lambda text, done, total: None):
    """Pack sets into one .zip: recognition/<set>.json/.npz + card-images/<set>/ (incl. language images)."""
    import zipfile
    files = []
    for code in codes:
        code = code.lower()
        files += [p for p in (SETS / f"{code}.json", SETS / f"{code}.npz") if p.exists()]
        files += [p for p in (IMAGES / code).rglob("*.jpg")] if (IMAGES / code).exists() else []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:  # JPG/NPZ are already compressed
        z.writestr("boosterset.json", json.dumps({"sets": [c.lower() for c in codes], "created": time.time()}))
        for n, f in enumerate(files, 1):
            z.write(f, f.relative_to(DATA).as_posix())
            if n % 50 == 0:
                progress("Sets exportieren …", n, len(files))
    return len(files)


def import_sets(path, progress=lambda text, done, total: None):
    """Counterpart to export_sets. Only takes files under recognition/ and card-images/ (older packages:
    erkennung/ and bilder/). -> list of set codes"""
    import zipfile
    old_names = {"erkennung/": "recognition/", "bilder/": "card-images/"}

    def new_name(n):
        for old, new in old_names.items():
            if n.startswith(old):
                return new + n[len(old):]
        return n
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        ok = [n for n in names if re.fullmatch(r"((recognition|erkennung)/[\w-]+\.(json|npz)|(card-images|bilder)/[\w-]+"
                                               r"(/[\w-]+)?/[\w.-]+\.jpg)", n)]
        if not any(new_name(n).startswith("recognition/") for n in ok):
            raise RuntimeError(tr("This is not a Bent°Corner set package."))
        for i, n in enumerate(ok, 1):
            target = DATA / new_name(n)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src:
                data = src.read()
            tmp = target.with_name(target.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(target)
            if i % 50 == 0:
                progress("Sets importieren …", i, len(ok))
    return sorted({pathlib_stem(n) for n in ok if new_name(n).startswith("recognition/")})


def pathlib_stem(name):
    return name.rpartition("/")[2].split(".")[0]
