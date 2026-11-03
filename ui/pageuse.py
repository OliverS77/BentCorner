"""Which pages someone uses – only on this PC, only for the load order at startup (never sent).

settings["page_use"] = {page: [value, timestamp]}: each visit +1, the value halves per week without a visit. At
startup the app loads the start page first, then the most-used pages, rarely used ones afterwards at leisure (one every
half second) (Main.qml: preload / lateLoad).
"""
import math
import time

HALF_LIFE = 7 * 86400   # after a week without a visit it only counts half
RARE = 0.6              # below this a page counts as rarely used (loads later)
# without counts (fresh install): capture and collection first, management last
DEFAULT = ["scan", "library", "sessions", "trade", "decks", "profile", "testing", "stats", "import", "settings"]


def _score(entry, now):
    try:
        value, t = float(entry[0]), float(entry[1])
    except (TypeError, ValueError, IndexError):
        return 0.0
    return value * math.pow(0.5, max(0.0, now - t) / HALF_LIFE)


def note(settings, page):
    """Page visited."""
    now = time.time()
    use = settings.setdefault("page_use", {})
    use[page] = [round(_score(use.get(page), now) + 1.0, 3), now]


def order(settings, keys):
    """-> (early, late): pages to preload right away (most used first) and those that follow at leisure."""
    use = settings.get("page_use") or {}
    if not use:   # no counts yet: fixed, sensible order, hold nothing back
        return [k for k in DEFAULT if k in keys] + [k for k in keys if k not in DEFAULT], []
    now = time.time()
    scores = {k: _score(use.get(k), now) for k in keys}
    ranked = sorted(keys, key=lambda k: (-scores[k], DEFAULT.index(k) if k in DEFAULT else 99))
    early = [k for k in ranked if scores[k] >= RARE]
    late = [k for k in ranked if scores[k] < RARE]
    return early, late
