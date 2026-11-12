"""The PC reads the phone's pairing sphere with its webcam (net/sync_cam.py, lead/legal 07.11.): the code is read from
the turning sphere; the frames stay in memory – nothing is written to a file; the camera stops by itself after the
time is up; no frames -> no_camera.

    python -m unittest tests/test_sync_cam.py
"""
import builtins
import threading
import unittest
from unittest import mock

import numpy as np

from net import pairing, sync_cam
from ui import sphere


class FakeCamera:
    """Frames of a turning sphere (ui/sphere.py), off centre in a 640 × 480 picture, at 30 frames a second of the
    fake clock."""

    def __init__(self, frames, clock):
        self.frames, self.clock, self.started, self.stopped = frames, clock, False, False

    def start(self, index, width, height):
        self.started = True

    def stop(self):
        self.stopped = True

    def latest(self):
        if not self.frames:
            return None, 0
        k = int(self.clock.t * 30)
        big = np.full((480, 640), 40, np.uint8)
        big[90:390, 300:600] = self.frames[k % len(self.frames)]
        return big, k + 1


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 1 / 30   # each look at the clock: the next frame
        return self.t


class Cam(unittest.TestCase):
    def run_cam(self, frames, stop_s=None):
        clock = Clock()
        cam = FakeCamera(frames, clock)
        got, ends, previews = [], [], []
        done = threading.Event()
        sc = sync_cam.SphereCam(0, previews.append, got.append, lambda why: (ends.append(why), done.set()),
                                camera=cam, clock=clock)
        with mock.patch.object(sync_cam, "STOP_S", stop_s or sync_cam.STOP_S):
            sc.start()
            self.assertTrue(done.wait(300))
        return got, ends, previews, cam

    def test_reads_the_code_in_memory_only(self):
        code = pairing.new_code()
        frames = sphere.frames(pairing.picture_bytes(code), n=120, size=300)
        real_open = builtins.open

        def no_write(file, mode="r", *a, **k):
            if any(c in str(mode) for c in "wax+"):
                raise AssertionError(f"a file was written: {file}")
            return real_open(file, mode, *a, **k)
        with mock.patch.object(builtins, "open", no_write), \
                mock.patch("cv2.imwrite", side_effect=AssertionError("no picture to disk")):
            got, ends, previews, cam = self.run_cam(frames)
        self.assertEqual(got, [code])
        self.assertEqual(ends, ["found"])
        self.assertTrue(previews and previews[0].ndim == 2)
        self.assertTrue(cam.stopped, "the camera is released")

    def test_time_is_up(self):
        frames = [np.full((300, 300), 24, np.uint8)] * 4   # a camera that sees no sphere
        got, ends, _p, cam = self.run_cam(frames, stop_s=2)
        self.assertEqual((got, ends, cam.stopped), ([], ["stopped"], True))

    def test_no_camera(self):
        got, ends, _p, cam = self.run_cam([])
        self.assertEqual((got, ends), ([], ["no_camera"]))



class ScanCamera(unittest.TestCase):
    def test_the_scan_cameras_name_gives_its_index(self):
        """The settings keep the scan camera's NAME – „Kugel lesen“ without a device must not crash (07.11. find)."""
        from net import sync_ctl
        from scanner import camera
        ctl = type("C", (), {})()
        with mock.patch.object(camera, "camera_names", lambda: ["Front", "Integrierte Webcam"]):
            ctl.settings = {"camera": "Integrierte Webcam"}
            self.assertEqual(sync_ctl.SyncControl._scan_camera_index(ctl), 1)
            ctl.settings = {"camera": "gone"}
            self.assertEqual(sync_ctl.SyncControl._scan_camera_index(ctl), 0)
            ctl.settings = {}
            self.assertEqual(sync_ctl.SyncControl._scan_camera_index(ctl), 0)

if __name__ == "__main__":
    unittest.main()
