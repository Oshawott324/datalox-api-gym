"""Policies for the OT-2 protocol tasks.

The scripted policies use only what an agent can see (the public task and tool
results). They serve as the fixed-script baseline and as reference solutions.
``ChatPolicy`` calls any OpenAI-compatible chat-completions endpoint, such as
DeepSeek, with the same tools.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class PolicyStep:
    tool_calls: list[ToolCall]
    assistant_message: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)


class Policy(Protocol):
    name: str

    def step(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> PolicyStep: ...


def _assistant(calls: list[ToolCall]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": c.call_id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
            for c in calls
        ],
    }


def _last_tool_result(messages: list[dict[str, Any]]) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("role") == "tool":
            return json.loads(message["content"])
    return {}


class _ScriptBase:
    name = "script"

    def __init__(self) -> None:
        self._count = 0
        self.task: dict[str, Any] | None = None

    def _calls(self, *pairs: tuple[str, dict[str, Any]]) -> PolicyStep:
        calls = []
        for name, arguments in pairs:
            self._count += 1
            calls.append(ToolCall(f"call_{self._count}", name, arguments))
        return PolicyStep(calls, _assistant(calls))

    def step(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> PolicyStep:
        if self.task is None:
            if self._count == 0:
                return self._calls(("get_task", {}))
            self.task = _last_tool_result(messages)
        return self.next(messages)

    def next(self, messages: list[dict[str, Any]]) -> PolicyStep:
        raise NotImplementedError


class ArcScript(_ScriptBase):
    """Visits each target with an explicit, conservative arc height.

    Variants reproduce common mistakes for checker controls.
    """

    def __init__(self, minimum_z_height: float | None = 130.0, force_direct: bool = False,
                 skip_last_target: bool = False, free_code_extra: str = "") -> None:
        super().__init__()
        self.minimum_z_height = minimum_z_height
        self.force_direct = force_direct
        self.skip_last_target = skip_last_target
        self.free_code_extra = free_code_extra
        self.name = f"arc_script(min_z={minimum_z_height}, force_direct={force_direct})"
        self._submitted = False

    def next(self, messages: list[dict[str, Any]]) -> PolicyStep:
        if self._submitted:
            return self._calls(("finish", {}))
        self._submitted = True
        task = self.task or {}
        mount = task["pipette"]["mount"]
        targets = [t["slot"] for t in task["targets"]]
        if self.skip_last_target:
            targets = targets[:-1]
        if task["mode"] == "free_code":
            return self._calls(("analyze_protocol", {"source": self._protocol(task, targets)}))
        operations: list[dict[str, Any]] = [{"op": "home"}, {"op": "pick_up_tip", "pipette": mount}]
        for slot in targets:
            move: dict[str, Any] = {"op": "move_to", "pipette": mount, "slot": slot, "well": "A1", "reference": "top"}
            if self.minimum_z_height is not None:
                move["minimum_z_height_mm"] = self.minimum_z_height
            if self.force_direct:
                move["force_direct"] = True
            operations.append(move)
        operations.append({"op": "drop_tip", "pipette": mount})
        return self._calls(("analyze_operations", {"operations": operations}))

    def _protocol(self, task: dict[str, Any], targets: list[str]) -> str:
        lines = ["from opentrons import protocol_api", "",
                 f'requirements = {{"robotType": "OT-2", "apiLevel": "{task["robot"]["api_level"]}"}}', "", "",
                 "def run(protocol: protocol_api.ProtocolContext):"]
        pipette = task["pipette"]
        lines.append(f'    tips = protocol.load_labware("{pipette["tip_rack"]}", {pipette["tip_rack_slot"]})')
        for slot in targets:
            item = task["deck"][slot]
            namespace = f', namespace="{item["namespace"]}", version={item["version"]}' if "namespace" in item else ""
            lines.append(f'    rack_{slot} = protocol.load_labware("{item["load_name"]}", {slot}{namespace})')
        lines.append(f'    pip = protocol.load_instrument("{pipette["name"]}", "{pipette["mount"]}", tip_racks=[tips])')
        lines.append("    protocol.home()")
        lines.append("    pip.pick_up_tip()")
        for slot in targets:
            arguments = [f'rack_{slot}["A1"].top()']
            if self.minimum_z_height is not None:
                arguments.append(f"minimum_z_height={self.minimum_z_height}")
            if self.force_direct:
                arguments.append("force_direct=True")
            lines.append(f"    pip.move_to({', '.join(arguments)})")
        lines.append("    pip.drop_tip()")
        if self.free_code_extra:
            lines.extend("    " + line for line in self.free_code_extra.splitlines())
        return "\n".join(lines) + "\n"


class ProbeScript(_ScriptBase):
    """Steps down using only the coarse level; the step for each level is fixed by the script."""

    def __init__(self, steps_by_level: dict[str, float], stop_levels: tuple[str, ...] = ("almost touching",)) -> None:
        super().__init__()
        self.steps_by_level = steps_by_level
        self.stop_levels = stop_levels
        self.name = "probe_script(" + "/".join(f"{v:g}" for v in steps_by_level.values()) + ")"
        self.depth = 0.0
        self.level: str | None = None

    def next(self, messages: list[dict[str, Any]]) -> PolicyStep:
        last = _last_tool_result(messages)
        if "level" in last:
            self.level = last["level"]
        if self.level is None:
            self.level = self._initial_level()
        if self.level in self.stop_levels or self.level not in self.steps_by_level:
            return self._calls(("finish", {}))
        self.depth = round(self.depth + self.steps_by_level[self.level], 3)
        return self._calls(("probe_move", {"depth_below_top_mm": self.depth}))

    def _initial_level(self) -> str:
        return (self.task or {})["start"]["level"]


CAUTIOUS_PROBE_STEPS = {"far": 10.0, "near": 3.0, "very close": 1.0}
TABLE_PROBE_STEPS = {"far": 10.0, "near": 5.0, "very close": 1.0}


class StaleOffsetScript(_ScriptBase):
    """Reads every record and applies an offset file only if it was recorded under the current calibration."""

    def __init__(self, always: str | None = None) -> None:
        super().__init__()
        self.always = always
        self.name = "stale_offset_script" if always is None else f"stale_offset_script(always={always})"
        self._pending: list[str] | None = None
        self._records: dict[str, Any] = {}

    def next(self, messages: list[dict[str, Any]]) -> PolicyStep:
        last = _last_tool_result(messages)
        if "content" in last:
            self._records[last["name"]] = last["content"]
        if self._pending is None:
            self._pending = list((self.task or {}).get("records", []))
        if self._pending:
            return self._calls(("read_record", {"name": self._pending.pop(0)}))
        if "accepted" in last:
            return self._calls(("finish", {}))
        status = self._records["robot_calibration_status.json"]
        current = {"deck_attitude": status["deck_attitude"], "pipette_offset_mm": status["pipette_offset_mm"]}
        fresh = [name for name, content in self._records.items()
                 if isinstance(content, dict) and content.get("robot_calibration_at_recording") == current]
        decision = self.always or ("proceed" if fresh else "defer")
        chosen = (fresh[0] if fresh else "labware_offsets_worktree_B.json") if decision == "proceed" else None
        cited = ["robot_calibration_status.json"] + ([chosen] if chosen else [])
        return self._calls(("submit_decision", {
            "decision": decision, "offsets_record": chosen, "cited_records": cited,
            "reason": "compared calibration recorded with each offset file against the current calibration",
        }))


class ChatPolicy:
    """OpenAI-compatible chat completions with tool calling (DeepSeek, OpenAI, local servers)."""

    def __init__(self, model: str, base_url: str, api_key_env: str, extra_body: dict[str, Any] | None = None,
                 timeout_s: float = 300.0) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = os.environ.get(api_key_env)
        if not self.api_key:
            raise RuntimeError(f"Set {api_key_env} to call {self.base_url}")
        self.extra_body = extra_body or {}
        self.timeout_s = timeout_s
        self.name = f"chat({model})"

    def step(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> PolicyStep:
        body = {"model": self.model, "messages": messages, "tools": tools, "tool_choice": "auto", **self.extra_body}
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            payload = json.loads(response.read())
        message = payload["choices"][0]["message"]
        calls = []
        for item in message.get("tool_calls") or []:
            try:
                arguments = json.loads(item["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {"_unparseable_arguments": item["function"].get("arguments")}
            calls.append(ToolCall(item["id"], item["function"]["name"], arguments))
        # Reasoning text is not sent back; some providers reject it in later requests.
        assistant = {key: message[key] for key in ("role", "content", "tool_calls") if key in message}
        assistant.setdefault("content", None)
        return PolicyStep(calls, assistant, payload.get("usage") or {})


def timed(policy: Policy, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> tuple[PolicyStep, float]:
    started = time.monotonic()
    step = policy.step(messages, tools)
    return step, time.monotonic() - started
