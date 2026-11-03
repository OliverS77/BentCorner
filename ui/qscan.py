"""Scan page in Qt Quick (qml/pages/ScanPage.qml) – without a bridge.

Camera image: every new camera frame goes as a QImage to the image source image://live/<name>cam/<number>; Qt Quick
loads it as a texture and scales it on the GPU (before: cv2 downscaling + QPainter + copying over the bridge, all on
the CPU). Overlay (pack list, Biggest Hit, effects …): exactly the same drawing logic as before (ui.overlay_paint.Overlay.paint)
into a transparent image – only when something changes or an animation is running – so the stream looks exactly the
same. Mouse and mouse wheel go to the view's logic (ui.scanview.ScanView).
QML draws the scan page's windows (find card, stream info, Stats) itself (see ScanPage.qml).
"""
import threading
import time

import cv2

from PySide6 import QtCore, QtGui, QtQml, QtQuick
from PySide6.QtCore import QPointF, Qt

from system.i18n import tr

_live = {}
_lock = threading.Lock()


class LiveImages(QtQuick.QQuickImageProvider):
    """Image source for continuously new images (camera, overlay): image://live/<name>/<number>."""

    def __init__(self):
        super().__init__(QtQml.QQmlImageProviderBase.ImageType.Image)

    def requestImage(self, key, size, requested):
        name = key.split("/", 1)[0]
        with _lock:
            img = _live.get(name)
        return img if img is not None else QtGui.QImage(1, 1, QtGui.QImage.Format_ARGB32_Premultiplied)


def install(engine):
    engine.addImageProvider("live", LiveImages())


def _put(name, img):
    with _lock:
        _live[name] = img


