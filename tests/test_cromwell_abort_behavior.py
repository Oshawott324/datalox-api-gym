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

from api_gym.provider_components.cromwell.abort_behavior import (
    ABORT_BOUNDARY,
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
    OWNERSHIP_MARKER,
    POLL_MAX_ATTEMPTS,
    PORT,
    RECIPE_PATH,
    SUBJECT_ID,
    UNKNOWN_WORKFLOW_ID,
    WDL_PATH,
    CromwellAbortBehaviorTarget,
    CromwellAbortTargetError,
    build_connector,
    build_fixture_receipt,
    build_recipe,
    case_load_arguments,
    load_checked_case,
    sha256_bytes,
)
from api_gym.provider_components.cromwell.failure_behavior import (
    DISPOSABLE_ROOT as FAILURE_DISPOSABLE_ROOT,
)
from api_gym.provider_components.cromwell.failure_behavior import (
    ORIGIN as FAILURE_ORIGIN,
)
from api_gym.provider_components.cromwell.success_behavior import (
    DISPOSABLE_ROOT as SUCCESS_DISPOSABLE_ROOT,
)
from api_gym.provider_components.cromwell.success_behavior import (
    ORIGIN as SUCCESS_ORIGIN,
)
from scripts.providers.cromwell import capture_abort_behavior as capture_wrapper
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
BEHAVIOR_CASES_ROOT = (
    Path(__file__).resolve().parents[1]
    / "source_packs"
    / "apis"
    / "cromwell"
    / "2026-07-30"
    / "behavior_cases"
)
ACCEPTED_CASE_BASELINES = {
    "workflow_success_v1": {
        "README.md": "3c7262efd8cf9881603fa0cf3e22a7653ab7d1a9ade60a12484fc5d1a61a9f5a",
        "capture.json": "13b94e8644fadd859202af40cf1f48930de75d24e1576517c6d2122b638014ec",
        "case_metadata.json": (
            "ab397709ddf745da35e2ad6853268305b8e36d627ff04de85c5dda1f326d76e7"
        ),
        "connector.json": "3838aef63df6fc33c92b2470440c7621a95b01f33758131f0cd10dba5cb36cca",
        "fixture_receipt.json": (
            "794b39c0e4dd82760397e586779529af7b2f07248c0a57c0cea56b536c928b5b"
        ),
        "recipe.json": "38c30c0dc479954814ba0665fd715610127786895b75a01b3d61491d758de9a8",
        "success.inputs.json": (
            "a57de4ed9167b07d59f574cbd8be218ecbbcc6d7d4d1d2e3fa8ef0c30dfa4b4a"
        ),
        "success.wdl": "6e6d652e3ba12cd5be4f76733733bc7b3408879d2d0beaf24a405575e1013078",
    },
    "workflow_failure_v1": {
        "README.md": "e27bdfb9c985ca49dcf31f8e035c44bb8c78da5b16b516af930039198f0b525d",
        "capture.json": "b726575994bf7b16a53ff39bf0bf1ea48a5c7138ea2c1fa1142d902b71282298",
        "case_metadata.json": (
            "29f0f35e54ee7f08cad59587f76e3eaf3579eeb24d27685e87717092f3f00ea9"
        ),
        "connector.json": "b57c888f22b40df132fa823a415eb97c10bc467e46bc18e0a4c4c7d4778918a8",
        "failure.inputs.json": (
            "ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356"
        ),
        "failure.wdl": "feaf458caad5621f5ce2ccd5b950d842033d86fc09078adfec7e084922b73f54",
        "fixture_receipt.json": (
            "2667f5fe9d83b545a8459ae6a263fe474c4895f1aadb18b1f42adce04261a05c"
        ),
        "recipe.json": "c09a55c7a927fbe9d592b50ccbc8e0d1c8e968032d6be313e202b10c8aa48245",
    },
}


def _digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _by_step(capture: v3.BehaviorCapture) -> dict[str, list[v3.CapturedExchange]]:
    result: dict[str, list[v3.CapturedExchange]] = {}
    for exchange in capture.exchanges:
        result.setdefault(exchange.step_id, []).append(exchange)
    return result


def test_accepted_success_and_failure_case_bytes_remain_unchanged() -> None:
    for case_name, baseline in ACCEPTED_CASE_BASELINES.items():
        case_root = BEHAVIOR_CASES_ROOT / case_name
        assert {
            path.name: _digest(path).removeprefix("sha256:")
            for path in case_root.iterdir()
            if path.is_file()
        } == baseline


def test_abort_case_reloads_with_exact_engine_provider_and_fixture_pins() -> None:
    metadata = json.loads(CASE_METADATA_PATH.read_text(encoding="utf-8"))

    assert v3.current_engine_identity() == ENGINE_IDENTITY
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


