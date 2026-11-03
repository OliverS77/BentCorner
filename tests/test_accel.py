"""Accelerator choice (scanner/accel.py) and the CPU fallback after a GPU crash (fingerprint.gpu_crashed):
- DirectML only from Windows' own DirectML.dll of version MIN_DML or newer, otherwise CPU with a reason in the log,
- a crash on the GPU ties the AI to the CPU – until an app update or another DirectML lifts it,
- the finished package must contain no DirectML.dll (tools/check_package.py, run by build.ps1).

    python -m unittest tests/test_accel.py
"""
import io
import json
import os
import pathlib
import struct
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

from scanner import accel
from scanner import fingerprint
from scanner import ocrscan

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import check_package  # noqa: E402


class Choice(unittest.TestCase):
    def setUp(self):
        accel._cache.clear()
        self.addCleanup(accel._cache.clear)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("BENTCORNER_NO_GPU", None)

    def _gpu(self, platform, providers, dml):
        import onnxruntime as ort
        with mock.patch.object(sys, "platform", platform), \
                mock.patch.object(ort, "get_available_providers", lambda: providers), \
                mock.patch.object(accel, "dml_version", lambda: dml), \
                mock.patch.object(accel, "log") as log:
            accel._cache.clear()
            res = accel.gpu()
            return res, [c.args[0] % c.args[1:] for c in log.info.call_args_list]

    def test_directml_from_the_minimum_version_on(self):
        (prov, _), _ = self._gpu("win32", [accel.DML, "CPUExecutionProvider"], accel.MIN_DML)
        self.assertEqual(prov, accel.DML)

    def test_older_directml_means_cpu_with_a_reason_in_the_log(self):
        (prov, why), logs = self._gpu("win32", [accel.DML, "CPUExecutionProvider"], (1, 14, 2))
        self.assertIsNone(prov)
        self.assertIn("DirectML 1.14.2 < 1.15.0", why)
        self.assertEqual(logs, ["AI on CPU: DirectML 1.14.2 < 1.15.0"])

    def test_no_directml_in_windows_means_cpu(self):
        (prov, why), _ = self._gpu("win32", [accel.DML, "CPUExecutionProvider"], None)
        self.assertIsNone(prov)
        self.assertIn("no DirectML", why)

    def test_coreml_on_the_mac_and_cpu_elsewhere(self):
        (prov, _), _ = self._gpu("darwin", [accel.COREML, "CPUExecutionProvider"], (1, 15, 6))
        self.assertEqual(prov, accel.COREML)
        (prov, _), _ = self._gpu("linux", ["CPUExecutionProvider"], (1, 15, 6))
        self.assertIsNone(prov)

    def test_ocr_on_the_gpu_only_with_directml(self):
        with mock.patch.object(accel, "provider", lambda: accel.COREML):
            self.assertFalse(accel.ocr_gpu())
        with mock.patch.object(accel, "provider", lambda: accel.DML):
            self.assertTrue(accel.ocr_gpu())

    def test_no_gpu_switch_is_not_cached(self):
        os.environ["BENTCORNER_NO_GPU"] = "1"
        self.assertIsNone(accel.provider())
        os.environ.pop("BENTCORNER_NO_GPU")
        accel._cache["gpu"] = (accel.DML, "")
        self.assertEqual(accel.provider(), accel.DML)

    def test_file_version_of_a_real_dll(self):
        if sys.platform != "win32":
            self.skipTest("Windows only")
        v = accel._file_version(pathlib.Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "kernel32.dll")
        self.assertIsInstance(v, tuple)
        self.assertGreaterEqual(v[0], 6)


