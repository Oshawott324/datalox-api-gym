"""Dry-run STAR backends for LabLongRun-Bench.

- ``STARDryRunBackend`` — liquid handling (extends ``LiquidHandlerChatterboxBackend``).
- ``PlateReaderDryRunBackend`` — absorbance/fluorescence/luminescence reading.
- ``PumpDryRunBackend`` — peristaltic/syringe pump operations.
"""

from __future__ import annotations

from typing import Any, Optional

from pylabrobot.liquid_handling.backends.chatterbox import (
    LiquidHandlerChatterboxBackend,
)
from pylabrobot.plate_reading.backend import PlateReaderBackend
from pylabrobot.pumps.backend import PumpBackend
from pylabrobot.resources import Plate, Well


class STARDryRunBackend(LiquidHandlerChatterboxBackend):
    """Configurable STAR dry-run backend.

    All operations are no-ops (print-only).  Volume / tip tracking is
    handled by ``LiquidHandler`` at the high-level API layer.
    """

    def __init__(
        self,
        num_channels: int = 8,
        with_96_head: bool = False,
        with_iswap: bool = False,
    ):
        super().__init__(num_channels=num_channels)
        self._head96_installed = with_96_head
        self._num_arms = 1 if with_iswap else 0


class PlateReaderDryRunBackend(PlateReaderBackend):
    """Dry-run plate reader backend.

    Returns zero-valued data matrices in the standard PLR format.
    Actual OD values, noise, and fault injection are applied by the
    service layer (``services.read_absorbance``), which wraps the
    PLR ``PlateReader.read_absorbance`` call.
    """

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def open(self) -> None:
        pass

    async def close(self, plate: Optional[Plate] = None) -> None:
        pass

    async def read_absorbance(
        self, plate: Plate, wells: list[Well], wavelength: int,
    ) -> list[dict[str, Any]]:
        return [{
            "wavelength": wavelength,
            "time": 0.0,
            "temperature": 25.0,
            "data": [[0.0 for _ in wells]],
        }]

    async def read_fluorescence(
        self, plate: Plate, wells: list[Well],
        excitation_wavelength: int, emission_wavelength: int,
        focal_height: float,
    ) -> list[dict[str, Any]]:
        return [{
            "excitation_wavelength": excitation_wavelength,
            "emission_wavelength": emission_wavelength,
            "time": 0.0,
            "temperature": 25.0,
            "data": [[0.0 for _ in wells]],
        }]

    async def read_luminescence(
        self, plate: Plate, wells: list[Well], focal_height: float,
    ) -> list[dict[str, Any]]:
        return [{
            "time": 0.0,
            "temperature": 25.0,
            "data": [[0.0 for _ in wells]],
        }]

    def serialize(self) -> dict[str, Any]:
        return {}

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "PlateReaderDryRunBackend":
        return cls()


class PumpDryRunBackend(PumpBackend):
    """Dry-run pump backend.

    All operations are no-ops.  ``pump_volume``, ``run_for_duration``,
    and ``run_revolutions`` succeed silently.  The service layer records
    events and advances the clock.
    """

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def halt(self) -> None:
        pass

    async def run_continuously(self, speed: float) -> None:
        pass

    async def run_revolutions(self, num_revolutions: float) -> None:
        pass

    def serialize(self) -> dict[str, Any]:
        return {}

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "PumpDryRunBackend":
        return cls()
