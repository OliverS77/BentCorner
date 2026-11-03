"""Checks a finished dist\\BentCorner.exe (starter + program zip behind it): nothing in it that must not be shipped.
build.ps1 runs it after tools\\build_launcher.py; exit 1 with the list.

- DirectML*.dll: the app uses the DirectML from Windows itself (scanner/accel.py) – we ship no proprietary GPU
  library (signing/open source, 0.9.7.4).
- Qt Quick Timeline and Qt Virtual Keyboard: unused, and freely available only under the GPL (legal, 0.9.7.5) –
  tools/build_launcher.py leaves them out (SKIP_QML).

    .venv\\Scripts\\python tools\\check_package.py dist\\BentCorner.exe
"""
import io
import re
import struct
import sys
import zipfile

FORBIDDEN = re.compile(r"(^|/)(directml[^/]*\.dll|qt6quicktimeline[^/]*\.dll|qt6virtualkeyboard[^/]*\.dll)$"
                       r"|/qml/qtquick/(timeline|virtualkeyboard)/", re.I)


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


def forbidden_entries(path):
    """-> names in the program zip that must not be shipped."""
    with program_zip(path) as z:
        return [n for n in z.namelist() if FORBIDDEN.search(n)]


def main():
    found = forbidden_entries(sys.argv[1])
    if found:
        print("Darf nicht ins Paket:", *found, sep="\n  ")
        sys.exit(1)
    print("Paket ohne DirectML/Timeline/VirtualKeyboard – ok")


if __name__ == "__main__":
    main()
