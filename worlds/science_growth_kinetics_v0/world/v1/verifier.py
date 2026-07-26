from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

from datalox_gated_runtime.world_v1.session import WorldSession


@dataclass(frozen=True)
class GrowthVerifierResult:
    passed: bool
    checks: tuple[dict[str, Any], ...]
    failure_codes: tuple[str, ...]
    public_evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verifier_type": "science_growth_kinetics_v0",
            "checks": list(self.checks),
            "failure_codes": list(self.failure_codes),
            "public_evidence": self.public_evidence,
        }


def verify_growth(session: WorldSession) -> GrowthVerifierResult:
    """Evaluate grounded workflow invariants without assigning scalar reward."""

    state = session.list_state()
    protocol = state["protocol"]
    deck = state["deck"]
    incubator = state["incubator"]
    reader = state["reader"]
    facts = state["facts"]
    records = state["elabftw"]["result_records"]
    events = [
        event
        for event in session.verifier_events()
        if event.get("event_type") == "growth_operation"
    ]
    successful = [
        event for event in events if event.get("decision") in {"replay", "shadow_write"}
    ]
    operation_ids = [str(event.get("operation_id")) for event in successful]
    current_job_id = facts.get("current_complete_job_id")
    current_job = reader["jobs"].get(current_job_id) if current_job_id else None
    expected_wells = protocol["expected_wells"]
    plan_by_target = {
        row["target_well"]: {row["source_well"], *row["backup_source_wells"]}
        for row in protocol["transfer_plan"]
    }
    lineage = facts["transfer_lineage"]
    result_record = _selected_result_record(records, facts.get("decision_record_id"))
    result_metadata = result_record.get("metadata", {}) if result_record else {}
    checks_raw = (
        (
            "growth.protocol_inspected",
            "elabftw.get_experiment" in operation_ids,
            ["public_evidence:#/operation_sequence"],
        ),
        (
            "growth.prep_complete",
            facts["prep_complete"]
            and all(
                math.isclose(float(deck["target_volumes_ul"].get(well, 0)), 200.0)
                for well in expected_wells
            ),
            ["public_evidence:#/preparation"],
        ),
        (
            "growth.transfer_lineage_valid",
            set(lineage) == set(expected_wells)
            and all(
                lineage[target]["source_well"] in plan_by_target[target]
                for target in lineage
            ),
            ["public_evidence:#/preparation/transfer_lineage"],
        ),
        (
            "growth.unique_tip_per_transfer",
            len(facts["used_tips"])
            == len(set(facts["used_tips"]))
            == len(expected_wells),
            ["public_evidence:#/preparation/tip_usage"],
        ),
        (
            "growth.incubator_stabilized",
            incubator["released_at"] is not None
            and incubator["stabilized"] is True
            and incubator["temperature_c"] == protocol["temperature_c"],
            ["public_evidence:#/incubation"],
        ),
        (
            "growth.kinetic_complete",
            current_job is not None
            and current_job["status"] == "complete"
            and current_job["complete"] is True,
            ["public_evidence:#/kinetic_run"],
        ),
        (
            "growth.series_current",
            current_job is not None
            and current_job["plate_barcode"] == protocol["plate_barcode"]
            and current_job["protocol_revision"] == protocol["revision"],
            ["public_evidence:#/protocol", "public_evidence:#/kinetic_run"],
        ),
        (
            "growth.series_contract",
            current_job is not None
            and current_job["wavelength_nm"] == 600
            and current_job["interval_seconds"] == 120
            and current_job["duration_seconds"] == 72000
            and current_job["observation_count"] == 601
            and set(current_job["series"]) == set(expected_wells),
            ["public_evidence:#/kinetic_run"],
        ),
        (
            "growth.result_record_complete",
            result_record is not None
            and result_record["phase"] == "patched"
            and result_metadata.get("qc_status") == "accepted"
            and result_metadata.get("plate_barcode") == protocol["plate_barcode"]
            and result_metadata.get("protocol_revision") == protocol["revision"]
            and result_metadata.get("kinetic_job_id") == current_job_id
            and result_metadata.get("observation_count") == 601
            and result_metadata.get("expected_wells") == expected_wells,
            ["public_evidence:#/result_record"],
        ),
        (
            "growth.workflow_ordered",
            _operations_ordered(
                operation_ids,
                (
                    "elabftw.get_experiment",
                    "pylabrobot.transfer",
                    "pylabrobot.incubator_load",
                    "pylabrobot.incubator_release",
                    "pylabrobot.start_kinetic_read",
                    "pylabrobot.get_kinetic_read",
                    "elabftw.create_experiment",
                    "elabftw.patch_experiment",
                    "elabftw.get_experiment",
                ),
            ),
            ["public_evidence:#/operation_sequence"],
        ),
        (
            "growth.provider_mechanisms_executed",
            facts["provider_execution_counts"]["ot2"] >= len(expected_wells)
            and facts["provider_execution_counts"]["incubator"] >= 2
            and facts["provider_execution_counts"]["plate_reader"] >= 1,
            ["public_evidence:#/provider_execution_counts"],
        ),
    )
    checks = tuple(
        {
            "code": code,
            "passed": bool(passed),
            "evidence_refs": refs,
        }
        for code, passed, refs in checks_raw
    )
    failures = tuple(check["code"] for check in checks if not check["passed"])
    public_evidence = _public_evidence(
        protocol=protocol,
        deck=deck,
        incubator=incubator,
        facts=facts,
        current_job_id=current_job_id,
        current_job=current_job,
        result_record=result_record,
        operation_ids=operation_ids,
    )
    return GrowthVerifierResult(not failures, checks, failures, public_evidence)


