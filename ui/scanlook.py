"""Look of the scan overlay and stream panels: colour constants (refresh_color_consts() recreates them once
the appearance has loaded – read them as scanlook.INK … where that matters), fonts, euro amounts, price tiers,
card labels and small drawing helpers. Moved from app.py (re-exported there)."""
from PySide6 import QtGui
from PySide6.QtCore import QPointF, Qt

import games
from cards import carddb, packtypes
from system.i18n import tr
from ui import look


def shown_name(c, settings):
    """Name of a scanned card: in the card's language (setting "Card names in card language", default on)
    – otherwise the English name."""
    lang = c.get("lang") or "en"
    if lang != "en" and settings.get("printed_names", True):
        return carddb.printed_name(c.get("set") or "", c.get("number") or "", lang) or c["name"]
    return c["name"]


def lang_tag_needed(c, settings):
    """Language code (DE …) next to the name only if the name isn't already shown in the card's language."""
    return (c.get("lang") or "en") != "en" and shown_name(c, settings) == c["name"]


INK = QtGui.QColor("#eef1ff")
PAUSE_RED = QtGui.QColor("#ff5252")   # "off/paused" – the same red as in the scan bar
MUTED = QtGui.QColor("#8a91a8")
CYAN = QtGui.QColor("#62f2ff")
MAGENTA = QtGui.QColor("#ff5bd6")
COND_INK = QtGui.QColor("#ffb36b")   # condition (not Near Mint): its own colour, doesn't clash with foil/language
PLATE = QtGui.QColor(13, 16, 32, 219)
TIER_COLOR = {"hit": MAGENTA, "good": CYAN, "ok": INK, "bulk": MUTED, "none": MUTED}


def refresh_color_consts():
    """Recreate the colour constants after the appearance has loaded (at import time the look's colour redirection
    didn't exist yet)."""
    global INK, MUTED, CYAN, MAGENTA, PLATE, GOLD
    INK, MUTED, CYAN = QtGui.QColor("#eef1ff"), QtGui.QColor("#8a91a8"), QtGui.QColor("#62f2ff")
    MAGENTA, PLATE, GOLD = QtGui.QColor("#ff5bd6"), QtGui.QColor(13, 16, 32, 219), QtGui.QColor("#ffe27a")
    TIER_COLOR.update(hit=MAGENTA, good=CYAN, ok=INK, bulk=MUTED, none=MUTED)
RARITY = dict(games.current().rarities)


def rarity_text(r):
    """Rarity for display – empty if the game has none (e.g. Pokémon promos: no more "–")."""
    t = RARITY.get(r, r) if r else ""
    return "" if not t or t in ("–", "-", "none", "None") else t


def card_meta(c, sep=" · "):
    """"Rarity · SET #No." – without rarity just set and number."""
    return sep.join(x for x in (rarity_text(c.get("rarity")), f"{c['set']} #{c['number']}") if x)


def finish_label(c):
    """Finish + edition of a copy as words ("Reverse Holo · 1st Edition") – "" for the plain one."""
    from cards import finishes
    return finishes.full_label(c)


def finish_short(c):
    """Short label for the pack-list button: Magic F (foil on/off, E = etched), Pokémon N/H/RH (+ "1" for 1st)."""
    from cards import finishes
    s = finishes.short(c)
    if games.current().key == "mtg" and s == "N":
        s = "F"
    return s + ("¹" if c.get("edition") == "1st" else "")


def _game_changed():
    RARITY.clear()
    RARITY.update(games.current().rarities)


def eur(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def tier(price, hit):
    if price is None:
        return "none"
    return "hit" if price >= hit else "good" if price >= 2 else "ok" if price >= 0.5 else "bulk"


def font(px, weight=QtGui.QFont.Weight.Normal, family="Segoe UI"):
    """Overlay font: "Bahnschrift" = heading/number font, "Segoe UI" = text font (appearance)."""
    if family == "Bahnschrift":
        f = look.display_font()
    else:
        fam = look.cfg["font_text"] if family == "Segoe UI" else family
        f = QtGui.QFont(fam)
        f.setFamilies(look._families(fam))
        f.setWeight(weight)
    f.setPixelSize(max(1, round(px)))
    return f


def ease_out(u):
    return 1 - (1 - max(0.0, min(1.0, u))) ** 3


def ease_in_out(u):
    u = max(0.0, min(1.0, u))
    return 3 * u * u - 2 * u * u * u


def heart_path(cx, cy, size):
    path = QtGui.QPainterPath()
    path.moveTo(cx, cy + size * 0.35)
    path.cubicTo(cx - size * 1.1, cy - size * 0.35, cx - size * 0.45, cy - size * 1.05, cx, cy - size * 0.45)
    path.cubicTo(cx + size * 0.45, cy - size * 1.05, cx + size * 1.1, cy - size * 0.35, cx, cy + size * 0.35)
    return path


def star(p, pt, size, col):
    p.setPen(Qt.NoPen)
    p.setBrush(col)
    p.drawPolygon(QtGui.QPolygonF([QPointF(pt.x(), pt.y() - size), QPointF(pt.x() + size * 0.28, pt.y()),
                                   QPointF(pt.x(), pt.y() + size), QPointF(pt.x() - size * 0.28, pt.y())]))
    p.drawPolygon(QtGui.QPolygonF([QPointF(pt.x() - size, pt.y()), QPointF(pt.x(), pt.y() + size * 0.28),
                                   QPointF(pt.x() + size, pt.y()), QPointF(pt.x(), pt.y() - size * 0.28)]))


GOLD = QtGui.QColor("#ffe27a")


def pack_label(snap, settings, planned=0):
    """Heading in the overlay: "Pack 3 / 10" – for single-card sessions "Trade" or "Single purchase", for scanning
    cards just "Cards" (no packs there)."""
    if snap.get("singles"):
        return tr(packtypes.name(settings, snap.get("pack_type") or "trade"))
    if not snap.get("packs_shown", True):
        return tr("Cards")
    return tr(f"Pack {snap['pack_number']} / {planned}") if planned else tr(f"Pack {snap['pack_number']}")


def mix(a, b, t):
    """Colour between a and b (0 = a, 1 = b) as #rrggbb – for chips readable in light and dark."""
    return QtGui.QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                        round(a.blue() + (b.blue() - a.blue()) * t)).name()
