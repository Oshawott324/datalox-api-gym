from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from api_gym.cli import app
from api_gym.worlds.source_refs import validate_world_source_refs


def test_validate_billing_world_source_refs() -> None:
    result = validate_world_source_refs("billing_support_v0")

    assert result["ok"] is True
    assert result["world"] == "billing_support_v0"
    assert result["source_pack_count"] == 3
    assert result["world_evidence_count"] == 2


def test_validate_unitelabs_world_source_refs_without_source_packs() -> None:
    result = validate_world_source_refs("unitelabs_plate_qc_v0")

    assert result["ok"] is True
    assert result["world"] == "unitelabs_plate_qc_v0"
    assert result["source_pack_count"] == 0
    assert result["world_evidence_count"] == 2


def test_validate_world_source_refs_reports_missing_record(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    world_dir = repo_root / "worlds" / "example_world"
    pack_dir = repo_root / "source_packs" / "apis" / "example" / "2026-06-22"
    world_dir.mkdir(parents=True)
    pack_dir.mkdir(parents=True)
    (pack_dir / "source_pack.json").write_text(
        json.dumps(
            {
                "records": {
                    "operations": "operations.jsonl",
                    "response_cases": "response_cases.jsonl",
                }
            }
        ),
        encoding="utf-8",
    )
    (pack_dir / "operations.jsonl").write_text(
        json.dumps({"id": "operation:known"}) + "\n",
        encoding="utf-8",
    )
    (pack_dir / "response_cases.jsonl").write_text("", encoding="utf-8")
    (world_dir / "source_refs.json").write_text(
        json.dumps(
            {
                "schema_version": "api_gym.world_source_refs.v0",
                "world": "example_world",
                "source_packs": [
                    {
                        "source_pack_id": "api.example.2026-06-22",
                        "path": "../../source_packs/apis/example/2026-06-22/source_pack.json",
                        "records": ["operation:missing"],
                        "role": "test",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validate_world_source_refs("example_world", repo_root=repo_root)

    assert result["ok"] is False
    assert result["missing_records"] == [
        {
            "source_pack_id": "api.example.2026-06-22",
            "record_id": "operation:missing",
        }
    ]


def test_world_source_refs_validate_cli() -> None:
    result = CliRunner().invoke(app, ["world-source-refs", "validate", "--world", "billing_support_v0"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["world"] == "billing_support_v0"
