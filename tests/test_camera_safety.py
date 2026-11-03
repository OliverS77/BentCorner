"""The camera never crashes the program and never runs bigger than needed (a tester's crash, 0.9.2: a COM object of
the camera dialog freed by the garbage collector in the recognizer's thread). Without a camera: the COM side is faked.

    python -m unittest tests/test_camera_safety.py
"""
import sys
import types
import unittest
from unittest import mock

import numpy as np

from scanner import camctl, camera


class DriverDialog(unittest.TestCase):
    def test_failing_dialog_leaves_no_garbage_and_a_note(self):
        """The driver refuses: its COM objects stay in camctl's keep (never garbage), a quiet note, no exception."""
        made = []

        class Graph:
            def __init__(self):
                self.me = self        # a reference cycle, like pygrabber's – it would wait for the garbage collector
                made.append(self)

            def add_video_input_device(self, i):
                pass

            def get_input_device(self):
                return types.SimpleNamespace(instance=object())

        def boom(_):
            raise OSError("[WinError -2147467259] Unbekannter Fehler")
        fake = types.ModuleType("pygrabber.dshow_graph")
        fake.FilterGraph, fake.show_properties = Graph, boom
        com = types.SimpleNamespace(CoInitialize=lambda: None, CoUninitialize=lambda: None)
        cam = camera.Camera.__new__(camera.Camera)
        cam.dialog_error = ""
        keep = len(camctl._KEEP)
        with mock.patch.dict(sys.modules, {"pygrabber": types.ModuleType("pygrabber"), "pygrabber.dshow_graph": fake,
                                           "comtypes": com}):
            cam._driver_dialog(0)
        self.assertTrue(cam.dialog_error)
        self.assertIn(made[0], camctl._KEEP[keep:])


class ControlsReadOnce(unittest.TestCase):
    def test_values_cached(self):
        """The controls window rebuilds often: the camera is asked once per value, then what was set is kept."""
        calls = []
        ctl = types.SimpleNamespace(Get=lambda prop: calls.append(prop) or (5, camctl.AUTO), Set=lambda *a: None)
        c = camctl.Controls.__new__(camctl.Controls)
        key, _, iface, prop = camctl.PROPS[0]
        c._if, c._vals = {iface: ctl}, {}
        c.ranges = {key: {"min": 0, "max": 10, "step": 1, "default": 5, "auto": True, "manual": True}}
        for _ in range(5):
            self.assertEqual(c.get(key), (5, True))
        self.assertEqual(len(calls), 1)
        c.set(key, 7)
        self.assertEqual(c.get(key), (7, False))
        self.assertEqual(len(calls), 1)
        c._graph = object()
        c.close()
        self.assertEqual((c._if, c.ranges), ({}, {}))


class NotBiggerThanAsked(unittest.TestCase):
    def test_4k_scaled_to_the_asked_width(self):
        cam = camera.Camera.__new__(camera.Camera)
        cam.mirror = cam.flip_v = False
        cam.size, cam.seq, cam.frame = None, 0, None
        cam.lock = mock.MagicMock()
        cam.recent = []
        cam.want_w = 1920
        cam._put(np.zeros((2160, 3840, 3), np.uint8))
        self.assertEqual(cam.size, (1920, 1080))
        cam.want_w = 3840   # the studio asks for the largest: it gets it
        cam._put(np.zeros((2160, 3840, 3), np.uint8))
        self.assertEqual(cam.size, (3840, 2160))
