from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from api_gym.agent_harness import create_mcp_handler
from api_gym.cli import app
from api_gym.session import check_session_tools, create_world_session, finalize_world_session


REPO_ROOT = Path(__file__).resolve().parents[1]
WORLD = "adaptyv_foundry_dryrun_v0"
WORLD_ID = "adaptyv-foundry-dryrun-v0"
SCENARIO = "partial_results_not_final"
MCP_SERVER_NAME = "api-gym-adaptyv-foundry-dryrun-v0"
AGENT_VISIBLE_FORBIDDEN_HIDDEN_TOKENS = {
    "hidden/",
    "result_arrival_schedule.json",
    "quote_schedule.json",
    "fault_schedule.json",
    "measured_result_replay.json",
    "oracle_plan.json",
    "known_bad_plans.json",
    "verifier_expectations.json",
}


def test_create_world_session_writes_manifest_task_package_and_mcp_metadata(tmp_path: Path) -> None:
    manifest = create_world_session(
        world=WORLD,
        scenario=SCENARIO,
        seed=101,
        out_dir=tmp_path / "adaptyv-session",
    )
    run_dir = Path(manifest["run_dir"])
    expected_tools = sorted(_spec_tools())

    assert manifest["schema_version"] == "api_gym.world_session.v0"
    assert manifest["world"] == WORLD
    assert manifest["world_id"] == WORLD_ID
    assert manifest["scenario"] == SCENARIO
    assert manifest["mode"] == "dry_run"
    assert manifest["expected_tools"] == expected_tools
    assert manifest["task"]["scenario"] == SCENARIO
    assert manifest["task"]["scientific_outcome_source"] == "public_replay"
    assert manifest["task_package"] == str(run_dir / "agent_task.json")
    assert manifest["mcp"] == {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "command": "api-gym",
                "args": ["mcp", "--run", str(run_dir)],
            }
        }
    }
    assert manifest["commands"]["check_tools"] == ["api-gym", "session", "check-tools", "--run", str(run_dir)]
    assert manifest["commands"]["finalize"] == ["api-gym", "session", "finalize", "--run", str(run_dir)]
    assert manifest["artifacts"]["state_db"] == str(run_dir / "state.sqlite")
    assert manifest["artifacts"]["run_export"] == str(run_dir / "run_export.json")

    written_manifest = _read_json(run_dir / "session_manifest.json")
    agent_task = _read_json(run_dir / "agent_task.json")
    assert written_manifest == manifest
    assert agent_task["recommended_mcp_config"] == manifest["mcp"]
    visible_handoff_text = json.dumps(
        [
            manifest,
            agent_task,
            _read_json(run_dir / "task.json"),
        ],
        sort_keys=True,
    )
    for token in AGENT_VISIBLE_FORBIDDEN_HIDDEN_TOKENS:
        assert token not in visible_handoff_text
    for name in ("run.json", "task.json", "agent_task.json", "session_manifest.json", "state.sqlite"):
        assert (run_dir / name).exists()


def test_adaptyv_session_manifest_marks_http_unavailable(tmp_path: Path) -> None:
    manifest = create_world_session(
        world=WORLD,
        scenario=SCENARIO,
        seed=102,
        out_dir=tmp_path / "adaptyv-session",
    )

    assert manifest["http"] == {
        "available": False,
        "reason": f"World '{WORLD}' does not expose an HTTP app.",
    }


def test_check_session_tools_and_cli_list_exact_adaptyv_spec_tools(tmp_path: Path) -> None:
    run_dir = tmp_path / "adaptyv-session"
    expected_tools = sorted(_spec_tools())
    create_world_session(world=WORLD, scenario=SCENARIO, seed=103, out_dir=run_dir)

    direct = check_session_tools(run_dir)

    assert direct == {
        "ok": True,
        "world": WORLD,
        "expected_tools": expected_tools,
        "listed_tools": expected_tools,
        "missing_tools": [],
        "unexpected_tools": [],
    }

    cli = CliRunner().invoke(app, ["session", "check-tools", "--run", str(run_dir)])

    assert cli.exit_code == 0, cli.output
    assert json.loads(cli.output) == direct


def test_finalize_before_agent_action_writes_run_export_with_verifier_failure(tmp_path: Path) -> None:
    manifest = create_world_session(
        world=WORLD,
        scenario=SCENARIO,
        seed=104,
        out_dir=tmp_path / "adaptyv-session",
    )
    run_dir = Path(manifest["run_dir"])

    finalization = finalize_world_session(run_dir)
    run_export = _read_json(run_dir / "run_export.json")
    written_finalization = _read_json(run_dir / "session_finalization.json")

    assert finalization["ok"] is False
    assert finalization["verifier_result"]["ok"] is False
    assert finalization["verifier_result"]["failure_code"] == "MISSING_FINAL_CAMPAIGN_DECISION"
    assert finalization["export_path"] == str(run_dir / "run_export.json")
    assert written_finalization == finalization
    assert run_export["world"] == WORLD
    assert run_export["scenario"] == SCENARIO
    assert run_export["tool_trace"] == []
    assert run_export["verifier_result"] == finalization["verifier_result"]


