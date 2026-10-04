"""Does a model learned with the TP-Link predict the Xiaomi R4A on the lower floor?

Xiaomi walk 2026-10-04: lower floor only, all doors open. Time sync from the
first BOOT press (pressed with Stray's record button); Stray stop came ~5 s
before an accidental RST, so only the start marker is used (clock scale 1).
Transmitter: Xiaomi at aligned (5.5, -2.38, 8.4) from the operator's mark.

Models on 0.5 m lower-floor cells (>= 100 frames each), one global bias each:
  transferred : free space only -- what the TP-Link fit implied for the same
                floor (lower-floor brick walls showed no extra loss)
  mock 8 dB   : free space + 8 dB per wall crossing
  refit       : free space + wall loss fitted on this walk (2 numbers)
  Sionna      : physics / plain radio maps with the transmitter at the Xiaomi
"""

import json
from pathlib import Path

import numpy as np
import trimesh
from scipy import ndimage

from mock_coverage import fspl_db

FOLDER = Path("data/stray/walk_xiaomi_2026-10-04")
PROBE = Path("data/raw/walk_xiaomi_2026-10-04.jsonl")
MESH = Path("data/stray/walk_house_2026-10-04/tsdf_mesh_aligned.ply")
TX = np.array([5.5, -2.38, 8.4])
CELL, MIN_FRAMES, CEILING = 0.5, 100, -0.28
X0, Z0 = 2.0, -0.3


def db_mean(v):
    return 10 * np.log10(np.mean(10 ** (np.asarray(v) / 10)))


def main() -> None:
    odo = np.genfromtxt(FOLDER / "odometry.csv", delimiter=",", skip_header=1, usecols=range(5))
    m = np.load(FOLDER / "to_aligned_opencv.npy")
    pos = odo[:, 2:5] @ m[:3, :3].T + m[:3, 3]
    st = odo[:, 0]

    rec = [json.loads(line) for line in PROBE.open()]
    boot0 = rec[0]["boot_id"]
    rec = [r for r in rec if r["boot_id"] == boot0]
    pc = np.array([r["pc_time"] for r in rec])
    rssi = np.array([r["rssi"] for r in rec], dtype=float)
    pt = np.array([r["point"] for r in rec])
    t1 = pc[np.argmax(pt > 0)]
    phone_pc = t1 + (st - st[0])

    first = phone_pc < t1 + 20
    i_close = np.argmin(np.linalg.norm(pos[first] - TX, axis=1))
    w = (pc > t1) & (pc < t1 + 20)
    sec = np.floor(pc[w] - t1)
    strong = [k for k in sorted(set(sec)) if np.median(rssi[w][sec == k]) > -25]
    print(f"phone closest to the Xiaomi ({np.linalg.norm(pos[first][i_close] - TX):.2f} m) at "
          f"+{phone_pc[first][i_close] - t1:.1f} s; RSSI above -25 dBm during seconds "
          f"{strong[0]:.0f}-{strong[-1]:.0f}")

    inside = (pc >= t1) & (pc <= phone_pc[-1])
    xyz = np.c_[[np.interp(pc[inside], phone_pc, pos[:, k]) for k in range(3)]].T
    vals = rssi[inside]
    lower = xyz[:, 1] < -0.3
    print(f"{inside.sum():,} frames placed, {lower.sum():,} on the lower floor")
    xyz, vals = xyz[lower], vals[lower]

    ix = ((xyz[:, 0] - X0) / CELL).astype(int)
    iz = ((xyz[:, 2] - Z0) / CELL).astype(int)
    cells = []
    for key in set(zip(ix, iz)):
        sel = (ix == key[0]) & (iz == key[1])
        if sel.sum() >= MIN_FRAMES:
            cells.append((key, db_mean(vals[sel]), xyz[sel].mean(axis=0)))
    cells.sort()
    keys = [c[0] for c in cells]
    meas = np.array([c[1] for c in cells])
    cpos = np.array([c[2] for c in cells])

    mesh = trimesh.load(MESH, process=False)
    pts, fid = trimesh.sample.sample_surface(mesh, 3_000_000, seed=0)
    nrm = mesh.face_normals[fid]
    fine = 0.05
    shape = (int(10.0 / fine), int(6.0 / fine))
    wp = pts[(np.abs(nrm[:, 1]) < 0.3) & (pts[:, 1] > -2.3) & (pts[:, 1] < -0.6)]
    walls = np.zeros(shape, bool)
    wi = ((wp[:, 2] - Z0) / fine).astype(int)
    wj = ((wp[:, 0] - X0) / fine).astype(int)
    ok = (wi >= 0) & (wj >= 0) & (wi < shape[0]) & (wj < shape[1])
    walls[wi[ok], wj[ok]] = True
    walls = ndimage.binary_dilation(walls, iterations=2)

    dist, n_wall = [], []
    for p in cpos:
        d = np.linalg.norm(p - TX)
        dist.append(d)
        line = TX + np.linspace(0, 1, int(d / 0.025) + 2)[:, None] * (p - TX)
        li = ((line[:, 2] - Z0) / fine).astype(int).clip(0, shape[0] - 1)
        lj = ((line[:, 0] - X0) / fine).astype(int).clip(0, shape[1] - 1)
        hit = walls[li, lj] & (line[:, 1] < CEILING)
        n_wall.append(int(np.sum(hit[1:] & ~hit[:-1]) + hit[0]))
    dist, n_wall = np.array(dist), np.array(n_wall)
    fs = -fspl_db(np.maximum(dist, 0.3))
    print(f"{len(meas)} lower-floor cells; distance {dist.min():.1f}-{dist.max():.1f} m; "
          f"walls crossed median {np.median(n_wall):.0f}, max {n_wall.max()}")

    def bias(pred):
        return pred + np.mean(meas - pred)

    res = {"constant (no model)": (np.full_like(meas, meas.mean()), 1),
           "transferred from TP-Link (distance only)": (bias(fs), 1),
           "mock, 8 dB per wall": (bias(fs - 8 * n_wall), 1)}
    a = np.c_[np.ones(len(meas)), -n_wall]
    coef, *_ = np.linalg.lstsq(a, meas - fs, rcond=None)
    res[f"refit on this walk (wall {coef[1]:.1f} dB)"] = (fs + a @ coef, 2)
    for variant in ("physics", "plain"):
        z = np.load(f"data/derived/sionna_house_{variant}_xiaomi.npz")
        pg, gx, gz = z["path_gain"], z["x"], z["z"]
        pred = []
        for k in keys:
            cx0, cz0 = X0 + k[0] * CELL, Z0 + k[1] * CELL
            inc = (gx >= cx0) & (gx < cx0 + CELL) & (gz >= cz0) & (gz < cz0 + CELL)
            pred.append(10 * np.log10(np.mean(pg[inc])))
        res[f"Sionna {variant}"] = (bias(np.array(pred)), 1)

    print(f"\n{'model':42s} RMSE (dB)  fitted numbers")
    for name, (pred, k) in res.items():
        print(f"{name:42s} {np.sqrt(np.mean((meas - pred) ** 2)):6.2f}     {k}")
    np.savez("data/derived/xiaomi_compare.npz", meas=meas, pos=cpos, n_wall=n_wall, dist=dist,
             **{f"m{i}": pred for i, (pred, _) in enumerate(res.values())})


if __name__ == "__main__":
    main()
