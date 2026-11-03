"""Updates via our own server (contacts.SERVER + /dl): signed only, downloaded in the background,
installed on the next start (or at the press of a button).

    /dl/manifest.json       {"v": 1, "latest": "0.8.9", "date", "notes": [...],
                             "platforms": {"windows": {"file", "size", "sha256"}, "mac": null, "linux": null}}
    /dl/manifest.json.sig   Ed25519 signature (Base64) over the bytes of manifest.json
    /dl/<platform>/<file>   the program file

The signature is made with the release key, which is kept offline on the maintainer's PC (never on the server and
never in the repository). The program only knows the public key (PUBLIC_KEY) – whoever takes over the server still cannot slip in a
fake update with it. Without a valid signature or with a wrong checksum nothing is installed.

Download: in chunks (Range), pause/resume, continues after a restart. Fully downloaded -> data/updates/<file>.
Install (Windows, a single .exe): the running exe is renamed (BentCorner.old.exe – Windows allows that), the
new one is put in its place and restarted; the old one is deleted on the next start.
"""
import base64
import hashlib
import json
import logging
import os
import pathlib
import sys
import threading
import time

import version
from system import contacts
from system.i18n import tr

log = logging.getLogger("booster")

BASE_URL = contacts.SERVER + "/dl"   # old address as a fallback: netpolite (signature check unchanged)
PUBLIC_KEY = "vRwXq29AvUSAElFBfz1pTe7x+kaJiS2zoKi4IWIg6tk="
CHUNK = 2 * 1024 * 1024
CHECK_EVERY = 6 * 3600


def platform_key():
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


def _ver(s):
    out = []
    for p in str(s).split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out + [0] * (3 - len(out)))


def newer(a, b):
    """Is version a newer than b?"""
    return _ver(a) > _ver(b)


def verify(raw, sig_b64, public_key=None):
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey
    try:
        VerifyKey(base64.b64decode(public_key or PUBLIC_KEY)).verify(raw, base64.b64decode(sig_b64.strip()))
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False


class UpdateError(Exception):
    pass


def _first_today():
    """First update check today? (marker in the update folder) – the server counts only these, without IP and ID:
    that shows how many installations per version run each day."""
    day = time.strftime("%Y-%m-%d")
    try:
        f = folder() / "last_check_day.txt"
        if f.exists() and f.read_text().strip() == day:
            return False
        f.write_text(day)
    except OSError:
        pass
    return True


def fetch_manifest(base=BASE_URL):
    """Fetch the manifest and verify its signature. -> dict"""
    from net import netpolite
    try:
        r = netpolite.get(f"{base}/manifest.json", params={"v": version.VERSION, "first": int(_first_today())},
                          timeout=20)
        s = netpolite.get(f"{base}/manifest.json.sig", timeout=20)
    except Exception as e:  # noqa: BLE001
        raise UpdateError(tr(f"Server unreachable ({e.__class__.__name__})")) from None
    if r.status_code != 200 or s.status_code != 200:
        raise UpdateError(tr(f"No update directory ({r.status_code})"))
    if not verify(r.content, s.text):
        raise UpdateError(tr("Invalid update signature – not used"))
    try:
        return json.loads(r.content.decode("utf-8"))
    except ValueError:
        raise UpdateError(tr("Manifest unreadable")) from None


