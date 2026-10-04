"""Render a top-down map of the loft scan so walls can be identified by eye.

Colour = ceiling height above the floor (shows where the roof slopes down).
Black = holes in the floor (stairwell). White outlines = surfaces at desk
height (~0.6-0.8 m above floor), which should reveal desks and tables.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from view_scan import load_mesh

OUT_PATH = Path("data/derived/loft_topdown.png")
FLOOR_Y = -0.05  # metres, from the up-facing-area histogram of the scan
CELL = 0.05  # metres per map pixel


def dominant_wall_yaw(mesh) -> float:
    """Return the yaw (radians) that best aligns vertical faces with the X/Z axes."""
    n = mesh.face_normals
    vertical = np.abs(n[:, 1]) < 0.2
    angles = np.arctan2(n[vertical, 2], n[vertical, 0]) % (np.pi / 2)
    hist, edges = np.histogram(angles, bins=90, weights=mesh.area_faces[vertical])
    return edges[np.argmax(hist)] + (edges[1] - edges[0]) / 2


def main() -> None:
    mesh = load_mesh()
    yaw = dominant_wall_yaw(mesh)
    c, s = np.cos(-yaw), np.sin(-yaw)
    rot = np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])
    v = mesh.vertices @ rot.T
    v[:, 1] -= FLOOR_Y
    print(f"Rotated by {np.degrees(yaw):.1f} deg to align walls with axes")

    x0, z0 = v[:, 0].min(), v[:, 2].min()
    ix = ((v[:, 0] - x0) / CELL).astype(int)
    iz = ((v[:, 2] - z0) / CELL).astype(int)
    nx, nz = ix.max() + 1, iz.max() + 1

    ceiling = np.full((nz, nx), np.nan)
    floor_min = np.full((nz, nx), np.nan)
    np.fmax.at(ceiling, (iz, ix), v[:, 1])
    np.fmin.at(floor_min, (iz, ix), v[:, 1])

    tri = v[mesh.faces].mean(axis=1)
    up = mesh.face_normals @ rot.T
    desk = (up[:, 1] > 0.9) & (tri[:, 1] > 0.6) & (tri[:, 1] < 0.85)

    extent = [0, nx * CELL, nz * CELL, 0]
    fig, ax = plt.subplots(figsize=(7, 10))
    im = ax.imshow(np.clip(ceiling, 0, 3.2), cmap="viridis", extent=extent)
    hole = np.where(floor_min < -0.3, 1.0, np.nan)
    ax.imshow(hole, cmap="gray_r", vmin=0, vmax=1, extent=extent)
    ax.scatter(tri[desk, 0] - x0, tri[desk, 2] - z0, s=0.3, c="white")

    w, d = nx * CELL, nz * CELL
    style = dict(fontsize=22, fontweight="bold", color="red", ha="center", va="center")
    ax.text(w / 2, -0.25, "A", **style)
    ax.text(w + 0.25, d / 2, "B", **style)
    ax.text(w / 2, d + 0.25, "C", **style)
    ax.text(-0.25, d / 2, "D", **style)
    ax.set_xlim(-0.6, w + 0.6)
    ax.set_ylim(d + 0.6, -0.6)
    ax.set_xlabel("metres")
    ax.set_ylabel("metres")
    ax.set_title("Loft top view - colour: ceiling height (m)\nblack: stairwell, white: desk-height surfaces")
    fig.colorbar(im, ax=ax, shrink=0.6, label="ceiling height above floor (m)")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=110, bbox_inches="tight")
    print(f"Saved {OUT_PATH}")


if __name__ == "__main__":
    main()
