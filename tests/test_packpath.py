"""Pack files under hashed names ("path") in packs-data2.json (own prefix v2) and the fingerprint add-on
(docs/FP-ADD-FORMAT.md) – lead/Gordon 14.11.2026. Keys are made here and thrown away; no network.

    python -m unittest tests.test_packpath
"""
import base64
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import numpy as np
from nacl.signing import SigningKey

from cards import datakeys, packs
from scanner import fingerprint
from tests.test_datakeys import Base, Resp


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Paths(unittest.TestCase):
    def test_hashed_name(self):
        s = "1a2b3c4d" + "0" * 56
        self.assertEqual(datakeys.hashed_name("cards.sqlite", s), "cards.1a2b3c4d.sqlite")
        self.assertEqual(datakeys.hashed_name("langs.tsv.gz", s), "langs.1a2b3c4d.tsv.gz")
        self.assertEqual(datakeys.hashed_name("fingerprints-add.npz", s), "fingerprints-add.1a2b3c4d.npz")

    def entry(self, **kw):
        s = sha(b"x")
        e = {"name": "cards.sqlite", "size": 1, "sha256": s, "path": datakeys.hashed_name("cards.sqlite", s)}
        e.update(kw)
        return e

    def check(self, e, names=("cards.sqlite",)):
        datakeys.check_files("pokemon", [e], names)

    def test_right_path_and_without_path(self):
        self.check(self.entry())
        e = self.entry()
        del e["path"]
        self.check(e)   # like before: the fixed name (release data)

    def test_wrong_paths_refused(self):
        s = self.entry()["sha256"]
        for bad in ("cards.sqlite", "cards.deadbeef.sqlite", "../cards.%s.sqlite" % s[:8], "x/" + self.entry()["path"],
                    "evil.%s.exe" % s[:8], 5, None if False else ""):
            with self.subTest(bad=bad), self.assertRaises(datakeys.DataRejected):
                self.check(self.entry(path=bad))
        with self.assertRaises(datakeys.DataRejected):   # no proper sha256 – no path
            self.check(self.entry(sha256="X" * 64, path=datakeys.hashed_name("cards.sqlite", "X" * 64)))

    def test_path_unlocks_no_other_file(self):
        s = sha(b"x")
        for name in ("BentCorner.exe", "manifest.json", "dinov2-small-q.onnx", "packs.json"):
            with self.subTest(name=name), self.assertRaises(datakeys.DataRejected):
                self.check({"name": name, "size": 1, "sha256": s, "path": datakeys.hashed_name(name, s)},
                           datakeys.DATA_FILES["pokemon"])

    def test_gz_path_must_follow(self):
        e = self.entry()
        e["gz"] = {"name": "cards.sqlite.gz", "size": 1, "sha256": sha(b"z"), "path": e["path"] + ".gz"}
        self.check(e)
        for gzp in (None, "cards.sqlite.gz", e["path"]):
            bad = json.loads(json.dumps(e))
            if gzp is None:
                del bad["gz"]["path"]
            else:
                bad["gz"]["path"] = gzp
            with self.subTest(gz=gzp), self.assertRaises(datakeys.DataRejected):
                self.check(bad)
        nopath = json.loads(json.dumps(e))
        del nopath["path"]   # a gz path without the file's path
        with self.assertRaises(datakeys.DataRejected):
            self.check(nopath)


class Prefixes(Base):
    def test_data2_with_v1_and_v1_with_v2_refused(self):
        self.release([self.entry()])
        raw, _ = self.data()
        v1 = base64.b64encode(self.dk.sign(datakeys.PREFIX + raw).signature).decode()
        with self.assertRaises(datakeys.DataRejected):   # what 0.9.7–0.9.9 sign-check would accept: not here
            datakeys.verify_data(raw, v1)
        raw2, v2 = self.data(seq=2)
        self.assertEqual(datakeys.verify_data(raw2, v2)["seq"], 2)
        with self.assertRaises(datakeys.DataRejected):   # data2 bytes played to an older app (v1 check)
            datakeys.verify_data(raw2, v2, prefix=datakeys.PREFIX)

    def test_the_app_reads_packs_data2(self):
        self.assertEqual(datakeys.DATA_NAME, "packs-data2.json")
        self.release([self.entry()])
        raw, sig = self.data()
        got = []

        def get(url, **kw):
            got.append(url)
            return mock.Mock(status_code=200, content=raw, text=sig) if url.endswith(".sig") else \
                mock.Mock(status_code=200, content=raw)
        with mock.patch("net.netpolite.get", side_effect=get):
            out = packs._data_listing()
        self.assertEqual([u.rsplit("/", 1)[1] for u in got], ["packs-data2.json", "packs-data2.json.sig"])
        self.assertIn("pokemon", out["packs"])


