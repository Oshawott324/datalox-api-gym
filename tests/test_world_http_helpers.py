from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api_gym.worlds.http import append_jsonl, append_world_http_trace, query_params, structured_error_response


def test_append_jsonl_writes_compact_sorted_rows(tmp_path: Path) -> None:
    path = tmp_path / "traces" / "http.jsonl"

    append_jsonl(path, {"b": 2, "a": 1})
    append_jsonl(path, {"ok": True})

    assert path.read_text(encoding="utf-8").splitlines() == [
        '{"a":1,"b":2}',
        '{"ok":true}',
    ]


def test_append_world_http_trace_writes_agent_readable_error_row(tmp_path: Path) -> None:
    path = tmp_path / "traces" / "http_requests.jsonl"

    append_world_http_trace(
        path,
        world="billing_support_v0",
        method="GET",
        path_value="/support/tickets/not-real",
        query_params={},
        request_json=None,
        status_code=200,
        response={
            "ok": False,
            "error": {
                "code": "ticket_not_found",
                "message": "Ticket does not exist.",
                "details": {"ticket_id": "not-real"},
            },
        },
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        {
            "error": {
                "code": "ticket_not_found",
                "details": {"ticket_id": "not-real"},
                "message": "Ticket does not exist.",
            },
            "method": "GET",
            "ok": False,
            "path": "/support/tickets/not-real",
            "query_params": {},
            "request_json": None,
            "schema_version": "api_gym.world_http_call.v0",
            "status_code": 200,
            "world": "billing_support_v0",
        }
    ]


def test_query_params_preserves_repeated_values() -> None:
    app = FastAPI()

    @app.get("/probe")
    async def probe(request: Request) -> JSONResponse:
        return JSONResponse(query_params(request))

    response = TestClient(app).get("/probe?expand[]=charge&expand[]=customer&limit=10")

    assert response.status_code == 200
    assert response.json() == {"expand[]": ["charge", "customer"], "limit": "10"}


def test_structured_error_response() -> None:
    response = structured_error_response(
        status_code=409,
        code="world_conflict",
        message="The world state rejected this transition.",
        details={"object_id": "obj_123"},
    )

    assert response.status_code == 409
    assert json.loads(response.body) == {
        "ok": False,
        "error": {
            "code": "world_conflict",
            "message": "The world state rejected this transition.",
            "details": {"object_id": "obj_123"},
        },
    }
