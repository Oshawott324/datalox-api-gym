from __future__ import annotations

import json
import shutil
import socket
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest
from datalox_gated_runtime.behavior_harvest.engines import v3

from api_gym.provider_components.cromwell.failure_behavior import (
    CAPTURE_PATH,
    CASE_METADATA_PATH,
    CONNECTOR_PATH,
    CROMWELL_JAR_SHA256,
    CROMWELL_JAR_SIZE,
    CROMWELL_RELEASE_COMMIT,
    DISPOSABLE_ROOT,
    ENGINE_IDENTITY,
    FIXTURE_RECEIPT_PATH,
    INPUTS_PATH,
    ORIGIN,
    PORT,
    RECIPE_PATH,
    SUBJECT_ID,
    WDL_PATH,
    CromwellFailureBehaviorTarget,
    build_connector,
    build_fixture_receipt,
    build_recipe,
    case_load_arguments,
    load_checked_case,
    sha256_bytes,
)
from api_gym.provider_components.cromwell.success_behavior import (
    DISPOSABLE_ROOT as SUCCESS_DISPOSABLE_ROOT,
)
from api_gym.provider_components.cromwell.success_behavior import (
    ORIGIN as SUCCESS_ORIGIN,
)
from scripts.providers.cromwell import capture_failure_behavior as capture_wrapper
from scripts.providers.cromwell.reference_fixture import (
    disposable_cromwell_fixture,
    inspect_fixture_receipt,
)

STATIC_PATHS = (
    CONNECTOR_PATH,
    RECIPE_PATH,
    FIXTURE_RECEIPT_PATH,
    WDL_PATH,
    INPUTS_PATH,
    CAPTURE_PATH,
    CASE_METADATA_PATH,
)
PRIMARY_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DUPLICATE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SUCCESS_CASE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "source_packs"
    / "apis"
    / "cromwell"
    / "2026-07-30"
    / "behavior_cases"
    / "workflow_success_v1"
)
SUCCESS_BASELINE_SHA256 = {
    "connector.json": "3838aef63df6fc33c92b2470440c7621a95b01f33758131f0cd10dba5cb36cca",
    "recipe.json": "38c30c0dc479954814ba0665fd715610127786895b75a01b3d61491d758de9a8",
    "fixture_receipt.json": (
        "794b39c0e4dd82760397e586779529af7b2f07248c0a57c0cea56b536c928b5b"
    ),
    "success.wdl": "6e6d652e3ba12cd5be4f76733733bc7b3408879d2d0beaf24a405575e1013078",
    "success.inputs.json": (
        "a57de4ed9167b07d59f574cbd8be218ecbbcc6d7d4d1d2e3fa8ef0c30dfa4b4a"
    ),
    "capture.json": "13b94e8644fadd859202af40cf1f48930de75d24e1576517c6d2122b638014ec",
    "case_metadata.json": (
        "ab397709ddf745da35e2ad6853268305b8e36d627ff04de85c5dda1f326d76e7"
    ),
}


def _digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _by_step(capture: v3.BehaviorCapture) -> dict[str, list[v3.CapturedExchange]]:
    result: dict[str, list[v3.CapturedExchange]] = {}
    for exchange in capture.exchanges:
        result.setdefault(exchange.step_id, []).append(exchange)
    return result


def test_success_case_bytes_remain_at_committed_baseline() -> None:
    assert {
        path.name: _digest(path).removeprefix("sha256:")
        for path in SUCCESS_CASE_ROOT.iterdir()
        if path.name in SUCCESS_BASELINE_SHA256
    } == SUCCESS_BASELINE_SHA256


