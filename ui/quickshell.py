"""Main window in Qt Quick (branch "qtquick"): qml/Main.qml with navigation and pages.

The logic stays where it is (app.MainWindow = control: collection, sessions, recognition, Settings). During the
rebuild the old program window (StreamWindow) keeps running invisibly – page switches, source tabs and indicator
dots are mirrored from there to here. Pages that have already moved live in qml/pages/<Name>.qml.
"""
import functools
import os
import logging

from PySide6 import QtCore, QtGui, QtQml

from ui import brand
from ui import perf
from ui import quickui
from system.i18n import tr

log = logging.getLogger("bentcorner")

# page -> QML file (if missing, the placeholder shows "being rebuilt")
# pages only built when opened (Main.qml tears them down 60 s after leaving): every item of a preloaded page costs in
# every frame of the whole window (Qt 6.11 walks all items after each new tile) – "Play" is rarely used
LAZY_PAGES = ("testing",)
PAGE_FILES = {}


class Incubator(QtQml.QQmlIncubationController):
    """Builds asynchronously loaded QML (deep views, lists column …) in 6 ms slices back to back while something is
    pending, with the event loop running in between. Qt Quick's own controller only gives a third of a frame
    (~2 ms at 144 Hz), so a deck list took 2–3 s to appear; built in one go it froze the UI for ~250 ms."""
    SLICE_MS = 6

    def __init__(self):
        super().__init__()
        self._t = QtCore.QTimer(interval=0, timeout=self._step)

    def incubatingObjectCountChanged(self, n):
        if n > 0:
            if not self._t.isActive():
                self._t.start()
        else:
            self._t.stop()

    def _step(self):
        self.incubateFor(self.SLICE_MS)
        if self.incubatingObjectCount() == 0:
            self._t.stop()


