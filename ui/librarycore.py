"""Library without widgets: search, filters, sorting, grouping, detail and compare view as state.

Everything is drawn and animated in Qt Quick (qlibrary.py / LibraryPage.qml, qdetail.py / DetailView.qml); this
module only holds the logic – the same as formerly in libview.LibraryWindow / DetailPanel.

LibraryCore    the Library (collection or all cards) – also the library views in the "Trade" tab (subclass)
DetailState    detail or compare view of a card: section texts, languages, prints, image, price history
DetailHost     detail (+ compare) outside the Library (sessions, trade)
"""
import collections
import datetime
import html
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6 import QtCore, QtGui
from PySide6.QtCore import QRectF, Qt

from cards import carddb
from cards import currency
import games
from cards import library
from ui import look
from ui import qdialogs
from collection.collection import LANGS, lang_short, price as item_price, scryfall_id
from scanner.common import BASE, REF, image_rel, lang_img
from system.i18n import tr
from ui.searchbox import CountSection, Mode, SearchBox, Steps, Toggle, merged_order

THUMBS = REF / "thumbs"   # small card images for the grid (loaded once, offline afterwards)
LARGE = REF / "large"     # large images of the detail view
RARITY = dict(games.current().rarities)
CARD_MARGIN = 28          # margin around the detail-view card image (room for shine/tilt, as formerly CardView)


def eur(v):
    """Price (in euros) in the chosen display currency (Settings → Collection)."""
    return currency.fmt(v)


# ---------- Background ----------
class _Call(QtCore.QObject):
    """Deliver the result of a function from a background thread in the main thread."""
    done = QtCore.Signal(object, object)

    def __init__(self, parent, cb):
        super().__init__(parent)
        self.cb = cb
        self.done.connect(self._finish)

    @QtCore.Slot(object, object)
    def _finish(self, res, err):
        try:
            self.cb(res, err)
        finally:
            self.deleteLater()


def run_async(parent, fn, cb):
    """fn() in the background, then cb(result, error) in the main thread (as long as parent is alive)."""
    call = _Call(parent, cb)

    def work():
        try:
            res, err = fn(), None
        except Exception as e:  # noqa: BLE001 – the error goes to the UI as text
            res, err = None, e
        try:
            call.done.emit(res, err)
        except RuntimeError:
            pass  # torn down in the meantime
    threading.Thread(target=work, daemon=True).start()


_api_lock = threading.Lock()
_api_last = [0.0]


def _throttle(url):
    """The Scryfall API (not the image servers) asks for at most ~10 requests per second."""
    if "api.scryfall.com" not in url:
        return
    with _api_lock:
        wait = _api_last[0] + 0.11 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _api_last[0] = time.monotonic()


class ImageLoader(QtCore.QObject):
    """Card images in the background: local file first, otherwise download (and store it there)."""
    ready = QtCore.Signal(str)
    _loaded = QtCore.Signal(str, QtGui.QImage)

    def __init__(self, parent=None, workers=6, keep=600):
        super().__init__(parent)
        self.workers = workers
        self.pool = ThreadPoolExecutor(workers, thread_name_prefix="bilder")
        self.cache, self.keep = collections.OrderedDict(), keep
        self.pending, self.failed = set(), set()
        self._loaded.connect(self._store)

    def get(self, key, width, local=None, url=None, cache=None, fallback=None):
        """QPixmap or None (then it is loaded and ready(key) is emitted later). fallback: file to use if the
        download fails (offline)."""
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        if key not in self.pending and key not in self.failed:
            self.pending.add(key)
            self.pool.submit(self._work, key, width, local, url, cache, fallback)
        return None

    def cancel(self):
        """Discard pending downloads (window closed) so the program can exit immediately."""
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.pool = ThreadPoolExecutor(self.workers, thread_name_prefix="bilder")
        self.pending.clear()

    def forget(self, key):
        self.cache.pop(key, None)
        self.failed.discard(key)

    def _work(self, key, width, local, url, cache, fallback=None):
        img = QtGui.QImage()
        try:
            for path in (local, cache):
                if path is not None and path.exists():
                    img.load(str(path))
                    if not img.isNull():
                        break
            if img.isNull() and url:
                _throttle(url)
                data = library.fetch_bytes(url)
                img.loadFromData(data)
                if not img.isNull() and cache is not None:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_bytes(data)
        except Exception:  # noqa: BLE001 – offline or image missing: placeholder
            img = QtGui.QImage()
        if img.isNull() and fallback is not None and fallback.exists():
            img.load(str(fallback))
        if not img.isNull() and width:
            img = img.scaledToWidth(width, Qt.SmoothTransformation)
        try:
            self._loaded.emit(key, img)
        except RuntimeError:
            pass

    @QtCore.Slot(str, QtGui.QImage)
    def _store(self, key, img):
        self.pending.discard(key)
        if img.isNull():
            self.failed.add(key)
        else:
            self.cache[key] = QtGui.QPixmap.fromImage(img)
            while len(self.cache) > self.keep:
                self.cache.popitem(last=False)
        self.ready.emit(key)


# ---------- Tile appearance (Settings → Appearance) ----------
DISPLAY_DEFAULTS = {"group_prints": True, "group_sets": False, "chips": "lang", "chip_max": 3, "set_line": "set",
                    "show_lang": "en"}  # show_lang: tile language when there are several ("most" = most common)


def display(settings):
    """Settings → Appearance: how cards in the grid are labelled and grouped."""
    d = dict(DISPLAY_DEFAULTS)
    d.update({k: v for k, v in (settings.get("display") or {}).items() if k in DISPLAY_DEFAULTS})
    return d



def _fin_parts(it):
    """["Reverse Holo"] or ["Foil"] for rows – empty for the plain finish."""
    from cards import finishes
    lb = finishes.full_label(it)
    return [tr(lb)] if lb else []

def group_rows(rows, disp):
    """Same print (set + number) in another language/foil -> one tile; optionally all prints of a name.
    The tile carries variants [(quantity, language, foil)] for the chips, sets [(set, number, quantity)] for the line
    below it and value (sum of price × quantity)."""
    if not disp["group_prints"] and not disp["group_sets"]:
        for r in rows:
            r["variants"] = [(r["count"], r.get("lang") or "en", r.get("fin") or ("Foil" if r.get("foil") else ""))] \
                if r.get("count") else []
            r["sets"] = [(r["set"], r["number"], r.get("count") or 0)]
        return rows
    out, by = [], {}
    pref = disp.get("show_lang") or "en"

    def rank(r):  # which variant the tile shows: the desired language first, otherwise the one you own most of
        return ((r.get("lang") or "en") == pref and pref != "most", r.get("count") or 0)
    for r in rows:
        key = (r.get("game") or "", r["name"] if disp["group_sets"] else r["sid"])   # never merge games
        g = by.get(key)
        var = (r["count"], r.get("lang") or "en", r.get("fin") or ("Foil" if r.get("foil") else ""))
        val = (r.get("price") or 0) * (r.get("count") or 0)
        if g is None:
            g = by[key] = dict(r, variants=[var] if r.get("count") else [], sets={}, value=val, _best=rank(r))
            g["sets"][(r["set"], r["number"])] = r.get("count") or 0
            g["key"] = f"{key[0]}|{key[1]}|*" if key[0] else f"{key[1]}|*"
            out.append(g)
            continue
        if r.get("count"):
            g["variants"].append(var)
            g["conds"] = (g.get("conds") or []) + (r.get("conds") or [])
        g["count"] = (g.get("count") or 0) + (r.get("count") or 0)
        g["value"] += val
        g["sets"][(r["set"], r["number"])] = g["sets"].get((r["set"], r["number"]), 0) + (r.get("count") or 0)
        if rank(r) > g["_best"]:  # image, language, detail: the desired language, otherwise the most common one
            for k in ("sid", "set", "number", "lang", "foil", "img", "thumb", "normal", "card", "db", "rarity", "price"):
                g[k] = r.get(k)
            g["_best"] = rank(r)
    for g in out:
        g["variants"].sort(key=lambda v: (-v[0], v[1], v[2]))
        g["sets"] = sorted(((s, n, c) for (s, n), c in g["sets"].items()), key=lambda t: (-t[2], t[0], t[1]))
    return out


def chip_texts(row, disp, mode):
    """Chips of a tile: "1× EN Foil", "2× FR" … (depending on the setting), at most chip_max (otherwise "+n")."""
    if mode == "all":
        return [f"{row['count']}×"] if row.get("count") else []
    var = row.get("variants") or ([(row["count"], row.get("lang") or "en",
                                    row.get("fin") or ("Foil" if row.get("foil") else ""))] if row.get("count") else [])
    if len(var) > 1:   # same language + finish (e.g. differing only in condition): one chip
        merged = {}
        for n, lang, f in var:
            merged[(lang, f)] = merged.get((lang, f), 0) + n
        var = sorted(((n, lang, f) for (lang, f), n in merged.items()), key=lambda v: (-v[0], v[1], v[2]))
    if disp["chips"] == "count":
        texts = [f"{sum(v[0] for v in var)}×"] if var else []
    elif disp["chips"] == "foil":
        plain, foil = sum(v[0] for v in var if not v[2]), sum(v[0] for v in var if v[2])
        texts = ([f"{plain}×"] if plain else []) + ([f"{foil}× {tr(games.current().counter_foil)}"] if foil else [])
    else:
        texts = [f"{n}× {lang_short(lang)}" + (f" {tr(f)}" if f else "") for n, lang, f in var]
    k = max(1, int(disp["chip_max"]))
    if len(texts) > k:  # the rest hangs on the last chip ("2× FR  +3")
        texts = texts[:k - 1] + [f"{texts[k - 1]}  +{len(texts) - k}"]
    if row.get("game_tag"):   # mixed Library: which game it comes from
        texts = [row["game_tag"]] + texts
    return texts


def cond_chip(row):
    """Condition on the tile (its own box, conditions.py): "" if everything is Near Mint, otherwise the grade or
    the range "NM–PL" across the grouped copies."""
    cs = [c for c in (row.get("conds") or []) if c]
    if not cs or all(plain for _, _, plain in cs):
        return ""
    cs.sort(key=lambda c: c[0])
    best, worst = cs[0][1], cs[-1][1]
    return best if best == worst else f"{best}–{worst}"


def sets_text(row, disp):
    sets = row.get("sets") or [(row["set"], row["number"], row.get("count") or 0)]
    if disp["set_line"] == "setnum":
        return " · ".join(f"{s} #{n}" for s, n, _ in sets)
    return " · ".join(dict.fromkeys(s for s, _, _ in sets))


# natural direction per sorting (▲ ascending / ▼ descending in the selection list)
SORT_NATURAL = {"relevance": "desc", "name": "asc", "price": "desc", "set": "desc", "new": "desc", "type": "asc",
                "mv": "asc", "color": "asc", "rarity": "desc", "count": "desc", "cond": "asc"}
SORTS = (("relevance", "Sortierung: Beste Treffer"), ("count", "Sortierung: Anzahl"), ("name", "Sortierung: Name"),
         ("price", "Sortierung: Preis"),
         ("set", "Sortierung: Set"), ("new", "Sortierung: Neueste"), ("type", "Sortierung: Kartentyp"),
         ("mv", "Sortierung: Manawert"), ("color", "Sortierung: Farbe"), ("rarity", "Sortierung: Seltenheit"),
         ("cond", "Sortierung: Zustand"))


def detail_width(saved=None):
    """Width of the detail view: saved (dragged by the user) or 1/5 of the screen width."""
    if saved and int(saved) != 640:  # 640 was the old fixed default – no longer treat it as a preference
        return int(saved)
    screen = QtGui.QGuiApplication.primaryScreen()
    return max(360, round(screen.availableGeometry().width() / 5)) if screen else 384


def source_text(item):
    src = item.get("src") or ""
    sid = src.split("/")[0] if src else item.get("from_session")
    if sid:
        imported = sid.startswith("import_")   # an import's log "import_2026-11-02_11-25-41" (importview.do_collection)
        try:
            d = datetime.datetime.strptime(sid[7:] if imported else sid, "%Y-%m-%d_%H-%M-%S").strftime("%d.%m.%Y")
        except ValueError:
            d = sid
        return tr(f"imported on {d}") if imported else tr(f"pulled on {d}")
    return tr(f"added by hand · {time.strftime('%d.%m.%Y', time.localtime(item.get('added') or 0))}")


# ---------- Card info as HTML (detail view) ----------
FOLDS = [("image", "Kartenbild"), ("text", "Kartentext"), ("prices", "Preise"), ("card", "Karte"),
         ("legal", "Legalität"), ("print", "Druck"), ("popular", "Beliebtheit & Geschichte"), ("rulings", "Rulings"),
         ("prints", "Alle Drucke"), ("altarts", "Alt arts"), ("ids", "IDs"), ("own", "In deiner Sammlung"), ("lists", "Meine Listen"),
         ("links", "Links")]  # "own": adding as well
LEGAL_FORMATS = list(games.current().legal_long)
LEGAL_STATE = {"legal": ("legal", "#46d17a"), "not_legal": ("nicht legal", "#4a5270"),
               "banned": ("gebannt", "#ff4d5e"), "restricted": ("eingeschränkt", "#ffb347")}
LANG_NAME = {code: name for code, _, name in LANGS}
FINISH_NAMES = dict(games.current().finishes)


def _game_changed():
    g = games.current()
    RARITY.clear()
    RARITY.update(g.rarities)
    LEGAL_FORMATS[:] = list(g.legal_long)
    FINISH_NAMES.clear()
    FINISH_NAMES.update(g.finishes)
BORDER_NAMES = {"black": "schwarz", "white": "weiß", "borderless": "randlos", "silver": "silber", "gold": "gold",
                "yellow": "gelb"}
GAME_NAMES = {"paper": "Papier", "arena": "MTG Arena", "mtgo": "MTG Online"}


def _price_str(v):
    return f"{v:.2f}" if isinstance(v, (int, float)) else v


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pretty(s):
    return _esc(str(s).replace("_", " ").strip()).title() if s else ""


