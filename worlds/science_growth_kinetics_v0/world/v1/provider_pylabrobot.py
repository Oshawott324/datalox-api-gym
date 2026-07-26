"""Standalone PyLabRobot 0.2.1 mechanisms vendored into executable worlds."""

from __future__ import annotations

import asyncio
import hashlib
import io
import math
from contextlib import redirect_stderr, redirect_stdout
from importlib.metadata import version
from typing import Any, Mapping

from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.liquid_handling.backends import OpentronsOT2Simulator
from pylabrobot.plate_reading import PlateReader, PlateReaderChatterboxBackend
from pylabrobot.resources import (
    Coordinate,
    Cor_96_wellplate_360ul_Fb,
    PlateCarrier,
    PlateHolder,
    does_tip_tracking,
    does_volume_tracking,
    set_tip_tracking,
    set_volume_tracking,
)
from pylabrobot.resources.opentrons import OTDeck, opentrons_96_tiprack_300ul
from pylabrobot.storage import Incubator, IncubatorChatterboxBackend

PINNED_PYLABROBOT_VERSION = "0.2.1"


class PyLabRobotBridgeError(RuntimeError):
    """Stable world-facing error produced by an executed PyLabRobot call."""

    def __init__(self, code: str, message: str, *, details: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "details": dict(self.details),
        }


def run_ot2_transfer(
    *,
    source_volumes_ul: Mapping[str, float],
    target_volumes_ul: Mapping[str, float],
    tip_availability: Mapping[str, bool],
    source_well: str,
    target_well: str,
    tip_spot: str,
    volume_ul: float,
) -> dict[str, Any]:
    """Execute one tracked pick/aspirate/dispense/return sequence locally."""
    _require_version()
    return asyncio.run(
        _run_ot2_transfer(
            source_volumes_ul=source_volumes_ul,
            target_volumes_ul=target_volumes_ul,
            tip_availability=tip_availability,
            source_well=source_well,
            target_well=target_well,
            tip_spot=tip_spot,
            volume_ul=volume_ul,
        )
    )


async def _run_ot2_transfer(
    *,
    source_volumes_ul: Mapping[str, float],
    target_volumes_ul: Mapping[str, float],
    tip_availability: Mapping[str, bool],
    source_well: str,
    target_well: str,
    tip_spot: str,
    volume_ul: float,
) -> dict[str, Any]:
    previous_tip_tracking = does_tip_tracking()
    previous_volume_tracking = does_volume_tracking()
    set_tip_tracking(True)
    set_volume_tracking(True)
    deck = OTDeck()
    tips = opentrons_96_tiprack_300ul("tips_300ul")
    source = Cor_96_wellplate_360ul_Fb("source_plate")
    target = Cor_96_wellplate_360ul_Fb("target_plate")
    deck.assign_child_at_slot(tips, 1)
    deck.assign_child_at_slot(source, 2)
    deck.assign_child_at_slot(target, 3)
    for well, volume in source_volumes_ul.items():
        source.get_item(well).tracker.set_volume(float(volume))
    for well, volume in target_volumes_ul.items():
        target.get_item(well).tracker.set_volume(float(volume))
    for spot, available in tip_availability.items():
        if not available:
            tips.get_item(spot).empty()
    backend = OpentronsOT2Simulator(
        left_pipette_name="p300_single_gen2",
        right_pipette_name="p20_single_gen2",
    )
    handler = LiquidHandler(backend=backend, deck=deck)
    setup_complete = False
    try:
        await handler.setup()
        setup_complete = True
        await handler.pick_up_tips([tips.get_item(tip_spot)], use_channels=[0])
        await handler.aspirate(
            [source.get_item(source_well)],
            vols=[float(volume_ul)],
            use_channels=[0],
        )
        await handler.dispense(
            [target.get_item(target_well)],
            vols=[float(volume_ul)],
            use_channels=[0],
        )
        await handler.discard_tips(use_channels=[0])
        return {
            "grounding_level": "simulator_executed",
            "provider": _provider("OpentronsOT2Simulator"),
            "executed_methods": [
                "LiquidHandler.setup",
                "LiquidHandler.pick_up_tips",
                "LiquidHandler.aspirate",
                "LiquidHandler.dispense",
                "LiquidHandler.discard_tips",
                "LiquidHandler.stop",
            ],
            "source_well": source_well,
            "source_volume_ul": float(source.get_item(source_well).tracker.volume),
            "target_well": target_well,
            "target_volume_ul": float(target.get_item(target_well).tracker.volume),
            "tip_spot": tip_spot,
            "tip_available": bool(tips.get_item(tip_spot).tracker.has_tip),
            "volume_ul": float(volume_ul),
        }
    except Exception as error:
        raise _normalize_error(error, operation="ot2.transfer") from error
    finally:
        try:
            if setup_complete:
                await handler.stop()
        finally:
            set_tip_tracking(previous_tip_tracking)
            set_volume_tracking(previous_volume_tracking)


