"""Phone as camera – only on the local Wi-Fi, without our server: Bent°Corner starts a small https server on the PC,
the phone opens the page (QR code in the scan view or under Settings → Scanning), films with the rear camera and
sends the frames as JPEG straight to the PC. The scan page takes them like a webcam.

- https is mandatory: phone browsers only grant camera access on secure pages. Bent°Corner creates the certificate
  itself (once, in the data folder) – so the phone warns on first opening ("not secure"), then
  "Advanced → open anyway". Nothing leaves the Wi-Fi.
- Access only with the key from the QR code (?k=…), otherwise 403 – neighbours on the same network see nothing.
- Without a live camera (old browser): "Take photo" sends single frames.
- If the Wi-Fi doesn't let devices see each other (client isolation, guest Wi-Fi): phone via cable and "USB tethering"
  – the cable then is a small network of its own between phone and PC, the QR code points to that address (usb_ips()).

    start() -> URL for the phone (or error text), latest() -> (frame, number, time), stop()
"""
import datetime
import ipaddress
import json
import logging
import os
import secrets
import socket
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

log = logging.getLogger("booster")
PORTS = (8765, 8766, 8767, 8780)
_state = {"server": None, "thread": None, "url": "", "frame": None, "seq": 0, "t": 0.0, "status": "",
          "token": "", "status_fn": None, "error": "", "seen": 0.0}
_lock = threading.Lock()


