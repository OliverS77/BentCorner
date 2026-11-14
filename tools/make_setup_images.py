"""Images for the installer (0.9.9, lead 13.11.2026): the brand mark (logo rule 06.11.: app symbols = the mark; the long
single-line version doesn't fit the tall wizard image) from brand\\logo, for Inno's dark style – the light mark,
transparent around it (PNG with alpha), so it sits on whatever background the wizard draws.

  setup-small.png   110 × 110  the header image (WizardSmallImageFile, 55 × 55 at 200 %)
  setup-big.png     328 × 628  welcome/finish image (WizardImageFile, 164 × 314 at 200 %), the mark in the upper third

Without brand\\ nothing is written (forks: Inno's own images). A DEV build takes the red brand folder if given.

    <venv>\\python tools\\make_setup_images.py <out folder> [<brand folder>]   (QT_QPA_PLATFORM=offscreen is fine)
"""
import pathlib
import sys

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    out = pathlib.Path(sys.argv[1])
    brand = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "brand"
    if not (brand / "logo").is_dir():
        print("no brand\\logo – Inno's own images")
        return
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])   # noqa: F841 (SVG rendering)
    from ui import iconkit
    iconkit.folder = lambda: brand / "logo"
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / "setup-small.png"), iconkit.pixel_image(110, "dark"))
    big = np.zeros((628, 328, 4), np.uint8)
    mark = iconkit.pixel_image(256, "dark")
    y, x = 110, (328 - 256) // 2
    big[y:y + 256, x:x + 256] = mark
    cv2.imwrite(str(out / "setup-big.png"), big)
    print("setup images:", out)


if __name__ == "__main__":
    main()
