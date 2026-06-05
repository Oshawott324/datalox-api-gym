from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..registry import load_driver
from ..types import ToolCall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Datalox World API v0 CLI adapter.")
    sub = parser.add_subparsers(dest="command", required=True)
    smoke = sub.add_parser("smoke", help="Initialize a world session and run a minimal task-specific tool call.")
    smoke.add_argument("--world", required=True)
    smoke.add_argument("--task-id", required=True)
    smoke.add_argument("--run", required=True)
    args = parser.parse_args(argv)

    if args.command == "smoke":
        driver = load_driver(args.world)
        reset = driver.reset(args.task_id, Path(args.run))
        result = {
            "ok": True,
            "session_id": reset.session_id,
            "task_id": reset.task_id,
            "tool_names": [tool["name"] for tool in reset.tools],
            "run_dir": str(reset.run_dir),
        }
        if any(tool["name"] == "workspace.list_files" for tool in reset.tools):
            step = driver.step(reset.session_id, ToolCall("workspace.list_files", {}))
            result["first_step"] = step.observation
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
