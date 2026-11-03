"""AI in its own process: the fingerprint network and text recognition (both on the GPU via DirectML) run in a
worker process instead of inside the app.

Why: while creating a DirectML session, onnxruntime holds the Python lock (GIL) – the whole UI freezes for that time
(measured: 0.3 s on 12 cores, up to ~13 s on 2 cores). In a separate process the UI doesn't notice any of it. Side
benefits: if the graphics driver crashes, only the worker process dies (and gets restarted), and when unloading after
idle, ending the process really frees the memory. One process, one queue: AI and text recognition automatically run
one after the other (DirectML doesn't tolerate concurrent runs).

The computation uses the same code (fingerprint, ocrscan) and the same session settings as before – the fingerprints
are bit-identical. If the process doesn't start (virus scanner, broken environment), everything is computed inside
the app as before.

  App:      aiworker.call("embed", …) / call("ocr", …)  – blocks only the calling scan thread
  Process:  app.py --ai-worker  or  python aiworker.py --ai-worker  (no Qt, no windows)
"""
import logging
import os
import secrets
import subprocess
import sys
import threading
import time

log = logging.getLogger("booster")

ARG = "--ai-worker"
# Switch off for comparison/emergencies: BENTCORNER_AI_INPROC=1 -> everything inside the app (as before)
ENABLED = sys.platform == "win32" and not os.environ.get("BENTCORNER_AI_INPROC")
START_TIMEOUT = 60.0   # how long the process may take to connect (first start: the virus scanner checks the exe)
MAX_FAILS = 3          # failed this many times in a row -> compute inside the app for the rest of this run

BELOW_NORMAL = 0x00004000
NORMAL = 0x00000020
NO_WINDOW = 0x08000000


class Unavailable(Exception):
    """Worker process not available (doesn't start, crashed) – the caller computes by itself."""


# ================================================================================================ in the app (client)
_lock = threading.Lock()        # one job after the other (like fingerprint._run_lock used to)
_start_lock = threading.Lock()
_proc = None                    # subprocess.Popen
_conn = None                    # multiprocessing.connection.Connection
_fails = 0
_info = {}                      # reported by the process: {"backend": "GPU (device 0)", "ocr_gpu": True}


def usable():
    """Compute via the worker process? (enabled, not failed too often, not the process itself)"""
    return ENABLED and _fails < MAX_FAILS and not _IN_WORKER[0]


def running():
    return _conn is not None and _proc is not None and _proc.poll() is None


def info():
    return dict(_info)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # project folder (contains scanner/)


def _command():
    if getattr(sys, "frozen", False):
        return [sys.executable, ARG]   # the app exe itself (not the launcher) – app.py branches off at the very top
    return [sys.executable, "-m", "scanner.aiworker", ARG]   # during development: as a module from the project folder


def start():
    """Start the worker process (unless already running) and wait until it is connected. Loads nothing yet – it
    creates the network on its first job or on "warm". -> True if it is running."""
    global _proc, _conn, _fails
    if not usable():
        return False
    with _start_lock:
        if running():
            return True
        _close()
        from multiprocessing.connection import Listener
        address = rf"\\.\pipe\bentcorner-ai-{os.getpid()}-{secrets.token_hex(6)}"
        key = secrets.token_bytes(24)
        env = dict(os.environ, BENTCORNER_AI_PIPE=address, BENTCORNER_AI_KEY=key.hex(),
                   BENTCORNER_AI_PARENT=str(os.getpid()))
        t = time.monotonic()
        try:
            with Listener(address, family="AF_PIPE", authkey=key) as lst:
                # low priority while it creates the network (takes seconds on 2 cores) – the UI keeps the CPU;
                # afterwards it switches itself to normal (fast replies while scanning)
                proc = subprocess.Popen(_command(), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, creationflags=BELOW_NORMAL | NO_WINDOW,
                                        close_fds=True, cwd=None if getattr(sys, "frozen", False) else ROOT)
                conn = _accept(lst, proc)
        except Exception as e:  # noqa: BLE001 – then compute inside the app instead
            _fails += 1
            log.warning("AI process does not start (%s/%s): %s", _fails, MAX_FAILS, e)
            return False
        _proc, _conn = proc, conn   # reset the fail counter only after a successful job (crash loop)
        log.info("AI process started (PID %s, %.1f s)", proc.pid, time.monotonic() - t)
        return True


def _accept(lst, proc):
    """Wait for the connection – without hanging forever if the process dies right away."""
    got = {}

    def accept():
        try:
            got["conn"] = lst.accept()
        except Exception as e:  # noqa: BLE001
            got["err"] = e
    th = threading.Thread(target=accept, daemon=True)
    th.start()
    end = time.monotonic() + START_TIMEOUT
    while th.is_alive() and time.monotonic() < end:
        th.join(0.1)
        if proc.poll() is not None and th.is_alive():
            break
    if "conn" in got:
        return got["conn"]
    proc.kill()
    _poke(lst)   # release the waiting accept()
    raise RuntimeError(got.get("err") or f"no connection (process exit {proc.poll()})")


