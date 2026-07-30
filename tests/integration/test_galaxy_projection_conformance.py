from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("datalox_gated_runtime.reference")

from datalox_gated_runtime.reference import (  # noqa: E402
    ConformanceReport,
    ObservedResponse,
    run_conformance,
)

from api_gym.provider_components.galaxy.capture_contract import (  # noqa: E402
    DEFAULT_CAPTURE_PATH,
    FASTA_TEXT,
    INPUT_SHA256,
    REPRESENTATIVE_EXCHANGES,
    CaptureContractError,
    load_capture_contract,
)
from api_gym.provider_components.galaxy.projection import (  # noqa: E402
    GalaxyConnectedFastaProjection,
    ProjectionError,
)
from api_gym.provider_components.galaxy.reference_conformance import (  # noqa: E402
    DEFAULT_REPORT_PATH,
    GalaxyProjectionTarget,
    GalaxyReferenceProfile,
    load_reference_trace,
    run_projection_conformance,
)

READ_HEADERS = {"accept": "application/json"}
WRITE_HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
}
UPLOAD_INPUTS = {
    "ajax_upload": "true",
    "dbkey": "?",
    "file_type": "fasta",
    "files_0|NAME": "input.fa",
    "files_0|type": "upload_dataset",
    "files_0|url_paste": FASTA_TEXT,
}


def test_capture_contract_validates_pinned_provider_evidence(tmp_path: Path) -> None:
    capture = load_capture_contract()

    assert capture.capture_digest == (
        "sha256:bca9a588f319b3572369b9093b312cc1d0889983bab281cb78280afa2ae5cb37"
    )
    assert capture.input_bytes == FASTA_TEXT.encode("ascii")
    assert capture.raw["provider_version"] == "26.1.rc1"
    assert capture.raw["provider_execution"]["status"] == "observed"
    assert capture.raw["minimal_sequence"]["completed"] is True
    assert capture.raw["staramr_execution"]["import_attempted"] is False
    assert capture.raw["staramr_execution"]["invocation_attempted"] is False

    tampered = json.loads(DEFAULT_CAPTURE_PATH.read_text(encoding="utf-8"))
    tampered["provider_version"] = "26.2"
    tampered_path = tmp_path / "tampered-capture.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    tampered_digest = _sha256(tampered_path.read_bytes())

    with pytest.raises(CaptureContractError) as error:
        load_capture_contract(
            tampered_path,
            expected_capture_sha256=tampered_digest,
        )
    assert error.value.code == "GALAXY_CAPTURE_PROVIDER_MISMATCH"


def test_reference_trace_compiles_exact_representative_exchanges() -> None:
    trace = load_reference_trace()

    assert [step.step_id for step in trace.steps] == list(REPRESENTATIVE_EXCHANGES)
    assert len(trace.evidence_refs) == 13
    assert trace.evidence_refs[4].endswith("capture.json#/exchanges/7")
    assert trace.evidence_refs[5].endswith("capture.json#/exchanges/10")
    assert trace.evidence_refs[6].endswith("capture.json#/exchanges/91")
    assert trace.metadata["representative_state_progression"] == (
        {
            "reference_step_id": "dataset_queued",
            "capture_step_id": "poll_dataset_01",
            "exchange_index": 7,
            "state": "queued",
            "response_body_sha256": (
                "sha256:92ed4c71072e62492b9a2498b3c876e2695118ae7e1d7d8a5ea3b77f61ec6d23"
            ),
        },
        {
            "reference_step_id": "dataset_running",
            "capture_step_id": "poll_dataset_04",
            "exchange_index": 10,
            "state": "running",
            "response_body_sha256": (
                "sha256:a940c650f4ef0fdc9f5737101715d127f54aeb3892f6668ebe4ef147811718ac"
            ),
        },
        {
            "reference_step_id": "dataset_ok",
            "capture_step_id": "poll_dataset_85",
            "exchange_index": 91,
            "state": "ok",
            "response_body_sha256": (
                "sha256:20641c3666ea409e90d886bec0cb8ac2aebe85af8ea5bb9e7b050c60c8734be8"
            ),
        },
    )
    assert trace.metadata["poll_timing"] == {
        "classification": "ungrounded_timing",
        "captured_poll_count": 85,
        "captured_total_duration_ms": 52596.99,
        "provider_semantics_claimed": False,
        "projection_rule": "ordered queued -> running -> ok only",
    }
    assert trace.metadata["substantive_fields_normalized"] is False


