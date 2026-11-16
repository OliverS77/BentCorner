"""Card data signed by the server's own data key (Oliver/lead/Gordon 07.11.): new sets come automatically, without a
release. The data key lives only on the VPS – so everything it signs is treated as foreign: whoever takes over the
server may change card data of the games below, never anything else.

    /dl/packs/packs-data2.json      {"v": 1, "key_id", "seq", "t", "packs": {<game>: {"files": [...]}}}  (packs.json format)
    /dl/packs/packs-data2.json.sig  Ed25519 (Base64) over PREFIX2 + the bytes of packs-data2.json

Since 0.9.9.10x (lead/Gordon 14.11.2026) the data files lie on the server under names with their checksum ("path",
e.g. cards.1a2b3c4d.sqlite – see hashed_name); the files with fixed names belong to the release data (packs.json)
and are never touched by the data key. 0.9.7–0.9.9 read the older packs-data.json (PREFIX, v1) and know no "path":
for them that file is never published, and the own prefix v2 keeps data2 content from passing as v1.

Which data keys count is said only by the signed release manifest (manifest.json, release key): "data_keys":
[{"id", "pk", "until": "YYYY-MM-DD"}]. No field, an empty list, an unknown id or a passed "until" -> no data key.
Revoking = a new release manifest without the entry. The app keeps the newest release manifest it saw (with its
signature, checked again on every read; an older one never replaces it). A data manifest is only ever read for
key_id, seq, t and packs – data_keys, games_off or anything else in it is ignored.

What a data key may deliver is the hard list DATA_FILES below (exact names, per game; changes only with a program
update). seq counts per key_id and may only grow (at most MAX_SEQ_JUMP at a time); t must not lie in the future. A data
entry for a game only counts when it is newer than that game's entry in packs.json – a fresh release listing always
wins over older data entries.
"""
import base64
import datetime
import json
import logging
import pathlib
import time

log = logging.getLogger(__name__)

PREFIX = b"bc-carddata-v1\n"    # packs-data.json of 0.9.7–0.9.9 – never published (no "path" there)
PREFIX2 = b"bc-carddata-v2\n"   # packs-data2.json: data files under hashed names ("path")
DATA_NAME = "packs-data2.json"
MAX_SEQ_JUMP = 10_000
FUTURE_S = 24 * 3600       # clock skew allowed for "t"
MB = 1 << 20

# the only files a data key may deliver – Scryfall bulk (Magic: languages, set names, index), TCGdex (Pokémon),
# YGOPRODeck (Yu-Gi-Oh!). Lorcana and every other game: never, also once they are released.
DATA_FILES = {
    "mtg": ("langs.tsv.gz", "setnames.json", "fingerprints-all.npz", "fingerprints-add.npz", "LICENSES.txt"),
    "pokemon": ("cards.sqlite", "cm_fix.json", "setnames.json", "fingerprints-all.npz", "LICENSES.txt"),
    "yugioh": ("cards.sqlite", "ygo-locale.sqlite", "fingerprints-all.npz", "fingerprints-add.npz", "LICENSES.txt"),
}
# largest size per file (any signature): the biggest real files are ~80 MB (11/2026)
LIMIT_BY_SUFFIX = {".sqlite": 400 * MB, ".npz": 400 * MB, ".gz": 200 * MB, ".json": 20 * MB, ".txt": 1 * MB,
                   ".npy": 4 * MB}
LIMIT_BY_NAME = {"fingerprints-add.npz": 32 * MB}   # docs/FP-ADD-FORMAT.md §2
# the tables a card database must have (probe before it is put in place)
NEEDS_TABLES = {"cards.sqlite": {"cards", "meta"}, "ygo-locale.sqlite": {"prints", "meta"}}


class DataRejected(Exception):
    pass


def limit_of(name):
    if name in LIMIT_BY_NAME:
        return LIMIT_BY_NAME[name]
    suffix = pathlib.PurePosixPath(name).suffix.lower()
    return LIMIT_BY_SUFFIX.get(suffix, 50 * MB)


def hashed_name(name, sha256):
    """Server name of a data file with its checksum: the first 8 hex digits of its sha256 after the stem –
    cards.sqlite -> cards.1a2b3c4d.sqlite, langs.tsv.gz -> langs.1a2b3c4d.tsv.gz. Its packed twin: + ".gz"."""
    stem, dot, rest = name.partition(".")
    return f"{stem}.{sha256[:8]}{dot}{rest}" if dot else f"{name}.{sha256[:8]}"


