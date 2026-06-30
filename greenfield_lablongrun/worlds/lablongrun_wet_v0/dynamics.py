"""Wet-lab state transitions for the LabLongRun-Wet v0 prototype."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from greenfield_lablongrun.core.schemas import ActionError, tool_ok
from greenfield_lablongrun.worlds.lablongrun_wet_v0 import state


DEAD_VOLUME_UL = 5.0


def get_deck_state(db_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    with state.connect(db_path) as conn:
        labware = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, kind, display_name, slot
                FROM labware
                WHERE visible_to_agent = 1
                ORDER BY slot, id
                """
            ).fetchall()
        ]
        pipette = dict(conn.execute("SELECT * FROM pipette_state WHERE id = ?", ("p300_single",)).fetchone())
    return tool_ok({"labware": labware, "pipette": _public_pipette(pipette)}), {"observed": ["deck", "pipette"]}


def get_labware_state(db_path: Path, labware_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    with state.connect(db_path) as conn:
        labware = conn.execute("SELECT * FROM labware WHERE id = ?", (labware_id,)).fetchone()
        if labware is None:
            raise ActionError("UNKNOWN_LABWARE", f"No labware exists with id {labware_id!r}.")
        wells = [
            state.row_to_well(row)
            for row in conn.execute(
                """
                SELECT * FROM wells
                WHERE labware_id = ?
                ORDER BY well_id
                """,
                (labware_id,),
            ).fetchall()
        ]
        tips = [
            {
                "tip_ref": row["tip_ref"],
                "status": row["status"],
                "touched_wells": state.loads_json(row["touched_wells_json"]) or [],
            }
            for row in conn.execute(
                """
                SELECT * FROM tips
                WHERE tip_ref LIKE ?
                ORDER BY tip_ref
                """,
                (f"{labware_id}:%",),
            ).fetchall()
        ]
    return tool_ok({"labware": dict(labware), "wells": wells, "tips": tips}), {"observed": [labware_id]}


def pick_up_tip(db_path: Path, tip_ref: str) -> tuple[dict[str, Any], dict[str, Any]]:
    with state.connect(db_path) as conn:
        pipette = _get_pipette(conn)
        if pipette["current_tip"] is not None:
            raise ActionError("TIP_ALREADY_ATTACHED", "Drop the current tip before picking up another.")
        tip = conn.execute("SELECT * FROM tips WHERE tip_ref = ?", (tip_ref,)).fetchone()
        if tip is None:
            raise ActionError("UNKNOWN_TIP", f"No tip exists with reference {tip_ref!r}.")
        if tip["status"] != "clean":
            raise ActionError("TIP_NOT_CLEAN", f"Tip {tip_ref} has status {tip['status']!r}.")
        conn.execute("UPDATE tips SET status = ? WHERE tip_ref = ?", ("attached", tip_ref))
        conn.execute(
            """
            UPDATE pipette_state
            SET current_tip = ?, held_volume_ul = 0, held_cell_signal = 0,
                held_source_ref = NULL, touched_wells_json = '[]'
            WHERE id = ?
            """,
            (tip_ref, "p300_single"),
        )
        _record_action(conn, "pick_up_tip", target_ref=tip_ref, tip_ref=tip_ref)
    return tool_ok({"tip_ref": tip_ref, "status": "attached"}), {"tip": {"ref": tip_ref, "status": "attached"}}


def drop_tip(db_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    with state.connect(db_path) as conn:
        pipette = _get_pipette(conn)
        tip_ref = pipette["current_tip"]
        if tip_ref is None:
            raise ActionError("NO_TIP_ATTACHED", "Pick up a tip before dropping one.")
        if float(pipette["held_volume_ul"]) > 0:
            raise ActionError(
                "TIP_CONTAINS_LIQUID",
                "Dispense held liquid before dropping the tip.",
                {"held_volume_ul": pipette["held_volume_ul"]},
            )
        touched = state.loads_json(pipette["touched_wells_json"]) or []
        conn.execute(
            "UPDATE tips SET status = ?, touched_wells_json = ? WHERE tip_ref = ?",
            ("used", state.dumps_json(touched), tip_ref),
        )
        conn.execute(
            """
            UPDATE pipette_state
            SET current_tip = NULL, held_volume_ul = 0, held_cell_signal = 0,
                held_source_ref = NULL, touched_wells_json = '[]'
            WHERE id = ?
            """,
            ("p300_single",),
        )
        _record_action(conn, "drop_tip", source_ref=tip_ref, tip_ref=tip_ref)
    return tool_ok({"tip_ref": tip_ref, "status": "used"}), {"tip": {"ref": tip_ref, "status": "used"}}


def aspirate(db_path: Path, well_ref: str, volume_ul: float) -> tuple[dict[str, Any], dict[str, Any]]:
    if volume_ul <= 0:
        raise ActionError("INVALID_VOLUME", "Aspirate volume must be positive.", {"volume_ul": volume_ul})
    with state.connect(db_path) as conn:
        pipette = _get_pipette(conn)
        tip_ref = _require_tip(pipette)
        max_volume = float(state.get_metadata(conn, "pipette_max_volume_ul", 200.0))
        held_volume = float(pipette["held_volume_ul"])
        if held_volume + volume_ul > max_volume:
            raise ActionError(
                "PIPETTE_CAPACITY_EXCEEDED",
                "Requested aspirate would exceed pipette capacity.",
                {"held_volume_ul": held_volume, "volume_ul": volume_ul, "max_volume_ul": max_volume},
            )
        labware_id, well_id = state.parse_well_ref(well_ref)
        well = _get_well(conn, labware_id, well_id)
        source_volume = float(well["volume_ul"])
        available = max(0.0, source_volume - DEAD_VOLUME_UL)
        if volume_ul > available:
            raise ActionError(
                "OVERDRAW_SOURCE_WELL",
                f"Requested {volume_ul} uL from {well_ref}, but only {available:.2f} uL is available above dead volume.",
                {"well_ref": well_ref, "volume_ul": volume_ul, "available_ul": round(available, 6)},
            )
        _record_cross_contact_if_needed(conn, well, well_ref, pipette, tip_ref)
        fraction = volume_ul / source_volume
        moved_signal = float(well["cell_signal"]) * fraction
        conn.execute(
            """
            UPDATE wells
            SET volume_ul = volume_ul - ?, cell_signal = cell_signal - ?
            WHERE labware_id = ? AND well_id = ?
            """,
            (volume_ul, moved_signal, labware_id, well_id),
        )
        conn.execute(
            """
            UPDATE pipette_state
            SET held_volume_ul = held_volume_ul + ?,
                held_cell_signal = held_cell_signal + ?,
                held_source_ref = ?
            WHERE id = ?
            """,
            (volume_ul, moved_signal, well_ref, "p300_single"),
        )
        _append_pipette_touch(conn, well_ref)
        _record_action(conn, "aspirate", source_ref=well_ref, volume_ul=volume_ul, tip_ref=tip_ref)
    return (
        tool_ok({"well_ref": well_ref, "volume_ul": volume_ul, "tip_ref": tip_ref}),
        {"well_volume_delta": {well_ref: -volume_ul}, "pipette_held_delta_ul": volume_ul},
    )


def dispense(db_path: Path, well_ref: str, volume_ul: float) -> tuple[dict[str, Any], dict[str, Any]]:
    if volume_ul <= 0:
        raise ActionError("INVALID_VOLUME", "Dispense volume must be positive.", {"volume_ul": volume_ul})
    with state.connect(db_path) as conn:
        pipette = _get_pipette(conn)
        tip_ref = _require_tip(pipette)
        held_volume = float(pipette["held_volume_ul"])
        if volume_ul > held_volume:
            raise ActionError(
                "DISPENSE_EXCEEDS_HELD_VOLUME",
                "Cannot dispense more liquid than the pipette holds.",
                {"volume_ul": volume_ul, "held_volume_ul": held_volume},
            )
        labware_id, well_id = state.parse_well_ref(well_ref)
        _get_well(conn, labware_id, well_id)
        requested_volume = volume_ul
        partial = _maybe_apply_partial_dispense(conn, well_ref, requested_volume)
        if partial:
            volume_ul = float(partial["delivered_volume_ul"])
        fraction = volume_ul / held_volume if held_volume else 0.0
        moved_signal = float(pipette["held_cell_signal"]) * fraction
        conn.execute(
            """
            UPDATE wells
            SET volume_ul = volume_ul + ?, cell_signal = cell_signal + ?, mixed = 0
            WHERE labware_id = ? AND well_id = ?
            """,
            (volume_ul, moved_signal, labware_id, well_id),
        )
        conn.execute(
            """
            UPDATE pipette_state
            SET held_volume_ul = held_volume_ul - ?,
                held_cell_signal = held_cell_signal - ?
            WHERE id = ?
            """,
            (volume_ul, moved_signal, "p300_single"),
        )
        _append_pipette_touch(conn, well_ref)
        _append_well_touch(conn, labware_id, well_id, tip_ref)
        _record_action(
            conn,
            "dispense",
            target_ref=well_ref,
            volume_ul=volume_ul,
            tip_ref=tip_ref,
            payload={
                "requested_volume_ul": requested_volume,
                "delivered_volume_ul": volume_ul,
                "partial_dispense": bool(partial),
            },
        )
    return (
        tool_ok(
            {
                "well_ref": well_ref,
                "volume_ul": requested_volume,
                "delivered_volume_ul": volume_ul,
                "tip_ref": tip_ref,
                "partial_dispense": bool(partial),
            }
        ),
        {"well_volume_delta": {well_ref: volume_ul}, "pipette_held_delta_ul": -volume_ul},
    )


def mix(db_path: Path, well_ref: str, repetitions: int, volume_ul: float) -> tuple[dict[str, Any], dict[str, Any]]:
    if repetitions <= 0:
        raise ActionError("INVALID_REPETITIONS", "Mix repetitions must be positive.", {"repetitions": repetitions})
    if volume_ul <= 0:
        raise ActionError("INVALID_VOLUME", "Mix volume must be positive.", {"volume_ul": volume_ul})
    with state.connect(db_path) as conn:
        pipette = _get_pipette(conn)
        tip_ref = _require_tip(pipette)
        labware_id, well_id = state.parse_well_ref(well_ref)
        well = _get_well(conn, labware_id, well_id)
        if float(well["volume_ul"]) < volume_ul:
            raise ActionError(
                "MIX_VOLUME_EXCEEDS_WELL_VOLUME",
                "Cannot mix with a volume larger than the well volume.",
                {"well_ref": well_ref, "volume_ul": volume_ul, "well_volume_ul": well["volume_ul"]},
            )
        conn.execute("UPDATE wells SET mixed = 1 WHERE labware_id = ? AND well_id = ?", (labware_id, well_id))
        conn.execute(
            "INSERT INTO mixes (id, well_ref, repetitions, volume_ul, tip_ref, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (state.next_id(conn, "mix"), well_ref, repetitions, volume_ul, tip_ref, state.next_timestamp(conn)),
        )
        _append_pipette_touch(conn, well_ref)
        _append_well_touch(conn, labware_id, well_id, tip_ref)
    return tool_ok({"well_ref": well_ref, "repetitions": repetitions, "volume_ul": volume_ul}), {"mixed": [well_ref]}


def wait(db_path: Path, seconds: float, reason: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if seconds <= 0:
        raise ActionError("INVALID_DELAY", "Wait duration must be positive.", {"seconds": seconds})
    with state.connect(db_path) as conn:
        accumulated = float(state.get_metadata(conn, "accumulated_wait_seconds", 0.0))
        state.set_metadata(conn, "accumulated_wait_seconds", round(accumulated + seconds, 6))
        conn.execute(
            "INSERT INTO delays (id, seconds, reason, created_at) VALUES (?, ?, ?, ?)",
            (state.next_id(conn, "delay"), seconds, reason, state.next_timestamp(conn)),
        )
    return tool_ok({"seconds": seconds, "reason": reason}), {"logical_wait_seconds": seconds}


def read_absorbance(
    db_path: Path,
    well_ref: str,
    wavelength_nm: int,
    dilution_factor: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if wavelength_nm != 600:
        raise ActionError("UNSUPPORTED_WAVELENGTH", "Phase 1 only supports OD600 readout.", {"wavelength_nm": wavelength_nm})
    if dilution_factor <= 0:
        raise ActionError("INVALID_DILUTION_FACTOR", "Dilution factor must be positive.", {"dilution_factor": dilution_factor})
    with state.connect(db_path) as conn:
        reader_busy_until = state.get_metadata(conn, "reader_busy_until_wait_seconds")
        if reader_busy_until is not None:
            accumulated = float(state.get_metadata(conn, "accumulated_wait_seconds", 0.0))
            if accumulated < float(reader_busy_until):
                raise ActionError(
                    "READER_BUSY",
                    "Plate reader is still busy; wait until the scheduled dry-run ready time.",
                    {
                        "required_wait_seconds": float(reader_busy_until),
                        "accumulated_wait_seconds": accumulated,
                    },
                )
        labware_id, well_id = state.parse_well_ref(well_ref)
        well = _get_well(conn, labware_id, well_id)
        raw_value = state.raw_od600(float(well["volume_ul"]), float(well["cell_signal"]))
        if raw_value is None:
            raise ActionError("EMPTY_READ_WELL", "Cannot read absorbance from an empty well.", {"well_ref": well_ref})
        readout_id = state.next_id(conn, "readout")
        corrected = round(raw_value * dilution_factor, 6)
        conn.execute(
            """
            INSERT INTO od_readouts (
              id, plate_id, well_id, wavelength_nm, raw_od600, corrected_od600,
              dilution_factor, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (readout_id, labware_id, well_id, wavelength_nm, raw_value, corrected, dilution_factor, state.next_timestamp(conn)),
        )
    return (
        tool_ok(
            {
                "readout_id": readout_id,
                "well_ref": well_ref,
                "wavelength_nm": wavelength_nm,
                "raw_od600": raw_value,
                "corrected_od600": corrected,
                "dilution_factor": dilution_factor,
            }
        ),
        {"readout_created": readout_id},
    )


def add_workflow_note(db_path: Path, note: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not note.strip():
        raise ActionError("EMPTY_NOTE", "Workflow note must not be empty.")
    with state.connect(db_path) as conn:
        note_id = state.next_id(conn, "note")
        conn.execute(
            "INSERT INTO lab_notes (id, note, created_at) VALUES (?, ?, ?)",
            (note_id, note, state.next_timestamp(conn)),
        )
    return tool_ok({"note_id": note_id}), {"note_created": note_id}


def submit_protocol_decision(
    db_path: Path,
    decision: str,
    evidence_readout_id: str,
    target_well_ref: str,
    rationale: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if decision not in {"continue", "hold"}:
        raise ActionError("INVALID_DECISION", "Decision must be 'continue' or 'hold'.", {"decision": decision})
    if not rationale.strip():
        raise ActionError("MISSING_RATIONALE", "Protocol decision must include rationale.")
    with state.connect(db_path) as conn:
        readout = conn.execute("SELECT * FROM od_readouts WHERE id = ?", (evidence_readout_id,)).fetchone()
        if readout is None:
            raise ActionError(
                "UNKNOWN_READOUT",
                "Protocol decision must cite a readout produced in this run.",
                {"evidence_readout_id": evidence_readout_id},
            )
        plate_id, well_id = state.parse_well_ref(target_well_ref)
        if readout["plate_id"] != plate_id or readout["well_id"] != well_id:
            raise ActionError(
                "READOUT_TARGET_MISMATCH",
                "Cited readout does not match the submitted target well.",
                {"evidence_readout_id": evidence_readout_id, "target_well_ref": target_well_ref},
            )
        submission_id = state.next_id(conn, "submission")
        conn.execute(
            """
            INSERT INTO qc_submissions (
              id, decision, evidence_readout_id, target_well_ref, rationale,
              evidence_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (submission_id, decision, evidence_readout_id, target_well_ref, rationale, "valid", state.next_timestamp(conn)),
        )
    return (
        tool_ok(
            {
                "submission_id": submission_id,
                "decision": decision,
                "evidence_readout_id": evidence_readout_id,
                "target_well_ref": target_well_ref,
            }
        ),
        {"submission_created": submission_id, "decision": decision},
    )


def _get_pipette(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM pipette_state WHERE id = ?", ("p300_single",)).fetchone()
    if row is None:
        raise ActionError("PIPETTE_NOT_FOUND", "Expected p300_single pipette is missing.")
    return row


def _public_pipette(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "current_tip": row["current_tip"],
        "held_volume_ul": row["held_volume_ul"],
    }


def _require_tip(pipette: sqlite3.Row) -> str:
    tip_ref = pipette["current_tip"]
    if tip_ref is None:
        raise ActionError("NO_TIP_ATTACHED", "Pick up a tip before liquid handling.")
    return str(tip_ref)


def _get_well(conn: sqlite3.Connection, labware_id: str, well_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM wells WHERE labware_id = ? AND well_id = ?",
        (labware_id, well_id),
    ).fetchone()
    if row is None:
        raise ActionError("UNKNOWN_WELL", f"No well exists at {state.well_ref(labware_id, well_id)!r}.")
    return row


def _append_pipette_touch(conn: sqlite3.Connection, well_ref: str) -> None:
    pipette = _get_pipette(conn)
    touched = state.loads_json(pipette["touched_wells_json"]) or []
    if well_ref not in touched:
        touched.append(well_ref)
    conn.execute(
        "UPDATE pipette_state SET touched_wells_json = ? WHERE id = ?",
        (state.dumps_json(touched), "p300_single"),
    )


def _append_well_touch(conn: sqlite3.Connection, labware_id: str, well_id: str, tip_ref: str) -> None:
    well = _get_well(conn, labware_id, well_id)
    touched = state.loads_json(well["touched_by_tip_json"]) or []
    if tip_ref not in touched:
        touched.append(tip_ref)
    conn.execute(
        "UPDATE wells SET touched_by_tip_json = ? WHERE labware_id = ? AND well_id = ?",
        (state.dumps_json(touched), labware_id, well_id),
    )


def _record_cross_contact_if_needed(
    conn: sqlite3.Connection,
    well: sqlite3.Row,
    well_ref: str,
    pipette: sqlite3.Row,
    tip_ref: str,
) -> None:
    metadata = state.loads_json(well["metadata_json"]) or {}
    touched = state.loads_json(pipette["touched_wells_json"]) or []
    if metadata.get("contents") != "sterile_diluent" or not touched:
        return
    risky_touches = [ref for ref in touched if ref != well_ref]
    if not risky_touches:
        return
    _record_contamination(
        conn,
        tip_ref=tip_ref,
        source_ref=well_ref,
        risk_code="STERILE_DILUENT_TOUCHED_AFTER_SAMPLE",
        details={"prior_touched_wells": risky_touches},
    )


def _maybe_apply_partial_dispense(
    conn: sqlite3.Connection,
    well_ref: str,
    requested_volume_ul: float,
) -> dict[str, Any] | None:
    event = state.get_metadata(conn, "partial_dispense_once")
    if not isinstance(event, dict) or event.get("applied"):
        return None
    if event.get("target_well_ref") != well_ref:
        return None
    if abs(float(event.get("requested_volume_ul", 0.0)) - requested_volume_ul) > 0.0001:
        return None
    event = dict(event)
    event["applied"] = True
    state.set_metadata(conn, "partial_dispense_once", event)
    return event


def _record_contamination(
    conn: sqlite3.Connection,
    *,
    tip_ref: str,
    source_ref: str | None = None,
    target_ref: str | None = None,
    risk_code: str,
    details: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO contamination_events (
          id, tip_ref, source_ref, target_ref, risk_code, details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            state.next_id(conn, "contam"),
            tip_ref,
            source_ref,
            target_ref,
            risk_code,
            state.dumps_json(details or {}),
            state.next_timestamp(conn),
        ),
    )


def _record_action(
    conn: sqlite3.Connection,
    action: str,
    *,
    source_ref: str | None = None,
    target_ref: str | None = None,
    volume_ul: float | None = None,
    tip_ref: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO liquid_actions (
          id, action, source_ref, target_ref, volume_ul, tip_ref, created_at, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            state.next_id(conn, "action"),
            action,
            source_ref,
            target_ref,
            volume_ul,
            tip_ref,
            state.next_timestamp(conn),
            state.dumps_json(payload or {}),
        ),
    )
