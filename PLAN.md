# PLAN.md: Flash-Flood Street Alerts, Prototype Build Plan

> **For Claude Code.** This is the build plan for our team's entry to the Sime Darby Property University Hackathon 2026 (Planet track, Climate Resilience). Read this whole file before writing any code. Build phase by phase, in order. At the end of each phase, run the tests, show a working demo for that phase, and commit. Stop and ask the team when you reach any item marked **🟡 TEAM DECISION**.

---

## 0. Context in one page

**The idea.** Put low-cost ultrasonic water-level sensors in drains, culverts, underpasses and basement car-park ramps inside a township. They measure how fast the water is rising and predict when each street will flood. Residents on the affected streets get a targeted message such as *"Move your car to Car Park X now. About 20 minutes until flooding."* The message has an **"I moved my car"** button.

**Pilot township.** Bandar Bukit Raja (BBR), Klang, Selangor. It has recurring flash floods. Jalan Makyong is reported to flood about three times a year since 2021.

**Why a simulation.** We are CS students and we can't make a real flood on demand. The prototype is therefore an **agent-based simulation in Mesa (Python)**. Each tick is 1 minute. Every input that can be real is real: terrain, roads, buildings, car parks and rainfall. Only the water flow and resident decisions are simulated.

**The two numbers we are judged on:**
1. **Alert lead time.** Minutes from the ACT alert to the street reaching **0.3 m** of water.
2. **Vehicles moved before flooding.** The share of at-risk cars that reach safe ground before their parking spot reaches 0.3 m.

**Required prototype deliverables (from our proposal):**
- A. A Mesa model on GitHub that runs 4 scenarios with Monte Carlo sweeps.
- B. A browser dashboard that shows water rising and cars moving on the BBR map.
- C. A mock-up of the resident alert (phone screen with the "I moved my car" button).
- D. Results figures and tables for the pitch deck.

### Alert levels (starting values; tune them in the simulation)

| Level | Trigger | Message |
|---|---|---|
| WATCH | Drain > 50% full **and** rising fast, or a thunderstorm warning in the rainfall input | "Heavy rain and drain levels rising. Be ready to move your car." |
| ACT | Predicted time-to-flood (TTF) for the street < 30 min, **confirmed** by 2 sensors, or by 1 sensor plus rainfall above a threshold | "Move your car to [nearest safe car park] now. About N minutes until flooding." + "I moved my car" button |
| AVOID | ≥ 0.15 m of water on the road | "Jalan X is flooded. Do not drive through. Use route Y." |
| ALL CLEAR | Water level falling for 30 consecutive min | "Water has receded on Jalan X." |

**Predictor:** `TTF = (critical_level − current_level) / rate_of_rise`. Fit `rate_of_rise` over the last 10 minutes of readings (least-squares slope, not just two points), and apply a multiplier when rainfall intensity is high. Keep it simple and explainable on purpose.

### Scenarios to compare

| ID | Name | Rule |
|---|---|---|
| S0 | No alerts | Residents only react when water reaches their own door and they are awake |
| S1 | River-style alert | One township-wide broadcast, triggered by a "virtual river gauge" (see §4.6). It has a publishing delay and a dissemination delay, and only reaches 56% of residents (Alias et al., 2020) |
| S2 | Street sensors, fixed threshold | ACT when the sensor serving a street is > X% full |
| S3 | Street sensors + rate-of-rise | ACT when predicted TTF < 30 min, with 2-source confirmation |

**Sweeps:** sensor count {5, 10, 20, 40} × compliance {0.3, 0.5, 0.8} × scenario {S0–S3} × storm. Run each cell **N Monte Carlo runs** with different seeds (N = 100 by default, configurable).

---

## 1. Ground rules for Claude Code

