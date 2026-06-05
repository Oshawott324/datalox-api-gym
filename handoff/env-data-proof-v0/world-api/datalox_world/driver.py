from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .types import ExportResult, FinalizeResult, ResetResult, StepResult, ToolCall


class WorldDriver(Protocol):
    def reset(self, task_id: str, run_dir: str | Path, seed: int | None = None) -> ResetResult:
        ...

    def tools(self, session_id: str) -> list[dict]:
        ...

    def step(self, session_id: str, tool_call: ToolCall) -> StepResult:
        ...

    def finalize(self, session_id: str, answer: dict) -> FinalizeResult:
        ...

    def export(self, session_id: str, format: str, out_path: str | Path | None = None) -> ExportResult:
        ...