def _poke(lst):
    try:
        from multiprocessing.connection import Client
        Client(lst.address, family="AF_PIPE", authkey=b"x").close()
    except Exception:  # noqa: BLE001
        pass


def call(op, *args):
    """Job to the worker process -> result. If it crashes meanwhile, restart once and retry; if that fails too:
    Unavailable (the caller then computes by itself). Errors INSIDE the job come back as an exception."""
    global _fails
    for attempt in (0, 1):
        if not start():
            raise Unavailable
        with _lock:
            conn = _conn
            if conn is None:
                continue
            try:
                conn.send((op, args))
                ok, res, meta = conn.recv()
            except (EOFError, OSError, BrokenPipeError) as e:
                log.warning("AI process gone (%s) – %s", e, "restarting" if attempt == 0 else "computing in-process")
                _fails += 1
                _close()
                # died on the GPU (graphics driver, too old/broken DirectML): restart on the CPU – and in-process
                # too, otherwise the app itself would crash the same way (lifted by an app update / new DirectML)
                from scanner import fingerprint
                fingerprint.gpu_crashed(f"AI process gone during '{op}'")
                continue
        _fails = 0
        _info.update(meta or {})
        if not ok:
            raise RuntimeError(res)
        return res
    raise Unavailable


def stop(background=False):
    """End the worker process (unload after idle, app exit). If a job is currently running: don't wait. -> True if
    it is gone. background: waiting for the process to exit happens in a thread (unloading from the UI thread – the
    wait took 250–300 ms there); the process is detached right away, a new start() doesn't wait for it."""
    if not _lock.acquire(blocking=False):
        return False
    try:
        if _conn is not None:
            try:
                _conn.send(("quit", ()))
            except (OSError, EOFError):
                pass
        _close(wait=1.0, background=background)
        _info.clear()
    finally:
        _lock.release()
    return True


def _close(wait=0.0, background=False):
    global _proc, _conn
    conn, proc, _conn, _proc = _conn, _proc, None, None
    if background and (conn is not None or proc is not None):
        threading.Thread(target=_end, args=(conn, proc, wait), name="ai-stop", daemon=True).start()
    else:
        _end(conn, proc, wait)


def _end(conn, proc, wait):
    if conn is not None:
        try:
            conn.close()
        except OSError:
            pass
    if proc is not None:
        try:
            proc.wait(wait)
        except subprocess.TimeoutExpired:
            pass
        if proc.poll() is None:
            proc.kill()


# ============================================================================================= in the worker process
_IN_WORKER = [False]


def _watch_parent(pid):
    """App gone (even after a hard crash) -> the process ends itself, no orphans."""
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    h = k32.OpenProcess(0x00100000, 0, pid)   # SYNCHRONIZE
    if not h:
        os._exit(0)

    def wait():
        k32.WaitForSingleObject(h, 0xFFFFFFFF)
        os._exit(0)
    threading.Thread(target=wait, daemon=True).start()


def _set_priority(cls):
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k32.SetPriorityClass(k32.GetCurrentProcess(), cls)
    except Exception:  # noqa: BLE001
        pass


def serve():
    """Main loop of the worker process: accept jobs, compute, reply – until the app says "quit" or disappears."""
    _IN_WORKER[0] = True
    from multiprocessing.connection import Client
    _watch_parent(int(os.environ["BENTCORNER_AI_PARENT"]))
    conn = Client(os.environ["BENTCORNER_AI_PIPE"], family="AF_PIPE",
                  authkey=bytes.fromhex(os.environ["BENTCORNER_AI_KEY"]))
    from scanner import fingerprint
    from scanner import ocrscan
    warm = False
    while True:
        try:
            op, args = conn.recv()
        except (EOFError, OSError):
            break
        if op == "quit":
            break
        try:
            if op == "embed":
                res = fingerprint.embed_small(*args)
            elif op == "ocr":
                res = ocrscan.run_local(*args)
            elif op == "warm":   # create the network (batch sizes for scanning) and text recognition in advance –
                # 16 (importing sets) only when needed, it costs the most memory
                for b in fingerprint.GPU_BATCHES[:2]:
                    fingerprint.embed_small([fingerprint.blank()] * b, b)
                if args and args[0] and ocrscan.available():
                    ocrscan.run_local(ocrscan.blank())
                res = True
            else:
                raise ValueError(f"unbekannter Auftrag {op}")
            ok = True
        except Exception as e:  # noqa: BLE001 – report the error back, the process keeps running
            ok, res = False, f"{type(e).__name__}: {e}"
        if not warm and fingerprint.loaded():
            warm = True
            _set_priority(NORMAL)   # network is loaded: reply quickly from now on
        try:
            conn.send((ok, res, {"backend": fingerprint.backend, "ocr_gpu": bool(ocrscan._gpu[0])}))
        except (OSError, EOFError):
            break
    os._exit(0)


if __name__ == "__main__" and ARG in sys.argv:
    from scanner import aiworker   # as a module (not __main__): fingerprint/ocrscan then see the same state
    aiworker.serve()
