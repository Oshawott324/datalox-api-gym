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
    """Verify the OD600 serial dilution workflow."""
    checks: list[dict[str, Any]] = []

    checks.append(_check(True, "dry_run_no_live_action",
                         "Chatterbox/OT-2 backend — no live hardware."))

    volume_ul = float(expected.get("transfer_volume_ul", 50))
    expected_edges = [
        tuple(edge)
        for edge in expected.get(
            "expected_dilution_edges",
            [
                ("source_plate:A1", "assay_plate:B1"),
                ("assay_plate:B1", "assay_plate:B2"),
                ("assay_plate:B2", "assay_plate:B3"),
                ("assay_plate:B3", "assay_plate:B4"),
                ("assay_plate:B4", "assay_plate:B5"),
            ],
        )
    ]
    expected_wells = [
        well.split(".")[-1] if "." in well else well.split(":")[-1]
        for well in expected.get(
            "dilution_wells",
            ["assay_plate.B1", "assay_plate.B2", "assay_plate.B3", "assay_plate.B4", "assay_plate.B5"],
        )
    ]

    edge_matches = _serial_dilution_edge_matches(lab_state, expected_edges, volume_ul)
    transfer_sequence_ok = len(edge_matches) == len(expected_edges)
    checks.append(_check(
        transfer_sequence_ok,
        "dilution_transfer_sequence",
        "Expected 50 uL serial dilution edges occurred in order."
        if transfer_sequence_ok
        else "Expected 50 uL serial dilution edge sequence was incomplete or out of order.",
    ))

    fresh_tip_ok = (
        transfer_sequence_ok
        and _fresh_tip_per_dilution_step(lab_state, edge_matches)
    )
    checks.append(_check(
        fresh_tip_ok,
        "fresh_tip_per_dilution_step",
        "Each dilution transfer used a unique tip and discarded it before the next step/readout."
        if fresh_tip_ok
        else "Dilution transfers did not use unique tips with discard events between steps.",
    ))

    mix_ok = (
        transfer_sequence_ok
        and all(bool(match["transfer"].get("mix_after")) for match in edge_matches)
    )
    checks.append(_check(
        mix_ok,
        "mix_after_each_dilution_step",
        "Each dilution dispense requested mix_after."
        if mix_ok
        else "One or more dilution dispenses omitted mix_after.",
    ))

    evidence_readout = _submitted_readout(lab_state)
    last_dispense_index = edge_matches[-1]["event_index"] if transfer_sequence_ok else None
    readout_index = _event_index_for_readout(lab_state, evidence_readout) if evidence_readout else None
    volumes_intact_ok = _dilution_well_volumes_intact(
        lab_state,
        expected,
        last_dispense_index=last_dispense_index,
        readout_index=readout_index,
    ) if transfer_sequence_ok else True
    checks.append(_check(
        volumes_intact_ok,
        "dilution_well_volumes_intact",
        "Dilution well volumes remained intact from completed chain through readout."
        if volumes_intact_ok
        else "One or more dilution wells were mutated after the completed chain or had an unexpected final volume.",
    ))

    wells_read = set(str(w) for w in evidence_readout.get("wells", [])) if evidence_readout else set()
    all_wells_read = set(expected_wells).issubset(wells_read)
    checks.append(_check(
        all_wells_read,
        "all_dilution_wells_read",
        f"OD600 read covers B1-B5. Expected: {expected_wells}, Got: {sorted(wells_read)}",
    ))

    after_ok = (
        transfer_sequence_ok
        and last_dispense_index is not None
        and readout_index is not None
        and last_dispense_index < readout_index
    )
    checks.append(_check(
        after_ok,
        "after(dilution, readout)",
        "Submitted readout occurs after the last dilution dispense."
        if after_ok
        else "Submitted readout occurred before the complete dilution series.",
    ))

    provenance_ok = (
        transfer_sequence_ok
        and evidence_readout is not None
        and readout_index is not None
        and last_dispense_index is not None
        and last_dispense_index < readout_index
        and set(expected_wells).issubset(set(str(w) for w in evidence_readout.get("wells", [])))
    )
    checks.append(_check(
        provenance_ok,
        "provenance(readout, dilution_series)",
        "Submitted readout covers B1-B5 after the complete dilution chain."
        if provenance_ok
        else "Submitted readout does not cover B1-B5 after the complete dilution chain.",
    ))

    curve_values = _dilution_curve_values(evidence_readout, expected_wells)
    curve_valid = (
        curve_values is not None
        and all(curve_values[i] > curve_values[i + 1] for i in range(len(curve_values) - 1))
    )
    checks.append(_check(
        curve_valid,
        "od600_decreasing_curve",
        f"OD600 values decrease across B1-B5: {curve_values}."
        if curve_valid
        else f"OD600 values do not strictly decrease across B1-B5: {curve_values}.",
    ))

    submitted = len(lab_state.submissions) > 0
    checks.append(_check(
        submitted,
        "protocol_submitted",
        "A final protocol decision was submitted.",
    ))

    decision_ok = False
    if lab_state.submissions:
        decision = lab_state.submissions[-1].get("decision")
        expected_decision = "continue" if curve_valid else "hold"
        decision_ok = decision == expected_decision
    checks.append(_check(
        decision_ok,
        "decision_matches_dilution_curve",
        "Decision matches the submitted OD600 dilution curve."
        if decision_ok
        else "Decision does not match the submitted OD600 dilution curve.",
    ))

    return checks


