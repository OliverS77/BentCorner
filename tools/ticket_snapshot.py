"""Ticket-Schnappschuss für Badges & Collectibles (collectibles.py): je Programmversion, in der sich am Tauschticket
etwas geändert hat, den Code (ticket.py, rscode.py, tradelib.offer_image) und ein Muster-Ticket nach
assets/collectibles/ legen. Das Programm kopiert das beim Start nach data/collectibles/.

    .venv\\Scripts\\python tools\\ticket_snapshot.py            # aktuelle Version (läuft in build.ps1 mit)
    .venv\\Scripts\\python tools\\ticket_snapshot.py --history  # alle früheren Versionen aus git nachholen
    .venv\\Scripts\\python tools\\ticket_snapshot.py --resample # alle Muster neu zeichnen (andere Musterkarten), je mit
                                                          # dem archivierten Code ihrer Version – Render-ID bleibt

„Geändert“ heißt: der Code, der das Ticket schreibt, liest oder zeichnet, ist anders (Prüfsumme). Gleiches Aussehen
in einer neuen Version → nichts Neues.
"""
import argparse
import ast
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "assets" / "collectibles"
FILES = ("ticket.py", "rscode.py")
# Seit v0.9.1.22 liegen sie im Paket collection/ – ältere Stände (git) noch in der Wurzel
WHERE = {"ticket.py": "collection/ticket.py", "rscode.py": "collection/rscode.py", "tradelib.py": "collection/tradelib.py"}


def flat(src):
    """Paket-Importe auf die alte Form zurückrechnen („from collection import rscode“ -> „import rscode“), damit
    der Hash (render_id) nur bei echten Änderungen am Ticket wechselt – nicht wegen des Umzugs in Pakete."""
    pkgs = "(?:scanner|cards|collection|net|ui|system)"
    src = re.sub(r"^(\s*)from " + pkgs + r" import (\w+)( as \w+)?(\r?)$", r"\1import \2\3\4", src, flags=re.M)
    return re.sub(r"^(\s*)from " + pkgs + r"\.(\w+) import ", r"\1from \2 import ", src, flags=re.M)
    return re.sub(r"^(\s*)from " + pkgs + r"\.(\w+) import ", r"from  import ", src, flags=re.M)

# Muster: feste Karten, feste Namen – immer dasselbe Ticket, damit man die Formate vergleichen kann.
# Nie Universes Beyond (nicht von der Fan Content Policy gedeckt – legal 03.11.2026; tests/test_collectibles_no_ub.py)
# und nie der Standard-Rücken: beide haben einen eigenen, neutralen Rücken (BACKS).
ME = ("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6", "Oliver")
FRIEND = ("f0e1d2c3b4a5968778695a4b3c2d1e0f", "Max")
GIVE = [{"set": "m10", "number": "146", "lang": "de", "foil": False, "count": 1, "name": "Lightning Bolt"},
        {"set": "mh2", "number": "267", "lang": "en", "foil": True, "count": 1, "name": "Counterspell"}]
GET = [{"set": "dsk", "number": "112", "lang": "en", "foil": False, "count": 2, "name": "Overlord of the Hauntwoods"},
       {"set": "mh3", "number": "198", "lang": "ja", "foil": False, "count": 1, "name": "Ugin's Labyrinth"}]
PRICE = {"146": 2.1, "267": 1.4, "112": 7.8, "198": 3.1}
BACKS = ("nacht", "wald")   # userprofile.PRESETS: Sternennacht (Oliver), Wald (Max) – the samples up to 0.9.7.30
# from 0.9.7.31 on (the ticket draws no default back): Max without an own back – the sample shows the empty place.
# The backs of a sample are stored in its about.json ("backs"); --resample draws every version with its own.
NEW_BACKS = ("nacht", None)


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


