"""Run one (world, storm, scenario, seed) and return the model and its metrics."""
from __future__ import annotations

import subprocess
from functools import lru_cache

from ffsa.abm.model import FloodModel
from ffsa.config import ROOT, Config
from ffsa.data.rainfall import Storm, load_storm
from ffsa.hydro.simulate import Water, get_water
from ffsa.world import World


@lru_cache(maxsize=1)
def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        return out.stdout.strip() or "uncommitted"
    except OSError:
        return "unknown"


def load_world(name: str, cfg: Config, rebuild: bool = False) -> World:
    """'toy' is built on the fly (cheap); real worlds come from `ffsa.cli data`."""
    if name == "toy":
        from ffsa.data.toy import build_toy_world

        return build_toy_world(cfg)
    world = World.load(name)
    if rebuild or world.drains is None:
        from ffsa.hydro.drains import build_drains

        world.drains, world.cell_node = build_drains(world, cfg)
    return world


def prepare(world_name: str, storm_name: str, cfg: Config) -> tuple[World, Storm, Water]:
    world = load_world(world_name, cfg)
    storm = load_storm(storm_name, cfg.sim.duration_minutes)
    return world, storm, get_water(world, storm, cfg)


def run_one(world: World, storm: Storm, water: Water, cfg: Config, scenario: str, seed: int,
            record: bool = False) -> tuple[FloodModel, dict]:
    model = FloodModel(world, water, storm, cfg, scenario, seed, record=record)
    res = model.run()
    res.update({"world": world.name, "storm": storm.name, "storm_synthetic": storm.synthetic,
                "config_hash": cfg.hash(), "git_commit": git_commit()})
    return model, res
