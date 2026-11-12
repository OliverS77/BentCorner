"""Set aside (SYNC-LOGS §4, legal/lead 07.11.2026): before this device takes over another device's data – „keep the
data of the device with the code“, another device chose „keep this device's data“ (takeover), or more than 90 days
out of sync – its own data is copied aside, never thrown away.

    data/beiseite/<YYYY-MM-DD_HH-MM-SS>/   one folder per time it happened – never replaced, never deleted by itself
        meta.json                          {"when", "why": "theirs"|"takeover"|"offline"|"restore", "other", "what"}
        games/<game>/…                     the game's own documents (decks, binders, lists, wishlist, collection,
                                           bookings, sessions/)
        settings.json                      the own settings that travel (profile, price alarms, list alarms)

Only OWN data (legal 07.11.): nothing friends shared – their lists and binders (my-data/friends/), their keys and
boards (settings relay) – is ever copied aside, so restoring can never bring back what a friend withdrew.
Several states stay side by side; each can be looked at, brought back or deleted on its own. Bringing one back sets
the current state aside first – nothing is lost silently.
"""
import json
import os
import pathlib
import shutil
import time

OWN_FILES = ("decks.json", "binders.json", "lists.json", "wishlist.json", "collection.json", "bookings.json",
             "offers.json")   # trade offers (legal 07.11.): brought back on THIS device only – sent again only by hand
# open tickets (parts of trades still to book): aside only to look at and delete, never brought back (friends' side
# – legal 07.11.); the copy keeps only the friend's name, the cards and the amount – no keys, addresses, mailbox ids
VIEW_ONLY = "pending-trades.json"
OWN_DIRS = ("sessions",)
OWN_SETTINGS = ("profile", "price_alarms", "list_alarms")   # alarms are own data (lead/legal 07.11.)
WHY = ("theirs", "takeover", "offline", "restore")


def root():
    from scanner.common import DATA
    return DATA / "beiseite"


def _what(folder):
    """{"decks", "lists", "binders", "cards"} of a set-aside (or my-data) layout: games/<game>/… or one my-data."""
    out = {"decks": 0, "lists": 0, "binders": 0, "cards": 0}

    def load(p, default):
        try:
            return json.loads(p.read_text("utf-8")) if p.exists() else default
        except (OSError, ValueError):
            return default
    for g in sorted(folder.iterdir()) if folder.exists() else []:
        if not g.is_dir():
            continue
        out["decks"] += len((load(g / "decks.json", {}) or {}).get("decks") or [])
        out["binders"] += len((load(g / "binders.json", {}) or {}).get("binders") or [])
        lists = load(g / "lists.json", {}) or {}
        out["lists"] += sum(len(lists.get(p) or []) for p in ("wish", "have", "custom"))
        out["cards"] += sum(int(it.get("count", 1)) for it in (load(g / "collection.json", {}) or {}).get("items") or []
                            if isinstance(it, dict))
    return out


def put(mine, settings, why, other="", now=None):
    """Copy this device's own data aside. mine: {game: its my-data folder}. -> the new id (folder name).
    Raises OSError if it cannot be copied whole – then the caller must not go on (nothing may be lost)."""
    now = now or time.time()
    base = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(now))
    r = root()
    r.mkdir(parents=True, exist_ok=True)
    sid, n = base, 1
    while (r / sid).exists():   # the same second twice: its own folder, never on top of another
        n += 1
        sid = f"{base}-{n}"
    tmp = r / (sid + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        _copy(mine, settings, tmp, why, other, now)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)   # no half copy left behind
        raise
    os.replace(tmp, r / sid)   # whole or not at all
    return sid


