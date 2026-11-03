"""Appearance in one place: fonts, font size, corners and colors – without widgets.

Qt Quick (quickui.palette) and everything drawn get colors, fonts and roundings from here. The default colors
are in PALETTE; the base look ("grau"/"neon") and custom colors (Settings → Skin) sit on top.
Per page: cfg["pages"][area] = {"colors", "radius_ctrl", "radius_panel", "elements", "fx"}.

If something changes live (color, background), look reports it to listeners (listen) – the old widget stylesheets
(theme.py) then recalculate.
"""
import pathlib
import shutil
import sys
import zipfile

from PySide6 import QtGui

from scanner.common import DATA

_listeners = []


def listen(fn):
    """fn(kind, key=None) on live changes: "palette", "background", "area" (with area)."""
    _listeners.append(fn)


def _notify(kind, key=None):
    for fn in list(_listeners):
        try:
            fn(kind, key)
        except Exception:  # noqa: BLE001 – a listener must not break the setting
            import logging
            logging.getLogger(__name__).exception("Applying appearance live")


FONT_DIR = DATA / "schriften"
TEXT_FAMILY, DISPLAY_FAMILY = "Inter 18pt", "Barlow Semi Condensed"
DEFAULTS = {"font_text": TEXT_FAMILY, "font_text_weight": 300, "font_display": DISPLAY_FAMILY,
            "font_display_weight": 500, "font_scale": 100, "radius_panel": 5.0, "radius_panel_unit": "%",
            "radius_ctrl": 9.0, "radius_ctrl_unit": "px", "colors": {}, "elements": {}, "elements_saved": {}, "skin": {},
            "bar_width": 7, "fx": {}, "pages": {}, "look": "grau"}  # elements_saved: own values of disabled elements (restored on re-enable)
PANEL_NOMINAL = 300  # shorter side of a "typical" surface, for % values in stylesheets
# (key, label, default color)
PALETTE = [("accent", "Accent (glow, selection)", "#62f2ff"), ("accent_deep", "Accent dark (active areas)", "#1f5f6b"),
           ("bg", "Background", "#0b0e1a"), ("surface", "Surface", "#111527"), ("surface2", "Surface light", "#161b30"),
           ("button", "Buttons", "#1b2033"), ("line", "Lines & borders", "#2c3352"), ("line2", "Borders light", "#3a4260"),
           ("text", "Text", "#eef1ff"), ("text2", "Text muted", "#aab1c8"), ("muted", "Text grey", "#8a91a8"),
           ("dim", "Text dark grey", "#6c7390"), ("pink", "Hit / pink", "#ff5bd6"), ("amber", "Amber", "#ffb347"),
           ("green", "Green (good)", "#46d17a"), ("red", "Red (error)", "#ff4d5e")]
# Base looks: "grau" (default) = dark greyscale without accent color, highlight light grey, controls tactile
# (neumorphism); "neon" = the former look (cyan accent). Custom colors (cfg["colors"]) sit on top.
LOOKS = [("grau", "Gray (default)"), ("hell", "Light"), ("neon", "Neon (classic)")]
GRAY = {"accent": "#e4e4e4", "accent_deep": "#3b3b3b", "bg": "#0a0a0a", "surface": "#121212", "surface2": "#181818",
        "button": "#1d1d1d", "line": "#2a2a2a", "line2": "#3d3d3d", "text": "#ededed", "text2": "#b5b5b5",
        "muted": "#8e8e8e", "dim": "#686868", "pink": "#ffffff", "amber": "#c4c4c4", "green": "#8fb89a",
        "red": "#d48a8a"}
# Light: the same greyscale world, inverted – light surfaces, dark text, dark highlight
LIGHT = {"accent": "#2a2a2e", "accent_deep": "#c8c8cc", "bg": "#e9e9eb", "surface": "#f1f1f2", "surface2": "#f8f8f9",
         "button": "#e4e4e6", "line": "#d2d2d6", "line2": "#bcbcc1", "text": "#141416", "text2": "#3d3d42",
         "muted": "#6a6a70", "dim": "#8e8e94", "pink": "#141416", "amber": "#5c5c60", "green": "#3f7a50",
         "red": "#b04545"}
