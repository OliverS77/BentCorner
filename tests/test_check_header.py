"""Own tests don't count in the download statistics (Oliver 03.11.2026): with BC_CHECK=1 or in an isolated test run
(BC_STARTER_* folders) requests to our own server carry "X-BC-Check: 1" (net/netpolite.py) – normal installations and
requests to other services never.

    python -m unittest tests/test_check_header.py
"""
import os
import types
import unittest
from unittest import mock

from net import netpolite
from system import contacts, datahome


class CheckHeader(unittest.TestCase):
    def sent(self, url, env=None, isolated=False):
        seen = {}

        def fake(method, u, host, headers=None, **kw):
            seen.update(headers or {})
            return types.SimpleNamespace(status_code=200, headers={}, ok=True)
        with mock.patch.object(netpolite, "_request", fake), mock.patch.object(datahome, "ISOLATED", isolated), \
                mock.patch.dict(os.environ, env or {}, clear=False), mock.patch.object(netpolite, "_gap", lambda *a: 0.0):
            if not env:
                os.environ.pop("BC_CHECK", None)
            netpolite._send_one("GET", url)
        return seen

    def test_switch_on_own_server(self):
        url = contacts.SERVER + "/dl/manifest.json"
        self.assertEqual(self.sent(url, {"BC_CHECK": "1"}).get("X-BC-Check"), "1")
        self.assertEqual(self.sent(url, isolated=True).get("X-BC-Check"), "1")

    def test_normal_installation_never(self):
        self.assertNotIn("X-BC-Check", self.sent(contacts.SERVER + "/dl/manifest.json"))

    def test_other_services_never(self):
        self.assertNotIn("X-BC-Check", self.sent("https://api.scryfall.com/sets", {"BC_CHECK": "1"}))


if __name__ == "__main__":
    unittest.main()
