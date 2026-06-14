"""Filesystem-backed response gate lookup over API source packs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACKS_ROOT = PROJECT_ROOT / "source_packs" / "apis"


class SourcePackGateError(ValueError):
    """Stable, agent-readable source-pack gate lookup error."""

    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def __str__(self) -> str:
        return self.message


def list_providers(*, repo_root: Path | None = None) -> list[str]:
    """List providers with checked-in API source packs."""
    source_packs_root = _source_packs_root(repo_root)
    if not source_packs_root.exists() or not source_packs_root.is_dir():
        raise SourcePackGateError(
            "source_pack_gate_root_not_found",
            "API source-pack root does not exist.",
            {"path": str(source_packs_root)},
        )
    return sorted(path.name for path in source_packs_root.iterdir() if path.is_dir())


def find_operation(
    provider: str,
    method: str,
    path: str,
    version: str | None = None,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Find one operation by provider, method, and exact or templated path."""
    provider_root = _provider_root(provider, repo_root)
    pack_root = _pack_root(provider_root, provider, version)
    operations = _read_named_record(pack_root, "operations")
    method_upper = method.upper()

    exact_matches = [
        operation
        for operation in operations
        if operation.get("method") == method_upper and operation.get("path") == path
    ]
    if exact_matches:
        return _single_match(exact_matches, "source_pack_gate_operation_ambiguous", provider, method_upper, path)

    template_matches = [
        operation
        for operation in operations
        if operation.get("method") == method_upper
        and isinstance(operation.get("path"), str)
        and _path_template_matches(operation["path"], path)
    ]
    if template_matches:
        return _single_match(template_matches, "source_pack_gate_operation_ambiguous", provider, method_upper, path)

    raise SourcePackGateError(
        "source_pack_gate_operation_not_found",
        "No source-pack operation matches the provider, method, and path.",
        {"provider": provider, "method": method_upper, "path": path, "version": pack_root.name},
    )


