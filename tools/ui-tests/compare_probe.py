"""Compare two overlay_probe.py runs image by image: share of differing pixels (any channel off by more than 24).
With a second pair of runs it also shows the noise floor (base vs base, branch vs branch) – a difference only counts
if the same version doesn't show it against itself.

    python tools\\ui-tests\\compare_probe.py <base run> <branch run> [<base run 2> <branch run 2>]
"""
import pathlib
import sys

import cv2

THRESHOLD = 24


def diff(x, y):
    a, b = cv2.imread(str(x)), cv2.imread(str(y))
    if a is None or b is None or a.shape != b.shape:
        return None
    n = int((cv2.absdiff(a, b).max(axis=2) > THRESHOLD).sum())
    return 100.0 * n / (a.shape[0] * a.shape[1])


def main(args):
    base, branch = pathlib.Path(args[0]), pathlib.Path(args[1])
    base2, branch2 = (pathlib.Path(args[2]), pathlib.Path(args[3])) if len(args) >= 4 else (None, None)
    fmt = lambda v: "-" if v is None else f"{v:.3f}"   # noqa: E731
    print(f"{'step':22} {'base<->branch %':>14}" + (f" {'base<->base %':>12} {'branch<->branch %':>16}" if base2 else ""))
    above_noise = []
    for name in sorted(p.name for p in base.glob("*.png")):
        d = diff(base / name, branch / name)
        line = f"{name[:-4]:22} {fmt(d):>14}"
        if base2:
            nb, ns = diff(base / name, base2 / name), diff(branch / name, branch2 / name)
            line += f" {fmt(nb):>12} {fmt(ns):>16}"
            if d is None or d > max(nb or 0, ns or 0):
                above_noise.append(name[:-4])
        elif d is None or d > 0:
            above_noise.append(name[:-4])
        print(line)
    print("above noise:" if base2 else "different:", ", ".join(above_noise) or "none")
    return 1 if above_noise else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
