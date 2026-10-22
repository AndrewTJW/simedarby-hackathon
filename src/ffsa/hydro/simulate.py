"""Run a full storm through the hydrology once and cache depth[t, r, c] and drain_level[t, node].

Water depends only on storm + terrain + hydro parameters, never on residents, so Monte Carlo runs
replay this cache and only re-sample sensors and people.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ffsa.config import ROOT, Config
from ffsa.data.rainfall import Storm
from ffsa.hydro.runoff import runoff_volume
from ffsa.hydro.surface import outlet_outflow, route_surface
from ffsa.world import World, runoff_C_grid

CACHE = ROOT / "data" / "cache"
HYDRO_VERSION = 2  # bump whenever the hydrology code changes, so stale caches are not replayed


@dataclass
class Water:
    depth: np.ndarray        # (T, H, W) float16 metres, end of each minute
    drain_level: np.ndarray  # (T, N) float32, fraction of storage filled
    mass: dict
    street_depth: np.ndarray | None = None  # (T, S) max depth over each street's cells
    edge_depth: np.ndarray | None = None    # (T, E) max depth over each road edge's cells

    def derive(self, world: World) -> "Water":
        T = self.depth.shape[0]
        flat = self.depth.reshape(T, -1)
        self.street_depth = np.stack([flat[:, s["cells"]].max(axis=1) for s in world.streets], axis=1).astype(np.float32)
        edges = world.edge_by_eid()
        self.edge_depth = np.stack([flat[:, d["cells"]].max(axis=1) for _, _, d in edges], axis=1).astype(np.float32)
        return self


def water_key(world: World, storm: Storm, cfg: Config) -> str:
    blob = json.dumps({"version": HYDRO_VERSION, "world": world.name, "hydro": cfg.hydro.model_dump(mode="json"),
                       "sim": cfg.sim.model_dump(mode="json"), "storm": storm.hash(),
                       "dem": hashlib.sha1(world.dem.tobytes()).hexdigest()}, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def simulate(world: World, storm: Storm, cfg: Config) -> Water:
    H, W = world.shape
    T = cfg.sim.duration_minutes
    nsub = cfg.sim.substeps_per_tick
    dt = cfg.sim.tick_minutes * 60.0 / nsub
    dx = world.cell_m
    A = world.cell_area
    z = world.dem.astype(np.float64)
    C = runoff_C_grid(world.landcover, cfg.hydro.runoff_C)
    dr = world.drains
    N = len(dr.cell)
    cell_node = world.cell_node
    down = dr.downstream
    to_out = down < 0
    down_idx = np.where(to_out, 0, down)
    S = dr.storage_m3
    cap = dr.capacity_m3s * dt
    inlet_cap = dr.capacity_m3s * cfg.hydro.inlet_capacity_factor * dt
    n_catch = np.maximum(np.bincount(cell_node, minlength=N), 1)

    h = np.zeros((H, W))
    V = np.zeros(N)
    depth = np.empty((T, H, W), dtype=np.float16)
    level = np.empty((T, N), dtype=np.float32)
    m = {"rain_total_m3": 0.0, "runoff_in_m3": 0.0, "drain_out_m3": 0.0, "surface_out_m3": 0.0}

    for t in range(T):
        i = storm.intensity_mm_hr[t] if t < len(storm.intensity_mm_hr) else 0.0
        r = runoff_volume(C, i, A, dt)  # (H, W) m^3
        m["rain_total_m3"] += i / 3.6e6 * dt * A * H * W * nsub
        for _ in range(nsub):
            m["runoff_in_m3"] += r.sum()
            # 1. drain conveyance (simultaneous update); surcharge spills evenly over the node's catchment
            out = np.minimum(V, cap)
            V -= out
            m["drain_out_m3"] += out[to_out].sum()
            V += np.bincount(down_idx[~to_out], weights=out[~to_out], minlength=N)
            spill = np.maximum(V - S, 0.0)
            V -= spill
            h += (spill / n_catch)[cell_node].reshape(H, W) / A
            # 2. runoff + surface water offered to the catchment inlet, limited by spare storage
            offer = (r + h * A).ravel()
            demand = np.bincount(cell_node, weights=offer, minlength=N)
            accept = np.minimum(S - V, inlet_cap)
            frac = np.where(demand > 0, np.minimum(1.0, accept / np.where(demand > 0, demand, 1.0)), 0.0)
            V += demand * frac
            h = (offer * (1.0 - frac[cell_node])).reshape(H, W) / A
            # 3. surface routing and outlet boundary
            h = route_surface(h, z, dx, dt, cfg.hydro.manning_n)
            q_out = outlet_outflow(h, world.outlet_mask, dx, dt)
            m["surface_out_m3"] += q_out.sum()
            h -= q_out / A
        depth[t] = h
        level[t] = V / S

    m["surface_store_m3"] = float(h.sum() * A)
    m["drain_store_m3"] = float(V.sum())
    m["balance_error"] = float(
        (m["runoff_in_m3"] - m["drain_out_m3"] - m["surface_out_m3"] - m["surface_store_m3"] - m["drain_store_m3"])
        / max(m["runoff_in_m3"], 1e-9)
    )
    return Water(depth=depth, drain_level=level, mass={k: float(v) for k, v in m.items()})


def get_water(world: World, storm: Storm, cfg: Config, use_cache: bool = True) -> Water:
    path = CACHE / f"{world.name}_{storm.name}_{water_key(world, storm, cfg)}.npz"
    if use_cache and path.exists():
        z = np.load(path, allow_pickle=False)
        water = Water(depth=z["depth"], drain_level=z["drain_level"], mass=json.loads(str(z["mass"])))
    else:
        water = simulate(world, storm, cfg)
        if use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, depth=water.depth, drain_level=water.drain_level, mass=json.dumps(water.mass))
    return water.derive(world)
