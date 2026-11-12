"""Bent°Corner in the system tray of the taskbar (bottom right by the clock).

If "Keep running in the system tray" is on, closing the window doesn't quit the program: it saves, switches camera
and AI off (frees the memory) and stays as a small icon. From there it fetches prices once a day and reports
price alerts as Windows notifications. Optionally it starts with Windows, straight away invisible in the system tray.

Single instance only (per Windows user, Oliver 03.11.2026): a second start – starter, exe or shortcut – brings the
running window to the front, also out of the tray, and quits (QLocalServer). The server listens from the very start
(claim(), before the first-run setup); requests wait until the main window takes over (attach()).
"""
import gc
import logging
import sys
import time

from PySide6 import QtCore, QtNetwork, QtWidgets

from system import datahome
from system.i18n import tr

def _server_name():
    """One instance per Windows user, whatever the data folder (lead 03.11.2026). Test runs (BC_STARTER_* test
    folders, BC_HOME) get one per test folder instead: they never block the real program or bring its window up."""
    import getpass
    import hashlib
    import os
    key = "user:" + (os.environ.get("USERNAME") or getpass.getuser()).lower()
    # BC_HOME only counts where datahome follows it (from the source): in the exe it would only split the lock
    if datahome.ISOLATED or (not datahome.FROZEN and os.environ.get("BC_HOME", "").strip()):
        key = "test:" + str(datahome.HOME).lower()
    return "BentCorner-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


SERVER = _server_name()
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "BentCorner"
log = logging.getLogger("booster")  # like app.py (ends up in bentcorner.log)
CHECK_MS = 20 * 60 * 1000  # check every 20 minutes whether today's prices are already there


# ---------- single instance only ----------
def _allow_foreground(pid):
    """Windows only lets the process the user just started take the foreground – this one hands that right to the
    running instance, so its window really comes to the front (also out of the tray)."""
    if sys.platform == "win32" and pid:
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(int(pid))
        except Exception:  # noqa: BLE001
            pass


def other_instance():
    """Is Bent°Corner already running? Then have it show its window there -> True (this instance quits). The running
    one answers with its process ID first (for AllowSetForegroundWindow), then gets "show"."""
    sock = QtNetwork.QLocalSocket()
    sock.connectToServer(SERVER)
    if not sock.waitForConnected(300):
        return False
    pid = 0
    if sock.waitForReadyRead(500):
        raw = bytes(sock.readAll()).decode("ascii", "ignore")
        if raw.startswith("pid "):
            pid = int(raw[4:].strip() or 0)
    _allow_foreground(pid)
    sock.write(b"show")
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


_server = {"server": None, "on_show": None, "pending": False, "mutex": None}


def acquire():
    """Am I the first? A named mutex answers that atomically – two starts in the same moment (double click, two
    starters) would otherwise both ask the pipe before either listens, and Windows lets both listen. -> True = first.
    The mutex lives until release() or the end of the process."""
    if sys.platform != "win32":
        return True
    if _server["mutex"]:
        return True
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = ctypes.c_void_p
    h = k32.CreateMutexW(None, False, "Local\\" + SERVER)
    if k32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS: another instance holds it
        k32.CloseHandle(ctypes.c_void_p(h))
        return False
    _server["mutex"] = h
    return True


def show_other(seconds=5.0):
    """Another instance holds the lock: ask it to show its window – it may still be starting, so try a few times."""
    end = time.time() + seconds
    while time.time() < end:
        if other_instance():
            return True
        time.sleep(0.2)
    return False


def _show():
    if _server["on_show"] is not None:
        _server["on_show"]()
    else:
        _server["pending"] = True   # still in the first-run setup / starting: shown once the window is there


