"""Pick walk-survey points on free floor and draw a numbered route map.

A cell counts as free floor when the scan sees the floor there, nothing in the
cell sits between 0.15 m and 1.3 m (furniture, desks, beds), and the ceiling is
higher than 1.4 m so a tripod at 1.0 m fits. Points are spread with farthest-
point sampling, a reference point R sits ~1.2 m from the AP, and the visiting
order is a short closed tour that starts and ends at R.
"""

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import trimesh
from scipy import ndimage

from locate_ap import aligned_frame
from view_scan import load_mesh

N_POINTS = 18
CELL = 0.10
SAMPLES = 2_000_000
CLEARANCE_CELLS = 1  # keep the tripod centre 10 cm away from furniture edges
REF_DISTANCE = 1.2
MIN_AP_DISTANCE = 0.8
AP_PATH = Path("data/derived/ap_location.npy")
OUT_PNG = Path("data/derived/survey_points.png")
OUT_CSV = Path("data/derived/survey_points.csv")


def free_floor_map(mesh_aligned):
    pts, _ = trimesh.sample.sample_surface(mesh_aligned, SAMPLES, seed=0)
    ix = (pts[:, 0] / CELL).astype(int)
    iz = (pts[:, 2] / CELL).astype(int)
    shape = (iz.max() + 1, ix.max() + 1)

    ceiling = np.full(shape, -np.inf)
    floor = np.full(shape, np.inf)
    np.maximum.at(ceiling, (iz, ix), pts[:, 1])
    np.minimum.at(floor, (iz, ix), pts[:, 1])
    band = (pts[:, 1] > 0.15) & (pts[:, 1] < 1.3)
    obstacle = np.zeros(shape, bool)
    obstacle[iz[band], ix[band]] = True

    seen = np.isfinite(ceiling)
    free = seen & (floor > -0.3) & (floor < 0.2) & ~obstacle & (ceiling > 1.4)
    free = ndimage.binary_erosion(free, iterations=CLEARANCE_CELLS)
    labels, n = ndimage.label(free)
    sizes = ndimage.sum(free, labels, range(1, n + 1))
    free = np.isin(labels, 1 + np.flatnonzero(sizes * CELL**2 >= 0.15))
    ceiling[~seen] = np.nan
    return free, ceiling


def farthest_point_sampling(cands, seeds, k):
    d = np.min(np.linalg.norm(cands[:, None, :] - seeds[None, :, :], axis=2), axis=1)
    chosen = []
    for _ in range(k):
        i = int(np.argmax(d))
        chosen.append(i)
        d = np.minimum(d, np.linalg.norm(cands - cands[i], axis=1))
    return cands[chosen]


def closed_tour(points):
    """Nearest-neighbour tour from points[0], improved with 2-opt; returns visiting order."""
    n = len(points)
    dist = np.linalg.norm(points[:, None] - points[None], axis=2)
    order = [0]
    left = set(range(1, n))
    while left:
        nxt = min(left, key=lambda j: dist[order[-1], j])
        order.append(nxt)
        left.remove(nxt)
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                a, b = order[i - 1], order[i]
                c, d = order[j], order[(j + 1) % n]
                if dist[a, c] + dist[b, d] < dist[a, b] + dist[c, d] - 1e-9:
                    order[i : j + 1] = order[i : j + 1][::-1]
                    improved = True
    return order


def main() -> None:
    raw = load_mesh()
    v, *_ = aligned_frame(raw)
    free, ceiling = free_floor_map(trimesh.Trimesh(v, raw.faces, process=False))
    ap = np.load(AP_PATH)
    ap_xz = ap[[0, 2]]

    iz, ix = np.nonzero(free)
    cands = np.c_[(ix + 0.5) * CELL, (iz + 0.5) * CELL]
    d_ap = np.linalg.norm(cands - ap_xz, axis=1)
    print(f"Free floor for the tripod: {free.sum() * CELL**2:.1f} m2")

    ref = cands[np.argmin(np.abs(d_ap - REF_DISTANCE))]
    pool = cands[d_ap >= MIN_AP_DISTANCE]
    points = farthest_point_sampling(pool, np.vstack([ref, ap_xz]), N_POINTS)
    order = closed_tour(np.vstack([ref, points]))
    route = np.vstack([ref, points])[order]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "press", "x_m", "z_m", "dist_to_ap_m", "ceiling_m"])
        for k, (x, z) in enumerate(route):
            c = ceiling[int(z / CELL), int(x / CELL)]
            label = "R" if k == 0 else str(k)
            w.writerow([label, k + 1, f"{x:.2f}", f"{z:.2f}", f"{np.hypot(x - ap_xz[0], z - ap_xz[1]):.2f}", f"{c:.2f}"])
        w.writerow(["R", len(route) + 1, f"{ref[0]:.2f}", f"{ref[1]:.2f}", f"{np.linalg.norm(ref - ap_xz):.2f}", ""])
    tour_len = np.sum(np.linalg.norm(np.diff(np.vstack([route, route[:1]]), axis=0), axis=1))
    print(f"{len(route) - 1} points + reference R, closed walk {tour_len:.1f} m")

    extent = [0, free.shape[1] * CELL, free.shape[0] * CELL, 0]
    fig, ax = plt.subplots(figsize=(8, 11))
    im = ax.imshow(np.clip(ceiling, 0, 3.2), cmap="viridis", extent=extent)
    ax.imshow(np.where(free, 1.0, np.nan), cmap="Greys", vmin=0, vmax=3, alpha=0.45, extent=extent)
    loop = np.vstack([route, route[:1]])
    ax.plot(loop[:, 0], loop[:, 1], "-", color="white", lw=1.5, alpha=0.9)
    ax.plot(*ap_xz, "*", ms=22, mfc="red", mec="black")
    ax.annotate("Router", ap_xz, xytext=(12, 12), textcoords="offset points", color="red", fontsize=12, fontweight="bold")
    for k, (x, z) in enumerate(route):
        label = "R" if k == 0 else str(k)
        face = "orange" if k == 0 else "white"
        ax.plot(x, z, "o", ms=20, mfc=face, mec="black", mew=1.5)
        ax.text(x, z, label, ha="center", va="center", fontsize=11, fontweight="bold")

    w_, d_ = free.shape[1] * CELL, free.shape[0] * CELL
    style = dict(fontsize=22, fontweight="bold", color="red", ha="center", va="center")
    ax.text(w_ / 2, -0.3, "A", **style)
    ax.text(w_ + 0.3, d_ / 2, "B", **style)
    ax.text(w_ / 2, d_ + 0.3, "C", **style)
    ax.text(-0.3, d_ / 2, "D", **style)
    ax.set_xlim(-0.6, w_ + 0.6)
    ax.set_ylim(d_ + 0.6, -0.6)
    ax.set_xlabel("metres")
    ax.set_ylabel("metres")
    ax.set_title("Walk survey route: start at R, then 1, 2, 3 ... and finish at R again\n"
                 "grey shade = free floor for the tripod, colour = ceiling height")
    fig.colorbar(im, ax=ax, shrink=0.5, label="ceiling height above floor (m)")
    fig.savefig(OUT_PNG, dpi=110, bbox_inches="tight")
    print(f"Saved {OUT_PNG} and {OUT_CSV}")


if __name__ == "__main__":
    main()
