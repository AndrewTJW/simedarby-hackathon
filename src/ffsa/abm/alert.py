"""Alert system: one agent per model, implementing scenarios S0-S3.

S0  no alerts.
S1  township-wide broadcast from a virtual river gauge (fill of the outlet drain node), with a 15-min publishing
    cycle, a WhatsApp-chain dissemination delay per street, and 56% reach. Generic message.
S2  street sensors, fixed threshold: ACT when a serving sensor is more than X% full.
S3  street sensors + rate of rise: ACT when predicted TTF < 30 min, confirmed by a second rising
    sensor or by rainfall above a threshold. Message names the nearest safe car park and minutes left.
S2 and S3 share WATCH / AVOID / ALL CLEAR logic and the per-street state machine.
"""
from __future__ import annotations

import math

import mesa
import networkx as nx
import numpy as np

from ffsa.abm.alert_fsm import Level, StreetAlertFSM
from ffsa.abm.predictor import time_to_flood

SCENARIOS = ("S0", "S1", "S2", "S3")

# BM wording must be checked by a Malay-speaking teammate (see docs/OPEN_QUESTIONS.md).
TEXT = {
    Level.WATCH: (
        "Heavy rain and drain levels rising on {street}. Be ready to move your car.",
        "Hujan lebat dan paras longkang meningkat di {street}. Bersedia untuk mengalihkan kereta anda.",
    ),
    Level.ACT: (
        "Move your car to {safe} now. About {mins} minutes until flooding on {street}.",
        "Alihkan kereta anda ke {safe} sekarang. Kira-kira {mins} minit lagi sebelum {street} banjir.",
    ),
    "ACT_NO_TTF": (
        "Move your car to {safe} now. {street} is expected to flood.",
        "Alihkan kereta anda ke {safe} sekarang. {street} dijangka banjir.",
    ),
    "ACT_GENERIC": (
        "Flood warning for the area. Move vehicles to higher ground.",
        "Amaran banjir untuk kawasan ini. Alihkan kenderaan ke kawasan tinggi.",
    ),
    Level.AVOID: (
        "{street} is flooded. Do not drive through. Use {safe} via another route.",
        "{street} dinaiki air. Jangan memandu melaluinya. Gunakan laluan lain ke {safe}.",
    ),
    Level.ALL_CLEAR: (
        "Water has receded on {street}.",
        "Air telah surut di {street}.",
    ),
}