def test_checked_connector_recipe_and_abort_artifact_bytes_match_code() -> None:
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
        b"task wait_long_enough_to_abort {\n"
        b"  command <<<\n"
        b"    printf '%s\\n' 'started'\n"
        b"    sleep 120\n"
        b"    printf '%s\\n' 'finished' > result.txt\n"
        b"  >>>\n"
        b"\n"
        b"  output {\n"
        b'    File result_file = "result.txt"\n'
        b"  }\n"
        b"}\n"
        b"\n"
        b"workflow abort_case {\n"
        b"  call wait_long_enough_to_abort\n"
        b"}\n"
    )
    assert INPUTS_PATH.read_bytes() == b"{}\n"
    assert _digest(WDL_PATH) == (
        "sha256:1f5b811ff2f381f464e42a47932bd845360548a9b4a9605890424081eb4dcc8f"
    )
    assert _digest(INPUTS_PATH) == (
        "sha256:ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356"
    )


def test_abort_program_roles_order_relations_and_poll_bounds() -> None:
    recipe = build_recipe()
    assert [step.step_id for step in recipe.steps] == [
        "submit_primary",
        "poll_primary_running",
        "abort_primary",
        "abort_primary_duplicate",
        "abort_unknown_workflow",
        "poll_primary_aborted",
        "primary_outputs",
        "primary_logs",
        "primary_metadata",
    ]
    assert [step.role for step in recipe.steps] == [
        "supporting",
        "before",
        "success",
        "duplicate",
        "native_failure",
        "supporting",
        "supporting",
        "supporting",
        "resulting_state",
    ]
    assert recipe.requirements.to_dict() == {
        "success": True,
        "duplicate": True,
        "native_failure": True,
        "resulting_state": True,
    }
    assert all(step.subject_id == SUBJECT_ID for step in recipe.steps)
    assert recipe.steps[2].request.method == "POST"
    assert recipe.steps[2].expected_outcome == "mutation_success"
    assert recipe.steps[3].expected_outcome == "observe"
    assert recipe.steps[4].expected_outcome == "native_failure"
    assert recipe.steps[-1].expected_outcome == "observe"

    running_poll = recipe.steps[1].poll
    aborted_poll = recipe.steps[5].poll
    assert running_poll is not None
    assert aborted_poll is not None
    assert running_poll.transient_http_statuses == (404,)
    assert running_poll.allowed_intermediate_values == ("Submitted",)
    assert running_poll.terminal_values == (
        "Running",
        "Aborting",
        "Succeeded",
        "Failed",
        "Aborted",
    )
    assert running_poll.accepted_terminal_values == ("Running",)
    assert aborted_poll.transient_http_statuses == ()
    assert aborted_poll.allowed_intermediate_values == ("Running", "Aborting")
    assert aborted_poll.terminal_values == (
        "Submitted",
        "Succeeded",
        "Failed",
        "Aborted",
    )
    assert aborted_poll.accepted_terminal_values == ("Aborted",)
    connector = build_connector(
        json.loads(FIXTURE_RECEIPT_PATH.read_text(encoding="utf-8"))
    )
    assert running_poll.max_attempts == aborted_poll.max_attempts == POLL_MAX_ATTEMPTS
    assert running_poll.max_attempts * 2 <= connector.bounds.max_polls

    duplicate_assertions = {
        item.assertion_id: item for item in recipe.steps[3].assertions
    }
    assert duplicate_assertions["duplicate_exact_request"].prior_step_id == (
        "abort_primary"
    )
    assert duplicate_assertions["duplicate_abort_aborting"].expected == "Aborting"
    relation = {
        item.assertion_id: item for item in recipe.steps[-1].assertions
    }["running_to_aborted_observed"]
    assert relation.kind == "state_observe_step"
    assert relation.pointer == "/status"
    assert relation.prior_step_id == "poll_primary_running"
    assert relation.prior_pointer == "/status"


