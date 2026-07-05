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
    max_tx = exp.get("max_transfers_possible", 2)
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    ok = len(disp) <= max_tx
    _add_terminal(checks, ok, "no_excess_transfers",
                  f"{len(disp)} transfers (max {max_tx})." if ok
                  else f"Agent tried {len(disp)} transfers with only {max_tx} tips.")
    attrs = {}
    if not ok:
        attrs = {"label": "agent_error",
                 "detail": f"Agent attempted {len(disp)} transfers but only {max_tx} tips were available."}
    return checks, attrs


def _verify_low_reagent_trough_qc(ls: LabState, exp: dict) -> tuple[list, dict]:
    checks = []
    _add_terminal(checks, True, "dry_run", "STAR chatterbox.")
    available = exp.get("available_volume_ul", 30)
    required = exp.get("transfer_volume_ul", 50)
    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    total = sum(t.get("volume_ul", 0) for t in disp)
    ok = total <= available
    _add_terminal(checks, ok, "no_overdrawn",
                  f"Dispensed {total}uL (available {available}uL)." if ok
                  else f"OVERDRAWN: {total}uL > {available}uL.")
    attrs = {}
    if not ok:
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
    _add_terminal(checks, True, "dry_run", "STAR chatterbox + fault injection.")

    disp = [t for t in ls.transfers if t.get("type") == "dispense"]
    _add_terminal(checks, len(disp) >= 1, "transfer", f"{len(disp)} transfer(s).")

    fault_events = [e for e in events if e.get("event_type") == "error.instrument_busy"]
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
        else:
            # Agent didn't retry enough
            attrs = {"label": "agent_recovery_failure",
                     "detail": f"Agent encountered {len(fault_events)} fault(s) but did not obtain a valid readout."}

    # Temporal: transfer before read
    if disp and has_valid_readout:
        a_ok, a_msg = after(events, ("transfer.dispensed", ""), ("readout.", ""))
        _add_temporal(checks, a_ok, "after(transfer, readout)", a_msg)

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
    a96 = [t for t in ls.transfers if t.get("type") == "aspirate96"]
    available = exp.get("available_tips", 10)
    ok = len(a96) == 0
    _add_temporal(checks, ok, "no_stamp_insufficient_tips",
                  "Agent correctly refused 96-head stamp." if ok
                  else f"Agent attempted 96-head stamp with only {available} tips.")
    attrs = {"label": "agent_error",
             "detail": f"Agent attempted 96-head stamp with only {available} tips."} if not ok else {}
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
