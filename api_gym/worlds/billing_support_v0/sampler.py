"""Deterministic scenario sampler for billing_support_v0."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from api_gym.worlds.billing_support_v0.state import (
    RUN_METADATA_NAME,
    STATE_DB_NAME,
    TASK_NAME,
    connect,
    dumps_json,
    initialize_db,
    insert_event,
)

WORLD = "billing_support_v0"
WORLD_ID = "billing-support-v0"
BASE_TIME = datetime(2026, 2, 18, 15, 30, tzinfo=timezone.utc)
AGENT_EMAIL = "agent@billing-support.example"
SUPPORT_EMAIL = "support@api-gym.example"


@dataclass(frozen=True)
class SampledEpisode:
    run_dir: Path
    db_path: Path
    task_path: Path
    run_metadata_path: Path
    task: dict[str, object]


ScenarioBuilder = Callable[[Path, int], dict[str, object]]


def sample_episode(*, scenario: str, seed: int, out_dir: Path) -> SampledEpisode:
    """Create one deterministic SQLite-backed episode run."""
    if scenario not in SCENARIOS:
        supported = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unsupported billing_support_v0 scenario '{scenario}'. Supported: {supported}")

    out_dir = out_dir.resolve()
    db_path = out_dir / STATE_DB_NAME
    task_path = out_dir / TASK_NAME
    run_metadata_path = out_dir / RUN_METADATA_NAME

    if db_path.exists() or task_path.exists() or run_metadata_path.exists():
        raise FileExistsError(f"Run directory already contains API Gym state files: {out_dir}")

    initialize_db(db_path)
    task = SCENARIOS[scenario](db_path, seed)

    out_dir.mkdir(parents=True, exist_ok=True)
    task_path.write_text(json.dumps(task, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_metadata = {
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": scenario,
        "seed": seed,
        "state_db": STATE_DB_NAME,
        "task": TASK_NAME,
    }
    run_metadata_path.write_text(json.dumps(run_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return SampledEpisode(
        run_dir=out_dir,
        db_path=db_path,
        task_path=task_path,
        run_metadata_path=run_metadata_path,
        task=task,
    )


def _stable_prefix(scenario: str, seed: int) -> str:
    digest = hashlib.sha256(f"{WORLD}:{scenario}:{seed}".encode("utf-8")).hexdigest()
    return digest[:10]


def _rng(scenario: str, seed: int) -> random.Random:
    digest = hashlib.sha256(f"rng:{WORLD}:{scenario}:{seed}".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _iso(days: int = 0, minutes: int = 0) -> str:
    return (BASE_TIME + timedelta(days=days, minutes=minutes)).isoformat().replace("+00:00", "Z")


def _scenario_context(scenario: str, seed: int) -> dict[str, str]:
    rng = _rng(scenario, seed)
    customer_pool = [
        ("Maya Patel", "maya.patel@example.test", "Northstar Analytics"),
        ("Jon Bell", "jon.bell@example.test", "Cedar Labs"),
        ("Elena Rossi", "elena.rossi@example.test", "Harbor Metrics"),
        ("Sam Rivera", "sam.rivera@example.test", "Brightpath Ops"),
    ]
    name, email, account = rng.choice(customer_pool)
    prefix = _stable_prefix(scenario, seed)
    return {
        "prefix": prefix,
        "account_id": f"acct_{prefix}",
        "customer_id": f"cus_{prefix}",
        "subscription_id": f"sub_{prefix}",
        "ticket_id": f"tkt_{prefix}",
        "customer_name": name,
        "customer_email": email,
        "account_name": account,
    }


def _insert_common_customer(conn, ctx: dict[str, str], *, created_at: str) -> None:
    conn.execute(
        """
        INSERT INTO accounts (id, name, support_plan, default_currency, created_at, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            ctx["account_id"],
            ctx["account_name"],
            "business",
            "usd",
            created_at,
            dumps_json({"crm_segment": "smb", "region": "us"}),
        ),
    )
    conn.execute(
        """
        INSERT INTO customers (
          id, account_id, email, name, phone, default_payment_method, delinquent, created_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ctx["customer_id"],
            ctx["account_id"],
            ctx["customer_email"],
            ctx["customer_name"],
            "+1-415-555-0137",
            "pm_card_visa_4242",
            0,
            created_at,
            dumps_json({"external_crm_id": f"crm_{ctx['prefix']}"}),
        ),
    )
    conn.execute(
        """
        INSERT INTO subscriptions (
          id, customer_id, status, plan_name, current_period_start, current_period_end,
          cancel_at_period_end, created_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ctx["subscription_id"],
            ctx["customer_id"],
            "active",
            "Growth",
            _iso(-20),
            _iso(10),
            0,
            created_at,
            dumps_json({"billing_interval": "month"}),
        ),
    )
    conn.execute(
        """
        INSERT INTO policies (id, policy_key, version, body_json, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "pol_refund_standard_v1",
            "standard_refund_policy",
            "2026-02",
            dumps_json(
                {
                    "refund_window_days": 120,
                    "duplicate_payment_reason": "duplicate",
                    "manual_review_tag": "billing_policy_review",
                    "allowed_reasons": ["duplicate", "fraudulent", "requested_by_customer"],
                    "hard_decline_codes": [
                        "incorrect_number",
                        "lost_card",
                        "pickup_card",
                        "stolen_card",
                        "revocation_of_authorization",
                        "revocation_of_all_authorizations",
                        "authentication_required",
                        "highest_risk_level",
                        "transaction_not_allowed",
                    ],
                }
            ),
            1,
            created_at,
        ),
    )


def _insert_ticket(
    conn,
    ctx: dict[str, str],
    *,
    subject: str,
    customer_body: str,
    tags: list[str],
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO tickets (
          id, customer_id, requester_email, subject, status, priority, assignee_group,
          tags_json, created_at, updated_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ctx["ticket_id"],
            ctx["customer_id"],
            ctx["customer_email"],
            subject,
            "open",
            "normal",
            "billing-support",
            dumps_json(tags),
            created_at,
            created_at,
            dumps_json({"channel": "email"}),
        ),
    )
    conn.execute(
        """
        INSERT INTO ticket_messages (ticket_id, author_type, author_email, body, public, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ctx["ticket_id"], "customer", ctx["customer_email"], customer_body, 1, created_at),
    )
    conn.execute(
        """
        INSERT INTO emails (
          ticket_id, customer_id, to_email, from_email, subject, body, status, provider_message_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ctx["ticket_id"],
            ctx["customer_id"],
            SUPPORT_EMAIL,
            ctx["customer_email"],
            subject,
            customer_body,
            "received",
            f"msg_{ctx['prefix']}_inbound",
            created_at,
        ),
    )


def _build_duplicate_payment_refund(db_path: Path, seed: int) -> dict[str, object]:
    scenario = "duplicate_payment_refund"
    ctx = _scenario_context(scenario, seed)
    invoice_id = f"in_{ctx['prefix']}_01"
    original_payment_id = f"py_{ctx['prefix']}_ok_01"
    duplicate_payment_id = f"py_{ctx['prefix']}_dup_02"
    amount = 4900
    created_at = _iso(-3)

    with connect(db_path) as conn:
        _insert_common_customer(conn, ctx, created_at=created_at)
        conn.execute(
            """
            INSERT INTO invoices (
              id, customer_id, subscription_id, number, status, collection_method, currency,
              amount_due, amount_paid, amount_remaining, attempt_count,
              due_date, paid_at, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                ctx["customer_id"],
                ctx["subscription_id"],
                f"BS-{ctx['prefix'].upper()}-001",
                "paid",
                "charge_automatically",
                "usd",
                amount,
                amount,
                0,
                1,
                _iso(-2),
                _iso(-2, 10),
                created_at,
                dumps_json({"duplicate_payment_candidate": duplicate_payment_id}),
            ),
        )
        conn.execute(
            """
            INSERT INTO payments (
              id, customer_id, invoice_id, amount, currency, status, payment_method,
              payment_intent_id, charge_id, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                original_payment_id,
                ctx["customer_id"],
                invoice_id,
                amount,
                "usd",
                "succeeded",
                "card_visa_4242",
                f"pi_{ctx['prefix']}_01",
                f"ch_{ctx['prefix']}_01",
                _iso(-2, 10),
                dumps_json({"network_status": "approved_by_network"}),
            ),
        )
        conn.execute(
            """
            INSERT INTO payments (
              id, customer_id, invoice_id, amount, currency, status, payment_method,
              payment_intent_id, charge_id, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                duplicate_payment_id,
                ctx["customer_id"],
                invoice_id,
                amount,
                "usd",
                "succeeded",
                "card_visa_4242",
                f"pi_{ctx['prefix']}_02",
                f"ch_{ctx['prefix']}_02",
                _iso(-2, 13),
                dumps_json({"duplicate_of": original_payment_id, "network_status": "approved_by_network"}),
            ),
        )
        conn.execute("UPDATE invoices SET latest_payment_id = ? WHERE id = ?", (original_payment_id, invoice_id))
        _insert_ticket(
            conn,
            ctx,
            subject="Charged twice for the same invoice",
            customer_body=(
                f"I see two card charges for ${amount / 100:.2f} against invoice {invoice_id}. "
                "One looks like a duplicate. Please refund the extra charge."
            ),
            tags=["billing", "refund_request", "duplicate_payment"],
            created_at=_iso(-1),
        )
        expected = {
            "scenario": scenario,
            "ticket_id": ctx["ticket_id"],
            "customer_id": ctx["customer_id"],
            "invoice_id": invoice_id,
            "refund_payment_id": duplicate_payment_id,
            "do_not_refund_payment_id": original_payment_id,
            "refund_amount": amount,
            "refund_reason": "duplicate",
            "reply_must_mention": ["refund"],
        }
        insert_event(
            conn,
            event_type="expected_resolution.created",
            object_type="scenario",
            object_id=scenario,
            payload=expected,
            created_at=_iso(-1),
            visible_to_agent=False,
        )

    return {
        "world": WORLD,
        "scenario": scenario,
        "seed": seed,
        "ticket_id": ctx["ticket_id"],
        "prompt": (
            f"Resolve ticket {ctx['ticket_id']} for {ctx['customer_name']}. "
            f"The customer reports duplicate charges for invoice {invoice_id}. "
            "Use the billing and support APIs to identify the extra payment, refund only the duplicate "
            "payment if eligible, then reply to the customer and close the ticket when done."
        ),
    }


