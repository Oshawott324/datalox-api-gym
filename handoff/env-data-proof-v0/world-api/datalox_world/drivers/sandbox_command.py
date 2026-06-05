from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..types import ExportResult, FinalizeResult, ResetResult, StepResult, ToolCall


@dataclass
class _SandboxSession:
    task_id: str
    run_dir: Path
    tools: list[dict[str, Any]]


class SandboxCommandDriver:
    """Generic boundary for sandbox/runtime-backed worlds.

    The external runtime owns sandbox setup and domain behavior. This driver
    only substitutes lifecycle placeholders, executes commands, and validates
    structured JSON responses.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.sessions: dict[str, _SandboxSession] = {}

    def reset(self, task_id: str, run_dir: str | Path, seed: int | None = None) -> ResetResult:
        run_root = Path(run_dir).resolve()
        result = self._run_json("reset_command", {
            "task_id": task_id,
            "run_dir": str(run_root),
            "seed": "" if seed is None else str(seed),
        })
        session_id = _required_str(result, "session_id")
        tools = _required_list(result, "tools")
        observation = _required_dict(result, "observation")
        observed_task_id = _required_str(result, "task_id")
        self.sessions[session_id] = _SandboxSession(task_id=observed_task_id, run_dir=run_root, tools=tools)
        return ResetResult(
            session_id=session_id,
            task_id=observed_task_id,
            observation=observation,
            tools=tools,
            run_dir=run_root,
        )

    def tools(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._session(session_id).tools)

    def step(self, session_id: str, tool_call: ToolCall) -> StepResult:
        self._session(session_id)
        result = self._run_json("step_command", {
            "session_id": session_id,
            "tool_name": tool_call.name,
            "arguments_json": json.dumps(tool_call.arguments, sort_keys=True),
        })
        return StepResult(
            observation=_required_dict(result, "observation"),
            reward=float(result.get("reward", 0)),
            terminated=bool(result.get("terminated", False)),
            truncated=bool(result.get("truncated", False)),
            info=_dict_or_empty(result.get("info")),
        )

    def finalize(self, session_id: str, answer: dict[str, Any]) -> FinalizeResult:
        self._session(session_id)
        result = self._run_json("finalize_command", {
            "session_id": session_id,
            "answer_json": json.dumps(answer, sort_keys=True),
        })
        return FinalizeResult(
            passed=bool(result.get("passed", False)),
            reward=float(result.get("reward", 0)),
            terminated=bool(result.get("terminated", True)),
            info=_dict_or_empty(result.get("info")),
        )

    def export(self, session_id: str, format: str, out_path: str | Path | None = None) -> ExportResult:
        self._session(session_id)
        if "export_command" not in self.config:
            raise ValueError("sandbox_command driver has no export_command configured")
        result = self._run_json("export_command", {
            "session_id": session_id,
            "format": format,
            "out_path": "" if out_path is None else str(out_path),
        })
        return ExportResult(
            format=_required_str(result, "format"),
            path=_required_str(result, "path"),
            rows=int(result.get("rows", 0)),
        )

    def _run_json(self, command_key: str, values: dict[str, str]) -> dict[str, Any]:
        command = self.config.get(command_key)
        if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
            raise ValueError(f"sandbox_command driver requires string list: {command_key}")
        expanded = [_expand(item, values) for item in command]
        completed = subprocess.run(expanded, text=True, capture_output=True)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or f"Command failed: {expanded}")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ValueError(f"Command did not return JSON: {expanded}") from error
        if not isinstance(result, dict):
            raise ValueError(f"Command must return JSON object: {expanded}")
        return result

    def _session(self, session_id: str) -> _SandboxSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown sandbox session: {session_id}")
        return session


def _expand(value: str, mapping: dict[str, str]) -> str:
    rendered = value
    for key, replacement in mapping.items():
        rendered = rendered.replace("{" + key + "}", replacement)
    return rendered


def _required_str(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"Expected non-empty string field: {key}")
    return item


def _required_dict(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"Expected object field: {key}")
    return item


def _required_list(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
    item = value.get(key)
    if not isinstance(item, list) or not all(isinstance(entry, dict) for entry in item):
        raise ValueError(f"Expected object list field: {key}")
    return item


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
