"""Shared HTTP adapter helpers for API Gym worlds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

COMMON_HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
WORLD_HTTP_CALL_SCHEMA_VERSION = "api_gym.world_http_call.v0"


async def request_json_or_none(request: Request) -> object:
    """Return a request JSON body, or None for non-JSON/empty bodies."""
    try:
        return await request.json()
    except json.JSONDecodeError:
        return None


def query_params(request: Request) -> dict[str, object]:
    """Return query parameters with repeated keys preserved as lists."""
    return {
        key: values[0] if len(values) == 1 else values
        for key in sorted(set(request.query_params.keys()))
        if (values := request.query_params.getlist(key))
    }


def append_jsonl(path: Path, row: dict[str, object]) -> None:
    """Append one compact JSON object row to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def append_world_http_trace(
    trace_path: Path,
    *,
    world: str,
    method: str,
    path_value: str,
    query_params: dict[str, object],
    request_json: object,
    status_code: int,
    response: dict[str, Any],
) -> None:
    """Append one stateful world HTTP call trace row."""
    ok = response.get("ok") is True
    row: dict[str, object] = {
        "schema_version": WORLD_HTTP_CALL_SCHEMA_VERSION,
        "world": world,
        "method": method,
        "path": path_value,
        "query_params": query_params,
        "request_json": request_json,
        "status_code": status_code,
        "ok": ok,
    }
    error = response.get("error")
    if not ok and isinstance(error, dict):
        row["error"] = error
    append_jsonl(trace_path, row)


def structured_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any],
) -> JSONResponse:
    """Build a stable agent-readable JSON error response."""
    return JSONResponse(
        content={
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "details": details,
            },
        },
        status_code=status_code,
    )