class CrashMark(unittest.TestCase):
    """GPU crashed -> CPU only (choice file), lifted by an app update or another DirectML."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (mock.patch.object(fingerprint, "CHOICE_FILE", pathlib.Path(self.tmp.name) / "ai-device.json"),
                  mock.patch.object(accel, "key", lambda: "dml-1.15.6"),
                  mock.patch.object(fingerprint, "_crash_logged", [False]),
                  mock.patch.object(ocrscan, "_gpu_known", [])):
            p.start()
            self.addCleanup(p.stop)

    def test_crash_on_the_gpu_switches_to_the_cpu(self):
        fingerprint._save_choice(0)
        with self.assertLogs("booster", "WARNING") as logs:
            fingerprint.gpu_crashed("test")
        self.assertIn("GPU crashed (test)", "\n".join(logs.output))
        self.assertIsNone(fingerprint._load_choice())
        self.assertIn("test", json.loads(fingerprint.CHOICE_FILE.read_text("utf-8"))["crash"])
        self.assertEqual(ocrscan._gpu_known, [False])   # text recognition off the GPU as well
        self.assertEqual(fingerprint.backend, "CPU")

    def test_crash_while_measuring_counts_too(self):
        self.assertEqual(fingerprint._load_choice(), "?")   # not measured yet: the crash may come from the GPU
        fingerprint.gpu_crashed("measuring")
        self.assertIsNone(fingerprint._load_choice())

    def test_crash_on_the_cpu_changes_nothing(self):
        fingerprint._save_choice(None)
        fingerprint.gpu_crashed("other cause")
        self.assertNotIn("crash", json.loads(fingerprint.CHOICE_FILE.read_text("utf-8")))

    def test_app_update_lifts_the_mark(self):
        fingerprint._save_choice(0)
        fingerprint.gpu_crashed("test")
        with mock.patch("version.VERSION", "9.9.9.9"):
            self.assertEqual(fingerprint._load_choice(), "?")   # measured again

    def test_other_directml_lifts_the_mark(self):
        fingerprint._save_choice(0)
        fingerprint.gpu_crashed("test")
        with mock.patch.object(accel, "key", lambda: "dml-1.16.0"):
            self.assertEqual(fingerprint._load_choice(), "?")

    def test_marked_choice_is_logged_once_on_load(self):
        fingerprint._save_choice(None, crash="2026-10-31 test")
        with self.assertLogs("booster", "INFO") as logs:
            fingerprint._load_choice()
            fingerprint._load_choice()
        self.assertEqual(sum("GPU crashed earlier" in line for line in logs.output), 1)


class PackageCheck(unittest.TestCase):
    """tools/check_package.py reads the program zip behind the starter."""

    def _exe(self, names):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for n in names:
                z.writestr(n, b"x")
        data = buf.getvalue()
        f = tempfile.NamedTemporaryFile(suffix=".exe", delete=False)
        f.write(b"MZstarter" + data + struct.pack("<q", len(data)) + b"BCPAYLD1")
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_clean_package(self):
        self.assertEqual(check_package.forbidden_entries(self._exe(["0.9.7.4-1/onnxruntime/capi/onnxruntime.dll"])),
                         [])

    def test_directml_anywhere_is_found(self):
        exe = self._exe(["BentCorner.exe", "0.9.7.4-1/onnxruntime/capi/DirectML.dll", "0.9.7.4-1/x/directml.debug.dll"])
        self.assertEqual(len(check_package.forbidden_entries(exe)), 2)

    def test_unused_gpl_only_qt_modules_are_found(self):
        exe = self._exe(["0.9.7.5-1/PySide6/Qt6QuickTimeline.dll", "0.9.7.5-1/PySide6/Qt6QuickTimelineBlendTrees.dll",
                         "0.9.7.5-1/PySide6/qml/QtQuick/VirtualKeyboard/qmldir",
                         "0.9.7.5-1/PySide6/qml/QtQuick/Timeline/qtquicktimelineplugin.dll",
                         "0.9.7.5-1/PySide6/Qt6Quick.dll", "0.9.7.5-1/PySide6/qml/QtQuick/Shapes/qmldir"])
        self.assertEqual(len(check_package.forbidden_entries(exe)), 4)

    def test_not_a_package(self):
        f = tempfile.NamedTemporaryFile(suffix=".exe", delete=False)
        f.write(b"MZ" + b"\0" * 32)
        f.close()
        self.addCleanup(os.unlink, f.name)
        with self.assertRaises(ValueError):
            check_package.forbidden_entries(f.name)


if __name__ == "__main__":
    unittest.main()
