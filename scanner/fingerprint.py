"""AI fingerprint of card images: a small neural network (DINOv2-small, ONNX, runs on the CPU,
~25 ms per image) turns an image into a vector of 384 numbers. Similar images -> similar vectors.

Index: per downloaded set, the fingerprints of all card images, computed once (data/erkennung/<set>.fp.npz).
When scanning: fingerprint of the camera image, most similar cards via dot product -> candidates, which are then
confirmed by image matching (keypoints).
"""
import hashlib
import logging
import os
import pathlib
import sys
import threading
import time

import cv2

import numpy as np

from scanner.common import BASE, DATA, RECOG

log = logging.getLogger("booster")

MODEL_NAME = "dinov2-small-q.onnx"
SIZE = 224
_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)
_session, _lock = None, threading.Lock()


def model_path():
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1]))
    return base / "models" / MODEL_NAME


GLOBAL_NAME = "fingerprints-all.npz"
CARDBACK = "cardback.npy"   # the normal Magic card back as a fingerprint (Index._drop_card_backs), in the Magic pack


def global_path():
    """Bundled index of all cards (tools/build_fingerprints.py): in the app (models/) or, during development,
    in data/fp_build/ – per game: Magic directly there, others in a subfolder (models/pokemon/ …). None if there
    is none for the active game."""
    import games
    key = games.current().key
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1]))
    sub = pathlib.Path(games.current().subdir)
    from cards import packs   # first the loaded data pack (data/packs/<game>/), then the app or developer folder
    pack = packs.file_of(key, GLOBAL_NAME) if key in packs.PACKS else None
    for p in ([pack] if pack else []) + [base / "models" / sub / GLOBAL_NAME, DATA / "fp_build" / sub / GLOBAL_NAME]:
        if p.exists():
            return p
    return None


def available():
    return model_path().exists()


GPU_MODEL_NAME = "dinov2-small-fp16.onnx"  # the same network unquantized – runs on the GPU (accel: DirectML/CoreML)
backend = "?"  # "GPU (device n)" or "CPU" – for log/status
# DirectML is much faster with a fixed batch size (6 images: ~9 instead of ~39 ms) – hence one session per size,
# smaller batches are padded with blank images. 1 = known position, 6 = search windows, 16 = indexing sets.
GPU_BATCHES = (1, 6, 16)
CHOICE_FILE = DATA / "ai-device.json"  # remembered choice (device), so it isn't measured on every start
# (not in the recognition folder: every .json there is a set)
_device = None  # GPU device or None (CPU)
_gpu = {}       # batch size -> session