# Fixed UI colors outside the palette (surfaces, gradients, hover borders …) -> grey. Content colors stay:
# mana symbols, rarities, card backs.
GRAY_LOOSE = {"#0f1322": "#101010", "#141a30": "#171717", "#3f7f8f": "#5c5c5c", "#1b2238": "#1b1b1b",
              "#11162a": "#131313", "#5a6078": "#5e5e5e", "#4a5270": "#4f4f4f", "#39415f": "#3f3f3f",
              "#16323a": "#272727", "#16303a": "#272727", "#252b44": "#272727", "#18203a": "#191919",
              "#141931": "#151515", "#121833": "#141414", "#2c4a5a": "#363636", "#3aa7b8": "#9c9c9c",
              "#b8fbff": "#f4f4f4", "#e8faff": "#f6f6f6", "#cfe9ee": "#e2e2e2", "#c9cee0": "#cdcdcd",
              "#d9dce6": "#dedede", "#7b84a3": "#878787", "#4a5170": "#4f4f4f", "#0c0f1c": "#0b0b0b",
              "#2a3150": "#353535", "#b8c4d6": "#c6c6c6", "#4a3a1f": "#333333", "#ffe9c2": "#e8e8e8",
              "#8a91a8": "#8e8e8e", "#3f9fb0": "#7a7a7a", "#b04ca8": "#474747", "#1f7a4d": "#2f2f2f",
              # automatic: blue-grey UI tones -> grey of the same brightness
              "#070912": "#090909", "#0f1324": "#131313", "#12192c": "#191919", "#13172a": "#181818", "#131a2e": "#1a1a1a", "#151b33": "#1b1b1b", "#151c34": "#1c1c1c", "#1b2140": "#222222", "#1c3a52": "#353535", "#20343a": "#303030", "#232a45": "#2a2a2a", "#262b40": "#2b2b2b", "#343b57": "#3c3c3c", "#3f4a6b": "#4a4a4a", "#3f5670": "#535353", "#3f6f80": "#666666", "#3f6f8a": "#676767", "#4a5272": "#535353", "#5c6380": "#646464", "#5d6480": "#656565", "#6f7690": "#767676", "#8fb7c4": "#afafaf", "#9aa0b4": "#a0a0a0"}
GRAY_RGB = {(22, 27, 48): (24, 24, 24), (20, 24, 42): (22, 22, 22), (13, 16, 32): (14, 14, 14),
            (43, 91, 102): (60, 60, 60), (37, 43, 68): (40, 40, 40), (238, 241, 255): (237, 237, 237),
            (11, 14, 26): (10, 10, 10), (38, 44, 70): (44, 44, 44), (31, 95, 107): (59, 59, 59),
            (18, 24, 51): (20, 20, 20), (30, 34, 52): (32, 32, 32), (17, 21, 39): (18, 18, 18), (5, 7, 14): (5, 5, 5),
            (27, 32, 51): (29, 29, 29), (235, 248, 255): (240, 240, 240), (20, 24, 44): (22, 22, 22),
            (10, 14, 28): (10, 10, 10)}


def look():
    return cfg.get("look") if cfg.get("look") in dict(LOOKS) else "grau"


def is_gray():
    """Greyscale world (Grau or Hell) – keys, indicator lights, no accent color."""
    return look() in ("grau", "hell")


def is_light():
    return look() == "hell"


def base_colors():
    """Colors of the base look (without custom adjustments)."""
    return dict(LIGHT) if is_light() else dict(GRAY) if is_gray() else {}


WEIGHTS = [(200, "ExtraLight 200"), (300, "Light 300"), (400, "Regular 400"), (500, "Medium 500"),
           (600, "SemiBold 600"), (700, "Bold 700")]

cfg = dict(DEFAULTS)
_color_map, _rgb_map = {}, {}
_hooked = False


