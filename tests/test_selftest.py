"""SCAN° self-test for the Win10 test stick (system/selftest.py, lead 06.11.2026): only the given data folder, no
network, no window/tray/lock, and without the switch the program starts exactly as before.

    python -m unittest tests/test_selftest.py
"""
import ast
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _py(code, *argv, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, "-c", code, *argv], cwd=str(ROOT), env=e, capture_output=True, text=True,
                          timeout=120)


class Network(unittest.TestCase):
    def test_every_connection_fails_and_is_counted(self):
        r = _py("import socket, urllib.request\n"
                "from system import selftest\n"
                "selftest._block_network()\n"
                "for f in (lambda: socket.create_connection(('example.org', 80), 2),\n"
                "          lambda: socket.getaddrinfo('bentcorner.app', 443),\n"
                "          lambda: socket.socket().connect(('127.0.0.1', 9)),\n"
                "          lambda: urllib.request.urlopen('https://bentcorner.app/dl/manifest.json', timeout=2)):\n"
                "    try:\n"
                "        f(); print('GOT THROUGH')\n"
                "    except OSError:\n"
                "        pass\n"
                "print('blocked', len(selftest._blocked))")
        self.assertNotIn("GOT THROUGH", r.stdout, r.stderr)
        self.assertIn("blocked 4", r.stdout, r.stderr)


class DataFolder(unittest.TestCase):
    CODE = ("import json, sys\nfrom system import datahome\n"
            "print(json.dumps({'home': str(datahome.HOME), 'first': datahome.FIRST_RUN}))")

    def test_only_the_given_folder_and_nothing_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            roaming = pathlib.Path(tmp) / "roaming"
            data = pathlib.Path(tmp) / "st"
            r = _py(self.CODE, f"--selftest-scan={tmp}\\r.json", f"--selftest-data={data}",
                    env={"BC_STARTER_ROAMING": str(roaming)})
            got = json.loads(r.stdout.strip().splitlines()[-1])
            self.assertEqual((got["home"], got["first"]), (str(data), False))
            self.assertFalse(roaming.exists(), "no datenordner.json may be written")

    def test_without_the_switch_unchanged(self):
        plain = json.loads(_py(self.CODE).stdout.strip().splitlines()[-1])
        other = json.loads(_py(self.CODE, "--some-other-switch").stdout.strip().splitlines()[-1])
        self.assertEqual(plain, other)
        self.assertNotEqual(plain["home"], "")

    def test_relative_or_missing_folder_refused(self):
        r = _py(self.CODE, "--selftest-scan=x.json", "--selftest-data=relative\\path")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--selftest-data", r.stderr)


class Entry(unittest.TestCase):
    def test_app_branches_off_only_with_the_switch(self):
        """app.py: the self-test is imported only inside its own `if` with the switch – nothing else changes."""
        tree = ast.parse((ROOT / "app.py").read_text("utf-8"))
        hits = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and any(a.name == "selftest" for a in n.names)]
        self.assertEqual(len(hits), 1)
        guard = next(n for n in tree.body if isinstance(n, ast.If) and hits[0] in ast.walk(n))
        self.assertIn("--selftest-scan=", ast.unparse(guard.test))

    def test_headless_run_without_data_reports_and_exits(self):
        """The real entry (app.py) with an empty data folder: report 'test data missing', exit 4 – no window, no tray,
        no lock, no network attempt."""
        with tempfile.TemporaryDirectory() as tmp:
            rep, data = pathlib.Path(tmp) / "r.json", pathlib.Path(tmp) / "empty"
            data.mkdir()
            r = subprocess.run([sys.executable, "app.py", f"--selftest-scan={rep}", f"--selftest-data={data}"],
                               cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 4, r.stderr[-2000:])
            got = json.loads(rep.read_text("utf-8"))
            self.assertTrue(got["done"])
            self.assertIn("test data missing", got["error"])
            self.assertEqual(got["ui_loaded"], [])
            self.assertEqual(got["network_attempts_blocked"], 0)


if __name__ == "__main__":
    unittest.main()
