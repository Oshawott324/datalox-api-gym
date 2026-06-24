"""Dry-run Automata LINQ workflow planning service operations."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_gym.worlds.automata_linq_workflow_planning_v0.state import (
    connect,
    dumps_json,
    insert_audit,
    insert_event,
    loads_json,
)

AGENT_ACTOR = "agent@automata-linq.example"
SOURCE_PACK_VERSION = "2026-06-22"
ALLOWED_NEXT_STEPS = ["validate_workflow", "plan_workflow", "get_plan_status", "get_plan_result"]


def get_api_version(db_path: Path) -> dict[str, Any]:
    _ = db_path
    return _ok({"version": SOURCE_PACK_VERSION})


def get_organizations(db_path: Path) -> dict[str, Any]:
    with connect(db_path) as conn:
        organizations = [
            {
                "externalID": row["external_id"],
                "id": row["id"],
                "logo": row["logo_url"],
                "name": row["name"],
                "slug": row["slug"],
                "workspace": row["workspace_id"],
            }
            for row in conn.execute("SELECT * FROM organizations ORDER BY name")
        ]
    return _ok({"organizations": organizations})


def get_scheduler_versions(db_path: Path) -> dict[str, Any]:
    versions: dict[str, list[str]] = {}
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM scheduler_versions ORDER BY scheduler, is_default DESC, version DESC"
        ).fetchall()
    for row in rows:
        versions.setdefault(row["scheduler"], []).append(row["version"])
    return _ok(versions)


def get_all_drivers(db_path: Path, scheduler: str, version: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        if not _scheduler_version_exists(conn, scheduler, version):
            return _error(
                "scheduler_version_not_found",
                "Scheduler/version is not available in this dry-run world.",
                {"scheduler": scheduler, "version": version},
            )
        rows = conn.execute(
            """
            SELECT * FROM drivers
            WHERE scheduler = ? AND scheduler_version = ?
            ORDER BY name, version
            """,
            (scheduler, version),
        ).fetchall()
    return _ok(
        [
            {
                "name": row["name"],
                "version": row["version"],
                "configuration": loads_json(row["configuration_json"]) or {},
                "actions": loads_json(row["actions_json"]) or {},
                "protocols": loads_json(row["protocols_json"]) or {},
                "metadata": loads_json(row["metadata_json"]) or {},
            }
            for row in rows
        ]
    )


def get_workcells(db_path: Path, workspace_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM workcells WHERE workspace_id = ? ORDER BY name",
            (workspace_id,),
        ).fetchall()
    return _ok(
        {
            "workcells": [
                {
                    "hub_id": row["hub_id"],
                    "hub_last_access": row["hub_last_access"],
                    "id": row["id"],
                    "mode": row["mode"],
                    "name": row["name"],
                    "status": row["status"],
                    "transport_config_id": row["transport_config_id"],
                    "transport_config_type": row["transport_config_type"],
                    "transport_config_version": row["transport_config_version"],
                }
                for row in rows
            ]
        }
    )


def get_device_status(db_path: Path, device_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if row is None:
        return _error("device_not_found", "Device id is not present in this dry-run world.", {"device_id": device_id})
    return _ok(
        {
            "id": row["id"],
            "name": row["name"],
            "serial": row["serial"],
            "online": bool(row["online"]),
            "state": {"status": row["state_status"], "details": row["state_details"]},
            "error": loads_json(row["error_json"]),
        }
    )


def get_run_histories(db_path: Path, device_id: str, count: int | None = None) -> dict[str, Any]:
    limit = 100 if count is None else max(1, min(int(count), 1000))
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM run_histories
            WHERE device_id = ?
            ORDER BY start_time DESC
            LIMIT ?
            """,
            (device_id, limit),
        ).fetchall()
    return _ok(
        {
            "list": [
                {
                    "id": row["id"],
                    "device_id": row["device_id"],
                    "last_updated": row["last_updated"],
                    "owner": loads_json(row["owner_json"]) or {},
                    "outcome": row["outcome"],
                    "outcome_details": row["outcome_details"],
                    "start_time": row["start_time"],
                    "stop_time": row["stop_time"],
                    "workflow": loads_json(row["workflow_json"]),
                    "tags": loads_json(row["tags_json"]) or [],
                }
                for row in rows
            ],
            "next_cursor": None,
        }
    )


