from __future__ import annotations

import json

from fastapi.testclient import TestClient

from api_gym.source_pack_gate_server import create_gate_app


def test_gate_server_returns_invoice_body_excerpt_for_pay_invoice() -> None:
    client = TestClient(create_gate_app("stripe"))

    response = client.post("/v1/invoices/in_123/pay")

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "invoice"
    assert payload["status"] == "paid"


def test_gate_server_returns_full_gate_response_for_error_shape_case() -> None:
    client = TestClient(create_gate_app("stripe"))

    response = client.post("/v1/refunds", headers={"x-api-gym-case": "error"})

    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == 400
    assert payload["response_mode"] == "error_shape"
    assert payload["error_shape"] == {
        "error": {
            "type": "string",
            "message": "string",
            "code": "string_optional",
            "param": "string_optional",
        }
    }
    assert payload["gating_notes"] == [
        "Creating a refund raises an error when the referenced Charge or PaymentIntent has already been refunded, or when the identifier is invalid."
    ]


def test_gate_server_returns_stable_error_for_non_concrete_source_status() -> None:
    client = TestClient(create_gate_app("stripe"))

    response = client.post("/v1/refunds")

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "source_pack_gate_http_status_not_concrete"
    assert payload["error"]["details"] == {
        "response_case_id": "response_case:createRefund:success",
        "status": "2xx",
    }


def test_gate_server_returns_stable_error_for_unsupported_path() -> None:
    client = TestClient(create_gate_app("stripe"))

    response = client.post("/v1/not-a-real-operation")

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "source_pack_gate_operation_not_found"
    assert payload["error"]["message"] == "No source-pack operation matches the provider, method, and path."
    assert payload["error"]["details"]["provider"] == "stripe"
    assert payload["error"]["details"]["method"] == "POST"
    assert payload["error"]["details"]["path"] == "/v1/not-a-real-operation"


def test_gate_server_records_ok_evidence_row_for_matched_json_request(tmp_path) -> None:
    evidence_path = tmp_path / "trace" / "gate.jsonl"
    client = TestClient(create_gate_app("stripe", evidence_path=evidence_path))

    response = client.post("/v1/invoices/in_123/pay?expand[]=charge", json={"paid_out_of_band": True})

    assert response.status_code == 200
    rows = [json.loads(line) for line in evidence_path.read_text().splitlines()]
    assert rows == [
        {
            "schema_version": "api_gym.gated_api_call.v0",
            "provider": "stripe",
            "method": "POST",
            "path": "/v1/invoices/in_123/pay",
            "query_params": {"expand[]": "charge"},
            "request_json": {"paid_out_of_band": True},
            "matched_operation_id": "operation:payInvoice",
            "response_case_id": "response_case:payInvoice:success",
            "selected_case": "success",
            "status_code": 200,
            "response_mode": "body_excerpt",
            "ok": True,
        }
    ]


def test_gate_server_records_case_query_as_provider_query_not_selector(tmp_path) -> None:
    evidence_path = tmp_path / "gate.jsonl"
    client = TestClient(create_gate_app("stripe", evidence_path=evidence_path))

    response = client.post("/v1/refunds?case=error", headers={"x-api-gym-case": "error"})

    assert response.status_code == 400
    rows = [json.loads(line) for line in evidence_path.read_text().splitlines()]
    assert rows[0]["query_params"] == {"case": "error"}
    assert rows[0]["selected_case"] == "error"
    assert rows[0]["response_case_id"] == "response_case:createRefund:invalid_request_error"
    assert rows[0]["ok"] is True


def test_gate_server_records_error_evidence_row_for_unsupported_path(tmp_path) -> None:
    evidence_path = tmp_path / "gate.jsonl"
    client = TestClient(create_gate_app("stripe", evidence_path=evidence_path))

    response = client.post("/v1/not-a-real-operation")

    assert response.status_code == 404
    rows = [json.loads(line) for line in evidence_path.read_text().splitlines()]
    assert rows == [
        {
            "schema_version": "api_gym.gated_api_call.v0",
            "provider": "stripe",
            "method": "POST",
            "path": "/v1/not-a-real-operation",
            "query_params": {},
            "request_json": None,
            "selected_case": "success",
            "status_code": 404,
            "ok": False,
            "error": {
                "code": "source_pack_gate_operation_not_found",
                "message": "No source-pack operation matches the provider, method, and path.",
                "details": {
                    "provider": "stripe",
                    "method": "POST",
                    "path": "/v1/not-a-real-operation",
                    "version": "2026-06-12",
                },
            },
        }
    ]
