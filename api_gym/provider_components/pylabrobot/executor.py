"""Sanitized, reproducible reference executions through PyLabRobot 0.2.1."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
from importlib.metadata import version
from pathlib import Path
from typing import Any, Awaitable, Callable

from api_gym.provider_components.pylabrobot.errors import PyLabRobotComponentError
from api_gym.provider_components.pylabrobot.grounding import PYLABROBOT_VERSION
from api_gym.provider_components.pylabrobot.incubation import (
    IncubatorChatterboxComponent,
)
from api_gym.provider_components.pylabrobot.liquid_handling import (
    OT2SimulatorComponent,
    _require_pinned_version,
)
from api_gym.provider_components.pylabrobot.plate_reading import (
    PlateReaderChatterboxComponent,
)

REFERENCE_SCHEMA_VERSION = "api_gym.pylabrobot_reference_sequences.v0"
_HASHED_MODULES = (
    "pylabrobot.liquid_handling.backends.opentrons_simulator",
    "pylabrobot.plate_reading.chatterbox",
    "pylabrobot.storage.chatterbox",
)


def capture_reference_sequences() -> dict[str, Any]:
    """Execute every retained sequence locally and return deterministic JSON."""
    _require_pinned_version()
    return asyncio.run(_capture_reference_sequences())


async def _capture_reference_sequences() -> dict[str, Any]:
    return {
        "schema_version": REFERENCE_SCHEMA_VERSION,
        "package": _package_evidence(),
        "hardware_execution_allowed": False,
        "network_access_required": False,
        "normalization": {
            "console": "unstructured Chatterbox stdout/stderr omitted; line count and normalized hash retained",
            "non_finite_numbers": "replaced with explicit normalized_non_finite_float objects",
            "timestamps": "replaced with <normalized-runtime-timestamp>",
        },
        "sequences": {
            "incubator_errors_v0": await _incubator_errors(),
            "incubator_success_v0": await _incubator_success(),
            "ot2_success_v0": await _ot2_success(),
            "ot2_tracker_errors_v0": await _ot2_tracker_errors(),
            "plate_reader_errors_v0": await _plate_reader_errors(),
            "plate_reader_success_v0": await _plate_reader_success(),
        },
    }


async def _ot2_success() -> dict[str, Any]:
    component = OT2SimulatorComponent()
    steps: list[dict[str, Any]] = []
    try:
        steps.append(await component.setup())
        steps.append(await component.pick_up_tip("A1"))
        steps.append(await component.aspirate("A1", 25.0))
        steps.append(await component.dispense("A1", 25.0))
        steps.append(await component.drop_tip("A1"))
        steps.append(
            {
                **_snapshot_step("pylabrobot.ot2.snapshot", component.snapshot()),
            }
        )
    finally:
        steps.append(await component.stop())
    return {"status": "completed", "steps": steps}


async def _ot2_tracker_errors() -> dict[str, Any]:
    return {
        "status": "completed",
        "cases": [
            await _capture_component_error(_ot2_no_tip_error),
            await _capture_component_error(_ot2_insufficient_source_error),
            await _capture_component_error(_ot2_tip_capacity_error),
        ],
    }


async def _ot2_no_tip_error() -> None:
    component = OT2SimulatorComponent()
    try:
        component.empty_tip_spot_for_reference("A1")
        await component.setup()
        await component.pick_up_tip("A1")
    finally:
        await component.stop()


async def _ot2_insufficient_source_error() -> None:
    component = OT2SimulatorComponent(initial_source_volume_ul=0.0)
    try:
        await component.setup()
        await component.pick_up_tip("A1")
        await component.aspirate("A1", 10.0)
    finally:
        await component.stop()


async def _ot2_tip_capacity_error() -> None:
    component = OT2SimulatorComponent(
        tip_capacity_ul=20,
        initial_source_volume_ul=100.0,
    )
    try:
        await component.setup()
        await component.pick_up_tip("A1")
        await component.aspirate("A1", 25.0)
    finally:
        await component.stop()


async def _incubator_success() -> dict[str, Any]:
    component = IncubatorChatterboxComponent()
    steps: list[dict[str, Any]] = []
    try:
        steps.append(await component.setup())
        steps.append(component.place_plate_on_tray("growth_plate"))
        steps.append(await component.open_door())
        steps.append(await component.close_door())
        steps.append(await component.set_temperature(30.0))
        steps.append(await component.get_temperature())
        steps.append(await component.start_shaking(2.0))
        steps.append(await component.stop_shaking())
        steps.append(await component.take_in_plate())
        steps.append(await component.fetch_plate("growth_plate"))
        steps.append(
            _snapshot_step("pylabrobot.incubator.snapshot", component.snapshot())
        )
    finally:
        steps.append(await component.stop())
    return {"status": "completed", "steps": steps}


async def _incubator_errors() -> dict[str, Any]:
    async def no_plate_on_tray() -> None:
        component = IncubatorChatterboxComponent()
        try:
            await component.setup()
            await component.take_in_plate()
        finally:
            await component.stop()

    return {
        "status": "completed",
        "cases": [await _capture_component_error(no_plate_on_tray)],
    }


async def _plate_reader_success() -> dict[str, Any]:
    component = PlateReaderChatterboxComponent()
    steps: list[dict[str, Any]] = []
    try:
        steps.append(await component.setup())
        steps.append(await component.open())
        steps.append(component.place_plate("growth_plate"))
        steps.append(await component.close())
        steps.append(
            await component.read_absorbance(
                wavelength_nm=600,
                wells=("A1", "B1"),
            )
        )
        steps.append(
            await component.read_fluorescence(
                excitation_wavelength_nm=485,
                emission_wavelength_nm=528,
                focal_height_mm=7.5,
                wells=("A1", "B1"),
            )
        )
        steps.append(
            await component.read_luminescence(
                focal_height_mm=7.5,
                wells=("A1", "B1"),
            )
        )
        steps.append(
            _snapshot_step("pylabrobot.plate_reader.snapshot", component.snapshot())
        )
    finally:
        steps.append(await component.stop())
    return {"status": "completed", "steps": steps}


async def _plate_reader_errors() -> dict[str, Any]:
    async def no_plate() -> None:
        component = PlateReaderChatterboxComponent()
        try:
            await component.setup()
            await component.read_absorbance(
                wavelength_nm=600,
                wells=("A1",),
            )
        finally:
            await component.stop()

    return {
        "status": "completed",
        "cases": [await _capture_component_error(no_plate)],
    }


async def _capture_component_error(
    call: Callable[[], Awaitable[None]],
) -> dict[str, Any]:
    try:
        await call()
    except PyLabRobotComponentError as error:
        return {"status": "error", "error": error.to_dict()}
    raise AssertionError("reference error sequence unexpectedly succeeded")


def _snapshot_step(operation_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    from api_gym.provider_components.pylabrobot.grounding import (
        operation_observation,
    )

    return operation_observation(operation_id, result=snapshot)


def _package_evidence() -> dict[str, Any]:
    return {
        "distribution": "pylabrobot",
        "version": version("pylabrobot"),
        "module_sha256": {
            module_name: _module_sha256(module_name)
            for module_name in _HASHED_MODULES
        },
        "expected_version": PYLABROBOT_VERSION,
    }


def _module_sha256(module_name: str) -> str:
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.origin is None:
        raise RuntimeError(f"cannot locate installed PyLabRobot module: {module_name}")
    return hashlib.sha256(Path(spec.origin).read_bytes()).hexdigest()
