"""Seeded stochastic schedules for pylabrobot_lab_v0.

Provides deterministic noise and fault generation so that the same
(task_seed, readout_spec) always produces the same observation sequence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


NOISE_SCHEDULE_NAME = "noise_schedule.json"
FAULT_SCHEDULE_NAME = "fault_schedule.json"


# ── NoiseSchedule ───────────────────────────────────────────────────────────


@dataclass
class NoiseSchedule:
    """Pre-generated OD600 measurement noise, deterministic per seed.

    Each entry is keyed by "<plate_id>:<wavelength>:<well>:<readout_index>"
    and maps to a noise value sampled from N(0, sigma) clipped to [-clip, clip].

    ``source_status`` and ``attribution_label`` are metadata for the
    projection contract — they do not affect computation.
    """

    seed: int
    sigma: float = 0.03
    clip: float = 0.1
    noise_values: dict[str, float] = field(default_factory=dict)
    # Projection-contract metadata
    source_status: str = "assumption_for_calibration"
    attribution_label: str = "environment_noise"

    @staticmethod
    def generate(
        seed: int,
        readout_specs: list[dict[str, Any]],
        sigma: float = 0.03,
        clip: float = 0.1,
    ) -> "NoiseSchedule":
        """Pre-generate noise for every planned readout.

        *readout_specs* is a list of dicts, each with keys:
          plate_id, wavelength_nm, wells (list[str])

        A noise value is sampled for each (plate, wavelength, well, index)
        tuple, where *index* is the 1-based readout index for that plate+wavelength
        combination.
        """
        import random as _random

        rng = _random.Random(seed)
        schedule = NoiseSchedule(seed=seed, sigma=sigma, clip=clip)

        # Count how many times each (plate, wavelength) combination will be read
        counter: dict[str, int] = {}
        for spec in readout_specs:
            key = f"{spec['plate_id']}:{spec['wavelength_nm']}"
            counter[key] = counter.get(key, 0) + 1
            readout_idx = counter[key]
            for well in spec["wells"]:
                noise_key = f"{key}:{well}:{readout_idx}"
                # Box-Muller transform for normal distribution
                u1 = rng.random()
                u2 = rng.random()
                import math
                noise = sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
                noise = max(-clip, min(clip, noise))
                schedule.noise_values[noise_key] = noise

        return schedule

    def get_noise(
        self, plate_id: str, wavelength_nm: int, well: str, readout_index: int
    ) -> float:
        """Look up the pre-generated noise value, or 0.0 if not found."""
        key = f"{plate_id}:{wavelength_nm}:{well}:{readout_index}"
        return self.noise_values.get(key, 0.0)

    def save(self, path: Path) -> None:
        """Persist the noise schedule to JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "seed": self.seed,
                    "sigma": self.sigma,
                    "clip": self.clip,
                    "source_status": self.source_status,
                    "attribution_label": self.attribution_label,
                    "noise_values": self.noise_values,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "NoiseSchedule":
        """Load a noise schedule from JSON."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            seed=data["seed"],
            sigma=data.get("sigma", 0.03),
            clip=data.get("clip", 0.1),
            noise_values=data.get("noise_values", {}),
            source_status=data.get("source_status", "assumption_for_calibration"),
            attribution_label=data.get("attribution_label", "environment_noise"),
        )


# ── FaultSchedule ───────────────────────────────────────────────────────────


@dataclass
class FaultSchedule:
    """Pre-generated instrument-busy fault triggers, deterministic per seed.

    Each entry is keyed by "<plate_id>:<wavelength>" and maps to a sorted
    list of attempt numbers (1-based) where the instrument will return a
    fault instead of a valid reading.
    """

    seed: int
    fault_probability: float = 0.15
    max_retries: int = 2
    fault_map: dict[str, list[int]] = field(default_factory=dict)
    # Projection-contract metadata
    source_status: str = "assumption_for_calibration"
    attribution_label: str = "environment_fault"

    @staticmethod
    def generate(
        seed: int,
        readout_specs: list[dict[str, Any]],
        fault_probability: float = 0.15,
        max_retries: int = 2,
    ) -> "FaultSchedule":
        """Pre-generate fault triggers for readout operations.

        For each (plate_id, wavelength_nm) pair, the expected number of
        readout attempts is derived from *readout_specs*.  A fault trigger
        is sampled per attempt using a Bernoulli(fault_probability)
        distribution, but the *last* attempt is always forced to succeed
        (no fault) so the scenario remains completable.
        """
        import random as _random

        rng = _random.Random(seed)
        schedule = FaultSchedule(
            seed=seed,
            fault_probability=fault_probability,
            max_retries=max_retries,
        )

        counter: dict[str, int] = {}
        for spec in readout_specs:
            key = f"{spec['plate_id']}:{spec['wavelength_nm']}"
            counter[key] = counter.get(key, 0) + 1
            attempt = counter[key]
            if rng.random() < fault_probability:
                schedule.fault_map.setdefault(key, []).append(attempt)

        return schedule

    def should_fault(
        self, plate_id: str, wavelength_nm: int, attempt: int
    ) -> bool:
        """Return True if this readout attempt should be a fault."""
        key = f"{plate_id}:{wavelength_nm}"
        return attempt in self.fault_map.get(key, [])

    def save(self, path: Path) -> None:
        """Persist the fault schedule to JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "seed": self.seed,
                    "fault_probability": self.fault_probability,
                    "max_retries": self.max_retries,
                    "source_status": self.source_status,
                    "attribution_label": self.attribution_label,
                    "fault_map": self.fault_map,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "FaultSchedule":
        """Load a fault schedule from JSON."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            seed=data["seed"],
            fault_probability=data.get("fault_probability", 0.15),
            max_retries=data.get("max_retries", 2),
            fault_map=data.get("fault_map", {}),
            source_status=data.get("source_status", "assumption_for_calibration"),
            attribution_label=data.get("attribution_label", "environment_fault"),
        )