def test_grounded_capture_conforms_to_projection() -> None:
    capture = load_capture_contract()
    trace = load_reference_trace()
    replay = _replay_trace(GalaxyProjectionTarget(), trace, seed=trace.seed)
    responses = dict(
        zip(
            (step.step_id for step in trace.steps),
            replay["responses"],
            strict=True,
        )
    )
    projected_ids = {
        "user_id": responses["create_history"]["body"]["user_id"],
        "history_id": responses["create_history"]["body"]["id"],
        "dataset_id": responses["upload_fasta"]["body"]["outputs"][0]["id"],
        "job_id": responses["upload_fasta"]["body"]["jobs"][0]["id"],
    }
    report = run_projection_conformance()

    assert len(set(capture.captured_entity_ids.values())) == 1
    assert len(set(projected_ids.values())) == len(projected_ids)
    assert responses["create_history"]["body"]["contents_url"] == (
        f"/api/histories/{projected_ids['history_id']}/contents"
    )
    assert responses["upload_fasta"]["body"]["jobs"][0]["history_id"] == (
        projected_ids["history_id"]
    )
    assert responses["dataset_queued"]["body"]["creating_job"] == (
        projected_ids["job_id"]
    )
    assert responses["dataset_queued"]["body"]["download_url"] == (
        f"/api/histories/{projected_ids['history_id']}"
        f"/contents/{projected_ids['dataset_id']}/display"
    )
    assert responses["read_provenance"]["body"]["id"] == projected_ids["dataset_id"]
    assert responses["read_provenance"]["body"]["job_id"] == projected_ids["job_id"]
    assert report.passed is True
    assert report.provider_id == "galaxy"
    assert report.provider_version == "26.1.rc1"
    assert report.target_id == "galaxy_connected_history_fasta_projection_v1"
    assert report.profile_id == "galaxy_generated_fields_v1"


def test_projection_reset_is_deterministic_for_complete_reference_trace() -> None:
    trace = load_reference_trace()
    target = GalaxyProjectionTarget()

    first = _replay_trace(target, trace, seed=41)
    second = _replay_trace(target, trace, seed=41)
    third = _replay_trace(target, trace, seed=42)

    assert first == second
    assert first["responses"][2]["body"]["id"] != third["responses"][2]["body"]["id"]
    assert first["states"] == ["queued", "running", "ok", "ok"]
    assert first["final_snapshot"]["phase"] == "complete"
    assert first["final_snapshot"]["purged"] is True


def test_exact_fasta_display_and_upload_provenance() -> None:
    trace = load_reference_trace()
    target = GalaxyProjectionTarget()
    target.reset(trace.seed)
    profile = GalaxyReferenceProfile()
    normalized_pairs: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    actual_by_step: dict[str, ObservedResponse] = {}

    for step in trace.steps:
        actual = target.execute(step.call)
        actual_by_step[step.step_id] = actual
        normalized_pairs[step.step_id] = (
            profile.normalize_response(
                step=step, response=step.expected_response
            ).to_dict(),
            profile.normalize_response(step=step, response=actual).to_dict(),
        )
        for observation in step.post_observations:
            target.observe(observation.request)

    display = actual_by_step["readback_dataset"]
    assert display.body == FASTA_TEXT
    assert _sha256(display.body.encode("ascii")) == INPUT_SHA256
    assert display.headers["content-type"] == "application/octet-stream"

    expected_provenance, actual_provenance = normalized_pairs["read_provenance"]
    expected_upload, actual_upload = normalized_pairs["upload_fasta"]
    expected_queued, actual_queued = normalized_pairs["dataset_queued"]
    assert actual_upload == expected_upload
    assert actual_upload["body"]["jobs"][0]["history_id"] == "{history_id}"
    assert actual_upload["body"]["jobs"][0]["id"] == "{job_id}"
    assert actual_upload["body"]["outputs"][0]["history_id"] == "{history_id}"
    assert actual_upload["body"]["outputs"][0]["id"] == "{dataset_id}"
    assert actual_queued == expected_queued
    assert actual_queued["body"]["download_url"] == (
        "/api/histories/{history_id}/contents/{dataset_id}/display"
    )
    assert actual_provenance == expected_provenance
    assert actual_provenance["body"]["id"] == "{dataset_id}"
    assert actual_provenance["body"]["job_id"] == "{job_id}"
    assert actual_provenance["body"]["tool_id"] == "upload1"
    assert actual_provenance["body"]["stderr"] == ""
    assert actual_provenance["body"]["stdout"] == ""
    assert (
        json.loads(actual_provenance["body"]["parameters"]["files"])[0]["url_paste"]
        == "{internal_url_paste_path}"
    )
    assert json.loads(actual_provenance["body"]["parameters"]["paramfile"]) == (
        "{internal_upload_paramfile_path}"
    )


