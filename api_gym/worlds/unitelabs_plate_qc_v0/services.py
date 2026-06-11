"""Dry-run lab service operations for unitelabs_plate_qc_v0."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_gym.worlds.unitelabs_plate_qc_v0.state import (
    connect,
    dumps_json,
    insert_audit,
    insert_event,
    loads_json,
)

AGENT_ACTOR = "agent@unitelabs.example"
VALID_DECISIONS = {"continue", "hold"}


def get_deck_state(db_path: Path) -> dict[str, Any]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM deck WHERE id = ?", ("deck_1",)).fetchone()
        if row is None:
            return _error("deck_not_found", "Dry-run deck state does not exist.", {})
        return _ok(
            {
                "id": row["id"],
                "mode": row["mode"],
                "dry_run": bool(row["dry_run"]),
                "loaded_labware": loads_json(row["loaded_labware_json"]) or [],
                "metadata": loads_json(row["metadata_json"]) or {},
            }
        )


def get_labware_state(db_path: Path, labware_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        labware = conn.execute("SELECT * FROM labware WHERE id = ?", (labware_id,)).fetchone()
        if labware is None:
            return _error("labware_not_found", "Labware id is not loaded on this dry-run deck.", {"labware_id": labware_id})
        wells = {
            row["well_id"]: {
                "volume_ul": _clean_number(row["volume_ul"]),
                "metadata": loads_json(row["metadata_json"]) or {},
            }
            for row in conn.execute(
                "SELECT * FROM wells WHERE labware_id = ? ORDER BY well_id",
                (labware_id,),
            )
        }
        tips = {
            row["well_id"]: {"status": row["status"]}
            for row in conn.execute(
                "SELECT * FROM tips WHERE rack_id = ? ORDER BY well_id",
                (labware_id,),
            )
        }
        data: dict[str, Any] = {
            "id": labware["id"],
            "kind": labware["kind"],
            "display_name": labware["display_name"],
            "metadata": loads_json(labware["metadata_json"]) or {},
        }
        if wells:
            data["wells"] = wells
        if tips:
            data["tips"] = tips
        return _ok(data)


def aspirate(db_path: Path, source: str, volume_ul: float, tip: str) -> dict[str, Any]:
    request = {"source": source, "volume_ul": volume_ul, "tip": tip}
    now = _now()
    with connect(db_path) as conn:
        source_ref = _parse_well_ref(source, field="source")
        if source_ref is None:
            return _audited_error(conn, "lab.aspirate", "well", source, request, "invalid_source_ref", "Source must be labware_id:well_id.", now)
        tip_ref = _parse_well_ref(tip, field="tip")
        if tip_ref is None:
            return _audited_error(conn, "lab.aspirate", "tip", tip, request, "invalid_tip_ref", "Tip must be rack_id:well_id.", now)
        if volume_ul <= 0:
            return _audited_error(conn, "lab.aspirate", "well", source, request, "invalid_volume", "Volume must be positive.", now)

        source_well = _get_well(conn, *source_ref)
        if source_well is None:
            return _audited_error(conn, "lab.aspirate", "well", source, request, "well_not_found", "Source well does not exist.", now)
        tip_row = conn.execute("SELECT * FROM tips WHERE rack_id = ? AND well_id = ?", tip_ref).fetchone()
        if tip_row is None:
            return _audited_error(conn, "lab.aspirate", "tip", tip, request, "tip_not_found", "Tip location does not exist.", now)
        if tip_row["status"] != "available":
            return _audited_error(conn, "lab.aspirate", "tip", tip, request, "tip_not_available", "Tip is not available.", now)
        pipette = _pipette(conn)
        if pipette["aspirated_volume_ul"] > 0:
            return _audited_error(conn, "lab.aspirate", "pipette", "p300_single", request, "pipette_not_empty", "Dispense pending aspirated volume before aspirating again.", now)
        if source_well["volume_ul"] < volume_ul:
            return _audited_error(
                conn,
                "lab.aspirate",
                "well",
                source,
                request,
                "insufficient_well_volume",
                "Source well does not contain enough volume for this aspirate.",
                now,
                {"available_ul": _clean_number(source_well["volume_ul"]), "requested_ul": volume_ul},
            )

        remaining = source_well["volume_ul"] - volume_ul
        conn.execute(
            "UPDATE wells SET volume_ul = ? WHERE labware_id = ? AND well_id = ?",
            (remaining, source_ref[0], source_ref[1]),
        )
        conn.execute("UPDATE tips SET status = ? WHERE rack_id = ? AND well_id = ?", ("in_use", tip_ref[0], tip_ref[1]))
        conn.execute(
            """
            UPDATE pipette_state
            SET tip = ?, aspirated_volume_ul = ?, source_labware_id = ?, source_well_id = ?
            WHERE id = ?
            """,
            (tip, volume_ul, source_ref[0], source_ref[1], "p300_single"),
        )
        response = {"source": source, "volume_ul": _clean_number(volume_ul), "tip": tip, "source_remaining_ul": _clean_number(remaining)}
        _record_success(conn, "lab.aspirate", "well", source, request, response, now, "transfer.aspirated")
        return _ok(response)


def dispense(db_path: Path, target: str, volume_ul: float, mix_after: bool) -> dict[str, Any]:
    request = {"target": target, "volume_ul": volume_ul, "mix_after": mix_after}
    now = _now()
    with connect(db_path) as conn:
        target_ref = _parse_well_ref(target, field="target")
        if target_ref is None:
            return _audited_error(conn, "lab.dispense", "well", target, request, "invalid_target_ref", "Target must be labware_id:well_id.", now)
        if volume_ul <= 0:
            return _audited_error(conn, "lab.dispense", "well", target, request, "invalid_volume", "Volume must be positive.", now)
        target_well = _get_well(conn, *target_ref)
        if target_well is None:
            return _audited_error(conn, "lab.dispense", "well", target, request, "well_not_found", "Target well does not exist.", now)
        pipette = _pipette(conn)
        pending = float(pipette["aspirated_volume_ul"])
        if pending <= 0:
            return _audited_error(conn, "lab.dispense", "pipette", "p300_single", request, "no_aspirated_volume", "No aspirated volume is pending.", now)
        if volume_ul > pending:
            return _audited_error(
                conn,
                "lab.dispense",
                "pipette",
                "p300_single",
                request,
                "dispense_exceeds_aspirated_volume",
                "Dispense volume exceeds pending aspirated volume.",
                now,
                {"available_ul": _clean_number(pending), "requested_ul": volume_ul},
            )

        target_volume = float(target_well["volume_ul"]) + volume_ul
        remaining = pending - volume_ul
        conn.execute(
            "UPDATE wells SET volume_ul = ? WHERE labware_id = ? AND well_id = ?",
            (target_volume, target_ref[0], target_ref[1]),
        )
        if remaining == 0:
            conn.execute(
                """
                UPDATE pipette_state
                SET aspirated_volume_ul = 0, source_labware_id = NULL, source_well_id = NULL
                WHERE id = ?
                """,
                ("p300_single",),
            )
        else:
            conn.execute("UPDATE pipette_state SET aspirated_volume_ul = ? WHERE id = ?", (remaining, "p300_single"))

        conn.execute(
            """
            INSERT INTO transfers (
              source_labware_id, source_well_id, target_labware_id, target_well_id,
              volume_ul, tip, mix_after, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pipette["source_labware_id"],
                pipette["source_well_id"],
                target_ref[0],
                target_ref[1],
                volume_ul,
                pipette["tip"],
                int(mix_after),
                now,
            ),
        )
        response = {
            "target": target,
            "volume_ul": _clean_number(volume_ul),
            "target_volume_ul": _clean_number(target_volume),
            "remaining_aspirated_volume_ul": _clean_number(remaining),
            "mix_after": bool(mix_after),
        }
        _record_success(conn, "lab.dispense", "well", target, request, response, now, "transfer.dispensed")
        return _ok(response)


