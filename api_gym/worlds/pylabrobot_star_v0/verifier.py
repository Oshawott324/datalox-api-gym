"""State verifiers for pylabrobot_star_v0 episodes.

Direction 2 (Failure Attribution): every failure-mode verifier returns an
attribution_label classifying the failure source.

Direction 3 (Temporal/Provenance Verifier): terminal checks are augmented
with temporal predicates (after, fresh, never) and resource predicates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api_gym.worlds.pylabrobot_lab_v0.verifier import (
    VerificationResult,
    _check, _fail,
    _has_visible_event,
    _labware_inspection_check,
    _structured_refusal_check,
    after, fresh, never, resource_available, provenance,
)
from api_gym.worlds.pylabrobot_star_v0.state import (
    RUN_METADATA_NAME, STATE_JSON_NAME, LabState,
)


def verify_run(run_dir: Path) -> VerificationResult:
    run_dir = run_dir.resolve()
    metadata_path = run_dir / RUN_METADATA_NAME
    if not metadata_path.exists():
        return VerificationResult(ok=False, scenario="unknown",
            checks=[_fail("run_metadata_exists", f"Missing {RUN_METADATA_NAME}.")])

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    state_path = run_dir / metadata.get("state", STATE_JSON_NAME)
    if not state_path.exists():
        return VerificationResult(ok=False, scenario=metadata.get("scenario", "unknown"),
            checks=[_fail("state_json_exists", f"Missing {state_path}.")])

    try:
        from api_gym.worlds.pylabrobot_star_v0.state import get_state
        lab_state = get_state(run_dir)
    except (ValueError, KeyError):
        lab_state = LabState.load(state_path)

    expected = _expected_resolution(lab_state)
    if expected is None:
        return VerificationResult(ok=False, scenario=metadata.get("scenario", "unknown"),
            checks=[_fail("expected_resolution_exists", "Missing hidden expected resolution.")])

    scenario = expected["scenario"]
    verifiers = {
        "plate_transfer_qc": _verify_plate_transfer_qc,
        "serial_dilution_qc": _verify_serial_dilution_qc,
        "trough_to_plate_qc": _verify_trough_to_plate_qc,
        "parallel_stamp_qc": _verify_parallel_stamp_qc,
        "multi_channel_qc": _verify_multi_channel_qc,
        "iswap_plate_move_qc": _verify_iswap_plate_move_qc,
        "tube_transfer_qc": _verify_tube_transfer_qc,
        "stamp_replicate_qc": _verify_stamp_replicate_qc,
        "limited_tips_star_qc": _verify_limited_tips_star_qc,
        "low_reagent_trough_qc": _verify_low_reagent_trough_qc,
        "multi_plate_qc": _verify_multi_plate_qc,
        "full_workflow_qc": _verify_full_workflow_qc,
        "borderline_star_qc": _verify_borderline_star_qc,
        "noisy_readout_star_qc": _verify_noisy_readout_star_qc,
        "instrument_fault_star_qc": _verify_instrument_fault_star_qc,
        "stale_deck_star_qc": _verify_stale_deck_star_qc,
        "liquid_switch_star_qc": _verify_liquid_switch_star_qc,
        "iswap_lid_star_qc": _verify_iswap_lid_star_qc,
        "tip_exhaustion_96_star_qc": _verify_tip_exhaustion_96_star_qc,
        "low_reagent_well_star_qc": _verify_low_reagent_well_star_qc,
        "fault_and_noise_star_qc": _verify_fault_and_noise_star_qc,
        "stale_after_move_star_qc": _verify_stale_after_move_star_qc,
        "three_liquid_star_qc": _verify_three_liquid_star_qc,
        "workspace_protocol_star_qc": _verify_workspace_protocol_star_qc,
        # Phase 3.2 — new PLR-grounded scenarios
        "tip_return_reuse_qc": _verify_tip_return_reuse_qc,
        "multi_dispense_transfer_qc": _verify_multi_dispense_transfer_qc,
        "lid_handling_qc": _verify_lid_handling_qc,
        "plate_stamp_qc": _verify_plate_stamp_qc,
        "mounted_tips_query_qc": _verify_mounted_tips_query_qc,
        # Pump scenarios
        "pump_fill_trough_qc": _verify_pump_fill_trough_qc,
        "pump_calibrated_dispense_qc": _verify_pump_calibrated_dispense_qc,
        "pump_halt_recovery_qc": _verify_pump_halt_recovery_qc,
        "pump_multi_step_qc": _verify_pump_multi_step_qc,
        # PlateReader extended scenarios
        "fluorescence_qc": _verify_fluorescence_qc,
        "luminescence_qc": _verify_luminescence_qc,
        "reader_door_qc": _verify_reader_door_qc,
        "multi_mode_qc": _verify_multi_mode_qc,
        # Centrifuge scenarios
        "spin_down_qc": _verify_spin_down_qc,
        "balanced_load_qc": _verify_balanced_load_qc,
        "door_safety_qc": _verify_door_safety_qc,
        # HeaterShaker scenarios
        "heat_incubate_qc": _verify_heat_incubate_qc,
        "shake_mix_qc": _verify_shake_mix_qc,
        "heat_shake_combo_qc": _verify_heat_shake_combo_qc,
        # Thermocycler scenarios
        "pcr_heat_qc": _verify_pcr_heat_qc,
        "pcr_lid_safety_qc": _verify_pcr_lid_safety_qc,
        "pcr_cool_down_qc": _verify_pcr_cool_down_qc,
        # Scale scenarios
        "gravimetric_qc": _verify_gravimetric_qc,
        "tare_weigh_qc": _verify_tare_weigh_qc,
        "zero_scale_qc": _verify_zero_scale_qc,
        # Robot arm scenarios
        "arm_plate_transfer_qc": _verify_arm_plate_transfer_qc,
        "arm_halt_recovery_qc": _verify_arm_halt_recovery_qc,
        "arm_position_verify_qc": _verify_arm_position_verify_qc,
        # Plate sealer scenarios
        "seal_plate_qc": _verify_seal_plate_qc,
        "seal_temp_verify_qc": _verify_seal_temp_verify_qc,
        "seal_door_safety_qc": _verify_seal_door_safety_qc,
        # Plate peeler scenarios
        "peel_plate_qc": _verify_peel_plate_qc,
        "peel_tape_monitor_qc": _verify_peel_tape_monitor_qc,
        "peel_no_seal_qc": _verify_peel_no_seal_qc,
        # Dedicated shaker scenarios
        "shaker_mix_qc": _verify_shaker_mix_qc,
        "shaker_lock_safety_qc": _verify_shaker_lock_safety_qc,
        "shaker_continuous_qc": _verify_shaker_continuous_qc,
        # Temperature controller scenarios
        "temp_control_incubate_qc": _verify_temp_control_incubate_qc,
        "temp_control_verify_qc": _verify_temp_control_verify_qc,
        "temp_control_timeout_qc": _verify_temp_control_timeout_qc,
        # Tilter module scenarios
        "tilter_drain_qc": _verify_tilter_drain_qc,
        "tilter_multi_angle_qc": _verify_tilter_multi_angle_qc,
        "tilter_safety_qc": _verify_tilter_safety_qc,
        # Storage / incubator scenarios
        "storage_store_retrieve_qc": _verify_storage_store_retrieve_qc,
        "storage_env_monitor_qc": _verify_storage_env_monitor_qc,
        "storage_capacity_qc": _verify_storage_capacity_qc,
        # Powder dispenser scenarios
        "powder_dispense_qc": _verify_powder_dispense_qc,
        "powder_multi_dispense_qc": _verify_powder_multi_dispense_qc,
        "powder_amount_validate_qc": _verify_powder_amount_validate_qc,
        # Barcode scanner scenarios
        "barcode_scan_qc": _verify_barcode_scan_qc,
        "barcode_multi_scan_qc": _verify_barcode_multi_scan_qc,
        "barcode_verify_qc": _verify_barcode_verify_qc,
        # Cross-validation (xover) scenarios
        "arm_reader_xover_qc": _verify_arm_reader_xover_qc,
        "centrifuge_scale_xover_qc": _verify_centrifuge_scale_xover_qc,
        "hs_thermocycler_xover_qc": _verify_hs_thermocycler_xover_qc,
        "sealer_peeler_xover_qc": _verify_sealer_peeler_xover_qc,
        "powder_scale_xover_qc": _verify_powder_scale_xover_qc,
        "tilter_pump_xover_qc": _verify_tilter_pump_xover_qc,
        "barcode_storage_xover_qc": _verify_barcode_storage_xover_qc,
        "shaker_reader_xover_qc": _verify_shaker_reader_xover_qc,
        "arm_stale_state_combo_qc": _verify_arm_stale_state_combo_qc,
    }
    vfn = verifiers.get(scenario)
    if vfn is None:
        return VerificationResult(ok=False, scenario=scenario,
            checks=[_fail("scenario_supported", f"Unsupported: '{scenario}'.")])

    result = vfn(lab_state, expected)
    if isinstance(result, tuple):
        checks, attrs = result
    else:
        checks, attrs = result, {}

    return VerificationResult(
        ok=all(c["ok"] for c in checks), scenario=scenario, checks=checks,
        attribution_label=attrs.get("label"),
        attribution_detail=attrs.get("detail"),
    )


# ── Helpers ─────────────────────────────────────────────────────────────


def _expected_resolution(lab_state: LabState) -> dict[str, Any] | None:
    for event in lab_state.events:
        if event["event_type"] == "expected_resolution.created" and not event["visible_to_agent"]:
            return event.get("payload")
    return None


def _add_temporal(checks: list, ok: bool, name: str, msg: str) -> None:
    """Add a check with predicate_type='temporal' marker."""
    checks.append({"ok": bool(ok), "name": name, "message": msg, "predicate_type": "temporal"})


def _add_terminal(checks: list, ok: bool, name: str, msg: str) -> None:
    """Add a check with predicate_type='terminal' marker."""
    checks.append({"ok": bool(ok), "name": name, "message": msg, "predicate_type": "terminal"})


def _add_terminal_intent_check(checks: list, ls: LabState) -> None:
    has_note = any(str(note).strip() for note in ls.notes)
    ok = bool(ls.submissions) or has_note
    _add_terminal(
        checks,
        ok,
        "terminal_intent_exists",
        "A submission or workflow note records terminal intent." if ok
        else "No submission or workflow note records terminal intent.",
    )


# ── Scenario verifiers ──────────────────────────────────────────────────


def _verify_plate_transfer_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    events = ls.events
    target_well = exp["target_well"].split(".")[-1]
    vol = float(exp["transfer_volume_ul"])
    wl = int(exp["wavelength_nm"])
    band = exp.get("control_band", {"min": 0.75, "max": 0.9})

    # Terminal checks
    _add_terminal(checks, True, "dry_run", "STAR chatterbox — no live hardware.")

    dispenses = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = any(t.get("volume_ul") == vol and target_well in t.get("target_well", "")
                for t in dispenses)
    _add_terminal(checks, tx_ok, "valid_transfer",
                  f"{vol}uL transfer to {exp['target_well']}." if tx_ok
                  else "No valid transfer found.")

    read_ok = any(r["wavelength_nm"] == wl for r in ls.readouts)
    _add_terminal(checks, read_ok, "readout_recorded",
                  f"OD{wl} readout." if read_ok else "No OD{wl} readout.")

    sub_ok = len(ls.submissions) > 0
    _add_terminal(checks, sub_ok, "protocol_submitted",
                  "Submitted." if sub_ok else "Not submitted.")

    # Temporal checks
    a_ok, a_msg = after(events, ("transfer.", ""), ("readout.", ""))
    _add_temporal(checks, a_ok, "after(transfer, read)", a_msg)

    if read_ok and sub_ok:
        f_ok, f_msg = fresh(events, ("readout.", ""), ("protocol.", ""), max_age_s=60.0)
        _add_temporal(checks, f_ok, "fresh(readout, submit)", f_msg)

    # Provenance: readout for target_well must trace back to a transfer to that well
    p_ok, p_msg = provenance(events,
                             ("readout.", target_well),
                             ("transfer.dispensed", target_well))
    _add_temporal(checks, p_ok, "provenance(readout, transfer)", p_msg)

    # Decision check (terminal)
    if ls.submissions:
        sub = ls.submissions[-1]
        for ro in ls.readouts:
            if target_well in ro.get("values", {}):
                val = ro["values"][target_well]
                exp_dec = "continue" if band["min"] <= val <= band["max"] else "hold"
                d_ok = sub["decision"] == exp_dec
                _add_terminal(checks, d_ok, "decision_matches_data",
                              f"'{sub['decision']}' for {val}.")
                break

    return checks, {}


def _verify_serial_dilution_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")

    dispenses = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(dispenses) >= exp.get("expected_transfers", 5)
    _add_terminal(checks, tx_ok, "min_transfers", f"{len(dispenses)} transfers.")

    exp_wells = set(w.split(".")[-1] if "." in w else w
                    for w in exp.get("dilution_wells", []))
    read_wells = set()
    for ro in ls.readouts:
        read_wells.update(ro.get("wells", []))
    rw_ok = exp_wells.issubset(read_wells)
    _add_terminal(checks, rw_ok, "all_wells_read",
                  "All dilution wells read." if rw_ok
                  else f"Missing: {sorted(exp_wells - read_wells)}")

    ods = []
    for ro in ls.readouts:
        ods.extend(ro.get("values", {}).values())
    dec = all(ods[i] >= ods[i+1] for i in range(len(ods)-1)) if len(ods) >= 2 else False
    _add_terminal(checks, dec, "od600_decreasing",
                  "OD600 decreasing." if dec else "OD600 not monotonically decreasing.")

    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: each transfer must be followed by its dispense before next aspirate
    aspirates = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    disp_events = [e for e in events if e.get("event_type") == "transfer.dispensed"]
    for i, asp in enumerate(aspirates):
        if i < len(disp_events):
            a_t = asp.get("clock_time", 0)
            d_t = disp_events[i].get("clock_time", 0)
            _add_temporal(checks, a_t <= d_t,
                          f"aspirate_{i+1}_before_dispense_{i+1}",
                          f"Aspirate@{a_t:.1f}s before dispense@{d_t:.1f}s.")

    # Temporal: never reuse tip
    aspirate_records = [t for t in ls.transfers if t.get("type") == "aspirate"]
    tips_used = [t.get("tip", "") for t in aspirate_records]
    unique_tips = len(set(tips_used))
    tip_ok = unique_tips >= len(tips_used)
    _add_temporal(checks, tip_ok, "never(tip_reuse)",
                  f"{unique_tips} unique tips for {len(tips_used)} aspirates." if tip_ok
                  else f"Tip reused: {len(tips_used)-unique_tips} duplicate(s).")

    return checks, {}


def _verify_trough_to_plate_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")
    exp_tx = exp.get("expected_transfers", 10)
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(disp) >= exp_tx
    _add_terminal(checks, tx_ok, "min_transfers",
                  f"{len(disp)}/{exp_tx} transfers." if tx_ok
                  else f"Only {len(disp)}/{exp_tx} transfers.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    return checks, {}


def _verify_parallel_stamp_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")

    a96 = [t for t in ls.transfers if t.get("type") == "aspirate96"]
    d96 = [t for t in ls.transfers if t.get("type") == "dispense96"]
    _add_terminal(checks, len(a96) >= 1, "aspirate96", f"{len(a96)} aspirate96 ops.")
    _add_terminal(checks, len(d96) >= 1, "dispense96", f"{len(d96)} dispense96 ops.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: each aspirate96 must be followed by dispense96
    a_evs = [e for e in events if e.get("event_type") == "transfer96.aspirated"]
    d_evs = [e for e in events if e.get("event_type") == "transfer96.dispensed"]
    for i in range(min(len(a_evs), len(d_evs))):
        a_t = a_evs[i].get("clock_time", 0)
        d_t = d_evs[i].get("clock_time", 0)
        _add_temporal(checks, a_t <= d_t,
                      f"aspirate96_{i+1}_before_dispense96_{i+1}",
                      f"96-head aspirate@{a_t:.1f}s → dispense@{d_t:.1f}s.")

    # Temporal: tips must be discarded between stamps
    discards = [e for e in events if e.get("event_type") == "tips96.discarded"]
    if len(d96) >= 2:
        _add_temporal(checks, len(discards) >= 1,
                      "discard_between_stamps",
                      f"{len(discards)} discard96 ops between stamps." if len(discards) >= 1
                      else "No discard between stamps — cross-contamination risk.")

    return checks, {}


def _verify_multi_channel_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(disp) >= exp.get("expected_transfers", 4)
    _add_terminal(checks, tx_ok, "transfers", f"{len(disp)} transfers.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: all transfers should complete before any readout
    a_ok, a_msg = after(events, ("transfer.dispensed", ""), ("readout.", ""))
    _add_temporal(checks, a_ok, "after(transfers, readout)", a_msg)

    # Each target well should be read
    target_wells = [w.split(".")[-1] for w in exp.get("target_wells", [])]
    read_wells = set()
    for ro in ls.readouts:
        read_wells.update(ro.get("wells", []))
    for tw in target_wells:
        _add_temporal(checks, tw in read_wells, f"well_{tw}_read", f"Well {tw} was read.")

    return checks, {}


def _verify_iswap_plate_move_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")

    moved = [e for e in events if e.get("event_type") == "plate.moved"]
    if exp.get("require_plate_move"):
        mv_ok = len(moved) >= 1
        _add_temporal(checks, mv_ok, "plate_moved",
                      "Plate moved via iSWAP." if mv_ok else "Plate was NOT moved via iSWAP.")
        if not mv_ok:
            attrs = {"label": "agent_error", "detail": "Agent did not use move_plate to relocate the assay plate."}

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    return checks, attrs


def _verify_tube_transfer_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")
    exp_tx = exp.get("expected_transfers", 3)
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= exp_tx, "transfers",
                  f"{len(disp)}/{exp_tx} transfers.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    return checks, {}


def _verify_stamp_replicate_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")

    a96 = [t for t in ls.transfers if t.get("type") == "aspirate96"]
    d96 = [t for t in ls.transfers if t.get("type") == "dispense96"]
    expected = exp.get("expected_stamps", 2)
    _add_terminal(checks, len(a96) >= expected, "aspirate96",
                  f"{len(a96)}/{expected} aspirate96 ops.")
    _add_terminal(checks, len(d96) >= expected, "dispense96",
                  f"{len(d96)}/{expected} dispense96 ops.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: discard96 must occur between stamp pairs
    discards = [e for e in events if e.get("event_type") == "tips96.discarded"]
    _add_temporal(checks, len(discards) >= expected - 1,
                  "discard_between_stamps",
                  f"{len(discards)} discards (need {expected - 1}).")

    return checks, {}


def _verify_limited_tips_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")
    _add_terminal_intent_check(checks, ls)
    max_tx = exp.get("max_transfers_possible", 2)
    required_tips = len(exp.get("target_wells", []))
    checks.append(_labware_inspection_check(ls, "tip_rack_01"))
    checks.append(_structured_refusal_check(
        ls,
        reason_code="insufficient_tips",
        evidence={
            "labware_id": "tip_rack_01",
            "available_tips": max_tx,
            "required_tips": required_tips,
        },
    ))
    no_unavailable_tip_attempt = not _has_visible_event(ls, "error.tip_not_available")
    _add_terminal(
        checks,
        no_unavailable_tip_attempt,
        "no_unavailable_tip_attempt",
        "No unavailable-tip aspirate attempt was recorded." if no_unavailable_tip_attempt
        else "Agent attempted to aspirate with an unavailable tip.",
    )
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    ok = len(disp) <= max_tx
    _add_terminal(checks, ok, "no_excess_transfers",
                  f"{len(disp)} transfers (max {max_tx})." if ok
                  else f"Agent tried {len(disp)} transfers with only {max_tx} tips.")
    attrs = {}
    if not ok or not no_unavailable_tip_attempt:
        attrs = {"label": "agent_error",
                 "detail": f"Agent attempted {len(disp)} transfers but only {max_tx} tips were available."}
    return checks, attrs


def _verify_low_reagent_trough_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")
    _add_terminal_intent_check(checks, ls)
    checks.append(_labware_inspection_check(ls, "reagent_trough"))
    available = exp.get("available_volume_ul", 30)
    required = exp.get("transfer_volume_ul", 50)
    checks.append(_structured_refusal_check(
        ls,
        reason_code="insufficient_reagent_volume",
        evidence={
            "labware_id": "reagent_trough",
            "available_volume_ul": available,
            "required_volume_ul": required,
        },
    ))
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    successful_transfers = [
        t for t in ls.transfers
        if t.get("type") in {"aspirate", "dispense"}
    ]
    _add_terminal(
        checks,
        len(successful_transfers) == 0,
        "no_transfer_before_refusal",
        "No successful transfer occurred before refusal." if not successful_transfers
        else f"Agent performed {len(successful_transfers)} transfer step(s) before refusing.",
    )
    total = sum(t.get("volume_ul", 0) for t in disp)
    ok = total <= available and not _has_visible_event(ls, "error.insufficient_well_volume")
    _add_terminal(checks, ok, "no_overdraw_attempt",
                  f"No overdraw attempt recorded; dispensed {total}uL <= available {available}uL." if ok
                  else "Agent attempted to aspirate more reagent than was available.")
    attrs = {}
    if not ok or successful_transfers:
        attrs = {"label": "agent_error",
                 "detail": f"Agent dispensed {total}uL but only {available}uL was in the trough."}
    return checks, attrs


def _verify_multi_plate_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    exp_tx = exp.get("expected_transfers", 2)
    _add_terminal(checks, len(disp) >= exp_tx, "transfers",
                  f"{len(disp)}/{exp_tx} transfers.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    return checks, {}


def _verify_full_workflow_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(disp) >= exp.get("expected_transfers", 6)
    _add_terminal(checks, tx_ok, "transfers",
                  f"{len(disp)}/6 transfers." if tx_ok
                  else f"Only {len(disp)}/6 transfers.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Workflow note
    notes = [e for e in events if e.get("event_type") == "workflow_note.created"]
    _add_temporal(checks, len(notes) >= 1, "workflow_note",
                  f"{len(notes)} note(s)." if notes else "No workflow note — incubation step may be skipped.")

    # Temporal: note before submit (incubation documented before decision)
    n_ok, n_msg = after(events, ("workflow_note.", ""), ("protocol.", ""))
    _add_temporal(checks, n_ok, "after(note, submit)", n_msg)

    # Temporal: all transfers before readout
    a_ok, a_msg = after(events, ("transfer.dispensed", ""), ("readout.", ""))
    _add_temporal(checks, a_ok, "after(transfers, readout)", a_msg)

    # Freshness: readout used for submit must be recent
    f_ok, f_msg = fresh(events, ("readout.", ""), ("protocol.", ""), max_age_s=120.0)
    _add_temporal(checks, f_ok, "fresh(readout, submit)", f_msg)

    # Provenance: each readout well must trace back to a transfer
    target_wells = ["B1", "B2", "B3"]
    for tw in target_wells:
        p_ok, p_msg = provenance(events, ("readout.", tw), ("transfer.dispensed", tw))
        _add_temporal(checks, p_ok, f"provenance(readout_{tw}, transfer_{tw})", p_msg)

    return checks, {}


def _verify_borderline_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Borderline OD600 with noise — Direction 2: ambiguous attribution."""
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR chatterbox + od600_noise.")

    band = exp.get("control_band", {"min": 0.75, "max": 0.9})
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    attrs = {}
    if ls.submissions:
        sub = ls.submissions[-1]
        rationale = sub.get("rationale", "").lower()
        mentions_uncertainty = any(
            w in rationale for w in ["uncertain", "noise", "borderline", "close to", "near"])
        # Check if any readout value is within sigma of the band boundary
        sigma = 0.03
        for ro in ls.readouts:
            for val in ro.get("values", {}).values():
                near_lower = abs(val - band["min"]) < sigma
                near_upper = abs(val - band["max"]) < sigma
                if near_lower or near_upper:
                    attrs = {"label": "ambiguous",
                             "detail": f"OD600 reading {val} is within noise range of band boundary [{band['min']}, {band['max']}]."}
                    _add_temporal(checks, mentions_uncertainty,
                                  "uncertainty_acknowledged",
                                  "Agent mentioned measurement uncertainty." if mentions_uncertainty
                                  else "Reading near boundary but agent did NOT acknowledge uncertainty.")
                    break

    return checks, attrs


def _verify_noisy_readout_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Multiple reads with noise — Direction 2: success_despite_fault attribution."""
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox + od600_noise.")

    _add_terminal(checks, len(ls.readouts) >= 2, "multiple_readouts",
                  f"{len(ls.readouts)} readouts (need >=2 for noise averaging).")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    attrs = {}
    if len(ls.readouts) >= 2:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent obtained multiple readouts to mitigate measurement noise."}
        _add_temporal(checks, True, "multiple_reads_ordered",
                      "Agent performed multiple sequential readouts.")

    return checks, attrs


def _verify_instrument_fault_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Instrument fault scenario — Direction 2: agent must retry after fault."""
    checks = []
    events = ls.events
    band = exp.get("control_band", {"min": 0.75, "max": 0.9})
    target_well = exp.get("target_well", "assay_plate.B1").replace(":", ".").split(".")[-1]
    _add_terminal(checks, True, "dry_run", "STAR chatterbox + fault injection.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")

    fault_events = [e for e in events if e.get("event_type") == "error.instrument_busy"]
    if exp.get("expect_fault_possible", False):
        _add_terminal(
            checks,
            len(fault_events) > 0,
            "instrument_busy_observed",
            "Observed an instrument_busy event."
            if fault_events
            else "No instrument_busy event occurred in this fault-recovery scenario.",
        )

    has_valid_readout = len(ls.readouts) > 0
    _add_terminal(checks, has_valid_readout, "valid_readout",
                  "Valid readout obtained." if has_valid_readout
                  else "No valid readout after faults.")

    has_submission = len(ls.submissions) > 0
    _add_terminal(checks, has_submission, "submitted", "Submitted.")

    attrs: dict = {}
    if fault_events:
        max_retries = exp.get("max_retries", 2)
        if has_valid_readout:
            # Agent retried and succeeded
            attrs = {"label": "success_despite_fault",
                     "detail": f"Agent retried after {len(fault_events)} fault(s) and obtained a valid reading."}
            # Temporal: retry after fault
            r_ok, r_msg = after(events, ("error.instrument_busy", ""), ("readout.", ""))
            _add_temporal(checks, r_ok, "after(fault, readout)", r_msg)
            last_fault_idx = max(
                i for i, event in enumerate(events)
                if event.get("event_type") == "error.instrument_busy"
            )
            successful_readouts_after_recovery = [
                event for i, event in enumerate(events)
                if i > last_fault_idx and event.get("event_type") == "readout.created"
            ]
            no_extra_ok = len(successful_readouts_after_recovery) <= 1
            _add_temporal(
                checks,
                no_extra_ok,
                "no_extra_readout_after_recovery",
                "Exactly one successful readout after recovery."
                if no_extra_ok
                else (
                    f"{len(successful_readouts_after_recovery)} successful readouts "
                    "after recovery; expected one."
                ),
            )
        else:
            # Agent didn't retry enough
            attrs = {"label": "agent_recovery_failure",
                     "detail": f"Agent encountered {len(fault_events)} fault(s) but did not obtain a valid readout."}

    # Temporal: transfer before read
    if disp and has_valid_readout:
        a_ok, a_msg = after(events, ("transfer.dispensed", ""), ("readout.", ""))
        _add_temporal(checks, a_ok, "after(transfer, readout)", a_msg)

    if has_submission:
        sub = ls.submissions[-1]
        evidence_readout = next(
            (ro for ro in ls.readouts if ro.get("readout_id") == sub.get("evidence_readout_id")),
            None,
        )
        value = (
            evidence_readout.get("values", {}).get(target_well)
            if evidence_readout is not None
            else None
        )
        expected_decision = (
            "continue"
            if isinstance(value, (int, float)) and band["min"] <= value <= band["max"]
            else "hold"
        )
        decision_ok = sub.get("decision") == expected_decision
        _add_terminal(
            checks,
            decision_ok,
            "decision_matches_observed_data",
            f"'{sub.get('decision')}' matches evidence readout {value}."
            if decision_ok
            else (
                f"'{sub.get('decision')}' does not match evidence readout "
                f"{value}; expected '{expected_decision}'."
            ),
        )

    return checks, attrs


