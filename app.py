"""Bent°Corner as a standalone program.

Two windows:
    Control        camera, scan frame, buttons, pack list, settings
    Stream         webcam + overlay, no controls. Share this window in Discord.

    python app.py
"""
import sys

if "--ai-worker" in sys.argv:   # AI worker process (aiworker.py): no Qt or windows, just network + text recognition
    from scanner import aiworker
    aiworker.serve()

import collections
import html
import json
import logging
import pathlib
import threading
import time
import os

# Media Foundation: without this switch the camera only opens after ~30 s
os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")
import cv2  # noqa: E402
# Image processing with 4 threads: measured just as fast as with all 24, but ~40 % less CPU time
cv2.setNumThreads(4)
from PySide6 import QtCore, QtGui, QtWidgets  # QtWidgets only for: QApplication (for the icon in the system tray)
from PySide6.QtCore import Qt

from cards import carddb
from cards import conditions
import games
from ui import statsview
from ui.sessparts import EditPage
from cards import currency
from collection import decks
from cards import packtypes
from ui import scanui
from ui import setupui
from system import datahome
from scanner.camera import Camera
from scanner.recognizer import Recognizer
from scanner import fingerprint
from scanner import tracker
from cards import pricehist
from ui import qmenu
from ui import qdialogs
from ui import qstate
from cards import library
from scanner import scandata
from collection.collection import EXPORT_FORMATS, LANGS, Collection, export_csv, lang_short, scryfall_id
from ui.librarycore import DetailHost, run_async
from system import hwinfo
from ui import perf
from system.i18n import set_language, tr
from collection import sessions
from scanner.common import BASE, DATA, lang_img
from scanner.core import INFO_DEFAULTS, Matcher, Session, pack_total, price_of, has_packs, kind_of

from scanner.scan_ctl import ScanControl   # APP-SPLIT D: MainWindow mixin

from net.relay_ctl import RelayControl   # APP-SPLIT C: MainWindow mixin

from system.upkeep_ctl import UpkeepControl   # APP-SPLIT C: MainWindow mixin

from system import jobqueue
from system.jobqueue import JobQueue, fmt_duration   # APP-SPLIT C: MainWindow mixin
from system import orbit   # Bent°Corner Orbit: Core · Near Orbit · Full Orbit

log = logging.getLogger("booster")
from system import startup
from system.startup import SETTINGS_FILE, saved_language   # APP-SPLIT C: start-up lives in system/startup.py


set_language(saved_language())  # before all translated texts (including the constants below)

from ui.scanlook import eur, finish_label, finish_short, refresh_color_consts, shown_name  # noqa: E402
from ui.scanlook import CYAN, MAGENTA  # noqa: E402,F401 – qcharts reads app.CYAN / app.MAGENTA


DEFAULTS = {
    "camera": "", "resolution": "1920x1080", "mirror": False, "mirror_v": False,
    "zone": [0.5, 0.5, 0.3], "min_inliers": 25, "stable": 3, "scan_hints": False,
    "hit": 0.5, "scan_sounds": True, "hold": 10, "hold_forever": True,
    "scan_tiles": {}, "scan_view": "normal",   # scan page: tiles (scantiles.py)
    "price_update": "start", "catalog_update": "weekly", "last_price_day": "",
    "disabled_sets": [], "expanded_groups": [], "language": "de", "price_history": False, "scan_mode": "ai", "image_cache_mb": 1000, "cam_controls": {}, "preview_zoom": 1.0, "preview_center": [0.5, 0.5],
    "cond_scale": "auto", "cond_default": "near_mint", "cond_chip": True, "main_shop": "auto",
    "card_lang": "en", "printed_names": True, "collection_auto": True, "scan_data": True, "export_format": "manabox", "start_fullscreen": False,
    "tray_mode": False,  # window closed = keep running in the system tray – off like the first-run setup preselects
    "lib_cols": 6, "lib_detail_w": 0, "currency": "EUR", "offline_skip_basics": True, "detail_folded": ["links"],
}
# Settings tabs, ordered by need (STREAMLINE-VORSCHLAG §4, no "Advanced" – the user: "just give me everything");
# SETTINGS_SECTIONS: heading above the first tab of each block
SETTINGS_PAGES = [("general", "settings", "General", "Game, language, program window, background and data folder"),
                  ("scan", "scan", "Scanning", "Camera, recognition, scan frame and how the stream looks"),
                  ("collection", "tag", "Collection & prices", "Currency, language, prices and export"),
                  ("display", "display", "Presentation", "How cards and lists look, animations & performance"),
                  ("appearance", "palette", "Skin", "Look, colors, fonts and corners"),
                  ("backup", "backup", "Backup", "Automatic backup, one-off backup, restore and moving"),
                  ("privacy", "friends", "Friends & privacy", "What the program shares and sends – every switch is only here"),
                  ("sets", "database", "Card data", "What the program knows: database, languages, images"),
                  ("updates", "update", "Updates", "New versions and patch history"),
                  ("legal", "legal", "Legal", "Legal notice, privacy policy, terms, sources and licenses"),
                  ("about", "heart", "About Bent°Corner", "Who is behind it, version and a coffee"),
                  ("game", "game", "Scalper Invaders", "Psst – a little easter egg")]
SETTINGS_SECTIONS = {"general": "Everyday", "display": "Looks", "backup": "Your data", "updates": "Advanced"}
LEGAL_TEXT = [
    ("Preise", "Bent°Corner doesn't make its own prices. It shows the guide values of the two big marketplaces: "
               "<b>Cardmarket</b> (Europe, in €, the “trend” price) and <b>TCGplayer</b> (USA, in $, the “market "
               "price”); foils have their own value. That's why a card has one or two values – if one marketplace "
               "doesn't list it, only the other one is shown.<br><br>Where they come from: Magic via the daily bulk "
               "data of <a href='https://scryfall.com'>Scryfall</a>. Pokémon and Disney Lorcana: the Cardmarket price "
               "guide (the app downloads the file itself, at most once a day) and TCGplayer via the Bent°Corner price "
               "server (data from <a href='https://tcgcsv.com'>TCGCSV</a>). Yu-Gi-Oh!: both from the Bent°Corner "
               "price server (Cardmarket via <a href='https://ygoprodeck.com'>YGOPRODeck</a>, TCGplayer via "
               "TCGCSV).<br><br>How often: the marketplaces update their values once a day; Bent°Corner fetches them "
               "as set under Settings (default: when the app starts). Other currencies are converted with the daily "
               "rates of the European Central Bank (<a href='https://frankfurter.dev'>Frankfurter</a>).<br><br>All "
               "prices are guide values and without guarantee. They change constantly, can be outdated and are not a "
               "recommendation to buy, sell or trade. Values of collections, packs and sets are sums of these guide "
               "values."),
    # Riftbound: add its lines here (and on the website) when the game is ready.
    ("Sources", "<b>Card data:</b> Magic – <a href='https://scryfall.com'>Scryfall</a> · Pokémon – <a "
                "href='https://tcgdex.dev'>TCGdex</a> · Yu-Gi-Oh! – <a href='https://ygoprodeck.com'>YGOPRODeck</a>"
                "{lorcana_data}{more_data}.<br><b>Card images:</b> Magic – Scryfall (the app loads them itself) · "
                "Pokémon – TCGdex, through our image mirror (supplementary images: <a "
                "href='https://pokemontcg.io'>pokemontcg.io</a>) · Yu-Gi-Oh! – YGOPRODeck, hosted on our server as "
                "YGOPRODeck requires{lorcana_images}{more_images}."
                "<br><b>Prices:</b> Cardmarket and TCGplayer (see "
                "Prices) · price history for Magic: <a href='https://mtgjson.com'>MTGJSON</a> · exchange rates: "
                "European Central Bank via Frankfurter.<br><b>Symbols:</b> mana symbols are redrawn by Bent°Corner "
                "(they remain property of Wizards of the Coast); the game icons are our own pixel art – no publisher "
                "logos, no set symbols.<br><b>SCAN°:</b> the fingerprint indexes in the data packs are computed "
                "by Bent°Corner from the card images and contain no images."),
    ("Magic: The Gathering", "Bent°Corner is unofficial Fan Content permitted under the "
                             "<a href='https://company.wizards.com/en/legal/fancontentpolicy'>Fan Content Policy</a>. "
                             "Not approved/endorsed by Wizards. Portions of the materials used are property of "
                             "Wizards of the Coast. ©Wizards of the Coast LLC.<br><br>Magic: The Gathering, card "
                             "names, card images, mana symbols and set symbols are trademarks or property of Wizards "
                             "of the Coast LLC, a subsidiary of Hasbro, Inc."),
    ("Kartendaten und Bilder", "Magic card data and images come from <a href='https://scryfall.com'>Scryfall</a> – "
                               "the app loads them itself; the SCAN° index in the Magic data pack is computed "
                               "from Scryfall images. Bent°Corner is not affiliated with Scryfall."),
    ("Pokémon", "Pokémon card data from <a href='https://tcgdex.dev'>TCGdex</a> (MIT license, © 2021 TCGdex); the "
                "card images come from TCGdex via our server, which fetches each image once and keeps it, so TCGdex "
                "doesn't have to deliver it to every user individually. Supplementary images for cards TCGdex "
                "has no image of come from <a href='https://pokemontcg.io'>pokemontcg.io</a>, fetched once in the same way. Prices from <a "
                "href='https://www.cardmarket.com'>Cardmarket</a> (official price guide) and TCGplayer via the "
                "Bent°Corner price server (data from <a href='https://tcgcsv.com'>TCGCSV</a>) – thank you! "
                "Pokémon, card names and images are property of "
                "Nintendo, Creatures Inc., GAME FREAK inc. and The Pokémon Company. Bent°Corner is not produced, "
                "endorsed, supported or affiliated with Nintendo or The Pokémon Company."),
    ("Yu-Gi-Oh!", "Yu-Gi-Oh! card data and images from <a href='https://ygoprodeck.com'>YGOPRODeck</a>, delivered by "
                  "our server (images downloaded once and self-hosted, as YGOPRODeck requires). Prints from Japan, "
                  "Korea, Asia and Spain and names in Japanese, Korean, Spanish and Chinese from <a "
                  "href='https://github.com/iconmaster5326/YGOJSON'>YGOJSON</a> (MIT license, © 2024 iconmaster), "
                  "which collects them from <a href='https://yugipedia.com'>Yugipedia</a> (<a "
                  "href='https://creativecommons.org/licenses/by-sa/4.0/'>CC BY-SA 4.0</a>) – as a separate file in "
                  "the data pack (ygo-locale.sqlite, filtered and converted by Bent°Corner, CC BY-SA 4.0 as well), "
                  "shown with the image of the English print; prices "
                  "from our price server (Cardmarket via YGOPRODeck, TCGplayer via <a "
                  "href='https://tcgcsv.com'>TCGCSV</a>) – thank you! Yu-Gi-Oh! is a trademark of Konami Digital "
                  "Entertainment; card texts and images © 4K Media Inc. / Konami. Bent°Corner is not affiliated "
                  "with Konami or 4K Media."),
    ("Weitere Quellen", "Kombos: <a href='https://commanderspellbook.com'>Commander Spellbook</a> · Turnierdaten: "
                        "<a href='https://edhtop16.com'>EDHTop16</a> · Beliebtheit: "
                        "<a href='https://edhrec.com'>EDHREC</a> · Preisverlauf: <a href='https://mtgjson.com'>MTGJSON</a> "
                        "(MIT-Lizenz, © 2018–heute Zach Halpern) · Wechselkurse: "
                        "<a href='https://frankfurter.dev'>Frankfurter</a> (EZB). Alle Angaben ohne Gewähr; Bent°Corner ist mit diesen "
                        "Seiten nicht verbunden."),
    ("Schätzungen", "Bracket, Kartenfunktionen (Ramp, Removal …), erkannte Karten beim Scannen und ähnliche Auswertungen "
                    "sind automatische Schätzungen und können falsch sein."),
    ("Datenschutz", "<b>The camera image never leaves your computer when you scan</b> – SCAN° (our smart card search) "
                    "runs entirely on your PC: it reads the cards (fingerprinting) to find them again when you scan a card "
                    "you own – nothing more. <b>No AI that could generate cards is trained with the card images.</b> While scanning, Bent°Corner only downloads images of cards to compare them (the "
                    "request contains the card, never your camera image). Card pictures leave your computer only if "
                    "you want them to: uploads from the Scan Studio and the scan data you send yourself.<br><br>"
                    "At start, Bent°Corner reads which processor, how much memory and which graphics card are "
                    "installed – only to set up SCAN° and animations. This stays on your computer. Online "
                    "lookups (Scryfall, Commander Spellbook …) contain only the cards or decks you look up – "
                    "no personal data. Our own server: the app checks for updates every 6 hours (version file only); "
                    "images of {mirror_games} come through our image mirror (only if it can't "
                    "deliver an image does the app ask the source directly), Yu-Gi-Oh! data, images and prices from our "
                    "server. Prices and exchange rates only from Near Orbit on (Bent°Corner Orbit, Settings → Friends & "
                    "privacy). Only if you turn them on: the exchange with friends (Full Orbit, end-to-end encrypted), anonymous "
                    "usage numbers (once a week, without any ID) and uploads from the Scan Studio. Details: <a "
                    "href='https://bentcorner.app/datenschutz.html'>privacy policy</a>."),
    ("Scan data", "When you correct a misrecognized card, Bent°Corner keeps the crop of that card (not the whole "
                  "camera image – so no faces or rooms) and a line of text: what was recognized and what is right. At "
                  "most 20 MB, the oldest drop out. The data stays on your computer until you click “Send” yourself. "
                  "Turn off, view and delete: Settings → Friends & privacy → Scan data."),
]
# Notices of games that are still being built: shown (after Yu-Gi-Oh!) as soon as the game is ready in games.GAMES.
# The publishers' wording stays verbatim (Riot requires its sentence exactly like this).
GAME_LEGAL = [
    ("lorcana", "Disney Lorcana", "Disney Lorcana card data from <a href='https://lorcanajson.org'>LorcanaJSON</a> "
                "(data from the official Disney Lorcana app), card images from Ravensburger via our image mirror "
                "(each image fetched once and kept, so Ravensburger doesn't have to deliver it to every user); "
                "prices from <a "
                "href='https://www.cardmarket.com'>Cardmarket</a> (official price guide) and TCGplayer via the "
                "Bent°Corner price server (data from <a href='https://tcgcsv.com'>TCGCSV</a>) – thank you! "
                "Uses trademarks and/or copyrights associated with Disney Lorcana TCG, used under Ravensburger's "
                "<a href='https://cdn.ravensburger.com/lorcana/community-code-en'>Community Code Policy</a>. We are "
                "expressly prohibited from charging you to use or access this content. Bent°Corner is not "
                "published, endorsed, or specifically approved by Disney or Ravensburger."),
    *__import__("games").extra("GAME_LEGAL", []),   # private games (games/extras.py)
    ("riftbound", "Riftbound", "Bent°Corner was created under Riot Games' \"Legal Jibber Jabber\" policy using "
                  "assets owned by Riot Games. Riot Games does not endorse or sponsor this project.<br><br>"
                  "Riftbound card texts are shown in Riot's official English version; translations only next to it. "
                  "Prices from <a href='https://www.cardmarket.com'>Cardmarket</a> (official price guide) and "
                  "TCGplayer via the Bent°Corner price server (data from <a href='https://tcgcsv.com'>TCGCSV</a>). "
                  "Riftbound, League of Legends and Riot Games are trademarks of Riot Games, Inc."),
]


# Lines of games that are still being built or withdrawn (games.WITHDRAWN) in "Sources" and "Datenschutz": as
# {placeholders}, filled in only for games that are ready – a game that comes back shows up again by itself.
LEGAL_PARTS = {
    "lorcana_data": ("lorcana", " · Disney Lorcana – <a href='https://lorcanajson.org'>LorcanaJSON</a> (from the "
                                "official Disney Lorcana app)"),
    "lorcana_images": ("lorcana", " · Disney Lorcana – Ravensburger, through our image mirror"),
    # private games (games/extras.py) fill these; empty in the public program
    "more_data": (None, ""),
    "more_images": (None, ""),
    **__import__("games").extra("LEGAL_PARTS", {}),
}
MIRROR_GAMES = (("pokemon", "Pokémon"), ("lorcana", "Disney Lorcana"), *__import__("games").extra("MIRROR_GAMES", ()))


def _ready():
    from games import GAMES
    return {k for k, _, r in GAMES if r}


def legal_entries():
    """LEGAL_TEXT plus the notices of the games that are ready (after Yu-Gi-Oh!). -> [(title, text)]"""
    ready = _ready()
    extra = [(title, text) for key, title, text in GAME_LEGAL if key in ready]
    at = next((i + 1 for i, (t, _) in enumerate(LEGAL_TEXT) if t == "Yu-Gi-Oh!"), len(LEGAL_TEXT))
    return LEGAL_TEXT[:at] + extra + LEGAL_TEXT[at:]


def legal_text(text):
    """A legal text translated, its {placeholders} filled with the lines of the games that are ready."""
    t = tr(text)
    if "{" not in t:
        return t
    ready = _ready()
    parts = {name: tr(line) if key in ready else "" for name, (key, line) in LEGAL_PARTS.items()}
    names = [n for k, n in MIRROR_GAMES if k in ready]
    parts["mirror_games"] = names[-1] if len(names) < 2 else ", ".join(names[:-1]) + tr(" and ") + names[-1]
    return t.format(**parts)
NAV_PAGES = [("stats", "▲", "Statistik", "Wie laufen deine Packs, Tausche und deine Sammlung?"),
             ("sessions", "☰", "Logs & stats", "Vergangene Logs ansehen und bearbeiten")]
SESS_COLUMNS = ["Datum", "Titel / Produkt", "Typen", "Tags", "Packs", "Karten", "Wert", "Einsatz", "Bilanz"]
PRODUCTS = ["Play Booster", "Collector Booster", "Set Booster", "Draft Booster", "Jumpstart Booster",
            "Play Booster Display", "Collector Booster Display", "Set Booster Display", "Bundle", "Commander Deck",
            "Prerelease Pack", "Secret Lair", "Gemischte Packs"]
PRICE_MODES = [("start", tr("on start")), ("daily", tr("once a day (on start)")),
               ("close", tr("on close")), ("manual", tr("manually only"))]
