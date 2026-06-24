from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from api_gym.worlds.automata_linq_workflow_planning_v0.sampler import sample_episode
from api_gym.worlds.automata_linq_workflow_planning_v0.services import (
    create_workflow,
    export_run_logs,
    get_all_drivers,
    get_api_version,
    get_device_status,
    get_organizations,
    get_plan_result,
    get_plan_status,
    get_run_histories,
    get_scheduler_versions,
    get_workcells,
    get_workflow,
    list_workflows_paginated,
    plan_workflow,
    reject_live_action,
    validate_workflow,
)


def test_read_surfaces_return_source_shaped_live_boundary_data_without_dereferencing_logs(tmp_path: Path) -> None:
    episode = sample_episode(scenario="live_action_boundary", seed=101, out_dir=tmp_path / "run")

    api_version = get_api_version(episode.db_path)
    assert api_version == {"ok": True, "data": {"version": "2026-06-22"}}

    organizations = get_organizations(episode.db_path)
    assert organizations["ok"] is True
    organization = organizations["data"]["organizations"][0]
    assert set(organization) == {"externalID", "id", "logo", "name", "slug", "workspace"}
    assert organization["name"] == "Example Automation Lab"
    workspace_id = organization["workspace"]

    scheduler_versions = get_scheduler_versions(episode.db_path)
    assert scheduler_versions == {"ok": True, "data": {"linq": ["2026.6", "2026.5"]}}

    drivers = get_all_drivers(episode.db_path, scheduler="linq", version="2026.6")
    assert drivers["ok"] is True
    assert drivers["data"] == [
        {
            "name": "plate_mover",
            "version": "1.0.0",
            "configuration": {"deck": "standard"},
            "actions": {"move_plate": {"parameters": ["source", "target"]}},
            "protocols": {"plate_transfer": {"compatible": True}},
            "metadata": {"source_shape": "response_case:getAllDrivers:success"},
        }
    ]

    workcells = get_workcells(episode.db_path, workspace_id=workspace_id)
    assert workcells["ok"] is True
    assert set(workcells["data"]) == {"workcells"}
    workcell = workcells["data"]["workcells"][0]
    assert workcell["status"] == "ready"
    assert workcell["mode"] == "active"

    device_id = _first_value(episode.db_path, "SELECT id FROM devices")
    device = get_device_status(episode.db_path, device_id=device_id)
    assert device["ok"] is True
    assert device["data"]["id"] == device_id
    assert device["data"]["online"] is True
    assert device["data"]["state"] == {"status": "ready", "details": "Ready for dry-run inspection."}
    assert device["data"]["error"]["available_actions"] == ["respond_to_error"]

    histories = get_run_histories(episode.db_path, device_id=device_id, count=10)
    assert histories["ok"] is True
    assert set(histories["data"]) == {"list", "next_cursor"}
    assert histories["data"]["next_cursor"] is None
    history = histories["data"]["list"][0]
    assert history["device_id"] == device_id
    assert history["outcome"] == "failed"
    assert history["tags"] == ["dry-run-boundary", "historical"]

    log_export = export_run_logs(episode.db_path, run_id=history["id"])
    assert log_export["ok"] is True
    assert log_export["data"]["download_url"].startswith("https://downloads.example.invalid/automata/")
    assert _first_value(
        episode.db_path,
        "SELECT dereferenced FROM log_exports WHERE run_history_id = ?",
        (history["id"],),
    ) == 0


def test_validate_workflow_reports_structured_invalid_cases_then_valid_repair(tmp_path: Path) -> None:
    episode = sample_episode(scenario="repair_invalid_workflow_plan", seed=102, out_dir=tmp_path / "run")
    workcell_id = _first_value(episode.db_path, "SELECT id FROM workcells")

    no_steps = validate_workflow(episode.db_path, _workflow_payload(workcell_id, steps=[]))
    assert no_steps["ok"] is True
    assert no_steps["data"]["is_valid"] is False
    assert _error_types(no_steps) == {"empty_workflow"}

    missing_driver = validate_workflow(
        episode.db_path,
        _workflow_payload(workcell_id, steps=[{"id": "move_plate"}]),
        validate_for_execution=True,
        validate_for_infeasibility=True,
    )
    assert missing_driver["ok"] is True
    assert missing_driver["data"]["is_valid"] is False
    assert "missing_driver" in _error_types(missing_driver)

    repaired = validate_workflow(
        episode.db_path,
        _workflow_payload(workcell_id, steps=[{"id": "move_plate", "driver": "plate_mover"}]),
        validate_for_execution=True,
        validate_for_infeasibility=True,
    )
    assert repaired["ok"] is True
    assert repaired["data"] == {"is_valid": True, "errors": [], "warnings": []}


def test_create_workflow_stores_provider_shape_and_get_list_return_it(tmp_path: Path) -> None:
    episode = sample_episode(scenario="repair_invalid_workflow_plan", seed=103, out_dir=tmp_path / "run")
    workcell_id = _first_value(episode.db_path, "SELECT id FROM workcells")
    payload = _workflow_payload(workcell_id, steps=[{"id": "move_plate", "driver": "plate_mover"}])

    created = create_workflow(episode.db_path, payload)
    assert created["ok"] is True
    workflow_id = created["data"]["id"]
    assert created["data"]["name"] == payload["name"]
    assert created["data"]["author"] == "api-gym-agent"
    assert created["data"]["published"] is False
    assert created["data"]["synced_plan_id"] is None

    fetched = get_workflow(episode.db_path, workflow_id=workflow_id)
    assert fetched["ok"] is True
    assert fetched["data"]["name"] == payload["name"]
    assert fetched["data"]["metadata"] == payload["metadata"]
    assert fetched["data"]["workflow"] == payload["workflow"]
    assert fetched["data"]["workcell"] == payload["workcell"]
    assert fetched["data"]["scheduler_config"] == payload["scheduler_config"]
    assert fetched["data"]["published"] is False

    listed = list_workflows_paginated(episode.db_path, page_size=100)
    assert listed["ok"] is True
    assert any(workflow["id"] == workflow_id for workflow in listed["data"]["workflows"])
    assert listed["data"]["pagination"] == {
        "last_evaluated_key": None,
        "has_more": False,
        "page_size": 100,
    }


