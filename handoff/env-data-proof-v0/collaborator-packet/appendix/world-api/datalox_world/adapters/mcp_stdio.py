#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datalox_world.registry import load_driver
from datalox_world.types import ToolCall


SUBMIT_TOOL = {
    "name": "datalox_submit_answer",
    "description": "Submit the final structured answer to the task verifier and receive pass/fail reward.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "object",
                "description": "Structured final answer for the current task."
            }
        },
        "required": ["answer"],
        "additionalProperties": False,
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minimal MCP stdio adapter for Datalox World API v0.")
    parser.add_argument("--world", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args(argv)

    driver = load_driver(args.world)
    reset = driver.reset(args.task_id, Path(args.run))
    server = McpServer(driver, reset.session_id)
    server.serve()
    return 0


class McpServer:
    def __init__(self, driver, session_id: str):
        self.driver = driver
        self.session_id = session_id

    def serve(self) -> None:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                response = self.handle(request)
            except Exception as error:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(error)},
                }
            sys.stdout.write(json.dumps(response, sort_keys=True) + "\n")
            sys.stdout.flush()

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "serverInfo": {"name": "datalox-world-api", "version": "0.0.1"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": [_mcp_tool(tool) for tool in [*self.driver.tools(self.session_id), SUBMIT_TOOL]]}
        elif method == "tools/call":
            result = self._call_tool(params)
        elif method == "shutdown":
            result = {}
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unsupported method: {method}"},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str):
            raise ValueError("tools/call requires string name")
        if not isinstance(arguments, dict):
            raise ValueError("tools/call requires object arguments")
        if name == SUBMIT_TOOL["name"]:
            answer = arguments.get("answer")
            if not isinstance(answer, dict):
                raise ValueError("datalox_submit_answer requires answer object")
            final = self.driver.finalize(self.session_id, answer)
            structured = {
                "passed": final.passed,
                "reward": final.reward,
                "terminated": final.terminated,
                "info": final.info,
            }
            return _tool_result(structured)
        step = self.driver.step(self.session_id, ToolCall(name, arguments))
        return _tool_result(step.observation)


def _mcp_tool(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool["name"],
        "description": tool["description"],
        "inputSchema": tool["input_schema"],
    }


def _tool_result(structured: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(structured, sort_keys=True)}],
        "structuredContent": structured,
    }


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
