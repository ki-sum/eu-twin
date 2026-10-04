"""Phase 0 step 0-9 (second attempt): Sionna RT radio map at tripod height.

The path solver (scripts/sionna_predict.py) found only 1-6 paths per receiver:
exact specular paths rarely exist on a phone-scan mesh made of thousands of
small, slightly tilted triangles. The radio map solver instead shoots rays,
bounces them off whatever triangle they hit and accumulates the energy that
crosses a horizontal measurement plane, so it does not need perfect mirrors.

Prediction at a survey point = mean path gain of its cell and the 8 neighbours
(0.75 m x 0.75 m), which also smooths Monte Carlo noise. One global bias is
fitted, as for the mock.

    .venv-sionna/Scripts/python.exe scripts/sionna_radiomap.py --material plasterboard
"""

import argparse
import csv
import json
import os
import time
from pathlib import Path

os.environ.setdefault("DRJIT_LIBLLVM_PATH", str(Path("tools/llvm-20.1.8/LLVM-C.dll").resolve()))

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sionna.rt import PlanarArray, RadioMapSolver, Transmitter, load_scene  # noqa: E402

SCENE_DIR = Path("data/sionna")
RESULTS_CSV = Path("data/derived/survey_results.csv")
FREQ_HZ = 2.437e9
PLANE_HEIGHT = 1.0
CELL = 0.25
SCENE_XML = """<scene version="2.1.0">
    <bsdf type="itu-radio-material" id="mat">
        <string name="type" value="{material}"/>
        <float name="thickness" value="{thickness}"/>
    </bsdf>
    <shape type="ply" id="loft">
        <string name="filename" value="loft.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat" name="bsdf"/>
    </shape>
</scene>
"""


EXTRA_XML = """    <bsdf type="itu-radio-material" id="mat-{name}-material">
        <string name="type" value="{material}"/>
        <float name="thickness" value="{thickness}"/>
    </bsdf>
    <shape type="ply" id="obj-{name}">
        <string name="filename" value="extra_{name}.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat-{name}-material" name="bsdf"/>
    </shape>
"""


