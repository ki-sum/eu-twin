"""Xiaomi R4A, both floors: lower-floor walk (start marker only) + upper-floor walk (2 markers).

Models share one global bias over all cells:
  transferred : free space + 13.5 dB for the upper floor (floor step learned with the TP-Link)
  refit       : free space + floor step fitted on these cells (2 numbers)
  Sionna      : physics / plain radio maps, TX at the Xiaomi, planes at -1.25 m and +1.35 m
"""

import json
from pathlib import Path

import numpy as np

from mock_coverage import fspl_db

TX = np.array([5.5, -2.38, 8.4])
CELL, MIN_FRAMES, X0, Z0 = 0.5, 100, 2.0, -0.3
WALKS = [("lower", "data/stray/walk_xiaomi_2026-10-04", "data/raw/walk_xiaomi_2026-10-04.jsonl", lambda y: y < -0.3),
         ("upper", "data/stray/walk_xiaomi_up_2026-10-04", "data/raw/walk_xiaomi_up_2026-10-04.jsonl", lambda y: y > 0.3)]


def db_mean(v):
    return 10 * np.log10(np.mean(10 ** (np.asarray(v) / 10)))


def walk_cells(folder, probe, keep):
    folder = Path(folder)
    odo = np.genfromtxt(folder / "odometry.csv", delimiter=",", skip_header=1, usecols=range(5))
    m = np.load(folder / "to_aligned_opencv.npy")
    pos = odo[:, 2:5] @ m[:3, :3].T + m[:3, 3]
    st = odo[:, 0]
    rec = [json.loads(line) for line in open(probe)]
    rec = [r for r in rec if r["boot_id"] == rec[0]["boot_id"]]
    pc = np.array([r["pc_time"] for r in rec])
    rssi = np.array([r["rssi"] for r in rec], dtype=float)
    pt = np.array([r["point"] for r in rec])
    marks = [i for i in range(1, len(pt)) if pt[i] != pt[i - 1]]
    t1 = pc[marks[0]]
    scale = (pc[marks[-1]] - t1) / (st[-1] - st[0]) if len(marks) > 1 else 1.0
    phone_pc = t1 + (st - st[0]) * scale
    inside = (pc >= t1) & (pc <= phone_pc[-1])
    xyz = np.c_[[np.interp(pc[inside], phone_pc, pos[:, k]) for k in range(3)]].T
    vals = rssi[inside]
    sel0 = keep(xyz[:, 1])
    xyz, vals = xyz[sel0], vals[sel0]
    ix = ((xyz[:, 0] - X0) / CELL).astype(int)
    iz = ((xyz[:, 2] - Z0) / CELL).astype(int)
    out = []
    for key in sorted(set(zip(ix, iz))):
        sel = (ix == key[0]) & (iz == key[1])
        if sel.sum() >= MIN_FRAMES:
            out.append((key, db_mean(vals[sel]), xyz[sel].mean(axis=0)))
    return out


def sionna_at(npz, keys):
    z = np.load(npz)
    pg, gx, gz = z["path_gain"], z["x"], z["z"]
    pred = []
    for k in keys:
        cx0, cz0 = X0 + k[0] * CELL, Z0 + k[1] * CELL
        inc = (gx >= cx0) & (gx < cx0 + CELL) & (gz >= cz0) & (gz < cz0 + CELL)
        pred.append(10 * np.log10(np.mean(pg[inc])))
    return np.array(pred)


def main() -> None:
    floors, meas, pos, keys = [], [], [], []
    for name, folder, probe, keep in WALKS:
        cells = walk_cells(folder, probe, keep)
        floors += [name] * len(cells)
        keys += [c[0] for c in cells]
        meas += [c[1] for c in cells]
        pos += [c[2] for c in cells]
    floors, meas, pos = np.array(floors), np.array(meas), np.array(pos)
    up = (floors == "upper").astype(float)
    dist = np.linalg.norm(pos - TX, axis=1)
    fs = -fspl_db(np.maximum(dist, 0.3))
    print(f"cells: lower {int((up == 0).sum())}, upper {int(up.sum())}; measured upper-minus-lower "
          f"mean {meas[up == 1].mean() - meas[up == 0].mean():+.1f} dB")

    preds = {"transferred (FSPL + 13.5 dB floor step)": (fs - 13.5 * up, 1)}
    a = np.c_[np.ones(len(meas)), -up]
    coef, *_ = np.linalg.lstsq(a, meas - fs, rcond=None)
    preds[f"refit (FSPL + {coef[1]:.1f} dB floor step)"] = (fs + a @ coef - coef[0], 2)
    for variant in ("physics", "plain"):
        lo = sionna_at(f"data/derived/sionna_house_{variant}_xiaomi.npz", [k for k, f in zip(keys, floors) if f == "lower"])
        hi = sionna_at(f"data/derived/sionna_house_{variant}_xiaomi_up.npz", [k for k, f in zip(keys, floors) if f == "upper"])
        p = np.empty(len(meas))
        p[up == 0], p[up == 1] = lo, hi
        preds[f"Sionna {variant}"] = (p, 1)
        print(f"Sionna {variant}: predicted upper-minus-lower mean {p[up == 1].mean() - p[up == 0].mean():+.1f} dB")

    print(f"\n{'model':42s} {'RMSE all':>9s} {'lower':>7s} {'upper':>7s}   fitted")
    print(f"{'constant':42s} {np.std(meas):9.2f}")
    for name, (p, k) in preds.items():
        p = p + np.mean(meas - p)
        r = meas - p
        print(f"{name:42s} {np.sqrt(np.mean(r ** 2)):9.2f} {np.sqrt(np.mean(r[up == 0] ** 2)):7.2f} "
              f"{np.sqrt(np.mean(r[up == 1] ** 2)):7.2f}   {k}")


if __name__ == "__main__":
    main()
