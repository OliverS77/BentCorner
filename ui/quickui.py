"""Qt Quick in Bent°Corner (since v0.5.0) – the UI moves step by step from Qt Widgets to Qt Quick:
animations run there on the GPU. Each page switches only once the new one is at least as good as the old one.

Here lives what all Qt Quick parts need:
  qml_dir()        folder with the .qml files (also in the .exe)
  palette()        colours from the skin (look.py) for QML – as the context property "T"
  quick_widget()   put a QML file as a widget into the existing UI (transition period)
  file_url()       local path -> URL for Image { source }

When idle, Qt Quick draws nothing – load only arises while something is moving.
"""
import functools
import logging
import pathlib
import sys

from PySide6 import QtCore, QtGui, QtQuickWidgets

from ui import brand
from ui import look

log = logging.getLogger("bentcorner")


@functools.cache
def qml_dir():
    """The program's qml folder – fixed while it runs, so resolved once (it was asked per binder tile)."""
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1]))
    return base / "qml"


def palette():
    """All colours of the current look (grey/neon + custom skin colours) and the fonts."""
    out = {k: look.color(k) for k, _, _ in look.PALETTE}
    out["font"] = look.text_font().family()
    out["display"] = look.display_font().family()
    out["gray"] = look.is_gray()
    light = look.is_light()
    out["light"] = light
    # fixed contrast colours (active chips, check marks, keys) – inverted in the light look
    out["top"] = "#000000" if light else "#ffffff"         # strongest text (selected row)
    out["hi"] = "#1c1c1e" if light else "#f2f2f2"          # "on": light surface (dark in the light look)
    out["onHi"] = "#f2f2f2" if light else "#111111"        # text on "on"
    out["off"] = "#c9c9cd" if light else "#3a3a3d"          # "off" (seg, indicator lights)
    out["keyFace"] = "#e6e6e8" if light else "#141416"     # key lab: surface, light top left, shadow bottom right
    out["keyLight"] = "#ffffff" if light else "#202023"
    out["keyDark"] = "#bfbfc4" if light else "#060607"
    out["inkOn"] = "#141416" if light else "#e2e2e2"        # key text: active / normal / under the mouse
    out["inkOff"] = "#4a4a4f" if light else "#b4b4b4"
    out["inkHover"] = "#000000" if light else "#f4f4f4"
    out["btnRadius"] = look.ctrl_radius(34, "button")
    out["panelRadius"] = look.panel_radius(300, 300)
    out["tile"] = TILE
    return out


# Scan page tiles: ALL spacings in one place (fine-tune here – QML reads T.tile.*). Pixels at 100 % scale.
TILE = {
    "bar": 56,          # height of both bars (nav at the top, quick access at the bottom) – the tiles live between them
    "margin": 16,       # grid edge: window border -> first column / row
    "gap": 10,          # space between two tiles
    "pad": 14,          # inner padding of a tile (left/right)
    "padB": 10,         # inner padding at the bottom
    "head": 30,         # head row (grip · title · Stream chip)
    "radius": 16,       # corner radius of a tile
    "row": 34,          # one line in a list (cards) – thumbnail height follows
    "line": 1,          # divider lines inside a tile
    "glass": 0.62,      # tile background opacity – over the frosted camera image (ScanPage: frost)
    "frost": True,      # frosted glass under the tiles (one blur of a quarter-size image per frame, GPU)
    "glassStream": 0.74,
    "fadeMs": 260,      # bars sliding/fading (stream view)
    "wakeMs": 3000,     # stream view: controls stay this long after the last mouse move
}


def file_url(path):
    return QtCore.QUrl.fromLocalFile(str(path)).toString() if path else ""


def quick_widget(name, context=None, parent=None):
    """QML file qml/<name> as a QQuickWidget. context: {name: object} as context properties (plus always "T")."""
    w = QtQuickWidgets.QQuickWidget(parent)
    w.setResizeMode(QtQuickWidgets.QQuickWidget.SizeRootObjectToView)
    w.setAttribute(QtCore.Qt.WA_AlwaysStackOnTop, False)
    w.setClearColor(QtGui.QColor(look.background()))
    ctx = w.rootContext()
    ctx.setContextProperty("T", palette())
    brand.expose(ctx)   # logo and the loading logo card (ui/brand.py)
    for key, obj in (context or {}).items():
        ctx.setContextProperty(key, obj)
    w.statusChanged.connect(lambda st: _report(w, name) if st == QtQuickWidgets.QQuickWidget.Error else None)
    w.setSource(QtCore.QUrl.fromLocalFile(str(qml_dir() / name)))
    return w


def _report(w, name):
    for err in w.errors():
        log.error("QML %s: %s", name, err.toString())