def run_incubator_load(
    *,
    plate_name: str,
    temperature_c: float,
    shaking_hz: float,
) -> dict[str, Any]:
    """Execute a bounded Chatterbox incubator load and configuration sequence."""
    _require_version()
    return asyncio.run(
        _run_incubator_load(
            plate_name=plate_name,
            temperature_c=temperature_c,
            shaking_hz=shaking_hz,
        )
    )


async def _run_incubator_load(
    *,
    plate_name: str,
    temperature_c: float,
    shaking_hz: float,
) -> dict[str, Any]:
    incubator, site = _new_incubator()
    stdout = io.StringIO()
    stderr = io.StringIO()
    setup_complete = False
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            await incubator.setup()
            setup_complete = True
            incubator.loading_tray.assign_child_resource(
                Cor_96_wellplate_360ul_Fb(plate_name)
            )
            await incubator.open_door()
            await incubator.close_door()
            await incubator.set_temperature(float(temperature_c))
            observed_temperature = await incubator.get_temperature()
            await incubator.start_shaking(float(shaking_hz))
            await incubator.take_in_plate("smallest")
        return {
            "grounding_level": "chatterbox_executed",
            "provider": _provider("IncubatorChatterboxBackend"),
            "executed_methods": [
                "Incubator.setup",
                "Incubator.open_door",
                "Incubator.close_door",
                "Incubator.set_temperature",
                "Incubator.get_temperature",
                "Incubator.start_shaking",
                "Incubator.take_in_plate",
                "Incubator.stop",
            ],
            "plate_name": plate_name,
            "requested_temperature_c": float(temperature_c),
            "observed_dummy_temperature_c": float(observed_temperature),
            "requested_shaking_hz": float(shaking_hz),
            "site": site.name,
            "site_plate": site.resource.name if site.resource is not None else None,
            "console": _console_evidence(stdout.getvalue(), stderr.getvalue()),
        }
    except Exception as error:
        raise _normalize_error(error, operation="incubator.load") from error
    finally:
        if setup_complete:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                await incubator.stop()


def run_incubator_release(*, plate_name: str) -> dict[str, Any]:
    """Execute a bounded Chatterbox fetch from an incubator site."""
    _require_version()
    return asyncio.run(_run_incubator_release(plate_name=plate_name))


async def _run_incubator_release(*, plate_name: str) -> dict[str, Any]:
    incubator, site = _new_incubator()
    site.assign_child_resource(Cor_96_wellplate_360ul_Fb(plate_name))
    stdout = io.StringIO()
    stderr = io.StringIO()
    setup_complete = False
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            await incubator.setup()
            setup_complete = True
            await incubator.stop_shaking()
            plate = await incubator.fetch_plate_to_loading_tray(plate_name)
        return {
            "grounding_level": "chatterbox_executed",
            "provider": _provider("IncubatorChatterboxBackend"),
            "executed_methods": [
                "Incubator.setup",
                "Incubator.stop_shaking",
                "Incubator.fetch_plate_to_loading_tray",
                "Incubator.stop",
            ],
            "plate_name": plate.name,
            "loading_tray_plate": (
                incubator.loading_tray.resource.name
                if incubator.loading_tray.resource is not None
                else None
            ),
            "console": _console_evidence(stdout.getvalue(), stderr.getvalue()),
        }
    except Exception as error:
        raise _normalize_error(error, operation="incubator.release") from error
    finally:
        if setup_complete:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                await incubator.stop()


def run_plate_reader_absorbance(
    *,
    plate_name: str,
    wells: tuple[str, ...],
    wavelength_nm: int,
) -> dict[str, Any]:
    """Execute one Chatterbox absorbance read without claiming assay fidelity."""
    _require_version()
    return asyncio.run(
        _run_plate_reader_absorbance(
            plate_name=plate_name,
            wells=wells,
            wavelength_nm=wavelength_nm,
        )
    )