CATALOG_MODES = [("start", tr("on start")), ("weekly", tr("once a week")), ("manual", tr("manually only"))]
JOB_TEXT = {"download": tr("downloading"), "update": tr("updating prices"), "remove": tr("removing"),
            "carddb": tr("loading card database"), "images": tr("loading images"),
            "export": tr("exporting"), "import": tr("importing"),
            "pricehist": tr("Loading price history"), "prices": tr("updating prices"),
            "pack": tr("Downloading data pack")}
jobqueue.JOB_TEXT.update(JOB_TEXT)   # the queue's labels – translated here, after set_language


def no_power_throttling():
    """Windows 11 throttles programs whose window isn't in front (EcoQoS, coarser timer) – then the stream
    animations stutter (e.g. the floating big card) as soon as you're in another window. Turn it off:
    Bent°Corner often runs alongside OBS & co. and should stay smooth."""
    if sys.platform != "win32":
        return
    import ctypes

    class State(ctypes.Structure):
        _fields_ = [("Version", ctypes.c_ulong), ("ControlMask", ctypes.c_ulong), ("StateMask", ctypes.c_ulong)]
    try:
        st = State(1, 0x1 | 0x4, 0)   # EXECUTION_SPEED + IGNORE_TIMER_RESOLUTION: both off (StateMask 0)
        k32 = ctypes.WinDLL("kernel32")   # own instance: types set here don't affect ctypes.windll (uiaguard!)
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.SetProcessInformation.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
        ok = k32.SetProcessInformation(k32.GetCurrentProcess(), 4, ctypes.byref(st), ctypes.sizeof(st))  # 4 = Throttling
        log.info("Power throttling off: %s", bool(ok))
    except Exception as e:  # noqa: BLE001 – older Windows versions don't know this
        log.info("Power throttling: %s", e)


# ---------- Overlay (painted into the stream window) ----------


from ui.overlay_paint import Overlay  # noqa: E402


# ---------- Video display (preview and stream) ----------
from ui.scanview import ScanView  # noqa: E402


# Navigation items at the top (Qt Quick draws them; pictograms: qml/components/NavIcon.qml) – short names, all tabs
# the same width (P5: the page itself says “Import/Export”). Two words stacked (\n): two small lines next to the icon
# (review .93, Oliver) – the width counts only the longer line
NAV_ITEMS = (("stats", "Statistik"), ("sessions", "Logs\nStats"), ("scan", "Scannen"),
             ("library", "Bibliothek"), ("decks", "Decks"), ("testing", "Spielen"), ("import", "Import\nExport"),
             ("trade", "Orbit"), ("settings", "Einstellungen"), ("profile", "Profil"))
# Start page at program start (Settings → General → Program window)
START_PAGES = {"library": "Bibliothek", "scan": "Scannen", "sessions": "Logs & stats", "decks": "Decks",
               "trade": "Orbit", "import": "Import/Export", "stats": "Statistik"}
# Page transition (appearance; Qt Quick plays it)
PAGE_ANIMS = [("flip", "Blättern – die neue Seite kommt von hinten (zurück: legt sich von vorn darüber)"),
              ("slide", "Rutschen – wie Wischen in der Fotos-App: Seite gleitet seitlich raus, die neue rein")]


from ui.streamwindow import StreamWindow  # noqa: E402

# ---------- Windows in the stream: search/edit card, stream info ----------
from ui.panels import CardPanel  # noqa: E402


# ---------- Background tasks ----------
from ui.dialogs import end_session_dialog, pack_types_dialog  # noqa: E402


class Bridge(QtCore.QObject):
    loaded = QtCore.Signal(object, object)       # cards, matcher
    progress = QtCore.Signal(str, int, int)
    job_done = QtCore.Signal(object, str, str)   # job, message, error
    catalog = QtCore.Signal(object, bool)        # set list from Scryfall, triggered by hand?
    ticket = QtCore.Signal(object)               # camera read a trade ticket
    relay_done = QtCore.Signal(str, object, str)  # mailbox: kind, result, error
    backup_done = QtCore.Signal(object)           # automatic backup: [(target, ok, text)]
    update_changed = QtCore.Signal()              # updater (updater.py): state/progress


BASIC_LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}


def is_basic_land(name):
    name = (name or "").replace("Snow-Covered ", "")
    return name in BASIC_LANDS


def human_mb(n):
    mb = n / 2**20
    if mb < 1:
        return "< 1 MB"
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


# ---------- Main window ----------
class UndoKeys(QtCore.QObject):
    """Ctrl + key left of X = undo, Ctrl + key in the top row (Y/Z) = redo – by the key's position,
    not the letter: so on German keyboards Ctrl+Y / Ctrl+Z, on English ones Ctrl+Z / Ctrl+Y.
    In text fields the field's own undo applies."""
    SC_UNDO, SC_REDO = 0x2C, 0x15   # Windows scan codes (key at bottom left next to X / top row after T)

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.ctrl = ctrl

    def eventFilter(self, obj, ev):
        if ev.type() != QtCore.QEvent.Type.KeyPress or not isinstance(obj, QtGui.QWindow):
            return False
        mods = ev.modifiers()
        if not (mods & Qt.ControlModifier) or (mods & Qt.AltModifier):
            return False
        sc = ev.nativeScanCode()
        if sc:
            hit_undo, hit_redo = sc == self.SC_UNDO, sc == self.SC_REDO
        else:
            hit_undo, hit_redo = ev.key() == Qt.Key_Z, ev.key() == Qt.Key_Y
        if not (hit_undo or hit_redo):
            return False
        fo = QtGui.QGuiApplication.focusObject()
        if fo is not None and any(t in fo.metaObject().className() for t in ("TextInput", "TextEdit", "LineEdit")):
            return False   # text field: its own undo
        redo = hit_redo or bool(mods & Qt.ShiftModifier)
        self.ctrl.do_undo(redo)
        return True