def test_failure_case_reloads_with_exact_engine_provider_and_fixture_pins() -> None:
    metadata = json.loads(CASE_METADATA_PATH.read_text(encoding="utf-8"))

    assert v3.current_engine_identity() == ENGINE_IDENTITY
    assert ENGINE_IDENTITY.to_dict() == {
        "engine_id": "behavior_harvest_http11",
        "engine_version": "3",
        "source_sha256": (
            "sha256:a8131506d96f018c0cd7a4268e0fefcab104d788e8c6c425f5d367aaaab328e1"
        ),
    }
    assert metadata["engine"] == ENGINE_IDENTITY.to_dict()
    assert metadata["digests"] == {
        "capture": _digest(CAPTURE_PATH),
        "connector": _digest(CONNECTOR_PATH),
        "fixture_receipt": _digest(FIXTURE_RECEIPT_PATH),
        "inputs": _digest(INPUTS_PATH),
        "recipe": _digest(RECIPE_PATH),
        "workflow": _digest(WDL_PATH),
    }

    loaded = load_checked_case().value
    connector = loaded.connector
    assert connector.provider_id == "cromwell"
    assert connector.provider_version == "92"
    assert connector.origin == ORIGIN
    assert connector.boundary.production_equivalence == "not_claimed"
    assert connector.isolation.reset_equivalence_claimed is False
    assert connector.driver_source_sha256 == ENGINE_IDENTITY.source_sha256

    pins = {pin.pin_id: pin for pin in connector.source_pins}
    assert pins["cromwell_92_release_jar"].sha256 == CROMWELL_JAR_SHA256
    assert pins["cromwell_92_release_jar"].version == "92"
    receipt = json.loads(FIXTURE_RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["jar"]["size_bytes"] == CROMWELL_JAR_SIZE
    assert receipt["jar"]["sha256"] == CROMWELL_JAR_SHA256
    assert receipt["release"]["tag_commit"] == CROMWELL_RELEASE_COMMIT
    assert receipt["java"]["required_major"] == 17
    assert receipt["origin"] == ORIGIN
    assert receipt["paths"]["disposable_root"] == str(DISPOSABLE_ROOT)


def test_checked_connector_recipe_and_failure_artifact_bytes_match_code() -> None:
    receipt = json.loads(FIXTURE_RECEIPT_PATH.read_text(encoding="utf-8"))
    connector = v3.load_connector(
        CONNECTOR_PATH,
        expected_sha256=_digest(CONNECTOR_PATH),
    ).value
    recipe = v3.load_recipe(RECIPE_PATH, expected_sha256=_digest(RECIPE_PATH)).value

    assert connector == build_connector(receipt)
    assert recipe == build_recipe()
    assert WDL_PATH.read_bytes() == (
        b"version 1.0\n"
        b"\n"
        b"task exit_nonzero {\n"
        b"  command <<<\n"
        b"    printf '%s\\n' 'intentional failure on stderr' >&2\n"
        b"    exit 23\n"
        b"  >>>\n"
        b"\n"
        b"  output {\n"
        b"    String unreachable = read_string(stdout())\n"
        b"  }\n"
        b"}\n"
        b"\n"
        b"workflow failure_case {\n"
        b"  call exit_nonzero\n"
        b"}\n"
    )
    assert INPUTS_PATH.read_bytes() == b"{}\n"
    assert _digest(WDL_PATH) == (
        "sha256:feaf458caad5621f5ce2ccd5b950d842033d86fc09078adfec7e084922b73f54"
    )
    assert _digest(INPUTS_PATH) == (
        "sha256:ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356"
    )


def test_failure_program_roles_order_relations_and_poll_bounds() -> None:
    recipe = build_recipe()
    assert [step.step_id for step in recipe.steps] == [
        "provider_status_before_submit",
        "submit_primary",
        "submit_duplicate",
        "poll_primary",
        "poll_duplicate",
        "primary_outputs",
        "primary_logs",
        "abort_terminal_failed_primary",
        "primary_metadata",
    ]
    assert [step.role for step in recipe.steps] == [
        "before",
        "success",
        "duplicate",
        "supporting",
        "supporting",
        "supporting",
        "supporting",
        "native_failure",
        "resulting_state",
    ]
    assert all(step.subject_id == SUBJECT_ID for step in recipe.steps)
    assert recipe.steps[0].request.method == "GET"
    assert recipe.steps[0].request.path == "/engine/v1/status"
    assert recipe.steps[2].expected_outcome == "observe"
    assert recipe.steps[7].request.method == "POST"
    assert recipe.steps[7].expected_outcome == "native_failure"
    assert recipe.steps[-1].expected_outcome == "observe"

    primary_poll = recipe.steps[3].poll
    duplicate_poll = recipe.steps[4].poll
    assert primary_poll is not None
    assert duplicate_poll is not None
    assert primary_poll == duplicate_poll
    assert primary_poll.transient_http_statuses == (404,)
    assert primary_poll.allowed_intermediate_values == ("Submitted", "Running")
    assert primary_poll.terminal_values == ("Succeeded", "Failed", "Aborted")
    assert primary_poll.accepted_terminal_values == ("Failed",)
    assert primary_poll.max_attempts * 2 <= build_connector(
        json.loads(FIXTURE_RECEIPT_PATH.read_text())
    ).bounds.max_polls

    assertions = {
        item.assertion_id: item for item in recipe.steps[-1].assertions
    }
    assert assertions["metadata_failed"].expected == "Failed"
    assert assertions["metadata_backend_local"].expected == "Local"
    assert assertions["metadata_execution_failed"].expected == "Failed"
    assert assertions["metadata_return_code"].expected == 23
    assert assertions["metadata_not_retryable"].expected is False
    relation = assertions["submitted_to_failed_observed"]
    assert relation.kind == "state_observe_step"
    assert relation.pointer == "/status"
    assert relation.prior_step_id == "submit_primary"
    assert relation.prior_pointer == "/status"


def test_uuid_occurrences_cover_all_terminal_failure_responses() -> None:
    recipe = build_recipe()
    primary = recipe.steps[1].bindings[0]
    duplicate = recipe.steps[2].bindings[0]

    assert {
        (item.step_id, item.pointer) for item in primary.response_occurrences
    } == {
        ("submit_primary", "/id"),
        ("poll_primary", "/id"),
        ("primary_outputs", "/id"),
        ("primary_logs", "/id"),
        ("primary_metadata", "/id"),
    }
    assert {
        (item.step_id, item.pointer) for item in duplicate.response_occurrences
    } == {
        ("submit_duplicate", "/id"),
        ("poll_duplicate", "/id"),
    }

    execution_prefix = f"{DISPOSABLE_ROOT}/executions/failure_case/"
    assert {
        (item.step_id, item.pointer, item.prefix, item.suffix)
        for item in primary.composed_string_occurrences
    } == {
        (
            "primary_logs",
            "/calls/failure_case.exit_nonzero/0/stdout",
            execution_prefix,
            "/call-exit_nonzero/execution/stdout",
        ),
        (
            "primary_logs",
            "/calls/failure_case.exit_nonzero/0/stderr",
            execution_prefix,
            "/call-exit_nonzero/execution/stderr",
        ),
        (
            "abort_terminal_failed_primary",
            "/message",
            "Couldn't abort ",
            " because no workflow with that ID is in progress",
        ),
        (
            "primary_metadata",
            "/labels/cromwell-workflow-id",
            "cromwell-",
            "",
        ),
        (
            "primary_metadata",
            "/workflowRoot",
            execution_prefix,
            "",
        ),
        (
            "primary_metadata",
            "/calls/failure_case.exit_nonzero/0/callRoot",
            execution_prefix,
            "/call-exit_nonzero",
        ),
        (
            "primary_metadata",
            "/calls/failure_case.exit_nonzero/0/stdout",
            execution_prefix,
            "/call-exit_nonzero/execution/stdout",
        ),
        (
            "primary_metadata",
            "/calls/failure_case.exit_nonzero/0/stderr",
            execution_prefix,
            "/call-exit_nonzero/execution/stderr",
        ),
    }


def test_capture_proves_valid_non_idempotent_failure_submissions_and_terminal_404() -> None:
    capture = load_checked_case().value
    exchanges = _by_step(capture)
    primary = exchanges["submit_primary"][-1]
    duplicate = exchanges["submit_duplicate"][-1]
    native_failure = exchanges["abort_terminal_failed_primary"][-1]

    assert primary.status_code == duplicate.status_code == 201
    assert primary.request_receipt == duplicate.request_receipt
    assert primary.request_receipt.body_bytes == 584
    assert primary.request_receipt.headers["content-type"] == (
        "multipart/form-data; boundary=DataloxCromwellFailureBoundary"
    )
    assert capture.bindings["primary_workflow_id"] != capture.bindings[
        "duplicate_workflow_id"
    ]
    assert primary.body["status"] == duplicate.body["status"] == "Submitted"

    primary_id = capture.bindings["primary_workflow_id"]
    assert native_failure.status_code == 404
    assert native_failure.body == {
        "status": "error",
        "message": (
            f"Couldn't abort {primary_id} because no workflow with that ID is in progress"
        ),
    }


def test_capture_retains_polls_empty_outputs_logs_and_failed_metadata() -> None:
    capture = load_checked_case().value
    exchanges = _by_step(capture)
    primary_polls = exchanges["poll_primary"]
    duplicate_polls = exchanges["poll_duplicate"]

    for attempts in (primary_polls, duplicate_polls):
        assert [item.attempt_number for item in attempts] == list(
            range(1, len(attempts) + 1)
        )
        assert [item.monotonic_elapsed_ms for item in attempts] == sorted(
            item.monotonic_elapsed_ms for item in attempts
        )
        assert attempts[-1].status_code == 200
        assert attempts[-1].body["status"] == "Failed"
    assert any(item.status_code == 404 for item in primary_polls)
    observed_states = {
        item.body.get("status")
        for item in (*primary_polls, *duplicate_polls)
        if isinstance(item.body, Mapping)
    }
    assert {"Submitted", "Running", "Failed"} <= observed_states

    workflow_id = capture.bindings["primary_workflow_id"]
    expected_prefix = f"{DISPOSABLE_ROOT}/executions/failure_case/{workflow_id}"
    outputs = exchanges["primary_outputs"][-1]
    logs = exchanges["primary_logs"][-1]
    metadata = exchanges["primary_metadata"][-1]

    assert outputs.status_code == 200
    assert outputs.body == {"id": workflow_id, "outputs": {}}
    assert logs.status_code == 200
    call_logs = logs.body["calls"]["failure_case.exit_nonzero"][0]
    assert call_logs["stdout"] == f"{expected_prefix}/call-exit_nonzero/execution/stdout"
    assert call_logs["stderr"] == f"{expected_prefix}/call-exit_nonzero/execution/stderr"

    call_metadata = metadata.body["calls"]["failure_case.exit_nonzero"][0]
    assert metadata.status_code == 200
    assert metadata.body["status"] == "Failed"
    assert metadata.body["outputs"] == {}
    assert call_metadata["backend"] == "Local"
    assert call_metadata["executionStatus"] == "Failed"
    assert call_metadata["returnCode"] == 23
    assert call_metadata["retryableFailure"] is False
    assert dict(capture.observed_relations) == {
        "primary_metadata.submitted_to_failed_observed": "changed"
    }
    case_metadata = json.loads(CASE_METADATA_PATH.read_text(encoding="utf-8"))
    assert case_metadata["coverage"]["primary_poll_calls"] == len(primary_polls)
    assert case_metadata["coverage"]["duplicate_poll_calls"] == len(duplicate_polls)
    assert case_metadata["coverage"]["program_http_calls"] == len(capture.exchanges)
    assert case_metadata["coverage"]["observed_relations"] == {
        "primary_metadata.submitted_to_failed_observed": "changed"
    }


def test_capture_wrapper_retains_partial_journal_after_uncertain_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def fake_fixture(**_: Any) -> Iterator[object]:
        yield object()

    class FailingHarvester:
        def run(self, **kwargs: Any) -> None:
            output_path = kwargs["output_path"]
            partial_path = output_path.with_name(f"{output_path.name}.partial.jsonl")
            partial_path.write_text('{"state":"dispatched"}\n', encoding="utf-8")
            raise RuntimeError("uncertain provider interaction")

    monkeypatch.setattr(capture_wrapper, "disposable_cromwell_fixture", fake_fixture)
    monkeypatch.setattr(
        capture_wrapper,
        "inspect_fixture_receipt",
        lambda fixture: build_fixture_receipt(),
    )
    monkeypatch.setattr(capture_wrapper.v3, "BehaviorHarvester", FailingHarvester)

    with pytest.raises(RuntimeError, match="uncertain provider interaction"):
        capture_wrapper.capture_failure_behavior(
            jar_path=tmp_path / "explicit.jar",
            java_bin=tmp_path / "explicit-java",
            case_root=tmp_path,
        )

    assert (tmp_path / "capture.json.partial.jsonl").read_text() == (
        '{"state":"dispatched"}\n'
    )


def test_fixture_accepts_distinct_failure_resources_and_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure_root = DISPOSABLE_ROOT
    assert not failure_root.exists()
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "scripts.providers.cromwell.reference_fixture.validate_cromwell_jar",
        lambda path: None,
    )
    monkeypatch.setattr(
        "scripts.providers.cromwell.reference_fixture.validate_java_17",
        lambda path: None,
    )
    monkeypatch.setattr(
        "scripts.providers.cromwell.reference_fixture._wait_for_exact_readiness",
        lambda fixture: None,
    )
    monkeypatch.setattr(
        "scripts.providers.cromwell.reference_fixture._assert_exact_readiness",
        lambda port: None,
    )

    def fake_destroy(fixture: Any) -> None:
        captured.update(
            root=fixture.root,
            port=fixture.port,
            marker=fixture.ownership_marker,
            receipt=fixture.fixture_receipt,
        )
        fixture.stdout_handle.close()
        fixture.stderr_handle.close()
        shutil.rmtree(fixture.root)

    monkeypatch.setattr(
        "scripts.providers.cromwell.reference_fixture.destroy_fixture",
        fake_destroy,
    )

    class FakeProcess:
        pid = 123

        def poll(self) -> None:
            return None

    class FakePopen:
        def __new__(cls, *args: Any, **kwargs: Any) -> FakeProcess:
            return FakeProcess()

    monkeypatch.setattr(
        "scripts.providers.cromwell.reference_fixture.subprocess.Popen",
        FakePopen,
    )

    receipt = build_fixture_receipt()
    marker = b"datalox-cromwell-92-workflow-failure-v1\n"
    with disposable_cromwell_fixture(
        jar_path=tmp_path / "cromwell.jar",
        java_bin=tmp_path / "java",
        root=failure_root,
        port=PORT,
        ownership_marker=marker,
        fixture_receipt=receipt,
    ) as fixture:
        assert inspect_fixture_receipt(fixture) == receipt

    assert captured == {
        "root": failure_root,
        "port": PORT,
        "marker": marker,
        "receipt": receipt,
    }
    assert not failure_root.exists()


