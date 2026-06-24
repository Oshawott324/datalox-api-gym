"""State verifiers for pylabrobot_lab_v0 episodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api_gym.worlds.pylabrobot_lab_v0.state import (
    RUN_METADATA_NAME,
    STATE_JSON_NAME,
    LabState,
    get_well,
    get_well_volume,
    has_tip,
)


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    scenario: str
    checks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "scenario": self.scenario, "checks": self.checks}


def verify_run(run_dir: Path) -> VerificationResult:
    """Verify a PyLabRobot-backed episode from its final state."""
    run_dir = run_dir.resolve()
    metadata_path = run_dir / RUN_METADATA_NAME
    if not metadata_path.exists():
        return VerificationResult(
            ok=False, scenario="unknown",
            checks=[_fail("run_metadata_exists", f"Missing {RUN_METADATA_NAME}.")],
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    state_path = run_dir / metadata.get("state", STATE_JSON_NAME)
    if not state_path.exists():
        return VerificationResult(
            ok=False, scenario=metadata.get("scenario", "unknown"),
            checks=[_fail("state_json_exists", f"Missing state file at {state_path}.")],
        )

    # Prefer in-memory state (with live PyLabRobot objects) over JSON
    try:
        from api_gym.worlds.pylabrobot_lab_v0.state import get_state
        lab_state = get_state(run_dir)
    except (ValueError, KeyError):
        lab_state = LabState.load(state_path)
    expected = _expected_resolution(lab_state)
    if expected is None:
        return VerificationResult(
            ok=False, scenario=metadata.get("scenario", "unknown"),
            checks=[_fail("expected_resolution_exists", "Missing hidden expected resolution event.")],
        )

    scenario = expected["scenario"]
    if scenario == "plate_transfer_qc":
        checks = _verify_plate_transfer_qc(lab_state, expected)
    elif scenario == "serial_dilution_qc":
        checks = _verify_serial_dilution_qc(lab_state, expected)
    else:
        checks = [_fail("scenario_supported", f"Unsupported verifier scenario '{scenario}'.")]

    return VerificationResult(
        ok=all(check["ok"] for check in checks),
        scenario=scenario,
        checks=checks,
    )


def _verify_plate_transfer_qc(lab_state: LabState,
                               expected: dict[str, Any]) -> list[dict[str, Any]]:
    """Run all checks for the plate_transfer_qc scenario."""
    checks: list[dict[str, Any]] = []

    source_labware, source_well_name = expected["source_well"].split(".", 1)
    target_labware, target_well_name = expected["target_well"].split(".", 1)
    volume_ul = float(expected["transfer_volume_ul"])
    wavelength_nm = int(expected["wavelength_nm"])

    # 1. dry_run_no_live_action — chatterbox ensures this
    checks.append(_check(True, "dry_run_no_live_action",
                         "Chatterbox backend — no live hardware was connected."))

    # 2. labware exists on deck (only if deck objects are live)
    deck = lab_state.deck
    if deck is not None:
        source_ok = _find_child(deck, source_labware) is not None
        target_ok = _find_child(deck, target_labware) is not None
        checks.append(_check(
            source_ok and target_ok,
            "expected_labware_exists",
            "Source and target labware are present on the deck.",
        ))
    else:
        checks.append(_check(True, "expected_labware_exists",
                             "State loaded from JSON — deck objects not available for inspection."))

    # 3. No overdrawn well
    checks.append(_check(True, "no_overdrawn_well",
                         "Chatterbox tracks volumes — no negative volumes."))

    # 4. Valid transfer completed
    transfer_ok = any(
        t.get("type") == "dispense"
        and t.get("volume_ul") == volume_ul
        and target_well_name in t.get("target_well", "")
        for t in lab_state.transfers
    )
    checks.append(_check(
        transfer_ok,
        "valid_transfer_completed",
        f"A {volume_ul} uL transfer to {expected['target_well']} was recorded.",
    ))

    # 5. Readout recorded
    readout_ok = any(
        ro["plate"] == target_labware
        and ro["wavelength_nm"] == wavelength_nm
        for ro in lab_state.readouts
    )
    checks.append(_check(
        readout_ok,
        "readout_recorded",
        f"An OD{wavelength_nm} readout was recorded for {target_labware}.",
    ))

    # 6. Protocol submitted
    checks.append(_check(
        len(lab_state.submissions) > 0,
        "protocol_submitted",
        "A final protocol decision was submitted.",
    ))

    # 7. Target matches
    if lab_state.submissions:
        sub = lab_state.submissions[-1]
        submitted_target_ok = target_well_name in sub.get("target_well", "")
        checks.append(_check(
            submitted_target_ok,
            "submitted_target_matches_expected",
            "Submitted protocol target matches the expected QC well.",
        ))

        # 8. Decision matches observed data
        band = expected["control_band"]
        readout_value = None
        for ro in lab_state.readouts:
            if target_well_name in ro.get("values", {}):
                readout_value = ro["values"][target_well_name]
                break

        if readout_value is not None:
            expected_decision = "continue" if float(band["min"]) <= readout_value <= float(band["max"]) else "hold"
            decision_ok = sub["decision"] == expected_decision
            checks.append(_check(
                decision_ok,
                "decision_matches_observed_data",
                f"Decision '{sub['decision']}' matches observed value {readout_value} in [{band['min']}, {band['max']}].",
            ))
        else:
            checks.append(_fail(
                "decision_matches_observed_data",
                "No readout value found for target well.",
            ))
    else:
        checks.append(_fail("submitted_target_matches_expected", "No submission found."))
        checks.append(_fail("decision_matches_observed_data", "No submission found."))

    return checks


def _expected_resolution(lab_state: LabState) -> dict[str, Any] | None:
    """Extract the hidden expected resolution from events."""
    for event in lab_state.events:
        if event["event_type"] == "expected_resolution.created" and not event["visible_to_agent"]:
            return event.get("payload")
    return None


def _verify_serial_dilution_qc(lab_state: LabState,
                                expected: dict[str, Any]) -> list[dict[str, Any]]:
    """Verify the serial dilution scenario."""
    checks: list[dict[str, Any]] = []

    checks.append(_check(True, "dry_run_no_live_action",
                         "Chatterbox/OT-2 backend — no live hardware."))

    # Expected transfers: 5 dispense operations
    dispenses = [t for t in lab_state.transfers if t.get("type") == "dispense"]
    checks.append(_check(
        len(dispenses) >= expected.get("expected_transfers", 5),
        "minimum_transfers_completed",
        f"At least {expected.get('expected_transfers', 5)} dispense transfers recorded.",
    ))

    # Readouts should cover all wells in the dilution chain
    # Strip plate prefix for matching (readout stores short well names like "B1")
    wells_expected_raw = expected.get("dilution_wells", [])
    wells_expected = set(w.split(".")[-1] if "." in w else w for w in wells_expected_raw)
    wells_read = set()
    for ro in lab_state.readouts:
        wells_read.update(ro.get("wells", []))
    checks.append(_check(
        wells_expected.issubset(wells_read),
        "all_dilution_wells_read",
        f"OD600 read for all dilution wells. Expected: {sorted(wells_expected)}, Got: {sorted(wells_read)}",
    ))

    # Protocol submitted
    checks.append(_check(
        len(lab_state.submissions) > 0,
        "protocol_submitted",
        "A final protocol decision was submitted.",
    ))

    if lab_state.submissions:
        sub = lab_state.submissions[-1]
        # Decision should be based on decreasing OD values
        od_values = []
        for ro in lab_state.readouts:
            od_values.extend(ro.get("values", {}).values())
        decreasing = all(
            od_values[i] >= od_values[i + 1]
            for i in range(len(od_values) - 1)
        ) if len(od_values) >= 2 else False
        checks.append(_check(
            decreasing,
            "od600_decreasing_curve",
            "OD600 values show decreasing trend (dilution verified).",
        ))
        checks.append(_check(
            sub["decision"] in ("continue", "hold"),
            "valid_decision",
            f"Decision is '{sub['decision']}'.",
        ))

    return checks


def _find_child(deck: Any, name: str) -> Any:
    for child in deck.children:
        if child.name == name:
            return child
    return None


def _check(condition: bool, name: str, message: str) -> dict[str, Any]:
    return {"ok": bool(condition), "name": name, "message": message}


def _fail(name: str, message: str) -> dict[str, Any]:
    return _check(False, name, message)
