"""Scalper Invaders – mini game (first-run setup, while the data loads, and easter egg under Settings → Game).

Your card back is the ship. From above fall boosters (collect +1, golden +5) and scalpers (shoot down +1,
with a "Sold out" sign 2 hits = +2). If a scalper reaches the line above the ship: −1 of 3 lives. Boosters that
fall past are simply gone. Faster and denser over time. The game is played in qml/components/ScalperGame.qml;
only the pixel images (once, as PNG data) and the high score (settings["game_best"]) are made here.

Controls, all at once: mouse left/right · A/D · ←/→ move; left click · space · W · ↑ shoot.
"""
import base64

from PySide6 import QtCore, QtGui

PACK = ["k.k.k.k.k.", "kkkkkkkkkk", "hsssssssss", "hsssssssss", "hsBBBBBBss", "hsBwwwwBss", "hsBwBBwBss",
        "hsBwwwwBss", "hsBBBBBBss", "hsssssssss", "hsssssssss", "hsssssssss", "kkkkkkkkkk", "k.k.k.k.k."]
BANDS = ("#3987e5", "#d95926", "#199e70")
SCALPER = [".....hhhh.......", "....hhhhhh......", "...gggggggg.....", "....hhhhhh......", ".....hmmh.......",
           "....dddddd......", "...dddddddd.....", "...dd.dd.ddtcccc", "...dd.dd.dd.cpqc", ".....dd.....cqpc",
           "....d..d....cccc", "...dd..dd....o.o"]
SCALE = 3
_cache = {}


def _png_url(img):
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(buf.data())).decode()


def _sprite(rows, pal):
    img = QtGui.QImage(len(rows[0]) * SCALE, len(rows) * SCALE, QtGui.QImage.Format_ARGB32)
    img.fill(0)
    p = QtGui.QPainter(img)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in pal:
                p.fillRect(x * SCALE, y * SCALE, SCALE, SCALE, QtGui.QColor(pal[ch]))
    p.end()
    return _png_url(img)


def sprites():
    """{"packs": [3 colours], "gold", "scalper"} as data: URLs (computed once)."""
    if not _cache:
        _cache["packs"] = [_sprite(PACK, {"k": "#7a7a7e", "s": "#bdbdc1", "h": "#ededed", "B": b, "w": "#ededed"})
                           for b in BANDS]
        _cache["gold"] = _sprite(PACK, {"k": "#a8792a", "s": "#e3c063", "h": "#fff1c4", "B": "#7b4dd8", "w": "#fff8e0"})
        _cache["scalper"] = _sprite(SCALPER, {"h": "#d9b38c", "g": "#0e0e0e", "m": "#7a3b2a", "d": "#5a5a5e",
                                              "t": "#9a9a9e", "c": "#a0a0a4", "p": "#3987e5", "q": "#d95926",
                                              "o": "#3a3a3d"})
    return dict(_cache)


def ship_url(back):
    """Your card back as the ship (42 × 60 pixels, rounded corners)."""
    from system import userprofile
    img = userprofile.back_image(back, 60, border=None)
    return _png_url(img)


def node(ui, settings, on_change=None):
    """Game as a form building block (qform): card back from the profile, high score from the settings."""
    from system import userprofile
    prof = userprofile.get(settings) or {}

    def act(v):
        if v and v[0] == "best" and int(v[1]) > int(settings.get("game_best") or 0):
            settings["game_best"] = int(v[1])
            if on_change:
                on_change()
    return {"t": "game", "id": ui._id(act), "ship": ship_url(prof.get("back") or userprofile.DEFAULT_BACK),
            "best": int(settings.get("game_best") or 0), "sprites": sprites()}
