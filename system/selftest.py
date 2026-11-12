"""SCAN° self-test for the Windows 10 test stick (docs/WIN10-TEST.md): test frames on the GPU and on the CPU – no window,
no tray, no single-instance lock, no network, only the data folder the stick script passes.

    BentCorner.exe --selftest-scan=<report.json> --selftest-data=<folder> [--selftest-phase=cpu]

<folder> holds data/packs/pokemon/ (the data pack) and data/fp_build/scan-bench/pokemon/ (the bench images); system/
datahome.py takes exactly that folder in this mode. The report is rewritten after every step, so a crash leaves what
was done so far and the step it died in ("phase"). Steps:
  env        version, DirectML (scanner/accel.py) and the reason when the GPU is not used
  devices    fingerprint model timed on the CPU and forced on each GPU (like the app's one-time measurement), text
             recognition on a test line on the GPU (if DirectML is usable) and on the CPU
  scan_auto  the scan bench (tools/scan-bench: 30 Pokémon cards × 8 kinds of trouble, without reference images – so
             fingerprint and collector line, the two parts that run on the GPU) on the device the app picks itself
  fallback   the app's reaction to a GPU crash (fingerprint.gpu_crashed): CPU from then on, marked in ai-device.json
  scan_cpu   the scan bench on the CPU (BENTCORNER_NO_GPU, like a PC without a usable GPU)
--selftest-phase=cpu: only env and scan_cpu, all on the CPU – the stick's second run after a real crash on the GPU.
Exit 0 = report complete (it says ok or problem), 3 = scan bench not in this build, 4 = data missing.
The scan bench is private (tools/public/manifest.txt): builds from the public export report "not in this build".
"""
import json
import os
import pathlib
import sys
import time
import traceback

_blocked = []


def _block_network():
    """Every connection attempt fails (and is counted) – updater, mailbox, prices, team news: nothing gets out."""
    import socket

    def refuse(*a, **k):
        _blocked.append(str(a[1] if len(a) > 1 else a[0] if a else "")[:80])
        raise OSError("network is off in --selftest-scan")
    socket.socket.connect = refuse
    socket.socket.connect_ex = refuse
    socket.create_connection = refuse
    socket.getaddrinfo = refuse
    for k in ("HTTPS_PROXY", "HTTP_PROXY"):
        os.environ[k] = "http://127.0.0.1:9"
    os.environ["NO_PROXY"] = ""


def _arg(name, default=""):
    return next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")), default)


def _mask(text):
    home = os.environ.get("USERPROFILE") or str(pathlib.Path.home())
    return str(text).replace(home, "<user>") if home else str(text)


class Report:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.data = {"phase": "start", "done": False, "t0": time.strftime("%Y-%m-%d %H:%M:%S")}

    def step(self, phase):
        self.data["phase"] = phase
        self.write()

    def put(self, key, value):
        self.data[key] = value
        self.write()

    def write(self):
        self.data["network_attempts_blocked"] = len(_blocked)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(_mask(json.dumps(self.data, indent=1, ensure_ascii=False)), "utf-8")
        os.replace(tmp, self.path)


def _bench():
    """The scan bench modules: built into the exe (private build), from tools/scan-bench during development."""
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "scan-bench"))
    import bench   # noqa: F401 – private module
    if getattr(sys, "frozen", False):
        bench.HERE = pathlib.Path(sys._MEIPASS) / "scan-bench"   # cards.json, expected.json
    return bench


def _env():
    import platform
    import version
    from scanner import accel
    prov, why = accel.gpu()
    return {"app": version.VERSION, "exe": pathlib.Path(sys.executable).parent.name if getattr(sys, "frozen", False)
            else "source", "python": platform.python_version(), "directml": accel._vstr(accel.dml_version()),
            "directml_min": accel._vstr(accel.MIN_DML), "gpu_provider": prov, "gpu_not_used_because": why or None}


