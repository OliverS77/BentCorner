"""When did the user last do something in the window? (mouse click, key, scroll wheel, touch)

Only the time is noted – nothing about what was clicked. Used to slow down background work that talks to our
server while nobody is at the PC (SERVER-REGELN 6: the mailbox asks every 15 minutes instead of every 3 after 30
minutes without input). Installed on the main window only (not the whole application), so ordinary events (paint,
timers) never reach Python.
"""
import time

from PySide6 import QtCore

INPUT = {QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.Wheel,
         QtCore.QEvent.Type.TouchBegin}


class Activity(QtCore.QObject):
    """Event filter: last = monotonic time of the last input. on_wake() runs on the first input after idle_after s."""

    def __init__(self, parent=None, idle_after=30 * 60, on_wake=None):
        super().__init__(parent)
        self.last = time.monotonic()
        self.idle_after = idle_after
        self.on_wake = on_wake

    def idle_for(self, now=None):
        return (now if now is not None else time.monotonic()) - self.last

    def idle(self, now=None):
        return self.idle_for(now) >= self.idle_after

    def touch(self, now=None):
        """An input: note it; after a long pause also wake whoever waits for it."""
        now = now if now is not None else time.monotonic()
        was_idle = self.idle(now)
        self.last = now
        if was_idle and self.on_wake is not None:
            self.on_wake()

    def eventFilter(self, obj, ev):
        if ev.type() in INPUT:
            self.touch()
        return False   # only watching – the event goes on as usual