def claim():
    """Listen for later starts right away (before the first-run setup). -> the server (close() it before a restart)."""
    import os
    if _server["server"] is not None:
        return _server["server"]
    QtNetwork.QLocalServer.removeServer(SERVER)  # leftovers of a crashed run
    server = QtNetwork.QLocalServer()
    server.setSocketOptions(QtNetwork.QLocalServer.UserAccessOption)

    def incoming():
        sock = server.nextPendingConnection()
        if sock is not None:
            sock.write(f"pid {os.getpid()}".encode("ascii"))
            sock.readyRead.connect(lambda: (sock.readAll(), _show()))
    server.newConnection.connect(incoming)
    server.listen(SERVER)
    _server["server"] = server
    return server


def release():
    """Stop listening and give up the lock (before starting the next instance: restart, relaunch after the first-run
    setup, moving the data folder)."""
    if _server["server"] is not None:
        _server["server"].close()
        _server["server"] = None
    if _server["mutex"]:
        import ctypes
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_server["mutex"]))
        _server["mutex"] = None


def listen(on_show):
    """The main window takes over: later starts call on_show (a request during the start is answered now)."""
    server = claim()
    _server["on_show"] = on_show
    if _server["pending"]:
        _server["pending"] = False
        QtCore.QTimer.singleShot(0, on_show)
    return server


# ---------- autostart ----------
def autostart_possible():
    from system import datahome
    return (sys.platform == "win32" and getattr(sys, "frozen", False)
            and not datahome.TEST and not datahome.ISOLATED)   # test start / isolated test run: never the registry


def _run_value():
    """The current "BentCorner" autostart entry (its command line) or None."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, RUN_NAME)[0]
    except OSError:
        return None


def _is_ours(value):
    """Does the entry start THIS program? There is only one entry name for all installations – another one (Oliver's
    PC installation, a copy on a USB stick) has its own path."""
    import os
    exe = str(value or "").strip()
    exe = exe[1:].split('"', 1)[0] if exe.startswith('"') else exe.split(" ", 1)[0]
    if not exe:
        return False
    return os.path.normcase(os.path.abspath(exe)) == os.path.normcase(os.path.abspath(datahome.program()))


def autostart_enabled():
    """Does THIS installation start with Windows? (an entry of another installation doesn't count)"""
    if sys.platform != "win32":
        return False
    value = _run_value()
    return value is not None and _is_ours(value)


def set_autostart(on):
    """Start with Windows (invisible in the system tray) – only for the finished .exe. Switching off only removes an
    entry of THIS program: the setup of a second installation (e.g. a portable copy) used to delete the autostart of
    the real one (0.9.7.8). Switching on is an explicit choice here, so it takes the entry over (logged)."""
    if not autostart_possible():
        return False
    import winreg
    current = _run_value()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                if current and not _is_ours(current):
                    log.info("Autostart: taking over the entry of another installation (%s)", current)
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, f'"{datahome.program()}" --tray')
            elif current and _is_ours(current):
                winreg.DeleteValue(k, RUN_NAME)
            elif current:
                log.info("Autostart: the entry belongs to another installation – left as it is")
        return True
    except OSError:
        return False


