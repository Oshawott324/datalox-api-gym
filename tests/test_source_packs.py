from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from api_gym.cli import app
from api_gym.source_packs import SourcePackValidationError, validate_source_pack, validate_world_source_refs


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_source_pack_validator_accepts_minimal_real_pack(tmp_path: Path) -> None:
    pack_root = _write_minimal_source_pack(tmp_path)

    result = validate_source_pack(pack_root)

    assert result["ok"] is True
    assert result["source_pack_id"] == "api.example.2026-06-12"
    assert result["record_counts"] == {"operations": 1, "response_cases": 1, "world_candidates": 1}


def test_source_pack_validator_rejects_live_execution_allowed(tmp_path: Path) -> None:
    pack_root = _write_minimal_source_pack(tmp_path)
    source_pack_path = pack_root / "source_pack.json"
    payload = json.loads(source_pack_path.read_text(encoding="utf-8"))
    payload["live_execution"]["allowed"] = True
    source_pack_path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        validate_source_pack(pack_root)
    except SourcePackValidationError as exc:
        assert exc.code == "source_pack_live_execution_not_allowed"
        assert exc.details == {"path": str(source_pack_path)}
    else:
        raise AssertionError("expected SourcePackValidationError")


def test_source_pack_validator_rejects_empty_listed_record_file(tmp_path: Path) -> None:
    pack_root = _write_minimal_source_pack(tmp_path)
    (pack_root / "operations.jsonl").write_text("", encoding="utf-8")

    try:
        validate_source_pack(pack_root)
    except SourcePackValidationError as exc:
        assert exc.code == "source_pack_record_file_empty"
        assert exc.details == {"path": str(pack_root / "operations.jsonl")}
    else:
        raise AssertionError("expected SourcePackValidationError")


def test_source_pack_validator_requires_response_case_per_operation(tmp_path: Path) -> None:
    pack_root = _write_minimal_source_pack(tmp_path)
    (pack_root / "response_cases.jsonl").write_text(
        json.dumps(
            {
                "id": "response_case:otherOperation:success",
                "source_pack_id": "api.example.2026-06-12",
                "operation_ref": "operation:otherOperation",
                "case": "success",
                "status": "2xx",
                "response_mode": "body_shape",
                "source_refs": [{"kind": "docs", "url": "https://docs.example.invalid/widgets"}],
                "body_shape": {"object": "Widget"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        validate_source_pack(pack_root)
    except SourcePackValidationError as exc:
        assert exc.code == "source_pack_response_case_missing"
        assert exc.details == {"path": str(pack_root / "response_cases.jsonl"), "operation_ref": "operation:listWidgets"}
    else:
        raise AssertionError("expected SourcePackValidationError")


def test_source_pack_validate_cli_reports_json(tmp_path: Path) -> None:
    pack_root = _write_minimal_source_pack(tmp_path)

    result = CliRunner().invoke(app, ["source-pack", "validate", str(pack_root)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["source_pack_id"] == "api.example.2026-06-12"


def test_existing_world_source_refs_are_valid() -> None:
    for rel_path in [
        "worlds/billing_support_v0/source_refs.json",
        "worlds/unitelabs_plate_qc_v0/source_refs.json",
    ]:
        result = validate_world_source_refs(REPO_ROOT / rel_path)
        assert result["ok"] is True
        assert result["world"]
        assert result["citation_count"] > 0


def test_checked_in_source_packs_validate() -> None:
    roots = sorted((REPO_ROOT / "source_packs" / "apis").glob("*/*/source_pack.json"))

    assert roots
    for source_pack_json in roots:
        result = validate_source_pack(source_pack_json.parent)
        assert result["ok"] is True
        assert result["source_pack_id"]


def test_world_source_refs_reject_missing_jsonl_record(tmp_path: Path) -> None:
    world_root = tmp_path / "worlds" / "example_world_v0"
    world_root.mkdir(parents=True)
    (world_root / "evidence.jsonl").write_text(
        json.dumps({"id": "present.record", "source_pack_id": "api.example.2026-06-12"}) + "\n",
        encoding="utf-8",
    )
    refs_path = world_root / "source_refs.json"
    refs_path.write_text(
        json.dumps(
            {
                "schema_version": "api_gym.world_source_refs.v0",
                "world": "example_world_v0",
                "world_evidence": [
                    {
                        "path": "evidence.jsonl",
                        "records": ["missing.record"],
                        "role": "test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        validate_world_source_refs(refs_path)
    except SourcePackValidationError as exc:
        assert exc.code == "world_source_record_missing"
        assert exc.details == {"path": str(world_root / "evidence.jsonl"), "record": "missing.record"}
    else:
        raise AssertionError("expected SourcePackValidationError")


def _write_minimal_source_pack(tmp_path: Path) -> Path:
    pack_root = tmp_path / "source_packs" / "apis" / "example" / "2026-06-12"
    pack_root.mkdir(parents=True)
    (pack_root / "source_pack.json").write_text(
        json.dumps(
            {
                "schema_version": "api_gym.api_source_pack.v0",
                "source_pack_id": "api.example.2026-06-12",
                "provider": "example",
                "version": "2026-06-12",
                "status": "normalized",
                "source_types": ["docs"],
                "records": {
                    "operations": "operations.jsonl",
                    "response_cases": "response_cases.jsonl",
                    "world_candidates": "world_candidates.jsonl",
                },
                "live_execution": {
                    "allowed": False,
                    "reason": "Source substrate only.",
                },
            }
        ),
        encoding="utf-8",
    )
    (pack_root / "operations.jsonl").write_text(
        json.dumps(
            {
                "id": "operation:listWidgets",
                "source_pack_id": "api.example.2026-06-12",
                "operation_id": "listWidgets",
                "method": "GET",
                "path": "/widgets",
                "source_refs": [{"kind": "docs", "url": "https://docs.example.invalid/widgets"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (pack_root / "world_candidates.jsonl").write_text(
        json.dumps(
            {
                "id": "world_candidate:widget_triage_v0",
                "source_pack_id": "api.example.2026-06-12",
                "candidate_world": "widget_triage_v0",
                "operation_refs": ["operation:listWidgets"],
                "design_status": "candidate",
                "not_world_contract": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (pack_root / "response_cases.jsonl").write_text(
        json.dumps(
            {
                "id": "response_case:listWidgets:success",
                "source_pack_id": "api.example.2026-06-12",
                "operation_ref": "operation:listWidgets",
                "case": "success",
                "status": "2xx",
                "response_mode": "body_shape",
                "source_refs": [{"kind": "docs", "url": "https://docs.example.invalid/widgets"}],
                "body_shape": {"object": "Widget"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return pack_root
