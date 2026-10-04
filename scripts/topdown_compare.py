"""Top-down map of a newer loft scan, with the area it adds over the reference scan outlined.

    .venv/Scripts/python.exe scripts/topdown_compare.py data/scans/loft_with_bathroom_2026-10-03.usdz
"""

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import trimesh
from scipy import ndimage

from align_scans import REFERENCE
from scan_frame import load_aligned

CELL = 0.05


def ceiling_map(mesh, shape=None, origin=(0.0, 0.0)):
    pts, _ = trimesh.sample.sample_surface(mesh, 3_000_000, seed=0)
    ix = ((pts[:, 0] - origin[0]) / CELL).astype(int)
    iz = ((pts[:, 2] - origin[1]) / CELL).astype(int)
    ok = (ix >= 0) & (iz >= 0) & (ix < shape[1]) & (iz < shape[0]) & (pts[:, 1] > -0.3)
    ceil = np.full(shape, np.nan)
    np.fmax.at(ceil, (iz[ok], ix[ok]), pts[ok, 1])
    return ceil


def main() -> None:
    scan = Path(sys.argv[1])
    new = load_aligned(scan)
    old = load_aligned(REFERENCE)
    lo = np.minimum(new.bounds[0], old.bounds[0])
    hi = np.maximum(new.bounds[1], old.bounds[1])
    origin = (lo[0], lo[2])
    shape = (int((hi[2] - lo[2]) / CELL) + 1, int((hi[0] - lo[0]) / CELL) + 1)
    c_new = ceiling_map(new, shape, origin)
    c_old = ceiling_map(old, shape, origin)

    seen_old = ndimage.binary_closing(np.isfinite(c_old), iterations=3)
    added = np.isfinite(c_new) & ~ndimage.binary_dilation(seen_old, iterations=4)
    added = ndimage.binary_opening(added, iterations=2)
    print(f"Area seen only in the new scan: {added.sum() * CELL**2:.1f} m2")

    extent = [lo[0], lo[0] + shape[1] * CELL, lo[2] + shape[0] * CELL, lo[2]]
    fig, ax = plt.subplots(figsize=(9, 11))
    im = ax.imshow(np.clip(c_new, 0, 3.2), cmap="viridis", extent=extent)
    xs = origin[0] + (np.arange(shape[1]) + 0.5) * CELL
    zs = origin[1] + (np.arange(shape[0]) + 0.5) * CELL
    ax.contour(xs, zs, added.astype(float), levels=[0.5], colors="red", linewidths=2.5)
    ap = np.load("data/derived/ap_location.npy")
    ax.plot(ap[0], ap[2], "*", ms=22, mfc="red", mec="black")
    for r in csv.DictReader(open("data/derived/survey_points.csv")):
        ax.plot(float(r["x_m"]), float(r["z_m"]), "o", ms=13, mfc="white", mec="black")
        ax.text(float(r["x_m"]), float(r["z_m"]), r["label"], ha="center", va="center", fontsize=7, fontweight="bold")
    style = dict(fontsize=22, fontweight="bold", color="red", ha="center", va="center")
    ax.text((extent[0] + extent[1]) / 2, extent[3] - 0.35, "A", **style)
    ax.text(extent[1] + 0.35, (extent[2] + extent[3]) / 2, "B", **style)
    ax.text((extent[0] + extent[1]) / 2, extent[2] + 0.35, "C", **style)
    ax.text(extent[0] - 0.35, (extent[2] + extent[3]) / 2, "D", **style)
    ax.set_xlim(extent[0] - 0.7, extent[1] + 0.7)
    ax.set_ylim(extent[2] + 0.7, extent[3] - 0.7)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("z (m)")
    ax.set_title("New scan, top view - colour: ceiling height\nred outline: area that only the new scan covers")
    fig.colorbar(im, ax=ax, shrink=0.5, label="ceiling height above floor (m)")
    out = Path("data/derived") / f"topdown_{scan.stem}.png"
    fig.savefig(out, dpi=100, bbox_inches="tight")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
