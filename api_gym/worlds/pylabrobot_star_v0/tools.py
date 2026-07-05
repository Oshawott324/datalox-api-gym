"""OpenAI-compatible tool schemas and dispatcher for pylabrobot_star_v0.

Every tool is grounded in a PyLabRobot ``LiquidHandler`` method (see the
``plr_method`` annotation in each definition).  Non-PLR tools (read_absorbance,
workspace files, workflow) are explicitly marked as benchmark-specific.

Architecture::

    LLM tool call (JSON strings)
        → tools.dispatch_tool (resolve LabState)
        → handler → services.<function> (thin PLR wrapper)
        → LiquidHandler method → VolumeTracker/TipTracker updated by PLR
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from api_gym.worlds.pylabrobot_star_v0 import services
from api_gym.worlds.pylabrobot_star_v0.state import LabState, get_state

ToolHandler = Callable[[LabState, dict[str, Any]], dict[str, Any]]


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties,
            "required": required, "additionalProperties": False}


# ── Tool definitions ──────────────────────────────────────────────────────

TOOL_DEFINITIONS: list[dict[str, Any]] = [

    # ══════════════════════════════════════════════════════════════════════
    # Inspection (PLR: LiquidHandler + Resource API)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "get_deck_state",
            "description": (
                "Inspect the STAR deck: loaded carriers, labware, and instrument "
                "status (single-channel, 96-head, iSWAP arm).\n\n"
                "PLR: LiquidHandler.summary() + deck resource tree."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_labware_state",
            "description": (
                "Inspect one labware item (plate, tip rack, trough, tube rack) "
                "including per-well volumes, max capacities, and tip availability.\n\n"
                "PLR: Resource.children → VolumeTracker / TipSpot."
            ),
            "parameters": _schema(
                {"labware_id": {"type": "string",
                                "description": "Labware name on the deck (e.g. 'assay_plate')."}},
                ["labware_id"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mounted_tips",
            "description": (
                "Query which tips are currently mounted on the pipetting channels. "
                "Returns per-channel tip status.\n\n"
                "PLR: LiquidHandler.get_mounted_tips()."
            ),
            "parameters": _schema({}, []),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # Single-channel tip operations (PLR: LiquidHandler)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "pick_up_tips",
            "description": (
                "Pick up tips from tip rack spots onto pipetting channels. "
                "Must be called BEFORE aspirate.  One tip_ref per channel.\n\n"
                "PLR: LiquidHandler.pick_up_tips(tip_spots, use_channels)."
            ),
            "parameters": _schema(
                {
                    "tip_refs": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Tip references, e.g. ['tip_rack_01:A1'].",
                    },
                    "channels": {
                        "type": "array", "items": {"type": "integer"},
                        "description": "Channel indices (default: [0, 1, ...]).",
                    },
                },
                ["tip_refs"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drop_tips",
            "description": (
                "Drop tips back to specific tip rack spots (for tip reuse).\n\n"
                "PLR: LiquidHandler.drop_tips(tip_spots, use_channels)."
            ),
            "parameters": _schema(
                {
                    "tip_refs": {
                        "type": "array", "items": {"type": "string"},
                        "description": "Tip spot references to drop to.",
                    },
                    "channels": {
                        "type": "array", "items": {"type": "integer"},
                        "description": "Channel indices (default: all channels with tips).",
                    },
                },
                ["tip_refs"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discard_tips",
            "description": (
                "Discard currently mounted tips to the trash area. "
                "Use when tips are contaminated or no longer needed.\n\n"
                "PLR: LiquidHandler.discard_tips(use_channels)."
            ),
            "parameters": _schema(
                {
                    "channels": {
                        "type": "array", "items": {"type": "integer"},
                        "description": "Channel indices to discard from (default: all).",
                    },
                },
                [],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "return_tips",
            "description": (
                "Return tips to their original rack positions. "
                "Use when tips are still clean and can be reused.\n\n"
                "PLR: LiquidHandler.return_tips(use_channels)."
            ),
            "parameters": _schema(
                {
                    "channels": {
                        "type": "array", "items": {"type": "integer"},
                        "description": "Channel indices (default: all).",
                    },
                },
                [],
            ),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # Single-channel liquid operations (PLR: LiquidHandler)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "aspirate",
            "description": (
                "Aspirate liquid from a source well into the tip currently "
                "mounted on the specified channel.  You MUST call pick_up_tips first.\n\n"
                "PLR: LiquidHandler.aspirate([well], vols=[volume_ul], use_channels=[channel])."
            ),
            "parameters": _schema(
                {
                    "source": {
                        "type": "string",
                        "description": "Well reference: 'labware:well' (e.g. 'source_plate:A1').",
                    },
                    "volume_ul": {
                        "type": "number", "exclusiveMinimum": 0,
                        "description": "Volume in microlitres.",
                    },
                    "channel": {
                        "type": "integer", "default": 0,
                        "description": "Pipetting channel index (0-based).",
                    },
                },
                ["source", "volume_ul"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispense",
            "description": (
                "Dispense liquid from the tip into a target well.\n\n"
                "PLR: LiquidHandler.dispense([well], vols=[volume_ul], use_channels=[channel])."
            ),
            "parameters": _schema(
                {
                    "target": {
                        "type": "string",
                        "description": "Well reference: 'labware:well' (e.g. 'assay_plate:B1').",
                    },
                    "volume_ul": {
                        "type": "number", "exclusiveMinimum": 0,
                        "description": "Volume in microlitres.",
                    },
                    "channel": {
                        "type": "integer", "default": 0,
                        "description": "Pipetting channel index (0-based).",
                    },
                    "mix_after": {
                        "type": "boolean", "default": False,
                        "description": "Mix after dispensing.",
                    },
                },
                ["target", "volume_ul"],
            ),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # 96-head parallel operations (PLR: LiquidHandler)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "pick_up_tips96",
            "description": (
                "Pick up a full rack of 96 tips using the 96-channel head. "
                "Requires 96-head to be installed.\n\n"
                "PLR: LiquidHandler.pick_up_tips96(tip_rack)."
            ),
            "parameters": _schema(
                {
                    "tip_rack_id": {
                        "type": "string",
                        "description": "Name of the tip rack on the deck (e.g. 'tip_rack_01').",
                    },
                },
                ["tip_rack_id"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drop_tips96",
            "description": (
                "Drop 96-head tips to a tip rack or trash.\n\n"
                "PLR: LiquidHandler.drop_tips96(resource)."
            ),
            "parameters": _schema(
                {
                    "target": {
                        "type": "string", "default": "trash",
                        "description": "Target resource name or 'trash'.",
                    },
                },
                [],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discard_tips96",
            "description": (
                "Discard all 96 tips from the 96-head to the waste area.\n\n"
                "PLR: LiquidHandler.discard_tips96()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aspirate96",
            "description": (
                "Aspirate from all 96 wells of a plate simultaneously using the "
                "96-head.  Requires tips already picked up via pick_up_tips96.\n\n"
                "PLR: LiquidHandler.aspirate96(plate, volume)."
            ),
            "parameters": _schema(
                {
                    "plate_id": {
                        "type": "string",
                        "description": "Plate name on the deck.",
                    },
                    "volume_ul": {
                        "type": "number", "exclusiveMinimum": 0,
                        "description": "Volume in microlitres per well.",
                    },
                },
                ["plate_id", "volume_ul"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispense96",
            "description": (
                "Dispense to all 96 wells of a plate simultaneously using the "
                "96-head.\n\n"
                "PLR: LiquidHandler.dispense96(plate, volume)."
            ),
            "parameters": _schema(
                {
                    "plate_id": {
                        "type": "string",
                        "description": "Plate name on the deck.",
                    },
                    "volume_ul": {
                        "type": "number", "exclusiveMinimum": 0,
                        "description": "Volume in microlitres per well.",
                    },
                },
                ["plate_id", "volume_ul"],
            ),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # iSWAP robotic arm (PLR: LiquidHandler)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "move_plate",
            "description": (
                "Move a plate to a different deck position using the iSWAP "
                "robotic arm.  Requires iSWAP to be installed.\n\n"
                "PLR: LiquidHandler.move_plate(plate, to)."
            ),
            "parameters": _schema(
                {
                    "plate_id": {
                        "type": "string",
                        "description": "Name of the plate to move.",
                    },
                    "to_position": {
                        "type": "string",
                        "description": "Destination resource name (e.g. carrier site).",
                    },
                },
                ["plate_id", "to_position"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_lid",
            "description": (
                "Move a plate's lid using the iSWAP robotic arm. "
                "Requires iSWAP to be installed and the plate to have a lid.\n\n"
                "PLR: LiquidHandler.move_lid(lid, to)."
            ),
            "parameters": _schema(
                {
                    "plate_id": {
                        "type": "string",
                        "description": "Name of the plate whose lid to move.",
                    },
                    "to_position": {
                        "type": "string",
                        "description": "Destination resource name.",
                    },
                },
                ["plate_id", "to_position"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_resource",
            "description": (
                "Move any deck resource (tube rack, tip carrier, etc.) using "
                "the iSWAP robotic arm.  Requires iSWAP to be installed.\n\n"
                "PLR: LiquidHandler.move_resource(resource, to)."
            ),
            "parameters": _schema(
                {
                    "resource_id": {
                        "type": "string",
                        "description": "Name of the resource to move.",
                    },
                    "to_position": {
                        "type": "string",
                        "description": "Destination resource name.",
                    },
                },
                ["resource_id", "to_position"],
            ),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # Convenience transfers (PLR: LiquidHandler)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "transfer",
            "description": (
                "Multi-dispense: aspirate once from a source well, then dispense "
                "equal volumes to multiple target wells.  More efficient than "
                "individual aspirate+dispense calls for serial dilutions.\n\n"
                "PLR: LiquidHandler.transfer(source, targets, target_vols=...)."
            ),
            "parameters": _schema(
                {
                    "source": {
                        "type": "string",
                        "description": "Source well reference: 'labware:well'.",
                    },
                    "targets": {
                        "type": "array", "items": {"type": "string"},
                        "description": "List of target well references.",
                    },
                    "volume_ul": {
                        "type": "number", "exclusiveMinimum": 0,
                        "description": "Volume to dispense to each target.",
                    },
                    "channel": {
                        "type": "integer", "default": 0,
                        "description": "Pipetting channel index.",
                    },
                },
                ["source", "targets", "volume_ul"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stamp",
            "description": (
                "Full-plate 96-to-96 stamp / replicate: aspirate from all 96 "
                "wells of the source plate and dispense to all 96 wells of the "
                "target plate.  Requires 96-head with tips loaded.\n\n"
                "PLR: LiquidHandler.stamp(source, target, volume)."
            ),
            "parameters": _schema(
                {
                    "source_plate": {
                        "type": "string",
                        "description": "Source plate name on the deck.",
                    },
                    "target_plate": {
                        "type": "string",
                        "description": "Target plate name on the deck.",
                    },
                    "volume_ul": {
                        "type": "number", "exclusiveMinimum": 0,
                        "description": "Volume per well in microlitres.",
                    },
                },
                ["source_plate", "target_plate", "volume_ul"],
            ),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # Centrifuge operations (PLR: Centrifuge)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "centrifuge_open_door",
            "description": (
                "Open the centrifuge door to load/unload buckets.\n\n"
                "PLR: Centrifuge.open_door()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "centrifuge_close_door",
            "description": (
                "Close the centrifuge door before spinning.\n\n"
                "PLR: Centrifuge.close_door()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "centrifuge_lock_door",
            "description": (
                "Lock the centrifuge door (safety interlock).  Must be locked "
                "BEFORE spinning.\n\n"
                "PLR: Centrifuge.lock_door()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "centrifuge_go_to_bucket1",
            "description": (
                "Rotate the centrifuge to present bucket 1 for loading.\n\n"
                "PLR: Centrifuge.go_to_bucket1()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "centrifuge_go_to_bucket2",
            "description": (
                "Rotate the centrifuge to present bucket 2 for loading.\n\n"
                "PLR: Centrifuge.go_to_bucket2()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "centrifuge_lock_bucket",
            "description": (
                "Lock the current bucket in place before spinning.\n\n"
                "PLR: Centrifuge.lock_bucket()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "centrifuge_spin",
            "description": (
                "Spin the centrifuge at the specified g-force for a given "
                "duration (seconds).  Door must be closed and locked first. "
                "Balanced loading (both buckets) is required for safe operation.\n\n"
                "PLR: Centrifuge.spin(g, duration, acceleration)."
            ),
            "parameters": _schema(
                {
                    "g_force": {"type": "number", "exclusiveMinimum": 0,
                                "description": "Relative centrifugal force (×g)."},
                    "duration_s": {"type": "number", "exclusiveMinimum": 0,
                                   "description": "Spin duration in seconds."},
                },
                ["g_force", "duration_s"],
            ),
        },
    },

    
    # ══════════════════════════════════════════════════════════════════════
    # Thermocycler operations (PLR: Thermocycler)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "tc_close_lid",
            "description": (
                "Close the thermocycler lid. Must be closed before heating.\n\n"
                "PLR: Thermocycler.close_lid()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tc_open_lid",
            "description": (
                "Open the thermocycler lid to remove the plate.\n\n"
                "PLR: Thermocycler.open_lid()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tc_set_lid_temp",
            "description": (
                "Set the lid heater temperature (typically 105C to prevent "
                "condensation).\n\n"
                "PLR: Thermocycler.set_lid_temperature(temperature)."
            ),
            "parameters": _schema(
                {"temperature": {"type": "number", "description": "Lid temperature in Celsius."}},
                ["temperature"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tc_set_block_temp",
            "description": (
                "Set the block temperature for the PCR step.\n\n"
                "PLR: Thermocycler.set_block_temperature(temperature)."
            ),
            "parameters": _schema(
                {"temperature": {"type": "number", "description": "Block temperature in Celsius."}},
                ["temperature"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tc_get_block_temp",
            "description": (
                "Read the current block temperature.\n\n"
                "PLR: Thermocycler.get_block_current_temperature()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tc_deactivate",
            "description": (
                "Deactivate the thermocycler (block + lid heating off).\n\n"
                "PLR: Thermocycler.deactivate_block() + deactivate_lid()."
            ),
            "parameters": _schema({}, []),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # HeaterShaker operations (PLR: HeaterShaker)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "hs_set_temperature",
            "description": (
                "Set the heater/shaker target temperature in Celsius.\n\n"
                "PLR: HeaterShaker.set_temperature(temperature)."
            ),
            "parameters": _schema(
                {"temperature": {"type": "number", "description": "Target temperature in C."}},
                ["temperature"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hs_get_temperature",
            "description": (
                "Read the current temperature from the heater/shaker.\n\n"
                "PLR: HeaterShaker.get_temperature()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hs_shake",
            "description": (
                "Start shaking at the specified RPM.  Optional duration in seconds.\n\n"
                "PLR: HeaterShaker.shake(speed, duration)."
            ),
            "parameters": _schema(
                {
                    "speed_rpm": {"type": "number", "exclusiveMinimum": 0, "description": "Shaking speed in RPM."},
                    "duration_s": {"type": "number", "exclusiveMinimum": 0, "description": "Optional duration in seconds."},
                },
                ["speed_rpm"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hs_stop_shaking",
            "description": (
                "Stop the shaking motion.\n\n"
                "PLR: HeaterShaker.stop_shaking()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hs_deactivate",
            "description": (
                "Deactivate both heating and shaking - returns to ambient.\n\n"
                "PLR: HeaterShaker.deactivate()."
            ),
            "parameters": _schema({}, []),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # Scale operations (PLR: Scale)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "scale_get_weight",
            "description": (
                "Read the current weight from the analytical balance in grams. "
                "Use for gravimetric verification of dispensed volumes.\n\n"
                "PLR: Scale.get_weight() / Scale.read_weight()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scale_tare",
            "description": (
                "Tare the scale — set the current reading to zero.  Use BEFORE "
                "placing a sample on the scale to measure net weight.\n\n"
                "PLR: Scale.tare()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scale_zero",
            "description": (
                "Zero the scale — reset to absolute zero reference.  Use at "
                "the START of a weighing session (before any tare).\n\n"
                "PLR: Scale.zero()."
            ),
            "parameters": _schema({}, []),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # Pump operations (PLR: Pump)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "pump_run_duration",
            "description": (
                "Run the peristaltic pump at a fixed speed for a specified "
                "duration (in seconds).  Use this to fill troughs, dispense "
                "reagent, or flush lines.\n\n"
                "PLR: Pump.run_for_duration(speed, duration)."
            ),
            "parameters": _schema(
                {
                    "speed_rpm": {
                        "type": "number", "exclusiveMinimum": 0,
                        "description": "Pump speed in RPM.",
                    },
                    "duration_s": {
                        "type": "number", "exclusiveMinimum": 0,
                        "description": "Duration in seconds.",
                    },
                },
                ["speed_rpm", "duration_s"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pump_run_volume",
            "description": (
                "Pump a calibrated volume.  Requires the pump to be "
                "pre-calibrated (check workspace files for calibration data).\n\n"
                "PLR: Pump.pump_volume(speed, volume)."
            ),
            "parameters": _schema(
                {
                    "speed_rpm": {
                        "type": "number", "exclusiveMinimum": 0,
                        "description": "Pump speed in RPM.",
                    },
                    "volume_ul": {
                        "type": "number", "exclusiveMinimum": 0,
                        "description": "Volume in microlitres.",
                    },
                },
                ["speed_rpm", "volume_ul"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pump_halt",
            "description": (
                "Emergency-stop the pump immediately.  Use when a pump "
                "operation needs to be aborted (e.g. wrong speed, wrong "
                "reagent selected).\n\n"
                "PLR: Pump.halt()."
            ),
            "parameters": _schema({}, []),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # Plate reading (PLR: PlateReader)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "read_absorbance",
            "description": (
                "Read OD absorbance for specified wells at a given wavelength. "
                "May return 'instrument_busy' errors requiring retry.\n\n"
                "PLR: PlateReader.read_absorbance(wavelength, wells)."
            ),
            "parameters": _schema(
                {
                    "plate_id": {"type": "string"},
                    "wavelength_nm": {"type": "integer"},
                    "wells": {"type": "array", "items": {"type": "string"}},
                },
                ["plate_id", "wavelength_nm", "wells"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_fluorescence",
            "description": (
                "Read fluorescence for specified wells.  Requires excitation "
                "and emission wavelengths and a focal height.\n\n"
                "PLR: PlateReader.read_fluorescence(excitation, emission, "
                "focal_height, wells)."
            ),
            "parameters": _schema(
                {
                    "plate_id": {"type": "string"},
                    "excitation_nm": {"type": "integer",
                                      "description": "Excitation wavelength in nm."},
                    "emission_nm": {"type": "integer",
                                    "description": "Emission wavelength in nm."},
                    "focal_height_mm": {"type": "number",
                                        "description": "Focal height in mm."},
                    "wells": {"type": "array", "items": {"type": "string"}},
                },
                ["plate_id", "excitation_nm", "emission_nm",
                 "focal_height_mm", "wells"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_luminescence",
            "description": (
                "Read luminescence for specified wells.  No excitation needed — "
                "only focal height.  Common for ATP / reporter gene assays.\n\n"
                "PLR: PlateReader.read_luminescence(focal_height, wells)."
            ),
            "parameters": _schema(
                {
                    "plate_id": {"type": "string"},
                    "focal_height_mm": {"type": "number",
                                        "description": "Focal height in mm."},
                    "wells": {"type": "array", "items": {"type": "string"}},
                },
                ["plate_id", "focal_height_mm", "wells"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plate_reader_open",
            "description": (
                "Open the plate reader door.  Call BEFORE inserting a plate "
                "into the reader.\n\n"
                "PLR: PlateReader.open()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plate_reader_close",
            "description": (
                "Close the plate reader door.  Call AFTER inserting a plate "
                "and BEFORE reading.\n\n"
                "PLR: PlateReader.close()."
            ),
            "parameters": _schema({}, []),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # Workspace files (Direction 5 — benchmark-specific)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "list_workspace_files",
            "description": (
                "List available workspace files (protocol, plate map, reagent "
                "inventory, prior run log).  Always check this first to "
                "understand the task context.\n\n"
                "Source: Direction 5 (lab scaffold realism)."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workspace_file",
            "description": (
                "Read the content of a specific workspace file.\n\n"
                "Source: Direction 5 (lab scaffold realism)."
            ),
            "parameters": _schema(
                {"filename": {"type": "string"}},
                ["filename"],
            ),
        },
    },

    # ══════════════════════════════════════════════════════════════════════
    # Workflow (benchmark-specific)
    # ══════════════════════════════════════════════════════════════════════

    {
        "type": "function",
        "function": {
            "name": "add_workflow_note",
            "description": (
                "Add a workflow note to the run record for audit trail.\n\n"
                "Source: benchmark-specific."
            ),
            "parameters": _schema(
                {"note": {"type": "string", "description": "Note text."}},
                ["note"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_protocol",
            "description": (
                "Submit the final QC protocol decision with supporting readout "
                "evidence.  This ends the agent's run.\n\n"
                "Source: benchmark-specific."
            ),
            "parameters": _schema(
                {
                    "decision": {
                        "type": "string",
                        "enum": ["continue", "hold"],
                        "description": "QC decision: 'continue' (pass) or 'hold' (fail).",
                    },
                    "evidence_readout_id": {
                        "type": "string",
                        "description": "The readout_id from read_absorbance.",
                    },
                    "target_well": {
                        "type": "string",
                        "description": "Well reference: 'labware:well'.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Brief justification for the decision.",
                    },
                },
                ["decision", "evidence_readout_id", "target_well", "rationale"],
            ),
        },
    },
]


# ── Dispatch ──────────────────────────────────────────────────────────────


def dispatch_tool(run_dir: Path, *, name: str,
                  arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call by name, resolving LabState from the run directory."""
    lab_state = get_state(run_dir)
    return _dispatch(lab_state, name=name, arguments=arguments)


