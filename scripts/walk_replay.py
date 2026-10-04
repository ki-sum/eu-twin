"""Animated replay of the two-floor TP-Link walk: measured RSSI vs four models.

Top: plan views of both floors (wall-height slice of the walk's TSDF mesh, so
furniture is left out), the walker's trail coloured by measured RSSI.
Bottom: measured RSSI (1.5 s power average) and the four model predictions
along the walk, plus each model's running RMS error so far.

Models, each with one global bias fitted over the whole walk:
  free space   distance only
  calibrated   free space + slab step (13.6 dB, learned on this walk)
  Sionna RT    radio maps on the phone-scan mesh (concrete slab + brick)
  hybrid       Sionna on the router's floor, free space + 16.7 dB step below

    .venv/Scripts/python.exe scripts/walk_replay.py --preview 300   # one frame at t = 300 s
    .venv/Scripts/python.exe scripts/walk_replay.py                 # MP4 (needs ffmpeg)
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from matplotlib.animation import FFMpegWriter  # noqa: E402

from mock_coverage import fspl_db  # noqa: E402

SAMPLES = Path("data/stray/walk_house_2026-10-04/walk_samples.npz")
MESH = Path("data/stray/walk_house_2026-10-04/tsdf_mesh_aligned.ply")
SIONNA = {"upper": Path("data/derived/sionna_house_physics_tp_up.npz"),
          "lower": Path("data/derived/sionna_house_physics.npz")}
TX = np.array([2.815, 0.858, 7.302])
STEP_SIMPLE, STEP_HYBRID = 13.6, 16.7
FLOOR_SPLIT = -0.14          # middle of the slab
LOWER_FLOOR, UPPER_FLOOR = -2.68, 0.02
SMOOTH_S = 1.5
SPEED = 12                   # seconds of walk per second of video
FPS = 30
OUT = Path("data/derived/walk_replay_tplink.mp4")

COLORS = {"measured": "#1c2226", "free space": "#9aa3a8", "calibrated": "#1f8a70",
          "Sionna RT": "#e07a1f", "hybrid": "#6b4fbb"}
MODELS = ["free space", "calibrated", "Sionna RT", "hybrid"]


def power_mean(v):
    return 10 * np.log10(np.mean(10 ** (np.asarray(v) / 10)))


def sionna_lookup(path, xyz):
    z = np.load(path)
    gx, gz, pg = z["x"], z["z"], z["path_gain"]
    xs, zs = np.unique(gx), np.unique(gz)
    ix = np.clip(np.searchsorted(xs, xyz[:, 0]) - 1, 0, len(xs) - 1)
    iz = np.clip(np.searchsorted(zs, xyz[:, 2]) - 1, 0, len(zs) - 1)
    inside = (xyz[:, 0] >= xs[0]) & (xyz[:, 0] <= xs[-1] + 0.25) & (xyz[:, 2] >= zs[0]) & (xyz[:, 2] <= zs[-1] + 0.25)
    grid = {(round(a, 3), round(b, 3)): v for a, b, v in zip(gx.ravel(), gz.ravel(), pg.ravel())}
    out = np.full(len(xyz), np.nan)
    for k in np.where(inside)[0]:
        v = grid.get((round(xs[ix[k]], 3), round(zs[iz[k]], 3)), 0.0)
        if v > 0:
            out[k] = 10 * np.log10(v)
    return out


def wall_points(mesh, floor_y):
    v = np.asarray(mesh.vertices)
    sel = (v[:, 1] > floor_y + 1.0) & (v[:, 1] < floor_y + 1.7)
    p = v[sel][:, [0, 2]]
    keys = np.unique(np.floor(p / 0.04).astype(int), axis=0)
    return (keys + 0.5) * 0.04


def build_series():
    s = np.load(SAMPLES)
    t = s["pc"] - s["pc"][0]
    xyz, rssi = s["xyz"], s["rssi"].astype(float)
    order = np.argsort(t)
    t, xyz, rssi = t[order], xyz[order], rssi[order]

    grid_t = np.arange(0, t[-1], 1 / FPS * SPEED / 2)
    meas, pos = [], []
    for g in grid_t:
        sel = (t >= g - SMOOTH_S / 2) & (t < g + SMOOTH_S / 2)
        meas.append(power_mean(rssi[sel]) if sel.any() else np.nan)
        pos.append(xyz[np.argmin(np.abs(t - g))])
    meas, pos = np.array(meas), np.array(pos)
    upper = pos[:, 1] > FLOOR_SPLIT

    fs = -fspl_db(np.maximum(np.linalg.norm(pos - TX, axis=1), 0.3))
    sio = np.where(upper, sionna_lookup(SIONNA["upper"], pos), sionna_lookup(SIONNA["lower"], pos))
    raw = {"free space": fs,
           "calibrated": np.where(upper, fs, fs - STEP_SIMPLE),
           "Sionna RT": sio,
           "hybrid": np.where(upper, sio, fs - STEP_HYBRID)}
    pred = {}
    for name, p in raw.items():
        ok = np.isfinite(p) & np.isfinite(meas)
        pred[name] = p + np.mean(meas[ok] - p[ok])
    return grid_t, meas, pos, upper, pred


def running_rmse(meas, p, upto):
    m, q = meas[:upto + 1], p[:upto + 1]
    ok = np.isfinite(m) & np.isfinite(q)
    return np.sqrt(np.mean((m[ok] - q[ok]) ** 2)) if ok.sum() > 5 else np.nan


def make_figure(mesh):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig = plt.figure(figsize=(10.8, 10.8), dpi=100, facecolor="#f6f7f5")
    gs = fig.add_gridspec(3, 3, height_ratios=[1.35, 1, 0.06], width_ratios=[1, 1, 0.72],
                          left=0.08, right=0.97, top=0.9, bottom=0.05, hspace=0.32, wspace=0.18)
    ax_up, ax_lo = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])
    ax_ts = fig.add_subplot(gs[1, :2])
    ax_tab = fig.add_subplot(gs[:2, 2])
    fig.text(0.05, 0.955, "One walk through a two-storey house: measured Wi-Fi vs four models",
             fontsize=17, weight="bold", color=COLORS["measured"])
    fig.text(0.05, 0.925, "2.4 GHz, router upstairs. ESP32 probe on a phone, positions from iPhone LiDAR.",
             fontsize=11, color="#5b6469")
    fig.text(0.05, 0.012, "github.com/ki-sum/eu-twin", fontsize=11, color="#5b6469")
    for ax, name, fy in ((ax_up, "Upper floor (attic)", UPPER_FLOOR), (ax_lo, "Lower floor", LOWER_FLOOR)):
        w = wall_points(mesh, fy)
        ax.scatter(w[:, 0], w[:, 1], s=0.4, c="#c3c8c6", linewidths=0)
        ax.set_title(name, fontsize=12, loc="left", color=COLORS["measured"])
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.set_facecolor("#f6f7f5")
    ax_up.plot(TX[0], TX[2], marker="^", ms=13, color="#c0392b", mec="white", zorder=5)
    ax_up.annotate("router", (TX[0], TX[2]), xytext=(8, -14), textcoords="offset points", fontsize=10, color="#c0392b")
    return fig, ax_up, ax_lo, ax_ts, ax_tab


def render(preview_t=None):
    grid_t, meas, pos, upper, pred = build_series()
    mesh = trimesh.load(MESH, process=False)
    fig, ax_up, ax_lo, ax_ts, ax_tab = make_figure(mesh)
    vmin, vmax = -80, -30
    lo = np.nanmin(np.r_[meas, *pred.values()]) - 2
    hi = np.nanmax(np.r_[meas, *pred.values()]) + 2
    window = 90.0

    trail_up = ax_up.scatter([], [], s=6, c=[], cmap="viridis", vmin=vmin, vmax=vmax, linewidths=0)
    trail_lo = ax_lo.scatter([], [], s=6, c=[], cmap="viridis", vmin=vmin, vmax=vmax, linewidths=0)
    cax = fig.add_axes([0.08, 0.47, 0.25, 0.012])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=plt.Normalize(vmin, vmax), cmap="viridis"), cax=cax,
                      orientation="horizontal")
    cb.set_label("trail colour: measured RSSI (dBm)", fontsize=9, color="#5b6469")
    cb.ax.tick_params(labelsize=8)
    cb.outline.set_visible(False)
    dot_up, = ax_up.plot([], [], "o", ms=12, color="#1c2226", mec="white", mew=2, zorder=6)
    dot_lo, = ax_lo.plot([], [], "o", ms=12, color="#1c2226", mec="white", mew=2, zorder=6)
    for ax, sel in ((ax_up, upper), (ax_lo, ~upper)):
        p = pos[sel]
        ax.set_xlim(p[:, 0].min() - 0.8, p[:, 0].max() + 0.8)
        ax.set_ylim(p[:, 2].max() + 0.8, p[:, 2].min() - 0.8)

    lines = {}
    for name in MODELS:
        lines[name], = ax_ts.plot([], [], color=COLORS[name], lw=1.8,
                                  ls="--" if name == "free space" else "-", label=name)
    lines["measured"], = ax_ts.plot([], [], color=COLORS["measured"], lw=2.6, label="measured")
    ax_ts.set_ylim(lo, hi)
    ax_ts.set_ylabel("RSSI (dBm)")
    ax_ts.set_xlabel("walk time (s)")
    ax_ts.grid(alpha=0.25)
    ax_ts.set_facecolor("#ffffff")
    for sp in ("top", "right"):
        ax_ts.spines[sp].set_visible(False)
    ax_ts.legend(loc="lower left", ncol=5, fontsize=9, frameon=False)
    floor_txt = ax_ts.text(0.99, 0.95, "", transform=ax_ts.transAxes, ha="right", va="top", fontsize=11,
                           color="#5b6469")

    ax_tab.axis("off")
    tab_txt = {}
    y = 0.97
    ax_tab.text(0, y, "now", fontsize=11, color="#5b6469", transform=ax_tab.transAxes)
    rows = ["measured"] + MODELS
    for i, name in enumerate(rows):
        yy = y - 0.07 - i * 0.075
        ax_tab.text(0, yy, name, fontsize=12, color=COLORS[name], weight="bold", transform=ax_tab.transAxes)
        tab_txt[name] = ax_tab.text(1, yy, "", fontsize=13, ha="right", color=COLORS[name],
                                    transform=ax_tab.transAxes, family="DejaVu Sans Mono")
    y2 = y - 0.07 - len(rows) * 0.075 - 0.06
    ax_tab.text(0, y2, "RMS error so far", fontsize=11, color="#5b6469", transform=ax_tab.transAxes)
    bars, bar_txt = {}, {}
    for i, name in enumerate(MODELS):
        yy = y2 - 0.075 - i * 0.075
        ax_tab.text(0, yy, name, fontsize=11, color=COLORS[name], transform=ax_tab.transAxes)
        bars[name] = ax_tab.add_patch(plt.Rectangle((0.0, yy - 0.032), 0, 0.022, color=COLORS[name],
                                                    transform=ax_tab.transAxes, clip_on=False))
        bar_txt[name] = ax_tab.text(1, yy, "", fontsize=12, ha="right", color=COLORS[name],
                                    transform=ax_tab.transAxes, family="DejaVu Sans Mono")
    ax_tab.text(0, 0.0, "Each model has one constant offset\nfitted over the whole walk.\n"
                "Sionna runs on the rough phone-scan\nmesh, not on clean building plans.",
                fontsize=9.5, color="#5b6469", transform=ax_tab.transAxes, va="bottom")

    def draw(k):
        tnow = grid_t[k]
        seen = slice(0, k + 1)
        for scat, sel in ((trail_up, upper[seen]), (trail_lo, ~upper[seen])):
            p = pos[seen][sel]
            scat.set_offsets(p[:, [0, 2]] if len(p) else np.empty((0, 2)))
            scat.set_array(meas[seen][sel])
        if upper[k]:
            dot_up.set_data([pos[k, 0]], [pos[k, 2]])
            dot_lo.set_data([], [])
        else:
            dot_lo.set_data([pos[k, 0]], [pos[k, 2]])
            dot_up.set_data([], [])
        x0 = max(0.0, tnow - window * 0.8)
        ax_ts.set_xlim(x0, x0 + window)
        lines["measured"].set_data(grid_t[seen], meas[seen])
        for name in MODELS:
            lines[name].set_data(grid_t[seen], pred[name][seen])
        floor_txt.set_text("upper floor" if upper[k] else "lower floor (through the concrete slab)")
        fmt = lambda v: "   -  " if not np.isfinite(v) else f"{v:6.1f}"
        tab_txt["measured"].set_text(fmt(meas[k]) + " dBm")
        for name in MODELS:
            tab_txt[name].set_text(fmt(pred[name][k]) + " dBm")
            e = running_rmse(meas, pred[name], k)
            bars[name].set_width(0 if not np.isfinite(e) else min(e, 12) / 12 * 0.62)
            bars[name].set_x(0.0)
            bar_txt[name].set_text("" if not np.isfinite(e) else f"{e:4.1f} dB")

    if preview_t is not None:
        k = int(np.argmin(np.abs(grid_t - preview_t)))
        draw(k)
        out = OUT.with_name(f"walk_replay_preview_{int(preview_t)}s.png")
        fig.savefig(out, facecolor=fig.get_facecolor())
        print("saved", out)
        return
    step = 2  # grid runs at twice the video frame rate
    writer = FFMpegWriter(fps=FPS, bitrate=6000)
    with writer.saving(fig, str(OUT), dpi=100):
        for k in range(0, len(grid_t), step):
            draw(k)
            writer.grab_frame(facecolor=fig.get_facecolor())
    print("saved", OUT)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=float, default=None, help="render one frame at this walk time (s)")
    args = ap.parse_args()
    render(args.preview)


if __name__ == "__main__":
    main()
