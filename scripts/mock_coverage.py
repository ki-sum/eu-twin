"""Phase 0 mock coverage map: free-space path loss + fixed loss per structural crossing.

Structure is taken from a 2.5D height map of the scan instead of labelling
walls: a straight line from the AP to a receiver is "inside" while it stays
below the ceiling/roof height of every cell it passes over and stays within
the scanned floor area. Each stretch where it leaves that volume counts as
one crossing. Furniture sits below the ceiling and is therefore ignored,
which is deliberate for this baseline.

Output is path loss in dB relative to nothing (no TX power assumed): the
unknown TX power and antenna gains are later absorbed by the single global
bias fitted against measurements (Phase 0 step 0-8).
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy import ndimage

from locate_ap import aligned_frame
from view_scan import load_mesh

AP_PATH = Path("data/derived/ap_location.npy")
OUT_PNG = Path("data/derived/mock_coverage.png")
OUT_NPZ = Path("data/derived/mock_coverage.npz")

FREQ_HZ = 2.437e9  # 2.4 GHz channel 6; channels 1-11 differ by <0.2 dB in FSPL
RX_HEIGHT = 1.0  # metres; hand-held ESP32 during the walk survey
CELL = 0.10  # metres per grid cell
STEP = 0.05  # metres between samples along each ray
# Placeholder from our internal project plan (Phase 0 Week 1
# step 4). Not taken from a measurement source; replaced by fitted values later.
LOSS_PER_CROSSING_DB = 8.0
MIN_DISTANCE = 0.3  # metres; free-space formula is not meaningful closer than this


def fspl_db(d):
    """Free-space path loss (Friis), d in metres."""
    return 20 * np.log10(d) + 20 * np.log10(FREQ_HZ) - 147.55


def build_maps(v):
    ix = (v[:, 0] / CELL).astype(int)
    iz = (v[:, 2] / CELL).astype(int)
    shape = (iz.max() + 1, ix.max() + 1)
    ceiling = np.full(shape, -np.inf)
    floor = np.full(shape, np.inf)
    np.maximum.at(ceiling, (iz, ix), v[:, 1])
    np.minimum.at(floor, (iz, ix), v[:, 1])

    known = ndimage.binary_closing(np.isfinite(ceiling), iterations=2)
    known = ndimage.binary_fill_holes(known)
    # Skylight glass and other unscanned ceiling patches leave low values; take
    # the local maximum so the roof stays continuous over them.
    ceiling = ndimage.grey_closing(np.where(np.isfinite(ceiling), ceiling, 0.0), size=7)
    ceiling[~known] = 0.0
    floor = np.where(np.isfinite(floor), floor, np.nan)
    return ceiling, floor, known


def count_crossings(ap, rx_xz, ceiling, known):
    """Number of separate obstructed stretches on the straight line AP -> each receiver."""
    rx = np.c_[rx_xz[:, 0], np.full(len(rx_xz), RX_HEIGHT), rx_xz[:, 1]]
    length = np.linalg.norm(rx - ap, axis=1)
    n_samples = int(np.ceil(length.max() / STEP)) + 1
    t = np.linspace(0.0, 1.0, n_samples)
    pts = ap[None, None, :] + t[None, :, None] * (rx - ap)[:, None, :]
    cx = np.clip((pts[..., 0] / CELL).astype(int), 0, ceiling.shape[1] - 1)
    cz = np.clip((pts[..., 2] / CELL).astype(int), 0, ceiling.shape[0] - 1)
    blocked = ~known[cz, cx] | (pts[..., 1] > ceiling[cz, cx])
    starts = blocked[:, 1:] & ~blocked[:, :-1]
    return starts.sum(axis=1) + blocked[:, 0], length


def main() -> None:
    v, *_ = aligned_frame(load_mesh())
    ap = np.load(AP_PATH)
    ceiling, floor, known = build_maps(v)

    rx_ok = known & (floor > -0.3) & (floor < 0.9) & (ceiling > RX_HEIGHT + 0.2)
    iz, ix = np.nonzero(rx_ok)
    rx_xz = np.c_[(ix + 0.5) * CELL, (iz + 0.5) * CELL]

    crossings, dist = count_crossings(ap, rx_xz, ceiling, known)
    loss = fspl_db(np.maximum(dist, MIN_DISTANCE)) + LOSS_PER_CROSSING_DB * crossings

    loss_map = np.full(ceiling.shape, np.nan)
    loss_map[iz, ix] = loss
    cross_map = np.full(ceiling.shape, np.nan)
    cross_map[iz, ix] = crossings
    np.savez(OUT_NPZ, loss=loss_map, crossings=cross_map, ceiling=ceiling, known=known, cell=CELL, ap=ap)

    print(f"Receiver cells: {len(rx_xz)} ({len(rx_xz) * CELL**2:.1f} m2 where a hand-held probe fits)")
    print(f"Path loss: min {loss.min():.1f} dB, median {np.median(loss):.1f} dB, max {loss.max():.1f} dB")
    for k in range(int(crossings.max()) + 1):
        share = np.mean(crossings == k) * 100
        print(f"  {k} crossing(s): {share:5.1f}% of cells")

    extent = [0, ceiling.shape[1] * CELL, ceiling.shape[0] * CELL, 0]
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 8))
    outline = np.where(known, 0.85, np.nan)
    for ax in (a, b):
        ax.imshow(outline, cmap="gray", vmin=0, vmax=1, extent=extent)
        ax.plot(ap[0], ap[2], "*", ms=20, mfc="red", mec="black")
        ax.set_xlabel("x (m)")
        ax.set_ylabel("z (m)")
    im = a.imshow(loss_map, cmap="turbo_r", extent=extent)
    a.set_title(f"Predicted path loss at {RX_HEIGHT} m height (dB)\nfree space + {LOSS_PER_CROSSING_DB:.0f} dB per crossing")
    fig.colorbar(im, ax=a, shrink=0.6, label="path loss (dB) - lower is stronger signal")
    im2 = b.imshow(cross_map, cmap="Oranges", vmin=0, vmax=max(2, crossings.max()), extent=extent)
    b.set_title("Structural crossings on the direct line from the AP")
    fig.colorbar(im2, ax=b, shrink=0.6, label="number of crossings")
    fig.savefig(OUT_PNG, dpi=110, bbox_inches="tight")
    print(f"Saved {OUT_PNG}")


if __name__ == "__main__":
    main()
