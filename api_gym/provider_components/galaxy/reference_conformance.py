"""Differential conformance between the Galaxy capture and bounded projection."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from datalox_gated_runtime.reference import (
    ConformanceReport,
    ExpectedObservation,
    ObservationRequest,
    ObservedResponse,
    ReferenceCall,
    ReferenceStep,
    ReferenceTrace,
    run_conformance,
)

from api_gym.provider_components.galaxy.capture_contract import (
    AFTER_OBSERVATION_ENTITY_ID_TEMPLATES,
    DEFAULT_CAPTURE_PATH,
    GENERATED_ENTITY_ID_NAMES,
    PROVIDER_VERSION,
    REPRESENTATIVE_EXCHANGES,
    RESPONSE_ENTITY_ID_TEMPLATES,
    CaptureContractError,
    GalaxyCaptureContract,
    load_capture_contract,
)
from api_gym.provider_components.galaxy.projection import (
    PROJECTION_VERSION,
    GalaxyConnectedFastaProjection,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT_PATH = (
    REPO_ROOT
    / "source_packs"
    / "apis"
    / "galaxy"
    / "2026-07-30"
    / "conformance"
    / "projection_report.json"
)

CAPTURE_PROVIDER_VERSION = PROVIDER_VERSION
_HISTORY_TOKEN = "{history_id}"
_DATASET_TOKEN = "{dataset_id}"
_USER_TOKEN = "{user_id}"
_USERNAME_TOKEN = "{disposable_username}"
_UUID_TOKEN = "{dataset_uuid}"
_DRS_TOKEN = "{dataset_drs_id}"
_URL_PASTE_TOKEN = "{internal_url_paste_path}"
_PARAMFILE_TOKEN = "{internal_upload_paramfile_path}"

_OPAQUE_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")
_USERNAME_PATTERN = re.compile(r"^datalox_[0-9a-f]{12}$")
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_DRS_ID_PATTERN = re.compile(r"^hda-[0-9a-f]{16}$")
_ISO_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?Z?$"
)
_HTTP_TIMESTAMP_PATTERN = re.compile(
    r"^[A-Z][a-z]{2}, [0-9]{2} [A-Z][a-z]{2} [0-9]{4} "
    r"[0-9]{2}:[0-9]{2}:[0-9]{2} GMT$"
)
_REQUEST_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_URL_PASTE_PATH_PATTERN = re.compile(
    r"^/galaxy/server/database/tmp/strio_url_paste_[0-9a-z]+$"
)
_PARAMFILE_PATH_PATTERN = re.compile(
    r"^/galaxy/server/database/tmp/upload_params_[0-9a-z]+$"
)

_REFERENCE_STEP_IDS = tuple(REPRESENTATIVE_EXCHANGES)
_OPERATION_IDS = {
    "get_version": "galaxy.version.get",
    "histories_before": "galaxy.histories.list",
    "create_history": "galaxy.histories.create",
    "upload_fasta": "galaxy.tools.upload_fasta",
    "dataset_queued": "galaxy.datasets.get",
    "dataset_running": "galaxy.datasets.get",
    "dataset_ok": "galaxy.datasets.get",
    "read_dataset": "galaxy.datasets.get",
    "read_provenance": "galaxy.datasets.provenance.get",
    "readback_dataset": "galaxy.datasets.display.get",
    "read_history_after": "galaxy.histories.get",
    "read_history_contents_after": "galaxy.histories.contents.list",
    "purge_history": "galaxy.histories.purge",
}
_REFERENCE_PATH_TEMPLATES = {
    "get_version": "/api/version",
    "histories_before": "/api/histories",
    "create_history": "/api/histories",
    "upload_fasta": "/api/tools",
    "dataset_queued": "/api/datasets/{dataset_id}",
    "dataset_running": "/api/datasets/{dataset_id}",
    "dataset_ok": "/api/datasets/{dataset_id}",
    "read_dataset": "/api/datasets/{dataset_id}",
    "read_provenance": (
        "/api/histories/{history_id}/contents/{dataset_id}/provenance"
    ),
    "readback_dataset": (
        "/api/histories/{history_id}/contents/{dataset_id}/display"
    ),
    "read_history_after": "/api/histories/{history_id}",
    "read_history_contents_after": "/api/histories/{history_id}/contents",
    "purge_history": "/api/histories/{history_id}",
}
_UUID_POINTERS = {
    "upload_fasta": ("/body/outputs/0/uuid",),
    "dataset_queued": ("/body/uuid",),
    "dataset_running": ("/body/uuid",),
    "dataset_ok": ("/body/uuid",),
    "read_dataset": ("/body/uuid",),
    "read_provenance": ("/body/uuid",),
}
_DRS_POINTERS = {
    step_id: ("/body/drs_id",)
    for step_id in ("dataset_queued", "dataset_running", "dataset_ok", "read_dataset")
}
_USERNAME_POINTERS = {
    "create_history": ("/body/username",),
    "read_history_after": ("/body/username",),
    "purge_history": ("/body/username",),
}
_TIMESTAMP_POINTERS = {
    "create_history": (
        ("/body/create_time", "history_create"),
        ("/body/update_time", "history_update_create"),
    ),
    "upload_fasta": (
        ("/body/jobs/0/create_time", "job_create"),
        ("/body/jobs/0/update_time", "job_update_create"),
        ("/body/outputs/0/create_time", "dataset_create"),
        ("/body/outputs/0/update_time", "dataset_update_queued"),
    ),
    "dataset_queued": (
        ("/body/create_time", "dataset_create"),
        ("/body/update_time", "dataset_update_queued"),
    ),
    "dataset_running": (
        ("/body/create_time", "dataset_create"),
        ("/body/update_time", "dataset_update_running"),
    ),
    "dataset_ok": (
        ("/body/create_time", "dataset_create"),
        ("/body/update_time", "dataset_update_ok"),
    ),
    "read_dataset": (
        ("/body/create_time", "dataset_create"),
        ("/body/update_time", "dataset_update_ok"),
    ),
    "read_history_after": (
        ("/body/create_time", "history_create"),
        ("/body/update_time", "history_update_ok"),
    ),
    "read_history_contents_after": (
        ("/body/0/create_time", "dataset_create"),
        ("/body/0/update_time", "dataset_update_ok"),
    ),
    "purge_history": (
        ("/body/create_time", "history_create"),
        ("/body/update_time", "history_update_purge"),
    ),
}
_OBSERVATION_UUID_POINTERS = ("/provenance/uuid",)
_OBSERVATION_USERNAME_POINTERS = ("/history/username",)
_OBSERVATION_TIMESTAMPS = (
    ("/history/create_time", "history_create"),
    ("/history/update_time", "history_update_ok"),
    ("/history_contents/0/create_time", "dataset_create"),
    ("/history_contents/0/update_time", "dataset_update_ok"),
)


class GalaxyProjectionTarget:
    target_id = "galaxy_connected_history_fasta_projection_v1"
    target_version = PROJECTION_VERSION

    def __init__(
        self,
        projection: GalaxyConnectedFastaProjection | None = None,
    ) -> None:
        self.projection = projection or GalaxyConnectedFastaProjection()

    def reset(self, seed: int) -> None:
        self.projection.reset(seed)

    def execute(self, call: ReferenceCall) -> ObservedResponse:
        response = self.projection.request(
            call.method,
            self._resolve_tokens(call.path),
            query=self._resolve_json(call.query),
            body=self._resolve_json(call.body),
            headers=dict(call.headers),
            actor_id=self.projection.actor_id,
        )
        return ObservedResponse(
            status_code=response.status_code,
            headers=response.headers,
            body=response.body,
        )

    def observe(self, request: ObservationRequest) -> Any:
        query = _plain_json(request.query)
        if request.observation_id == "galaxy.histories.before":
            _require_exact_query(
                query,
                {"kind": "history_collection", "actor_id": _USER_TOKEN},
            )
            return self.projection.before_observation()
        if request.observation_id == "galaxy.fasta.after":
            _require_exact_query(
                query,
                {
                    "kind": "successful_fasta_state",
                    "history_id": _HISTORY_TOKEN,
                    "dataset_id": _DATASET_TOKEN,
                },
            )
            return self.projection.successful_fasta_observation()
        raise CaptureContractError(
            "GALAXY_REFERENCE_OBSERVATION_UNSUPPORTED",
            "Observation is outside the Galaxy reference contract.",
            details={"observation_id": request.observation_id},
        )

    def _resolve_tokens(self, value: str) -> str:
        history_id = self.projection.history_id
        dataset_id = self.projection.dataset_id
        result = value
        if _HISTORY_TOKEN in result:
            if history_id is None:
                raise CaptureContractError(
                    "GALAXY_REFERENCE_HISTORY_ID_UNAVAILABLE",
                    "Reference call requires a history that has not been created.",
                )
            result = result.replace(_HISTORY_TOKEN, history_id)
        if _DATASET_TOKEN in result:
            if dataset_id is None:
                raise CaptureContractError(
                    "GALAXY_REFERENCE_DATASET_ID_UNAVAILABLE",
                    "Reference call requires a dataset that has not been uploaded.",
                )
            result = result.replace(_DATASET_TOKEN, dataset_id)
        return result

    def _resolve_json(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: self._resolve_json(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return [self._resolve_json(item) for item in value]
        if isinstance(value, list):
            return [self._resolve_json(item) for item in value]
        if type(value) is str:
            return self._resolve_tokens(value)
        return value


class GalaxyReferenceProfile:
    """Normalize only explicitly admitted generated capture fields."""

    profile_id = "galaxy_generated_fields_v1"

    def __init__(self) -> None:
        self._response_calls: dict[str, int] = {}
        self._observation_calls: dict[str, int] = {}
        self._bindings = {
            "expected": {},
            "actual": {},
        }

    def normalize_response(
        self,
        *,
        step: ReferenceStep,
        response: ObservedResponse,
    ) -> ObservedResponse:
        side = self._next_side(self._response_calls, step.step_id)
        value = response.to_dict()
        bindings = self._bindings[side]

        if step.step_id == "create_history":
            self._bind_generated(
                bindings,
                "history_id",
                _pointer_get(value, "/body/id"),
                pattern=_OPAQUE_ID_PATTERN,
            )
            self._bind_generated(
                bindings,
                "user_id",
                _pointer_get(value, "/body/user_id"),
                pattern=_OPAQUE_ID_PATTERN,
            )
            self._bind_generated(
                bindings,
                "username",
                _pointer_get(value, "/body/username"),
                pattern=_USERNAME_PATTERN,
            )
        if step.step_id == "upload_fasta":
            self._bind_generated(
                bindings,
                "job_id",
                _pointer_get(value, "/body/jobs/0/id"),
                pattern=_OPAQUE_ID_PATTERN,
            )
            self._bind_generated(
                bindings,
                "dataset_id",
                _pointer_get(value, "/body/outputs/0/id"),
                pattern=_OPAQUE_ID_PATTERN,
            )
            self._bind_generated(
                bindings,
                "dataset_uuid",
                _pointer_get(value, "/body/outputs/0/uuid"),
                pattern=_UUID_PATTERN,
            )
        if step.step_id == "dataset_queued":
            self._bind_generated(
                bindings,
                "drs_id",
                _pointer_get(value, "/body/drs_id"),
                pattern=_DRS_ID_PATTERN,
            )

        self._normalize_entity_id_templates(
            value,
            RESPONSE_ENTITY_ID_TEMPLATES.get(step.step_id, ()),
            bindings=bindings,
        )
        self._normalize_bound_pointers(
            value,
            _UUID_POINTERS.get(step.step_id, ()),
            binding=bindings.get("dataset_uuid"),
            token=_UUID_TOKEN,
        )
        self._normalize_bound_pointers(
            value,
            _DRS_POINTERS.get(step.step_id, ()),
            binding=bindings.get("drs_id"),
            token=_DRS_TOKEN,
        )
        self._normalize_bound_pointers(
            value,
            _USERNAME_POINTERS.get(step.step_id, ()),
            binding=bindings.get("username"),
            token=_USERNAME_TOKEN,
        )
        self._normalize_timestamps(
            value,
            _TIMESTAMP_POINTERS.get(step.step_id, ()),
            bindings=bindings,
        )
        self._normalize_response_headers(value, step_id=step.step_id)
        if step.step_id == "read_provenance":
            self._normalize_provenance(value["body"], bindings=bindings)
        return ObservedResponse.from_dict(value)

    def normalize_observation(
        self,
        *,
        request: ObservationRequest,
        value: Any,
    ) -> Any:
        side = self._next_side(
            self._observation_calls,
            request.observation_id,
        )
        normalized = _plain_json(value)
        if request.observation_id != "galaxy.fasta.after":
            return normalized
        bindings = self._bindings[side]
        self._normalize_entity_id_templates(
            normalized,
            AFTER_OBSERVATION_ENTITY_ID_TEMPLATES,
            bindings=bindings,
        )
        self._normalize_bound_pointers(
            normalized,
            _OBSERVATION_UUID_POINTERS,
            binding=bindings.get("dataset_uuid"),
            token=_UUID_TOKEN,
        )
        self._normalize_bound_pointers(
            normalized,
            _OBSERVATION_USERNAME_POINTERS,
            binding=bindings.get("username"),
            token=_USERNAME_TOKEN,
        )
        self._normalize_timestamps(
            normalized,
            _OBSERVATION_TIMESTAMPS,
            bindings=bindings,
        )
        self._normalize_provenance(
            normalized["provenance"],
            bindings=bindings,
        )
        return normalized

    def _normalize_response_headers(
        self,
        value: dict[str, Any],
        *,
        step_id: str,
    ) -> None:
        headers = value["headers"]
        if _matches(headers.get("date"), _HTTP_TIMESTAMP_PATTERN):
            headers["date"] = f"{{timestamp:response_date:{step_id}}}"
        if _matches(headers.get("last-modified"), _HTTP_TIMESTAMP_PATTERN):
            headers["last-modified"] = f"{{timestamp:last_modified:{step_id}}}"
        if _matches(headers.get("x-request-id"), _REQUEST_ID_PATTERN):
            headers["x-request-id"] = f"{{generated_id:x_request_id:{step_id}}}"

    def _normalize_bound_pointers(
        self,
        value: Any,
        pointers: tuple[str, ...],
        *,
        binding: Any,
        token: str,
    ) -> None:
        if type(binding) is not str or not binding:
            return
        for pointer in pointers:
            current = _pointer_get(value, pointer)
            if type(current) is str and binding in current:
                _pointer_set(value, pointer, current.replace(binding, token))

    def _normalize_entity_id_templates(
        self,
        value: Any,
        templates: tuple[tuple[str, str], ...],
        *,
        bindings: dict[str, Any],
    ) -> None:
        for pointer, template in templates:
            required_bindings = [
                name
                for name in GENERATED_ENTITY_ID_NAMES
                if f"{{{name}}}" in template
            ]
            if not all(
                type(bindings.get(name)) is str for name in required_bindings
            ):
                continue
            if _pointer_get(value, pointer) == template.format(**bindings):
                _pointer_set(value, pointer, template)

    def _normalize_timestamps(
        self,
        value: Any,
        rules: tuple[tuple[str, str], ...],
        *,
        bindings: dict[str, Any],
    ) -> None:
        for pointer, label in rules:
            current = _pointer_get(value, pointer)
            if not _matches(current, _ISO_TIMESTAMP_PATTERN):
                continue
            binding_key = f"timestamp:{label}"
            self._bind(bindings, binding_key, current)
            if current == bindings[binding_key]:
                _pointer_set(value, pointer, f"{{timestamp:{label}}}")

    def _normalize_provenance(
        self,
        provenance: dict[str, Any],
        *,
        bindings: dict[str, Any],
    ) -> None:
        parameters = provenance["parameters"]
        files = json.loads(parameters["files"])
        url_paste_path = files[0]["url_paste"]
        self._bind_generated(
            bindings,
            "url_paste_path",
            url_paste_path,
            pattern=_URL_PASTE_PATH_PATTERN,
        )
        if url_paste_path == bindings.get("url_paste_path"):
            files[0]["url_paste"] = _URL_PASTE_TOKEN
            parameters["files"] = json.dumps(files)

        paramfile_path = json.loads(parameters["paramfile"])
        self._bind_generated(
            bindings,
            "paramfile_path",
            paramfile_path,
            pattern=_PARAMFILE_PATH_PATTERN,
        )
        if paramfile_path == bindings.get("paramfile_path"):
            parameters["paramfile"] = json.dumps(_PARAMFILE_TOKEN)

    def _bind(self, bindings: dict[str, Any], name: str, value: Any) -> None:
        if name not in bindings:
            bindings[name] = value

    def _bind_generated(
        self,
        bindings: dict[str, Any],
        name: str,
        value: Any,
        *,
        pattern: re.Pattern[str],
    ) -> None:
        if _matches(value, pattern):
            self._bind(bindings, name, value)

    def _next_side(self, counts: dict[str, int], identifier: str) -> str:
        count = counts.get(identifier, 0)
        counts[identifier] = count + 1
        return "expected" if count % 2 == 0 else "actual"


def load_reference_trace(
    path: Path = DEFAULT_CAPTURE_PATH,
) -> ReferenceTrace:
    capture = load_capture_contract(path)
    steps: list[ReferenceStep] = []
    for reference_step_id in _REFERENCE_STEP_IDS:
        exchange = capture.exchange(reference_step_id)
        post_observations: tuple[ExpectedObservation, ...] = ()
        if reference_step_id == "read_history_contents_after":
            post_observations = (
                ExpectedObservation(
                    request=ObservationRequest(
                        observation_id="galaxy.fasta.after",
                        query={
                            "kind": "successful_fasta_state",
                            "history_id": _HISTORY_TOKEN,
                            "dataset_id": _DATASET_TOKEN,
                        },
                    ),
                    expected=capture.observation("after"),
                ),
            )
        steps.append(
            ReferenceStep(
                step_id=reference_step_id,
                call=_compile_call(
                    reference_step_id,
                    exchange=exchange,
                    capture=capture,
                ),
                expected_response=_compile_response(exchange),
                post_observations=post_observations,
            )
        )

    evidence_prefix = (
        "source_packs/apis/galaxy/2026-07-30/behavior_cases/"
        "connected_history_fasta_v1/capture.json"
    )
    poll_exchanges = [
        exchange
        for exchange in capture.raw["exchanges"]
        if str(exchange.get("step_id", "")).startswith("poll_dataset_")
    ]
    representative_states = []
    for reference_step_id in ("dataset_queued", "dataset_running", "dataset_ok"):
        exchange = capture.exchange(reference_step_id)
        representative_states.append(
            {
                "reference_step_id": reference_step_id,
                "capture_step_id": exchange["step_id"],
                "exchange_index": REPRESENTATIVE_EXCHANGES[reference_step_id],
                "state": exchange["response"]["body"]["state"],
                "response_body_sha256": exchange["response"]["body_sha256"],
            }
        )

    return ReferenceTrace(
        provider_id="galaxy",
        provider_version=PROVIDER_VERSION,
        seed=20260730,
        initial_observations=(
            ExpectedObservation(
                request=ObservationRequest(
                    observation_id="galaxy.histories.before",
                    query={
                        "kind": "history_collection",
                        "actor_id": _USER_TOKEN,
                    },
                ),
                expected=capture.observation("before"),
            ),
        ),
        steps=tuple(steps),
        evidence_refs=tuple(
            f"{evidence_prefix}#/exchanges/{index}"
            for index in REPRESENTATIVE_EXCHANGES.values()
        ),
        metadata={
            "capture_digest": capture.capture_digest,
            "capture_schema_id": capture.raw["schema_id"],
            "capture_id": capture.raw["capture_id"],
            "provider_execution": "connected_self_hosted_reference",
            "production_equivalence": "not_claimed",
            "representative_state_progression": representative_states,
            "poll_timing": {
                "classification": "ungrounded_timing",
                "captured_poll_count": len(poll_exchanges),
                "captured_total_duration_ms": capture.raw["timing"]["duration_ms"],
                "provider_semantics_claimed": False,
                "projection_rule": "ordered queued -> running -> ok only",
            },
            "normalization_rules": [
                {
                    "kind": "generated_ids",
                    "scope": (
                        "independent user, history, dataset, and job ids; dataset "
                        "UUID; DRS id; and response request-id pointers"
                    ),
                },
                {
                    "kind": "timestamps",
                    "scope": "explicit response header and resource timestamp pointers",
                },
                {
                    "kind": "random_disposable_identity",
                    "scope": "explicit username and user-id pointers",
                },
                {
                    "kind": "internal_temp_paths",
                    "scope": "provenance url_paste and paramfile fields only",
                },
            ],
            "substantive_fields_normalized": False,
            "unsupported_boundaries": {
                "staramr": "fail_closed",
                "workflow_import": "fail_closed",
                "workflow_invocation": "fail_closed",
            },
        },
    )


def run_projection_conformance(
    *,
    capture_path: Path = DEFAULT_CAPTURE_PATH,
    report_path: Path | None = None,
    target: GalaxyProjectionTarget | None = None,
) -> ConformanceReport:
    trace = load_reference_trace(capture_path)
    report = run_conformance(
        trace,
        target or GalaxyProjectionTarget(),
        profile=GalaxyReferenceProfile(),
    )
    if not report.passed:
        raise CaptureContractError(
            "GALAXY_PROJECTION_CONFORMANCE_FAILED",
            "Galaxy projection does not conform to the retained reference trace.",
            details={
                "mismatches": [mismatch.to_dict() for mismatch in report.mismatches]
            },
        )
    if report_path is not None:
        write_conformance_report(report, report_path)
    return report


def write_conformance_report(report: ConformanceReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _compile_call(
    reference_step_id: str,
    *,
    exchange: dict[str, Any],
    capture: GalaxyCaptureContract,
) -> ReferenceCall:
    request = exchange["request"]
    parsed = urlsplit(request["target"])
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if len(query_pairs) != len({key for key, _ in query_pairs}):
        raise CaptureContractError(
            "GALAXY_CAPTURE_DUPLICATE_QUERY",
            "Selected Galaxy request contains duplicate query keys.",
            details={"step_id": exchange["step_id"]},
        )
    path = _REFERENCE_PATH_TEMPLATES[reference_step_id]
    expected_captured_path = path.format(**capture.captured_entity_ids)
    if parsed.path != expected_captured_path:
        raise CaptureContractError(
            "GALAXY_REFERENCE_PATH_BINDING_MISMATCH",
            "Selected Galaxy request path does not preserve entity bindings.",
            details={
                "step_id": exchange["step_id"],
                "expected": expected_captured_path,
                "actual": parsed.path,
            },
        )
    body = deepcopy(request["body"])
    if reference_step_id == "upload_fasta":
        if (
            type(body) is not dict
            or body.get("history_id") != capture.captured_history_id
        ):
            raise CaptureContractError(
                "GALAXY_REFERENCE_BODY_BINDING_MISMATCH",
                "Selected Galaxy upload body does not preserve history binding.",
                details={"step_id": exchange["step_id"]},
            )
        body["history_id"] = _HISTORY_TOKEN
    headers = {"accept": request["headers"]["accept"]}
    if "content-type" in request["headers"]:
        headers["content-type"] = request["headers"]["content-type"]
    return ReferenceCall(
        method=request["method"],
        path=path,
        query=dict(query_pairs),
        body=body,
        headers=headers,
        operation_id=_OPERATION_IDS[reference_step_id],
    )


def _compile_response(exchange: dict[str, Any]) -> ObservedResponse:
    response = exchange["response"]
    return ObservedResponse(
        status_code=response["status_code"],
        body=response["body"],
        headers=_captured_headers(response["headers"]),
    )


def _captured_headers(values: list[list[str]]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_name, raw_value in values:
        name = raw_name.lower()
        current = headers.get(name)
        if current is not None and current != raw_value:
            raise CaptureContractError(
                "GALAXY_CAPTURE_HEADER_CONFLICT",
                "Selected response has conflicting duplicate headers.",
                details={"header": name},
            )
        headers[name] = raw_value
    return headers


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    if isinstance(value, list):
        return [_plain_json(item) for item in value]
    return value


def _pointer_get(value: Any, pointer: str) -> Any:
    current = value
    for component in _pointer_components(pointer):
        if type(current) is dict:
            current = current[component]
        elif type(current) is list:
            current = current[int(component)]
        else:
            raise CaptureContractError(
                "GALAXY_NORMALIZATION_POINTER_INVALID",
                "Normalization pointer does not resolve through JSON containers.",
                details={"pointer": pointer},
            )
    return current


def _pointer_set(value: Any, pointer: str, replacement: Any) -> None:
    components = _pointer_components(pointer)
    parent = value
    for component in components[:-1]:
        parent = parent[component] if type(parent) is dict else parent[int(component)]
    final = components[-1]
    if type(parent) is dict:
        parent[final] = replacement
    else:
        parent[int(final)] = replacement


def _pointer_components(pointer: str) -> tuple[str, ...]:
    if not pointer.startswith("/") or pointer == "/":
        raise CaptureContractError(
            "GALAXY_NORMALIZATION_POINTER_INVALID",
            "Normalization pointer must identify a concrete JSON field.",
            details={"pointer": pointer},
        )
    return tuple(
        component.replace("~1", "/").replace("~0", "~")
        for component in pointer[1:].split("/")
    )


def _require_exact_query(actual: Any, expected: dict[str, Any]) -> None:
    if actual != expected:
        raise CaptureContractError(
            "GALAXY_REFERENCE_OBSERVATION_QUERY_INVALID",
            "Galaxy observation query does not match the reference contract.",
            details={"expected": expected, "actual": actual},
        )


def _matches(value: Any, pattern: re.Pattern[str]) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None
