"""Ultrasonic water-level sensor at a drain node, culvert, underpass or ramp.

The reported level (metres above the drain invert) is the drain fill times the drain depth while the
drain has room, then drain depth + surface water depth once it surcharges onto the road. Critical
level for a street is therefore drain_depth + car_float_m.
"""
from __future__ import annotations

from collections import deque

import mesa
import numpy as np

from ffsa.abm.predictor import ls_slope


class SensorAgent(mesa.Agent):
    def __init__(self, model, idx: int, node: int):
        super().__init__(model)
        self.idx = idx
        self.node = node
        self.cell = int(model.world.drains.cell[node])
        cfg = model.cfg
        self.drain_depth = cfg.hydro.drain_depth_m
        self.interval = cfg.sensors.report_interval_min
        self.sigma = cfg.sensors.noise_sigma_m
        self.p_dropout = cfg.sensors.p_dropout
        self.window = cfg.thresholds.rate_window_min
        self.buffer: deque[tuple[int, float]] = deque()
        self.blocked = model.rng.random() < cfg.sensors.p_blocked
        self.stuck_value: float | None = None
        self.phase = int(model.rng.integers(self.interval))  # sensors don't all report on the same minute
        self.level = np.nan
        self.slope = np.nan

    def true_level(self, t: int) -> float:
        frac = float(self.model.water.drain_level[t, self.node])
        if frac < 0.999:
            return frac * self.drain_depth
        return self.drain_depth + float(self.model.depth_flat[t, self.cell])

    def step(self):
        t = self.model.t
        if (t + self.phase) % self.interval:
            return
        rng = self.model.rng
        if rng.random() < self.p_dropout:
            reading = np.nan
        elif self.blocked:
            if self.stuck_value is None:
                self.stuck_value = self.true_level(t)
            reading = self.stuck_value
        else:
            reading = max(0.0, self.true_level(t) + rng.normal(0, self.sigma))
        self.buffer.append((t, reading))
        while self.buffer and self.buffer[0][0] <= t - self.window:
            self.buffer.popleft()
        if not np.isnan(reading):
            self.level = reading
        ts, vs = zip(*self.buffer)
        self.slope = ls_slope(ts, vs)

    @property
    def fill(self) -> float:
        return min(1.0, self.level / self.drain_depth) if not np.isnan(self.level) else np.nan
