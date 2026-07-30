from __future__ import annotations

import hashlib
import json
import socket
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest
from datalox_gated_runtime.behavior_harvest.engines import v3

from api_gym.provider_components.cromwell.success_behavior import (
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
    RECIPE_PATH,
    SUBJECT_ID,
    WDL_PATH,
    CromwellSuccessBehaviorTarget,
    build_connector,
    build_fixture_receipt,
    build_recipe,
    case_load_arguments,
    load_checked_case,
    sha256_bytes,
)
from scripts.providers.cromwell import capture_complete_behavior as capture_wrapper
from scripts.providers.cromwell.reference_fixture import (
    FixtureError,
    assert_fixture_available,
    validate_cromwell_jar,
    validate_java_17,
)

VALIDATION_SECRET_VALUES: dict[str, bytes] = {}
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


def _digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _by_step(capture: v3.BehaviorCapture) -> dict[str, list[v3.CapturedExchange]]:
    result: dict[str, list[v3.CapturedExchange]] = {}
    for exchange in capture.exchanges:
        result.setdefault(exchange.step_id, []).append(exchange)
    return result


def test_case_reloads_with_exact_engine_provider_and_artifact_pins() -> None:
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
    assert connector.boundary.kind == "self_hosted_reference"
    assert connector.boundary.production_equivalence == "not_claimed"
    assert connector.isolation.reset_equivalence_claimed is False
    assert connector.driver_id == ENGINE_IDENTITY.engine_id
    assert connector.driver_version == ENGINE_IDENTITY.engine_version
    assert connector.driver_source_sha256 == ENGINE_IDENTITY.source_sha256

    pins = {pin.pin_id: pin for pin in connector.source_pins}
    assert pins["cromwell_92_release_jar"].sha256 == CROMWELL_JAR_SHA256
    assert pins["cromwell_92_release_jar"].version == "92"
    receipt = json.loads(FIXTURE_RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["jar"]["size_bytes"] == CROMWELL_JAR_SIZE
    assert receipt["jar"]["sha256"] == CROMWELL_JAR_SHA256
    assert receipt["release"]["tag_commit"] == CROMWELL_RELEASE_COMMIT
    assert receipt["java"]["required_major"] == 17


def test_checked_connector_recipe_and_static_bytes_match_construction_code() -> None:
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
        b"task write_message {\n"
        b"  input {\n"
        b"    String message\n"
        b"  }\n"
        b"\n"
        b"  command <<<\n"
        b"    printf '%s\\n' '~{message}' > result.txt\n"
        b"  >>>\n"
        b"\n"
        b"  output {\n"
        b'    File result_file = "result.txt"\n'
        b'    String echoed = read_string("result.txt")\n'
        b"  }\n"
        b"}\n"
        b"\n"
        b"workflow success_case {\n"
        b"  input {\n"
        b"    String message\n"
        b"  }\n"
        b"\n"
        b"  call write_message {\n"
        b"    input:\n"
        b"      message = message\n"
        b"  }\n"
        b"\n"
        b"  output {\n"
        b"    File result_file = write_message.result_file\n"
        b"    String echoed = write_message.echoed\n"
        b"  }\n"
        b"}\n"
    )
    assert INPUTS_PATH.read_bytes() == (
        b'{"success_case.message":"hello from cromwell 92"}\n'
    )
    assert _digest(WDL_PATH) == (
        "sha256:6e6d652e3ba12cd5be4f76733733bc7b3408879d2d0beaf24a405575e1013078"
    )
    assert _digest(INPUTS_PATH) == (
        "sha256:a57de4ed9167b07d59f574cbd8be218ecbbcc6d7d4d1d2e3fa8ef0c30dfa4b4a"
    )


