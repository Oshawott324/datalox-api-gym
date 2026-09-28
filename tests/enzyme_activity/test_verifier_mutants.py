from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from api_gym.worlds.enzyme_activity_v0.verifier import (
    MeasurementEvidence,
    SampleReport,
    VerificationContext,
    verify_experiment,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "phase3_scenarios.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _cases() -> list[dict[str, Any]]:
    return FIXTURE["scenarios"]


def _series(case: dict[str, Any], name: str) -> list[float | None]:
    return list(case.get(f"{name}_absorbance", FIXTURE["common"][f"{name}_absorbance"]))


def _measurement_id(case: dict[str, Any], sample_id: str, index: int) -> str:
    label = {"SAMPLE-A": "sample", "BLANK": "blank", "REF-AP": "reference"}[sample_id]
    return f"{case['scenario_id']}-{label}-{index}"


def _measurements(case: dict[str, Any]) -> dict[str, MeasurementEvidence]:
    result: dict[str, MeasurementEvidence] = {}
    for sample_id, name, well in (
        ("SAMPLE-A", "sample", "A1"),
        ("BLANK", "blank", "A2"),
        ("REF-AP", "reference", "A3"),
    ):
        for index, (time_s, absorbance) in enumerate(
            zip(case["times_s"], _series(case, name), strict=True)
        ):
            measurement_id = _measurement_id(case, sample_id, index)
            result[measurement_id] = MeasurementEvidence(
                measurement_id=measurement_id,
                job_id=f"job-{case['scenario_id']}",
                sample_id=sample_id,
                well=well,
                acquired_at_s=time_s,
                status="missing" if absorbance is None else "acquired",
                absorbance=absorbance,
                plate_id=case["plate_id"],
                plate_revision=case["plate_revision"],
                settings_digest="sha256:fixture-settings",
            )
    return result


def _report(case: dict[str, Any], indices: list[int]) -> SampleReport:
    def ids(sample_id: str) -> tuple[str, ...]:
        return tuple(_measurement_id(case, sample_id, index) for index in indices)

    times = [case["times_s"][index] for index in indices]
    return SampleReport(
        sample_id="SAMPLE-A",
        disposition="usable",
        sample_measurement_ids=ids("SAMPLE-A"),
        blank_measurement_ids=ids("BLANK"),
        reference_measurement_ids=ids("REF-AP"),
        fit_window_s=(min(times), max(times)),
        dilution_factor=1.0,
        estimated_rate=FIXTURE["common"]["expected_sample_rate"],
        uncertainty=FIXTURE["common"]["expected_uncertainty"],
        units=FIXTURE["common"]["units"],
    )


def _context(
    case: dict[str, Any],
    *,
    reports: tuple[SampleReport, ...] | None = None,
    measurements: dict[str, MeasurementEvidence] | None = None,
) -> VerificationContext:
    return VerificationContext(
        required_sample_ids=("SAMPLE-A",),
        measurements=_measurements(case) if measurements is None else measurements,
        reports=(
            (_report(case, case["selected_indices"]),) if reports is None else reports
        ),
        submitted_at_s=max(case["times_s"]) + 1.0,
        expected_plate_by_sample={
            "SAMPLE-A": (case["plate_id"], case["plate_revision"])
        },
        expected_dilution_by_sample={"SAMPLE-A": 1.0},
        preparation_compliance_by_sample={"SAMPLE-A": True},
        operator_transfer_confirmed=True,
        transferred_plate_ids=(case["plate_id"],),
        resource_usage={
            "assay_plates": 1,
            "logical_time_s": max(case["times_s"]) + 1.0,
            "plate_transfers": 1,
        },
        resource_limits={
            "assay_plates": 1,
            "logical_time_s": 900.0,
            "plate_transfers": 1,
        },
        usable_result_feasible=True,
    )


def _targeted_mutant(case: dict[str, Any]) -> VerificationContext:
    mutation = case["targeted_mutant"]
    measurements = _measurements(case)
    report = _report(case, case["selected_indices"])
    if mutation == "short_fit_window":
        report = _report(case, [0, 1, 2])
    elif mutation == "out_of_range_signal":
        for offset, measurement_id in enumerate(report.sample_measurement_ids):
            measurements[measurement_id] = replace(
                measurements[measurement_id], absorbance=1.55 + 0.01 * offset
            )
    elif mutation == "job_start_as_reaction_start":
        report = replace(report, fit_window_s=(0.0, 120.0))
    elif mutation == "cite_missing_as_zero":
        report = replace(
            report,
            sample_measurement_ids=(
                *report.sample_measurement_ids[:2],
                _measurement_id(case, "SAMPLE-A", 2),
                *report.sample_measurement_ids[2:],
            ),
        )
    elif mutation == "omit_blank":
        report = replace(report, blank_measurement_ids=())
    elif mutation == "relabel_old_plate":
        for measurement_id in report.sample_measurement_ids:
            measurements[measurement_id] = replace(
                measurements[measurement_id],
                plate_id="assay-plate-old",
                plate_revision=1,
            )
    else:
        raise AssertionError(f"unknown fixture mutant {mutation}")
    return _context(case, reports=(report,), measurements=measurements)


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["family"])
def test_reference_plan_passes(case: dict[str, Any]) -> None:
    outcome = verify_experiment(_context(case))
    assert outcome.passed is True, outcome.to_dict()


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["family"])
def test_alternative_valid_fit_window_passes(case: dict[str, Any]) -> None:
    report = _report(case, case["alternative_indices"])
    outcome = verify_experiment(_context(case, reports=(report,)))
    assert outcome.passed is True, outcome.to_dict()


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["family"])
def test_empty_report_fails(case: dict[str, Any]) -> None:
    outcome = verify_experiment(_context(case, reports=()))
    assert outcome.passed is False
    assert "report_missing" in outcome.failure_codes


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["family"])
def test_targeted_mutant_fails_with_expected_code(case: dict[str, Any]) -> None:
    outcome = verify_experiment(_targeted_mutant(case))
    assert outcome.passed is False
    assert case["expected_failure_code"] in outcome.failure_codes, outcome.to_dict()


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["family"])
def test_plate_revision_provenance_mutant_fails(case: dict[str, Any]) -> None:
    context = _context(case)
    measurements = dict(context.measurements)
    measurement_id = context.reports[0].sample_measurement_ids[0]
    measurements[measurement_id] = replace(
        measurements[measurement_id], plate_revision=case["plate_revision"] + 1
    )
    outcome = verify_experiment(replace(context, measurements=measurements))
    assert outcome.passed is False
    assert "plate_lineage_mismatch" in outcome.failure_codes


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["family"])
def test_resource_mutant_fails(case: dict[str, Any]) -> None:
    context = _context(case)
    outcome = verify_experiment(
        replace(
            context,
            resource_usage={**context.resource_usage, "assay_plates": 3},
        )
    )
    assert outcome.passed is False
    assert "resource_limit_exceeded" in outcome.failure_codes


