"""Bounded local OT-2 simulator component using actual PyLabRobot classes."""

from __future__ import annotations

from importlib.metadata import version
from typing import Any

from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.liquid_handling.backends import OpentronsOT2Simulator
from pylabrobot.resources import (
    Cor_96_wellplate_360ul_Fb,
    does_tip_tracking,
    does_volume_tracking,
    set_tip_tracking,
    set_volume_tracking,
)
from pylabrobot.resources.opentrons import (
    OTDeck,
    opentrons_96_tiprack_20ul,
    opentrons_96_tiprack_300ul,
)

from api_gym.provider_components.pylabrobot.errors import (
    PyLabRobotComponentError,
    normalize_plr_exception,
)
from api_gym.provider_components.pylabrobot.grounding import (
    PYLABROBOT_VERSION,
    operation_observation,
)
from api_gym.provider_components.pylabrobot.snapshots import ot2_snapshot


class OT2SimulatorComponent:
    """A software-only OT-2 fixture with PyLabRobot tip and volume tracking."""

    def __init__(
        self,
        *,
        tip_capacity_ul: int = 300,
        initial_source_volume_ul: float = 100.0,
    ) -> None:
        _require_pinned_version()
        if tip_capacity_ul not in {20, 300}:
            raise ValueError("tip_capacity_ul must be 20 or 300")
        self.tip_capacity_ul = tip_capacity_ul
        self.channel = 0 if tip_capacity_ul == 300 else 1
        self.deck = OTDeck()
        tip_rack_factory = (
            opentrons_96_tiprack_300ul
            if tip_capacity_ul == 300
            else opentrons_96_tiprack_20ul
        )
        self.tip_rack = tip_rack_factory(f"tips_{tip_capacity_ul}ul")
        self.source_plate = Cor_96_wellplate_360ul_Fb("source_plate")
        self.target_plate = Cor_96_wellplate_360ul_Fb("target_plate")
        self.deck.assign_child_at_slot(self.tip_rack, 1)
        self.deck.assign_child_at_slot(self.source_plate, 2)
        self.deck.assign_child_at_slot(self.target_plate, 3)
        self.source_plate.get_item("A1").tracker.set_volume(initial_source_volume_ul)
        self.backend = OpentronsOT2Simulator(
            left_pipette_name="p300_single_gen2",
            right_pipette_name="p20_single_gen2",
        )
        self.liquid_handler = LiquidHandler(backend=self.backend, deck=self.deck)
        self._previous_tip_tracking = does_tip_tracking()
        self._previous_volume_tracking = does_volume_tracking()
        self._setup = False

    async def setup(self) -> dict[str, Any]:
        set_tip_tracking(True)
        set_volume_tracking(True)
        try:
            await self.liquid_handler.setup()
        except Exception as error:
            self._restore_tracking()
            raise normalize_plr_exception(
                error, operation_id="pylabrobot.ot2.setup"
            ) from error
        self._setup = True
        return operation_observation(
            "pylabrobot.ot2.setup",
            result={"setup_finished": self.liquid_handler.setup_finished},
            snapshot=self.snapshot(),
        )

    async def pick_up_tip(self, tip_spot: str = "A1") -> dict[str, Any]:
        operation_id = "pylabrobot.ot2.pick_up_tip"
        try:
            await self.liquid_handler.pick_up_tips(
                [self.tip_rack.get_item(tip_spot)],
                use_channels=[self.channel],
            )
        except Exception as error:
            raise normalize_plr_exception(error, operation_id=operation_id) from error
        return operation_observation(
            operation_id,
            request={"channel": self.channel, "tip_spot": tip_spot},
            result=None,
            snapshot=self.snapshot(),
        )

    async def aspirate(
        self,
        well: str,
        volume_ul: float,
        *,
        plate: str = "source",
    ) -> dict[str, Any]:
        operation_id = "pylabrobot.ot2.aspirate"
        selected_plate = self._plate(plate)
        try:
            await self.liquid_handler.aspirate(
                [selected_plate.get_item(well)],
                vols=[volume_ul],
                use_channels=[self.channel],
            )
        except Exception as error:
            raise normalize_plr_exception(error, operation_id=operation_id) from error
        return operation_observation(
            operation_id,
            request={
                "channel": self.channel,
                "plate": selected_plate.name,
                "volume_ul": float(volume_ul),
                "well": well,
            },
            result=None,
            snapshot=self.snapshot(),
        )

    async def dispense(
        self,
        well: str,
        volume_ul: float,
        *,
        plate: str = "target",
    ) -> dict[str, Any]:
        operation_id = "pylabrobot.ot2.dispense"
        selected_plate = self._plate(plate)
        try:
            await self.liquid_handler.dispense(
                [selected_plate.get_item(well)],
                vols=[volume_ul],
                use_channels=[self.channel],
            )
        except Exception as error:
            raise normalize_plr_exception(error, operation_id=operation_id) from error
        return operation_observation(
            operation_id,
            request={
                "channel": self.channel,
                "plate": selected_plate.name,
                "volume_ul": float(volume_ul),
                "well": well,
            },
            result=None,
            snapshot=self.snapshot(),
        )

    async def drop_tip(self, tip_spot: str = "A1") -> dict[str, Any]:
        operation_id = "pylabrobot.ot2.drop_tip"
        try:
            await self.liquid_handler.drop_tips(
                [self.tip_rack.get_item(tip_spot)],
                use_channels=[self.channel],
            )
        except Exception as error:
            raise normalize_plr_exception(error, operation_id=operation_id) from error
        return operation_observation(
            operation_id,
            request={"channel": self.channel, "tip_spot": tip_spot},
            result=None,
            snapshot=self.snapshot(),
        )

    async def stop(self) -> dict[str, Any]:
        try:
            if self._setup:
                await self.liquid_handler.stop()
        except Exception as error:
            raise normalize_plr_exception(
                error, operation_id="pylabrobot.ot2.stop"
            ) from error
        finally:
            self._setup = False
            self._restore_tracking()
        return operation_observation(
            "pylabrobot.ot2.stop",
            result={"setup_finished": self.liquid_handler.setup_finished},
        )

    def snapshot(self) -> dict[str, Any]:
        return ot2_snapshot(
            self.liquid_handler,
            tip_rack=self.tip_rack,
            source_plate=self.source_plate,
            target_plate=self.target_plate,
        )

    def empty_tip_spot_for_reference(self, tip_spot: str) -> None:
        """Prepare a deterministic tracker-error fixture without disabling tracking."""
        self.tip_rack.get_item(tip_spot).empty()

    def _plate(self, name: str):
        if name == "source":
            return self.source_plate
        if name == "target":
            return self.target_plate
        raise ValueError("plate must be source or target")

    def _restore_tracking(self) -> None:
        set_tip_tracking(self._previous_tip_tracking)
        set_volume_tracking(self._previous_volume_tracking)


def _require_pinned_version() -> None:
    installed = version("pylabrobot")
    if installed != PYLABROBOT_VERSION:
        raise PyLabRobotComponentError(
            "PYLABROBOT_VERSION_MISMATCH",
            f"Expected PyLabRobot {PYLABROBOT_VERSION}, found {installed}.",
            operation_id="pylabrobot.package.require_version",
            details={
                "expected": PYLABROBOT_VERSION,
                "installed": installed,
                "hardware_execution_attempted": False,
            },
        )
