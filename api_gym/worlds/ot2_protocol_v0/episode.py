"""One episode: tool handlers, public results, and the trusted record the checks read."""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from api_gym.worlds.ot2_protocol_v0.compliance import Violation, check_protocol_source
from api_gym.worlds.ot2_protocol_v0.native import AnalysisResult
from api_gym.worlds.ot2_protocol_v0.tasks import PROBE_MAX_MOVES, SLOT3_LOAD, TaskInstance, probe_level, reference

WELL_NAME = re.compile(r"^[A-P](?:[1-9]|1[0-9]|2[0-4])$")
OPERATIONS = ("pick_up_tip", "drop_tip", "move_to", "home")


class Analyzer(Protocol):
    def analyze(self, source: str) -> AnalysisResult: ...


class ToolError(ValueError):
    """An invalid request; returned to the agent, never executed."""


@dataclass
class Submission:
    source: str
    operations: list[dict[str, Any]] | None
    violations: tuple[Violation, ...]
    analysis: AnalysisResult


@dataclass
class EpisodeLog:
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    submissions: list[Submission] = field(default_factory=list)
    probe_depths_mm: list[float] = field(default_factory=lambda: [0.0])
    probe_levels: list[str] = field(default_factory=list)
    records_read: list[str] = field(default_factory=list)
    decision: dict[str, Any] | None = None
    finished: bool = False
    terminal_reason: str | None = None


class Episode:
    def __init__(self, task: TaskInstance, analyzer: Analyzer | None = None) -> None:
        self.task = task
        self.analyzer = analyzer
        self.log = EpisodeLog()
        if task.family == "probe_tube_bottom":
            self.log.probe_levels.append(self._level(0.0))
        self._handlers = {
            "get_task": self._get_task,
            "finish": self._finish,
        }
        if task.family == "arc_four_slots":
            if task.mode == "free_code":
                self._handlers["analyze_protocol"] = self._analyze_protocol
            else:
                self._handlers["analyze_operations"] = self._analyze_operations
        elif task.family == "probe_tube_bottom":
            self._handlers["probe_move"] = self._probe_move
        elif task.family == "stale_offsets":
            self._handlers.update({"read_record": self._read_record, "submit_decision": self._submit_decision})

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        started = time.monotonic()
        if name not in self._handlers:
            result: dict[str, Any] = {"error": f"unknown tool {name!r}"}
        elif self.log.finished and name != "get_task":
            result = {"error": "episode already finished"}
        else:
            try:
                result = self._handlers[name](**arguments)
            except ToolError as error:
                result = {"error": str(error)}
            except TypeError as error:
                result = {"error": f"invalid arguments: {error}"}
        self.log.tool_calls.append(
            {"tool": name, "arguments": arguments, "result": result, "duration_s": round(time.monotonic() - started, 4)}
        )
        return result

    # Shared tools -----------------------------------------------------------------------------------------------

    def _get_task(self) -> dict[str, Any]:
        return self.task.public

    def _finish(self) -> dict[str, Any]:
        self.log.finished = True
        self.log.terminal_reason = self.log.terminal_reason or "agent_finished"
        return {"status": "finished"}

    # Arc task ---------------------------------------------------------------------------------------------------

    def _analyze_protocol(self, source: str) -> dict[str, Any]:
        if not isinstance(source, str) or not source.strip():
            raise ToolError("source must be a non-empty protocol")
        return self._submit(source, None)

    def _analyze_operations(self, operations: list[dict[str, Any]]) -> dict[str, Any]:
        validated = [_validate_operation(op, index) for index, op in enumerate(operations or [])]
        if not validated:
            raise ToolError("operations must be a non-empty list")
        return self._submit(render_protocol(validated), validated)

    def _submit(self, source: str, operations: list[dict[str, Any]] | None) -> dict[str, Any]:
        if self.analyzer is None:
            raise ToolError("no official analyzer is configured for this episode")
        analysis = self.analyzer.analyze(source)
        violations = check_protocol_source(source) if operations is None else ()
        self.log.submissions.append(Submission(source, operations, violations, analysis))
        return {"submission": len(self.log.submissions), "official_analysis": analysis.public_summary()}

    # Probe task -------------------------------------------------------------------------------------------------

    def _level(self, depth_mm: float) -> str:
        return probe_level(self.task.hidden["physical_depth_mm"], depth_mm)

    def _probe_move(self, depth_below_top_mm: float) -> dict[str, Any]:
        if self.log.terminal_reason == "contact":
            raise ToolError("the tip reached the contact-risk level; no further moves are possible")
        if len(self.log.probe_depths_mm) - 1 >= PROBE_MAX_MOVES:
            raise ToolError(f"move limit of {PROBE_MAX_MOVES} reached")
        depth = float(depth_below_top_mm)
        if not math.isfinite(depth) or depth < 0 or depth > 120:
            raise ToolError("depth_below_top_mm must be between 0 and 120")
        self.log.probe_depths_mm.append(depth)
        level = self._level(depth)
        self.log.probe_levels.append(level)
        response = {"depth_below_top_mm": depth, "official_call": f"move_to(well.top(z={-depth:g}))", "level": level}
        if level == "contact risk":
            self.log.terminal_reason = "contact"
            self.log.finished = True
            response["episode"] = "ended: the tip reached the contact-risk level"
        return response

    # Stale-offset task ------------------------------------------------------------------------------------------

    def _read_record(self, name: str) -> dict[str, Any]:
        records = self.task.hidden["records"]
        if name not in records:
            raise ToolError(f"no record named {name!r}; available: {sorted(records)}")
        if name not in self.log.records_read:
            self.log.records_read.append(name)
        return {"name": name, "content": records[name]}

    def _submit_decision(self, decision: str, reason: str, cited_records: list[str],
                         offsets_record: str | None = None) -> dict[str, Any]:
        if self.log.decision is not None:
            raise ToolError("a decision was already submitted")
        if decision not in ("proceed", "defer"):
            raise ToolError("decision must be 'proceed' or 'defer'")
        if decision == "proceed" and not offsets_record:
            raise ToolError("proceed requires offsets_record")
        self.log.decision = {"decision": decision, "offsets_record": offsets_record, "reason": str(reason),
                             "cited_records": [str(item) for item in (cited_records or [])]}
        return {"accepted": True}


