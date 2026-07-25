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
from pylabrobot.arms.backend import SCARABackend
from pylabrobot.sealing.backend import SealerBackend
from pylabrobot.peeling.backend import PeelerBackend
from pylabrobot.shaking.backend import ShakerBackend
from pylabrobot.temperature_controlling.backend import TemperatureControllerBackend
from pylabrobot.tilting.tilter_backend import TilterBackend
from pylabrobot.storage.backend import IncubatorBackend
from pylabrobot.powder_dispensing.backend import PowderDispenserBackend
from pylabrobot.barcode_scanners.backend import BarcodeScannerBackend


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


class ArmDryRunBackend(SCARABackend):
    """Dry-run robot arm backend (PreciseFlex / SCARA).

    Tracks cartesian position and gripper state internally so safety
    checks (e.g. pick-up with open gripper) can be enforced by the
    service layer.  All motions are instant no-ops.
    """
    def __init__(self):
        self._x: float = 0.0
        self._y: float = 0.0
        self._z: float = 0.0
        self._gripper_open: bool = True
        self._gripper_width: float = 80.0
        self._homed: bool = False
        self._in_freedrive: bool = False

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def home(self) -> None:
        self._homed = True
        self._x, self._y, self._z = 0.0, 0.0, 150.0

    def _update_position(self, position) -> None:
        """Update internal position from CartesianCoords or joint dict."""
        if isinstance(position, dict):
            self._x = position.get(0, self._x)
            self._y = position.get(1, self._y)
            self._z = position.get(2, self._z)
        else:
            loc = getattr(position, 'location', position)
            self._x = getattr(loc, 'x', 0.0)
            self._y = getattr(loc, 'y', 0.0)
            self._z = getattr(loc, 'z', 0.0)

    async def move_to(self, position) -> None:
        self._update_position(position)

    async def move_to_safe(self) -> None:
        self._x, self._y, self._z = 0.0, 0.0, 150.0

    async def approach(self, position, access=None) -> None:
        self._update_position(position)

    async def pick_up_resource(self, position, plate_width,
                                access=None) -> None:
        self._gripper_open = False
        self._gripper_width = plate_width

    async def drop_resource(self, position, access=None) -> None:
        self._gripper_open = True
        self._gripper_width = 80.0

    async def open_gripper(self, gripper_width: float) -> None:
        self._gripper_open = True
        self._gripper_width = gripper_width

    async def close_gripper(self, gripper_width: float) -> None:
        self._gripper_open = False
        self._gripper_width = gripper_width

    async def is_gripper_closed(self) -> bool:
        return not self._gripper_open

    async def get_cartesian_position(self):
        from pylabrobot.resources import Coordinate, Rotation
        from pylabrobot.arms.precise_flex.coords import PreciseFlexCartesianCoords
        loc = Coordinate(x=self._x, y=self._y, z=self._z)
        rot = Rotation(x=0.0, y=0.0, z=0.0)
        return PreciseFlexCartesianCoords(location=loc, rotation=rot)

    async def get_joint_position(self) -> dict:
        return {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}

    async def halt(self) -> None:
        pass

    async def freedrive_mode(self, free_axes) -> None:
        self._in_freedrive = True

    async def end_freedrive_mode(self) -> None:
        self._in_freedrive = False

    def serialize(self) -> dict:
        return {}

    @classmethod
    def deserialize(cls, data: dict) -> "ArmDryRunBackend":
        return cls()


class SealerDryRunBackend(SealerBackend):
    """Dry-run plate sealer backend.

    Tracks door state, target/current temperature, and seal status
    so safety checks (e.g. seal with door open) can be enforced.
    """
    def __init__(self):
        self._door_open: bool = True
        self._target_temp: float = 25.0
        self._current_temp: float = 25.0
        self._heater_on: bool = False
        self._sealing: bool = False

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def open(self) -> None:
        self._door_open = True

    async def close(self) -> None:
        self._door_open = False

    async def set_temperature(self, temperature: float) -> None:
        self._target_temp = temperature
        self._current_temp = temperature
        self._heater_on = True

    async def get_temperature(self) -> float:
        return self._current_temp

    async def seal(self, temperature: int, duration: float) -> None:
        self._sealing = True
        self._current_temp = float(temperature)

    def serialize(self) -> dict:
        return {}

    @classmethod
    def deserialize(cls, data: dict) -> "SealerDryRunBackend":
        return cls()