def _build_failed_invoice_retryable(db_path: Path, seed: int) -> dict[str, object]:
    scenario = "failed_invoice_retryable"
    ctx = _scenario_context(scenario, seed)
    invoice_id = f"in_{ctx['prefix']}_retry"
    failed_payment_id = f"py_{ctx['prefix']}_failed_01"
    amount = 12900
    created_at = _iso(-8)

    with connect(db_path) as conn:
        _insert_common_customer(conn, ctx, created_at=created_at)
        conn.execute(
            "UPDATE customers SET delinquent = 1 WHERE id = ?",
            (ctx["customer_id"],),
        )
        conn.execute(
            """
            INSERT INTO invoices (
              id, customer_id, subscription_id, number, status, collection_method, currency,
              amount_due, amount_paid, amount_remaining, attempt_count, next_payment_attempt,
              due_date, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                ctx["customer_id"],
                ctx["subscription_id"],
                f"BS-{ctx['prefix'].upper()}-002",
                "open",
                "charge_automatically",
                "usd",
                amount,
                0,
                amount,
                1,
                _iso(1),
                _iso(-1),
                created_at,
                dumps_json({"latest_failure": "invoice.payment_failed"}),
            ),
        )
        conn.execute(
            """
            INSERT INTO payments (
              id, customer_id, invoice_id, amount, currency, status, payment_method,
              payment_intent_id, charge_id, decline_code, failure_message, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                failed_payment_id,
                ctx["customer_id"],
                invoice_id,
                amount,
                "usd",
                "failed",
                "card_visa_4242",
                f"pi_{ctx['prefix']}_failed",
                f"ch_{ctx['prefix']}_failed",
                "insufficient_funds",
                "The card was declined because it had insufficient funds.",
                _iso(-1, -30),
                dumps_json({"retryable": True}),
            ),
        )
        conn.execute("UPDATE invoices SET latest_payment_id = ? WHERE id = ?", (failed_payment_id, invoice_id))
        _insert_ticket(
            conn,
            ctx,
            subject="Can you retry my invoice payment?",
            customer_body=(
                f"My invoice {invoice_id} failed yesterday after I moved funds into the account. "
                "Please retry the payment and let me know whether it worked."
            ),
            tags=["billing", "failed_invoice", "payment_retry"],
            created_at=_iso(0),
        )
        expected = {
            "scenario": scenario,
            "ticket_id": ctx["ticket_id"],
            "customer_id": ctx["customer_id"],
            "invoice_id": invoice_id,
            "failed_payment_id": failed_payment_id,
            "expected_invoice_status": "paid",
            "reply_must_mention": ["retry"],
            "ticket_status": "solved",
        }
        insert_event(
            conn,
            event_type="expected_resolution.created",
            object_type="scenario",
            object_id=scenario,
            payload=expected,
            created_at=_iso(0),
            visible_to_agent=False,
        )

    return {
        "world": WORLD,
        "scenario": scenario,
        "seed": seed,
        "ticket_id": ctx["ticket_id"],
        "prompt": (
            f"Resolve ticket {ctx['ticket_id']} for {ctx['customer_name']}. "
            f"The customer says invoice {invoice_id} failed after a temporary funding issue and asks you to retry it. "
            "Use the billing API to inspect retryability and retry the invoice only if the decline is retryable. "
            "Then update the ticket with the outcome and close it if the invoice is paid."
        ),
    }


