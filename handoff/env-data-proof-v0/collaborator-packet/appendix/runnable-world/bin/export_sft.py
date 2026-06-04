#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from world_runtime import WorldError, export_sft


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a passing runnable-world run to tool-message SFT JSONL.")
    parser.add_argument("--run", required=True, help="Run directory.")
    parser.add_argument("--out", required=True, help="Output JSONL path.")
    args = parser.parse_args()
    try:
        result = export_sft(Path(args.run).resolve(), Path(args.out).resolve())
    except WorldError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
