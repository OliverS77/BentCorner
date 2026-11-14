"""Review 0.9.7, the low findings on the PC (VERIFY.md / FUNDE.md, lead 10.11.). Only temp folders, nothing real.

    python -m unittest tests/test_review_lowfix.py
"""
import copy
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui import textsafe  # noqa: E402

EVIL = "<b>x</b> &amp; <img src='https://evil.example/p.png'> y‮"


class ShownNamesTest(unittest.TestCase):
    """1 – foreign names only ever as text; what is stored stays byte-identical (lead 10.11.)."""

    def test_name_is_plain_text(self):
        n = textsafe.name(EVIL)
        self.assertNotIn("<", n)
        self.assertNotIn(">", n)
        self.assertNotIn("‮", n)
        self.assertFalse(textsafe.looks_rich(n))
        self.assertIn("‹b›x‹/b›", n)
        self.assertEqual(textsafe.name("x" * 100, 10), "x" * 9 + "…")
        self.assertEqual(textsafe.name(None), "")

    def test_a_label_with_a_name_stays_text(self):
        from ui.qform import UI
        lab = UI(None).label("Trade with " + textsafe.name(EVIL))
        self.assertFalse(lab["rich"])
        self.assertFalse(UI(None).label("x <3 y")["rich"])          # no own tag: text
        self.assertFalse(UI(None).label("<script>alert(1)</script>")["rich"])

    def test_rich_labels_keep_only_our_tags(self):
        from ui.qform import UI
        h = UI(None).label("<b>ok</b><img src='https://evil/p.png'><img src='data:image/png;base64,AA'>"
                       "<script>x</script><span onclick='y'>s</span>")["html"]
        self.assertIn("<b>ok</b>", h)
        self.assertNotIn("evil", h)                        # a remote image never loads
        self.assertIn("data:image/png", h)                 # our own (mana symbols) stay
        self.assertIn("&lt;script&gt;", h)                 # shown as text
        self.assertNotIn("onclick", h)

    def test_stored_data_stays_as_it_came(self):
        from collection import tradelib
        from ui import joinui, qsync
        friend = {"name": EVIL, "pid": "p1", "status": "ok"}
        dev = {"name": EVIL, "n": 2, "dev": "d1"}
        ticket = {"partner": EVIL, "t": 0, "give": [], "get": [], "money": 0}
        before = copy.deepcopy((friend, dev, ticket))
        self.assertNotIn("<", qsync.device_name(dev))
        self.assertNotIn("<", joinui.ticket_line(ticket))
        self.assertEqual((friend, dev, ticket), before)   # display only: sync and matching see the same bytes
        self.assertTrue(callable(tradelib.money_text))


class TicketArchiveTest(unittest.TestCase):
    """2 – the local ticket archive (collectibles/index.html): foreign names only via textContent (T7/B7)."""
    HTML = __import__("pathlib").Path(__file__).resolve().parent.parent / "assets" / "collectibles" / "index.html"

    def test_inner_html_only_with_fixed_text(self):
        import re
        found = re.findall(r"\.innerHTML\s*=\s*(.+?);", self.HTML.read_text("utf-8"), re.S)   # also over lines
        self.assertTrue(found)
        for rhs in found:   # only string literals: nothing from a ticket goes through the HTML parser
            self.assertRegex(rhs.strip(), r"""^(""|'[^']*'|"[^"]*")$""", rhs)

    def test_the_page_script_is_valid(self):
        import shutil, subprocess, tempfile, pathlib
        node = shutil.which("node")
        if not node:
            self.skipTest("no node")
        src = self.HTML.read_text("utf-8")
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "page.js"
            f.write_text(src[src.rindex("<script>") + 8:src.rindex("</script>")], "utf-8")
            out = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])


def _junction(link, target):
    """An NTFS junction (no admin needed) – what a prepared backup stick could contain."""
    import subprocess
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
    return r.returncode == 0