def _hexsha(v):
    return isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)


def _check_path(key, name, f):
    """"path" (optional): exactly hashed_name(name, sha256) – no folder, nothing but another download name for a file
    that is allowed anyway; its .gz then must have path + ".gz". Never unlocks any other file."""
    path, gz = f.get("path"), f.get("gz")
    gzpath = gz.get("path") if isinstance(gz, dict) else None
    if path is None:
        if gzpath is not None:
            raise DataRejected(f"{key}/{name}: gz path without path")
        return
    if not isinstance(path, str) or not _hexsha(f.get("sha256")) or path != hashed_name(name, f["sha256"]):
        raise DataRejected(f"{key}/{name}: path")
    if gz is not None and gzpath != path + ".gz":
        raise DataRejected(f"{key}/{name}: gz path")


def release_names(key):
    """Files a release-signed packs.json may name for a game: exactly the program's own list (packs.PACKS)."""
    from cards import packs
    spec = packs.PACKS.get(key) or {}
    return (*spec.get("files", ()), *spec.get("extra", ()), "LICENSES.txt")


def check_files(key, files, names):
    """Every file entry of one game: name exactly from `names`, .gz exactly "<name>.gz", sizes within the limits.
    -> None, raises DataRejected otherwise (the whole listing is refused, not just the entry)."""
    if not isinstance(files, list):
        raise DataRejected(f"{key}: files is not a list")
    for f in files:
        if not isinstance(f, dict) or f.get("name") not in names or not isinstance(f["name"], str):
            raise DataRejected(f"{key}: file not allowed: {str(f.get('name') if isinstance(f, dict) else f)[:80]}")
        name = f["name"]
        try:
            size = int(f.get("size") or 0)
        except (TypeError, ValueError):
            raise DataRejected(f"{key}/{name}: size") from None
        if size < 0 or size > limit_of(name):
            raise DataRejected(f"{key}/{name}: too large")
        _check_path(key, name, f)
        gz = f.get("gz")
        if gz is not None:
            if not isinstance(gz, dict) or gz.get("name") != name + ".gz":
                raise DataRejected(f"{key}/{name}: gz name")
            try:
                gsize = int(gz.get("size") or 0)
            except (TypeError, ValueError):
                raise DataRejected(f"{key}/{name}: gz size") from None
            if gsize < 0 or gsize > limit_of(name):
                raise DataRejected(f"{key}/{name}: gz too large")


# ---- data keys from the release manifest ----

def _cache_dir():
    from net import updater
    return updater.folder()


def remember_release(raw, sig_text, folder=None):
    """A release manifest whose signature was just verified (updater.fetch_manifest): keep it as the source of the data
    keys – unless it is older than the one kept (an old manifest played back must not bring a revoked key back)."""
    from net import updater
    folder = pathlib.Path(folder or _cache_dir())
    if not updater.verify(raw, sig_text):   # checked here too: nothing else ever replaces the kept one
        return False
    try:
        new = json.loads(raw.decode("utf-8"))
    except ValueError:
        return False
    old = _cached_release(folder)
    if old is not None and _stamp(new) < _stamp(old):
        log.info("Release manifest older than the kept one – data keys unchanged")
        return False
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "release-manifest.json.tmp").write_bytes(raw)
        (folder / "release-manifest.json.sig.tmp").write_text(sig_text.strip(), "ascii")
        (folder / "release-manifest.json.sig.tmp").replace(folder / "release-manifest.json.sig")
        (folder / "release-manifest.json.tmp").replace(folder / "release-manifest.json")
    except OSError:
        return False
    return True


def _stamp(m):
    """Order of release manifests: "t" (seconds, newer publish_release) or the day."""
    try:
        t = int(m.get("t") or 0)
    except (TypeError, ValueError):
        t = 0
    return (str(m.get("date") or ""), t)


def _cached_release(folder):
    from net import updater
    try:
        raw = (folder / "release-manifest.json").read_bytes()
        sig = (folder / "release-manifest.json.sig").read_text("ascii")
    except OSError:
        return None
    if not updater.verify(raw, sig):   # release key only
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        return None


