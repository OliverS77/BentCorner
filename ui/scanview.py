"""Camera image with layers on top (ScanView) – calculation, mouse and drawing for the stream and the preview
in the settings. Moved from app.py (re-exported there)."""
import math
import time

from PySide6 import QtCore, QtGui
from PySide6.QtCore import QPointF, QRectF, Qt

from scanner.camera import Camera
from scanner.core import zone_rect
from system.i18n import tr
from ui import look, scanlook
from ui.scanlook import font


class ScanView(QtCore.QObject):
    """Camera image with layers on top – calculation, mouse and drawing, no widget. stream=True: the image in the stream
    (overlay with hover buttons); False: the preview in the settings (drag the scan frame, zoom, crop).
    Both are shown by Qt Quick (qscan.LiveView): size comes via resize(), mouse via press/move/…"""

    def __init__(self, ctrl, stream):
        super().__init__(ctrl)
        self.ctrl, self.stream = ctrl, stream
        self._w, self._h = 1600, 900
        self._drag = None
        self._pan = None
        self._chip = QRectF()
        self.zone_edit = False  # Stream: scan-frame toggle of the bar – frame above the overlay, even without a camera
        self.cursor = "arrow" if stream else "open"  # mouse cursor for QML: arrow | hand | open | closed | move
        self.on_update = None  # LiveView: "redraw"

    def width(self):
        return self._w

    def height(self):
        return self._h

    def size(self):
        return QtCore.QSize(self._w, self._h)

    def resize(self, size):
        self._w, self._h = max(320, size.width()), max(180, size.height())
        st = getattr(self.ctrl, "stream", None)
        if self.stream and st is not None:
            st.resized()

    def update(self):
        if self.on_update is not None:
            self.on_update()

    def _area(self):
        """For per-side values (rounding): the space of the scan page."""
        st = getattr(self.ctrl, "stream", None)
        return "scan" if self.stream and st is not None else None

    def frame_size(self):
        f = self.ctrl.frame_rgb
        return (f.shape[1], f.shape[0]) if f is not None else (1920, 1080)

    def canvas(self):
        fw, fh = self.frame_size()
        aspect = fw / fh
        w, h = self.width(), self.height()
        cw, ch = (h * aspect, h) if w / h > aspect else (w, w / aspect)
        return QRectF((w - cw) / 2, (h - ch) / 2, cw, ch)

    # --- Software zoom of the preview (for any camera; recognition always uses the full image) ---
    ZOOM_MAX = 4.0

    def zoom(self):
        return 1.0 if self.stream else float(self.ctrl.settings.get("preview_zoom", 1.0))

    def view_rect(self):
        """Visible crop of the camera image (pixels): (x, y, width, height)."""
        fw, fh = self.frame_size()
        z = self.zoom()
        vw, vh = fw / z, fh / z
        cx, cy = (0.5, 0.5) if self.stream else self.ctrl.settings.get("preview_center", [0.5, 0.5])
        x = min(max(0.0, cx * fw - vw / 2), fw - vw)
        y = min(max(0.0, cy * fh - vh / 2), fh - vh)
        return x, y, vw, vh

    def to_frame(self, pos):
        """Point in the window -> point in the camera image (pixels)."""
        c = self.canvas()
        vx, vy, vw, vh = self.view_rect()
        return vx + (pos.x() - c.left()) * vw / c.width(), vy + (pos.y() - c.top()) * vh / c.height()

    def set_zoom(self, z, anchor=None):
        """Zoom; anchor (window point) stays at the same spot of the image."""
        fw, fh = self.frame_size()
        z = round(min(self.ZOOM_MAX, max(1.0, z)), 3)
        c = self.canvas()
        if anchor is None:
            anchor = c.center()
        ax, ay = self.to_frame(anchor)
        u, v = (anchor.x() - c.left()) / c.width(), (anchor.y() - c.top()) / c.height()
        vw, vh = fw / z, fh / z
        self.ctrl.settings["preview_zoom"] = z
        self.ctrl.settings["preview_center"] = [(ax - u * vw + vw / 2) / fw, (ay - v * vh + vh / 2) / fh]
        self._clamp_center()
        self.ctrl.settings_changed()
        self.update()

    def _clamp_center(self):
        fw, fh = self.frame_size()
        vx, vy, vw, vh = self.view_rect()
        self.ctrl.settings["preview_center"] = [(vx + vw / 2) / fw, (vy + vh / 2) / fh]

    def fit_zone(self):
        """Zoom so far that the scan frame fills the preview nicely."""
        fw, fh = self.frame_size()
        x, y, w, h = zone_rect(self.ctrl.settings["zone"], fw, fh)
        z = min(self.ZOOM_MAX, max(1.0, 0.8 * fh / max(1, h)))
        self.ctrl.settings["preview_zoom"] = round(z, 3)
        self.ctrl.settings["preview_center"] = [(x + w / 2) / fw, (y + h / 2) / fh]
        self._clamp_center()
        self.ctrl.settings_changed()
        self.update()

    def zone_in_view(self):
        c = self.canvas()
        fw, fh = self.frame_size()
        x, y, w, h = zone_rect(self.ctrl.settings["zone"], fw, fh)
        vx, vy, vw, vh = self.view_rect()
        k = c.width() / vw
        return QRectF(c.left() + (x - vx) * k, c.top() + (y - vy) * k, w * k, h * k)

    hover_q = False  # Qt Quick: mouse over the image (the invisible view itself never sees the mouse)

    def paint_layers(self, p, c, dpr, fx=True):
        """Everything above the camera image: hint without image, scan overlay (preview) or stream overlay.
        Qt Quick draws the camera image itself and puts this image on top (qscan.py). fx=False: without the
        moments (big preview, Biggest Hit) – the scan page draws them on a layer above its tiles and windows."""
        frame = self.ctrl.frame_rgb
        # waking up from a rest: the blurred last picture is there – no "Opening camera …" on top (errors still show)
        resting = getattr(self.ctrl, "frame_rest", None) is not None and self.ctrl.camera.message == tr("Opening camera …")
        if frame is None and not (self.stream and resting) and                 (not self.stream or self.ctrl.camera.running or self.ctrl.cam_combo.count() == 0):
            # Stream: only while the camera is (re)starting – or if there is none at all
            p.setPen(scanlook.MUTED)
            p.setFont(font(15))
            if self.ctrl.cam_combo.currentData() == Camera.PHONE:   # phone waiting: QR code instead of just text
                self._paint_phone_qr(p, c)
            else:
                box = c.adjusted(20, 20, -20, -20)
                if self.stream:   # scan page: a narrow column in the middle – the tiles sit at the sides
                    w = min(box.width(), 460.0)
                    box = QRectF(c.center().x() - w / 2, box.top(), w, box.height())
                p.drawText(box, Qt.AlignCenter | Qt.TextWordWrap, self.ctrl.camera.message)
        if frame is not None and not self.stream:  # scan overlay only in the preview, never in the stream
            self._paint_scan(p, c)
            if self.hover_q or self._drag is not None:  # scan frame only for adjusting
                self._paint_zone(p, c)
            self._paint_zoom_chip(p, c)
        if self.stream:
            studio = getattr(self.ctrl, "studio", None)
            if fx:
                self.paint_fx(p, c, dpr)
            if studio is not None and studio.on:
                studio.paint(p, c, self.frame_size())
            if self.zone_edit:  # only added on top – the overlay stays
                self._paint_zone(p, c)

    def paint_fx(self, p, c, dpr):
        """The stream overlay's moments: the big preview of a card under the mouse and the Biggest-Hit celebration."""
        studio = getattr(self.ctrl, "studio", None)
        k = 0.0   # Studio open/closed: both sides of the overlay slide out to / in from their edge (0.35 s)
        if studio is not None:
            k = min(1.0, (time.monotonic() - studio.since) / 0.35)
            k = 1 - (1 - k) ** 3
            k = k if studio.on else 1 - k
        if k < 0.999:
            p.save()
            p.setOpacity(1 - k)
            self.ctrl.overlay.slide = k
            self.ctrl.overlay.paint(p, c, time.monotonic(), dpr)
            self.ctrl.overlay.slide = 0.0
            p.restore()

    def _paint_phone_qr(self, p, c):
        """Phone as camera, no image yet: QR code + short instructions in the middle of the scan view."""
        from scanner import phonecam
        url = phonecam.url() or self.ctrl.phone_start()
        if not url:
            p.drawText(c.adjusted(20, 20, -20, -20), Qt.AlignCenter | Qt.TextWordWrap,
                       tr("Phone camera could not start: ") + (phonecam.error() or "?"))
            return
        side = int(min(c.width(), c.height()) * 0.36)
        img = phonecam.qr_image(url, 8).scaled(side, side, Qt.KeepAspectRatio, Qt.FastTransformation)
        shown = time.monotonic() - getattr(self, "_qr_shown", -1e9) < phonecam.REVEAL_S
        if not shown:   # blurred until clicked – so nobody in the room (or in the stream) can read along
            img = phonecam.blurred(img)
        x, y = int(c.center().x() - side / 2), int(c.center().y() - side / 2 - 40)
        self._qr_rect = QRectF(x, y, side, side)
        p.drawImage(x, y, img)
        if not shown:
            p.save()
            p.setPen(QtGui.QColor(20, 20, 20))
            p.setFont(font(15, QtGui.QFont.Weight.Bold))
            p.drawText(self._qr_rect, Qt.AlignCenter | Qt.TextWordWrap, tr("Click to show"))
            p.restore()
        first = getattr(self, "_qr_first", 0.0)   # when the QR code was first shown (time.time)
        stuck = first and time.time() - first > 20 and phonecam.seen() < first
        text = tr("Scan with your phone (same Wi-Fi). The first time the browser warns – “Advanced → proceed anyway”: the connection stays in your network.")
        if stuck:   # 20 s after showing not one attempt: the Wi-Fi probably keeps the devices apart
            p.save()
            p.setPen(scanlook.INK)
            p.setFont(font(15, QtGui.QFont.Weight.Bold))
            p.drawText(QRectF(c.left() + 20, y + side + 10, c.width() - 40, 26), Qt.AlignHCenter,
                       tr("Phone not getting through?"))
            p.restore()
            text = (tr("Some Wi-Fi networks keep devices apart. A cable always works: plug the phone into the PC, tap the USB notification → “USB tethering” (iPhone: “Personal Hotspot”). The QR code switches over – just scan it again.") + "\n" +
                    tr("Android: the browser needs the “Nearby devices” permission. VPN on the PC: disconnect briefly."))
            y += 26
        else:
            text += "\n" + tr("Or by cable: tap the USB notification → “USB tethering”, then scan again.")
        p.drawText(QRectF(c.left() + 20, y + side + 14, c.width() - 40, 110), Qt.AlignHCenter | Qt.TextWordWrap, text)

    def to_view(self, pts, c):
        """Points in the camera image (pixels) -> window points (with zoom)."""
        vx, vy, vw, vh = self.view_rect()
        k = c.width() / vw
        return [QPointF(c.left() + (x - vx) * k, c.top() + (y - vy) * k) for x, y in pts]

    @staticmethod
    def _card_path(q):
        """Rectangle with rounded corners (like a real card)."""
        n = len(q)
        side = min(math.hypot(q[i].x() - q[(i + 1) % n].x(), q[i].y() - q[(i + 1) % n].y()) for i in range(n))
        r = side * 0.045
        path = QtGui.QPainterPath()
        for i in range(n):
            a, b, c2 = q[i - 1], q[i], q[(i + 1) % n]

            def toward(p1, p2, d):
                L = max(1e-6, math.hypot(p2.x() - p1.x(), p2.y() - p1.y()))
                return QPointF(p1.x() + (p2.x() - p1.x()) * d / L, p1.y() + (p2.y() - p1.y()) * d / L)
            p_in, p_out = toward(b, a, r), toward(b, c2, r)
            if i == 0:
                path.moveTo(p_in)
            else:
                path.lineTo(p_in)
            path.quadTo(b, p_out)
        path.closeSubpath()
        return path

    def _paint_scan(self, p, c):
        """Scan overlay: image slightly darkened (20 %), the card stays clear; a card frame follows the card,
        lights run around it. Green = counted, amber = question open."""
        trk = self.ctrl.tracker
        rec = self.ctrl.recognizer
        quad = trk.quad
        now = time.monotonic()
        dim = QtGui.QPainterPath()
        dim.addRect(c)
        if quad is None:
            p.fillPath(dim, QtGui.QColor(0, 0, 0, 51))
            if not rec.paused:
                self._scan_hint(p, c, tr("reading …") if rec.looking else tr("Hold a card into the picture"))
            return
        q = self.to_view(quad, c)
        card = self._card_path(q)
        p.fillPath(dim.subtracted(card), QtGui.QColor(0, 0, 0, 51))
        hit = rec.hit
        counted = hit is not None and rec.current is not None and hit[0]["id"] == rec.current["id"] \
            and trk.state == "erfasst"
        if rec.pending is not None:
            col = QtGui.QColor("#ffb347")
        elif counted:
            col = QtGui.QColor("#46d17a")
        else:
            col = QtGui.QColor(scanlook.CYAN)
        size = max(40.0, card.boundingRect().width())
        outside = dim.subtracted(card)
        p.save()
        p.setClipPath(outside)  # glow and lights only outside – the card stays clear
        # soft glow + frame
        glow = QtGui.QColor(col)
        glow.setAlpha(70)
        p.setBrush(Qt.NoBrush)
        p.setPen(QtGui.QPen(glow, max(8.0, size * 0.06), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(card)
        if not counted and rec.pending is None:  # searching/reading: two lights run around the card
            self._comets(p, card, col, now, size)
        p.restore()
        line = QtGui.QColor(col)
        line.setAlpha(230 if trk.state == "erfasst" else 150)
        p.setPen(QtGui.QPen(line, max(1.5, size * 0.008), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(card)
        if counted and time.time() - hit[1] < 0.9:  # counted: wave outwards
            u = (time.time() - hit[1]) / 0.9
            ring = QtGui.QColor(col)
            ring.setAlpha(int(200 * (1 - u)))
            p.setPen(QtGui.QPen(ring, 2 + 4 * (1 - u)))
            ctr = card.boundingRect().center()
            k = 1 + 0.12 * u
            p.drawPath(QtGui.QTransform().translate(ctr.x(), ctr.y()).scale(k, k)
                       .translate(-ctr.x(), -ctr.y()).map(card))
        # label below the card
        text = None
        if rec.pending is not None:
            text = tr("Several printings – please pick")
        elif trk.state == "erfasst" and rec.current is not None:
            text = f"{rec.current['name']}  ·  {rec.current['set']} #{rec.current['number']}"
        elif trk.state == "gefunden":
            text = tr("reading …")
        if text:
            bottom = max(q, key=lambda pt: pt.y()) if trk.state != "erfasst" else \
                QPointF((q[2].x() + q[3].x()) / 2, max(q[2].y(), q[3].y()))
            self._label(p, c, QPointF(card.boundingRect().center().x(), bottom.y() + 12), text, col)

    @staticmethod
    def _comets(p, path, col, now, size):
        lap = 2.4
        for phase in (0.0, 0.5):
            head = (now / lap + phase) % 1.0
            steps = 22
            for i in range(steps):
                t0 = (head - 0.16 * i / steps) % 1.0
                t1 = (head - 0.16 * (i + 1) / steps) % 1.0
                a = 1 - i / steps
                cc = QtGui.QColor(col)
                cc.setAlpha(int(255 * a))
                p.setPen(QtGui.QPen(cc, max(4.0, size * 0.04) * (0.4 + 0.6 * a), Qt.SolidLine, Qt.RoundCap))
                p.drawLine(path.pointAtPercent(t0), path.pointAtPercent(t1))
            glow = QtGui.QColor(col)
            glow.setAlpha(70)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            pt = path.pointAtPercent(head)
            r = max(5.0, size * 0.035)
            p.drawEllipse(pt, r, r)

    def _label(self, p, c, pos, text, col):
        p.setFont(font(12))
        fm = p.fontMetrics()
        w, h = fm.horizontalAdvance(text) + 22, fm.height() + 10
        x = min(max(c.left() + 6, pos.x() - w / 2), c.right() - w - 6)
        y = min(pos.y(), c.bottom() - h - 6)
        r = QRectF(x, y, w, h)
        p.setPen(QtGui.QPen(col, 1))
        p.setBrush(QtGui.QColor(11, 14, 26, 215))
        rad = look.ctrl_radius(h, "chip", self._area())
        p.drawRoundedRect(r, rad, rad)
        p.setPen(QtGui.QColor("#eef1ff"))
        p.drawText(r, Qt.AlignCenter, text)

    def _scan_hint(self, p, c, text):
        self._label(p, c, QPointF(c.center().x(), c.bottom() - 44), text, QtGui.QColor(scanlook.CYAN))

    def _paint_zoom_chip(self, p, c):
        """Small button at the top left: zoom level, click = zoom to the scan frame or back to 1×."""
        z = self.zoom()
        text = (f"⌕ {z:.1f}×  ·  " + (tr("whole image") if z > 1.01 else tr("zoom to frame"))).replace(".", ",")
        p.setFont(font(12))
        fm = p.fontMetrics()
        r = QRectF(c.left() + 10, c.top() + 10, fm.horizontalAdvance(text) + 22, fm.height() + 10)
        self._chip = r
        p.setPen(QtGui.QPen(QtGui.QColor(scanlook.CYAN), 1))
        p.setBrush(QtGui.QColor(11, 14, 26, 200))
        rad = look.ctrl_radius(r.height(), "chip", self._area())
        p.drawRoundedRect(r, rad, rad)
        p.setPen(QtGui.QColor("#eef1ff"))
        p.drawText(r, Qt.AlignCenter, text)

    def _paint_zone(self, p, c):
        z = self.zone_in_view()
        rec = self.ctrl.recognizer
        found = rec.stable_idx is not None and not rec.paused
        color = QtGui.QColor("#9dffb0") if found else QtGui.QColor(scanlook.CYAN)
        shade = QtGui.QPainterPath()
        shade.addRect(c)
        hole = QtGui.QPainterPath()
        hole.addRect(z)
        p.fillPath(shade.subtracted(hole), QtGui.QColor(0, 0, 0, 90))
        L = z.width() * 0.16
        p.setPen(QtGui.QPen(color, max(2.0, z.width() * 0.018), Qt.SolidLine, Qt.RoundCap))
        for cx, cy, dx, dy in ((z.left(), z.top(), 1, 1), (z.right(), z.top(), -1, 1),
                               (z.left(), z.bottom(), 1, -1), (z.right(), z.bottom(), -1, -1)):
            p.drawLine(QPointF(cx, cy), QPointF(cx + dx * L, cy))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy * L))
        if rec.paused:
            p.setFont(font(22, QtGui.QFont.Weight.Bold))
            p.setPen(scanlook.INK)
            p.drawText(z, Qt.AlignCenter, "PAUSE")

    # Scan frame by mouse (preview only)
    def _set_center(self, pos):
        fw, fh = self.frame_size()
        fx, fy = self.to_frame(pos)
        zone = self.ctrl.settings["zone"]
        zone[0] = min(1.0, max(0.0, fx / fw))
        zone[1] = min(1.0, max(0.0, fy / fh))
        self.ctrl.settings_changed()

    def overlay_button(self, pos):
        for rect, action, idx in reversed(self.ctrl.overlay.buttons):  # painted last = on top
            if rect.contains(pos):
                return action, idx
        return None

    # --- Mouse (from Qt Quick: position in the image, button as Qt.MouseButton) ---
    def press(self, pos, button):
        qr = getattr(self, "_qr_rect", None)
        if qr is not None and button == Qt.LeftButton and qr.contains(pos) and self.ctrl.frame_rgb is None:
            self._qr_shown = time.monotonic()   # show the QR code sharp for a minute
            if not getattr(self, "_qr_first", 0.0):
                self._qr_first = time.time()      # from now on the 20 s until the cable hint count
            self.update()
            return
        if self.stream and self.zone_edit and button == Qt.LeftButton and self.zone_in_view().contains(pos):
            self._drag = pos - self.zone_in_view().center()  # grab the scan frame (next to it: overlay as usual)
            self.cursor = "closed"
            return
        if self.stream:  # hover buttons: F / ⚙ / ✕ per row, Search, ⚙ on the info blocks
            win = self.ctrl.stream
            if any(panel.isVisible() for panel in win.panels) or self.ctrl.overlay.panel_open:
                win.close_all()  # a click next to it closes an open menu (and triggers nothing else)
                return
            hit = self.overlay_button(pos) if button == Qt.LeftButton else None
            if hit:
                win.overlay_action(*hit)
            return
        if button in (Qt.RightButton, Qt.MiddleButton):  # move the crop
            self._pan = (pos, list(self.ctrl.settings.get("preview_center", [0.5, 0.5])))
            self.cursor = "move"
            return
        if button != Qt.LeftButton:
            return
        if self._chip.contains(pos):
            self.set_zoom(1.0) if self.zoom() > 1.01 else self.fit_zone()
            return
        z = self.zone_in_view()
        self._drag = pos - z.center() if z.contains(pos) else QPointF(0, 0)
        self._set_center(pos - self._drag)
        self.cursor = "closed"

    def move(self, pos):
        if self.stream and self._drag is not None:
            self._set_center(pos - self._drag)
            self.update()
            return
        if self.stream:
            if self.zone_edit and self.zone_in_view().contains(pos):
                self.cursor = "open"
                return
            self.ctrl.overlay.hover = pos
            self.ctrl.overlay.moved = time.monotonic()
            self.cursor = "hand" if self.overlay_button(pos) else "arrow"
            return
        if self._pan is not None:
            start, center = self._pan
            c = self.canvas()
            z = self.zoom()
            d = pos - start
            self.ctrl.settings["preview_center"] = [center[0] - d.x() / c.width() / z,
                                                    center[1] - d.y() / c.height() / z]
            self._clamp_center()
            self.update()
            return
        if self._drag is not None:
            self._set_center(pos - self._drag)

    def leave(self):
        if self.stream:
            self.ctrl.overlay.hover = None

    def release(self, pos, button):
        if self._pan is not None:
            self._pan = None
            self.ctrl.settings_changed()
        self._drag = None
        if not self.stream or self.zone_edit:
            self.cursor = "open"

    def double_click(self, pos):
        if not self.stream and not self._chip.contains(pos):
            self.set_zoom(1.0)

    def wheel(self, pos, dy, mods=Qt.NoModifier):
        if self.stream and not (self.zone_edit and self.zone_in_view().contains(pos)):
            return
        if mods & Qt.ControlModifier and not self.stream:  # Ctrl + mouse wheel: zoom
            self.set_zoom(self.zoom() * (1.15 if dy > 0 else 1 / 1.15), pos)
            return
        zone = self.ctrl.settings["zone"]
        step = 0.01 if dy > 0 else -0.01
        zone[2] = round(min(0.6, max(0.08, zone[2] + step)), 3)
        self.ctrl.settings_changed()
        self.update()