def _build_refund_not_allowed_policy(db_path: Path, seed: int) -> dict[str, object]:
    scenario = "refund_not_allowed_policy"
    ctx = _scenario_context(scenario, seed)
    invoice_id = f"in_{ctx['prefix']}_old"
    payment_id = f"py_{ctx['prefix']}_old_01"
    amount = 29900
    created_at = _iso(-240)

    with connect(db_path) as conn:
        _insert_common_customer(conn, ctx, created_at=created_at)
        conn.execute(
            """
            INSERT INTO invoices (
              id, customer_id, subscription_id, number, status, collection_method, currency,
              amount_due, amount_paid, amount_remaining, attempt_count,
              due_date, paid_at, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                ctx["customer_id"],
                ctx["subscription_id"],
                f"BS-{ctx['prefix'].upper()}-003",
                "paid",
                "charge_automatically",
                "usd",
                amount,
                amount,
                0,
                1,
                _iso(-220),
                _iso(-220),
                created_at,
                dumps_json({"billing_period": "annual", "refund_window_days": 120}),
            ),
        )
        conn.execute(
            """
            INSERT INTO payments (
              id, customer_id, invoice_id, amount, currency, status, payment_method,
              payment_intent_id, charge_id, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payment_id,
                ctx["customer_id"],
                invoice_id,
                amount,
                "usd",
                "succeeded",
                "card_visa_4242",
                f"pi_{ctx['prefix']}_old",
                f"ch_{ctx['prefix']}_old",
                _iso(-220),
                dumps_json({"service_period_completed": True}),
            ),
        )
        conn.execute("UPDATE invoices SET latest_payment_id = ? WHERE id = ?", (payment_id, invoice_id))
        _insert_ticket(
            conn,
            ctx,
            subject="Refund request for old annual invoice",
            customer_body=(
                f"I paid invoice {invoice_id} months ago but stopped using the product. "
                "Please refund the annual charge."
            ),
            tags=["billing", "refund_request", "policy_review"],
            created_at=_iso(0),
        )
        expected = {
            "scenario": scenario,
            "ticket_id": ctx["ticket_id"],
            "customer_id": ctx["customer_id"],
            "invoice_id": invoice_id,
            "payment_id": payment_id,
            "must_not_refund": True,
            "policy_key": "standard_refund_policy",
            "refund_window_days": 120,
            "acceptable_tags": ["billing_policy_review", "escalated"],
            "reply_must_explain_policy": True,
        }
        insert_event(
            conn,
            event_type="expected_resolution.created",
            object_type="scenario",
            object_id=scenario,
            payload=expected,
            created_at=_iso(0),
            visible_to_agent=False,
        )

    return {
        "world": WORLD,
        "scenario": scenario,
        "seed": seed,
        "ticket_id": ctx["ticket_id"],
        "prompt": (
            f"Resolve ticket {ctx['ticket_id']} for {ctx['customer_name']}. "
            f"The customer asks for a refund on old paid invoice {invoice_id}. "
            "Inspect the customer, payment, invoice, and policy state. Do not issue a refund if policy forbids it; "
            "instead explain the policy and either close the ticket or escalate for billing policy review."
        ),
    }


SCENARIOS: dict[str, ScenarioBuilder] = {
    "duplicate_payment_refund": _build_duplicate_payment_refund,
    "failed_invoice_retryable": _build_failed_invoice_retryable,
    "refund_not_allowed_policy": _build_refund_not_allowed_policy,
}