def test_plan_workflow_requires_latest_valid_validation_then_progresses_to_result(tmp_path: Path) -> None:
    episode = sample_episode(scenario="repair_invalid_workflow_plan", seed=104, out_dir=tmp_path / "run")
    workcell_id = _first_value(episode.db_path, "SELECT id FROM workcells")
    payload = _workflow_payload(workcell_id, steps=[{"id": "move_plate", "driver": "plate_mover"}])
    workflow_id = create_workflow(episode.db_path, payload)["data"]["id"]

    missing_validation = plan_workflow(episode.db_path, workflow_id=workflow_id)
    assert missing_validation["ok"] is False
    assert missing_validation["error"]["code"] == "workflow_validation_required"

    workflow_payload = get_workflow(episode.db_path, workflow_id=workflow_id)["data"]
    validated = validate_workflow(
        episode.db_path,
        {"id": workflow_id, **workflow_payload},
        validate_for_execution=True,
        validate_for_infeasibility=True,
    )
    assert validated["data"]["is_valid"] is True

    planned = plan_workflow(episode.db_path, workflow_id=workflow_id, parameter_values=[])
    assert planned["ok"] is True
    plan_id = planned["data"]["id"]
    assert planned["data"]["status"] == "PENDING"
    assert planned["data"]["result_available"] is False

    unavailable = get_plan_result(episode.db_path, workflow_id=workflow_id, plan_id=plan_id)
    assert unavailable["ok"] is False
    assert unavailable["error"]["code"] == "plan_result_unavailable"

    latest_status: dict[str, Any] | None = None
    for _ in range(4):
        status = get_plan_status(episode.db_path, workflow_id=workflow_id, plan_id=plan_id)
        assert status["ok"] is True
        latest_status = status["data"]
        if latest_status["result_available"]:
            break

    assert latest_status is not None
    assert latest_status["status"] == "COMPLETED"
    assert latest_status["result_available"] is True
    assert _first_value(episode.db_path, "SELECT COUNT(*) FROM plan_results WHERE plan_id = ?", (plan_id,)) == 1

    artifact_path = episode.run_dir / "artifacts" / "plan_results" / f"{plan_id}.json"
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["plan_id"] == plan_id
    assert set(artifact["result"]) == {"plan", "metrics", "locations"}

    result = get_plan_result(episode.db_path, workflow_id=workflow_id, plan_id=plan_id)
    assert result["ok"] is True
    assert set(result["data"]) == {"plan", "metrics", "locations"}
    assert result["data"]["plan"]["workflow_id"] == workflow_id
    assert result["data"]["metrics"]["step_count"] == 1
    assert result["data"]["locations"]["workcell_id"] == workcell_id
    assert _first_value(
        episode.db_path,
        "SELECT COUNT(*) FROM events WHERE event_type = ? AND object_id = ?",
        ("plan_result.fetched", plan_id),
    ) == 1


def test_reject_live_action_does_not_mutate_workcell_or_device_status(tmp_path: Path) -> None:
    episode = sample_episode(scenario="live_action_boundary", seed=105, out_dir=tmp_path / "run")
    before_workcell = _first_row(episode.db_path, "SELECT status, mode FROM workcells")
    before_device = _first_row(episode.db_path, "SELECT online, state_status, state_details, error_json FROM devices")

    rejected = reject_live_action(episode.db_path, operation="start_workflow")

    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "automata_linq_live_execution_not_allowed"
    assert rejected["error"]["details"] == {"operation": "start_workflow"}
    assert _first_row(episode.db_path, "SELECT status, mode FROM workcells") == before_workcell
    assert _first_row(episode.db_path, "SELECT online, state_status, state_details, error_json FROM devices") == before_device
    assert _first_value(
        episode.db_path,
        "SELECT COUNT(*) FROM audit_log WHERE action = ?",
        ("boundary.live_action_rejected",),
    ) == 1


def _workflow_payload(workcell_id: str, *, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": "Dry-run plate transfer",
        "metadata": {"purpose": "service-test"},
        "workflow": {"steps": steps},
        "workcell": {"id": workcell_id},
        "options": {"dry_run": True},
        "scheduler_config": {"scheduler": "linq", "version": "2026.6"},
        "parameter_definitions": [],
        "run_instructions": [],
        "drivers_version": "2026.6",
        "evals_version": "2026.6",
    }


def _error_types(response: dict[str, Any]) -> set[str]:
    return {error["type"] for error in response["data"]["errors"]}


def _first_value(db_path: Path, query: str, params: tuple[Any, ...] = ()) -> Any:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(query, params).fetchone()[0]


def _first_row(db_path: Path, query: str) -> tuple[Any, ...]:
    with sqlite3.connect(db_path) as conn:
        return tuple(conn.execute(query).fetchone())