class LiveView(QtCore.QObject):
    """A live image (camera + drawing on top) for Qt Quick (LiveView.qml). view = ui.scanview.ScanView: logic (mouse,
    zoom, scan frame) and drawing of the layers (paint_layers)."""
    changed = QtCore.Signal()      # camera image, overlay, crop

    OVERLAY_IDLE_S = 0.5           # without changes, redraw at most this often (clock, slow transitions)
    FX_LAYER = False               # the moments (big preview, Biggest Hit) on their own layer above the page (fxSource)
    FROST_W = 0                    # > 0: a small blurred copy of the camera image this wide (frostSource) – the tiles'
                                   # frosted glass; made here once per new frame (~1 ms), so the GPU only scales it

    def __init__(self, ctrl, view, name, parent=None):
        super().__init__(parent)
        self.ctrl, self.view, self.name = ctrl, view, name
        self._cam_n, self._ov_n, self._seq = 0, 0, None
        self._frost_n, self._frost_lum, self._frost_step = 0, 0.0, 0.0
        self._fx_n, self._fx_on = 0, False   # the top layer: drawn only while it has something
        self._rest, self._rest_n = None, 0   # the resting camera's last picture (blurred) – shown until it is back
        self._size, self._dpr = QtCore.QSize(1600, 900), 1.0
        self._dirty, self._ov_t, self._active = True, 0.0, False
        self._canvas = QtCore.QRectF(0, 0, 1600, 900)
        self._vrect = QtCore.QRectF(0, 0, 1920, 1080)
        view.on_update = lambda: setattr(self, "_dirty", True)  # "redraw" = overlay fresh
        self._timer = QtCore.QTimer(self, interval=15, timeout=self._tick)
        self._timer.setTimerType(Qt.PreciseTimer)

    def busy(self, now):
        """Is an animation currently running (then redraw every time)?"""
        return False

    # ---------- tick ----------
    @QtCore.Slot(bool)
    def setActive(self, on):
        self._active = bool(on)
        if on:
            self._dirty = True
            self._timer.start()
        else:
            self._timer.stop()

    @QtCore.Slot(float, float, float)
    def setSize(self, w, h, dpr):
        size = QtCore.QSize(max(320, round(w)), max(180, round(h)))
        if size != self._size or dpr != self._dpr:
            self._size, self._dpr, self._dirty = size, float(dpr or 1.0), True
            self.view.resize(size)  # same size = same coordinates for overlay buttons and scan frame
            self._tick()

    def _tick(self):
        ctrl, view = self.ctrl, self.view
        if view.size() != self._size:
            view.resize(self._size)
        changed = False
        frame = ctrl.frame_rgb
        seq = ctrl.frame_seq if frame is not None else None
        if seq != self._seq:
            self._seq = seq
            if frame is not None:
                h, w = frame.shape[:2]
                img = QtGui.QImage(frame.data, w, h, frame.strides[0], QtGui.QImage.Format_RGB888).copy()
                _put(self.name + "cam", img)
                self._cam_n += 1
                if self.FROST_W:
                    self._frost(frame)
            self._dirty = True  # image size can change (crop)
            changed = True
        rest = getattr(ctrl, "frame_rest", None)
        if rest is not self._rest:
            self._rest = rest
            if rest is not None:
                h, w = rest.shape[:2]
                _put(self.name + "rest", QtGui.QImage(rest.data, w, h, rest.strides[0], QtGui.QImage.Format_RGB888).copy())
                self._rest_n += 1
            changed = True
        c = view.canvas()
        vr = QtCore.QRectF(*view.view_rect())
        if c != self._canvas or vr != self._vrect:
            self._canvas, self._vrect, changed = c, vr, True
        now = time.monotonic()
        if self._dirty or self.busy(now) or now - self._ov_t >= self.OVERLAY_IDLE_S:
            self._dirty, self._ov_t = False, now
            self._paint_overlay()
            changed = True
        if changed:
            self.changed.emit()

    def _frost(self, frame):
        """The frosted glass: the whole frame small (area average) and blurred – QML scales it like the camera image."""
        h, w = frame.shape[:2]
        fw = self.FROST_W
        fh = max(1, round(fw * h / w))
        small = cv2.GaussianBlur(cv2.resize(frame, (fw, fh), interpolation=cv2.INTER_AREA), (0, 0), fw / 90)
        _put(self.name + "frost", QtGui.QImage(small.data, fw, fh, small.strides[0], QtGui.QImage.Format_RGB888).copy())
        self._frost_n += 1
        # how bright it is (slowly, in steps of 0.05 – the tiles' tint follows it without flickering)
        self._frost_lum = self._frost_lum * 0.9 + float(small.mean()) / 255 * 0.1
        self._frost_step = round(self._frost_lum / 0.05) * 0.05

    def _image(self, paint):
        dpr = self._dpr
        size = QtCore.QSize(round(self._size.width() * dpr), round(self._size.height() * dpr))
        img = QtGui.QImage(size, QtGui.QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.transparent)
        p = QtGui.QPainter(img)
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform
                         | QtGui.QPainter.TextAntialiasing)
        try:
            paint(p, self.view.canvas(), dpr)
        finally:
            p.end()
        return img

    def _paint_overlay(self):
        if not self.FX_LAYER:
            _put(self.name + "overlay", self._image(self.view.paint_layers))
            self._ov_n += 1
            return
        _put(self.name + "overlay", self._image(lambda p, c, dpr: self.view.paint_layers(p, c, dpr, fx=False)))
        self._ov_n += 1
        on = self.ctrl.overlay.has_fx(time.monotonic())
        if on or self._fx_on:   # once more after the last moment: the layer goes empty
            self._fx_on = on
            _put(self.name + "fx", self._image(self.view.paint_fx))
            self._fx_n += 1

    # ---------- for QML ----------
    @QtCore.Property(str, notify=changed)
    def camSource(self):
        return f"image://live/{self.name}cam/{self._cam_n}" if self._seq is not None else ""

    @QtCore.Property(float, notify=changed)
    def frostLum(self):
        """Brightness of the frosted camera image, 0 dark … 1 white (steps of 0.05) – the tiles' tint follows it."""
        return float(self._frost_step) if self._frost_n and self._seq is not None else 0.0

    @QtCore.Property(str, notify=changed)
    def frostSource(self):
        """The camera image small and blurred (FROST_W) – "" without one."""
        return f"image://live/{self.name}frost/{self._frost_n}" if self._frost_n and self._seq is not None else ""

    @QtCore.Property(str, notify=changed)
    def restSource(self):
        """The camera rests (another page for a minute): its last picture, blurred – "" when there is none."""
        return f"image://live/{self.name}rest/{self._rest_n}" if self._rest is not None else ""

    @QtCore.Property(str, notify=changed)
    def overlaySource(self):
        return f"image://live/{self.name}overlay/{self._ov_n}"

    @QtCore.Property(str, notify=changed)
    def fxSource(self):
        """The top layer (FX_LAYER): the big preview and the Biggest-Hit moment – above tiles and windows."""
        return f"image://live/{self.name}fx/{self._fx_n}" if self._fx_n else ""

    @QtCore.Property(QtCore.QRectF, notify=changed)
    def canvas(self):
        return QtCore.QRectF(self._canvas)

    @QtCore.Property(QtCore.QRectF, notify=changed)
    def viewRect(self):
        """Visible crop of the camera image in pixels (preview zoom)."""
        return QtCore.QRectF(self._vrect)

    @QtCore.Property(QtCore.QSizeF, notify=changed)
    def frameSize(self):
        fw, fh = self.view.frame_size()
        return QtCore.QSizeF(fw, fh)

    # ---------- mouse -> view logic ----------
    @QtCore.Slot(float, float, int)
    def press(self, x, y, button):
        self.view.press(QPointF(x, y), Qt.MouseButton(button))
        self._dirty = True

    @QtCore.Slot(float, float, int)
    def release(self, x, y, button):
        self.view.release(QPointF(x, y), Qt.MouseButton(button))
        self._dirty = True

    @QtCore.Slot(float, float, int)
    def move(self, x, y, buttons):
        self.view.move(QPointF(x, y))
        self._dirty = True

    @QtCore.Slot(float, float)
    def doubleClick(self, x, y):
        self.view.double_click(QPointF(x, y))
        self._dirty = True

    @QtCore.Slot()
    def enter(self):
        self.view.hover_q = True
        self._dirty = True

    @QtCore.Slot()
    def leave(self):
        self.view.hover_q = False
        self.view.leave()
        self._dirty = True

    @QtCore.Slot(float, float, int)
    def wheel(self, x, y, dy):
        self.wheelMods(x, y, dy, 0)

    @QtCore.Slot(float, float, int, int)
    def wheelMods(self, x, y, dy, mods):
        self.view.wheel(QPointF(x, y), int(dy), Qt.KeyboardModifiers(mods))
        self._dirty = True

    @QtCore.Property(str, notify=changed)
    def cursor(self):
        return self.view.cursor


