"""The /v1 lock outside Full Orbit (lead/legal 14.11.2026, 0.9.9): outside Full Orbit no /v1 request leaves the app –
except the user's own catch-up deletions dev/leave and forget, each once, with ID + signature, no collection data, and
nothing asked afterwards. /dl and prices stay. Leaving Full Orbit takes the shared lists back BEFORE the level drops.
No network: every way out (netpolite, requests, the poll session) is replaced by a recorder.

    python -m unittest tests.test_v1_gate
"""
import base64
import json
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

from net import anonstats, boxbase, devkeys, forget, poll, relay, relay_ctl, teamnews, vault
from system import orbit

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEED = base64.b64encode(b"\x22" * 32).decode()
BOX = "https://box.example"
OTHER = ("/v1/poll", "/v1/stats", "/v1/key/AAAAAAAAAAAAAAAA", "/v1/health", "/v1/register", "/v1/send", "/v1/news",
         "/v1/gate", "/v1/studio/part", "/v1/fetch", "/v1/vault/put", "/v1/board/put", "/v1/board/del", "/v1/dev/add",
         "/v1/dev/list", "/v1/guard/set", "/v1/pair/put", "/v1/rekey")


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._d, self.headers, self.cookies = status, data if data is not None else {}, {}, {}

    def json(self):
        return self._d


def settings(level="near", on=False):
    s = {"orbit": level}
    st = relay.state(s)
    st["seed"] = SEED
    st["registered"] = BOX
    st["on"] = on
    return s


class Net(unittest.TestCase):
    """Binds the given settings like the app does and records every request (path, json) – nothing leaves."""
    answers = {}

    def setUp(self):
        self.calls = []
        self.addCleanup(orbit.bind, orbit._bound)

        def record(method):
            def send(url, *a, **kw):
                p = boxbase.v1_path(url) or url
                self.calls.append((p, kw.get("json")))
                status, data = self.answers.get(p, (200, {}))
                return Resp(status, data)
            return send
        session = mock.Mock()
        session.post.side_effect = record("POST")
        for target, fn in (("net.netpolite.post", record("POST")), ("net.netpolite.get", record("GET")),
                           ("requests.post", record("POST")), ("requests.get", record("GET")),
                           ("net.boxbase.base", lambda s=None: BOX), ("net.poll._http", lambda: session)):
            p = mock.patch(target, fn)
            p.start()
            self.addCleanup(p.stop)

    def paths(self):
        return [p for p, _ in self.calls]


class Matrix(Net):
    def test_outside_full_only_the_two_catch_ups(self):
        for lv in ("core", "near"):
            orbit.bind(settings(lv))
            for p in OTHER:
                self.assertFalse(boxbase.allowed(BOX + p), f"{lv} {p}")
                self.assertFalse(boxbase.allowed("https://bentcorner.app/testapp/box" + p), f"{lv} test {p}")
            for p in ("/v1/dev/leave", "/v1/forget"):
                self.assertTrue(boxbase.allowed(BOX + p))
            for url in ("https://bentcorner.app/dl/manifest.json", "https://bentcorner.app/dl/web/prices-mtg.json.gz",
                        "https://api.scryfall.com/cards/x"):
                self.assertTrue(boxbase.allowed(url), url)
        self.assertEqual(boxbase.CATCHUP, frozenset({"/v1/dev/leave", "/v1/forget"}))

    def test_full_orbit_everything_as_before(self):
        orbit.bind(settings("near", on=True))
        for p in OTHER:
            self.assertTrue(boxbase.allowed(BOX + p), p)

    def test_unbound_ship_is_locked_source_is_open(self):
        orbit.bind(None)
        with mock.patch("collection.syncrun.ship_build", return_value=True):
            with self.assertRaises(boxbase.Blocked):
                boxbase.check(BOX + "/v1/poll")
            boxbase.check(BOX + "/v1/forget")
        with mock.patch("collection.syncrun.ship_build", return_value=False):
            boxbase.check(BOX + "/v1/poll")


