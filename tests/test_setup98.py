"""Leaner setup 0.9.8 (Oliver/Gordon/lead 13.11.2026): language → storage location (preset, [OK] or [Customise]; not
in a portable copy) → games → name → Orbit → done. Existing users never see it. Temp folders only.

    python -m unittest tests/test_setup98.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from system import datahome
from ui import onboarding


def _collection(folder):
    (folder / "data" / "my-data").mkdir(parents=True, exist_ok=True)
    (folder / "data" / "my-data" / "collection.json").write_text(json.dumps({"items": [{"count": 2}]}), "utf-8")
    (folder / "settings.json").write_text("{}", "utf-8")


class ExistingUsers(unittest.TestCase):
    """lead 13.11.: a data folder named in datenordner.json never lands in the new setup."""

    def test_pointer_means_no_first_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            home = tmp / "Documents" / "BentCorner"
            _collection(home)
            pointer = tmp / "roaming" / "datenordner.json"
            pointer.parent.mkdir(parents=True)
            pointer.write_text(json.dumps({"home": str(home)}), "utf-8")
            with mock.patch.object(datahome, "INSTALLED", True), mock.patch.object(datahome, "FROZEN", True), \
                    mock.patch.object(datahome, "TEST", False), mock.patch.object(datahome, "APP_DIR", tmp / "prog"), \
                    mock.patch.object(datahome, "POINTER", pointer), \
                    mock.patch.object(datahome, "_selftest_home", lambda: None):
                self.assertEqual(datahome._resolve(), (home, False))   # no first start, no setup window

    def test_settings_without_onboarding_never_start_it(self):
        self.assertFalse(onboarding.active({}))
        self.assertFalse(onboarding.active({"language": "de", "games_on": ["mtg"]}))

    def test_an_old_setup_closed_in_between_lands_on_finish(self):
        for old in ("stats", "background", "wait", "done"):
            with self.subTest(old=old):
                self.assertTrue(onboarding.active({"onboarding": old}))
                ob = onboarding.Onboarding.__new__(onboarding.Onboarding)
                ob.s = {"onboarding": old}
                self.assertEqual(ob.step, "finish")


class Storage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = [mock.patch.object(datahome, "_local_home", lambda: pathlib.Path(self.tmp.name) / "local"),
                  mock.patch.object(datahome, "PORTABLE", None)]   # an installed copy (in the source it's APP_DIR)
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def backend(self, found=()):
        from ui import setupui
        with mock.patch.object(datahome, "existing", lambda: list(found)):
            return setupui.FirstRunBackend()

    def test_preset_ok(self):
        b = self.backend()
        self.assertEqual((b.choice, b.customise, b.steps), ("docs", False, 5))
        b.next()
        self.assertEqual((b.page, b.stepNo), (1, 2))
        self.assertTrue(b.canGoOn)                           # [OK] right away

    def test_customise_and_back_to_the_preset(self):
        b = self.backend()
        b.setCustomise(True)
        b.setChoice("other")
        self.assertTrue(b.customise)
        b.setCustomise(False)
        self.assertEqual(b.choice, "docs")

    def test_found_opens_customised_nothing_preselected(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = pathlib.Path(tmp) / "alt"
            _collection(old)
            b = self.backend([{"path": old, "cards": 2, "changed": 0, "reachable": True}])
            self.assertTrue(b.customise)
            self.assertEqual(b.choice, "")
            self.assertEqual(b.steps, 5)

    def test_portable_skips_the_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            port = pathlib.Path(tmp) / "stick"
            with mock.patch.object(datahome, "PORTABLE", port):
                b = self.backend()
                self.assertEqual((b.choice, b.steps), ("port", 4))
                b.next()                                     # language → games
                self.assertEqual((b.page, b.stepNo), (2, 2))
                self.assertEqual(b.chosen(), port)
                b.back()
                self.assertEqual(b.page, 0)

    def test_portable_with_a_collection_found_asks(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, port = pathlib.Path(tmp) / "alt", pathlib.Path(tmp) / "stick"
            _collection(old)
            with mock.patch.object(datahome, "PORTABLE", port):
                b = self.backend([{"path": old, "cards": 2, "changed": 0, "reachable": True}])
                self.assertEqual(b.steps, 5)
                b.next()
                self.assertEqual(b.page, 1)


class ProgramWindow(unittest.TestCase):
    def test_steps_and_numbers(self):
        self.assertEqual(onboarding.STEPS, ("profile", "friends", "rescue", "finish"))
        for total, want in ((5, (4, 5)), (4, (3, 4))):
            self.assertEqual((total - onboarding.FROM_END["profile"], total - onboarding.FROM_END["friends"]), want)

    def test_no_more_numbers_or_background_pages(self):
        for gone in ("_stats", "_background"):
            self.assertFalse(hasattr(onboarding.Onboarding, gone), gone)

    def test_finish_leaves_the_numbers_off_never_asked_again(self):
        from net import anonstats
        ob = onboarding.Onboarding.__new__(onboarding.Onboarding)
        ob.s, ob.ctrl, ob.dlg = {"onboarding": "finish"}, mock.MagicMock(), None
        ob.timer = mock.MagicMock()
        ob.finish()
        self.assertIs(ob.s["stats_share"], False)
        self.assertTrue(anonstats.asked(ob.s))               # upkeep never pops the question later
        ob.s = {"onboarding": "finish", "stats_share": True}
        ob.finish()
        self.assertIs(ob.s["stats_share"], True)             # a yes given elsewhere stays


if __name__ == "__main__":
    unittest.main()
