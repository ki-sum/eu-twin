# EM Material Parameter Data for Building Materials — Public Sources Survey

**Date**: 2026-08-06
**Source**: Parallel research subagent (general-purpose)

## 1. What ITU-R P.2040-3 actually gives you

**P.2040-3 (Aug 2023)** is free to download from ITU and is the de facto anchor. Rather than measurement tables, it provides a **frequency-parameterised formula**:
- εr = a · f_GHz^b
- σ = c · f_GHz^d  (S/m)
- loss tangent derived: tanδ = σ / (2π·f·ε0·εr)

Table 3 covers **14 materials × 4 coefficients** with valid frequency ranges (confirmed via MATLAB Antenna Toolbox mirror and Sionna source):

| Material | a | b | c | d | f range (GHz) |
|---|---|---|---|---|---|
| Vacuum | 1 | 0 | 0 | 0 | 0.001–100 |
| Concrete | 5.24 | 0 | 0.0462 | 0.7822 | 1–100 |
| Brick | 3.91 | 0 | 0.0238 | 0.16 | 1–40 |
| Plasterboard (drywall) | 2.73 | 0 | 0.0085 | 0.9395 | 1–100 |
| Wood | 1.99 | 0 | 0.0047 | 1.0718 | 0.001–100 |
| Glass | 6.31 | 0 | 0.0036 | 1.3394 | 0.1–100 |
| Glass (high-f) | 5.79 | 0 | 0.0004 | 1.658 | 220–450 |
| Ceiling board | 1.48 | 0 | 0.0011 | 1.0750 | 1–100 |
| Chipboard | 2.58 | 0 | 0.0217 | 0.78 | 1–100 |
| Plywood | 2.71 | 0 | 0.33 | 0 | 1–40 |
| Marble | 7.074 | 0 | 0.0055 | 0.9262 | 1–60 |
| Floorboard | 3.66 | 0 | 0.0044 | 1.3515 | 50–100 |
| Metal | 1 | 0 | 10⁷ | 0 | 1–100 |
| Ground (dry/med/wet) | 3 / 15 / 30 | 0 / −0.1 / −0.4 | 0.00015 / 0.035 / 0.15 | 2.52 / 1.63 / 1.30 | 1–10 |

License: ITU-R Recommendations are freely downloadable; coefficient tables are numeric facts (no copyright on the numbers themselves; the text is © ITU). **P.2040-4** (Sep 2025) is now current — same structure, extended above 100 GHz.

**Note P.1238-13** (indoor propagation) does NOT publish additional material εr/σ — it gives *aggregate* path-loss and floor/wall penetration-loss constants for statistical models, not per-material EM parameters.

## 2. Other free authoritative sources

- **3GPP TR 38.901** (via ETSI, free): Table 7.4.3-1 — penetration-loss vs frequency for concrete, IRR glass, standard glass, wood (linear model, 0.5–100 GHz). Aggregate-loss format, not εr/σ.  https://www.etsi.org/deliver/etsi_tr/138900_138999/138901/
- **Sionna RT `ITURadioMaterial`** — turnkey wrapper of P.2040-3 with the 14 materials pre-loaded. Source: `sionna/rt/radio_materials/itu.py` on https://github.com/NVlabs/sionna (Apache 2.0).
- **NYUSIM** (MIT-style, free) — 0.5–150 GHz simulator with parabolic building-penetration model (low/high-loss classes only, not per-material εr). https://wireless.engineering.nyu.edu/nyusim/
- **NYU / Rappaport measurement papers** (arXiv, open):
  - 28/73 GHz indoor materials: arXiv:1703.08030, 1908.00166
  - 28/73/91 GHz attenuation (glass, drywall, wood, brick): ResearchGate 339540385
  - 6.75/16.95 GHz FR1(C)/FR3 penetration: arXiv:2405.01362, 2412.08752
  - 140 GHz calibration: arXiv:2410.03104
