"""Deterministic, declared projection dynamics for the science workflows."""

from __future__ import annotations

import math
from typing import Any


def amplification_series(
    wells: dict[str, dict[str, Any]], *, cycles: int = 40
) -> dict[str, list[float]]:
    """Return deterministic qPCR-shaped fluorescence, not a vendor simulator."""

    series: dict[str, list[float]] = {}
    for well, config in wells.items():
        ct = config["ct"]
        values: list[float] = []
        for cycle in range(1, cycles + 1):
            baseline = 95.0 + cycle * 0.35
            if ct is None:
                value = baseline
            else:
                value = baseline + 12_000.0 / (1.0 + math.exp(-(cycle - float(ct)) / 1.7))
            values.append(round(value, 2))
        series[well] = values
    return series


def growth_od600(*, time_s: float, replicate_index: int) -> float:
    """Return a deterministic microbial growth-shaped OD600 observation."""

    hours = max(0.0, time_s / 3600.0)
    carrying_capacity = 1.18 + replicate_index * 0.008
    baseline = 0.075 + replicate_index * 0.0015
    growth = carrying_capacity / (1.0 + math.exp(-0.82 * (hours - 4.3)))
    initial = carrying_capacity / (1.0 + math.exp(0.82 * 4.3))
    return round(baseline + growth - initial, 4)


def ramp_temperature(
    *, current_c: float, target_c: float, seconds: float, rate_c_per_s: float
) -> float:
    delta = target_c - current_c
    movement = min(abs(delta), seconds * rate_c_per_s)
    if delta < 0:
        movement = -movement
    return round(current_c + movement, 4)


def powder_delivery(*, requested_mg: float, pulse_index: int) -> float:
    """Return deterministic pulse delivery with a declared, non-vendor error model."""

    factors = (0.986, 0.997, 1.003, 0.999)
    return round(max(0.0, requested_mg * factors[(pulse_index - 1) % len(factors)]), 3)


def balance_noise_g(*, read_index: int) -> float:
    offsets = (0.0000, 0.0001, -0.0001, 0.0000)
    return offsets[(read_index - 1) % len(offsets)]

