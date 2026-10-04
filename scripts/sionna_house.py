"""Sionna RT radio map on the lower floor of the house (run with .venv-sionna).

    .venv-sionna/Scripts/python.exe scripts/sionna_house.py --variant physics
    .venv-sionna/Scripts/python.exe scripts/sionna_house.py --variant plain

physics: concrete slab (2 scanned surfaces x 0.10 m), concrete lower floor,
         brick lower-floor walls (2 sides x 0.06 m), rest plasterboard 0.10 m
plain:   everything plasterboard 0.10 m
The measurement plane is horizontal at aligned height -1.25 m (about 1.4 m above
the lower floor, where the phone was held). Saves path gain and cell centres
(aligned frame x, z) to data/derived/sionna_house_<variant>.npz.
"""

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("DRJIT_LIBLLVM_PATH", str(Path("tools/llvm-20.1.8/LLVM-C.dll").resolve()))

import numpy as np  # noqa: E402
from sionna.rt import PlanarArray, RadioMapSolver, Transmitter, load_scene  # noqa: E402

SCENE_DIR = Path("data/sionna/house")
FREQ_HZ = 2.437e9
CELL = 0.25
PLANE_HEIGHT = -1.25
X_RANGE = (2.0, 7.5)   # aligned frame
Z_RANGE = (-0.3, 9.5)
SHAPE = """    <bsdf type="itu-radio-material" id="mat-{name}-m">
        <string name="type" value="{material}"/>
        <float name="thickness" value="{thickness}"/>
        <float name="scattering_coefficient" value="{scattering}"/>
    </bsdf>
    <shape type="ply" id="obj-{name}">
        <string name="filename" value="{name}.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat-{name}-m" name="bsdf"/>
    </shape>
"""
VARIANTS = {
    "physics": [("slab", "concrete", 0.10), ("lowerfloor", "concrete", 0.20),
                ("walls", "brick", 0.06), ("other", "plasterboard", 0.10)],
    "slabonly": [("slab", "concrete", 0.10), ("lowerfloor", "concrete", 0.20), ("other", "plasterboard", 0.10)],
    "plain": [("slab", "plasterboard", 0.10), ("lowerfloor", "plasterboard", 0.10),
              ("walls", "plasterboard", 0.10), ("other", "plasterboard", 0.10)],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=VARIANTS, default="physics")
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--samples", type=int, default=32_000_000)
    parser.add_argument("--tx-pattern", default="iso", help="router antenna: iso, dipole, hw_dipole")
    parser.add_argument("--tx", type=float, nargs=3, default=None, metavar=("X", "Y", "Z"),
                        help="transmitter in the aligned frame (x, height, z); default: TP-Link from geometry.json")
    parser.add_argument("--tag", default="", help="suffix for the output file")
    parser.add_argument("--plane-height", type=float, default=PLANE_HEIGHT, help="aligned height of the radio map plane")
    parser.add_argument("--scattering", type=float, default=0.0,
                        help="scattering coefficient S for every surface; > 0 also enables diffuse reflection")
    args = parser.parse_args()

    body = "".join(SHAPE.format(name=n, material=m, thickness=t, scattering=args.scattering)
                   for n, m, t in VARIANTS[args.variant])
    tag = args.variant + (f"_s{args.scattering:g}" if args.scattering > 0 else "") + (f"_d{args.max_depth}" if args.max_depth != 8 else "") + (f"_{args.tx_pattern}" if args.tx_pattern != "iso" else "") + args.tag
    xml = SCENE_DIR / f"scene_{tag}.xml"
    xml.write_text(f'<scene version="2.1.0">\n{body}</scene>\n')
    geo = json.loads((SCENE_DIR / "geometry.json").read_text())

    scene = load_scene(str(xml))
    scene.frequency = FREQ_HZ
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern=args.tx_pattern, polarization="V")
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    tx = [args.tx[0], -args.tx[2], args.tx[1]] if args.tx else geo["tx"]
    scene.add(Transmitter("router", position=tx))

    # Sionna frame: X = x, Y = -z, Z = height
    cx = (X_RANGE[0] + X_RANGE[1]) / 2
    cy = -(Z_RANGE[0] + Z_RANGE[1]) / 2
    size = [X_RANGE[1] - X_RANGE[0], Z_RANGE[1] - Z_RANGE[0]]
    t0 = time.time()
    rm = RadioMapSolver()(scene, center=[cx, cy, args.plane_height], orientation=[0, 0, 0], size=size,
                          cell_size=[CELL, CELL], samples_per_tx=args.samples, max_depth=args.max_depth,
                          los=True, specular_reflection=True, diffuse_reflection=args.scattering > 0, refraction=True)
    pg = np.array(rm.path_gain)[0]
    centres = np.array(rm.cell_centers)
    elapsed = time.time() - t0
    out = Path(f"data/derived/sionna_house_{tag}.npz")
    np.savez(out, path_gain=pg, x=centres[..., 0], z=-centres[..., 1], cell=CELL)
    print(f"{tag}: {pg.shape[1]}x{pg.shape[0]} cells solved in {elapsed:.1f} s, "
          f"{np.mean(pg > 0) * 100:.0f}% of cells reached, saved {out}")


if __name__ == "__main__":
    main()
