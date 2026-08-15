"""Shared operation helpers for the PyLabRobot science workflow world."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine


Handler = Callable[[Any, dict[str, Any], dict[str, Any]], dict[str, Any]]


def tool_definition(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def error(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "details": details},
    }


def run_async(coroutine: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coroutine)


def require_family(state: dict[str, Any], expected: str) -> dict[str, Any] | None:
    if state["family"] == expected:
        return None
    return error(
        "tool_not_available_for_scenario",
        f"This operation belongs to the {expected} workflow family.",
        active_family=state["family"],
    )
