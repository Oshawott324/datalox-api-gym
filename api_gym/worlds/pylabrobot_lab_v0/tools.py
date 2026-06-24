"""OpenAI-compatible tool schemas and dispatcher for pylabrobot_lab_v0."""

from __future__ import annotations

import json
from typing import Any, Callable

from api_gym.worlds.pylabrobot_lab_v0 import services
from api_gym.worlds.pylabrobot_lab_v0.state import LabState

ToolHandler = Callable[[LabState, dict[str, Any]], dict[str, Any]]


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_deck_state",
            "description": "Inspect the dry-run deck mode and loaded labware with their positions.",
            "parameters": _schema({}, []),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_labware_state",
            "description": (
                "Inspect one loaded labware object (plate or tip rack), including "
                "well volumes, max capacities, and tip availability."
            ),
            "parameters": _schema({"labware_id": {"type": "string"}}, ["labware_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aspirate",
            "description": (
                "Dry-run aspirate from a source well using an available tip. "
                "The pipette must be empty before aspirating.  Reference format: "
                "'labware_name:well_id' (e.g. 'source_plate:A1')."
            ),
            "parameters": _schema(
                {
                    "source": {"type": "string", "description": "Well reference such as source_plate:A1."},
                    "volume_ul": {"type": "number", "exclusiveMinimum": 0},
                    "tip": {"type": "string", "description": "Tip reference such as tip_rack_01:A1."},
                },
                ["source", "volume_ul", "tip"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dispense",
            "description": (
                "Dry-run dispense pending aspirated volume into a target well. "
                "Reference format: 'labware_name:well_id' (e.g. 'assay_plate:B1')."
            ),
            "parameters": _schema(
                {
                    "target": {"type": "string", "description": "Well reference such as assay_plate:B1."},
                    "volume_ul": {"type": "number", "exclusiveMinimum": 0},
                    "mix_after": {"type": "boolean", "default": False},
                },
                ["target", "volume_ul"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_absorbance",
            "description": "Create a dry-run absorbance readout for one or more plate wells.",
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
            "name": "add_workflow_note",
            "description": "Add an internal dry-run workflow note.",
            "parameters": _schema({"note": {"type": "string"}}, ["note"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_protocol",
            "description": "Submit the final plate QC protocol decision with readout evidence.",
            "parameters": _schema(
                {
                    "decision": {"type": "string", "enum": ["continue", "hold"]},
                    "evidence_readout_id": {"type": "string"},
                    "target_well": {"type": "string", "description": "Well reference such as assay_plate:B1."},
                    "rationale": {"type": "string"},
                },
                ["decision", "evidence_readout_id", "target_well", "rationale"],
            ),
        },
    },
]


from pathlib import Path

from api_gym.worlds.pylabrobot_lab_v0.state import get_state


def dispatch_tool(run_dir: Path, *, name: str,
                  arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call by name, resolving LabState from the run directory.

    This is the registry-compatible entry point (signature: Path -> dispatch).
    """
    lab_state = get_state(run_dir)
    return _dispatch(lab_state, name=name, arguments=arguments)


def _dispatch(lab_state: LabState, *, name: str,
              arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call by name against the in-memory LabState."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return _tool_error(
            "unknown_tool",
            "Tool name is not registered for this world.",
            {"tool_name": name},
        )
    try:
        return handler(lab_state, arguments)
    except KeyError as exc:
        return _tool_error(
            "missing_tool_argument",
            "A required tool argument is missing.",
            {"tool_name": name, "argument": str(exc).strip("'")},
        )
    except (TypeError, ValueError) as exc:
        return _tool_error(
            "invalid_tool_arguments",
            "Tool arguments do not match the tool schema.",
            {"tool_name": name, "message": str(exc)},
        )


def dispatch_tool_call(run_dir: Path, tool_call: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one OpenAI-compatible function call from a run directory."""
    name, arguments = _extract_name_and_arguments(tool_call)
    if name is None:
        return _tool_error("missing_tool_name", "Tool call is missing a function name.", {})
    if arguments is None:
        return _tool_error("invalid_tool_arguments", "Tool arguments must be a JSON object.", {})
    return dispatch_tool(run_dir, name=name, arguments=arguments)


def _extract_name_and_arguments(tool_call: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    function = tool_call.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        raw_arguments = function.get("arguments", {})
    else:
        name = tool_call.get("name")
        raw_arguments = tool_call.get("arguments", {})

    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return str(name) if name is not None else None, None
    else:
        arguments = raw_arguments

    if not isinstance(arguments, dict):
        return str(name) if name is not None else None, None
    return str(name) if name is not None else None, arguments


# ── Handlers ────────────────────────────────────────────────────────────


def _get_deck_state(lab_state: LabState, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.get_deck_state(lab_state)


def _get_labware_state(lab_state: LabState, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.get_labware_state(lab_state, labware_id=str(arguments["labware_id"]))


def _aspirate(lab_state: LabState, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.aspirate(
        lab_state,
        source=str(arguments["source"]),
        volume_ul=float(arguments["volume_ul"]),
        tip_ref=str(arguments["tip"]),
    )


def _dispense(lab_state: LabState, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.dispense(
        lab_state,
        target=str(arguments["target"]),
        volume_ul=float(arguments["volume_ul"]),
        mix_after=bool(arguments.get("mix_after", False)),
    )


def _read_absorbance(lab_state: LabState, arguments: dict[str, Any]) -> dict[str, Any]:
    wells = arguments["wells"]
    if not isinstance(wells, list):
        raise TypeError("wells must be a list")
    return services.read_absorbance(
        lab_state,
        plate_id=str(arguments["plate_id"]),
        wavelength_nm=int(arguments["wavelength_nm"]),
        wells=[str(w) for w in wells],
    )


def _add_workflow_note(lab_state: LabState, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.add_workflow_note(lab_state, note=str(arguments["note"]))


def _submit_protocol(lab_state: LabState, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.submit_protocol(
        lab_state,
        decision=str(arguments["decision"]),
        evidence_readout_id=str(arguments["evidence_readout_id"]),
        target_well=str(arguments["target_well"]),
        rationale=str(arguments["rationale"]),
    )


def _tool_error(code: str, message: str,
                details: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_deck_state": _get_deck_state,
    "get_labware_state": _get_labware_state,
    "aspirate": _aspirate,
    "dispense": _dispense,
    "read_absorbance": _read_absorbance,
    "add_workflow_note": _add_workflow_note,
    "submit_protocol": _submit_protocol,
}
