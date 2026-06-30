"""Trace recorder for agent-visible tool calls and semantic state diffs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from greenfield_lablongrun.core.schemas import append_jsonl, count_jsonl


TOOL_CALLS_NAME = "tool_calls.jsonl"
STATE_DIFFS_NAME = "state_diffs.jsonl"


class TraceRecorder:
    """Append-only JSONL recorder scoped to one run directory."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.tool_calls_path = run_dir / TOOL_CALLS_NAME
        self.state_diffs_path = run_dir / STATE_DIFFS_NAME
        self._tool_sequence = count_jsonl(self.tool_calls_path)
        self._diff_sequence = count_jsonl(self.state_diffs_path)

    def record_tool_call(self, tool_name: str, arguments: dict[str, Any], result: dict[str, Any]) -> int:
        self._tool_sequence += 1
        record = {
            "schema_version": "greenfield_lablongrun.tool_call.v0",
            "sequence": self._tool_sequence,
            "tool_name": tool_name,
            "arguments": arguments,
            "ok": bool(result.get("ok")),
            "result": result,
        }
        error = result.get("error")
        if isinstance(error, dict):
            record["error_code"] = error.get("code")
        append_jsonl(self.tool_calls_path, record)
        return self._tool_sequence

    def record_state_diff(self, source_tool_sequence: int, action: str, diff: dict[str, Any]) -> int:
        self._diff_sequence += 1
        record = {
            "schema_version": "greenfield_lablongrun.state_diff.v0",
            "sequence": self._diff_sequence,
            "source_tool_sequence": source_tool_sequence,
            "action": action,
            "diff": diff,
        }
        append_jsonl(self.state_diffs_path, record)
        return self._diff_sequence

    def counts(self) -> dict[str, int]:
        return {
            "tool_calls": count_jsonl(self.tool_calls_path),
            "state_diffs": count_jsonl(self.state_diffs_path),
        }

