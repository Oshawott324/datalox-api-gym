"""Validate Lab Campaign Ops source-pack skeletons."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = "greenfield_lab_campaign_ops.source_pack.v0"
REQUIRED_FIELDS = {
    "schema_version",
    "source_pack_id",
    "provider",
    "role",
    "source_status",
    "evidence_urls",
    "tools",
    "fixtures",
    "dry_run_semantics",
    "live_boundary",
    "allowed_errors",
    "source_gaps",
}
ALLOWED_SOURCE_STATUSES = {
    "source_grounded",
    "domain_reviewed",
    "speculative_calibration_only",
}
ALLOWED_FIXTURE_STATUSES = {
    "source_copied_example",
    "derived_from_source_example",
    "speculative_fixture_for_schema_exercise",
}


def main() -> int:
    packs = sorted(path for path in ROOT.glob("*_v*/source_pack.json"))
    failures: list[str] = []
    if not packs:
        failures.append("NO_SOURCE_PACKS: no */source_pack.json files found")

    seen_pack_ids: set[str] = set()
    for pack_path in packs:
        failures.extend(_validate_pack(pack_path, seen_pack_ids))

    if failures:
        for failure in failures:
            print(failure)
        return 1

    print(f"Validated {len(packs)} source pack(s).")
    return 0


def _validate_pack(pack_path: Path, seen_pack_ids: set[str]) -> list[str]:
    failures: list[str] = []
    pack = _read_json(pack_path)
    rel = pack_path.relative_to(ROOT)

    missing = sorted(REQUIRED_FIELDS - set(pack))
    if missing:
        failures.append(f"{rel}: MISSING_FIELDS {missing}")
        return failures

    if pack["schema_version"] != SCHEMA_VERSION:
        failures.append(f"{rel}: BAD_SCHEMA_VERSION {pack['schema_version']!r}")
    if pack["source_status"] not in ALLOWED_SOURCE_STATUSES:
        failures.append(f"{rel}: BAD_SOURCE_STATUS {pack['source_status']!r}")

    pack_id = pack["source_pack_id"]
    if pack_id in seen_pack_ids:
        failures.append(f"{rel}: DUPLICATE_SOURCE_PACK_ID {pack_id}")
    seen_pack_ids.add(pack_id)
    if pack_path.parent.name != pack_id:
        failures.append(f"{rel}: DIRECTORY_MISMATCH expected directory {pack_id!r}")

    failures.extend(_validate_evidence_urls(pack_path, pack))
    failures.extend(_validate_tools(pack_path, pack))
    failures.extend(_validate_fixtures(pack_path, pack))
    failures.extend(_validate_live_boundary(pack_path, pack))
    failures.extend(_validate_allowed_errors(pack_path, pack))
    return failures


def _validate_evidence_urls(pack_path: Path, pack: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    seen_labels: set[str] = set()
    for index, item in enumerate(_expect_list(pack.get("evidence_urls"))):
        label = item.get("label")
        url = item.get("url")
        if not label or not isinstance(label, str):
            failures.append(f"{pack_path}: evidence_urls[{index}] missing label")
        elif label in seen_labels:
            failures.append(f"{pack_path}: DUPLICATE_EVIDENCE_LABEL {label}")
        else:
            seen_labels.add(label)
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            failures.append(f"{pack_path}: evidence_urls[{index}] invalid url")
    return failures


def _validate_tools(pack_path: Path, pack: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    tools = _expect_list(pack.get("tools"))
    if not tools:
        return [f"{pack_path}: NO_TOOLS"]

    evidence_labels = {item["label"] for item in _expect_list(pack.get("evidence_urls")) if "label" in item}
    fixture_ids = {item["fixture_id"] for item in _expect_list(pack.get("fixtures")) if "fixture_id" in item}
    seen_tool_ids: set[str] = set()
    for index, tool in enumerate(tools):
        tool_id = tool.get("tool_id")
        if not tool_id:
            failures.append(f"{pack_path}: tools[{index}] missing tool_id")
        elif tool_id in seen_tool_ids:
            failures.append(f"{pack_path}: DUPLICATE_TOOL_ID {tool_id}")
        else:
            seen_tool_ids.add(tool_id)

        for source_ref in _expect_list(tool.get("source_refs")):
            if source_ref not in evidence_labels:
                failures.append(f"{pack_path}: tool {tool_id} unknown source_ref {source_ref}")
        for fixture_ref in _expect_list(tool.get("fixture_refs", [])):
            if fixture_ref not in fixture_ids:
                failures.append(f"{pack_path}: tool {tool_id} unknown fixture_ref {fixture_ref}")
        if not str(tool.get("dry_run_behavior", "")).strip():
            failures.append(f"{pack_path}: tool {tool_id} missing dry_run_behavior")
    return failures


def _validate_fixtures(pack_path: Path, pack: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    evidence_labels = {item["label"] for item in _expect_list(pack.get("evidence_urls")) if "label" in item}
    seen_fixture_ids: set[str] = set()
    for fixture in _expect_list(pack.get("fixtures")):
        fixture_id = fixture.get("fixture_id")
        if not fixture_id:
            failures.append(f"{pack_path}: fixture missing fixture_id")
        elif fixture_id in seen_fixture_ids:
            failures.append(f"{pack_path}: DUPLICATE_FIXTURE_ID {fixture_id}")
        else:
            seen_fixture_ids.add(fixture_id)

        if fixture.get("fixture_status") not in ALLOWED_FIXTURE_STATUSES:
            failures.append(f"{pack_path}: fixture {fixture_id} bad fixture_status")
        fixture_path = pack_path.parent / fixture.get("path", "")
        if not fixture_path.is_file():
            failures.append(f"{pack_path}: fixture {fixture_id} missing file {fixture_path}")
        for source_ref in _expect_list(fixture.get("source_refs")):
            if source_ref not in evidence_labels:
                failures.append(f"{pack_path}: fixture {fixture_id} unknown source_ref {source_ref}")
    return failures


def _validate_live_boundary(pack_path: Path, pack: dict[str, Any]) -> list[str]:
    boundary = pack.get("live_boundary")
    if not isinstance(boundary, dict):
        return [f"{pack_path}: live_boundary must be object"]
    statement = str(boundary.get("boundary_statement", "")).lower()
    forbidden = _expect_list(boundary.get("forbidden_actions"))
    failures = []
    if not forbidden:
        failures.append(f"{pack_path}: live_boundary.forbidden_actions empty")
    if "live" not in statement and "hardware" not in statement and "production" not in statement:
        failures.append(f"{pack_path}: live_boundary statement must mention live/hardware/production")
    return failures


def _validate_allowed_errors(pack_path: Path, pack: dict[str, Any]) -> list[str]:
    failures = []
    seen_codes: set[str] = set()
    for item in _expect_list(pack.get("allowed_errors")):
        code = item.get("code")
        if not code:
            failures.append(f"{pack_path}: allowed error missing code")
        elif code in seen_codes:
            failures.append(f"{pack_path}: DUPLICATE_ERROR_CODE {code}")
        else:
            seen_codes.add(code)
        if not str(item.get("meaning", "")).strip():
            failures.append(f"{pack_path}: allowed error {code} missing meaning")
    return failures


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _expect_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


if __name__ == "__main__":
    sys.exit(main())
