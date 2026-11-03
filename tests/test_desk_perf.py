"""Desktop survey 0.9.3.18 (the biggest stalls first): the search over printed names finds exactly what the loop over
all names found, the file counts of Settings → Card data run in the background and refresh the page once done.

    python -m unittest tests/test_desk_perf.py
"""
import threading
import time
import unittest

from PySide6 import QtCore, QtWidgets

from cards import carddb
from ui import qsetpages, qstate

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _loop(names, words, limit=300):
    """The former search: every printed name in a Python loop."""
    out = set()
    for k in names:
        if all(w in k for w in words):
            out |= names[k]
            if len(out) >= limit:
                break
    return sorted(out)


class PrintedNames(unittest.TestCase):
    def setUp(self):
        self.old = dict(carddb._printed)
        self.addCleanup(lambda: (carddb._printed.clear(), carddb._printed.update(self.old)))
        names = {}
        for i in range(3000):
            names.setdefault(f"blitzschlag {i % 7}", set()).add(f"Lightning Bolt {i % 7}")
            names.setdefault(f"feuriger drache {i}", set()).add(f"Fire Dragon {i}")
            names.setdefault(f"drachenei {i % 50}", set()).add(f"Dragon Egg {i % 50}")
        self.names = names
        carddb._printed.update(idx=names, keys=list(names), blob=None, starts=None, busy=False)

    def test_same_hits_as_the_loop(self):
        for q in ("drache", "blitz", "drachen ei", "feuriger 12", "zzz", "ei drache"):
            words = q.split()
            self.assertEqual(carddb.names_by_printed(q), _loop(self.names, words), q)

    def test_never_a_hit_across_two_names(self):
        carddb._printed.update(idx={"abc": {"A"}, "def": {"D"}}, keys=["abc", "def"], blob=None, starts=None)
        for q in ("cde", "c\nd", "bc de", "(", "*", ".*", "+2 mace"):
            self.assertEqual(carddb.names_by_printed(q), _loop(carddb._printed["idx"], q.lower().split())
                             if sum(len(w) for w in q.split()) >= 3 else [], repr(q))
        self.assertEqual(carddb.names_by_printed("bc de"), [])   # each word in another name: no hit
        self.assertEqual(carddb.names_by_printed("abc"), ["A"])

    def test_a_word_twice_in_one_name_counts_once(self):
        carddb._printed.update(idx={"drache drache": {"Twin Dragon"}}, keys=["drache drache"], blob=None, starts=None)
        self.assertEqual(carddb.names_by_printed("drache"), ["Twin Dragon"])


class BackgroundCount(unittest.TestCase):
    def setUp(self):
        qsetpages._COUNTS.clear()
        self.seen = []
        qstate.watch(self.on_change)
        self.addCleanup(lambda: qstate._watchers.remove(self.on_change))

    def on_change(self):
        self.seen.append(threading.current_thread() is threading.main_thread())

    def test_first_call_does_not_wait_and_the_page_hears_back_in_the_main_thread(self):
        gate = threading.Event()

        def slow():
            gate.wait(5)
            return 42
        t = time.perf_counter()
        self.assertIsNone(qsetpages._cached_count(("t",), slow))   # "counting …"
        self.assertLess(time.perf_counter() - t, 0.5)
        gate.set()
        end = time.monotonic() + 5
        while not self.seen and time.monotonic() < end:
            _app.processEvents()
            time.sleep(0.01)
        self.assertEqual(self.seen, [True])
        self.assertEqual(qsetpages._cached_count(("t",), slow), 42)


if __name__ == "__main__":
    unittest.main()