def test_complete_program_roles_order_relations_and_poll_bounds() -> None:
    recipe = build_recipe()
    assert [step.step_id for step in recipe.steps] == [
        "provider_status_before_submit",
        "submit_primary",
        "submit_duplicate",
        "missing_source_submission",
        "poll_primary",
        "poll_duplicate",
        "primary_outputs",
        "primary_logs",
        "primary_metadata",
    ]
    assert [step.role for step in recipe.steps] == [
        "before",
        "success",
        "duplicate",
        "native_failure",
        "supporting",
        "supporting",
        "supporting",
        "supporting",
        "resulting_state",
    ]
    assert all(step.subject_id == SUBJECT_ID for step in recipe.steps)
    assert recipe.steps[0].request.method == "GET"
    assert recipe.steps[0].request.path == "/engine/v1/status"
    assert recipe.steps[2].expected_outcome == "observe"
    assert recipe.steps[-1].step_id == "primary_metadata"
    assert recipe.steps[-1].expected_outcome == "observe"

    primary_poll = recipe.steps[4].poll
    duplicate_poll = recipe.steps[5].poll
    assert primary_poll is not None
    assert duplicate_poll is not None
    assert primary_poll == duplicate_poll
    assert primary_poll.transient_http_statuses == (404,)
    assert primary_poll.allowed_intermediate_values == ("Submitted", "Running")
    assert primary_poll.accepted_terminal_values == ("Succeeded",)
    assert primary_poll.max_attempts * 2 <= build_connector(
        json.loads(FIXTURE_RECEIPT_PATH.read_text())
    ).bounds.max_polls

    metadata_assertions = {item.assertion_id: item for item in recipe.steps[-1].assertions}
    submit_assertions = {item.assertion_id: item for item in recipe.steps[1].assertions}
    assert "metadata_status" not in metadata_assertions
    assert metadata_assertions["metadata_succeeded"].expected == "Succeeded"
    assert submit_assertions["primary_submitted"].expected == "Submitted"
    relation = metadata_assertions["submitted_to_succeeded_observed"]
    assert relation.kind == "state_observe_step"
    assert relation.pointer == "/status"
    assert relation.prior_step_id == "submit_primary"
    assert relation.prior_pointer == "/status"


def test_uuid_occurrences_are_exact_and_cover_terminal_path_fields() -> None:
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

    assert {
        (item.step_id, item.pointer, item.prefix, item.suffix)
        for item in primary.composed_string_occurrences
    } == {
        (
            "primary_outputs",
            "/outputs/success_case.result_file",
            f"{DISPOSABLE_ROOT}/executions/success_case/",
            "/call-write_message/execution/result.txt",
        ),
        (
            "primary_logs",
            "/calls/success_case.write_message/0/stdout",
            f"{DISPOSABLE_ROOT}/executions/success_case/",
            "/call-write_message/execution/stdout",
        ),
        (
            "primary_logs",
            "/calls/success_case.write_message/0/stderr",
            f"{DISPOSABLE_ROOT}/executions/success_case/",
            "/call-write_message/execution/stderr",
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
            f"{DISPOSABLE_ROOT}/executions/success_case/",
            "",
        ),
        (
            "primary_metadata",
            "/calls/success_case.write_message/0/callRoot",
            f"{DISPOSABLE_ROOT}/executions/success_case/",
            "/call-write_message",
        ),
        (
            "primary_metadata",
            "/calls/success_case.write_message/0/stdout",
            f"{DISPOSABLE_ROOT}/executions/success_case/",
            "/call-write_message/execution/stdout",
        ),
        (
            "primary_metadata",
            "/calls/success_case.write_message/0/stderr",
            f"{DISPOSABLE_ROOT}/executions/success_case/",
            "/call-write_message/execution/stderr",
        ),
        (
            "primary_metadata",
            "/calls/success_case.write_message/0/outputs/result_file",
            f"{DISPOSABLE_ROOT}/executions/success_case/",
            "/call-write_message/execution/result.txt",
        ),
        (
            "primary_metadata",
            "/outputs/success_case.result_file",
            f"{DISPOSABLE_ROOT}/executions/success_case/",
            "/call-write_message/execution/result.txt",
        ),
    }


