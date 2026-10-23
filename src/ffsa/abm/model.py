"""FloodModel: replays cached water and simulates sensors, the alert system and residents (Mesa 3)."""
from __future__ import annotations

import math
from datetime import datetime

import mesa
import networkx as nx
import numpy as np

from ffsa import metrics
from ffsa.abm.alert import AlertSystemAgent
from ffsa.abm.alert_fsm import Level
from ffsa.abm.placement import place_sensors, serving_sensors
from ffsa.abm.resident import ResidentAgent
from ffsa.abm.sensor import SensorAgent
from ffsa.config import Config
from ffsa.data.rainfall import Storm
from ffsa.hydro.simulate import Water
from ffsa.world import World


class FloodModel(mesa.Model):
    def __init__(self, world: World, water: Water, storm: Storm, cfg: Config, scenario: str, seed: int,
                 record: bool = False):
        super().__init__(seed=seed)
        self.world, self.water, self.storm, self.cfg = world, water, storm, cfg
        self.scenario = scenario
        self.seed = seed
        self.record = record
        self.compliance = cfg.residents.compliance
        self.T = water.depth.shape[0]
        self.depth_flat = water.depth.reshape(self.T, -1)
        self.max_depth_flat = self.depth_flat.max(axis=0).astype(np.float32)
        self.t = 0
        self.safe_nodes = {s["node"] for s in world.safe_zones}
        self._route_cache: dict[bytes, dict] = {}
        self._blocked_key = b""
        self._blocked_key_alerted = b""
        self._edges = world.edge_by_eid()
        self._edge_geom: dict[int, tuple] = {}

        # sensors (placement is deterministic except for the random strategy)
        sc = cfg.sensors
        nodes = place_sensors(world, sc.n_sensors, sc.placement, self.rng, sc.min_spacing_m, sc.low_point_window_m)
        self.sensors = [SensorAgent(self, k, n) for k, n in enumerate(nodes)]
        self.serve = serving_sensors(world, nodes, sc.max_serve_distance_m, sc.same_elevation_tol_m)

        # residents: cars per building, sampled down to max_cars
        self.residents = self._make_residents()
        self.residents_by_street: dict[int, list[ResidentAgent]] = {}
        for r in self.residents:
            self.residents_by_street.setdefault(r.street, []).append(r)

        self.alerts = AlertSystemAgent(self, scenario, self.serve)
        self._park_cells = np.array([r.park_cell for r in self.residents], dtype=np.int64)
        self._wake_depth = min(cfg.residents.self_notice_depth_m, cfg.thresholds.car_float_m)
        self.timeline: list[dict] = []

    # --- setup ---------------------------------------------------------------------------------
    def _make_residents(self) -> list[ResidentAgent]:
        rc = self.cfg.residents
        rng = self.rng
        cars = []
        for b in self.world.buildings:
            hh = rc.households_per_apartment if b["kind"] == "apartments" else 1
            mean = hh * rc.cars_per_household
            n = int(mean) + int(rng.random() < mean - int(mean))
            cars.extend([b] * n)
        self.n_cars_total = len(cars)
        if len(cars) > rc.max_cars:
            idx = rng.choice(len(cars), size=rc.max_cars, replace=False)
            cars = [cars[i] for i in sorted(idx)]
        self.car_scale = self.n_cars_total / max(1, len(cars))
        hour = datetime.fromisoformat(self.cfg.sim.storm_start_local).hour
        p_sleep, p_away = rc.p_asleep_by_hour[hour], rc.p_away_by_hour[hour]
        out = []
        for b in cars:
            u = rng.random()
            state = "asleep" if u < p_sleep else ("away" if u < p_sleep + p_away else "home_awake")
            out.append(ResidentAgent(self, b, state))
        return out

    # --- helpers used by agents ----------------------------------------------------------------
    def rain(self, t: int) -> float:
        s = self.storm.intensity_mm_hr
        return float(s[t]) if t < len(s) else 0.0

    def route_to_safe(self, node, alerted: bool = False) -> tuple[list | None, bool]:
        """Shortest passable path from node to the nearest safe zone, or None. Cached per blocked-edge set.

        Alerted drivers avoid roads with >= avoid_m (as the AVOID message tells them) and fall back to the
        car_float_m rule only when no such route exists. Returns (path, avoids_avoid_m)."""
        if alerted:
            path = self._route(node, self._blocked_key_alerted)
            if path is not None:
                return path, True
        return self._route(node, self._blocked_key), False

    def _route(self, node, key: bytes) -> list | None:
        if key not in self._route_cache:
            blocked = np.flatnonzero(np.frombuffer(key, dtype=bool)) if key else []
            G = nx.restricted_view(self.world.graph, [], [self._edges[e][:2] for e in blocked])
            _, paths = nx.multi_source_dijkstra(G, self.safe_nodes, weight="length")
            self._route_cache[key] = paths
        p = self._route_cache[key].get(node)
        return None if p is None else p[::-1]

    def point_on_edge(self, eid: int, from_node, dist: float) -> tuple[float, float]:
        """(x, y) at `dist` metres along edge `eid`, travelling away from `from_node`."""
        if eid not in self._edge_geom:
            u, _, d = self._edges[eid]
            pts = np.asarray(d["coords"], dtype=float)
            nu = self.world.graph.nodes[u]
            if np.hypot(pts[0, 0] - nu["x"], pts[0, 1] - nu["y"]) > np.hypot(pts[-1, 0] - nu["x"], pts[-1, 1] - nu["y"]):
                pts = pts[::-1]  # make coords run from u
            cum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
            self._edge_geom[eid] = (u, pts, cum)
        u, pts, cum = self._edge_geom[eid]
        if from_node != u:
            dist = cum[-1] - dist
        f = np.clip(dist / max(cum[-1], 1e-9), 0, 1) * cum[-1]
        return float(np.interp(f, cum, pts[:, 0])), float(np.interp(f, cum, pts[:, 1]))

    # --- simulation ----------------------------------------------------------------------------
    def step(self):
        t = self.t
        self._blocked_key = (self.water.edge_depth[t] >= self.cfg.thresholds.car_float_m).tobytes()
        self._blocked_key_alerted = (self.water.edge_depth[t] >= self.cfg.thresholds.avoid_m).tobytes()
        for s in self.sensors:
            s.step()
        self.alerts.step()
        # only residents who can do something this tick: busy ones, or home with water at the door
        busy = [r for r in self.residents if r.status in ("waiting", "driving", "stranded")]
        wet = np.flatnonzero(self.depth_flat[t, self._park_cells] >= self._wake_depth)
        active = busy + [self.residents[i] for i in wet if self.residents[i].status == "home"]
        for k in self.rng.permutation(len(active)):
            active[k].step()
        if self.record:
            self._record(t)
        self.t += 1

    def run(self) -> dict:
        while self.t < self.T:
            self.step()
        return self.results()

    def _record(self, t: int):
        res = self.residents
        self.timeline.append({
            "t": t,
            "rain": round(self.rain(t), 2),
            "sensor_level": [None if np.isnan(s.level) else round(float(s.level), 3) for s in self.sensors],
            "sensor_ttf": [None if not math.isfinite(x) else round(float(x), 1) for x in self.alerts.sensor_ttf],
            "street_level": [int(f.level) for f in self.alerts.fsm],
            "cars_moved_at_risk": sum(1 for r in res if r.status == "safe" and r.at_risk),
            "cars_moved": sum(1 for r in res if r.status == "safe"),
            "cars_flooded": sum(1 for r in res if r.status == "flooded"),
            "presses": sum(1 for r in res if r.pressed),
            "streets_act": sum(1 for f in self.alerts.fsm if f.level in (Level.ACT, Level.AVOID)),
        })

    def results(self) -> dict:
        th = self.cfg.thresholds
        t_flood = metrics.first_crossing(self.water.street_depth, th.car_float_m)
        lead, missed = metrics.lead_times(t_flood, self.alerts.first_act)
        outcomes = [r.final_outcome() for r in self.residents]
        at_risk = np.array([r.at_risk for r in self.residents])
        flooded = np.array([o.startswith("flooded") for o in outcomes])
        per_car = self.cfg.damage.per_car_rm or 0.0
        act_alerted = ~np.isnan(self.alerts.first_act)
        out = {
            "scenario": self.scenario,
            "seed": self.seed,
            "n_sensors": len(self.sensors),
            "compliance": self.compliance,
            **metrics.summarize_lead(lead, missed, t_flood),
            **metrics.vehicle_summary(outcomes, at_risk, np.array([r.pressed for r in self.residents])),
            "car_scale": self.car_scale,
            "damage_rm": metrics.car_damage_rm(flooded, per_car) * self.car_scale,
            "damage_no_action_rm": metrics.car_damage_rm(at_risk, per_car) * self.car_scale,
            "false_alarm_rate": metrics.false_alarm_rate(act_alerted, ~np.isnan(t_flood)),
            "msgs_per_resident": self.alerts.n_delivered / max(1, len(self.residents)),
            "n_streets_unserved": sum(1 for s in self.serve if not s),
        }
        out["rm_avoided_vs_no_action"] = out["damage_no_action_rm"] - out["damage_rm"]
        self.street_lead = lead
        self.street_t_flood = t_flood
        self.car_outcomes = outcomes
        return out
