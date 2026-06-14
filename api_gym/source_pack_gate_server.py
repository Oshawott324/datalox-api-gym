"""HTTP dry-run gate over API source-pack response cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api_gym.source_pack_gate import (
    SourcePackGateError,
    build_gate_response,
    choose_response_case,
    find_operation,
)


COMMON_HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
GATED_API_CALL_SCHEMA_VERSION = "api_gym.gated_api_call.v0"


def create_gate_app(
    provider: str,
    version: str | None = None,
    default_case: str = "success",
    evidence_path: Path | None = None,
) -> FastAPI:
    """Create a source-pack backed HTTP gate for original-shaped provider paths."""
    app = FastAPI(title=f"API Gym source-pack gate: {provider}")

    @app.api_route("/{path:path}", methods=COMMON_HTTP_METHODS)
    async def gate_request(path: str, request: Request) -> JSONResponse:
        requested_case = request.headers.get("x-api-gym-case", default_case)
        provider_path = "/" + path.lstrip("/")
        request_json = await _request_json_or_none(request)
        evidence_row = _base_evidence_row(
            provider=provider,
            version=version,
            method=request.method,
            path=provider_path,
            query_params=_query_params(request),
            request_json=request_json,
            selected_case=requested_case,
        )
        try:
            operation = find_operation(provider, request.method, provider_path, version=version)
            evidence_row["matched_operation_id"] = operation["id"]
            response_case = choose_response_case(provider, operation["id"], case=requested_case, version=version)
            evidence_row["response_case_id"] = response_case["id"]
            gate_response = build_gate_response(response_case)
            status_code = _status_code(gate_response.get("status"), response_case)
        except SourcePackGateError as exc:
            error_response = _source_pack_error_response(exc)
            _record_evidence(
                evidence_path,
                {
                    **evidence_row,
                    "status_code": error_response.status_code,
                    "ok": False,
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                },
            )
            return error_response

        _record_evidence(
            evidence_path,
            {
                **evidence_row,
                "status_code": status_code,
                "response_mode": gate_response["response_mode"],
                "ok": True,
            },
        )

        return JSONResponse(
            content=_response_content(gate_response),
            status_code=status_code,
        )

    return app


async def _request_json_or_none(request: Request) -> object:
    try:
        return await request.json()
    except json.JSONDecodeError:
        return None


def _query_params(request: Request) -> dict[str, object]:
    return {
        key: values[0] if len(values) == 1 else values
        for key in sorted(set(request.query_params.keys()))
        if (values := request.query_params.getlist(key))
    }


def _base_evidence_row(
    *,
    provider: str,
    version: str | None,
    method: str,
    path: str,
    query_params: dict[str, object],
    request_json: object,
    selected_case: str,
) -> dict[str, object]:
    row: dict[str, object] = {
        "schema_version": GATED_API_CALL_SCHEMA_VERSION,
        "provider": provider,
        "method": method,
        "path": path,
        "query_params": query_params,
        "request_json": request_json,
        "selected_case": selected_case,
    }
    if version is not None:
        row["version"] = version
    return row


def _record_evidence(evidence_path: Path | None, row: dict[str, object]) -> None:
    if evidence_path is None:
        return
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _response_content(gate_response: dict[str, Any]) -> object:
    if "body" in gate_response:
        return gate_response["body"]
    if "body_excerpt" in gate_response:
        return gate_response["body_excerpt"]
    return gate_response


def _status_code(status: object, response_case: dict[str, Any]) -> int:
    if isinstance(status, int):
        return status
    raise SourcePackGateError(
        "source_pack_gate_http_status_not_concrete",
        "HTTP gate response status must be a concrete integer status code.",
        {"response_case_id": response_case.get("id", ""), "status": status},
    )


def _source_pack_error_response(exc: SourcePackGateError) -> JSONResponse:
    status_code = 404 if "not_found" in exc.code else 400
    return JSONResponse(
        content={
            "ok": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        },
        status_code=status_code,
    )
