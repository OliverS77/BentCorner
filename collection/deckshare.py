"""Share decks as an image – in the style of the session recap, with whole cards (card game: show everything; this also
keeps the artist and © line visible, as Scryfall and the Fan Content Policy require).

One deck:      key figures on the left, the cover card(s) large in the middle (commander, two for partners), mana curve,
               roles, combos and Game Changers on the right.
Several decks: lineup – per deck the cover card with name, bracket and colors below ("this is what I'm bringing today").

Cover card: deck["cover"] (sid) – otherwise the commanders – otherwise a suggestion (most frequent, then most expensive
non-land card).
"""
import math

from PySide6 import QtCore, QtGui
from PySide6.QtCore import QRectF, Qt

from ui import look
from games import mtg as _mtg
from system.i18n import tr
from collection import decks

W, H = 1600, 900
MANA = _mtg.GAME.color_hex   # Magic's mana colors (shared decks are Commander decks)
INK, MUTED, DIM = "#eeeeee", "#8e8e8e", "#5e5e5e"


def eur(v):
    return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _font(px, bold=True, display=True):
    f = look.display_font(px) if display else look.text_font(px)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def _price(r):
    return r.get("eur") if r.get("eur") is not None else (r.get("eur_foil") or 0)


def suggested_cover(deck, rows):
    """Suggestion without a commander: the most frequent non-land card, on a tie the most expensive."""
    best = None
    for c in deck.get("cards", []):
        r = rows.get(c["sid"])
        if r is None or c.get("board", "main") != "main" or "Land" in (r.get("type_line") or ""):
            continue
        key = (c["count"], _price(r) or 0)
        if best is None or key > best[0]:
            best = (key, r)
    return best[1] if best else None


def cover_rows(deck, rows):
    """Cover card(s) of a deck: own choice > commander > suggestion."""
    if deck.get("cover") in rows:
        return [rows[deck["cover"]]]
    cm = [rows[s] for s in deck.get("commanders", []) if s in rows]
    if cm:
        return cm[:2]
    r = suggested_cover(deck, rows)
    return [r] if r is not None else []


def _background(p, w, h, identity):
    """Dark background with two soft lights in the deck's colors (colorless: gray)."""
    p.fillRect(QRectF(0, 0, w, h), QtGui.QColor(look.background()))
    cols = [MANA[c] for c in identity] or ["#9a9a9a"]
    for center, col, rad in ((QtCore.QPointF(w * 0.42, h * 0.45), cols[0], w * 0.42),
                             (QtCore.QPointF(w * 0.95, h * 0.95), cols[-1], w * 0.45)):
        g = QtGui.QRadialGradient(center, rad)
        c = QtGui.QColor(col)
        c.setAlpha(40)
        g.setColorAt(0, c)
        g.setColorAt(1, QtGui.QColor(0, 0, 0, 0))
        p.fillRect(QRectF(0, 0, w, h), g)


def _card(p, rect, pm, name, glow=None):
    """Whole card with rounded corners (placeholder with the name while the image loads) – no shadow (Oliver, 31.10.)."""
    radius = rect.width() * 0.045
    if glow:
        g = QtGui.QRadialGradient(rect.center(), rect.width() * 1.0)
        c0 = QtGui.QColor(glow)
        c0.setAlpha(70)
        g.setColorAt(0, c0)
        g.setColorAt(1, QtGui.QColor(0, 0, 0, 0))
        p.fillRect(rect.adjusted(-rect.width(), -rect.width() * 0.5, rect.width(), rect.width() * 0.5), g)
    path = QtGui.QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.save()
    p.setClipPath(path)
    if pm is None or pm.isNull():
        p.fillRect(rect, QtGui.QColor("#1e1e1e"))
        p.setPen(QtGui.QColor("#aaaaaa"))
        p.setFont(_font(max(14, int(rect.width() * 0.07))))
        p.drawText(rect.adjusted(14, 14, -14, -14), Qt.AlignCenter | Qt.TextWordWrap, name or "")
    else:
        p.drawPixmap(rect, pm, QRectF(pm.rect()))
    p.restore()


