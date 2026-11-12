"""The Ship switch (lead 08.11.): sync + online backup are on ONLY in an exe built with `build.ps1 -Ship` (the candidate).
A normal build – Oliver's real app in app\\, every work version – stays off: no engine, no network. In a built exe the
test server address (BC_SYNC_BASE) is never followed, Ship build or not.

    python -m unittest tests.test_ship_flag
"""
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

from collection import syncrun

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Frozen:
    """Like a built exe: sys.frozen and the bundle folder (_MEIPASS) – with or without the Ship mark."""
    def __init__(self, ship):
        self.ship = ship

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        if self.ship:
            (pathlib.Path(self.tmp.name) / syncrun.SHIP_FLAG).write_text("sync", "ascii")
        self.patches = [mock.patch.object(sys, "frozen", True, create=True),
                        mock.patch.object(sys, "_MEIPASS", self.tmp.name, create=True),
                        mock.patch.dict("os.environ", {"BC_SYNC": "1", "BC_SYNC_BASE": "http://127.0.0.1:8799"})]
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()


class ShipFlag(unittest.TestCase):
    def test_normal_build_off_even_with_the_test_switches(self):
        with Frozen(ship=False):
            self.assertFalse(syncrun.ship_build())
            self.assertFalse(syncrun.available(), "a normal exe never syncs – BC_SYNC counts only from the source")
            self.assertIsNone(syncrun.test_base())

    def test_ship_build_on_and_never_the_test_server(self):
        with Frozen(ship=True):
            self.assertTrue(syncrun.ship_build())
            self.assertTrue(syncrun.available())
            self.assertIsNone(syncrun.test_base(), "the Ship exe goes to the real server, never BC_SYNC_BASE")

    def test_source_unchanged(self):
        with mock.patch.dict("os.environ", {"BC_SYNC": "1"}):
            self.assertTrue(syncrun.available())
        with mock.patch.dict("os.environ", {"BC_SYNC": ""}):
            self.assertFalse(syncrun.available())
        self.assertFalse(syncrun.SYNC_TEST, "SYNC_TEST stays off in the repository")

    def test_normal_build_no_poll_no_network(self):
        """Off = not one question to the server (the minute question asks syncrun.available first)."""
        from net import poll_ctl
        w = mock.Mock()
        w.settings = {"orbit": "near", "relay": {"on": True}}
        w.sync_on.return_value = True
        w.sync_orbit_ok.return_value = True
        with Frozen(ship=False), mock.patch("system.orbit.level", lambda s: "full"), \
                mock.patch("net.relay.enabled", lambda s: True):
            self.assertFalse(poll_ctl.PollControl._poll_wanted(w))


class LiveBase(unittest.TestCase):
    """Gordon 08.11.: the live box answers at https://bentcorner.app (/v1/…) – only there, also with old settings."""

    def test_ship_build_goes_to_bentcorner_app(self):
        from net import vault
        from system import contacts
        self.assertEqual(contacts.SERVER, "https://bentcorner.app")
        old = {"relay": {"url": contacts.SERVER_OLD}}
        with Frozen(ship=True):
            self.assertEqual(vault._base(old), "https://bentcorner.app")
            self.assertEqual(vault._base({}), "https://bentcorner.app")

    def test_poll_and_registry_use_the_same_base(self):
        """The minute question and /v1/dev/* go through vault._base too (no own address)."""
        for mod in ("net/poll.py", "net/devkeys.py"):
            src = (ROOT / mod).read_text("utf-8")
            self.assertNotIn("SERVER_OLD", src, mod)
            self.assertNotIn("relay.url(", src, mod)
        self.assertIn("vault._base(settings)", (ROOT / "net/poll.py").read_text("utf-8"))


class BuildScript(unittest.TestCase):
    """build.ps1 puts the mark into the exe only under -Ship and removes an old one before every build."""

    def test_mark_only_with_ship(self):
        s = (ROOT / "build.ps1").read_text("utf-8-sig")
        self.assertIn("param([switch]$Ship)", s)
        self.assertIn("Remove-Item build\\ship-sync.flag", s)
        i_if, i_add = s.index("if ($Ship) {"), s.index('"build\\ship-sync.flag;."')
        i_else = s.index("} else {", i_if)
        self.assertTrue(i_if < i_add < i_else, "the --add-data for the mark sits inside if ($Ship)")
        self.assertIn("@ShipData", s)
        self.assertLess(s.index("Remove-Item build\\ship-sync.flag"), i_if)


if __name__ == "__main__":
    unittest.main()
