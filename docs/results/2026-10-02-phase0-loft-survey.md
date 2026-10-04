# Phase 0 Results — Walk Survey in an Attic Loft

**Date of survey**: 2026-10-02 (3D scan: 2026-08-07)
**Authors**: Juan Wang (Kisum GmbH, measurements) and Claude (analysis)
**Status**: Phase 0 (first validation round) complete.
Follow-up: `2026-10-04-phase1-bathroom-and-house-walk.md`

## Summary

We ran the whole chain once, end to end, on consumer hardware: iPhone 15 Pro
LiDAR scan → 3D model on a Windows PC → simple propagation model and Sionna RT
→ walk survey with a ~€40 ESP32-C6 probe → comparison. Everything worked, and
Sionna RT runs on the PC's CPU in seconds, so no cloud GPU was needed.

The modelling result is less flattering. In this single open-plan loft, every
model we tried lands at about 3 dB RMS error after a single global bias fit,
including Sionna RT. The measurement itself is good enough to see a
difference of roughly 1 dB, so this is a real tie, not a noisy one. Our
reading is that a single open room is close to the worst case for showing the
value of a physics model: distance explains most of what there is, and
there are no walls to get wrong.

The most useful finding was not planned. The objects the phone's LiDAR misses
are exactly the ones that matter most for 2.4 GHz: black monitors (metal back
plates), a mirror (metal coating) and window glass. The scan does not only
miss them; the mirror produced a phantom room behind the wall. Any product
built on phone scans needs a step that finds these objects some other way.

## Setup

**Site.** The attic floor of a typical German two-storey house: one open room under a pitched roof (Dachgeschoss), about 6.0 m × 9.9 m
footprint, ridge about 3.0 m above the floor, roof pitch about 32° on the desk
side, a dormer (Gaube), several Velux skylights, a stairwell opening, and a lot
of furniture. Only about 6 m² of floor was free enough for a tripod. An
enclosed bathroom and toilet sit in the corner between sides A and B (about
x 5.5–7.2 m, z 0–3.8 m in the aligned frame); it was neither scanned nor
surveyed, so all 19 points are in the open part of the floor.

**3D model.** 3D Scanner App (Laan Labs, free tier, LiDAR mode, Medium
processing), exported as USDZ: 271,738 vertices, 448,559 faces. Loaded with
`usd-core`, rotated by 20.5° so walls align with the axes, floor at y = 0
(`scripts/load_scan.py`, `scripts/topdown_map.py`).

**Access point.** TP-Link TL-WR845N (2.4 GHz, 802.11n, 2×2) on a desk, placed
in the model from three tape measurements (`scripts/locate_ap.py`; AP at
x 2.815, z 7.302 m in the aligned frame). For the duration of the survey the
router was locked to channel 6 and 20 MHz bandwidth (it was on auto, and auto
had picked channel 6).

**Probe.** ESP32-C6-DevKitC-1 (N8) with firmware in `firmware/csi_probe`, based
on Espressif's `esp-csi/examples/get-started/csi_recv_router`. It pings the
gateway at 50 Hz and captures CSI (64 subcarriers, I/Q int8) and RSSI from the
replies, sending each record over UDP to the survey PC, which is wired to the
router. Pressing BOOT gives 3 s to step away, then a 15 s recording window,
shown on the RGB LED. Powered by a power bank on a plastic camera tripod at
1.0 m, antenna end always pointing to the same side of the room.
`scripts/csi_receiver.py` stores everything as JSONL.

**Survey.** 18 points plus a reference point R about 1.2 m from the router,
chosen by `scripts/plan_points.py` on free floor (farthest-point sampling,
closed walking tour). Three rounds, R → 1…18 → R each, 58 recording windows,
about 750 records per window, no dropped records and no reboots. Operator notes:
points 7 and 8 were walked in swapped order in every round, point 16 was
measured at 1.15 m and point 17 at 1.10 m; both are handled in
`scripts/analyze_survey.py`.

## Measurement quality

| Quantity | Value |
|---|---|
| RSSI spread inside one 15 s window (median over 58 windows) | 0.44 dB SD |
| Round-to-round spread at the same point (pooled) | 1.89 dB SD |
| Implied uncertainty of a 3-round mean | about 1.1 dB |
| Reference point R over 4 visits | −38, −38, −38, −40 dBm |
| Mean round offset (all points) | +0.0, +0.9, −0.9 dB |

Standing next to the probe while it records is not negligible. In a desk test
with the operator moving around the board, RSSI swung between −41 and −55 dBm
within 15 s. With the operator stepped away, the swing was below 1 dB.

## Model comparison

Each model's prediction gets one global bias (absorbing TX power and antenna
gains) fitted to the measured 3-round means. We report the RMS of the residuals.