class MainWindow(ScanControl, JobQueue, UpkeepControl, RelayControl, QtCore.QObject):
    """Program control (camera, recognition, sessions, sets, collection, settings) – not a window: everything is
    shown by Qt Quick (quickshell)."""
    sess_changed = QtCore.Signal()  # Sessions: table, selection, overview or pack list changed
    preview_watched = False  # Qt Quick: the camera preview in the settings is currently visible (qscan.PreviewBackend)

    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()
        conditions.bind(self.settings)   # condition: scale and default when scanning
        from ui import lagwatch
        lagwatch.start(self)   # UI hangs into the log (to find stutter)
        if self.settings.get("scan_mode") != "ai":   # only the AI is available (the other modes are dormant)
            self.settings["scan_mode"] = "ai"
        if not games.current().text_recognition and self.settings.get("scan_mode") not in ("ai", "ai_foil"):
            self.settings["scan_mode"] = "ai"   # games without text recognition: AI only
        # Performance level: on first start from the hardware (read locally only), afterwards as chosen
        self.hw = hwinfo.read()
        if self.settings.get("perf_level") not in dict(perf.LEVELS):
            self.settings["perf_level"] = perf.detect(self.hw)
        perf.set_level(self.settings["perf_level"])
        currency.set_current(self.settings["currency"])
        QtCore.QTimer.singleShot(4000, carddb.prewarm_printed)  # names in other languages for the search (background)
        self.camera = Camera()
        self.camera.phone_starter = self.phone_start   # phone as camera: server only when needed
        self.camera.mirror = self.settings["mirror"]
        self.camera.flip_v = self.settings["mirror_v"]
        try:  # move old folders (data/sets, data/images, data/sessions) into the new structure
            library.migrate_layout()
        except Exception:
            log.exception("Moving the data failed")
        self.heal_prints()
        self.session = self.blank_session(sessions.latest_open())  # continue an open session (e.g. after a crash)
        self.saved_rev = self.session.rev
        self.recognizer = Recognizer(self.camera, self.session, self.settings)
        self.tracker = tracker.CardTracker(self.camera, self.settings, self.recognizer)
        self.overlay = Overlay(self.settings)
        self.cards = []
        self.frame_rgb, self.frame_seq = None, -1
        self.last_rev, self.snap = -1, self.session.snapshot()

        # Queue for set jobs (download, update, remove; internal: load, rebuild)
        self.jobs, self.current = [], None
        self.packs_missing = set()   # data packs the server doesn't have yet (packs.PackMissing) – not asked again
        self.cancel_requested = self.quit_when_done = self.force_quit = False
        self.img_rate, self.feat_rate, self._phase = 0.35, 0.015, ("", 0.0, 0)  # seconds per image/card
        self.catalog_sets, self.catalog_by_code, self.installed, self.installed_by_code = [], {}, [], {}
        # Set list right away from the saved state (or the bundled one), updated later in the background
        self.catalog_sets = library.cached_sets()
        self.catalog_by_code = {s["code"]: s for s in self.catalog_sets}
        self.suggest_codes, self.last_msg = {}, ""

        self.bridge = Bridge()
        self.bridge.loaded.connect(self.on_loaded)
        self.bridge.progress.connect(self.on_progress)
        self.bridge.job_done.connect(self.on_job_done)
        self.bridge.catalog.connect(self.on_catalog)
        self.bridge.ticket.connect(self.ticket_seen)
        self.recognizer.on_ticket = self.bridge.ticket.emit

        self._save_timer = QtCore.QTimer(self, singleShot=True, interval=500, timeout=self.save_settings)
        self._session_timer = QtCore.QTimer(self, singleShot=True, interval=1000, timeout=self.save_session)
        # Limit the image cache: shortly after start and then every 30 minutes
        # Session sets changed? (scan mode "All cards": preload their images)
        # and from the third card on: comparison images of the sets currently being scanned from
        self._prefetch_timer = QtCore.QTimer(self, interval=2000, timeout=self.prefetch_tick)
        self._prefetch_timer.start()
        self._trim_timer = QtCore.QTimer(self, interval=30 * 60 * 1000, timeout=self.trim_image_cache)
        self._trim_timer.start()
        QtCore.QTimer.singleShot(20000, self.trim_image_cache)
        QtCore.QTimer.singleShot(6000, self.prewarm_search)
        # Collection: scanned cards are added when the session is saved
        self.collection = Collection()
        self.session.default_lang = self.settings["card_lang"]
        self.library_win, self._lang_tried = None, set()
        self._coll_timer = QtCore.QTimer(self, singleShot=True, interval=1500, timeout=self.save_collection)
        self._undo_keys = UndoKeys(self)   # only on the program window (see below) – app-wide it cost startup time
        if self.collection.is_new and self.settings["collection_auto"]:
            self.sync_all_sessions()
        else:
            self.logs_purge()   # logs in the trash past 60 days, then: the library = the sum of its logs
            self.logs_check()
        self._thumbs = collections.OrderedDict()
        self.closing = False
        self.init_settings()
        self.stream = StreamWindow(self)
        # One window: the former control window is now the "Settings" page
        for key in ["settings"] + [k for k, *_ in NAV_PAGES]:
            self.stream.add_page(key)
        self.load_info_fields()
        QtCore.QTimer.singleShot(300, self.ask_continue_session)

        self.fill_cameras()
        # Exchange rates once a day: needed for euros too – TCGplayer prices come in dollars (not in Orbit's Core)
        if orbit.prices_on(self.settings):
            run_async(self, currency.refresh, lambda res, err: self.currency_changed())
        self.recognizer.status = tr("Loading card data …")
        self.enqueue("load")

        # 60 frames/s for the stream window (smooth animations); the preview only on a new camera frame
        self.timer = QtCore.QTimer(self, interval=16, timeout=self.tick)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.start()
        no_power_throttling()   # Windows: don't throttle in the background (mouse elsewhere, other window in front)
        self.shell = None
        if "--widgets" not in sys.argv:  # new UI (Qt Quick); --widgets = the old one for comparison
            from ui import quickshell
            self.shell = quickshell.Shell(self)
            if self.shell.window is not None:   # undo keys: only this window's events go through Python
                self.shell.window.installEventFilter(self._undo_keys)
                self.shell.window.installEventFilter(self.activity)   # last input (mailbox slower when idle)
        start = self.settings.get("start_page") or "library"  # start page (Settings → General)
        self.stream.show_page(start if start in START_PAGES else "library", animate=False)
        from ui import tray
        self.tray = tray.Tray(self)  # system tray area of the taskbar (daily prices, price alerts)
        if "--tray" in sys.argv and self.tray.enabled:  # started with Windows: stay invisible
            self.tray.hide_to_tray(first=True)
        else:
            QtCore.QTimer.singleShot(0, self.stream.showFullScreen if self.settings["start_fullscreen"]
                                     else self.stream.showMaximized)

    # --- Settings ---
    def load_settings(self):
        s = json.loads(json.dumps(DEFAULTS))
        try:
            s.update(json.loads(SETTINGS_FILE.read_text("utf-8")))
        except (OSError, ValueError):
            pass
        return s

    def settings_changed(self):
        self._save_timer.start()

    def save_settings(self):
        if getattr(self, "restored", False):
            return
        try:
            SETTINGS_FILE.write_text(json.dumps(self.settings, indent=1, ensure_ascii=False), "utf-8")
        except OSError:
            pass

    # --- UI ---
    def page_shown(self, *keys):
        """Is one of these pages (top bar) currently open?"""
        stream = getattr(self, "stream", None)
        return stream is not None and stream.page in keys

    def init_settings(self):
        """State of the settings – without widgets (qstate). Everything is shown by qsettings/qsetpages."""
        S = qstate
        self.settings_keys = [k for k, *_ in SETTINGS_PAGES]
        self.settings_page = "scan"
        self.settings_listeners = []  # fn(section) when the section changes (Qt Quick page)
        self.preview = ScanView(self, stream=False)  # logic of the camera preview (shown: qscan.PreviewBackend)
        self.status = S.Text()            # recognition: state
        self.cam_combo = S.Choice()       # cameras
        self.res_combo = S.Choice()
        self.res_combo.addItems(["3840x2160", "2560x1440", "1920x1080", "1280x720"])
        self.res_combo.setCurrentText(self.settings["resolution"])
        self.pack_sel = None              # selected row in the current pack
        self.pack_rows = []               # [(name, foil, price)]
        self.totals = S.Text()
        self.info_summary = S.Text()
        self.scandata_info = S.Text()
        self.db_info, self.ph_info, self.data_info, self.set_total = S.Text(), S.Text(), S.Text(), S.Text()
        self.ph_btn = S.Text()
        self.ph_check = S.Flag(self.settings["price_history"])
        self.progress = S.Progress()
        self.set_filter = ""              # filter of the downloaded sets
        self.trash_sel = set()            # selected entries in the trash
        self.coll_info, self.coll_msg, self.cur_info = S.Text(), S.Text(), S.Text()
        self.cur_info.setText(tr(currency.rate_info()))
        self._rebuild_timer = QtCore.QTimer(self, singleShot=True, interval=700,
                                            timeout=lambda: self.enqueue("rebuild"))
        self.image_store = scanui.ImageStore(self)
        self.refresh_scandata()
        self.refresh_ph_info()
        self.refresh_db_info()
        self.refresh_sets()
        self.refresh_collection_info()
        self.build_nav_pages()

    def build_nav_pages(self):
        """Statistics and sessions: their own pages in the top bar (data; drawn by Qt Quick)."""
        self.build_stats_page()
        self.build_sessions_page()

    def show_settings(self, key):
        """Choose a settings section ("scan", "sessions", "sets" …)."""
        key = {"overlay": "scan"}.get(key, key)  # stream overlay now lives on the "Scan window" page
        if key not in self.settings_keys:
            return
        self.settings_page = key
        if key == "collection":
            self.refresh_collection_info()
        elif key == "sets":
            self.image_store.refresh()
        for fn in list(self.settings_listeners):
            fn(key)

    def refresh_scandata(self):
        n, size = scandata.stats()
        self.scandata_info.setText(tr(f"{n} cards · {size / 1024 / 1024:.1f} MB of 20 MB"))

    def scandata_zip(self):
        if not scandata.stats()[0]:
            self.scandata_info.setText(tr("Nothing collected yet."))
            return
        path = qdialogs.save_file(tr("Save scan data"),
                                  str(BASE / f"bentcorner-scan-data-{time.strftime('%Y-%m-%d')}.zip"), tr("ZIP (*.zip)"))
        if path:
            from ui.busy import busy
            with busy(self, tr("Saving scan data …")):
                n = scandata.make_zip(path)
            self.scandata_info.setText(tr(f"✓ {n} cards saved: {path}"))

    def scandata_clear(self):
        scandata.clear()
        self.refresh_scandata()

    def trade_holders(self, force=False):
        """Formerly: friends' card backs as chips on the cards – removed entirely (user request, 0.8.23). Kept as an
        empty answer for deck building & co. that ask for it."""
        return {}

    def trade_changed(self):
        """Friends imported/switched on/off: redraw chips everywhere."""
        self._holders = None
        page = getattr(self, "trade_page", None)
        if page is not None:
            page.holders_changed()
        page = getattr(self, "deck_page", None)
        if page is not None and getattr(page, "editor", None) is not None and page.editor.deck is not None:
            page.editor.fill_list()
            page.editor.results.changed.emit()

    def maybe_welcome(self):
        """No profile yet: ask once, playfully, for a name and card back."""
        from system import userprofile
        prof = userprofile.get(self.settings)
        if (prof and prof.get("name")) or self.settings.get("profile_asked"):
            return
        self.settings["profile_asked"] = True
        userprofile.welcome(self.settings, self.settings_changed)

    # --- Trash: deleted items restorable for 60 days (datastore.TRASH_DAYS) ---
    TRASH_KINDS = {"session": "Log", "deck": "Deck", "friend": "Freund", "cards": "Karte",
                   "sesscard": "Karte aus Log", "sesspack": "Pack aus Log"}

    def fill_trash(self):
        qstate._changed()  # the trash is shown on the "General" settings page (trash_view)

    def trash_view(self):
        """-> [(name, text)] in the trash."""
        from system import datastore
        out = []
        for name, e in datastore.trash_list():
            when = time.strftime("%d.%m.%Y %H:%M", time.localtime(e.get("deleted", 0)))
            out.append((name, f"{tr(self.TRASH_KINDS.get(e['kind'], e['kind']))} „{e.get('title')}“"
                              f"   ·   {tr("deleted")} {when}"))
        return out

    def _trash_selected(self):
        sel, self.trash_sel = sorted(self.trash_sel), set()
        return sel

    def trash_restore(self, e):
        """Put an entry from the trash back in its place."""
        kind, data = e["kind"], e["data"]
        if kind == "session":
            d = data["session"]
            if data.get("kept"):
                d["collection"] = False  # the cards are still (detached) in the collection – not twice
            sessions.save(d)
            if data.get("items"):
                self.collection.restore_items(data["items"])
                self.save_collection()
            self.refresh_stats()
        elif kind == "deck":
            page = getattr(self, "deck_page", None)
            if page is not None:
                page.decks = [x for x in page.decks if x["id"] != data["id"]] + [data]
                page.save()
                page.fill_overview()
            else:
                from collection import decks as decks_mod
                decks_mod.save([x for x in decks_mod.load() if x["id"] != data["id"]] + [data])
        elif kind == "friend":
            from collection import trade
            trade.save_friend(data)
            page = getattr(self, "trade_page", None)
            if page is not None and hasattr(page, "fill_friends"):
                page.fill_friends()
            if hasattr(self, "trade_changed"):
                self.trade_changed()
        elif kind in ("sesscard", "sesspack"):
            sid = data["sid"]
            if sid != self.session.id and not sessions.exists(sid):
                qdialogs.info(tr("Restore"), tr("Its log no longer exists – restore the log from the trash first, then the card."))
                from system import datastore
                datastore.trash_put(kind, e.get("title", ""), data)  # stays in the trash
                return

            def put_back(sess):
                with sess.lock:
                    if kind == "sesspack":
                        sess.packs.insert(min(max(0, data["pi"]), len(sess.packs)), data["pack"])
                    else:
                        if not sess.packs:
                            sess.packs.append({"opened": time.time(), "cards": [], "type": None})
                        pk = sess.packs[min(max(0, data["pi"]), len(sess.packs) - 1)]
                        pk["cards"].insert(min(max(0, data["ci"]), len(pk["cards"])), data["entry"])
                    sess.rev += 1
            self.stats_apply(sid, put_back)
        elif kind == "cards":
            self.collection.restore_items(data["items"])
            for it in data["items"]:   # back in the library: the matching line (logs as the source)
                self._manual(it, int(it.get("count", 1)))
            self.save_collection()
            lib = getattr(self, "library_win", None)
            if lib is not None:
                lib.refresh(keep=True)
        self.stream_toast(tr(f"Restored: “{e.get('title')}”"))

    def trash_empty(self):
        from system import datastore
        if qdialogs.question(tr("Empty trash"), tr("Delete everything in the trash for good?")):
            datastore.trash_drop()
            for d in sessions.hidden_all():   # hidden logs too (their kept cards become lines first)
                self.log_for_good(d["id"])
            self.fill_trash()
            self.refresh_stats()

    def stream_toast(self, text):
        """Short message at the bottom of the program window (Qt Quick)."""
        shell = getattr(self, "shell", None)
        if shell is not None:
            shell.show_toast(text)

    def refresh_db_info(self):
        st = carddb.status()
        if not st:
            self.db_info.setText(tr("Not downloaded yet. Without the database everything works as before (search via Scryfall)."))
            return
        stamp = time.strftime("%d.%m.%Y %H:%M", time.localtime(st["updated"]))
        txt = tr(f"{st['cards']:,} cards · as of {stamp} · {human_mb(st['size'])}").replace(",", ".")
        if st["langs"]:
            txt += tr(f" · language index with {st['langs']:,} printings").replace(",", ".")
        self.db_info.setText(txt)

    def refresh_ph_info(self):
        if not hasattr(self, "ph_info"):
            return
        on = bool(self.settings["price_history"])
        st = pricehist.status()
        self.ph_btn.setVisible(on)
        if not on:
            self.ph_info.setText(tr("Off. Checked: load the last 90 days, then add each day."))
        elif not st:
            self.ph_info.setText(tr("Loading … (progress in the queue above)"))
        else:
            day = pricehist.date_of(st["updated"]).strftime("%d.%m.%Y")
            self.ph_info.setText(tr(f"{st['cards']:,} cards with history · as of {day} · {human_mb(st['size'])} · source: MTGJSON").replace(",", "."))

    def ph_eta(self):
        """Seconds until the price history is loaded (running or queued) – None if nothing is loading."""
        cur = self.current or {}
        left = max(0.0, self.job_estimate(cur) - (time.time() - getattr(self, "_job_t0", time.time()))) if cur else 0.0
        if cur.get("kind") == "pricehist" and not cur.get("daily"):
            return max(10.0, left)
        for j in self.jobs:
            left += self.job_estimate(j)
            if j["kind"] == "pricehist" and not j.get("daily"):
                return max(10.0, left)
        return None

    def enable_price_history(self):
        """"Load price history" from the detail/alert view: like the checkbox in the settings."""
        if hasattr(self, "ph_check"):
            self.ph_check.blockSignals(True)
            self.ph_check.setChecked(True)
            self.ph_check.blockSignals(False)
        self.toggle_price_history(True)

    def toggle_price_history(self, on):
        if on:
            self.settings["price_history"] = True
            self.settings_changed()
            if not pricehist.status() and orbit.prices_on(self.settings):
                self.enqueue("pricehist", "ph", label="€", name=tr("Price history"))
        else:
            if pricehist.exists():
                if not qdialogs.question(tr("Price history"),
                                         tr("Turn off price history and delete the saved data?")):
                    self.ph_check.blockSignals(True)
                    self.ph_check.setChecked(True)
                    self.ph_check.blockSignals(False)
                    return
                pricehist.delete()
            self.settings["price_history"] = False
            self.settings_changed()
        self.refresh_ph_info()

    # --- Sets: list and search ---
    def refresh_sets(self):
        self.jobs_changed()
        self.installed = sorted(library.installed_sets(), key=lambda s: -s["ram"])
        self.installed_by_code = {s["code"]: s for s in self.installed}
        self.refresh_queue()
        self.refresh_list()

    def refresh_queue(self):
        qstate._changed()  # the queue is shown on the "Sets & card data" settings page (queue_view)

    def queue_view(self):
        """Running and waiting jobs -> [{"label", "name", "state", "est", "job"}]."""
        out = []
        for j in ([self.current] if self.current else []) + self.jobs:
            if j["kind"] not in JOB_TEXT:
                continue
            running = j is self.current
            out.append({"label": j.get("label") or j["code"], "name": j["name"],
                        "state": tr("paused") if j.get("paused") else
                        JOB_TEXT[j["kind"]] + (tr(" …") if running else tr(" (waiting)")),
                        "est": "" if running else f"~ {fmt_duration(self.job_estimate(j))}", "job": j})
        return out

    def root_of(self, s):
        """Main set of a set family, e.g. fic, fca, tfin, tfic -> fin."""
        code, seen = s["code"], set()
        parent = self.catalog_by_code.get(code, {}).get("parent") or s.get("parent")
        while parent and parent not in seen:
            seen.add(code)
            code = parent
            parent = (self.catalog_by_code.get(code, {}).get("parent")
                      or self.installed_by_code.get(code, {}).get("parent"))
        return code

    def refresh_list(self):
        """Downloaded sets: update the total (the list itself is built by sets_view)."""
        disabled = set(self.settings["disabled_sets"])
        if self.installed:
            active = [s for s in self.installed if s["code"] not in disabled]
            self.set_total.setText(
                tr(f"<b>Downloaded</b> · {len(self.installed)} sets, {len(active)} active · ≈ <b>{human_mb(sum((s['ram'] for s in active)))}</b> memory · {human_mb(sum((s['disk'] for s in self.installed)))} disk"))
        else:
            self.set_total.setText(tr("<b>Downloaded</b> · no sets yet. Search above and download."))
        qstate._changed()

    def sets_view(self):
        """Downloaded sets, grouped by main set, filtered (set_filter).
        -> [{"kind": "group"|"set", …}] in display order."""
        disabled = set(self.settings["disabled_sets"])
        q = self.set_filter.strip().lower()
        groups = {}
        for s in self.installed:
            groups.setdefault(self.root_of(s), []).append(s)
        out = []
        for root, sets in sorted(groups.items(), key=lambda kv: -sum(s["ram"] for s in kv[1])):
            sets.sort(key=lambda s: (s["code"] != root, -s["ram"]))
            title = self.set_title(root)
            visible = sets
            if q and not (q in root or q in title.lower()):
                visible = [s for s in sets if q in s["code"] or q in s["name"].lower()]
            if not visible:
                continue
            if len(sets) == 1:
                out.append(self._set_entry(sets[0], disabled, False))
                continue
            expanded = bool(q) or root in self.settings["expanded_groups"]
            codes = {s["code"] for s in sets}
            n_on = len(codes - disabled)
            out.append({"kind": "group", "root": root, "title": title, "sets": sets, "codes": codes, "n_on": n_on,
                        "expanded": expanded,
                        "ram": human_mb(sum(s["ram"] for s in sets if s["code"] not in disabled))})
            if expanded:
                out += [self._set_entry(s, disabled, True) for s in visible]
        return out

    def _set_entry(self, s, disabled, indent):
        on = s["code"] not in disabled
        stamp = time.localtime(s["updated"]) if s["updated"] else None
        day = time.strftime("%d.%m.", stamp) if stamp else tr("–")
        full = time.strftime("%d.%m.%Y %H:%M", stamp) if stamp else tr("–")
        return {"kind": "set", "set": s, "on": on, "indent": indent,
                "sub": tr(f"{s['count']} cards · prices {day}") + ("" if on else tr(" · off")),
                "ram": f"≈ {human_mb(s['ram'])}",
                "tip": tr(f"Prices from {full} · {human_mb(s['disk'])} on disk · ≈ {human_mb(s['ram'])} memory")}

    def toggle_group(self, root):
        exp = self.settings["expanded_groups"]
        exp.remove(root) if root in exp else exp.append(root)
        self.settings_changed()
        self.refresh_list()

    def set_enabled(self, codes, on):
        dis = set(self.settings["disabled_sets"])
        dis = dis - codes if on else dis | codes
        self.settings["disabled_sets"] = sorted(dis)
        self.settings_changed()
        QtCore.QTimer.singleShot(0, self.refresh_list)  # don't clear our own checkmark inside the click handler
        self._rebuild_timer.start()  # several clicks in quick succession = one rebuild

    def remove_group(self, root, sets):
        names = "\n".join(f"  {s['code'].upper()}  {s['name']}" for s in sets)
        if qdialogs.question(tr("Remove sets"),
                             tr(f"Remove all {len(sets)} sets of group {root.upper()}?\n\n{names}\n\nThe card images will be deleted ({human_mb(sum((s['disk'] for s in sets)))}).")):
            for s in sets:
                self.enqueue("remove", s["code"])

    def set_title(self, code):
        for s in self.installed:
            if s["code"] == code:
                return s["name"]
        return self.catalog_by_code.get(code, {}).get("name", code.upper())

    def load_catalog(self, max_age, manual=False):
        key = games.current().key

        def work():
            sets = library.scryfall_sets(max_age)
            if games.current().key == key:   # game switched meanwhile: the set list belongs to the old one
                self.bridge.catalog.emit(sets, manual)
        threading.Thread(target=work, daemon=True).start()
        if manual:
            self.data_info.setText(tr("Updating set list …"))

    def on_catalog(self, sets, manual):
        self.catalog_sets = sets
        self.catalog_by_code = {s["code"]: s for s in sets}
        self.refresh_list()  # groups (main set) come from the set list
        if manual:
            self.data_info.setText(tr(f"Set list updated: {len(sets)} sets.") if sets
                                   else tr("Could not load the set list (no internet?)."))

    def update_all(self):
        """Today's prices of all cards (MTGJSON, one download) – for sets, collection, Library, price history.
        Orbit's Core fetches no prices: the button says so and leads to the slider."""
        if not orbit.prices_on(self.settings):
            self.stream_toast(tr("Prices come with Near Orbit – Settings → Friends & privacy"))
            self.stream.show_page("settings", back=True)
            self.show_settings("privacy")
            return
        self.enqueue("prices", "all", label="€", name=tr("Prices (all cards)"))
        self.settings["last_price_day"] = time.strftime("%Y-%m-%d")
        self.settings_changed()

    def update_lists(self):
        """Refresh the card lists of all enabled sets from Scryfall (new cards, disabled ones via ↻)."""
        for s in self.installed:
            if s["code"] not in self.settings["disabled_sets"]:
                self.enqueue("update", s["code"])

    @staticmethod
    def apply_prices(prices):
        """Write today's prices into the card database and set files (background thread). -> number of set cards."""
        if carddb.exists() and prices:
            with carddb.connection() as con:
                con.executemany(
                    "UPDATE cards SET eur = COALESCE(?, eur), eur_foil = COALESCE(?, eur_foil), "
                    "usd = COALESCE(?, usd), usd_foil = COALESCE(?, usd_foil) WHERE id = ?",
                    [(p.get("eur"), p.get("eur_foil"), p.get("usd"), p.get("usd_foil"), sid) for sid, p in prices.items()])
                con.commit()
        n = 0
        for st in library.installed_sets():
            meta = library._meta(st["code"])
            if not meta:
                continue
            changed = False
            for c in meta["cards"]:
                p = prices.get(scryfall_id(c["id"]))
                if not p:
                    continue
                new = (p.get("eur", c.get("eur")), p.get("eur_foil", c.get("eur_foil")))
                if (c.get("eur"), c.get("eur_foil")) != new:
                    c["eur"], c["eur_foil"] = new
                    changed, n = True, n + 1
            if changed:
                library._save_meta(meta)
        return n

    def remove_set(self, s):
        if qdialogs.question(tr("Remove set"), tr(f"Remove {s['code'].upper()} ({s['name']})?\n\nThe card images will be deleted ({human_mb(s['disk'])}). You can download the set again at any time.")):
            self.enqueue("remove", s["code"])

    # --- Sets: queue ---

    def update_fingerprints(self, cards):
        """AI fingerprints: compute missing/outdated sets in the background, then set the index."""
        if not fingerprint.available():   # no SCAN° Engine (model missing): a game with a collector line reader scans
            # by that alone (an empty index -> aiscan._footer_only), the others by the text recognition (no index:
            # recognizer stage "no_engine")
            footer = games.current().footer_parse is not None and carddb.exists()
            self.recognizer.fp_index = fingerprint.Index({}, [], None) if footer else None
            return
        if getattr(getattr(self, "tray", None), "hidden", False):
            return  # only in the tray: load the AI only when opened
        self._fp_gen = getattr(self, "_fp_gen", 0) + 1
        gen = self._fp_gen
        by_set = {}
        for c in cards:
            by_set.setdefault(c["set"].lower(), []).append(c)
        game = games.current().key
        sig = (game, len(cards), tuple(sorted(by_set)))
        cached = getattr(self, "_fp_cache", {}).get(game)
        if cached is not None and getattr(cached, "sig", None) == sig:   # switched back to the game: reuse the index
            self.recognizer.fp_index = cached
            log.info("AI index %s from memory (%s cards)", game, len(cached))
            return

        def work():
            try:
                for code, cs in by_set.items():
                    if gen != self._fp_gen:
                        return
                    if not fingerprint.up_to_date(code, cs):  # new set or cards added
                        t = time.time()
                        n = fingerprint.build_set(code, cs)
                        log.info("AI fingerprints %s: %s cards in %.0f s", code.upper(), n, time.time() - t)
                if gen == self._fp_gen:
                    glob = fingerprint.global_path() if carddb.exists() else None
                    index = fingerprint.Index({c["id"]: c for c in cards}, list(by_set), glob)
                    index.sig = sig
                    if self.camera_watched():   # scan page open: load the network now (otherwise only when scanning)
                        self.warm_ai()
                    if gen != self._fp_gen or games.current().key != game:   # switched in the meantime
                        return
                    self.recognizer.fp_index = index
                    log.info("AI index: %s cards (%s from loaded sets, %s bundled)", len(index),
                             index.n_sets, index.n_global)
            except Exception:
                log.exception("AI fingerprints")
        threading.Thread(target=work, daemon=True).start()

    def build_matcher(self):
        """Load card lists; the image features (lots of memory, ~30 MB per set) only for the scan mode
        "Loaded sets" – AI mode and text recognition don't need them."""
        exclude = set(self.settings["disabled_sets"])
        if self.settings.get("scan_mode") != "sets":
            return library.load_cards(exclude=exclude), None
        cards, pts, des = library.load_library(exclude=exclude)
        return cards, (Matcher(cards, pts, des, self.settings["min_inliers"]) if cards else None)

    def check_alarms(self):
        """Price alerts after a price update: message in the tray or in the window."""
        from collection import alarms
        try:
            hits = alarms.check(self.settings, self.collection)
        except Exception:  # noqa: BLE001 – an alert must never disturb the update
            log.exception("Price alerts")
            return
        self.settings_changed()
        for title, text in hits[:5]:
            self.tray.notify(title, text)
        if len(hits) > 5:
            self.tray.notify(tr("Price alert"), tr(f"… and {len(hits) - 5} more – Orbit → Wishlist."))

    def alarms_at_start(self):
        """At start: check alerts (report newly triggered ones) and say once how many are currently triggered –
        even if no price update ran (prices at most every 4 h)."""
        from collection import alarms
        self.check_alarms()
        try:
            n = sum(1 for a in alarms.alarms(self.settings) if a.get("hit"))
            n += sum(sum(1 for v in (a.get("hit") or {}).values() if v) for a in alarms.list_alarms(self.settings))
        except Exception:  # noqa: BLE001
            return
        if n:
            self.stream_toast(tr("1 price alert triggered – Orbit → Price alerts") if n == 1 else
                              tr(f"{n} price alerts triggered – Orbit → Price alerts"))
            self.stream.set_badge("trade", True)

    def show_import(self, key="deck", back=True, **ctx):
        """Open the "Import/Export" tab directly at the matching sub-item (deck, collection, wishlist, friend, sets –
        and for handing out share_decks, deck_export, coll_export, friend_export, session_share, offer, backup)."""
        self.stream.show_page("import", back=back)
        self.import_page.show_tab(key, **ctx)

    def go_export(self, key, **ctx):
        self.show_import(key, **ctx)

    def do_undo(self, redo=False):
        """Ctrl+Y/Z: in the deck builder its history, otherwise the last saved steps (collection, decks, lists …)."""
        from system import undo
        shell = getattr(self, "shell", None)
        if shell is not None and shell.sheets.covering:
            return
        dp = getattr(self, "deck_page", None)
        if dp is not None and dp.view == "editor" and self.stream.page == "decks":
            if dp.editor.step(1 if redo else -1):
                dp.toast(tr("Redone") if redo else tr("Undone"))
            else:
                dp.toast(tr("Nothing to redo") if redo else tr("Nothing to undo"))
            return
        if self._coll_timer.isActive():   # save a pending change first – it's the last step
            self._coll_timer.stop()
            self.save_collection()
        res = undo.redo() if redo else undo.undo()
        toast = getattr(shell, "show_toast", None) if shell is not None else None
        if res is None:
            if toast:
                toast(tr("Nothing to redo") if redo else tr("Nothing to undo – not possible after switching games")
                      if undo.cleared_why() == "game" else tr("Nothing to undo"))
            return
        paths, label = res
        self.after_undo(paths)
        if toast:
            what = f" ({tr(label)})" if label else ""
            toast((tr("Redone") if redo else tr("Undone")) + what)

    def after_undo(self, paths):
        """After undo/redo: re-read everything that belongs to the files."""
        from collection import collection as collmod
        names = {pathlib.Path(p).name for p in paths}
        if collmod.FILE.name in names:
            self.collection.reload()
            # the files went back past the logs: what differs now becomes lines (the library = sum of its logs)
            from system import undo
            with undo.quiet():
                self.logs_check(why=tr("undone"))
            if hasattr(self, "coll_info"):
                self.refresh_collection_info()
        dp = getattr(self, "deck_page", None)
        if dp is not None:
            if decks.FILE.name in names:
                dp.decks = decks.load()
                if dp.view == "editor" and dp.editor.deck is not None and not dp.editor.dirty:
                    d = next((x for x in dp.decks if x["id"] == dp.editor.deck["id"]), None)
                    if d is not None:
                        dp.editor.open(d)
                    else:
                        dp.show_overview()
                dp.fill_overview()
            try:
                dp.update_owned()
            except Exception:  # noqa: BLE001 – the display refreshes next time
                log.exception("Decks after undo")
        if self.library_win is not None:
            try:
                self.library_win.refresh(keep=True)
            except Exception:  # noqa: BLE001
                log.exception("Library after undo")
        tp = getattr(self, "trade_page", None)
        if tp is not None:
            try:
                if hasattr(tp, "reload_friends"):
                    tp.reload_friends()
                tp.list_panel.fill()
                tb = self.shell.backends.get("trade") if getattr(self, "shell", None) is not None else None
                if tb is not None:
                    for sig in ("listsChanged", "entriesChanged", "changed"):
                        if hasattr(tb, sig):
                            getattr(tb, sig).emit()
            except Exception:  # noqa: BLE001
                log.exception("Trade after undo")
        if any(pathlib.Path(p).parent == sessions.SESSIONS for p in paths) and hasattr(self, "refresh_stats"):
            self.refresh_stats()   # e.g. trade session after undo

    # --- Start / end session (no permanent session) ---
    def blank_session(self, data=None, cards=()):
        """New session shell. If it isn't a saved one (data without id), it only counts after "New session"
        (setting session_required, default on)."""
        s = Session(list(cards), data)
        if (data is None or not data.get("id")) and self.settings.get("session_required", True):
            s.info["active"] = False
        return s

    def session_button(self):
        """Button in Sessions/Scan: if a session is running → end it; otherwise → "New session" (flow in the window)."""
        if self.session.active:
            return self.new_session()
        from collection import sessionstart
        sessionstart.open_wizard(self)
        return True

    def start_session(self, game, kind, pack_type, planned=0, paid=0.0, title=""):
        """From the "New session" flow: choose game, set type and info, release the session, go to scanning."""
        if game != games.current().key:   # switch first (waits for a running job if needed), then start
            return self.switch_game(game, then=lambda: self.start_session(game, kind, pack_type, planned, paid, title))
        s = self.session
        if kind == "packs":
            self.set_session_kind("packs", s)
            s.set_pack_type(pack_type)
        elif kind == "cards":
            self.set_session_kind("cards", s)
        else:
            self.set_session_kind("singles", s)
            s.set_pack_type("trade" if kind == "trade" else "purchase")
        s.set_info(active=True, title=title or "", packs_planned=int(planned or 0), paid=float(paid or 0),
                   trade_scan=kind == "trade")
        self.save_session()
        self.load_info_fields()
        if hasattr(self, "refresh_stats"):
            self.refresh_stats()
        self.stream.show_page("scan")
        return True

    def start_ticket(self, game, how):
        """"New session → Trade ticket": load as an image or scan from the phone with the camera."""
        if game != games.current().key:
            return self.switch_game(game, then=lambda: self.start_ticket(game, how))
        tp = getattr(self, "trade_page", None)
        if how == "file":
            if tp is not None:
                tp.import_dialog()
            return True
        self.recognizer.ticket_mode = True
        self.stream.show_page("scan")
        self.stream_toast(tr("Hold the trade ticket in the frame – e.g. the image on your phone screen."))
        return True

    def ticket_seen(self, t):
        """The camera read a trade ticket (main thread)."""
        self.recognizer.ticket_mode = False
        tp = getattr(self, "trade_page", None)
        if tp is not None:
            tp.book_ticket(t)

    def end_trade_scan(self):
        """End a trade session: cards marked "giving away" leave the collection (one booking, can be
        undone), the others are added as always. -> False = cancelled"""
        s = self.session
        outs = [e for p in s.packs for e in p["cards"] if e.get("out")]
        if not outs:
            return True
        from collection import bookings
        give = {}
        for e in outs:
            k = (str(e.get("set") or "").lower(), str(e.get("number") or ""), e.get("lang") or "en", bool(e.get("foil")))
            give[k] = give.get(k, 0) + 1
        lines = [[k[0], k[1], k[2], 1 if k[3] else 0, n, next(e["name"] for e in outs
                  if (str(e.get("set") or "").lower(), str(e.get("number") or "")) == (k[0], k[1]))]
                 for k, n in give.items()]
        partner = ["", s.info.get("title") or ""]
        bookings.book_trade(self.collection, {"id": f"session-{s.id}"}, lines, [], partner)
        log.info("Trade scan %s: %s cards given away", s.id, sum(give.values()))
        return True

    AUTO_JOBS = ("prices", "pricehist", "load", "rebuild")   # run by themselves – a game switch cancels them

    def switch_game(self, key, then=None):
        """Switch game without restarting: save everything, switch folders (common.switch_game), then load the new
        game's collection, sets, AI index, session, decks, trade and Library. If only automatic jobs are running
        (prices, price history, loading recognition): they are cancelled and caught up on the next visit to the game;
        the switch happens as soon as the running job stops (then then()). -> True if switched (or on the way)."""
        from collection import collection as collmod
        from scanner import common
        from system import undo
        if key == games.current().key or not any(c["key"] == key and c["ready"] for c in games.choices()):
            return False
        shell = getattr(self, "shell", None)
        toast = getattr(shell, "show_toast", None) if shell is not None else None
        keep = [j for j in self.jobs if self.independent_job(j)]   # game downloads: independent of the open game
        cur_free = self.current is not None and self.independent_job(self.current)
        if (self.current and not cur_free) or len(keep) < len(self.jobs):
            running = ([self.current] if self.current and not cur_free else []) + [j for j in self.jobs if j not in keep]
            if any(j["kind"] not in self.AUTO_JOBS for j in running):   # set download & co.: write into the old game
                if toast:
                    toast(tr("Wait for the running jobs (Card data) to finish – then switch."))
                return False
            self.jobs = keep
            self.__dict__.setdefault("_game_jobs_done", set()).discard(games.current().key)   # catch up later
            if self.current and not cur_free:
                self.cancel_requested = True
                self._pending_switch = (key, then)
                if toast:
                    toast(tr(f"Switching to {games.name_of(key)} …"))
                return True
        # Transition: fade out first (card stack + game name), then switch while hidden, then fade back in softly.
        # Better a second longer but calm – you rarely switch anyway.
        if shell is not None and getattr(self, "switch_anim", True) and hasattr(shell, "game_switch_begin")                 and shell.window is not None and shell.window.isVisible():
            if getattr(self, "_switching", False):
                return True
            self._switching = True
            t0 = time.monotonic()
            shell.game_switch_begin(games.name_of(key))

            def run():
                try:
                    self._switch_now(key, then)
                finally:
                    self._switching = False
                    rest = max(0, 1100 - int((time.monotonic() - t0) * 1000))   # show the stack for at least ~1 s
                    QtCore.QTimer.singleShot(rest, shell.game_switch_end)
            QtCore.QTimer.singleShot(340, run)
            return True
        return self._switch_now(key, then)

    def _switch_now(self, key, then=None):
        from collection import collection as collmod
        from scanner import common
        from system import undo
        shell = getattr(self, "shell", None)
        # 1. save everything of the old game
        self._coll_timer.stop()
        self.save_session()
        self.save_collection()
        dp = getattr(self, "deck_page", None)
        ed = getattr(dp, "editor", None) if dp is not None else None
        if ed is not None and getattr(ed, "deck", None) is not None and getattr(ed, "dirty", False):
            ed.save_deck()
        # remember the old game's AI index – when switching back just swap instead of rebuilding (at most two
        # games in memory)
        old_key = games.current().key
        if self.recognizer.fp_index is not None:
            cache = getattr(self, "_fp_cache", {})
            cache[old_key] = self.recognizer.fp_index
            self._fp_cache = {k: v for k, v in cache.items() if k in (old_key, key)}
        # 2. switch
        common.switch_game(key)
        undo.clear("game")   # a mixed trade's waiting part may be booked there now – no half undo afterwards
        self.settings["game"] = key
        if not games.load(key).text_recognition and self.settings.get("scan_mode") not in ("ai", "ai_foil"):
            self.settings["scan_mode"] = "ai"
        self.settings_changed()
        # 3. load the new game
        self.heal_prints()
        self.collection.reload()
        self.collection.is_new = not collmod.FILE.exists()
        self.cards = []
        self.recognizer.fp_index = None
        old_matcher, self.recognizer.matcher = self.recognizer.matcher, None
        if old_matcher is not None:
            QtCore.QTimer.singleShot(5000, old_matcher.close)
        self.session = self.blank_session(sessions.latest_open())
        self.session.default_lang = self.settings["card_lang"]
        self.saved_rev = self.session.rev
        self.recognizer.session = self.session
        self.new_overlay()
        self.catalog_sets = library.cached_sets()
        self.catalog_by_code = {s["code"]: s for s in self.catalog_sets}
        self.refresh_sets()
        if self.collection.is_new and self.settings["collection_auto"]:
            self.sync_all_sessions()
        else:
            self.logs_purge()
            self.logs_check()   # per game: its first time runs the migration
        self.recognizer.status = tr("Loading card data …")
        self.enqueue("load")
        if self._own_db_missing(key) and not self._carddb_pending():   # Lorcana without its card database: build now
            self.enqueue("carddb", "db", name=tr(f"{games.current().name}: card data"))
        for bar in [getattr(getattr(self, "library_win", None), "bar", None), getattr(ed, "bar", None)]:
            if bar is not None and hasattr(bar, "rebuild_for_game"):
                try:
                    bar.rebuild_for_game()
                except Exception:  # noqa: BLE001
                    log.exception("Search after game switch")
        if dp is not None:
            try:
                dp.decks = decks.load()
                if getattr(dp, "view", "") == "editor":
                    dp.show_overview()
                dp.fill_overview()
            except Exception:  # noqa: BLE001
                log.exception("Decks after game switch")
        tp = getattr(self, "trade_page", None)
        if tp is not None:
            try:
                friend = tp.friend_id if getattr(tp, "view", "") == "friend" else None
                if hasattr(tp, "open_me"):   # open friend/list editor belongs to the old game
                    tp.open_me()
                if hasattr(tp, "reload_friends"):
                    tp.reload_friends()
                if hasattr(tp, "fill_friends"):
                    tp.fill_friends()
                tp.list_panel.fill()
                if friend and hasattr(tp, "reopen_friend"):   # was looking at a friend: stay there (not the alerts)
                    tp.reopen_friend(friend, key)
            except Exception:  # noqa: BLE001
                log.exception("Trade after game switch")
        pb = getattr(shell, "backends", {}).get("profile") if shell is not None else None
        if pb is not None:   # profile: binders and friends of the new game
            pb.binder.close() if pb.binder.isOpen else None
            pb.refresh()
        self.trade_changed()
        self.after_booking()   # show collection, Library, sessions anew
        if tp is not None and hasattr(tp, "apply_pending"):   # mixed trades: the part for this game
            QtCore.QTimer.singleShot(2500, lambda k=key: self._apply_pending(k))
        # the new game's daily jobs (only when due) – only after a while: whoever just takes a quick look
        # doesn't trigger downloads
        QtCore.QTimer.singleShot(20000, lambda k=key: self.game_jobs() if games.current().key == k else None)
        QtCore.QTimer.singleShot(1500, carddb.prewarm_printed)   # names in other languages for the search
        if shell is not None:
            shell.game_switched()
        log.info("Game switched: %s", key)
        try:   # shared items come without card names: fill them in from the game's card database
            from net import relay
            from collection import trade
            for d in trade.friends():
                if d.get("source") == "relay" and any(len(c) < 6 or not c[5] for c in d.get("cards") or []):
                    trade.save_friend(relay.fill_names(d))
        except Exception:  # noqa: BLE001
            log.exception("Filling in names")
        if then is not None:
            then()
        return True

    def copy_text(self, text, note=""):
        QtGui.QGuiApplication.clipboard().setText(text)
        if note:
            self.stream_toast(note)

    def trade_offers_changed(self, open_folder=False):
        """Trade offers changed (shared, read in, accepted …): redisplay the folders in the Trade tab."""
        tb = self.shell.backends.get("trade") if getattr(self, "shell", None) is not None else None
        if tb is not None and hasattr(tb, "offers_refresh"):
            tb.offers_refresh(open_folder)
        if open_folder:
            self.stream.show_page("trade", back=True)

    def book_in_game(self, key, t, give, get, partner, foreign, opts):
        """Book the part of a mixed trade in ANOTHER game without switching: briefly switch to its folders,
        book, switch back. Not while a job is running (it could meanwhile write files of the
        wrong game) -> None, then it's booked on the next opening."""
        from collection import bookings
        from collection import collection as collmod
        from scanner import common
        from collection import trade
        if self.current is not None:
            return None
        cur = games.current().key
        common.switch_game(key)
        try:
            if bookings.by_ticket(t.get("id")) is not None:
                return None
            coll = collmod.Collection()
            db = carddb.by_prints([(c[0], c[1]) for c in give + get]) if carddb.exists() else {}
            b = bookings.book_trade(coll, t, give, get, partner, cards_db=db, foreign=foreign)
            trade.after_trade(coll, b.get("taken"), get, opts.get("have", True), opts.get("wish", True))
            coll.save()
            return b
        except Exception:  # noqa: BLE001
            log.exception("Booking trade in %s", key)
            return None
        finally:
            common.switch_game(cur)

    def show_trade_session(self, key, sid):
        """"To session" from the receipt: show Sessions and select the trade session (other game: switch first)."""
        def show():
            self.stream.show_page("sessions", back=True)
            try:
                self.sess_select(sid)
                b = self.shell.backends.get("sessions") if getattr(self, "shell", None) else None
                if b is not None:
                    b.changed.emit()
                    b.detailChanged.emit()
            except Exception:  # noqa: BLE001
                log.exception("Showing trade session")
        if key == games.current().key:
            show()
        elif not self.switch_game(key, then=show):
            self.stream_toast(tr("Can't switch right now – wait for the running tasks first."))

    def show_ticket_session(self, key, ticket_id):
        """Greyed-out card of a mixed trade session clicked: switch to that game and show the session
        of the same ticket there."""
        def show():
            sid = next((d["id"] for d in sessions.load_all() if (d.get("info") or {}).get("ticket") == ticket_id), None)
            self.stream.show_page("sessions", back=True)
            if sid:
                self.show_trade_session(key, sid)
        if key == games.current().key:
            show()
        elif not self.switch_game(key, then=show):
            self.stream_toast(tr("Can't switch right now – wait for the running tasks first."))

    def _apply_pending(self, key, tries=0):
        if games.current().key != key:
            return
        try:
            if self.trade_page.apply_pending() == 0 and not carddb.exists() and tries < 20:
                QtCore.QTimer.singleShot(5000, lambda: self._apply_pending(key, tries + 1))
        except Exception:  # noqa: BLE001
            log.exception("Booking pending trades")

    def after_booking(self):
        """Trade booked or undone: show collection, sessions, Library, trade anew."""
        if hasattr(self, "coll_info"):
            self.refresh_collection_info()
        if self.library_win is not None:
            try:
                self.library_win.refresh(keep=True)
            except Exception:  # noqa: BLE001
                log.exception("Library after trade")
        if hasattr(self, "refresh_stats"):
            self.refresh_stats()
        self.trade_changed()

    def go_session_settings(self):
        """Quick settings → "Session settings": Sessions tab with the running session (for editing)."""
        self.save_session()
        self.stream.show_page("sessions", back=True)
        if hasattr(self, "refresh_stats"):
            self.refresh_stats()
        self.sess_select(self.session.id)

    def go_settings(self, tab):
        """Quick link (slider icon) into the settings – with "← Back to …". (Profile is a tab of its own.)"""
        if tab == "profile":
            self.stream.show_page("profile", back=True)
            return
        self.stream.show_page("settings", tab=tab, back=True)

    def show_alarms(self, key=None, opts=None):
        """Price alerts: Trade tab, "Price alerts" folder – with key, the editor right in this alert's row."""
        if self.tray.hidden:
            self.tray.restore()
        self.stream.show_page("trade", back=True)
        self.trade_page.show_tab(0)
        tb = getattr(getattr(self, "shell", None), "backends", {}).get("trade")
        if tb is not None:
            tb.setFolder("alarms")
            if key:   # the alert editors live in tb.alarms_b (docs/TRADE-SPLIT.md)
                if key not in tb.alarms_b.alarmOpenKeys:
                    tb.alarms_b.openAlarm(key)
                for k, v in (opts or {}).items():   # e.g. foil if the detail view shows foil
                    tb.alarms_b.setAlarmOptOf(key, k, v)

    def maybe_backup_reminder(self):
        """Gently: remind once when the last backup (or the first start) is 30 days ago."""
        s, now = self.settings, time.time()
        if not s.get("backup_since"):
            s["backup_since"] = now
            self.settings_changed()
            return
        from system import autobackup
        if not autobackup.attention(s):   # automatic backup to a second location is running: no tip needed
            return
        since = max(s.get("last_backup") or 0, s["backup_since"])
        if now - since < 30 * 86400 or (s.get("backup_reminded") or 0) > since or not self.collection.items:
            return
        s["backup_reminded"] = now
        self.settings_changed()
        self.stream.set_badge("import", True)
        self.stream_toast(tr("Tip: make a backup of your collection – Settings → Backup (e.g. to a USB stick)."))

    def after_start(self):
        from net import anonstats
        from ui import onboarding
        anonstats.bind(self.settings)   # counts only with consent (on which days which area)
        if not onboarding.active(self.settings):   # newly set up: the first-run setup asks (below)
            QtCore.QTimer.singleShot(1500, self.maybe_welcome)
        QtCore.QTimer.singleShot(8000, self.maybe_backup_reminder)
        self.relay_setup()   # friends online: fetch if switched on
        QtCore.QTimer.singleShot(12000, self.alarms_at_start)   # report price alerts even without a new price update
        from collection import trade as _trade   # automatic trade lists need the collection and deck cards
        _trade.COLLECTION[0] = lambda: self.collection.items
        _trade.DECK_NAMES[0] = self._deck_name_counts
        self.autobackup_setup()   # automatic backup (quietly in the background)
        self.updater_setup()      # updates via our own server (signed)
        from scanner import scansound          # generate scan sounds once (in the background – first scan won't wait)
        threading.Thread(target=scansound.prepare, daemon=True, name="scansound").start()
        self.packs_check()   # data bundles of the chosen games (not in the .exe) – missing ones get downloaded
        if self.settings.get("first_setup"):
            waits = any(j["kind"] == "pack" for j in self.jobs + ([self.current] if self.current else []))
            if not carddb.exists() and games.current().lang_pack != "bundled":
                # first start: load the card database (Magic: Scryfall), after that scanning works right away
                log.info("First-run setup: loading card database")
                self.enqueue("carddb", "db")
            elif carddb.exists() and not waits:
                self.settings["first_setup"] = False
                self.settings_changed()
        if onboarding.active(self.settings):   # first-run setup part 2 (profile, friends, numbers, background)
            QtCore.QTimer.singleShot(600, lambda: onboarding.start(self))
        self.lists_private_once()
        if not onboarding.active(self.settings):   # after the update: ask once whether the Library is shared
            QtCore.QTimer.singleShot(9000, self.share_library_ask)
        QtCore.QTimer.singleShot(2500, self.patchnotes_once)
        self.game_jobs()

    def patchnotes_once(self):
        """After an update show once what's new: the patch history since the last started version.
        New installations see nothing (everything is new to them); Settings → Updates always shows everything."""
        from ui import onboarding
        import version
        seen = self.settings.get("seen_version")
        if seen == version.VERSION:
            self.orbit_once()
            return
        self.settings["seen_version"] = version.VERSION
        self.settings_changed()
        if self.settings.get("first_setup") or onboarding.active(self.settings):
            return
        try:
            import patchnotes
            notes = patchnotes.NOTES
        except ImportError:
            self.orbit_once()
            return

        def key(v):   # shipped version (three digits) includes all its work-in-progress builds: 0.9.1 = 0.9.1.∞
            parts = [int(x) for x in str(v).split(".") if x.isdigit()]
            return tuple(parts + [10 ** 9] * (4 - len(parts)))
        if seen:
            new = [n for n in notes if key(seen) < key(n[0]) <= key(version.VERSION)]
        else:   # previous version unknown (first time with this display): everything from the current release
            new = [n for n in notes if version.release_of(n[0]) == version.release_of()]
        if not new:
            self.orbit_once()
            return
        # shipped versions in between with highlights: only those (at most 5 points – more nobody reads)
        hl = [t for r, pts in sorted(getattr(version, "HIGHLIGHTS", {}).items(), key=lambda x: key(x[0]), reverse=True)
              if (not seen or key(seen) < key(r)) and key(r) <= key(version.VERSION) for t in pts][:5]
        more = 0 if hl else len(new) - 5   # with highlights: „All changes“ leads to the rest

        def build(ui, d):
            rows = [ui.label(tr(f"Bent°Corner is now on {version.label()}. What's new:"), big=True)]
            if hl:
                rows.append(ui.label("<table>" + "".join(
                    f"<tr><td style='padding:4px 12px 4px 0; vertical-align:top'>•</td>"
                    f"<td style='padding:4px 0'>{html.escape(tr(t))}</td></tr>" for t in hl) + "</table>", rich=True))
            else:   # table like the patch history (Settings → Updates): version in grey, texts aligned below each other
                rows.append(ui.label("<table>" + "".join(
                    f"<tr><td style='padding:3px 14px 3px 0; color:gray; white-space:nowrap'>v{num}</td>"
                    f"<td style='padding:3px 0'>{html.escape(text)}</td></tr>" for num, _date, text in new[:5]) + "</table>",
                    rich=True))
            if more > 0:
                rows.append(ui.label(tr(f"… and {more} more changes"), color="gray"))

            def all_notes():
                d.close("all")
                self.stream.show_page("settings", back=True)
                self.show_settings("updates")
            rows += [ui.space(4), ui.row([ui.stretch(), ui.button(tr("All changes"), all_notes),
                                          ui.button(tr("Next"), lambda: d.close("ok"), primary=True)])]
            return ui.col([ui.scroll(rows[:-2], h=min(520, 130 + 56 * (len(hl) or min(5, len(new)))))] + rows[-2:],
                          spacing=12)
        qdialogs.show(tr("What's new?"), build, wait=False, on_close=lambda _r: self.orbit_once())

    def orbit_once(self):
        """Since Bent°Corner Orbit (Oliver, 2026-10-29): users from before are asked ONCE, right after "What's new?".
        Preselected is what their settings did so far (exchange on = Full Orbit, prices only by hand = Core, otherwise
        Near Orbit) – nobody is moved up to Full Orbit: the slider only changes what they pick themselves."""
        from ui import onboarding
        s = self.settings
        if orbit.asked(s) or s.get("first_setup") or onboarding.active(s):
            return

        def done(_r=None):
            if not orbit.asked(s):
                if orbit.level(s) != "full":
                    s["orbit"] = orbit.level(s)
                s["orbit_asked"] = True
                self.settings_changed()

        pending = {"lv": orbit.level(s)}   # the slider only moves – the level applies with "Done"

        def apply(d):   # Full Orbit only with the age line on (legal 03.11.) – otherwise Near Orbit
            want = pending["lv"]
            if want == "full" and not orbit.age_ok(s) and orbit.level(s) != "full":
                want = "near"
            orbit.set_level(self, want)
            d.close("ok")

        def build(ui, d):
            def pick(i):
                pending["lv"] = orbit.LEVELS[i]
                d.form.soon()
            return ui.col([
                ui.label(tr("New: Bent°Corner Orbit"), big=True),
                ui.label(tr("The Trade tab is now called Orbit. Choose how far your data may travel – preselected is what your settings did so far.")),
                ui.space(4),
                ui.orbit(orbit.LEVELS.index(pending["lv"]), pick,
                         leave=tr(orbit.LEAVE) if orbit.level(s) == "full" else ""),
                ui.row([ui.stretch(), ui.button(tr("Done"), lambda: apply(d), primary=True)]),
            ], spacing=12)
        qdialogs.show(tr("Bent°Corner Orbit"), build, wait=False, on_close=done)

    def lists_private_once(self):
        """Since 0.8.23: lists start out private – set all lists of all games to private once."""
        if self.settings.get("lists_private_v1"):
            return
        from collection import trade
        for key, _n, ready in games.GAMES:
            if not ready:
                continue
            try:
                d = trade._read_lists(key)
                if any(x.pop("shared", None) for k in ("wish", "have", "custom") for x in d[k]):
                    trade._write_lists(d, key)
            except Exception:  # noqa: BLE001
                log.exception("Setting lists to private")
        self.settings["lists_private_v1"] = True
        self.settings_changed()

    def download_game(self, key):
        """Games bar: download a game (bundle from our own server, for Magic plus the card database from
        Scryfall) – independent of the open game, switching works meanwhile."""
        from cards import packs
        name = games.name_of(key)
        if key in packs.PACKS and not (packs.installed(key) or packs.bundled(key)):
            self.enqueue("pack", key, name=tr(packs.PACKS[key]["name"]), label="PKG", dl_game=key)
        if key == "mtg" and not packs.game_ready("mtg"):
            if not carddb._has("mtg"):   # an empty file counts as missing (see carddb._drop_empty)
                self.enqueue("carddb", "db-mtg", name=tr("Magic card data (Scryfall)"), label="DB", dl_game=key,
                             **{"for": "mtg"})
        elif self._own_db_missing(key):   # no data pack (Lorcana): the app builds the card database from the source
            self.enqueue("carddb", f"db-{key}", name=tr(f"{name}: card data"), label="DB", dl_game=key,
                         **{"for": key})
        self.jobs_changed()
        if not self._game_downloading(key):   # nothing to load (already there)
            self._game_downloaded(key, name)

    @staticmethod
    def _own_db_missing(key):
        """Game without a data pack that builds its card database itself (download_db) – and it isn't there yet?"""
        from cards import packs
        if key == "mtg" or key in packs.PACKS or not games.load(key).db_target:
            return False
        return not carddb._has(key)   # an empty file (left by an old open) counts as missing and goes

    def _game_downloading(self, key):
        return any(j.get("dl_game") == key for j in self.jobs + ([self.current] if self.current else []))

    def _game_downloaded(self, key, name=None):
        """Everything for a game is there: move it to the front of the games bar, notice (no automatic switch)."""
        on = list(self.settings.get("games_on") or [])
        if key not in on:
            on.append(key)
            self.settings["games_on"] = on
            self.settings_changed()
        self.stream_toast(tr(f"{name or games.name_of(key)} is ready – open it with the game button at the top left."))
        self.jobs_changed()

    def packs_check(self):
        """Queue missing data bundles of the chosen games (packs.py) – at start and after a
        game switch. Without internet: then shows as an error ("Try again")."""
        from cards import packs
        for key in packs.needed(self.settings):
            if key not in self.packs_missing:   # the server has no such pack yet: asked once per session is enough
                self.enqueue("pack", key, name=tr(packs.PACKS[key]["name"]), label="PKG")
        if self._own_db_missing(games.current().key) and not carddb.exists():   # Lorcana: from the source itself
            self.enqueue("carddb", "db", name=tr(f"{games.current().name}: card data"))
        if getattr(self, "_packs_checked", False):
            return
        self._packs_checked = True   # once per start: does the server have newer versions (e.g. price corrections)?
        keys = [k for k in packs.PACKS if packs.installed(k) and not packs.bundled(k)]
        if not keys:
            return

        def check():
            entries = packs.manifest()
            return [k for k in keys if packs.outdated(k, entries.get(k))]

        def done(res, err):
            for key in res or []:
                log.info("Data pack %s: newer version on the server", key)
                self.enqueue("pack", key, name=tr(packs.PACKS[key]["name"]), label="PKG")
        from ui.librarycore import run_async
        run_async(self, check, done)

    def game_jobs(self):
        """Daily jobs of the open game (at start and after a game switch – per game at most once
        per program start, otherwise "Prices on every start" reloaded everything after each switch). Prices/price
        history come from MTGJSON for Magic – other games have no price history (yet): nothing of that there."""
        key = games.current().key
        done = self.__dict__.setdefault("_game_jobs_done", set())
        if key in done:
            return
        done.add(key)
        # Prices fresh (last successful update < 4 h): don't reload – not even in "on every start" mode
        # (the price lists only change once a day anyway; otherwise every game switch reloaded everything)
        fresh = time.time() - float(self.settings.get(f"price_ok_{key}") or 0) < 4 * 3600
        if games.current().price_source == "daily":   # only the daily prices (Cardmarket guide + TCGplayer, our server)
            mode = orbit.price_mode(self.settings)
            # without a card database (Lorcana before its first build) there's nothing to price – and the price job
            # opening it used to leave an empty file behind (the 0.9.2.54 switch error)
            if games.current().update_prices is not None and mode in ("start", "daily") and not fresh \
                    and carddb.exists():
                day_key = f"last_price_day_{key}"
                # at most once a day per game, "on every start" too: Cardmarket's price files are daily files
                # (netpolite) – a second start on the same day changes nothing
                if self.settings.get(day_key) != time.strftime("%Y-%m-%d"):
                    self.enqueue("prices", "all", label="€", name=tr("Prices (all cards)"))
                    self.settings[day_key] = time.strftime("%Y-%m-%d")
                    self.settings_changed()
            return
        if carddb.exists() and not carddb.has_flavor_names():
            # older state without special names ("The Imperial City of Archades" = Wall of Omens): reload once
            log.info("Card database without special names – updating")
            self.enqueue("carddb", "db")
        mode = orbit.price_mode(self.settings)
        due = not fresh and (mode == "start" or (mode == "daily"
                                                 and self.settings["last_price_day"] != time.strftime("%Y-%m-%d")))
        if due:
            self.update_all()  # also extends the price history
        max_age = {"start": 0, "weekly": 7 * 24 * 3600}.get(self.settings["catalog_update"], float("inf"))
        self.load_catalog(max_age)
        if self.settings["price_history"] and not due and orbit.prices_on(self.settings):  # price history: once a day
            st = pricehist.status()
            if not st:
                self.enqueue("pricehist", "ph", label="€", name=tr("Price history"))
            elif st["updated"] < pricehist.today():
                self.enqueue("pricehist", "ph", label="€", name=tr("Price history (today)"), daily=True)

    def on_loaded(self, cards, matcher):
        self.cards = cards
        self.overlay.card_by_id = {c["id"]: c for c in cards}
        self.session.reprice(cards)
        self.reprice_collection()
        old, self.recognizer.matcher = self.recognizer.matcher, matcher
        self.update_fingerprints(cards)
        if old is not None:  # release the old index's search threads once no search runs on it any more
            QtCore.QTimer.singleShot(5000, old.close)
        if not fingerprint.available() and carddb.exists():   # no SCAN° Engine: a quiet line, no endless loading
            self.recognizer.status = tr("SCAN° Engine missing – recognising by collector number only") \
                if games.current().footer_parse is not None else \
                tr("SCAN° Engine missing – reading the card's text instead (slower, asks more often). Reinstalling "
                   "Bent°Corner brings it back.")
        elif cards:
            self.recognizer.status = tr(f"{len(cards)} cards ready. Hold a card in the frame.")
        elif fingerprint.global_path() is not None and fingerprint.available():
            self.recognizer.status = tr("Hold a card in the frame – SCAN° recognizes all cards.")
        elif self._carddb_pending() and not carddb.exists():   # being built right now (Lorcana after the switch)
            self.recognizer.status = tr("Loading card data …")
        elif carddb.exists() and games.current().footer_parse is not None:
            # no index of all cards, but the card database: the scanner reads the card's line (aiscan._footer_only)
            self.recognizer.status = tr("All set – hold a card up to the camera.")
        else:
            # the game's data is missing (still): loading goes through the games bar – no more set download
            self.recognizer.status = tr("This game's data is still missing – load it via the game button at the top left.")

    # --- Session: save, continue, new ---
    def save_session(self):
        if getattr(self, "restored", False):
            return
        s = self.session
        d = s.to_dict()
        if d["stats"]["cards"] or any(d["info"][k] != v for k, v in INFO_DEFAULTS.items()) or d["ended"]:
            try:
                sessions.save(d)
            except OSError:
                log.exception("Session could not be saved")
        self.sync_collection(d)
        self.saved_rev = s.rev
        if self.overlay.hit_mode == "all":
            self.update_all_time_hit()

    def ask_continue_session(self):
        st = self.snap["stats"]
        if not st["cards"]:
            return
        started = time.strftime("%d.%m.%Y %H:%M", time.localtime(self.session.started))
        answer = qdialogs.ask(tr("Last log"),
                              tr(f"The log from {started} is still open ({st['packs']} packs, {eur(st['total'])})."),
                              [("new", tr("Start new log"), ""), ("cont", tr("Continue"), "active")])
        if answer != "cont":
            self.new_session(ask=False)

    def new_session(self, ask=True):
        """End the current session and start a new one. With cards a dialog asks: into the collection? save?
        -> False if cancelled."""
        s = self.session
        st = s.to_dict()["stats"]
        to_coll, keep = False, True
        if st["cards"]:
            from scanner import core
            res = end_session_dialog(st, self.settings["collection_auto"], core.trade_end_text(s.info, s.packs))
            if res is None:
                return False
            to_coll, keep, as_deck, as_list = res
            self.end_trade_scan()   # trade scan: book the "giving away" cards (only after confirming)
            if as_deck:
                self.deck_from_session(s.to_dict(), ask_open=False)
            if as_list:
                self.session_to_list(d=s.to_dict())
        s.ended = time.time()
        s.to_collection = to_coll
        s.rev += 1
        d = s.to_dict()
        self.save_session()   # "don't keep" = into the trash (60 days), never just gone – the logs are the source
        if st["cards"]:
            if to_coll:
                self.collection.sync_session(d)
            else:
                self.collection.remove_session(s.id)
            self.save_collection()
        if not keep:
            sessions.flush()
            sessions.hide(s.id, kept=to_coll)
            self.fill_trash()
        self.session = self.blank_session({"info": {"pack_type": s.info.get("pack_type") or packtypes.DEFAULT}},
                                          cards=self.cards)
        self.session.default_lang = self.settings['card_lang']
        self.recognizer.session = self.session
        self.new_overlay()
        self.last_rev = -1
        self.load_info_fields()
        self.pack_sel = None
        return True

    def end_session_now(self, name=""):
        """The scan tile's "End scan" (Oliver's review .101 c2): ends right away, no question – the cards go into the
        library as set in Settings (collection_auto), the log keeps them; an empty name becomes name ("Scan N").
        -> True when "Undo" can take it back (not after a trade scan: its giving-away booking stays)."""
        s = self.session
        st = s.to_dict()["stats"]
        if not st["cards"] and not s.active:
            return False
        if not st["cards"]:   # nothing scanned: no empty log in Logs (Oliver 2026-10-30) – the scan starts afresh
            if sessions.exists(s.id):   # written earlier for its info (name, price paid)
                sessions.delete(s.id)
            self._ended = None
            self._fresh_session(s)
            return False
        to_coll = bool(self.settings["collection_auto"])
        undoable = not any(e.get("out") for p in s.packs for e in p["cards"])
        if st["cards"]:
            self.end_trade_scan()
        if name and not (s.info.get("title") or "").strip():
            s.set_info(title=name)
        s.ended = time.time()
        s.to_collection = to_coll
        s.rev += 1
        d = s.to_dict()
        self.save_session()
        if st["cards"]:
            if to_coll:
                self.collection.sync_session(d)
            else:
                self.collection.remove_session(s.id)
            self.save_collection()
        self._ended = s if undoable and st["cards"] else None
        self._fresh_session(s)
        return self._ended is not None

    def _fresh_session(self, old):
        """After "End scan": a new, empty log of the same pack type takes over."""
        self.session = self.blank_session({"info": {"pack_type": old.info.get("pack_type") or packtypes.DEFAULT}},
                                          cards=self.cards)
        self.session.default_lang = self.settings['card_lang']
        self.recognizer.session = self.session
        self.new_overlay()
        self.last_rev = -1
        self.load_info_fields()
        self.pack_sel = None

    def undo_end_session(self):
        """"Undo" after "End scan": the ended log runs again, its cards leave the library again – only while the new
        log has no card yet. -> True when done."""
        old = getattr(self, "_ended", None)
        self._ended = None
        if old is None or self.session.to_dict()["stats"]["cards"]:
            return False
        if old.to_collection:
            self.collection.remove_session(old.id)
            self.save_collection()
        old.ended, old.to_collection = None, None
        old.rev += 1
        self.session = old
        self.recognizer.session = old
        self.save_session()
        self.new_overlay()
        self.last_rev = -1
        self.load_info_fields()
        self.pack_sel = None
        return True

    # --- Deck from scanned cards ---
    def deck_from_session(self, d, packs=None, ask_open=True):
        """New deck from the cards of a session (or of single packs, packs = indices)."""
        chosen = [p for i, p in enumerate(d["packs"]) if packs is None or i in packs]
        cards = [e for p in chosen for e in p["cards"]]
        if not cards:
            return None
        info = d["info"]
        date = time.strftime("%d.%m.%Y", time.localtime(d.get("started") or time.time()))
        name = " · ".join(x for x in (info.get("title") or info.get("product"), date) if x)
        fmt = "commander" if chosen and all(p.get("type") == "commander" for p in chosen) else "casual"
        deck = decks.new_deck(name or tr("Deck from log"), fmt)
        for e in cards:
            decks.add_card(deck, scryfall_id(e["id"]), 1)
        page = getattr(self, "deck_page", None)
        if page is not None:
            page.decks.append(deck)
            page.save()
        else:
            decks.save(decks.load() + [deck])
        if ask_open:
            if qdialogs.ask(tr("Deck created"), tr(f"Deck “{deck['name']}” with {len(cards)} cards created."),
                            [("later", tr("Later"), ""), ("open", tr("Open now"), "active")]) == "open":
                self.stream.show_page("decks", back=True)
                self.deck_page.open_deck(deck)
        return deck

    def new_overlay(self):
        """Fresh overlay for a new session; settings like hit mode/card back stay."""
        old = self.overlay
        self.overlay = Overlay(self.settings)
        for key in ("card_by_id", "hit_mode", "all_time_hit", "show_back", "details"):
            setattr(self.overlay, key, getattr(old, key))

    # --- Stream info (left side in the stream) ---
    def load_info_fields(self, reload_panel=True):
        """Refresh the summary in the stream tab and (after a session switch) the info window in the stream."""
        info = self.session.info
        parts = [info.get("title") or tr("no title"),
                 Overlay.sets_text(info) or tr("no sets"),
                 tr(f"{info.get('packs_planned') or '–'} packs planned"),
                 tr(f"Spent {eur(info['paid'])}") if info.get("paid") else tr("Spent –")]
        self.info_summary.setText(" · ".join(parts))

    # --- Statistics ---
    def build_stats_page(self):
        self.stats_page = statsview.StatsPage(fmt=currency.fmt, settings=self.settings, on_save=self.settings_changed,
                                              price_now=self.prices_now, ctrl=self)
        self._stats_timer = QtCore.QTimer(self, singleShot=True, interval=800, timeout=self.refresh_stats)

    def build_sessions_page(self):
        """Sessions: table, edit + packs, on the right the detail view of a clicked card or "Edit
        card" – all data or logic (shown by qsessions)."""
        self.sess_rows, self.sess_sel = [], None  # table: [{"sid", "cells": [{"text", "color", "tip"}]}], selection
        self.sess_hidden = self._sess_columns()  # hidden columns
        self.sess_packs, self.sess_open, self.sess_cur = [], {}, None  # pack list, expanded {pi: bool}, (pi, ci)
        self.sess_summary = ""
        self.sess_lib = {"text": tr("Add to library"), "tip": "", "enabled": False}
        # "Edit session": draft as data (shown as a form by qsessions)
        self.sess_draft = {"started": time.time(), "type": packtypes.DEFAULT, "mixed": False, "title": "",
                           "paid": 0.0, "notes": "", "tags": [], "dirty": False}
        self._sess_filling = False
        # right: detail view of a card (like in the Library, with comparison), appears when clicked
        self.sess_host = DetailHost(self, self, "sessions", on_close=self.sess_close_card, width_key="sess_card_w")
        self.sess_card, self.sess_cmp = self.sess_host.panel, self.sess_host.compare
        self.sess_edit = EditPage(self, CardPanel)

    SESS_REQUIRED = {0}  # the date always stays

    def _sess_columns(self):
        """Hidden columns of the Sessions table. Formerly saved as the state of a Qt header
        (settings["sess_columns"]) – take it over once."""
        st = self.settings.get("sess_hidden")
        if isinstance(st, list):
            return {int(i) for i in st if 0 <= int(i) < len(SESS_COLUMNS)} - self.SESS_REQUIRED
        hidden = _old_header_hidden(self.settings.get("sess_columns"), len(SESS_COLUMNS))
        self.settings["sess_hidden"] = sorted(hidden - self.SESS_REQUIRED)
        return hidden - self.SESS_REQUIRED

    def sess_set_column(self, i, shown):
        if i in self.SESS_REQUIRED or not 0 <= i < len(SESS_COLUMNS):
            return
        (self.sess_hidden.discard if shown else self.sess_hidden.add)(i)
        self.settings["sess_hidden"] = sorted(self.sess_hidden)
        self.settings_changed()
        self.sess_changed.emit()

    def sess_select(self, sid):
        if sid != self.sess_sel:
            self.sess_sel = sid
            self.show_session_detail()

    def sess_set(self, **fields):
        """Change field(s) in the "Edit session" draft (only saved with "Save changes")."""
        self.sess_draft.update(fields)
        self.sess_mark_dirty()

    def sess_mark_dirty(self):
        if self._sess_filling:
            return
        self.sess_draft["dirty"] = True
        qstate._changed()

    def sess_clean(self):
        self.sess_draft["dirty"] = False
        qstate._changed()

    def _sess_pack(self, pi):
        return next((p for p in self.sess_packs if p["pi"] == pi), None)

    def _sess_entry(self, pi, ci):
        p = self._sess_pack(pi)
        return p["cards"][ci]["entry"] if p is not None and 0 <= ci < len(p["cards"]) else None

    def pack_clicked(self, pi, ci, col):
        """Click in the pack list: ci None = pack row (column 1 = choose type), otherwise card = detail view."""
        self.sess_cur = (pi, ci)
        sid = self.selected_session_id()
        if ci is None:  # pack row: click on the type = choose type
            pk = self._sess_pack(pi)
            if col == 1 and sid and pk is not None:
                m = qmenu.Menu()
                cur = pk["typeKey"]
                for t in packtypes.types(self.settings):
                    act = m.addAction(tr(t["name"]) + ("" if t["counts"] else tr("  (doesn't count as a pack)")))
                    act.setCheckable(True)
                    act.setChecked(t["key"] == cur)
                    act.triggered.connect(lambda _=False, key=t["key"]: QtCore.QTimer.singleShot(
                        0, lambda: self.stats_apply(sid, lambda s: s.set_pack_type(key, pi))))
                m.exec(QtGui.QCursor.pos())
            return
        entry = self._sess_entry(pi, ci)
        if entry:
            self.sess_show_card(entry)

    def sess_show_card(self, entry):
        if self.sess_edit.isVisible():
            self.sess_edit.close_page(show_detail=False)
        self.sess_host.open_detail(self.sess_host.row_for_entry(entry))

    def sess_close_card(self):
        self.sess_host.hide_detail()

    def session_to_deck(self):
        sid = self.selected_session_id()
        if not sid:
            return
        packs = None
        if self.sess_cur is not None and self.sess_cur[1] is None:
            packs = {self.sess_cur[0]}  # only the selected pack
        self.deck_from_session(self.session_obj(sid).to_dict(), packs)

    def prices_now(self, ids):
        """Today's prices {Scryfall ID: (eur, eur_foil)}: card database, more current from the loaded sets."""
        out = {}
        if carddb.exists():
            try:
                out.update({k: (r["eur"], r["eur_foil"]) for k, r in carddb.cards_by_ids(ids).items()})
            except Exception:
                log.exception("Prices from the card database")
        for c in self.cards:
            sid = scryfall_id(c["id"])
            if sid in ids:
                out[sid] = (c.get("eur"), c.get("eur_foil"))
        return out

    def save_session_edit(self):
        sid = self.selected_session_id()
        if not sid:
            return
        dr = self.sess_draft
        ts = float(dr["started"])
        ptype = "_mixed" if dr["mixed"] else dr["type"]
        title, paid, notes = dr["title"].strip(), round(float(dr["paid"]), 2), dr["notes"].strip()
        tags = list(dr["tags"])

        def apply(sess):
            sess.started = ts
            sess.info.update(title=title, paid=paid, notes=notes, tags=tags)
            if ptype != "_mixed":  # leaving "mixed" = every pack keeps its type
                for p in range(len(sess.packs)):
                    sess.set_pack_type(ptype, p)
                sess.info["pack_type"] = ptype
            sess.rev += 1
        self.stats_apply(sid, apply)
        self.load_info_fields()
        self.sess_clean()

    def refresh_stats(self):
        self.save_session()
        # empty sessions (also the running one, as long as it has no card yet) don't appear here
        all_s = [s for s in sessions.load_all()
                 if s["stats"]["cards"] or (sessions.is_manual(s) and (s.get("packs") or [{}])[0].get("cards"))]
        self.stats_sessions = all_s
        keep = self.selected_session_id() or self.session.id
        rows = []
        this_year = time.localtime().tm_year
        # a log without its own name is called "Scan 1", "Scan 2" … – counted by start, oldest first (only the
        # scanned logs: imports and the days' changes by hand have their own names)
        scan_no = {x["id"]: i + 1 for i, x in enumerate(sorted(
            (x for x in all_s if not sessions.is_manual(x) and not sessions.is_import(x)), key=lambda x: x["started"]))}
        for s in all_s:
            st, info = s["stats"], s["info"]
            # short, so the column never cuts it: "18.10. 13:55" this year, "18.10.25 13:55" before
            when = time.localtime(s["started"])
            date = time.strftime("%d.%m. %H:%M" if when.tm_year == this_year else "%d.%m.%y %H:%M", when)
            if sessions.is_manual(s):   # the day's changes by hand: "By hand · 27.10.", net count signed
                rows.append(self._manual_row(s, date))
                continue
            title = " · ".join(x for x in (info.get("title"), info.get("product")) if x) or (
                f"Scan {scan_no[s['id']]}" if s["id"] in scan_no else "–")   # the same in German
            if s["id"] == self.session.id:
                title = tr("● running · ") + title
            profit = tr("–") if st["profit"] is None else ("+" if st["profit"] >= 0 else "−") + eur(abs(st["profit"]))
            counts = {}
            for pk in s.get("packs", []):
                if pk.get("cards"):
                    k = pk.get("type") or packtypes.DEFAULT
                    counts[k] = counts.get(k, 0) + 1
            types = ", ".join(tr(packtypes.name(self.settings, k)) + (f" ×{n}" if n > 1 else "")
                              for k, n in counts.items()) or "–"
            if kind_of(info) == "cards":   # scanning cards: no packs (and no pack types)
                types = tr("Scan cards")
            tags = ", ".join(info.get("tags") or []) or "–"
            vals = (date, title, types, tags, str(st["packs"]) if has_packs(info) else "–", str(st["cards"]), eur(st["total"]),
                    eur(st["paid"]) if st.get("paid") else "–", profit)
            cells = [{"text": x, "color": "", "tip": ""} for x in vals]
            cells[2]["tip"], cells[3]["tip"] = types, tags
            if st["profit"] is not None:
                cells[8]["color"] = "#3fbf6f" if st["profit"] >= 0 else "#e05555"
            rows.append({"sid": s["id"], "cells": cells, "imp": sessions.is_import(s), "singles": sessions.is_singles(s),
                         "kind": kind_of(info)})
        self.sess_rows = rows
        # nothing chosen (yet): the top entry – the Log opens split right away (review .90)
        self.sess_sel = keep if any(r["sid"] == keep for r in rows) else (rows[0]["sid"] if rows else None)

        if self.page_shown("stats"):
            self.stats_page.set_sessions([x for x in all_s if sessions.counts_in_stats(x)])
        self.show_session_detail()

    def selected_session_id(self):
        return self.sess_sel

    def session_obj(self, sid):
        """Load the running session directly, saved ones for editing."""
        return self.session if sid == self.session.id else Session(self.cards, sessions.load(sid))

    def share_session(self):
        sid = self.selected_session_id()
        if not sid:
            qdialogs.info(tr("Share"), tr("Please pick a log on the left first."))
            return
        self.go_export("session_share", sid=sid)

    def _manual_title(self, d):
        mig = (d.get("info") or {}).get("migrated")
        if mig:   # the one-off migration log (logs as the library's source)
            from system import i18n
            day = time.strftime("%d.%m.%Y", time.localtime(mig)) if i18n.LANG == "de" else \
                time.strftime("%d %b %Y", time.localtime(mig)).lstrip("0")
            return tr("By hand") + " (" + tr(f"everything until {day} combined") + ")"
        return tr("By hand") + " · " + time.strftime("%d.%m.", time.localtime(d["started"]))

    def _manual_row(self, s, date):
        st = s["stats"]
        n = int(st.get("cards") or 0)
        vals = (date, self._manual_title(s), tr("By hand"), "–", "–", (f"+{n}" if n > 0 else f"−{-n}" if n < 0 else "0"),
                ("" if st["total"] >= 0 else "−") + eur(abs(st["total"])), "–", "–")
        cells = [{"text": x, "color": "", "tip": ""} for x in vals]
        cells[2]["tip"] = tr("Changes by hand outside the scanner – each line can be undone on its own")
        return {"sid": s["id"], "cells": cells, "imp": False, "singles": False, "kind": "manual"}

    def _manual_detail(self, d):
        """A day of changes by hand: summary + one plain list, each line +n/−n with its own undo (no packs)."""
        st = d["stats"]
        lines = d["packs"][0]["cards"] if d.get("packs") else []
        first = time.strftime("%H:%M", time.localtime(d["started"]))
        last = time.strftime("%H:%M", time.localtime(d.get("ended") or d["started"]))
        plus = sum(int(e.get("delta") or 0) for e in lines if int(e.get("delta") or 0) > 0)
        minus = -sum(int(e.get("delta") or 0) for e in lines if int(e.get("delta") or 0) < 0)
        self.sess_summary = "<br>".join([
            f"<span style='color:#eef1ff; font-size:14px; font-weight:700'>{self._manual_title(d)}</span>"
            f"&nbsp;&nbsp;<span style='color:#6c7390'>{first} – {last}</span>",
            tr(f"{plus} added · {minus} taken out by hand – already in your collection"),
            tr(f"Value <b style='color:#f2f2f2'>{eur(st['total'])}</b>"),
        ])
        cards = []
        for ci, e in enumerate(lines):
            n = int(e.get("delta") or 0)
            sign = f"+{n}" if n > 0 else f"−{-n}" if n < 0 else "✎"
            cards.append({"ci": ci, "name": f"{sign}  " + shown_name(e, self.settings) +
                          (f"  · {tr(finish_label(e))}" if finish_label(e) else ""),
                          "set": f"{e.get('set', '')} #{e.get('number', '')}",
                          "price": tr("–") if e.get("price") is None else eur(e["price"]),
                          "note": edit_note(e.get("edit")) or e.get("why") or "",
                          "fin": finish_short(e), "entry": e, "manual": True, "added": e.get("added")})
        self.sess_packs.append({"pi": 0, "name": tr(f"{len(lines)} changes"), "type": "", "typeKey": "",
                                "typeColor": "", "price": eur(st["total"]), "cards": cards, "plain": True, "manual": True})
        self.sess_changed.emit()

    def sess_manual_undo(self, ci):
        """Undo one line of a by-hand day: when the card moved on since, say why and ask first."""
        sid = self.selected_session_id()
        try:
            line = sessions.load(sid)["packs"][0]["cards"][ci]
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            return
        res, why = self.manual_undo(sid, line.get("added"))
        if res == "moved":
            if not qdialogs.question(tr("Undo anyway?"), why + "\n\n" + tr("Take it back anyway?")):
                return
            res, why = self.manual_undo(sid, line.get("added"), force=True)
        if res == "gone":
            self.stream_toast(why)
        elif res == "ok":
            self.stream_toast(tr("Change undone"))
        self.refresh_stats()

    def show_session_detail(self):
        sid = self.selected_session_id()
        if sid != getattr(self, "_sess_shown", None):  # other session: forget expanded items and selection
            self._sess_shown, self.sess_open, self.sess_cur = sid, {}, None
        self.sess_packs = []
        self.sess_foreign = []
        self.sess_update_lib_btn(sid)
        edit = getattr(self, "sess_edit", None)
        if edit is not None and not edit.isHidden() and (edit.target or (None,))[0] != sid:
            edit.close_page(show_detail=False)  # another session selected
        if not sid:
            self.sess_summary = (f"<div style='color:#8a91a8; font-size:13px'>"
                                 f"{tr("Pick a log on the left – then you can edit it and correct its cards here.")}</div>")
            self.sess_changed.emit()
            return
        raw = sessions.load(sid) if sid != self.session.id else None
        if raw is not None and sessions.is_manual(raw):
            self.sess_draft = {"sid": sid, "kind": "manual", "started": float(raw["started"]), "mixed": False,
                               "type": "", "title": "", "paid": 0.0, "notes": "", "tags": [], "dirty": False}
            qstate._changed()
            self._manual_detail(raw)
            return
        d = self.session_obj(sid).to_dict()
        st, info = d["stats"], d["info"]
        self.sess_foreign = list(info.get("foreign") or [])   # mixed trade: cards of other games (greyed out)
        self.sess_ticket = info.get("ticket") or ""
        kinds = {p.get("type") or info.get("pack_type") or packtypes.DEFAULT for p in d.get("packs") or []}
        self.sess_draft = {"sid": sid, "started": float(d["started"]),
                           # packs of different types: "mixed" (stays so as long as nothing is chosen)
                           "mixed": len(kinds) > 1,
                           "type": next(iter(kinds)) if len(kinds) == 1
                           else (info.get("pack_type") or packtypes.DEFAULT),
                           "title": info.get("title") or "", "paid": float(info.get("paid") or 0),
                           "notes": info.get("notes") or "", "tags": list(info.get("tags") or []), "dirty": False,
                           "kind": kind_of(info)}
        qstate._changed()
        counts = st["counts"]
        types = {}
        for pk in d["packs"]:
            if pk["cards"]:
                k = pk.get("type") or packtypes.DEFAULT
                types[k] = types.get(k, 0) + 1
        started = time.strftime("%d.%m.%Y %H:%M", time.localtime(d["started"]))
        ended = time.strftime("%H:%M", time.localtime(d["ended"])) if d.get("ended") else tr("running")
        head = " · ".join(x for x in (info.get("title"), info.get("product")) if x) or tr("Log")
        lines = [f"<span style='color:#eef1ff; font-size:14px; font-weight:700'>{head}</span>"
                 f"&nbsp;&nbsp;<span style='color:#6c7390'>{started} – {ended}</span>"]
        if has_packs(info) or kind_of(info) == "singles":
            lines.append(tr("Types: ") + (", ".join(f"<b>{tr(packtypes.name(self.settings, k))}</b>" + (f" ×{n}" if n > 1 else "")
                                                  for k, n in types.items()) or "–"))
        if info.get("tags"):
            lines.append(tr("Tags: ") + " ".join(f"<span style='background:#4a3a1f; color:#ffe9c2'>&nbsp;{t}&nbsp;</span>"
                                                  for t in info["tags"]))
        money = tr(f"Value <b style='color:#f2f2f2'>{eur(st['total'])}</b>")   # greyscale, no accent
        if st.get("paid"):
            pr = st["profit"]
            money += tr(f" · spent {eur(st['paid'])} · balance ") + \
                f"<b style='color:{'#46d17a' if pr >= 0 else '#ff4d5e'}'>{'+' if pr >= 0 else '−'}{eur(abs(pr))}</b>"
        lines.append(money)
        top, second, foil = (tr(x) for x in games.current().counter_labels())
        lines.append((tr(f"{st['packs']} packs · {st['cards']} cards") if has_packs(info) else tr(f"{st['cards']} cards")) +
                     f" · {top} {counts['mythic']} · {second} {counts['rare']} · {foil} {counts['foil']}")
        if st["biggest_hit"]:
            lines.append(tr(f"Biggest hit: <b>{st['biggest_hit']['name']}</b> {eur(st['biggest_hit']['price'])}"))
        if info.get("notes"):
            lines.append(f"<span style='color:#8a91a8'>{info['notes']}</span>")
        self.sess_summary = "<br>".join(lines)
        for pi, pack in enumerate(d["packs"]):
            if not pack["cards"] and pi != len(d["packs"]) - 1:
                continue
            opened = time.strftime("%H:%M", time.localtime(pack["opened"]))
            key = pack.get("type") or packtypes.DEFAULT
            if self.settings.get("printed_names", True):   # the names in card language: one database read for all
                carddb.printed_names_for([(e.get("set") or "", e.get("number") or "", e.get("lang") or "en") for e in pack["cards"]])
            cards = [{"ci": ci, "name": shown_name(e, self.settings) + (f"  · {tr(finish_label(e))}" if finish_label(e) else ""),
                      "set": f"{e['set']} #{e['number']}", "price": tr("–") if e["price"] is None else eur(e["price"]),
                      "fin": finish_short(e), "note": edit_note(e.get("edits")), "entry": e}
                     for ci, e in enumerate(pack["cards"])]
            if not has_packs(info) and kind_of(info) != "singles":
                self.sess_packs.append({"pi": pi, "name": tr(f"{len(pack['cards'])} cards"), "type": "", "typeKey": key,
                                        "typeColor": "", "price": eur(pack_total(pack)), "cards": cards, "plain": True})
                continue
            self.sess_packs.append({"pi": pi, "name": tr(f"Pack {pi + 1} · {opened} · {len(pack['cards'])} cards"),
                                    "type": tr(packtypes.name(self.settings, key)), "typeKey": key,
                                    "typeColor": "#e2e2e2" if packtypes.counts(self.settings, key) else "#8e8e8e",   # counts: bright, not: quiet
                                    "price": eur(pack_total(pack)), "cards": cards})
        self.sess_changed.emit()

    def tree_target(self, need_card=True):
        sid = self.selected_session_id()
        if self.sess_cur is None or not sid:
            return None
        pi, ci = self.sess_cur
        if need_card and ci is None:
            return None
        return sid, pi, ci

    def stats_apply(self, sid, fn):
        s = self.session_obj(sid)
        fn(s)
        if s is self.session:
            self.save_session()
        else:   # an older log: written a moment later in the background (sessions.save_later)
            d = s.to_dict()
            sessions.save_later(d)
            self.sync_collection(d)
        self.refresh_stats()

    def stats_edit_card(self):
        t = self.tree_target()
        if not t:
            return
        sid, pi, ci = t
        entry = self.session_obj(sid).to_dict()["packs"][pi]["cards"][ci]
        self.sess_edit.open(sid, pi, ci, entry)

    def sess_row_action(self, pi, ci, action):
        """Hover button on a row of the pack list (like in the scanner: F · ⚙ · ✕). ci None = pack."""
        self.sess_cur = (pi, ci)
        {"foil": self.stats_foil, "gear": self.stats_edit_card, "remove": self.stats_remove_card,
         "pack": self.stats_delete_pack, "plus": self.stats_plus, "merge": self.stats_merge_pack,
         "undo": lambda: self.sess_manual_undo(ci)}[action]()

    def stats_merge_pack(self):
        """Merge a pack with the one before it (e.g. after an accidental "New pack")."""
        t = self.tree_target(need_card=False)
        if t and t[1] > 0:
            self.stats_apply(t[0], lambda s: s.merge_into_previous(t[1]))

    def sess_in_library(self, sid):
        return any((it.get("src") or "").startswith(sid + "/") for it in self.collection.items)

    def sess_update_lib_btn(self, sid):
        running = sid == self.session.id
        manual = bool(sid) and sid.startswith("manual_")
        if manual:
            self.sess_lib = {"text": tr("Add to library"), "enabled": False,
                             "tip": tr("Changes by hand are already in your collection – undo single lines instead")}
            self.sess_changed.emit()
            return
        if running:
            text, tip = tr("Add to library"), tr("Still running – when you end it you'll be asked whether the cards go into your collection")
        elif sid and self.sess_in_library(sid):
            text, tip = tr("Remove from library"), tr("Take this log's cards out of your collection again (the log stays)")
        else:
            text, tip = tr("Add to library"), tr("Add all cards of this log to your collection")
        # "on": the log's cards are in the library – the Logs tab shows it as a switch (review .101)
        self.sess_lib = {"text": text, "tip": tip, "enabled": bool(sid) and not running,
                         "on": bool(sid) and not running and self.sess_in_library(sid)}
        self.sess_changed.emit()

    def sess_toggle_library(self):
        sid = self.selected_session_id()
        if not sid or sid == self.session.id:
            return
        d = sessions.load(sid)
        if self.sess_in_library(sid):
            if not qdialogs.question(tr("Remove from library"),
                                     tr("Remove this log's cards from your collection? The log itself stays.")):
                return
            self.collection.remove_session(sid)
            d["collection"] = False
        else:
            d["collection"] = True
            self.collection.sync_session(d)
        sessions.save(d)
        self.save_collection()
        self.sess_update_lib_btn(sid)

    def stats_plus(self):
        t = self.tree_target()
        if t:
            self.stats_apply(t[0], lambda s: s.duplicate(t[2], t[1]))

    def stats_foil(self):
        t = self.tree_target()
        if t:
            self.stats_apply(t[0], lambda s: s.toggle_foil(t[2], t[1]))

    def _sess_title(self, d):
        info = d.get("info") or {}
        return info.get("title") or time.strftime("%d.%m.%Y", time.localtime(d.get("started") or time.time()))

    def stats_remove_card(self):
        """Take a card out of a session – it goes to the trash, "Undo" right after."""
        t = self.tree_target()
        if not t:
            return
        from system import datastore
        sid, pi, ci = t
        d = self.session_obj(sid).to_dict()
        try:
            entry = d["packs"][pi]["cards"][ci]
        except (IndexError, KeyError):
            return
        name = datastore.trash_put("sesscard", f"{entry.get('name', '?')} · {self._sess_title(d)}",
                                   {"sid": sid, "pi": pi, "ci": ci, "entry": entry})
        self.stats_apply(sid, lambda s: s.undo(ci, pi))
        self.sess_set_undo(name, tr(f"“{entry.get('name', '?')}” removed from the log"))

    def stats_delete_pack(self):
        t = self.tree_target(need_card=False)
        if not t:
            return
        from system import datastore
        sid, pi = t[0], t[1]
        d = self.session_obj(sid).to_dict()
        try:
            pack = d["packs"][pi]
        except (IndexError, KeyError):
            return
        if not qdialogs.question(tr("Delete pack"), tr(f"Delete pack {pi + 1} with all cards?"),
                                 informative=tr("It goes to the trash – “Undo” brings it back.")):
            return
        name = datastore.trash_put("sesspack", f"{tr('Pack')} {pi + 1} · {self._sess_title(d)}",
                                   {"sid": sid, "pi": pi, "pack": pack})
        self.stats_apply(sid, lambda s: s.delete_pack(pi))
        self.sess_set_undo(name, tr(f"Pack {pi + 1} deleted"))

    # "Undo" in the Sessions tab (last deletion, for a few seconds)
    sess_undo = None

    def sess_set_undo(self, trash_name, text):
        self.sess_undo = (trash_name, text, time.time())
        self.sess_changed.emit()

    def sess_do_undo(self):
        from system import datastore
        u, self.sess_undo = self.sess_undo, None
        if u is not None:
            e = datastore.trash_take(u[0])
            if e is not None:
                self.trash_restore(e)
        self.fill_trash()
        self.sess_changed.emit()

    # --- Single-card session (trade, purchase) ---
    def set_session_kind(self, kind, sess=None):
        """kind "cards" (scanning cards: one list), "packs" (opening boosters) or "singles" (single cards:
        trade/purchase – each card individually) -> False if not possible (to "cards"/"singles" with several packs)."""
        sess = sess or self.session
        if not sess.set_kind(kind):
            return False
        cur = sess.packs[-1].get("type") or sess.info.get("pack_type")
        if kind == "singles" and cur not in packtypes.SINGLES:
            sess.set_pack_type("trade")
        elif kind != "singles" and cur in packtypes.SINGLES:
            sess.set_pack_type(packtypes.DEFAULT)
        if sess is self.session and self.page_shown("sessions", "stats"):   # the Sessions page shows the new kind
            self.refresh_stats()
        return True

    def new_singles_session(self):
        """Sessions → "Scan trade / purchase": start a new single-card session and go to the scan window."""
        if self.session.to_dict()["stats"]["cards"] and not self.new_session():
            return
        self.set_session_kind("singles")
        self.stream.show_page("scan")

    # --- Session as a list ---
    def session_to_list(self, sid=None, kind="custom", d=None, toast=True):
        """All cards of a session (exactly those prints) as a new list (default: own list) -> list id."""
        from collection import trade
        d = d or (self.session_obj(sid).to_dict() if sid else None)
        if not d:
            return None
        entries = {}
        for pk in d.get("packs") or []:
            for e in pk.get("cards") or []:
                key = (e.get("name"), (e.get("set") or "").lower(), str(e.get("number") or ""), e.get("lang") or "en",
                       bool(e.get("foil")))
                x = entries.setdefault(key, {"name": e.get("name"), "set": (e.get("set") or "").lower() or None,
                                             "number": e.get("number"), "count": 0, "lang": e.get("lang") or "en",
                                             "foil": bool(e.get("foil")), "uid": None})
                x["count"] += 1
        if not entries:
            return None
        name = self._sess_title(d)
        lid = trade.add_list(kind, name)
        trade.put_entries(kind, lid, list(entries.values()), self.collection)
        if toast:
            self.stream_toast(tr(f"List “{name}” created – Library → Lists"))
        page = getattr(self, "trade_page", None)
        if page is not None and hasattr(page, "lists_changed"):
            page.lists_changed.emit()
        return lid

    def stats_delete_session(self):
        sid = self.selected_session_id()
        if not sid:
            return
        if sid == self.session.id:   # the running session: end it first (otherwise no new one could be started)
            self.stream_toast(tr("End the running log first – then it can be deleted."))
            return
        n = sum(it.get("count", 1) for it in self.collection.items if (it.get("src") or "").startswith(sid + "/"))
        from collection import bookings
        booked = next((b for b in bookings.load() if b.get("session") == sid), None)   # session of a trade
        btns = [("cancel", tr("Cancel"), "")]
        if booked is not None:   # trade: undo it (all as before) or just put the entry away (the trade stays valid)
            btns += [("undo_trade", tr("Undo trade"), "active"), ("keep", tr("To the trash, trade stays"), "")]
            info = tr("“Undo trade”: the cards you gave come back, the ones you got leave – as before the trade.\n“To the trash, trade stays”: the trade stays valid, all cards stay as they are.")
        else:
            btns += [("keep", tr("To the trash, keep cards"), "active"),
                     ("drop", tr("To the trash incl. cards"), "danger")] if n else [("keep", tr("To the trash"), "danger")]
            info = tr(f"{n} cards from it are in your collection.") if n else ""
        clicked = qdialogs.ask(tr("Log to the trash"), tr("Put this log into the trash? It stays there for 60 days."),
                               btns, informative=info)
        if clicked == "undo_trade":
            bookings.cancel(self.collection, booked["id"])
            self.after_booking()
            self.stream_toast(tr("Trade undone"))
            return
        if clicked not in ("keep", "drop"):
            return
        # logs as the library's source: the log is hidden (trash, 60 days), never just deleted – with "keep" it
        # still holds its cards, with "drop" they leave the library (they come back with the log)
        sessions.flush()
        if clicked == "drop":
            self.collection.remove_session(sid)
        sessions.hide(sid, kept=clicked != "drop")
        self.save_collection()
        if sid == self.session.id:
            self.session = self.blank_session(cards=self.cards)
            self.session.default_lang = self.settings['card_lang']
            self.recognizer.session = self.session
            self.new_overlay()
            self.last_rev = -1
            self.load_info_fields()
        self.fill_trash()
        self.refresh_stats()

    def log_unhide(self, sid):
        """A log back out of the trash: it shows again (its cards: with "keep" they never left; with "drop" the log
        is out of the library – put it back with „Add to library“)."""
        sessions.unhide(sid)
        self.refresh_stats()

    def log_for_good(self, sid):
        """A hidden log goes for good (trash emptied, or 60 days over): cards it still holds stay in the library –
        they become lines in the day's „By hand“ log first, so the library stays the sum of its logs."""
        from collection import manual
        try:
            d = sessions.load(sid)
        except (OSError, ValueError):
            return
        if (d.get("hidden") or {}).get("kept") and d.get("collection") is not False:
            held = [it for it in self.collection.items if (it.get("src") or "").startswith(sid + "/")]
            self.collection.detach_session(sid)
            for it in held:
                try:
                    manual.record(dict(it, src=None), int(it.get("count", 1)),
                                  why=tr("from a log deleted for good"))
                except Exception:  # noqa: BLE001
                    log.exception("Log for good: line")
            self.save_collection()
        sessions.delete(sid)

    def logs_purge(self):
        """Hidden longer than 60 days: for good, oldest first."""
        for d in sessions.due_for_good():
            self.log_for_good(d["id"])

    # --- Collection ---
    def currency_changed(self):
        """Display currency changed or rates loaded: redraw everything with prices."""
        self.cur_info.setText(tr(currency.rate_info()))
        self.refresh_collection_info()
        if self.library_win is not None:
            self.library_win.refresh(keep=True)
            self.library_win.detail.refresh_owned()
        if self.page_shown("stats"):
            self.refresh_stats()

    def condition_scale_changed(self):
        """Condition scale switched (Cardmarket ↔ TCGplayer): relabel tiles, detail and scan list."""
        if self.library_win is not None:
            self.library_win.refresh(keep=True)
            self.library_win.detail.refresh_owned()
        self.session.rev += 1

    def refresh_collection_info(self):
        s = self.collection.summary()
        if not s["cards"]:
            self.coll_info.setText(tr("<b>Collection</b>: still empty."))
            return
        langs = " · ".join(f"{lang_short(k)} {v}" for k, v in sorted(s["langs"].items(), key=lambda t: -t[1]))
        self.coll_info.setText(tr(f"<b>Collection</b>: {s['cards']} cards ({s['unique']} different) · value <b>{currency.fmt(s['value'])}</b>") + f"<br>{langs}")

    def open_library(self):
        self.stream.show_page("library")

    def show_list(self, kind, lid, back=False):
        """The Library on one list: the lists column open, the list picked (only its cards). back=True: the page you
        came from gets the way back in the navigation."""
        self.stream.show_page("library", back=back)
        lib = getattr(self, "library_win", None)
        if lib is None:
            return
        if not lib.lists_open:
            lib.show_lists()
        if lib.list_sel != (kind, lid):
            lib.pick_list(kind, lid)
        shell = getattr(self, "shell", None)
        b = shell.backends.get("library") if shell is not None else None
        if b is not None:
            b.changed.emit()

    def save_collection(self):
        if getattr(self, "restored", False):
            return
        try:
            self.collection.save()
        except OSError:
            log.exception("Collection could not be saved")
        if hasattr(self, "coll_info"):  # at start before init_settings
            self.refresh_collection_info()

    def sync_collection(self, d):
        """Add a finished session to the collection (if chosen so when ending; old sessions: yes)."""
        if d.get("ended") and d.get("collection") is not False and self.collection.sync_session(d):
            self._coll_timer.start()

    def sync_all_sessions(self):
        """Add all saved sessions (and the running one) to the collection – the hidden ones (trash) too: a log with
        kept cards still holds them. collection.json lost: rebuilt from all logs (by hand and trades included).
        Then the library must be exactly the sum of its logs (logs_check)."""
        changed = False
        self.logs_purge()   # logs in the trash longer than 60 days: for good (their kept cards become lines)
        logs = sessions.load_all(include_hidden=True)
        for d in logs:
            if d["id"] != self.session.id and d.get("ended") and d.get("collection") is not False:
                changed |= self.collection.sync_session(d)
        if self.collection.is_new and logs:
            from collection import bookings, logsum
            changed |= bool(logsum.repair(self.collection, logs, bookings.load()))
        if changed or self.collection.is_new:
            self.collection.is_new = False
            self.save_collection()
        self.logs_check(logs)

    def logs_check(self, logs=None, why=""):
        """The library is the sum of its logs (docs/SYNC-PLAN.md §3b). The first time per game: what the logs can't
        explain yet (cards from before every change was written down) becomes one log „By hand (everything until …
        combined)“. After that a gap only comes from a path past the logs (undo, an old bug): it becomes lines in
        the day's „By hand“ log – and a warning in the log file. -> lines written."""
        import games
        from collection import bookings, logsum, manual
        logs = logs if logs is not None else sessions.load_all(include_hidden=True)
        for d in logs:   # old "gone" minus lines without a card (0.9.2.102–104) -> the log's "gone" list
            if manual.fold_gone(d):
                manual.save(d)
                log.info("Logs as source: old gone lines folded in %s", d["id"])
        logs = [d for d in logs if d["id"] != self.session.id] + [self.session.to_dict()]
        done = self.settings.setdefault("logs_source", {})
        game = games.current().key
        try:
            book = bookings.load()
            if not done.get(game):
                def card_of(key):
                    sid, _, added = key.partition("/")
                    for d in logs:
                        if d.get("id") == sid:
                            for pk in d.get("packs") or []:
                                for e in pk.get("cards") or []:
                                    if repr(e.get("added", 0)) == added:
                                        return e
                    return None
                mig = logsum.migration(self.collection.items, logs, book, time.time(), card_of)
                n = 0
                if mig is not None:
                    from system import datastore
                    datastore.snapshot("before-logs-migration")
                    manual.hide_gone(self.collection, mig)
                    manual.save(mig)
                    n = len(mig["packs"][0]["cards"])
                    log.info("Logs as source (%s): %d lines into %s", game, n, mig["id"])
                done[game] = 1
                self.settings_changed()
                return n
            gap = logsum.diff(self.collection.items, logs, book)
            if not gap:
                return 0
            n = manual.close_gap(self.collection, logs, book, why or tr("matched to the library"))
            log.warning("Logs as source (%s): %d lines for a gap (%s)", game, n, why or "check")
            self.save_collection()
            return n
        except Exception:  # noqa: BLE001 – never block the start because of it
            log.exception("Logs as source: check")
            return 0

    def heal_prints(self):
        """Before the game's data is loaded: references to prints that left its card database move to the English
        print of the same card (collection.printmove – Yu-Gi-Oh!: the prints from YGOJSON)."""
        try:
            from collection import printmove
            printmove.heal()
        except Exception:  # noqa: BLE001 – never block the start because of it
            log.exception("Moving removed prints")

    def reprice_market_fix(self):
        """Once per bundle version: cards whose marketplace mapping was corrected (tools/fix_pokemon_market.py –
        e.g. Piplup from Shifting Worlds showed the price of its full-art version) get the right price in all sessions
        of the game. (The collection is caught up by reprice_collection anyway.)"""
        fix = (games.current().market_fix() if games.current().market_fix is not None else None) or {}
        sids = set(fix.get("fixed") or {}) | set(fix.get("untrusted") or [])
        key = f"market_fix_{games.current().key}"
        if not sids or self.settings.get(key) == fix.get("pk_build"):
            return
        try:
            rows = carddb.cards_by_ids(sids)
        except Exception:  # noqa: BLE001
            log.exception("Price correction: card database")
            return
        n = 0
        targets = [self.session] + [Session(self.cards, d) for d in sessions.load_all() if d.get("id") != self.session.id]
        for s in targets:
            touched = False
            for pack in s.packs:
                for e in pack["cards"]:
                    r = rows.get(scryfall_id(e["id"]))
                    if r is None or (e.get("eur"), e.get("eur_foil")) == (r["eur"], r["eur_foil"]):
                        continue
                    e["eur"], e["eur_foil"] = r["eur"], r["eur_foil"]
                    e["price"] = price_of(e)
                    touched, n = True, n + 1
            if touched and s is not self.session:
                sessions.save(s.to_dict())
        if n:
            self.save_session()
            log.info("Price correction: %s cards in sessions repriced", n)
            if hasattr(self, "refresh_stats"):
                self.refresh_stats()
        self.settings[key] = fix.get("pk_build")
        self.settings_changed()

    def reprice_collection(self):
        """Collection prices from the card database and (more current) from the loaded sets."""
        prices = {}
        if carddb.exists():
            try:
                rows = carddb.cards_by_ids({scryfall_id(it["id"]) for it in self.collection.items})
                prices.update({k: (r["eur"], r["eur_foil"]) for k, r in rows.items()
                               if r["eur"] is not None or r["eur_foil"] is not None})   # no price: keep the old one
            except Exception:
                log.exception("Prices from the card database")
        for c in self.cards:
            prices[scryfall_id(c["id"])] = (c["eur"], c["eur_foil"])
        if self.collection.reprice(prices):
            if self._coll_timer.isActive():   # a real change is waiting for saving anyway
                self._coll_timer.start()
            else:   # only new prices: save quietly (no undo step)
                from system import undo
                with undo.quiet():
                    self.save_collection()

    def collection_add(self, card, lang, foil, count, finish=None, edition=None, cond=None):
        """Add by hand (library, detail, compare …) – also a line in the day's "changed by hand" session."""
        it = self.collection.add(card, lang, foil, count, finish=finish, edition=edition, cond=cond)
        self._manual(it, count)
        self._coll_timer.start()

    def _manual(self, item, delta):
        from collection import manual
        try:
            manual.record(item, delta)
        except Exception:  # noqa: BLE001 – the change itself is done; only the history line is missing
            log.exception("Change by hand not recorded")

    def manual_undo(self, sid, added, force=False):
        """Take back one line of a "changed by hand" session -> ("ok"|"moved"|"gone", why)."""
        from collection import manual
        res = manual.undo(self.collection, sid, added, force)
        if res[0] == "ok":
            self._coll_timer.start()
        return res

    def collection_count(self, item, n):
        """Change the number of copies by hand (0 = take out) – also a line in the day's "changed by hand" session."""
        if n <= 0:
            from system import datastore
            datastore.trash_put("cards", item.get("name") or "?", {"items": [dict(item)]})  # 30 days in the trash
        before = dict(self.collection.get(item["uid"]) or item)
        self.collection.set_count(item["uid"], n)
        self._manual(before, max(0, int(n)) - int(before.get("count", 1)))
        self._coll_timer.start()

    def collection_change(self, item, lang=None, foil=None, finish=None, edition=None, cond=None):
        """Change language/foil/finish/edition/condition of a copy; scanned cards also in their session.
        cond: {"cond": …, "grade_by", "grade", "cond_note"} (conditions.py)."""
        from cards import finishes
        fields = {}
        if cond is not None:
            from cards import conditions
            tmp = dict(item)
            conditions.apply(tmp, cond.get("cond"), cond.get("grade_by"), cond.get("grade"), cond.get("cond_note"))
            fields.update({k: tmp.get(k) for k in ("cond", "grade_by", "grade", "cond_note")})
        if lang is not None:
            fields["lang"] = lang
        if finish is not None:
            tmp = dict(item)
            if finishes.apply(tmp, finish):
                fields.update(finish=tmp["finish"], foil=tmp["foil"])
        elif foil is not None:
            fields["foil"] = bool(foil)
        if edition is not None:
            fields["edition"] = edition or None
        changes = {k: [item.get(k), v] for k, v in fields.items() if item.get(k) != v}
        self.collection.update(item["uid"], **fields)
        self._coll_timer.start()
        src = item.get("src")
        if not src:   # no log of its own: a line in the day's „By hand“ log
            if changes:
                from collection import manual
                try:
                    manual.record_edit(dict(item, **fields), changes)
                except Exception:  # noqa: BLE001
                    log.exception("Change not recorded")
            return
        sid, _, added = src.partition("/")
        try:
            added = float(added)
        except ValueError:
            return
        if sid == self.session.id:
            self.session.set_card(added, lang, foil, finish, edition, cond)  # saved via the tick
            self.session.note_edit(added, changes)
        elif (sessions.SESSIONS / f"{sid}.json").exists():
            s = Session(self.cards, sessions.load(sid))
            if s.set_card(added, lang, foil, finish, edition, cond):
                s.note_edit(added, changes)
                sessions.save(s.to_dict())

    def fetch_lang_images(self):
        """Cards in another language: load the language version's image in the background (the overlay shows it)."""
        snap = self.snap
        for e in snap["pack"] + ([snap["current"]] if snap["current"] else []):
            lang = e.get("lang") or "en"
            if lang == "en" or e["img"] != e.get("img_en"):
                continue
            key = (self.session.id, e.get("added"), lang)
            if key in self._lang_tried:
                continue
            self._lang_tried.add(key)
            session, entry = self.session, dict(e)
            run_async(self, lambda entry=entry, lang=lang: library.fetch_lang_print(entry, lang),
                      lambda res, err, entry=entry, lang=lang, session=session:
                      self.on_lang_image(session, entry, lang, res, err))

    def on_lang_image(self, session, entry, lang, img, err):
        if err or not img:
            log.info("Language version %s %s #%s: %s", lang, entry["set"], entry["number"], err or "no image")
            return
        session.set_image(entry.get("added"), lang, img)

    def download_collection_images(self, progress):
        """Fetch images of all cards in the collection (and their language versions) to disk."""
        from ui.librarycore import _throttle
        items = list(self.collection.items)
        if self.settings["offline_skip_basics"]:
            items = [it for it in items if not is_basic_land(it.get("name"))]
        n = 0
        for i, it in enumerate(items, 1):
            progress("Bilder der Sammlung laden …", i, len(items))
            path = BASE / it["img"]
            if not path.exists():
                face = 1 if it["img"].endswith("_1.jpg") else 0
                url = library.image_url(it["set"], it["number"], "en", "normal", face)
                try:
                    _throttle(url)
                    data = library.fetch_bytes(url)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                    n += 1
                except Exception as e:
                    log.info("Image %s: %s", it["img"], e)
            if (it.get("lang") or "en") != "en" and not (BASE / lang_img(it["img"], it["lang"])).exists():
                try:
                    if library.fetch_lang_print(dict(it), it["lang"]):
                        n += 1
                except Exception as e:
                    log.info("Language image %s %s: %s", it["img"], it["lang"], e)
        return n

    def export_collection(self, msg=None):
        msg = msg or self.coll_msg
        groups = self.collection.groups()
        if not groups:
            msg.setText(tr("The collection is still empty."))
            return
        fmt = self.settings["export_format"]
        default = str(BASE / f"sammlung_{fmt}_{time.strftime('%Y-%m-%d')}.csv")
        path = qdialogs.save_file(tr("Export collection"), default, "CSV (*.csv)")
        if not path:
            return
        names = {s["code"]: s["name"] for s in self.catalog_sets}
        from ui.busy import busy
        try:
            with busy(self, tr("Exporting collection …")):
                n = export_csv(groups, path, fmt, names)
            msg.setText(tr(f"{n} rows exported: {path}"))
        except OSError as e:
            msg.setText(tr(f"Export failed: {e}"))

    def import_sets_dialog(self):
        paths = qdialogs.open_files(tr("Import sets"), str(BASE), tr("Set package (*.zip)"))
        for path in paths:
            self.enqueue("import", path, path=path, label="ZIP", name=path.replace("\\", "/").rpartition("/")[2])

    def edit_pack_types(self):
        types = pack_types_dialog(self.settings)
        if types is not None:
            packtypes.save_types(self.settings, types)
            self.settings_changed()
            self.last_rev = -1
            if self.page_shown("sessions", "stats"):
                self.refresh_stats()
                self.show_session_detail()  # refill the "Type" of the selected session

    def refresh_table(self):
        s = self.snap
        self.pack_rows = [(shown_name(c, self.settings), tr(finish_label(c)),
                           tr("–") if c["price"] is None else eur(c["price"])) for c in s["pack"]]
        if self.pack_sel is not None and self.pack_sel >= len(s["pack"]):
            self.pack_sel = None
        if not s.get("packs_shown", True):   # scanning cards: no packs, one list
            self.totals.setText(tr(f"{len(s['pack'])} cards · {eur(s['pack_total'])}"))
            qstate._changed()
            return
        text = tr(f"Pack {s['pack_number']}: {len(s['pack'])} cards · {eur(s['pack_total'])}")
        if s["pack_number"] > 1:
            text += tr(f"   (log {eur(s['session_total'])})")
        self.totals.setText(text)
        qstate._changed()

    def change_data_home(self):
        target = qdialogs.get_dir(tr("New place for your data"), str(BASE.parent))
        if not target:
            return
        target = pathlib.Path(target).resolve()
        here = BASE.resolve()
        if target == here:
            return
        if here in target.parents:
            qdialogs.warn(tr("Data folder"), tr("The new place must not be inside the current data folder."))
            return
        if datahome.has_data(target):
            if qdialogs.question(tr("Data folder"),
                                 tr(f"{target} already contains Bent°Corner data.\n\nUse it? Your current data stays in the old place.")):
                datahome.set_home(target)
                self.restart()
            return
        size = sum(f.stat().st_size for f in DATA.rglob("*") if f.is_file()) if DATA.exists() else 0
        if not qdialogs.question(tr("Data folder"),
                                 tr(f"Move all data ({size / 1024 / 1024 / 1024:.1f} GB) to\n{target}?\n\nBent°Corner closes briefly and restarts in the new place.")
                                 .replace(".", ",", 1)):
            return
        self.save_settings()
        self.save_session()
        self.save_collection()
        if getattr(self, "tray", None) is not None:
            self.tray.server.close()
        setupui.start_move(BASE, target)
        self.force_quit = True
        self.request_quit()

    def restart_after_restore(self):
        """After "Restore backup": the restored files must not be overwritten by the state in memory
        – so restart without saving."""
        self.restored = True
        self.restart()

    def restart(self):
        """Restart the program (e.g. after a language change)."""
        self.save_settings()
        self.save_session()
        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        args = [a for a in args if a not in ("--first-run-test", "--continue-test")] + datahome.restart_args()
        # The .exe (PyInstaller) must not share the old process's unpacked folder – it gets deleted on
        # exit. PYINSTALLER_RESET_ENVIRONMENT makes the new process unpack itself anew.
        import os
        import subprocess
        env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        if getattr(self, "tray", None) is not None:
            self.tray.server.close()
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            subprocess.Popen([datahome.program(), *args], env=env, cwd=str(BASE), creationflags=flags, close_fds=True)
        except OSError:
            log.exception("Restart failed")
            QtCore.QProcess.startDetached(datahome.program(), args)
        self.force_quit = True
        self.request_quit()

    def request_quit(self):
        """Quit the program. -> False if prices still need updating first ("Prices on close":
        work through the queue first, then quit. Closing a second time = immediately)."""
        if self.closing:
            return True
        deck_page = getattr(self, "deck_page", None)
        if deck_page is not None and not deck_page.editor.maybe_leave():
            return False  # deck not saved yet – cancel
        tray = getattr(self, "tray", None)
        if not self.force_quit and tray is not None and tray.enabled:
            tray.hide_to_tray()  # keep running: daily prices, price alerts
            return False
        if not self.force_quit and orbit.price_mode(self.settings) == "close":
            self.force_quit = self.quit_when_done = True
            self.update_all()
            self.stream.show_page("settings", tab="sets")
            self.data_info.setText(tr("Updating prices, then the program closes. Close again = quit immediately."))
            return False
        self.closing = True
        self.save_settings()
        self.save_session()  # stays open and is offered for continuing at the next start
        sessions.flush()     # logs changed a moment ago (Log page): written now
        self.save_collection()
        if self.library_win is not None:
            self.library_win.close()
        self.recognizer.running = False
        self.camera.stop()
        try:
            self.autobackup_on_exit()   # a last backup if something changed (at most 8 s, invisible)
        except Exception:  # noqa: BLE001 – closing must never fail because of it
            log.exception("Backup on exit")
        QtWidgets.QApplication.quit()
        return True

