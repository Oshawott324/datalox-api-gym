"""Minimal fake service operations for billing_support_v0."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api_gym.worlds.billing_support_v0.state import (
    connect,
    dumps_json,
    insert_audit,
    insert_event,
    loads_json,
    row_to_dict,
)

AGENT_EMAIL = "agent@billing-support.example"
SUPPORT_EMAIL = "support@api-gym.example"
ALLOWED_REFUND_REASONS = {"duplicate", "fraudulent", "requested_by_customer"}


def get_ticket(db_path: Path, ticket_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            return _error("ticket_not_found", "Ticket does not exist.", {"ticket_id": ticket_id})
        messages = conn.execute(
            "SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY id",
            (ticket_id,),
        ).fetchall()
        data = row_to_dict(ticket)
        data["messages"] = [row_to_dict(row) for row in messages]
        return _ok(data)


def add_reply(
    db_path: Path,
    *,
    ticket_id: str,
    body: str,
    public: bool = True,
    actor_email: str = AGENT_EMAIL,
) -> dict[str, Any]:
    body = body.strip()
    if not body:
        return _error("empty_reply", "Ticket replies require a non-empty body.", {"ticket_id": ticket_id})

    now = _now()
    with connect(db_path) as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            return _error("ticket_not_found", "Ticket does not exist.", {"ticket_id": ticket_id})
        conn.execute(
            """
            INSERT INTO ticket_messages (ticket_id, author_type, author_email, body, public, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticket_id, "agent", actor_email, body, int(public), now),
        )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        if public:
            conn.execute(
                """
                INSERT INTO emails (
                  ticket_id, customer_id, to_email, from_email, subject, body, status, provider_message_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket_id,
                    ticket["customer_id"],
                    ticket["requester_email"],
                    SUPPORT_EMAIL,
                    f"Re: {ticket['subject']}",
                    body,
                    "sent",
                    f"msg_{ticket_id}_{_message_count(conn, ticket_id) + 1}",
                    now,
                ),
            )
        response = {"ticket_id": ticket_id, "public": public, "body": body}
        insert_event(
            conn,
            event_type="ticket.comment_created",
            object_type="ticket",
            object_id=ticket_id,
            payload=response,
            created_at=now,
        )
        insert_audit(
            conn,
            actor=actor_email,
            action="support.add_reply",
            object_type="ticket",
            object_id=ticket_id,
            request={"body": body, "public": public},
            response=response,
            created_at=now,
        )
        return _ok(response)


def close_ticket(db_path: Path, *, ticket_id: str, actor_email: str = AGENT_EMAIL) -> dict[str, Any]:
    now = _now()
    with connect(db_path) as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            return _error("ticket_not_found", "Ticket does not exist.", {"ticket_id": ticket_id})
        conn.execute(
            "UPDATE tickets SET status = ?, updated_at = ?, closed_at = ? WHERE id = ?",
            ("solved", now, now, ticket_id),
        )
        response = {"ticket_id": ticket_id, "status": "solved"}
        insert_event(
            conn,
            event_type="ticket.solved",
            object_type="ticket",
            object_id=ticket_id,
            payload=response,
            created_at=now,
        )
        insert_audit(
            conn,
            actor=actor_email,
            action="support.close_ticket",
            object_type="ticket",
            object_id=ticket_id,
            request={},
            response=response,
            created_at=now,
        )
        return _ok(response)


def tag_ticket(
    db_path: Path,
    *,
    ticket_id: str,
    tags: list[str],
    actor_email: str = AGENT_EMAIL,
) -> dict[str, Any]:
    clean_tags = sorted({tag.strip() for tag in tags if tag.strip()})
    if not clean_tags:
        return _error("empty_tags", "At least one non-empty tag is required.", {"ticket_id": ticket_id})

    now = _now()
    with connect(db_path) as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            return _error("ticket_not_found", "Ticket does not exist.", {"ticket_id": ticket_id})
        merged_tags = _merge_tags(loads_json(ticket["tags_json"]) or [], clean_tags)
        conn.execute(
            "UPDATE tickets SET tags_json = ?, updated_at = ? WHERE id = ?",
            (dumps_json(merged_tags), now, ticket_id),
        )
        response = {"ticket_id": ticket_id, "tags": merged_tags}
        insert_event(
            conn,
            event_type="ticket.tags_added",
            object_type="ticket",
            object_id=ticket_id,
            payload={"added_tags": clean_tags, "tags": merged_tags},
            created_at=now,
        )
        insert_audit(
            conn,
            actor=actor_email,
            action="support.tag_ticket",
            object_type="ticket",
            object_id=ticket_id,
            request={"tags": clean_tags},
            response=response,
            created_at=now,
        )
        return _ok(response)


def escalate_ticket(
    db_path: Path,
    *,
    ticket_id: str,
    reason: str,
    actor_email: str = AGENT_EMAIL,
) -> dict[str, Any]:
    reason = reason.strip()
    if not reason:
        return _error("empty_escalation_reason", "Escalation requires a reason.", {"ticket_id": ticket_id})

    now = _now()
    with connect(db_path) as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if ticket is None:
            return _error("ticket_not_found", "Ticket does not exist.", {"ticket_id": ticket_id})
        tags = _merge_tags(loads_json(ticket["tags_json"]) or [], ["escalated", "billing_policy_review"])
        conn.execute(
            """
            UPDATE tickets
            SET status = ?, priority = ?, assignee_group = ?, tags_json = ?, updated_at = ?
            WHERE id = ?
            """,
            ("pending", "high", "billing-escalations", dumps_json(tags), now, ticket_id),
        )
        response = {
            "ticket_id": ticket_id,
            "status": "pending",
            "priority": "high",
            "assignee_group": "billing-escalations",
            "tags": tags,
            "reason": reason,
        }
        insert_event(
            conn,
            event_type="ticket.escalated",
            object_type="ticket",
            object_id=ticket_id,
            payload=response,
            created_at=now,
        )
        insert_audit(
            conn,
            actor=actor_email,
            action="support.escalate_ticket",
            object_type="ticket",
            object_id=ticket_id,
            request={"reason": reason},
            response=response,
            created_at=now,
        )
        return _ok(response)


def get_customer(db_path: Path, customer_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if customer is None:
            return _error("customer_not_found", "Customer does not exist.", {"customer_id": customer_id})
        data = row_to_dict(customer)
        data["subscriptions"] = [
            row_to_dict(row)
            for row in conn.execute("SELECT * FROM subscriptions WHERE customer_id = ? ORDER BY created_at", (customer_id,))
        ]
        data["invoices"] = [
            row_to_dict(row)
            for row in conn.execute("SELECT * FROM invoices WHERE customer_id = ? ORDER BY created_at", (customer_id,))
        ]
        return _ok(data)


def get_invoice(db_path: Path, invoice_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if invoice is None:
            return _error("invoice_not_found", "Invoice does not exist.", {"invoice_id": invoice_id})
        payments = conn.execute(
            "SELECT * FROM payments WHERE invoice_id = ? ORDER BY created_at, id",
            (invoice_id,),
        ).fetchall()
        data = row_to_dict(invoice)
        data["payments"] = [row_to_dict(row) for row in payments]
        return _ok(data)


def get_payment(db_path: Path, payment_id: str) -> dict[str, Any]:
    with connect(db_path) as conn:
        payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if payment is None:
            return _error("payment_not_found", "Payment does not exist.", {"payment_id": payment_id})
        refunds = conn.execute(
            "SELECT * FROM refunds WHERE payment_id = ? ORDER BY created_at, id",
            (payment_id,),
        ).fetchall()
        data = row_to_dict(payment)
        data["refunds"] = [row_to_dict(row) for row in refunds]
        data["refundable_amount"] = payment["amount"] - payment["refunded_amount"]
        return _ok(data)


def create_refund(
    db_path: Path,
    *,
    payment_id: str,
    amount: int | None = None,
    reason: str,
    ticket_id: str | None = None,
    actor_email: str = AGENT_EMAIL,
) -> dict[str, Any]:
    reason = reason.strip()
    if reason not in ALLOWED_REFUND_REASONS:
        return _error(
            "invalid_refund_reason",
            "Refund reason must match a supported billing reason.",
            {"allowed_reasons": sorted(ALLOWED_REFUND_REASONS), "reason": reason},
        )

    now = _now()
    with connect(db_path) as conn:
        payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if payment is None:
            return _error("payment_not_found", "Payment does not exist.", {"payment_id": payment_id})
        if ticket_id is not None:
            ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if ticket is None:
                return _error("ticket_not_found", "Ticket does not exist.", {"ticket_id": ticket_id})
        if payment["status"] != "succeeded":
            return _error(
                "payment_not_refundable",
                "Only succeeded payments can be refunded.",
                {"payment_id": payment_id, "status": payment["status"]},
            )

        remaining = payment["amount"] - payment["refunded_amount"]
        refund_amount = remaining if amount is None else amount
        if refund_amount <= 0:
            return _error("invalid_refund_amount", "Refund amount must be positive.", {"amount": refund_amount})
        if refund_amount > remaining:
            return _error(
                "refund_amount_exceeds_remaining",
                "Refund amount exceeds the unrefunded payment amount.",
                {"payment_id": payment_id, "remaining": remaining, "requested": refund_amount},
            )

        policy = _active_refund_policy(conn)
        if policy is None:
            return _error(
                "policy_not_configured",
                "The active refund policy is missing from episode state.",
                {"policy_key": "standard_refund_policy"},
            )
        policy_error = _refund_policy_error(payment, reason, policy, now)
        if policy_error is not None:
            return policy_error

        refund_id = _next_refund_id(conn, payment_id)
        conn.execute(
            """
            INSERT INTO refunds (
              id, payment_id, amount, currency, status, reason, ticket_id, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                refund_id,
                payment_id,
                refund_amount,
                payment["currency"],
                "succeeded",
                reason,
                ticket_id,
                now,
                dumps_json({"created_by": actor_email}),
            ),
        )
        conn.execute(
            "UPDATE payments SET refunded_amount = refunded_amount + ? WHERE id = ?",
            (refund_amount, payment_id),
        )
        response = {
            "id": refund_id,
            "payment_id": payment_id,
            "amount": refund_amount,
            "currency": payment["currency"],
            "status": "succeeded",
            "reason": reason,
            "ticket_id": ticket_id,
        }
        insert_event(
            conn,
            event_type="refund.succeeded",
            object_type="refund",
            object_id=refund_id,
            payload=response,
            created_at=now,
        )
        insert_event(
            conn,
            event_type="charge.refunded",
            object_type="payment",
            object_id=payment_id,
            payload={"refund_id": refund_id, "amount": refund_amount, "reason": reason},
            created_at=now,
        )
        insert_audit(
            conn,
            actor=actor_email,
            action="billing.create_refund",
            object_type="payment",
            object_id=payment_id,
            request={"amount": amount, "reason": reason, "ticket_id": ticket_id},
            response=response,
            created_at=now,
        )
        return _ok(response)


