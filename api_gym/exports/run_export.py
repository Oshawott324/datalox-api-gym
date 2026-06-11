"""Run evidence export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api_gym.agent_harness import AGENT_TOOL_TRACE_NAME
from api_gym.worlds.registry import get_runtime_for_run, read_run_metadata


def build_run_export(run_dir: Path) -> dict[str, Any]:
    """Build a compact evidence export for one sampled run."""
    run_dir = run_dir.resolve()
    runtime = get_runtime_for_run(run_dir)
    metadata = read_run_metadata(run_dir)
    task_path = run_dir / runtime.task_name
    if not task_path.exists():
        raise FileNotFoundError(f"Missing {runtime.task_name} in run directory: {run_dir}")

    task = _read_json(task_path)
    tool_trace_path = run_dir / AGENT_TOOL_TRACE_NAME
    tool_trace = _read_jsonl(tool_trace_path) if tool_trace_path.exists() else []
    verifier_result = runtime.verify_run(run_dir).to_dict()
    return {
        "schema_version": "api_gym.run_export.v0",
        "world": metadata["world"],
        "world_id": metadata["world_id"],
        "scenario": metadata["scenario"],
        "seed": metadata["seed"],
        "run_dir": str(run_dir),
        "task": task,
        "tool_trace": tool_trace,
        "verifier_result": verifier_result,
        "artifacts": {
            "run_metadata": str(run_dir / runtime.run_metadata_name),
            "task": str(task_path),
            "tool_trace": str(tool_trace_path) if tool_trace_path.exists() else None,
        },
    }


def write_run_export(run_dir: Path, out: Path) -> dict[str, Any]:
    """Write and return a compact evidence export for one sampled run."""
    payload = build_run_export(run_dir)
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object.")
    return data


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_number} must contain a JSON object.")
        rows.append(row)
    return rows
