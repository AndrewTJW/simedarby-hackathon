"""The static world a simulation runs in: terrain grid, road graph, streets, buildings, safe zones, drains.

Both the synthetic toy world (Phase 2) and the real BBR world (Phase 3) are built into this one
structure, so everything downstream (hydrology, agents, export) is shared.

Grid convention: row 0 is the northern edge. Cell (r, c) has its centre at
x = x0 + (c + 0.5) * cell_m, y = y0 - (r + 0.5) * cell_m, where (x0, y0) is the north-west corner
in the project CRS. Cells are addressed by flat index r * W + c.
"""
from __future__ import annotations

import math
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np

from ffsa.config import ROOT

PROCESSED = ROOT / "data" / "processed"

# land-cover codes
GREEN, RESIDENTIAL, ROAD, ROOF = 0, 1, 2, 3


@dataclass
class Drains:
    cell: np.ndarray            # (N,) flat cell index of each drain node
    downstream: np.ndarray      # (N,) index of the next node, -1 = leaves the domain
    storage_m3: np.ndarray      # (N,)
    capacity_m3s: np.ndarray    # (N,) outflow capacity to the downstream node
    upstream_cells: np.ndarray  # (N,) contributing cells (incl. upstream nodes), for placement
    kind: list[str]             # "inlet" | "culvert"


@dataclass
class World:
    name: str
    synthetic: bool
    cell_m: float
    crs: str
    x0: float
    y0: float
    dem: np.ndarray             # (H, W) metres, after cleanup and road burning
    landcover: np.ndarray       # (H, W) land-cover codes
    outlet_mask: np.ndarray     # (H, W) bool, cells where surface water leaves the domain
    graph: nx.Graph             # nodes: x, y, cell. edges: eid, street, length, cells, coords
    streets: list[dict]         # id, name, cells (flat idx array), eids
    buildings: list[dict]       # id, x, y, cell, kind, street, node, polygon (optional, xy list)
    safe_zones: list[dict]      # id, name, x, y, node, kind
    lonlat: dict                # {"mode": "local", "lon0", "lat0"} or {"mode": "pyproj", "crs"}
    drains: Drains | None = None
    cell_node: np.ndarray | None = None   # (H*W,) drain node serving each cell
    validation_streets: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return self.dem.shape

    @property
    def cell_area(self) -> float:
        return self.cell_m ** 2

    def cell_xy(self, flat) -> tuple[np.ndarray, np.ndarray]:
        r, c = np.divmod(np.asarray(flat), self.shape[1])
        return self.x0 + (c + 0.5) * self.cell_m, self.y0 - (r + 0.5) * self.cell_m

    def xy_cell(self, x, y) -> np.ndarray:
        H, W = self.shape
        c = np.clip(((np.asarray(x) - self.x0) // self.cell_m).astype(int), 0, W - 1)
        r = np.clip(((self.y0 - np.asarray(y)) // self.cell_m).astype(int), 0, H - 1)
        return r * W + c

    def edge_by_eid(self) -> list[tuple]:
        out = [None] * self.graph.number_of_edges()
        for u, v, d in self.graph.edges(data=True):
            out[d["eid"]] = (u, v, d)
        return out

    # --- coordinates for the dashboard ---------------------------------------------------------
    def to_lonlat(self, x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if self.lonlat["mode"] == "local":
            lat0 = self.lonlat["lat0"]
            lat = lat0 + y / 111_320.0
            lon = self.lonlat["lon0"] + x / (111_320.0 * math.cos(math.radians(lat0)))
            return lon, lat
        from pyproj import Transformer

        tr = Transformer.from_crs(self.crs, "EPSG:4326", always_xy=True)
        return tr.transform(x, y)

    def bounds_lonlat(self) -> list[float]:
        H, W = self.shape
        xs = [self.x0, self.x0 + W * self.cell_m]
        ys = [self.y0 - H * self.cell_m, self.y0]
        lon, lat = self.to_lonlat(np.array([xs[0], xs[1], xs[0], xs[1]]), np.array([ys[0], ys[0], ys[1], ys[1]]))
        return [float(np.min(lon)), float(np.min(lat)), float(np.max(lon)), float(np.max(lat))]

    # --- persistence ---------------------------------------------------------------------------
    def save(self, path: Path | None = None) -> Path:
        path = path or PROCESSED / f"world_{self.name}.pkl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)
        return path

    @staticmethod
    def load(name_or_path: str | Path) -> "World":
        p = Path(name_or_path)
        if not p.suffix:
            p = PROCESSED / f"world_{name_or_path}.pkl"
        with open(p, "rb") as f:
            return pickle.load(f)


def runoff_C_grid(landcover: np.ndarray, C) -> np.ndarray:
    lut = np.array([C.green, C.residential, C.road, C.roof])
    return lut[landcover]


def densify(coords, step: float) -> np.ndarray:
    """Points every `step` metres along a polyline (always including both ends)."""
    pts = np.asarray(coords, dtype=float)
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.ceil(np.hypot(*(b - a)) / step)))
        out.extend(a + (b - a) * (k / n) for k in range(1, n + 1))
    return np.asarray(out)


def assign_to_edges(world: World, xs, ys) -> tuple[np.ndarray, np.ndarray]:
    """For each point, the eid of the closest road edge and the nearer endpoint node of that edge."""
    from scipy.spatial import cKDTree

    pts, owner = [], []
    edges = world.edge_by_eid()
    for eid, (u, v, d) in enumerate(edges):
        p = densify(d["coords"], world.cell_m / 3)
        pts.append(p)
        owner.append(np.full(len(p), eid))
    tree = cKDTree(np.vstack(pts))
    owner = np.concatenate(owner)
    _, idx = tree.query(np.column_stack([xs, ys]))
    eids = owner[idx]
    nodes = np.empty(len(eids), dtype=object)
    for i, eid in enumerate(eids):
        u, v, _ = edges[eid]
        nu, nv = world.graph.nodes[u], world.graph.nodes[v]
        du = math.hypot(nu["x"] - xs[i], nu["y"] - ys[i])
        dv = math.hypot(nv["x"] - xs[i], nv["y"] - ys[i])
        nodes[i] = u if du <= dv else v
    return eids, nodes


def cells_along(world: World, coords) -> np.ndarray:
    """Unique flat cells a polyline passes through, in path order."""
    p = densify(coords, world.cell_m / 3)
    cells = world.xy_cell(p[:, 0], p[:, 1])
    _, first = np.unique(cells, return_index=True)
    return cells[np.sort(first)]
