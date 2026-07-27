from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from datalox_gated_runtime.remote_world_service import create_remote_world_app

WORLD_ID = "science_growth_kinetics_v0"
API_GYM_COMMIT = "ca47eb299ae1ea9f96848807c3d74395d486cce4"
GATED_RUNTIME_COMMIT = "ce5372623ddbab41dab169e4e0d0fc1c000a56c2"


def _csv_env(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    if not raw:
        return []
    values = raw.split(",")
    if any(not value for value in values):
        raise ValueError(f"{name} contains an empty entry")
    return values


def _append_once(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


allowed_hosts = _csv_env(
    "DATALOX_ALLOWED_HOSTS",
    "localhost:*,127.0.0.1:*",
)
allowed_origins = _csv_env("DATALOX_ALLOWED_ORIGINS")
space_host = os.getenv("SPACE_HOST", "")
if space_host:
    _append_once(allowed_hosts, space_host)
    _append_once(allowed_origins, f"https://{space_host}")

if not allowed_hosts:
    raise ValueError("At least one MCP Host must be allowed")

service = create_remote_world_app(
    runs_root=Path(os.getenv("DATALOX_RUNS_ROOT", "/home/user/runs")),
    allowed_examples={WORLD_ID},
    max_sessions=int(os.getenv("DATALOX_MAX_SESSIONS", "4")),
    ttl_seconds=float(os.getenv("DATALOX_SESSION_TTL_SECONDS", "1800")),
    cleanup_interval_seconds=float(os.getenv("DATALOX_CLEANUP_INTERVAL_SECONDS", "5")),
    allowed_hosts=allowed_hosts,
    allowed_origins=allowed_origins,
)


@service.control_app.get("/")
async def service_manifest() -> dict[str, Any]:
    return {
        "schema_version": "datalox_science_growth_space_manifest_v1",
        "service": "datalox_remote_world_service",
        "world_id": WORLD_ID,
        "dry_run_only": True,
        "routes": {
            "manifest": {"method": "GET", "path": "/"},
            "health": {"method": "GET", "path": "/health"},
            "create_session": {"method": "POST", "path": "/sessions"},
            "mcp": {
                "method": "POST",
                "path": "/sessions/{session_id}/mcp",
                "transport": "streamable_http",
            },
            "finalize": {
                "method": "POST",
                "path": "/sessions/{session_id}/finalize",
            },
            "export": {
                "method": "GET",
                "path": "/sessions/{session_id}/export",
            },
            "delete": {
                "method": "DELETE",
                "path": "/sessions/{session_id}",
            },
        },
        "pinned_commits": {
            "api_gym": API_GYM_COMMIT,
            "gated_runtime": GATED_RUNTIME_COMMIT,
        },
    }


app = service
