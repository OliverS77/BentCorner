"""Writes docs/web/sphere-vectors.json: the pairing sphere (ui/sphere.py) for the web's JS port.

Exact (must match bit for bit): cells, ORDER, strip_values, the arc table samples (LENGTH, PITCH).
With a tolerance (float32 here, float64 in JS – shape borders may tip by one pixel):
  texture  per row the ink runs [start, end) of the band picture (S=48); "max_diff" pixels may differ in all
  render   per angle a grid of sample pixels inside 0.95 radius (the outline is drawn by cv2 – not compared) and
           the mean of all pixels inside it; each sample within "tol" grey levels

    python tools/make_sphere_vectors.py
"""
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui import sphere  # noqa: E402

OUT = ROOT / "docs" / "web" / "sphere-vectors.json"
PAYLOADS = ["0001020304050607", "a5f00f5a3cc39669", "ffffffffffffffff"]
ANGLES = [0.0, 0.5, 2.0, 4.0]
SIZE = 300
GRID = 21


def runs(row):
    """A row of 0/1 -> [[start, end), …] of the 1s."""
    d = np.diff(np.concatenate([[0], (row > 0.5).astype(np.int8), [0]]))
    return [[int(a), int(b)] for a, b in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0])]


def samples(img, radius):
    """A GRID × GRID lattice of points over the sphere, those inside 0.95 radius: [[x, y, grey]]."""
    out = []
    c = SIZE / 2
    for gy in range(GRID):
        for gx in range(GRID):
            x = int(round(c - radius + (gx + 0.5) * 2 * radius / GRID))
            y = int(round(c - radius + (gy + 0.5) * 2 * radius / GRID))
            if (x + 0.5 - c) ** 2 + (y + 0.5 - c) ** 2 < (0.95 * radius) ** 2:
                out.append([x, y, int(img[y, x])])
    return out


def build():
    radius = SIZE * 270 / 640
    cases = []
    for hexp in PAYLOADS:
        payload = bytes.fromhex(hexp)
        tex = sphere.texture(payload)
        renders = []
        for rot in ANGLES:
            img = sphere.render(tex, rot, size=SIZE, radius=radius)
            ys, xs = np.mgrid[0:SIZE, 0:SIZE]
            inner = (xs + 0.5 - SIZE / 2) ** 2 + (ys + 0.5 - SIZE / 2) ** 2 < (0.95 * radius) ** 2
            renders.append({"rot": rot, "mean_inner": round(float(img[inner].mean()), 3),
                            "samples": samples(img, radius)})
        cases.append({"payload": hexp, "cells": sphere.cells(payload), "strip_values": sphere.strip_values(payload),
                      "texture": {"S": 48, "width": int(tex.shape[1]), "height": int(tex.shape[0]),
                                  "ink": int(tex.sum()), "rows": [runs(r) for r in tex]},
                      "render": renders})
    idx = np.linspace(0, len(sphere.T_TAB) - 1, 21).astype(int)
    return {"about": "Pairing sphere (ui/sphere.py, PAIRING.md §2) for the JS port. Exact: cells, order, "
                     "strip_values, arc samples. texture: ink runs per row, at most max_diff pixels may differ. "
                     "render: size 300, radius 300*270/640, fg 230 bg 24, rot in rad; samples [x, y, grey] within "
                     "tol, mean_inner within tol_mean (outline excluded: drawn by cv2).",
            "consts": {"PERIOD": sphere.PERIOD, "FPS": sphere.FPS, "TURNS": sphere.TURNS, "TH0": sphere.TH0,
                       "TH1": sphere.TH1, "TILT": sphere.TILT, "N": sphere.N, "BW": sphere.BW,
                       "V_DATA": sphere.V_DATA, "V_FEED": sphere.V_FEED, "EDGE": sphere.EDGE,
                       "F5": sphere.F5, "KINDS": list(sphere.KINDS), "arc_table_points": len(sphere.T_TAB),
                       "band": {k: getattr(sphere._Band, k) for k in ("dot", "ring", "neck", "rneck", "rt", "band")}},
            "order": [int(x) for x in sphere.ORDER],
            "arc": {"length": float(sphere.LENGTH), "pitch": float(sphere.PITCH),
                    "samples": [[float(sphere.T_TAB[i]), float(sphere.S_TAB[i])] for i in idx]},
            "tolerance": {"max_diff": 400, "tol": 12, "tol_mean": 1.0},
            "size": SIZE, "cases": cases}


def main():
    OUT.write_text(json.dumps(build(), separators=(",", ":")) + "\n", "utf-8")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
