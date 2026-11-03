"""Mailbox pace (SERVER-REGELN 6): every 3 min while someone uses the app, every 15 min after 30 min without input,
back to normal (and one fetch right away) on the first input. No window, no network: fake timers.

    python -m unittest tests/test_relay_pace.py
"""
import types
import unittest
from unittest import mock

import app
from system import activity


class _Timer:
    def __init__(self, ms):
        self.ms, self.starts = ms, 0

    def interval(self):
        return self.ms

    def setInterval(self, ms):
        self.ms = ms

    def start(self):
        self.starts += 1


class Activity(unittest.TestCase):
    def test_idle_and_wake_once(self):
        woke = []
        a = activity.Activity(idle_after=60, on_wake=lambda: woke.append(1))
        a.touch(now=1000.0)
        self.assertFalse(a.idle(now=1059.0))
        self.assertTrue(a.idle(now=1060.0))
        a.touch(now=1100.0)           # first input after the pause: wake
        a.touch(now=1101.0)           # not again
        self.assertEqual(woke, [1])

    def test_only_inputs_count(self):
        from PySide6 import QtCore
        a = activity.Activity(idle_after=60)
        a.last = 0.0
        self.assertFalse(a.eventFilter(None, QtCore.QEvent(QtCore.QEvent.Type.Paint)))
        self.assertEqual(a.last, 0.0)   # paint/timer events are not "someone is there"
        a.eventFilter(None, QtCore.QEvent(QtCore.QEvent.Type.KeyPress))
        self.assertGreater(a.last, 0.0)


class Pace(unittest.TestCase):
    def win(self, idle):
        w = types.SimpleNamespace(RELAY_EVERY=180, LISTS_EVERY=300, RELAY_IDLE_EVERY=900,
                                  _relay_t=_Timer(180_000), _lists_t=_Timer(300_000),
                                  activity=types.SimpleNamespace(idle=lambda: idle), settings={})
        return w

    def test_slow_when_idle_normal_when_used(self):
        w = self.win(idle=True)
        app.MainWindow._relay_pace(w)
        self.assertEqual((w._relay_t.ms, w._lists_t.ms), (900_000, 900_000))
        w.activity = types.SimpleNamespace(idle=lambda: False)
        app.MainWindow._relay_pace(w)
        self.assertEqual((w._relay_t.ms, w._lists_t.ms), (180_000, 300_000))

    def test_wake_fetches_once_if_old(self):
        w = self.win(idle=False)
        w._relay_pace = lambda: app.MainWindow._relay_pace(w)
        w._relay_tick = lambda: None
        w._relay_last = 0.0
        shots = []
        with mock.patch("net.relay.enabled", lambda s: True), \
                mock.patch.object(app.QtCore.QTimer, "singleShot", lambda ms, fn: shots.append(ms)):
            app.MainWindow._relay_wake(w)
        self.assertEqual((len(shots), w._relay_t.starts), (1, 1))

    def test_wake_does_nothing_when_friends_off(self):
        w = self.win(idle=False)
        with mock.patch("net.relay.enabled", lambda s: False):
            app.MainWindow._relay_wake(w)
        self.assertEqual(w._relay_t.starts, 0)


if __name__ == "__main__":
    unittest.main()