# ---------- Settings ----------
def load(settings):
    """Take values from settings["appearance"] (missing = default)."""
    global cfg
    cfg = dict(DEFAULTS, **(settings.get("appearance") or {}))
    cfg["colors"] = dict(cfg.get("colors") or {})
    cfg["elements"] = {k: list(v) for k, v in (cfg.get("elements") or {}).items()}
    cfg["elements_saved"] = {k: list(v) for k, v in (cfg.get("elements_saved") or {}).items()}
    cfg["skin"] = dict(cfg.get("skin") or {})
    cfg["fx"] = dict(cfg.get("fx") or {})
    cfg["pages"] = {k: dict(v) for k, v in (cfg.get("pages") or {}).items() if isinstance(v, dict)}
    global RARITY_NAMES
    RARITY_NAMES = bool(settings.get("rarity_colors", False))
    _build_color_map()


def save(settings):
    settings["appearance"] = {k: cfg[k] for k in DEFAULTS}


def _fill_maps(cmap, rmap, colors):
    cmap.clear()
    rmap.clear()
    if is_gray():
        for old, new in GRAY_LOOSE.items():
            cmap[old] = new
            c, n = QtGui.QColor(old), QtGui.QColor(new)
            rmap[(c.red(), c.green(), c.blue())] = (n.red(), n.green(), n.blue())
        rmap.update(GRAY_RGB)
    for key, _, default in PALETTE:
        new = (colors.get(key) or "").lower()
        if new and new != default:
            cmap[default] = new
            c, n = QtGui.QColor(default), QtGui.QColor(new)
            rmap[(c.red(), c.green(), c.blue())] = (n.red(), n.green(), n.blue())


def _build_color_map():
    _fill_maps(_color_map, _rgb_map, dict(base_colors(), **cfg["colors"]))
    pages_changed()


_color_hooked = False


def install_color_hook():
    """Once at startup: redirect colors when drawing (QColor("#62f2ff") in the overlay etc.) to the look."""
    global _color_hooked
    if _color_hooked:
        return
    _color_hooked = True
    if _color_map:  # only if colors are changed (otherwise no extra cost when drawing)
        base = QtGui.QColor

        class ThemedColor(base):
            def __init__(self, *args):
                if len(args) == 1 and isinstance(args[0], base):  # copy of a color: take over its values
                    super().__init__()
                    self.setRgba(args[0].rgba()) if args[0].isValid() else None
                    return
                if len(args) == 1 and isinstance(args[0], str):
                    args = (_color_map.get(args[0].lower(), args[0]),)
                elif len(args) in (3, 4) and all(isinstance(a, int) for a in args):
                    rgb = _rgb_map.get(tuple(args[:3]))
                    if rgb:
                        args = rgb + tuple(args[3:])
                try:
                    super().__init__(*args)
                except TypeError:  # other Qt types (e.g. Qt.GlobalColor via detours): like the original
                    super().__init__()
                    self.setRgba(base(*args).rgba())
        QtGui.QColor = ThemedColor


def color(key, area=None):
    """Current color of a palette entry (hex) – with an area: its own color, otherwise the global one."""
    default = next(d for k, _, d in PALETTE if k == key)
    own = page_color(area, key) if area else None
    return (own or cfg["colors"].get(key) or base_colors().get(key) or default).lower()


# ---------- Per page ----------
_ctx = None          # area process_qss is currently computing for
_own_areas = set()   # areas with their own values
_area_maps = {}      # area -> (color table, RGB table)
PAGE_PARTS = ("colors", "radius_ctrl", "radius_panel", "elements", "fx")


def page_cfg(area):
    return (cfg.get("pages") or {}).get(area) or {} if area else {}


def page_color(area, key):
    """Own color of a page (the background is stored as an area color in the skin) or None."""
    if key == "bg":
        return (cfg.get("skin") or {}).get(f"bg_{area}")
    return (page_cfg(area).get("colors") or {}).get(key)


