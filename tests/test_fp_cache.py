"""The memory-mapped fingerprint cache (fingerprint._mapped): a rebuilt index with the same cards but other vectors
(0.9.7: batch-1 index) gets a new file – the old matrix is never reused – and the old file is cleared away."""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import numpy as np

from scanner import fingerprint


class FpCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(fingerprint, "DATA", pathlib.Path(self.tmp.name))
        p.start()
        self.addCleanup(p.stop)
        g = mock.patch("games.current", return_value=mock.Mock(key="mtg"))
        g.start()
        self.addCleanup(g.stop)
        self.ids = [f"card-{i}_0" for i in range(3000)]
        self.folder = pathlib.Path(self.tmp.name) / "cache" / "fp"

    def mat(self, seed):
        v = np.random.default_rng(seed).standard_normal((3000, 384)).astype(np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    def test_same_index_same_file(self):
        a = self.mat(1)
        m1 = fingerprint._mapped(self.ids, a)
        m2 = fingerprint._mapped(self.ids, a.copy())
        self.assertEqual(m1.filename, m2.filename)
        self.assertTrue(np.array_equal(np.asarray(m2), a))

    def test_rebuilt_vectors_new_file_old_cleared(self):
        old, new = self.mat(1), self.mat(2)
        m_old = fingerprint._mapped(self.ids, old)
        old_file = pathlib.Path(m_old.filename)
        del m_old   # the app holds one mapping per game – released before the new index loads
        m_new = fingerprint._mapped(self.ids, new)
        self.assertNotEqual(pathlib.Path(m_new.filename), old_file)
        self.assertTrue(np.array_equal(np.asarray(m_new), new))   # the NEW vectors, not the cached old ones
        self.assertEqual([p.name for p in self.folder.glob("mtg-*.npy")], [pathlib.Path(m_new.filename).name])

    def npz(self, name, mat, meta=None):
        p = pathlib.Path(self.tmp.name) / name
        extra = {"meta": json.dumps(meta)} if meta is not None else {}
        np.savez_compressed(p, ids=np.array(self.ids), vecs=mat.astype(np.float16), **extra)
        return p

    def test_one_row_changed_new_file(self):
        """A server that recomputes a single card: the sample of 512 rows may miss it – the file's tag doesn't."""
        a = self.mat(1)
        b = a.copy()
        b[1] = self.mat(9)[1]   # row 1: not in the sample (every 5th row of 3000)
        f1, f2 = self.npz("a.npz", a), self.npz("b.npz", b)
        m1 = fingerprint._mapped(self.ids, a, fingerprint._index_tag(f1))
        name1 = pathlib.Path(m1.filename).name
        del m1
        m2 = fingerprint._mapped(self.ids, b, fingerprint._index_tag(f2))
        self.assertNotEqual(pathlib.Path(m2.filename).name, name1)
        self.assertTrue(np.array_equal(np.asarray(m2)[1], b[1]))

    def test_tag_names_the_index_type(self):
        meta = {"model": "dinov2-small-q.onnx", "batch": 1, "versions": "model dinov2-small-q.onnx, batch 1"}
        tag = fingerprint._index_tag(self.npz("new.npz", self.mat(1), meta))
        self.assertIn(":dinov2-small-q.onnx:1:", tag)
        old = fingerprint._index_tag(self.npz("old.npz", self.mat(1), {"model": "dinov2-small-q.onnx"}))
        self.assertTrue(old.endswith(":dinov2-small-q.onnx"))   # old index without batch/versions: size + sha256 + model
        self.assertEqual(fingerprint._index_tag(pathlib.Path(self.tmp.name) / "missing.npz"), "")

    def test_small_index_stays_in_memory(self):
        a = self.mat(3)[:100]
        self.assertIs(fingerprint._mapped(self.ids[:100], a), a)


if __name__ == "__main__":
    unittest.main()
