"""Complete, capture-backed Cromwell 92 workflow-success behavior contract."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from datalox_gated_runtime.behavior_harvest.engines import v3
from datalox_gated_runtime.reference import ObservedResponse, ReferenceCall

REPO_ROOT = Path(__file__).resolve().parents[3]
CASE_ROOT = (
    REPO_ROOT
    / "source_packs"
    / "apis"
    / "cromwell"
    / "2026-07-30"
    / "behavior_cases"
    / "workflow_success_v1"
)
CONNECTOR_PATH = CASE_ROOT / "connector.json"
RECIPE_PATH = CASE_ROOT / "recipe.json"
FIXTURE_RECEIPT_PATH = CASE_ROOT / "fixture_receipt.json"
WDL_PATH = CASE_ROOT / "success.wdl"
INPUTS_PATH = CASE_ROOT / "success.inputs.json"
CAPTURE_PATH = CASE_ROOT / "capture.json"
CASE_METADATA_PATH = CASE_ROOT / "case_metadata.json"

PROVIDER_VERSION = "92"
PROGRAM_ID = "cromwell_workflow_success_v1"
SUBJECT_ID = "cromwell_workflow_submission_service"
PORT = 59637
ORIGIN = f"http://127.0.0.1:{PORT}"
DISPOSABLE_ROOT = Path("/tmp/datalox-cromwell-92-workflow-success-v1")
EXECUTION_ROOT = DISPOSABLE_ROOT / "executions"
SUCCESS_BOUNDARY = "DataloxCromwellSuccessBoundary"
INVALID_BOUNDARY = "DataloxCromwellInvalidBoundary"
POLL_MAX_ATTEMPTS = 480
POLL_INTERVAL_MS = 500
POLL_DEADLINE_MS = 240_000

CROMWELL_RELEASE_COMMIT = "e94341fdb32f0526b4338f9e1206a84b936dfcac"
CROMWELL_JAR_SIZE = 220_674_800
CROMWELL_JAR_SHA256 = (
    "sha256:e0e3a050d4124e81369a79059e5774142b2f06bd89df4a0b035f559db85cedf5"
)
CROMWELL_JAR_SOURCE = (
    "https://github.com/broadinstitute/cromwell/releases/download/92/cromwell-92.jar"
)
WDL_SHA256 = (
    "sha256:6e6d652e3ba12cd5be4f76733733bc7b3408879d2d0beaf24a405575e1013078"
)
INPUTS_SHA256 = (
    "sha256:a57de4ed9167b07d59f574cbd8be218ecbbcc6d7d4d1d2e3fa8ef0c30dfa4b4a"
)
ENGINE_IDENTITY = v3.EngineIdentity(
    engine_id="behavior_harvest_http11",
    engine_version="3",
    source_sha256=(
        "sha256:a8131506d96f018c0cd7a4268e0fefcab104d788e8c6c425f5d367aaaab328e1"
    ),
)


def canonical_bytes(value: Any) -> bytes:
    body = value.to_dict() if hasattr(value, "to_dict") else value
    return (
        json.dumps(
            body,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def build_fixture_receipt() -> dict[str, Any]:
    return {
        "schema_id": "api_gym.cromwell_fixture_inspection.v1",
        "provider": "cromwell",
        "provider_version": PROVIDER_VERSION,
        "release": {
            "tag": PROVIDER_VERSION,
            "tag_commit": CROMWELL_RELEASE_COMMIT,
        },
        "jar": {
            "source": CROMWELL_JAR_SOURCE,
            "size_bytes": CROMWELL_JAR_SIZE,
            "sha256": CROMWELL_JAR_SHA256,
        },
        "java": {"required_major": 17},
        "origin": ORIGIN,
        "loopback_only": True,
        "backend": {
            "name": "Local",
            "container_runtime": "not_used",
        },
        "database": {
            "engine": "HSQLDB",
            "storage": "file",
            "path_prefix": f"{DISPOSABLE_ROOT}/db/",
        },
        "paths": {
            "disposable_root": str(DISPOSABLE_ROOT),
            "execution_root": str(EXECUTION_ROOT),
            "workflow_log_root": f"{DISPOSABLE_ROOT}/workflow-logs",
        },
    }


def _request(
    method: str,
    path: str | tuple[Any, ...],
    *,
    body: Any = None,
) -> v3.RequestTemplate:
    return v3.RequestTemplate(
        method=method,
        path=path,
        query={},
        body=body,
        headers={},
    )


def _status(assertion_id: str, expected: int) -> v3.AssertionSpec:
    return v3.AssertionSpec(
        assertion_id=assertion_id,
        kind="status_equals",
        expected=expected,
    )


def _json_equals(
    assertion_id: str,
    pointer: str,
    expected: Any,
) -> v3.AssertionSpec:
    return v3.AssertionSpec(
        assertion_id=assertion_id,
        kind="json_pointer_equals",
        pointer=pointer,
        expected=expected,
    )


def _success_multipart() -> v3.MultipartFormDataSpec:
    return v3.MultipartFormDataSpec(
        boundary=SUCCESS_BOUNDARY,
        parts=(
            v3.MultipartPartSpec(
                name="workflowSource",
                artifact_ref="workflow",
                filename="success.wdl",
                media_type="application/octet-stream",
            ),
            v3.MultipartPartSpec(
                name="workflowInputs",
                artifact_ref="inputs",
                filename="success.inputs.json",
                media_type="application/json",
            ),
        ),
    )


def _missing_source_multipart() -> v3.MultipartFormDataSpec:
    return v3.MultipartFormDataSpec(
        boundary=INVALID_BOUNDARY,
        parts=(
            v3.MultipartPartSpec(
                name="workflowInputs",
                artifact_ref="inputs",
                filename="success.inputs.json",
                media_type="application/json",
            ),
        ),
    )


def _poll_spec() -> v3.PollSpec:
    return v3.PollSpec(
        interval_ms=POLL_INTERVAL_MS,
        max_attempts=POLL_MAX_ATTEMPTS,
        deadline_ms=POLL_DEADLINE_MS,
        transient_http_statuses=(404,),
        status_pointer="/status",
        allowed_intermediate_values=("Submitted", "Running"),
        terminal_values=("Succeeded", "Failed", "Aborted"),
        accepted_terminal_values=("Succeeded",),
    )


def _composed(
    step_id: str,
    pointer: str,
    *,
    prefix: str,
    suffix: str,
) -> v3.ComposedStringBindingOccurrence:
    return v3.ComposedStringBindingOccurrence(
        step_id=step_id,
        pointer=pointer,
        prefix=prefix,
        binding_id="primary_workflow_id",
        suffix=suffix,
    )


def build_recipe() -> v3.BehaviorRecipe:
    primary_path = (
        "/api/workflows/v1/",
        {"$binding": "primary_workflow_id"},
    )
    duplicate_path = (
        "/api/workflows/v1/",
        {"$binding": "duplicate_workflow_id"},
    )
    execution_prefix = f"{EXECUTION_ROOT}/success_case/"
    call_prefix = "/call-write_message"
    primary_binding = v3.BindingSpec(
        binding_id="primary_workflow_id",
        pointer="/id",
        value_type="string",
        response_occurrences=tuple(
            v3.ResponseBindingOccurrence(step_id, "/id")
            for step_id in (
                "submit_primary",
                "poll_primary",
                "primary_outputs",
                "primary_logs",
                "primary_metadata",
            )
        ),
        composed_string_occurrences=(
            _composed(
                "primary_outputs",
                "/outputs/success_case.result_file",
                prefix=execution_prefix,
                suffix=f"{call_prefix}/execution/result.txt",
            ),
            _composed(
                "primary_logs",
                "/calls/success_case.write_message/0/stdout",
                prefix=execution_prefix,
                suffix=f"{call_prefix}/execution/stdout",
            ),
            _composed(
                "primary_logs",
                "/calls/success_case.write_message/0/stderr",
                prefix=execution_prefix,
                suffix=f"{call_prefix}/execution/stderr",
            ),
            _composed(
                "primary_metadata",
                "/labels/cromwell-workflow-id",
                prefix="cromwell-",
                suffix="",
            ),
            _composed(
                "primary_metadata",
                "/workflowRoot",
                prefix=execution_prefix,
                suffix="",
            ),
            _composed(
                "primary_metadata",
                "/calls/success_case.write_message/0/callRoot",
                prefix=execution_prefix,
                suffix=call_prefix,
            ),
            _composed(
                "primary_metadata",
                "/calls/success_case.write_message/0/stdout",
                prefix=execution_prefix,
                suffix=f"{call_prefix}/execution/stdout",
            ),
            _composed(
                "primary_metadata",
                "/calls/success_case.write_message/0/stderr",
                prefix=execution_prefix,
                suffix=f"{call_prefix}/execution/stderr",
            ),
            _composed(
                "primary_metadata",
                "/calls/success_case.write_message/0/outputs/result_file",
                prefix=execution_prefix,
                suffix=f"{call_prefix}/execution/result.txt",
            ),
            _composed(
                "primary_metadata",
                "/outputs/success_case.result_file",
                prefix=execution_prefix,
                suffix=f"{call_prefix}/execution/result.txt",
            ),
        ),
    )
    duplicate_binding = v3.BindingSpec(
        binding_id="duplicate_workflow_id",
        pointer="/id",
        value_type="string",
        response_occurrences=(
            v3.ResponseBindingOccurrence("submit_duplicate", "/id"),
            v3.ResponseBindingOccurrence("poll_duplicate", "/id"),
        ),
    )
    success_multipart = _success_multipart()
    poll = _poll_spec()
    return v3.BehaviorRecipe(
        program_id=PROGRAM_ID,
        seed=20260730,
        requirements=v3.ProgramRequirements(
            success=True,
            duplicate=True,
            native_failure=True,
            resulting_state=True,
        ),
        steps=(
            v3.BehaviorStep(
                step_id="provider_status_before_submit",
                operation_id="cromwell.engine.status_before_submit",
                kind="read",
                role="before",
                expected_outcome="read_success",
                subject_id=SUBJECT_ID,
                auth_context_id="loopback_anonymous",
                request=_request("GET", "/engine/v1/status"),
                assertions=(
                    _status("before_status_code", 200),
                    _json_equals("before_status_body", "", {}),
                ),
            ),
            v3.BehaviorStep(
                step_id="submit_primary",
                operation_id="cromwell.workflows.submit",
                kind="mutation",
                role="success",
                expected_outcome="mutation_success",
                subject_id=SUBJECT_ID,
                auth_context_id="loopback_anonymous",
                request=_request("POST", "/api/workflows/v1", body=success_multipart),
                bindings=(primary_binding,),
                assertions=(
                    _status("primary_submit_status", 201),
                    _json_equals("primary_submitted", "/status", "Submitted"),
                    v3.AssertionSpec(
                        assertion_id="primary_uuid",
                        kind="json_pointer_pattern",
                        pointer="/id",
                        pattern=(
                            "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                            "[0-9a-f]{4}-[0-9a-f]{12}"
                        ),
                    ),
                ),
            ),
            v3.BehaviorStep(
                step_id="submit_duplicate",
                operation_id="cromwell.workflows.submit",
                kind="mutation",
                role="duplicate",
                expected_outcome="observe",
                subject_id=SUBJECT_ID,
                auth_context_id="loopback_anonymous",
                request=_request("POST", "/api/workflows/v1", body=success_multipart),
                bindings=(duplicate_binding,),
                assertions=(
                    v3.AssertionSpec(
                        assertion_id="duplicate_exact_request",
                        kind="request_equals_step",
                        prior_step_id="submit_primary",
                    ),
                ),
            ),
            v3.BehaviorStep(
                step_id="missing_source_submission",
                operation_id="cromwell.workflows.submit_missing_source",
                kind="mutation",
                role="native_failure",
                expected_outcome="native_failure",
                subject_id=SUBJECT_ID,
                auth_context_id="loopback_anonymous",
                request=_request(
                    "POST",
                    "/api/workflows/v1",
                    body=_missing_source_multipart(),
                ),
                assertions=(
                    _status("missing_source_status", 400),
                    _json_equals("missing_source_kind", "/status", "fail"),
                    _json_equals(
                        "missing_source_message",
                        "/message",
                        "Error(s): workflowSource or workflowUrl needs to be supplied",
                    ),
                ),
            ),
            v3.BehaviorStep(
                step_id="poll_primary",
                operation_id="cromwell.workflows.status",
                kind="read",
                role="supporting",
                expected_outcome="read_success",
                subject_id=SUBJECT_ID,
                auth_context_id="loopback_anonymous",
                request=_request("GET", (*primary_path, "/status")),
                assertions=(
                    _status("primary_poll_status", 200),
                    _json_equals("primary_poll_succeeded", "/status", "Succeeded"),
                ),
                poll=poll,
            ),
            v3.BehaviorStep(
                step_id="poll_duplicate",
                operation_id="cromwell.workflows.status",
                kind="read",
                role="supporting",
                expected_outcome="read_success",
                subject_id=SUBJECT_ID,
                auth_context_id="loopback_anonymous",
                request=_request("GET", (*duplicate_path, "/status")),
                assertions=(
                    _status("duplicate_poll_status", 200),
                    _json_equals("duplicate_poll_succeeded", "/status", "Succeeded"),
                ),
                poll=poll,
            ),
            v3.BehaviorStep(
                step_id="primary_outputs",
                operation_id="cromwell.workflows.outputs",
                kind="read",
                role="supporting",
                expected_outcome="read_success",
                subject_id=SUBJECT_ID,
                auth_context_id="loopback_anonymous",
                request=_request("GET", (*primary_path, "/outputs")),
                assertions=(
                    _status("outputs_status", 200),
                    _json_equals(
                        "outputs_echoed",
                        "/outputs/success_case.echoed",
                        "hello from cromwell 92",
                    ),
                ),
            ),
            v3.BehaviorStep(
                step_id="primary_logs",
                operation_id="cromwell.workflows.logs",
                kind="read",
                role="supporting",
                expected_outcome="read_success",
                subject_id=SUBJECT_ID,
                auth_context_id="loopback_anonymous",
                request=_request("GET", (*primary_path, "/logs")),
                assertions=(
                    _status("logs_status", 200),
                    v3.AssertionSpec(
                        assertion_id="logs_calls_object",
                        kind="json_pointer_type",
                        pointer="/calls",
                        value_type="object",
                    ),
                ),
            ),
            v3.BehaviorStep(
                step_id="primary_metadata",
                operation_id="cromwell.workflows.metadata",
                kind="read",
                role="resulting_state",
                expected_outcome="observe",
                subject_id=SUBJECT_ID,
                auth_context_id="loopback_anonymous",
                request=_request("GET", (*primary_path, "/metadata")),
                assertions=(
                    _json_equals("metadata_succeeded", "/status", "Succeeded"),
                    _json_equals(
                        "metadata_return_code",
                        "/calls/success_case.write_message/0/returnCode",
                        0,
                    ),
                    _json_equals(
                        "metadata_echoed",
                        "/outputs/success_case.echoed",
                        "hello from cromwell 92",
                    ),
                    v3.AssertionSpec(
                        assertion_id="submitted_to_succeeded_observed",
                        kind="state_observe_step",
                        pointer="/status",
                        prior_step_id="submit_primary",
                        prior_pointer="/status",
                    ),
                ),
            ),
        ),
    )


def build_connector(fixture_receipt: dict[str, Any]) -> v3.ConnectorSpec:
    expected_receipt = build_fixture_receipt()
    if fixture_receipt != expected_receipt:
        raise ValueError("fixture receipt does not match the pinned Cromwell fixture")
    return v3.ConnectorSpec(
        connector_id="cromwell_92_local_workflow_success_v1",
        provider_id="cromwell",
        provider_version=PROVIDER_VERSION,
        origin=ORIGIN,
        driver_kind="http",
        driver_id=ENGINE_IDENTITY.engine_id,
        driver_version=ENGINE_IDENTITY.engine_version,
        driver_source_sha256=ENGINE_IDENTITY.source_sha256,
        request_encoding="canonical_json",
        allowed_request_headers=(),
        boundary=v3.BoundarySpec(
            kind="self_hosted_reference",
            production_equivalence="not_claimed",
            statement=(
                "Disposable loopback Cromwell 92 Local-backend fixture; "
                "production equivalence is not claimed."
            ),
        ),
        auth=v3.AuthProfile(
            profile_id="cromwell_loopback_no_auth_v1",
            kind="none",
            secret_sources=(),
            contexts=(
                v3.AuthContext(
                    context_id="loopback_anonymous",
                    strategy_id="none",
                    secret_source_names=(),
                    actor_alias="loopback_fixture",
                    grant_required=False,
                ),
            ),
        ),
        identity_preflight=v3.IdentityPreflight(
            strategy_id="cromwell_version_status_and_fixture_inspection_v1",
            expected_identity={
                "cromwell": PROVIDER_VERSION,
                "fixture_inspection": fixture_receipt,
            },
            calls=(
                v3.EvidenceCallSpec(
                    call_id="cromwell_version",
                    strategy_id="cromwell_version_status_and_fixture_inspection_v1",
                    auth_context_id="loopback_anonymous",
                    request=_request("GET", "/engine/v1/version"),
                    assertions=(
                        _status("version_status", 200),
                        _json_equals("version_exact", "/cromwell", PROVIDER_VERSION),
                    ),
                ),
                v3.EvidenceCallSpec(
                    call_id="cromwell_status",
                    strategy_id="cromwell_version_status_and_fixture_inspection_v1",
                    auth_context_id="loopback_anonymous",
                    request=_request("GET", "/engine/v1/status"),
                    assertions=(
                        _status("engine_status", 200),
                        _json_equals("engine_status_exact", "", {}),
                    ),
                ),
            ),
            identity_call_id="cromwell_version",
            identity_pointer="",
            authenticated_context_ids=(),
            static_projections=(
                v3.StaticIdentityProjection(
                    output_key="fixture_inspection",
                    input_id="fixture_inspection",
                    pointer="",
                ),
            ),
        ),
        isolation=v3.IsolationResetSpec(
            isolation_kind="run_scoped_resources",
            cleanup_kind="delete_run_resources",
            cleanup_strategy_id="stop_process_and_delete_owned_root",
            reset_kind="none",
            reset_strategy_id=None,
            reset_equivalence_claimed=False,
        ),
        authoring_policy=v3.AuthoringPolicy(),
        static_json_inputs=(
            v3.StaticJsonInputSpec(
                input_id="fixture_inspection",
                schema_id="api_gym.cromwell_fixture_inspection.v1",
                max_bytes=16_384,
                expected_json=fixture_receipt,
            ),
        ),
        source_pins=(
            v3.SourcePin(
                pin_id="cromwell_92_release_jar",
                source_ref=CROMWELL_JAR_SOURCE,
                version=PROVIDER_VERSION,
                sha256=CROMWELL_JAR_SHA256,
            ),
        ),
        collectors=(),
        known_limitations=(
            "This is an exact captured-program projection, not arbitrary Cromwell business logic.",
            "Production deployment, authorization, concurrency, and production equivalence are not claimed.",
            "Fresh-root cleanup is verified, but reset equivalence is not claimed.",
            "Returned log paths are captured as JSON; referenced host files are not dereferenced.",
            "Timestamps, job IDs, and Cromwell instance IDs remain exact capture evidence.",
        ),
        bounds=v3.HarvestBounds(
            max_requests=9 + (2 * POLL_MAX_ATTEMPTS),
            max_request_bytes=65_536,
            max_response_bytes=131_072,
            max_total_response_bytes=8 << 20,
            max_polls=2 * POLL_MAX_ATTEMPTS,
            request_timeout_ms=30_000,
            min_request_interval_ms=0,
        ),
        static_artifact_inputs=(
            v3.StaticArtifactInputSpec(
                artifact_id="workflow",
                filename="success.wdl",
                media_type="application/octet-stream",
                max_bytes=4_096,
                expected_sha256=WDL_SHA256,
            ),
            v3.StaticArtifactInputSpec(
                artifact_id="inputs",
                filename="success.inputs.json",
                media_type="application/json",
                max_bytes=4_096,
                expected_sha256=INPUTS_SHA256,
            ),
        ),
    )


def load_case_metadata() -> dict[str, Any]:
    return json.loads(CASE_METADATA_PATH.read_text(encoding="utf-8"))


def case_load_arguments() -> dict[str, Any]:
    metadata = load_case_metadata()
    return {
        "capture_path": CAPTURE_PATH,
        "expected_capture_sha256": metadata["digests"]["capture"],
        "connector_path": CONNECTOR_PATH,
        "expected_connector_sha256": metadata["digests"]["connector"],
        "recipe_path": RECIPE_PATH,
        "expected_recipe_sha256": metadata["digests"]["recipe"],
        "expected_engine": ENGINE_IDENTITY,
        "sensitive_values": {},
        "static_input_paths": {"fixture_inspection": FIXTURE_RECEIPT_PATH},
        "expected_static_input_sha256": {
            "fixture_inspection": metadata["digests"]["fixture_receipt"]
        },
        "static_artifact_paths": {
            "workflow": WDL_PATH,
            "inputs": INPUTS_PATH,
        },
    }


def load_checked_case() -> v3.LoadedCapture:
    arguments = case_load_arguments()
    return v3.load_capture(
        path=arguments.pop("capture_path"),
        expected_sha256=arguments.pop("expected_capture_sha256"),
        **arguments,
    )


class CromwellSuccessTargetError(RuntimeError):
    """The caller diverged from the exact captured Cromwell success program."""


class CromwellSuccessBehaviorTarget:
    """Exact captured-program projection; no broader Cromwell semantics are claimed."""

    target_id = "cromwell_success_captured_program_projection_v1"
    target_version = "workflow_success_v1"

    def __init__(
        self,
        *,
        capture_path: Path = CAPTURE_PATH,
        generated_primary_id: str | None = None,
        generated_duplicate_id: str | None = None,
    ) -> None:
        raw = json.loads(capture_path.read_text(encoding="utf-8"))
        self._recipe = raw["recipe"]
        self._seed = self._recipe["seed"]
        self._captured_bindings = dict(raw["bindings"])
        self._generated_bindings = {
            "primary_workflow_id": self._validated_uuid(
                generated_primary_id
                or self._captured_bindings["primary_workflow_id"],
                name="generated primary workflow id",
            ),
            "duplicate_workflow_id": self._validated_uuid(
                generated_duplicate_id
                or self._captured_bindings["duplicate_workflow_id"],
                name="generated duplicate workflow id",
            ),
        }
        if (
            self._generated_bindings["primary_workflow_id"]
            == self._generated_bindings["duplicate_workflow_id"]
        ):
            raise CromwellSuccessTargetError("generated workflow IDs must be distinct")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for exchange in raw["exchanges"]:
            grouped.setdefault(exchange["step_id"], []).append(exchange)
        self._steps = tuple(self._recipe["steps"])
        self._terminal_exchanges = tuple(grouped[step["step_id"]][-1] for step in self._steps)
        self._index = 0

    @staticmethod
    def _validated_uuid(value: str, *, name: str) -> str:
        if type(value) is not str:
            raise CromwellSuccessTargetError(f"{name} must be a UUID string")
        try:
            parsed = uuid.UUID(value)
        except ValueError as error:
            raise CromwellSuccessTargetError(f"{name} must be a UUID string") from error
        if str(parsed) != value:
            raise CromwellSuccessTargetError(f"{name} must use canonical UUID syntax")
        return value

    def reset(self, seed: int) -> None:
        if seed != self._seed:
            raise CromwellSuccessTargetError("seed does not match the captured program")
        self._index = 0

    def execute(self, call: ReferenceCall) -> ObservedResponse:
        if self._index >= len(self._steps):
            raise CromwellSuccessTargetError("captured success program is already finished")
        step = self._steps[self._index]
        exchange = self._terminal_exchanges[self._index]
        expected_request = step["request"]
        expected = {
            "method": expected_request["method"],
            "path": self._render_path(expected_request["path"]),
            "query": expected_request["query"],
            "body": expected_request["body"],
            "headers": expected_request["headers"],
            "operation_id": step["operation_id"],
        }
        actual = {
            "method": call.method,
            "path": call.path,
            "query": _plain_json(call.query),
            "body": _plain_json(call.body),
            "headers": dict(call.headers),
            "operation_id": call.operation_id,
        }
        if actual != expected:
            raise CromwellSuccessTargetError(
                f"call {self._index} does not match captured step {step['step_id']}"
            )

        response = exchange["response"]
        body = deepcopy(response["body"])
        self._substitute_response_occurrences(step["step_id"], body)
        self._index += 1
        return ObservedResponse(
            status_code=response["status_code"],
            headers=response["headers"],
            body=body,
        )

    def _render_path(self, template: Any) -> str:
        if type(template) is str:
            return template
        parts: list[str] = []
        for segment in template:
            if isinstance(segment, dict) and set(segment) == {"$binding"}:
                parts.append(self._generated_bindings[segment["$binding"]])
            else:
                parts.append(segment)
        return "".join(parts)

    def _substitute_response_occurrences(self, step_id: str, body: Any) -> None:
        for owner_step in self._steps:
            for binding in owner_step["bindings"]:
                binding_id = binding["binding_id"]
                replacement = self._generated_bindings[binding_id]
                for occurrence in binding.get("response_occurrences", []):
                    if occurrence["step_id"] == step_id:
                        _set_pointer(body, occurrence["pointer"], replacement)
                for occurrence in binding.get("composed_string_occurrences", []):
                    if occurrence["step_id"] == step_id:
                        _set_pointer(
                            body,
                            occurrence["pointer"],
                            f"{occurrence['prefix']}{replacement}{occurrence['suffix']}",
                        )


def _set_pointer(value: Any, pointer: str, replacement: Any) -> None:
    components = [
        item.replace("~1", "/").replace("~0", "~")
        for item in pointer.split("/")[1:]
    ]
    current = value
    for component in components[:-1]:
        current = current[int(component)] if isinstance(current, list) else current[component]
    final = components[-1]
    if isinstance(current, list):
        current[int(final)] = replacement
    else:
        current[final] = replacement


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_json(item) for item in value]
    return value
