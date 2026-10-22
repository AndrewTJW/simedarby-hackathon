"""Deck-ready figures from a sweep Parquet (PNG for slides + SVG), and a results bundle for results.html."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ffsa.config import ROOT, load_config

FIG = ROOT / "results" / "figures"
DASH = ROOT / "dashboard" / "public" / "figures"
COLORS = {"S0": "#7d8590", "S1": "#8e6bbf", "S2": "#2f7fc1", "S3": "#e8743b"}
NAMES = {"S0": "S0 no alerts", "S1": "S1 river-style", "S2": "S2 sensors, threshold", "S3": "S3 sensors + rate of rise"}

plt.rcParams.update({"font.size": 15, "axes.titlesize": 17, "axes.labelsize": 15, "legend.fontsize": 12,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 110})


def _stamp(fig, df: pd.DataFrame):
    notes = []
    if df["world"].iloc[0] == "toy":
        notes.append("TOY WORLD")
    if df["storm_synthetic"].any():
        notes.append("SYNTHETIC STORM")
    if df["placeholders"].iloc[0]:
        notes.append("PLACEHOLDER VALUES")
    notes.append(f"N={int(df.groupby(['scenario', 'n_sensors', 'compliance']).seed.nunique().median())} runs/cell")
    fig.text(0.99, 0.01, " · ".join(notes), ha="right", va="bottom", fontsize=10, color="#b42318" if len(notes) > 1 else "#555")


def _save(fig, df, name):
    _stamp(fig, df)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    FIG.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(FIG / f"{name}.{ext}", dpi=160 if ext == "png" else None)
    plt.close(fig)
    return name


def _band(ax, x, g, col, label):
    m = g.mean()
    lo, hi = g.quantile(0.05), g.quantile(0.95)
    ax.plot(x, m.values, "-o", color=col, lw=2.5, label=label)
    ax.fill_between(x, lo.values, hi.values, color=col, alpha=0.15)


def make_figures(results: str | None = None) -> list[str]:
    path = Path(results) if results else max((ROOT / "results").glob("sweep_*_latest.parquet"), key=lambda p: p.stat().st_mtime)
    df = pd.read_parquet(path)
    cfg, _ = load_config(allow_placeholders=True)
    k0 = 20 if 20 in df.n_sensors.unique() else int(df.n_sensors.median())
    c0 = 0.5 if 0.5 in df.compliance.unique() else float(df.compliance.median())
    storm = df.storm.iloc[0]
    base = df[(df.n_sensors == k0) & (df.compliance == c0) & (df.storm == storm)]
    scen = [s for s in ("S0", "S1", "S2", "S3") if s in df.scenario.unique()]
    made = []

    # 1. lead time by scenario
    fig, ax = plt.subplots(figsize=(9, 5.5))
    data = [base[base.scenario == s]["lead_median_min"].dropna() for s in scen]
    bp = ax.boxplot(data, patch_artist=True, widths=0.55, showfliers=False)
    for patch, s in zip(bp["boxes"], scen):
        patch.set_facecolor(COLORS[s]); patch.set_alpha(0.75)
    ax.set_xticks(range(1, len(scen) + 1), [NAMES[s].replace(" ", "\n", 1) for s in scen])
    ax.axhline(0, color="#999", lw=1)
    ax.set_ylabel("median lead time per run (min)")
    ax.set_title(f"Alert lead time before streets reach 0.3 m ({k0} sensors)")
    made.append(_save(fig, df, "1_lead_time_by_scenario"))

    # 2. % moved vs sensors
    fig, ax = plt.subplots(figsize=(9, 5.5))
    sub = df[(df.compliance == c0) & (df.storm == storm)]
    for s in scen:
        g = sub[sub.scenario == s].groupby("n_sensors")["pct_moved"]
        _band(ax, g.mean().index, g, COLORS[s], NAMES[s])
    ax.set_xlabel("number of street sensors"); ax.set_ylabel("at-risk cars moved before flooding")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xticks(sorted(sub.n_sensors.unique()))
    ax.set_title(f"How many sensors does BBR need? (compliance {int(c0 * 100)}%)")
    ax.legend(frameon=False)
    made.append(_save(fig, df, "2_moved_vs_sensors"))

    # 3. % moved vs compliance, S1 vs S3
    fig, ax = plt.subplots(figsize=(9, 5.5))
    sub = df[(df.n_sensors == k0) & (df.storm == storm)]
    for s in [x for x in ("S1", "S3") if x in scen]:
        g = sub[sub.scenario == s].groupby("compliance")["pct_moved"]
        _band(ax, g.mean().index * 100, g, COLORS[s], NAMES[s])
    ax.set_xlabel("residents who act on an alert (%)"); ax.set_ylabel("at-risk cars moved before flooding")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_title("Targeted street alerts vs a township broadcast")
    ax.legend(frameon=False)
    made.append(_save(fig, df, "3_moved_vs_compliance"))

    # 4. RM avoided per storm vs S0
    fig, ax = plt.subplots(figsize=(9, 5.5))
    alerts = [s for s in scen if s != "S0"]
    vals = [base[base.scenario == s]["rm_avoided_vs_s0"] for s in alerts]
    means = [v.mean() for v in vals]
    err = np.array([[m - v.quantile(0.05), v.quantile(0.95) - m] for m, v in zip(means, vals)]).T
    ax.bar([NAMES[s].replace(" ", "\n", 1) for s in alerts], means, yerr=err, capsize=6, color=[COLORS[s] for s in alerts], alpha=0.85)
    ax.set_ylabel("RM damage avoided vs S0, per storm")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"RM{v / 1e3:,.0f}k"))
    ax.set_title("Vehicle damage avoided (mean, 90% interval)")
    made.append(_save(fig, df, "4_rm_avoided"))

    # 5. false alarms S2 vs S3
    fig, ax = plt.subplots(figsize=(9, 5.5))
    sub = df[(df.compliance == c0) & (df.storm == storm)]
    for s in [x for x in ("S2", "S3") if x in scen]:
        g = sub[sub.scenario == s].groupby("n_sensors")["false_alarm_rate"]
        _band(ax, g.mean().index, g, COLORS[s], NAMES[s])
    ax.set_xlabel("number of street sensors"); ax.set_ylabel("ACT alerts on streets that never flooded")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_xticks(sorted(sub.n_sensors.unique()))
    ax.set_title("False-alarm rate")
    ax.legend(frameon=False)
    made.append(_save(fig, df, "5_false_alarms"))

    # 6. cost vs benefit
    fig, ax = plt.subplots(figsize=(9, 5.5))
    s3 = base[base.scenario == "S3"]["rm_avoided_vs_s0"] if "S3" in scen else pd.Series([np.nan])
    ax.bar(["Pilot cost\n(20 sensors)", "RM avoided\nper storm (S3)"], [cfg.damage.pilot_cost_rm, s3.mean()],
           color=["#7d8590", COLORS["S3"]], alpha=0.85,
           yerr=[[0, s3.mean() - s3.quantile(0.05)], [0, s3.quantile(0.95) - s3.mean()]], capsize=6)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"RM{v / 1e3:,.0f}k"))
    ax.set_title("One-off pilot cost vs damage avoided in one storm")
    made.append(_save(fig, df, "6_cost_benefit"))

    # bundle for results.html
    DASH.mkdir(parents=True, exist_ok=True)
    for name in made:
        shutil.copy(FIG / f"{name}.png", DASH / f"{name}.png")
    from ffsa.experiments.sweep import summarize

    summ = summarize(df).replace({np.nan: None})
    info = {"source": path.name, "world": df.world.iloc[0], "storm": storm,
            "synthetic_storm": bool(df.storm_synthetic.any()), "placeholders": df.placeholders.iloc[0],
            "figures": made, "summary": summ.to_dict(orient="records")}
    (DASH / "results.js").write_text(f"window.FFSA_RESULTS = {json.dumps(info)};\n", encoding="utf-8")
    print(f"{len(made)} figures -> {FIG.relative_to(ROOT)} (and dashboard/public/figures)")
    return made
