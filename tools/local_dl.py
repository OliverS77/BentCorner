"""Fill the local copy for the test switch BC_LOCAL_DL (net/netpolite.py) – once, from a real run of the first start.

    fill(root, copies=[...])   -> from now on, a request missing in <root> is fetched once (through netpolite, so with
                                  its gaps, User-Agent and, for our server, "X-BC-Check: 1"), stored, then answered
                                  from the copy like every other.
Pack files are first looked for in `copies` (e.g. a COPY of an installed app's data/packs – only read): taken only if
their checksum is the one in the signed packs.json, otherwise downloaded. Used by tools/ui-tests/erststart.py --fill.
"""
import hashlib
import json
import os
import pathlib
import shutil
import threading
from urllib.parse import urlparse

import requests

from net import netpolite

STATS = {"fetched": 0, "fetched_bytes": 0, "copied": 0, "copied_bytes": 0, "missing": []}
_lock = threading.Lock()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _pack_copy(root, url, copies):
    """A local pack file with the checksum packs.json asks for -> path, else None."""
    path = urlparse(url).path
    if "/dl/packs/" not in path or not copies:
        return None
    try:
        listing = json.loads(open(os.path.join(root, netpolite.local_name("GET", url.split("/dl/packs/")[0]
                                                                          + "/dl/packs/packs.json")), "rb").read())
    except (OSError, ValueError):
        return None
    rest = path.split("/dl/packs/", 1)[1]
    if "/" not in rest:   # packs.json, packs.json.sig: always from the server
        return None
    sub, name = rest.split("/", 1)
    for entry in (listing.get("packs") or {}).values():
        for f in entry.get("files") or []:
            if f.get("name") != name or f.get("gz"):   # .gz downloads: the copy holds the unpacked file – fetch
                continue
            for c in copies:
                p = os.path.join(c, sub, name)
                if os.path.isfile(p) and os.path.getsize(p) == int(f.get("size") or -1) and _sha256(p) == f["sha256"]:
                    return p
    return None


def save_stats(path):
    with _lock:
        pathlib.Path(path).write_text(json.dumps(STATS, indent=1), "utf-8")


def fill(root, copies=()):
    real = netpolite._local_response

    def answer(root_, method, url, headers=None, data=None, json=None, stream=False, **kw):
        import json as _json
        body = _json.dumps(json) if json is not None else data
        target = os.path.join(root_, netpolite.local_name(method, url, body))
        with _lock:
            if not os.path.isfile(target) and method in ("GET", "POST"):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                src = _pack_copy(root_, url, copies)
                if src:
                    shutil.copyfile(src, target)
                    STATS["copied"] += 1
                    STATS["copied_bytes"] += os.path.getsize(target)
                else:
                    h = {k: v for k, v in (headers or {}).items() if k.lower() != "range"}   # whole file, once
                    try:
                        r = requests.request(method, url, headers=h, data=data, json=json, stream=True,
                                             timeout=kw.get("timeout", 60))
                    except requests.RequestException:
                        STATS["missing"].append(f"{method} {url} (not reachable)")
                        raise
                    if r.status_code != 200:   # a 404 etc. stays a 404 for the app – nothing stored
                        STATS["missing"].append(f"{method} {url} ({r.status_code})")
                        return r
                    with open(target + ".part", "wb") as out:
                        for chunk in r.iter_content(1 << 20):
                            out.write(chunk)
                    os.replace(target + ".part", target)
                    STATS["fetched"] += 1
                    STATS["fetched_bytes"] += os.path.getsize(target)
        return real(root_, method, url, headers=headers, data=data, json=json, stream=stream, **kw)

    netpolite._local_response = answer
