"""BLE vs Wi-Fi RSSI on the same phone during one walk (no positions needed).

The router-side transmitter for BLE is an iPhone running LightBlue (virtual
"Heart Rate" peripheral) placed next to the router. iOS rotates its private
address, so pass every address the iPhone used during the walk (on the
2026-10-04 walk it changed once, at ~107 s; the new one was identified because
it appears as the old one stops and peaks when the walker returns to the
router). Wi-Fi is the phone's own RSSI for the connected router, which Android
refreshes only every ~2 s.

    .venv/Scripts/python.exe scripts/ble_vs_wifi.py data/android/walk_p30_2026-10-04 ADDR1 [ADDR2 ...]
"""

import csv
import sys
from pathlib import Path

import numpy as np


def power_mean(v):
    return 10 * np.log10(np.mean(10 ** (np.asarray(v) / 10)))


def main() -> None:
    folder = Path(sys.argv[1])
    beacon_addresses = set(sys.argv[2:])
    poses = list(csv.DictReader(open(folder / "poses.csv")))
    t0 = int(poses[0]["t_ns"])
    pt = np.array([(int(r["t_ns"]) - t0) / 1e9 for r in poses])
    py = np.array([float(r["ty"]) for r in poses])
    wifi = [r for r in csv.DictReader(open(folder / "wifi.csv")) if r["source"] == "poll"]
    wt = np.array([(int(r["t_ns"]) - t0) / 1e9 for r in wifi])
    wr = np.array([float(r["rssi"]) for r in wifi])
    ble = [r for r in csv.DictReader(open(folder / "ble.csv")) if r["address"] in beacon_addresses]
    bt = np.array([(int(r["t_ns"]) - t0) / 1e9 for r in ble])
    br = np.array([float(r["rssi"]) for r in ble])

    for win in (5, 10, 20):
        w, b, y = [], [], []
        for s in np.arange(0, pt[-1], win):
            mw = (wt >= s) & (wt < s + win)
            mb = (bt >= s) & (bt < s + win)
            if mw.any() and mb.sum() >= 3:
                w.append(power_mean(wr[mw]))
                b.append(power_mean(br[mb]))
                y.append(py[(pt >= s) & (pt < s + win)].mean())
        w, b, y = map(np.array, (w, b, y))
        offset = np.mean(b - w)
        rmse = np.sqrt(np.mean((b - w - offset) ** 2))
        slope = np.polyfit(w, b, 1)[0]
        print(f"window {win:2d} s: {len(w)} windows, corr {np.corrcoef(w, b)[0, 1]:.2f}, "
              f"slope {slope:.2f}, BLE - WiFi offset {offset:.1f} dB, RMSE after offset {rmse:.1f} dB")
        if win == 10:
            lower = y < -0.5
            print(f"   upper-minus-lower floor: WiFi {w[~lower].mean() - w[lower].mean():.1f} dB, "
                  f"BLE {b[~lower].mean() - b[lower].mean():.1f} dB ({lower.sum()} lower-floor windows)")


if __name__ == "__main__":
    main()