@unittest.skipUnless(os.name == "nt", "junctions are Windows")
class RestoreLinksTest(__import__("tests.test_autobackup", fromlist=["_Home"])._Home):
    """3 – a folder backup never follows a link or junction (F6)."""

    def setUp(self):
        super().setUp()
        self.secret = self.root / "victim-documents"
        self.secret.mkdir()
        (self.secret / "secret.json").write_text('{"private": 1}', "utf-8")
        self.bk = self.root / "backup"
        (self.bk / "my-data").mkdir(parents=True)
        (self.bk / "my-data" / "collection.json").write_text('{"items": [{"uid": "a", "count": 1}]}', "utf-8")
        self.write("data/my-data/collection.json", '{"items": []}')

    def test_a_junction_inside_is_left_out(self):
        from system import datastore
        if not _junction(self.bk / "my-data" / "sessions", self.secret):
            self.skipTest("mklink /J not possible here")
        self.assertTrue(datastore.restore_backup(self.bk))
        got = self.data / "my-data"
        self.assertTrue((got / "collection.json").exists())
        self.assertFalse((got / "sessions").exists())                      # not followed, not copied
        self.assertEqual([p.name for p in self.secret.iterdir()], ["secret.json"])   # the target untouched

    def test_a_linked_my_data_restores_nothing(self):
        from system import datastore
        import shutil
        shutil.rmtree(self.bk / "my-data")
        (self.root / "elsewhere").mkdir()
        (self.root / "elsewhere" / "collection.json").write_text('{"items": [{"uid": "x"}]}', "utf-8")
        if not _junction(self.bk / "my-data", self.root / "elsewhere"):
            self.skipTest("mklink /J not possible here")
        with self.assertRaises(ValueError):   # "couldn't be restored – your previous state is back"
            datastore.restore_backup(self.bk)
        self.assertEqual((self.data / "my-data" / "collection.json").read_text("utf-8"), '{"items": []}')


class CsvFormulaTest(unittest.TestCase):
    """4 – spreadsheet exports: a text cell never becomes a formula (H2-7); import files for other apps stay exact."""

    def groups(self):
        base = {"count": 2, "set": "abc", "number": "1", "lang": "en", "foil": False, "rarity": "rare", "sid": "s1",
                "condition": "NM", "last": 0}
        return [dict(base, name="+2 Mace"), dict(base, name="=HYPERLINK(\"http://x\")", sid="s2"),
                dict(base, name="@SUM(1)", sid="s3"), dict(base, name="Plain", sid="s4")]

    def read(self, path, delim):
        import csv
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f, delimiter=delim))

    def test_excel_export(self):
        import tempfile, pathlib
        from collection import collection
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "x.csv"
            collection.export_csv(self.groups(), f, "excel")
            rows = self.read(f, ";")
        names = [r[1] for r in rows[1:]]
        self.assertEqual(names, ["'+2 Mace", "'=HYPERLINK(\"http://x\")", "'@SUM(1)", "Plain"])
        self.assertEqual(rows[1][0], "2")                     # a number stays a number

    def test_import_files_stay_exact(self):
        import tempfile, pathlib
        from collection import collection
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "m.csv"
            collection.export_csv(self.groups(), f, "moxfield")
            self.assertEqual(self.read(f, ",")[1][2], "+2 Mace")    # Moxfield matches by name

    def test_cell(self):
        from collection import csvsafe
        self.assertEqual([csvsafe.cell(v) for v in ("-1", "	x", "a=b", 3, -3, None)], ["'-1", "'	x", "a=b", 3, -3, None])


class BrokenFileTest(unittest.TestCase):
    """5/6 – a damaged import file says so (H2-5); a language from a file is a known one or "en" (H2-6)."""

    def bentcorner(self, d):
        import json, tempfile, pathlib, zlib
        from collection import trade
        f = pathlib.Path(tempfile.mkdtemp()) / "x.bentcorner"
        f.write_bytes(trade.MAGIC + zlib.compress(json.dumps(d).encode()))
        return f

    def test_damaged_rows(self):
        from collection import trade
        base = {"app": "BentCorner", "id": "abc"}
        for c in ({"no": "list"}, [1, 2], [["a", "1", "en", 0, [], "x"]], [["a", "1", "en", 0, "inf", "x"]], [["a"]]):
            with self.assertRaises(ValueError) as e:
                trade.read_file(self.bentcorner(dict(base, c=c)))
            self.assertEqual(str(e.exception), trade.BROKEN, c)
        ok = trade.read_file(self.bentcorner(dict(base, c=[["ABC", 7, "..", 1, "3", "Card", "sid1"]])))
        self.assertEqual(ok["data"]["c"], [["ABC", "7", "en", 1, 3, "Card", "sid1"]])

    def test_deep_nesting_is_a_message_too(self):
        import tempfile, pathlib, zlib
        from collection import trade
        f = pathlib.Path(tempfile.mkdtemp()) / "deep.bentcorner"
        f.write_bytes(trade.MAGIC + zlib.compress(b"[" * 100000 + b"]" * 100000))
        with self.assertRaises(ValueError):
            trade.read_file(f)

    def test_language(self):
        from collection import trade
        self.assertEqual([trade.lang_of(x) for x in ("..", "a/b", "German", "JA", "", "zhs", "xx")],
                         ["en", "en", "de", "ja", "en", "zhs", "en"])

    def test_german(self):
        from locales import de
        from collection import trade
        self.assertIn(trade.BROKEN, de.TEXTS)