| Model | All 19 points | Without point 6 |
|---|---|---|
| Constant (every point = mean) | 3.65 dB | 3.71 dB |
| Mock: free-space loss + 8 dB per structural crossing | 3.21 dB | 2.98 dB |
| Log-distance fit, 2 parameters | 3.00 dB (n = 1.28) | 2.86 dB (n = 1.48) |
| Sionna RT radio map, 8 variants¹ | 3.51–3.85 dB | 2.82–2.88 dB |

¹ Whole mesh as one ITU material (plasterboard, concrete, wood, brick; 0.1 m),
max depth 4 or 8, 16 M rays, 0.25 m cells at 1.0 m height, prediction = mean
of the 3×3 cells around each point (`scripts/sionna_radiomap.py`). Material
and depth barely matter.

Beyond about 2.4 m from the router, the measured RSSI is almost flat: 15
points between −55 and −47 dBm (2.0 dB SD) for distances from 2.5 m to 5.8 m.
The fitted path-loss exponent of 1.3–1.5, below the free-space value of 2,
fits the picture of reflections from roof, walls and furniture keeping the
far end of the room filled.

The "8 dB per crossing" of the mock is the placeholder from the stitching plan,
not a measured value. It hardly matters here: in an open room 99.8 % of the
grid has no crossing at all.

**Point 6 was excluded after the fact**, which is why both columns are shown.
It was the least repeatable point (−48, −44, −51 dBm over the rounds) and was
6–9 dB stronger than every model. A metal mirror 1.5 m away was the obvious
suspect, but adding it to the Sionna scene changed nothing, and the geometry
shows why: a single reflection from that wall to point 6 would have to hit
the wall near z ≈ 6.1 m, nowhere near the mirror. In round 2, points 5, 6 and
7 were all about 4 dB stronger than in rounds 1 and 3, while R and the router's
rate/format stayed identical and, per the operator, nothing in the room moved.
We have no explanation yet. Small differences in tripod position or board
orientation are the leading candidates; a 9-window test at point 6 (5
positions, 4 orientations) would settle it.

## What the scan missed

The mock and Sionna residuals correlate at 0.90: both models get the same
points wrong, in the same direction. That points to something neither model
contains, and in two cases we found it.

