"""„Alles löschen, auch online“ without a connection (lead 07.11., the web alike; behind the sync switch): this PC's
data goes at once, only the seed and a mark stay; the next start online deletes on the server first; until then
nothing new (no mailbox). With the switch off: exactly as before (failed, try again). A protection code set: the page
asks for it.

    python -m unittest tests/test_forget_pending.py
"""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from collection import syncrun
from net import forget, relay
from system import i18n, wipe
from ui import qforget
from tests.test_forget_ui import sync

SEED = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


class Pending(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.plan = wipe.Plan(folder=str(self.root), delete=[str(self.root / "data")])
        for p in (mock.patch.object(forget, "pending_file", lambda: self.root / "forget-pending.json"),
                  mock.patch.object(forget, "has_id", lambda s: True),
                  mock.patch.object(forget, "available", lambda s: True),
                  mock.patch.object(wipe, "plan", lambda s: self.plan)):
            p.start()
            self.addCleanup(p.stop)
        lang = i18n.LANG
        self.addCleanup(i18n.set_language, lang)
        i18n.set_language("en")
        self.settings = {"relay": {"seed": SEED, "friends": {"F": {"status": "ok"}}}}

    def form(self, result, switch=True):
        p = mock.patch.object(forget, "delete_server", lambda s, **kw: result)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(syncrun, "available", lambda: switch)
        q.start()
        self.addCleanup(q.stop)
        f = qforget.Forget(self.settings, run=sync, changed=lambda: None, quit_after=lambda p: None)
        f.ask_version()
        f.local = True
        return f

    def test_offline_deletes_here_and_remembers_only_seed(self):
        f = self.form(forget.Result(forget.FAILED, "ConnectionError", "X", offline=True))
        f.start()
        self.assertEqual(f.state, "local_done")
        self.assertTrue(f.pending)
        mark = json.loads((self.root / "forget-pending.json").read_text("utf-8"))
        self.assertEqual(set(mark), {"at", "seed", "url", "code"})
        self.assertNotIn("friends", json.dumps(mark))

    def test_switch_off_as_before(self):
        f = self.form(forget.Result(forget.FAILED, "ConnectionError", "X", offline=True), switch=False)
        f.start()
        self.assertEqual(f.state, "failed")
        self.assertFalse((self.root / "forget-pending.json").exists())

    def test_a_refusal_is_no_offline(self):
        f = self.form(forget.Result(forget.FAILED, "500", "X"))
        f.start()
        self.assertEqual(f.state, "failed")

    def test_protection_code_is_asked(self):
        f = self.form(forget.Result(forget.MAIN_REQUIRED, "", "X"))
        f.start()
        self.assertEqual(f.state, "need_code")

    def test_while_waiting_nothing_new_then_the_start_finishes(self):
        forget.remember_pending(self.settings)
        with mock.patch.object(relay, "_post") as post:
            with self.assertRaises(relay.RelayError) as e:
                relay.register({"relay": {"seed": SEED}})
            post.assert_not_called()
        self.assertTrue(e.exception.data.get("forget_pending"))
        seen = []
        with mock.patch.object(forget, "forget", lambda s, g=None: seen.append((s, g)) or forget.Result(forget.DELETED)):
            r = forget.finish_pending()
        self.assertEqual(r.status, forget.DELETED)
        self.assertEqual(seen[0][0]["relay"]["seed"], SEED)
        self.assertIsNone(forget.pending())
        with mock.patch.object(forget, "forget", lambda s, g=None: forget.Result(forget.FAILED, "x", offline=True)):
            forget.remember_pending(self.settings)
            forget.finish_pending()
        self.assertIsNotNone(forget.pending(), "offline at the start: the mark stays for the next one")


if __name__ == "__main__":
    unittest.main()
