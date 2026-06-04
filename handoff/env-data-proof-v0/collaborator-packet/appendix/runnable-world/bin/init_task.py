#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from world_runtime import WorldError, create_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a Datalox runnable-world task workspace.")
    parser.add_argument("--task", required=True, help="Task id to initialize.")
    parser.add_argument("--run", required=True, help="Run directory to create.")
    args = parser.parse_args()
    try:
        run = create_run(args.task, Path(args.run).resolve())
    except WorldError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "run_dir": run["run_dir"], "workspace_dir": run["workspace_dir"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
