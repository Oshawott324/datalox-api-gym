"""Hidden verifier for the LabLongRun-Wet Phase 1 prototype."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from greenfield_lablongrun.core.schemas import VerifierResult, check, read_json, write_json
from greenfield_lablongrun.worlds.lablongrun_wet_v0 import state


def verify_run(run_dir: Path, *, write_outputs: bool = True) -> VerifierResult:
    run_dir = run_dir.resolve()
    run = read_json(run_dir / "run.json")
    expectations = read_json(run_dir / "hidden" / "verifier_expectations.json")
    traces = _read_jsonl(run_dir / "tool_calls.jsonl")
    checks = []

    with state.connect(run_dir / state.STATE_DB_NAME) as conn:
        checks.extend(_check_dry_run(conn))
        checks.extend(_check_required_artifacts(traces, expectations))
        checks.extend(_check_final_volumes(conn, expectations))
        checks.extend(_check_readout(conn, expectations))
        checks.extend(_check_submission(conn, expectations))
        checks.extend(_check_contamination(conn, expectations))
        checks.extend(_check_fresh_readout(conn, expectations))
        checks.extend(_check_required_wait(conn, expectations))
        checks.extend(_check_partial_dispense(conn, expectations))
        checks.extend(_check_ordering(conn))

    result = VerifierResult(
        schema_version="greenfield_lablongrun.verifier_result.v0",
        world=run["world"],
        scenario=run["scenario"],
        ok=all(item.ok for item in checks),
        checks=checks,
    )
    if write_outputs:
        write_json(run_dir / "verifier_result.json", result.to_dict())
        write_json(run_dir / "run_export.json", _build_run_export(run_dir, result))
    return result


def _check_dry_run(conn) -> list:
    dry_run = bool(state.get_metadata(conn, "dry_run", False))
    return [
        check(
            "dry_run_boundary",
            dry_run,
            "live_boundary",
            "Run remained inside dry-run state; no live hardware/provider path exists.",
        )
    ]


def _check_required_artifacts(traces: list[dict[str, Any]], expectations: dict[str, Any]) -> list:
    read_artifacts = {
        record.get("result", {}).get("data", {}).get("artifact_name")
        for record in traces
        if record.get("tool_name") == "get_protocol_artifact" and record.get("ok")
    }
    checks = []
    for artifact_name in expectations["required_artifacts_read"]:
        checks.append(
            check(
                f"artifact_read:{artifact_name}",
                artifact_name in read_artifacts,
                "provenance",
                f"Agent inspected required visible artifact {artifact_name}.",
                {"artifact_name": artifact_name},
            )
        )
    return checks


def _check_final_volumes(conn, expectations: dict[str, Any]) -> list:
    checks = []
    for well_ref, expected_volume in expectations["expected_final_volumes_ul"].items():
        labware_id, well_id = state.parse_well_ref(well_ref)
        row = conn.execute(
            "SELECT volume_ul FROM wells WHERE labware_id = ? AND well_id = ?",
            (labware_id, well_id),
        ).fetchone()
        actual = None if row is None else round(float(row["volume_ul"]), 6)
        ok = actual is not None and abs(actual - float(expected_volume)) <= 0.0001
        checks.append(
            check(
                f"final_volume:{well_ref}",
                ok,
                "terminal_state",
                f"{well_ref} final volume matched expectation.",
                {"expected_volume_ul": expected_volume, "actual_volume_ul": actual},
            )
        )
    negative = conn.execute("SELECT labware_id, well_id, volume_ul FROM wells WHERE volume_ul < -0.000001").fetchall()
    checks.append(
        check(
            "no_negative_well_volumes",
            not negative,
            "resource",
            "No well volume went negative.",
            {"negative_wells": [dict(row) for row in negative]},
        )
    )
    return checks


def _check_readout(conn, expectations: dict[str, Any]) -> list:
    target_plate, target_well = state.parse_well_ref(expectations["target_well_ref"])
    readout = conn.execute(
        """
        SELECT * FROM od_readouts
        WHERE plate_id = ? AND well_id = ? AND wavelength_nm = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (target_plate, target_well, expectations["evidence_wavelength_nm"]),
    ).fetchone()
    if readout is None:
        return [
            check(
                "readout_exists",
                False,
                "terminal_state",
                "Expected OD600 readout was produced for the target well.",
            )
        ]
    band = expectations["corrected_od600_band"]
    corrected = float(readout["corrected_od600"])
    return [
        check(
            "readout_exists",
            True,
            "terminal_state",
            "Expected OD600 readout was produced for the target well.",
            {"readout_id": readout["id"]},
        ),
        check(
            "corrected_od600_in_band",
            float(band["min"]) <= corrected <= float(band["max"]),
            "terminal_state",
            "Corrected OD600 is inside the expected acceptance band.",
            {"corrected_od600": corrected, "band": band, "readout_id": readout["id"]},
        ),
    ]


