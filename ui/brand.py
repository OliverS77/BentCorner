"""The brand assets in brand/ – logo, app icons, the logo card of the loading animation (loadcard.json). They are © Oliver
Schunn, all rights reserved, NOT under the GPL (brand/BRAND.md, LICENSE § 7(e), legal 03.11.2026): only unmodified
official builds may use them. The program builds and runs without the folder – forks get neutral placeholders (a plain
grey card instead of the mark, the name as text, a random first loading card); the code that draws them stays GPL.

    present()        brand/ with the logo is there
    logo(name)       path of a logo file, or None
    load_card()      {"corner", "fold", "tilt"} of the first loading card, or None (then it is random like the others)
    expose(context)  the same for QML: context property "brandInfo" (Loading.qml, Lockup.qml, Main.qml)
    NAME, WORD       the display name (one place for it) and its lettering
"""
import json
import pathlib
import sys

# The display name – the ONE place (legal 03.11.2026): the lockup (Lockup.qml, iconkit), the window title, the
# launcher's splash and the trade ticket read it, so a fork changes its name here. The attribution under the GPL
# additional terms (ui/qsetpages.GPL_ATTRIBUTION, "Based on Bent°Corner – …") is separate and never changes.
NAME = "Bent°Corner"
WORD = NAME.upper()   # the lettering of the lockup: BENT°CORNER


def folder():
    """brand/ next to the program (in the exe: _MEIPASS, in development: the project folder)."""
    return pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1])) / "brand"


def present():
    return (folder() / "logo").is_dir()


def logo(name):
    p = folder() / "logo" / name
    return p if p.is_file() else None


def load_card():
    try:
        d = json.loads((folder() / "loadcard.json").read_text("utf-8"))
        return {"corner": int(d["corner"]) % 4, "fold": float(d["fold"]), "tilt": float(d["tilt"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def info():
    """For QML: logo present, and the first loading card as [corner, fold, tilt, 1] ([0, 0, 0, 0]: random)."""
    card = load_card()
    return {"logo": present(), "name": NAME, "word": WORD,
            "loadCard": [card["corner"], card["fold"], card["tilt"], 1.0] if card else [0.0, 0.0, 0.0, 0.0]}


def expose(context):
    context.setContextProperty("brandInfo", info())