def _dispatch(lab_state: LabState, *, name: str,
              arguments: dict[str, Any]) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return _tool_error("unknown_tool",
                           f"Tool '{name}' not registered.", {"tool_name": name})
    try:
        return handler(lab_state, arguments)
    except KeyError as exc:
        return _tool_error("missing_tool_argument",
                           "Missing required argument.",
                           {"tool_name": name, "argument": str(exc).strip("'")})
    except (TypeError, ValueError) as exc:
        return _tool_error("invalid_tool_arguments",
                           "Invalid argument.",
                           {"tool_name": name, "message": str(exc)})


def dispatch_tool_call(run_dir: Path, tool_call: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one OpenAI-compatible function call from a run directory."""
    name, arguments = _extract_name_and_arguments(tool_call)
    if name is None:
        return _tool_error("missing_tool_name", "No function name.", {})
    if arguments is None:
        return _tool_error("invalid_tool_arguments", "Arguments must be a JSON object.", {})
    return dispatch_tool(run_dir, name=name, arguments=arguments)


def _extract_name_and_arguments(tool_call: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    function = tool_call.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        raw = function.get("arguments", {})
    else:
        name = tool_call.get("name")
        raw = tool_call.get("arguments", {})
    if isinstance(raw, str):
        try:
            arguments = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return str(name) if name else None, None
    else:
        arguments = raw
    if not isinstance(arguments, dict):
        return str(name) if name else None, None
    return str(name) if name else None, arguments


# ── Handlers ──────────────────────────────────────────────────────────────


def _get_deck_state(ls: LabState, _a: dict) -> dict:
    return services.get_deck_state(ls)


def _get_labware_state(ls: LabState, a: dict) -> dict:
    return services.get_labware_state(ls, labware_id=str(a["labware_id"]))


def _get_mounted_tips(ls: LabState, _a: dict) -> dict:
    return services.get_mounted_tips(ls)


def _pick_up_tips(ls: LabState, a: dict) -> dict:
    return services.pick_up_tips(
        ls,
        tip_refs=[str(r) for r in a["tip_refs"]],
        channels=[int(c) for c in a["channels"]] if "channels" in a else None,
    )


def _drop_tips(ls: LabState, a: dict) -> dict:
    return services.drop_tips(
        ls,
        tip_refs=[str(r) for r in a["tip_refs"]],
        channels=[int(c) for c in a["channels"]] if "channels" in a else None,
    )


def _discard_tips(ls: LabState, a: dict) -> dict:
    return services.discard_tips(
        ls,
        channels=[int(c) for c in a["channels"]] if "channels" in a else None,
    )


def _return_tips(ls: LabState, a: dict) -> dict:
    return services.return_tips(
        ls,
        channels=[int(c) for c in a["channels"]] if "channels" in a else None,
    )


def _aspirate(ls: LabState, a: dict) -> dict:
    return services.aspirate(
        ls,
        source=str(a["source"]),
        volume_ul=float(a["volume_ul"]),
        channel=int(a.get("channel", 0)),
    )


def _dispense(ls: LabState, a: dict) -> dict:
    return services.dispense(
        ls,
        target=str(a["target"]),
        volume_ul=float(a["volume_ul"]),
        channel=int(a.get("channel", 0)),
        mix_after=bool(a.get("mix_after", False)),
    )


def _pick_up_tips96(ls: LabState, a: dict) -> dict:
    return services.pick_up_tips96(ls, tip_rack_id=str(a["tip_rack_id"]))


def _drop_tips96(ls: LabState, a: dict) -> dict:
    return services.drop_tips96(ls, target=str(a.get("target", "trash")))


def _discard_tips96(ls: LabState, _a: dict) -> dict:
    return services.discard_tips96(ls)


def _aspirate96(ls: LabState, a: dict) -> dict:
    return services.aspirate96(
        ls,
        plate_id=str(a["plate_id"]),
        volume_ul=float(a["volume_ul"]),
    )


def _dispense96(ls: LabState, a: dict) -> dict:
    return services.dispense96(
        ls,
        plate_id=str(a["plate_id"]),
        volume_ul=float(a["volume_ul"]),
    )


def _move_plate(ls: LabState, a: dict) -> dict:
    return services.move_plate(
        ls,
        plate_id=str(a["plate_id"]),
        to_position=str(a["to_position"]),
    )


def _move_lid(ls: LabState, a: dict) -> dict:
    return services.move_lid(
        ls,
        plate_id=str(a["plate_id"]),
        to_position=str(a["to_position"]),
    )


def _move_resource(ls: LabState, a: dict) -> dict:
    return services.move_resource(
        ls,
        resource_id=str(a["resource_id"]),
        to_position=str(a["to_position"]),
    )


def _transfer(ls: LabState, a: dict) -> dict:
    return services.transfer(
        ls,
        source=str(a["source"]),
        targets=[str(t) for t in a["targets"]],
        volume_ul=float(a["volume_ul"]),
        channel=int(a.get("channel", 0)),
    )


def _stamp(ls: LabState, a: dict) -> dict:
    return services.stamp(
        ls,
        source_plate=str(a["source_plate"]),
        target_plate=str(a["target_plate"]),
        volume_ul=float(a["volume_ul"]),
    )


def _list_workspace_files(ls: LabState, _a: dict) -> dict:
    return services.list_workspace_files(ls)


def _get_workspace_file(ls: LabState, a: dict) -> dict:
    return services.get_workspace_file(ls, filename=str(a["filename"]))


def _read_absorbance(ls: LabState, a: dict) -> dict:
    wells = a["wells"]
    if not isinstance(wells, list):
        raise TypeError("wells must be a list")
    return services.read_absorbance(
        ls,
        plate_id=str(a["plate_id"]),
        wavelength_nm=int(a["wavelength_nm"]),
        wells=[str(w) for w in wells],
    )


def _read_fluorescence(ls: LabState, a: dict) -> dict:
    wells = a["wells"]
    if not isinstance(wells, list):
        raise TypeError("wells must be a list")
    return services.read_fluorescence(
        ls,
        plate_id=str(a["plate_id"]),
        excitation_nm=int(a["excitation_nm"]),
        emission_nm=int(a["emission_nm"]),
        focal_height_mm=float(a["focal_height_mm"]),
        wells=[str(w) for w in wells],
    )


def _read_luminescence(ls: LabState, a: dict) -> dict:
    wells = a["wells"]
    if not isinstance(wells, list):
        raise TypeError("wells must be a list")
    return services.read_luminescence(
        ls,
        plate_id=str(a["plate_id"]),
        focal_height_mm=float(a["focal_height_mm"]),
        wells=[str(w) for w in wells],
    )


def _plate_reader_open(ls: LabState, _a: dict) -> dict:
    return services.plate_reader_open(ls)


def _plate_reader_close(ls: LabState, _a: dict) -> dict:
    return services.plate_reader_close(ls)


def _centrifuge_open_door(ls: LabState, _a: dict) -> dict:
    return services.centrifuge_open_door(ls)


def _centrifuge_close_door(ls: LabState, _a: dict) -> dict:
    return services.centrifuge_close_door(ls)


def _centrifuge_lock_door(ls: LabState, _a: dict) -> dict:
    return services.centrifuge_lock_door(ls)


def _centrifuge_go_to_bucket1(ls: LabState, _a: dict) -> dict:
    return services.centrifuge_go_to_bucket1(ls)


def _centrifuge_go_to_bucket2(ls: LabState, _a: dict) -> dict:
    return services.centrifuge_go_to_bucket2(ls)


def _centrifuge_lock_bucket(ls: LabState, _a: dict) -> dict:
    return services.centrifuge_lock_bucket(ls)


def _centrifuge_spin(ls: LabState, a: dict) -> dict:
    return services.centrifuge_spin(ls, g_force=float(a["g_force"]),
                                    duration_s=float(a["duration_s"]))



def _tc_close_lid(ls: LabState, _a: dict) -> dict:
    return services.tc_close_lid(ls)


def _tc_open_lid(ls: LabState, _a: dict) -> dict:
    return services.tc_open_lid(ls)


def _tc_set_lid_temp(ls: LabState, a: dict) -> dict:
    return services.tc_set_lid_temp(ls, temperature=float(a["temperature"]))


def _tc_set_block_temp(ls: LabState, a: dict) -> dict:
    return services.tc_set_block_temp(ls, temperature=float(a["temperature"]))


def _tc_get_block_temp(ls: LabState, _a: dict) -> dict:
    return services.tc_get_block_temp(ls)


def _tc_deactivate(ls: LabState, _a: dict) -> dict:
    return services.tc_deactivate(ls)


def _hs_set_temperature(ls: LabState, a: dict) -> dict:
    return services.hs_set_temperature(ls, temperature=float(a["temperature"]))


def _hs_get_temperature(ls: LabState, _a: dict) -> dict:
    return services.hs_get_temperature(ls)


def _hs_shake(ls: LabState, a: dict) -> dict:
    return services.hs_shake(ls, speed_rpm=float(a["speed_rpm"]),
                             duration_s=float(a["duration_s"]) if "duration_s" in a else None)


def _hs_stop_shaking(ls: LabState, _a: dict) -> dict:
    return services.hs_stop_shaking(ls)


def _hs_deactivate(ls: LabState, _a: dict) -> dict:
    return services.hs_deactivate(ls)


def _scale_get_weight(ls: LabState, _a: dict) -> dict:
    return services.scale_get_weight(ls)


def _scale_tare(ls: LabState, _a: dict) -> dict:
    return services.scale_tare(ls)


def _scale_zero(ls: LabState, _a: dict) -> dict:
    return services.scale_zero(ls)


def _pump_run_duration(ls: LabState, a: dict) -> dict:
    return services.pump_run_for_duration(
        ls,
        speed_rpm=float(a["speed_rpm"]),
        duration_s=float(a["duration_s"]),
    )


def _pump_run_volume(ls: LabState, a: dict) -> dict:
    return services.pump_run_volume(
        ls,
        speed_rpm=float(a["speed_rpm"]),
        volume_ul=float(a["volume_ul"]),
    )


def _pump_halt(ls: LabState, _a: dict) -> dict:
    return services.pump_halt(ls)


def _add_workflow_note(ls: LabState, a: dict) -> dict:
    return services.add_workflow_note(ls, note=str(a["note"]))


def _submit_protocol(ls: LabState, a: dict) -> dict:
    return services.submit_protocol(
        ls,
        decision=str(a["decision"]),
        evidence_readout_id=str(a["evidence_readout_id"]),
        target_well=str(a["target_well"]),
        rationale=str(a["rationale"]),
    )


def _tool_error(code: str, message: str, details: dict) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_deck_state": _get_deck_state,
    "get_labware_state": _get_labware_state,
    "get_mounted_tips": _get_mounted_tips,
    # Single-channel tip
    "pick_up_tips": _pick_up_tips,
    "drop_tips": _drop_tips,
    "discard_tips": _discard_tips,
    "return_tips": _return_tips,
    # Single-channel liquid
    "aspirate": _aspirate,
    "dispense": _dispense,
    # 96-head
    "pick_up_tips96": _pick_up_tips96,
    "drop_tips96": _drop_tips96,
    "discard_tips96": _discard_tips96,
    "aspirate96": _aspirate96,
    "dispense96": _dispense96,
    # iSWAP
    "move_plate": _move_plate,
    "move_lid": _move_lid,
    "move_resource": _move_resource,
    # Convenience
    "transfer": _transfer,
    "stamp": _stamp,
    # Centrifuge
    "centrifuge_open_door": _centrifuge_open_door,
    "centrifuge_close_door": _centrifuge_close_door,
    "centrifuge_lock_door": _centrifuge_lock_door,
    "centrifuge_go_to_bucket1": _centrifuge_go_to_bucket1,
    "centrifuge_go_to_bucket2": _centrifuge_go_to_bucket2,
    "centrifuge_lock_bucket": _centrifuge_lock_bucket,
    "centrifuge_spin": _centrifuge_spin,
    # Thermocycler
    "tc_close_lid": _tc_close_lid,
    "tc_open_lid": _tc_open_lid,
    "tc_set_lid_temp": _tc_set_lid_temp,
    "tc_set_block_temp": _tc_set_block_temp,
    "tc_get_block_temp": _tc_get_block_temp,
    "tc_deactivate": _tc_deactivate,
    # HeaterShaker
    "hs_set_temperature": _hs_set_temperature,
    "hs_get_temperature": _hs_get_temperature,
    "hs_shake": _hs_shake,
    "hs_stop_shaking": _hs_stop_shaking,
    "hs_deactivate": _hs_deactivate,
    # Scale
    "scale_get_weight": _scale_get_weight,
    "scale_tare": _scale_tare,
    "scale_zero": _scale_zero,
    # Pump
    "pump_run_duration": _pump_run_duration,
    "pump_run_volume": _pump_run_volume,
    "pump_halt": _pump_halt,
    # Benchmark-specific
    "list_workspace_files": _list_workspace_files,
    "get_workspace_file": _get_workspace_file,
    "read_absorbance": _read_absorbance,
    "read_fluorescence": _read_fluorescence,
    "read_luminescence": _read_luminescence,
    "plate_reader_open": _plate_reader_open,
    "plate_reader_close": _plate_reader_close,
    "add_workflow_note": _add_workflow_note,
    "submit_protocol": _submit_protocol,
}
