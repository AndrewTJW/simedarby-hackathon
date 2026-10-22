"""Cellular surface-flow routing on the water-surface elevation (ground + depth).

Diffusive-wave style: the flux across each cell face follows Manning's equation driven by the
water-surface slope, using the depth available above the higher of the two beds. Two limiters keep
it stable and mass-conserving: a face never moves more than a quarter of the head difference, and a
cell never gives away more water than it holds.
"""
from __future__ import annotations

import numpy as np


def route_surface(h: np.ndarray, z: np.ndarray, dx: float, dt: float, n: float) -> np.ndarray:
    """Return the new depth after one sub-step (h, z in metres; dx in m; dt in s)."""
    A = dx * dx
    wse = z + h

    def face_flux(wa, wb, za, zb):
        dH = wa - wb
        hf = np.maximum(np.maximum(wa, wb) - np.maximum(za, zb), 0.0)
        q = (1.0 / n) * hf ** (5.0 / 3.0) * np.sqrt(np.abs(dH) / dx) * dx  # m^3/s across the face
        vol = np.minimum(q * dt, np.abs(dH) * A / 4.0)
        return np.sign(dH) * vol  # > 0 means a -> b

    fx = face_flux(wse[:, :-1], wse[:, 1:], z[:, :-1], z[:, 1:])  # (H, W-1) left -> right
    fy = face_flux(wse[:-1, :], wse[1:, :], z[:-1, :], z[1:, :])  # (H-1, W) top -> bottom

    out = np.zeros_like(h)
    out[:, :-1] += np.maximum(fx, 0)
    out[:, 1:] += np.maximum(-fx, 0)
    out[:-1, :] += np.maximum(fy, 0)
    out[1:, :] += np.maximum(-fy, 0)
    avail = h * A
    scale = np.where(out > avail, avail / np.where(out > 0, out, 1.0), 1.0)

    fx = np.where(fx > 0, fx * scale[:, :-1], fx * scale[:, 1:])
    fy = np.where(fy > 0, fy * scale[:-1, :], fy * scale[1:, :])

    dv = np.zeros_like(h)
    dv[:, :-1] -= fx
    dv[:, 1:] += fx
    dv[:-1, :] -= fy
    dv[1:, :] += fy
    return np.maximum(h + dv / A, 0.0)


def outlet_outflow(h: np.ndarray, outlet: np.ndarray, dx: float, dt: float) -> np.ndarray:
    """Volume (m^3) leaving each outlet cell this sub-step: critical-depth discharge, capped at storage."""
    q = np.sqrt(9.81 * h) * h * dx
    return np.where(outlet, np.minimum(q * dt, h * dx * dx), 0.0)
