"""Small schema helpers for verifier results, exports, and tool errors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ActionError(Exception):
    """Structured tool error intended to be useful to an agent."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_result(self) -> dict[str, Any]:
        return tool_error(self.code, self.message, self.details)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    category: str
    message: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "ok": self.ok,
            "category": self.category,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(frozen=True)
class VerifierResult:
    schema_version: str
    world: str
    scenario: str
    ok: bool
    checks: list[Check]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "world": self.world,
            "scenario": self.scenario,
            "ok": self.ok,
            "checks": [check.to_dict() for check in self.checks],
        }


def check(name: str, ok: bool, category: str, message: str, details: dict[str, Any] | None = None) -> Check:
    return Check(name=name, ok=bool(ok), category=category, message=message, details=details)


def tool_ok(data: dict[str, Any], warnings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "data": data}
    if warnings:
        payload["warnings"] = warnings
    return payload


def tool_error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details or {}}}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

