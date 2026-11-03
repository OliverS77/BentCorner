"""The loading sign for work that blocks the GUI thread for a moment (Oliver, 29.10.: a short freeze is fine, but
always with the loading sign, so nobody thinks the app crashed).

    with busy(ctrl, tr("Backing up …")):
        datastore.create_backup(dest)

Shows the central loading sign (qml/components/Loading.qml) with the text in a small card over the window, lets
the window paint it once (a few frames, without leaving the caller), then runs the block. The deck keeps moving
during the block when the render loop is threaded (see the "Render loop" line in the log). Without a Qt Quick
window (tests, first start) it does nothing."""
import contextlib

from PySide6 import QtCore

PAINT_MS = 70   # long enough for at least one frame with the card on it


@contextlib.contextmanager
def busy(ctrl, text=""):
    shell = getattr(ctrl, "shell", None)
    if shell is None or getattr(shell, "window", None) is None or not hasattr(shell, "set_busy"):
        yield
        return
    shell.set_busy(text or " ")
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(PAINT_MS, loop.quit)
    loop.exec(QtCore.QEventLoop.ExcludeUserInputEvents)   # paint it, but no clicks meanwhile
    try:
        yield
    finally:
        shell.set_busy("")
