"""„Bent°Corner löschen“, server part (net/forget.py) against a FAKE mailbox on 127.0.0.1 – never the real server.
legal 03.11.2026: "deleted" only after the server confirmed; anything else = NOT deleted; a deleted ID is never
registered anew; the uninstaller sends only the deletion request.

    python -m unittest tests/test_forget.py
"""
import base64
import http.server
import json
import threading
import unittest

from nacl.signing import VerifyKey

from net import forget, netpolite, relay

from tests import livebox  # noqa: E402
setUpModule, tearDownModule = livebox.module()   # the live box, as a Ship build (DEV split 13.11.)


class Box(http.server.BaseHTTPRequestHandler):
    """Answers like Gordon's mailbox (/v1/forget, /v1/board/del, /v1/register); the test sets `mode`."""
    mode = "deleted"
    seen = []
    keys = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        Box.seen.append((self.path, None))
        if self.path == "/v1/health":
            return self.answer(200, {"ok": True} if Box.mode == "missing" else {"ok": True, "forget": True})
        self.answer(404, None)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        Box.seen.append((self.path, body))
        if self.path == "/v1/register":
            Box.keys[body["code"]] = body["sign_pk"]
            return self.answer(200, {"ok": True})
        if self.path == "/v1/forget":
            if Box.mode == "missing":
                return self.answer(404, None)
            pk = Box.keys.get(body["code"])
            if Box.mode == "unknown" or pk is None:
                return self.answer(403, {"unknown": True})
            try:
                VerifyKey(base64.b64decode(pk)).verify(f"forget|{body['code']}|{body['t']}".encode(),
                                                      base64.b64decode(body["sig"]))
            except Exception:  # noqa: BLE001
                return self.answer(403, {"error": "Unterschrift falsch"})
            if Box.mode == "error":
                return self.answer(500, {"error": "boom"})
            Box.keys.pop(body["code"])
            return self.answer(200, {"ok": True, "deleted": True})
        if self.path == "/v1/board/del":
            return self.answer(200 if Box.mode != "error" else 500, {"ok": True})
        self.answer(404, None)

    def answer(self, status, data):
        raw = b"Not Found" if data is None else json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json" if data is not None else "text/plain")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class Forget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Box)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
        cls._gap = netpolite._gap
        netpolite._gap = lambda *a: 0.0

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        netpolite._gap = cls._gap

    def setUp(self):
        netpolite._next.clear()   # no pause from an earlier test's server error (30 s) or 429
        netpolite._cool.clear()
        Box.mode, Box.seen, Box.keys = "deleted", [], {}
        self.settings = {"relay": {"url": self.url, "on": True}}
        relay.register(self.settings)   # a throwaway ID, only on the fake mailbox
        self.settings["relay"]["posted"] = {"mtg/lists": {"to": []}, "mtg/binder-1": {"to": []}}
        Box.seen = []

    def test_b_deleted_only_when_confirmed(self):
        r = forget.delete_server(self.settings)
        self.assertEqual(r.status, forget.DELETED)
        self.assertEqual(r.exit_code, 0)
        self.assertEqual([p for p, _ in Box.seen], ["/v1/health", "/v1/forget"])
        body = Box.seen[1][1]
        self.assertEqual(set(body), {"code", "t", "sig"})
        for k in ("registered", "seed"):   # nothing left that points to the deleted ID, no re-registering
            self.assertNotIn(k, self.settings["relay"])

    def test_unknown_is_already_deleted_and_never_registers_again(self):
        Box.mode = "unknown"
        r = forget.forget(self.settings)
        self.assertEqual(r.status, forget.ALREADY)
        self.assertNotIn("/v1/register", [p for p, _ in Box.seen])

    def test_failure_is_not_deleted_and_names_the_id(self):
        for mode in ("error",):
            Box.mode = mode
            r = forget.forget(self.settings)
            self.assertEqual(r.status, forget.FAILED)
            self.assertFalse(r.ok)
            self.assertEqual(r.code, relay.pretty(relay.my_code(self.settings)))
            self.assertIn("registered", self.settings["relay"])   # nothing forgotten locally

    def test_offline_is_not_deleted(self):
        self.settings["relay"]["url"] = "http://127.0.0.1:9"   # nobody listens there
        r = forget.delete_server(self.settings)
        self.assertEqual(r.status, forget.FAILED)
        self.assertEqual(r.exit_code, 3)

    def test_a_until_forget_is_live(self):
        Box.mode = "missing"
        r = forget.delete_server(self.settings, notify=False)
        self.assertEqual(r.status, forget.DELETED)
        paths = [p for p, _ in Box.seen]
        self.assertEqual(paths[0], "/v1/health")
        self.assertNotIn("/v1/forget", paths)   # A never asks more than its text says
        self.assertEqual(sorted(b["slot"] for p, b in Box.seen if p == "/v1/board/del"), ["binder-1", "lists"])
        self.assertEqual(set(paths), {"/v1/health", "/v1/board/del"})   # uninstaller: nothing else
        self.assertEqual(self.settings["relay"]["posted"], {})

    def test_version_from_health(self):
        self.assertTrue(forget.available(self.settings))
        Box.mode = "missing"
        self.assertFalse(forget.available(self.settings))
        self.settings["relay"]["url"] = "http://127.0.0.1:9"
        self.assertFalse(forget.available(self.settings))   # offline: A

    def test_no_id_nothing_to_do(self):
        r = forget.delete_server({"relay": {"url": self.url}}, full=True)
        self.assertEqual(r.status, forget.NO_ID)
        self.assertEqual(Box.seen, [])

    def test_deadlines_match_the_texts(self):
        self.assertEqual((forget.BOARD_DAYS, forget.KEY_DAYS, forget.PARCEL_DAYS), (180, 365, 14))


if __name__ == "__main__":
    unittest.main()