@pytest.mark.parametrize(
    ("method", "path", "query", "body", "expected_code"),
    [
        (
            "GET",
            "/api/tools",
            {"q": "staramr", "in_panel": "false"},
            None,
            "GALAXY_UNSUPPORTED_STARAMR",
        ),
        (
            "POST",
            "/api/tools",
            {},
            {"tool_id": "toolshed.g2.bx.psu.edu/repos/iuc/staramr/staramr_search"},
            "GALAXY_UNSUPPORTED_STARAMR",
        ),
        (
            "GET",
            (
                "/api/tools/toolshed.g2.bx.psu.edu%2Frepos%2Fiuc%2F"
                "amrfinderplus%2Famrfinderplus%2F3.12.8%2Bgalaxy0"
            ),
            {},
            None,
            "GALAXY_UNSUPPORTED_STARAMR",
        ),
        (
            "POST",
            "/api/workflows",
            {},
            {"archive_source": "unsupported"},
            "GALAXY_UNSUPPORTED_WORKFLOW_IMPORT",
        ),
        (
            "POST",
            "/api/workflows/workflow-id/invocations",
            {},
            {"history_id": "history-id"},
            "GALAXY_UNSUPPORTED_WORKFLOW_INVOCATION",
        ),
    ],
)
def test_staramr_and_workflow_operations_fail_closed_atomically(
    method: str,
    path: str,
    query: dict[str, Any],
    body: Any,
    expected_code: str,
) -> None:
    projection = GalaxyConnectedFastaProjection(seed=7)
    before = projection.state_snapshot()

    with pytest.raises(ProjectionError) as error:
        projection.request(method, path, query=query, body=body)

    assert error.value.code == expected_code
    assert projection.state_snapshot() == before


def test_wrong_sequence_owner_history_dataset_and_input_are_atomic() -> None:
    projection = GalaxyConnectedFastaProjection(seed=7)
    before = projection.state_snapshot()
    with pytest.raises(ProjectionError) as sequence_error:
        projection.request(
            "GET",
            "/api/histories",
            headers=READ_HEADERS,
            actor_id=projection.actor_id,
        )
    assert sequence_error.value.code == "GALAXY_SEQUENCE_VIOLATION"
    assert projection.state_snapshot() == before

    _get_version(projection)
    before = projection.state_snapshot()
    with pytest.raises(ProjectionError) as owner_error:
        projection.request(
            "GET",
            "/api/histories",
            headers=READ_HEADERS,
            actor_id="not-the-owner",
        )
    assert owner_error.value.code == "GALAXY_OWNERSHIP_VIOLATION"
    assert projection.state_snapshot() == before

    _list_histories(projection)
    _create_history(projection)
    before = projection.state_snapshot()
    wrong_history_body = _upload_body("wrong-history")
    with pytest.raises(ProjectionError) as history_error:
        projection.request(
            "POST",
            "/api/tools",
            body=wrong_history_body,
            headers=WRITE_HEADERS,
            actor_id=projection.actor_id,
        )
    assert history_error.value.code == "GALAXY_HISTORY_NOT_FOUND"
    assert projection.state_snapshot() == before

    wrong_input_body = _upload_body(projection.history_id)
    wrong_input_body["inputs"]["files_0|url_paste"] = ">changed\nACGT\n"
    with pytest.raises(ProjectionError) as input_error:
        projection.request(
            "POST",
            "/api/tools",
            body=wrong_input_body,
            headers=WRITE_HEADERS,
            actor_id=projection.actor_id,
        )
    assert input_error.value.code == "GALAXY_INPUT_INTEGRITY_MISMATCH"
    assert projection.state_snapshot() == before

    _upload(projection)
    before = projection.state_snapshot()
    with pytest.raises(ProjectionError) as dataset_error:
        projection.request(
            "GET",
            "/api/datasets/wrong-dataset",
            headers=READ_HEADERS,
            actor_id=projection.actor_id,
        )
    assert dataset_error.value.code == "GALAXY_DATASET_NOT_FOUND"
    assert projection.state_snapshot() == before