def pages_changed():
    """After every per-page change: rebuild the tables."""
    _own_areas.clear()
    _area_maps.clear()
    for area, _ in AREAS:
        p = page_cfg(area)
        if any(p.get(k) for k in PAGE_PARTS) or (cfg.get("skin") or {}).get(f"bg_{area}"):
            _own_areas.add(area)


_area_ids = {}  # id(page widget) -> area


def area_of(w):
    """Area a widget lies in (only one with its own values counts), otherwise None."""
    if not _own_areas:
        return None
    if isinstance(w, str):  # area directly (e.g. "scan")
        return w if w in _own_areas else None
    while w is not None:
        k = _area_ids.get(id(w))
        if k:
            return k if k in _own_areas else None
        w = w.parentWidget()
    return None


# ---------- Fonts ----------
def font_dirs():
    """Bundled fonts (in the program) and custom ones (data/schriften)."""
    bundled = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1])) / "fonts"
    return [bundled, FONT_DIR]


_registered = None


def register_fonts():
    """Load bundled and custom fonts (once). -> sorted list of families."""
    global _registered
    if _registered is not None:
        return _registered
    fams = set()
    for d in font_dirs():
        if not d.exists():
            continue
        for f in sorted(list(d.glob("*.ttf")) + list(d.glob("*.otf")) + list(d.glob("*.TTF")) + list(d.glob("*.OTF"))):
            i = QtGui.QFontDatabase.addApplicationFont(str(f))
            if i >= 0:
                fams.update(QtGui.QFontDatabase.applicationFontFamilies(i))
    _registered = sorted(fams)
    check_families()
    return _registered


def import_fonts(paths):
    """Copy font files (.ttf/.otf, also inside .zip) to data/schriften and load them. -> new families."""
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    added = []
    for p in paths:
        p = pathlib.Path(p)
        targets = []
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                for name in z.namelist():
                    base = name.rsplit("/", 1)[-1]
                    if base.lower().endswith((".ttf", ".otf")) and "__MACOSX" not in name:
                        out = FONT_DIR / base
                        out.write_bytes(z.read(name))
                        targets.append(out)
        elif p.suffix.lower() in (".ttf", ".otf"):
            out = FONT_DIR / p.name
            if p.resolve() != out.resolve():
                shutil.copyfile(p, out)
            targets.append(out)
        for t in targets:
            i = QtGui.QFontDatabase.addApplicationFont(str(t))
            if i >= 0:
                added += QtGui.QFontDatabase.applicationFontFamilies(i)
    return sorted(set(added))


STYLE_WORDS = {"thin", "extralight", "light", "regular", "medium", "semibold", "bold", "extrabold", "black",
               "italic", "18pt", "24pt", "28pt"}


def resolve_family(name, fallback):
    """Font name from the selection -> existing family ("Inter 18pt 18pt Medium" -> "Inter 18pt"). The family also gets
    BC Symbols as substitute: QML only names one family and would otherwise take symbols from any system font
    (Windows: MS UI Gothic, Linux/Mac: empty boxes)."""
    fam = _resolve_family(name, fallback)
    if fam != SYMBOLS and SYMBOLS not in QtGui.QFont.substitutes(fam):
        QtGui.QFont.insertSubstitution(fam, SYMBOLS)
    return fam


def _resolve_family(name, fallback):
    fams = set(QtGui.QFontDatabase.families())
    if name in fams:
        return name
    words = (name or "").split()
    while words:
        cand = " ".join(words)
        if cand in fams:
            return cand
        words = words[:-1]
    base = [w for w in (name or "").split() if w.lower() not in STYLE_WORDS]
    for cand in (" ".join(base), " ".join(base + ["18pt"])):
        if cand in fams:
            return cand
    return fallback


def scale():
    return max(0.6, min(1.8, float(cfg.get("font_scale") or 100) / 100))


SYMBOLS = "BC Symbols"   # fonts/BCSymbols-Regular.ttf (tools/make_symbol_font.py): symbols Inter and Barlow lack
FALLBACK = [SYMBOLS, "Segoe UI Symbol", "Segoe UI Emoji", "Segoe UI", "Apple Symbols", "Noto Sans Symbols 2", "DejaVu Sans"]