def test_failure_resources_are_distinct_and_capture_has_no_probe_runtime_paths() -> None:
    assert DISPOSABLE_ROOT != SUCCESS_DISPOSABLE_ROOT
    assert ORIGIN != SUCCESS_ORIGIN
    combined = b"\n".join(path.read_bytes() for path in STATIC_PATHS)
    forbidden = (
        b"/Users/",
        b"/tmp/datalox-cromwell-probe",
        b"java17-brew",
        b"state.sqlite",
    )
    assert all(value not in combined for value in forbidden)
    assert b"CROMWELL_92_JAR" not in combined
    assert b"CROMWELL_JAVA_BIN" not in combined
    assert not any(
        path.suffix in {".jar", ".db", ".log"}
        for path in CAPTURE_PATH.parent.rglob("*")
        if path.is_file()
    )


def test_checked_failure_capture_compiles_and_exact_projection_conforms() -> None:
    arguments = case_load_arguments()
    trace = v3.compile_reference_trace(**arguments)
    assert len(trace.steps) == len(build_recipe().steps)

    report = v3.run_compiled_behavior_trace(
        target=CromwellFailureBehaviorTarget(
            generated_primary_id=PRIMARY_ID,
            generated_duplicate_id=DUPLICATE_ID,
        ),
        **arguments,
    )
    assert report.passed is True
    assert report.mismatches == ()
    assert report.target_id == "cromwell_failure_captured_program_projection_v1"


