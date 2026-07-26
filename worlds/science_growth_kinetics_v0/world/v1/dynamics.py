from __future__ import annotations

import math


def growth_series(
    *,
    wells: list[str],
    seed: int,
    interval_seconds: int,
    duration_seconds: int,
) -> dict[str, list[float]]:
    """Generate the benchmark-defined OD600 projection for a completed read."""

    count = duration_seconds // interval_seconds + 1
    result: dict[str, list[float]] = {}
    for well_index, well in enumerate(wells):
        if well == "H12":
            result[well] = [0.03 for _ in range(count)]
            continue
        baseline = 0.035 + (seed % 5) * 0.001 + well_index * 0.0005
        amplitude = 0.78 + (seed % 3) * 0.015 + well_index * 0.004
        midpoint = 30000 + (well_index - 3) * 480
        rate = 0.00015
        result[well] = [
            round(
                baseline
                + amplitude / (1.0 + math.exp(-rate * (elapsed - midpoint))),
                5,
            )
            for elapsed in range(0, duration_seconds + 1, interval_seconds)
        ]
    return result
