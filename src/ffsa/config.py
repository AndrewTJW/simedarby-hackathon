"""Configuration loading.

YAML leaves are written as ``{value, source}`` or ``{value, assumption}``. The loader strips the
provenance into a side table (used to generate docs/ASSUMPTIONS.md) and validates the plain values
with pydantic models.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"

PROVENANCE_KEYS = {"value", "source", "assumption", "placeholder"}


class ConfigError(ValueError):
    pass


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Sim(_M):
    tick_minutes: int
    duration_minutes: int
    storm_start_local: str
    substeps_per_tick: int


class Grid(_M):
    cell_m: float
    crs: str


class RunoffC(_M):
    road: float
    roof: float
    residential: float
    green: float


class Hydro(_M):
    runoff_C: RunoffC
    manning_n: float
    drain_node_spacing_m: float
    drain_design_intensity_mm_hr: float
    drain_capacity_factor: float
    drain_storage_seconds: float
    drain_depth_m: float
    inlet_capacity_factor: float
    road_burn_m: float
    outlet_edge: str


class Thresholds(_M):
    car_float_m: float
    avoid_m: float
    watch_drain_frac: float
    watch_rate_m_per_min: float
    act_ttf_min: float
    rate_window_min: int
    all_clear_falling_min: int
    min_hold_min: int
    heavy_rain_mm_hr: float
    heavy_rain_rate_multiplier: float
    rain_confirm_mm_hr: float
    rising_confirm_m_per_min: float
    s2_fixed_threshold: float


class Sensors(_M):
    report_interval_min: int
    noise_sigma_m: float
    p_dropout: float
    p_blocked: float
    n_sensors: int
    placement: str
    low_point_window_m: float
    min_spacing_m: float
    max_serve_distance_m: float
    same_elevation_tol_m: float


class ResponseDelay(_M):
    awake_median_min: float
    asleep_median_min: float
    sigma: float


class Residents(_M):
    cars_per_household: float
    park_at: str
    households_per_apartment: int
    max_cars: int
    compliance: float
    response_delay_lognorm: ResponseDelay
    s1_search_delay_min: float
    drive_speed_kmh: float
    slow_speed_kmh: float
    p_button: float
    self_notice_depth_m: float
    p_asleep_by_hour: list[float]
    p_away_by_hour: list[float]


class ScenarioS1(_M):
    gauge_threshold_frac: float
    publish_interval_min: int
    dissemination_delay_min: tuple[float, float]
    reach: float


class Damage(_M):
    per_car_rm: float | None
    partial_damage_depth_m: float
    pilot_cost_rm: float


class Config(_M):
    sim: Sim
    grid: Grid
    hydro: Hydro
    thresholds: Thresholds
    sensors: Sensors
    residents: Residents
    scenario_s1: ScenarioS1
    damage: Damage

    def hash(self) -> str:
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        return hashlib.sha1(blob).hexdigest()[:10]


def split_provenance(tree: Any, path: str = "", prov: dict | None = None) -> tuple[Any, dict]:
    """Replace every {value, source|assumption} leaf by its value; collect provenance by dotted path."""
    if prov is None:
        prov = {}
    if isinstance(tree, dict):
        if "value" in tree and set(tree) <= PROVENANCE_KEYS:
            if not (tree.get("source") or tree.get("assumption")):
                raise ConfigError(f"{path}: needs a `source` or an `assumption`")
            prov[path] = {k: tree.get(k) for k in ("value", "source", "assumption", "placeholder")}
            return tree["value"], prov
        return {k: split_provenance(v, f"{path}.{k}" if path else k, prov)[0] for k, v in tree.items()}, prov
    return tree, prov


def set_dotted(tree: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    for k in keys[:-1]:
        tree = tree[k]
    if keys[-1] not in tree:
        raise ConfigError(f"Unknown config key {dotted}")
    tree[keys[-1]] = value


def load_yaml(path: Path | str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(
    path: Path | str = CONFIG_DIR / "base.yaml",
    overrides: dict[str, Any] | None = None,
    allow_placeholders: bool = False,
) -> tuple[Config, dict]:
    """Return (validated config, provenance). Overrides use dotted keys, e.g. {"sensors.n_sensors": 10}."""
    raw, prov = split_provenance(load_yaml(path))
    raw = copy.deepcopy(raw)
    for k, v in (overrides or {}).items():
        set_dotted(raw, k, v)
    placeholders = [k for k, p in prov.items() if p.get("placeholder") and k not in (overrides or {})]
    if placeholders and not allow_placeholders:
        raise ConfigError(
            "Placeholder values must be sourced before use: "
            + ", ".join(placeholders)
            + ". Pass --allow-placeholders to run anyway (outputs will be stamped PLACEHOLDER VALUES)."
        )
    cfg = Config.model_validate(raw)
    prov["_placeholders_in_use"] = placeholders
    return cfg, prov
