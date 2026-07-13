"""Agent tools for the source-grounded Synergy H1 projection."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .dynamics import current_temperature, od600_value
from .state import connect, dumps_json, insert_event, loads_json, resolve_state_db_path


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOL_DEFINITIONS = [
    _tool("inspect_workcell", "Inspect projected reader and plate state (benchmark-local).", {}, []),
    _tool("reader_open", "Open the Synergy H1 tray via PlateReader.open().", {}, []),
    _tool(
        "reader_load_plate",
        "Assign the plate to the reader via PlateReader.assign_child_resource().",
        {"plate_id": {"type": "string"}},
        ["plate_id"],
    ),
    _tool("reader_close", "Close the reader via PlateReader.close().", {}, []),
    _tool(
        "reader_set_temperature",
        "Set heating through SynergyH1Backend.set_temperature().",
        {"temperature_c": {"type": "number", "maximum": 45}},
        ["temperature_c"],
    ),
    _tool(
        "reader_get_temperature",
        "Read temperature through SynergyH1Backend.get_current_temperature().",
        {},
        [],
    ),
    _tool(
        "reader_start_shaking",
        "Start Synergy H1 shaking through SynergyH1Backend.shake(type, setting).",
        {
            "shake_type": {"type": "string", "enum": ["LINEAR", "ORBITAL"]},
            "frequency_setting": {"type": "integer", "minimum": 1, "maximum": 6},
        },
        ["shake_type", "frequency_setting"],
    ),
    _tool("reader_stop_shaking", "Stop shaking via SynergyH1Backend.stop_shaking().", {}, []),
    _tool(
        "reader_stop_temperature",
        "Stop heating via SynergyH1Backend.stop_heating_or_cooling().",
        {},
        [],
    ),
    _tool(
        "advance_logical_time",
        "Advance benchmark logical time without wall-clock waiting (benchmark-local).",
        {"seconds": {"type": "number", "exclusiveMinimum": 0}},
        ["seconds"],
    ),
    _tool(
        "reader_read_absorbance",
        "Read absorbance through PlateReader.read_absorbance(wavelength, wells).",
        {
            "plate_id": {"type": "string"},
            "wavelength_nm": {"type": "integer", "minimum": 230, "maximum": 999},
            "wells": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        },
        ["plate_id", "wavelength_nm", "wells"],
    ),
    _tool(
        "submit_growth_decision",
        "Submit the run-level decision and supporting measurement (benchmark-local).",
        {
            "decision": {"type": "string", "enum": ["accept", "reject"]},
            "evidence_measurement_id": {"type": "string"},
            "rationale": {"type": "string"},
        },
        ["decision", "evidence_measurement_id", "rationale"],
    ),
]


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


def _clock(conn: Any) -> float:
    return float(conn.execute("SELECT time_s FROM clock WHERE singleton = 1").fetchone()[0])


def _refresh_temperature(conn: Any, now_s: float) -> float:
    row = conn.execute("SELECT * FROM reader WHERE singleton = 1").fetchone()
    temperature = current_temperature(
        start_c=float(row["temperature_start_c"]),
        target_c=row["target_temperature_c"],
        set_at_s=row["temperature_set_at_s"],
        now_s=now_s,
    )
    conn.execute(
        "UPDATE reader SET current_temperature_c = ? WHERE singleton = 1",
        (temperature,),
    )
    return temperature


def dispatch_tool(run_dir: Path, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handlers: dict[str, Callable[[Any, dict[str, Any]], dict[str, Any]]] = {
        "inspect_workcell": _inspect,
        "reader_open": _open,
        "reader_load_plate": _load,
        "reader_close": _close,
        "reader_set_temperature": _set_temperature,
        "reader_get_temperature": _get_temperature,
        "reader_start_shaking": _start_shaking,
        "reader_stop_shaking": _stop_shaking,
        "reader_stop_temperature": _stop_temperature,
        "advance_logical_time": _advance_time,
        "reader_read_absorbance": _read_absorbance,
        "submit_growth_decision": _submit,
    }
    handler = handlers.get(name)
    if handler is None:
        return _error("unknown_tool", f"Unknown tool: {name}")
    try:
        with connect(resolve_state_db_path(run_dir)) as conn:
            return handler(conn, arguments)
    except (KeyError, TypeError, ValueError) as exc:
        return _error("invalid_arguments", str(exc))


def _inspect(conn: Any, _arguments: dict[str, Any]) -> dict[str, Any]:
    now = _clock(conn)
    temperature = _refresh_temperature(conn, now)
    reader = dict(conn.execute("SELECT * FROM reader WHERE singleton = 1").fetchone())
    plate = dict(conn.execute("SELECT * FROM plate").fetchone())
    plate["replicate_wells"] = loads_json(plate.pop("replicate_wells_json"))
    insert_event(conn, "workcell.inspected", now)
    return _ok({"clock_time_s": now, "temperature_c": temperature, "reader": reader, "plate": plate})


def _open(conn: Any, _arguments: dict[str, Any]) -> dict[str, Any]:
    now = _clock(conn)
    conn.execute("UPDATE reader SET door_open = 1 WHERE singleton = 1")
    insert_event(conn, "reader.opened", now)
    return _ok({"door_open": True})


def _load(conn: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    plate_id = str(arguments["plate_id"])
    reader = conn.execute("SELECT door_open, loaded_plate_id FROM reader WHERE singleton = 1").fetchone()
    if not reader["door_open"]:
        return _error("reader_door_closed", "Open the reader before loading a plate.")
    if reader["loaded_plate_id"] not in (None, plate_id):
        return _error("reader_already_loaded", "The reader already contains another plate.")
    if conn.execute("SELECT 1 FROM plate WHERE plate_id = ?", (plate_id,)).fetchone() is None:
        return _error("unknown_plate", f"Unknown plate: {plate_id}", plate_id=plate_id)
    conn.execute("UPDATE reader SET loaded_plate_id = ? WHERE singleton = 1", (plate_id,))
    insert_event(conn, "reader.plate_loaded", _clock(conn), {"plate_id": plate_id})
    return _ok({"loaded_plate_id": plate_id})


def _close(conn: Any, _arguments: dict[str, Any]) -> dict[str, Any]:
    now = _clock(conn)
    loaded_plate_id = conn.execute(
        "SELECT loaded_plate_id FROM reader WHERE singleton = 1"
    ).fetchone()[0]
    if loaded_plate_id is None:
        return _error("plate_not_loaded", "Load a plate before closing the reader.")
    conn.execute("UPDATE reader SET door_open = 0 WHERE singleton = 1")
    insert_event(conn, "reader.closed", now)
    return _ok({"door_open": False})


def _set_temperature(conn: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    target = float(arguments["temperature_c"])
    if target > 45.0:
        return _error("temperature_out_of_range", "Synergy H1 heating target must not exceed 45 C.")
    now = _clock(conn)
    current = _refresh_temperature(conn, now)
    if target < current:
        return _error(
            "cooling_unsupported",
            "The Synergy H1 projection supports heating but not active cooling.",
            current_temperature_c=current,
        )
    conn.execute(
        """
        UPDATE reader SET target_temperature_c = ?, current_temperature_c = ?,
          temperature_set_at_s = ?, temperature_start_c = ? WHERE singleton = 1
        """,
        (target, current, now, current),
    )
    insert_event(conn, "reader.temperature_set", now, {"target_c": target})
    return _ok({"target_temperature_c": target})


def _get_temperature(conn: Any, _arguments: dict[str, Any]) -> dict[str, Any]:
    now = _clock(conn)
    temperature = _refresh_temperature(conn, now)
    insert_event(conn, "reader.temperature_observed", now, {"temperature_c": temperature})
    return _ok({"temperature_c": temperature})


def _start_shaking(conn: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    shake_type = str(arguments["shake_type"])
    setting = int(arguments["frequency_setting"])
    if shake_type not in {"LINEAR", "ORBITAL"} or not 1 <= setting <= 6:
        return _error("invalid_shake_setting", "Use LINEAR/ORBITAL and a setting from 1 to 6.")
    reader = conn.execute("SELECT door_open, loaded_plate_id FROM reader WHERE singleton = 1").fetchone()
    if reader["door_open"] or reader["loaded_plate_id"] is None:
        return _error("reader_not_ready", "Load the plate and close the reader before shaking.")
    conn.execute(
        "UPDATE reader SET shaking = 1, shake_type = ?, frequency_setting = ? WHERE singleton = 1",
        (shake_type, setting),
    )
    insert_event(conn, "reader.shaking_started", _clock(conn), {"shake_type": shake_type, "frequency_setting": setting})
    return _ok({"shaking": True, "shake_type": shake_type, "frequency_setting": setting})


def _stop_shaking(conn: Any, _arguments: dict[str, Any]) -> dict[str, Any]:
    conn.execute("UPDATE reader SET shaking = 0 WHERE singleton = 1")
    insert_event(conn, "reader.shaking_stopped", _clock(conn))
    return _ok({"shaking": False})


def _stop_temperature(conn: Any, _arguments: dict[str, Any]) -> dict[str, Any]:
    now = _clock(conn)
    current = _refresh_temperature(conn, now)
    conn.execute(
        """
        UPDATE reader SET target_temperature_c = NULL, temperature_set_at_s = NULL,
          temperature_start_c = ?, current_temperature_c = ? WHERE singleton = 1
        """,
        (current, current),
    )
    insert_event(conn, "reader.temperature_stopped", now)
    return _ok({"temperature_c": current})


def _advance_time(conn: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    seconds = float(arguments["seconds"])
    if seconds <= 0:
        return _error("invalid_time_advance", "seconds must be greater than zero.")
    now = _clock(conn) + seconds
    conn.execute("UPDATE clock SET time_s = ? WHERE singleton = 1", (now,))
    temperature = _refresh_temperature(conn, now)
    insert_event(conn, "clock.advanced", now, {"seconds": seconds})
    return _ok({"clock_time_s": now, "temperature_c": temperature})


def _read_absorbance(conn: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    plate_id = str(arguments["plate_id"])
    wavelength = int(arguments["wavelength_nm"])
    wells = [str(well) for well in arguments["wells"]]
    reader = conn.execute("SELECT * FROM reader WHERE singleton = 1").fetchone()
    if reader["door_open"]:
        return _error("reader_door_open", "Close the reader before measuring absorbance.")
    if reader["loaded_plate_id"] != plate_id:
        return _error("plate_not_loaded", "The requested plate is not loaded.", plate_id=plate_id)
    if not 230 <= wavelength <= 999:
        return _error("wavelength_out_of_range", "Absorbance wavelength must be 230-999 nm.")
    plate = conn.execute("SELECT * FROM plate WHERE plate_id = ?", (plate_id,)).fetchone()
    allowed = set(loads_json(plate["replicate_wells_json"]))
    if not wells or len(wells) != len(set(wells)) or not set(wells).issubset(allowed):
        return _error("invalid_wells", "Wells must be unique members of the configured replicate set.")
    now = _clock(conn)
    temperature = _refresh_temperature(conn, now)
    values = {well: od600_value(time_s=now, replicate_index=int(well[1:]) - 1) for well in wells}
    measurement_id = f"measurement-{conn.execute('SELECT COUNT(*) FROM measurements').fetchone()[0] + 1:04d}"
    conn.execute(
        """
        INSERT INTO measurements(
          measurement_id, time_s, plate_id, plate_version, wavelength_nm,
          wells_json, values_json, temperature_c, shaking
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            measurement_id, now, plate_id, int(plate["version"]), wavelength,
            dumps_json(wells), dumps_json(values), temperature, int(reader["shaking"]),
        ),
    )
    insert_event(conn, "reader.absorbance_measured", now, {"measurement_id": measurement_id})
    return _ok({"measurement_id": measurement_id, "time_s": now, "values": values})


def _submit(conn: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    decision = str(arguments["decision"])
    evidence_id = str(arguments["evidence_measurement_id"])
    rationale = str(arguments["rationale"])
    if decision not in {"accept", "reject"}:
        return _error("invalid_decision", "Decision must be accept or reject.")
    if conn.execute("SELECT 1 FROM measurements WHERE measurement_id = ?", (evidence_id,)).fetchone() is None:
        return _error("unknown_evidence", "Evidence measurement does not exist.", measurement_id=evidence_id)
    now = _clock(conn)
    conn.execute(
        "INSERT INTO submissions(decision, evidence_measurement_id, rationale, time_s) VALUES (?, ?, ?, ?)",
        (decision, evidence_id, rationale, now),
    )
    insert_event(conn, "growth_decision.submitted", now, {"decision": decision, "evidence_measurement_id": evidence_id})
    return _ok({"decision": decision, "evidence_measurement_id": evidence_id})
