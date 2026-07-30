"""Capture-derived eLabFTW shapes reused by analysis-handoff worlds."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PROVIDER_VERSION = "5.6.10"
PROGRAM_ID = "elabftw_experiments_patch_complete_v1"
FACTS_SCHEMA_VERSION = "api_gym.elabftw_analysis_projection_facts.v1"
_PATCH_FIELDS = frozenset({"body", "metadata", "title"})
_EXPECTED_CAPTURE_SHA256 = (
    "sha256:f83ba0c58a078c332064e16f629084b8dcd7e341ef3d2861e2ff974790e6eca6"
)
_EXPECTED_LIST_BODY_SHA256 = (
    "sha256:cd0094f808a31b8f9452d55ec302ee7da95117cffefdf039efe1aa726b967796"
)


class ELabFTWAnalysisProjectionError(RuntimeError):
    """The selected capture or projected operation is outside the admitted case."""

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


def deterministic_experiment_id(*, seed: int, ordinal: int) -> int:
    if type(seed) is not int or type(ordinal) is not int or ordinal < 0:
        raise ELabFTWAnalysisProjectionError(
            "ELABFTW_EXPERIMENT_ID_INPUT_INVALID",
            "seed and non-negative ordinal must be integers",
        )
    digest = hashlib.sha256(
        f"science-elabftw:{seed}:experiment:{ordinal}".encode("ascii")
    ).digest()
    return 100_000 + int.from_bytes(digest[:8], "big") % 900_000


def build_capture_facts(case_root: Path | None = None) -> dict[str, Any]:
    root = case_root or (
        Path(__file__).resolve().parents[3]
        / "source_packs"
        / "apis"
        / "elabftw"
        / "2026-07-30"
        / "behavior_cases"
        / "experiments_patch_complete_v1"
    )
    metadata = _read_object(root / "case_metadata.json")
    if (
        metadata.get("provider_id") != "elabftw"
        or metadata.get("provider_version") != PROVIDER_VERSION
        or metadata.get("program_id") != PROGRAM_ID
    ):
        _invalid_facts("case metadata identity does not match the admitted program")
    digests = metadata.get("digests")
    if not isinstance(digests, dict):
        _invalid_facts("case metadata digests are missing")
    for key, filename in (
        ("capture", "capture.json"),
        ("connector", "connector.json"),
        ("fixture_receipt", "fixture_receipt.json"),
        ("recipe", "recipe.json"),
    ):
        expected = digests.get(key)
        if not isinstance(expected, str):
            _invalid_facts(f"case metadata digest {key!r} is missing")
        _require_digest(root / filename, expected)

    capture = _read_object(root / "capture.json")
    recipe = _read_object(root / "recipe.json")
    exchanges = _exchanges_by_step(capture)
    create = exchanges["create_experiment"][-1]
    listed = exchanges["list_experiments"][-1]
    before = exchanges["before_experiment"][-1]
    patch = exchanges["patch_experiment"][-1]
    duplicate = exchanges["duplicate_patch"][-1]
    resulting = exchanges["resulting_experiment"][-1]
    steps = {
        step["step_id"]: step
        for step in recipe.get("steps", [])
        if isinstance(step, dict) and isinstance(step.get("step_id"), str)
    }
    patch_request = steps.get("patch_experiment", {}).get("request", {})
    patch_body = patch_request.get("body") if isinstance(patch_request, dict) else None
    if not isinstance(patch_body, dict):
        _invalid_facts("captured PATCH request body is missing")

    patched_template = deepcopy(patch["response"]["body"])
    if not isinstance(patched_template, dict):
        _invalid_facts("captured PATCH response is not an object")
    patched_template["captured_changelog_count"] = len(
        patched_template.get("changelog", [])
    )
    facts = {
        "schema_version": FACTS_SCHEMA_VERSION,
        "provider_version": PROVIDER_VERSION,
        "grounding": {
            "grounding_level": "G2_LOCAL_EXECUTED",
            "program_id": PROGRAM_ID,
            "capture_sha256": digests["capture"],
            "connector_sha256": digests["connector"],
            "recipe_sha256": digests["recipe"],
            "fixture_receipt_sha256": digests["fixture_receipt"],
            "production_equivalence": "not_claimed",
            "reset_equivalence": "not_claimed",
        },
        "projection": {
            "dynamic_changelog": "G0_BENCHMARK_DEFINED",
            "dynamic_links": "G0_BENCHMARK_DEFINED",
            "dynamic_timestamps": "G0_BENCHMARK_DEFINED",
            "provider_response_shape": "G2_LOCAL_EXECUTED",
        },
        "operations": {
            "create": {
                "status_code": create["response"]["status_code"],
                "body_kind": create["response"]["body_kind"],
                "request_fields": sorted(
                    create["request"]["body"]
                    if isinstance(create["request"].get("body"), dict)
                    else []
                ),
            },
            "get": {"status_code": resulting["response"]["status_code"]},
            "list": {
                "body_shape": (
                    "array"
                    if isinstance(listed["response"]["body"], list)
                    else "invalid"
                ),
                "body_sha256": listed["response"]["body_sha256"],
                "status_code": listed["response"]["status_code"],
            },
            "patch": {
                "status_code": patch["response"]["status_code"],
                "request_fields": sorted(patch_body),
            },
        },
        "response_headers": {
            "create": {
                "content-type": create["response"]["headers"]["content-type"],
                "location_template": "/api/v2/experiments/{experiment_id}",
            },
            "list": deepcopy(listed["response"]["headers"]),
            "get": deepcopy(before["response"]["headers"]),
            "patch": deepcopy(patch["response"]["headers"]),
        },
        "templates": {
            "before_experiment": deepcopy(before["response"]["body"]),
            "patched_experiment": patched_template,
            "duplicate_patch_changelog_delta": (
                len(duplicate["response"]["body"].get("changelog", []))
                - len(patch["response"]["body"].get("changelog", []))
            ),
        },
    }
    validate_capture_facts(facts)
    return facts


def validate_capture_facts(facts: Mapping[str, Any]) -> None:
    try:
        grounding = facts["grounding"]
        operations = facts["operations"]
        projection = facts["projection"]
        headers = facts["response_headers"]
        templates = facts["templates"]
        valid = (
            facts["schema_version"] == FACTS_SCHEMA_VERSION
            and facts["provider_version"] == PROVIDER_VERSION
            and grounding["program_id"] == PROGRAM_ID
            and grounding["capture_sha256"] == _EXPECTED_CAPTURE_SHA256
            and grounding["production_equivalence"] == "not_claimed"
            and projection
            == {
                "dynamic_changelog": "G0_BENCHMARK_DEFINED",
                "dynamic_links": "G0_BENCHMARK_DEFINED",
                "dynamic_timestamps": "G0_BENCHMARK_DEFINED",
                "provider_response_shape": "G2_LOCAL_EXECUTED",
            }
            and operations["create"]
            == {
                "body_kind": "empty",
                "request_fields": [],
                "status_code": 201,
            }
            and operations["get"] == {"status_code": 200}
            and operations["list"]
            == {
                "body_shape": "array",
                "body_sha256": _EXPECTED_LIST_BODY_SHA256,
                "status_code": 200,
            }
            and operations["patch"]
            == {
                "request_fields": ["body", "metadata", "title"],
                "status_code": 200,
            }
            and headers["create"]["content-type"]
            == "text/html; charset=UTF-8"
            and headers["create"]["location_template"]
            == "/api/v2/experiments/{experiment_id}"
            and headers["get"] == {"content-type": "application/json"}
            and headers["list"] == {"content-type": "application/json"}
            and headers["patch"] == {"content-type": "application/json"}
            and isinstance(templates["before_experiment"], dict)
            and isinstance(templates["patched_experiment"], dict)
            and templates["duplicate_patch_changelog_delta"] == 2
            and set(templates["patched_experiment"])
            >= {
                "body",
                "body_html",
                "captured_changelog_count",
                "changelog",
                "id",
                "metadata",
                "metadata_decoded",
                "state",
                "team",
                "title",
            }
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        _invalid_facts("capture-derived eLabFTW facts do not match the admitted case")


def validate_patch_body(
    facts: Mapping[str, Any],
    body: Mapping[str, Any],
) -> dict[str, Any]:
    validate_capture_facts(facts)
    if not isinstance(body, Mapping) or set(body) != _PATCH_FIELDS:
        raise ELabFTWAnalysisProjectionError(
            "ELABFTW_INVALID_PATCH_PAYLOAD",
            "captured PATCH accepts exactly title, body, and metadata",
        )
    if type(body["title"]) is not str or type(body["body"]) is not str:
        raise ELabFTWAnalysisProjectionError(
            "ELABFTW_INVALID_PATCH_PAYLOAD",
            "title and body must be strings",
        )
    if type(body["metadata"]) is not str:
        raise ELabFTWAnalysisProjectionError(
            "ELABFTW_METADATA_MUST_BE_JSON_STRING",
            "metadata must be a JSON string",
        )
    try:
        decoded = json.loads(body["metadata"])
    except json.JSONDecodeError as error:
        raise ELabFTWAnalysisProjectionError(
            "ELABFTW_INVALID_METADATA_JSON",
            f"metadata is not valid JSON at line {error.lineno} column {error.colno}",
        ) from error
    if type(decoded) is not dict:
        raise ELabFTWAnalysisProjectionError(
            "ELABFTW_INVALID_METADATA_SHAPE",
            "metadata must decode to an object",
        )
    return decoded


def render_create_response(
    facts: Mapping[str, Any],
    experiment_id: int,
) -> tuple[int, None, dict[str, str]]:
    validate_capture_facts(facts)
    if type(experiment_id) is not int or experiment_id <= 0:
        raise ELabFTWAnalysisProjectionError(
            "ELABFTW_EXPERIMENT_ID_INVALID",
            "experiment id must be a positive integer",
        )
    create = facts["operations"]["create"]
    headers = facts["response_headers"]["create"]
    return (
        int(create["status_code"]),
        None,
        {
            "content-type": str(headers["content-type"]),
            "location": str(headers["location_template"]).format(
                experiment_id=experiment_id
            ),
        },
    )


def render_experiment(
    facts: Mapping[str, Any],
    *,
    experiment_id: int,
    title: str,
    body: str,
    metadata: Mapping[str, Any],
    created_at: str,
    modified_at: str,
    changelog_repetitions: int = 0,
) -> dict[str, Any]:
    validate_capture_facts(facts)
    if (
        type(experiment_id) is not int
        or experiment_id <= 0
        or type(title) is not str
        or type(body) is not str
        or not isinstance(metadata, Mapping)
        or type(created_at) is not str
        or type(modified_at) is not str
        or type(changelog_repetitions) is not int
        or changelog_repetitions < 0
    ):
        raise ELabFTWAnalysisProjectionError(
            "ELABFTW_RECORD_RENDER_INVALID",
            "record fields do not match the projected provider shape",
        )
    template = deepcopy(facts["templates"]["patched_experiment"])
    captured_count = int(template.pop("captured_changelog_count"))
    template["id"] = experiment_id
    template["title"] = title
    template["body"] = body
    template["body_html"] = body
    template["metadata"] = json.dumps(
        dict(metadata),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    template["metadata_decoded"] = deepcopy(dict(metadata))
    created = _provider_timestamp(created_at)
    modified = _provider_timestamp(modified_at)
    template["created_at"] = created
    template["modified_at"] = modified
    template["sharelink"] = f"datalox-world://elabftw/experiments/{experiment_id}"
    captured_changelog = template.get("changelog")
    if not isinstance(captured_changelog, list):
        _invalid_facts("captured experiment changelog is not an array")
    actor = next(
        (
            entry
            for entry in captured_changelog
            if isinstance(entry, Mapping)
            and isinstance(entry.get("fullname"), str)
            and isinstance(entry.get("userid"), int)
        ),
        {"fullname": "Datalox Fixture", "userid": 2},
    )
    encoded_metadata = template["metadata"]
    changelog = [
        _changelog_entry(actor, target="body", content=body, created_at=modified),
        _changelog_entry(
            actor,
            target="metadata",
            content=encoded_metadata,
            created_at=modified,
        ),
        _changelog_entry(actor, target="title", content=title, created_at=modified),
        _changelog_entry(
            actor,
            target="created",
            content="Experiment was created",
            created_at=created,
        ),
    ]
    if changelog_repetitions % 2:
        raise ELabFTWAnalysisProjectionError(
            "ELABFTW_CHANGELOG_REPETITIONS_INVALID",
            "projected changelog repetitions must preserve body/title patch pairs",
        )
    for _ in range(changelog_repetitions // 2):
        changelog.extend(
            (
                _changelog_entry(
                    actor,
                    target="body",
                    content=body,
                    created_at=modified,
                ),
                _changelog_entry(
                    actor,
                    target="title",
                    content=title,
                    created_at=modified,
                ),
            )
        )
    if len(changelog) != captured_count + changelog_repetitions:
        _invalid_facts("captured experiment changelog count is inconsistent")
    template["changelog"] = changelog
    return template


def _provider_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ELabFTWAnalysisProjectionError(
            "ELABFTW_PROJECTED_TIMESTAMP_INVALID",
            "projected timestamps must be ISO-8601 values",
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _changelog_entry(
    actor: Mapping[str, Any],
    *,
    target: str,
    content: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "content": content,
        "created_at": created_at,
        "fullname": str(actor["fullname"]),
        "target": target,
        "userid": int(actor["userid"]),
    }


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
    required = {
        "before_experiment",
        "create_experiment",
        "duplicate_patch",
        "list_experiments",
        "patch_experiment",
        "resulting_experiment",
    }
    if not required.issubset(grouped):
        _invalid_facts("capture is missing required experiment steps")
    return grouped


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
    raise ELabFTWAnalysisProjectionError(
        "ELABFTW_CAPTURE_FACTS_INVALID",
        message,
    )
