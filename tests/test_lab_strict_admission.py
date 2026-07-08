from __future__ import annotations

from pathlib import Path

import pytest

from api_gym.worlds.pylabrobot_lab_v0.sampler import sample_episode as sample_lab_episode
from api_gym.worlds.pylabrobot_lab_v0.verifier import verify_run as verify_lab_run
from api_gym.worlds.pylabrobot_star_v0.sampler import sample_episode as sample_star_episode
from api_gym.worlds.pylabrobot_star_v0.verifier import verify_run as verify_star_run
from api_gym.worlds.registry import get_world_runtime


@pytest.mark.parametrize(
    ("world", "scenario", "sampler", "verifier"),
    [
        ("pylabrobot_lab_v0", "limited_tips_qc", sample_lab_episode, verify_lab_run),
        ("pylabrobot_lab_v0", "low_reagent_qc", sample_lab_episode, verify_lab_run),
        ("pylabrobot_star_v0", "limited_tips_star_qc", sample_star_episode, verify_star_run),
        ("pylabrobot_star_v0", "low_reagent_trough_qc", sample_star_episode, verify_star_run),
        ("pylabrobot_star_v0", "tip_exhaustion_96_star_qc", sample_star_episode, verify_star_run),
    ],
)
def test_resource_failure_scenarios_reject_empty_trajectory(
    tmp_path: Path,
    world: str,
    scenario: str,
    sampler,
    verifier,
) -> None:
    episode = sampler(scenario=scenario, seed=42, out_dir=tmp_path / world / scenario)

    result = verifier(episode.run_dir)

    failed_check_names = {check["name"] for check in result.checks if not check["ok"]}
    assert result.ok is False
    assert "terminal_intent_exists" in failed_check_names


@pytest.mark.parametrize(
    ("world", "scenario", "labware_id"),
    [
        ("pylabrobot_lab_v0", "limited_tips_qc", "tip_rack_01"),
        ("pylabrobot_lab_v0", "low_reagent_qc", "source_plate"),
        ("pylabrobot_star_v0", "limited_tips_star_qc", "tip_rack_01"),
        ("pylabrobot_star_v0", "low_reagent_trough_qc", "reagent_trough"),
        ("pylabrobot_star_v0", "tip_exhaustion_96_star_qc", "tip_rack_01"),
    ],
)
def test_resource_failure_scenarios_reject_arbitrary_note(
    tmp_path: Path,
    world: str,
    scenario: str,
    labware_id: str,
) -> None:
    runtime = get_world_runtime(world)
    episode = runtime.sample_episode(
        scenario=scenario,
        seed=42,
        out_dir=tmp_path / world / scenario,
    )
    runtime.dispatch_tool(episode.run_dir, name="get_labware_state", arguments={"labware_id": labware_id})
    runtime.dispatch_tool(episode.run_dir, name="add_workflow_note", arguments={"note": "done"})

    result = runtime.verify_run(episode.run_dir)

    failed_check_names = {check["name"] for check in result.checks if not check["ok"]}
    assert result.ok is False
    assert "structured_refusal_intent" in failed_check_names


