"""State- and artifact-based verification for the science workflow families."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backends import ThermocyclerProgramBackend
from .state import CONTRACT_NAME, RUN_METADATA_NAME, connect, load_state, loads_json, resolve_state_db_path


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
    contract_path = run_dir / CONTRACT_NAME
    if not metadata_path.exists() or not contract_path.exists():
        missing = RUN_METADATA_NAME if not metadata_path.exists() else CONTRACT_NAME
        return VerificationResult(False, "unknown", [_result("world_files_exist", False, f"Missing {missing}.")])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    with connect(resolve_state_db_path(run_dir)) as conn:
        state = load_state(conn)
        if state["family"] == "thermocycler":
            checks = _verify_thermocycler(conn, state, contract)
        elif state["family"] == "incubator_shaker":
            checks = _verify_incubator(conn, state, contract)
        elif state["family"] == "powder_balance":
            checks = _verify_powder(conn, state, contract)
        else:
            checks = [_result("known_family", False, f"Unknown family: {state['family']}")]
    return VerificationResult(all(check["ok"] for check in checks), str(metadata["scenario"]), checks)


def _result(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _verify_thermocycler(conn: Any, state: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    backend = ThermocyclerProgramBackend(state["thermocycler"])
    expected_steps = sum(int(stage["repeats"]) * len(stage["steps"]) for stage in contract["protocol"])
    expected_duration = sum(
        int(stage["repeats"]) * sum(float(step["hold_seconds"]) for step in stage["steps"])
        for stage in contract["protocol"]
    )
    artifact_row = conn.execute(
        "SELECT payload_json FROM artifacts WHERE kind = 'qpcr_amplification' ORDER BY time_s DESC LIMIT 1"
    ).fetchone()
    artifact = loads_json(artifact_row[0]) if artifact_row is not None else None
    decision = conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 1").fetchone()
    heated_lid = abs(float(backend.lid_target_c) - float(contract["lid_temperature_c"])) <= 0.1
    profile_ok = len(backend.timeline) == expected_steps and abs(backend.total_duration_s - expected_duration) <= 0.001
    controls_ok = bool(artifact and artifact.get("controls_valid"))
    decision_ok = bool(
        decision is not None
        and decision["decision"] == "accept"
        and artifact is not None
        and decision["evidence_id"] == artifact["artifact_id"]
        and controls_ok
    )
    return [
        _result("heated_lid_configured", heated_lid, f"Lid target: {backend.lid_target_c} C."),
        _result("declared_profile_loaded", profile_ok, f"Steps: {len(backend.timeline)}/{expected_steps}; duration: {backend.total_duration_s}/{expected_duration} s."),
        _result("thermal_program_completed", backend.completed, f"Elapsed: {backend.elapsed_s}/{backend.total_duration_s} s."),
        _result("amplification_controls_valid", controls_ok, "Positive and no-template controls must have the expected calls."),
        _result("decision_uses_amplification_evidence", decision_ok, "Accept must cite the completed control-valid amplification artifact."),
    ]


def _verify_incubator(conn: Any, state: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    incubator = state["incubator"]
    rows = conn.execute(
        "SELECT artifact_id, time_s, payload_json FROM artifacts WHERE kind = 'od600_measurement' ORDER BY time_s, artifact_id"
    ).fetchall()
    artifacts = [loads_json(row["payload_json"]) for row in rows]
    expected_times = [float(value) for value in contract["measurement_times_s"]]
    observed_times = [float(item["time_s"]) for item in artifacts]
    tolerance = float(contract["cadence_tolerance_s"])
    cadence_ok = len(observed_times) == len(expected_times) and all(
        abs(observed - expected) <= tolerance for observed, expected in zip(observed_times, expected_times)
    )
    identity_ok = bool(artifacts) and all(
        item["plate_id"] == contract["plate_id"]
        and item["barcode"] == contract["barcode"]
        and int(item["plate_version"]) == 1
        for item in artifacts
    )
    read_shape_ok = bool(artifacts) and all(
        int(item["wavelength_nm"]) == 600
        and list(item["wells"]) == [f"A{i}" for i in range(1, 9)]
        and len(item["values"]) == 8
        for item in artifacts
    )
    configured_ok = (
        incubator["target_temperature_c"] is not None
        and abs(float(incubator["target_temperature_c"]) - float(contract["temperature_c"])) <= 0.1
        and bool(incubator["shaking"])
        and abs(float(incubator["shake_rpm"]) - float(contract["shake_rpm"])) <= 0.1
    )
    exposure = float(incubator["conditioned_exposure_s"])
    exposure_ok = exposure >= float(contract["minimum_conditioned_exposure_s"])
    growth_ok = bool(artifacts) and all(
        float(artifacts[-1]["values"][well]) > float(artifacts[0]["values"][well])
        for well in artifacts[0]["wells"]
    )
    decision = conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 1").fetchone()
    latest_id = artifacts[-1]["artifact_id"] if artifacts else None
    decision_ok = bool(
        decision is not None
        and decision["decision"] == "accept"
        and decision["evidence_id"] == latest_id
        and cadence_ok
        and exposure_ok
        and growth_ok
    )
    return [
        _result("incubation_conditions_configured", configured_ok, f"Target {incubator['target_temperature_c']} C; shaking {incubator['shake_rpm']} rpm."),
        _result("plate_identity_preserved", identity_ok, f"OD600 artifacts with expected plate identity: {len(artifacts)}."),
        _result("measurement_series_complete", cadence_ok and read_shape_ok, f"Observed timepoints: {observed_times}; expected: {expected_times}."),
        _result("conditioned_shaking_exposure_complete", exposure_ok, f"Conditioned exposure: {exposure} s; minimum: {contract['minimum_conditioned_exposure_s']} s."),
        _result("growth_series_biologically_ordered", growth_ok, "Every replicate must increase from baseline to the final timepoint."),
        _result("decision_uses_final_growth_evidence", decision_ok, f"Latest evidence: {latest_id!r}."),
    ]


def _verify_powder(conn: Any, state: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    pulse_rows = conn.execute(
        "SELECT seq, payload_json FROM events WHERE operation = 'powder.pulse_dispensed' ORDER BY seq"
    ).fetchall()
    pulses = [loads_json(row["payload_json"]) for row in pulse_rows]
    tare = conn.execute(
        "SELECT seq FROM events WHERE operation = 'balance.tared' ORDER BY seq LIMIT 1"
    ).fetchone()
    tare_before_dose = bool(tare is not None and pulse_rows and int(tare["seq"]) < int(pulse_rows[0]["seq"]))
    powder_identity_ok = bool(pulses) and all(
        pulse["powder"] == contract["powder"] and float(pulse["requested_mg"]) <= float(contract["max_pulse_mg"])
        for pulse in pulses
    )
    measurement_rows = conn.execute(
        "SELECT artifact_id, payload_json FROM artifacts WHERE kind = 'gravimetric_measurement' ORDER BY time_s, artifact_id"
    ).fetchall()
    measurements = [loads_json(row["payload_json"]) for row in measurement_rows]
    feedback_loop_ok = bool(
        len(measurements) >= 2
        and not bool(measurements[0]["within_tolerance"])
        and bool(measurements[-1]["within_tolerance"])
        and len(pulses) >= 2
    )
    final = measurements[-1] if measurements else None
    final_tolerance_ok = bool(
        final
        and final["vial_id"] == contract["vial_id"]
        and final["powder"] == contract["powder"]
        and abs(float(final["measured_mass_mg"]) - float(contract["target_mass_mg"]))
        <= float(contract["tolerance_mg"])
    )
    decision = conn.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 1").fetchone()
    decision_ok = bool(
        decision is not None
        and decision["decision"] == "accept"
        and final is not None
        and decision["evidence_id"] == final["artifact_id"]
        and final_tolerance_ok
    )
    return [
        _result("balance_tared_before_dosing", tare_before_dose, "The empty vial must be tared before the first powder pulse."),
        _result("powder_identity_and_pulses_valid", powder_identity_ok, f"Recorded powder pulses: {len(pulses)}."),
        _result("gravimetric_feedback_loop_complete", feedback_loop_ok, f"Recorded balance measurements: {len(measurements)}."),
        _result("final_mass_within_tolerance", final_tolerance_ok, "The final measured net mass must be inside the declared target band."),
        _result("decision_uses_final_gravimetric_evidence", decision_ok, f"Final evidence: {None if final is None else final['artifact_id']!r}."),
    ]