def read_absorbance(db_path: Path, plate: str, wavelength_nm: int, wells: list[str]) -> dict[str, Any]:
    request = {"plate": plate, "wavelength_nm": wavelength_nm, "wells": wells}
    now = _now()
    with connect(db_path) as conn:
        labware = conn.execute("SELECT * FROM labware WHERE id = ? AND kind = ?", (plate, "plate")).fetchone()
        if labware is None:
            return _audited_error(conn, "lab.read_absorbance", "plate", plate, request, "plate_not_found", "Plate id is not loaded.", now)
        if not wells:
            return _audited_error(conn, "lab.read_absorbance", "plate", plate, request, "empty_well_list", "At least one well is required.", now)
        values: dict[str, float] = {}
        for well_id in wells:
            if _get_well(conn, plate, well_id) is None:
                return _audited_error(conn, "lab.read_absorbance", "well", f"{plate}:{well_id}", request, "well_not_found", "Requested well does not exist.", now)
            values[well_id] = _read_value(conn, plate, well_id, int(wavelength_nm))

        readout_id = f"ro_{plate}_{int(wavelength_nm)}_{_readout_count(conn) + 1}"
        conn.execute(
            """
            INSERT INTO readouts (id, plate_id, wavelength_nm, wells_json, values_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (readout_id, plate, int(wavelength_nm), dumps_json(wells), dumps_json(values), now),
        )
        response = {"readout_id": readout_id, "plate": plate, "wavelength_nm": int(wavelength_nm), "wells": wells, "values": values}
        _record_success(conn, "lab.read_absorbance", "plate", plate, request, response, now, "readout.created")
        return _ok(response)


def add_workflow_note(db_path: Path, note: str) -> dict[str, Any]:
    note = note.strip()
    request = {"note": note}
    now = _now()
    with connect(db_path) as conn:
        if not note:
            return _audited_error(conn, "lab.add_workflow_note", "workflow_note", "new", request, "empty_note", "Workflow note must be non-empty.", now)
        conn.execute("INSERT INTO workflow_notes (note, created_at) VALUES (?, ?)", (note, now))
        note_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        response = {"note_id": note_id, "note": note}
        _record_success(conn, "lab.add_workflow_note", "workflow_note", str(note_id), request, response, now, "workflow_note.created")
        return _ok(response)


def submit_protocol(
    db_path: Path,
    decision: str,
    evidence_readout_id: str,
    target_well: str,
    rationale: str,
) -> dict[str, Any]:
    decision = decision.strip().lower()
    rationale = rationale.strip()
    request = {
        "decision": decision,
        "evidence_readout_id": evidence_readout_id,
        "target_well": target_well,
        "rationale": rationale,
    }
    now = _now()
    with connect(db_path) as conn:
        target_ref = _parse_well_ref(target_well, field="target_well")
        if target_ref is None:
            return _audited_error(conn, "lab.submit_protocol", "submission", "new", request, "invalid_target_well", "Target well must be labware_id:well_id.", now)
        if decision not in VALID_DECISIONS:
            return _audited_error(
                conn,
                "lab.submit_protocol",
                "submission",
                "new",
                request,
                "invalid_decision",
                "Decision must be continue or hold.",
                now,
                {"allowed_decisions": sorted(VALID_DECISIONS)},
            )
        if not rationale:
            return _audited_error(conn, "lab.submit_protocol", "submission", "new", request, "empty_rationale", "Submission rationale must be non-empty.", now)
        if _get_well(conn, *target_ref) is None:
            return _audited_error(conn, "lab.submit_protocol", "well", target_well, request, "well_not_found", "Target well does not exist.", now)
        readout = conn.execute("SELECT * FROM readouts WHERE id = ?", (evidence_readout_id,)).fetchone()
        if readout is None:
            return _audited_error(conn, "lab.submit_protocol", "readout", evidence_readout_id, request, "readout_not_found", "Evidence readout does not exist.", now)

        conn.execute(
            """
            INSERT INTO submissions (
              decision, evidence_readout_id, target_labware_id, target_well_id, rationale, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (decision, evidence_readout_id, target_ref[0], target_ref[1], rationale, now),
        )
        submission_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        response = {
            "submission_id": submission_id,
            "decision": decision,
            "evidence_readout_id": evidence_readout_id,
            "target_well": target_well,
            "rationale": rationale,
        }
        _record_success(conn, "lab.submit_protocol", "submission", str(submission_id), request, response, now, "protocol.submitted")
        return _ok(response)


def _parse_well_ref(value: str, *, field: str) -> tuple[str, str] | None:
    if not isinstance(value, str) or ":" not in value:
        return None
    labware_id, well_id = value.split(":", 1)
    if not labware_id or not well_id or ":" in well_id:
        return None
    return labware_id, well_id


def _get_well(conn, labware_id: str, well_id: str):
    return conn.execute("SELECT * FROM wells WHERE labware_id = ? AND well_id = ?", (labware_id, well_id)).fetchone()


def _pipette(conn):
    row = conn.execute("SELECT * FROM pipette_state WHERE id = ?", ("p300_single",)).fetchone()
    if row is None:
        raise RuntimeError("Missing p300_single pipette state.")
    return row


def _read_value(conn, plate: str, well_id: str, wavelength_nm: int) -> float:
    band = conn.execute(
        """
        SELECT * FROM control_bands
        WHERE plate_id = ? AND well_id = ? AND wavelength_nm = ?
        """,
        (plate, well_id, wavelength_nm),
    ).fetchone()
    if band is None:
        return 0.0
    transfer = conn.execute(
        """
        SELECT * FROM transfers
        WHERE target_labware_id = ? AND target_well_id = ? AND volume_ul = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (plate, well_id, band["required_dispense_ul"]),
    ).fetchone()
    if transfer is None:
        return 0.0
    return float(band["expected_value"])


def _readout_count(conn) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM readouts").fetchone()
    return int(row["count"])


def _record_success(
    conn,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    response: dict[str, Any],
    created_at: str,
    event_type: str,
) -> None:
    insert_event(conn, event_type=event_type, object_type=object_type, object_id=object_id, payload=response, created_at=created_at)
    insert_audit(
        conn,
        actor=AGENT_ACTOR,
        action=action,
        object_type=object_type,
        object_id=object_id,
        request=request,
        response={"ok": True, "data": response},
        created_at=created_at,
    )


def _audited_error(
    conn,
    action: str,
    object_type: str,
    object_id: str,
    request: dict[str, Any],
    code: str,
    message: str,
    created_at: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = _error(code, message, details or {})
    insert_audit(
        conn,
        actor=AGENT_ACTOR,
        action=action,
        object_type=object_type,
        object_id=object_id,
        request=request,
        response=response,
        created_at=created_at,
    )
    return response


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_number(value: float) -> int | float:
    number = float(value)
    if number.is_integer():
        return int(number)
    return number
