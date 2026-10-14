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
    recorded_offsets: dict[str, list[float]] = field(default_factory=dict)
    run_offsets: dict[str, list[float]] = field(default_factory=dict)
    runs_started: int = 0
    tip_position_mm: list[float] | None = None
    tip_slot: str | None = None
    moves: int = 0
    operator_questions: int = 0
    readbacks: int = 0
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
        elif task.family == "measure_offset":
            self.log.run_offsets = {task.hidden["slot"]: list(task.hidden["current_run_offset_mm"])}
            self._run_id = "run-0"
            self._handlers.update({
                "read_record": self._read_record,
                "get_current_run": self._get_current_run,
                "start_run": self._start_run,
                "move_to_well_top": self._move_to_well_top,
                "jog": self._jog,
                "read_position": self._read_position,
                "ask_operator": self._ask_operator,
                "record_offset": self._record_offset,
            })

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


    # Offset measurement -----------------------------------------------------------------------------------------

    def physical_mouth(self, slot: str) -> list[float]:
        """Trusted: where the tube mouth centre physically is."""
        measurement = reference()["offset_measurement"]
        true = (self.task.hidden["true_offset_mm"] if slot == self.task.hidden["slot"]
                else measurement["measured_true_offset_mm"][slot])
        return [m + t for m, t in zip(measurement["model_a1_top_readback_mm"][slot], true)]

    def _contact(self) -> str | None:
        if self.log.tip_position_mm is None or self.log.tip_slot is None:
            return None
        mouth = self.physical_mouth(self.log.tip_slot)
        dx, dy, dz = (p - m for p, m in zip(self.log.tip_position_mm, mouth))
        if dz >= -0.5:
            return None
        if math.hypot(dx, dy) > self.task.hidden["tube_radius_mm"] - 0.3:
            return "the tip hit the rack beside the tube mouth"
        if -dz > self.task.hidden["tube_depth_mm"] - 1.0:
            return "the tip reached the tube bottom"
        return None

    def _after_motion(self, response: dict[str, Any]) -> dict[str, Any]:
        self.log.moves += 1
        contact = self._contact()
        if contact:
            self.log.terminal_reason = "contact"
            self.log.finished = True
            response["episode"] = f"ended: {contact}"
        return response

    def _require_motion_allowed(self) -> None:
        if self.log.terminal_reason == "contact":
            raise ToolError("the episode ended after contact")
        if self.log.moves >= MAX_OFFSET_MOVES:
            raise ToolError(f"move limit of {MAX_OFFSET_MOVES} reached")

    def _get_current_run(self) -> dict[str, Any]:
        return {"id": self._run_id, "labwareOffsets": [
            {"location": {"slotName": slot}, "vector": dict(zip("xyz", vector))}
            for slot, vector in sorted(self.log.run_offsets.items())]}

    def _start_run(self, labware_offsets: str) -> dict[str, Any]:
        if labware_offsets not in ("none", "file"):
            raise ToolError("labware_offsets must be 'none' or 'file'")
        file_offsets = self.task.hidden["records"]["labware_offsets.json"]["labware_offsets_mm"]
        self.log.runs_started += 1
        self._run_id = f"run-{self.log.runs_started}"
        self.log.run_offsets = ({} if labware_offsets == "none"
                                else {slot: list(file_offsets[slot]) for slot in OFFSET_SLOTS})
        self.log.tip_position_mm, self.log.tip_slot = None, None
        return self._get_current_run()

    def _move_to_well_top(self, slot: str) -> dict[str, Any]:
        self._require_motion_allowed()
        slot = str(slot)
        if slot not in OFFSET_SLOTS:
            raise ToolError(f"slot must be one of {OFFSET_SLOTS}")
        model = reference()["offset_measurement"]["model_a1_top_readback_mm"][slot]
        applied = self.log.run_offsets.get(slot, [0.0, 0.0, 0.0])
        self.log.tip_position_mm = [m + a for m, a in zip(model, applied)]
        self.log.tip_slot = slot
        return self._after_motion({"status": "succeeded", "command": f"moveToWell slot {slot} A1 top"})

    def _jog(self, dx: float, dy: float, dz: float) -> dict[str, Any]:
        self._require_motion_allowed()
        if self.log.tip_position_mm is None:
            raise ToolError("move to a well top first")
        delta = _vector((dx, dy, dz), "jog")
        if any(abs(d) > 10.0 for d in delta):
            raise ToolError("each jog axis must be within 10 mm")
        self.log.tip_position_mm = [p + d for p, d in zip(self.log.tip_position_mm, delta)]
        return self._after_motion({"status": "succeeded", "command": "moveRelative"})

    def _read_position(self) -> dict[str, Any]:
        if self.log.tip_position_mm is None:
            raise ToolError("no position yet: move to a well top first")
        self.log.readbacks += 1
        position = (round(v, 2) for v in self.log.tip_position_mm)
        return {"command": "moveRelative(distance=0)", "position": dict(zip("xyz", position))}

    def _ask_operator(self) -> dict[str, Any]:
        self.log.operator_questions += 1
        if self.log.tip_position_mm is None or self.log.tip_slot is None:
            return {"observation": "The tip is not over a tube rack."}
        mouth = self.physical_mouth(self.log.tip_slot)
        parts = []
        for error, (positive, negative) in zip((p - m for p, m in zip(self.log.tip_position_mm, mouth)), AXES):
            if abs(error) <= 0.2:
                continue
            direction = positive if error > 0 else negative
            parts.append(f"slightly {direction}" if abs(error) <= 1.0
                         else f"about {round(abs(error) * 2) / 2:g} mm {direction}")
        if not parts:
            return {"observation": "The tip is centred on the tube mouth."}
        return {"observation": "The tip is " + ", ".join(parts) + "."}

    def _record_offset(self, slot: str, x: float, y: float, z: float) -> dict[str, Any]:
        slot = str(slot)
        if slot not in OFFSET_SLOTS:
            raise ToolError(f"slot must be one of {OFFSET_SLOTS}")
        self.log.recorded_offsets[slot] = _vector((x, y, z), "offset")
        return {"recorded": {"slot": slot, "offset_mm": dict(zip("xyz", self.log.recorded_offsets[slot]))}}


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


OFFSET_SLOTS = ("3", "6", "7", "8")
AXES = (("right", "left"), ("back", "front"), ("high", "low"))
MAX_OFFSET_MOVES = 60


def _vector(values: Any, name: str) -> list[float]:
    try:
        vector = [float(v) for v in values]
    except (TypeError, ValueError) as error:
        raise ToolError(f"{name} must be three numbers") from error
    if len(vector) != 3 or not all(math.isfinite(v) for v in vector):
        raise ToolError(f"{name} must be three finite numbers")
    return vector
