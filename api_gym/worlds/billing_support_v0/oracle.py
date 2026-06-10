"""Scripted oracle resolver for billing_support_v0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api_gym.worlds.billing_support_v0.state import connect, loads_json, resolve_state_db_path
from api_gym.worlds.billing_support_v0.tools import dispatch_tool_call
from api_gym.worlds.billing_support_v0.verifier import verify_run


def resolve_run(run_dir: Path, *, policy: str = "oracle") -> dict[str, Any]:
    """Resolve one sampled run through the public tool dispatcher."""
    if policy != "oracle":
        return _error("unsupported_policy", "Only the oracle resolver policy is supported.", {"policy": policy})

    run_dir = run_dir.resolve()
    db_path = resolve_state_db_path(run_dir)
    expected = _expected_resolution(db_path)
    if expected is None:
        return _error("expected_resolution_missing", "Run is missing hidden expected resolution state.", {"run": str(run_dir)})

    scenario = expected.get("scenario")
    if scenario == "duplicate_payment_refund":
        calls = _duplicate_payment_calls(expected)
    elif scenario == "failed_invoice_retryable":
        calls = _retryable_invoice_calls(expected)
    elif scenario == "refund_not_allowed_policy":
        calls = _policy_blocked_calls(expected)
    else:
        return _error("unsupported_scenario", "Oracle cannot resolve this scenario.", {"scenario": scenario})

    tool_results = []
    for call in calls:
        result = dispatch_tool_call(db_path, call)
        tool_results.append({"name": call["name"], "arguments": call["arguments"], "result": result})

    verifier_result = verify_run(run_dir).to_dict()
    return {
        "ok": verifier_result["ok"],
        "policy": policy,
        "scenario": scenario,
        "tool_results": tool_results,
        "verifier_result": verifier_result,
    }


def _expected_resolution(db_path: Path) -> dict[str, Any] | None:
    with connect(db_path) as conn:
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


def _duplicate_payment_calls(expected: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": "support_get_ticket", "arguments": {"ticket_id": expected["ticket_id"]}},
        {"name": "billing_get_invoice", "arguments": {"invoice_id": expected["invoice_id"]}},
        {"name": "billing_get_payment", "arguments": {"payment_id": expected["refund_payment_id"]}},
        {
            "name": "billing_create_refund",
            "arguments": {
                "payment_id": expected["refund_payment_id"],
                "amount": expected["refund_amount"],
                "reason": expected["refund_reason"],
                "ticket_id": expected["ticket_id"],
            },
        },
        {
            "name": "support_add_reply",
            "arguments": {
                "ticket_id": expected["ticket_id"],
                "body": "The duplicate payment was confirmed and a refund has been issued.",
            },
        },
        {"name": "support_close_ticket", "arguments": {"ticket_id": expected["ticket_id"]}},
    ]


def _retryable_invoice_calls(expected: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": "support_get_ticket", "arguments": {"ticket_id": expected["ticket_id"]}},
        {"name": "billing_get_invoice", "arguments": {"invoice_id": expected["invoice_id"]}},
        {"name": "billing_get_payment", "arguments": {"payment_id": expected["failed_payment_id"]}},
        {"name": "billing_retry_invoice", "arguments": {"invoice_id": expected["invoice_id"]}},
        {
            "name": "support_add_reply",
            "arguments": {
                "ticket_id": expected["ticket_id"],
                "body": "The invoice retry succeeded and the invoice is now paid.",
            },
        },
        {"name": "support_close_ticket", "arguments": {"ticket_id": expected["ticket_id"]}},
    ]


def _policy_blocked_calls(expected: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": "support_get_ticket", "arguments": {"ticket_id": expected["ticket_id"]}},
        {"name": "billing_get_invoice", "arguments": {"invoice_id": expected["invoice_id"]}},
        {"name": "billing_get_payment", "arguments": {"payment_id": expected["payment_id"]}},
        {
            "name": "billing_create_refund",
            "arguments": {
                "payment_id": expected["payment_id"],
                "reason": "requested_by_customer",
                "ticket_id": expected["ticket_id"],
            },
        },
        {
            "name": "support_add_reply",
            "arguments": {
                "ticket_id": expected["ticket_id"],
                "body": (
                    "This payment is outside the 120 day refund window, so policy says it is not eligible "
                    "for a refund. I am escalating for billing policy review."
                ),
            },
        },
        {
            "name": "support_escalate_ticket",
            "arguments": {
                "ticket_id": expected["ticket_id"],
                "reason": "Customer requested billing review outside the refund policy window.",
            },
        },
    ]


def _error(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}
