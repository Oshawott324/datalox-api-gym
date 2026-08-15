"""PyLabRobot backends with serializable dry-run state."""

from __future__ import annotations

from typing import Any

from pylabrobot.plate_reading.backend import PlateReaderBackend
from pylabrobot.powder_dispensing.backend import PowderDispenserBackend
from pylabrobot.scales.scale_backend import ScaleBackend
from pylabrobot.storage.backend import IncubatorBackend
from pylabrobot.thermocycling.backend import ThermocyclerBackend
from pylabrobot.thermocycling.standard import BlockStatus, LidStatus


class ThermocyclerProgramBackend(ThermocyclerBackend):
    """Stateful thermal-program projection behind the real PLR interface."""

    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        data = snapshot or {}
        self.lid_open = bool(data.get("lid_open", True))
        self.block_temperature_c = float(data.get("block_temperature_c", 25.0))
        self.block_target_c = float(data.get("block_target_c", 25.0))
        self.lid_temperature_c = float(data.get("lid_temperature_c", 25.0))
        self.lid_target_c = float(data.get("lid_target_c", 25.0))
        self.timeline = list(data.get("timeline", []))
        self.elapsed_s = float(data.get("elapsed_s", 0.0))
        self.running = bool(data.get("running", False))
        self.completed = bool(data.get("completed", False))
        self.block_max_volume_ul = data.get("block_max_volume_ul")

    async def setup(self) -> None:
        return None

    async def stop(self) -> None:
        self.running = False

    async def close_lid(self) -> None:
        self.lid_open = False

    async def open_lid(self) -> None:
        if self.running:
            raise RuntimeError("Cannot open the thermocycler lid while a protocol is running.")
        self.lid_open = True

    async def set_block_temperature(self, temperature: list[float]) -> None:
        self.block_target_c = float(temperature[0])
        self.block_temperature_c = self.block_target_c

    async def set_lid_temperature(self, temperature: list[float]) -> None:
        self.lid_target_c = float(temperature[0])
        self.lid_temperature_c = self.lid_target_c

    async def get_block_current_temperature(self) -> list[float]:
        return [self.block_temperature_c]

    async def get_block_target_temperature(self) -> list[float]:
        return [self.block_target_c]

    async def get_lid_current_temperature(self) -> list[float]:
        return [self.lid_temperature_c]

    async def get_lid_target_temperature(self) -> list[float]:
        return [self.lid_target_c]

    async def get_lid_open(self) -> bool:
        return self.lid_open

    async def get_block_status(self) -> BlockStatus:
        return BlockStatus.HOLDING_AT_TARGET if self.running else BlockStatus.IDLE

    async def get_lid_status(self) -> LidStatus:
        return LidStatus.HOLDING_AT_TARGET if not self.lid_open else LidStatus.IDLE

    async def get_hold_time(self) -> float:
        current = self.current_step
        if current is None:
            return 0.0
        return round(max(0.0, self.elapsed_s - float(current["start_s"])), 3)

    async def get_total_cycle_count(self) -> int:
        return max((int(step["global_cycle_index"]) for step in self.timeline), default=-1) + 1

    async def get_current_cycle_index(self) -> int:
        current = self.current_step
        return int(current["global_cycle_index"]) if current is not None else 0

    async def get_total_step_count(self) -> int:
        return len(self.timeline)

    async def get_current_step_index(self) -> int:
        current = self.current_step
        return int(current["program_step_index"]) if current is not None else 0

    async def deactivate_block(self) -> None:
        self.block_target_c = 25.0
        self.block_temperature_c = 25.0

    async def deactivate_lid(self) -> None:
        self.lid_target_c = 25.0
        self.lid_temperature_c = 25.0

    async def run_protocol(self, protocol: Any, block_max_volume: float) -> None:
        if self.lid_open:
            raise RuntimeError("Close the thermocycler lid before starting a protocol.")
        if self.running:
            raise RuntimeError("A thermocycler protocol is already running.")
        timeline: list[dict[str, Any]] = []
        cursor_s = 0.0
        global_cycle = 0
        program_step = 0
        for stage_index, stage in enumerate(protocol.stages):
            for cycle_index in range(int(stage.repeats)):
                for step_index, step in enumerate(stage.steps):
                    hold_s = float(step.hold_seconds)
                    timeline.append(
                        {
                            "stage_index": stage_index,
                            "cycle_index": cycle_index,
                            "global_cycle_index": global_cycle,
                            "step_index": step_index,
                            "program_step_index": program_step,
                            "temperature_c": float(step.temperature[0]),
                            "hold_seconds": hold_s,
                            "start_s": cursor_s,
                            "end_s": cursor_s + hold_s,
                        }
                    )
                    cursor_s += hold_s
                    program_step += 1
                global_cycle += 1
        if not timeline:
            raise ValueError("Thermocycler protocol must contain at least one step.")
        self.timeline = timeline
        self.elapsed_s = 0.0
        self.running = True
        self.completed = False
        self.block_max_volume_ul = float(block_max_volume)
        self._sync_temperature()

    @property
    def total_duration_s(self) -> float:
        return float(self.timeline[-1]["end_s"]) if self.timeline else 0.0

    @property
    def current_step(self) -> dict[str, Any] | None:
        if not self.timeline:
            return None
        if self.completed:
            return self.timeline[-1]
        for step in self.timeline:
            if self.elapsed_s < float(step["end_s"]):
                return step
        return self.timeline[-1]

    def advance(self, seconds: float) -> None:
        if seconds <= 0:
            raise ValueError("seconds must be greater than zero")
        if not self.timeline or self.completed:
            raise RuntimeError("No thermocycler protocol is currently running.")
        self.elapsed_s = min(self.total_duration_s, self.elapsed_s + seconds)
        if self.elapsed_s >= self.total_duration_s:
            self.running = False
            self.completed = True
        self._sync_temperature()

    def _sync_temperature(self) -> None:
        current = self.current_step
        if current is not None:
            self.block_target_c = float(current["temperature_c"])
            self.block_temperature_c = self.block_target_c

    def serialize(self) -> dict[str, Any]:
        return {
            "lid_open": self.lid_open,
            "block_temperature_c": self.block_temperature_c,
            "block_target_c": self.block_target_c,
            "lid_temperature_c": self.lid_temperature_c,
            "lid_target_c": self.lid_target_c,
            "timeline": self.timeline,
            "elapsed_s": self.elapsed_s,
            "running": self.running,
            "completed": self.completed,
            "block_max_volume_ul": self.block_max_volume_ul,
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "ThermocyclerProgramBackend":
        return cls(data)

    @property
    def supports_lid_heating(self) -> bool:
        return True


class IncubatorProjectionBackend(IncubatorBackend):
    """PLR incubator backend whose physical state is persisted by the world."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.door_open = bool(snapshot["door_open"])
        self.target_temperature_c = snapshot["target_temperature_c"]
        self.current_temperature_c = float(snapshot["current_temperature_c"])
        self.shaking = bool(snapshot["shaking"])
        self.shake_rpm = float(snapshot["shake_rpm"])

    async def setup(self) -> None:
        return None

    async def stop(self) -> None:
        self.shaking = False

    async def open_door(self) -> None:
        self.door_open = True

    async def close_door(self) -> None:
        self.door_open = False

    async def set_temperature(self, temperature: float) -> None:
        self.target_temperature_c = float(temperature)

    async def get_temperature(self) -> float:
        return self.current_temperature_c

    async def start_shaking(self, frequency: float = 1.0) -> None:
        self.shaking = True
        self.shake_rpm = float(frequency)

    async def stop_shaking(self) -> None:
        self.shaking = False
        self.shake_rpm = 0.0

    async def fetch_plate_to_loading_tray(self, plate: Any, **kwargs: Any) -> None:
        return None

    async def take_in_plate(self, plate: Any, site: Any, **kwargs: Any) -> None:
        return None

    def serialize(self) -> dict[str, Any]:
        return {
            "door_open": self.door_open,
            "target_temperature_c": self.target_temperature_c,
            "current_temperature_c": self.current_temperature_c,
            "shaking": self.shaking,
            "shake_rpm": self.shake_rpm,
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "IncubatorProjectionBackend":
        return cls(data)


class GrowthPlateReaderBackend(PlateReaderBackend):
    """Return one precomputed OD600 row through the PLR reader interface."""

    def __init__(self, values: list[float], *, time_s: float, temperature_c: float) -> None:
        self.values = values
        self.time_s = time_s
        self.temperature_c = temperature_c

    async def setup(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def open(self) -> None:
        return None

    async def close(self, plate: Any = None) -> None:
        return None

    async def read_absorbance(
        self, plate: Any, wells: list[Any], wavelength: int
    ) -> list[dict[str, Any]]:
        return [
            {
                "wavelength": wavelength,
                "time": self.time_s,
                "temperature": self.temperature_c,
                "data": [self.values],
            }
        ]

    async def read_fluorescence(
        self,
        plate: Any,
        wells: list[Any],
        excitation_wavelength: int,
        emission_wavelength: int,
        focal_height: float,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("This workflow exposes absorbance only.")

    async def read_luminescence(
        self, plate: Any, wells: list[Any], focal_height: float
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("This workflow exposes absorbance only.")

    def serialize(self) -> dict[str, Any]:
        return {
            "values": self.values,
            "time_s": self.time_s,
            "temperature_c": self.temperature_c,
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "GrowthPlateReaderBackend":
        return cls(data["values"], time_s=data["time_s"], temperature_c=data["temperature_c"])


class PowderPulseBackend(PowderDispenserBackend):
    """Return a precomputed delivered mass through the PLR powder interface."""

    def __init__(self, actual_amount_mg: float) -> None:
        self.actual_amount_mg = actual_amount_mg

    async def setup(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def dispense(self, dispense_parameters: list[Any], **kwargs: Any) -> list[dict[str, Any]]:
        if len(dispense_parameters) != 1:
            raise ValueError("The formulation workflow accepts one pulse at a time.")
        return [{"actual_amount": self.actual_amount_mg, "unit": "mg"}]

    def serialize(self) -> dict[str, Any]:
        return {"actual_amount_mg": self.actual_amount_mg}

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "PowderPulseBackend":
        return cls(float(data["actual_amount_mg"]))


class BalanceProjectionBackend(ScaleBackend):
    """PLR scale backend over persisted gross and tare masses."""

    def __init__(self, *, gross_mass_g: float, tare_offset_g: float) -> None:
        self.gross_mass_g = gross_mass_g
        self.tare_offset_g = tare_offset_g

    async def setup(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def tare(self) -> None:
        self.tare_offset_g = self.gross_mass_g

    async def zero(self) -> None:
        self.tare_offset_g = self.gross_mass_g

    async def get_weight(self) -> float:
        return self.gross_mass_g - self.tare_offset_g

    async def read_weight(self) -> float:
        return await self.get_weight()

    def serialize(self) -> dict[str, Any]:
        return {"gross_mass_g": self.gross_mass_g, "tare_offset_g": self.tare_offset_g}

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "BalanceProjectionBackend":
        return cls(gross_mass_g=float(data["gross_mass_g"]), tare_offset_g=float(data["tare_offset_g"]))
