"""Lab service operations for Hamilton STAR, powered by STARChatterboxBackend.

All operations use PyLabRobot's LiquidHandler API with STAR-specific
features: 96-head parallel pipetting, iSWAP arm, liquid classes, troughs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from api_gym.worlds.pylabrobot_star_v0.state import (
    LabState,
    _run_async,
    deck_summary,
    get_well,
    get_well_volume,
    get_well_max_volume,
)

AGENT_ACTOR = "agent@star-lab.example"
VALID_DECISIONS = {"continue", "hold"}

# ── PLR exception translation (shared pattern with OT-2 world) ──────────

_PLR_ERRORS_LOADED = False
TooLittleLiquidError: Any = Exception
TooLittleVolumeError: Any = Exception
NoTipError: Any = Exception
HasTipError: Any = Exception


def _ensure_plr_errors() -> None:
    global _PLR_ERRORS_LOADED, TooLittleLiquidError, TooLittleVolumeError
    global NoTipError, HasTipError
    if _PLR_ERRORS_LOADED:
        return
    try:
        from pylabrobot.resources.errors import (
            TooLittleLiquidError as _TLLE,
            TooLittleVolumeError as _TLVE,
            NoTipError as _NTE,
            HasTipError as _HTE,
        )
        TooLittleLiquidError = _TLLE
        TooLittleVolumeError = _TLVE
        NoTipError = _NTE
        HasTipError = _HTE
    except ImportError:
        pass
    _PLR_ERRORS_LOADED = True


def _translate_plr_error(exc: Exception) -> dict[str, Any]:
    _ensure_plr_errors()
    if isinstance(exc, TooLittleLiquidError):
        return _error("too_little_liquid", "Insufficient volume.", {"detail": str(exc)})
    if isinstance(exc, TooLittleVolumeError):
        return _error("well_overflow", "Would exceed max volume.", {"detail": str(exc)})
    if isinstance(exc, NoTipError):
        return _error("tip_not_available", "No tip available.", {"detail": str(exc)})
    if isinstance(exc, HasTipError):
        return _error("tip_already_mounted", "Channel already has tip.", {"detail": str(exc)})
    return _error("operation_failed", str(exc))


# ── Inspection ──────────────────────────────────────────────────────────


def get_deck_state(lab_state: LabState) -> dict[str, Any]:
    if lab_state.liquid_handler is None:
        return _error("deck_not_found", "Deck state is not initialised.")
    summary = deck_summary(lab_state.liquid_handler)
    summary["has_96_head"] = lab_state.has_96_head
    summary["has_iswap"] = lab_state.has_iswap
    return _ok(summary)


def get_labware_state(lab_state: LabState, labware_id: str) -> dict[str, Any]:
    if lab_state.deck is None:
        return _error("deck_not_found", "Deck not initialised.")
    resource = _find_resource(lab_state.deck, labware_id)
    if resource is None:
        return _error("labware_not_found",
                      f"Labware '{labware_id}' not found on deck.",
                      {"labware_id": labware_id})

    data: dict[str, Any] = {
        "id": resource.name,
        "kind": getattr(resource, "category", type(resource).__name__),
        "size": {"x": resource.get_size_x(), "y": resource.get_size_y(), "z": resource.get_size_z()},
    }

    # Wells
    wells: dict[str, dict[str, Any]] = {}
    labware_meta = lab_state.well_metadata.get(labware_id, {})
    for child in resource.children if hasattr(resource, "children") else []:
        if hasattr(child, "tracker") and hasattr(child, "max_volume", 0) > 0:
            short = _short_name(child.name)
            wd: dict[str, Any] = {
                "volume_ul": get_well_volume(child),
                "max_volume_ul": get_well_max_volume(child),
            }
            if short in labware_meta:
                wd["metadata"] = labware_meta[short]
            wells[short] = wd

    # Tips
    tips: dict[str, dict[str, Any]] = {}
    for child in resource.children if hasattr(resource, "children") else []:
        if hasattr(child, "has_tip"):
            short = _short_name(child.name)
            has = child.has_tip() if callable(child.has_tip) else getattr(child, "has_tip", False)
            tips[short] = {"has_tip": bool(has)}

    if wells:
        data["wells"] = wells
    if tips:
        data["tips"] = tips
    return _ok(data)


# ── Single-channel liquid handling ──────────────────────────────────────


def aspirate(lab_state: LabState, source: str, volume_ul: float,
             tip_ref: str) -> dict[str, Any]:
    """Single-channel aspirate: pick up tip → aspirate from source."""
    if lab_state.liquid_handler is None or lab_state.deck is None:
        return _error("not_initialised", "Deck / liquid handler not initialised.")

    lh = lab_state.liquid_handler
    src_labware, src_well = _parse_ref(source)
    tip_labware, tip_well = _parse_ref(tip_ref)

    source_plate = _find_resource(lab_state.deck, src_labware)
    if source_plate is None:
        return _error("labware_not_found", f"'{src_labware}' not found.")
    sw = source_plate[src_well]
    src_w = sw[0] if isinstance(sw, list) else sw
    if get_well_volume(src_w) < volume_ul:
        return _error("insufficient_well_volume", "Not enough volume.",
                      {"available_ul": get_well_volume(src_w), "requested_ul": volume_ul})

    tip_rack = _find_resource(lab_state.deck, tip_labware)
    if tip_rack is None:
        return _error("labware_not_found", f"'{tip_labware}' not found.")
    ts = tip_rack[tip_well]
    tip_spot = ts[0] if isinstance(ts, list) else ts
    if callable(tip_spot.has_tip) and not tip_spot.has_tip():
        return _error("tip_not_available", "Tip not available.")

    try:
        async def _op():
            await lh.pick_up_tips([tip_spot], use_channels=[0])
            await asyncio.sleep(1.5)
            await lh.aspirate([src_w], vols=[volume_ul], use_channels=[0])
            await asyncio.sleep(1.5)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    new_vol = get_well_volume(src_w)
    resp = {"source": source, "volume_ul": volume_ul, "tip": tip_ref,
            "source_remaining_ul": new_vol}
    lab_state.transfers.append({"type": "aspirate", **resp})
    lab_state.insert_event("transfer.aspirated", "well", source, resp)
    lab_state.tips_used += 1
    lab_state.clock.advance(3.0)
    return _ok(resp)


def dispense(lab_state: LabState, target: str, volume_ul: float,
             mix_after: bool = False) -> dict[str, Any]:
    """Single-channel dispense: dispense → return tips."""
    if lab_state.liquid_handler is None or lab_state.deck is None:
        return _error("not_initialised", "Deck / liquid handler not initialised.")

    lh = lab_state.liquid_handler
    tgt_labware, tgt_well = _parse_ref(target)
    target_plate = _find_resource(lab_state.deck, tgt_labware)
    if target_plate is None:
        return _error("labware_not_found", f"'{tgt_labware}' not found.")
    tw = target_plate[tgt_well]
    tgt_w = tw[0] if isinstance(tw, list) else tw

    before_vol = get_well_volume(tgt_w)
    try:
        async def _op():
            await lh.dispense([tgt_w], vols=[volume_ul], use_channels=[0])
            await asyncio.sleep(1.5)
            await lh.return_tips()
            await asyncio.sleep(1.5)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    after_vol = get_well_volume(tgt_w)
    resp = {"target": target, "volume_ul": volume_ul,
            "target_volume_before_ul": before_vol,
            "target_volume_after_ul": after_vol, "mix_after": mix_after}
    lab_state.transfers.append({"type": "dispense", "target_well": target, "volume_ul": volume_ul})
    lab_state.insert_event("transfer.dispensed", "well", target, resp)
    lab_state.clock.advance(3.0)
    return _ok(resp)


def discard_tips(lab_state: LabState) -> dict[str, Any]:
    """Discard mounted tips to trash."""
    if lab_state.liquid_handler is None:
        return _error("not_initialised", "Liquid handler not initialised.")
    lh = lab_state.liquid_handler
    try:
        async def _op():
            await lh.discard_tips()
            await asyncio.sleep(1.0)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)
    lab_state.insert_event("tips.discarded", "pipette", "ch0", {})
    lab_state.clock.advance(1.0)
    return _ok({"discarded": True})


# ── 96-head parallel operations ─────────────────────────────────────────

def pick_up_tips96(lab_state: LabState) -> dict[str, Any]:
    """Pick up a full rack of 96 tips using the 96-head."""
    if not lab_state.has_96_head:
        return _error("no_96_head", "96-head is not installed on this STAR.")
    if lab_state.tip_rack is None:
        return _error("no_tip_rack", "No tip rack on deck.")

    lh = lab_state.liquid_handler
    try:
        async def _op():
            await lh.pick_up_tips96(lab_state.tip_rack)
            await asyncio.sleep(2.0)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    lab_state.tips_used += 96
    lab_state.insert_event("tips96.picked_up", "tip_rack", lab_state.tip_rack.name, {})
    lab_state.clock.advance(2.0)
    return _ok({"tips_picked_up": 96})


def aspirate96(lab_state: LabState, plate_id: str, volume_ul: float) -> dict[str, Any]:
    """Aspirate from all 96 wells of a plate simultaneously using the 96-head."""
    if not lab_state.has_96_head:
        return _error("no_96_head", "96-head is not installed.")
    plate = _find_resource(lab_state.deck, plate_id)
    if plate is None:
        return _error("labware_not_found", f"Plate '{plate_id}' not found.")

    lh = lab_state.liquid_handler
    try:
        async def _op():
            await lh.aspirate96(plate, volume=volume_ul)
            await asyncio.sleep(2.0)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    lab_state.transfers.append({"type": "aspirate96", "plate": plate_id, "volume_ul": volume_ul})
    lab_state.insert_event("transfer96.aspirated", "plate", plate_id,
                           {"volume_ul": volume_ul})
    lab_state.clock.advance(2.0)
    return _ok({"plate": plate_id, "volume_ul": volume_ul})


def dispense96(lab_state: LabState, plate_id: str, volume_ul: float) -> dict[str, Any]:
    """Dispense to all 96 wells of a plate simultaneously using the 96-head."""
    if not lab_state.has_96_head:
        return _error("no_96_head", "96-head is not installed.")
    plate = _find_resource(lab_state.deck, plate_id)
    if plate is None:
        return _error("labware_not_found", f"Plate '{plate_id}' not found.")

    lh = lab_state.liquid_handler
    try:
        async def _op():
            await lh.dispense96(plate, volume=volume_ul)
            await asyncio.sleep(2.0)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    lab_state.transfers.append({"type": "dispense96", "plate": plate_id, "volume_ul": volume_ul})
    lab_state.insert_event("transfer96.dispensed", "plate", plate_id,
                           {"volume_ul": volume_ul})
    lab_state.clock.advance(2.0)
    return _ok({"plate": plate_id, "volume_ul": volume_ul})


def discard_tips96(lab_state: LabState) -> dict[str, Any]:
    """Discard 96-head tips to trash."""
    if not lab_state.has_96_head:
        return _error("no_96_head", "96-head is not installed.")
    lh = lab_state.liquid_handler
    try:
        async def _op():
            await lh.discard_tips96()
            await asyncio.sleep(1.0)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)
    lab_state.insert_event("tips96.discarded", "pipette", "96_head", {})
    lab_state.clock.advance(1.0)
    return _ok({"discarded": True})


# ── iSWAP arm operations ────────────────────────────────────────────────


def move_plate(lab_state: LabState, plate_id: str,
               to_position: str) -> dict[str, Any]:
    """Move a plate to a different position on the deck using the iSWAP arm."""
    if not lab_state.has_iswap:
        return _error("no_iswap", "iSWAP arm is not installed on this STAR.")

    plate = _find_resource(lab_state.deck, plate_id)
    if plate is None:
        return _error("labware_not_found", f"Plate '{plate_id}' not found.")

    # Resolve destination: can be a carrier site reference like "carrier_0" or coordinates
    dest = _find_resource(lab_state.deck, to_position)
    lh = lab_state.liquid_handler
    try:
        async def _op():
            await lh.move_plate(plate, dest)
            await asyncio.sleep(3.0)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    lab_state.insert_event("plate.moved", "plate", plate_id,
                           {"from": str(plate.location), "to": to_position})
    lab_state.clock.advance(3.0)
    return _ok({"plate": plate_id, "moved_to": to_position})


# ── Plate reading ───────────────────────────────────────────────────────


def read_absorbance(lab_state: LabState, plate_id: str,
                    wavelength_nm: int, wells: list[str]) -> dict[str, Any]:
    """Simulated absorbance read.  (PlateReader simulation — see projection contract.)"""
    if lab_state.deck is None:
        return _error("not_initialised", "Deck not initialised.")
    plate = _find_resource(lab_state.deck, plate_id)
    if plate is None:
        return _error("plate_not_found", f"Plate '{plate_id}' not loaded.")
    if not wells:
        return _error("empty_well_list", "At least one well required.")

    # Apply noise schedule if available
    noise_schedule = getattr(lab_state, "_noise_schedule", None)
    readout_index = len(lab_state.readouts) + 1

    values: dict[str, float] = {}
    for well_name in wells:
        w = plate[well_name]
        well = w[0] if isinstance(w, list) else w
        vol = get_well_volume(well)
        base = 0.82 if vol >= 50.0 else (round(0.82 * vol / 50.0, 4) if vol > 0 else 0.0)
        noise = 0.0
        if noise_schedule is not None:
            noise = noise_schedule.get_noise(plate_id, wavelength_nm, well_name, readout_index)
        values[well_name] = round(max(0.0, base + noise), 4)

    readout_id = f"ro_{plate_id}_{wavelength_nm}_{readout_index}"
    readout = {"readout_id": readout_id, "plate": plate_id,
               "wavelength_nm": wavelength_nm, "wells": wells, "values": values}
    lab_state.readouts.append(readout)
    lab_state.insert_event("readout.created", "plate", plate_id, readout)
    lab_state.clock.advance(5.0)
    return _ok(readout)


# ── Workflow ────────────────────────────────────────────────────────────


def add_workflow_note(lab_state: LabState, note: str) -> dict[str, Any]:
    note = note.strip()
    if not note:
        return _error("empty_note", "Note must be non-empty.")
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
        return _error("invalid_decision",
                      "Decision must be 'continue' or 'hold'.",
                      {"allowed_decisions": sorted(VALID_DECISIONS)})
    if not rationale:
        return _error("empty_rationale", "Rationale must be non-empty.")

    readout = None
    for ro in lab_state.readouts:
        if ro["readout_id"] == evidence_readout_id:
            readout = ro
            break
    if readout is None:
        return _error("readout_not_found", f"Readout '{evidence_readout_id}' not found.")

    submission_id = len(lab_state.submissions) + 1
    submission = {"submission_id": submission_id, "decision": decision,
                  "evidence_readout_id": evidence_readout_id,
                  "target_well": target_well, "rationale": rationale}
    lab_state.submissions.append(submission)
    lab_state.insert_event("protocol.submitted", "submission", str(submission_id), submission)
    return _ok(submission)


# ── Helpers ─────────────────────────────────────────────────────────────


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error(code: str, message: str,
           details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details or {}}}


def _parse_ref(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError(f"Invalid reference '{value}': expected 'labware_id:well_id'")
    parts = value.split(":", 1)
    return parts[0], parts[1]


def _find_resource(deck: Any, name: str) -> Any:
    """Find a resource by name, searching recursively through carriers."""
    for child in deck.children:
        if child.name == name:
            return child
        if hasattr(child, "children"):
            for grandchild in child.children:
                if grandchild.name == name:
                    return grandchild
                if hasattr(grandchild, "children"):
                    for gg in grandchild.children:
                        if gg.name == name:
                            return gg
    return None


def _short_name(full_name: str) -> str:
    """Extract short well/tip name from PLR full name."""
    parts = full_name.rsplit("_well_", 1)
    if len(parts) == 2:
        return parts[1]
    parts = full_name.rsplit("_tipspot_", 1)
    if len(parts) == 2:
        return parts[1]
    return full_name.rsplit("_", 1)[-1]
