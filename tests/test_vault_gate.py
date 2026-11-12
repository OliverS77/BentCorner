"""Sync test server (lead/Gordon 06.11.): BC_SYNC_BASE only from the source; the gate code for
bentcorner.app/testapp/box lives only in memory and goes only as the cookie bc_gate to exactly that address –
never to another host, never over http, never into the settings or the log, and nothing pre-fills it.

    python -m unittest tests/test_vault_gate.py
"""
import json
import logging
import os
import pathlib
import sys
import unittest
from unittest import mock

from collection import syncrun
from net import netpolite, relay, vault

GATE = "geheim-TEST-7Q"   # a made-up code – the real one never appears anywhere
LIVE = "https://bentcorner.app/testapp/box"


class Answer:
    status_code = 200
    headers = {"Date": "Fri, 06 Nov 2026 21:00:00 GMT"}

    def __init__(self, data=None):
        self.data = data or {"version": 0, "items": []}

    def json(self):
        return self.data


def env(base):
    return mock.patch.dict(os.environ, {"BC_SYNC": "1", "BC_SYNC_BASE": base})


class Base(unittest.TestCase):
    def test_only_from_the_source_with_the_switch(self):
        with env(LIVE + "/"):
            self.assertEqual(syncrun.test_base(), LIVE)
            with mock.patch.object(sys, "frozen", True, create=True):
                self.assertIsNone(syncrun.test_base(), "a built exe never follows BC_SYNC_BASE")
        with mock.patch.dict(os.environ, {"BC_SYNC": "", "BC_SYNC_BASE": LIVE}):
            self.assertIsNone(syncrun.test_base(), "without BC_SYNC=1 nothing changes")

    def test_gated_is_exactly_the_test_instance(self):
        self.assertTrue(vault._gated(LIVE + "/v1/vault/get"))
        for url in ("http://bentcorner.app/testapp/box/v1/vault/get",          # not over http
                    "https://bentcorner.app/v1/vault/get",                      # the real mailbox
                    "https://bentcorner.app/testapp/boxer/v1",                  # another path
                    "https://bentcorner.app.example.com/testapp/box/v1",       # another host
                    "https://evil.example/testapp/box/v1",
                    "http://127.0.0.1:8799/v1/vault/get"):
            self.assertFalse(vault._gated(url), url)


