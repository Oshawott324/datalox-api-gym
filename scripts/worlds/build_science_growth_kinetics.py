#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / "worlds" / "science_growth_kinetics_v0"
V1 = WORLD / "world" / "v1"
BRIDGE_SOURCE = (
    ROOT
    / "api_gym"
    / "provider_components"
    / "pylabrobot"
    / "world_bridge.py"
)
BRIDGE_DESTINATION = V1 / "provider_pylabrobot.py"
PLR_CAPTURE_ROOT = (
    ROOT / "source_packs" / "apis" / "pylabrobot" / "2026-07-26"
)
ELABFTW_CAPTURE_ROOT = (
    ROOT / "source_packs" / "apis" / "elabftw" / "2026-07-26"
)

WORLD_ID = "science_growth_kinetics_v0"
FAMILIES = (
    "growth_nominal_v1",
    "growth_resource_recovery_v1",
    "growth_async_freshness_recovery_v1",
)
EXPECTED_WELLS = [f"A{column}" for column in range(1, 9)] + ["H12"]
ALL_FAILURE_CODES = [
    "growth.protocol_inspected",
    "growth.prep_complete",
    "growth.transfer_lineage_valid",
    "growth.unique_tip_per_transfer",
    "growth.incubator_stabilized",
    "growth.kinetic_complete",
    "growth.series_current",
    "growth.series_contract",
    "growth.result_record_complete",
    "growth.workflow_ordered",
    "growth.provider_mechanisms_executed",
]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(value, sort_keys=True, allow_nan=False) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def episode(seed: int) -> dict[str, Any]:
    family = FAMILIES[seed // 4]
    initial_time = datetime.fromisoformat("2026-07-26T08:00:00+00:00")
    protocol_experiment_id = 1100 + seed
    result_experiment_id = 2100 + seed * 10
    source_volumes = {
        **{f"A{column}": 220.0 for column in range(1, 9)},
        "H11": 220.0,
        "G12": 220.0,
    }
    tip_availability = {
        f"{row}{column}": True
        for row in ("A", "B")
        for column in range(1, 13)
    }
    faults: dict[str, Any] = {
        "low_source_well": None,
        "missing_tip_spot": None,
        "reader_busy_seconds": 0,
        "partial_first_run": False,
        "protocol_revision_bump_after_seconds": None,
    }
    if family == "growth_resource_recovery_v1":
        if seed % 2 == 0:
            source_volumes["A4"] = 150.0
            faults["low_source_well"] = "A4"
        else:
            tip_availability["A1"] = False
            faults["missing_tip_spot"] = "A1"
    if family == "growth_async_freshness_recovery_v1":
        if seed == 8:
            faults["reader_busy_seconds"] = 1800
        elif seed == 9:
            faults["partial_first_run"] = True
        elif seed == 10:
            faults["protocol_revision_bump_after_seconds"] = 600
        else:
            faults["reader_busy_seconds"] = 1800
            faults["partial_first_run"] = True

    transfer_plan = []
    for well in EXPECTED_WELLS:
        source = "H11" if well == "H12" else well
        backups = ["G12"] if well == "A4" else []
        transfer_plan.append(
            {
                "target_well": well,
                "source_well": source,
                "backup_source_wells": backups,
                "volume_ul": 200.0,
                "control_role": "blank" if well == "H12" else "sample_replicate",
            }
        )
    revision = 1
    state = {
        "protocol": {
            "experiment_id": protocol_experiment_id,
            "revision": revision,
            "plate_barcode": f"YGR-{seed:03d}",
            "organism": "Saccharomyces cerevisiae",
            "plate_format": 96,
            "expected_wells": deepcopy(EXPECTED_WELLS),
            "sample_replicates": [f"A{column}" for column in range(1, 9)],
            "blank_well": "H12",
            "target_volume_ul": 200.0,
            "temperature_c": 30.0,
            "stabilization_seconds": 600,
            "shaking_hz": 2.0,
            "wavelength_nm": 600,
            "interval_seconds": 120,
            "duration_seconds": 72000,
            "expected_observation_count": 601,
            "transfer_plan": transfer_plan,
            "read_method_note": "Revision 1 uses the declared OD600 kinetic contract.",
        },
        "deck": {
            "backend": "OpentronsOT2Simulator",
            "source_volumes_ul": source_volumes,
            "target_volumes_ul": {well: 0.0 for well in EXPECTED_WELLS},
            "tip_availability": tip_availability,
        },
        "incubator": {
            "backend": "IncubatorChatterboxBackend",
            "plate_barcode": None,
            "location": "deck",
            "loaded_at": None,
            "temperature_c": None,
            "shaking_hz": None,
            "stabilization_ready_at": None,
            "stabilized": False,
            "released_at": None,
        },
        "reader": {
            "backend": "PlateReaderChatterboxBackend",
            "next_job_number": 1,
            "active_job_id": None,
            "busy_until": (
                initial_time + timedelta(seconds=int(faults["reader_busy_seconds"]))
            ).isoformat()
            if faults["reader_busy_seconds"]
            else None,
            "jobs": {},
        },
        "elabftw": {
            "provider_version": "5.6.10",
            "protocol_experiment_id": protocol_experiment_id,
            "next_result_id": result_experiment_id,
            "result_records": {},
        },
        "faults": faults,
        "facts": {
            "seed": seed,
            "prep_complete": False,
            "used_tips": [],
            "transfer_lineage": {},
            "current_complete_job_id": None,
            "decision_record_id": None,
            "provider_execution_counts": {
                "ot2": 0,
                "incubator": 0,
                "plate_reader": 0,
            },
        },
    }
    return {
        "id": f"growth-kinetics-{seed:03d}",
        "family_id": family,
        "seed": seed,
        "metadata": {
            "clock": initial_time.isoformat(),
            "grounding": {
                "provider_mechanisms": "simulator_or_chatterbox_executed",
                "kinetic_values": "benchmark_defined",
                "fault_schedule": "benchmark_defined",
            },
        },
        "state": state,
        "task": {
            "task_id": f"growth-kinetics-{seed:03d}",
            "title": "Run and document a dry-run yeast growth kinetics assay",
            "instructions": (
                f"Read eLabFTW protocol experiment {protocol_experiment_id}. Inspect the "
                "tracked deck and prepare every declared assay well with a unique clean tip; "
                "use a declared backup source when needed. Load and stabilize the plate, then "
                "release it and start the exact current OD600 kinetic method. The reader may "
                "be busy, return a partial first run, or the protocol may be revised while "
                "time advances. Recover using current provider state. After one complete, "
                "current 601-observation series exists, create an eLabFTW experiment, patch "
                "it with title/body/JSON-string metadata, and read it back. Metadata must "
                "include qc_status='accepted', plate_barcode, protocol_revision, "
                "kinetic_job_id, observation_count=601, and expected_wells."
            ),
            "success_criteria": [
                "Every protocol well contains 200 uL from an allowed source.",
                "Every transfer uses a distinct clean tip and executes the OT-2 simulator.",
                "The plate is stabilized at 30 C before reader release.",
                "A complete current OD600 series covers all nine wells at 120-second cadence for 20 hours.",
                "The eLabFTW result record cites the current plate, protocol revision, and complete job.",
            ],
        },
    }


def mcp(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "surface": "mcp",
        "tool_name": tool_name,
        "arguments": arguments,
        "actor_role": "scientist_agent",
        "actor_id": "science-agent-001",
    }


def reference_steps(item: dict[str, Any]) -> list[dict[str, Any]]:
    state = item["state"]
    protocol = state["protocol"]
    deck = state["deck"]
    faults = state["faults"]
    available_tips = [
        spot for spot, available in deck["tip_availability"].items() if available
    ]
    steps = [
        mcp(
            "elabftw.get_experiment",
            {"experiment_id": protocol["experiment_id"]},
        ),
        mcp("pylabrobot.inspect_deck", {}),
    ]
    for index, transfer in enumerate(protocol["transfer_plan"]):
        source_well = transfer["source_well"]
        if deck["source_volumes_ul"][source_well] < transfer["volume_ul"]:
            source_well = transfer["backup_source_wells"][0]
        steps.append(
            mcp(
                "pylabrobot.transfer",
                {
                    "source_well": source_well,
                    "target_well": transfer["target_well"],
                    "tip_spot": available_tips[index],
                    "volume_ul": transfer["volume_ul"],
                },
            )
        )
    steps.extend(
        [
            mcp(
                "pylabrobot.incubator_load",
                {
                    "plate_barcode": protocol["plate_barcode"],
                    "temperature_c": protocol["temperature_c"],
                    "shaking_hz": protocol["shaking_hz"],
                },
            ),
            mcp("clock.advance", {"seconds": protocol["stabilization_seconds"]}),
            mcp(
                "elabftw.get_experiment",
                {"experiment_id": protocol["experiment_id"]},
            ),
            mcp("pylabrobot.incubator_status", {}),
            mcp(
                "pylabrobot.incubator_release",
                {"plate_barcode": protocol["plate_barcode"]},
            ),
        ]
    )
    current_revision = (
        protocol["revision"] + 1
        if faults["protocol_revision_bump_after_seconds"] is not None
        else protocol["revision"]
    )
    start_arguments = {
        "plate_barcode": protocol["plate_barcode"],
        "protocol_revision": current_revision,
        "wells": protocol["expected_wells"],
        "wavelength_nm": protocol["wavelength_nm"],
        "interval_seconds": protocol["interval_seconds"],
        "duration_seconds": protocol["duration_seconds"],
    }
    if faults["reader_busy_seconds"] > protocol["stabilization_seconds"]:
        steps.append(mcp("pylabrobot.start_kinetic_read", start_arguments))
        steps.append(
            mcp(
                "clock.advance",
                {
                    "seconds": (
                        faults["reader_busy_seconds"]
                        - protocol["stabilization_seconds"]
                    )
                },
            )
        )
    run_count = 2 if faults["partial_first_run"] else 1
    for run_number in range(1, run_count + 1):
        steps.extend(
            [
                mcp(
                    "pylabrobot.start_kinetic_read",
                    start_arguments,
                ),
                mcp(
                    "clock.advance",
                    {"seconds": protocol["duration_seconds"]},
                ),
                mcp(
                    "pylabrobot.get_kinetic_read",
                    {"job_id": f"run-{run_number:03d}"},
                ),
            ]
        )
    result_id = state["elabftw"]["next_result_id"]
    final_job_id = f"run-{run_count:03d}"
    result_metadata = {
        "expected_wells": protocol["expected_wells"],
        "kinetic_job_id": final_job_id,
        "observation_count": protocol["expected_observation_count"],
        "plate_barcode": protocol["plate_barcode"],
        "protocol_revision": current_revision,
        "qc_status": "accepted",
    }
    steps.extend(
        [
            mcp("elabftw.create_experiment", {}),
            mcp(
                "elabftw.patch_experiment",
                {
                    "experiment_id": result_id,
                    "title": f"Accepted growth kinetics {protocol['plate_barcode']}",
                    "body": (
                        f"Dry-run job {final_job_id} completed with all declared "
                        "replicates and blank control."
                    ),
                    "metadata": json.dumps(
                        result_metadata,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            ),
            mcp("elabftw.get_experiment", {"experiment_id": result_id}),
        ]
    )
    return steps


def trajectories(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in episodes:
        rows.append(
            {
                "id": f"reference-{item['id']}",
                "kind": "reference",
                "episode_id": item["id"],
                "steps": reference_steps(item),
                "expected": {"passed": True, "failure_codes": []},
            }
        )

    nominal = episodes[0]
    rows.append(
        {
            "id": "negative-empty",
            "kind": "negative",
            "episode_id": nominal["id"],
            "steps": [],
            "expected": {
                "passed": False,
                "failure_codes": deepcopy(ALL_FAILURE_CODES),
            },
        }
    )

    low_resource = episodes[4]
    failed_transfer = [
        mcp(
            "elabftw.get_experiment",
            {"experiment_id": low_resource["state"]["protocol"]["experiment_id"]},
        ),
        mcp("pylabrobot.inspect_deck", {}),
        mcp(
            "pylabrobot.transfer",
            {
                "source_well": "A4",
                "target_well": "A4",
                "tip_spot": "A1",
                "volume_ul": 200.0,
            },
        ),
    ]
    rows.append(
        {
            "id": "negative-low-resource-unrecovered",
            "kind": "negative",
            "episode_id": low_resource["id"],
            "steps": failed_transfer,
            "expected": {
                "passed": False,
                "failure_codes": [
                    code for code in ALL_FAILURE_CODES if code != "growth.protocol_inspected"
                ],
            },
        }
    )

    partial = episodes[9]
    partial_steps = reference_steps(partial)
    second_start = next(
        index
        for index, step in enumerate(partial_steps)
        if step["tool_name"] == "pylabrobot.start_kinetic_read"
        and index
        > next(
            first_index
            for first_index, first_step in enumerate(partial_steps)
            if first_step["tool_name"] == "pylabrobot.start_kinetic_read"
        )
    )
    first_result_id = partial["state"]["elabftw"]["next_result_id"]
    partial_metadata = {
        "expected_wells": partial["state"]["protocol"]["expected_wells"],
        "kinetic_job_id": "run-001",
        "observation_count": 601,
        "plate_barcode": partial["state"]["protocol"]["plate_barcode"],
        "protocol_revision": 1,
        "qc_status": "accepted",
    }
    partial_steps = partial_steps[:second_start] + [
        mcp("elabftw.create_experiment", {}),
        mcp(
            "elabftw.patch_experiment",
            {
                "experiment_id": first_result_id,
                "title": "Incorrectly accepted partial growth kinetics",
                "body": "This record incorrectly treats a partial run as complete.",
                "metadata": json.dumps(
                    partial_metadata,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ),
        mcp("elabftw.get_experiment", {"experiment_id": first_result_id}),
    ]
    rows.append(
        {
            "id": "negative-partial-treated-as-complete",
            "kind": "negative",
            "episode_id": partial["id"],
            "steps": partial_steps,
            "expected": {
                "passed": False,
                "failure_codes": [
                    "growth.kinetic_complete",
                    "growth.series_current",
                    "growth.series_contract",
                    "growth.result_record_complete",
                ],
            },
        }
    )

    revised = episodes[10]
    stale_steps = reference_steps(revised)
    patch = next(
        step
        for step in stale_steps
        if step["tool_name"] == "elabftw.patch_experiment"
    )
    metadata = json.loads(patch["arguments"]["metadata"])
    metadata["protocol_revision"] = 1
    patch["arguments"]["metadata"] = json.dumps(
        metadata, sort_keys=True, separators=(",", ":")
    )
    rows.append(
        {
            "id": "negative-stale-result-record",
            "kind": "negative",
            "episode_id": revised["id"],
            "steps": stale_steps,
            "expected": {
                "passed": False,
                "failure_codes": ["growth.result_record_complete"],
            },
        }
    )

    rows.append(
        {
            "id": "parity-get-protocol",
            "kind": "parity",
            "episode_id": nominal["id"],
            "http_step": {
                "surface": "http",
                "method": "GET",
                "path": (
                    "/api/v2/experiments/"
                    f"{nominal['state']['protocol']['experiment_id']}"
                ),
                "query": {},
                "body": None,
                "actor_role": "scientist_agent",
                "actor_id": "science-http-001",
            },
            "mcp_step": mcp(
                "elabftw.get_experiment",
                {"experiment_id": nominal["state"]["protocol"]["experiment_id"]},
            ),
            "expected": {"matched": True},
        }
    )
    return rows


def copy_evidence() -> None:
    evidence = WORLD / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ELABFTW_CAPTURE_ROOT
        / "raw"
        / "reference_sequences"
        / "experiments_create_patch_get_v0.json",
        evidence / "elabftw_experiments_create_patch_get_v0.json",
    )
    for name in (
        "ot2_success_v0.json",
        "incubator_success_v0.json",
        "plate_reader_success_v0.json",
    ):
        shutil.copy2(
            PLR_CAPTURE_ROOT / "raw" / "reference_sequences" / name,
            evidence / name,
        )
    write_json(
        evidence / "growth_protocol_sources.json",
        {
            "agilent_app_note": {
                "url": "https://www.agilent.com/cs/library/applications/monitoring-growth-of-saccharomyces-cerevisiae-5994-3284EN-agilent.pdf",
                "locators": {
                    "workflow": "pages 2-3: 30 C, 600 nm, two-minute measurements, continuous orbital shaking",
                    "replicates": "page 3: 200 uL aliquots in replicates of eight",
                    "duration": "page 3: experiment completed 20 hours later",
                },
            },
            "agilent_technical_details": {
                "url": "https://www.agilent.com/cs/library/specifications/public/Synergy-H1-technical-details-5994-3583EN-agilent.pdf",
                "locators": {
                    "reader": "page 1: kinetic reads, incubation, orbital shaking, and 230-999 nm absorbance"
                },
            },
        },
    )


def build() -> None:
    if not (V1 / "implementation.py").is_file() or not (V1 / "contract.py").is_file():
        raise RuntimeError("world implementation and contract must exist before build")
    V1.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BRIDGE_SOURCE, BRIDGE_DESTINATION)
    copy_evidence()
    episodes = [episode(seed) for seed in range(12)]
    trajectory_rows = trajectories(episodes)
    write_jsonl(V1 / "episodes.jsonl", episodes)
    write_json(
        V1 / "roles.json",
        {
            "roles": [
                {
                    "id": "scientist_agent",
                    "description": "Executes and documents a dry-run microbial growth workflow.",
                }
            ]
        },
    )
    sys.path.insert(0, str(ROOT))
    from worlds.science_growth_kinetics_v0.world.v1.contract import TOOLS

    write_json(V1 / "tools.json", {"tools": list(TOOLS)})
    write_json(
        V1 / "verifier.json",
        {
            "schema_version": "science_growth_kinetics_verifier_v0",
            "assertions": [
                {"type": "implementation_check", "failure_code": code}
                for code in ALL_FAILURE_CODES
            ],
            "semantic_rubrics": [],
            "scalar_reward_owned_here": False,
        },
    )
    write_json(
        V1 / "sources.json",
        {
            "sources": [
                {
                    "id": "elabftw_reference_capture",
                    "kind": "authorized_local_fixture_capture",
                    "grounding_level": "G2_LOCAL_EXECUTED",
                    "locator": "evidence/elabftw_experiments_create_patch_get_v0.json",
                    "derivation": (
                        "Pinned eLabFTW 5.6.10 create-patch-get request and response "
                        "sequence captured from the disposable official container."
                    ),
                    "supports": [
                        "operation:elabftw.get_experiment",
                        "operation:elabftw.create_experiment",
                        "operation:elabftw.patch_experiment",
                    ],
                },
                {
                    "id": "pylabrobot_executed_source_pack",
                    "kind": "local_simulator_and_chatterbox_execution",
                    "grounding_level": "G2_LOCAL_EXECUTED",
                    "locator": (
                        "evidence/ot2_success_v0.json; evidence/incubator_success_v0.json; "
                        "evidence/plate_reader_success_v0.json"
                    ),
                    "derivation": (
                        "Pinned PyLabRobot 0.2.1 methods were executed locally with "
                        "OpentronsOT2Simulator and Chatterbox backends."
                    ),
                    "supports": [
                        "operation:pylabrobot.transfer",
                        "operation:pylabrobot.incubator_load",
                        "operation:pylabrobot.incubator_release",
                        "operation:pylabrobot.start_kinetic_read",
                    ],
                },
                {
                    "id": "agilent_growth_protocol",
                    "kind": "official_application_note",
                    "grounding_level": "G1_OFFICIAL_DOCS",
                    "locator": "evidence/growth_protocol_sources.json",
                    "derivation": (
                        "Grounds the selected 96-well, eight-replicate, 200 uL, "
                        "30 C, OD600, two-minute, 20-hour protocol values."
                    ),
                    "supports": ["protocol:growth_kinetics"],
                },
                {
                    "id": "growth_projection_contract",
                    "kind": "benchmark_projection",
                    "grounding_level": "G0_BENCHMARK_DEFINED",
                    "locator": "projection_contract.md",
                    "derivation": (
                        "Defines logical-time stabilization, synthetic OD values, "
                        "fault schedules, and state-verification semantics."
                    ),
                    "supports": [
                        "dynamics:logical_time",
                        "dynamics:kinetic_values",
                        "dynamics:fault_schedule",
                    ],
                },
            ],
            "grounding_gaps": [
                {
                    "operation_family": "plate_reading",
                    "status": "partial",
                    "reason": (
                        "The Chatterbox backend executes the interface but returns dummy "
                        "values. Kinetic OD600 values are benchmark-defined, not instrument observations."
                    ),
                },
                {
                    "operation_family": "incubation",
                    "status": "partial",
                    "reason": (
                        "Chatterbox does not model stabilization, exposure, or temperature "
                        "dynamics. Logical-time stabilization is benchmark-defined."
                    ),
                },
                {
                    "operation_family": "cross_instrument_transport",
                    "status": "unsupported",
                    "reason": (
                        "No robot arm or physical workcell handoff is executed. Plate identity "
                        "is preserved by world state across independent local fixtures."
                    ),
                },
                {
                    "operation_family": "biological_prediction",
                    "status": "unsupported",
                    "reason": (
                        "The deterministic logistic curves are stable workflow fixtures and "
                        "must not be interpreted as biological predictions."
                    ),
                },
            ],
        },
    )
    write_json(
        V1 / "construction.json",
        {
            "schema_version": "datalox_science_world_construction_v1",
            "world_id": WORLD_ID,
            "episode_count": len(episodes),
            "family_ids": list(FAMILIES),
            "provider_projects": ["eLabFTW", "PyLabRobot"],
            "executed_provider_backends": [
                "OpentronsOT2Simulator",
                "IncubatorChatterboxBackend",
                "PlateReaderChatterboxBackend",
            ],
            "hardware_execution_allowed": False,
            "network_access_required": False,
            "scalar_reward_owned_here": False,
            "verifier_complexity": {
                "state_loads": 1,
                "event_passes": 1,
                "assertion_count": len(ALL_FAILURE_CODES),
            },
            "provider_bridge_source_sha256": (
                "sha256:" + hashlib.sha256(BRIDGE_SOURCE.read_bytes()).hexdigest()
            ),
        },
    )
    write_json(
        WORLD / "tests" / "trajectories" / "growth.json",
        {"trajectories": trajectory_rows},
    )
    write_json(
        WORLD / "source_refs.json",
        {
            "schema_version": "api_gym.world_source_refs.v0",
            "world": WORLD_ID,
            "source_packs": [
                {
                    "source_pack_id": "api.pylabrobot.2026-07-26",
                    "path": "../../source_packs/apis/pylabrobot/2026-07-26/source_pack.json",
                    "records": [
                        "operation:pylabrobot.ot2.aspirate",
                        "operation:pylabrobot.ot2.dispense",
                        "operation:pylabrobot.ot2.discard_tip",
                        "operation:pylabrobot.incubator.take_in_plate",
                        "operation:pylabrobot.incubator.fetch_plate",
                        "operation:pylabrobot.plate_reader.read_absorbance",
                    ],
                }
            ],
            "world_evidence": [
                {
                    "path": "evidence/elabftw_experiments_create_patch_get_v0.json",
                    "role": "elabftw_reference_sequence",
                },
                {
                    "path": "evidence/growth_protocol_sources.json",
                    "role": "scientific_protocol_sources",
                },
            ],
        },
    )
    write_json(
        WORLD / "gate_config.json",
        {
            "config_id": WORLD_ID,
            "response_cases": [],
            "audit_rules": [],
            "policy": {"deny": [], "shadow_write": [], "live_capture": []},
            "world": {"kind": "world_bundle_v1", "seed": 0},
        },
    )
    write_json(WORLD / "task.json", episodes[0]["task"])
    write_json(WORLD / "replay_script.json", {"calls": []})
    (WORLD / "skills").mkdir(parents=True, exist_ok=True)
    (WORLD / "skills" / "SKILL.md").write_text(
        "# Growth kinetics dry run\n\n"
        "Read the eLabFTW protocol before acting and again after advancing time. "
        "Inspect tracked resources, use one clean tip per transfer, and use only "
        "declared backup sources. Treat provider errors as state evidence. Logical "
        "time does not sleep. Confirm incubation stabilization before release. A "
        "partial kinetic result is not recoverable by documentation; rerun the "
        "complete 20-hour method. Record only a complete job whose plate barcode "
        "and protocol revision remain current. eLabFTW PATCH metadata must be a "
        "JSON string. Never claim that Chatterbox values are physical measurements "
        "or that the benchmark curve predicts biology.\n",
        encoding="utf-8",
    )
    (WORLD / "README.md").write_text(
        "# Science Growth Kinetics v0\n\n"
        "A resettable cross-service science-agent world over eLabFTW-shaped records "
        "and executed PyLabRobot 0.2.1 simulator/Chatterbox mechanisms. Twelve "
        "episodes cover nominal execution, resource recovery, reader availability, "
        "partial-run recovery, and protocol freshness. No hardware or network "
        "execution is available.\n\n"
        "Build and check:\n\n"
        "```bash\n"
        "python scripts/worlds/build_science_growth_kinetics.py\n"
        "python scripts/worlds/build_science_growth_kinetics.py --check\n"
        "datalox-gate env admit-world --env worlds/science_growth_kinetics_v0 --json\n"
        "```\n",
        encoding="utf-8",
    )
    (WORLD / "projection_contract.md").write_text(
        "# Projection Contract\n\n"
        "The world executes PyLabRobot 0.2.1 OT-2 simulator calls for every liquid "
        "transfer and Chatterbox calls for incubator loading/release and plate-reader "
        "absorbance. These calls establish interface execution and tracker behavior, "
        "not hardware fidelity.\n\n"
        "The 30 C, 600 nm, 200 uL, eight-replicate, two-minute, 20-hour values are "
        "selected from the retained Agilent application note. The inclusive schedule "
        "contains 601 observations. The blank well, ten-minute preconditioning "
        "interval, deterministic logistic values, reader-busy timing, partial-run "
        "fault, and revision-bump timing are benchmark-defined. They are workflow "
        "fixtures, not biological or production-frequency claims.\n\n"
        "Plate transport between independent fixtures is state-projected; no robot "
        "arm is executed. Live hardware and network calls are inexpressible.\n",
        encoding="utf-8",
    )
    from datalox_gated_runtime.world_v1.bundle import compute_bundle_hashes

    write_json(
        WORLD / "world" / "manifest.json",
        {
            "schema_version": "datalox_world_bundle_v1",
            "world_id": WORLD_ID,
            "bundle_version": "0.1.0",
            "implementation": "world/v1/implementation.py:create_world",
            "episodes_path": "world/v1/episodes.jsonl",
            "roles_path": "world/v1/roles.json",
            "tools_path": "world/v1/tools.json",
            "verifier_path": "world/v1/verifier.json",
            "sources_path": "world/v1/sources.json",
            "default_actor_role": "scientist_agent",
            "required_runtime_capabilities": [
                "actors",
                "role_scoped_tools",
                "transactions",
                "clock",
                "scheduled_events",
            ],
            "trajectory_paths": ["tests/trajectories/growth.json"],
            "content_hashes": compute_bundle_hashes(WORLD),
        },
    )


def snapshot() -> dict[str, bytes]:
    if not WORLD.exists():
        return {}
    return {
        path.relative_to(WORLD).as_posix(): path.read_bytes()
        for path in WORLD.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.name != "world_admission.json"
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    before = snapshot()
    build()
    if args.check:
        after = snapshot()
        if before != after:
            print("science growth kinetics generated artifacts were stale.", file=sys.stderr)
            return 1
        print("science growth kinetics generated artifacts are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
