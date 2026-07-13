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
        "scenarios": 9,
        "cases": 44,
        "passed_cases": 44,
        "failed_cases": 0,
    }
    cases = {
        (case["world"], case["scenario"], case["case_id"]): case
        for scenario in result["scenarios"]
        for case in scenario["cases"]
    }
    assert cases[("pylabrobot_lab_v0", "plate_transfer_qc", "oracle")]["verifier_ok"] is True
    assert all(case["matched_expected_failure_codes"] for case in cases.values())
    serial_oracle = cases[("pylabrobot_lab_v0", "serial_dilution_qc", "oracle")]
    assert serial_oracle["verifier_ok"] is True
    serial_readout = next(
        step["result"]["data"]
        for step in serial_oracle["tool_results"]
        if step["name"] == "read_absorbance"
    )
    serial_values = [serial_readout["values"][well] for well in ["B1", "B2", "B3", "B4", "B5"]]
    assert all(left > right for left, right in zip(serial_values, serial_values[1:]))
    assert cases[("pylabrobot_lab_v0", "limited_tips_qc", "oracle")]["verifier_ok"] is True

    assert cases[("pylabrobot_lab_v0", "serial_dilution_qc", "empty")]["expected_failure_codes"] == [
        "dilution_transfer_sequence",
        "fresh_tip_per_dilution_step",
        "mix_after_each_dilution_step",
        "all_dilution_wells_read",
        "after(dilution, readout)",
        "provenance(readout, dilution_series)",
        "od600_decreasing_curve",
        "protocol_submitted",
        "decision_matches_dilution_curve",
    ]
    assert cases[("pylabrobot_lab_v0", "serial_dilution_qc", "read_before_dilution")][
        "expected_failure_codes"
    ] == [
        "after(dilution, readout)",
        "provenance(readout, dilution_series)",
        "od600_decreasing_curve",
    ]
    assert cases[("pylabrobot_lab_v0", "serial_dilution_qc", "tip_reuse_between_steps")][
        "expected_failure_codes"
    ] == ["fresh_tip_per_dilution_step"]
    assert cases[("pylabrobot_lab_v0", "serial_dilution_qc", "missing_mix_after_dispense")][
        "expected_failure_codes"
    ] == ["mix_after_each_dilution_step"]
    assert cases[("pylabrobot_lab_v0", "serial_dilution_qc", "post_dilution_mutation")][
        "expected_failure_codes"
    ] == ["dilution_well_volumes_intact"]
    assert cases[("pylabrobot_lab_v0", "serial_dilution_qc", "missing_terminal_readout")][
        "expected_failure_codes"
    ] == [
        "all_dilution_wells_read",
        "after(dilution, readout)",
        "provenance(readout, dilution_series)",
        "od600_decreasing_curve",
        "protocol_submitted",
        "decision_matches_dilution_curve",
    ]
    assert cases[("pylabrobot_lab_v0", "serial_dilution_qc", "wrong_decision")][
        "expected_failure_codes"
    ] == ["decision_matches_dilution_curve"]

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
    from api_gym.lab_strict_admission import (
        EXPERIMENTAL_SCENARIO_DECLS,
        STRICT_SCENARIOS,
        STRICT_SCENARIO_DECLS,
    )

    assert len(STRICT_SCENARIOS) == 9
    assert len(STRICT_SCENARIO_DECLS) == 9
    assert {decl.scenario for decl in EXPERIMENTAL_SCENARIO_DECLS} == {
        "arm_scale_xover_qc",
        "centrifuge_reader_xover_qc",
        "tempctrl_reader_xover_qc",
        "hs_reader_xover_qc",
        "pump_scale_xover_qc",
        "pcr_reader_xover_qc",
    }
    assert not {
        decl.scenario for decl in EXPERIMENTAL_SCENARIO_DECLS
    } & {decl.scenario for decl in STRICT_SCENARIO_DECLS}

    expanded = {
        (scenario.world, scenario.scenario): [case.case_id for case in scenario.cases]
        for scenario in STRICT_SCENARIOS
    }
    assert expanded[("pylabrobot_lab_v0", "serial_dilution_qc")] == [
        "oracle",
        "empty",
        "read_before_dilution",
        "tip_reuse_between_steps",
        "missing_mix_after_dispense",
        "post_dilution_mutation",
        "missing_terminal_readout",
        "wrong_decision",
    ]
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
        "tip_reuse_between_steps",
        "missing_mix_after_dispense",
        "post_dilution_mutation",
        "missing_terminal_readout",
    }.issubset(families)

    for scenario_decl in STRICT_SCENARIO_DECLS:
        for mutant in scenario_decl.mutants:
            assert mutant.family
            assert mutant.expected_failure_codes


def test_serial_dilution_readout_tracks_volume_weighted_od(tmp_path: Path) -> None:
    runtime = get_world_runtime("pylabrobot_lab_v0")
    episode = runtime.sample_episode(
        scenario="serial_dilution_qc",
        seed=42,
        out_dir=tmp_path / "serial_dilution_od",
    )

    for index, (source, target) in enumerate(
        [
            ("source_plate:A1", "assay_plate:B1"),
            ("assay_plate:B1", "assay_plate:B2"),
            ("assay_plate:B2", "assay_plate:B3"),
            ("assay_plate:B3", "assay_plate:B4"),
            ("assay_plate:B4", "assay_plate:B5"),
        ],
        start=1,
    ):
        tip = f"tip_rack_01:A{index}"
        assert runtime.dispatch_tool(
            episode.run_dir,
            name="aspirate",
            arguments={"source": source, "volume_ul": 50, "tip": tip},
        )["ok"]
        assert runtime.dispatch_tool(
            episode.run_dir,
            name="dispense",
            arguments={"target": target, "volume_ul": 50, "mix_after": True},
        )["ok"]
        assert runtime.dispatch_tool(episode.run_dir, name="discard_tips", arguments={})["ok"]

    readout = runtime.dispatch_tool(
        episode.run_dir,
        name="read_absorbance",
        arguments={"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1", "B2", "B3", "B4", "B5"]},
    )

    assert readout["ok"] is True
    values = [readout["data"]["values"][well] for well in ["B1", "B2", "B3", "B4", "B5"]]
    assert values == [0.5, 0.25, 0.125, 0.0625, 0.0312]
    assert all(left > right for left, right in zip(values, values[1:]))