class Cookie(unittest.TestCase):
    def setUp(self):
        self.settings = {"relay": {}}
        self.addCleanup(vault.set_gate, None)
        vault.set_gate(None)
        vault._reregistered[0] = 0.0

    def run_get(self, base):
        sent = {"requests": [], "netpolite": []}

        def req(url, **kw):
            sent["requests"].append((url, kw))
            return Answer()

        def pol(url, **kw):
            sent["netpolite"].append((url, kw))
            return Answer()
        with env(base), mock.patch("requests.post", req), mock.patch.object(netpolite, "post", pol):
            vault.get(self.settings, 0)
        return sent

    def test_local_box_never_gets_a_cookie(self):
        vault._gate[0] = GATE
        sent = self.run_get("http://127.0.0.1:8799")
        self.assertEqual(sent["requests"], [])
        self.assertEqual([u for u, _ in sent["netpolite"]],
                         ["http://127.0.0.1:8799/v1/register", "http://127.0.0.1:8799/v1/vault/get"])
        self.assertTrue(all("cookies" not in kw for _, kw in sent["netpolite"]))

    def test_test_instance_gets_it_directly_and_only_there(self):
        vault._gate[0] = GATE
        sent = self.run_get(LIVE)
        self.assertEqual(sent["netpolite"], [], "not through netpolite (its fallback would carry the cookie along)")
        self.assertEqual([u for u, _ in sent["requests"]], [LIVE + "/v1/register", LIVE + "/v1/vault/get"])
        for _, kw in sent["requests"]:
            self.assertEqual(kw["cookies"], {"bc_gate": GATE})
            self.assertFalse(kw["allow_redirects"])

    def test_registered_once_per_test_server(self):
        vault._gate[0] = GATE
        self.run_get(LIVE)
        sent = self.run_get(LIVE)
        self.assertEqual([u for u, _ in sent["requests"]], [LIVE + "/v1/vault/get"])
        self.assertNotIn("registered", self.settings["relay"], "the real mailbox's registration is untouched")

    def test_emptied_test_server_registers_again_once(self):
        """Gordon empties the test instance (or ports' box starts fresh): "unknown" -> register anew, once, retry."""
        vault._gate[0] = GATE
        self.run_get(LIVE)                                     # registered once
        calls, answers = [], [Answer({"error": "Adresse unbekannt", "unknown": True}), Answer(), Answer()]

        def req(url, **kw):
            calls.append(url)
            a = answers.pop(0)
            a.status_code = 403 if a.data.get("unknown") else 200
            return a
        with env(LIVE), mock.patch("requests.post", req):
            vault.get(self.settings, 0)
        self.assertEqual(calls, [LIVE + "/v1/vault/get", LIVE + "/v1/register", LIVE + "/v1/vault/get"])
        self.assertEqual(self.settings["relay"]["test_registered"], LIVE)

    def test_registering_anew_at_most_once_in_15_minutes(self):
        """Each new registration uses one of the server's 5 new addresses an hour (lead 06.11.): a second "unknown"
        shortly after is an error, not another registration."""
        vault._gate[0] = GATE
        self.settings["relay"]["test_registered"] = LIVE   # registered long ago: only registering ANEW is counted
        calls = []

        def req(url, **kw):
            calls.append(url)
            a = Answer({"error": "Adresse unbekannt", "unknown": True} if url.endswith("/vault/get") else None)
            a.status_code = 403 if url.endswith("/vault/get") else 200
            return a
        with env(LIVE), mock.patch("requests.post", req):
            for _ in range(3):   # three runs in a row
                with self.assertRaises(vault.VaultError):
                    vault.get(self.settings, 0)
        self.assertEqual(calls.count(LIVE + "/v1/register"), 1)
        vault._reregistered[0] -= vault.REREGISTER_GAP + 1   # 15 minutes later: once more
        with env(LIVE), mock.patch("requests.post", req), self.assertRaises(vault.VaultError):
            vault.get(self.settings, 0)
        self.assertEqual(calls.count(LIVE + "/v1/register"), 2)

    def test_still_unknown_after_registering_is_an_error_not_a_loop(self):
        vault._gate[0] = GATE
        calls = []

        def req(url, **kw):
            calls.append(url)
            a = Answer({"error": "Adresse unbekannt", "unknown": True} if url.endswith("/vault/get") else None)
            a.status_code = 403 if url.endswith("/vault/get") else 200
            return a
        with env(LIVE), mock.patch("requests.post", req), self.assertRaises(vault.VaultError) as e:
            vault.get(self.settings, 0)
        self.assertEqual(e.exception.status, 403)
        self.assertEqual(calls.count(LIVE + "/v1/vault/get"), 2)

    def test_without_the_code_nothing_is_sent(self):
        with env(LIVE), mock.patch("requests.post") as req, mock.patch.object(netpolite, "post") as pol:
            self.assertTrue(vault.gate_needed())
            with self.assertRaises(vault.VaultError) as e:
                vault.get(self.settings, 0)
        self.assertEqual(e.exception.status, 401)
        req.assert_not_called()
        pol.assert_not_called()

    def test_the_code_stays_out_of_settings_log_and_errors(self):
        vault._gate[0] = GATE
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("booster").info("marker")
            self.run_get(LIVE)

            def boom(url, **kw):
                raise RuntimeError(f"failed with {kw.get('cookies')}")
            with env(LIVE), mock.patch("requests.post", boom), self.assertRaises(vault.VaultError) as e:
                vault.get(self.settings, 0)
        self.assertNotIn(GATE, json.dumps(self.settings))
        self.assertNotIn(GATE, "\n".join(logs.output))
        self.assertNotIn(GATE, str(e.exception))

    def test_the_sync_row_says_what_is_wrong(self):
        from net import sync_ctl
        with env(LIVE), mock.patch("system.i18n.tr", lambda s: s), mock.patch.object(sync_ctl, "tr", lambda s: s):
            self.assertEqual(sync_ctl.problem_text(vault.VaultError(401, "x")),
                             "The access code for the test server is missing.")
            vault._gate[0] = GATE
            self.assertEqual(sync_ctl.problem_text(vault.VaultError(403, "x")),
                             "The test server didn't accept the access code.")
        with mock.patch.object(sync_ctl, "tr", lambda s: s), mock.patch.dict(os.environ, {"BC_SYNC": ""}):
            self.assertEqual(sync_ctl.problem_text(vault.VaultError(403, "x")), "Sync did not work – tries again later")

    def test_nothing_prefills_the_code(self):
        """No environment variable, setting or file feeds the gate – it only comes from set_gate (typed in)."""
        src = pathlib.Path(vault.__file__).read_text("utf-8")
        self.assertNotIn("environ", src)
        self.assertNotIn("settings[\"gate", src)
        with env(LIVE), mock.patch.dict(os.environ, {"BC_GATE": GATE, "BC_SYNC_GATE": GATE}):
            vault.set_gate(None)
            self.assertTrue(vault.gate_needed())


