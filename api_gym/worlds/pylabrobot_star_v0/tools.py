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
            "name": "arm_home",
            "description": (
                "Home the robot arm — reset all axes to zero position.\n\n"
                "PLR: ExperimentalSCARA.home().  Must be called before any "
                "arm motion."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arm_move_to",
            "description": (
                "Move the robot arm to the specified cartesian coordinates "
                "(x, y, z in mm).\n\n"
                "PLR: ExperimentalSCARA.move_to(CartesianCoords)."
            ),
            "parameters": _schema(
                {
                    "x": {"type": "number", "description": "X coordinate in mm."},
                    "y": {"type": "number", "description": "Y coordinate in mm."},
                    "z": {"type": "number", "description": "Z coordinate in mm."},
                },
                ["x", "y", "z"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arm_move_to_safe",
            "description": (
                "Move the robot arm to a safe retracted position (clear of "
                "the deck).\n\n"
                "PLR: ExperimentalSCARA.move_to_safe()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arm_approach",
            "description": (
                "Approach a position with the robot arm — a slower, more "
                "precise move used before picking up or dropping a resource.\n\n"
                "PLR: ExperimentalSCARA.approach(CartesianCoords, access)."
            ),
            "parameters": _schema(
                {
                    "x": {"type": "number", "description": "X coordinate in mm."},
                    "y": {"type": "number", "description": "Y coordinate in mm."},
                    "z": {"type": "number", "description": "Z coordinate in mm."},
                    "access": {
                        "type": "string",
                        "enum": ["vertical", "horizontal"],
                        "description": "Access direction: 'vertical' (top-down) or 'horizontal' (side).",
                    },
                },
                ["x", "y", "z"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arm_pick_up_resource",
            "description": (
                "Pick up a resource (e.g. plate, lid) at the specified position "
                "using the robot arm gripper.  Requires gripper to be open "
                "beforehand.\n\n"
                "PLR: ExperimentalSCARA.pick_up_resource(position, plate_width)."
            ),
            "parameters": _schema(
                {
                    "x": {"type": "number", "description": "X coordinate in mm."},
                    "y": {"type": "number", "description": "Y coordinate in mm."},
                    "z": {"type": "number", "description": "Z coordinate in mm."},
                    "plate_width_mm": {
                        "type": "number",
                        "description": "Width of the plate/resource to grip (mm), typically ~85 for an SBS plate.",
                    },
                },
                ["x", "y", "z", "plate_width_mm"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arm_drop_resource",
            "description": (
                "Drop the currently held resource at the specified position. "
                "Requires the gripper to be holding something.\n\n"
                "PLR: ExperimentalSCARA.drop_resource(position)."
            ),
            "parameters": _schema(
                {
                    "x": {"type": "number", "description": "X coordinate in mm."},
                    "y": {"type": "number", "description": "Y coordinate in mm."},
                    "z": {"type": "number", "description": "Z coordinate in mm."},
                },
                ["x", "y", "z"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arm_open_gripper",
            "description": (
                "Open the robot arm gripper to the specified width.  Must be "
                "open before picking up a resource.\n\n"
                "PLR: ExperimentalSCARA.open_gripper(gripper_width)."
            ),
            "parameters": _schema(
                {
                    "width_mm": {
                        "type": "number",
                        "description": "Gripper opening width in mm (default 80).",
                    },
                },
                ["width_mm"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arm_close_gripper",
            "description": (
                "Close the robot arm gripper to the specified width (for "
                "gripping a plate).\n\n"
                "PLR: ExperimentalSCARA.close_gripper(gripper_width)."
            ),
            "parameters": _schema(
                {
                    "width_mm": {
                        "type": "number",
                        "description": "Gripper closing width in mm (typically ~85 for SBS plate).",
                    },
                },
                ["width_mm"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arm_get_position",
            "description": (
                "Get the current cartesian position (x, y, z) of the robot arm.\n\n"
                "PLR: ExperimentalSCARA.get_cartesian_position()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arm_get_gripper_state",
            "description": (
                "Check whether the robot arm gripper is closed (holding "
                "something) or open, and report the current gripper width.\n\n"
                "PLR: ExperimentalSCARA.is_gripper_closed()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "arm_halt",
            "description": (
                "Emergency-stop the robot arm immediately.\n\n"
                "PLR: ExperimentalSCARA.halt()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sealer_seal",
            "description": (
                "Heat-seal a plate at the specified temperature for the given "
                "duration.  The sealer door MUST be closed before sealing.\n\n"
                "PLR: Sealer.seal(temperature, duration)."
            ),
            "parameters": _schema(
                {
                    "temperature": {
                        "type": "integer",
                        "description": "Sealing temperature in degrees Celsius (e.g. 170).",
                    },
                    "duration_s": {
                        "type": "number",
                        "description": "Seal duration in seconds (e.g. 3.0).",
                    },
                },
                ["temperature", "duration_s"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sealer_open",
            "description": (
                "Open the sealer door to insert or remove a plate.\n\n"
                "PLR: Sealer.open()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sealer_close",
            "description": (
                "Close the sealer door.  Required before sealing.\n\n"
                "PLR: Sealer.close()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sealer_set_temperature",
            "description": (
                "Set the target sealing temperature for the sealer.\n\n"
                "PLR: Sealer.set_temperature(temperature)."
            ),
            "parameters": _schema(
                {
                    "temperature": {
                        "type": "number",
                        "description": "Target temperature in degrees Celsius.",
                    },
                },
                ["temperature"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sealer_get_temperature",
            "description": (
                "Read the current sealer temperature.  Use to verify the sealer "
                "has reached the target temperature before sealing.\n\n"
                "PLR: Sealer.get_temperature()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peeler_seal_check",
            "description": (
                "Check whether a seal is present on the plate currently in "
                "the peeler.  Returns 'seal_detected', 'no_seal', or "
                "'plate_not_detected'.\n\n"
                "PLR: XPeelBackend.seal_check()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peeler_peel",
            "description": (
                "Peel the seal off the plate in the peeler.  Requires a seal "
                "to be present (verified by peeler_seal_check first).\n\n"
                "PLR: XPeelBackend.peel(begin_location, fast, adhere_time)."
            ),
            "parameters": _schema(
                {
                    "begin_location": {
                        "type": "integer",
                        "description": "Peel start location: -2, 0, 2, or 4 (default 0).",
                    },
                    "fast": {
                        "type": "boolean",
                        "description": "Use fast peel mode (default false).",
                    },
                    "adhere_time": {
                        "type": "number",
                        "description": "Adhesion time in seconds before peeling (default 2.5).",
                    },
                },
                [],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peeler_move_conveyor_in",
            "description": (
                "Move the conveyor in — load the plate into the peeler.\n\n"
                "PLR: XPeelBackend.move_conveyor_in()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peeler_move_conveyor_out",
            "description": (
                "Move the conveyor out — unload the plate from the peeler.\n\n"
                "PLR: XPeelBackend.move_conveyor_out()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peeler_move_elevator_up",
            "description": (
                "Raise the elevator to bring the plate to peel position.\n\n"
                "PLR: XPeelBackend.move_elevator_up()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peeler_move_elevator_down",
            "description": (
                "Lower the elevator to return the plate to conveyor level.\n\n"
                "PLR: XPeelBackend.move_elevator_down()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peeler_advance_tape",
            "description": (
                "Advance the adhesive tape to the next clean segment.\n\n"
                "PLR: XPeelBackend.advance_tape()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peeler_get_tape_remaining",
            "description": (
                "Check how much adhesive tape is remaining (percentage).\n\n"
                "PLR: XPeelBackend.get_tape_remaining()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peeler_get_status",
            "description": (
                "Get the peeler device status (state, error, warning codes).\n\n"
                "PLR: XPeelBackend.get_status()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shaker_lock_plate",
            "description": (
                "Lock the plate onto the dedicated shaker.  Required before "
                "shaking — attempting to shake without locking will fail.\n\n"
                "PLR: Shaker.lock_plate()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shaker_unlock_plate",
            "description": (
                "Unlock the plate from the dedicated shaker.  Automatically "
                "stops shaking if it was active.\n\n"
                "PLR: Shaker.unlock_plate()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shaker_shake",
            "description": (
                "Start shaking the plate at the specified speed in RPM.  "
                "Optionally specify a duration — if omitted, shaking "
                "continues until shaker_stop_shaking is called.  Plate "
                "MUST be locked first.\n\n"
                "PLR: Shaker.shake(speed, duration)."
            ),
            "parameters": _schema(
                {
                    "speed_rpm": {
                        "type": "number",
                        "description": "Shaking speed in RPM (e.g. 500).",
                    },
                    "duration_s": {
                        "type": "number",
                        "description": "Optional duration in seconds. If omitted, shakes until stopped.",
                    },
                },
                ["speed_rpm"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shaker_stop_shaking",
            "description": (
                "Stop the shaker immediately.\n\n"
                "PLR: Shaker.stop_shaking()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "temp_controller_set_temperature",
            "description": (
                "Set the target temperature on the dedicated temperature "
                "controller (no shaking capability).\n\n"
                "PLR: TemperatureController.set_temperature(temperature, passive)."
            ),
            "parameters": _schema(
                {
                    "temperature": {
                        "type": "number",
                        "description": "Target temperature in degrees Celsius.",
                    },
                    "passive": {
                        "type": "boolean",
                        "description": "If true, wait passively without active heating/cooling (default false).",
                    },
                },
                ["temperature"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "temp_controller_get_temperature",
            "description": (
                "Read the current temperature from the dedicated temperature "
                "controller.\n\n"
                "PLR: TemperatureController.get_temperature()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "temp_controller_deactivate",
            "description": (
                "Deactivate the temperature controller — return to ambient "
                "temperature.\n\n"
                "PLR: TemperatureController.deactivate()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "temp_controller_wait_for_temperature",
            "description": (
                "Wait until the temperature controller reaches its target "
                "temperature.  Blocks until the temperature is within the "
                "specified tolerance or the timeout is reached.\n\n"
                "PLR: TemperatureController.wait_for_temperature(timeout, tolerance)."
            ),
            "parameters": _schema(
                {
                    "timeout": {
                        "type": "number",
                        "description": "Maximum time to wait in seconds (default 300).",
                    },
                    "tolerance": {
                        "type": "number",
                        "description": "Temperature tolerance in degrees Celsius (default 0.5).",
                    },
                },
                [],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tilter_set_angle",
            "description": (
                "Set the absolute tilt angle of the plate tilter module. "
                "0° = flat/level, positive = tilted.  Safety limit: ±45°.\n\n"
                "PLR: Tilter.set_angle(absolute_angle)."
            ),
            "parameters": _schema(
                {
                    "angle": {
                        "type": "number",
                        "description": "Absolute tilt angle in degrees (0 = level, positive = tilted).",
                    },
                },
                ["angle"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tilter_tilt",
            "description": (
                "Tilt the plate by a relative angle from the current position.\n\n"
                "PLR: Tilter.tilt(relative_angle)."
            ),
            "parameters": _schema(
                {
                    "relative_angle": {
                        "type": "number",
                        "description": "Relative tilt angle in degrees (positive = tilt more).",
                    },
                },
                ["relative_angle"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tilter_get_angle",
            "description": (
                "Get the current absolute tilt angle of the tilter module.\n\n"
                "Reads current backend state (no dedicated PLR getter)."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tilter_return_to_level",
            "description": (
                "Return the tilter to 0° (flat/level position). "
                "Always return the tilter to level after use — leaving it "
                "tilted may cause pipetting errors on subsequent operations.\n\n"
                "Convenience wrapper around tilter_set_angle(0.0)."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "storage_open_door",
            "description": (
                "Open the incubator/storage door to access plates.\n\n"
                "PLR: Incubator.open_door()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "storage_close_door",
            "description": (
                "Close the incubator/storage door.\n\n"
                "PLR: Incubator.close_door()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "storage_set_temperature",
            "description": (
                "Set the incubator temperature (e.g. 37°C for cell culture).\n\n"
                "PLR: Incubator.set_temperature(temperature)."
            ),
            "parameters": _schema(
                {
                    "temperature": {
                        "type": "number",
                        "description": "Target temperature in degrees Celsius.",
                    },
                },
                ["temperature"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "storage_get_temperature",
            "description": (
                "Read the current incubator temperature.\n\n"
                "PLR: Incubator.get_temperature()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "storage_start_shaking",
            "description": (
                "Start the built-in shaker in the incubator.\n\n"
                "PLR: Incubator.start_shaking(frequency)."
            ),
            "parameters": _schema(
                {
                    "frequency": {
                        "type": "number",
                        "description": "Shaking frequency (default 1.0).",
                    },
                },
                [],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "storage_stop_shaking",
            "description": (
                "Stop the built-in shaker.\n\n"
                "PLR: Incubator.stop_shaking()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "storage_store_plate",
            "description": (
                "Store a plate into the incubator at a random free site. "
                "The door must be open first.\n\n"
                "PLR: Incubator.take_in_plate(site)."
            ),
            "parameters": _schema(
                {
                    "plate_name": {
                        "type": "string",
                        "description": "Name of the plate to store (e.g. 'assay_plate').",
                    },
                },
                ["plate_name"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "storage_retrieve_plate",
            "description": (
                "Retrieve a plate from the incubator to the loading tray.\n\n"
                "PLR: Incubator.fetch_plate_to_loading_tray(plate_name)."
            ),
            "parameters": _schema(
                {
                    "plate_name": {
                        "type": "string",
                        "description": "Name of the plate to retrieve (e.g. 'assay_plate').",
                    },
                },
                ["plate_name"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "storage_get_free_sites",
            "description": (
                "Check how many free storage sites are available in the "
                "incubator.\n\n"
                "PLR: Incubator.get_num_free_sites()."
            ),
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "powder_dispense",
            "description": (
                "Dispense a powder into a single target well at the specified "
                "amount in milligrams.\n\n"
                "PLR: PowderDispenser.dispense(resources, powders, amounts)."
            ),
            "parameters": _schema(
                {
                    "powder_name": {
                        "type": "string",
                        "description": "Name of the powder to dispense (e.g. 'reagent_a').",
                    },
                    "amount_mg": {
                        "type": "number",
                        "description": "Amount to dispense in milligrams (max 1000 per dispense).",
                    },
                    "target_well": {
                        "type": "string",
                        "description": "Target well reference (e.g. 'assay_plate:B1').",
                    },
                },
                ["powder_name", "amount_mg", "target_well"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "powder_dispense_multi",
            "description": (
                "Dispense the same powder amount to multiple wells at once.\n\n"
                "PLR: PowderDispenser.dispense(resources, powders, amounts) with lists."
            ),
            "parameters": _schema(
                {
                    "powder_name": {
                        "type": "string",
                        "description": "Name of the powder to dispense.",
                    },
                    "amount_mg": {
                        "type": "number",
                        "description": "Amount per well in milligrams.",
                    },
                    "target_wells": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of target well references.",
                    },
                },
                ["powder_name", "amount_mg", "target_wells"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "barcode_scan",
            "description": (
                "Scan the barcode of a plate or container to verify its "
                "identity.  Returns a barcode string like 'PLATE-001'.\n\n"
                "PLR: BarcodeScanner.scan()."
            ),
            "parameters": _schema({}, []),
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
    result = _dispatch(lab_state, name=name, arguments=arguments)

    from api_gym.worlds.pylabrobot_star_v0.replay import get_public_replay

    recorder = get_public_replay(run_dir)
    if recorder is not None:
        recorder.record_completed_tool(
            operation_id=name,
            arguments=arguments,
            simulated_at_seconds=lab_state.clock.current_time,
        )
    return result


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


# ── Robot arm handlers ───────────────────────────────────────────────────


def _arm_home(ls: LabState, _a: dict) -> dict:
    return services.arm_home(ls)


def _arm_move_to(ls: LabState, a: dict) -> dict:
    return services.arm_move_to(ls, x=float(a["x"]), y=float(a["y"]),
                                z=float(a["z"]))


def _arm_move_to_safe(ls: LabState, _a: dict) -> dict:
    return services.arm_move_to_safe(ls)


def _arm_approach(ls: LabState, a: dict) -> dict:
    return services.arm_approach(ls, x=float(a["x"]), y=float(a["y"]),
                                 z=float(a["z"]),
                                 access=a.get("access", "vertical"))


def _arm_pick_up_resource(ls: LabState, a: dict) -> dict:
    return services.arm_pick_up_resource(ls, x=float(a["x"]), y=float(a["y"]),
                                          z=float(a["z"]),
                                          plate_width_mm=float(a["plate_width_mm"]))


def _arm_drop_resource(ls: LabState, a: dict) -> dict:
    return services.arm_drop_resource(ls, x=float(a["x"]), y=float(a["y"]),
                                       z=float(a["z"]))


def _arm_open_gripper(ls: LabState, a: dict) -> dict:
    return services.arm_open_gripper(ls, width_mm=float(a["width_mm"]))


def _arm_close_gripper(ls: LabState, a: dict) -> dict:
    return services.arm_close_gripper(ls, width_mm=float(a["width_mm"]))


def _arm_get_position(ls: LabState, _a: dict) -> dict:
    return services.arm_get_position(ls)


def _arm_get_gripper_state(ls: LabState, _a: dict) -> dict:
    return services.arm_get_gripper_state(ls)


def _arm_halt(ls: LabState, _a: dict) -> dict:
    return services.arm_halt(ls)


# ── Plate sealer handlers ───────────────────────────────────────────────


def _sealer_seal(ls: LabState, a: dict) -> dict:
    return services.sealer_seal(ls, temperature=int(a["temperature"]),
                                duration_s=float(a["duration_s"]))


def _sealer_open(ls: LabState, _a: dict) -> dict:
    return services.sealer_open(ls)


def _sealer_close(ls: LabState, _a: dict) -> dict:
    return services.sealer_close(ls)


def _sealer_set_temperature(ls: LabState, a: dict) -> dict:
    return services.sealer_set_temperature(ls, temperature=float(a["temperature"]))


def _sealer_get_temperature(ls: LabState, _a: dict) -> dict:
    return services.sealer_get_temperature(ls)


# ── Plate peeler handlers ───────────────────────────────────────────────


def _peeler_seal_check(ls: LabState, _a: dict) -> dict:
    return services.peeler_seal_check(ls)


def _peeler_peel(ls: LabState, a: dict) -> dict:
    return services.peeler_peel(
        ls,
        begin_location=int(a.get("begin_location", 0)),
        fast=bool(a.get("fast", False)),
        adhere_time=float(a.get("adhere_time", 2.5)),
    )


def _peeler_move_conveyor_in(ls: LabState, _a: dict) -> dict:
    return services.peeler_move_conveyor_in(ls)


def _peeler_move_conveyor_out(ls: LabState, _a: dict) -> dict:
    return services.peeler_move_conveyor_out(ls)


def _peeler_move_elevator_up(ls: LabState, _a: dict) -> dict:
    return services.peeler_move_elevator_up(ls)


def _peeler_move_elevator_down(ls: LabState, _a: dict) -> dict:
    return services.peeler_move_elevator_down(ls)


def _peeler_advance_tape(ls: LabState, _a: dict) -> dict:
    return services.peeler_advance_tape(ls)


def _peeler_get_tape_remaining(ls: LabState, _a: dict) -> dict:
    return services.peeler_get_tape_remaining(ls)


def _peeler_get_status(ls: LabState, _a: dict) -> dict:
    return services.peeler_get_status(ls)


# ── Dedicated shaker handlers ───────────────────────────────────────────


def _shaker_lock_plate(ls: LabState, _a: dict) -> dict:
    return services.shaker_lock_plate(ls)


def _shaker_unlock_plate(ls: LabState, _a: dict) -> dict:
    return services.shaker_unlock_plate(ls)


def _shaker_shake(ls: LabState, a: dict) -> dict:
    return services.shaker_shake(
        ls, speed_rpm=float(a["speed_rpm"]),
        duration_s=float(a["duration_s"]) if a.get("duration_s") is not None else None,
    )


def _shaker_stop_shaking(ls: LabState, _a: dict) -> dict:
    return services.shaker_stop_shaking(ls)


# ── Temperature controller handlers ─────────────────────────────────────


def _temp_controller_set_temperature(ls: LabState, a: dict) -> dict:
    return services.tc_set_temperature(
        ls, temperature=float(a["temperature"]),
        passive=bool(a.get("passive", False)),
    )


def _temp_controller_get_temperature(ls: LabState, _a: dict) -> dict:
    return services.tc_get_temperature(ls)


def _temp_controller_deactivate(ls: LabState, _a: dict) -> dict:
    return services.temp_control_deactivate(ls)


def _temp_controller_wait_for_temperature(ls: LabState, a: dict) -> dict:
    return services.tc_wait_for_temperature(
        ls, timeout=float(a.get("timeout", 300)),
        tolerance=float(a.get("tolerance", 0.5)),
    )


# ── Tilter module handlers ──────────────────────────────────────────────


def _tilter_set_angle(ls: LabState, a: dict) -> dict:
    return services.tilter_set_angle(ls, angle=float(a["angle"]))


def _tilter_tilt(ls: LabState, a: dict) -> dict:
    return services.tilter_tilt(ls, relative_angle=float(a["relative_angle"]))


def _tilter_get_angle(ls: LabState, _a: dict) -> dict:
    return services.tilter_get_angle(ls)


def _tilter_return_to_level(ls: LabState, _a: dict) -> dict:
    return services.tilter_return_to_level(ls)


# ── Storage / incubator handlers ────────────────────────────────────────


def _storage_open_door(ls: LabState, _a: dict) -> dict:
    return services.storage_open_door(ls)


def _storage_close_door(ls: LabState, _a: dict) -> dict:
    return services.storage_close_door(ls)


def _storage_set_temperature(ls: LabState, a: dict) -> dict:
    return services.storage_set_temperature(ls, temperature=float(a["temperature"]))


def _storage_get_temperature(ls: LabState, _a: dict) -> dict:
    return services.storage_get_temperature(ls)


def _storage_start_shaking(ls: LabState, a: dict) -> dict:
    return services.storage_start_shaking(
        ls, frequency=float(a.get("frequency", 1.0)),
    )


def _storage_stop_shaking(ls: LabState, _a: dict) -> dict:
    return services.storage_stop_shaking(ls)


def _storage_store_plate(ls: LabState, a: dict) -> dict:
    return services.storage_store_plate(ls, plate_name=str(a["plate_name"]))


def _storage_retrieve_plate(ls: LabState, a: dict) -> dict:
    return services.storage_retrieve_plate(ls, plate_name=str(a["plate_name"]))


def _storage_get_free_sites(ls: LabState, _a: dict) -> dict:
    return services.storage_get_free_sites(ls)


# ── Powder dispenser handlers ───────────────────────────────────────────


def _powder_dispense(ls: LabState, a: dict) -> dict:
    return services.powder_dispense(
        ls, powder_name=str(a["powder_name"]),
        amount_mg=float(a["amount_mg"]),
        target_well=str(a["target_well"]),
    )


def _powder_dispense_multi(ls: LabState, a: dict) -> dict:
    return services.powder_dispense_multi(
        ls, powder_name=str(a["powder_name"]),
        amount_mg=float(a["amount_mg"]),
        target_wells=[str(w) for w in a["target_wells"]],
    )


# ── Barcode scanner handler ─────────────────────────────────────────────


def _barcode_scan(ls: LabState, _a: dict) -> dict:
    return services.barcode_scan(ls)


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
    # Robot arm
    "arm_home": _arm_home,
    "arm_move_to": _arm_move_to,
    "arm_move_to_safe": _arm_move_to_safe,
    "arm_approach": _arm_approach,
    "arm_pick_up_resource": _arm_pick_up_resource,
    "arm_drop_resource": _arm_drop_resource,
    "arm_open_gripper": _arm_open_gripper,
    "arm_close_gripper": _arm_close_gripper,
    "arm_get_position": _arm_get_position,
    "arm_get_gripper_state": _arm_get_gripper_state,
    "arm_halt": _arm_halt,
    # Plate sealer
    "sealer_seal": _sealer_seal,
    "sealer_open": _sealer_open,
    "sealer_close": _sealer_close,
    "sealer_set_temperature": _sealer_set_temperature,
    "sealer_get_temperature": _sealer_get_temperature,
    # Plate peeler
    "peeler_seal_check": _peeler_seal_check,
    "peeler_peel": _peeler_peel,
    "peeler_move_conveyor_in": _peeler_move_conveyor_in,
    "peeler_move_conveyor_out": _peeler_move_conveyor_out,
    "peeler_move_elevator_up": _peeler_move_elevator_up,
    "peeler_move_elevator_down": _peeler_move_elevator_down,
    "peeler_advance_tape": _peeler_advance_tape,
    "peeler_get_tape_remaining": _peeler_get_tape_remaining,
    "peeler_get_status": _peeler_get_status,
    # Dedicated shaker
    "shaker_lock_plate": _shaker_lock_plate,
    "shaker_unlock_plate": _shaker_unlock_plate,
    "shaker_shake": _shaker_shake,
    "shaker_stop_shaking": _shaker_stop_shaking,
    # Temperature controller
    "temp_controller_set_temperature": _temp_controller_set_temperature,
    "temp_controller_get_temperature": _temp_controller_get_temperature,
    "temp_controller_deactivate": _temp_controller_deactivate,
    "temp_controller_wait_for_temperature": _temp_controller_wait_for_temperature,
    # Tilter module
    "tilter_set_angle": _tilter_set_angle,
    "tilter_tilt": _tilter_tilt,
    "tilter_get_angle": _tilter_get_angle,
    "tilter_return_to_level": _tilter_return_to_level,
    # Storage / incubator
    "storage_open_door": _storage_open_door,
    "storage_close_door": _storage_close_door,
    "storage_set_temperature": _storage_set_temperature,
    "storage_get_temperature": _storage_get_temperature,
    "storage_start_shaking": _storage_start_shaking,
    "storage_stop_shaking": _storage_stop_shaking,
    "storage_store_plate": _storage_store_plate,
    "storage_retrieve_plate": _storage_retrieve_plate,
    "storage_get_free_sites": _storage_get_free_sites,
    # Powder dispenser
    "powder_dispense": _powder_dispense,
    "powder_dispense_multi": _powder_dispense_multi,
    # Barcode scanner
    "barcode_scan": _barcode_scan,
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