- **Ofcom / BRE "Building Materials and Propagation" (2014)** — 123 pp, two real UK houses + anechoic chamber at 88 MHz, 217 MHz, 698 MHz, 2.4 GHz, 5.7 GHz. Free PDF: http://www.qostic.org/Qostic/wp-content/uploads/Qostic6/AHQ-78-05-Building_Materials_and_Propagation.pdf and https://www.ofcom.org.uk/research-and-data/technology/general/building-materials
- **Télécom Paris / HAL** — "Material Permittivity and Conductivity Estimation from 2 to 260 GHz" extending P.2040 above 100 GHz. https://telecom-paris.hal.science/hal-04688601v1
- **MDPI Appl. Sci. 2025 W-band study** (75–110 GHz attenuation, several building materials, open access): https://www.mdpi.com/2076-3417/15/24/13178
- **NIST CTL mmWave scattering system** — publications only, no downloadable DB: https://www.nist.gov/ctl/millimeter-wave-scattering-system-materials-testing
- **IEEE DataPort 60 GHz digital-twin channel map** (measurements, not εr tables): https://ieee-dataport.org/documents/indoor-60-ghz-radio-channel-map-digital-twin-construction-directional-beam-measurements
- **NVlabs/diff-rt** — differentiable-learning of material params from measurements (Apache 2.0): https://github.com/NVlabs/diff-rt
- **WiSegRT** — 3D-segmented indoor RT dataset: arXiv:2312.11245

## 3. What is behind a paywall / not public

- Remcom Wireless InSite ships a proprietary material DB (not published as a table anywhere I can find).
- Altair WinProp same — configurable but no public parameter list.
- MetaRadio (Beijing Qianjing) — advertised material library, no public docs surfaced.
- NIMS/Murata 20k dielectric DB — mostly capacitor ceramics, not construction materials; 2026 release, unclear license.
- Chinese-university (BJTU/BUPT) measurements exist in IEEE Xplore/Springer papers, individually paywalled.

## 4. Gap analysis for European homes

P.2040-3 covers the eight most common surfaces you'll actually hit (concrete, brick, drywall, wood, glass, chipboard, plywood, ceiling-board, marble/floor/metal). **Real gaps**:
- Modern German construction: **Ytong/AAC aerated concrete**, **Poroton (perforated clay)**, **EPS/rock-wool/glass-wool insulation**, **KfW-standard triple glazing with low-E coating** (IRR glass ≠ standard glass), **vapour barriers with aluminium foil**, **underfloor-heating screed with rebar mesh**, **wallpaper (esp. metallic/glass-fibre)**, **modern ceramic/porcelain tile**, **laminate flooring core (HDF)**, **carpet**. None of these are in P.2040-3.
- 6 GHz (WiFi 6E) is inside all P.2040-3 ranges — no interpolation needed.
- **60 GHz** is inside range for concrete/plasterboard/wood/glass/marble/chipboard, but brick and plywood valid only to 40 GHz — use Rappaport 60/73 GHz numbers here.
- **UWB 6.5/8 GHz** is fine everywhere.

## 5. Bootstrap recommendation

**Yes, MVP-viable from P.2040-3 alone.** You get 14 materials × any frequency in 1–100 GHz × (εr, σ, tanδ) = a complete dense grid for the eight WiFi/UWB/mmWave bands you care about. That is ~14 × 8 × 3 = **~336 populated (material, band, parameter) cells** on day one, wrapped by Sionna's `ITURadioMaterial` so zero implementation cost.

Layer on top:
1. Sionna's ITU wrapper as baseline (Apache 2.0 code reuse).
2. Ofcom/BRE 2014 report for 700–900 MHz and 2.4/5.7 GHz sanity-check on real UK/EU wall stacks.
3. Rappaport papers as override for 28/60/73 GHz where P.2040-3 is out of range or thin.
4. 3GPP 38.901 penetration-loss numbers to sanity-check whole-wall aggregate loss (not per-material, but validates the ray-tracer output).