**Monitors at point 18.** Point 18 is 1.8 m from the router and 6–8 dB weaker
than predicted. Along the router–18 line the mesh is empty between 0.8 m and
1.3 m height, yet the room has two monitors there (1.0 m wide, bottom edge
1.0 m, top 1.3 m) and a 2 m × 1.4 m acoustic panel; all of them are black. The
direct path rises from 0.86 m (antenna) to 1.0 m (probe), so the monitors' lower
edge grazes it. The single knife-edge approximation of
[ITU-R P.526](https://www.itu.int/rec/R-REC-P.526) gives 2.8–5.0 dB of loss
depending on which part of the edge is taken, the same order as the measured
excess. The acoustic panel stands between the router and almost every point
except 16 and 17; after the bias fit those two show +1.0/+0.6 dB (mock) and
−0.6/−0.5 dB (Sionna), so the panel costs at most a dB or two.

**Mirror.** The D wall has a 1.4 m gap in the mesh exactly where the operator
reports a triangular mirror (1.4 m × 1.4 m, 1.0–2.4 m high), and there is a
cloud of points behind the wall: LiDAR saw the reflected room. It did not
explain point 6 (see above), but it shows the failure mode clearly.

Both objects are now in `data/sionna/extras.json` as hand-added metal
triangles, with their sources noted.

## What we learned about the tools

- **Sionna RT works on a 2016 office PC.** i7-6700T, 4 cores, no NVIDIA GPU,
  Windows 11, `sionna-rt` 2.2.0 on Python 3.13, LLVM backend. A radio map of
  the loft takes 2–10 s. NVIDIA's own guidance is that CPU is much slower than
  GPU ([discussion #986](https://github.com/NVlabs/sionna/discussions/986):
  0.04 s vs 0.6 s for a city scene), which is fine for one-off runs but will
  matter once we fit materials iteratively.
- **The LLVM version matters on Windows.** Dr.Jit asks for LLVM ≥ 18
  ([docs](https://drjit.readthedocs.io/en/latest/what.html)). LLVM 18.1.8 loaded
  but failed on our scene with `JIT session error: Failed to materialize
  symbols: __ymm@…`; LLVM 20.1.8 works. Only `LLVM-C.dll` is needed; we
  extracted it from the official installer into `tools/llvm-20.1.8/`. `winget`
  stalled while downloading and was not needed.
- **The exact-path solver does not work on a raw phone-scan mesh.** Sionna's
  `PathSolver` found 1–6 paths per receiver (9.9 dB RMS error, with the
  reference point predicted among the weakest). Specular paths need the
  reflection point to land on a triangle with exactly the right normal, and a
  scanned wall is thousands of slightly tilted triangles. The radio map solver,
  which just bounces rays, is robust to this.
- **Furniture blocks the antenna position.** The desk surface in the mesh is at
  0.74 m, not the 0.70 m measured by tape, so the transmitter has to be placed
  above it (0.86 m) or the router ends up inside the desk.

## Answers to the Phase 0 questions

From the stitching plan, Part 7:

1. *Is the phone mesh good enough for propagation modelling?* For the room
   shell, yes: the Dachgeschoss geometry, roof pitch and stairwell came out
   well. For exact-path ray tracing, no. And it is blind to black, mirrored and
   glass objects, which matter most.
2. *Can the ESP32-C6 collect enough samples?* Yes: about 50 records/s, 750 per
   point, no losses over the survey. The walking survey was done with a fixed
   tripod rather than ARKit poses, which made positions easy to reproduce.
3. *ARKit drift?* Not tested. We dropped the iOS app for Phase 0 and placed the
   probe on floor stickers instead.
4. *Is Sionna worth it?* Not shown in this room. It ties with a two-line
   formula. We do not read this as a verdict on Sionna, but the burden of proof
   has moved: Phase 1 has to pick an environment and a protocol where a
   physics model can be expected to win, and show it.

## Proposals for Phase 1

These are open for discussion, roughly in order of how much we think they
matter.

- **Survey through interior walls.** That is where simple models break and
  where people actually have WiFi problems. The cheapest first step is the
  enclosed bathroom on the same floor: extend the scan into it and add a few
  points inside, with router and probe unchanged. The floor below, or a
  friend's flat, would come next.
- **Change the measurement protocol.** Record 3–5 sub-positions per point within
  about 30 cm and average them, so we compare against the local mean power that
  the models predict. The operator stands at a fixed spot, or leaves the room,
  during every window. Check the board orientation with a simple marker.
- **Clean the geometry before ray tracing.** Walls, floor and roof as planes
  (Apple RoomPlan's parametric output, e.g. via Polycam Room mode, is one
  route), plus explicit boxes for large furniture. This should make Sionna's
  exact-path solver usable and lets us assign materials per surface.
- **Find the LiDAR blind spots from the camera.** Monitors, TVs, mirrors and
  windows need to be detected in the RGB images and added as metal or glass.
  This is the material/object step of the original roadmap, and the loft shows
  it is not optional.
- **Turn on diffraction** for obstacles that graze the path (point 18), once
  the geometry is clean enough that edge diffraction is not run on every scan
  triangle.
- **Longer term:** iPhone 15 Pro and newer have hardware ray tracing in the GPU
  (A17 Pro onwards). An on-device propagation model, written against Metal
  rather than Sionna, would fit the data-stays-at-home positioning. Not a
  Phase 1 item.

## Reproducing

Main environment `.venv` (Python 3.13: usd-core, trimesh, scipy, matplotlib),
Sionna environment `.venv-sionna` (`sionna-rt` 2.2.0), ESP-IDF 5.5.4 under
`C:\Espressif` (build with `firmware/idf.ps1`).

```
.venv/Scripts/python.exe scripts/topdown_map.py          # top-down map
.venv/Scripts/python.exe scripts/locate_ap.py            # AP position
.venv/Scripts/python.exe scripts/mock_coverage.py        # mock prediction
.venv/Scripts/python.exe scripts/plan_points.py          # survey points + route
.venv/Scripts/python.exe scripts/csi_receiver.py         # during the survey
.venv/Scripts/python.exe scripts/analyze_survey.py       # mock vs measurement
.venv/Scripts/python.exe scripts/export_sionna_scene.py  # mesh + positions for Sionna
.venv-sionna/Scripts/python.exe scripts/sionna_radiomap.py --material plasterboard --max-depth 8 --samples 16000000
```

Raw survey data: `data/raw/survey_2026-10-02_round1-3.jsonl`. Derived tables
and figures: `data/derived/`. Wi-Fi credentials for the probe live only in
`firmware/csi_probe/sdkconfig.secrets` and must not be shared.

## Limitations

19 points in one room, one router position, one band, one day. The survey
points are where furniture allowed a tripod, not a designed sample, and they
cluster in the middle of the room. Point positions come from floor stickers
placed by eye from a map (estimated ±10–20 cm). Monitor and mirror positions
are the operator's estimates. RSSI is reported by the ESP32 in 1 dB steps and
is not absolutely calibrated; we only use differences. The CSI itself (64
subcarriers per record) is recorded but not yet analysed.
