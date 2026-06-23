from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from api_gym.cli import app
from api_gym.world_blueprints import (
    WorldBlueprintError,
    scaffold_research_world_from_blueprint,
    validate_research_world_blueprint,
)


BLUEPRINT = Path("blueprints/research/dose_response_assay_env_v0.json")


def test_dose_response_blueprint_validates() -> None:
    result = validate_research_world_blueprint(BLUEPRINT)

    assert result["ok"] is True
    assert result["world"] == "dose_response_assay_env_v0"
    assert result["world_id"] == "dose-response-assay-env-v0"
    assert "eight_point_viability_ic50" in result["scenarios"]
    assert "submit_assay_report" in result["actions"]
    assert "final_report_cites_traceable_evidence" in result["verifier_checks"]


def test_world_blueprint_scaffold_writes_non_registered_world(tmp_path: Path) -> None:
    result = scaffold_research_world_from_blueprint(BLUEPRINT, out_root=tmp_path)

    world_dir = tmp_path / "worlds" / "dose_response_assay_env_v0"
    runtime_dir = tmp_path / "api_gym" / "worlds" / "dose_response_assay_env_v0"
    assert result["registered"] is False
    assert world_dir.exists()
    assert runtime_dir.exists()

    spec = json.loads((world_dir / "spec.json").read_text(encoding="utf-8"))
    assert spec["world"] == "dose_response_assay_env_v0"
    assert spec["runtime"]["status"] == "scaffolded_not_registered"
    assert spec["tools"] == [
        "inspect_assay_state",
        "propose_plate_map",
        "run_transfer_dry",
        "read_plate_dry",
        "run_assay_qc",
        "fit_dose_response",
        "submit_assay_report",
    ]

    task = json.loads((world_dir / "tasks" / "eight_point_viability_ic50.json").read_text(encoding="utf-8"))
    assert task["schema_version"] == "api_gym.research_world_task_design.v0"
    assert "dry-run transfer plan" in task["agent_task"]

    contract = (world_dir / "policies" / "environment-contract.md").read_text(encoding="utf-8")
    assert "hidden_expected_resolution" in contract
    assert "live_execution_allowed" in contract

    with pytest.raises(WorldBlueprintError) as exc_info:
        scaffold_research_world_from_blueprint(BLUEPRINT, out_root=tmp_path)
    assert exc_info.value.code == "world_scaffold_already_exists"
    assert exc_info.value.details["collisions"]


def test_world_blueprint_cli_validate_and_scaffold(tmp_path: Path) -> None:
    runner = CliRunner()

    validated = runner.invoke(app, ["world-blueprint", "validate", str(BLUEPRINT)])
    assert validated.exit_code == 0, validated.output
    validate_payload = json.loads(validated.output)
    assert validate_payload["ok"] is True
    assert validate_payload["scenario_count"] == 1

    scaffolded = runner.invoke(
        app,
        [
            "world-blueprint",
            "scaffold",
            str(BLUEPRINT),
            "--out-root",
            str(tmp_path),
        ],
    )
    assert scaffolded.exit_code == 0, scaffolded.output
    scaffold_payload = json.loads(scaffolded.output)
    assert scaffold_payload["ok"] is True
    assert scaffold_payload["registered"] is False
    assert (tmp_path / "worlds" / "dose_response_assay_env_v0" / "README.md").exists()


def test_world_blueprint_validation_returns_structured_errors(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        json.dumps(
            {
                "schema_version": "api_gym.research_world_blueprint.v0",
                "id": "bad",
                "world": "bad",
            }
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["world-blueprint", "validate", str(invalid)])

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_research_world_blueprint"
    assert payload["error"]["details"]["errors"]
