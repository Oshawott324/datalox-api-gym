from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

import pytest
from datalox_gated_runtime.behavior_harvest.engines import v2

from api_gym.provider_components.elabftw.complete_behavior import (
    AUTH_SECRET_NAME,
    CONNECTOR_PATH,
    ENGINE_IDENTITY,
    FIXTURE_RECEIPT_PATH,
    RECIPE_PATH,
    ELabFTWCompleteBehaviorTarget,
)
from scripts.providers.elabftw.capture_complete_behavior import (
    capture_complete_behavior,
)
from scripts.providers.elabftw.reference_fixture import FixtureCredentials


@pytest.mark.skipif(
    os.getenv("ELABFTW_COMPLETE_BEHAVIOR_LIVE") != "1",
    reason="set ELABFTW_COMPLETE_BEHAVIOR_LIVE=1 for a fresh disposable capture",
)
def test_fresh_complete_behavior_capture_uses_generic_harvester(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = FixtureCredentials.generate()
    monkeypatch.setattr(
        FixtureCredentials,
        "generate",
        classmethod(lambda cls: credentials),
    )

    metadata = capture_complete_behavior(case_root=tmp_path)
    capture_path = tmp_path / "capture.json"
    connector_path = tmp_path / "connector.json"
    recipe_path = tmp_path / "recipe.json"
    receipt_path = tmp_path / "fixture_receipt.json"

    assert connector_path.read_bytes() == CONNECTOR_PATH.read_bytes()
    assert recipe_path.read_bytes() == RECIPE_PATH.read_bytes()
    assert receipt_path.read_bytes() == FIXTURE_RECEIPT_PATH.read_bytes()
    assert metadata["engine"] == ENGINE_IDENTITY.to_dict()

    secret = credentials.api_key.encode("utf-8")
    artifact_bytes = b"\n".join(path.read_bytes() for path in tmp_path.iterdir())
    assert secret not in artifact_bytes
    assert base64.b64encode(secret) not in artifact_bytes
    assert hashlib.sha256(secret).hexdigest().encode("ascii") not in artifact_bytes

    arguments = {
        "capture_path": capture_path,
        "expected_capture_sha256": metadata["digests"]["capture"],
        "connector_path": connector_path,
        "expected_connector_sha256": metadata["digests"]["connector"],
        "recipe_path": recipe_path,
        "expected_recipe_sha256": metadata["digests"]["recipe"],
        "expected_engine": ENGINE_IDENTITY,
        "sensitive_values": {AUTH_SECRET_NAME: secret},
        "static_input_paths": {"fixture_inspection": receipt_path},
        "expected_static_input_sha256": {
            "fixture_inspection": metadata["digests"]["fixture_receipt"]
        },
    }
    load_arguments = dict(arguments)
    loaded = v2.load_capture(
        path=load_arguments.pop("capture_path"),
        expected_sha256=load_arguments.pop("expected_capture_sha256"),
        **load_arguments,
    ).value
    assert [exchange.status_code for exchange in loaded.exchanges] == [
        201,
        200,
        200,
        200,
        200,
        400,
        200,
    ]
    report = v2.run_compiled_behavior_trace(
        target=ELabFTWCompleteBehaviorTarget(capture_path=capture_path),
        **arguments,
    )
    assert report.passed is True
    assert report.mismatches == ()

    assert not list(tmp_path.glob("*.partial.jsonl"))
    assert json.loads((tmp_path / "case_metadata.json").read_text()) == metadata
