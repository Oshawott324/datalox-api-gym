import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parents[2]


async def _drive(out_dir: Path) -> tuple[set[str], dict]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "api_gym.worlds.ot2_protocol_v0.mcp_server"],
        cwd=str(REPO),
        env={**os.environ, "OT2P_FAMILY": "stale_offsets", "OT2P_SEED": "0", "OT2P_MODE": "official_tools",
             "OT2P_OUT": str(out_dir)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}
            task = json.loads((await session.call_tool("get_task", {})).content[0].text)
            for name in task["records"]:
                await session.call_tool("read_record", {"name": name})
            assert not (out_dir / "verification.json").exists()
            await session.call_tool("submit_decision", {
                "decision": "defer", "reason": "calibration changed after the offsets were recorded",
                "cited_records": ["robot_calibration_status.json"]})
            await session.call_tool("finish", {})
    return tools, json.loads((out_dir / "verification.json").read_text())


def test_mcp_server_serves_one_episode_and_writes_trusted_result(tmp_path):
    tools, verification = asyncio.run(_drive(tmp_path / "out"))
    assert tools == {"get_task", "finish", "read_record", "submit_decision"}
    assert verification["task_id"] == "stale_offsets-official_tools-0000"
    assert verification["passed"], verification["failure_codes"]