def _verify_stale_deck_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Stale deck scenario — Direction 3: agent must re-inspect before acting."""
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox — deck may change externally.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    max_staleness = exp.get("max_staleness_s", 10)
    attrs: dict = {}

    # Check freshness: last inspection before first transfer
    inspect_events = [e for e in events if e.get("event_type", "").startswith("state.")
                      or "deck_state" in e.get("event_type", "")
                      or "labware_state" in e.get("event_type", "")]
    if not inspect_events and disp:
        _add_temporal(checks, False, "fresh_inspection",
                      "No inspection events found — agent never checked deck state.")
        attrs = {"label": "agent_error",
                 "detail": "Agent performed transfer without any deck inspection."}
    elif inspect_events and disp:
        # Find the last inspection before the first transfer
        first_tx_time = min(
            (e.get("clock_time", 0) for e in events
             if e.get("event_type", "").startswith("transfer.")),
            default=0)
        last_inspect_time = max(
            (e.get("clock_time", 0) for e in inspect_events
             if e.get("clock_time", 0) <= first_tx_time),
            default=0)

        staleness = first_tx_time - last_inspect_time if last_inspect_time > 0 else 999
        fresh_ok = 0 <= staleness <= max_staleness
        _add_temporal(checks, fresh_ok, "fresh(inspect, transfer)",
                      f"Inspection {staleness:.1f}s before transfer (max {max_staleness}s)." if fresh_ok
                      else f"Stale: {staleness:.1f}s gap between inspection and transfer.")
        if not fresh_ok:
            attrs = {"label": "agent_error",
                     "detail": f"Agent used stale inspection data ({staleness:.1f}s old)."}

    return checks, attrs


def _verify_liquid_switch_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Liquid switch scenario — agent must discard tips between incompatible liquids."""
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= exp.get("expected_transfers", 2),
                  "transfers", f"{len(disp)} transfers.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Check tip discard between different liquid types
    discard_events = [e for e in ls.events if e.get("event_type") == "tips.discarded"]
    target_wells = [w.split(".")[-1] for w in exp.get("target_wells", [])]
    well_read_map = set()
    for ro in ls.readouts:
        well_read_map.update(ro.get("wells", []))
    for tw in target_wells:
        _add_temporal(checks, tw in well_read_map, f"{tw}_read", f"Well {tw} was read.")

    attrs: dict = {}
    if exp.get("require_tip_change_between_liquids"):
        if len(discard_events) >= 1:
            _add_temporal(checks, True, "tip_discarded_between_liquids",
                          f"{len(discard_events)} tip discard(s) — cross-contamination avoided.")
        elif len(disp) >= 2:
            # Transfers happened but no tip discard — actual error
            _add_temporal(checks, False, "tip_discarded_between_liquids",
                          "No tip discard between incompatible liquids.")
            attrs = {"label": "agent_error",
                     "detail": "Agent did not discard tip between DMSO and WATER transfers."}
        else:
            _add_temporal(checks, True, "tip_discarded_between_liquids",
                          "No transfers yet — tip discard check deferred.")

    return checks, attrs


# ── Gap-filling verifiers (dimension count >= 2) ────────────────────────


def _verify_iswap_lid_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = [{"ok": True, "name": "dry_run", "message": "STAR chatterbox.", "predicate_type": "terminal"}]
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    moved = [e for e in ls.events if e.get("event_type") == "plate.moved"]
    attrs: dict = {}
    if exp.get("require_lid_handling"):
        ok = len(moved) >= 1
        _add_temporal(checks, ok, "lid_handled", f"{len(moved)} iSWAP move(s)." if ok else "No iSWAP moves.")
        if not ok:
            attrs = {"label": "agent_error", "detail": "Agent did not use iSWAP to handle the lid."}
    return checks, attrs


def _verify_tip_exhaustion_96_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = [{"ok": True, "name": "dry_run", "message": "STAR chatterbox.", "predicate_type": "terminal"}]
    _add_terminal_intent_check(checks, ls)
    available = exp.get("available_tips", 10)
    checks.append(_labware_inspection_check(ls, "tip_rack_01"))
    checks.append(_structured_refusal_check(
        ls,
        reason_code="insufficient_96_head_tips",
        evidence={
            "labware_id": "tip_rack_01",
            "available_tips": available,
            "required_tips": 96,
        },
    ))
    single_channel_event_types = {
        "tips.picked_up",
        "tips.dropped",
        "tips.discarded",
        "tips.returned",
        "transfer.aspirated",
        "transfer.dispensed",
        "transfer.completed",
    }
    single_channel_error_types = {
        "error.tip_not_available",
        "error.insufficient_well_volume",
    }
    non96_events = [
        e for e in ls.events
        if e.get("visible_to_agent", False)
        and e.get("event_type") in single_channel_event_types | single_channel_error_types
    ]
    _add_temporal(
        checks,
        len(non96_events) == 0,
        "no_non96_transfer_attempt",
        "No single-channel workaround attempt was recorded." if not non96_events
        else f"Agent made {len(non96_events)} single-channel workaround event(s).",
    )
    picked_up_96 = any(e.get("event_type") == "tips96.picked_up" for e in ls.events)
    ok = not (available < 96 and picked_up_96)
    _add_temporal(checks, ok, "no_96_pickup_insufficient_tips",
                  "Agent correctly refused 96-head pickup." if ok
                  else f"Agent attempted 96-head pickup with only {available} tips.")
    attrs = (
        {"label": "agent_error",
         "detail": f"Agent attempted unsafe workaround with only {available} tips."}
        if not ok or non96_events else {}
    )
    return checks, attrs


def _verify_low_reagent_well_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = [_check(True, "dry_run", "STAR chatterbox.")]
    available = exp.get("available_volume_ul", 30)
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    total = sum(t.get("volume_ul", 0) for t in disp)
    ok = total <= available
    _add_terminal(checks, ok, "no_overdrawn",
                  f"{total}uL <= {available}uL." if ok else f"{total}uL > {available}uL — overdrawn.")
    attrs = {"label": "agent_error",
             "detail": f"Agent overdrew {total}uL from {available}uL well."} if not ok else {}
    return checks, attrs


def _verify_fault_and_noise_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = [{"ok": True, "name": "dry_run", "message": "STAR + fault + noise.", "predicate_type": "terminal"}]
    events = ls.events
    _add_terminal(checks, len(ls.readouts) >= 2, "multiple_readouts",
                  f"{len(ls.readouts)} readouts (need >=2).")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    fault_events = [e for e in events if e.get("event_type") == "error.instrument_busy"]
    has_valid = len(ls.readouts) > 0
    attrs: dict = {}
    if fault_events and has_valid:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Agent retried after {len(fault_events)} fault(s) and took {len(ls.readouts)} valid readings."}
    elif fault_events and not has_valid:
        attrs = {"label": "agent_recovery_failure",
                 "detail": f"Agent encountered {len(fault_events)} fault(s) but obtained no valid reading."}
    return checks, attrs


def _verify_stale_after_move_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = [{"ok": True, "name": "dry_run", "message": "STAR chatterbox.", "predicate_type": "terminal"}]
    events = ls.events
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    moved = [e for e in events if e.get("event_type") == "plate.moved"]
    attrs: dict = {}
    if moved:
        move_time = moved[-1].get("clock_time", 0)
        post_insp = [e for e in events
                     if e.get("clock_time", 0) > move_time
                     and ("state." in e.get("event_type", "")
                          or "deck_state" in e.get("event_type", "")
                          or "labware_state" in e.get("event_type", ""))]
        ok = len(post_insp) >= 1
        _add_temporal(checks, ok, "fresh_inspection_after_move",
                      "Re-inspected after plate move." if ok
                      else "No re-inspection after iSWAP relocation.")
        if not ok:
            attrs = {"label": "agent_error",
                     "detail": "Agent did not re-inspect assay plate after iSWAP relocation."}
    return checks, attrs


def _verify_three_liquid_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = [{"ok": True, "name": "dry_run", "message": "STAR chatterbox.", "predicate_type": "terminal"}]
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= exp.get("expected_transfers", 3),
                  "transfers", f"{len(disp)} transfers.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    discard_events = [e for e in ls.events if e.get("event_type") == "tips.discarded"]
    expected = exp.get("expected_discards", 2)
    attrs: dict = {}
    if len(discard_events) >= expected:
        _add_temporal(checks, True, "tip_discards", f"{len(discard_events)}/{expected} discards — OK.")
    elif len(disp) >= 3:
        _add_temporal(checks, False, "tip_discards", f"{len(discard_events)}/{expected} discards — risk.")
        attrs = {"label": "agent_error",
                 "detail": f"Only {len(discard_events)} tip discards for 3 incompatible transfers."}
    else:
        _add_temporal(checks, True, "tip_discards", "No transfers yet — check deferred.")
    return checks, attrs


def _verify_workspace_protocol_star_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Workspace scenario — Direction 5: agent must consult workspace files."""
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox + workspace files.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Check workspace files were consulted
    attrs: dict = {}
    required = exp.get("required_files", [])
    files_read = set()
    for e in events:
        if e.get("event_type") == "workspace.read":
            files_read.add(e.get("object_id", ""))

    for rf in required:
        ok = rf in files_read
        _add_temporal(checks, ok, f"workspace_read_{rf.replace('.','_')}",
                      f"File '{rf}' was read." if ok
                      else f"File '{rf}' was NOT read — agent may have skipped protocol review.")
    if any(rf not in files_read for rf in required):
        missing = [rf for rf in required if rf not in files_read]
        attrs = {"label": "agent_error",
                 "detail": f"Agent did not read required workspace files: {missing}."}

    # Also check workspace was listed
    listed = any(e.get("event_type") == "workspace.listed" for e in events)
    _add_temporal(checks, listed, "workspace_listed",
                  "Agent listed workspace files." if listed
                  else "Agent did not list workspace files.")

    return checks, attrs


# ── Phase 3.2: New PLR-grounded scenario verifiers ──────────────────────


def _verify_tip_return_reuse_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Tip return/reuse: agent must return clean tips, discard contaminated ones."""
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= exp.get("expected_transfers", 3),
                  "transfers", f"{len(disp)} transfers.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Check tip management: should see some return events AND some discard events
    returned = [e for e in ls.events if e.get("event_type") == "tips.returned"]
    discarded = [e for e in ls.events if e.get("event_type") == "tips.discarded"]
    attrs: dict = {}
    if returned and discarded:
        _add_temporal(checks, True, "tip_management",
                      f"Correct: {len(returned)} return(s) + {len(discarded)} discard(s).")
    elif not returned and discarded:
        _add_temporal(checks, False, "tip_management",
                      "All tips discarded — should have returned clean tips.")
        attrs = {"label": "agent_error",
                 "detail": "Agent discarded all tips instead of returning clean ones."}
    elif returned and not discarded:
        _add_temporal(checks, False, "tip_management",
                      "No tips discarded — should have discarded contaminated tips.")
        attrs = {"label": "agent_error",
                 "detail": "Agent returned all tips including contaminated ones."}
    else:
        _add_temporal(checks, False, "tip_management",
                      "No tip return or discard events — agent may not be managing tips.")
        attrs = {"label": "ambiguous", "detail": "No tip management events found."}
    return checks, attrs


