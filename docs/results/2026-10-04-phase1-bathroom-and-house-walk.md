# Phase 1 Results — Through-Wall, Walking Survey and Two Floors

**Dates**: 2026-10-03 (bathroom) and 2026-10-04 (walking surveys)
**Authors**: Juan Wang (Kisum GmbH, measurements) and Claude (analysis)
**Builds on**: `2026-10-02-phase0-loft-survey.md`

## Summary

Phase 0 ended in a tie between Sionna RT and a two-line formula in an open
room, and we suspected the room was the problem: no walls, so nothing for a
physics model to get right. This round went looking for walls and floors.

- **A brick-and-tile bathroom wall cost about 3 dB.** A calibrated simple model
  (free space plus one fitted loss per wall) matched the bathroom points at
  2.0 dB RMS; Sionna at 2.4–2.5 dB. With a measurement uncertainty of about
  2.3 dB per point, nothing separates them.
- **We found a much faster way to measure.** An ESP32-C6 taped to an
  iPhone running the open-source Stray Scanner records signal and 3D pose
  together. Ten minutes of walking gave a two-floor 3D model and 29,000
  positioned RSSI samples, against 35 minutes for 58 tripod readings.
- **Across two floors, a two-number model fits within about 2 dB.** Free-space
  distance plus one loss for the concrete slab, both fitted from data,
  describes 116 half-metre cells at 2.4 dB RMS (upper floor) and 1.8 dB (lower
  floor). The fitted slab loss, 13.5 dB, agrees with the ITU-R P.2040
  concrete parameters Sionna uses (13.2 dB for 20 cm). Brick walls on the
  lower floor show no measurable extra loss.
- **Through the slab, Sionna on our scanned mesh missed by more than a
  constant would**: 5.7–6.7 dB RMS against 3.3 dB for a constant on the lower
  floor, with the router upstairs, in every variant we tried. It predicts too
  much signal near and below the router and too little far away. We suspect
  the noisy phone-scan mesh around the slab and stairwell; we have not
  confirmed it.
- **With a second router on the multi-room lower floor, Sionna was the most
  accurate model on that floor** (away from the router's own cabinet,
  3.4–3.6 dB against 4.0–4.8 dB for the simple models, section 4), and a hybrid of Sionna within the floor plus
  a calibrated slab step was best overall (section 6).

So physics helped where a floor has several rooms and walls, and the
calibrated simple model was closer in the open attic and through the slab.
Because all Sionna runs used a rough phone-scan mesh, we read this as a
statement about our pipeline, not about Sionna.

## 1. Bathroom session (2026-10-03)

**Setup.** The enclosed bathroom in the loft corner was added to the scan with
3D Scanner App's Extend Scan. The extension came back offset by about 54 cm;
trimmed ICP (`scripts/align_scans.py`, 600 iterations) aligned it to the
reference scan at 1.1 cm median distance, confirmed independently on the
stairwell surface (0.8 cm). All later scans use `scripts/scan_frame.py`.
The wall between loft and bathroom is about 20 cm thick (brick plus ceramic
tiles, per the operator; scan surfaces at x 5.35 and 5.55 m), the C-side wall
about 18 cm.

**Protocol.** Five points inside the bathroom (B1–B5) and three outside at
similar distance (7, 9, 11), door closed, firmware settle time raised to 12 s
so the operator could leave and close the door. Each point recorded at three
sub-positions (centre, 20 cm towards A, 20 cm towards B), averaged as linear
power. 27 windows; the operator was unsure whether point 9 had 2 or 3 presses
and point 7 had 3 or 4; only 3 + 4 matches the 27 recorded windows.

**Results.** One global bias per model, 9 points:

| Model | RMS error | Fitted numbers |
|---|---|---|
| Constant | 5.40 dB | 1 |
| Mock, 8 dB per wall crossing | 3.15 dB | 1 |
| Mock with fitted wall loss (3.1 dB) | 1.99 dB | 2 |
| Sionna, all plasterboard | 2.36 dB | 1 |
| Sionna, brick walls + wooden door | 2.46 dB | 1 |

**What we learned.**

