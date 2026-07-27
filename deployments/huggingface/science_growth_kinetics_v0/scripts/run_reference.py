from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

WORLD_ID = "science_growth_kinetics_v0"
EPISODE_ID = "growth-kinetics-000"
REFERENCE_ID = "reference-growth-kinetics-000"
EXPECTED_EVENT_COUNT = 22
EXPECTED_CHECK_COUNT = 11
EXPECTED_PROVIDER_COUNTS = {
    "ot2": 9,
    "incubator": 2,
    "plate_reader": 1,
}


def _load_reference(worlds_root: Path) -> dict[str, Any]:
    path = worlds_root / WORLD_ID / "tests" / "trajectories" / "growth.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    trajectories = payload.get("trajectories")
    if not isinstance(trajectories, list):
        raise ValueError(f"trajectories must be a list: {path}")
    matches = [
        trajectory
        for trajectory in trajectories
        if trajectory.get("id") == REFERENCE_ID
        and trajectory.get("episode_id") == EPISODE_ID
        and trajectory.get("kind") == "reference"
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one seed-0 reference trajectory: {path}")
    reference = matches[0]
    steps = reference.get("steps")
    if not isinstance(steps, list) or len(steps) != EXPECTED_EVENT_COUNT:
        raise ValueError("seed-0 reference trajectory must contain exactly 22 steps")
    if any(step.get("surface") != "mcp" for step in steps):
        raise ValueError("seed-0 reference trajectory contains a non-MCP step")
    return reference


def _require_success(response: httpx.Response) -> dict[str, Any]:
    if response.is_error:
        raise RuntimeError(
            f"{response.request.method} {response.request.url} returned "
            f"{response.status_code}: {response.text}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("control-plane response must be a JSON object")
    return payload


async def _execute_reference(
    *,
    base_url: str,
    worlds_root: Path,
    transport_host: str | None,
    transport_origin: str | None,
) -> dict[str, Any]:
    reference = _load_reference(worlds_root)
    timeout = httpx.Timeout(120.0)
    session_id: str | None = None
    token: str | None = None

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as control:
        created = _require_success(
            await control.post(
                "/sessions",
                json={"example": WORLD_ID, "seed": 0},
            )
        )
        session_id = created["session_id"]
        token = created["token"]
        if created["task"]["task_id"] != EPISODE_ID:
            raise AssertionError("remote session did not select the seed-0 episode")

        mcp_url = f"{base_url.rstrip('/')}{created['mcp_url']}"
        mcp_headers = {"Authorization": f"Bearer {token}"}
        if transport_host:
            mcp_headers["Host"] = transport_host
        if transport_origin:
            mcp_headers["Origin"] = transport_origin
        mcp_http = httpx.AsyncClient(headers=mcp_headers, timeout=timeout)
        try:
            async with mcp_http:
                async with streamable_http_client(
                    mcp_url,
                    http_client=mcp_http,
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as mcp:
                        await mcp.initialize()
                        listed = await mcp.list_tools()
                        available = {tool.name for tool in listed.tools}
                        required = {step["tool_name"] for step in reference["steps"]}
                        missing = sorted(required - available)
                        if missing:
                            raise AssertionError(
                                f"reference tools missing from MCP catalog: {missing}"
                            )

                        for index, step in enumerate(reference["steps"], start=1):
                            result = await mcp.call_tool(
                                step["tool_name"],
                                arguments=step["arguments"],
                            )
                            if result.isError:
                                raise RuntimeError(
                                    f"reference step {index} failed "
                                    f"({step['tool_name']}): {result.content}"
                                )

            public_export = _require_success(
                await control.post(
                    f"/sessions/{session_id}/finalize",
                    headers={"Authorization": f"Bearer {token}"},
                )
            )
            _assert_public_export(public_export)
            return _summary(public_export)
        finally:
            if session_id and token:
                await control.delete(
                    f"/sessions/{session_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )


def _assert_public_export(public_export: dict[str, Any]) -> None:
    if public_export.get("schema_version") != "datalox_public_run_export_v1":
        raise AssertionError("unexpected public export schema")
    if public_export.get("example") != WORLD_ID:
        raise AssertionError("public export identifies the wrong example")
    world = public_export.get("world", {})
    if world.get("world_id") != WORLD_ID or world.get("episode_id") != EPISODE_ID:
        raise AssertionError("public export identifies the wrong world episode")

    events = public_export.get("events")
    if not isinstance(events, list) or len(events) != EXPECTED_EVENT_COUNT:
        raise AssertionError("public export must contain exactly 22 ledger events")

    verification = public_export.get("verification", {})
    if verification.get("passed") is not True:
        raise AssertionError("overall verification did not pass")
    world_verifier = verification.get("verifiers", {}).get("world", {})
    if world_verifier.get("passed") is not True:
        raise AssertionError("world verifier did not pass")
    checks = world_verifier.get("checks")
    if not isinstance(checks, list) or len(checks) != EXPECTED_CHECK_COUNT:
        raise AssertionError("world verifier must expose exactly 11 checks")
    if not all(check.get("passed") is True for check in checks):
        raise AssertionError("not all 11 world checks passed")

    public_evidence = world_verifier.get("public_evidence", {})
    provider_counts = public_evidence.get("provider_execution_counts")
    if provider_counts != EXPECTED_PROVIDER_COUNTS:
        raise AssertionError(
            "provider execution counts do not prove the expected "
            f"OT-2/incubator/plate-reader calls: {provider_counts}"
        )


def _summary(public_export: dict[str, Any]) -> dict[str, Any]:
    world_verifier = public_export["verification"]["verifiers"]["world"]
    return {
        "schema_version": "datalox_reference_smoke_result_v1",
        "world_id": WORLD_ID,
        "episode_id": EPISODE_ID,
        "ledger_events": len(public_export["events"]),
        "passed_checks": sum(
            check["passed"] is True for check in world_verifier["checks"]
        ),
        "overall_passed": public_export["verification"]["passed"],
        "provider_execution_counts": world_verifier["public_evidence"][
            "provider_execution_counts"
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute the installed seed-0 public reference trajectory."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:7860",
        help="Remote world service base URL.",
    )
    parser.add_argument(
        "--worlds-root",
        type=Path,
        default=Path(os.getenv("DATALOX_GATE_EXAMPLES_DIR", "/opt/datalox/worlds")),
        help="Directory containing installed world bundles.",
    )
    parser.add_argument(
        "--transport-host",
        help="Override the MCP Host header for transport allowlist testing.",
    )
    parser.add_argument(
        "--transport-origin",
        help="Send an MCP Origin header for transport allowlist testing.",
    )
    args = parser.parse_args()
    result = asyncio.run(
        _execute_reference(
            base_url=args.base_url,
            worlds_root=args.worlds_root,
            transport_host=args.transport_host,
            transport_origin=args.transport_origin,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
