"""Bounded local incubator component using the PyLabRobot Chatterbox backend."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Awaitable, Callable

from pylabrobot.resources import (
    Coordinate,
    Cor_96_wellplate_360ul_Fb,
    PlateCarrier,
    PlateHolder,
)
from pylabrobot.storage import Incubator, IncubatorChatterboxBackend

from api_gym.provider_components.pylabrobot.errors import normalize_plr_exception
from api_gym.provider_components.pylabrobot.grounding import operation_observation
from api_gym.provider_components.pylabrobot.liquid_handling import (
    _require_pinned_version,
)
from api_gym.provider_components.pylabrobot.normalization import (
    normalize_console_output,
    normalize_json,
)
from api_gym.provider_components.pylabrobot.snapshots import incubator_snapshot


class IncubatorChatterboxComponent:
    """A one-site PyLabRobot incubator fixture with no hardware connection path."""

    def __init__(self) -> None:
        _require_pinned_version()
        site = PlateHolder(
            name="site_1",
            size_x=128,
            size_y=86,
            size_z=20,
            pedestal_size_z=0,
            child_location=Coordinate.zero(),
        )
        site.location = Coordinate.zero()
        rack = PlateCarrier(
            name="rack_1",
            size_x=130,
            size_y=90,
            size_z=100,
            sites={1: site},
        )
        self.backend = IncubatorChatterboxBackend()
        self.incubator = Incubator(
            backend=self.backend,
            name="incubator",
            size_x=200,
            size_y=200,
            size_z=300,
            racks=[rack],
            loading_tray_location=Coordinate.zero(),
        )
        self._setup = False

    async def setup(self) -> dict[str, Any]:
        observation = await self._call(
            "pylabrobot.incubator.setup", self.incubator.setup
        )
        self._setup = True
        observation["snapshot"] = self.snapshot()
        return observation

    def place_plate_on_tray(self, plate_name: str = "growth_plate") -> dict[str, Any]:
        operation_id = "pylabrobot.incubator.place_plate_on_tray"
        try:
            plate = Cor_96_wellplate_360ul_Fb(plate_name)
            self.incubator.loading_tray.assign_child_resource(plate)
        except Exception as error:
            raise normalize_plr_exception(error, operation_id=operation_id) from error
        return operation_observation(
            operation_id,
            request={"plate_name": plate_name},
            result=None,
            snapshot=self.snapshot(),
        )

    async def open_door(self) -> dict[str, Any]:
        return await self._call(
            "pylabrobot.incubator.open_door", self.incubator.open_door
        )

    async def close_door(self) -> dict[str, Any]:
        return await self._call(
            "pylabrobot.incubator.close_door", self.incubator.close_door
        )

    async def set_temperature(self, temperature_c: float) -> dict[str, Any]:
        return await self._call(
            "pylabrobot.incubator.set_temperature",
            lambda: self.incubator.set_temperature(temperature_c),
            request={"temperature_c": float(temperature_c)},
        )

    async def get_temperature(self) -> dict[str, Any]:
        return await self._call(
            "pylabrobot.incubator.get_temperature",
            self.incubator.get_temperature,
        )

    async def start_shaking(self, frequency_hz: float) -> dict[str, Any]:
        return await self._call(
            "pylabrobot.incubator.start_shaking",
            lambda: self.incubator.start_shaking(frequency_hz),
            request={"frequency_hz": float(frequency_hz)},
        )

    async def stop_shaking(self) -> dict[str, Any]:
        return await self._call(
            "pylabrobot.incubator.stop_shaking",
            self.incubator.stop_shaking,
        )

    async def take_in_plate(self, site: str = "smallest") -> dict[str, Any]:
        operation_id = "pylabrobot.incubator.take_in_plate"
        observation = await self._call(
            operation_id,
            lambda: self.incubator.take_in_plate(site),
            request={"site": site},
        )
        observation["snapshot"] = self.snapshot()
        return observation

    async def fetch_plate(self, plate_name: str) -> dict[str, Any]:
        operation_id = "pylabrobot.incubator.fetch_plate"
        observation = await self._call(
            operation_id,
            lambda: self.incubator.fetch_plate_to_loading_tray(plate_name),
            request={"plate_name": plate_name},
            result_transform=lambda plate: {"plate_name": plate.name},
        )
        observation["snapshot"] = self.snapshot()
        return observation

    async def stop(self) -> dict[str, Any]:
        if not self._setup:
            return operation_observation(
                "pylabrobot.incubator.stop", result={"already_stopped": True}
            )
        observation = await self._call(
            "pylabrobot.incubator.stop", self.incubator.stop
        )
        self._setup = False
        return observation

    def snapshot(self) -> dict[str, Any]:
        return incubator_snapshot(self.incubator)

    async def _call(
        self,
        operation_id: str,
        call: Callable[[], Awaitable[Any]],
        *,
        request: dict[str, Any] | None = None,
        result_transform: Callable[[Any], Any] | None = None,
    ) -> dict[str, Any]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                raw_result = await call()
        except Exception as error:
            raise normalize_plr_exception(error, operation_id=operation_id) from error
        result = result_transform(raw_result) if result_transform else raw_result
        return operation_observation(
            operation_id,
            request=request,
            result=normalize_json(result),
            console=normalize_console_output(stdout.getvalue(), stderr.getvalue()),
        )
