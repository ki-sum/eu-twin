"""Compare the bathroom session (2026-10-03) with the mock and Sionna RT.

Press-to-point mapping from the operator's notes: 27 windows =
R, 11 x3, 9 x3, 7 x4, B1 x3, B2 x3, B3 x3, B4 x3, B5 x3, R
(unsure whether 9 had 2 or 3 and 7 had 3 or 4 presses; only 3 + 4 adds up
to the 27 recorded windows; B4 was walked before B5).
Local mean = mean linear power over a point's sub-positions. Models are
averaged the same way over the planned sub-positions (centre, 20 cm towards A,
20 cm towards B). One global bias per model.
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from mock_coverage import fspl_db

DATA = Path("data/raw/bathroom_2026-10-03.jsonl")
GEO = Path("data/sionna/bath/geometry.json")
SEQ = ["R"] + ["11"] * 3 + ["9"] * 3 + ["7"] * 4 + ["B1"] * 3 + ["B2"] * 3 + ["B3"] * 3 + ["B4"] * 3 + ["B5"] * 3 + ["R"]
POINTS = ["R", "11", "9", "7", "B1", "B2", "B3", "B4", "B5"]
INSIDE = ["B1", "B2", "B3", "B4", "B5"]
OUTSIDE = ["7", "9", "11"]
LOSS_PER_CROSSING_DB = 8.0
# wall centre lines in the aligned frame (x, z): door wall incl. the closed door, C-side wall
WALLS = [((5.44, 0.30), (5.44, 3.90)), ((5.44, 3.90), (7.10, 3.90))]


def db_mean(values_db):
    return 10 * np.log10(np.mean(10 ** (np.asarray(values_db) / 10)))


def crosses(p, q, a, b):
    def orient(u, v, w):
        return np.sign((v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0]))
    return orient(p, q, a) != orient(p, q, b) and orient(a, b, p) != orient(a, b, q)


def main() -> None:
    windows = defaultdict(list)
    for line in DATA.open(encoding="utf-8"):
        r = json.loads(line)
        if r["state"] == 2:
            windows[r["point"]].append(r["rssi"])
    presses = sorted(windows)
    assert len(presses) == len(SEQ), f"{len(presses)} windows, expected {len(SEQ)}"
    subs = defaultdict(list)
    for p, label in zip(presses, SEQ):
        subs[label].append(float(np.median(windows[p])))
    meas = np.array([db_mean(subs[k]) for k in POINTS])

    geo = json.loads(GEO.read_text())
    tx = np.array(geo["tx"])  # Sionna frame (X, Y, Z up); aligned (x, z) = (X, -Y)
    tx_xz = (tx[0], -tx[1])
    mock, n_cross = [], []
    for k in POINTS:
        pls, cr = [], []
        for name, p in geo["rx"].items():
            if name.split("_")[0] != k:
                continue
            c = sum(crosses(tx_xz, (p[0], -p[1]), a, b) for a, b in WALLS)
            pls.append(-(fspl_db(np.linalg.norm(np.array(p) - tx)) + LOSS_PER_CROSSING_DB * c))
            cr.append(c)
        mock.append(db_mean(pls))
        n_cross.append(np.mean(cr))
    models = {"mock (8 dB/crossing)": np.array(mock)}
    for variant in ("plain", "brick"):
        pg = json.loads(Path(f"data/derived/sionna_bathroom_{variant}.json").read_text())["path_gain_db"]
        models[f"Sionna {variant}"] = np.array([db_mean([v for n, v in pg.items() if n.split("_")[0] == k]) for k in POINTS])

    idx_in = [POINTS.index(k) for k in INSIDE]
    idx_out = [POINTS.index(k) for k in OUTSIDE]
    print("point  crossings  measured  " + "  ".join(f"{m:>20s}" for m in models))
    fitted = {}
    for m, pred in models.items():
        fitted[m] = pred + np.mean(meas - pred)
    for i, k in enumerate(POINTS):
        print(f"{k:>5}  {n_cross[i]:9.1f}  {meas[i]:8.1f}  " + "  ".join(f"{fitted[m][i]:20.1f}" for m in models))
    print()
    gap_meas = db_mean(meas[idx_out]) - db_mean(meas[idx_in])
    print(f"{'model':22s} RMSE (dB)  outside-minus-inside (dB)")
    print(f"{'measured':22s}     -      {gap_meas:5.1f}")
    print(f"{'constant (no model)':22s} {np.std(meas):6.2f}      0.0")
    for m, pred in models.items():
        rmse = np.sqrt(np.mean((meas - fitted[m]) ** 2))
        gap = db_mean(pred[idx_out]) - db_mean(pred[idx_in])
        print(f"{m:22s} {rmse:6.2f}     {gap:5.1f}")
    Path("data/derived/bathroom_results.json").write_text(json.dumps({
        "points": POINTS, "measured_dbm": meas.round(2).tolist(), "sub_positions_dbm": subs,
        "models_fitted_dbm": {m: v.round(2).tolist() for m, v in fitted.items()},
        "outside_minus_inside_measured_db": round(float(gap_meas), 2),
    }, indent=2))


if __name__ == "__main__":
    main()