def _selected_result_record(
    records: Mapping[str, Any],
    record_id: Any,
) -> Mapping[str, Any] | None:
    if not isinstance(record_id, int):
        return None
    return records.get(str(record_id))


def _operations_ordered(actual: list[str], required: tuple[str, ...]) -> bool:
    cursor = 0
    for operation in actual:
        if cursor < len(required) and operation == required[cursor]:
            cursor += 1
    return cursor == len(required)


def _public_evidence(
    *,
    protocol: Mapping[str, Any],
    deck: Mapping[str, Any],
    incubator: Mapping[str, Any],
    facts: Mapping[str, Any],
    current_job_id: Any,
    current_job: Mapping[str, Any] | None,
    result_record: Mapping[str, Any] | None,
    operation_ids: list[str],
) -> dict[str, Any]:
    result_metadata = result_record.get("metadata", {}) if result_record else {}
    kinetic_run = None
    if current_job is not None:
        kinetic_run = {
            "job_id": current_job_id,
            "status": current_job.get("status"),
            "complete": current_job.get("complete"),
            "plate_barcode": current_job.get("plate_barcode"),
            "protocol_revision": current_job.get("protocol_revision"),
            "wavelength_nm": current_job.get("wavelength_nm"),
            "interval_seconds": current_job.get("interval_seconds"),
            "duration_seconds": current_job.get("duration_seconds"),
            "observation_count": current_job.get("observation_count"),
            "expected_wells": list(current_job.get("expected_wells", [])),
            "series_commitment": _series_commitment(current_job.get("series", {})),
            "started_at": current_job.get("started_at"),
            "completed_at": current_job.get("completed_at"),
        }
    return {
        "schema_version": "science_growth_kinetics_public_evidence_v1",
        "operation_sequence": operation_ids,
        "protocol": {
            "experiment_id": protocol["experiment_id"],
            "plate_barcode": protocol["plate_barcode"],
            "revision": protocol["revision"],
            "expected_wells": list(protocol["expected_wells"]),
            "target_volume_ul": protocol["target_volume_ul"],
            "temperature_c": protocol["temperature_c"],
            "stabilization_seconds": protocol["stabilization_seconds"],
            "wavelength_nm": protocol["wavelength_nm"],
            "interval_seconds": protocol["interval_seconds"],
            "duration_seconds": protocol["duration_seconds"],
            "expected_observation_count": protocol["expected_observation_count"],
        },
        "preparation": {
            "complete": facts["prep_complete"],
            "target_volumes_ul": {
                well: deck["target_volumes_ul"].get(well)
                for well in protocol["expected_wells"]
            },
            "transfer_lineage": facts["transfer_lineage"],
            "tip_usage": {
                "count": len(facts["used_tips"]),
                "distinct_count": len(set(facts["used_tips"])),
            },
        },
        "incubation": {
            "plate_barcode": incubator.get("plate_barcode"),
            "temperature_c": incubator.get("temperature_c"),
            "shaking_hz": incubator.get("shaking_hz"),
            "stabilized": incubator.get("stabilized"),
            "loaded_at": incubator.get("loaded_at"),
            "released_at": incubator.get("released_at"),
        },
        "kinetic_run": kinetic_run,
        "result_record": (
            None
            if result_record is None
            else {
                "phase": result_record.get("phase"),
                "qc_status": result_metadata.get("qc_status"),
                "plate_barcode": result_metadata.get("plate_barcode"),
                "protocol_revision": result_metadata.get("protocol_revision"),
                "kinetic_job_id": result_metadata.get("kinetic_job_id"),
                "observation_count": result_metadata.get("observation_count"),
                "expected_wells": result_metadata.get("expected_wells"),
            }
        ),
        "provider_execution_counts": facts["provider_execution_counts"],
    }


def _series_commitment(series: Any) -> dict[str, Any]:
    if not isinstance(series, Mapping):
        return {"sha256": None, "well_count": 0, "total_values": 0}
    canonical = json.dumps(
        series,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return {
        "sha256": f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        "well_count": len(series),
        "total_values": sum(
            len(values) for values in series.values() if isinstance(values, list)
        ),
    }
