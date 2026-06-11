"""World session lifecycle helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api_gym.agent_harness import (
    AGENT_TASK_NAME,
    AGENT_TOOL_TRACE_NAME,
    build_agent_task_package,
    create_mcp_handler,
    write_agent_task_package,
)
from api_gym.exports.run_export import write_run_export
from api_gym.worlds.registry import get_runtime_for_run, get_world_runtime, read_run_metadata

SESSION_MANIFEST_NAME = "session_manifest.json"
SESSION_FINALIZATION_NAME = "session_finalization.json"
RUN_EXPORT_NAME = "run_export.json"


def create_world_session(*, world: str, scenario: str, seed: int, out_dir: Path) -> dict[str, Any]:
    """Create a sampled run and write a fool-proof session manifest."""
    runtime = get_world_runtime(world)
    if scenario not in runtime.scenarios:
        supported = ", ".join(sorted(runtime.scenarios))
        raise ValueError(f"Unsupported scenario '{scenario}'. Supported: {supported}")

    episode = runtime.sample_episode(scenario=scenario, seed=seed, out_dir=out_dir)
    write_agent_task_package(episode.run_dir, episode.run_dir / AGENT_TASK_NAME)
    manifest = build_session_manifest(episode.run_dir)
    _write_json(episode.run_dir / SESSION_MANIFEST_NAME, manifest)
    return manifest


def build_session_manifest(run_dir: Path) -> dict[str, Any]:
    """Build the stable handoff object consumed by external agent environments."""
    run_dir = run_dir.resolve()
    runtime = get_runtime_for_run(run_dir)
    metadata = read_run_metadata(run_dir)
    task_package = build_agent_task_package(run_dir)
    task_package_path = run_dir / AGENT_TASK_NAME
    export_path = run_dir / RUN_EXPORT_NAME
    expected_tools = _tool_names(runtime.tool_definitions)
    mode = str(metadata.get("mode", "runtime"))
    return {
        "schema_version": "api_gym.world_session.v0",
        "session_id": run_dir.name,
        "world": metadata["world"],
        "world_id": metadata["world_id"],
        "scenario": metadata["scenario"],
        "seed": metadata["seed"],
        "mode": mode,
        "run_dir": str(run_dir),
        "task": task_package["task"],
        "task_path": str(run_dir / runtime.task_name),
        "task_instructions": task_package["agent_facing_instructions"],
        "task_package": str(task_package_path),
        "mcp": task_package["recommended_mcp_config"],
        "expected_tools": expected_tools,
        "integration_instructions": [
            "Load the task_package and MCP config from this manifest.",
            "Attach the MCP server before running the agent.",
            "Run the Datalox tool catalog check, then prove the host agent-visible tool layer contains expected_tools before rollout.",
            "Do not expose state.sqlite or hidden verifier state to the agent.",
            "After the agent stops, call the finalize command and consume verifier_result plus run_export.",
        ],
        "preflight": {
            "required": True,
            "datalox_tool_catalog_command": ["api-gym", "session", "check-tools", "--run", str(run_dir)],
            "host_requirement": "The host must compare its own agent-visible tool registry against expected_tools before rollout.",
            "proves_agent_visible_tools": False,
        },
        "commands": {
            "check_tools": ["api-gym", "session", "check-tools", "--run", str(run_dir)],
            "verify": ["api-gym", "verify", "--run", str(run_dir)],
            "export": ["api-gym", "export", "--run", str(run_dir), "--out", str(export_path)],
            "finalize": ["api-gym", "session", "finalize", "--run", str(run_dir)],
        },
        "artifacts": {
            "root": str(run_dir),
            "run_metadata": str(run_dir / runtime.run_metadata_name),
            "state_db": str(runtime.resolve_state_db_path(run_dir)),
            "task": str(run_dir / runtime.task_name),
            "task_package": str(task_package_path),
            "tool_trace": str(run_dir / AGENT_TOOL_TRACE_NAME),
            "session_manifest": str(run_dir / SESSION_MANIFEST_NAME),
            "run_export": str(export_path),
            "finalization": str(run_dir / SESSION_FINALIZATION_NAME),
        },
    }


def check_session_tools(run_dir: Path) -> dict[str, Any]:
    """Verify the Datalox MCP server lists the tools declared by the session."""
    run_dir = run_dir.resolve()
    runtime = get_runtime_for_run(run_dir)
    expected_tools = _tool_names(runtime.tool_definitions)
    handler = create_mcp_handler(run_dir)
    listed = handler.handle_message({"jsonrpc": "2.0", "id": "check-tools", "method": "tools/list"})
    if listed is None:
        raise ValueError("MCP tools/list returned no response.")
    tool_names = sorted(tool["name"] for tool in listed["result"]["tools"])
    missing = sorted(set(expected_tools) - set(tool_names))
    unexpected = sorted(set(tool_names) - set(expected_tools))
    return {
        "ok": not missing and not unexpected,
        "world": runtime.world,
        "expected_tools": expected_tools,
        "listed_tools": tool_names,
        "missing_tools": missing,
        "unexpected_tools": unexpected,
    }


def finalize_world_session(run_dir: Path) -> dict[str, Any]:
    """Run verifier, export evidence, and write finalization result."""
    run_dir = run_dir.resolve()
    runtime = get_runtime_for_run(run_dir)
    metadata = read_run_metadata(run_dir)
    verifier_result = runtime.verify_run(run_dir).to_dict()
    export_path = run_dir / RUN_EXPORT_NAME
    export_payload = write_run_export(run_dir, export_path)
    result = {
        "schema_version": "api_gym.world_session_finalization.v0",
        "ok": bool(verifier_result["ok"]),
        "world": metadata["world"],
        "world_id": metadata["world_id"],
        "scenario": metadata["scenario"],
        "seed": metadata["seed"],
        "run_dir": str(run_dir),
        "verifier_result": verifier_result,
        "export_path": str(export_path),
        "export": export_payload,
    }
    _write_json(run_dir / SESSION_FINALIZATION_NAME, result)
    return result


def _tool_names(tool_definitions: list[dict[str, Any]]) -> list[str]:
    return sorted(str(tool["function"]["name"]) for tool in tool_definitions)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
