"""A data pack the server doesn't have yet (a new game until the release that ships it) is a quiet note, asked once per
session – no error with "Try again". No internet stays an error."""
import types
import unittest
from unittest import mock

from cards import packs


class Download(unittest.TestCase):
    def test_not_on_the_server_is_pack_missing(self):
        with mock.patch.object(packs, "manifest", return_value={"yugioh": {"files": []}}):
            with self.assertRaises(packs.PackMissing):
                packs.download("newgame")

    def test_no_internet_stays_an_error(self):
        with mock.patch.object(packs, "manifest", side_effect=packs.PackError("Server not reachable: offline")):
            with self.assertRaises(packs.PackError) as ctx:
                packs.download("newgame")
        self.assertNotIsInstance(ctx.exception, packs.PackMissing)


class Job(unittest.TestCase):
    def run_job(self, side_effect):
        from system.jobqueue import JobQueue
        done = []
        win = types.SimpleNamespace(cancel_requested=False, packs_missing=set(),
                                    _job_done=lambda *a: done.append(a))
        job = {"kind": "pack", "code": "newgame", "name": "Neues-Spiel-Daten"}
        with mock.patch.object(packs, "download", side_effect=side_effect):
            JobQueue._work(win, job)
        return win, job, done

    def test_missing_pack_is_a_note(self):
        win, job, done = self.run_job(packs.PackMissing("Pack “newgame” doesn't exist on the server"))
        (_job, msg, error), = done
        self.assertEqual(error, "")
        self.assertIn("next update", msg)
        self.assertTrue(job.get("missing"))
        self.assertEqual(win.packs_missing, {"newgame"})

    def test_no_internet_is_an_error(self):
        win, job, done = self.run_job(packs.PackError("Server not reachable: offline"))
        (_job, msg, error), = done
        self.assertIn("Server not reachable", error)
        self.assertFalse(job.get("missing"))
        self.assertEqual(win.packs_missing, set())


class Check(unittest.TestCase):
    def test_missing_pack_not_asked_again(self):
        import app
        jobs = []
        win = types.SimpleNamespace(settings={}, packs_missing={"newgame"}, _packs_checked=True,
                                    enqueue=lambda kind, code=None, **k: jobs.append((kind, code)),
                                    _own_db_missing=lambda key: False)
        with mock.patch.object(packs, "needed", return_value=["newgame", "yugioh"]):
            app.MainWindow.packs_check(win)
        self.assertEqual(jobs, [("pack", "yugioh")])


if __name__ == "__main__":
    unittest.main()