def test_finalize_after_oracle_equivalent_mcp_calls_returns_ok_and_exports_trace(tmp_path: Path) -> None:
    manifest = create_world_session(
        world=WORLD,
        scenario=SCENARIO,
        seed=105,
        out_dir=tmp_path / "adaptyv-session",
    )
    run_dir = Path(manifest["run_dir"])
    handler = create_mcp_handler(run_dir)

    initialized = handler.handle_message(
        {
            "jsonrpc": "2.0",
            "id": "initialize",
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        }
    )
    assert initialized is not None
    assert initialized["result"]["serverInfo"]["name"] == MCP_SERVER_NAME

    listed = handler.handle_message({"jsonrpc": "2.0", "id": "list", "method": "tools/list"})
    assert listed is not None
    assert sorted(tool["name"] for tool in listed["result"]["tools"]) == sorted(_spec_tools())

    experiments = _mcp_call(handler, "list_experiments", {})["data"]["experiments"]
    experiment_id = next(row["id"] for row in experiments if row["status"] == "submitted")
    _mcp_call(handler, "list_experiment_updates", {"experiment_id": experiment_id})
    winner = _wait_for_visible_final_winner(handler, experiment_id)

    decision = _mcp_call(
        handler,
        "submit_campaign_decision",
        {
            "experiment_id": experiment_id,
            "decision": "select_measured_replay_winner",
            "cited_result_ids": [winner["id"]],
            "rationale": "Waited for final visible measured replay results and cited the best final current-experiment result.",
        },
    )
    assert decision["data"]["campaign_decision"]["cited_result_ids"] == [winner["id"]]

    finalization = finalize_world_session(run_dir)
    run_export = _read_json(run_dir / "run_export.json")

    assert finalization["ok"] is True
    assert finalization["verifier_result"]["ok"] is True
    assert finalization["verifier_result"]["failure_code"] is None
    assert run_export["verifier_result"]["ok"] is True
    tool_names = [row["tool_name"] for row in run_export["tool_trace"]]
    assert tool_names[:2] == ["list_experiments", "list_experiment_updates"]
    assert tool_names[-1] == "submit_campaign_decision"
    assert tool_names.count("list_experiment_results") >= 2


def test_cli_create_check_tools_finalize_smoke_for_initial_failure(tmp_path: Path) -> None:
    run_dir = tmp_path / "adaptyv-cli-session"
    runner = CliRunner()

    created = runner.invoke(
        app,
        [
            "session",
            "create",
            "--world",
            WORLD,
            "--scenario",
            SCENARIO,
            "--seed",
            "106",
            "--out",
            str(run_dir),
            "--json",
        ],
    )
    assert created.exit_code == 0, created.output
    assert json.loads(created.output)["expected_tools"] == sorted(_spec_tools())

    checked = runner.invoke(app, ["session", "check-tools", "--run", str(run_dir)])
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.output)["ok"] is True

    finalized = runner.invoke(app, ["session", "finalize", "--run", str(run_dir), "--json"])
    assert finalized.exit_code == 1, finalized.output
    payload = json.loads(finalized.output)
    assert payload["ok"] is False
    assert payload["verifier_result"]["failure_code"] == "MISSING_FINAL_CAMPAIGN_DECISION"
    assert (run_dir / "run_export.json").is_file()
    assert (run_dir / "session_finalization.json").is_file()


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


def _wait_for_visible_final_winner(handler: Any, experiment_id: str) -> dict[str, Any]:
    for _ in range(4):
        response = _mcp_call(handler, "list_experiment_results", {"experiment_id": experiment_id})
        final_rows = [row for row in response["data"]["results"] if row["status"] == "final"]
        if final_rows:
            return min(
                final_rows,
                key=lambda row: (
                    int(row["value"].get("rank", 999)),
                    float(row["value"].get("kd_m", "inf")),
                    row["id"],
                ),
            )
    raise AssertionError("Final measured replay results were not reachable through MCP polling.")


def _spec_tools() -> list[str]:
    spec = _read_json(REPO_ROOT / "worlds" / WORLD / "spec.json")
    tools = spec["tools"]
    assert isinstance(tools, list)
    return [str(tool) for tool in tools]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