def retry_invoice(
    db_path: Path,
    *,
    invoice_id: str,
    actor_email: str = AGENT_EMAIL,
) -> dict[str, Any]:
    now = _now()
    with connect(db_path) as conn:
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if invoice is None:
            return _error("invoice_not_found", "Invoice does not exist.", {"invoice_id": invoice_id})
        if invoice["status"] == "paid":
            return _error("invoice_already_paid", "Invoice is already paid.", {"invoice_id": invoice_id})
        if invoice["collection_method"] != "charge_automatically":
            return _error(
                "invoice_not_auto_collect",
                "Only automatically collected invoices can be retried by this operation.",
                {"invoice_id": invoice_id, "collection_method": invoice["collection_method"]},
            )

        latest_payment = None
        if invoice["latest_payment_id"]:
            latest_payment = conn.execute(
                "SELECT * FROM payments WHERE id = ?",
                (invoice["latest_payment_id"],),
            ).fetchone()
        policy = _active_refund_policy(conn)
        if policy is None:
            return _error(
                "policy_not_configured",
                "The active retry policy is missing from episode state.",
                {"policy_key": "standard_refund_policy"},
            )
        hard_declines = set(policy.get("hard_decline_codes", []))
        decline_code = latest_payment["decline_code"] if latest_payment is not None else None
        if decline_code in hard_declines:
            return _error(
                "invoice_not_retryable_hard_decline",
                "Invoice cannot be retried without a new payment method because the latest decline is hard.",
                {"invoice_id": invoice_id, "decline_code": decline_code},
            )

        amount = invoice["amount_remaining"]
        if amount <= 0:
            return _error(
                "invoice_has_no_remaining_amount",
                "Invoice has no remaining amount to collect.",
                {"invoice_id": invoice_id, "amount_remaining": amount},
            )

        attempt_number = invoice["attempt_count"] + 1
        payment_id = f"py_{invoice_id}_retry_{attempt_number}"
        conn.execute(
            """
            INSERT INTO payments (
              id, customer_id, invoice_id, amount, currency, status, payment_method,
              payment_intent_id, charge_id, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payment_id,
                invoice["customer_id"],
                invoice_id,
                amount,
                invoice["currency"],
                "succeeded",
                "card_visa_4242",
                f"pi_{invoice_id}_retry_{attempt_number}",
                f"ch_{invoice_id}_retry_{attempt_number}",
                now,
                dumps_json({"retry_attempt": attempt_number}),
            ),
        )
        conn.execute(
            """
            UPDATE invoices
            SET status = ?, amount_paid = amount_due, amount_remaining = 0, attempt_count = ?,
                next_payment_attempt = NULL, latest_payment_id = ?, paid_at = ?
            WHERE id = ?
            """,
            ("paid", attempt_number, payment_id, now, invoice_id),
        )
        conn.execute("UPDATE customers SET delinquent = 0 WHERE id = ?", (invoice["customer_id"],))
        response = {
            "invoice_id": invoice_id,
            "status": "paid",
            "attempt_count": attempt_number,
            "payment_id": payment_id,
        }
        insert_event(
            conn,
            event_type="invoice.payment_retry_succeeded",
            object_type="invoice",
            object_id=invoice_id,
            payload=response,
            created_at=now,
        )
        insert_event(
            conn,
            event_type="invoice.paid",
            object_type="invoice",
            object_id=invoice_id,
            payload=response,
            created_at=now,
        )
        insert_audit(
            conn,
            actor=actor_email,
            action="billing.retry_invoice",
            object_type="invoice",
            object_id=invoice_id,
            request={},
            response=response,
            created_at=now,
        )
        return _ok(response)


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _message_count(conn, ticket_id: str) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM ticket_messages WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return int(row["count"])


def _merge_tags(existing: list[str], additions: list[str]) -> list[str]:
    return sorted({*existing, *additions})


def _active_refund_policy(conn) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT body_json FROM policies
        WHERE policy_key = ? AND active = 1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        ("standard_refund_policy",),
    ).fetchone()
    return loads_json(row["body_json"]) if row is not None else None


def _refund_policy_error(payment, reason: str, policy: dict[str, Any], now: str) -> dict[str, Any] | None:
    if reason == policy.get("duplicate_payment_reason", "duplicate"):
        return None

    window_days = int(policy.get("refund_window_days", 0))
    if window_days <= 0:
        return None

    paid_at = datetime.fromisoformat(payment["created_at"].replace("Z", "+00:00"))
    checked_at = datetime.fromisoformat(now.replace("Z", "+00:00"))
    age_days = (checked_at - paid_at).days
    if age_days > window_days:
        return _error(
            "refund_not_allowed_by_policy",
            "Payment is outside the standard refund window and needs policy handling instead of direct refund.",
            {"payment_id": payment["id"], "age_days": age_days, "refund_window_days": window_days},
        )
    return None


def _next_refund_id(conn, payment_id: str) -> str:
    row = conn.execute("SELECT COUNT(*) AS count FROM refunds WHERE payment_id = ?", (payment_id,)).fetchone()
    return f"re_{payment_id}_{int(row['count']) + 1}"
