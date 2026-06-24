"""OT-2 visual service operations using real LiquidHandler methods.

Each aspirate/dispense triggers a pick-up-tip / return-tip cycle,
producing visible 3D motion in the OT-2 Simulator visualizer.
All functions are sync wrappers around async LiquidHandler calls.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from api_gym.worlds.pylabrobot_lab_v0.state import (
    LabState,
    deck_summary,
    get_well,
    get_well_max_volume,
    get_well_volume,
)
from api_gym.worlds.pylabrobot_lab_v0.state_ot2 import _run_async


AGENT_ACTOR = "agent@pylabrobot-lab.example"
VALID_DECISIONS = {"continue", "hold"}


# ── Inspection (no hardware movement — safe to be sync) ────────────────────


def get_deck_state(lab_state: LabState) -> dict[str, Any]:
    if lab_state.liquid_handler is None:
        return _error("deck_not_found", "Deck state is not initialised.")
    return _ok(deck_summary(lab_state.liquid_handler))


def get_labware_state(lab_state: LabState, labware_id: str) -> dict[str, Any]:
    if lab_state.deck is None:
        return _error("deck_not_found", "Deck state is not initialised.")

    resource = None
    for child in lab_state.deck.children:
        if child.name == labware_id:
            resource = child
            break

    # OTDeck children include Trash etc. — check parent slots too
    if resource is None:
        for child in lab_state.deck.children:
            for grandchild in child.children if hasattr(child, "children") else []:
                if grandchild.name == labware_id:
                    resource = grandchild
                    break
            if resource is not None:
                break

    if resource is None:
        return _error("labware_not_found", "Labware id is not loaded on this deck.",
                      {"labware_id": labware_id})

    data: dict[str, Any] = {
        "id": resource.name,
        "kind": getattr(resource, "category", type(resource).__name__),
        "size": {"x": resource.get_size_x(), "y": resource.get_size_y(), "z": resource.get_size_z()},
        "location": {"x": resource.location.x, "y": resource.location.y, "z": resource.location.z},
    }

    wells: dict[str, dict[str, Any]] = {}
    labware_meta = lab_state.well_metadata.get(labware_id, {})
    for child in resource.children:
        if hasattr(child, "tracker") and hasattr(child.tracker, "get_used_volume"):
            from api_gym.worlds.pylabrobot_lab_v0.services import _short_well_name
            short_name = _short_well_name(child.name)
            well_data: dict[str, Any] = {
                "volume_ul": get_well_volume(child),
                "max_volume_ul": get_well_max_volume(child),
            }
            if short_name in labware_meta:
                well_data["metadata"] = labware_meta[short_name]
            wells[short_name] = well_data

    tips: dict[str, dict[str, Any]] = {}
    for child in resource.children:
        if hasattr(child, "has_tip"):
            from api_gym.worlds.pylabrobot_lab_v0.services import _short_well_name
            short_name = _short_well_name(child.name)
            has_tip_val = child.has_tip() if callable(child.has_tip) else getattr(child, "has_tip", False)
            tips[short_name] = {"has_tip": bool(has_tip_val)}

    if wells:
        data["wells"] = wells
    if tips:
        data["tips"] = tips
    return _ok(data)


# ── Liquid handling (async → visual OT-2 motion) ──────────────────────────


def _find_plate_by_name(deck: Any, name: str) -> Any:
    """Find a plate resource on the deck by name."""
    for child in deck.children:
        if child.name == name:
            return child
        if hasattr(child, "children"):
            for grandchild in child.children:
                if grandchild.name == name:
                    return grandchild
    return None


def aspirate(lab_state: LabState, source: str, volume_ul: float,
             tip_ref: str) -> dict[str, Any]:
    """OT-2 visual aspirate: pick up tip → aspirate."""
    if lab_state.liquid_handler is None or lab_state.deck is None:
        return _error("not_initialised", "Deck / liquid handler not initialised.")

    lh = lab_state.liquid_handler

    from api_gym.worlds.pylabrobot_lab_v0.services import _parse_ref
    source_labware_name, source_well_name = _parse_ref(source)
    tip_rack_name, tip_well_name = _parse_ref(tip_ref)

    source_plate = _find_plate_by_name(lab_state.deck, source_labware_name)
    if source_plate is None:
        return _error("labware_not_found", f"Source labware '{source_labware_name}' not found.")

    src_wells = source_plate[source_well_name]
    if isinstance(src_wells, list):
        if not src_wells:
            return _error("well_not_found", f"Well {source_well_name} not found.")
        src_well = src_wells[0]
    else:
        src_well = src_wells

    src_vol = get_well_volume(src_well)
    if src_vol < volume_ul:
        return _error("insufficient_well_volume", "Not enough volume.",
                      {"available_ul": src_vol, "requested_ul": volume_ul})

    tip_rack = _find_plate_by_name(lab_state.deck, tip_rack_name)
    if tip_rack is None:
        return _error("labware_not_found", f"Tip rack '{tip_rack_name}' not found.")

    tip_spots = tip_rack[tip_well_name]
    if isinstance(tip_spots, list):
        if not tip_spots:
            return _error("tip_not_found", f"Tip {tip_well_name} not found.")
        tip_spot = tip_spots[0]
    else:
        tip_spot = tip_spots

    if callable(tip_spot.has_tip) and not tip_spot.has_tip():
        return _error("tip_not_available", "Tip is not available.")
    if not callable(tip_spot.has_tip) and not getattr(tip_spot, "has_tip", False):
        return _error("tip_not_available", "Tip is not available.")

    try:
        async def _op():
            await lh.pick_up_tips([tip_spot], use_channels=[0])
            await asyncio.sleep(1.5)
            await lh.aspirate([src_well], vols=[volume_ul], use_channels=[0])
            await asyncio.sleep(1.5)

        _run_async(_op())
    except Exception as exc:
        return _error("aspirate_failed", str(exc))

    new_src_vol = get_well_volume(src_well)

    response = {
        "source": source, "volume_ul": volume_ul, "tip": tip_ref,
        "source_remaining_ul": new_src_vol,
    }
    lab_state.transfers.append({"type": "aspirate", **response})
    lab_state.insert_event("transfer.aspirated", "well", source, response)
    return _ok(response)


def dispense(lab_state: LabState, target: str, volume_ul: float,
             mix_after: bool = False) -> dict[str, Any]:
    """OT-2 visual dispense: dispense → return tips."""
    if lab_state.liquid_handler is None or lab_state.deck is None:
        return _error("not_initialised", "Deck / liquid handler not initialised.")

    lh = lab_state.liquid_handler

    from api_gym.worlds.pylabrobot_lab_v0.services import _parse_ref
    target_labware_name, target_well_name = _parse_ref(target)

    target_plate = _find_plate_by_name(lab_state.deck, target_labware_name)
    if target_plate is None:
        return _error("labware_not_found", f"Target labware '{target_labware_name}' not found.")

    tgt_wells = target_plate[target_well_name]
    if isinstance(tgt_wells, list):
        if not tgt_wells:
            return _error("well_not_found", f"Well {target_well_name} not found.")
        tgt_well = tgt_wells[0]
    else:
        tgt_well = tgt_wells

    before_vol = get_well_volume(tgt_well)

    try:
        async def _op():
            await lh.dispense([tgt_well], vols=[volume_ul], use_channels=[0])
            await asyncio.sleep(1.5)
            await lh.return_tips()
            await asyncio.sleep(1.5)

        _run_async(_op())
    except Exception as exc:
        return _error("dispense_failed", str(exc))

    after_vol = get_well_volume(tgt_well)

    response = {
        "target": target, "volume_ul": volume_ul,
        "target_volume_before_ul": before_vol, "target_volume_after_ul": after_vol,
        "mix_after": mix_after,
    }
    lab_state.transfers.append({
        "type": "dispense", "target_well": target, "volume_ul": volume_ul,
    })
    lab_state.insert_event("transfer.dispensed", "well", target, response)
    return _ok(response)


# ── Plate reading / workflow (no hardware motion) ──────────────────────────


def read_absorbance(lab_state: LabState, plate_id: str,
                    wavelength_nm: int, wells: list[str]) -> dict[str, Any]:
    if lab_state.deck is None:
        return _error("not_initialised", "Deck not initialised.")

    plate = _find_plate_by_name(lab_state.deck, plate_id)
    if plate is None:
        return _error("plate_not_found", f"Plate '{plate_id}' is not loaded.")
    if not wells:
        return _error("empty_well_list", "At least one well is required.")

    values: dict[str, float] = {}
    for well_name in wells:
        w = plate[well_name]
        well = w[0] if isinstance(w, list) else w
        vol = get_well_volume(well)
        values[well_name] = 0.82 if vol >= 50.0 else (round(0.82 * vol / 50.0, 4) if vol > 0 else 0.0)

    readout_id = f"ro_{plate_id}_{wavelength_nm}_{len(lab_state.readouts) + 1}"
    readout = {
        "readout_id": readout_id, "plate": plate_id,
        "wavelength_nm": wavelength_nm, "wells": wells, "values": values,
    }
    lab_state.readouts.append(readout)
    lab_state.insert_event("readout.created", "plate", plate_id, readout)
    return _ok(readout)


def add_workflow_note(lab_state: LabState, note: str) -> dict[str, Any]:
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
    decision = decision.strip().lower()
    rationale = rationale.strip()
    if decision not in VALID_DECISIONS:
        return _error("invalid_decision", "Decision must be 'continue' or 'hold'.",
                      {"allowed_decisions": sorted(VALID_DECISIONS)})
    if not rationale:
        return _error("empty_rationale", "Submission rationale must be non-empty.")

    readout = None
    for ro in lab_state.readouts:
        if ro["readout_id"] == evidence_readout_id:
            readout = ro
            break
    if readout is None:
        return _error("readout_not_found", f"Readout '{evidence_readout_id}' does not exist.")

    submission_id = len(lab_state.submissions) + 1
    submission = {
        "submission_id": submission_id, "decision": decision,
        "evidence_readout_id": evidence_readout_id, "target_well": target_well,
        "rationale": rationale,
    }
    lab_state.submissions.append(submission)
    lab_state.insert_event("protocol.submitted", "submission", str(submission_id), submission)
    return _ok(submission)


# ── Helpers ─────────────────────────────────────────────────────────────


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error(code: str, message: str,
           details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details or {}}}
