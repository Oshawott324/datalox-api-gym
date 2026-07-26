"""Bounded local plate-reader component using the PyLabRobot Chatterbox backend."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Awaitable, Callable

from pylabrobot.plate_reading import PlateReader, PlateReaderChatterboxBackend
from pylabrobot.resources import Cor_96_wellplate_360ul_Fb

from api_gym.provider_components.pylabrobot.errors import normalize_plr_exception
from api_gym.provider_components.pylabrobot.grounding import operation_observation
from api_gym.provider_components.pylabrobot.liquid_handling import (
    _require_pinned_version,
)
from api_gym.provider_components.pylabrobot.normalization import (
    normalize_console_output,
    normalize_json,
)
from api_gym.provider_components.pylabrobot.snapshots import plate_reader_snapshot


class PlateReaderChatterboxComponent:
    """A PyLabRobot plate-reader fixture with deterministic normalized readings."""

    def __init__(self) -> None:
        _require_pinned_version()
        self.backend = PlateReaderChatterboxBackend()
        self.reader = PlateReader(
            name="plate_reader",
            size_x=1,
            size_y=1,
            size_z=1,
            backend=self.backend,
        )
        self._setup = False

    async def setup(self) -> dict[str, Any]:
        observation = await self._call(
            "pylabrobot.plate_reader.setup", self.reader.setup
        )
        self._setup = True
        observation["snapshot"] = self.snapshot()
        return observation

    def place_plate(self, plate_name: str = "growth_plate") -> dict[str, Any]:
        operation_id = "pylabrobot.plate_reader.place_plate"
        try:
            self.reader.assign_child_resource(
                Cor_96_wellplate_360ul_Fb(plate_name)
            )
        except Exception as error:
            raise normalize_plr_exception(error, operation_id=operation_id) from error
        return operation_observation(
            operation_id,
            request={"plate_name": plate_name},
            result=None,
            snapshot=self.snapshot(),
        )

    async def open(self) -> dict[str, Any]:
        return await self._call("pylabrobot.plate_reader.open", self.reader.open)

    async def close(self) -> dict[str, Any]:
        return await self._call("pylabrobot.plate_reader.close", self.reader.close)

    async def read_absorbance(
        self,
        *,
        wavelength_nm: int,
        wells: tuple[str, ...],
    ) -> dict[str, Any]:
        return await self._call(
            "pylabrobot.plate_reader.read_absorbance",
            lambda: self.reader.read_absorbance(
                wavelength=wavelength_nm,
                wells=self._wells(wells),
                use_new_return_type=True,
            ),
            request={"wavelength_nm": wavelength_nm, "wells": list(wells)},
        )

    async def read_fluorescence(
        self,
        *,
        excitation_wavelength_nm: int,
        emission_wavelength_nm: int,
        focal_height_mm: float,
        wells: tuple[str, ...],
    ) -> dict[str, Any]:
        return await self._call(
            "pylabrobot.plate_reader.read_fluorescence",
            lambda: self.reader.read_fluorescence(
                excitation_wavelength=excitation_wavelength_nm,
                emission_wavelength=emission_wavelength_nm,
                focal_height=focal_height_mm,
                wells=self._wells(wells),
                use_new_return_type=True,
            ),
            request={
                "emission_wavelength_nm": emission_wavelength_nm,
                "excitation_wavelength_nm": excitation_wavelength_nm,
                "focal_height_mm": float(focal_height_mm),
                "wells": list(wells),
            },
        )

    async def read_luminescence(
        self,
        *,
        focal_height_mm: float,
        wells: tuple[str, ...],
    ) -> dict[str, Any]:
        return await self._call(
            "pylabrobot.plate_reader.read_luminescence",
            lambda: self.reader.read_luminescence(
                focal_height=focal_height_mm,
                wells=self._wells(wells),
                use_new_return_type=True,
            ),
            request={
                "focal_height_mm": float(focal_height_mm),
                "wells": list(wells),
            },
        )

    async def stop(self) -> dict[str, Any]:
        if not self._setup:
            return operation_observation(
                "pylabrobot.plate_reader.stop", result={"already_stopped": True}
            )
        observation = await self._call(
            "pylabrobot.plate_reader.stop", self.reader.stop
        )
        self._setup = False
        return observation

    def snapshot(self) -> dict[str, Any]:
        return plate_reader_snapshot(self.reader)

    def _wells(self, names: tuple[str, ...]):
        plate = self.reader.get_plate()
        return [plate.get_item(name) for name in names]

    async def _call(
        self,
        operation_id: str,
        call: Callable[[], Awaitable[Any]],
        *,
        request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = await call()
        except Exception as error:
            raise normalize_plr_exception(error, operation_id=operation_id) from error
        return operation_observation(
            operation_id,
            request=request,
            result=normalize_json(result),
            console=normalize_console_output(stdout.getvalue(), stderr.getvalue()),
        )
