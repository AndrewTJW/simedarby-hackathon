# Open questions for the team (🟡)

Each one blocks or weakens a specific part of the build. Answer in this file (or in the linked
config) and note who decided and when.

| # | Question | Where it goes | Blocks | Status |
|---|---|---|---|---|
| 1 | **Study-area bbox.** Proposed: OSM boundary of Bandar Bukit Raja + ~300 m margin = `[101.4093, 3.0732, 101.4714, 3.1143]`. Check `results/phase3_overlay.png`. Does it cover Jalan Makyong and the other reported flood streets? | `config/area_bbr.yaml` → `bbox`, set `bbox_confirmed: true` | Phase 3 sign-off | **open** |
| 2 | **Rainfall source.** JPS/MetMalaysia records, GPM IMERG (needs a NASA Earthdata login), or published figures? Which storm(s): Dec 2021, Apr 2024, others? | `config/storms/<name>.yaml` (+ CSV), with `source:` and `synthetic: false` | Phase 4 | **decided 2026-10-23: use the synthetic design storm for now** (no real record); every output is stamped synthetic and `VALIDATION.md` cannot claim a real-storm hit rate. Swap in a real record if one turns up |
| 3 | **MSMA IDF coefficients** (λ, κ, θ, η) for the nearest Klang station, and the runoff-C table numbers in MSMA 2nd ed. | `config/storms/design_storm_PLACEHOLDER.yaml` (rename), `config/base.yaml` → `hydro.runoff_C` sources | design-storm runs; drain design intensity | open |
| 4 | **Named safe car parks** in BBR (SDP / mall multi-storey car parks), with lon/lat. | `config/area_bbr.yaml` → `safe_car_parks` | convincing ACT message text | open |
| 5 | **Per-car damage cost** (RM) and its source, e.g. DOSM 2021 vehicle loss RM1.0 bn ÷ a cited count of affected vehicles. | `config/base.yaml` → `damage.per_car_rm` (remove `placeholder: true`) | RM avoided; runs need `--allow-placeholders` until then | open |
| 6 | **Cars per household** and its source (e.g. DOSM household survey). | `config/base.yaml` → `residents.cars_per_household` | number of cars | open |
| 7 | **Validation streets:** list of streets reported flooded, with citations (news reports). | `config/area_bbr.yaml` → `validation_streets` | Phase 4 `VALIDATION.md` | open |
| 8 | **Hackathon deadline**, so phases can be cut to fit (minimum viable demo = Phases 0–3 + design storm, Phase 6 with S0 vs S3, two headline figures). | — | planning | open |

## Also for a teammate to check

- **Bahasa Melayu wording** of the alert messages in `src/ffsa/abm/alert.py` (`TEXT`) and the phone mock-up buttons in `dashboard/src/alert.js`.
- **Sensor noise σ** (`sensors.noise_sigma_m`): cite UTHM / FloodNet ultrasonic sensor accuracy.

## Findings to discuss (from the toy world, Phase 2)

- **False alarms are high (~80%) in both S2 and S3** on the toy world: drain sensors fill on most served
  streets during a heavy storm, but only a few streets reach 0.3 m. The 2-source confirmation does not
  separate them much, because heavy rain alone satisfies it. This may change with real terrain; if it
  does not, options include a higher `rain_confirm_mm_hr`, requiring the second sensor (not rain), or a
  street-specific critical level. We have not tuned this, so as not to tune toward a desired result.
- **S1 (river-style) alerts arrive after streets flood** in the toy world (median lead −54 min),
  because the outlet "gauge" integrates the whole township and peaks late, then the 15-min publish
  cycle and WhatsApp forwarding add 30–60 min.