1. **Never fabricate data.** Every number that is not computed from a real dataset goes in `config/` with either a `source:` (citation) or `assumption: true` plus a one-line reason. Generate `docs/ASSUMPTIONS.md` automatically from the config (Phase 7). Judges will ask "where did this number come from?", and we must always have an answer.
2. **Toy world first, real world second.** Phase 2 builds the whole pipeline (water → sensors → alerts → residents → metrics → dashboard export) on a **synthetic 50×50 grid with a fake road graph**. Swap in real BBR data only after that works end to end. This is the main way we reduce risk.
3. **Separate the deterministic water from the stochastic people.** Water depth depends only on the storm and terrain, not on resident behaviour, so compute it **once per storm** and cache it as `depth[t, row, col]`. Monte Carlo runs then replay the cached water and only re-sample sensor noise and resident behaviour. This makes thousands of runs cheap.
4. **Treat the water as numpy and the decision-makers as Mesa agents.** Water is a vectorised grid that the model updates each tick. Sensors, the alert system and residents are Mesa agents. Do not make 20,000 grid cells into agents.
5. **Pin versions and check APIs.** Use Mesa 3.x. Mesa 3 removed schedulers: agents are created with `Agent(model)`, there is no `unique_id` argument, and you call `model.agents.shuffle_do("step")` or `model.agents_by_type[...]`. OSMnx 2.x renamed several functions (`features_from_point`, etc.). Check the installed version's API before writing code against it.
6. **Make everything reproducible.** One seed controls each run. Every result file records the config hash, git commit and seed.
7. **Keep the demo offline-safe.** The pitch dashboard must work with no Python server and no internet. It is a static site that replays precomputed JSON. A live server is optional and only for development.
8. **Commit after each phase** with a clear message. Keep `README.md` current with how to run things.

---

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Mesa, geo stack |
| ABM | `mesa` 3.x | Named in our proposal |
| Geo | `osmnx`, `geopandas`, `shapely`, `rasterio`, `pyproj`, `networkx` | OSM roads/buildings, DEM, routing |
| Numerics | `numpy`, `scipy`, `pandas`, `pyarrow` | Water grid, stats, Parquet results |
| Config | `pydantic` + YAML | Validated, documented parameters |
| Parallel | `joblib` | Monte Carlo |
| Plots | `matplotlib` (static figures for the deck) | |
| Tests | `pytest` | |
| Dashboard | Static site: **Vite + vanilla TypeScript** (or plain JS), **MapLibre GL JS** + **deck.gl** | Smooth animated map, no backend, deploys to GitHub Pages |
| Alert mock-up | A page inside the same static site, styled as a phone with a Telegram-style chat | One deployable link for judges |
| Optional | Telegram bot (`python-telegram-bot`) that sends real alerts during a replay | "Wow" moment in the live demo; stretch goal only |

Use `uv` or `pip` with a `pyproject.toml`. Add a `Makefile` (or `justfile`) with targets: `setup`, `data`, `test`, `sim`, `sweep`, `export`, `figures`, `dash`.

---

## 3. Repository layout

```
flash-flood-street-alerts/
├── README.md
├── PLAN.md                     # this file
├── pyproject.toml
├── Makefile
├── config/
│   ├── base.yaml               # all parameters, each with source/assumption
│   ├── area_bbr.yaml           # bbox, CRS, safe zones, validation streets
│   ├── storms/                 # one YAML/CSV per storm (hyetograph)
│   └── sweeps/default.yaml     # scenario × sensors × compliance × N
├── data/
│   ├── raw/                    # downloaded (git-ignored), with download script
│   ├── processed/              # dem_clipped.tif, roads.graphml, buildings.gpkg, ...
│   └── cache/                  # cached water simulations per storm (npz)
├── src/ffsa/
│   ├── config.py               # pydantic models
│   ├── data/
│   │   ├── fetch_dem.py
│   │   ├── fetch_osm.py
│   │   ├── rainfall.py         # load real hyetographs + design storm generator
│   │   └── prepare.py          # clip, reproject, burn roads/buildings, link streets↔cells
│   ├── hydro/
│   │   ├── runoff.py           # MSMA rational method
│   │   ├── drains.py           # drain-node storage & capacity
│   │   ├── surface.py          # cellular surface-flow routing
│   │   └── simulate.py         # run full storm → depth[t,r,c] + drain_level[t,node]
│   ├── abm/
│   │   ├── model.py            # FloodModel(mesa.Model)
│   │   ├── sensor.py           # SensorAgent
│   │   ├── alert.py            # AlertSystemAgent + scenario strategies S0–S3
│   │   ├── resident.py         # ResidentAgent
│   │   └── placement.py        # sensor placement strategies
│   ├── metrics.py              # lead time, % moved, RM avoided, false alarms
│   ├── experiments/
│   │   ├── run_one.py
│   │   └── sweep.py            # Monte Carlo grid → results/*.parquet
│   ├── export/
│   │   └── replay.py           # one run → dashboard/public/runs/<id>/*.json
│   └── figures.py              # deck-ready PNG/SVG charts
├── tests/
├── results/                    # parquet + figures (git-ignored except summary)
├── docs/
│   ├── ASSUMPTIONS.md          # auto-generated
│   ├── VALIDATION.md           # model vs reported flooded streets
│   └── DEMO_SCRIPT.md
└── dashboard/
    ├── index.html              # map replay + KPIs
    ├── results.html            # Monte Carlo charts
    ├── alert.html              # phone mock-up
    ├── src/
    └── public/runs/            # exported replays + geojson
```