class PreviewBackend(LiveView):
    """Camera preview in Settings (scan window): drag the scan frame, mouse wheel = size, Ctrl+mouse wheel = zoom,
    right mouse button = move the crop."""

    def __init__(self, ctrl, parent=None):
        super().__init__(ctrl, ctrl.preview, "preview", parent)

    def busy(self, now):
        return self.ctrl.tracker.quad is not None  # lights run around the card

    @QtCore.Slot(bool)
    def setActive(self, on):
        super().setActive(on)
        _watch(self.ctrl, self.name, on)


def _watch(ctrl, name, on):
    """Which previews in Settings are currently visible – as long as one is there, the camera runs."""
    w = ctrl.__dict__.setdefault("_preview_watchers", set())
    (w.add if on else w.discard)(name)
    ctrl.preview_watched = bool(w)


class OverlayPreviewBackend(LiveView):
    """Stream overlay as a small live preview in Settings (scan window): the same view as the scan window,
    computed at window size, shown scaled down – clicks work as they do there (if something opens a window in the
    stream, e.g. ⚙ on the info blocks, the program jumps to the scan window)."""
    aspectChanged = QtCore.Signal()

    def __init__(self, ctrl, parent=None):
        super().__init__(ctrl, ctrl.stream.view, "ovprev", parent)
        self._k = 1.0          # window pixels per preview pixel

    def busy(self, now):
        return self.ctrl.overlay.busy(now)

    @QtCore.Slot(bool)
    def setActive(self, on):
        super().setActive(on)
        _watch(self.ctrl, self.name, on)

    def _logical(self):
        shell = getattr(self.ctrl, "shell", None)
        w = shell.window if shell is not None else None
        if w is not None and w.width() > 0:
            return QtCore.QSize(max(960, w.width()), max(540, w.height()))
        return QtCore.QSize(1600, 900)

    @QtCore.Property(float, notify=aspectChanged)
    def aspect(self):
        size = self._logical()
        return size.width() / max(1, size.height())

    @QtCore.Slot(float, float, float)
    def setSize(self, w, h, dpr):
        size = self._logical()
        self._k = size.width() / max(1.0, w)
        # compute at window size, but only draw as finely as the preview is large
        super().setSize(size.width(), size.height(), max(0.2, (dpr or 1.0) / self._k))
        aspect = size.width() / max(1, size.height())
        # only on a real change, and after this call: QML calls setSize from the height change that this very
        # aspect causes – a synchronous signal re-enters that binding (binding loop)
        if aspect != getattr(self, "_aspect", None):
            self._aspect = aspect
            QtCore.QTimer.singleShot(0, self.aspectChanged.emit)

    @QtCore.Property(QtCore.QRectF, notify=LiveView.changed)
    def canvas(self):
        c, k = self._canvas, self._k
        return QtCore.QRectF(c.x() / k, c.y() / k, c.width() / k, c.height() / k)

    def _p(self, x, y):
        return x * self._k, y * self._k

    @QtCore.Slot(float, float, int)
    def press(self, x, y, button):
        super().press(*self._p(x, y), button)

    @QtCore.Slot(float, float, int)
    def release(self, x, y, button):
        super().release(*self._p(x, y), button)

    @QtCore.Slot(float, float, int)
    def move(self, x, y, buttons):
        super().move(*self._p(x, y), buttons)

    @QtCore.Slot(float, float)
    def doubleClick(self, x, y):
        super().doubleClick(*self._p(x, y))

    @QtCore.Slot(float, float, int, int)
    def wheelMods(self, x, y, dy, mods):
        super().wheelMods(*self._p(x, y), dy, mods)


