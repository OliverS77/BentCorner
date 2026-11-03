"""Updates without the real server (test plan 1.11): a test release signed with a test key – manifest signature,
download in chunks, checksum; forged or broken = never installed. "What's new": at most 5 points per shipped
version, all translated.

    python -m unittest tests/test_updates.py
"""
import base64
import hashlib
import json
import pathlib
import re
import tempfile
import time
import unittest
from unittest import mock

from nacl.signing import SigningKey

import version
from locales import de
from net import netpolite, updater

KEY = SigningKey.generate()
PUB = base64.b64encode(bytes(KEY.verify_key)).decode()
EXE = b"MZ fake exe " * 400_000   # ~4.8 MB: three chunks of 2 MB


def manifest(latest="9.9.9", data=EXE):
    m = {"v": 1, "latest": latest, "date": "2026-10-26", "notes": ["test"],
         "platforms": {updater.platform_key(): {"file": "BentCorner-9.9.9.exe", "size": len(data),
                                                "sha256": hashlib.sha256(data).hexdigest()}}}
    raw = json.dumps(m).encode()
    return raw, base64.b64encode(KEY.sign(raw).signature).decode()


class _R:
    def __init__(self, code, content=b"", text=""):
        self.status_code, self.content, self.text = code, content, text or content.decode("latin-1")


class Server:
    """Fake update server: manifest, signature, the exe in Range chunks."""
    def __init__(self, raw, sig, data=EXE):
        self.raw, self.sig, self.data, self.calls = raw, sig, data, []

    def get(self, url, headers=None, **kw):
        self.calls.append(url)
        if url.endswith("manifest.json"):
            return _R(200, self.raw)
        if url.endswith("manifest.json.sig"):
            return _R(200, text=self.sig)
        rng = (headers or {}).get("Range")
        a, b = map(int, re.match(r"bytes=(\d+)-(\d+)", rng).groups())
        return _R(206, self.data[a:b + 1])


class Updates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = [mock.patch.object(updater, "PUBLIC_KEY", PUB),
                  mock.patch.object(updater, "folder", lambda: pathlib.Path(self.tmp.name)),
                  mock.patch.object(version, "VERSION", "0.9.2")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def run_check(self, srv):
        u = updater.Updater(base="https://test.invalid/dl-test", news=lambda: False)
        with mock.patch.object(netpolite, "get", srv.get):
            u.check(auto_download=True)
            for _ in range(500):
                if u.state in ("none", "ready", "error"):
                    break
                time.sleep(0.01)
        return u

    def test_signed_release_downloads_and_is_ready(self):
        u = self.run_check(Server(*manifest()))
        self.assertEqual(u.state, "ready", u.error)
        self.assertEqual(u.target().read_bytes(), EXE)
        self.assertFalse(u.target().with_name(u.target().name + ".part").exists())

    def test_forged_manifest_refused(self):
        raw, sig = manifest()
        u = self.run_check(Server(raw.replace(b"9.9.9", b"9.9.8"), sig))   # changed after signing
        self.assertEqual((u.state, u.error), ("error", "Invalid update signature – not used"))
        other = SigningKey.generate()
        u = self.run_check(Server(raw, base64.b64encode(other.sign(raw).signature).decode()))   # someone else's key
        self.assertEqual(u.state, "error")

    def test_wrong_checksum_discarded(self):
        raw, sig = manifest()
        u = self.run_check(Server(raw, sig, data=EXE[:-1] + b"X"))     # the file on the server was swapped
        self.assertEqual(u.state, "error")
        self.assertIn("Checksum", u.error)
        left = [x.name for x in pathlib.Path(self.tmp.name).iterdir() if x.name != "last_check_day.txt"]
        self.assertEqual(left, [])   # no half or wrong exe left behind (only the daily check marker)

    def test_not_newer_nothing_downloaded(self):
        srv = Server(*manifest(latest="0.9.1"))
        u = self.run_check(srv)
        self.assertEqual(u.state, "none")
        self.assertFalse(any("BentCorner" in c for c in srv.calls))

    def test_install_only_in_the_exe(self):
        u = self.run_check(Server(*manifest()))
        self.assertFalse(u.can_install())   # not frozen: a test never replaces a real exe
        with self.assertRaises(updater.UpdateError):
            u.install()

    def test_version_order(self):
        self.assertTrue(updater.newer("0.9.10", "0.9.9"))
        self.assertTrue(updater.newer("1.0", "0.9.2.20"))
        self.assertFalse(updater.newer("0.9.2", "0.9.2.0"))


class Highlights(unittest.TestCase):
    def test_at_most_five_per_shipped_version_and_translated(self):
        self.assertTrue(version.HIGHLIGHTS)
        for v, points in version.HIGHLIGHTS.items():
            self.assertTrue(version.is_release(v), f"{v}: only shipped (three-part) versions")
            self.assertTrue(1 <= len(points) <= 5, f"{v}: {len(points)} points")
            for p in points:
                self.assertLess(len(p), 300, p[:40])
                self.assertIn(p, de.TEXTS, f"not translated: {p[:50]}")


if __name__ == "__main__":
    unittest.main()
