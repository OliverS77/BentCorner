"""What is inside the computer? – read locally only, none of it leaves the PC.

Reads what Windows shows every program without administrator rights (registry, system calls): processor,
number of threads, RAM, graphics cards (name, video memory), screen, operating system. No
serial numbers, no identifiers. From this, perf.py suggests the matching animation level.
"""
import os
import platform
import subprocess
import sys

_cache = None


def _win_cpu():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
    except OSError:
        return platform.processor()


def _win_ram_gb():
    import ctypes

    class MEMSTAT(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MEMSTAT()
    st.dwLength = ctypes.sizeof(MEMSTAT)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return round(st.ullTotalPhys / 1024 ** 3)
    return 0


def _win_gpus():
    """Graphics cards from the driver registry: [(name, video memory GB)] – virtual adapters without memory are
    dropped."""
    import winreg
    out = []
    base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return out
    with root:
        for i in range(64):
            try:
                sub = winreg.EnumKey(root, i)
            except OSError:
                break
            if not sub.isdigit():
                continue
            try:
                with winreg.OpenKey(root, sub) as k:
                    name = str(winreg.QueryValueEx(k, "DriverDesc")[0])
                    mem = 0
                    for val in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                        try:
                            raw = winreg.QueryValueEx(k, val)[0]
                            mem = int.from_bytes(raw, "little") if isinstance(raw, (bytes, bytearray)) else int(raw)
                            if mem:
                                break
                        except OSError:
                            continue
            except OSError:
                continue
            if mem:
                out.append((name, round(mem / 1024 ** 3, 1)))
    return out


def hardware_gpu():
    """Is there a real graphics adapter (Direct3D)? False if Windows only offers the "Microsoft Basic Render Driver"
    (no driver installed, some VMs/remote sessions) – then rendering would otherwise fall back to the processor
    (WARP, 3–4 cores fully loaded). None = unknown (not Windows, DXGI cannot be queried)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    class DESC1(ctypes.Structure):
        _fields_ = [("Description", ctypes.c_wchar * 128), ("VendorId", wintypes.UINT), ("DeviceId", wintypes.UINT),
                    ("SubSysId", wintypes.UINT), ("Revision", wintypes.UINT), ("DedicatedVideoMemory", ctypes.c_size_t),
                    ("DedicatedSystemMemory", ctypes.c_size_t), ("SharedSystemMemory", ctypes.c_size_t),
                    ("LuidLow", wintypes.DWORD), ("LuidHigh", wintypes.LONG), ("Flags", wintypes.UINT)]

    def call(obj, index, restype, argtypes=(), *args):   # COM: method number index of the interface
        vt = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vt[index])
        return fn(obj, *args)
    try:
        iid = GUID(0x770aae78, 0xf26f, 0x4dba, (ctypes.c_ubyte * 8)(0xa8, 0x29, 0x25, 0x3c, 0x83, 0xd1, 0xb3, 0x87))
        factory = ctypes.c_void_p()
        if ctypes.windll.dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)) != 0:
            return None
        try:
            found, i = False, 0
            while i < 16:
                ad = ctypes.c_void_p()
                if call(factory, 12, ctypes.c_long, (wintypes.UINT, ctypes.c_void_p), i,
                        ctypes.byref(ad)) != 0:   # EnumAdapters1
                    break
                d = DESC1()
                call(ad, 10, ctypes.c_long, (ctypes.c_void_p,), ctypes.byref(d))   # GetDesc1
                call(ad, 2, wintypes.ULONG)                     # Release
                if not d.Flags & 2:   # DXGI_ADAPTER_FLAG_SOFTWARE
                    found = True
                    break
                i += 1
            return found
        finally:
            call(factory, 2, wintypes.ULONG)
    except Exception:  # noqa: BLE001 – just an extra
        return None


def _mac_info():
    def sysctl(key):
        try:
            return subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, timeout=2).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    cpu = sysctl("machdep.cpu.brand_string") or platform.processor()
    try:
        ram = round(int(sysctl("hw.memsize") or 0) / 1024 ** 3)
    except ValueError:
        ram = 0
    gpus = [(cpu + " GPU", 0.0)] if "Apple" in cpu else []
    return cpu, ram, gpus


def read(screen=None):
    """-> {"cpu", "threads", "ram_gb", "gpus": [(name, GB)], "dedicated", "os", "screen"} (cached)."""
    global _cache
    if _cache is not None and screen is None:
        return _cache
    try:
        if sys.platform == "win32":
            cpu, ram, gpus = _win_cpu(), _win_ram_gb(), _win_gpus()
        elif sys.platform == "darwin":
            cpu, ram, gpus = _mac_info()
        else:
            cpu, ram, gpus = platform.processor(), 0, []
    except Exception:  # noqa: BLE001 – reading is an extra, never a reason to fail
        cpu, ram, gpus = platform.processor(), 0, []
    dedicated = any(gb >= 3 or any(k in n.upper() for k in ("NVIDIA", "GEFORCE", "RTX", "GTX", "RADEON RX", "ARC A"))
                    for n, gb in gpus if "MICROSOFT BASIC" not in n.upper())
    if "Apple" in cpu:
        dedicated = True  # Apple chips: strong built-in graphics
    info = {"cpu": cpu, "threads": os.cpu_count() or 1, "ram_gb": ram, "gpus": gpus, "dedicated": dedicated,
            "os": platform.platform(terse=True), "screen": screen or ""}
    _cache = info
    return info


def summary(info):
    """Short text for Settings (and for the testers' performance report)."""
    gpu = ", ".join(f"{n} ({gb:g} GB)" if gb else n for n, gb in info["gpus"]) or "–"
    return (f"{info['cpu']} · {info['threads']} Threads · {info['ram_gb']} GB RAM · {gpu}"
            + (f" · {info['screen']}" if info.get("screen") else ""))
