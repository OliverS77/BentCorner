"""What the scanner is doing right now (line under the scan frame): the code of an AI frame (Recognizer._stage_of)
and the calm display in the scan page backend (shown only after STAGE_AFTER, kept STAGE_HOLD, "counted" at once).

    python -m unittest tests/test_scan_stage.py
"""
import types
import unittest
from unittest import mock

from scanner.recognizer import STAGES, Recognizer, stage_text


class StageOf(unittest.TestCase):
    def test_codes(self):
        of = Recognizer._stage_of
        self.assertEqual(of({"how": "SCAN° fingerprint (0.9) + image match (80)"}, "Bolt", True), "counted")
        self.assertEqual(of({"how": "Loading reference images …"}, None, False), "loading_refs")
        self.assertEqual(of({"how": "Image match close, fingerprint disagrees"}, None, False), "comparing")
        self.assertEqual(of({"how": "Checking a similar print …"}, None, False), "comparing")
        self.assertEqual(of({"how": "Reading the collector line …", "footer": True}, None, False), "reading_line")
        self.assertEqual(of({"how": ""}, None, False), "searching")

    def test_every_code_has_a_text(self):
        for code in STAGES:
            self.assertTrue(stage_text(code))
        self.assertEqual(stage_text("nonsense"), "")


class CalmLine(unittest.TestCase):
    """ScanBackend._stage_tick without Qt widgets: a fake controller, the clock moved by hand."""

    def tick(self, code, t):
        from ui import qscan
        with mock.patch.object(qscan.time, "monotonic", lambda: t):
            self.rec.stage = code
            qscan.ScanBackend._stage_tick(self.b)
        return self.b._stage["shown"]

    def setUp(self):
        self.rec = types.SimpleNamespace(stage="", sleeping=False)
        zone = mock.Mock()
        zone.getRect.return_value = (0, 0, 10, 14)
        self.ctrl = types.SimpleNamespace(recognizer=self.rec, frame_rgb=object())   # a camera image is there
        self.b = types.SimpleNamespace(ctrl=self.ctrl,
                                       view=types.SimpleNamespace(zone_in_view=lambda: zone),
                                       _stage={"shown": "", "at": 0.0, "cand": "", "since": 0.0, "zone": None},
                                       stageChanged=mock.Mock(), STAGE_AFTER=0.3, STAGE_HOLD=0.6)

    def test_short_stages_never_show(self):
        self.assertEqual(self.tick("idle", 10.0), "")
        self.assertEqual(self.tick("idle", 10.4), "idle")
        self.assertEqual(self.tick("searching", 10.5), "idle")   # 0.1 s – not yet
        self.assertEqual(self.tick("comparing", 10.6), "idle")   # changed again – starts over
        self.assertEqual(self.tick("comparing", 10.95), "idle")  # 0.35 s, but "idle" was shown < 0.6 s ago
        self.assertEqual(self.tick("comparing", 11.05), "comparing")

    def test_counted_at_once(self):
        self.tick("searching", 1.0)
        self.tick("searching", 1.4)
        self.assertEqual(self.tick("counted", 1.45), "counted")

    def test_signal_only_on_change(self):
        self.tick("idle", 1.0)
        self.tick("idle", 1.4)
        n = self.b.stageChanged.call_count
        for t in (1.5, 1.6, 1.7):
            self.tick("idle", t)
        self.assertEqual(self.b.stageChanged.call_count, n)

    def test_no_camera_image_shows_nothing(self):   # the scanner isn't working at all – no "loading …" forever
        self.ctrl.frame_rgb = None
        self.tick("loading", 1.0)
        self.assertEqual(self.tick("loading", 2.0), "")

    def test_sleeping_scanner_shows_nothing(self):
        self.tick("idle", 1.0)
        self.tick("idle", 1.4)
        self.rec.sleeping = True
        self.tick("idle", 2.1)
        self.assertEqual(self.tick("idle", 2.5), "")


if __name__ == "__main__":
    unittest.main()
