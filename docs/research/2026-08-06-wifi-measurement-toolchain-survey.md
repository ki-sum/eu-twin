# Indoor WiFi Measurement Toolchain — Research Report

**Date**: 2026-08-06
**Source**: Parallel research subagent (general-purpose)

## Platform capability table

| Platform | RSSI of connected AP | Scan nearby APs | Raw CSI | Notes |
|---|---|---|---|---|
| **iOS 12–18** | No public API for raw dBm; `NEHotspotNetwork.signalStrength` gives 0.0–1.0 bucket only | Blocked. `NEHotspotHelper` needs `com.apple.developer.networking.HotspotHelper` — Apple grants almost only to captive-portal / carrier apps; consumer WiFi apps get denied | No | No changes in iOS 17/18 that help. `CNCopyCurrentNetworkInfo` needs Location + associated-domain entitlement |
| **iPadOS** | Same as iOS | Same as iOS | No | No differences |
| **Android 10–15** | Yes, via `WifiManager.getConnectionInfo().rssi` | Yes via `startScan()` but **throttled: foreground 4 scans / 2 min, background 1 / 30 min**. Toggle off in Developer Options for testing | No (stock). Rooted Nexus 5 / 6P / RPi via Nexmon CSI only | Requires ACCESS_FINE_LOCATION at runtime. Also `WifiRttManager` for 802.11mc FTM ranging (~1 m, sub-1 m on 802.11az in Android 15) on supported chipsets |
| **macOS 14.4+** | `wdutil info` (needs sudo) or `CoreWLAN` framework | `CoreWLAN.CWInterface.scanForNetworks()` works but needs Location permission and signed binary | No | `airport` CLI removed in Sonoma 14.4 |
| **Linux** | `iw dev wlan0 link`, `iwconfig` | `iw dev wlan0 scan`, `wpa_cli scan_results` — no throttling, reliable | Yes: Nexmon CSI (RPi 3B+/4), Intel 5300 (Halperin tool), Atheros CSI tool | Best signal fidelity, worst form factor |
| **ESP32 / ESP32-C6** | Yes, in every scan result | `esp_wifi_scan_start()` — hundreds of ms per full scan; single-channel much faster | **Yes**: Espressif official `esp-csi` supports CSI on all ESP32 series including C6. Sampling rate is bounded by frame arrival rate at the STA — with a nearby AP in ping mode 100–500 Hz is realistic | Best walk-around form factor for a hobbyist; C6 also gets 6 GHz |

## Position tracking, ranked for this MVP

1. **ARKit `ARWorldTrackingConfiguration` on iPhone Pro with LiDAR** — best-in-class VIO, ~2 cm/s drift, cm-level over short walks in a lit, textured room. Same session that ran RoomPlan can continue emitting 6-DoF pose. Corridors and stairwells drift; a single-room home is fine.
2. **ARCore on flagship Android** — comparable in principle but empirically less stable than ARKit in the VIO benchmarks. Only relevant if the measurement device is Android.
3. **RTAB-Map / ORB-SLAM3 on a laptop with RGB-D or stereo** — mature, but heavy for a walk-around MVP; not worth it when ARKit is one API away.
4. **WiFi RTT (802.11mc / 802.11az)** — cool but requires FTM-capable APs; consumer routers rarely support it. Skip.
5. **BLE beacon triangulation** — needs pre-deploying beacons in the target home before every survey. Kills the "consumer walks in with a phone" UX.
6. **Manual tap-on-floorplan** — how every open-source heatmap tool works today (see `jantman/python-wifi-survey-heatmap`). Acceptable for MVP; expect 30–50 cm human placement error and ~30 points per room instead of thousands.

## Existing open-source projects worth pulling from

- https://github.com/espressif/esp-csi — official ESP32 CSI, works on C6
- https://github.com/StevenMHernandez/ESP32-CSI-Tool — well-documented walkthrough, CSV output
- https://github.com/seemoo-lab/nexmon_csi — Broadcom CSI on rooted Android/RPi
- https://github.com/jantman/python-wifi-survey-heatmap — Linux, iperf3 + floorplan clicks, closest thing to your workflow
- https://github.com/hnykda/wifi-heatmapper — macOS/Windows/Linux, uses `wdutil` on Sonoma
- https://github.com/kismetwireless/kismet — passive sniffer + GPS-tagged log (`.kismet` SQLite)
- https://github.com/NVlabs/sionna — the ray-tracer to calibrate against; differentiable, materials are ITU-R P.2040, gradients wrt material params are built-in — this is the killer feature for step 6
- https://arxiv.org/abs/2511.00494 — "Indoor Radio Mapping Dataset Combining 3D Point Clouds and RSSI" — the closest prior art; read before building

