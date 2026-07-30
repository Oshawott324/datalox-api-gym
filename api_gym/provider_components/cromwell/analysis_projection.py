"""Capture-derived Cromwell 92 program facts for bounded analysis worlds."""

from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

PROVIDER_VERSION = "92"
FACTS_SCHEMA_VERSION = "api_gym.cromwell_analysis_projection_facts.v1"
WORKFLOW_ID_TOKEN = "__WORKFLOW_ID__"
_PROGRAMS = ("abort", "failure", "success")
_TERMINAL_STATUS = {
    "abort": "Aborted",
    "failure": "Failed",
    "success": "Succeeded",
}
_CASE_NAME = {
    "abort": "workflow_abort_v1",
    "failure": "workflow_failure_v1",
    "success": "workflow_success_v1",
}
_ARTIFACT_NAMES = {
    "abort": ("abort.wdl", "abort.inputs.json"),
    "failure": ("failure.wdl", "failure.inputs.json"),
    "success": ("success.wdl", "success.inputs.json"),
}
_EXPECTED_CAPTURE_DIGESTS = {
    "abort": "sha256:14a8382eb9a80e2adc8e089543cd80a235b3fe1566bd096f61c2ed83bcf759e0",
    "failure": "sha256:b726575994bf7b16a53ff39bf0bf1ea48a5c7138ea2c1fa1142d902b71282298",
    "success": "sha256:13b94e8644fadd859202af40cf1f48930de75d24e1576517c6d2122b638014ec",
}
_PROVIDER_STATUSES = (
    "Aborted",
    "Aborting",
    "Failed",
    "Running",
    "Submitted",
    "Succeeded",
)


