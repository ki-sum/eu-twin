"""Load the loft USDZ scan and report basic mesh statistics."""

from pathlib import Path

import numpy as np
import trimesh
from pxr import Usd, UsdGeom

SCAN_PATH = Path("data/scans/loft_scan_2026-08-07.usdz")


def extract_meshes_from_usd(stage: Usd.Stage) -> list[trimesh.Trimesh]:
    """Walk the USD stage and pull every UsdGeomMesh into a trimesh.Trimesh."""
    meshes = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        points = np.array(mesh.GetPointsAttr().Get(), dtype=np.float64)
        face_vertex_counts = np.array(mesh.GetFaceVertexCountsAttr().Get(), dtype=np.int32)
        face_vertex_indices = np.array(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int32)

        faces = []
        cursor = 0
        for count in face_vertex_counts:
            face = face_vertex_indices[cursor : cursor + count]
            if count == 3:
                faces.append(face)
            elif count == 4:
                faces.append([face[0], face[1], face[2]])
                faces.append([face[0], face[2], face[3]])
            else:
                for i in range(1, count - 1):
                    faces.append([face[0], face[i], face[i + 1]])
            cursor += count

        faces = np.array(faces, dtype=np.int32)
        tm = trimesh.Trimesh(vertices=points, faces=faces, process=False)
        tm.metadata["usd_path"] = str(prim.GetPath())
        meshes.append(tm)
    return meshes


def main() -> None:
    print(f"Loading {SCAN_PATH} ...")
    stage = Usd.Stage.Open(str(SCAN_PATH))
    if stage is None:
        raise RuntimeError(f"Failed to open USD stage: {SCAN_PATH}")

    meshes = extract_meshes_from_usd(stage)
    print(f"Found {len(meshes)} mesh prim(s)")

    if not meshes:
        return

    combined = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]

    bounds = combined.bounds
    extents = bounds[1] - bounds[0]

    print()
    print("=== Combined mesh ===")
    print(f"Vertices:      {len(combined.vertices):,}")
    print(f"Faces:         {len(combined.faces):,}")
    print(f"Watertight:    {combined.is_watertight}")
    print()
    print("=== Bounding box (metres, USD Y-up convention) ===")
    print(f"Min:           x={bounds[0, 0]:+.3f}  y={bounds[0, 1]:+.3f}  z={bounds[0, 2]:+.3f}")
    print(f"Max:           x={bounds[1, 0]:+.3f}  y={bounds[1, 1]:+.3f}  z={bounds[1, 2]:+.3f}")
    print(f"Extents:       dx={extents[0]:.3f}  dy={extents[1]:.3f}  dz={extents[2]:.3f}")
    print(f"Bbox volume:   {np.prod(extents):.2f} m^3")
    print()
    print("=== Per-mesh breakdown ===")
    for i, m in enumerate(meshes):
        print(f"  [{i}] {m.metadata.get('usd_path')}  V={len(m.vertices):>7,}  F={len(m.faces):>7,}")


if __name__ == "__main__":
    main()
