"""Validate the lab_campaign_ops_v0 schemas and task templates."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


WORLD_ID = "lab_campaign_ops_v0"
WORLD_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = WORLD_ROOT.parents[1]
SOURCE_PACK_ROOT = PACKAGE_ROOT / "source_packs"

TASK_SCHEMA_FIELDS = {
    "task_id",
    "world",
    "seed",
    "tool_families",
    "failure_mode",
    "visible_artifacts",
    "hidden_state_refs",
    "expected_failure_codes",
    "cross_provider_invariants",
    "dry_run_boundary",
}
STATE_SCHEMA_FIELDS = {
    "world",
    "seed",
    "worklist",
    "samples_entities",
    "plate_map",
    "protocol_analysis_state",
    "instrument_readout_records",
    "result_upload_records",
    "dry_run_boundary_events",
}
EXPECTED_SOURCE_PACKS = {
    "benchling_assay_v1",
    "opentrons_http_v1",
    "tetrascience_context_v1",
}
REQUIRED_TEMPLATE_FIELDS = {
    "template_id",
    "world",
    "source_status",
    "failure_mode",
    "tool_families",
    "source_pack_fixture_refs",
    "objective",
    "visible_artifacts",
    "cross_provider_invariants",
    "dry_run_boundary",
    "state_parameters",
}
TEMPLATE_EXPECTATIONS = {
    "stale_instrument_data_handoff": {
        "path": WORLD_ROOT / "templates" / "stale_instrument_data_handoff.json",
        "tool_families": {"benchling_assay_v1", "tetrascience_context_v1"},
        "artifact_ids": {"assay_request_worklist", "instrument_context_summary"},
        "failure_code": "SUBMISSION_CITES_CURRENT_INSTRUMENT_RECORD",
        "required_params": {
            "assay_request_id",
            "worklist_id",
            "sample_id",
            "entity_id",
            "plate_well",
            "current_run_id",
            "stale_run_id",
            "current_record_id",
            "stale_record_id",
            "measurement_type",
        },
    },
    "od600_qc_handoff_nominal": {
        "path": WORLD_ROOT / "templates" / "od600_qc_handoff_nominal.json",
        "tool_families": {"benchling_assay_v1", "opentrons_http_v1", "tetrascience_context_v1"},
        "artifact_ids": {"assay_request_worklist", "protocol_artifact", "instrument_context_summary"},
        "failure_code": "RESULT_CITES_PROTOCOL_DRY_RUN_AND_CURRENT_RECORD",
        "required_params": {
            "assay_request_id",
            "worklist_id",
            "sample_id",
            "entity_id",
            "plate_well",
            "current_run_id",
            "current_record_id",
            "measurement_type",
            "protocol_name",
            "protocol_id_prefix",
            "analysis_id_prefix",
            "dry_run_plan_id_prefix",
            "pipette",
            "tiprack",
            "source_labware",
            "destination_labware",
            "transfer_volume_ul",
        },
    },
}


def main() -> int:
    failures: list[str] = []

    task_schema = _load_object(WORLD_ROOT / "task_schema.json", failures)
    state_schema = _load_object(WORLD_ROOT / "state_schema.json", failures)
    refs = _load_object(WORLD_ROOT / "source_pack_refs.json", failures)

    if task_schema:
        failures.extend(
            _validate_schema(
                path=WORLD_ROOT / "task_schema.json",
                schema=task_schema,
                required_fields=TASK_SCHEMA_FIELDS,
            )
        )
    if state_schema:
        failures.extend(
            _validate_schema(
                path=WORLD_ROOT / "state_schema.json",
                schema=state_schema,
                required_fields=STATE_SCHEMA_FIELDS,
            )
        )
    if refs:
        failures.extend(_validate_source_pack_refs(refs))

    for template_id, expectations in TEMPLATE_EXPECTATIONS.items():
        template = _load_object(expectations["path"], failures)
        if template:
            failures.extend(_validate_template(template_id, template, expectations))

    if failures:
        for failure in failures:
            print(failure)
        return 1

    print(
        f"Validated {WORLD_ID} schemas, {len(EXPECTED_SOURCE_PACKS)} source-pack reference(s), "
        f"and {len(TEMPLATE_EXPECTATIONS)} task template(s)."
    )
    return 0


def _validate_schema(path: Path, schema: dict[str, Any], required_fields: set[str]) -> list[str]:
    failures: list[str] = []
    if schema.get("type") != "object":
        failures.append(f"{path}: ROOT_TYPE_NOT_OBJECT")

    required = schema.get("required")
    if not isinstance(required, list):
        failures.append(f"{path}: REQUIRED_NOT_LIST")
        required = []
    missing_required = sorted(required_fields - set(required))
    if missing_required:
        failures.append(f"{path}: MISSING_REQUIRED_FIELDS {missing_required}")

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        failures.append(f"{path}: PROPERTIES_NOT_OBJECT")
        properties = {}
    missing_properties = sorted(required_fields - set(properties))
    if missing_properties:
        failures.append(f"{path}: MISSING_PROPERTIES {missing_properties}")

    world_property = properties.get("world")
    if not isinstance(world_property, dict) or world_property.get("const") != WORLD_ID:
        failures.append(f"{path}: WORLD_CONST_NOT_{WORLD_ID}")

    return failures


def _validate_source_pack_refs(refs: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if refs.get("world") != WORLD_ID:
        failures.append(f"source_pack_refs.json: BAD_WORLD {refs.get('world')!r}")

    source_packs = refs.get("source_packs")
    if not isinstance(source_packs, list):
        return failures + ["source_pack_refs.json: SOURCE_PACKS_NOT_LIST"]

    ref_ids: set[str] = set()
    for index, item in enumerate(source_packs):
        if not isinstance(item, dict):
            failures.append(f"source_pack_refs.json: source_packs[{index}] NOT_OBJECT")
            continue
        pack_id = item.get("source_pack_id")
        if not isinstance(pack_id, str) or not pack_id:
            failures.append(f"source_pack_refs.json: source_packs[{index}] missing source_pack_id")
            continue
        if pack_id in ref_ids:
            failures.append(f"source_pack_refs.json: DUPLICATE_SOURCE_PACK_REF {pack_id}")
        ref_ids.add(pack_id)

        pack_dir = SOURCE_PACK_ROOT / pack_id
        pack_json = pack_dir / "source_pack.json"
        if not pack_dir.is_dir():
            failures.append(f"source_pack_refs.json: SOURCE_PACK_DIR_MISSING {pack_dir}")
            continue
        if not pack_json.is_file():
            failures.append(f"source_pack_refs.json: SOURCE_PACK_JSON_MISSING {pack_json}")
            continue
        pack = _load_object(pack_json, failures)
        if pack and pack.get("source_pack_id") != pack_id:
            failures.append(f"source_pack_refs.json: SOURCE_PACK_ID_MISMATCH {pack_id}")

    missing_refs = sorted(EXPECTED_SOURCE_PACKS - ref_ids)
    extra_refs = sorted(ref_ids - EXPECTED_SOURCE_PACKS)
    if missing_refs:
        failures.append(f"source_pack_refs.json: MISSING_SOURCE_PACK_REFS {missing_refs}")
    if extra_refs:
        failures.append(f"source_pack_refs.json: UNKNOWN_SOURCE_PACK_REFS {extra_refs}")

    return failures


def _validate_template(
    template_id: str,
    template: dict[str, Any],
    expectations: dict[str, Any],
) -> list[str]:
    path = expectations["path"]
    failures: list[str] = []
    missing = sorted(REQUIRED_TEMPLATE_FIELDS - set(template))
    if missing:
        return [f"{path}: MISSING_TEMPLATE_FIELDS {missing}"]

    if template.get("template_id") != template_id:
        failures.append(f"{path}: BAD_TEMPLATE_ID {template.get('template_id')!r}")
    if template.get("world") != WORLD_ID:
        failures.append(f"{path}: BAD_WORLD {template.get('world')!r}")
    if template.get("source_status") != "speculative_calibration_only":
        failures.append(f"{path}: BAD_SOURCE_STATUS {template.get('source_status')!r}")

    tool_families = set(_expect_list(template.get("tool_families")))
    if tool_families != expectations["tool_families"]:
        failures.append(f"{path}: BAD_TOOL_FAMILIES {sorted(tool_families)}")

    artifact_ids = {
        item.get("artifact_id")
        for item in _expect_list(template.get("visible_artifacts"))
        if isinstance(item, dict)
    }
    if artifact_ids != expectations["artifact_ids"]:
        failures.append(f"{path}: BAD_VISIBLE_ARTIFACTS {sorted(artifact_ids)}")

    failure_codes = {
        item.get("failure_code")
        for item in _expect_list(template.get("cross_provider_invariants"))
        if isinstance(item, dict)
    }
    if expectations["failure_code"] not in failure_codes:
        failures.append(f"{path}: MISSING_FAILURE_CODE {expectations['failure_code']}")

    params = template.get("state_parameters")
    if not isinstance(params, dict):
        failures.append(f"{path}: STATE_PARAMETERS_NOT_OBJECT")
        return failures
    missing_params = sorted(expectations["required_params"] - set(params))
    if missing_params:
        failures.append(f"{path}: MISSING_STATE_PARAMETERS {missing_params}")
    if "stale_record_id" in params and params.get("current_record_id") == params.get("stale_record_id"):
        failures.append(f"{path}: CURRENT_AND_STALE_RECORD_IDS_MATCH")

    return failures


def _load_object(path: Path, failures: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        failures.append(f"{path}: FILE_MISSING")
        return None
    except json.JSONDecodeError as exc:
        failures.append(f"{path}: INVALID_JSON {exc.msg} line={exc.lineno} column={exc.colno}")
        return None

    if not isinstance(value, dict):
        failures.append(f"{path}: JSON_ROOT_NOT_OBJECT")
        return None
    return value


def _expect_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


if __name__ == "__main__":
    sys.exit(main())
