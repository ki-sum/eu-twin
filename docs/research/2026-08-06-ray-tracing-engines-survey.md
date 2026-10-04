# Open-source EM ray tracing engines — survey for indoor WiFi digital twin

**Date**: 2026-08-06
**Source**: Parallel research subagent (general-purpose)

## Comparison table

| Engine | License | GitHub URL | GPU | EM material params (εr, σ) | Differentiable | Multipath (refl/diffr/scatter) | Active? |
|---|---|---|---|---|---|---|---|
| **Sionna RT** (NVIDIA) | Apache-2.0 | github.com/NVlabs/sionna-rt | CUDA (via OptiX/Mitsuba) + CPU via LLVM | Yes — ITU radio-material model (eta_r, sigma, thickness, scattering coef, xpd) | Yes (gradients via Dr.Jit) | LOS, specular, diffuse, refraction, diffraction, scattering | Yes, v2.0.1 (2026) |
| **Mitsuba 3** | BSD-3-Clause (~2.9k stars) | github.com/mitsuba-renderer/mitsuba3 | CUDA/OptiX + LLVM CPU | No (visual BSDFs only) — Sionna RT is the EM layer on top | Yes (via Dr.Jit) | Optical multi-bounce, not EM | Yes |
| **Dr.Jit** (JIT compiler) | BSD-3-Clause | github.com/mitsuba-renderer/drjit | CUDA + LLVM | n/a | Yes (foundation for both above) | n/a | Yes |
| **DiffeRT** (Eertmans, UCLouvain) | MIT | github.com/jeertmans/DiffeRT | GPU/TPU via JAX | Yes (EM field computation, RIS support) | Yes (JAX autodiff) | Path tracing between node pairs, RIS | Yes (pre-1.0, active 2026) |
| **PyLayers** (IETR Rennes) | MIT, ~205 stars | github.com/pylayers/pylayers | CPU only (NumPy) | Yes (UWB site-specific, incl. diffraction via UTD) | No | Reflection + UTD diffraction + multipath (delays, DoA/DoD) | Low — inactive since ~2021 |
| **Opal** (Egea-Lopez et al., Veneris) | MIT | gitlab.com/esteban.egea/opal | CUDA via NVIDIA OptiX (C++) | Yes | No | Ray-launching, specular + material response | Low — 2021 paper baseline |
| **OpenGERT** | Open source (MIT-style, MMSys'24) | search "OpenGERT" on GitHub | Depends on backend | Yes, geometry+EM sensitivity | Partial | Yes | New (2025) |
| **PBRT-v4** | BSD-2-Clause | github.com/mmp/pbrt-v4 | OptiX | No (visual) | No (reference renderer) | Optical only | Yes |

Not recommended as engines but worth knowing: **RadioPropa** (astrophysics, inhomogeneous media — not indoor WiFi); **ns-3 mmWave** (network sim, not a general RT engine); **WiThRay** (paper only, no public repo confirmed).

## Differentiable ray tracing and calibration

A differentiable ray tracer expresses the entire pipeline — geometry intersection, Fresnel coefficients, path summation, channel impulse response — as operations whose Jacobians are computed by an autodiff engine (Dr.Jit for Sionna/Mitsuba, JAX for DiffeRT). Concretely: you define a loss `L = ||CIR_sim(θ) − CIR_measured||²` where `θ` includes each surface's εr, σ, roughness. Because every op has a defined gradient, `∂L/∂θ` propagates back through reflections/diffractions, and you fit materials by gradient descent (Adam) instead of brute-force grid search. For the calibration loop (phone walks the room, measures RSSI, engine adjusts drywall/glass/concrete params), this turns a combinatorial problem into a smooth optimisation — Sionna's own `diff-rt-calibration` repo demonstrates fitting real measurements this way.

## Sionna RT for indoor WiFi MVP

Sionna RT is the only engine that combines Apache-2.0 (clean commercial use), true EM materials with ITU-R P.2040 permittivity/conductivity models, full multi-bounce with diffraction+scattering, and differentiability out of the box — the exact stack needed for the calibration loop. Scene input is Mitsuba XML with meshes (Blender + Mitsuba-Blender add-on is the documented authoring path), output is CIR / CFR / coverage-map tensors; official examples ship urban scenes (`munich`, `simple_street_canyon`) but no bundled indoor room — you'll build the first indoor scene in Blender from the phone scan. Windows caveat: GPU RT is not supported on native Windows or WSL2 (OptiX + TF constraint, issue #593); on Windows use Mitsuba's `cuda_ad_rgb` variant indirectly or run under Linux; RTX 30/40 series work on Linux with driver ≥ 550, though 555/560 have known OptiX-init bugs on 4090.

## Recommendation

- **Start with:** Sionna RT on Linux (or dual-boot / cloud L4/A10). It's the only engine that hits all four requirements (license, EM materials, differentiable, active).
- **Level-0 mock / Python-only fallback:** DiffeRT (JAX, MIT, pure Python, runs anywhere including Windows CPU). Use it to prototype the calibration loop and API surface before Sionna is wired in — same conceptual model (differentiable), much smaller install.
- **Watch:** OpenGERT (auto geometry extraction pairs naturally with phone-scan input) and Opal (if you ever need OptiX-native C++ speed and can drop autodiff).
- **Do not use:** PyLayers (dormant, not differentiable), raw Mitsuba 3 (no EM materials — Sionna is already the right wrapper), PBRT (visual only).

## Key references

- Sionna RT repo: https://github.com/NVlabs/sionna-rt
- Sionna RT tutorials: https://nvlabs.github.io/sionna/rt/tutorials/Introduction.html
- Calibration demo (differentiable fit to measurements): https://github.com/NVlabs/diff-rt-calibration
- DiffeRT (Python-only mock): https://github.com/jeertmans/DiffeRT
- Windows GPU limitation: https://github.com/NVlabs/sionna/issues/593
- Mitsuba 3 (dependency): https://github.com/mitsuba-renderer/mitsuba3
- Original Sionna RT paper: https://arxiv.org/pdf/2303.11103
