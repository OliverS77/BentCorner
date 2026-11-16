"""lead 14.11.2026: (1) tools/build_yugioh_db.py stops when too few prints get a euro price (no exchange rates), (2) the
price history's one-time backups go after 60 days – by the day their cleanup wrote into the history's meta (copy2 kept
the original's file date), the file date only as fallback.

    python -m unittest tests.test_housekeep
"""
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
try:   # private builder – not in the public source (tools/public/manifest.txt)
    import build_yugioh_db as ygo  # noqa: E402
except ImportError:
    ygo = None

from cards import pricehist  # noqa: E402


@unittest.skipIf(ygo is None, "tools/build_yugioh_db.py is not part of this source")
class Euros(unittest.TestCase):
    def test_enough(self):
        rows = [{"usd": 1.0, "eur": 0.9}] * 95 + [{"usd": 1.0, "eur": None}] * 5 + [{"usd": None, "eur": None}] * 50
        self.assertAlmostEqual(ygo.check_euros(rows), 0.95)

    def test_too_few_stops(self):
        rows = [{"usd": 1.0, "eur": 0.9}] * 10 + [{"usd": 1.0, "eur": None}] * 90   # like 14.11.: no rates
        with self.assertRaises(SystemExit):
            ygo.check_euros(rows)

    def test_new_build(self):
        self.assertEqual(ygo.BUILD, "9")

    def test_no_ygoprodeck_cardmarket(self):   # Oliver/legal 16.11.2026 (E1c): euros only converted (≈)
        import inspect
        self.assertNotIn('pr.get("cardmarket_price")', inspect.getsource(ygo))
        self.assertEqual(ygo.EUR_MIN_SHARE, 0.9)


class Backups(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        p = mock.patch.object(pricehist, "DB", self.tmp / "price-history.sqlite")
        p.start()
        self.addCleanup(p.stop)
        hc = pricehist._connect()
        today = pricehist.today()
        hc.executemany("INSERT INTO meta VALUES (?, ?)", [("ygo_cm_per_card_cleared", str(today - 61)),
                                                          ("ygo_cn_converted_cleared", str(today - 3))])
        hc.commit()
        hc.close()
        self.cm = self.tmp / "price-history.before-cm-fix.sqlite"
        self.cn = self.tmp / "price-history.before-cn-conv-fix.sqlite"
        self.other = self.tmp / "price-history.before-something.sqlite"
        for p in (self.cm, self.cn, self.other):
            p.write_bytes(b"x")
        os.utime(self.cm, (0, 2_000_000_000))   # copy2: the original's (recent) date – must not count
        old = (pricehist.today() - 70) * 86400
        os.utime(self.other, (old, old))   # unknown backup: by its file date

    def test_by_the_day_of_the_cleanup(self):
        gone = pricehist.drop_old_backups()
        self.assertEqual(sorted(gone), ["price-history.before-cm-fix.sqlite", "price-history.before-something.sqlite"])
        self.assertTrue(self.cn.exists())   # 3 days old: stays
        self.assertTrue(pricehist.DB.exists())   # the history itself is never touched
        self.assertEqual(pricehist.drop_old_backups(), [])


if __name__ == "__main__":
    unittest.main()
