from __future__ import annotations

import pytest

from api_gym.worlds.enzyme_activity_v0.analysis import (
    AnalysisRules,
    ObservedReading,
    fit_blank_corrected_rate,
)


RULES = AnalysisRules(4, 90, 0.02, 1.5)


def readings(prefix: str, slope_per_s: float, *, revision: int = 1) -> tuple[ObservedReading, ...]:
    return tuple(
        ObservedReading(
            measurement_id=f"{prefix}-{index}",
            well="A1" if prefix == "sample" else "A2",
            acquired_at_s=time_s,
            absorbance=0.05 + slope_per_s * time_s,
            plate_id="plate-1",
            plate_revision=revision,
            settings_digest="sha256:settings",
        )
        for index, time_s in enumerate((0, 30, 60, 90, 120), start=1)
    )


def test_reference_fit_blank_corrects_and_applies_actual_dilution() -> None:
    result = fit_blank_corrected_rate(
        sample_readings=readings("sample", 0.002),
        blank_readings=readings("blank", 0.0001),
        dilution_factor=4,
        rules=RULES,
    )
    assert result.disposition == "usable"
    assert result.rate == pytest.approx((0.002 - 0.0001) * 60 * 4)
    assert result.standard_error == pytest.approx(0, abs=1e-14)
    assert result.fit_window_s == (0, 120)


def test_reference_fit_rejects_mismatched_blank_revision() -> None:
    result = fit_blank_corrected_rate(
        sample_readings=readings("sample", 0.002),
        blank_readings=readings("blank", 0.0001, revision=2),
        dilution_factor=1,
        rules=RULES,
    )
    assert result.disposition == "unresolved"
    assert result.reason_code == "blank_evidence_mismatch"
    assert result.rate is None


def test_reference_fit_rejects_unsuitable_signal_and_short_window() -> None:
    overrange = tuple(
        item.__class__(**{**item.__dict__, "absorbance": 1.7})
        for item in readings("sample", 0.002)
    )
    result = fit_blank_corrected_rate(
        sample_readings=overrange,
        blank_readings=readings("blank", 0.0001),
        dilution_factor=1,
        rules=RULES,
    )
    assert result.reason_code == "fit_window_signal_invalid"
