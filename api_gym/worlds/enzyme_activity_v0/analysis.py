"""Transparent reference analysis for modeled relative enzyme rates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ObservedReading:
    measurement_id: str
    well: str
    acquired_at_s: float
    absorbance: float
    plate_id: str
    plate_revision: int
    settings_digest: str


@dataclass(frozen=True)
class AnalysisRules:
    minimum_observations: int
    minimum_window_s: float
    usable_absorbance_min: float
    usable_absorbance_max: float
    permitted_rate_unit: str = "delta_absorbance_per_minute"


@dataclass(frozen=True)
class RateEstimate:
    disposition: str
    rate: float | None
    standard_error: float | None
    units: str
    sample_measurement_ids: tuple[str, ...]
    blank_measurement_ids: tuple[str, ...]
    fit_window_s: tuple[float, float] | None
    dilution_factor: float
    reason_code: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "rate": self.rate,
            "standard_error": self.standard_error,
            "units": self.units,
            "sample_measurement_ids": list(self.sample_measurement_ids),
            "blank_measurement_ids": list(self.blank_measurement_ids),
            "fit_window_s": None if self.fit_window_s is None else list(self.fit_window_s),
            "dilution_factor": self.dilution_factor,
            "reason_code": self.reason_code,
        }


def fit_blank_corrected_rate(
    *,
    sample_readings: Iterable[ObservedReading],
    blank_readings: Iterable[ObservedReading],
    dilution_factor: float,
    rules: AnalysisRules,
) -> RateEstimate:
    sample = tuple(sorted(sample_readings, key=lambda item: item.acquired_at_s))
    blank = tuple(sorted(blank_readings, key=lambda item: item.acquired_at_s))
    unresolved = _validate_fit_inputs(sample, blank, dilution_factor, rules)
    if unresolved is not None:
        return RateEstimate(
            disposition="unresolved",
            rate=None,
            standard_error=None,
            units=rules.permitted_rate_unit,
            sample_measurement_ids=tuple(item.measurement_id for item in sample),
            blank_measurement_ids=tuple(item.measurement_id for item in blank),
            fit_window_s=None,
            dilution_factor=float(dilution_factor),
            reason_code=unresolved,
        )
    sample_slope_s, sample_se_s = _linear_slope(sample)
    blank_slope_s, blank_se_s = _linear_slope(blank)
    corrected_per_min = (sample_slope_s - blank_slope_s) * 60.0 * dilution_factor
    uncertainty = math.hypot(sample_se_s, blank_se_s) * 60.0 * dilution_factor
    overlap_start = max(sample[0].acquired_at_s, blank[0].acquired_at_s)
    overlap_end = min(sample[-1].acquired_at_s, blank[-1].acquired_at_s)
    return RateEstimate(
        disposition="usable",
        rate=corrected_per_min,
        standard_error=uncertainty,
        units=rules.permitted_rate_unit,
        sample_measurement_ids=tuple(item.measurement_id for item in sample),
        blank_measurement_ids=tuple(item.measurement_id for item in blank),
        fit_window_s=(overlap_start, overlap_end),
        dilution_factor=float(dilution_factor),
        reason_code=None,
    )


def _validate_fit_inputs(
    sample: tuple[ObservedReading, ...],
    blank: tuple[ObservedReading, ...],
    dilution_factor: float,
    rules: AnalysisRules,
) -> str | None:
    if type(dilution_factor) not in (int, float) or not math.isfinite(float(dilution_factor)):
        return "dilution_factor_invalid"
    if dilution_factor < 1:
        return "dilution_factor_invalid"
    if len(sample) < rules.minimum_observations or len(blank) < rules.minimum_observations:
        return "insufficient_observations"
    if len({item.measurement_id for item in sample + blank}) != len(sample) + len(blank):
        return "measurement_reference_invalid"
    sample_identity = {
        (item.plate_id, item.plate_revision, item.settings_digest) for item in sample
    }
    blank_identity = {
        (item.plate_id, item.plate_revision, item.settings_digest) for item in blank
    }
    if len(sample_identity) != 1 or sample_identity != blank_identity:
        return "blank_evidence_mismatch"
    if any(
        not rules.usable_absorbance_min
        <= item.absorbance
        <= rules.usable_absorbance_max
        for item in sample + blank
    ):
        return "fit_window_signal_invalid"
    overlap_start = max(sample[0].acquired_at_s, blank[0].acquired_at_s)
    overlap_end = min(sample[-1].acquired_at_s, blank[-1].acquired_at_s)
    if overlap_end - overlap_start < rules.minimum_window_s:
        return "fit_window_invalid"
    return None


def _linear_slope(readings: tuple[ObservedReading, ...]) -> tuple[float, float]:
    times = [item.acquired_at_s for item in readings]
    values = [item.absorbance for item in readings]
    mean_t = sum(times) / len(times)
    mean_y = sum(values) / len(values)
    denominator = sum((value - mean_t) ** 2 for value in times)
    if denominator == 0:
        raise ValueError("fit timestamps must not all be equal")
    slope = sum(
        (time_s - mean_t) * (absorbance - mean_y)
        for time_s, absorbance in zip(times, values, strict=True)
    ) / denominator
    if len(readings) <= 2:
        return slope, math.inf
    residual_sum_squares = sum(
        (
            absorbance
            - (mean_y + slope * (time_s - mean_t))
        )
        ** 2
        for time_s, absorbance in zip(times, values, strict=True)
    )
    standard_error = math.sqrt(
        residual_sum_squares / (len(readings) - 2) / denominator
    )
    return slope, standard_error