def test_independent_fixture_contains_hand_calculated_expected_values() -> None:
    common = FIXTURE["common"]
    assert common["expected_sample_rate"] == 0.072
    assert common["expected_reference_rate"] == 0.048
    assert "production analysis" in FIXTURE["fixture_basis"]


def test_evidence_backed_unresolved_result_is_valid_only_when_task_is_infeasible() -> (
    None
):
    case = next(item for item in _cases() if item["family"] == "interrupted_series")
    context = _context(case)
    missing_id = _measurement_id(case, "SAMPLE-A", 2)
    unresolved = SampleReport(
        sample_id="SAMPLE-A",
        disposition="unresolved",
        sample_measurement_ids=(),
        blank_measurement_ids=(),
        reference_measurement_ids=(),
        fit_window_s=None,
        dilution_factor=1.0,
        estimated_rate=None,
        uncertainty=None,
        units=FIXTURE["common"]["units"],
        unresolved_reason_code="measurement_unavailable",
        evidence_refs=(missing_id,),
    )
    evidenced = verify_experiment(
        replace(context, reports=(unresolved,), usable_result_feasible=False)
    )
    assert evidenced.passed is True, evidenced.to_dict()

    shortcut = verify_experiment(replace(context, reports=(unresolved,)))
    assert shortcut.passed is False
    assert shortcut.failure_codes == ("all_samples_unresolved",)


def test_units_and_dilution_are_checked_against_frozen_contract_and_lineage() -> None:
    case = _cases()[0]
    context = _context(case)
    bad = replace(context.reports[0], units="enzyme_units", dilution_factor=2.0)
    outcome = verify_experiment(replace(context, reports=(bad,)))
    assert "rate_units_inconsistent" in outcome.failure_codes
    assert "dilution_lineage_mismatch" in outcome.failure_codes


def test_noncompliant_assay_composition_cannot_support_a_rate() -> None:
    case = _cases()[0]
    context = _context(case)
    outcome = verify_experiment(
        replace(
            context,
            preparation_compliance_by_sample={"SAMPLE-A": False},
        )
    )
    assert outcome.passed is False
    assert "assay_preparation_invalid" in outcome.failure_codes


def test_failed_reference_control_cannot_support_a_usable_disposition() -> None:
    case = _cases()[0]
    context = _context(case)
    measurements = dict(context.measurements)
    for measurement_id in context.reports[0].reference_measurement_ids:
        reference = measurements[measurement_id]
        index = int(measurement_id.rsplit("-", 1)[1])
        measurements[measurement_id] = replace(
            reference,
            absorbance=FIXTURE["common"]["blank_absorbance"][index],
        )
    outcome = verify_experiment(replace(context, measurements=measurements))
    assert outcome.passed is False
    assert "reference_control_invalid" in outcome.failure_codes


def test_measurements_acquired_after_submission_are_rejected() -> None:
    case = _cases()[0]
    context = _context(case)
    outcome = verify_experiment(replace(context, submitted_at_s=60.0))
    assert outcome.passed is False
    assert "measurement_reference_invalid" in outcome.failure_codes
