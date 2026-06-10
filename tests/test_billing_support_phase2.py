from __future__ import annotations

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api_gym.runner.openai_compatible import run_openai_compatible_agent
from api_gym.worlds.billing_support_v0.http import create_app
from api_gym.worlds.billing_support_v0.oracle import resolve_run
from api_gym.worlds.billing_support_v0.sampler import SCENARIOS, sample_episode
from api_gym.worlds.billing_support_v0.services import get_ticket
from api_gym.worlds.billing_support_v0.state import loads_json
from api_gym.worlds.billing_support_v0.tools import TOOL_DEFINITIONS, dispatch_tool_call
from api_gym.worlds.billing_support_v0.verifier import verify_run


EXPECTED_TOOL_NAMES = {
    "support_get_ticket",
    "support_add_reply",
    "support_close_ticket",
    "support_tag_ticket",
    "support_escalate_ticket",
    "billing_get_customer",
    "billing_get_invoice",
    "billing_get_payment",
    "billing_create_refund",
    "billing_retry_invoice",
}


def test_http_endpoints_mutate_sqlite_and_return_service_errors(tmp_path: Path) -> None:
    episode = sample_episode(scenario="duplicate_payment_refund", seed=1, out_dir=tmp_path / "run")
    expected = _expected(episode.db_path)
    client = TestClient(create_app(episode.run_dir))

    ticket = client.get(f"/support/tickets/{expected['ticket_id']}").json()
    assert ticket["ok"] is True
    assert ticket["data"]["id"] == expected["ticket_id"]

    refund = client.post(
        "/billing/refunds",
        json={
            "payment_id": expected["refund_payment_id"],
            "amount": expected["refund_amount"],
            "reason": "duplicate",
            "ticket_id": expected["ticket_id"],
        },
    ).json()
    assert refund["ok"] is True
    assert refund["data"]["payment_id"] == expected["refund_payment_id"]

    payment = client.get(f"/billing/payments/{expected['refund_payment_id']}").json()
    assert payment["ok"] is True
    assert payment["data"]["refunded_amount"] == expected["refund_amount"]

    missing_ticket = client.post("/support/tickets/tkt_missing/reply", json={"body": "Hello"}).json()
    assert missing_ticket == {
        "ok": False,
        "error": {
            "code": "ticket_not_found",
            "message": "Ticket does not exist.",
            "details": {"ticket_id": "tkt_missing"},
        },
    }


def test_tool_schemas_include_expected_names_and_dispatch_mutates_sqlite(tmp_path: Path) -> None:
    episode = sample_episode(scenario="refund_not_allowed_policy", seed=2, out_dir=tmp_path / "run")
    expected = _expected(episode.db_path)

    tool_names = {tool["function"]["name"] for tool in TOOL_DEFINITIONS}
    assert tool_names == EXPECTED_TOOL_NAMES
    for tool in TOOL_DEFINITIONS:
        assert tool["type"] == "function"
        assert tool["function"]["parameters"]["type"] == "object"

    result = dispatch_tool_call(
        episode.db_path,
        {
            "name": "support_tag_ticket",
            "arguments": {"ticket_id": expected["ticket_id"], "tags": ["agent_checked"]},
        },
    )
    assert result["ok"] is True

    ticket = get_ticket(episode.db_path, expected["ticket_id"])
    assert ticket["ok"] is True
    assert "agent_checked" in ticket["data"]["tags"]

    unknown = dispatch_tool_call(episode.db_path, {"name": "missing_tool", "arguments": {}})
    assert unknown["ok"] is False
    assert unknown["error"]["code"] == "unknown_tool"


def test_fresh_sampled_run_fails_verifier(tmp_path: Path) -> None:
    episode = sample_episode(scenario="failed_invoice_retryable", seed=3, out_dir=tmp_path / "run")

    result = verify_run(episode.run_dir)

    assert result.ok is False
    assert any(check["ok"] is False for check in result.checks)


def test_oracle_resolves_all_phase_1_scenarios_through_tools(tmp_path: Path) -> None:
    for scenario in sorted(SCENARIOS):
        episode = sample_episode(scenario=scenario, seed=4, out_dir=tmp_path / scenario)

        result = resolve_run(episode.run_dir, policy="oracle")

        assert result["ok"] is True
        assert result["policy"] == "oracle"
        assert result["scenario"] == scenario
        assert verify_run(episode.run_dir).ok is True
        with sqlite3.connect(episode.db_path) as conn:
            audit_count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        assert audit_count > 0


def test_agent_runner_uses_fake_openai_compatible_server_and_writes_artifacts(tmp_path: Path) -> None:
    episode = sample_episode(scenario="duplicate_payment_refund", seed=5, out_dir=tmp_path / "run")
    expected = _expected(episode.db_path)
    calls = [
        _tool_call_response(
            "call_refund",
            "billing_create_refund",
            {
                "payment_id": expected["refund_payment_id"],
                "amount": expected["refund_amount"],
                "reason": "duplicate",
                "ticket_id": expected["ticket_id"],
            },
        ),
        _tool_call_response(
            "call_reply",
            "support_add_reply",
            {
                "ticket_id": expected["ticket_id"],
                "body": "I issued a refund for the duplicate charge.",
            },
        ),
        _tool_call_response("call_close", "support_close_ticket", {"ticket_id": expected["ticket_id"]}),
        {"role": "assistant", "content": "Resolved the ticket."},
    ]

    with _fake_chat_server(calls) as server:
        result = run_openai_compatible_agent(
            run_dir=episode.run_dir,
            model="fake-model",
            base_url=server.base_url,
            api_key="EMPTY",
            max_turns=8,
        )

    assert result["ok"] is True
    assert result["final_answer"]["content"] == "Resolved the ticket."
    assert result["verifier_result"]["ok"] is True
    assert verify_run(episode.run_dir).ok is True

    for artifact_name in ("messages.jsonl", "tool_calls.jsonl", "final_answer.json", "verifier_result.json"):
        assert (episode.run_dir / artifact_name).exists()

    tool_call_rows = [_loads_json_line(line) for line in (episode.run_dir / "tool_calls.jsonl").read_text().splitlines()]
    assert [row["name"] for row in tool_call_rows] == [
        "billing_create_refund",
        "support_add_reply",
        "support_close_ticket",
    ]
    assert server.requests[0]["tool_choice"] == "auto"
    assert {tool["function"]["name"] for tool in server.requests[0]["tools"]} == EXPECTED_TOOL_NAMES


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


def _tool_call_response(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, sort_keys=True)},
            }
        ],
    }


def _loads_json_line(line: str) -> dict[str, Any]:
    return json.loads(line)


class _fake_chat_server:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = list(messages)
        self.requests: list[dict[str, Any]] = []
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""

    def __enter__(self) -> "_fake_chat_server":
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                assert self.path == "/v1/chat/completions"
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                owner.requests.append(payload)
                message = owner.messages.pop(0)
                response = {"choices": [{"message": message}]}
                body = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        host, port = self._server.server_address
        self.base_url = f"http://{host}:{port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        assert self._server is not None
        assert self._thread is not None
        self._server.shutdown()
        self._thread.join(timeout=5)
