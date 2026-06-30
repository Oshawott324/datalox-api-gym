"""Agent-visible tool dispatch for the LabLongRun-Wet v0 prototype."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from greenfield_lablongrun.core.schemas import ActionError, tool_ok
from greenfield_lablongrun.core.trace import TraceRecorder
from greenfield_lablongrun.worlds.lablongrun_wet_v0 import dynamics


ToolFn = Callable[..., tuple[dict[str, Any], dict[str, Any]]]


TOOL_FUNCTIONS: dict[str, ToolFn] = {
    "get_deck_state": dynamics.get_deck_state,
    "get_labware_state": dynamics.get_labware_state,
    "pick_up_tip": dynamics.pick_up_tip,
    "drop_tip": dynamics.drop_tip,
    "aspirate": dynamics.aspirate,
    "dispense": dynamics.dispense,
    "mix": dynamics.mix,
    "wait": dynamics.wait,
    "read_absorbance": dynamics.read_absorbance,
    "add_workflow_note": dynamics.add_workflow_note,
    "submit_protocol_decision": dynamics.submit_protocol_decision,
}


def expected_tools() -> list[str]:
    return ["get_protocol_artifact", *TOOL_FUNCTIONS.keys()]


def dispatch_tool(db_path: Path, trace: TraceRecorder, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "get_protocol_artifact":
            result, diff = get_protocol_artifact(trace.run_dir, **arguments)
        else:
            tool_fn = TOOL_FUNCTIONS.get(name)
            if tool_fn is None:
                raise ActionError("UNKNOWN_TOOL", f"No LabLongRun-Wet tool named {name!r}.")
            result, diff = tool_fn(db_path, **arguments)
    except ActionError as exc:
        result = exc.to_result()
        sequence = trace.record_tool_call(name, arguments, result)
        return {**result, "tool_sequence": sequence}

    sequence = trace.record_tool_call(name, arguments, result)
    trace.record_state_diff(sequence, name, diff)
    return {**result, "tool_sequence": sequence}


def get_protocol_artifact(run_dir: Path, artifact_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if "/" in artifact_name or artifact_name.startswith("."):
        raise ActionError("INVALID_ARTIFACT_NAME", "Artifact name must be a simple file name.", {"artifact_name": artifact_name})
    path = run_dir / "visible_artifacts" / artifact_name
    if not path.exists():
        raise ActionError("UNKNOWN_ARTIFACT", f"No visible protocol artifact named {artifact_name!r}.")
    return (
        tool_ok({"artifact_name": artifact_name, "content": path.read_text(encoding="utf-8")}),
        {"artifact_read": artifact_name},
    )
