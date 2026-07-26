#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from api_gym.provider_components.elabftw.reference_conformance import (
    DEFAULT_CAPTURE_PATH,
    DEFAULT_REPORT_PATH,
    run_projection_conformance,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check the bounded eLabFTW projection against retained real evidence."
    )
    parser.add_argument("--capture", type=Path, default=DEFAULT_CAPTURE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    report = run_projection_conformance(
        capture_path=args.capture,
        report_path=args.output,
    )
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
