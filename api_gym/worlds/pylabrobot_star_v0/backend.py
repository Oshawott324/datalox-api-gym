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
from pylabrobot.centrifuge.backend import CentrifugeBackend
from pylabrobot.heating_shaking.backend import HeaterShakerBackend
from pylabrobot.resources import Plate, Well
from pylabrobot.scales.scale_backend import ScaleBackend
from pylabrobot.thermocycling.backend import ThermocyclerBackend


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


class ScaleDryRunBackend(ScaleBackend):
    """Dry-run scale backend.

    ``get_weight`` returns a configurable default; ``tare`` and ``zero``
    are no-ops.  The service layer records events and advances the clock.
    """

    _default_weight: float = 0.0

    def __init__(self, default_weight: float = 0.0) -> None:
        self._default_weight = default_weight
        self._tare_offset: float = 0.0

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def tare(self) -> None:
        self._tare_offset = self._default_weight

    async def zero(self) -> None:
        self._tare_offset = self._default_weight

    async def get_weight(self) -> float:
        return self._default_weight - self._tare_offset

    async def read_weight(self) -> float:
        self._default_weight = self._default_weight + 0.001  # slight drift
        return self._default_weight - self._tare_offset

    def serialize(self) -> dict[str, Any]:
        return {"default_weight": self._default_weight}

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "ScaleDryRunBackend":
        return cls(default_weight=data.get("default_weight", 0.0))


class CentrifugeDryRunBackend(CentrifugeBackend):
    """Dry-run centrifuge backend.

    All mechanical operations are no-ops.  ``spin`` advances a simulated
    timer.  Door/bucket state is tracked internally so safety checks
    (e.g. spin with door open) can be enforced by the service layer.
    """

    def __init__(self) -> None:
        self._door_open: bool = True
        self._door_locked: bool = False
        self._at_bucket: int = 0

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def open_door(self) -> None:
        self._door_open = True

    async def close_door(self) -> None:
        self._door_open = False

    async def lock_door(self) -> None:
        self._door_locked = True

    async def unlock_door(self) -> None:
        self._door_locked = False

    async def go_to_bucket1(self) -> None:
        self._at_bucket = 1

    async def go_to_bucket2(self) -> None:
        self._at_bucket = 2

    async def lock_bucket(self) -> None:
        pass

    async def unlock_bucket(self) -> None:
        pass

    async def spin(self, g: float, duration: float,
                   acceleration: float) -> None:
        pass  # time advance handled by service layer

    def serialize(self) -> dict[str, Any]:
        return {}

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "CentrifugeDryRunBackend":
        return cls()


class HeaterShakerDryRunBackend(HeaterShakerBackend):
    """Dry-run heater/shaker backend."""
    def __init__(self):
        self._target_temp: float = 25.0
        self._current_temp: float = 25.0
        self._shaking: bool = False
        self._plate_locked: bool = False

    async def setup(self) -> None: pass
    async def stop(self) -> None: pass
    async def set_temperature(self, temperature: float) -> None:
        self._target_temp = temperature
        self._current_temp = temperature
    async def get_current_temperature(self) -> float:
        return self._current_temp
    async def start_shaking(self, speed: float) -> None:
        self._shaking = True
    async def stop_shaking(self) -> None:
        self._shaking = False
    async def lock_plate(self) -> None:
        self._plate_locked = True
    async def unlock_plate(self) -> None:
        self._plate_locked = False
    async def deactivate(self) -> None:
        self._shaking = False
        self._current_temp = 25.0
    @property
    def supports_active_cooling(self) -> bool: return False
    @property
    def supports_locking(self) -> bool: return True
    def serialize(self): return {}
    @classmethod
    def deserialize(cls, data): return cls()


class ThermocyclerDryRunBackend(ThermocyclerBackend):
    """Dry-run thermocycler backend."""
    def __init__(self):
        self._lid_open: bool = True
        self._block_temp: float = 25.0
        self._block_target: float = 25.0
        self._lid_temp: float = 25.0
        self._lid_target: float = 25.0

    async def setup(self) -> None: pass
    async def stop(self) -> None: pass
    async def close_lid(self) -> None: self._lid_open = False
    async def open_lid(self) -> None: self._lid_open = True
    async def set_block_temperature(self, temperature: list) -> None:
        self._block_target = float(temperature[0]) if temperature else 25.0
        self._block_temp = self._block_target
    async def set_lid_temperature(self, temperature: list) -> None:
        self._lid_target = float(temperature[0]) if temperature else 25.0
        self._lid_temp = self._lid_target
    async def get_block_current_temperature(self) -> list: return [self._block_temp]
    async def get_block_target_temperature(self) -> list: return [self._block_target]
    async def get_lid_current_temperature(self) -> list: return [self._lid_temp]
    async def get_lid_target_temperature(self) -> list: return [self._lid_target]
    async def get_lid_open(self) -> bool: return self._lid_open
    async def get_block_status(self): 
        from pylabrobot.thermocycling.standard import BlockStatus; return BlockStatus.IDLE
    async def get_lid_status(self):
        from pylabrobot.thermocycling.standard import LidStatus; return LidStatus.IDLE
    async def get_hold_time(self) -> float: return 0.0
    async def get_total_cycle_count(self) -> int: return 0
    async def get_current_cycle_index(self) -> int: return 0
    async def get_total_step_count(self) -> int: return 0
    async def get_current_step_index(self) -> int: return 0
    async def deactivate_block(self) -> None: self._block_temp = 25.0
    async def deactivate_lid(self) -> None: self._lid_temp = 25.0
    async def run_protocol(self, protocol, block_max_volume): pass
    def serialize(self): return {}
    @classmethod
    def deserialize(cls, data): return cls()
    @property
    def supports_lid_heating(self) -> bool: return True