---

## 4. The model in detail

### 4.1 Study area
- Geocode "Bandar Bukit Raja, Klang, Selangor" with OSMnx and show the team the resulting boundary/bbox on a quick map. **🟡 TEAM DECISION:** confirm the bbox. It must include Jalan Makyong and the reported flood streets. Store it in `area_bbr.yaml`.
- Use a projected CRS in metres: **EPSG:3168 (Kertau RSO)** or UTM 47N (EPSG:32647). Pick one and use it everywhere. Export to EPSG:4326 only for the dashboard.
- Check whether "Jalan Makyong" exists in OSM within the bbox. Print the matching street names. If it is missing or spelled differently, tell the team.

### 4.2 Terrain (Copernicus GLO-30)
- Download the tile covering the bbox from the open AWS bucket (no login). BBR is around 3°N, 101°E, so the tile should be `Copernicus_DSM_COG_10_N03_00_E101_00_DEM`. Verify the exact URL/name before relying on it. Clip and reproject to the project CRS at 30 m.
- **Known caveat:** Copernicus is a *surface* model, so buildings and trees appear as bumps. Mitigate this:
  1. Mask OSM building footprints and replace those cells with the median of the surrounding non-building cells.
  2. Lower road cells slightly (e.g. 0.1–0.2 m, as an assumption) so water follows streets, as it does in reality.
  3. Fill tiny pits (< 1 cell), but **keep** real depressions, because those are where floods happen.
  4. Document all of this in ASSUMPTIONS.md.
- A ~4 × 4 km area is roughly 130 × 130 cells. Keep it vectorised.

### 4.3 Roads, buildings, car parks (OpenStreetMap via OSMnx)
- Drive network → `networkx` graph in the project CRS. Keep edge `name`, `length` and geometry.
- **Street segment = the unit of alerting.** Group edges by street name (or by edge for unnamed roads). For each segment, store the list of grid cells it passes through.
- Buildings: residential footprints (`building=house/residential/terrace/apartments`, or untagged buildings inside `landuse=residential`). These become resident homes.
- **Safe zones:** OSM `amenity=parking` with `parking=multi-storey`, plus the top ~10% highest-elevation road-accessible cells. **🟡 TEAM DECISION:** add or confirm named safe car parks in `area_bbr.yaml`. Real SDP or mall car parks make the alert message more convincing.

### 4.4 Rainfall
Support two storm sources, both loaded into the same format: a per-minute intensity series in mm/hr.
1. **Real storm replay (preferred).** CSV with columns `timestamp, rainfall_mm`, at whatever interval the source has, resampled to 1 min. **🟡 TEAM DECISION:** pick the data source. Options:
   - JPS / MetMalaysia records for 17–18 Dec 2021 (team requests or transcribes them).
   - **GPM IMERG** half-hourly satellite rainfall (real, global, free with a NASA Earthdata login).
   - Values transcribed from published reports.

   Each storm file must carry a `source:` field. **Do not invent a hyetograph and call it real.**
2. **Design storm (fallback, clearly labelled synthetic).** Use the MSMA IDF relationship with a chosen ARI and duration, plus a temporal pattern. The team supplies the IDF coefficients for the nearest Klang station from MSMA 2nd ed. Until then, use a placeholder file named `design_storm_PLACEHOLDER.yaml` that the dashboard labels "synthetic".
- Optional thunderstorm-warning flag in the storm file (time it was issued). Used by WATCH and by the S3 rainfall confirmation.

