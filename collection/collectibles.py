# NOTE: this module docstring stays German on purpose – sync_bundled() writes it to data/collectibles/LIESMICH.txt.
"""Badges & Collectibles: alles zu Tauschtickets, was man später für eine Ticket-Statistik, Sonder-Tickets oder einen
Import braucht – damit Beta-Tickets nicht verloren gehen und niemand ihr Aussehen aus dem Gedächtnis nachbauen muss.

data/collectibles/                (liegt im Auto-Backup, für alle Spiele gemeinsam)
  index.html                      lokale Seite: alle Tickets und Ticket-Formate, nachgebaut aus den Daten
  data.js                         dieselben Daten für die Seite (eine Skriptdatei geht auch ohne Server, per Doppelklick)
  tickets/<spiel>/<tausch-id>/<ticket-id>.json   das Ticket + alles drumherum (wer, wann, Karten mit Namen und
                                                 Preisen zum Zeitpunkt, Geld, Programm- und Formatversion, Pixel-Code,
                                                 Ereignisse: gesendet / erhalten / gebucht …)
  tickets/<spiel>/<tausch-id>/<ticket-id>.png    das Ticketbild, sobald es einmal gezeigt wurde
  formats/<format>/               der Code, der das Ticket schreibt und liest (Kopie aus dem Programm) + about.json
  versions/<programmversion>/     Muster-Ticket je Programmversion, in der sich am Ticket etwas geändert hat

Formate und Muster entstehen beim Bauen (tools/ticket_snapshot.py → assets/collectibles) und werden beim Start in
den Datenordner kopiert. Nur lesen/ergänzen – hier wird nie etwas gelöscht.
"""
import json
import pathlib
import shutil
import sys
import threading
import time

from scanner.common import DATA

DIR = DATA / "collectibles"
TICKETS = DIR / "tickets"
_lock = threading.Lock()


def _bundled():
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1]))
    return base / "assets" / "collectibles"


def render_id():
    """ID of the current ticket look (from the build snapshot) – "" without a snapshot."""
    try:
        return json.loads((_bundled() / "manifest.json").read_text("utf-8")).get("current") or ""
    except (OSError, ValueError):
        return ""


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(path)


def _code(t):
    from collection import ticket
    try:
        b = ticket.bits(t)
    except Exception:  # noqa: BLE001
        b = None
    if not b:
        return None
    lay = ticket.RECEIPT
    return {"cols": lay.COLS, "x0": lay.X0, "m": lay.M, "w": lay.W, "bottom": ticket.BOTTOM, "rows": b[0],
            "bits": "".join("1" if v else "0" for v in b[1])}


def _rows(cards):
    """Cards with names and current prices (for the statistics later)."""
    try:
        from cards import carddb
        db = carddb.by_prints([(c[0], c[1]) for c in cards]) if cards and carddb.exists() else {}
    except Exception:  # noqa: BLE001
        db = {}
    out = []
    for c in cards:
        r = db.get((str(c[0]).lower(), str(c[1]))) or {}
        foil = bool(c[3]) if len(c) > 3 else False
        price = r.get("eur_foil") if foil and r.get("eur_foil") is not None else r.get("eur")
        out.append({"set": str(c[0]).upper(), "number": str(c[1]), "lang": (c[2] if len(c) > 2 else "") or "en",
                    "foil": foil, "count": int((c[4] if len(c) > 4 else 1) or 1),
                    "name": (c[5] if len(c) > 5 and c[5] else r.get("name")) or "", "eur": price})
    return out


def _path(t):
    from collection import ticket
    return TICKETS / ticket.game_of(t) / str(t.get("x") or t.get("id")) / f"{t.get('id')}.json"


def archive(t, event, img=None, info=None):
    """Store or update a ticket. event: "sent" | "received" | "accepted" | "booked" | "shown" | "found" …
    img: QImage of the ticket (saved once as PNG). Errors are swallowed – archiving must never disrupt a
    trade."""
    if not t or not t.get("id"):
        return None
    try:
        with _lock:
            return _archive(t, event, img, info)
    except Exception:  # noqa: BLE001
        return None


def _archive(t, event, img, info):
    from collection import ticket
    import version
    p = _path(t)
    try:
        e = json.loads(p.read_text("utf-8")) if p.exists() else None
    except (OSError, ValueError):
        e = None
    now = time.time()
    if e is None:
        e = {"collectible": "trade-ticket", "id": t["id"], "trade": t.get("x") or t["id"], "game": ticket.game_of(t),
             "label": ticket.label(t), "kind": ticket.kind(t), "version_in_trade": int(t.get("n") or 1),
             "issued": t.get("t"), "from": t.get("f"), "to": t.get("o"), "money_eur": int(t.get("m") or 0) / 100,
             "app_version": version.VERSION, "ticket_format": t.get("v"), "render": render_id(),
             "a": _rows(t.get("a") or []), "b": _rows(t.get("b") or []),
             "ticket": t, "code": _code(t), "events": [], "png": None, "first_seen": now}
        try:
            from scanner import common
            from system import userprofile
            settings = json.loads((common.BASE / "settings.json").read_text("utf-8"))
            prof = userprofile.get(settings)
            if prof:
                e["me"] = [prof.get("id") or "", prof.get("name") or ""]
        except Exception:  # noqa: BLE001
            pass
    if not any(x.get("event") == event and x.get("app") == version.VERSION for x in e["events"]) or event == "booked":
        e["events"].append(dict({"event": event, "at": now, "app": version.VERSION}, **(info or {})))
    if img is not None and not e.get("png"):
        png = p.with_suffix(".png")
        png.parent.mkdir(parents=True, exist_ok=True)
        if img.save(str(png), "PNG"):
            e["png"] = png.name
    _write_json(p, e)
    _schedule_index()
    return e


