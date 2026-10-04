"""Turn a Stray Scanner recording into a point cloud (and test the pose convention).

Stray's docs do not state the camera convention. ARKit's camera.transform is
camera-to-world with the camera looking down -Z and +Y up (OpenGL style); the
alternative would be OpenCV (+Z forward, +Y down). Depth images are 256x192
and share the RGB field of view, so the RGB intrinsics are scaled by 256/1920.

    .venv/Scripts/python.exe scripts/stray_cloud.py data/stray/walk_loft_2026-10-04 --test
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

PIXEL_STEP = 4
VOXEL = 0.03


def quat_to_matrix(qx, qy, qz, qw):
    return np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
    ])


def load_odometry(folder: Path):
    d = np.genfromtxt(folder / "odometry.csv", delimiter=",", skip_header=1, usecols=range(13))
    return d  # timestamp, frame, x, y, z, qx, qy, qz, qw, fx, fy, cx, cy


def frame_points(folder: Path, row, convention: str):
    frame = int(row[1])
    depth = np.asarray(Image.open(folder / "depth" / f"{frame:06d}.png"), dtype=np.float64) / 1000.0
    conf = np.asarray(Image.open(folder / "confidence" / f"{frame:06d}.png"))
    h, w = depth.shape
    s = w / 1920.0
    fx, fy, cx, cy = row[9] * s, row[10] * s, row[11] * s, row[12] * s
    v, u = np.mgrid[0:h:PIXEL_STEP, 0:w:PIXEL_STEP]
    d = depth[v, u]
    ok = (conf[v, u] == 2) & (d > 0.2) & (d < 4.0)
    u, v, d = u[ok], v[ok], d[ok]
    x = (u - cx) / fx * d
    y = (v - cy) / fy * d
    if convention == "arkit":
        cam = np.c_[x, -y, -d]
    else:
        cam = np.c_[x, y, d]
    r = quat_to_matrix(*row[5:9])
    return cam @ r.T + row[2:5]


def build_cloud(folder: Path, convention: str, frame_step: int, min_phone_height=None):
    odo = load_odometry(folder)
    if min_phone_height is not None:
        odo = odo[odo[:, 3] > min_phone_height]
    pts = np.vstack([frame_points(folder, row, convention) for row in odo[::frame_step]])
    keys = np.floor(pts / VOXEL).astype(np.int64)
    _, idx = np.unique(keys, axis=0, return_index=True)
    return pts, pts[idx]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--test", action="store_true", help="compare the two pose conventions")
    parser.add_argument("--frame-step", type=int, default=6)
    parser.add_argument("--convention", choices=("arkit", "opencv"), default="opencv")
    parser.add_argument("--min-phone-height", type=float, default=None,
                        help="only frames with the phone above this Stray-world height (e.g. upper floor only)")
    parser.add_argument("--tag", default="", help="suffix for the output file")
    args = parser.parse_args()

    if args.test:
        for conv in ("arkit", "opencv"):
            pts, vox = build_cloud(args.folder, conv, frame_step=30)
            print(f"{conv:7s}: {len(pts):,} points occupy {len(vox):,} voxels of {VOXEL * 100:.0f} cm "
                  f"({len(vox) / len(pts) * 100:.1f}% - lower means the frames agree better); "
                  f"height range {np.percentile(pts[:, 1], 1):.2f}..{np.percentile(pts[:, 1], 99):.2f} m")
        return
    pts, vox = build_cloud(args.folder, args.convention, args.frame_step, args.min_phone_height)
    out = args.folder / f"cloud_{args.convention}{args.tag}_voxel3cm.npy"
    np.save(out, vox.astype(np.float32))
    print(f"{len(pts):,} points -> {len(vox):,} voxels saved to {out}")


if __name__ == "__main__":
    main()
