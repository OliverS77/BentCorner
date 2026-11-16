"""Building blocks of the "Trade" page (no widgets – drawn in Qt Quick, qtrade.py):

Browser       one column in the "Trade" tab: cards with search, filter chips, grid/list and checkmarks for
              selecting/deselecting. Rows: {"key", "name", "set", "number", "lang", "foil", "count", "price",
              "db" (card database row or None), "tags" ([text]), "checked" (True/False/None)}.
offer_image   trade offer as an image (PNG / clipboard).
"""
import time

from PySide6 import QtCore, QtGui
from PySide6.QtCore import QRectF, Qt

from ui import look
from system import userprofile
from system.i18n import tr

LANG_SHORT = {"en": "EN", "de": "DE", "fr": "FR", "it": "IT", "es": "ES", "pt": "PT", "ja": "JP", "ko": "KR",
              "ru": "RU", "zhs": "CS", "zht": "CT", "ph": "PH", "th": "TH",
              "id": "ID"}


def eur(v):
    return "–" if v is None else f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def card_eur(v, est=False):
    """A CARD value in the display currency (lead 14.11.: no fixed "€" for card values), „≈" when converted from
    dollars (legal 14.11.2026). eur() stays for money between friends – a typed amount is euros, never converted."""
    from cards import currency
    return "–" if v is None else currency.fmt(v, est)


def value(v, est=False):
    """A CARD value (market price) – "" in Orbit's Core (legal 06.11.); eur() stays for money between friends."""
    from system import orbit
    return card_eur(v, est) if orbit.prices_shown() else ""


def row_sid(r):
    """The print of a trade row (its card database row's id) – for the „≈" mark."""
    return ((r or {}).get("db") or {}).get("id") or (r or {}).get("sid")


def row_est(r):
    """Is a trade row's price converted from dollars? (a row may carry "est" itself – e.g. the offer picture; a row
    of another game carries "game": that game's card database is asked)"""
    if "est" in (r or {}):
        return bool(r["est"])
    from cards import currency
    return currency.estimated(row_sid(r), (r or {}).get("game"))


def rows_est(rows):
    """A sum of trade rows gets „≈" when one priced row is converted (legal 14.11.)."""
    return any(r.get("price") and row_est(r) for r in rows)


def rows_tip(rows):
    """The legal text for the „≈" of a sum of trade rows – "" without a converted price."""
    from cards import currency
    days = [currency.rate_day_of(row_sid(r), r.get("game")) or "" for r in rows if r.get("price") and row_est(r)]
    return currency.approx_tip(max(days) or None) if days else ""


PAY_NOTE = "Payment happens between you – Bent°Corner handles no money."


def money_text(t, my_id):
    """The amount in a ticket as the proposal of whoever made it – also in Orbit's Core (legal/lead 06.11.: a sum a
    friend entered is no market value; hiding it would hide part of the deal). No card values, no sums, no balance.
    -> "" without money."""
    from collection import ticket
    m = ticket.money_from_me(t, my_id) if t else 0.0   # + I pay, − I get
    if abs(m) < 0.01:
        return ""
    if ticket.kind(t) == "f":   # closing ticket: the deal is agreed – who pays whom, nobody "wants" (lead 06.11.)
        sd = ticket.side(t, my_id)
        from ui import textsafe
        other = textsafe.name(sd[2][1] if sd else "")   # a friend's name, shown as text only
        if m > 0:
            return tr(f"You pay {eur(m)} to {other}") if other else tr(f"You pay {eur(m)} to your friend")
        return tr(f"{other} pays you {eur(-m)}") if other else tr(f"Your friend pays you {eur(-m)}")
    mine = (t.get("f") or ["", ""])[0] == my_id         # who made this version: me or the friend
    if mine:
        other = (t.get("o") or ["", ""])[1] or "?"
        return tr(f"You add {eur(m)}") if m > 0 else tr(f"You want {eur(-m)} from {other}")
    name = (t.get("f") or ["", ""])[1] or "?"
    return tr(f"{name} adds {eur(-m)}") if m < 0 else tr(f"{name} wants {eur(m)} from you")


