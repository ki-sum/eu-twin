"""Phase 0 step 0-8: compare the walk-survey RSSI with the mock prediction.

Press-to-location mapping for the 2026-10-02 survey:
  - presses 1-3 belong to the R -> 1 -> R trial run and are skipped
  - then R, (1..18 with 7 and 8 swapped), R, repeated for three rounds
    (the operator walked 8 before 7 in every round)
Tripod height was 1.00 m except point 16 (1.15 m) and point 17 (1.10 m).

Models compared on the per-location mean RSSI:
  - constant: every location gets the overall mean (what "no model" gives)
  - mock + single bias: RSSI = b - (free-space loss + 8 dB per crossing),
    b absorbs TX power and antenna gains (stitching plan Phase 0 Week 2)
  - log-distance fit (extra): RSSI = b - 10 n log10(d), n fitted
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from locate_ap import aligned_frame
from mock_coverage import LOSS_PER_CROSSING_DB, build_maps, count_crossings, fspl_db
from view_scan import load_mesh

DATA = Path("data/raw/survey_2026-10-02_round1-3.jsonl")
POINTS_CSV = Path("data/derived/survey_points.csv")
AP_PATH = Path("data/derived/ap_location.npy")
OUT_CSV = Path("data/derived/survey_results.csv")
OUT_PNG = Path("data/derived/survey_results.png")

SKIP_PRESSES = 3
ROUND_ORDER = ["1", "2", "3", "4", "5", "6", "8", "7"] + [str(i) for i in range(9, 19)]
SEQUENCE = ["R"] + (ROUND_ORDER + ["R"]) * 3
HEIGHT = defaultdict(lambda: 1.00, {"16": 1.15, "17": 1.10})


def load_windows():
    """Median RSSI of each recording window, keyed by press number."""
    rssi = defaultdict(list)
    for line in DATA.open(encoding="utf-8"):
        r = json.loads(line)
        if r["state"] == 2:
            rssi[(r["point"], r["attempt"])].append(r["rssi"])
    latest = {}
    for (press, attempt), vals in rssi.items():
        if press not in latest or attempt > latest[press][0]:
            latest[press] = (attempt, vals)
    return {p: (np.median(v), len(v)) for p, (_, v) in latest.items()}


def main() -> None:
    windows = load_windows()
    presses = sorted(p for p in windows if p > SKIP_PRESSES)
    assert len(presses) == len(SEQUENCE), f"expected {len(SEQUENCE)} windows, got {len(presses)}"

    visits = defaultdict(list)
    round_of = []
    rnd = 0
    for press, label in zip(presses, SEQUENCE):
        visits[label].append(windows[press][0])
        round_of.append(rnd)
        if label == "R":
            rnd += 1

    pts = {r["label"]: (float(r["x_m"]), float(r["z_m"])) for r in csv.DictReader(POINTS_CSV.open())}
    ap = np.load(AP_PATH)
    v, *_ = aligned_frame(load_mesh())
    ceiling, _, known = build_maps(v)

    labels = ["R"] + [str(i) for i in range(1, 19)]
    xz = np.array([pts[k] for k in labels])
    crossings, _ = count_crossings(ap, xz, ceiling, known)
    rx = np.c_[xz[:, 0], [HEIGHT[k] for k in labels], xz[:, 1]]
    dist = np.linalg.norm(rx - ap, axis=1)
    pl = fspl_db(dist) + LOSS_PER_CROSSING_DB * crossings

    meas = np.array([np.mean(visits[k]) for k in labels])
    spread = np.array([np.max(visits[k]) - np.min(visits[k]) for k in labels])
    within_sd = np.sqrt(np.mean([np.var(visits[k], ddof=1) for k in labels]))

    bias = np.mean(meas + pl)
    pred = bias - pl
    resid = meas - pred
    rmse_mock = np.sqrt(np.mean(resid**2))
    rmse_const = np.std(meas)
    a_mat = np.c_[np.ones(len(dist)), -10 * np.log10(dist)]
    (b_ld, n_ld), *_ = np.linalg.lstsq(a_mat, meas, rcond=None)
    rmse_ld = np.sqrt(np.mean((meas - a_mat @ [b_ld, n_ld]) ** 2))

    print("label  dist_m  cross  visits(dBm)            mean   pred   resid")
    for i, k in enumerate(labels):
        vs = " ".join(f"{x:5.1f}" for x in visits[k])
        print(f"{k:>5}  {dist[i]:5.2f}  {crossings[i]:5d}  {vs:22s} {meas[i]:6.1f} {pred[i]:6.1f} {resid[i]:+6.1f}")
    print()
    print(f"Repeatability: pooled within-location SD across rounds {within_sd:.2f} dB, "
          f"largest spread {spread.max():.1f} dB (point {labels[int(np.argmax(spread))]})")
    print(f"R over {len(visits['R'])} visits: {', '.join(f'{x:.0f}' for x in visits['R'])} dBm")
    print(f"RMSE, constant (no model):        {rmse_const:.2f} dB")
    print(f"RMSE, mock + single bias:         {rmse_mock:.2f} dB  (bias {bias:.1f} dB)")
    print(f"RMSE, log-distance fit (extra):   {rmse_ld:.2f} dB  (exponent n = {n_ld:.2f}, free space = 2)")

    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "x_m", "z_m", "rx_height_m", "dist_m", "crossings", "visits_dbm",
                    "mean_dbm", "spread_db", "mock_pred_dbm", "residual_db"])
        for i, k in enumerate(labels):
            w.writerow([k, *xz[i], HEIGHT[k], f"{dist[i]:.2f}", crossings[i],
                        ";".join(f"{x:.1f}" for x in visits[k]), f"{meas[i]:.2f}",
                        f"{spread[i]:.1f}", f"{pred[i]:.2f}", f"{resid[i]:+.2f}"])

    fig, (a, b) = plt.subplots(1, 2, figsize=(15, 8))
    extent = [0, ceiling.shape[1] * 0.10, ceiling.shape[0] * 0.10, 0]
    a.imshow(np.where(known, 0.85, np.nan), cmap="gray", vmin=0, vmax=1, extent=extent)
    lim = max(6, np.abs(resid).max())
    sc = a.scatter(xz[:, 0], xz[:, 1], c=resid, cmap="coolwarm_r", vmin=-lim, vmax=lim, s=420, edgecolors="black")
    for i, k in enumerate(labels):
        a.text(xz[i, 0], xz[i, 1], k, ha="center", va="center", fontsize=10, fontweight="bold")
    a.plot(ap[0], ap[2], "*", ms=22, mfc="yellow", mec="black")
    a.set_title("Measured minus mock prediction (dB)\nblue = stronger than predicted, red = weaker")
    a.set_xlabel("x (m)")
    a.set_ylabel("z (m)")
    fig.colorbar(sc, ax=a, shrink=0.6, label="residual (dB)")

    order = np.argsort(dist)
    for i in range(len(labels)):
        b.plot([dist[i]] * len(visits[labels[i]]), visits[labels[i]], ".", color="gray", ms=6)
    b.plot(dist, meas, "o", color="black", label="measured (mean of rounds)")
    for i, k in enumerate(labels):
        b.annotate(k, (dist[i], meas[i]), xytext=(5, 4), textcoords="offset points", fontsize=9)
    b.plot(dist[order], pred[order], "-", color="tab:red", label=f"mock + bias (RMSE {rmse_mock:.1f} dB)")
    dd = np.linspace(dist.min(), dist.max(), 50)
    b.plot(dd, b_ld - 10 * n_ld * np.log10(dd), "--", color="tab:blue", label=f"log-distance n={n_ld:.2f} (RMSE {rmse_ld:.1f} dB)")
    b.set_xscale("log")
    b.set_xlabel("distance from router (m, log scale)")
    b.set_ylabel("RSSI (dBm)")
    b.set_title(f"RSSI vs distance - grey dots: individual rounds\nround-to-round SD {within_sd:.1f} dB")
    b.legend()
    b.grid(alpha=0.3)
    fig.savefig(OUT_PNG, dpi=110, bbox_inches="tight")
    print(f"Saved {OUT_PNG} and {OUT_CSV}")


if __name__ == "__main__":
    main()
