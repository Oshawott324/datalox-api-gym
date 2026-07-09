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


STRICT_SCENARIO_DECLS: tuple[StrictScenarioDecl, ...] = (
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
)


STRICT_SCENARIOS: tuple[StrictScenario, ...] = tuple(
    _expand_decl(decl) for decl in STRICT_SCENARIO_DECLS
)