**What you'll still need to measure yourselves** to be defensible as a moat: Ytong/AAC, Poroton, low-E triple glazing, EPS/rock-wool, foil vapour barriers, modern floor stacks. That's ~8–12 materials × 4–6 frequencies — a plausible in-house/university-partnership measurement campaign (VNA + free-space horn setup, or open-resonator for mmWave). PTB Braunschweig or Fraunhofer HHI/IZM would be the German metrology partners; neither publishes an open EU-building-material DB today.

## 6. Candidate open projects to contribute back to

- **NVlabs/sionna** — extend `radio_materials/itu.py` with a `EUBuildingMaterial` class carrying the European additions.
- **NVlabs/diff-rt** — pipeline for learning εr/σ from measurements; directly reusable to backfill missing materials.
- **chenhaowu5/EM-NeRF** — actively curated index of EM-neural-field work; good place to publish a dataset.
- **WiSegRT** — segmented indoor scenes; natural home for a paired-material-label + EM-parameter release.

## Key references

- [ITU-R P.2040-3 PDF](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.2040-3-202308-S!!PDF-E.pdf)
- [ITU-R P.2040-4 (2025)](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.2040-4-202509-I!!PDF-E.pdf)
- [ITU-R P.1238-9](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.1238-9-201706-I!!PDF-E.pdf)
- [MATLAB buildingMaterialPermittivity (Table 3 mirror)](https://www.mathworks.com/help/antenna/ref/buildingmaterialpermittivity.html)
- [Sionna RT Radio Materials docs](https://nvlabs.github.io/sionna/rt/api/radio_materials.html)
- [Sionna GitHub](https://github.com/NVlabs/sionna)
- [NVlabs diff-rt](https://github.com/NVlabs/diff-rt)
- [ETSI TR 138.901 (3GPP)](https://www.etsi.org/deliver/etsi_tr/138900_138999/138901/15.00.00_60/tr_138901v150000p.pdf)
- [NYUSIM download](https://wireless.engineering.nyu.edu/nyusim/)
- [NYU 73 GHz penetration loss arXiv:1703.08030](https://arxiv.org/pdf/1703.08030)
- [NYU 73/81 GHz arXiv:1908.00166](https://arxiv.org/pdf/1908.00166)
- [FR1(C)/FR3 penetration arXiv:2405.01362](https://arxiv.org/pdf/2405.01362)
- [FR1/FR3 model arXiv:2412.08752](https://arxiv.org/pdf/2412.08752)
- [NYURay 28/73/142 GHz arXiv:2410.03104](https://arxiv.org/pdf/2410.03104)
- [Ofcom/BRE 2014 Building Materials and Propagation](http://www.qostic.org/Qostic/wp-content/uploads/Qostic6/AHQ-78-05-Building_Materials_and_Propagation.pdf)
- [Ofcom index page](https://www.ofcom.org.uk/research-and-data/technology/general/building-materials)
- [Télécom Paris 2–260 GHz extension of P.2040](https://telecom-paris.hal.science/hal-04688601v1)
- [MDPI W-band (75–110 GHz) attenuation](https://www.mdpi.com/2076-3417/15/24/13178)
- [NIST mmWave scattering system](https://www.nist.gov/ctl/millimeter-wave-scattering-system-materials-testing)
- [NIST dielectric measurement methods 30–100 GHz](https://www.nist.gov/publications/dielectric-measurement-methods-millimeter-wave-frequencies)
- [IEEE DataPort 60 GHz indoor channel map](https://ieee-dataport.org/documents/indoor-60-ghz-radio-channel-map-digital-twin-construction-directional-beam-measurements)
- [Remcom Wireless InSite materials page](https://www.remcom.com/wireless-insite-em-propagation-software/materials)
- [WiSegRT dataset arXiv:2312.11245](https://arxiv.org/html/2312.11245v2)
- [EM-NeRF curated index](https://github.com/chenhaowu5/EM-NeRF)
- [NIMS MatNavi dielectric DB](https://mits.nims.go.jp/)
