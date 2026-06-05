from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ResetResult:
    session_id: str
    task_id: str
    observation: dict[str, Any]
    tools: list[dict[str, Any]]
    run_dir: Path


@dataclass(frozen=True)
class StepResult:
    observation: dict[str, Any]
    reward: float
    terminated: bool
    truncated: bool
    info: dict[str, Any]


@dataclass(frozen=True)
class FinalizeResult:
    passed: bool
    reward: float
    terminated: bool
    info: dict[str, Any]


@dataclass(frozen=True)
class ExportResult:
    format: str
    path: str
    rows: int
