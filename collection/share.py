"""Share an opening as an image: a recap card (1600×900) of a session – packs, value, balance, the best hits with
card image, plus your name and your card back. For copying (WhatsApp, Discord) or saving as PNG."""
import time

from PySide6 import QtCore, QtGui
from PySide6.QtCore import QRectF, Qt

from ui import look
from scanner.common import BASE
from system.i18n import tr

W, H = 1600, 900
CYAN, AMBER, PINK, GREEN, RED = "#62f2ff", "#ffb347", "#ff5bd6", "#46d17a", "#ff4d5e"


def eur(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _font(px, bold=True, display=True):
    f = look.display_font(px) if display else look.text_font(px)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def copy_key(c):
    """The same card as another copy: the same print, the same finish (foil/holo …), the same language."""
    return (c.get("id"), c.get("finish") or ("foil" if c.get("foil") else ""), c.get("lang") or "en")


def grouped(cards):
    """Copies of the same card as one entry with "n" (4× Lightning Bolt instead of four rows, 03.11.) – in the order
    of the first copy; the entry is the first copy's dict with n added."""
    out, at = [], {}
    for c in cards:
        k = copy_key(c)
        if k in at:
            at[k]["n"] += 1
        else:
            at[k] = dict(c, n=1)
            out.append(at[k])
    return out


def hits(d, n=5):
    """The most valuable cards of the session (foil price for foils) – copies of the same card once, with "n"."""
    cards = [c for pk in d.get("packs", []) for c in pk.get("cards", [])]
    cards = grouped(sorted(cards, key=lambda c: -(c.get("price") or 0)))
    return cards[:n]


GAP = 0.03   # card <-> its price: share of the card height (big and small cards alike)

# The image leaves the app (Instagram, Discord …): with card images in it, the rights holders' notice, small and grey,
# English whatever the language (legal 03.11.2026, like the notices in LICENSES). Per game; without a drawn card
# image (only placeholders) it goes.
CREDITS = {
    "mtg": "Card images © Wizards of the Coast · via Scryfall · unofficial fan content",
    "pokemon": "Card images © Nintendo, Creatures, GAME FREAK, The Pokémon Company · unofficial fan content",
    "yugioh": "Card images © Konami / 4K Media · unofficial fan content",
    "lorcana": "Card images © Disney · used under Ravensburger's Community Code Policy · "
               "not endorsed by Disney or Ravensburger",   # like the credit in app.py (legal 03.11.)
}
# games whose card images may not go into a shared picture: an old log shows placeholders with the names only
NO_IMAGES = set(__import__("games").extra("SHARE_NO_IMAGES", set()))   # private games (games/extras.py)


def _card(p, rect, c, glow, shimmer=True, images=True):   # -> True when a card image was drawn
    """Card image (or placeholder) with rounded corners and foil shimmer – no shadow (Oliver, 31.10.: it read as a dark
    bar under each card). shimmer=False (Magic): no overlay on the card image – Scryfall forbids covering or
    recoloring its images; foils keep the ✦ next to the price."""
    radius = rect.width() * 0.045
    if glow:  # glow behind the biggest hit
        g = QtGui.QRadialGradient(rect.center(), rect.width() * 0.95)
        c0 = QtGui.QColor(AMBER)
        c0.setAlpha(110)
        g.setColorAt(0, c0)
        g.setColorAt(1, QtGui.QColor(0, 0, 0, 0))
        p.fillRect(rect.adjusted(-rect.width(), -rect.width() * 0.6, rect.width(), rect.width() * 0.6), g)
    path = QtGui.QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.save()
    p.setClipPath(path)
    img = QtGui.QImage(str(BASE / c["img"])) if c.get("img") and images else QtGui.QImage()
    if img.isNull():
        p.fillRect(rect, QtGui.QColor("#1b2033"))
        p.setPen(QtGui.QColor("#aab1c8"))
        p.setFont(_font(max(14, int(rect.width() * 0.08))))
        p.drawText(rect.adjusted(12, 12, -12, -12), Qt.AlignCenter | Qt.TextWordWrap, c["name"])
    else:
        p.drawImage(rect, img.scaled(int(rect.width() * 2), int(rect.height() * 2), Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation))
    if c.get("foil") and (shimmer or img.isNull()):  # rainbow shimmer
        g = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
        for k, col in ((0.0, "#ff5bd6"), (0.35, "#62f2ff"), (0.65, "#ffe66d"), (1.0, "#46d17a")):
            q = QtGui.QColor(col)
            q.setAlpha(55)
            g.setColorAt(k, q)
        p.fillRect(rect, g)
    p.restore()
    return not img.isNull()


def _game(d):
    """The log's game: the dict names it, else the open game (sessions live in its my-data folder)."""
    from games import current
    return d.get("game") or (d.get("info") or {}).get("game") or current().key


def _shimmer(d):
    """Foil shimmer over card images – not for Magic (Scryfall images). Sessions belong to the open game
    (stored in its my-data folder), unless the dict names one."""
    return _game(d) != "mtg"


def render(d, settings):
    """Session dict (Session.to_dict) -> QImage."""
    st, info = d["stats"], d["info"]
    img = QtGui.QImage(W, H, QtGui.QImage.Format_ARGB32_Premultiplied)
    p = QtGui.QPainter(img)
    p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform | QtGui.QPainter.TextAntialiasing)
    bg = QtGui.QColor(look.background())
    p.fillRect(img.rect(), bg)
    for center, col, rad in ((QtCore.QPointF(W * 0.18, H * 0.2), CYAN, 700), (QtCore.QPointF(W * 0.9, H * 0.95), PINK,
                                                                               800)):
        g = QtGui.QRadialGradient(center, rad)
        c = QtGui.QColor(col)
        c.setAlpha(46)
        g.setColorAt(0, c)
        g.setColorAt(1, QtGui.QColor(0, 0, 0, 0))
        p.fillRect(img.rect(), g)
    # header
    title = " · ".join(x for x in (info.get("title"), info.get("product")) if x) or tr("Pack opening")
    p.setPen(QtGui.QColor("#eef1ff"))
    p.setFont(_font(54))
    p.drawText(QRectF(70, 52, W - 520, 70), Qt.AlignLeft | Qt.AlignVCenter, QtGui.QFontMetrics(p.font()).elidedText(
        title, Qt.ElideRight, W - 520))
    sets = ", ".join(s["code"].upper() if s.get("code") else s["name"] for s in info.get("sets", [])[:4])
    sub = time.strftime("%d.%m.%Y", time.localtime(d.get("started") or time.time())) + (f"  ·  {sets}" if sets else "")
    p.setPen(QtGui.QColor("#8a91a8"))
    p.setFont(_font(26, bold=False, display=False))
    p.drawText(QRectF(72, 122, W - 520, 40), Qt.AlignLeft | Qt.AlignVCenter, sub)
    # profile top right
    prof = settings.get("profile") or {}
    from system import userprofile
    chosen = userprofile.shared_back(prof)   # only a back the user chose – never the default (lead 03.11.)
    if chosen or prof.get("name"):
        back = userprofile.back_image(chosen, 96) if chosen else None
        bw = 96 * userprofile.GW / userprofile.GH
        if back is not None and not back.isNull():
            p.drawImage(QRectF(W - 70 - bw, 44, bw, 96), back)
            x_name = W - 90 - bw
        else:
            x_name = W - 70
        p.setPen(QtGui.QColor("#eef1ff"))
        p.setFont(_font(30))
        p.drawText(QRectF(x_name - 360, 60, 360, 40), Qt.AlignRight | Qt.AlignVCenter, prof.get("name") or "")
        p.setPen(QtGui.QColor("#8a91a8"))
        p.setFont(_font(20, bold=False, display=False))
        p.drawText(QRectF(x_name - 360, 100, 360, 30), Qt.AlignRight | Qt.AlignVCenter, tr("opened"))
    # key figures on the left – Orbit's Core fetches no prices: then no amount at all on a picture that leaves the app
    # (legal 03.11.2026: "0" is not 0 €, and an old price beside new ones without is wrong)
    from system import orbit
    priced = orbit.prices_on(settings)
    paid = float(st.get("paid") or info.get("paid") or 0) if priced else 0
    profit = st.get("total", 0) - paid if paid else None
    from scanner import core
    packs = core.has_packs(info)   # pack figures only when opening boosters
    kpis = [(tr("Packs"), str(st.get("packs", 0)), "#eef1ff")] if packs else []
    kpis += [(tr("Cards"), str(st.get("cards", 0)), "#eef1ff")]
    if priced:
        kpis.append((tr("Value"), eur(st.get("total", 0)), CYAN))
    if packs and priced:
        kpis.append((tr("Ø per pack"), eur(st.get("avg_pack", 0)), "#eef1ff"))
    if paid:
        kpis.append((tr("Einsatz"), eur(paid), "#aab1c8"))
        kpis.append((tr("Balance"), ("+" if profit >= 0 else "−") + eur(abs(profit)), GREEN if profit >= 0 else RED))
    y = 196
    for label, value, col in kpis:   # (at most six rows: they end above the counters)
        p.setPen(QtGui.QColor("#8a91a8"))
        p.setFont(_font(22, bold=False, display=False))
        p.drawText(QRectF(72, y, 420, 30), Qt.AlignLeft | Qt.AlignVCenter, label.upper())
        p.setPen(QtGui.QColor(col))
        p.setFont(_font(48))
        p.drawText(QRectF(70, y + 26, 440, 60), Qt.AlignLeft | Qt.AlignVCenter, value)
        y += 92
    counts = st.get("counts") or {}
    import games
    top, second, foil = (tr(x) for x in games.current().counter_labels())   # per game (Lorcana: Enchanted …)
    chips = [(f"{counts.get('mythic', 0)} {top}", "#ff8a3d"), (f"{counts.get('rare', 0)} {second}", "#e7c35a"),
             (f"{counts.get('foil', 0)} {foil}", PINK)]
    x = 72
    p.setFont(_font(22))
    for text, col in chips:
        w = QtGui.QFontMetrics(p.font()).horizontalAdvance(text) + 32
        r = QRectF(x, H - 120, w, 44)
        c = QtGui.QColor(col)
        c.setAlpha(40)
        p.setBrush(c)
        p.setPen(QtGui.QPen(QtGui.QColor(col), 1.5))
        p.drawRoundedRect(r, 22, 22)
        p.setPen(QtGui.QColor(col))
        p.drawText(r, Qt.AlignCenter, text)
        x += w + 12
    # hits: the biggest one large, the next four beside it
    top = hits(d)
    shimmer = _shimmer(d)
    images = _game(d) not in NO_IMAGES
    drawn = False
    money = (lambda c: (eur(c["price"]) if c.get("price") is not None else "")) if priced else (lambda c: "")
    if top:
        big_h = 600
        big = QRectF(560, 210, big_h * 63 / 88, big_h)
        drawn |= _card(p, big, top[0], True, shimmer, images)
        p.setPen(QtGui.QColor(AMBER))
        p.setFont(_font(24))
        gap = GAP * big.height()   # price line: the same share of the card height as under the small cards
        p.drawText(QRectF(big.left(), big.top() - gap - 34, big.width() + 200, 34), Qt.AlignLeft | Qt.AlignBottom,
                   tr("BIGGEST HIT") + (f"  ·  {money(top[0])}" if money(top[0]) else "") + (" ✦" if top[0].get("foil") else "")
                   + (f"  ·  {top[0]['n']}×" if top[0].get("n", 1) > 1 else ""))
        small_h = 280
        sw = small_h * 63 / 88
        for i, c in enumerate(top[1:5]):
            col, row = i % 2, i // 2
            r = QRectF(big.right() + 50 + col * (sw + 30), 210 + row * (small_h + 40), sw, small_h)
            drawn |= _card(p, r, c, False, shimmer, images)
            p.setPen(QtGui.QColor("#eef1ff"))
            p.setFont(_font(20))
            p.drawText(QRectF(r.left(), r.bottom() + GAP * r.height(), r.width(), 28), Qt.AlignHCenter | Qt.AlignTop,
                       " ".join(x for x in (f"{c['n']}×" if c.get("n", 1) > 1 else "", money(c), "✦" if c.get("foil") else "") if x))
    credit = CREDITS.get(_game(d)) if drawn else None
    if credit:   # one line along the bottom, under the counters, left of the logo (the longest one fits)
        p.setPen(QtGui.QColor("#8a91a8"))
        p.setFont(_font(17, bold=False, display=False))
        p.drawText(QRectF(72, H - 50, W - 72 - 340, 30), Qt.AlignLeft | Qt.AlignVCenter, credit)
    # brand bottom right: the long version (card + BENT°CORNER), quiet like the old lettering
    from ui import iconkit
    iconkit.draw_lockup(p, W - 70, H - 30, 22, "dark", 0.55)
    p.end()
    return img
