"""Public dry-run tools for lab_campaign_ops_v0 task families."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolError(Exception):
    """Stable, agent-readable tool error."""

    code: str
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


def dispatch_tool(
    *,
    tool_family: str,
    tool_id: str,
    state: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Invoke one public dry-run tool against a mutable sandbox state copy."""

    tool_name = f"{tool_family}.{tool_id}"
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise ToolError(
            code="UNKNOWN_TOOL",
            message="Tool is not exposed by this lab campaign runtime.",
            details={"tool_family": tool_family, "tool_id": tool_id},
        )
    return handler(state, args)


def get_assay_request(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    assay_request_id = _require_string(args, "assay_request_id")
    worklist = state.get("worklist", {})
    if worklist.get("assay_request_id") != assay_request_id:
        raise ToolError(
            code="ASSAY_REQUEST_NOT_FOUND",
            message="No sandbox assay request matches the requested id.",
            details={"assay_request_id": assay_request_id},
        )

    sample_ids = set(worklist.get("sample_ids", []))
    return _ok(
        "benchling_assay_v1.get_assay_request",
        {
            "assay_request_id": assay_request_id,
            "worklist": copy.deepcopy(worklist),
            "samples_entities": [
                copy.deepcopy(item)
                for item in state.get("samples_entities", [])
                if item.get("sample_id") in sample_ids
            ],
            "plate_map": [
                copy.deepcopy(item)
                for item in state.get("plate_map", [])
                if item.get("sample_id") in sample_ids
            ],
        },
    )


def list_instrument_records(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    sample_id = args.get("sample_id")
    entity_id = args.get("entity_id")
    records = []
    for record in state.get("instrument_readout_records", []):
        if sample_id is not None and record.get("sample_id") != sample_id:
            continue
        if entity_id is not None and record.get("entity_id") != entity_id:
            continue
        records.append(_instrument_record_summary(record))

    return _ok(
        "tetrascience_context_v1.list_instrument_records",
        {
            "records": records,
            "filters": {
                "sample_id": sample_id,
                "entity_id": entity_id,
            },
        },
    )


def get_instrument_record(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    record_id = _require_string(args, "record_id")
    record = _find_instrument_record(state, record_id)
    if record is None:
        raise ToolError(
            code="UNKNOWN_CONTEXT_RECORD",
            message="No sandbox instrument context record matches the requested id.",
            details={"record_id": record_id},
        )
    return _ok("tetrascience_context_v1.get_instrument_record", {"record": copy.deepcopy(record)})


def upload_protocol(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    protocol_id = _require_string(args, "protocol_id")
    protocol_name = _require_string(args, "protocol_name")
    assay_request_id = _require_string(args, "assay_request_id")

    if state.get("worklist", {}).get("assay_request_id") != assay_request_id:
        raise ToolError(
            code="PROTOCOL_ASSAY_REQUEST_MISMATCH",
            message="Uploaded protocol does not match the sandbox assay request.",
            details={"assay_request_id": assay_request_id},
        )

    protocol_state = state.setdefault("protocol_analysis_state", {})
    protocol_state.update(
        {
            "protocol_id": protocol_id,
            "protocol_name": protocol_name,
            "assay_request_id": assay_request_id,
            "analysis_id": "not_analyzed",
            "status": "uploaded",
            "is_current": False,
            "accepted": False,
            "commands": [],
            "errors": [],
            "warnings": [],
            "dry_run_plan_id": "not_created",
            "dry_run_plan_status": "not_created",
            "source_pack_id": "opentrons_http_v1",
            "source_status": protocol_state.get("source_status", "speculative_calibration_only"),
        }
    )
    boundary_event = _boundary_event(
        state=state,
        source_pack_id="opentrons_http_v1",
        action="upload_protocol",
        extra={"protocol_id": protocol_id},
    )
    return _ok(
        "opentrons_http_v1.upload_protocol",
        {
            "protocol": {
                "protocol_id": protocol_id,
                "protocol_name": protocol_name,
                "status": "uploaded",
            },
            "dry_run_boundary_event": copy.deepcopy(boundary_event),
        },
    )


def analyze_protocol(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    protocol_id = _require_string(args, "protocol_id")
    analysis_id = _require_string(args, "analysis_id")
    protocol_state = state.get("protocol_analysis_state", {})
    if protocol_state.get("protocol_id") != protocol_id or protocol_state.get("status") not in {"uploaded", "completed"}:
        raise ToolError(
            code="PROTOCOL_NOT_UPLOADED",
            message="Protocol must be uploaded in sandbox state before analysis.",
            details={"protocol_id": protocol_id},
        )

    plate_map = state.get("plate_map", [])
    if not plate_map:
        raise ToolError(
            code="PROTOCOL_ANALYSIS_FAILED",
            message="Protocol analysis cannot build commands without a plate map.",
            details={"protocol_id": protocol_id},
        )
    target_well = plate_map[0].get("well")
    transfer_volume_ul = int(args.get("transfer_volume_ul", protocol_state.get("transfer_volume_ul", 100)))
    commands = [
        {
            "command_id": f"{analysis_id}_cmd_001",
            "command_type": "loadLabware",
            "params": {"location": "D1", "load_name": args.get("tiprack", "opentrons_96_tiprack_300ul")},
        },
        {
            "command_id": f"{analysis_id}_cmd_002",
            "command_type": "aspirate",
            "params": {"well": "A1", "volume_ul": transfer_volume_ul},
        },
        {
            "command_id": f"{analysis_id}_cmd_003",
            "command_type": "dispense",
            "params": {"well": target_well, "volume_ul": transfer_volume_ul},
        },
    ]
    protocol_state.update(
        {
            "analysis_id": analysis_id,
            "status": "completed",
            "is_current": True,
            "accepted": True,
            "commands": commands,
            "errors": [],
            "warnings": [],
            "transfer_volume_ul": transfer_volume_ul,
        }
    )
    boundary_event = _boundary_event(
        state=state,
        source_pack_id="opentrons_http_v1",
        action="analyze_protocol",
        extra={"protocol_id": protocol_id, "analysis_id": analysis_id},
    )
    return _ok(
        "opentrons_http_v1.analyze_protocol",
        {
            "analysis": _protocol_analysis_summary(protocol_state),
            "dry_run_boundary_event": copy.deepcopy(boundary_event),
        },
    )


def get_protocol_analysis(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    analysis_id = _require_string(args, "analysis_id")
    protocol_state = state.get("protocol_analysis_state", {})
    if protocol_state.get("analysis_id") != analysis_id or protocol_state.get("status") == "not_required":
        raise ToolError(
            code="PROTOCOL_ANALYSIS_NOT_FOUND",
            message="No sandbox protocol analysis matches the requested id.",
            details={"analysis_id": analysis_id},
        )
    return _ok("opentrons_http_v1.get_protocol_analysis", {"analysis": _protocol_analysis_summary(protocol_state)})


def create_dry_run_plan(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    analysis_id = _require_string(args, "analysis_id")
    dry_run_plan_id = _require_string(args, "dry_run_plan_id")
    protocol_state = state.get("protocol_analysis_state", {})
    if protocol_state.get("analysis_id") != analysis_id:
        raise ToolError(
            code="PROTOCOL_ANALYSIS_NOT_FOUND",
            message="No sandbox protocol analysis matches the requested id.",
            details={"analysis_id": analysis_id},
        )
    if protocol_state.get("status") != "completed" or not protocol_state.get("is_current"):
        raise ToolError(
            code="STALE_ANALYSIS",
            message="Dry-run plan requires a current completed protocol analysis.",
            details={"analysis_id": analysis_id, "status": protocol_state.get("status")},
        )
    if protocol_state.get("errors"):
        raise ToolError(
            code="PROTOCOL_ANALYSIS_FAILED",
            message="Dry-run plan cannot be created from an analysis with errors.",
            details={"analysis_id": analysis_id, "errors": copy.deepcopy(protocol_state.get("errors"))},
        )

    protocol_state.update(
        {
            "dry_run_plan_id": dry_run_plan_id,
            "dry_run_plan_status": "accepted",
            "dry_run_plan_source": "sandbox_analysis",
        }
    )
    boundary_event = _boundary_event(
        state=state,
        source_pack_id="opentrons_http_v1",
        action="create_dry_run_plan",
        extra={"analysis_id": analysis_id, "dry_run_plan_id": dry_run_plan_id},
    )
    return _ok(
        "opentrons_http_v1.create_dry_run_plan",
        {
            "dry_run_plan": {
                "dry_run_plan_id": dry_run_plan_id,
                "analysis_id": analysis_id,
                "status": "accepted",
                "commands": copy.deepcopy(protocol_state.get("commands", [])),
                "live_execution": "forbidden",
            },
            "dry_run_boundary_event": copy.deepcopy(boundary_event),
        },
    )


def create_assay_result_draft(state: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    result_id = _require_string(args, "result_id")
    assay_request_id = _require_string(args, "assay_request_id")
    sample_id = _require_string(args, "sample_id")
    entity_id = _require_string(args, "entity_id")
    measurement_record_id = _require_string(args, "measurement_record_id")
    evidence_record_ids = args.get("evidence_record_ids")
    if not isinstance(evidence_record_ids, list) or not all(isinstance(item, str) for item in evidence_record_ids):
        raise ToolError(
            code="RESULT_PROVENANCE_MISSING",
            message="Assay result draft must cite evidence_record_ids.",
            details={"result_id": result_id},
        )

    worklist = state.get("worklist", {})
    if worklist.get("assay_request_id") != assay_request_id:
        raise ToolError(
            code="RESULT_SCHEMA_MISMATCH",
            message="Draft assay_request_id does not match sandbox worklist.",
            details={"assay_request_id": assay_request_id},
        )
    if sample_id not in worklist.get("sample_ids", []):
        raise ToolError(
            code="UNKNOWN_SAMPLE_ENTITY",
            message="Draft sample_id is not present in the sandbox worklist.",
            details={"sample_id": sample_id},
        )
    if not any(
        item.get("sample_id") == sample_id and item.get("entity_id") == entity_id
        for item in state.get("samples_entities", [])
    ):
        raise ToolError(
            code="UNKNOWN_SAMPLE_ENTITY",
            message="Draft entity_id is not linked to the sandbox sample.",
            details={"sample_id": sample_id, "entity_id": entity_id},
        )

    measurement_record = _find_instrument_record(state, measurement_record_id)
    if measurement_record is None:
        raise ToolError(
            code="UNKNOWN_CONTEXT_RECORD",
            message="Draft measurement_record_id is not present in sandbox instrument records.",
            details={"measurement_record_id": measurement_record_id},
        )
    missing_evidence = [record_id for record_id in evidence_record_ids if not _evidence_id_exists(state, record_id)]
    if missing_evidence:
        raise ToolError(
            code="RESULT_PROVENANCE_MISSING",
            message="Draft cites evidence records that are absent from sandbox state.",
            details={"missing_evidence_record_ids": missing_evidence},
        )

    result_record = {
        "result_id": result_id,
        "assay_request_id": assay_request_id,
        "entity_id": entity_id,
        "sample_id": sample_id,
        "evidence_record_ids": list(evidence_record_ids),
        "measurement_record_id": measurement_record_id,
        "measurement": copy.deepcopy(measurement_record["measurement"]),
        "protocol_analysis_id": args.get("protocol_analysis_id"),
        "dry_run_plan_id": args.get("dry_run_plan_id"),
        "source_pack_id": "benchling_assay_v1",
        "source_status": "speculative_calibration_only",
        "write_scope": "sandbox_only",
    }
    state.setdefault("result_upload_records", []).append(result_record)

    boundary_event = _boundary_event(
        state=state,
        source_pack_id="benchling_assay_v1",
        action="create_assay_result_draft",
        extra={"result_id": result_id},
    )

    return _ok(
        "benchling_assay_v1.create_assay_result_draft",
        {
            "result": copy.deepcopy(result_record),
            "dry_run_boundary_event": copy.deepcopy(boundary_event),
        },
    )


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "benchling_assay_v1.get_assay_request": get_assay_request,
    "tetrascience_context_v1.list_instrument_records": list_instrument_records,
    "tetrascience_context_v1.get_instrument_record": get_instrument_record,
    "opentrons_http_v1.upload_protocol": upload_protocol,
    "opentrons_http_v1.analyze_protocol": analyze_protocol,
    "opentrons_http_v1.get_protocol_analysis": get_protocol_analysis,
    "opentrons_http_v1.create_dry_run_plan": create_dry_run_plan,
    "benchling_assay_v1.create_assay_result_draft": create_assay_result_draft,
}


def _ok(tool_name: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "tool": tool_name,
        "data": data,
    }


def _require_string(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ToolError(
            code="ARGUMENT_SCHEMA_MISMATCH",
            message="Required string argument is missing or empty.",
            details={"argument": key},
        )
    return value


def _find_instrument_record(state: dict[str, Any], record_id: str) -> dict[str, Any] | None:
    for record in state.get("instrument_readout_records", []):
        if record.get("record_id") == record_id:
            return record
    return None


def _evidence_id_exists(state: dict[str, Any], evidence_id: str) -> bool:
    if _find_instrument_record(state, evidence_id) is not None:
        return True
    protocol_state = state.get("protocol_analysis_state", {})
    return evidence_id in {
        protocol_state.get("analysis_id"),
        protocol_state.get("dry_run_plan_id"),
    }


def _protocol_analysis_summary(protocol_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocol_id": protocol_state.get("protocol_id"),
        "protocol_name": protocol_state.get("protocol_name"),
        "analysis_id": protocol_state.get("analysis_id"),
        "status": protocol_state.get("status"),
        "is_current": protocol_state.get("is_current"),
        "accepted": protocol_state.get("accepted"),
        "commands": copy.deepcopy(protocol_state.get("commands", [])),
        "errors": copy.deepcopy(protocol_state.get("errors", [])),
        "warnings": copy.deepcopy(protocol_state.get("warnings", [])),
        "dry_run_plan_id": protocol_state.get("dry_run_plan_id"),
        "dry_run_plan_status": protocol_state.get("dry_run_plan_status"),
        "source_pack_id": protocol_state.get("source_pack_id"),
    }


def _boundary_event(
    *,
    state: dict[str, Any],
    source_pack_id: str,
    action: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": f"dry_run_write_{len(state.get('dry_run_boundary_events', [])) + 1:04d}",
        "source_pack_id": source_pack_id,
        "action": action,
        "boundary_status": "allowed_sandbox_write",
    }
    if extra:
        event.update(extra)
    state.setdefault("dry_run_boundary_events", []).append(event)
    return event


def _instrument_record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": record.get("record_id"),
        "run_id": record.get("run_id"),
        "status": record.get("status"),
        "freshness": record.get("freshness"),
        "sample_id": record.get("sample_id"),
        "entity_id": record.get("entity_id"),
        "plate_well": record.get("plate_well"),
        "measurement_type": record.get("measurement", {}).get("type"),
        "captured_at": record.get("captured_at"),
    }
