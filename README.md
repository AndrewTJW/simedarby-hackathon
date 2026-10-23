# Flash-Flood Street Alerts (prototype)

Sime Darby Property University Hackathon 2026 — Planet track, Climate Resilience.
Pilot township: **Bandar Bukit Raja (BBR), Klang**.

Low-cost water-level sensors in drains predict when each street will flood, and residents on that
street get a message such as *"Move your car to Car Park X now. About 20 minutes until flooding."*
with an **"I moved my car"** button. This repo is an agent-based simulation of that system on the
real BBR map, plus a browser dashboard that replays it.

> **Honesty note.** The water model is a *reduced-complexity* model, not a full hydraulic model.
> The map, roads, buildings and terrain are real; the storm is **synthetic** and some inputs are
> placeholders (all listed in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md)). Results are simulation
> estimates until a real sensor pilot exists.

---

## 1. Just show the demo (no setup needed)

The simulation results are already in the repo, so the dashboard works straight after cloning,
with **no Python, no server and no internet**.

1. Open **`dashboard/index.html`** in Chrome or Edge (double-click it). This is the map.
2. Open **`dashboard/alert.html`** in a second window. This is the resident's phone.
3. On the map page, pick the run **`bbr / design_storm_PLACEHOLDER / seed 1`** and press **Play**.

What you will see:
- water rising on the BBR streets, minute by minute (1 tick = 1 minute);
- sensors changing colour as drains fill;
- streets switching through **WATCH → ACT → AVOID → ALL CLEAR**;
- cars driving to safe zones (green crosses) after an ACT alert;
- a split view comparing **S0 (no alerts)** with **S3 (our system)** at the same moment.

Press **"I moved my car"** on the phone and the counter on the map goes up (both windows stay in sync).