class AlertSystemAgent(mesa.Agent):
    def __init__(self, model, scenario: str, serve: list[list[int]]):
        super().__init__(model)
        if scenario not in SCENARIOS:
            raise ValueError(scenario)
        self.scenario = scenario
        cfg = model.cfg
        self.th = cfg.thresholds
        self.s1 = cfg.scenario_s1
        self.serve = serve
        self.critical = cfg.hydro.drain_depth_m + self.th.car_float_m
        self.avoid_level = cfg.hydro.drain_depth_m + self.th.avoid_m
        nS = len(model.world.streets)
        self.fsm = [StreetAlertFSM(self.th.min_hold_min, self.th.all_clear_falling_min) for _ in range(nS)]
        self.falling = np.zeros(nS)
        self.first_act = np.full(nS, np.nan)
        self.sensor_ttf = np.full(len(model.sensors), np.inf)
        self.events: list[dict] = []
        self.n_delivered = 0
        self.street_safe = self._nearest_safe_per_street()
        # S1 state
        self.gauge_node = self._gauge_node()
        self.s1_publish_t: int | None = None
        self.s1_street_t = np.full(nS, np.nan)

    # --- setup helpers -------------------------------------------------------------------------
    def _nearest_safe_per_street(self) -> list[dict]:
        w = self.model.world
        lengths = {s["node"]: nx.single_source_dijkstra_path_length(w.graph, s["node"], weight="length") for s in w.safe_zones}
        edges = w.edge_by_eid()
        out = []
        for st in w.streets:
            ends = {n for e in st["eids"] for n in edges[e][:2]}
            best = min(w.safe_zones, key=lambda s: min(lengths[s["node"]].get(n, math.inf) for n in ends))
            out.append(best)
        return out

    def _gauge_node(self) -> int:
        """Virtual river gauge: the drain node leaving the domain with the largest upstream area. It
        integrates the whole township's runoff, like a river station downstream of it."""
        d = self.model.world.drains
        outs = np.flatnonzero(d.downstream < 0)
        return int(outs[np.argmax(d.upstream_cells[outs])])

    # --- messaging -----------------------------------------------------------------------------
    def _send(self, street: int, level, recipients: list, mins: float | None = None, generic: bool = False):
        t = self.model.t
        name = self.model.world.streets[street]["name"] if street >= 0 else "the township"
        safe = self.street_safe[street]["name"] if street >= 0 else ""
        if level == Level.ACT and generic:
            key = "ACT_GENERIC"
        elif level == Level.ACT and (mins is None or not math.isfinite(mins)):
            key = "ACT_NO_TTF"
        else:
            key = level
        m = None if mins is None or not math.isfinite(mins) else max(1, int(round(mins)))
        en, bm = (s.format(street=name, safe=safe, mins=m) for s in TEXT[key])
        self.events.append({"t": t, "street": street, "street_name": name, "level": Level(level).name,
                            "n_recipients": len(recipients), "minutes": m, "safe_zone": safe,
                            "text_en": en, "text_bm": bm})
        self.n_delivered += len(recipients)
        for r in recipients:
            r.receive(Level(level), generic=generic, safe=self.street_safe[street] if street >= 0 else None)

    # --- per-tick logic ------------------------------------------------------------------------
    def step(self):
        m = self.model
        t = m.t
        rain = m.rain(t)
        sensors = m.sensors
        for k, s in enumerate(sensors):
            self.sensor_ttf[k] = time_to_flood(s.level if not np.isnan(s.level) else 0.0, self.critical, s.slope,
                                               rain, self.th.heavy_rain_mm_hr, self.th.heavy_rain_rate_multiplier)
        if self.scenario == "S1":
            self._step_s1(t)
        elif self.scenario in ("S2", "S3"):
            self._step_sensors(t, rain)

    def _step_s1(self, t: int):
        m = self.model
        if self.s1_publish_t is None and m.water.drain_level[t, self.gauge_node] >= self.s1.gauge_threshold_frac:
            P = self.s1.publish_interval_min
            self.s1_publish_t = int(math.ceil((t + 1) / P) * P)
            lo, hi = self.s1.dissemination_delay_min
            self.s1_street_t = self.s1_publish_t + np.round(m.rng.uniform(lo, hi, len(self.fsm)))
        if self.s1_publish_t is None:
            return
        for sid in np.flatnonzero(self.s1_street_t == t):
            residents = [r for r in m.residents_by_street.get(int(sid), []) if r.s1_reached]
            self.first_act[sid] = t
            self.fsm[sid].level = Level.ACT
            self._send(int(sid), Level.ACT, residents, generic=True)

    def _step_sensors(self, t: int, rain: float):
        m = self.model
        th = self.th
        sensors = m.sensors
        warning = m.storm.warning_min is not None and t >= m.storm.warning_min
        for sid, serving in enumerate(self.serve):
            if not serving:
                continue
            ss = [sensors[k] for k in serving]
            levels = np.array([s.level for s in ss])
            slopes = np.array([s.slope for s in ss])
            fills = np.array([s.fill for s in ss])
            valid = ~np.isnan(slopes)
            self.falling[sid] = self.falling[sid] + 1 if valid.any() and (slopes[valid] < 0).all() else 0

            proposed = Level.NONE
            if warning or np.any((fills > th.watch_drain_frac) & (slopes > th.watch_rate_m_per_min)):
                proposed = Level.WATCH
            ttf = min(self.sensor_ttf[k] for k in serving)
            if self.scenario == "S2":
                if np.nanmax(np.append(fills, -1)) > th.s2_fixed_threshold:
                    proposed = Level.ACT
            else:
                k_best = serving[int(np.argmin([self.sensor_ttf[k] for k in serving]))]
                others_rising = any(sensors[k].slope > th.rising_confirm_m_per_min for k in serving if k != k_best)
                if ttf < th.act_ttf_min and (others_rising or rain > th.rain_confirm_mm_hr):
                    proposed = Level.ACT
            if np.nanmax(np.append(levels, -1)) >= self.avoid_level:
                proposed = Level.AVOID

            for lvl in self.fsm[sid].update(t, proposed, self.falling[sid]):
                if lvl == Level.ACT and np.isnan(self.first_act[sid]):
                    self.first_act[sid] = t
                self._send(sid, lvl, m.residents_by_street.get(sid, []),
                           mins=ttf if self.scenario == "S3" else None)
