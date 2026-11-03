"""App icon: the Bent°Corner mark (Oliver, 30.10.2026 – labs/logo-2026-10-30/LIESMICH.md), one form per size:

  16 / 20 / 24 px   corner folded back at 45°, big dot – 2-bit pixel images (brand/logo/mark-*-<px>.png), never scaled
  32 / 40 / 48 px   card with grey dog-ear + full dot (mark-32 / mark-48 SVG; at 32 the dog-ear is 1 px larger)
  from 64 px        card with dog-ear + ring (mark SVG) – the usual logo

Each form exists for a dark background (light mark, "auf-dunkel" / "mark-hell") and a light one (dark mark). The
window and tray icon follow the Windows taskbar (light or dark); icon.ico/icns – fixed in the .exe – use ICO_ON.
The mark is a brand asset (brand/, ui/brand.py): without the folder every size is a neutral placeholder – a plain grey
card – and the long version is the name alone.
"""
import pathlib
import struct
import subprocess
import sys
import tempfile

import cv2
import numpy as np

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)  # what Windows queries for taskbar, Explorer, Alt+Tab etc.
ICNS_SIZES = (16, 32, 64, 128, 256, 512, 1024)  # macOS iconset: 16/32/128/256/512 at 1x + @2x (32/64/256/512/1024)
PIXEL = (16, 20, 24)   # hand-made pixel images
ICO_ON = "light"       # background the fixed icon (.ico/.icns) is made for: Explorer and Windows 11 default to light


def folder():
    from ui import brand
    return brand.folder() / "logo"


def source_path():
    """Preview image of the logo (brand/icon.png) – written by `python iconkit.py`."""
    return folder().parent / "icon.png"


PLACEHOLDER = {"dark": (160, 154, 154), "light": (102, 96, 96)}   # BGR (bluish grey like the loading card)


def placeholder_image(size, on=None):
    """Without brand/: a plain grey card (no dog-ear, no dot) as BGRA – neutral, nobody's mark."""
    img = np.zeros((size, size, 4), np.uint8)
    w, h = max(2, round(size * 0.62)), max(2, round(size * 0.86))
    x, y = (size - w) // 2, (size - h) // 2
    r = max(1, round(size * 0.07))
    col = (*PLACEHOLDER[on or ICO_ON], 255)
    cv2.rectangle(img, (x + r, y), (x + w - 1 - r, y + h - 1), col, -1)
    cv2.rectangle(img, (x, y + r), (x + w - 1, y + h - 1 - r), col, -1)
    for cx, cy in ((x + r, y + r), (x + w - 1 - r, y + r), (x + r, y + h - 1 - r), (x + w - 1 - r, y + h - 1 - r)):
        cv2.circle(img, (cx, cy), r, col, -1, cv2.LINE_AA)
    return img


def _svg_name(size, on):
    side = "auf-dunkel" if on == "dark" else "auf-hell"
    form = "mark-32" if size < 40 else "mark-48" if size < 64 else "mark"
    return f"{form}-{side}.svg"


def _render_svg(path, size):
    """SVG -> QImage size × size (vector, no bitmap scaling)."""
    from PySide6 import QtCore, QtGui, QtSvg
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    QtSvg.QSvgRenderer(str(path)).render(p, QtCore.QRectF(0, 0, size, size))
    p.end()
    return img


def _qimage_to_bgra(img):
    from PySide6 import QtGui
    img = img.convertToFormat(QtGui.QImage.Format_RGBA8888)
    arr = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 4]
    return cv2.cvtColor(arr.reshape(img.height(), img.width(), 4).copy(), cv2.COLOR_RGBA2BGRA)


def pixel_image(size, on=None):
    """The mark at size × size as BGRA. on: "dark"/"light" background (default ICO_ON)."""
    on = on or ICO_ON
    if not folder().is_dir():
        return placeholder_image(size, on)
    if size in PIXEL:
        img = cv2.imread(str(folder() / f"mark-{'hell' if on == 'dark' else 'dunkel'}-{size}.png"), cv2.IMREAD_UNCHANGED)
        if img is not None and img.shape[:2] == (size, size):
            return img if img.shape[2] == 4 else cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return _qimage_to_bgra(_render_svg(folder() / _svg_name(size, on), size))


def write_ico(path, sizes=SIZES, on=None):
    """Windows .ico with all sizes (each embedded as PNG, supported since Windows Vista)."""
    blobs = [cv2.imencode(".png", pixel_image(s, on))[1].tobytes() for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, blob in zip(sizes, blobs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    pathlib.Path(path).write_bytes(head + entries + b"".join(blobs))


def write_icns(path):
    """macOS .icns via the system tool `iconutil` (only available on macOS)."""
    mapping = {"icon_16x16.png": 16, "icon_16x16@2x.png": 32, "icon_32x32.png": 32, "icon_32x32@2x.png": 64,
               "icon_128x128.png": 128, "icon_128x128@2x.png": 256, "icon_256x256.png": 256,
               "icon_256x256@2x.png": 512, "icon_512x512.png": 512, "icon_512x512@2x.png": 1024}
    with tempfile.TemporaryDirectory() as tmp:
        iconset = pathlib.Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for name, size in mapping.items():
            cv2.imencode(".png", pixel_image(size))[1].tofile(str(iconset / name))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(path)], check=True)


