"""State verifiers for billing_support_v0 episodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api_gym.worlds.billing_support_v0.state import RUN_METADATA_NAME, STATE_DB_NAME, connect, loads_json


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    scenario: str
    checks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "scenario": self.scenario, "checks": self.checks}


def verify_run(run_dir: Path) -> VerificationResult:
    run_dir = run_dir.resolve()
    metadata_path = run_dir / RUN_METADATA_NAME
    if not metadata_path.exists():
        return VerificationResult(
            ok=False,
            scenario="unknown",
            checks=[_fail("run_metadata_exists", f"Missing {RUN_METADATA_NAME}.")],
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    db_path = run_dir / metadata.get("state_db", STATE_DB_NAME)
    if not db_path.exists():
        return VerificationResult(
            ok=False,
            scenario=metadata.get("scenario", "unknown"),
            checks=[_fail("state_db_exists", f"Missing state database at {db_path}.")],
        )

    with connect(db_path) as conn:
        expected = _expected_resolution(conn)
        if expected is None:
            return VerificationResult(
                ok=False,
                scenario=metadata.get("scenario", "unknown"),
                checks=[_fail("expected_resolution_exists", "Missing hidden expected resolution event.")],
            )
        scenario = expected["scenario"]
        if scenario == "duplicate_payment_refund":
            checks = _verify_duplicate_payment_refund(conn, expected)
        elif scenario == "failed_invoice_retryable":
            checks = _verify_failed_invoice_retryable(conn, expected)
        elif scenario == "refund_not_allowed_policy":
            checks = _verify_refund_not_allowed_policy(conn, expected)
        else:
            checks = [_fail("scenario_supported", f"Unsupported verifier scenario '{scenario}'.")]
        return VerificationResult(ok=all(check["ok"] for check in checks), scenario=scenario, checks=checks)


def _verify_duplicate_payment_refund(conn, expected: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    duplicate_payment_id = expected["refund_payment_id"]
    original_payment_id = expected["do_not_refund_payment_id"]
    expected_amount = expected["refund_amount"]
    ticket_id = expected["ticket_id"]

    refund = conn.execute(
        """
        SELECT * FROM refunds
        WHERE payment_id = ? AND amount = ? AND reason = ? AND status = ?
        """,
        (duplicate_payment_id, expected_amount, expected["refund_reason"], "succeeded"),
    ).fetchone()
    checks.append(_check(refund is not None, "duplicate_payment_refunded", "Duplicate payment has a succeeded duplicate refund."))

    original_refunds = conn.execute("SELECT COUNT(*) AS count FROM refunds WHERE payment_id = ?", (original_payment_id,)).fetchone()
    checks.append(
        _check(
            int(original_refunds["count"]) == 0,
            "original_payment_not_refunded",
            "Original invoice payment was not refunded.",
        )
    )

    reply_ok = _ticket_has_public_agent_reply(conn, ticket_id, ["refund"])
    checks.append(_check(reply_ok, "ticket_reply_mentions_refund", "Ticket has a public agent reply mentioning the refund."))
    return checks


def _verify_failed_invoice_retryable(conn, expected: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    invoice_id = expected["invoice_id"]
    ticket_id = expected["ticket_id"]

    invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    checks.append(
        _check(
            invoice is not None and invoice["status"] == "paid" and invoice["amount_remaining"] == 0,
            "invoice_paid_after_retry",
            "Invoice is paid with no remaining balance.",
        )
    )
    event = conn.execute(
        """
        SELECT * FROM events
        WHERE event_type = ? AND object_type = ? AND object_id = ?
        """,
        ("invoice.payment_retry_succeeded", "invoice", invoice_id),
    ).fetchone()
    checks.append(_check(event is not None, "retry_event_recorded", "Invoice retry success event was recorded."))

    reply_ok = _ticket_has_public_agent_reply(conn, ticket_id, ["retry"])
    checks.append(_check(reply_ok, "ticket_reply_mentions_retry", "Ticket has a public agent reply mentioning the retry."))

    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    checks.append(
        _check(
            ticket is not None and ticket["status"] in {"solved", "closed"},
            "ticket_closed_after_retry",
            "Ticket is solved or closed after the successful retry.",
        )
    )
    return checks


def _verify_refund_not_allowed_policy(conn, expected: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    payment_id = expected["payment_id"]
    ticket_id = expected["ticket_id"]

    refunds = conn.execute("SELECT COUNT(*) AS count FROM refunds WHERE payment_id = ?", (payment_id,)).fetchone()
    checks.append(_check(int(refunds["count"]) == 0, "no_refund_created", "No refund was created for the policy-blocked payment."))

    explanation = _ticket_has_public_agent_reply(
        conn,
        ticket_id,
        ["policy"],
        any_terms=["not eligible", "outside", "120", "refund window", "cannot refund", "can't refund"],
    )
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    tags = set(loads_json(ticket["tags_json"]) or []) if ticket is not None else set()
    escalated = bool(tags.intersection(expected["acceptable_tags"])) or (
        ticket is not None and ticket["assignee_group"] == "billing-escalations"
    )
    status_handled = ticket is not None and ticket["status"] in {"pending", "solved", "closed"}
    checks.append(
        _check(
            explanation and (status_handled or escalated),
            "policy_explained_or_escalated",
            "Ticket explains the refund policy and is either handled or escalated.",
        )
    )
    return checks


def _expected_resolution(conn) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT payload_json FROM events
        WHERE event_type = ? AND visible_to_agent = 0
        ORDER BY id DESC
        LIMIT 1
        """,
        ("expected_resolution.created",),
    ).fetchone()
    return loads_json(row["payload_json"]) if row is not None else None


def _ticket_has_public_agent_reply(
    conn,
    ticket_id: str,
    required_terms: list[str],
    *,
    any_terms: list[str] | None = None,
) -> bool:
    rows = conn.execute(
        """
        SELECT body FROM ticket_messages
        WHERE ticket_id = ? AND author_type = ? AND public = 1
        """,
        (ticket_id, "agent"),
    ).fetchall()
    for row in rows:
        body = row["body"].lower()
        if all(term.lower() in body for term in required_terms):
            if any_terms is None or any(term.lower() in body for term in any_terms):
                return True
    return False


def _check(condition: bool, name: str, message: str) -> dict[str, Any]:
    return {"ok": bool(condition), "name": name, "message": message}


def _fail(name: str, message: str) -> dict[str, Any]:
    return _check(False, name, message)
