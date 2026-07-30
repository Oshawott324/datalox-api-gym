from __future__ import annotations

import hashlib
import json
import os
import socket
from pathlib import Path

import pytest
from datalox_gated_runtime.behavior_harvest.engines import v3

from api_gym.provider_components.cromwell.abort_behavior import (
    CAPTURE_PATH,
    CONNECTOR_PATH,
    DISPOSABLE_ROOT,
    ENGINE_IDENTITY,
    FIXTURE_RECEIPT_PATH,
    INPUTS_PATH,
    ORIGIN,
    RECIPE_PATH,
    WDL_PATH,
    CromwellAbortBehaviorTarget,
)
from scripts.providers.cromwell.capture_abort_behavior import (
    capture_abort_behavior,
    fresh_case_load_arguments,
)


@pytest.mark.skipif(
    os.getenv("CROMWELL_ABORT_BEHAVIOR_LIVE") != "1",
    reason=(
        "set CROMWELL_ABORT_BEHAVIOR_LIVE=1 with explicit CROMWELL_92_JAR "
        "and CROMWELL_JAVA_BIN for a fresh disposable abort capture"
    ),
)
def test_fresh_abort_behavior_capture_uses_generic_v3_and_cleans_up(
    tmp_path: Path,
) -> None:
    jar_value = os.environ.get("CROMWELL_92_JAR")
    java_value = os.environ.get("CROMWELL_JAVA_BIN")
    assert jar_value, "CROMWELL_92_JAR must be explicit when live capture is enabled"
    assert java_value, "CROMWELL_JAVA_BIN must be explicit when live capture is enabled"

    metadata = capture_abort_behavior(
        case_root=tmp_path,
        jar_path=Path(jar_value),
        java_bin=Path(java_value),
    )
    assert metadata["engine"] == ENGINE_IDENTITY.to_dict()

    deterministic_files = {
        "connector.json": CONNECTOR_PATH,
        "recipe.json": RECIPE_PATH,
        "fixture_receipt.json": FIXTURE_RECEIPT_PATH,
        "abort.wdl": WDL_PATH,
        "abort.inputs.json": INPUTS_PATH,
    }
    for filename, checked_path in deterministic_files.items():
        assert (tmp_path / filename).read_bytes() == checked_path.read_bytes()
        digest_key = {
            "abort.wdl": "workflow",
            "abort.inputs.json": "inputs",
        }.get(filename, filename.removesuffix(".json"))
        assert metadata["digests"][digest_key] == (
            "sha256:"
            + hashlib.sha256((tmp_path / filename).read_bytes()).hexdigest()
        )

    arguments = fresh_case_load_arguments(tmp_path, metadata)
    load_arguments = dict(arguments)
    loaded = v3.load_capture(
        path=load_arguments.pop("capture_path"),
        expected_sha256=load_arguments.pop("expected_capture_sha256"),
        **load_arguments,
    ).value
    assert loaded.engine == ENGINE_IDENTITY
    assert len(loaded.preflight_exchanges) == 2
    assert len(loaded.exchanges) == metadata["coverage"]["program_http_calls"]

    grouped: dict[str, list[v3.CapturedExchange]] = {}
    for exchange in loaded.exchanges:
        grouped.setdefault(exchange.step_id, []).append(exchange)
    abort = grouped["abort_primary"][-1]
    duplicate = grouped["abort_primary_duplicate"][-1]
    workflow_id = loaded.bindings["primary_workflow_id"]
    assert abort.request_receipt == duplicate.request_receipt
    assert abort.status_code == duplicate.status_code == 200
    assert abort.body == duplicate.body == {
        "id": workflow_id,
        "status": "Aborting",
    }
    assert grouped["abort_unknown_workflow"][-1].status_code == 404
    assert grouped["poll_primary_running"][-1].body["status"] == "Running"
    assert grouped["poll_primary_aborted"][-1].body["status"] == "Aborted"

    report = v3.run_compiled_behavior_trace(
        target=CromwellAbortBehaviorTarget(
            capture_path=tmp_path / "capture.json"
        ),
        **arguments,
    )
    assert report.passed is True
    assert report.mismatches == ()

    assert not DISPOSABLE_ROOT.exists()
    port = int(ORIGIN.rsplit(":", 1)[1])
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0
    assert not list(tmp_path.glob("*.partial.jsonl"))
    assert json.loads((tmp_path / "case_metadata.json").read_text()) == metadata
    assert CAPTURE_PATH.name == "capture.json"
