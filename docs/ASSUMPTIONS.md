# Assumptions and sources

_Auto-generated from `config/base.yaml` by `python -m ffsa.cli assumptions`. Do not edit by hand._

18 parameters cite a source, 45 are explicit assumptions, 1 placeholder(s) must be sourced before final results.

## ⚠ Placeholders (must be sourced)

| Parameter | Value | Note |
|---|---|---|
| `damage.per_car_rm` | `20000` | PLACEHOLDER. Must be sourced, e.g. DOSM 2021 vehicle loss RM1.0 bn / cited count of affected vehicles (OPEN_QUESTIONS #5) |

## Sourced parameters

| Parameter | Value | Source |
|---|---|---|
| `sim.storm_start_local` | `2021-12-17T18:00:00+08:00` | Start of the 17-18 Dec 2021 Klang Valley storm (proposal); sets the asleep/away mix |
| `grid.cell_m` | `30` | Copernicus GLO-30 DEM native resolution (ESA, 2021) |
| `hydro.runoff_C.road` | `0.9` | MSMA 2nd ed. (DID, 2012) runoff coefficient table: impervious surfaces 0.90 (table number to be filled in by team) |
| `hydro.runoff_C.roof` | `0.9` | MSMA 2nd ed. (DID, 2012): roofs 0.90 (table number to be filled in by team) |
| `hydro.runoff_C.residential` | `0.7` | MSMA 2nd ed. (DID, 2012): residential, medium density ~0.70 (table number to be filled in by team) |
| `hydro.runoff_C.green` | `0.3` | MSMA 2nd ed. (DID, 2012): open space / grass ~0.30 (table number to be filled in by team) |
| `thresholds.car_float_m` | `0.3` | US National Weather Service, 'Turn Around Don't Drown' (n.d.): 30 cm of moving water floats most cars |
| `thresholds.avoid_m` | `0.15` | Proposal: half of car_float_m; NWS 15 cm causes loss of control |
| `thresholds.watch_drain_frac` | `0.5` | Proposal alert table: WATCH when drain > 50% full and rising |
| `thresholds.act_ttf_min` | `30` | Proposal alert table: ACT when predicted TTF < 30 min |
| `thresholds.rate_window_min` | `10` | Plan §0: least-squares slope over the last 10 minutes |
| `thresholds.all_clear_falling_min` | `30` | Proposal alert table: ALL CLEAR after 30 min of falling water |
| `thresholds.s2_fixed_threshold` | `0.7` | Plan §4.6 sweep values 60/70/80%; 70% default |
| `sensors.n_sensors` | `20` | Proposal pilot: 20 nodes for < RM10k |
| `residents.compliance` | `0.5` | Plan sweep values {0.3, 0.5, 0.8}; 0.5 default |
| `scenario_s1.publish_interval_min` | `15` | Public InfoBanjir updates every 15 min (Malay Mail, 2025) |
| `scenario_s1.reach` | `0.56` | Alias et al. (2020): 56% of residents received flood warnings |
| `damage.pilot_cost_rm` | `10000` | Proposal: < RM10k for a 20-node pilot |

## Assumptions

| Parameter | Value | Reason |
|---|---|---|
| `sim.tick_minutes` | `1` | Model resolution; 1-minute ticks resolve 10-min rate-of-rise fits |
| `sim.duration_minutes` | `480` | 8 h covers a flash-flood storm plus recession |
| `sim.substeps_per_tick` | `6` | 10-s hydraulic sub-steps keep the 30 m surface scheme stable |
| `grid.crs` | `EPSG:3168` | Kertau RSO (metres), national projected CRS for Peninsular Malaysia; used everywhere except dashboard export (EPSG:4326) |
| `hydro.manning_n` | `0.035` | Mixed urban surface roughness for overland flow; typical textbook range 0.02-0.05 |
| `hydro.drain_node_spacing_m` | `80` | Plan §4.5 suggests 60-100 m manhole/inlet spacing |
| `hydro.drain_design_intensity_mm_hr` | `100` | Minor-system design intensity stand-in until MSMA IDF for Klang is supplied (OPEN_QUESTIONS #3) |
| `hydro.drain_capacity_factor` | `0.6` | Main calibration knob; <1 reflects resident reports of undersized/clogged drains |
| `hydro.drain_storage_seconds` | `240` | Pipe/channel storage expressed as seconds of design flow between nodes |
| `hydro.drain_depth_m` | `1.0` | Typical roadside monsoon drain depth; converts fill % to a water level in metres |
| `hydro.inlet_capacity_factor` | `1.5` | Inlets can admit up to 1.5x pipe design flow when there is spare storage |
| `hydro.road_burn_m` | `0.15` | Road cells lowered so overland flow follows streets (plan §4.2, 0.1-0.2 m) |
| `hydro.outlet_edge` | `south` | Toy world drains to the south edge; BBR outlet set in area_bbr.yaml |
| `thresholds.watch_rate_m_per_min` | `0.01` | 'Rising fast' = > 1 cm/min sustained over the fit window |
| `thresholds.min_hold_min` | `10` | Minimum time a street stays at a level before de-escalating (anti-flapping) |
| `thresholds.heavy_rain_mm_hr` | `50` | Above this intensity the TTF rate is multiplied (rain still to arrive in the drain) |
| `thresholds.heavy_rain_rate_multiplier` | `1.25` | Simple, explainable boost to rate-of-rise under heavy rain |
| `thresholds.rain_confirm_mm_hr` | `40` | S3 second-source confirmation by rainfall; MetMalaysia 'heavy rain' is > 30 mm/h |
| `thresholds.rising_confirm_m_per_min` | `0.003` | A confirming sensor counts as rising above 3 mm/min |
| `sensors.report_interval_min` | `2` | Within the 1-5 min LoRaWAN reporting range in plan §4.6 |
| `sensors.noise_sigma_m` | `0.01` | Ultrasonic level-sensor accuracy ~1 cm; to be cited from UTHM / FloodNet specs |
| `sensors.p_dropout` | `0.0` | No packet loss in the baseline; varied in robustness runs |
| `sensors.p_blocked` | `0.0` | No stuck sensors in the baseline; varied in robustness runs |
| `sensors.placement` | `low_points` | Team decision 2026-10-23: drains at terrain low points (sags, dips, underpasses), where street water collects first; trunk drains (flow_accumulation) never filled on the real BBR map. Compared with flow_accumulation/historical/random in Phase 8 |
| `sensors.low_point_window_m` | `300` | Neighbourhood used to judge a low point: node ground level vs the mean ground level within a ~300 m square |
| `sensors.min_spacing_m` | `150` | Spread sensors apart when choosing by flow accumulation |
| `sensors.max_serve_distance_m` | `600` | A sensor only serves streets within 600 m road distance; farther streets are unserved |
| `sensors.same_elevation_tol_m` | `0.5` | Serving sensors must be upstream or within 0.5 m of the street's lowest point |
| `residents.cars_per_household` | `1.5` | Placeholder until a DOSM household figure is supplied (OPEN_QUESTIONS #6) |
| `residents.park_at` | `street` | BBR terraced houses park on the porch / kerb at road level, so a car's water depth is the road cell in front of the house ('building' = the house's own cell) |
| `residents.households_per_apartment` | `10` | OSM apartment blocks rarely carry unit counts; 10 households per block as a stand-in |
| `residents.max_cars` | `3000` | Cap on simulated cars for speed; results are shares so they scale |
| `residents.response_delay_lognorm.awake_median_min` | `5` | Median time to get keys and reach the car when awake |
| `residents.response_delay_lognorm.asleep_median_min` | `12` | Median time when woken by a phone alert |
| `residents.response_delay_lognorm.sigma` | `0.6` | Lognormal spread of response delays |
| `residents.s1_search_delay_min` | `10` | Extra time to decide where to go when the message names no car park (S1) |
| `residents.drive_speed_kmh` | `20` | Cautious driving in heavy rain on residential streets |
| `residents.slow_speed_kmh` | `5` | Speed on edges with >= avoid_m of water |
| `residents.p_button` | `0.7` | Share of movers who press 'I moved my car' |
| `residents.self_notice_depth_m` | `0.1` | S0: residents notice water at their door at 10 cm |
| `residents.p_asleep_by_hour` | [0.9, 0.92, 0.93, 0.93, … (24 values)] | Typical sleep schedule; swept in sensitivity tests |
| `residents.p_away_by_hour` | [0.03, 0.03, 0.03, 0.03, … (24 values)] | Share away from home (at work, out) by hour; cannot move their car |
| `scenario_s1.gauge_threshold_frac` | `0.75` | Virtual river gauge = fill of the township's outlet drain node (all upstream area); 75% stands in for InfoBanjir's 'Warning' level |
| `scenario_s1.dissemination_delay_min` | `[15, 45]` | WhatsApp-chain forwarding delay, uniform range |
| `damage.partial_damage_depth_m` | `0.3` | Step depth-damage curve: no damage below car_float_m, full per-car cost at/above it |

## Modelling choices (code)

| Choice | Description |
|---|---|
| Building footprints in the DEM | OSM footprint cells are replaced by the median of non-building cells in a 7x7 window (Copernicus is a surface model). |
| Road burning | Road cells are lowered by `hydro.road_burn_m` so overland flow follows streets. |
| Pit filling | Only single-cell pits are filled; larger depressions are kept because that is where floods happen. |
| Drain network geometry | Drain nodes along roads every `hydro.drain_node_spacing_m`; each drains to the nearest strictly lower node; culvert nodes at road low points. |
| Drain capacity | MSMA-style design flow C*i*A/360 for each node's upstream area at `hydro.drain_design_intensity_mm_hr`, scaled by `hydro.drain_capacity_factor`. |
| Surface routing | Manning-based diffusive cellular scheme with stability limiters; not a full hydraulic model. |
| Street flooded | A street counts as flooded when any of its cells reaches `thresholds.car_float_m`. |
| Car at risk | A car is at risk if its parking cell reaches `thresholds.car_float_m` at any time in the storm (water is independent of behaviour, so this equals the S0 definition). |
| S1 lead time | A street's S1 ACT time is the publication time plus one dissemination delay sampled per street. |

## Storms

| Storm | Synthetic | Source |
|---|---|---|
| `design_storm_PLACEHOLDER` | yes | PLACEHOLDER IDF coefficients (assumption) — replace with MSMA 2nd ed. values for the nearest Klang station |
| `toy_storm` | yes | Synthetic toy hyetograph for pipeline testing (assumption: true) |

## Study area

- bbox: `[101.4093, 3.0732, 101.4714, 3.1143]` — OSM Nominatim boundary for Bandar Bukit Raja + ~300 m margin (proposal, awaiting team confirmation) (**not yet confirmed**)
- DEM: Copernicus GLO-30 DEM (ESA / Airbus, 2021), open AWS bucket, no login
- Roads, buildings, land use, car parks: OpenStreetMap contributors (ODbL)
- Outlet: boundary cells in the lowest 10% of boundary elevation (assumption)
- **Synthetic safe car parks** (assumption, no real list yet): highest road node per 1500 m tile, labelled 'Assumed car park N (synthetic)'
- Validation street: Jalan Makyong — News reports cited in the proposal: floods ~3 times a year since 2021 (citation to be added by team)
- **Current BBR build has no OSM landuse, parking** (Overpass unreachable): land cover defaults to residential (C=0.7)
