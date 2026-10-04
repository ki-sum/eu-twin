# Router placement apps: quick market scan (2026-10-04)

Question: does an app already exist that lets you walk
through a home once, mark the router, and get predicted coverage, weak spots
and a better router position? Or is this a gap?

Short answer: it is not a gap. Several small apps already combine a LiDAR
scan with a router placement suggestion. What we did not find is an app that
fits its propagation model to measurements taken in that home. This is a
one-hour scan of store pages and product docs, not a full competitive study;
we have not installed or tested any of these apps.

## Consumer apps that already suggest router positions

- **WiFi Sage** (iOS, Tap Water Ltd, v1.0 in May 2026, 6 ratings): LiDAR/AR
  scan, "Path Loss Model + Genetic Algorithm AI", recommends router position
  and whether a mesh is needed. $19.99/year or $39.99 lifetime. The store page
  does not say whether the model is fitted to measurements.
  https://apps.apple.com/us/app/wifi-sage-wifi-ar-heat-map/id6763244358
- **LiDAR WiFi Planner** (iOS, Yu-Chiao Wang, since June 2024, too few
  ratings to show): LiDAR floor plan, measures throughput/latency (not RSSI,
  because iOS hides it), "multi-AP / mesh / extender simulation (FSPL +
  wall-loss model)" and a "Coverage Advisor" that suggests where to add an AP.
  https://apps.apple.com/gb/app/lidar-wifi-planner/id6780439542
- **NetSpot** (Windows/macOS/Android): Planning Mode with hand-drawn walls and
  materials, simulated router positions, plus measured surveys.
  https://help.netspotapp.com/help/how-to-perform-predictive-survey-with-netspot/
- **TP-Link Deco app**: guided placement of mesh satellites, checks link
  quality to the main unit before you commit.
  https://www.omadanetworks.com/us/support/faq/1446/

## Apps that only map measurements (no what-if)

- **WiFi Heatmap & Speed Survey** (iOS, AetherCore LLC): multi-room LiDAR
  plan, RSSI via iOS Shortcuts, interpolated heatmap, no simulation. 3
  ratings, one review calls the mapping inaccurate.
  https://apps.apple.com/us/app/wifi-heatmap-speed-survey/id6761348520
- **Signl** (iOS): speed and ping per room, optional LiDAR model, no placement
  suggestion. https://www.signlwifi.com/
- **Robot vacuums**: iRobot Roomba 900 series built Wi-Fi coverage maps while
  cleaning (https://support.irobot.co.uk/articles/en_GB/Knowledge/31251);
  Ecovacs DEEBOT shows Wi-Fi strength on its map
  (https://www.epdtonthenet.net/article/156030/The-robots-that-read-the-room--Smart-Navigation-Function-in-the-home.aspx).
  Neither predicts what happens if the router moves.

## Professional tools

- **Ekahau AI Pro**: predictive design with wall materials and an AI
  auto-planner for AP positions, aimed at IT professionals.
  https://www.openreality.co.uk/product/ekahau-ai-pro/
- **Hamina** (Planner + Onsite): survey app on iOS/macOS with external
  measurement hardware (Hamina Clip, Oscium Nomad, WLAN Pi).
  https://docs.hamina.com/hamina/onsite

## A side finding: RSSI on iOS

Since iOS 17 the Shortcuts action "Get Network Details" returns RSSI, noise,
channel and link rates of the current network
(https://www.intuitibits.com/2023/09/). Apps still cannot read RSSI directly,
and a shortcut gives one reading per run, so this is far below the ~100
readings/s of our ESP32 probe. Worth testing whether it is good enough for a
probe-free mode.

## Prices (from store pages, 2026-10-04)

All consumer apps are freemium: free download, paid tier for the useful parts.
WiFi Sage $2.99/week, $19.99/year, $39.99 lifetime. LiDAR WiFi Planner free
for one plan, then £1.99 / £9.99 / £99.99. WiFi Heatmap $9.99/month. Signl
$34.99/year. NetSpot Home $59, Pro $119
(https://betanews.com/2025/07/15/netspot-5-0-can-identify-wi-fi-dead-spots/).
Router vendor apps (Deco) are free with the hardware. Ekahau is priced for
companies.

## Room geometry from the phone

WiFi Sage, LiDAR WiFi Planner and WiFi Heatmap use the iPhone LiDAR to build a
floor plan (WiFi Heatmap merges multiple rooms with doorway detection). Signl
uses LiDAR optionally. NetSpot, Ekahau and the open-source tools work from a
floor plan image or hand-drawn walls. None of the store pages mentions
multiple floors from a scan.

## Open source on GitHub

- **WiFi-Heatmap-Architect** (Zizlik, MIT, 2026, 0 stars): hand-drawn floor
  plan, log-distance model with per-wall losses after ITU-R P.1238,
  **calibrated from the user's measurements**, and an optimizer that scores
  router positions every ~0.5 m. Closest to our idea, minus the scan and the
  walk. https://github.com/Zizlik/WiFi-Heatmap-Architect
- **wifi-planner** (crazyman62, ~40 stars): desktop predictive planner,
  log-distance + wall + floor attenuation, multiple floors, no calibration
  against measurements. https://github.com/crazyman62/wifi-planner
- Measurement-only heatmappers: https://github.com/hnykda/wifi-heatmapper,
  https://github.com/ribaldorafael/wifi-heatmap,
  https://github.com/jantman/python-wifi-survey-heatmap
- RoomPlan wrappers for Flutter (MIT): https://pub.dev/packages/roomplan
- No open-source project found that combines a phone scan with walking RSSI.

## Do we need extra hardware?

- **iPhone**: apps cannot read RSSI. Options are the ESP32 probe, throughput
  as a proxy (what the iOS apps above do), or the Shortcuts reading (untested).
- **Android**: apps can read the RSSI of the connected network
  (`WifiInfo.getRssi()`, https://developer.android.com/reference/android/net/wifi/WifiInfo).
  How often the value refreshes is not documented; must be tested on the
  a Huawei P30 Pro. Most Android phones have no LiDAR; ARCore gives the
  walking path from the camera, geometry would be coarser.
- **Router side**: the FRITZ!Box reports each client's signal strength over
  TR-064 (openHAB binding channel `macSignalStrength1`,
  https://www.openhab.org/addons/bindings/tr064). A router can measure the
  phone instead of the phone measuring the router. For a router OEM or ISP
  customer this removes the probe completely. Polling rate not yet tested.

## Where we might still differ

Our own data says the default wall losses these apps use can be badly off.
On the test house's lower floor, free space + 8 dB per wall gave 8.2 dB RMSE,
while the same model with the loss fitted from a walk gave 1.6 dB; the
concrete slab step (13.5 dB) learned with one router carried over to a
second router (Phase 1 report, sections 3-6). Calibration alone is not new
(WiFi-Heatmap-Architect does it from a few hand-placed points). What we have
not seen anywhere is the combination: geometry from the phone, thousands of
positioned readings from one walk, a slab loss learned per house and carried
over to other router positions, and physics only where a floor has many
rooms. Whether WiFi Sage or LiDAR WiFi Planner calibrate internally we could
not tell from their store pages.

The low rating counts (3-6 ratings) suggest these consumer apps have little
traction so far. That fits the strategy note that the paying customers are
router OEMs, ISPs and robot vendors, not end users, but we have no data on
that yet.
