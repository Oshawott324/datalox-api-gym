"""Executable oracle plan and requirement-scoped mutation operators."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable


Action = dict[str, Any]
Plan = list[Action]

PLATE_ID = "yeast_growth_plate"
WELLS = [f"A{i}" for i in range(1, 9)]


def action(name: str, **arguments: Any) -> Action:
    return {"name": name, "arguments": arguments}


def oracle_plan() -> Plan:
    plan = [
        action("inspect_workcell"),
        action("reader_open"),
        action("reader_load_plate", plate_id=PLATE_ID),
        action("reader_close"),
        action("reader_set_temperature", temperature_c=30.0),
        action("advance_logical_time", seconds=400.0),
        action("reader_get_temperature"),
        action("reader_start_shaking", shake_type="ORBITAL", frequency_setting=3),
        action("reader_read_absorbance", plate_id=PLATE_ID, wavelength_nm=600, wells=WELLS),
    ]
    for _ in range(600):
        plan.append(action("advance_logical_time", seconds=120.0))
        plan.append(
            action(
                "reader_read_absorbance",
                plate_id=PLATE_ID,
                wavelength_nm=600,
                wells=WELLS,
            )
        )
    plan.extend(
        [
            action(
                "submit_growth_decision",
                decision="accept",
                evidence_measurement_id="measurement-0601",
                rationale="The complete 20-hour series meets the declared acquisition contract.",
            ),
            action("advance_logical_time", seconds=1.0),
            action("reader_stop_shaking"),
            action("reader_stop_temperature"),
        ]
    )
    return plan


def _kinetic_advances(plan: Plan) -> list[Action]:
    first_read = next(i for i, item in enumerate(plan) if item["name"] == "reader_read_absorbance")
    return [item for item in plan[first_read + 1 :] if item["name"] == "advance_logical_time"][:-1]


def _reads(plan: Plan) -> list[Action]:
    return [item for item in plan if item["name"] == "reader_read_absorbance"]


def temperature_set_without_stabilization(plan: Plan) -> Plan:
    mutated = deepcopy(plan)
    del mutated[5:7]
    return mutated


def insufficient_incubation_exposure(plan: Plan) -> Plan:
    mutated = deepcopy(plan)
    reads_seen = 0
    keep: Plan = []
    for item in mutated:
        if item["name"] == "reader_read_absorbance":
            reads_seen += 1
        if reads_seen > 301 and item["name"] in {"reader_read_absorbance", "advance_logical_time"}:
            continue
        keep.append(item)
    submission = next(item for item in keep if item["name"] == "submit_growth_decision")
    submission["arguments"]["evidence_measurement_id"] = "measurement-0301"
    return keep


def measurement_outside_cadence_window(plan: Plan) -> Plan:
    mutated = deepcopy(plan)
    advances = _kinetic_advances(mutated)
    advances[0]["arguments"]["seconds"] = 126.0
    advances[1]["arguments"]["seconds"] = 114.0
    return mutated


def shaking_interrupted(plan: Plan) -> Plan:
    mutated = deepcopy(plan)
    reads = _reads(mutated)
    target = reads[300]
    index = mutated.index(target)
    mutated[index:index] = [action("reader_stop_shaking")]
    mutated[index + 2:index + 2] = [
        action("reader_start_shaking", shake_type="ORBITAL", frequency_setting=3)
    ]
    return mutated


def wrong_wavelength(plan: Plan) -> Plan:
    mutated = deepcopy(plan)
    _reads(mutated)[300]["arguments"]["wavelength_nm"] = 590
    return mutated


def missing_replicate(plan: Plan) -> Plan:
    mutated = deepcopy(plan)
    _reads(mutated)[300]["arguments"]["wells"] = WELLS[:-1]
    return mutated


def decision_from_incomplete_series(plan: Plan) -> Plan:
    mutated = deepcopy(plan)
    submission = next(item for item in mutated if item["name"] == "submit_growth_decision")
    submission["arguments"]["evidence_measurement_id"] = "measurement-0301"
    return mutated


def cadence_at_declared_tolerance(plan: Plan) -> Plan:
    mutated = deepcopy(plan)
    advances = _kinetic_advances(mutated)
    advances[0]["arguments"]["seconds"] = 125.0
    advances[1]["arguments"]["seconds"] = 115.0
    return mutated


def temperature_at_declared_tolerance(plan: Plan) -> Plan:
    mutated = deepcopy(plan)
    mutated[5]["arguments"]["seconds"] = 375.0
    return mutated


@dataclass(frozen=True)
class PlanCase:
    case_id: str
    operator: str
    requirement: str
    transform: Callable[[Plan], Plan]
    expected_failure_codes: tuple[str, ...]


MUTANTS: tuple[PlanCase, ...] = (
    PlanCase(
        "temperature_set_without_stabilization",
        "drop_actions",
        "temperature_stabilized_before_series",
        temperature_set_without_stabilization,
        ("temperature_stabilized_before_series", "decision_supported_by_complete_series"),
    ),
    PlanCase(
        "insufficient_incubation_exposure",
        "truncate_interval",
        "kinetic_duration_complete",
        insufficient_incubation_exposure,
        (
            "measurement_cadence_complete",
            "kinetic_duration_complete",
            "decision_supported_by_complete_series",
        ),
    ),
    PlanCase(
        "measurement_outside_cadence_window",
        "shift_scheduled_event",
        "measurement_cadence_complete",
        measurement_outside_cadence_window,
        ("measurement_cadence_complete", "decision_supported_by_complete_series"),
    ),
    PlanCase(
        "shaking_interrupted",
        "interrupt_interval",
        "continuous_orbital_shaking",
        shaking_interrupted,
        ("continuous_orbital_shaking", "decision_supported_by_complete_series"),
    ),
    PlanCase(
        "wrong_wavelength",
        "replace_parameter",
        "correct_wavelength",
        wrong_wavelength,
        ("correct_wavelength", "decision_supported_by_complete_series"),
    ),
    PlanCase(
        "missing_replicate",
        "drop_entity",
        "required_replicates_present",
        missing_replicate,
        ("required_replicates_present", "decision_supported_by_complete_series"),
    ),
    PlanCase(
        "decision_from_incomplete_series",
        "truncate_evidence",
        "decision_supported_by_complete_series",
        decision_from_incomplete_series,
        ("decision_supported_by_complete_series",),
    ),
)

NEAR_MISSES: tuple[PlanCase, ...] = (
    PlanCase(
        "cadence_at_declared_tolerance",
        "shift_scheduled_event",
        "measurement_cadence_complete",
        cadence_at_declared_tolerance,
        (),
    ),
    PlanCase(
        "temperature_at_declared_tolerance",
        "shift_scheduled_event",
        "temperature_stabilized_before_series",
        temperature_at_declared_tolerance,
        (),
    ),
    PlanCase(
        "minimum_duration_and_replicates",
        "identity",
        "kinetic_duration_complete,required_replicates_present",
        deepcopy,
        (),
    ),
)
