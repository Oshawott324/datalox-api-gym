"""FastAPI surface for billing_support_v0 run state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from pydantic import BaseModel

from api_gym.worlds.billing_support_v0 import services
from api_gym.worlds.billing_support_v0.state import resolve_state_db_path
from api_gym.worlds.http import append_world_http_trace, query_params


WORLD = "billing_support_v0"


class ReplyRequest(BaseModel):
    body: str
    public: bool = True


class TagRequest(BaseModel):
    tags: list[str]


class EscalateRequest(BaseModel):
    reason: str


class RefundRequest(BaseModel):
    payment_id: str
    reason: str
    amount: int | None = None
    ticket_id: str | None = None


def create_app(run_dir: Path) -> FastAPI:
    """Create an HTTP app bound to one sampled run directory."""
    db_path = resolve_state_db_path(run_dir)
    trace_path = run_dir / "traces" / "http_requests.jsonl"
    app = FastAPI(title="Datalox API Gym billing_support_v0")

    @app.get("/support/tickets/{ticket_id}")
    def get_ticket(ticket_id: str, http_request: Request) -> dict:
        return _recorded_response(
            trace_path,
            request=http_request,
            request_json=None,
            response=services.get_ticket(db_path, ticket_id),
        )

    @app.post("/support/tickets/{ticket_id}/reply")
    def add_reply(ticket_id: str, request: ReplyRequest, http_request: Request) -> dict:
        return _recorded_response(
            trace_path,
            request=http_request,
            request_json=_request_model_payload(request),
            response=services.add_reply(db_path, ticket_id=ticket_id, body=request.body, public=request.public),
        )

    @app.post("/support/tickets/{ticket_id}/close")
    def close_ticket(ticket_id: str, http_request: Request) -> dict:
        return _recorded_response(
            trace_path,
            request=http_request,
            request_json=None,
            response=services.close_ticket(db_path, ticket_id=ticket_id),
        )

    @app.post("/support/tickets/{ticket_id}/tag")
    def tag_ticket(ticket_id: str, request: TagRequest, http_request: Request) -> dict:
        return _recorded_response(
            trace_path,
            request=http_request,
            request_json=_request_model_payload(request),
            response=services.tag_ticket(db_path, ticket_id=ticket_id, tags=request.tags),
        )

    @app.post("/support/tickets/{ticket_id}/escalate")
    def escalate_ticket(ticket_id: str, request: EscalateRequest, http_request: Request) -> dict:
        return _recorded_response(
            trace_path,
            request=http_request,
            request_json=_request_model_payload(request),
            response=services.escalate_ticket(db_path, ticket_id=ticket_id, reason=request.reason),
        )

    @app.get("/billing/customers/{customer_id}")
    def get_customer(customer_id: str, http_request: Request) -> dict:
        return _recorded_response(
            trace_path,
            request=http_request,
            request_json=None,
            response=services.get_customer(db_path, customer_id),
        )

    @app.get("/billing/invoices/{invoice_id}")
    def get_invoice(invoice_id: str, http_request: Request) -> dict:
        return _recorded_response(
            trace_path,
            request=http_request,
            request_json=None,
            response=services.get_invoice(db_path, invoice_id),
        )

    @app.get("/billing/payments/{payment_id}")
    def get_payment(payment_id: str, http_request: Request) -> dict:
        return _recorded_response(
            trace_path,
            request=http_request,
            request_json=None,
            response=services.get_payment(db_path, payment_id),
        )

    @app.post("/billing/refunds")
    def create_refund(request: RefundRequest, http_request: Request) -> dict:
        return _recorded_response(
            trace_path,
            request=http_request,
            request_json=_request_model_payload(request),
            response=services.create_refund(
                db_path,
                payment_id=request.payment_id,
                amount=request.amount,
                reason=request.reason,
                ticket_id=request.ticket_id,
            ),
        )

    @app.post("/billing/invoices/{invoice_id}/retry")
    def retry_invoice(invoice_id: str, http_request: Request) -> dict:
        return _recorded_response(
            trace_path,
            request=http_request,
            request_json=None,
            response=services.retry_invoice(db_path, invoice_id=invoice_id),
        )

    return app


def _recorded_response(
    trace_path: Path,
    *,
    request: Request,
    request_json: object,
    response: dict[str, Any],
) -> dict[str, Any]:
    append_world_http_trace(
        trace_path,
        world=WORLD,
        method=request.method,
        path_value=request.url.path,
        query_params=query_params(request),
        request_json=request_json,
        status_code=200,
        response=response,
    )
    return response


def _request_model_payload(request: BaseModel) -> dict[str, Any]:
    return request.model_dump(mode="json")
