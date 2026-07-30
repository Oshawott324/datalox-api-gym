"""Validated access to the retained Galaxy connected FASTA capture."""

from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
CASE_ROOT = (
    REPO_ROOT
    / "source_packs"
    / "apis"
    / "galaxy"
    / "2026-07-30"
    / "behavior_cases"
    / "connected_history_fasta_v1"
)
DEFAULT_CAPTURE_PATH = CASE_ROOT / "capture.json"
DEFAULT_CASE_METADATA_PATH = CASE_ROOT / "case_metadata.json"
DEFAULT_INPUT_PATH = CASE_ROOT / "input.fa"

CAPTURE_SCHEMA_ID = "api_gym.galaxy_connected_capture.v1"
CASE_METADATA_SCHEMA_ID = "api_gym.provider_behavior_case_metadata.v1"
CAPTURE_ID = "galaxy_connected_history_fasta_v1"
PROVIDER_ID = "galaxy"
PROVIDER_VERSION = "26.1.rc1"
INPUT_SHA256 = "sha256:d044ffc156b7f0a06cd252ec80ab8f0c0ef40ee57bbe3b0d4139f70bd8cbd39c"
INPUT_BYTES = 44
FASTA_TEXT = ">datalox_connected_fixture\nACGTACGTACGTACGT\n"

# These are artifact coordinates, not a claim that the observed poll count is
# Galaxy provider semantics.
REPRESENTATIVE_EXCHANGES = {
    "get_version": 2,
    "histories_before": 4,
    "create_history": 5,
    "upload_fasta": 6,
    "dataset_queued": 7,
    "dataset_running": 10,
    "dataset_ok": 91,
    "read_dataset": 92,
    "read_provenance": 93,
    "readback_dataset": 94,
    "read_history_after": 95,
    "read_history_contents_after": 96,
    "purge_history": 103,
}
REPRESENTATIVE_CAPTURE_STEP_IDS = {
    "get_version": "get_version",
    "histories_before": "histories_before",
    "create_history": "create_history",
    "upload_fasta": "upload_fasta",
    "dataset_queued": "poll_dataset_01",
    "dataset_running": "poll_dataset_04",
    "dataset_ok": "poll_dataset_85",
    "read_dataset": "read_dataset",
    "read_provenance": "read_provenance",
    "readback_dataset": "readback_dataset",
    "read_history_after": "read_history_after",
    "read_history_contents_after": "read_history_contents_after",
    "purge_history": "purge_history",
}
GENERATED_ENTITY_ID_NAMES = ("user_id", "history_id", "dataset_id", "job_id")

_CREATED_HISTORY_ID_TEMPLATES = (
    ("/body/contents_url", "/api/histories/{history_id}/contents"),
    ("/body/id", "{history_id}"),
    ("/body/url", "/api/histories/{history_id}"),
    ("/body/user_id", "{user_id}"),
)
_COMPLETED_HISTORY_ID_TEMPLATES = _CREATED_HISTORY_ID_TEMPLATES + (
    ("/body/state_ids/ok/0", "{dataset_id}"),
)
_DATASET_ID_TEMPLATES = (
    ("/body/creating_job", "{job_id}"),
    ("/body/dataset_id", "{dataset_id}"),
    (
        "/body/download_url",
        "/api/histories/{history_id}/contents/{dataset_id}/display",
    ),
    ("/body/history_id", "{history_id}"),
    ("/body/id", "{dataset_id}"),
    ("/body/permissions/manage/0", "{user_id}"),
    ("/body/type_id", "dataset-{dataset_id}"),
    (
        "/body/url",
        "/api/histories/{history_id}/contents/{dataset_id}",
    ),
)
_DISPLAY_APP_ID_TEMPLATE = (
    "/body/display_apps/0/links/0/href",
    "/display_application/{dataset_id}/igv_fasta/local_default",
)

