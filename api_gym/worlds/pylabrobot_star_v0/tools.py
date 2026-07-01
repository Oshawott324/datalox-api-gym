"""OpenAI-compatible tool schemas and dispatcher for pylabrobot_star_v0."""

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


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    # ── Inspection ──
    {
        "type": "function",
        "function": {
            "name": "get_deck_state",
            "description": "Inspect the STAR deck: loaded carriers, labware, and instrument status (single-channel, 96-head, iSWAP arm).",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_labware_state",
            "description": "Inspect one labware item (plate, tip rack, trough, tube rack) including well volumes and tip availability.",
            "parameters": _schema({"labware_id": {"type": "string"}}, ["labware_id"]),
        },
    },
    # ── Single-channel ──
    {
        "type": "function",
        "function": {
            "name": "aspirate",
            "description": "Pick up a single tip and aspirate from a source well. Format: 'labware:well' (e.g. 'source_plate:A1').",
            "parameters": _schema({
                "source": {"type": "string", "description": "Well ref: labware:well (e.g. source_plate:A1)."},
                "volume_ul": {"type": "number", "exclusiveMinimum": 0},
                "tip": {"type": "string", "description": "Tip ref: tip_rack:well (e.g. tip_rack_01:A1)."},
            }, ["source", "volume_ul", "tip"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispense",
            "description": "Dispense into a target well and return the tip. Format: 'labware:well'.",
            "parameters": _schema({
                "target": {"type": "string", "description": "Well ref: labware:well (e.g. assay_plate:B1)."},
                "volume_ul": {"type": "number", "exclusiveMinimum": 0},
                "mix_after": {"type": "boolean", "default": False},
            }, ["target", "volume_ul"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discard_tips",
            "description": "Discard the currently mounted tip(s) to the trash area.",
            "parameters": _schema({}, []),
        },
    },
    # ── 96-head ──
    {
        "type": "function",
        "function": {
            "name": "pick_up_tips96",
            "description": "Pick up a full rack of 96 tips using the 96-channel head. Requires 96-head to be installed.",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aspirate96",
            "description": "Aspirate from all 96 wells of a plate simultaneously using the 96-head. Requires tips already picked up via pick_up_tips96.",
            "parameters": _schema({
                "plate_id": {"type": "string", "description": "Plate name on the deck."},
                "volume_ul": {"type": "number", "exclusiveMinimum": 0},
            }, ["plate_id", "volume_ul"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispense96",
            "description": "Dispense to all 96 wells of a plate simultaneously using the 96-head.",
            "parameters": _schema({
                "plate_id": {"type": "string", "description": "Plate name on the deck."},
                "volume_ul": {"type": "number", "exclusiveMinimum": 0},
            }, ["plate_id", "volume_ul"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discard_tips96",
            "description": "Discard all 96 tips from the 96-head to the waste area.",
            "parameters": _schema({}, []),
        },
    },
    # ── iSWAP arm ──
    {
        "type": "function",
        "function": {
            "name": "move_plate",
            "description": "Move a plate to a different deck position using the iSWAP robotic arm. Requires iSWAP to be installed.",
            "parameters": _schema({
                "plate_id": {"type": "string", "description": "Name of the plate to move."},
                "to_position": {"type": "string", "description": "Destination resource name (e.g. carrier site, incubator)."},
            }, ["plate_id", "to_position"]),
        },
    },
    # ── Workspace files ──
    {
        "type": "function",
        "function": {
            "name": "list_workspace_files",
            "description": "List available workspace files (protocol, plate map, reagent inventory, prior run log). Always check this first to understand the task context.",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workspace_file",
            "description": "Read the content of a specific workspace file.",
            "parameters": _schema({"filename": {"type": "string"}}, ["filename"]),
        },
    },
    # ── Reading ──
    {
        "type": "function",
        "function": {
            "name": "read_absorbance",
            "description": "Read OD absorbance for specified wells at a given wavelength (simulated plate reader).",
            "parameters": _schema({
                "plate_id": {"type": "string"},
                "wavelength_nm": {"type": "integer"},
                "wells": {"type": "array", "items": {"type": "string"}},
            }, ["plate_id", "wavelength_nm", "wells"]),
        },
    },
    # ── Workflow ──
    {
        "type": "function",
        "function": {
            "name": "add_workflow_note",
            "description": "Add a workflow note to the run record.",
            "parameters": _schema({"note": {"type": "string"}}, ["note"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_protocol",
            "description": "Submit the final QC protocol decision with supporting readout evidence.",
            "parameters": _schema({
                "decision": {"type": "string", "enum": ["continue", "hold"]},
                "evidence_readout_id": {"type": "string"},
                "target_well": {"type": "string", "description": "Well ref: labware:well."},
                "rationale": {"type": "string"},
            }, ["decision", "evidence_readout_id", "target_well", "rationale"]),
        },
    },
]


# ── Dispatch ────────────────────────────────────────────────────────────


def dispatch_tool(run_dir: Path, *, name: str,
                  arguments: dict[str, Any]) -> dict[str, Any]:
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


# ── Handlers ────────────────────────────────────────────────────────────


def _get_deck_state(ls: LabState, _a: dict) -> dict:
    return services.get_deck_state(ls)


def _get_labware_state(ls: LabState, a: dict) -> dict:
    return services.get_labware_state(ls, labware_id=str(a["labware_id"]))


def _aspirate(ls: LabState, a: dict) -> dict:
    return services.aspirate(ls, source=str(a["source"]),
                             volume_ul=float(a["volume_ul"]),
                             tip_ref=str(a["tip"]))


def _dispense(ls: LabState, a: dict) -> dict:
    return services.dispense(ls, target=str(a["target"]),
                             volume_ul=float(a["volume_ul"]),
                             mix_after=bool(a.get("mix_after", False)))


def _discard_tips(ls: LabState, _a: dict) -> dict:
    return services.discard_tips(ls)


def _pick_up_tips96(ls: LabState, _a: dict) -> dict:
    return services.pick_up_tips96(ls)


def _aspirate96(ls: LabState, a: dict) -> dict:
    return services.aspirate96(ls, plate_id=str(a["plate_id"]),
                               volume_ul=float(a["volume_ul"]))


def _dispense96(ls: LabState, a: dict) -> dict:
    return services.dispense96(ls, plate_id=str(a["plate_id"]),
                               volume_ul=float(a["volume_ul"]))


def _discard_tips96(ls: LabState, _a: dict) -> dict:
    return services.discard_tips96(ls)


def _move_plate(ls: LabState, a: dict) -> dict:
    return services.move_plate(ls, plate_id=str(a["plate_id"]),
                               to_position=str(a["to_position"]))


def _list_workspace_files(ls: LabState, _a: dict) -> dict:
    return services.list_workspace_files(ls)


def _get_workspace_file(ls: LabState, a: dict) -> dict:
    return services.get_workspace_file(ls, filename=str(a["filename"]))


def _read_absorbance(ls: LabState, a: dict) -> dict:
    wells = a["wells"]
    if not isinstance(wells, list):
        raise TypeError("wells must be a list")
    return services.read_absorbance(ls, plate_id=str(a["plate_id"]),
                                    wavelength_nm=int(a["wavelength_nm"]),
                                    wells=[str(w) for w in wells])


def _add_workflow_note(ls: LabState, a: dict) -> dict:
    return services.add_workflow_note(ls, note=str(a["note"]))


def _submit_protocol(ls: LabState, a: dict) -> dict:
    return services.submit_protocol(ls, decision=str(a["decision"]),
                                    evidence_readout_id=str(a["evidence_readout_id"]),
                                    target_well=str(a["target_well"]),
                                    rationale=str(a["rationale"]))


def _tool_error(code: str, message: str, details: dict) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_deck_state": _get_deck_state,
    "get_labware_state": _get_labware_state,
    "aspirate": _aspirate,
    "dispense": _dispense,
    "discard_tips": _discard_tips,
    "pick_up_tips96": _pick_up_tips96,
    "aspirate96": _aspirate96,
    "dispense96": _dispense96,
    "discard_tips96": _discard_tips96,
    "move_plate": _move_plate,
    "list_workspace_files": _list_workspace_files,
    "get_workspace_file": _get_workspace_file,
    "read_absorbance": _read_absorbance,
    "add_workflow_note": _add_workflow_note,
    "submit_protocol": _submit_protocol,
}
