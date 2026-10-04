"""Phase 0 step 0-9: Sionna RT prediction at the survey points, compared with measurements.

Run with the Sionna environment (CPU / LLVM backend on this PC):

    .venv-sionna/Scripts/python.exe scripts/sionna_predict.py --material plasterboard

The whole scan mesh gets one ITU material (furniture included); this is the
crudest physically based model and is meant to be compared against the mock
(free space + 8 dB per crossing). Received power is the incoherent sum of all
path powers, i.e. small-scale fading is averaged out. A single global bias is
fitted, exactly as for the mock, so only the spatial pattern is compared.
"""

import argparse
import csv
import json
import os
import time
from pathlib import Path

os.environ.setdefault("DRJIT_LIBLLVM_PATH", str(Path("tools/llvm-18.1.8/LLVM-C.dll").resolve()))

import numpy as np  # noqa: E402
from sionna.rt import PathSolver, PlanarArray, Receiver, Transmitter, load_scene  # noqa: E402

SCENE_DIR = Path("data/sionna")
RESULTS_CSV = Path("data/derived/survey_results.csv")
FREQ_HZ = 2.437e9
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", default="plasterboard")
    parser.add_argument("--thickness", type=float, default=0.10, help="metres")
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--samples", type=int, default=1_000_000)
    args = parser.parse_args()

    xml = SCENE_DIR / f"loft_{args.material}.xml"
    xml.write_text(SCENE_XML.format(material=args.material, thickness=args.thickness))
    geo = json.loads((SCENE_DIR / "geometry.json").read_text())

    scene = load_scene(str(xml))
    scene.frequency = FREQ_HZ
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.add(Transmitter("router", position=geo["tx"]))
    labels = list(geo["rx"])
    for k in labels:
        scene.add(Receiver(f"rx_{k}", position=geo["rx"][k]))

    t0 = time.time()
    paths = PathSolver()(scene, max_depth=args.max_depth, samples_per_src=args.samples,
                         los=True, specular_reflection=True, diffuse_reflection=False, refraction=True)
    a, _ = paths.cir(out_type="numpy")
    elapsed = time.time() - t0

    a = np.asarray(a).reshape(a.shape[0], -1)  # receivers x (everything else)
    pg_db = 10 * np.log10(np.sum(np.abs(a) ** 2, axis=1))
    n_paths = np.count_nonzero(np.abs(a) > 0, axis=1)

    rows = {r["label"]: r for r in csv.DictReader(RESULTS_CSV.open())}
    meas = np.array([float(rows[k]["mean_dbm"]) for k in labels])
    mock = np.array([float(rows[k]["mock_pred_dbm"]) for k in labels])
    bias = np.mean(meas - pg_db)
    pred = bias + pg_db
    resid = meas - pred
    rmse = np.sqrt(np.mean(resid**2))
    rmse_mock = np.sqrt(np.mean((meas - mock) ** 2))
    rmse_const = np.std(meas)

    print(f"material {args.material}, thickness {args.thickness} m, max_depth {args.max_depth}, "
          f"{args.samples:,} rays: solved in {elapsed:.1f} s")
    print("label  paths  path_gain_dB  pred   meas   resid")
    for i, k in enumerate(labels):
        print(f"{k:>5}  {n_paths[i]:5d}  {pg_db[i]:12.1f}  {pred[i]:5.1f}  {meas[i]:5.1f}  {resid[i]:+5.1f}")
    print(f"RMSE constant {rmse_const:.2f} dB | mock {rmse_mock:.2f} dB | Sionna {rmse:.2f} dB (bias {bias:.1f} dB)")

    out = Path(f"data/derived/sionna_{args.material}_d{args.max_depth}.json")
    out.write_text(json.dumps({
        "material": args.material, "thickness_m": args.thickness, "max_depth": args.max_depth,
        "samples_per_src": args.samples, "solve_seconds": round(elapsed, 1), "bias_db": round(float(bias), 2),
        "rmse_db": round(float(rmse), 2), "rmse_mock_db": round(float(rmse_mock), 2),
        "rmse_constant_db": round(float(rmse_const), 2),
        "points": {k: {"path_gain_db": round(float(pg_db[i]), 2), "pred_dbm": round(float(pred[i]), 2),
                       "meas_dbm": round(float(meas[i]), 2), "paths": int(n_paths[i])} for i, k in enumerate(labels)},
    }, indent=2))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
