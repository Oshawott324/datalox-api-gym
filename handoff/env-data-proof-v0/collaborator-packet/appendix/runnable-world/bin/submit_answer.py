#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from world_runtime import WorldError, submit_answer


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit an answer to a Datalox runnable-world verifier.")
    parser.add_argument("--run", required=True, help="Run directory.")
    parser.add_argument("answer_path", help="Path to answer JSON.")
    args = parser.parse_args()
    try:
        result = submit_answer(Path(args.run).resolve(), Path(args.answer_path).resolve())
    except WorldError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