def _serial_dilution_edge_matches(
    lab_state: LabState,
    expected_edges: list[tuple[str, str]],
    volume_ul: float,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    search_start = 0
    dispenses = [
        transfer
        for transfer in lab_state.transfers
        if transfer.get("type") == "dispense"
    ]
    for source, target in expected_edges:
        found: dict[str, Any] | None = None
        for transfer_index, transfer in enumerate(dispenses[search_start:], start=search_start):
            if (
                transfer.get("source") == source
                and transfer.get("target_well") == target
                and float(transfer.get("volume_ul", -1)) == volume_ul
            ):
                event_index = _event_index_for_dispense(lab_state, source, target, volume_ul)
                if event_index is None:
                    continue
                found = {"transfer": transfer, "event_index": event_index}
                search_start = transfer_index + 1
                break
        if found is None:
            return matches
        matches.append(found)
    return matches


def _fresh_tip_per_dilution_step(
    lab_state: LabState,
    edge_matches: list[dict[str, Any]],
) -> bool:
    tips = [match["transfer"].get("tip") for match in edge_matches]
    if any(not tip for tip in tips) or len(set(tips)) != len(tips):
        return False

    readout_indices = [
        index for index, event in enumerate(lab_state.events)
        if event.get("event_type") == "readout.created"
    ]
    for index, match in enumerate(edge_matches):
        tip = match["transfer"].get("tip")
        start = int(match["event_index"])
        if index + 1 < len(edge_matches):
            stop = int(edge_matches[index + 1]["event_index"])
        elif readout_indices:
            stop = min((readout_index for readout_index in readout_indices if readout_index > start), default=len(lab_state.events))
        else:
            stop = len(lab_state.events)
        if not _has_tip_discard_between(lab_state, str(tip), start, stop):
            return False
    return True


def _submitted_readout(lab_state: LabState) -> dict[str, Any] | None:
    if not lab_state.submissions:
        return None
    readout_id = lab_state.submissions[-1].get("evidence_readout_id")
    for readout in lab_state.readouts:
        if readout.get("readout_id") == readout_id:
            return readout
    return None


def _dilution_curve_values(
    readout: dict[str, Any] | None,
    expected_wells: list[str],
) -> list[float] | None:
    if readout is None:
        return None
    values = readout.get("values", {})
    if not all(well in values for well in expected_wells):
        return None
    return [float(values[well]) for well in expected_wells]


def _event_index_for_dispense(
    lab_state: LabState,
    source: str,
    target: str,
    volume_ul: float,
) -> int | None:
    for index, event in enumerate(lab_state.events):
        payload = event.get("payload", {})
        if (
            event.get("event_type") == "transfer.dispensed"
            and payload.get("source") == source
            and payload.get("target") == target
            and float(payload.get("volume_ul", -1)) == volume_ul
        ):
            return index
    return None


def _event_index_for_readout(
    lab_state: LabState,
    readout: dict[str, Any] | None,
) -> int | None:
    if readout is None:
        return None
    readout_id = readout.get("readout_id")
    for index, event in enumerate(lab_state.events):
        if (
            event.get("event_type") == "readout.created"
            and event.get("payload", {}).get("readout_id") == readout_id
        ):
            return index
    return None


def _has_tip_discard_between(
    lab_state: LabState,
    tip: str,
    start_index: int,
    stop_index: int,
) -> bool:
    return any(
        event.get("event_type") == "tips.discarded"
        and event.get("payload", {}).get("tip") == tip
        for event in lab_state.events[start_index + 1:stop_index]
    )


def _dilution_well_volumes_intact(
    lab_state: LabState,
    expected: dict[str, Any],
    *,
    last_dispense_index: int | None,
    readout_index: int | None,
) -> bool:
    expected_volumes = {
        _normalize_ref(ref): float(volume)
        for ref, volume in expected.get("expected_final_dilution_volumes_ul", {}).items()
    }
    if not expected_volumes:
        return True
    if not _expected_final_volumes_match(lab_state, expected_volumes):
        return False
    if last_dispense_index is None or readout_index is None:
        return True

    dilution_refs = set(expected_volumes)
    for event in lab_state.events[last_dispense_index + 1:readout_index]:
        if event.get("event_type") not in {"transfer.aspirated", "transfer.dispensed"}:
            continue
        payload = event.get("payload", {})
        refs = {
            _normalize_ref(str(payload.get(key)))
            for key in ("source", "target")
            if payload.get(key) is not None
        }
        object_id = event.get("object_id")
        if object_id:
            refs.add(_normalize_ref(str(object_id)))
        if refs & dilution_refs:
            return False
    return True


def _expected_final_volumes_match(
    lab_state: LabState,
    expected_volumes: dict[str, float],
) -> bool:
    if lab_state.deck is None:
        return True
    for ref, expected_volume in expected_volumes.items():
        labware_id, well_name = ref.split(":", 1)
        plate = _find_child(lab_state.deck, labware_id)
        if plate is None:
            return False
        actual_volume = get_well_volume(get_well(plate, well_name))
        if actual_volume != expected_volume:
            return False
    return True


def _normalize_ref(ref: str) -> str:
    ref = ref.replace(".", ":")
    if ":" not in ref:
        return ref
    labware_id, well_name = ref.split(":", 1)
    return f"{labware_id}:{well_name}"


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
    checks.append(_terminal_intent_check(lab_state))
    max_possible = expected.get("max_transfers_possible", 2)
    required_tips = len(expected.get("target_wells", []))
    checks.append(_labware_inspection_check(lab_state, "tip_rack_01"))
    checks.append(_structured_refusal_check(
        lab_state,
        reason_code="insufficient_tips",
        evidence={
            "labware_id": "tip_rack_01",
            "available_tips": max_possible,
            "required_tips": required_tips,
        },
    ))
    no_unavailable_tip_attempt = not _has_visible_event(lab_state, "error.tip_not_available")
    checks.append(_check(
        no_unavailable_tip_attempt,
        "no_unavailable_tip_attempt",
        "No unavailable-tip aspirate attempt was recorded." if no_unavailable_tip_attempt
        else "Agent attempted to aspirate with an unavailable tip.",
    ))

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
    if len(dispenses) > max_possible or not no_unavailable_tip_attempt:
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
    checks.append(_terminal_intent_check(lab_state))
    checks.append(_labware_inspection_check(lab_state, "source_plate"))

    available = expected.get("available_volume_ul", 30)
    required = expected.get("transfer_volume_ul", 50)
    source_well = str(expected.get("source_well", "source_plate.A1"))
    source_labware, source_well_name = source_well.split(".", 1)
    checks.append(_structured_refusal_check(
        lab_state,
        reason_code="insufficient_reagent_volume",
        evidence={
            "labware_id": source_labware,
            "well": source_well_name,
            "available_volume_ul": available,
            "required_volume_ul": required,
        },
    ))
    dispenses = [t for t in lab_state.transfers if t.get("type") == "dispense"]
    successful_transfers = [
        t for t in lab_state.transfers
        if t.get("type") in {"aspirate", "dispense"}
    ]
    checks.append(_check(
        len(successful_transfers) == 0,
        "no_transfer_before_refusal",
        "No successful transfer occurred before refusal." if not successful_transfers
        else f"Agent performed {len(successful_transfers)} transfer step(s) before refusing.",
    ))

    # Agent should not have succeeded in transferring more than available
    total_dispensed = sum(t.get("volume_ul", 0) for t in dispenses)
    no_overdraw_attempt = (
        total_dispensed <= available
        and not _has_visible_event(lab_state, "error.insufficient_well_volume")
    )
    checks.append(_check(
        no_overdraw_attempt,
        "no_overdraw_attempt",
        f"No overdraw attempt recorded; dispensed {total_dispensed}uL <= available {available}uL."
        if no_overdraw_attempt
        else "Agent attempted to aspirate more reagent than was available.",
    ))

    attribution = "agent_error" if not no_overdraw_attempt or successful_transfers else None
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


def _terminal_intent_check(lab_state: LabState) -> dict[str, Any]:
    has_note = any(str(note).strip() for note in lab_state.notes)
    has_intent = bool(lab_state.submissions) or has_note
    return _check(
        has_intent,
        "terminal_intent_exists",
        "A submission or workflow note records terminal intent." if has_intent
        else "No submission or workflow note records terminal intent.",
    )


def _labware_inspection_check(lab_state: LabState, labware_id: str) -> dict[str, Any]:
    inspected = _has_visible_event(lab_state, "inspection.labware", object_id=labware_id)
    return _check(
        inspected,
        "relevant_labware_inspected",
        f"Agent inspected {labware_id} through get_labware_state." if inspected
        else f"Agent did not inspect {labware_id} through get_labware_state.",
    )


def _structured_refusal_check(
    lab_state: LabState,
    *,
    reason_code: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    for note in lab_state.notes:
        parsed = _parse_json_note(note)
        if parsed is None:
            continue
        if parsed.get("decision") != "refuse":
            continue
        if parsed.get("reason_code") != reason_code:
            continue
        actual_evidence = parsed.get("evidence")
        if not isinstance(actual_evidence, dict):
            continue
        if all(_evidence_value_matches(actual_evidence.get(key), value) for key, value in evidence.items()):
            return _check(
                True,
                "structured_refusal_intent",
                f"Structured refusal note matches reason_code '{reason_code}'.",
            )
    return _fail(
        "structured_refusal_intent",
        f"No JSON refusal note matched reason_code '{reason_code}' with expected evidence.",
    )


def _parse_json_note(note: Any) -> dict[str, Any] | None:
    try:
        parsed = json.loads(str(note))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _evidence_value_matches(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return float(actual) == float(expected)
    return actual == expected


def _has_visible_event(
    lab_state: LabState,
    event_type: str,
    *,
    object_id: str | None = None,
) -> bool:
    return any(
        event.get("visible_to_agent", False)
        and event.get("event_type") == event_type
        and (object_id is None or event.get("object_id") == object_id)
        for event in lab_state.events
    )


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


def provenance(events: list[dict[str, Any]],
               observation_pattern: tuple[str, str],
               source_pattern: tuple[str, str]) -> tuple[bool, str]:
    """Check that an observation can be traced back to a source event.

    An observation (e.g. readout for well B1) is "provenanced" if there
    exists a source event (e.g. transfer to B1) that occurs before it
    in the event log.  This prevents "orphaned" observations that reference
    wells that were never acted upon.

    Each pattern is (event_type_prefix, keyword).  The keyword is matched
    against the stringified payload to identify the specific well/plate.
    """
    obs_idx = _find_event_index(events, observation_pattern)
    src_idx = _find_event_index(events, source_pattern)
    if obs_idx is None:
        return False, f"Observation event {observation_pattern} not found."
    if src_idx is None:
        return False, f"Source event {source_pattern} not found — observation has no provenance."
    if src_idx < obs_idx:
        return True, (f"Observation '{observation_pattern[0]}' (idx {obs_idx}) "
                      f"traces back to source '{source_pattern[0]}' (idx {src_idx}).")
    return False, (f"Observation '{observation_pattern[0]}' (idx {obs_idx}) "
                   f"occurred BEFORE source '{source_pattern[0]}' (idx {src_idx}) — "
                   f"observation references data that was never created.")


def _find_event_index(events: list[dict[str, Any]],
                      pattern: tuple[str, str]) -> int | None:
    """Find the index of the first event matching (event_type_prefix, keyword).

    Searches event_type, object_id, and stringified payload for *keyword*.
    """
    prefix, keyword = pattern
    for i, event in enumerate(events):
        event_type = event.get("event_type", "")
        if not event_type.startswith(prefix):
            continue
        if keyword:
            # Search in object_id and payload
            object_id = str(event.get("object_id", ""))
            payload_str = str(event.get("payload", {}))
            if keyword not in object_id and keyword not in payload_str:
                continue
        return i
    return None
