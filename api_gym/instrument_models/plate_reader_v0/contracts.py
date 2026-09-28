"""Versioned contracts for the authored absorbance reader model.

The profile describes the model's supported domain.  It is not a claim about a
particular physical reader.  All time values are logical experiment seconds,
all volumes are microlitres, and absorbance is dimensionless optical density.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any


def _finite(value: Any, *, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class ReaderProfile:
    profile_id: str
    wavelength_nm: int
    temperature_c: float
    compatible_plate_load_name: str
    reaction_volume_min_ul: float
    reaction_volume_max_ul: float
    optical_path_cm: float
    product_extinction_per_mM_cm: float
    blank_intercept_abs: float
    blank_drift_abs_per_s: float
    noise_sd_abs: float
    detector_min_abs: float
    detector_max_abs: float
    per_well_delay_s: float
    evidence_level: str = "provisional_authored_model"

    def __post_init__(self) -> None:
        if not self.profile_id or self.profile_id.strip() != self.profile_id:
            raise ValueError("profile_id must be a non-empty trimmed string")
        if type(self.wavelength_nm) is not int or self.wavelength_nm <= 0:
            raise ValueError("wavelength_nm must be a positive integer")
        if not self.compatible_plate_load_name:
            raise ValueError("compatible_plate_load_name is required")
        for name in (
            "temperature_c",
            "reaction_volume_min_ul",
            "reaction_volume_max_ul",
            "optical_path_cm",
            "product_extinction_per_mM_cm",
            "blank_intercept_abs",
            "blank_drift_abs_per_s",
            "noise_sd_abs",
            "detector_min_abs",
            "detector_max_abs",
            "per_well_delay_s",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name=name))
        if not 0 < self.reaction_volume_min_ul <= self.reaction_volume_max_ul:
            raise ValueError("reader reaction-volume interval is invalid")
        if self.optical_path_cm <= 0 or self.product_extinction_per_mM_cm <= 0:
            raise ValueError("optical path and extinction coefficient must be positive")
        if self.noise_sd_abs < 0 or self.per_well_delay_s < 0:
            raise ValueError("noise and per-well delay must be non-negative")
        if self.detector_min_abs >= self.detector_max_abs:
            raise ValueError("detector interval is invalid")
        if self.evidence_level != "provisional_authored_model":
            raise ValueError("v0 only admits explicitly provisional modeled readings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "wavelength_nm": self.wavelength_nm,
            "temperature_c": self.temperature_c,
            "compatible_plate_load_name": self.compatible_plate_load_name,
            "reaction_volume_interval_ul": [
                self.reaction_volume_min_ul,
                self.reaction_volume_max_ul,
            ],
            "optical_path_cm": self.optical_path_cm,
            "product_extinction_per_mM_cm": self.product_extinction_per_mM_cm,
            "blank_intercept_abs": self.blank_intercept_abs,
            "blank_drift_abs_per_s": self.blank_drift_abs_per_s,
            "noise_sd_abs": self.noise_sd_abs,
            "detector_interval_abs": [
                self.detector_min_abs,
                self.detector_max_abs,
            ],
            "per_well_delay_s": self.per_well_delay_s,
            "evidence_level": self.evidence_level,
        }

    @property
    def digest(self) -> str:
        payload = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class AcquisitionSettings:
    wavelength_nm: int
    temperature_c: float
    wells: tuple[str, ...]
    time_offsets_s: tuple[float, ...]

    def __post_init__(self) -> None:
        if type(self.wavelength_nm) is not int or self.wavelength_nm <= 0:
            raise ValueError("wavelength_nm must be a positive integer")
        object.__setattr__(
            self, "temperature_c", _finite(self.temperature_c, name="temperature_c")
        )
        if not self.wells or len(set(self.wells)) != len(self.wells):
            raise ValueError("wells must be a non-empty unique tuple")
        if any(type(well) is not str or not well for well in self.wells):
            raise ValueError("each well must be a non-empty string")
        offsets = tuple(_finite(value, name="time_offset_s") for value in self.time_offsets_s)
        if not offsets or offsets[0] < 0 or any(
            right <= left for left, right in zip(offsets, offsets[1:])
        ):
            raise ValueError("time offsets must be non-negative and strictly increasing")
        object.__setattr__(self, "time_offsets_s", offsets)

    def validate_for(self, profile: ReaderProfile) -> None:
        if self.wavelength_nm != profile.wavelength_nm:
            raise ValueError("reader wavelength is outside the admitted profile")
        if self.temperature_c != profile.temperature_c:
            raise ValueError("reader temperature is outside the admitted fixed condition")

    def to_dict(self) -> dict[str, Any]:
        return {
            "wavelength_nm": self.wavelength_nm,
            "temperature_c": self.temperature_c,
            "wells": list(self.wells),
            "time_offsets_s": list(self.time_offsets_s),
        }

    @property
    def digest(self) -> str:
        payload = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()
