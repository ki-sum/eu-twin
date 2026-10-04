"""Shared coordinate frame for every scan of the loft.

The "aligned frame" (walls along X/Z, Y up, floor at y=0, X/Z offset so the
2026-08-07 scan starts at 0) is defined once from the reference scan, exactly
as scripts/locate_ap.py builds it. Later scans are first mapped into the
reference scan's raw frame with the rigid transform from scripts/align_scans.py,
then through the same reference transform, so the AP position and survey
points stay valid for them.
"""

from pathlib import Path

import numpy as np
import trimesh

from align_scans import REFERENCE, load_usdz
from topdown_map import FLOOR_Y, dominant_wall_yaw

FRAME_PATH = Path("data/derived/reference_frame.npy")


def reference_transform() -> np.ndarray:
    """4x4 matrix: reference scan raw coordinates -> aligned frame."""
    if FRAME_PATH.exists():
        return np.load(FRAME_PATH)
    mesh = load_usdz(REFERENCE)
    yaw = dominant_wall_yaw(mesh)
    c, s = np.cos(-yaw), np.sin(-yaw)
    rot = np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])
    v = mesh.vertices @ rot.T
    v[:, 1] -= FLOOR_Y
    offset = np.array([v[:, 0].min(), 0.0, v[:, 2].min()])
    t = np.eye(4)
    t[:3, :3] = rot
    t[:3, 3] = -offset + np.array([0.0, -FLOOR_Y, 0.0])
    np.save(FRAME_PATH, t)
    return t


def load_aligned(scan: Path) -> trimesh.Trimesh:
    """Load any loft scan in the aligned frame."""
    mesh = load_usdz(scan)
    t = reference_transform()
    if Path(scan).resolve() != REFERENCE.resolve():
        t = t @ np.load(Path("data/derived") / f"{Path(scan).stem}_to_reference.npy")
    v = mesh.vertices @ t[:3, :3].T + t[:3, 3]
    return trimesh.Trimesh(v, mesh.faces, process=False)
