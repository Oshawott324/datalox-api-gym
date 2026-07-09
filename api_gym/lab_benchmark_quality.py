"""Benchmark-quality reporting for the strict lab admission suite."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


SPLIT_IDS = ("dev", "test_family_heldout", "test_fault_heldout")
MILESTONE_IDS = (
    "target_action",
    "resource_check_before_action",
    "fresh_evidence_before_submit",
    "decision_matches_observation",
    "recover_after_fault",
    "collateral_damage_avoidance",
)

_RESOURCE_SCENARIOS = frozenset(
    {
        ("pylabrobot_lab_v0", "limited_tips_qc"),
        ("pylabrobot_lab_v0", "low_reagent_qc"),
        ("pylabrobot_star_v0", "limited_tips_star_qc"),
        ("pylabrobot_star_v0", "low_reagent_trough_qc"),
        ("pylabrobot_star_v0", "tip_exhaustion_96_star_qc"),
    }
)
_TARGET_ACTION_SCENARIOS = frozenset(
    {
        ("pylabrobot_lab_v0", "plate_transfer_qc"),
        ("pylabrobot_lab_v0", "serial_dilution_qc"),
        ("pylabrobot_star_v0", "plate_transfer_qc"),
        ("pylabrobot_star_v0", "instrument_fault_star_qc"),
    }
)
_FRESH_EVIDENCE_CODES = frozenset(
    {
        "after(transfer, read)",
        "after(transfer, readout)",
        "after(dilution, readout)",
        "provenance(readout, transfer)",
        "provenance(readout, dilution_series)",
    }
)
_RECOVER_AFTER_FAULT_CASES = frozenset(
    {
        ("pylabrobot_star_v0", "instrument_fault_star_qc", "oracle"),
        ("pylabrobot_star_v0", "instrument_fault_star_qc", "no_retry_after_busy"),
        ("pylabrobot_star_v0", "instrument_fault_star_qc", "wrong_decision_after_recovery"),
        ("pylabrobot_star_v0", "instrument_fault_star_qc", "extra_read_after_success"),
    }
)
_COLLATERAL_MUTANT_FAMILIES = frozenset(
    {
        "unsafe_resource_attempt",
        "partial_action_before_refusal",
        "non96_workaround_attempt",
        "extra_retry_after_success",
        "tip_reuse_between_steps",
        "missing_mix_after_dispense",
        "post_dilution_mutation",
    }
)
_MILESTONE_FAILURE_CODES: dict[str, frozenset[str]] = {
    "target_action": frozenset(
        {
            "transfer",
            "valid_transfer",
            "valid_transfer_completed",
            "dilution_transfer_sequence",
        }
    ),
    "resource_check_before_action": frozenset(
        {
            "terminal_intent_exists",
            "relevant_labware_inspected",
            "structured_refusal_intent",
            "no_unavailable_tip_attempt",
            "no_overdraw_attempt",
            "no_transfer_before_refusal",
            "no_96_pickup_insufficient_tips",
            "no_non96_transfer_attempt",
            "fresh_tip_per_dilution_step",
            "mix_after_each_dilution_step",
            "dilution_well_volumes_intact",
        }
    ),
    "fresh_evidence_before_submit": frozenset(
        {
            "after(transfer, read)",
            "after(transfer, readout)",
            "after(dilution, readout)",
            "provenance(readout, transfer)",
            "provenance(readout, dilution_series)",
            "valid_readout",
            "all_dilution_wells_read",
        }
    ),
    "decision_matches_observation": frozenset(
        {
            "decision_matches_observed_data",
            "decision_matches_dilution_curve",
            "od600_decreasing_curve",
        }
    ),
    "recover_after_fault": frozenset(
        {
            "valid_readout",
            "submitted",
        }
    ),
    "collateral_damage_avoidance": frozenset(
        {
            "no_unavailable_tip_attempt",
            "no_overdraw_attempt",
            "no_transfer_before_refusal",
            "no_96_pickup_insufficient_tips",
            "no_non96_transfer_attempt",
            "no_extra_readout_after_recovery",
            "fresh_tip_per_dilution_step",
            "mix_after_each_dilution_step",
            "dilution_well_volumes_intact",
        }
    ),
}


def build_admission_matrix() -> dict[str, Any]:
    """Return one quality row per strict admission case."""
    from api_gym.lab_strict_admission import STRICT_SCENARIO_DECLS, STRICT_SCENARIOS

    decls_by_scenario = {
        (decl.world, decl.scenario): decl for decl in STRICT_SCENARIO_DECLS
    }
    rows: list[dict[str, Any]] = []
    mutant_families: set[str] = set()

    for scenario in STRICT_SCENARIOS:
        decl = decls_by_scenario[(scenario.world, scenario.scenario)]
        mutants_by_case_id = {mutant.case_id: mutant for mutant in decl.mutants}
        for case in scenario.cases:
            mutant = mutants_by_case_id.get(case.case_id)
            mutant_family = mutant.family if mutant is not None else None
            if mutant_family is not None:
                mutant_families.add(mutant_family)

            expected_failure_codes = list(case.expected_failure_codes)
            rows.append(
                {
                    "world": scenario.world,
                    "scenario": scenario.scenario,
                    "case_id": case.case_id,
                    "case_kind": "oracle" if case.case_id == "oracle" else "mutant",
                    "mutant_family": mutant_family,
                    "expected_failure_codes": expected_failure_codes,
                    "milestones": _milestones_for_case(
                        world=scenario.world,
                        scenario=scenario.scenario,
                        case_id=case.case_id,
                        mutant_family=mutant_family,
                        expected_failure_codes=expected_failure_codes,
                    ),
                    "split": _split_for_case(
                        world=scenario.world,
                        scenario=scenario.scenario,
                        case_id=case.case_id,
                    ),
                }
            )

    split_counts = Counter(row["split"] for row in rows)
    return {
        "rows": rows,
        "summary": {
            "scenarios": len(STRICT_SCENARIOS),
            "cases": len(rows),
            "mutant_families": len(mutant_families),
            "splits": {split: split_counts[split] for split in SPLIT_IDS},
        },
    }


def summarize_quality_results(case_results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate pass counts by benchmark split and milestone."""
    split_counts = {split: {"cases": 0, "passed_cases": 0} for split in SPLIT_IDS}
    milestone_counts = {
        milestone: {"cases": 0, "passed_cases": 0} for milestone in MILESTONE_IDS
    }

    for case in case_results:
        case_ok = bool(case["ok"])
        split = str(case["split"])
        milestone_results = case["milestone_results"]
        split_counts.setdefault(split, {"cases": 0, "passed_cases": 0})
        split_counts[split]["cases"] += 1
        if case_ok:
            split_counts[split]["passed_cases"] += 1

        for milestone in case["milestones"]:
            milestone_counts.setdefault(milestone, {"cases": 0, "passed_cases": 0})
            milestone_counts[milestone]["cases"] += 1
            milestone_result = milestone_results[milestone]
            milestone_ok = bool(milestone_result["outcome_matched"])
            if milestone_ok:
                milestone_counts[milestone]["passed_cases"] += 1

    return {
        "milestones": milestone_counts,
        "splits": split_counts,
    }


