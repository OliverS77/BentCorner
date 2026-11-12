"""Sync without buttons (lead/Oliver 07.11., docs/web/DEVICE-KEYS.md §7): the minute question /v1/poll, its pace, what
its answer sets off, the way back to the old timers on an older server, the last push on closing – and the device list
fields (n, os, ver, added, rename any device).

    python -m unittest tests.test_poll
"""
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from collection import syncrun
from net import poll, poll_ctl
from net.vault import VaultError


class Pace(unittest.TestCase):
    def test_active_idle_and_jitter(self):
        p = poll.Pace()
        self.assertEqual(p.next(True, 0.0, now=0), 60)
        self.assertEqual(p.next(True, 1.0, now=0), 70)
        self.assertEqual(p.next(True, -1.0, now=0), 50)
        self.assertEqual(p.next(False, 0.0, now=0), 900)

    def test_errors_double_up_to_15_minutes_never_right_away(self):
        p = poll.Pace()
        got = []
        for _ in range(7):
            p.failed(now=0)
            got.append(p.next(True, 0.0, now=0))
        self.assertEqual(got, [60, 120, 240, 480, 900, 900, 900])
        p.ok(now=0)
        self.assertEqual(p.next(True, 0.0, now=0), 60)

    def test_server_pause_holds(self):
        p = poll.Pace()
        p.failed(retry_after=600, now=100)
        self.assertEqual(p.next(True, 0.0, now=100), 600)
        p.ok(slow=900, now=1000)   # the emergency switch „slow“: every
        self.assertEqual(p.next(True, 0.0, now=1000), 900)
        self.assertEqual(p.next(True, 0.0, now=1890), 60)


class Response:
    def __init__(self, status, data, headers=None):
        self.status_code, self._d, self.headers = status, data, headers or {}

    def json(self):
        return self._d


class Ask(unittest.TestCase):
    def ask(self, resp):
        sent = []
        sess = types.SimpleNamespace(post=lambda url, **kw: (sent.append((url, kw)), resp)[1])
        with mock.patch.object(poll, "_http", lambda: sess), \
                mock.patch("net.vault._me", lambda s: ("ABCDEFGH", 1700000000)), \
                mock.patch("net.vault._base", lambda s: "https://bentcorner.app"), \
                mock.patch("net.relay._signed", lambda s, msg: "sig:" + msg):
            return poll.ask({}), sent

    def test_signed_question_and_answer(self):
        got, sent = self.ask(Response(200, {"vault_version": 7, "box_n": 2, "now": 1, "guard": {"set": True},
                                            "guard_request": None, "every": 900, "closed": True}))
        url, kw = sent[0]
        self.assertEqual(url, "https://bentcorner.app/v1/poll")
        self.assertEqual(kw["json"], {"code": "ABCDEFGH", "t": 1700000000, "sig": "sig:poll|ABCDEFGH|1700000000"})
        self.assertNotIn("cookies", kw, "the gate cookie only goes to the test instance")
        self.assertEqual((got["vault_version"], got["box_n"], got["slow"], got["closed"]), (7, 2, 900, True))

    def test_registry_fields_go_through(self):
        """Guide run 07.11.: without reg_version the device list was fetched once and never again (✕ failed)."""
        got, _ = self.ask(Response(200, {"vault_version": 1, "box_n": 0, "reg_version": 4, "devices": 3,
                                         "dev_request": [{"dev_id": "dX", "since": 1, "until": 2}]}))
        self.assertEqual((got["reg_version"], got["devices"], got["dev_request"][0]["dev_id"]), (4, 3, "dX"))

    def test_older_server_and_retry_after(self):
        with self.assertRaises(VaultError) as c:
            self.ask(Response(404, {}))
        self.assertEqual(c.exception.status, 404)
        with self.assertRaises(VaultError) as c:
            self.ask(Response(429, {"error": "zu oft"}, {"Retry-After": "120"}))
        self.assertEqual((c.exception.status, c.exception.retry_after), (429, 120))


class Timer:
    def __init__(self):
        self.active, self.ms, self.stops = False, None, 0

    def start(self, ms=None):
        self.active, self.ms = True, ms

    def stop(self):
        self.active = False
        self.stops += 1

    def isActive(self):
        return self.active


def window(sync=True, friends=True, version=3, idle=False):
    w = types.SimpleNamespace()
    for n in [n for n in dir(poll_ctl.PollControl) if not n.startswith("__")]:
        attr = getattr(poll_ctl.PollControl, n)
        setattr(w, n, types.MethodType(attr, w) if callable(attr) else attr)
    w.settings = {}
    w.sync_status = {"busy": False}
    w.sync_engine = types.SimpleNamespace(meta={"version": version, "guard": False, "guard_request": None}, pending=[])
    w.sync_on = lambda: sync
    w.sync_orbit_ok = lambda: True
    w.activity = types.SimpleNamespace(idle=lambda: idle)
    w.sync_now, w.relay_poll, w.sync_setup, w.relay_setup = (mock.Mock() for _ in range(4))
    w._sync_t, w._relay_t, w._poll_t = Timer(), Timer(), Timer()
    w._poll_pace, w._poll_busy, w._poll_on = poll.Pace(), False, False
    w._friends = friends
    return w