class Senders(Net):
    """Every sender of /v1 asks the lock first – outside Full Orbit nothing reaches the network."""

    def setUp(self):
        super().setUp()
        self.s = settings("near")
        orbit.bind(self.s)

    def test_vault_gated(self):
        with self.assertRaises(boxbase.Blocked):
            vault.gated("POST", BOX + "/v1/vault/put", 20, json={})
        self.assertEqual(self.calls, [])

    def test_relay_and_vault_post_say_why(self):
        with self.assertRaises(relay.RelayError) as e:
            relay._post(self.s, "/v1/board/put", {"code": "X"})
        self.assertEqual(e.exception.status, boxbase.BLOCKED_STATUS)
        with self.assertRaises(vault.VaultError) as e:
            vault._post(self.s, "/v1/vault/get", {"code": "X"})
        self.assertEqual(e.exception.status, boxbase.BLOCKED_STATUS)
        with self.assertRaises(relay.RelayError):
            relay.lookup(self.s, "AAAAAAAAAAAAAAAA")
        self.assertEqual(self.calls, [])

    def test_poll_not_even_registering(self):
        with self.assertRaises(boxbase.Blocked):
            poll.ask(self.s)
        self.assertEqual(self.calls, [])

    def test_anonymous_numbers(self):
        self.s["stats_share"] = True
        with self.assertRaises(boxbase.Blocked):
            anonstats.send(self.s)
        with mock.patch("system.datahome.TEST", False), mock.patch("system.datahome.FROZEN", True), \
                mock.patch("version.is_release", return_value=True):
            self.assertFalse(anonstats.due(self.s))
            self.assertTrue(anonstats.due(settings("near", on=True) | {"stats_share": True}))
        self.assertEqual(self.calls, [])

    def test_team_news_and_gate_code(self):
        self.assertEqual(teamnews.fetch_news(BOX + "/"), [])
        with self.assertRaises(vault.VaultError) as e:
            vault.set_gate("1234")
        self.assertEqual(e.exception.status, boxbase.BLOCKED_STATUS)
        self.assertEqual(self.calls, [])


