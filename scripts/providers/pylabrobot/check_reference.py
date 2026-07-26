#!/usr/bin/env python3
"""Re-execute and verify the checked-in PyLabRobot reference source pack."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api_gym.source_packs import validate_source_pack
from scripts.providers.pylabrobot.capture_reference import (
    DEFAULT_OUTPUT,
    write_capture,
)
from api_gym.provider_components.pylabrobot.executor import (
    capture_reference_sequences,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check retained PyLabRobot captures against fresh local execution."
    )
    parser.add_argument("--source-pack", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    fresh = capture_reference_sequences()
    with tempfile.TemporaryDirectory(prefix="datalox-plr-check-") as temp_dir:
        generated = Path(temp_dir) / "2026-07-26"
        write_capture(generated, fresh)
        mismatches = _compare_trees(args.source_pack, generated)

    validation = validate_source_pack(args.source_pack)
    result = {
        "ok": not mismatches and validation["ok"] is True,
        "mismatches": mismatches,
        "source_pack_id": validation["source_pack_id"],
        "record_counts": validation["record_counts"],
        "sequence_count": len(fresh["sequences"]),
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


def _compare_trees(expected: Path, actual: Path) -> list[str]:
    expected_files = {
        path.relative_to(expected)
        for path in expected.rglob("*")
        if path.is_file()
    }
    actual_files = {
        path.relative_to(actual)
        for path in actual.rglob("*")
        if path.is_file()
    }
    mismatches = [
        f"missing_generated:{path}" for path in sorted(expected_files - actual_files)
    ]
    mismatches.extend(
        f"unexpected_generated:{path}" for path in sorted(actual_files - expected_files)
    )
    for relative in sorted(expected_files & actual_files):
        if (expected / relative).read_bytes() != (actual / relative).read_bytes():
            mismatches.append(f"content:{relative}")
    return mismatches


if __name__ == "__main__":
    raise SystemExit(main())