class Act(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch("collection.syncrun.available", lambda: True),
                  mock.patch("system.orbit.level", lambda s: "full")):
            p.start()
            self.addCleanup(p.stop)

    def run_done(self, w, res=None, err=None):
        with mock.patch("net.relay.enabled", lambda s: w._friends):
            poll_ctl.PollControl._poll_done(w, res, err)

    def test_nothing_new_nothing_fetched(self):
        w = window()
        self.run_done(w, {"vault_version": 3, "box_n": 0})
        w.sync_now.assert_not_called()
        w.relay_poll.assert_not_called()
        self.assertTrue(w._poll_t.active)
        self.assertGreaterEqual(w._poll_t.ms, 50_000)

    def test_vault_changed_or_parcels_waiting(self):
        w = window()
        self.run_done(w, {"vault_version": 4, "box_n": 2})
        w.sync_now.assert_called_once()
        w.relay_poll.assert_called_once()

    def test_guard_request_or_deleted_set_off_a_sync(self):
        for res in ({"vault_version": 3, "guard_request": {"since": 1}}, {"vault_version": 0, "deleted": 1700000000},
                    {"vault_version": 3, "guard": {"set": True}}):
            w = window()
            self.run_done(w, res)
            w.sync_now.assert_called_once()

    def test_closed_or_sync_off_no_sync(self):
        w = window()
        self.run_done(w, {"vault_version": 9, "closed": True})
        w.sync_now.assert_not_called()
        w = window(sync=False)
        self.run_done(w, {"vault_version": 9, "box_n": 1})
        w.sync_now.assert_not_called()
        w.relay_poll.assert_called_once()

    def test_first_answer_stops_the_old_timers(self):
        w = window()
        w._sync_t.start(180_000)
        w._relay_t.start(180_000)
        self.run_done(w, {"vault_version": 3})
        self.assertFalse(w._sync_t.active or w._relay_t.active)
        self.assertTrue(w.poll_mode())

    def test_older_server_keeps_the_old_timers(self):
        w = window()
        self.run_done(w, err=VaultError(404, "nope"))
        self.assertTrue(w._poll_unsupported)
        self.assertFalse(w.poll_mode())
        w.sync_setup.assert_called_once()
        w.relay_setup.assert_called_once()
        self.assertFalse(w._poll_t.active)
        w.poll_setup()   # sync_setup / relay_setup call it again: it stays out of the way
        self.assertFalse(w._poll_t.active)

    def test_error_backs_off(self):
        w = window()
        self.run_done(w, err=VaultError(0, "offline"))
        self.run_done(w, err=VaultError(0, "offline"))
        self.assertEqual(w._poll_pace.fails, 2)
        self.assertGreaterEqual(w._poll_t.ms, 110_000)

    def test_idle_asks_every_15_minutes(self):
        w = window(idle=True)
        self.run_done(w, {"vault_version": 3})
        self.assertGreaterEqual(w._poll_t.ms, 890_000)

    def test_event_syncs_and_asks_now(self):
        w = window()
        with mock.patch("net.relay.enabled", lambda s: True):
            w.sync_event()
        w.sync_now.assert_called_once()
        self.assertEqual(w._poll_t.ms, 0)

    def test_friend_burst_asks_every_20_seconds(self):
        w = window()
        with mock.patch("net.relay.enabled", lambda s: True):
            w.sync_poll_burst()
            w._poll_schedule()
        self.assertEqual(w._poll_t.ms, 20_000)


class NeverWithoutReason(unittest.TestCase):
    """lead 07.11.: backup and mailbox off, outside Full Orbit, or a live build (the sync behind its switch) – not one
    question, no network call; the old timers stay as they were."""

    def setup_and_tick(self, available=True, level="full", sync=True, friends=True):
        w = window(sync=sync, friends=friends)
        w._poll_t = None
        asked = []
        with mock.patch("collection.syncrun.available", lambda: available),                 mock.patch("system.orbit.level", lambda s: level),                 mock.patch("net.relay.enabled", lambda s: friends),                 mock.patch("net.poll.ask", lambda s: asked.append(1)),                 mock.patch.object(poll_ctl.QtCore, "QTimer", lambda *a, **k: Timer()):
            w._sync_bg = lambda step, fn: fn()
            w.poll_setup()
            w._poll_tick()
            w.poll_now()
            w.sync_event()
        return w, asked

    def test_off_cases_ask_nothing(self):
        for kw in ({"sync": False, "friends": False}, {"level": "near"}, {"level": "core"}, {"available": False}):
            w, asked = self.setup_and_tick(**kw)
            self.assertEqual(asked, [], kw)
            self.assertFalse(w._poll_t.active, kw)

    def test_on_asks(self):
        w, asked = self.setup_and_tick()
        self.assertEqual(asked, [1])