# JSON pointers are rooted at the provider response object. Templates identify
# semantic entity bindings even when captured encoded values happen to coincide.
RESPONSE_ENTITY_ID_TEMPLATES = {
    "create_history": _CREATED_HISTORY_ID_TEMPLATES,
    "upload_fasta": (
        ("/body/jobs/0/history_id", "{history_id}"),
        ("/body/jobs/0/id", "{job_id}"),
        ("/body/outputs/0/history_id", "{history_id}"),
        ("/body/outputs/0/id", "{dataset_id}"),
    ),
    "dataset_queued": _DATASET_ID_TEMPLATES,
    "dataset_running": _DATASET_ID_TEMPLATES,
    "dataset_ok": _DATASET_ID_TEMPLATES + (_DISPLAY_APP_ID_TEMPLATE,),
    "read_dataset": _DATASET_ID_TEMPLATES + (_DISPLAY_APP_ID_TEMPLATE,),
    "read_provenance": (
        ("/body/id", "{dataset_id}"),
        ("/body/job_id", "{job_id}"),
    ),
    "read_history_after": _COMPLETED_HISTORY_ID_TEMPLATES,
    "read_history_contents_after": (
        ("/body/0/dataset_id", "{dataset_id}"),
        ("/body/0/history_id", "{history_id}"),
        ("/body/0/id", "{dataset_id}"),
        ("/body/0/type_id", "dataset-{dataset_id}"),
        (
            "/body/0/url",
            "/api/histories/{history_id}/contents/{dataset_id}",
        ),
    ),
    "purge_history": _COMPLETED_HISTORY_ID_TEMPLATES,
}
AFTER_OBSERVATION_ENTITY_ID_TEMPLATES = (
    ("/history/contents_url", "/api/histories/{history_id}/contents"),
    ("/history/id", "{history_id}"),
    ("/history/state_ids/ok/0", "{dataset_id}"),
    ("/history/url", "/api/histories/{history_id}"),
    ("/history/user_id", "{user_id}"),
    ("/history_contents/0/dataset_id", "{dataset_id}"),
    ("/history_contents/0/history_id", "{history_id}"),
    ("/history_contents/0/id", "{dataset_id}"),
    ("/history_contents/0/type_id", "dataset-{dataset_id}"),
    (
        "/history_contents/0/url",
        "/api/histories/{history_id}/contents/{dataset_id}",
    ),
    ("/provenance/id", "{dataset_id}"),
    ("/provenance/job_id", "{job_id}"),
)
_REFERENCE_HTTP_CONTRACTS = {
    "get_version": ("GET", "/api/version", 200, "minimal_sequence"),
    "histories_before": ("GET", "/api/histories", 200, "minimal_sequence"),
    "create_history": ("POST", "/api/histories", 200, "minimal_sequence"),
    "upload_fasta": ("POST", "/api/tools", 200, "minimal_sequence"),
    "dataset_queued": (
        "GET",
        "/api/datasets/{dataset_id}",
        200,
        "minimal_sequence",
    ),
    "dataset_running": (
        "GET",
        "/api/datasets/{dataset_id}",
        200,
        "minimal_sequence",
    ),
    "dataset_ok": (
        "GET",
        "/api/datasets/{dataset_id}",
        200,
        "minimal_sequence",
    ),
    "read_dataset": (
        "GET",
        "/api/datasets/{dataset_id}",
        200,
        "minimal_sequence",
    ),
    "read_provenance": (
        "GET",
        "/api/histories/{history_id}/contents/{dataset_id}/provenance",
        200,
        "minimal_sequence",
    ),
    "readback_dataset": (
        "GET",
        "/api/histories/{history_id}/contents/{dataset_id}/display?raw=true",
        200,
        "minimal_sequence",
    ),
    "read_history_after": (
        "GET",
        "/api/histories/{history_id}",
        200,
        "minimal_sequence",
    ),
    "read_history_contents_after": (
        "GET",
        "/api/histories/{history_id}/contents",
        200,
        "minimal_sequence",
    ),
    "purge_history": (
        "DELETE",
        "/api/histories/{history_id}?purge=true",
        200,
        "teardown",
    ),
}


