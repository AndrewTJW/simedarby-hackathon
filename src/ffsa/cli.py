"""Command line: python -m ffsa.cli <command>. Mirrors the Makefile targets."""
from __future__ import annotations

import argparse
import json
import sys
import time

import pandas as pd

from ffsa.config import ROOT, load_config

DEFAULT_STORM = {"toy": "toy_storm"}


def _cfg(args, overrides=None):
    return load_config(overrides=overrides, allow_placeholders=args.allow_placeholders)


def cmd_sim(args):
    """Run S0-S3 for one storm and seed, print the headline metrics, export the replay."""
    from ffsa.experiments.run_one import prepare, run_one
    from ffsa.export.replay import export_runs

    overrides = {"sensors.n_sensors": args.sensors, "residents.compliance": args.compliance}
    cfg, prov = _cfg(args, {k: v for k, v in overrides.items() if v is not None})
    storm_name = args.storm or DEFAULT_STORM.get(args.world, "design_storm_PLACEHOLDER")
    t0 = time.time()
    world, storm, water = prepare(args.world, storm_name, cfg)
    print(f"water: {time.time() - t0:.1f}s  mass balance error {water.mass['balance_error']:.2e}  "
          f"max depth {float(water.depth.max()):.2f} m  storm {storm.total_mm:.0f} mm"
          f"{'  [SYNTHETIC]' if storm.synthetic else ''}")
    runs = {}
    for sc in args.scenarios.split(","):
        runs[sc] = run_one(world, storm, water, cfg, sc, args.seed, record=True)
    rows = pd.DataFrame([r for _, r in runs.values()]).set_index("scenario")
    cols = ["n_streets_flooded", "n_streets_missed", "lead_median_min", "share_lead_ge15", "share_lead_ge30",
            "n_cars_at_risk", "pct_moved", "false_alarm_rate", "msgs_per_resident", "rm_avoided_vs_no_action"]
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(rows[cols].round(2).to_string())
    if prov["_placeholders_in_use"]:
        print("PLACEHOLDER VALUES in use:", ", ".join(prov["_placeholders_in_use"]))
    run_id = f"{world.name}_{storm.name}_seed{args.seed}"
    out = export_runs(run_id, world, storm, water, runs, prov["_placeholders_in_use"])
    (ROOT / "results").mkdir(exist_ok=True)
    rows.reset_index().to_csv(ROOT / "results" / f"sim_{run_id}.csv", index=False)
    print(f"replay exported to {out.relative_to(ROOT)}  ({time.time() - t0:.1f}s total)")


def cmd_sweep(args):
    from ffsa.experiments.sweep import run_sweep

    run_sweep(args.config, world_name=args.world, n_runs=args.n, allow_placeholders=args.allow_placeholders,
              n_jobs=args.jobs)


def cmd_figures(args):
    from ffsa.figures import make_figures

    make_figures(args.results)


def cmd_assumptions(args):
    from ffsa.docs import write_assumptions

    print(write_assumptions())


def cmd_validate(args):
    from ffsa.docs import write_validation

    print(write_validation(args.world, args.storm))


def cmd_data(args):
    from ffsa.data.prepare import prepare_area

    prepare_area(args.area, allow_placeholders=args.allow_placeholders, skip_optional_osm=args.skip_optional_osm)


def main(argv=None):
    p = argparse.ArgumentParser(prog="ffsa")
    p.add_argument("--allow-placeholders", action="store_true",
                   help="run with unsourced placeholder values (outputs are stamped PLACEHOLDER VALUES)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sim", help="run S0-S3 once and export a dashboard replay")
    s.add_argument("--world", default="toy")
    s.add_argument("--storm")
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--scenarios", default="S0,S1,S2,S3")
    s.add_argument("--sensors", type=int)
    s.add_argument("--compliance", type=float)
    s.set_defaults(fn=cmd_sim)
    sub.add_parser("export", help="alias of sim").set_defaults(fn=cmd_sim, world="toy", storm=None, seed=1,
                                                                scenarios="S0,S1,S2,S3", sensors=None, compliance=None)

    s = sub.add_parser("sweep", help="Monte Carlo sweep -> results/*.parquet")
    s.add_argument("--world", default="toy")
    s.add_argument("--config", default=str(ROOT / "config" / "sweeps" / "default.yaml"))
    s.add_argument("-n", type=int, help="override Monte Carlo runs per cell")
    s.add_argument("--jobs", type=int, default=-1)
    s.set_defaults(fn=cmd_sweep)

    s = sub.add_parser("figures", help="deck-ready figures from a sweep parquet")
    s.add_argument("--results", default=None)
    s.set_defaults(fn=cmd_figures)

    sub.add_parser("assumptions", help="regenerate docs/ASSUMPTIONS.md").set_defaults(fn=cmd_assumptions)

    s = sub.add_parser("validate", help="docs/VALIDATION.md: modelled vs reported flooded streets")
    s.add_argument("--world", default="bbr")
    s.add_argument("--storm", default="design_storm_PLACEHOLDER")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("data", help="fetch and prepare the real study area (Phase 3)")
    s.add_argument("--area", default=str(ROOT / "config" / "area_bbr.yaml"))
    s.add_argument("--skip-optional-osm", action="store_true",
                   help="build without OSM land use and car parks (when Overpass is down)")
    s.set_defaults(fn=cmd_data)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
