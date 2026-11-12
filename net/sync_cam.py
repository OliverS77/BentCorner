"""This PC reads the phone's pairing sphere with its webcam (PAIRING §2, lead 07.11.: Oliver wants it; the code is the
fallback). legal 07.11. (library's line „Das Kamerabild wird nur auf diesem PC ausgewertet …“): the frames are read
in memory only – never written to a file, no debug picture, nothing sent; only the code read goes on, as if typed.
The camera stops by itself: code read, stop() (the page left / Cancel), or STOP_S without a hit.

    cam = SphereCam(index, on_preview, on_found, on_end); cam.start(); … cam.stop()
      on_preview(gray uint8 image)   ~PREVIEW_FPS a second, for the page (the caller keeps it in memory only)
      on_found(code)                 the 10-character pairing code
      on_end(why)                    "stopped" (time is up) | "no_camera" | "found" | "off"
All callbacks run on the camera's thread – the caller hands them to the main thread.
"""
import threading
import time

STOP_S = 180          # 3 minutes without a hit: the camera goes off (library shows „[Kugel lesen]“ to start again)
PREVIEW_FPS = 8
READ_W = 640          # the reader works on a frame this wide (the sphere fills a part of it)


class SphereCam:
    def __init__(self, index, on_preview, on_found, on_end, camera=None, clock=time.monotonic):
        self.index = index
        self.on_preview, self.on_found, self.on_end = on_preview, on_found, on_end
        self._camera = camera
        self._clock = clock
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout=3)
        self.thread = None

    def _run(self):
        import cv2
        from net import pairing
        from net.spherelab import sphere as lab
        cam = self._camera
        if cam is None:
            from scanner.camera import Camera
            cam = Camera()   # its own instance: the scan camera rests outside the scan page
        why = "off"
        try:
            cam.start(self.index, 1280, 720)
            t0 = self._clock()
            reader = lab.Reader(lab.PERIOD)
            last, shown, got_any = 0, 0.0, False
            while self.running:
                now = self._clock() - t0
                if now > STOP_S:
                    why = "stopped"
                    break
                frame, seq = cam.latest()
                if frame is None or seq == last:
                    if not got_any and now > 8:
                        why = "no_camera"
                        break
                    time.sleep(0.01)
                    continue
                last, got_any = seq, True
                g = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if g.shape[1] > READ_W:
                    g = cv2.resize(g, (READ_W, round(g.shape[0] * READ_W / g.shape[1])), interpolation=cv2.INTER_AREA)
                if now - shown >= 1 / PREVIEW_FPS:
                    shown = now
                    self.on_preview(g)
                payload = reader.add(g, now)
                if payload is not None:
                    try:
                        code = pairing.code_of_picture(payload)
                    except pairing.PairError:
                        continue
                    why = "found"
                    self.on_found(code)
                    break
        finally:
            try:
                cam.stop()
            finally:
                self.running = False
                self.on_end(why)