class Forget(Net):
    """Deleting everything online outside Full Orbit: exactly one POST /v1/forget – no health, no fallback, no
    re-registering; only ID + signature."""
    ALLOWED_KEYS = {"code", "t", "sig", "dev_id", "sig_dev", "sig_main"}

    def setUp(self):
        super().setUp()
        self.s = settings("core")
        relay.state(self.s)["posted"] = {"mtg/lists": {"to": []}}
        orbit.bind(self.s)

    def test_one_request_only(self):
        self.answers = {"/v1/forget": (200, {"deleted": True})}
        r = forget.delete_server(self.s, notify=False)
        self.assertEqual(r.status, forget.DELETED)
        self.assertEqual(self.paths(), ["/v1/forget"])
        self.assertLessEqual(set(self.calls[0][1]), self.ALLOWED_KEYS)

    def test_no_fallback_and_no_retry(self):
        for answer in ((404, {}), (403, {"unknown": True}), (503, {})):
            self.calls.clear()
            self.answers = {"/v1/forget": answer}
            forget.delete_server(self.s, notify=False)
            self.assertEqual(self.paths(), ["/v1/forget"], answer)
            relay.state(self.s).update(seed=SEED, registered=BOX)

    def test_uninstaller_check_asks_nothing(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        f = tmp / "settings.json"
        f.write_text(json.dumps(self.s), "utf-8")
        for guard, code in ((False, forget.CHECK_FULL), (True, forget.CHECK_GUARD)):
            with mock.patch("system.datastore.SETTINGS", f), mock.patch.object(sys, "argv", ["x", "--forget-server", "--check"]), \
                    mock.patch("net.forget.guarded", return_value=guard):
                with self.assertRaises(SystemExit) as e:
                    forget.main()
            self.assertEqual(e.exception.code, code)
        self.assertEqual(self.calls, [])


class Leave(Net):
    """Signing out of an ID outside Full Orbit: exactly one POST /v1/dev/leave – no register before, none after."""

    def setUp(self):
        super().setUp()
        orbit.bind(settings("near"))
        for target, value in (("net.devkeys._load", lambda *a: {"dev_id": "d1"}), ("net.devkeys.sign", lambda m: "sd"),
                              ("net.devkeys.registered", lambda s: True)):
            p = mock.patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def test_leave_seed_one_call(self):
        self.assertTrue(devkeys.leave_seed(SEED, BOX))
        self.assertEqual(self.paths(), ["/v1/dev/leave"])
        self.assertEqual(set(self.calls[0][1]), {"code", "dev_id", "t", "sig_id", "sig_dev"})

    def test_own_leave_one_call(self):
        self.assertTrue(devkeys.leave(settings("near")))
        self.assertEqual(self.paths(), ["/v1/dev/leave"])

    def test_unknown_or_error_is_not_repeated(self):
        for answer in ((403, {"unknown": True}), (503, {})):
            self.calls.clear()
            self.answers = {"/v1/dev/leave": answer}
            with self.assertRaises(vault.VaultError):
                devkeys.leave_seed(SEED, BOX)
            self.assertEqual(self.paths(), ["/v1/dev/leave"], answer)

    def test_pending_leave_once_per_start(self):
        from net import sync_ctl
        c = mock.Mock()
        c.settings = settings("near") | {"sync_leave_pending": {"seed": SEED, "at": 1}}
        jobs = []
        c._sync_bg = lambda what, fn: jobs.append((what, fn))
        self.answers = {"/v1/dev/leave": (503, {})}
        with mock.patch("collection.syncrun.available", return_value=True):
            sync_ctl.SyncControl.leave_pending_check(c)
        self.assertEqual(len(jobs), 1)
        try:
            jobs[0][1]()
            err = None
        except Exception as e:  # noqa: BLE001
            err = e
        sync_ctl.SyncControl._join_leave_done(c, None, err)
        self.assertEqual(self.paths(), ["/v1/dev/leave"])
        self.assertIn("sync_leave_pending", c.settings, "kept for the next start – not retried now")
        self.assertEqual(len(jobs), 1)


class LeavingFull(Net):
    """Leaving Full Orbit: the shared lists are taken back first (still Full Orbit), then the level drops."""

    def ctl(self):
        c = mock.Mock()
        c.settings = settings("near", on=True)
        relay.state(c.settings)["posted"] = {"mtg/lists": {"to": []}}
        relay.state(c.settings)["registered"] = relay.url(c.settings)
        orbit.bind(c.settings)
        jobs = []
        c._relay_bg = lambda what, fn: jobs.append((what, fn))
        c._leaving_job = False
        c.relay_toggle = lambda on: relay_ctl.RelayControl.relay_toggle(c, on)
        c.relay_fp_file.return_value = pathlib.Path(tempfile.mkdtemp()) / "fp.json"
        return c, jobs

    def test_withdraw_first_then_off(self):
        c, jobs = self.ctl()
        relay_ctl.RelayControl.relay_toggle(c, False)
        self.assertTrue(relay.enabled(c.settings), "still Full Orbit while taking back")
        self.assertTrue(relay.state(c.settings)["leaving"])
        self.assertEqual([w for w, _ in jobs], ["leave_full"])
        relay_ctl.RelayControl.relay_toggle(c, False)   # a second click: no second job
        self.assertEqual(len(jobs), 1)
        res = jobs[0][1]()
        self.assertIn("/v1/board/del", self.paths())
        relay_ctl.RelayControl._relay_done(c, "leave_full", res, "")
        self.assertFalse(relay.enabled(c.settings))
        self.assertNotIn("leaving", relay.state(c.settings))
        self.assertEqual(orbit.level(c.settings), "near")
        with self.assertRaises(boxbase.Blocked):
            boxbase.check(BOX + "/v1/board/del")

    def test_offline_still_drops_the_level(self):
        c, jobs = self.ctl()
        relay_ctl.RelayControl.relay_toggle(c, False)
        relay_ctl.RelayControl._relay_done(c, "leave_full", None, "offline")
        self.assertFalse(relay.enabled(c.settings))

    def test_cut_off_leaving_is_finished_at_the_next_start(self):
        c, jobs = self.ctl()
        relay.state(c.settings)["leaving"] = True
        c._relay_t, c._lists_t = mock.Mock(), mock.Mock()
        relay_ctl.RelayControl.relay_setup(c)
        self.assertEqual([w for w, _ in jobs], ["leave_full"])
        c._relay_t.start.assert_not_called()

    def test_nothing_shared_drops_at_once(self):
        c, jobs = self.ctl()
        relay.state(c.settings)["posted"] = {}
        relay_ctl.RelayControl.relay_toggle(c, False)
        self.assertEqual(jobs, [])
        self.assertFalse(relay.enabled(c.settings))


class Source(unittest.TestCase):
    """Every module that talks to /v1 itself (not through relay/vault) asks the lock."""
    RAW = re.compile(r"\b(requests|netpolite|_http\(\))\.(post|get|put|delete|request)\(|\(requests\.post if")

    def test_raw_senders_are_locked(self):
        found = set()
        for p in [ROOT / "app.py", *[f for d in ("net", "collection", "system", "ui", "cards") for f in (ROOT / d).rglob("*.py")]]:
            s = p.read_text("utf-8")
            if "/v1" in s.replace("frankfurter.dev/v1", "") and self.RAW.search(s):
                found.add(p.relative_to(ROOT).as_posix())
                self.assertRegex(s, r"boxbase\.(check|allowed)\(", p.name)
        self.assertEqual(found, {"net/anonstats.py", "net/poll.py", "net/teamnews.py", "net/vault.py"})


if __name__ == "__main__":
    unittest.main()
