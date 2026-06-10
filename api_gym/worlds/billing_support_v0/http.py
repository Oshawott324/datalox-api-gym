"""FastAPI surface for billing_support_v0 run state."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from api_gym.worlds.billing_support_v0 import services
from api_gym.worlds.billing_support_v0.state import resolve_state_db_path


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
    app = FastAPI(title="Datalox API Gym billing_support_v0")

    @app.get("/support/tickets/{ticket_id}")
    def get_ticket(ticket_id: str) -> dict:
        return services.get_ticket(db_path, ticket_id)

    @app.post("/support/tickets/{ticket_id}/reply")
    def add_reply(ticket_id: str, request: ReplyRequest) -> dict:
        return services.add_reply(db_path, ticket_id=ticket_id, body=request.body, public=request.public)

    @app.post("/support/tickets/{ticket_id}/close")
    def close_ticket(ticket_id: str) -> dict:
        return services.close_ticket(db_path, ticket_id=ticket_id)

    @app.post("/support/tickets/{ticket_id}/tag")
    def tag_ticket(ticket_id: str, request: TagRequest) -> dict:
        return services.tag_ticket(db_path, ticket_id=ticket_id, tags=request.tags)

    @app.post("/support/tickets/{ticket_id}/escalate")
    def escalate_ticket(ticket_id: str, request: EscalateRequest) -> dict:
        return services.escalate_ticket(db_path, ticket_id=ticket_id, reason=request.reason)

    @app.get("/billing/customers/{customer_id}")
    def get_customer(customer_id: str) -> dict:
        return services.get_customer(db_path, customer_id)

    @app.get("/billing/invoices/{invoice_id}")
    def get_invoice(invoice_id: str) -> dict:
        return services.get_invoice(db_path, invoice_id)

    @app.get("/billing/payments/{payment_id}")
    def get_payment(payment_id: str) -> dict:
        return services.get_payment(db_path, payment_id)

    @app.post("/billing/refunds")
    def create_refund(request: RefundRequest) -> dict:
        return services.create_refund(
            db_path,
            payment_id=request.payment_id,
            amount=request.amount,
            reason=request.reason,
            ticket_id=request.ticket_id,
        )

    @app.post("/billing/invoices/{invoice_id}/retry")
    def retry_invoice(invoice_id: str) -> dict:
        return services.retry_invoice(db_path, invoice_id=invoice_id)

    return app
