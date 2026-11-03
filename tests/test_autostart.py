"""Autostart (ui/tray.py) with SEVERAL installations on one PC: switching off only removes the entry of THIS program –
the setup of a portable copy used to delete the autostart of the real installation (0.9.7.8). Switching on is an
explicit choice and takes the entry over. Only a fake registry here – the real Run key is never touched.

    python -m unittest tests/test_autostart.py
"""
import sys
import types
import unittest
from unittest import mock

from ui import tray

HERE = r"C:\Users\x\Desktop\BentCorner\BentCorner.exe"
OTHER = r"E:\Stick\BentCorner-Test\BentCorner.exe"


def fake_winreg(store):
    """Just enough of winreg for tray.py: one key, values in `store` (name -> data)."""
    w = types.SimpleNamespace(HKEY_CURRENT_USER=1, KEY_SET_VALUE=2, REG_SZ=1)

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def query(k, name):
        if name not in store:
            raise FileNotFoundError(name)
        return store[name], w.REG_SZ

    def delete(k, name):
        if name not in store:
            raise FileNotFoundError(name)
        del store[name]

    w.OpenKey = lambda *a, **k: Key()
    w.QueryValueEx = query
    w.SetValueEx = lambda k, name, _r, _t, value: store.__setitem__(name, value)
    w.DeleteValue = delete
    return w


class Autostart(unittest.TestCase):
    def setUp(self):
        self.store = {}
        for p in (mock.patch.dict(sys.modules, {"winreg": fake_winreg(self.store)}),
                  mock.patch.object(tray, "autostart_possible", lambda: True),
                  mock.patch.object(tray.sys, "platform", "win32"),
                  mock.patch.object(tray.datahome, "program", lambda: HERE)):
            p.start()
            self.addCleanup(p.stop)

    def test_off_leaves_the_entry_of_another_installation(self):
        self.store[tray.RUN_NAME] = f'"{OTHER}" --tray'
        with self.assertLogs("booster", "INFO"):
            self.assertTrue(tray.set_autostart(False))
        self.assertEqual(self.store[tray.RUN_NAME], f'"{OTHER}" --tray')
        self.assertFalse(tray.autostart_enabled())   # not ours – the switch here shows "off"

    def test_off_removes_our_own_entry(self):
        tray.set_autostart(True)
        self.assertTrue(tray.autostart_enabled())
        tray.set_autostart(False)
        self.assertNotIn(tray.RUN_NAME, self.store)

    def test_off_without_any_entry(self):
        self.assertTrue(tray.set_autostart(False))
        self.assertEqual(self.store, {})

    def test_on_takes_over_with_a_note_in_the_log(self):
        self.store[tray.RUN_NAME] = f'"{OTHER}" --tray'
        with self.assertLogs("booster", "INFO") as logs:
            tray.set_autostart(True)
        self.assertEqual(self.store[tray.RUN_NAME], f'"{HERE}" --tray')
        self.assertIn("another installation", "\n".join(logs.output))

    def test_same_path_in_other_spelling_counts_as_ours(self):
        self.store[tray.RUN_NAME] = '"' + HERE.lower().replace("\\desktop\\", "\\Desktop\\.\\") + '" --tray'
        self.assertTrue(tray.autostart_enabled())
        tray.set_autostart(False)
        self.assertNotIn(tray.RUN_NAME, self.store)

    def test_entry_without_quotes(self):
        self.assertTrue(tray._is_ours(f"{HERE} --tray"))   # HERE has no spaces
        self.assertFalse(tray._is_ours(f"{OTHER} --tray"))
        self.assertFalse(tray._is_ours(""))
        self.assertFalse(tray._is_ours(None))


if __name__ == "__main__":
    unittest.main()
