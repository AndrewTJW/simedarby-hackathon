"""Monte Carlo sweep: scenario x sensors x compliance x storm x N seeds -> one tidy Parquet table."""
from __future__ import annotations

import itertools
import time
from datetime import datetime
from functools import lru_cache

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from ffsa.config import ROOT, load_config, load_yaml
from ffsa.experiments.run_one import prepare, run_one

RESULTS = ROOT / "results"
SENSOR_INDEPENDENT = {"S0", "S1"}


@lru_cache(maxsize=4)
def _prepared(world_name: str, storm: str, overrides_items: tuple, allow_placeholders: bool):
    cfg, _ = load_config(overrides=dict(overrides_items), allow_placeholders=allow_placeholders)
    return (cfg, *prepare(world_name, storm, cfg))


def _task(world_name, storm, scenario, n_sensors, compliance, seeds, overrides_items, allow_placeholders):
    base, world, st, water = _prepared(world_name, storm, overrides_items, allow_placeholders)
    cfg = base.model_copy(update={
        "sensors": base.sensors.model_copy(update={"n_sensors": n_sensors}),
        "residents": base.residents.model_copy(update={"compliance": compliance}),
    })
    rows = []
    for seed in seeds:
        _, res = run_one(world, st, water, cfg, scenario, int(seed))
        rows.append(res)
    return rows


def run_sweep(config_path, world_name: str | None = None, n_runs: int | None = None,
              allow_placeholders: bool = False, n_jobs: int = -1) -> pd.DataFrame:
    spec = load_yaml(config_path)
    world_name = world_name or spec["world"]
    n = n_runs or spec["n_runs"]
    ov = tuple(sorted((spec.get("overrides") or {}).items()))
    _, prov = load_config(overrides=dict(ov), allow_placeholders=allow_placeholders)
    for storm in spec["storms"]:  # build water caches once, before forking workers
        _prepared(world_name, storm, ov, allow_placeholders)

    chunk = max(1, min(25, n))
    seed_chunks = [list(range(i, min(n, i + chunk))) for i in range(0, n, chunk)]
    tasks = []
    for storm, sc, comp in itertools.product(spec["storms"], spec["scenarios"], spec["compliance"]):
        sensors = [max(spec["n_sensors"])] if sc in SENSOR_INDEPENDENT else spec["n_sensors"]
        for k, seeds in itertools.product(sensors, seed_chunks):
            tasks.append((world_name, storm, sc, k, comp, seeds, ov, allow_placeholders))
    print(f"sweep: {len(tasks)} tasks, {n} runs per cell, world={world_name}")
    t0 = time.time()
    out = Parallel(n_jobs=n_jobs, verbose=5)(delayed(_task)(*t) for t in tasks)
    df = pd.DataFrame([r for rows in out for r in rows])

    # S0/S1 ignore street sensors: report the same runs against every sensor count
    dup = []
    for k in spec["n_sensors"]:
        part = df[df.scenario.isin(SENSOR_INDEPENDENT)].copy()
        part["n_sensors"] = k
        dup.append(part)
    df = pd.concat([df[~df.scenario.isin(SENSOR_INDEPENDENT)], *dup], ignore_index=True)
    df["sensor_independent"] = df.scenario.isin(SENSOR_INDEPENDENT)
    df["placeholders"] = ",".join(prov["_placeholders_in_use"])

    # RM avoided vs S0 for the same storm, compliance, seed
    s0 = df[df.scenario == "S0"].groupby(["storm", "compliance", "seed"])["damage_rm"].first()
    key = list(zip(df.storm, df.compliance, df.seed))
    df["rm_avoided_vs_s0"] = s0.reindex(key).to_numpy() - df["damage_rm"].to_numpy()

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = RESULTS / f"sweep_{world_name}_{stamp}.parquet"
    df.to_parquet(path, index=False)
    (RESULTS / f"sweep_{world_name}_latest.parquet").write_bytes(path.read_bytes())
    summary = summarize(df)
    summary.to_csv(RESULTS / f"summary_{world_name}.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_columns", 30, "display.max_rows", 200):
        print(summary.round(2).to_string(index=False))
    print(f"{len(df)} rows -> {path.relative_to(ROOT)}  ({time.time() - t0:.0f}s)")
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["storm", "scenario", "n_sensors", "compliance"])
    q = lambda p: (lambda s: np.nanpercentile(s, p) if s.notna().any() else np.nan)
    return g.agg(
        runs=("seed", "count"),
        lead_median_min=("lead_median_min", "median"),
        share_lead_ge15=("share_lead_ge15", "mean"),
        pct_moved=("pct_moved", "mean"),
        pct_moved_p5=("pct_moved", q(5)),
        pct_moved_p95=("pct_moved", q(95)),
        false_alarm_rate=("false_alarm_rate", "mean"),
        msgs_per_resident=("msgs_per_resident", "mean"),
        rm_avoided_vs_s0=("rm_avoided_vs_s0", "mean"),
    ).reset_index()
