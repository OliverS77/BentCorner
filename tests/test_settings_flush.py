"""Review 08.11. (M12): documents that live in the settings (friends, notes, alarms …) change only in memory when the
sync writes them – settings.json must be on disk BEFORE their shadow says „written“. Otherwise a crash in between makes
the next run read the old file against the new shadow: delete ops for those entries to every device.

    python -m unittest tests.test_settings_flush
"""
import tempfile
import unittest

from tests.test_syncrun import Device, FakeVault


class SettingsFlush(unittest.TestCase):
    def test_settings_saved_before_their_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = [1793600000000]
            vault = FakeVault()
            a = Device(tmp, "a", vault, lambda: t[0])
            b = Device(tmp, "b", vault, lambda: t[0])
            a.settings["friend_notes"] = {"p1": "from the club"}
            a.eng.switch_on()
            a.sync()
            t[0] += 1000
            seen = []

            def shadows():
                return "".join(f.read_text("utf-8") for f in (b.home / "sync").rglob("*friend_notes*"))

            def save():
                seen.append(("from the club" in shadows(), dict(b.settings.get("friend_notes") or {})))
            b.docs.save_settings = save
            b.eng.switch_on()
            b.sync()
            self.assertTrue(seen, "settings.json written during write_back")
            self.assertEqual(seen[0], (False, {"p1": "from the club"}), "saved with the new note, shadow not yet")
            self.assertIn("from the club", shadows(), "and the shadow after it")


if __name__ == "__main__":
    unittest.main()
