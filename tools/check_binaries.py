"""After PyInstaller: every DLL/.pyd in the exe must come from the build venv, the Python installation it is based on,
Windows itself or the project folder. Anything else was picked up by accident from the PATH (0.9.7.4: miniconda's
ucrtbase/api-ms-win-*/libcrypto via the PowerShell profile – 43 foreign DLLs in the exe). Exit 1 with the list.
build.ps1 runs it right after PyInstaller.

    .venv\\Scripts\\python tools\\check_binaries.py build\\BentCorner\\COLLECT-00.toc
"""
import ast
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def allowed_roots():
    roots = [sys.prefix, sys.base_prefix, os.environ.get("SystemRoot", r"C:\Windows"), str(ROOT)]
    return [os.path.normcase(os.path.realpath(r)) for r in roots]


def foreign(toc_path, roots=None):
    """-> [(name in the exe, source path)] of binaries from anywhere else."""
    roots = roots or allowed_roots()
    entries = ast.literal_eval(pathlib.Path(toc_path).read_text("utf-8"))[0]
    bad = []
    for name, src, kind in entries:
        if kind not in ("BINARY", "EXTENSION"):
            continue
        real = os.path.normcase(os.path.realpath(src))
        if not any(real == r or real.startswith(r + os.sep) for r in roots):
            bad.append((name, src))
    return bad


def main():
    bad = foreign(sys.argv[1])
    if bad:
        print("DLLs von außerhalb von venv/Python/Windows in der exe (PATH prüfen, z. B. conda/msys):")
        for name, src in bad:
            print(f"  {name}  <-  {src}")
        sys.exit(1)
    print("Bibliotheken nur aus venv/Python/Windows – ok")


if __name__ == "__main__":
    main()
