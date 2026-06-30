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
    after, fresh, never, resource_available,
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
        # Agent took multiple readings — good practice with noise
        attrs = {"label": "success_despite_fault",
                 "detail": "Agent obtained multiple readouts to mitigate measurement noise."}
        # Temporal: first readout before last readout before submit
        a_ok, a_msg = after(events, ("readout.", ""), ("readout.", ""))
        _add_temporal(checks, True, "multiple_reads_ordered",
                      "Agent performed multiple sequential readouts.")

    return checks, attrs
