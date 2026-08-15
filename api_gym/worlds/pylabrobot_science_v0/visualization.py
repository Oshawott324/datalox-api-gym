"""Portable visualizations for the three instrument-rich science workflows."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from pylabrobot.resources import Coordinate, Resource

from .contracts import (
    INCUBATOR_SCENARIO,
    POWDER_SCENARIO,
    SCENARIO_CONTRACTS,
    THERMOCYCLER_SCENARIO,
)
from .dynamics import amplification_series
from .plans import ORACLE_PLANS, run_plan
from .sampler import WORLD, sample_episode
from .verifier import verify_run


VISUALIZATION_RUN_SCHEMA = "datalox_visualization_run_v1"
VISUALIZATION_RENDERER_ID = "pylabrobot_visualizer_v1"
PYLABROBOT_PROTOCOL_VERSION = "0.1.0"
PYLABROBOT_VIEWER_PACKAGE_VERSION = "0.2.2"


def export_science_visualization(*, scenario: str, destination: Path) -> dict[str, Any]:
    """Execute one reference workflow and write its public visualization document."""

    if scenario not in SCENARIO_CONTRACTS:
        raise ValueError(f"Unsupported visualization scenario: {scenario}")
    with tempfile.TemporaryDirectory(prefix="datalox-science-visualization-") as temporary:
        episode = sample_episode(
            scenario=scenario,
            seed=1,
            out_dir=Path(temporary) / "run",
        )
        operations = run_plan(episode.run_dir, ORACLE_PLANS[scenario])
        if not operations or not all(item["result"]["ok"] for item in operations):
            raise RuntimeError(f"Reference workflow failed for {scenario}")
        verification = verify_run(episode.run_dir)
        if not verification.ok:
            raise RuntimeError(f"Reference workflow did not verify for {scenario}")
    document = build_science_visualization(scenario=scenario, operations=operations)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return document


def build_science_visualization(
    *, scenario: str, operations: list[dict[str, Any]]
) -> dict[str, Any]:
    contract = SCENARIO_CONTRACTS[scenario]
    visible_operations = [item for item in operations if item["name"] != "inspect_science_workcell"]
    artifacts = _artifacts(visible_operations)
    tracker = _initial_tracker(scenario, contract)
    steps = [
        _step(
            scenario=scenario,
            sequence=index,
            operation=operation,
            tracker=tracker,
            contract=contract,
        )
        for index, operation in enumerate(visible_operations, start=1)
    ]
    metadata = _presentation_metadata(scenario)
    return {
        "schema_version": VISUALIZATION_RUN_SCHEMA,
        "run_id": f"{scenario}-seed-1",
        "world_id": WORLD,
        "presentation": {
            "title": metadata["title"],
            "summary": metadata["summary"],
            "subject": metadata["subject"],
            "mode": "dry_run",
            "status": "completed",
            "agent": None,
        },
        "workflow": {
            "stages": [
                {
                    "id": "execution",
                    "label": metadata["stage"],
                    "kind": "lab_automation",
                    "provider": "PyLabRobot",
                    "status": "completed",
                },
                {
                    "id": "decision",
                    "label": "Evidence-linked decision",
                    "kind": "workflow_decision",
                    "provider": None,
                    "status": "completed",
                },
            ],
            "edges": [{"from": "execution", "to": "decision"}],
        },
        "renderer": {
            "id": VISUALIZATION_RENDERER_ID,
            "protocol_version": PYLABROBOT_PROTOCOL_VERSION,
            "payload": {
                "capture_package_version": "0.2.1",
                "viewer_package_version": PYLABROBOT_VIEWER_PACKAGE_VERSION,
                "initialization": _initialization(scenario),
            },
        },
        "resources": _resources(scenario),
        "artifacts": artifacts,
        "steps": steps,
        "outcome": None,
    }


def _step(
    *,
    scenario: str,
    sequence: int,
    operation: dict[str, Any],
    tracker: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    name = operation["name"]
    result = operation["result"]["data"]
    title, description = _copy(name, result)
    if name == "submit_science_decision":
        scene = _decision_scene(result, operation["arguments"])
        phase_id = "decision"
    elif scenario == THERMOCYCLER_SCENARIO:
        scene = _thermocycler_scene(name, result, tracker, contract)
        phase_id = "execution"
    elif scenario == INCUBATOR_SCENARIO:
        scene = _incubator_scene(name, result, tracker, contract)
        phase_id = "execution"
    else:
        scene = _powder_scene(name, result, tracker, contract)
        phase_id = "execution"
    artifact_id = result.get("artifact_id")
    return {
        "sequence": sequence,
        "phase_id": phase_id,
        "operation_id": f"{name}-{sequence}",
        "title": title,
        "description": description,
        "simulated_at": _simulated_at(tracker),
        "duration_ms": _duration_ms(name),
        "status": "completed",
        "render": {"commands": []},
        "scene": scene,
        "facts": _facts(name, result),
        "state_changes": [],
        "artifact_ids": [artifact_id] if artifact_id else [],
    }


def _thermocycler_scene(
    name: str,
    result: dict[str, Any],
    tracker: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    lid_motion = "stationary"
    if name == "thermocycler_close_lid":
        tracker["lid_open"] = False
        lid_motion = "closing"
    elif name == "thermocycler_open_lid":
        tracker["lid_open"] = True
        lid_motion = "opening"
    elif name == "thermocycler_set_lid_temperature":
        tracker["lid_temperature_c"] = float(result["lid_target_temperature_c"])
    elif name == "thermocycler_start_protocol":
        tracker.update(
            {
                "block_temperature_c": 95.0,
                "cycle": 0,
                "total_cycles": int(result["total_cycles"]),
                "stage": "Initial denaturation",
                "hold_elapsed_s": 0.0,
                "hold_total_s": 120.0,
                "run_progress": 0,
            }
        )
    elif name in {"thermocycler_advance_time", "thermocycler_get_status"}:
        tracker["clock_s"] = float(result["elapsed_s"])
        tracker["block_temperature_c"] = float(result["block_temperature_c"])
        tracker["lid_temperature_c"] = float(result["lid_temperature_c"])
        tracker["cycle"] = min(int(result["total_cycles"]), int(result["cycle_index"]) + 1)
        tracker["total_cycles"] = int(result["total_cycles"])
        tracker["stage"] = _thermal_stage_name(result)
        tracker["hold_elapsed_s"] = float(result["hold_elapsed_s"])
        tracker["hold_total_s"] = float(result["hold_total_s"] or 0.0)
        tracker["run_progress"] = round(
            100.0 * float(result["elapsed_s"]) / max(1.0, float(result["total_duration_s"])),
        )
    elif name == "qpcr_read_amplification":
        tracker["amplification_result"] = result
        tracker["cycle"] = tracker["total_cycles"]
        tracker["run_progress"] = 100
    amplification_count = min(40, max(0, int(tracker["cycle"])))
    amplification = _amplification_payload(
        contract,
        count=amplification_count,
        result=tracker.get("amplification_result"),
    )
    hold_total = float(tracker["hold_total_s"])
    hold_elapsed = min(float(tracker["hold_elapsed_s"]), hold_total)
    hold_progress = 100 if hold_total == 0 and tracker["run_progress"] == 100 else (
        0 if hold_total == 0 else round(100 * hold_elapsed / hold_total)
    )
    return {
        "kind": "instrument",
        "label": "Thermocycler program",
        "data": {
            "variant": "thermocycler",
            "instrument": "qPCR thermocycler",
            "action": _copy(name, result)[0],
            "sample": contract["plate_id"],
            "lid": {
                "state": "open" if tracker["lid_open"] else "closed",
                "motion": lid_motion,
            },
            "block_temperature": {"value": tracker["block_temperature_c"], "unit": "C"},
            "lid_temperature": {"value": tracker["lid_temperature_c"], "unit": "C"},
            "cycle": {"index": tracker["cycle"], "total": tracker["total_cycles"]},
            "stage": {
                "name": tracker["stage"],
                "hold_elapsed_seconds": hold_elapsed,
                "hold_total_seconds": hold_total,
                "progress_percent": hold_progress,
            },
            "run_progress_percent": tracker["run_progress"],
            "amplification": amplification,
        },
    }


def _incubator_scene(
    name: str,
    result: dict[str, Any],
    tracker: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    if name == "reader_measure_od600":
        tracker["clock_s"] = float(result["time_s"])
        mean = sum(float(value) for value in result["values"].values()) / len(result["values"])
        tracker["od600"].append(
            {"elapsed_seconds": tracker["clock_s"], "label": _clock_label(tracker["clock_s"]), "value": round(mean, 4)}
        )
    elif name == "incubator_set_temperature":
        tracker["target_temperature_c"] = float(result["target_temperature_c"])
        tracker["current_temperature_c"] = float(result["current_temperature_c"])
    elif name == "incubator_start_shaking":
        tracker["shaking"] = bool(result["shaking"])
        tracker["shake_rpm"] = int(result["shake_rpm"])
    elif name == "incubator_store_plate":
        tracker["plate_location"] = str(result["slot"])
    elif name == "incubator_retrieve_plate":
        tracker["plate_location"] = "loading_tray"
    elif name in {"incubator_advance_time", "incubator_get_status"}:
        tracker["clock_s"] = float(result["clock_s"])
        tracker["current_temperature_c"] = float(result["current_temperature_c"])
        tracker["conditioned_exposure_s"] = float(result["conditioned_exposure_s"])
        tracker["plate_location"] = str(result["plate_location"])
        tracker["shaking"] = bool(result["shaking"])
        if "shake_rpm" in result:
            tracker["shake_rpm"] = int(result["shake_rpm"])
    current = float(tracker["current_temperature_c"])
    target = float(tracker["target_temperature_c"])
    ramping = abs(current - target) > float(contract["temperature_tolerance_c"])
    slot_index = int(tracker["plate_location"][1:]) if tracker["plate_location"].startswith("S") else None
    slots = [
        {
            "index": index,
            "label": f"S{index:02d}",
            "status": "occupied" if slot_index == index else "empty",
        }
        for index in range(1, 9)
    ]
    exposure = float(tracker["conditioned_exposure_s"])
    target_exposure = float(contract["minimum_conditioned_exposure_s"])
    return {
        "kind": "instrument",
        "label": "Incubator-shaker campaign",
        "data": {
            "variant": "incubator_shaker",
            "instrument": "Orbital incubator and OD600 reader",
            "action": _copy(name, result)[0],
            "plate": contract["barcode"],
            "storage_slots": slots,
            "plate_location": {
                "kind": "slot" if slot_index is not None else "external",
                "slot_index": slot_index,
                "label": tracker["plate_location"].replace("_", " ").title(),
            },
            "temperature": {
                "current": {"value": current, "unit": "C"},
                "target": {"value": target, "unit": "C"},
                "ramp": {
                    "state": "heating" if ramping and current < target else ("cooling" if ramping else "holding"),
                    "rate": {"value": contract["temperature_ramp_c_per_s"] if ramping else 0.0, "unit": "C/s"},
                },
            },
            "shaker": {"enabled": tracker["shaking"], "rpm": tracker["shake_rpm"] if tracker["shaking"] else 0},
            "logical_time": {"elapsed_seconds": tracker["clock_s"], "display": _clock_label(tracker["clock_s"])},
            "conditioned_exposure": {
                "condition": "Stored at 30 C with orbital shaking",
                "elapsed_seconds": exposure,
                "target_seconds": target_exposure,
                "progress_percent": min(100, round(100 * exposure / target_exposure)),
            },
            "od600": {
                "x_label": "Campaign time",
                "y_label": "Mean OD600",
                "y_unit": None,
                "points": [dict(point) for point in tracker["od600"]],
            },
        },
    }


def _powder_scene(
    name: str,
    result: dict[str, Any],
    tracker: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    transfer = tracker["transfer"]
    if name == "formulation_move_vial":
        source = "analytical_balance" if result["from"] == "balance" else result["from"]
        target = "analytical_balance" if result["to"] == "balance" else result["to"]
        tracker["location"] = target
        transfer = {"from": source, "to": target, "state": "arrived", "progress_percent": 100}
        tracker["transfer"] = transfer
    elif name == "powder_dispense_pulse":
        tracker["clock_s"] += 2.0
        tracker["pulses"].append(
            {
                "index": int(result["pulse_index"]),
                "requested": {"value": result["requested_mg"], "unit": "mg"},
                "actual": {"value": result["actual_amount_mg"], "unit": "mg"},
                "cumulative": {"value": result["cumulative_amount_mg"], "unit": "mg"},
            }
        )
        tracker["measured_mass_mg"] = float(result["cumulative_amount_mg"])
    elif name == "balance_read_mass":
        tracker["clock_s"] += 1.0
        tracker["measured_mass_mg"] = float(result["measured_mass_mg"])
    measured = float(tracker["measured_mass_mg"])
    target_mass = float(contract["target_mass_mg"])
    tolerance = float(contract["tolerance_mg"])
    tolerance_state = (
        "below_tolerance"
        if measured < target_mass - tolerance
        else "above_tolerance"
        if measured > target_mass + tolerance
        else "in_tolerance"
    )
    return {
        "kind": "instrument",
        "label": "Gravimetric formulation",
        "data": {
            "variant": "powder_balance",
            "instrument": "Powder dispenser and analytical balance",
            "action": _copy(name, result)[0],
            "instruments": {
                "powder_dispenser": "Powder dosing station",
                "analytical_balance": "Analytical balance",
            },
            "vial": {"label": contract["vial_id"], "location": tracker["location"]},
            "transfer": transfer,
            "dosing_pulses": [
                {
                    "index": pulse["index"],
                    "requested": dict(pulse["requested"]),
                    "actual": dict(pulse["actual"]),
                    "cumulative": dict(pulse["cumulative"]),
                }
                for pulse in tracker["pulses"]
            ],
            "measured_mass": {"value": measured, "unit": "mg"},
            "target_mass": {"value": target_mass, "unit": "mg"},
            "tolerance": {
                "minus": {"value": tolerance, "unit": "mg"},
                "plus": {"value": tolerance, "unit": "mg"},
            },
            "tolerance_state": tolerance_state,
        },
    }


def _decision_scene(result: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "evidence",
        "label": "Run decision",
        "data": {
            "decision": result["decision"],
            "rationale": str(arguments["rationale"]),
            "evidence": [{"label": "Evidence artifact", "value": result["evidence_id"]}],
        },
    }


def _initial_tracker(scenario: str, contract: dict[str, Any]) -> dict[str, Any]:
    if scenario == THERMOCYCLER_SCENARIO:
        return {
            "clock_s": 0.0,
            "lid_open": True,
            "lid_temperature_c": 25.0,
            "block_temperature_c": 25.0,
            "cycle": 0,
            "total_cycles": 42,
            "stage": "Ready",
            "hold_elapsed_s": 0.0,
            "hold_total_s": 0.0,
            "run_progress": 0,
        }
    if scenario == INCUBATOR_SCENARIO:
        return {
            "clock_s": 0.0,
            "plate_location": "loading_tray",
            "current_temperature_c": 22.0,
            "target_temperature_c": float(contract["temperature_c"]),
            "shaking": False,
            "shake_rpm": 0,
            "conditioned_exposure_s": 0.0,
            "od600": [],
        }
    return {
        "clock_s": 0.0,
        "location": "analytical_balance",
        "transfer": {
            "from": "powder_dispenser",
            "to": "analytical_balance",
            "state": "arrived",
            "progress_percent": 100,
        },
        "pulses": [],
        "measured_mass_mg": 0.0,
    }


def _amplification_payload(
    contract: dict[str, Any], *, count: int, result: dict[str, Any] | None
) -> dict[str, Any]:
    source = result["series"] if result is not None else amplification_series(contract["amplification_wells"])
    series = []
    for well, values in source.items():
        role = contract["amplification_wells"][well]["role"].replace("_", " ")
        series.append(
            {
                "label": f"{well} {role}",
                "points": [
                    {"cycle": cycle, "value": round(float(values[cycle - 1]) / 12_000.0, 5)}
                    for cycle in range(1, count + 1)
                ],
            }
        )
    return {
        "x_label": "Amplification cycle",
        "y_label": "Normalized fluorescence",
        "y_unit": None,
        "series": series if count else [],
    }


def _thermal_stage_name(result: dict[str, Any]) -> str:
    if int(result["stage_index"]) == 0:
        return "Initial denaturation"
    if int(result["stage_index"]) == 2:
        return "Final extension"
    return "Denaturation" if float(result["block_temperature_c"]) >= 90 else "Anneal and extend"


def _artifacts(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts = []
    for operation in operations:
        result = operation["result"]["data"]
        artifact_id = result.get("artifact_id")
        if artifact_id is None:
            continue
        if artifact_id.startswith("qpcr"):
            artifact_type, label = "simulated_amplification", "qPCR amplification result"
        elif artifact_id.startswith("od600"):
            artifact_type, label = "simulated_measurement", f"OD600 timepoint {artifact_id[-3:]}"
        else:
            artifact_type, label = "simulated_measurement", f"Gravimetric reading {artifact_id[-3:]}"
        artifacts.append(
            {
                "id": artifact_id,
                "label": label,
                "type": artifact_type,
                "summary": "Deterministic dry-run evidence produced by the declared benchmark projection.",
                "data": result,
            }
        )
    return artifacts


def _resources(scenario: str) -> list[dict[str, Any]]:
    entries = {
        THERMOCYCLER_SCENARIO: [
            ("qpcr_thermocycler", "qPCR thermocycler", "thermocycler"),
            ("qpcr_plate_01", "qPCR plate 01", "plate"),
        ],
        INCUBATOR_SCENARIO: [
            ("orbital_incubator", "Orbital incubator", "incubator_shaker"),
            ("od600_reader", "OD600 reader", "plate_reader"),
            ("culture_plate_01", "Culture plate CULTURE-BC-1042", "plate"),
        ],
        POWDER_SCENARIO: [
            ("powder_dispenser", "Powder dosing station", "powder_dispenser"),
            ("analytical_balance", "Analytical balance", "scale"),
            ("FORM-001", "Formulation vial FORM-001", "vial"),
        ],
    }[scenario]
    return [
        {
            "id": resource_id,
            "label": label,
            "type": kind,
            "status": "ready",
            "summary": "Declared instrument or sample in the dry-run workflow.",
            "attributes": {},
        }
        for resource_id, label, kind in entries
    ]


def _initialization(scenario: str) -> list[dict[str, Any]]:
    root = Resource(name="science_workcell", size_x=1000, size_y=650, size_z=200)
    names = [item[0] for item in {
        THERMOCYCLER_SCENARIO: [("qpcr_thermocycler",), ("qpcr_plate_01",)],
        INCUBATOR_SCENARIO: [("orbital_incubator",), ("od600_reader",), ("culture_plate_01",)],
        POWDER_SCENARIO: [("powder_dispenser",), ("analytical_balance",), ("FORM-001",)],
    }[scenario]]
    for index, name in enumerate(names):
        child = Resource(name=name, size_x=180, size_y=160, size_z=120)
        root.assign_child_resource(child, location=Coordinate(x=80 + index * 260, y=220, z=0))
    return [{"event": "set_root_resource", "data": {"resource": root.serialize()}}]


def _copy(name: str, result: dict[str, Any]) -> tuple[str, str]:
    copy = {
        "thermocycler_close_lid": ("Close the heated lid", "The qPCR plate is enclosed before thermal cycling."),
        "thermocycler_set_lid_temperature": ("Heat the lid to 105 C", "The heated lid limits condensation during repeated temperature stages."),
        "thermocycler_start_protocol": ("Start the qPCR profile", "The thermocycler queues 82 timed temperature steps."),
        "thermocycler_advance_time": ("Advance the thermal program", "Logical time reveals the current cycle, temperature stage, and hold progress."),
        "thermocycler_get_status": ("Confirm protocol completion", "The final status reports all temperature stages completed."),
        "qpcr_read_amplification": ("Read amplification curves", "The projected result separates positive, negative, and sample reactions."),
        "thermocycler_open_lid": ("Open the completed run", "The lid opens only after the thermal program has stopped."),
        "reader_measure_od600": ("Measure the culture plate", "The separate reader records A1-A8 at 600 nm for this timepoint."),
        "incubator_set_temperature": ("Set incubation to 30 C", "The chamber begins a declared 22 to 30 C temperature ramp."),
        "incubator_start_shaking": ("Start orbital shaking", "The incubator holds the culture plate at 250 rpm while stored."),
        "incubator_store_plate": ("Store the plate in slot S04", "Plate custody moves from the loading tray into a declared storage position."),
        "incubator_advance_time": ("Advance two hours", "Logical time accumulates only temperature-conditioned shaking exposure."),
        "incubator_get_status": ("Check the incubation conditions", "The chamber reports temperature, shaking, storage, and exposure state."),
        "incubator_retrieve_plate": ("Retrieve the culture plate", "The identified plate returns to the loading tray for measurement."),
        "balance_tare": ("Tare the empty vial", "The balance stores the empty-vial mass so subsequent readings report net powder mass."),
        "formulation_move_vial": ("Move the formulation vial", "The same vial moves between the dosing and weighing stations."),
        "powder_dispense_pulse": ("Dispense one powder pulse", "The dispenser reports requested, actual, and cumulative delivered mass."),
        "balance_read_mass": ("Weigh the formulation", "The analytical balance compares measured net mass with the target band."),
        "submit_science_decision": ("Submit the evidence-linked decision", "The final decision cites the latest completed measurement artifact."),
    }
    return copy.get(name, (name.replace("_", " ").title(), "The dry-run operation completed."))


def _facts(name: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[tuple[str, Any, str | None, str]] = []
    for label, key, unit in (
        ("Cycle", "cycle_index", None),
        ("Block", "block_temperature_c", "C"),
        ("Time", "clock_s", "s"),
        ("Exposure", "conditioned_exposure_s", "s"),
        ("Actual", "actual_amount_mg", "mg"),
        ("Measured", "measured_mass_mg", "mg"),
    ):
        if key in result:
            candidates.append((label, result[key], unit, "info"))
    if "within_tolerance" in result:
        candidates.append(("Tolerance", "pass" if result["within_tolerance"] else "adjust", None, "success" if result["within_tolerance"] else "warning"))
    if "decision" in result:
        candidates.append(("Decision", result["decision"], None, "success"))
    if not candidates:
        candidates.append(("Operation", name.replace("_", " "), None, "neutral"))
    return [
        {"label": label, "value": str(value), "unit": unit, "tone": tone}
        for label, value, unit, tone in candidates[:3]
    ]


def _duration_ms(name: str) -> int:
    if name in {"thermocycler_advance_time", "incubator_advance_time"}:
        return 1800
    if name in {"qpcr_read_amplification", "reader_measure_od600", "balance_read_mass"}:
        return 2200
    if name == "submit_science_decision":
        return 1500
    return 1200


def _simulated_at(tracker: dict[str, Any]) -> str:
    return f"T+{float(tracker.get('clock_s', 0.0)):.1f}s"


def _clock_label(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours:02d}:{minutes:02d}"


def _presentation_metadata(scenario: str) -> dict[str, str]:
    return {
        THERMOCYCLER_SCENARIO: {
            "title": "qPCR thermal program dry run",
            "summary": "Heated-lid motion, 82 thermal steps, cycle progression, and control-aware amplification evidence.",
            "subject": "Thermocycler workflow",
            "stage": "Thermal program and amplification",
        },
        INCUBATOR_SCENARIO: {
            "title": "Eight-hour shaking-incubation campaign",
            "summary": "Plate custody, chamber ramp, conditioned shaking exposure, and five OD600 timepoints.",
            "subject": "Incubator-shaker workflow",
            "stage": "Incubation and repeated measurement",
        },
        POWDER_SCENARIO: {
            "title": "Gravimetric powder formulation dry run",
            "summary": "Tare, coarse dose, gravimetric feedback, correction pulse, and final tolerance evidence.",
            "subject": "Powder formulation workflow",
            "stage": "Powder dosing and gravimetric correction",
        },
    }[scenario]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(SCENARIO_CONTRACTS), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    export_science_visualization(scenario=args.scenario, destination=args.out)
    print(args.out.resolve())


if __name__ == "__main__":
    main()
