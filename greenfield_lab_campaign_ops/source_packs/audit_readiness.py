"""Audit which greenfield source packs meet the current build-readiness gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
ADMITTED_RESPONSE_BODY_STATUSES = {
    "exact_public_json_body",
    "captured_probe_response",
}
ADMITTED_FIXTURE_STATUSES = {
    "source_copied_example",
    "captured_probe_response",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--fail-if-excluded",
        action="store_true",
        help="Exit nonzero when any source pack is excluded by the strict gate.",
    )
    args = parser.parse_args()

    results = [_audit_pack(path) for path in sorted(ROOT.glob("*_v*/source_pack.json"))]
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        _print_text(results)

    has_excluded = any(result["readiness_status"] == "excluded" for result in results)
    return 1 if args.fail_if_excluded and has_excluded else 0


def _audit_pack(path: Path) -> dict[str, Any]:
    pack = json.loads(path.read_text(encoding="utf-8"))
    reasons: list[str] = []

    if pack.get("source_status") != "source_grounded":
        reasons.append(f"source_status is {pack.get('source_status')!r}, not 'source_grounded'")
    if pack.get("tool_surface_status") != "source_grounded":
        reasons.append(
            f"tool_surface_status is {pack.get('tool_surface_status')!r}, not 'source_grounded'"
        )
    if pack.get("response_body_status") not in ADMITTED_RESPONSE_BODY_STATUSES:
        reasons.append(
            "response_body_status is "
            f"{pack.get('response_body_status')!r}; strict gate requires exact public JSON "
            "or captured probe response"
        )

    fixtures = pack.get("fixtures", [])
    if not fixtures:
        reasons.append("no fixtures")
    for fixture in fixtures:
        status = fixture.get("fixture_status")
        if status not in ADMITTED_FIXTURE_STATUSES:
            reasons.append(
                f"fixture {fixture.get('fixture_id')!r} has status {status!r}; "
                "strict gate allows only source-copied or captured fixtures"
            )

    readiness_status = "excluded" if reasons else "admitted"
    return {
        "source_pack_id": pack.get("source_pack_id", path.parent.name),
        "provider": pack.get("provider"),
        "role": pack.get("role"),
        "readiness_status": readiness_status,
        "response_body_status": pack.get("response_body_status"),
        "fixture_statuses": sorted({fixture.get("fixture_status") for fixture in fixtures}),
        "reasons": reasons,
    }


def _print_text(results: list[dict[str, Any]]) -> None:
    admitted = [result for result in results if result["readiness_status"] == "admitted"]
    excluded = [result for result in results if result["readiness_status"] == "excluded"]

    print("Admitted source packs:")
    for result in admitted:
        print(f"- {result['source_pack_id']}: {result['response_body_status']}")

    print("\nExcluded source packs:")
    for result in excluded:
        print(f"- {result['source_pack_id']}:")
        for reason in result["reasons"]:
            print(f"  - {reason}")


if __name__ == "__main__":
    sys.exit(main())
