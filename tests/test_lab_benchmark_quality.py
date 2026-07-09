from __future__ import annotations

import pytest
from pathlib import Path


def test_admission_matrix_covers_every_strict_case() -> None:
    from api_gym.lab_benchmark_quality import build_admission_matrix
    from api_gym.lab_strict_admission import STRICT_SCENARIOS

    matrix = build_admission_matrix()

    expected_case_count = sum(len(scenario.cases) for scenario in STRICT_SCENARIOS)
    assert len(matrix["rows"]) == expected_case_count
    assert matrix["summary"] == {
        "scenarios": 8,
        "cases": 36,
        "mutant_families": 10,
        "splits": {
            "dev": 24,
            "test_family_heldout": 6,
            "test_fault_heldout": 6,
        },
    }

    tip_exhaustion_rows = [
        row for row in matrix["rows"]
        if row["world"] == "pylabrobot_star_v0"
        and row["scenario"] == "tip_exhaustion_96_star_qc"
    ]
    assert {row["split"] for row in tip_exhaustion_rows} == {"test_family_heldout"}

    instrument_rows = [
        row for row in matrix["rows"]
        if row["world"] == "pylabrobot_star_v0"
        and row["scenario"] == "instrument_fault_star_qc"
    ]
    assert [row["case_id"] for row in instrument_rows] == [
        "oracle",
        "empty",
        "no_retry_after_busy",
        "read_before_transfer_then_retry",
        "wrong_decision_after_recovery",
        "extra_read_after_success",
    ]
    assert instrument_rows[0]["case_kind"] == "oracle"
    assert {row["split"] for row in instrument_rows} == {"test_fault_heldout"}
    assert instrument_rows[2]["mutant_family"] == "fault_recovery"
    assert instrument_rows[2]["expected_failure_codes"] == ["valid_readout", "submitted"]


def test_admission_matrix_declares_milestones_and_collateral_damage() -> None:
    from api_gym.lab_benchmark_quality import build_admission_matrix

    matrix = build_admission_matrix()
    rows = matrix["rows"]
    milestone_ids = {
        milestone
        for row in rows
        for milestone in row["milestones"]
    }
    assert {
        "target_action",
        "resource_check_before_action",
        "fresh_evidence_before_submit",
        "decision_matches_observation",
        "recover_after_fault",
        "collateral_damage_avoidance",
    }.issubset(milestone_ids)

    collateral_rows = [
        row for row in rows
        if "collateral_damage_avoidance" in row["milestones"]
    ]
    assert collateral_rows
    assert {
        "no_unavailable_tip_attempt",
        "no_overdraw_attempt",
        "no_transfer_before_refusal",
        "no_96_pickup_insufficient_tips",
        "no_non96_transfer_attempt",
        "no_extra_readout_after_recovery",
    }.issubset({
        code
        for row in collateral_rows
        for code in row["expected_failure_codes"]
    })


def test_quality_summary_uses_milestone_outcomes_not_only_case_outcome() -> None:
    from api_gym.lab_benchmark_quality import build_milestone_results, summarize_quality_results

    milestone_results = build_milestone_results(
        milestone_ids=["recover_after_fault"],
        expected_failure_codes=["valid_readout"],
        failed_check_names=["valid_readout"],
        admission_ok=False,
    )
    assert milestone_results["recover_after_fault"] == {
        "admission_ok": False,
        "expected_failure_codes": ["valid_readout"],
        "expected_observed_ok": False,
        "failed_check_names": ["valid_readout"],
        "observed_ok": False,
        "outcome_matched": True,
    }

    summary = summarize_quality_results(
        [
            {
                "ok": False,
                "split": "test_fault_heldout",
                "milestones": ["recover_after_fault"],
                "milestone_results": milestone_results,
            }
        ]
    )

    assert summary["splits"]["test_fault_heldout"] == {
        "cases": 1,
        "passed_cases": 0,
    }
    assert summary["milestones"]["recover_after_fault"] == {
        "cases": 1,
        "passed_cases": 1,
    }


def test_quality_summary_requires_explicit_milestone_results() -> None:
    from api_gym.lab_benchmark_quality import summarize_quality_results

    with pytest.raises(KeyError, match="milestone_results"):
        summarize_quality_results(
            [
                {
                    "ok": True,
                    "split": "dev",
                    "milestones": ["target_action"],
                }
            ]
        )


def test_milestone_result_match_is_order_insensitive() -> None:
    from api_gym.lab_benchmark_quality import build_milestone_results

    milestone_results = build_milestone_results(
        milestone_ids=["recover_after_fault"],
        expected_failure_codes=["submitted", "valid_readout"],
        failed_check_names=["valid_readout", "submitted"],
        admission_ok=True,
    )

    assert milestone_results["recover_after_fault"]["outcome_matched"] is True


def test_strict_admission_suite_reports_milestones(tmp_path: Path) -> None:
    from api_gym.lab_strict_admission import run_strict_admission_suite

    result = run_strict_admission_suite(out_dir=tmp_path / "strict-admission")

    assert result["quality_summary"]["milestones"]["recover_after_fault"]["cases"] == 4
    assert result["quality_summary"]["milestones"]["collateral_damage_avoidance"]["cases"] == 9
    assert result["quality_summary"]["splits"] == {
        "dev": {"cases": 24, "passed_cases": 24},
        "test_family_heldout": {"cases": 6, "passed_cases": 6},
        "test_fault_heldout": {"cases": 6, "passed_cases": 6},
    }

    instrument_fault = next(
        case
        for scenario in result["scenarios"]
        for case in scenario["cases"]
        if case["scenario"] == "instrument_fault_star_qc"
        and case["case_id"] == "no_retry_after_busy"
    )
    assert instrument_fault["split"] == "test_fault_heldout"
    assert "recover_after_fault" in instrument_fault["milestones"]
    assert instrument_fault["milestone_results"]["recover_after_fault"] == {
        "admission_ok": True,
        "expected_failure_codes": ["valid_readout", "submitted"],
        "expected_observed_ok": False,
        "failed_check_names": ["valid_readout", "submitted"],
        "observed_ok": False,
        "outcome_matched": True,
    }

    extra_retry = next(
        case
        for scenario in result["scenarios"]
        for case in scenario["cases"]
        if case["scenario"] == "instrument_fault_star_qc"
        and case["case_id"] == "extra_read_after_success"
    )
    assert extra_retry["milestone_results"]["recover_after_fault"]["observed_ok"] is True
    assert extra_retry["milestone_results"]["collateral_damage_avoidance"] == {
        "admission_ok": True,
        "expected_failure_codes": ["no_extra_readout_after_recovery"],
        "expected_observed_ok": False,
        "failed_check_names": ["no_extra_readout_after_recovery"],
        "observed_ok": False,
        "outcome_matched": True,
    }

    unsafe_tip_attempt = next(
        case
        for scenario in result["scenarios"]
        for case in scenario["cases"]
        if case["scenario"] == "limited_tips_qc"
        and case["case_id"] == "unsafe_attempt"
    )
    assert unsafe_tip_attempt["milestone_results"]["collateral_damage_avoidance"] == {
        "admission_ok": True,
        "expected_failure_codes": ["no_unavailable_tip_attempt"],
        "expected_observed_ok": False,
        "failed_check_names": ["no_unavailable_tip_attempt"],
        "observed_ok": False,
        "outcome_matched": True,
    }
