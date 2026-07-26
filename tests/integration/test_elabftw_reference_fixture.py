from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.providers.elabftw.reference_fixture import (
    DISPOSABLE_MARKER,
    FixtureCredentials,
    FixtureError,
    REFERENCE_BODY,
    REFERENCE_METADATA,
    REFERENCE_TITLE,
    _verify_inspected_web_container,
    exercise_fixture,
    require_loopback_base_url,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_FILE = (
    REPO_ROOT
    / "source_packs"
    / "apis"
    / "elabftw"
    / "2026-07-26"
    / "raw"
    / "reference_sequences"
    / "experiments_create_patch_get_v0.json"
)
PINNED_WEB_DIGEST = (
    "sha256:a4dd2264b6fa40bb250ca68d3845afa442bb15c29aed95cd444786084eb30e67"
)


def test_reference_fixture_refuses_non_loopback_urls() -> None:
    with pytest.raises(FixtureError, match="non-loopback"):
        require_loopback_base_url("http://elab.example.org")


def test_reference_fixture_accepts_loopback_http_urls() -> None:
    assert require_loopback_base_url("http://127.0.0.1:3148/") == "http://127.0.0.1:3148"
    assert require_loopback_base_url("http://localhost:3148") == "http://localhost:3148"


def test_compose_environment_does_not_inherit_arbitrary_credentials() -> None:
    credentials = FixtureCredentials(
        database_password="fixture-db",
        root_password="fixture-root",
        secret_key="fixture-secret",
        api_key="fixture-api",
    )
    source_environment = {
        "PATH": "/usr/bin",
        "HOME": "/tmp/home",
        "TMPDIR": "/tmp",
        "DOCKER_CONTEXT": "colima",
        "HTTPS_PROXY": "http://proxy.example.invalid",
        "NO_PROXY": "127.0.0.1,localhost",
        "PROVIDER_API_KEY": "must-not-propagate",
        "AWS_SECRET_ACCESS_KEY": "must-not-propagate",
    }

    environment = credentials.compose_environment(
        3148,
        source_environment=source_environment,
    )

    assert environment == {
        "PATH": "/usr/bin",
        "HOME": "/tmp/home",
        "TMPDIR": "/tmp",
        "DOCKER_CONTEXT": "colima",
        "HTTPS_PROXY": "http://proxy.example.invalid",
        "NO_PROXY": "127.0.0.1,localhost",
        "ELABFTW_FIXTURE_DB_PASSWORD": "fixture-db",
        "ELABFTW_FIXTURE_ROOT_PASSWORD": "fixture-root",
        "ELABFTW_FIXTURE_SECRET_KEY": "fixture-secret",
        "ELABFTW_FIXTURE_PORT": "3148",
    }


def test_disposable_fixture_rejects_wrong_running_image_digest() -> None:
    container, image = _fake_inspection()
    image["RepoDigests"] = ["elabftw/elabimg@sha256:not-the-pinned-content"]

    with pytest.raises(FixtureError, match="image content digest"):
        _verify_inspected_web_container(
            container,
            image,
            project="datalox-elabftw-test",
            port=3148,
            expected_digest=PINNED_WEB_DIGEST,
        )


def test_disposable_fixture_accepts_matching_running_image_digest() -> None:
    container, image = _fake_inspection()

    _verify_inspected_web_container(
        container,
        image,
        project="datalox-elabftw-test",
        port=3148,
        expected_digest=PINNED_WEB_DIGEST,
    )


def _fake_inspection() -> tuple[dict[str, object], dict[str, object]]:
    image_id = "sha256:local-image-content-id"
    container = {
        "Image": image_id,
        "Config": {
            "Image": f"elabftw/elabimg:5.6.10@{PINNED_WEB_DIGEST}",
            "Labels": {
                "org.datalox.fixture.disposable": DISPOSABLE_MARKER,
                "com.docker.compose.project": "datalox-elabftw-test",
            },
        },
        "NetworkSettings": {
            "Ports": {
                "443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3148"}],
            }
        },
    }
    image = {
        "Id": image_id,
        "RepoDigests": [f"elabftw/elabimg@{PINNED_WEB_DIGEST}"],
    }
    return container, image


def test_checked_in_reference_sequence_is_sanitized_grounded_evidence() -> None:
    capture = json.loads(CAPTURE_FILE.read_text(encoding="utf-8"))

    assert capture["schema_version"] == "api_gym.provider_reference_sequence.v0"
    assert capture["provider"]["version"] == "5.6.10"
    assert capture["provider"]["image"]["digest"] == PINNED_WEB_DIGEST
    assert [step["operation"] for step in capture["steps"]] == [
        "POST /api/v2/experiments",
        "PATCH /api/v2/experiments/{experiment_id}",
        "GET /api/v2/experiments/{experiment_id}",
    ]
    assert [step["response"]["status"] for step in capture["steps"]] == [201, 200, 200]
    assert capture["steps"][0]["response"]["headers"]["location"] == (
        "/api/v2/experiments/{experiment_id}"
    )
    assert json.loads(capture["steps"][1]["request"]["body"]["metadata"]) == REFERENCE_METADATA
    assert capture["observations"]["pre"]["accessible_experiment_count"] == 0
    assert capture["observations"]["post"]["experiment_count_delta"] == 1
    assert capture["observations"]["post"]["experiment"]["metadata"] == REFERENCE_METADATA

    serialized = CAPTURE_FILE.read_text(encoding="utf-8")
    forbidden = (
        "Authorization",
        "Set-Cookie",
        "/Users/",
        "127.0.0.1",
        "localhost",
        "datalox-fixture@example.invalid",
        "datalox-bootstrap@example.invalid",
    )
    assert not any(value in serialized for value in forbidden)


@pytest.mark.skipif(
    os.getenv("ELABFTW_REFERENCE_TEST") != "1",
    reason="set ELABFTW_REFERENCE_TEST=1 to provision the real disposable eLabFTW fixture",
)
def test_real_elabftw_create_patch_get_sequence(tmp_path: Path) -> None:
    output_path = tmp_path / "reference-sequence.json"

    capture = exercise_fixture(output_path)

    assert capture["provider"]["id"] == "elabftw"
    assert capture["provider"]["version"] == "5.6.10"
    assert capture["fixture"] == {
        "disposable_marker": DISPOSABLE_MARKER,
        "loopback_only": True,
        "volumes_destroyed_after_capture": True,
    }
    assert [step["operation"] for step in capture["steps"]] == [
        "POST /api/v2/experiments",
        "PATCH /api/v2/experiments/{experiment_id}",
        "GET /api/v2/experiments/{experiment_id}",
    ]
    assert [step["response"]["status"] for step in capture["steps"]] == [201, 200, 200]
    assert capture["steps"][0]["response"]["headers"]["location"] == (
        "/api/v2/experiments/{experiment_id}"
    )
    assert capture["observations"]["pre"] == {
        "accessible_experiment_count": 0,
        "reference_title_present": False,
    }
    assert capture["observations"]["post"]["experiment_count_delta"] == 1
    assert capture["observations"]["post"]["experiment"] == {
        "id": "{experiment_id}",
        "title": REFERENCE_TITLE,
        "body": REFERENCE_BODY,
        "metadata": REFERENCE_METADATA,
    }
    assert json.loads(output_path.read_text(encoding="utf-8")) == capture

    serialized = output_path.read_text(encoding="utf-8")
    forbidden = (
        "Authorization",
        "Set-Cookie",
        "/Users/",
        "127.0.0.1",
        "localhost",
        "datalox-fixture@example.invalid",
    )
    assert not any(value in serialized for value in forbidden)
