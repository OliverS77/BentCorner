"""Library transitions (detail/compare open and close, different card count, side swap).

They are drawn in Qt Quick (qml/components/LibraryView.qml: glide and focus). Only the settings (style, slow
motion) remain here, plus a slim interface for the logic of the library, deck builder and
sessions: run(apply) sets the end state immediately – formerly a widget "overlay" played the transition here.
"""
DURATION = 0.46   # s ("Glide" style, normal speed) – basis for slow motion

STYLES = [("glide", "Gleiten – alle Karten wandern an ihren neuen Platz"),
          ("focus", "Fokus – gewählte Karte fliegt, der Rest ploppt von ihr aus auf")]
SPEEDS = [(1.0, "normal"), (3.0 / DURATION, "Zeitlupe (ca. 3 s)"), (6.0 / DURATION, "Super-Zeitlupe (ca. 6 s)")]


def speed(settings):
    """Factor for all transitions (1 = normal)."""
    try:
        return max(0.5, float((settings or {}).get("anim_speed") or 1.0))
    except (TypeError, ValueError):
        return 1.0


class _Instant:
    """Same interface as the former transition overlays: end state immediately, then then()."""
    running = False
    style = "glide"

    def __init__(self, *args, **kwargs):
        pass

    def run(self, apply, anchor_row=None, swap=None, then=None):
        apply()
        if then is not None:
            then()


GridMorph = PanelMorph = _Instant


