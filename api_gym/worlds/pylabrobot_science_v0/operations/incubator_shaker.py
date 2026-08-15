"""Incubator-shaker and plate-reader operations."""

from __future__ import annotations

from typing import Any

from pylabrobot.plate_reading import PlateReader
from pylabrobot.resources import Coordinate
from pylabrobot.resources.carrier import PlateCarrier, PlateHolder
from pylabrobot.storage import Incubator

from ..backends import GrowthPlateReaderBackend, IncubatorProjectionBackend
from ..dynamics import growth_od600, ramp_temperature
from ..state import insert_artifact, insert_event, load_state, save_state
from .common import Handler, error, ok, require_family, run_async, tool_definition


TOOL_DEFINITIONS = [
    tool_definition(
        "incubator_set_temperature",
        "Set the incubator target through PyLabRobot Incubator.set_temperature().",
        {"temperature_c": {"type": "number", "minimum": 4, "maximum": 60}},
        ["temperature_c"],
    ),
    tool_definition(
        "incubator_start_shaking",
        "Start orbital shaking through PyLabRobot Incubator.start_shaking().",
        {"rpm": {"type": "number", "minimum": 1, "maximum": 1200}},
        ["rpm"],
    ),
    tool_definition(
        "incubator_store_plate",
        "Move the plate from the loading tray into a named incubator slot.",
        {"slot": {"type": "string", "pattern": "^S0[1-8]$"}},
        ["slot"],
    ),
    tool_definition(
        "incubator_retrieve_plate",
        "Move the culture plate from storage to the loading tray.",
        {},
        [],
    ),
    tool_definition(
        "incubator_advance_time",
        "Advance incubation logical time, temperature ramp, and conditioned shaking exposure.",
        {"seconds": {"type": "number", "exclusiveMinimum": 0}},
        ["seconds"],
    ),
    tool_definition(
        "incubator_get_status",
        "Read incubator temperature, storage, and shaking status.",
        {},
        [],
    ),
    tool_definition(
        "reader_measure_od600",
        "Measure A1-A8 at 600 nm through a separate PyLabRobot PlateReader interface.",
        {},
        [],
    ),
]


def _incubator(
    state: dict[str, Any],
) -> tuple[Incubator, IncubatorProjectionBackend]:
    backend = IncubatorProjectionBackend(state["incubator"])
    sites: dict[int, PlateHolder] = {}
    for index in range(8):
        site = PlateHolder(
            name=f"S{index + 1:02d}",
            size_x=130,
            size_y=90,
            size_z=20,
            pedestal_size_z=0,
            child_location=Coordinate.zero(),
        )
        site.location = Coordinate(x=0, y=index * 30, z=0)
        sites[index] = site
    rack = PlateCarrier(
        name="incubator_rack",
        size_x=500,
        size_y=300,
        size_z=300,
        sites=sites,
    )
    instrument = Incubator(
        backend=backend,
        name="orbital_incubator",
        size_x=800,
        size_y=600,
        size_z=800,
        racks=[rack],
        loading_tray_location=Coordinate(x=0, y=300, z=100),
    )
    from api_gym.worlds.pylabrobot_lab_v0.state import create_plate

    plate = create_plate(state["plate"]["plate_id"])
    location = state["plate"]["location"]
    if location == "loading_tray":
        instrument.loading_tray.assign_child_resource(plate)
    elif location in state["incubator"]["slots"]:
        site = next(item for item in sites.values() if item.name == location)
        site.assign_child_resource(plate)
    run_async(instrument.setup())
    return instrument, backend


def _persist_incubator(
    conn: Any,
    state: dict[str, Any],
    backend: IncubatorProjectionBackend,
) -> None:
    preserved = {
        "slots": state["incubator"]["slots"],
        "conditioned_exposure_s": state["incubator"]["conditioned_exposure_s"],
    }
    state["incubator"] = {**backend.serialize(), **preserved}
    save_state(conn, state)


