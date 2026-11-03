def offer_image(me, friend, get_rows, give_rows, tk=None):
    """me/friend: (Name, Kartenrückseite). Zeilen: [{"name", "set", "number", "count", "price", "lang", "foil"}].
    tk: Ticket (ticket.new) – dann wird das Bild ein Tauschticket mit Abriss und Pixel-Code, das Bent°Corner wieder
    einlesen kann (Tausch → Importieren). -> QImage (2× für scharfe Darstellung)."""
    import json
    import ticket
    S = 2
    W = ticket.W
    rows_n = max(len(get_rows), len(give_rows), 1)
    code = ticket.bits(tk) if tk else None
    stub = (ticket.band_height(code[0]) + 70) if code else 0   # Abriss: Ticketnummer + Pixel-Code
    H = 250 + 34 * min(rows_n, 40) + 150 + stub
    img = QtGui.QImage(W * S, H * S, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(S)
    img.fill(QtGui.QColor("#0a0a0a"))
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.TextAntialiasing)
    ink, muted, line = QtGui.QColor("#ededed"), QtGui.QColor("#8e8e8e"), QtGui.QColor("#2a2a2a")
    body = QtGui.QColor("#141414")

    def font(px, bold=False, display=False):
        f = look.display_font(px) if display else look.text_font(px)
        f.setBold(bold)
        return f
    cut = H - stub   # Abriss-Linie
    if tk:
        # Ticket: Fläche mit runden Ecken, an der Abriss-Linie links/rechts eingestanzt
        shape = QtGui.QPainterPath()
        shape.addRoundedRect(QRectF(16, 16, W - 32, H - 32), 22, 22)
        for x in (16, W - 16):
            hole = QtGui.QPainterPath()
            hole.addEllipse(QtCore.QPointF(x, cut), 18, 18)
            shape = shape.subtracted(hole)
        p.fillPath(shape, body)
        p.setPen(QtGui.QPen(QtGui.QColor("#262626"), 1))
        p.drawPath(shape)
        pen = QtGui.QPen(QtGui.QColor("#3a3a3a"), 2)
        pen.setDashPattern([3, 4])
        p.setPen(pen)
        p.drawLine(QtCore.QPointF(48, cut), QtCore.QPointF(W - 48, cut))
    # Kopf: Kennzeile, Titel, beide Kartenrückseiten
    p.setFont(font(13, True))
    p.setPen(muted)
    head = "BENT°CORNER  ·  " + (tr("TAUSCHTICKET") if tk else tr("TAUSCHANGEBOT")) + "  ·  " + time.strftime("%d.%m.%Y")
    p.drawText(QRectF(48, 34, 700, 20), Qt.AlignLeft, head)
    p.setFont(font(44, display=True))
    p.setPen(ink)
    p.drawText(QRectF(48, 60, W - 96, 60), Qt.AlignLeft | Qt.AlignVCenter, f"{me[0]}  ⇄  {friend[0]}")
    for i, (name, back) in enumerate((me, friend)):
        pm = userprofile.back_pixmap(back, 64)
        p.drawPixmap(QtCore.QPoint(W - 48 - 50 - (1 - i) * 58, 52), pm)  # gleiche Reihenfolge wie im Titel
    p.setPen(QtGui.QPen(line, 1))
    p.drawLine(QtCore.QPointF(48, 140), QtCore.QPointF(W - 48, 140))
    col_w = (W - 96 - 40) / 2
    sums = []
    for k, (title, rows) in enumerate(((tr(f"{me[0]} bekommt"), get_rows), (tr(f"{friend[0]} bekommt"), give_rows))):
        x = 48 + k * (col_w + 40)
        p.setFont(font(13, True))
        p.setPen(muted)
        p.drawText(QRectF(x, 156, col_w, 22), Qt.AlignLeft, f"0{k + 1} — " + title.upper())
        y = 192
        total = 0.0
        for r in rows[:40]:
            n = int(r.get("count") or 1)
            total += (r.get("price") or 0) * n
            p.setFont(font(16, True))
            p.setPen(ink)
            name = QtGui.QFontMetricsF(p.font()).elidedText(f"{n}×  {r['name']}", Qt.ElideRight, col_w - 120)
            p.drawText(QRectF(x, y, col_w - 110, 24), Qt.AlignLeft | Qt.AlignVCenter, name)
            p.setFont(font(14))
            p.setPen(muted)
            extra = f"{r['set']} #{r['number']}" + (" · Foil" if r.get("foil") else "") + \
                (f" · {LANG_SHORT.get(r.get('lang'), '')}" if (r.get("lang") or "en") != "en" else "")
            p.drawText(QRectF(x + 30, y + 20, col_w - 140, 16), Qt.AlignLeft | Qt.AlignVCenter, extra)
            p.setFont(font(16))
            p.setPen(ink)
            p.drawText(QRectF(x, y, col_w, 24), Qt.AlignRight | Qt.AlignVCenter,
                       eur(None if r.get("price") is None else r["price"] * n))
            y += 34 + 4
            if y > cut - 160:
                break
        if len(rows) > 40:
            p.setPen(muted)
            p.drawText(QRectF(x, y, col_w, 20), Qt.AlignLeft, tr(f"… und {len(rows) - 40} weitere"))
        if not rows:
            p.setFont(font(15))
            p.setPen(muted)
            p.drawText(QRectF(x, y, col_w, 24), Qt.AlignLeft, tr("nichts"))
        sums.append(total)
    p.setPen(QtGui.QPen(line, 1))
    p.drawLine(QtCore.QPointF(48, cut - 110), QtCore.QPointF(W - 48, cut - 110))
    for k, total in enumerate(sums):
        x = 48 + k * (col_w + 40)
        p.setFont(font(13, True))
        p.setPen(muted)
        p.drawText(QRectF(x, cut - 96, col_w, 20), Qt.AlignLeft, tr("WERT"))
        p.setFont(font(34, display=True))
        p.setPen(ink)
        p.drawText(QRectF(x, cut - 76, col_w, 44), Qt.AlignLeft | Qt.AlignVCenter, eur(total))
    p.setFont(font(12))
    p.setPen(muted)
    p.drawText(QRectF(48, cut - 30, W - 96, 18), Qt.AlignRight, tr("Preise: Cardmarket-Trend, ohne Gewähr"))
    if tk and int(tk.get("m") or 0):   # Geld dazu (von f an o, negativ umgekehrt)
        m = int(tk["m"]) / 100
        payer, payee = ((tk.get("f") or ["", "?"])[1], (tk.get("o") or ["", "?"])[1])
        if m < 0:
            payer, payee, m = payee, payer, -m
        p.setFont(font(15, True))
        p.setPen(ink)
        p.drawText(QRectF(48, cut - 34, W / 2, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   tr(f"+ {eur(m)} von {payer} an {payee}"))
    if tk:   # Art des Tickets und Tausch-ID (gleich über alle Versionen)
        import ticket as _tk
        kind = tr("ABSCHLUSS") if _tk.kind(tk) == "f" else (tr("ANGEBOT") if int(tk.get("n") or 1) == 1
                                                            else tr(f"GEGENANGEBOT {int(tk.get('n') or 1)}"))
        p.setFont(font(13, True))
        p.setPen(muted)
        p.drawText(QRectF(W - 48 - 420, 34, 420, 20), Qt.AlignRight, kind + "  ·  " + tr("TAUSCH") + " "
                   + str(tk.get("x") or tk.get("id") or "").upper())
    if tk:
        # Abriss: Ticketnummer, Hinweis, darunter der Pixel-Code (helle Blöcke auf der Ticketfläche)
        p.setFont(font(13, True))
        p.setPen(muted)
        p.drawText(QRectF(48, cut + 18, 400, 20), Qt.AlignLeft, tr("TICKET") + "  Nº " + ticket.label(tk))
        p.setFont(font(12))
        p.drawText(QRectF(360, cut + 18, W - 408, 20), Qt.AlignRight,
                   tr("Einlösen: Bent°Corner → Tausch → Importieren"))
        if code:
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor("#c9c9c9"))
            for i, v in enumerate(code[1]):
                if v:
                    x, y, m = ticket.module_rect(i, H)
                    p.drawRect(QRectF(x + 0.5, y + 0.5, m - 1, m - 1))
    p.end()
    if tk:
        img.setText(ticket.TEXT_KEY, json.dumps(tk, ensure_ascii=False, separators=(",", ":")))
    return img