import time

import networkx as nx
import numpy as np
import pytest

from ffsa.config import load_config
from ffsa.data.rainfall import Storm, load_storm
from ffsa.data.toy import build_toy_world
from ffsa.hydro.drains import build_drains
from ffsa.hydro.simulate import simulate
from ffsa.world import ROAD, RESIDENTIAL, World, cells_along


@pytest.fixture(scope="module")
def cfg():
    return load_config(allow_placeholders=True)[0]


def storm(minutes, mm_hr, T):
    s = np.zeros(T)
    s[:minutes] = mm_hr
    return Storm("test", s, True, "test", None)


def bowl_world(cfg, n=30, cell=30.0):
    """Flat-sided bowl with its lowest point at the centre and one road across it; no outlet."""
    r, c = np.mgrid[0:n, 0:n]
    dem = 0.002 * ((r - n / 2) ** 2 + (c - n / 2) ** 2)
    lc = np.full((n, n), RESIDENTIAL, dtype=np.int8)
    G = nx.Graph()
    w = World("bowl", True, cell, "LOCAL", 0.0, n * cell, dem, lc, np.zeros((n, n), bool), G, [], [], [],
              {"mode": "local", "lon0": 101.0, "lat0": 3.0})
    a, b = (2 * cell, (n - 15.5) * cell), ((n - 2) * cell, (n - 15.5) * cell)
    G.add_node(0, x=a[0], y=a[1], cell=0)
    G.add_node(1, x=b[0], y=b[1], cell=0)
    cells = cells_along(w, [a, b])
    G.add_edge(0, 1, eid=0, street=0, length=b[0] - a[0], cells=cells, coords=[a, b], name="x")
    lc.ravel()[cells] = ROAD
    w.streets = [{"id": 0, "name": "x", "cells": cells, "eids": [0]}]
    w.drains, w.cell_node = build_drains(w, cfg)
    return w


def test_mass_balance_toy(cfg):
    w = build_toy_world(cfg)
    s = load_storm("toy_storm", cfg.sim.duration_minutes)
    water = simulate(w, s, cfg)
    assert abs(water.mass["balance_error"]) < 0.01
    assert water.depth.min() >= 0
    assert np.all(water.drain_level >= 0) and np.all(water.drain_level <= 1 + 1e-6)


def with_(cfg, section, **kw):
    return cfg.model_copy(update={section: getattr(cfg, section).model_copy(update=kw)})


def test_bowl_fills_lowest_point_first(cfg):
    T = 60
    # near-zero drain capacity so the surface scheme alone decides where water collects
    cfg = with_(with_(cfg, "hydro", drain_capacity_factor=1e-6), "sim", duration_minutes=T)
    w = bowl_world(cfg)
    water = simulate(w, storm(30, 200.0, T), cfg)
    assert abs(water.mass["balance_error"]) < 0.01
    d = water.depth[-1].astype(float)
    centre = d[14:17, 14:17].mean()
    rim = np.concatenate([d[0], d[-1], d[:, 0], d[:, -1]]).mean()
    assert centre > 0.05 and centre > 5 * rim
    first_wet = np.argmax(water.depth.reshape(T, -1) > 0.02, axis=0)
    wet_ever = (water.depth > 0.02).any(axis=0).ravel()
    lowest = np.argmin(w.dem.ravel())
    assert wet_ever[lowest] and first_wet[lowest] == first_wet[wet_ever].min()


def test_speed_6h_storm_130x130(cfg):
    n = 130
    r, c = np.mgrid[0:n, 0:n]
    dem = 10 - 0.05 * r + 0.3 * np.sin(c / 7.0)
    lc = np.full((n, n), RESIDENTIAL, dtype=np.int8)
    G = nx.Graph()
    w = World("speed", True, 30.0, "LOCAL", 0.0, n * 30.0, dem, lc, np.zeros((n, n), bool), G, [], [], [],
              {"mode": "local", "lon0": 101.0, "lat0": 3.0})
    w.outlet_mask[-1, :] = True
    for k, row in enumerate(range(5, n, 10)):
        a, b = (15.0, (n - row - 0.5) * 30.0), ((n - 0.5) * 30.0, (n - row - 0.5) * 30.0)
        G.add_node(("a", k), x=a[0], y=a[1], cell=0)
        G.add_node(("b", k), x=b[0], y=b[1], cell=0)
        G.add_edge(("a", k), ("b", k), eid=k, street=k, length=b[0] - a[0], cells=cells_along(w, [a, b]), coords=[a, b])
    w.drains, w.cell_node = build_drains(w, cfg)
    t0 = time.time()
    simulate(w, storm(180, 80.0, 360), with_(cfg, "sim", duration_minutes=360))
    assert time.time() - t0 < 30