def _cpu_session():
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.log_severity_level = 3
    so.intra_op_num_threads = max(2, min(8, (os.cpu_count() or 4) // 2))  # half the cores, at most 8
    so.add_session_config_entry("session.intra_op.allow_spinning", "0")  # threads sleep instead of spinning
    return ort.InferenceSession(str(model_path()), so, providers=["CPUExecutionProvider"])


def _gpu_session(dev, batch):
    import onnxruntime as ort
    go = ort.SessionOptions()
    go.log_severity_level = 3
    go.enable_mem_pattern = False
    go.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    go.add_free_dimension_override_by_name("batch_size", batch)
    from scanner import accel
    entry = accel.provider_entry(dev)
    g = ort.InferenceSession(str(model_path().parent / GPU_MODEL_NAME), go, providers=[entry])
    if entry[0] not in g.get_providers():
        raise RuntimeError(f"no {entry[0]} device")
    return g


def _timed(sess, batch, runs=4):
    x = np.zeros((batch, 3, SIZE, SIZE), np.float32)
    sess.run(None, {"pixel_values": x})  # warm up
    t = time.perf_counter()
    for _ in range(runs):
        sess.run(None, {"pixel_values": x})
    return (time.perf_counter() - t) / runs


def _choice_key():
    """Another app version, onnxruntime, GPU model or accelerator (e.g. DirectML after a Windows update) -> measure
    again; this also lifts a "GPU crashed" mark."""
    import onnxruntime as ort
    import version
    from scanner import accel
    gm = model_path().parent / GPU_MODEL_NAME
    return f"{ort.__version__}|{gm.stat().st_size if gm.exists() else 0}|{accel.key()}|{version.VERSION}"


_crash_logged = [False]


def _load_choice():
    """Remembered device: a number (GPU), None (CPU) or "?" (not measured yet / something changed)."""
    import json
    try:
        d = json.loads(CHOICE_FILE.read_text("utf-8"))
        if d.get("key") != _choice_key():
            return "?"
        if d.get("crash") and not _crash_logged[0]:
            _crash_logged[0] = True
            log.info("AI on CPU: GPU crashed earlier (%s) – again after an app update or another DirectML",
                     d.get("crash"))
        return d["device"]
    except (OSError, ValueError, KeyError):
        return "?"


def _save_choice(dev, crash=None):
    import json
    try:
        CHOICE_FILE.parent.mkdir(parents=True, exist_ok=True)
        d = {"device": dev, "key": _choice_key()}
        if crash:
            d["crash"] = crash
        CHOICE_FILE.write_text(json.dumps(d), "utf-8")
    except OSError:
        pass


def gpu_crashed(why):
    """The AI process died while it was on (or about to use) the GPU: from now on CPU only – in the process and
    here in the app (no retry on the GPU, so no crash loop). Lifted by an app update or another DirectML."""
    global _session, _device, backend
    if _load_choice() is None:
        return   # already on the CPU: the crash had another cause
    log.warning("AI on CPU from now on: GPU crashed (%s)", why)
    _save_choice(None, crash=f"{time.strftime('%Y-%m-%d')} {why}")
    _crash_logged[0] = True
    with _lock:
        _gpu.clear()
        _session, _device, backend = None, None, "CPU"
    from scanner import ocrscan
    ocrscan.gpu_off()


def _choose():
    """Measure the fastest device (6 images, as when scanning): every GPU (accel) against the CPU."""
    from scanner import accel
    cpu = _cpu_session()
    best, best_t = None, _timed(cpu, 6)
    gm = model_path().parent / GPU_MODEL_NAME
    if accel.provider() and gm.exists():
        for dev in range(accel.max_devices()):
            try:
                g = _gpu_session(dev, 6)
                t = _timed(g, 6)
            except Exception:  # noqa: BLE001 – device doesn't exist / driver acting up
                break
            if t < best_t * 0.7:
                best, best_t = dev, t
            del g
    return best, (cpu if best is None else None)


def session(batch=1):
    """Fingerprint model for a batch size. On first use: take the remembered device or measure (once) which is
    fastest – GPU (accel, fixed batch sizes) or the quantized model on the CPU."""
    global _session, _device, backend
    with _lock:
        if _session is None and not _gpu:
            import onnxruntime as ort
            ort.set_default_logger_severity(3)  # only real errors into the log
            from scanner import accel
            dev = None if accel.provider() is None else _load_choice()
            cpu = None
            if dev == "?":
                dev, cpu = _choose()
                _save_choice(dev)
            if dev is not None:
                try:
                    _gpu[batch] = _gpu_session(dev, batch)
                    _device, backend = dev, f"GPU (device {dev})"
                except Exception:  # noqa: BLE001 – driver/GPU changed: measure again on next start
                    _save_choice("?")
                    dev = None
            if dev is None:
                _session, backend = cpu or _cpu_session(), "CPU"
        if _device is not None and batch not in _gpu:
            _gpu[batch] = _gpu_session(_device, batch)
    return _gpu.get(batch) or _session


def loaded():
    """Is the model currently in memory (CPU or GPU; or is the AI process running)?"""
    from scanner import aiworker
    return _session is not None or bool(_gpu) or aiworker.running()


_last_use = [0.0]   # time.monotonic() of the last fingerprint (for unloading after a minute without a scan)


def idle_for(now=None):
    """Seconds since the last fingerprint."""
    return (time.monotonic() if now is None else now) - _last_use[0]


def release():
    """Unload the model (system tray, no scan for a long time, minimized) – reloaded on the next fingerprint."""
    global _session, _device
    from scanner import aiworker
    if aiworker.running():
        return aiworker.stop(background=True)   # end the process: really frees all memory (waiting in a thread)
    if not _run_lock.acquire(blocking=False):   # currently running (scan, fingerprints): not this time – never wait
        return False
    try:
        with _lock:
            _gpu.clear()
            _session, _device = None, None
    finally:
        _run_lock.release()
    return True


def _small(bgr):
    """Shrink to the model's input size (in the app – only 150 KB per image go to the AI process)."""
    return cv2.resize(bgr, (SIZE, SIZE), interpolation=cv2.INTER_AREA)


def _prep(small):
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return ((rgb - _MEAN) / _STD).transpose(2, 0, 1)


def blank():
    return np.zeros((SIZE, SIZE, 3), np.uint8)


_run_lock = threading.RLock()   # one call after another: the GPU binding (DirectML) can't handle
# concurrent runs (e.g. computing fingerprints while a scan is already running – or after a game switch)


def embed(images, batch=16):
    """Card images (BGR) -> normalized fingerprints (n × 384, float32). Loads the model on demand (< 1 s).
    Computed in the AI process (aiworker) – if that's unavailable, here in the app (same result)."""
    global backend
    from scanner import aiworker
    small = [_small(im) for im in images]
    try:
        if aiworker.usable():
            try:
                res = aiworker.call("embed", small, batch)
                backend = aiworker.info().get("backend", backend) + " · own process"
                return res
            except aiworker.Unavailable:
                pass
        return embed_small(small, batch)
    finally:
        _last_use[0] = time.monotonic()


def warm(ocr=False):
    """Preload the model (all batch sizes; ocr: OCR too) – in the AI process, without blocking the UI.
    Without the process: only batch 1 here in the app (as before)."""
    from scanner import aiworker
    if aiworker.usable():
        try:
            aiworker.call("warm", ocr)
            global backend
            backend = aiworker.info().get("backend", backend) + " · own process"
            return
        except aiworker.Unavailable:
            pass
    embed([blank()])


def embed_small(small, batch=16):
    """Like embed, but images already shrunk to model size and always in this process (the AI process calls this)."""
    with _run_lock:
        return _embed(small, batch)


def _embed(images, batch):
    out = []
    session(1)  # pick the device
    for i in range(0, len(images), batch):
        x = np.stack([_prep(im) for im in images[i:i + batch]])
        n = len(x)
        if _device is not None:  # fixed batch size: pad
            size = next((b for b in GPU_BATCHES if b >= n), GPU_BATCHES[-1])
            if size > n:
                x = np.concatenate([x, np.zeros((size - n,) + x.shape[1:], np.float32)])
            h = session(size).run(None, {"pixel_values": x})[0][:n]
        else:
            h = session().run(None, {"pixel_values": x})[0]
        v = h[:, 0]  # class token = summary of the whole image
        out.append(v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9))
    return np.concatenate(out) if out else np.zeros((0, 384), np.float32)


# ---------- Index per set ----------
def fp_path(code):
    return RECOG / f"{code}.fp.npz"


def build_set(code, cards, progress=lambda done, total: None):
    """Compute and save the fingerprints of all card images of a set. cards: entries with "id" and "img"."""
    ids, vecs, todo = [], [], []
    for c in cards:
        path = BASE / c["img"]
        if path.exists():
            todo.append((c["id"], path))
    for i in range(0, len(todo), 16):
        part = todo[i:i + 16]
        imgs = [cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR) for _, p in part]
        keep = [(cid, im) for (cid, _), im in zip(part, imgs) if im is not None]
        if keep:
            vecs.append(embed([im for _, im in keep]))
            ids += [cid for cid, _ in keep]
        progress(min(i + 16, len(todo)), len(todo))
    if not ids:
        return 0
    np.savez_compressed(fp_path(code), ids=np.array(ids), vecs=np.concatenate(vecs).astype(np.float16))
    return len(ids)


