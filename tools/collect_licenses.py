"""The full license texts of everything inside the exe, into licenses/ (build.ps1 bundles the folder; Settings → Legal →
Third-party notices shows it without internet). THIRD_PARTY_NOTICES.md points here – LGPL for Qt/PySide6, FFmpeg and
GEOS (legal 03.11.2026, P4), the Python, OpenCV and ONNX Runtime notices, and the license files of every bundled package.

    .venv\\Scripts\\python tools\\collect_licenses.py [target folder]     # default: licenses/ next to build.ps1

- tools/license-texts/: GPL-3.0, LGPL-3.0, LGPL-2.1 (FSF), Apache-2.0, Mesa 11.2.2 and LLVM 3.6.2 – unchanged (sha256 in TEXTS); Apache-2.0
  for the parts under it that ship no text of their own (RapidOCR, PaddleOCR models, FlatBuffers, DINOv2).
- From this Python and .venv: Python's LICENSE.txt, cv2's LICENSE-3RD-PARTY.txt, onnxruntime's ThirdPartyNotices.txt,
  and per installed package its license files – in its .dist-info or at the top of its own folder (onnxruntime/
  LICENSE) – except the build-only tools in BUILD_ONLY.
The folder is rebuilt each time (only this script writes into it); same .venv -> same bytes.
"""
import hashlib
import importlib.metadata
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXTS = {   # tools/license-texts/ – the FSF texts (gnu.org) and the Apache License (apache.org), verbatim
    "GPL-3.0.txt": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
    "LGPL-3.0.txt": "e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118",
    "LGPL-2.1.txt": "20e50fe7aae3e56378ebf0417d9de904f55a0e61e4df315333e632a4d3555d95",
    "Apache-2.0.txt": "aac73b3148f6d1d7111dbca32099f68d26c644c6813ae1e4f05f6579aa2663fe",
    # Qt's software OpenGL (opengl32sw.dll): Mesa 11.2.2 with LLVM 3.6.2 – the release texts, as plain text
    "Mesa-LICENSE.txt": "218cb50375faa3be87572127fca0d9242d0cbc48d20cdff0ec10890c8438afba",
    "LLVM-3.6.2-LICENSE.txt": "ae8b7982c2c4f9a7bcbb00e80ae584f6d2c6a6a7f3d43bdc7641ee60cdd84b54",
}
# in the .venv only to build the exe – PyInstaller doesn't put them into the program
BUILD_ONLY = {"pip", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile", "pywin32-ctypes"}
# installed as dependencies of other packages, but not in the program (checked in the 0.9.7.28 exe: none of their
# modules is in it – PyInstaller only packs what is imported);
# tests/test_collect_licenses.py: every package left in licenses/ has its line in THIRD_PARTY_NOTICES.md
NOT_BUNDLED = {"colorama", "mpmath", "protobuf", "pycparser", "six", "sympy", "tqdm"}
LICENSE_FILE = re.compile(r"(licen[cs]e|copying|notice|authors)", re.I)
# Qt's commercial terms come with the PySide6/shiboken6 wheels; Bent°Corner uses Qt under the LGPL-3.0 – leaving them
# out avoids suggesting otherwise
SKIP = {"LicenseRef-Qt-Commercial.txt"}
INDEX = """Full license texts of the components in Bent°Corner (overview: THIRD_PARTY_NOTICES.md)

GPL-3.0.txt, LGPL-3.0.txt   Qt and PySide6/Shiboken6 (LGPL-3.0, which builds on the GPL-3.0)
LGPL-2.1.txt                FFmpeg (cv2/opencv_videoio_ffmpeg*.dll) and GEOS (Shapely.libs/geos*.dll)
Apache-2.0.txt              RapidOCR, the PaddleOCR models, FlatBuffers, DINOv2 and the other Apache-2.0 parts
Mesa-LICENSE.txt, LLVM-3.6.2-LICENSE.txt  opengl32sw.dll (Qt's software OpenGL: Mesa llvmpipe with LLVM 3.6.2)
Python-LICENSE.txt          Python and the parts it bundles (expat, zlib, OpenSSL, SQLite, libffi …)
opencv-LICENSE-3RD-PARTY.txt  third-party code inside OpenCV
onnxruntime-ThirdPartyNotices.txt  third-party code inside ONNX Runtime
packages/<name>-<version>/  the license files each bundled Python package ships
"""


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def collect(target):
    target = pathlib.Path(target)
    if target.exists():
        shutil.rmtree(target)
    (target / "packages").mkdir(parents=True)
    for name, digest in TEXTS.items():
        src = ROOT / "tools" / "license-texts" / name
        data = src.read_bytes().replace(b"\r\n", b"\n")   # git may check text out with CRLF – the hash is of the LF text
        if hashlib.sha256(data).hexdigest() != digest:
            raise SystemExit(f"{src}: not the expected license text (sha256)")
        (target / name).write_bytes(data)
    shutil.copyfile(pathlib.Path(sys.base_prefix) / "LICENSE.txt", target / "Python-LICENSE.txt")
    dists = {_norm(d.metadata["Name"]): d for d in importlib.metadata.distributions()}
    for out, (dist, rel) in {"opencv-LICENSE-3RD-PARTY.txt": ("opencv-python", "cv2/LICENSE-3RD-PARTY.txt"),
                             "onnxruntime-ThirdPartyNotices.txt": ("onnxruntime-directml",
                                                                   "onnxruntime/ThirdPartyNotices.txt")}.items():
        src = pathlib.Path(dists[dist].locate_file(rel))
        if not src.exists():
            raise SystemExit(f"missing: {src}")
        shutil.copyfile(src, target / out)
    top = {p.read_bytes() for p in target.iterdir() if p.is_file()}
    n = 0
    for key in sorted(dists):
        if key in BUILD_ONLY or key in NOT_BUNDLED:
            continue
        d = dists[key]
        files = sorted({f for f in (d.files or []) if LICENSE_FILE.search(f.name) and f.name not in SKIP
                        and (".dist-info/" in f.as_posix() or len(f.parts) == 2)}, key=str)
        if not files:
            continue
        folder = target / "packages" / f"{key}-{d.version}"
        for f in files:
            src = pathlib.Path(d.locate_file(f))
            if src.is_file() and src.read_bytes() not in top:   # not twice (cv2's and onnxruntime's notices are above)
                # path below the .dist-info / package folder: numpy has a LICENSE per bundled library
                dest = folder.joinpath(*[p for p in f.parts[1:] if p != "licenses"] or [f.name])
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                n += 1
    (target / "README.txt").write_text(INDEX, "utf-8")
    return n


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "licenses"
    count = collect(out)
    print(f"licenses: {len(list(out.rglob('*')))} entries ({count} package license files) in {out}")
