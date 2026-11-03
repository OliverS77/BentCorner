def offer_image(me, friend, get_rows, give_rows, tk=None):
    """me/friend: (Name, Kartenrückseite). Zeilen: [{"name", "set", "number", "count", "price", "lang", "foil"}].
    Hochkant wie ein Kassenbon – auf dem Handy liest man es durch Reinzoomen. tk: Ticket (ticket.new) – dann trägt der
    Bon unten Abriss und Pixel-Code, den Bent°Corner wieder einlesen kann (Tausch → Importieren).
    -> QImage (2× für scharfe Darstellung)."""
    import json
    import ticket
    S = 2
    W = ticket.RECEIPT.W
    L, R = 40, W - 40          # Textränder
    SHOW = 30                  # so viele Karten je Seite stehen lesbar auf dem Bon (der Code trägt alle)
    code = ticket.bits(tk) if tk else None
    stub = (ticket.band_height(code[0]) + 96) if code else 40   # Abriss: Ticketnummer + Pixel-Code
    ROW = 50

    def side_h(rows):
        n = min(len(rows), SHOW)
        return 40 + max(1, n) * ROW + (26 if len(rows) > SHOW else 0) + 50
    money = int(tk.get("m") or 0) / 100 if tk else 0.0
    H = 262 + side_h(get_rows) + side_h(give_rows) + (40 if abs(money) >= 0.01 else 0) + 96 + stub
    img = QtGui.QImage(W * S, H * S, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(S)
    img.fill(QtGui.QColor("#0a0a0a"))
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.TextAntialiasing)
    ink, muted, line = QtGui.QColor("#ededed"), QtGui.QColor("#8e8e8e"), QtGui.QColor("#2e2e2e")
    paper = QtGui.QColor("#151515")

    def font(px, bold=False, display=False):
        f = look.display_font(px) if display else look.text_font(px)
        f.setBold(bold)
        return f

    def dashed(y):
        pen = QtGui.QPen(QtGui.QColor("#3a3a3a"), 2)
        pen.setDashPattern([3, 4])
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(L, y), QtCore.QPointF(R, y))

    def text(rect, flags, t, px, color=ink, bold=False, display=False):
        p.setFont(font(px, bold, display))
        p.setPen(color)
        p.drawText(rect, flags, t)
    cut = H - stub
    # Papier: oben und unten gezackt (abgerissener Bon)
    tooth = 12
    shape = QtGui.QPainterPath()
    shape.moveTo(8, tooth)
    x = 8.0
    while x < W - 8:
        shape.lineTo(min(W - 8, x + tooth / 2), 0)
        shape.lineTo(min(W - 8, x + tooth), tooth)
        x += tooth
    shape.lineTo(W - 8, H - tooth)
    x = W - 8.0
    while x > 8:
        shape.lineTo(max(8, x - tooth / 2), H)
        shape.lineTo(max(8, x - tooth), H - tooth)
        x -= tooth
    shape.closeSubpath()
    p.fillPath(shape, paper)
    # Kopf
    text(QRectF(L, 34, R - L, 34), Qt.AlignHCenter | Qt.AlignVCenter, "BENT°CORNER", 30, ink, display=True)
    kind = tr("TAUSCHANGEBOT")
    if tk:
        kind = tr("ABSCHLUSS") if ticket.kind(tk) == "f" else (
            tr("TAUSCHTICKET") if int(tk.get("n") or 1) == 1 else tr(f"GEGENANGEBOT {int(tk.get('n') or 1)}"))
    text(QRectF(L, 72, R - L, 20), Qt.AlignHCenter, kind + "  ·  " + time.strftime("%d.%m.%Y %H:%M"), 13, muted, True)
    if tk:
        text(QRectF(L, 94, R - L, 20), Qt.AlignHCenter, tr("TAUSCH") + " " + str(tk.get("x") or tk.get("id") or "").upper(),
             13, muted)
    dashed(126)
    for i, (name, back) in enumerate((me, friend)):
        pm = userprofile.back_pixmap(back, 52)
        p.drawPixmap(QtCore.QPoint(int(L if i == 0 else R - 40), 142), pm)
    text(QRectF(L + 56, 140, R - L - 112, 64), Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap,
         f"{me[0]}  ⇄  {friend[0]}", 26, ink, display=True)
    dashed(222)
    y = 238
    sums = []
    for k, (title, rows) in enumerate(((tr(f"{me[0]} bekommt"), get_rows), (tr(f"{friend[0]} bekommt"), give_rows))):
        text(QRectF(L, y, R - L, 22), Qt.AlignLeft, f"0{k + 1} — " + title.upper(), 13, muted, True)
        y += 40
        total = 0.0
        for r in rows:
            total += (r.get("price") or 0) * int(r.get("count") or 1)
        for r in rows[:SHOW]:
            n = int(r.get("count") or 1)
            p.setFont(font(17, True))
            nm = QtGui.QFontMetricsF(p.font()).elidedText(f"{n}×  {r['name']}", Qt.ElideRight, R - L - 120)
            text(QRectF(L, y, R - L - 110, 24), Qt.AlignLeft | Qt.AlignVCenter, nm, 17, ink, True)
            text(QRectF(L, y, R - L, 24), Qt.AlignRight | Qt.AlignVCenter,
                 eur(None if r.get("price") is None else r["price"] * n), 17)
            extra = f"{r['set']} #{r['number']}" + (" · Foil" if r.get("foil") else "") +                 (f" · {LANG_SHORT.get(r.get('lang'), '')}" if (r.get("lang") or "en") != "en" else "")
            text(QRectF(L + 34, y + 24, R - L - 34, 18), Qt.AlignLeft | Qt.AlignVCenter, extra, 14, muted)
            y += ROW
        if not rows:
            text(QRectF(L, y, R - L, 24), Qt.AlignLeft, tr("nichts"), 16, muted)
            y += ROW
        if len(rows) > SHOW:
            text(QRectF(L, y, R - L, 22), Qt.AlignLeft, tr(f"… und {len(rows) - SHOW} weitere (im Code enthalten)"), 14, muted)
            y += 26
        p.setPen(QtGui.QPen(line, 1))
        p.drawLine(QtCore.QPointF(L, y + 6), QtCore.QPointF(R, y + 6))
        text(QRectF(L, y + 12, R - L, 28), Qt.AlignLeft | Qt.AlignVCenter, tr("SUMME"), 13, muted, True)
        text(QRectF(L, y + 12, R - L, 28), Qt.AlignRight | Qt.AlignVCenter, eur(total), 22, ink, display=True)
        y += 50
        sums.append(total)
    if abs(money) >= 0.01:   # Geld dazu (von f an o, negativ umgekehrt)
        payer, payee, m = (tk.get("f") or ["", "?"])[1], (tk.get("o") or ["", "?"])[1], money
        if m < 0:
            payer, payee, m = payee, payer, -m
        text(QRectF(L, y, R - L, 30), Qt.AlignLeft | Qt.AlignVCenter, tr(f"+ {eur(m)} von {payer} an {payee}"), 17,
             ink, True)
        y += 40
    dashed(y + 10)
    # Bilanz aus Sicht von me: bekommt − gibt − was me drauflegt (m > 0: f zahlt an o)
    me_pays = money if tk and (tk.get("f") or ["", ""])[1] == me[0] else -money
    diff = sums[0] - sums[1] - me_pays
    text(QRectF(L, y + 22, R - L, 30), Qt.AlignLeft | Qt.AlignVCenter, tr(f"BILANZ FÜR {me[0]}").upper(), 13, muted,
         True)
    text(QRectF(L, y + 22, R - L, 30), Qt.AlignRight | Qt.AlignVCenter,
         ("+" if diff > 0.005 else "") + eur(diff), 22, ink, display=True)
    text(QRectF(L, y + 58, R - L, 18), Qt.AlignHCenter, tr("Preise: Cardmarket-Trend, ohne Gewähr"), 12, muted)
    if tk:
        # Abriss: Ticketnummer, Hinweis, darunter der Pixel-Code (helle Blöcke auf dem Papier)
        for x in (8, W - 8):   # eingestanzte Halbkreise an der Abrisslinie
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor("#0a0a0a"))
            p.drawEllipse(QtCore.QPointF(x, cut), 14, 14)
        dashed(cut)
        text(QRectF(L, cut + 20, R - L, 22), Qt.AlignHCenter, tr("TICKET") + "  Nº " + ticket.label(tk), 15, ink, True)
        text(QRectF(L, cut + 46, R - L, 20), Qt.AlignHCenter, tr("Einlösen: Bent°Corner → Tausch → Importieren"), 13,
             muted)
        if code:
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor("#c9c9c9"))
            for i, v in enumerate(code[1]):
                if v:
                    bx, by, m = ticket.module_rect(i, H)
                    p.drawRect(QRectF(bx + 0.5, by + 0.5, m - 1, m - 1))
    p.end()
    if tk:
        img.setText(ticket.TEXT_KEY, json.dumps(tk, ensure_ascii=False, separators=(",", ":")))
    return img