def keys(now=None, folder=None):
    """{id: public key (Base64)} of the data keys the newest kept release manifest allows today. Nothing built in."""
    m = _cached_release(pathlib.Path(folder or _cache_dir()))
    out = {}
    if not m:
        return out
    today = datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc).date()
    for k in m.get("data_keys") or []:
        if not isinstance(k, dict) or not isinstance(k.get("id"), str) or not isinstance(k.get("pk"), str):
            continue
        try:
            until = datetime.date.fromisoformat(str(k.get("until")))
        except ValueError:
            continue
        if today <= until:
            out[k["id"]] = k["pk"]
    return out


def refresh(base):
    """Fetch the release manifest (no counting parameters) and keep it if it is genuine and not older."""
    from net import netpolite
    from net import updater
    try:
        r = netpolite.get(f"{base}/manifest.json", timeout=20)
        s = netpolite.get(f"{base}/manifest.json.sig", timeout=20)
    except Exception:  # noqa: BLE001 – offline: the kept one counts
        return
    if r.status_code == 200 and s.status_code == 200 and updater.verify(r.content, s.text):
        remember_release(r.content, s.text)


# ---- the data manifest ----

def _seq_file():
    from scanner.common import DATA
    return DATA / "packs" / ".dataseq.json"


def _seen(path):
    try:
        return json.loads(pathlib.Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def verify_data(raw, sig_text, now=None, allowed=None, seq_file=None, prefix=PREFIX2):
    """packs-data2.json -> {"key_id", "seq", "t", "packs"} if a data key the release manifest allows signed it (over
    `prefix` + the bytes – v2; a v1 signature never passes here, nor a v2 one in 0.9.7–0.9.9) and everything in it is
    on the hard list. Raises DataRejected otherwise. Remembers the seq (per key_id)."""
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey
    now = time.time() if now is None else now
    allowed = keys(now) if allowed is None else allowed
    if not allowed:
        raise DataRejected("no data key allowed")
    try:
        m = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise DataRejected("unreadable") from None
    if not isinstance(m, dict):
        raise DataRejected("unreadable")
    kid = m.get("key_id")
    pk = allowed.get(kid) if isinstance(kid, str) else None
    if not pk:
        raise DataRejected("unknown or revoked data key")
    try:
        VerifyKey(base64.b64decode(pk)).verify(prefix + raw, base64.b64decode(sig_text.strip()))
    except (BadSignatureError, ValueError, TypeError):
        raise DataRejected("signature") from None
    seq, t = m.get("seq"), m.get("t")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0 or not isinstance(t, (int, float)) \
            or isinstance(t, bool):
        raise DataRejected("seq/t")
    if t > now + FUTURE_S:
        raise DataRejected("t in the future")
    seq_file = pathlib.Path(seq_file or _seq_file())
    seen = _seen(seq_file)
    last = seen.get(kid, 0) if isinstance(seen.get(kid, 0), int) else 0
    if seq < last:
        raise DataRejected("older seq")
    if seq > last + MAX_SEQ_JUMP:
        raise DataRejected("seq jump")
    packs_ = m.get("packs")
    if not isinstance(packs_, dict):
        raise DataRejected("packs")
    for game, entry in packs_.items():
        if game not in DATA_FILES or not isinstance(entry, dict):
            raise DataRejected(f"game not allowed: {str(game)[:40]}")
        check_files(game, entry.get("files"), DATA_FILES[game])
    if seq != last or kid not in seen:
        seen[kid] = seq
        try:
            seq_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = seq_file.with_name(seq_file.name + ".tmp")
            tmp.write_text(json.dumps(seen), "utf-8")
            tmp.replace(seq_file)
        except OSError:
            pass
    # only these fields ever leave here – data_keys, games_off, notes … in a data manifest mean nothing
    return {"key_id": kid, "seq": seq, "t": t, "packs": packs_}


def release_time(entry):
    """When a game's entry in packs.json was published: "t" (seconds) or – older listings – the end of its day (UTC),
    so a data entry from that same day never counts as newer."""
    try:
        if entry.get("t") is not None:
            return float(entry["t"])
    except (TypeError, ValueError):
        pass
    try:
        d = datetime.date.fromisoformat(str(entry.get("date")))
    except ValueError:
        return float("inf") if entry else 0.0   # no date at all: the release entry always wins
    return datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc).timestamp() + 86400