def lan_ips():
    """All IPv4 addresses of this PC that fit a home network – most likely first: 192.168.… (Wi-Fi router), then
    172.16–31.… and 10.… (often VPN or virtual adapters such as WSL/Hyper-V); never 169.254.… or 127.…"""
    ips = set()
    try:
        ips |= {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:   # the outbound route (without sending anything)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()

    def rank(ip):
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31:
            return 2
        if ip.startswith("10."):
            return 3
        return 9
    return sorted((ip for ip in ips if not ip.startswith(("127.", "169.254."))), key=rank) or ["127.0.0.1"]


def lan_ip():
    return lan_ips()[0]


USB_ADAPTERS = ("remote ndis", "rndis", "usbncm", "apple mobile device ethernet")


def usb_ips():
    """Addresses of this PC on a phone cable (USB tethering: Android RNDIS/NCM, iPhone "Personal Hotspot") – Windows
    only, from "ipconfig /all" (adapter name + IPv4 per block). Empty if there is no phone network."""
    if sys.platform != "win32":
        return []
    try:
        out = subprocess.run(["ipconfig", "/all"], capture_output=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found, usb = [], False
    for line in out.decode("ascii", "ignore").splitlines():
        if line and not line[0].isspace():   # new adapter block
            usb = False
        low = line.lower()
        if any(a in low for a in USB_ADAPTERS):
            usb = True
        if usb and "ipv4" in low and ":" in line:
            ip = line.split(":", 1)[1].strip().split("(")[0].strip()
            if ip.count(".") == 3 and not ip.startswith(("127.", "169.254.")):
                found.append(ip)
    return found


def _cert(folder, ip):
    """Self-signed certificate (once) -> (cert.pem, key.pem). Stays the same even with a new address (Wi-Fi ↔ cable)
    – the phone warns anyway because it is self-signed; a new one would only mean another warning."""
    folder.mkdir(parents=True, exist_ok=True)
    crt, key = folder / "cert.pem", folder / "key.pem"
    meta = folder / "cert.json"
    if crt.exists() and key.exists():
        return crt, key
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    k = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Bent°Corner auf diesem PC")])
    now = datetime.datetime.now(datetime.timezone.utc)
    san = [x509.DNSName("localhost")]
    try:
        san.append(x509.IPAddress(ipaddress.ip_address(ip)))
    except ValueError:
        pass
    c = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(k.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
         .not_valid_after(now + datetime.timedelta(days=3650))
         .add_extension(x509.SubjectAlternativeName(san), critical=False).sign(k, hashes.SHA256()))
    key.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    crt.write_bytes(c.public_bytes(serialization.Encoding.PEM))
    meta.write_text(json.dumps({"ip": ip}), "utf-8")
    return crt, key


PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bent°Corner – Handy-Kamera</title>
<style>
 :root { color-scheme: dark; }
 body { margin: 0; background: #0e0e0e; color: #ececec; font: 15px system-ui, sans-serif; text-align: center; }
 video { width: 100%; max-height: 70vh; object-fit: contain; background: #000; display: block; }
 .bar { display: flex; gap: 10px; justify-content: center; padding: 12px; flex-wrap: wrap; }
 button, label.btn { background: #1d1d1d; color: #ececec; border: 1px solid #3a3a3a; border-radius: 12px;
   padding: 12px 18px; font-weight: 700; font-size: 15px; }
 #st { color: #9a9a9a; padding: 4px 12px 16px; min-height: 20px; }
 #res { font-weight: 700; font-size: 18px; padding: 6px; min-height: 26px; }
 input[type=file] { display: none; }
</style></head><body>
<video id="v" playsinline muted autoplay></video>
<div id="res"></div>
<div class="bar">
 <button id="go">Kamera starten</button>
 <button id="torch" style="display:none">Licht</button>
 <label class="btn" id="photo">Foto aufnehmen<input id="file" type="file" accept="image/*" capture="environment"></label>
</div>
<div id="st">Halte die Karte ruhig vor die Kamera – Bent°Corner auf dem PC erkennt sie.</div>
<script>
const K = new URLSearchParams(location.search).get("k") || "";
const v = document.getElementById("v"), st = document.getElementById("st"), res = document.getElementById("res");
const c = document.createElement("canvas");
let track = null, running = false, torchOn = false, lock = null;
async function send(blob) {
  const r = await fetch("/frame?k=" + encodeURIComponent(K), { method: "POST", body: blob,
                                                               headers: { "Content-Type": "image/jpeg" } });
  if (r.ok) { const j = await r.json(); res.textContent = j.status || ""; }
  else st.textContent = "PC antwortet nicht (" + r.status + ") – QR-Code neu scannen.";
}
async function loop() {
  while (running) {
    if (v.videoWidth) {
      const w = Math.min(1280, v.videoWidth), h = Math.round(w * v.videoHeight / v.videoWidth);
      c.width = w; c.height = h; c.getContext("2d").drawImage(v, 0, 0, w, h);
      const blob = await new Promise(ok => c.toBlob(ok, "image/jpeg", 0.8));
      try { await send(blob); } catch (e) { st.textContent = "Verbindung weg – im selben WLAN?"; await new Promise(r => setTimeout(r, 1000)); }
    } else await new Promise(r => setTimeout(r, 100));
  }
}
document.getElementById("go").onclick = async () => {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    st.textContent = "Live-Kamera geht in diesem Browser nicht – nimm „Foto aufnehmen“."; return; }
  try {
    const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" },
                                                                   width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
    v.srcObject = s; track = s.getVideoTracks()[0];
    const caps = track.getCapabilities ? track.getCapabilities() : {};
    if (caps.torch) document.getElementById("torch").style.display = "";
    try { lock = await navigator.wakeLock.request("screen"); } catch (e) {}
    running = true; document.getElementById("go").style.display = "none";
    st.textContent = "Verbunden – Bent°Corner sieht, was du filmst."; loop();
  } catch (e) { st.textContent = "Kamera nicht freigegeben: " + e.message; }
};
document.getElementById("torch").onclick = async () => {
  torchOn = !torchOn; try { await track.applyConstraints({ advanced: [{ torch: torchOn }] }); } catch (e) {} };
document.getElementById("file").onchange = async (e) => {
  const f = e.target.files[0]; if (!f) return; st.textContent = "Foto wird geschickt …";
  try { await send(f); st.textContent = "Foto angekommen."; } catch (er) { st.textContent = "Nicht angekommen – im selben WLAN?"; }
};
</script></body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "BentCorner"

    def log_message(self, *a):   # no access log
        pass

    def _ok_key(self):
        q = parse_qs(urlparse(self.path).query)
        return secrets.compare_digest((q.get("k") or [""])[0], _state["token"] or "-")

    def do_GET(self):
        if urlparse(self.path).path not in ("/", "/index.html") or not self._ok_key():
            self.send_error(403)
            return
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlparse(self.path).path != "/frame" or not self._ok_key():
            self.send_error(403)
            return
        n = int(self.headers.get("Content-Length") or 0)
        if not 0 < n < 15_000_000:
            self.send_error(413)
            return
        data = self.rfile.read(n)
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            with _lock:
                _state["frame"], _state["seq"], _state["t"] = img, _state["seq"] + 1, time.time()
        fn = _state.get("status_fn")
        status = ""
        try:
            status = fn() if fn else ""
        except Exception:  # noqa: BLE001
            status = ""
        body = json.dumps({"ok": img is not None, "status": status}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False   # Windows: otherwise a second app could share the same port
    daemon_threads = True
    ctx = None

    def get_request(self):
        """Accept without encryption, then do the TLS handshake in its own thread – so an aborted handshake (e.g. the
        phone first shows the certificate warning) doesn't hang the whole server. Every attempt briefly lands in the
        log (only time and device on the home network) – for troubleshooting."""
        sock, addr = self.socket.accept()
        _state["seen"] = time.time()
        log.info("Phone camera: connection from %s", addr[0])
        return sock, addr

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(20)
            request = self.ctx.wrap_socket(request, server_side=True)
        except Exception as e:  # noqa: BLE001
            log.info("Phone camera: handshake with %s aborted: %s", client_address[0], e)
            try:
                request.close()
            except OSError:
                pass
            return
        super().process_request_thread(request, client_address)


def start(data_dir, token, status_fn=None):
    """Start the server (unless already running) -> URL for the phone or "" (then error() holds the reason)."""
    with _lock:
        if _state["server"] is not None:
            _state["status_fn"] = status_fn or _state["status_fn"]
            return _state["url"]
    ip = (usb_ips() or [lan_ip()])[0]   # phone on the cable (tethering) takes precedence
    try:
        crt, key = _cert(data_dir / "phonecam", ip)
    except Exception as e:  # noqa: BLE001
        log.exception("Phone camera: certificate")
        _state["error"] = str(e)
        return ""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(crt), str(key))
    srv = None
    for port in PORTS:
        try:
            srv = _Server(("0.0.0.0", port), _Handler)
            break
        except OSError:
            continue
    if srv is None:
        _state["error"] = "Kein freier Port"
        return ""
    srv.daemon_threads = True
    srv.ctx = ctx   # handshake per connection in its own thread (get_request/process_request_thread)
    th = threading.Thread(target=srv.serve_forever, name="handy-kamera", daemon=True)
    th.start()
    url = f"https://{ip}:{srv.server_address[1]}/?k={token}"
    with _lock:
        _state.update(server=srv, thread=th, url=url, token=token, status_fn=status_fn, error="")
    log.info("Phone camera: %s", url.split("?")[0])
    return url


def stop():
    with _lock:
        srv = _state["server"]
        _state.update(server=None, thread=None, url="", frame=None)
    if srv is not None:
        threading.Thread(target=srv.shutdown, daemon=True).start()


def host():
    return urlparse(_state["url"]).hostname or ""


def set_host(ip):
    """Switch the QR address (Wi-Fi ↔ cable) – the server listens on all networks anyway."""
    with _lock:
        u = urlparse(_state["url"])
        if u.hostname and u.hostname != ip:
            _state["url"] = u._replace(netloc=f"{ip}:{u.port}").geturl()
            log.info("Phone camera: now %s", _state["url"].split("?")[0])
        return _state["url"]


def running():
    return _state["server"] is not None


def url():
    return _state["url"]


def error():
    return _state["error"]


def seen():
    """Time of the last connection attempt (0 = never) – does the phone get through at all?"""
    return _state["seen"]


def latest():
    """-> (frame or None, number, time of the frame)."""
    with _lock:
        return _state["frame"], _state["seq"], _state["t"]


def new_token():
    return secrets.token_urlsafe(9)


REVEAL_S = 60   # how long the QR code stays sharp after a click


def blurred(img):
    """Blurred version (for "click to show") – smeared so heavily that nobody can read it over your shoulder."""
    from PySide6 import QtCore, QtGui
    small = img.scaled(max(6, img.width() // 14), max(6, img.height() // 14), QtCore.Qt.IgnoreAspectRatio,
                       QtCore.Qt.SmoothTransformation)
    out = small.scaled(img.width(), img.height(), QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
    return out.convertToFormat(QtGui.QImage.Format_RGB32)


def qr_image(text, scale=6):
    """QR code as a QImage (black on white, with border)."""
    import segno
    from PySide6 import QtGui
    q = segno.make(text, error="m")
    rows = list(q.matrix_iter(scale=1, border=2))
    n = len(rows)
    img = QtGui.QImage(n * scale, n * scale, QtGui.QImage.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QtGui.QPainter(img)
    for y, row in enumerate(rows):
        for x, on in enumerate(row):
            if on:
                p.fillRect(x * scale, y * scale, scale, scale, QtGui.QColor(0, 0, 0))
    p.end()
    return img