def _date(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return iso or ""


_MANA_IMG = {}


def mana_img(s, px):
    """Mana symbol as an equally sized, rounded square (image URL for rich text). Hybrid: two colors split
    diagonally, Phyrexian: Φ. Corners from the skin builder (element "Manasymbole")."""
    radius = look.mana_radius(px)
    key = (s, px, round(radius, 2), tuple(sorted((look.cfg.get("skin") or {}).items())))
    url = _MANA_IMG.get(key)
    if url is not None:
        return url
    dpr = 2.0
    img = QtGui.QImage(round(px * dpr), round(px * dpr), QtGui.QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    img.setDevicePixelRatio(dpr)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setRenderHint(QtGui.QPainter.TextAntialiasing)
    r = QRectF(0.5, 0.5, px - 1, px - 1)
    path = QtGui.QPainterPath()
    path.addRoundedRect(r, radius, radius)
    parts = [x for x in s.split("/") if x != "P"]
    phyrexian = "/P" in s
    cols = [QtGui.QColor(look.mana_color(x)) for x in parts] or [QtGui.QColor(look.mana_color("generic"))]
    if len(cols) >= 2:  # hybrid: split diagonally
        p.fillPath(path, cols[0])
        tri = QtGui.QPainterPath()
        tri.moveTo(r.topRight())
        tri.lineTo(r.bottomRight())
        tri.lineTo(r.bottomLeft())
        tri.closeSubpath()
        p.fillPath(path.intersected(tri), cols[1])
        label = ""
    else:
        p.fillPath(path, cols[0])
        label = {"T": "↷", "Q": "↶"}.get(s, "Φ" if phyrexian else parts[0] if parts else s)
    if label:
        f = QtGui.QFont(look.text_font())
        f.setBold(True)
        f.setPixelSize(max(6, round(px * (0.62 if len(label) == 1 else 0.48))))
        p.setFont(f)
        p.setPen(QtGui.QColor(look.skin_color("mana_text")))
        br = QtGui.QFontMetricsF(f).tightBoundingRect(label)
        p.drawText(QtCore.QPointF(r.center().x() - br.center().x(), r.center().y() - br.center().y()), label)
    p.end()
    ba = QtCore.QByteArray()
    buf = QtCore.QBuffer(ba)
    buf.open(QtCore.QIODevice.WriteOnly)
    img.save(buf, "PNG")
    url = "data:image/png;base64," + bytes(ba.toBase64()).decode("ascii")
    _MANA_IMG[key] = url
    return url


def _symbols(text, escaped=False, size=15):
    """{2}{R}{T} … in the text -> mana symbols (equally sized, rounded squares)."""
    if not escaped:
        text = _esc(text)

    def sym(m):
        return f"<img src='{mana_img(m.group(1), size)}' width='{size}' height='{size}' align='middle'>&#8202;"
    return re.sub(r"\{([^}]+)\}", sym, text)


def _color_list(colors):
    if not colors:
        return tr("colorless")
    return " ".join(f"<img src='{mana_img(c, 15)}' width='15' height='15' align='middle'>" for c in colors)


def _table(rows, label_w=36):
    body = "".join(f"<tr><td width='{label_w}%' valign='top' style='color:#8a91a8'>{a}</td>"
                   f"<td valign='top'>{b}</td></tr>" for a, b in rows)
    return f"<table width='100%' cellspacing='0' cellpadding='3'>{body}</table>"


def _rules_box(f, show_name=False):
    """Rules-text box of a card face: name/cost (for several faces), type, text, stats, flavor."""
    parts = []
    if show_name:
        parts.append(f"<span style='font-size:14pt; font-weight:700'>{_esc(f.get('name'))}</span>"
                     + (f"&nbsp;&nbsp;{_symbols(f['mana_cost'])}" if f.get("mana_cost") else ""))
    if f.get("type_line"):
        parts.append(f"<b>{_esc(f['type_line'])}</b>")
    if f.get("oracle_text"):
        txt = _symbols(f["oracle_text"])
        txt = re.sub(r"\(([^)]*)\)", r"<i style='color:#8a91a8'>(\1)</i>", txt)  # reminder text
        parts.append(txt.replace("\n", "<br>"))
    stats = []
    if f.get("power") is not None and f.get("toughness") is not None:
        stats.append(f"{_esc(f['power'])}/{_esc(f['toughness'])}")
    if f.get("loyalty"):
        stats.append(tr(f"Loyalty {_esc(f['loyalty'])}"))
    if f.get("defense"):
        stats.append(tr(f"Defense {_esc(f['defense'])}"))
    if stats:
        parts.append(f"<div align='right' style='font-size:13pt; font-weight:700'>{' · '.join(stats)}</div>")
    if f.get("flavor_text"):
        parts.append(f"<i style='color:#8a91a8'>{_esc(f['flavor_text']).replace(chr(10), '<br>')}</i>")
    if show_name and f.get("artist"):
        parts.append(f"<span style='color:#6c7390'>{tr('Illustration')}: {_esc(f['artist'])}</span>")
    body = "".join(f"<p style='margin:0 0 9px 0'>{p}</p>" for p in parts)
    return (f"<table width='100%' cellspacing='0' cellpadding='12' style='margin-top:8px'>"
            f"<tr><td bgcolor='#131a2e' style='border: 1px solid #2c3352'>{body}</td></tr></table>")


def _legal_table(leg):
    cells = []
    for key, name in LEGAL_FORMATS:
        if key not in leg:
            continue
        label, col = LEGAL_STATE.get(leg[key], (leg[key], "#8a91a8"))
        dim = "" if leg[key] != "not_legal" else "color:#6c7390;"
        cells.append(f"<td width='50%' style='{dim}'><span style='color:{col}'>●</span>&nbsp; {name}"
                     f" <span style='color:{col}; font-size:9pt'>{tr(label)}</span></td>")
    rows = "".join("<tr>" + "".join(cells[i:i + 2]) + "</tr>" for i in range(0, len(cells), 2))
    return f"<table width='100%' cellspacing='0' cellpadding='3'>{rows}</table>"


# ---------- Small states of the detail view ----------
class Shown:
    """visible / hidden (instead of widget visibility)."""
    _visible = True

    def isVisible(self):
        return self._visible

    def isHidden(self):
        return not self._visible

    def setVisible(self, on):
        self._visible = bool(on)

    def show(self):
        self.setVisible(True)

    def hide(self):
        self.setVisible(False)

    def setToolTip(self, *_):
        pass

    def update(self):
        pass


class Html(Shown):
    """Rich text of a line (instead of MarqueeLabel / QLabel)."""

    def __init__(self):
        self.html = ""

    def set_html(self, html, animate=True):
        self.html = html or ""

    def setText(self, html):
        self.set_html(html)

    def text(self):
        return self.html

    def set_text(self, text, color=None, animate=True):
        col = QtGui.QColor(color).name() if color else "#8a91a8"
        self.set_html(f"<span style='color:{col}'>{_esc(text or '')}</span>" if text else "", animate)


class Button(QtCore.QObject, Shown):
    """Button with state (pin, flip, close, star, book). Signals like QAbstractButton."""
    clicked = QtCore.Signal()
    toggled = QtCore.Signal(bool)

    def __init__(self, checkable=False, visible=True, parent=None):
        super().__init__(parent)
        self.checkable, self._checked, self._visible = checkable, False, visible
        self.active, self.empty = False, True

    def isChecked(self):
        return self._checked

    def setChecked(self, on):
        on = bool(on)
        if on != self._checked:
            self._checked = on
            self.toggled.emit(on)

    def click(self):
        if self.checkable:
            self.setChecked(not self._checked)
        self.clicked.emit()


class ImageState:
    """Large card image of the detail view: image, text instead of an image, loading placeholder, foil and how it
    appears (mode: in | swap | flip | fade | quiet – Qt Quick plays the transition)."""

    def __init__(self):
        self.pm, self.text, self.foil, self.loading_name = None, "", False, ""
        self.missing = False   # there is no image (not available online) – empty card instead of loading
        self.mode, self.next_anim = "in", "in"

    def setPixmap(self, pm):
        if pm is None or pm.isNull():
            if self.next_anim in ("flip", "swap", "quiet") and self.pm is not None:
                return  # the old image stays until the new one is there (flip/language)
            self.pm = None
            return
        self.pm, self.text, self.loading_name, self.missing = pm, "", "", False
        self.mode, self.next_anim = self.next_anim, "in"

    def replace_pixmap(self, pm):
        """Same image in a better resolution – without a new transition."""
        self.pm = pm

    def set_foil(self, on):
        self.foil = bool(on)

    def setText(self, text):
        self.text, self.loading_name, self.missing = text, "", False

    def set_loading(self, name):
        """Placeholder in full card size until the image is there."""
        self.text, self.loading_name, self.missing = "", name or " ", False

    def set_missing(self, name):
        """No image online: empty card with the name (without the loading shimmer)."""
        self.pm, self.text, self.loading_name, self.missing = None, "", name or " ", True


class _Head:
    def __init__(self):
        self.sub, self.closed_sub = "", ""


class FoldState(Shown):
    """Collapsible section of the detail view: open/closed, extra text next to the title, hidden via the menu."""

    def __init__(self, key):
        self.key, self.is_open, self.user_hidden, self._visible = key, True, False, True
        self.head = _Head()
        self._label = None

    def setVisible(self, on):
        """Hidden in the section menu: stays off, no matter who calls show()."""
        self._visible = bool(on) and not self.user_hidden

    def set_sub(self, text, closed=None):
        """Grey extra text next to the heading; closed = separate text while the section is collapsed."""
        self.head.sub = text
        if closed is not None:
            self.head.closed_sub = closed

    def set_open(self, on, animate=True):
        self.is_open = bool(on)

    def label(self):
        """Text (rich text) as the content of the section."""
        self._label = Html()
        return self._label


class LangState(QtCore.QObject, Shown):
    """Languages this print exists in (EN, DE, JP …); current = the selected one (instead of LangBar)."""
    picked = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.langs, self.current = [], "en"
        self.hint, self.hint_rev = "", 0   # short notice next to the languages (e.g. no image in this language)

    def set_langs(self, langs, current=None):
        """langs: [(code, display, Scryfall ID, printed name)] or None (= still being determined)."""
        if current is not None:
            self.current = current
        self.langs = list(langs or [])

    def pick(self, code):
        self.set_current(code)
        self.picked.emit(code)

    def set_current(self, code):
        self.current = code

    def has(self, code):
        return any(c == code for c, *_ in self.langs)

    def printed_name(self, code):
        return next((p for c, _, _, p in self.langs if c == code), None)


class _Rows:
    def __init__(self):
        self.rows = []


class PrintsState(Shown):
    """All prints of this card (click = compare to the left); marks: main | compare."""

    def __init__(self):
        self.model_, self.marks, self._visible = _Rows(), {}, False

    def set_prints(self, prints, name):
        self.model_.rows = [dict(p, name=name) for p in prints]

    def set_marks(self, marks):
        self.marks = {k: v for k, v in marks.items() if k}

class PriceData(Shown):
    """Price history of a card: Cardmarket and TCGplayer (converted from $), normal/foil, time range."""
    RANGES = [(30, "30 T"), (90, "90 T")]   # the source doesn't provide more (pricehist.WINDOW)

    _all = None   # all history displays (weakly referenced) – refill them after the history has loaded

    def __init__(self, settings):
        self.settings, self.data, self.finish, self._visible = settings, None, "n", False
        self.days = int(settings.get("ph_range", 90)) or 90   # formerly "All" (0)
        self._last = None
        if PriceData._all is None:
            import weakref
            PriceData._all = weakref.WeakSet()
        PriceData._all.add(self)

    @classmethod
    def refresh_all(cls):
        """Price history finished loading: refill every open display with its card (now shows the chart)."""
        for pd in list(cls._all or []):
            if pd._last is not None:
                try:
                    pd.set_card(*pd._last)
                except RuntimeError:   # the display no longer exists
                    pass

    def set_card(self, sid, foil=False):
        """Load the history; None/no data = hide."""
        from cards import pricehist
        self._last = (sid, foil)
        self.data = pricehist.series(sid) if sid else None
        if not self.data:
            self.hide()
            return False
        has = {k: any(self.data.get(s + k) for s in "ct") for k in "nf"}
        want = "f" if foil else "n"
        self.finish = want if has[want] else ("n" if has["n"] else "f")
        self.show()
        return True

    def set_finish(self, k):
        self.finish = k

    def set_range(self, days):
        self.days = days
        self.settings["ph_range"] = days

    def lines_all(self):
        """Both finishes: [(name, source c/t, foil?, dimmed?, [(date, €, original)], original currency)] –
        the currently selected finish bold, the other dimmed."""
        out = []
        for fin in ("n", "f"):
            keep = self.finish
            self.finish = fin
            try:
                for name, _col, pts, unit in self.lines():
                    out.append((name + (" " + tr(games.current().foil_word) if fin == "f" else ""),
                                "c" if name == "Cardmarket" else "t",
                                fin == "f", fin != keep, pts, unit))
            finally:
                self.finish = keep
        return out

    def lines(self):
        """[(name, color, [(date, value in €, original value)], original currency)] in the selected time range."""
        out = []
        for shop, name, col in (("c", "Cardmarket", "#62f2ff"), ("t", "TCGplayer", "#ffb347")):
            pts = (self.data or {}).get(shop + self.finish) or []
            if shop == "t":
                pts = [(d, currency.from_usd(p), p) for d, p in pts]
                pts = [x for x in pts if x[1] is not None]
            else:
                pts = [(d, p, p) for d, p in pts]
            if self.days and pts:
                cut = pts[-1][0] - datetime.timedelta(days=self.days)
                pts = [x for x in pts if x[0] >= cut]
            if pts:
                out.append((name, col, pts, "$" if shop == "t" else "€"))
        return out


# ---------- Detail view ----------
class DetailState(QtCore.QObject, Shown):
    """Detail view of a card; compare=True: second view for another print (to the left).
    lib: Library or DetailHost (ctrl, mode, loader, detail_context, compare/pin …)."""
    LOAD_TIMEOUT_MS = 8000   # no answer from the image server (offline): the crossed-out card instead of loading forever

    def __init__(self, lib, compare=False):
        super().__init__(lib)
        self.lib, self.ctrl, self.compare = lib, lib.ctrl, compare
        self.row, self.lang, self.face, self.token, self.want_lang = None, "en", 0, 0, None
        self.info, self.full, self.src_pm = None, None, None
        self._visible = False
        self.ctx = getattr(lib, "detail_context", "library")
        self.title, self.alt_names, self.cost, self.set_line = Html(), Html(), Html(), Html()
        self.rules_btn = Button(parent=self)
        self.rules_btn.clicked.connect(self.show_rulings)
        self.pin_btn = Button(checkable=not compare, visible=bool(getattr(lib, "supports_pin", False)), parent=self)
        if compare:
            self.pin_btn.clicked.connect(lambda: getattr(self.lib, "swap_panels", lambda: None)())
        else:
            self.pin_btn.toggled.connect(lambda on: setattr(self.lib, "detail_pinned", on))
        self.star_btn = Button(parent=self)
        self.star_btn.clicked.connect(lambda: self.reveal_fold("lists"))
        self.close_btn = Button(parent=self)
        self.close_btn.clicked.connect(lambda: self.lib.close_compare() if compare else self.lib.close_detail())
        self.image = ImageState()
        self.langbar = LangState(self)
        self.langbar.picked.connect(self.pick_lang)
        self.flip = Button(checkable=True, visible=False, parent=self)
        self.flip.clicked.connect(self.toggle_face)
        self.lang_note, self.text, self.note = Html(), Html(), Html()
        self.folds = {key: FoldState(key) for key, _ in FOLDS}
        self.fold_order = [k for k, _ in FOLDS]
        self.labels = {k: self.folds[k].label() for k in ("card", "legal", "prices", "print", "popular", "rulings",
                                                          "ids", "links", "altarts")}
        self.price_chart = PriceData(self.ctrl.settings)
        self.strip = PrintsState()
        self.prints_empty = Html()
        self.prints_empty.hide()
        # "Your copies" and "My Lists": data only (shown as a form by qdetail)
        self.own_view, self.own_total = [], ""
        self.lists_data, self.list_fns = [], {}
        self.add_n, self.add_is_foil, self.add_foil_ok, self.add_text = 1, False, True, ""
        self.add_finish = ""   # finish for adding (finishes.py)
        self.add_edition = ""  # edition for adding ("1st") – stays set until you deselect it
        self.add_cond = {}     # condition for adding (conditions.py) – empty: default from the settings
        folded = set(self.ctrl.settings.get("detail_folded") or [])
        for key, f in self.folds.items():
            f.set_open(key not in folded, animate=False)
        self.apply_order(self.ctrl.settings.get(f"detail_order_{self.ctx}"))
        self.apply_hidden(self.hidden_folds())
        self.lib.loader.ready.connect(self.on_image)
        self.show_row(None)

    # interface of the former view (size, header row: drawn by Qt Quick)
    def set_fold(self, key, on, animate=True):
        if key in self.folds:
            self.folds[key].set_open(on, animate)

    # --- Section menu (☰): visible sections and order ---
    def hidden_folds(self):
        return set(self.ctrl.settings.get(f"detail_hidden_{self.ctx}") or [])

    def apply_hidden(self, hidden):
        for key, f in self.folds.items():
            f.user_hidden = key in hidden
            if f.user_hidden:
                f._visible = False
            elif self.row is not None and key != "prints":
                f.setVisible(True)
        if self.row is not None and self.full is not None and "prints" not in hidden:
            self.folds["prints"].setVisible(True)

    def set_layout_prefs(self, order, hidden):
        """From the menu: apply order and hidden sections for the detail and compare view."""
        self.ctrl.settings[f"detail_order_{self.ctx}"] = list(order)
        self.ctrl.settings[f"detail_hidden_{self.ctx}"] = sorted(hidden)
        self.ctrl.settings_changed()
        for panel in getattr(self.lib, "detail_panels", lambda: [self])():
            panel.apply_order(order)
            panel.apply_hidden(set(hidden))

    def show_rulings(self):
        """Book: jump to the rulings (without rulings: nothing)."""
        if not self.rules_btn.empty:
            self.reveal_fold("rulings")

    def reveal_fold(self, key):
        """Jump to a section and expand it (Qt Quick scrolls). Hidden? Turned on again, at the very bottom."""
        if self.row is None:
            return
        hidden = self.hidden_folds()
        if key in hidden:
            order = [k for k in self.fold_order if k != key] + [key]
            self.set_layout_prefs(order, hidden - {key})
        fold = self.folds[key]
        fold.setVisible(True)
        if not fold.is_open:
            self.lib.set_fold(key, True)
        fold.set_open(True)

    def apply_order(self, order):
        """Show categories in this order (missing ones appended). The card image is always at the top."""
        order = merged_order(order, [k for k, _ in FOLDS])
        self.fold_order = ["image"] + [k for k in order if k != "image"]

    # --- My Lists (section): per list the versions of this card, with −/+/✕ ---
    def _lists_changed(self, main_have=False):
        if main_have:
            self.lib.ctrl.collection.save()
        page = getattr(self.lib.ctrl, "trade_page", None)
        if page is not None:
            page.fill_wishes()
        for panel in getattr(self.lib, "detail_panels", lambda: [self])():
            if panel is not None and panel.row is not None:
                panel.refresh_lists()
                panel.update_star()

    def _wish_set(self, key, lid, n):
        from collection import trade
        trade.set_wish_count(key, lid, n)
        self._lists_changed()

    def _wish_add(self, lid, any_version):
        from collection import trade
        r = self.row
        if any_version:
            trade.add_wish(r["name"], 1, list_id=lid)
        else:
            trade.add_wish(r["name"], 1, (r.get("set") or "").lower() or None, r.get("number"), list_id=lid)
        self._lists_changed()

    def _have_set(self, lid, it, n):
        from collection import trade
        n = max(0, min(int(n), int(it.get("count", 1))))
        if lid == trade.MAIN_HAVE:
            self.lib.ctrl.collection.update(it["uid"], trade=n)
        else:
            trade.set_have(lid, it["uid"], n)
        self._lists_changed(lid == trade.MAIN_HAVE)

    def _have_print_set(self, lid, pk, n):
        from collection import trade
        trade.set_have_print(lid, pk, n, self.row["name"])
        self._lists_changed()

    def refresh_lists(self):
        """Section "My Lists" (shown by MyLists.qml) -> lists_data: [{kind, title, lists: [{key, name,
        buttons: [{fid, text, tip, enabled}], entries: [{text, n, here, red, minus, plus, remove}], total, summary}]}],
        actions as identifier fid -> list_fns[fid]()."""
        from collection import trade
        data, fns = [], {}
        self.lists_data, self.list_fns = data, fns
        if self.row is None or getattr(self.lib, "ctrl", None) is None:
            self.folds["lists"].set_sub("", "")
            return
        r = self.row
        name = r["name"]
        my_set, my_num = (r.get("set") or "").lower(), r.get("number") or ""
        coll = [it for it in self.lib.ctrl.collection.items if it.get("name") == name]
        own = self._own_items()
        mine = {it["uid"] for it in own}
        used = 0

        def fn(f):
            fid = f"f{len(fns)}"
            fns[fid] = f
            return fid

        def version(set_code, number):
            return f"{(set_code or '').upper()} #{number}" if number else (set_code or "").upper()

        all_wishes = [w for w in trade.wishes(raw=True) if w["name"] == name]
        for kind, title in (("wish", tr("Wishlists")), ("custom", tr("Own lists")), ("have", tr("Trade lists"))):
            sec = {"kind": kind, "title": title, "lists": []}
            for x in trade.lists(kind):
                lid = x["id"]
                main = lid in (trade.MAIN_WISH, trade.MAIN_HAVE)
                entries = []
                if kind in ("wish", "custom"):
                    ws = [w for w in all_wishes if (w.get("list") or trade.MAIN_WISH) == lid]
                    has_any = any(not w.get("set") for w in ws)
                    has_this = any((w.get("set") or "").lower() == my_set and str(w.get("number") or "") == str(my_num)
                                   for w in ws if w.get("set"))
                    buttons = [{"fid": fn(lambda lid=lid: self._wish_add(lid, False)), "text": tr("＋ this one"),
                                "tip": tr("Put exactly this printing on the list"), "enabled": bool(my_set) and not has_this},
                               {"fid": fn(lambda lid=lid: self._wish_add(lid, True)), "text": tr("＋ any"),
                                "tip": tr("Any printing"), "enabled": not has_any}]
                    ws.sort(key=lambda w: (bool(w.get("set")), w.get("set") or "", str(w.get("number") or "")))
                    for w in ws:
                        key, n = trade.wish_key(w), int(w.get("count", 1))
                        here = bool(w.get("set")) and (w.get("set") or "").lower() == my_set \
                            and str(w.get("number") or "") == str(my_num)
                        entries.append({
                            "text": version(w.get("set"), w.get("number")) if w.get("set") else tr("any version"),
                            "n": n, "here": here, "red": False,
                            "minus": fn(lambda k=key, l=lid, n=n: self._wish_set(k, l, n - 1)),
                            "plus": fn(lambda k=key, l=lid, n=n: self._wish_set(k, l, n + 1)),
                            "remove": fn(lambda k=key, l=lid: self._wish_set(k, l, 0))})
                else:
                    rows = [(it, trade.have_count(it, lid)) for it in coll]
                    rows = [(it, n) for it, n in rows if n > 0]
                    names = trade.have_print_names(lid)
                    prints = {k: n for k, n in trade.have_prints(lid).items() if names.get(k) == name and n > 0}
                    free_here = [it for it in own if trade.have_count(it, lid) < int(it.get("count", 1))]
                    free_all = [it for it in coll if trade.have_count(it, lid) < int(it.get("count", 1))]
                    auto = bool(x.get("rule"))   # automatic list: fills itself
                    buttons = [{"fid": fn(lambda lid=lid: self._list_toggle("have", lid, True)), "text": tr("＋ this one"),
                                "tip": tr("Automatic list – fills itself") if auto else
                                tr("Offer one copy of this printing for trade"),
                                "enabled": bool(free_here) and not auto},
                               {"fid": fn(lambda lid=lid: self._have_all(lid)), "text": tr("＋ all"),
                                "tip": tr("All your copies of this card (every version) on the list"),
                                "enabled": bool(free_all) and not auto}]
                    for it, n in rows:
                        card = it.get("card") or {}
                        parts = [version(it.get("set") or card.get("set"),
                                         it.get("number") or card.get("collector_number")),
                                 lang_short(it.get("lang") or "en")] + _fin_parts(it)
                        top = int(it.get("count", 1))
                        entries.append({
                            "text": " · ".join(p for p in parts if p), "n": n, "here": it["uid"] in mine, "red": False,
                            "minus": fn(lambda it=it, l=lid, n=n: self._have_set(l, it, n - 1)),
                            "plus": fn(lambda it=it, l=lid, n=n: self._have_set(l, it, n + 1)) if n < top else "",
                            "remove": fn(lambda it=it, l=lid: self._have_set(l, it, 0))})
                    for pk, n in sorted(prints.items()):
                        s_, num, lang, foil = (pk.split("|") + ["", "", "", ""])[:4]
                        parts = [version(s_, num), lang_short(lang or "en")] + ([tr("Foil")] if foil == "1" else [])
                        entries.append({
                            "text": " · ".join(parts) + "  " + tr("(not in the collection)"), "n": n,
                            "here": s_ == my_set and num == str(my_num), "red": True,
                            "minus": fn(lambda k=pk, l=lid, n=n: self._have_print_set(l, k, n - 1)),
                            "plus": fn(lambda k=pk, l=lid, n=n: self._have_print_set(l, k, n + 1)),
                            "remove": fn(lambda k=pk, l=lid: self._have_print_set(l, k, 0))})
                used += len(entries)
                total = sum(e["n"] for e in entries)
                summary = " · ".join(f"{e['n']}× {e['text']}" for e in entries[:3]) + \
                    (f" · +{len(entries) - 3}" if len(entries) > 3 else "")
                if kind == "have" and not entries:   # trade list without the card: say why nothing works
                    summary = tr("automatic") if x.get("rule") else (
                        "" if any(it.get("name") == name for it in coll) else tr("not in collection"))
                sec["lists"].append({"key": f"{kind}|{lid}", "name": tr(x["name"]) if main else x["name"],
                                     "buttons": buttons, "entries": entries, "total": total, "summary": summary,
                                     "dim": kind == "have" and not entries and not any(it.get("name") == name
                                                                                       for it in coll)})
            data.append(sec)
        self.folds["lists"].set_sub("", tr(f"{used} entries") if used > 1 else (tr("1 entry") if used else
                                                                                 tr("keine")))

    def _have_all(self, lid):
        """All owned copies of this card (every version) onto the trade list."""
        from collection import trade
        coll = self.lib.ctrl.collection
        for it in [it for it in coll.items if it.get("name") == self.row["name"]]:
            if lid == trade.MAIN_HAVE:
                coll.update(it["uid"], trade=int(it.get("count", 1)))
            else:
                trade.set_have(lid, it["uid"], int(it.get("count", 1)))
        self._lists_changed(lid == trade.MAIN_HAVE)

    def _list_toggle(self, kind, lid, on):
        """Put a card on a list or take it off (wishlist: exactly this print)."""
        from collection import trade
        r = self.row
        if kind in ("wish", "custom"):
            if on:
                trade.add_wish(r["name"], 1, (r.get("set") or "").lower() or None, r.get("number"), list_id=lid)
            else:
                trade.remove_wish(r["name"], list_id=lid)
        else:
            coll = self.lib.ctrl.collection
            items = [it for it in self._own_items() if (it.get("lang") or "en") == (r.get("lang") or "en")] or \
                self._own_items()
            if on:
                for it in items:
                    n = trade.have_count(it, lid)
                    if n < int(it.get("count", 1)):
                        if lid == trade.MAIN_HAVE:
                            coll.update(it["uid"], trade=n + 1)
                        else:
                            trade.set_have(lid, it["uid"], n + 1)
                        break
                else:  # not in the collection: remember it as a print (red in the list)
                    pk = f"{(r.get('set') or '').lower()}|{r.get('number') or ''}|{r.get('lang') or 'en'}|" \
                         f"{1 if r.get('foil') else 0}"
                    trade.set_have_print(lid, pk, trade.have_prints(lid).get(pk, 0) + 1, r["name"])
            else:
                for it in self._own_items():
                    if lid == trade.MAIN_HAVE:
                        coll.update(it["uid"], trade=0)
                    else:
                        trade.set_have(lid, it["uid"], 0)
        self._lists_changed(kind == "have" and lid == trade.MAIN_HAVE)

    def _new_list(self, kind):
        from collection import trade
        name, ok = qdialogs.get_text_ok(tr("New list"), tr("Name of the list:"))
        if ok and name.strip():
            self._list_toggle(kind, trade.add_list(kind, name), True)

    def _own_items(self):
        return [it for it in self.lib.ctrl.collection.items if scryfall_id(it["id"]) == self.row["sid"]]

    def update_star(self):
        ctrl = getattr(self.lib, "ctrl", None)
        if ctrl is None or self.row is None:
            self.star_btn.setVisible(False)
            return
        from collection import trade
        name = self.row["name"]
        sc, num = str(self.row.get("set") or "").lower(), str(self.row.get("number") or "")
        # wish "any version": any print; pinned: only exactly this one
        on_list = any(w["name"] == name and (not w.get("set") or (str(w["set"]).lower() == sc
                                                                  and str(w.get("number") or "") == num))
                      for w in trade.wishes(raw=True))
        if not on_list:   # trade lists: only your copy of exactly this print
            from collection.collection import scryfall_id
            sid = self.row.get("sid")
            coll = [it for it in ctrl.collection.items if it.get("name") == name and scryfall_id(it["id"]) == sid]
            on_list = bool(trade.have_items(coll)) or any(
                k.split("|")[0].lower() == sc and (k.split("|") + [""])[1] == num
                for x in trade.lists("have") for k, v in trade.have_print_names(x["id"]).items() if v == name)
        self.star_btn.active = on_list
        self.star_btn.setVisible(True)

    def _print_picked(self, pr):
        """Print clicked in "All prints": normally shown as a comparison next to it; but the view can handle it
        itself (upgrade mode in the deck builder: the print appears in exactly this window)."""
        own = getattr(self.lib, "print_picked", None)
        if own is not None and own(pr, self):
            return
        self.lib.show_compare(pr)

    def show_empty(self, text):
        """Empty window with a sentence (e.g. "free space") – the window stays, nothing jumps."""
        self.show_row(None)
        self.image.setText(text)
        self.title.set_html(f"<span style='color:#8e8e8e'>{_esc(text)}</span>", animate=False)

    def show_row(self, row):
        self.row = row
        self.view_foil = None   # new card: back to the default finish
        self.token += 1
        self.update_star()
        self.full = None
        self.image.next_anim = "in"
        self.image.foil = self.is_foil()
        enabled = row is not None
        for f in self.folds.values():
            f.setVisible(enabled)
        self.folds["prints"].hide()
        self.flip.setVisible(False)
        if not enabled:
            self.image.setPixmap(None)
            self.image.setText(tr("Click a card on the left"))
            self.title.set_html("", animate=False)
            self.alt_names.set_html("", animate=False)
            self.cost.set_html("", animate=False)
            self.set_line.set_text("", None, animate=False)
            self.text.setText("")
            self.note.setText("")
            self.langbar.set_langs([], "en")
            self.langbar.hide()
            self.lang_note.setText("")
            return
        self.langbar.show()
        self.no_img = set()   # languages of this print without an image online (the English image is shown instead)
        self.lang_note.setText("")
        # the Library shows English; owned copies in another language: their language
        self.lang = row["lang"] if (self.lib.mode == "mine" and row["lang"] != "en") else "en"
        # default language (Settings → Collection): switch once it is clear the print exists in it
        pref = self.ctrl.settings.get("card_lang") or "en"
        self.want_lang = pref if self.lang == "en" and pref != "en" else None
        self.face = 0
        self.flip.setChecked(False)
        self.info = dict(row["db"]) if row.get("db") else None
        self.langbar.set_langs(None, self.lang)
        token = self.token
        run_async(self, lambda: library.print_languages(row["set"], row["number"]),
                  lambda res, err: self.on_langs(token, res, err))
        sid = row["sid"]  # everything Scryfall has (cached; offline: card database)
        run_async(self, lambda: library.card_full(sid), lambda res, err: self.on_full(token, res, err))
        self.flip.setVisible(self.has_back())
        from cards import finishes
        opts = finishes.options(row["card"])
        self.add_foil_ok = len(opts) > 1
        self.add_finish = opts[0]["key"]
        if self.lib.mode == "mine" and row.get("foil"):   # owned foil card: suggest it that way right away
            self.add_finish = finishes.current(dict(row["card"], foil=True, finish=row.get("finish")))
        self.add_is_foil = bool(next(o for o in opts if o["key"] == self.add_finish)["foil"])
        self.image.set_foil(self.add_is_foil or self.is_foil())
        self.add_n = 1
        self.fill_text()
        self.refresh_owned()
        self.refresh_lists()
        self.fill_altarts()
        self.update_add_btn()
        self.load_image()

    def fill_altarts(self):
        """Section „Alt arts“ (like „All printings“): your alt-art copies of this card and your alt-art contributions
        from the Scan Studio (with artist and status) – otherwise how to add one."""
        r = self.row
        if r is None:
            return
        name = r.get("name") or (r.get("card") or {}).get("name") or ""
        mine = [it for it in self.ctrl.collection.items
                if it.get("name") == name and (it.get("altart") or (it.get("card") or {}).get("altart"))]
        studio = getattr(self.ctrl, "studio", None)
        sent = studio.alt_arts_for(games.current().key, name) if studio is not None else []
        parts = []
        if mine:
            parts.append("<b>" + tr("In your collection") + "</b><br>" + "<br>".join(
                html.escape(f"{str(it.get('set') or '').upper()} #{it.get('number') or ''} · {int(it.get('count') or 1)}×")
                for it in mine))
        if sent:
            rows = []
            for s in sent:
                img = f"<img src='{s['thumb']}' height='72'> " if s["thumb"] else ""
                who = (" · " + tr("art by") + " " + html.escape(s["artist"])) if s["artist"] else ""
                rows.append(f"{img}{html.escape(s['title'])}{who}<br><font color='gray'>{html.escape(s['status'])}</font>")
            parts.append("<b>" + tr("Your contributions") + "</b><br>" + "<br><br>".join(rows))
        if not parts:
            parts.append("<font color='gray'>" + html.escape(tr(
                "No alt arts of this card yet. Painted or altered one? Add it in the Scan Studio as “Alt-Art” – with the "
                "artist.")) + "</font>")
        self.labels["altarts"].set_html("<br><br>".join(parts))
        n = len(mine) + len(sent)
        self.folds["altarts"].set_sub(str(n) if n else "", str(n) if n else "")
        self.folds["altarts"].show()

    def finish_options(self):
        """Finishes of the shown print: ["nonfoil", "foil"] (or only one; etched counts as foil)."""
        if self.row is None:
            return []
        return games.current().finish_info(self.row)[0]

    def finish_labels(self):
        """Label of the switch per game: Magic "Non-Foil | Foil", Pokémon "Normal | Reverse Holo" …"""
        if self.row is None:
            return {}
        return games.current().finish_info(self.row)[1]

    def is_foil(self):
        """Displayed finish: switched by the user – otherwise an owned foil copy or a print that only exists as
        foil."""
        if self.row is None:
            return False
        opts = self.finish_options()
        if getattr(self, "view_foil", None) is not None and len(opts) > 1:
            return bool(self.view_foil)
        return bool(self.row.get("foil")) or opts == ["foil"]

    def set_view_foil(self, on):
        """The "Non-Foil | Foil" switch clicked: shine on the image, price history and links follow (not saved)."""
        self.view_foil = bool(on)
        self.image.foil = self.is_foil()
        if self.price_chart.data:
            self.price_chart.set_finish("f" if self.is_foil() else "n")

    def has_back(self):
        faces = ((self.full or {}).get("card") or {}).get("card_faces") or []
        if len(faces) > 1 and faces[0].get("image_uris"):
            return True
        if self.info and self.info.get("faces"):
            faces = json.loads(self.info["faces"])
            return len(faces) > 1 and bool(faces[0].get("img_normal"))
        img = (self.row.get("img") or "").replace("_0.jpg", "_1.jpg")
        return bool(img) and img != self.row["img"] and (BASE / img).exists()

    def on_langs(self, token, res, err):
        if token != self.token:
            return
        self.langbar.set_langs(res or [], self.lang)
        if res and not self.langbar.has(self.lang):
            self.pick_lang("en")
        elif self.want_lang and self.langbar.has(self.want_lang):
            self.pick_lang(self.want_lang, quiet=True)
        self.want_lang = None
        self.update_add_btn()

    def on_full(self, token, res, err):
        if token != self.token or not res or not res.get("card"):
            return
        self.full = res
        self.fill_text()
        if self.flip.isHidden() and self.has_back():
            self.flip.setVisible(True)

    def card_data(self):
        """Scryfall record: complete (online/cached) or rebuilt from the card database."""
        if self.full and self.full.get("card"):
            return self.full["card"], True
        r, i = self.row, self.info or {}
        faces = json.loads(i["faces"]) if i.get("faces") else []
        c = {"name": r["name"], "set": r["set"], "collector_number": r["number"], "rarity": r.get("rarity"),
             "lang": "en"}
        for key in ("mana_cost", "cmc", "type_line", "oracle_text", "power", "toughness", "loyalty", "flavor_text",
                    "artist", "set_name", "layout", "border_color", "edhrec_rank"):
            if i.get(key) not in (None, ""):
                c[key] = i[key]
        if i.get("released"):
            c["released_at"] = i["released"]
        for key in ("colors", "color_identity"):
            if i.get(key) is not None:
                c[key] = list(i[key])
        for key, sep in (("keywords", ", "), ("finishes", ","), ("promo_types", ","), ("frame_effects", ",")):
            if i.get(key):
                c[key] = [x for x in i[key].split(sep) if x]
        for key in ("reserved", "game_changer", "full_art"):
            if i.get(key):
                c[key] = True
        if i.get("flavor_name"):
            c["flavor_name"] = i["flavor_name"]
        if i.get("booster") is not None:
            c["booster"] = bool(i["booster"])
        if i.get("legalities"):
            ok = json.loads(i["legalities"])
            c["legalities"] = {k: "legal" if k in ok else "not_legal" for k, _ in LEGAL_FORMATS}
        c["prices"] = {k: (f"{i[k]:.2f}" if i.get(k) is not None else None)
                       for k in ("eur", "eur_foil", "usd", "usd_foil")}
        if not i:  # without a card database: at least the prices from the collection/catalog
            c["prices"] = {"eur": _price_str(r["card"].get("eur")), "eur_foil": _price_str(r["card"].get("eur_foil"))}
        if len(faces) > 1:
            c["card_faces"] = faces
        if r["card"].get("url"):
            c["scryfall_uri"] = r["card"]["url"]
        return c, False

    def fill_text(self):
        r = self.row
        if r is None:
            return
        c, complete = self.card_data()
        printed = self.langbar.printed_name(self.lang) if self.lang != "en" else None
        light = look.skin_color("text_light")
        head = (f"<span style='font-size:21px; font-weight:700; color:{look.rarity_color(r.get('rarity'))}'>"
                f"{_esc(c.get('name') or r['name'])}</span>")
        alt = []
        if c.get("flavor_name"):  # special name on the card (e.g. "Stay with Me") – stays findable via the search
            alt.append(f"<span style='color:{light}; font-style:italic'>„{_esc(c['flavor_name'])}“</span>")
        if printed and printed != r["name"]:  # printed name of this language version
            alt.append(f"<span style='color:{light}'>{_esc(printed)}</span>")
        self.alt_names.set_html("&nbsp;&nbsp;".join(alt))
        cost = c.get("mana_cost") if not c.get("card_faces") else ""
        self.cost.set_html(_symbols(cost, size=21) if cost else "", animate=False)
        rar = RARITY.get(r.get("rarity"), r.get("rarity") or "")  # (shown below under "Print")
        self.title.setText(head)
        self.set_line.set_text(c.get("set_name") or r["set"], look.skin_color("text_light"))

        # rules text: one box per face
        faces = c.get("card_faces") if c.get("card_faces") and len(c["card_faces"]) > 1 else [c]
        self.text.setText("".join(_rules_box(f, show_name=len(faces) > 1) for f in faces))
        sec = {}
        # prices
        pr = c.get("prices") or {}
        from cards import shoplinks
        self.shop_links = shoplinks.market_links(c, self.ctrl.settings)   # "Marketplaces" button next to the prices
        shop_url = {m["key"]: m["url"] for m in self.shop_links}
        shop_foil = {m["key"]: m["url"] for m in shoplinks.market_links(c, self.ctrl.settings, foil=True)}
        rows = []
        est = games.current().price_estimated(r.get("sid") or "")   # euros only converted from TCGplayer
        fw = tr(games.current().foil_word)   # "Foil" or "Reverse Holo"
        tw = "Trend " if games.current().price_trend_word else ""
        for key, label in (("eur", "Cardmarket Trend"), ("eur_foil", f"Cardmarket {tw}{fw}"),
                           ("eur_etched", "Cardmarket Trend Etched"), ("usd", "TCGplayer Market"),
                           ("usd_foil", f"TCGplayer {'Market ' if tw else ''}{fw}"), ("usd_etched", "TCGplayer Market Etched"),
                           ("tix", "MTGO (Tix)")):
            if key == "tix" and not self.ctrl.settings.get("show_tix"):   # Magic Online: only on request
                continue
            v = pr.get(key)
            if v:
                unit = "€" if key.startswith("eur") else "$" if key.startswith("usd") else "Tix"
                urls = shop_foil if ("foil" in key or "etched" in key) else shop_url
                url = urls.get("cardmarket" if key.startswith("eur") else "tcgplayer" if key.startswith("usd") else "")
                # name of the price = link to the page (Cardmarket or TCGplayer)
                lab = (f"<a href='{_esc(url)}' style='color:#8a91a8; text-decoration:none; white-space:nowrap'>"
                       f"{label}&nbsp;↗</a>" if url else label)
                if est and key == "eur":   # no Cardmarket price: converted from TCGplayer
                    lab = label + " <span style='color:#5c6380'>" + tr("(converted from TCGplayer)") + "</span>"
                    rows.append((lab, f"<b>≈ {v.replace('.', ',')} {unit}</b>"))
                    continue
                rows.append((lab, f"<b>{v.replace('.', ',')} {unit}</b>"))
            elif "etched" not in key:  # missing (e.g. new card, not on MTGO): show anyway
                rows.append((label, "<span style='color:#5c6380'>–</span>"))
        stamp = self.full.get("fetched") if complete and self.full else None
        trend = []  # collapsed: Cardmarket trend price (Scryfall "eur" = Cardmarket trend)
        if pr.get("eur"):
            trend.append(tr("Cardmarket trend ") + ("≈ " if est else "") + eur(float(pr["eur"])))
        if pr.get("eur_foil"):
            trend.append((f"{fw} " if trend else f"{tr("Cardmarket trend")} {fw} ") + eur(float(pr["eur_foil"])))
        if not trend and pr.get("usd"):
            trend.append("TCGplayer " + pr["usd"].replace(".", ",") + " $")
        self.folds["prices"].set_sub(f"{tr("as of")} {time.strftime('%d.%m.%Y', time.localtime(stamp))}"
                                     if stamp else "", " · ".join(trend))
        sec["prices"] = _table(rows, 58) if rows else ""   # names with a link on one line
        # card
        rows = []
        cmc = c.get("cmc") if games.current().key == "mtg" else None
        if games.current().key != "mtg":   # other games: card type and HP instead of mana value/colors
            dbr = r.get("db") or {}
            own = games.current().info_rows(dbr) if dbr else None   # the game's own values (Lorcana)
            if own is not None:
                rows += [(label, _esc(str(v))) for label, v in own]
            if own is None and dbr.get("type_line"):
                rows.append((tr("Card type"), _esc(dbr["type_line"])))
            if own is None and dbr.get("power"):
                rows.append((tr("HP"), _esc(str(dbr["power"]))))
        if cmc is not None:
            rows.append((tr("Mana value"), f"{cmc:g}"))
        for key, label in (("colors", tr("Colors")), ("color_identity", tr("Color identity")),
                           ("color_indicator", tr("Color indicator")), ("produced_mana", tr("Produces mana"))):
            if games.current().key != "mtg":
                break
            if c.get(key) is not None and (c[key] or key != "color_indicator"):
                rows.append((label, _color_list(c[key])))
        if c.get("keywords"):
            rows.append((tr("Keywords"), ", ".join(_esc(k) for k in c["keywords"])))
        if c.get("hand_modifier") or c.get("life_modifier"):
            rows.append((tr("Hand / life"), f"{c.get('hand_modifier', '–')} / {c.get('life_modifier', '–')}"))
        if c.get("layout") and games.current().key == "mtg":
            rows.append(("Layout", _pretty(c["layout"])))
        related = [p for p in c.get("all_parts") or [] if p.get("name") != c.get("name")]
        if related:
            rows.append((tr("Related cards"), "<br>".join(
                f"{_esc(p['name'])} <span style='color:#8a91a8'>· {_pretty(p.get('component', ''))} · "
                f"{_esc(p.get('type_line') or '')}</span>" for p in related)))
        sec["card"] = _table(rows) if rows else ""
        # print
        rows = []
        if c.get("set_name"):
            st = f" · {_pretty(c['set_type'])}" if c.get("set_type") else ""
            rows.append(("Set", f"{_esc(c['set_name'])} ({c['set'].upper()}){st}"))
        rows.append((tr("Number"), f"#{_esc(c.get('collector_number') or r['number'])} · {rar}"))
        if c.get("released_at"):
            rows.append((tr("Released"), _date(c["released_at"])))
        if c.get("artist"):   # a click searches all cards by the artist (Library → All cards, a:"…")
            from urllib.parse import quote
            rows.append((tr("Illustration"), f"<a href='bc-artist:{quote(c['artist'])}' style='color:#d6d6d6'>"
                                             f"{_esc(c['artist'])}</a>"))
        if c.get("lang"):
            rows.append((tr("Language of this record"), LANG_NAME.get(c["lang"], c["lang"])))
        if c.get("finishes"):
            rows.append((tr("Finishes"), ", ".join(FINISH_NAMES.get(x, _pretty(x)) for x in c["finishes"])))
        looks = []
        if c.get("frame"):
            looks.append(tr(f"Frame {c['frame']}"))
        looks += [_pretty(x) for x in c.get("frame_effects") or []]
        if c.get("border_color"):
            looks.append(tr(f"Border {BORDER_NAMES.get(c['border_color'], c['border_color'])}"))
        for key, label in (("full_art", "Full Art"), ("textless", tr("Textless")), ("oversized", tr("Oversized"))):
            if c.get(key):
                looks.append(label)
        if looks:
            rows.append((tr("Look"), " · ".join(looks)))
        if c.get("watermark"):
            rows.append((tr("Watermark"), _pretty(c["watermark"])))
        if c.get("security_stamp"):
            rows.append((tr("Security stamp"), _pretty(c["security_stamp"])))
        if c.get("promo_types"):
            rows.append((tr("Promo"), ", ".join(_pretty(x) for x in c["promo_types"])))
        flags = []
        if c.get("reprint") is False:
            flags.append(tr("First printing"))
        elif c.get("reprint"):
            flags.append(tr("Reprint"))
        if c.get("booster") is not None:
            flags.append(tr("in boosters") if c["booster"] else tr("not in boosters"))
        for key, label in (("reserved", "Reserved List"), ("game_changer", "Game Changer"),
                           ("story_spotlight", "Story Spotlight"), ("variation", tr("Variant")),
                           ("digital", tr("digital only")), ("promo", "Promo"),
                           ("content_warning", tr("Content warning"))):
            if c.get(key):
                flags.append(label)
        if flags:
            rows.append((tr("Traits"), " · ".join(flags)))
        if c.get("games"):
            rows.append((tr("Playable in"), ", ".join(GAME_NAMES.get(g, g) for g in c["games"])))
        sec["print"] = _table(rows)
        # popularity
        rows = []
        if c.get("edhrec_rank"):
            rows.append(("EDHREC", tr(f"Seat {c['edhrec_rank']:,}").replace(",", ".")))
        if c.get("penny_rank"):
            rows.append(("Penny Dreadful", tr(f"Seat {c['penny_rank']:,}").replace(",", ".")))
        prints = (self.full or {}).get("prints") if complete else None
        if not (prints and prints.get("list")):
            prints = self.local_prints()  # immediately from the card database – Scryfall only adds to it later
        if prints and prints.get("list"):
            lst = prints["list"]
            first = lst[0]
            txt = tr(f"{prints['total']} printings") if prints.get("total", 0) != 1 else tr("only printing")
            if prints.get("total", 0) != 1:
                txt += tr(f" · first printed {_date(first.get('date'))} in {_esc(first.get('set_name'))}")
            rows.append((tr("Printings"), txt))
        sec["popular"] = _table(rows) if rows else ""
        sec["legal"] = _legal_table(c["legalities"]) if c.get("legalities") else ""
        # rulings
        rulings = (self.full or {}).get("rulings") if complete else None
        if rulings:
            sec["rulings"] = "".join(f"<p style='margin:0 0 8px 0'><span style='color:#62f2ff'>"
                                     f"{_date(x.get('date'))}</span>&nbsp; "
                                     f"{_symbols(_esc(x.get('text') or ''), escaped=True)}</p>" for x in rulings)
        self.folds["rulings"].set_sub(str(len(rulings)) if rulings else "", str(len(rulings)) if rulings else tr("keine"))
        self.rules_btn.empty = not rulings
        self.fill_prints(prints, c.get("name") or r["name"])
        # IDs & links
        rows = []
        for key, label in (("multiverse_ids", "Multiverse (Gatherer)"), ("mtgo_id", "MTGO"), ("arena_id", "Arena"),
                           ("tcgplayer_id", "TCGplayer"), ("cardmarket_id", "Cardmarket"), ("id", "Scryfall"),
                           ("oracle_id", "Oracle"), ("illustration_id", tr("Illustration"))):
            v = c.get(key)
            if v:
                rows.append((label, f"<span style='color:#aab1c8'>{', '.join(map(str, v)) if isinstance(v, list) else v}"
                                    f"</span>"))
        sec["ids"] = _table(rows) if rows else ""
        # links by topic: card info · buy & sell · Magic Online
        info, shop, digital = [], [], []
        if c.get("scryfall_uri"):
            info.append(("Scryfall", c["scryfall_uri"]))
        for key, label in (("gatherer", "Gatherer"), ("edhrec", "EDHREC")):
            if (c.get("related_uris") or {}).get(key):
                info.append((label, c["related_uris"][key]))
        for m in getattr(self, "shop_links", None) or []:   # Cardmarket, TCGplayer, eBay, Kleinanzeigen
            shop.append((m["label"], m["url"]))
        if (c.get("purchase_uris") or {}).get("cardhoarder"):
            digital.append(("Cardhoarder", c["purchase_uris"]["cardhoarder"]))

        def joined(items):
            return " &nbsp;·&nbsp; ".join(f"<a style='color:#d0d0d0' href='{_esc(u)}'>{label}</a>" for label, u in items)
        groups = [(tr("Info"), info), (tr("Buy & sell"), shop), (tr("Magic Online"), digital)]
        sec["links"] = _table([(lab, joined(items)) for lab, items in groups if items], 30)
        empty = ("<span style='color:#6c7390'>" + (tr("keine") if complete else
                 tr("none – more info comes from Scryfall (not available offline)")) + "</span>")
        for key, lab in self.labels.items():  # all areas stay visible, empty = "none"
            lab.setText(sec.get(key) or empty)
            self.folds[key].show()
            if key not in ("prices", "rulings"):
                self.folds[key].set_sub(self.folds[key].head.sub, "" if sec.get(key) else tr("keine"))
        if not sec.get("rulings"):
            self.folds["rulings"].set_sub("", tr("keine"))
        if self.price_chart.set_card(r.get("sid"), bool(r.get("foil")) or self.is_foil()):
            self.folds["prices"].show()
        self.note.setText("" if complete else tr("More info (rulings, all printings, IDs …) is loaded from Scryfall – offline only the card database data."))

    def local_prints(self):
        """All prints of this card from the card database (offline, immediately) in the format of the Scryfall list."""
        info = self.info or {}
        oid = info.get("oracle_id")
        if not oid or not carddb.exists():
            return None
        try:
            with carddb.connection() as con:
                rows = con.execute(
                    "SELECT id, set_code, set_name, number, released, rarity, eur, eur_foil, finishes, img_small, booster "
                    "FROM cards WHERE oracle_id = ? AND layout NOT IN ('art_series') ORDER BY released, set_code, "
                    "CAST(number AS INTEGER), number", (oid,)).fetchall()
        except Exception:  # noqa: BLE001
            return None
        lst = [{"id": r["id"], "set": r["set_code"], "set_name": r["set_name"], "number": r["number"],
                "date": r["released"], "rarity": r["rarity"], "eur": r["eur"], "eur_foil": r["eur_foil"],
                "finishes": (r["finishes"] or "").split(",") if r["finishes"] else [], "img": r["img_small"],
                "booster": bool(r["booster"])} for r in rows]
        return {"total": len(lst), "list": lst, "local": True} if lst else None

    def fill_prints(self, prints, name):
        lst = (prints or {}).get("list") or []
        fold = self.folds["prints"]
        fold.show()  # the area is always there – empty with a notice instead of disappearing
        if len(lst) < 2:
            loaded = bool(self.full and self.full.get("card"))
            self.strip.hide()
            self.prints_empty.setText(tr("no other printings") if loaded else tr("not loaded from Scryfall yet"))
            self.prints_empty.show()
            fold.set_sub("", tr("keine") if loaded else "–")
            return
        self.strip.show()
        self.prints_empty.hide()
        more = (prints.get("total") or len(lst)) - len(lst)
        # only the number – that a click compares to the left is noticed on the first click
        fold.set_sub(f"{prints.get('total') or len(lst)}"
                     + (tr(f" · the first {len(lst)}") if more > 0 else ""), str(prints.get("total") or len(lst)))
        if [x["id"] for x in self.strip.model_.rows] != [x["id"] for x in lst]:
            self.strip.set_prints(lst, name)
        self.lib.update_marks()

    # --- Image, language, back face ---
    def img_lang(self):
        """Language of the shown image: the chosen one – or English if there is none online in it (or the game has
        images in English only, like Yu-Gi-Oh!)."""
        import games
        if not games.current().lang_images:
            return "en"
        return "en" if self.lang in getattr(self, "no_img", ()) else self.lang

    def _locale_print(self):
        """Is the shown print one the game marks as shown with another print's image (games.<game>.locale_print)?"""
        check = getattr(games.current(), "locale_print", None)
        return bool(check and self.row and check(re.sub(r"_\d+$", "", str(self.row.get("sid") or ""))))

    def image_key(self):
        return f"big_{self.row['sid']}_{self.img_lang()}_{self.face}"

    def load_image(self):
        r = self.row
        key = self.image_key()
        self._stand_in = None
        il = self.img_lang()
        if self._locale_print():
            # Yu-Gi-Oh! prints from Japan/Korea/Asia/Spain (ygo-locale.sqlite): no image of their own anywhere allowed
            self.lang_note.setText(tr("Image: English print"))
        elif il == self.lang:
            self.lang_note.setText("")
        elif getattr(self, "img_offline", False):
            self.lang_note.setText(tr(f"{lang_short(self.lang)} image couldn't be loaded (offline?) – showing EN"))
        else:
            self.lang_note.setText(tr(f"No {lang_short(self.lang)} image online – showing EN"))
        local_rel = lang_img(image_rel(r["set"], r["number"], self.face), il)
        if il != "en" and not (BASE / local_rel).exists():
            self.image.setPixmap(None)
            self.image.setText(tr(f"Loading {lang_short(il)} version …"))
            token, lang = self.token, il
            entry = dict(r["card"], img=image_rel(r["set"], r["number"], self.face))
            run_async(self, lambda: library.fetch_lang_print(entry, lang),
                      lambda res, err: self.on_lang_image(token, lang, res, err))
            return
        url = None
        if il == "en":
            faces = json.loads(self.info["faces"]) if self.info and self.info.get("faces") else []
            if faces and faces[0].get("img_normal"):
                url = faces[min(self.face, len(faces) - 1)].get("img_normal")
            else:
                url = (self.info or {}).get("img_normal")
            # print missing from the database (r["normal"]: image of another print of the same card, mine_rows)
            url = url or (r.get("normal") if not self.info else None) or                 library.image_url(r["set"], r["number"], "en", "normal", self.face)
            big = LARGE / f"{r['sid']}_{self.face}.jpg"
            local = BASE / local_rel
            if not url and not local.exists() and not big.exists():   # no image online (e.g. some Pokémon prints)
                self.src_pm = None
                self.image.set_missing(r.get("name") or "")
                return
            # large version (the detail view can be very wide), separate cache; offline: local image
            url = (url or "").replace("/normal/", "/large/").replace("version=normal", "version=large") or None
            if key not in self.lib.loader.cache and not big.exists() and local.exists():
                # the image is on disk: show it immediately instead of waiting for the download of the large version;
                # only fetch the large one if the view is wider than the normal image (488 px)
                pm_local = QtGui.QPixmap(str(local))
                if not pm_local.isNull():
                    self.set_pixmap(pm_local)
                    if self.needs_large(pm_local):
                        pm = self.lib.loader.get(key, 0, big, url, big, fallback=local)
                        if pm is not None:
                            self.src_pm = pm
                            self.image.replace_pixmap(pm)
                        else:
                            self._stand_in = key  # the large version silently replaces the image, no new fly-in
                    return
            pm = self.lib.loader.get(key, 0, big, url, big, fallback=local)
        else:
            pm = self.lib.loader.get(key, 0, BASE / local_rel, None, None)
        if pm is not None:
            self.set_pixmap(pm)
            return
        stand_in = self.small_image(r)
        if stand_in is not None and not stand_in.isNull():
            self.set_pixmap(stand_in)
            self._stand_in = key  # the large image replaces it silently, without flying in again
            return
        self.src_pm = None
        self.image.setPixmap(None)
        self.image.set_loading(r.get("name") or "")
        QtCore.QTimer.singleShot(self.LOAD_TIMEOUT_MS, lambda k=key: self._load_timeout(k))

    def _load_timeout(self, key):
        """Still loading the same card after LOAD_TIMEOUT_MS: show it as not available (NoImage). If the image comes
        after all, on_image puts it in as usual."""
        if self.row is not None and key == self.image_key() and self.image.loading_name and not self.image.missing                 and getattr(self, "src_pm", None) is None:
            self.image.set_missing(self.row.get("name") or "")

    def on_lang_image(self, token, lang, res, err):
        if token != self.token or lang != self.lang:
            return
        if err or not res:   # not online in this language: keep the language (name, adding), show the English image
            self.no_img.add(lang)
            self.img_offline = err is not None and not isinstance(err, LookupError)   # network trouble, not missing
        self.load_image()

    def small_image(self, r):
        """Small image of this print that is already there (grid, print bar, disk) – as a placeholder
        until the large one has loaded. None if there is none."""
        sid = r.get("sid") if isinstance(r, dict) else None
        if not sid:
            return None
        best = None
        for key, pm in list(self.lib.loader.cache.items()):
            if key.startswith(f"{sid}_") and (best is None or pm.width() > best.width()):
                best = pm
        if best is None:
            # grid images (every language, normal before small), then the owned image on disk
            lang = getattr(self, "lang", "en") or "en"
            names = [f"{sid}_{lang}_n.jpg", f"{sid}_en_n.jpg"]
            names += sorted((p.name for p in THUMBS.glob(f"{sid}_*_n*.jpg")), key=len)
            names += [f"{sid}_{lang}_s.jpg", f"{sid}_en_s.jpg"] + [p.name for p in THUMBS.glob(f"{sid}_*_s*.jpg")]
            paths = [THUMBS / n for n in dict.fromkeys(names)]
            if r.get("set") and r.get("number"):
                paths.append(BASE / image_rel(r["set"], r["number"], getattr(self, "face", 0)))
            for path in paths:
                if path.exists():
                    pm = QtGui.QPixmap(str(path))
                    if not pm.isNull():
                        best = pm
                        break
        return best if best is not None and not best.isNull() else None

    def needs_large(self, pm):
        """Is the image displayed wider than it is? (then the large version is worth it)"""
        screen = QtGui.QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        width = detail_width(self.ctrl.settings.get(getattr(self.lib, "width_key", None) or "lib_detail_w"))
        return (width - 24 - CARD_MARGIN) * dpr > pm.width() * 1.05

    def on_image(self, key):
        if self.row is not None and key == self.image_key():
            pm = self.lib.loader.cache.get(key)
            if pm is not None and self.__dict__.get("_stand_in") == key and self.image.pm is not None:
                self._stand_in = None
                self.src_pm = pm
                self.image.replace_pixmap(pm)
            elif pm is not None:
                if self.image.loading_name:  # the loading placeholder was running before: fade in softly
                    self.image.next_anim = "fade"
                self.set_pixmap(pm)
            elif getattr(self, "src_pm", None) is None or self.src_pm.isNull():
                self.image.set_missing(self.row.get("name"))  # crossed-out card (NoImage); otherwise the local image stays

    def set_pixmap(self, pm):
        self.src_pm = pm
        self.image.setPixmap(pm)

    def pick_lang(self, lang, quiet=False):
        """quiet: swap silently (automatically into the default language, right after opening)."""
        if self.row is None:
            return
        import games
        if lang != "en" and not games.current().lang_images:
            # only the name/text changes, the image stays English – with a short notice next to the languages
            self.lang = lang
            self.langbar.set_current(lang)
            self.langbar.hint = "" if quiet else tr("Card image not available in this language")
            self.langbar.hint_rev += 1
            self.fill_text()
            self.update_add_btn()
            return
        if lang != self.lang:
            self.image.next_anim = "quiet" if quiet else "swap"
        self.lang = lang
        self.langbar.set_current(lang)
        self.fill_text()
        self.update_add_btn()
        self.load_image()

    def toggle_face(self):
        self.face = 1 if self.flip.isChecked() else 0
        self.image.next_anim = "flip"
        self.load_image()

    def update_add_btn(self):
        self.add_text = tr(f"Add ({lang_short(self.lang)})")

    def set_add_foil(self, on):
        self.add_is_foil = bool(on)
        self.image.set_foil(self.add_is_foil or self.is_foil())

    def set_add_finish(self, key):
        from cards import finishes
        if self.row is None:
            return
        o = next((o for o in finishes.options(self.row["card"]) if o["key"] == key), None)
        if o is not None:
            self.add_finish = key
            self.set_add_foil(o["foil"])

    # --- Owned copies ---
    def refresh_owned(self):
        """Owned copies of this card -> own_view [(copy, language codes)], own_total."""
        self.own_view, self.own_total = [], ""
        if self.row is None:
            return
        items = [it for it in self.ctrl.collection.items if scryfall_id(it["id"]) == self.row["sid"]]
        from cards import finishes
        by = {}   # collapsed: quantity per finish ("3× · 2× Reverse Holo")
        for it in items:
            lb = finishes.full_label(it)
            by[lb] = by.get(lb, 0) + it.get("count", 1)
        parts = [f"{n}×" + (f" {tr(lb)}" if lb else "") for lb, n in sorted(by.items(), key=lambda kv: kv[0] != "")]
        self.folds["own"].set_sub("", " · ".join(parts) or tr("keine"))  # collapsed: quantity normal / foil
        if not items:
            return
        items.sort(key=lambda it: (it.get("lang") != self.lang, it.get("added") or 0))
        langs = [c for c, *_ in (self.langbar.langs or [(c, s, None, None) for c, s, _ in LANGS])]
        for it in items:
            codes = langs + ([it.get("lang", "en")] if it.get("lang", "en") not in langs else [])
            self.own_view.append((it, codes))
        total = sum(it.get("count", 1) for it in items)
        value = sum((item_price(it) or 0) * it.get("count", 1) for it in items)
        self.own_total = tr(f"Together {total}× · {eur(value)}")

    def set_add_cond(self, c):
        """Condition of the cards you add – stays set (like the edition)."""
        from cards import conditions
        d = {}
        conditions.apply(d, c.get("cond"), c.get("grade_by"), c.get("grade"), c.get("cond_note"))
        self.add_cond = d

    def set_add_edition(self, key):
        self.add_edition = key or ""
        self.update_add_btn() if hasattr(self, "update_add_btn") else None

    def add(self):
        if self.row is None:
            return
        card = dict(self.row["card"])
        from cards import finishes
        ed = self.add_edition if any(e["key"] == self.add_edition for e in finishes.editions(card)) else None
        self.ctrl.collection_add(card, self.lang, self.add_is_foil, self.add_n, finish=self.add_finish or None,
                                 edition=ed, cond=self.add_cond or None)
        self.lib.refresh(keep=True)
        self.refresh_owned()


class CompareState(QtCore.QObject):
    """Compare (second detail view) open/closed – Qt Quick slides it in. closing: currently sliding out."""

    def __init__(self, panel, on_change=None, parent=None):
        super().__init__(parent)
        self.panel, self.on_change, self.closing = panel, on_change or (lambda: None), False

    def open(self, animate=True):
        self.closing = False
        self.panel.show()

    def close(self, animate=True):
        if not self.panel.isVisible():
            return
        self.closing = False
        self.panel.hide()
        self.on_change()


class _Instant:
    """Transition: apply immediately (Qt Quick animates by itself)."""
    running = False

    @staticmethod
    def run(apply, *_, then=None, **__):
        apply()
        if then:
            then()


# ---------- Detail outside the Library (sessions, trade) ----------
class DetailHost(QtCore.QObject):
    """Detail and compare view outside the Library. A click on another print shows it as a comparison
    (or, without compare, in the same view). Pin: the next card opens next to it."""

    def __init__(self, parent, ctrl, context, on_close=None, with_compare=True, width_key=None):
        super().__init__(parent)
        self.ctrl, self.detail_context, self.mode = ctrl, context, "all"
        self.width_key = width_key
        self.loader = ImageLoader(self, keep=10)   # only the large images of the detail view (~2 MB each)
        self.on_close = on_close or (lambda: None)
        self.detail_pinned = False
        self.supports_pin = with_compare
        self.morph = _Instant()
        self.panel = DetailState(self)
        self.compare = DetailState(self, compare=True) if with_compare else None
        self.slide = CompareState(self.compare, self.update_marks, self) if with_compare else None

    def swap_panels(self):
        a, b = self.compare.row if self.compare else None, self.panel.row if self.panel else None
        if a is None or b is None or not self.compare.isVisible():
            return
        self.panel.show_row(a)
        self.compare.show_row(b)
        self.update_marks()
        self._pin_after_swap(self.panel)

    @staticmethod
    def _pin_after_swap(panel):
        """After the side swap the card in the detail view is pinned automatically."""
        if not panel.pin_btn.isHidden():
            panel.pin_btn.setChecked(True)

    def open_detail(self, row):
        """Show the detail view; if it is already open, only the card changes (pinned: new card next to it)."""
        if self.panel.isVisible():
            if self.detail_pinned and self.compare is not None:
                self.compare.show_row(row)
                self.slide.open()
                self.update_marks()
                return
            if self.compare is not None and self.compare.isVisible():
                self.slide.close(False)
            self.panel.show_row(row)
            self.update_marks()
            return
        self.panel.show()
        self.panel.show_row(row)
        self.update_marks()

    def hide_detail(self):
        """Close the detail view (and compare)."""
        if not self.panel.isVisible():
            return
        self.panel.pin_btn.setChecked(False)  # closed: pin released
        if self.compare is not None and self.compare.isVisible():
            self.slide.close(False)
        self.panel.hide()
        self.panel.show_row(None)

    @property
    def owned_cache(self):
        return self.ctrl.collection.owned()

    def row_from_db(self, r):
        return LibraryCore.row_from_db(self, r)

    def detail_panels(self):
        return [x for x in (self.panel, self.compare) if x is not None]

    def set_fold(self, key, on):
        folded = set(self.ctrl.settings.get("detail_folded") or [])
        folded.discard(key) if on else folded.add(key)
        self.ctrl.settings["detail_folded"] = sorted(folded)
        self.ctrl.settings_changed()
        for panel in self.detail_panels():
            panel.set_fold(key, on)

    def show_compare(self, pr):
        """Show another print as a comparison (without a compare view: in the same view)."""
        if self.compare is None:
            self.panel.show_row(LibraryCore.row_for_print(self, pr))
            self.update_marks()
            return
        if self.panel.row is not None and pr["id"] == self.panel.row["sid"]:
            self.close_compare()
            return
        self.compare.show_row(LibraryCore.row_for_print(self, pr))
        self.slide.open()
        self.update_marks()

    def close_compare(self, animate=True):
        if self.compare is not None and self.compare.isVisible():
            self.slide.close(False)

    def close_detail(self):
        self.on_close()

    def update_marks(self):
        marks = {}
        if self.panel.row is not None:
            marks[self.panel.row["sid"]] = "main"
        if self.compare is not None and self.compare.isVisible() and self.compare.row is not None:
            marks[self.compare.row["sid"]] = "compare"
        for panel in self.detail_panels():
            panel.strip.set_marks(marks)

    def refresh(self, keep=False):
        self.panel.refresh_owned()

    def row_for_entry(self, e):
        """Row for a scanned card (session): from the card database, otherwise from the session data."""
        sid = scryfall_id(e["id"])
        db = carddb.cards_by_ids({sid}) if carddb.exists() else {}
        if sid in db:
            row = LibraryCore.row_from_db(self, db[sid])
            row.update(lang=e.get("lang") or "en", foil=bool(e.get("foil")))
            return row
        card = {k: e.get(k) for k in ("id", "name", "set", "number", "rarity", "finishes", "booster", "eur",
                                      "eur_foil", "img", "url")}
        return {"key": f"{sid}|{e.get('lang') or 'en'}|{int(bool(e.get('foil')))}", "sid": sid, "name": e["name"],
                "set": e["set"], "number": e["number"], "rarity": e.get("rarity"), "lang": e.get("lang") or "en",
                "foil": bool(e.get("foil")), "count": self.owned_cache.get(sid, 0), "price": e.get("price"),
                "img": e.get("img"), "thumb": None, "normal": None, "card": card, "db": None, "last": 0}


# ---------- Library ----------
class RowModel(QtCore.QObject):
    """Library result: rows; reset = refilled, appended(from, to) = appended (scrolling)."""
    reset = QtCore.Signal()
    appended = QtCore.Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []

    def rowCount(self):
        return len(self.rows)

    def set_rows(self, rows):
        self.rows = list(rows)
        self.reset.emit()

    def append(self, rows):
        if not rows:
            return
        start = len(self.rows)
        self.rows += rows
        self.appended.emit(start, len(self.rows) - 1)


class Status(QtCore.QObject):
    """Line below the grid (count, value …)."""
    changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""

    def text(self):
        return self._text

    def setText(self, t):
        self._text = t or ""
        self.changed.emit()


def is_altart(row):
    """The card is an alt art (flag on the entry or on the card – set by approved studio contributions)."""
    return bool(row.get("altart") or (row.get("card") or {}).get("altart"))


class LibraryCore(QtCore.QObject):
    """The Library: own collection (mode "mine") or all cards of the card database ("all"), searched with the
    SearchBox, sorted, grouped into tiles (model.rows); detail and compare view as DetailState.
    Reuse (trade): source = its own card source instead of the collection (groups/owned/items/rev),
    extra_filter(row) -> bool for extra chips, show_holders = friends' card backs on the cards."""
    changed = QtCore.Signal()   # mode, detail/compare, columns …
    PAGE = 300
    view_rows = 4   # rows the grid shows (qlibrary.setViewRows) – "All cards" loads those + one more row
    # slider 5–10 / 4–9 / 3–8 depending on the work area; with set completion open ("_c") one step less each
    START = {"full": 5, "medium": 4, "small": 3, "full_c": 4, "medium_c": 3, "small_c": 2}
    SPAN = 5                    # slider: START … START + SPAN (per work area)
    HI = None                   # or fixed upper limits per area (e.g. binder: 6 / 4 / 3)
    COLS_KEY = "lib_cols_area"  # setting in which each view remembers its card count
    supports_pin, detail_pinned = True, False
    source, extra_filter, drag_mime, show_holders = None, None, None, False
    detail_context, width_key = "library", "lib_detail_w"

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.mode, self.offset, self.more, self.seen_rev = "mine", 0, False, -1
        self.loader = ImageLoader(self, keep=10)   # large detail images; Qt Quick keeps the tiles (grid cacheBuffer)
        self.owned_cache, self.detail_open = {}, False
        self.current = -1                                 # selected tile (detail view)
        self.appear_t0 = None                             # new search (Qt Quick fades in)
        self.morph = _Instant()
        self.bar = SearchBox(ctrl, "library")
        b = self.bar  # short names as before
        self.search, self.adv_btn, self.adv_note = b.search, b.adv_btn, b.adv_note
        self.lang_filter, self.foil_only, self.own_lang, self.missing, self.mark_owned = \
            b.lang_filter, b.foil_only, b.own_lang, b.missing, b.mark_owned
        self.alt_only = b.alt_only
        for name in ("sec_sets", "sec_colors", "sec_opts", "sec_types", "sec_super", "sec_sub", "sec_kw", "sec_rarity",
                     "sec_range", "sec_count", "sec_format", "sec_text", "sections"):
            setattr(self, name, getattr(b, name))
        self.mine_btn = Toggle(tr("My collection"), True, parent=self)
        self.all_btn = Toggle(tr("All cards"), False, parent=self)
        self.done_btn = Toggle("", False, parent=self)   # set completion open/closed
        self.db_btn = Toggle(tr("Load card database …"), parent=self)
        self.sort = Mode([(tr(label), key) for key, label in SORTS], self)
        self.sort.currentIndexChanged.connect(lambda _: self.refresh())
        self.sort_dir = None  # None = natural direction of the sorting (SORT_NATURAL), otherwise "asc"/"desc"
        self.completion_open = bool(ctrl.settings.get("lib_completion_open")) and type(self) is LibraryCore
        # lists (wish/trade lists) on the left – share the column with set completion; the one opened last
        # is at the top. list_sel = (kind, id): the Library shows only cards of this list.
        self.lists_open = bool(ctrl.settings.get("lib_lists_open")) and type(self) is LibraryCore
        self.side_top = ctrl.settings.get("lib_side_top") or "completion"
        self.list_sel = None
        self.list_add = False   # "+ Search cards" on a picked list: the filter rests, the list stays the target
        self.list_any = set()   # print ids standing for a wish of "any version" (the cheapest copy) – chip on the tile
        # Group by (ui/grouping.py): chain of properties and the chosen branch per level; group_base = the rows the
        # tree counts (set in mine_rows, before the path is applied)
        self.group_chain, self.group_path, self.group_base = [], [], []
        self.cols_slider = Steps(self.START["full"], self.col_hi("full"), self.area_columns("full"), self)
        self.model = RowModel(self)
        self.status = Status(self)
        self.detail = DetailState(self)
        self.compare = DetailState(self, compare=True)
        self.slide = CompareState(self.compare, self._cmp_changed, self)
        self.bar.changed.connect(self.refresh)
        # new cards (scanning, changes) appear without reloading
        self.watch = QtCore.QTimer(self, interval=1000, timeout=self.check_changes)
        self.bar.update_adv_btn()
        self.sync_slider()

    @property
    def coll(self):
        return self.source if self.source is not None else self.ctrl.collection

    def holders(self):
        return self.ctrl.trade_holders(force=True) if self.show_holders else {}

    # --- Opening (page in the program window) ---
    def enter(self):
        self.bar.prepare()
        self.update_mode_widgets()
        self.refresh(keep=True)
        self.watch.start()

    def leave(self):
        self.watch.stop()
        self.loader.cancel()

    close = leave  # program exit

    def isWindow(self):
        return False

    def hide(self):
        self.leave()

    def escape(self):
        if self.compare.isVisible():
            self.close_compare()
        elif self.detail_open:
            self.close_detail()
        else:
            self.ctrl.stream.show_page("scan")

    def check_changes(self):
        if self.coll.rev != self.seen_rev:
            self.refresh(keep=True)

    def load_db(self):
        self.ctrl.enqueue("carddb", "db")
        self.ctrl.stream.show_page("settings", tab="sets", back=True)

    def set_mode(self, mode):
        if mode == "altart":   # the former tab "Alt-arts": My Collection with the option "alt-arts only"
            mode = "mine"
            self.alt_only.setChecked(True)
        self.mode = mode
        self.mine_btn.setChecked(mode == "mine")
        self.all_btn.setChecked(mode == "all")
        self.update_mode_widgets()
        self.refresh()

    def update_mode_widgets(self):
        mine = self.mode in ("mine", "altart")   # alt arts: own cards (view like "My Collection")
        has_db = carddb.exists()
        for w in (self.lang_filter, self.foil_only, self.own_lang, self.alt_only):
            w.setVisible(mine)
        counts = {}
        for it in self.coll.items:
            counts[it.get("lang") or "en"] = counts.get(it.get("lang") or "en", 0) + int(it.get("count", 1))
        self.lang_filter.set_present(counts)
        for w in (self.missing, self.mark_owned):
            w.setVisible(not mine)
        self.sec_colors.setEnabled(has_db)
        self.adv_note.setVisible(self.adv_btn.isChecked() and not has_db)
        self.db_btn.setVisible(not has_db)

    # --- Search (SearchBox) ---
    @property
    def set_codes(self):
        return self.bar.set_codes

    def set_set(self, code, on=True):
        self.bar.set_set(code, on)

    def filters(self, live=True):
        return self.bar.filters(live)

    def refresh_chips(self):
        self.bar.refresh_chips()

    def clear_all(self):
        self.bar.clear_all()

    def update_adv_btn(self):
        self.bar.update_adv_btn()

    def show_set(self, code):
        self.set_mode("all")
        self.bar.search.setText(code)

    # --- Grid size ---
    def area(self):
        """Work area: full (grid only), medium (with detail view), small (detail view + compare)."""
        c = "_c" if self.completion_open or self.lists_open else ""
        if not self.detail_open:
            return "full" + c
        return ("small" if self.compare.isVisible() and not self.slide.closing else "medium") + c

    def area_columns(self, area):
        """Saved card count for a work area (each area remembers its own value)."""
        saved = self.ctrl.settings.get(self.COLS_KEY) or {}
        lo, hi = self.START[area], self.col_hi(area)
        if area in saved:
            return max(lo, min(hi, int(saved[area])))
        if self.HI is not None:
            return hi
        idx = self.ctrl.settings.get("lib_col_index")
        if idx is None:
            idx = max(0, min(5, int(self.ctrl.settings.get("lib_cols") or 6) - 5))
        return lo + int(idx)

    def sync_slider(self):
        area = self.area()
        lo = self.START[area]
        self.cols_slider.lo, self.cols_slider.hi = lo, self.col_hi(area)
        self.cols_slider.set_value(self.area_columns(area), emit=False)
        self.changed.emit()

    def col_hi(self, area):
        return (self.HI or {}).get(area, self.START[area] + self.SPAN)

    def columns(self):
        """Cards per row: same slider position, the number depends on the work area (5–10, 4–9, 3–8)."""
        return self.cols_slider.value

    def set_columns(self, n):
        saved = dict(self.ctrl.settings.get(self.COLS_KEY) or {})
        saved[self.area()] = int(n)
        self.ctrl.settings[self.COLS_KEY] = saved
        self.ctrl.settings.pop("lib_small", None)
        self.ctrl.settings_changed()
        self.changed.emit()

    def show_completion(self):
        """Set completion on/off – the detail and compare view then move to the left."""
        self.completion_open = not self.completion_open
        self.done_btn.setChecked(self.completion_open)
        self.ctrl.settings["lib_completion_open"] = self.completion_open
        if self.completion_open:
            self._side_top("completion")
        self.ctrl.settings_changed()
        self.sync_slider()

    # --- Lists ---
    def _side_top(self, key):
        self.side_top = key
        self.ctrl.settings["lib_side_top"] = key

    def show_lists(self):
        """Lists on the left on/off (with set completion open: the one opened last at the top, both half height)."""
        self.lists_open = not self.lists_open
        self.ctrl.settings["lib_lists_open"] = self.lists_open
        if self.lists_open:
            self._side_top("lists")
        self.ctrl.settings_changed()
        self.sync_slider()

    def pick_list(self, kind, lid):
        """Click a list: the Library shows only its cards (click again = all again). Wishlists under
        "All Cards" (the cards are usually still missing), trade lists under "My Collection"."""
        sel = (kind, lid)
        self.list_sel = None if self.list_sel == sel else sel
        self.list_add = False
        want = "mine" if kind == "have" or (kind == "custom" and self._list_owned(lid)) else "all"
        if self.list_sel is not None and self.mode != want and (want == "mine" or carddb.exists()):
            self.set_mode(want)
            return
        self.refresh()

    def _list_owned(self, lid):
        """An own list whose prints are all in the collection (e.g. "As list" from a log): shown in "My Collection",
        where language and finish count – otherwise under "All Cards"."""
        from collection import trade
        ws = trade.wishes([lid])
        if not ws or any(not w.get("set") or not w.get("number") for w in ws):
            return False
        have = {((it.get("set") or "").lower(), str(it.get("number") or "")) for it in self.ctrl.collection.items}
        return all((w["set"].lower(), str(w["number"])) in have for w in ws)

    def list_match(self, w, r):
        """How well a list entry fits a tile row: 3 print + language + finish, 2 print, 1 name, 0 not at all.
        "All Cards" only knows prints (English, no finish) – language and finish don't count there."""
        if (w.get("name") or "").lower() != (r.get("name") or "").lower():
            return 0
        if not w.get("set") or not w.get("number"):
            return 1
        if ((w["set"] or "").lower(), str(w["number"])) != ((r.get("set") or "").lower(), str(r.get("number") or "")):
            return 0
        if self.mode != "mine" or not (w.get("lang") or w.get("foil")):
            return 2
        return 3 if ((w.get("lang") or "en"), bool(w.get("foil"))) == ((r.get("lang") or "en"), bool(r.get("foil")))             else 0

    def list_counts(self, rows):
        """Picked list: a tile shows how many are ON THE LIST, not how many you own (Oliver, review .62) – each entry
        counts on the row it fits best (the first of equals)."""
        if self.list_sel is None or self.list_add:
            return rows
        from collection import trade
        kind, lid = self.list_sel
        if kind == "have":
            for r in rows:
                r["count"] = sum(trade.have_count(it, lid) for it in r.get("items") or [])
            return rows
        for r in rows:
            r["count"] = 0
        for w in trade.wishes([lid]):
            best, at = 0, None
            for r in rows:
                m = self.list_match(w, r)
                if m > best:
                    best, at = m, r
            if at is not None:
                at["count"] += int(w.get("count", 1))
        return rows

    def list_entry(self, r):
        """Key of the list entry behind a tile (for −/+/remove), or None."""
        if self.list_sel is None or r is None:
            return None
        from collection import trade
        kind, lid = self.list_sel
        if kind == "have":
            its = [it for it in r.get("items") or [] if trade.have_count(it, lid) > 0]
            return its[0]["uid"] if its else None
        ws = sorted(trade.wishes([lid]), key=lambda w: -self.list_match(w, r))
        return trade.wish_key(ws[0]) if ws and self.list_match(ws[0], r) else None

    def _list_filter(self):
        """-> (check per row, ids for "All Cards") of the selected list, or (None, None)."""
        self.list_any = set()
        if self.list_sel is None or self.list_add:
            return None, None
        from collection import trade
        kind, lid = self.list_sel
        if kind in ("wish", "custom"):
            # a wish without a print ("any version") shows ONE tile in "All Cards": always the cheapest copy, with the
            # chip "any version" (Oliver, review .90) – in "My Collection" every own copy of the name; an entry with set
            # and number exactly that print – in "My Collection" also its language and finish
            ws = trade.wishes([lid])
            loose = {w["name"] for w in ws if not w.get("set") or not w.get("number")}
            exact = [w for w in ws if w.get("set") and w.get("number")]
            low = {n.lower() for n in loose}
            prints = {(w["set"].lower(), str(w["number"])) for w in exact}
            mine = self.mode == "mine"
            full = {(w["set"].lower(), str(w["number"]), w.get("lang") or "en", bool(w.get("foil")))
                    for w in exact if w.get("lang") or w.get("foil")}
            any_finish = {(w["set"].lower(), str(w["number"])) for w in exact if not (w.get("lang") or w.get("foil"))}

            cheapest = {} if mine else carddb.cheapest_ids_for_names(loose)
            self.list_any = set(cheapest.values())

            def keep(r):
                p = ((r.get("set") or "").lower(), str(r.get("number") or ""))
                if not mine:
                    return r.get("sid") in self.list_any or p in prints
                if (r.get("name") or "").lower() in low:
                    return True
                return p in any_finish or p + ((r.get("lang") or "en"), bool(r.get("foil"))) in full
            ids = (list(cheapest.values()) if not mine else carddb.ids_for_names(loose)) + carddb.ids_for_prints(
                [(w["set"], w["number"], w.get("lang")) for w in exact])
            return keep, list(dict.fromkeys(ids))
        if lid == trade.MAIN_HAVE:
            sids = {scryfall_id(it["id"]) for it in self.ctrl.collection.items if int(it.get("trade") or 0) > 0}
        else:
            uids = {u for u, n in trade.have_counts(lid).items() if n > 0}
            sids = {scryfall_id(it["id"]) for it in self.ctrl.collection.items if it.get("uid") in uids}
        return (lambda r: r.get("sid") in sids), list(sids)

    # --- Data ---
    def refresh(self, keep=False):
        sel = self.current_row()
        self.seen_rev = self.coll.rev
        self.owned_cache = self.coll.owned()
        self.refresh_chips()
        try:
            # keep (e.g. card into the collection): as many rows as already loaded – otherwise the pages
            # scrolled further would be missing and the grid would jump to the top
            n_old = len(self.model.rows) if keep else 0
            if self.alt_view():   # "alt-arts only": cards marked as alt art (they come via the scan studio)
                rows = [r for r in self.mine_rows() if is_altart(r)]
            else:
                rows = self.mine_rows() if self.mode == "mine" else self.db_rows(0, max(self.page_size(), n_old))
        except Exception as e:  # noqa: BLE001 – e.g. invalid search syntax
            rows = []
            self.status.setText(tr(f"Search not possible: {e}"))
        self.appear_t0 = None if keep else time.monotonic()
        found = next((i for i, r in enumerate(rows) if sel is not None and r["key"] == sel["key"]), None)
        self.current = found if (found is not None and self.detail_open) else -1
        self.model.set_rows(rows)
        if found is not None and self.detail_open:
            self.detail.row = rows[found]
            self.detail.refresh_owned()
        # card no longer in the result: detail/compare still stay open – close only on request
        self.update_status()

    def alt_view(self):
        """My Collection with "alt-arts only" (Advanced search → Display)."""
        return self.mode in ("mine", "altart") and self.alt_only.isChecked() and not self.alt_only.isHidden()

    def current_row(self):
        rows = self.model.rows
        return rows[self.current] if 0 <= self.current < len(rows) else None

    def mine_rows(self):
        groups = self.coll.groups()
        db = carddb.cards_by_ids({g["sid"] for g in groups}) if carddb.exists() else {}
        f, text = self.filters()
        set_codes = f.pop("set_codes", [])
        if set_codes and f.get("sets_mode") == "and" and db:
            f["set_codes"] = set_codes  # AND: via the database (card printed in all sets)
            set_codes = []
        db_filter = any(f.get(k) for k in ("colors", "types", "supertypes", "subtypes", "keywords", "rarities",
                                           "formats", "formats_any", "ranges", "texts", "set_codes", "number")) \
            or any(k.startswith("not_") and v for k, v in f.items())
        ids = None
        if db and (text or db_filter):
            ids = carddb.matching_ids(text, only_ids=list(db), **f)
        words = text.lower().split()
        langs, foil = self.lang_filter.selected(), self.foil_only.mode
        if langs and self.lang_filter.mode() == "and" and len(langs) > 1:  # AND: card in all selected languages
            have = {}
            for g in groups:
                have.setdefault(g["sid"], set()).add(g["lang"])
            ok_sids = {sid for sid, ls in have.items() if langs <= ls}
            groups = [g for g in groups if g["sid"] in ok_sids]
        owned = f.pop("owned", None)
        # owned prints the card database doesn't have (any more – e.g. Yu-Gi-Oh! OCG prints after the data change):
        # searched by name here, shown with the image of another print of the same card
        lost = sorted({g["name"] for g in groups if db and g["sid"] not in db})
        stand = carddb.by_names(lost) if lost else {}
        rows = []
        for g in groups:
            if set_codes and g["set"].lower() not in set_codes:
                continue
            if langs and g["lang"] not in langs:
                continue
            if (foil == "only" and not g["foil"]) or (foil == "none" and g["foil"]):
                continue
            if ids is not None and g["sid"] not in ids:
                if g["sid"] in db or db_filter:   # not a match – or no data for the advanced filters
                    continue
                if words and not all(w in g["name"].lower() for w in words):
                    continue
            if owned and not CountSection.matches(self.owned_cache.get(g["sid"], 0), *owned):
                continue
            if ids is None and not db and f.get("rarities") and g.get("rarity") not in f["rarities"]:
                continue
            if ids is None and not db and g.get("rarity") in (f.get("not_rarities") or []):
                continue
            if ids is None and words and not all(w in g["name"].lower() for w in words):
                continue
            rows.append(self.row_from_group(g, db.get(g["sid"]), stand.get(g["name"].lower())))
        other = self.other_game_rows(set_codes, langs, foil, words)
        if other:   # mixed: also the own cards with a game chip
            import games
            act = games.current().key
            for r in rows:
                r.update(game=act, game_tag=games.SHORT.get(act, act.upper()))
            rows += other
        if self.extra_filter is not None:
            rows = [r for r in rows if self.extra_filter(r)]
        keep, _ = self._list_filter()
        if keep is not None:
            rows = self.list_counts([r for r in rows if keep(r)])
        # Group by (review .101): the tree counts what search, filters and list leave – the grid shows the chosen node
        self.group_base = rows
        chain = getattr(self, "group_chain", None)
        if chain and getattr(self, "mode", "") == "mine":
            from ui import grouping
            gk = grouping.keep(chain, self.group_path)
            if gk is not None:
                rows = [r for r in rows if gk(r)]
        self.disp = display(self.ctrl.settings)
        rows = group_rows(rows, self.disp)
        sort = self.sort.currentData()
        tl = lambda r: ((r["db"] or {}).get("type_line") or "")  # noqa: E731
        if sort == "price":
            rows.sort(key=lambda r: -(r["price"] or 0))
        elif sort == "set":  # as in the card database: newest sets first, within them by number
            rows.sort(key=lambda r: (r["set"], carddb.number_key(r["number"]), r["lang"]))
            rows.sort(key=lambda r: (r["db"] or {}).get("released") or "", reverse=True)
        elif sort == "type":
            order = ["Creature", "Planeswalker", "Instant", "Sorcery", "Artifact", "Enchantment", "Battle", "Land"]
            rows.sort(key=lambda r: (next((i for i, t in enumerate(order) if t in tl(r)), 9), r["name"]))
        elif sort == "mv":
            rows.sort(key=lambda r: ((r["db"] or {}).get("cmc") or 0, r["name"]))
        elif sort == "color":
            def ckey(r):
                c = (r["db"] or {}).get("colors") or ""
                return (7 if not c else 6 if len(c) > 1 else "WUBRG".index(c) + 1, c, r["name"])
            rows.sort(key=ckey)
        elif sort == "rarity":
            rank = {"mythic": 0, "special": 1, "rare": 2, "uncommon": 3, "common": 4}
            rows.sort(key=lambda r: (rank.get(r.get("rarity"), 5), r["name"]))
        elif sort == "cond":   # best condition first (Graded, Mint, Near Mint … Poor, Other), then A–Z
            rows.sort(key=lambda r: (min((c[0] for c in r.get("conds") or [(1, "", True)]), default=1),
                                     r["name"].lower(), r["set"]))
        elif sort == "count":   # most copies first, then A–Z
            rows.sort(key=lambda r: (-(r.get("count") or 0), r["name"].lower(), r["set"]))
        elif sort == "relevance" and not text:   # nothing searched, nothing selected: alphabetical
            rows.sort(key=lambda r: (r["name"].lower(), r["set"]))
        elif sort == "new" and not text:
            rows.sort(key=lambda r: -r["last"])
        else:
            rows.sort(key=lambda r: (not r["name"].lower().startswith(text.lower()), r["name"], r["set"]))
        if self.sort_reverse():
            rows.reverse()
        return rows

    def sort_reverse(self):
        key = self.sort.currentData() or "relevance"
        return self.sort_dir is not None and self.sort_dir != SORT_NATURAL.get(key, "asc")

    def page_size(self):
        """"All cards" (Oliver, after 0.9.2): not everything at once – the visible rows and one more, then page by
        page while scrolling."""
        return max(12, int(self.columns() or 6) * (int(self.view_rows) + 1))

    def db_query(self):
        """Search text and filters of "All cards" -> (text, filters for carddb) – the grid and the Group-by tree."""
        f, text = self.filters()
        owned = f.pop("owned", None)
        if owned:
            f["only_ids"] = [sid for sid, n in self.owned_cache.items() if CountSection.matches(n, *owned)]
        if self.missing.isChecked():
            f["exclude_ids"] = list(self.owned_cache)
        _, list_ids = self._list_filter()
        if list_ids is not None:  # only cards of the selected list
            f["only_ids"] = [i for i in f["only_ids"] if i in set(list_ids)] if f.get("only_ids") else list_ids
        if not text and not f.get("set_codes") and not f.get("types"):
            f["no_tokens"] = True
        return text, f

    def db_rows(self, offset, limit=None):
        if not carddb.exists():
            self.more = False
            return []
        text, f = self.db_query()
        _, list_ids = self._list_filter()
        chain = getattr(self, "group_chain", None)
        if chain:   # Group by: the chosen branch as an SQL condition (the tree counts in SQL, ui/qgroup.py)
            from ui import grouping
            f["where_sql"] = grouping.sql_where(chain, self.group_path)
        limit = limit or self.page_size()
        res = carddb.search(text, limit=limit, offset=offset, sort=self.sort.currentData(),
                            reverse=self.sort_reverse(), **f)
        self.offset = offset + len(res)
        self.more = len(res) == limit
        rows = [self.row_from_db(r) for r in res]
        return self.list_counts(rows) if list_ids is not None else rows

    def fetch_more(self):
        """Scrolled further (all cards): append the next page."""
        if self.mode == "all" and self.more:
            self.more = False
            self.model.append(self.db_rows(self.offset))
            self.update_status()

    def other_game_rows(self, set_codes, langs, foil, words):
        """Mixed Library (game button → Mix): cards of the other enabled games, read-only –
        filtered by name, set, language, foil (their card database is not loaded). All rows then carry
        their game as a chip."""
        import games
        keys = games.shown(self.ctrl.settings) if self.source is None else []
        if len(keys) < 2:
            return []
        act = games.current().key
        out = []
        for key in keys:
            if key == act:
                continue
            from collection.collection import groups_of
            for g in groups_of(games.collection_items(key)):
                if set_codes and str(g.get("set") or "").lower() not in set_codes:
                    continue
                if langs and g["lang"] not in langs:
                    continue
                if (foil == "only" and not g["foil"]) or (foil == "none" and g["foil"]):
                    continue
                if words and not all(w in (g.get("name") or "").lower() for w in words):
                    continue
                r = self.row_from_group(g, None)
                r.update(game=key, game_tag=games.SHORT.get(key, key.upper()), foreign=True)
                out.append(r)
        return out

    def row_from_group(self, g, dbrow, stand=None):
        """stand: another print of the same card (only for its image) when the database lacks this print."""
        card = {k: g.get(k) for k in ("id", "name", "set", "number", "rarity", "finishes", "booster", "eur",
                                      "eur_foil", "img", "url")}
        from cards import finishes
        fin = finishes.full_label(g)
        from cards import conditions
        return {"key": f"{g['sid']}|{g['lang']}|{int(g['foil'])}|{g.get('finish') or ''}|{g.get('edition') or ''}"
                       + f"|{conditions.ident(g)}",
                "sid": g["sid"], "name": g["name"], "fin": fin,
                "conds": [(conditions.rank(g), conditions.short(g), conditions.is_plain(g))],
                "set": g["set"], "number": g["number"], "rarity": g.get("rarity"), "lang": g["lang"],
                "foil": g["foil"], "count": g["count"], "price": item_price(g), "img": g["img"],
                "thumb": (dbrow or stand or {}).get("img_small"), "normal": (dbrow or stand or {}).get("img_normal"),
                "card": card, "db": dbrow, "last": g["last"], "items": g.get("items") or []}

    def row_from_db(self, r):
        card = carddb.entry_from_row(r)
        return {"key": f"{r['id']}|en|0", "sid": r["id"], "name": card["name"], "set": card["set"],
                "number": card["number"], "rarity": card["rarity"], "lang": "en", "foil": False,
                "count": self.owned_cache.get(r["id"], 0),
                "price": r["eur"] if r["eur"] is not None else r["eur_foil"], "img": card["img"],
                "thumb": r["img_small"], "normal": r["img_normal"], "card": card, "db": r, "last": 0}

    def row_for_print(self, pr):
        """Row for a print from the print list: from the card database, otherwise from the Scryfall data."""
        db = carddb.cards_by_ids({pr["id"]}) if carddb.exists() else {}
        if pr["id"] in db:
            return LibraryCore.row_from_db(self, db[pr["id"]])
        eur_n, eur_f = (float(pr[k]) if pr.get(k) else None for k in ("eur", "eur_foil"))
        card = {"id": f"{pr['id']}_0", "name": pr["name"], "set": pr["set"], "number": pr["number"],
                "rarity": pr.get("rarity"), "finishes": pr.get("finishes") or [], "booster": pr.get("booster"),
                "eur": eur_n, "eur_foil": eur_f, "img": image_rel(pr["set"], pr["number"], 0), "url": None}
        return {"key": f"{pr['id']}|en|0", "sid": pr["id"], "name": pr["name"], "set": pr["set"],
                "number": pr["number"], "rarity": pr.get("rarity"), "lang": "en", "foil": False,
                "count": self.owned_cache.get(pr["id"], 0), "price": eur_n if eur_n is not None else eur_f,
                "img": card["img"], "thumb": pr.get("img"), "normal": None, "card": card, "db": None, "last": 0}

    def update_status(self):
        rows = self.model.rows
        if self.alt_view():
            self.status.setText(tr("<b>{n}</b> alt-arts").format(n=len(rows)) if rows else
                                tr("No alt-arts yet – the first ones will come from artists via the Scan Studio."))
            return
        if self.mode == "mine" and self.source is not None:
            n = sum(r["count"] for r in rows)
            value = sum(r.get("value", (r["price"] or 0) * r["count"]) for r in rows)
            self.status.setText(tr(f"<b>{n}</b> cards shown · value <b>{eur(value)}</b>"))
            return
        if self.mode == "mine":
            s = self.ctrl.collection.summary()
            n = sum(r["count"] for r in rows)
            value = sum(r.get("value", (r["price"] or 0) * r["count"]) for r in rows)
            langs = " · ".join(f"{lang_short(k)} {v}" for k, v in sorted(s["langs"].items(), key=lambda t: -t[1]))
            txt = tr(f"<b>{n}</b> cards shown · value <b>{eur(value)}</b>")
            from cards import valuehist
            total = eur(s["value"])
            if valuehist.available() and s["cards"]:   # click the value: the history expands at the bottom
                total = f"<a href='value'>{total}</a>"
            txt += tr(f"  —  whole collection: {s['cards']} cards ({s['unique']} different) · ") + total
            if langs:
                txt += f" · {langs}"
            if not s["cards"]:
                txt = tr("No cards in the collection yet. Scanned cards are added automatically; under “All cards” you can also add cards by hand.")
        elif not carddb.exists():
            txt = tr("“All cards” needs the game's data – load it via the game button at the top left.")
        else:
            txt = tr(f"<b>{len(rows)}</b> cards") + (tr(" (more when scrolling)") if self.more else "")
        self.status.setText(txt)

    # --- Detail view ---
    def show_detail(self, i):
        """Tile i clicked -> detail view (pinned: next to it; an open comparison belongs to the old card)."""
        rows = self.model.rows
        if not 0 <= i < len(rows):
            return
        row = rows[i]
        if self.detail_open and self.detail.row is not None and self.detail.row["key"] == row["key"]:
            self.current = i
            return
        if self.detail_open and self.detail_pinned:  # pinned: card in the compare slot next to it
            self.open_beside(row)
            return
        self.current = i
        if self.compare.isVisible():
            self.close_compare(animate=False)
        if not self.detail_open:
            self.detail_open = True
            self.detail.show()
            self.detail.show_row(row)
            self.sync_slider()
            return
        self.detail.show_row(row)
        self.changed.emit()

    def open_beside(self, row):
        """Second detail view in the compare slot (the pinned card stays on the right)."""
        opening = not self.compare.isVisible()
        self.compare.show_row(row)
        if opening:
            self.slide.open(animate=False)
            self.sync_slider()
        self.update_marks()

    def swap_panels(self):
        """⇄: swap the content of compare and detail. The pin stays on the right."""
        a, b = self.compare.row, self.detail.row
        if a is None or b is None or not self.compare.isVisible():
            return
        self.detail.show_row(a)
        self.compare.show_row(b)
        self.update_marks()
        DetailHost._pin_after_swap(self.detail)

    def show_card_row(self, row):
        """Show a card that doesn't have to be in the grid (e.g. click on a list entry in the "Trade" tab)."""
        if row is None:
            return
        if self.detail_open:
            if self.compare.isVisible():
                self.close_compare(animate=False)
            self.detail.show_row(row)
            return
        self.detail_open = True
        self.detail.show()
        self.detail.show_row(row)
        self.sync_slider()

    def close_detail(self):
        self.detail.pin_btn.setChecked(False)  # closed: pin released (only the side swap keeps it)
        self.close_compare(animate=False)
        self.detail_open = False
        self.detail.hide()
        self.detail.show_row(None)
        self.current = -1
        self.sync_slider()

    def detail_panels(self):
        return [self.detail, self.compare]

    def set_fold(self, key, on):
        """Expand/collapse a section of the detail view – applies to all cards and stays saved."""
        folded = set(self.ctrl.settings.get("detail_folded") or [])
        folded.discard(key) if on else folded.add(key)
        self.ctrl.settings["detail_folded"] = sorted(folded)
        self.ctrl.settings_changed()
        for panel in (self.detail, self.compare):
            panel.set_fold(key, on)
        editor = getattr(getattr(self.ctrl, "deck_page", None), "editor", None)
        if editor is not None and getattr(editor, "detail", None) is not None:
            editor.detail.set_fold(key, on)

    # --- Compare: another print to the left of the detail view ---
    def show_compare(self, pr):
        if pr is None or not self.detail_open:
            return
        if self.detail.row is not None and pr["id"] == self.detail.row["sid"]:
            self.close_compare()  # the displayed print itself: compare closed
            return
        if self.compare.row is not None and self.compare.row["sid"] == pr["id"] and self.compare.isVisible():
            return
        opening = not self.compare.isVisible()
        self.compare.show_row(self.row_for_print(pr))
        if opening:
            self.slide.open(animate=False)
            self.sync_slider()
        self.update_marks()

    def _cmp_changed(self):
        if not self.compare.isVisible():
            self.compare.show_row(None)
        self.update_marks()
        self.sync_slider()

    def close_compare(self, animate=True):
        if self.compare.isVisible():
            self.slide.close(False)

    def update_marks(self):
        """Mark in both print bars: detail view = main, compare = compare."""
        marks = {}
        if self.detail.row is not None:
            marks[self.detail.row["sid"]] = "main"
        if self.compare.isVisible() and self.compare.row is not None:
            marks[self.compare.row["sid"]] = "compare"
        for panel in (self.detail, self.compare):
            panel.strip.set_marks(marks)