### 4.5 Hydrology: a simple, explainable, reduced-complexity model
This is **not** a full hydraulic model. Say so in the README. It needs to be plausible, conserve mass and be fast.

Each 1-minute tick (use sub-steps inside the tick if needed for stability):
1. **Runoff (MSMA rational method).** For each cell, rainfall excess comes from `Q = C·i·A/360` (Q in m³/s, i in mm/hr, A in ha), giving a volume per minute. `C` comes from land cover: roads/roofs ≈ 0.9, residential ≈ 0.7, open/green ≈ 0.3. Take these from MSMA tables and cite them.
2. **Drain network.** Assign each cell to its nearest **drain node**. Create drain nodes along roads at about 60–100 m spacing, plus explicit culvert/underpass/ramp nodes at low points. Each node has a storage volume and an outflow capacity (m³/s) to the next node downstream, following the DEM toward the outlet. Drain level = stored volume / storage capacity (0–100%). **Drain capacity is the main calibration knob.** Start from an MSMA minor-system design capacity, then scale it with one global factor (residents report undersized drains).
3. **Overflow.** When a node is full, the excess goes to the surface cells in its catchment.
4. **Surface routing.** Use a cellular automaton on the water-surface elevation (ground + depth). Move water to lower neighbours in proportion to the head difference, with a stability limiter. A WCA2D-style or simple diffusive-wave scheme is fine. Water re-enters drains when they have spare capacity.
5. **Outflow boundary.** Water leaves at the lowest edge cells (toward Sungai Puloh). Optional: an upstream inflow boundary for Setia Alam runoff (mark it as an assumption).

**Outputs** cached per storm: `depth[t, r, c]` (float16, m) and `drain_level[t, node]` (0–1), saved to `data/cache/<storm_hash>.npz`.

**Tests:** mass balance (rain in = stored + out ± 1%), no negative depths, a flat-bowl test case that fills its lowest point first, and a speed check (a 6-hour storm on 130×130 runs in under ~30 s).

### 4.6 Agents (Mesa)

**SensorAgent**
- Sits at a drain node, culvert, underpass or ramp.
- Each `report_interval` (1–5 min, configurable) it reads `drain_level` (or road depth for underpass nodes) and adds Gaussian noise (σ from the UTHM/FloodNet accuracy figures, as an assumption).
- Optional failure modes for robustness tests: `p_dropout` per reading, and `p_blocked` (stuck reading).
- Keeps a rolling 10-minute buffer and computes the slope.

**Placement strategies** (`placement.py`), for k ∈ {5, 10, 20, 40}:
- `flow_accumulation`: choose the k drain nodes with the highest upstream area, spread apart by a minimum distance.
- `historical`: nodes nearest the reported flood streets, then fill the rest by flow accumulation.
- `random`: baseline for comparison.

Each street segment is "served" by its nearest 1–2 sensors **upstream or at the same elevation** (network distance, not straight-line).

**AlertSystemAgent** (one per model). It implements a strategy per scenario and keeps a per-street state machine `NONE → WATCH → ACT → AVOID → ALL_CLEAR`, with no flapping (minimum hold time). It sends messages to residents on affected streets only, except in S1.
- **S1 virtual river gauge:** use the depth at the township's main outlet cell as a stand-in for a river station. Alert when it crosses a threshold. Then add the 15-min publication interval (Public InfoBanjir updates every 15 min) plus a dissemination delay (WhatsApp-chain assumption, e.g. 15–45 min), and reach 56% of residents at random (Alias et al., 2020). The message is generic, so residents must find a safe zone themselves.
- **S2:** ACT when the serving sensor is above `fixed_threshold` (sweep 60/70/80%).
- **S3:** ACT when `TTF < 30 min` **and** (a second sensor shows a rising trend **or** rainfall intensity > `rain_confirm_mm_hr`). The message includes the nearest safe car park and the minutes remaining.
- Logs every alert as `(t, street_id, level, n_recipients)`.

