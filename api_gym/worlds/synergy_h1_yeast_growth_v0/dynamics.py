"""Deterministic calibration dynamics; not a biological fidelity claim."""

from __future__ import annotations

import math


TEMPERATURE_RAMP_C_PER_S = 0.02


def current_temperature(
    *, start_c: float, target_c: float | None, set_at_s: float | None, now_s: float
) -> float:
    if target_c is None or set_at_s is None:
        return start_c
    elapsed = max(0.0, now_s - set_at_s)
    delta = target_c - start_c
    movement = min(abs(delta), elapsed * TEMPERATURE_RAMP_C_PER_S)
    if delta < 0:
        movement = -movement
    return round(start_c + movement, 3)


def od600_value(*, time_s: float, replicate_index: int) -> float:
    """Return a deterministic, synthetic growth-shaped observation."""
    midpoint_s = 8.0 * 3600.0 + replicate_index * 45.0
    value = 0.05 + 0.95 / (1.0 + math.exp(-(time_s - midpoint_s) / 4200.0))
    return round(value, 4)
