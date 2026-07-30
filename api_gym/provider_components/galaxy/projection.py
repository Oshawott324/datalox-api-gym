"""Bounded stateful Galaxy projection for one captured FASTA lifecycle."""

from __future__ import annotations

import hashlib
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from api_gym.provider_components.galaxy.capture_contract import (
    AFTER_OBSERVATION_ENTITY_ID_TEMPLATES,
    FASTA_TEXT,
    INPUT_SHA256,
    PROVIDER_VERSION,
    RESPONSE_ENTITY_ID_TEMPLATES,
    GalaxyCaptureContract,
    load_capture_contract,
)

PROJECTION_VERSION = "galaxy_connected_history_fasta_projection_v1"

_HISTORY_PATH = re.compile(r"^/api/histories/([^/]+)$")
_HISTORY_CONTENTS_PATH = re.compile(r"^/api/histories/([^/]+)/contents$")
_PROVENANCE_PATH = re.compile(r"^/api/histories/([^/]+)/contents/([^/]+)/provenance$")
_DISPLAY_PATH = re.compile(r"^/api/histories/([^/]+)/contents/([^/]+)/display$")
_DATASET_PATH = re.compile(r"^/api/datasets/([^/]+)$")
_HISTORY_NAME = "Datalox connected FASTA behavior case"
_UPLOAD_BODY_KEYS = frozenset({"history_id", "inputs", "tool_id"})
_UPLOAD_INPUT_KEYS = frozenset(
    {
        "ajax_upload",
        "dbkey",
        "file_type",
        "files_0|NAME",
        "files_0|type",
        "files_0|url_paste",
    }
)
_STARAMR_REQUIRED_TOOL_MARKERS = (
    "staramr_search",
    "amrfinderplus",
    "/abricate/",
    "%2fabricate%2f",
    "tooldistillator",
)


