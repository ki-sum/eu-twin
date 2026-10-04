"""Export the loft+bathroom scan for Sionna, with the bathroom walls split out as brick.

Run with the main .venv. Writes into data/sionna/bath/:
  loft.ply        everything except the two bathroom walls (Sionna Z-up frame)
  walls.ply       faces of the door wall and the C-side bathroom wall
  door.ply        a closed door (the door was open during the scan)
  geometry.json   transmitter and every receiver sub-position

Wall surfaces measured from the scan on 2026-10-03: door wall between
x 5.33 (loft side) and 5.55 (bathroom side), C-side wall between z 3.81
(bathroom side) and 4.0 (loft side); door gap at z 1.15-2.10.
Sub-positions follow the protocol: centre, 20 cm towards A (-z), 20 cm towards B (+x).
"""

import csv
import json
from pathlib import Path

import numpy as np
import trimesh

from scan_frame import load_aligned

SCAN = Path("data/scans/loft_with_bathroom_2026-10-03.usdz")
OUT = Path("data/sionna/bath")
AP_PATH = Path("data/derived/ap_location.npy")
PLAN = Path("data/derived/bathroom_plan.json")
POINTS_CSV = Path("data/derived/survey_points.csv")
ANTENNA_ABOVE_DESK = 0.12
SUB_OFFSETS = {"c": (0.0, 0.0), "a": (0.0, -0.20), "b": (0.20, 0.0)}
DOOR = dict(x=5.44, z0=1.15, z1=2.10, y1=2.0)


def to_sionna(p):
    p = np.atleast_2d(p)
    return np.c_[p[:, 0], -p[:, 2], p[:, 1]]


def main() -> None:
    mesh = load_aligned(SCAN)
    n, c = mesh.face_normals, mesh.triangles_center
    wall_height = (c[:, 1] > -0.05) & (c[:, 1] < 3.25)  # the walls reach the roof at about 3.1 m
    door_wall = (np.abs(n[:, 0]) > 0.7) & (c[:, 0] > 5.25) & (c[:, 0] < 5.62) & (c[:, 2] > 0.3) & (c[:, 2] < 4.05)
    c_wall = (np.abs(n[:, 2]) > 0.7) & (c[:, 2] > 3.75) & (c[:, 2] < 4.06) & (c[:, 0] > 5.3) & (c[:, 0] < 7.15)
    walls = wall_height & (door_wall | c_wall)
    print(f"Bathroom wall faces: {walls.sum():,} ({mesh.area_faces[walls].sum():.1f} m2)")

    OUT.mkdir(parents=True, exist_ok=True)
    v = to_sionna(mesh.vertices)
    trimesh.Trimesh(v, mesh.faces[~walls], process=False).export(OUT / "loft.ply")
    trimesh.Trimesh(v, mesh.faces[walls], process=False).export(OUT / "walls.ply")
    # The C-side wall was not scanned below ~0.4 m (hidden behind bathroom fittings);
    # close that strip so rays cannot slip under the wall.
    patch = np.array([[5.44, 0.0, 3.90], [7.10, 0.0, 3.90], [7.10, 0.45, 3.90], [5.44, 0.45, 3.90]])
    trimesh.Trimesh(to_sionna(patch), [[0, 1, 2], [0, 2, 3]], process=False).export(OUT / "patch.ply")
    d = DOOR
    door = np.array([[d["x"], 0.0, d["z0"]], [d["x"], 0.0, d["z1"]], [d["x"], d["y1"], d["z1"]], [d["x"], d["y1"], d["z0"]]])
    trimesh.Trimesh(to_sionna(door), [[0, 1, 2], [0, 2, 3]], process=False).export(OUT / "door.ply")

    ap = np.load(AP_PATH)
    near = (np.hypot(mesh.vertices[:, 0] - ap[0], mesh.vertices[:, 2] - ap[2]) < 0.10) & (mesh.vertices[:, 1] < 1.0)
    tx = np.array([ap[0], mesh.vertices[near, 1].max() + ANTENNA_ABOVE_DESK, ap[2]])

    centres = {r["label"]: (float(r["x_m"]), float(r["z_m"])) for r in csv.DictReader(POINTS_CSV.open())}
    centres.update({k: tuple(v) for k, v in json.loads(PLAN.read_text())["bathroom_points"].items()})
    rx = {}
    for label in ["R", "11", "9", "7", "B1", "B2", "B3", "B4", "B5"]:
        x, z = centres[label]
        for s, (dx, dz) in SUB_OFFSETS.items():
            if label == "R" and s != "c":
                continue
            rx[f"{label}_{s}"] = to_sionna([x + dx, 1.0, z + dz])[0].round(4).tolist()
    (OUT / "geometry.json").write_text(json.dumps({"tx": to_sionna(tx)[0].round(4).tolist(), "rx": rx}, indent=2))
    print(f"Transmitter at height {tx[1]:.3f} m; {len(rx)} receiver positions; wrote {OUT}")


if __name__ == "__main__":
    main()