def export_run_logs(db_path: Path, run_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM log_exports WHERE run_history_id = ?", (run_id,)).fetchone()
        if row is None:
            return _error("log_export_not_found", "No dry-run log export exists for this run history.", {"run_id": run_id})
        _record_audit(
            conn,
            action="automata_linq.export_run_logs",
            object_type="run_history",
            object_id=run_id,
            request={"run_id": run_id},
            response={"ok": True, "data": {"download_url": row["download_url"]}},
        )
        return _ok({"download_url": row["download_url"]})


def create_workflow(db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    with connect(db_path) as conn:
        workflow_id = str(payload.get("id") or _next_id(conn, "workflows", "workflow_agent"))
        config = _workflow_config_payload(payload)
        conn.execute(
            """
            INSERT INTO workflows (
              id, name, author, creator_username, version, workflow_type, published,
              created_at, updated_at, published_at, parameter_definitions_json,
              valid_batch_data_json, synced_plan_id, workflow_config_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_id,
                str(payload.get("name", "Untitled dry-run workflow")),
                "api-gym-agent",
                "api-gym-agent",
                "1.0.0",
                "dry_run",
                0,
                now,
                now,
                None,
                dumps_json(payload.get("parameter_definitions", [])),
                dumps_json({}),
                None,
                dumps_json(config),
                dumps_json({"source_shape": "response_case:createWorkflow:success"}),
            ),
        )
        response = _workflow_info_from_payload(workflow_id, payload, now)
        _record_success(conn, "automata_linq.create_workflow", "workflow", workflow_id, payload, response)
        return _ok(response)


def list_workflows_paginated(db_path: Path, page_size: int = 100) -> dict[str, Any]:
    page_size = max(1, min(int(page_size), 100))
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC, id LIMIT ?", (page_size,)).fetchall()
    return _ok(
        {
            "workflows": [_workflow_info(row) for row in rows],
            "pagination": {"last_evaluated_key": None, "has_more": False, "page_size": page_size},
        }
    )


def get_workflow(db_path: Path, workflow_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
    if row is None:
        return _error("workflow_not_found", "Workflow id is not stored in this dry-run world.", {"workflow_id": workflow_id})
    config = loads_json(row["workflow_config_json"]) or {}
    return _ok(
        {
            "id": row["id"],
            "name": row["name"],
            "metadata": config.get("metadata", {}),
            "workflow": config.get("workflow", {}),
            "workcell": config.get("workcell", {}),
            "options": config.get("options", {}),
            "run_instructions": config.get("run_instructions", []),
            "parameter_definitions": loads_json(row["parameter_definitions_json"]) or [],
            "scheduler_config": config.get("scheduler_config", {}),
            "published": bool(row["published"]),
            "drivers_version": config.get("drivers_version"),
            "evals_version": config.get("evals_version"),
        }
    )


def validate_workflow(
    db_path: Path,
    payload: dict[str, Any],
    validate_for_execution: bool = False,
    validate_for_infeasibility: bool = False,
) -> dict[str, Any]:
    now = _now()
    with connect(db_path) as conn:
        errors = _validate_payload(conn, payload)
        warnings: list[dict[str, Any]] = []
        response = {"is_valid": not errors, "errors": errors, "warnings": warnings}
        workflow_id = payload.get("id")
        if isinstance(workflow_id, str) and _workflow_exists(conn, workflow_id):
            validation_id = _next_id(conn, "workflow_validations", "validation")
            conn.execute(
                """
                INSERT INTO workflow_validations (
                  id, workflow_id, validate_for_execution, validate_for_infeasibility,
                  is_valid, errors_json, warnings_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    validation_id,
                    workflow_id,
                    int(validate_for_execution),
                    int(validate_for_infeasibility),
                    int(not errors),
                    dumps_json(errors),
                    dumps_json(warnings),
                    now,
                ),
            )
            _record_audit(
                conn,
                action="automata_linq.validate_workflow",
                object_type="workflow",
                object_id=workflow_id,
                request={
                    "workflow_id": workflow_id,
                    "validate_for_execution": validate_for_execution,
                    "validate_for_infeasibility": validate_for_infeasibility,
                },
                response={"ok": True, "data": response},
            )
        return _ok(response)


def plan_workflow(db_path: Path, workflow_id: str, parameter_values: list[Any] | None = None) -> dict[str, Any]:
    now = _now()
    with connect(db_path) as conn:
        workflow = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        if workflow is None:
            return _audited_error(
                conn,
                "automata_linq.plan_workflow",
                "workflow",
                workflow_id,
                {"workflow_id": workflow_id},
                "workflow_not_found",
                "Workflow id is not stored in this dry-run world.",
                {"workflow_id": workflow_id},
            )
        latest_validation = conn.execute(
            """
            SELECT * FROM workflow_validations
            WHERE workflow_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (workflow_id,),
        ).fetchone()
        if latest_validation is None or not bool(latest_validation["is_valid"]):
            return _audited_error(
                conn,
                "automata_linq.plan_workflow",
                "workflow",
                workflow_id,
                {"workflow_id": workflow_id},
                "workflow_validation_required",
                "Planning requires a latest valid validation for the stored workflow.",
                {"workflow_id": workflow_id},
            )

        config = loads_json(workflow["workflow_config_json"]) or {}
        scheduler_config = config.get("scheduler_config") if isinstance(config.get("scheduler_config"), dict) else {}
        scheduler = str(scheduler_config.get("scheduler", "linq"))
        version = str(scheduler_config.get("version", "2026.6"))
        plan_id = _next_id(conn, "plans", "plan")
        checksum = _workflow_checksum(config)
        conn.execute(
            """
            INSERT INTO plans (
              id, workflow_id, workflow_checksum, status, error, stage, stage_detail,
              result_available, status_poll_count, scheduler, scheduler_version,
              parameter_values_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_id,
                workflow_id,
                checksum,
                "PENDING",
                "",
                "queued",
                "Plan request accepted by dry-run planner.",
                0,
                0,
                scheduler,
                version,
                dumps_json(parameter_values or []),
                now,
                now,
            ),
        )
        response = _plan_status_row(
            {
                "id": plan_id,
                "status": "PENDING",
                "error": "",
                "stage": "queued",
                "stage_detail": "Plan request accepted by dry-run planner.",
                "result_available": 0,
            }
        )
        _record_success(conn, "automata_linq.plan_workflow", "plan", plan_id, {"workflow_id": workflow_id}, response)
        return _ok(response)


def get_plan_status(db_path: Path, workflow_id: str, plan_id: str) -> dict[str, Any]:
    now = _now()
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM plans WHERE id = ? AND workflow_id = ?",
            (plan_id, workflow_id),
        ).fetchone()
        if row is None:
            return _audited_error(
                conn,
                "automata_linq.get_plan_status",
                "plan",
                plan_id,
                {"workflow_id": workflow_id, "plan_id": plan_id},
                "plan_not_found",
                "Plan id is not stored for this workflow.",
                {"workflow_id": workflow_id, "plan_id": plan_id},
            )
        poll_count = int(row["status_poll_count"]) + 1
        if bool(row["result_available"]):
            response = _plan_status_row(row)
        elif poll_count >= 2:
            conn.execute(
                """
                UPDATE plans
                SET status = ?, stage = ?, stage_detail = ?, result_available = ?,
                    status_poll_count = ?, updated_at = ?
                WHERE id = ?
                """,
                ("COMPLETED", "final", "Dry-run plan completed.", 1, poll_count, now, plan_id),
            )
            _ensure_plan_result(conn, db_path, workflow_id=workflow_id, plan_id=plan_id, created_at=now)
            response = {
                "id": plan_id,
                "status": "COMPLETED",
                "error": "",
                "stage": "final",
                "stage_detail": "Dry-run plan completed.",
                "result_available": True,
            }
        else:
            conn.execute(
                """
                UPDATE plans
                SET status = ?, stage = ?, stage_detail = ?, status_poll_count = ?, updated_at = ?
                WHERE id = ?
                """,
                ("PENDING", "planning", "Dry-run planner is checking dependencies.", poll_count, now, plan_id),
            )
            response = {
                "id": plan_id,
                "status": "PENDING",
                "error": "",
                "stage": "planning",
                "stage_detail": "Dry-run planner is checking dependencies.",
                "result_available": False,
            }
        _record_success(
            conn,
            "automata_linq.get_plan_status",
            "plan",
            plan_id,
            {"workflow_id": workflow_id, "plan_id": plan_id},
            response,
        )
        return _ok(response)


def get_plan_result(db_path: Path, workflow_id: str, plan_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        plan = conn.execute(
            "SELECT * FROM plans WHERE id = ? AND workflow_id = ?",
            (plan_id, workflow_id),
        ).fetchone()
        if plan is None:
            return _audited_error(
                conn,
                "automata_linq.get_plan_result",
                "plan",
                plan_id,
                {"workflow_id": workflow_id, "plan_id": plan_id},
                "plan_not_found",
                "Plan id is not stored for this workflow.",
                {"workflow_id": workflow_id, "plan_id": plan_id},
            )
        if not bool(plan["result_available"]):
            return _audited_error(
                conn,
                "automata_linq.get_plan_result",
                "plan",
                plan_id,
                {"workflow_id": workflow_id, "plan_id": plan_id},
                "plan_result_unavailable",
                "Plan result is not available yet; poll get_plan_status until result_available is true.",
                {"workflow_id": workflow_id, "plan_id": plan_id},
            )
        result = conn.execute("SELECT * FROM plan_results WHERE plan_id = ?", (plan_id,)).fetchone()
        if result is None:
            _ensure_plan_result(conn, db_path, workflow_id=workflow_id, plan_id=plan_id, created_at=_now())
            result = conn.execute("SELECT * FROM plan_results WHERE plan_id = ?", (plan_id,)).fetchone()
        response = {
            "plan": loads_json(result["plan_json"]) or {},
            "metrics": loads_json(result["metrics_json"]) or {},
            "locations": loads_json(result["locations_json"]) or {},
        }
        insert_event(
            conn,
            event_type="plan_result.fetched",
            object_type="plan",
            object_id=plan_id,
            payload={"workflow_id": workflow_id, "plan_id": plan_id},
            created_at=_now(),
        )
        _record_success(
            conn,
            "automata_linq.get_plan_result",
            "plan",
            plan_id,
            {"workflow_id": workflow_id, "plan_id": plan_id},
            response,
        )
        return _ok(response)


def reject_live_action(db_path: Path, operation: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        response = _error(
            "automata_linq_live_execution_not_allowed",
            "This dry-run world does not execute live Automata LINQ workcell actions.",
            {"operation": operation},
        )
        _record_audit(
            conn,
            action="boundary.live_action_rejected",
            object_type="boundary",
            object_id=operation,
            request={"operation": operation, "allowed_next_steps": ALLOWED_NEXT_STEPS},
            response=response,
        )
        return response


def _validate_payload(conn, payload: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    workflow = payload.get("workflow") if isinstance(payload.get("workflow"), dict) else {}
    steps = workflow.get("steps") if isinstance(workflow.get("steps"), list) else []
    if not steps:
        errors.append(_validation_issue("empty_workflow", ["workflow", "steps"], "Workflow must contain at least one step."))

    step_ids = {str(step.get("id")) for step in steps if isinstance(step, dict) and step.get("id")}
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(_validation_issue("invalid_step", ["workflow", "steps", idx], "Step must be an object."))
            continue
        dependencies = step.get("depends_on", [])
        if dependencies is None:
            dependencies = []
        if not isinstance(dependencies, list):
            errors.append(_validation_issue("invalid_dependencies", ["workflow", "steps", idx, "depends_on"], "depends_on must be a list."))
        else:
            for dependency in dependencies:
                if str(dependency) not in step_ids:
                    errors.append(
                        _validation_issue(
                            "unknown_dependency",
                            ["workflow", "steps", idx, "depends_on"],
                            f"Dependency {dependency} does not reference an existing step.",
                        )
                    )

    scheduler_config = payload.get("scheduler_config") if isinstance(payload.get("scheduler_config"), dict) else {}
    scheduler = str(scheduler_config.get("scheduler", ""))
    version = str(scheduler_config.get("version", ""))
    if not _scheduler_version_exists(conn, scheduler, version):
        errors.append(
            _validation_issue(
                "scheduler_version_not_found",
                ["scheduler_config"],
                "Selected scheduler/version is not available.",
            )
        )

    available_drivers = _driver_names(conn, scheduler, version)
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        driver = step.get("driver")
        if driver is None:
            errors.append(_validation_issue("missing_driver", ["workflow", "steps", idx, "driver"], "Step must reference a driver."))
        elif str(driver) not in available_drivers:
            errors.append(
                _validation_issue(
                    "driver_not_found",
                    ["workflow", "steps", idx, "driver"],
                    f"Driver {driver} is not available for {scheduler}/{version}.",
                )
            )

    workcell = payload.get("workcell") if isinstance(payload.get("workcell"), dict) else {}
    workcell_id = str(workcell.get("id", ""))
    if not workcell_id or conn.execute("SELECT 1 FROM workcells WHERE id = ?", (workcell_id,)).fetchone() is None:
        errors.append(_validation_issue("workcell_not_found", ["workcell", "id"], "Workcell id is not available."))

    parameter_definitions = payload.get("parameter_definitions", [])
    required_parameters = [
        str(definition.get("name"))
        for definition in parameter_definitions
        if isinstance(definition, dict) and definition.get("required") is True and definition.get("name")
    ]
    values = {
        str(value.get("name")): value.get("value")
        for value in payload.get("parameter_values", [])
        if isinstance(value, dict) and value.get("name")
    }
    for name in required_parameters:
        if name not in values:
            errors.append(_validation_issue("missing_parameter_value", ["parameter_values", name], f"Missing value for {name}."))
    return errors


def _ensure_plan_result(conn, db_path: Path, *, workflow_id: str, plan_id: str, created_at: str) -> None:
    existing = conn.execute("SELECT 1 FROM plan_results WHERE plan_id = ?", (plan_id,)).fetchone()
    if existing is not None:
        return
    workflow = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
    config = loads_json(workflow["workflow_config_json"]) or {}
    steps = config.get("workflow", {}).get("steps", []) if isinstance(config.get("workflow"), dict) else []
    workcell_id = str(config.get("workcell", {}).get("id", "")) if isinstance(config.get("workcell"), dict) else ""
    plan = {"workflow_id": workflow_id, "plan_id": plan_id, "tasks": steps}
    metrics = {"step_count": len(steps), "synthetic": True}
    locations = {"workcell_id": workcell_id}
    result_id = f"plan_result_{plan_id}"
    conn.execute(
        """
        INSERT INTO plan_results (id, plan_id, plan_json, metrics_json, locations_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (result_id, plan_id, dumps_json(plan), dumps_json(metrics), dumps_json(locations), created_at),
    )
    artifact = {
        "schema_version": "api_gym.automata_linq_plan_result.v0",
        "workflow_id": workflow_id,
        "plan_id": plan_id,
        "result": {"plan": plan, "metrics": metrics, "locations": locations},
    }
    artifact_path = db_path.parent / "artifacts" / "plan_results" / f"{plan_id}.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _workflow_config_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "metadata": payload.get("metadata", {}),
        "workflow": payload.get("workflow", {}),
        "workcell": payload.get("workcell", {}),
        "options": payload.get("options", {}),
        "run_instructions": payload.get("run_instructions", []),
        "scheduler_config": payload.get("scheduler_config", {}),
        "parameter_definitions": payload.get("parameter_definitions", []),
        "drivers_version": payload.get("drivers_version"),
        "evals_version": payload.get("evals_version"),
    }


def _workflow_info_from_payload(workflow_id: str, payload: dict[str, Any], timestamp: str) -> dict[str, Any]:
    return {
        "id": workflow_id,
        "name": str(payload.get("name", "Untitled dry-run workflow")),
        "author": "api-gym-agent",
        "creator_username": "api-gym-agent",
        "version": "1.0.0",
        "workflow_type": "dry_run",
        "published": False,
        "created_at": timestamp,
        "updated_at": timestamp,
        "published_at": None,
        "parameter_definitions": payload.get("parameter_definitions", []),
        "valid_batch_data": {},
        "synced_plan_id": None,
    }


def _workflow_info(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "author": row["author"],
        "creator_username": row["creator_username"],
        "version": row["version"],
        "workflow_type": row["workflow_type"],
        "published": bool(row["published"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "published_at": row["published_at"],
        "parameter_definitions": loads_json(row["parameter_definitions_json"]) or [],
        "valid_batch_data": loads_json(row["valid_batch_data_json"]) or {},
        "synced_plan_id": row["synced_plan_id"],
    }


def _plan_status_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "status": row["status"],
        "error": row["error"],
        "stage": row["stage"],
        "stage_detail": row["stage_detail"],
        "result_available": bool(row["result_available"]),
    }


def _scheduler_version_exists(conn, scheduler: str, version: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM scheduler_versions WHERE scheduler = ? AND version = ?",
        (scheduler, version),
    ).fetchone() is not None


def _driver_names(conn, scheduler: str, version: str) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM drivers WHERE scheduler = ? AND scheduler_version = ?",
            (scheduler, version),
        )
    }


def _workflow_exists(conn, workflow_id: str) -> bool:
    return conn.execute("SELECT 1 FROM workflows WHERE id = ?", (workflow_id,)).fetchone() is not None


def _workflow_checksum(config: dict[str, Any]) -> str:
    return hashlib.sha256(dumps_json(config).encode("utf-8")).hexdigest()


def _next_id(conn, table: str, prefix: str) -> str:
    count = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]) + 1
    return f"{prefix}_{count:04d}"


def _validation_issue(issue_type: str, loc: list[Any], message: str) -> dict[str, Any]:
    return {"level": "error", "type": issue_type, "loc": loc, "msg": message}


def _record_success(
    conn,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    response: dict[str, Any],
) -> None:
    created_at = _now()
    insert_event(conn, event_type=f"{action}.succeeded", object_type=object_type, object_id=object_id, payload=response, created_at=created_at)
    _record_audit(
        conn,
        action=action,
        object_type=object_type,
        object_id=object_id,
        request=request,
        response={"ok": True, "data": response},
        created_at=created_at,
    )


def _audited_error(
    conn,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    code: str,
    message: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    response = _error(code, message, details)
    _record_audit(conn, action=action, object_type=object_type, object_id=object_id, request=request, response=response)
    return response


def _record_audit(
    conn,
    *,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    response: dict[str, Any],
    created_at: str | None = None,
) -> None:
    insert_audit(
        conn,
        actor=AGENT_ACTOR,
        action=action,
        object_type=object_type,
        object_id=object_id,
        request=request,
        response=response,
        created_at=created_at or _now(),
    )


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
