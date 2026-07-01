"""Generate and admit lab_campaign_ops_v0 task families."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenfield_lab_campaign_ops.worlds.lab_campaign_ops_v0.runtime import execute_plan


WORLD_ID = "lab_campaign_ops_v0"
SCHEMA_VERSION = "greenfield_lab_campaign_ops.task_bundle.v0"

STALE_TEMPLATE_ID = "stale_instrument_data_handoff"
NOMINAL_TEMPLATE_ID = "od600_qc_handoff_nominal"
TEMPLATE_IDS = (STALE_TEMPLATE_ID, NOMINAL_TEMPLATE_ID)

STALE_FAILURE_CODE = "SUBMISSION_CITES_CURRENT_INSTRUMENT_RECORD"
NOMINAL_FAILURE_CODE = "RESULT_CITES_PROTOCOL_DRY_RUN_AND_CURRENT_RECORD"

WORLD_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = WORLD_ROOT.parents[1]
SOURCE_PACK_ROOT = PACKAGE_ROOT / "source_packs"
TEMPLATE_PATHS = {template_id: WORLD_ROOT / "templates" / f"{template_id}.json" for template_id in TEMPLATE_IDS}

HIDDEN_LEAK_TOKENS = (
    STALE_FAILURE_CODE,
    NOMINAL_FAILURE_CODE,
    "verifier_expectations",
    "oracle_plan",
    "known_bad_plans",
    "expected_current_record_id",
    "hidden/",
)


@dataclass(frozen=True)
class GeneratedTask:
    task_dir: Path
    task_id: str
    template_id: str
    seed: int
    admission_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_dir": str(self.task_dir),
            "task_id": self.task_id,
            "template_id": self.template_id,
            "seed": self.seed,
            "admission": str(self.admission_path),
        }


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    code: str | None
    details: dict[str, Any]


def generate_task(
    out: Path,
    *,
    seed: int = 1,
    clean: bool = False,
    admit: bool = True,
    template_id: str = STALE_TEMPLATE_ID,
) -> GeneratedTask:
    """Generate one task bundle for a supported lab campaign task family."""

    template = _read_template(template_id)
    task_id = f"{template_id}__seed_{seed:04d}"
    task_dir = out.resolve()
    if clean and task_dir.exists():
        shutil.rmtree(task_dir)
    if task_dir.exists() and any(task_dir.iterdir()):
        raise FileExistsError(f"Task directory already exists and is not empty: {task_dir}")

    visible_dir = task_dir / "visible_artifacts"
    hidden_dir = task_dir / "hidden"
    visible_dir.mkdir(parents=True, exist_ok=True)
    hidden_dir.mkdir(parents=True, exist_ok=True)

    state = _initial_state(template, seed)
    task = _task_json(template, task_id, seed)
    agent_task = _agent_task_json(template, task_id)
    oracle_plan = _oracle_plan_json(template, seed)
    known_bad_plan = _known_bad_plan_json(template, seed)
    verifier_expectations = _verifier_expectations(template)

    _write_json(task_dir / "task.json", task)
    _write_json(task_dir / "agent_task.json", agent_task)
    _write_json(task_dir / "initial_state.json", state)
    _write_json(hidden_dir / "verifier_expectations.json", verifier_expectations)
    _write_json(hidden_dir / "oracle_plan.json", oracle_plan)
    _write_json(
        hidden_dir / "known_bad_plans.json",
        {
            "schema_version": SCHEMA_VERSION,
            "plans": [known_bad_plan],
        },
    )
    _write_visible_artifacts(visible_dir, state, template, seed)

    if admit:
        admit_task(task_dir)

    return GeneratedTask(
        task_dir=task_dir,
        task_id=task_id,
        template_id=template_id,
        seed=seed,
        admission_path=task_dir / "admission.json",
    )


def admit_task(task_dir: Path) -> dict[str, Any]:
    """Run admission checks for one generated task bundle."""

    task_dir = task_dir.resolve()
    task = _read_json(task_dir / "task.json")
    state = _read_json(task_dir / "initial_state.json")
    oracle_plan = _read_json(task_dir / "hidden" / "oracle_plan.json")
    known_bad_doc = _read_json(task_dir / "hidden" / "known_bad_plans.json")
    expectations = _read_json(task_dir / "hidden" / "verifier_expectations.json")
    template = _read_template(expectations["template_id"])
    expected_source_packs = set(template["tool_families"])
    expected_failure_code = expectations["failure_code"]
    runs_dir = task_dir / "runs"

    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, details: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"name": name, "ok": bool(ok)}
        if details:
            payload["details"] = details
        checks.append(payload)

    declared_source_packs = set(task.get("tool_families", []))
    add_check(
        "source_packs_declared",
        declared_source_packs == expected_source_packs,
        {"declared": sorted(declared_source_packs), "expected": sorted(expected_source_packs)},
    )
    missing_pack_dirs = sorted(
        pack_id for pack_id in declared_source_packs if not (SOURCE_PACK_ROOT / pack_id / "source_pack.json").is_file()
    )
    add_check("source_packs_exist", not missing_pack_dirs, {"missing": missing_pack_dirs})

    missing_artifacts = [
        item.get("path", "")
        for item in task.get("visible_artifacts", [])
        if not (task_dir / item.get("path", "")).is_file()
    ]
    add_check("visible_artifacts_exist", not missing_artifacts, {"missing": missing_artifacts})
    add_check("hidden_leakage_absent", not _visible_artifacts_leak(task_dir), {})
    add_check("task_schema_shape", _task_shape_ok(task, template), {})
    add_check("initial_state_shape", _initial_state_shape_ok(state, template), {})

    oracle_run = execute_plan(task_dir=task_dir, plan=oracle_plan, run_dir=runs_dir / "oracle")
    oracle_result = (
        _verify_final_state(oracle_run.final_state, expectations)
        if oracle_run.ok
        else VerificationResult(False, "TOOL_RUNTIME_FAILED", {"runtime_error": oracle_run.error})
    )
    add_check(
        "oracle_public_tool_run_passes",
        oracle_run.ok and oracle_result.ok,
        {
            "code": oracle_result.code,
            "run": oracle_run.trace_refs(base_dir=task_dir),
            **oracle_result.details,
        },
    )

    known_bad_plans = known_bad_doc.get("plans", [])
    known_bad_results: list[dict[str, Any]] = []
    for plan in known_bad_plans:
        run = execute_plan(task_dir=task_dir, plan=plan, run_dir=runs_dir / str(plan.get("plan_id")))
        result = (
            _verify_final_state(run.final_state, expectations)
            if run.ok
            else VerificationResult(False, "TOOL_RUNTIME_FAILED", {"runtime_error": run.error})
        )
        known_bad_results.append(
            {
                "plan_id": plan.get("plan_id"),
                "runtime_ok": run.ok,
                "verifier_ok": result.ok,
                "code": result.code,
                "expected_failure_code": plan.get("expected_failure_code"),
                "run": run.trace_refs(base_dir=task_dir),
            }
        )
    exact_known_bad_failure = bool(known_bad_results) and all(
        item["runtime_ok"]
        and (not item["verifier_ok"])
        and item["code"] == item["expected_failure_code"] == expected_failure_code
        for item in known_bad_results
    )
    add_check("known_bad_public_tool_run_fails_with_exact_code", exact_known_bad_failure, {"results": known_bad_results})

    admitted = all(check["ok"] for check in checks)
    admission = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task.get("task_id"),
        "template_id": expectations["template_id"],
        "admitted": admitted,
        "run_traces": {
            "oracle": oracle_run.trace_refs(base_dir=task_dir),
            "known_bad": [item["run"] for item in known_bad_results],
        },
        "checks": checks,
    }
    _write_json(task_dir / "admission.json", admission)
    return admission


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate one lab_campaign_ops_v0 task.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--template-id", choices=TEMPLATE_IDS, default=STALE_TEMPLATE_ID)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    generated = generate_task(args.out, seed=args.seed, clean=args.clean, template_id=args.template_id)
    admission = _read_json(generated.admission_path)
    print(json.dumps({"task": generated.to_dict(), "admitted": admission["admitted"]}, indent=2))
    return 0 if admission["admitted"] else 1


def _task_json(template: dict[str, Any], task_id: str, seed: int) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "world": WORLD_ID,
        "seed": seed,
        "tool_families": template["tool_families"],
        "failure_mode": template["failure_mode"],
        "visible_artifacts": template["visible_artifacts"],
        "hidden_state_refs": [
            "hidden/verifier_expectations.json",
            "hidden/oracle_plan.json",
            "hidden/known_bad_plans.json",
        ],
        "expected_failure_codes": _failure_codes(template),
        "cross_provider_invariants": template["cross_provider_invariants"],
        "dry_run_boundary": template["dry_run_boundary"],
    }


def _agent_task_json(template: dict[str, Any], task_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "world": WORLD_ID,
        "objective": template["objective"],
        "available_tool_families": template["tool_families"],
        "visible_artifacts": template["visible_artifacts"],
        "instructions": template.get("instructions", _default_instructions()),
        "hidden_state_warning": "Hidden verifier expectations and plan documents are not agent-visible.",
    }


def _initial_state(template: dict[str, Any], seed: int) -> dict[str, Any]:
    params = template["state_parameters"]
    source_status = template["source_status"]
    current_measurement = 1.20 + ((seed % 7) * 0.01)
    records = []
    if "stale_record_id" in params:
        records.append(
            _instrument_record(
                params=params,
                record_id=params["stale_record_id"],
                run_id=params["stale_run_id"],
                freshness="stale",
                measurement_value=round(current_measurement - 0.04, 3),
                captured_at="2026-06-29T09:30:00Z",
                source_status=source_status,
            )
        )
    records.append(
        _instrument_record(
            params=params,
            record_id=params["current_record_id"],
            run_id=params["current_run_id"],
            freshness="current",
            measurement_value=round(current_measurement, 3),
            captured_at="2026-07-01T09:30:00Z",
            source_status=source_status,
        )
    )
    return {
        "world": WORLD_ID,
        "seed": seed,
        "worklist": {
            "worklist_id": params["worklist_id"],
            "assay_request_id": params["assay_request_id"],
            "status": "ready_for_result_draft",
            "sample_ids": [params["sample_id"]],
            "source_pack_id": "benchling_assay_v1",
            "source_status": source_status,
        },
        "samples_entities": [
            {
                "sample_id": params["sample_id"],
                "entity_id": params["entity_id"],
                "source_pack_id": "benchling_assay_v1",
                "source_status": source_status,
            }
        ],
        "plate_map": [
            {
                "well": params["plate_well"],
                "sample_id": params["sample_id"],
                "entity_id": params["entity_id"],
                "source_status": source_status,
            }
        ],
        "protocol_analysis_state": _initial_protocol_state(template),
        "instrument_readout_records": records,
        "result_upload_records": [],
        "dry_run_boundary_events": [],
    }


def _initial_protocol_state(template: dict[str, Any]) -> dict[str, Any]:
    source_status = template["source_status"]
    if "opentrons_http_v1" not in template["tool_families"]:
        return {
            "protocol_id": "not_required_for_stale_instrument_data_handoff",
            "analysis_id": "not_required_for_stale_instrument_data_handoff",
            "status": "not_required",
            "is_current": True,
            "source_pack_id": "opentrons_http_v1",
            "source_status": source_status,
        }

    params = template["state_parameters"]
    return {
        "protocol_id": "not_uploaded",
        "protocol_name": params["protocol_name"],
        "analysis_id": "not_analyzed",
        "status": "not_uploaded",
        "is_current": False,
        "accepted": False,
        "commands": [],
        "errors": [],
        "warnings": [],
        "dry_run_plan_id": "not_created",
        "dry_run_plan_status": "not_created",
        "source_pack_id": "opentrons_http_v1",
        "source_status": source_status,
    }


def _instrument_record(
    *,
    params: dict[str, Any],
    record_id: str,
    run_id: str,
    freshness: str,
    measurement_value: float,
    captured_at: str,
    source_status: str,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "run_id": run_id,
        "status": "final",
        "freshness": freshness,
        "source_pack_id": "tetrascience_context_v1",
        "sample_id": params["sample_id"],
        "entity_id": params["entity_id"],
        "plate_well": params["plate_well"],
        "measurement": {
            "type": params["measurement_type"],
            "value": measurement_value,
        },
        "captured_at": captured_at,
        "source_status": source_status,
    }


def _oracle_plan_json(template: dict[str, Any], seed: int) -> dict[str, Any]:
    if template["template_id"] == STALE_TEMPLATE_ID:
        return _stale_plan_json(
            plan_id="oracle_current_record",
            template=template,
            result_id=f"result_draft_current_seed_{seed:04d}",
            evidence_record_id=template["state_parameters"]["current_record_id"],
            expected_failure_code=None,
        )
    if template["template_id"] == NOMINAL_TEMPLATE_ID:
        return _nominal_plan_json(
            plan_id="oracle_protocol_dry_run_current_record",
            template=template,
            seed=seed,
            result_id=f"result_draft_nominal_seed_{seed:04d}",
            include_protocol_evidence=True,
            expected_failure_code=None,
        )
    raise ValueError(f"Unsupported template_id: {template['template_id']}")


def _known_bad_plan_json(template: dict[str, Any], seed: int) -> dict[str, Any]:
    if template["template_id"] == STALE_TEMPLATE_ID:
        return _stale_plan_json(
            plan_id="known_bad_stale_record",
            template=template,
            result_id=f"result_draft_stale_seed_{seed:04d}",
            evidence_record_id=template["state_parameters"]["stale_record_id"],
            expected_failure_code=STALE_FAILURE_CODE,
        )
    if template["template_id"] == NOMINAL_TEMPLATE_ID:
        return _nominal_plan_json(
            plan_id="known_bad_missing_protocol_evidence",
            template=template,
            seed=seed,
            result_id=f"result_draft_missing_protocol_evidence_seed_{seed:04d}",
            include_protocol_evidence=False,
            expected_failure_code=NOMINAL_FAILURE_CODE,
        )
    raise ValueError(f"Unsupported template_id: {template['template_id']}")


def _stale_plan_json(
    *,
    plan_id: str,
    template: dict[str, Any],
    result_id: str,
    evidence_record_id: str,
    expected_failure_code: str | None,
) -> dict[str, Any]:
    params = template["state_parameters"]
    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "steps": [
            {
                "tool_family": "benchling_assay_v1",
                "tool_id": "get_assay_request",
                "args": {"assay_request_id": params["assay_request_id"]},
            },
            {
                "tool_family": "tetrascience_context_v1",
                "tool_id": "list_instrument_records",
                "args": {"sample_id": params["sample_id"], "entity_id": params["entity_id"]},
            },
            {
                "tool_family": "tetrascience_context_v1",
                "tool_id": "get_instrument_record",
                "args": {"record_id": params["stale_record_id"]},
            },
            {
                "tool_family": "tetrascience_context_v1",
                "tool_id": "get_instrument_record",
                "args": {"record_id": params["current_record_id"]},
            },
            {
                "tool_family": "benchling_assay_v1",
                "tool_id": "create_assay_result_draft",
                "args": {
                    "result_id": result_id,
                    "assay_request_id": params["assay_request_id"],
                    "sample_id": params["sample_id"],
                    "entity_id": params["entity_id"],
                    "evidence_record_ids": [evidence_record_id],
                    "measurement_record_id": evidence_record_id,
                },
            },
        ],
    }
    if expected_failure_code:
        plan["expected_failure_code"] = expected_failure_code
    return plan


def _nominal_plan_json(
    *,
    plan_id: str,
    template: dict[str, Any],
    seed: int,
    result_id: str,
    include_protocol_evidence: bool,
    expected_failure_code: str | None,
) -> dict[str, Any]:
    params = template["state_parameters"]
    ids = _protocol_ids(params, seed)
    evidence_record_ids = [params["current_record_id"]]
    if include_protocol_evidence:
        evidence_record_ids.extend([ids["analysis_id"], ids["dry_run_plan_id"]])

    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "steps": [
            {
                "tool_family": "benchling_assay_v1",
                "tool_id": "get_assay_request",
                "args": {"assay_request_id": params["assay_request_id"]},
            },
            {
                "tool_family": "opentrons_http_v1",
                "tool_id": "upload_protocol",
                "args": {
                    "protocol_id": ids["protocol_id"],
                    "protocol_name": params["protocol_name"],
                    "assay_request_id": params["assay_request_id"],
                },
            },
            {
                "tool_family": "opentrons_http_v1",
                "tool_id": "analyze_protocol",
                "args": {
                    "protocol_id": ids["protocol_id"],
                    "analysis_id": ids["analysis_id"],
                    "tiprack": params["tiprack"],
                    "transfer_volume_ul": params["transfer_volume_ul"],
                },
            },
            {
                "tool_family": "opentrons_http_v1",
                "tool_id": "get_protocol_analysis",
                "args": {"analysis_id": ids["analysis_id"]},
            },
            {
                "tool_family": "opentrons_http_v1",
                "tool_id": "create_dry_run_plan",
                "args": {"analysis_id": ids["analysis_id"], "dry_run_plan_id": ids["dry_run_plan_id"]},
            },
            {
                "tool_family": "tetrascience_context_v1",
                "tool_id": "list_instrument_records",
                "args": {"sample_id": params["sample_id"], "entity_id": params["entity_id"]},
            },
            {
                "tool_family": "tetrascience_context_v1",
                "tool_id": "get_instrument_record",
                "args": {"record_id": params["current_record_id"]},
            },
            {
                "tool_family": "benchling_assay_v1",
                "tool_id": "create_assay_result_draft",
                "args": {
                    "result_id": result_id,
                    "assay_request_id": params["assay_request_id"],
                    "sample_id": params["sample_id"],
                    "entity_id": params["entity_id"],
                    "evidence_record_ids": evidence_record_ids,
                    "measurement_record_id": params["current_record_id"],
                    "protocol_analysis_id": ids["analysis_id"] if include_protocol_evidence else None,
                    "dry_run_plan_id": ids["dry_run_plan_id"] if include_protocol_evidence else None,
                },
            },
        ],
    }
    if expected_failure_code:
        plan["expected_failure_code"] = expected_failure_code
    return plan


def _write_visible_artifacts(
    visible_dir: Path,
    state: dict[str, Any],
    template: dict[str, Any],
    seed: int,
) -> None:
    artifact_ids = {item["artifact_id"] for item in template["visible_artifacts"]}
    if "assay_request_worklist" in artifact_ids:
        _write_json(
            visible_dir / "assay_request_worklist.json",
            {
                "artifact_id": "assay_request_worklist",
                "source_pack_id": "benchling_assay_v1",
                "source_status": template["source_status"],
                "worklist": state["worklist"],
                "samples_entities": state["samples_entities"],
                "plate_map": state["plate_map"],
            },
        )
    if "protocol_artifact" in artifact_ids:
        params = template["state_parameters"]
        _write_json(
            visible_dir / "protocol_artifact.json",
            {
                "artifact_id": "protocol_artifact",
                "source_pack_id": "opentrons_http_v1",
                "source_status": template["source_status"],
                "protocol_name": params["protocol_name"],
                "assay_request_id": params["assay_request_id"],
                "plate_well": params["plate_well"],
                "pipette": params["pipette"],
                "tiprack": params["tiprack"],
                "source_labware": params["source_labware"],
                "destination_labware": params["destination_labware"],
                "transfer_volume_ul": params["transfer_volume_ul"],
                "seed": seed,
                "write_scope": "sandbox_upload_only",
            },
        )
    if "instrument_context_summary" in artifact_ids:
        _write_json(
            visible_dir / "instrument_context_summary.json",
            {
                "artifact_id": "instrument_context_summary",
                "source_pack_id": "tetrascience_context_v1",
                "source_status": template["source_status"],
                "records": [
                    {
                        "record_id": record["record_id"],
                        "run_id": record["run_id"],
                        "sample_id": record["sample_id"],
                        "entity_id": record["entity_id"],
                        "plate_well": record["plate_well"],
                        "status": record["status"],
                        "freshness": record["freshness"],
                        "measurement_type": record["measurement"]["type"],
                        "captured_at": record["captured_at"],
                    }
                    for record in state["instrument_readout_records"]
                ],
            },
        )


def _verifier_expectations(template: dict[str, Any]) -> dict[str, Any]:
    params = template["state_parameters"]
    expectations = {
        "schema_version": SCHEMA_VERSION,
        "template_id": template["template_id"],
        "source_status": template["source_status"],
        "expected_assay_request_id": params["assay_request_id"],
        "expected_entity_id": params["entity_id"],
        "expected_sample_id": params["sample_id"],
        "expected_current_record_id": params["current_record_id"],
        "failure_code": _failure_codes(template)[0],
    }
    if "stale_record_id" in params:
        expectations["stale_record_ids"] = [params["stale_record_id"]]
    return expectations


def _verify_final_state(state: dict[str, Any], expectations: dict[str, Any]) -> VerificationResult:
    if expectations["template_id"] == STALE_TEMPLATE_ID:
        return _verify_current_record_submission(state, expectations)
    if expectations["template_id"] == NOMINAL_TEMPLATE_ID:
        return _verify_protocol_dry_run_current_record_submission(state, expectations)
    return VerificationResult(False, "UNKNOWN_TEMPLATE", {"template_id": expectations.get("template_id")})


def _verify_current_record_submission(
    state: dict[str, Any],
    expectations: dict[str, Any],
) -> VerificationResult:
    expected_assay_request_id = expectations["expected_assay_request_id"]
    expected_entity_id = expectations["expected_entity_id"]
    expected_current_record_id = expectations["expected_current_record_id"]
    failure_code = expectations["failure_code"]
    records_by_id = {record["record_id"]: record for record in state["instrument_readout_records"]}
    candidates = _matching_results(state, expected_assay_request_id, expected_entity_id)
    if not candidates:
        return VerificationResult(False, "ASSAY_RESULT_DRAFT_MISSING", {})

    for result in candidates:
        evidence_ids = result.get("evidence_record_ids", [])
        if expected_current_record_id not in evidence_ids:
            return VerificationResult(
                False,
                failure_code,
                {"result_id": result.get("result_id"), "evidence_record_ids": evidence_ids},
            )
        non_current_ids = [
            record_id
            for record_id in evidence_ids
            if records_by_id.get(record_id, {}).get("freshness") != "current"
        ]
        if non_current_ids:
            return VerificationResult(
                False,
                failure_code,
                {"result_id": result.get("result_id"), "non_current_evidence_record_ids": non_current_ids},
            )
    return VerificationResult(True, None, {"result_count": len(candidates)})


def _verify_protocol_dry_run_current_record_submission(
    state: dict[str, Any],
    expectations: dict[str, Any],
) -> VerificationResult:
    expected_assay_request_id = expectations["expected_assay_request_id"]
    expected_entity_id = expectations["expected_entity_id"]
    expected_current_record_id = expectations["expected_current_record_id"]
    failure_code = expectations["failure_code"]
    records_by_id = {record["record_id"]: record for record in state["instrument_readout_records"]}
    current_record = records_by_id.get(expected_current_record_id)
    protocol_state = state.get("protocol_analysis_state", {})
    candidates = _matching_results(state, expected_assay_request_id, expected_entity_id)

    if not candidates:
        return VerificationResult(False, "ASSAY_RESULT_DRAFT_MISSING", {})
    if current_record is None or current_record.get("freshness") != "current" or current_record.get("status") != "final":
        return VerificationResult(False, failure_code, {"reason": "current_instrument_record_missing_or_not_final"})
    if not (
        protocol_state.get("status") == "completed"
        and protocol_state.get("is_current") is True
        and protocol_state.get("accepted") is True
    ):
        return VerificationResult(False, failure_code, {"reason": "protocol_analysis_not_current_accepted"})
    if protocol_state.get("dry_run_plan_status") != "accepted":
        return VerificationResult(False, failure_code, {"reason": "dry_run_plan_not_accepted"})

    analysis_id = protocol_state.get("analysis_id")
    dry_run_plan_id = protocol_state.get("dry_run_plan_id")
    required_evidence_ids = {expected_current_record_id, analysis_id, dry_run_plan_id}
    for result in candidates:
        evidence_ids = set(result.get("evidence_record_ids", []))
        missing_evidence_ids = sorted(item for item in required_evidence_ids if item not in evidence_ids)
        if missing_evidence_ids:
            return VerificationResult(
                False,
                failure_code,
                {
                    "result_id": result.get("result_id"),
                    "missing_evidence_ids": missing_evidence_ids,
                    "evidence_record_ids": sorted(evidence_ids),
                },
            )
        if result.get("measurement_record_id") != expected_current_record_id:
            return VerificationResult(
                False,
                failure_code,
                {
                    "result_id": result.get("result_id"),
                    "measurement_record_id": result.get("measurement_record_id"),
                },
            )
        if result.get("protocol_analysis_id") != analysis_id or result.get("dry_run_plan_id") != dry_run_plan_id:
            return VerificationResult(
                False,
                failure_code,
                {
                    "result_id": result.get("result_id"),
                    "protocol_analysis_id": result.get("protocol_analysis_id"),
                    "dry_run_plan_id": result.get("dry_run_plan_id"),
                },
            )
    return VerificationResult(True, None, {"result_count": len(candidates), "protocol_analysis_id": analysis_id})


def _matching_results(state: dict[str, Any], assay_request_id: str, entity_id: str) -> list[dict[str, Any]]:
    return [
        record
        for record in state.get("result_upload_records", [])
        if record.get("assay_request_id") == assay_request_id and record.get("entity_id") == entity_id
    ]


def _task_shape_ok(task: dict[str, Any], template: dict[str, Any]) -> bool:
    required = {
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
    return (
        required.issubset(task)
        and task.get("world") == WORLD_ID
        and set(task.get("tool_families", [])) == set(template["tool_families"])
        and task.get("expected_failure_codes") == _failure_codes(template)
    )


def _initial_state_shape_ok(state: dict[str, Any], template: dict[str, Any]) -> bool:
    current = [record for record in state.get("instrument_readout_records", []) if record.get("freshness") == "current"]
    stale = [record for record in state.get("instrument_readout_records", []) if record.get("freshness") == "stale"]
    protocol_state = state.get("protocol_analysis_state", {})
    base_ok = (
        state.get("world") == WORLD_ID
        and len(current) == 1
        and state.get("result_upload_records") == []
        and current[0].get("sample_id") == template["state_parameters"]["sample_id"]
        and current[0].get("entity_id") == template["state_parameters"]["entity_id"]
    )
    if template["template_id"] == STALE_TEMPLATE_ID:
        return (
            base_ok
            and len(stale) == 1
            and current[0].get("sample_id") == stale[0].get("sample_id")
            and current[0].get("entity_id") == stale[0].get("entity_id")
            and protocol_state.get("status") == "not_required"
        )
    if template["template_id"] == NOMINAL_TEMPLATE_ID:
        return (
            base_ok
            and stale == []
            and protocol_state.get("status") == "not_uploaded"
            and protocol_state.get("is_current") is False
            and protocol_state.get("dry_run_plan_status") == "not_created"
        )
    return False


def _visible_artifacts_leak(task_dir: Path) -> bool:
    visible_dir = task_dir / "visible_artifacts"
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(visible_dir.glob("*.json")))
    return any(token in text for token in HIDDEN_LEAK_TOKENS)


def _failure_codes(template: dict[str, Any]) -> list[str]:
    return [item["failure_code"] for item in template["cross_provider_invariants"]]


def _protocol_ids(params: dict[str, Any], seed: int) -> dict[str, str]:
    suffix = f"seed_{seed:04d}"
    return {
        "protocol_id": f"{params['protocol_id_prefix']}_{suffix}",
        "analysis_id": f"{params['analysis_id_prefix']}_{suffix}",
        "dry_run_plan_id": f"{params['dry_run_plan_id_prefix']}_{suffix}",
    }


def _default_instructions() -> list[str]:
    return [
        "Inspect the assay request/worklist artifact.",
        "Inspect candidate instrument context records before drafting a result.",
        "Use the current instrument record for the requested sample/entity.",
        "Create only a sandbox assay-result draft; do not call live provider APIs.",
    ]


def _read_template(template_id: str) -> dict[str, Any]:
    path = TEMPLATE_PATHS.get(template_id)
    if path is None:
        raise ValueError(f"Unsupported template_id: {template_id}")
    return _read_json(path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