# ---------- notice in the window ----------
class Tray(QtCore.QObject):
    """System tray icon + daily price check + notifications. ctrl: MainWindow."""

    def __init__(self, ctrl):
        super().__init__(ctrl)
        self.ctrl = ctrl
        self.hidden = False
        self.icon = None
        self._timer = QtCore.QTimer(self, interval=CHECK_MS, timeout=self.daily)
        self._timer.start()
        self.server = listen(self.restore)
        self.apply()

    @property
    def enabled(self):
        """Isolated test copies never stay in the tray: closing the window quits them (Oliver 05.11.2026 – a test
        version ends when the user ends it, no Task Manager needed)."""
        return (bool(self.ctrl.settings.get("tray_mode")) and not datahome.ISOLATED
                and QtWidgets.QSystemTrayIcon.isSystemTrayAvailable())

    def apply(self):
        """Setting changed: show/hide the icon."""
        if self.enabled and self.icon is None:
            from ui import iconkit
            self.icon = QtWidgets.QSystemTrayIcon(iconkit.qicon(), self)
            iconkit.on_icon_change(self.icon.setIcon)   # taskbar switches light/dark: the mark follows
            self.icon.setToolTip("Bent°Corner")
            menu = QtWidgets.QMenu()
            menu.addAction(tr("Open Bent°Corner"), self.restore)
            menu.addAction(tr("Update prices now"), self.ctrl.update_all)
            menu.addAction(tr("Price alerts …"), self.ctrl.show_alarms)
            menu.addSeparator()
            menu.addAction(tr("Quit"), self.quit)
            self.icon.setContextMenu(menu)
            self._menu = menu
            self.icon.activated.connect(self._activated)
            self.icon.messageClicked.connect(self.restore)
        if self.icon is not None:
            self.icon.setVisible(self.enabled)
        log.info("Tray: %s (available: %s)", "on" if self.enabled else "off",
                 QtWidgets.QSystemTrayIcon.isSystemTrayAvailable())

    def _activated(self, reason):
        if reason in (QtWidgets.QSystemTrayIcon.Trigger, QtWidgets.QSystemTrayIcon.DoubleClick):
            self.restore()

    # --- hide / show ---
    def hide_to_tray(self, first=False):
        """Window closed: save, camera and AI off (memory freed), icon stays."""
        ctrl = self.ctrl
        self.hidden = True
        log.info("Tray: window hidden%s", " (start with Windows)" if first else "")
        if not first:
            ctrl.save_settings()
            ctrl.save_session()
            ctrl.save_collection()
        if ctrl.library_win is not None and ctrl.library_win.isWindow():
            ctrl.library_win.hide()
        ctrl.stream.hide()
        ctrl.camera.stop()
        ctrl.recognizer.fp_index = None
        from scanner import fingerprint
        fingerprint.release()
        gc.collect()
        if not first and self.icon is not None and not ctrl.settings.get("tray_hint_shown"):
            ctrl.settings["tray_hint_shown"] = True
            self.icon.showMessage("Bent°Corner", tr("Keeps running in the system tray – fetches prices once a day and reports price alerts. Right-click the icon to quit."),
                                  QtWidgets.QSystemTrayIcon.Information, 6000)
        self.daily()

    def restore(self):
        ctrl = self.ctrl
        st = ctrl.stream
        if self.hidden:
            self.hidden = False
            st.showFullScreen() if ctrl.settings.get("start_fullscreen") else st.showMaximized()
            ctrl.camera_selected()
            ctrl.update_fingerprints(ctrl.cards)
        elif st.isMinimized():
            st.showMaximized()
        st.raise_()
        st.activateWindow()

    def quit(self):
        self.ctrl.force_quit = True
        if self.hidden:  # window is already saved and hidden
            self.ctrl.closing = False
        self.ctrl.request_quit()

    # --- daily ---
    def daily(self):
        """Today's prices not there yet? Then fetch them (in the system tray or when the window has been open long)."""
        ctrl = self.ctrl
        from system import orbit
        if not orbit.prices_on(ctrl.settings) or not (self.enabled or orbit.price_mode(ctrl.settings) == "daily"):
            return
        if ctrl.settings.get("last_price_day") == time.strftime("%Y-%m-%d"):
            return
        if any(j["kind"] == "prices" for j in ctrl.jobs) or (ctrl.current or {}).get("kind") == "prices":
            return
        log.info("Tray: fetching daily prices")
        ctrl.update_all()

    # --- notifications ---
    def notify(self, title, text):
        """Windows notification (system tray) or a notice in the window."""
        if self.icon is not None and self.icon.isVisible():
            self.icon.showMessage(title, text, QtWidgets.QSystemTrayIcon.Information, 8000)
        shell = getattr(self.ctrl, "shell", None)
        if not self.hidden and shell is not None and self.ctrl.stream.isVisible():
            shell.show_toast(f"<b>{title}</b><br>{text}")