class Exchange(unittest.TestCase):
    """Gordon 06.11.: the server wants the TOKEN as bc_gate, not the code – the code goes once to /v1/gate (like the
    browser's code.html), the token comes back as Set-Cookie; only the token is kept, the code never."""

    def setUp(self):
        self.addCleanup(vault.set_gate, None)

    class R:
        def __init__(self, status, token=None):
            self.status_code = status
            self.cookies = {"bc_gate": token} if token else {}

    def test_code_goes_to_gate_token_is_kept(self):
        sent = []

        def req(url, **kw):
            sent.append((url, kw))
            return self.R(200, "tok-123")
        with mock.patch("requests.post", req):
            vault.set_gate("  mein-code  ")
        self.assertEqual(sent[0][0], "https://bentcorner.app/v1/gate")
        self.assertEqual(sent[0][1]["json"], {"code": "mein-code"})
        self.assertFalse(sent[0][1]["allow_redirects"])
        self.assertEqual(vault._gate[0], "tok-123", "the token, not the code")
        self.assertNotIn("mein-code", repr(vars(vault)))

    def test_wrong_code_and_too_many_tries(self):
        for status, want in ((403, "Wrong access code."), (429, "Too many tries – please try again later.")):
            with mock.patch("requests.post", lambda url, **kw: self.R(status)), \
                    mock.patch.object(vault, "tr", lambda s: s), self.assertRaises(vault.VaultError) as e:
                vault.set_gate("falsch")
            self.assertEqual(e.exception.status, status)
            self.assertEqual(str(e.exception), want)
            self.assertIsNone(vault._gate[0])

    def test_box_requests_carry_the_token(self):
        with mock.patch("requests.post", lambda url, **kw: self.R(200, "tok-9")):
            vault.set_gate("code")
        calls = []

        def req(url, **kw):
            calls.append(kw.get("cookies"))
            return Answer()
        with env(LIVE), mock.patch("requests.post", req):
            vault.get({"relay": {"test_registered": LIVE}}, 0)
        self.assertEqual(calls, [{"bc_gate": "tok-9"}])


if __name__ == "__main__":
    unittest.main()


class MailboxGate(unittest.TestCase):
    """lead/Gordon 07.11.: the test instance lets nothing through without the gate – the mailbox (relay), the key
    lookup and forget send the same token, ONLY below /testapp/ on our host; never to the live mailbox, never logged."""

    def setUp(self):
        self.addCleanup(vault.set_gate, None)
        vault._gate[0] = GATE
        self.sent = {"requests": [], "netpolite": []}

    def call(self, base, fn):
        def req(url, **kw):
            self.sent["requests"].append((url, kw))
            return Answer({"ok": True, "sign_pk": ""})

        def pol(url, **kw):
            self.sent["netpolite"].append((url, kw))
            return Answer({"ok": True})
        settings = {"relay": {"url": base}}
        with mock.patch("requests.post", req), mock.patch("requests.get", req), \
                mock.patch.object(netpolite, "post", pol), mock.patch.object(netpolite, "get", pol):
            try:
                fn(settings)
            except relay.RelayError:
                pass
        return settings

    def test_live_mailbox_never_gets_the_cookie(self):
        self.call("https://bentcorner.app", lambda s: relay._post(s, "/v1/send", {"code": "X"}))
        self.call("https://bentcorner.app", lambda s: relay.lookup(s, "ABCDEFGH23456789"))
        self.assertEqual(self.sent["requests"], [], "the live mailbox goes through netpolite, without a cookie")
        self.assertTrue(self.sent["netpolite"])
        self.assertNotIn(GATE, repr(self.sent["netpolite"]))

    def test_test_instance_mailbox_gets_it(self):
        self.call(LIVE, lambda s: relay._post(s, "/v1/send", {"code": "X"}))
        self.call(LIVE, lambda s: relay.lookup(s, "ABCDEFGH23456789"))
        from net import forget
        self.call(LIVE, lambda s: forget._raw_post(s, "/v1/forget", {"code": "X"}))
        self.assertEqual(self.sent["netpolite"], [])
        self.assertEqual(len(self.sent["requests"]), 3)
        for url, kw in self.sent["requests"]:
            self.assertTrue(url.startswith(LIVE + "/v1/"), url)
            self.assertEqual(kw["cookies"], {vault.GATE_COOKIE: GATE})
            self.assertFalse(kw["allow_redirects"])

    def test_the_token_is_in_no_log(self):
        with self.assertLogs(level="DEBUG") as logs:
            logging.getLogger().debug("start")
            self.call(LIVE, lambda s: relay._post(s, "/v1/send", {"code": "X"}))
            self.call("https://bentcorner.app", lambda s: relay._post(s, "/v1/send", {"code": "X"}))
        self.assertNotIn(GATE, "\n".join(logs.output))

    def test_without_the_code_nothing_goes_out(self):
        vault._gate[0] = None
        caught = []

        def run(s):
            try:
                relay._post(s, "/v1/send", {"code": "X"})
            except relay.RelayError as err:
                caught.append(err.status)
        self.call(LIVE, run)
        self.assertEqual(caught, [401])
        self.assertEqual(self.sent["requests"] + self.sent["netpolite"], [])
        from net import forget
        s = {"relay": {"url": LIVE, "seed": "A" * 43 + "=", "registered": "x"}}
        r = forget.forget(s)
        self.assertEqual(r.status, forget.FAILED)
        self.assertFalse(getattr(r, "offline", False), "a missing gate code is never „offline“ – nothing is wiped")