def up_to_date(code, cards):
    """Fingerprints of the set present and for exactly these cards (with image)? Price updates rewrite the
    set file but change no images – so all that counts is whether cards were added or removed."""
    f = fp_path(code)
    if not f.exists():
        return False
    try:
        with np.load(f) as z:
            have = set(z["ids"].tolist())
    except (OSError, ValueError, KeyError):
        return False
    want = {c["id"] for c in cards if (BASE / c["img"]).exists()}
    return have == want


class Index:
    """Fingerprints of the loaded sets (cards: {id: entry}) plus – if present – the bundled index of all
    cards. Cards from sets that aren't loaded are looked up in the card database only on a hit; aiscan loads their
    image for confirmation on demand."""

    def __init__(self, cards_by_id, codes, global_file=None):
        self.ids, mats, seen = [], [], set()
        for code in codes:
            f = fp_path(code)
            if not f.exists():
                continue
            with np.load(f) as z:
                ids, vecs = list(z["ids"]), z["vecs"].astype(np.float32)
            keep = [i for i, cid in enumerate(ids) if cid in cards_by_id]
            self.ids += [ids[i] for i in keep]
            seen.update(ids[i] for i in keep)
            mats.append(vecs[keep])
        self.n_sets = len(self.ids)
        self.n_global = 0
        if global_file is not None:
            with np.load(global_file) as z:
                gids, gvecs = z["ids"].tolist(), z["vecs"]
            keep = [i for i, cid in enumerate(gids) if cid not in seen]
            self.ids += [gids[i] for i in keep]
            mats.append(gvecs[keep].astype(np.float32))
            self.n_global = len(keep)
        self.mat = np.concatenate(mats) if mats else np.zeros((0, 384), np.float32)
        self._drop_card_backs()
        self.mat = _mapped(self.ids, self.mat)
        self.cards = dict(cards_by_id)

    def _drop_card_backs(self):
        """Drop entries whose image is just the normal card back (e.g. playtest double-faced cards from MB2: Scryfall
        shows the card back as the "back face") – otherwise every face-down card counts as that card. The card back's
        fingerprint is SCAN° data: it comes with the Magic data pack (models/ during development); without it nothing
        is filtered."""
        from cards import packs
        f = packs.path_of("mtg", CARDBACK) if "mtg" in packs.PACKS else None
        if f is None or not len(self.ids):
            return
        back = np.load(f).astype(np.float32)
        keep = (self.mat @ back) < 0.9
        if keep.all():
            return
        self.ids = [cid for cid, k in zip(self.ids, keep) if k]
        self.mat = self.mat[keep]

    def __len__(self):
        return len(self.ids)

    def vector(self, cid):
        """Fingerprint of a print (normalised like the search) or None – e.g. to find prints with the same image."""
        pos = self.__dict__.get("_pos")
        if pos is None:
            pos = self._pos = {c: i for i, c in enumerate(self.ids)}
        i = pos.get(cid)
        return None if i is None else self.mat[i]

    def entry(self, cid):
        """Entry for an ID – from the loaded sets or from the card database (with image URL)."""
        e = self.cards.get(cid)
        if e is None:
            e = _entry_from_db(cid)
            if e is not None:
                self.cards[cid] = e
        return e

    def rows_of_sets(self, codes):
        """Row numbers of the prints of these sets (filtered scan, aiscan) – from the card database once per set list;
        their part of the fingerprint matrix is copied into RAM with it (search_many(rows=) then reads only that)."""
        key = tuple(sorted({c.lower() for c in codes if c}))
        cache = self.__dict__.setdefault("_focus_rows", {})
        if key not in cache:
            from cards import carddb
            sids = set()
            if key and carddb.exists():
                with carddb.connection() as con:
                    sids = {r[0] for r in con.execute(
                        f"SELECT id FROM cards WHERE lower(set_code) IN ({','.join('?' * len(key))})", key)}
            rows = np.array([i for i, cid in enumerate(self.ids) if cid.rpartition("_")[0] in sids], np.int64)
            subs = self.__dict__.setdefault("_focus_mat", {})
            subs.clear()   # one set choice at a time (a few MB at most)
            subs[id(rows)] = (rows, np.ascontiguousarray(self.mat[rows]) if len(rows) else None)
            for k in [k for k in cache if k != key]:
                del cache[k]
            cache[key] = rows
        return cache[key]

    def preload_sets(self, codes):
        """Filtered scan, chosen sets: their rows and matrix (rows_of_sets) and their card entries ready in RAM ->
        the entries (for the reference images)."""
        rows = self.rows_of_sets(codes)
        missing = [self.ids[i] for i in rows if self.ids[i] not in self.cards]
        if missing:
            self.cards.update(_entries_from_db(missing))
        return [self.cards[self.ids[i]] for i in rows if self.ids[i] in self.cards]

    def search_many(self, vecs, k=8, rows=None):
        """Several fingerprints at once (one matrix multiplication instead of n) -> [[(entry, similarity)], …].
        rows: only these index rows (rows_of_sets – the filtered scan)."""
        if not len(self.ids) or not len(vecs) or (rows is not None and not len(rows)):
            return [[] for _ in vecs]
        if rows is None:
            mat = self.mat
        else:   # the filtered scan's part, already copied (rows_of_sets) – otherwise cut out now
            sub = self.__dict__.get("_focus_mat", {}).get(id(rows))
            mat = sub[1] if sub is not None and sub[0] is rows else self.mat[rows]
        sims_all = np.asarray(vecs, np.float32) @ mat.T  # (windows × cards) – twice as fast this way round
        k = min(k, sims_all.shape[1])
        tops = np.argpartition(sims_all, -k, axis=1)[:, -k:]  # all windows at once
        cid = self.ids.__getitem__ if rows is None else (lambda i: self.ids[rows[i]])   # subset row -> print
        missing = {cid(i) for i in tops.ravel() if cid(i) not in self.cards}
        if missing:  # cards from sets that aren't loaded: all at once from the card database
            self.cards.update(_entries_from_db(sorted(missing)))
        out = []
        for j in range(sims_all.shape[0]):
            sims = sims_all[j]
            top = tops[j][np.argsort(-sims[tops[j]])]
            row = []
            for i in top:
                e = self.entry(cid(i))
                if e is not None:
                    row.append((e, float(sims[i])))
            out.append(row)
        return out

    def search(self, vec, k=8):
        """-> [(entry, similarity 0..1)] the k most similar cards."""
        if not len(self.ids):
            return []
        sims = self.mat @ vec
        top = np.argpartition(-sims, min(k, len(sims) - 1))[:k]
        top = top[np.argsort(-sims[top])]
        out = []
        for i in top:
            e = self.entry(self.ids[i])
            if e is not None:
                out.append((e, float(sims[i])))
        return out


