"""Agent-facing tool descriptions, shared by the MCP server and the in-process runner."""

from __future__ import annotations

from typing import Any

from api_gym.worlds.ot2_protocol_v0.episode import OPERATIONS

TOOL_SPECS: dict[str, dict[str, Any]] = {
    "get_task": {
        "description": "Return the task: instruction, robot setup, rules and any operator note.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "finish": {
        "description": "End the episode. Call this once you are done; nothing can be changed afterwards.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    "analyze_protocol": {
        "description": (
            "Run the official Opentrons analyzer (opentrons analyze, OT-2) on a complete Python protocol and return "
            "its result. Nothing runs on a robot. The last submission before finish is evaluated."
        ),
        "parameters": {
            "type": "object",
            "properties": {"source": {"type": "string", "description": "Complete OT-2 Python protocol source."}},
            "required": ["source"],
            "additionalProperties": False,
        },
    },
    "analyze_operations": {
        "description": (
            "Build an OT-2 protocol from official operations (the deck and pipettes in the task are loaded for you) "
            "and run the official Opentrons analyzer on it. The last submission before finish is evaluated."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": list(OPERATIONS)},
                            "pipette": {"type": "string", "enum": ["left", "right"]},
                            "slot": {"type": "string"},
                            "well": {"type": "string"},
                            "reference": {"type": "string", "enum": ["top", "bottom"]},
                            "z_offset_mm": {"type": "number"},
                            "minimum_z_height_mm": {"type": "number"},
                            "force_direct": {"type": "boolean"},
                        },
                        "required": ["op"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["operations"],
            "additionalProperties": False,
        },
    },
    "probe_move": {
        "description": (
            "Move the tip to the given depth below the top of well A1 in slot 3, i.e. "
            "move_to(well.top(z=-depth_below_top_mm)). Returns the operator's coarse distance level."
        ),
        "parameters": {
            "type": "object",
            "properties": {"depth_below_top_mm": {"type": "number"}},
            "required": ["depth_below_top_mm"],
            "additionalProperties": False,
        },
    },
    "read_record": {
        "description": "Read one record listed in the task.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    "submit_decision": {
        "description": "Submit the run decision once. proceed requires offsets_record.",
        "parameters": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["proceed", "defer"]},
                "offsets_record": {"type": "string"},
                "reason": {"type": "string"},
                "cited_records": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["decision", "reason", "cited_records"],
            "additionalProperties": False,
        },
    },
}


def openai_tools(tool_names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": name, **TOOL_SPECS[name]}}
        for name in tool_names
    ]
