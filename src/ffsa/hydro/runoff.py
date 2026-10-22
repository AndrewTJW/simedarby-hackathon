"""MSMA rational method."""
from __future__ import annotations

import numpy as np


def rational_Q(C, i_mm_hr, A_ha):
    """Peak runoff Q (m^3/s) = C * i * A / 360, with i in mm/hr and A in hectares (MSMA 2nd ed.)."""
    return np.asarray(C) * np.asarray(i_mm_hr) * np.asarray(A_ha) / 360.0


def runoff_volume(C, i_mm_hr, cell_area_m2: float, dt_s: float):
    """Rainfall-excess volume (m^3) produced by each cell over dt seconds."""
    return rational_Q(C, i_mm_hr, cell_area_m2 / 1e4) * dt_s