def folder():
    from scanner import common
    d = common.DATA / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Updater:
    """State for the UI: state = "idle" | "checking" | "none" | "available" | "downloading" | "paused" |
    "ready" | "error"; progress 0…1; info (version, notes)."""

    def __init__(self, on_change=None, base=BASE_URL, news=lambda: True):
        self.base = base
        self.news = news   # -> False: "Messages from the team" switched off – then no request for news either
        self.state, self.progress, self.error = "idle", 0.0, ""
        self.manifest, self.entry = None, None
        self.on_change = on_change or (lambda: None)
        self._pause = threading.Event()
        self._thread = None

    def _set(self, state, **kw):
        self.state = state
        for k, v in kw.items():
            setattr(self, k, v)
        try:
            self.on_change()
        except Exception:  # noqa: BLE001
            pass

    @property
    def latest(self):
        return (self.manifest or {}).get("latest") or ""

    @property
    def notes(self):
        return (self.manifest or {}).get("notes") or []

    def target(self):
        return folder() / self.entry["file"] if self.entry else None

    # ---------- check ----------
    def check(self, auto_download=True):
        def work():
            self._set("checking")
            try:
                m = fetch_manifest(self.base)
            except UpdateError as e:
                self._set("error", error=str(e))
                return
            e = (m.get("platforms") or {}).get(platform_key())
            if self.base.endswith("/dl") and self.news():   # news from the team lives in the mailbox next door
                from net import teamnews
                m["news"] = list(m.get("news") or []) + teamnews.fetch_news(self.base[:-3])
            self.manifest = m
            if not e or not newer(m.get("latest"), version.VERSION):
                self._set("none", entry=None)
                return
            self.entry = e
            t = self.target()
            if t.exists() and self._sha_ok(t):
                self._set("ready", progress=1.0)
                return
            self._set("available", progress=0.0)
            if auto_download:
                self._download()
        threading.Thread(target=work, daemon=True).start()

    # ---------- download ----------
    def download(self):
        if self.state in ("available", "paused", "error") and self.entry:
            self._pause.clear()
            threading.Thread(target=self._download, daemon=True).start()

    def pause(self):
        if self.state == "downloading":
            self._pause.set()

    def _download(self):
        from net import netpolite
        e = self.entry
        t = self.target()
        part = t.with_name(t.name + ".part")
        size = int(e.get("size") or 0)
        self._pause.clear()
        try:
            while True:
                have = part.stat().st_size if part.exists() else 0
                if size and have >= size:
                    break
                self._set("downloading", progress=(have / size) if size else 0.0)
                if self._pause.is_set():
                    self._set("paused")
                    return
                end = have + CHUNK - 1 if not size else min(size - 1, have + CHUNK - 1)
                r = netpolite.get(f"{self.base}/{platform_key()}/{e['file']}", timeout=60,
                                  headers={"Range": f"bytes={have}-{end}"})
                if r.status_code == 200 and have:   # server cannot do chunks: start over
                    part.unlink(missing_ok=True)
                    continue
                if r.status_code not in (200, 206):
                    raise UpdateError(tr(f"Download error {r.status_code}"))
                with open(part, "ab") as f:
                    f.write(r.content)
                if not r.content or (r.status_code == 200):
                    break
            if not self._sha_ok(part):
                part.unlink(missing_ok=True)
                raise UpdateError(tr("Checksum mismatch – download discarded"))
            os.replace(part, t)
            self._set("ready", progress=1.0)
            log.info("Update %s downloaded: %s", self.latest, t)
        except UpdateError as err:
            self._set("error", error=str(err))
        except Exception as err:  # noqa: BLE001
            log.exception("Update download")
            self._set("error", error=f"{err.__class__.__name__}")

    def _sha_ok(self, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest() == (self.entry or {}).get("sha256")

    # ---------- install ----------
    def can_install(self):
        return self.state == "ready" and getattr(sys, "frozen", False) and platform_key() == "windows"

    def install(self):
        """Put the new exe in place of the running one. -> path of the new exe (restart afterwards)."""
        if not self.can_install():
            raise UpdateError(tr("Installing only works in the finished Windows exe"))
        new = self.target()
        if not self._sha_ok(new):
            raise UpdateError(tr("Checksum mismatch"))
        from system import datahome
        exe = datahome.EXE   # the launcher (i.e. the exe you start) – not the unpacked program
        old = exe.with_name(exe.stem + ".old" + exe.suffix)
        if old.exists():
            old.unlink()
        os.replace(exe, old)          # rename the running exe (allowed on Windows)
        try:
            import shutil
            shutil.copy2(new, exe)
        except OSError:
            os.replace(old, exe)       # roll back if copying fails
            raise
        new.unlink(missing_ok=True)
        return exe


def cleanup_old():
    """At startup: clean up the old exe from the last update."""
    if not getattr(sys, "frozen", False):
        return
    from system import datahome
    exe = datahome.EXE
    old = exe.with_name(exe.stem + ".old" + exe.suffix)
    for _ in range(3):
        try:
            old.unlink(missing_ok=True)
            return
        except OSError:
            time.sleep(0.5)
