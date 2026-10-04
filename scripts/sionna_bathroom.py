"""Sionna RT radio map for the bathroom session (run with .venv-sionna).

    .venv-sionna/Scripts/python.exe scripts/sionna_bathroom.py --variant brick
    .venv-sionna/Scripts/python.exe scripts/sionna_bathroom.py --variant plain

variant "plain": every surface plasterboard 0.10 m, no door (the scan as is).
variant "brick": bathroom walls brick (0.09 m per scanned side, ~0.18 m wall),
                 closed wooden door 0.04 m, rest plasterboard 0.10 m.
Each receiver sub-position gets the mean linear path gain of the 3x3 cells
(0.3 m x 0.3 m) around it; results go to data/derived/sionna_bathroom_<variant>.json.
"""

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("DRJIT_LIBLLVM_PATH", str(Path("tools/llvm-20.1.8/LLVM-C.dll").resolve()))

import numpy as np  # noqa: E402
from sionna.rt import PlanarArray, RadioMapSolver, Transmitter, load_scene  # noqa: E402

SCENE_DIR = Path("data/sionna/bath")
FREQ_HZ = 2.437e9
CELL = 0.10
SHAPE = """    <bsdf type="itu-radio-material" id="mat-{name}">
        <string name="type" value="{material}"/>
        <float name="thickness" value="{thickness}"/>
    </bsdf>
    <shape type="ply" id="obj-{name}">
        <string name="filename" value="{name}.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat-{name}" name="bsdf"/>
    </shape>
"""
VARIANTS = {
    "plain": [("loft", "plasterboard", 0.10), ("walls", "plasterboard", 0.10), ("patch", "plasterboard", 0.10)],
    "brick": [("loft", "plasterboard", 0.10), ("walls", "brick", 0.09), ("patch", "brick", 0.18), ("door", "wood", 0.04)],
    "metaldoor": [("loft", "plasterboard", 0.10), ("walls", "brick", 0.09), ("patch", "brick", 0.18), ("door", "metal", 0.01)],
    "metalwalls": [("loft", "plasterboard", 0.10), ("walls", "metal", 0.01), ("patch", "metal", 0.01), ("door", "metal", 0.01)],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=VARIANTS, default="brick")
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--samples", type=int, default=32_000_000)
    args = parser.parse_args()

    xml = SCENE_DIR / f"scene_{args.variant}.xml"
    body = "".join(SHAPE.format(name=n, material=m, thickness=t) for n, m, t in VARIANTS[args.variant])
    xml.write_text(f'<scene version="2.1.0">\n{body}</scene>\n')
    geo = json.loads((SCENE_DIR / "geometry.json").read_text())
    names = list(geo["rx"])
    rx = np.array([geo["rx"][k] for k in names])

    scene = load_scene(str(xml))
    scene.frequency = FREQ_HZ
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.add(Transmitter("router", position=geo["tx"]))

    lo = np.minimum(rx[:, :2].min(axis=0), geo["tx"][:2]) - 0.6
    hi = np.maximum(rx[:, :2].max(axis=0), geo["tx"][:2]) + 0.6
    t0 = time.time()
    rm = RadioMapSolver()(scene, center=[float(v) for v in (lo + hi) / 2] + [1.0], orientation=[0, 0, 0],
                          size=[float(v) for v in hi - lo], cell_size=[CELL, CELL], samples_per_tx=args.samples,
                          max_depth=args.max_depth, los=True, specular_reflection=True,
                          diffuse_reflection=False, refraction=True)
    pg = np.array(rm.path_gain)[0]
    centres = np.array(rm.cell_centers)
    x0, y0 = centres[0, 0, 0] - CELL / 2, centres[0, 0, 1] - CELL / 2
    out = {}
    for k, p in zip(names, rx):
        i, j = int((p[1] - y0) / CELL), int((p[0] - x0) / CELL)
        out[k] = float(10 * np.log10(np.mean(pg[i - 1 : i + 2, j - 1 : j + 2])))
    elapsed = time.time() - t0
    path = Path(f"data/derived/sionna_bathroom_{args.variant}.json")
    path.write_text(json.dumps({"variant": args.variant, "max_depth": args.max_depth, "samples": args.samples,
                                "cell_m": CELL, "solve_seconds": round(elapsed, 1), "path_gain_db": out}, indent=2))
    print(f"{args.variant}: solved in {elapsed:.1f} s, saved {path}")


if __name__ == "__main__":
    main()
