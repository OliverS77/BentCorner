"""Overlay painted over the camera image of the scan page – only the moments the tiles (scantiles.py) don't show: the
Biggest-Hit celebration and the big preview of a card under the mouse (Overlay.paint). The effects (sparkles,
fireworks, hearts, orbit) are in overlay_fx.py.
Moved from app.py (re-exported there)."""
import collections
import json
import logging
import math
import re
import threading

from PySide6 import QtGui
from PySide6.QtCore import QPointF, QRectF, Qt

import games
from cards import carddb, imgcache, library
from scanner.common import BASE
from scanner.core import CARD_ASPECT
from system.i18n import tr
from ui import scanlook
from ui.overlay_fx import OverlayFx
from ui.scanlook import TIER_COLOR, card_meta, ease_in_out, ease_out, eur, finish_label, font, shown_name, tier

log = logging.getLogger("booster")
CARD_FILL = (24, 24, 24)   # card surface behind the placeholders (missing / loading) – grey like the "grau" look


class Overlay(OverlayFx):
    """Recreation of overlay.html with QPainter. Coordinates on a 1920-wide grid.
    With the mouse in the stream window, buttons appear (hover); self.buttons holds them for clicking."""
    MARGIN = 48
    # Idle animations of the Biggest Hit: (name, duration in s)
    IDLE = [("Tanzen", 2.4), ("Sternenfunkeln", 2.8), ("Kippen", 2.6), ("Lichtreflex", 0.9),
            ("Feuerwerk", 2.8), ("Herzchen", 3.2), ("Orbit-Lichter", 2.8), ("Wackelpudding", 1.5)]
    IDLE_DUR = dict(IDLE)
    IDLE_EVERY = 14.0

    def __init__(self, settings):
        self.settings = settings
        self.card, self.shown_key = None, None
        self.show_t, self.hide_at, self.fade_t = 0.0, None, None
        self.snap = None
        self.pm_cache = collections.OrderedDict()
        self.hover = None        # mouse position in the window (None = mouse not in the stream window)
        self.moved = 0.0         # when the mouse last moved (briefly show the gear at top right)
        self.suppress = False    # a window (search, info …) is open: no hover preview
        self.buttons = []        # (rect in the window, action, card index)
        self.name_regions = []   # (rect in the window, card) for the big preview
        self.panel_open = False  # card search sits where the pack list is
        self.panel_hover = None  # card the mouse is over in the card search
        self.panel_rect = None   # card search/edit open: its place (window pixels) – the big preview moves aside
        self.list_tile = None    # the scan tile with its list: the preview of a card of the list stands beside it
        self.free_band = None    # free strip between the status tile above and the dock below (window pixels)
        self.hover_list = False  # panel_hover comes from that list (not from the card search)
        self._canvas, self._s = QRectF(), 1.0
        self.slide = 0.0         # Studio open/closed (0..1): each side slides out to its edge
        self.details = {}        # Scryfall extra info per card (None = loading)
        self.flip = None         # page-turn animation {'t0', 'dir': 'open'/'close', 'pix': image of the search}
        self.big_hit, self.big_hit_t = None, 0.0
        self.manual = None       # (animation number, start time) after clicking the Biggest Hit
        self.last_kind = -1
        self.focus = None        # big preview: {"card", "t", "mode"}
        self.leaving = []        # previews fading out
        self.hit_mode = "session"  # Biggest Hit of the session or of all time ("all")
        self.all_time_hit = None
        self.paused = False      # recognition paused (pause/play on the current card)
        self.show_back = False   # big preview shows the back (double-faced cards)
        self.back_t = -9.0       # time of the last flip (flip animation)
        self.card_by_id = {}     # all loaded cards (for the second face)

    def busy(self, now):
        """Is a fast transition running (fly-in, page turn, preview, hit animation)? Then draw at the full
        frame rate – otherwise 30 frames/s are enough for the calm movements."""
        if self.hover is not None or self.focus or self.leaving or self.flip or self.fade_t is not None:
            return True
        if self.panel_hover is not None:   # the mouse just went onto a card (tiles, search): show it right away
            return True
        if now - self.back_t < 0.6:
            return True
        return False

    def has_fx(self, now):
        """Is there anything for the top layer (the big preview)? Nothing: that layer isn't drawn."""
        return bool(self.panel_hover is not None or self.focus or self.leaving)

    # State
    def update(self, snap, now):
        self.snap = snap
        self._refresh_hit(now)
        cur = snap["current"]
        if cur:
            self.hide_at = None
            key = f"{cur['id']}|{cur['foil']}|{cur['price']}"
            if key != self.shown_key:
                self.shown_key, self.card, self.show_t, self.fade_t = key, cur, now, None
            elif self.fade_t is None:
                self.card = cur  # e.g. image of the language version loaded later
        elif self.shown_key and self.hide_at is None and not self.settings.get("hold_forever"):
            self.hide_at = now + self.settings["hold"]  # let the last card stay a little longer
        if self.hide_at is not None and now >= self.hide_at:
            self.hide_at, self.shown_key, self.fade_t = None, None, now
        if self.fade_t is not None and now - self.fade_t > 0.3:
            self.card, self.fade_t = None, None

    def _refresh_hit(self, now):
        """Biggest Hit of the session – or of all time, when switched (click on the heading)."""
        hit = self.snap["stats"]["biggest_hit"] if self.snap else None
        if self.hit_mode == "all" and self.all_time_hit and \
                (hit is None or (self.all_time_hit["price"] or 0) > (hit["price"] or 0)):
            hit = self.all_time_hit
        key = hit and (hit["id"], hit.get("added"), hit["price"], hit["img"])
        if key != (self.big_hit and (self.big_hit["id"], self.big_hit.get("added"), self.big_hit["price"],
                                     self.big_hit["img"])):
            self.big_hit, self.big_hit_t = hit, now

    def other_face(self, card):
        """The other face of a double-faced card (or None)."""
        if not card:
            return None
        sid, _, face = card["id"].rpartition("_")
        if not face.isdigit():
            return None
        other = "1" if face == "0" else "0"
        back = self.card_by_id.get(f"{sid}_{other}")
        img = card["img"].replace(f"_{face}.jpg", f"_{other}.jpg")
        if back:
            back = dict(back, foil=card.get("foil"), price=card.get("price"), added=card.get("added"),
                        lang=card.get("lang"))
            if card.get("lang", "en") != "en" and (BASE / img).exists():
                back["img"] = img  # back in the same language
            return back
        if img != card["img"] and (BASE / img).exists():
            return dict(card, img=img)
        return None

    def toggle_back(self, now):
        self.show_back = not self.show_back
        self.back_t = now

    def play_next_idle(self, now):
        """Click on the Biggest Hit: play the next idle animation (with its number shown)."""
        self.manual = ((self.last_kind + 1) % len(self.IDLE), now)

    # Images
    def fetch_image(self, card):
        """Fetch a missing card image in the background (once per image, throttled via netpolite) – then the
        overlay draws it by itself (placeholder until then)."""
        img = card.get("img")
        pending = self.__dict__.setdefault("_img_pending", set())
        if not img or img in pending or (BASE / img).exists():
            return
        pending.add(img)
        face = 1 if str(card.get("id", "")).endswith("_1") else 0

        def work():
            try:
                url = library.image_url(card["set"], str(card["number"]), version="normal", face=face)
                if url:
                    library.fetch_image(card, url)
                else:   # the source has no image (e.g. new promos): placeholder "not available" instead of "loading"
                    imgcache.mark_missing(img)
            except Exception as e:  # noqa: BLE001
                log.info("Card image %s: %s", img, e)
                imgcache.mark_missing(img)
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def missing_card(p, rect, radius=8.0):
        """The source has no image: the crossed-out card like qml/components/NoImage.qml (the user's design) – solid
        outline and a diagonal from bottom left to top right; from 180 px wide "Image not available" in the middle,
        the line leaves a gap around the text."""
        p.save()
        p.fillRect(rect, QtGui.QColor(*CARD_FILL))
        ink = QtGui.QColor(scanlook.INK)
        ink.setAlphaF(0.55)
        lw = max(1.2, rect.width() / 90)
        pen = QtGui.QPen(ink, lw)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        half = lw / 2
        p.drawRoundedRect(rect.adjusted(half, half, -half, -half), radius, radius)
        inset = radius * 0.9
        a = QPointF(rect.left() + inset, rect.bottom() - inset)
        b = QPointF(rect.right() - inset, rect.top() + inset)
        if rect.width() < 180:
            p.drawLine(a, b)
            p.restore()
            return
        p.setFont(font(max(12.0, rect.width() / 17)))
        text = tr("Image not available")
        box = p.boundingRect(QRectF(rect.left() + rect.width() * 0.15, rect.top(), rect.width() * 0.7, rect.height()),
                             Qt.AlignCenter | Qt.TextWordWrap, text)
        dx, dy = b.x() - a.x(), a.y() - b.y()
        dt = min((box.width() / 2 + 10) / max(1.0, dx), (box.height() / 2 + 8) / max(1.0, dy))
        p.drawLine(a, QPointF(a.x() + dx * (0.5 - dt), a.y() - dy * (0.5 - dt)))
        p.drawLine(QPointF(a.x() + dx * (0.5 + dt), a.y() - dy * (0.5 + dt)), b)
        text_ink = QtGui.QColor(scanlook.INK)
        text_ink.setAlphaF(0.75)
        p.setPen(text_ink)
        p.drawText(box, Qt.AlignCenter | Qt.TextWordWrap, text)
        p.restore()

    def no_image(self, p, rect, c, radius=8.0):
        """Placeholder instead of a card image: the crossed-out card if the source has none (missing_card), otherwise
        – still loading – a dark card with border, name, set and "loading image …"."""
        if imgcache.is_missing(c.get("img")):
            self.missing_card(p, rect, radius)
            return
        p.save()
        p.fillRect(rect, QtGui.QColor(*CARD_FILL))
        p.setPen(QtGui.QPen(QtGui.QColor(238, 241, 255, 60), max(1.0, rect.width() / 160)))
        p.setBrush(Qt.NoBrush)
        m = rect.width() * 0.06
        inner = rect.adjusted(m, m, -m, -m)
        p.drawRoundedRect(inner, radius * 0.6, radius * 0.6)
        big = max(9.0, rect.width() / 13)
        p.setPen(QtGui.QColor(238, 241, 255, 170))
        p.setFont(font(big, QtGui.QFont.Weight.DemiBold))
        p.drawText(inner.adjusted(8, 8, -8, -inner.height() * 0.45), Qt.AlignHCenter | Qt.AlignBottom | Qt.TextWordWrap,
                   shown_name(c, self.settings))
        p.setFont(font(max(7.0, big * 0.62)))
        p.setPen(QtGui.QColor(238, 241, 255, 110))
        p.drawText(inner.adjusted(8, inner.height() * 0.58, -8, -8), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                   f"{c['set']} #{c['number']}\n" + tr("loading image …"))
        p.restore()

    def pixmap(self, card, width, tint=None):
        key = (card["img"], width, tint)
        if key in self.pm_cache:
            self.pm_cache.move_to_end(key)
            return self.pm_cache[key]
        if tint is None:
            src = QtGui.QPixmap(str(BASE / card["img"]))
            if src.isNull():   # image missing: fetch it, show the placeholder – and don't remember it as "empty"
                self.fetch_image(card)
                return src
            pm = src.scaledToWidth(width, Qt.SmoothTransformation)
        else:
            base = self.pixmap(card, width)
            img = QtGui.QImage(base.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
            img.fill(Qt.transparent)
            p = QtGui.QPainter(img)
            p.drawPixmap(0, 0, base)
            p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
            p.fillRect(img.rect(), QtGui.QColor(tint))
            p.end()
            pm = QtGui.QPixmap.fromImage(img)
        self.pm_cache[key] = pm
        while len(self.pm_cache) > 64:
            self.pm_cache.popitem(last=False)
        return pm

    # --- Hover buttons ---
    def _hovered(self, p, rect):
        if self.hover is None:
            return False
        inv, ok = p.transform().inverted()
        return ok and rect.contains(inv.map(self.hover))

    def _button(self, p, rect, text, action, index=None, accent=None, size=15, active=False):
        """Paint a button into the overlay and remember it as clickable – the same key as in the UI (Key.qml,
        key lab "B · OP-XY knapp"): case colour, short shadows light at top left / dark at bottom right,
        highlight edge at top left, dark edge at bottom right; hover = brighter text. accent only colours the text
        (foil, pause …), active = lamp on the left lit."""
        hot = self._hovered(p, rect)
        r = min(9.0, rect.height() / 2)
        face = QtGui.QColor("#141416")
        p.save()
        p.setPen(Qt.NoPen)
        for dx, col in ((-3, QtGui.QColor(0x20, 0x20, 0x23)), (3, QtGui.QColor(0x06, 0x06, 0x07))):
            for k, a in ((3.0, 70), (1.5, 140), (0.0, 255)):   # soft shadow from three layers
                c = QtGui.QColor(col)
                c.setAlpha(a)
                p.setBrush(c)
                p.drawRoundedRect(rect.translated(dx * 0.8, dx * 0.8).adjusted(-k, -k, k, k), r + k, r + k)
        diag = rect.width() + rect.height()
        g = QtGui.QLinearGradient(rect.topLeft(), rect.topRight())   # highlight edge at top left
        g.setColorAt(0, QtGui.QColor(255, 255, 255, 56))
        g.setColorAt(min(1.0, 0.55 * diag / max(1.0, rect.width())), QtGui.QColor(0, 0, 0, 0))
        p.setBrush(face)
        p.drawRoundedRect(rect, r, r)
        p.setBrush(QtGui.QBrush(g))
        p.drawRoundedRect(rect, r, r)
        e = QtGui.QLinearGradient(rect.topLeft(), rect.topRight())   # dark edge at bottom right
        e.setColorAt(max(0.0, 1 - 0.40 * diag / max(1.0, rect.width())), QtGui.QColor(0, 0, 0, 0))
        e.setColorAt(1, QtGui.QColor(0, 0, 0, 150))
        inner = rect.adjusted(1, 1, 0, 0)
        p.setBrush(face)
        p.drawRoundedRect(inner, r - 0.5, r - 0.5)
        p.setBrush(QtGui.QBrush(e))
        p.drawRoundedRect(inner, r - 0.5, r - 0.5)
        p.setBrush(face)
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), r - 1, r - 1)
        word = len(text) > 2   # words in the normal font, characters in the symbol font
        tx = QRectF(rect)
        if active:   # lamp on the left
            p.setBrush(QtGui.QColor("#f2f2f2"))
            p.drawEllipse(QPointF(rect.left() + 11, rect.center().y()), 2.5, 2.5)
            tx.setLeft(tx.left() + 10)
        ink = QtGui.QColor("#f4f4f4" if hot else "#b4b4b4")
        if accent is not None and accent != scanlook.CYAN:
            ink = QtGui.QColor(accent)
        p.setFont(font(size, QtGui.QFont.Weight.Bold) if word else font(size, QtGui.QFont.Weight.Bold, "Segoe UI Symbol"))
        p.setPen(ink)
        p.drawText(tx, Qt.AlignCenter, text)
        p.restore()
        self.buttons.append((p.transform().mapRect(rect), action, index))

    # --- Drawing ---
    def paint(self, p, canvas, now, dpr):
        s = canvas.width() / 1920
        self._canvas, self._s = QRectF(canvas), s
        # Which card is under the mouse? (names from the last frame)
        hovered = None
        if not self.suppress:
            hovered = self.panel_hover
            if hovered is None and self.hover is not None:
                hovered = next((c for r, c in self.name_regions if r.contains(self.hover)), None)
        self._update_focus(hovered, now)
        self.buttons, self.name_regions = [], []
        p.save()
        p.setClipRect(canvas)
        p.translate(canvas.topLeft())
        p.scale(s, s)
        cw, ch = canvas.width() / s, canvas.height() / s
        self._paint_effects(p, cw, ch, now, s, dpr)   # the tiles show card, list and session – here only the effects
        p.restore()

    def _paint_effects(self, p, cw, ch, now, s, dpr):
        """With the tiles: only the big preview of a card under the mouse (the tiles' list, the card search). A new
        card – and a new Biggest Hit – jumps into the "Last hit" tile there (QML, one sequence, never here)."""
        self._paint_focus(p, cw, ch, now, s, dpr)

    def _to_overlay(self, g):
        return QRectF((g.left() - self._canvas.left()) / self._s, (g.top() - self._canvas.top()) / self._s,
                      g.width() / self._s, g.height() / self._s)

    # --- Big preview in the middle (hover over card names) ---
    FRAME_NAMES = {"showcase": "Showcase", "extendedart": "Extended Art", "etched": "Etched", "inverted": "Inverted",
                   "fullart": "Full Art", "companion": "Companion", "shatteredglass": "Shattered Glass"}
    PROMO_NAMES = {"surgefoil": "Surge Foil", "galaxyfoil": "Galaxy Foil", "textured": "Textured Foil",
                   "serialized": "Seriennummeriert", "halofoil": "Halo Foil", "ripplefoil": "Ripple Foil",
                   "gilded": "Gilded Foil", "confettifoil": "Confetti Foil", "doublerainbow": "Double Rainbow",
                   "stepandcompleat": "Step-and-Compleat", "prerelease": "Prerelease-Promo",
                   "promopack": "Promo Pack", "buyabox": "Buy-a-Box", "neonink": "Neon Ink",
                   "oilslick": "Oil Slick", "fracturefoil": "Fracture Foil", "manafoil": "Mana Foil",
                   "raisedfoil": "Raised Foil", "firstplacefoil": "First Place Foil", "rainbowfoil": "Rainbow Foil"}

    def _update_focus(self, hovered, now):
        cur = self.focus["card"] if self.focus else None
        same = cur is not None and hovered is not None and \
            (cur.get("added"), cur["id"]) == (hovered.get("added"), hovered["id"])
        if same or (cur is None and hovered is None):
            return
        if self.focus:
            self.leaving.append(dict(self.focus, t=now, mode="switch" if hovered else "out"))
        self.focus = {"card": hovered, "t": now, "mode": "switch" if cur else "in"} if hovered else None
        # fast sweeping: only fade out the last leaving preview (otherwise up to 5 cards stacked up,
        # each with shadow and gloss – the overlay then only managed ~10 frames/s)
        self.leaving = [f for f in self.leaving if now - f["t"] < 0.4][-1:]
        if hovered:
            self._request_details(hovered)

    @staticmethod
    def _local_details(sid):
        """Other games (Pokémon): extra info from the local card database – artist, set, HP, type, weakness,
        retreat, regulation mark, finishes, prints, legality. Same format as the Scryfall info (+ "extra")."""
        r = carddb.card(sid) if carddb.exists() else None
        if not r:
            return {"error": "keine Daten"}
        d = {"artist": r.get("artist") or "", "set_name": r.get("set_name") or "",
             "released_at": r.get("released") or "", "flavor_text": r.get("flavor_text") or ""}
        pr = {k: f"{r[k]:.2f}" for k in ("eur", "eur_foil", "usd", "usd_foil") if r.get(k) is not None}
        d["prices"] = pr
        extra = games.current().info_rows(r)   # the game's own values (Lorcana: cost, inkwell, lore …)
        if extra is None:
            extra = []
            if r.get("type_line"):
                extra.append((tr("Type"), r["type_line"]))
            if r.get("power"):
                extra.append((tr("HP"), str(r["power"])))
            if r.get("mana_cost"):
                extra.append((tr("Weakness"), r["mana_cost"]))
            if r.get("cmc") is not None and r.get("power"):
                extra.append((tr("Retreat"), str(int(r["cmc"]))))
            if r.get("promo_types"):
                extra.append(("Regulation Mark", r["promo_types"]))
        try:
            variants = games.current().variants_of(sid) if games.current().variants_of is not None else []
        except Exception:  # noqa: BLE001
            variants = []
        names = {"normal": "Normal", "holo": "Holo", "reverse": "Reverse Holo", "firstEdition": "1st Edition",
                 "wPromo": "W-Promo"}
        if variants:
            extra.append((tr("Finishes"), " · ".join(names.get(v, v) for v in variants)))
        d["extra"] = extra
        try:
            with carddb.connection() as con:
                # only prints of the English sets (Asian sets are separate prints with their own names)
                eng = "name = ? AND COALESCE(lang, 'en') = 'en'"
                prints = con.execute(f"SELECT COUNT(*), MIN(released) FROM cards WHERE {eng}", (r["name"],)).fetchone()
                first = con.execute(f"SELECT set_name FROM cards WHERE {eng} AND released != '' ORDER BY released "
                                    "LIMIT 1", (r["name"],)).fetchone()
            d["prints"], d["first_date"], d["first_set"] = prints[0], prints[1] or "", first[0] if first else ""
        except Exception:  # noqa: BLE001
            pass
        try:
            legal = json.loads(r.get("legalities") or "{}")
            d["legal"] = [k.capitalize() for k, v in legal.items() if v == "legal"]
        except ValueError:
            pass
        return d

    def _request_details(self, card):
        sid = card["id"].rpartition("_")[0]
        if sid in self.details:
            return
        if not games.current().online_details:   # local data: right there, no internet
            self.details[sid] = self._local_details(sid)
            return
        self.details[sid] = None  # loading

        def work():
            try:
                self.details[sid] = library.card_details(card)
            except Exception as e:
                log.warning("Card info for %s: %s", card["name"], e)
                self.details[sid] = {"error": str(e)}
        threading.Thread(target=work, daemon=True).start()

    def _paint_focus(self, p, cw, ch, now, s, dpr):
        # faded out: gone (else busy()/has_fx() would keep the overlay drawing at the full rate for ever)
        self.leaving = [f for f in self.leaving if now - f["t"] < 0.35]
        items = [(f, False) for f in self.leaving]
        if self.focus:
            items.append((self.focus, True))
        if not items:
            return
        # the preview just stands there – nothing around it is darkened (Oliver: "mag das gar nicht")
        for f, on in items:
            self._paint_focus_card(p, f, on, cw, ch, now, s, dpr)

    def _focus_shadow(self, card_w, card_h, radius, dpr):
        """Shadow of the big preview (7 soft layers) as a finished image – once per card size."""
        key = (round(card_w), round(card_h), dpr)
        cache = self.__dict__.setdefault("_shadow_cache", {})
        if key not in cache:
            pad = 7 * 5 + 2
            img = QtGui.QImage(round((card_w + 2 * pad) * dpr), round((card_h + 2 * pad + 64) * dpr),
                               QtGui.QImage.Format_ARGB32_Premultiplied)
            img.setDevicePixelRatio(dpr)
            img.fill(Qt.transparent)
            q = QtGui.QPainter(img)
            q.setRenderHint(QtGui.QPainter.Antialiasing)
            q.setPen(Qt.NoPen)
            rect = QRectF(pad, pad, card_w, card_h)
            for k in range(7):
                q.setBrush(QtGui.QColor(0, 0, 0, 24))
                q.drawRoundedRect(rect.adjusted(-k * 5, 16 - k, k * 5, 22 + k * 6), radius + k * 5, radius + k * 5)
            q.end()
            if len(cache) > 8:
                cache.clear()
            cache[key] = (img, pad)
        return cache[key]

    def _paint_focus_card(self, p, f, entering, cw, ch, now, s, dpr):
        c = f["card"]
        t = now - f["t"]
        back = self.other_face(c)
        wv = (now - self.back_t) / 0.45  # flip animation after clicking ⟲
        turning = back is not None and 0 <= wv < 1
        show_back = self.show_back if not turning or wv >= 0.5 else not self.show_back
        if back is not None and show_back:
            c = back
        card_h = min(ch * 0.62, 660.0)
        card_w = card_h * CARD_ASPECT
        info_w, gap = 400.0, 44.0
        group_w = card_w + gap + info_w
        cx = cw / 2 - group_w / 2 + card_w / 2
        cy = ch / 2 - 70
        free = self._free_beside_panel(cw)
        if free is not None:   # search/edit open: just the card, large in the free space beside it (for comparing)
            fl, fr = free
            card_h = min(ch * 0.56, 640.0, (fr - fl) / CARD_ASPECT)
            card_w = card_h * CARD_ASPECT
            cx = (fl + fr) / 2
        elif self.hover_list:   # a card of the scan list: just the card, right beside the list (never in the middle)
            beside = self._beside_list(cw, ch)
            if beside is not None:
                cx, cy, card_h = beside
                card_w = card_h * CARD_ASPECT
                free = (cx, cx)
        if entering:
            u = ease_out(t / 0.3)
            if f["mode"] == "switch":   # slide in from the right
                opacity, scale, dx, dy, rot = u, 0.96 + 0.04 * u, 90 * (1 - u), 0.0, 4 * (1 - u)
            else:                       # rise gently from the depth
                opacity, scale, dx, dy, rot = u, 0.82 + 0.18 * u, 0.0, 40 * (1 - u), 0.0
        else:
            u = ease_in_out(t / 0.3)
            if f["mode"] == "switch":   # slide away to the left
                opacity, scale, dx, dy, rot = 1 - u, 1 - 0.04 * u, -90 * u, 0.0, -4 * u
            else:                       # sink downwards and fade
                opacity, scale, dx, dy, rot = 1 - u, 1 - 0.1 * u, 0.0, 30 * u, 0.0
        if opacity <= 0.01:
            return
        # Only the card floats (text stays still)
        fy = 9 * math.sin(now * 1.3)
        tilt = math.sin(now * 0.8)
        p.save()
        p.setOpacity(opacity)
        p.translate(cx + dx, cy + dy + fy)
        p.rotate(rot + 0.8 * math.sin(now * 0.6))
        turn = abs(math.cos(math.pi * wv)) if turning else 1.0
        p.scale(scale * (1 - 0.025 * abs(tilt)) * max(turn, 0.02), scale)
        p.shear(0, 0.012 * tilt)
        rect = QRectF(-card_w / 2, -card_h / 2, card_w, card_h)
        radius = card_w * 0.047
        p.setPen(Qt.NoPen)
        sh, pad = self._focus_shadow(card_w, card_h, radius, dpr)   # soft shadow: painted once, then only copied
        p.drawImage(QRectF(rect.left() - pad, rect.top() - pad, card_w + 2 * pad, card_h + 2 * pad + 64), sh)
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        p.save()
        p.setClipPath(clip)
        pm = self.pixmap(c, max(1, round(card_w * s * dpr)))
        if pm.isNull() and imgcache.is_missing(c.get("img")):   # the source has none: crossed-out card
            self.missing_card(p, rect, radius)
        elif pm.isNull():   # image still loading: blank card with border, name and set
            p.fillRect(rect, QtGui.QColor(*CARD_FILL))
            p.setPen(QtGui.QPen(QtGui.QColor(238, 241, 255, 60), 2))
            p.setBrush(Qt.NoBrush)
            inner = rect.adjusted(card_w * 0.05, card_w * 0.05, -card_w * 0.05, -card_w * 0.05)
            p.drawRoundedRect(inner, radius * 0.6, radius * 0.6)
            p.drawRect(QRectF(inner.left() + 10, inner.top() + inner.height() * 0.1, inner.width() - 20,
                              inner.height() * 0.42))
            p.setPen(QtGui.QColor(238, 241, 255, 150))
            p.setFont(font(22, QtGui.QFont.Weight.DemiBold))
            p.drawText(QRectF(inner.left() + 14, inner.top() + 6, inner.width() - 28, inner.height() * 0.1 - 6),
                       Qt.AlignLeft | Qt.AlignVCenter, shown_name(c, self.settings))
            p.setFont(font(15))
            p.setPen(QtGui.QColor(238, 241, 255, 90))
            p.drawText(QRectF(inner.left(), inner.top() + inner.height() * 0.58, inner.width(), 40),
                       Qt.AlignHCenter | Qt.AlignVCenter, f"{c['set']} #{c['number']}  ·  " + tr("loading image …"))
        else:
            p.drawPixmap(rect, pm, QRectF(pm.rect()))
        # Gloss: a wide streak of light moves slowly across the card, now and then a short flash
        drift = math.sin(now * 0.5) * card_w * 0.75
        flicker = math.sin(now * 0.9) ** 16
        light = QtGui.QLinearGradient(rect.left() + drift, rect.top(), rect.right() + drift, rect.bottom())
        light.setColorAt(0.28, QtGui.QColor(255, 255, 255, 0))
        light.setColorAt(0.44, QtGui.QColor(255, 255, 255, int(40 + 35 * flicker)))
        light.setColorAt(0.5, QtGui.QColor(255, 255, 255, int(78 + 70 * flicker)))
        light.setColorAt(0.56, QtGui.QColor(255, 255, 255, int(40 + 35 * flicker)))
        light.setColorAt(0.72, QtGui.QColor(255, 255, 255, 0))
        p.fillRect(rect, light)
        if c.get("foil"):  # Foil: rainbow shimmer moving in the opposite direction
            off = math.sin(now * 0.35 + 1.2) * card_w
            holo = QtGui.QLinearGradient(rect.left() + off, rect.top(), rect.right() + off, rect.bottom())
            a = int(48 + 30 * flicker)
            for pos, col in ((0.0, "#ff5bd6"), (0.18, "#ffe45b"), (0.36, "#9dffb0"), (0.54, "#62f2ff"),
                             (0.72, "#8f7bff"), (0.9, "#ff5bd6"), (1.0, "#ffe45b")):
                cc = QtGui.QColor(col)
                cc.setAlpha(a)
                holo.setColorAt(pos, cc)
            p.setCompositionMode(QtGui.QPainter.CompositionMode_Screen)
            p.fillRect(rect, holo)
        p.restore()
        p.setPen(QtGui.QPen(QtGui.QColor(238, 241, 255, 60), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, radius, radius)
        p.restore()
        if not entering and f["mode"] == "switch":
            return  # on a switch the old card slides away without text

        # Name, rarity, price below – fixed, only fading in/out; not beside the open card search (it shows them itself,
        # and the text would run over the tiles there)
        if free is not None and not self.hover_list:
            return
        p.save()
        p.setOpacity(opacity)
        base = QPointF(cx + dx, cy + dy + card_h / 2)
        level = tier(c.get("price"), self.settings["hit"])
        p.setFont(font(40, QtGui.QFont.Weight.DemiBold))
        p.setPen(scanlook.INK)
        p.drawText(QRectF(base.x() - 500, base.y() + 22, 1000, 50), Qt.AlignHCenter | Qt.AlignVCenter,
                   shown_name(c, self.settings))
        meta = card_meta(c) + (f" · {tr(finish_label(c))}" if finish_label(c) else "")
        if back is not None:
            meta += "  ·  " + (tr("back") if show_back else tr("front"))
        p.setFont(font(20))
        p.setPen(scanlook.MUTED)
        p.drawText(QRectF(base.x() - 500, base.y() + 70, 1000, 28), Qt.AlignHCenter | Qt.AlignVCenter, meta)
        price = c.get("price")
        p.setFont(font(54, QtGui.QFont.Weight.Bold, "Bahnschrift"))
        p.setPen(TIER_COLOR[level])
        p.drawText(QRectF(base.x() - 500, base.y() + 98, 1000, 70), Qt.AlignHCenter | Qt.AlignVCenter,
                   tr("no price") if price is None else eur(price))
        # Card info to the right (Magic: Scryfall, other games: own card database) – not when the
        # card search is open beside it (it shows name, price and info itself)
        if free is None:
            self._paint_details(p, c, QRectF(cx + dx + card_w / 2 + gap, cy + dy - card_h / 2, info_w, card_h + 150))
        p.restore()

    def _beside_list(self, cw, ch):
        """The scan tile's list: where the preview of one of its cards stands – right beside the tile, on its wider
        side -> (centre x, centre y, card height) in overlay coordinates, or None (no room)."""
        if self.list_tile is None or self._s <= 0:
            return None
        r = self._to_overlay(self.list_tile)
        right = cw - r.right() >= r.left()
        room = (cw - r.right() if right else r.left()) - 2 * 40
        top, bottom = 30.0, ch - 30.0
        if self.free_band is not None:   # never over the status line or the dock: card, name and price fit between
            b = self._to_overlay(self.free_band)
            top, bottom = max(top, b.top() + 20), min(bottom, b.bottom() - 20)
        text_h = 180.0   # name, rarity and price below the card (+ its gentle float)
        card_h = min(ch * 0.6, 620.0, room / CARD_ASPECT, bottom - top - text_h - 10)
        if card_h < 120:
            return None
        card_w = card_h * CARD_ASPECT
        cx = r.right() + 40 + card_w / 2 if right else r.left() - 40 - card_w / 2
        cy = min(max(r.center().y() - 60, top + card_h / 2 + 10), bottom - card_h / 2 - text_h)
        return cx, cy, card_h

    def _free_beside_panel(self, cw):
        """Card search/edit open: the wider free strip beside it (overlay coordinates) -> (left, right) or None (too
        narrow or nothing open)."""
        g = self.panel_rect
        if g is None or self._s <= 0:
            return None
        gl = (g.left() - self._canvas.left()) / self._s
        gr = (g.right() - self._canvas.left()) / self._s
        fl, fr = max((self.MARGIN, gl - 40), (gr + 40, cw - self.MARGIN), key=lambda f: f[1] - f[0])
        return (fl, fr) if fr - fl > 220 else None

    def _detail_rows(self, c, d):
        rows = list(d.get("extra") or [])   # game-specific details (Pokémon: type, HP, weakness …)
        if d.get("artist"):
            rows.append((tr("Artist"), d["artist"]))
        if d.get("set_name"):
            date = d.get("released_at") or ""
            date = f"{date[8:10]}.{date[5:7]}.{date[:4]}" if len(date) == 10 else date
            rows.append((tr("Set"), f"{d['set_name']} ({c['set']})" + (f" · {date}" if date else "")))
        variants = []
        if d.get("border_color") == "borderless":
            variants.append(tr("Borderless"))
        variants += [self.FRAME_NAMES[x] for x in d.get("frame_effects", []) if x in self.FRAME_NAMES]
        if d.get("full_art") and "Full Art" not in variants:
            variants.append("Full Art")
        variants += [self.PROMO_NAMES[x] for x in d.get("promo_types", []) if x in self.PROMO_NAMES]
        if variants:
            rows.append((tr("Variant"), " · ".join(tr(v) for v in variants)))
        games = [x for x in d.get("promo_types", []) if re.fullmatch(r"ff[ivx]+", x)]
        if games:
            rows.append((tr("From"), ", ".join("Final Fantasy " + g[2:].upper() for g in games)))
        pr = d.get("prices") or {}
        price_parts = []
        for key, fmt in (("eur", "{} €"), ("eur_foil", tr("Foil {} €")), ("usd", "{} $"), ("usd_foil", tr("Foil {} $"))):
            if pr.get(key):
                price_parts.append(fmt.format(pr[key].replace(".", ",")))
        if price_parts:
            rows.append((tr("Prices"), " · ".join(price_parts)))
        if d.get("prints"):
            first = d.get("first_date", "")[:4]
            txt = tr(f"{d['prints']} printings") if d["prints"] != 1 else tr("only printing")
            if d.get("first_set") and d["prints"] != 1:
                txt += tr(f" · first printed {first} in {d['first_set']}")
            rows.append((tr("Printings"), txt))
        if d.get("edhrec_rank"):
            rows.append(("EDHREC", tr(f"Seat {d['edhrec_rank']:,}").replace(",", ".") + tr(" among the most popular Commander cards")))
        if d.get("legal"):
            rows.append((tr("Legal in"), ", ".join(d["legal"])))
        badges = []
        if d.get("reserved"):
            badges.append("Reserved List")
        if d.get("game_changer"):
            badges.append("Game Changer")
        if d.get("story_spotlight"):
            badges.append("Story Spotlight")
        if d.get("reprint") is False:
            badges.append(tr("First printing"))
        if d.get("textless"):
            badges.append(tr("Textless"))
        return rows, badges

    def _paint_details(self, p, c, area):
        sid = c["id"].rpartition("_")[0]
        d = self.details.get(sid)
        pad, w = 22.0, area.width()
        lf, vf, hf = font(15, QtGui.QFont.Weight.DemiBold), font(18), font(16, QtGui.QFont.Weight.DemiBold)
        if not d or "error" in d:
            msg = tr("Loading info from Scryfall …") if d is None else tr("No extra info (offline?)")
            box = QRectF(area.left(), area.top(), w, 64)
            self._plate(p, box)
            p.setFont(font(16))
            p.setPen(scanlook.MUTED)
            p.drawText(box, Qt.AlignCenter, msg)
            return
        rows, badges = self._detail_rows(c, d)
        fm_v = QtGui.QFontMetricsF(vf)
        layout = []
        y = pad + 30
        for label, value in rows:
            vh = fm_v.boundingRect(QRectF(0, 0, w - 2 * pad, 400), Qt.TextWordWrap, value).height()
            layout.append((label, value, y, vh))
            y += 20 + vh + 10
        badge_h = 40 if badges else 0
        flavor = (d.get("flavor_text") or "").strip()
        ff = font(17)
        ff.setItalic(True)
        flavor_h = 0.0
        if flavor:
            flavor_h = min(QtGui.QFontMetricsF(ff).boundingRect(QRectF(0, 0, w - 2 * pad, 400), Qt.TextWordWrap,
                                                                 f"„{flavor}“").height(), 5 * 24) + 16
        box = QRectF(area.left(), area.top(), w, min(area.height(), y + badge_h + flavor_h + pad - 4))
        self._plate(p, box, 16)
        p.save()
        p.setClipRect(box)
        p.setFont(hf)
        p.setPen(scanlook.CYAN)
        p.drawText(QRectF(box.left() + pad, box.top() + pad - 4, w - 2 * pad, 26), Qt.AlignLeft | Qt.AlignVCenter,
                   tr("CARD INFO"))
        for label, value, ry, vh in layout:
            p.setFont(lf)
            p.setPen(scanlook.MUTED)
            p.drawText(QRectF(box.left() + pad, box.top() + ry, w - 2 * pad, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       label)
            p.setFont(vf)
            p.setPen(scanlook.INK)
            p.drawText(QRectF(box.left() + pad, box.top() + ry + 20, w - 2 * pad, vh),
                       Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, value)
        by = box.top() + y
        if badges:
            bx = box.left() + pad
            p.setFont(font(14, QtGui.QFont.Weight.Bold))
            for b in badges:
                bw = QtGui.QFontMetricsF(p.font()).horizontalAdvance(b) + 22
                if bx + bw > box.right() - pad:
                    break
                r = QRectF(bx, by, bw, 28)
                p.setPen(QtGui.QPen(scanlook.MAGENTA if b in ("Reserved List", "Game Changer") else scanlook.CYAN, 1.5))
                p.setBrush(QtGui.QColor(20, 24, 42))
                p.drawRoundedRect(r, 14, 14)
                p.setPen(scanlook.INK)
                p.drawText(r, Qt.AlignCenter, b)
                bx += bw + 8
            by += badge_h
        if flavor:
            p.setFont(ff)
            p.setPen(QtGui.QColor(238, 241, 255, 190))
            p.drawText(QRectF(box.left() + pad, by + 6, w - 2 * pad, flavor_h - 10),
                       Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, f"„{flavor}“")
        p.restore()

    def _plate(self, p, rect, radius=14):
        p.setPen(Qt.NoPen)
        p.setBrush(scanlook.PLATE)
        p.drawRoundedRect(rect, radius, radius)

    @staticmethod
    def sets_text(info):
        sets = info.get("sets") or []
        if len(sets) == 1:
            return sets[0]["name"]
        return " · ".join(s["code"].upper() if s.get("code") else s["name"] for s in sets)

    def _idle_state(self, now):
        """-> (animation number, progress 0..1, by click?) or None."""
        if self.manual:
            k, t0 = self.manual
            dur = self.IDLE[k][1]
            self.last_kind = k
            if now - t0 < dur:
                return k, (now - t0) / dur, True
            if now - t0 > dur + 1.2:
                self.manual = None
        t = now - self.big_hit_t - 1.2
        if t < 0:
            return None
        cycle, phase = divmod(t, self.IDLE_EVERY)
        k = int(cycle) % len(self.IDLE)
        if phase < self.IDLE[k][1]:
            self.last_kind = k
            return k, phase / self.IDLE[k][1], False
        return None

    def _paint_big_hit(self, p, x, w, top, bottom, now, s, dpr):
        c = self.big_hit
        head_h, label_h = 42, 76
        avail = bottom - top - head_h - label_h
        if avail < 120:
            return
        cw_ = min(230.0, avail * CARD_ASPECT)
        chh = cw_ / CARD_ASPECT
        block_top = top + (avail - chh) / 2  # heading, card, name/price as one block, vertically centred
        cx = x + w / 2
        cy = block_top + head_h + chh / 2
        t = now - self.big_hit_t

        # heading = toggle Session / All Time
        head = QRectF(x, block_top - 4, w, 30)
        if not self.manual:  # while a click label is running, it replaces the heading
            hot = self._hovered(p, head)
            p.setFont(font(16, QtGui.QFont.Weight.DemiBold))
            p.setPen(scanlook.CYAN if (hot or self.hit_mode == "all") else scanlook.MUTED)
            label = tr("BIGGEST HIT · ALL TIME") if self.hit_mode == "all" else tr("BIGGEST HIT")
            p.drawText(QRectF(x, block_top, w, 22), Qt.AlignHCenter | Qt.AlignVCenter, label + ("  ⇄" if hot else ""))
        self.buttons.append((p.transform().mapRect(head), "hitmode", None))

        # Basic movement: gentle floating and swaying
        dy = 6 * math.sin(now * 1.1)
        rot = 1.6 * math.sin(now * 0.7)
        sx = sy = scale = 1.0
        shine, tilt = None, 0.0
        extra, k, u, manual = None, None, 0.0, False
        if t < 1.2:  # new Biggest Hit: card jumps in
            v = t / 1.2
            scale = 0.55 + 0.45 * (1 + 2.2 * (v - 1) ** 3 + 1.2 * (v - 1) ** 2)
            rot += (1 - v) * -14
            extra, u = "Sternenfunkeln", v
        state = self._idle_state(now) if t >= 1.2 else None
        if state:
            k, u, manual = state
            name = self.IDLE[k][0]
            env = math.sin(math.pi * u)
            if name == "Tanzen":  # slower, easing in and out softly
                rot += 6 * math.sin(u * math.pi * 4) * env
                dy -= 11 * abs(math.sin(u * math.pi * 2)) * env
            elif name == "Kippen":  # tilt first to the top left, then to the bottom right
                tilt = math.sin(u * 2 * math.pi) * env ** 0.5
            elif name == "Lichtreflex":
                shine = u
            elif name == "Wackelpudding":
                wob = math.sin(u * math.pi * 7) * (1 - u) * 0.09
                sx, sy = 1 + wob, 1 - wob
                dy += 10 * wob * 10
            elif name == "Feuerwerk":
                dy -= 4 * env
            elif name == "Herzchen":
                scale = 1 + 0.03 * math.sin(u * math.pi * 3) * env
            extra = name

        rect = QRectF(-cw_ / 2, -chh / 2, cw_, chh)
        world = QRectF(cx - cw_ / 2, cy + dy - chh / 2, cw_, chh)
        if extra == "Orbit-Lichter":
            self._fx_orbit(p, world, u, back=True)
        if extra == "Herzchen":
            self._fx_hearts(p, world, u, int(self.big_hit_t * 10), back=True)
        p.save()
        p.translate(cx, cy + dy)
        p.rotate(rot)
        p.scale(scale * sx, scale * sy)
        if tilt:  # real 3D tilt towards the corner (perspective)
            q = QtGui.QTransform()
            q.rotate(-16 * tilt, Qt.YAxis, 600)
            q.rotate(16 * tilt, Qt.XAxis, 600)
            p.setTransform(q, True)
        radius = cw_ * 0.047
        p.setPen(Qt.NoPen)
        for i in range(5):
            p.setBrush(QtGui.QColor(0, 0, 0, 22))
            p.drawRoundedRect(rect.adjusted(-i * 3, 10 - i, i * 3, 12 + i * 4), radius + i * 3, radius + i * 3)
        glow = QtGui.QColor(scanlook.MAGENTA if tier(c["price"], self.settings["hit"]) == "hit" else scanlook.CYAN)
        glow.setAlpha(int(120 + 60 * math.sin(now * 2.0)))
        p.setPen(QtGui.QPen(glow, 3))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        p.save()
        p.setClipPath(clip)
        pm = self.pixmap(c, max(1, round(cw_ * s * dpr)))
        if not pm.isNull():
            p.drawPixmap(rect, pm, QRectF(pm.rect()))
        else:
            self.no_image(p, rect, c, radius)
        if shine is not None:  # double, subtle light reflection
            for delay, alpha in ((0.0, 95), (0.22, 60)):
                v = (shine - delay) / (1 - 0.22)
                if 0 < v < 1:
                    off = (v * 2.4 - 1.2) * cw_
                    band = QtGui.QLinearGradient(rect.left() + off, rect.top(), rect.right() + off, rect.bottom())
                    band.setColorAt(0.42, QtGui.QColor(255, 255, 255, 0))
                    band.setColorAt(0.5, QtGui.QColor(255, 255, 255, alpha))
                    band.setColorAt(0.58, QtGui.QColor(255, 255, 255, 0))
                    p.fillRect(rect, band)
        if tilt:  # when tilting: gloss moves along, rainbow only for foil
            off = tilt * cw_ * 0.9
            g = QtGui.QLinearGradient(rect.left() + off, rect.top(), rect.right() + off, rect.bottom())
            if c.get("foil"):
                for pos, col in ((0.0, "#ff5bd6"), (0.25, "#ffe45b"), (0.5, "#62f2ff"), (0.75, "#9dffb0"),
                                 (1.0, "#ff5bd6")):
                    cc = QtGui.QColor(col)
                    cc.setAlpha(int(75 * abs(tilt)))
                    g.setColorAt(pos, cc)
            else:
                g.setColorAt(0.3, QtGui.QColor(255, 255, 255, 0))
                g.setColorAt(0.5, QtGui.QColor(255, 255, 255, int(110 * abs(tilt))))
                g.setColorAt(0.7, QtGui.QColor(255, 255, 255, 0))
            p.fillRect(rect, g)
        p.restore()
        p.restore()

        if extra == "Sternenfunkeln":
            self._fx_sparkles(p, world, u, int(self.big_hit_t * 10) + (k or 0))
        elif extra == "Feuerwerk":
            self._fx_fireworks(p, world, u, int(self.big_hit_t * 10) + (k or 0))
        elif extra == "Herzchen":
            self._fx_hearts(p, world, u, int(self.big_hit_t * 10), back=False)
        elif extra == "Orbit-Lichter":
            self._fx_orbit(p, world, u, back=False)

        self.buttons.append((p.transform().mapRect(world), "bighit", None))
        ly = block_top + head_h + chh + 18
        name_rect = QRectF(x, ly, w, 72)
        self.name_regions.append((p.transform().mapRect(name_rect), c))
        p.setFont(font(19, QtGui.QFont.Weight.DemiBold))
        p.setPen(scanlook.INK)
        p.drawText(QRectF(x, ly, w, 28), Qt.AlignHCenter | Qt.AlignVCenter,
                   QtGui.QFontMetricsF(p.font()).elidedText(shown_name(c, self.settings), Qt.ElideRight, w - 10))
        p.setFont(font(30, QtGui.QFont.Weight.Bold, "Bahnschrift"))
        p.setPen(TIER_COLOR[tier(c["price"], self.settings["hit"])])
        p.drawText(QRectF(x, ly + 28, w, 42), Qt.AlignHCenter | Qt.AlignVCenter, eur(c["price"]))
        tag_k, fade = None, 1.0
        if state and manual:  # after a click: which animation was it?
            tag_k = k
        elif self.manual:     # let the number stay a little longer
            tag_k, t0 = self.manual
            fade = max(0.0, min(1.0, 1 - (now - t0 - self.IDLE[tag_k][1]) / 1.2))
        if tag_k is not None:
            p.setFont(font(15, QtGui.QFont.Weight.Bold))
            label = f"{tr('Animation')} {tag_k + 1}/{len(self.IDLE)} · {tr(self.IDLE[tag_k][0])}"
            lw = QtGui.QFontMetricsF(p.font()).horizontalAdvance(label) + 24
            tag = QRectF(x + (w - lw) / 2, block_top - 2, lw, 26)
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(98, 242, 255, int(210 * fade)))
            p.drawRoundedRect(tag, 13, 13)
            col = QtGui.QColor(10, 14, 28)
            col.setAlpha(int(255 * fade))
            p.setPen(col)
            p.drawText(tag, Qt.AlignCenter, label)