def test_serial_dilution_submitted_readout_must_cover_all_wells(tmp_path: Path) -> None:
    runtime = get_world_runtime("pylabrobot_lab_v0")
    episode = runtime.sample_episode(
        scenario="serial_dilution_qc",
        seed=42,
        out_dir=tmp_path / "serial_dilution_submitted_readout",
    )
    _run_serial_dilution_chain(runtime, episode.run_dir, mix_after=True)

    assert runtime.dispatch_tool(
        episode.run_dir,
        name="read_absorbance",
        arguments={"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1", "B2", "B3", "B4"]},
    )["ok"]
    submitted_readout = runtime.dispatch_tool(
        episode.run_dir,
        name="read_absorbance",
        arguments={"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B5"]},
    )
    assert submitted_readout["ok"] is True
    assert runtime.dispatch_tool(
        episode.run_dir,
        name="submit_protocol",
        arguments={
            "decision": "hold",
            "evidence_readout_id": submitted_readout["data"]["readout_id"],
            "target_well": "assay_plate:B5",
            "rationale": "Intentional test: only the submitted readout should count.",
        },
    )["ok"]

    result = runtime.verify_run(episode.run_dir)
    failed_check_names = {check["name"] for check in result.checks if not check["ok"]}
    assert "all_dilution_wells_read" in failed_check_names


def test_serial_dilution_readout_does_not_report_od_for_drained_well(tmp_path: Path) -> None:
    runtime = get_world_runtime("pylabrobot_lab_v0")
    episode = runtime.sample_episode(
        scenario="serial_dilution_qc",
        seed=42,
        out_dir=tmp_path / "serial_dilution_drained_readout",
    )
    _run_serial_dilution_chain(runtime, episode.run_dir, mix_after=True)

    assert runtime.dispatch_tool(
        episode.run_dir,
        name="aspirate",
        arguments={"source": "assay_plate:B1", "volume_ul": 50, "tip": "tip_rack_01:A6"},
    )["ok"]
    readout = runtime.dispatch_tool(
        episode.run_dir,
        name="read_absorbance",
        arguments={"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )

    assert readout["ok"] is True
    assert readout["data"]["values"]["B1"] == 0.0


def test_serial_dilution_ot2_path_tracks_od_and_verifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from api_gym.worlds.pylabrobot_lab_v0 import services_ot2

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(services_ot2.asyncio, "sleep", _no_sleep)
    runtime = get_world_runtime("pylabrobot_lab_v0")
    episode = runtime.sample_episode(
        scenario="serial_dilution_qc_ot2",
        seed=42,
        out_dir=tmp_path / "serial_dilution_ot2",
    )
    lab_state = episode.lab_state

    for index, (source, target) in enumerate(_SERIAL_DILUTION_EDGES, start=1):
        assert services_ot2.aspirate(lab_state, source=source, volume_ul=50, tip_ref=f"tip_rack_01:A{index}")["ok"]
        assert services_ot2.dispense(lab_state, target=target, volume_ul=50, mix_after=True)["ok"]
        assert services_ot2.discard_tips(lab_state)["ok"]

    readout = services_ot2.read_absorbance(
        lab_state,
        plate_id="assay_plate",
        wavelength_nm=600,
        wells=["B1", "B2", "B3", "B4", "B5"],
    )
    assert readout["ok"] is True
    values = [readout["data"]["values"][well] for well in ["B1", "B2", "B3", "B4", "B5"]]
    assert values == [0.5, 0.25, 0.125, 0.0625, 0.0312]
    assert all(left > right for left, right in zip(values, values[1:]))
    assert services_ot2.submit_protocol(
        lab_state,
        decision="continue",
        evidence_readout_id=readout["data"]["readout_id"],
        target_well="assay_plate:B5",
        rationale="OD600 decreases across B1-B5.",
    )["ok"]

    result = runtime.verify_run(episode.run_dir)
    assert result.ok is True


_SERIAL_DILUTION_EDGES = [
    ("source_plate:A1", "assay_plate:B1"),
    ("assay_plate:B1", "assay_plate:B2"),
    ("assay_plate:B2", "assay_plate:B3"),
    ("assay_plate:B3", "assay_plate:B4"),
    ("assay_plate:B4", "assay_plate:B5"),
]


def _run_serial_dilution_chain(runtime, run_dir: Path, *, mix_after: bool) -> None:
    for index, (source, target) in enumerate(_SERIAL_DILUTION_EDGES, start=1):
        assert runtime.dispatch_tool(
            run_dir,
            name="aspirate",
            arguments={"source": source, "volume_ul": 50, "tip": f"tip_rack_01:A{index}"},
        )["ok"]
        assert runtime.dispatch_tool(
            run_dir,
            name="dispense",
            arguments={"target": target, "volume_ul": 50, "mix_after": mix_after},
        )["ok"]
        assert runtime.dispatch_tool(run_dir, name="discard_tips", arguments={})["ok"]


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
