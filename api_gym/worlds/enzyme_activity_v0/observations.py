"""Explicit agent-visible projections; latent model parameters never enter them."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


def public_experiment_observation(
    *,
    logical_time_s: float,
    inventory: Mapping[str, Any],
    plate_id: str,
    plate_revision: int,
    plate_location: str,
    operator_requests: tuple[Mapping[str, Any], ...] = (),
    reader_jobs: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    """Build the complete public envelope from already observable records."""

    return {
        "schema_version": "enzyme_activity_observation_v0",
        "logical_time_s": float(logical_time_s),
        "inventory": deepcopy(dict(inventory)),
        "plate": {
            "plate_id": plate_id,
            "revision": plate_revision,
            "location": plate_location,
        },
        "operator_requests": [deepcopy(dict(item)) for item in operator_requests],
        "reader_jobs": [deepcopy(dict(item)) for item in reader_jobs],
        "claim": "Modeled observations; not physical reader captures.",
    }