def _check_submission(conn, expectations: dict[str, Any]) -> list:
    submission = conn.execute("SELECT * FROM qc_submissions ORDER BY created_at DESC LIMIT 1").fetchone()
    if submission is None:
        return [
            check(
                "submission_exists",
                False,
                "terminal_state",
                "Expected a final protocol decision submission.",
            )
        ]
    readout = conn.execute("SELECT * FROM od_readouts WHERE id = ?", (submission["evidence_readout_id"],)).fetchone()
    return [
        check(
            "submission_exists",
            True,
            "terminal_state",
            "Final protocol decision submission exists.",
            {"submission_id": submission["id"]},
        ),
        check(
            "decision_matches_expected",
            submission["decision"] == expectations["expected_decision"],
            "terminal_state",
            "Final protocol decision matched expectation.",
            {"expected": expectations["expected_decision"], "actual": submission["decision"]},
        ),
        check(
            "submission_target_matches",
            submission["target_well_ref"] == expectations["target_well_ref"],
            "terminal_state",
            "Final protocol decision targeted the expected well.",
            {"expected": expectations["target_well_ref"], "actual": submission["target_well_ref"]},
        ),
        check(
            "submission_cites_run_readout",
            readout is not None,
            "provenance",
            "Final protocol decision cited a readout produced in this run.",
            {"evidence_readout_id": submission["evidence_readout_id"]},
        ),
    ]


def _check_ordering(conn) -> list:
    submission = conn.execute("SELECT * FROM qc_submissions ORDER BY created_at DESC LIMIT 1").fetchone()
    if submission is None:
        return []
    readout = conn.execute("SELECT * FROM od_readouts WHERE id = ?", (submission["evidence_readout_id"],)).fetchone()
    if readout is None:
        return []
    return [
        check(
            "decision_after_readout",
            readout["created_at"] < submission["created_at"],
            "temporal",
            "Protocol decision was submitted after the cited readout was created.",
            {"readout_created_at": readout["created_at"], "submission_created_at": submission["created_at"]},
        )
    ]


def _check_contamination(conn, expectations: dict[str, Any]) -> list:
    if not expectations.get("forbid_contamination_events"):
        return []
    rows = conn.execute(
        "SELECT tip_ref, source_ref, target_ref, risk_code, details_json FROM contamination_events ORDER BY created_at"
    ).fetchall()
    return [
        check(
            "no_contamination_events",
            not rows,
            "provenance",
            "No contamination-risk event was recorded for protected reagent/sample contact.",
            {"events": [dict(row) for row in rows]},
        )
    ]


def _check_fresh_readout(conn, expectations: dict[str, Any]) -> list:
    if not expectations.get("require_fresh_readout"):
        return []
    submission = conn.execute("SELECT * FROM qc_submissions ORDER BY created_at DESC LIMIT 1").fetchone()
    if submission is None:
        return []
    readout = conn.execute("SELECT * FROM od_readouts WHERE id = ?", (submission["evidence_readout_id"],)).fetchone()
    first_action = conn.execute("SELECT created_at FROM liquid_actions ORDER BY created_at LIMIT 1").fetchone()
    ok = readout is not None and first_action is not None and readout["created_at"] > first_action["created_at"]
    return [
        check(
            "submission_cites_fresh_readout",
            ok,
            "provenance",
            "Final protocol decision cited a readout produced after this run began liquid handling.",
            {
                "evidence_readout_id": submission["evidence_readout_id"],
                "readout_created_at": None if readout is None else readout["created_at"],
                "first_action_created_at": None if first_action is None else first_action["created_at"],
            },
        )
    ]


def _check_required_wait(conn, expectations: dict[str, Any]) -> list:
    required = expectations.get("required_wait_seconds")
    if required is None:
        return []
    waited = conn.execute("SELECT COALESCE(SUM(seconds), 0) AS seconds FROM delays").fetchone()
    waited_seconds = 0.0 if waited is None else float(waited["seconds"])
    return [
        check(
            "required_wait_satisfied",
            waited_seconds >= float(required),
            "temporal",
            "Run waited long enough for the scheduled dry-run instrument-ready gate.",
            {"required_wait_seconds": float(required), "actual_wait_seconds": waited_seconds},
        )
    ]


def _check_partial_dispense(conn, expectations: dict[str, Any]) -> list:
    if not expectations.get("require_partial_dispense_recovery"):
        return []
    event = state.get_metadata(conn, "partial_dispense_once")
    pipette = conn.execute("SELECT held_volume_ul FROM pipette_state WHERE id = ?", ("p300_single",)).fetchone()
    applied = isinstance(event, dict) and bool(event.get("applied"))
    empty = pipette is not None and abs(float(pipette["held_volume_ul"])) <= 0.0001
    return [
        check(
            "partial_dispense_fault_observed",
            applied,
            "fault_recovery",
            "The scheduled partial-dispense fault was exercised.",
            {"partial_dispense": event},
        ),
        check(
            "partial_dispense_recovered",
            applied and empty,
            "fault_recovery",
            "Run recovered from partial dispense and left no held liquid in the pipette.",
            {
                "partial_dispense": event,
                "held_volume_ul": None if pipette is None else float(pipette["held_volume_ul"]),
            },
        ),
    ]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _build_run_export(run_dir: Path, result: VerifierResult) -> dict[str, Any]:
    run = read_json(run_dir / "run.json")
    return {
        "schema_version": "greenfield_lablongrun.run_export.v0",
        "world_ref": {"world": result.world, "scenario": result.scenario},
        "task_ref": {"task": "task.json", "agent_task": "agent_task.json"},
        "run_ref": {"run_dir": str(run_dir), "label": run["label"]},
        "trace_ref": {"tool_calls": "tool_calls.jsonl", "state_diffs": "state_diffs.jsonl"},
        "verifier_result": result.to_dict(),
        "artifact_refs": {
            "source_refs": "source_refs_snapshot.json",
            "visible_artifacts": "visible_artifacts/",
            "hidden_expectations": "hidden/verifier_expectations.json",
        },
    }