For the 3-minute pitch walkthrough and answers to likely judge questions, see
[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

> Don't show `dashboard/results.html` for BBR yet: it still has charts from the synthetic toy
> world (see section 5).

---

## 2. Set up Python (only to re-run the simulation)

You need **Python 3.11 or newer**. Run these once, from the project folder.

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,geo]"
.venv\Scripts\python -m pytest -q        # should end with "30 passed"
```

**macOS / Linux:** the same, with `.venv/bin/python` instead of `.venv\Scripts\python`.

All commands below use the Windows form. If you have `make`, the `Makefile` has short versions
(`make test`, `make sim`, ...).

---

## 3. Run the simulation on the real BBR map

**Step 1: build the BBR map** (once, about 1 minute; needs internet):
```powershell
.venv\Scripts\python -m ffsa.cli data --skip-optional-osm
```
This downloads the terrain (Copernicus 30 m) and the roads and buildings (OpenStreetMap), then builds
the drains, safe zones and street links. It writes a check image to `results/phase3_overlay.png`.
`--skip-optional-osm` skips land use and car parks, because the public OpenStreetMap servers often
time out on those; drop the flag to try fetching them.

**Step 2: run the four scenarios**:
```powershell
.venv\Scripts\python -m ffsa.cli --allow-placeholders sim --world bbr
```
This runs S0–S3 once (about 1–2 minutes), prints a results table and exports a new replay to
`dashboard/public/runs/`. Reload `dashboard/index.html` to see it.

`--allow-placeholders` is required while some inputs (e.g. the cost of a flooded car) are still
placeholders; outputs are then stamped "PLACEHOLDER VALUES".

Useful options for `sim`:

| Option | Example | Effect |
|---|---|---|
| `--seed` | `--seed 7` | a different random draw of residents and sensor noise |
| `--sensors` | `--sensors 40` | number of street sensors (default 20) |
| `--compliance` | `--compliance 0.8` | share of residents who act on an ACT alert (default 0.5) |
| `--scenarios` | `--scenarios S0,S3` | run only some scenarios |
| `--storm` | `--storm toy_storm` | storm file from `config/storms/` |

### Reading the results table

| Column | Meaning |
|---|---|
| `n_streets_flooded` | streets that reach 0.3 m of water |
| `n_streets_missed` | flooded streets that got no ACT alert before flooding |
| `lead_median_min` | median minutes between the ACT alert and the street reaching 0.3 m (**judged number 1**) |
| `pct_moved` | share of at-risk cars that reached safety before their spot flooded (**judged number 2**) |
| `false_alarm_rate` | share of ACT-alerted streets that never flooded |
| `rm_avoided_vs_no_action` | car damage avoided, in RM (uses a placeholder cost per car) |

### The four scenarios

| ID | Name | Rule |
|---|---|---|
| S0 | No alerts | Residents only react when water reaches their door |
| S1 | River-style alert | One township-wide broadcast from a "river gauge", with publishing and WhatsApp delays |
| S2 | Street sensors, fixed threshold | ACT when a street's sensor is more than 70% full |
| S3 | Street sensors + rate of rise | ACT when the predicted time to flood is under 30 min, confirmed by a second source |

---

## 4. Toy world (quick test, no internet)

A synthetic 50×50 test town that runs in about a second:
```powershell
.venv\Scripts\python -m ffsa.cli --allow-placeholders sim
```
Then pick the `toy` run in `dashboard/index.html`.

---

## 5. Optional: Monte Carlo sweep and charts

The sweep repeats each scenario many times with different random seeds, for averaged charts.
It is **not needed for the demo** and it keeps the CPU busy, so use few workers (`--jobs 2`) and
fewer runs (`-n 30`):
```powershell
.venv\Scripts\python -m ffsa.cli --allow-placeholders sweep --world bbr --config config/sweeps/bbr.yaml -n 30 --jobs 2
.venv\Scripts\python -m ffsa.cli figures
```
The second command redraws the charts in `results/figures/` and `dashboard/results.html`.

---

## 6. Other commands

| Command | What it does |
|---|---|
| `.venv\Scripts\python -m pytest -q` | run the tests |
| `.venv\Scripts\python -m ffsa.cli validate` | write `docs/VALIDATION.md` (modelled vs reported flood streets) |
| `.venv\Scripts\python -m ffsa.cli assumptions` | regenerate `docs/ASSUMPTIONS.md` from `config/` |

---

## 7. What is real and what is made up

| Input | Status |
|---|---|
| Terrain | **Real**: Copernicus GLO-30 DEM |
| Roads, ~3,100 homes | **Real**: OpenStreetMap |
| Storm | **Synthetic** 3-hour, 139 mm design storm (no real rainfall record yet) |
| Safe car parks | **Synthetic**: "Assumed car park N", placed at local high ground |
| Land use | Not fetched; all ground treated as residential |
| Cost per car, cars per household | **Placeholders** |
| Everything else | Each value in `config/` has a source or a stated assumption ([docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md)) |

Validation against reported floods: under the synthetic storm, **0 of 20 Jalan Makyong sections**
reach 0.3 m ([docs/VALIDATION.md](docs/VALIDATION.md)). Open items for the team are in
[docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md).

---

## 8. How the model works

**Water (computed once per storm, then cached).** Rain on each 30 m cell runs off using the MSMA
rational method (`Q = C·i·A/360`) into a network of drain points along the roads. When a drain is
full, the water stays on the surface and flows downhill cell to cell, leaving the map at the lowest
edge. The result, water depth per cell per minute, is cached in `data/cache/`.

**People and alerts (random each run, Mesa 3 agents).** Sensors sit in drains at terrain low points
and read the water level with noise. The alert system decides per street (WATCH → ACT → AVOID →
ALL CLEAR). Each car belongs to a resident who is asleep, at home or away depending on the hour. On
an ACT alert, a resident acts with some probability after a short delay and drives to the nearest
safe zone. Alerted drivers avoid roads with 15 cm or more of water; everyone avoids 30 cm.

## 9. Project layout

```
config/         all parameters (base.yaml), study area (area_bbr.yaml), storms, sweep grids
src/ffsa/       the model: data/ (map building), hydro/ (water), abm/ (sensors, alerts, residents)
dashboard/      static web dashboard (index.html map, alert.html phone, results.html charts)
docs/           ASSUMPTIONS, VALIDATION, DEMO_SCRIPT, OPEN_QUESTIONS
tests/          pytest suite
PLAN.md         the full build plan
```
