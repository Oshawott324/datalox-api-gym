"""Thermocycler and qPCR operations."""

from __future__ import annotations

from typing import Any

from pylabrobot.resources import Coordinate
from pylabrobot.thermocycling import Thermocycler
from pylabrobot.thermocycling.standard import Protocol, Stage, Step

from ..backends import ThermocyclerProgramBackend
from ..dynamics import amplification_series
from ..state import insert_artifact, insert_event, load_state, save_state
from .common import Handler, error, ok, require_family, run_async, tool_definition


TOOL_DEFINITIONS = [
    tool_definition(
        "thermocycler_close_lid",
        "Close the lid through PyLabRobot Thermocycler.close_lid().",
        {},
        [],
    ),
    tool_definition(
        "thermocycler_set_lid_temperature",
        "Set the heated lid through PyLabRobot Thermocycler.set_lid_temperature().",
        {"temperature_c": {"type": "number", "minimum": 30, "maximum": 120}},
        ["temperature_c"],
    ),
    tool_definition(
        "thermocycler_start_protocol",
        "Start the scenario thermal profile through PyLabRobot Thermocycler.run_protocol().",
        {},
        [],
    ),
    tool_definition(
        "thermocycler_advance_time",
        "Advance the running thermal program in accelerated benchmark logical time.",
        {"seconds": {"type": "number", "exclusiveMinimum": 0}},
        ["seconds"],
    ),
    tool_definition(
        "thermocycler_get_status",
        "Read thermal program status through PyLabRobot getters.",
        {},
        [],
    ),
    tool_definition(
        "qpcr_read_amplification",
        "Read the deterministic benchmark qPCR amplification artifact after the thermal program completes.",
        {},
        [],
    ),
    tool_definition(
        "thermocycler_open_lid",
        "Open the lid through PyLabRobot Thermocycler.open_lid().",
        {},
        [],
    ),
]


def _thermocycler(
    state: dict[str, Any],
) -> tuple[Thermocycler, ThermocyclerProgramBackend]:
    backend = ThermocyclerProgramBackend(state["thermocycler"])
    instrument = Thermocycler(
        name="qpcr_thermocycler",
        size_x=300,
        size_y=400,
        size_z=300,
        backend=backend,
        child_location=Coordinate.zero(),
    )
    run_async(instrument.setup())
    return instrument, backend


def _persist_thermocycler(
    conn: Any,
    state: dict[str, Any],
    backend: ThermocyclerProgramBackend,
) -> None:
    state["thermocycler"] = backend.serialize()
    save_state(conn, state)