class CromwellAnalysisProjectionError(RuntimeError):
    """The selected request or data is outside the captured Cromwell families."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def deterministic_workflow_id(*, seed: int, ordinal: int) -> str:
    if type(seed) is not int or type(ordinal) is not int or ordinal < 0:
        raise CromwellAnalysisProjectionError(
            "CROMWELL_WORKFLOW_ID_INPUT_INVALID",
            "seed and non-negative ordinal must be integers",
        )
    namespace = uuid.UUID("deccf199-5103-4cb6-bb4f-9d11436ab589")
    return str(uuid.uuid5(namespace, f"science-cromwell:{seed}:{ordinal}"))


def build_capture_facts(cases_root: Path | None = None) -> dict[str, Any]:
    root = cases_root or (
        Path(__file__).resolve().parents[3]
        / "source_packs"
        / "apis"
        / "cromwell"
        / "2026-07-30"
        / "behavior_cases"
    )
    programs: dict[str, Any] = {}
    grounding_cases: dict[str, Any] = {}
    transient_template: dict[str, Any] | None = None
    status_templates: dict[str, Any] = {}
    submit_template: dict[str, Any] | None = None
    abort_templates: dict[str, Any] = {}

    for program in _PROGRAMS:
        case_root = root / _CASE_NAME[program]
        metadata = _read_object(case_root / "case_metadata.json")
        if (
            metadata.get("provider_id") != "cromwell"
            or metadata.get("provider_version") != PROVIDER_VERSION
        ):
            _invalid_facts(f"{program} case metadata identity is invalid")
        digests = metadata.get("digests")
        if not isinstance(digests, dict):
            _invalid_facts(f"{program} case metadata digests are missing")
        workflow_name, inputs_name = _ARTIFACT_NAMES[program]
        for key, filename in (
            ("capture", "capture.json"),
            ("connector", "connector.json"),
            ("fixture_receipt", "fixture_receipt.json"),
            ("inputs", inputs_name),
            ("recipe", "recipe.json"),
            ("workflow", workflow_name),
        ):
            expected = digests.get(key)
            if not isinstance(expected, str):
                _invalid_facts(f"{program} digest {key!r} is missing")
            _require_digest(case_root / filename, expected)
        capture = _read_object(case_root / "capture.json")
        receipt = _read_object(case_root / "fixture_receipt.json")
        grouped = _exchanges_by_step(capture)
        captured_id = str(capture["bindings"]["primary_workflow_id"])
        disposable_root = str(receipt["paths"]["disposable_root"])
        outputs = _terminal_response(grouped, "primary_outputs")
        logs = _terminal_response(grouped, "primary_logs")
        metadata_body = _terminal_response(grouped, "primary_metadata")
        programs[program] = {
            "case_name": _CASE_NAME[program],
            "capture_sha256": digests["capture"],
            "workflow_sha256": digests["workflow"],
            "inputs_sha256": digests["inputs"],
            "workflow_source": (case_root / workflow_name).read_text(
                encoding="utf-8"
            ),
            "workflow_inputs": json.loads(
                (case_root / inputs_name).read_text(encoding="utf-8")
            ),
            "terminal_status": _TERMINAL_STATUS[program],
            "outputs_template": _normalize_template(
                outputs["body"],
                captured_id=captured_id,
                disposable_root=disposable_root,
            ),
            "logs_template": _normalize_template(
                logs["body"],
                captured_id=captured_id,
                disposable_root=disposable_root,
            ),
            "metadata_template": _normalize_template(
                metadata_body["body"],
                captured_id=captured_id,
                disposable_root=disposable_root,
            ),
        }
        grounding_cases[program] = {
            "program_id": metadata["program_id"],
            "capture_sha256": digests["capture"],
            "connector_sha256": digests["connector"],
            "recipe_sha256": digests["recipe"],
            "fixture_receipt_sha256": digests["fixture_receipt"],
            "production_equivalence": "not_claimed",
            "reset_equivalence": "not_claimed",
        }

        for exchanges in grouped.values():
            for exchange in exchanges:
                response = exchange.get("response", {})
                body = response.get("body") if isinstance(response, dict) else None
                if not isinstance(body, dict):
                    continue
                status = body.get("status")
                if response.get("status_code") == 404 and status == "fail":
                    transient_template = _normalize_template(
                        body,
                        captured_id=captured_id,
                        disposable_root=disposable_root,
                    )
                if (
                    response.get("status_code") == 200
                    and status in _PROVIDER_STATUSES
                    and set(body) == {"id", "status"}
                ):
                    normalized_status = _normalize_template(
                        body,
                        captured_id=captured_id,
                        disposable_root=disposable_root,
                    )
                    normalized_status["id"] = WORKFLOW_ID_TOKEN
                    status_templates[str(status)] = normalized_status
        if submit_template is None:
            submit = _terminal_response(grouped, "submit_primary")
            submit_template = _normalize_template(
                submit["body"],
                captured_id=captured_id,
                disposable_root=disposable_root,
            )
        if program == "abort":
            abort_templates["success"] = _normalize_template(
                _terminal_response(grouped, "abort_primary")["body"],
                captured_id=captured_id,
                disposable_root=disposable_root,
            )
            abort_templates["not_in_progress"] = _normalize_template(
                _terminal_response(grouped, "abort_unknown_workflow")["body"],
                captured_id="00000000-0000-0000-0000-000000000000",
                disposable_root=disposable_root,
            )

    if transient_template is None or submit_template is None:
        _invalid_facts("captured status or submit templates are missing")
    facts = {
        "schema_version": FACTS_SCHEMA_VERSION,
        "provider_version": PROVIDER_VERSION,
        "provider_statuses": list(_PROVIDER_STATUSES),
        "grounding": {
            "grounding_level": "G2_LOCAL_EXECUTED",
            "cases": grounding_cases,
            "projection": "captured_program_families_only",
        },
        "projection": {
            "dynamic_timestamps": "G0_BENCHMARK_DEFINED",
            "provider_response_shape": "G2_LOCAL_EXECUTED",
        },
        "submit": {"status_code": 201, "body_template": submit_template},
        "status": {
            "success_status_code": 200,
            "transient_status_code": 404,
            "transient_template": transient_template,
            "body_templates": status_templates,
        },
        "abort": {
            "success_status_code": 200,
            "not_in_progress_status_code": 404,
            "body_templates": abort_templates,
        },
        "programs": programs,
    }
    validate_capture_facts(facts)
    return facts


def validate_capture_facts(facts: Mapping[str, Any]) -> None:
    try:
        programs = facts["programs"]
        grounding_cases = facts["grounding"]["cases"]
        projection = facts["projection"]
        valid = (
            facts["schema_version"] == FACTS_SCHEMA_VERSION
            and facts["provider_version"] == PROVIDER_VERSION
            and facts["provider_statuses"] == list(_PROVIDER_STATUSES)
            and set(programs) == set(_PROGRAMS)
            and set(grounding_cases) == set(_PROGRAMS)
            and projection
            == {
                "dynamic_timestamps": "G0_BENCHMARK_DEFINED",
                "provider_response_shape": "G2_LOCAL_EXECUTED",
            }
            and facts["submit"]["status_code"] == 201
            and facts["submit"]["body_template"]["status"] == "Submitted"
            and facts["status"]["success_status_code"] == 200
            and facts["status"]["transient_status_code"] == 404
            and facts["abort"]["success_status_code"] == 200
            and facts["abort"]["not_in_progress_status_code"] == 404
        )
        for program in _PROGRAMS:
            item = programs[program]
            workflow_digest = (
                "sha256:"
                + hashlib.sha256(item["workflow_source"].encode("utf-8")).hexdigest()
            )
            inputs_bytes = (
                json.dumps(
                    item["workflow_inputs"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
            valid = (
                valid
                and item["terminal_status"] == _TERMINAL_STATUS[program]
                and item["capture_sha256"] == _EXPECTED_CAPTURE_DIGESTS[program]
                and isinstance(item["workflow_inputs"], dict)
                and item["outputs_template"]["id"] == WORKFLOW_ID_TOKEN
                and item["logs_template"]["id"] == WORKFLOW_ID_TOKEN
                and item["metadata_template"]["id"] == WORKFLOW_ID_TOKEN
                and item["metadata_template"]["status"]
                == _TERMINAL_STATUS[program]
                and workflow_digest == item["workflow_sha256"]
                and f"sha256:{hashlib.sha256(inputs_bytes).hexdigest()}"
                == item["inputs_sha256"]
            )
        valid = valid and "/tmp/" not in json.dumps(facts, sort_keys=True)
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        _invalid_facts("capture-derived Cromwell facts do not match admitted cases")


def classify_program(
    facts: Mapping[str, Any],
    workflow_source: str,
    workflow_inputs: Mapping[str, Any],
) -> str:
    validate_capture_facts(facts)
    if type(workflow_source) is not str or not isinstance(workflow_inputs, Mapping):
        raise CromwellAnalysisProjectionError(
            "CROMWELL_PROGRAM_NOT_ADMITTED",
            "workflowSource must be a string and workflowInputs must be an object",
        )
    for program in _PROGRAMS:
        selected = facts["programs"][program]
        if (
            workflow_source == selected["workflow_source"]
            and dict(workflow_inputs) == selected["workflow_inputs"]
        ):
            return program
    raise CromwellAnalysisProjectionError(
        "CROMWELL_PROGRAM_NOT_ADMITTED",
        "only the checked success, failure, and abort WDL/input families are admitted",
    )


def render_submit_response(
    facts: Mapping[str, Any],
    workflow_id: str,
) -> dict[str, Any]:
    validate_capture_facts(facts)
    _require_uuid(workflow_id)
    return _render(facts["submit"]["body_template"], workflow_id)


def render_status(
    facts: Mapping[str, Any],
    *,
    workflow_id: str,
    provider_status: str | None,
) -> tuple[int, dict[str, Any]]:
    validate_capture_facts(facts)
    _require_uuid(workflow_id)
    if provider_status is None:
        return (
            int(facts["status"]["transient_status_code"]),
            _render(facts["status"]["transient_template"], workflow_id),
        )
    if provider_status not in _PROVIDER_STATUSES:
        raise CromwellAnalysisProjectionError(
            "CROMWELL_STATUS_NOT_CAPTURED",
            f"provider status is outside checked cases: {provider_status!r}",
        )
    template = facts["status"]["body_templates"].get(provider_status)
    if not isinstance(template, Mapping):
        template = {"id": WORKFLOW_ID_TOKEN, "status": provider_status}
    return int(facts["status"]["success_status_code"]), _render(
        template, workflow_id
    )


def render_abort_response(
    facts: Mapping[str, Any],
    *,
    workflow_id: str,
    provider_status: str | None,
) -> tuple[int, dict[str, Any]]:
    validate_capture_facts(facts)
    _require_uuid(workflow_id)
    if provider_status in {"Running", "Aborting"}:
        return (
            int(facts["abort"]["success_status_code"]),
            _render(facts["abort"]["body_templates"]["success"], workflow_id),
        )
    return (
        int(facts["abort"]["not_in_progress_status_code"]),
        _render(
            facts["abort"]["body_templates"]["not_in_progress"],
            workflow_id,
        ),
    )


def render_outputs(
    facts: Mapping[str, Any],
    program: str,
    workflow_id: str,
) -> dict[str, Any]:
    return _render_program_template(facts, program, "outputs_template", workflow_id)


def render_logs(
    facts: Mapping[str, Any],
    program: str,
    workflow_id: str,
) -> dict[str, Any]:
    return _render_program_template(facts, program, "logs_template", workflow_id)


def render_metadata(
    facts: Mapping[str, Any],
    program: str,
    workflow_id: str,
    *,
    projected_timing: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    rendered = _render_program_template(
        facts,
        program,
        "metadata_template",
        workflow_id,
    )
    if projected_timing is not None:
        rendered = _project_metadata_timestamps(rendered, projected_timing)
    return rendered


def _render_program_template(
    facts: Mapping[str, Any],
    program: str,
    template_name: str,
    workflow_id: str,
) -> dict[str, Any]:
    validate_capture_facts(facts)
    _require_uuid(workflow_id)
    if program not in _PROGRAMS:
        raise CromwellAnalysisProjectionError(
            "CROMWELL_PROGRAM_NOT_ADMITTED",
            f"program is outside checked cases: {program!r}",
        )
    return _render(facts["programs"][program][template_name], workflow_id)


def _normalize_template(
    value: Any,
    *,
    captured_id: str,
    disposable_root: str,
) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_template(
                item,
                captured_id=captured_id,
                disposable_root=disposable_root,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _normalize_template(
                item,
                captured_id=captured_id,
                disposable_root=disposable_root,
            )
            for item in value
        ]
    if isinstance(value, str):
        return value.replace(disposable_root, "datalox-world://cromwell").replace(
            captured_id,
            WORKFLOW_ID_TOKEN,
        )
    return value


def _render(value: Mapping[str, Any], workflow_id: str) -> dict[str, Any]:
    rendered = _replace_token(deepcopy(dict(value)), workflow_id)
    if not isinstance(rendered, dict):
        raise AssertionError("rendered provider response must be an object")
    return rendered


def _replace_token(value: Any, workflow_id: str) -> Any:
    if isinstance(value, dict):
        return {key: _replace_token(item, workflow_id) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_token(item, workflow_id) for item in value]
    if isinstance(value, str):
        return value.replace(WORKFLOW_ID_TOKEN, workflow_id)
    return value


def _project_metadata_timestamps(
    metadata: Mapping[str, Any],
    projected_timing: Mapping[str, str],
) -> dict[str, Any]:
    required = {"submitted_at", "started_at", "ended_at"}
    if set(projected_timing) != required:
        raise CromwellAnalysisProjectionError(
            "CROMWELL_PROJECTED_TIMING_INVALID",
            "projected timing requires submitted_at, started_at, and ended_at",
        )
    captured_submission = _parse_timestamp(str(metadata["submission"]))
    captured_end = _parse_timestamp(str(metadata["end"]))
    projected_submission = _parse_timestamp(projected_timing["submitted_at"])
    projected_start = _parse_timestamp(projected_timing["started_at"])
    projected_end = _parse_timestamp(projected_timing["ended_at"])
    if not (
        captured_submission < captured_end
        and projected_submission <= projected_start <= projected_end
    ):
        raise CromwellAnalysisProjectionError(
            "CROMWELL_PROJECTED_TIMING_INVALID",
            "projected timing must be ordered",
        )
    captured_span = (captured_end - captured_submission).total_seconds()
    projected_span = (projected_end - projected_submission).total_seconds()

    def replace(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        if not isinstance(value, str):
            return value
        try:
            captured = _parse_timestamp(value)
        except ValueError:
            return value
        ratio = (captured - captured_submission).total_seconds() / captured_span
        projected = projected_submission + timedelta(seconds=projected_span * ratio)
        return _format_timestamp(projected)

    rendered = replace(deepcopy(dict(metadata)))
    rendered["submission"] = _format_timestamp(projected_submission)
    rendered["start"] = _format_timestamp(projected_start)
    rendered["end"] = _format_timestamp(projected_end)
    return rendered


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00",
        "Z",
    )


def _terminal_response(
    grouped: Mapping[str, list[dict[str, Any]]],
    step_id: str,
) -> dict[str, Any]:
    try:
        response = grouped[step_id][-1]["response"]
    except (KeyError, IndexError, TypeError):
        _invalid_facts(f"capture is missing terminal response for {step_id}")
    if not isinstance(response, dict) or not isinstance(response.get("body"), dict):
        _invalid_facts(f"terminal response for {step_id} is not a JSON object")
    return response


def _exchanges_by_step(capture: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    exchanges = capture.get("exchanges")
    if not isinstance(exchanges, list):
        _invalid_facts("capture exchanges are missing")
    for exchange in exchanges:
        if not isinstance(exchange, dict) or not isinstance(
            exchange.get("step_id"), str
        ):
            _invalid_facts("capture exchange is invalid")
        grouped.setdefault(exchange["step_id"], []).append(exchange)
    return grouped


def _require_uuid(workflow_id: str) -> None:
    if type(workflow_id) is not str:
        raise CromwellAnalysisProjectionError(
            "CROMWELL_WORKFLOW_ID_INVALID",
            "workflow id must use canonical UUID syntax",
        )
    try:
        parsed = uuid.UUID(workflow_id)
    except ValueError as error:
        raise CromwellAnalysisProjectionError(
            "CROMWELL_WORKFLOW_ID_INVALID",
            "workflow id must use canonical UUID syntax",
        ) from error
    if str(parsed) != workflow_id:
        raise CromwellAnalysisProjectionError(
            "CROMWELL_WORKFLOW_ID_INVALID",
            "workflow id must use canonical UUID syntax",
        )


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _invalid_facts(f"could not read checked artifact {path.name}: {error}")
    if not isinstance(value, dict):
        _invalid_facts(f"checked artifact {path.name} is not an object")
    return value


def _require_digest(path: Path, expected: str) -> None:
    try:
        actual = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    except OSError as error:
        _invalid_facts(f"could not read checked artifact {path.name}: {error}")
    if actual != expected:
        _invalid_facts(
            f"checked artifact {path.name} digest mismatch: {actual} != {expected}"
        )


def _invalid_facts(message: str) -> None:
    raise CromwellAnalysisProjectionError(
        "CROMWELL_CAPTURE_FACTS_INVALID",
        message,
    )
