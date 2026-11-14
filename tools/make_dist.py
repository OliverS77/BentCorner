"""The two ways to ship besides the old single exe (labs/installer/PLAN.md): the installer and the portable ZIP.

    .venv\\Scripts\\python tools\\make_dist.py          (build.ps1 runs it after the starter)

1. dist\\app-stage\\  – the PyInstaller folder without what must never ship (the same SKIP list the starter uses:
   Qt Quick Timeline / Virtual Keyboard, freely available only under the GPL) – checked like check_package.py.
2. dist\\BentCorner-<version>-portable.zip – that folder as "Bent°Corner\\…"; unpacked anywhere it runs portable
   (data next to it, never replaces itself – net/updater.distribution()).
3. dist\\BentCorner-Setup-<version>.exe – Inno Setup (installer\\bentcorner.iss), if ISCC.exe is installed; without it
   (a fork, a PC without Inno) only the ZIP, with a note.

Signing (Certum, cloud signing – the key never lies on this PC or in the repo): BC_SIGN = the command that signs one
file, with $f for the file, e.g.
    signtool sign /sha1 <certificate thumbprint> /fd sha256 /tr http://time.certum.pl /td sha256 $f
Set: BentCorner.exe is signed before the ZIP and the setup take it, ISCC signs the setup and unins000.exe with the
same command, and all of them are checked (signtool verify /pa). Unset: unsigned, with a note.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import version  # noqa: E402
from build_launcher import APP, SKIP  # noqa: E402
from check_package import FORBIDDEN  # noqa: E402

DIST = ROOT / "dist"
STAGE = DIST / "app-stage"
ISCC = [pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        pathlib.Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        pathlib.Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe"]


def build_id():
    bid = os.environ.get("BC_BUILD_ID")
    if bid and (APP / bid).is_dir():
        return bid
    dirs = [d.name for d in APP.iterdir() if d.is_dir() and re.match(r"\d+\.\d+", d.name)]
    if len(dirs) != 1:
        sys.exit(f"dist\\BentCorner: expected one program folder <version>-<time>, found {dirs}")
    return dirs[0]


def stage():
    """dist\\app-stage = the program folder without the files the starter leaves out. -> number of files."""
    if not (APP / "BentCorner.exe").exists():
        sys.exit("dist\\BentCorner\\BentCorner.exe missing – first PyInstaller (build.ps1)")
    skip = re.compile("^" + re.escape(build_id()) + SKIP)
    if STAGE.exists():
        shutil.rmtree(STAGE)
    n = 0
    for p in sorted(APP.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(APP).as_posix()
        if skip.search(rel):
            continue
        if FORBIDDEN.search(rel):
            sys.exit(f"must not ship: {rel}")
        dest = STAGE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        n += 1
    return n


SIGN = os.environ.get("BC_SIGN", "").strip()


def signtool():
    """signtool.exe for verifying: on the PATH or the newest Windows SDK."""
    found = shutil.which("signtool")
    if found:
        return found
    kits = sorted(pathlib.Path(os.environ.get("ProgramFiles(x86)", "")).glob("Windows Kits/10/bin/*/x64/signtool.exe"))
    return str(kits[-1]) if kits else None


def sign(path):
    """Sign one file with BC_SIGN and check it – a release is never half signed."""
    r = subprocess.run(SIGN.replace("$f", f'"{path}"'), shell=True, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit(f"signing failed: {path}")
    verify(path)


def verify(path):
    tool = signtool()
    if tool is None:
        sys.exit("signtool.exe not found (Windows SDK) – cannot check the signature")
    r = subprocess.run([tool, "verify", "/pa", str(path)], capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit(f"signature not valid: {path}")


def portable_zip():
    out = DIST / f"BentCorner-{version.VERSION}-portable.zip"
    out.unlink(missing_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(STAGE.rglob("*")):
            if p.is_file():
                z.write(p, "Bent°Corner/" + p.relative_to(STAGE).as_posix())
    return out


def setup():
    iscc = next((p for p in ISCC if p.exists()), None)
    if iscc is None:
        print("Inno Setup (ISCC.exe) not found – no installer built, only the portable ZIP")
        return None
    icon = ROOT / "brand" / "icon.ico" if (ROOT / "brand" / "icon.ico").exists() else ROOT / "build" / "icon.ico"
    signing = ["/DSign", "/Sbcsign=" + SIGN] if SIGN else []
    # wizard images from the brand (0.9.9): a Ship build (build.ps1 wrote build\ship-sync.flag) always the normal brand,
    # a work build the red DEV copy if build.ps1 made one – a stale brand-dev never reaches a Ship build
    ship = (ROOT / "build" / "ship-sync.flag").exists()
    brand = ROOT / "build" / "brand-dev" if not ship and (ROOT / "build" / "brand-dev" / "logo").is_dir() else ROOT / "brand"
    images = ROOT / "build" / "setup-images"
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_setup_images.py"), str(images), str(brand)], check=True,
                   env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    pics = ([f"/DSmallImage={images / 'setup-small.png'}", f"/DBigImage={images / 'setup-big.png'}"]
            if (images / "setup-small.png").exists() else [])
    r = subprocess.run([str(iscc), "/Q", f"/DAppVersion={version.VERSION}", f"/DSrcDir={STAGE}", f"/DIconFile={icon}",
                        f"/DOutDir={DIST}", *signing, *pics, str(ROOT / "installer" / "bentcorner.iss")],
                       capture_output=True, text=True, encoding="oem", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:])
        sys.exit("Inno Setup failed")
    out = DIST / f"BentCorner-Setup-{version.VERSION}.exe"
    if SIGN:
        verify(out)   # unins000.exe is signed by ISCC inside the setup (SignedUninstaller) – checked after installing
    return out


def main():
    n = stage()
    if SIGN:
        sign(STAGE / "BentCorner.exe")
    else:
        print("BC_SIGN not set – BentCorner.exe, the setup and unins000.exe stay unsigned")
    z = portable_zip()
    print(f"portable: {z} ({z.stat().st_size / 1e6:.0f} MB, {n} files)")
    s = setup()
    if s:
        print(f"installer: {s} ({s.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
