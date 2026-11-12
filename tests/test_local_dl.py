"""Test switch BC_LOCAL_DL (first-start copy, lead 04.11.2026): requests are answered from a local folder – only in an
isolated test run (BC_STARTER_* set), ignored otherwise. Signature and checksum checks stay as they are: a changed pack
list or pack file in the local folder is refused."""
import base64
import hashlib
import json
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

import requests

from net import netpolite
from net import updater as _updater
from system import datahome

REAL_KEY = _updater.PUBLIC_KEY   # ours, before a test swaps it


class Base(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="bc-localdl-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self._saved = list(netpolite._local_root)
        self.addCleanup(lambda: netpolite._local_root.__setitem__(slice(None), self._saved))
        netpolite._local_root[:] = [None, False]
        env = mock.patch.dict(os.environ, {"BC_LOCAL_DL": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        pace = mock.patch.object(netpolite, "LOCAL_RATE", 1 << 40)
        pace.start()
        self.addCleanup(pace.stop)

    def put(self, url, data, method="GET", body=None):
        p = self.root / netpolite.local_name(method, url, body)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p


class Switch(Base):
    def test_ignored_without_an_isolated_test_run(self):
        # what a normal installation sees (no BC_STARTER_*): the variable alone changes nothing
        with mock.patch.object(datahome, "ISOLATED", False):
            self.assertIsNone(netpolite.local_dl())
            self.put("https://bentcorner.app/dl/x.txt", b"local")
            with mock.patch.object(requests, "request", return_value="network") as net:
                self.assertEqual(netpolite._request("GET", "https://bentcorner.app/dl/x.txt", "bentcorner.app"),
                                 "network")
            net.assert_called_once()

    def test_isolated_is_ISOLATED_from_the_starter_variables(self):
        # the exe decides it the same way: ISOLATED comes only from BC_STARTER_LOCAL/ROAMING/DOCUMENTS
        src = pathlib.Path(datahome.__file__).read_text("utf-8")
        self.assertIn('ISOLATED = any(os.environ.get(v, "").strip() for v in ("BC_STARTER_LOCAL", "BC_STARTER_ROAMING", '
                      '"BC_STARTER_DOCUMENTS"))', src)

    def test_on_in_an_isolated_test_run(self):
        with mock.patch.object(datahome, "ISOLATED", True):
            self.assertEqual(netpolite.local_dl(), os.path.abspath(str(self.root)))


class Answers(Base):
    def setUp(self):
        super().setUp()
        iso = mock.patch.object(datahome, "ISOLATED", True)
        iso.start()
        self.addCleanup(iso.stop)
        self.net = mock.patch.object(requests, "request", side_effect=AssertionError("network used"))
        self.net.start()
        self.addCleanup(self.net.stop)

    def test_file_range_missing(self):
        self.put("https://bentcorner.app/dl/packs/packs.json", b"0123456789")
        r = netpolite._request("GET", "https://bentcorner.app/dl/packs/packs.json", "bentcorner.app")
        self.assertEqual((r.status_code, r.content), (200, b"0123456789"))
        r = netpolite._request("GET", "https://bentcorner.app/dl/packs/packs.json", "bentcorner.app",
                               headers={"Range": "bytes=4-"}, stream=True)
        self.assertEqual(r.status_code, 206)
        self.assertEqual(b"".join(r.iter_content(3)), b"456789")
        self.assertEqual(r.headers["Content-Range"], "bytes 4-9/10")
        r = netpolite._request("GET", "https://bentcorner.app/dl/packs/packs.json", "bentcorner.app",
                               headers={"Range": "bytes=10-"})
        self.assertEqual(r.status_code, 416)
        with self.assertRaises(requests.ConnectionError):   # not in the copy = not reachable, never the network
            netpolite._request("GET", "https://bentcorner.app/dl/other.json", "bentcorner.app")

    def test_query_and_post_body_are_separate_files(self):
        self.put("https://api.example.org/q?page=1", b"one")
        self.put("https://api.example.org/q?page=2", b"two")
        self.put("https://api.example.org/gql", b"A", "POST", json.dumps({"q": "a"}))
        self.assertEqual(netpolite._request("GET", "https://api.example.org/q?page=2", "api.example.org").content, b"two")
        self.assertEqual(netpolite._request("POST", "https://api.example.org/gql", "api.example.org",
                                            json={"q": "a"}).content, b"A")
        with self.assertRaises(requests.ConnectionError):
            netpolite._request("POST", "https://api.example.org/gql", "api.example.org", json={"q": "b"})

    def test_never_outside_the_folder(self):
        name = netpolite.local_name("GET", "https://bentcorner.app/dl/../../../secret.txt")
        self.assertNotIn("..", pathlib.Path(name).parts)


class Signed(Base):
    """packs.manifest/download over the switch: the real checks, with a throwaway key instead of ours."""

    def setUp(self):
        super().setUp()
        from nacl.signing import SigningKey
        from cards import packs
        from net import updater
        self.packs, self.updater = packs, updater
        self.key = SigningKey.generate()
        for p in (mock.patch.object(datahome, "ISOLATED", True),
                  mock.patch.object(requests, "request", side_effect=AssertionError("network used")),
                  mock.patch.object(updater, "PUBLIC_KEY", base64.b64encode(bytes(self.key.verify_key)).decode()),
                  mock.patch.object(packs, "ROOT", self.root / "data-packs")):
            p.start()
            self.addCleanup(p.stop)
        import io
        import numpy as np
        npz = io.BytesIO()   # real file kinds: every pack file is probed before it is put in place (cards/datakeys)
        np.savez(npz, ids=np.array(["a", "b"]), vecs=np.zeros((2, 4), np.float16))
        kinds = {".npz": npz.getvalue(), ".json": b'{"fingerprints": 1}'}
        self.content = {f: kinds.get(pathlib.Path(f).suffix, b"fingerprints" * 100) for f in packs.PACKS["mtg"]["files"]}
        self.data = self.content[packs.PACKS["mtg"]["files"][0]]
        self.base = packs.base_url()
        entry = {"files": [{"name": f, "size": len(c), "sha256": hashlib.sha256(c).hexdigest()}
                           for f, c in self.content.items()]}
        self.raw = json.dumps({"packs": {"mtg": entry}}).encode()
        self.put(self.base + "/packs.json", self.raw)
        self.put(self.base + "/packs.json.sig", base64.b64encode(self.key.sign(self.raw).signature))
        self.files = [self.put(f"{self.base}/{packs.PACKS['mtg']['dir']}/{f}", c) for f, c in self.content.items()]

    def test_genuine_copy_installs(self):
        self.packs.download("mtg")
        for f in self.packs.PACKS["mtg"]["files"]:
            self.assertEqual((self.packs.folder("mtg") / f).read_bytes(), self.content[f])

    def test_changed_pack_list_is_refused(self):
        self.put(self.base + "/packs.json", self.raw.replace(b"fingerprints", b"fingerprintz") + b" ")
        with self.assertRaises(self.packs.PackError):
            self.packs.manifest()

    def test_changed_pack_file_is_refused(self):
        self.files[0].write_bytes(b"x" + self.data[1:])
        with self.assertRaises(self.packs.PackError):
            self.packs.download("mtg")
        self.assertFalse((self.packs.folder("mtg") / self.packs.PACKS["mtg"]["files"][0]).exists())

    def test_our_key_does_not_accept_a_self_signed_list(self):
        with mock.patch.object(self.updater, "PUBLIC_KEY", REAL_KEY):
            with self.assertRaises(self.packs.PackError):
                self.packs.manifest()


if __name__ == "__main__":
    unittest.main()
