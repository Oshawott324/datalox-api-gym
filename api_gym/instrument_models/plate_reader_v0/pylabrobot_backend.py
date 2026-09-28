"""Device-free backend for the exact PyLabRobot 0.2.1 absorbance interface."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from pylabrobot.plate_reading.backend import PlateReaderBackend


AbsorbanceMatrix = list[list[float | None]]
AbsorbanceFactory = Callable[[Any, list[Any], int], AbsorbanceMatrix]


class AuthoredAbsorbanceBackend(PlateReaderBackend):
    """A deterministic interface probe, explicitly not a hardware emulator."""

    def __init__(
        self,
        factory: AbsorbanceFactory,
        *,
        logical_time_s: float = 0.0,
        temperature_c: float = 37.0,
    ) -> None:
        self._factory = factory
        self._time_s = float(logical_time_s)
        self._temperature_c = float(temperature_c)
        self._setup = False
        self._open = False

    async def setup(self) -> None:
        self._setup = True

    async def stop(self) -> None:
        self._setup = False
        self._open = False

    async def open(self) -> None:
        self._require_setup()
        self._open = True

    async def close(self, plate: Any | None) -> None:
        self._require_setup()
        if plate is None:
            raise ValueError("a plate must be assigned before closing the modeled tray")
        self._open = False

    async def read_absorbance(
        self, plate: Any, wells: list[Any], wavelength: int
    ) -> list[dict[str, Any]]:
        self._require_setup()
        if self._open:
            raise RuntimeError("modeled tray must be closed before acquisition")
        if type(wavelength) is not int or wavelength <= 0:
            raise ValueError("wavelength must be a positive integer in nanometres")
        matrix = self._factory(plate, wells, wavelength)
        _validate_matrix(matrix)
        return [
            {
                "wavelength": wavelength,
                "time": self._time_s,
                "temperature": self._temperature_c,
                "data": matrix,
            }
        ]

    async def read_luminescence(
        self, plate: Any, wells: list[Any], focal_height: float
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("the admitted reader profile supports absorbance only")

    async def read_fluorescence(
        self,
        plate: Any,
        wells: list[Any],
        excitation_wavelength: int,
        emission_wavelength: int,
        focal_height: float,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("the admitted reader profile supports absorbance only")

    def _require_setup(self) -> None:
        if not self._setup:
            raise RuntimeError("modeled plate reader has not been set up")


def _validate_matrix(matrix: Any) -> None:
    if not isinstance(matrix, list) or not matrix or not all(
        isinstance(row, list) and row for row in matrix
    ):
        raise ValueError("absorbance data must be a non-empty rectangular matrix")
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise ValueError("absorbance data must be rectangular")
    for row in matrix:
        for value in row:
            if value is not None and (
                type(value) not in (int, float) or not math.isfinite(float(value))
            ):
                raise ValueError("absorbance cells must be finite numbers or null")


__all__ = ["AbsorbanceFactory", "AbsorbanceMatrix", "AuthoredAbsorbanceBackend"]
