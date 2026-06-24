"""Runtime registry for API Gym worlds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class WorldRuntime:
    world: str
    world_id: str
    scenarios: set[str]
    sample_episode: Callable[..., Any]
    verify_run: Callable[[Path], Any]
    tool_definitions: list[dict[str, Any]]
    dispatch_tool: Callable[..., dict[str, Any]]
    resolve_state_db_path: Callable[[Path], Path]
    run_metadata_name: str
    task_name: str
    mcp_server_name: str
    mcp_server_title: str


SUPPORTED_WORLDS = ("billing_support_v0", "unitelabs_plate_qc_v0", "pylabrobot_lab_v0")


def get_world_runtime(world: str) -> WorldRuntime:
    """Return the runtime adapter for a world id."""
    if world == "billing_support_v0":
        return _runtime_from_package(
            world=world,
            package="api_gym.worlds.billing_support_v0",
            mcp_server_title="API Gym Billing Support",
        )
    if world == "unitelabs_plate_qc_v0":
        return _runtime_from_package(
            world=world,
            package="api_gym.worlds.unitelabs_plate_qc_v0",
            mcp_server_title="API Gym UniteLabs Plate QC",
        )
    if world == "pylabrobot_lab_v0":
        return _runtime_from_package(
            world=world,
            package="api_gym.worlds.pylabrobot_lab_v0",
            mcp_server_title="API Gym PyLabRobot Lab",
        )
    supported = ", ".join(SUPPORTED_WORLDS)
    raise ValueError(f"Unsupported world '{world}'. Supported: {supported}")


def get_runtime_for_run(run_dir: Path) -> WorldRuntime:
    """Load run metadata and return the runtime adapter for that run."""
    metadata = read_run_metadata(run_dir)
    world = metadata.get("world")
    if not isinstance(world, str) or not world:
        raise ValueError("run.json must contain a non-empty world string.")
    return get_world_runtime(world)


def read_run_metadata(run_dir: Path) -> dict[str, Any]:
    """Read a run.json object from a sampled run directory."""
    metadata_path = run_dir.resolve() / "run.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing run.json in run directory: {run_dir.resolve()}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("run.json must contain a JSON object.")
    return metadata


def _runtime_from_package(*, world: str, package: str, mcp_server_title: str) -> WorldRuntime:
    sampler = import_module(f"{package}.sampler")
    verifier = import_module(f"{package}.verifier")
    tools = import_module(f"{package}.tools")
    state = import_module(f"{package}.state")

    world_id = str(sampler.WORLD_ID)
    return WorldRuntime(
        world=world,
        world_id=world_id,
        scenarios=set(sampler.SCENARIOS),
        sample_episode=sampler.sample_episode,
        verify_run=verifier.verify_run,
        tool_definitions=tools.TOOL_DEFINITIONS,
        dispatch_tool=tools.dispatch_tool,
        resolve_state_db_path=state.resolve_state_db_path,
        run_metadata_name=str(state.RUN_METADATA_NAME),
        task_name=str(state.TASK_NAME),
        mcp_server_name=f"api-gym-{world_id}",
        mcp_server_title=mcp_server_title,
    )