class CaptureContractError(ValueError):
    """The retained Galaxy capture violates its pinned fail-closed contract."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = deepcopy(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "details": deepcopy(self.details),
        }


@dataclass(frozen=True)
class GalaxyCaptureContract:
    """Validated source data used by the bounded projection."""

    capture_digest: str
    raw: dict[str, Any]
    input_bytes: bytes
    captured_user_id: str
    captured_history_id: str
    captured_dataset_id: str
    captured_job_id: str
    captured_username: str
    captured_dataset_uuid: str
    captured_drs_id: str
    captured_url_paste_path: str
    captured_paramfile_path: str

    @property
    def captured_entity_ids(self) -> dict[str, str]:
        return {
            "user_id": self.captured_user_id,
            "history_id": self.captured_history_id,
            "dataset_id": self.captured_dataset_id,
            "job_id": self.captured_job_id,
        }

    def exchange(self, reference_step_id: str) -> dict[str, Any]:
        try:
            index = REPRESENTATIVE_EXCHANGES[reference_step_id]
        except KeyError as error:
            raise CaptureContractError(
                "GALAXY_CAPTURE_UNKNOWN_REFERENCE_STEP",
                "Reference step is not compiled from the retained Galaxy capture.",
                details={"step_id": reference_step_id},
            ) from error
        return deepcopy(self.raw["exchanges"][index])

    def observation(self, name: str) -> Any:
        observations = self.raw["observations"]
        if name not in observations:
            raise CaptureContractError(
                "GALAXY_CAPTURE_UNKNOWN_OBSERVATION",
                "Observation is not retained in the Galaxy capture.",
                details={"observation": name},
            )
        return deepcopy(observations[name])


def load_capture_contract(
    path: Path = DEFAULT_CAPTURE_PATH,
    *,
    case_metadata_path: Path = DEFAULT_CASE_METADATA_PATH,
    input_path: Path = DEFAULT_INPUT_PATH,
    expected_capture_sha256: str | None = None,
) -> GalaxyCaptureContract:
    """Load and validate the exact connected FASTA evidence contract."""

    raw_bytes = path.read_bytes()
    capture_digest = _sha256(raw_bytes)
    metadata = _load_json_object(case_metadata_path, label="case metadata")
    _validate_case_metadata(metadata)
    expected_digest = expected_capture_sha256 or metadata["digests"]["capture"]
    _require(
        capture_digest == expected_digest,
        "GALAXY_CAPTURE_DIGEST_MISMATCH",
        "Galaxy capture bytes do not match the pinned case metadata.",
        expected=expected_digest,
        actual=capture_digest,
    )

    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaptureContractError(
            "GALAXY_CAPTURE_INVALID_JSON",
            "Galaxy capture must be valid UTF-8 JSON.",
        ) from error
    _require(
        type(raw) is dict,
        "GALAXY_CAPTURE_INVALID_ROOT",
        "Galaxy capture must be a JSON object.",
    )

    input_bytes = input_path.read_bytes()
    _validate_capture(raw, input_bytes=input_bytes)
    provenance = _exchange_by_step(raw, "read_provenance")["response"]["body"]
    provenance_files = json.loads(provenance["parameters"]["files"])
    captured_paramfile_path = json.loads(provenance["parameters"]["paramfile"])
    create_body = _exchange_by_step(raw, "create_history")["response"]["body"]
    upload_body = _exchange_by_step(raw, "upload_fasta")["response"]["body"]
    queued_body = _exchange_by_step(raw, "poll_dataset_01")["response"]["body"]

    return GalaxyCaptureContract(
        capture_digest=capture_digest,
        raw=deepcopy(raw),
        input_bytes=input_bytes,
        captured_user_id=create_body["user_id"],
        captured_history_id=raw["minimal_sequence"]["history_id"],
        captured_dataset_id=raw["minimal_sequence"]["dataset_id"],
        captured_job_id=upload_body["jobs"][0]["id"],
        captured_username=create_body["username"],
        captured_dataset_uuid=upload_body["outputs"][0]["uuid"],
        captured_drs_id=queued_body["drs_id"],
        captured_url_paste_path=provenance_files[0]["url_paste"],
        captured_paramfile_path=captured_paramfile_path,
    )


def _validate_case_metadata(raw: dict[str, Any]) -> None:
    _require(
        raw.get("schema_id") == CASE_METADATA_SCHEMA_ID,
        "GALAXY_CASE_METADATA_SCHEMA_MISMATCH",
        "Galaxy case metadata schema is not supported.",
    )
    _require(
        raw.get("program_id") == CAPTURE_ID,
        "GALAXY_CASE_METADATA_PROGRAM_MISMATCH",
        "Galaxy case metadata program id is not supported.",
    )
    _require(
        raw.get("provider_id") == PROVIDER_ID
        and raw.get("provider_version") == PROVIDER_VERSION,
        "GALAXY_CASE_METADATA_PROVIDER_MISMATCH",
        "Galaxy case metadata provider identity is not supported.",
    )
    digests = raw.get("digests")
    _require(
        type(digests) is dict
        and _is_sha256(digests.get("capture"))
        and digests.get("input") == INPUT_SHA256,
        "GALAXY_CASE_METADATA_DIGESTS_INVALID",
        "Galaxy case metadata must pin the capture and exact FASTA input.",
    )


def _validate_capture(raw: dict[str, Any], *, input_bytes: bytes) -> None:
    _require(
        raw.get("schema_id") == CAPTURE_SCHEMA_ID,
        "GALAXY_CAPTURE_SCHEMA_MISMATCH",
        "Galaxy capture schema is not supported.",
    )
    _require(
        raw.get("capture_id") == CAPTURE_ID,
        "GALAXY_CAPTURE_ID_MISMATCH",
        "Galaxy capture id is not supported.",
    )
    _require(
        raw.get("provider_id") == PROVIDER_ID
        and raw.get("provider_version") == PROVIDER_VERSION,
        "GALAXY_CAPTURE_PROVIDER_MISMATCH",
        "Galaxy capture provider identity is not supported.",
    )
    _require(
        raw.get("capture_error") is None,
        "GALAXY_CAPTURE_RECORDED_ERROR",
        "Galaxy capture recorded a capture failure.",
    )
    execution = raw.get("provider_execution")
    _require(
        type(execution) is dict
        and execution.get("kind") == "connected_self_hosted_reference"
        and execution.get("status") == "observed"
        and execution.get("production_equivalence") == "not_claimed",
        "GALAXY_CAPTURE_EXECUTION_BOUNDARY_MISMATCH",
        "Galaxy capture must be provider-observed without production equivalence.",
    )

    input_contract = raw.get("input")
    _require(
        type(input_contract) is dict
        and input_contract.get("immutable") is True
        and input_contract.get("body_bytes") == INPUT_BYTES
        and input_contract.get("body_sha256") == INPUT_SHA256,
        "GALAXY_CAPTURE_INPUT_CONTRACT_MISMATCH",
        "Galaxy capture does not pin the exact immutable FASTA input.",
    )
    _require(
        len(input_bytes) == INPUT_BYTES
        and _sha256(input_bytes) == INPUT_SHA256
        and input_bytes.decode("ascii") == FASTA_TEXT,
        "GALAXY_CAPTURE_INPUT_FILE_MISMATCH",
        "Retained input.fa does not match the captured FASTA bytes.",
    )

    minimal = raw.get("minimal_sequence")
    _require(
        type(minimal) is dict
        and minimal.get("completed") is True
        and minimal.get("provider_executed") is True,
        "GALAXY_CAPTURE_MINIMAL_SEQUENCE_INCOMPLETE",
        "Galaxy minimal sequence must be successfully provider-executed.",
    )
    create_user_body = _exchange_by_step(raw, "create_disposable_user")["response"][
        "body"
    ]
    create_history_body = _exchange_by_step(raw, "create_history")["response"]["body"]
    upload_body = _exchange_by_step(raw, "upload_fasta")["response"]["body"]
    entity_ids = {
        "user_id": create_history_body.get("user_id"),
        "history_id": minimal.get("history_id"),
        "dataset_id": minimal.get("dataset_id"),
        "job_id": upload_body.get("jobs", [{}])[0].get("id"),
    }
    _require(
        all(_is_opaque_id(value) for value in entity_ids.values())
        and create_user_body.get("id") == entity_ids["user_id"]
        and create_history_body.get("id") == entity_ids["history_id"]
        and upload_body.get("outputs", [{}])[0].get("id")
        == entity_ids["dataset_id"],
        "GALAXY_CAPTURE_RESOURCE_BINDINGS_INVALID",
        "Galaxy capture entity bindings are invalid.",
        entity_ids=entity_ids,
    )

    exchanges = raw.get("exchanges")
    _require(
        type(exchanges) is list,
        "GALAXY_CAPTURE_EXCHANGES_INVALID",
        "Galaxy capture exchanges must be an array.",
    )
    for reference_step_id, index in REPRESENTATIVE_EXCHANGES.items():
        _require(
            index < len(exchanges),
            "GALAXY_CAPTURE_EXCHANGE_MISSING",
            "Galaxy capture is missing a cited representative exchange.",
            step_id=reference_step_id,
            exchange_index=index,
        )
        exchange = exchanges[index]
        expected_step_id = REPRESENTATIVE_CAPTURE_STEP_IDS[reference_step_id]
        _require(
            type(exchange) is dict
            and exchange.get("step_id") == expected_step_id
            and exchange.get("provider_executed") is True,
            "GALAXY_CAPTURE_EXCHANGE_MISMATCH",
            "Galaxy representative exchange does not match its pinned citation.",
            step_id=reference_step_id,
            exchange_index=index,
            expected_capture_step_id=expected_step_id,
        )
        method, target_template, status, phase = _REFERENCE_HTTP_CONTRACTS[
            reference_step_id
        ]
        expected_target = target_template.format(**entity_ids)
        _require(
            exchange.get("phase") == phase
            and exchange.get("request", {}).get("method") == method
            and exchange.get("request", {}).get("target") == expected_target
            and exchange.get("response", {}).get("status_code") == status,
            "GALAXY_CAPTURE_HTTP_CONTRACT_MISMATCH",
            "Galaxy representative exchange changed method, target, status, or phase.",
            step_id=reference_step_id,
            expected_method=method,
            expected_target=expected_target,
            expected_status=status,
            expected_phase=phase,
        )
        _validate_exchange_payloads(exchange)
        _validate_entity_id_templates(
            exchange["response"],
            RESPONSE_ENTITY_ID_TEMPLATES.get(reference_step_id, ()),
            entity_ids=entity_ids,
            label=f"{reference_step_id} response",
        )

    poll_exchanges = [
        exchange
        for exchange in exchanges
        if type(exchange) is dict
        and str(exchange.get("step_id", "")).startswith("poll_dataset_")
    ]
    poll_states = [exchange["response"]["body"]["state"] for exchange in poll_exchanges]
    _require(
        poll_states == minimal.get("poll_states"),
        "GALAXY_CAPTURE_POLL_RECORD_MISMATCH",
        "Galaxy poll exchanges and minimal-sequence state record disagree.",
    )
    ordered_states = [
        state
        for index, state in enumerate(poll_states)
        if index == 0 or state != poll_states[index - 1]
    ]
    _require(
        ordered_states == ["queued", "running", "ok"],
        "GALAXY_CAPTURE_STATE_ORDER_MISMATCH",
        "Galaxy capture must establish ordered queued, running, and ok states.",
        observed=ordered_states,
    )
    for step_id, expected_state in (
        ("poll_dataset_01", "queued"),
        ("poll_dataset_04", "running"),
        ("poll_dataset_85", "ok"),
    ):
        actual_state = _exchange_by_step(raw, step_id)["response"]["body"].get("state")
        _require(
            actual_state == expected_state,
            "GALAXY_CAPTURE_REPRESENTATIVE_STATE_MISMATCH",
            "Galaxy representative state exchange changed.",
            step_id=step_id,
            expected=expected_state,
            actual=actual_state,
        )

    readback = _exchange_by_step(raw, "readback_dataset")["response"]
    _require(
        readback.get("status_code") == 200
        and readback.get("body") == FASTA_TEXT
        and readback.get("body_bytes") == INPUT_BYTES
        and readback.get("body_sha256") == INPUT_SHA256,
        "GALAXY_CAPTURE_READBACK_MISMATCH",
        "Galaxy dataset readback does not match the exact FASTA input.",
    )
    provenance = _exchange_by_step(raw, "read_provenance")["response"]["body"]
    _require(
        type(provenance) is dict
        and provenance.get("tool_id") == "upload1"
        and provenance.get("stderr") == ""
        and provenance.get("stdout") == "",
        "GALAXY_CAPTURE_PROVENANCE_MISMATCH",
        "Galaxy provenance does not identify the captured upload1 execution.",
    )
    observations = raw.get("observations")
    _require(
        type(observations) is dict
        and observations.get("before") == {"histories": []}
        and observations.get("after", {}).get("history")
        == _exchange_by_step(raw, "read_history_after")["response"]["body"]
        and observations.get("after", {}).get("history_contents")
        == _exchange_by_step(raw, "read_history_contents_after")["response"]["body"]
        and observations.get("after", {}).get("provenance") == provenance,
        "GALAXY_CAPTURE_OBSERVATIONS_MISMATCH",
        "Galaxy selected before/after observations do not match captured exchanges.",
    )
    _validate_entity_id_templates(
        observations["after"],
        AFTER_OBSERVATION_ENTITY_ID_TEMPLATES,
        entity_ids=entity_ids,
        label="after observation",
    )

    staramr = raw.get("staramr_execution")
    _require(
        type(staramr) is dict
        and staramr.get("status") == "unsupported"
        and staramr.get("import_attempted") is False
        and staramr.get("invocation_attempted") is False
        and len(staramr.get("missing_required_tools", [])) == 5
        and [item.get("status") for item in staramr.get("exact_tool_checks", [])]
        == [404, 404, 404, 404, 404],
        "GALAXY_CAPTURE_STARAMR_BOUNDARY_MISMATCH",
        "Galaxy capture must retain the fail-closed unsupported StarAMR boundary.",
    )
    purge = _exchange_by_step(raw, "purge_history")["response"]
    _require(
        purge.get("status_code") == 200
        and purge.get("body", {}).get("deleted") is True
        and purge.get("body", {}).get("purged") is True,
        "GALAXY_CAPTURE_PURGE_MISMATCH",
        "Galaxy capture must retain successful history purge.",
    )


def _validate_exchange_payloads(exchange: dict[str, Any]) -> None:
    request = exchange.get("request")
    response = exchange.get("response")
    _require(
        type(request) is dict and type(response) is dict,
        "GALAXY_CAPTURE_EXCHANGE_SHAPE_INVALID",
        "Galaxy exchange must contain request and response objects.",
        step_id=exchange.get("step_id"),
    )
    _validate_payload_record(
        request,
        label=f"{exchange['step_id']} request",
        empty_body_allowed=True,
    )
    _validate_payload_record(
        response,
        label=f"{exchange['step_id']} response",
        empty_body_allowed=False,
    )
    _require(
        type(response.get("status_code")) is int
        and 100 <= response["status_code"] <= 599,
        "GALAXY_CAPTURE_RESPONSE_STATUS_INVALID",
        "Galaxy captured response status is invalid.",
        step_id=exchange.get("step_id"),
    )


def _validate_payload_record(
    record: dict[str, Any],
    *,
    label: str,
    empty_body_allowed: bool,
) -> None:
    body_bytes = record.get("body_bytes")
    body_sha256 = record.get("body_sha256")
    _require(
        type(body_bytes) is int and body_bytes >= 0 and _is_sha256(body_sha256),
        "GALAXY_CAPTURE_PAYLOAD_METADATA_INVALID",
        f"{label} payload metadata is invalid.",
    )
    encoded = record.get("body_base64")
    if encoded is None:
        _require(
            empty_body_allowed
            and body_bytes == 0
            and body_sha256 == _sha256(b"")
            and record.get("body") is None,
            "GALAXY_CAPTURE_PAYLOAD_BYTES_MISSING",
            f"{label} is missing captured payload bytes.",
        )
        return
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as error:
        raise CaptureContractError(
            "GALAXY_CAPTURE_PAYLOAD_BASE64_INVALID",
            f"{label} body_base64 is invalid.",
        ) from error
    _require(
        len(decoded) == body_bytes and _sha256(decoded) == body_sha256,
        "GALAXY_CAPTURE_PAYLOAD_DIGEST_MISMATCH",
        f"{label} decoded bytes do not match retained size and digest.",
    )
    kind = record.get("body_kind")
    if kind == "json":
        try:
            decoded_body = json.loads(decoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CaptureContractError(
                "GALAXY_CAPTURE_PAYLOAD_JSON_INVALID",
                f"{label} captured bytes are not valid UTF-8 JSON.",
            ) from error
        _require(
            _json_exact(decoded_body, record.get("body")),
            "GALAXY_CAPTURE_PAYLOAD_BODY_MISMATCH",
            f"{label} parsed body does not match captured bytes.",
        )
    elif kind in {"text", "bytes"}:
        _require(
            decoded.decode("utf-8") == record.get("body"),
            "GALAXY_CAPTURE_PAYLOAD_BODY_MISMATCH",
            f"{label} text body does not match captured bytes.",
        )
    else:
        _require(
            False,
            "GALAXY_CAPTURE_PAYLOAD_KIND_INVALID",
            f"{label} body kind is not supported.",
            body_kind=kind,
        )


def _exchange_by_step(raw: dict[str, Any], step_id: str) -> dict[str, Any]:
    matches = [
        exchange
        for exchange in raw["exchanges"]
        if type(exchange) is dict and exchange.get("step_id") == step_id
    ]
    _require(
        len(matches) == 1,
        "GALAXY_CAPTURE_STEP_CARDINALITY_MISMATCH",
        "Galaxy capture step must occur exactly once.",
        step_id=step_id,
        count=len(matches),
    )
    return matches[0]


def _validate_entity_id_templates(
    value: Any,
    templates: tuple[tuple[str, str], ...],
    *,
    entity_ids: dict[str, Any],
    label: str,
) -> None:
    for pointer, template in templates:
        actual = _pointer_get(value, pointer)
        expected = template.format(**entity_ids)
        _require(
            actual == expected,
            "GALAXY_CAPTURE_ENTITY_BINDING_MISMATCH",
            f"Galaxy {label} does not preserve its semantic entity binding.",
            pointer=pointer,
            expected=expected,
            actual=actual,
        )


def _pointer_get(value: Any, pointer: str) -> Any:
    current = value
    for component in pointer[1:].split("/"):
        if type(current) is dict:
            current = current[component]
        elif type(current) is list:
            current = current[int(component)]
        else:
            _require(
                False,
                "GALAXY_CAPTURE_ENTITY_POINTER_INVALID",
                "Galaxy entity pointer does not resolve through JSON containers.",
                pointer=pointer,
            )
    return current


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaptureContractError(
            "GALAXY_CAPTURE_AUXILIARY_JSON_INVALID",
            f"Galaxy {label} must be readable UTF-8 JSON.",
            details={"path": str(path)},
        ) from error
    _require(
        type(value) is dict,
        "GALAXY_CAPTURE_AUXILIARY_ROOT_INVALID",
        f"Galaxy {label} must be a JSON object.",
        path=str(path),
    )
    return value


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


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _is_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _is_opaque_id(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 16
        and all(character in "0123456789abcdef" for character in value)
    )


def _require(
    condition: bool,
    code: str,
    message: str,
    **details: Any,
) -> None:
    if not condition:
        raise CaptureContractError(code, message, details=details)
