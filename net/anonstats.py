"""Voluntary, anonymous usage numbers – only if the user consents (settings["stats_share"] = True).

Once a week a small parcel to the mailbox server (POST /v1/stats), WITHOUT any identifier: no ID, no
name, no cards. The server only adds it to the weekly totals; individual parcels are not stored.

    {"v": "0.8.17", "os": "windows", "lang": "de", "games": ["mtg", "pokemon"],
     "use": {"scan": 5, "library": 3, "decks": 0, …},            # on how many of the last 7 days used (0–7)
     "scans": "11-100", "decks": "1-10", "friends": "0", "binders": "1-10", "tickets": "0"}   # rough only

No times, no click counts: an area counts at most once per day – ten misclicks on one day are one
day, whoever really uses something gets several. Amounts only as buckets (0 · 1–10 · 11–100 · 100+), so nobody
can be recognised by exact numbers. Counting happens only with consent (settings["usage"], the last 7 days).
Question: in the first-run setup (onboarding.py), for older installations once after startup – yes/no
equally weighted, changeable at any time under Settings → Legal & Data.
"""
import json
import sys
import time

WEEK = 7 * 86400
# Areas that are counted (navigation pages; "scan" only counts once a card has been scanned, because the
# program starts on the scan page)
AREAS = ("scan", "library", "decks", "testing", "trade", "sessions", "stats", "import", "profile", "settings")
_settings = None


def bind(settings):
    """Remember the settings so mark() can count directly."""
    global _settings
    _settings = settings


def asked(settings):
    return settings.get("stats_share") in (True, False)


def enabled(settings):
    return settings.get("stats_share") is True


def _days():
    return [time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400)) for i in range(7)]


def mark(area, scans=0):
    """Area used today (scans: cards scanned on top). Only with consent, otherwise nothing happens."""
    s = _settings
    if s is None or not enabled(s) or area not in AREAS:
        return
    today, keep = time.strftime("%Y-%m-%d"), set(_days())
    u = s.setdefault("usage", {})
    days = u.setdefault("days", {})
    seen = [d for d in days.get(area) or [] if d in keep]
    if today not in seen:
        seen.append(today)
    days[area] = seen
    if scans:
        n = {d: k for d, k in (u.get("scans") or {}).items() if d in keep}
        n[today] = n.get(today, 0) + int(scans)
        u["scans"] = n


def bucket(n):
    n = int(n or 0)
    return "0" if n <= 0 else "1-10" if n <= 10 else "11-100" if n <= 100 else "100+"


def _tickets_last_week():
    """Ticket events of the last 7 days from the archive (data/collectibles) – only the count."""
    from collection import collectibles
    since, n = time.time() - WEEK, 0
    for p in collectibles.TICKETS.glob("*/*/*.json") if collectibles.TICKETS.exists() else []:
        try:
            e = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        n += sum(1 for ev in e.get("events") or [] if float(ev.get("at") or 0) >= since
                 and ev.get("event") in ("sent", "received", "booked"))
    return n


def used_games(settings):
    """Which games are really used: those with cards in the collection. No cards yet: those chosen during
    setup. (Up to 0.8.16 the currently open game counted – and the program always started in Magic,
    so Pokémon players showed up as Magic in the statistics.)"""
    import games
    have = [k for k, _, ready in games.GAMES if ready and games.collection_items(k)]
    return sorted(have or {str(g) for g in settings.get("games_on") or []} or {games.current().key})[:10]


def payload(settings):
    """Exactly what would be sent (also for the "This is what gets sent" display)."""
    import games
    from system import i18n
    import version

    def count(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return 0
    from collection import binders
    from collection import decks
    from net import relay
    keep = set(_days())
    u = settings.get("usage") or {}
    use = {a: len([d for d in (u.get("days") or {}).get(a) or [] if d in keep]) for a in AREAS}
    scans = sum(k for d, k in (u.get("scans") or {}).items() if d in keep)
    plat = "windows" if sys.platform.startswith("win") else "mac" if sys.platform == "darwin" else "linux"
    return {"v": version.VERSION, "os": plat, "lang": i18n.LANG, "games": used_games(settings),
            "use": use, "scans": bucket(scans), "decks": bucket(count(lambda: len(decks.load()))),
            "friends": bucket(count(lambda: len(relay.ok_friends(settings)))),
            "binders": bucket(count(lambda: len(binders.load()))), "tickets": bucket(count(_tickets_last_week))}


AREA_NAMES = {"scan": "Scannen", "library": "Bibliothek", "decks": "Decks", "testing": "Test", "trade": "Tausch",
              "sessions": "Log", "stats": "Statistik", "import": "Import/Export", "profile": "Profil",
              "settings": "Einstellungen"}


def describe(p):
    """The parcel in words (for the question) – exactly the same values, just readable."""
    from system.i18n import tr
    import games
    names = ", ".join(games.name_of(g) for g in p.get("games") or []) or "–"
    use = p.get("use") or {}
    used = ", ".join(f"{tr(AREA_NAMES[a])} {use.get(a, 0)}" for a in AREAS)
    return "\n".join([
        tr("Version") + f" {p.get('v')} · {str(p.get('os') or '').title()} · {str(p.get('lang') or '').upper()}",
        tr("Games") + f": {names}",
        tr("Days used (out of 7)") + f": {used}",
        tr("Rough (0 · 1–10 · 11–100 · 100+)") + ": " + ", ".join(
            f"{tr(label)} {p.get(k)}" for k, label in (("scans", "gescannt"), ("decks", "Decks"),
                                                     ("friends", "Freunde"), ("binders", "Binder"),
                                                     ("tickets", "Tickets"))),
        tr("Nothing else – no ID, no name, no cards, no times.")])


def due(settings):
    """Due? Never in a test start (--first-run-test), never while developing (without .exe) and never in work builds
    (four digits, only on the developer's PC) – otherwise tests would be counted too."""
    from system import datahome
    import version
    if datahome.TEST or not datahome.FROZEN or not version.is_release():
        return False
    return enabled(settings) and time.time() - float(settings.get("stats_sent") or 0) >= WEEK


def send(settings):
    """Send the parcel (no identifier, no signature). -> True if it arrived."""
    from net import netpolite
    from net import relay
    r = netpolite.post(relay.url(settings) + "/v1/stats", json=payload(settings), timeout=20)
    if r.status_code == 200:
        settings["stats_sent"] = time.time()
        return True
    return False
