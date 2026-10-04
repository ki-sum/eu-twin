"""Lower-floor comparison of the 2026-10-04 house walk with the mock and Sionna RT.

Measured: walk samples on the lower floor (aligned height below -0.3 m) binned
into 0.5 m x 0.5 m cells, mean linear power per cell, cells with >= 50 samples.
Mock: free-space loss + loss per crossing of the concrete slab (unless the
straight path passes the stairwell opening) and of lower-floor walls (vertical
surfaces of the TSDF mesh, so tall furniture counts too). "8 dB" uses the
stitching-plan placeholder for both; "fitted" fits slab and wall loss.
Sionna: mean path gain of the 0.25 m radio-map cells inside each 0.5 m cell.
Every model gets one global bias (the fitted mock also gets its two losses).
"""

from pathlib import Path

import numpy as np
import trimesh
from scipy import ndimage

from mock_coverage import fspl_db

SAMPLES = Path("data/stray/walk_house_2026-10-04/walk_samples.npz")
MESH = Path("data/stray/walk_house_2026-10-04/tsdf_mesh_aligned.ply")
AP_PATH = Path("data/derived/ap_location.npy")
TX_HEIGHT = 0.858
CELL = 0.5
MIN_SAMPLES = 50
SLAB_MID = -0.14
CEILING = -0.28


def db_mean(v):
    return 10 * np.log10(np.mean(10 ** (np.asarray(v) / 10)))


def occupancy(points, cell, x0, z0, shape):
    m = np.zeros(shape, bool)
    ix = ((points[:, 0] - x0) / cell).astype(int)
    iz = ((points[:, 2] - z0) / cell).astype(int)
    ok = (ix >= 0) & (iz >= 0) & (ix < shape[1]) & (iz < shape[0])
    m[iz[ok], ix[ok]] = True
    return m


def main() -> None:
    s = np.load(SAMPLES)
    xyz, rssi = s["xyz"], s["rssi"]
    lower = xyz[:, 1] < -0.3
    xyz, rssi = xyz[lower], rssi[lower]
    ap = np.load(AP_PATH)
    tx = np.array([ap[0], TX_HEIGHT, ap[2]])

    x0, z0 = 2.0, -0.3
    ix = ((xyz[:, 0] - x0) / CELL).astype(int)
    iz = ((xyz[:, 2] - z0) / CELL).astype(int)
    cells = {}
    for key in set(zip(ix, iz)):
        sel = (ix == key[0]) & (iz == key[1])
        if sel.sum() >= MIN_SAMPLES:
            cells[key] = (db_mean(rssi[sel]), xyz[sel].mean(axis=0), sel.sum())
    keys = sorted(cells)
    meas = np.array([cells[k][0] for k in keys])
    pos = np.array([cells[k][1] for k in keys])
    print(f"lower-floor cells with >= {MIN_SAMPLES} samples: {len(keys)} (of {len(set(zip(ix, iz)))} visited)")

    # geometry maps from the TSDF mesh
    mesh = trimesh.load(MESH, process=False)
    pts, fid = trimesh.sample.sample_surface(mesh, 3_000_000, seed=0)
    nrm = mesh.face_normals[fid]
    fine = 0.05
    shape = (int(10.0 / fine), int(6.0 / fine))
    slab_pts = pts[(np.abs(nrm[:, 1]) > 0.8) & (pts[:, 1] > -0.45) & (pts[:, 1] < 0.15)]
    slab = ndimage.binary_closing(occupancy(slab_pts, fine, x0, z0, shape), iterations=6)
    wall_pts = pts[(np.abs(nrm[:, 1]) < 0.3) & (pts[:, 1] > -2.3) & (pts[:, 1] < -0.6)]
    walls = ndimage.binary_dilation(occupancy(wall_pts, fine, x0, z0, shape), iterations=2)

    n_slab, n_wall, dist = [], [], []
    for p in pos:
        d = np.linalg.norm(p - tx)
        dist.append(d)
        t = (SLAB_MID - tx[1]) / (p[1] - tx[1])
        cx, cz = tx[0] + t * (p[0] - tx[0]), tx[2] + t * (p[2] - tx[2])
        ci, cj = int((cz - z0) / fine), int((cx - x0) / fine)
        n_slab.append(int(0 <= ci < shape[0] and 0 <= cj < shape[1] and slab[ci, cj]))
        ts = np.linspace(0, 1, int(d / 0.025) + 2)
        line = tx + ts[:, None] * (p - tx)
        below = line[:, 1] < CEILING
        li = ((line[:, 2] - z0) / fine).astype(int).clip(0, shape[0] - 1)
        lj = ((line[:, 0] - x0) / fine).astype(int).clip(0, shape[1] - 1)
        hit = walls[li, lj] & below
        n_wall.append(int(np.sum(hit[1:] & ~hit[:-1]) + hit[0]))
    n_slab, n_wall, dist = map(np.array, (n_slab, n_wall, dist))
    fs = -fspl_db(dist)
    print(f"slab crossed on {n_slab.mean() * 100:.0f}% of cells (rest: straight path through the stairwell); "
          f"wall crossings per cell: median {np.median(n_wall):.0f}, max {n_wall.max()}")

    def fit_bias(pred):
        return pred + np.mean(meas - pred)

    results = {}
    results["constant (no model)"] = (np.full_like(meas, meas.mean()), 1)
    results["mock, 8 dB per slab/wall"] = (fit_bias(fs - 8 * (n_slab + n_wall)), 1)
    a = np.c_[np.ones(len(meas)), -n_slab, -n_wall]
    coef, *_ = np.linalg.lstsq(a, meas - fs, rcond=None)
    results[f"mock fitted (slab {coef[1]:.1f}, wall {coef[2]:.1f} dB)"] = (fs + a @ coef, 3)
    xs = (pos[:, 0] - x0) / 0.25
    for variant in ("plain", "physics", "plain_s0.3", "physics_s0.3", "slabonly", "physics_d16", "physics_hw_dipole", "plain_hw_dipole"):
        z = np.load(f"data/derived/sionna_house_{variant}.npz")
        pg, gx, gz = z["path_gain"], z["x"], z["z"]
        pred = []
        for k in keys:
            cx0, cz0 = x0 + k[0] * CELL, z0 + k[1] * CELL
            inside = (gx >= cx0) & (gx < cx0 + CELL) & (gz >= cz0) & (gz < cz0 + CELL)
            pred.append(10 * np.log10(np.mean(pg[inside])) if inside.any() and np.mean(pg[inside]) > 0 else np.nan)
        pred = np.array(pred)
        ok = np.isfinite(pred)
        p2 = np.where(ok, pred, np.nanmean(pred))
        results[f"Sionna {variant}"] = (fit_bias(p2), 1)

    print(f"\n{'model':38s} RMSE (dB)  fitted numbers")
    for name, (pred, k) in results.items():
        print(f"{name:38s} {np.sqrt(np.mean((meas - pred) ** 2)):6.2f}     {k}")
    np.savez("data/derived/house_compare.npz", meas=meas, pos=pos, n_slab=n_slab, n_wall=n_wall,
             **{name.split(" (")[0].replace(" ", "_").replace(",", ""): pred for name, (pred, _) in results.items()})


if __name__ == "__main__":
    main()
