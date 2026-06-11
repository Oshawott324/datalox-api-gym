"""Agent-host harness surfaces for sampled API Gym runs."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

import api_gym
from api_gym.worlds.registry import WorldRuntime, get_runtime_for_run, read_run_metadata

AGENT_TASK_NAME = "agent_task.json"
AGENT_TOOL_TRACE_NAME = "agent_tool_calls.jsonl"
HOST_RESULT_NAME = "host_result.json"
MCP_SERVER_NAME = "api-gym-billing-support-v0"
MCP_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_MCP_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")


def build_agent_task_package(run_dir: Path) -> dict[str, Any]:
    """Build the JSON payload an agent host should receive for one run."""
    run_dir = run_dir.resolve()
    runtime = _ensure_supported_run(run_dir)
    task = _read_json(run_dir / runtime.task_name)
    metadata = _read_json(run_dir / runtime.run_metadata_name)
    prompt = str(task.get("prompt", "")).strip()
    mcp_command = ["api-gym", "mcp", "--run", str(run_dir)]
    verifier_command = ["api-gym", "verify", "--run", str(run_dir)]

    rules = [
        "Use the MCP tools for every state inspection and mutation.",
        "Do not answer from task text alone.",
        "Do not inspect state.sqlite or hidden verifier state directly.",
        "Finish by leaving the run state ready for the verifier command to pass.",
    ]
    instructions = "\n".join(
        [
            f"You are solving a Datalox API Gym {runtime.world} task.",
            "",
            prompt,
            "",
            "Rules:",
            *(f"- {rule}" for rule in rules),
        ]
    )

    return {
        "schema_version": "api_gym.agent_task.v0",
        "world": metadata["world"],
        "world_id": metadata["world_id"],
        "scenario": metadata["scenario"],
        "seed": metadata["seed"],
        "run_dir": str(run_dir),
        "agent_facing_instructions": instructions,
        "task": task,
        "rules": rules,
        "verifier_command": verifier_command,
        "verifier_command_string": shlex.join(verifier_command),
        "recommended_mcp_command": mcp_command,
        "recommended_mcp_command_string": shlex.join(mcp_command),
        "recommended_mcp_config": {
            "mcpServers": {
                runtime.mcp_server_name: {
                    "command": "api-gym",
                    "args": ["mcp", "--run", str(run_dir)],
                }
            }
        },
        "environment": {
            "API_GYM_RUN_DIR": str(run_dir),
            "API_GYM_TASK_JSON": str(run_dir / AGENT_TASK_NAME),
            "API_GYM_MCP_COMMAND": shlex.join(mcp_command),
            "API_GYM_VERIFY_COMMAND": shlex.join(verifier_command),
        },
    }


def write_agent_task_package(run_dir: Path, out: Path) -> Path:
    """Write the agent task package and return the resolved output path."""
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    package = build_agent_task_package(run_dir)
    package["task_package_path"] = str(out)
    package["environment"]["API_GYM_TASK_JSON"] = str(out)
    out.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def run_host_command(*, run_dir: Path, command: list[str], result_out: Path | None = None) -> dict[str, Any]:
    """Execute a generic agent host command, then verify and record the result."""
    if not command:
        raise ValueError("Host command is required after '--'.")

    run_dir = run_dir.resolve()
    runtime = _ensure_supported_run(run_dir)
    task_package_path = write_agent_task_package(run_dir, run_dir / AGENT_TASK_NAME)
    mcp_command = ["api-gym", "mcp", "--run", str(run_dir)]
    verifier_command = ["api-gym", "verify", "--run", str(run_dir)]
    env = os.environ.copy()
    env.update(
        {
            "API_GYM_RUN_DIR": str(run_dir),
            "API_GYM_TASK_JSON": str(task_package_path),
            "API_GYM_MCP_COMMAND": shlex.join(mcp_command),
            "API_GYM_VERIFY_COMMAND": shlex.join(verifier_command),
        }
    )

    completed = subprocess.run(command, env=env, check=False)
    verifier_result = runtime.verify_run(run_dir).to_dict()
    result_path = (result_out or (run_dir / HOST_RESULT_NAME)).resolve()
    result = {
        "ok": completed.returncode == 0 and verifier_result["ok"],
        "host_command": command,
        "host_exit_code": completed.returncode,
        "run_dir": str(run_dir),
        "task_package": str(task_package_path),
        "verifier_command": verifier_command,
        "verifier_result": verifier_result,
        "result_path": str(result_path),
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


class BillingSupportMcpHandler:
    """Compatibility MCP handler for one billing_support_v0 run."""

    def __init__(self, run_dir: Path) -> None:
        self._handler = create_mcp_handler(run_dir)
        if self._handler.metadata.get("world") != "billing_support_v0":
            raise ValueError("BillingSupportMcpHandler only supports billing_support_v0 runs.")

    @property
    def stop_requested(self) -> bool:
        return self._handler.stop_requested

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        return self._handler.handle_message(message)


class ApiGymMcpHandler:
    """Minimal MCP JSON-RPC handler for one sampled API Gym run."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir.resolve()
        self.runtime = _ensure_supported_run(self.run_dir)
        self.db_path = self.runtime.resolve_state_db_path(self.run_dir)
        self.metadata = _read_json(self.run_dir / self.runtime.run_metadata_name)
        self.protocol_version = MCP_PROTOCOL_VERSION
        self.stop_requested = False

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        if not isinstance(method, str):
            return None

        if method == "notifications/initialized":
            return None
        if method == "exit":
            self.stop_requested = True
            return None
        if "id" not in message:
            return None

        request_id = message.get("id")
        if method == "initialize":
            return self._initialize(request_id, message.get("params"))
        if method == "tools/list":
            return _jsonrpc_result(request_id, {"tools": [_to_mcp_tool(tool) for tool in self.runtime.tool_definitions]})
        if method == "tools/call":
            return self._call_tool(request_id, message.get("params"))
        if method == "shutdown":
            self.stop_requested = True
            return _jsonrpc_result(request_id, {})
        return _jsonrpc_error(request_id, -32601, "Method not found.", {"method": method})

    def _initialize(self, request_id: Any, params: Any) -> dict[str, Any]:
        client_version = params.get("protocolVersion") if isinstance(params, dict) else None
        self.protocol_version = _negotiate_protocol_version(client_version)
        return _jsonrpc_result(
            request_id,
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": self.runtime.mcp_server_name,
                    "title": self.runtime.mcp_server_title,
                    "version": api_gym.__version__,
                },
            },
        )

    def _call_tool(self, request_id: Any, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            return _jsonrpc_error(request_id, -32602, "tools/call params must be an object.")
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name:
            return _jsonrpc_error(request_id, -32602, "tools/call requires a non-empty tool name.")
        if not isinstance(arguments, dict):
            return _jsonrpc_error(request_id, -32602, "tools/call arguments must be an object.")

        result = self.runtime.dispatch_tool(self.db_path, name=name, arguments=arguments)
        self._append_tool_trace(name=name, arguments=arguments, result=result)
        return _jsonrpc_result(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(result, indent=2, sort_keys=True)}],
                "structuredContent": result,
                "isError": not bool(result.get("ok")),
            },
        )

    def _append_tool_trace(self, *, name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        row = {
            "schema_version": "api_gym.agent_tool_call.v0",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "world": self.metadata["world"],
            "scenario": self.metadata["scenario"],
            "tool_name": name,
            "arguments": arguments,
            "result": result,
        }
        with (self.run_dir / AGENT_TOOL_TRACE_NAME).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def serve_mcp_stdio(run_dir: Path, input_stream: TextIO | None = None, output_stream: TextIO | None = None) -> None:
    """Serve one run over line-delimited MCP JSON-RPC on stdio."""
    handler = create_mcp_handler(run_dir)
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout

    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        request_id = None
        try:
            message = json.loads(line)
            request_id = message.get("id") if isinstance(message, dict) else None
            if not isinstance(message, dict):
                response = _jsonrpc_error(None, -32600, "JSON-RPC message must be an object.")
            else:
                response = handler.handle_message(message)
        except json.JSONDecodeError as exc:
            response = _jsonrpc_error(None, -32700, "Parse error.", {"message": str(exc)})
        except Exception as exc:
            response = _jsonrpc_error(request_id, -32603, "Internal MCP server error.", {"message": str(exc)})

        if response is not None:
            output_stream.write(json.dumps(response, separators=(",", ":")) + "\n")
            output_stream.flush()
        if handler.stop_requested:
            break


def create_mcp_handler(run_dir: Path) -> ApiGymMcpHandler:
    """Create an MCP handler for the world declared by run metadata."""
    return ApiGymMcpHandler(run_dir)


def _ensure_supported_run(run_dir: Path) -> WorldRuntime:
    runtime = get_runtime_for_run(run_dir)
    runtime.resolve_state_db_path(run_dir)
    metadata = read_run_metadata(run_dir)
    if metadata.get("world") != runtime.world:
        raise ValueError(f"Run metadata world does not match runtime world '{runtime.world}'.")
    task_path = run_dir / runtime.task_name
    if not task_path.exists():
        raise FileNotFoundError(f"Missing {runtime.task_name} in run directory: {run_dir}")
    return runtime


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return data


def _to_mcp_tool(tool: dict[str, Any]) -> dict[str, Any]:
    function = tool["function"]
    return {
        "name": function["name"],
        "description": function.get("description", ""),
        "inputSchema": function["parameters"],
    }


def _negotiate_protocol_version(client_version: Any) -> str:
    if isinstance(client_version, str) and client_version in SUPPORTED_MCP_PROTOCOL_VERSIONS:
        return client_version
    return MCP_PROTOCOL_VERSION


def _jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}