def _mapped(ids, mat):
    """Fingerprint matrix as a file (data/cache/fp/), only memory-mapped (mmap) instead of held in RAM:
    Windows keeps it in the file cache and can release it at any time – the app needs ~170 MB less
    private memory (Magic, 113,000 cards). Just as fast: after the first search the pages are in memory.
    Same cards = same file (name derived from the IDs); old files of the same game are deleted."""
    if len(ids) < 2000:
        return mat
    import games
    try:
        h = hashlib.sha1("\n".join(ids).encode("utf-8")).hexdigest()[:16]
        folder = DATA / "cache" / "fp"
        folder.mkdir(parents=True, exist_ok=True)
        key = games.current().key
        path = folder / f"{key}-{h}-{mat.shape[0]}.npy"
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                np.save(f, np.ascontiguousarray(mat, np.float32))
            tmp.replace(path)
            for old in folder.glob(f"{key}-*.npy"):
                if old != path:
                    try:
                        old.unlink()
                    except OSError:
                        pass   # still mapped (second game in memory) – next time
        m = np.load(path, mmap_mode="r")
        if m.shape != mat.shape:
            return mat
        return m
    except (OSError, ValueError) as e:   # no space, read-only …: then keep it in memory
        log.info("AI index stays in memory: %s", e)
        return mat


