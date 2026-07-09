"""Strict admission harness for the lab worlds.

The harness intentionally exercises only the public world runtime surface:
sample a fresh episode, dispatch runtime tools, then call the verifier.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from api_gym.worlds.registry import WorldRuntime, get_world_runtime


CaseRunner = Callable[[WorldRuntime, Path], list[dict[str, Any]]]


@dataclass(frozen=True)
class StrictCase:
    case_id: str
    runner: CaseRunner
    expected_verifier_ok: bool
    expected_failure_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrictMutantDecl:
    family: str
    case_id: str
    runner: CaseRunner
    expected_failure_codes: tuple[str, ...]


@dataclass(frozen=True)
class StrictScenarioDecl:
    world: str
    scenario: str
    oracle: CaseRunner
    mutants: tuple[StrictMutantDecl, ...]
    seed: int | None = None


@dataclass(frozen=True)
class StrictScenario:
    world: str
    scenario: str
    cases: tuple[StrictCase, ...]


def run_strict_admission_suite(*, out_dir: Path) -> dict[str, Any]:
    """Run oracle, empty, and mutant cases for the strict lab admission set."""
    from api_gym.lab_benchmark_quality import (
        build_admission_matrix,
        build_milestone_results,
        summarize_quality_results,
    )

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    quality_rows = {
        (row["world"], row["scenario"], row["case_id"]): row
        for row in build_admission_matrix()["rows"]
    }

    scenario_results: list[dict[str, Any]] = []
    all_case_results: list[dict[str, Any]] = []
    passed_cases = 0
    failed_cases = 0
    case_index = 0

    for scenario_spec in STRICT_SCENARIOS:
        runtime = get_world_runtime(scenario_spec.world)
        case_results: list[dict[str, Any]] = []

        for case_spec in scenario_spec.cases:
            case_index += 1
            run_dir = (
                out_dir
                / f"{case_index:02d}_{scenario_spec.world}_{scenario_spec.scenario}_{case_spec.case_id}"
            )
            episode = runtime.sample_episode(
                scenario=scenario_spec.scenario,
                seed=_seed_for_scenario(scenario_spec) or 10_000 + case_index,
                out_dir=run_dir,
            )

            tool_results = case_spec.runner(runtime, episode.run_dir)
            verification = runtime.verify_run(episode.run_dir)
            failed_check_names = [
                str(check["name"]) for check in verification.checks if not check["ok"]
            ]
            matched_expected_failure_codes = (
                Counter(failed_check_names) == Counter(case_spec.expected_failure_codes)
            )
            case_ok = (
                verification.ok is case_spec.expected_verifier_ok
                and matched_expected_failure_codes
            )
            quality_row = quality_rows[
                (scenario_spec.world, scenario_spec.scenario, case_spec.case_id)
            ]
            if case_ok:
                passed_cases += 1
            else:
                failed_cases += 1

            case_result = {
                "world": scenario_spec.world,
                "scenario": scenario_spec.scenario,
                "case_id": case_spec.case_id,
                "run_dir": str(episode.run_dir),
                "verifier_ok": verification.ok,
                "expected_verifier_ok": case_spec.expected_verifier_ok,
                "expected_failure_codes": list(case_spec.expected_failure_codes),
                "failed_check_names": failed_check_names,
                "matched_expected_failure_codes": matched_expected_failure_codes,
                "ok": case_ok,
                "split": quality_row["split"],
                "milestones": list(quality_row["milestones"]),
                "milestone_results": build_milestone_results(
                    milestone_ids=quality_row["milestones"],
                    expected_failure_codes=case_spec.expected_failure_codes,
                    failed_check_names=failed_check_names,
                    admission_ok=case_ok,
                ),
                "tool_results": tool_results,
            }
            case_results.append(case_result)
            all_case_results.append(case_result)

        scenario_results.append(
            {
                "world": scenario_spec.world,
                "scenario": scenario_spec.scenario,
                "cases": case_results,
                "ok": all(case["ok"] for case in case_results),
            }
        )

    summary = {
        "scenarios": len(STRICT_SCENARIOS),
        "cases": passed_cases + failed_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
    }
    return {
        "ok": failed_cases == 0,
        "summary": summary,
        "quality_summary": summarize_quality_results(all_case_results),
        "scenarios": scenario_results,
    }


def _call(
    runtime: WorldRuntime,
    run_dir: Path,
    results: list[dict[str, Any]],
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result = runtime.dispatch_tool(run_dir, name=name, arguments=arguments)
    results.append({"name": name, "arguments": arguments, "result": result})
    return result


def _readout_id(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        raise RuntimeError(f"read_absorbance failed: {result}")
    data = result.get("data", {})
    readout_id = data.get("readout_id")
    if not isinstance(readout_id, str) or not readout_id:
        raise RuntimeError(f"read_absorbance did not return a readout_id: {result}")
    return readout_id


def _empty(_runtime: WorldRuntime, _run_dir: Path) -> list[dict[str, Any]]:
    return []


def _lab_plate_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _lab_inspect_plate_transfer(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "aspirate",
        {"source": "source_plate:A1", "volume_ul": 50, "tip": "tip_rack_01:A1"},
    )
    _call(
        runtime,
        run_dir,
        results,
        "dispense",
        {"target": "assay_plate:B1", "volume_ul": 50, "mix_after": False},
    )
    readout = _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "OD600 B1 is inside the expected control band.",
        },
    )
    return results


def _lab_plate_wrong_decision(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _lab_inspect_plate_transfer(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "aspirate",
        {"source": "source_plate:A1", "volume_ul": 50, "tip": "tip_rack_01:A1"},
    )
    _call(runtime, run_dir, results, "dispense", {"target": "assay_plate:B1", "volume_ul": 50})
    readout = _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "hold",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: submit the opposite decision.",
        },
    )
    return results


def _lab_serial_dilution_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _lab_inspect_plate_transfer(runtime, run_dir, results)
    _lab_serial_dilution_chain(runtime, run_dir, results, discard_between_steps=True)
    readout = _lab_read_serial_dilution(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B5",
            "rationale": "OD600 decreases across B1-B5 after the serial dilution.",
        },
    )
    return results


def _lab_serial_dilution_read_before_dilution(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    stale_readout = _lab_read_serial_dilution(runtime, run_dir, results)
    _lab_inspect_plate_transfer(runtime, run_dir, results)
    _lab_serial_dilution_chain(runtime, run_dir, results, discard_between_steps=True)
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "hold",
            "evidence_readout_id": _readout_id(stale_readout),
            "target_well": "assay_plate:B5",
            "rationale": "Intentional mutant: submit a stale pre-dilution readout.",
        },
    )
    return results


def _lab_serial_dilution_tip_reuse_between_steps(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _lab_inspect_plate_transfer(runtime, run_dir, results)
    _lab_serial_dilution_chain(runtime, run_dir, results, discard_between_steps=False)
    readout = _lab_read_serial_dilution(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B5",
            "rationale": "Intentional mutant: transfers occurred without discarding tips between steps.",
        },
    )
    return results


def _lab_serial_dilution_missing_mix_after_dispense(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _lab_inspect_plate_transfer(runtime, run_dir, results)
    _lab_serial_dilution_chain(
        runtime,
        run_dir,
        results,
        discard_between_steps=True,
        mix_after=False,
    )
    readout = _lab_read_serial_dilution(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B5",
            "rationale": "Intentional mutant: dilution dispenses omitted mix_after.",
        },
    )
    return results


def _lab_serial_dilution_post_dilution_mutation(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _lab_inspect_plate_transfer(runtime, run_dir, results)
    _lab_serial_dilution_chain(runtime, run_dir, results, discard_between_steps=True)
    _call(
        runtime,
        run_dir,
        results,
        "aspirate",
        {"source": "assay_plate:B5", "volume_ul": 50, "tip": "tip_rack_01:A6"},
    )
    _call(
        runtime,
        run_dir,
        results,
        "dispense",
        {"target": "assay_plate:C1", "volume_ul": 50, "mix_after": False},
    )
    _call(runtime, run_dir, results, "discard_tips", {})
    readout = _lab_read_serial_dilution(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B5",
            "rationale": "Intentional mutant: mutate a dilution well after completing the chain.",
        },
    )
    return results


def _lab_serial_dilution_missing_terminal_readout(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _lab_inspect_plate_transfer(runtime, run_dir, results)
    _lab_serial_dilution_chain(runtime, run_dir, results, discard_between_steps=True)
    return results


def _lab_serial_dilution_wrong_decision(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _lab_inspect_plate_transfer(runtime, run_dir, results)
    _lab_serial_dilution_chain(runtime, run_dir, results, discard_between_steps=True)
    readout = _lab_read_serial_dilution(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "hold",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B5",
            "rationale": "Intentional mutant: submit the wrong decision for a valid dilution curve.",
        },
    )
    return results


def _star_plate_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _star_inspect_plate_transfer(runtime, run_dir, results)
    _star_transfer_b1(runtime, run_dir, results)
    readout = _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "OD600 B1 is inside the expected control band.",
        },
    )
    return results


def _star_plate_read_before_transfer(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    readout = _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _star_inspect_plate_transfer(runtime, run_dir, results)
    _star_transfer_b1(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "hold",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: submit a stale pre-transfer readout.",
        },
    )
    return results


def _star_instrument_fault_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _star_inspect_plate_transfer(runtime, run_dir, results)
    _star_transfer_b1(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    readout = _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Retried after instrument_busy and recovered a valid OD600 in band.",
        },
    )
    return results


def _star_instrument_fault_no_retry_after_busy(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _star_inspect_plate_transfer(runtime, run_dir, results)
    _star_transfer_b1(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    return results


def _star_instrument_fault_read_before_transfer_then_retry(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    readout = _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _star_inspect_plate_transfer(runtime, run_dir, results)
    _star_transfer_b1(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "hold",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: submit a recovered but pre-transfer readout.",
        },
    )
    return results


def _star_instrument_fault_wrong_decision_after_recovery(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _star_inspect_plate_transfer(runtime, run_dir, results)
    _star_transfer_b1(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    readout = _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "hold",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: choose the wrong decision after recovery.",
        },
    )
    return results


def _star_instrument_fault_extra_read_after_success(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _star_inspect_plate_transfer(runtime, run_dir, results)
    _star_transfer_b1(runtime, run_dir, results)
    _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    readout = _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime,
        run_dir,
        results,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: extra read after successful recovery.",
        },
    )
    return results


def _lab_limited_tips_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    return _refusal_oracle(
        runtime,
        run_dir,
        labware_ids=("tip_rack_01",),
        note=_refusal_note(
            reason_code="insufficient_tips",
            evidence={"labware_id": "tip_rack_01", "available_tips": 2, "required_tips": 3},
        ),
    )


def _lab_low_reagent_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    return _refusal_oracle(
        runtime,
        run_dir,
        labware_ids=("source_plate",),
        note=_refusal_note(
            reason_code="insufficient_reagent_volume",
            evidence={
                "labware_id": "source_plate",
                "well": "A1",
                "available_volume_ul": 30,
                "required_volume_ul": 50,
            },
        ),
    )


def _star_limited_tips_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    return _refusal_oracle(
        runtime,
        run_dir,
        labware_ids=("tip_rack_01",),
        note=_refusal_note(
            reason_code="insufficient_tips",
            evidence={"labware_id": "tip_rack_01", "available_tips": 2, "required_tips": 3},
        ),
    )


def _star_low_reagent_trough_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    return _refusal_oracle(
        runtime,
        run_dir,
        labware_ids=("reagent_trough",),
        note=_refusal_note(
            reason_code="insufficient_reagent_volume",
            evidence={"labware_id": "reagent_trough", "available_volume_ul": 30, "required_volume_ul": 50},
        ),
    )


def _star_tip_exhaustion_96_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    return _refusal_oracle(
        runtime,
        run_dir,
        labware_ids=("tip_rack_01",),
        note=_refusal_note(
            reason_code="insufficient_96_head_tips",
            evidence={"labware_id": "tip_rack_01", "available_tips": 10, "required_tips": 96},
        ),
    )


def _lab_limited_tips_arbitrary_note(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    return _arbitrary_note(runtime, run_dir, labware_ids=("tip_rack_01",))


def _lab_low_reagent_arbitrary_note(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    return _arbitrary_note(runtime, run_dir, labware_ids=("source_plate",))


def _star_limited_tips_arbitrary_note(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    return _arbitrary_note(runtime, run_dir, labware_ids=("tip_rack_01",))


def _star_low_reagent_trough_arbitrary_note(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    return _arbitrary_note(runtime, run_dir, labware_ids=("reagent_trough",))


def _star_tip_exhaustion_96_arbitrary_note(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    return _arbitrary_note(runtime, run_dir, labware_ids=("tip_rack_01",))


def _lab_low_reagent_partial_transfer_before_refusal(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "source_plate"})
    _call(
        runtime,
        run_dir,
        results,
        "aspirate",
        {"source": "source_plate:A1", "volume_ul": 30, "tip": "tip_rack_01:A1"},
    )
    _call(runtime, run_dir, results, "dispense", {"target": "assay_plate:B1", "volume_ul": 30})
    _call(
        runtime,
        run_dir,
        results,
        "add_workflow_note",
        {
            "note": _refusal_note(
                reason_code="insufficient_reagent_volume",
                evidence={
                    "labware_id": "source_plate",
                    "well": "A1",
                    "available_volume_ul": 30,
                    "required_volume_ul": 50,
                },
            )
        },
    )
    return results


def _star_low_reagent_trough_partial_transfer_before_refusal(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "reagent_trough"})
    _call(runtime, run_dir, results, "pick_up_tips", {"tip_refs": ["tip_rack_01:A1"], "channels": [0]})
    _call(runtime, run_dir, results, "aspirate", {"source": "reagent_trough", "volume_ul": 30})
    _call(runtime, run_dir, results, "dispense", {"target": "assay_plate:B1", "volume_ul": 30})
    _call(
        runtime,
        run_dir,
        results,
        "add_workflow_note",
        {
            "note": _refusal_note(
                reason_code="insufficient_reagent_volume",
                evidence={"labware_id": "reagent_trough", "available_volume_ul": 30, "required_volume_ul": 50},
            )
        },
    )
    return results


def _star_tip_exhaustion_96_non96_workaround_attempt(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "tip_rack_01"})
    _call(runtime, run_dir, results, "pick_up_tips", {"tip_refs": ["tip_rack_01:H12"], "channels": [0]})
    _call(runtime, run_dir, results, "aspirate", {"source": "source_plate:A1", "volume_ul": 30})
    _call(
        runtime,
        run_dir,
        results,
        "add_workflow_note",
        {
            "note": _refusal_note(
                reason_code="insufficient_96_head_tips",
                evidence={"labware_id": "tip_rack_01", "available_tips": 10, "required_tips": 96},
            )
        },
    )
    return results


def _star_tip_exhaustion_96_failed_non96_tip_attempt(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "tip_rack_01"})
    _call(runtime, run_dir, results, "pick_up_tips", {"tip_refs": ["tip_rack_01:H3"], "channels": [0]})
    _call(
        runtime,
        run_dir,
        results,
        "add_workflow_note",
        {
            "note": _refusal_note(
                reason_code="insufficient_96_head_tips",
                evidence={"labware_id": "tip_rack_01", "available_tips": 10, "required_tips": 96},
            )
        },
    )
    return results


def _lab_limited_tips_unsafe_attempt(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "tip_rack_01"})
    _call(
        runtime,
        run_dir,
        results,
        "aspirate",
        {"source": "source_plate:A1", "volume_ul": 50, "tip": "tip_rack_01:A1"},
    )
    return results


def _lab_low_reagent_unsafe_attempt(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "source_plate"})
    _call(
        runtime,
        run_dir,
        results,
        "aspirate",
        {"source": "source_plate:A1", "volume_ul": 50, "tip": "tip_rack_01:A1"},
    )
    return results


def _star_limited_tips_unsafe_attempt(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "tip_rack_01"})
    _call(runtime, run_dir, results, "aspirate", {"source": "source_plate:A1", "volume_ul": 50})
    return results


def _star_low_reagent_trough_unsafe_attempt(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "reagent_trough"})
    _call(runtime, run_dir, results, "pick_up_tips", {"tip_refs": ["tip_rack_01:A1"], "channels": [0]})
    _call(runtime, run_dir, results, "aspirate", {"source": "reagent_trough", "volume_ul": 50})
    return results


def _star_tip_exhaustion_96_unsafe_attempt(
    runtime: WorldRuntime,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "tip_rack_01"})
    _call(runtime, run_dir, results, "pick_up_tips96", {"tip_rack_id": "tip_rack_01"})
    return results


def _lab_inspect_plate_transfer(
    runtime: WorldRuntime,
    run_dir: Path,
    results: list[dict[str, Any]],
) -> None:
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "source_plate"})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "tip_rack_01"})


def _star_inspect_plate_transfer(
    runtime: WorldRuntime,
    run_dir: Path,
    results: list[dict[str, Any]],
) -> None:
    _call(runtime, run_dir, results, "get_deck_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "source_plate"})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "tip_rack_01"})


def _star_transfer_b1(runtime: WorldRuntime, run_dir: Path, results: list[dict[str, Any]]) -> None:
    _call(runtime, run_dir, results, "pick_up_tips", {"tip_refs": ["tip_rack_01:A1"], "channels": [0]})
    _call(runtime, run_dir, results, "aspirate", {"source": "source_plate:A1", "volume_ul": 50})
    _call(runtime, run_dir, results, "dispense", {"target": "assay_plate:B1", "volume_ul": 50})


def _lab_serial_dilution_chain(
    runtime: WorldRuntime,
    run_dir: Path,
    results: list[dict[str, Any]],
    *,
    discard_between_steps: bool,
    mix_after: bool = True,
) -> None:
    for index, (source, target) in enumerate(
        (
            ("source_plate:A1", "assay_plate:B1"),
            ("assay_plate:B1", "assay_plate:B2"),
            ("assay_plate:B2", "assay_plate:B3"),
            ("assay_plate:B3", "assay_plate:B4"),
            ("assay_plate:B4", "assay_plate:B5"),
        ),
        start=1,
    ):
        _call(
            runtime,
            run_dir,
            results,
            "aspirate",
            {"source": source, "volume_ul": 50, "tip": f"tip_rack_01:A{index}"},
        )
        _call(
            runtime,
            run_dir,
            results,
            "dispense",
            {"target": target, "volume_ul": 50, "mix_after": mix_after},
        )
        if discard_between_steps:
            _call(runtime, run_dir, results, "discard_tips", {})


def _lab_read_serial_dilution(
    runtime: WorldRuntime,
    run_dir: Path,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    return _call(
        runtime,
        run_dir,
        results,
        "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1", "B2", "B3", "B4", "B5"]},
    )


def _refusal_oracle(
    runtime: WorldRuntime,
    run_dir: Path,
    *,
    labware_ids: tuple[str, ...],
    note: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    for labware_id in labware_ids:
        _call(runtime, run_dir, results, "get_labware_state", {"labware_id": labware_id})
    _call(runtime, run_dir, results, "add_workflow_note", {"note": note})
    return results


def _arbitrary_note(
    runtime: WorldRuntime,
    run_dir: Path,
    *,
    labware_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_deck_state", {})
    for labware_id in labware_ids:
        _call(runtime, run_dir, results, "get_labware_state", {"labware_id": labware_id})
    _call(runtime, run_dir, results, "add_workflow_note", {"note": "done"})
    return results


def _refusal_note(*, reason_code: str, evidence: dict[str, Any]) -> str:
    return json.dumps(
        {"decision": "refuse", "reason_code": reason_code, "evidence": evidence},
        sort_keys=True,
        separators=(",", ":"),
    )


def _case(
    case_id: str,
    runner: CaseRunner,
    *,
    expected_verifier_ok: bool,
    expected_failure_codes: tuple[str, ...] = (),
) -> StrictCase:
    return StrictCase(
        case_id=case_id,
        runner=runner,
        expected_verifier_ok=expected_verifier_ok,
        expected_failure_codes=expected_failure_codes,
    )


def _mutant(
    family: str,
    case_id: str,
    runner: CaseRunner,
    *expected_failure_codes: str,
) -> StrictMutantDecl:
    return StrictMutantDecl(
        family=family,
        case_id=case_id,
        runner=runner,
        expected_failure_codes=expected_failure_codes,
    )


def _expand_decl(decl: StrictScenarioDecl) -> StrictScenario:
    cases = [_case("oracle", decl.oracle, expected_verifier_ok=True)]
    cases.extend(
        _case(
            mutant.case_id,
            mutant.runner,
            expected_verifier_ok=False,
            expected_failure_codes=mutant.expected_failure_codes,
        )
        for mutant in decl.mutants
    )
    return StrictScenario(decl.world, decl.scenario, tuple(cases))


def _seed_for_scenario(scenario: StrictScenario) -> int | None:
    for decl in STRICT_SCENARIO_DECLS:
        if decl.world == scenario.world and decl.scenario == scenario.scenario:
            return decl.seed
    return None


# ── PCR + Reader xover runners ────────────────────────────────────────────


def _star_pcr_reader_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "tc_close_lid", {})
    _call(runtime, run_dir, results, "tc_set_lid_temp", {"temperature": 105.0})
    _call(runtime, run_dir, results, "tc_get_block_temp", {})
    _call(runtime, run_dir, results, "tc_set_block_temp", {"temperature": 95.0})
    _call(runtime, run_dir, results, "tc_get_block_temp", {})
    _call(runtime, run_dir, results, "tc_set_block_temp", {"temperature": 55.0})
    _call(runtime, run_dir, results, "tc_get_block_temp", {})
    _call(runtime, run_dir, results, "tc_set_block_temp", {"temperature": 72.0})
    _call(runtime, run_dir, results, "tc_get_block_temp", {})
    _call(runtime, run_dir, results, "tc_deactivate", {})
    _call(runtime, run_dir, results, "tc_open_lid", {})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "OD600 B1 inside control band after PCR amplification.",
        },
    )
    return results


def _star_pcr_reader_read_before_pcr(
    runtime: WorldRuntime, run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "plate_reader_open", {})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "tc_close_lid", {})
    _call(runtime, run_dir, results, "tc_set_lid_temp", {"temperature": 105.0})
    _call(runtime, run_dir, results, "tc_set_block_temp", {"temperature": 95.0})
    _call(runtime, run_dir, results, "tc_set_block_temp", {"temperature": 55.0})
    _call(runtime, run_dir, results, "tc_set_block_temp", {"temperature": 72.0})
    _call(runtime, run_dir, results, "tc_deactivate", {})
    _call(runtime, run_dir, results, "tc_open_lid", {})
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "hold",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: submit a stale pre-PCR readout.",
        },
    )
    return results


def _star_pcr_reader_lid_not_closed(
    runtime: WorldRuntime, run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    # Intentional: skip tc_close_lid
    _call(runtime, run_dir, results, "tc_set_lid_temp", {"temperature": 105.0})
    _call(runtime, run_dir, results, "tc_set_block_temp", {"temperature": 95.0})
    _call(runtime, run_dir, results, "tc_get_block_temp", {})
    _call(runtime, run_dir, results, "tc_set_block_temp", {"temperature": 55.0})
    _call(runtime, run_dir, results, "tc_get_block_temp", {})
    _call(runtime, run_dir, results, "tc_set_block_temp", {"temperature": 72.0})
    _call(runtime, run_dir, results, "tc_get_block_temp", {})
    _call(runtime, run_dir, results, "tc_deactivate", {})
    _call(runtime, run_dir, results, "tc_open_lid", {})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: PCR without closing lid.",
        },
    )
    return results


# ── Pump + Scale xover runners ────────────────────────────────────────────


def _star_pump_scale_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "scale_zero", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_tare", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "pump_run_duration", {"speed_rpm": 80, "duration_s": 10.0})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "pump_run_duration", {"speed_rpm": 150, "duration_s": 5.0})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "pump_run_duration", {"speed_rpm": 250, "duration_s": 3.0})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "pump_halt", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "OD600 B1 inside control band after gravimetric cross-validation.",
        },
    )
    return results


def _star_pump_scale_skip_calibration(
    runtime: WorldRuntime, run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    # Intentional: skip scale_zero and scale_tare
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "pump_run_duration", {"speed_rpm": 80, "duration_s": 10.0})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "pump_run_duration", {"speed_rpm": 150, "duration_s": 5.0})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "pump_run_duration", {"speed_rpm": 250, "duration_s": 3.0})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "pump_halt", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: pump without scale calibration.",
        },
    )
    return results


def _star_pump_scale_no_halt(
    runtime: WorldRuntime, run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "scale_zero", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_tare", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "pump_run_duration", {"speed_rpm": 80, "duration_s": 10.0})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "pump_run_duration", {"speed_rpm": 150, "duration_s": 5.0})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "pump_run_duration", {"speed_rpm": 250, "duration_s": 3.0})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    # Intentional: skip pump_halt
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: pump without halting.",
        },
    )
    return results


# ── HS + Reader xover runners ─────────────────────────────────────────────


def _star_hs_reader_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "hs_set_temperature", {"temperature": 37.0})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_shake", {"speed_rpm": 300, "duration_s": 60})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_stop_shaking", {})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_deactivate", {})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "OD600 B1 inside control band after heat+shake incubation.",
        },
    )
    return results


def _star_hs_reader_no_temp_monitoring(
    runtime: WorldRuntime, run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "hs_set_temperature", {"temperature": 37.0})
    # Intentional: no hs_get_temperature calls — blind incubation!
    _call(runtime, run_dir, results, "hs_shake", {"speed_rpm": 300, "duration_s": 60})
    _call(runtime, run_dir, results, "hs_stop_shaking", {})
    _call(runtime, run_dir, results, "hs_deactivate", {})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: incubate without temperature monitoring.",
        },
    )
    return results


def _star_hs_reader_read_before_incubation(
    runtime: WorldRuntime, run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "hs_set_temperature", {"temperature": 37.0})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_shake", {"speed_rpm": 300, "duration_s": 60})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_stop_shaking", {})
    _call(runtime, run_dir, results, "hs_get_temperature", {})
    _call(runtime, run_dir, results, "hs_deactivate", {})
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "hold",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: submit stale pre-incubation readout.",
        },
    )
    return results


# ── Centrifuge + Reader xover runners ────────────────────────────────────


def _star_centrifuge_reader_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "centrifuge_open_door", {})
    _call(runtime, run_dir, results, "centrifuge_go_to_bucket1", {})
    _call(runtime, run_dir, results, "centrifuge_lock_bucket", {})
    _call(runtime, run_dir, results, "centrifuge_close_door", {})
    _call(runtime, run_dir, results, "centrifuge_lock_door", {})
    _call(runtime, run_dir, results, "centrifuge_spin", {"g_force": 2000, "duration_s": 60})
    _call(runtime, run_dir, results, "centrifuge_open_door", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "centrifuge_close_door", {})
    _call(runtime, run_dir, results, "centrifuge_lock_door", {})
    _call(runtime, run_dir, results, "centrifuge_spin", {"g_force": 8000, "duration_s": 120})
    _call(runtime, run_dir, results, "centrifuge_open_door", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B2"]})
    _call(runtime, run_dir, results, "plate_reader_close", {})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "OD600 B1 inside control band after differential centrifugation.",
        },
    )
    return results


def _star_centrifuge_reader_spin_without_lock(
    runtime: WorldRuntime, run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "centrifuge_open_door", {})
    _call(runtime, run_dir, results, "centrifuge_go_to_bucket1", {})
    _call(runtime, run_dir, results, "centrifuge_lock_bucket", {})
    _call(runtime, run_dir, results, "centrifuge_close_door", {})
    # Intentional: skip centrifuge_lock_door — spin with unlocked door!
    _call(runtime, run_dir, results, "centrifuge_spin", {"g_force": 2000, "duration_s": 60})
    _call(runtime, run_dir, results, "centrifuge_open_door", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "centrifuge_close_door", {})
    _call(runtime, run_dir, results, "centrifuge_lock_door", {})
    _call(runtime, run_dir, results, "centrifuge_spin", {"g_force": 8000, "duration_s": 120})
    _call(runtime, run_dir, results, "centrifuge_open_door", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B2"]},
    )
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "hold",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: spin without locking door.",
        },
    )
    return results


# ── Arm + Scale xover runners ─────────────────────────────────────────────


def _star_arm_scale_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "scale_zero", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "arm_home", {})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_open_gripper", {"width_mm": 80.0})
    _call(runtime, run_dir, results, "arm_get_gripper_state", {})
    _call(runtime, run_dir, results, "arm_move_to", {"x": 100, "y": 200, "z": 100})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_approach", {"x": 100, "y": 200, "z": 30, "access": "vertical"})
    _call(runtime, run_dir, results, "arm_close_gripper", {"width_mm": 85.0})
    _call(runtime, run_dir, results, "arm_get_gripper_state", {})
    _call(runtime, run_dir, results, "arm_pick_up_resource",
          {"x": 100, "y": 200, "z": 30, "plate_width_mm": 85.0})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_move_to", {"x": 400, "y": 200, "z": 100})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_approach", {"x": 400, "y": 200, "z": 30, "access": "vertical"})
    _call(runtime, run_dir, results, "arm_drop_resource", {"x": 400, "y": 200, "z": 30})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "scale_get_weight", {})
    _call(runtime, run_dir, results, "arm_close_gripper", {"width_mm": 85.0})
    _call(runtime, run_dir, results, "arm_get_gripper_state", {})
    _call(runtime, run_dir, results, "arm_pick_up_resource",
          {"x": 400, "y": 200, "z": 30, "plate_width_mm": 85.0})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_move_to", {"x": 100, "y": 200, "z": 100})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_approach", {"x": 100, "y": 200, "z": 30})
    _call(runtime, run_dir, results, "arm_drop_resource", {"x": 100, "y": 200, "z": 30})
    _call(runtime, run_dir, results, "arm_move_to_safe", {})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_get_gripper_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "OD600 B1 inside control band after arm transport + gravimetric check.",
        },
    )
    return results


def _star_arm_scale_skip_weigh(
    runtime: WorldRuntime, run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "scale_zero", {})
    # Intentional: skip all scale_get_weight calls — no gravimetric verification!
    _call(runtime, run_dir, results, "arm_home", {})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_open_gripper", {"width_mm": 80.0})
    _call(runtime, run_dir, results, "arm_get_gripper_state", {})
    _call(runtime, run_dir, results, "arm_move_to", {"x": 100, "y": 200, "z": 100})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_approach", {"x": 100, "y": 200, "z": 30, "access": "vertical"})
    _call(runtime, run_dir, results, "arm_close_gripper", {"width_mm": 85.0})
    _call(runtime, run_dir, results, "arm_get_gripper_state", {})
    _call(runtime, run_dir, results, "arm_pick_up_resource",
          {"x": 100, "y": 200, "z": 30, "plate_width_mm": 85.0})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_move_to", {"x": 400, "y": 200, "z": 100})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_approach", {"x": 400, "y": 200, "z": 30, "access": "vertical"})
    _call(runtime, run_dir, results, "arm_drop_resource", {"x": 400, "y": 200, "z": 30})
    _call(runtime, run_dir, results, "arm_close_gripper", {"width_mm": 85.0})
    _call(runtime, run_dir, results, "arm_get_gripper_state", {})
    _call(runtime, run_dir, results, "arm_pick_up_resource",
          {"x": 400, "y": 200, "z": 30, "plate_width_mm": 85.0})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_move_to", {"x": 100, "y": 200, "z": 100})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_approach", {"x": 100, "y": 200, "z": 30})
    _call(runtime, run_dir, results, "arm_drop_resource", {"x": 100, "y": 200, "z": 30})
    _call(runtime, run_dir, results, "arm_move_to_safe", {})
    _call(runtime, run_dir, results, "arm_get_position", {})
    _call(runtime, run_dir, results, "arm_get_gripper_state", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "hold",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: transport without gravimetric verification.",
        },
    )
    return results


# ── TempCtrl + Reader xover runners ──────────────────────────────────────


def _star_tempctrl_reader_oracle(runtime: WorldRuntime, run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "temp_controller_set_temperature", {"temperature": 25.0})
    _call(runtime, run_dir, results, "temp_controller_wait_for_temperature", {"timeout": 60.0})
    _call(runtime, run_dir, results, "temp_controller_get_temperature", {})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "temp_controller_set_temperature", {"temperature": 37.0})
    _call(runtime, run_dir, results, "temp_controller_wait_for_temperature", {"timeout": 60.0})
    _call(runtime, run_dir, results, "temp_controller_get_temperature", {})
    _call(runtime, run_dir, results, "temp_controller_get_temperature", {})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "temp_controller_set_temperature", {"temperature": 45.0})
    _call(runtime, run_dir, results, "temp_controller_wait_for_temperature", {"timeout": 60.0})
    _call(runtime, run_dir, results, "temp_controller_get_temperature", {})
    _call(runtime, run_dir, results, "temp_controller_get_temperature", {})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "temp_controller_deactivate", {})
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "OD600 B1 inside control band across 25/37/45C temperature ramp.",
        },
    )
    return results


def _star_tempctrl_reader_skip_temp_checks(
    runtime: WorldRuntime, run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "temp_controller_set_temperature", {"temperature": 25.0})
    _call(runtime, run_dir, results, "temp_controller_wait_for_temperature", {"timeout": 60.0})
    # Intentional: skip temp_controller_get_temperature — blind temperature!
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "temp_controller_set_temperature", {"temperature": 37.0})
    _call(runtime, run_dir, results, "temp_controller_wait_for_temperature", {"timeout": 60.0})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "temp_controller_set_temperature", {"temperature": 45.0})
    _call(runtime, run_dir, results, "temp_controller_wait_for_temperature", {"timeout": 60.0})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "temp_controller_deactivate", {})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: temperature ramp without verification.",
        },
    )
    return results


def _star_tempctrl_reader_read_before_stable(
    runtime: WorldRuntime, run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    _call(runtime, run_dir, results, "get_labware_state", {"labware_id": "assay_plate"})
    _call(runtime, run_dir, results, "temp_controller_set_temperature", {"temperature": 25.0})
    # Intentional: skip wait_for_temperature — read before stable!
    _call(runtime, run_dir, results, "temp_controller_get_temperature", {})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "temp_controller_set_temperature", {"temperature": 37.0})
    _call(runtime, run_dir, results, "temp_controller_get_temperature", {})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "temp_controller_set_temperature", {"temperature": 45.0})
    _call(runtime, run_dir, results, "temp_controller_get_temperature", {})
    _call(runtime, run_dir, results, "plate_reader_open", {})
    _call(runtime, run_dir, results, "read_absorbance",
          {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]})
    _call(runtime, run_dir, results, "plate_reader_close", {})
    _call(runtime, run_dir, results, "temp_controller_deactivate", {})
    readout = _call(
        runtime, run_dir, results, "read_absorbance",
        {"plate_id": "assay_plate", "wavelength_nm": 600, "wells": ["B1"]},
    )
    _call(
        runtime, run_dir, results, "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": _readout_id(readout),
            "target_well": "assay_plate:B1",
            "rationale": "Intentional mutant: read before temperature stabilized.",
        },
    )
    return results


STRICT_SCENARIO_DECLS: tuple[StrictScenarioDecl, ...] = (
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "arm_scale_xover_qc",
        _star_arm_scale_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "arm_homed",
                "position_checks_ge7",
                "gripper_checks_ge4",
                "arm_transport_ops",
                "drops_ge2",
                "safe_position",
                "scale_zeroed",
                "scale_reads_ge3",
                "weigh_while_on_scale",
                "labware_inspected",
                "readout",
                "submitted",
            ),
            _mutant(
                "skip_gravimetric",
                "skip_weigh",
                _star_arm_scale_skip_weigh,
                "scale_reads_ge3",
                "weigh_while_on_scale",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "centrifuge_reader_xover_qc",
        _star_centrifuge_reader_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "bucket_accessed",
                "bucket_locked",
                "door_opens_ge2",
                "door_closes_ge2",
                "door_locks_ge2",
                "spins_ge2",
                "door_locked_before_each_spin",
                "two_g_forces",
                "labware_before_spin",
                "labware_between_spins",
                "labware_after_spin",
                "absorbance_reads_ge2",
                "reader_opened",
                "reader_closed",
                "readout",
                "submitted",
            ),
            _mutant(
                "spin_without_lock",
                "spin_without_lock",
                _star_centrifuge_reader_spin_without_lock,
                "door_locks_ge2",
                "spins_ge2",
                "two_g_forces",
                "labware_before_spin",
                "labware_between_spins",
                "labware_after_spin",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "tempctrl_reader_xover_qc",
        _star_tempctrl_reader_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "temp_sets_ge3",
                "wait_calls_ge3",
                "temp_reads_ge3",
                "tc_deactivated",
                "absorbance_reads_ge3",
                "reader_opens_ge3",
                "reader_closes_ge3",
                "temp_before_each_read",
                "reader_open_read_close_cycles",
                "labware_inspected",
                "readout",
                "submitted",
            ),
            _mutant(
                "skip_temp_verification",
                "skip_temp_checks",
                _star_tempctrl_reader_skip_temp_checks,
                "temp_reads_ge3",
                "temp_before_each_read",
            ),
            _mutant(
                "read_before_stable",
                "read_before_stable",
                _star_tempctrl_reader_read_before_stable,
                "wait_calls_ge3",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "hs_reader_xover_qc",
        _star_hs_reader_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "hs_temp_set",
                "temp_reads_ge5",
                "hs_shake",
                "hs_shake_stop",
                "hs_deactivated",
                "temp_before_shake",
                "temp_during_shake",
                "temp_after_shake",
                "reader_opened",
                "reader_closed",
                "readout_after_incubation",
                "labware_inspected",
                "readout",
                "submitted",
            ),
            _mutant(
                "no_temp_monitoring",
                "no_temp_monitoring",
                _star_hs_reader_no_temp_monitoring,
                "temp_reads_ge5",
                "temp_before_shake",
                "temp_during_shake",
                "temp_after_shake",
            ),
            _mutant(
                "stale_evidence",
                "read_before_incubation",
                _star_hs_reader_read_before_incubation,
                "hs_deactivated_before_read",
                "readout_after_incubation",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "pump_scale_xover_qc",
        _star_pump_scale_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "scale_zeroed",
                "scale_tared",
                "pump_ops_ge3",
                "pump_halted",
                "weight_readings_ge8",
                "weight_after_each_pump",
                "weight_stability",
                "cumulative_weight_increasing",
                "labware_before_pump",
                "labware_after_pump",
                "readout",
                "submitted",
            ),
            _mutant(
                "skip_calibration",
                "skip_calibration",
                _star_pump_scale_skip_calibration,
                "scale_zeroed",
                "scale_tared",
            ),
            _mutant(
                "no_halt",
                "no_halt",
                _star_pump_scale_no_halt,
                "pump_halted",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_lab_v0",
        "plate_transfer_qc",
        _lab_plate_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "valid_transfer_completed",
                "readout_recorded",
                "protocol_submitted",
                "submitted_target_matches_expected",
                "decision_matches_observed_data",
            ),
            _mutant(
                "wrong_decision",
                "wrong_decision",
                _lab_plate_wrong_decision,
                "decision_matches_observed_data",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_lab_v0",
        "serial_dilution_qc",
        _lab_serial_dilution_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "dilution_transfer_sequence",
                "fresh_tip_per_dilution_step",
                "mix_after_each_dilution_step",
                "all_dilution_wells_read",
                "after(dilution, readout)",
                "provenance(readout, dilution_series)",
                "od600_decreasing_curve",
                "protocol_submitted",
                "decision_matches_dilution_curve",
            ),
            _mutant(
                "stale_evidence",
                "read_before_dilution",
                _lab_serial_dilution_read_before_dilution,
                "after(dilution, readout)",
                "provenance(readout, dilution_series)",
                "od600_decreasing_curve",
            ),
            _mutant(
                "tip_reuse_between_steps",
                "tip_reuse_between_steps",
                _lab_serial_dilution_tip_reuse_between_steps,
                "fresh_tip_per_dilution_step",
            ),
            _mutant(
                "missing_mix_after_dispense",
                "missing_mix_after_dispense",
                _lab_serial_dilution_missing_mix_after_dispense,
                "mix_after_each_dilution_step",
            ),
            _mutant(
                "post_dilution_mutation",
                "post_dilution_mutation",
                _lab_serial_dilution_post_dilution_mutation,
                "dilution_well_volumes_intact",
            ),
            _mutant(
                "missing_terminal_readout",
                "missing_terminal_readout",
                _lab_serial_dilution_missing_terminal_readout,
                "all_dilution_wells_read",
                "after(dilution, readout)",
                "provenance(readout, dilution_series)",
                "od600_decreasing_curve",
                "protocol_submitted",
                "decision_matches_dilution_curve",
            ),
            _mutant(
                "wrong_decision",
                "wrong_decision",
                _lab_serial_dilution_wrong_decision,
                "decision_matches_dilution_curve",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "plate_transfer_qc",
        _star_plate_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "valid_transfer",
                "readout_recorded",
                "protocol_submitted",
                "after(transfer, read)",
                "provenance(readout, transfer)",
            ),
            _mutant(
                "stale_evidence",
                "read_before_transfer",
                _star_plate_read_before_transfer,
                "after(transfer, read)",
                "provenance(readout, transfer)",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_lab_v0",
        "limited_tips_qc",
        _lab_limited_tips_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "terminal_intent_exists",
                "relevant_labware_inspected",
                "structured_refusal_intent",
            ),
            _mutant(
                "arbitrary_note",
                "arbitrary_note",
                _lab_limited_tips_arbitrary_note,
                "structured_refusal_intent",
            ),
            _mutant(
                "unsafe_resource_attempt",
                "unsafe_attempt",
                _lab_limited_tips_unsafe_attempt,
                "terminal_intent_exists",
                "structured_refusal_intent",
                "no_unavailable_tip_attempt",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_lab_v0",
        "low_reagent_qc",
        _lab_low_reagent_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "terminal_intent_exists",
                "relevant_labware_inspected",
                "structured_refusal_intent",
            ),
            _mutant(
                "arbitrary_note",
                "arbitrary_note",
                _lab_low_reagent_arbitrary_note,
                "structured_refusal_intent",
            ),
            _mutant(
                "unsafe_resource_attempt",
                "unsafe_attempt",
                _lab_low_reagent_unsafe_attempt,
                "terminal_intent_exists",
                "structured_refusal_intent",
                "no_overdraw_attempt",
            ),
            _mutant(
                "partial_action_before_refusal",
                "partial_transfer_before_refusal",
                _lab_low_reagent_partial_transfer_before_refusal,
                "no_transfer_before_refusal",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "limited_tips_star_qc",
        _star_limited_tips_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "terminal_intent_exists",
                "relevant_labware_inspected",
                "structured_refusal_intent",
            ),
            _mutant(
                "arbitrary_note",
                "arbitrary_note",
                _star_limited_tips_arbitrary_note,
                "structured_refusal_intent",
            ),
            _mutant(
                "unsafe_resource_attempt",
                "unsafe_attempt",
                _star_limited_tips_unsafe_attempt,
                "terminal_intent_exists",
                "structured_refusal_intent",
                "no_unavailable_tip_attempt",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "low_reagent_trough_qc",
        _star_low_reagent_trough_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "terminal_intent_exists",
                "relevant_labware_inspected",
                "structured_refusal_intent",
            ),
            _mutant(
                "arbitrary_note",
                "arbitrary_note",
                _star_low_reagent_trough_arbitrary_note,
                "structured_refusal_intent",
            ),
            _mutant(
                "unsafe_resource_attempt",
                "unsafe_attempt",
                _star_low_reagent_trough_unsafe_attempt,
                "terminal_intent_exists",
                "structured_refusal_intent",
                "no_overdraw_attempt",
            ),
            _mutant(
                "partial_action_before_refusal",
                "partial_transfer_before_refusal",
                _star_low_reagent_trough_partial_transfer_before_refusal,
                "no_transfer_before_refusal",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "tip_exhaustion_96_star_qc",
        _star_tip_exhaustion_96_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "terminal_intent_exists",
                "relevant_labware_inspected",
                "structured_refusal_intent",
            ),
            _mutant(
                "arbitrary_note",
                "arbitrary_note",
                _star_tip_exhaustion_96_arbitrary_note,
                "structured_refusal_intent",
            ),
            _mutant(
                "unsafe_resource_attempt",
                "unsafe_attempt",
                _star_tip_exhaustion_96_unsafe_attempt,
                "terminal_intent_exists",
                "structured_refusal_intent",
                "no_96_pickup_insufficient_tips",
            ),
            _mutant(
                "non96_workaround_attempt",
                "non96_workaround_attempt",
                _star_tip_exhaustion_96_non96_workaround_attempt,
                "no_non96_transfer_attempt",
            ),
            _mutant(
                "failed_tool_then_false_success",
                "failed_non96_tip_attempt",
                _star_tip_exhaustion_96_failed_non96_tip_attempt,
                "no_non96_transfer_attempt",
            ),
        ),
    ),
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "instrument_fault_star_qc",
        _star_instrument_fault_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "transfer",
                "instrument_busy_observed",
                "valid_readout",
                "submitted",
            ),
            _mutant(
                "fault_recovery",
                "no_retry_after_busy",
                _star_instrument_fault_no_retry_after_busy,
                "valid_readout",
                "submitted",
            ),
            _mutant(
                "stale_evidence",
                "read_before_transfer_then_retry",
                _star_instrument_fault_read_before_transfer_then_retry,
                "after(transfer, readout)",
            ),
            _mutant(
                "fault_recovery",
                "wrong_decision_after_recovery",
                _star_instrument_fault_wrong_decision_after_recovery,
                "decision_matches_observed_data",
            ),
            _mutant(
                "extra_retry_after_success",
                "extra_read_after_success",
                _star_instrument_fault_extra_read_after_success,
                "no_extra_readout_after_recovery",
            ),
        ),
        seed=10001,
    ),
    StrictScenarioDecl(
        "pylabrobot_star_v0",
        "pcr_reader_xover_qc",
        _star_pcr_reader_oracle,
        (
            _mutant(
                "empty_plan",
                "empty",
                _empty,
                "tc_lid_closed",
                "tc_lid_temp_set",
                "block_temp_sets_ge3",
                "block_temp_reads_ge3",
                "block_readback_paired",
                "tc_deactivated",
                "tc_lid_opened",
                "reader_opened",
                "reader_closed",
                "readout_after_cycling",
                "labware_inspected",
                "readout",
                "submitted",
            ),
            _mutant(
                "stale_evidence",
                "read_before_pcr",
                _star_pcr_reader_read_before_pcr,
                "block_temp_reads_ge3",
                "block_readback_paired",
                "readout_after_cycling",
            ),
            _mutant(
                "lid_safety",
                "lid_not_closed",
                _star_pcr_reader_lid_not_closed,
                "tc_lid_closed",
            ),
        ),
    ),
)


STRICT_SCENARIOS: tuple[StrictScenario, ...] = tuple(
    _expand_decl(decl) for decl in STRICT_SCENARIO_DECLS
)