def _copy(mine, settings, tmp, why, other, now):
    for game, folder in mine.items():
        folder = pathlib.Path(folder)
        dest = tmp / "games" / game
        dest.mkdir(parents=True, exist_ok=True)
        for f in OWN_FILES:
            if (folder / f).exists():
                shutil.copy2(folder / f, dest / f)
        for d in OWN_DIRS:
            if (folder / d).is_dir():
                shutil.copytree(folder / d, dest / d, ignore=shutil.ignore_patterns("*.tmp", "*.sync-new"))
        tickets = _tickets_of(folder / VIEW_ONLY)
        if tickets:
            (dest / VIEW_ONLY).write_text(json.dumps({"version": 1, "view_only": True, "pending": tickets},
                                                     ensure_ascii=False, indent=1), "utf-8")
    own = {k: settings[k] for k in OWN_SETTINGS if k in settings}
    (tmp / "settings.json").write_text(json.dumps(own, ensure_ascii=False, indent=1), "utf-8")
    meta = {"when": now, "why": why if why in WHY else "theirs", "other": other if other in ("phone", "pc") else "",
            "what": _what(tmp / "games")}
    (tmp / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")


def _tickets_of(path):
    """Open tickets of one game, reduced to the own record of the trade (legal 07.11.): ticket id, the friend's NAME,
    the cards given/got (with amounts) and when – nothing else of the ticket or the friend."""
    try:
        doc = json.loads(path.read_text("utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return []
    items = doc.get("pending") or []
    if doc.get("view_only"):   # already the reduced copy in a set-aside state
        return [x for x in items if isinstance(x, dict)]
    out = []
    for x in items:
        if not isinstance(x, dict):
            continue
        partner = x.get("partner") or ["", ""]   # [profile ID, name] – only the name stays
        tk = x.get("ticket") if isinstance(x.get("ticket"), dict) else {}
        m = int(tk.get("m") or 0)   # cents, from the ticket's issuer "f" to "o" (collection/ticket.py)
        mine = isinstance(partner, (list, tuple)) and (tk.get("f") or [""])[0] != partner[0]
        out.append({"id": str(tk.get("id") or ""),
                    "partner": str(partner[1] if isinstance(partner, (list, tuple)) and len(partner) > 1 else ""),
                    "give": _cards(x.get("give")), "get": _cards(x.get("get")),
                    "money": m if mine else -m,   # cents I pay (negative: I get)
                    "t": x.get("t")})
    return out


def _cards(rows):
    """Cards of one side: [set, number, language, foil, count, name] – nothing else of the row."""
    out = []
    for r in rows or []:
        if isinstance(r, (list, tuple)):
            out.append([v for v in list(r)[:6] if isinstance(v, (str, int, float, bool)) or v is None])
    return out


def tickets(sid):
    """-> {game: [ticket …]} of a set-aside state – to look at only (no bringing back)."""
    g = folder(sid) / "games"
    out = {}
    for d in sorted(g.iterdir()) if g.is_dir() else []:
        rows = _tickets_of(d / VIEW_ONLY)
        if rows:
            out[d.name] = rows
    return out


def ticket_delete(sid, game, ticket_id):
    """Delete one open ticket from a set-aside state (the user's word). -> True if it was there."""
    p = folder(sid) / "games" / pathlib.Path(game).name / VIEW_ONLY
    rows = _tickets_of(p)
    left = [r for r in rows if r["id"] != str(ticket_id)]
    if len(left) == len(rows):
        return False
    if left:
        p.write_text(json.dumps({"version": 1, "view_only": True, "pending": left}, ensure_ascii=False, indent=1),
                     "utf-8")
    else:
        p.unlink(missing_ok=True)
    return True


def list_all():
    """-> [{"id", "when", "why", "other", "what"}] newest first."""
    out = []
    r = root()
    for d in sorted(r.iterdir(), reverse=True) if r.exists() else []:
        if not d.is_dir() or d.name.endswith(".part"):
            continue
        try:
            m = json.loads((d / "meta.json").read_text("utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"id": d.name, "when": m.get("when"), "why": m.get("why") or "", "other": m.get("other") or "",
                    "what": m.get("what") or _what(d / "games")})
    out.sort(key=lambda e: (e.get("when") or 0, e["id"]), reverse=True)
    return out


def folder(sid):
    p = root() / pathlib.Path(sid).name   # only a folder name – never a path from outside
    if not sid or not p.is_dir() or not (p / "meta.json").exists():
        raise KeyError(sid)
    return p


def restore(sid, mine, settings, now=None):
    """Bring a set-aside state back (the caller turns the sync off first – legal: restoring leaves it off). The
    current state is set aside before (why "restore"), so nothing is lost. Each game's own documents become exactly
    those of the set-aside state (a document it didn't have is removed); friend data stays as it is. Open tickets
    are never brought back – this device's current ones stay as they are (legal 07.11.); restored trade offers lie
    on this device only – nothing is sent to a friend until the user sends it again.
    -> the id the current state was set aside under."""
    src = folder(sid)
    current = put(mine, settings, "restore", now=now)
    for game, mfolder in mine.items():
        mfolder = pathlib.Path(mfolder)
        g = src / "games" / game
        for f in OWN_FILES:
            target = mfolder / f
            if (g / f).exists():
                mfolder.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".tmp")
                shutil.copy2(g / f, tmp)
                os.replace(tmp, target)
            else:
                target.unlink(missing_ok=True)
        for d in OWN_DIRS:
            target = mfolder / d
            new = target.with_name(target.name + ".restore")
            shutil.rmtree(new, ignore_errors=True)
            if (g / d).is_dir():
                shutil.copytree(g / d, new)
            else:
                new.mkdir(parents=True)
            old = target.with_name(target.name + ".old")
            shutil.rmtree(old, ignore_errors=True)
            if target.exists():
                os.replace(target, old)
            os.replace(new, target)
            shutil.rmtree(old, ignore_errors=True)
    try:
        own = json.loads((src / "settings.json").read_text("utf-8"))
    except (OSError, ValueError):
        own = {}
    for k in OWN_SETTINGS:
        if k in own:
            settings[k] = own[k]
        else:
            settings.pop(k, None)
    return current


def delete(sid):
    """Only on the user's word (two taps in the page): the folder goes."""
    shutil.rmtree(folder(sid))


def open_folder(sid):
    """[Ansehen]: the folder in the file manager (local only – nothing leaves the device)."""
    p = folder(sid)
    if hasattr(os, "startfile"):
        os.startfile(str(p))   # noqa: S606 – our own folder
    return p
