# Flash-Flood Street Alerts (prototype)

Sime Darby Property University Hackathon 2026 — Planet track, Climate Resilience.
Pilot township: Bandar Bukit Raja (BBR), Klang. See [PLAN.md](PLAN.md) for the full build plan.

> **Honesty note.** The water model is a *reduced-complexity* model (rational-method runoff, a
> drain-node network and a cellular surface-flow scheme). It is not a full hydraulic model. All
> results are simulation estimates until a real sensor pilot exists.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev,geo]"     # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m pytest -q
```

Every Makefile target is also available as `python -m ffsa.cli <target>` (for Windows without `make`).

## Status

| Phase | State |
|---|---|
| 0. Scaffold | done |
| 1. Core formulas | done |
| 2. Toy world end to end | done |
| 3. Real BBR data | done (built without OSM land use / car parks, Overpass was down); bbox still to be confirmed by the team |
| 4. Real storm + calibration | runs on a **synthetic** design storm (team decision); `docs/VALIDATION.md` reports 0/20 Jalan Makyong hits |
| 5. Monte Carlo sweeps | code done; toy world swept; BBR sweep skipped for now (`config/sweeps/bbr.yaml`) |
| 6. Dashboard + alert mock-up | map replay, split S0/S3, KPIs, phone mock-up done; GitHub Pages deploy pending |
| 7. Figures, docs | figures (toy), auto `ASSUMPTIONS.md`, `VALIDATION.md`, `DEMO_SCRIPT.md` done; README screenshots pending |

## Commands

| Make target | Without make | What it does |
|---|---|---|
| `make test` | `python -m pytest -q` | unit + end-to-end tests |
| `make sim` | `python -m ffsa.cli --allow-placeholders sim [--world bbr --storm <name>]` | S0-S3 once, prints metrics, exports a dashboard replay |
| `make sweep` | `python -m ffsa.cli --allow-placeholders sweep [-n 30]` | Monte Carlo grid → `results/sweep_*.parquet`, `results/summary_*.csv` |
| `make figures` | `python -m ffsa.cli figures` | deck figures → `results/figures/` and `dashboard/results.html` |
| `make data` | `python -m ffsa.cli data [--skip-optional-osm]` | fetch DEM + OSM for BBR, build `data/processed/world_bbr.pkl`, write `results/phase3_overlay.png`; `--skip-optional-osm` skips land use and car parks when Overpass is down |
| | `python -m ffsa.cli validate` | `docs/VALIDATION.md`: modelled vs reported flood streets |
| `make assumptions` | `python -m ffsa.cli assumptions` | regenerate `docs/ASSUMPTIONS.md` from `config/` |

(On Windows use `.venv/Scripts/python`; on macOS/Linux `.venv/bin/python`.)

## How the model works (one paragraph each)

**Water (deterministic, cached per storm).** Rainfall excess per 30 m cell from the MSMA rational
method (`Q = C·i·A/360`) enters a drain-node network built along roads; nodes drain to the nearest
lower node and have a capacity scaled by one calibration factor. When drains are full, water stays
on the surface and is routed cell to cell by a Manning-based diffusive scheme; it leaves at the
lowest boundary cells. Mass balance is tracked and tested. The result `depth[t, r, c]` and
`drain_level[t, node]` is cached in `data/cache/`.

**People and alerts (stochastic, Mesa 3 agents).** Sensors read drain level (or road water once the
drain surcharges) with noise. The alert system runs S0-S3 and a per-street state machine
(WATCH → ACT → AVOID → ALL CLEAR, no flapping). Residents (one agent per car) are asleep, home or
away depending on the hour; on ACT they comply with some probability after a lognormal delay and
drive to the nearest reachable safe car park, re-routing around roads with ≥ 0.3 m of water.

**Never fabricated.** Every parameter in `config/base.yaml` carries a `source` or an `assumption`;
placeholders stop the run unless `--allow-placeholders` is passed, and every figure and the
dashboard are stamped when synthetic data or placeholders are used.

## Real BBR demo

```bash
.venv/Scripts/python -m ffsa.cli data --skip-optional-osm            # build the BBR map (~1 min)
.venv/Scripts/python -m ffsa.cli --allow-placeholders sim --world bbr  # S0-S3 on BBR, synthetic storm
```

Open `dashboard/index.html` and pick the `bbr` run. See `docs/DEMO_SCRIPT.md` for the 3-minute walkthrough.
Inputs that are made up are labelled: the storm is synthetic, safe car parks are "Assumed car park N
(synthetic)", and placeholder values are listed in `docs/ASSUMPTIONS.md`.

## Toy world (Phase 2)

```bash
.venv/Scripts/python -m ffsa.cli --allow-placeholders sim        # S0-S3 on the synthetic toy world
```

Then open `dashboard/index.html` directly in Chrome/Edge (no server, no internet needed).
`dashboard/alert.html` is the phone mock-up; open both and they stay in sync, and "I moved my car"
presses show up on the map page. `dashboard/results.html` shows the Monte Carlo figures.
