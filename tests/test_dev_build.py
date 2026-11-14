"""The DEV version (Oliver/Gordon/lead 13.11.2026): every build without the ship flag talks to the box ONLY through the
test instance (net/boxbase.py), shows „DEV <version>“ and carries the red mark – a Ship build never does.

- one address for every /v1 request: Ship = live, DEV (and the source without BC_SYNC_BASE) = <SERVER>/testapp/box,
  the source with BC_SYNC=1 + BC_SYNC_BASE = exactly that box (local box checks keep working)
- recording of every request in DEV: without the access code nothing leaves at all, with it every /v1 path goes to the
  test instance; /dl is not /v1 and stays live
- tools/check_package refuses a Ship package with the red mark; iconkit.dev_tint keeps the form
Only temp folders, no network.

    python -m unittest tests.test_dev_build
"""
import os
import pathlib
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

import numpy as np

from net import boxbase, relay, vault
from system import contacts

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_BOX = contacts.SERVER.rstrip("/") + "/testapp/box"
NO_TEST_BASE = {"BC_SYNC": "", "BC_SYNC_BASE": ""}


class Address(unittest.TestCase):
    def test_sync_test_copies_reach_the_test_instance_and_never_live(self):
        """lead 13.11.: LocalTestVersions\\Desktop-Sync (Start.cmd live: from the source, BC_SYNC=1 + BC_SYNC_BASE)
        and every built SYNC_TEST exe go to /testapp/box – a SYNC_TEST build never falls back to the live box, not even
        with the ship flag."""
        with mock.patch.dict(os.environ, {"BC_SYNC": "1", "BC_SYNC_BASE": TEST_BOX}), \
                mock.patch.object(sys, "frozen", False, create=True):
            self.assertEqual(boxbase.base({}), TEST_BOX)                       # Start.cmd live
        for ship in (False, True):
            with mock.patch.dict(os.environ, NO_TEST_BASE), mock.patch("collection.syncrun.SYNC_TEST", True), \
                    mock.patch("collection.syncrun.ship_build", lambda: ship):
                self.assertEqual(boxbase.base({}), TEST_BOX, f"SYNC_TEST build, ship flag {ship}")
                self.assertFalse(boxbase.live())

    def test_ship_live_dev_test_instance(self):
        with mock.patch.dict(os.environ, NO_TEST_BASE), mock.patch("collection.syncrun.ship_build", lambda: True):
            self.assertEqual(boxbase.base({}), contacts.SERVER.rstrip("/"))
            self.assertTrue(boxbase.live())
        with mock.patch.dict(os.environ, NO_TEST_BASE), mock.patch("collection.syncrun.ship_build", lambda: False):
            self.assertEqual(boxbase.base({}), TEST_BOX)
            self.assertFalse(boxbase.live())

    def test_old_stored_address_is_never_used(self):
        s = {"relay": {"url": "https://bentcorner.oliver-schunn.tech", "on": True}}
        with mock.patch.dict(os.environ, NO_TEST_BASE), mock.patch("collection.syncrun.ship_build", lambda: False):
            self.assertEqual(relay.url(s), TEST_BOX)
            self.assertEqual(vault._base(s), TEST_BOX)

    def test_local_box_from_the_source_stays(self):
        with mock.patch.dict(os.environ, {"BC_SYNC": "1", "BC_SYNC_BASE": "http://127.0.0.1:8799"}), \
                mock.patch.object(sys, "frozen", False, create=True):
            self.assertEqual(relay.url({}), "http://127.0.0.1:8799")
            self.assertEqual(vault._base({}), "http://127.0.0.1:8799")


