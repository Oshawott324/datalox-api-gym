"""Safe UniteLabs API contract sampling for the Plate QC world."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCHEMA_VERSION = "api_gym.unitelabs_api_contract_sample.v0"
OFFICIAL_DOCS_URLS = [
    "https://docs.unitelabs.io/technical-reference/rest-api/",
    "https://docs.unitelabs.io/automate/guides/deploy-a-workflow/",
    "https://docs.unitelabs.io/automate/guides/run-a-workflow/",
    "https://docs.unitelabs.io/automate/concepts/logs/",
]
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")
DRY_RUN_TOOL_NAMES = [
    "get_deck_state",
    "get_labware_state",
    "aspirate",
    "dispense",
    "read_absorbance",
    "add_workflow_note",
    "submit_protocol",
]
RELEVANT_CATEGORIES = {
    "workflow": {"include": ("workflow",), "exclude": ("run",)},
    "run": {"include": ("run",), "exclude": ("log", "artifact")},
    "log": {"include": ("log",), "exclude": ()},
    "artifact": {"include": ("artifact",), "exclude": ()},
}


class UnitelabsApiContractSamplingError(ValueError):
    """Agent-facing contract sampler error with a stable machine code."""

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def sample_openapi_contract(
    *,
    openapi_file: Path | None = None,
    openapi_url: str | None = None,
    bearer_token_env: str | None = None,
) -> dict[str, object]:
    """Read an explicit OpenAPI source and emit a safe Unitelabs contract sample."""

    _validate_source(openapi_file=openapi_file, openapi_url=openapi_url)
    if openapi_file is not None:
        spec = _read_openapi_file(openapi_file)
        source: dict[str, object] = {"kind": "openapi_file", "path": str(openapi_file)}
    else:
        assert openapi_url is not None
        spec = _read_openapi_url(openapi_url, bearer_token_env=bearer_token_env)
        source = {"kind": "openapi_url", "url": openapi_url}
        if bearer_token_env:
            source["bearer_token_env"] = bearer_token_env

    _validate_openapi_document(spec, source)
    info = spec.get("info", {}) if isinstance(spec.get("info"), dict) else {}
    operations = _extract_operations(spec)
    relevant_operations = {
        category: [
            operation
            for operation in operations
            if _matches_category(operation, include=specification["include"], exclude=specification["exclude"])
        ]
        for category, specification in RELEVANT_CATEGORIES.items()
    }

    source.update(
        {
            "title": info.get("title"),
            "version": info.get("version"),
            "servers": spec.get("servers", []),
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "sampled_at": _now_iso(),
        "source": source,
        "official_docs_urls": OFFICIAL_DOCS_URLS,
        "operations": operations,
        "relevant_operations": relevant_operations,
        "agent_tool_mapping": {
            "status": "requires_human_mapping",
            "proven": False,
            "reason": "This sample lists real API operations but does not prove dry-run MCP tools are semantically equivalent.",
            "dry_run_tools": DRY_RUN_TOOL_NAMES,
            "candidate_real_api_operation_ids": {
                category: [operation["operation_id"] for operation in category_operations]
                for category, category_operations in relevant_operations.items()
            },
        },
        "live_execution": {
            "allowed": False,
            "reason": "Contract sampling only; no workflow, run, hardware, or tenant API action is executed.",
        },
    }


def write_openapi_contract_sample(
    *,
    out: Path,
    openapi_file: Path | None = None,
    openapi_url: str | None = None,
    bearer_token_env: str | None = None,
) -> dict[str, object]:
    """Write a contract sample JSON file and return the payload."""

    payload = sample_openapi_contract(openapi_file=openapi_file, openapi_url=openapi_url, bearer_token_env=bearer_token_env)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _validate_source(*, openapi_file: Path | None, openapi_url: str | None) -> None:
    if (openapi_file is None and openapi_url is None) or (openapi_file is not None and openapi_url is not None):
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_source_required",
            "Supply --openapi-file or --openapi-url, but not both.",
            {"openapi_file": None if openapi_file is None else str(openapi_file), "openapi_url": openapi_url},
        )


def _read_openapi_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_file_not_found",
            f"OpenAPI file does not exist: {path}",
            {"path": str(path)},
        )
    if not path.is_file():
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_file_not_file",
            f"OpenAPI path is not a file: {path}",
            {"path": str(path)},
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_file_not_utf8",
            f"OpenAPI file is not UTF-8 text: {path}",
            {"path": str(path)},
        ) from exc
    except OSError as exc:
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_file_read_error",
            f"OpenAPI file could not be read: {exc}",
            {"path": str(path), "reason": str(exc)},
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_invalid_json",
            f"OpenAPI file is not valid JSON: {exc}",
            {"path": str(path), "line": exc.lineno, "column": exc.colno},
        ) from exc
    if not isinstance(payload, dict):
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_invalid_shape",
            "OpenAPI document must be a JSON object.",
            {"path": str(path)},
        )
    return payload


def _validate_openapi_document(spec: dict[str, Any], source: dict[str, object]) -> None:
    openapi_version = spec.get("openapi")
    swagger_version = spec.get("swagger")
    if not isinstance(openapi_version, str) and not isinstance(swagger_version, str):
        details = {
            key: value
            for key, value in source.items()
            if key in {"path", "url"}
        }
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_not_openapi",
            "OpenAPI document must contain an openapi or swagger string version.",
            details,
        )


def _read_openapi_url(url: str, *, bearer_token_env: str | None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if bearer_token_env:
        token = os.environ.get(bearer_token_env)
        if not token:
            raise UnitelabsApiContractSamplingError(
                "unitelabs_api_contract_missing_bearer_token",
                f"Environment variable {bearer_token_env} is required for --openapi-url.",
                {"bearer_token_env": bearer_token_env},
            )
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_url_http_error",
            f"OpenAPI URL returned HTTP {exc.code}.",
            {"url": url, "status": exc.code},
        ) from exc
    except URLError as exc:
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_url_error",
            f"OpenAPI URL could not be fetched: {exc.reason}",
            {"url": url, "reason": str(exc.reason)},
        ) from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_invalid_json",
            f"OpenAPI URL did not return valid JSON: {exc}",
            {"url": url, "line": exc.lineno, "column": exc.colno},
        ) from exc
    if not isinstance(payload, dict):
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_invalid_shape",
            "OpenAPI document must be a JSON object.",
            {"url": url},
        )
    return payload


def _extract_operations(spec: dict[str, Any]) -> list[dict[str, object]]:
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        raise UnitelabsApiContractSamplingError(
            "unitelabs_api_contract_missing_paths",
            "OpenAPI document must contain a paths object.",
        )

    operations: list[dict[str, object]] = []
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        inherited_parameters = path_item.get("parameters", [])
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            parameters = []
            if isinstance(inherited_parameters, list):
                parameters.extend(inherited_parameters)
            operation_parameters = operation.get("parameters", [])
            if isinstance(operation_parameters, list):
                parameters.extend(operation_parameters)
            operation_id = operation.get("operationId")
            operations.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": operation_id if isinstance(operation_id, str) else None,
                    "summary": operation.get("summary") if isinstance(operation.get("summary"), str) else None,
                    "tags": operation.get("tags") if isinstance(operation.get("tags"), list) else [],
                    "parameter_names": _parameter_names(parameters),
                    "request_schema_refs": _collect_refs(operation.get("requestBody", {})),
                    "response_schema_refs": _collect_refs(operation.get("responses", {})),
                }
            )
    return operations


def _parameter_names(parameters: list[Any]) -> list[str]:
    names = [parameter.get("name") for parameter in parameters if isinstance(parameter, dict)]
    return [name for name in names if isinstance(name, str)]


def _collect_refs(value: Any) -> list[str]:
    refs: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                refs.add(ref)
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return sorted(refs)


def _matches_category(operation: dict[str, object], *, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    tags = [str(tag).lower() for tag in operation.get("tags", []) if isinstance(tag, str)]
    haystack = " ".join(
        str(value).lower()
        for value in (*tags, operation.get("operation_id"), operation.get("summary"), operation.get("path"))
        if value is not None
    )
    return any(keyword in haystack for keyword in include) and not any(keyword in haystack for keyword in exclude)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
