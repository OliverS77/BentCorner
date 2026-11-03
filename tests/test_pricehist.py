"""Price history (cards/pricehist.py) and collection value over time (cards/valuehist.py): compacting to price
changes, the 90-day window, merging records, MTGJSON entries, series()/series_many() on a temp SQLite file, the
status() cache, and the value curve (owned-since day, no back-fill, foil/USD fallback, grey line of older cards).
pricehist.DB points into a temp folder; downloads (_download, _build_date, netpolite.get) are blocked.

    python -m unittest tests/test_pricehist.py
"""
import datetime
import pathlib
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from cards import currency, pricehist, valuehist
from net import netpolite

W = pricehist.WINDOW


def _no_net(*a, **k):
    raise AssertionError("no network in tests")


class _DB(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self._tmp.name) / "card-data" / "price-history.sqlite"
        self.cons = []
        real_connect = sqlite3.connect

        def connect(*a, **k):   # remember every connection: closed in tearDown so the temp file can go
            con = real_connect(*a, **k)
            self.cons.append(con)
            return con
        self.p = [mock.patch.object(pricehist, "DB", self.db),
                  mock.patch.object(pricehist.sqlite3, "connect", connect),
                  mock.patch.object(pricehist, "_download", _no_net),
                  mock.patch.object(pricehist, "_build_date", _no_net),
                  mock.patch.object(netpolite, "get", _no_net),
                  mock.patch.object(pricehist, "_status_cache", {})]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in reversed(self.p):
            p.stop()
        for con in self.cons:   # see the finding below: a leaked connection keeps the file locked on Windows
            con.close()
        self._tmp.cleanup()

    def store(self, records):
        con = pricehist._connect()
        try:
            pricehist._write(con, records)
        finally:
            con.close()


class Pure(unittest.TestCase):
    def test_days(self):
        self.assertEqual(pricehist.day_of("1970-01-02"), 1)
        self.assertEqual(pricehist.date_of(pricehist.day_of("2026-10-26")), datetime.date(2026, 10, 26))

    def test_changes_keeps_only_price_changes(self):
        pts = [(1, 1.0), (2, 1.0), (3, 2.0), (4, 2.0), (5, 1.0)]
        self.assertEqual(pricehist._changes(pts), [[1, 1.0], [3, 2.0], [5, 1.0]])
        self.assertEqual(pricehist._changes([]), [])

    def test_window(self):
        end = 200
        cut = end - W + 1
        inside = [[cut + 5, 2.0]]
        self.assertEqual(pricehist._window(inside, end), inside)                       # all inside: unchanged
        self.assertEqual(pricehist._window([[10, 1.0], [cut + 5, 2.0]], end), [[cut, 1.0], [cut + 5, 2.0]])
        self.assertEqual(pricehist._window([[10, 1.0], [20, 3.0]], end), [[cut, 3.0]])   # last price carried in
        self.assertEqual(pricehist._window([[10, 1.0], [cut, 4.0]], end), [[cut, 4.0]])
        self.assertEqual(pricehist._window([], end), [])

    def test_merge_new_wins_and_window_applied(self):
        old = {"e": 100, "cn": [[50, 1.0], [80, 2.0]], "tn": [[60, 5.0]]}
        new = {"e": 101, "cn": [[80, 2.5], [101, 2.5]], "cf": [[101, 9.0]]}
        m = pricehist._merge(old, new)
        self.assertEqual(m["e"], 101)
        self.assertEqual(m["cn"], [[50, 1.0], [80, 2.5]])                 # day 80 replaced, day 101 = no change
        self.assertEqual(m["cf"], [[101, 9.0]])
        self.assertEqual(m["tn"], [[60, 5.0]])
        self.assertNotIn("tf", m)
        far = pricehist._merge({"e": 10, "cn": [[1, 1.0]]}, {"e": 10 + 2 * W, "cn": [[10 + 2 * W, 3.0]]})
        self.assertEqual(far["cn"], [[10 + W + 1, 1.0], [10 + 2 * W, 3.0]])   # old part trimmed to the window

    def test_entry_from_mtgjson(self):
        paper = {"cardmarket": {"retail": {"normal": {"2026-10-01": 1.004, "2026-10-02": 1.0, "2026-10-03": 1.5},
                                           "foil": {"2026-10-02": None}}},
                 "tcgplayer": {"retail": {"foil": {"2026-10-04": "3.333"}}},
                 "cardkingdom": {"retail": {"normal": {"2026-10-09": 9.0}}}}   # not one of our sources
        e = pricehist._entry(paper)
        d1 = pricehist.day_of("2026-10-01")
        self.assertEqual(e["cn"], [[d1, 1.0], [d1 + 2, 1.5]])
        self.assertEqual(e["tf"], [[d1 + 3, 3.33]])
        self.assertNotIn("cf", e)                                         # only None prices: no series
        self.assertEqual(e["e"], d1 + 3)
        self.assertEqual(pricehist._entry({}), {})

    def test_pack_round_trip_and_current(self):
        e = {"e": 5, "cn": [[1, 1.5], [4, 2.0]], "tf": [[3, 7.0]]}
        self.assertEqual(pricehist._unpack(pricehist._pack(e)), e)
        self.assertEqual(pricehist._current(e), {"eur": 2.0, "usd_foil": 7.0})