def offer_image_source(tradelib_src):
    tree = ast.parse(tradelib_src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "offer_image":
            return ast.get_source_segment(tradelib_src, node)
    return ""


def sources_now():
    out = {f: flat((ROOT / WHERE[f]).read_text("utf-8")) for f in FILES}
    out["offer_image.py"] = offer_image_source(flat((ROOT / WHERE["tradelib.py"]).read_text("utf-8")))
    return out


def _show(rev, f):
    """Datei eines alten Stands – am neuen Ort, sonst am alten (vor dem Umzug in Pakete)."""
    try:
        return flat(git("show", f"{rev}:{WHERE[f]}"))
    except subprocess.CalledProcessError:
        return git("show", f"{rev}:{f}")


def sources_at(rev):
    out = {}
    for f in FILES:
        try:
            out[f] = _show(rev, f)
        except subprocess.CalledProcessError:
            return None
    try:
        out["offer_image.py"] = offer_image_source(_show(rev, "tradelib.py"))
    except subprocess.CalledProcessError:
        return None
    return out if out["offer_image.py"] else None


def render_id(src):
    h = hashlib.sha256()
    for k in sorted(src):
        h.update(k.encode() + b"\0" + src[k].replace("\r\n", "\n").encode("utf-8") + b"\0")
    return h.hexdigest()[:10]


def load_manifest():
    try:
        return json.loads((OUT / "manifest.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {"current": "", "formats": {}, "versions": []}


def _module(name, code):
    m = types.ModuleType(name)
    m.__file__ = f"<{name} snapshot>"
    sys.modules[name] = m
    exec(compile(code, m.__file__, "exec"), m.__dict__)
    return m


def _rows(cards):
    return [{"name": c["name"], "set": c["set"].upper(), "number": c["number"], "count": c["count"],
             "price": PRICE.get(c["number"]), "lang": c["lang"], "foil": c["foil"]} for c in cards]


def render(src, out_dir, version, backs=NEW_BACKS):
    """Muster-Ticket mit dem Code von damals zeichnen. -> Archiv-Eintrag (wie collectibles.archive)"""
    from collection import tradelib  # aktuelle Umgebung (Schriften, Farben, Kartenrückseiten)
    saved = {k: sys.modules.get(k) for k in ("ticket", "rscode")}
    try:
        _module("rscode", src["rscode.py"])
        tk = _module("ticket", src["ticket.py"])
        import inspect
        params = inspect.signature(tk.new).parameters
        kw = {}
        if "kind" in params:
            kw["kind"] = "o"
        if "money" in params:
            kw["money"] = 2.5
        t = tk.new(ME, FRIEND, GIVE, GET, **kw)
        t["id"], t["t"] = "c0ffee42", 1760000000 + 86400 * 10
        if "x" in t:
            t["x"] = "c0ffee42"
        if "g" in t:
            t["g"] = "mtg"
        ns = dict(tradelib.__dict__)
        exec(compile(src["offer_image.py"], "<offer_image snapshot>", "exec"), ns)
        from system import userprofile
        back = {p[0]: p[2] for p in userprofile.PRESETS}
        img = ns["offer_image"]((ME[1], back.get(backs[0])), (FRIEND[1], back.get(backs[1])), _rows(GET), _rows(GIVE), t)
        out_dir.mkdir(parents=True, exist_ok=True)
        img.save(str(out_dir / "sample.png"), "PNG")
        code = None
        try:
            lay = getattr(tk, "RECEIPT", None)
            b = tk.bits(t, lay) if lay is not None else tk.bits(t)
            if b:
                lay = lay or tk
                code = {"cols": lay.COLS, "x0": lay.X0, "m": lay.M, "w": lay.W, "bottom": tk.BOTTOM, "rows": b[0],
                        "bits": "".join("1" if v else "0" for v in b[1])}
        except Exception:  # noqa: BLE001
            code = None
        label = tk.label(t) if hasattr(tk, "label") else t["id"]

        def rows(cards):
            return [dict(c, set=c["set"].upper(), eur=PRICE.get(c["number"])) for c in cards]
        return {"collectible": "trade-ticket", "id": t["id"], "trade": t.get("x") or t["id"], "game": "mtg",
                "label": label, "kind": t.get("k") or "f", "version_in_trade": int(t.get("n") or 1),
                "issued": t["t"], "from": t["f"], "to": t["o"], "money_eur": int(t.get("m") or 0) / 100,
                "app_version": version, "ticket_format": t.get("v"), "a": rows(GIVE), "b": rows(GET),
                "ticket": t, "code": code, "events": [], "me": list(ME), "png": "sample.png", "backs": list(backs),
                "layout": "receipt" if hasattr(tk, "RECEIPT") else "wide"}
    finally:
        for k, m in saved.items():
            if m is not None:
                sys.modules[k] = m
            else:
                sys.modules.pop(k, None)


def _same_as_last(src, version, man):
    """Quelltext anders, Ticket gleich? Muster probeweise zeichnen und mit dem der letzten Version vergleichen
    (Bild pixelgleich, gleicher Ticket-Code). Übersetzungsschlüssel, Kommentare oder Importe allein ändern am Ticket
    nichts – dafür keine neue Collectible-Version (Regel: nur mitführen, wenn sich am Ticket etwas ändert)."""
    import tempfile
    import cv2
    last = man["versions"][-1]["version"]
    old_png = OUT / "versions" / last / "sample.png"
    try:
        old_about = json.loads((OUT / "versions" / last / "about.json").read_text("utf-8"))
    except (OSError, ValueError):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        try:
            sample = render(src, pathlib.Path(tmp), version)
        except Exception:  # noqa: BLE001
            return False
        a, b = cv2.imread(str(pathlib.Path(tmp) / "sample.png")), cv2.imread(str(old_png))
    if a is None or b is None or a.shape != b.shape:
        return False
    ys = (cv2.absdiff(a, b).max(axis=2) > 0).nonzero()[0]
    # Unterschiede nur in der Datumszeile im Kopf (das Muster trägt die Uhrzeit des Zeichnens) zählen nicht
    if len(ys) and not (ys.max() - ys.min() < 60 and ys.max() < a.shape[0] * 0.1):
        return False
    return (sample or {}).get("code") == (old_about.get("sample") or {}).get("code")


def snapshot(src, version, note, man):
    rid = render_id(src)
    if man["versions"] and man["versions"][-1]["render"] == rid:
        man["current"] = rid
        return False                                   # nichts am Ticket geändert
    if man["versions"] and _same_as_last(src, version, man):
        man["current"] = man["versions"][-1]["render"]
        return False                                   # nur der Quelltext anders, das Ticket selbst nicht
    fdir = OUT / "formats" / rid
    if rid not in man["formats"]:
        fdir.mkdir(parents=True, exist_ok=True)
        for name, code in src.items():
            (fdir / name).write_text(code, "utf-8")
        tv = None
        for line in src["ticket.py"].splitlines():
            if line.startswith("VERSION ="):
                tv = line.split("=", 1)[1].strip()
        about = {"render": rid, "since": version, "ticket_format": tv, "files": sorted(src),
                 "note": "Code, der das Ticket schreibt (ticket.new/bits), liest (decode_*, read_image) und zeichnet "
                         "(offer_image). Zum Einlesen alter Tickets: ticket.py + rscode.py reichen."}
        (fdir / "about.json").write_text(json.dumps(about, ensure_ascii=False, indent=1), "utf-8")
        man["formats"][rid] = about
    vdir = OUT / "versions" / version
    try:
        sample = render(src, vdir, version)
        png = "sample.png"
    except Exception as e:  # noqa: BLE001 – alter Code passt nicht mehr zur heutigen Umgebung
        vdir.mkdir(parents=True, exist_ok=True)
        sample, png = None, None
        note = (note + " · " if note else "") + f"Muster nicht zeichenbar ({type(e).__name__}: {e})"
    about = {"version": version, "render": rid, "png": png, "sample": sample, "note": note,
             "format_dir": f"formats/{rid}"}
    (vdir / "about.json").write_text(json.dumps(about, ensure_ascii=False, indent=1), "utf-8")
    man["versions"] = [v for v in man["versions"] if v["version"] != version] + [
        {"version": version, "render": rid}]
    man["current"] = rid
    return True


def resample(man):
    """Every archived version drawn again with its own code (formats/<render>) – new sample cards, same render ID,
    same note. -> the versions drawn."""
    done = []
    for v in man["versions"]:
        vdir = OUT / "versions" / v["version"]
        fdir = OUT / "formats" / v["render"]
        try:
            about = json.loads((vdir / "about.json").read_text("utf-8"))
        except (OSError, ValueError):
            continue
        src = {f.name: f.read_text("utf-8") for f in fdir.glob("*.py")}
        about["sample"] = render(src, vdir, v["version"], tuple((about.get("sample") or {}).get("backs") or BACKS))
        about["png"] = "sample.png"
        (vdir / "about.json").write_text(json.dumps(about, ensure_ascii=False, indent=1), "utf-8")
        done.append(v["version"])
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--resample", action="store_true")
    a = ap.parse_args()
    # kein offscreen: dort fehlen die Ersatzschriften (⇄ wird zum Kästchen); ein Fenster öffnet sich trotzdem nicht
    from PySide6 import QtGui
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(sys.argv)
    from ui import look
    look.register_fonts()
    from system import i18n
    i18n.set_language("de")   # Muster wie bisher auf Deutsch (bis v0.9.1.21 die Standardsprache) – vergleichbar bleiben
    man = load_manifest()
    if a.resample:
        print("neu gezeichnet:", ", ".join(resample(man)))
        return
    if a.history:
        log = git("log", "--reverse", "--format=%H %s", "--", "ticket.py", "rscode.py", "tradelib.py").splitlines()
        for line in log:
            rev, title = line.split(" ", 1)
            if not title.startswith("v") or ":" not in title:
                continue
            ver = title.split(":", 1)[0][1:]
            src = sources_at(rev)
            if src and snapshot(src, ver, title.split(":", 1)[1].strip(), man):
                print("neu:", ver, render_id(src))
    import version
    src = sources_now()
    if snapshot(src, version.VERSION, "", man):
        print("neu:", version.VERSION, render_id(src))
    else:
        print("Ticket unverändert:", render_id(src))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
    del app


if __name__ == "__main__":
    main()
