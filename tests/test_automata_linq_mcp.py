from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from api_gym.agent_harness import create_mcp_handler
from api_gym.cli import app


EXPECTED_TOOL_NAMES = {
    "automata_linq_get_api_version",
    "automata_linq_get_organizations",
    "automata_linq_get_scheduler_versions",
    "automata_linq_get_all_drivers",
    "automata_linq_get_workcells",
    "automata_linq_get_device_status",
    "automata_linq_get_run_histories",
    "automata_linq_export_run_logs",
    "automata_linq_create_workflow",
    "automata_linq_list_workflows",
    "automata_linq_get_workflow",
    "automata_linq_validate_workflow",
    "automata_linq_plan_workflow",
    "automata_linq_get_plan_status",
    "automata_linq_get_plan_result",
    "automata_linq_reject_live_action",
}


def test_automata_linq_session_check_tools_mcp_flow_and_finalize(tmp_path: Path) -> None:
    run_dir = tmp_path / "session"
    runner = CliRunner()

    create = runner.invoke(
        app,
        [
            "session",
            "create",
            "--world",
            "automata_linq_workflow_planning_v0",
            "--scenario",
            "repair_invalid_workflow_plan",
            "--seed",
            "401",
            "--out",
            str(run_dir),
            "--json",
        ],
    )
    assert create.exit_code == 0, create.output
    manifest = json.loads(create.output)
    assert manifest["expected_tools"] == sorted(EXPECTED_TOOL_NAMES)
    assert manifest["http"]["available"] is True

    check = runner.invoke(app, ["session", "check-tools", "--run", str(run_dir)])
    assert check.exit_code == 0, check.output
    assert json.loads(check.output)["listed_tools"] == sorted(EXPECTED_TOOL_NAMES)

    handler = create_mcp_handler(run_dir)
    listed = handler.handle_message({"jsonrpc": "2.0", "id": "list", "method": "tools/list"})
    assert listed is not None
    assert {tool["name"] for tool in listed["result"]["tools"]} == EXPECTED_TOOL_NAMES

    organizations = _mcp_call(handler, "automata_linq_get_organizations", {})
    workspace_id = organizations["data"]["organizations"][0]["workspace"]
    scheduler_versions = _mcp_call(handler, "automata_linq_get_scheduler_versions", {})
    assert scheduler_versions["data"]["linq"][0] == "2026.6"
    drivers = _mcp_call(handler, "automata_linq_get_all_drivers", {"scheduler": "linq", "version": "2026.6"})
    assert drivers["data"][0]["name"] == "plate_mover"
    workcells = _mcp_call(handler, "automata_linq_get_workcells", {"workspace_id": workspace_id})
    workcell_id = workcells["data"]["workcells"][0]["id"]
    seeded_workflows = _mcp_call(handler, "automata_linq_list_workflows", {})
    seeded_workflow_id = seeded_workflows["data"]["workflows"][0]["id"]

    created = _mcp_call(handler, "automata_linq_create_workflow", _workflow_payload(workcell_id, seeded_workflow_id))
    workflow_id = created["data"]["id"]
    fetched = _mcp_call(handler, "automata_linq_get_workflow", {"workflow_id": workflow_id})
    validated = _mcp_call(
        handler,
        "automata_linq_validate_workflow",
        {
            "id": workflow_id,
            **fetched["data"],
            "validate_for_execution": True,
            "validate_for_infeasibility": True,
        },
    )
    assert validated["data"]["is_valid"] is True

    planned = _mcp_call(handler, "automata_linq_plan_workflow", {"workflow_id": workflow_id, "parameter_values": []})
    plan_id = planned["data"]["id"]
    unavailable = _mcp_call(
        handler,
        "automata_linq_get_plan_result",
        {"workflow_id": workflow_id, "plan_id": plan_id},
        expect_error=True,
    )
    assert unavailable["error"]["code"] == "plan_result_unavailable"

    latest_status: dict[str, Any] | None = None
    for _ in range(3):
        status = _mcp_call(handler, "automata_linq_get_plan_status", {"workflow_id": workflow_id, "plan_id": plan_id})
        latest_status = status["data"]
        if latest_status["result_available"]:
            break
    assert latest_status is not None
    assert latest_status["status"] == "COMPLETED"

    result = _mcp_call(handler, "automata_linq_get_plan_result", {"workflow_id": workflow_id, "plan_id": plan_id})
    assert result["data"]["plan"]["workflow_id"] == workflow_id

    finalized = runner.invoke(app, ["session", "finalize", "--run", str(run_dir), "--json"])
    assert finalized.exit_code == 0, finalized.output
    payload = json.loads(finalized.output)
    assert payload["ok"] is True
    assert payload["verifier_result"]["ok"] is True


def _mcp_call(handler: Any, name: str, arguments: dict[str, Any], *, expect_error: bool = False) -> dict[str, Any]:
    response = handler.handle_message(
        {
            "jsonrpc": "2.0",
            "id": name,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert response is not None
    result = response["result"]
    assert result["isError"] is expect_error
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result["structuredContent"]


def _workflow_payload(workcell_id: str, repaired_from_workflow_id: str) -> dict[str, Any]:
    return {
        "name": "MCP dry-run plate transfer",
        "metadata": {"purpose": "mcp-test", "repaired_from_workflow_id": repaired_from_workflow_id},
        "workflow": {"steps": [{"id": "move_plate", "driver": "plate_mover"}]},
        "workcell": {"id": workcell_id},
        "options": {"dry_run": True},
        "scheduler_config": {"scheduler": "linq", "version": "2026.6"},
        "parameter_definitions": [],
        "run_instructions": [],
        "drivers_version": "2026.6",
        "evals_version": "2026.6",
    }