def list_response_cases(
    provider: str,
    operation_ref: str,
    version: str | None = None,
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """List response cases for one operation reference."""
    provider_root = _provider_root(provider, repo_root)
    pack_root = _pack_root(provider_root, provider, version)
    cases = [
        row
        for row in _read_named_record(pack_root, "response_cases")
        if row.get("operation_ref") == operation_ref
    ]
    if not cases:
        raise SourcePackGateError(
            "source_pack_gate_response_cases_not_found",
            "No source-pack response cases match the operation reference.",
            {"provider": provider, "operation_ref": operation_ref, "version": pack_root.name},
        )
    return cases


def choose_response_case(
    provider: str,
    operation_ref: str,
    case: str = "success",
    version: str | None = None,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Choose a deterministic response case for one operation."""
    matches = [
        response_case
        for response_case in list_response_cases(provider, operation_ref, version, repo_root=repo_root)
        if response_case.get("case") == case
    ]
    if not matches:
        raise SourcePackGateError(
            "source_pack_gate_response_case_not_found",
            "No source-pack response case matches the requested case.",
            {"provider": provider, "operation_ref": operation_ref, "case": case, "version": version},
        )
    return sorted(matches, key=lambda row: str(row.get("id", "")))[0]


def build_gate_response(response_case: dict[str, Any]) -> dict[str, Any]:
    """Build the agent-visible response gate payload from a source response case."""
    if "status" not in response_case:
        raise SourcePackGateError(
            "source_pack_gate_response_status_missing",
            "Response case must include status.",
            {"response_case_id": response_case.get("id", "")},
        )
    response_mode = response_case.get("response_mode")
    if not isinstance(response_mode, str) or not response_mode:
        raise SourcePackGateError(
            "source_pack_gate_response_mode_missing",
            "Response case must include response_mode.",
            {"response_case_id": response_case.get("id", "")},
        )

    gate_response = {
        "status": response_case["status"],
        "response_mode": response_mode,
    }
    for key in ("body", "body_excerpt", "body_shape", "error_shape", "headers", "gating_notes"):
        if key in response_case:
            gate_response[key] = response_case[key]
    return gate_response


def _source_packs_root(repo_root: Path | None) -> Path:
    return (repo_root or PROJECT_ROOT) / "source_packs" / "apis"


def _provider_root(provider: str, repo_root: Path | None) -> Path:
    _validate_path_segment(provider, "provider")
    provider_root = _source_packs_root(repo_root) / provider
    if not provider_root.exists() or not provider_root.is_dir():
        raise SourcePackGateError(
            "source_pack_gate_provider_not_found",
            "Provider source pack does not exist.",
            {"provider": provider, "path": str(provider_root)},
        )
    return provider_root


def _pack_root(provider_root: Path, provider: str, version: str | None) -> Path:
    if version is not None:
        _validate_path_segment(version, "version")
        pack_root = provider_root / version
        if not pack_root.exists() or not pack_root.is_dir():
            raise SourcePackGateError(
                "source_pack_gate_version_not_found",
                "Provider source-pack version does not exist.",
                {"provider": provider, "version": version, "path": str(pack_root)},
            )
        return pack_root

    versions = sorted(path for path in provider_root.iterdir() if path.is_dir())
    if not versions:
        raise SourcePackGateError(
            "source_pack_gate_version_not_found",
            "Provider has no source-pack versions.",
            {"provider": provider, "path": str(provider_root)},
        )
    if len(versions) > 1:
        raise SourcePackGateError(
            "source_pack_gate_version_required",
            "Provider has multiple source-pack versions; pass version explicitly.",
            {"provider": provider, "versions": [path.name for path in versions]},
        )
    return versions[0]


def _validate_path_segment(value: str, segment_name: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise SourcePackGateError(
            "source_pack_gate_path_segment_invalid",
            "Source-pack path segment must be a non-empty provider or version id without path separators.",
            {"segment_name": segment_name, "segment_value": value},
        )


def _read_named_record(pack_root: Path, record_name: str) -> list[dict[str, Any]]:
    source_pack_path = pack_root / "source_pack.json"
    source_pack = _read_json_object(source_pack_path, "source_pack_gate_source_pack_invalid_json")
    records = source_pack.get("records")
    if not isinstance(records, dict):
        raise SourcePackGateError(
            "source_pack_gate_records_invalid",
            "Source pack records must be an object.",
            {"path": str(source_pack_path)},
        )
    rel_path = records.get(record_name)
    if not isinstance(rel_path, str) or not rel_path:
        raise SourcePackGateError(
            "source_pack_gate_record_missing",
            "Source pack does not define the requested record file.",
            {"path": str(source_pack_path), "record": record_name},
        )
    record_path = _resolve_child(pack_root, rel_path, source_pack_path)
    return _read_jsonl_objects(record_path)


def _read_json_object(path: Path, code: str) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise SourcePackGateError(
            "source_pack_gate_file_missing",
            "Source-pack file does not exist.",
            {"path": str(path)},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourcePackGateError(
            code,
            f"Invalid JSON in {path}: {exc}",
            {"path": str(path), "line": exc.lineno},
        ) from exc
    if not isinstance(payload, dict):
        raise SourcePackGateError(code, "JSON file must contain an object.", {"path": str(path)})
    return payload


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        raise SourcePackGateError(
            "source_pack_gate_record_file_missing",
            "Source-pack record file does not exist.",
            {"path": str(path)},
        )
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SourcePackGateError(
                "source_pack_gate_record_invalid_jsonl",
                f"Invalid JSONL row in {path}: {exc}",
                {"path": str(path), "line": line_number},
            ) from exc
        if not isinstance(row, dict):
            raise SourcePackGateError(
                "source_pack_gate_record_row_not_object",
                "Source-pack record rows must be objects.",
                {"path": str(path), "line": line_number},
            )
        rows.append(row)
    return rows


def _resolve_child(root: Path, rel_path: str, source_path: Path) -> Path:
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise SourcePackGateError(
            "source_pack_gate_path_escape",
            "Source-pack record path must stay inside the source-pack directory.",
            {"path": str(source_path), "record_path": rel_path},
        ) from exc
    return candidate


def _single_match(
    matches: list[dict[str, Any]],
    code: str,
    provider: str,
    method: str,
    path: str,
) -> dict[str, Any]:
    if len(matches) == 1:
        return matches[0]
    raise SourcePackGateError(
        code,
        "Multiple source-pack operations match the provider, method, and path.",
        {
            "provider": provider,
            "method": method,
            "path": path,
            "operation_refs": [str(match.get("id", "")) for match in matches],
        },
    )


def _path_template_matches(template: str, path: str) -> bool:
    template_segments = _path_segments(template)
    path_segments = _path_segments(path)
    if len(template_segments) != len(path_segments):
        return False
    return all(
        _is_template_segment(template_segment) or template_segment == path_segment
        for template_segment, path_segment in zip(template_segments, path_segments)
    )


def _path_segments(path: str) -> list[str]:
    return path.strip("/").split("/") if path != "/" else []


def _is_template_segment(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}") and len(segment) > 2
