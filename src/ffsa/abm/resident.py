"""Resident car owner. One agent per car."""
from __future__ import annotations

import math

import mesa
import numpy as np

from ffsa.abm.alert_fsm import Level


class ResidentAgent(mesa.Agent):
    def __init__(self, model, building: dict, state: str):
        super().__init__(model)
        cfg = model.cfg.residents
        self.rc = cfg
        self.building = building
        self.street = building["street"]
        self.home_node = building["node"]
        self.park_cell = building["cell"]
        self.state = state                      # asleep | home_awake | away
        self.status = "home"                    # home | waiting | driving | safe | flooded | stranded
        self.outcome: str | None = None
        self.at_risk = bool(model.max_depth_flat[self.park_cell] >= model.cfg.thresholds.car_float_m)
        self.s1_reached = model.rng.random() < model.cfg.scenario_s1.reach
        self.decided = False                    # has already decided whether to comply with an ACT
        self.street_alerted = False             # got a street-level message (S2/S3), so knows AVOID roads
        self.route_strict = False               # current route avoids roads with >= avoid_m
        self.depart_t: float | None = None
        self.path: list = []
        self.pos = 0
        self.progress = 0.0
        self.cur_eid: int | None = None
        self.cur_from = None                    # node the current edge was entered from
        self.trail: list[list[float]] = []
        self.pressed = False
        self.t_safe: float | None = None
        self.t_flooded: float | None = None
        self.n_msgs = 0

    # --- decisions -----------------------------------------------------------------------------
    def _delay(self) -> float:
        d = self.rc.response_delay_lognorm
        med = d.asleep_median_min if self.state == "asleep" else d.awake_median_min
        return float(self.model.rng.lognormal(math.log(med), d.sigma))

    def _schedule(self, extra: float = 0.0):
        if self.status == "home" and self.state != "away":
            self.status = "waiting"
            self.depart_t = self.model.t + self._delay() + extra

    def receive(self, level: Level, generic: bool = False, safe: dict | None = None):
        self.n_msgs += 1
        if not generic:
            self.street_alerted = True
        if level != Level.ACT or self.decided:
            return
        self.decided = True
        if self.model.rng.random() < self.model.compliance:
            self._schedule(self.rc.s1_search_delay_min if generic else 0.0)

    # --- movement ------------------------------------------------------------------------------
    def _xy(self, node) -> tuple[float, float]:
        n = self.model.world.graph.nodes[node]
        return n["x"], n["y"]

    def _start_driving(self, t: float):
        path, self.route_strict = self.model.route_to_safe(self.home_node, self.street_alerted)
        x, y = self.building["x"], self.building["y"]
        self.trail.append([x, y, t])
        if path is None:
            self.status = "stranded"
            return
        self.status = "driving"
        self.path, self.pos, self.progress = path, 0, 0.0
        self.trail.append([*self._xy(path[0]), t + 0.25])

    def _drive(self, t: int):
        m = self.model
        th = m.cfg.thresholds
        G = m.world.graph
        if self.progress > 0 and self._depth_here(t) >= th.car_float_m:
            self._flood(t, "flooded_en_route")
            return
        budget = 1.0
        while budget > 1e-9:
            node = self.path[self.pos]
            if node in m.safe_nodes:
                self.status, self.outcome, self.t_safe = "safe", "moved_safe", t + 1 - budget
                self.pressed = m.rng.random() < self.rc.p_button
                return
            nxt = self.path[self.pos + 1]
            e = G.edges[node, nxt]
            limit = th.avoid_m if self.route_strict else th.car_float_m
            if self.progress == 0 and m.water.edge_depth[t, e["eid"]] >= limit:
                path, self.route_strict = m.route_to_safe(node, self.street_alerted)
                if path is None:
                    self.status = "stranded"
                    self.park_cell = G.nodes[node]["cell"]
                    return
                self.path, self.pos = path, 0
                continue
            self.cur_eid, self.cur_from = e["eid"], node
            deep = m.water.edge_depth[t, e["eid"]] >= th.avoid_m
            speed = (self.rc.slow_speed_kmh if deep else self.rc.drive_speed_kmh) * 1000 / 60  # m/min
            remaining = e["length"] - self.progress
            if remaining / speed <= budget:
                budget -= remaining / speed
                self.progress = 0.0
                self.pos += 1
                self.trail.append([*self._xy(nxt), t + 1 - budget])
            else:
                self.progress += speed * budget
                budget = 0.0
                if self._depth_here(t) >= th.car_float_m:
                    self._flood(t, "flooded_en_route")

    def _depth_here(self, t: int) -> float:
        """Water depth at the car's position part-way along its current edge."""
        m = self.model
        x, y = m.point_on_edge(self.cur_eid, self.cur_from, self.progress)
        return float(m.depth_flat[t, int(m.world.xy_cell(x, y))])

    def _flood(self, t: int, outcome: str):
        self.status, self.outcome, self.t_flooded = "flooded", outcome, t

    def step(self):
        m = self.model
        t = m.t
        th = m.cfg.thresholds
        if self.status in ("safe", "flooded"):
            return
        if self.status in ("home", "waiting", "stranded"):
            if m.depth_flat[t, self.park_cell] >= th.car_float_m:
                self._flood(t, "flooded_en_route" if self.status == "stranded" else "flooded_parked")
                return
        if self.status == "home" and self.state == "home_awake" and m.depth_flat[t, self.park_cell] >= self.rc.self_notice_depth_m:
            self.decided = True
            self._schedule()
        if self.status == "waiting" and t >= self.depart_t:
            self._start_driving(float(self.depart_t))
        if self.status == "driving":
            self._drive(t)

    def final_outcome(self) -> str:
        if self.outcome:
            return self.outcome
        if self.status == "stranded":
            return "stranded_dry"
        return "not_moved_dry" if self.at_risk else "never_at_risk"
