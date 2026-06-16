"""Validation helpers for API source packs and world source references."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACK_SCHEMA_VERSION = "api_gym.api_source_pack.v0"
WORLD_SOURCE_REFS_SCHEMA_VERSION = "api_gym.world_source_refs.v0"
RESPONSE_CASE_PAYLOAD_FIELDS = ("body", "body_excerpt", "body_shape", "error_shape", "headers")
RESPONSE_CASE_RESPONSE_MODES = frozenset((*RESPONSE_CASE_PAYLOAD_FIELDS, "no_body"))


class SourcePackValidationError(ValueError):
    """Stable, agent-readable source-pack validation error."""

    def __init__(self, code: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def __str__(self) -> str:
        return self.message


def validate_source_pack(path: Path) -> dict[str, object]:
    """Validate one provider/version API source pack."""
    source_pack_path = _source_pack_path(path)
    pack_root = source_pack_path.parent
    pack = _read_json_object(source_pack_path, "source_pack_invalid_json")

    _require_equal(pack, "schema_version", SOURCE_PACK_SCHEMA_VERSION, source_pack_path)
    source_pack_id = _require_string(pack, "source_pack_id", source_pack_path)
    provider = _require_string(pack, "provider", source_pack_path)
    version = _require_string(pack, "version", source_pack_path)
    _require_nonempty_list(pack, "source_types", source_pack_path)

    records = pack.get("records")
    if not isinstance(records, dict) or not records:
        _raise("source_pack_records_invalid", "`records` must be a non-empty object.", source_pack_path)

    live_execution = pack.get("live_execution")
    if not isinstance(live_execution, dict) or live_execution.get("allowed") is not False:
        _raise("source_pack_live_execution_not_allowed", "`live_execution.allowed` must be false.", source_pack_path)

    operation_refs: set[str] = set()
    response_operation_refs: set[str] = set()
    response_cases_path: Path | None = None
    record_counts: dict[str, int] = {}
    record_ids: dict[str, tuple[Path, int]] = {}
    for record_name, rel_path_value in records.items():
        if not isinstance(record_name, str) or not isinstance(rel_path_value, str):
            _raise("source_pack_record_ref_invalid", "Record names and paths must be strings.", source_pack_path)
        record_path = _resolve_child(pack_root, rel_path_value, source_pack_path)
        if not record_path.exists() or not record_path.is_file():
            _raise("source_pack_record_file_missing", "Listed record file is missing.", record_path)
        rows = _read_record_rows(record_path)
        if not rows:
            _raise("source_pack_record_file_empty", "Listed record file must contain at least one row.", record_path)
        for row_number, row in enumerate(rows, start=1):
            _validate_record_row(
                row=row,
                row_number=row_number,
                record_name=record_name,
                record_path=record_path,
                source_pack_id=source_pack_id,
            )
            row_id = row["id"]
            if row_id in record_ids:
                first_path, first_line = record_ids[row_id]
                _raise_row(
                    "source_pack_record_id_duplicate",
                    "`id` values must be unique across listed source-pack record files.",
                    record_path,
                    row_number,
                    extra={"id": row_id, "first_path": str(first_path), "first_line": first_line},
                )
            record_ids[row_id] = (record_path, row_number)
            if record_name == "operations":
                operation_refs.add(row["id"])
            elif record_name == "response_cases":
                response_cases_path = record_path
                operation_ref = row.get("operation_ref")
                if isinstance(operation_ref, str):
                    response_operation_refs.add(operation_ref)
        record_counts[record_name] = len(rows)

    if "operations" in records:
        if "response_cases" not in records:
            _raise("source_pack_response_cases_missing", "`records.response_cases` is required when operations are listed.", source_pack_path)
        for operation_ref in sorted(response_operation_refs - operation_refs):
            _raise(
                "source_pack_response_case_operation_missing",
                "Response case references an operation that is not listed in operations.jsonl.",
                response_cases_path or source_pack_path,
                extra={"operation_ref": operation_ref},
            )
        for operation_ref in sorted(operation_refs):
            if operation_ref not in response_operation_refs:
                _raise(
                    "source_pack_response_case_missing",
                    "Every operation must have at least one response case.",
                    response_cases_path or source_pack_path,
                    extra={"operation_ref": operation_ref},
                )

    return {
        "ok": True,
        "path": str(source_pack_path),
        "source_pack_id": source_pack_id,
        "provider": provider,
        "version": version,
        "record_counts": record_counts,
    }


def validate_world_source_refs(path: Path) -> dict[str, object]:
    """Validate one world's source citation surface."""
    refs_path = path
    refs = _read_json_object(refs_path, "world_source_refs_invalid_json")

    _require_equal(refs, "schema_version", WORLD_SOURCE_REFS_SCHEMA_VERSION, refs_path)
    world = _require_string(refs, "world", refs_path)

    citation_count = 0
    for source_pack_ref in _optional_list(refs, "source_packs", refs_path):
        if not isinstance(source_pack_ref, dict):
            _raise("world_source_ref_invalid", "`source_packs` entries must be objects.", refs_path)
        _require_string(source_pack_ref, "source_pack_id", refs_path)
        pack_ref_path = _require_string(source_pack_ref, "path", refs_path)
        source_pack_path = _resolve_repo_path(refs_path.parent, pack_ref_path, refs_path)
        if source_pack_path.exists():
            validate_source_pack(source_pack_path)
            _validate_source_pack_record_refs(source_pack_path, source_pack_ref)
        else:
            _raise("world_source_pack_missing", "Referenced source pack does not exist.", source_pack_path)
        citation_count += _record_ref_count(source_pack_ref)

    for evidence_ref in _optional_list(refs, "world_evidence", refs_path):
        if not isinstance(evidence_ref, dict):
            _raise("world_evidence_ref_invalid", "`world_evidence` entries must be objects.", refs_path)
        evidence_path_value = _require_string(evidence_ref, "path", refs_path)
        evidence_path = _resolve_child(refs_path.parent, evidence_path_value, refs_path)
        if not evidence_path.exists() or not evidence_path.is_file():
            _raise("world_evidence_file_missing", "Referenced world evidence file does not exist.", evidence_path)
        _validate_file_record_refs(evidence_path, evidence_ref)
        citation_count += _record_ref_count(evidence_ref)

    if citation_count == 0:
        _raise("world_source_refs_empty", "World source refs must cite at least one source record.", refs_path)

    return {
        "ok": True,
        "path": str(refs_path),
        "world": world,
        "citation_count": citation_count,
    }