class WipeForeignDataTest(unittest.TestCase):
    """7 – "Delete Bent°Corner" never takes an unrelated data folder along (F9). Throwaway folders only – never a real
    data folder or %LOCALAPPDATA% (lead 10.11.)."""

    def setUp(self):
        import tempfile, pathlib
        from unittest import mock
        from system import datastore, wipe
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = pathlib.Path(self.tmp.name)
        self.drive, self.roaming, self.local = t / "D", t / "Roaming", t / "Local"   # "D:\" picked as the data folder
        for d in (self.drive / "data" / "holiday-photos", self.roaming, self.local):
            d.mkdir(parents=True)
        (self.drive / "data" / "holiday-photos" / "1.jpg").write_bytes(b"jpg")
        (self.drive / "settings.json").write_text("{}", "utf-8")
        for p in (mock.patch.object(wipe, "BASE", self.drive),
                  mock.patch.object(datastore, "BACKUPS", self.drive / "data" / "backups"),
                  mock.patch.object(wipe.datahome, "_config_dir", lambda: self.roaming),
                  mock.patch.object(wipe, "_local_home", lambda: self.local)):
            p.start()
            self.addCleanup(p.stop)

    def test_foreign_data_stays(self):
        from system import wipe
        p = wipe.plan({})
        self.assertNotIn(str(self.drive / "data"), p.delete)
        self.assertEqual(wipe.wipe(p), [])
        self.assertTrue((self.drive / "data" / "holiday-photos" / "1.jpg").exists())
        self.assertFalse((self.drive / "settings.json").exists())   # ours: gone as before

    def test_ours_goes(self):
        from system import wipe
        (self.drive / "data" / "my-data").mkdir()
        self.assertIn(str(self.drive / "data"), wipe.plan({}).delete)


class RestoreVsAutoBackupTest(__import__("tests.test_autobackup", fromlist=["_Home"])._Home):
    """8 – restoring never runs next to the automatic backup; afterwards none until the restart (F10)."""

    def setUp(self):
        super().setUp()
        self.bk = self.root / "backup"
        (self.bk / "my-data").mkdir(parents=True)
        (self.bk / "my-data" / "collection.json").write_text('{"items": []}', "utf-8")
        self.write("data/my-data/collection.json", '{"items": [{"uid": "a", "count": 1}]}')

    def test_waits_for_a_running_backup(self):
        from unittest import mock
        from system import autobackup, datastore
        autobackup._lock.acquire()
        try:
            with mock.patch.object(autobackup, "RESTORE_WAIT", 0.2):
                with self.assertRaises(datastore.RestoreError):
                    datastore.restore_backup(self.bk)
        finally:
            autobackup._lock.release()
        self.assertIn('"uid": "a"', (self.data / "my-data" / "collection.json").read_text("utf-8"))   # untouched
        self.assertFalse(autobackup.restored)

    def test_no_backup_after_a_restore(self):
        from system import autobackup, datastore
        self.assertTrue(datastore.restore_backup(self.bk))
        self.assertTrue(autobackup.restored)
        autobackup.add_target(self.s, self.stick)
        self.assertEqual(autobackup.run(self.s, force=True, only_changed=False), [])
        self.assertFalse((self.stick / autobackup.FOLDER).exists() and any((self.stick / autobackup.FOLDER).iterdir()))


class TicketImageSizeTest(unittest.TestCase):
    """9 – a huge image is refused from its header, before it is decoded (T8)."""

    def test_huge_image_refused_before_decoding(self):
        import tempfile, pathlib
        from unittest import mock
        from PySide6 import QtGui
        from collection import ticket
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "big.png"
            QtGui.QImage(400, 300, QtGui.QImage.Format_RGB32).save(str(f))
            with mock.patch.object(ticket, "MAX_PIXELS", 400 * 300 - 1),                     mock.patch.object(QtGui, "QImage", side_effect=AssertionError("decoded")):
                with self.assertRaises(ValueError) as e:
                    ticket.read_image(f)
            self.assertEqual(str(e.exception), ticket.TOO_BIG)
            self.assertIsNone(ticket.read_image(f))   # normal size: read as before (no ticket in it)

    def test_german(self):
        from locales import de
        from collection import ticket
        self.assertIn(ticket.TOO_BIG, de.TEXTS)


if __name__ == "__main__":
    unittest.main()
