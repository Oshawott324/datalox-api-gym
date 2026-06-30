"""Lab service operations wrapping PyLabRobot standard API.

All operations target the in-memory LabState (Deck + LiquidHandler).
The chatterbox backend simulates everything — no real hardware.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api_gym.worlds.pylabrobot_lab_v0.state import (
    LabState,
    deck_summary,
    get_well,
    get_well_max_volume,
    get_well_volume,
    has_tip,
)

AGENT_ACTOR = "agent@pylabrobot-lab.example"
VALID_DECISIONS = {"continue", "hold"}


# ── Inspection ──────────────────────────────────────────────────────────


def get_deck_state(lab_state: LabState) -> dict[str, Any]:
    """Inspect the dry-run deck and instruments."""
    if lab_state.liquid_handler is None:
        return _error("deck_not_found", "Deck state is not initialised.")
    return _ok(deck_summary(lab_state.liquid_handler))


def get_labware_state(lab_state: LabState, labware_id: str) -> dict[str, Any]:
    """Inspect one loaded labware object (plate or tip rack)."""
    if lab_state.deck is None:
        return _error("deck_not_found", "Deck state is not initialised.")

    resource = None
    for child in lab_state.deck.children:
        if child.name == labware_id:
            resource = child
            break

    if resource is None:
        return _error(
            "labware_not_found",
            "Labware id is not loaded on this deck.",
            {"labware_id": labware_id},
        )

    data: dict[str, Any] = {
        "id": resource.name,
        "kind": getattr(resource, "category", type(resource).__name__),
        "size": {
            "x": resource.get_size_x(),
            "y": resource.get_size_y(),
            "z": resource.get_size_z(),
        },
        "location": {
            "x": resource.location.x,
            "y": resource.location.y,
            "z": resource.location.z,
        },
    }

    # Wells (only for resources with VolumeTracker, not TipSpot)
    wells: dict[str, dict[str, Any]] = {}
    labware_meta = lab_state.well_metadata.get(labware_id, {})
    for child in resource.children:
        if hasattr(child, "tracker") and hasattr(child.tracker, "get_used_volume"):
            short_name = _short_well_name(child.name)
            well_data: dict[str, Any] = {
                "volume_ul": get_well_volume(child),
                "max_volume_ul": get_well_max_volume(child),
            }
            if short_name in labware_meta:
                well_data["metadata"] = labware_meta[short_name]
            wells[short_name] = well_data

    # Tips (TipSpot resources)
    tips: dict[str, dict[str, Any]] = {}
    for child in resource.children:
        if hasattr(child, "has_tip"):
            short_name = _short_well_name(child.name)
            has_tip_val = child.has_tip() if callable(child.has_tip) else getattr(child, "has_tip", False)
            tips[short_name] = {"has_tip": bool(has_tip_val)}

    if wells:
        data["wells"] = wells
    if tips:
        data["tips"] = tips

    return _ok(data)


# ── Liquid handling ─────────────────────────────────────────────────────

# PyLabRobot's LiquidHandler head setup is complex and hardware-specific.
# For dry-run simulation we bypass the LiquidHandler and directly
# manipulate Well VolumeTrackers — functionally equivalent and much simpler.


def aspirate(lab_state: LabState, source: str, volume_ul: float,
             tip_ref: str) -> dict[str, Any]:
    """Aspirate from a source well using a specified tip (dry-run)."""
    if lab_state.deck is None:
        return _error("not_initialised", "Deck not initialised.")

    source_labware_name, source_well_name = _parse_ref(source)
    tip_rack_name, tip_well_name = _parse_ref(tip_ref)

    # Find source well
    source_plate = _find_child(lab_state.deck, source_labware_name)
    if source_plate is None:
        return _error("labware_not_found", f"Source labware '{source_labware_name}' not found.")

    src_well = get_well(source_plate, source_well_name)
    src_vol = get_well_volume(src_well)
    if src_vol < volume_ul:
        return _error(
            "insufficient_well_volume",
            "Source well does not contain enough volume.",
            {"available_ul": src_vol, "requested_ul": volume_ul},
        )

    # Find and reserve tip
    tip_rack = _find_child(lab_state.deck, tip_rack_name)
    if tip_rack is None:
        return _error("labware_not_found", f"Tip rack '{tip_rack_name}' not found.")

    tip_spot = get_well(tip_rack, tip_well_name)
    if not (callable(tip_spot.has_tip) and tip_spot.has_tip()) or not getattr(tip_spot, "has_tip", False):
        return _error("tip_not_available", "Tip is not available or already used.")

    # Mark tip as used
    if hasattr(tip_spot, "_has_tip"):
        tip_spot._has_tip = False

    # Transfer volume: decrease source, track in pipette
    new_src_vol = src_vol - volume_ul
    if hasattr(src_well, "tracker") and src_well.tracker is not None:
        src_well.tracker.set_volume(new_src_vol)

    # Record pipette pending volume
    lab_state._pending_volume_ul = volume_ul
    lab_state._pending_tip = tip_ref
    lab_state.tips_used += 1

    response = {
        "source": source,
        "volume_ul": volume_ul,
        "tip": tip_ref,
        "source_remaining_ul": new_src_vol,
    }
    lab_state.transfers.append({"type": "aspirate", **response})
    lab_state.insert_event("transfer.aspirated", "well", source, response)
    return _ok(response)


def dispense(lab_state: LabState, target: str, volume_ul: float,
             mix_after: bool = False) -> dict[str, Any]:
    """Dispense pending aspirated volume into a target well (dry-run)."""
    if lab_state.deck is None:
        return _error("not_initialised", "Deck not initialised.")

    pending = getattr(lab_state, "_pending_volume_ul", 0.0)
    if pending <= 0:
        return _error("no_aspirated_volume", "No aspirated volume is pending.")

    if volume_ul > pending:
        return _error(
            "dispense_exceeds_aspirated_volume",
            "Dispense volume exceeds pending aspirated volume.",
            {"available_ul": pending, "requested_ul": volume_ul},
        )

    target_labware_name, target_well_name = _parse_ref(target)
    target_plate = _find_child(lab_state.deck, target_labware_name)
    if target_plate is None:
        return _error("labware_not_found", f"Target labware '{target_labware_name}' not found.")

    tgt_well = get_well(target_plate, target_well_name)
    before_vol = get_well_volume(tgt_well)

    # Transfer: decrease pending, increase target
    after_vol = before_vol + volume_ul
    if after_vol > get_well_max_volume(tgt_well):
        return _error(
            "well_overflow",
            "Dispense would exceed well maximum volume.",
            {"max_ul": get_well_max_volume(tgt_well), "would_be": after_vol},
        )

    if hasattr(tgt_well, "tracker") and tgt_well.tracker is not None:
        tgt_well.tracker.set_volume(after_vol)

    remaining = pending - volume_ul
    lab_state._pending_volume_ul = remaining

    response = {
        "target": target,
        "volume_ul": volume_ul,
        "target_volume_before_ul": before_vol,
        "target_volume_after_ul": after_vol,
        "remaining_aspirated_volume_ul": remaining,
        "mix_after": mix_after,
    }
    lab_state.transfers.append({
        "type": "dispense",
        "source_well": getattr(lab_state, "_pending_tip", "pipette"),
        "target_well": target,
        "volume_ul": volume_ul,
    })
    lab_state.insert_event("transfer.dispensed", "well", target, response)
    return _ok(response)


def discard_tips(lab_state: LabState) -> dict[str, Any]:
    """Discard currently mounted tips to trash (chatterbox dry-run).

    Clears any pending aspirated volume and resets tip tracking.
    """
    pending = getattr(lab_state, "_pending_volume_ul", 0.0)
    tip = getattr(lab_state, "_pending_tip", None)
    lab_state._pending_volume_ul = 0.0
    lab_state._pending_tip = None
    lab_state.insert_event("tips.discarded", "pipette", "channel_0",
                           {"pending_volume_discarded_ul": pending, "tip": tip})
    return _ok({"discarded": True, "pending_volume_discarded_ul": pending, "tip": tip})


# ── Plate reading ───────────────────────────────────────────────────────


def read_absorbance(lab_state: LabState, plate_id: str,
                    wavelength_nm: int, wells: list[str]) -> dict[str, Any]:
    """Create a simulated absorbance readout for plate wells."""
    if lab_state.deck is None:
        return _error("not_initialised", "Deck not initialised.")

    plate = _find_child(lab_state.deck, plate_id)
    if plate is None:
        return _error("plate_not_found", f"Plate '{plate_id}' is not loaded.")
    if getattr(plate, "category", "") != "plate":
        return _error("not_a_plate", f"'{plate_id}' is not a plate (category={getattr(plate, 'category', '?')}).")
    if not wells:
        return _error("empty_well_list", "At least one well is required.")

    # Check well exists and compute values
    values: dict[str, float] = {}
    for well_name in wells:
        well = get_well(plate, well_name)
        vol = get_well_volume(well)
        # Simulated OD600: proportional to volume, capped at control band
        if vol >= 50.0:
            values[well_name] = 0.82  # expected control value
        elif vol > 0:
            values[well_name] = round(0.82 * vol / 50.0, 4)
        else:
            values[well_name] = 0.0

    readout_id = f"ro_{plate_id}_{wavelength_nm}_{len(lab_state.readouts) + 1}"
    readout = {
        "readout_id": readout_id,
        "plate": plate_id,
        "wavelength_nm": wavelength_nm,
        "wells": wells,
        "values": values,
    }
    lab_state.readouts.append(readout)
    lab_state.insert_event("readout.created", "plate", plate_id, readout)
    return _ok(readout)


# ── Workflow ────────────────────────────────────────────────────────────


def add_workflow_note(lab_state: LabState, note: str) -> dict[str, Any]:
    """Add a workflow note."""
    note = note.strip()
    if not note:
        return _error("empty_note", "Workflow note must be non-empty.")
    note_id = len(lab_state.notes) + 1
    lab_state.notes.append(note)
    lab_state.insert_event("workflow_note.created", "note", str(note_id), {"note": note})
    return _ok({"note_id": note_id, "note": note})


def submit_protocol(lab_state: LabState, decision: str,
                    evidence_readout_id: str, target_well: str,
                    rationale: str) -> dict[str, Any]:
    """Submit a final protocol decision with readout evidence."""
    decision = decision.strip().lower()
    rationale = rationale.strip()

    if decision not in VALID_DECISIONS:
        return _error(
            "invalid_decision",
            "Decision must be 'continue' or 'hold'.",
            {"allowed_decisions": sorted(VALID_DECISIONS)},
        )
    if not rationale:
        return _error("empty_rationale", "Submission rationale must be non-empty.")

    # Verify readout exists
    readout = None
    for ro in lab_state.readouts:
        if ro["readout_id"] == evidence_readout_id:
            readout = ro
            break
    if readout is None:
        return _error("readout_not_found", f"Readout '{evidence_readout_id}' does not exist.")

    submission_id = len(lab_state.submissions) + 1
    submission = {
        "submission_id": submission_id,
        "decision": decision,
        "evidence_readout_id": evidence_readout_id,
        "target_well": target_well,
        "rationale": rationale,
    }
    lab_state.submissions.append(submission)
    lab_state.insert_event("protocol.submitted", "submission", str(submission_id), submission)
    return _ok(submission)


# ── Helpers ─────────────────────────────────────────────────────────────


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details or {}}}


def _parse_ref(value: str) -> tuple[str, str]:
    """Parse 'labware_id:well_id' into (labware_id, well_id)."""
    if ":" not in value:
        raise ValueError(f"Invalid reference '{value}': expected 'labware_id:well_id'")
    parts = value.split(":", 1)
    return parts[0], parts[1]


def _find_child(deck: Any, name: str) -> Any:
    """Find a child resource by name on the deck."""
    for child in deck.children:
        if child.name == name:
            return child
    return None


def _short_well_name(full_name: str) -> str:
    """Extract short well name from PyLabRobot's full well name.

    E.g. 'assay_plate_well_A1' → 'A1'.
    """
    # Try to find pattern like 'well_A1' at the end
    parts = full_name.rsplit("_well_", 1)
    if len(parts) == 2:
        return parts[1]
    # Fallback: last segment after underscore
    return full_name.rsplit("_", 1)[-1]
