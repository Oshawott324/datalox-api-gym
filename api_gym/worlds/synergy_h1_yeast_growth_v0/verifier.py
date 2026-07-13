"""Composable state/event verifier for the Synergy H1 growth contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .state import CONTRACT_NAME, RUN_METADATA_NAME, connect, loads_json, resolve_state_db_path


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    scenario: str
    checks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "scenario": self.scenario, "checks": self.checks}


Predicate = Callable[[Any, dict[str, Any]], tuple[bool, str]]


def _check(name: str, predicate: Predicate, conn: Any, contract: dict[str, Any]) -> dict[str, Any]:
    ok, detail = predicate(conn, contract)
    return {"name": name, "ok": ok, "detail": detail}


PREDICATES: tuple[tuple[str, Predicate], ...] = (
    ("plate_configuration", lambda conn, c: _plate_configuration(conn, c)),
    ("temperature_stabilized_before_series", lambda conn, c: _temperature_before_series(conn, c)),
    ("continuous_orbital_shaking", lambda conn, c: _continuous_shaking(conn, c)),
    ("correct_wavelength", lambda conn, c: _correct_wavelength(conn, c)),
    ("required_replicates_present", lambda conn, c: _required_replicates(conn, c)),
    ("measurement_cadence_complete", lambda conn, c: _cadence_complete(conn, c)),
    ("kinetic_duration_complete", lambda conn, c: _duration_complete(conn, c)),
    ("decision_supported_by_complete_series", lambda conn, c: _decision_supported(conn, c)),
)


def verify_run(run_dir: Path) -> VerificationResult:
    run_dir = run_dir.resolve()
    metadata_path = run_dir / RUN_METADATA_NAME
    contract_path = run_dir / CONTRACT_NAME
    if not metadata_path.exists() or not contract_path.exists():
        missing = RUN_METADATA_NAME if not metadata_path.exists() else CONTRACT_NAME
        return VerificationResult(False, "unknown", [{"name": "world_files_exist", "ok": False, "detail": f"Missing {missing}."}])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    with connect(resolve_state_db_path(run_dir)) as conn:
        checks = [_check(name, predicate, conn, contract) for name, predicate in PREDICATES]
    return VerificationResult(all(item["ok"] for item in checks), str(metadata["scenario"]), checks)


def _measurements(conn: Any) -> list[Any]:
    return list(conn.execute("SELECT * FROM measurements ORDER BY time_s, measurement_id"))


def _plate_configuration(conn: Any, contract: dict[str, Any]) -> tuple[bool, str]:
    plate = conn.execute("SELECT * FROM plate WHERE plate_id = ?", (contract["plate_id"],)).fetchone()
    if plate is None:
        return False, "Expected plate is missing."
    ok = (
        int(plate["version"]) == int(contract["plate_version"])
        and bool(plate["sealed"]) is bool(contract["sealed"])
        and float(plate["volume_ul"]) == float(contract["volume_ul"])
        and loads_json(plate["replicate_wells_json"]) == contract["replicate_wells"]
    )
    return ok, "Plate identity, version, seal, volume, and replicate set match the contract."


def _temperature_before_series(conn: Any, contract: dict[str, Any]) -> tuple[bool, str]:
    first = conn.execute("SELECT time_s, temperature_c FROM measurements ORDER BY time_s LIMIT 1").fetchone()
    if first is None:
        return False, "No kinetic measurement exists."
    target = float(contract["temperature_c"])
    tolerance = float(contract["temperature_tolerance_c"])
    observed = conn.execute(
        """
        SELECT payload_json FROM events
        WHERE event_type = 'reader.temperature_observed' AND time_s <= ?
        ORDER BY time_s DESC, seq DESC LIMIT 1
        """,
        (float(first["time_s"]),),
    ).fetchone()
    observed_c = loads_json(observed[0])["temperature_c"] if observed is not None else None
    ok = (
        observed_c is not None
        and abs(float(observed_c) - target) <= tolerance
        and abs(float(first["temperature_c"]) - target) <= tolerance
    )
    return ok, f"Temperature was observed at {observed_c!r} C before the first read; target is {target} C."


def _continuous_shaking(conn: Any, contract: dict[str, Any]) -> tuple[bool, str]:
    rows = _measurements(conn)
    if not rows:
        return False, "No kinetic measurement exists."
    start = conn.execute(
        "SELECT time_s, payload_json FROM events WHERE event_type = 'reader.shaking_started' ORDER BY time_s, seq LIMIT 1"
    ).fetchone()
    if start is None:
        return False, "Shaking was never started."
    payload = loads_json(start["payload_json"])
    stop_count = conn.execute(
        """
        SELECT COUNT(*) FROM events WHERE event_type = 'reader.shaking_stopped'
          AND time_s >= ? AND time_s <= ?
        """,
        (float(rows[0]["time_s"]), float(rows[-1]["time_s"])),
    ).fetchone()[0]
    ok = (
        float(start["time_s"]) <= float(rows[0]["time_s"])
        and payload.get("shake_type") == contract["shake_type"]
        and int(payload.get("frequency_setting", -1)) == int(contract["frequency_setting"])
        and stop_count == 0
        and all(bool(row["shaking"]) for row in rows)
    )
    return ok, f"Required shaking mode spans the series; stop events during series: {stop_count}."


def _correct_wavelength(conn: Any, contract: dict[str, Any]) -> tuple[bool, str]:
    count, wrong = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN wavelength_nm != ? THEN 1 ELSE 0 END) FROM measurements",
        (int(contract["wavelength_nm"]),),
    ).fetchone()
    wrong = int(wrong or 0)
    return int(count) > 0 and wrong == 0, f"Measurements: {count}; wrong-wavelength measurements: {wrong}."


def _required_replicates(conn: Any, contract: dict[str, Any]) -> tuple[bool, str]:
    required = set(contract["replicate_wells"])
    rows = conn.execute("SELECT wells_json FROM measurements").fetchall()
    missing_rows = sum(set(loads_json(row[0])) != required for row in rows)
    return bool(rows) and missing_rows == 0, f"Measurements missing the exact replicate set: {missing_rows}."


def _cadence_complete(conn: Any, contract: dict[str, Any]) -> tuple[bool, str]:
    times = [float(row[0]) for row in conn.execute("SELECT time_s FROM measurements ORDER BY time_s, measurement_id")]
    expected_count = int(contract["measurement_count"])
    period = float(contract["cadence_s"])
    tolerance = float(contract["cadence_tolerance_s"])
    bad_intervals = sum(abs((b - a) - period) > tolerance for a, b in zip(times, times[1:]))
    ok = len(times) == expected_count and bad_intervals == 0
    return ok, f"Measurements: {len(times)}/{expected_count}; cadence violations: {bad_intervals}."


def _duration_complete(conn: Any, contract: dict[str, Any]) -> tuple[bool, str]:
    row = conn.execute("SELECT MIN(time_s), MAX(time_s), COUNT(*) FROM measurements").fetchone()
    span = 0.0 if not row[2] else float(row[1]) - float(row[0])
    required = float(contract["duration_s"])
    return span >= required, f"Observed span: {span} s; required: {required} s."


def _decision_supported(conn: Any, contract: dict[str, Any]) -> tuple[bool, str]:
    submission = conn.execute("SELECT * FROM submissions ORDER BY id DESC LIMIT 1").fetchone()
    final = conn.execute("SELECT measurement_id, time_s FROM measurements ORDER BY time_s DESC, measurement_id DESC LIMIT 1").fetchone()
    if submission is None or final is None:
        return False, "A submission and final measurement are required."
    prerequisite_names = {
        "temperature_stabilized_before_series": _temperature_before_series,
        "continuous_orbital_shaking": _continuous_shaking,
        "correct_wavelength": _correct_wavelength,
        "required_replicates_present": _required_replicates,
        "measurement_cadence_complete": _cadence_complete,
        "kinetic_duration_complete": _duration_complete,
    }
    prerequisites_ok = all(predicate(conn, contract)[0] for predicate in prerequisite_names.values())
    ok = (
        submission["decision"] == "accept"
        and submission["evidence_measurement_id"] == final["measurement_id"]
        and float(submission["time_s"]) >= float(final["time_s"])
        and prerequisites_ok
    )
    return ok, "Accept must cite the final measurement of a complete, contract-conforming series."