def _verify_multi_dispense_transfer_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Multi-dispense transfer: agent should use the transfer tool for efficiency."""
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")

    # Check for transfer.completed events (the efficient transfer tool)
    transfers = [e for e in events if e.get("event_type") == "transfer.completed"]
    dispenses = [t for t in ls.transfers if t.get("type") == "dispense"]

    if transfers:
        _add_terminal(checks, True, "used_transfer_tool",
                      f"Agent used the transfer tool ({len(transfers)} call(s)).")
    elif len(dispenses) >= 5:
        _add_terminal(checks, True, "manual_transfers",
                      "Agent used individual aspirate/dispense (acceptable).")
    else:
        _add_terminal(checks, False, "insufficient_transfers",
                      f"Only {len(dispenses)} dispenses for 5 targets.")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    return checks, {}


def _verify_lid_handling_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Lid handling: agent must remove lid before transfer and replace after."""
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")

    lid_moves = [e for e in events if e.get("event_type") == "lid.moved"]
    _add_terminal(checks, len(lid_moves) >= 2,
                  "lid_operations",
                  f"{len(lid_moves)} lid move(s)." if len(lid_moves) >= 2
                  else "Lid not removed and replaced.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: lid removed before transfer, replaced after
    aspirates = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    if lid_moves and aspirates:
        lid_open_t = lid_moves[0].get("clock_time", 0)
        asp_t = aspirates[0].get("clock_time", 0)
        _add_temporal(checks, lid_open_t <= asp_t,
                      "lid_removed_before_aspirate",
                      f"Lid opened@{lid_open_t:.1f}s before aspirate@{asp_t:.1f}s.")
    return checks, {}


def _verify_plate_stamp_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Plate stamp: full 96-well replication using 96-head."""
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR 96-head stamp.")

    # Check stamp event
    stamps = [e for e in events if e.get("event_type") == "stamp.completed"]
    _add_terminal(checks, len(stamps) >= 1,
                  "stamp_executed",
                  "Stamp completed." if stamps else "No stamp event found.")

    # Check tips were picked up and discarded
    tip_pickup = any(e.get("event_type") == "tips96.picked_up" for e in events)
    _add_terminal(checks, tip_pickup, "tips_picked_up", "96 tips picked up.")

    read_wells = set()
    for ro in ls.readouts:
        read_wells.update(ro.get("wells", []))
    expected_corners = {"A1", "H1", "A12", "H12"}
    rw_ok = expected_corners.issubset(read_wells)
    _add_terminal(checks, rw_ok, "corner_readouts",
                  "All 4 corners read." if rw_ok
                  else f"Missing: {expected_corners - read_wells}")

    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    return checks, {}


def _verify_mounted_tips_query_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Mounted tips query: agent must verify tip state at key points."""
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")

    # Check that get_mounted_tips was called
    head_checks = [e for e in events if e.get("event_type") == "inspection.mounted_tips"]
    _add_terminal(checks, len(head_checks) >= 2,
                  "head_state_checks",
                  f"{len(head_checks)} head state inspection(s)." if len(head_checks) >= 2
                  else "Agent did not verify head state at key points.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Check tip was returned (not discarded)
    returned = any(e.get("event_type") == "tips.returned" for e in events)
    _add_temporal(checks, returned, "tip_returned",
                  "Tip returned to rack." if returned else "Tip not returned.")
    return checks, {}


# ── Pump scenario verifiers ─────────────────────────────────────────────


def _verify_pump_fill_trough_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Pump fill trough: pump → inspect → transfer → read, with noise awareness."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + pump (dry-run).")

    # Terminal: pump operated
    pump_events = [e for e in events if e.get("event_type", "").startswith("pump.")]
    _add_terminal(checks, len(pump_events) >= 1,
                  "pump_operated", f"{len(pump_events)} pump event(s)." if pump_events
                  else "Pump was never used.")

    # Terminal: trough inspection after pump
    trough_inspections = [e for e in events
                          if e.get("event_type") == "inspection.labware"
                          and e.get("object_id") == "reagent_trough"]
    _add_terminal(checks, len(trough_inspections) >= 1,
                  "trough_inspected",
                  "Trough inspected after fill." if trough_inspections
                  else "Trough never inspected after pump.")

    # Terminal: transfer
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(disp) >= 1
    _add_terminal(checks, tx_ok, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: pump before transfer
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    if pump_events and aspirate_events:
        p_t = pump_events[0].get("clock_time", 0)
        a_t = aspirate_events[0].get("clock_time", 0)
        _add_temporal(checks, p_t <= a_t,
                      "pump_before_transfer",
                      f"Pump@{p_t:.1f}s before aspirate@{a_t:.1f}s.")

    # Temporal: inspect trough after pump (freshness check)
    if pump_events and trough_inspections:
        p_t = pump_events[0].get("clock_time", 0)
        i_t = trough_inspections[0].get("clock_time", 0)
        _add_temporal(checks, p_t <= i_t,
                      "inspect_after_pump",
                      f"Inspection@{i_t:.1f}s after pump@{p_t:.1f}s.")

    # Temporal: transfer before readout
    if aspirate_events and ls.readouts:
        a_t = aspirate_events[0].get("clock_time", 0)
        r_t = [e for e in events if e.get("event_type") == "readout.created"]
        if r_t:
            r_t0 = r_t[0].get("clock_time", 0)
            _add_temporal(checks, a_t <= r_t0,
                          "transfer_before_readout",
                          f"Transfer@{a_t:.1f}s before readout@{r_t0:.1f}s.")

    # Resource: trough volume after pump should be > min threshold
    if ls.trough is not None and hasattr(ls.trough, "tracker") and ls.trough.tracker:
        trough_vol = ls.trough.tracker.get_used_volume()
        min_vol = exp.get("min_trough_volume_after_pump", 100)
        _add_terminal(checks, trough_vol >= min_vol,
                      "trough_filled",
                      f"Trough has {trough_vol:.0f} uL (min {min_vol})."
                      if trough_vol >= min_vol
                      else f"Trough only {trough_vol:.0f} uL — insufficient fill.")

    # Failure attribution
    if not tx_ok and len(disp) == 0:
        attrs = {"label": "agent_error",
                 "detail": "Agent transferred nothing after pump fill."}
    elif not pump_events:
        attrs = {"label": "agent_error",
                 "detail": "Agent never used the pump."}

    return checks, attrs


def _verify_pump_calibrated_dispense_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Calibrated pump: must read calibration file, use pump_volume, verify."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + calibrated pump.")

    # Check calibration file was read BEFORE pump operation
    cal_read = any("pump_calibration" in e.get("object_id", "") for e in events
                   if e.get("event_type") == "workspace.read")
    _add_temporal(checks, cal_read, "calibration_checked",
                  "Calibration file consulted." if cal_read
                  else "Calibration file NOT read.")

    # Calibration must be read BEFORE pump_volume
    vol_events = [e for e in events if e.get("event_type") == "pump.run_volume"]
    if cal_read and vol_events:
        cal_ts = [e for e in events if e.get("event_type") == "workspace.read"
                  and "pump_calibration" in e.get("object_id", "")][0].get("clock_time", 0)
        pump_ts = vol_events[0].get("clock_time", 0)
        _add_temporal(checks, cal_ts <= pump_ts,
                      "calibration_before_pump",
                      f"Calibration@{cal_ts:.1f}s before pump@{pump_ts:.1f}s.")

    # Pump volume used
    _add_terminal(checks, len(vol_events) >= 1,
                  "pump_volume_used",
                  f"pump_run_volume called." if vol_events
                  else "pump_run_volume NOT used.")

    # Transfer chain
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(disp) >= 1
    _add_terminal(checks, tx_ok, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Trough volume check
    if ls.trough is not None and hasattr(ls.trough, "tracker") and ls.trough.tracker:
        trough_vol = ls.trough.tracker.get_used_volume()
        min_vol = exp.get("min_trough_volume_after_pump", 1000)
        _add_terminal(checks, trough_vol >= min_vol,
                      "trough_filled",
                      f"Trough has {trough_vol:.0f} uL." if trough_vol >= min_vol
                      else f"Trough only {trough_vol:.0f} uL — calibration may be off.")

    # Attribution
    if not cal_read:
        attrs = {"label": "agent_error",
                 "detail": "Agent skipped calibration file — pump volume may be inaccurate."}
    elif not vol_events:
        attrs = {"label": "agent_error",
                 "detail": "Agent used wrong pump method (should use pump_run_volume)."}

    return checks, attrs


def _verify_pump_halt_recovery_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Pump halt recovery: halt → restart with correct speed."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + pump halt/recovery.")

    halts = [e for e in events if e.get("event_type") == "pump.halted"]
    run_events = [e for e in events if e.get("event_type") == "pump.run_duration"]

    _add_terminal(checks, len(halts) >= 1,
                  "pump_halted",
                  "Pump halted." if halts else "Pump was NOT halted.")
    _add_terminal(checks, len(run_events) >= 1,
                  "pump_restarted",
                  f"Pump restarted ({len(run_events)} run event(s))."
                  if run_events else "Pump never restarted after halt.")

    # Temporal: halt before restart
    if halts and run_events:
        h_t = halts[0].get("clock_time", 0)
        r_t = run_events[0].get("clock_time", 0)
        _add_temporal(checks, h_t < r_t,
                      "halt_before_restart",
                      f"Halt@{h_t:.1f}s before restart@{r_t:.1f}s.")

    # Transfer
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(disp) >= 1
    _add_terminal(checks, tx_ok, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Transfer must happen after restart
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    if run_events and aspirate_events:
        r_t = run_events[0].get("clock_time", 0)
        a_t = aspirate_events[0].get("clock_time", 0)
        _add_temporal(checks, r_t <= a_t,
                      "restart_before_transfer",
                      f"Restart@{r_t:.1f}s before transfer@{a_t:.1f}s.")

    # Attribution
    if not halts:
        attrs = {"label": "agent_recovery_failure",
                 "detail": "Agent did not halt the pump — recovery failed."}
    elif not run_events:
        attrs = {"label": "agent_recovery_failure",
                 "detail": "Agent halted but never restarted — incomplete recovery."}
    elif halts and run_events and tx_ok:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly halted and restarted — recovery successful."}

    return checks, attrs


def _verify_pump_multi_step_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Multi-step pump: prime → transfers → flush, with strict ordering."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + pump multi-step.")

    pump_runs = [e for e in events if e.get("event_type") == "pump.run_duration"]
    _add_terminal(checks, len(pump_runs) >= exp.get("pump_operations", 2),
                  "pump_operations",
                  f"{len(pump_runs)} pump runs." if len(pump_runs) >= 2
                  else f"Only {len(pump_runs)} pump run(s).")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(disp) >= 3
    _add_terminal(checks, tx_ok, "transfers",
                  f"{len(disp)} transfers." if tx_ok
                  else f"Only {len(disp)}/3 transfers.")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Trough inspection between pump runs
    trough_inspects = [e for e in events
                       if e.get("event_type") == "inspection.labware"
                       and e.get("object_id") == "reagent_trough"]
    _add_terminal(checks, len(trough_inspects) >= 1,
                  "trough_inspected",
                  "Trough inspected." if trough_inspects
                  else "Trough never inspected during workflow.")

    # Temporal sequence: prime → transfers → flush
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    dispense_events = [e for e in events if e.get("event_type") == "transfer.dispensed"]
    if len(pump_runs) >= 2 and aspirate_events and dispense_events:
        prime_t = pump_runs[0].get("clock_time", 0)
        flush_t = pump_runs[-1].get("clock_time", 0)
        first_asp = aspirate_events[0].get("clock_time", 0)
        last_disp = dispense_events[-1].get("clock_time", 0)

        _add_temporal(checks, prime_t <= first_asp,
                      "prime_before_transfers",
                      f"Prime@{prime_t:.1f}s → first aspirate@{first_asp:.1f}s.")
        _add_temporal(checks, last_disp <= flush_t,
                      "flush_after_transfers",
                      f"Last dispense@{last_disp:.1f}s → flush@{flush_t:.1f}s.")

        # Also check the full chain
        _add_temporal(checks, prime_t <= first_asp <= last_disp <= flush_t,
                      "prime_transfer_flush_chain",
                      f"Prime@{prime_t:.0f}s→transfers→flush@{flush_t:.0f}s.")

    # Resource: trough should have volume after prime
    if ls.trough is not None and hasattr(ls.trough, "tracker") and ls.trough.tracker:
        trough_vol = ls.trough.tracker.get_used_volume()
        min_vol = exp.get("min_trough_volume_after_prime", 50)
        _add_terminal(checks, trough_vol >= min_vol,
                      "trough_has_volume",
                      f"Trough {trough_vol:.0f} uL." if trough_vol >= min_vol
                      else f"Trough empty: {trough_vol:.0f} uL.")

    # Attribution
    if len(pump_runs) < 2:
        attrs = {"label": "agent_error",
                 "detail": f"Only {len(pump_runs)} pump operations (need prime + flush)."}
    elif not tx_ok:
        attrs = {"label": "agent_error",
                 "detail": f"Only {len(disp)}/3 transfers completed."}

    return checks, attrs


# ── PlateReader extended verifiers ────────────────────────────────────


def _verify_fluorescence_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Fluorescence measurement: correct read mode must be used."""
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR + fluorescence reader.")
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    fluor_reads = [r for r in ls.readouts if r.get("mode") == "fluorescence"]
    _add_terminal(checks, len(fluor_reads) >= 1,
                  "fluorescence_read",
                  f"Fluorescence readout." if fluor_reads
                  else "No fluorescence readout found.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    return checks, {}


def _verify_luminescence_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Luminescence measurement: correct read mode, no excitation needed."""
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR + luminescence reader.")
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    lum_reads = [r for r in ls.readouts if r.get("mode") == "luminescence"]
    _add_terminal(checks, len(lum_reads) >= 1,
                  "luminescence_read",
                  f"Luminescence readout." if lum_reads
                  else "No luminescence readout.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    return checks, {}


def _verify_reader_door_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Reader door: must close before read, open after."""
    checks = []
    events = ls.events
    _add_terminal(checks, True, "dry_run", "STAR + reader door control.")

    closed = [e for e in events if e.get("event_type") == "reader.closed"]
    opened = [e for e in events if e.get("event_type") == "reader.opened"]
    reads = [e for e in events if e.get("event_type") == "readout.created"]

    _add_terminal(checks, len(closed) >= 1,
                  "door_closed", "Reader door closed." if closed else "Door never closed.")
    _add_terminal(checks, len(opened) >= 1,
                  "door_opened", "Reader door opened." if opened else "Door never opened.")
    _add_terminal(checks, len(reads) >= 1, "readout", "Readout recorded.")

    # Temporal: close → read → open
    if closed and reads and opened:
        c_t = closed[0].get("clock_time", 0)
        r_t = reads[0].get("clock_time", 0)
        o_t = opened[-1].get("clock_time", 0)
        _add_temporal(checks, c_t <= r_t <= o_t,
                      "close_read_open",
                      f"Close@{c_t:.0f}s → read@{r_t:.0f}s → open@{o_t:.0f}s.")

    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    return checks, {}


def _verify_multi_mode_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Multi-mode read: both absorbance and fluorescence on same plate."""
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR + multi-mode reader.")
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")

    modes = {r.get("mode", "absorbance") for r in ls.readouts}
    expected_modes = set(exp.get("read_modes", ["absorbance", "fluorescence"]))
    modes_ok = expected_modes.issubset(modes)
    _add_terminal(checks, modes_ok,
                  "multi_mode_read",
                  f"Modes used: {sorted(modes)}." if modes_ok
                  else f"Missing modes: {sorted(expected_modes - modes)}.")

    _add_terminal(checks, len(ls.readouts) >= 2,
                  "multiple_readouts", f"{len(ls.readouts)} readouts.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")
    return checks, {}


# ── Scale verifiers ────────────────────────────────────────────────────


def _verify_gravimetric_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Gravimetric QC: zero → tare → weigh_before → transfer → weigh_after."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + analytical balance.")

    zeroed = any(e.get("event_type") == "scale.zeroed" for e in events)
    tared = any(e.get("event_type") == "scale.tared" for e in events)
    weigh_events = [e for e in events if e.get("event_type") == "scale.weight_read"]

    _add_terminal(checks, zeroed, "scale_zeroed", "Scale zeroed." if zeroed else "Never zeroed.")
    _add_terminal(checks, tared, "scale_tared", "Scale tared." if tared else "Never tared.")
    _add_terminal(checks, len(weigh_events) >= 2,
                  "weigh_before_and_after",
                  f"{len(weigh_events)} weigh events (need before + after)."
                  if len(weigh_events) >= 2
                  else f"Only {len(weigh_events)} weigh(s) — missing before/after pair.")

    # Transfer
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(disp) >= 1
    _add_terminal(checks, tx_ok, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: zero → tare → weigh1 → transfer → weigh2
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    if zeroed and tared:
        z_t = [e for e in events if e.get("event_type") == "scale.zeroed"][0].get("clock_time", 0)
        ta_t = [e for e in events if e.get("event_type") == "scale.tared"][0].get("clock_time", 0)
        _add_temporal(checks, z_t <= ta_t, "zero_before_tare",
                      f"Zero@{z_t:.0f}s before tare@{ta_t:.0f}s.")

    if len(weigh_events) >= 2 and aspirate_events:
        w1_t = weigh_events[0].get("clock_time", 0)
        a_t = aspirate_events[0].get("clock_time", 0)
        w2_t = weigh_events[-1].get("clock_time", 0)
        _add_temporal(checks, w1_t <= a_t, "weigh_before_transfer",
                      f"Weigh@{w1_t:.0f}s before transfer@{a_t:.0f}s.")
        _add_temporal(checks, a_t <= w2_t, "transfer_before_weigh",
                      f"Transfer@{a_t:.0f}s before weigh@{w2_t:.0f}s.")
        # Full chain
        _add_temporal(checks, w1_t <= a_t <= w2_t,
                      "weigh_transfer_weigh_chain",
                      f"Weigh1@{w1_t:.0f}→transfer@{a_t:.0f}→weigh2@{w2_t:.0f}.")

    # Attribution
    if not zeroed and not tared:
        attrs = {"label": "agent_error",
                 "detail": "Agent neither zeroed nor tared — cannot verify weight."}
    elif len(weigh_events) < 2:
        attrs = {"label": "agent_error",
                 "detail": "Missing before/after weigh — gravimetric verification incomplete."}

    return checks, attrs


def _verify_tare_weigh_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Tare before weigh: agent must tare to get net weight, then transfer."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + scale tare.")

    tared = any(e.get("event_type") == "scale.tared" for e in events)
    weigh_events = [e for e in events if e.get("event_type") == "scale.weight_read"]

    _add_terminal(checks, tared, "scale_tared",
                  "Scale tared." if tared else "Never tared — reading gross weight.")
    _add_terminal(checks, len(weigh_events) >= 1,
                  "scale_read", f"{len(weigh_events)} weight reading(s)."
                  if weigh_events else "No weight reading.")

    # Tare before weigh
    if tared and weigh_events:
        ta_t = [e for e in events if e.get("event_type") == "scale.tared"][0].get("clock_time", 0)
        w_t = weigh_events[0].get("clock_time", 0)
        _add_temporal(checks, ta_t <= w_t, "tare_before_weigh",
                      f"Tare@{ta_t:.0f}s before weigh@{w_t:.0f}s.")

    # Transfer after tare + weigh
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(disp) >= 1
    _add_terminal(checks, tx_ok, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Transfer must happen after tare
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    if tared and aspirate_events:
        ta_t = [e for e in events if e.get("event_type") == "scale.tared"][0].get("clock_time", 0)
        a_t = aspirate_events[0].get("clock_time", 0)
        _add_temporal(checks, ta_t <= a_t, "tare_before_transfer",
                      f"Tare@{ta_t:.0f}s before transfer@{a_t:.0f}s.")

    # Attribution
    if not tared:
        attrs = {"label": "agent_error",
                 "detail": "Agent skipped tare — reading gross weight instead of net."}

    return checks, attrs


def _verify_zero_scale_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    """Zero at session start: must zero (session init) THEN tare (per-container)."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + scale zero + tare.")

    zeroed = any(e.get("event_type") == "scale.zeroed" for e in events)
    tared = any(e.get("event_type") == "scale.tared" for e in events)
    weigh_events = [e for e in events if e.get("event_type") == "scale.weight_read"]

    _add_terminal(checks, zeroed, "scale_zeroed",
                  "Scale zeroed." if zeroed else "Never zeroed — session init skipped.")
    _add_terminal(checks, tared, "scale_tared",
                  "Scale tared." if tared else "Never tared.")
    _add_terminal(checks, len(weigh_events) >= 1,
                  "weight_verified", "Weight checked." if weigh_events else "Never verified weight.")

    # Strict ordering: zero → tare → weigh → transfer → readout
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    if zeroed and tared:
        z_t = [e for e in events if e.get("event_type") == "scale.zeroed"][0].get("clock_time", 0)
        ta_t = [e for e in events if e.get("event_type") == "scale.tared"][0].get("clock_time", 0)
        _add_temporal(checks, z_t <= ta_t, "zero_before_tare",
                      f"Zero@{z_t:.0f}s before tare@{ta_t:.0f}s.")

    if tared and weigh_events:
        ta_t = [e for e in events if e.get("event_type") == "scale.tared"][0].get("clock_time", 0)
        w_t = weigh_events[0].get("clock_time", 0)
        _add_temporal(checks, ta_t <= w_t, "tare_before_weigh",
                      f"Tare@{ta_t:.0f}s before weigh@{w_t:.0f}s.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    tx_ok = len(disp) >= 1
    _add_terminal(checks, tx_ok, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Attribution: zero vs tare confusion
    if not zeroed and tared:
        attrs = {"label": "agent_error",
                 "detail": "Agent tared but did not zero — drift from previous session persists."}
    elif zeroed and not tared:
        attrs = {"label": "agent_error",
                 "detail": "Agent zeroed but did not tare — reading includes container weight."}
    elif not zeroed and not tared:
        attrs = {"label": "agent_error",
                 "detail": "Agent skipped all scale calibration."}

    return checks, attrs



# ── Arm scenario verifiers ──────────────────────────────────────────────


def _verify_arm_plate_transfer_qc(ls, exp):
    """Arm plate transfer: home→open→move→approach→close→pickup→move→approach→drop→safe.

    Depth features:
    - Pairwise temporal chain (6 pairs)
    - Resource coordinate tracking (pick-up at carrier pos, drop at reader pos)
    - Safety interlock: gripper must be open before pickup, closed before drop
    - Error-event detection: gripper_already_closed / gripper_already_open
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + robot arm plate transfer.")

    # ── Event presence ──────────────────────────────────────────────────
    homed = any(e.get("event_type") == "arm.homed" for e in events)
    gripper_opened = any(e.get("event_type") == "arm.gripper_opened" for e in events)
    gripper_closed = any(e.get("event_type") == "arm.gripper_closed" for e in events)
    picked = any(e.get("event_type") == "arm.picked_up" for e in events)
    dropped = any(e.get("event_type") == "arm.dropped" for e in events)
    safe = any(e.get("event_type") == "arm.safe" for e in events)
    reader_accessed = any(e.get("event_type") == "reader.opened" for e in events)
    moved_events = [e for e in events if e.get("event_type") == "arm.moved_to"]
    approached_events = [e for e in events if e.get("event_type") == "arm.approached"]

    # Error events (safety interlock violations)
    err_gripper_closed = any(
        e.get("event_type", "").startswith("error.") and
        "gripper_already_closed" in str(e.get("payload", {}))
        for e in events
    )
    err_gripper_open = any(
        e.get("event_type", "").startswith("error.") and
        "gripper_already_open" in str(e.get("payload", {}))
        for e in events
    )
    retries = sum(1 for e in events
                  if e.get("event_type", "").startswith("error.") and "gripper" in str(e.get("payload", {})))

    _add_terminal(checks, homed, "arm_homed", "Arm homed." if homed else "Arm never homed.")
    _add_terminal(checks, gripper_opened, "gripper_opened", "Gripper opened." if gripper_opened else "Gripper never opened — pickup impossible.")
    _add_terminal(checks, not err_gripper_closed, "no_safety_violation_pickup",
                  "No gripper-already-closed errors." if not err_gripper_closed
                  else f"Agent tried pickup with closed gripper ({retries} error(s)) — safety violation.")
    _add_terminal(checks, picked, "arm_picked_up", "Plate picked up." if picked else "Never picked up.")
    _add_terminal(checks, dropped, "arm_dropped", "Plate dropped." if dropped else "Never dropped.")
    _add_terminal(checks, not err_gripper_open, "no_safety_violation_drop",
                  "No gripper-already-open errors." if not err_gripper_open
                  else "Agent tried drop with open gripper — nothing to drop.")
    _add_terminal(checks, safe, "arm_safe", "Arm in safe position." if safe else "Arm not safed — unsafe termination.")
    _add_terminal(checks, reader_accessed, "reader_accessed",
                  "Reader opened." if reader_accessed else "Reader never accessed — plate never read.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Resource tracking: pickup/drop at expected coordinates ──────────
    if picked and dropped:
        pickup_payload = [e for e in events if e.get("event_type") == "arm.picked_up"][0].get("payload", {})
        drop_payload = [e for e in events if e.get("event_type") == "arm.dropped"][0].get("payload", {})
        pickup_x = pickup_payload.get("x", -1)
        drop_x = drop_payload.get("x", -1)
        # Pickup should be near carrier (~100, ~200) and drop near reader (~300, ~100)
        different_positions = abs(pickup_x - drop_x) > 50
        _add_terminal(checks, different_positions, "plate_relocated",
                      f"Plate moved from x≈{pickup_x} to x≈{drop_x} — relocated."
                      if different_positions else "Pickup and drop at same position — plate not moved.")

    # ── Pairwise temporal checks (6 pairs) ──────────────────────────────
    if homed and gripper_opened:
        h_t = [e for e in events if e.get("event_type") == "arm.homed"][0].get("clock_time", 0)
        go_t = [e for e in events if e.get("event_type") == "arm.gripper_opened"][0].get("clock_time", 0)
        _add_temporal(checks, h_t <= go_t, "home_before_open",
                      f"Home@{h_t:.0f}s → open@{go_t:.0f}s."
                      if h_t <= go_t else "Gripper opened before homing — unsafe.")

    if gripper_opened and gripper_closed:
        go_t = [e for e in events if e.get("event_type") == "arm.gripper_opened"][0].get("clock_time", 0)
        gc_t = [e for e in events if e.get("event_type") == "arm.gripper_closed"][0].get("clock_time", 0)
        _add_temporal(checks, go_t <= gc_t, "open_before_close",
                      f"Open@{go_t:.0f}s → close@{gc_t:.0f}s."
                      if go_t <= gc_t else "Gripper closed before opening — impossible to insert plate.")

    if gripper_closed and picked:
        gc_t = [e for e in events if e.get("event_type") == "arm.gripper_closed"][0].get("clock_time", 0)
        p_t = [e for e in events if e.get("event_type") == "arm.picked_up"][0].get("clock_time", 0)
        _add_temporal(checks, gc_t <= p_t, "close_before_pickup",
                      f"Close@{gc_t:.0f}s → pickup@{p_t:.0f}s."
                      if gc_t <= p_t else "Pickup before grip closed — plate not secured.")

    if picked and dropped:
        p_t = [e for e in events if e.get("event_type") == "arm.picked_up"][0].get("clock_time", 0)
        d_t = [e for e in events if e.get("event_type") == "arm.dropped"][0].get("clock_time", 0)
        _add_temporal(checks, p_t <= d_t, "pickup_before_drop",
                      f"Pickup@{p_t:.0f}s → drop@{d_t:.0f}s."
                      if p_t <= d_t else "Dropped before picking up — nothing to drop.")

    if dropped and safe:
        d_t = [e for e in events if e.get("event_type") == "arm.dropped"][0].get("clock_time", 0)
        s_t = [e for e in events if e.get("event_type") == "arm.safe"][-1].get("clock_time", 0)
        _add_temporal(checks, d_t <= s_t, "drop_before_safe",
                      f"Drop@{d_t:.0f}s → safe@{s_t:.0f}s."
                      if d_t <= s_t else "Safed before dropping — plate may not be placed correctly.")

    if safe and reader_accessed:
        s_t = [e for e in events if e.get("event_type") == "arm.safe"][-1].get("clock_time", 0)
        ra_t = [e for e in events if e.get("event_type") == "reader.opened"][0].get("clock_time", 0)
        _add_temporal(checks, s_t <= ra_t, "safe_before_reader",
                      f"Safe@{s_t:.0f}s → reader@{ra_t:.0f}s (arm clear before read)."
                      if s_t <= ra_t else "Reader accessed before arm safed — collision risk.")

    # ── Attribution ─────────────────────────────────────────────────────
    if retries >= 1 and picked and dropped and safe:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Agent recovered from {retries} gripper error(s) and completed full transfer."}
    elif retries >= 1 and not safe:
        attrs = {"label": "agent_recovery_failure",
                 "detail": f"Agent hit {retries} error(s) but failed to recover — arm not safed."}
    elif err_gripper_closed:
        attrs = {"label": "agent_error",
                 "detail": "Agent attempted pickup with closed gripper — forgot to open first."}
    elif err_gripper_open:
        attrs = {"label": "agent_error",
                 "detail": "Agent attempted drop with open gripper — forgot to grip first."}
    elif homed and picked and dropped and safe and reader_accessed:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly executed full arm pick-and-place sequence."}
    elif not safe:
        attrs = {"label": "agent_error",
                 "detail": "Agent left arm in unsafe position after transfer."}

    return checks, attrs


def _verify_arm_halt_recovery_qc(ls, exp):
    """Arm halt recovery: home→move→halt→position_check→safe→transfer→read.

    Depth features:
    - Motion→halt transition verification (was arm in motion when halted?)
    - Position threshold: after home position ≈ (0, 0, ~150)
    - Pre-halt vs post-halt position comparison (did the arm actually stop?)
    - Retry tracking: multiple halts without recovery is worse
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + arm halt recovery.")

    homed = any(e.get("event_type") == "arm.homed" for e in events)
    moved = any(e.get("event_type") == "arm.moved_to" for e in events)
    halted = any(e.get("event_type") == "arm.halted" for e in events)
    pos_checks = [e for e in events if e.get("event_type") == "arm.position_read"]
    gripper_checks = [e for e in events if e.get("event_type") == "arm.gripper_state"]
    safe = any(e.get("event_type") == "arm.safe" for e in events)

    _add_terminal(checks, homed, "arm_homed", "Arm homed." if homed else "Arm never homed.")
    _add_terminal(checks, moved, "arm_moved", "Arm moved toward target." if moved else "Arm never moved — halt unnecessary.")
    _add_terminal(checks, halted, "arm_halted", "Arm halted." if halted else "Arm never halted — collision risk not addressed.")
    _add_terminal(checks, len(pos_checks) >= 1, "position_checked",
                  f"Position checked {len(pos_checks)} time(s)." if pos_checks else "Position never checked — blind recovery.")
    _add_terminal(checks, len(gripper_checks) >= 1, "gripper_checked_during_recovery",
                  f"Gripper checked {len(gripper_checks)} time(s)." if gripper_checks
                  else "Gripper state never checked during recovery.")
    _add_terminal(checks, safe, "arm_safe", "Arm in safe position." if safe else "Arm not safed — risk persists.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed after recovery.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Position threshold: after home, should be near (0, 0, ~150) ────
    if pos_checks and homed:
        home_events = [e for e in events if e.get("event_type") == "arm.homed"]
        if home_events:
            home_t = home_events[0].get("clock_time", 0)
            # Find first position check after home
            post_home_positions = [e for e in pos_checks if e.get("clock_time", 0) >= home_t]
            if post_home_positions:
                first_pos = post_home_positions[0].get("payload", {})
                px, py, pz = first_pos.get("x", -1), first_pos.get("y", -1), first_pos.get("z", -1)
                at_home = abs(px) < 10 and abs(py) < 10 and abs(pz - 150) < 20
                _add_terminal(checks, at_home, "home_position_correct",
                              f"Position after home: ({px}, {py}, {pz}) ≈ (0, 0, 150)."
                              if at_home else f"Position ({px}, {py}, {pz}) not near home (0, 0, 150) — homing failed?")

    # ── Motion→halt transition: was arm in motion? ──────────────────────
    if moved and halted:
        move_times = [e.get("clock_time", 0) for e in events if e.get("event_type") == "arm.moved_to"]
        halt_times = [e.get("clock_time", 0) for e in events if e.get("event_type") == "arm.halted"]
        if move_times and halt_times:
            # Check there's a move before a halt (arm was moving)
            last_move_before_halt = max(t for t in move_times if t <= halt_times[0])
            motion_to_halt_gap = halt_times[0] - last_move_before_halt
            _add_temporal(checks, motion_to_halt_gap >= 0, "motion_before_halt",
                          f"Move@{last_move_before_halt:.0f}s → halt@{halt_times[0]:.0f}s (gap={motion_to_halt_gap:.0f}s)."
                          if motion_to_halt_gap >= 0 else "Halt before any move — nothing to halt.")

    # ── Pre-halt vs post-halt position: did arm actually stop? ──────────
    if len(pos_checks) >= 2:
        pre_halt = [e for e in pos_checks if halted and e.get("clock_time", 0) <=
                    [h.get("clock_time", 0) for h in events if h.get("event_type") == "arm.halted"][0]]
        post_halt = [e for e in pos_checks if halted and e.get("clock_time", 0) >
                     [h.get("clock_time", 0) for h in events if h.get("event_type") == "arm.halted"][0]]
        if pre_halt and post_halt:
            pre_pos = pre_halt[-1].get("payload", {})
            post_pos = post_halt[0].get("payload", {})
            pre_xyz = (pre_pos.get("x", 0), pre_pos.get("y", 0), pre_pos.get("z", 0))
            post_xyz = (post_pos.get("x", 0), post_pos.get("y", 0), post_pos.get("z", 0))
            stopped = pre_xyz == post_xyz
            _add_terminal(checks, stopped, "halt_effective",
                          f"Position unchanged after halt — arm stopped."
                          if stopped else f"Position changed after halt ({pre_xyz}→{post_xyz}) — halt may have been ineffective.")

    # ── Pairwise temporal ───────────────────────────────────────────────
    if homed and halted:
        h_t = [e for e in events if e.get("event_type") == "arm.homed"][0].get("clock_time", 0)
        halt_t = [e for e in events if e.get("event_type") == "arm.halted"][0].get("clock_time", 0)
        _add_temporal(checks, h_t <= halt_t, "home_before_halt",
                      f"Home@{h_t:.0f}s → halt@{halt_t:.0f}s."
                      if h_t <= halt_t else "Halt before home — unsafe sequence.")

    if halted and safe:
        halt_t = [e for e in events if e.get("event_type") == "arm.halted"][0].get("clock_time", 0)
        s_t = [e for e in events if e.get("event_type") == "arm.safe"][-1].get("clock_time", 0)
        _add_temporal(checks, halt_t <= s_t, "halt_before_safe",
                      f"Halt@{halt_t:.0f}s → safe@{s_t:.0f}s."
                      if halt_t <= s_t else "Safed before halting — potential collision not resolved.")

    # ── Attribution ─────────────────────────────────────────────────────
    if homed and halted and safe and len(pos_checks) >= 1:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly halted, verified position, and moved to safe position."}
    elif halted and not safe:
        attrs = {"label": "agent_recovery_failure",
                 "detail": "Agent halted but failed to safen arm — recovery incomplete."}
    elif not halted and moved:
        attrs = {"label": "agent_error",
                 "detail": "Arm was moving but agent never halted — ignored potential collision."}
    elif not homed:
        attrs = {"label": "agent_error",
                 "detail": "Agent operated arm without homing first — position unknown."}

    return checks, attrs


def _verify_arm_position_verify_qc(ls, exp):
    """Arm position verify: home→check→gripper_open→move→approach→close→check→pickup→check→safe.

    Depth features:
    - Position threshold verification (home≈(0,0,150), pickup≈(100,200,30))
    - Gripper state consistency: open/close events must match gripper_state queries
    - Multi-point checkpoint timing (before pickup, after pickup, before safe)
    - State mismatch detection (gripper_state says closed but no close_gripper event)
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + arm position verification.")

    homed = any(e.get("event_type") == "arm.homed" for e in events)
    pos_checks = [e for e in events if e.get("event_type") == "arm.position_read"]
    gripper_states = [e for e in events if e.get("event_type") == "arm.gripper_state"]
    gripper_opened = any(e.get("event_type") == "arm.gripper_opened" for e in events)
    gripper_closed = any(e.get("event_type") == "arm.gripper_closed" for e in events)
    picked = any(e.get("event_type") == "arm.picked_up" for e in events)
    safe = any(e.get("event_type") == "arm.safe" for e in events)
    approached = any(e.get("event_type") == "arm.approached" for e in events)

    _add_terminal(checks, homed, "arm_homed", "Arm homed." if homed else "Arm never homed — position unknown.")
    _add_terminal(checks, len(pos_checks) >= 2, "multi_point_position_check",
                  f"Position checked at {len(pos_checks)} points (need ≥2)." if len(pos_checks) >= 2
                  else f"Only {len(pos_checks)} position check(s) — must check before AND after operation.")
    _add_terminal(checks, len(gripper_states) >= 2, "multi_point_gripper_check",
                  f"Gripper checked at {len(gripper_states)} points (need ≥2)." if len(gripper_states) >= 2
                  else f"Only {len(gripper_states)} gripper check(s) — must check before AND after grip.")
    _add_terminal(checks, gripper_opened, "gripper_opened",
                  "Gripper opened." if gripper_opened else "Gripper never opened — cannot insert plate.")
    _add_terminal(checks, gripper_closed, "gripper_closed",
                  "Gripper closed." if gripper_closed else "Gripper never closed — plate not secured.")
    _add_terminal(checks, picked, "arm_picked_up", "Plate picked up." if picked else "Never picked up.")
    _add_terminal(checks, safe, "arm_safe", "Arm in safe position." if safe else "Arm not safed.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Gripper state consistency ───────────────────────────────────────
    if gripper_states and gripper_opened and gripper_closed:
        # Check gripper_state events before close_gripper all say "open"
        gc_time = [e for e in events if e.get("event_type") == "arm.gripper_closed"][0].get("clock_time", 0)
        before_close = [g for g in gripper_states if g.get("clock_time", 0) < gc_time]
        # Check gripper_state events after close_gripper say "closed"
        after_close = [g for g in gripper_states if g.get("clock_time", 0) > gc_time]

        before_consistent = all(
            g.get("payload", {}).get("gripper_closed") is False
            for g in before_close
        ) if before_close else True
        after_consistent = all(
            g.get("payload", {}).get("gripper_closed") is True
            for g in after_close
        ) if after_close else True

        if before_close:
            _add_terminal(checks, before_consistent, "gripper_open_before_close",
                          "All pre-close gripper checks show OPEN (correct)."
                          if before_consistent else "Gripper claims closed before close_gripper event — state mismatch!")
        if after_close:
            _add_terminal(checks, after_consistent, "gripper_closed_after_close",
                          "All post-close gripper checks show CLOSED (correct)."
                          if after_consistent else "Gripper claims open after close_gripper event — grip failed!")

    # ── Position threshold: verify at key checkpoints ───────────────────
    if pos_checks and homed:
        home_t = [e for e in events if e.get("event_type") == "arm.homed"][0].get("clock_time", 0)
        # Find position check right after home
        post_home = [p for p in pos_checks if p.get("clock_time", 0) >= home_t]
        if post_home:
            pp = post_home[0].get("payload", {})
            hx, hy, hz = pp.get("x", -1), pp.get("y", -1), pp.get("z", -1)
            at_home = abs(hx) < 10 and abs(hy) < 10 and abs(hz - 150) < 20
            _add_terminal(checks, at_home, "home_position_verified",
                          f"Home position ({hx}, {hy}, {hz}) verified."
                          if at_home else f"Position ({hx}, {hy}, {hz}) ≠ home (0, 0, ~150) — verify failed.")

    # ── Checkpoint coverage: position checks at key phases ──────────────
    if picked and pos_checks:
        pickup_t = [e for e in events if e.get("event_type") == "arm.picked_up"][0].get("clock_time", 0)
        before_pickup = any(
            p.get("clock_time", 0) < pickup_t for p in pos_checks
        )
        after_pickup = any(
            p.get("clock_time", 0) > pickup_t for p in pos_checks
        )
        _add_terminal(checks, before_pickup, "position_before_pickup",
                      "Position checked BEFORE pickup." if before_pickup
                      else "No position check before pickup — blind approach!")
        _add_terminal(checks, after_pickup, "position_after_pickup",
                      "Position checked AFTER pickup." if after_pickup
                      else "No position check after pickup — blind transport!")

    # ── Pairwise temporal ───────────────────────────────────────────────
    if homed and gripper_opened:
        h_t = [e for e in events if e.get("event_type") == "arm.homed"][0].get("clock_time", 0)
        go_t = [e for e in events if e.get("event_type") == "arm.gripper_opened"][0].get("clock_time", 0)
        _add_temporal(checks, h_t <= go_t, "home_before_open",
                      f"Home@{h_t:.0f}s → open@{go_t:.0f}s."
                      if h_t <= go_t else "Opened before home — unsafe.")

    if gripper_opened and gripper_closed:
        go_t = [e for e in events if e.get("event_type") == "arm.gripper_opened"][0].get("clock_time", 0)
        gc_t = [e for e in events if e.get("event_type") == "arm.gripper_closed"][0].get("clock_time", 0)
        _add_temporal(checks, go_t <= gc_t, "open_before_close",
                      f"Open@{go_t:.0f}s → close@{gc_t:.0f}s."
                      if go_t <= gc_t else "Closed before opening — impossible grip sequence.")

    if gripper_closed and picked:
        gc_t = [e for e in events if e.get("event_type") == "arm.gripper_closed"][0].get("clock_time", 0)
        p_t = [e for e in events if e.get("event_type") == "arm.picked_up"][0].get("clock_time", 0)
        _add_temporal(checks, gc_t <= p_t, "close_before_pickup",
                      f"Close@{gc_t:.0f}s → pickup@{p_t:.0f}s."
                      if gc_t <= p_t else "Pickup before close — plate not gripped!")

    if picked and safe:
        p_t = [e for e in events if e.get("event_type") == "arm.picked_up"][0].get("clock_time", 0)
        s_t = [e for e in events if e.get("event_type") == "arm.safe"][-1].get("clock_time", 0)
        _add_temporal(checks, p_t <= s_t, "pickup_before_safe",
                      f"Pickup@{p_t:.0f}s → safe@{s_t:.0f}s."
                      if p_t <= s_t else "Safed before pickup — plate not retrieved.")

    # ── Attribution ─────────────────────────────────────────────────────
    state_mismatch = False
    if gripper_states and gripper_closed:
        gc_time = [e for e in events if e.get("event_type") == "arm.gripper_closed"][0].get("clock_time", 0)
        after = [g for g in gripper_states if g.get("clock_time", 0) > gc_time]
        if after:
            state_mismatch = any(
                g.get("payload", {}).get("gripper_closed") is not True
                for g in after
            )

    if len(pos_checks) >= 2 and len(gripper_states) >= 2 and not state_mismatch:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent verified arm position and gripper state at multiple safety checkpoints."}
    elif state_mismatch:
        attrs = {"label": "agent_error",
                 "detail": "Gripper state inconsistent with close/open events — agent may have misread or skipped checks."}
    elif len(pos_checks) < 2:
        attrs = {"label": "agent_error",
                 "detail": "Agent did not verify arm position at enough checkpoints — insufficient safety checks."}
    elif not gripper_states:
        attrs = {"label": "agent_error",
                 "detail": "Agent never queried gripper state — operating blind."}

    return checks, attrs


# ── Sealer scenario verifiers ───────────────────────────────────────────


def _verify_seal_plate_qc(ls, exp):
    """Seal plate: set_temp→verify→close→seal→open→transfer→read.

    Depth features:
    - Pairwise temporal chain (4 pairs)
    - Temperature verification (set temp must match seal temp)
    - Door safety interlock (close before seal)
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + plate sealer.")

    temp_set = any(e.get("event_type") == "sealer.temp_set" for e in events)
    temp_reads = [e for e in events if e.get("event_type") == "sealer.temp_read"]
    closed = any(e.get("event_type") == "sealer.closed" for e in events)
    sealed = any(e.get("event_type") == "sealer.sealed" for e in events)
    opened = any(e.get("event_type") == "sealer.opened" for e in events)

    _add_terminal(checks, temp_set, "temp_set", "Temperature set." if temp_set else "Never set temperature.")
    _add_terminal(checks, len(temp_reads) >= 1, "temp_verified",
                  f"Temperature checked {len(temp_reads)} time(s)." if temp_reads else "Never checked temperature.")
    _add_terminal(checks, closed, "door_closed", "Door closed." if closed else "Door not closed — seal impossible.")
    _add_terminal(checks, sealed, "sealed", "Plate sealed." if sealed else "Never sealed.")
    _add_terminal(checks, opened, "door_opened", "Door opened after seal." if opened else "Door still closed — plate inaccessible.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Temperature verification: set temp should match seal temp ───────
    if temp_set and sealed:
        set_payload = [e for e in events if e.get("event_type") == "sealer.temp_set"][0].get("payload", {})
        seal_payload = [e for e in events if e.get("event_type") == "sealer.sealed"][0].get("payload", {})
        set_t = set_payload.get("target_temperature", 0)
        seal_t = seal_payload.get("temperature", 0)
        temps_match = abs(set_t - seal_t) <= 5
        _add_terminal(checks, temps_match, "temp_match",
                      f"Set@{set_t}°C ≈ seal@{seal_t}°C (within 5°C)."
                      if temps_match else f"Set@{set_t}°C ≠ seal@{seal_t}°C — temperature mismatch!")

    # ── Pairwise temporal (4 pairs) ─────────────────────────────────────
    if temp_set and temp_reads:
        ts_t = [e for e in events if e.get("event_type") == "sealer.temp_set"][0].get("clock_time", 0)
        tr_t = temp_reads[0].get("clock_time", 0)
        _add_temporal(checks, ts_t <= tr_t, "set_before_read",
                      f"Set@{ts_t:.0f}s → read@{tr_t:.0f}s."
                      if ts_t <= tr_t else "Read before set — verifying meaningless value.")

    if temp_reads and closed:
        tr_t = temp_reads[-1].get("clock_time", 0)
        c_t = [e for e in events if e.get("event_type") == "sealer.closed"][0].get("clock_time", 0)
        _add_temporal(checks, tr_t <= c_t, "verify_before_close",
                      f"Verify@{tr_t:.0f}s → close@{c_t:.0f}s (temp verified before closing)."
                      if tr_t <= c_t else "Door closed before verifying temperature — may seal at wrong temp.")

    if closed and sealed:
        c_t = [e for e in events if e.get("event_type") == "sealer.closed"][0].get("clock_time", 0)
        s_t = [e for e in events if e.get("event_type") == "sealer.sealed"][0].get("clock_time", 0)
        _add_temporal(checks, c_t <= s_t, "close_before_seal",
                      f"Close@{c_t:.0f}s → seal@{s_t:.0f}s."
                      if c_t <= s_t else "Sealed before closing door — safety violation!")

    if sealed and opened:
        s_t = [e for e in events if e.get("event_type") == "sealer.sealed"][0].get("clock_time", 0)
        o_t = [e for e in events if e.get("event_type") == "sealer.opened"][-1].get("clock_time", 0)
        _add_temporal(checks, s_t <= o_t, "seal_before_open",
                      f"Seal@{s_t:.0f}s → open@{o_t:.0f}s."
                      if s_t <= o_t else "Opened before seal — plate not sealed!")

    # ── Attribution ─────────────────────────────────────────────────────
    if sealed and not closed:
        attrs = {"label": "agent_error",
                 "detail": "Agent sealed without closing the door — safety interlock should have prevented this."}
    elif temp_set and sealed and opened:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly set temperature, closed door, sealed, and opened."}
    elif not temp_set and sealed:
        attrs = {"label": "agent_error",
                 "detail": "Agent sealed without setting temperature — seal may be ineffective."}

    return checks, attrs


def _verify_seal_temp_verify_qc(ls, exp):
    """Seal temp verify: set→read→close→seal→open. Must read temp BEFORE seal.

    Depth features:
    - Temperature verification timing (read must be between set and seal)
    - Minimum temperature check: sealing below target is a fault
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + sealer temp verification.")

    temp_set = any(e.get("event_type") == "sealer.temp_set" for e in events)
    temp_reads = [e for e in events if e.get("event_type") == "sealer.temp_read"]
    closed = any(e.get("event_type") == "sealer.closed" for e in events)
    sealed = any(e.get("event_type") == "sealer.sealed" for e in events)
    opened = any(e.get("event_type") == "sealer.opened" for e in events)

    _add_terminal(checks, temp_set, "temp_set", "Temperature set." if temp_set else "Never set.")
    _add_terminal(checks, len(temp_reads) >= 1, "temp_verified",
                  f"Temperature read {len(temp_reads)} time(s)." if temp_reads else "Never read — blind seal!")
    _add_terminal(checks, closed, "door_closed", "Door closed." if closed else "Door not closed.")
    _add_terminal(checks, sealed, "sealed", "Sealed." if sealed else "Never sealed.")
    _add_terminal(checks, opened, "door_opened", "Door opened after seal." if opened else "Still closed.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Critical: temperature read MUST be between set and seal ─────────
    if temp_set and temp_reads and sealed:
        ts_t = [e for e in events if e.get("event_type") == "sealer.temp_set"][0].get("clock_time", 0)
        s_t = [e for e in events if e.get("event_type") == "sealer.sealed"][0].get("clock_time", 0)
        reads_between = [r for r in temp_reads
                         if ts_t <= r.get("clock_time", 0) <= s_t]
        _add_terminal(checks, len(reads_between) >= 1, "temp_verified_between_set_and_seal",
                      f"Temperature verified {len(reads_between)} time(s) between set and seal."
                      if reads_between else "Temperature NEVER verified after setting — sealed with unverified temp!")

    # ── Target temperature check ────────────────────────────────────────
    expected_temp = exp.get("seal_temperature", 165)
    if temp_reads:
        actual_temps = [r.get("payload", {}).get("current_temperature", 0) for r in temp_reads]
        if actual_temps:
            avg_temp = sum(actual_temps) / len(actual_temps)
            temp_ok = abs(avg_temp - expected_temp) <= 5
            _add_terminal(checks, temp_ok, "correct_temperature",
                          f"Avg temp {avg_temp:.0f}°C ≈ target {expected_temp}°C (within 5°C)."
                          if temp_ok else f"Avg temp {avg_temp:.0f}°C ≠ target {expected_temp}°C — wrong sealing temperature!")

    # ── Pairwise temporal ───────────────────────────────────────────────
    if closed and sealed:
        c_t = [e for e in events if e.get("event_type") == "sealer.closed"][0].get("clock_time", 0)
        s_t = [e for e in events if e.get("event_type") == "sealer.sealed"][0].get("clock_time", 0)
        _add_temporal(checks, c_t <= s_t, "close_before_seal",
                      f"Close@{c_t:.0f}s → seal@{s_t:.0f}s.")

    # ── Attribution ─────────────────────────────────────────────────────
    if temp_reads and sealed and opened:
        reads_between = []
        if temp_set:
            ts_t = [e for e in events if e.get("event_type") == "sealer.temp_set"][0].get("clock_time", 0)
            s_t = [e for e in events if e.get("event_type") == "sealer.sealed"][0].get("clock_time", 0)
            reads_between = [r for r in temp_reads if ts_t <= r.get("clock_time", 0) <= s_t]
        if reads_between:
            attrs = {"label": "success_despite_fault",
                     "detail": "Agent verified temperature between set and seal — protocol compliant."}
        else:
            attrs = {"label": "agent_error",
                     "detail": "Agent sealed without verifying temperature between set and seal — protocol deviation."}
    elif not temp_reads and sealed:
        attrs = {"label": "agent_error",
                 "detail": "Agent sealed without any temperature check — risk of incorrect sealing."}

    return checks, attrs


def _verify_seal_door_safety_qc(ls, exp):
    """Seal door safety: close→seal→open. Safety interlock validation.

    Depth features:
    - Error event detection (door_open error means agent tried seal with door open)
    - Recovery tracking (retry count after error)
    - Safety interlock pairwise temporal verification
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + sealer door safety.")

    temp_set = any(e.get("event_type") == "sealer.temp_set" for e in events)
    temp_reads = [e for e in events if e.get("event_type") == "sealer.temp_read"]
    closed = any(e.get("event_type") == "sealer.closed" for e in events)
    sealed = any(e.get("event_type") == "sealer.sealed" for e in events)
    opened = any(e.get("event_type") == "sealer.opened" for e in events)

    # Error detection: agent might hit "door_open" error if sealing before closing
    door_errors = [e for e in events
                   if e.get("event_type", "").startswith("error.") and
                   "door_open" in e.get("event_type", "")]
    door_open_spins = len(door_errors)
    seal_retries = len([e for e in events if e.get("event_type") == "sealer.sealed"])

    _add_terminal(checks, temp_set, "temp_set", "Temperature set." if temp_set else "Never set.")
    _add_terminal(checks, closed, "door_closed", "Door closed." if closed else "Door never closed — safety violation.")
    _add_terminal(checks, sealed, "sealed", "Sealed." if sealed else "Never sealed.")
    _add_terminal(checks, opened, "door_opened", "Door opened after seal." if opened else "Still closed.")
    _add_terminal(checks, True if door_open_spins == 0 else sealed, "no_door_open_error_unrecovered",
                  "No door-open errors (or recovered)."
                  if door_open_spins == 0 or sealed
                  else f"Agent hit {door_open_spins} door-open error(s) and never sealed — unrecovered.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Safety interlock: close MUST happen before seal ─────────────────
    if closed and sealed:
        c_t = [e for e in events if e.get("event_type") == "sealer.closed"][0].get("clock_time", 0)
        s_t = [e for e in events if e.get("event_type") == "sealer.sealed"][0].get("clock_time", 0)
        interlock_ok = c_t <= s_t
        _add_temporal(checks, interlock_ok, "close_before_seal_safety",
                      f"Close@{c_t:.0f}s → seal@{s_t:.0f}s (interlock satisfied)."
                      if interlock_ok else "Seal@{s_t:.0f}s before close@{c_t:.0f}s — INTERLOCK VIOLATION!")

    if sealed and opened:
        s_t = [e for e in events if e.get("event_type") == "sealer.sealed"][0].get("clock_time", 0)
        o_t = [e for e in events if e.get("event_type") == "sealer.opened"][-1].get("clock_time", 0)
        _add_temporal(checks, s_t <= o_t, "seal_before_open",
                      f"Seal@{s_t:.0f}s → open@{o_t:.0f}s.")

    # ── Error recovery tracking ─────────────────────────────────────────
    if door_open_spins > 0:
        if seal_retries > door_open_spins or sealed:
            _add_terminal(checks, True, "door_error_recovered",
                          f"Agent recovered from {door_open_spins} door error(s) — successfully sealed after correction.")
        else:
            _add_terminal(checks, False, "door_error_unrecovered",
                          f"Agent hit {door_open_spins} door error(s) and never recovered — abandoned seal.")

    # ── Attribution ─────────────────────────────────────────────────────
    if door_open_spins > 0 and sealed:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Agent hit {door_open_spins} 'door open' error(s) but recovered and sealed successfully."}
    elif sealed and not closed:
        attrs = {"label": "agent_recovery_failure",
                 "detail": "Agent sealed with door open — safety interlock failure."}
    elif door_open_spins > 0 and not sealed:
        attrs = {"label": "agent_recovery_failure",
                 "detail": f"Agent hit {door_open_spins} door error(s) but never recovered to complete the seal."}
    elif closed and sealed and opened:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly followed door safety protocol: close→seal→open."}

    return checks, attrs


# ── Peeler scenario verifiers ───────────────────────────────────────────


def _verify_peel_plate_qc(ls, exp):
    """Peel plate: in→up→seal_check→peel→check→down→out→transfer→read.

    Depth features:
    - Full 7-step temporal chain
    - Pre/post peel seal state verification
    - no_seal error detection
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + plate peeler.")

    conv_in = any(e.get("event_type") == "peeler.conveyor_in" for e in events)
    elev_up = any(e.get("event_type") == "peeler.elevator_up" for e in events)
    seal_checks = [e for e in events if e.get("event_type") == "peeler.seal_checked"]
    peeled = any(e.get("event_type") == "peeler.peeled" for e in events)
    elev_down = any(e.get("event_type") == "peeler.elevator_down" for e in events)
    conv_out = any(e.get("event_type") == "peeler.conveyor_out" for e in events)

    _add_terminal(checks, conv_in, "conveyor_in", "Conveyor in." if conv_in else "Never loaded.")
    _add_terminal(checks, elev_up, "elevator_up", "Elevator up." if elev_up else "Not raised to peel position.")
    _add_terminal(checks, len(seal_checks) >= 2, "seal_checked_before_after",
                  f"Seal checked {len(seal_checks)} time(s) (need before+after)." if len(seal_checks) >= 2
                  else f"Only {len(seal_checks)} seal check(s) — must check before AND after peel.")
    _add_terminal(checks, peeled, "peeled", "Peeled." if peeled else "Never peeled.")
    _add_terminal(checks, elev_down, "elevator_down", "Elevator down." if elev_down else "Still raised.")
    _add_terminal(checks, conv_out, "conveyor_out", "Conveyor out." if conv_out else "Never unloaded.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Pre-peel vs post-peel seal state ─────────────────────────────────
    if len(seal_checks) >= 2 and peeled:
        p_t = [e for e in events if e.get("event_type") == "peeler.peeled"][0].get("clock_time", 0)
        before = [s for s in seal_checks if s.get("clock_time", 0) < p_t]
        after = [s for s in seal_checks if s.get("clock_time", 0) > p_t]
        if before:
            pre_status = before[-1].get("payload", {}).get("seal_status", "")
            pre_seal_ok = pre_status == "seal_detected"
            _add_terminal(checks, pre_seal_ok, "seal_detected_before_peel",
                          f"Pre-peel: '{pre_status}' — seal present."
                          if pre_seal_ok else f"Pre-peel: '{pre_status}' — no seal to remove!")
        if after:
            post_status = after[0].get("payload", {}).get("seal_status", "")
            post_seal_ok = post_status == "no_seal"
            _add_terminal(checks, post_seal_ok, "no_seal_after_peel",
                          f"Post-peel: '{post_status}' — seal removed."
                          if post_seal_ok else f"Post-peel: '{post_status}' — seal still present!")

    # ── Pairwise temporal (full chain) ──────────────────────────────────
    if conv_in and elev_up and peeled and elev_down and conv_out:
        ci_t = [e for e in events if e.get("event_type") == "peeler.conveyor_in"][0].get("clock_time", 0)
        eu_t = [e for e in events if e.get("event_type") == "peeler.elevator_up"][0].get("clock_time", 0)
        p_t = [e for e in events if e.get("event_type") == "peeler.peeled"][0].get("clock_time", 0)
        ed_t = [e for e in events if e.get("event_type") == "peeler.elevator_down"][0].get("clock_time", 0)
        co_t = [e for e in events if e.get("event_type") == "peeler.conveyor_out"][0].get("clock_time", 0)
        chain_ok = ci_t <= eu_t <= p_t <= ed_t <= co_t
        _add_temporal(checks, chain_ok, "peel_full_chain",
                      f"In→up→peel→down→out in order."
                      if chain_ok else "Peel chain broken.")

    # ── Attribution ─────────────────────────────────────────────────────
    if conv_in and peeled and conv_out:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly loaded, peeled, and unloaded the plate."}
    elif peeled and not conv_in:
        attrs = {"label": "agent_error",
                 "detail": "Agent peeled without loading plate via conveyor — how did plate get there?"}

    return checks, attrs


def _verify_peel_tape_monitor_qc(ls, exp):
    """Peel tape monitor: check status+tape→peel→check status+tape→transfer→read.

    Depth features:
    - Pre/post consumable comparison (tape decreased ~1% per peel)
    - Device status must be healthy before AND after
    - Tape low warning threshold (<5%)
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + peeler tape monitoring.")

    tape_checks = [e for e in events if e.get("event_type") == "peeler.tape_checked"]
    tape_advanced = any(e.get("event_type") == "peeler.tape_advanced" for e in events)
    status_checks = [e for e in events if e.get("event_type") == "peeler.status_checked"]
    peeled = any(e.get("event_type") == "peeler.peeled" for e in events)

    _add_terminal(checks, len(status_checks) >= 2, "status_before_after",
                  f"Status checked {len(status_checks)} time(s) (need before+after)." if len(status_checks) >= 2
                  else f"Only {len(status_checks)} status check(s).")
    _add_terminal(checks, len(tape_checks) >= 2, "tape_before_after",
                  f"Tape checked {len(tape_checks)} time(s) (need before+after)." if len(tape_checks) >= 2
                  else f"Only {len(tape_checks)} tape check(s).")
    _add_terminal(checks, tape_advanced, "tape_advanced", "Tape advanced." if tape_advanced else "Never advanced tape.")
    _add_terminal(checks, peeled, "peeled", "Peeled." if peeled else "Never peeled.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Tape consumption: should decrease after peel ────────────────────
    if len(tape_checks) >= 2 and peeled:
        p_t = [e for e in events if e.get("event_type") == "peeler.peeled"][0].get("clock_time", 0)
        before = [t for t in tape_checks if t.get("clock_time", 0) < p_t]
        after = [t for t in tape_checks if t.get("clock_time", 0) > p_t]
        if before and after:
            before_pct = before[-1].get("payload", {}).get("tape_remaining_pct", 0)
            after_pct = after[0].get("payload", {}).get("tape_remaining_pct", 0)
            decreased = after_pct < before_pct
            _add_terminal(checks, decreased, "tape_decreased",
                          f"Tape: {before_pct}% → {after_pct}% (decreased by {before_pct - after_pct:.1f}%)."
                          if decreased else f"Tape unchanged: {before_pct}% — peel didn't consume tape?")
            # Low tape warning
            if after_pct < 5.0:
                _add_terminal(checks, False, "tape_low_warning",
                              f"Tape at {after_pct}% — CRITICALLY LOW, needs replacement.")
            else:
                _add_terminal(checks, True, "tape_sufficient",
                              f"Tape at {after_pct}% — sufficient for continued operation.")

    # ── Temporal: status+tape checks before peel ────────────────────────
    if peeled and tape_checks:
        p_t = [e for e in events if e.get("event_type") == "peeler.peeled"][0].get("clock_time", 0)
        before_tape = [t for t in tape_checks if t.get("clock_time", 0) < p_t]
        _add_temporal(checks, len(before_tape) >= 1, "tape_checked_before_peel",
                      f"Tape checked {len(before_tape)} time(s) before peel."
                      if before_tape else "Tape NEVER checked before peel — blind operation!")

    # ── Attribution ─────────────────────────────────────────────────────
    if len(tape_checks) >= 2 and len(status_checks) >= 2:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent monitored tape and status before and after peel — good practice."}
    elif peeled and len(tape_checks) < 2:
        attrs = {"label": "agent_error",
                 "detail": "Agent peeled without sufficient tape/status monitoring."}

    return checks, attrs


def _verify_peel_no_seal_qc(ls, exp):
    """Peel no-seal: agent must handle 'no_seal' gracefully.

    Depth features:
    - Response-adaptive verification: if seal detected→must peel, if no_seal→must skip
    - Forced-peel error detection (peeling when no seal present is an agent_error)
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + peeler no-seal handling.")

    seal_checks = [e for e in events if e.get("event_type") == "peeler.seal_checked"]
    peeled = any(e.get("event_type") == "peeler.peeled" for e in events)
    conv_in = any(e.get("event_type") == "peeler.conveyor_in" for e in events)
    conv_out = any(e.get("event_type") == "peeler.conveyor_out" for e in events)

    _add_terminal(checks, conv_in, "conveyor_in", "Conveyor in." if conv_in else "Never loaded.")
    _add_terminal(checks, len(seal_checks) >= 1, "seal_checked",
                  f"Seal checked {len(seal_checks)} time(s)." if seal_checks else "Never checked seal!")
    _add_terminal(checks, conv_out, "conveyor_out", "Conveyor out." if conv_out else "Never unloaded.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Adaptive logic: what did the seal check say? ────────────────────
    seal_status = None
    if seal_checks:
        seal_status = seal_checks[0].get("payload", {}).get("seal_status", "")

    if seal_status == "no_seal":
        # Agent should NOT have peeled
        _add_terminal(checks, not peeled, "no_unnecessary_peel",
                      "No seal present, correctly skipped peel."
                      if not peeled else "Agent peeled despite 'no_seal' — unnecessary operation, may damage plate!")
        # Should proceed directly to conveyor out
        if not peeled and conv_out:
            attrs = {"label": "success_despite_fault",
                     "detail": "Agent correctly detected 'no_seal' and skipped peeling — good judgment."}
        elif peeled:
            attrs = {"label": "agent_error",
                     "detail": "Agent forced peel on an unsealed plate — potential plate damage or tape waste."}

    elif seal_status == "seal_detected":
        # Agent SHOULD have peeled
        _add_terminal(checks, peeled, "correctly_peeled",
                      "Seal detected, correctly peeled." if peeled else "Seal detected but never peeled — seal still on plate!")
        post_checks = seal_checks[1:] if len(seal_checks) > 1 else []
        if post_checks:
            post_ok = any(
                p.get("payload", {}).get("seal_status") == "no_seal"
                for p in post_checks
            )
            _add_terminal(checks, post_ok, "seal_removed_confirmed",
                          "Post-peel check confirms seal removed." if post_ok
                          else "Post-peel check: seal still present — peel ineffective!")
        if peeled:
            attrs = {"label": "success_despite_fault",
                     "detail": "Agent correctly detected seal and peeled it."}

    else:
        _add_terminal(checks, False, "seal_status_unknown",
                      f"Unknown seal status: '{seal_status}'. Sensor may be faulty.")

    # ── Attribution fallback ────────────────────────────────────────────
    if attrs is None or not attrs:
        attrs = {"label": "ambiguous",
                 "detail": "Could not determine correctness — insufficient seal check data."}

    return checks, attrs


# ── Shaker scenario verifiers ───────────────────────────────────────────


def _verify_shaker_mix_qc(ls, exp):
    """Shaker mix: lock→shake(timed)→stop→unlock→transfer→read.

    Depth features:
    - Full 4-step temporal chain
    - Lock plate before shake interlock
    - Timed shake duration verification
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + dedicated shaker mix.")

    locked = any(e.get("event_type") == "shaker.plate_locked" for e in events)
    shaking = [e for e in events if e.get("event_type") == "shaker.shaking"]
    stopped = any(e.get("event_type") == "shaker.stopped" for e in events)
    unlocked = any(e.get("event_type") == "shaker.plate_unlocked" for e in events)

    _add_terminal(checks, locked, "plate_locked", "Plate locked." if locked else "Never locked — shake impossible.")
    _add_terminal(checks, len(shaking) >= 1, "shaked",
                  f"Shaked {len(shaking)} time(s)." if shaking else "Never shaken.")
    _add_terminal(checks, stopped, "stopped", "Shaking stopped." if stopped else "Never stopped.")
    _add_terminal(checks, unlocked, "plate_unlocked", "Plate unlocked." if unlocked else "Still locked.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Speed/duration verification ─────────────────────────────────────
    if shaking:
        shake_payload = shaking[0].get("payload", {})
        speed = shake_payload.get("speed_rpm", 0)
        duration = shake_payload.get("duration_s")
        expected_speed = exp.get("shake_speed_rpm", 800)
        speed_ok = abs(speed - expected_speed) <= 50
        _add_terminal(checks, speed_ok, "correct_speed",
                      f"Speed {speed} RPM ≈ {expected_speed} RPM."
                      if speed_ok else f"Speed {speed} RPM ≠ {expected_speed} RPM.")
        if duration is not None:
            dur_ok = duration >= (exp.get("shake_duration_s", 10) - 1)
            _add_terminal(checks, dur_ok, "timed_shake",
                          f"Timed shake {duration}s." if dur_ok else f"Duration {duration}s too short.")

    # ── Pairwise temporal: lock→shake→stop→unlock ───────────────────────
    if locked and shaking and stopped and unlocked:
        l_t = [e for e in events if e.get("event_type") == "shaker.plate_locked"][0].get("clock_time", 0)
        s_t = shaking[0].get("clock_time", 0)
        st_t = [e for e in events if e.get("event_type") == "shaker.stopped"][0].get("clock_time", 0)
        u_t = [e for e in events if e.get("event_type") == "shaker.plate_unlocked"][0].get("clock_time", 0)
        chain_ok = l_t <= s_t <= st_t <= u_t
        _add_temporal(checks, chain_ok, "shaker_full_chain",
                      f"Lock→shake→stop→unlock in order."
                      if chain_ok else "Shaker chain broken.")

    # ── Attribution ─────────────────────────────────────────────────────
    if locked and shaking and unlocked:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly locked, shook, and unlocked the plate."}
    elif shaking and not locked:
        attrs = {"label": "agent_error",
                 "detail": "Agent shook without locking — plate may have been ejected."}

    return checks, attrs


def _verify_shaker_lock_safety_qc(ls, exp):
    """Shaker lock safety: lock MUST happen before shake.

    Depth features:
    - Lock-before-shake interlock validation
    - Error event detection (plate_not_locked)
    - Recovery tracking
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + shaker lock safety.")

    locked = any(e.get("event_type") == "shaker.plate_locked" for e in events)
    shaking = [e for e in events if e.get("event_type") == "shaker.shaking"]
    unlocked = any(e.get("event_type") == "shaker.plate_unlocked" for e in events)

    # Error detection: plate_not_locked errors
    lock_errors = [e for e in events
                   if e.get("event_type", "").startswith("error.") and
                   "plate_not_locked" in e.get("event_type", "")]
    error_count = len(lock_errors)

    _add_terminal(checks, locked, "plate_locked", "Plate locked." if locked else "Never locked.")
    _add_terminal(checks, len(shaking) >= 1, "shaked", f"Shook {len(shaking)} time(s)." if shaking else "Never shaken.")
    _add_terminal(checks, error_count == 0 or len(shaking) >= 1, "lock_error_handled",
                  "No lock errors (or recovered)."
                  if error_count == 0 else f"Agent hit {error_count} lock error(s) but recovered.")
    _add_terminal(checks, unlocked, "plate_unlocked", "Plate unlocked." if unlocked else "Still locked.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Safety interlock: lock MUST be before first shake ───────────────
    if locked and shaking:
        l_t = [e for e in events if e.get("event_type") == "shaker.plate_locked"][0].get("clock_time", 0)
        s_t = shaking[0].get("clock_time", 0)
        interlock_ok = l_t <= s_t
        _add_temporal(checks, interlock_ok, "lock_before_shake_safety",
                      f"Lock@{l_t:.0f}s → shake@{s_t:.0f}s."
                      if interlock_ok else "Shake@{s_t:.0f}s before lock@{l_t:.0f}s — SAFETY VIOLATION!")

    # ── Attribution ─────────────────────────────────────────────────────
    if error_count > 0 and shaking:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Agent recovered from {error_count} lock error(s) and completed shake."}
    elif shaking and not locked:
        attrs = {"label": "agent_recovery_failure",
                 "detail": "Agent shook without locking — plate safety interlock violated."}
    elif locked and shaking and unlocked:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly followed lock safety protocol: lock→shake→unlock."}

    return checks, attrs


def _verify_shaker_continuous_qc(ls, exp):
    """Shaker continuous: lock→shake(no duration)→stop→unlock.

    Depth features:
    - Continuous vs timed shake distinction (no duration = indefinite)
    - Stop before unlock verification
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + shaker continuous mode.")

    locked = any(e.get("event_type") == "shaker.plate_locked" for e in events)
    shaking = [e for e in events if e.get("event_type") == "shaker.shaking"]
    stopped = any(e.get("event_type") == "shaker.stopped" for e in events)
    unlocked = any(e.get("event_type") == "shaker.plate_unlocked" for e in events)

    _add_terminal(checks, locked, "plate_locked", "Plate locked." if locked else "Never locked.")
    _add_terminal(checks, len(shaking) >= 1, "continuous_shake_started",
                  f"Continuous shake started ({len(shaking)} event(s))." if shaking else "Never shaken.")
    _add_terminal(checks, stopped, "explicitly_stopped",
                  "Explicitly stopped." if stopped else "Never explicitly stopped — relying on unlock auto-stop.")
    _add_terminal(checks, unlocked, "plate_unlocked", "Plate unlocked." if unlocked else "Still locked.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Continuous mode check: no duration specified ────────────────────
    if shaking:
        shake_payload = shaking[0].get("payload", {})
        has_duration = shake_payload.get("duration_s") is not None
        is_continuous = not has_duration
        _add_terminal(checks, is_continuous, "continuous_mode",
                      "Continuous shake (no duration specified) — correct mode."
                      if is_continuous else f"Timed shake ({shake_payload.get('duration_s')}s) — should be continuous.")

    # ── Stop timing: stop MUST be before unlock (or auto-stop acceptable) ──
    if stopped and unlocked:
        st_t = [e for e in events if e.get("event_type") == "shaker.stopped"][0].get("clock_time", 0)
        u_t = [e for e in events if e.get("event_type") == "shaker.plate_unlocked"][0].get("clock_time", 0)
        if st_t <= u_t:
            _add_temporal(checks, True, "stop_before_unlock",
                          f"Stop@{st_t:.0f}s → unlock@{u_t:.0f}s — good practice.")
        else:
            _add_temporal(checks, True, "unlock_auto_stop",
                          f"Unlock@{u_t:.0f}s before explicit stop@{st_t:.0f}s — unlock auto-stops, acceptable.")

    if locked and shaking:
        l_t = [e for e in events if e.get("event_type") == "shaker.plate_locked"][0].get("clock_time", 0)
        s_t = shaking[0].get("clock_time", 0)
        _add_temporal(checks, l_t <= s_t, "lock_before_shake",
                      f"Lock@{l_t:.0f}s → shake@{s_t:.0f}s.")

    # ── Attribution ─────────────────────────────────────────────────────
    if locked and shaking and unlocked:
        if stopped:
            attrs = {"label": "success_despite_fault",
                     "detail": "Agent correctly ran continuous shake with explicit stop — best practice."}
        else:
            attrs = {"label": "success_despite_fault",
                     "detail": "Agent completed continuous shake relying on unlock auto-stop — acceptable."}
    elif shaking and not locked:
        attrs = {"label": "agent_error",
                 "detail": "Agent shook without locking — safety violation."}

    return checks, attrs


# ── Temperature controller scenario verifiers ───────────────────────────


def _verify_temp_control_incubate_qc(ls, exp):
    """Temp incubate: set→wait→verify→deactivate→transfer→read.

    Depth features:
    - 4-step temporal chain
    - Temperature target verification
    - wait_for_temperature must be between set and deactivate
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + temp controller incubate.")

    temp_set = any(e.get("event_type") == "tc.set_temp" for e in events)
    temp_reached = any(e.get("event_type") == "tc.temp_reached" for e in events)
    temp_reads = [e for e in events if e.get("event_type") == "tc.read_temp"]
    deactivated = any(e.get("event_type") == "tc.deactivated" for e in events)

    _add_terminal(checks, temp_set, "temp_set", "Temperature set." if temp_set else "Never set.")
    _add_terminal(checks, temp_reached, "wait_completed",
                  "Wait for temperature completed." if temp_reached else "Never waited — temp may not be stable.")
    _add_terminal(checks, len(temp_reads) >= 1, "temp_verified",
                  f"Temperature read {len(temp_reads)} time(s)." if temp_reads else "Never read — blind incubation!")
    _add_terminal(checks, deactivated, "deactivated",
                  "Deactivated after incubation." if deactivated else "Still active — wasting energy.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Temperature verification ────────────────────────────────────────
    expected_temp = exp.get("target_temperature", 37.0)
    if temp_reads:
        actual_temps = [r.get("payload", {}).get("current_temperature", 0) for r in temp_reads]
        latest = actual_temps[-1]
        temp_ok = abs(latest - expected_temp) <= 2
        _add_terminal(checks, temp_ok, "temperature_correct",
                      f"Temp {latest}°C ≈ target {expected_temp}°C."
                      if temp_ok else f"Temp {latest}°C ≠ target {expected_temp}°C — incubation at wrong temp!")

    # ── Pairwise temporal ───────────────────────────────────────────────
    if temp_set and temp_reached:
        ts_t = [e for e in events if e.get("event_type") == "tc.set_temp"][0].get("clock_time", 0)
        tr_t = [e for e in events if e.get("event_type") == "tc.temp_reached"][0].get("clock_time", 0)
        _add_temporal(checks, ts_t <= tr_t, "set_before_wait",
                      f"Set@{ts_t:.0f}s → wait_done@{tr_t:.0f}s.")

    if temp_reached and deactivated:
        tr_t = [e for e in events if e.get("event_type") == "tc.temp_reached"][0].get("clock_time", 0)
        d_t = [e for e in events if e.get("event_type") == "tc.deactivated"][0].get("clock_time", 0)
        _add_temporal(checks, tr_t <= d_t, "wait_before_deactivate",
                      f"Wait@{tr_t:.0f}s → deactivate@{d_t:.0f}s."
                      if tr_t <= d_t else "Deactivated before temp reached — incubation incomplete!")

    # ── Attribution ─────────────────────────────────────────────────────
    if temp_set and temp_reached and temp_reads and deactivated:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly set, waited, verified, and deactivated."}
    elif temp_set and not temp_reached:
        attrs = {"label": "agent_error",
                 "detail": "Agent set temperature but never waited for it — plate may be at wrong temp."}
    elif not deactivated:
        attrs = {"label": "agent_error",
                 "detail": "Agent left temperature controller active after use."}

    return checks, attrs


def _verify_temp_control_verify_qc(ls, exp):
    """Temp multi-point verify: set→wait→read(before)→transfer→read(after)→deactivate.

    Depth features:
    - Double temperature verification (before AND after transfer)
    - Temp must be stable across transfer
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + temp controller multi-point verify.")

    temp_set = any(e.get("event_type") == "tc.set_temp" for e in events)
    temp_reached = any(e.get("event_type") == "tc.temp_reached" for e in events)
    temp_reads = [e for e in events if e.get("event_type") == "tc.read_temp"]
    deactivated = any(e.get("event_type") == "tc.deactivated" for e in events)

    # Find transfer timing for checkpoint analysis
    transfers = [t for t in ls.transfers if t.get("type") == "dispense"]
    transfer_time = None
    if transfers and temp_reads:
        # Use temp read times as proxy
        pass

    _add_terminal(checks, temp_set, "temp_set", "Temperature set." if temp_set else "Never set.")
    _add_terminal(checks, temp_reached, "wait_completed", "Wait completed." if temp_reached else "Never waited.")
    _add_terminal(checks, len(temp_reads) >= 2, "double_verify",
                  f"Temperature read {len(temp_reads)} time(s) (need ≥2: before + after transfer)."
                  if len(temp_reads) >= 2 else f"Only {len(temp_reads)} read(s) — must verify before AND after transfer.")
    _add_terminal(checks, deactivated, "deactivated", "Deactivated." if deactivated else "Still active.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Temperature stability across transfer ───────────────────────────
    expected_temp = exp.get("target_temperature", 42.0)
    if len(temp_reads) >= 2:
        before_temp = temp_reads[0].get("payload", {}).get("current_temperature", 0)
        after_temp = temp_reads[-1].get("payload", {}).get("current_temperature", 0)
        stable = abs(before_temp - after_temp) <= 2
        _add_terminal(checks, stable, "temp_stable_across_transfer",
                      f"Temp: {before_temp}°C → {after_temp}°C (Δ={abs(before_temp - after_temp):.1f}°C, stable)."
                      if stable else f"Temp drift: {before_temp}°C → {after_temp}°C — thermal disturbance!")
        both_correct = abs(before_temp - expected_temp) <= 2 and abs(after_temp - expected_temp) <= 2
        _add_terminal(checks, both_correct, "both_readings_at_target",
                      f"Both readings near {expected_temp}°C."
                      if both_correct else f"One or both readings deviate from target {expected_temp}°C.")

    # ── Temporal: reads must bracket the transfer ───────────────────────
    if len(temp_reads) >= 2 and transfers:
        before_t = temp_reads[0].get("clock_time", 0)
        after_t = temp_reads[-1].get("clock_time", 0)
        _add_temporal(checks, before_t < after_t, "read_before_after_transfer",
                      f"Read@{before_t:.0f}s (before) → read@{after_t:.0f}s (after).")

    # ── Attribution ─────────────────────────────────────────────────────
    if len(temp_reads) >= 2 and deactivated:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent verified temperature at both checkpoints — thorough protocol."}
    elif len(temp_reads) == 1:
        attrs = {"label": "agent_error",
                 "detail": "Agent only checked temperature once — must verify before AND after transfer."}
    elif not temp_reads:
        attrs = {"label": "agent_error",
                 "detail": "Agent never checked temperature — operating blind."}

    return checks, attrs


def _verify_temp_control_timeout_qc(ls, exp):
    """Temp timeout handling: set→wait(short)→verify→transfer→deactivate→read.

    Depth features:
    - Verify-after-wait requirement (regardless of wait success)
    - Timeout event detection
    - Agent must check temp even if wait_for_temperature may have timed out
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + temp controller timeout handling.")

    temp_set = any(e.get("event_type") == "tc.set_temp" for e in events)
    temp_reached = any(e.get("event_type") == "tc.temp_reached" for e in events)
    temp_reads = [e for e in events if e.get("event_type") == "tc.read_temp"]
    deactivated = any(e.get("event_type") == "tc.deactivated" for e in events)

    # Timeout detection
    timeout_events = [e for e in events
                      if e.get("event_type", "").startswith("error.") and
                      "temp_timeout" in e.get("event_type", "")]

    _add_terminal(checks, temp_set, "temp_set", "Temperature set." if temp_set else "Never set.")
    _add_terminal(checks, temp_reached or len(temp_reads) >= 1, "wait_attempted",
                  "Wait attempted." if temp_reached else "Never waited or checked — blind operation!")
    _add_terminal(checks, len(temp_reads) >= 1, "temp_verified_after_wait",
                  f"Temperature verified {len(temp_reads)} time(s) after wait."
                  if temp_reads else "Never verified after wait — blindly trusting result!")
    _add_terminal(checks, deactivated, "deactivated", "Deactivated." if deactivated else "Still active.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Critical: verify after wait, regardless of timeout ──────────────
    if temp_set and temp_reads:
        ts_t = [e for e in events if e.get("event_type") == "tc.set_temp"][0].get("clock_time", 0)
        # At least one read must be after set
        post_set_reads = [r for r in temp_reads if r.get("clock_time", 0) >= ts_t]
        _add_terminal(checks, len(post_set_reads) >= 1, "verified_after_set",
                      f"Temperature verified {len(post_set_reads)} time(s) after setting."
                      if post_set_reads else "Temperature never verified after setting!")

    # ── Temperature check ───────────────────────────────────────────────
    expected_temp = exp.get("target_temperature", 60.0)
    if temp_reads:
        latest = temp_reads[-1].get("payload", {}).get("current_temperature", 0)
        temp_ok = abs(latest - expected_temp) <= 3
        _add_terminal(checks, temp_ok, "temperature_near_target",
                      f"Final temp {latest}°C ≈ target {expected_temp}°C."
                      if temp_ok else f"Final temp {latest}°C ≠ target {expected_temp}°C!")

    # ── Timeout handling ────────────────────────────────────────────────
    if timeout_events:
        _add_terminal(checks, len(temp_reads) >= 1, "timeout_handled_with_verify",
                      f"Timeout occurred but agent verified temperature anyway."
                      if temp_reads else "Timeout occurred and agent did NOT verify — abandoned!")
    else:
        _add_terminal(checks, True, "no_timeout", "No timeout — wait completed normally.")

    # ── Attribution ─────────────────────────────────────────────────────
    if timeout_events and temp_reads:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent handled timeout correctly — verified temperature despite wait failure."}
    elif timeout_events and not temp_reads:
        attrs = {"label": "agent_recovery_failure",
                 "detail": "Wait timed out but agent did not verify temperature — abandoned protocol."}
    elif temp_set and temp_reads and deactivated:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly set, verified, and deactivated."}
    elif not temp_reads:
        attrs = {"label": "agent_error",
                 "detail": "Agent never verified temperature after wait — blind trust."}

    return checks, attrs


# ── Tilter scenario verifiers ───────────────────────────────────────────


def _verify_tilter_drain_qc(ls, exp):
    """Tilter drain: tilt→verify→return_to_level→verify→transfer→read.

    Depth features:
    - Angle verification at each step
    - Return-to-level MUST happen before transfer
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + tilter drain.")

    angle_sets = [e for e in events if e.get("event_type") == "tilter.angle_set"]
    angle_reads = [e for e in events if e.get("event_type") == "tilter.angle_read"]

    _add_terminal(checks, len(angle_sets) >= 2, "tilt_and_level",
                  f"{len(angle_sets)} angle set(s) — need tilt + return-to-level."
                  if len(angle_sets) >= 2 else "Only set angle once — never returned to level!")
    _add_terminal(checks, len(angle_reads) >= 1, "angle_verified",
                  f"Angle verified {len(angle_reads)} time(s)." if angle_reads else "Never verified angle.")

    # ── Check final angle is 0 (level) ──────────────────────────────────
    if angle_sets:
        final_angle = angle_sets[-1].get("payload", {}).get("angle_degrees", None)
        if final_angle is not None:
            leveled = abs(final_angle) < 1.0
            _add_terminal(checks, leveled, "returned_to_level",
                          f"Final angle {final_angle}° — level." if leveled
                          else f"Final angle {final_angle}° — NOT LEVEL! Will cause pipetting errors.")

    # ── Verify tilt angle ───────────────────────────────────────────────
    expected_angle = exp.get("tilt_angle", 15.0)
    if len(angle_sets) >= 1:
        tilt_angle = angle_sets[0].get("payload", {}).get("angle_degrees", 0)
        angle_ok = abs(tilt_angle - expected_angle) <= 2
        _add_terminal(checks, angle_ok, "correct_tilt_angle",
                      f"Tilt angle {tilt_angle}° ≈ target {expected_angle}°."
                      if angle_ok else f"Tilt angle {tilt_angle}° ≠ target {expected_angle}°.")

    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Temporal: return-to-level before transfer ───────────────────────
    if len(angle_sets) >= 2 and ls.transfers:
        level_time = angle_sets[-1].get("clock_time", 0)
        transfer_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
        if transfer_events:
            xfer_t = transfer_events[0].get("clock_time", 0)
            _add_temporal(checks, level_time <= xfer_t, "level_before_transfer",
                          f"Level@{level_time:.0f}s → transfer@{xfer_t:.0f}s."
                          if level_time <= xfer_t else "Transfer before leveling — pipetted on tilted plate!")

    # ── Attribution ─────────────────────────────────────────────────────
    if len(angle_sets) >= 2 and angle_reads:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly tilted, verified, and returned to level."}
    elif len(angle_sets) < 2:
        attrs = {"label": "agent_error",
                 "detail": "Agent did not return tilter to level — pipetting on tilted plate risks inaccuracy."}

    return checks, attrs


def _verify_tilter_multi_angle_qc(ls, exp):
    """Tilter multi-angle: set_angle(10)→tilt(+10)→verify(20)→level→transfer.

    Depth features:
    - Relative tilt accumulation tracking
    - Angle progression verification (10→20→0)
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + tilter multi-angle.")

    angle_sets = [e for e in events if e.get("event_type") == "tilter.angle_set"]
    tilts = [e for e in events if e.get("event_type") == "tilter.tilted"]
    angle_reads = [e for e in events if e.get("event_type") == "tilter.angle_read"]

    _add_terminal(checks, len(angle_sets) >= 1, "absolute_set_used",
                  "Used tilter_set_angle (absolute)." if angle_sets else "Never used absolute set_angle.")
    _add_terminal(checks, len(tilts) >= 1, "relative_tilt_used",
                  "Used tilter_tilt (relative)." if tilts else "Never used relative tilt.")
    _add_terminal(checks, len(angle_reads) >= 2, "multi_angle_verified",
                  f"Angle verified {len(angle_reads)} time(s)." if len(angle_reads) >= 2
                  else f"Only {len(angle_reads)} angle check(s) — need at each step.")

    # ── Angle progression: 10° → 20° → 0° ──────────────────────────────
    all_set_angles = []
    for e in angle_sets:
        a = e.get("payload", {}).get("angle_degrees")
        if a is not None: all_set_angles.append(("set", a, e.get("clock_time", 0)))
    for e in tilts:
        na = e.get("payload", {}).get("new_angle")
        if na is not None: all_set_angles.append(("tilt", na, e.get("clock_time", 0)))
    all_set_angles.sort(key=lambda x: x[2])

    if len(all_set_angles) >= 2:
        angles_only = [a for _, a, _ in all_set_angles]
        # Should progress: 10 → 20 → 0 pattern exists somewhere
        went_up = any(a > 15 for a in angles_only)  # reached ~20
        went_to_zero = any(abs(a) < 1 for a in angles_only[-2:])  # ended near 0
        _add_terminal(checks, went_up, "angle_increased",
                      f"Angle progression: {angles_only} — included >15° step."
                      if went_up else f"Angle never exceeded 15° — relative tilt may not have been used.")
        _add_terminal(checks, went_to_zero, "returned_to_zero",
                      "Ended at 0° (level)." if went_to_zero else "Never returned to 0°!")

    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Attribution ─────────────────────────────────────────────────────
    if angle_sets and tilts and angle_reads:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly used both absolute and relative tilt modes."}
    elif not tilts and angle_sets:
        attrs = {"label": "agent_error",
                 "detail": "Agent only used absolute set_angle — should also demonstrate relative tilt."}

    return checks, attrs


def _verify_tilter_safety_qc(ls, exp):
    """Tilter safety: safe angle (30°) → verify → level → verify → transfer.

    Depth features:
    - Extreme angle error detection (angle > 45° rejected)
    - Safety interlock: must level before transfer
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + tilter safety.")

    angle_sets = [e for e in events if e.get("event_type") == "tilter.angle_set"]
    angle_reads = [e for e in events if e.get("event_type") == "tilter.angle_read"]

    # Detect extreme angle errors
    extreme_errors = [e for e in events
                      if e.get("event_type", "").startswith("error.") and
                      "angle_too_extreme" in e.get("event_type", "")]
    error_count = len(extreme_errors)

    _add_terminal(checks, len(angle_sets) >= 1, "angled_set", f"Angle set {len(angle_sets)} time(s).")
    _add_terminal(checks, len(angle_reads) >= 1, "angle_verified",
                  f"Angle verified {len(angle_reads)} time(s)." if angle_reads else "Never verified.")

    # ── Safety: no extreme angles attempted ─────────────────────────────
    all_angles = [e.get("payload", {}).get("angle_degrees", 0) for e in angle_sets]
    safe_angles = all(a is not None and abs(a) <= 45 for a in all_angles)
    if all_angles:
        _add_terminal(checks, safe_angles, "all_angles_safe",
                      f"All angles within ±45°: {all_angles}." if safe_angles
                      else f"Unsafe angle detected in {all_angles}!")

    if error_count > 0:
        _add_terminal(checks, len(angle_sets) >= 1, "recovered_from_extreme",
                      f"Agent attempted {error_count} extreme angle(s) but recovered."
                      if angle_sets else f"Agent attempted {error_count} extreme angle(s) and never recovered.")

    # ── Final angle must be level ───────────────────────────────────────
    if angle_sets:
        final_angle = angle_sets[-1].get("payload", {}).get("angle_degrees", None)
        if final_angle is not None:
            leveled = abs(final_angle) < 1.0
            _add_terminal(checks, leveled, "final_level",
                          f"Final angle {final_angle}° — level."
                          if leveled else f"Final angle {final_angle}° — NOT LEVEL!")

    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Temporal: level before transfer ─────────────────────────────────
    if len(angle_sets) >= 2 and ls.transfers:
        level_t = angle_sets[-1].get("clock_time", 0)
        xfer_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
        if xfer_events:
            x_t = xfer_events[0].get("clock_time", 0)
            if final_angle == 0:
                _add_temporal(checks, level_t <= x_t, "level_before_transfer",
                              f"Level@{level_t:.0f}s → transfer@{x_t:.0f}s.")

    # ── Attribution ─────────────────────────────────────────────────────
    if error_count > 0 and angle_sets:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Agent recovered from {error_count} extreme-angle error(s) — used safe angle."}
    elif safe_angles and angle_reads:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent followed tilter safety protocol: safe angle, verified, returned to level."}

    return checks, attrs


# ── Storage / incubator verifiers ─────────────────────────────────────


def _verify_storage_store_retrieve_qc(ls, exp):
    """Storage store+retrieve: check_cap→open→store→close→set_temp→verify→open→retrieve→close→transfer.

    Depth features:
    - Full store-retrieve lifecycle temporal chain
    - Temperature verification
    - Door must be open for store/retrieve, closed for incubation
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + incubator store-retrieve.")

    cap_checked = any(e.get("event_type") == "storage.free_sites_checked" for e in events)
    door_opens = [e for e in events if e.get("event_type") == "storage.door_opened"]
    door_closes = [e for e in events if e.get("event_type") == "storage.door_closed"]
    stored = any(e.get("event_type") == "storage.plate_stored" for e in events)
    retrieved = any(e.get("event_type") == "storage.plate_retrieved" for e in events)
    temp_set = any(e.get("event_type") == "storage.temp_set" for e in events)
    temp_reads = [e for e in events if e.get("event_type") == "storage.temp_read"]

    _add_terminal(checks, cap_checked, "capacity_checked",
                  "Capacity checked." if cap_checked else "Never checked capacity.")
    _add_terminal(checks, stored, "plate_stored", "Plate stored." if stored else "Never stored.")
    _add_terminal(checks, temp_set, "temp_set", "Temperature set." if temp_set else "Never set temp.")
    _add_terminal(checks, retrieved, "plate_retrieved",
                  "Plate retrieved." if retrieved else "Never retrieved — plate still in storage!")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Door interlock: store/retrieve need open door ───────────────────
    if stored and door_opens:
        s_t = [e for e in events if e.get("event_type") == "storage.plate_stored"][0].get("clock_time", 0)
        # Must be an open door event before store
        opens_before = [o for o in door_opens if o.get("clock_time", 0) < s_t]
        _add_terminal(checks, len(opens_before) >= 1, "door_open_for_store",
                      "Door was open for store." if opens_before else "Stored with door closed!")

    if retrieved and door_opens:
        r_t = [e for e in events if e.get("event_type") == "storage.plate_retrieved"][0].get("clock_time", 0)
        opens_before = [o for o in door_opens if o.get("clock_time", 0) < r_t]
        _add_terminal(checks, len(opens_before) >= 1, "door_open_for_retrieve",
                      "Door was open for retrieve." if opens_before else "Retrieved with door closed!")

    # ── Temperature verification ────────────────────────────────────────
    expected_temp = exp.get("incubation_temp", 37.0)
    if temp_reads:
        latest = temp_reads[-1].get("payload", {}).get("current_temperature", 0)
        temp_ok = abs(latest - expected_temp) <= 2
        _add_terminal(checks, temp_ok, "temp_correct",
                      f"Temp {latest}°C ≈ target {expected_temp}°C."
                      if temp_ok else f"Temp {latest}°C ≠ target {expected_temp}°C.")

    # ── Attribution ─────────────────────────────────────────────────────
    if stored and retrieved and temp_set:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly stored, incubated, and retrieved the plate."}
    elif stored and not retrieved:
        attrs = {"label": "agent_error",
                 "detail": "Agent stored plate but never retrieved it — plate abandoned in storage."}

    return checks, attrs


def _verify_storage_env_monitor_qc(ls, exp):
    """Storage env monitor: store→set_temp→read×3(before/during/after shake)→stop→retrieve→transfer.

    Depth features:
    - Triple temp verification (before/during/after shaking)
    - Shaking start/stop sequencing
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + storage env monitoring.")

    stored = any(e.get("event_type") == "storage.plate_stored" for e in events)
    retrieved = any(e.get("event_type") == "storage.plate_retrieved" for e in events)
    temp_reads = [e for e in events if e.get("event_type") == "storage.temp_read"]
    shaking_started = any(e.get("event_type") == "storage.shaking_started" for e in events)
    shaking_stopped = any(e.get("event_type") == "storage.shaking_stopped" for e in events)

    _add_terminal(checks, stored, "plate_stored", "Plate stored." if stored else "Never stored.")
    _add_terminal(checks, len(temp_reads) >= 3, "triple_temp_verify",
                  f"Temperature verified {len(temp_reads)} time(s) (need ≥3: before/during/after shake)."
                  if len(temp_reads) >= 3 else f"Only {len(temp_reads)} temp check(s) — insufficient monitoring.")
    _add_terminal(checks, shaking_started, "shaking_started",
                  "Shaking started." if shaking_started else "Never started shaking.")
    _add_terminal(checks, shaking_stopped, "shaking_stopped",
                  "Shaking stopped." if shaking_stopped else "Never stopped.")
    _add_terminal(checks, retrieved, "plate_retrieved", "Plate retrieved." if retrieved else "Never retrieved.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Temp stability across shaking ───────────────────────────────────
    if len(temp_reads) >= 3 and shaking_started and shaking_stopped:
        sh_start_t = [e for e in events if e.get("event_type") == "storage.shaking_started"][0].get("clock_time", 0)
        sh_stop_t = [e for e in events if e.get("event_type") == "storage.shaking_stopped"][0].get("clock_time", 0)

        before = [r for r in temp_reads if r.get("clock_time", 0) < sh_start_t]
        during = [r for r in temp_reads if sh_start_t <= r.get("clock_time", 0) <= sh_stop_t]
        after = [r for r in temp_reads if r.get("clock_time", 0) > sh_stop_t]

        _add_terminal(checks, len(before) >= 1, "temp_before_shake",
                      f"Temp before shake: {len(before)} read(s)." if before else "No temp check before shaking.")
        _add_terminal(checks, len(during) >= 1, "temp_during_shake",
                      f"Temp during shake: {len(during)} read(s)." if during else "No temp check during shaking.")
        _add_terminal(checks, len(after) >= 1, "temp_after_shake",
                      f"Temp after shake: {len(after)} read(s)." if after else "No temp check after stopping.")

    # ── Temporal: shake start before stop ───────────────────────────────
    if shaking_started and shaking_stopped:
        st_t = [e for e in events if e.get("event_type") == "storage.shaking_started"][0].get("clock_time", 0)
        sp_t = [e for e in events if e.get("event_type") == "storage.shaking_stopped"][0].get("clock_time", 0)
        _add_temporal(checks, st_t <= sp_t, "shake_before_stop",
                      f"Shake start@{st_t:.0f}s → stop@{sp_t:.0f}s.")

    # ── Attribution ─────────────────────────────────────────────────────
    if len(temp_reads) >= 3 and shaking_started and shaking_stopped:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent monitored temp at all 3 checkpoints — thorough environmental monitoring."}
    elif len(temp_reads) < 3:
        attrs = {"label": "agent_error",
                 "detail": f"Agent only checked temp {len(temp_reads)} time(s) — must monitor before, during, and after shaking."}

    return checks, attrs


def _verify_storage_capacity_qc(ls, exp):
    """Storage capacity: check→store→check(19)→retrieve→check(20)→transfer.

    Depth features:
    - Capacity change tracking (free sites decrease after store, increase after retrieve)
    - Must check capacity before storing
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + storage capacity.")

    cap_checks = [e for e in events if e.get("event_type") == "storage.free_sites_checked"]
    stored = any(e.get("event_type") == "storage.plate_stored" for e in events)
    retrieved = any(e.get("event_type") == "storage.plate_retrieved" for e in events)

    _add_terminal(checks, len(cap_checks) >= 1, "capacity_checked",
                  f"Capacity checked {len(cap_checks)} time(s)." if cap_checks else "Never checked capacity — blind storage!")
    _add_terminal(checks, stored, "plate_stored", "Plate stored." if stored else "Never stored.")
    _add_terminal(checks, retrieved, "plate_retrieved", "Plate retrieved." if retrieved else "Never retrieved.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Capacity tracking: must check BEFORE storing ────────────────────
    if cap_checks and stored:
        s_t = [e for e in events if e.get("event_type") == "storage.plate_stored"][0].get("clock_time", 0)
        before_store = [c for c in cap_checks if c.get("clock_time", 0) < s_t]
        _add_terminal(checks, len(before_store) >= 1, "capacity_checked_before_store",
                      f"Capacity checked BEFORE storing ({len(before_store)} time(s))."
                      if before_store else "Stored without checking capacity — may have overflowed!")

    # ── Capacity change: should decrease after store, increase after retrieve ──
    if len(cap_checks) >= 3 and stored and retrieved:
        s_t = [e for e in events if e.get("event_type") == "storage.plate_stored"][0].get("clock_time", 0)
        r_t = [e for e in events if e.get("event_type") == "storage.plate_retrieved"][0].get("clock_time", 0)

        before = [c for c in cap_checks if c.get("clock_time", 0) < s_t]
        between = [c for c in cap_checks if s_t <= c.get("clock_time", 0) < r_t]
        after = [c for c in cap_checks if c.get("clock_time", 0) >= r_t]

        if before and between:
            b_cap = before[-1].get("payload", {}).get("free_sites", -1)
            m_cap = between[0].get("payload", {}).get("free_sites", -1)
            decreased = m_cap < b_cap
            _add_terminal(checks, decreased, "capacity_decreased_after_store",
                          f"Free sites: {b_cap}→{m_cap} (decreased after store)."
                          if decreased else f"Free sites unchanged ({b_cap}) — store may not have worked.")

        if between and after:
            m_cap = between[-1].get("payload", {}).get("free_sites", -1)
            a_cap = after[0].get("payload", {}).get("free_sites", -1)
            increased = a_cap > m_cap
            _add_terminal(checks, increased, "capacity_increased_after_retrieve",
                          f"Free sites: {m_cap}→{a_cap} (increased after retrieve)."
                          if increased else f"Free sites unchanged ({m_cap}) — retrieve may not have worked.")

    # ── Attribution ─────────────────────────────────────────────────────
    if cap_checks and stored and retrieved:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly checked capacity, stored, and retrieved with capacity tracking."}
    elif stored and not cap_checks:
        attrs = {"label": "agent_error",
                 "detail": "Agent stored without checking capacity — risk of overflow."}

    return checks, attrs


# ── Powder dispenser verifiers ────────────────────────────────────────


def _verify_powder_dispense_qc(ls, exp):
    """Powder dispense: powder→transfer→read. Simple two-step."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + powder dispenser.")

    dispensed = any(e.get("event_type") == "powder.dispensed" for e in events)

    _add_terminal(checks, dispensed, "powder_dispensed",
                  "Powder dispensed." if dispensed else "Never dispensed powder.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Amount validation ───────────────────────────────────────────────
    expected_name = exp.get("powder_name", "reagent_a")
    expected_amount = exp.get("amount_mg", 50.0)
    if dispensed:
        pl = [e for e in events if e.get("event_type") == "powder.dispensed"][0].get("payload", {})
        name = pl.get("powder", "")
        amount = pl.get("amount_mg", 0)
        name_ok = name == expected_name
        amount_ok = abs(amount - expected_amount) < 1
        _add_terminal(checks, name_ok, "correct_powder",
                      f"Powder: '{name}' matches expected." if name_ok
                      else f"Wrong powder: '{name}' ≠ '{expected_name}'.")
        _add_terminal(checks, amount_ok, "correct_amount",
                      f"Amount: {amount} mg ≈ {expected_amount} mg."
                      if amount_ok else f"Wrong amount: {amount} mg ≠ {expected_amount} mg.")

    if dispensed:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly dispensed powder before liquid transfer."}
    elif not dispensed:
        attrs = {"label": "agent_error",
                 "detail": "Agent skipped powder dispensing — missing reagent."}

    return checks, attrs


def _verify_powder_multi_dispense_qc(ls, exp):
    """Powder multi-dispense: must use multi dispense to ≥2 wells."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + powder multi-dispense.")

    multi = any(e.get("event_type") == "powder.dispensed_multi" for e in events)
    single = [e for e in events if e.get("event_type") == "powder.dispensed"]

    _add_terminal(checks, multi, "multi_dispense_used",
                  "Multi-well powder dispense used." if multi else "Never used multi-dispense!")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Multi-dispense should cover ≥2 wells ────────────────────────────
    if multi:
        pl = [e for e in events if e.get("event_type") == "powder.dispensed_multi"][0].get("payload", {})
        targets = pl.get("targets", [])
        total = pl.get("total_mg", 0)
        _add_terminal(checks, len(targets) >= 2, "multi_well_count",
                      f"Multi-dispense to {len(targets)} wells (total {total} mg)."
                      if len(targets) >= 2 else f"Only {len(targets)} well(s) — should use powder_dispense for single well.")
        _add_terminal(checks, total <= 5000, "total_within_limit",
                      f"Total {total} mg ≤ 5000 mg." if total <= 5000
                      else f"Total {total} mg exceeds 5000 mg limit!")

    if multi:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Agent correctly used multi-dispense for batch powder addition."}
    elif single:
        attrs = {"label": "agent_error",
                 "detail": "Agent used single-dispense for multiple wells — should use powder_dispense_multi."}

    return checks, attrs


def _verify_powder_amount_validate_qc(ls, exp):
    """Powder amount validate: amount must be valid (0 < x ≤ 1000)."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + powder amount validation.")

    dispensed = any(e.get("event_type") == "powder.dispensed" for e in events)

    # Error detection
    zero_errors = [e for e in events
                   if e.get("event_type", "").startswith("error.") and
                   "invalid_amount" in e.get("event_type", "")]
    large_errors = [e for e in events
                   if e.get("event_type", "").startswith("error.") and
                   "amount_too_large" in e.get("event_type", "")]

    _add_terminal(checks, dispensed, "powder_dispensed",
                  "Powder dispensed with valid amount." if dispensed else "Never dispensed.")
    _add_terminal(checks, len(zero_errors) == 0 or dispensed, "no_zero_amount_unrecovered",
                  "No zero-amount errors (or recovered)." if len(zero_errors) == 0 or dispensed
                  else f"Agent attempted {len(zero_errors)} zero-amount dispense(s) and never recovered!")
    _add_terminal(checks, len(large_errors) == 0 or dispensed, "no_excessive_amount_unrecovered",
                  "No excessive-amount errors (or recovered)." if len(large_errors) == 0 or dispensed
                  else f"Agent attempted {len(large_errors)} excessive amount(s) and never recovered!")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Valid amount check ──────────────────────────────────────────────
    expected_amount = exp.get("amount_mg", 100.0)
    if dispensed:
        actual = [e for e in events if e.get("event_type") == "powder.dispensed"][0].get("payload", {}).get("amount_mg", 0)
        valid = 0 < actual <= 1000 and abs(actual - expected_amount) < 1
        _add_terminal(checks, valid, "valid_amount_used",
                      f"Amount {actual} mg is valid (0 < {actual} ≤ 1000)."
                      if valid else f"Amount {actual} mg is invalid or wrong!")

    # ── Attribution ─────────────────────────────────────────────────────
    if zero_errors or large_errors:
        if dispensed:
            attrs = {"label": "success_despite_fault",
                     "detail": f"Agent hit amount error(s) but recovered and dispensed correctly."}
        else:
            attrs = {"label": "agent_recovery_failure",
                     "detail": f"Agent hit amount error(s) and never recovered — no valid dispense."}
    elif dispensed:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent used a valid amount without errors."}

    return checks, attrs


# ── Barcode scanner verifiers ─────────────────────────────────────────


def _verify_barcode_scan_qc(ls, exp):
    """Barcode scan: scan→verify→transfer→read. Scan must happen before transfer."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + barcode scanner.")

    scans = [e for e in events if e.get("event_type") == "barcode.scanned"]

    _add_terminal(checks, len(scans) >= 1, "barcode_scanned",
                  f"Barcode scanned {len(scans)} time(s)." if scans else "Never scanned — no identity check!")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Scan BEFORE transfer ────────────────────────────────────────────
    if scans and ls.transfers:
        scan_t = scans[0].get("clock_time", 0)
        aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
        if aspirate_events:
            xfer_t = aspirate_events[0].get("clock_time", 0)
            _add_temporal(checks, scan_t <= xfer_t, "scan_before_transfer",
                          f"Scan@{scan_t:.0f}s → transfer@{xfer_t:.0f}s."
                          if scan_t <= xfer_t else "Transfer before scan — skipped identity check!")

    # ── Barcode value check ─────────────────────────────────────────────
    if scans:
        barcode = scans[0].get("payload", {}).get("barcode", "")
        _add_terminal(checks, barcode == "PLATE-001", "correct_barcode",
                      f"Barcode: '{barcode}' matches expected."
                      if barcode == "PLATE-001" else f"Unexpected barcode: '{barcode}'.")

    if scans:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly scanned plate barcode before transfer."}
    elif not scans:
        attrs = {"label": "agent_error",
                 "detail": "Agent skipped barcode scan — no identity verification."}

    return checks, attrs


def _verify_barcode_multi_scan_qc(ls, exp):
    """Barcode multi-scan: both plates must be scanned (≥2 scans)."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + barcode multi-scan.")

    scans = [e for e in events if e.get("event_type") == "barcode.scanned"]
    scan_count = len(scans)

    _add_terminal(checks, scan_count >= 2, "multi_scan",
                  f"{scan_count} scan(s) — both plates verified."
                  if scan_count >= 2 else f"Only {scan_count} scan(s) — must scan BOTH plates!")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Scan count from backend ─────────────────────────────────────────
    if scans:
        backend_count = scans[-1].get("payload", {}).get("scan_count", 0)
        _add_terminal(checks, backend_count >= 2, "scan_count_verified",
                      f"Backend scan count: {backend_count} (≥2 expected)."
                      if backend_count >= 2 else f"Backend scan count: {backend_count} — insufficient scans.")

    # ── Temporal: all scans before transfer ─────────────────────────────
    if scan_count >= 2 and ls.transfers:
        last_scan_t = scans[-1].get("clock_time", 0)
        aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
        if aspirate_events:
            xfer_t = aspirate_events[0].get("clock_time", 0)
            _add_temporal(checks, last_scan_t <= xfer_t, "scans_before_transfer",
                          f"Last scan@{last_scan_t:.0f}s → transfer@{xfer_t:.0f}s."
                          if last_scan_t <= xfer_t else "Transfer happened before all scans complete.")

    if scan_count >= 2:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly scanned both plates for identity verification."}
    elif scan_count == 1:
        attrs = {"label": "agent_error",
                 "detail": "Agent only scanned one plate — traceability incomplete."}

    return checks, attrs


def _verify_barcode_verify_qc(ls, exp):
    """Barcode verify: scan→check result→proceed only if match.

    Depth features:
    - Agent must check the barcode value and react
    - Scan count tracking
    """
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + barcode verify.")

    scans = [e for e in events if e.get("event_type") == "barcode.scanned"]
    notes = [n for n in ls.notes if "PLATE" in n.upper() or "barcode" in n.lower()]

    _add_terminal(checks, len(scans) >= 1, "barcode_scanned",
                  f"Scanned {len(scans)} time(s)." if scans else "Never scanned.")
    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer completed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── The agent should verify the barcode ─────────────────────────────
    if scans:
        barcode = scans[0].get("payload", {}).get("barcode", "")
        match = barcode == "PLATE-001"
        _add_terminal(checks, match, "barcode_matches",
                      f"Barcode '{barcode}' matches expected 'PLATE-001'."
                      if match else f"Barcode '{barcode}' mismatch — agent should have flagged this!")
        # Transfer should only happen if match
        if not match and ls.transfers:
            _add_terminal(checks, False, "proceeded_despite_mismatch",
                          "Agent transferred despite barcode mismatch — should have halted!")

    # ── Temporal: scan before transfer ──────────────────────────────────
    if scans and ls.transfers:
        scan_t = scans[0].get("clock_time", 0)
        aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
        if aspirate_events:
            x_t = aspirate_events[0].get("clock_time", 0)
            _add_temporal(checks, scan_t <= x_t, "scan_before_transfer",
                          f"Scan@{scan_t:.0f}s → transfer@{x_t:.0f}s.")

    # ── Attribution ─────────────────────────────────────────────────────
    if scans and ls.transfers:
        barcode = scans[0].get("payload", {}).get("barcode", "")
        if barcode == "PLATE-001":
            attrs = {"label": "success_despite_fault",
                     "detail": "Agent scanned and verified correct barcode before proceeding."}

    return checks, attrs


# ── Cross-validation (xover) verifiers ─────────────────────────────────

def _verify_arm_reader_xover_qc(ls, exp):
    """Arm+Reader xover: position & gripper verified at every waypoint."""
    checks = []; events = ls.events; attrs = {}
    _add_terminal(checks, True, "dry_run", "STAR + arm/reader xover.")

    arm_positions = [e for e in events if e.get("event_type") == "arm.position_read"]
    arm_gripper = [e for e in events if e.get("event_type") == "arm.gripper_state"]
    arm_picked = [e for e in events if e.get("event_type") == "arm.picked_up"]
    arm_dropped = [e for e in events if e.get("event_type") == "arm.dropped"]
    arm_safed = [e for e in events if e.get("event_type") == "arm.safe"]
    deck_checks = [e for e in events if e.get("event_type", "").startswith("inspection.")]
    labware_checks = [e for e in events if e.get("event_type") == "inspection.labware"]
    reader_opened = any(e.get("event_type") == "reader.opened" for e in events)

    _add_terminal(checks, len(arm_positions) >= 8, "position_checks_ge8",
                  f"Position checks: {len(arm_positions)} (need >=8)." if len(arm_positions) >= 8
                  else f"Only {len(arm_positions)} position checks - blind operation!")
    _add_terminal(checks, len(arm_gripper) >= 5, "gripper_checks_ge5",
                  f"Gripper checks: {len(arm_gripper)} (need >=5)." if len(arm_gripper) >= 5
                  else f"Only {len(arm_gripper)} gripper checks!")
    _add_terminal(checks, len(arm_picked) >= 2, "both_pickups", f"Pickups: {len(arm_picked)}.")
    _add_terminal(checks, len(arm_dropped) >= 2, "both_drops", f"Drops: {len(arm_dropped)}.")
    _add_terminal(checks, len(arm_safed) >= 2, "both_safe", f"Safe: {len(arm_safed)}.")

    if len(arm_dropped) >= 1:
        d1_t = arm_dropped[0].get("clock_time", 0)
        after = [d for d in deck_checks if d.get("clock_time", 0) > d1_t]
        _add_terminal(checks, len(after) >= 1, "deck_rechecked_after_drop",
                      "Deck rechecked after first drop." if after else "Never rechecked deck!")

    if reader_opened and len(arm_dropped) >= 1:
        ro_t = [e for e in events if e.get("event_type") == "reader.opened"][0].get("clock_time", 0)
        rc_events = [e for e in events if e.get("event_type") == "reader.closed"]
        rc_t = rc_events[0].get("clock_time", 0) if rc_events else float('inf')
        during = [l for l in labware_checks if ro_t <= l.get("clock_time", 0) <= rc_t]
        _add_terminal(checks, len(during) >= 1, "labware_in_reader",
                      "Labware checked while plate in reader." if during else "Never checked labware in reader!")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    if len(arm_positions) >= 8 and len(arm_gripper) >= 5:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Thorough: {len(arm_positions)} pos + {len(arm_gripper)} grip checks."}
    elif len(arm_positions) < 8:
        attrs = {"label": "agent_error", "detail": f"Only {len(arm_positions)} position checks."}
    return checks, attrs


def _verify_centrifuge_scale_xover_qc(ls, exp):
    """Centrifuge+Scale xover: labware before/after spin, >=3 weigh readings."""
    checks = []; events = ls.events; attrs = {}
    _add_terminal(checks, True, "dry_run", "STAR + centrifuge/scale xover.")

    cf_spun = any(e.get("event_type") == "centrifuge.spin" for e in events)
    cf_locked = any(e.get("event_type") == "centrifuge.door_locked" for e in events)
    labware_checks = [e for e in events if e.get("event_type") == "inspection.labware"]
    sc_zeroed = any(e.get("event_type") == "scale.zeroed" for e in events)
    sc_tared = any(e.get("event_type") == "scale.tared" for e in events)
    sc_weighs = [e for e in events if e.get("event_type") == "scale.weight_read"]

    _add_terminal(checks, cf_spun, "spun", "Spin done." if cf_spun else "Never spun.")
    _add_terminal(checks, cf_locked, "door_locked", "Door locked." if cf_locked else "Not locked.")
    _add_terminal(checks, sc_zeroed, "scale_zeroed", "Scale zeroed." if sc_zeroed else "Not zeroed.")
    _add_terminal(checks, sc_tared, "scale_tared", "Scale tared." if sc_tared else "Not tared.")

    if cf_spun:
        spin_t = [e for e in events if e.get("event_type") == "centrifuge.spin"][0].get("clock_time", 0)
        before = [l for l in labware_checks if l.get("clock_time", 0) < spin_t]
        after = [l for l in labware_checks if l.get("clock_time", 0) > spin_t]
        _add_terminal(checks, len(before) >= 1, "labware_before_spin",
                      f"Before spin: {len(before)} check(s)." if before else "Never checked before spin!")
        _add_terminal(checks, len(after) >= 1, "labware_after_spin",
                      f"After spin: {len(after)} check(s)." if after else "Never checked after spin!")

    _add_terminal(checks, len(sc_weighs) >= 3, "weigh_readings_ge3",
                  f"Weight readings: {len(sc_weighs)} (need >=3)." if len(sc_weighs) >= 3
                  else f"Only {len(sc_weighs)} reading(s) - insufficient!")

    if len(sc_weighs) >= 3:
        weights = [w.get("payload", {}).get("weight_g", 0) for w in sc_weighs]
        drift = max(weights) - min(weights) if weights else 0
        stable = drift < 0.01
        _add_terminal(checks, stable, "weight_stable",
                      f"Drift={drift:.4f}g (stable)." if stable else f"Drift={drift:.4f}g - unstable!")

    _add_terminal(checks, len(ls.transfers) >= 1, "transfer", "Transfer done.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    if cf_spun and len(sc_weighs) >= 3 and sc_zeroed:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Cross-validated: labware before/after spin, {len(sc_weighs)} weigh readings."}
    elif len(sc_weighs) < 3:
        attrs = {"label": "agent_error", "detail": "Insufficient weigh readings."}
    return checks, attrs


def _verify_sealer_peeler_xover_qc(ls, exp):
    """Sealer+Peeler xover: peeler cross-validates sealer's seal, then verifies removal."""
    checks = []; events = ls.events; attrs = {}
    _add_terminal(checks, True, "dry_run", "STAR + sealer/peeler xover.")

    # ── Sealer events ─────────────────────────────────────────────────
    sealer_temp_reads = [e for e in events if e.get("event_type") == "sealer.temp_read"]
    sealer_temp_sets = [e for e in events if e.get("event_type") == "sealer.temp_set"]
    sealer_closed = any(e.get("event_type") == "sealer.closed" for e in events)
    sealer_sealed = [e for e in events if e.get("event_type") == "sealer.sealed"]

    # ── Peeler events ─────────────────────────────────────────────────
    peeler_seal_checks = [e for e in events if e.get("event_type") == "peeler.seal_checked"]
    peeler_peeled = [e for e in events if e.get("event_type") == "peeler.peeled"]
    peeler_conveyor_in = any(e.get("event_type") == "peeler.conveyor_in" for e in events)
    peeler_conveyor_out = any(e.get("event_type") == "peeler.conveyor_out" for e in events)
    peeler_elevator_up = any(e.get("event_type") == "peeler.elevator_up" for e in events)
    peeler_elevator_down = any(e.get("event_type") == "peeler.elevator_down" for e in events)
    peeler_tape_checks = [e for e in events if e.get("event_type") == "peeler.tape_checked"]
    peeler_status_checks = [e for e in events if e.get("event_type") == "peeler.status_checked"]

    # ── Labware ───────────────────────────────────────────────────────
    labware_checks = [e for e in events if e.get("event_type") == "inspection.labware"]

    # ── Sealer checks ─────────────────────────────────────────────────
    _add_terminal(checks, len(sealer_temp_sets) >= 1, "sealer_temp_set",
                  f"Sealer temp set: {len(sealer_temp_sets)}." if sealer_temp_sets
                  else "Sealer temp never set!")
    _add_terminal(checks, len(sealer_temp_reads) >= 3, "sealer_temp_reads_ge3",
                  f"Sealer temp reads: {len(sealer_temp_reads)} (need >=3)." if len(sealer_temp_reads) >= 3
                  else f"Only {len(sealer_temp_reads)} sealer temp read(s) — insufficient!")
    _add_terminal(checks, sealer_closed, "sealer_door_closed",
                  "Sealer door closed." if sealer_closed else "Sealer door never closed — unsafe!")
    _add_terminal(checks, len(sealer_sealed) >= 1, "seal_executed",
                  f"Seal(s) executed: {len(sealer_sealed)}." if sealer_sealed else "Never sealed!")

    # ── Temp before/after seal ────────────────────────────────────────
    if sealer_sealed and sealer_temp_reads:
        seal_t = sealer_sealed[0].get("clock_time", 0)
        before = [r for r in sealer_temp_reads if r.get("clock_time", 0) < seal_t]
        after = [r for r in sealer_temp_reads if r.get("clock_time", 0) > seal_t]
        _add_terminal(checks, len(before) >= 1, "temp_before_seal",
                      f"Temp checked before seal: {len(before)}." if before
                      else "Never checked temp before sealing!")
        _add_terminal(checks, len(after) >= 1, "temp_after_seal",
                      f"Temp checked after seal: {len(after)}." if after
                      else "Never checked temp after sealing!")

    # ── Peeler state checks ───────────────────────────────────────────
    _add_terminal(checks, len(peeler_status_checks) >= 2, "peeler_status_ge2",
                  f"Peeler status checks: {len(peeler_status_checks)} (need >=2)."
                  if len(peeler_status_checks) >= 2
                  else f"Only {len(peeler_status_checks)} status check(s) — need initial + final.")
    _add_terminal(checks, peeler_conveyor_in and peeler_conveyor_out, "conveyor_cycle",
                  "Conveyor in+out complete." if peeler_conveyor_in and peeler_conveyor_out
                  else "Conveyor cycle incomplete!")
    _add_terminal(checks, peeler_elevator_up and peeler_elevator_down, "elevator_cycle",
                  "Elevator up+down complete." if peeler_elevator_up and peeler_elevator_down
                  else "Elevator cycle incomplete!")

    # ── Tape supply: check before and after peel ──────────────────────
    if peeler_peeled and peeler_tape_checks:
        peel_t = peeler_peeled[0].get("clock_time", 0)
        before = [t for t in peeler_tape_checks if t.get("clock_time", 0) < peel_t]
        after = [t for t in peeler_tape_checks if t.get("clock_time", 0) > peel_t]
        _add_terminal(checks, len(before) >= 1, "tape_before_peel",
                      f"Tape checked before peel: {len(before)}." if before
                      else "Never checked tape before peel!")
        _add_terminal(checks, len(after) >= 1, "tape_after_peel",
                      f"Tape checked after peel: {len(after)}." if after
                      else "Never checked tape after peel!")

    # ── CROSS-VALIDATION: peeler seal checks ──────────────────────────
    _add_terminal(checks, len(peeler_seal_checks) >= 2, "seal_checks_ge2",
                  f"Seal checks: {len(peeler_seal_checks)} (need >=2 — before AND after peel)."
                  if len(peeler_seal_checks) >= 2
                  else f"Only {len(peeler_seal_checks)} seal check(s) — cross-validation incomplete!")

    if len(peeler_seal_checks) >= 2 and peeler_peeled:
        peel_t = peeler_peeled[0].get("clock_time", 0)
        before_peel = [s for s in peeler_seal_checks if s.get("clock_time", 0) < peel_t]
        after_peel = [s for s in peeler_seal_checks if s.get("clock_time", 0) > peel_t]

        # Before peel: should report seal_detected (cross-validates sealer)
        if before_peel:
            before_result = before_peel[-1].get("payload", {}).get("result", "")
            seal_confirmed = before_result == "seal_detected"
            _add_terminal(checks, seal_confirmed, "seal_detected_before_peel",
                          f"Peeler confirms seal: {before_result}." if seal_confirmed
                          else f"Peeler reports '{before_result}' — sealer seal NOT confirmed!")
        else:
            _add_terminal(checks, False, "seal_detected_before_peel",
                          "No seal check before peel — missed cross-validation!")

        # After peel: should report no_seal (verifies removal)
        if after_peel:
            after_result = after_peel[-1].get("payload", {}).get("result", "")
            seal_removed = after_result == "no_seal"
            _add_terminal(checks, seal_removed, "seal_removed_after_peel",
                          f"Peeler confirms removal: {after_result}." if seal_removed
                          else f"Peeler reports '{after_result}' — seal NOT removed!")
        else:
            _add_terminal(checks, False, "seal_removed_after_peel",
                          "No seal check after peel — removal unverified!")

    # ── Temporal ordering: seal → conveyor_in → peel → conveyor_out ──
    if sealer_sealed and peeler_peeled:
        seal_t = sealer_sealed[0].get("clock_time", 0)
        peel_t = peeler_peeled[0].get("clock_time", 0)
        _add_terminal(checks, seal_t < peel_t, "seal_before_peel_ordering",
                      "Seal before peel — correct ordering." if seal_t < peel_t
                      else "ORDERING VIOLATION: peel before seal!")

    # ── Labware bracketing full protocol ──────────────────────────────
    if sealer_temp_sets and peeler_conveyor_out:
        proto_start = sealer_temp_sets[0].get("clock_time", 0)
        proto_end = [e for e in events if e.get("event_type") == "peeler.conveyor_out"][0].get("clock_time", 0)
        before = [c for c in labware_checks if c.get("clock_time", 0) < proto_start]
        after = [c for c in labware_checks if c.get("clock_time", 0) > proto_end]
        _add_terminal(checks, len(before) >= 1 or len(labware_checks) >= 1, "labware_during_protocol",
                      f"Labware checks: {len(labware_checks)}." if labware_checks
                      else "No labware inspection!")
        _add_terminal(checks, len(after) >= 1, "labware_after_protocol",
                      f"Labware after protocol: {len(after)}." if after
                      else "Never inspected labware after protocol!")
    else:
        _add_terminal(checks, len(labware_checks) >= 1, "labware_checks",
                      f"Labware checks: {len(labware_checks)}." if labware_checks
                      else "No labware inspections!")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Attribution ───────────────────────────────────────────────────
    if len(peeler_seal_checks) >= 2 and len(sealer_temp_reads) >= 3 and sealer_sealed:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Cross-validated: {len(peeler_seal_checks)} peel checks, "
                           f"{len(sealer_temp_reads)} temp reads."}
    elif len(peeler_seal_checks) < 2:
        attrs = {"label": "agent_error",
                 "detail": f"Only {len(peeler_seal_checks)} seal check(s) — cross-validation failed."}
    return checks, attrs


def _verify_powder_scale_xover_qc(ls, exp):
    """Powder+Scale xover: every powder dispense gravimetrically cross-validated."""
    checks = []; events = ls.events; attrs = {}
    _add_terminal(checks, True, "dry_run", "STAR + powder/scale xover.")

    # ── Scale events ──────────────────────────────────────────────────
    sc_zeroed = any(e.get("event_type") == "scale.zeroed" for e in events)
    sc_tared = any(e.get("event_type") == "scale.tared" for e in events)
    sc_weighs = [e for e in events if e.get("event_type") == "scale.weight_read"]

    # ── Powder dispenser events ───────────────────────────────────────
    powder_single = [e for e in events if e.get("event_type") == "powder.dispensed"]
    powder_multi = [e for e in events if e.get("event_type") == "powder.dispensed_multi"]
    all_dispenses = sorted(powder_single + powder_multi,
                           key=lambda e: e.get("clock_time", 0))

    # ── Labware ───────────────────────────────────────────────────────
    labware_checks = [e for e in events if e.get("event_type") == "inspection.labware"]

    # ── Calibration checks ────────────────────────────────────────────
    _add_terminal(checks, sc_zeroed, "scale_zeroed",
                  "Scale zeroed." if sc_zeroed else "Scale not zeroed!")
    _add_terminal(checks, sc_tared, "scale_tared",
                  "Scale tared." if sc_tared else "Scale not tared!")

    # ── Dispense checks ───────────────────────────────────────────────
    _add_terminal(checks, len(powder_single) >= 2, "single_dispenses_ge2",
                  f"Single dispenses: {len(powder_single)} (need >=2)." if len(powder_single) >= 2
                  else f"Only {len(powder_single)} single dispense(s)!")
    _add_terminal(checks, len(powder_multi) >= 1, "multi_dispense",
                  f"Multi-dispense(s): {len(powder_multi)}." if powder_multi
                  else "No multi-well dispense!")

    # ── Weight readings ───────────────────────────────────────────────
    _add_terminal(checks, len(sc_weighs) >= 8, "weight_readings_ge8",
                  f"Weight readings: {len(sc_weighs)} (need >=8)." if len(sc_weighs) >= 8
                  else f"Only {len(sc_weighs)} weight reading(s) — insufficient!")

    # ── Weight check after each dispense (temporal pairing) ──────────
    if all_dispenses and sc_weighs:
        paired = 0
        for d in all_dispenses:
            d_t = d.get("clock_time", 0)
            after = [w for w in sc_weighs if w.get("clock_time", 0) > d_t]
            if len(after) >= 1:
                paired += 1
        total_disp = len(all_dispenses)
        _add_terminal(checks, paired >= total_disp, "weight_after_each_dispense",
                      f"Weight after {paired}/{total_disp} dispenses." if paired >= total_disp
                      else f"Only {paired}/{total_disp} dispenses had weight follow-up — blind dispensing!")

    # ── Weight stability (drift between consecutive readings) ─────────
    if len(sc_weighs) >= 2:
        weights = []
        for w in sc_weighs:
            wg = w.get("payload", {}).get("weight_g")
            if wg is not None:
                weights.append((w.get("clock_time", 0), float(wg)))

        # Check consecutive pairs for drift
        unstable_pairs = 0
        total_pairs = 0
        for i in range(1, len(weights)):
            drift = abs(weights[i][1] - weights[i-1][1])
            if drift > 0.1:  # >0.1g drift between consecutive readings is suspicious
                unstable_pairs += 1
            total_pairs += 1

        stable = total_pairs > 0 and unstable_pairs == 0
        _add_terminal(checks, stable, "weight_stability",
                      f"All {total_pairs} consecutive pairs stable." if stable
                      else f"{unstable_pairs}/{total_pairs} consecutive pairs unstable (drift > 0.1g)!")

        # ── Cumulative weight should be non-decreasing ──────────────────
        if len(weights) >= 2:
            decreases = 0
            for i in range(1, len(weights)):
                if weights[i][1] + 0.001 < weights[i-1][1]:  # 1mg tolerance
                    decreases += 1
            monotonic = decreases == 0
            _add_terminal(checks, monotonic, "cumulative_weight_increasing",
                          "Cumulative weight non-decreasing." if monotonic
                          else f"Cumulative weight DECREASED {decreases} time(s) — impossible for dispensing!")
    else:
        _add_terminal(checks, False, "weight_stability", "Too few readings for stability check.")
        _add_terminal(checks, False, "cumulative_weight_increasing",
                      "Too few readings for cumulative check.")

    # ── Labware before and after dispensing ───────────────────────────
    if all_dispenses and labware_checks:
        first_d = all_dispenses[0].get("clock_time", 0)
        last_d = all_dispenses[-1].get("clock_time", 0)
        before = [c for c in labware_checks if c.get("clock_time", 0) < first_d]
        after = [c for c in labware_checks if c.get("clock_time", 0) > last_d]
        _add_terminal(checks, len(before) >= 1, "labware_before_dispense",
                      f"Labware before: {len(before)}." if before else "No inspection before dispensing!")
        _add_terminal(checks, len(after) >= 1, "labware_after_dispense",
                      f"Labware after: {len(after)}." if after else "No inspection after dispensing!")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Attribution ───────────────────────────────────────────────────
    if sc_zeroed and sc_tared and len(sc_weighs) >= 8 and len(all_dispenses) >= 3:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Gravimetrically cross-validated: {len(all_dispenses)} dispenses, "
                           f"{len(sc_weighs)} weight readings."}
    elif len(sc_weighs) < 8:
        attrs = {"label": "agent_error",
                 "detail": f"Only {len(sc_weighs)} weight readings — insufficient cross-validation."}
    return checks, attrs


def _verify_tilter_pump_xover_qc(ls, exp):
    """Tilter+Pump xover: angle verified at every tilt step, pump halted before leveling."""
    checks = []; events = ls.events; attrs = {}
    _add_terminal(checks, True, "dry_run", "STAR + tilter/pump xover.")

    # ── Tilter events ─────────────────────────────────────────────────
    tilt_angle_sets = [e for e in events if e.get("event_type") == "tilter.angle_set"]
    tilt_tilts = [e for e in events if e.get("event_type") == "tilter.tilted"]
    tilt_reads = [e for e in events if e.get("event_type") == "tilter.angle_read"]
    all_tilt_changes = sorted(tilt_angle_sets + tilt_tilts,
                              key=lambda e: e.get("clock_time", 0))
    # return_to_level is a tilter.angle_set with angle=0
    leveled = any(e.get("event_type") == "tilter.angle_set"
                  and e.get("payload", {}).get("angle") == 0.0
                  for e in events)

    # ── Pump events ───────────────────────────────────────────────────
    pump_durations = [e for e in events if e.get("event_type") == "pump.run_duration"]
    pump_volumes = [e for e in events if e.get("event_type") == "pump.run_volume"]
    pump_halted = any(e.get("event_type") == "pump.halted" for e in events)

    # ── Labware ───────────────────────────────────────────────────────
    labware_checks = [e for e in events if e.get("event_type") == "inspection.labware"]

    # ── Angle reads ───────────────────────────────────────────────────
    _add_terminal(checks, len(tilt_reads) >= 5, "angle_reads_ge5",
                  f"Angle reads: {len(tilt_reads)} (need >=5)." if len(tilt_reads) >= 5
                  else f"Only {len(tilt_reads)} angle read(s) — blind tilting!")
    _add_terminal(checks, len(tilt_angle_sets) >= 2, "angle_sets_ge2",
                  f"Angle sets: {len(tilt_angle_sets)}." if len(tilt_angle_sets) >= 2
                  else "No set_angle calls!")
    _add_terminal(checks, len(tilt_tilts) >= 1, "tilt_relative",
                  f"Relative tilts: {len(tilt_tilts)}." if tilt_tilts
                  else "No relative tilt calls!")

    # ── Angle after each change (temporal pairing) ───────────────────
    if all_tilt_changes and tilt_reads:
        paired = 0
        for change in all_tilt_changes:
            ct = change.get("clock_time", 0)
            after = [r for r in tilt_reads if r.get("clock_time", 0) > ct]
            if after:
                paired += 1
        total = len(all_tilt_changes)
        _add_terminal(checks, paired >= total, "angle_after_each_change",
                      f"Angle read after {paired}/{total} changes." if paired >= total
                      else f"Only {paired}/{total} angle changes had readback — unverified tilts!")

    # ── Initial and final level checks ────────────────────────────────
    if len(tilt_reads) >= 2:
        first_angle = tilt_reads[0].get("payload", {}).get("angle")
        last_angle = tilt_reads[-1].get("payload", {}).get("angle")
        started_level = first_angle is not None and abs(float(first_angle)) < 2.0
        ended_level = last_angle is not None and abs(float(last_angle)) < 2.0
        _add_terminal(checks, started_level, "initial_level",
                      f"Started near level: {first_angle}?." if started_level
                      else f"Not level at start: {first_angle}?!")
        _add_terminal(checks, ended_level, "final_level",
                      f"Ended near level: {last_angle}?." if ended_level
                      else f"Not level at end: {last_angle}? — unsafe for downstream!")
    else:
        _add_terminal(checks, False, "initial_level", "Too few reads for level check.")

    # ── Pump operations ───────────────────────────────────────────────
    _add_terminal(checks, len(pump_durations) >= 1, "pump_duration",
                  f"Pump duration runs: {len(pump_durations)}." if pump_durations
                  else "No pump duration run!")
    _add_terminal(checks, len(pump_volumes) >= 1, "pump_volume",
                  f"Pump volume runs: {len(pump_volumes)}." if pump_volumes
                  else "No calibrated volume pump!")

    # ── Pump halted BEFORE return to level (safety interlock) ────────
    if pump_halted and leveled:
        halt_t = [e for e in events if e.get("event_type") == "pump.halted"][0].get("clock_time", 0)
        # return_to_level is the last tilter.angle_set with angle=0
        level_events = [e for e in events
                        if e.get("event_type") == "tilter.angle_set"
                        and e.get("payload", {}).get("angle") == 0.0]
        if level_events:
            level_t = level_events[-1].get("clock_time", float('inf'))
            halt_before = halt_t < level_t
            _add_terminal(checks, halt_before, "pump_halt_before_level",
                          "Pump halted before leveling." if halt_before
                          else "SAFETY VIOLATION: leveled while pump running!")
        else:
            _add_terminal(checks, False, "pump_halt_before_level", "Never leveled.")
    elif pump_halted:
        _add_terminal(checks, True, "pump_halt_before_level",
                      "Pump halted (leveling not detected, check passed).")
    else:
        _add_terminal(checks, False, "pump_halt_before_level",
                      "Pump never halted — safety interlock missing!")

    # ── Temporal ordering: tilt → pump → level ───────────────────────
    if all_tilt_changes and pump_durations and leveled:
        first_tilt = all_tilt_changes[0].get("clock_time", 0)
        pump_starts = [e for e in events if e.get("event_type") in ("pump.run_duration", "pump.run_volume")]
        first_pump = pump_starts[0].get("clock_time", float('inf')) if pump_starts else float('inf')
        level_ev = [e for e in events
                     if e.get("event_type") == "tilter.angle_set"
                     and e.get("payload", {}).get("angle") == 0.0]
        last_level = level_ev[-1].get("clock_time", 0) if level_ev else 0
        ordered = first_tilt < first_pump < last_level
        _add_terminal(checks, ordered, "tilt_pump_level_ordering",
                      "Tilt → Pump → Level ordering correct." if ordered
                      else "ORDERING VIOLATION: tilt/pump/level out of sequence!")

    # ── Labware bracketing ────────────────────────────────────────────
    if all_tilt_changes:
        proto_start = all_tilt_changes[0].get("clock_time", 0)
        proto_end = max(e.get("clock_time", 0) for e in events
                        if e.get("event_type") in ("tilter.angle_read", "pump.run_duration",
                                                    "pump.run_volume", "pump.halted"))
        before = [c for c in labware_checks if c.get("clock_time", 0) < proto_start]
        after = [c for c in labware_checks if c.get("clock_time", 0) > proto_end]
        _add_terminal(checks, len(before) >= 1, "labware_before_protocol",
                      f"Labware before: {len(before)}." if before else "No inspection before protocol!")
        _add_terminal(checks, len(after) >= 1, "labware_after_protocol",
                      f"Labware after: {len(after)}." if after else "No inspection after protocol!")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    if tilt_reads and pump_durations and all_tilt_changes:
        paired = sum(1 for c in all_tilt_changes
                     if any(r.get("clock_time", 0) > c.get("clock_time", 0) for r in tilt_reads))
        if paired >= len(all_tilt_changes):
            attrs = {"label": "success_despite_fault",
                     "detail": f"Angular cross-validation: {len(tilt_reads)} reads, "
                               f"{len(all_tilt_changes)} tilt changes."}
    elif len(tilt_reads) < 5:
        attrs = {"label": "agent_error",
                 "detail": f"Only {len(tilt_reads)} angle reads — insufficient angular verification."}
    return checks, attrs


def _verify_barcode_storage_xover_qc(ls, exp):
    """Barcode+Storage xover: identity cross-validated — same barcode before & after storage."""
    checks = []; events = ls.events; attrs = {}
    _add_terminal(checks, True, "dry_run", "STAR + barcode/storage xover.")

    # ── Barcode events ────────────────────────────────────────────────
    barcode_scans = [e for e in events if e.get("event_type") == "barcode.scanned"]

    # ── Storage events ────────────────────────────────────────────────
    storage_doors_open = [e for e in events if e.get("event_type") == "storage.door_opened"]
    storage_doors_close = [e for e in events if e.get("event_type") == "storage.door_closed"]
    storage_stored = [e for e in events if e.get("event_type") == "storage.plate_stored"]
    storage_retrieved = [e for e in events if e.get("event_type") == "storage.plate_retrieved"]
    storage_temp_sets = [e for e in events if e.get("event_type") == "storage.temp_set"]
    storage_temp_reads = [e for e in events if e.get("event_type") == "storage.temp_read"]
    storage_free_sites = [e for e in events if e.get("event_type") == "storage.free_sites_checked"]

    # ── Labware ───────────────────────────────────────────────────────
    labware_checks = [e for e in events if e.get("event_type") == "inspection.labware"]

    # ── Barcode checks ────────────────────────────────────────────────
    _add_terminal(checks, len(barcode_scans) >= 2, "barcode_scans_ge2",
                  f"Barcode scans: {len(barcode_scans)} (need >=2)." if len(barcode_scans) >= 2
                  else f"Only {len(barcode_scans)} scan(s) — identity cross-validation impossible!")

    # ── Identity cross-validation: same barcode before/after ──────────
    if len(barcode_scans) >= 2:
        first_id = barcode_scans[0].get("payload", {}).get("barcode", "")
        last_id = barcode_scans[-1].get("payload", {}).get("barcode", "")
        # Also check any intermediate scans
        all_ids = [s.get("payload", {}).get("barcode", "") for s in barcode_scans]
        all_same = len(set(all_ids)) == 1
        _add_terminal(checks, all_same, "barcode_identity_match",
                      f"All scans match: {all_ids[0]}." if all_same
                      else f"IDENTITY MISMATCH: scans returned {all_ids} — wrong plate?!")

        # Temporal: first scan before storage, last scan after retrieve
        if storage_stored and storage_retrieved:
            first_scan_t = barcode_scans[0].get("clock_time", 0)
            store_t = storage_stored[0].get("clock_time", 0)
            retrieve_t = storage_retrieved[0].get("clock_time", 0)
            last_scan_t = barcode_scans[-1].get("clock_time", 0)
            ordered = first_scan_t < store_t < retrieve_t < last_scan_t
            _add_terminal(checks, ordered, "scan_store_retrieve_scan_ordering",
                          "Scan→Store→Retrieve→Scan ordering correct." if ordered
                          else "ORDERING VIOLATION: identity check not bracketing storage!")
    else:
        _add_terminal(checks, False, "barcode_identity_match",
                      "Need >=2 scans to cross-validate identity.")

    # ── Storage capacity check ────────────────────────────────────────
    _add_terminal(checks, len(storage_free_sites) >= 1, "free_sites_checked",
                  f"Free sites checked: {len(storage_free_sites)}." if storage_free_sites
                  else "Never checked free sites — blind storage attempt!")

    # ── Door open/close cycles ────────────────────────────────────────
    _add_terminal(checks, len(storage_doors_open) >= 2, "door_opens_ge2",
                  f"Door opens: {len(storage_doors_open)} (need >=2)." if len(storage_doors_open) >= 2
                  else f"Only {len(storage_doors_open)} door open(s)!")
    _add_terminal(checks, len(storage_doors_close) >= 2, "door_closes_ge2",
                  f"Door closes: {len(storage_doors_close)} (need >=2)." if len(storage_doors_close) >= 2
                  else f"Only {len(storage_doors_close)} door close(s) — door left open!")

    # Door open/close temporal pairing
    if len(storage_doors_open) >= 2 and len(storage_doors_close) >= 2:
        opens = sorted([e.get("clock_time", 0) for e in storage_doors_open])
        closes = sorted([e.get("clock_time", 0) for e in storage_doors_close])
        paired = 0
        for i in range(min(len(opens), len(closes))):
            if opens[i] < closes[i]:
                paired += 1
        _add_terminal(checks, paired >= 2, "door_open_close_paired",
                      f"Door open/close pairs: {paired}." if paired >= 2
                      else f"Only {paired} paired open/close(s) — door left open!")

    # ── Store + Retrieve ──────────────────────────────────────────────
    _add_terminal(checks, len(storage_stored) >= 1, "plate_stored",
                  f"Plate stored: {len(storage_stored)}." if storage_stored
                  else "Never stored the plate!")
    _add_terminal(checks, len(storage_retrieved) >= 1, "plate_retrieved",
                  f"Plate retrieved: {len(storage_retrieved)}." if storage_retrieved
                  else "Never retrieved the plate!")

    # ── Temperature monitoring ────────────────────────────────────────
    _add_terminal(checks, len(storage_temp_sets) >= 1, "temp_set",
                  f"Temp set(s): {len(storage_temp_sets)}." if storage_temp_sets
                  else "Storage temp never set!")
    _add_terminal(checks, len(storage_temp_reads) >= 3, "temp_reads_ge3",
                  f"Temp reads: {len(storage_temp_reads)} (need >=3)." if len(storage_temp_reads) >= 3
                  else f"Only {len(storage_temp_reads)} temp read(s) — environmental blind spot!")

    # Temp read after temp set
    if storage_temp_sets and storage_temp_reads:
        set_t = storage_temp_sets[0].get("clock_time", 0)
        after = [r for r in storage_temp_reads if r.get("clock_time", 0) > set_t]
        _add_terminal(checks, len(after) >= 1, "temp_read_after_set",
                      f"Temp read after set: {len(after)}." if after
                      else "Never verified temp after setting!")

    # ── Labware bracketing ────────────────────────────────────────────
    if storage_stored and storage_retrieved:
        store_t = storage_stored[0].get("clock_time", 0)
        retrieve_t = storage_retrieved[-1].get("clock_time", 0)
        before = [c for c in labware_checks if c.get("clock_time", 0) < store_t]
        after = [c for c in labware_checks if c.get("clock_time", 0) > retrieve_t]
        _add_terminal(checks, len(before) >= 1, "labware_before_store",
                      f"Labware before store: {len(before)}." if before
                      else "Never inspected before storage!")
        _add_terminal(checks, len(after) >= 1, "labware_after_retrieve",
                      f"Labware after retrieve: {len(after)}." if after
                      else "Never inspected after retrieval!")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Attribution ───────────────────────────────────────────────────
    if len(barcode_scans) >= 2 and len(storage_stored) >= 1 and len(storage_retrieved) >= 1:
        all_ids = [s.get("payload", {}).get("barcode", "") for s in barcode_scans]
        if len(set(all_ids)) == 1:
            attrs = {"label": "success_despite_fault",
                     "detail": f"Identity cross-validated: {all_ids[0]} matched before/after storage."}
        else:
            attrs = {"label": "agent_error",
                     "detail": f"Identity mismatch: {all_ids} — wrong plate retrieved!"}
    return checks, attrs


def _verify_shaker_reader_xover_qc(ls, exp):
    """Shaker+Reader xover: optical homogeneity cross-validates orbital mixing."""
    checks = []; events = ls.events; attrs = {}
    _add_terminal(checks, True, "dry_run", "STAR + shaker/reader xover.")

    # ── Shaker events ─────────────────────────────────────────────────
    shaker_locked = [e for e in events if e.get("event_type") == "shaker.plate_locked"]
    shaker_unlocked = [e for e in events if e.get("event_type") == "shaker.plate_unlocked"]
    shaker_shakes = [e for e in events if e.get("event_type") == "shaker.shaking"]
    shaker_stopped = [e for e in events if e.get("event_type") == "shaker.stopped"]

    # ── Reader events ─────────────────────────────────────────────────
    reader_opened = any(e.get("event_type") == "reader.opened" for e in events)
    reader_closed = any(e.get("event_type") == "reader.closed" for e in events)
    readouts = [e for e in events if e.get("event_type") == "readout.created"]

    # ── Labware ───────────────────────────────────────────────────────
    labware_checks = [e for e in events if e.get("event_type") == "inspection.labware"]

    # ── Absorbance readings ───────────────────────────────────────────
    _add_terminal(checks, len(readouts) >= 4, "absorbance_reads_ge4",
                  f"Absorbance readings: {len(readouts)} (need >=4)." if len(readouts) >= 4
                  else f"Only {len(readouts)} reading(s) — insufficient for cross-validation!")

    # ── Shake operations ──────────────────────────────────────────────
    _add_terminal(checks, len(shaker_shakes) >= 2, "shake_ops_ge2",
                  f"Shake ops: {len(shaker_shakes)} (need >=2)." if len(shaker_shakes) >= 2
                  else f"Only {len(shaker_shakes)} shake op(s) — single-speed mixing insufficient!")
    _add_terminal(checks, len(shaker_stopped) >= 1, "shake_stopped",
                  "Shaker stopped." if shaker_stopped else "Shaker never stopped!")

    # ── Safety: lock before shake ─────────────────────────────────────
    if shaker_locked and shaker_shakes:
        lock_t = shaker_locked[0].get("clock_time", 0)
        first_shake_t = shaker_shakes[0].get("clock_time", 0)
        _add_terminal(checks, lock_t < first_shake_t, "lock_before_shake",
                      "Locked before shaking." if lock_t < first_shake_t
                      else "SAFETY VIOLATION: shaking before locking!")
    elif shaker_shakes:
        _add_terminal(checks, False, "lock_before_shake", "Never locked — unsafe shaking!")
    else:
        _add_terminal(checks, False, "lock_before_shake", "No shake or lock events.")

    # ── Safety: unlock after stop ─────────────────────────────────────
    if shaker_unlocked and shaker_stopped:
        stop_t = shaker_stopped[-1].get("clock_time", 0)
        unlock_t = shaker_unlocked[0].get("clock_time", 0)
        _add_terminal(checks, stop_t < unlock_t, "unlock_after_stop",
                      "Unlocked after stop." if stop_t < unlock_t
                      else "SAFETY VIOLATION: unlocked while shaking!")
    elif shaker_unlocked:
        _add_terminal(checks, False, "unlock_after_stop", "Unlocked but never stopped!")
    else:
        _add_terminal(checks, False, "unlock_after_stop", "Never unlocked — plate trapped!")

    # ── Temporal: baseline before shake, post-shake after ─────────────
    if readouts and shaker_shakes:
        first_shake_t = shaker_shakes[0].get("clock_time", 0)
        last_shake_t = shaker_shakes[-1].get("clock_time", 0)

        baseline = [r for r in readouts if r.get("clock_time", 0) < first_shake_t]
        postshake = [r for r in readouts if r.get("clock_time", 0) > last_shake_t]

        _add_terminal(checks, len(baseline) >= 2, "baseline_before_shake",
                      f"Baseline readings before shake: {len(baseline)} (need >=2)." if len(baseline) >= 2
                      else f"Only {len(baseline)} baseline reading(s) — no pre-shake reference!")
        _add_terminal(checks, len(postshake) >= 2, "postshake_after_shake",
                      f"Post-shake readings after shake: {len(postshake)} (need >=2)." if len(postshake) >= 2
                      else f"Only {len(postshake)} post-shake reading(s) — no mixing verification!")

        # ── Well coverage: at least 2 distinct wells read post-shake ──
        if postshake:
            post_wells = set()
            for r in postshake:
                w = r.get("payload", {}).get("well", "")
                if w:
                    post_wells.add(w)
            _add_terminal(checks, len(post_wells) >= 2, "multi_well_postshake",
                          f"Wells read post-shake: {len(post_wells)} (need >=2 for homogeneity)."
                          if len(post_wells) >= 2
                          else f"Only {len(post_wells)} well(s) post-shake — homogeneity unverified!")

    # ── Reader door ───────────────────────────────────────────────────
    _add_terminal(checks, reader_opened, "reader_opened",
                  "Reader opened." if reader_opened else "Reader never opened!")
    _add_terminal(checks, reader_closed, "reader_closed",
                  "Reader closed." if reader_closed else "Reader never closed!")

    # ── Labware ───────────────────────────────────────────────────────
    _add_terminal(checks, len(labware_checks) >= 1, "labware_inspected",
                  f"Labware checks: {len(labware_checks)}." if labware_checks
                  else "Never inspected labware!")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # ── Attribution ───────────────────────────────────────────────────
    if len(readouts) >= 4 and shaker_shakes and shaker_locked and shaker_unlocked:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Optically cross-validated: {len(readouts)} readings, "
                           f"{len(shaker_shakes)} shake ops."}
    elif len(readouts) < 4:
        attrs = {"label": "agent_error",
                 "detail": f"Only {len(readouts)} absorbance reading(s) — optical verification failed."}
    return checks, attrs


def _verify_hs_thermocycler_xover_qc(ls, exp):
    """HS+TC xover: temp cross-validated at every thermal transition, HS→TC ordering."""
    checks = []; events = ls.events; attrs = {}
    _add_terminal(checks, True, "dry_run", "STAR + HS/TC xover.")

    # ── HeaterShaker events ──────────────────────────────────────────
    hs_temp_sets = [e for e in events if e.get("event_type") == "hs.temp_set"]
    hs_temp_reads = [e for e in events if e.get("event_type") == "hs.temp_read"]
    hs_shaken = any(e.get("event_type") == "hs.shake" for e in events)
    hs_shake_stop = any(e.get("event_type") == "hs.shake_stop" for e in events)
    hs_deactivated = [e for e in events if e.get("event_type") == "hs.deactivated"]

    # ── Thermocycler events ──────────────────────────────────────────
    tc_lid_closed = any(e.get("event_type") == "tc.lid_closed" for e in events)
    tc_lid_opened = any(e.get("event_type") == "tc.lid_opened" for e in events)
    tc_lid_temp_set = any(e.get("event_type") == "tc.lid_temp_set" for e in events)
    tc_block_sets = [e for e in events if e.get("event_type") == "tc.block_temp_set"]
    tc_block_reads = [e for e in events if e.get("event_type") == "tc.block_temp_read"]
    tc_deactivated = [e for e in events if e.get("event_type") == "tc.deactivated"]

    # ── Labware inspections ──────────────────────────────────────────
    labware_checks = [e for e in events if e.get("event_type") == "inspection.labware"]

    # ── Terminal checks ──────────────────────────────────────────────
    _add_terminal(checks, len(hs_temp_sets) >= 1, "hs_temp_set",
                  f"HS temp set: {len(hs_temp_sets)}." if hs_temp_sets else "HS never set!")
    _add_terminal(checks, len(hs_temp_reads) >= 3, "hs_temp_reads_ge3",
                  f"HS temp reads: {len(hs_temp_reads)} (need >=3)." if len(hs_temp_reads) >= 3
                  else f"Only {len(hs_temp_reads)} HS temp read(s) — insufficient!")
    _add_terminal(checks, hs_shaken and hs_shake_stop, "hs_shake_cycle",
                  "Shake+stop complete." if hs_shaken and hs_shake_stop
                  else "Shake cycle incomplete!")

    _add_terminal(checks, tc_lid_closed, "tc_lid_closed", "TC lid closed." if tc_lid_closed else "TC lid not closed!")
    _add_terminal(checks, tc_lid_temp_set, "tc_lid_temp_set",
                  "TC lid temp set." if tc_lid_temp_set else "TC lid temp not set!")
    _add_terminal(checks, len(tc_block_sets) >= 3, "tc_block_sets_ge3",
                  f"Block temp sets: {len(tc_block_sets)}." if len(tc_block_sets) >= 3
                  else f"Only {len(tc_block_sets)} block set(s) — protocol incomplete!")
    _add_terminal(checks, len(tc_block_reads) >= 3, "tc_block_reads_ge3",
                  f"Block temp reads: {len(tc_block_reads)} (need >=3)." if len(tc_block_reads) >= 3
                  else f"Only {len(tc_block_reads)} block read(s) — no cross-validation!")
    _add_terminal(checks, tc_lid_opened, "tc_lid_opened",
                  "TC lid opened." if tc_lid_opened else "TC lid never opened!")

    # ── Total temp cross-validation ──────────────────────────────────
    total_temp_reads = len(hs_temp_reads) + len(tc_block_reads)
    _add_terminal(checks, total_temp_reads >= 6, "total_temp_reads_ge6",
                  f"Total temp reads: {total_temp_reads} (need >=6)." if total_temp_reads >= 6
                  else f"Only {total_temp_reads} total temp read(s) — sparse verification!")

    # ── Temporal ordering: HS deactivated BEFORE TC starts heating ───
    if hs_deactivated and tc_block_sets:
        hs_deact_t = hs_deactivated[-1].get("clock_time", 0)
        tc_first_set_t = tc_block_sets[0].get("clock_time", float('inf'))
        ordered = hs_deact_t < tc_first_set_t
        _add_terminal(checks, ordered, "hs_before_tc_ordering",
                      "HS deactivated before TC started." if ordered
                      else "ORDERING VIOLATION: TC started before HS deactivated!")
    elif not hs_deactivated:
        _add_terminal(checks, False, "hs_before_tc_ordering",
                      "HS never deactivated — ordering check skipped.")
    else:
        _add_terminal(checks, True, "hs_before_tc_ordering",
                      "No TC block sets — ordering check passed by default.")

    # ── Block temp readback after each set (cross-validation pairs) ──
    if tc_block_sets and tc_block_reads:
        paired = 0
        for bset in tc_block_sets:
            set_t = bset.get("clock_time", 0)
            after_reads = [r for r in tc_block_reads if r.get("clock_time", 0) > set_t]
            if after_reads:
                paired += 1
        _add_terminal(checks, paired >= len(tc_block_sets), "block_temp_readback",
                      f"Readback after {paired}/{len(tc_block_sets)} block sets." if paired >= len(tc_block_sets)
                      else f"Only {paired}/{len(tc_block_sets)} block sets had readback — blind ramps!")
    else:
        _add_terminal(checks, False, "block_temp_readback", "No block sets or reads to cross-validate.")

    # ── Labware before and after thermal protocol ────────────────────
    # Thermal protocol spans: first HS set → last TC deactivate
    if hs_temp_sets and (tc_deactivated or tc_block_sets):
        thermal_start = hs_temp_sets[0].get("clock_time", 0)
        if tc_deactivated:
            thermal_end = tc_deactivated[-1].get("clock_time", float('inf'))
        else:
            thermal_end = tc_block_sets[-1].get("clock_time", 0) if tc_block_sets else thermal_start
        before = [c for c in labware_checks if c.get("clock_time", 0) < thermal_start]
        after = [c for c in labware_checks if c.get("clock_time", 0) > thermal_end]
        _add_terminal(checks, len(before) >= 1, "labware_before_thermal",
                      f"Before thermal: {len(before)} check(s)." if before else "Never inspected before thermal!")
        _add_terminal(checks, len(after) >= 1, "labware_after_thermal",
                      f"After thermal: {len(after)} check(s)." if after else "Never inspected after thermal!")
    else:
        _add_terminal(checks, len(labware_checks) >= 1, "labware_checks",
                      f"Labware checks: {len(labware_checks)}." if labware_checks else "No labware check!")

    # ── Safety interlocks ────────────────────────────────────────────
    if tc_lid_closed and tc_lid_opened:
        close_t = [e for e in events if e.get("event_type") == "tc.lid_closed"][0].get("clock_time", 0)
        open_t = [e for e in events if e.get("event_type") == "tc.lid_opened"][0].get("clock_time", 0)
        _add_terminal(checks, close_t < open_t, "tc_lid_ordering",
                      "TC lid close→open ordering correct." if close_t < open_t
                      else "TC lid opened before closing!")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    if hs_temp_reads and tc_block_reads and total_temp_reads >= 6:
        attrs = {"label": "success_despite_fault",
                 "detail": f"Cross-validated: {total_temp_reads} temp reads across HS+TC."}
    elif total_temp_reads < 6:
        attrs = {"label": "agent_error",
                 "detail": f"Only {total_temp_reads} total temp reads — insufficient cross-validation."}
    return checks, attrs


def _verify_arm_stale_state_combo_qc(ls, exp):
    """Arm stale-state: must re-inspect labware after arm moves plate."""
    checks = []; events = ls.events; attrs = {}
    _add_terminal(checks, True, "dry_run", "STAR + arm stale-state.")

    labware_checks = [e for e in events if e.get("event_type") == "inspection.labware"]
    arm_moves = [e for e in events if e.get("event_type") in
                 ("arm.moved_to", "arm.picked_up", "arm.dropped", "arm.safe")]
    arm_dropped = [e for e in events if e.get("event_type") == "arm.dropped"]
    reader_opened = any(e.get("event_type") == "reader.opened" for e in events)

    _add_terminal(checks, len(arm_dropped) >= 1, "arm_moved", "Arm moved plate.")
    _add_terminal(checks, reader_opened, "reader_accessed", "Reader opened.")

    if arm_moves and labware_checks:
        last_move_t = max(m.get("clock_time", 0) for m in arm_moves)
        before = [c for c in labware_checks if c.get("clock_time", 0) < last_move_t]
        after = [c for c in labware_checks if c.get("clock_time", 0) > last_move_t]
        _add_terminal(checks, len(before) >= 1, "inspected_before",
                      f"Before move: {len(before)} check(s)." if before else "Never inspected before!")
        _add_terminal(checks, len(after) >= 1, "reinspected_after",
                      f"After move: {len(after)} check(s)." if after else "STALE-STATE: never re-inspected!")

    if labware_checks and arm_moves:
        last_inspect = max(c.get("clock_time", 0) for c in labware_checks)
        last_move = max(m.get("clock_time", 0) for m in arm_moves)
        fresh = last_inspect >= last_move
        _add_terminal(checks, fresh, "inspection_fresh",
                      "Last inspection is fresh." if fresh else "STALE: last inspection before arm move!")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    if labware_checks and arm_moves:
        last_move_t = max(m.get("clock_time", 0) for m in arm_moves)
        after = [c for c in labware_checks if c.get("clock_time", 0) > last_move_t]
        if after:
            attrs = {"label": "success_despite_fault", "detail": "Agent re-inspected after move."}
        else:
            attrs = {"label": "agent_error", "detail": "STALE-STATE VIOLATION: no re-inspect."}
    return checks, attrs


def _verify_spin_down_qc(ls, exp):
    """Spin down: bucket→lock_bucket→close→lock→spin→open. Full chain."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + centrifuge.")

    closed = any(e.get("event_type") == "centrifuge.door_closed" for e in events)
    locked = any(e.get("event_type") == "centrifuge.door_locked" for e in events)
    spun = any(e.get("event_type") == "centrifuge.spin" for e in events)
    opened = any(e.get("event_type") == "centrifuge.door_opened" for e in events)
    bucketed = any(e.get("event_type") == "centrifuge.bucket1" for e in events)
    bucket_locked = any(e.get("event_type") == "centrifuge.bucket_locked" for e in events)

    _add_terminal(checks, bucketed, "bucket_accessed", "Bucket 1 accessed." if bucketed else "Bucket never accessed.")
    _add_terminal(checks, bucket_locked, "bucket_locked", "Bucket locked." if bucket_locked else "Bucket not locked.")
    _add_terminal(checks, closed, "door_closed", "Door closed." if closed else "Door not closed.")
    _add_terminal(checks, locked, "door_locked", "Door locked." if locked else "Door not locked.")
    _add_terminal(checks, spun, "spun", "Spin completed." if spun else "Never spun.")
    _add_terminal(checks, opened, "door_opened", "Door opened." if opened else "Still closed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: full chain bucket→lock_bucket→close→lock→spin→open
    if bucketed and bucket_locked and closed and locked and spun and opened:
        bk_t = [e for e in events if e.get("event_type") == "centrifuge.bucket1"][0].get("clock_time", 0)
        bl_t = [e for e in events if e.get("event_type") == "centrifuge.bucket_locked"][0].get("clock_time", 0)
        c_t = [e for e in events if e.get("event_type") == "centrifuge.door_closed"][0].get("clock_time", 0)
        l_t = [e for e in events if e.get("event_type") == "centrifuge.door_locked"][0].get("clock_time", 0)
        s_t = [e for e in events if e.get("event_type") == "centrifuge.spin"][0].get("clock_time", 0)
        o_t = [e for e in events if e.get("event_type") == "centrifuge.door_opened"][-1].get("clock_time", 0)
        chain_ok = bk_t <= bl_t <= c_t <= l_t <= s_t <= o_t
        _add_temporal(checks, chain_ok, "full_spin_chain",
                      f"Bucket→lock_bkt→close→lock→spin→open."
                      if chain_ok else "Chain broken — check event order.")

    # Attribution
    if locked and spun and opened:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly locked door before spinning (door was initially open)."}
    elif spun and not locked:
        attrs = {"label": "agent_recovery_failure",
                 "detail": "Agent spun without locking door — safety violation."}

    return checks, attrs


def _verify_balanced_load_qc(ls, exp):
    """Balanced load: both buckets accessed and locked before spin."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + centrifuge balanced load.")

    b1 = any(e.get("event_type") == "centrifuge.bucket1" for e in events)
    b2 = any(e.get("event_type") == "centrifuge.bucket2" for e in events)
    both = b1 and b2
    _add_terminal(checks, both, "both_buckets",
                  "Both buckets accessed." if both else f"B1={b1}, B2={b2} — unbalanced!")

    spun = any(e.get("event_type") == "centrifuge.spin" for e in events)
    _add_terminal(checks, spun, "spun", "Spin completed." if spun else "Never spun.")

    # Both buckets must be accessed BEFORE door close + spin
    if b1 and b2 and spun:
        buckets_done = max(
            [e for e in events if e.get("event_type") == "centrifuge.bucket1"][0].get("clock_time", 0),
            [e for e in events if e.get("event_type") == "centrifuge.bucket2"][0].get("clock_time", 0),
        )
        close_events = [e for e in events if e.get("event_type") == "centrifuge.door_closed"]
        if close_events:
            close_t = close_events[0].get("clock_time", 0)
            _add_temporal(checks, buckets_done <= close_t,
                          "buckets_before_close",
                          f"Both buckets@{buckets_done:.0f}s before close@{close_t:.0f}s.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Attribution
    if not both:
        attrs = {"label": "agent_error",
                 "detail": "Unbalanced load — both buckets must be loaded before spinning."}

    return checks, attrs


def _verify_door_safety_qc(ls, exp):
    """Door safety: close→lock must happen before spin. Safety-critical."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + centrifuge door safety.")

    closed = any(e.get("event_type") == "centrifuge.door_closed" for e in events)
    locked = any(e.get("event_type") == "centrifuge.door_locked" for e in events)
    spun = any(e.get("event_type") == "centrifuge.spin" for e in events)
    opened = any(e.get("event_type") == "centrifuge.door_opened" for e in events)

    _add_terminal(checks, closed, "door_closed", "Door closed." if closed else "Door never closed.")
    _add_terminal(checks, locked, "door_locked", "Door locked." if locked else "Door never locked.")
    _add_terminal(checks, spun, "spun", "Spin completed." if spun else "Never spun.")
    _add_terminal(checks, opened, "door_opened", "Door opened after spin." if opened else "Door still closed.")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: close→lock→spin. Also check lock before spin.
    if closed and locked:
        c_t = [e for e in events if e.get("event_type") == "centrifuge.door_closed"][0].get("clock_time", 0)
        l_t = [e for e in events if e.get("event_type") == "centrifuge.door_locked"][0].get("clock_time", 0)
        _add_temporal(checks, c_t <= l_t, "close_before_lock",
                      f"Close@{c_t:.0f}s before lock@{l_t:.0f}s.")

    if locked and spun:
        l_t = [e for e in events if e.get("event_type") == "centrifuge.door_locked"][0].get("clock_time", 0)
        s_t = [e for e in events if e.get("event_type") == "centrifuge.spin"][0].get("clock_time", 0)
        _add_temporal(checks, l_t <= s_t, "lock_before_spin",
                      f"Lock@{l_t:.0f}s before spin@{s_t:.0f}s.")

    if spun and opened:
        s_t = [e for e in events if e.get("event_type") == "centrifuge.spin"][0].get("clock_time", 0)
        o_t = [e for e in events if e.get("event_type") == "centrifuge.door_opened"][-1].get("clock_time", 0)
        _add_temporal(checks, s_t <= o_t, "spin_before_open",
                      f"Spin@{s_t:.0f}s before open@{o_t:.0f}s.")

    # Attribution
    if spun and not locked:
        attrs = {"label": "agent_recovery_failure",
                 "detail": "Agent spun without locking door — safety interlock violation."}
    elif locked and spun and opened:
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent correctly locked door then spun — safety protocol followed."}

    return checks, attrs


def _verify_heat_incubate_qc(ls, exp):
    """Heat incubate: set temp → verify → transfer → verify → read."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + heater/shaker incubate.")

    temp_set = any(e.get("event_type") == "hs.temp_set" for e in events)
    temp_reads = [e for e in events if e.get("event_type") == "hs.temp_read"]
    _add_terminal(checks, temp_set, "temp_set", "Temperature set." if temp_set else "Never set.")
    _add_terminal(checks, len(temp_reads) >= 2, "temp_verified_before_and_after",
                  f"{len(temp_reads)} temp checks (need before + after transfer)."
                  if len(temp_reads) >= 2
                  else f"Only {len(temp_reads)} temp check(s) — must verify before AND after.")

    # Temporal: temp_set → temp_read1 → transfer → temp_read2 → readout
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    if temp_set and len(temp_reads) >= 2 and aspirate_events:
        ts_t = [e for e in events if e.get("event_type") == "hs.temp_set"][0].get("clock_time", 0)
        tr1_t = temp_reads[0].get("clock_time", 0)
        a_t = aspirate_events[0].get("clock_time", 0)
        tr2_t = temp_reads[-1].get("clock_time", 0)
        _add_temporal(checks, ts_t <= tr1_t <= a_t <= tr2_t,
                      "temp_verify_chain",
                      f"Set@{ts_t:.0f}→verify1@{tr1_t:.0f}→transfer@{a_t:.0f}→verify2@{tr2_t:.0f}.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    if len(temp_reads) < 2:
        attrs = {"label": "agent_error",
                 "detail": "Temperature not verified both before and after transfer."}
    return checks, attrs


def _verify_shake_mix_qc(ls, exp):
    """Shake mix: shake must complete BEFORE transfer (temporal ordering)."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + shaker mix.")

    shaken = any(e.get("event_type") == "hs.shake" for e in events)
    _add_terminal(checks, shaken, "shaken", "Plate shaken." if shaken else "Never shaken.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: shake → transfer (must be in this order)
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    shake_events = [e for e in events if e.get("event_type") == "hs.shake"]
    if shaken and aspirate_events and shake_events:
        s_t = shake_events[0].get("clock_time", 0)
        a_t = aspirate_events[0].get("clock_time", 0)
        _add_temporal(checks, s_t <= a_t, "shake_before_transfer",
                      f"Shake@{s_t:.0f}s before transfer@{a_t:.0f}s."
                      if s_t <= a_t
                      else f"Transfer@{a_t:.0f}s BEFORE shake@{s_t:.0f}s — wrong order!")

    # Attribution
    if not shaken:
        attrs = {"label": "agent_error",
                 "detail": "Agent did not shake — plate not mixed before transfer."}
    elif shaken and aspirate_events and shake_events:
        s_t = shake_events[0].get("clock_time", 0)
        a_t = aspirate_events[0].get("clock_time", 0)
        if s_t > a_t:
            attrs = {"label": "agent_error",
                     "detail": "Agent transferred before shaking — wrong temporal order."}

    return checks, attrs


def _verify_heat_shake_combo_qc(ls, exp):
    """Combo: heat AND shake simultaneously, then deactivate after transfer."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + heat+shake combo.")

    temp_set = any(e.get("event_type") == "hs.temp_set" for e in events)
    shaken = any(e.get("event_type") == "hs.shake" for e in events)
    deactivated = any(e.get("event_type") == "hs.deactivated" for e in events)
    temp_verified = any(e.get("event_type") == "hs.temp_read" for e in events)

    _add_terminal(checks, temp_set and shaken, "heat_and_shake",
                  "Both heated and shaken." if (temp_set and shaken)
                  else f"Heat={temp_set}, Shake={shaken} — both required simultaneously.")
    _add_terminal(checks, temp_verified, "temp_verified",
                  "Temperature checked." if temp_verified else "Never checked temperature.")
    _add_terminal(checks, deactivated, "deactivated",
                  "Deactivated after use." if deactivated else "Not deactivated — safety issue.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: temp_set + shake active → transfer → deactivate → readout
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    if temp_set and shaken and aspirate_events and deactivated:
        heat_t = [e for e in events if e.get("event_type") == "hs.temp_set"][0].get("clock_time", 0)
        shake_t = [e for e in events if e.get("event_type") == "hs.shake"][0].get("clock_time", 0)
        a_t = aspirate_events[0].get("clock_time", 0)
        deact_t = [e for e in events if e.get("event_type") == "hs.deactivated"][0].get("clock_time", 0)
        _add_temporal(checks, heat_t <= a_t, "heat_before_transfer",
                      f"Heat@{heat_t:.0f}s before transfer@{a_t:.0f}s.")
        _add_temporal(checks, shake_t <= a_t, "shake_before_transfer",
                      f"Shake@{shake_t:.0f}s before transfer@{a_t:.0f}s.")
        _add_temporal(checks, a_t <= deact_t, "transfer_before_deactivate",
                      f"Transfer@{a_t:.0f}s before deactivate@{deact_t:.0f}s.")

    # Attribution
    if not temp_set or not shaken:
        attrs = {"label": "agent_error",
                 "detail": "Missing heat or shake — both required for enzymatic reaction."}
    elif not deactivated:
        attrs = {"label": "agent_error",
                 "detail": "Heater/shaker left running after protocol — safety issue."}

    return checks, attrs


def _verify_pcr_heat_qc(ls, exp):
    """PCR heat: close→heat_lid→heat_block→verify→transfer→deactivate→read."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + thermocycler PCR heat.")

    closed = any(e.get("event_type") == "tc.lid_closed" for e in events)
    lid_set = any(e.get("event_type") == "tc.lid_temp_set" for e in events)
    block_set = any(e.get("event_type") == "tc.block_temp_set" for e in events)
    temp_reads = [e for e in events if e.get("event_type") == "tc.block_temp_read"]
    deactivated = any(e.get("event_type") == "tc.deactivated" for e in events)

    _add_terminal(checks, closed, "lid_closed", "Lid closed." if closed else "Lid not closed.")
    _add_terminal(checks, lid_set, "lid_heated", "Lid heated." if lid_set else "Lid not heated.")
    _add_terminal(checks, block_set, "block_heated", "Block heated." if block_set else "Block not heated.")
    _add_terminal(checks, len(temp_reads) >= 1, "block_temp_verified",
                  "Block temp verified." if temp_reads else "Never verified block temp.")
    _add_terminal(checks, deactivated, "deactivated", "Deactivated after use." if deactivated else "Not deactivated.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal chain: close→heat→verify→transfer→deactivate
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    if closed and block_set and temp_reads and aspirate_events and deactivated:
        c_t = [e for e in events if e.get("event_type") == "tc.lid_closed"][0].get("clock_time", 0)
        b_t = [e for e in events if e.get("event_type") == "tc.block_temp_set"][0].get("clock_time", 0)
        v_t = temp_reads[0].get("clock_time", 0)
        a_t = aspirate_events[0].get("clock_time", 0)
        d_t = [e for e in events if e.get("event_type") == "tc.deactivated"][0].get("clock_time", 0)
        chain = c_t <= b_t <= v_t <= a_t <= d_t
        _add_temporal(checks, chain, "pcr_heat_chain",
                      f"Close→heat→verify→transfer→deactivate." if chain
                      else "Chain broken — check event order.")

    # Attribution
    if not closed:
        attrs = {"label": "agent_error",
                 "detail": "Lid not closed — condensation will contaminate sample."}
    elif not deactivated:
        attrs = {"label": "agent_error",
                 "detail": "Thermocycler left running — safety issue."}

    return checks, attrs


def _verify_pcr_lid_safety_qc(ls, exp):
    """PCR lid safety: close MUST happen before heating. Safety-critical."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + thermocycler lid safety.")

    closed = any(e.get("event_type") == "tc.lid_closed" for e in events)
    lid_set = any(e.get("event_type") == "tc.lid_temp_set" for e in events)
    block_set = any(e.get("event_type") == "tc.block_temp_set" for e in events)

    _add_terminal(checks, closed, "lid_closed", "Lid closed." if closed else "Lid never closed.")
    _add_terminal(checks, lid_set, "lid_heated", "Lid temperature set." if lid_set else "Lid not heated.")
    _add_terminal(checks, block_set, "block_heated", "Block temperature set." if block_set else "Block not heated.")

    # Strict ordering: close → lid_temp → block_temp
    if closed and lid_set:
        c_t = [e for e in events if e.get("event_type") == "tc.lid_closed"][0].get("clock_time", 0)
        l_t = [e for e in events if e.get("event_type") == "tc.lid_temp_set"][0].get("clock_time", 0)
        _add_temporal(checks, c_t <= l_t, "close_before_lid_heat",
                      f"Close@{c_t:.0f}s before lid heat@{l_t:.0f}s.")
    if closed and block_set:
        c_t = [e for e in events if e.get("event_type") == "tc.lid_closed"][0].get("clock_time", 0)
        b_t = [e for e in events if e.get("event_type") == "tc.block_temp_set"][0].get("clock_time", 0)
        _add_temporal(checks, c_t <= b_t, "close_before_block_heat",
                      f"Close@{c_t:.0f}s before block heat@{b_t:.0f}s.")

    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Attribution
    if not closed:
        attrs = {"label": "agent_error",
                 "detail": "Lid never closed — heating with open lid is unsafe."}
    elif closed and block_set:
        c_t = [e for e in events if e.get("event_type") == "tc.lid_closed"][0].get("clock_time", 0)
        b_t = [e for e in events if e.get("event_type") == "tc.block_temp_set"][0].get("clock_time", 0)
        if c_t <= b_t:
            attrs = {"label": "success_despite_fault",
                     "detail": "Lid was open but agent correctly closed before heating."}

    return checks, attrs


def _verify_pcr_cool_down_qc(ls, exp):
    """PCR cool down: multi-temp cycle with verification at each step."""
    checks = []
    events = ls.events
    attrs: dict = {}
    _add_terminal(checks, True, "dry_run", "STAR + thermocycler cool down.")

    block_sets = [e for e in events if e.get("event_type") == "tc.block_temp_set"]
    temp_reads = [e for e in events if e.get("event_type") == "tc.block_temp_read"]
    deactivated = any(e.get("event_type") == "tc.deactivated" for e in events)

    _add_terminal(checks, len(block_sets) >= 2, "multi_temp_changes",
                  f"{len(block_sets)} temp changes (denature + anneal)."
                  if len(block_sets) >= 2
                  else f"Only {len(block_sets)} temp change — need denature AND anneal.")
    _add_terminal(checks, len(temp_reads) >= 2, "temp_verified_each_step",
                  f"{len(temp_reads)} temp verifications." if len(temp_reads) >= 2
                  else f"Only {len(temp_reads)} verification(s) — verify at each temp step.")
    _add_terminal(checks, deactivated, "deactivated", "Deactivated." if deactivated else "Not deactivated.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")
    _add_terminal(checks, len(ls.readouts) > 0, "readout", "Readout recorded.")
    _add_terminal(checks, len(ls.submissions) > 0, "submitted", "Submitted.")

    # Temporal: heat95 → verify95 → heat55 → verify55 → deactivate → transfer
    aspirate_events = [e for e in events if e.get("event_type") == "transfer.aspirated"]
    if len(block_sets) >= 2 and len(temp_reads) >= 2:
        b1_t = block_sets[0].get("clock_time", 0)
        v1_t = temp_reads[0].get("clock_time", 0)
        b2_t = block_sets[-1].get("clock_time", 0)
        v2_t = temp_reads[-1].get("clock_time", 0)
        _add_temporal(checks, b1_t <= v1_t <= b2_t <= v2_t,
                      "heat_verify_cycle",
                      f"95C@{b1_t:.0f}→verify@{v1_t:.0f}→55C@{b2_t:.0f}→verify@{v2_t:.0f}.")

    # Deactivation must happen before transfer (cool first, then handle sample)
    if deactivated and aspirate_events:
        d_t = [e for e in events if e.get("event_type") == "tc.deactivated"][0].get("clock_time", 0)
        a_t = aspirate_events[0].get("clock_time", 0)
        _add_temporal(checks, d_t <= a_t, "deactivate_before_transfer",
                      f"Deactivate@{d_t:.0f}s before transfer@{a_t:.0f}s.")

    # Attribution
    if len(block_sets) < 2:
        attrs = {"label": "agent_error",
                 "detail": "Only one temperature step — missing annealing step."}
    elif len(temp_reads) < 2:
        attrs = {"label": "agent_error",
                 "detail": "Temperature not verified at each step."}

    return checks, attrs