class PeelerDryRunBackend(PeelerBackend):
    """Dry-run plate peeler / de-sealer backend.

    Tracks conveyor position, elevator state, tape remaining, seal
    sensor status, and peel count.  Mirrors XPeelBackend's rich API.
    """
    def __init__(self):
        self._conveyor_in: bool = False
        self._elevator_up: bool = False
        self._tape_remaining: float = 100.0  # percent
        self._peel_count: int = 0
        self._seal_present: bool = True  # starts with seal on plate
        self._plate_check_enabled: bool = True
        self._seal_threshold_lower: int = 50
        self._seal_threshold_upper: int = 200
        self._status: tuple = (0, 0, 0)  # (state, error, warning)

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    # ── PeelerBackend abstract methods ──────────────────────────────────

    async def peel(self, begin_location=0, fast=False,
                   adhere_time=2.5) -> None:
        if self._seal_present:
            self._seal_present = False
            self._peel_count += 1
            self._tape_remaining = max(0.0, self._tape_remaining - 1.0)

    async def restart(self) -> None:
        self._conveyor_in = False
        self._elevator_up = False
        self._status = (0, 0, 0)

    # ── XPeelBackend-style methods ──────────────────────────────────────

    async def seal_check(self) -> str:
        if not self._plate_check_enabled:
            return "plate_not_detected"
        return "seal_detected" if self._seal_present else "no_seal"

    async def advance_tape(self) -> None:
        self._tape_remaining = max(0.0, self._tape_remaining - 0.5)

    async def move_conveyor_in(self) -> None:
        self._conveyor_in = True

    async def move_conveyor_out(self) -> None:
        self._conveyor_in = False

    async def move_elevator_up(self) -> None:
        self._elevator_up = True

    async def move_elevator_down(self) -> None:
        self._elevator_up = False

    async def enable_plate_check(self, enabled: bool = True) -> None:
        self._plate_check_enabled = enabled

    async def get_status(self) -> tuple:
        return self._status

    async def get_tape_remaining(self) -> float:
        return self._tape_remaining

    async def get_seal_sensor_status(self) -> dict:
        return {"seal_detected": self._seal_present,
                "threshold_lower": self._seal_threshold_lower,
                "threshold_upper": self._seal_threshold_upper}

    async def get_version(self) -> str:
        return "XPeel-DryRun v1.0"

    async def set_seal_threshold_lower(self, value: int) -> None:
        self._seal_threshold_lower = value

    async def set_seal_threshold_upper(self, value: int) -> None:
        self._seal_threshold_upper = value

    async def reset(self) -> None:
        self._conveyor_in = False
        self._elevator_up = False
        self._peel_count = 0
        self._seal_present = True
        self._status = (0, 0, 0)

    def serialize(self) -> dict:
        return {}

    @classmethod
    def deserialize(cls, data: dict) -> "PeelerDryRunBackend":
        return cls()


class ShakerDryRunBackend(ShakerBackend):
    """Dry-run shaker backend (pure shaking, no temperature control).

    Tracks plate lock state and shaking speed/duration.
    Plate must be locked before shaking can start.
    """
    def __init__(self):
        self._plate_locked: bool = False
        self._shaking: bool = False
        self._speed_rpm: float = 0.0

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def lock_plate(self) -> None:
        self._plate_locked = True

    async def unlock_plate(self) -> None:
        self._plate_locked = False
        self._shaking = False  # auto-stop on unlock

    async def start_shaking(self, speed: float) -> None:
        if not self._plate_locked:
            raise RuntimeError("Plate not locked — lock before shaking.")
        self._shaking = True
        self._speed_rpm = speed

    async def stop_shaking(self) -> None:
        self._shaking = False
        self._speed_rpm = 0.0

    @property
    def supports_locking(self) -> bool:
        return True

    def serialize(self) -> dict:
        return {}

    @classmethod
    def deserialize(cls, data: dict) -> "ShakerDryRunBackend":
        return cls()