Nothing in the wild combines RoomPlan + RSSI + ray-tracing calibration. There is a gap here.

## Recommended MVP toolchain (opinionated)

**Single-device path: iPhone Pro does everything.**

- RoomPlan scan produces the USDZ mesh.
- Immediately after, keep the `ARSession` running in `ARWorldTrackingConfiguration`. User is prompted to walk the room holding the phone.
- Phone measures RSSI of the target router via `NEHotspotNetwork.fetchCurrent` (bucketed 0–1) — this is the honest limit on iOS.
- Because the bucketed value is useless for calibration, **pair the phone with a tethered ESP32-C6 puck** running `esp-csi` connected as a STA to the target router. Puck streams `{timestamp, rssi_dbm, csi_amplitude[64]}` over BLE or USB-C serial to the iPhone at ~50 Hz.
- iPhone timestamps each sample and attaches the current ARKit pose (`ARFrame.camera.transform`, `worldMappingStatus == .mapped`).
- Export JSONL: `{t, x, y, z, qw, qx, qy, qz, rssi_dbm, csi:[...], room_uuid, ap_bssid}`.
- Python calibration script loads USDZ into Sionna RT, places the AP at the annotated position, and uses Sionna's differentiable material gradients to fit ITU-R P.2040 params to the measured RSSI/CSI cloud.

The ESP32-C6 puck is the piece that makes this actually work — we already have one and know ESP-IDF, so this is essentially free.

## Gotchas that will bite in week 1

- ARKit pose is in the RoomPlan session's coordinate frame — if you stop and restart the session, the origin moves. Don't drop the session between scan and survey.
- iOS `NEHotspotNetwork.signalStrength` is a **quality bucket**, not dBm. Do not calibrate against it.
- ESP32 CSI amplitude has a per-boot random gain offset; log a known-position calibration point at the start of every walk and subtract.
- Android `startScan()` throttling silently returns cached results — always check `WifiManager.WIFI_SCAN_AVAILABLE` broadcast and enable "WiFi scan throttling off" in Developer Options during MVP.
- macOS `wdutil` needs `sudo` every call; scriptable via NOPASSWD sudoers but this bites CI.
- Sionna RT needs the mesh watertight and with material labels — RoomPlan exports semantic labels (wall/window/door) via `CapturedRoom` — extract these before feeding Sionna, otherwise every surface defaults to concrete.
- Router position error dominates the residual. Provide an in-app "tap the router" step and require the user to physically hold the phone against it once for ground truth.

## Sources

- [iOS WiFi scan API discussion](https://developer.apple.com/forums/thread/788783)
- [NEHotspotHelper entitlement rarely granted](https://developer.apple.com/forums/thread/718089)
- [Android WiFi scan throttling docs](https://developer.android.com/develop/connectivity/wifi/wifi-scan)
- [macOS airport removed in 14.4](https://www.intuitibits.com/2024/03/14/goodbye-airport/)
- [wdutil replacement writeup](https://dev.to/jaisonerick/reading-wi-fi-data-from-go-on-macos-after-apple-removed-airport-19g)
- [Espressif esp-csi (ESP32-C6 supported)](https://github.com/espressif/esp-csi)
- [StevenMHernandez ESP32-CSI-Tool](https://github.com/StevenMHernandez/ESP32-CSI-Tool)
- [Nexmon CSI (Broadcom/rooted Android)](https://github.com/seemoo-lab/nexmon_csi)
- [ARKit VIO drift benchmark (~2 cm/s)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9785098/)
- [Android WiFi RTT / 802.11mc](https://developer.android.com/develop/connectivity/wifi/wifi-rtt)
- [Android 15 WiFi Ranging (802.11az, sub-1 m)](https://www.androidauthority.com/android-15-wi-fi-ranging-3498128/)
- [jantman python-wifi-survey-heatmap](https://github.com/jantman/python-wifi-survey-heatmap)
- [hnykda wifi-heatmapper (uses wdutil)](https://github.com/hnykda/wifi-heatmapper)
- [Kismet with GPS tagging](https://www.kali.org/tools/kismet/)
- [NVIDIA Sionna RT (differentiable, ITU-R materials)](https://github.com/NVlabs/sionna)
- [Sionna RT paper (differentiable ray tracing)](https://arxiv.org/pdf/2303.11103)
- [Indoor Radio Mapping Dataset: 3D point clouds + RSSI](https://arxiv.org/pdf/2511.00494)
- [Apple RoomPlan overview](https://machinelearning.apple.com/research/roomplan)
