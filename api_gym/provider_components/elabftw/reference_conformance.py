"""Differential conformance between the eLabFTW capture and projection."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

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

from api_gym.provider_components.elabftw.projection import (
    ELabFTWExperimentsProjection,
    PROJECTION_VERSION,
    ProjectionError,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CAPTURE_PATH = (
    REPO_ROOT
    / "source_packs"
    / "apis"
    / "elabftw"
    / "2026-07-26"
    / "raw"
    / "reference_sequences"
    / "experiments_create_patch_get_v0.json"
)
DEFAULT_REPORT_PATH = (
    REPO_ROOT
    / "source_packs"
    / "apis"
    / "elabftw"
    / "2026-07-26"
    / "conformance"
    / "projection_report.json"
)

CAPTURE_PROVIDER_VERSION = "5.6.10"
CAPTURE_WEB_IMAGE_DIGEST = (
    "sha256:a4dd2264b6fa40bb250ca68d3845afa442bb15c29aed95cd444786084eb30e67"
)
_EXPERIMENT_TOKEN = "{experiment_id}"
_LOCATION_PATTERN = re.compile(r"^/api/v2/experiments/([1-9][0-9]*)$")
_OPERATION_IDS = {
    "POST /api/v2/experiments": "elabftw.experiments.create",
    "PATCH /api/v2/experiments/{experiment_id}": "elabftw.experiments.patch",
    "GET /api/v2/experiments/{experiment_id}": "elabftw.experiments.get",
}


class CaptureContractError(ValueError):
    """The retained eLabFTW sequence is not the grounded contract expected here."""


class ELabFTWProjectionTarget:
    target_id = "elabftw_experiments_projection_v0"
    target_version = PROJECTION_VERSION

    def __init__(self, projection: ELabFTWExperimentsProjection | None = None) -> None:
        self.projection = projection or ELabFTWExperimentsProjection()
        self._experiment_id: int | None = None

    def reset(self, seed: int) -> None:
        self.projection.reset(seed)
        self._experiment_id = None

    def execute(self, call: ReferenceCall) -> ObservedResponse:
        path = self._resolve_path(call.path)
        response = self.projection.request(
            call.method,
            path,
            body=_json_copy(call.body),
            headers=dict(call.headers),
        )
        if call.operation_id == "elabftw.experiments.create":
            location = response.headers.get("location", "")
            match = re.fullmatch(r"/api/v2/experiments/([1-9][0-9]*)", location)
            if match is None:
                raise ProjectionError(
                    "ELABFTW_INVALID_CREATE_LOCATION",
                    "Projection create response did not identify the created experiment.",
                    details={"location": location},
                )
            self._experiment_id = int(match.group(1))
        return ObservedResponse(
            status_code=response.status_code,
            body=response.body,
            headers=response.headers,
        )

    def observe(self, request: ObservationRequest) -> Any:
        query = _json_copy(request.query)
        if request.observation_id == "elabftw.pre_experiments":
            _require_exact_query(
                query,
                {
                    "kind": "pre_experiment_state",
                    "reference_title": query.get("reference_title"),
                },
            )
            title = _require_string(query.get("reference_title"), "reference_title")
            return {
                "accessible_experiment_count": self.projection.accessible_experiment_count(),
                "reference_title_present": self.projection.reference_title_present(title),
            }
        if request.observation_id == "elabftw.post_experiment":
            _require_exact_query(
                query,
                {
                    "kind": "post_experiment_state",
                    "experiment_id": _EXPERIMENT_TOKEN,
                },
            )
            experiment_id = self._require_experiment_id()
            return {
                "accessible_experiment_count": self.projection.accessible_experiment_count(),
                "experiment": self.projection.experiment_snapshot(experiment_id),
                "experiment_count_delta": self.projection.experiment_count_delta(),
            }
        raise CaptureContractError(
            f"unsupported eLabFTW observation: {request.observation_id}"
        )

    def _resolve_path(self, path: str) -> str:
        if _EXPERIMENT_TOKEN not in path:
            return path
        return path.replace(_EXPERIMENT_TOKEN, str(self._require_experiment_id()))

    def _require_experiment_id(self) -> int:
        if self._experiment_id is None:
            raise ProjectionError(
                "ELABFTW_EXPERIMENT_ID_UNAVAILABLE",
                "The reference sequence has not created an experiment yet.",
                details={"required_predecessor": "POST /api/v2/experiments"},
            )
        return self._experiment_id


class ELabFTWReferenceProfile:
    profile_id = "elabftw_experiment_id_location_v0"

    def __init__(self) -> None:
        self._generated_experiment_id: int | None = None

    def normalize_response(
        self,
        *,
        step: ReferenceStep,
        response: ObservedResponse,
    ) -> ObservedResponse:
        value = response.to_dict()
        if step.step_id == "create_experiment":
            location = value["headers"].get("location")
            if location == "/api/v2/experiments/{experiment_id}":
                return ObservedResponse.from_dict(value)
            match = _LOCATION_PATTERN.fullmatch(location) if isinstance(location, str) else None
            if match is not None:
                self._generated_experiment_id = int(match.group(1))
                value["headers"]["location"] = (
                    "/api/v2/experiments/{experiment_id}"
                )
        elif step.step_id in {"patch_experiment", "get_experiment"}:
            body = value["body"]
            if isinstance(body, dict) and self._matches_generated_id(body.get("id")):
                body["id"] = _EXPERIMENT_TOKEN
        return ObservedResponse.from_dict(value)

    def normalize_observation(
        self,
        *,
        request: ObservationRequest,
        value: Any,
    ) -> Any:
        normalized = _json_copy(value)
        if request.observation_id != "elabftw.post_experiment":
            return normalized
        if not isinstance(normalized, dict):
            return normalized
        experiment = normalized.get("experiment")
        if isinstance(experiment, dict) and self._matches_generated_id(experiment.get("id")):
            experiment["id"] = _EXPERIMENT_TOKEN
        return normalized

    def _matches_generated_id(self, value: Any) -> bool:
        if value == _EXPERIMENT_TOKEN:
            return True
        if self._generated_experiment_id is None:
            return False
        if type(value) is int:
            return value == self._generated_experiment_id
        return (
            type(value) is str
            and value.isdigit()
            and int(value) == self._generated_experiment_id
        )


def load_reference_trace(path: Path = DEFAULT_CAPTURE_PATH) -> ReferenceTrace:
    raw_bytes = path.read_bytes()
    capture_digest = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
    raw = json.loads(raw_bytes.decode("utf-8"))
    _validate_capture(raw)
    steps: list[ReferenceStep] = []
    for index, captured_step in enumerate(raw["steps"]):
        operation = captured_step["operation"]
        method, path_value = operation.split(" ", 1)
        response = captured_step["response"]
        post_observations: tuple[ExpectedObservation, ...] = ()
        if index == len(raw["steps"]) - 1:
            post_observations = (
                ExpectedObservation(
                    request=ObservationRequest(
                        observation_id="elabftw.post_experiment",
                        query={
                            "kind": "post_experiment_state",
                            "experiment_id": _EXPERIMENT_TOKEN,
                        },
                    ),
                    expected=raw["observations"]["post"],
                ),
            )
        steps.append(
            ReferenceStep(
                step_id=(
                    "create_experiment",
                    "patch_experiment",
                    "get_experiment",
                )[index],
                call=ReferenceCall(
                    method=method,
                    path=path_value,
                    operation_id=_OPERATION_IDS[operation],
                    body=captured_step["request"]["body"],
                    headers=captured_step["request"]["headers"],
                ),
                expected_response=ObservedResponse(
                    status_code=response["status"],
                    body=response["body"],
                    headers=response["headers"],
                ),
                post_observations=post_observations,
            )
        )

    return ReferenceTrace(
        provider_id=raw["provider"]["id"],
        provider_version=raw["provider"]["version"],
        seed=20260726,
        initial_observations=(
            ExpectedObservation(
                request=ObservationRequest(
                    observation_id="elabftw.pre_experiments",
                    query={
                        "kind": "pre_experiment_state",
                        "reference_title": raw["steps"][1]["request"]["body"]["title"],
                    },
                ),
                expected=raw["observations"]["pre"],
            ),
        ),
        steps=tuple(steps),
        evidence_refs=tuple(raw["evidence_sources"]),
        metadata={
            "capture_digest": capture_digest,
            "capture_schema_version": raw["schema_version"],
            "sequence_id": raw["sequence_id"],
            "provider_image_digest": raw["provider"]["image"]["digest"],
        },
    )


def run_projection_conformance(
    *,
    capture_path: Path = DEFAULT_CAPTURE_PATH,
    report_path: Path | None = None,
    target: ELabFTWProjectionTarget | None = None,
) -> ConformanceReport:
    trace = load_reference_trace(capture_path)
    report = run_conformance(
        trace,
        target or ELabFTWProjectionTarget(),
        profile=ELabFTWReferenceProfile(),
    )
    if not report.passed:
        raise CaptureContractError(
            "eLabFTW projection does not conform to the retained reference sequence: "
            f"{[mismatch.to_dict() for mismatch in report.mismatches]}"
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


def _validate_capture(raw: Any) -> None:
    if type(raw) is not dict:
        raise CaptureContractError("eLabFTW capture must be a JSON object")
    if raw.get("schema_version") != "api_gym.provider_reference_sequence.v0":
        raise CaptureContractError("unsupported eLabFTW capture schema")
    provider = raw.get("provider")
    if not isinstance(provider, dict) or provider.get("id") != "elabftw":
        raise CaptureContractError("capture provider must be elabftw")
    if provider.get("version") != CAPTURE_PROVIDER_VERSION:
        raise CaptureContractError(
            f"capture provider version must be {CAPTURE_PROVIDER_VERSION}"
        )
    image = provider.get("image")
    image_digest = image.get("digest") if isinstance(image, dict) else None
    if image_digest != CAPTURE_WEB_IMAGE_DIGEST:
        raise CaptureContractError(
            f"capture provider web image digest must be {CAPTURE_WEB_IMAGE_DIGEST}"
        )
    operations = [
        step.get("operation") for step in raw.get("steps", []) if isinstance(step, dict)
    ]
    if operations != list(_OPERATION_IDS):
        raise CaptureContractError(
            "capture must contain the grounded create, patch, get sequence"
        )
    if not isinstance(raw.get("observations"), dict):
        raise CaptureContractError("capture observations are required")


def _json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_copy(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_copy(item) for item in value]
    if isinstance(value, list):
        return [_json_copy(item) for item in value]
    return value


def _require_exact_query(actual: Any, expected: dict[str, Any]) -> None:
    if actual != expected:
        raise CaptureContractError(
            f"invalid observation query: expected {expected!r}, received {actual!r}"
        )


def _require_string(value: Any, field: str) -> str:
    if type(value) is not str or not value:
        raise CaptureContractError(f"observation query {field} must be a non-empty string")
    return value