def build_milestone_results(
    *,
    milestone_ids: Iterable[str],
    expected_failure_codes: Iterable[str],
    failed_check_names: Iterable[str],
    admission_ok: bool,
) -> dict[str, dict[str, Any]]:
    """Build deterministic per-milestone outcome records for a case result."""
    expected_failure_list = list(expected_failure_codes)
    failed_check_list = list(failed_check_names)
    milestone_results: dict[str, dict[str, Any]] = {}

    for milestone_id in milestone_ids:
        relevant_codes = _MILESTONE_FAILURE_CODES.get(milestone_id, frozenset())
        milestone_expected_failure_codes = [
            code for code in expected_failure_list if code in relevant_codes
        ]
        milestone_failed_check_names = [
            name for name in failed_check_list if name in relevant_codes
        ]
        expected_observed_ok = not milestone_expected_failure_codes
        observed_ok = not milestone_failed_check_names
        milestone_results[milestone_id] = {
            "admission_ok": admission_ok,
            "expected_failure_codes": milestone_expected_failure_codes,
            "expected_observed_ok": expected_observed_ok,
            "failed_check_names": milestone_failed_check_names,
            "observed_ok": observed_ok,
            "outcome_matched": (
                observed_ok == expected_observed_ok
                and Counter(milestone_failed_check_names)
                == Counter(milestone_expected_failure_codes)
            ),
        }

    return milestone_results


def _split_for_case(*, world: str, scenario: str, case_id: str) -> str:
    if world == "pylabrobot_star_v0" and scenario == "tip_exhaustion_96_star_qc":
        return "test_family_heldout"
    if world == "pylabrobot_star_v0" and scenario == "instrument_fault_star_qc":
        return "test_fault_heldout"
    return "dev"


def _milestones_for_case(
    *,
    world: str,
    scenario: str,
    case_id: str,
    mutant_family: str | None,
    expected_failure_codes: list[str],
) -> list[str]:
    scenario_key = (world, scenario)
    case_key = (world, scenario, case_id)
    failure_code_set = set(expected_failure_codes)
    milestones: list[str] = []

    if scenario_key in _TARGET_ACTION_SCENARIOS:
        milestones.append("target_action")
    if (
        scenario_key in _RESOURCE_SCENARIOS
        or "relevant_labware_inspected" in failure_code_set
        or "fresh_tip_per_dilution_step" in failure_code_set
        or "mix_after_each_dilution_step" in failure_code_set
        or "dilution_well_volumes_intact" in failure_code_set
    ):
        milestones.append("resource_check_before_action")
    if scenario_key in _TARGET_ACTION_SCENARIOS or failure_code_set & _FRESH_EVIDENCE_CODES:
        milestones.append("fresh_evidence_before_submit")
    if (
        scenario_key in _TARGET_ACTION_SCENARIOS
        or "decision_matches_observed_data" in failure_code_set
        or "decision_matches_dilution_curve" in failure_code_set
        or "od600_decreasing_curve" in failure_code_set
    ):
        milestones.append("decision_matches_observation")
    if case_key in _RECOVER_AFTER_FAULT_CASES:
        milestones.append("recover_after_fault")
    if mutant_family in _COLLATERAL_MUTANT_FAMILIES:
        milestones.append("collateral_damage_avoidance")

    return milestones
