"""Settings → "Delete Bent°Corner" (ui/qforget.py; PLAN.md § 5.1, texts legal § 8): the order (the server first, its
result, then this PC), "Deleted." only when the server confirmed it, the failure path with [Try again] / [Continue
without deleting server data], the checkboxes (server preselected, local never). Never the real server, never the real
data folder: net.forget and system.wipe are faked, the "after exit" step is only recorded.

    python -m unittest tests/test_forget_ui.py
"""
import unittest
from unittest import mock

from net import forget
from system import i18n, wipe
from ui import qforget


def sync(fn, done, on_error=None):
    try:
        value = fn()
    except Exception:  # noqa: BLE001
        value = on_error
    done(value)


class Flow(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.quit = []
        self.plan = wipe.Plan(folder="C:/Test/BentCorner", delete=["C:/Test/BentCorner/data"])
        p = [mock.patch.object(forget, "has_id", lambda s: True),
             mock.patch.object(forget, "available", lambda s: self.calls.append("available") or True),
             mock.patch.object(wipe, "plan", lambda s: self.calls.append("plan") or self.plan)]
        for x in p:
            x.start()
            self.addCleanup(x.stop)
        lang = i18n.LANG
        self.addCleanup(i18n.set_language, lang)
        i18n.set_language("en")

    def make(self, results):
        it = iter(results)

        def delete_server(settings, full=None):
            self.calls.append(f"server(full={full})")
            r = next(it)
            if isinstance(r, Exception):
                raise r
            return r
        x = mock.patch.object(forget, "delete_server", delete_server)
        x.start()
        self.addCleanup(x.stop)
        f = qforget.Forget({}, run=sync, changed=lambda: None, quit_after=lambda p: self.quit.append(p))
        f.ask_version()
        return f

    def test_checkboxes_server_preselected_local_never(self):
        f = self.make([])
        self.assertTrue(f.server)
        self.assertFalse(f.local)
        self.assertTrue(f.full)          # B: the server said "forget": true

    def test_server_only_deleted(self):
        f = self.make([forget.Result(forget.DELETED, code="ABCD-1234")])
        f.start()
        self.assertEqual(f.server_line(), "Deleted.")
        self.assertEqual(self.calls, ["available", "server(full=True)"])
        self.assertEqual(self.quit, [], "nothing on this PC – the program keeps running")

    def test_already_deleted(self):
        f = self.make([forget.Result(forget.ALREADY)])
        f.start()
        self.assertEqual(f.server_line(), "Was already deleted.")

    def test_server_then_this_pc(self):
        f = self.make([forget.Result(forget.DELETED)])
        f.local = True
        f.start()
        self.assertEqual(self.calls, ["available", "server(full=True)", "plan"], "the server first, then this PC")
        self.assertEqual(f.state, "local_done")
        self.assertEqual(self.quit, [], "the program ends only with [Quit now]")
        f.finish()
        self.assertEqual(self.quit, [self.plan])
        f.finish()
        self.assertEqual(self.quit, [self.plan], "once")

    def test_failed_never_says_deleted_and_never_goes_on_by_itself(self):
        f = self.make([forget.Result(forget.FAILED, code="ABCD-1234")])
        f.local = True
        f.start()
        self.assertEqual(f.state, "failed")
        self.assertEqual(f.server_line(), "")
        self.assertEqual(self.quit, [], "this PC waits for the choice")
        self.assertEqual(f.my_id(), "ABCD-1234")

    def test_try_again(self):
        f = self.make([forget.Result(forget.FAILED), forget.Result(forget.DELETED)])
        f.start()
        f.retry()
        self.assertEqual(f.server_line(), "Deleted.")

    def test_continue_without_server_deletes_this_pc_without_saying_deleted(self):
        f = self.make([forget.Result(forget.FAILED)])
        f.local = True
        f.start()
        f.skip()
        self.assertEqual(f.state, "local_done")
        self.assertEqual(f.server_line(), "", "the server part was NOT deleted – never 'Deleted.'")
        f.finish()
        self.assertEqual(self.quit, [self.plan])

    def test_continue_without_server_and_without_local_ends_quietly(self):
        f = self.make([forget.Result(forget.FAILED)])
        f.start()
        f.skip()
        self.assertEqual(f.state, "idle")
        self.assertEqual(self.quit, [])

    def test_an_error_on_the_way_is_a_failure(self):
        f = self.make([OSError("offline")])
        f.start()
        self.assertEqual(f.state, "failed")

    def test_only_local_without_an_id(self):
        with mock.patch.object(forget, "has_id", lambda s: False):
            f = self.make([])
            self.assertFalse(f.can_start(), "nothing chosen yet")
            f.local = True
            f.start()
        self.assertNotIn("server(full=True)", self.calls)
        f.finish()
        self.assertEqual(self.quit, [self.plan])

    def test_version_a_when_offline(self):
        with mock.patch.object(forget, "available", lambda s: (_ for _ in ()).throw(OSError("offline"))):
            f = self.make([])
        self.assertFalse(f.full, "offline = A")


class Texts(unittest.TestCase):
    """The German texts as legal gave them (PLAN.md § 8)."""

    def test_german_word_for_word(self):
        lang = i18n.LANG
        self.addCleanup(i18n.set_language, lang)
        i18n.set_language("de")
        tr = i18n.tr
        self.assertEqual(tr(qforget.BUTTON), "Bent°Corner löschen")
        self.assertEqual(tr(qforget.B_CHECK), "Meine Daten auf dem Bent°Corner-Server löschen – deine ID (die Adresse, "
                                              "unter der dich Freunde finden) mit Schlüssel, geteilte Listen und Binder, "
                                              "Päckchen und Blockaden. Sofort.")   # legal 07.11.: ID explained
        self.assertEqual(tr(qforget.NO_ID), "Auf dem Bent°Corner-Server liegt nichts von dir.")
        self.assertEqual(tr(qforget.FAILED).format(mail="hello@bentcorner.app"),
                         "Deine Daten auf dem Server sind NICHT gelöscht. Ohne Nutzung löscht der Server sie automatisch: "
                         "geteilte Listen und Binder 6 Monate nach dem letzten Teilen, deine ID und dein Schlüssel nach "
                         "365 Tagen, Päckchen nach dem Abholen, spätestens nach 14 Tagen. Sofort geht es per Mail an "
                         "hello@bentcorner.app.")
        self.assertEqual(tr(qforget.SKIP), "Ohne Serverlöschung fortfahren")
        self.assertEqual(tr(qforget.DONE), "Gelöscht.")
        # every text has its German line
        for name in ("EXPORT", "EXPORT_GO", "A_CHECK", "A_SMALL", "B_CHECK", "B_SMALL", "BOTH", "NO_ID", "LOCAL_CHECK",
                     "BACKUP_KEPT", "BACKUP_GOES", "BACKUP_ELSEWHERE", "BACKUP_NONE", "BACKUP_MAKE", "BUTTON", "DONE",
                     "ALREADY", "FAILED", "FAILED_ID", "COPY", "RETRY", "SKIP", "SKIP_LOCAL", "PORTABLE", "QUIT"):
            en = getattr(qforget, name)
            self.assertNotEqual(tr(en), en, name)

    def test_the_mail_comes_from_contacts(self):
        from system import contacts
        self.assertEqual(contacts.MAIL, "hello@bentcorner.app")


if __name__ == "__main__":
    unittest.main()
