"""Synthetic 50x50 toy world for Phase 2 (whole pipeline before any real data).

Terrain: a gentle north-to-south slope toward an outlet on the southern edge, with a few bowls
(where streets flood at different times) and a ridge of high ground in the north-east (safe car
parks). Roads: a regular grid; each block-length road segment is its own street. Nothing here is
real; the dashboard labels it "Toy world (synthetic)".
"""
from __future__ import annotations

import networkx as nx
import numpy as np

from ffsa.config import Config
from ffsa.hydro.drains import build_drains
from ffsa.world import RESIDENTIAL, ROAD, ROOF, GREEN, World, assign_to_edges, cells_along

N = 50
ROAD_LINES = [4, 12, 20, 28, 36, 45]
ROW_NAMES = ["Lorong Anggerik", "Lorong Bakawali", "Lorong Cempaka", "Lorong Dahlia", "Lorong Kenanga", "Lorong Melur"]
COL_NAMES = ["Jalan Satu", "Jalan Dua", "Jalan Tiga", "Jalan Empat", "Jalan Lima", "Jalan Enam"]
BOWLS = [  # (row, col, depth m, radius cells)
    (30, 14, 2.6, 6.0),
    (22, 34, 1.8, 5.0),
    (40, 30, 1.4, 5.0),
    (13, 20, 1.0, 4.0),
]


def toy_dem(seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    r, c = np.mgrid[0:N, 0:N].astype(float)
    z = 20.0 - 0.18 * r - 0.03 * c                                  # ~9 m fall to the south
    z += 4.0 * np.exp(-(((r - 6) ** 2) / 60 + ((c - 42) ** 2) / 60))  # north-east ridge
    for br, bc, d, rad in BOWLS:
        z -= d * np.exp(-((r - br) ** 2 + (c - bc) ** 2) / (2 * rad ** 2))
    z += rng.normal(0, 0.05, z.shape)
    return z


def build_toy_world(cfg: Config) -> World:
    cell = cfg.grid.cell_m
    dem = toy_dem()
    landcover = np.full((N, N), RESIDENTIAL, dtype=np.int8)
    landcover[30:40, 0:6] = GREEN  # a park

    G = nx.Graph()
    x0, y0 = 0.0, N * cell

    def xy(r, c):
        return x0 + (c + 0.5) * cell, y0 - (r + 0.5) * cell

    for r in ROAD_LINES:
        for c in ROAD_LINES:
            G.add_node((r, c), x=xy(r, c)[0], y=xy(r, c)[1], cell=r * N + c)

    world = World(name="toy", synthetic=True, cell_m=cell, crs="LOCAL (synthetic toy world)", x0=x0, y0=y0,
                  dem=dem, landcover=landcover, outlet_mask=np.zeros((N, N), bool), graph=G, streets=[],
                  buildings=[], safe_zones=[], lonlat={"mode": "local", "lon0": 101.0, "lat0": 3.0})

    streets = []
    eid = 0
    for i, r in enumerate(ROAD_LINES):
        for j, (c1, c2) in enumerate(zip(ROAD_LINES[:-1], ROAD_LINES[1:])):
            streets.append(((r, c1), (r, c2), f"{ROW_NAMES[i]} {j + 1}"))
    for j, c in enumerate(ROAD_LINES):
        for i, (r1, r2) in enumerate(zip(ROAD_LINES[:-1], ROAD_LINES[1:])):
            streets.append(((r1, c), (r2, c), f"{COL_NAMES[j]} {i + 1}"))
    for sid, (u, v, name) in enumerate(streets):
        coords = [xy(*u), xy(*v)]
        cells = cells_along(world, coords)
        length = float(np.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1]))
        G.add_edge(u, v, eid=eid, street=sid, length=length, cells=cells, coords=coords, name=name)
        world.streets.append({"id": sid, "name": name, "cells": cells, "eids": [eid]})
        eid += 1
        landcover.ravel()[cells] = ROAD

    # buildings: every other cell flanking each road, one cell off the road
    rng = np.random.default_rng(11)
    cand = set()
    for r in ROAD_LINES:
        for c in range(N):
            for rr in (r - 1, r + 1):
                if 0 <= rr < N and c % 2 == 0:
                    cand.add((rr, c))
    for c in ROAD_LINES:
        for r in range(N):
            for cc in (c - 1, c + 1):
                if 0 <= cc < N and r % 2 == 0:
                    cand.add((r, cc))
    cand = sorted(p for p in cand if landcover[p] == RESIDENTIAL)
    bx = np.array([xy(*p)[0] for p in cand])
    by = np.array([xy(*p)[1] for p in cand])
    eids, nodes = assign_to_edges(world, bx, by)
    edges = world.edge_by_eid()
    for k, p in enumerate(cand):
        landcover[p] = ROOF
        world.buildings.append({
            "id": k, "x": float(bx[k]), "y": float(by[k]), "cell": int(p[0] * N + p[1]),
            "kind": "apartments" if rng.random() < 0.1 else "house",
            "street": int(edges[eids[k]][2]["street"]), "node": nodes[k],
        })

    # road burning (plan §4.2): water follows streets
    road = landcover == ROAD
    world.dem = dem - road * cfg.hydro.road_burn_m
    world.outlet_mask[-1, :] = True

    # safe zones: the 3 highest intersections ("multi-storey car parks" in the toy world)
    by_height = sorted(G.nodes, key=lambda n: -world.dem.ravel()[G.nodes[n]["cell"]])
    for k, n in enumerate(by_height[:3]):
        world.safe_zones.append({"id": k, "name": f"Toy Car Park {'ABC'[k]}", "x": G.nodes[n]["x"],
                                 "y": G.nodes[n]["y"], "node": n, "kind": "multi-storey (synthetic)"})

    world.drains, world.cell_node = build_drains(world, cfg)
    world.meta = {"description": "Synthetic 50x50 toy world (Phase 2)"}
    return world