def test_primary_uuid_occurrences_cover_every_exact_and_composed_response() -> None:
    binding = build_recipe().steps[0].bindings[0]
    assert {
        (item.step_id, item.pointer) for item in binding.response_occurrences
    } == {
        ("submit_primary", "/id"),
        ("poll_primary_running", "/id"),
        ("abort_primary", "/id"),
        ("abort_primary_duplicate", "/id"),
        ("poll_primary_aborted", "/id"),
        ("primary_outputs", "/id"),
        ("primary_logs", "/id"),
        ("primary_metadata", "/id"),
    }

    execution_prefix = f"{DISPOSABLE_ROOT}/executions/abort_case/"
    call_prefix = "/call-wait_long_enough_to_abort"
    assert {
        (item.step_id, item.pointer, item.prefix, item.suffix)
        for item in binding.composed_string_occurrences
    } == {
        (
            "primary_logs",
            "/calls/abort_case.wait_long_enough_to_abort/0/stdout",
            execution_prefix,
            f"{call_prefix}/execution/stdout",
        ),
        (
            "primary_logs",
            "/calls/abort_case.wait_long_enough_to_abort/0/stderr",
            execution_prefix,
            f"{call_prefix}/execution/stderr",
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
            "/calls/abort_case.wait_long_enough_to_abort/0/callRoot",
            execution_prefix,
            call_prefix,
        ),
        (
            "primary_metadata",
            "/calls/abort_case.wait_long_enough_to_abort/0/stdout",
            execution_prefix,
            f"{call_prefix}/execution/stdout",
        ),
        (
            "primary_metadata",
            "/calls/abort_case.wait_long_enough_to_abort/0/stderr",
            execution_prefix,
            f"{call_prefix}/execution/stderr",
        ),
    }


def test_capture_proves_exact_duplicate_abort_and_native_unknown_failure() -> None:
    capture = load_checked_case().value
    exchanges = _by_step(capture)
    submit = exchanges["submit_primary"][-1]
    abort = exchanges["abort_primary"][-1]
    duplicate = exchanges["abort_primary_duplicate"][-1]
    native_failure = exchanges["abort_unknown_workflow"][-1]
    workflow_id = capture.bindings["primary_workflow_id"]

    assert submit.status_code == 201
    assert submit.body == {"id": workflow_id, "status": "Submitted"}
    assert submit.request_receipt.body_bytes == 605
    assert submit.request_receipt.headers["content-type"] == (
        f"multipart/form-data; boundary={ABORT_BOUNDARY}"
    )

    assert abort.request_receipt == duplicate.request_receipt
    assert abort.request_receipt.body_bytes == duplicate.request_receipt.body_bytes == 0
    assert abort.status_code == duplicate.status_code == 200
    assert abort.body == duplicate.body == {
        "id": workflow_id,
        "status": "Aborting",
    }
    assert native_failure.status_code == 404
    assert native_failure.body == {
        "status": "error",
        "message": (
            f"Couldn't abort {UNKNOWN_WORKFLOW_ID} because no workflow with "
            "that ID is in progress"
        ),
    }


def test_capture_retains_physical_polls_and_exact_aborted_observations() -> None:
    capture = load_checked_case().value
    exchanges = _by_step(capture)
    running_polls = exchanges["poll_primary_running"]
    aborted_polls = exchanges["poll_primary_aborted"]

    for attempts in (running_polls, aborted_polls):
        assert [item.attempt_number for item in attempts] == list(
            range(1, len(attempts) + 1)
        )
        assert [item.monotonic_elapsed_ms for item in attempts] == sorted(
            item.monotonic_elapsed_ms for item in attempts
        )
    assert running_polls[-1].status_code == 200
    assert running_polls[-1].body["status"] == "Running"
    assert any(item.status_code == 404 for item in running_polls)
    running_states = {
        item.body.get("status")
        for item in running_polls
        if isinstance(item.body, Mapping) and item.status_code == 200
    }
    assert {"Submitted", "Running"} <= running_states

    assert all(item.status_code == 200 for item in aborted_polls)
    assert aborted_polls[-1].body["status"] == "Aborted"
    aborted_states = {
        item.body.get("status")
        for item in aborted_polls
        if isinstance(item.body, Mapping)
    }
    assert {"Running", "Aborting", "Aborted"} <= aborted_states

    metadata = json.loads(CASE_METADATA_PATH.read_text(encoding="utf-8"))
    assert metadata["coverage"]["running_poll_calls"] == len(running_polls)
    assert metadata["coverage"]["aborted_poll_calls"] == len(aborted_polls)
    assert metadata["coverage"]["program_http_calls"] == len(capture.exchanges)
    assert metadata["coverage"]["observed_relations"] == {
        "primary_metadata.running_to_aborted_observed": "changed"
    }
    assert dict(capture.observed_relations) == {
        "primary_metadata.running_to_aborted_observed": "changed"
    }