def _close_lid(
    conn: Any,
    _arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "thermocycler")
    if invalid:
        return invalid
    instrument, backend = _thermocycler(state)
    run_async(instrument.close_lid())
    state["clock_s"] += 2.0
    _persist_thermocycler(conn, state, backend)
    payload = {"lid_open": False}
    insert_event(
        conn,
        operation="thermocycler.lid_closed",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _set_lid_temperature(
    conn: Any,
    arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "thermocycler")
    if invalid:
        return invalid
    temperature = float(arguments["temperature_c"])
    instrument, backend = _thermocycler(state)
    run_async(instrument.set_lid_temperature([temperature]))
    state["clock_s"] += 1.0
    _persist_thermocycler(conn, state, backend)
    payload = {"lid_target_temperature_c": temperature}
    insert_event(
        conn,
        operation="thermocycler.lid_temperature_set",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _protocol(contract: dict[str, Any]) -> Protocol:
    stages = []
    for stage in contract["protocol"]:
        steps = [
            Step(
                temperature=[float(item["temperature_c"])],
                hold_seconds=float(item["hold_seconds"]),
            )
            for item in stage["steps"]
        ]
        stages.append(Stage(steps=steps, repeats=int(stage["repeats"])))
    return Protocol(stages=stages)


def _start_protocol(
    conn: Any,
    _arguments: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "thermocycler")
    if invalid:
        return invalid
    instrument, backend = _thermocycler(state)
    run_async(
        instrument.run_protocol(
            _protocol(contract),
            block_max_volume=float(contract["block_max_volume_ul"]),
        )
    )
    state["clock_s"] += 1.0
    _persist_thermocycler(conn, state, backend)
    payload = {
        "running": True,
        "total_duration_s": backend.total_duration_s,
        "total_steps": len(backend.timeline),
        "total_cycles": run_async(instrument.get_total_cycle_count()),
    }
    insert_event(
        conn,
        operation="thermocycler.protocol_started",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _advance_time(
    conn: Any,
    arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "thermocycler")
    if invalid:
        return invalid
    seconds = float(arguments["seconds"])
    instrument, backend = _thermocycler(state)
    backend.advance(seconds)
    state["clock_s"] += seconds
    _persist_thermocycler(conn, state, backend)
    payload = _status_payload(instrument, backend)
    payload["advanced_seconds"] = seconds
    insert_event(
        conn,
        operation="thermocycler.time_advanced",
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
    invalid = require_family(state, "thermocycler")
    if invalid:
        return invalid
    instrument, backend = _thermocycler(state)
    payload = _status_payload(instrument, backend)
    insert_event(
        conn,
        operation="thermocycler.status_read",
        time_s=state["clock_s"],
        payload=payload,
    )
    return ok(payload)


def _status_payload(
    instrument: Thermocycler,
    backend: ThermocyclerProgramBackend,
) -> dict[str, Any]:
    current = backend.current_step
    return {
        "running": backend.running,
        "completed": backend.completed,
        "lid_open": run_async(instrument.get_lid_open()),
        "lid_temperature_c": run_async(instrument.get_lid_current_temperature())[0],
        "block_temperature_c": run_async(instrument.get_block_current_temperature())[0],
        "elapsed_s": backend.elapsed_s,
        "total_duration_s": backend.total_duration_s,
        "cycle_index": run_async(instrument.get_current_cycle_index()),
        "total_cycles": run_async(instrument.get_total_cycle_count()),
        "step_index": run_async(instrument.get_current_step_index()),
        "total_steps": run_async(instrument.get_total_step_count()),
        "stage_index": None if current is None else current["stage_index"],
        "hold_elapsed_s": run_async(instrument.get_hold_time()),
        "hold_total_s": None if current is None else current["hold_seconds"],
    }


def _read_amplification(
    conn: Any,
    _arguments: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "thermocycler")
    if invalid:
        return invalid
    backend = ThermocyclerProgramBackend(state["thermocycler"])
    if not backend.completed:
        return error(
            "protocol_incomplete",
            "Complete the thermal program before reading amplification.",
        )
    wells = contract["amplification_wells"]
    artifact_id = "qpcr-amplification-001"
    payload = {
        "artifact_id": artifact_id,
        "cycles": list(range(1, 41)),
        "series": amplification_series(wells),
        "calls": {well: config for well, config in wells.items()},
        "controls_valid": wells["A1"]["ct"] is not None and wells["A2"]["ct"] is None,
        "grounding": "benchmark_defined_qpcr_projection",
    }
    insert_artifact(
        conn,
        artifact_id=artifact_id,
        kind="qpcr_amplification",
        time_s=state["clock_s"],
        payload=payload,
    )
    insert_event(
        conn,
        operation="qpcr.amplification_read",
        time_s=state["clock_s"],
        payload={"artifact_id": artifact_id},
    )
    return ok(payload)


def _open_lid(
    conn: Any,
    _arguments: dict[str, Any],
    _contract: dict[str, Any],
) -> dict[str, Any]:
    state = load_state(conn)
    invalid = require_family(state, "thermocycler")
    if invalid:
        return invalid
    instrument, backend = _thermocycler(state)
    run_async(instrument.open_lid())
    state["clock_s"] += 2.0
    _persist_thermocycler(conn, state, backend)
    insert_event(
        conn,
        operation="thermocycler.lid_opened",
        time_s=state["clock_s"],
        payload={"lid_open": True},
    )
    return ok({"lid_open": True})


HANDLERS: dict[str, Handler] = {
    "thermocycler_close_lid": _close_lid,
    "thermocycler_set_lid_temperature": _set_lid_temperature,
    "thermocycler_start_protocol": _start_protocol,
    "thermocycler_advance_time": _advance_time,
    "thermocycler_get_status": _get_status,
    "qpcr_read_amplification": _read_amplification,
    "thermocycler_open_lid": _open_lid,
}
