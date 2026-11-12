"""S7 (Prüfkette 08.11.): this device's own key change and the background jobs never overlap. Before, a sync/mailbox job
running while „Remove device“ moved the address got the 410 for the OLD address and relay.moved_away destroyed the
new seed or called this very device removed.

    python -m unittest tests.test_own_change
"""
import base64
import threading
import time
import unittest
from unittest import mock

from net import rekey, relay


def _settings():
    return {"relay": {"on": True, "seed": base64.b64encode(b"\x11" * 32).decode()}}


class MovedAway(unittest.TestCase):
    def test_410_during_own_change_changes_nothing(self):
        s = _settings()
        seed = s["relay"]["seed"]
        with relay.own_change(wait=1):
            for data in ({"gone": True}, {"per_device": True}, {"fwd": "x"}):
                self.assertFalse(relay.moved_away(s, dict(data)))
        self.assertEqual(s["relay"]["seed"], seed)
        self.assertNotIn("identity_gone", s["relay"])

    def test_after_the_change_a_410_counts_again(self):
        s = _settings()
        with mock.patch("net.devkeys.forget"):
            self.assertTrue(relay.moved_away(s, {"gone": True}))
        self.assertTrue(s["relay"].get("identity_gone"))


class Order(unittest.TestCase):
    def test_change_waits_for_a_running_job(self):
        seen = []
        started = threading.Event()

        def job():
            with relay.job():
                started.set()
                time.sleep(0.3)
                seen.append("job done")
        t = threading.Thread(target=job)
        t.start()
        started.wait(2)
        with relay.own_change(wait=5):
            seen.append("change")
        t.join()
        self.assertEqual(seen, ["job done", "change"])

    def test_job_waits_for_the_change(self):
        seen = []
        inside = threading.Event()

        def change():
            with relay.own_change(wait=2):
                inside.set()
                time.sleep(0.3)
                seen.append("change done")
        t = threading.Thread(target=change)
        t.start()
        inside.wait(2)
        with relay.job(wait=5):
            seen.append("job")
        t.join()
        self.assertEqual(seen, ["change done", "job"])

    def test_remove_one_busy_without_sending(self):
        """A job that doesn't end: the change gives up (Busy) and nothing went to the server."""
        release = threading.Event()
        started = threading.Event()

        def job():
            with relay.job():
                started.set()
                release.wait(5)
        t = threading.Thread(target=job)
        t.start()
        started.wait(2)
        try:
            with mock.patch.object(relay, "JOB_WAIT", 0.2), \
                    mock.patch("net.relay._post", side_effect=AssertionError("sent")), \
                    mock.patch("net.vault._post", side_effect=AssertionError("sent")):
                with self.assertRaises(relay.Busy):
                    rekey.remove_one(_settings(), "R" * 16)
                with self.assertRaises(relay.Busy):
                    rekey.change(_settings(), "remove")
        finally:
            release.set()
            t.join()
        self.assertEqual(relay._count, {"jobs": 0, "change": 0})


class Controllers(unittest.TestCase):
    def test_background_steps_count_as_jobs_but_not_the_change(self):
        from net import sync_ctl
        got = {}
        w = mock.Mock()
        done = threading.Event()
        w.bridge.sync_done.emit.side_effect = lambda *a: done.set()
        for step in ("fetch", "poll", "dev_add", "remove_one", "rekey"):
            done.clear()
            sync_ctl.SyncControl._sync_bg.__get__(w)(step, lambda step=step: got.__setitem__(step, relay._count["jobs"]))
            self.assertTrue(done.wait(2))
        self.assertEqual(got, {"fetch": 1, "poll": 1, "dev_add": 1, "remove_one": 0, "rekey": 0})

    def test_mailbox_jobs_count(self):
        from net import relay_ctl
        got = []
        w = mock.Mock()
        done = threading.Event()
        w.bridge.relay_done.emit.side_effect = lambda *a: done.set()
        relay_ctl.RelayControl._relay_bg.__get__(w)("poll", lambda: got.append(relay._count["jobs"]))
        self.assertTrue(done.wait(2))
        self.assertEqual(got, [1])


if __name__ == "__main__":
    unittest.main()