def _families(first):
    """Font + fallback fonts for characters it lacks (symbols like ◉ ▦ ☰ ✕ ⟲)."""
    return [first] + [f for f in FALLBACK if f != first]


def text_font(px=None, weight=None):
    f = QtGui.QFont(cfg["font_text"])
    f.setFamilies(_families(cfg["font_text"]))
    if px:
        f.setPixelSize(max(1, round(px)))
    f.setWeight(QtGui.QFont.Weight(int(weight or cfg["font_text_weight"])))
    return f


def display_weight():
    return QtGui.QFont.Weight(int(cfg["font_display_weight"]))


def display_font(px=None):
    f = QtGui.QFont(cfg["font_display"])
    f.setFamilies(_families(cfg["font_display"]))
    if px:
        f.setPixelSize(max(1, round(px)))
    f.setWeight(display_weight())
    return f


# ---------- Corners ----------
def element(el, area=None):
    """Own rounding of an element -> (value, unit) or None (= like the group). With an area (or while
    process_qss computes for an area): first the page's value, then the global one."""
    if not el:
        return None
    area = area or _ctx
    v = (page_cfg(area).get("elements") or {}).get(el) or (cfg.get("elements") or {}).get(el)
    return (float(v[0]), v[1]) if v else None


def group(kind, area=None):
    """Rounding of a group (ctrl/panel) -> (value, unit); page before global."""
    v = page_cfg(area or _ctx).get(f"radius_{kind}")
    return (float(v[0]), v[1]) if v else (float(cfg[f"radius_{kind}"]), cfg[f"radius_{kind}_unit"])


def _radius(size, v, unit):
    r = size * v / 100 if unit == "%" else v
    return max(0.0, min(r, size / 2))


def panel_radius(w, h=None, el=None, widget=None):
    """Rounding of a surface (tile, panel, header) for its real size (widget: for per-page values)."""
    short = min(w, h) if h else w
    area = area_of(widget) if widget is not None else None
    own = element(el, area)
    return _radius(short, *(own or group("panel", area)))


def ctrl_radius(h, el=None, widget=None):
    """Rounding of a control (button, field, chip) for its height (widget: for per-page values)."""
    area = area_of(widget) if widget is not None else None
    own = element(el, area)
    return _radius(h, *(own or group("ctrl", area)))


# Skin builder → colors: (key, label, default)
SKIN_COLORS = [("rar_common", "Name: Common", "#c3c8da"), ("rar_uncommon", "Name: Uncommon", "#b8c7d9"),
               ("rar_rare", "Name: Rare", "#e7c35a"), ("rar_mythic", "Name: Mythic", "#ff8a3d"),
               ("text_light", "Set- und Zusatznamen", "#aab1c8"),
               ("mana_W", "Mana: Weiß", "#f4ecc8"), ("mana_U", "Mana: Blau", "#4a90d9"),
               ("mana_B", "Mana: Schwarz", "#8c7f86"), ("mana_R", "Mana: Rot", "#e0553d"),
               ("mana_G", "Mana: Grün", "#3f9b5a"), ("mana_C", "Mana: Farblos", "#b6b6b6"),
               ("mana_generic", "Mana: Generisch (2, X …)", "#c9c9c9"), ("mana_text", "Mana: Schrift", "#111111")]
# Areas (pages) with their own background – without their own color the app background applies
AREAS = [("stats", "Statistik"), ("sessions", "Log"), ("scan", "Scannen"), ("library", "Bibliothek"),
         ("decks", "Deckbau"), ("testing", "Spielen"), ("import", "Import"), ("trade", "Tausch"),
         ("settings", "Einstellungen")]
