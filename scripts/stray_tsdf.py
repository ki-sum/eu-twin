"""Fuse a Stray Scanner recording into a triangle mesh with Open3D TSDF (run with .venv-o3d).

Follows StrayVisualizer: T_WC from odometry (camera-to-world, OpenCV camera
axes), extrinsic = inv(T_WC), intrinsics scaled from 1920x1440 to the 256x192
depth images, only confidence==2 depth. The mesh is then moved into the loft's
aligned frame with the transform from stray_align.py.

    .venv-o3d/Scripts/python.exe scripts/stray_tsdf.py data/stray/walk_house_2026-10-04
"""

import sys
from pathlib import Path

import numpy as np
import open3d as o3d
from PIL import Image
from scipy.spatial.transform import Rotation

VOXEL = 0.03
FRAME_STEP = 3


def main() -> None:
    folder = Path(sys.argv[1])
    odo = np.genfromtxt(folder / "odometry.csv", delimiter=",", skip_header=1, usecols=range(13))
    # ScalableTSDFVolume in open3d 0.20 (Windows) returns no surface even for a
    # synthetic flat wall, so use a UniformTSDFVolume around the scanned points.
    cloud = np.load(folder / "cloud_opencv_voxel3cm.npy")
    lo, hi = cloud.min(axis=0) - 0.3, cloud.max(axis=0) + 0.3
    length = float((hi - lo).max())
    volume = o3d.pipelines.integration.UniformTSDFVolume(
        length=length, resolution=int(np.ceil(length / VOXEL)), sdf_trunc=4 * VOXEL,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.NoColor, origin=lo.astype(float))
    print(f"volume: {length:.1f} m cube, {int(np.ceil(length / VOXEL))}^3 voxels", flush=True)
    blank = None
    for n, row in enumerate(odo[::FRAME_STEP]):
        frame = int(row[1])
        depth = np.asarray(Image.open(folder / "depth" / f"{frame:06d}.png")).astype(np.uint16)
        conf = np.asarray(Image.open(folder / "confidence" / f"{frame:06d}.png"))
        depth = np.where(conf == 2, depth, 0).astype(np.uint16)
        h, w = depth.shape
        if blank is None:
            blank = o3d.geometry.Image(np.zeros((h, w, 3), dtype=np.uint8))
        s = w / 1920.0
        intr = o3d.camera.PinholeCameraIntrinsic(w, h, row[9] * s, row[10] * s, row[11] * s, row[12] * s)
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            blank, o3d.geometry.Image(depth), depth_scale=1000.0, depth_trunc=4.0, convert_rgb_to_intensity=False)
        t_wc = np.eye(4)
        t_wc[:3, :3] = Rotation.from_quat(row[5:9]).as_matrix()
        t_wc[:3, 3] = row[2:5]
        volume.integrate(rgbd, intr, np.linalg.inv(t_wc))
        if n % 1000 == 0:
            print(f"integrated {n} / {len(odo) // FRAME_STEP + 1} frames", flush=True)

    mesh = volume.extract_triangle_mesh()
    print(f"raw mesh: {len(mesh.vertices):,} vertices, {len(mesh.triangles):,} triangles", flush=True)
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_vertices()
    tri_clusters, cluster_n, _ = mesh.cluster_connected_triangles()
    tri_clusters = np.asarray(tri_clusters)
    small = np.asarray(cluster_n)[tri_clusters] < 200
    mesh.remove_triangles_by_mask(small)
    mesh.remove_unreferenced_vertices()
    m = np.load(folder / "to_aligned_opencv.npy")
    mesh.transform(m)
    out = folder / "tsdf_mesh_aligned.ply"
    o3d.io.write_triangle_mesh(str(out), mesh)
    print(f"cleaned mesh: {len(mesh.vertices):,} vertices, {len(mesh.triangles):,} triangles -> {out}", flush=True)


if __name__ == "__main__":
    main()