class FileLevelMerge(unittest.TestCase):
    rel = {"mtg": {"name": "Magic-Daten", "t": 1000, "files": [
        {"name": "fingerprints-all.npz", "size": 1, "sha256": "a"}, {"name": "langs.tsv.gz", "size": 1, "sha256": "b"},
        {"name": "setnames.json", "size": 1, "sha256": "c"}, {"name": "cardback.npy", "size": 1, "sha256": "d"}]}}

    def test_files_the_data_entry_leaves_out_stay_from_the_release(self):
        s = sha(b"add")
        data = {"t": 2000, "packs": {"mtg": {"files": [{"name": "fingerprints-add.npz", "size": 1, "sha256": s,
                                                        "path": datakeys.hashed_name("fingerprints-add.npz", s)}]}}}
        out = datakeys.merge(self.rel, data)["mtg"]
        self.assertEqual([f["name"] for f in out["files"]],
                         ["fingerprints-add.npz", "fingerprints-all.npz", "langs.tsv.gz", "setnames.json",
                          "cardback.npy"])
        self.assertEqual(out["src"], "data")
        self.assertEqual(out["rel_names"], ["fingerprints-all.npz", "langs.tsv.gz", "setnames.json", "cardback.npy"])
        names = packs.allowed_names("mtg", out)
        self.assertIn("cardback.npy", names)   # kept from packs.json – allowed through the release list only
        datakeys.check_files("mtg", out["files"], names)

    def test_rel_names_never_widen_beyond_the_release_list(self):
        names = packs.allowed_names("mtg", {"src": "data", "rel_names": ["BentCorner.exe", "cardback.npy"]})
        self.assertNotIn("BentCorner.exe", names)
        self.assertIn("cardback.npy", names)
        self.assertEqual(set(packs.allowed_names("mtg", {})), set(datakeys.release_names("mtg")))


