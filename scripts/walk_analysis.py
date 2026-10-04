"""Attach a 3D position to every probe record of a Stray Scanner walk and compare with tripod data.

Time sync: the first and last BOOT presses (state changes in the probe stream,
PC clock) were pressed together with Stray's record and stop buttons, so the
first and last odometry frames map linearly onto them. Positions are the phone
camera, moved into the aligned frame with stray_align.py's transform; the probe
sits a few cm above the phone, which is ignored here.

    .venv/Scripts/python.exe scripts/walk_analysis.py [stray_folder probe_jsonl]
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np

FOLDER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/stray/walk_loft_2026-10-04")
PROBE = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/raw/walk_loft_2026-10-04.jsonl")
TRIPOD = Path("data/derived/survey_results.csv")
AP_PATH = Path("data/derived/ap_location.npy")
RADIUS = 0.40
HEIGHT = (0.6, 1.5)


def db_mean(v):
    return 10 * np.log10(np.mean(10 ** (np.asarray(v) / 10)))


def main() -> None:
    odo = np.genfromtxt(FOLDER / "odometry.csv", delimiter=",", skip_header=1, usecols=range(5))
    m = np.load(FOLDER / "to_aligned_opencv.npy")
    pos = odo[:, 2:5] @ m[:3, :3].T + m[:3, 3]
    st = odo[:, 0]

    rec = [json.loads(line) for line in PROBE.open()]
    pc = np.array([r["pc_time"] for r in rec])
    rssi = np.array([r["rssi"] for r in rec], dtype=float)
    pt = np.array([r["point"] for r in rec])
    marks = [i for i in range(1, len(rec)) if pt[i] != pt[i - 1]]
    t1, t2 = pc[marks[0]], pc[marks[-1]]
    scale = (t2 - t1) / (st[-1] - st[0])
    print(f"walk: {st[-1] - st[0]:.1f} s on the phone, {t2 - t1:.1f} s between BOOT presses (scale {scale:.5f})")

    # router-touch check: when is the phone closest to the router, and when is RSSI highest?
    ap = np.load(AP_PATH)
    phone_pc = t1 + (st - st[0]) * scale
    first = phone_pc < t1 + 30
    i_close = np.argmin(np.linalg.norm(pos[first] - ap, axis=1))
    w = (pc > t1) & (pc < t1 + 30)
    sec = np.floor(pc[w] - t1)
    peak = max(set(sec), key=lambda k: np.median(rssi[w][sec == k]))
    print(f"start: phone closest to router ({np.linalg.norm(pos[first][i_close] - ap):.2f} m) at +{phone_pc[first][i_close] - t1:.1f} s, "
          f"strongest RSSI second at +{peak:.0f}-{peak + 1:.0f} s")

    inside = (pc >= t1) & (pc <= t2)
    xyz = np.c_[[np.interp(pc[inside], phone_pc, pos[:, k]) for k in range(3)]].T
    vals = rssi[inside]
    np.savez(FOLDER / "walk_samples.npz", xyz=xyz, rssi=vals, pc=pc[inside])
    print(f"{len(vals):,} probe records placed; height of the phone: median {np.median(xyz[:, 1]):.2f} m, "
          f"10-90% {np.percentile(xyz[:, 1], 10):.2f}-{np.percentile(xyz[:, 1], 90):.2f} m")

    rows = list(csv.DictReader(TRIPOD.open()))
    print(f"\npoint  tripod   walk(r={RADIUS} m)  n      diff   seconds")
    diffs = []
    for r in rows:
        x, z = float(r["x_m"]), float(r["z_m"])
        sel = (np.hypot(xyz[:, 0] - x, xyz[:, 2] - z) < RADIUS) & (xyz[:, 1] > HEIGHT[0]) & (xyz[:, 1] < HEIGHT[1])
        tri = float(r["mean_dbm"])
        if sel.sum() < 25:
            print(f"{r['label']:>5}  {tri:6.1f}   (fewer than 25 samples: {sel.sum()})")
            continue
        wv = db_mean(vals[sel])
        diffs.append((r["label"], tri, wv))
        print(f"{r['label']:>5}  {tri:6.1f}   {wv:6.1f}        {sel.sum():5d}  {wv - tri:+5.1f}   {sel.sum() / 50:5.1f}")
    d = np.array([w - t for _, t, w in diffs])
    tr = np.array([t for _, t, _ in diffs]); wk = np.array([w for _, _, w in diffs])
    print(f"\n{len(d)} points with data: walk minus tripod mean {d.mean():+.1f} dB, SD {d.std():.1f} dB, "
          f"correlation {np.corrcoef(tr, wk)[0, 1]:.2f}")


if __name__ == "__main__":
    main()