# ---------- Cards of one column ----------
class Browser(QtCore.QObject):
    """Cards with search, filter chips and a grid/list toggle. checkable: checkmarks for selecting/deselecting.
    rows = what is currently visible; info/empty = texts below. Signals: clicked(row), checks_changed(), changed()."""
    clicked = QtCore.Signal(object)
    checks_changed = QtCore.Signal()
    changed = QtCore.Signal()

    def __init__(self, settings, key, checkable=False, parent=None):
        super().__init__(parent)
        self.settings, self.key, self.checkable = settings, key, checkable
        self.all_rows, self.rows, self.filters, self.exclusive, self.active = [], [], [], [], set()
        self.search, self.info, self.empty, self.empty_text = "", "", "", ""
        self.info_tip = ""   # the legal text on the „≈" of the info line
        self.mode = settings.get(f"browse_{key}") if settings.get(f"browse_{key}") in ("grid", "list") else "grid"

    # --- Data ---
    def set_rows(self, rows, empty_text=""):
        self.all_rows = rows
        self.empty_text = empty_text
        self.refresh()

    def set_filters(self, filters, exclusive=()):
        """filters: [(key, label, test function(row))] – several on = all must match.
        exclusive: pairs of keys that cannot be on at the same time (turning one on turns the other off)."""
        self.filters, self.exclusive = filters, [set(x) for x in exclusive]
        self.active &= {k for k, _, _ in filters}
        self.changed.emit()

    def set_search(self, text):
        if text != self.search:
            self.search = text
            self.refresh()

    def _chip(self, key, on):
        if on:
            self.active.add(key)
            for group in self.exclusive:
                if key in group:
                    self.active -= group - {key}
        else:
            self.active.discard(key)
        self.refresh()
        self.checks_changed.emit()  # totals depend on what is visible

    def shown_rows(self):
        words = self.search.lower().split()
        tests = [fn for k, _, fn in self.filters if k in self.active]
        out = []
        for r in self.all_rows:
            hay = f"{r['name']} {r['set']} {r['number']}".lower()
            if words and not all(w in hay for w in words):
                continue
            if not all(fn(r) for fn in tests):
                continue
            out.append(r)
        return out

    def checked_rows(self):
        """Checked cards that the filter currently shows (e.g. without other versions under "📌 Version")."""
        return [r for r in self.shown_rows() if r.get("checked")]

    def refresh(self):
        rows = self.rows = self.shown_rows()
        n = sum(int(r.get("count") or 1) for r in rows)
        val = sum((r.get("price") or 0) * int(r.get("count") or 1) for r in rows)
        if self.checkable:  # price of the checked cards, followed by all
            checked = [r for r in rows if r.get("checked")]
            chk = sum((r.get("price") or 0) * int(r.get("count") or 1) for r in checked)
            self.info = (tr(f"{n} cards · {card_eur(chk, rows_est(checked))}") + " "
                         + tr(f"(All: {card_eur(val, rows_est(rows))})"))
        else:
            self.info = tr(f"{n} cards · {card_eur(val, rows_est(rows))}")
        self.info_tip = rows_tip(rows)
        from system import orbit
        if not orbit.prices_shown():   # Orbit's Core: only the count
            self.info, self.info_tip = tr(f"{n} cards"), ""
        self.empty = "" if rows else (self.empty_text if not self.all_rows
                                      else tr("Nothing found – change the search or filters."))
        self.changed.emit()

    def set_mode(self, mode, save=True):
        self.mode = mode if mode in ("grid", "list") else "grid"
        if save:
            self.settings[f"browse_{self.key}"] = self.mode
        self.changed.emit()

    # --- Checkmarks ---
    def toggle(self, r):
        r["checked"] = not r.get("checked")
        self.refresh()
        self.checks_changed.emit()

    def check_all(self, on):
        for r in self.shown_rows():
            r["checked"] = on
        self.refresh()
        self.checks_changed.emit()


def same_cards(items, key, count, add):
    """Identical cards once with the summed count ("2× Bolt" instead of two lines) – first place kept, order unchanged.
    key(x) -> what makes two entries the same card, count(x) -> its count, add(x, n) -> a copy with count n."""
    out, at = [], {}
    for x in items:
        k = key(x)
        if k in at:
            i = at[k]
            out[i] = add(out[i], count(out[i]) + count(x))
        else:
            at[k] = len(out)
            out.append(x)
    return out


