from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from api_gym.cli import app

from api_gym.worlds.unitelabs_plate_qc_v0.api_contract_sampler import (
    UnitelabsApiContractSamplingError,
    sample_openapi_contract,
)


def test_unitelabs_openapi_contract_sampler_extracts_safe_grounding(tmp_path: Path) -> None:
    openapi_path = tmp_path / "unitelabs-openapi.json"
    openapi_path.write_text(json.dumps(_minimal_unitelabs_openapi()), encoding="utf-8")

    sample = sample_openapi_contract(openapi_file=openapi_path)

    assert sample["schema_version"] == "api_gym.unitelabs_api_contract_sample.v0"
    assert sample["source"]["kind"] == "openapi_file"
    assert sample["source"]["path"] == str(openapi_path)
    assert sample["source"]["title"] == "Unitelabs Tenant API"
    assert sample["source"]["version"] == "2026-06-11"
    assert sample["official_docs_urls"] == [
        "https://docs.unitelabs.io/technical-reference/rest-api/",
        "https://docs.unitelabs.io/automate/guides/deploy-a-workflow/",
        "https://docs.unitelabs.io/automate/guides/run-a-workflow/",
        "https://docs.unitelabs.io/automate/concepts/logs/",
    ]
    assert sample["live_execution"] == {
        "allowed": False,
        "reason": "Contract sampling only; no workflow, run, hardware, or tenant API action is executed.",
    }
    assert sample["agent_tool_mapping"]["status"] == "requires_human_mapping"
    assert sample["agent_tool_mapping"]["proven"] is False

    operation_ids = {operation["operation_id"] for operation in sample["operations"]}
    assert operation_ids == {
        "listWorkflows",
        "createWorkflowRun",
        "getWorkflowRun",
        "listRunLogs",
        "listRunArtifacts",
    }

    relevant = sample["relevant_operations"]
    assert [operation["operation_id"] for operation in relevant["workflow"]] == ["listWorkflows"]
    assert [operation["operation_id"] for operation in relevant["run"]] == ["createWorkflowRun", "getWorkflowRun"]
    assert [operation["operation_id"] for operation in relevant["log"]] == ["listRunLogs"]
    assert [operation["operation_id"] for operation in relevant["artifact"]] == ["listRunArtifacts"]


def test_unitelabs_contract_sampler_cli_writes_json_and_rejects_missing_source(tmp_path: Path) -> None:
    openapi_path = tmp_path / "unitelabs-openapi.json"
    out_path = tmp_path / "contract-sample.json"
    openapi_path.write_text(json.dumps(_minimal_unitelabs_openapi()), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "unitelabs",
            "sample-api-contract",
            "--openapi-file",
            str(openapi_path),
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["out"] == str(out_path)
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["schema_version"] == "api_gym.unitelabs_api_contract_sample.v0"
    assert written["live_execution"]["allowed"] is False

    missing_source = CliRunner().invoke(
        app,
        [
            "unitelabs",
            "sample-api-contract",
            "--out",
            str(tmp_path / "missing-source.json"),
        ],
    )

    assert missing_source.exit_code == 2
    error_payload = json.loads(missing_source.stderr)
    assert error_payload["error"]["code"] == "unitelabs_api_contract_source_required"
    assert "Supply --openapi-file or --openapi-url" in error_payload["error"]["message"]


def test_unitelabs_contract_sampler_cli_rejects_directory_source_without_traceback(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "unitelabs",
            "sample-api-contract",
            "--openapi-file",
            str(tmp_path),
            "--out",
            str(tmp_path / "contract-sample.json"),
        ],
    )

    assert result.exit_code == 2
    assert "Traceback" not in result.output
    assert "Traceback" not in result.stderr
    error_payload = json.loads(result.stderr)
    assert error_payload["error"]["code"] == "unitelabs_api_contract_file_not_file"
    assert error_payload["error"]["details"] == {"path": str(tmp_path)}


def test_unitelabs_contract_sampler_rejects_paths_without_openapi_or_swagger_version(tmp_path: Path) -> None:
    openapi_path = tmp_path / "not-openapi.json"
    openapi_path.write_text(json.dumps({"paths": {}}), encoding="utf-8")

    with pytest.raises(UnitelabsApiContractSamplingError) as error:
        sample_openapi_contract(openapi_file=openapi_path)

    assert error.value.code == "unitelabs_api_contract_not_openapi"
    assert error.value.details == {"path": str(openapi_path)}


def _minimal_unitelabs_openapi() -> dict[str, object]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Unitelabs Tenant API", "version": "2026-06-11"},
        "servers": [{"url": "https://tenant.unitelabs.example/api"}],
        "paths": {
            "/workflows": {
                "get": {
                    "operationId": "listWorkflows",
                    "summary": "List workflows",
                    "tags": ["Workflows"],
                },
            },
            "/workflows/{workflow_id}/runs": {
                "post": {
                    "operationId": "createWorkflowRun",
                    "summary": "Create a workflow run",
                    "tags": ["Runs"],
                },
            },
            "/runs/{run_id}": {
                "get": {
                    "operationId": "getWorkflowRun",
                    "summary": "Get a workflow run",
                    "tags": ["Runs"],
                },
            },
            "/runs/{run_id}/logs": {
                "get": {
                    "operationId": "listRunLogs",
                    "summary": "List run logs",
                    "tags": ["Logs"],
                },
            },
            "/runs/{run_id}/artifacts": {
                "get": {
                    "operationId": "listRunArtifacts",
                    "summary": "List run artifacts",
                    "tags": ["Artifacts"],
                },
            },
        },
    }
