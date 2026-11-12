"""Slim build (lead, after 0.9.7.50): one list (tools/build_launcher.SKIP) leaves out what the app never uses – the
onedir folder is pruned right after PyInstaller, starter/app-stage skip it, tools/check_package.py stops the build when
a package update brings it back. Here: the list hits exactly the planned files, keeps what the app needs, and prune /
check_package work on folders and ZIPs.

    python -m unittest tests/test_slim_build.py
"""
import pathlib
import re
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import build_launcher  # noqa: E402
import check_package  # noqa: E402

ID = "0.9.7.51-2611070000"
GONE = [
    "PySide6/qml/QtQuick/Controls/Basic/Button.qml",
    "PySide6/qml/QtQuick/Dialogs/qmldir",
    "PySide6/qml/QtQuick/Layouts/qquicklayoutsplugin.dll",
    "PySide6/qml/QtQuick/Templates/qmldir",
    "PySide6/qml/QtQuick/NativeStyle/qmldir",
    "PySide6/qml/Qt/labs/platform/qmldir",
    "PySide6/Qt6QuickControls2.dll",
    "PySide6/Qt6QuickControls2FluentWinUI3StyleImpl.dll",
    "PySide6/Qt6QuickTemplates2.dll",
    "PySide6/Qt6QuickDialogs2QuickImpl.dll",
    "PySide6/Qt6QuickLayouts.dll",
    "PySide6/Qt6LabsStyleKit.dll",
    "PySide6/translations/qt_de.qm",
    "PySide6/translations/qtdeclarative_de.qm",
    "PySide6/translations/qtbase_fr.qm",
    "PySide6/translations/qt_help_de.qm",
    "PIL/_avif.cp312-win_amd64.pyd",
    "cv2/opencv_videoio_ffmpeg4140_64.dll",
    "PySide6/Qt6QuickTimeline.dll",
    "PySide6/qml/QtQuick/VirtualKeyboard/qmldir",
]
KEPT = [
    "BentCorner.exe",
    "PySide6/translations/qtbase_de.qm",        # system/startup.py: Qt's own texts in German
    "PySide6/Qt6OpenGL.dll",                    # Qt6Quick.dll imports it
    "PySide6/QtOpenGL.pyd",                     # PySide6.QtQuick imports PySide6.QtOpenGL when it loads
    "PySide6/opengl32sw.dll",                   # software OpenGL for VMs/RDP/old drivers
    "PySide6/Qt6Quick.dll",
    "PySide6/Qt6QuickWidgets.dll",
    "PySide6/QtQuickWidgets.pyd",
    "PySide6/Qt6QuickEffects.dll",
    "PySide6/Qt6QuickShapes.dll",
    "PySide6/qml/QtQuick/Effects/effectsplugin.dll",
    "PySide6/qml/QtQuick/Shapes/qmldir",
    "PySide6/qml/QtQuick/Window/qmldir",
    "PySide6/qml/QtQuick/qtquick2plugin.dll",
    "PIL/_imaging.cp312-win_amd64.pyd",
    "PIL/_webp.cp312-win_amd64.pyd",
    "cv2/cv2.pyd",
    "models/dinov2-small-fp16.onnx",            # the GPU path (scanner/fingerprint.py)
    "models/dinov2-small-q.onnx",
    "scan-bench/cards.json",                    # --selftest-scan (system/selftest.py)
    "licenses/LGPL-2.1.txt",                    # still GEOS
]


def skipped(rel):
    return bool(re.search("^" + re.escape(ID) + build_launcher.SKIP, f"{ID}/{rel}"))


class SkipList(unittest.TestCase):
    def test_planned_parts_are_left_out(self):
        self.assertEqual([r for r in GONE if not skipped(r)], [])

    def test_what_the_app_needs_stays(self):
        self.assertEqual([r for r in KEPT if skipped(r)], [])

    def test_no_import_of_a_left_out_module(self):
        """qml/ imports only QtQuick, .Effects, .Shapes, .Window; no Qt Quick Controls style in Python – else the list is wrong."""
        root = pathlib.Path(__file__).resolve().parents[1]
        for f in (root / "qml").rglob("*.qml"):
            text = f.read_text("utf-8")
            self.assertIsNone(re.search(r"^\s*import\s+(QtQuick\.(Controls|Dialogs|Layouts|Templates)|Qt\.labs)\b",
                                        text, re.M), f)
        for pkg in ("ui", "system", "scanner", "cards", "collection", "net", "games"):
            for f in (root / pkg).rglob("*.py"):
                text = f.read_text("utf-8")
                self.assertNotRegex(text, r"QQuickStyle|QtQuickControls2", str(f))
                self.assertNotRegex(text, r"VideoCapture\(\s*['\"fr]|VideoWriter\(|CAP_FFMPEG", str(f))


class Prune(unittest.TestCase):
    def test_prune_deletes_only_the_list_and_empty_folders(self):
        with tempfile.TemporaryDirectory() as d:
            app = pathlib.Path(d)
            for rel in GONE + KEPT:
                p = app / ID / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"x" * 10)
            n, size = build_launcher.prune(app)
            self.assertEqual((n, size), (len(GONE), 10 * len(GONE)))
            left = sorted(p.relative_to(app / ID).as_posix() for p in app.rglob("*") if p.is_file())
            self.assertEqual(left, sorted(KEPT))
            self.assertFalse((app / ID / "PySide6/qml/QtQuick/Controls").exists())
            self.assertFalse((app / ID / "PySide6/qml/Qt").exists())


class CheckPackage(unittest.TestCase):
    def _zip(self, d, names):
        z = pathlib.Path(d) / "BentCorner-0.9.7.51-portable.zip"
        with zipfile.ZipFile(z, "w") as f:
            for n in names:
                f.writestr("Bent°Corner/" + n, b"x" * 1000)
        return z

    def test_slim_zip_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            z = self._zip(d, [f"{ID}/{r}" for r in KEPT])
            self.assertEqual(check_package.slim_entries(z), [])
            self.assertEqual(check_package.forbidden_entries(z), [])
            self.assertAlmostEqual(check_package.size_mb(z), len(KEPT) / 1000)

    def test_parts_coming_back_are_found_in_zip_and_folder(self):
        with tempfile.TemporaryDirectory() as d:
            z = self._zip(d, [f"{ID}/{r}" for r in KEPT + ["cv2/opencv_videoio_ffmpeg4150_64.dll",
                                                           "PySide6/Qt6QuickControls2Material.dll"]])
            self.assertEqual(len(check_package.slim_entries(z)), 2)
            stage = pathlib.Path(d) / "app-stage"
            p = stage / ID / "PySide6" / "translations" / "qtbase_fr.qm"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"x")
            (stage / ID / "PySide6" / "translations" / "qtbase_de.qm").write_bytes(b"x")
            self.assertEqual(check_package.slim_entries(stage), [f"{ID}/PySide6/translations/qtbase_fr.qm"])


if __name__ == "__main__":
    unittest.main()