class Series(_DB):
    def test_missing_db(self):
        self.assertFalse(pricehist.exists())
        self.assertIsNone(pricehist.series("x"))
        self.assertEqual(pricehist.series_many(["x"]), {})
        self.assertIsNone(pricehist.status())
        self.assertFalse(self.db.exists())                                # reading never creates the file

    def test_series_daily_resolution(self):
        self.store({"a": {"e": 1005, "cn": [[1000, 1.0], [1003, 2.0]], "tf": [[1005, 4.0]]}})
        s = pricehist.series("a")
        d = pricehist.date_of
        self.assertEqual(s["cn"], [(d(1000), 1.0), (d(1001), 1.0), (d(1002), 1.0), (d(1003), 2.0), (d(1004), 2.0),
                                   (d(1005), 2.0)])
        self.assertEqual(s["tf"], [(d(1005), 4.0)])
        self.assertIsNone(pricehist.series("unknown"))

    def test_series_window_and_series_many_agree(self):
        recs = {"a": {"e": 500, "cn": [[100, 1.0], [480, 2.0]]},
                "b": {"e": 500, "cf": [[499, 3.0]]},
                "c": {"e": 500}}                                          # no series at all
        self.store(recs)
        a = pricehist.series("a")
        self.assertEqual(len(a["cn"]), W)                                 # exactly the window, day by day
        self.assertEqual(a["cn"][0], (pricehist.date_of(500 - W + 1), 1.0))
        many = pricehist.series_many(["a", "b", "c", "a", "zzz"])
        self.assertEqual(set(many), {"a", "b"})
        self.assertEqual(many["a"], a)
        self.assertEqual(many["b"], pricehist.series("b"))
        self.assertIsNone(pricehist.series("c"))

    def test_series_many_large_batch(self):
        self.store({f"s{i}": {"e": 10, "cn": [[10, float(i)]]} for i in range(1200)})   # more than one IN query
        many = pricehist.series_many([f"s{i}" for i in range(1200)])
        self.assertEqual(len(many), 1200)
        self.assertEqual(many["s1199"]["cn"], [(pricehist.date_of(10), 1199.0)])

    def test_write_merge(self):
        self.store({"a": {"e": 100, "cn": [[90, 1.0]]}})
        con = pricehist._connect()
        try:
            self.assertEqual(pricehist._write(con, {"a": {"e": 101, "cn": [[101, 2.0]]}}, merge=True), 1)
            self.assertEqual(pricehist._write(con, {}), 0)
        finally:
            con.close()
        s = pricehist.series("a")["cn"]
        self.assertEqual((s[0], s[-1]), ((pricehist.date_of(90), 1.0), (pricehist.date_of(101), 2.0)))

    def test_status_cached_until_file_changes(self):
        self.store({"a": {"e": 1, "cn": [[1, 1.0]]}})
        con = pricehist._connect()
        con.execute("INSERT OR REPLACE INTO meta VALUES ('updated', '123')")
        con.commit()
        con.close()
        calls = []
        real = pricehist._status_uncached

        def counted():
            calls.append(1)
            return real()
        with mock.patch.object(pricehist, "_status_uncached", counted):
            st = pricehist.status()
            self.assertEqual((st["cards"], st["updated"]), (1, 123))
            self.assertIs(pricehist.status(), st)
            self.assertEqual(len(calls), 1)                               # second call from the cache
            time.sleep(0.02)
            self.store({"b": {"e": 1, "cn": [[1, 1.0]]}})
            self.assertEqual(pricehist.status()["cards"], 2)
            self.assertEqual(len(calls), 2)

    def test_status_empty_or_corrupt(self):
        self.store({})
        self.assertIsNone(pricehist.status())                             # file there, but no cards
        self.db.write_bytes(b"not a database at all" * 100)
        pricehist._status_cache.clear()
        self.assertIsNone(pricehist.status())
        self.assertIsNone(pricehist.series("a"))
        self.assertEqual(pricehist.series_many(["a"]), {})

    # finding: cards/pricehist.py _connect – if the CREATE TABLE statements fail (corrupt file), the freshly opened
    # connection is never closed; on Windows the file then stays locked until garbage collection, so delete() (the
    # way out of a corrupt history) raised PermissionError. Fixed 2026-10-26: _connect closes it when the setup fails.
    def test_corrupt_db_can_be_deleted(self):
        self.db.parent.mkdir(parents=True)
        self.db.write_bytes(b"not a database at all" * 100)
        self.assertIsNone(pricehist.status())
        pricehist.delete()
        self.assertFalse(self.db.exists())

    def test_seen_and_note(self):
        con = pricehist._connect()
        try:
            self.assertFalse(pricehist._seen(con, "2026-10-26", "hist"))
            pricehist._note(con, "2026-10-26", "hist")
            self.assertTrue(pricehist._seen(con, "2026-10-26", "hist"))
            self.assertFalse(pricehist._seen(con, "2026-10-26", "prices"))
            self.assertFalse(pricehist._seen(con, None, "hist"))          # offline: never "seen"
        finally:
            con.close()

    def test_delete(self):
        self.store({"a": {"e": 1, "cn": [[1, 1.0]]}})
        pricehist.delete()
        self.assertFalse(self.db.exists())
        pricehist.delete()                                                # twice is fine


