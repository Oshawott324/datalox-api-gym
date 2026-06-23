from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from api_gym.cli import app
from api_gym.worlds.billing_support_v0.sampler import sample_episode as sample_billing_episode
from api_gym.worlds.unitelabs_plate_qc_v0.sampler import sample_episode as sample_unitelabs_episode


def test_serve_cli_uses_generic_world_http_app(tmp_path: Path, monkeypatch) -> None:
    episode = sample_billing_episode(
        scenario="duplicate_payment_refund",
        seed=51,
        out_dir=tmp_path / "billing-run",
    )
    called: dict[str, object] = {}

    def fake_run(fastapi_app, *, host: str, port: int) -> None:
        called["title"] = fastapi_app.title
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)

    result = CliRunner().invoke(
        app,
        ["serve", "--run", str(episode.run_dir), "--host", "127.0.0.1", "--port", "9099"],
    )

    assert result.exit_code == 0, result.output
    assert called == {
        "title": "Datalox API Gym billing_support_v0",
        "host": "127.0.0.1",
        "port": 9099,
    }


def test_serve_cli_reports_world_without_http_surface(tmp_path: Path) -> None:
    episode = sample_unitelabs_episode(
        scenario="plate_transfer_qc",
        seed=52,
        out_dir=tmp_path / "unitelabs-run",
    )

    result = CliRunner().invoke(app, ["serve", "--run", str(episode.run_dir)])

    assert result.exit_code == 2
    payload = json.loads(result.stderr)
    assert payload == {
        "ok": False,
        "error": {
            "code": "invalid_run",
            "message": "World 'unitelabs_plate_qc_v0' does not expose an HTTP app.",
            "details": {"run": str(episode.run_dir)},
        },
    }