class Shell(QtCore.QObject):
    pageChanged = QtCore.Signal(str, int)
    tipRequested = QtCore.Signal(str, float, float)
    gamesChanged = QtCore.Signal()
    toast = QtCore.Signal(str)
    showRequested = QtCore.Signal(str)
    navChanged = QtCore.Signal()
    trimPages = QtCore.Signal()   # minimized: tear down pages (app.trim_memory), Main.qml rebuilds them when restored
    busyChanged = QtCore.Signal()   # ui/busy.py: the loading sign over the window while the GUI thread works

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.ctrl, self.stream = ctrl, ctrl.stream
        from app import NAV_ITEMS
        self._nav_items = [{"key": k, "text": tr(t)} for k, t in NAV_ITEMS]
        self._back, self._badges = "", {}
        self.engine = QtQml.QQmlApplicationEngine(self)
        self._incubator = Incubator()
        self.engine.setIncubationController(self._incubator)
        ctx = self.engine.rootContext()
        ctx.setContextProperty("T", quickui.palette())
        brand.expose(ctx)   # logo and the loading logo card – or neutral placeholders without brand/
        ctx.setContextProperty("shell", self)
        self.backends = {}  # page -> Python object for its QML file (as a context property of the same name)
        self._hook_stream()
        from ui import quickimages
        quickimages.install(self.engine)
        from ui import qscan
        qscan.install(self.engine)  # live images (camera, overlay) for the scan page
        from ui import qsheets
        self.sheets = qsheets.Sheets(self)
        ctx.setContextProperty("sheetHost", self.sheets)
        from ui import qdialogs
        qdialogs.set_host(self.sheets)
        from ui import qpopups
        self.popups = qpopups.install(self)  # choice lists, menus, suggestions, tooltips of the old building blocks
        ctx.setContextProperty("popupHost", self.popups)
        self._register_pages()
        self.engine.warnings.connect(lambda ws: [log.warning("QML: %s", w.toString()) for w in ws])
        self.engine.load(QtCore.QUrl.fromLocalFile(str(quickui.qml_dir() / "Main.qml")))
        roots = self.engine.rootObjects()
        self.window = roots[0] if roots else None
        if self.window is None:
            log.error("QML: Main.qml could not be loaded")
        else:
            self._log_render_loop(self.window)

    @staticmethod
    def _log_render_loop(win):
        """One line in the log: graphics API and render loop. Loading.qml keeps moving while Python works only with a
        render thread of its own ("threaded") – with the software backend ("basic") it stands still then."""
        import threading
        seen = []

        def first_frame():
            if seen:
                return
            seen.append(1)
            api = win.rendererInterface().graphicsApi() if win.rendererInterface() else None
            loop = "basic (GUI thread)" if threading.current_thread() is threading.main_thread() else "threaded"
            log.info("Render loop: %s · graphics API: %s · QT_QUICK_BACKEND=%s", loop,
                     getattr(api, "name", api), os.environ.get("QT_QUICK_BACKEND", ""))
        # once, on the render thread if there is one (a slot on every frame would take the GIL there each time)
        win.sceneGraphInitialized.connect(first_frame, QtCore.Qt.DirectConnection)

    # ---------- hook into the page logic (ui.streamwindow.StreamWindow) ----------
    def _hook_stream(self):
        st = self.stream
        self.navChanged.connect(self._nav_all_games)   # ∞ on the game button (price alerts of all games)
        self.gamesChanged.connect(self._nav_all_games)
        old_show = st.show_page

        def show_page(key, tab=None, animate=True, back=False):
            before = st.page
            old_show(key, tab=tab, animate=False, back=back)  # logic as before (invisible, without transition)
            if key != before:
                from ui import pageuse
                pageuse.note(self.ctrl.settings, key)   # only for the loading order at the next start
            self._back = st.back_from if st.back_from != key else ""
            self.navChanged.emit()
            if key != before or True:
                self.pageChanged.emit(key, 0)
        st.show_page = show_page
        def set_badge(key, on):
            """on: True = dot, a number > 0 = dot with number, otherwise gone."""
            b = dict(self._badges)
            if on:
                b[key] = int(on) if isinstance(on, int) and not isinstance(on, bool) else True
            else:
                b.pop(key, None)
            self._badges = b
            self.navChanged.emit()
        st.set_badge = set_badge
        # show/hide window (tray, full screen) -> Qt Quick window
        st.showFullScreen = lambda: self.showRequested.emit("full")
        st.showMaximized = lambda: self.showRequested.emit("max")
        st.showNormal = lambda: self.showRequested.emit("normal")
        st.hide = lambda: self.showRequested.emit("hide")
        st.show = st.raise_ = st.activateWindow = lambda: self.showRequested.emit("raise")
        st.isVisible = lambda: bool(self.window is not None and self.window.isVisible())
        st.isMinimized = lambda: bool(self.window is not None and
                                      self.window.visibility() == QtGui.QWindow.Minimized)

    def _register_pages(self):
        """Pages that have already moved to Qt Quick."""
        from ui import qlibrary
        lib = qlibrary.LibraryBackend(self.ctrl)
        lib.install_collapse_hook()
        self.register("library", lib, "LibraryPage.qml")
        from ui import qscan
        self.register("scan", qscan.ScanBackend(self.ctrl), "ScanPage.qml")
        # Main.qml itself has a property "scanPage" (bool) – it shadows the name: own, unique name
        self.engine.rootContext().setContextProperty("scanView", self.backends["scan"])
        from ui import qstudio   # Scan Studio: contribute cards to the database ("Studio" button in the scan bar)
        self.ctrl.studio = qstudio.StudioBackend(self.ctrl, self)
        self.engine.rootContext().setContextProperty("studioView", self.ctrl.studio)
        from ui import scantiles   # scan page tiles: session, cards, last hit, status – grid, modes, inline editing
        self.scan_tiles = scantiles.TilesBackend(self.ctrl, self)
        self.engine.rootContext().setContextProperty("scanTiles", self.scan_tiles)
        self.ctrl.stream.open_info = self.scan_tiles.ping   # "the log's settings": they are in the log tile
        self.preview_view = qscan.PreviewBackend(self.ctrl, self)  # camera preview (Settings → scan window)
        self.engine.rootContext().setContextProperty("previewView", self.preview_view)
        self.overlay_view = qscan.OverlayPreviewBackend(self.ctrl, self)  # stream overlay preview (same place)
        self.engine.rootContext().setContextProperty("overlayView", self.overlay_view)
        from ui import qdecks
        self.register("decks", qdecks.DecksBackend(self.ctrl), "DecksPage.qml")
        from ui import qsettings
        self.register("settings", qsettings.SettingsBackend(self.ctrl), "SettingsPage.qml")
        from ui import qimport
        self.register("import", qimport.ImportBackend(self.ctrl), "ImportPage.qml")
        from ui import qtrade
        self.register("trade", qtrade.TradeBackend(self.ctrl), "TradePage.qml")
        self.engine.rootContext().setContextProperty("tradeLists", self.backends["trade"].lists_b)   # TRADE-SPLIT
        self.engine.rootContext().setContextProperty("tradeAlarms", self.backends["trade"].alarms_b)
        self.engine.rootContext().setContextProperty("tradeFriends", self.backends["trade"].friends_b)
        from ui import qsessions
        self.register("sessions", qsessions.SessionsBackend(self.ctrl), "SessionsPage.qml")
        from ui import qstats
        self.register("stats", qstats.StatsBackend(self.ctrl), "StatsPage.qml")
        from ui import qtesting   # Test: opening-hand chances per deck (the solo table follows)
        self.register("testing", qtesting.TestBackend(self.ctrl), "TestPage.qml")
        from ui import qprofile
        self.register("profile", qprofile.ProfileBackend(self.ctrl), "ProfilePage.qml")

    def register(self, page, backend, qml_file):
        """Register a moved page: QML file + Python object (in QML under the page's name). If the active game
        doesn't support the page yet (games.<game>.features), it shows "Coming soon"."""
        PAGE_FILES[page] = qml_file
        self.backends[page] = backend
        self.engine.rootContext().setContextProperty(page + "Page", backend)

    # ---------- for QML ----------
    @QtCore.Property("QVariantList", notify=navChanged)
    def navItems(self):
        return self._nav_items

    @QtCore.Property("QVariantList", constant=True)
    def pageKeys(self):
        return [k for k, _ in __import__("app").NAV_ITEMS]

    @QtCore.Property("QVariantList", constant=True)
    def preloadEarly(self):
        """Pages preloaded right after the start page – most used first (pageuse.py)."""
        from ui import pageuse
        return [k for k in pageuse.order(self.ctrl.settings, self.pageKeys)[0] if k not in LAZY_PAGES]

    @QtCore.Property("QVariantList", constant=True)
    def preloadLate(self):
        """Rarely used pages: afterwards at leisure (or immediately when clicked)."""
        from ui import pageuse
        return [k for k in pageuse.order(self.ctrl.settings, self.pageKeys)[1] if k not in LAZY_PAGES]

    @QtCore.Property("QVariantList", constant=True)
    def lazyPages(self):
        """Pages built only when opened and torn down a minute after leaving (Main.qml) – never preloaded."""
        return list(LAZY_PAGES)

    @QtCore.Property(str, notify=navChanged)
    def backKey(self):
        return self._back

    @QtCore.Property("QVariantMap", notify=navChanged)
    def badges(self):
        return self._badges

    @QtCore.Property(float, notify=navChanged)
    def speed(self):
        """Duration factor of the animations (performance level × slow motion); 0 = no transitions."""
        if not perf.animate():
            return 0.0
        try:
            slow = max(1.0, float(self.ctrl.settings.get("anim_speed") or 1.0))
        except (TypeError, ValueError):
            slow = 1.0
        return perf.duration_factor() * slow

    @QtCore.Property(bool, notify=navChanged)
    def animate(self):
        return perf.animate()

    @QtCore.Property(str, notify=navChanged)
    def animStyle(self):
        """Library transitions: "glide" (all cards glide) or "focus" (the chosen card flies in an arc)."""
        if perf.level() == "balanced":
            return "glide"  # plainer: no "focus"
        return self.ctrl.settings.get("anim_style") or "glide"

    @QtCore.Property(str, notify=navChanged)
    def pageAnim(self):
        return self.ctrl.settings.get("page_anim") or "flip"

    @QtCore.Slot(str, int, result=str)
    def pageSourceFor(self, key, _rev):
        """Like pageSource – _rev (gameRev) makes QML ask again after a game switch."""
        return self.pageSource(key)

    @QtCore.Slot(str, result=str)
    def pageSource(self, key):
        """QML file of the page; if the active game lacks the page yet (games.<game>.features): "Coming soon"."""
        import games
        name = PAGE_FILES[key]
        feats = games.current().features
        if feats is not None and key not in feats and key not in ("settings", "stats", "profile"):
            name = "ComingSoon.qml"
        path = quickui.qml_dir() / "pages" / name
        return QtCore.QUrl.fromLocalFile(str(path)).toString()

    @QtCore.Slot(str, result=str)
    def text(self, s):
        return tr(s)

    @QtCore.Slot(str, result=str)
    def pageTitle(self, key):
        from app import NAV_ITEMS
        return tr(dict(NAV_ITEMS).get(key, key)).replace("\n", " & ")   # stacked tab names in one line

    @QtCore.Slot(result=str)
    def gameName(self):
        import games
        return games.current().name

    # ---------- game button (left in the bar) ----------
    allGamesChanged = QtCore.Signal()

    def _nav_all_games(self):
        now = self.allGames
        if now != getattr(self, "_all_games_last", None):
            self._all_games_last = now
            self.allGamesChanged.emit()

    @QtCore.Property(bool, notify=allGamesChanged)
    def allGames(self):
        """Trade → price alerts with several games, or a friend with several games switched on: the games mix
        there – the game button shows ∞."""
        try:
            tb = self.backends.get("trade")
            if self.stream.page != "trade" or tb is None:
                return False
            if tb.page.view == "friend":
                return tb.friends_b.friendMixed
            return tb.folder == "alarms" and tb.page.view == "me" and len(tb.lists_b.listGames) > 1
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    @functools.cache
    def game_icon(key):
        """The game's own pixel icon (assets/games/<game>.png) as a URL – no manufacturer logos. Program files:
        fixed while it runs, looked up once per game."""
        from ui import quickui
        f = quickui.qml_dir().parent / "assets" / "games" / f"{key}.png"
        return QtCore.QUrl.fromLocalFile(str(f)).toString() if f.exists() else ""

    @QtCore.Property(str, notify=gamesChanged)
    def gameIcon(self):
        import games
        return self.game_icon(games.current().key)

    @QtCore.Property(str, notify=gamesChanged)
    def gameLabel(self):
        import games
        return tr(games.label(self.ctrl.settings))

    @QtCore.Property(str, notify=gamesChanged)
    def gamesOffNote(self):
        """Line in the game picker for games switched off by the emergency switch (games/offswitch.py) – "" if none."""
        import games
        gone = [c["name"] for c in games.choices() if c.get("off")]
        return tr(f"No longer available: {', '.join(gone)}") if gone else ""

    @QtCore.Property(str, notify=gamesChanged)
    def gamesOffWhy(self):
        """Tooltip of that line: the reason(s) from the manifest."""
        import games
        from games import offswitch
        return "\n\n".join(offswitch.reason(c["key"]) for c in games.choices() if c.get("off"))

    @QtCore.Property(bool, notify=gamesChanged)
    def advReady(self):
        """Advanced search for the open game ready? (Pokémon: not yet – overlay "Coming soon")"""
        import games
        return bool(games.current().adv_search)

    @QtCore.Property("QVariantList", notify=gamesChanged)
    def gameChoices(self):
        """For the sliding-out row: [{key, name, short, on, active, installed, cards, mb, loading, progress}] – only
        games that already exist; loaded ones first (by cards in the collection), the not-yet-loaded ones behind."""
        import games
        from cards import packs
        on = set(games.shown(self.ctrl.settings))
        act = games.current().key
        cur = self.ctrl.current or {}
        out = []
        for c in games.choices():
            if not c["ready"]:
                continue
            k = c["key"]
            items = self.ctrl.collection.items if k == act else games.collection_items(k)
            loading = self.ctrl._game_downloading(k)
            out.append({"key": k, "name": c["name"], "short": games.SHORT.get(k, ""), "on": k in on,
                        "icon": self.game_icon(k),
                        "active": k == act, "installed": k == act or (packs.game_ready(k) and not loading),
                        "cards": sum(int(it.get("count") or 1) for it in items), "mb": packs.game_download_mb(k),
                        "loading": loading,
                        # the server has no data for it yet (packs.PackMissing – a new game until its release)
                        "later": k in self.ctrl.packs_missing,
                        "progress": self.ctrl.job_fraction() if cur.get("dl_game") == k else 0.0})
        order = list(self.ctrl.settings.get("game_order") or [])   # dragged by the user (reorderGames) takes precedence
        out.sort(key=lambda g: (not g["installed"],
                                order.index(g["key"]) if g["installed"] and g["key"] in order else len(order),
                                -g["cards"] if g["installed"] else 0))
        return out

    @QtCore.Slot(str, str, bool)
    def reorderGames(self, src, target, after):
        """Game dragged to the edge of another (like the decks): custom order – applies from then on instead of "by
        card count"."""
        keys = [g["key"] for g in self.gameChoices if g["installed"]]
        if src not in keys or target not in keys or src == target:
            return
        keys.remove(src)
        keys.insert(keys.index(target) + (1 if after else 0), src)
        self.ctrl.settings["game_order"] = keys
        self.ctrl.settings_changed()
        self.gamesChanged.emit()

    @QtCore.Slot(str)
    def downloadGame(self, key):
        self.ctrl.download_game(key)

    # ---------- download circle at the top of the bar (like in the browser) ----------
    jobsChanged = QtCore.Signal()

    # only what you started yourself and what is really loading – prices & co. after a game switch don't count
    RING_KINDS = ("pack", "carddb", "download", "images")

    def _ring_jobs(self):
        return [j for j in ([self.ctrl.current] if self.ctrl.current else []) + list(self.ctrl.jobs)
                if j.get("kind") in self.RING_KINDS]

    def _update_row(self):
        """The program update as a row in the download circle (loads in its own thread – the app stays usable)."""
        u = getattr(self.ctrl, "updater", None)
        if u is None or u.state not in ("downloading", "paused", "ready"):
            return None
        state = {"downloading": tr("downloading …"), "paused": tr("paused"),
                 "ready": tr("ready – installing restarts")}[u.state]
        return {"name": tr(f"Update to Bent°Corner {u.latest}"), "state": state, "est": "",
                "running": u.state == "downloading", "paused": u.state == "paused", "pausable": u.state != "ready",
                "pct": int(u.progress * 100) if u.state == "downloading" else -1, "kind": "update",
                "ready": u.state == "ready"}

    @QtCore.Property(bool, notify=jobsChanged)
    def updateReady(self):
        r = self._update_row()
        return bool(r and r["ready"])

    @QtCore.Property(str, notify=jobsChanged)
    def updateVersion(self):
        u = getattr(self.ctrl, "updater", None)
        return str(getattr(u, "latest", "") or "")

    @QtCore.Property(bool, notify=jobsChanged)
    def jobsActive(self):
        return (bool(self._ring_jobs()) or self._update_row() is not None) and not getattr(self, "_switching", False)

    @QtCore.Property(bool, notify=jobsChanged)
    def jobsPaused(self):
        """Everything the circle shows is paused (the circle then shows ‖ instead of the arrow)."""
        jobs = self._ring_jobs()
        u = self._update_row()
        if u and not u["ready"]:
            return all(j.get("paused") for j in jobs) and u["paused"]
        return bool(jobs) and all(j.get("paused") for j in jobs)

    @QtCore.Property(float, notify=jobsChanged)
    def jobsProgress(self):
        cur = self.ctrl.current
        if cur and cur.get("kind") in self.RING_KINDS:
            return float(self.ctrl.job_fraction())
        u = self._update_row()
        return float(self.ctrl.updater.progress) if u else 0.0

    @QtCore.Property("QVariantList", notify=jobsChanged)
    def jobsList(self):
        """[{name, state, est, running}] – what is loading, what is waiting."""
        return [{"name": r["name"] or r["label"], "state": r["state"], "est": r["est"],
                 "running": r["job"] is self.ctrl.current and not r["job"].get("paused"),
                 "paused": bool(r["job"].get("paused")), "pausable": r["job"].get("kind") in self.RING_KINDS,
                 "pct": int(self.ctrl.job_fraction() * 100) if r["job"] is self.ctrl.current else -1}
                for r in self.ctrl.queue_view()] + ([self._update_row()] if self._update_row() else [])

    @QtCore.Slot(int)
    def pauseJob(self, i):
        """Download list: pause or resume."""
        rows = self.ctrl.queue_view()
        if 0 <= i < len(rows):
            job = rows[i]["job"]
            self.ctrl.pause_job(job, not job.get("paused"))
            self.jobsChanged.emit()
        elif i == len(rows) and self._update_row():   # the update: pause / resume
            u = self.ctrl.updater
            u.pause() if u.state == "downloading" else u.download()
            self.jobsChanged.emit()

    @QtCore.Slot()
    def installUpdate(self):
        """The "Install" button in the download list: save, put the new exe in place, restart."""
        self.ctrl.update_install()

    @QtCore.Slot(int)
    def cancelJob(self, i):
        rows = self.ctrl.queue_view()
        if 0 <= i < len(rows):
            self.ctrl.cancel_job(rows[i]["job"])
            self.jobsChanged.emit()

    @QtCore.Slot(str)
    def pickGame(self, key):
        """Without mixing: open this game (restart, own data). With mixing: switch on/off (the open game always
        stays on)."""
        import games
        s = self.ctrl.settings
        if not any(c["key"] == key and c["ready"] for c in games.choices()):
            return
        act = games.current().key
        if s.get("games_mix") and games.MIX_ENABLED:
            if key == act:
                return
            on = [k for k in (s.get("games_on") or []) if k != act]
            on = [k for k in on if k != key] if key in on else on + [key]
            s["games_on"] = on
            self.ctrl.settings_changed()
            self.gamesChanged.emit()
            self._games_refresh()
            return
        if key == act:
            return
        if self.ctrl.switch_game(key):
            self.show_toast(tr(f"{games.name_of(key)} opened"))

    gameRevChanged = QtCore.Signal()

    @QtCore.Property(int, notify=gameRevChanged)
    def gameRev(self):
        return getattr(self, "_game_rev", 0)

    gameSwitchChanged = QtCore.Signal()

    def game_switch_begin(self, name):
        """Game switch begins: fade in the transition (Main.qml, BootShuffle)."""
        self._switch_name, self._switching = name, True
        self.gameSwitchChanged.emit()
        self.jobsChanged.emit()

    def game_switch_end(self):
        self._switching = False
        self.gameSwitchChanged.emit()
        self.jobsChanged.emit()

    def set_busy(self, text):
        """ui/busy.py: show (text) or hide ("") the loading card over the window."""
        self._busy = text or ""
        self.busyChanged.emit()

    @QtCore.Property(str, notify=busyChanged)
    def busyText(self):
        return getattr(self, "_busy", "")

    @QtCore.Property(bool, notify=gameSwitchChanged)
    def gameSwitching(self):
        return bool(getattr(self, "_switching", False))

    @QtCore.Property(str, notify=gameSwitchChanged)
    def gameSwitchName(self):
        return getattr(self, "_switch_name", "") or ""

    def game_switched(self):
        """After the switch: reload tabs whose page depends on the game (real page ↔ "Coming soon")."""
        self._game_rev = getattr(self, "_game_rev", 0) + 1
        self.gameRevChanged.emit()
        self.gamesChanged.emit()
        self.navChanged.emit()

    def _games_refresh(self):
        lib = getattr(self.ctrl, "library_win", None)
        if lib is not None:
            try:
                lib.refresh(keep=True)
            except Exception:  # noqa: BLE001 – the display refreshes next time
                pass

    @QtCore.Slot(str, int)
    def pick(self, key, _dir=0):
        self.stream.show_page(key)

    @QtCore.Slot(str)
    def openBack(self, key):
        """Open a page with the way back to the current one (e.g. from the friends menu)."""
        self.stream.show_page(key, back=True)

    @QtCore.Slot(str)
    def pickView(self, key):
        """A view inside one tab (Sessions: list | stats): switch without the page flip."""
        self.stream.show_page(key, animate=False)

    @QtCore.Slot(str)
    def navHover(self, key):
        """Mouse rests on a tab (300 ms): "Scan" -> start the AI process already, on click it is often ready."""
        if key == "scan":
            self.ctrl.warm_ai()

    @QtCore.Slot(result=bool)
    def requestClose(self):
        """Window close button: quit (save) – or go to the system tray or fetch prices first (False = stays)."""
        return bool(self.ctrl.request_quit())

    @QtCore.Slot()
    def goBack(self):
        self.stream.go_back()

    @QtCore.Slot(str, float, float)
    def tip(self, text, x, y):
        self.tipRequested.emit(text, x, y)

    def show_toast(self, text):
        self.toast.emit(text)

    def refresh_theme(self):
        self.engine.rootContext().setContextProperty("T", quickui.palette())