**ResidentAgent** (car owner)
- Home = a residential building. Car parked at street level (or in a basement where the building is tagged apartments, as an assumption). Number of cars = residential buildings × `cars_per_household` (an assumption; sample down if needed for speed and scale results back up).
- State depends on time of day: `asleep` (night), `home_awake`, or `away` (cannot move the car). Probabilities by hour are an assumption, swept in sensitivity tests.
- On receiving ACT: with probability `compliance`, after a response delay (lognormal; median ~5 min awake, ~12 min asleep, as an assumption), walk to the car and drive the shortest route to the nearest reachable safe zone.
- **Driving:** follows the road graph at reduced speed (e.g. 20 km/h). An edge with depth ≥ 0.15 m slows the car. An edge with depth ≥ 0.3 m is impassable, so the resident re-routes. If no route exists, the car stays put. Cache shortest paths, and only recompute when an edge on the path becomes blocked.
- **S0 behaviour:** self-notices when water at the home cell is ≥ 0.1 m and the resident is awake, then tries to move (usually too late).
- On reaching a safe zone, presses "I moved my car" with probability `p_button` (an assumption). This gives a "reported" count alongside the true count, which shows the KPI the SDP dashboard would see.
- **Outcome per car:** `moved_safe` | `flooded_parked` | `flooded_en_route` | `never_at_risk`. A car is "at risk" if its parking cell reaches 0.3 m in the S0 run of the same storm.

### 4.7 Metrics (`metrics.py`)
Per run:
- **Lead time** per street that floods (reaches 0.3 m): `t_flood − t_first_ACT`. Report the median, the 10th–90th percentile, and the share of flooded streets with lead time ≥ 15 / ≥ 30 min. Streets that flooded with no ACT count as **missed**.
- **% vehicles moved before flooding** = cars `moved_safe` / cars at risk.
- **RM damage avoided** vs S0, using a depth-damage function per car (e.g. a step or linear curve, capped at an average repair or write-off cost). **🟡 TEAM DECISION / SOURCE:** the per-car cost. Using the DOSM 2021 vehicle loss (RM1.0 bn) divided by a cited count of affected vehicles is one defensible route. Flag it as an estimate.
- **False-alarm rate:** ACT-alerted streets that never reached 0.3 m, divided by all ACT-alerted streets.
- **Alert volume:** messages sent per resident (alert fatigue).

Sweep outputs go to one tidy Parquet table: one row per (run, config).

### 4.8 Validation (`docs/VALIDATION.md`)
- Run the real Dec 2021 storm (or the closest available real storm). List the streets the model floods.
- Compare them with streets named in the cited news reports (Jalan Makyong and others the team supplies). Report the hit rate honestly.
- Run a sensitivity check on drain-capacity factor, runoff C and road lowering: do the conclusions (S3 > S2 > S1 > S0) hold?
- If the model does not flood Jalan Makyong, say so and show the team. Do not tune silently until it does. Calibration choices go in VALIDATION.md.

---

## 5. Dashboard (deliverable B), alert mock-up (C) and figures (D)

### 5.1 Replay export (`export/replay.py`)
For one chosen run, write to `dashboard/public/runs/<run_id>/`:
- `meta.json`: scenario, storm, sensors, compliance, seed, start time, CRS, bounds, and a `synthetic: true/false` flag for the storm.
- `streets.geojson`, `buildings.geojson`, `safe_zones.geojson`, `sensors.geojson`, `drains.geojson` (EPSG:4326).
- `depth.bin`: depth per frame quantised to uint8 centimetres (0–255 cm), frames every 1 min, gzip. Alternatively one PNG per frame. Pick whichever deck.gl `BitmapLayer` handles more simply.
- `timeline.json`: per minute: rainfall, sensor readings and TTF, street alert states, KPI counters.
- `cars.json`: per car: home, outcome, and a path as `[[lon, lat, t], ...]` for deck.gl `TripsLayer`.
- `events.json`: alert messages sent (for the phone mock-up and an event feed).

Export **S0 and S3 for the same storm and seed**, so the dashboard can show them side by side.

### 5.2 `index.html`: map replay
- A base layer drawn from our own GeoJSON (roads, buildings) on a neutral background, so no internet is needed. A switch adds an online basemap when available (OpenFreeMap / CARTO, no API key).
- **Water layer:** a blue depth ramp; the 0.15 m and 0.3 m contours are visibly distinct.
- **Streets** coloured by alert level (WATCH yellow, ACT orange, AVOID red, ALL CLEAR green).
- **Sensors** as dots, filled by drain %. Click one for a sparkline of level and TTF.
- **Cars** as animated dots (TripsLayer) coloured by outcome.
- **Controls:** play/pause, speed (1×–60×), time scrubber, scenario switch, and a **split-screen S0 vs S3** toggle.
- **KPI panel (live as it plays):** minutes into storm, rainfall now, streets on ACT, median lead time so far, cars moved / at risk, "I moved my car" presses, RM avoided.
- An event feed of alerts as they fire.
- If the storm is synthetic, show a clear "Synthetic design storm" badge.

