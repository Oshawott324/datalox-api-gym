from __future__ import annotations

from collections import Counter
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
        "scenarios": 8,
        "cases": 36,
        "passed_cases": 36,
        "failed_cases": 0,
    }
    cases = {
        (case["world"], case["scenario"], case["case_id"]): case
        for scenario in result["scenarios"]
        for case in scenario["cases"]
    }
    assert cases[("pylabrobot_lab_v0", "plate_transfer_qc", "oracle")]["verifier_ok"] is True
    assert all(case["matched_expected_failure_codes"] for case in cases.values())
    assert cases[("pylabrobot_lab_v0", "limited_tips_qc", "oracle")]["verifier_ok"] is True

    assert cases[("pylabrobot_lab_v0", "limited_tips_qc", "arbitrary_note")]["expected_failure_codes"] == [
        "structured_refusal_intent"
    ]
    assert cases[("pylabrobot_lab_v0", "limited_tips_qc", "unsafe_attempt")]["expected_failure_codes"] == [
        "terminal_intent_exists",
        "structured_refusal_intent",
        "no_unavailable_tip_attempt",
    ]
    assert cases[("pylabrobot_star_v0", "plate_transfer_qc", "read_before_transfer")][
        "expected_failure_codes"
    ] == [
        "after(transfer, read)",
        "provenance(readout, transfer)",
    ]
    tip_96_unsafe = cases[("pylabrobot_star_v0", "tip_exhaustion_96_star_qc", "unsafe_attempt")]
    assert tip_96_unsafe["expected_failure_codes"] == [
        "terminal_intent_exists",
        "structured_refusal_intent",
        "no_96_pickup_insufficient_tips",
    ]
    tip_96_non96 = cases[("pylabrobot_star_v0", "tip_exhaustion_96_star_qc", "non96_workaround_attempt")]
    assert tip_96_non96["expected_failure_codes"] == ["no_non96_transfer_attempt"]
    tip_96_failed_non96 = cases[
        ("pylabrobot_star_v0", "tip_exhaustion_96_star_qc", "failed_non96_tip_attempt")
    ]
    assert tip_96_failed_non96["expected_failure_codes"] == ["no_non96_transfer_attempt"]
    assert cases[("pylabrobot_star_v0", "instrument_fault_star_qc", "oracle")]["verifier_ok"] is True
    assert (
        cases[("pylabrobot_star_v0", "instrument_fault_star_qc", "empty")]["expected_failure_codes"]
        == ["transfer", "instrument_busy_observed", "valid_readout", "submitted"]
    )
    assert (
        cases[("pylabrobot_star_v0", "instrument_fault_star_qc", "no_retry_after_busy")][
            "expected_failure_codes"
        ]
        == ["valid_readout", "submitted"]
    )
    assert (
        cases[("pylabrobot_star_v0", "instrument_fault_star_qc", "wrong_decision_after_recovery")][
            "expected_failure_codes"
        ]
        == ["decision_matches_observed_data"]
    )
    assert (
        cases[("pylabrobot_star_v0", "instrument_fault_star_qc", "extra_read_after_success")][
            "expected_failure_codes"
        ]
        == ["no_extra_readout_after_recovery"]
    )


def test_strict_admission_matches_exact_failed_check_sets(tmp_path: Path) -> None:
    from api_gym.lab_strict_admission import run_strict_admission_suite

    result = run_strict_admission_suite(out_dir=tmp_path / "strict-admission")

    for scenario in result["scenarios"]:
        for case in scenario["cases"]:
            failed_check_names = Counter(case["failed_check_names"])
            expected_failure_codes = Counter(case["expected_failure_codes"])
            if case["expected_verifier_ok"]:
                assert expected_failure_codes == Counter()
                assert failed_check_names == Counter()
            else:
                assert failed_check_names == expected_failure_codes, case
            assert case["matched_expected_failure_codes"] is True


def test_strict_admission_declarations_expose_mutant_families() -> None:
    from api_gym.lab_strict_admission import STRICT_SCENARIOS, STRICT_SCENARIO_DECLS

    assert len(STRICT_SCENARIOS) == 8
    assert len(STRICT_SCENARIO_DECLS) == 8

    expanded = {
        (scenario.world, scenario.scenario): [case.case_id for case in scenario.cases]
        for scenario in STRICT_SCENARIOS
    }
    assert expanded[("pylabrobot_star_v0", "instrument_fault_star_qc")] == [
        "oracle",
        "empty",
        "no_retry_after_busy",
        "read_before_transfer_then_retry",
        "wrong_decision_after_recovery",
        "extra_read_after_success",
    ]

    families = {
        mutant.family
        for scenario_decl in STRICT_SCENARIO_DECLS
        for mutant in scenario_decl.mutants
    }
    assert {
        "empty_plan",
        "arbitrary_note",
        "wrong_decision",
        "stale_evidence",
        "unsafe_resource_attempt",
        "partial_action_before_refusal",
        "non96_workaround_attempt",
        "failed_tool_then_false_success",
        "fault_recovery",
        "extra_retry_after_success",
    }.issubset(families)

    for scenario_decl in STRICT_SCENARIO_DECLS:
        for mutant in scenario_decl.mutants:
            assert mutant.family
            assert mutant.expected_failure_codes


def test_instrument_fault_verifier_requires_busy_recovery(tmp_path: Path) -> None:
    runtime = get_world_runtime("pylabrobot_star_v0")
    episode = runtime.sample_episode(
        scenario="instrument_fault_star_qc",
        seed=2,
        out_dir=tmp_path / "instrument_fault_without_busy",
    )

    runtime.dispatch_tool(episode.run_dir, name="get_deck_state", arguments={})
    runtime.dispatch_tool(episode.run_dir, name="get_labware_state", arguments={"labware_id": "source_plate"})
    runtime.dispatch_tool(episode.run_dir, name="get_labware_state", arguments={"labware_id": "assay_plate"})
    runtime.dispatch_tool(episode.run_dir, name="get_labware_state", arguments={"labware_id": "tip_rack_01"})
    runtime.dispatch_tool(
        episode.run_dir,
        name="pick_up_tips",
        arguments={"tip_refs": ["tip_rack_01:A1"], "channels": [0]},
    )
    runtime.dispatch_tool(
        episode.run_dir,
        name="aspirate",
        arguments={"source": "source_plate:A1", "volume_ul": 50},
    )
    runtime.dispatch_tool(
        episode.run_dir,
        name="dispense",
        arguments={"target": "assay_plate:B1", "volume_ul": 50},
    )
    readout = runtime.dispatch_tool(
        episode.run_dir,
        name="read_absorbance",
        arguments={"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    assert readout["ok"] is True
    runtime.dispatch_tool(
        episode.run_dir,
        name="submit_protocol",
        arguments={
            "decision": "continue",
            "evidence_readout_id": readout["data"]["readout_id"],
            "target_well": "assay_plate:B1",
            "rationale": "This run intentionally uses a seed without instrument_busy.",
        },
    )

    verification = runtime.verify_run(episode.run_dir)

    failed_check_names = {check["name"] for check in verification.checks if not check["ok"]}
    assert verification.ok is False
    assert "instrument_busy_observed" in failed_check_names