def _pips(p, x, y, identity, size=30):
    """Color identity as round mana symbols. -> width"""
    f = _font(round(size * 0.55))
    p.setFont(f)
    for i, c in enumerate(identity or "C"):
        r = QRectF(x + i * (size + 6), y, size, size)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(MANA[c]))
        p.drawEllipse(r)
        p.setPen(QtGui.QColor("#111111"))
        p.drawText(r, Qt.AlignCenter, c)
    return len(identity or "C") * (size + 6)


def _chip(p, x, y, text, col, px=20):
    p.setFont(_font(px))
    w = QtGui.QFontMetrics(p.font()).horizontalAdvance(text) + 30
    r = QRectF(x, y, w, px + 20)
    c = QtGui.QColor(col)
    c.setAlpha(36)
    p.setBrush(c)
    p.setPen(QtGui.QPen(QtGui.QColor(col), 1.4))
    p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
    p.setPen(QtGui.QColor(col))
    p.drawText(r, Qt.AlignCenter, text)
    return w


def _label(p, x, y, w, text):
    p.setPen(QtGui.QColor(MUTED))
    p.setFont(_font(19, bold=False, display=False))
    p.drawText(QRectF(x, y, w, 26), Qt.AlignLeft | Qt.AlignVCenter, text.upper())


def watermark(p, rect):
    """The brand bottom right: the long version (card + BENT°CORNER), quiet like the old lettering."""
    from ui import iconkit
    r = rect.adjusted(0, 0, -56, -26)
    iconkit.draw_lockup(p, r.right(), r.bottom(), 22, "light" if look.is_light() else "dark", 0.5)


def _profile(p, w, prof):
    """Name and card back at the top right (as in the session recap)."""
    from system import userprofile
    chosen = userprofile.shared_back(prof)   # only a back the user chose – never the default (lead 03.11.)
    if not prof or not (chosen or prof.get("name")):
        return
    back = userprofile.back_image(chosen, 84) if chosen else None
    bw = 84 * userprofile.GW / userprofile.GH
    x_name = w - 64
    if back is not None and not back.isNull():
        p.drawImage(QRectF(w - 64 - bw, 46, bw, 84), back)
        x_name = w - 82 - bw
    p.setPen(QtGui.QColor(INK))
    p.setFont(_font(28))
    p.drawText(QRectF(x_name - 360, 56, 360, 38), Qt.AlignRight | Qt.AlignVCenter, prof.get("name") or "")
    p.setPen(QtGui.QColor(MUTED))
    p.setFont(_font(19, bold=False, display=False))
    p.drawText(QRectF(x_name - 360, 94, 360, 28), Qt.AlignRight | Qt.AlignVCenter, tr("plays"))


def _sub(it):
    parts = [it.get("format") or ""]
    if it.get("bracket"):
        parts.append(tr(f"Bracket {it['bracket']} (estimated)"))
    return "  ·  ".join(x for x in parts if x)


