"""OpenAI-compatible tool schemas and dispatcher for billing_support_v0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from api_gym.worlds.billing_support_v0 import services

ToolHandler = Callable[[Path, dict[str, Any]], dict[str, Any]]


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "support_get_ticket",
            "description": "Fetch a support ticket with customer and agent messages.",
            "parameters": _schema({"ticket_id": {"type": "string"}}, ["ticket_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "support_add_reply",
            "description": (
                "Add an agent reply to a support ticket. Public replies are customer-visible by default; "
                "use this tool to notify the customer or explain billing policy and refund decisions."
            ),
            "parameters": _schema(
                {
                    "ticket_id": {"type": "string"},
                    "body": {
                        "type": "string",
                        "description": "Reply text to send to the customer when public is true.",
                    },
                    "public": {"type": "boolean", "default": True},
                },
                ["ticket_id", "body"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "support_close_ticket",
            "description": "Mark a support ticket solved.",
            "parameters": _schema({"ticket_id": {"type": "string"}}, ["ticket_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "support_tag_ticket",
            "description": "Add one or more tags to a support ticket.",
            "parameters": _schema(
                {"ticket_id": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}},
                ["ticket_id", "tags"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "support_escalate_ticket",
            "description": (
                "Escalate a ticket to internal billing policy review. Escalation changes internal "
                "assignment/review state only and does not send a customer-visible reply. Call "
                "support_add_reply when the customer must be notified or when a policy/refund-window "
                "explanation is needed."
            ),
            "parameters": _schema(
                {
                    "ticket_id": {"type": "string"},
                    "reason": {
                        "type": "string",
                        "description": (
                            "Internal escalation rationale for reviewers; not customer-visible text "
                            "and not a substitute for support_add_reply."
                        ),
                    },
                },
                ["ticket_id", "reason"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "billing_get_customer",
            "description": "Fetch a billing customer with subscriptions and invoices.",
            "parameters": _schema({"customer_id": {"type": "string"}}, ["customer_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "billing_get_invoice",
            "description": "Fetch a billing invoice with related payments.",
            "parameters": _schema({"invoice_id": {"type": "string"}}, ["invoice_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "billing_get_payment",
            "description": "Fetch a payment with refunds and remaining refundable amount.",
            "parameters": _schema({"payment_id": {"type": "string"}}, ["payment_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "billing_create_refund",
            "description": (
                "Create a refund for a succeeded payment if policy allows it. Use reason=duplicate "
                "for duplicate charges/payments, reason=requested_by_customer for ordinary "
                "customer-requested refunds that are not duplicates or fraud, and reason=fraudulent "
                "only for suspected fraud."
            ),
            "parameters": _schema(
                {
                    "payment_id": {"type": "string"},
                    "amount": {"type": "integer", "minimum": 1},
                    "reason": {
                        "type": "string",
                        "description": (
                            "Use duplicate for duplicate charges/payments; requested_by_customer for "
                            "ordinary customer-requested refunds that are not duplicates or fraud; "
                            "fraudulent only for suspected fraud."
                        ),
                        "enum": ["duplicate", "fraudulent", "requested_by_customer"],
                    },
                    "ticket_id": {"type": "string"},
                },
                ["payment_id", "reason"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "billing_retry_invoice",
            "description": "Retry payment collection for an automatically collected unpaid invoice.",
            "parameters": _schema({"invoice_id": {"type": "string"}}, ["invoice_id"]),
        },
    },
]


def dispatch_tool_call(db_path: Path, tool_call: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one OpenAI-compatible function call against a run DB."""
    name, arguments = _extract_name_and_arguments(tool_call)
    if name is None:
        return _tool_error("missing_tool_name", "Tool call is missing a function name.", {"tool_call": tool_call})
    if arguments is None:
        return _tool_error("invalid_tool_arguments", "Tool arguments must be a JSON object.", {"tool_name": name})
    return dispatch_tool(db_path, name=name, arguments=arguments)


def dispatch_tool(db_path: Path, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return _tool_error("unknown_tool", "Tool name is not registered for this world.", {"tool_name": name})
    try:
        return handler(db_path, arguments)
    except KeyError as exc:
        return _tool_error(
            "missing_tool_argument",
            "A required tool argument is missing.",
            {"tool_name": name, "argument": str(exc).strip("'")},
        )
    except (TypeError, ValueError) as exc:
        return _tool_error(
            "invalid_tool_arguments",
            "Tool arguments do not match the tool schema.",
            {"tool_name": name, "message": str(exc)},
        )


def _extract_name_and_arguments(tool_call: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    function = tool_call.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        raw_arguments = function.get("arguments", {})
    else:
        name = tool_call.get("name")
        raw_arguments = tool_call.get("arguments", {})

    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return str(name) if name is not None else None, None
    else:
        arguments = raw_arguments

    if not isinstance(arguments, dict):
        return str(name) if name is not None else None, None
    return str(name) if name is not None else None, arguments


def _support_get_ticket(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.get_ticket(db_path, str(arguments["ticket_id"]))


def _support_add_reply(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.add_reply(
        db_path,
        ticket_id=str(arguments["ticket_id"]),
        body=str(arguments["body"]),
        public=bool(arguments.get("public", True)),
    )


def _support_close_ticket(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.close_ticket(db_path, ticket_id=str(arguments["ticket_id"]))


def _support_tag_ticket(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    tags = arguments["tags"]
    if not isinstance(tags, list):
        raise TypeError("tags must be a list")
    return services.tag_ticket(db_path, ticket_id=str(arguments["ticket_id"]), tags=[str(tag) for tag in tags])


def _support_escalate_ticket(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.escalate_ticket(db_path, ticket_id=str(arguments["ticket_id"]), reason=str(arguments["reason"]))


def _billing_get_customer(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.get_customer(db_path, str(arguments["customer_id"]))


def _billing_get_invoice(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.get_invoice(db_path, str(arguments["invoice_id"]))


def _billing_get_payment(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.get_payment(db_path, str(arguments["payment_id"]))


def _billing_create_refund(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    amount = arguments.get("amount")
    return services.create_refund(
        db_path,
        payment_id=str(arguments["payment_id"]),
        amount=None if amount is None else int(amount),
        reason=str(arguments["reason"]),
        ticket_id=None if arguments.get("ticket_id") is None else str(arguments.get("ticket_id")),
    )


def _billing_retry_invoice(db_path: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    return services.retry_invoice(db_path, invoice_id=str(arguments["invoice_id"]))


def _tool_error(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details}}


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "support_get_ticket": _support_get_ticket,
    "support_add_reply": _support_add_reply,
    "support_close_ticket": _support_close_ticket,
    "support_tag_ticket": _support_tag_ticket,
    "support_escalate_ticket": _support_escalate_ticket,
    "billing_get_customer": _billing_get_customer,
    "billing_get_invoice": _billing_get_invoice,
    "billing_get_payment": _billing_get_payment,
    "billing_create_refund": _billing_create_refund,
    "billing_retry_invoice": _billing_retry_invoice,
}