def test_intentional_substantive_response_mismatch_is_detected() -> None:
    report = run_conformance(
        load_reference_trace(),
        _MismatchedProvenanceTarget(),
        profile=GalaxyReferenceProfile(),
    )

    assert report.passed is False
    assert any(
        mismatch.code == "response_type_mismatch"
        and mismatch.path == "/body/tool_id"
        and mismatch.step_id == "read_provenance"
        and mismatch.expected == "upload1"
        and mismatch.actual == 1
        for mismatch in report.mismatches
    )


def test_checked_in_report_is_deterministic_and_current(tmp_path: Path) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = run_projection_conformance(report_path=first_path)
    second = run_projection_conformance(report_path=second_path)
    checked_in_raw = json.loads(DEFAULT_REPORT_PATH.read_text(encoding="utf-8"))

    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_path.read_bytes() == DEFAULT_REPORT_PATH.read_bytes()
    assert ConformanceReport.from_dict(checked_in_raw) == first == second


def test_component_imports_only_generic_reference_contract_from_runtime() -> None:
    component_root = (
        Path(__file__).resolve().parents[2]
        / "api_gym"
        / "provider_components"
        / "galaxy"
    )
    runtime_imports: list[tuple[Path, str]] = []
    forbidden_imports: list[tuple[Path, str]] = []

    for path in sorted(component_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module: str | None = None
            if isinstance(node, ast.ImportFrom):
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("datalox_gated_runtime"):
                        runtime_imports.append((path, alias.name))
                    if _is_forbidden_internal_import(alias.name):
                        forbidden_imports.append((path, alias.name))
            if module is None:
                continue
            if module.startswith("datalox_gated_runtime"):
                runtime_imports.append((path, module))
            if _is_forbidden_internal_import(module):
                forbidden_imports.append((path, module))

    assert runtime_imports == [
        (component_root / "reference_conformance.py", "datalox_gated_runtime.reference")
    ]
    assert forbidden_imports == []


class _MismatchedProvenanceTarget(GalaxyProjectionTarget):
    target_id = "galaxy_intentional_provenance_mismatch"

    def execute(self, call):
        response = super().execute(call)
        if call.operation_id != "galaxy.datasets.provenance.get":
            return response
        body = response.to_dict()["body"]
        body["tool_id"] = 1
        return ObservedResponse(
            status_code=response.status_code,
            headers=response.headers,
            body=body,
        )


def _replay_trace(
    target: GalaxyProjectionTarget,
    trace,
    *,
    seed: int,
) -> dict[str, Any]:
    target.reset(seed)
    initial = [
        target.observe(observation.request)
        for observation in trace.initial_observations
    ]
    responses: list[dict[str, Any]] = []
    post_observations: list[Any] = []
    states: list[str] = []
    for step in trace.steps:
        response = target.execute(step.call)
        responses.append(response.to_dict())
        if step.step_id in {
            "dataset_queued",
            "dataset_running",
            "dataset_ok",
            "read_dataset",
        }:
            states.append(response.body["state"])
        post_observations.extend(
            target.observe(observation.request)
            for observation in step.post_observations
        )
    return {
        "initial": initial,
        "responses": responses,
        "post_observations": post_observations,
        "states": states,
        "final_snapshot": target.projection.state_snapshot(),
    }


def _get_version(projection: GalaxyConnectedFastaProjection) -> None:
    projection.request("GET", "/api/version", headers=READ_HEADERS)


def _list_histories(projection: GalaxyConnectedFastaProjection) -> None:
    projection.request(
        "GET",
        "/api/histories",
        headers=READ_HEADERS,
        actor_id=projection.actor_id,
    )


def _create_history(projection: GalaxyConnectedFastaProjection) -> None:
    projection.request(
        "POST",
        "/api/histories",
        body={"name": "Datalox connected FASTA behavior case"},
        headers=WRITE_HEADERS,
        actor_id=projection.actor_id,
    )


def _upload(projection: GalaxyConnectedFastaProjection) -> None:
    projection.request(
        "POST",
        "/api/tools",
        body=_upload_body(projection.history_id),
        headers=WRITE_HEADERS,
        actor_id=projection.actor_id,
    )


def _upload_body(history_id: Any) -> dict[str, Any]:
    return {
        "history_id": history_id,
        "inputs": dict(UPLOAD_INPUTS),
        "tool_id": "upload1",
    }


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _is_forbidden_internal_import(module: str) -> bool:
    return (
        module.startswith("api_gym.world")
        or module.startswith("api_gym.session")
        or module.startswith("api_gym.runtime")
        or (
            module.startswith("datalox_gated_runtime.")
            and module != "datalox_gated_runtime.reference"
        )
    )