def _source_pack_path(path: Path) -> Path:
    if path.is_dir():
        return path / "source_pack.json"
    return path


def _read_json_object(path: Path, code: str) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        _raise("source_pack_file_missing" if path.name == "source_pack.json" else "json_file_missing", "JSON file is missing.", path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourcePackValidationError(code, f"Invalid JSON in {path}: {exc}", {"path": str(path), "line": exc.lineno}) from exc
    if not isinstance(payload, dict):
        _raise(code, "JSON file must contain an object.", path)
    return payload


def _read_record_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".json":
        payload = _read_json_object(path, "source_pack_record_invalid_json")
        return [payload]
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SourcePackValidationError(
                "source_pack_record_invalid_jsonl",
                f"Invalid JSONL row in {path}: {exc}",
                {"path": str(path), "line": line_number},
            ) from exc
        if not isinstance(row, dict):
            raise SourcePackValidationError(
                "source_pack_record_row_not_object",
                "Source-pack record rows must be objects.",
                {"path": str(path), "line": line_number},
            )
        rows.append(row)
    return rows


def _validate_record_row(
    *,
    row: dict[str, Any],
    row_number: int,
    record_name: str,
    record_path: Path,
    source_pack_id: str,
) -> None:
    row_id = row.get("id")
    if not isinstance(row_id, str) or not row_id:
        _raise_row("source_pack_record_id_missing", "`id` must be a non-empty string.", record_path, row_number)

    row_source_pack_id = row.get("source_pack_id")
    if row_source_pack_id is not None and row_source_pack_id != source_pack_id:
        _raise_row("source_pack_record_source_pack_mismatch", "`source_pack_id` does not match source_pack.json.", record_path, row_number)

    if row_source_pack_id is None and not any(key in row for key in ("operation_ref", "operation_refs", "source_refs")):
        _raise_row("source_pack_record_source_missing", "Record row must cite the source pack, an operation, or source refs.", record_path, row_number)

    if row.get("live_execution_allowed") is True:
        _raise_row("source_pack_record_live_execution_not_allowed", "Record rows must not allow live provider execution.", record_path, row_number)

    if record_name == "operations":
        _require_row_string(row, "operation_id", record_path, row_number)
        _require_row_source_refs(row, record_path, row_number)
    elif record_name == "schemas":
        _require_row_string(row, "name", record_path, row_number)
        _require_row_source_refs(row, record_path, row_number)
    elif record_name in {"examples", "observed_errors", "docs_index"}:
        _require_row_source_refs(row, record_path, row_number)
    elif record_name == "response_cases":
        _require_row_string(row, "operation_ref", record_path, row_number)
        _require_row_string(row, "case", record_path, row_number)
        response_mode = _require_row_string(row, "response_mode", record_path, row_number)
        _validate_response_case_payload(row, response_mode, record_path, row_number)
        if "status" not in row:
            _raise_row("source_pack_response_case_status_missing", "`status` is required.", record_path, row_number)
        _require_row_source_refs(row, record_path, row_number)
    elif record_name == "probes":
        if row.get("live_execution_allowed") is not False:
            _raise_row("source_pack_probe_live_execution_not_allowed", "Probe rows must set `live_execution_allowed` to false.", record_path, row_number)
    elif record_name == "world_candidates":
        if row.get("not_world_contract") is not True:
            _raise_row("source_pack_world_candidate_not_contract_missing", "World candidate rows must set `not_world_contract` to true.", record_path, row_number)


def _require_string(payload: dict[str, Any], key: str, path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        _raise("json_string_field_missing", f"`{key}` must be a non-empty string.", path)
    return value


def _require_equal(payload: dict[str, Any], key: str, expected: str, path: Path) -> None:
    if payload.get(key) != expected:
        _raise("json_schema_version_invalid", f"`{key}` must be {expected}.", path)


def _require_nonempty_list(payload: dict[str, Any], key: str, path: Path) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        _raise("json_list_field_missing", f"`{key}` must be a non-empty list.", path)
    return value


def _optional_list(payload: dict[str, Any], key: str, path: Path) -> list[Any]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        _raise("json_list_field_invalid", f"`{key}` must be a list.", path)
    return value


def _record_ref_count(ref: dict[str, Any]) -> int:
    records = ref.get("records", [])
    if isinstance(records, list):
        return len(records)
    return 0


def _validate_source_pack_record_refs(source_pack_path: Path, source_pack_ref: dict[str, Any]) -> None:
    records = source_pack_ref.get("records", [])
    if not isinstance(records, list) or not records:
        return
    pack = _read_json_object(source_pack_path, "source_pack_invalid_json")
    record_files = pack.get("records", {})
    if not isinstance(record_files, dict):
        return
    ids: set[str] = set()
    for rel_path_value in record_files.values():
        if not isinstance(rel_path_value, str):
            continue
        record_path = _resolve_child(source_pack_path.parent, rel_path_value, source_pack_path)
        if record_path.exists() and record_path.is_file():
            ids |= _record_ids_from_file(record_path)
    for record in records:
        if isinstance(record, str) and record not in ids:
            raise SourcePackValidationError(
                "world_source_record_missing",
                "Referenced source-pack record is missing.",
                {"path": str(source_pack_path), "record": record},
            )


def _validate_file_record_refs(path: Path, ref: dict[str, Any]) -> None:
    records = ref.get("records", [])
    if not isinstance(records, list) or not records:
        return
    if path.suffix not in {".jsonl", ".json"}:
        return
    ids = _record_ids_from_file(path)
    for record in records:
        if isinstance(record, str) and record not in ids:
            raise SourcePackValidationError(
                "world_source_record_missing",
                "Referenced world evidence record is missing.",
                {"path": str(path), "record": record},
            )


def _record_ids_from_file(path: Path) -> set[str]:
    return {row["id"] for row in _read_record_rows(path) if isinstance(row.get("id"), str)}


def _require_row_string(row: dict[str, Any], key: str, path: Path, row_number: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        _raise_row("source_pack_record_string_field_missing", f"`{key}` must be a non-empty string.", path, row_number)
    return value


def _require_row_source_refs(row: dict[str, Any], path: Path, row_number: int) -> None:
    value = row.get("source_refs")
    if not isinstance(value, list) or not value:
        _raise_row("source_pack_record_source_refs_missing", "`source_refs` must be a non-empty list.", path, row_number)
    for index, source_ref in enumerate(value):
        if not isinstance(source_ref, dict):
            _raise_row(
                "source_pack_record_source_ref_invalid",
                "Each source_ref must be an object.",
                path,
                row_number,
                extra={"source_ref_index": index},
            )
        kind = source_ref.get("kind")
        if not isinstance(kind, str) or not kind:
            _raise_row(
                "source_pack_record_source_ref_invalid",
                "Each source_ref must have a non-empty kind.",
                path,
                row_number,
                extra={"source_ref_index": index},
            )
        if not any(source_ref.get(key) for key in ("url", "path", "pointer", "record_id", "evidence_id")):
            _raise_row(
                "source_pack_record_source_ref_invalid",
                "Each source_ref must include url, path, pointer, record_id, or evidence_id.",
                path,
                row_number,
                extra={"source_ref_index": index},
            )


def _validate_response_case_payload(row: dict[str, Any], response_mode: str, path: Path, row_number: int) -> None:
    if response_mode not in RESPONSE_CASE_RESPONSE_MODES:
        _raise_row(
            "source_pack_response_case_mode_invalid",
            "`response_mode` must be a supported response case mode.",
            path,
            row_number,
            extra={"response_mode": response_mode},
        )

    present_payloads = [field for field in RESPONSE_CASE_PAYLOAD_FIELDS if field in row]
    if response_mode == "no_body":
        if present_payloads:
            _raise_row(
                "source_pack_response_case_payload_invalid",
                "`no_body` response cases must not include response payload fields.",
                path,
                row_number,
                extra={"response_mode": response_mode, "disallowed_payloads": present_payloads},
            )
        return

    if response_mode not in present_payloads:
        _raise_row(
            "source_pack_response_case_payload_invalid",
            "`response_mode` must match the response payload field.",
            path,
            row_number,
            extra={"response_mode": response_mode, "required_payload": response_mode},
        )

    disallowed_payloads = [field for field in present_payloads if field != response_mode]
    if disallowed_payloads:
        _raise_row(
            "source_pack_response_case_payload_invalid",
            "`response_mode` must match the response payload field.",
            path,
            row_number,
            extra={"response_mode": response_mode, "disallowed_payloads": disallowed_payloads},
        )


def _resolve_child(root: Path, rel_path: str, source_path: Path) -> Path:
    candidate = Path(rel_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        _raise("relative_path_invalid", "Referenced paths must be relative children.", source_path)
    return root / candidate


def _resolve_repo_path(root: Path, rel_path: str, source_path: Path) -> Path:
    candidate = Path(rel_path)
    if candidate.is_absolute():
        _raise("relative_path_invalid", "Referenced paths must be relative.", source_path)
    resolved = (root / candidate).resolve(strict=False)
    repo_root = PROJECT_ROOT.resolve()
    if not resolved.is_relative_to(repo_root):
        _raise("relative_path_escapes_repo", "Referenced path escapes the repository.", source_path)
    return resolved


def _raise(code: str, message: str, path: Path, *, extra: dict[str, object] | None = None) -> None:
    details = {"path": str(path)}
    if extra is not None:
        details.update(extra)
    raise SourcePackValidationError(code, message, details)


def _raise_row(code: str, message: str, path: Path, row_number: int, *, extra: dict[str, object] | None = None) -> None:
    details = {"path": str(path), "line": row_number}
    if extra is not None:
        details.update(extra)
    raise SourcePackValidationError(code, message, details)