def qpixmap(size, on=None):
    from PySide6 import QtGui
    img = cv2.cvtColor(pixel_image(size, on), cv2.COLOR_BGRA2RGBA)
    q = QtGui.QImage(img.data, size, size, size * 4, QtGui.QImage.Format_RGBA8888).copy()
    return QtGui.QPixmap.fromImage(q)


def taskbar_on():
    """Background of the Windows taskbar: "light" or "dark" (Settings → Personalization → Colors, "Windows mode")."""
    if sys.platform != "win32":
        return ICO_ON
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return "light" if winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] else "dark"
    except OSError:
        return ICO_ON


def qicon(on=None):
    """Window/tray icon with all sizes so Qt never has to scale (blurrily) by itself – for the taskbar's colour."""
    from PySide6 import QtGui
    on = on or taskbar_on()
    icon = QtGui.QIcon()
    for s in SIZES:
        icon.addPixmap(qpixmap(s, on))
    return icon


_follow = {"on": None, "timer": None, "listeners": []}


def follow_system(app):
    """Window and tray icon follow Windows while running (Settings → Personalization → Colors): on every colour-scheme
    change Qt reports and otherwise every 5 s (a local registry read) – light taskbar: dark mark, dark: light mark."""
    from PySide6 import QtCore
    _follow["on"] = taskbar_on()
    app.setWindowIcon(qicon(_follow["on"]))   # applies to all windows that have no icon of their own

    def check():
        on = taskbar_on()
        if on == _follow["on"]:
            return
        _follow["on"] = on
        icon = qicon(on)
        app.setWindowIcon(icon)
        for fn in list(_follow["listeners"]):
            try:
                fn(icon)
            except RuntimeError:   # its object is gone (tray closed)
                _follow["listeners"].remove(fn)
    t = QtCore.QTimer(app, interval=5000, timeout=check)
    t.start()
    _follow["timer"] = t
    hints = app.styleHints()
    if hasattr(hints, "colorSchemeChanged"):
        hints.colorSchemeChanged.connect(lambda *_: QtCore.QTimer.singleShot(300, check))


def on_icon_change(fn):
    """fn(QIcon) when the taskbar switches light/dark (tray icon)."""
    _follow["listeners"].append(fn)


INK = {"dark": "#f2f2f3", "light": "#161618"}   # mark and lettering on a dark / light background
from ui.brand import WORD  # noqa: E402  the lettering: the one display name


def lockup_image(px, on="dark", k=2):
    """The long version (word-image mark) as QImage at k× sharpness: card with dog-ear, no dot/ring
    (lockup-karte SVG), next to it BENT°CORNER in Barlow Semi Condensed SemiBold, one colour (the ° is in the name).
    Without brand/ only the name (no card).
    px = font size in points; card 1.2 × font size, gap 0.16 em, card moved −0.12 em to the left, tracking 0.03 em.
    -> (QImage, width, height) – width/height in points."""
    from PySide6 import QtCore, QtGui, QtSvg
    font = QtGui.QFont("Barlow Semi Condensed")
    font.setWeight(QtGui.QFont.Weight.DemiBold)
    font.setPixelSize(round(px * k))
    font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 0.03 * px * k)
    fm = QtGui.QFontMetricsF(font)
    svg = folder() / f"lockup-karte-{'auf-dunkel' if on == 'dark' else 'auf-hell'}.svg"
    card = 1.2 * px * k if svg.is_file() else 0.0
    x_text = card - 0.12 * px * k + 0.16 * px * k if card else 0.0
    w = x_text + fm.horizontalAdvance(WORD)
    h = max(card, fm.height())
    img = QtGui.QImage(int(w + 1), int(h + 1), QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing)
    if card:
        QtSvg.QSvgRenderer(str(svg)).render(p, QtCore.QRectF(-0.12 * px * k, (h - card) / 2, card, card))
    p.setFont(font)
    p.setPen(QtGui.QColor(INK[on]))
    p.drawText(QtCore.QPointF(x_text, h / 2 + fm.capHeight() / 2), WORD)   # caps centred on the card
    p.end()
    return img, w / k, h / k


def draw_lockup(p, right, bottom, px, on="dark", opacity=1.0):
    """The long version into a picture being painted (share images): right/bottom = where it ends."""
    from PySide6 import QtCore
    img, w, h = lockup_image(px, on)
    p.save()
    p.setOpacity(opacity)
    p.drawImage(QtCore.QRectF(right - w, bottom - h, w, h), img)
    p.restore()


if __name__ == "__main__":  # python -m ui.iconkit [target] -> app icon (default brand/icon.ico + brand/icon.png)
    from PySide6 import QtGui
    _app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(["iconkit", "-platform", "offscreen"])
    from ui import brand
    name = "icon.icns" if sys.platform == "darwin" else "icon.ico"
    # without brand/ (forks): the placeholder icon into the build folder – nothing is written outside it
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else brand.folder() / name
    out.parent.mkdir(parents=True, exist_ok=True)
    (write_icns if sys.platform == "darwin" else write_ico)(out)
    if brand.present() and len(sys.argv) == 1:
        cv2.imencode(".png", pixel_image(512))[1].tofile(str(source_path()))
    print("geschrieben:", out, out.stat().st_size, "Bytes")
