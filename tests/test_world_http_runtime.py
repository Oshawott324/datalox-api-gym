from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gym.server.app import create_app
from api_gym.worlds.billing_support_v0.sampler import sample_episode as sample_billing_episode
from api_gym.worlds.registry import get_world_runtime
from api_gym.worlds.unitelabs_plate_qc_v0.sampler import sample_episode as sample_unitelabs_episode


def test_billing_runtime_exposes_http_app_factory() -> None:
    runtime = get_world_runtime("billing_support_v0")

    assert runtime.create_http_app is not None
    assert runtime.http_surface == "available"


def test_unitelabs_runtime_has_no_http_app_factory() -> None:
    runtime = get_world_runtime("unitelabs_plate_qc_v0")

    assert runtime.create_http_app is None
    assert runtime.http_surface == "not_available"


def test_create_app_dispatches_to_registered_world_http(tmp_path: Path) -> None:
    episode = sample_billing_episode(
        scenario="duplicate_payment_refund",
        seed=41,
        out_dir=tmp_path / "billing-run",
    )

    app = create_app(episode.run_dir)

    assert isinstance(app, FastAPI)
    assert app.title == "Datalox API Gym billing_support_v0"
    response = TestClient(app).get("/support/tickets/not-real")
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "ticket_not_found"


def test_create_app_fails_clearly_for_world_without_http(tmp_path: Path) -> None:
    episode = sample_unitelabs_episode(
        scenario="plate_transfer_qc",
        seed=42,
        out_dir=tmp_path / "unitelabs-run",
    )

    with pytest.raises(ValueError) as exc_info:
        create_app(episode.run_dir)

    assert str(exc_info.value) == "World 'unitelabs_plate_qc_v0' does not expose an HTTP app."
