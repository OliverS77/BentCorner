"""Switch off the accessibility interface (Windows UI Automation) for Bent°Corner.

Other programs (overlays, recording software, assistive tools …) query the UI via the window message WM_GETOBJECT;
Qt then switches on its accessibility layer. That layer holds references to Qt Quick items that are constantly
recreated on page switches and window dragging – in Qt 6.11 this led to crashes (access violation in
QTextFrame::begin or in the QQuickTextInput destructor). We don't answer WM_GETOBJECT – the layer stays off.
Can be switched off via the setting "accessibility": true (e.g. for screen readers).
"""
import ctypes
import ctypes.wintypes as wt
import sys

from PySide6 import QtCore

WM_GETOBJECT = 0x003D
_filter = None


class _UiaGuard(QtCore.QAbstractNativeEventFilter):
    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) == b"windows_generic_MSG":  # comes as a QByteArray
                msg = wt.MSG.from_address(int(message))
                if msg.message == WM_GETOBJECT:
                    return True, 0
        except Exception:  # noqa: BLE001 – when in doubt, do nothing
            pass
        return False, 0


def hard_exit(code=0):
    """Quit immediately, without Windows still running Qt cleanup work while unloading (that crashed on
    exit when the accessibility layer was active). Everything must be saved beforehand."""
    if sys.platform == "win32":
        k32 = ctypes.WinDLL("kernel32")   # own instance with fixed types (handle = pointer, not int)
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        k32.TerminateProcess(k32.GetCurrentProcess(), int(code) & 0xFFFFFFFF)
    import os
    os._exit(code)


def install(app):
    """Once after creating the QApplication (Windows only)."""
    global _filter
    if sys.platform != "win32" or _filter is not None:
        return
    _filter = _UiaGuard()
    app.installNativeEventFilter(_filter)
