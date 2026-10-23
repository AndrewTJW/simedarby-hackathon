import numpy as np
import pytest

from ffsa.config import load_config
from ffsa.experiments.run_one import prepare, run_one


@pytest.fixture(scope="module")
def toy():
    cfg = load_config(allow_placeholders=True)[0]
    return (cfg, *prepare("toy", "toy_storm", cfg))


@pytest.fixture(scope="module")
def results(toy):
    cfg, world, storm, water = toy
    return {sc: run_one(world, storm, water, cfg, sc, seed=3)[1] for sc in ("S0", "S1", "S2", "S3")}


def test_toy_world_floods_some_streets(results):
    assert 0 < results["S0"]["n_streets_flooded"] < 60


def test_s0_sends_nothing(results):
    assert results["S0"]["msgs_per_resident"] == 0
    assert results["S0"]["n_streets_missed"] == results["S0"]["n_streets_flooded"]


def test_lead_time_ordering(results):
    """Phase 2 done-criterion: S3 lead time > S2 > S1 in the toy world."""
    lead = {k: (v["lead_median_min"] if not np.isnan(v["lead_median_min"]) else -np.inf) for k, v in results.items()}
    assert lead["S3"] > lead["S2"] > lead["S1"]


def test_outcomes_consistent(toy):
    cfg, world, storm, water = toy
    model, res = run_one(world, storm, water, cfg, "S3", seed=5)
    for r in model.residents:
        o = r.final_outcome()
        if o == "never_at_risk":
            assert not r.at_risk
        if o == "flooded_parked":
            assert r.at_risk
    assert res["n_moved_safe_at_risk"] <= res["n_cars_at_risk"]


def test_reproducible(toy):
    cfg, world, storm, water = toy
    a = run_one(world, storm, water, cfg, "S3", seed=9)[1]
    b = run_one(world, storm, water, cfg, "S3", seed=9)[1]
    assert a == b


def test_alerted_drivers_route_around_avoid_roads(toy):
    """Street-alerted drivers prefer routes with no road >= avoid_m; unalerted ones only avoid >= car_float_m."""
    cfg, world, storm, water = toy
    model = run_one(world, storm, water, cfg, "S2", seed=1)[0]
    th = cfg.thresholds
    t = int(np.argmax((water.edge_depth >= th.avoid_m).sum(axis=1)))  # tick with most roads at AVOID depth
    model._blocked_key = (water.edge_depth[t] >= th.car_float_m).tobytes()
    model._blocked_key_alerted = (water.edge_depth[t] >= th.avoid_m).tobytes()
    eid = {(u, v): d["eid"] for u, v, d in world.graph.edges(data=True)}
    for node in list(world.graph.nodes)[::7]:
        path, strict = model.route_to_safe(node, alerted=True)
        if path is None:
            continue
        depths = [water.edge_depth[t, eid.get((a, b), eid.get((b, a)))] for a, b in zip(path, path[1:])]
        assert all(d < (th.avoid_m if strict else th.car_float_m) for d in depths)
        assert model.route_to_safe(node, alerted=False)[0] is not None
