"""The long version of the logo (lockup) as SVG for places without our font – the README first (Oliver 06.11.2026:
horizontal lockup, light and dark, lettering as paths, from the app's own drawing).

Same geometry as qml/components/Lockup.qml and ui/iconkit.lockup_image: card (brand/logo/lockup-karte-*.svg)
1.2 × font size, moved −0.12 em to the left, gap 0.16 em, BENT°CORNER in Barlow Semi Condensed SemiBold, tracking
0.03 em, caps centred on the card, one colour (iconkit.INK). The lettering becomes outlines, so the files show the
same everywhere (GitHub, browsers) without the font.

    python tools/brand_lockup.py            -> brand/logo/lockup-lang-auf-dunkel.svg, lockup-lang-auf-hell.svg
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PX = 100.0   # font size in SVG units (the files scale freely)


def path_d(path):
    """QPainterPath -> SVG path data (move/line/cubic), coordinates rounded to 0.01."""
    from PySide6 import QtGui
    out, i, n = [], 0, path.elementCount()
    f = lambda v: f"{v:.2f}".rstrip("0").rstrip(".")   # noqa: E731
    while i < n:
        e = path.elementAt(i)
        if e.type == QtGui.QPainterPath.ElementType.MoveToElement:
            out.append(f"M{f(e.x)} {f(e.y)}")
        elif e.type == QtGui.QPainterPath.ElementType.LineToElement:
            out.append(f"L{f(e.x)} {f(e.y)}")
        elif e.type == QtGui.QPainterPath.ElementType.CurveToElement:
            c2, end = path.elementAt(i + 1), path.elementAt(i + 2)
            out.append(f"C{f(e.x)} {f(e.y)} {f(c2.x)} {f(c2.y)} {f(end.x)} {f(end.y)}")
            i += 2
        i += 1
    return "".join(out) + "Z"


def lockup_svg(on):
    from PySide6 import QtCore, QtGui
    from ui import iconkit
    from ui.brand import WORD
    font = QtGui.QFont("Barlow Semi Condensed")
    font.setWeight(QtGui.QFont.Weight.DemiBold)
    font.setPixelSize(int(PX))
    font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 0.03 * PX)
    fm = QtGui.QFontMetricsF(font)
    card_svg = (ROOT / "brand" / "logo" / f"lockup-karte-{'auf-dunkel' if on == 'dark' else 'auf-hell'}.svg").read_text("utf-8")
    card = 1.2 * PX
    x_text = card - 0.12 * PX + 0.16 * PX
    h = max(card, fm.height())
    text = QtGui.QPainterPath()
    text.addText(QtCore.QPointF(x_text, h / 2 + fm.capHeight() / 2), font, WORD)
    box = text.boundingRect()
    # the card's own group (its rotation and dog-ear), scaled from its 100 × 100 box into place
    group = re.search(r"<g .*</g>", card_svg, re.S).group(0)
    style = re.search(r"<style>(.*?)</style>", card_svg, re.S).group(1)
    left = -0.12 * PX
    w = max(x_text + fm.horizontalAdvance(WORD), box.right()) - left
    ink = iconkit.INK[on]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.2f} {h:.2f}" role="img" aria-label="Bent°Corner">\n'
            f'  <!-- Bent°Corner long version ({"on dark" if on == "dark" else "on light"}) – made by tools/brand_lockup.py from '
            f'the app\'s geometry; brand asset, all rights reserved (brand/BRAND.md); '
            f'lettering: Barlow Semi Condensed (SIL OFL 1.1, fonts/OFL-Barlow.txt) as outlines -->\n'
            f'  <style>{style}</style>\n'
            # everything moved right by the card's −0.12 em, so the picture starts at the card
            f'  <g transform="translate(0 {(h - card) / 2:.2f}) scale({card / 100:.4f})">{group}</g>\n'
            f'  <path fill="{ink}" transform="translate({-left:.2f} 0)" d="{path_d(text)}"/>\n'
            f'</svg>\n'), w, h


def main():
    from PySide6 import QtGui
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(["brand_lockup", "-platform", "offscreen"])
    fid = QtGui.QFontDatabase.addApplicationFont(str(ROOT / "fonts" / "BarlowSemiCondensed-SemiBold.ttf"))
    if fid < 0:
        sys.exit("font missing: fonts/BarlowSemiCondensed-SemiBold.ttf")
    for on, name in (("dark", "auf-dunkel"), ("light", "auf-hell")):
        svg, w, h = lockup_svg(on)
        out = ROOT / "brand" / "logo" / f"lockup-lang-{name}.svg"
        out.write_text(svg, "utf-8", newline="\n")
        print(out.relative_to(ROOT), f"{w:.0f} × {h:.0f}")
    del app


if __name__ == "__main__":
    main()