def same_rows(rows):
    """Image rows ({"name", "set", "number", "lang", "foil", "count", …}): identical cards in one row."""
    return same_cards(rows, lambda r: (r.get("name"), str(r.get("set")).upper(), str(r.get("number")),
                                       r.get("lang") or "en", bool(r.get("foil"))),
                      lambda r: int(r.get("count") or 1), lambda r, n: dict(r, count=n))


# ---------- Trade offer as an image (trade ticket) ----------
def offer_image(me, friend, get_rows, give_rows, tk=None, priced=True):
    """me/friend: (name, card back). Rows: [{"name", "set", "number", "count", "price", "lang", "foil"}].
    Portrait like a till receipt – on a phone you read it by zooming in. tk: ticket (ticket.new) – then the
    receipt carries a tear-off stub at the bottom with a pixel code that Bent°Corner can read back (Trade → Import).
    priced=False (Orbit's Core, legal 03.11.): only the cards and counts – no prices, no TOTAL, no balance; an amount
    the partners entered themselves is still printed (lead/legal 06.11.: it is part of the deal, not a value).
    -> QImage (2× for sharp rendering)."""
    import json
    from collection import ticket
    S = 2
    get_rows, give_rows = same_rows(get_rows), same_rows(give_rows)   # the same card twice: one line "2×"
    W = ticket.RECEIPT.W
    L, R = 40, W - 40          # text margins
    SHOW = 30                  # this many cards per side are printed legibly on the receipt (the code carries all)
    code = ticket.bits(tk) if tk else None
    stub = (ticket.band_height(code[0]) + 96) if code else 40   # stub: ticket number + pixel code
    ROW = 50

    def side_h(rows):
        n = min(len(rows), SHOW)
        return 40 + max(1, n) * ROW + (26 if len(rows) > SHOW else 0) + (50 if priced else 32)
    money = int(tk.get("m") or 0) / 100 if tk else 0.0
    H = 262 + side_h(get_rows) + side_h(give_rows) + (40 if abs(money) >= 0.01 else 0) + (96 if priced else 40) + stub
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
    # paper: jagged at top and bottom (torn-off receipt)
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
    # header
    from ui import brand
    text(QRectF(L, 34, R - L, 34), Qt.AlignHCenter | Qt.AlignVCenter, brand.WORD, 30, ink, display=True)
    kind = tr("TRADE OFFER")
    if tk:
        kind = tr("COMPLETION") if ticket.kind(tk) == "f" else (
            tr("TRADE TICKET") if int(tk.get("n") or 1) == 1 else tr(f"COUNTEROFFER {int(tk.get('n') or 1)}"))
    when = time.localtime(int(tk["t"]) if tk and tk.get("t") else None)   # the ticket's date, not when it is shown
    text(QRectF(L, 72, R - L, 20), Qt.AlignHCenter, kind + "  ·  " + time.strftime("%d.%m.%Y %H:%M", when), 13,
         muted, True)
    if tk:
        text(QRectF(L, 94, R - L, 20), Qt.AlignHCenter, tr("TRADE") + " " + str(tk.get("x") or tk.get("id") or "").upper(),
             13, muted)
    dashed(126)
    for i, (name, back) in enumerate((me, friend)):
        own = userprofile.shared_back({"back": back})   # never the default back on a shared picture (lead 03.11.)
        if own:                                           # none: the place stays empty, name and ⇄ stay centred
            p.drawPixmap(QtCore.QPoint(int(L if i == 0 else R - 40), 142), userprofile.back_pixmap(own, 52))
    text(QRectF(L + 56, 140, R - L - 112, 64), Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap,
         f"{me[0]}  ⇄  {friend[0]}", 26, ink, display=True)
    dashed(222)
    y = 238
    sums = []
    for k, (title, rows) in enumerate(((tr(f"{me[0]} gets"), get_rows), (tr(f"{friend[0]} gets"), give_rows))):
        text(QRectF(L, y, R - L, 22), Qt.AlignLeft, f"0{k + 1} — " + title.upper(), 13, muted, True)
        y += 40
        total = 0.0
        for r in rows:
            total += (r.get("price") or 0) * int(r.get("count") or 1)
        for r in rows[:SHOW]:
            n = int(r.get("count") or 1)
            p.setFont(font(17, True))
            nm = QtGui.QFontMetricsF(p.font()).elidedText(f"{n}×  {r['name']}", Qt.ElideRight,
                                                          R - L - (120 if priced else 0))
            text(QRectF(L, y, R - L - (110 if priced else 0), 24), Qt.AlignLeft | Qt.AlignVCenter, nm, 17, ink, True)
            if priced:
                text(QRectF(L, y, R - L, 24), Qt.AlignRight | Qt.AlignVCenter,
                     card_eur(None if r.get("price") is None else r["price"] * n, row_est(r)), 17)
            extra = f"{r['set']} #{r['number']}" + (" · Foil" if r.get("foil") else "") +                 (f" · {LANG_SHORT.get(r.get('lang'), '')}" if (r.get("lang") or "en") != "en" else "")
            text(QRectF(L + 34, y + 24, R - L - 34, 18), Qt.AlignLeft | Qt.AlignVCenter, extra, 14, muted)
            y += ROW
        if not rows:
            text(QRectF(L, y, R - L, 24), Qt.AlignLeft, tr("nothing"), 16, muted)
            y += ROW
        if len(rows) > SHOW:
            text(QRectF(L, y, R - L, 22), Qt.AlignLeft, tr(f"… and {len(rows) - SHOW} more (in the code)"), 14, muted)
            y += 26
        sums.append(total)
        if not priced:   # Orbit's Core: no TOTAL, only some air before the next side
            y += 32
            continue
        p.setPen(QtGui.QPen(line, 1))
        p.drawLine(QtCore.QPointF(L, y + 6), QtCore.QPointF(R, y + 6))
        text(QRectF(L, y + 12, R - L, 28), Qt.AlignLeft | Qt.AlignVCenter, tr("TOTAL"), 13, muted, True)
        text(QRectF(L, y + 12, R - L, 28), Qt.AlignRight | Qt.AlignVCenter, card_eur(total, rows_est(rows)), 22, ink,
             display=True)
        y += 50
    if abs(money) >= 0.01:   # money on top (from f to o, reversed if negative)
        # a side without a name is me (my profile has none): the same name as in the header
        payer, payee, m = (tk.get("f") or ["", ""])[1] or me[0], (tk.get("o") or ["", ""])[1] or me[0], money
        if m < 0:
            payer, payee, m = payee, payer, -m
        text(QRectF(L, y, R - L, 30), Qt.AlignLeft | Qt.AlignVCenter, tr(f"+ {eur(m)} from {payer} to {payee}"), 17,
             ink, True)
        y += 40
    dashed(y + 10)
    if priced:   # Orbit's Core: no balance, no prices note
        # balance from me's point of view: gets − gives − what me adds on top (m > 0: f pays o)
        me_pays = money if tk and (tk.get("f") or ["", ""])[1] == me[0] else -money
        diff = sums[0] - sums[1] - me_pays
        text(QRectF(L, y + 22, R - L, 30), Qt.AlignLeft | Qt.AlignVCenter, tr(f"BALANCE FOR {me[0]}").upper(), 13, muted,
             True)
        text(QRectF(L, y + 22, R - L, 30), Qt.AlignRight | Qt.AlignVCenter,
             ("+" if diff > 0.005 else "") + card_eur(diff, rows_est(get_rows) or rows_est(give_rows)), 22, ink,
             display=True)
        text(QRectF(L, y + 58, R - L, 18), Qt.AlignHCenter, tr("Prices: Cardmarket trend, no guarantee"), 12, muted)
    if tk:
        # stub: ticket number, hint, below it the pixel code (light blocks on the paper)
        for x in (8, W - 8):   # punched semicircles on the tear-off line
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor("#0a0a0a"))
            p.drawEllipse(QtCore.QPointF(x, cut), 14, 14)
        dashed(cut)
        text(QRectF(L, cut + 20, R - L, 22), Qt.AlignHCenter, tr("TICKET") + "  Nº " + ticket.label(tk), 15, ink, True)
        text(QRectF(L, cut + 46, R - L, 20), Qt.AlignHCenter, tr("Redeem: import in Bent°Corner"), 13,
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
