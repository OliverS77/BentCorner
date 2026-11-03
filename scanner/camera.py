"""Camera: opens the webcam (Media Foundation, DirectShow, AVFoundation) or the phone, reads frames in its own thread
and keeps the newest ones for the scanner (moved out of app.py, unchanged)."""
import collections
import logging
import sys
import threading
import time

import cv2

from system.i18n import tr

log = logging.getLogger("booster")


def camera_names():
    if sys.platform == "darwin":
        # AVFoundation gives us no device names via OpenCV - try the indices in order
        names = []
        for i in range(10):
            cap = cv2.VideoCapture(i, cv2.CAP_AVFOUNDATION)
            ok = cap.isOpened()
            cap.release()
            if not ok:
                break
            names.append(tr(f"Camera {i}"))
        return names or [tr("Camera 0")]
    try:
        from pygrabber.dshow_graph import FilterGraph
        return FilterGraph().get_input_devices()
    except Exception:
        return [tr(f"Camera {i}") for i in range(4)]


# ---------- Camera ----------
def _fourcc(v):
    v = int(v)
    return "".join(chr((v >> 8 * i) & 0xFF) for i in range(4)).strip(chr(0)) or "?"


class Camera:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame, self.seq = None, 0
        self.recent = collections.deque(maxlen=6)  # recent frames (text recognition takes the sharpest)
        self.thread, self.running = None, False
        self.mirror = False   # mirror horizontally
        self.flip_v = False   # mirror vertically
        self.message = tr("No camera selected")
        self.size = None           # (width, height) the camera actually delivers
        self.fps = None            # measured frame rate
        self.want_dialog = False   # open the driver dialog (focus, exposure …) in the camera thread
        self.dialog_error = ""     # the driver dialog failed: a quiet note for the window (scan_ctl shows it once)
        self.want_w = None         # the width asked for: a camera delivering far more is scaled down (_put)
        self.phone_starter = None  # starts the phone server (MainWindow.phone_start)

    @property
    def warning(self):
        """Hint when the camera only delivers a low resolution (then recognition can hardly read anything)."""
        if getattr(self, "index", None) == self.PHONE:   # phone: the phone determines size/portrait orientation
            return ""
        if self.fps and self.fps < 12 and self.size and self.size[0] >= 1280:
            return tr(f"Camera delivers only {self.fps:.0f} frames/s – make the room brighter or pick a lower resolution (1280×720) under Settings → Camera.")
        if self.size and self.size[0] < 1280:
            return tr(f"Camera only delivers {self.size[0]}×{self.size[1]} – is it still open in another program (e.g. Logitech software, OBS)? Close it and click ↻ in Settings.")
        return ""

    def open_dialog(self):
        self.want_dialog = True

    def start(self, index, width, height):
        self.stop()
        self.index = index
        self.want_w = width
        self.message = tr("Opening camera …")
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(index, width, height), daemon=True)
        self.thread.start()

    def sleep(self):
        """Camera off without waiting (the camera thread stops on its own and releases the device)."""
        self.running = False
        with self.lock:
            self.frame = None
            self.recent.clear()
        self.message = tr("Camera is resting – it comes back as soon as you open the scan page …")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
            self.thread = None
        with self.lock:
            self.frame = None
            self.recent.clear()
        self.size, self.fps = None, None

    def latest(self):
        with self.lock:
            return self.frame, self.seq

    def recent_frames(self):
        """-> [(seq, frame)] of the recent frames, newest last."""
        with self.lock:
            return list(self.recent)

    def _put(self, frame):
        w = frame.shape[1]
        if self.want_w and w > self.want_w * 1.25:   # e.g. 4K left on after the studio: recognition needs no more
            frame = cv2.resize(frame, (self.want_w, round(frame.shape[0] * self.want_w / w)), interpolation=cv2.INTER_AREA)
        size = (frame.shape[1], frame.shape[0])
        if size != self.size:
            self.size = size
        if self.mirror and self.flip_v:
            frame = cv2.flip(frame, -1)  # both = rotated by 180°
        elif self.mirror:
            frame = cv2.flip(frame, 1)   # horizontal (left/right)
        elif self.flip_v:
            frame = cv2.flip(frame, 0)   # vertical (top/bottom)
        with self.lock:
            self.frame, self.seq = frame, self.seq + 1
            self.recent.append((self.seq, frame))

    PHONE = "phone"   # camera choice: the phone on Wi-Fi (phonecam.py)

    def _run_phone(self, alive):
        """Phone as camera: frames come via Wi-Fi (phonecam); no new frame for 5 s -> scan view shows the QR code."""
        from scanner import phonecam
        last = -1
        if not phonecam.running() and self.phone_starter is not None:   # server only once the phone camera runs
            self.phone_starter()
        self.message = tr("Connect your phone: scan the QR code with it (same Wi-Fi)")
        while alive():
            frame, seq, t = phonecam.latest()
            if frame is not None and seq != last:
                last = seq
                self._put(frame)
                self.message = ""
            elif time.time() - t > 5:
                with self.lock:
                    self.frame = None
                self.message = tr("Connect your phone: scan the QR code with it (same Wi-Fi)")
            time.sleep(0.02)

    def _run(self, index, width, height):
        # OpenCV first (resolution adjustable), otherwise DirectShow directly:
        # some drivers (e.g. OM Webcam Beta, I420 only) can't be opened by OpenCV.
        me = threading.current_thread()
        alive = lambda: self.running and self.thread is me  # noqa: E731  (old thread stops after a camera switch)
        if index == self.PHONE:
            self._run_phone(alive)
            return
        if sys.platform == "darwin":
            log.info("Camera %s: opening via AVFoundation", index)
            # On the very first access macOS asks the user for camera permission (TCC) - AVFoundation can't
            # complete this prompt from a background thread ("can not spin main run loop from other
            # thread") while the dialog is open. Wait for a few attempts instead of giving up immediately.
            for attempt in range(1, 6):
                if not alive():
                    break
                if self._run_avfoundation(index, width, height, alive):
                    break
                self.message = tr(f"Camera can't be opened yet, retrying ({attempt}/5) …")
                for _ in range(20):
                    if alive():
                        time.sleep(0.1)
            else:
                self.message = tr("Camera can't be opened. Allow access under System Settings → Privacy & Security → Camera, or is another program using it (OBS, Discord)? Then click ↻ in Settings.")
            log.info("Camera %s: stopped (%s)", index, self.message)
            return
        log.info("Camera %s: opening via OpenCV", index)
        if not self._run_opencv(index, width, height, alive):
            # After another program releases it, the OM driver sometimes needs a few seconds
            for attempt in range(1, 6):
                if not alive():
                    break
                log.info("Camera %s: DirectShow directly, attempt %s", index, attempt)
                if self._run_dshow(index, alive, width, height):
                    break
                self.message = tr(f"Camera can't be opened yet, retrying ({attempt}/5) …")
                for _ in range(20):
                    if alive():
                        time.sleep(0.1)
            else:
                self.message = (tr("Camera can't be opened. Is another program using it (OBS, Discord, OM Capture)? Then click ↻ in Settings."))
        log.info("Camera %s: stopped (%s)", index, self.message)

    def _run_opencv(self, index, width, height, alive):
        """False if the camera never delivered a frame this way."""
        cap = self._open_msmf(index, width, height) or self._open_mjpg(index, width, height)
        if cap is None:
            return False
        fails, streamed = 0, False
        t0, n = None, 0
        while alive():
            ok, frame = cap.read()
            if not ok:
                fails += 1
                if fails > 60:
                    if not streamed:
                        cap.release()
                        return False
                    self.message = tr("Camera delivers no image. Is another program using it?")
                    with self.lock:
                        self.frame = None
                time.sleep(0.02)
                continue
            if not streamed:
                log.info("Camera %s: OpenCV delivers %sx%s %s", index, frame.shape[1], frame.shape[0],
                         _fourcc(cap.get(cv2.CAP_PROP_FOURCC)))
                if frame.shape[1] > width * 1.25:   # far more than asked: ask once more (else _put scales down)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    log.info("Camera %s: asked again for %sx%s (scaled down until then)", index, width, height)
            if t0 is None:
                t0 = time.monotonic()
            n += 1
            if n == 90:  # measure the real frame rate once (camera warning on stutter)
                self.fps = 89 / max(0.001, time.monotonic() - t0)
                log.info("Camera %s: %.1f fps", index, self.fps)
            fails, streamed = 0, True
            self._put(frame)
            if self.want_dialog:  # the camera's driver dialog (focus, exposure, sharpness …)
                self.want_dialog = False
                if cap.getBackendName() == "DSHOW":
                    cap.set(cv2.CAP_PROP_SETTINGS, 1)
                else:
                    threading.Thread(target=self._driver_dialog, args=(index,), daemon=True).start()
        cap.release()
        return True

    def _driver_dialog(self, index):
        """Settings dialog of the camera driver (also works while Media Foundation delivers the image) – in its own
        thread with its own COM; every COM object it made stays in camctl's keep (never garbage in another thread),
        a failure is a quiet note, never a crash."""
        import comtypes
        from scanner import camctl
        g = dev = None
        comtypes.CoInitialize()
        try:
            from pygrabber.dshow_graph import FilterGraph, show_properties
            g = FilterGraph()
            g.add_video_input_device(index)
            dev = g.get_input_device()
            show_properties(dev.instance)
        except Exception as e:
            log.info("Camera dialog: %s", e)
            self.dialog_error = tr("The camera's own settings window didn't open (the driver refused). "
                                   "The image controls still work.")
        finally:
            camctl.keep(g, dev)
            g = dev = None
            comtypes.CoUninitialize()

    @staticmethod
    def _open_msmf(index, width, height):
        """Open via Media Foundation – delivers webcams like the Logitech C922 in Full HD at 30 fps
        (MJPG doesn't work there via DirectShow: then only 640×480 or Full HD at ~5 fps)."""
        try:
            # Media Foundation only knows real cameras (no virtual ones like OBS) and counts differently -> by name
            from cv2_enumerate_cameras import enumerate_cameras
            names = camera_names()
            name = names[index] if index < len(names) else None
            same = [c for c in enumerate_cameras(cv2.CAP_MSMF) if c.name == name]
            nth = names[:index + 1].count(name) - 1  # several identical cameras
            if not name or nth >= len(same):
                return None
            cap = cv2.VideoCapture(same[nth].index, cv2.CAP_MSMF)
            if not cap.isOpened():
                return None
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, 30)
            ok, frame = cap.read()
            if not ok:
                cap.release()
                return None
            log.info("Camera %s: Media Foundation %sx%s", index, frame.shape[1], frame.shape[0])
            return cap
        except Exception as e:
            log.info("Camera %s: Media Foundation not working: %s", index, e)
            return None

    @staticmethod
    def _open_mjpg(index, width, height):
        """Open the camera with MJPG. Without MJPG webcams deliver Full HD at only ~5 fps (uncompressed) – in the dark
        even less and blurry. Depending on the driver, MJPG only takes effect in a certain order."""
        cap = None
        for order in ("vor", "nach", "beide"):
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                return None
            mjpg = cv2.VideoWriter_fourcc(*"MJPG")
            if order in ("vor", "beide"):
                cap.set(cv2.CAP_PROP_FOURCC, mjpg)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            if order in ("nach", "beide"):
                cap.set(cv2.CAP_PROP_FOURCC, mjpg)
            cap.set(cv2.CAP_PROP_FPS, 30)
            got = _fourcc(cap.get(cv2.CAP_PROP_FOURCC))
            log.info("Camera %s: format %s (MJPG %s size)", index, got, order)
            if got == "MJPG":
                return cap
            cap.release()
        return cv2.VideoCapture(index, cv2.CAP_DSHOW) if cap is not None else None

    def _run_dshow(self, index, alive, width=1920, height=1080):
        """False if the camera doesn't start (then try again)."""
        import comtypes
        comtypes.CoInitialize()
        graph, streamed = None, False
        try:
            from pygrabber.dshow_graph import FilterGraph
            got, box = threading.Event(), {}

            def on_frame(img):
                box["img"] = img.copy()
                got.set()

            graph = FilterGraph()
            graph.add_video_input_device(index)
            try:  # pick the desired resolution (otherwise DirectShow mostly delivers only 640×480)
                inp = graph.get_input_device()
                fmts = inp.get_formats()
                exact = [f for f in fmts if f["width"] == width and f["height"] == height]
                pick = exact or sorted(fmts, key=lambda f: f["width"] * f["height"])[-1:]
                if pick:
                    best = max(pick, key=lambda f: (f["media_type_str"] == "MJPG", f["max_framerate"]))
                    inp.set_format(best["index"])
                    log.info("Camera %s: DirectShow format %sx%s %s", index, best["width"], best["height"],
                             best["media_type_str"])
            except Exception as e:
                log.info("Camera %s: format not selectable: %s", index, e)
            graph.add_sample_grabber(on_frame)
            graph.add_null_render()
            graph.prepare_preview_graph()
            graph.run()
            fails = 0
            while alive():
                got.clear()
                graph.grab_frame()
                if got.wait(1.0):
                    if not streamed or fails:
                        log.info("Camera %s: DirectShow delivers %sx%s", index, box["img"].shape[1], box["img"].shape[0])
                    fails, streamed = 0, True
                    self._put(box["img"])
                    if self.want_dialog:
                        self.want_dialog = False
                        try:
                            from pygrabber.dshow_graph import show_properties
                            show_properties(graph.get_input_device().instance)
                        except Exception as e:
                            log.info("Camera dialog: %s", e)
                            self.dialog_error = tr("The camera's own settings window didn't open (the driver "
                                                   "refused). The image controls still work.")
                else:
                    fails += 1
                    if fails > 3:
                        self.message = tr("Camera delivers no image. Is it switched on and in webcam mode?")
                        with self.lock:
                            self.frame = None
        except Exception as e:
            log.warning("Camera %s: DirectShow error: %s", index, e)
        finally:
            if graph is not None:
                try:
                    graph.stop()
                except Exception:
                    pass
            from scanner import camctl
            camctl.keep(graph)   # never garbage in another thread (see camctl.keep)
            del graph
            comtypes.CoUninitialize()
        return streamed or not alive()

    def _run_avfoundation(self, index, width, height, alive):
        """macOS: open the camera via AVFoundation and read frames until alive() turns false.

        No equivalent to the DirectShow controls (camctl.py) or the driver dialog – neither exists like that under
        AVFoundation, so "Image controls …" shows the "no controls" hint and "Driver dialog …" has
        no effect (see want_dialog below)."""
        cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
        if not cap.isOpened():
            cap.release()
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 30)
        fails, streamed = 0, False
        t0, n = None, 0
        while alive():
            ok, frame = cap.read()
            if not ok:
                fails += 1
                if fails > 60:
                    if not streamed:
                        cap.release()
                        return False
                    self.message = tr("Camera delivers no image. Is another program using it?")
                    with self.lock:
                        self.frame = None
                time.sleep(0.02)
                continue
            if not streamed:
                log.info("Camera %s: AVFoundation delivers %sx%s", index, frame.shape[1], frame.shape[0])
            if t0 is None:
                t0 = time.monotonic()
            n += 1
            if n == 90:
                self.fps = 89 / max(0.001, time.monotonic() - t0)
                log.info("Camera %s: %.1f fps", index, self.fps)
            fails, streamed = 0, True
            self._put(frame)
            if self.want_dialog:  # no driver dialog under AVFoundation
                self.want_dialog = False
                log.info("Camera %s: no driver dialog on macOS", index)
        cap.release()
        return streamed