def _validate_operation(op: Any, index: int) -> dict[str, Any]:
    if not isinstance(op, dict) or op.get("op") not in OPERATIONS:
        raise ToolError(f"operation {index}: 'op' must be one of {OPERATIONS}")
    kind = op["op"]
    if kind == "home":
        return {"op": "home"}
    mount = op.get("pipette")
    if mount not in ("left", "right"):
        raise ToolError(f"operation {index}: 'pipette' must be 'left' or 'right'")
    if kind in ("pick_up_tip", "drop_tip"):
        return {"op": kind, "pipette": mount}
    slot = str(op.get("slot", ""))
    if slot not in reference()["deck"]:
        raise ToolError(f"operation {index}: unknown slot {slot!r}")
    well = str(op.get("well", ""))
    if not WELL_NAME.match(well):
        raise ToolError(f"operation {index}: invalid well name {well!r}")
    ref = op.get("reference", "top")
    if ref not in ("top", "bottom"):
        raise ToolError(f"operation {index}: reference must be 'top' or 'bottom'")
    z_offset = _finite(op.get("z_offset_mm", 0.0), index, "z_offset_mm")
    min_z = op.get("minimum_z_height_mm")
    force_direct = op.get("force_direct", False)
    if not isinstance(force_direct, bool):
        raise ToolError(f"operation {index}: force_direct must be true or false")
    return {"op": "move_to", "pipette": mount, "slot": slot, "well": well, "reference": ref, "z_offset_mm": z_offset,
            "minimum_z_height_mm": None if min_z is None else _finite(min_z, index, "minimum_z_height_mm"),
            "force_direct": force_direct}


def _finite(value: Any, index: int, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ToolError(f"operation {index}: {name} must be a number") from error
    if not math.isfinite(number):
        raise ToolError(f"operation {index}: {name} must be finite")
    return number


def render_protocol(operations: list[dict[str, Any]]) -> str:
    """Write validated official operations as an official Python protocol."""
    ref = reference()
    lines = [
        "from opentrons import protocol_api",
        "",
        f'requirements = {{"robotType": "OT-2", "apiLevel": "{ref["robot"]["api_level"]}"}}',
        "",
        "",
        "def run(protocol: protocol_api.ProtocolContext):",
        "    labware = {}",
    ]
    for slot, item in ref["deck"].items():
        if item.get("custom"):
            lines.append(
                f'    labware["{slot}"] = protocol.load_labware("{SLOT3_LOAD["load_name"]}", {slot}, '
                f'namespace="{SLOT3_LOAD["namespace"]}", version={SLOT3_LOAD["version"]})'
            )
        else:
            lines.append(f'    labware["{slot}"] = protocol.load_labware("{item["load_name"]}", {slot})')
    lines.append("    pipettes = {}")
    for mount, spec in ref["robot"]["pipettes"].items():
        lines.append(
            f'    pipettes["{mount}"] = protocol.load_instrument("{spec["name"]}", "{mount}", '
            f'tip_racks=[labware["{spec["tip_rack_slot"]}"]])'
        )
    for op in operations:
        if op["op"] == "home":
            lines.append("    protocol.home()")
        elif op["op"] in ("pick_up_tip", "drop_tip"):
            lines.append(f'    pipettes["{op["pipette"]}"].{op["op"]}()')
        else:
            target = f'labware["{op["slot"]}"]["{op["well"]}"].{op["reference"]}(z={op["z_offset_mm"]!r})'
            arguments = [target]
            if op["minimum_z_height_mm"] is not None:
                arguments.append(f"minimum_z_height={op['minimum_z_height_mm']!r}")
            if op["force_direct"]:
                arguments.append("force_direct=True")
            lines.append(f'    pipettes["{op["pipette"]}"].move_to({", ".join(arguments)})')
    return "\n".join(lines) + "\n"