def _set_temperature(
    conn: Any,
    arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "incubator_shaker")
    if invalid:
        return invalid
    target = float(arguments["temperature_c"])
    instrument, backend = _incubator(state)
    run_async(instrument.set_temperature(target))
    _persist_incubator(conn, state, backend)
    payload = {
        "target_temperature_c": target,
        "current_temperature_c": backend.current_temperature_c,
    }
    insert_event(
        conn,
        operation="incubator.temperature_set",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _start_shaking(
    conn: Any,
    arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "incubator_shaker")
    if invalid:
        return invalid
    rpm = float(arguments["rpm"])
    instrument, backend = _incubator(state)
    run_async(instrument.start_shaking(frequency=rpm))
    _persist_incubator(conn, state, backend)
    payload = {"shaking": True, "shake_rpm": rpm}
    insert_event(
        conn,
        operation="incubator.shaking_started",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _store_plate(
    conn: Any,
    arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "incubator_shaker")
    if invalid:
        return invalid
    slot = str(arguments["slot"])
    if slot not in state["incubator"]["slots"]:
        return error(
            "unknown_storage_slot",
            "Use a configured storage slot S01-S08.",
            slot=slot,
        )
    if state["plate"]["location"] != "loading_tray":
        return error(
            "plate_not_on_loading_tray",
            "Retrieve the plate before storing it again.",
        )
    if state["incubator"]["slots"][slot] is not None:
        return error(
            "storage_slot_occupied",
            "The selected storage slot is occupied.",
            slot=slot,
        )
    instrument, backend = _incubator(state)
    site = next(
        item for item in instrument._racks[0].sites.values() if item.name == slot
    )
    run_async(instrument.take_in_plate(site=site))
    state["plate"]["location"] = slot
    state["incubator"]["slots"][slot] = state["plate"]["plate_id"]
    _persist_incubator(conn, state, backend)
    payload = {"plate_id": state["plate"]["plate_id"], "slot": slot}
    insert_event(
        conn,
        operation="incubator.plate_stored",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _retrieve_plate(
    conn: Any,
    _arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "incubator_shaker")
    if invalid:
        return invalid
    location = state["plate"]["location"]
    if location == "loading_tray":
        return error(
            "plate_already_retrieved",
            "The plate is already on the loading tray.",
        )
    instrument, backend = _incubator(state)
    run_async(
        instrument.fetch_plate_to_loading_tray(plate_name=state["plate"]["plate_id"])
    )
    state["incubator"]["slots"][location] = None
    state["plate"]["location"] = "loading_tray"
    _persist_incubator(conn, state, backend)
    payload = {"plate_id": state["plate"]["plate_id"], "from_slot": location}
    insert_event(
        conn,
        operation="incubator.plate_retrieved",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _advance_time(
    conn: Any,
    arguments: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "incubator_shaker")
    if invalid:
        return invalid
    seconds = float(arguments["seconds"])
    if seconds <= 0:
        return error("invalid_time_advance", "seconds must be greater than zero.")
    incubator = state["incubator"]
    target = incubator["target_temperature_c"]
    current = float(incubator["current_temperature_c"])
    tolerance = float(contract["temperature_tolerance_c"])
    rate = float(contract["temperature_ramp_c_per_s"])
    conditioned_seconds = 0.0
    plate_stored = state["plate"]["location"] in incubator["slots"]
    if (
        target is not None
        and plate_stored
        and incubator["shaking"]
        and not incubator["door_open"]
    ):
        time_to_tolerance = max(
            0.0,
            (abs(float(target) - current) - tolerance) / rate,
        )
        conditioned_seconds = max(0.0, seconds - time_to_tolerance)
    if target is not None:
        incubator["current_temperature_c"] = ramp_temperature(
            current_c=current,
            target_c=float(target),
            seconds=seconds,
            rate_c_per_s=rate,
        )
    incubator["conditioned_exposure_s"] += conditioned_seconds
    state["clock_s"] += seconds
    save_state(conn, state)
    payload = {
        "advanced_seconds": seconds,
        "clock_s": state["clock_s"],
        "current_temperature_c": incubator["current_temperature_c"],
        "conditioned_exposure_s": round(incubator["conditioned_exposure_s"], 3),
        "plate_location": state["plate"]["location"],
        "shaking": incubator["shaking"],
    }
    insert_event(
        conn,
        operation="incubator.time_advanced",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _get_status(
    conn: Any,
    _arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "incubator_shaker")
    if invalid:
        return invalid
    instrument, _backend = _incubator(state)
    current = run_async(instrument.get_temperature())
    payload = {
        "clock_s": state["clock_s"],
        "current_temperature_c": current,
        "target_temperature_c": state["incubator"]["target_temperature_c"],
        "shaking": state["incubator"]["shaking"],
        "shake_rpm": state["incubator"]["shake_rpm"],
        "conditioned_exposure_s": state["incubator"]["conditioned_exposure_s"],
        "plate_location": state["plate"]["location"],
        "slots": state["incubator"]["slots"],
    }
    insert_event(
        conn,
        operation="incubator.status_read",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _measure_od600(
    conn: Any,
    _arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "incubator_shaker")
    if invalid:
        return invalid
    if state["plate"]["location"] != "loading_tray":
        return error(
            "plate_not_at_reader",
            "Retrieve the plate to the loading tray before reading OD600.",
        )
    wells = [f"A{i}" for i in range(1, 9)]
    values = [
        growth_od600(time_s=float(state["clock_s"]), replicate_index=i)
        for i in range(8)
    ]
    backend = GrowthPlateReaderBackend(
        values,
        time_s=float(state["clock_s"]),
        temperature_c=float(state["incubator"]["current_temperature_c"]),
    )
    reader = PlateReader(
        name="od600_reader",
        size_x=200,
        size_y=300,
        size_z=200,
        backend=backend,
    )
    from api_gym.worlds.pylabrobot_lab_v0.state import create_plate

    plate = create_plate(state["plate"]["plate_id"])
    reader.assign_child_resource(plate, location=Coordinate.zero())
    run_async(reader.setup())
    selected_wells = [plate.get_item(well) for well in wells]
    result = run_async(
        reader.read_absorbance(
            wavelength=600,
            wells=selected_wells,
            use_new_return_type=True,
        )
    )
    state["measurement_count"] += 1
    save_state(conn, state)
    artifact_id = f"od600-{state['measurement_count']:03d}"
    payload = {
        "artifact_id": artifact_id,
        "plate_id": state["plate"]["plate_id"],
        "barcode": state["plate"]["barcode"],
        "plate_version": state["plate"]["version"],
        "time_s": state["clock_s"],
        "wavelength_nm": 600,
        "wells": wells,
        "values": dict(zip(wells, result[0]["data"][0])),
        "grounding": "pylabrobot_plate_reader_with_benchmark_growth_projection",
    }
    insert_artifact(
        conn,
        artifact_id=artifact_id,
        kind="od600_measurement",
        time_s=state["clock_s"],
        payload=payload,
    )
    insert_event(
        conn,
        operation="reader.od600_measured",
        time_s=state["clock_s"],
        payload={"artifact_id": artifact_id},
    )
    return ok(payload)


HANDLERS: dict[str, Handler] = {
    "incubator_set_temperature": _set_temperature,
    "incubator_start_shaking": _start_shaking,
    "incubator_store_plate": _store_plate,
    "incubator_retrieve_plate": _retrieve_plate,
    "incubator_advance_time": _advance_time,
    "incubator_get_status": _get_status,
    "reader_measure_od600": _measure_od600,
}