- *Sub-positions matter more than expected.* Moving the tripod 20 cm changed
  RSSI by up to 14 dB (point 11). Pooled spread 3.9 dB, so a three-position
  mean is still uncertain by roughly 2.3 dB. Phase 0's single-spot readings
  carried this much "frozen" fading.
- *The wall is weak at 2.4 GHz.* B3 inside and point 7 outside are both 5.7 m
  from the router and differ by 0.8 dB. The fitted loss is 3.1 dB per
  crossing.
- *That is what ITU-R P.2040 predicts.* With the parameters in Sionna's
  `itu.py`, bulk absorption at 2.437 GHz is 23 dB/m for brick and 19 dB/m
  for plasterboard, so 18–20 cm of either costs about 4 dB. This is why
  switching the bathroom walls between brick and plasterboard barely changed
  Sionna's prediction. Making the walls metal lowered the bathroom by
  2–14 dB, so most energy does go through the walls in the simulation; some
  still arrives another way, which we did not trace.
- *A bug of ours, found on the way.* The first brick assignment only covered
  the walls up to 2.6 m, leaving the top 0.5 m as plasterboard, and the
  C-side wall was not scanned below 0.4 m. Both were fixed (walls to 3.25 m,
  a hand-added brick strip at the bottom); the results above are after the
  fix and changed by less than 0.1 dB.

## 2. Walking survey method (2026-10-04)