def test_failure_capture_and_static_artifact_tampering_fail_closed(
    tmp_path: Path,
) -> None:
    arguments = case_load_arguments()
    raw_capture = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    raw_capture["exchanges"][-1]["response"]["body"]["status"] = "Succeeded"
    tampered_capture = tmp_path / "capture.json"
    tampered_capture.write_text(json.dumps(raw_capture), encoding="utf-8")

    capture_arguments = dict(arguments)
    capture_arguments["capture_path"] = tampered_capture
    with pytest.raises(v3.BehaviorContractError, match="SHA-256"):
        v3.compile_reference_trace(**capture_arguments)

    tampered_wdl = tmp_path / "failure.wdl"
    tampered_wdl.write_bytes(WDL_PATH.read_bytes() + b"\n")
    artifact_arguments = dict(arguments)
    artifact_arguments["static_artifact_paths"] = {
        **arguments["static_artifact_paths"],
        "workflow": tampered_wdl,
    }
    with pytest.raises(v3.BehaviorContractError) as artifact_error:
        v3.compile_reference_trace(**artifact_arguments)
    assert artifact_error.value.code == "static_artifact_digest_mismatch"


def test_failure_fixture_pin_constants_are_exact() -> None:
    assert CROMWELL_JAR_SIZE == 220_674_800
    assert CROMWELL_JAR_SHA256 == (
        "sha256:e0e3a050d4124e81369a79059e5774142b2f06bd89df4a0b035f559db85cedf5"
    )
    assert CROMWELL_RELEASE_COMMIT == "e94341fdb32f0526b4338f9e1206a84b936dfcac"
    assert str(DISPOSABLE_ROOT) == "/tmp/datalox-cromwell-92-workflow-failure-v1"
    assert ORIGIN == f"http://127.0.0.1:{PORT}"
    assert PORT != int(SUCCESS_ORIGIN.rsplit(":", 1)[1])


def test_failure_port_is_not_currently_occupied() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        assert probe.connect_ex(("127.0.0.1", PORT)) != 0
