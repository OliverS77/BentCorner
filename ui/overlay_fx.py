"""Effects of the stream overlay (mixin of overlay_paint.Overlay): sparkles, fireworks, hearts, orbit around the
Biggest Hit. Moved from app.py."""
import math
import random

from PySide6 import QtGui
from PySide6.QtCore import QPointF, Qt

from ui import scanlook
from ui.scanlook import ease_in_out, ease_out, heart_path, star


class OverlayFx:
    """Effects of the stream overlay – uses Overlay's state (self.settings, self.card …)."""

    # --- Effects around the Biggest Hit (u = 0..1) ---
    def _fx_sparkles(self, p, rect, u, seed, n=12, spread=24.0):
        """Soft stars: fade in/out slowly, gently rotating and drifting outwards a little."""
        rnd = random.Random(seed)
        c = rect.center()
        for _ in range(n):
            side, f = rnd.random() * 4, rnd.random()
            if side < 1:
                pt = QPointF(rect.left() + f * rect.width(), rect.top() - rnd.random() * spread)
            elif side < 2:
                pt = QPointF(rect.right() + rnd.random() * spread, rect.top() + f * rect.height())
            elif side < 3:
                pt = QPointF(rect.left() + f * rect.width(), rect.bottom() + rnd.random() * spread)
            else:
                pt = QPointF(rect.left() - rnd.random() * spread, rect.top() + f * rect.height())
            delay = rnd.random() * 0.4
            v = (u - delay) / 0.6
            if not 0 < v < 1:
                continue
            e = math.sin(math.pi * v) ** 2  # soft fade in and out
            d = QPointF(pt.x() - c.x(), pt.y() - c.y())
            norm = math.hypot(d.x(), d.y()) or 1
            pos = QPointF(pt.x() + d.x() / norm * 10 * v, pt.y() + d.y() / norm * 10 * v)
            col = QtGui.QColor([scanlook.INK, scanlook.CYAN, scanlook.MAGENTA, scanlook.GOLD][rnd.randrange(4)])
            col.setAlpha(int(235 * e))
            size = (6 + rnd.random() * 6) * (0.4 + 0.6 * e)
            p.save()
            p.translate(pos)
            p.rotate(45 * v + rnd.random() * 30)
            glow = QtGui.QRadialGradient(QPointF(0, 0), size * 1.6)
            gc = QtGui.QColor(col)
            gc.setAlpha(int(70 * e))
            glow.setColorAt(0, gc)
            gc.setAlpha(0)
            glow.setColorAt(1, gc)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(0, 0), size * 1.6, size * 1.6)
            star(p, QPointF(0, 0), size, col)
            p.restore()

    def _fx_fireworks(self, p, rect, u, seed):
        rnd = random.Random(seed)
        total = self.IDLE_DUR["Feuerwerk"]
        t = u * total
        for i in range(3):
            start = i * 0.55
            lt = t - start
            if lt < 0:
                continue
            bx = rect.left() + rect.width() * (0.2 + 0.3 * i) + rnd.uniform(-20, 20)
            peak = QPointF(bx + rnd.uniform(-30, 30), rect.top() - rnd.uniform(20, 70))
            col = QtGui.QColor([scanlook.MAGENTA, scanlook.CYAN, scanlook.GOLD][i % 3])
            if lt < 0.45:  # rocket rises with a trail
                v = ease_out(lt / 0.45)
                pos = QPointF(bx + (peak.x() - bx) * v, rect.bottom() + (peak.y() - rect.bottom()) * v)
                trail = QtGui.QLinearGradient(pos, QPointF(pos.x(), pos.y() + 40))
                cc = QtGui.QColor(col)
                trail.setColorAt(0, cc)
                cc.setAlpha(0)
                trail.setColorAt(1, cc)
                p.setPen(QtGui.QPen(QtGui.QBrush(trail), 3, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(pos, QPointF(pos.x(), pos.y() + 40))
            else:          # explosion: ring of sparks with a little gravity
                v = (lt - 0.45) / 1.0
                if v >= 1:
                    continue
                e = ease_out(v)
                for j in range(18):
                    ang = j / 18 * 2 * math.pi + i
                    r = 55 * e
                    pt = QPointF(peak.x() + math.cos(ang) * r, peak.y() + math.sin(ang) * r + 25 * v * v)
                    cc = QtGui.QColor(col if j % 3 else scanlook.INK)
                    cc.setAlpha(int(255 * (1 - v)))
                    p.setPen(Qt.NoPen)
                    p.setBrush(cc)
                    p.drawEllipse(pt, 2.8 * (1 - v) + 0.8, 2.8 * (1 - v) + 0.8)
                if v < 0.25:  # short flash in the centre
                    cc = QtGui.QColor(scanlook.INK)
                    cc.setAlpha(int(200 * (1 - v / 0.25)))
                    p.setBrush(cc)
                    p.drawEllipse(peak, 8 * (1 - v / 0.25) + 2, 8 * (1 - v / 0.25) + 2)

    def _fx_hearts(self, p, rect, u, seed, back):
        """Heart balloons rise from below (behind/in front of the card) and fade at the top."""
        rnd = random.Random(seed)
        for i in range(5):
            behind = i % 2 == 1
            f = rnd.uniform(0.12, 0.88)
            size = rnd.uniform(15, 22)
            if behind != back:
                continue
            delay = i * 0.1
            v = (u - delay) / 0.6
            if not 0 < v < 1:
                continue
            rise = ease_in_out(v)
            x0 = rect.left() + rect.width() * f + 14 * math.sin(v * 4 + i)
            y0 = rect.bottom() + 30 - (rect.height() + 110) * rise
            alpha = min(1.0, v / 0.15) * min(1.0, (1 - v) / 0.35)
            col = QtGui.QColor(["#ff5bd6", "#ff8fb8", "#ff4f7a"][i % 3])
            col.setAlpha(int(235 * alpha * (0.75 if behind else 1)))
            string = QtGui.QPainterPath(QPointF(x0, y0 + size * 0.35))
            string.quadTo(QPointF(x0 + 6 * math.sin(v * 6 + i), y0 + size * 1.2), QPointF(x0 - 2, y0 + size * 2.1))
            sc = QtGui.QColor(238, 241, 255, int(120 * alpha))
            p.setPen(QtGui.QPen(sc, 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(string)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawPath(heart_path(x0, y0, size))
            hl = QtGui.QColor(255, 255, 255, int(110 * alpha))  # small highlight like on the balloon
            p.setBrush(hl)
            p.drawEllipse(QPointF(x0 - size * 0.35, y0 - size * 0.45), size * 0.14, size * 0.1)

    def _fx_orbit(self, p, rect, u, back):
        env = min(1.0, u / 0.15) * min(1.0, (1 - u) / 0.2)
        c = rect.center()
        rx, ry = rect.width() * 0.72, rect.height() * 0.2
        for i, col in enumerate((scanlook.CYAN, scanlook.MAGENTA, scanlook.GOLD)):
            for trail in range(6):
                ang = (u * 2.4 + i / 3) * 2 * math.pi - trail * 0.12
                behind = math.sin(ang) < 0
                if behind != back:
                    continue
                pt = QPointF(c.x() + math.cos(ang) * rx, c.y() + math.sin(ang) * ry + 30 * math.cos(ang + i))
                cc = QtGui.QColor(col)
                cc.setAlpha(int(230 * env * (1 - trail / 6) * (0.55 if behind else 1)))
                p.setPen(Qt.NoPen)
                p.setBrush(cc)
                r = (9 - trail * 1.2) * (0.8 if behind else 1)
                p.drawEllipse(pt, r, r)
