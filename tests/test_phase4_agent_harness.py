from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from api_gym.agent_harness import AGENT_TOOL_TRACE_NAME, MCP_SERVER_NAME, BillingSupportMcpHandler
from api_gym.cli import app
from api_gym.worlds.billing_support_v0.sampler import sample_episode
from api_gym.worlds.billing_support_v0.state import loads_json
from api_gym.worlds.billing_support_v0.tools import TOOL_DEFINITIONS


EXPECTED_TOOL_NAMES = {
    "support_get_ticket",
    "support_add_reply",
    "support_close_ticket",
    "support_tag_ticket",
    "support_escalate_ticket",
    "billing_get_customer",
    "billing_get_invoice",
    "billing_get_payment",
    "billing_create_refund",
    "billing_retry_invoice",
}


def test_task_cli_prints_agent_host_package_and_writes_file(tmp_path: Path) -> None:
    episode = sample_episode(scenario="duplicate_payment_refund", seed=17, out_dir=tmp_path / "run")
    out = tmp_path / "agent-task.json"
    result = CliRunner().invoke(app, ["task", "--run", str(episode.run_dir), "--out", str(out)])

    assert result.exit_code == 0, result.output
    package = json.loads(result.output)
    written = json.loads(out.read_text(encoding="utf-8"))

    assert package == written
    assert package["schema_version"] == "api_gym.agent_task.v0"
    assert package["world"] == "billing_support_v0"
    assert package["world_id"] == "billing-support-v0"
    assert package["scenario"] == "duplicate_payment_refund"
    assert package["run_dir"] == str(episode.run_dir)
    assert "Use the MCP tools" in package["agent_facing_instructions"]
    assert "Do not answer from task text alone" in package["agent_facing_instructions"]
    assert episode.task["prompt"] in package["agent_facing_instructions"]
    assert package["verifier_command"] == ["api-gym", "verify", "--run", str(episode.run_dir)]
    assert package["recommended_mcp_command"] == ["api-gym", "mcp", "--run", str(episode.run_dir)]
    assert package["recommended_mcp_config"]["mcpServers"][MCP_SERVER_NAME] == {
        "command": "api-gym",
        "args": ["mcp", "--run", str(episode.run_dir)],
    }
    assert package["environment"]["API_GYM_RUN_DIR"] == str(episode.run_dir)
    assert package["environment"]["API_GYM_TASK_JSON"] == str(out.resolve())
    assert package["environment"]["API_GYM_MCP_COMMAND"] == package["recommended_mcp_command_string"]