def _entry_from_db(cid):
    """<scryfall-id>_<face> -> entry as in the set files (with "img_normal" for lazy loading) or None."""
    return _entries_from_db([cid]).get(cid)


def _entries_from_db(cids):
    """Several entries with one query (when scanning ~8 new cards per search step) -> {ID: entry}."""
    from cards import carddb
    if not cids or not carddb.exists():
        return {}
    by_sid = {}
    for cid in cids:
        by_sid.setdefault(cid.rpartition("_")[0], []).append(cid)
    with carddb.connection() as con:
        rows = con.execute(f"SELECT * FROM cards WHERE id IN ({','.join('?' * len(by_sid))})",
                           list(by_sid)).fetchall()
    out = {}
    for row in rows:
        row = dict(row)
        for cid in by_sid.get(row["id"], []):
            e = _entry_from_row(cid, row)
            if e is not None:
                out[cid] = e
    return out


def _entry_from_row(cid, row):
    import json
    from cards import carddb
    from scanner.common import image_rel
    face = cid.rpartition("_")[2]
    e = carddb.entry_from_row(row)
    faces = json.loads(row["faces"]) if row.get("faces") else []
    f = int(face) if face.isdigit() else 0   # "_r": second, rotated vector of a landscape card – same entry
    if faces and faces[0].get("img_normal"):  # double-faced: each face has its own image
        if f >= len(faces):
            return None
        e.update(id=cid, name=faces[f].get("name") or e["name"],
                 img=image_rel(row["set_code"], row["number"], f), img_normal=faces[f].get("img_normal"))
    else:
        e["img_normal"] = row.get("img_normal")
    if row.get("layout") == "art_series":   # Magic art card: only the artwork – never counted on the fingerprint alone
        e["art_series"] = True
    return e