def test_capture_proves_multipart_non_idempotency_and_native_400() -> None:
    capture = load_checked_case().value
    exchanges = _by_step(capture)
    primary = exchanges["submit_primary"][-1]
    duplicate = exchanges["submit_duplicate"][-1]
    failure = exchanges["missing_source_submission"][-1]

    assert primary.status_code == 201
    assert duplicate.status_code == 201
    assert primary.request_receipt == duplicate.request_receipt
    assert primary.request_receipt.body_bytes > 0
    assert primary.request_receipt.headers["content-type"] == (
        "multipart/form-data; boundary=DataloxCromwellSuccessBoundary"
    )
    assert capture.bindings["primary_workflow_id"] != capture.bindings[
        "duplicate_workflow_id"
    ]
    assert primary.body["status"] == duplicate.body["status"] == "Submitted"

    assert failure.request_receipt.body_bytes > 0
    assert failure.request_receipt.body_sha256 != primary.request_receipt.body_sha256
    assert b'name="workflowInputs"' in failure.request_receipt.raw_body
    assert b"name=\"workflowSource\"" not in failure.request_receipt.raw_body
    assert failure.status_code == 400
    assert failure.body == {
        "status": "fail",
        "message": "Error(s): workflowSource or workflowUrl needs to be supplied",
    }


