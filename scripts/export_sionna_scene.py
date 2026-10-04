"""Export the loft scan for Sionna RT (run with the main .venv, which has usd-core).

Writes data/sionna/loft.ply in Sionna's Z-up frame and data/sionna/geometry.json
with the transmitter and receiver positions in the same frame.

Frame change: aligned scan frame (x, y up, z) -> Sionna (X, Y, Z up) = (x, -z, y),
which keeps the coordinate system right-handed.
"""

import csv
import json
from pathlib import Path

import numpy as np
import trimesh

from locate_ap import aligned_frame
from view_scan import load_mesh

OUT_DIR = Path("data/sionna")
POINTS_CSV = Path("data/derived/survey_points.csv")
AP_PATH = Path("data/derived/ap_location.npy")
RX_HEIGHT = {"16": 1.15, "17": 1.10}  # operator's notes from the 2026-10-02 survey
ANTENNA_ABOVE_DESK = 0.12  # router body plus the lower half of its upright antennas


def to_sionna(p):
    p = np.atleast_2d(p)
    return np.c_[p[:, 0], -p[:, 2], p[:, 1]]


def main() -> None:
    raw = load_mesh()
    v, *_ = aligned_frame(raw)
    mesh = trimesh.Trimesh(to_sionna(v), raw.faces, process=False)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mesh.export(OUT_DIR / "loft.ply")

    ap = np.load(AP_PATH)
    near = (np.hypot(v[:, 0] - ap[0], v[:, 2] - ap[2]) < 0.10) & (v[:, 1] < 1.0)
    desk_top = float(v[near, 1].max())
    tx = np.array([ap[0], desk_top + ANTENNA_ABOVE_DESK, ap[2]])
    print(f"Desk surface under the router: {desk_top:.3f} m, transmitter at {tx[1]:.3f} m")

    rx = {}
    for row in csv.DictReader(POINTS_CSV.open()):
        if row["label"] in rx:
            continue
        p = np.array([float(row["x_m"]), RX_HEIGHT.get(row["label"], 1.00), float(row["z_m"])])
        rx[row["label"]] = to_sionna(p)[0].round(4).tolist()

    geometry = {"tx": to_sionna(tx)[0].round(4).tolist(), "rx": rx, "faces": int(len(mesh.faces))}
    (OUT_DIR / "geometry.json").write_text(json.dumps(geometry, indent=2))
    print(f"Wrote {OUT_DIR / 'loft.ply'} ({len(mesh.faces):,} faces) and {OUT_DIR / 'geometry.json'} ({len(rx)} receivers)")


if __name__ == "__main__":
    main()
