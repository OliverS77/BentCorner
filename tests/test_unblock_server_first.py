"""Unblock – server first (lead 08.11., PC = web): /v1/block on:0 first; only when the server took it the entry goes here.
Offline or an error: nothing changes, relay_unblock_state says „failed“.

    python -m unittest tests.test_unblock_server_first
"""
import base64
import unittest
from unittest import mock

from net import relay, relay_ctl

SEED = base64.b64encode(b"\x11" * 32).decode()
CODE = "BBBBBBBBBBBBBBBB"


def _ctl(on=True):
    c = mock.Mock()
    c.relay_unblock_state = None
    c.settings = {"relay": {"on": on, "seed": SEED, "friends": {CODE: {"status": "blocked", "name": "X",
                                                                        "on_server": True}}}}
    jobs = []
    c._relay_bg = lambda what, fn: jobs.append((what, fn))
    c._unblock_local = lambda code: relay_ctl.RelayControl._unblock_local(c, code)
    c._unblock_done = lambda code, res, err: relay_ctl.RelayControl._unblock_done(c, code, res, err)
    return c, jobs


def _run(c, jobs):
    what, fn = jobs.pop()
    try:
        res, err = fn(), ""
    except Exception as e:  # noqa: BLE001 – what _relay_bg does
        res, err = None, str(e)
    relay_ctl.RelayControl._relay_done(c, what, res, err)


class ServerFirst(unittest.TestCase):
    def test_offline_changes_nothing(self):
        c, jobs = _ctl()
        with mock.patch("net.relay._post", side_effect=relay.RelayError("offline", 0)), \
                mock.patch("net.relay.register"):
            relay_ctl.RelayControl.relay_unblock(c, CODE)
            self.assertEqual(c.relay_unblock_state, {CODE: "busy"})
            self.assertIn(CODE, c.settings["relay"]["friends"], "nothing changes before the server answered")
            _run(c, jobs)
        self.assertEqual(c.relay_unblock_state, {CODE: "offline"})
        self.assertEqual(c.settings["relay"]["friends"][CODE]["status"], "blocked")

    def test_server_refusal_is_failed(self):
        c, jobs = _ctl()
        with mock.patch("net.relay._post", side_effect=relay.RelayError("nein", 403)), mock.patch("net.relay.register"):
            relay_ctl.RelayControl.relay_unblock(c, CODE)
            _run(c, jobs)
        self.assertEqual(c.relay_unblock_state, {CODE: "failed"})
        self.assertEqual(c.settings["relay"]["friends"][CODE]["status"], "blocked")

    def test_server_took_it(self):
        c, jobs = _ctl()
        sent = []
        with mock.patch("net.relay._post", lambda s, path, p, **k: sent.append((path, p["on"])) or {}), \
                mock.patch("net.relay.register"):
            relay_ctl.RelayControl.relay_unblock(c, CODE)
            _run(c, jobs)
        self.assertEqual(sent, [("/v1/block", 0)])
        self.assertNotIn(CODE, c.settings["relay"]["friends"])
        self.assertEqual(c.relay_unblock_state, {})

    def test_mailbox_off_changes_nothing(self):
        """lead 08.11.: blocked in Full Orbit, then Core (mailbox off): unblocking only here would leave the server's
        block – the person would silently not reach this ID back in Full Orbit. So nothing changes."""
        c, jobs = _ctl(on=False)
        relay_ctl.RelayControl.relay_unblock(c, CODE)
        self.assertEqual(jobs, [])
        self.assertEqual(c.settings["relay"]["friends"][CODE]["status"], "blocked")
        self.assertEqual(c.relay_unblock_state, {CODE: "mailbox_off"})


    def test_local_only_block_with_mailbox_off(self):
        """lead 08.11.: a block that never reached the server (a file import, or blocked while the mailbox was off)
        stays unblockable with the mailbox off – at once, only here."""
        c, jobs = _ctl(on=False)
        c.settings["relay"]["friends"][CODE] = {"status": "blocked", "name": "X"}   # no mark, no sign key
        relay_ctl.RelayControl.relay_unblock(c, CODE)
        self.assertEqual(jobs, [])
        self.assertNotIn(CODE, c.settings["relay"]["friends"])

    def test_older_mailbox_block_counts_as_server(self):
        c, jobs = _ctl(on=False)
        c.settings["relay"]["friends"][CODE] = {"status": "blocked", "name": "X", "sign_pk": "pk"}   # before the mark
        relay_ctl.RelayControl.relay_unblock(c, CODE)
        self.assertEqual(c.relay_unblock_state, {CODE: "mailbox_off"})

    def test_server_block_marks_it(self):
        s = {"relay": {"on": True, "seed": SEED, "friends": {CODE: {"status": "blocked"}}}}
        with mock.patch("net.relay._post", return_value={}), mock.patch("net.relay.register"):
            self.assertTrue(relay.server_block(s, CODE, True))
        self.assertTrue(s["relay"]["friends"][CODE]["on_server"])


if __name__ == "__main__":
    unittest.main()
