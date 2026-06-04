#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from world_runtime import WorldError, call_tool


def main() -> int:
    parser = argparse.ArgumentParser(description="Call a local Datalox runnable-world tool.")
    parser.add_argument("--run", required=True, help="Run directory.")
    parser.add_argument("tool_name", help="Tool name.")
    parser.add_argument("arguments_json", help="Tool arguments as a JSON object.")
    args = parser.parse_args()
    try:
        arguments = json.loads(args.arguments_json)
        if not isinstance(arguments, dict):
            raise WorldError("Tool arguments must be a JSON object.")
        observation = call_tool(Path(args.run).resolve(), args.tool_name, arguments)
    except (json.JSONDecodeError, WorldError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(observation, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
