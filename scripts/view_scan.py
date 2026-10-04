"""Open an interactive 3D viewer for the loft scan."""

from pathlib import Path

import numpy as np
import trimesh
from pxr import Usd, UsdGeom

SCAN_PATH = Path("data/scans/loft_scan_2026-08-07.usdz")


def load_mesh() -> trimesh.Trimesh:
    stage = Usd.Stage.Open(str(SCAN_PATH))
    prim = next(p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh))
    mesh = UsdGeom.Mesh(prim)

    points = np.array(mesh.GetPointsAttr().Get(), dtype=np.float64)
    counts = np.array(mesh.GetFaceVertexCountsAttr().Get(), dtype=np.int32)
    indices = np.array(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int32)

    faces = []
    cursor = 0
    for c in counts:
        f = indices[cursor : cursor + c]
        if c == 3:
            faces.append(f)
        else:
            for i in range(1, c - 1):
                faces.append([f[0], f[i], f[i + 1]])
        cursor += c
    return trimesh.Trimesh(vertices=points, faces=np.array(faces, dtype=np.int32), process=False)


def main() -> None:
    tm = load_mesh()
    tm.visual.face_colors = [200, 200, 200, 255]

    scene = trimesh.Scene(tm)
    scene.add_geometry(trimesh.creation.axis(origin_size=0.15))

    print("Opening viewer. Controls: left-drag rotate, right-drag pan, wheel zoom, Q to quit.")
    scene.show()


if __name__ == "__main__":
    main()