def _single(it, art_for, prof):
    img = QtGui.QImage(W, H, QtGui.QImage.Format_ARGB32_Premultiplied)
    p = QtGui.QPainter(img)
    p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform
                     | QtGui.QPainter.TextAntialiasing)
    _background(p, W, H, it.get("identity") or "")
    # header
    p.setPen(QtGui.QColor(INK))
    p.setFont(_font(54))
    p.drawText(QRectF(64, 46, W - 560, 72), Qt.AlignLeft | Qt.AlignVCenter,
               QtGui.QFontMetrics(p.font()).elidedText(it.get("name") or "", Qt.ElideRight, W - 560))
    p.setPen(QtGui.QColor(MUTED))
    p.setFont(_font(25, bold=False, display=False))
    p.drawText(QRectF(66, 116, W - 560, 38), Qt.AlignLeft | Qt.AlignVCenter, _sub(it))
    _profile(p, W, prof)
    # left: key figures
    kpis = [(tr("Cards"), f"{it.get('count', 0)}" + (f" / {it['size']}" if it.get("size") else "")),
            (tr("Value"), eur(it.get("price") or 0)),
            (tr("Ø mana value"), f"{it.get('avg_mv') or 0:.2f}".replace(".", ","))]
    if it.get("owned_pct") is not None:
        kpis.append((tr("I own"), f"{it['owned_pct']} %"))
    y = 196
    for label, value in kpis:
        _label(p, 66, y, 400, label)
        p.setPen(QtGui.QColor(INK))
        p.setFont(_font(46))
        p.drawText(QRectF(64, y + 24, 420, 58), Qt.AlignLeft | Qt.AlignVCenter, value)
        y += 92
    _label(p, 66, y + 6, 400, tr("Colors"))
    _pips(p, 66, y + 38, it.get("identity") or "")
    if it.get("built") is not None:
        _chip(p, 66, H - 118, tr("BUILT") if it["built"] else tr("NOT BUILT"),
              "#e6e6e6" if it["built"] else "#8e8e8e")
    # middle: cover card(s)
    covers = it.get("covers") or []
    ch = 640
    cw = ch * 63 / 88
    cx = 640
    if len(covers) >= 2:  # partner: second card offset behind it – lower, so its artist/© line stays visible (Scryfall)
        back = QRectF(cx + 70, 250, cw * 0.9, ch * 0.9)
        _card(p, back, art_for(covers[1]), covers[1].get("name"))
        _card(p, QRectF(cx - 40, 190, cw * 0.9, ch * 0.9), art_for(covers[0]), covers[0].get("name"),
              MANA[(it.get("identity") or "C")[0]])
        right_x = back.right() + 60
    elif covers:
        r = QRectF(cx - 40, 196, cw, ch)
        _card(p, r, art_for(covers[0]), covers[0].get("name"), MANA[(it.get("identity") or "C")[0]])
        right_x = r.right() + 70
    else:
        right_x = cx + cw + 30
    # right: mana curve, roles, combos, Game Changers
    x, w = right_x, W - right_x - 64
    y = 196
    _label(p, x, y, w, tr("Mana curve"))
    curve = (it.get("curve") or [0] * 8)[:8]
    top = max(curve) or 1
    bw = (w - 7 * 8) / 8
    for i, n in enumerate(curve):
        bh = 96 * n / top
        bx = x + i * (bw + 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor("#d8d8d8" if n else "#2a2a2a"))
        p.drawRoundedRect(QRectF(bx, y + 36 + 96 - max(bh, 3), bw, max(bh, 3)), 3, 3)
        p.setPen(QtGui.QColor(DIM))
        p.setFont(_font(15, bold=False, display=False))
        p.drawText(QRectF(bx, y + 136, bw, 20), Qt.AlignCenter, "7+" if i == 7 else str(i))
    y += 182
    _label(p, x, y, w, tr("Roles"))
    roles = it.get("roles") or {}
    shown = [("Ramp", decks.role_label("Ramp")), ("Kartenziehen", tr("Card draw")), ("Removal", decks.role_label("Removal")),
             ("Board Wipes", tr("Board wipes"))]
    top = max([roles.get(k, 0) for k, _ in shown] + [10])
    y += 34
    for key, label in shown:
        n = roles.get(key, 0)
        p.setPen(QtGui.QColor("#bdbdbd"))
        p.setFont(_font(18, bold=False, display=False))
        p.drawText(QRectF(x, y, 150, 24), Qt.AlignLeft | Qt.AlignVCenter, label)
        bar = QRectF(x + 150, y + 7, w - 200, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor("#2a2a2a"))
        p.drawRoundedRect(bar, 5, 5)
        p.setBrush(QtGui.QColor("#d8d8d8"))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * min(1.0, n / top), bar.height()), 5, 5)
        p.setPen(QtGui.QColor(INK))
        p.setFont(_font(18))
        p.drawText(QRectF(x + w - 40, y, 40, 24), Qt.AlignRight | Qt.AlignVCenter, str(n))
        y += 34
    y += 18
    _label(p, x, y, w, tr("Combos"))
    p.setPen(QtGui.QColor(INK))
    p.setFont(_font(40))
    p.drawText(QRectF(x, y + 24, w, 52), Qt.AlignLeft | Qt.AlignVCenter, str(it.get("combos") or 0))
    gcs = it.get("game_changers") or []
    if gcs:
        y += 92
        _label(p, x, y, w, tr("Game Changers"))
        y += 34
        cx2 = x
        for name in gcs[:4]:
            short = QtGui.QFontMetrics(_font(16)).elidedText(name, Qt.ElideRight, int(w - 40))
            cw2 = _chip(p, cx2, y, short, "#d0d0d0", 16)
            cx2 += cw2 + 8
            if cx2 > x + w - 120:
                cx2, y = x, y + 46
        if len(gcs) > 4:
            _chip(p, cx2, y, f"+{len(gcs) - 4}", "#8e8e8e", 16)
    watermark(p, QRectF(0, 0, W, H))
    p.end()
    return img