def test_strict_admission_suite_runs_oracles_and_mutants(tmp_path: Path) -> None:
    from api_gym.lab_strict_admission import run_strict_admission_suite

    result = run_strict_admission_suite(out_dir=tmp_path / "strict-admission")

    assert result["ok"] is True
    assert result["summary"] == {
        "scenarios": 7,
        "cases": 30,
        "passed_cases": 30,
        "failed_cases": 0,
    }
    cases = {
        (case["world"], case["scenario"], case["case_id"]): case
        for scenario in result["scenarios"]
        for case in scenario["cases"]
    }
    assert cases[("pylabrobot_lab_v0", "plate_transfer_qc", "oracle")]["verifier_ok"] is True
    assert cases[("pylabrobot_lab_v0", "plate_transfer_qc", "empty")]["matched_expected_failure_code"] is True
    assert cases[("pylabrobot_lab_v0", "plate_transfer_qc", "wrong_decision")]["matched_expected_failure_code"] is True
    assert cases[("pylabrobot_star_v0", "plate_transfer_qc", "read_before_transfer")]["matched_expected_failure_code"] is True
    assert cases[("pylabrobot_lab_v0", "limited_tips_qc", "oracle")]["verifier_ok"] is True
    assert (
        cases[("pylabrobot_lab_v0", "limited_tips_qc", "arbitrary_note")]["expected_failure_code"]
        == "structured_refusal_intent"
    )
    assert (
        cases[("pylabrobot_lab_v0", "limited_tips_qc", "arbitrary_note")]["matched_expected_failure_code"]
        is True
    )
    assert (
        cases[("pylabrobot_lab_v0", "limited_tips_qc", "unsafe_attempt")]["expected_failure_code"]
        == "no_unavailable_tip_attempt"
    )
    assert cases[("pylabrobot_lab_v0", "limited_tips_qc", "unsafe_attempt")]["matched_expected_failure_code"] is True
    assert (
        cases[("pylabrobot_lab_v0", "low_reagent_qc", "unsafe_attempt")]["expected_failure_code"]
        == "no_overdraw_attempt"
    )
    assert cases[("pylabrobot_lab_v0", "low_reagent_qc", "unsafe_attempt")]["matched_expected_failure_code"] is True
    assert (
        cases[("pylabrobot_lab_v0", "low_reagent_qc", "partial_transfer_before_refusal")][
            "expected_failure_code"
        ]
        == "no_transfer_before_refusal"
    )
    assert (
        cases[("pylabrobot_lab_v0", "low_reagent_qc", "partial_transfer_before_refusal")][
            "matched_expected_failure_code"
        ]
        is True
    )
    assert (
        cases[("pylabrobot_star_v0", "limited_tips_star_qc", "unsafe_attempt")]["expected_failure_code"]
        == "no_unavailable_tip_attempt"
    )
    assert (
        cases[("pylabrobot_star_v0", "limited_tips_star_qc", "unsafe_attempt")]["matched_expected_failure_code"]
        is True
    )
    assert (
        cases[("pylabrobot_star_v0", "low_reagent_trough_qc", "unsafe_attempt")]["expected_failure_code"]
        == "no_overdraw_attempt"
    )
    assert (
        cases[("pylabrobot_star_v0", "low_reagent_trough_qc", "unsafe_attempt")]["matched_expected_failure_code"]
        is True
    )
    assert (
        cases[("pylabrobot_star_v0", "low_reagent_trough_qc", "partial_transfer_before_refusal")][
            "expected_failure_code"
        ]
        == "no_transfer_before_refusal"
    )
    assert (
        cases[("pylabrobot_star_v0", "low_reagent_trough_qc", "partial_transfer_before_refusal")][
            "matched_expected_failure_code"
        ]
        is True
    )
    tip_96_unsafe = cases[("pylabrobot_star_v0", "tip_exhaustion_96_star_qc", "unsafe_attempt")]
    assert tip_96_unsafe["expected_failure_code"] == "no_96_pickup_insufficient_tips"
    assert tip_96_unsafe["matched_expected_failure_code"] is True
    tip_96_non96 = cases[("pylabrobot_star_v0", "tip_exhaustion_96_star_qc", "non96_workaround_attempt")]
    assert tip_96_non96["expected_failure_code"] == "no_non96_transfer_attempt"
    assert tip_96_non96["matched_expected_failure_code"] is True
    tip_96_failed_non96 = cases[
        ("pylabrobot_star_v0", "tip_exhaustion_96_star_qc", "failed_non96_tip_attempt")
    ]
    assert tip_96_failed_non96["expected_failure_code"] == "no_non96_transfer_attempt"
    assert tip_96_failed_non96["matched_expected_failure_code"] is True
