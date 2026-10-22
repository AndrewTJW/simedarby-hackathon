import math

import numpy as np
import pytest

from ffsa.abm.alert_fsm import Level, StreetAlertFSM
from ffsa.abm.predictor import ls_slope, time_to_flood
from ffsa.hydro.runoff import rational_Q, runoff_volume
from ffsa import metrics


# --- rational method -------------------------------------------------------------------------
def test_rational_q_units():
    # 1 ha, C=1, 360 mm/hr -> 1 m^3/s (by construction of the 1/360 factor)
    assert rational_Q(1.0, 360.0, 1.0) == pytest.approx(1.0)
    # equals C * i[m/s] * A[m^2]
    C, i, A_m2 = 0.7, 120.0, 900.0
    assert rational_Q(C, i, A_m2 / 1e4) == pytest.approx(C * i / 1000 / 3600 * A_m2)


def test_runoff_volume_one_minute():
    # 30 m cell, 60 mm/hr for 60 s, C = 0.5 -> 0.5 * 1 mm * 900 m^2 = 0.45 m^3
    assert runoff_volume(0.5, 60.0, 900.0, 60.0) == pytest.approx(0.45)


# --- TTF predictor -----------------------------------------------------------------------------
def test_ls_slope_uses_all_points():
    t = np.arange(10)
    v = 0.02 * t + np.array([0, .01, -.01, 0, .01, -.01, 0, .01, -.01, 0])
    assert ls_slope(t, v) == pytest.approx(0.02, abs=2e-3)
    assert math.isnan(ls_slope([1], [1.0]))
    assert ls_slope([0, 1, 2], [0.0, np.nan, 2.0]) == pytest.approx(1.0)


@pytest.mark.parametrize("rate", [0.0, -0.01, float("nan"), None])
def test_ttf_not_rising_is_inf(rate):
    assert time_to_flood(0.5, 1.3, rate) == math.inf


def test_ttf_basic_and_rain_multiplier():
    assert time_to_flood(1.0, 1.3, 0.01) == pytest.approx(30)
    assert time_to_flood(1.0, 1.3, 0.01, rain_mm_hr=80, heavy_rain_mm_hr=50, multiplier=1.5) == pytest.approx(20)
    assert time_to_flood(1.4, 1.3, -1) == 0.0


# --- alert state machine -----------------------------------------------------------------------
def fsm():
    return StreetAlertFSM(min_hold_min=10, all_clear_falling_min=30)


def test_escalation_and_first_act():
    f = fsm()
    assert f.update(0, Level.WATCH, 0) == [Level.WATCH]
    assert f.update(5, Level.ACT, 0) == [Level.ACT]
    assert f.first_act_t == 5
    assert f.update(6, Level.AVOID, 0) == [Level.AVOID]


def test_jump_to_avoid_emits_act():
    f = fsm()
    assert f.update(3, Level.AVOID, 0) == [Level.ACT, Level.AVOID]
    assert f.first_act_t == 3


def test_no_flapping():
    f = fsm()
    f.update(0, Level.ACT, 0)
    # conditions oscillate: no downgrade, no repeated messages
    for t in range(1, 40):
        assert f.update(t, Level.WATCH if t % 2 else Level.ACT, falling_for_min=0) == []
    assert f.level == Level.ACT


def test_all_clear_needs_falling_and_hold():
    f = fsm()
    f.update(0, Level.AVOID, 0)
    assert f.update(5, Level.NONE, falling_for_min=30) == []          # hold not met
    assert f.update(20, Level.NONE, falling_for_min=29) == []         # not falling long enough
    assert f.update(21, Level.NONE, falling_for_min=30) == [Level.ALL_CLEAR]
    assert f.update(25, Level.ACT, 0) == []                           # hold after ALL_CLEAR
    assert f.update(31, Level.ACT, 0) == [Level.ACT]                  # second wave
    assert f.first_act_t == 0


# --- metrics -----------------------------------------------------------------------------------
def test_first_crossing():
    x = np.array([[0, 0, 0], [0.1, 0.4, 0], [0.35, 0.5, 0]])
    t = metrics.first_crossing(x, 0.3)
    assert t[0] == 2 and t[1] == 1 and np.isnan(t[2])


def test_lead_time_and_missed():
    t_flood = np.array([60, 60, 60, np.nan])
    t_act = np.array([20, np.nan, 70, 10])
    lead, missed = metrics.lead_times(t_flood, t_act)
    assert lead[0] == 40 and np.isnan(lead[1]) and lead[2] == -10 and np.isnan(lead[3])
    assert missed.tolist() == [False, True, True, False]
    s = metrics.summarize_lead(lead, missed, t_flood)
    assert s["n_streets_flooded"] == 3 and s["n_streets_missed"] == 2
    assert s["share_lead_ge30"] == pytest.approx(1 / 3)


def test_false_alarm_and_vehicles():
    assert metrics.false_alarm_rate([1, 1, 0, 1], [1, 0, 1, 0]) == pytest.approx(2 / 3)
    v = metrics.vehicle_summary(["moved_safe", "flooded_parked", "moved_safe", "never_at_risk"], [1, 1, 0, 0])
    assert v["pct_moved"] == 0.5 and v["n_cars_at_risk"] == 2
    assert metrics.car_damage_rm([1, 0, 1], 100.0) == 200.0