def test_capture_retains_physical_polls_and_terminal_outputs_logs_metadata() -> None:
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
        assert attempts[-1].body["status"] == "Succeeded"
    assert any(item.status_code == 404 for item in (*primary_polls, *duplicate_polls))
    observed_states = {
        item.body.get("status")
        for item in (*primary_polls, *duplicate_polls)
        if isinstance(item.body, Mapping)
    }
    assert {"Submitted", "Running", "Succeeded"} <= observed_states

    workflow_id = capture.bindings["primary_workflow_id"]
    outputs = exchanges["primary_outputs"][-1]
    logs = exchanges["primary_logs"][-1]
    metadata = exchanges["primary_metadata"][-1]
    expected_prefix = f"{DISPOSABLE_ROOT}/executions/success_case/{workflow_id}"

    assert outputs.status_code == 200
    assert outputs.body["outputs"]["success_case.echoed"] == "hello from cromwell 92"
    assert outputs.body["outputs"]["success_case.result_file"] == (
        f"{expected_prefix}/call-write_message/execution/result.txt"
    )
    assert logs.status_code == 200
    call_logs = logs.body["calls"]["success_case.write_message"][0]
    assert call_logs["stdout"] == (
        f"{expected_prefix}/call-write_message/execution/stdout"
    )
    assert call_logs["stderr"] == (
        f"{expected_prefix}/call-write_message/execution/stderr"
    )

    call_metadata = metadata.body["calls"]["success_case.write_message"][0]
    assert metadata.status_code == 200
    assert metadata.body["status"] == "Succeeded"
    assert metadata.body["outputs"]["success_case.echoed"] == "hello from cromwell 92"
    assert call_metadata["backend"] == "Local"
    assert call_metadata["executionStatus"] == "Done"
    assert call_metadata["returnCode"] == 0
    assert dict(capture.observed_relations) == {
        "primary_metadata.submitted_to_succeeded_observed": "changed"
    }
    case_metadata = json.loads(CASE_METADATA_PATH.read_text(encoding="utf-8"))
    assert case_metadata["coverage"]["observed_relations"] == {
        "primary_metadata.submitted_to_succeeded_observed": "changed"
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

    monkeypatch.setattr(
        capture_wrapper,
        "disposable_cromwell_fixture",
        fake_fixture,
    )
    monkeypatch.setattr(
        capture_wrapper,
        "inspect_fixture_receipt",
        lambda fixture: build_fixture_receipt(),
    )
    monkeypatch.setattr(
        capture_wrapper.v3,
        "BehaviorHarvester",
        FailingHarvester,
    )

    with pytest.raises(RuntimeError, match="uncertain provider interaction"):
        capture_wrapper.capture_complete_behavior(
            jar_path=tmp_path / "explicit.jar",
            java_bin=tmp_path / "explicit-java",
            case_root=tmp_path,
        )

    assert (tmp_path / "capture.json.partial.jsonl").read_text() == (
        '{"state":"dispatched"}\n'
    )


def test_capture_contains_no_local_runtime_paths_or_uncommitted_runtime_state() -> None:
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


def test_checked_capture_compiles_and_exact_projection_conforms() -> None:
    arguments = case_load_arguments()
    trace = v3.compile_reference_trace(**arguments)
    assert len(trace.steps) == len(build_recipe().steps)

    report = v3.run_compiled_behavior_trace(
        target=CromwellSuccessBehaviorTarget(
            generated_primary_id=PRIMARY_ID,
            generated_duplicate_id=DUPLICATE_ID,
        ),
        **arguments,
    )
    assert report.passed is True
    assert report.mismatches == ()
    assert report.target_id == "cromwell_success_captured_program_projection_v1"


def test_capture_and_static_artifact_tampering_fail_closed(tmp_path: Path) -> None:
    arguments = case_load_arguments()
    raw_capture = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    raw_capture["exchanges"][-1]["response"]["body"]["status"] = "Failed"
    tampered_capture = tmp_path / "capture.json"
    tampered_capture.write_text(json.dumps(raw_capture), encoding="utf-8")

    capture_arguments = dict(arguments)
    capture_arguments["capture_path"] = tampered_capture
    with pytest.raises(v3.BehaviorContractError, match="SHA-256"):
        v3.compile_reference_trace(**capture_arguments)

    tampered_wdl = tmp_path / "success.wdl"
    tampered_wdl.write_bytes(WDL_PATH.read_bytes() + b"\n")
    artifact_arguments = dict(arguments)
    artifact_arguments["static_artifact_paths"] = {
        **arguments["static_artifact_paths"],
        "workflow": tampered_wdl,
    }
    with pytest.raises(v3.BehaviorContractError) as artifact_error:
        v3.compile_reference_trace(**artifact_arguments)
    assert artifact_error.value.code == "static_artifact_digest_mismatch"


def test_fixture_validation_refuses_bad_inputs_and_occupied_resources(
    tmp_path: Path,
) -> None:
    bad_jar = tmp_path / "cromwell.jar"
    bad_jar.write_bytes(b"not cromwell")
    with pytest.raises(FixtureError, match="size"):
        validate_cromwell_jar(bad_jar)

    fake_java = tmp_path / "java"
    fake_java.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'openjdk version \"21.0.1\"' >&2\n",
        encoding="ascii",
    )
    fake_java.chmod(0o700)
    with pytest.raises(FixtureError, match="major 17"):
        validate_java_17(fake_java)

    occupied_root = tmp_path / "owned-by-someone-else"
    occupied_root.mkdir()
    with pytest.raises(FixtureError, match="already exists"):
        assert_fixture_available(root=occupied_root, port=0)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(FixtureError, match="port"):
            assert_fixture_available(root=tmp_path / "available-root", port=port)


def test_fixture_pin_constants_are_not_derived_from_local_paths() -> None:
    assert CROMWELL_JAR_SIZE == 220_674_800
    assert CROMWELL_JAR_SHA256 == (
        "sha256:e0e3a050d4124e81369a79059e5774142b2f06bd89df4a0b035f559db85cedf5"
    )
    assert CROMWELL_RELEASE_COMMIT == "e94341fdb32f0526b4338f9e1206a84b936dfcac"
    assert str(DISPOSABLE_ROOT) == "/tmp/datalox-cromwell-92-workflow-success-v1"
    assert ORIGIN == "http://127.0.0.1:59637"
    assert hashlib.sha256(WDL_PATH.read_bytes()).hexdigest() in _digest(WDL_PATH)