class Recording(unittest.TestCase):
    """Every way to the box in DEV, with a recording of what would really go out."""

    def setUp(self):
        self.sent = []
        rec = lambda m: (lambda url, *a, **k: self.sent.append((m, url)) or Resp())   # noqa: E731
        for p in (mock.patch.dict(os.environ, NO_TEST_BASE),
                  mock.patch("collection.syncrun.ship_build", lambda: False),
                  mock.patch("requests.post", rec("POST")), mock.patch("requests.get", rec("GET")),
                  mock.patch("net.netpolite.post", rec("POST")), mock.patch("net.netpolite.get", rec("GET")),
                  mock.patch("net.poll._http", lambda: Session(rec))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(vault._gate.__setitem__, 0, vault._gate[0])
        self.s = {"relay": {"on": True, "seed": "AAAA", "url": "https://bentcorner.app"}}

    def calls(self):
        from net import forget, poll
        return [("relay", lambda: relay._post(self.s, "/v1/fetch", {"code": "X"})),
                ("vault", lambda: vault._post(self.s, "/v1/vault/get", {"code": "X"})),
                ("poll", lambda: poll.ask(self.s)),
                ("forget", lambda: forget._raw_post(self.s, "/v1/forget", {"code": "X"}))]

    def test_without_access_code_nothing_leaves(self):
        vault._gate[0] = None
        for name, fn in self.calls():
            with mock.patch("net.vault._me", lambda s: ("X", 1)), mock.patch("net.relay._signed", lambda s, m: "sig"):
                try:
                    fn()
                except Exception:  # noqa: BLE001 – refused before sending (VaultError/RelayError 401, GateMissing)
                    pass
        self.assertEqual(self.sent, [], "not one request without the test box's access code")

    def test_with_access_code_only_the_test_instance(self):
        vault._gate[0] = "TOKEN"
        for name, fn in self.calls():
            with mock.patch("net.vault._me", lambda s: ("X", 1)), mock.patch("net.relay._signed", lambda s, m: "sig"):
                try:
                    fn()
                except Exception:  # noqa: BLE001 – the stand-in answer may not please every caller
                    pass
        paths = {url.split("/v1/", 1)[-1] for _m, url in self.sent}
        self.assertEqual(paths, {"fetch", "vault/get", "poll", "forget"}, "every way recorded")
        for method, url in self.sent:
            self.assertTrue(url.startswith(TEST_BOX + "/v1/"), url)


class Session:
    def __init__(self, rec):
        self.post, self.get = rec("POST"), rec("GET")


class Resp:
    status_code = 200
    headers = {}
    text = "{}"
    content = b"{}"

    def json(self):
        return {}


class Mark(unittest.TestCase):
    def test_dev_flag(self):
        import version
        with mock.patch("collection.syncrun.ship_build", lambda: False):
            self.assertTrue(version.dev_build())
        with mock.patch("collection.syncrun.ship_build", lambda: True):
            self.assertFalse(version.dev_build())

    def test_tint_keeps_the_form(self):
        from ui import iconkit
        img = np.zeros((4, 4, 4), np.uint8)
        img[1:3, 1:3] = (243, 242, 242, 255)   # the light ink (BGR of #f2f2f3)
        red = iconkit.dev_tint(img, "dark")
        self.assertTrue((red[..., 3] == img[..., 3]).all(), "alpha = the form, unchanged")
        self.assertEqual(iconkit.dev_tint_hex("#f2f2f3", "dark").lower(), iconkit.DEV_RED.lower())
        self.assertEqual(iconkit.dev_tint_hex("#161618", "light").lower(), iconkit.DEV_RED.lower())

    def test_check_package_refuses_the_red_mark_in_a_ship_build(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import check_package
        with tempfile.TemporaryDirectory() as tmp:
            stage = pathlib.Path(tmp) / "stage"
            prog = stage / "0.9.8.100-x"
            (prog / "brand").mkdir(parents=True)
            (prog / "ship-sync.flag").write_text("sync")
            (prog / "brand" / "BRAND.md").write_bytes((ROOT / "brand" / "BRAND.md").read_bytes()
                                                      if (ROOT / "brand" / "BRAND.md").exists() else b"x")
            if (ROOT / "brand" / "BRAND.md").exists():
                self.assertEqual(check_package.brand_problems(stage), [])
            (prog / "brand" / "DEV.txt").write_text("DEV")
            self.assertTrue(check_package.brand_problems(stage))
            (prog / "ship-sync.flag").unlink()   # a work build may carry it
            self.assertEqual(check_package.brand_problems(stage), [])

    def test_build_script_uses_the_dev_brand_only_without_ship(self):
        b = (ROOT / "build.ps1").read_text("utf-8-sig")
        self.assertIn("if (-not $Ship -and (Test-Path brand\\logo))", b)
        self.assertIn('$Ship -and (Test-Path brand\\logo) -and $Icon -ne "brand\\icon.ico"', b)


if __name__ == "__main__":
    unittest.main()
