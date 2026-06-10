from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from api_gym.worlds.billing_support_v0.sampler import SCENARIOS, sample_episode
from api_gym.worlds.billing_support_v0.services import (
    add_reply,
    close_ticket,
    create_refund,
    escalate_ticket,
    get_payment,
    get_ticket,
    retry_invoice,
)
from api_gym.worlds.billing_support_v0.state import loads_json
from api_gym.worlds.billing_support_v0.verifier import verify_run


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_sampler_is_deterministic(tmp_path: Path, scenario: str) -> None:
    first = sample_episode(scenario=scenario, seed=42, out_dir=tmp_path / "first")
    second = sample_episode(scenario=scenario, seed=42, out_dir=tmp_path / "second")

    assert first.task == second.task
    assert _dump_sqlite(first.db_path) == _dump_sqlite(second.db_path)


def test_all_phase_1_scenarios_are_registered() -> None:
    assert set(SCENARIOS) == {
        "duplicate_payment_refund",
        "failed_invoice_retryable",
        "refund_not_allowed_policy",
    }


def test_duplicate_refund_service_mutates_state(tmp_path: Path) -> None:
    episode = sample_episode(scenario="duplicate_payment_refund", seed=9, out_dir=tmp_path / "run")
    expected = _expected(episode.db_path)

    ticket = get_ticket(episode.db_path, expected["ticket_id"])
    assert ticket["ok"] is True
    assert ticket["data"]["status"] == "open"
    assert ticket["data"]["messages"][0]["author_type"] == "customer"

    refund = create_refund(
        episode.db_path,
        payment_id=expected["refund_payment_id"],
        amount=expected["refund_amount"],
        reason="duplicate",
        ticket_id=expected["ticket_id"],
    )
    assert refund["ok"] is True

    payment = get_payment(episode.db_path, expected["refund_payment_id"])
    assert payment["ok"] is True
    assert payment["data"]["refunded_amount"] == expected["refund_amount"]
    assert payment["data"]["refundable_amount"] == 0

    reply = add_reply(
        episode.db_path,
        ticket_id=expected["ticket_id"],
        body="We found the duplicate card payment and issued a refund for the extra charge.",
    )
    assert reply["ok"] is True
    assert close_ticket(episode.db_path, ticket_id=expected["ticket_id"])["ok"] is True

    with sqlite3.connect(episode.db_path) as conn:
        sent_email_count = conn.execute("SELECT COUNT(*) FROM emails WHERE status = 'sent'").fetchone()[0]
    assert sent_email_count == 1


@pytest.mark.parametrize(
    "scenario, resolver",
    [
        ("duplicate_payment_refund", "_resolve_duplicate_payment"),
        ("failed_invoice_retryable", "_resolve_retryable_invoice"),
        ("refund_not_allowed_policy", "_resolve_policy_blocked_refund"),
    ],
)
def test_verifier_fails_then_passes_for_all_scenarios(tmp_path: Path, scenario: str, resolver: str) -> None:
    episode = sample_episode(scenario=scenario, seed=3, out_dir=tmp_path / scenario)

    initial = verify_run(episode.run_dir)
    assert initial.ok is False
    assert any(not check["ok"] for check in initial.checks)

    globals()[resolver](episode.db_path)

    final = verify_run(episode.run_dir)
    assert final.ok is True


def test_refund_policy_returns_agent_readable_error_without_mutation(tmp_path: Path) -> None:
    episode = sample_episode(scenario="refund_not_allowed_policy", seed=11, out_dir=tmp_path / "run")
    expected = _expected(episode.db_path)

    result = create_refund(
        episode.db_path,
        payment_id=expected["payment_id"],
        amount=29900,
        reason="requested_by_customer",
        ticket_id=expected["ticket_id"],
    )

    assert result == {
        "ok": False,
        "error": {
            "code": "refund_not_allowed_by_policy",
            "message": "Payment is outside the standard refund window and needs policy handling instead of direct refund.",
            "details": {
                "payment_id": expected["payment_id"],
                "age_days": result["error"]["details"]["age_days"],
                "refund_window_days": 120,
            },
        },
    }
    with sqlite3.connect(episode.db_path) as conn:
        refund_count = conn.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]
    assert refund_count == 0


def _resolve_duplicate_payment(db_path: Path) -> None:
    expected = _expected(db_path)
    assert create_refund(
        db_path,
        payment_id=expected["refund_payment_id"],
        amount=expected["refund_amount"],
        reason="duplicate",
        ticket_id=expected["ticket_id"],
    )["ok"]
    assert add_reply(
        db_path,
        ticket_id=expected["ticket_id"],
        body="The duplicate payment was confirmed and a refund has been issued.",
    )["ok"]
    assert close_ticket(db_path, ticket_id=expected["ticket_id"])["ok"]


def _resolve_retryable_invoice(db_path: Path) -> None:
    expected = _expected(db_path)
    assert retry_invoice(db_path, invoice_id=expected["invoice_id"])["ok"]
    assert add_reply(
        db_path,
        ticket_id=expected["ticket_id"],
        body="The invoice retry succeeded and the invoice is now paid.",
    )["ok"]
    assert close_ticket(db_path, ticket_id=expected["ticket_id"])["ok"]


def _resolve_policy_blocked_refund(db_path: Path) -> None:
    expected = _expected(db_path)
    blocked = create_refund(
        db_path,
        payment_id=expected["payment_id"],
        amount=29900,
        reason="requested_by_customer",
        ticket_id=expected["ticket_id"],
    )
    assert blocked["ok"] is False
    assert blocked["error"]["code"] == "refund_not_allowed_by_policy"
    assert add_reply(
        db_path,
        ticket_id=expected["ticket_id"],
        body=(
            "This payment is outside the 120 day refund window, so policy says it is not eligible "
            "for a refund. I am escalating for billing policy review."
        ),
    )["ok"]
    assert escalate_ticket(
        db_path,
        ticket_id=expected["ticket_id"],
        reason="Customer requested billing review outside the refund policy window.",
    )["ok"]


def _expected(db_path: Path) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT payload_json FROM events
            WHERE event_type = 'expected_resolution.created'
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
    assert row is not None
    return loads_json(row[0])


def _dump_sqlite(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return list(conn.iterdump())
