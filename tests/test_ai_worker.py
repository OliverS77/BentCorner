"""AI worker process (scanner/aiworker.py): a crashed worker is restarted, errors inside a job don't kill it, a worker
that keeps dying is given up (computing in the app instead) – and fingerprint/OCR never run on the GPU at the same
time (fingerprint._run_lock).

The real worker loads the AI model; here a tiny stand-in process speaks the same protocol over the same named pipe
(key-protected), so the client logic (start, restart, fallback) is tested for real without a GPU.

    python -m unittest tests/test_ai_worker.py
"""
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import numpy as np

from scanner import aiworker
from scanner import fingerprint
from scanner import ocrscan

FAKE = '''
import os
from multiprocessing.connection import Client
conn = Client(os.environ["BENTCORNER_AI_PIPE"], family="AF_PIPE", authkey=bytes.fromhex(os.environ["BENTCORNER_AI_KEY"]))
while True:
    try:
        op, args = conn.recv()
    except (EOFError, OSError):
        break
    if op == "quit":
        break
    if op == "die":
        os._exit(3)
    if op == "pid":
        conn.send((True, os.getpid(), {"backend": "fake"}))
    elif op == "fail":
        conn.send((False, "ValueError: boom", {}))
    else:
        conn.send((True, args[0] if args else None, {"backend": "fake"}))
'''


@unittest.skipUnless(sys.platform == "win32", "named pipes (AF_PIPE) only on Windows")
class Worker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        script = pathlib.Path(self.tmp.name) / "fake_worker.py"
        script.write_text(FAKE, "utf-8")
        self.patches = [mock.patch.object(aiworker, "_command", lambda: [sys.executable, str(script)]),
                        mock.patch.object(aiworker, "ENABLED", True),
                        mock.patch.object(aiworker, "START_TIMEOUT", 20.0),
                        mock.patch.object(fingerprint, "CHOICE_FILE", pathlib.Path(self.tmp.name) / "ai-device.json"),
                        mock.patch.object(ocrscan, "_gpu_known", [])]
        for p in self.patches:
            p.start()
        aiworker._fails = 0

    def tearDown(self):
        aiworker.stop()
        aiworker._close()
        aiworker._fails = 0
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_job_and_restart_after_kill(self):
        self.assertEqual(aiworker.call("echo", 42), 42)
        pid = aiworker.call("pid")
        aiworker._proc.kill()          # the graphics driver crashed, say
        aiworker._proc.wait(5)
        self.assertEqual(aiworker.call("echo", 7), 7)   # restarted on its own
        self.assertNotEqual(aiworker.call("pid"), pid)
        self.assertEqual(aiworker._fails, 0)   # a successful job resets the count

    def test_error_inside_a_job_keeps_the_process(self):
        pid = aiworker.call("pid")
        with self.assertRaises(RuntimeError):
            aiworker.call("fail")
        self.assertEqual(aiworker.call("pid"), pid)

    def test_worker_that_keeps_dying_is_given_up(self):
        for _ in range(aiworker.MAX_FAILS):
            if not aiworker.usable():
                break
            with self.assertRaises(aiworker.Unavailable):
                aiworker.call("die")
        self.assertFalse(aiworker.usable())   # from now on everything is computed in the app
        with self.assertRaises(aiworker.Unavailable):
            aiworker.call("echo", 1)

    def test_death_on_the_gpu_switches_to_the_cpu(self):
        fingerprint._save_choice(0)   # the AI runs on GPU device 0
        with self.assertRaises(aiworker.Unavailable):
            aiworker.call("die")       # dies twice (with the restart) – e.g. a too old or broken DirectML
        self.assertIsNone(fingerprint._load_choice())   # CPU from now on: in the process and in the app
        self.assertIn("'die'", json.loads(fingerprint.CHOICE_FILE.read_text("utf-8"))["crash"])

    def test_stop_ends_the_process(self):
        aiworker.call("echo", 1)
        proc = aiworker._proc
        self.assertTrue(aiworker.stop())
        self.assertIsNotNone(proc.poll())
        self.assertFalse(aiworker.running())

    def test_stop_in_the_background_returns_at_once(self):
        aiworker.call("echo", 1)
        proc = aiworker._proc
        with mock.patch.object(aiworker, "_end", wraps=aiworker._end) as end:
            self.assertTrue(aiworker.stop(background=True))
            self.assertFalse(aiworker.running())        # detached right away
            proc.wait(10)                                # ... and gone soon after
            for th in [t for t in threading.enumerate() if t.name == "ai-stop"]:
                th.join(10)
            end.assert_called_once()
        self.assertEqual(aiworker.call("echo", 2), 2)    # a new start doesn't wait for the old one


class Fallback(unittest.TestCase):
    def test_embed_computes_in_the_app_when_the_worker_is_unavailable(self):
        with mock.patch.object(aiworker, "usable", lambda: True), \
                mock.patch.object(aiworker, "call", side_effect=aiworker.Unavailable), \
                mock.patch.object(fingerprint, "embed_small", return_value="local") as local:
            self.assertEqual(fingerprint.embed([np.zeros((60, 40, 3), np.uint8)]), "local")
            local.assert_called_once()

    def test_ocr_computes_in_the_app_when_the_worker_is_unavailable(self):
        with mock.patch.object(aiworker, "usable", lambda: True), \
                mock.patch.object(ocrscan, "_gpu_ok", lambda: True), \
                mock.patch.object(aiworker, "call", side_effect=aiworker.Unavailable), \
                mock.patch.object(ocrscan, "run_local", return_value="local") as local:
            self.assertEqual(ocrscan.run(np.zeros((32, 96, 3), np.uint8)), "local")
            local.assert_called_once()


class RunLock(unittest.TestCase):
    """Fingerprint and OCR (on the GPU) never at the same time – DirectML can't take concurrent runs."""

    def test_fingerprint_and_gpu_ocr_never_overlap(self):
        active, peak, lock = [0], [0], threading.Lock()

        def busy(*_a, **_k):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.02)
            with lock:
                active[0] -= 1
            return []

        engine = mock.Mock(side_effect=busy)
        with mock.patch.object(fingerprint, "_embed", busy), \
                mock.patch.object(ocrscan, "engine", lambda: engine), \
                mock.patch.object(ocrscan, "_gpu", [True]):
            jobs = [threading.Thread(target=fingerprint.embed_small, args=([], 1)) for _ in range(6)] + \
                   [threading.Thread(target=ocrscan.run_local, args=(ocrscan.blank(),)) for _ in range(6)]
            for t in jobs:
                t.start()
            for t in jobs:
                t.join(10)
        self.assertEqual(peak[0], 1)
        self.assertEqual(engine.call_count, 6)

    def test_cpu_ocr_doesnt_wait_for_the_gpu(self):
        engine = mock.Mock(return_value="read")
        with mock.patch.object(ocrscan, "engine", lambda: engine), mock.patch.object(ocrscan, "_gpu", [False]):
            got = []
            with fingerprint._run_lock:   # the AI is busy …
                t = threading.Thread(target=lambda: got.append(ocrscan.run_local(ocrscan.blank())))
                t.start()
                t.join(2)
            self.assertEqual(got, ["read"])   # … CPU OCR ran anyway


if __name__ == "__main__":
    unittest.main()