def _ts(day):
    return time.mktime(day.timetuple()) + 12 * 3600


class ValueHistory(_DB):
    """collection_series with the history stored in the temp DB (today = last day of the window)."""

    def setUp(self):
        super().setUp()
        self.today = datetime.date.today()
        self.t0 = pricehist.today()
        self.start = self.today - datetime.timedelta(days=W - 1)

    def test_empty(self):
        self.assertIsNone(valuehist.collection_series([], {}))
        self.assertIsNone(valuehist.collection_series([{"id": "x", "added": _ts(self.today)}], {}))   # no price at all

    def test_owned_since_and_no_backfill(self):
        old = self.today - datetime.timedelta(days=200)
        self.store({"a": {"e": self.t0, "cn": [[self.t0 - 200, 2.0], [self.t0 - 10, 3.0]]},
                    "n": {"e": self.t0, "cn": [[self.t0 - 5, 50.0]]}})     # new set: first price 5 days ago
        items = [{"id": "a", "count": 2, "added": _ts(old)},
                 {"id": "n", "count": 1, "added": _ts(old)},
                 {"id": "a", "count": 1, "src": "sess1/1.0", "added": _ts(old)}]
        sess_day = self.today - datetime.timedelta(days=20)
        res = valuehist.collection_series(items, {"sess1": _ts(sess_day)})
        v = res["values"]
        self.assertEqual(len(v), W)
        self.assertEqual(res["days"][0], self.start)
        self.assertEqual(v[0], 4.0)                                       # 2 copies × 2 €
        i_sess = (sess_day - self.start).days
        self.assertEqual((v[i_sess - 1], v[i_sess]), (4.0, 6.0))          # session copy counts from its day
        self.assertEqual(v[W - 11], 9.0)                                  # price change: 3 × 3 €
        self.assertEqual((v[W - 7], v[W - 6]), (9.0, 59.0))               # new card only from its first price
        self.assertEqual(res["adds"][i_sess], (1, 2.0))
        self.assertEqual(v[-1], 59.0)
        self.assertEqual(res["base"][-1], 56.0)                           # grey line: without the session copy
        self.assertEqual(res["base_day"], 0)
        self.assertEqual(res["flat"], 0)

    def test_foil_usd_and_flat_fallbacks(self):
        self.store({"f": {"e": self.t0, "cn": [[self.t0 - 100, 1.0]], "cf": [[self.t0 - 100, 5.0]]},
                    "u": {"e": self.t0, "tn": [[self.t0 - 100, 10.0]]}})
        items = [{"id": "f", "foil": True, "added": 1},
                 {"id": "u", "added": 1},
                 {"id": "x", "added": 1, "eur": 0.5, "count": 2}]          # no history: today's price, flat
        with mock.patch.object(currency, "from_usd", lambda p: p * 0.5):
            res = valuehist.collection_series(items, {})
        self.assertEqual(res["values"][0], 5.0 + 5.0 + 1.0)
        self.assertEqual(res["values"][-1], 11.0)
        self.assertEqual(res["flat"], 2)

    def test_chart_spec(self):
        self.store({"a": {"e": self.t0, "cn": [[self.t0 - 100, 2.0], [self.t0 - 1, 3.0]]}})
        res = valuehist.collection_series([{"id": "a", "added": 1}], {})
        spec = valuehist.chart_spec(res, title="T")
        self.assertEqual((spec["kind"], spec["title"], spec["body"]["type"]), ("frame", "T", "line"))
        self.assertEqual(len(spec["body"]["tips"]), W)
        self.assertIn("+50,0 %", spec["sub"])
        self.assertEqual(valuehist.chart_spec(None)["body"]["type"], "empty")

    def test_marks_group_close_additions(self):
        marks = valuehist._marks({10: (1, 1.0), 11: (2, 1.0), 40: (1, 1.0)}, W)
        self.assertEqual(marks, [{"i": 10, "label": "+3"}, {"i": 40, "label": "+1"}])


if __name__ == "__main__":
    unittest.main()
