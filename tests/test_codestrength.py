"""Strength of a chosen protection code (collection/codestrength.py, Oliver/lead/legal 07.11.): the shared vectors
(docs/web/codestrength-vectors.json – the web decides alike), the word list is the one the vectors were made with,
the guard refuses a weak chosen code always.

    python -m unittest tests/test_codestrength.py
"""
import hashlib
import json
import pathlib
import unittest
from unittest import mock

from collection import codestrength as cs

_VEC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "web" / "codestrength-vectors.json"
if not _VEC.exists():   # private file (tools/public/manifest.txt: no example codes in the public source)
    raise unittest.SkipTest("codestrength vectors are not part of this source")
VEC = json.loads(_VEC.read_text("utf-8"))


class Vectors(unittest.TestCase):
    def test_words_file_is_the_one_of_the_vectors(self):
        self.assertEqual(hashlib.sha256(cs._words_file().read_bytes()).hexdigest(), VEC["words_file_sha256"])

    def test_every_case(self):
        for c in VEC["cases"]:
            r = cs.strength(c["input"])
            self.assertEqual((r["mbits"], r["bits"], r["score"], r["ok"]),
                             (c["mbits"], c["bits"], c["score"], c["ok"]), repr(c["input"]))

    def test_mb(self):
        for x, v in VEC["mb"].items():
            self.assertEqual(cs.mb(int(x)), v)

    def test_file_is_current(self):
        from tools import make_codestrength_vectors as mv
        self.assertEqual(json.loads(json.dumps(mv.build(), ensure_ascii=False)), VEC)


class Rules(unittest.TestCase):
    def test_minimum(self):
        self.assertEqual(cs.MIN_BITS, 60)
        self.assertGreaterEqual(sum(c["ok"] for c in VEC["cases"]), 5)
        self.assertGreaterEqual(sum(not c["ok"] for c in VEC["cases"]), 50)

    def test_guard_refuses_a_weak_chosen_code_always(self):
        from net import sync_ctl
        weak = next(c["input"] for c in VEC["cases"] if c["input"].strip() and not c["ok"])
        ctl = type("C", (), {})()
        ctl.sync_status, ctl._sync_changed, ctl._sync_bg = {}, mock.Mock(), mock.Mock()
        ctl.guard_strength = lambda t: sync_ctl.SyncControl.guard_strength(ctl, t)
        from collection import syncrun
        with mock.patch.object(syncrun, "available", lambda: True):   # the switch on (off: nothing at all)
            sync_ctl.SyncControl.guard_set(ctl, weak, own=True)
        self.assertEqual(ctl.sync_status["guard"], "weak")
        ctl._sync_bg.assert_not_called()


class Quiet(unittest.TestCase):
    def test_a_removed_identity_sends_nothing_by_itself(self):
        from net import relay
        s = {"relay": {"seed": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=", "identity_gone": 1.0}}
        with mock.patch.object(relay, "_post") as post:
            with self.assertRaises(relay.RelayError) as e:
                relay.register(s)
            post.assert_not_called()
        self.assertEqual(e.exception.status, 410)


if __name__ == "__main__":
    unittest.main()
