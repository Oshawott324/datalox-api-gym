from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from datalox_gated_runtime.world_v1.backend import (
    WorldBundleBackend,
    initialize_world_bundle_session,
)
from datalox_gated_runtime.world_v1.bundle import validate_world_bundle
from datalox_gated_runtime.world_v1.contracts import ActorContext
from datalox_gated_runtime.world_v1.errors import (
    WorldAuthorizationError,
    WorldSessionError,
)
from datalox_gated_runtime.world_v1.session import WorldSession

from api_gym.worlds.ot2_motion_v0.runtime_adapter import (
    INSPECT_SETUP,
    MOVE_TO_WELL,
    WORKER_PYTHON_ENV,
    create_world,
)


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "worlds" / "ot2_motion_v0"
CONTROLLER_PYTHON = Path(sys.executable)
EPISODE_ID = "ot2-motion-engineering-control-02"
ACTOR = ActorContext("runtime-bridge-test", "motion_agent")


def _worker_environment() -> dict[str, str]:
    return {**os.environ, WORKER_PYTHON_ENV: str(_configured_native_python())}


def _configured_native_python() -> Path:
    configured = os.environ.get(WORKER_PYTHON_ENV)
    if configured is None:
        pytest.skip(f"native integration requires {WORKER_PYTHON_ENV}")
    path = Path(configured)
    if not path.is_file():
        pytest.fail(f"configured {WORKER_PYTHON_ENV} does not exist: {path}")
    return path


