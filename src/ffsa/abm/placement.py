"""Sensor placement strategies and the street -> serving-sensor assignment."""
from __future__ import annotations

import networkx as nx
import numpy as np

from ffsa.world import World, assign_to_edges, is_validation_street


def _spread(order: np.ndarray, xy: np.ndarray, k: int, min_spacing: float, chosen: list[int] | None = None) -> list[int]:
    chosen = list(chosen or [])
    for i in order:
        if len(chosen) >= k:
            break
        if i in chosen:
            continue
        if all(np.hypot(*(xy[i] - xy[j])) >= min_spacing for j in chosen):
            chosen.append(int(i))
    for i in order:  # relax spacing if the area is too small for k well-spaced sensors
        if len(chosen) >= k:
            break
        if i not in chosen:
            chosen.append(int(i))
    return chosen


def place_sensors(world: World, k: int, strategy: str, rng: np.random.Generator, min_spacing: float,
                  low_point_window_m: float = 300.0) -> list[int]:
    """Return k drain-node indices."""
    dr = world.drains
    xy = np.column_stack(world.cell_xy(dr.cell))
    by_flow = np.argsort(-dr.upstream_cells, kind="stable")
    if strategy == "flow_accumulation":
        return _spread(by_flow, xy, k, min_spacing)
    if strategy == "low_points":
        # terrain only: how far each node sits below the mean ground level around it (sags, dips, underpasses)
        from scipy.ndimage import uniform_filter

        size = max(3, int(round(low_point_window_m / world.cell_m)) | 1)
        relief = uniform_filter(world.dem.astype(float), size=size, mode="nearest").ravel() - world.dem.ravel()
        return _spread(np.lexsort((-dr.upstream_cells, -relief[dr.cell])), xy, k, min_spacing)
    if strategy == "historical":
        cells = [c for s in world.streets if is_validation_street(s["name"], world.validation_streets) for c in s["cells"]]
        seeds = []
        if cells:
            sx, sy = world.cell_xy(np.asarray(cells))
            for x, y in zip(sx, sy):
                seeds.append(int(np.argmin(np.hypot(xy[:, 0] - x, xy[:, 1] - y))))
            seeds = list(dict.fromkeys(seeds))
        return _spread(by_flow, xy, k, min_spacing, chosen=_spread(np.asarray(seeds, dtype=int), xy, min(k, len(seeds)), min_spacing))
    if strategy == "random":
        return [int(i) for i in rng.choice(len(dr.cell), size=min(k, len(dr.cell)), replace=False)]
    raise ValueError(f"Unknown placement strategy {strategy}")


def serving_sensors(world: World, sensor_nodes: list[int], max_dist: float, elev_tol: float, n_serve: int = 2) -> list[list[int]]:
    """For each street, up to `n_serve` sensors (indices into sensor_nodes), nearest by road distance,
    restricted to sensors upstream of or level with the street. Streets beyond max_dist are unserved."""
    dr = world.drains
    sx, sy = world.cell_xy(dr.cell[sensor_nodes])
    _, gnodes = assign_to_edges(world, sx, sy)
    z = world.dem.ravel()
    dist = [nx.single_source_dijkstra_path_length(world.graph, g, cutoff=max_dist, weight="length") for g in gnodes]
    edges = world.edge_by_eid()
    out = []
    for s in world.streets:
        ends = {n for e in s["eids"] for n in edges[e][:2]}
        z_low = z[s["cells"]].min()
        cand = []
        for k, dk in enumerate(dist):
            d = min((dk.get(n, np.inf) for n in ends), default=np.inf)
            if d <= max_dist and z[dr.cell[sensor_nodes[k]]] >= z_low - elev_tol:
                cand.append((d, k))
        out.append([k for _, k in sorted(cand)[:n_serve]])
    return out
