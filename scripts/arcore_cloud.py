"""Turn an EU Twin Recorder (Android/ARCore) walk into a point cloud for stray_align.py.

ARCore camera poses are OpenGL style (+X right, +Y up, camera looks down -Z,
relative to the image readout), world frame gravity-aligned with +Y up. Depth
images are uint16 millimetres at 160x120 and share the CPU image's field of
view, so the 640x480 image intrinsics are scaled by depth_width / image_width.

    .venv/Scripts/python.exe scripts/arcore_cloud.py data/android/walk_p30_2026-10-04
    .venv/Scripts/python.exe scripts/stray_align.py data/android/walk_p30_2026-10-04 arcore "" \
        data/stray/walk_house_2026-10-04/tsdf_mesh_aligned.ply yaw
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np

from stray_cloud import quat_to_matrix

PIXEL_STEP = 2
VOXEL = 0.03


def main() -> None:
    folder = Path(sys.argv[1])
    meta = json.loads((folder / "meta.json").read_text())
    s = meta["depth_width"] / meta["image_width"]
    fx, fy = meta["image_fx"] * s, meta["image_fy"] * s
    cx, cy = meta["image_cx"] * s, meta["image_cy"] * s
    w, h = meta["depth_width"], meta["depth_height"]
    v, u = np.mgrid[0:h:PIXEL_STEP, 0:w:PIXEL_STEP]

    pts = []
    for row in csv.DictReader(open(folder / "depth.csv")):
        d = np.fromfile(folder / "depth" / f"{int(row['index']):06d}.bin", dtype="<u2").reshape(h, w)
        d = d[v, u] / 1000.0
        ok = (d > 0.2) & (d < 4.0)
        x = (u[ok] - cx) / fx * d[ok]
        y = (v[ok] - cy) / fy * d[ok]
        cam = np.c_[x, -y, -d[ok]]
        r = quat_to_matrix(*(float(row[k]) for k in ("qx", "qy", "qz", "qw")))
        t = np.array([float(row[k]) for k in ("tx", "ty", "tz")])
        pts.append(cam @ r.T + t)
    pts = np.vstack(pts)
    keys = np.floor(pts / VOXEL).astype(np.int64)
    _, idx = np.unique(keys, axis=0, return_index=True)
    out = folder / "cloud_arcore_voxel3cm.npy"
    np.save(out, pts[idx].astype(np.float32))
    print(f"{len(pts):,} points -> {len(idx):,} voxels saved to {out}; "
          f"height range {np.percentile(pts[:, 1], 1):.2f}..{np.percentile(pts[:, 1], 99):.2f} m")


if __name__ == "__main__":
    main()