### 5.3 `alert.html`: resident alert mock-up
- Phone frame with a Telegram-style bot chat for one resident on Jalan Makyong (or the team's chosen street). Messages appear at their simulation time: WATCH → ACT (with a **live countdown** and the safe car park name) → AVOID → ALL CLEAR.
- A working **"I moved my car"** button increments a counter, shared with the dashboard via `localStorage` or `BroadcastChannel` when both pages are open. The judges can press it.
- Bilingual toggle: Bahasa Melayu / English. Get the BM wording checked by a teammate.
- It can run synced to the map replay (same clock) or standalone.

### 5.4 `results.html` + `figures.py` (deck-ready)
1. Lead-time distribution by scenario (box/violin).
2. % vehicles moved vs number of sensors (5/10/20/40), one line per scenario.
3. % vehicles moved vs compliance (30/50/80%), S1 vs S3.
4. RM damage avoided per storm, with Monte Carlo 90% interval.
5. False-alarm rate: S2 vs S3 (shows why the 2-source confirmation matters).
6. Cost-benefit: pilot cost (< RM10k for 20 nodes, from our proposal) vs RM avoided per storm.

Export PNG (for slides) and SVG. Use one consistent palette and large fonts readable on a projector.

### 5.5 Optional stretch: live Telegram bot
`scripts/telegram_replay.py` replays `events.json` to a real Telegram chat (bot token in `.env`, never committed). Judges scan a QR code, join, and get the ACT alert on their own phones during the demo. Only build this after everything else is done.

---

## 6. Phases (each ends in something demo-able)

| Phase | Goal | Done when |
|---|---|---|
| **0. Scaffold** | Repo, `pyproject`, Makefile, config models, CI-free `pytest` run, README skeleton | `make test` passes on an empty test |
| **1. Core formulas** | `runoff.py`, TTF predictor, alert state machine, metrics functions, all with unit tests | Tests cover units (Q formula), the TTF edge cases (rate ≤ 0 → no TTF), no state flapping, and lead time/missed counting |
| **2. Toy world end to end** | Synthetic 50×50 bowl terrain, fake grid road graph, synthetic storm → cached water → sensors → S0–S3 → residents → metrics → replay export → bare dashboard showing water and cars | Running `make sim` on the toy world produces a replay that plays in the browser; S3 lead time > S2 > S1 in the toy world |
| **3. Real BBR data** | DEM fetch and cleanup, OSM fetch, street↔cell linking, safe zones, drain nodes, plotted for a sanity check | `make data` is reproducible; a PNG overlay of DEM + roads + safe zones + drain nodes is shown to the team for a visual check |
| **4. Real storm + calibration** | Load the team's rainfall source; run the hydrology; validation report | `VALIDATION.md` lists modelled vs reported flood streets with an honest hit rate |
| **5. Monte Carlo sweeps** | `sweep.py` with joblib; full grid; Parquet results | Full default sweep runs in < ~30 min on a laptop (reduce N if needed); summary table printed |
| **6. Dashboard + alert mock-up** | Full §5.2 and §5.3 features, split view, KPIs, bilingual phone mock-up | Opens from `dashboard/dist/` with no server and no internet; deployed to GitHub Pages |
| **7. Figures, docs, polish** | `figures.py`, `results.html`, `ASSUMPTIONS.md` auto-generated, README with screenshots, `DEMO_SCRIPT.md` | A teammate who has never run it can follow the README from clone to dashboard |
| **8. Stretch** | Telegram replay bot; sensor-failure robustness runs; placement strategy comparison | Optional |

If time is short, the **minimum viable demo** is Phases 0–3 plus a design storm, then Phase 6 with S0 vs S3 only, then the two headline figures. Monte Carlo with N = 30 is acceptable.

---

## 7. Configuration sketch (`config/base.yaml`)

```yaml
sim:
  tick_minutes: 1
  duration_minutes: 480
  storm_start_local: "2021-12-17T18:00:00+08:00"   # sets residents' asleep/away mix
grid:
  cell_m: 30
  crs: "EPSG:3168"
hydro:
  runoff_C: {road: 0.90, roof: 0.90, residential: 0.70, green: 0.30}
  runoff_C_source: "MSMA 2nd ed. (DID, 2012), Table X — fill in"
  drain_node_spacing_m: 80
  drain_capacity_factor: 1.0        # calibration knob
  road_burn_m: 0.15                 # assumption: true
thresholds:
  car_float_m: 0.30                 # source: NWS (n.d.)
  avoid_m: 0.15                     # source: proposal, half of car_float
  watch_drain_pct: 0.50
  act_ttf_min: 30
  rate_window_min: 10
  all_clear_falling_min: 30
sensors:
  report_interval_min: 2
  noise_sigma_m: 0.01               # assumption — cite UTHM / FloodNet accuracy
  p_dropout: 0.0
residents:
  cars_per_household: 1.5           # assumption: true — replace with cited figure
  response_delay_lognorm: {awake_median_min: 5, asleep_median_min: 12, sigma: 0.6}
  drive_speed_kmh: 20
  p_button: 0.7                     # assumption: true
  self_notice_depth_m: 0.10
scenario_s1:
  publish_interval_min: 15          # source: Malay Mail (2025)
  dissemination_delay_min: [15, 45] # assumption: true
  reach: 0.56                       # source: Alias et al. (2020)
damage:
  per_car_rm: null                  # TEAM DECISION — must be sourced
```

Every key gets a `source` or `assumption` entry. Fail loudly at startup if a required source is `null`, with an opt-in `--allow-placeholders` flag that also stamps "PLACEHOLDER VALUES" on every figure.

---

## 8. Demo script (write the final version into `docs/DEMO_SCRIPT.md`)

A 3-minute live demo:
1. **0:00** Open the dashboard on the BBR map. "This is Bandar Bukit Raja. It's 6 pm on 17 December 2021, and the rain is starting."
2. **0:20** Play at 30×. Drains fill; sensors turn from green to orange; Jalan Makyong goes to **WATCH**.
3. **0:50** S3 fires **ACT** for Jalan Makyong. Switch to the phone: *"Move your car to [car park] now. About 24 minutes until flooding."* A judge presses **"I moved my car"**, and the dashboard counter ticks up.
4. **1:20** Cars stream to safe zones. The street hits 0.3 m. KPI: "Lead time 24 min."
5. **1:50** Split screen S0 vs S3 at the same moment: in S0, cars are under water. Show the % moved and RM avoided.
6. **2:20** Results page: lead time by scenario; % moved vs number of sensors (the "how many sensors does BBR need" answer); cost < RM10k vs RM avoided.
7. **2:50** Close: "Structural works take years. A message takes seconds."

---

## 9. Open decisions for the team (🟡)

Claude Code: collect these in `docs/OPEN_QUESTIONS.md` and ask about them when you reach them. Do not guess them silently.

1. **Study-area bbox:** confirm after the Phase 3 overlay.
2. **Rainfall source:** JPS/MetMalaysia records, GPM IMERG (needs an Earthdata login), or published figures. Which real storm(s): Dec 2021, Apr 2024, others?
3. **MSMA IDF coefficients** for the Klang station (for design storms) and runoff C table values.
4. **Named safe car parks** in BBR.
5. **Per-car damage cost** and its source.
6. **Cars per household** and its source (e.g. DOSM household survey).
7. **Validation streets:** list of street names reported flooded, with citations.
8. **Hackathon deadline**, so the phases can be cut to fit.

---

## 10. Honesty checklist before submission
- [ ] README states clearly: reduced-complexity water model; results are simulation estimates until a real pilot.
- [ ] Every figure that uses a synthetic storm or placeholder value is labelled as such.
- [ ] `ASSUMPTIONS.md` is complete and matches `config/`.
- [ ] `VALIDATION.md` reports misses as well as hits.
- [ ] The dashboard and alert mock-up say "advisory layer: complements JPS/NADMA warnings; opt-in only".
- [ ] No API keys or tokens in the repo.
