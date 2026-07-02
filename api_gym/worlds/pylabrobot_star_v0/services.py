"""Lab service operations for Hamilton STAR, powered by STARDryRunBackend.

Every liquid-handling, tip, and resource-movement operation is a thin
wrapper around the corresponding ``LiquidHandler`` method from PyLabRobot.
VolumeTracker and TipTracker updates happen automatically inside
``LiquidHandler`` (when ``does_volume_tracking()`` is True).

String references (``"plate:well"``, ``"tip_rack:A1"``) are resolved to PLR
resource objects before the PLR call.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

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

# ── PLR exception translation ────────────────────────────────────────────

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


# ── Resource resolution ──────────────────────────────────────────────────


def _resolve_well(lab_state: LabState, ref: str) -> Any:
    """Resolve 'labware:well' → PLR Well/Container object."""
    labware_name, well_name = _parse_ref(ref)
    resource = _find_resource(lab_state.deck, labware_name)
    if resource is None:
        raise KeyError(f"Labware '{labware_name}' not found on deck.")
    wells = resource[well_name]
    return wells[0] if isinstance(wells, list) else wells


def _resolve_tip_spot(lab_state: LabState, ref: str) -> Any:
    """Resolve 'tip_rack:spot' → PLR TipSpot object."""
    labware_name, spot_name = _parse_ref(ref)
    resource = _find_resource(lab_state.deck, labware_name)
    if resource is None:
        raise KeyError(f"Tip resource '{labware_name}' not found on deck.")
    spots = resource[spot_name]
    return spots[0] if isinstance(spots, list) else spots


def _resolve_resource(lab_state: LabState, name: str) -> Any:
    """Resolve a resource name → PLR Resource object."""
    resource = _find_resource(lab_state.deck, name)
    if resource is None:
        raise KeyError(f"Resource '{name}' not found on deck.")
    return resource


# ── Inspection ──────────────────────────────────────────────────────────


def get_deck_state(lab_state: LabState) -> dict[str, Any]:
    """Return a summary of the STAR deck: carriers, labware, instruments."""
    if lab_state.liquid_handler is None:
        return _error("deck_not_found", "Deck state is not initialised.")
    summary = deck_summary(lab_state.liquid_handler)
    summary["has_96_head"] = lab_state.has_96_head
    summary["has_iswap"] = lab_state.has_iswap
    return _ok(summary)


def get_labware_state(lab_state: LabState, labware_id: str) -> dict[str, Any]:
    """Inspect one labware item: wells (volumes) and tips (presence)."""
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
        "size": {"x": resource.get_size_x(), "y": resource.get_size_y(),
                 "z": resource.get_size_z()},
    }

    # Wells
    wells: dict[str, dict[str, Any]] = {}
    labware_meta = lab_state.well_metadata.get(labware_id, {})
    for child in resource.children if hasattr(resource, "children") else []:
        if hasattr(child, "tracker") and hasattr(child, "max_volume"):
            mx = child.max_volume if isinstance(child.max_volume, (int, float)) else 0
            if mx > 0:
                short = _short_name(child.name)
                wd: dict[str, Any] = {
                    "volume_ul": get_well_volume(child),
                    "max_volume_ul": mx,
                }
                if short in labware_meta:
                    wd["metadata"] = labware_meta[short]
                wells[short] = wd

    # Tips
    tips: dict[str, dict[str, Any]] = {}
    for child in resource.children if hasattr(resource, "children") else []:
        if hasattr(child, "has_tip"):
            short = _short_name(child.name)
            has = child.has_tip() if callable(child.has_tip) else bool(getattr(child, "has_tip", False))
            tips[short] = {"has_tip": has}

    if wells:
        data["wells"] = wells
    if tips:
        data["tips"] = tips
    return _ok(data)


def get_mounted_tips(lab_state: LabState) -> dict[str, Any]:
    """Return what tips are currently mounted on the pipetting channels.

    PLR: ``LiquidHandler.get_mounted_tips()``.
    """
    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")
    mounted = lh.get_mounted_tips()
    channels: dict[str, Any] = {}
    for i, tip in enumerate(mounted):
        channels[f"ch{i}"] = {
            "has_tip": tip is not None,
            "tip_type": type(tip).__name__ if tip else None,
        }
    lab_state.insert_event("inspection.mounted_tips", "pipette", "", {"channels": channels})
    return _ok({"channels": channels})


# ── Single-channel tip operations ───────────────────────────────────────


def pick_up_tips(lab_state: LabState, tip_refs: list[str],
                 channels: list[int] | None = None) -> dict[str, Any]:
    """Pick up tips onto specified channels.

    PLR: ``LiquidHandler.pick_up_tips(tip_spots, use_channels)``.

    Args:
        tip_refs: List of ``\"tip_rack:well\"`` references, one per channel.
        channels: Channel indices (default [0, 1, ..., len(tip_refs)-1]).
    """
    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    if channels is None:
        channels = list(range(len(tip_refs)))

    tip_spots = [_resolve_tip_spot(lab_state, ref) for ref in tip_refs]

    try:
        async def _op():
            await lh.pick_up_tips(tip_spots, use_channels=channels)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    lab_state.tips_used += len(tip_refs)
    resp = {"tip_refs": tip_refs, "channels": channels}
    lab_state.insert_event("tips.picked_up", "pipette", ",".join(map(str, channels)), resp)
    lab_state.clock.advance(2.0)
    return _ok(resp)


def drop_tips(lab_state: LabState, tip_refs: list[str],
              channels: list[int] | None = None) -> dict[str, Any]:
    """Drop tips back to specified tip spots.

    PLR: ``LiquidHandler.drop_tips(tip_spots, use_channels)``.
    """
    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    if channels is None:
        channels = list(range(len(tip_refs)))

    tip_spots = [_resolve_tip_spot(lab_state, ref) for ref in tip_refs]

    try:
        async def _op():
            await lh.drop_tips(tip_spots, use_channels=channels)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    resp = {"tip_refs": tip_refs, "channels": channels}
    lab_state.insert_event("tips.dropped", "pipette", ",".join(map(str, channels)), resp)
    lab_state.clock.advance(2.0)
    return _ok(resp)


def discard_tips(lab_state: LabState,
                 channels: list[int] | None = None) -> dict[str, Any]:
    """Discard currently mounted tips to the trash area.

    PLR: ``LiquidHandler.discard_tips(use_channels)``.
    """
    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    try:
        async def _op():
            await lh.discard_tips(use_channels=channels)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    ch = channels or list(range(lh.backend.num_channels))
    lab_state.insert_event("tips.discarded", "pipette", ",".join(map(str, ch)), {})
    lab_state.clock.advance(1.0)
    return _ok({"discarded": True, "channels": ch})


def return_tips(lab_state: LabState,
                channels: list[int] | None = None) -> dict[str, Any]:
    """Return tips to their original rack positions.

    PLR: ``LiquidHandler.return_tips(use_channels)``.
    """
    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    try:
        async def _op():
            await lh.return_tips(use_channels=channels)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    ch = channels or list(range(lh.backend.num_channels))
    lab_state.insert_event("tips.returned", "pipette", ",".join(map(str, ch)), {})
    lab_state.clock.advance(2.0)
    return _ok({"returned": True, "channels": ch})


# ── Single-channel liquid operations ────────────────────────────────────


def aspirate(lab_state: LabState, source: str, volume_ul: float,
             channel: int = 0) -> dict[str, Any]:
    """Aspirate liquid from a source well.

    PLR: ``LiquidHandler.aspirate([well], vols=[volume_ul], use_channels=[channel])``.

    Args:
        source: Well reference (``\"plate:well\"``).
        volume_ul: Volume in microlitres.
        channel: Which pipetting channel to use (default 0).
    """
    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    src_well = _resolve_well(lab_state, source)
    src_vol_before = get_well_volume(src_well)

    if src_vol_before < volume_ul:
        return _error("insufficient_well_volume", "Not enough volume.",
                      {"available_ul": src_vol_before, "requested_ul": volume_ul})

    try:
        async def _op():
            await lh.aspirate([src_well], vols=[volume_ul], use_channels=[channel])
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    src_vol_after = get_well_volume(src_well)
    resp = {"source": source, "volume_ul": volume_ul, "channel": channel,
            "source_remaining_ul": src_vol_after}
    lab_state.transfers.append({"type": "aspirate", **resp})
    lab_state.insert_event("transfer.aspirated", "well", source, resp)
    lab_state.clock.advance(3.0)
    return _ok(resp)


def dispense(lab_state: LabState, target: str, volume_ul: float,
             channel: int = 0, mix_after: bool = False) -> dict[str, Any]:
    """Dispense liquid into a target well.

    PLR: ``LiquidHandler.dispense([well], vols=[volume_ul], use_channels=[channel])``.

    Args:
        target: Well reference (``\"plate:well\"``).
        volume_ul: Volume in microlitres.
        channel: Which pipetting channel to use (default 0).
        mix_after: Whether to mix after dispensing (PLR Mix parameter).
    """
    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    tgt_well = _resolve_well(lab_state, target)
    before_vol = get_well_volume(tgt_well)
    max_vol = get_well_max_volume(tgt_well)

    if before_vol + volume_ul > max_vol:
        return _error("well_overflow",
                      f"Dispense would exceed max volume ({max_vol}uL).",
                      {"max_ul": max_vol, "would_be": before_vol + volume_ul})

    try:
        async def _op():
            await lh.dispense([tgt_well], vols=[volume_ul], use_channels=[channel])
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    after_vol = get_well_volume(tgt_well)
    resp = {"target": target, "volume_ul": volume_ul, "channel": channel,
            "target_volume_before_ul": before_vol,
            "target_volume_after_ul": after_vol, "mix_after": mix_after}
    lab_state.transfers.append({"type": "dispense", "target_well": target,
                                "volume_ul": volume_ul})
    lab_state.insert_event("transfer.dispensed", "well", target, resp)
    lab_state.clock.advance(3.0)
    return _ok(resp)


# ── 96-head parallel operations ─────────────────────────────────────────


def pick_up_tips96(lab_state: LabState, tip_rack_id: str) -> dict[str, Any]:
    """Pick up a full rack of 96 tips using the 96-channel head.

    PLR: ``LiquidHandler.pick_up_tips96(tip_rack)``.
    """
    if not lab_state.has_96_head:
        return _error("no_96_head", "96-head is not installed on this STAR.")

    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    tip_rack = _resolve_resource(lab_state, tip_rack_id)

    try:
        async def _op():
            await lh.pick_up_tips96(tip_rack)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    lab_state.tips_used += 96
    resp = {"tip_rack": tip_rack_id, "tips_picked_up": 96}
    lab_state.insert_event("tips96.picked_up", "tip_rack", tip_rack_id, resp)
    lab_state.clock.advance(2.0)
    return _ok(resp)


def drop_tips96(lab_state: LabState, target: str = "trash") -> dict[str, Any]:
    """Drop 96-head tips to a tip rack or trash.

    PLR: ``LiquidHandler.drop_tips96(resource)``.

    Args:
        target: ``\"trash\"`` or a tip rack name on the deck.
    """
    if not lab_state.has_96_head:
        return _error("no_96_head", "96-head is not installed on this STAR.")

    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    if target.lower() == "trash":
        resource = lh.deck.get_trash_area96()
    else:
        resource = _resolve_resource(lab_state, target)

    try:
        async def _op():
            await lh.drop_tips96(resource)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    resp = {"target": target}
    lab_state.insert_event("tips96.dropped", "pipette", "96_head", resp)
    lab_state.clock.advance(2.0)
    return _ok(resp)


def discard_tips96(lab_state: LabState) -> dict[str, Any]:
    """Discard 96-head tips to the trash area.

    PLR: ``LiquidHandler.discard_tips96()``.
    """
    if not lab_state.has_96_head:
        return _error("no_96_head", "96-head is not installed on this STAR.")

    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    try:
        async def _op():
            await lh.discard_tips96()
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    lab_state.insert_event("tips96.discarded", "pipette", "96_head", {})
    lab_state.clock.advance(1.0)
    return _ok({"discarded": True})


def aspirate96(lab_state: LabState, plate_id: str,
               volume_ul: float) -> dict[str, Any]:
    """Aspirate from all 96 wells of a plate simultaneously.

    PLR: ``LiquidHandler.aspirate96(plate, volume)``.
    """
    if not lab_state.has_96_head:
        return _error("no_96_head", "96-head is not installed on this STAR.")

    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    plate = _resolve_resource(lab_state, plate_id)

    try:
        async def _op():
            await lh.aspirate96(plate, volume=volume_ul)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    resp = {"plate": plate_id, "volume_ul": volume_ul}
    lab_state.transfers.append({"type": "aspirate96", **resp})
    lab_state.insert_event("transfer96.aspirated", "plate", plate_id, resp)
    lab_state.clock.advance(2.0)
    return _ok(resp)


def dispense96(lab_state: LabState, plate_id: str,
               volume_ul: float) -> dict[str, Any]:
    """Dispense to all 96 wells of a plate simultaneously.

    PLR: ``LiquidHandler.dispense96(plate, volume)``.
    """
    if not lab_state.has_96_head:
        return _error("no_96_head", "96-head is not installed on this STAR.")

    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    plate = _resolve_resource(lab_state, plate_id)

    try:
        async def _op():
            await lh.dispense96(plate, volume=volume_ul)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    resp = {"plate": plate_id, "volume_ul": volume_ul}
    lab_state.transfers.append({"type": "dispense96", **resp})
    lab_state.insert_event("transfer96.dispensed", "plate", plate_id, resp)
    lab_state.clock.advance(2.0)
    return _ok(resp)


# ── iSWAP / robotic arm operations ──────────────────────────────────────


def move_plate(lab_state: LabState, plate_id: str,
               to_position: str) -> dict[str, Any]:
    """Move a plate using the iSWAP robotic arm.

    PLR: ``LiquidHandler.move_plate(plate, to)``.
    """
    if not lab_state.has_iswap:
        return _error("no_iswap", "iSWAP arm is not installed on this STAR.")

    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    plate = _resolve_resource(lab_state, plate_id)
    dest = _resolve_resource(lab_state, to_position)

    try:
        async def _op():
            await lh.move_plate(plate, to=dest)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    resp = {"plate": plate_id, "moved_to": to_position}
    lab_state.insert_event("plate.moved", "plate", plate_id, resp)
    lab_state.clock.advance(3.0)
    return _ok(resp)


def move_lid(lab_state: LabState, plate_id: str,
             to_position: str) -> dict[str, Any]:
    """Move a plate's lid using the iSWAP robotic arm.

    PLR: ``LiquidHandler.move_lid(lid, to)``.
    """
    if not lab_state.has_iswap:
        return _error("no_iswap", "iSWAP arm is not installed on this STAR.")

    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    plate = _resolve_resource(lab_state, plate_id)
    if not hasattr(plate, "lid") or plate.lid is None:
        return _error("no_lid", f"Plate '{plate_id}' has no lid.")

    dest = _resolve_resource(lab_state, to_position)

    try:
        async def _op():
            await lh.move_lid(plate.lid, to=dest)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    resp = {"plate": plate_id, "lid_moved_to": to_position}
    lab_state.insert_event("lid.moved", "lid", plate_id, resp)
    lab_state.clock.advance(3.0)
    return _ok(resp)


def move_resource(lab_state: LabState, resource_id: str,
                  to_position: str) -> dict[str, Any]:
    """Move any deck resource using the iSWAP robotic arm.

    PLR: ``LiquidHandler.move_resource(resource, to)``.
    """
    if not lab_state.has_iswap:
        return _error("no_iswap", "iSWAP arm is not installed on this STAR.")

    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    resource = _resolve_resource(lab_state, resource_id)
    dest = _resolve_resource(lab_state, to_position)

    try:
        async def _op():
            await lh.move_resource(resource, to=dest)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    resp = {"resource": resource_id, "moved_to": to_position}
    lab_state.insert_event("resource.moved", "resource", resource_id, resp)
    lab_state.clock.advance(3.0)
    return _ok(resp)


# ── Convenience transfers ────────────────────────────────────────────────


def transfer(lab_state: LabState, source: str, targets: list[str],
             volume_ul: float, channel: int = 0) -> dict[str, Any]:
    """Multi-dispense: aspirate once, dispense to multiple targets.

    PLR: ``LiquidHandler.transfer(source, targets, target_vols=...)``.

    Args:
        source: Source well reference.
        targets: List of target well references.
        volume_ul: Volume to dispense to each target.
        channel: Pipetting channel to use.
    """
    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    src_well = _resolve_well(lab_state, source)
    tgt_wells = [_resolve_well(lab_state, t) for t in targets]

    total_vol = volume_ul * len(targets)
    src_vol_before = get_well_volume(src_well)
    if src_vol_before < total_vol:
        return _error("insufficient_well_volume",
                      f"Need {total_vol}uL total, only {src_vol_before}uL available.",
                      {"available_ul": src_vol_before, "requested_total_ul": total_vol})

    try:
        async def _op():
            await lh.transfer(
                src_well, tgt_wells,
                target_vols=[volume_ul] * len(targets),
                aspiration_flow_rate=None,
                dispense_flow_rates=None,
            )
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    resp = {"source": source, "targets": targets, "volume_per_target_ul": volume_ul,
            "total_volume_ul": total_vol}
    lab_state.transfers.append({"type": "transfer", **resp})
    lab_state.insert_event("transfer.completed", "well", source, resp)
    lab_state.clock.advance(3.0 * (len(targets) + 1))
    return _ok(resp)


def stamp(lab_state: LabState, source_plate: str, target_plate: str,
          volume_ul: float) -> dict[str, Any]:
    """Full-plate 96-to-96 stamp / replicate.

    PLR: ``LiquidHandler.stamp(source, target, volume)``.

    Requires 96-head.
    """
    if not lab_state.has_96_head:
        return _error("no_96_head", "96-head is required for plate stamping.")

    lh = lab_state.liquid_handler
    if lh is None:
        return _error("not_initialised", "Liquid handler not initialised.")

    src = _resolve_resource(lab_state, source_plate)
    tgt = _resolve_resource(lab_state, target_plate)

    try:
        async def _op():
            await lh.stamp(src, tgt, volume=volume_ul)
        _run_async(_op())
    except Exception as exc:
        return _translate_plr_error(exc)

    resp = {"source_plate": source_plate, "target_plate": target_plate,
            "volume_ul": volume_ul}
    lab_state.transfers.append({"type": "stamp", **resp})
    lab_state.insert_event("stamp.completed", "plate", source_plate, resp)
    lab_state.clock.advance(5.0)
    return _ok(resp)


# ── Plate reading ───────────────────────────────────────────────────────


def read_absorbance(lab_state: LabState, plate_id: str,
                    wavelength_nm: int, wells: list[str]) -> dict[str, Any]:
    """Simulated absorbance read (plate reader simulation).

    Supports fault injection via ``FaultSchedule``: if a fault is scheduled
    for this readout attempt, returns an 'instrument_busy' error instead of
    a valid reading.  The agent must retry.
    """
    if lab_state.deck is None:
        return _error("not_initialised", "Deck not initialised.")
    plate_resource = _find_resource(lab_state.deck, plate_id)
    if plate_resource is None:
        return _error("plate_not_found", f"Plate '{plate_id}' not loaded.")
    if not wells:
        return _error("empty_well_list", "At least one well required.")

    # ── Fault injection ──────────────────────────────────────────────
    fault_schedule = getattr(lab_state, "_fault_schedule", None)
    if fault_schedule is not None:
        fkey = f"{plate_id}:{wavelength_nm}"
        attempts = getattr(lab_state, "_fault_attempts", {})
        attempt = attempts.get(fkey, 0) + 1
        attempts[fkey] = attempt
        lab_state._fault_attempts = attempts

        max_retries = fault_schedule.max_retries
        if fault_schedule.should_fault(plate_id, wavelength_nm, attempt):
            lab_state.insert_event("error.instrument_busy", "plate_reader", plate_id,
                                   {"attempt": attempt, "max_retries": max_retries})
            lab_state.clock.advance(3.0)
            if attempt <= max_retries:
                return _error("instrument_busy",
                              f"Plate reader busy on attempt {attempt}/{max_retries}. Retry available.",
                              {"attempt": attempt, "max_retries": max_retries,
                               "retry_available": True})
            else:
                return _error("instrument_busy_max_retries",
                              f"Plate reader failed after {max_retries} retries.",
                              {"attempt": attempt, "max_retries": max_retries,
                               "retry_available": False})

    # ── Normal readout ───────────────────────────────────────────────
    noise_schedule = getattr(lab_state, "_noise_schedule", None)
    readout_index = len(lab_state.readouts) + 1

    values: dict[str, float] = {}
    for well_name in wells:
        w = plate_resource[well_name]
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


# ── Workspace files (Direction 5) ────────────────────────────────────────


def list_workspace_files(lab_state: LabState) -> dict[str, Any]:
    """List available workspace files (protocol, plate map, inventory, etc.)."""
    files = list(lab_state.workspace_files.keys())
    lab_state.insert_event("workspace.listed", "workspace", "", {"files": files})
    return _ok({"files": files})


def get_workspace_file(lab_state: LabState, filename: str) -> dict[str, Any]:
    """Read the content of a specific workspace file."""
    content = lab_state.workspace_files.get(filename)
    if content is None:
        return _error("file_not_found",
                      f"Workspace file '{filename}' not found.",
                      {"available": list(lab_state.workspace_files.keys())})
    lab_state.insert_event("workspace.read", "workspace", filename, {"filename": filename})
    return _ok({"filename": filename, "content": content})


# ── Workflow ────────────────────────────────────────────────────────────


def add_workflow_note(lab_state: LabState, note: str) -> dict[str, Any]:
    """Add a workflow note to the run record."""
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
    """Submit the final QC protocol decision with supporting readout evidence."""
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
    return {"ok": False, "error": {"code": code, "message": message,
                                    "details": details or {}}}


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