def merge(release_packs, data):
    """packs.json's games; a game's files replaced by the data manifest's entry only when that is newer. Files the data
    entry doesn't name stay as packs.json lists them (e.g. cardback.npy, which no data key may deliver; a data entry
    with only the new index) – their names in "rel_names", checked against the release list (download/outdated).
    -> new dict"""
    out = dict(release_packs or {})
    if not data:
        return out
    for game, entry in data["packs"].items():
        if game not in DATA_FILES:   # verify_data already refused it; twice is cheap
            continue
        rel = out.get(game)
        if rel and data["t"] <= release_time(rel):
            continue
        named = {f.get("name") for f in entry["files"]}
        kept = [f for f in (rel or {}).get("files") or [] if isinstance(f, dict) and f.get("name") not in named]
        out[game] = {**{k: v for k, v in (rel or {}).items() if k in ("name",)}, "files": entry["files"] + kept,
                     "t": data["t"], "src": "data", "rel_names": [f.get("name") for f in kept]}
    return out


# ---- every delivered file is foreign: a probe before it is put in place (any signature) ----

def probe(name, path):
    """Check a downloaded file before it replaces the old one. Raises DataRejected."""
    path = pathlib.Path(path)
    if path.stat().st_size > limit_of(name):
        raise DataRejected("too large")
    suffix = pathlib.PurePosixPath(name).suffix.lower()
    if suffix == ".sqlite":
        _probe_sqlite(name, path)
    elif suffix in (".npz", ".npy"):
        _probe_numpy(name, path)
    elif suffix == ".json":
        try:
            if not isinstance(json.loads(path.read_text("utf-8")), (dict, list)):
                raise DataRejected("json")
        except (ValueError, UnicodeDecodeError):
            raise DataRejected("json") from None


def _probe_sqlite(name, path):
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        raise DataRejected("sqlite") from None
    try:
        if hasattr(con, "setconfig"):
            con.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        con.execute("PRAGMA trusted_schema = OFF")
        rows = con.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
        if con.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
            raise DataRejected("sqlite damaged")
    except sqlite3.Error:
        raise DataRejected("sqlite") from None
    finally:
        con.close()
    tables = set()
    for kind, tname, sql in rows:
        if kind in ("trigger", "view"):
            raise DataRejected(f"sqlite {kind}")
        if kind == "table":
            tables.add(tname)
            if sql and "VIRTUAL TABLE" in sql.upper() and "USING FTS5" not in " ".join(sql.upper().split()):
                raise DataRejected("sqlite virtual table")
    if not NEEDS_TABLES.get(name, set()) <= tables:
        raise DataRejected("sqlite tables")


def _probe_numpy(name, path):
    import numpy as np
    try:
        if name.endswith(".npy"):
            a = np.load(path, allow_pickle=False)
            arrays = {"": a}
        else:
            with np.load(path, allow_pickle=False) as z:
                arrays = {k: z[k] for k in z.files}
    except (ValueError, OSError, EOFError):
        raise DataRejected("numpy") from None
    for a in arrays.values():
        if a.dtype.kind not in "fiuUSb":
            raise DataRejected("numpy dtype")
    if name == "fingerprints-add.npz":   # docs/FP-ADD-FORMAT.md §2: ids, vecs n × 384 float16, meta with base/count
        ids, vecs, meta = arrays.get("ids"), arrays.get("vecs"), arrays.get("meta")
        if ids is None or vecs is None or meta is None or ids.ndim != 1 or ids.dtype.kind != "U" or vecs.ndim != 2 \
                or vecs.dtype != np.float16 or vecs.shape != (ids.shape[0], 384):
            raise DataRejected("numpy shape")
        try:
            m = json.loads(str(meta))
        except ValueError:
            raise DataRejected("add meta") from None
        if not isinstance(m, dict) or not _hexsha(m.get("base")) or m.get("count") != ids.shape[0]:
            raise DataRejected("add meta")
    if name == "fingerprints-all.npz":
        ids, vecs = arrays.get("ids"), arrays.get("vecs")
        if ids is None or vecs is None or ids.ndim != 1 or ids.dtype.kind != "U" or vecs.ndim != 2 \
                or vecs.dtype.kind != "f" or vecs.shape[0] != ids.shape[0]:
            raise DataRejected("numpy shape")
