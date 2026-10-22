"""Export runs to the static dashboard: dashboard/public/runs/<run_id>/.

Writes the plain files from the plan (meta.json, *.geojson, depth.bin, <scenario>/timeline.json,
cars.json, events.json) and a single `bundle.js` that carries all of it, so the dashboard also works
when opened straight from disk (file://), where browsers block fetch().
"""
from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path

import numpy as np

from ffsa.abm.alert_fsm import Level
from ffsa.abm.model import FloodModel
from ffsa.config import ROOT
from ffsa.world import World

RUNS = ROOT / "dashboard" / "public" / "runs"


def _r(v, n=6):
    return round(float(v), n)


def _ll(world: World, xs, ys) -> list[list[float]]:
    lon, lat = world.to_lonlat(np.asarray(xs), np.asarray(ys))
    return [[_r(a), _r(b)] for a, b in zip(np.atleast_1d(lon), np.atleast_1d(lat))]


def _fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def geo_layers(world: World, model: FloodModel, street_t_flood: np.ndarray) -> dict:
    edges = world.edge_by_eid()
    streets = []
    for s in world.streets:
        lines = [_ll(world, *np.asarray(edges[e][2]["coords"]).T) for e in s["eids"]]
        streets.append({"type": "Feature", "properties": {"id": s["id"], "name": s["name"],
                        "t_flood": None if np.isnan(street_t_flood[s["id"]]) else int(street_t_flood[s["id"]]),
                        "sensors": model.serve[s["id"]]},
                        "geometry": {"type": "MultiLineString", "coordinates": lines}})
    half = world.cell_m * 0.4
    buildings = []
    for b in world.buildings:
        poly = b.get("polygon")
        if poly is None:
            x, y = b["x"], b["y"]
            poly = [(x - half, y - half), (x + half, y - half), (x + half, y + half), (x - half, y + half), (x - half, y - half)]
        p = np.asarray(poly)
        buildings.append({"type": "Feature", "properties": {"id": b["id"], "kind": b["kind"], "street": b["street"]},
                          "geometry": {"type": "Polygon", "coordinates": [_ll(world, p[:, 0], p[:, 1])]}})
    safe = [{"type": "Feature", "properties": {"id": s["id"], "name": s["name"], "kind": s["kind"]},
             "geometry": {"type": "Point", "coordinates": _ll(world, [s["x"]], [s["y"]])[0]}} for s in world.safe_zones]
    sensors = []
    for s in model.sensors:
        x, y = world.cell_xy(s.cell)
        sensors.append({"type": "Feature", "properties": {"id": s.idx, "node": s.node, "kind": world.drains.kind[s.node]},
                        "geometry": {"type": "Point", "coordinates": _ll(world, [x], [y])[0]}})
    dx, dy = world.cell_xy(world.drains.cell)
    dll = _ll(world, dx, dy)
    drains = []
    for i, d in enumerate(world.drains.downstream):
        coords = [dll[i], dll[d]] if d >= 0 else [dll[i], dll[i]]
        drains.append({"type": "Feature", "properties": {"id": i, "kind": world.drains.kind[i],
                       "capacity_m3s": _r(world.drains.capacity_m3s[i], 3)},
                       "geometry": {"type": "LineString", "coordinates": coords}})
    return {"streets": _fc(streets), "buildings": _fc(buildings), "safe_zones": _fc(safe),
            "sensors": _fc(sensors), "drains": _fc(drains)}


def scenario_payload(world: World, model: FloodModel, res: dict) -> dict:
    cars = []
    for i, r in enumerate(model.residents):
        b = r.building
        trail = [[*_ll(world, [p[0]], [p[1]])[0], round(p[2], 2)] for p in r.trail]
        cars.append({"id": i, "building": b["id"], "home": _ll(world, [b["x"]], [b["y"]])[0], "street": r.street,
                     "state": r.state, "at_risk": r.at_risk, "outcome": r.final_outcome(),
                     "t_safe": r.t_safe, "t_flooded": r.t_flooded, "pressed": r.pressed, "path": trail})
    lead = [None if np.isnan(v) else float(v) for v in model.street_lead]
    first_act = [None if np.isnan(v) else int(v) for v in model.alerts.first_act]
    return {"timeline": model.timeline, "cars": cars, "events": model.alerts.events,
            "summary": {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in res.items()},
            "street_lead": lead, "street_first_act": first_act}


