"""Storm loading. Every storm becomes a per-minute intensity series in mm/hr.

Three kinds, all described by a YAML file in config/storms/:
- ``csv``: a real record (``timestamp, rainfall_mm`` at any interval), resampled to 1 min.
- ``design``: MSMA IDF + temporal pattern (synthetic).
- ``table``: piecewise-linear knots (synthetic, for the toy world).
Every storm file must carry ``source`` and ``synthetic``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ffsa.config import CONFIG_DIR, ConfigError, load_yaml


@dataclass
class Storm:
    name: str
    intensity_mm_hr: np.ndarray  # length = duration_minutes, value for minute t
    synthetic: bool
    source: str
    warning_min: int | None

    def hash(self) -> str:
        h = hashlib.sha1(self.intensity_mm_hr.astype(np.float32).tobytes())
        h.update(json.dumps([self.name, self.warning_min]).encode())
        return h.hexdigest()[:10]

    @property
    def total_mm(self) -> float:
        return float(self.intensity_mm_hr.sum() / 60.0)


def idf_intensity(idf: dict, ari_years: float, duration_hr: float) -> float:
    """MSMA 2nd ed. IDF: i = lambda * T^kappa / (d + theta)^eta (mm/hr)."""
    return idf["lambda"] * ari_years ** idf["kappa"] / (duration_hr + idf["theta"]) ** idf["eta"]


def chicago_pattern(idf: dict, ari_years: float, duration_min: int, peak_position: float) -> np.ndarray:
    """Chicago design hyetograph built from the IDF curve so every centred window matches the IDF depth."""
    t = np.arange(duration_min + 1, dtype=float)
    # cumulative depth of the most intense window of length d (minutes)
    def depth(d_min: np.ndarray) -> np.ndarray:
        d_hr = np.maximum(d_min, 1e-6) / 60.0
        return idf_intensity(idf, ari_years, d_hr) * d_hr
    tp = peak_position * duration_min
    # window length that ends at each minute boundary, measured outward from the peak
    before = np.clip(tp - t, 0, None) / max(peak_position, 1e-6)
    after = np.clip(t - tp, 0, None) / max(1 - peak_position, 1e-6)
    cum = np.where(t <= tp, -peak_position * depth(before), (1 - peak_position) * depth(after))
    mm_per_min = np.diff(cum)
    return np.clip(mm_per_min, 0, None) * 60.0


def _from_table(knots: list[list[float]], duration: int) -> np.ndarray:
    k = np.asarray(knots, dtype=float)
    return np.interp(np.arange(duration), k[:, 0], k[:, 1], left=0.0, right=0.0)


def _from_csv(path: Path, duration: int, start: str | None) -> np.ndarray:
    df = pd.read_csv(path, parse_dates=["timestamp"]).set_index("timestamp").sort_index()
    if start is not None:
        df = df[df.index >= pd.Timestamp(start)]
    step_min = df.index.to_series().diff().median().total_seconds() / 60.0
    # spread each interval's depth evenly over its minutes (depth-preserving)
    per_min = df["rainfall_mm"].resample("1min").asfreq().bfill(limit=int(step_min) - 1).fillna(0.0) / step_min
    arr = per_min.to_numpy()[:duration] * 60.0
    return np.pad(arr, (0, max(0, duration - len(arr))))


def load_storm(name_or_path: str | Path, duration: int) -> Storm:
    path = Path(name_or_path)
    if not path.suffix:
        path = CONFIG_DIR / "storms" / f"{name_or_path}.yaml"
    spec = load_yaml(path)
    for key in ("name", "source", "synthetic", "kind"):
        if key not in spec:
            raise ConfigError(f"Storm {path.name} must define `{key}`")
    kind = spec["kind"]
    if kind == "table":
        series = _from_table(spec["knots"], duration)
    elif kind == "design":
        rain = chicago_pattern(spec["idf"], spec["ari_years"], spec["duration_min"], spec.get("peak_position", 0.4))
        off = spec.get("start_offset_min", 0)
        series = np.zeros(duration)
        n = min(len(rain), duration - off)
        series[off : off + n] = rain[:n]
    elif kind == "csv":
        if spec["synthetic"]:
            raise ConfigError("CSV storms are real records; set synthetic: false and cite the source")
        series = _from_csv(path.parent / spec["csv"], duration, spec.get("start"))
    else:
        raise ConfigError(f"Unknown storm kind {kind}")
    return Storm(
        name=spec["name"],
        intensity_mm_hr=series.astype(float),
        synthetic=bool(spec["synthetic"]),
        source=spec["source"],
        warning_min=spec.get("thunderstorm_warning_min"),
    )