def edit_note(edits):
    """What changed on a card, as a short grey line: „Condition NM → LP · Language EN → DE“. edits: {field: [before,
    after]} (a „By hand“ line) or [{"t", "changes"}] (notes on a log card – the newest last)."""
    if not edits:
        return ""
    changes = edits if isinstance(edits, dict) else {}
    if isinstance(edits, list):
        for ed in edits:
            for k, v in (ed.get("changes") or {}).items():
                changes[k] = [changes.get(k, v)[0], v[1]]   # first before, last after
    names = {"cond": tr("Condition"), "lang": tr("Language"), "foil": "Foil", "finish": tr("Finish"),
             "edition": tr("Edition"), "grade": tr("Grade"), "grade_by": tr("Grader"), "cond_note": tr("Note")}

    def val(k, v):
        if k == "cond":   # the short label of the shop scale (NM, LP …), as everywhere else
            from cards import conditions
            return conditions.short({"cond": v or conditions.DEFAULT})
        if k == "foil":
            return "Foil" if v else tr("Normal")
        if k == "lang":
            return str(v or "en").upper()
        return str(v) if v not in (None, "") else "–"
    return " · ".join(f"{names.get(k, k)} {val(k, a)} → {val(k, b)}" for k, (a, b) in changes.items())


def _old_header_hidden(b64, n):
    """Hidden columns from the old saved state of a Qt header (QHeaderView.saveState) –
    read without a widget. The bits are in display order."""
    if not b64:
        return set()
    try:
        ds = QtCore.QDataStream(QtCore.QByteArray.fromBase64(b64.encode("ascii")))
        ds.setVersion(QtCore.QDataStream.Qt_5_0)
        if ds.readInt32() != 0xff or ds.readInt32() != 0:
            return set()
        ds.readInt32(), ds.readInt32(), ds.readInt32(), ds.readBool()  # alignment, sorting
        ds.skipRawData(4 * ds.readUInt32())                            # display positions
        logical = [ds.readInt32() for _ in range(ds.readUInt32())]     # position -> column
        bits = ds.readUInt32()
        raw = bytes(ds.readRawData((bits + 7) // 8))
        if ds.status() != QtCore.QDataStream.Ok:
            return set()
    except Exception:  # noqa: BLE001 – then just all columns
        return set()
    vis = [v for v in range(bits) if raw[v // 8] >> (v % 8) & 1]
    return {logical[v] if v < len(logical) else v for v in vis} & set(range(n))


def main():
    """Start the program (system/startup.py) with this module's main window."""
    startup.main(MainWindow)


if __name__ == "__main__":
    main()