def export_runs(run_id: str, world: World, storm, water, runs: dict[str, tuple[FloodModel, dict]],
                placeholders: list[str]) -> Path:
    out = RUNS / run_id
    out.mkdir(parents=True, exist_ok=True)
    any_model = next(iter(runs.values()))[0]
    T, H, W = water.depth.shape
    depth_cm = np.clip(np.round(water.depth.astype(np.float32) * 100), 0, 255).astype(np.uint8)
    depth_gz = gzip.compress(depth_cm.tobytes(), compresslevel=9)
    (out / "depth.bin").write_bytes(depth_gz)
    geo = geo_layers(world, any_model, any_model.street_t_flood)
    for name, fc in geo.items():
        (out / f"{name}.geojson").write_text(json.dumps(fc), encoding="utf-8")
    meta = {
        "run_id": run_id, "world": world.name, "world_synthetic": world.synthetic,
        "storm": storm.name, "storm_synthetic": storm.synthetic, "storm_source": storm.source,
        "storm_warning_min": storm.warning_min,
        "scenarios": list(runs), "seed": any_model.seed, "n_sensors": len(any_model.sensors),
        "compliance": any_model.compliance, "start_local": any_model.cfg.sim.storm_start_local,
        "crs": world.crs, "bounds": world.bounds_lonlat(), "grid": {"T": T, "H": H, "W": W, "cell_m": world.cell_m},
        "depth_encoding": "gzip uint8 centimetres, row-major [T][H][W], row 0 = north",
        "rain": [round(float(v), 2) for v in storm.intensity_mm_hr[:T]],
        "levels": [l.name for l in Level],
        "thresholds": {"avoid_m": any_model.cfg.thresholds.avoid_m, "car_float_m": any_model.cfg.thresholds.car_float_m,
                       "drain_depth_m": any_model.cfg.hydro.drain_depth_m},
        "per_car_rm": any_model.cfg.damage.per_car_rm,
        "placeholders": placeholders,
        "config_hash": next(iter(runs.values()))[1]["config_hash"],
        "git_commit": next(iter(runs.values()))[1]["git_commit"],
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    scen = {}
    for name, (model, res) in runs.items():
        payload = scenario_payload(world, model, res)
        d = out / name
        d.mkdir(exist_ok=True)
        for k in ("timeline", "cars", "events"):
            (d / f"{k}.json").write_text(json.dumps(payload[k]), encoding="utf-8")
        (d / "summary.json").write_text(json.dumps(payload["summary"], indent=1), encoding="utf-8")
        scen[name] = payload
    bundle = {"meta": meta, "geo": geo, "scenarios": scen, "depth_gz_b64": base64.b64encode(depth_gz).decode()}
    (out / "bundle.js").write_text(
        "window.FFSA_RUNS = window.FFSA_RUNS || {};\n"
        f"window.FFSA_RUNS[{json.dumps(run_id)}] = {json.dumps(bundle, separators=(',', ':'))};\n", encoding="utf-8")
    _write_index()
    return out


def _write_index():
    ids = sorted(p.name for p in RUNS.iterdir() if (p / "bundle.js").exists())
    metas = [json.loads((RUNS / i / "meta.json").read_text(encoding="utf-8")) for i in ids]
    idx = [{"run_id": m["run_id"], "world": m["world"], "storm": m["storm"], "storm_synthetic": m["storm_synthetic"],
            "world_synthetic": m["world_synthetic"], "scenarios": m["scenarios"]} for m in metas]
    (RUNS / "index.js").write_text(f"window.FFSA_RUN_INDEX = {json.dumps(idx)};\n", encoding="utf-8")
    (RUNS / "index.json").write_text(json.dumps(idx, indent=1), encoding="utf-8")