def write_extras(path: Path) -> str:
    """Write hand-added objects (aligned frame) as PLY files in Sionna's frame; return their XML."""
    xml = ""
    for obj in json.loads(path.read_text())["objects"]:
        tris = np.array(obj["triangles"], dtype=float)
        facing = np.array(obj["facing"], dtype=float)
        normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        flip = normals @ facing < 0
        tris[flip] = tris[flip][:, [0, 2, 1]]
        verts = tris.reshape(-1, 3)
        verts = np.c_[verts[:, 0], -verts[:, 2], verts[:, 1]]  # aligned -> Sionna Z-up
        lines = ["ply", "format ascii 1.0", f"element vertex {len(verts)}",
                 "property float x", "property float y", "property float z",
                 f"element face {len(tris)}", "property list uchar int vertex_indices", "end_header"]
        lines += [f"{x:.4f} {y:.4f} {z:.4f}" for x, y, z in verts]
        lines += [f"3 {3 * i} {3 * i + 1} {3 * i + 2}" for i in range(len(tris))]
        (SCENE_DIR / f"extra_{obj['name']}.ply").write_text("\n".join(lines) + "\n")
        xml += EXTRA_XML.format(name=obj["name"], material=obj["material"], thickness=obj["thickness"])
    return xml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", default="plasterboard")
    parser.add_argument("--thickness", type=float, default=0.10, help="metres")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--samples", type=int, default=4_000_000)
    parser.add_argument("--extras", type=Path, default=None, help="JSON with hand-added objects")
    args = parser.parse_args()

    xml_text = SCENE_XML.format(material=args.material, thickness=args.thickness)
    if args.extras:
        xml_text = xml_text.replace("</scene>", write_extras(args.extras) + "</scene>")
    xml = SCENE_DIR / f"loft_{args.material}{'_extras' if args.extras else ''}.xml"
    xml.write_text(xml_text)
    geo = json.loads((SCENE_DIR / "geometry.json").read_text())
    labels = list(geo["rx"])
    rx = np.array([geo["rx"][k] for k in labels])

    scene = load_scene(str(xml))
    scene.frequency = FREQ_HZ
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.add(Transmitter("router", position=geo["tx"]))

    lo = np.minimum(rx[:, :2].min(axis=0), geo["tx"][:2]) - 1.5
    hi = np.maximum(rx[:, :2].max(axis=0), geo["tx"][:2]) + 1.5
    center = [float(c) for c in (lo + hi) / 2] + [PLANE_HEIGHT]
    size = [float(s) for s in hi - lo]

    t0 = time.time()
    rm = RadioMapSolver()(scene, center=center, orientation=[0, 0, 0], size=size, cell_size=[CELL, CELL],
                          samples_per_tx=args.samples, max_depth=args.max_depth, los=True,
                          specular_reflection=True, diffuse_reflection=False, refraction=True)
    pg = np.array(rm.path_gain)[0]
    centers = np.array(rm.cell_centers)
    elapsed = time.time() - t0

    pg_db = 10 * np.log10(np.where(pg > 0, pg, np.nan))
    x0, y0 = centers[0, 0, 0] - CELL / 2, centers[0, 0, 1] - CELL / 2
    pred_db = []
    for p in rx:
        i = int((p[1] - y0) / CELL)
        j = int((p[0] - x0) / CELL)
        block = pg[max(i - 1, 0) : i + 2, max(j - 1, 0) : j + 2]
        pred_db.append(10 * np.log10(np.mean(block)))
    pred_db = np.array(pred_db)

    rows = {r["label"]: r for r in csv.DictReader(RESULTS_CSV.open())}
    meas = np.array([float(rows[k]["mean_dbm"]) for k in labels])
    mock = np.array([float(rows[k]["mock_pred_dbm"]) for k in labels])
    bias = np.mean(meas - pred_db)
    pred = bias + pred_db
    resid = meas - pred
    rmse = np.sqrt(np.mean(resid**2))
    rmse_mock = np.sqrt(np.mean((meas - mock) ** 2))
    rmse_const = np.std(meas)

    print(f"material {args.material}, thickness {args.thickness} m, max_depth {args.max_depth}, "
          f"{args.samples:,} rays, {pg.shape[1]}x{pg.shape[0]} cells: solved in {elapsed:.1f} s")
    print("label  pred   meas   resid")
    for i, k in enumerate(labels):
        print(f"{k:>5}  {pred[i]:5.1f}  {meas[i]:5.1f}  {resid[i]:+5.1f}")
    print(f"RMSE constant {rmse_const:.2f} dB | mock {rmse_mock:.2f} dB | Sionna radio map {rmse:.2f} dB (bias {bias:.1f} dB)")

    tag = f"{args.material}_d{args.max_depth}{'_extras' if args.extras else ''}"
    Path(f"data/derived/sionna_radiomap_{tag}.json").write_text(json.dumps({
        "material": args.material, "thickness_m": args.thickness, "max_depth": args.max_depth,
        "samples_per_tx": args.samples, "cell_m": CELL, "solve_seconds": round(elapsed, 1),
        "bias_db": round(float(bias), 2), "rmse_db": round(float(rmse), 2),
        "rmse_mock_db": round(float(rmse_mock), 2), "rmse_constant_db": round(float(rmse_const), 2),
        "points": {k: {"pred_dbm": round(float(pred[i]), 2), "meas_dbm": round(float(meas[i]), 2)}
                   for i, k in enumerate(labels)},
    }, indent=2))

    fig, ax = plt.subplots(figsize=(8, 10))
    extent = [x0, x0 + pg.shape[1] * CELL, y0, y0 + pg.shape[0] * CELL]
    im = ax.imshow(bias + pg_db, origin="lower", extent=extent, cmap="turbo", vmin=meas.min() - 8, vmax=meas.max() + 4)
    ax.scatter(rx[:, 0], rx[:, 1], c=meas, cmap="turbo", vmin=meas.min() - 8, vmax=meas.max() + 4, s=380, edgecolors="white", linewidths=2)
    for i, k in enumerate(labels):
        ax.text(rx[i, 0], rx[i, 1], k, ha="center", va="center", fontsize=9, fontweight="bold", color="white")
    ax.plot(geo["tx"][0], geo["tx"][1], "*", ms=22, mfc="white", mec="black")
    ax.set_title(f"Sionna radio map at {PLANE_HEIGHT} m ({args.material}, depth {args.max_depth})\n"
                 f"circles = measured; same colour scale. RMSE {rmse:.1f} dB vs mock {rmse_mock:.1f} dB")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)  (top of image = side A)")
    fig.colorbar(im, ax=ax, shrink=0.6, label="RSSI (dBm, bias-fitted)")
    out = Path(f"data/derived/sionna_radiomap_{tag}.png")
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