def scan_question(c):
    """The scanner asks: "print" / "lang" (the card search shows it) or "print_wait" / "lang_wait" (the search is busy
    – the status line offers it, key K); "" otherwise."""
    st = getattr(c, "stream", None)
    panel = getattr(st, "card_panel", None) if st is not None else None
    q = getattr(panel, "question", None)
    if q is not None and not panel.isHidden():
        return q["kind"]
    if q is not None:   # asked, but the window isn't up: the [K] note, never the text alone
        return f"{q['kind']}_wait"
    wait = getattr(c, "question_wait", None)
    return f"{wait}_wait" if wait else ""


def search_offered(c):
    """A card lies there without a hit and no search window is open: the status line offers the search (K)."""
    st = getattr(c, "stream", None)
    return getattr(c, "search_offer", None) is not None and st is not None and st.card_panel.isHidden()


class ScanBackend(LiveView):
    FX_LAYER = True
    FROST_W = 240
    panelsChanged = QtCore.Signal()
    barChanged = QtCore.Signal()   # bottom bar: pause, camera, scan frame, quick settings
    stageChanged = QtCore.Signal()   # what the scanner is doing (line under the scan frame) or where the frame is
    STAGE_AFTER = 0.3   # s a stage must last before the line shows it (no flicker between frames) …
    STAGE_HOLD = 0.6    # … and s it stays at least – "counted" both immediately

    def __init__(self, ctrl, parent=None):
        super().__init__(ctrl, ctrl.stream.view, "", parent)
        from ui import qform
        from ui import qstate
        self._quick = ""   # open settings window of the bar: "" · "cam" (camera)
        self.stats_m = qform.Form(self._build_stats, self)
        self._stats_tile = (False, False)   # shown, wide (set before the form: it builds right away)
        self.stats_tile_m = qform.Form(self._build_stats_tile, self)   # the stats tile (scan page)
        self._stats_rev = None
        self._stats_t = QtCore.QTimer(self, interval=1500, timeout=self._stats_tile_tick)
        qstate.watch(self._state_changed)
        self._panel_t = QtCore.QTimer(self, interval=150, timeout=self._panels)
        self._panel_state = None
        self._stage = {"shown": "", "at": 0.0, "cand": "", "since": 0.0, "zone": None}
        from ui.qcardsearch import CardSearchBackend
        self.card_b = CardSearchBackend(ctrl.stream.card_panel, self)

    def busy(self, now):
        studio = getattr(self.ctrl, "studio", None)
        if studio is not None and (studio.on or now - studio.since < 0.5):   # outline follows the card, overlay glides
            return True
        return self.ctrl.overlay.busy(now)

    @QtCore.Slot(bool)
    def setActive(self, on):
        super().setActive(on)
        self._panel_t.start() if on else self._panel_t.stop()

    # ---------- bottom bar in the middle ----------
    @QtCore.Property(bool, notify=barChanged)
    def paused(self):
        return bool(self.ctrl.recognizer.paused)

    @QtCore.Property(bool, notify=barChanged)
    def sessionActive(self):
        """Is a session running? Otherwise the scan page shows "New session" (counting starts only after that)."""
        return bool(self.ctrl.session.active)

    @QtCore.Property(bool, notify=barChanged)
    def ticketMode(self):
        return bool(getattr(self.ctrl.recognizer, "ticket_mode", False))

    @QtCore.Slot()
    def cancelTicket(self):
        self.ctrl.recognizer.ticket_mode = False
        self.barChanged.emit()

    @QtCore.Property(bool, notify=barChanged)
    def cameraOn(self):
        return not self.ctrl.camera_user_off

    @QtCore.Property(bool, notify=barChanged)
    def frameEdit(self):
        return self.view.zone_edit

    @QtCore.Property(bool, notify=barChanged)
    def quickOpen(self):
        return bool(self._quick)

    @QtCore.Property(str, notify=barChanged)
    def quickMode(self):
        return self._quick

    @QtCore.Slot()
    def togglePause(self):
        self.ctrl.toggle_pause()
        self._dirty = True
        self.barChanged.emit()

    @QtCore.Slot()
    def toggleCamera(self):
        self.ctrl.toggle_camera_user()
        self._dirty = True
        self.barChanged.emit()

    @QtCore.Slot()
    def toggleFrameEdit(self):
        """Scan frame (its own switch in the bar): while on, the scan frame lies above the overlay (which stays)
        – even without a camera. Drag = move, mouse wheel over it = size. May stay on.
        Open settings windows close meanwhile (they would otherwise lie above the frame)."""
        self._quick = ""
        self.view.zone_edit = not self.view.zone_edit
        self.view._drag = None
        self.view.cursor = "arrow"
        self._dirty = True
        self.barChanged.emit()

    @QtCore.Slot(str)
    def openPanel(self, which):
        """Bar: stats | info | search – opens the window (or closes it if it is already open)."""
        st = self.ctrl.stream
        if which == "stats":
            st.stats_panel.hide() if not st.stats_panel.isHidden() else st.open_stats()
        elif which == "info":   # the log's settings live in the log tile: it lights up
            st.open_info()
            return
        elif which == "search":   # press again: close
            st.close_card_panel() if not st.card_panel.isHidden() or self.ctrl.overlay.panel_open else self.ctrl.add_card()
        self._quick = ""
        self._panels()
        self.barChanged.emit()

    @QtCore.Slot()
    @QtCore.Slot(str)
    def toggleQuick(self, mode=""):
        """Bar: "cam" = camera; again or empty = close."""
        self._quick = "" if (not mode or mode == self._quick) else mode
        if self._quick:
            self.ctrl.stream.stats_panel.hide()
            self._panels()
        self.barChanged.emit()

    # ---------- the camera window (ScanPage.qml draws it: no boxes, only an ✕) ----------
    @QtCore.Property(str, notify=barChanged)
    def cameraName(self):
        cams = self.ctrl.cam_combo
        return cams.currentText() if cams.count() else ""

    @QtCore.Property(bool, notify=barChanged)
    def mirrorH(self):
        return bool(self.ctrl.settings.get("mirror"))

    @QtCore.Property(bool, notify=barChanged)
    def mirrorV(self):
        return bool(self.ctrl.settings.get("mirror_v"))

    @QtCore.Slot()
    def pickCamera(self):
        """The device: a light menu where the click was (every camera, the current one lit)."""
        from ui import qdialogs
        cams = self.ctrl.cam_combo
        names = cams.items()
        if not names:
            return

        def pick(i):
            cams.setCurrentIndex(i)
            self.ctrl.camera_selected()
            self.barChanged.emit()
        qdialogs.menu(tr("Camera"), [{"text": n, "checkable": True, "on": i == cams.currentIndex()}
                                     for i, n in enumerate(names)], pick)

    @QtCore.Slot()
    def rescanCameras(self):
        self.ctrl.fill_cameras()
        self.ctrl.camera_selected()
        self.barChanged.emit()

    @QtCore.Slot(str, bool)
    def setMirror(self, which, on):
        key, attr = ("mirror", "mirror") if which == "h" else ("mirror_v", "flip_v")
        self.ctrl.settings[key] = bool(on)
        self.ctrl.settings_changed()
        setattr(self.ctrl.camera, attr, bool(on))
        self._dirty = True
        self.barChanged.emit()

    @QtCore.Slot()
    def scanSettings(self):
        self.toggleQuick("")
        self.ctrl.go_settings("scan")

    def _state_changed(self):
        st = self.ctrl.stream
        if self._active and not st.stats_panel.isHidden():
            self.stats_m.soon()

    # ---------- Stats in the stream ----------
    def _build_stats(self, ui):
        from ui import qcharts
        ctrl = self.ctrl
        p = ctrl.stream.stats_panel

        def close():
            p.hide()
            self._panels()

        def tab(i):
            p.tab = i

        def chart(c):
            return ui.chart(qcharts.spec(c))
        body = []
        for row in p.layout():
            body.append(ui.row([chart(c) for c in row], spacing=10) if isinstance(row, tuple) else chart(row))
        return ui.col([
            ui.row([ui.label(tr("Stats"), px=24, bold=True),
                    ui.button(tr("All stats →"), lambda: (close(), ctrl.stream.show_page("stats", back=True)),
                              tip=tr("Logs & stats → Stats – the arrow on “Scan” leads back")),
                    ui.button("✕", close)]),
            ui.tabs([tr("This log"), tr("Total")], p.tab, tab, ui.col(body, spacing=10)),
        ], spacing=10)

    # ---------- the scan tile: the big preview of a card of its list stands beside it ----------
    @QtCore.Slot(float, float, float, float)
    def setListTile(self, x, y, w, h):
        """The scan tile: the preview of a card of its list stands right beside it."""
        self.ctrl.overlay.list_tile = QtCore.QRectF(x, y, w, h) if w > 0 and h > 0 else None

    @QtCore.Slot(float, float)
    def setFreeBand(self, top, bottom):
        """The free strip between the status tile and the dock: that preview stays inside it (name and price too)."""
        self.ctrl.overlay.free_band = QtCore.QRectF(0, top, 1, bottom - top) if bottom > top else None

    # ---------- the stats tile ----------
    @QtCore.Slot(bool, bool)
    def setStatsTile(self, shown, wide):
        """The stats tile is shown (wide: two charts side by side): its charts follow the log – every 1.5 s at most,
        only when something changed. Hidden: nothing is computed."""
        if (bool(shown), bool(wide)) == self._stats_tile:
            return
        self._stats_tile = (bool(shown), bool(wide))
        self._stats_rev = None
        if shown:
            self._stats_tile_tick()
            self._stats_t.start()
        else:
            self._stats_t.stop()

    def _stats_tile_tick(self):
        p = self.ctrl.stream.stats_panel
        rev = ((getattr(self.ctrl, "snap", None) or {}).get("rev"), self.ctrl.session.id, p.tab, self._stats_tile[1])
        if rev == self._stats_rev:
            return
        self._stats_rev = rev
        p.refresh()
        self.stats_tile_m.soon()

    def _build_stats_tile(self, ui):
        from ui import qcharts
        p = self.ctrl.stream.stats_panel

        def tab(i):
            p.tab = i
            self._stats_rev = None
            self._stats_tile_tick()
        body = []
        for row in p.layout():
            charts = list(row) if isinstance(row, tuple) else [row]
            if self._stats_tile[1] and len(charts) > 1:
                body.append(ui.row([ui.chart(qcharts.spec(c)) for c in charts], spacing=10))
            else:
                body += [ui.chart(qcharts.spec(c)) for c in charts]
        return ui.col([ui.tabs([tr("This log"), tr("Total")], p.tab, tab, ui.col(body, spacing=10)),
                       ui.row([ui.stretch(), ui.button(tr("All stats →"), lambda: self.ctrl.stream.show_page("stats", back=True),
                                                       tip=tr("Logs & stats → Stats – the arrow on “Scan” leads back"))])],
                      spacing=10)

    @QtCore.Property(QtCore.QObject, constant=True)
    def statsTileForm(self):
        return self.stats_tile_m

    # ---------- scan page windows ----------
    def _stage_tick(self):
        """Scanner stage for the line (every 150 ms while the page is shown, a signal only on a change)."""
        s, now = self._stage, time.monotonic()
        rec = getattr(self.ctrl, "recognizer", None)
        live = getattr(self.ctrl, "frame_rgb", None) is not None   # no camera image: the scanner isn't working at all
        code = getattr(rec, "stage", "") if rec is not None and live and not getattr(rec, "sleeping", False) else ""
        if code != s["cand"]:
            s["cand"], s["since"] = code, now
        quick = code == "counted"
        if code != s["shown"] and (quick or (now - s["since"] >= self.STAGE_AFTER and now - s["at"] >= self.STAGE_HOLD)):
            s["shown"], s["at"] = code, now
            self.stageChanged.emit()
        offer = (search_offered(self.ctrl), scan_question(self.ctrl))
        if offer != s.get("offer"):   # the card search offered for a card without a hit (scan_ctl.search_offer)
            s["offer"] = offer
            self.stageChanged.emit()
        zone = self.view.zone_in_view().getRect()
        if zone != s["zone"]:
            s["zone"] = zone
            self.stageChanged.emit()

    # the status tile's chain: the recognition's real steps, in order – a stage code -> how far it has come
    # (0 the card is in the frame, 1 fingerprint, 2 image match, 3 print / collector line, 4 counted with its price)
    STEP_OF = {"searching": 1, "loading_refs": 2, "comparing": 2, "reading_line": 3, "asking": 3, "counted": 4}

    @QtCore.Property("QVariantMap", notify=stageChanged)
    def scanStage(self):
        """{code, text, step, card} – what the scanner is doing right now (recognizer.STAGES, same wording as the phone
        scanner); step: how far along the chain (STEP_OF, -1 = no card / not working); card: the card it is on."""
        from scanner import fingerprint
        from scanner.recognizer import stage_text
        code = self._stage["shown"]
        cur = getattr(getattr(self.ctrl, "recognizer", None), "current", None) or {}
        step = self.STEP_OF.get(code, -1)
        text = stage_text(code)
        if code == "idle" and not fingerprint.available():   # no SCAN° Engine: the collector line alone – said quietly
            text += "  ·  " + tr("SCAN° Engine missing – collector number only")
        return {"code": code, "text": text, "step": step,
                "card": (cur.get("name") or "") if step >= 1 else "", "offer": search_offered(self.ctrl),
                "question": scan_question(self.ctrl)}

    def _panels(self):
        self._stage_tick()
        st = self.ctrl.stream
        state = tuple((not w.isHidden(), w.geometry().getRect()) for w in (st.card_panel, st.stats_panel)) + \
            (tuple(sorted(self.previewStrip.items())),)
        if state != self._panel_state:
            self._panel_state = state
            self.panelsChanged.emit()
        sess = (self.ctrl.session.id, self.ctrl.session.active, getattr(self.ctrl.recognizer, "ticket_mode", False))
        if sess != getattr(self, "_sess_state", None):   # session started/ended, ticket mode: rebuild the bar
            self._sess_state = sess
            self.barChanged.emit()

    def _geo(self, w):
        g = w.geometry()
        return {"shown": not w.isHidden(), "x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()}

    @QtCore.Property("QVariantMap", notify=panelsChanged)
    def cardPanel(self):
        cp = self.ctrl.stream.card_panel
        g = self._geo(cp)
        g["mode"] = "edit" if cp.editing is not None else "add"   # QML: edit slides in from the side, search from below
        g["fromLeft"] = True
        return g

    @QtCore.Property("QVariantMap", notify=panelsChanged)
    def previewStrip(self):
        """{x0, x1}: the strip beside the open card search where its big preview stands (overlay_paint
        ._free_beside_panel, window pixels) while it shows a card – the tiles there fade out softly (never a card over a
        tile's content); {} otherwise."""
        cp, ov = self.ctrl.stream.card_panel, self.ctrl.overlay
        if cp.isHidden() or ov.panel_hover is None or ov.hover_list:
            return {}
        c, s = ov._canvas, ov._s
        free = ov._free_beside_panel(1920.0) if s > 0 else None   # the overlay's own choice (overlay units, 1920 wide)
        if not free:
            return {}
        return {"x0": c.left() + free[0] * s, "x1": c.left() + free[1] * s}

    @QtCore.Property("QVariantMap", notify=panelsChanged)
    def statsPanel(self):
        return self._geo(self.ctrl.stream.stats_panel)

    @QtCore.Property(QtCore.QObject, constant=True)
    def cardSearch(self):
        return self.card_b

    @QtCore.Property(QtCore.QObject, constant=True)
    def statsForm(self):
        return self.stats_m

    @QtCore.Slot(str)
    def closePanel(self, which):
        st = self.ctrl.stream
        if which == "card":
            st.close_card_panel()
        else:
            st.stats_panel.hide()
        self._panels()

    # ---------- keys ----------
    @QtCore.Slot(str)
    def key(self, k):
        c = self.ctrl
        studio = getattr(c, "studio", None)
        if studio is not None and studio.on:   # in the studio: space = capture, otherwise nothing (nothing is counted)
            if k == "Space":
                studio.capture()
            return
        packs = (getattr(c, "snap", None) or {}).get("packs_shown", True)   # N: a new pack only when opening boosters
        fn = {"N": c.new_pack if packs else None, "U": c.remove_card, "Delete": c.remove_card, "F": c.toggle_foil, "Z": c.toggle_cond, "G": c.toggle_out,
              "Space": c.toggle_pause, "E": c.edit_card, "K": c.add_card, "B": c.open_library,
              "+": c.plus_card}.get(k)
        if fn is not None:
            fn()
        self._dirty = True
        self.barChanged.emit()   # e.g. space = pause: the bar shows it
