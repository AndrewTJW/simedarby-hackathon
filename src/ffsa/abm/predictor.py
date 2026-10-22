"""Time-to-flood predictor: TTF = (critical_level - current_level) / rate_of_rise.

The rate is a least-squares slope over the last `window` minutes of readings, boosted by a multiplier
under heavy rain. Deliberately simple and explainable.
"""
from __future__ import annotations

import math

import numpy as np


def ls_slope(times, values) -> float:
    """Least-squares slope of values against times (units per minute). NaNs are ignored."""
    t = np.asarray(times, dtype=float)
    v = np.asarray(values, dtype=float)
    ok = ~np.isnan(v)
    t, v = t[ok], v[ok]
    if len(t) < 2 or np.ptp(t) == 0:
        return float("nan")
    tc = t - t.mean()
    return float((tc * (v - v.mean())).sum() / (tc * tc).sum())


def time_to_flood(
    current: float,
    critical: float,
    rate: float,
    rain_mm_hr: float = 0.0,
    heavy_rain_mm_hr: float = math.inf,
    multiplier: float = 1.0,
) -> float:
    """Minutes until `critical` is reached. 0 if already there; inf if not rising (rate <= 0 or unknown)."""
    if current >= critical:
        return 0.0
    if rate is None or math.isnan(rate) or rate <= 0:
        return math.inf
    if rain_mm_hr > heavy_rain_mm_hr:
        rate *= multiplier
    return (critical - current) / rate
