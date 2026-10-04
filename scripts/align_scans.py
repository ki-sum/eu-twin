"""Rigidly align a newer scan of the loft to the 2026-08-07 reference scan.

Extend Scan in 3D Scanner App re-localises against the old session but not
exactly. Trimmed ICP on surface samples: old samples are matched to the new
surface, only the closest 60 % of pairs are used per iteration (the new scan
contains the bathroom, which the old one lacks), and a Kabsch fit gives the
rotation and translation. The inverse maps the new scan into the old raw frame,
so the AP position and survey points stay valid.

    .venv/Scripts/python.exe scripts/align_scans.py data/scans/loft_with_bathroom_2026-10-03.usdz
"""

import sys
from pathlib import Path

import numpy as np
import trimesh
from pxr import Usd, UsdGeom
from scipy.spatial import cKDTree

REFERENCE = Path("data/scans/loft_scan_2026-08-07.usdz")
KEEP = 0.60
ITERATIONS = 600


def load_usdz(path: Path) -> trimesh.Trimesh:
    stage = Usd.Stage.Open(str(path))
    meshes = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        m = UsdGeom.Mesh(prim)
        pts = np.array(m.GetPointsAttr().Get(), dtype=np.float64)
        counts = np.array(m.GetFaceVertexCountsAttr().Get())
        idx = np.array(m.GetFaceVertexIndicesAttr().Get())
        faces, c = [], 0
        for n in counts:
            q = idx[c : c + n]
            faces += [[q[0], q[i], q[i + 1]] for i in range(1, n - 1)]
            c += n
        meshes.append(trimesh.Trimesh(pts, np.array(faces), process=False))
    return trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]


def kabsch(src, dst):
    cs, cd = src.mean(axis=0), dst.mean(axis=0)
    u, _, vt = np.linalg.svd((src - cs).T @ (dst - cd))
    d = np.sign(np.linalg.det(vt.T @ u.T))
    r = vt.T @ np.diag([1, 1, d]) @ u.T
    return r, cd - r @ cs


def main() -> None:
    new_path = Path(sys.argv[1])
    old = load_usdz(REFERENCE)
    new = load_usdz(new_path)
    src, _ = trimesh.sample.sample_surface(old, 150_000, seed=0)
    dst, _ = trimesh.sample.sample_surface(new, 600_000, seed=0)
    tree = cKDTree(dst)

    total_r, total_t = np.eye(3), np.zeros(3)
    cur = src.copy()
    for it in range(ITERATIONS):
        d, j = tree.query(cur)
        keep = d <= np.quantile(d, KEEP)
        r, t = kabsch(cur[keep], dst[j[keep]])
        cur = cur @ r.T + t
        total_r, total_t = r @ total_r, r @ total_t + t
        if it in (0, 99, 199, 299, 399, 499, ITERATIONS - 1):
            print(f"iter {it + 1:2d}: median {np.median(d) * 100:5.1f} cm, kept-pair median {np.median(d[keep]) * 100:4.1f} cm")

    d, _ = tree.query(cur)
    angle = np.degrees(np.arccos(np.clip((np.trace(total_r) - 1) / 2, -1, 1)))
    print(f"result: rotation {angle:.2f} deg, translation {np.round(total_t * 100, 1)} cm")
    print(f"old surface -> new surface after alignment: median {np.median(d) * 100:.1f} cm, "
          f"within 5 cm {np.mean(d < 0.05) * 100:.0f}%")

    # old -> new is x' = R x + t, so new -> old is x = R^T (x' - t)
    to_old = np.eye(4)
    to_old[:3, :3] = total_r.T
    to_old[:3, 3] = -total_r.T @ total_t
    out = Path("data/derived") / f"{new_path.stem}_to_reference.npy"
    np.save(out, to_old)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
