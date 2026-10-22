"""Run metrics: alert lead time, vehicles moved before flooding, RM damage, false alarms, alert volume."""
from __future__ import annotations

import numpy as np

OUTCOMES = ("moved_safe", "flooded_parked", "flooded_en_route", "never_at_risk", "not_moved_dry")


def first_crossing(series_t_by_x: np.ndarray, threshold: float) -> np.ndarray:
    """For a [T, X] array, the first t where value >= threshold for each column (NaN if never)."""
    hit = series_t_by_x >= threshold
    t = np.argmax(hit, axis=0).astype(float)
    t[~hit.any(axis=0)] = np.nan
    return t


def lead_times(t_flood: np.ndarray, t_first_act: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Lead time (min) per street = t_flood - t_first_ACT, for streets that flood.

    Returns (lead, missed). `lead` is NaN for streets that never flood. A flooded street is *missed*
    if it got no ACT before it flooded; its lead is NaN when there was no ACT at all, or negative
    when the ACT came late.
    """
    t_flood = np.asarray(t_flood, dtype=float)
    t_act = np.asarray(t_first_act, dtype=float)
    flooded = ~np.isnan(t_flood)
    lead = np.where(flooded, t_flood - t_act, np.nan)
    missed = flooded & ~(lead >= 0)
    return lead, missed


def summarize_lead(lead: np.ndarray, missed: np.ndarray, t_flood: np.ndarray) -> dict:
    flooded = ~np.isnan(np.asarray(t_flood, dtype=float))
    n = int(flooded.sum())
    valid = lead[flooded & ~np.isnan(lead)]
    # missed streets with no ACT contribute 0 minutes of warning to the share statistics
    warned = np.where(missed[flooded], 0.0, np.nan_to_num(lead[flooded], nan=0.0)) if n else np.array([])
    q = lambda p: float(np.percentile(valid, p)) if len(valid) else float("nan")
    return {
        "n_streets_flooded": n,
        "n_streets_missed": int(missed.sum()),
        "lead_median_min": q(50),
        "lead_p10_min": q(10),
        "lead_p90_min": q(90),
        "share_lead_ge15": float((warned >= 15).mean()) if n else float("nan"),
        "share_lead_ge30": float((warned >= 30).mean()) if n else float("nan"),
    }


def vehicle_summary(outcomes: list[str], at_risk: np.ndarray, pressed: np.ndarray | None = None) -> dict:
    o = np.asarray(outcomes)
    at_risk = np.asarray(at_risk, dtype=bool)
    n_risk = int(at_risk.sum())
    moved = (o == "moved_safe") & at_risk
    out = {
        "n_cars": len(o),
        "n_cars_at_risk": n_risk,
        "n_moved_safe_at_risk": int(moved.sum()),
        "pct_moved": float(moved.sum() / n_risk) if n_risk else float("nan"),
        "n_flooded_parked": int((o == "flooded_parked").sum()),
        "n_flooded_en_route": int((o == "flooded_en_route").sum()),
    }
    if pressed is not None:
        out["n_button_presses"] = int(np.asarray(pressed, dtype=bool).sum())
    return out


def car_damage_rm(flooded: np.ndarray, per_car_rm: float) -> float:
    """Step depth-damage: a car caught in >= car_float_m of water costs `per_car_rm`, otherwise 0."""
    return float(np.asarray(flooded, dtype=bool).sum() * per_car_rm)


def false_alarm_rate(act_alerted: np.ndarray, flooded: np.ndarray) -> float:
    """ACT-alerted streets that never flooded / all ACT-alerted streets."""
    act_alerted = np.asarray(act_alerted, dtype=bool)
    n = act_alerted.sum()
    return float((act_alerted & ~np.asarray(flooded, dtype=bool)).sum() / n) if n else float("nan")