class TempControllerDryRunBackend(TemperatureControllerBackend):
    """Dry-run temperature controller backend (no shaking).

    Tracks target/current temperature and active state.
    In dry-run mode, temperature changes are instant (no ramp time).
    """
    def __init__(self):
        self._target_temp: float = 25.0
        self._current_temp: float = 25.0
        self._active: bool = False

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def set_temperature(self, temperature: float) -> None:
        self._target_temp = temperature
        self._current_temp = temperature
        self._active = True

    async def get_current_temperature(self) -> float:
        return self._current_temp

    async def deactivate(self) -> None:
        self._active = False
        self._current_temp = 25.0

    @property
    def supports_active_cooling(self) -> bool:
        return False

    def serialize(self) -> dict:
        return {}

    @classmethod
    def deserialize(cls, data: dict) -> "TempControllerDryRunBackend":
        return cls()


class TilterDryRunBackend(TilterBackend):
    """Dry-run tilter backend (Hamilton Tilt Module).

    Tracks absolute tilt angle.  Angle 0 = flat/level.
    """
    def __init__(self):
        self._angle: float = 0.0

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def set_angle(self, angle: float) -> None:
        self._angle = angle

    def serialize(self) -> dict:
        return {}

    @classmethod
    def deserialize(cls, data: dict) -> "TilterDryRunBackend":
        return cls()


class StorageDryRunBackend(IncubatorBackend):
    """Dry-run incubator / storage backend (Cytomat-like).

    Simulates a multi-site plate storage with temperature control
    and built-in shaking.  Tracks which plates are stored at which sites.
    """
    def __init__(self):
        self._door_open: bool = True
        self._target_temp: float = 25.0
        self._current_temp: float = 25.0
        self._shaking: bool = False
        self._stored_plates: dict[str, str] = {}  # plate_name → site_id
        self._free_sites: int = 20

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def open_door(self) -> None:
        self._door_open = True

    async def close_door(self) -> None:
        self._door_open = False

    async def set_temperature(self, temperature: float) -> None:
        self._target_temp = temperature
        self._current_temp = temperature

    async def get_temperature(self) -> float:
        return self._current_temp

    async def start_shaking(self, frequency: float) -> None:
        self._shaking = True

    async def stop_shaking(self) -> None:
        self._shaking = False

    async def fetch_plate_to_loading_tray(self, plate, **kwargs) -> None:
        plate_name = getattr(plate, 'name', str(plate))
        if plate_name in self._stored_plates:
            del self._stored_plates[plate_name]
            self._free_sites += 1

    async def take_in_plate(self, plate, site, **kwargs) -> None:
        plate_name = getattr(plate, 'name', str(plate))
        site_id = getattr(site, 'name', str(site))
        self._stored_plates[plate_name] = site_id
        self._free_sites = max(0, self._free_sites - 1)

    def serialize(self) -> dict:
        return {}

    @classmethod
    def deserialize(cls, data: dict) -> "StorageDryRunBackend":
        return cls()


class PowderDispenserDryRunBackend(PowderDispenserBackend):
    """Dry-run powder dispenser backend.

    Tracks dispense count and total amount dispensed.
    Returns success results for every dispense operation.
    """
    def __init__(self):
        self._dispense_count: int = 0
        self._total_amount_mg: float = 0.0

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def dispense(self, dispense_parameters, **kwargs):
        results = []
        for dp in dispense_parameters:
            amount = getattr(dp, 'amount', 0.0)
            self._total_amount_mg += amount
            self._dispense_count += 1
            results.append({"ok": True, "amount_mg": amount})
        return results

    def serialize(self) -> dict:
        return {}

    @classmethod
    def deserialize(cls, data: dict) -> "PowderDispenserDryRunBackend":
        return cls()


class BarcodeScannerDryRunBackend(BarcodeScannerBackend):
    """Dry-run barcode scanner backend.

    Returns a configurable barcode value.  Simulates scanning a plate
    or container barcode for identity verification.
    """
    def __init__(self, default_barcode: str = "PLATE-001"):
        self._barcode: str = default_barcode
        self._scan_count: int = 0

    async def setup(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def scan_barcode(self):
        from pylabrobot.resources.barcode import Barcode
        self._scan_count += 1
        return Barcode()

    def serialize(self) -> dict:
        return {"barcode": self._barcode}

    @classmethod
    def deserialize(cls, data: dict) -> "BarcodeScannerDryRunBackend":
        return cls(default_barcode=data.get("barcode", "PLATE-001"))
