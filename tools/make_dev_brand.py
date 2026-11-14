"""The red brand folder of the DEV version (Oliver 13.11.2026, colour approved by Gordon): a copy of brand/ in which the
mark and the lockups carry ui/iconkit.DEV_RED – the same form, only the colour. build.ps1 packs it instead of brand/
for every work build WITHOUT -Ship; a Ship build always packs brand/ itself (tools/check_package.py checks that).

- pixel images (mark-hell-*.png on dark, mark-dunkel-*.png on light): iconkit.dev_tint
- SVGs mark-* / lockup-*: every colour swapped for iconkit.dev_tint_hex (the loading image is not the mark: unchanged)
- icon.ico from the red images (iconkit.write_ico), icon.png likewise; DEV.txt marks the folder

    <venv>\\python tools\\make_dev_brand.py <out folder>     (needs Qt for the SVGs: QT_QPA_PLATFORM=offscreen is fine)
"""
import pathlib
import re
import shutil
import sys

import cv2

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def main():
    out = pathlib.Path(sys.argv[1])
    src = ROOT / "brand"
    if not (src / "logo").is_dir():
        sys.exit("brand/logo missing – a build without the brand keeps its placeholders (nothing to colour)")
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])   # noqa: F841 (SVG rendering)
    from ui import iconkit
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)
    logo = out / "logo"
    for f in sorted(logo.glob("mark-*.png")):
        on = "dark" if f.name.startswith("mark-hell-") else "light"
        img = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        cv2.imwrite(str(f), iconkit.dev_tint(img, on))
    for f in sorted(logo.glob("*.svg")):
        if not f.name.startswith(("mark-", "lockup-")):
            continue
        on = "dark" if "auf-dunkel" in f.name else "light"
        text = f.read_text("utf-8")
        f.write_text(HEX.sub(lambda m: iconkit.dev_tint_hex(m.group(0), on), text), "utf-8")
    iconkit.folder = lambda: logo   # the icon from the red images
    iconkit.write_ico(out / "icon.ico")
    cv2.imwrite(str(out / "icon.png"), iconkit.pixel_image(256))
    (out / "DEV.txt").write_text(f"DEV brand – {iconkit.DEV_RED} (tools/make_dev_brand.py). Never in a Ship build.\n",
                                 "utf-8")
    print("DEV brand:", out)


if __name__ == "__main__":
    main()
