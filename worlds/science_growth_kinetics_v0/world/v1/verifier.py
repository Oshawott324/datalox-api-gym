from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from datalox_gated_runtime.world_v1.session import WorldSession


@dataclass(frozen=True)
class GrowthVerifierResult:
    passed: bool
    checks: tuple[dict[str, Any], ...]
    failure_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verifier_type": "science_growth_kinetics_v0",
            "checks": list(self.checks),
            "failure_codes": list(self.failure_codes),
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
            ["operation:elabftw.get_experiment"],
        ),
        (
            "growth.prep_complete",
            facts["prep_complete"]
            and all(
                math.isclose(float(deck["target_volumes_ul"].get(well, 0)), 200.0)
                for well in expected_wells
            ),
            ["state:facts#/prep_complete", "state:deck#/target_volumes_ul"],
        ),
        (
            "growth.transfer_lineage_valid",
            set(lineage) == set(expected_wells)
            and all(lineage[target]["source_well"] in plan_by_target[target] for target in lineage),
            ["state:facts#/transfer_lineage"],
        ),
        (
            "growth.unique_tip_per_transfer",
            len(facts["used_tips"]) == len(set(facts["used_tips"])) == len(expected_wells),
            ["state:facts#/used_tips"],
        ),
        (
            "growth.incubator_stabilized",
            incubator["released_at"] is not None
            and incubator["stabilized"] is True
            and incubator["temperature_c"] == protocol["temperature_c"],
            ["state:incubator"],
        ),
        (
            "growth.kinetic_complete",
            current_job is not None
            and current_job["status"] == "complete"
            and current_job["complete"] is True,
            ["state:reader#/jobs", "state:facts#/current_complete_job_id"],
        ),
        (
            "growth.series_current",
            current_job is not None
            and current_job["plate_barcode"] == protocol["plate_barcode"]
            and current_job["protocol_revision"] == protocol["revision"],
            ["state:protocol", "state:reader#/jobs"],
        ),
        (
            "growth.series_contract",
            current_job is not None
            and current_job["wavelength_nm"] == 600
            and current_job["interval_seconds"] == 120
            and current_job["duration_seconds"] == 72000
            and current_job["observation_count"] == 601
            and set(current_job["series"]) == set(expected_wells),
            ["state:reader#/jobs"],
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
            ["state:elabftw#/result_records"],
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
            ["event:growth_operation"],
        ),
        (
            "growth.provider_mechanisms_executed",
            facts["provider_execution_counts"]["ot2"] >= len(expected_wells)
            and facts["provider_execution_counts"]["incubator"] >= 2
            and facts["provider_execution_counts"]["plate_reader"] >= 1,
            ["state:facts#/provider_execution_counts"],
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
    return GrowthVerifierResult(not failures, checks, failures)


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
