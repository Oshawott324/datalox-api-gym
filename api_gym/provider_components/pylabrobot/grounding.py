"""Grounding declarations for the bounded PyLabRobot component."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

PYLABROBOT_VERSION = "0.2.1"

GroundingLevel = Literal[
    "simulator_executed",
    "chatterbox_executed",
    "provider_interface_only",
    "captured_projection",
    "benchmark_defined",
    "unsupported",
]

GROUNDING_LEVELS = frozenset(
    {
        "simulator_executed",
        "chatterbox_executed",
        "provider_interface_only",
        "captured_projection",
        "benchmark_defined",
        "unsupported",
    }
)


@dataclass(frozen=True)
class OperationGrounding:
    operation_id: str
    level: GroundingLevel
    implementation: str
    summary: str


_DECLARATIONS = (
    OperationGrounding(
        "pylabrobot.ot2.setup",
        "simulator_executed",
        "pylabrobot.liquid_handling.LiquidHandler.setup",
        "Set up a LiquidHandler using OpentronsOT2Simulator.",
    ),
    OperationGrounding(
        "pylabrobot.ot2.pick_up_tip",
        "simulator_executed",
        "pylabrobot.liquid_handling.LiquidHandler.pick_up_tips",
        "Pick up one tracked tip through the OT-2 simulator backend.",
    ),
    OperationGrounding(
        "pylabrobot.ot2.aspirate",
        "simulator_executed",
        "pylabrobot.liquid_handling.LiquidHandler.aspirate",
        "Aspirate tracked liquid through the OT-2 simulator backend.",
    ),
    OperationGrounding(
        "pylabrobot.ot2.dispense",
        "simulator_executed",
        "pylabrobot.liquid_handling.LiquidHandler.dispense",
        "Dispense tracked liquid through the OT-2 simulator backend.",
    ),
    OperationGrounding(
        "pylabrobot.ot2.drop_tip",
        "simulator_executed",
        "pylabrobot.liquid_handling.LiquidHandler.drop_tips",
        "Drop one tracked tip through the OT-2 simulator backend.",
    ),
    OperationGrounding(
        "pylabrobot.ot2.stop",
        "simulator_executed",
        "pylabrobot.liquid_handling.LiquidHandler.stop",
        "Stop the local OT-2 simulator-backed liquid handler.",
    ),
    OperationGrounding(
        "pylabrobot.ot2.snapshot",
        "captured_projection",
        "api_gym.provider_components.pylabrobot.snapshots.ot2_snapshot",
        "Normalize selected PyLabRobot deck and tracker state as JSON.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.setup",
        "chatterbox_executed",
        "pylabrobot.storage.Incubator.setup",
        "Set up an Incubator using IncubatorChatterboxBackend.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.place_plate_on_tray",
        "provider_interface_only",
        "pylabrobot.resources.PlateHolder.assign_child_resource",
        "Assign a plate to the PyLabRobot incubator loading tray.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.open_door",
        "chatterbox_executed",
        "pylabrobot.storage.Incubator.open_door",
        "Execute the Chatterbox incubator door-open method.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.close_door",
        "chatterbox_executed",
        "pylabrobot.storage.Incubator.close_door",
        "Execute the Chatterbox incubator door-close method.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.set_temperature",
        "chatterbox_executed",
        "pylabrobot.storage.Incubator.set_temperature",
        "Execute the Chatterbox temperature-set method.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.get_temperature",
        "chatterbox_executed",
        "pylabrobot.storage.Incubator.get_temperature",
        "Read the Chatterbox backend's fixed dummy temperature.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.start_shaking",
        "chatterbox_executed",
        "pylabrobot.storage.Incubator.start_shaking",
        "Execute the Chatterbox start-shaking method.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.stop_shaking",
        "chatterbox_executed",
        "pylabrobot.storage.Incubator.stop_shaking",
        "Execute the Chatterbox stop-shaking method.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.take_in_plate",
        "chatterbox_executed",
        "pylabrobot.storage.Incubator.take_in_plate",
        "Move a plate from the loading tray to a PyLabRobot rack site.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.fetch_plate",
        "chatterbox_executed",
        "pylabrobot.storage.Incubator.fetch_plate_to_loading_tray",
        "Move a named plate from a rack site to the loading tray.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.stop",
        "chatterbox_executed",
        "pylabrobot.storage.Incubator.stop",
        "Stop the Chatterbox incubator.",
    ),
    OperationGrounding(
        "pylabrobot.incubator.snapshot",
        "captured_projection",
        "api_gym.provider_components.pylabrobot.snapshots.incubator_snapshot",
        "Normalize selected PyLabRobot incubator resource state as JSON.",
    ),
    OperationGrounding(
        "pylabrobot.plate_reader.setup",
        "chatterbox_executed",
        "pylabrobot.plate_reading.PlateReader.setup",
        "Set up a PlateReader using PlateReaderChatterboxBackend.",
    ),
    OperationGrounding(
        "pylabrobot.plate_reader.place_plate",
        "provider_interface_only",
        "pylabrobot.plate_reading.PlateReader.assign_child_resource",
        "Assign a plate to the PyLabRobot plate-reader resource holder.",
    ),
    OperationGrounding(
        "pylabrobot.plate_reader.open",
        "chatterbox_executed",
        "pylabrobot.plate_reading.PlateReader.open",
        "Execute the Chatterbox plate-reader open method.",
    ),
    OperationGrounding(
        "pylabrobot.plate_reader.close",
        "chatterbox_executed",
        "pylabrobot.plate_reading.PlateReader.close",
        "Execute the Chatterbox plate-reader close method.",
    ),
    OperationGrounding(
        "pylabrobot.plate_reader.read_absorbance",
        "chatterbox_executed",
        "pylabrobot.plate_reading.PlateReader.read_absorbance",
        "Execute a Chatterbox absorbance read for selected wells.",
    ),
    OperationGrounding(
        "pylabrobot.plate_reader.read_fluorescence",
        "chatterbox_executed",
        "pylabrobot.plate_reading.PlateReader.read_fluorescence",
        "Execute a Chatterbox fluorescence read for selected wells.",
    ),
    OperationGrounding(
        "pylabrobot.plate_reader.read_luminescence",
        "chatterbox_executed",
        "pylabrobot.plate_reading.PlateReader.read_luminescence",
        "Execute a Chatterbox luminescence read for selected wells.",
    ),
    OperationGrounding(
        "pylabrobot.plate_reader.stop",
        "chatterbox_executed",
        "pylabrobot.plate_reading.PlateReader.stop",
        "Stop the Chatterbox plate reader.",
    ),
    OperationGrounding(
        "pylabrobot.plate_reader.snapshot",
        "captured_projection",
        "api_gym.provider_components.pylabrobot.snapshots.plate_reader_snapshot",
        "Normalize selected PyLabRobot plate-reader resource state as JSON.",
    ),
)

OPERATION_GROUNDING = {item.operation_id: item for item in _DECLARATIONS}


def operation_observation(
    operation_id: str,
    *,
    result: Any = None,
    request: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
    console: dict[str, Any] | None = None,
) -> dict[str, Any]:
    grounding = OPERATION_GROUNDING[operation_id]
    observation: dict[str, Any] = {
        "operation_id": operation_id,
        "grounding_level": grounding.level,
        "implementation": grounding.implementation,
        "provider": {
            "distribution": "pylabrobot",
            "version": PYLABROBOT_VERSION,
            "hardware_execution_allowed": False,
        },
        "result": result,
    }
    if request is not None:
        observation["request"] = request
    if snapshot is not None:
        observation["snapshot"] = snapshot
    if console is not None:
        observation["console"] = console
    return observation
