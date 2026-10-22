"""Per-street alert state machine: NONE -> WATCH -> ACT -> AVOID -> ALL_CLEAR.

Rules (no flapping):
- Escalation happens immediately. Jumping straight to AVOID also emits ACT first, so lead time is
  always measured from an ACT.
- There is no partial de-escalation (AVOID never drops back to ACT). The only way down is ALL_CLEAR,
  after the water has been falling for `all_clear_falling_min` and the level has been held for
  `min_hold_min`.
- After ALL_CLEAR a street can re-escalate (a second wave) once `min_hold_min` has passed.
"""
from __future__ import annotations

from enum import IntEnum


class Level(IntEnum):
    NONE = 0
    WATCH = 1
    ACT = 2
    AVOID = 3
    ALL_CLEAR = 4


ACTIVE = (Level.WATCH, Level.ACT, Level.AVOID)


class StreetAlertFSM:
    def __init__(self, min_hold_min: int, all_clear_falling_min: int):
        self.min_hold = min_hold_min
        self.clear_after = all_clear_falling_min
        self.level = Level.NONE
        self.entered_t: float = -1e9
        self.first_act_t: float | None = None

    def _rank(self) -> int:
        return 0 if self.level == Level.ALL_CLEAR else int(self.level)

    def update(self, t: float, proposed: Level, falling_for_min: float) -> list[Level]:
        """Advance to time t given the level the current conditions call for. Returns emitted levels."""
        emitted: list[Level] = []
        held = t - self.entered_t >= self.min_hold
        if proposed > self._rank() and (self.level != Level.ALL_CLEAR or held):
            if proposed == Level.AVOID and self._rank() < Level.ACT:
                emitted.append(Level.ACT)
            emitted.append(proposed)
        elif self.level in ACTIVE and held and falling_for_min >= self.clear_after:
            emitted.append(Level.ALL_CLEAR)
        for lvl in emitted:
            self.level = lvl
            self.entered_t = t
            if lvl == Level.ACT and self.first_act_t is None:
                self.first_act_t = t
        return emitted
