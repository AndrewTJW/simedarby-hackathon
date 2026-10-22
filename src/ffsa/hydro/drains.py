"""Drain-node network built along the road graph.

Nodes sit every `drain_node_spacing_m` along roads, plus "culvert" nodes at local low points of the
road network. Each node drains to the nearest lower node (strictly lower, so the network is a tree
that ends at the outlet). Capacity follows an MSMA minor-system design flow for the node's upstream
area, scaled by one global calibration factor.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from ffsa.config import Config
from ffsa.world import Drains, World, densify, runoff_C_grid


def _road_low_points(world: World) -> list[int]:
    """Road cells lower than all 8 neighbours that are also road cells (culverts / underpasses)."""
    H, W = world.shape
    z = world.dem
    road = world.landcover == 2
    pad = np.pad(np.where(road, z, np.inf), 1, constant_values=np.inf)
    lower = np.ones_like(road)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr or dc:
                lower &= z < pad[1 + dr : 1 + dr + H, 1 + dc : 1 + dc + W]
    return list(np.flatnonzero(road & lower))


def build_drains(world: World, cfg: Config) -> tuple[Drains, np.ndarray]:
    hc = cfg.hydro
    pts = [densify(d["coords"], hc.drain_node_spacing_m) for _, _, d in world.graph.edges(data=True)]
    pts = np.vstack(pts)
    inlet_cells = world.xy_cell(pts[:, 0], pts[:, 1])
    culvert_cells = _road_low_points(world)
    cells, kinds = [], []
    seen: set[int] = set()
    for c, k in [(c, "culvert") for c in culvert_cells] + [(int(c), "inlet") for c in inlet_cells]:
        if c not in seen:
            seen.add(c)
            cells.append(c)
            kinds.append(k)
    cells = np.asarray(cells)
    z = world.dem.ravel()[cells]
    x, y = world.cell_xy(cells)
    xy = np.column_stack([x, y])
    n = len(cells)

    # catchments: every cell drains to its nearest node
    H, W = world.shape
    all_x, all_y = world.cell_xy(np.arange(H * W))
    tree = cKDTree(xy)
    _, cell_node = tree.query(np.column_stack([all_x, all_y]))

    # downstream: nearest strictly-lower node (ties broken by index); nodes on the outlet leave the domain
    order_key = z + np.arange(n) * 1e-9
    on_outlet = world.outlet_mask.ravel()[cells]
    downstream = np.full(n, -1)
    k = min(n, 12)
    _, nbrs = tree.query(xy, k=k)
    for i in range(n):
        if on_outlet[i]:
            continue
        cand = [j for j in np.atleast_1d(nbrs[i]) if order_key[j] < order_key[i]]
        if not cand:
            lower = np.flatnonzero(order_key < order_key[i])
            if len(lower):
                cand = [lower[np.argmin(np.hypot(*(xy[lower] - xy[i]).T))]]
        if cand:
            downstream[i] = cand[0]

    # accumulate upstream area and C*A from high to low
    C = runoff_C_grid(world.landcover, hc.runoff_C).ravel()
    own_cells = np.bincount(cell_node, minlength=n).astype(float)
    own_CA = np.bincount(cell_node, weights=C * world.cell_area, minlength=n)
    up_cells, up_CA = own_cells.copy(), own_CA.copy()
    for i in np.argsort(-order_key):
        d = downstream[i]
        if d >= 0:
            up_cells[d] += up_cells[i]
            up_CA[d] += up_CA[i]
    capacity = up_CA / 1e4 * hc.drain_design_intensity_mm_hr / 360.0 * hc.drain_capacity_factor
    storage = capacity * hc.drain_storage_seconds
    drains = Drains(cell=cells, downstream=downstream, storage_m3=storage, capacity_m3s=capacity,
                    upstream_cells=up_cells, kind=kinds)
    return drains, cell_node.astype(np.int32)
