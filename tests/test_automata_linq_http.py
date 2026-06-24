from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api_gym.server.app import create_app
from api_gym.worlds.automata_linq_workflow_planning_v0.sampler import sample_episode


FORBIDDEN_HTTP_ROUTES = [
    ("publish_workflow", "/v3/workflow/{workflow_id}/publish"),
    ("deploy_workflow", "/v3/workflow/{workflow_id}/deploy"),
    ("start_workflow", "/v3/workflow/{workflow_id}/start"),
    ("pause_workflow", "/v3/workflow/{workflow_id}/pause"),
    ("resume_workflow", "/v3/workflow/{workflow_id}/resume"),
    ("stop_workflow", "/v3/workflow/{workflow_id}/stop"),
    ("reset_workflow", "/v3/workflow/{workflow_id}/reset"),
    ("respond_to_error", "/v1/devices/{device_id}/errors/device_error_test/respond"),
    ("restart_hub", "/v1/workspace/{workspace_id}/hubs/hub_test/restart"),
    ("mutate_transport_config", "/v1/workspace/{workspace_id}/transport-configs/transport_test"),
    ("rotate_credentials", "/v1/workspace/{workspace_id}/credentials/credential_test/rotate"),
]


def test_original_shaped_http_create_validate_plan_status_result_and_trace(tmp_path: Path) -> None:
    episode = sample_episode(scenario="repair_invalid_workflow_plan", seed=301, out_dir=tmp_path / "run")
    client = TestClient(create_app(episode.run_dir))

    assert client.get("/version").json() == {"version": "2026-06-22"}

    organizations = client.get("/v2/user/organizations").json()
    workspace_id = organizations["organizations"][0]["workspace"]
    assert client.get("/v3/workflow/scheduler_versions").json() == {"linq": ["2026.6", "2026.5"]}
    assert client.get("/v3/driver/linq/2026.6").json()[0]["name"] == "plate_mover"
    workcell_id = client.get(f"/v1/workspace/{workspace_id}/workcells").json()["workcells"][0]["id"]

    created = client.post("/v3/workflow", json=_workflow_payload(workcell_id)).json()
    workflow_id = created["id"]
    assert created["name"] == "HTTP dry-run plate transfer"

    fetched = client.get(f"/v3/workflow/{workflow_id}").json()
    assert fetched["workflow"] == {"steps": [{"id": "move_plate", "driver": "plate_mover"}]}

    validated = client.post(
        "/v3/workflow/validate?validate_for_execution=true&validate_for_infeasibility=true",
        json={"id": workflow_id, **fetched},
    ).json()
    assert validated == {"is_valid": True, "errors": [], "warnings": []}

    planned_response = client.post(
        f"/v3/workflow/plan?workflow_id={workflow_id}",
        json={"parameter_values": []},
    )
    assert planned_response.status_code == 200
    planned = planned_response.json()
    plan_id = planned["id"]
    assert planned["result_available"] is False

    unavailable = client.get(f"/v3/workflow/{workflow_id}/plan/{plan_id}/result")
    assert unavailable.status_code == 404
    assert unavailable.json()["code"] == "plan_result_unavailable"

    latest_status: dict[str, Any] | None = None
    for _ in range(3):
        status_response = client.get(f"/v3/workflow/{workflow_id}/plan/{plan_id}/status")
        assert status_response.status_code == 200
        latest_status = status_response.json()
        if latest_status["result_available"]:
            break
    assert latest_status is not None
    assert latest_status["status"] == "COMPLETED"

    result = client.get(f"/v3/workflow/{workflow_id}/plan/{plan_id}/result")
    assert result.status_code == 200
    assert result.json()["plan"]["workflow_id"] == workflow_id
    assert result.json()["metrics"]["step_count"] == 1

    rows = [
        json.loads(line)
        for line in (episode.run_dir / "traces" / "http_requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["path"] == "/version"
    assert rows[0]["ok"] is True
    assert any(
        row["path"] == f"/v3/workflow/{workflow_id}/plan/{plan_id}/result"
        and row["status_code"] == 404
        and row["error"]["code"] == "plan_result_unavailable"
        for row in rows
    )
    validate_row = next(row for row in rows if row["path"] == "/v3/workflow/validate")
    assert validate_row["query_params"] == {
        "validate_for_execution": "true",
        "validate_for_infeasibility": "true",
    }


def test_original_shaped_http_live_boundary_rejects_without_mutating_state(tmp_path: Path) -> None:
    episode = sample_episode(scenario="live_action_boundary", seed=302, out_dir=tmp_path / "run")
    client = TestClient(create_app(episode.run_dir))
    workflow_id = _first_value(episode.db_path, "SELECT id FROM workflows")
    before_workcell = _first_row(episode.db_path, "SELECT status, mode FROM workcells")
    before_device = _first_row(episode.db_path, "SELECT online, state_status, state_details, error_json FROM devices")

    response = client.post(f"/v3/workflow/{workflow_id}/start")

    assert response.status_code == 200
    assert response.json()["code"] == "automata_linq_live_execution_not_allowed"
    assert response.json()["details"]["operation"] == "start_workflow"
    assert _first_row(episode.db_path, "SELECT status, mode FROM workcells") == before_workcell
    assert _first_row(episode.db_path, "SELECT online, state_status, state_details, error_json FROM devices") == before_device
    assert _first_value(
        episode.db_path,
        "SELECT COUNT(*) FROM audit_log WHERE action = ?",
        ("boundary.live_action_rejected",),
    ) == 1


def test_original_shaped_http_boundary_routes_are_structured(tmp_path: Path) -> None:
    episode = sample_episode(scenario="live_action_boundary", seed=303, out_dir=tmp_path / "run")
    client = TestClient(create_app(episode.run_dir))
    workflow_id = _first_value(episode.db_path, "SELECT id FROM workflows")
    workspace_id = _first_value(episode.db_path, "SELECT workspace_id FROM workcells")
    device_id = _first_value(episode.db_path, "SELECT id FROM devices")
    before_workcell = _first_row(episode.db_path, "SELECT status, mode FROM workcells")
    before_device = _first_row(episode.db_path, "SELECT online, state_status, state_details, error_json FROM devices")

    for operation, route_template in FORBIDDEN_HTTP_ROUTES:
        route = route_template.format(workflow_id=workflow_id, workspace_id=workspace_id, device_id=device_id)
        response = client.post(route)
        assert response.status_code == 200
        assert response.json()["code"] == "automata_linq_live_execution_not_allowed"
        assert response.json()["details"]["operation"] == operation

    assert _first_row(episode.db_path, "SELECT status, mode FROM workcells") == before_workcell
    assert _first_row(episode.db_path, "SELECT online, state_status, state_details, error_json FROM devices") == before_device
    assert _first_value(
        episode.db_path,
        "SELECT COUNT(*) FROM audit_log WHERE action = ?",
        ("boundary.live_action_rejected",),
    ) == len(FORBIDDEN_HTTP_ROUTES)


def _workflow_payload(workcell_id: str) -> dict[str, Any]:
    return {
        "name": "HTTP dry-run plate transfer",
        "metadata": {"purpose": "http-test"},
        "workflow": {"steps": [{"id": "move_plate", "driver": "plate_mover"}]},
        "workcell": {"id": workcell_id},
        "options": {"dry_run": True},
        "scheduler_config": {"scheduler": "linq", "version": "2026.6"},
        "parameter_definitions": [],
        "run_instructions": [],
        "drivers_version": "2026.6",
        "evals_version": "2026.6",
    }


def _first_value(db_path: Path, query: str, params: tuple[Any, ...] = ()) -> Any:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(query, params).fetchone()[0]


def _first_row(db_path: Path, query: str) -> tuple[Any, ...]:
    with sqlite3.connect(db_path) as conn:
        return tuple(conn.execute(query).fetchone())
