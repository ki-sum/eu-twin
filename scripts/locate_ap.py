"""Place the access point in the scan using the tape measurements.

Measurements (2026-08-07, tape measure):
  - 70 cm: AP height above the floor (desk surface)
  - 40 cm: horizontal distance from the wall the long desk stands against (side D)
  - 150 cm: horizontal distance, at AP height, towards the iMac end of the desk
            (side C) until the sloped ceiling is reached

Coordinates are in the aligned frame used by topdown_map.py: walls parallel to
the X/Z axes, Y up, floor at Y = 0, X/Z offset so the scan starts at 0.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from topdown_map import FLOOR_Y, dominant_wall_yaw
from view_scan import load_mesh

AP_HEIGHT = 0.70
AP_TO_BACK_WALL = 0.40
AP_TO_SLOPE = 1.50
DESK_REGION = dict(x=(1.8, 3.5), z=(5.5, 9.5))
OUT_PATH = Path("data/derived/ap_location.png")


def aligned_frame(mesh):
    yaw = dominant_wall_yaw(mesh)
    c, s = np.cos(-yaw), np.sin(-yaw)
    rot = np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])
    v = mesh.vertices @ rot.T
    v[:, 1] -= FLOOR_Y
    offset = np.array([v[:, 0].min(), 0.0, v[:, 2].min()])
    v -= offset
    normals = mesh.face_normals @ rot.T
    centres = v[mesh.faces].mean(axis=1)
    return v, normals, centres, mesh.area_faces


def in_region(p, x, z, y=(-np.inf, np.inf)):
    return (p[:, 0] > x[0]) & (p[:, 0] < x[1]) & (p[:, 2] > z[0]) & (p[:, 2] < z[1]) & (p[:, 1] > y[0]) & (p[:, 1] < y[1])


def main() -> None:
    _, n, ctr, area = aligned_frame(load_mesh())

    wall = in_region(ctr, y=(0.8, 1.6), **DESK_REGION) & (n[:, 0] > 0.85)
    wall_x = np.average(ctr[wall, 0], weights=area[wall])
    print(f"Back wall (side D): x = {wall_x:.3f} m  ({wall.sum()} faces, {area[wall].sum():.2f} m2)")

    slope = in_region(ctr, y=(0.8, 2.8), **DESK_REGION) & (n[:, 1] < -0.3) & (n[:, 2] < -0.3)
    a_mat = np.c_[np.ones(slope.sum()), ctr[slope, 0], ctr[slope, 2]]
    coef, *_ = np.linalg.lstsq(a_mat, ctr[slope, 1], rcond=None)
    resid = ctr[slope, 1] - a_mat @ coef
    pitch = np.degrees(np.arctan(abs(coef[2])))
    print(f"Sloped ceiling: y = {coef[0]:.3f} + {coef[1]:.3f}x + {coef[2]:.3f}z  "
          f"(pitch {pitch:.1f} deg, {slope.sum()} faces, rms {np.sqrt(np.mean(resid**2)) * 100:.1f} cm)")

    ap_x = wall_x + AP_TO_BACK_WALL
    z_hit = (AP_HEIGHT - coef[0] - coef[1] * ap_x) / coef[2]
    ap = np.array([ap_x, AP_HEIGHT, z_hit - AP_TO_SLOPE])
    print(f"Slope reaches {AP_HEIGHT} m height at z = {z_hit:.3f}")
    print(f"AP position: x = {ap[0]:.3f}  y = {ap[1]:.3f}  z = {ap[2]:.3f}  (metres)")
    np.save(OUT_PATH.with_suffix(".npy"), ap)

    fig, (top, side) = plt.subplots(1, 2, figsize=(12, 6))
    near = in_region(ctr, x=(1.0, 6.0), z=(3.0, 10.0))
    top.scatter(ctr[near, 0], ctr[near, 2], c=ctr[near, 1], s=0.2, cmap="viridis", vmin=0, vmax=3)
    desk = near & (n[:, 1] > 0.9) & (ctr[:, 1] > 0.6) & (ctr[:, 1] < 0.85)
    top.scatter(ctr[desk, 0], ctr[desk, 2], s=0.5, c="white")
    top.plot(ap[0], ap[2], "o", ms=14, mfc="red", mec="black")
    top.annotate("AP", (ap[0], ap[2]), xytext=(10, -10), textcoords="offset points", color="red", fontsize=14, fontweight="bold")
    top.set_aspect("equal")
    top.invert_yaxis()
    top.set_facecolor("black")
    top.set_title("Top view around the desk (red = AP)")
    top.set_xlabel("x (m)")
    top.set_ylabel("z (m)")

    band = in_region(ctr, x=(ap[0] - 0.15, ap[0] + 0.15), z=(3.0, 10.0))
    side.scatter(ctr[band, 2], ctr[band, 1], s=0.5, c="gray")
    side.plot([ap[2], z_hit], [AP_HEIGHT, AP_HEIGHT], "r--", lw=2)
    side.plot(ap[2], ap[1], "o", ms=14, mfc="red", mec="black")
    side.annotate("150 cm", ((ap[2] + z_hit) / 2, AP_HEIGHT), xytext=(0, 8), textcoords="offset points", ha="center", color="red", fontsize=12)
    side.set_aspect("equal")
    side.set_title(f"Side cut along the desk at x = {ap[0]:.2f} m")
    side.set_xlabel("z (m)  -> towards side C / iMac end")
    side.set_ylabel("height above floor (m)")

    fig.savefig(OUT_PATH, dpi=110, bbox_inches="tight")
    print(f"Saved {OUT_PATH}")


if __name__ == "__main__":
    main()