def _devices():
    """Fingerprint model on the CPU and forced on each GPU, text recognition on GPU (if usable) and CPU – ms each."""
    import cv2
    import numpy as np
    from scanner import accel, fingerprint
    out = {"fingerprint": {}, "ocr": {}}
    out["fingerprint"]["cpu_ms"] = round(1000 * fingerprint._timed(fingerprint._cpu_session(), 6), 1)
    if accel.provider():   # every device the app may measure (DirectML: one per graphics card) – errors per device
        for dev in range(accel.max_devices()):
            try:
                g = fingerprint._gpu_session(dev, 6)
                out["fingerprint"][f"gpu{dev}_ms"] = round(1000 * fingerprint._timed(g, 6), 1)
                del g
            except Exception as e:  # noqa: BLE001 – no such device / driver acting up
                out["fingerprint"][f"gpu{dev}_error"] = f"{type(e).__name__}: {e}"[:300]
    img = np.full((120, 600, 3), 255, np.uint8)
    cv2.putText(img, "SV01 EN 123/198", (12, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)
    from rapidocr_onnxruntime import RapidOCR
    kinds = (("gpu", True), ("cpu", False)) if accel.ocr_gpu() else (("cpu", False),)
    for name, dml in kinds:
        try:
            eng = RapidOCR(det_limit_type="max", det_limit_side_len=720, det_use_dml=dml, rec_use_dml=dml, cls_use_dml=dml)
            eng(img, use_cls=False)   # warm up
            t = time.perf_counter()
            for _ in range(3):
                res = eng(img, use_cls=False)[0]
            out["ocr"][f"{name}_ms"] = round(1000 * (time.perf_counter() - t) / 3, 1)
            out["ocr"][f"{name}_text"] = " ".join(r[1] for r in res or [])[:60]
            del eng
        except Exception as e:  # noqa: BLE001
            out["ocr"][f"{name}_error"] = f"{type(e).__name__}: {e}"[:300]
    return out


def _scan(bench, cpu):
    bench._use_cpu(cpu)
    from scanner import fingerprint, ocrscan
    with ocrscan._lock:   # text recognition follows the device again (a new engine for this run)
        ocrscan._engine, ocrscan._gpu[0] = None, False
    ocrscan._gpu_known[:] = [False] if cpu else []
    t = time.perf_counter()
    stats = bench.run("pokemon", norefs=True, quiet=True, cpu=cpu)
    stats["seconds"] = round(time.perf_counter() - t, 1)
    stats["device"] = fingerprint.backend
    stats["ocr_on_gpu"] = bool(ocrscan._gpu[0])
    stats["reference_this_project"] = _reference(bench, str(stats["device"]).startswith("CPU"))
    return stats


REF_CPU = "_selftest:pokemon:norefs-cpu"   # in expected.json; "_": not one of the bench's own runs ("all" skips it)


def _reference(bench, cpu):
    """The same run on the project's PC, on the same kind of device: a CPU run is compared with a CPU run (real CPU,
    BENTCORNER_NO_GPU from the start), a GPU run with the GPU one – never a CPU stick with the developer's GPU."""
    expected = json.loads((bench.HERE / "expected.json").read_text("utf-8"))
    want = expected.get(REF_CPU if cpu else "pokemon:norefs") or {}
    ref = {k: want.get(k) for k in ("quick", "text", "none", "ask", "false", "ms", "ms_first", "ms_sleep", "by")}
    ref["device"] = "CPU" if cpu else "GPU"
    if want.get("_measured"):
        ref["measured"] = want["_measured"]
    return ref


def _fallback():
    """What the app does when the AI process dies on the GPU: CPU from then on, in fingerprint and text recognition,
    marked in ai-device.json – and the next fingerprint runs on the CPU."""
    import numpy as np
    from scanner import fingerprint, ocrscan
    if not str(fingerprint.backend).startswith("GPU"):
        return {"checked": False, "why": f"the app already uses the CPU ({fingerprint.backend})"}
    fingerprint.gpu_crashed("selftest: simulated")
    choice = json.loads(fingerprint.CHOICE_FILE.read_text("utf-8"))
    vec = fingerprint.embed([np.full((300, 220, 3), 128, np.uint8)])
    return {"checked": True, "device_after": fingerprint.backend, "ocr_gpu_after": bool(ocrscan._gpu[0]),
            "marked_crash": bool(choice.get("crash")), "device_in_choice_file": choice.get("device"),
            "fingerprint_after_ok": vec is not None and len(vec) == 1,
            "ok": fingerprint.backend == "CPU" and not ocrscan._gpu[0] and bool(choice.get("crash"))}


def main():
    # all AI work in this process: the app's AI process would be started without these switches (data folder!) –
    # a real crash on the GPU ends this run, and the stick script then runs --selftest-phase=cpu
    os.environ["BENTCORNER_AI_INPROC"] = "1"
    _block_network()
    rep = Report(_arg("selftest-scan"))
    phase = _arg("selftest-phase", "all")
    if phase == "cpu":
        os.environ["BENTCORNER_NO_GPU"] = "1"
    import logging
    from system import datahome
    logging.basicConfig(filename=str(datahome.HOME / "selftest.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    code = 0
    try:
        rep.put("mode", phase)
        rep.step("env")
        rep.put("env", _env())
        from scanner.common import DATA
        if not (DATA / "fp_build" / "scan-bench" / "pokemon").is_dir() or not (DATA / "packs" / "pokemon").is_dir():
            rep.put("error", "test data missing (data/packs/pokemon, data/fp_build/scan-bench/pokemon)")
            return 4
        try:
            bench = _bench()
        except ImportError:
            rep.put("error", "scan bench not in this build (private tools/scan-bench)")
            return 3
        import benchlib
        benchlib.use_game("pokemon")
        if phase != "cpu":
            rep.step("devices")
            rep.put("devices", _devices())
            rep.step("scan_auto")
            rep.put("scan_auto", _scan(bench, cpu=False))
            rep.step("fallback")
            rep.put("fallback", _fallback())
        rep.step("scan_cpu")
        rep.put("scan_cpu", _scan(bench, cpu=True))
        runs = [rep.data[k] for k in ("scan_auto", "scan_cpu") if k in rep.data]
        fb = rep.data.get("fallback") or {}
        problems = [f"{k}: {rep.data[k]['false']} false" for k in ("scan_auto", "scan_cpu") if rep.data.get(k, {}).get("false")]
        problems += [f"{k}: only {rep.data[k]['quick'] + rep.data[k]['text']} of 240 read" for k in ("scan_auto", "scan_cpu")
                     if k in rep.data and rep.data[k]["quick"] + rep.data[k]["text"] < 120]
        if fb.get("checked") and not fb.get("ok"):
            problems.append("GPU fallback did not switch to the CPU")
        if _blocked:
            problems.append(f"{len(_blocked)} network attempts (blocked)")
        rep.put("problems", problems)
        rep.put("ok", not problems and bool(runs))
    except SystemExit as e:   # benchlib stops like that when the card database or index is missing
        rep.put("error", f"stopped: {e}")
        code = 4
    except Exception:  # noqa: BLE001 – into the report, not a window
        rep.put("error", traceback.format_exc()[-3000:])
        code = 1
    finally:
        rep.data["done"] = True
        # proof for the tests: no window, no tray, no single-instance lock (that lives in ui.tray) was ever loaded
        rep.data["ui_loaded"] = sorted(m for m in ("ui.tray", "PySide6.QtWidgets", "PySide6.QtGui", "PySide6.QtQuick")
                                       if m in sys.modules)
        rep.step("end")
    return code


def run():
    """Entry from app.py: never returns – the AI libraries are not torn down one by one (like the app's hard exit)."""
    code = 1
    try:
        code = main()
        import logging
        logging.shutdown()
    finally:
        os._exit(code)
