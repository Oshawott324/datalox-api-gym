from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..exporters import export_sft_messages
from ..io import read_json, write_json
from ..types import ExportResult, FinalizeResult, ResetResult, StepResult, ToolCall


@dataclass
class _Session:
    task_id: str
    run_dir: Path
    tools: list[dict[str, Any]]
    task_tool_names: list[str]
    finalized: bool = False


class RunnableWorldDriver:
    def __init__(self, world_spec_path: str | Path, runnable_world_root: str | Path):
        self.world_spec_path = Path(world_spec_path).resolve()
        self.world_spec = read_json(self.world_spec_path)
        self.runnable_world_root = Path(runnable_world_root).resolve()
        self.runtime = _load_world_runtime(self.runnable_world_root)
        self.sessions: dict[str, _Session] = {}

    def reset(self, task_id: str, run_dir: str | Path, seed: int | None = None) -> ResetResult:
        run_root = Path(run_dir).resolve()
        run = self.runtime.create_run(task_id, run_root)
        task = read_json(run_root / "workspace" / "task.json")
        tools = self._environment_tools()
        task_tool_names = list(task["allowed_tools"])
        session_id = _session_id(task_id, run_root)
        self.sessions[session_id] = _Session(
            task_id=task_id,
            run_dir=run_root,
            tools=tools,
            task_tool_names=task_tool_names,
        )
        observation = {
            "schema_version": "datalox_world_initial_observation.v0",
            "world_id": run["world_id"],
            "task_id": task_id,
            "family": task["family"],
            "prompt": task["prompt"],
            "run_dir": str(run_root),
            "workspace_dir": run["workspace_dir"],
            "tool_names": [tool["name"] for tool in tools],
            "task_tool_names": task_tool_names,
            "seed": seed,
        }
        return ResetResult(
            session_id=session_id,
            task_id=task_id,
            observation=observation,
            tools=tools,
            run_dir=run_root,
        )

    def tools(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._session(session_id).tools)

    def step(self, session_id: str, tool_call: ToolCall) -> StepResult:
        session = self._session(session_id)
        if session.finalized:
            return StepResult(
                observation={
                    "ok": False,
                    "error": {
                        "code": "session_finalized",
                        "message": "This world session has already been finalized.",
                    },
                },
                reward=0,
                terminated=True,
                truncated=False,
                info={
                    "session_id": session_id,
                    "task_id": session.task_id,
                    "tool_name": tool_call.name,
                    "run_dir": str(session.run_dir),
                },
            )
        observation = self.runtime.call_tool(session.run_dir, tool_call.name, tool_call.arguments)
        return StepResult(
            observation=observation,
            reward=0,
            terminated=False,
            truncated=False,
            info={
                "session_id": session_id,
                "task_id": session.task_id,
                "tool_name": tool_call.name,
                "run_dir": str(session.run_dir),
            },
        )

    def finalize(self, session_id: str, answer: dict[str, Any]) -> FinalizeResult:
        session = self._session(session_id)
        answer_path = session.run_dir / "answer.json"
        write_json(answer_path, answer)
        result = self.runtime.submit_answer(session.run_dir, answer_path)
        session.finalized = True
        return FinalizeResult(
            passed=bool(result["passed"]),
            reward=float(result["reward"]),
            terminated=True,
            info=result,
        )

    def export(self, session_id: str, format: str, out_path: str | Path | None = None) -> ExportResult:
        session = self._session(session_id)
        if format != "sft_messages":
            raise ValueError(f"Unsupported export format: {format}")
        target = Path(out_path) if out_path is not None else session.run_dir / "exports" / "sft.messages.jsonl"
        return export_sft_messages(session.run_dir, session.tools, target, session.task_tool_names)

    def _environment_tools(self) -> list[dict[str, Any]]:
        catalog = self.world_spec.get("tool_catalog")
        if not isinstance(catalog, dict):
            raise ValueError("world spec requires tool_catalog object")
        tools = []
        for name, entry in catalog.items():
            if not isinstance(entry, dict):
                raise ValueError(f"Tool catalog entry must be an object: {name}")
            input_schema = entry.get("input_schema")
            if not isinstance(input_schema, dict):
                raise ValueError(f"Tool entry requires input_schema: {name}")
            description = entry.get("description")
            if not isinstance(description, str) or not description:
                raise ValueError(f"Tool entry requires description: {name}")
            tools.append({
                "name": name,
                "description": description,
                "input_schema": input_schema,
            })
        return tools

    def _tools_for_task(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        tools_by_name = {tool["name"]: tool for tool in self._environment_tools()}
        scoped = []
        for name in task["allowed_tools"]:
            tool = tools_by_name.get(name)
            if tool is None:
                raise ValueError(f"Missing tool catalog entry: {name}")
            scoped.append(tool)
        return scoped

    def _session(self, session_id: str) -> _Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown world session: {session_id}")
        return session


def _load_world_runtime(runnable_world_root: Path):
    module_path = runnable_world_root / "bin" / "world_runtime.py"
    spec = importlib.util.spec_from_file_location("datalox_runnable_world_runtime", module_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load runnable world runtime: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _session_id(task_id: str, run_dir: Path) -> str:
    digest = hashlib.sha256(json.dumps({
        "task_id": task_id,
        "run_dir": str(run_dir),
    }, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"{task_id}:{digest}"