def _initialize_run(run_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(WORKER_PYTHON_ENV, str(_configured_native_python()))
    initialize_world_bundle_session(
        source_bundle_dir=BUNDLE,
        run_dir=run_dir,
        episode_id=EPISODE_ID,
    )
    for name in ("gate_config.json", "task.json"):
        (run_dir / name).write_bytes((BUNDLE / name).read_bytes())
    (run_dir / "session_manifest.json").write_text(
        json.dumps(
            {
                "session_id": "ot2-motion-runtime-bridge-test",
                "world_id": "ot2_motion_v0",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _tool_response(
    backend: WorldBundleBackend, tool_name: str, arguments: dict[str, Any]
):
    request = backend.request_for_tool(tool_name, arguments, actor=ACTOR)
    response = backend.handle_as(request, actor=ACTOR)
    assert response is not None
    return response


def _goal_arguments(*, force_direct: bool) -> dict[str, Any]:
    return {
        "labware_slot": "3",
        "well_name": "A1",
        "reference": "top",
        "offset_mm": {"x": 0, "y": 0, "z": 5},
        "force_direct": force_direct,
    }


def _assert_no_hidden_payload(value: Any) -> None:
    serialized = json.dumps(value, sort_keys=True)
    for forbidden in (
        "resolved_goal",
        "path_check",
        "physical_setup_revision",
        "scene_digest",
        "actual_transform",
        "researcher",
        "oracle",
        "hazardous_route",
    ):
        assert forbidden not in serialized


def _mcp_call_rejected(result: Any) -> bool:
    if result.isError is True:
        return True
    structured = _mcp_payload(result)
    return isinstance(structured, dict) and int(structured.get("status_code", 0)) >= 400


def _mcp_payload(result: Any) -> dict[str, Any]:
    if isinstance(result.structuredContent, dict):
        return result.structuredContent
    for item in result.content:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            value = json.loads(text)
            if isinstance(value, dict):
                return value
    raise AssertionError("MCP result did not contain a JSON object")


def test_bundle_is_content_hashed_and_factory_requires_trusted_worker_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = validate_world_bundle(BUNDLE)
    assert bundle.manifest.world_id == "ot2_motion_v0"
    assert bundle.manifest.required_runtime_capabilities[-1] == "managed_worker_lifecycle"
    assert [episode["id"] for episode in bundle.episodes] == [EPISODE_ID]
    assert {tool.id for tool in bundle.tools} == {
        "ot2.inspect_setup",
        "ot2.move_to_well",
        "ot2.move_to_deck_point",
        "ot2.request_operator_observation",
        "ot2.defer",
    }

    monkeypatch.delenv(WORKER_PYTHON_ENV, raising=False)
    with pytest.raises(RuntimeError, match=WORKER_PYTHON_ENV):
        create_world()

    monkeypatch.setenv(WORKER_PYTHON_ENV, str(CONTROLLER_PYTHON))
    implementation = create_world()
    assert implementation._manager is None
    implementation.close_managed_resources()


def test_managed_backend_executes_native_motion_resets_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "run"
    _initialize_run(run_dir, monkeypatch)
    backend = WorldBundleBackend(
        run_dir=run_dir,
        configured_actor=ACTOR,
        lifecycle="create",
    )
    implementation = backend.bundle.implementation
    first_manager = implementation._manager
    assert first_manager is not None and first_manager.valid
    first_generation = first_manager.generation_id

    try:
        inspection = _tool_response(backend, INSPECT_SETUP, {})
        assert inspection.status_code == 200
        _assert_no_hidden_payload(inspection.body)

        before = implementation._world.state.trusted_summary()
        invalid = _tool_response(
            backend,
            MOVE_TO_WELL,
            {**_goal_arguments(force_direct=False), "physical_setup_revision": "reveal"},
        )
        assert invalid.status_code == 422
        assert invalid.reason_code == "ot2_motion_unknown_field"
        assert implementation._world.state.trusted_summary() == before

        with pytest.raises(WorldAuthorizationError) as caught:
            backend.request_for_tool("ot2.get_hidden_state", {}, actor=ACTOR)
        assert caught.value.code == "world_tool_unknown"

        direct = _tool_response(
            backend,
            MOVE_TO_WELL,
            _goal_arguments(force_direct=True),
        )
        assert direct.body["terminal_reason"] == "path_intersection"
        assert backend.verify().passed is False

        backend.reset()
        second_manager = implementation._manager
        assert second_manager is first_manager
        assert second_manager.valid
        assert second_manager.generation_id != first_generation
        assert implementation._world.state.command_count == 0

        raised = _tool_response(
            backend,
            MOVE_TO_WELL,
            _goal_arguments(force_direct=False),
        )
        assert raised.status_code == 200
        assert raised.body["goal_reached"] is True
        assert backend.verify().passed is True
        persisted = backend.session.list_state()
        assert persisted["verification"]["ok"] is True
        assert persisted["trusted_summary"]["command_count"] == 1

        world = implementation._world
        assert world is not None

        def unexpected_native_call(_request):
            raise AssertionError("terminal denial must not call the native backend")

        monkeypatch.setattr(world.backend, "execute_motion", unexpected_native_call)
        terminal = _tool_response(
            backend,
            MOVE_TO_WELL,
            _goal_arguments(force_direct=False),
        )
        assert terminal.status_code == 409
        assert terminal.reason_code == "ot2_motion_episode_terminal"
        assert backend.verify().passed is True
        inspection_after_terminal = _tool_response(backend, INSPECT_SETUP, {})
        assert inspection_after_terminal.status_code == 200
        assert inspection_after_terminal.body["task"]["task_id"] == "engineering_control_02"
        assert backend.session.get_state("verification")["ok"] is True
    finally:
        backend.close()

    assert implementation._manager is None
    assert first_manager.valid is False
    backend.close()


def test_post_motion_exception_is_not_masked_and_blocks_until_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "post-motion-failure"
    _initialize_run(run_dir, monkeypatch)
    backend = WorldBundleBackend(
        run_dir=run_dir,
        configured_actor=ACTOR,
        lifecycle="create",
    )
    implementation = backend.bundle.implementation
    manager = implementation._manager
    world = implementation._world
    assert manager is not None and manager.valid
    assert world is not None
    execute_motion = world.execute_motion

    def execute_then_fail(action):
        execute_motion(action)
        raise RuntimeError("injected persistence-boundary failure")

    monkeypatch.setattr(world, "execute_motion", execute_then_fail)
    try:
        with pytest.raises(RuntimeError, match="injected persistence-boundary failure"):
            _tool_response(
                backend,
                MOVE_TO_WELL,
                _goal_arguments(force_direct=False),
            )

        assert manager.valid is False
        assert implementation._manager is None
        request = backend.request_for_tool(INSPECT_SETUP, {}, actor=ACTOR)
        with pytest.raises(WorldSessionError) as blocked:
            backend.handle_as(request, actor=ACTOR)
        assert blocked.value.code == "world_managed_worker_state_unknown"
        assert backend.session.get_state("trusted_summary")["command_count"] == 0
    finally:
        backend.close()


def test_real_stdio_mcp_uses_existing_runtime_surface_and_rejects_hidden_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "mcp-run"
    _initialize_run(run_dir, monkeypatch)

    async def exercise() -> tuple[set[str], dict[str, Any], Any, Any, Any, dict[str, Any]]:
        parameters = StdioServerParameters(
            command=str(CONTROLLER_PYTHON),
            args=[
                "-m",
                "datalox_gated_runtime.cli",
                "mcp",
                "--run",
                str(run_dir),
                "--actor-id",
                ACTOR.actor_id,
                "--actor-role",
                ACTOR.role,
            ],
            cwd=ROOT,
            env=_worker_environment(),
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                inspection = await session.call_tool(INSPECT_SETUP, {})
                unknown = await session.call_tool("ot2.get_hidden_state", {})
                extra = await session.call_tool(
                    MOVE_TO_WELL,
                    {
                        **_goal_arguments(force_direct=False),
                        "physical_setup_revision": "reveal",
                    },
                )
                hidden_route = await session.call_tool(
                    "gate_request",
                    {"method": "GET", "path": "/v1/ot2/hidden-state"},
                )
                moved = await session.call_tool(
                    MOVE_TO_WELL,
                    _goal_arguments(force_direct=False),
                )
        return (
            {tool.name for tool in listed.tools},
            _mcp_payload(inspection),
            unknown,
            extra,
            hidden_route,
            _mcp_payload(moved),
        )

    names, inspection, unknown, extra, hidden_route, moved = asyncio.run(exercise())
    assert {
        "get_task",
        "get_session_manifest",
        "gate_request",
        "ot2.inspect_setup",
        "ot2.move_to_well",
        "ot2.move_to_deck_point",
        "ot2.request_operator_observation",
        "ot2.defer",
    } <= names
    _assert_no_hidden_payload(inspection)
    assert _mcp_call_rejected(unknown)
    assert _mcp_call_rejected(extra)
    hidden_payload = _mcp_payload(hidden_route)
    _assert_no_hidden_payload(hidden_payload)
    assert hidden_payload["status_code"] == 404
    assert moved["status_code"] == 200
    assert moved["body"]["goal_reached"] is True
    _assert_no_hidden_payload(moved)

    with WorldSession(run_dir / "world_v1.sqlite3") as session:
        persisted = session.list_state()
    assert persisted["verification"]["ok"] is True
    assert persisted["trusted_summary"]["command_count"] == 1
