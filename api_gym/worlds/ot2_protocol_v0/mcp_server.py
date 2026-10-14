"""MCP stdio server for one OT-2 protocol episode, for external agent hosts.

Configuration comes from the trusted launcher, never from the agent:

    OT2P_FAMILY, OT2P_SEED, OT2P_MODE   which task instance to serve
    OT2P_OUT                            directory for the trusted result (not readable by the agent)
    DATALOX_OT2_ANALYSIS_PYTHON         interpreter with the OT-2-capable opentrons package

    python -m api_gym.worlds.ot2_protocol_v0.mcp_server
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from api_gym.worlds.ot2_protocol_v0.episode import Episode
from api_gym.worlds.ot2_protocol_v0.native import OfficialAnalyzer
from api_gym.worlds.ot2_protocol_v0.tasks import make_task
from api_gym.worlds.ot2_protocol_v0.tools import TOOL_SPECS
from api_gym.worlds.ot2_protocol_v0.verifier import verify


def build_server(episode: Episode, out_dir: Path) -> FastMCP:
    server = FastMCP("datalox-ot2-protocol")

    def record() -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "verification.json").write_text(json.dumps(verify(episode).to_dict(), indent=2) + "\n")
        (out_dir / "tool_calls.json").write_text(json.dumps(episode.log.tool_calls, indent=2, default=str) + "\n")

    def call(name: str, arguments: dict[str, Any]) -> str:
        result = episode.call(name, arguments)
        if episode.log.finished:
            record()
        return json.dumps(result)

    if "get_task" in episode.tool_names:
        @server.tool(name="get_task", description=TOOL_SPECS["get_task"]["description"])
        def get_task() -> str:
            return call("get_task", {})

    if "finish" in episode.tool_names:
        @server.tool(name="finish", description=TOOL_SPECS["finish"]["description"])
        def finish() -> str:
            return call("finish", {})

    if "analyze_protocol" in episode.tool_names:
        @server.tool(name="analyze_protocol", description=TOOL_SPECS["analyze_protocol"]["description"])
        def analyze_protocol(source: str) -> str:
            return call("analyze_protocol", {"source": source})

    if "analyze_operations" in episode.tool_names:
        @server.tool(name="analyze_operations", description=TOOL_SPECS["analyze_operations"]["description"])
        def analyze_operations(operations: list[dict[str, Any]]) -> str:
            return call("analyze_operations", {"operations": operations})

    if "probe_move" in episode.tool_names:
        @server.tool(name="probe_move", description=TOOL_SPECS["probe_move"]["description"])
        def probe_move(depth_below_top_mm: float) -> str:
            return call("probe_move", {"depth_below_top_mm": depth_below_top_mm})

    if "read_record" in episode.tool_names:
        @server.tool(name="read_record", description=TOOL_SPECS["read_record"]["description"])
        def read_record(name: str) -> str:
            return call("read_record", {"name": name})

    if "submit_decision" in episode.tool_names:
        @server.tool(name="submit_decision", description=TOOL_SPECS["submit_decision"]["description"])
        def submit_decision(decision: str, reason: str, cited_records: list[str],
                            offsets_record: str | None = None) -> str:
            return call("submit_decision", {"decision": decision, "reason": reason,
                                            "cited_records": cited_records, "offsets_record": offsets_record})

    if "get_current_run" in episode.tool_names:
        @server.tool(name="get_current_run", description=TOOL_SPECS["get_current_run"]["description"])
        def get_current_run() -> str:
            return call("get_current_run", {})

        @server.tool(name="start_run", description=TOOL_SPECS["start_run"]["description"])
        def start_run(labware_offsets: str) -> str:
            return call("start_run", {"labware_offsets": labware_offsets})

        @server.tool(name="move_to_well_top", description=TOOL_SPECS["move_to_well_top"]["description"])
        def move_to_well_top(slot: str) -> str:
            return call("move_to_well_top", {"slot": slot})

        @server.tool(name="jog", description=TOOL_SPECS["jog"]["description"])
        def jog(dx: float, dy: float, dz: float) -> str:
            return call("jog", {"dx": dx, "dy": dy, "dz": dz})

        @server.tool(name="read_position", description=TOOL_SPECS["read_position"]["description"])
        def read_position() -> str:
            return call("read_position", {})

        @server.tool(name="ask_operator", description=TOOL_SPECS["ask_operator"]["description"])
        def ask_operator() -> str:
            return call("ask_operator", {})

        @server.tool(name="record_offset", description=TOOL_SPECS["record_offset"]["description"])
        def record_offset(slot: str, x: float, y: float, z: float) -> str:
            return call("record_offset", {"slot": slot, "x": x, "y": y, "z": z})

    return server


def main() -> None:
    task = make_task(os.environ["OT2P_FAMILY"], int(os.environ.get("OT2P_SEED", "0")),
                     os.environ.get("OT2P_MODE", "official_tools"))
    analyzer = OfficialAnalyzer() if task.family == "arc_four_slots" else None
    episode = Episode(task, analyzer)
    build_server(episode, Path(os.environ["OT2P_OUT"])).run()


if __name__ == "__main__":
    main()
