from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io import read_json, read_jsonl
from .prompting import render_system_prompt
from .types import ExportResult


def export_sft_messages(
    run_dir: str | Path,
    tools: list[dict[str, Any]],
    out_path: str | Path,
    task_tool_names: list[str] | None = None,
) -> ExportResult:
    run_root = Path(run_dir)
    verifier_result = read_json(run_root / "verifier_result.json")
    if verifier_result.get("passed") is not True:
        raise ValueError("Cannot export SFT messages from a non-passing run.")

    run = read_json(run_root / "run.json")
    task = read_json(run_root / "workspace" / "task.json")
    scoped_task_tool_names = task_tool_names or list(task["allowed_tools"])
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": render_system_prompt(tools, scoped_task_tool_names)},
        {"role": "user", "content": task["prompt"]},
    ]

    final_answer = None
    tool_index = 0
    for event in read_jsonl(run_root / "trajectory.jsonl"):
        if event.get("type") == "tool_call":
            tool_index += 1
            call_id = f"call_{tool_index}"
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": event["tool_name"],
                        "arguments": json.dumps(event["arguments"], sort_keys=True),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": event["tool_name"],
                "content": json.dumps(event["observation"], sort_keys=True),
            })
        if event.get("type") == "submit_answer" and event.get("verifier_result", {}).get("passed") is True:
            final_answer = event["answer"]

    if final_answer is None:
        raise ValueError("Passing submit_answer event not found.")

    messages.append({
        "role": "assistant",
        "content": json.dumps(final_answer, sort_keys=True),
    })

    row = {
        "schema_version": "datalox_world_sft_messages.v0",
        "task_id": run["task_id"],
        "family": run["family"],
        "source_run": str(run_root),
        "messages": messages,
    }
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True))
        handle.write("\n")
    return ExportResult(format="sft_messages", path=str(target), rows=1)
