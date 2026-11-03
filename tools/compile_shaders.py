"""Compile the Qt Quick shaders (qml/shaders/*.frag -> *.frag.qsb) and note the source's checksum next to it
(*.frag.sha256 – tests/test_shaders.py checks that .frag and .qsb belong together).

qsb is not in PySide6-Essentials (dev\\.venv), only in PySide6-Addons – in its own tool venv, never in the build:
    <python> -m venv BentCorner\\tools\\qsb-venv
    BentCorner\\tools\\qsb-venv\\Scripts\\python -m pip install pyside6-addons==<same version as PySide6 in requirements.txt>
Then (in the project folder):
    .venv\\Scripts\\python tools\\compile_shaders.py [path\\to\\qsb.exe]
The .qsb files are committed – the build and the app don't need qsb.
"""
import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHADERS = ROOT / "qml" / "shaders"
DEFAULT_QSB = ROOT.parents[1] / "tools" / "qsb-venv" / "Lib" / "site-packages" / "PySide6" / "qsb.exe"
# GLSL for OpenGL (ES), HLSL for Direct3D, MSL for Metal – what Qt's RHI may use
TARGETS = ["--glsl", "100 es,120,150", "--hlsl", "50", "--msl", "12", "--qt6"]


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()   # same on every checkout


def main():
    qsb = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_QSB
    if not qsb.exists():
        sys.exit(f"qsb not found: {qsb} – see the text at the top of this file")
    for src in sorted(SHADERS.glob("*.frag")):
        out = src.with_suffix(".frag.qsb")
        subprocess.run([str(qsb), *TARGETS, "-o", str(out), str(src)], check=True)
        src.with_suffix(".frag.sha256").write_text(digest(src) + "\n", "utf-8")
        print(f"{out.name}: {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
