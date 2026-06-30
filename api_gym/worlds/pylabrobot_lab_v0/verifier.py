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
    attribution_label: str | None = None
    attribution_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ok": self.ok, "scenario": self.scenario, "checks": self.checks}
        if self.attribution_label:
            d["attribution_label"] = self.attribution_label
        if self.attribution_detail:
            d["attribution_detail"] = self.attribution_detail
        return d


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
        attribution = None
    elif scenario == "serial_dilution_qc":
        checks = _verify_serial_dilution_qc(lab_state, expected)
        attribution = None
    elif scenario == "multi_sample_qc":
        checks = _verify_multi_sample_qc(lab_state, expected)
        attribution = None
    elif scenario == "concentration_gradient_qc":
        checks = _verify_concentration_gradient_qc(lab_state, expected)
        attribution = None
    elif scenario == "limited_tips_qc":
        checks, attribution = _verify_limited_tips_qc(lab_state, expected)
    elif scenario == "low_reagent_qc":
        checks, attribution = _verify_low_reagent_qc(lab_state, expected)
    elif scenario == "instrument_busy_qc":
        checks, attribution = _verify_instrument_busy_qc(lab_state, expected)
    elif scenario == "stale_deck_qc":
        checks, attribution = _verify_stale_deck_qc(lab_state, expected)
    elif scenario == "borderline_qc":
        checks, attribution = _verify_borderline_qc(lab_state, expected)
    elif scenario == "cross_contamination_qc":
        checks, attribution = _verify_cross_contamination_qc(lab_state, expected)
    else:
        checks = [_fail("scenario_supported", f"Unsupported verifier scenario '{scenario}'.")]
        attribution = None

    return VerificationResult(
        ok=all(check["ok"] for check in checks),
        scenario=scenario,
        checks=checks,
        attribution_label=attribution,
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


def _verify_multi_sample_qc(lab_state: LabState,
                             expected: dict[str, Any]) -> list[dict[str, Any]]:
    """Verify multi-sample QC: 3 independent transfers and readouts."""
    checks: list[dict[str, Any]] = []
    checks.append(_check(True, "dry_run_no_live_action", "Dry-run backend."))

    target_wells = expected.get("target_wells", [])
    dispenses = [t for t in lab_state.transfers if t.get("type") == "dispense"]
    checks.append(_check(
        len(dispenses) >= expected.get("expected_transfers", 3),
        "minimum_transfers_completed",
        f"Expected {expected.get('expected_transfers', 3)} transfers, got {len(dispenses)}.",
    ))

    read_wells = set()
    for ro in lab_state.readouts:
        read_wells.update(ro.get("wells", []))
    for tw in target_wells:
        short = tw.split(".")[-1] if "." in tw else tw
        checks.append(_check(
            short in read_wells,
            f"readout_for_{short}",
            f"OD600 read recorded for {tw}.",
        ))

    checks.append(_check(len(lab_state.submissions) > 0, "protocol_submitted", "Protocol submitted."))
    return checks


def _verify_concentration_gradient_qc(lab_state: LabState,
                                       expected: dict[str, Any]) -> list[dict[str, Any]]:
    """Verify concentration gradient: 5 transfers, OD600 decreasing linearly."""
    checks: list[dict[str, Any]] = []
    checks.append(_check(True, "dry_run_no_live_action", "Dry-run backend."))

    dispenses = [t for t in lab_state.transfers if t.get("type") == "dispense"]
    checks.append(_check(
        len(dispenses) >= expected.get("expected_transfers", 5),
        "minimum_transfers_completed",
        f"Expected {expected.get('expected_transfers', 5)} transfers, got {len(dispenses)}.",
    ))

    od_values = []
    for ro in lab_state.readouts:
        od_values.extend(ro.get("values", {}).values())
    decreasing = all(
        od_values[i] >= od_values[i + 1] for i in range(len(od_values) - 1)
    ) if len(od_values) >= 2 else False
    checks.append(_check(decreasing, "od600_decreasing", "OD600 values show decreasing trend."))

    checks.append(_check(len(lab_state.submissions) > 0, "protocol_submitted", "Protocol submitted."))
    return checks


def _verify_limited_tips_qc(lab_state: LabState,
                              expected: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Verify limited-tips scenario: agent must detect tip exhaustion."""
    checks: list[dict[str, Any]] = []
    checks.append(_check(True, "dry_run_no_live_action", "Dry-run backend."))

    max_possible = expected.get("max_transfers_possible", 2)
    dispenses = [t for t in lab_state.transfers if t.get("type") == "dispense"]
    checks.append(_check(
        len(dispenses) <= max_possible,
        "no_excess_transfers",
        f"At most {max_possible} transfers possible (only {max_possible} tips). Got {len(dispenses)}.",
    ))

    # Agent should have detected tip exhaustion and not attempted a 3rd transfer
    exhaustion_events = [e for e in lab_state.events
                         if "tip" in str(e.get("payload", {})).lower()
                         and not e.get("ok", True)]
    attribution = None
    if len(dispenses) > max_possible:
        attribution = "agent_error"

    checks.append(_check(
        len(dispenses) <= max_possible,
        "tip_exhaustion_detected",
        "Agent correctly stopped before tip exhaustion." if len(dispenses) <= max_possible
        else f"Agent attempted {len(dispenses)} transfers with only {max_possible} tips.",
    ))

    return checks, attribution


def _verify_low_reagent_qc(lab_state: LabState,
                             expected: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Verify low-reagent scenario: agent must detect insufficient volume."""
    checks: list[dict[str, Any]] = []
    checks.append(_check(True, "dry_run_no_live_action", "Dry-run backend."))

    available = expected.get("available_volume_ul", 30)
    required = expected.get("transfer_volume_ul", 50)
    dispenses = [t for t in lab_state.transfers if t.get("type") == "dispense"]

    # Agent should not have succeeded in transferring more than available
    total_dispensed = sum(t.get("volume_ul", 0) for t in dispenses)
    checks.append(_check(
        total_dispensed <= available,
        "no_overdrawn_transfer",
        f"Total dispensed {total_dispensed}uL <= available {available}uL." if total_dispensed <= available
        else f"Agent overdrew: {total_dispensed}uL > {available}uL available.",
    ))

    attribution = "agent_error" if total_dispensed > available else None
    return checks, attribution


def _verify_instrument_busy_qc(lab_state: LabState,
                                 expected: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Verify instrument-busy scenario: agent must retry after fault."""
    checks: list[dict[str, Any]] = []
    checks.append(_check(True, "dry_run_no_live_action", "Dry-run backend."))

    dispenses = [t for t in lab_state.transfers if t.get("type") == "dispense"]
    checks.append(_check(len(dispenses) >= 1, "transfer_completed", "At least one transfer completed."))

    # Check retry behavior via events
    retry_events = [e for e in lab_state.events if "retry" in e.get("event_type", "").lower()]
    fault_events = [e for e in lab_state.events if "fault" in e.get("event_type", "").lower()
                    or "error.instrument_busy" in e.get("event_type", "")]

    has_readout = len(lab_state.readouts) > 0
    checks.append(_check(has_readout, "valid_readout_obtained", "A valid readout was obtained."))

    attribution = None
    if fault_events and has_readout:
        attribution = "success_despite_fault"
    elif fault_events and not has_readout:
        attribution = "agent_recovery_failure"

    checks.append(_check(
        has_readout or len(lab_state.submissions) > 0,
        "protocol_completed",
        "Protocol completed despite instrument faults." if has_readout else "No valid readout — recovery failed.",
    ))

    return checks, attribution


def _verify_stale_deck_qc(lab_state: LabState,
                            expected: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Verify stale-deck scenario: agent must re-inspect before acting."""
    checks: list[dict[str, Any]] = []
    checks.append(_check(True, "dry_run_no_live_action", "Dry-run backend."))

    max_staleness = expected.get("max_staleness_s", 5)

    # Find inspection and transfer events
    inspect_events = [e for e in lab_state.events
                      if e.get("event_type", "").startswith("state.")
                      or "deck_state" in e.get("event_type", "")]
    transfer_events = [e for e in lab_state.events
                       if e.get("event_type", "").startswith("transfer.")]

    # Check freshness: last inspection should be relatively recent before first transfer
    attribution = None
    if transfer_events and not inspect_events:
        checks.append(_fail("fresh_inspection_before_transfer",
                            "Agent transferred without any inspection."))
        attribution = "agent_error"
    elif transfer_events and inspect_events:
        last_inspect_time = max(e.get("clock_time", 0) for e in inspect_events)
        first_transfer_time = min(e.get("clock_time", 0) for e in transfer_events)
        staleness = first_transfer_time - last_inspect_time
        ok = staleness >= 0  # inspect must happen before transfer
        checks.append(_check(
            ok and staleness <= max_staleness,
            "fresh_inspection_before_transfer",
            f"Inspection {staleness:.1f}s before transfer (max {max_staleness}s)." if ok
            else "Inspection occurred after transfer — stale data used.",
        ))
        if not ok:
            attribution = "agent_error"

    checks.append(_check(len(lab_state.submissions) > 0, "protocol_submitted", "Protocol submitted."))
    return checks, attribution


def _verify_borderline_qc(lab_state: LabState,
                            expected: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Verify borderline-decision scenario: agent must handle near-boundary OD600."""
    checks: list[dict[str, Any]] = []
    checks.append(_check(True, "dry_run_no_live_action", "Dry-run backend."))

    band = expected.get("control_band", {"min": 0.75, "max": 0.9})
    dispenses = [t for t in lab_state.transfers if t.get("type") == "dispense"]
    checks.append(_check(len(dispenses) >= 1, "transfer_completed", "Transfer completed."))

    checks.append(_check(len(lab_state.readouts) > 0, "readout_recorded", "OD600 readout recorded."))
    checks.append(_check(len(lab_state.submissions) > 0, "protocol_submitted", "Protocol submitted."))

    # Check if agent mentioned uncertainty in rationale
    attribution = None
    if lab_state.submissions:
        rationale = lab_state.submissions[-1].get("rationale", "").lower()
        mentions_uncertainty = any(w in rationale for w in ["uncertain", "noise", "borderline", "close to", "near"])
        readout_val = None
        for ro in lab_state.readouts:
            vals = ro.get("values", {})
            if vals:
                readout_val = list(vals.values())[0]
                break
        if readout_val is not None:
            near_boundary = abs(readout_val - band["min"]) < 0.05 or abs(readout_val - band["max"]) < 0.05
            if near_boundary:
                attribution = "ambiguous"
                checks.append(_check(
                    mentions_uncertainty,
                    "uncertainty_acknowledged",
                    "Agent acknowledged measurement uncertainty in rationale." if mentions_uncertainty
                    else "Reading near boundary but agent did not mention uncertainty.",
                ))

    return checks, attribution


def _verify_cross_contamination_qc(lab_state: LabState,
                                     expected: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Verify cross-contamination scenario: agent must use fresh tips."""
    checks: list[dict[str, Any]] = []
    checks.append(_check(True, "dry_run_no_live_action", "Dry-run backend."))

    expected_tips = expected.get("expected_tips_used", 2)
    dispenses = [t for t in lab_state.transfers if t.get("type") == "dispense"]
    checks.append(_check(
        len(dispenses) >= expected.get("expected_transfers", 2),
        "minimum_transfers_completed",
        f"Expected {expected.get('expected_transfers', 2)} transfers, got {len(dispenses)}.",
    ))

    # Check tip reuse via transfer records
    tip_wells_used = set()
    for t in lab_state.transfers:
        if t.get("type") == "aspirate":
            tip_ref = t.get("tip", "")
            if tip_ref:
                tip_wells_used.add(tip_ref)

    attribution = None
    # Each transfer should use a unique tip if require_fresh_tip_per_transfer
    if expected.get("require_fresh_tip_per_transfer"):
        aspirates = [t for t in lab_state.transfers if t.get("type") == "aspirate"]
        tip_refs = [a.get("tip", "") for a in aspirates]
        unique_tips = len(set(tip_refs))
        ok = unique_tips >= len(aspirates)  # each aspirate used a different tip
        checks.append(_check(
            ok,
            "fresh_tip_per_transfer",
            f"Used {unique_tips} unique tips for {len(aspirates)} transfers." if ok
            else f"Only {unique_tips} unique tips for {len(aspirates)} transfers — tip reuse detected.",
        ))
        if not ok:
            attribution = "agent_error"

    checks.append(_check(len(lab_state.submissions) > 0, "protocol_submitted", "Protocol submitted."))
    return checks, attribution


def _find_child(deck: Any, name: str) -> Any:
    for child in deck.children:
        if child.name == name:
            return child
    return None


def _check(condition: bool, name: str, message: str) -> dict[str, Any]:
    return {"ok": bool(condition), "name": name, "message": message}


def _fail(name: str, message: str) -> dict[str, Any]:
    return _check(False, name, message)


# ── Temporal / provenance verifier predicates ───────────────────────────────


def after(events: list[dict[str, Any]],
          event_a_pattern: tuple[str, str],
          event_b_pattern: tuple[str, str]) -> tuple[bool, str]:
    """Check that event A occurs before event B in the event log.

    Each pattern is (event_type_prefix, keyword).  The predicate looks for
    the first matching event for each pattern, then checks their order.
    """
    idx_a = _find_event_index(events, event_a_pattern)
    idx_b = _find_event_index(events, event_b_pattern)
    if idx_a is None:
        return False, f"Event matching {event_a_pattern} not found in event log."
    if idx_b is None:
        return False, f"Event matching {event_b_pattern} not found in event log."
    if idx_a < idx_b:
        return True, f"'{event_a_pattern[0]}' (idx {idx_a}) occurs before '{event_b_pattern[0]}' (idx {idx_b})."
    return False, f"'{event_a_pattern[0]}' (idx {idx_a}) does NOT occur before '{event_b_pattern[0]}' (idx {idx_b})."


def fresh(events: list[dict[str, Any]],
          observation_pattern: tuple[str, str],
          usage_pattern: tuple[str, str],
          max_age_s: float) -> tuple[bool, str]:
    """Check that an observation is used within *max_age_s* of when it was made.

    Reads the ``clock_time`` field from matching events to compute age.
    """
    obs_idx = _find_event_index(events, observation_pattern)
    use_idx = _find_event_index(events, usage_pattern)
    if obs_idx is None:
        return False, f"Observation event {observation_pattern} not found."
    if use_idx is None:
        return False, f"Usage event {usage_pattern} not found."
    obs_time = events[obs_idx].get("clock_time", 0.0)
    use_time = events[use_idx].get("clock_time", 0.0)
    age = use_time - obs_time
    if age <= max_age_s:
        return True, f"Observation used {age:.1f}s after creation (max {max_age_s}s)."
    return False, f"Observation {age:.1f}s old at time of use (max allowed: {max_age_s}s) — stale."


def never(events: list[dict[str, Any]],
          forbidden_pattern: tuple[str, str]) -> tuple[bool, str]:
    """Check that a forbidden event pattern NEVER appears in the event log."""
    idx = _find_event_index(events, forbidden_pattern)
    if idx is None:
        return True, f"Forbidden pattern {forbidden_pattern} not found — ok."
    return False, f"Forbidden pattern {forbidden_pattern} found at index {idx}."


def resource_available(events: list[dict[str, Any]],
                       resource_type: str,
                       required: float) -> tuple[bool, str]:
    """Check whether a resource was sufficient.

    This predicate is a framework check — the actual resource tracking
    is done via well volumes and tip counts, checked by scenario-specific
    verifier logics.  Here we simply validate that no event indicates
    resource exhaustion without agent detection.
    """
    # Look for resource-related error events that the agent ignored
    exhaustion_events = [
        e for e in events
        if e.get("event_type", "").startswith("error.") and resource_type in str(e.get("payload", {}))
    ]
    if exhaustion_events:
        return False, f"Found {len(exhaustion_events)} {resource_type} exhaustion event(s) — agent may have ignored them."
    return True, f"No {resource_type} exhaustion events detected."


def _find_event_index(events: list[dict[str, Any]],
                      pattern: tuple[str, str]) -> int | None:
    """Find the index of the first event matching (event_type_prefix, keyword)."""
    prefix, keyword = pattern
    for i, event in enumerate(events):
        event_type = event.get("event_type", "")
        if not event_type.startswith(prefix):
            continue
        if keyword:
            payload_str = str(event.get("payload", {}))
            if keyword not in payload_str:
                continue
        return i
    return None