SKIN_COLORS += [(f"bg_{k}", label, None) for k, label in AREAS]
_SKIN_DEFAULT = {k: d for k, _, d in SKIN_COLORS}
# Skin builder → colors in sections (key, title, entries); "bg" = app background (palette)
SKIN_SECTIONS = [("bg", "Hintergründe", ["bg"] + [f"bg_{k}" for k, _ in AREAS]),
                 ("names", "Kartennamen & Texte", ["rar_common", "rar_uncommon", "rar_rare", "rar_mythic", "text_light"]),
                 ("mana", "Manasymbole", ["mana_W", "mana_U", "mana_B", "mana_R", "mana_G", "mana_C", "mana_generic",
                                          "mana_text"]),
                 ("base", "Grundfarben", [k for k, _, _ in PALETTE if k != "bg"])]


def skin_label(key):
    """Label of a color key from SKIN_COLORS or PALETTE."""
    if key == "bg":
        return "App (überall)"
    return next((lb for k, lb, _ in SKIN_COLORS + PALETTE if k == key), key)


def skin_color(key):
    """Color from the skin builder (hex). Area backgrounds without their own color: app background."""
    own = (cfg.get("skin") or {}).get(key)
    if own:
        return own
    if key.startswith("bg_"):
        return background()
    return _SKIN_DEFAULT.get(key) or "#c9c9c9"


def set_skin_color(key, value):
    """Set a skin-builder color (None = default) and apply it live."""
    if key == "bg":
        set_background(value)
        return
    if key in dict((k, 1) for k, _, _ in PALETTE):  # base colors
        if value:
            cfg["colors"][key] = value
        else:
            cfg["colors"].pop(key, None)
        _build_color_map()
        _notify("palette")
        return
    skin = cfg.setdefault("skin", {})
    if value:
        skin[key] = value
    else:
        skin.pop(key, None)
    if key.startswith("bg_"):
        pages_changed()
        _notify("area", key[3:])


# Effects (skin builder → effects): (key, label, default, min, max, unit, step)
FX = [("glow", "Leuchten der Knöpfe", 100, 0, 250, "%", 10), ("btn_border", "Rahmen der Knöpfe", 1.5, 0.5, 4.0, "px", 0.5),
      ("shine", "Glanz auf Karten (Maus drüber)", 100, 0, 200, "%", 10)]


def fx(key, widget=None):
    """Value of an effect; % values as a factor (100 % = 1.0). widget: value of its page, if it has its own."""
    _, _, default, lo, hi, unit, _ = next(f for f in FX if f[0] == key)
    area = area_of(widget) if widget is not None else None
    raw = (page_cfg(area).get("fx") or {}).get(key)
    if raw is None:
        raw = (cfg.get("fx") or {}).get(key, default)
    try:
        v = max(lo, min(hi, float(raw)))
    except (TypeError, ValueError):
        v = default
    return v / 100 if unit == "%" else v


RARITY_NAMES = False  # Settings → Display: card names in the color of their rarity (default: off)


def rarity_color(rarity, force=False):
    """Color for a card name: colored only with "rarity as name color" (or force), otherwise text color."""
    if not (RARITY_NAMES or force):
        return color("text")
    return skin_color(f"rar_{rarity}") if f"rar_{rarity}" in _SKIN_DEFAULT else skin_color("rar_common")


def mana_color(sym):
    return skin_color(f"mana_{sym}") if f"mana_{sym}" in _SKIN_DEFAULT else skin_color("mana_generic")


def background():
    return color("bg")


def set_background(hex_color):
    """Change the app background live."""
    if hex_color:
        cfg["colors"]["bg"] = hex_color
    else:
        cfg["colors"].pop("bg", None)
    _build_color_map()
    _notify("background")


def mana_radius(size):
    """Corners of the mana symbols (squares); slightly rounded without a custom setting."""
    own = element("mana")
    return _radius(size, *own) if own else size * 0.22  # drawn: global


def bar_width():
    return max(3, min(24, int(cfg.get("bar_width") or 7)))


def check_families():
    """After loading the fonts: repair invalid names."""
    cfg["font_text"] = resolve_family(cfg["font_text"], TEXT_FAMILY)
    cfg["font_display"] = resolve_family(cfg["font_display"], DISPLAY_FAMILY)
