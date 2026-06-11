"""State verifiers for unitelabs_plate_qc_v0 episodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api_gym.worlds.unitelabs_plate_qc_v0.state import RUN_METADATA_NAME, STATE_DB_NAME, connect, loads_json


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    scenario: str
    checks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "scenario": self.scenario, "checks": self.checks}


def verify_run(run_dir: Path) -> VerificationResult:
    run_dir = run_dir.resolve()
    metadata_path = run_dir / RUN_METADATA_NAME
    if not metadata_path.exists():
        return VerificationResult(ok=False, scenario="unknown", checks=[_fail("run_metadata_exists", f"Missing {RUN_METADATA_NAME}.")])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    db_path = run_dir / metadata.get("state_db", STATE_DB_NAME)
    if not db_path.exists():
        return VerificationResult(
            ok=False,
            scenario=metadata.get("scenario", "unknown"),
            checks=[_fail("state_db_exists", f"Missing state database at {db_path}.")],
        )

    with connect(db_path) as conn:
        expected = _expected_resolution(conn)
        if expected is None:
            return VerificationResult(
                ok=False,
                scenario=metadata.get("scenario", "unknown"),
                checks=[_fail("expected_resolution_exists", "Missing hidden expected resolution event.")],
            )
        scenario = expected["scenario"]
        if scenario != "plate_transfer_qc":
            checks = [_fail("scenario_supported", f"Unsupported verifier scenario '{scenario}'.")]
        else:
            checks = _verify_plate_transfer_qc(conn, expected)
        return VerificationResult(ok=all(check["ok"] for check in checks), scenario=scenario, checks=checks)


def _verify_plate_transfer_qc(conn, expected: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    source_labware, source_well = expected["source"].split(":", 1)
    target_labware, target_well = expected["target"].split(":", 1)
    tip_rack, tip_well = expected["tip"].split(":", 1)
    volume_ul = float(expected["transfer_volume_ul"])
    wavelength_nm = int(expected["wavelength_nm"])

    deck = conn.execute("SELECT * FROM deck WHERE id = ?", ("deck_1",)).fetchone()
    live_actions = conn.execute(
        """
        SELECT COUNT(*) AS count FROM audit_log
        WHERE action LIKE ? OR object_type = ?
        """,
        ("live.%", "hardware"),
    ).fetchone()
    checks.append(
        _check(
            deck is not None
            and bool(deck["dry_run"])
            and deck["mode"] == "dry_run"
            and int(live_actions["count"]) == 0,
            "dry_run_no_live_action",
            "Deck remains in dry-run mode with no live hardware/API action evidence.",
        )
    )

    overdrawn = conn.execute("SELECT COUNT(*) AS count FROM wells WHERE volume_ul < 0").fetchone()
    source_exists = _well_exists(conn, source_labware, source_well)
    target_exists = _well_exists(conn, target_labware, target_well)
    tip_exists = (
        conn.execute("SELECT 1 FROM tips WHERE rack_id = ? AND well_id = ?", (tip_rack, tip_well)).fetchone()
        is not None
    )
    checks.append(
        _check(
            source_exists and target_exists and tip_exists,
            "expected_labware_and_wells_exist",
            "Expected source well, target well, and tip location exist in final dry-run state.",
        )
    )
    checks.append(_check(int(overdrawn["count"]) == 0, "no_overdrawn_well", "No well has negative volume."))

    transfer = conn.execute(
        """
        SELECT * FROM transfers
        WHERE source_labware_id = ? AND source_well_id = ?
          AND target_labware_id = ? AND target_well_id = ? AND volume_ul = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (source_labware, source_well, target_labware, target_well, volume_ul),
    ).fetchone()
    checks.append(
        _check(
            transfer is not None,
            "valid_transfer_completed",
            "A 50 uL dry-run transfer from source_plate:A1 to assay_plate:B1 was completed.",
        )
    )

    readout = _latest_readout_for(conn, target_labware, target_well, wavelength_nm)
    expected_value = float(expected["expected_readout_value"])
    checks.append(
        _check(
            readout is not None
            and readout["values"].get(target_well) == expected_value
            and transfer is not None
            and transfer["created_at"] <= readout["created_at"],
            "readout_after_dispense",
            "A matching OD600 readout was recorded after the target dispense.",
        )
    )

    submission = conn.execute("SELECT * FROM submissions ORDER BY id DESC LIMIT 1").fetchone()
    checks.append(_check(submission is not None, "protocol_submitted", "A final protocol decision was submitted."))
    submitted_target_ok = (
        submission is not None
        and submission["target_labware_id"] == target_labware
        and submission["target_well_id"] == target_well
    )
    checks.append(
        _check(
            submitted_target_ok,
            "submitted_target_matches_expected",
            "Submitted protocol target matches the expected QC well.",
        )
    )

    decision_ok = False
    if submission is not None and readout is not None and submitted_target_ok:
        band = expected["control_band"]
        observed = float(readout["values"].get(target_well, -1))
        expected_decision = "continue" if float(band["min"]) <= observed <= float(band["max"]) else "hold"
        decision_ok = submission["decision"] == expected_decision and submission["evidence_readout_id"] == readout["id"]
    checks.append(
        _check(
            decision_ok,
            "decision_matches_observed_data",
            "Submitted decision matches the observed OD600 value and cites that readout.",
        )
    )
    return checks


def _latest_readout_for(conn, plate: str, well: str, wavelength_nm: int) -> dict[str, Any] | None:
    rows = conn.execute(
        """
        SELECT * FROM readouts
        WHERE plate_id = ? AND wavelength_nm = ?
        ORDER BY created_at DESC, id DESC
        """,
        (plate, wavelength_nm),
    ).fetchall()
    for row in rows:
        wells = loads_json(row["wells_json"]) or []
        values = loads_json(row["values_json"]) or {}
        if well in wells and well in values:
            return {"id": row["id"], "wells": wells, "values": values, "created_at": row["created_at"]}
    return None


def _well_exists(conn, labware_id: str, well_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM wells WHERE labware_id = ? AND well_id = ?",
        (labware_id, well_id),
    ).fetchone() is not None


def _expected_resolution(conn) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT payload_json FROM events
        WHERE event_type = ? AND visible_to_agent = 0
        ORDER BY id DESC
        LIMIT 1
        """,
        ("expected_resolution.created",),
    ).fetchone()
    return loads_json(row["payload_json"]) if row is not None else None


def _check(condition: bool, name: str, message: str) -> dict[str, Any]:
    return {"ok": bool(condition), "name": name, "message": message}


def _fail(name: str, message: str) -> dict[str, Any]:
    return _check(False, name, message)