class ProjectionError(RuntimeError):
    """A request falls outside the grounded Galaxy projection contract."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.code = code
        self.details = deepcopy(details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "details": deepcopy(self.details),
        }


@dataclass(frozen=True)
class ProjectionResponse:
    status_code: int
    headers: dict[str, str]
    body: Any


class GalaxyConnectedFastaProjection:
    """Execute only the admitted connected history/upload/read/purge program."""

    provider_version = PROVIDER_VERSION
    projection_version = PROJECTION_VERSION

    def __init__(
        self,
        *,
        seed: int = 0,
        capture: GalaxyCaptureContract | None = None,
    ) -> None:
        self._capture = capture or load_capture_contract()
        self.reset(seed)

    def reset(self, seed: int) -> None:
        if type(seed) is not int:
            raise ProjectionError(
                "GALAXY_INVALID_SEED",
                "Projection seed must be an integer.",
                details={"received_type": type(seed).__name__},
            )
        self._seed = seed
        self._user_id = self._hex_id("user", length=16)
        self._history_id = self._hex_id("history", length=16)
        self._dataset_id = self._hex_id("dataset", length=16)
        self._job_id = self._hex_id("job", length=16)
        self._username = f"datalox_{self._hex_id('username', length=12)}"
        self._dataset_uuid = str(
            uuid.UUID(bytes=self._digest("dataset-uuid")[:16], version=4)
        )
        self._drs_id = f"hda-{self._hex_id('drs', length=16)}"
        self._url_paste_path = (
            "/galaxy/server/database/tmp/"
            f"strio_url_paste_{self._hex_id('url-paste', length=8)}"
        )
        self._paramfile_path = (
            "/galaxy/server/database/tmp/"
            f"upload_params_{self._hex_id('paramfile', length=8)}"
        )
        self._phase = "awaiting_version"
        self._history_exists = False
        self._dataset_exists = False
        self._dataset_state: str | None = None
        self._purged = False
        self._fasta_sha256: str | None = None

    @property
    def actor_id(self) -> str:
        return self._user_id

    @property
    def history_id(self) -> str | None:
        return self._history_id if self._history_exists else None

    @property
    def dataset_id(self) -> str | None:
        return self._dataset_id if self._dataset_exists else None

    @property
    def job_id(self) -> str | None:
        return self._job_id if self._dataset_exists else None

    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
        actor_id: str | None = None,
    ) -> ProjectionResponse:
        normalized_method = self._normalize_method(method)
        normalized_path = self._normalize_path(path)
        normalized_query = self._normalize_query(query)
        normalized_headers = self._normalize_headers(headers)

        self._reject_unsupported_boundaries(
            normalized_method,
            normalized_path,
            query=normalized_query,
            body=body,
        )
        if normalized_method == "GET" and normalized_path == "/api/version":
            return self._get_version(
                query=normalized_query,
                body=body,
                headers=normalized_headers,
            )
        if normalized_path == "/api/histories":
            if normalized_method == "GET":
                return self._list_histories(
                    query=normalized_query,
                    body=body,
                    headers=normalized_headers,
                    actor_id=actor_id,
                )
            if normalized_method == "POST":
                return self._create_history(
                    query=normalized_query,
                    body=body,
                    headers=normalized_headers,
                    actor_id=actor_id,
                )
        if normalized_method == "POST" and normalized_path == "/api/tools":
            return self._upload_fasta(
                query=normalized_query,
                body=body,
                headers=normalized_headers,
                actor_id=actor_id,
            )

        dataset_match = _DATASET_PATH.fullmatch(normalized_path)
        if normalized_method == "GET" and dataset_match is not None:
            return self._get_dataset(
                dataset_match.group(1),
                query=normalized_query,
                body=body,
                headers=normalized_headers,
                actor_id=actor_id,
            )
        provenance_match = _PROVENANCE_PATH.fullmatch(normalized_path)
        if normalized_method == "GET" and provenance_match is not None:
            return self._read_provenance(
                provenance_match.group(1),
                provenance_match.group(2),
                query=normalized_query,
                body=body,
                headers=normalized_headers,
                actor_id=actor_id,
            )
        display_match = _DISPLAY_PATH.fullmatch(normalized_path)
        if normalized_method == "GET" and display_match is not None:
            return self._display_dataset(
                display_match.group(1),
                display_match.group(2),
                query=normalized_query,
                body=body,
                headers=normalized_headers,
                actor_id=actor_id,
            )
        contents_match = _HISTORY_CONTENTS_PATH.fullmatch(normalized_path)
        if normalized_method == "GET" and contents_match is not None:
            return self._read_history_contents(
                contents_match.group(1),
                query=normalized_query,
                body=body,
                headers=normalized_headers,
                actor_id=actor_id,
            )
        history_match = _HISTORY_PATH.fullmatch(normalized_path)
        if history_match is not None:
            if normalized_method == "GET":
                return self._read_history(
                    history_match.group(1),
                    query=normalized_query,
                    body=body,
                    headers=normalized_headers,
                    actor_id=actor_id,
                )
            if normalized_method == "DELETE":
                return self._purge_history(
                    history_match.group(1),
                    query=normalized_query,
                    body=body,
                    headers=normalized_headers,
                    actor_id=actor_id,
                )

        raise ProjectionError(
            "GALAXY_UNSUPPORTED_OPERATION",
            "Operation is outside the grounded Galaxy projection.",
            details={"method": normalized_method, "path": normalized_path},
        )

    def state_snapshot(self) -> dict[str, Any]:
        """Return a deterministic diagnostic snapshot for component tests."""

        return {
            "seed": self._seed,
            "phase": self._phase,
            "actor_id": self._user_id,
            "username": self._username,
            "history_id": self.history_id,
            "history_exists": self._history_exists,
            "dataset_id": self.dataset_id,
            "dataset_exists": self._dataset_exists,
            "job_id": self.job_id,
            "dataset_state": self._dataset_state,
            "purged": self._purged,
            "fasta_sha256": self._fasta_sha256,
        }

    def before_observation(self) -> dict[str, Any]:
        self._require_phase("awaiting_version", operation="observe histories before")
        return self._materialize_generated(self._capture.observation("before"))

    def successful_fasta_observation(self) -> dict[str, Any]:
        self._require_phase(
            "awaiting_purge",
            operation="observe successful FASTA state",
        )
        observation = self._capture.observation("after")
        self._materialize_entity_ids(
            observation,
            AFTER_OBSERVATION_ENTITY_ID_TEMPLATES,
            label="after observation",
        )
        return self._materialize_generated(observation)

    def _get_version(
        self,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
    ) -> ProjectionResponse:
        self._require_phase("awaiting_version", operation="GET /api/version")
        self._require_read_request(query=query, body=body, headers=headers)
        response = self._captured_response("get_version")
        self._phase = "awaiting_history_list"
        return response

    def _list_histories(
        self,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
        actor_id: str | None,
    ) -> ProjectionResponse:
        self._require_owner(actor_id)
        self._require_phase("awaiting_history_list", operation="GET /api/histories")
        self._require_read_request(query=query, body=body, headers=headers)
        response = self._captured_response("histories_before")
        self._phase = "awaiting_history_create"
        return response

    def _create_history(
        self,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
        actor_id: str | None,
    ) -> ProjectionResponse:
        self._require_owner(actor_id)
        self._require_phase("awaiting_history_create", operation="POST /api/histories")
        self._require_write_headers(headers)
        self._require_empty_query(query)
        expected_body = {"name": _HISTORY_NAME}
        if not _json_exact(body, expected_body):
            raise ProjectionError(
                "GALAXY_INVALID_HISTORY_INPUT",
                "Grounded history creation requires the exact captured name.",
                details={"expected": expected_body, "received": deepcopy(body)},
            )
        response = self._captured_response("create_history")
        self._history_exists = True
        self._phase = "awaiting_upload"
        return response

    def _upload_fasta(
        self,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
        actor_id: str | None,
    ) -> ProjectionResponse:
        self._require_owner(actor_id)
        self._require_phase("awaiting_upload", operation="POST /api/tools")
        self._require_write_headers(headers)
        self._require_empty_query(query)
        if type(body) is not dict or set(body) != _UPLOAD_BODY_KEYS:
            raise ProjectionError(
                "GALAXY_INVALID_UPLOAD_INPUT",
                "Grounded upload requires history_id, inputs, and tool_id only.",
                details={
                    "required_fields": sorted(_UPLOAD_BODY_KEYS),
                    "received_fields": sorted(body) if type(body) is dict else None,
                    "received_type": type(body).__name__,
                },
            )
        self._require_history_id(body["history_id"])
        inputs = body["inputs"]
        if type(inputs) is not dict or set(inputs) != _UPLOAD_INPUT_KEYS:
            raise ProjectionError(
                "GALAXY_INVALID_UPLOAD_INPUT",
                "Grounded upload inputs do not match the captured upload1 shape.",
                details={
                    "required_fields": sorted(_UPLOAD_INPUT_KEYS),
                    "received_fields": sorted(inputs) if type(inputs) is dict else None,
                    "received_type": type(inputs).__name__,
                },
            )
        expected_inputs = {
            "ajax_upload": "true",
            "dbkey": "?",
            "file_type": "fasta",
            "files_0|NAME": "input.fa",
            "files_0|type": "upload_dataset",
            "files_0|url_paste": FASTA_TEXT,
        }
        if body["tool_id"] != "upload1" or not _json_exact(inputs, expected_inputs):
            raise ProjectionError(
                "GALAXY_INPUT_INTEGRITY_MISMATCH",
                "Upload must preserve the exact captured upload1 FASTA input.",
                details={
                    "expected_tool_id": "upload1",
                    "expected_input_sha256": INPUT_SHA256,
                },
            )
        actual_digest = (
            f"sha256:{hashlib.sha256(FASTA_TEXT.encode('ascii')).hexdigest()}"
        )
        if actual_digest != INPUT_SHA256:
            raise ProjectionError(
                "GALAXY_INPUT_INTEGRITY_MISMATCH",
                "Projection FASTA bytes do not match the retained input digest.",
                details={"expected": INPUT_SHA256, "actual": actual_digest},
            )

        response = self._captured_response("upload_fasta")
        self._dataset_exists = True
        self._dataset_state = "queued"
        self._fasta_sha256 = actual_digest
        self._phase = "awaiting_dataset_queued"
        return response

    def _get_dataset(
        self,
        dataset_id: str,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
        actor_id: str | None,
    ) -> ProjectionResponse:
        self._require_owner(actor_id)
        self._require_dataset_id(dataset_id)
        self._require_read_request(query=query, body=body, headers=headers)
        phase_program = {
            "awaiting_dataset_queued": (
                "dataset_queued",
                "running",
                "awaiting_dataset_running",
            ),
            "awaiting_dataset_running": (
                "dataset_running",
                "ok",
                "awaiting_dataset_ok",
            ),
            "awaiting_dataset_ok": (
                "dataset_ok",
                "ok",
                "awaiting_dataset_detail",
            ),
            "awaiting_dataset_detail": (
                "read_dataset",
                "ok",
                "awaiting_provenance",
            ),
        }
        selected = phase_program.get(self._phase)
        if selected is None:
            self._raise_sequence("GET /api/datasets/{dataset_id}", tuple(phase_program))
        response_step, next_state, next_phase = selected
        response = self._captured_response(response_step)
        self._dataset_state = next_state
        self._phase = next_phase
        return response

    def _read_provenance(
        self,
        history_id: str,
        dataset_id: str,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
        actor_id: str | None,
    ) -> ProjectionResponse:
        self._require_owner(actor_id)
        self._require_history_id(history_id)
        self._require_dataset_id(dataset_id)
        self._require_phase(
            "awaiting_provenance",
            operation="GET history dataset provenance",
        )
        self._require_read_request(query=query, body=body, headers=headers)
        response = self._captured_response("read_provenance")
        self._phase = "awaiting_display"
        return response

    def _display_dataset(
        self,
        history_id: str,
        dataset_id: str,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
        actor_id: str | None,
    ) -> ProjectionResponse:
        self._require_owner(actor_id)
        self._require_history_id(history_id)
        self._require_dataset_id(dataset_id)
        self._require_phase("awaiting_display", operation="GET dataset display")
        self._require_read_headers(headers)
        if query != {"raw": "true"} or body is not None:
            raise ProjectionError(
                "GALAXY_INVALID_DISPLAY_INPUT",
                "Grounded display readback requires raw=true and no request body.",
                details={"expected_query": {"raw": "true"}, "received_query": query},
            )
        response = self._captured_response("readback_dataset")
        self._phase = "awaiting_history_read"
        return response

    def _read_history(
        self,
        history_id: str,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
        actor_id: str | None,
    ) -> ProjectionResponse:
        self._require_owner(actor_id)
        self._require_history_id(history_id)
        self._require_phase(
            "awaiting_history_read", operation="GET /api/histories/{id}"
        )
        self._require_read_request(query=query, body=body, headers=headers)
        response = self._captured_response("read_history_after")
        self._phase = "awaiting_history_contents"
        return response

    def _read_history_contents(
        self,
        history_id: str,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
        actor_id: str | None,
    ) -> ProjectionResponse:
        self._require_owner(actor_id)
        self._require_history_id(history_id)
        self._require_phase(
            "awaiting_history_contents",
            operation="GET /api/histories/{id}/contents",
        )
        self._require_read_request(query=query, body=body, headers=headers)
        response = self._captured_response("read_history_contents_after")
        self._phase = "awaiting_purge"
        return response

    def _purge_history(
        self,
        history_id: str,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
        actor_id: str | None,
    ) -> ProjectionResponse:
        self._require_owner(actor_id)
        self._require_history_id(history_id)
        self._require_phase(
            "awaiting_purge",
            operation="DELETE /api/histories/{id}?purge=true",
        )
        self._require_read_headers(headers)
        if query != {"purge": "true"} or body is not None:
            raise ProjectionError(
                "GALAXY_INVALID_PURGE_INPUT",
                "Grounded history deletion requires purge=true and no request body.",
                details={"expected_query": {"purge": "true"}, "received_query": query},
            )
        response = self._captured_response("purge_history")
        self._purged = True
        self._history_exists = False
        self._dataset_exists = False
        self._dataset_state = None
        self._phase = "complete"
        return response

    def _captured_response(self, reference_step_id: str) -> ProjectionResponse:
        captured = self._capture.exchange(reference_step_id)["response"]
        materialized = {"body": deepcopy(captured["body"])}
        self._materialize_entity_ids(
            materialized,
            RESPONSE_ENTITY_ID_TEMPLATES.get(reference_step_id, ()),
            label=f"{reference_step_id} response",
        )
        return ProjectionResponse(
            status_code=captured["status_code"],
            headers=self._captured_headers(captured["headers"]),
            body=self._materialize_generated(materialized["body"]),
        )

    def _materialize_generated(self, value: Any) -> Any:
        if type(value) is dict:
            return {
                key: self._materialize_generated(item) for key, item in value.items()
            }
        if type(value) is list:
            return [self._materialize_generated(item) for item in value]
        if type(value) is str:
            replacements = (
                (self._capture.captured_username, self._username),
                (self._capture.captured_dataset_uuid, self._dataset_uuid),
                (self._capture.captured_drs_id, self._drs_id),
                (self._capture.captured_url_paste_path, self._url_paste_path),
                (self._capture.captured_paramfile_path, self._paramfile_path),
            )
            result = value
            for captured, generated in replacements:
                result = result.replace(captured, generated)
            return result
        return value

    def _materialize_entity_ids(
        self,
        value: Any,
        templates: tuple[tuple[str, str], ...],
        *,
        label: str,
    ) -> None:
        captured_ids = self._capture.captured_entity_ids
        generated_ids = {
            "user_id": self._user_id,
            "history_id": self._history_id,
            "dataset_id": self._dataset_id,
            "job_id": self._job_id,
        }
        for pointer, template in templates:
            captured_value = template.format(**captured_ids)
            actual = _pointer_get(value, pointer)
            if actual != captured_value:
                raise ProjectionError(
                    "GALAXY_CAPTURE_ENTITY_BINDING_MISMATCH",
                    "Captured response does not preserve its semantic entity binding.",
                    details={
                        "label": label,
                        "pointer": pointer,
                        "expected": captured_value,
                        "actual": actual,
                    },
                )
            _pointer_set(value, pointer, template.format(**generated_ids))

    def _captured_headers(self, values: list[list[str]]) -> dict[str, str]:
        headers: dict[str, str] = {}
        for raw_name, raw_value in values:
            name = raw_name.lower()
            current = headers.get(name)
            if current is not None and current != raw_value:
                raise ProjectionError(
                    "GALAXY_CAPTURE_HEADER_CONFLICT",
                    "Captured response contains conflicting duplicate headers.",
                    details={"header": name},
                )
            headers[name] = raw_value
        return headers

    def _reject_unsupported_boundaries(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any],
        body: Any,
    ) -> None:
        if path.startswith("/api/workflows") or path.startswith("/api/invocations"):
            invocation = "invocation" in path or path.startswith("/api/invocations")
            code = (
                "GALAXY_UNSUPPORTED_WORKFLOW_INVOCATION"
                if invocation
                else "GALAXY_UNSUPPORTED_WORKFLOW_IMPORT"
            )
            raise ProjectionError(
                code,
                "Workflow import and invocation are outside the grounded Galaxy projection.",
                details={"method": method, "path": path},
            )
        query_text = " ".join(str(value) for value in query.values()).lower()
        body_tool_id = body.get("tool_id") if type(body) is dict else None
        tool_request_text = " ".join(
            (
                path.lower(),
                query_text,
                body_tool_id.lower() if type(body_tool_id) is str else "",
            )
        )
        staramr_requested = "staramr" in tool_request_text or any(
            marker in tool_request_text for marker in _STARAMR_REQUIRED_TOOL_MARKERS
        )
        if path.startswith("/api/tools") and staramr_requested:
            raise ProjectionError(
                "GALAXY_UNSUPPORTED_STARAMR",
                "StarAMR tools were absent and were not imported or invoked in the capture.",
                details={"method": method, "path": path},
            )

    def _require_owner(self, actor_id: str | None) -> None:
        if actor_id != self._user_id:
            raise ProjectionError(
                "GALAXY_OWNERSHIP_VIOLATION",
                "Authenticated actor does not own this projection namespace.",
                details={"actor_id": actor_id},
            )

    def _require_history_id(self, history_id: Any) -> None:
        if (
            type(history_id) is not str
            or not self._history_exists
            or history_id != self._history_id
        ):
            raise ProjectionError(
                "GALAXY_HISTORY_NOT_FOUND",
                "History does not exist in the authenticated projection namespace.",
                details={"history_id": history_id},
            )

    def _require_dataset_id(self, dataset_id: Any) -> None:
        if (
            type(dataset_id) is not str
            or not self._dataset_exists
            or dataset_id != self._dataset_id
        ):
            raise ProjectionError(
                "GALAXY_DATASET_NOT_FOUND",
                "Dataset does not exist in the authenticated projection namespace.",
                details={"dataset_id": dataset_id},
            )

    def _require_phase(self, expected: str, *, operation: str) -> None:
        if self._phase != expected:
            self._raise_sequence(operation, (expected,))

    def _raise_sequence(self, operation: str, expected_phases: tuple[str, ...]) -> None:
        raise ProjectionError(
            "GALAXY_SEQUENCE_VIOLATION",
            "Operation is not valid at this point in the grounded sequence.",
            details={
                "operation": operation,
                "expected_phases": list(expected_phases),
                "actual_phase": self._phase,
            },
        )

    def _require_read_request(
        self,
        *,
        query: dict[str, Any],
        body: Any,
        headers: dict[str, str],
    ) -> None:
        self._require_read_headers(headers)
        self._require_empty_query(query)
        if body is not None:
            raise ProjectionError(
                "GALAXY_INVALID_READ_INPUT",
                "Grounded Galaxy reads do not accept a request body.",
                details={"received_type": type(body).__name__},
            )

    def _require_read_headers(self, headers: dict[str, str]) -> None:
        if headers != {"accept": "application/json"}:
            raise ProjectionError(
                "GALAXY_INVALID_HEADERS",
                "Grounded Galaxy reads require exactly Accept: application/json.",
                details={"received": deepcopy(headers)},
            )

    def _require_write_headers(self, headers: dict[str, str]) -> None:
        expected = {
            "accept": "application/json",
            "content-type": "application/json",
        }
        if headers != expected:
            raise ProjectionError(
                "GALAXY_INVALID_HEADERS",
                "Grounded Galaxy writes require exact JSON accept and content type headers.",
                details={"received": deepcopy(headers)},
            )

    def _require_empty_query(self, query: dict[str, Any]) -> None:
        if query:
            raise ProjectionError(
                "GALAXY_INVALID_QUERY",
                "Grounded operation does not accept query parameters.",
                details={"received": deepcopy(query)},
            )

    def _normalize_method(self, method: Any) -> str:
        if type(method) is not str or not method:
            raise ProjectionError(
                "GALAXY_INVALID_METHOD",
                "Request method must be a non-empty string.",
                details={"received_type": type(method).__name__},
            )
        return method.upper()

    def _normalize_path(self, path: Any) -> str:
        if (
            type(path) is not str
            or not path.startswith("/")
            or "?" in path
            or "#" in path
        ):
            raise ProjectionError(
                "GALAXY_INVALID_PATH",
                "Request path must be absolute with query supplied separately.",
                details={"received": path},
            )
        return path

    def _normalize_query(self, query: Any) -> dict[str, Any]:
        if query is None:
            return {}
        if type(query) is not dict or not all(type(key) is str for key in query):
            raise ProjectionError(
                "GALAXY_INVALID_QUERY",
                "Request query must be a string-keyed object.",
                details={"received_type": type(query).__name__},
            )
        return deepcopy(query)

    def _normalize_headers(self, headers: Any) -> dict[str, str]:
        if headers is None:
            return {}
        if type(headers) is not dict or not all(
            type(key) is str and type(value) is str for key, value in headers.items()
        ):
            raise ProjectionError(
                "GALAXY_INVALID_HEADERS",
                "Request headers must be a string-to-string object.",
                details={"received_type": type(headers).__name__},
            )
        return {key.lower(): value for key, value in headers.items()}

    def _digest(self, label: str) -> bytes:
        return hashlib.sha256(f"galaxy:{self._seed}:{label}".encode("ascii")).digest()

    def _hex_id(self, label: str, *, length: int) -> str:
        return self._digest(label).hex()[:length]


def _json_exact(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(
            _json_exact(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _json_exact(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _pointer_get(value: Any, pointer: str) -> Any:
    current = value
    for component in pointer[1:].split("/"):
        current = current[component] if type(current) is dict else current[int(component)]
    return current


def _pointer_set(value: Any, pointer: str, replacement: Any) -> None:
    components = pointer[1:].split("/")
    parent = value
    for component in components[:-1]:
        parent = parent[component] if type(parent) is dict else parent[int(component)]
    final = components[-1]
    if type(parent) is dict:
        parent[final] = replacement
    else:
        parent[int(final)] = replacement
