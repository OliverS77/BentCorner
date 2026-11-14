"""Checks a finished package: nothing in it that must not be shipped, nothing the slim build leaves out, and its size.
build.ps1 runs it on dist\\BentCorner.exe after tools\\build_launcher.py and on dist\\app-stage + the portable ZIP after
tools\\make_dist.py; exit 1 with the list.

- DirectML*.dll: the app uses the DirectML from Windows itself (scanner/accel.py) – we ship no proprietary GPU
  library (signing/open source, 0.9.7.4).
- Qt Quick Timeline and Qt Virtual Keyboard: unused, and freely available only under the GPL (legal, 0.9.7.5).
- Everything else in build_launcher.SKIP (unused Qt Quick Controls/Qt.labs, translations, AVIF, FFmpeg …): a PySide6/
  Pillow/OpenCV update can bring new file names that slip past the filter – then this stops the build, not the user.
- Size: a warning above LIMIT_MB (program files unpacked), so that a new heavy dependency gets noticed.

    .venv\\Scripts\\python tools\\check_package.py dist\\BentCorner.exe [dist\\app-stage] [dist\\…-portable.zip]
"""
import io
import pathlib
import re
import struct
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_launcher import SKIP  # noqa: E402

FORBIDDEN = re.compile(r"(^|/)(directml[^/]*\.dll|qt6quicktimeline[^/]*\.dll|qt6virtualkeyboard[^/]*\.dll)$"
                       r"|/qml/qtquick/(timeline|virtualkeyboard)/", re.I)
LIMIT_MB = 420   # 0.9.7.50 had 470 MB (with the exe), slim ~401 MB
# data the program reads next to its code (Path(__file__).with_name) – PyInstaller only collects the .py of a package;
# 0.9.7 shipped without nicknames.json and every first sync failed (13.11.2026). build.ps1 adds them with --add-data.
REQUIRED = ("system/nicknames.json",)


def program_zip(path):
    """The program zip behind the starter (read in place, not copied)."""
    with open(path, "rb") as f:
        f.seek(-16, 2)
        tail = f.read(16)
        if tail[8:] != b"BCPAYLD1":
            raise ValueError(f"{path}: no program zip behind the starter")
        (length,) = struct.unpack("<q", tail[:8])
        end = f.tell() - 16
        f.seek(end - length)
        return zipfile.ZipFile(io.BytesIO(f.read(length)))


def entries(path):
    """-> [(name, unpacked bytes)] of a starter exe, a .zip or a folder (names with / as separator)."""
    p = pathlib.Path(path)
    if p.is_dir():
        return [(f.relative_to(p).as_posix(), f.stat().st_size) for f in sorted(p.rglob("*")) if f.is_file()]
    with (zipfile.ZipFile(p) if p.suffix.lower() == ".zip" else program_zip(p)) as z:
        return [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]


def forbidden_entries(path):
    """-> names in the package that must not be shipped."""
    return [n for n, _ in entries(path) if FORBIDDEN.search(n)]


def missing_entries(path):
    """-> REQUIRED files that are not in the package (under the program's own folder, any build-id prefix)."""
    names = [n for n, _ in entries(path)]
    return [r for r in REQUIRED if not any(n == r or n.endswith("/" + r) for n in names)]


def read_entry(path, name):
    """Bytes of one entry of a starter exe, a .zip or a folder."""
    p = pathlib.Path(path)
    if p.is_dir():
        return (p / name).read_bytes()
    with (zipfile.ZipFile(p) if p.suffix.lower() == ".zip" else program_zip(p)) as z:
        return z.read(name)


def brand_problems(path):
    """A Ship build (ship-sync.flag in the package) carries brand/ exactly as in the repository – never the red DEV
    mark (tools/make_dev_brand.py, Oliver 13.11.2026): no DEV.txt, every brand file byte-identical to brand/."""
    names = [n for n, _ in entries(path)]
    if not any(n == "ship-sync.flag" or n.endswith("/ship-sync.flag") for n in names):
        return []
    repo = pathlib.Path(__file__).resolve().parents[1] / "brand"
    out = []
    for n in names:
        i = n.find("brand/")
        if i < 0 or (i and n[i - 1] != "/"):
            continue
        rel = n[i + len("brand/"):]
        if rel == "DEV.txt":
            out.append(n + " (DEV mark)")
        elif (repo / rel).is_file() and read_entry(path, n) != (repo / rel).read_bytes():
            out.append(n + " (differs from brand/)")
    return out


def slim_entries(path):
    """-> names the slim build leaves out (build_launcher.SKIP) that are in the package anyway."""
    return [n for n, _ in entries(path) if re.search(SKIP, "/" + n)]


def size_mb(path):
    return sum(s for _, s in entries(path)) / 1e6


def main():
    bad = False
    for path in sys.argv[1:]:
        found = forbidden_entries(path)
        if found:
            print(f"{path}: darf nicht ins Paket:", *found, sep="\n  ")
            bad = True
        dev = brand_problems(path)
        if dev:
            print(f"{path}: Ship-Bau mit fremder/roter Marke:", *dev, sep="\n  ")
            bad = True
        gone = missing_entries(path)
        if gone:
            print(f"{path}: fehlt im Paket (build.ps1 --add-data):", *gone, sep="\n  ")
            bad = True
        back = slim_entries(path)
        if back:
            print(f"{path}: wieder drin, obwohl der schlanke Build es weglässt (Filter in tools/build_launcher.py SKIP "
                  f"nach einem Paket-Update anpassen):", *back[:40], sep="\n  ")
            bad = True
        mb = size_mb(path)
        print(f"{path}: {mb:.0f} MB Programmdateien (ausgepackt)")
        if mb > LIMIT_MB:
            print(f"WARNUNG: über {LIMIT_MB} MB – ist ein neues großes Paket dazugekommen? (tools/check_package.py)")
    if bad:
        sys.exit(1)
    print("Paket ohne DirectML/Timeline/VirtualKeyboard und ohne die weggelassenen Teile, mit allen nötigen Daten – ok")


if __name__ == "__main__":
    main()
