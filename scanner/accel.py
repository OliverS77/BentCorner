"""Which accelerator may the AI (fingerprint network, text recognition) use? CPU is the base everywhere; on top of it
only what the system itself brings – we ship no proprietary GPU libraries (signing/open source, 0.9.7.4):

  Windows  DirectML from Windows itself (System32\\DirectML.dll) – the copy onnxruntime-directml brings along is
           left out of the exe (build.ps1 checks it). Only from version MIN_DML up (see there).
  macOS    CoreML (built into the normal onnxruntime wheel) – untested, no Mac yet; fingerprint still measures
           GPU against CPU and takes the faster one.
  else     CPU.

Text recognition (RapidOCR) can only use DirectML; with anything else it runs on the CPU.
Whether the GPU is really used is decided by fingerprint (measured once, remembered in ai-device.json, also
"GPU crashed earlier" – that mark is tied to key(), so it goes away with an app update or another DirectML).
"""
import ctypes
import logging
import os
import pathlib
import sys

log = logging.getLogger("booster")

DML = "DmlExecutionProvider"
COREML = "CoreMLExecutionProvider"

# Oldest DirectML that onnxruntime 1.24.4 runs our models with. Determined 2026-10-31 on the bench (RTX PC): a copy
# of onnxruntime-directml 1.24.4 with the official DirectML builds from NuGet (Microsoft.AI.DirectML) in place of the
# bundled one, each in its own process, fp16 fingerprint network batch 6 + OCR (RapidOCR on DirectML):
#   1.8.2 · 1.10.1 · 1.12.1 · 1.13.1   fingerprint fails (LayerNormalization)
#   1.14.2                             fingerprint ok, OCR fails (Resize)
#   1.15.0 · 1.15.2 · 1.15.4 (bundled until 0.9.7.3) · 1.15.6 (Windows 11 26200)   all ok, same speed
# They failed with an error here, but an older DirectML can also lack functions onnxruntime loads "delay-loaded" –
# that ends the whole process without a Python exception. So the version is read from the file beforehand.
MIN_DML = (1, 15, 0)

_cache = {}


def _file_version(path):
    """Windows file version (a, b, c) of a DLL, or None."""
    try:
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(str(path), 0, size, buf):
            return None
        ptr, n = ctypes.c_void_p(), ctypes.c_uint()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(n)):
            return None
        info = (ctypes.c_uint32 * 13).from_address(ptr.value)   # VS_FIXEDFILEINFO: [2] = MS, [3] = LS
        return info[2] >> 16, info[2] & 0xFFFF, info[3] >> 16
    except (OSError, AttributeError, ValueError):
        return None


def dml_path():
    """The DirectML.dll onnxruntime will load: a copy next to onnxruntime (only during development – the venv
    package brings one along), otherwise the one from Windows."""
    try:
        import onnxruntime
        own = pathlib.Path(onnxruntime.__file__).parent / "capi" / "DirectML.dll"
        if own.exists():
            return own
    except ImportError:
        pass
    return pathlib.Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "DirectML.dll"


def dml_version():
    if "dml" not in _cache:
        p = dml_path()
        _cache["dml"] = _file_version(p) if p.exists() else None
    return _cache["dml"]


def _vstr(v):
    return ".".join(map(str, v)) if v else "none"


def gpu():
    """-> (provider name, why not) – provider None = CPU only. Logs the reason once."""
    if os.environ.get("BENTCORNER_NO_GPU"):   # not cached: the scan bench switches it within one run
        return None, "BENTCORNER_NO_GPU"
    if "gpu" in _cache:
        return _cache["gpu"]
    prov, why = None, ""
    try:
        import onnxruntime as ort
        avail = ort.get_available_providers()
    except Exception as e:  # noqa: BLE001
        avail, why = [], f"onnxruntime: {e}"
    if sys.platform == "win32" and DML in avail:
        v = dml_version()
        if v is None:
            why = "no DirectML in Windows"
        elif v < MIN_DML:
            why = f"DirectML {_vstr(v)} < {_vstr(MIN_DML)}"
        else:
            prov = DML
    elif sys.platform == "darwin" and COREML in avail:
        prov = COREML
    elif not why:
        why = "no GPU accelerator on this system"
    if prov is None:
        log.info("AI on CPU: %s", why)
    _cache["gpu"] = prov, why
    return prov, why


def provider():
    return gpu()[0]


def ocr_gpu():
    """Text recognition on the GPU? Only via DirectML (RapidOCR knows nothing else)."""
    return provider() == DML


def provider_entry(device):
    """onnxruntime providers entry for the GPU session."""
    p = provider()
    if p == DML:
        return (DML, {"device_id": device})
    return (p, {})


def max_devices():
    """How many GPU devices are tried when measuring (DirectML: one per graphics card; CoreML: one)."""
    return 4 if provider() == DML else 1


def key():
    """Part of the remembered choice in ai-device.json: another accelerator/DirectML -> measure again."""
    p = provider()
    return f"{p or 'cpu'}{'-' + _vstr(dml_version()) if p == DML else ''}"