def test_mcp_handler_lists_tools_calls_tool_and_traces(tmp_path: Path) -> None:
    episode = sample_episode(scenario="duplicate_payment_refund", seed=18, out_dir=tmp_path / "run")
    expected = _expected(episode.db_path)
    handler = BillingSupportMcpHandler(episode.run_dir)

    initialized = handler.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        }
    )

    assert initialized is not None
    assert initialized["result"]["protocolVersion"] == "2025-11-25"
    assert initialized["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert handler.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    listed = handler.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    assert listed is not None
    tools = listed["result"]["tools"]
    assert {tool["name"] for tool in tools} == EXPECTED_TOOL_NAMES
    assert all(tool["inputSchema"]["type"] == "object" for tool in tools)

    called = handler.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "support_get_ticket", "arguments": {"ticket_id": expected["ticket_id"]}},
        }
    )

    assert called is not None
    result = called["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["ok"] is True
    assert result["structuredContent"]["data"]["id"] == expected["ticket_id"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]

    trace_rows = [
        json.loads(line)
        for line in (episode.run_dir / AGENT_TOOL_TRACE_NAME).read_text(encoding="utf-8").splitlines()
    ]
    assert len(trace_rows) == 1
    assert trace_rows[0]["schema_version"] == "api_gym.agent_tool_call.v0"
    assert trace_rows[0]["world"] == "billing_support_v0"
    assert trace_rows[0]["scenario"] == "duplicate_payment_refund"
    assert trace_rows[0]["tool_name"] == "support_get_ticket"
    assert trace_rows[0]["arguments"] == {"ticket_id": expected["ticket_id"]}
    assert trace_rows[0]["result"] == result["structuredContent"]


def test_agent_facing_tool_schemas_describe_refund_and_escalation_semantics(tmp_path: Path) -> None:
    episode = sample_episode(scenario="refund_not_allowed_policy", seed=21, out_dir=tmp_path / "run")
    handler = BillingSupportMcpHandler(episode.run_dir)
    listed = handler.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert listed is not None
    openai_tools = {
        tool["function"]["name"]: {
            "description": tool["function"]["description"],
            "inputSchema": tool["function"]["parameters"],
        }
        for tool in TOOL_DEFINITIONS
    }
    mcp_tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

    for tools in (openai_tools, mcp_tools):
        refund_tool = tools["billing_create_refund"]
        refund_description = refund_tool["description"]
        refund_reason = refund_tool["inputSchema"]["properties"]["reason"]
        reason_description = refund_reason["description"]

        assert "succeeded payment" in refund_description
        assert "policy allows" in refund_description
        assert refund_reason["enum"] == ["duplicate", "fraudulent", "requested_by_customer"]
        assert "duplicate charges/payments" in reason_description
        assert "requested_by_customer" in reason_description
        assert "not duplicates or fraud" in reason_description
        assert "fraudulent only for suspected fraud" in reason_description

        escalate_tool = tools["support_escalate_ticket"]
        escalate_description = escalate_tool["description"]
        escalate_reason = escalate_tool["inputSchema"]["properties"]["reason"]["description"]

        assert "internal billing policy review" in escalate_description
        assert "internal assignment/review state only" in escalate_description
        assert "does not send a customer-visible reply" in escalate_description
        assert "support_add_reply" in escalate_description
        assert "policy/refund-window explanation" in escalate_description
        assert "Internal escalation rationale" in escalate_reason
        assert "not customer-visible text" in escalate_reason
        assert "not a substitute for support_add_reply" in escalate_reason

        add_reply_tool = tools["support_add_reply"]
        add_reply_description = add_reply_tool["description"]

        assert "customer-visible" in add_reply_description
        assert "notify the customer" in add_reply_description
        assert "billing policy and refund decisions" in add_reply_description

        combined_text = "\n".join(
            [
                refund_description,
                reason_description,
                escalate_description,
                escalate_reason,
                add_reply_description,
            ]
        )
        assert "duplicate_payment_refund" not in combined_text
        assert "refund_not_allowed_policy" not in combined_text
        assert "verifier" not in combined_text.lower()


def test_run_host_passes_environment_and_writes_verifier_result(tmp_path: Path) -> None:
    episode = sample_episode(scenario="failed_invoice_retryable", seed=19, out_dir=tmp_path / "run")
    env_probe = tmp_path / "host-env.json"
    code = (
        "import json, os, pathlib; "
        f"pathlib.Path({str(env_probe)!r}).write_text("
        "json.dumps({key: os.environ.get(key) for key in "
        "['API_GYM_RUN_DIR', 'API_GYM_TASK_JSON', 'API_GYM_MCP_COMMAND', 'API_GYM_VERIFY_COMMAND']}), "
        "encoding='utf-8')"
    )

    result = CliRunner().invoke(app, ["run-host", "--run", str(episode.run_dir), "--", sys.executable, "-c", code])

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    env = json.loads(env_probe.read_text(encoding="utf-8"))

    assert payload["host_exit_code"] == 0
    assert payload["ok"] is False
    assert payload["verifier_result"]["ok"] is False
    assert Path(payload["task_package"]).exists()
    assert Path(payload["result_path"]).exists()
    assert env["API_GYM_RUN_DIR"] == str(episode.run_dir)
    assert env["API_GYM_TASK_JSON"] == str(episode.run_dir / "agent_task.json")
    assert env["API_GYM_MCP_COMMAND"] == f"api-gym mcp --run {episode.run_dir}"
    assert env["API_GYM_VERIFY_COMMAND"] == f"api-gym verify --run {episode.run_dir}"


def _expected(db_path: Path) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT payload_json FROM events
            WHERE event_type = 'expected_resolution.created'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
    assert row is not None
    return loads_json(row[0])
