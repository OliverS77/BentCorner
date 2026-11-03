"""netpolite: a server error (5xx) pauses that service like a 429 – except our own server (fallback instead).

    python -m unittest tests/test_netpolite_backoff.py
"""
import unittest
from unittest import mock

from net import netpolite


class _R:
    def __init__(self, code, retry=None):
        self.status_code = code
        self.headers = {"Retry-After": retry} if retry else {}


class Backoff(unittest.TestCase):
    def setUp(self):
        netpolite._cool.clear()
        netpolite._next.clear()

    def _call(self, url, resp):
        with mock.patch.object(netpolite.requests, "request", return_value=resp), \
                mock.patch.object(netpolite.time, "sleep"):
            return netpolite.get(url)

    def test_503_pauses_service(self):
        self._call("https://api.lorcast.com/v0/sets", _R(503))
        self.assertGreaterEqual(netpolite.cooling("https://api.lorcast.com/v0/sets"), 29)

    def test_retry_after_longer_wins(self):
        self._call("https://rifthunt.com/api/bulk/cards", _R(503, "120"))
        self.assertGreater(netpolite.cooling("https://rifthunt.com/x"), 100)

    def test_own_server_not_paused(self):
        self._call("https://bentcorner.oliver-schunn.tech/prices/x.json.gz", _R(502))
        self.assertEqual(netpolite.cooling("https://bentcorner.oliver-schunn.tech/v1/health"), 0)

    def test_ok_and_404_no_pause(self):
        self._call("https://lorcanajson.org/files/current/en/metadata.json", _R(404))
        self.assertEqual(netpolite.cooling("https://lorcanajson.org/"), 0)

    def test_new_hosts_conservative(self):
        for host in ("lorcanajson.org", "api.lorcast.com", "api.lorcana.ravensburger.com",
                     "rifthunt.com", "api.riftcodex.com", "cmsassets.rgpub.io",
                     "europe.api.riotgames.com"):
            self.assertGreaterEqual(netpolite.POLICY[host], 0.25, host)


if __name__ == "__main__":
    unittest.main()