# ---------- On startup: copy formats/samples, collect existing tickets, write the page ----------
def startup():
    threading.Thread(target=_startup, daemon=True, name="collectibles").start()


def _startup():
    try:
        sync_bundled()
        backfill()
        write_index()
    except Exception:  # noqa: BLE001
        pass


def _differs(a, b):
    try:
        return a.read_bytes() != b.read_bytes()
    except OSError:
        return a.exists()


def sync_bundled():
    """Formats, sample tickets and the page from the app into the data folder (only missing ones; page always fresh).
    A sample the app brings in a new form (other sample cards – 0.9.7.29: no Universes Beyond, no default back)
    replaces the one in the data folder; your own tickets live in tickets/ and are never touched."""
    src = _bundled()
    if not src.is_dir():
        return
    DIR.mkdir(parents=True, exist_ok=True)
    for sub in ("formats", "versions"):
        if (src / sub).is_dir():
            for d in (src / sub).iterdir():
                if not d.is_dir():
                    continue
                to = DIR / sub / d.name
                if to.exists() and sub == "versions" and _differs(d / "about.json", to / "about.json"):
                    shutil.rmtree(to, ignore_errors=True)
                if not to.exists():
                    shutil.copytree(d, to)
    fonts = src.parent.parent / "fonts"      # fonts for the page (OFL, shipped with the app anyway)
    for f in ("Inter_18pt-Regular.ttf", "Inter_18pt-Medium.ttf", "BarlowSemiCondensed-SemiBold.ttf",
              "OFL-Inter.txt", "OFL-Barlow.txt"):
        if (fonts / f).exists() and not (DIR / "fonts" / f).exists():
            (DIR / "fonts").mkdir(parents=True, exist_ok=True)
            shutil.copy2(fonts / f, DIR / "fonts" / f)
    if (src / "index.html").exists():
        shutil.copy2(src / "index.html", DIR / "index.html")
    readme = DIR / "LIESMICH.txt"
    if not readme.exists():
        readme.write_text(__doc__.strip() + "\n", "utf-8")


def _personal_dirs():
    out = [DATA / "my-data"]
    g = DATA / "games"
    if g.is_dir():
        out += [d / "my-data" for d in sorted(g.iterdir()) if (d / "my-data").is_dir()]
    return out


def backfill():
    """Collect tickets from trade offers and bookings of all games (everything from before this archive)."""
    for mine in _personal_dirs():
        try:
            offers = json.loads((mine / "offers.json").read_text("utf-8")).get("offers") or []
        except (OSError, ValueError):
            offers = []
        for o in offers:
            for v in o.get("versions") or []:
                if not _path(v).exists():
                    archive(v, "found", info={"status": o.get("status"), "partner": o.get("partner")})
        try:
            raw = json.loads((mine / "bookings.json").read_text("utf-8"))
            books = raw.get("bookings") or raw.get("items") or [] if isinstance(raw, dict) else raw
        except (OSError, ValueError):
            books = []
        for b in books:
            tid = b.get("ticket")
            if not tid or str(tid).startswith("session-"):
                continue
            for p in TICKETS.glob(f"*/*/{tid}.json"):
                try:
                    e = json.loads(p.read_text("utf-8"))
                except (OSError, ValueError):
                    continue
                if not any(x.get("event") == "booked" for x in e.get("events") or []):
                    e["events"].append({"event": "booked", "at": b.get("t"), "booking": b.get("id"),
                                        "session": b.get("session"), "short": len(b.get("short") or []),
                                        "app": "(vor dem Archiv)"})
                    _write_json(p, e)


_timer = None


def _schedule_index():
    global _timer
    if _timer is not None:
        _timer.cancel()
    _timer = threading.Timer(2.0, write_index)
    _timer.daemon = True
    _timer.start()


def write_index():
    """data.js for index.html: all tickets, formats and samples."""
    if not DIR.exists():
        return
    tickets = []
    for p in sorted(TICKETS.glob("*/*/*.json")):
        try:
            e = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        e["dir"] = p.parent.relative_to(DIR).as_posix()
        tickets.append(e)
    versions = []
    for d in sorted((DIR / "versions").glob("*")) if (DIR / "versions").is_dir() else []:
        try:
            versions.append(dict(json.loads((d / "about.json").read_text("utf-8")), dir=d.relative_to(DIR).as_posix()))
        except (OSError, ValueError):
            pass
    formats = []
    for d in sorted((DIR / "formats").glob("*")) if (DIR / "formats").is_dir() else []:
        try:
            formats.append(dict(json.loads((d / "about.json").read_text("utf-8")), dir=d.relative_to(DIR).as_posix()))
        except (OSError, ValueError):
            pass
    tickets.sort(key=lambda e: e.get("issued") or 0, reverse=True)
    data = {"written": time.time(), "tickets": tickets, "versions": versions, "formats": formats}
    tmp = DIR / "data.js.tmp"
    tmp.write_text("window.BC = " + json.dumps(data, ensure_ascii=False) + ";\n", "utf-8")
    tmp.replace(DIR / "data.js")