def test_capture_retains_empty_outputs_log_paths_and_aborted_metadata() -> None:
    capture = load_checked_case().value
    exchanges = _by_step(capture)
    workflow_id = capture.bindings["primary_workflow_id"]
    expected_prefix = f"{DISPOSABLE_ROOT}/executions/abort_case/{workflow_id}"
    call_prefix = f"{expected_prefix}/call-wait_long_enough_to_abort"
    outputs = exchanges["primary_outputs"][-1]
    logs = exchanges["primary_logs"][-1]
    metadata = exchanges["primary_metadata"][-1]

    assert outputs.status_code == 200
    assert outputs.body == {"id": workflow_id, "outputs": {}}
    assert logs.status_code == 200
    call_logs = logs.body["calls"]["abort_case.wait_long_enough_to_abort"][0]
    assert call_logs["stdout"] == f"{call_prefix}/execution/stdout"
    assert call_logs["stderr"] == f"{call_prefix}/execution/stderr"

    call_metadata = metadata.body["calls"][
        "abort_case.wait_long_enough_to_abort"
    ][0]
    assert metadata.status_code == 200
    assert metadata.body["id"] == workflow_id
    assert metadata.body["status"] == "Aborted"
    assert metadata.body["outputs"] == {}
    assert metadata.body["labels"]["cromwell-workflow-id"] == (
        f"cromwell-{workflow_id}"
    )
    assert metadata.body["workflowRoot"] == expected_prefix
    assert call_metadata["backend"] == "Local"
    assert call_metadata["executionStatus"] == "Aborted"
    assert call_metadata["callRoot"] == call_prefix
    assert call_metadata["stdout"] == f"{call_prefix}/execution/stdout"
    assert call_metadata["stderr"] == f"{call_prefix}/execution/stderr"


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
        capture_wrapper.capture_abort_behavior(
            jar_path=tmp_path / "explicit.jar",
            java_bin=tmp_path / "explicit-java",
            case_root=tmp_path,
        )

    assert (tmp_path / "capture.json.partial.jsonl").read_text() == (
        '{"state":"dispatched"}\n'
    )


def test_fixture_accepts_exact_abort_resources_marker_and_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not DISPOSABLE_ROOT.exists()
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
    with disposable_cromwell_fixture(
        jar_path=tmp_path / "cromwell.jar",
        java_bin=tmp_path / "java",
        root=DISPOSABLE_ROOT,
        port=PORT,
        ownership_marker=OWNERSHIP_MARKER,
        fixture_receipt=receipt,
    ) as fixture:
        assert inspect_fixture_receipt(fixture) == receipt

    assert captured == {
        "root": DISPOSABLE_ROOT,
        "port": PORT,
        "marker": OWNERSHIP_MARKER,
        "receipt": receipt,
    }
    assert not DISPOSABLE_ROOT.exists()


def test_abort_resources_are_distinct_and_artifacts_have_no_runtime_path_leaks() -> None:
    assert len(
        {DISPOSABLE_ROOT, SUCCESS_DISPOSABLE_ROOT, FAILURE_DISPOSABLE_ROOT}
    ) == 3
    assert len({ORIGIN, SUCCESS_ORIGIN, FAILURE_ORIGIN}) == 3
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


def test_checked_abort_capture_compiles_and_exact_projection_propagates_uuid() -> None:
    arguments = case_load_arguments()
    trace = v3.compile_reference_trace(**arguments)
    assert len(trace.steps) == len(build_recipe().steps)

    report = v3.run_compiled_behavior_trace(
        target=CromwellAbortBehaviorTarget(generated_primary_id=PRIMARY_ID),
        **arguments,
    )
    assert report.passed is True
    assert report.mismatches == ()
    assert report.target_id == "cromwell_abort_captured_program_projection_v1"


def test_abort_target_rejects_noncanonical_generated_uuid() -> None:
    with pytest.raises(CromwellAbortTargetError, match="canonical UUID"):
        CromwellAbortBehaviorTarget(
            generated_primary_id="AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
        )


def test_abort_capture_and_static_artifact_tampering_fail_closed(
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

    tampered_wdl = tmp_path / "abort.wdl"
    tampered_wdl.write_bytes(WDL_PATH.read_bytes() + b"\n")
    artifact_arguments = dict(arguments)
    artifact_arguments["static_artifact_paths"] = {
        **arguments["static_artifact_paths"],
        "workflow": tampered_wdl,
    }
    with pytest.raises(v3.BehaviorContractError) as artifact_error:
        v3.compile_reference_trace(**artifact_arguments)
    assert artifact_error.value.code == "static_artifact_digest_mismatch"


def test_abort_fixture_pin_constants_are_exact() -> None:
    assert CROMWELL_JAR_SIZE == 220_674_800
    assert CROMWELL_JAR_SHA256 == (
        "sha256:e0e3a050d4124e81369a79059e5774142b2f06bd89df4a0b035f559db85cedf5"
    )
    assert CROMWELL_RELEASE_COMMIT == "e94341fdb32f0526b4338f9e1206a84b936dfcac"
    assert str(DISPOSABLE_ROOT) == "/tmp/datalox-cromwell-92-workflow-abort-v1"
    assert ORIGIN == "http://127.0.0.1:59639"
    assert PORT == 59639
    assert OWNERSHIP_MARKER == b"datalox-cromwell-92-workflow-abort-v1\n"


def test_abort_port_is_not_currently_occupied() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        assert probe.connect_ex(("127.0.0.1", PORT)) != 0
