"""Align a Stray Scanner point cloud to the loft model (aligned frame).

Both clouds are gravity-aligned with Y up, so only yaw and translation are
searched: every 5 degrees of yaw, a short trimmed ICP from a centroid-matched
start, then a long trimmed ICP (full rigid) from the best candidate.
Writes <folder>/to_aligned_<convention>.npy (4x4, Stray world -> aligned frame).

    .venv/Scripts/python.exe scripts/stray_align.py data/stray/walk_loft_2026-10-04 opencv
"""

import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from align_scans import kabsch
from scan_frame import load_aligned

REFERENCE_SCAN = Path("data/scans/loft_with_bathroom_2026-10-03.usdz")
KEEP = 0.6
YAW_ONLY = len(sys.argv) > 5 and sys.argv[5] == "yaw"  # gravity-aligned: forbid tilt


def kabsch_yaw(src, dst):
    """Best rotation about the vertical (Y) axis plus translation."""
    cs, cd = src.mean(axis=0), dst.mean(axis=0)
    a, b = (src - cs)[:, [0, 2]], (dst - cd)[:, [0, 2]]
    u, _, vt = np.linalg.svd(a.T @ b)
    r2 = vt.T @ np.diag([1, np.sign(np.linalg.det(vt.T @ u.T))]) @ u.T
    r = np.array([[r2[0, 0], 0, r2[0, 1]], [0, 1, 0], [r2[1, 0], 0, r2[1, 1]]])
    return r, cd - r @ cs


def trimmed_icp(src, tree, dst, r, t, iterations, tol=1e-4, max_dist=1.0):
    """Trimmed ICP; neighbours further than max_dist count as unmatched (keeps k-d queries fast)."""
    prev = np.inf
    for _ in range(iterations):
        cur = src @ r.T + t
        d, j = tree.query(cur, distance_upper_bound=max_dist, workers=-1)
        ok = np.isfinite(d)
        if ok.sum() < 100:
            break
        med = np.median(np.where(ok, d, max_dist))
        if prev - med < tol:
            break
        prev = med
        keep = ok & (d <= np.quantile(d[ok], KEEP))
        dr, dt = (kabsch_yaw if YAW_ONLY else kabsch)(cur[keep], dst[j[keep]])
        r, t = dr @ r, dr @ t + dt
    d, _ = tree.query(src @ r.T + t, distance_upper_bound=max_dist, workers=-1)
    return r, t, np.where(np.isfinite(d), d, max_dist)


def yaw_matrix(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def main() -> None:
    folder, conv = Path(sys.argv[1]), sys.argv[2]
    tag = sys.argv[3] if len(sys.argv) > 3 else ""
    cloud = np.load(folder / f"cloud_{conv}{tag}_voxel3cm.npy").astype(np.float64)
    ref_mesh = trimesh.load(sys.argv[4], process=False) if len(sys.argv) > 4 else load_aligned(REFERENCE_SCAN)
    ref, _ = trimesh.sample.sample_surface(ref_mesh, 800_000, seed=0)
    tree = cKDTree(ref)
    rng = np.random.default_rng(0)
    coarse = cloud[rng.choice(len(cloud), 5_000, replace=False)]
    small_ref = ref[rng.choice(len(ref), 200_000, replace=False)]
    small_tree = cKDTree(small_ref)

    # floor: first dense height level from below
    y_shift = -np.percentile(cloud[:, 1], 2) + np.percentile(ref[:, 1], 2)

    def try_yaw(deg, iterations):
        r = yaw_matrix(np.radians(deg))
        rotated = coarse @ r.T
        t = np.r_[ref[:, 0].mean() - rotated[:, 0].mean(), y_shift, ref[:, 2].mean() - rotated[:, 2].mean()]
        r2, t2, d = trimmed_icp(coarse, small_tree, small_ref, r, t, iterations, max_dist=0.8)
        return np.median(d), deg, r2, t2

    best = min((try_yaw(deg, 8) for deg in range(0, 360, 10)), key=lambda b: b[0])
    print(f"[{conv}] coarse: yaw {best[1]} deg, median distance {best[0] * 100:.1f} cm", flush=True)
    best = min((try_yaw(deg, 15) for deg in range(best[1] - 10, best[1] + 11, 2)), key=lambda b: b[0])
    print(f"[{conv}] refined start: yaw {best[1]} deg, median distance {best[0] * 100:.1f} cm", flush=True)
    fine = cloud[rng.choice(len(cloud), min(50_000, len(cloud)), replace=False)]
    r, t, d = trimmed_icp(fine, tree, ref, best[2], best[3], 150, tol=2e-5, max_dist=0.5)
    tilt = np.degrees(np.arccos(np.clip(r[1, 1], -1, 1)))
    print(f"[{conv}] final: median distance {np.median(d) * 100:.1f} cm, within 5 cm {np.mean(d < 0.05) * 100:.0f}%, "
          f"tilt of up axis {tilt:.2f} deg")
    m = np.eye(4)
    m[:3, :3], m[:3, 3] = r, t
    np.save(folder / f"to_aligned_{conv}.npy", m)


if __name__ == "__main__":
    main()
