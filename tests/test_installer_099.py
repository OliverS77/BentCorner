"""Installer 0.9.9 (library's setup plan; Oliver/Gordon/lead/legal 13.11.2026), the Inno side and the program's answer to
the uninstaller. Reads installer/bentcorner.iss as text (compiling it needs Inno – tools/make_dist.py) and runs the
program's `--forget-server --check` logic on stand-ins. No network.

    python -m unittest tests.test_installer_099
"""
import json
import os
import re
import pathlib
import tempfile
import unittest
from unittest import mock

from net import forget

ISS = pathlib.Path(__file__).resolve().parents[1] / "installer" / "bentcorner.iss"


GERMAN_ISL = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "Languages" / "German.isl"
SIE = re.compile(r"\b(Sie|Ihr|Ihre|Ihrem|Ihren|Ihrer|Ihnen)\b")


class Texts(unittest.TestCase):
    """Gordon 14.11.2026: German always "du", less text, no Ready page."""

    def setUp(self):
        self.s = ISS.read_text("utf-8-sig")
        self.msgs = dict(re.findall(r"^(de\.\w+|en\.\w+)=(.*)$", self.s, re.M))

    def test_no_sie_in_our_german_texts(self):
        for k, v in self.msgs.items():
            if k.startswith("de."):
                self.assertIsNone(SIE.search(v), f"{k}={v}")

    @unittest.skipUnless(GERMAN_ISL.exists(), "Inno Setup's German.isl (only on a PC with Inno)")
    def test_every_sie_text_of_inno_is_replaced(self):
        for line in GERMAN_ISL.read_text("utf-8-sig", errors="replace").splitlines():
            m = re.match(r"^(\w+)=(.*)$", line)
            if m and SIE.search(m.group(2)):
                self.assertIn("de." + m.group(1), self.msgs, f"{m.group(1)} still says Sie")

    def test_one_line_pages_and_no_ready_page(self):
        self.assertIn("DisableReadyPage=yes", self.s)
        for lang, line, done in (("de", "Installiert [name/ver] auf deinem PC.", "[name] ist installiert."),
                                 ("en", "Installs [name/ver] on your PC.", "[name] is installed.")):
            self.assertEqual(self.msgs[f"{lang}.WelcomeLabel2"], line)
            self.assertEqual(self.msgs[f"{lang}.FinishedHeadingLabel"], done)
            for empty in ("ClickNext", "SelectTasksLabel2", "SelectTasksDesc", "FinishedLabel", "FinishedLabelNoIcons",
                          "ClickFinish"):
                self.assertEqual(self.msgs[f"{lang}.{empty}"], "", empty)
        self.assertNotIn("GroupDescription", self.s)
        # the page before installing says "Installieren" (Inno renames only its own pages)
        self.assertIn("WizardForm.NextButton.Caption := SetupMessage(msgButtonInstall);", self.s)
        self.assertIn("HomePage.Edits[0].OnChange := @HomeEditChange;", self.s)


class Script(unittest.TestCase):
    def setUp(self):
        self.s = ISS.read_text("utf-8-sig")

    def test_dark_and_language_first(self):
        self.assertIn("WizardStyle=modern dark", self.s)   # always dark, like the app (Oliver 13.11.)
        self.assertIn("ShowLanguageDialog=yes", self.s)
        self.assertIn("DisableWelcomePage=no", self.s)   # welcome page with the brand mark (Gordon 14.11.)

    def test_desktop_shortcut_ticked(self):
        line = next(l for l in self.s.splitlines() if l.startswith('Name: "desktopicon"'))
        self.assertNotIn("unchecked", line)

    def test_storage_page_only_for_a_new_installation(self):
        self.assertIn("datenordner.json", self.s)
        self.assertIn("if not NewInstall then Exit;", self.s)
        self.assertIn("{localappdata}\\BentCorner')", self.s)   # no subfolder (Oliver/Gordon 13.11.)
        self.assertIn("installer.json", self.s)
        self.assertIn("SaveStringsToUTF8FileWithoutBOM(", self.s)   # library 13.11.: non-ANSI user names arrive intact
        self.assertNotIn("SaveStringToFile(", self.s)
        self.assertIn("(HomePage = nil) then Exit;", self.s)   # existing users: no installer.json
        self.assertNotIn("MsgBox(CustomMessage('HomeInApp')", self.s)   # the note sits on the page, no pop-up
        for lang in ("de", "en"):
            self.assertIn(f"{lang}.HomeLine=", self.s)

    def test_uninstaller_checkbox_always_unticked(self):
        self.assertIn("ServerBox.Checked := False;", self.s)
        self.assertNotIn("ServerBox.Checked := True;", self.s)

    def test_legal_texts_verbatim(self):
        self.assertIn("de.ForgetGuard=Du hast einen Schutz-Code. Deine Daten auf dem Server löschst du in der App mit "
                      "„Alles löschen, auch online“ – vor dem Deinstallieren.", self.s)
        self.assertIn("Nutzt du sie nicht mehr, löschen wir die Online-Sicherung nach 183 Tagen und die ID nach 365 Tagen.",
                      self.s)
        self.assertIn("Sofort und für alle deine Geräte.", self.s)
        self.assertIn("else if Mode = 12 then", self.s)


class Check(unittest.TestCase):
    """`BentCorner.exe --forget-server --check`: 12 when a protection code is set (the uninstaller has no code)."""

    def run_check(self, settings, full=True, meta=None):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            (home / "settings.json").write_text(json.dumps(settings), "utf-8")
            if meta is not None:
                (home / "sync").mkdir()
                (home / "sync" / "meta.json").write_text(json.dumps(meta), "utf-8")
            with mock.patch("system.datastore.SETTINGS", home / "settings.json"), \
                    mock.patch("system.datahome.HOME", home), \
                    mock.patch.object(forget, "available", lambda s: full), \
                    mock.patch("sys.argv", ["BentCorner.exe", "--forget-server", "--check"]):
                with self.assertRaises(SystemExit) as end:
                    forget.main()
        return end.exception.code

    def test_codes(self):
        ident = {"relay": {"seed": "AAAA", "registered": "https://bentcorner.app"}}
        self.assertEqual(self.run_check({}), forget.EXIT[forget.NO_ID])
        self.assertEqual(self.run_check(ident), forget.CHECK_FULL)
        self.assertEqual(self.run_check(ident, full=False), forget.CHECK_SHARED)
        guarded = {"relay": dict(ident["relay"], guard_salt="S" * 24)}
        self.assertEqual(self.run_check(guarded), forget.CHECK_GUARD)
        self.assertEqual(self.run_check(ident, meta={"guard": True}), forget.CHECK_GUARD)   # only the sync state knows it
        self.assertEqual(self.run_check(guarded, full=False), forget.CHECK_SHARED)   # old box: lists and binders only
        self.assertEqual(forget.CHECK_GUARD, 12)


if __name__ == "__main__":
    unittest.main()
