"""Tiny public-tool runtime for one lab_campaign_ops_v0 task family."""

from __future__ import annotations

import copy
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenfield_lab_campaign_ops.worlds.lab_campaign_ops_v0.tools import ToolError, dispatch_tool


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    ok: bool
    final_state: dict[str, Any]
    final_state_path: Path
    tool_calls_path: Path
    state_diffs_path: Path
    error: dict[str, Any] | None = None

    def trace_refs(self, *, base_dir: Path) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": _rel(self.run_dir, base_dir),
            "ok": self.ok,
            "final_state": _rel(self.final_state_path, base_dir),
            "tool_calls": _rel(self.tool_calls_path, base_dir),
            "state_diffs": _rel(self.state_diffs_path, base_dir),
            "error": self.error,
        }


def execute_plan(
    *,
    task_dir: Path,
    plan: dict[str, Any],
    run_dir: Path,
) -> RunResult:
    """Execute a hidden plan through agent-visible dry-run tools."""

    task_dir = task_dir.resolve()
    run_dir = run_dir.resolve()
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    initial_state = _read_json(task_dir / "initial_state.json")
    state = copy.deepcopy(initial_state)
    run_id = str(plan.get("plan_id") or run_dir.name)

    initial_state_path = run_dir / "initial_state.json"
    final_state_path = run_dir / "final_state.json"
    tool_calls_path = run_dir / "tool_calls.jsonl"
    state_diffs_path = run_dir / "state_diffs.jsonl"
    _write_json(initial_state_path, initial_state)
    tool_calls_path.write_text("", encoding="utf-8")
    state_diffs_path.write_text("", encoding="utf-8")

    run_error: dict[str, Any] | None = None
    for index, step in enumerate(plan.get("steps", []), start=1):
        before = copy.deepcopy(state)
        tool_family = step.get("tool_family")
        tool_id = step.get("tool_id")
        args = step.get("args", {})
        if not isinstance(tool_family, str) or not isinstance(tool_id, str) or not isinstance(args, dict):
            run_error = {
                "code": "PLAN_STEP_SCHEMA_MISMATCH",
                "message": "Plan step must define string tool_family/tool_id and object args.",
                "details": {"step_index": index},
            }
            _append_jsonl(
                tool_calls_path,
                _tool_call_record(index=index, step=step, status="error", error=run_error),
            )
            break

        try:
            output = dispatch_tool(tool_family=tool_family, tool_id=tool_id, state=state, args=args)
        except ToolError as exc:
            run_error = exc.to_dict()["error"]
            _append_jsonl(
                tool_calls_path,
                _tool_call_record(index=index, step=step, status="error", error=run_error),
            )
            break

        _append_jsonl(
            tool_calls_path,
            _tool_call_record(index=index, step=step, status="ok", output=output),
        )
        diff = _state_diff(before, state)
        if diff["changed"]:
            _append_jsonl(
                state_diffs_path,
                {
                    "call_index": index,
                    "tool_family": tool_family,
                    "tool_id": tool_id,
                    "diff": diff,
                },
            )

    _write_json(final_state_path, state)
    return RunResult(
        run_id=run_id,
        run_dir=run_dir,
        ok=run_error is None,
        final_state=state,
        final_state_path=final_state_path,
        tool_calls_path=tool_calls_path,
        state_diffs_path=state_diffs_path,
        error=run_error,
    )


def _tool_call_record(
    *,
    index: int,
    step: dict[str, Any],
    status: str,
    output: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "call_index": index,
        "tool_family": step.get("tool_family"),
        "tool_id": step.get("tool_id"),
        "args": copy.deepcopy(step.get("args", {})),
        "status": status,
    }
    if output is not None:
        record["output"] = output
    if error is not None:
        record["error"] = error
    return record


def _state_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed_keys = [key for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)]
    summaries = []
    for key in changed_keys:
        before_value = before.get(key)
        after_value = after.get(key)
        summary: dict[str, Any] = {"path": key}
        if isinstance(before_value, list) and isinstance(after_value, list):
            summary["before_count"] = len(before_value)
            summary["after_count"] = len(after_value)
            if len(after_value) > len(before_value):
                summary["added"] = after_value[len(before_value) :]
        else:
            summary["before"] = before_value
            summary["after"] = after_value
        summaries.append(summary)
    return {"changed": bool(changed_keys), "changes": summaries}


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rel(path: Path, base_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return str(path)
