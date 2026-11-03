"""Spiel-Symbole (eigene Pixel-Art, 16×16) nach assets/games/<spiel>.png zeichnen.

Bewusst KEINE Logos der Hersteller: je Spiel eine Andeutung (Magic: fünf Farben im Kreis, Pokémon: Blitz,
Yu-Gi-Oh: Auge, Lorcana: Funkelstern, Riftbound: Strudel im Ring). Gezeichnet mit Vektor-
Formen und danach hart gerastert (halbe Pixel werden voll oder verschwinden) – wie im Entwurf mit dem Nutzer.

    python tools/game_icons.py
"""
import math
import pathlib
import sys

from PySide6 import QtCore, QtGui

OUT = pathlib.Path(__file__).resolve().parent.parent / "assets" / "games"
sys.path.insert(0, str(OUT.parents[1]))   # the repo root: games.extra (private games bring their own icon)
C = {"W": "#f4efe4", "U": "#3f8cff", "B": "#8f6bd0", "R": "#e8433f", "G": "#3fbf5f", "Y": "#ffd23f", "O": "#ff8a2a",
     "D": "#c99a2e", "K": "#1c1c1c", "P": "#a06bff"}


def pt(x, y):
    return QtCore.QPointF(x, y)


def poly(p, pts, fill, stroke=None):
    p.setBrush(QtGui.QColor(fill))
    p.setPen(QtGui.QPen(QtGui.QColor(stroke), 1) if stroke else QtCore.Qt.NoPen)
    p.drawPolygon(QtGui.QPolygonF([pt(x, y) for x, y in pts]))


def dot(p, x, y, r, c):
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor(c))
    p.drawEllipse(pt(x, y), r, r)


def star(p, x, y, r1, r2, n, c):
    pts = []
    for i in range(n * 2):
        a = -math.pi / 2 + i * math.pi / n
        r = r2 if i % 2 else r1
        pts.append((x + math.cos(a) * r, y + math.sin(a) * r))
    poly(p, pts, c)


def pent(cx, cy, r, i):
    a = -math.pi / 2 + i * 2 * math.pi / 5
    return cx + math.cos(a) * r, cy + math.sin(a) * r


def spiral(p, color, width, turns, r0, step, phase):
    path = QtGui.QPainterPath()
    t = 0.0
    while t <= turns:
        r, a = r0 + t * step, t + phase
        q = pt(8 + math.cos(a) * r, 8 + math.sin(a) * r)
        path.lineTo(q) if t else path.moveTo(q)
        t += 0.1
    p.setBrush(QtCore.Qt.NoBrush)
    p.setPen(QtGui.QPen(QtGui.QColor(color), width))
    p.drawPath(path)


def mtg(p):
    for i, c in enumerate("WUBRG"):
        x, y = pent(8, 8.5, 5.4, i)
        dot(p, x, y, 2.4, C[c])


def pokemon(p):
    poly(p, [(10, 1), (3.5, 9), (7.5, 9), (5.5, 15), (12.5, 6.5), (8.5, 6.5)], C["Y"], C["O"])


def yugioh(p):
    poly(p, [(0.5, 8), (5, 3.5), (11, 3.5), (15.5, 8), (11, 12.5), (5, 12.5)], C["D"])
    poly(p, [(2.5, 8), (6, 5), (10, 5), (13.5, 8), (10, 11), (6, 11)], C["W"])
    dot(p, 8, 8, 2.6, C["P"])
    dot(p, 8, 8, 1.1, C["K"])


def lorcana(p):
    star(p, 8, 8, 7.9, 2.9, 4, C["D"])
    star(p, 8, 8, 6.4, 2.2, 4, C["Y"])
    star(p, 8, 8, 2.8, 1.2, 4, C["W"])


def riftbound(p):
    p.setBrush(QtCore.Qt.NoBrush)
    p.setPen(QtGui.QPen(QtGui.QColor("#ff7a1a"), 2.2))
    p.drawEllipse(pt(8, 8), 6.6, 6.6)
    for k in range(2):
        spiral(p, "#ffb15a", 1.5, 1.6 * math.pi, 0.8, 0.85, k * math.pi)
    dot(p, 8, 8, 1, "#fff1e0")


ICONS = {"mtg": mtg, "pokemon": pokemon, "yugioh": yugioh, "lorcana": lorcana, "riftbound": riftbound}
for _after, _key, _draw in __import__("games").extra("GAME_ICONS", ()):   # private games (games/extras.py)
    _keys = list(ICONS)
    _at = _keys.index(_after) + 1 if _after in _keys else len(_keys)
    ICONS = {**dict(list(ICONS.items())[:_at]), _key: (lambda p, d=_draw: d(p, sys.modules[__name__])),
             **dict(list(ICONS.items())[_at:])}


def render(draw):
    img = QtGui.QImage(16, 16, QtGui.QImage.Format_ARGB32)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    draw(p)
    p.end()
    for y in range(16):   # hart rastern
        for x in range(16):
            c = img.pixelColor(x, y)
            c.setAlpha(255 if c.alpha() >= 110 else 0)
            img.setPixelColor(x, y, c)
    return img


def main():
    QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    for key, draw in ICONS.items():
        render(draw).save(str(OUT / f"{key}.png"))
        print("ok", key)


if __name__ == "__main__":
    main()
