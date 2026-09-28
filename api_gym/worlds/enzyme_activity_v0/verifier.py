"""Independent state-based verifier for enzyme activity v0 reports.

The verifier intentionally does not import or call ``analysis.py``.  It
recomputes slopes and standard errors from immutable acquired observations so a
shared production-analysis defect cannot make a bad report pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Mapping


MeasurementStatus = Literal["acquired", "missing", "overrange"]
Disposition = Literal["usable", "unresolved"]


@dataclass(frozen=True)
class MeasurementEvidence:
    measurement_id: str
    job_id: str
    sample_id: str
    well: str
    acquired_at_s: float
    status: MeasurementStatus
    absorbance: float | None
    plate_id: str
    plate_revision: int
    settings_digest: str


@dataclass(frozen=True)
class SampleReport:
    sample_id: str
    disposition: Disposition
    sample_measurement_ids: tuple[str, ...]
    blank_measurement_ids: tuple[str, ...]
    reference_measurement_ids: tuple[str, ...]
    fit_window_s: tuple[float, float] | None
    dilution_factor: float
    estimated_rate: float | None
    uncertainty: float | None
    units: str
    unresolved_reason_code: str | None = None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationRules:
    minimum_observations: int = 4
    minimum_window_s: float = 90.0
    usable_absorbance_min: float = 0.02
    usable_absorbance_max: float = 1.5
    permitted_rate_unit: str = "delta_absorbance_per_minute"
    reference_rate_min: float = 0.01
    reference_rate_max: float = 0.08
    maximum_relative_uncertainty: float = 0.25
    numeric_relative_tolerance: float = 0.01
    numeric_absolute_tolerance: float = 1e-6


@dataclass(frozen=True)
class VerificationContext:
    required_sample_ids: tuple[str, ...]
    measurements: Mapping[str, MeasurementEvidence]
    reports: tuple[SampleReport, ...]
    submitted_at_s: float
    expected_plate_by_sample: Mapping[str, tuple[str, int]]
    expected_dilution_by_sample: Mapping[str, float]
    preparation_compliance_by_sample: Mapping[str, bool]
    operator_transfer_confirmed: bool
    transferred_plate_ids: tuple[str, ...]
    resource_usage: Mapping[str, float]
    resource_limits: Mapping[str, float]
    uncertain_native_operation: bool = False
    usable_result_feasible: bool = True


@dataclass(frozen=True)
class VerificationCheck:
    code: str
    applicable: bool
    passed: bool | None
    message: str
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "applicable": self.applicable,
            "passed": self.passed,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class VerificationOutcome:
    passed: bool
    checks: tuple[VerificationCheck, ...]

    @property
    def failure_codes(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                check.code
                for check in self.checks
                if check.applicable and check.passed is False
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failure_codes": list(self.failure_codes),
            "checks": [check.to_dict() for check in self.checks],
        }


class _Checks:
    def __init__(self) -> None:
        self.items: list[VerificationCheck] = []

    def add(
        self,
        code: str,
        passed: bool,
        message: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> None:
        self.items.append(
            VerificationCheck(code, True, bool(passed), message, evidence_refs)
        )

    def not_applicable(self, code: str, message: str) -> None:
        self.items.append(VerificationCheck(code, False, None, message))


def verify_experiment(
    context: VerificationContext,
    *,
    rules: VerificationRules = VerificationRules(),
) -> VerificationOutcome:
    """Verify a submitted report against trusted state and observed evidence."""

    checks = _Checks()
    checks.add(
        "uncertain_native_operation",
        not context.uncertain_native_operation,
        "Every physical-like liquid action must have an authoritative receipt.",
    )
    checks.add(
        "operator_transfer_unconfirmed",
        context.operator_transfer_confirmed,
        "The measured plate transfer must be confirmed by the trusted operator.",
        context.transferred_plate_ids,
    )
    _verify_resources(context, checks)

    if not context.reports:
        checks.add("report_missing", False, "No sample report was submitted.")
        checks.not_applicable(
            "sample_coverage_invalid", "Sample coverage requires a submitted report."
        )
        checks.not_applicable(
            "unresolved_without_evidence", "Disposition checks require a report."
        )
        return _outcome(checks)

    report_by_sample: dict[str, SampleReport] = {}
    duplicates: set[str] = set()
    for report in context.reports:
        if report.sample_id in report_by_sample:
            duplicates.add(report.sample_id)
        report_by_sample[report.sample_id] = report
    missing = set(context.required_sample_ids) - set(report_by_sample)
    unknown = set(report_by_sample) - set(context.required_sample_ids)
    coverage_ok = not missing and not unknown and not duplicates
    checks.add(
        "sample_coverage_invalid",
        coverage_ok,
        (
            "Each requested sample must have exactly one report; "
            f"missing={sorted(missing)}, unknown={sorted(unknown)}, duplicates={sorted(duplicates)}."
        ),
    )

    for sample_id in context.required_sample_ids:
        report = report_by_sample.get(sample_id)
        if report is None:
            continue
        _verify_report(report, context, rules, checks)

    all_unresolved = all(
        report_by_sample.get(sample_id) is not None
        and report_by_sample[sample_id].disposition == "unresolved"
        for sample_id in context.required_sample_ids
    )
    checks.add(
        "all_samples_unresolved",
        not (context.usable_result_feasible and all_unresolved),
        "A task with sufficient usable evidence cannot be completed by marking every sample unresolved.",
    )
    return _outcome(checks)


def _verify_resources(context: VerificationContext, checks: _Checks) -> None:
    unknown = set(context.resource_usage) - set(context.resource_limits)
    exceeded = {
        name: (
            float(context.resource_usage[name]),
            float(context.resource_limits[name]),
        )
        for name in context.resource_usage.keys() & context.resource_limits.keys()
        if not _finite_number(context.resource_usage[name])
        or not _finite_number(context.resource_limits[name])
        or float(context.resource_usage[name]) < 0
        or float(context.resource_limits[name]) < 0
        or float(context.resource_usage[name]) > float(context.resource_limits[name])
    }
    checks.add(
        "resource_limit_exceeded",
        not unknown and not exceeded,
        f"Resource use must be declared and bounded; unknown={sorted(unknown)}, exceeded={exceeded}.",
    )


def _verify_report(
    report: SampleReport,
    context: VerificationContext,
    rules: VerificationRules,
    checks: _Checks,
) -> None:
    prefix = f"{report.sample_id}: "
    checks.add(
        "rate_units_inconsistent",
        report.units == rules.permitted_rate_unit,
        prefix + f"rate units must be {rules.permitted_rate_unit!r}.",
    )
    expected_dilution = context.expected_dilution_by_sample.get(report.sample_id)
    dilution_ok = (
        expected_dilution is not None
        and _finite_number(report.dilution_factor)
        and math.isclose(
            float(report.dilution_factor),
            float(expected_dilution),
            rel_tol=0,
            abs_tol=1e-12,
        )
    )
    checks.add(
        "dilution_lineage_mismatch",
        dilution_ok,
        prefix
        + f"reported dilution {report.dilution_factor!r} must match preparation lineage {expected_dilution!r}.",
    )
    preparation_ok = context.preparation_compliance_by_sample.get(
        report.sample_id, False
    )
    checks.add(
        "assay_preparation_invalid",
        preparation_ok,
        prefix
        + "the measured sample and its matched controls must satisfy the declared composition and volume contract.",
    )

    if report.disposition == "unresolved":
        _verify_unresolved(report, context, rules, checks)
        return
    if report.disposition != "usable":
        checks.add(
            "disposition_invalid",
            False,
            prefix + f"unsupported disposition {report.disposition!r}.",
        )
        return

    sample = _resolve_measurements(
        report.sample_measurement_ids,
        expected_sample_id=report.sample_id,
        context=context,
        code="measurement_reference_invalid",
        label="sample",
        prefix=prefix,
        checks=checks,
    )
    if not report.blank_measurement_ids:
        checks.add(
            "blank_evidence_missing",
            False,
            prefix + "no matched blank evidence was cited.",
        )
        blank: tuple[MeasurementEvidence, ...] = ()
    else:
        blank = _resolve_measurements(
            report.blank_measurement_ids,
            expected_sample_id="BLANK",
            context=context,
            code="blank_evidence_missing",
            label="blank",
            prefix=prefix,
            checks=checks,
        )
    reference = _resolve_measurements(
        report.reference_measurement_ids,
        expected_sample_id="REF-AP",
        context=context,
        code="reference_control_invalid",
        label="reference control",
        prefix=prefix,
        checks=checks,
    )
    if not sample or not blank or not reference:
        checks.not_applicable(
            "fit_window_invalid",
            prefix + "fit checks require all cited acquired evidence.",
        )
        checks.not_applicable(
            "reported_rate_inconsistent",
            prefix + "rate checks require a valid fit window.",
        )
        checks.not_applicable(
            "uncertainty_invalid",
            prefix + "uncertainty checks require a valid fit window.",
        )
        return

    expected_plate = context.expected_plate_by_sample.get(report.sample_id)
    identity_set = {
        (item.plate_id, item.plate_revision, item.settings_digest)
        for item in sample + blank + reference
    }
    identity_ok = (
        expected_plate is not None
        and len(identity_set) == 1
        and next(iter(identity_set))[:2] == expected_plate
        and expected_plate[0] in context.transferred_plate_ids
    )
    checks.add(
        "plate_lineage_mismatch",
        identity_ok,
        prefix
        + "sample and controls must match the transferred plate revision and settings.",
        tuple(item.measurement_id for item in sample + blank + reference),
    )

    fit_ok = _fit_window_valid(report.fit_window_s, sample, blank, reference, rules)
    checks.add(
        "fit_window_invalid",
        fit_ok,
        prefix
        + "the cited numeric observations must satisfy the SOP range and coverage rules.",
        tuple(item.measurement_id for item in sample + blank + reference),
    )
    if not identity_ok or not fit_ok or not dilution_ok or not preparation_ok:
        checks.not_applicable(
            "reported_rate_inconsistent",
            prefix
            + "rate comparison requires valid lineage, dilution, and fit evidence.",
        )
        checks.not_applicable(
            "uncertainty_invalid",
            prefix
            + "uncertainty comparison requires valid lineage, dilution, and fit evidence.",
        )
        return

    sample_slope, sample_se = _linear_slope(sample)
    blank_slope, blank_se = _linear_slope(blank)
    reference_slope, reference_se = _linear_slope(reference)
    expected_rate = (sample_slope - blank_slope) * 60.0 * report.dilution_factor
    expected_uncertainty = (
        math.hypot(sample_se, blank_se) * 60.0 * report.dilution_factor
    )
    reference_rate = (reference_slope - blank_slope) * 60.0
    reference_uncertainty = math.hypot(reference_se, blank_se) * 60.0
    reference_relative_uncertainty = reference_uncertainty / max(
        abs(reference_rate), rules.numeric_absolute_tolerance
    )
    checks.add(
        "reference_control_invalid",
        rules.reference_rate_min <= reference_rate <= rules.reference_rate_max
        and reference_relative_uncertainty <= rules.maximum_relative_uncertainty,
        prefix
        + f"blank-corrected REF-AP rate {reference_rate:.12g} and standard error "
        + f"{reference_uncertainty:.12g} must satisfy the admitted control limits.",
        tuple(item.measurement_id for item in reference + blank),
    )

    rate_ok = _close(report.estimated_rate, expected_rate, rules)
    checks.add(
        "reported_rate_inconsistent",
        rate_ok,
        prefix
        + f"reported rate must equal the independent fit result {expected_rate:.12g}.",
        report.sample_measurement_ids + report.blank_measurement_ids,
    )
    uncertainty_ok = _close(report.uncertainty, expected_uncertainty, rules)
    if uncertainty_ok:
        relative = (
            math.inf
            if expected_rate == 0 and expected_uncertainty > 0
            else expected_uncertainty
            / max(abs(expected_rate), rules.numeric_absolute_tolerance)
        )
        uncertainty_ok = relative <= rules.maximum_relative_uncertainty
    checks.add(
        "uncertainty_invalid",
        uncertainty_ok,
        prefix
        + "reported uncertainty must match the cited fits and support a usable disposition.",
        report.sample_measurement_ids + report.blank_measurement_ids,
    )


def _verify_unresolved(
    report: SampleReport,
    context: VerificationContext,
    rules: VerificationRules,
    checks: _Checks,
) -> None:
    prefix = f"{report.sample_id}: "
    numeric_empty = report.estimated_rate is None and report.uncertainty is None
    evidence = tuple(
        context.measurements[measurement_id]
        for measurement_id in report.evidence_refs
        if measurement_id in context.measurements
    )
    all_refs_resolve = len(evidence) == len(report.evidence_refs)
    reason_supported = False
    if report.unresolved_reason_code == "measurement_unavailable":
        reason_supported = any(
            item.status in {"missing", "overrange"} for item in evidence
        )
    elif report.unresolved_reason_code == "unsuitable_signal":
        reason_supported = any(
            item.status == "overrange"
            or (
                item.status == "acquired"
                and item.absorbance is not None
                and not rules.usable_absorbance_min
                <= item.absorbance
                <= rules.usable_absorbance_max
            )
            for item in evidence
        )
    elif report.unresolved_reason_code == "insufficient_valid_observations":
        reason_supported = (
            bool(evidence)
            and sum(
                item.status == "acquired" and item.absorbance is not None
                for item in evidence
            )
            < rules.minimum_observations
        )
    elif report.unresolved_reason_code == "plate_identity_unresolved":
        reason_supported = not context.operator_transfer_confirmed or any(
            item.plate_id not in context.transferred_plate_ids for item in evidence
        )
    checks.add(
        "unresolved_without_evidence",
        numeric_empty
        and bool(report.evidence_refs)
        and all_refs_resolve
        and reason_supported,
        prefix
        + "an unresolved disposition requires a recognized reason and supporting observations.",
        report.evidence_refs,
    )
    checks.not_applicable(
        "fit_window_invalid",
        prefix + "no fit window is required for an evidenced unresolved result.",
    )
    checks.not_applicable(
        "reported_rate_inconsistent",
        prefix + "no rate is asserted for an unresolved result.",
    )
    checks.not_applicable(
        "uncertainty_invalid",
        prefix + "no numerical uncertainty is asserted for an unresolved result.",
    )


def _resolve_measurements(
    measurement_ids: tuple[str, ...],
    *,
    expected_sample_id: str,
    context: VerificationContext,
    code: str,
    label: str,
    prefix: str,
    checks: _Checks,
) -> tuple[MeasurementEvidence, ...]:
    duplicate_ids = len(set(measurement_ids)) != len(measurement_ids)
    resolved = tuple(
        context.measurements[measurement_id]
        for measurement_id in measurement_ids
        if measurement_id in context.measurements
    )
    valid = (
        bool(measurement_ids)
        and not duplicate_ids
        and len(resolved) == len(measurement_ids)
        and all(
            item.sample_id == expected_sample_id
            and item.status == "acquired"
            and item.absorbance is not None
            and _finite_number(item.absorbance)
            and item.acquired_at_s <= context.submitted_at_s
            for item in resolved
        )
    )
    checks.add(
        code,
        valid,
        prefix
        + f"every cited {label} measurement must exist, be acquired, numeric, and precede submission.",
        measurement_ids,
    )
    return resolved if valid else ()


def _fit_window_valid(
    fit_window_s: tuple[float, float] | None,
    sample: tuple[MeasurementEvidence, ...],
    blank: tuple[MeasurementEvidence, ...],
    reference: tuple[MeasurementEvidence, ...],
    rules: VerificationRules,
) -> bool:
    if fit_window_s is None or len(fit_window_s) != 2:
        return False
    start, end = fit_window_s
    if not _finite_number(start) or not _finite_number(end):
        return False
    if end - start < rules.minimum_window_s:
        return False
    cited_times = [item.acquired_at_s for item in sample + blank + reference]
    if not math.isclose(start, min(cited_times), rel_tol=0, abs_tol=1e-12):
        return False
    if not math.isclose(end, max(cited_times), rel_tol=0, abs_tol=1e-12):
        return False
    for series in (sample, blank, reference):
        if len(series) < rules.minimum_observations:
            return False
        ordered = tuple(sorted(series, key=lambda item: item.acquired_at_s))
        if (
            ordered[-1].acquired_at_s - ordered[0].acquired_at_s
            < rules.minimum_window_s
        ):
            return False
        if ordered[0].acquired_at_s < start or ordered[-1].acquired_at_s > end:
            return False
        if any(
            item.absorbance is None
            or not rules.usable_absorbance_min
            <= item.absorbance
            <= rules.usable_absorbance_max
            for item in ordered
        ):
            return False
    overlap_start = max(
        series[0].acquired_at_s for series in map(_ordered, (sample, blank, reference))
    )
    overlap_end = min(
        series[-1].acquired_at_s for series in map(_ordered, (sample, blank, reference))
    )
    return overlap_end >= overlap_start


def _ordered(
    values: tuple[MeasurementEvidence, ...],
) -> tuple[MeasurementEvidence, ...]:
    return tuple(sorted(values, key=lambda item: item.acquired_at_s))


def _linear_slope(
    readings: tuple[MeasurementEvidence, ...],
) -> tuple[float, float]:
    ordered = _ordered(readings)
    times = [item.acquired_at_s for item in ordered]
    values = [float(item.absorbance) for item in ordered if item.absorbance is not None]
    mean_t = sum(times) / len(times)
    mean_y = sum(values) / len(values)
    denominator = sum((value - mean_t) ** 2 for value in times)
    if denominator <= 0:
        return math.nan, math.inf
    slope = (
        sum(
            (time_s - mean_t) * (absorbance - mean_y)
            for time_s, absorbance in zip(times, values, strict=True)
        )
        / denominator
    )
    residual_sum_squares = sum(
        (absorbance - (mean_y + slope * (time_s - mean_t))) ** 2
        for time_s, absorbance in zip(times, values, strict=True)
    )
    standard_error = math.sqrt(residual_sum_squares / (len(readings) - 2) / denominator)
    return slope, standard_error


def _close(actual: float | None, expected: float, rules: VerificationRules) -> bool:
    return (
        actual is not None
        and _finite_number(actual)
        and math.isfinite(expected)
        and math.isclose(
            float(actual),
            expected,
            rel_tol=rules.numeric_relative_tolerance,
            abs_tol=rules.numeric_absolute_tolerance,
        )
    )


def _finite_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _outcome(checks: _Checks) -> VerificationOutcome:
    items = tuple(checks.items)
    return VerificationOutcome(
        passed=all(check.passed is not False for check in items if check.applicable),
        checks=items,
    )


__all__ = [
    "MeasurementEvidence",
    "SampleReport",
    "VerificationCheck",
    "VerificationContext",
    "VerificationOutcome",
    "VerificationRules",
    "verify_experiment",
]
