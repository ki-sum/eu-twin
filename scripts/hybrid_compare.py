"""Hybrid model: Sionna on the router's own floor, free space + slab step on the other floor.

The slab step is learned on the TP-Link walk (router upstairs) and carried over
unchanged to the Xiaomi walks (router downstairs); each router gets its own
global bias (different transmit power). Compared with the simple model
(free space + step everywhere) and Sionna everywhere (concrete slab + brick).
"""

import numpy as np

from mock_coverage import fspl_db
from xiaomi_both import sionna_at, walk_cells

ROUTERS = {
    "TP-Link (upstairs)": dict(
        tx=np.array([2.815, 0.858, 7.302]), own="upper",
        walks=[("upper", "data/stray/walk_house_2026-10-04", "data/raw/walk_house_2026-10-04.jsonl", lambda y: y > 0.3),
               ("lower", "data/stray/walk_house_2026-10-04", "data/raw/walk_house_2026-10-04.jsonl", lambda y: y < -0.3)],
        sionna={"upper": "data/derived/sionna_house_physics_tp_up.npz", "lower": "data/derived/sionna_house_physics.npz"}),
    "Xiaomi (downstairs)": dict(
        tx=np.array([5.5, -2.38, 8.4]), own="lower",
        walks=[("lower", "data/stray/walk_xiaomi_2026-10-04", "data/raw/walk_xiaomi_2026-10-04.jsonl", lambda y: y < -0.3),
               ("upper", "data/stray/walk_xiaomi_up_2026-10-04", "data/raw/walk_xiaomi_up_2026-10-04.jsonl", lambda y: y > 0.3)],
        sionna={"lower": "data/derived/sionna_house_physics_xiaomi.npz", "upper": "data/derived/sionna_house_physics_xiaomi_up.npz"}),
}


def load(r):
    meas, same, fs, sio = [], [], [], []
    for floor, folder, probe, keep in r["walks"]:
        cells = walk_cells(folder, probe, keep)
        keys = [c[0] for c in cells]
        pos = np.array([c[2] for c in cells])
        meas += [c[1] for c in cells]
        same += [floor == r["own"]] * len(cells)
        fs += list(-fspl_db(np.maximum(np.linalg.norm(pos - r["tx"], axis=1), 0.3)))
        sio += list(sionna_at(r["sionna"][floor], keys))
    return np.array(meas), np.array(same), np.array(fs), np.array(sio)


def rmse(meas, pred, same):
    pred = pred + np.mean(meas - pred)
    r = meas - pred
    return np.sqrt(np.mean(r ** 2)), np.sqrt(np.mean(r[same] ** 2)), np.sqrt(np.mean(r[~same] ** 2))


def main() -> None:
    data = {name: load(r) for name, r in ROUTERS.items()}
    meas, same, fs, sio = data["TP-Link (upstairs)"]
    other = (~same).astype(float)
    a = np.c_[np.ones(len(meas)), -other]
    (_, s_hyb), *_ = np.linalg.lstsq(a, meas - np.where(same, sio, fs), rcond=None)
    a2 = np.c_[np.ones(len(meas)), -other]
    (_, s_simple), *_ = np.linalg.lstsq(a2, meas - fs, rcond=None)
    print(f"learned on the TP-Link walk: slab step {s_simple:.1f} dB (simple), {s_hyb:.1f} dB (hybrid)\n")

    print(f"{'router':20s} {'model':38s} {'all':>6s} {'same fl.':>9s} {'other fl.':>10s}")
    for name, (m, sm, f, s) in data.items():
        tag = "(fitted here)" if name.startswith("TP") else "(carried over)"
        rows = [(f"simple: FSPL + {s_simple:.1f} dB step {tag}", np.where(sm, f, f - s_simple)),
                ("Sionna everywhere", s),
                (f"hybrid: Sionna + {s_hyb:.1f} dB step {tag}", np.where(sm, s, f - s_hyb))]
        print(f"{name:20s} cells: same floor {int(sm.sum())}, other floor {int((~sm).sum())}")
        for label, pred in rows:
            a_, b_, c_ = rmse(m, pred, sm)
            print(f"{'':20s} {label:38s} {a_:6.2f} {b_:9.2f} {c_:10.2f}")


if __name__ == "__main__":
    main()
