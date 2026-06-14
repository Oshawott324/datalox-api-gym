from __future__ import annotations

import json

from typer.testing import CliRunner

from api_gym.cli import app
from api_gym.source_pack_gate import build_gate_response


def test_source_pack_respond_cli_returns_success_response() -> None:
    result = CliRunner().invoke(
        app,
        [
            "source-pack",
            "respond",
            "--provider",
            "stripe",
            "--method",
            "POST",
            "--path",
            "/v1/refunds",
            "--case",
            "success",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["provider"] == "stripe"
    assert payload["operation"]["id"] == "operation:createRefund"
    assert payload["response_case"]["id"] == "response_case:createRefund:success"
    assert payload["response"] == build_gate_response(payload["response_case"])


def test_source_pack_respond_cli_exits_2_for_unsupported_path() -> None:
    result = CliRunner().invoke(
        app,
        [
            "source-pack",
            "respond",
            "--provider",
            "stripe",
            "--method",
            "POST",
            "--path",
            "/v1/not-a-real-operation",
            "--case",
            "success",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "source_pack_gate_operation_not_found"
    assert payload["error"]["message"] == "No source-pack operation matches the provider, method, and path."
    assert payload["error"]["details"]["provider"] == "stripe"
    assert payload["error"]["details"]["method"] == "POST"
    assert payload["error"]["details"]["path"] == "/v1/not-a-real-operation"


def test_gate_serve_cli_is_exposed_in_help_without_starting_server() -> None:
    result = CliRunner().invoke(app, ["gate", "serve", "--help"])

    assert result.exit_code == 0, result.output
    assert "--provider" in result.output
    assert "--version" in result.output
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--case" in result.output
    assert "--trace" in result.output