def _lineup(items, art_for, prof, title=None):
    n = len(items)
    cols = min(n, 5)
    rows = math.ceil(n / cols)
    ch = 430 if cols <= 4 else 380
    cw = ch * 63 / 88
    gap = 46
    w = max(1200, round(2 * 70 + cols * cw + (cols - 1) * gap))
    h = round(190 + rows * (ch + 140) + 40)
    img = QtGui.QImage(w, h, QtGui.QImage.Format_ARGB32_Premultiplied)
    p = QtGui.QPainter(img)
    p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform
                     | QtGui.QPainter.TextAntialiasing)
    ident = "".join(c for c in "WUBRG" if any(c in (it.get("identity") or "") for it in items))
    _background(p, w, h, ident)
    p.setPen(QtGui.QColor(INK))
    p.setFont(_font(50))
    p.drawText(QRectF(64, 46, w - 520, 70), Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine,
               p.fontMetrics().elidedText(title or tr("My lineup"), Qt.ElideRight, w - 520))
    p.setPen(QtGui.QColor(MUTED))
    p.setFont(_font(24, bold=False, display=False))
    p.drawText(QRectF(66, 112, w - 520, 36), Qt.AlignLeft | Qt.AlignVCenter, tr(f"{n} decks"))
    _profile(p, w, prof)
    row_w = cols * cw + (cols - 1) * gap
    for i, it in enumerate(items):
        col, row = i % cols, i // cols
        in_row = min(cols, n - row * cols)  # last row centered
        x0 = (w - (in_row * cw + (in_row - 1) * gap)) / 2 if in_row < cols else (w - row_w) / 2
        r = QRectF(x0 + col * (cw + gap), 190 + row * (ch + 140), cw, ch)
        covers = it.get("covers") or []
        partner = len(covers) >= 2
        if partner:  # second card down-right, so its artist/© line is not covered (Scryfall image rules)
            _card(p, r.adjusted(26, 22, 26, 22), art_for(covers[1]), covers[1].get("name"))
        _card(p, r, art_for(covers[0]) if covers else None, covers[0].get("name") if covers else it.get("name"))
        dy = 24 if partner else 0   # name/info move below the lower partner card
        p.setPen(QtGui.QColor(INK))
        p.setFont(_font(24))
        p.drawText(QRectF(r.left() - 10, r.bottom() + 20 + dy, r.width() + 20, 32), Qt.AlignCenter,
                   QtGui.QFontMetrics(p.font()).elidedText(it.get("name") or "", Qt.ElideRight, int(r.width() + 20)))
        p.setPen(QtGui.QColor(MUTED))
        p.setFont(_font(18, bold=False, display=False))
        p.drawText(QRectF(r.left() - 10, r.bottom() + 54 + dy, r.width() + 20, 26), Qt.AlignCenter, _sub(it))
        pw = len(it.get("identity") or "C") * 28 - 6
        _pips(p, r.center().x() - pw / 2, r.bottom() + 88 + dy, it.get("identity") or "", 22)
    watermark(p, QRectF(0, 0, w, h))
    p.end()
    return img


def render(items, art_for, profile=None, title=None):
    """items: per deck {"name", "format", "bracket", "covers" [rows], "identity", "curve", "roles", "combos",
    "game_changers", "count", "size", "price", "avg_mv", "owned_pct", "built"}; art_for(row) -> QPixmap|None.
    -> QImage"""
    if not items:
        return None
    title = (title or "").strip() or None   # custom heading (one deck: instead of the deck name)
    if len(items) == 1:
        return _single(dict(items[0], name=title) if title else items[0], art_for, profile)
    return _lineup(items, art_for, profile, title)