**Hardware and apps.** ESP32-C6 taped to the back of the iPhone 15 Pro with
the antenna end sticking out above the phone, power bank in a pocket, same
firmware as Phase 0 (UDP to the survey PC). The phone runs
[Stray Scanner](https://github.com/strayrobots/scanner) (free, MIT), which
records RGB video, 256×192 LiDAR depth with confidence, and a per-frame
camera pose (`odometry.csv`) at 60 Hz. iOS does not expose Wi-Fi RSSI in dBm
to apps, so the phone cannot measure the signal itself.

**Time sync.** BOOT on the ESP32 and record/stop in Stray Scanner are pressed
together at start and end; each BOOT press shows up as a state change in the
probe stream with the PC's timestamp. A 5 s hold of the probe against the
router at start (and end) gives an independent check. In both walks the two
clocks agreed to 0.1–0.2 s over 5–10 minutes, and the router-touch peak fell
within about one second of the phone's closest approach to the router.

**Pose convention.** Stray's format document does not state it. Its own
viewer, [StrayVisualizer](https://github.com/kekeblom/StrayVisualizer), builds
`T_WC` from the quaternion and position without axis flips and hands
`inv(T_WC)` to Open3D, i.e. camera-to-world in OpenCV axes. Our data agrees:
the OpenCV reading gives a cloud twice as sharp (26.6 % vs 54.1 % of points
in distinct 3 cm voxels). Depth intrinsics are the RGB ones scaled by
256/1920.

**Registration.** The Stray point cloud is gravity-aligned, so only yaw and
translation are searched (`scripts/stray_align.py`: 10° coarse grid on 5,000
points, 2° refinement, then trimmed ICP with neighbour searches capped at
0.5–1 m). It takes 1.5 minutes and lands at 2.6 cm (loft walk) and 2.9 cm
(house walk, aligned on upper-floor frames only) median distance to the
reference scan. Two earlier versions of this script looked hung; the real
causes were uncapped k-d tree searches for badly placed candidates, an old
background loop still running, and our own output piping hiding progress.

**Validation against the tripod points (loft walk, 289 s, 78 m).** RSSI
falls with distance as expected (correlation with log distance −0.80). At 17
tripod points with enough walking data within 40 cm, the walk reads +3.9 dB
higher with power averaging and +2.5 dB with dB averaging; point-to-point
scatter is about 4 dB. Phone height is not the cause: restricted to
0.85–1.15 m (tripod height) the offset is still +6 dB. Our reading:

- the scatter is mostly the tripod's single-spot fading (walking samples
  inside a 40 cm disc themselves spread by 3.8 dB);
- about 1.4 dB of the offset comes from comparing a power average with a dB
  average, which differ by about 2.5 dB under Rayleigh-like fading;
- the remaining ~2.5 dB is unexplained. Our leading guess is board
  orientation (flat on the tripod, upright on the phone). A uniform offset is
  absorbed by the global bias in every model comparison.

## 3. Two-floor house walk (2026-10-04)

The test house has a typical German layout: an open attic floor under a pitched
roof, a concrete slab, and a lower floor of several brick-walled rooms joined
by a hallway and an open stairwell.

**Recording.** 570 s, 184 m, 26,028 frames: from the router down the stairs,
every room on the lower floor, back up, the rest of the loft including the
bathroom, back to the router. All doors open.

**Geometry.** Open3D's `ScalableTSDFVolume` (0.20.0 on Windows, Python 3.11)
returned no surface even for a synthetic flat wall, so we used
`UniformTSDFVolume` (11 m cube, 3 cm voxels): 1.25 M triangles
(`scripts/stray_tsdf.py`). Dense horizontal levels in the aligned frame:
loft floor +0.02 m, lower-floor ceiling −0.28 m, lower floor −2.68 m. So the
lower rooms are 2.40 m high and the slab is about 30 cm (concrete, per the
operator). Lower-floor walls are brick.

**Measurement.** 12,941 upper-floor and 15,630 lower-floor samples. Median
RSSI −49 dBm upstairs, −63 dBm downstairs. Binned into 0.5 m cells with at
least 50 samples (one second): 53 upper and 63 lower cells.

**Simple model across both floors.** Free-space loss + global bias + one
step for being on the lower floor:

| | Value |
|---|---|
| Fitted floor step | 13.5 dB |
| RMS error, upper floor (53 cells) | 2.36 dB |
| RMS error, lower floor (63 cells) | 1.84 dB |

ITU-R P.2040 concrete as implemented in Sionna (εr 5.24, σ 0.093 S/m at
2.437 GHz) absorbs 66 dB/m, i.e. 13.2 dB for 20 cm, before interface
reflections. The measured step is consistent with that.

On the lower floor, residuals of this model do not fall with the number of
brick walls on the straight path; if anything they rise (correlation +0.40;
cells behind 4 walls read 2.8 dB stronger than the model). We counted walls
from all vertical mesh surfaces, so tall furniture counts as a wall, but the
direction of the effect is not what a wall loss would produce.

**Lower-floor model comparison (63 cells, one global bias each):**

| Model | RMS error |
|---|---|
| Constant | 3.31 dB |
| Mock, 8 dB per slab and per wall | 8.19 dB |
| Mock, fitted slab and wall loss¹ | 1.60 dB |
| Sionna, concrete slab + brick walls | 6.72 dB |
| Sionna, all plasterboard | 6.13 dB |
| Sionna, walls removed | 5.71 dB |
| Sionna, scattering coefficient 0.3 + diffuse | 6.67 dB |
| Sionna, depth 16, 64 M rays | 6.47 dB |
| Sionna, half-wave dipole at the router | 6.50 dB |

¹ On the lower floor alone the slab loss is not identifiable (90 % of cells
cross it, so it trades off against the bias); use the two-floor fit above for
the slab value.

Radio maps run at aligned height −1.25 m with 0.25 m cells
(`scripts/sionna_house.py`, 15–45 s each on the CPU). Sionna's map is
up to about 12 dB too strong in the cells closest to the router's footprint
and up to about 12 dB too weak at the far end of the lower floor (A side); measured values are
much flatter. Changing materials, removing walls, adding diffuse scattering,
doubling the bounce depth and using a dipole pattern each moved the error by
less than 1 dB. Loading the scene back confirmed that the scattering
coefficient of 0.3 reached every material, so that test was valid.

We have not found the cause. Candidates we have not yet tested: the TSDF
mesh contains many near-duplicate and noisy surfaces, so a ray crosses more
slabs than the real house has; furniture is modelled as plasterboard shells;
the router's real antennas and their near-field (desk, monitors) differ
from any standard pattern; and the radio-map plane is at a single height
while the phone moved between 1.0 and 1.8 m above the floor.

## 4. Addendum: a second router on the lower floor (2026-10-04, evening)

To test whether predictions carry over to a router position we never
calibrated on, we walked the lower floor (3 minutes, battery-limited, upper
floor not covered, doors open) connected to a Xiaomi R4A, which
sits on the lower floor in a corner room, 30 cm above the floor in an open
cabinet under a printer. The Xiaomi never produced CSI for the probe (frames
arrive non-HT) and ignores pings to itself, so the firmware pinged the
FRITZ!Box behind it and recorded per-frame RSSI in promiscuous mode
(beacons and data, medians −56/−57 dBm). Sync from the start BOOT press,
checked against the router touch (phone 0.18 m from the router at +7.1 s,
RSSI above −25 dBm in seconds 0–10). The Stray cloud was aligned to the house
TSDF mesh at 3.9 cm. Median 4 brick walls on the straight path.

| Lower-floor cells | all (49) | ≥ 1.5 m (45) | ≥ 2.5 m (40) |
|---|---|---|---|
| Constant | 10.07 | 7.64 | 5.94 |
| Model carried over from the TP-Link walk (distance only) | 5.43 | 4.75 | 4.05 |
| Free space + wall loss fitted on this walk (1.6 dB/wall) | 4.61 | 4.26 | 3.95 |
| Sionna, concrete + brick | 4.81 | 3.57 | 3.56 |
| Sionna, all plasterboard | 4.55 | 3.41 | 3.47 |

RMS errors in dB, one global bias per model. Away from the router's own
cabinet, Sionna beats both simple models by 0.5–1.3 dB, including the one
fitted on the same data. This is the first result in favour of the physics
model. Materials barely matter (plasterboard ≈ concrete/brick), so the gain
comes from the geometry: walls, doorways and reflections in a multi-room
floor. With the TP-Link on the other floor, Sionna on our mesh was off by
~6 dB, which now points at how the concrete slab and the stairwell are
modelled in our scene rather than at the walls. One short walk and 40–49 cells; this needs repeating, with the
upper floor included.

## 5. Addendum: the Xiaomi seen from the upper floor (2026-10-04, night)

A second Xiaomi walk covered the upper floor (217 s; probe and Stray clocks
agree to 0.2 s). A full rigid ICP against the loft scan tilted the cloud by
2.15°, so we restricted the fit to yaw and translation (gravity is shared):
3.9 cm median, no tilt. Together with section 4 this gives 49 lower and 40
upper cells for the same router, one global bias per model:

| Model | all | lower | upper |
|---|---|---|---|
| Carried over from the TP-Link walk: free space + 13.5 dB floor step | 4.64 | 5.68 | 2.90 |
| Free space + floor step refitted here (9.8 dB) | 4.27 | 5.43 | 2.09 |
| Sionna, concrete slab + brick | 4.93 | 4.95 | 4.90 |
| Sionna, all plasterboard | 5.37 | 5.58 | 5.10 |

Measured, the upper floor is 13.1 dB weaker on average than the lower floor;
Sionna predicts 10.4 dB with concrete and 5.9 dB with plasterboard, so the
slab material does matter. The floor step learned with the TP-Link (one
router, signal going down) carries over to the Xiaomi (another router, signal
going up) and gives the best result upstairs. Sionna's spatial pattern through
the slab is again worse than the simple model, while within the lower floor it
is better (section 4).

Our current reading: house properties learned with one router do transfer to
another router position, which is what a "where should the router go" feature
needs. A hybrid looks promising: Sionna for the geometry within a floor, and
a slab loss calibrated from a walk. Both readings rest on one house and short
walks.

## 6. Hybrid model (computed on existing data)

Own floor: Sionna (concrete + brick). Other floor: free space minus a slab
step. The step is learned on the TP-Link walk (13.6 dB for the simple model,
16.7 dB for the hybrid, which also absorbs Sionna's level offset) and carried
over unchanged to the Xiaomi walks; each router gets its own bias
(`scripts/hybrid_compare.py`; cells need at least 100 frames).

| Router | Model | all | own floor | other floor |
|---|---|---|---|---|
| TP-Link (fitted) | simple | 1.91 | 2.02 | 1.82 |
| | Sionna everywhere | 6.14 | 4.43 | 7.27 |
| | hybrid | 2.49 | 3.10 | 1.82 |
| Xiaomi (carried over) | simple | 4.67 | 5.69 | 2.96 |
| | Sionna everywhere | 4.93 | 4.95 | 4.90 |
| | hybrid | 4.07 | 4.96 | 2.59 |

For the Xiaomi, whose own floor is the multi-room brick floor, the hybrid is
best. For the TP-Link, whose own floor is the open loft, the simple model is
closer to the measurements than Sionna on our mesh, as in Phase 0. So far physics helps where a floor
has several rooms and walls, not in an open room, and not through the slab.

## What this means for the project

Two readings of the evidence, and we cannot yet choose between them:

1. **Physics has little to add at 2.4 GHz in this kind of house.** Brick walls
   cost a few dB, the concrete slab is the one big step, and a model with
   distance plus a per-floor loss captures what matters. If that holds for
   other homes, a ray tracer may not be needed for basic coverage prediction.
2. **Physics needs clean geometry.** Sionna's material parameters are right
   (slab 13.5 dB measured vs 13.2 dB from P.2040, bathroom wall 3 dB vs ~4 dB),
   but a phone-scan TSDF mesh may be the wrong input for it. A version of the
   house with walls, floors and roof as clean planes would separate the two
   explanations.

Meanwhile, something else worked well: **scan + ten-minute walk + calibrated
simple model** reached about 2 dB on two floors, needs no GPU, and tolerates
messy geometry, as long as the floors and the stairwell are identified.
Whether that is a product, and whether it holds beyond this one house, are
open questions.

## Proposals

- **Clean-geometry experiment** (decides between the two readings): build a
  simplified model of both floors with planar walls, slab and roof extracted
  from the scan, assign materials, and rerun Sionna on the same 116 cells.
- **Test a second house** with the walking method before drawing product
  conclusions; ten minutes per floor makes this cheap.
- **Keep the walking protocol**: same phone height and probe orientation,
  router touch at start and end, note every door. Add a second walk in the
  opposite direction to estimate body shadowing.
- **Write down the alternative product** (scan + walk + calibrated model) as a
  hypothesis to test against OEM interest, not as a decision.

## Reproducing

Environments: `.venv` (Python 3.13), `.venv-sionna` (sionna-rt 2.2.0, LLVM 20
at `tools/llvm-20.1.8/`), `.venv-o3d` (Python 3.11 from ESP-IDF, open3d 0.20).

```
# bathroom
.venv/Scripts/python.exe scripts/align_scans.py data/scans/loft_with_bathroom_2026-10-03.usdz
.venv/Scripts/python.exe scripts/export_bathroom_scene.py
.venv-sionna/Scripts/python.exe scripts/sionna_bathroom.py --variant brick   # also plain, metaldoor, metalwalls
.venv/Scripts/python.exe scripts/analyze_bathroom.py
# walks
.venv/Scripts/python.exe scripts/stray_cloud.py data/stray/walk_house_2026-10-04 --min-phone-height -0.3 --tag _upper
.venv/Scripts/python.exe scripts/stray_cloud.py data/stray/walk_house_2026-10-04
.venv/Scripts/python.exe scripts/stray_align.py data/stray/walk_house_2026-10-04 opencv _upper
.venv/Scripts/python.exe scripts/walk_analysis.py data/stray/walk_house_2026-10-04 data/raw/walk_house_2026-10-04.jsonl
.venv-o3d/Scripts/python.exe scripts/stray_tsdf.py data/stray/walk_house_2026-10-04
.venv/Scripts/python.exe scripts/export_house_scene.py
.venv-sionna/Scripts/python.exe scripts/sionna_house.py --variant physics   # see --help for variants
.venv/Scripts/python.exe scripts/house_compare.py
```

Raw data: `data/raw/bathroom_2026-10-03.jsonl`, `data/raw/walk_loft_2026-10-04.jsonl`,
`data/raw/walk_house_2026-10-04.jsonl`, `data/stray/` (Stray recordings).

## Limitations

One house, one router position, one band (2.4 GHz, channel 6, 20 MHz), two
days. The walking data carries the operator's body next to the probe and
changing probe orientation; we have not measured that effect directly.
Wall counts come from mesh surfaces and include furniture. The bathroom
press-to-point mapping for points 7 and 9 rests on the window count. The
remaining ~2.5 dB offset between walking and tripod readings is unexplained.