class DownloadByPath(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        p = mock.patch.object(packs, "ROOT", self.tmp / "packs")
        p.start()
        self.addCleanup(p.stop)

    def test_server_name_from_path_local_name_fixed(self):
        body = b"{}"
        s = sha(body)
        f = {"name": "cm_fix.json", "size": len(body), "sha256": s, "path": datakeys.hashed_name("cm_fix.json", s)}
        urls = []

        def get(url, **kw):
            urls.append(url)
            return Resp(body)
        with mock.patch.object(packs, "manifest", return_value={"pokemon": {"files": [f], "src": "data"}}), \
                mock.patch("net.netpolite.get", side_effect=get):
            packs.download("pokemon")
        self.assertTrue(urls[0].endswith("/pokemon/" + f["path"]))
        self.assertTrue((packs.folder("pokemon") / "cm_fix.json").exists())
        self.assertFalse((packs.folder("pokemon") / f["path"]).exists())

    def test_old_app_without_path_knowledge_reads_the_fixed_name(self):
        """what 0.9.7–0.9.9 do with an entry: the fixed name – which is why the data key never writes those (path)"""
        body = b"{}"
        f = {"name": "cm_fix.json", "size": len(body), "sha256": sha(body)}
        urls = []
        with mock.patch.object(packs, "manifest", return_value={"pokemon": {"files": [f]}}), \
                mock.patch("net.netpolite.get", side_effect=lambda url, **kw: (urls.append(url), Resp(body))[1]):
            packs.download("pokemon")
        self.assertTrue(urls[0].endswith("/pokemon/cm_fix.json"))


def npz(path, ids, vecs, meta):
    np.savez(path, ids=np.array(ids), vecs=np.asarray(vecs, np.float16), meta=json.dumps(meta))


def unit(rng, n):
    v = rng.normal(size=(n, 384)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


class AddOn(unittest.TestCase):
    META = {"model": "dinov2-small-q.onnx", "batch": 1, "versions": "v1"}

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.rng = np.random.default_rng(3)
        self.base = self.tmp / "fingerprints-all.npz"
        self.bvecs = unit(self.rng, 5)
        npz(self.base, [f"b{i}_0" for i in range(5)], self.bvecs, self.META)
        self.base_sha = sha(self.base.read_bytes())
        for p in (mock.patch.object(fingerprint, "_mapped", lambda ids, mat, tag="": mat),
                  mock.patch.object(fingerprint.Index, "_drop_card_backs", lambda self: None)):
            p.start()
            self.addCleanup(p.stop)

    def add(self, ids, vecs, **meta):
        m = dict(self.META, base=self.base_sha, count=len(ids), game="mtg", created="x")
        m.update(meta)
        npz(self.tmp / "fingerprints-add.npz", ids, vecs, m)

    def test_add_on_appended_after_the_base(self):
        self.add(["n1_0", "n2_0"], unit(self.rng, 2))
        idx = fingerprint.Index({}, [], str(self.base))
        self.assertEqual(idx.ids, [f"b{i}_0" for i in range(5)] + ["n1_0", "n2_0"])
        self.assertEqual((idx.n_global, idx.n_add), (5, 2))

    def test_duplicate_id_add_on_wins(self):
        v = unit(self.rng, 1)
        self.add(["b2_0"], v)
        idx = fingerprint.Index({}, [], str(self.base))
        self.assertEqual(idx.ids.count("b2_0"), 1)
        self.assertEqual(idx.ids[-1], "b2_0")
        self.assertTrue(np.allclose(idx.vector("b2_0"), v[0].astype(np.float16).astype(np.float32), atol=1e-3))

    def test_wrong_base_or_versions_ignored(self):
        for bad in ({"base": "0" * 64}, {"versions": "other"}, {"batch": 64}, {"model": "x.onnx"}, {"count": 9}):
            with self.subTest(bad=bad):
                self.add(["n1_0"], unit(self.rng, 1), **bad)
                idx = fingerprint.Index({}, [], str(self.base))
                self.assertEqual(idx.ids, [f"b{i}_0" for i in range(5)])
                self.assertEqual(idx.n_add, 0)

    def test_cache_tag_changes_with_the_add_on(self):
        tags = []
        with mock.patch.object(fingerprint, "_mapped", lambda ids, mat, tag="": (tags.append(tag), mat)[1]):
            fingerprint.Index({}, [], str(self.base))
            self.add(["n1_0"], unit(self.rng, 1))
            fingerprint.Index({}, [], str(self.base))
            self.add(["n1_0", "n2_0"], unit(self.rng, 2))
            fingerprint.Index({}, [], str(self.base))
        self.assertEqual(len(set(tags)), 3)
        self.assertNotIn(":add:", tags[0])

    def test_probe(self):
        self.add(["n1_0"], unit(self.rng, 1))
        datakeys.probe("fingerprints-add.npz", self.tmp / "fingerprints-add.npz")
        self.add(["n1_0"], unit(self.rng, 1), base="nope")
        with self.assertRaises(datakeys.DataRejected):
            datakeys.probe("fingerprints-add.npz", self.tmp / "fingerprints-add.npz")
        np.savez(self.tmp / "fingerprints-add.npz", ids=np.array(["a_0"]), vecs=np.zeros((1, 384), np.float32),
                 meta=json.dumps(dict(self.META, base=self.base_sha, count=1)))
        with self.assertRaises(datakeys.DataRejected):   # float32: not the format
            datakeys.probe("fingerprints-add.npz", self.tmp / "fingerprints-add.npz")
        self.assertEqual(datakeys.limit_of("fingerprints-add.npz"), 32 << 20)

    def test_lists(self):
        for g in ("mtg", "yugioh"):
            self.assertIn("fingerprints-add.npz", datakeys.DATA_FILES[g])
            self.assertIn("fingerprints-add.npz", datakeys.release_names(g))
            self.assertNotIn("fingerprints-add.npz", packs.PACKS[g]["files"])   # never needed for "installed"
        self.assertNotIn("fingerprints-add.npz", datakeys.DATA_FILES["pokemon"])   # FP-ADD-FORMAT §1


class StaleAddOn(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        p = mock.patch.object(packs, "ROOT", self.tmp / "packs")
        p.start()
        self.addCleanup(p.stop)
        self.f = packs.folder("mtg")
        self.f.mkdir(parents=True)
        (self.f / "fingerprints-all.npz").write_bytes(b"base-1")

    def add(self, base):
        npz(self.f / "fingerprints-add.npz", ["n_0"], np.zeros((1, 384)), {"base": base, "count": 1})

    def test_kept_while_it_belongs_removed_after_a_new_base(self):
        self.add(sha(b"base-1"))
        self.assertFalse(packs.drop_stale_add("mtg"))
        self.assertTrue((self.f / "fingerprints-add.npz").exists())
        (self.f / "fingerprints-all.npz").write_bytes(b"base-2")
        self.assertTrue(packs.drop_stale_add("mtg"))
        self.assertFalse((self.f / "fingerprints-add.npz").exists())


if __name__ == "__main__":
    unittest.main()
