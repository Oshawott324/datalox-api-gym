"""Bounded eLabFTW experiment projection for one grounded lifecycle."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

PROVIDER_VERSION = "5.6.10"
PROJECTION_VERSION = "elabftw_experiments_create_patch_get_v0"

_EXPERIMENT_PATH = re.compile(r"^/api/v2/experiments/([^/]+)$")
_COLLECTION_PATHS = frozenset({"/api/v2/experiments", "/api/v2/experiments/"})
_PATCH_FIELDS = frozenset({"title", "body", "metadata"})


class ProjectionError(RuntimeError):
    """A request falls outside the grounded eLabFTW projection contract."""

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


@dataclass
class _Experiment:
    experiment_id: int
    title: str = ""
    body: str = ""
    metadata: dict[str, Any] | None = None

    def selected_response_body(self) -> dict[str, Any]:
        return {
            "id": self.experiment_id,
            "title": self.title,
            "body": self.body,
            "metadata": deepcopy(self.metadata or {}),
        }


class ELabFTWExperimentsProjection:
    """Execute only POST -> PATCH -> GET for one eLabFTW experiment."""

    provider_version = PROVIDER_VERSION
    projection_version = PROJECTION_VERSION

    def __init__(self, *, seed: int = 0) -> None:
        self.reset(seed)

    def reset(self, seed: int) -> None:
        if type(seed) is not int:
            raise ProjectionError(
                "ELABFTW_INVALID_SEED",
                "Projection seed must be an integer.",
                details={"received_type": type(seed).__name__},
            )
        self._seed = seed
        self._experiments: dict[int, _Experiment] = {}
        self._created_experiment_id: int | None = None
        self._phase = "awaiting_create"

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> ProjectionResponse:
        if type(method) is not str or not method:
            raise ProjectionError(
                "ELABFTW_INVALID_METHOD",
                "Request method must be a non-empty string.",
                details={"received_type": type(method).__name__},
            )
        if type(path) is not str or not path.startswith("/"):
            raise ProjectionError(
                "ELABFTW_INVALID_PATH",
                "Request path must be an absolute path string.",
                details={"received_type": type(path).__name__},
            )
        normalized_method = method.upper()
        normalized_headers = self._normalize_headers(headers)

        if normalized_method == "POST" and path == "/api/v2/experiments":
            return self._create_experiment(body=body, headers=normalized_headers)
        if normalized_method == "PATCH" and path in _COLLECTION_PATHS:
            self._raise_missing_id(normalized_method, path)
        if normalized_method == "GET" and path in _COLLECTION_PATHS:
            self._raise_missing_id(normalized_method, path)

        match = _EXPERIMENT_PATH.fullmatch(path) if isinstance(path, str) else None
        if match and normalized_method == "PATCH":
            experiment_id = self._parse_experiment_id(match.group(1), method=normalized_method)
            return self._patch_experiment(
                experiment_id,
                body=body,
                headers=normalized_headers,
            )
        if match and normalized_method == "GET":
            experiment_id = self._parse_experiment_id(match.group(1), method=normalized_method)
            return self._get_experiment(
                experiment_id,
                body=body,
                headers=normalized_headers,
            )

        raise ProjectionError(
            "ELABFTW_UNSUPPORTED_OPERATION",
            "Operation is outside the grounded eLabFTW projection.",
            details={"method": normalized_method, "path": path},
        )

    def accessible_experiment_count(self) -> int:
        return len(self._experiments)

    def reference_title_present(self, title: str) -> bool:
        return any(experiment.title == title for experiment in self._experiments.values())

    def experiment_snapshot(self, experiment_id: int) -> dict[str, Any]:
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            raise ProjectionError(
                "ELABFTW_EXPERIMENT_NOT_FOUND",
                "Experiment does not exist in the current projection state.",
                details={"experiment_id": experiment_id},
            )
        return experiment.selected_response_body()

    def experiment_count_delta(self) -> int:
        return len(self._experiments)

    @property
    def created_experiment_id(self) -> int | None:
        return self._created_experiment_id

    def _create_experiment(
        self,
        *,
        body: Any,
        headers: dict[str, str],
    ) -> ProjectionResponse:
        self._require_phase("awaiting_create", operation="POST /api/v2/experiments")
        self._require_headers(headers, content_type=True)
        if type(body) is not dict or body:
            raise ProjectionError(
                "ELABFTW_INVALID_CREATE_PAYLOAD",
                "Grounded experiment creation requires an empty JSON object.",
                details={"expected": {}, "received_type": type(body).__name__},
            )

        experiment_id = self._deterministic_experiment_id()
        self._experiments[experiment_id] = _Experiment(experiment_id=experiment_id)
        self._created_experiment_id = experiment_id
        self._phase = "awaiting_patch"
        return ProjectionResponse(
            status_code=201,
            headers={
                "content-type": "text/html; charset=UTF-8",
                "location": f"/api/v2/experiments/{experiment_id}",
            },
            body=None,
        )

    def _patch_experiment(
        self,
        experiment_id: int,
        *,
        body: Any,
        headers: dict[str, str],
    ) -> ProjectionResponse:
        self._require_existing_experiment(experiment_id, operation="PATCH")
        self._require_phase("awaiting_patch", operation="PATCH /api/v2/experiments/{id}")
        self._require_selected_id(experiment_id)
        self._require_headers(headers, content_type=True)
        if type(body) is not dict or set(body) != _PATCH_FIELDS:
            received_fields = sorted(body) if type(body) is dict else None
            raise ProjectionError(
                "ELABFTW_INVALID_PATCH_PAYLOAD",
                "Grounded experiment patch requires title, body, and metadata only.",
                details={
                    "required_fields": sorted(_PATCH_FIELDS),
                    "received_fields": received_fields,
                    "received_type": type(body).__name__,
                },
            )
        if type(body["title"]) is not str or type(body["body"]) is not str:
            raise ProjectionError(
                "ELABFTW_INVALID_PATCH_PAYLOAD",
                "Experiment title and body must be strings.",
                details={
                    "title_type": type(body["title"]).__name__,
                    "body_type": type(body["body"]).__name__,
                },
            )
        if type(body["metadata"]) is not str:
            raise ProjectionError(
                "ELABFTW_METADATA_MUST_BE_JSON_STRING",
                "eLabFTW 5.6.10 expects metadata as a JSON string on this PATCH surface.",
                details={"received_type": type(body["metadata"]).__name__},
            )
        try:
            metadata = json.loads(body["metadata"])
        except json.JSONDecodeError as error:
            raise ProjectionError(
                "ELABFTW_INVALID_METADATA_JSON",
                "Experiment metadata is not valid JSON.",
                details={"line": error.lineno, "column": error.colno},
            ) from error
        if type(metadata) is not dict:
            raise ProjectionError(
                "ELABFTW_INVALID_METADATA_SHAPE",
                "Experiment metadata must decode to a JSON object.",
                details={"decoded_type": type(metadata).__name__},
            )

        experiment = self._experiments[experiment_id]
        experiment.title = body["title"]
        experiment.body = body["body"]
        experiment.metadata = deepcopy(metadata)
        self._phase = "awaiting_get"
        return ProjectionResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=experiment.selected_response_body(),
        )

    def _get_experiment(
        self,
        experiment_id: int,
        *,
        body: Any,
        headers: dict[str, str],
    ) -> ProjectionResponse:
        self._require_existing_experiment(experiment_id, operation="GET")
        self._require_phase("awaiting_get", operation="GET /api/v2/experiments/{id}")
        self._require_selected_id(experiment_id)
        self._require_headers(headers, content_type=False)
        if body is not None:
            raise ProjectionError(
                "ELABFTW_INVALID_GET_PAYLOAD",
                "Grounded experiment retrieval does not accept a request body.",
                details={"received_type": type(body).__name__},
            )
        self._phase = "complete"
        experiment = self._experiments[experiment_id]
        return ProjectionResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=experiment.selected_response_body(),
        )

    def _deterministic_experiment_id(self) -> int:
        digest = hashlib.sha256(
            f"elabftw:{self._seed}:experiment:0".encode("utf-8")
        ).digest()
        return 100_000 + int.from_bytes(digest[:8], "big") % 900_000

    def _require_headers(self, headers: dict[str, str], *, content_type: bool) -> None:
        if headers.get("accept", "").lower() != "application/json":
            raise ProjectionError(
                "ELABFTW_INVALID_ACCEPT_HEADER",
                "Grounded eLabFTW requests require Accept: application/json.",
                details={"received": headers.get("accept")},
            )
        if content_type and headers.get("content-type", "").lower() != "application/json":
            raise ProjectionError(
                "ELABFTW_INVALID_CONTENT_TYPE",
                "Grounded eLabFTW writes require Content-Type: application/json.",
                details={"received": headers.get("content-type")},
            )

    def _require_phase(self, expected: str, *, operation: str) -> None:
        if self._phase != expected:
            raise ProjectionError(
                "ELABFTW_SEQUENCE_VIOLATION",
                "Operation is not valid at this point in the grounded sequence.",
                details={
                    "operation": operation,
                    "expected_phase": expected,
                    "actual_phase": self._phase,
                },
            )

    def _require_existing_experiment(self, experiment_id: int, *, operation: str) -> None:
        if experiment_id not in self._experiments:
            raise ProjectionError(
                "ELABFTW_EXPERIMENT_NOT_FOUND",
                "Experiment must exist before this operation.",
                details={"operation": operation, "experiment_id": experiment_id},
            )

    def _require_selected_id(self, experiment_id: int) -> None:
        if experiment_id != self._created_experiment_id:
            raise ProjectionError(
                "ELABFTW_EXPERIMENT_ID_MISMATCH",
                "Operation must target the experiment created by this sequence.",
                details={
                    "expected_experiment_id": self._created_experiment_id,
                    "received_experiment_id": experiment_id,
                },
            )

    def _parse_experiment_id(self, value: str, *, method: str) -> int:
        if not value.isdigit() or int(value) <= 0:
            raise ProjectionError(
                "ELABFTW_INVALID_EXPERIMENT_ID",
                "Experiment id must be a positive integer.",
                details={"method": method, "received": value},
            )
        return int(value)

    def _raise_missing_id(self, method: str, path: str) -> None:
        raise ProjectionError(
            "ELABFTW_EXPERIMENT_ID_REQUIRED",
            "This operation requires an experiment id in the path.",
            details={"method": method, "path": path},
        )

    def _normalize_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        if headers is None:
            return {}
        if type(headers) is not dict or not all(
            type(key) is str and type(value) is str for key, value in headers.items()
        ):
            raise ProjectionError(
                "ELABFTW_INVALID_HEADERS",
                "Request headers must be a string-to-string object.",
                details={"received_type": type(headers).__name__},
            )
        return {key.lower(): value for key, value in headers.items()}
