"""Baut dist\\BentCorner.exe: den Starter (launcher\\Launcher.cs, mit dem csc.exe aus Windows übersetzt) und dahinter
das Programm aus dist\\BentCorner\\ (PyInstaller-Ordner) als Zip.

    [Starter][payload.zip][8 Byte Länge][8 Byte "BCPAYLD1"]

Der Starter legt das Programm einmal je Build in „Bent°Corner Essentials“ (neben den Daten) ab – deshalb bekommt
jeder Build eine eigene Kennung (Version + Zeitstempel).
"""
import datetime
import os
import pathlib
import re
import struct
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import version  # noqa: E402

CSC = pathlib.Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
FW = CSC.parent
SRC = ROOT / "launcher" / "Launcher.cs"
DIST = ROOT / "dist"
APP = DIST / "BentCorner"          # PyInstaller --onedir
BUILD = ROOT / "build" / "launcher"
OUT = DIST / "BentCorner.exe"
# QML-Bausteine, die unsere Oberfläche nicht nutzt (sie importiert nur QtQuick, .Effects, .Shapes, .Window) – kleiner
# und vor allem kürzere Pfade (die Bilder von QtQuick.Controls kommen sonst an Windows' 260-Zeichen-Grenze)
# Qt Quick Timeline / Virtual Keyboard also as libraries: unused, and freely available only under the GPL (legal,
# 0.9.7.5) – tools/check_package.py makes sure they stay out
SKIP_QML = (r"/PySide6/(qml/(QtTest|QtQuick/(Controls|Dialogs|NativeStyle|Templates|VirtualKeyboard|"
            r"Particles|Timeline|LocalStorage|tooling|VectorImage))/|Qt6(QuickTimeline|VirtualKeyboard)[^/]*\.dll$)")


def _write_lockup(path):
    """Bent°Corner long version (ui/iconkit.lockup_image) as PNG for the launcher splash – offscreen Qt."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT))
    from PySide6 import QtGui
    _app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication(["launcher"])
    from ui import iconkit
    from ui import look
    look.register_fonts()
    img, _w, _h = iconkit.lockup_image(21, "dark", k=2)
    img.save(str(path))


def _brand():
    """(icon, logo card or None, brand present) – brand/ (ui/brand.py); without it the placeholder icon build.ps1 wrote
    into build/ and no lockup picture (the splash then shows the name as text)."""
    sys.path.insert(0, str(ROOT))
    from ui import brand
    icon = brand.folder() / "icon.ico" if brand.present() else ROOT / "build" / "icon.ico"   # build.ps1 wrote it
    return icon, brand.load_card(), brand.present()


def main():
    if not (APP / "BentCorner.exe").exists():
        sys.exit("dist\\BentCorner\\BentCorner.exe fehlt – erst PyInstaller (--onedir)")
    BUILD.mkdir(parents=True, exist_ok=True)
    # die Kennung, mit der PyInstaller gebaut hat (build.ps1: --contents-directory <Kennung>): so heißt der Ordner der
    # Programmdateien, und so legt ihn der Starter in „Essentials“ ab (die kleine BentCorner.exe an festem Ort daneben)
    build_id = os.environ.get("BC_BUILD_ID") or f"{version.VERSION}-{datetime.datetime.now().strftime('%y%m%d%H%M')}"
    if not (APP / build_id).is_dir():
        sys.exit(f"dist\\BentCorner\\{build_id} fehlt – PyInstaller mit --contents-directory {build_id} bauen (build.ps1)")
    skip = re.compile("^" + re.escape(build_id) + SKIP_QML)
    nums = (re.findall(r"\d+", version.VERSION) + ["0"] * 4)[:4]
    icon, card, has_brand = _brand()
    from ui import brand
    name = brand.NAME.encode("ascii", "backslashreplace").decode().replace("\\x", "\\u00")   # C# \u00B0
    info = BUILD / "BuildInfo.cs"
    info.write_text(
        "using System.Reflection;\n"
        f'[assembly: AssemblyTitle("Bent\\u00B0Corner")]\n'
        f'[assembly: AssemblyProduct("Bent\\u00B0Corner")]\n'
        f'[assembly: AssemblyDescription("Bent\\u00B0Corner – Karten scannen, sammeln, tauschen")]\n'
        f'[assembly: AssemblyVersion("{".".join(nums)}")]\n'
        f'[assembly: AssemblyFileVersion("{".".join(nums)}")]\n'
        f'[assembly: AssemblyInformationalVersion("{version.VERSION}")]\n'
        "static class BuildInfo {\n"
        f'    public const string Id = "{build_id}";\n'
        "}\n"
        "static class BrandInfo {   // the first loading card: the logo card (brand/loadcard.json) – or random\n"
        f"    public const bool LogoCard = {'true' if card else 'false'};\n"
        f"    public const int Corner = {card['corner'] if card else 0};\n"
        f"    public const float Fold = {card['fold'] if card else 0}f;\n"
        f"    public const double Tilt = {card['tilt'] if card else 0};\n"
        f"    public const string Name = \"{name}\";   // ui/brand.NAME – the one display name\n"
        "}\n", "utf-8-sig")
    stub = BUILD / "Launcher.exe"
    lockup = BUILD / "Lockup.png"   # the brand for the splash: long version, light on dark, 2× sharp
    if has_brand:
        _write_lockup(lockup)
    cmd = [str(CSC), "/nologo", "/optimize+", "/target:winexe", "/platform:x64", f"/out:{stub}",
           f"/win32icon:{icon}", *([f"/resource:{lockup},Lockup.png"] if has_brand else []),
           f"/r:{FW / 'System.IO.Compression.dll'}", "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll",
           str(SRC), str(info)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="oem", errors="replace")
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        sys.exit("csc fehlgeschlagen")

    payload = BUILD / "payload.zip"
    files = sorted(p for p in APP.rglob("*") if p.is_file() and not skip.search(p.relative_to(APP).as_posix()))
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, p.relative_to(APP).as_posix())
    size = payload.stat().st_size
    with open(OUT, "wb") as out:
        out.write(stub.read_bytes())
        with open(payload, "rb") as f:
            while block := f.read(1 << 22):
                out.write(block)
        out.write(struct.pack("<q", size) + b"BCPAYLD1")
    print(f"Starter: {OUT} ({OUT.stat().st_size / 1e6:.0f} MB, {len(files)} Dateien, Kennung {build_id})")


if __name__ == "__main__":
    main()
