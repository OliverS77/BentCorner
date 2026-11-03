"""Performance level of the UI – so Bent°Corner stays smooth on weaker machines too.

- performance: no transition animations (cards jump straight to their place), pages and sections without animation,
  no staggered fade-in/out of the cards
- balanced:    transitions on, but only "Glide" (no "Focus") and a bit shorter
- beauty:      everything as designed

On first start detect() chooses based on the hardware (hwinfo, local only) – after that the user decides
(Settings → Skin → Animations).
"""
LEVELS = [("performance", "Performance"), ("balanced", "Balanced"), ("beauty", "Beauty")]
HELP = {
    "performance": "Für schwächere Rechner: Karten springen sofort an ihren Platz, Seiten und Abschnitte ohne "
                   "Animation – am sparsamsten.",
    "balanced": "Übergänge an, aber schlichter und etwas kürzer – guter Mittelweg.",
    "beauty": "Alle Animationen, wie sie gestaltet sind – für starke Rechner.",
}
_level = "beauty"


def detect(info):
    """Suggestion from the hardware: threads, RAM, dedicated graphics card."""
    threads, ram, gpu = info.get("threads", 1), info.get("ram_gb", 0), info.get("dedicated", False)
    if threads >= 12 and ram >= 16 and gpu:
        return "beauty"
    if threads >= 6 and ram >= 8:
        return "balanced"
    return "performance"


def set_level(level):
    global _level
    _level = level if level in dict(LEVELS) else "beauty"


def level():
    return _level


def animate():
    """Play transitions at all?"""
    return _level != "performance"


def duration_factor():
    return 0.8 if _level == "balanced" else 1.0
