"""Split the two-floor TSDF mesh by surface type and export it for Sionna (run with .venv).

Heights in the aligned frame (loft floor = 0), measured from the walk cloud on
2026-10-04: loft floor +0.02 m, lower-floor ceiling -0.28 m, lower floor -2.68 m.
On-site information: the slab between the floors is concrete, lower-floor walls are brick.

  slab        horizontal faces between -0.45 and +0.15 m (loft floor + lower ceiling)
  lowerfloor  horizontal faces between -2.85 and -2.50 m
  walls       vertical faces between -2.60 and -0.35 m (lower-floor walls)
  other       everything else (loft walls, roof, furniture, stairs)

Writes data/sionna/house/<class>.ply in Sionna's Z-up frame and geometry.json.
"""

import json
from pathlib import Path

import numpy as np
import trimesh

MESH = Path("data/stray/walk_house_2026-10-04/tsdf_mesh_aligned.ply")
OUT = Path("data/sionna/house")
AP_PATH = Path("data/derived/ap_location.npy")
TX_HEIGHT = 0.858  # router antenna, as in export_sionna_scene.py


def to_sionna(p):
    p = np.atleast_2d(p)
    return np.c_[p[:, 0], -p[:, 2], p[:, 1]]


def main() -> None:
    mesh = trimesh.load(MESH, process=False)
    n, c, a = mesh.face_normals, mesh.triangles_center, mesh.area_faces
    horizontal = np.abs(n[:, 1]) > 0.8
    vertical = np.abs(n[:, 1]) < 0.3
    classes = {
        "slab": horizontal & (c[:, 1] > -0.45) & (c[:, 1] < 0.15),
        "lowerfloor": horizontal & (c[:, 1] > -2.85) & (c[:, 1] < -2.50),
        "walls": vertical & (c[:, 1] > -2.60) & (c[:, 1] < -0.35),
    }
    taken = np.zeros(len(c), bool)
    for k in classes:
        classes[k] &= ~taken
        taken |= classes[k]
    classes["other"] = ~taken

    OUT.mkdir(parents=True, exist_ok=True)
    v = to_sionna(mesh.vertices)
    for name, sel in classes.items():
        trimesh.Trimesh(v, mesh.faces[sel], process=False).export(OUT / f"{name}.ply")
        print(f"{name:10s}: {sel.sum():9,} faces, {a[sel].sum():7.1f} m2")
    ap = np.load(AP_PATH)
    tx = to_sionna([ap[0], TX_HEIGHT, ap[2]])[0]
    (OUT / "geometry.json").write_text(json.dumps({"tx": tx.round(4).tolist()}, indent=2))
    print(f"transmitter (Sionna frame): {tx.round(3).tolist()}")


if __name__ == "__main__":
    main()
