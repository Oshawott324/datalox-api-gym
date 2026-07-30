"""Complete, capture-backed eLabFTW PATCH behavior contract."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from datalox_gated_runtime.behavior_harvest.engines import v2
from datalox_gated_runtime.reference import ObservedResponse, ReferenceCall

REPO_ROOT = Path(__file__).resolve().parents[3]
CASE_ROOT = (
    REPO_ROOT
    / "source_packs"
    / "apis"
    / "elabftw"
    / "2026-07-30"
    / "behavior_cases"
    / "experiments_patch_complete_v1"
)
CONNECTOR_PATH = CASE_ROOT / "connector.json"
RECIPE_PATH = CASE_ROOT / "recipe.json"
FIXTURE_RECEIPT_PATH = CASE_ROOT / "fixture_receipt.json"
CAPTURE_PATH = CASE_ROOT / "capture.json"
CASE_METADATA_PATH = CASE_ROOT / "case_metadata.json"

ORIGIN = "http://127.0.0.1:3148"
PROVIDER_VERSION = "5.6.10"
PROGRAM_ID = "elabftw_experiments_patch_complete_v1"
SUBJECT_ID = "elabftw_experiment_record"
AUTH_SECRET_NAME = "elabftw_api_key"
ENGINE_IDENTITY = v2.EngineIdentity(
    engine_id="behavior_harvest_http11",
    engine_version="2",
    source_sha256=(
        "sha256:efbdea5510aead688bf128d3c2091db4650998d3e96a57bec2415018bcf81844"
    ),
)
WEB_IMAGE_DIGEST = (
    "sha256:a4dd2264b6fa40bb250ca68d3845afa442bb15c29aed95cd444786084eb30e67"
)
MYSQL_IMAGE_DIGEST = (
    "sha256:8dbcf531a03aade657e181b9cf2f1d1803ce621a1d55610cb44cb531ab7d7db6"
)

REFERENCE_TITLE = "Datalox AMR analysis handoff"
REFERENCE_BODY = "<p>Reference AMR analysis handoff for isolate AMR-ISO-001.</p>"
REFERENCE_METADATA = {
    "extra_fields": {
        "isolate_id": {
            "description": "Stable isolate identifier used across the analysis handoff",
            "type": "text",
            "value": "AMR-ISO-001",
        }
    }
}
PATCH_BODY = {
    "body": REFERENCE_BODY,
    "metadata": json.dumps(REFERENCE_METADATA, separators=(",", ":"), sort_keys=True),
    "title": REFERENCE_TITLE,
}
NATIVE_FAILURE_BODY = {"unknown_update_target": "must_fail"}
INFO_IDENTITY = {
    "active_users_count": 2,
    "all_users_count": 2,
    "compounds_count": 0,
    "elabftw_version": PROVIDER_VERSION,
    "elabftw_version_int": 50610,
    "entities_timestamped_count_last_30_days": 0,
    "experiments_count": 0,
    "experiments_timestamped_count": 0,
    "items_count": 0,
    "teams_count": 1,
    "ts_balance": 0,
    "ts_limit": 0,
    "uploads_filesize_sum": 0,
    "uploads_filesize_sum_formatted": "0.00 B",
}


def _request(
    method: str,
    path: str | tuple[Any, ...],
    *,
    body: Any = None,
) -> v2.RequestTemplate:
    return v2.RequestTemplate(
        method=method,
        path=path,
        body=body,
        headers={"accept": "application/json"},
    )


def _status(assertion_id: str, expected: int) -> v2.AssertionSpec:
    return v2.AssertionSpec(
        assertion_id=assertion_id,
        kind="status_equals",
        expected=expected,
    )


def build_recipe() -> v2.BehaviorRecipe:
    bound_path = ("/api/v2/experiments/", {"$binding": "experiment_id"})
    id_occurrences = tuple(
        v2.ResponseBindingOccurrence(step_id, pointer)
        for step_id, pointer in (
            ("list_experiments", "/0/id"),
            ("before_experiment", "/id"),
            ("patch_experiment", "/id"),
            ("duplicate_patch", "/id"),
            ("resulting_experiment", "/id"),
        )
    )
    return v2.BehaviorRecipe(
        program_id=PROGRAM_ID,
        seed=20260730,
        requirements=v2.ProgramRequirements(
            success=True,
            duplicate=True,
            native_failure=True,
            resulting_state=True,
        ),
        steps=(
            v2.BehaviorStep(
                step_id="create_experiment",
                operation_id="elabftw.experiments.create",
                kind="mutation",
                role="supporting",
                expected_outcome="mutation_success",
                subject_id=SUBJECT_ID,
                auth_context_id="fixture_actor",
                request=_request("POST", "/api/v2/experiments", body={}),
                assertions=(_status("create_status", 201),),
            ),
            v2.BehaviorStep(
                step_id="list_experiments",
                operation_id="elabftw.experiments.list",
                kind="read",
                role="supporting",
                expected_outcome="read_success",
                subject_id=SUBJECT_ID,
                auth_context_id="fixture_actor",
                request=_request("GET", "/api/v2/experiments"),
                bindings=(
                    v2.BindingSpec(
                        binding_id="experiment_id",
                        pointer="/0/id",
                        value_type="integer",
                        response_occurrences=id_occurrences,
                    ),
                ),
                assertions=(
                    _status("list_status", 200),
                    v2.AssertionSpec(
                        assertion_id="list_id_type",
                        kind="json_pointer_type",
                        pointer="/0/id",
                        value_type="integer",
                    ),
                ),
            ),
            v2.BehaviorStep(
                step_id="before_experiment",
                operation_id="elabftw.experiments.get",
                kind="read",
                role="before",
                expected_outcome="read_success",
                subject_id=SUBJECT_ID,
                auth_context_id="fixture_actor",
                request=_request("GET", bound_path),
                assertions=(
                    _status("before_status", 200),
                    v2.AssertionSpec(
                        assertion_id="before_title_type",
                        kind="json_pointer_type",
                        pointer="/title",
                        value_type="string",
                    ),
                ),
            ),
            v2.BehaviorStep(
                step_id="patch_experiment",
                operation_id="elabftw.experiments.patch",
                kind="mutation",
                role="success",
                expected_outcome="mutation_success",
                subject_id=SUBJECT_ID,
                auth_context_id="fixture_actor",
                request=_request("PATCH", bound_path, body=PATCH_BODY),
                assertions=(
                    _status("patch_status", 200),
                    v2.AssertionSpec(
                        assertion_id="patch_title",
                        kind="json_pointer_equals",
                        pointer="/title",
                        expected=REFERENCE_TITLE,
                    ),
                ),
            ),
            v2.BehaviorStep(
                step_id="duplicate_patch",
                operation_id="elabftw.experiments.patch",
                kind="mutation",
                role="duplicate",
                expected_outcome="observe",
                subject_id=SUBJECT_ID,
                auth_context_id="fixture_actor",
                request=_request("PATCH", bound_path, body=PATCH_BODY),
                assertions=(
                    v2.AssertionSpec(
                        assertion_id="duplicate_exact_request",
                        kind="request_equals_step",
                        prior_step_id="patch_experiment",
                    ),
                ),
            ),
            v2.BehaviorStep(
                step_id="invalid_patch",
                operation_id="elabftw.experiments.patch.invalid_target",
                kind="mutation",
                role="native_failure",
                expected_outcome="native_failure",
                subject_id=SUBJECT_ID,
                auth_context_id="fixture_actor",
                request=_request("PATCH", bound_path, body=NATIVE_FAILURE_BODY),
                assertions=(
                    _status("invalid_patch_status", 400),
                    v2.AssertionSpec(
                        assertion_id="invalid_patch_code",
                        kind="json_pointer_equals",
                        pointer="/code",
                        expected=400,
                    ),
                    v2.AssertionSpec(
                        assertion_id="invalid_patch_message",
                        kind="json_pointer_equals",
                        pointer="/message",
                        expected="Invalid update target.",
                    ),
                ),
            ),
            v2.BehaviorStep(
                step_id="resulting_experiment",
                operation_id="elabftw.experiments.get",
                kind="read",
                role="resulting_state",
                expected_outcome="observe",
                subject_id=SUBJECT_ID,
                auth_context_id="fixture_actor",
                request=_request("GET", bound_path),
                assertions=(
                    v2.AssertionSpec(
                        assertion_id="observed_title_vs_before",
                        kind="state_observe_step",
                        pointer="/title",
                        prior_step_id="before_experiment",
                        prior_pointer="/title",
                    ),
                    v2.AssertionSpec(
                        assertion_id="observed_title_vs_success",
                        kind="state_observe_step",
                        pointer="/title",
                        prior_step_id="patch_experiment",
                        prior_pointer="/title",
                    ),
                ),
            ),
        ),
    )


def build_connector(fixture_receipt: dict[str, Any]) -> v2.ConnectorSpec:
    if fixture_receipt.get("origin") != ORIGIN:
        raise ValueError(f"fixture receipt origin must be {ORIGIN}")
    return v2.ConnectorSpec(
        connector_id="elabftw_local_complete_behavior_v1",
        provider_id="elabftw",
        provider_version=PROVIDER_VERSION,
        origin=ORIGIN,
        driver_kind="http",
        driver_id=ENGINE_IDENTITY.engine_id,
        driver_version=ENGINE_IDENTITY.engine_version,
        driver_source_sha256=ENGINE_IDENTITY.source_sha256,
        request_encoding="canonical_json",
        allowed_request_headers=("accept",),
        boundary=v2.BoundarySpec(
            kind="self_hosted_reference",
            production_equivalence="not_claimed",
            statement=(
                "Disposable loopback eLabFTW 5.6.10 fixture; no production "
                "equivalence is claimed."
            ),
        ),
        auth=v2.AuthProfile(
            profile_id="elabftw_opaque_api_key_v1",
            kind="secret",
            secret_sources=(
                v2.SecretSource(
                    name=AUTH_SECRET_NAME,
                    kind="environment",
                    scan_variants=("raw", "urlencoded", "base64"),
                ),
            ),
            contexts=(
                v2.AuthContext(
                    context_id="fixture_actor",
                    strategy_id=v2.AUTH_STRATEGY_OPAQUE_AUTHORIZATION_HEADER,
                    secret_source_names=(AUTH_SECRET_NAME,),
                    actor_alias="disposable_fixture_actor",
                    grant_required=False,
                ),
            ),
        ),
        identity_preflight=v2.IdentityPreflight(
            strategy_id="elabftw_info_and_fixture_inspection_v1",
            expected_identity={
                **INFO_IDENTITY,
                "fixture_inspection": fixture_receipt,
            },
            calls=(
                v2.EvidenceCallSpec(
                    call_id="elabftw_info",
                    strategy_id="elabftw_info_and_fixture_inspection_v1",
                    auth_context_id="fixture_actor",
                    request=_request("GET", "/api/v2/info"),
                    assertions=(
                        _status("info_status", 200),
                        v2.AssertionSpec(
                            assertion_id="info_version",
                            kind="json_pointer_equals",
                            pointer="/elabftw_version",
                            expected=PROVIDER_VERSION,
                        ),
                    ),
                ),
            ),
            identity_call_id="elabftw_info",
            identity_pointer="",
            authenticated_context_ids=(),
            static_projections=(
                v2.StaticIdentityProjection(
                    output_key="fixture_inspection",
                    input_id="fixture_inspection",
                    pointer="",
                ),
            ),
        ),
        isolation=v2.IsolationResetSpec(
            isolation_kind="namespace",
            cleanup_kind="namespace_recreate",
            cleanup_strategy_id="docker_compose_down_volumes",
            reset_kind="tenant_recreate",
            reset_strategy_id="docker_compose_fresh_project",
            reset_equivalence_claimed=False,
        ),
        authoring_policy=v2.AuthoringPolicy(concurrency=1, write_retries=0),
        static_json_inputs=(
            v2.StaticJsonInputSpec(
                input_id="fixture_inspection",
                schema_id="api_gym.elabftw_fixture_inspection.v1",
                max_bytes=16384,
                expected_json=fixture_receipt,
            ),
        ),
        source_pins=(
            v2.SourcePin(
                pin_id="elabftw_web_image",
                source_ref="docker://elabftw/elabimg:5.6.10",
                version=PROVIDER_VERSION,
                sha256=WEB_IMAGE_DIGEST,
            ),
            v2.SourcePin(
                pin_id="mysql_fixture_image",
                source_ref="docker://mysql:8.4",
                version="8.4",
                sha256=MYSQL_IMAGE_DIGEST,
            ),
        ),
        collectors=(),
        known_limitations=(
            "Only the captured experiment create/list/get/patch behavior is projected.",
            "The duplicate PATCH is observational and is not claimed to be idempotent.",
            "No production deployment, concurrency, permissions, or attachment behavior is claimed.",
        ),
        bounds=v2.HarvestBounds(
            max_requests=8,
            max_request_bytes=65536,
            max_response_bytes=2_000_000,
            max_total_response_bytes=12_000_000,
            max_polls=0,
            request_timeout_ms=30000,
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


def load_case_metadata() -> dict[str, Any]:
    return json.loads(CASE_METADATA_PATH.read_text(encoding="utf-8"))


def case_load_arguments(secret: bytes) -> dict[str, Any]:
    metadata = load_case_metadata()
    return {
        "capture_path": CAPTURE_PATH,
        "expected_capture_sha256": metadata["digests"]["capture"],
        "connector_path": CONNECTOR_PATH,
        "expected_connector_sha256": metadata["digests"]["connector"],
        "recipe_path": RECIPE_PATH,
        "expected_recipe_sha256": metadata["digests"]["recipe"],
        "expected_engine": ENGINE_IDENTITY,
        "sensitive_values": {AUTH_SECRET_NAME: secret},
        "static_input_paths": {"fixture_inspection": FIXTURE_RECEIPT_PATH},
        "expected_static_input_sha256": {
            "fixture_inspection": metadata["digests"]["fixture_receipt"]
        },
    }


def load_checked_case(secret: bytes) -> v2.LoadedCapture:
    arguments = case_load_arguments(secret)
    return v2.load_capture(
        path=arguments.pop("capture_path"),
        expected_sha256=arguments.pop("expected_capture_sha256"),
        **arguments,
    )


class CompleteBehaviorTargetError(RuntimeError):
    """The caller diverged from the admitted complete behavior program."""


class ELabFTWCompleteBehaviorTarget:
    """Exact capture-backed projection for the admitted seven-call program."""

    target_id = "elabftw_complete_behavior_projection_v1"
    target_version = "experiments_patch_complete_v1"

    def __init__(
        self,
        *,
        capture_path: Path = CAPTURE_PATH,
        generated_experiment_id: int | None = None,
    ) -> None:
        raw = json.loads(capture_path.read_text(encoding="utf-8"))
        self._exchanges = tuple(raw["exchanges"])
        self._captured_experiment_id = raw["bindings"]["experiment_id"]
        if (
            type(self._captured_experiment_id) is not int
            or self._captured_experiment_id < 0
        ):
            raise CompleteBehaviorTargetError("capture experiment id is invalid")
        selected = (
            self._captured_experiment_id
            if generated_experiment_id is None
            else generated_experiment_id
        )
        if type(selected) is not int or selected < 0:
            raise CompleteBehaviorTargetError(
                "generated experiment id must be a non-negative integer"
            )
        self._generated_experiment_id = selected
        self._index = 0

    def reset(self, seed: int) -> None:
        if type(seed) is not int:
            raise CompleteBehaviorTargetError("seed must be an integer")
        self._index = 0

    def execute(self, call: ReferenceCall) -> ObservedResponse:
        if self._index >= len(self._exchanges):
            raise CompleteBehaviorTargetError(
                "complete behavior program is already finished"
            )
        exchange = self._exchanges[self._index]
        expected_request = exchange["request"]
        expected_path = expected_request["path"]
        suffix = f"/{self._captured_experiment_id}"
        if expected_path.endswith(suffix):
            expected_path = (
                expected_path[: -len(suffix)] + f"/{self._generated_experiment_id}"
            )
        expected = {
            "method": expected_request["method"],
            "path": expected_path,
            "query": expected_request["query"],
            "body": expected_request["body"],
            "headers": expected_request["headers"],
            "operation_id": expected_request["operation_id"],
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
            raise CompleteBehaviorTargetError(
                f"call {self._index} does not match admitted step {exchange['step_id']}"
            )

        response = exchange["response"]
        body = deepcopy(response["body"])
        if exchange["step_id"] == "list_experiments":
            body[0]["id"] = self._generated_experiment_id
        elif exchange["step_id"] in {
            "before_experiment",
            "patch_experiment",
            "duplicate_patch",
            "resulting_experiment",
        }:
            body["id"] = self._generated_experiment_id
        self._index += 1
        return ObservedResponse(
            status_code=response["status_code"],
            headers=response["headers"],
            body=body,
        )


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    if isinstance(value, list):
        return [_plain_json(item) for item in value]
    return value