class RealWindowState(unittest.TestCase):
    """Guide run 07.11.: on the real window nothing but poll_setup prepares the state – the first answer crashed
    (_poll_on missing), so the minute question never ran. Here only what poll_setup itself sets up."""

    def test_first_answer_after_poll_setup(self):
        w = window()
        for n in ("_poll_on", "_poll_t", "_poll_pace", "_poll_busy"):
            delattr(w, n)
        with mock.patch("collection.syncrun.available", lambda: True),                 mock.patch("system.orbit.level", lambda s: "full"),                 mock.patch("net.relay.enabled", lambda s: True),                 mock.patch.object(poll_ctl.QtCore, "QTimer", lambda *a, **k: Timer()):
            w.poll_setup()
            poll_ctl.PollControl._poll_done(w, {"vault_version": 3}, None)
        self.assertTrue(w.poll_mode())
        self.assertTrue(w._poll_t.active)


class Flush(unittest.TestCase):
    def test_nothing_pending_no_network(self):
        w = window()
        w.sync_engine.push = mock.Mock()
        self.assertFalse(w.sync_flush())
        w.sync_engine.push.assert_not_called()

    def test_pending_goes_out(self):
        w = window()
        w.sync_engine.pending = [{"op": 1}]
        w.sync_engine.push = mock.Mock()
        self.assertTrue(w.sync_flush())
        w.sync_engine.push.assert_called_once()

    def test_closing_never_waits_longer(self):
        w = window()
        w.sync_engine.pending = [{"op": 1}]
        gate = threading.Event()
        w.sync_engine.push = lambda: gate.wait(5)
        w.FLUSH_WAIT = 0.2
        t = time.monotonic()
        self.assertFalse(w.sync_flush())
        self.assertLess(time.monotonic() - t, 1.0)
        gate.set()


class DeviceNumber(unittest.TestCase):
    def test_new_device_takes_the_largest_plus_one(self):
        view = {"a": {"n": 1, "added": 10}, "b": {"n": 3, "added": 20}, "c": {"added": 30}}
        self.assertEqual(syncrun.device_number("c", view), 4)

    def test_same_number_the_later_one_moves_on(self):
        view = {"a": {"n": 2, "added": 10}, "b": {"n": 2, "added": 10}, "c": {"n": 1, "added": 5}}
        self.assertEqual(syncrun.device_number("a", view), 2, "(added, dev) smaller: keeps it")
        self.assertEqual(syncrun.device_number("b", view), 3)

    def test_keeps_its_number(self):
        view = {"a": {"n": 5, "added": 10}, "b": {"n": 1, "added": 20}}
        self.assertEqual(syncrun.device_number("a", view), 5)


class DeviceList(unittest.TestCase):
    """Two engines on one fake vault (tests/test_syncrun.py): the new fields, „Device N“, rename any device."""

    def setUp(self):
        from tests import test_syncrun as ts
        self.ts = ts
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = ts.FakeVault()
        self.clock = [1_780_000_000_000]
        clock = lambda: self.clock[0]   # noqa: E731
        self.a = ts.Device(self.tmp.name, "a", self.vault, clock)
        self.b = ts.Device(self.tmp.name, "b", self.vault, clock)

    def tearDown(self):
        self.tmp.cleanup()

    def both(self):
        self.a.eng.switch_on()
        self.a.sync()
        self.b.eng.switch_on()
        self.b.sync()
        self.clock[0] += 1000
        self.a.sync()

    def test_fields_and_default_names(self):
        self.both()
        devs = self.a.eng.devices()
        self.assertEqual([(d["n"], d["name"], d["me"]) for d in devs], [(1, None, True), (2, None, False)])
        me = devs[0]
        self.assertEqual((me["kind"], me["os"]), ("pc", syncrun.os_name()))
        self.assertTrue(me["ver"])
        self.assertEqual(me["added"], self.clock[0] // syncrun.DAY_MS * syncrun.DAY_MS)

    def test_rename_another_device_arrives_there(self):
        self.both()
        other = [d for d in self.a.eng.devices() if not d["me"]][0]
        self.assertTrue(self.a.eng.rename_device(other["dev"], "  Laptop  im Flur "))
        self.a.sync()
        self.b.sync()
        self.assertEqual(self.b.eng.devices()[0]["name"], "Laptop im Flur")
        self.b.eng.catch_up()
        self.assertEqual(self.b.settings.get("device_name"), "Laptop im Flur", "the settings follow (rekey's name)")
        self.assertEqual(self.b.eng.devices()[0]["name"], "Laptop im Flur", "its own run doesn't write it back")
        self.assertTrue(self.a.eng.rename_device(other["dev"], ""))
        self.a.sync()
        self.b.sync()
        self.b.eng.catch_up()
        self.assertIsNone(self.b.eng.devices()[0]["name"])
        self.assertNotIn("device_name", self.b.settings)


if __name__ == "__main__":
    unittest.main()