async def _run_plate_reader_absorbance(
    *,
    plate_name: str,
    wells: tuple[str, ...],
    wavelength_nm: int,
) -> dict[str, Any]:
    backend = PlateReaderChatterboxBackend()
    reader = PlateReader(
        name="plate_reader",
        size_x=1,
        size_y=1,
        size_z=1,
        backend=backend,
    )
    plate = Cor_96_wellplate_360ul_Fb(plate_name)
    stdout = io.StringIO()
    stderr = io.StringIO()
    setup_complete = False
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            await reader.setup()
            setup_complete = True
            await reader.open()
            reader.assign_child_resource(plate)
            await reader.close()
            result = await reader.read_absorbance(
                wavelength=int(wavelength_nm),
                wells=[plate.get_item(well) for well in wells],
                use_new_return_type=True,
            )
        return {
            "grounding_level": "chatterbox_executed",
            "provider": _provider("PlateReaderChatterboxBackend"),
            "executed_methods": [
                "PlateReader.setup",
                "PlateReader.open",
                "PlateReader.close",
                "PlateReader.read_absorbance",
                "PlateReader.stop",
            ],
            "plate_name": plate_name,
            "wavelength_nm": int(wavelength_nm),
            "wells": list(wells),
            "provider_dummy_result": _normalize_json(result),
            "console": _console_evidence(stdout.getvalue(), stderr.getvalue()),
        }
    except Exception as error:
        raise _normalize_error(error, operation="plate_reader.read_absorbance") from error
    finally:
        if setup_complete:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                await reader.stop()


def _new_incubator() -> tuple[Incubator, PlateHolder]:
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
    return (
        Incubator(
            backend=IncubatorChatterboxBackend(),
            name="incubator",
            size_x=200,
            size_y=200,
            size_z=300,
            racks=[rack],
            loading_tray_location=Coordinate.zero(),
        ),
        site,
    )


def _require_version() -> None:
    installed = version("pylabrobot")
    if installed != PINNED_PYLABROBOT_VERSION:
        raise PyLabRobotBridgeError(
            "PYLABROBOT_VERSION_MISMATCH",
            f"Expected PyLabRobot {PINNED_PYLABROBOT_VERSION}, found {installed}.",
            details={"expected": PINNED_PYLABROBOT_VERSION, "installed": installed},
        )


def _normalize_error(error: Exception, *, operation: str) -> PyLabRobotBridgeError:
    exception_name = type(error).__name__
    code = {
        "NoTipError": "PYLABROBOT_NO_TIP",
        "TooLittleLiquidError": "PYLABROBOT_TOO_LITTLE_LIQUID",
        "TooLittleVolumeError": "PYLABROBOT_TOO_LITTLE_VOLUME",
        "NoPlateError": "PYLABROBOT_NO_PLATE",
        "NoFreeSiteError": "PYLABROBOT_NO_FREE_SITE",
    }.get(exception_name, "PYLABROBOT_EXECUTION_ERROR")
    return PyLabRobotBridgeError(
        code,
        str(error),
        details={
            "exception_type": f"{type(error).__module__}.{exception_name}",
            "operation": operation,
            "hardware_execution_attempted": False,
        },
    )


def _provider(backend: str) -> dict[str, Any]:
    return {
        "distribution": "pylabrobot",
        "version": PINNED_PYLABROBOT_VERSION,
        "backend": backend,
        "hardware_execution_allowed": False,
        "network_access_required": False,
    }


def _console_evidence(stdout: str, stderr: str) -> dict[str, Any]:
    def describe(value: str) -> dict[str, Any]:
        normalized = "\n".join(
            " ".join(line.split()) for line in value.splitlines() if line.strip()
        )
        return {
            "nonempty_line_count": 0 if not normalized else len(normalized.splitlines()),
            "normalized_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
        }

    return {"stdout": describe(stdout), "stderr": describe(stderr)}


def _normalize_json(value: Any, *, key: str | None = None) -> Any:
    if key in {"time", "timestamp", "created_at", "updated_at"} and isinstance(
        value, (int, float, str)
    ):
        return "<normalized-runtime-timestamp>"
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"kind": "normalized_non_finite_float", "value": "NaN"}
        if math.isinf(value):
            return {
                "kind": "normalized_non_finite_float",
                "value": "Infinity" if value > 0 else "-Infinity",
            }
        return value
    if isinstance(value, Mapping):
        return {
            str(child_key): _normalize_json(child_value, key=str(child_key))
            for child_key, child_value in sorted(
                value.items(), key=lambda item: str(item[0])
            )
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    raise TypeError(f"Unsupported provider result type: {type(value).__name__}")
