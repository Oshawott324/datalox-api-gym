"""Authentic PyLabRobot visual replay capture for one STAR run.

The recorder consumes commands emitted by the pinned upstream Visualizer. It
does not translate API Gym semantic events into guessed visual state.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Coroutine, Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from pylabrobot.visualizer import Visualizer

from api_gym.worlds.pylabrobot_star_v0.state import get_state

PUBLIC_REPLAY_PROJECTION_NAME = "public_replay_projection.json"
WORLD_REPLAY_PROJECTION_SCHEMA = "datalox_world_replay_projection_v1"
PYLABROBOT_RENDERER_ID = "pylabrobot_visualizer"
PYLABROBOT_CAPTURE_PACKAGE_VERSION = "0.2.1"
PYLABROBOT_VIEWER_PACKAGE_VERSION = "0.2.2"
PYLABROBOT_PROTOCOL_VERSION = "0.1.0"

_SERIAL_DILUTION_TRANSFERS = (
    ("source_plate:A1", "assay_plate:B1", "tip_rack_01:A1"),
    ("assay_plate:B1", "assay_plate:B2", "tip_rack_01:A2"),
    ("assay_plate:B2", "assay_plate:B3", "tip_rack_01:A3"),
    ("assay_plate:B3", "assay_plate:B4", "tip_rack_01:A4"),
    ("assay_plate:B4", "assay_plate:B5", "tip_rack_01:A5"),
)


class STARReplayRecorder(Visualizer):
    """Record upstream Visualizer commands without opening a server or browser."""

    def __init__(self, *, liquid_handler: Any, run_dir: Path) -> None:
        _require_pylabrobot_version()
        super().__init__(
            resource=liquid_handler,
            open_browser=False,
            show_machine_tools_at_start=True,
        )
        self._run_dir = run_dir.resolve()
        self._commands: list[dict[str, Any]] = []
        self._commands_lock = threading.Lock()
        self._closed = False
        self._replay_loop = asyncio.new_event_loop()
        self._loop = self._replay_loop
        self._loop_ready = threading.Event()
        self._loop_thread = threading.Thread(
            target=self._run_loop,
            name=f"pylabrobot-replay-{self._run_dir.name}",
            daemon=True,
        )
        self._loop_thread.start()
        if not self._loop_ready.wait(timeout=5):
            raise RuntimeError("PyLabRobot replay loop did not start")
        self._submit(self._send_resources_and_state())
        self._initialization = self._drain_commands()
        self._steps: list[dict[str, Any]] = []
        self._write_projection()

    async def send_command(
        self,
        event: str,
        data: dict[str, Any] | None = None,
        wait_for_response: bool = True,
    ) -> None:
        serialized, _ = self._assemble_command(event, data or {})
        command = json.loads(serialized)
        with self._commands_lock:
            self._commands.append(
                {"event": command["event"], "data": command["data"]}
            )

    def record_completed_tool(
        self,
        *,
        operation_id: str,
        arguments: Mapping[str, Any],
        simulated_at_seconds: float,
    ) -> None:
        """Flush renderer events caused by one completed API Gym tool call."""

        self._submit(self._barrier())
        commands = self._drain_commands()
        if not commands:
            return
        self._steps.append(
            {
                "sequence": len(self._steps) + 1,
                "simulated_at": f"T+{simulated_at_seconds:.3f}s",
                "operation_id": operation_id,
                "label": _operation_label(operation_id, arguments),
                "display_duration_ms": 900,
                "commands": commands,
            }
        )
        self._write_projection()

    def projection(self) -> dict[str, Any]:
        return {
            "schema_version": WORLD_REPLAY_PROJECTION_SCHEMA,
            "renderer": {
                "id": PYLABROBOT_RENDERER_ID,
                "capture_package_version": PYLABROBOT_CAPTURE_PACKAGE_VERSION,
                "viewer_package_version": PYLABROBOT_VIEWER_PACKAGE_VERSION,
                "protocol_version": PYLABROBOT_PROTOCOL_VERSION,
            },
            "initialization": list(self._initialization),
            "steps": list(self._steps),
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._replay_loop.call_soon_threadsafe(self._replay_loop.stop)
        self._loop_thread.join(timeout=5)
        if self._loop_thread.is_alive():
            raise RuntimeError("PyLabRobot replay loop did not stop")
        self._replay_loop.close()

    def _handle_state_update_callback(self, resource: Any) -> None:
        if not self._closed:
            super()._handle_state_update_callback(resource)

    def _handle_resource_assigned_callback(self, resource: Any) -> None:
        if not self._closed:
            super()._handle_resource_assigned_callback(resource)

    def _handle_resource_unassigned_callback(self, resource: Any) -> None:
        if not self._closed:
            super()._handle_resource_unassigned_callback(resource)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._replay_loop)
        self._loop_ready.set()
        self._replay_loop.run_forever()

    def _submit(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        if self._closed:
            coroutine.close()
            raise RuntimeError("PyLabRobot replay recorder is closed")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._replay_loop)
        return future.result(timeout=10)

    async def _barrier(self) -> None:
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    def _drain_commands(self) -> list[dict[str, Any]]:
        with self._commands_lock:
            commands = self._commands
            self._commands = []
        return commands

    def _write_projection(self) -> None:
        destination = self._run_dir / PUBLIC_REPLAY_PROJECTION_NAME
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(self.projection(), indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)


_recorders: dict[str, STARReplayRecorder] = {}


def start_public_replay(run_dir: Path) -> STARReplayRecorder:
    """Attach one recorder to an already sampled STAR run."""

    key = str(run_dir.resolve())
    if key in _recorders:
        raise ValueError(f"Public replay is already active for {run_dir}")
    lab_state = get_state(run_dir)
    if lab_state.liquid_handler is None:
        raise ValueError("STAR run has no liquid handler")
    recorder = STARReplayRecorder(
        liquid_handler=lab_state.liquid_handler,
        run_dir=run_dir,
    )
    _recorders[key] = recorder
    return recorder


def get_public_replay(run_dir: Path) -> STARReplayRecorder | None:
    return _recorders.get(str(run_dir.resolve()))


def stop_public_replay(run_dir: Path) -> None:
    recorder = _recorders.pop(str(run_dir.resolve()), None)
    if recorder is not None:
        recorder.close()


def read_public_replay_projection(run_dir: Path) -> dict[str, Any]:
    path = run_dir.resolve() / PUBLIC_REPLAY_PROJECTION_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{PUBLIC_REPLAY_PROJECTION_NAME} must contain an object")
    return payload


def run_serial_dilution_qc_replay_case(run_dir: Path) -> list[dict[str, Any]]:
    """Execute the existing STAR serial-dilution task through normal tools."""

    run_dir = run_dir.resolve()
    if get_public_replay(run_dir) is None:
        raise ValueError("Public replay must be active before running the replay case")

    task_path = run_dir / "task.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    if task.get("world") != "pylabrobot_star_v0" or task.get("scenario") != "serial_dilution_qc":
        raise ValueError(
            "Serial-dilution replay requires a pylabrobot_star_v0 "
            "serial_dilution_qc run"
        )

    operations: list[dict[str, Any]] = []
    for source, target, tip_ref in _SERIAL_DILUTION_TRANSFERS:
        _run_required_tool(
            run_dir,
            operations,
            "pick_up_tips",
            {"tip_refs": [tip_ref], "channels": [0]},
        )
        _run_required_tool(
            run_dir,
            operations,
            "aspirate",
            {"source": source, "volume_ul": 50, "channel": 0},
        )
        _run_required_tool(
            run_dir,
            operations,
            "dispense",
            {"target": target, "volume_ul": 50, "channel": 0},
        )
        _run_required_tool(
            run_dir,
            operations,
            "discard_tips",
            {"channels": [0]},
        )

    _run_required_tool(
        run_dir,
        operations,
        "read_absorbance",
        {"plate_id": "source_plate", "wavelength_nm": 600, "wells": ["A1"]},
    )
    assay_readout = _run_required_tool(
        run_dir,
        operations,
        "read_absorbance",
        {
            "plate_id": "assay_plate",
            "wavelength_nm": 600,
            "wells": ["B1", "B2", "B3", "B4", "B5"],
        },
    )
    _run_required_tool(
        run_dir,
        operations,
        "submit_protocol",
        {
            "decision": "continue",
            "evidence_readout_id": assay_readout["data"]["readout_id"],
            "target_well": "assay_plate:B5",
            "rationale": "OD600 was recorded after all five serial-dilution transfers.",
        },
    )
    return operations


def _run_required_tool(
    run_dir: Path,
    operations: list[dict[str, Any]],
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    from api_gym.worlds.pylabrobot_star_v0.tools import dispatch_tool

    result = dispatch_tool(run_dir, name=name, arguments=arguments)
    operations.append({"name": name, "arguments": arguments, "result": result})
    if not result.get("ok"):
        raise RuntimeError(f"{name} failed during serial-dilution replay: {result}")
    return result


def _operation_label(operation_id: str, arguments: Mapping[str, Any]) -> str:
    if operation_id == "pick_up_tips":
        count = len(arguments.get("tip_refs", []))
        return f"Pick up {count} clean tip{'s' if count != 1 else ''}"
    if operation_id == "aspirate":
        return f"Aspirate {_volume(arguments)} from {arguments.get('source', 'source')}"
    if operation_id == "dispense":
        return f"Dispense {_volume(arguments)} into {arguments.get('target', 'target')}"
    if operation_id in {"discard_tips", "return_tips", "drop_tips"}:
        return operation_id.replace("_", " ").capitalize()
    if operation_id in {"move_plate", "move_resource", "move_lid"}:
        resource = arguments.get("resource_name", arguments.get("plate_name", "resource"))
        return f"Move {resource}"
    return operation_id.replace("_", " ").capitalize()


def _volume(arguments: Mapping[str, Any]) -> str:
    value = arguments.get("volume_ul", arguments.get("vol", "liquid"))
    return f"{value:g} uL" if isinstance(value, (int, float)) else str(value)


def _require_pylabrobot_version() -> None:
    try:
        installed = version("pylabrobot")
    except PackageNotFoundError as exc:
        raise RuntimeError("PyLabRobot is not installed") from exc
    if installed != PYLABROBOT_CAPTURE_PACKAGE_VERSION:
        raise RuntimeError(
            "PyLabRobot replay version mismatch: "
            f"expected {PYLABROBOT_CAPTURE_PACKAGE_VERSION}, installed {installed}"
        )
