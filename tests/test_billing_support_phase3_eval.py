from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from api_gym.cli import app


def test_eval_cli_writes_model_rows_and_report_summarizes_pass_rates(tmp_path: Path) -> None:
    out = tmp_path / "eval.jsonl"
    runner = CliRunner()

    with _scenario_fake_chat_server() as server:
        result = runner.invoke(
            app,
            [
                "eval",
                "--world",
                "billing_support_v0",
                "--scenarios",
                "duplicate_payment_refund,failed_invoice_retryable,refund_not_allowed_policy",
                "--seeds",
                "1",
                "--model",
                "fake-eval-model",
                "--base-url",
                server.base_url,
                "--api-key",
                "EMPTY",
                "--out",
                str(out),
                "--max-turns",
                "8",
            ],
        )

    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3

    by_scenario = {row["scenario"]: row for row in rows}
    assert by_scenario["duplicate_payment_refund"]["passed"] is True
    assert by_scenario["failed_invoice_retryable"]["passed"] is True
    assert by_scenario["refund_not_allowed_policy"]["passed"] is False

    for scenario, row in by_scenario.items():
        assert row["world"] == "billing_support_v0"
        assert row["seed"] == 1
        assert row["model"] == "fake-eval-model"
        assert row["base_url"] == server.base_url
        assert row["verifier_result"]["scenario"] == scenario
        assert row["verifier_result"]["ok"] is row["passed"]
        assert row["final_answer"]
        assert row["stop_reason"] == "assistant_final"
        assert Path(row["run_dir"]).exists()
        assert (Path(row["run_dir"]) / "tool_calls.jsonl").exists()

    assert by_scenario["duplicate_payment_refund"]["tool_call_count"] == 4
    assert by_scenario["failed_invoice_retryable"]["tool_call_count"] == 4
    assert by_scenario["refund_not_allowed_policy"]["tool_call_count"] == 2

    report = runner.invoke(app, ["report", "--input", str(out)])

    assert report.exit_code == 0, report.output
    stats = json.loads(report.output)
    assert stats == {
        "by_scenario": {
            "duplicate_payment_refund": {"passed": 1, "pass_rate": 1.0, "total": 1},
            "failed_invoice_retryable": {"passed": 1, "pass_rate": 1.0, "total": 1},
            "refund_not_allowed_policy": {"passed": 0, "pass_rate": 0.0, "total": 1},
        },
        "pass_rate": 2 / 3,
        "passed": 2,
        "total": 3,
    }


class _scenario_fake_chat_server:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""

    def __enter__(self) -> "_scenario_fake_chat_server":
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                assert self.path == "/v1/chat/completions"
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                owner.requests.append(payload)
                body = json.dumps({"choices": [{"message": owner._message_for(payload)}]}).encode("utf-8")
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

    def _message_for(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages = payload["messages"]
        prompt = _user_prompt(messages)
        ticket_id = _extract_id(prompt, r"ticket (tkt_[a-f0-9]+)")
        invoice_id = _extract_id(prompt, r"invoice (in_[a-f0-9]+_(?:01|retry|old))")

        if "duplicate charges" in prompt:
            return self._duplicate_payment_message(messages, ticket_id, invoice_id)
        if "retry" in prompt and "failed" in prompt:
            return self._retry_invoice_message(messages, ticket_id, invoice_id)
        if "old paid invoice" in prompt:
            return self._policy_failure_message(messages, ticket_id, invoice_id)
        raise AssertionError(f"Unrecognized prompt: {prompt}")

    def _duplicate_payment_message(self, messages: list[dict[str, Any]], ticket_id: str, invoice_id: str) -> dict[str, Any]:
        if not _called(messages, "billing_get_invoice"):
            return _tool_call("call_get_invoice", "billing_get_invoice", {"invoice_id": invoice_id})

        invoice = _tool_result(messages, "billing_get_invoice")["data"]
        duplicate = next(payment for payment in invoice["payments"] if payment["metadata"].get("duplicate_of"))
        if not _called(messages, "billing_create_refund"):
            return _tool_call(
                "call_refund",
                "billing_create_refund",
                {
                    "payment_id": duplicate["id"],
                    "amount": duplicate["amount"],
                    "reason": "duplicate",
                    "ticket_id": ticket_id,
                },
            )
        if not _called(messages, "support_add_reply"):
            return _tool_call(
                "call_reply",
                "support_add_reply",
                {"ticket_id": ticket_id, "body": "I issued a refund for the duplicate payment."},
            )
        if not _called(messages, "support_close_ticket"):
            return _tool_call("call_close", "support_close_ticket", {"ticket_id": ticket_id})
        return {"role": "assistant", "content": "Refunded the duplicate payment and closed the ticket."}

    def _retry_invoice_message(self, messages: list[dict[str, Any]], ticket_id: str, invoice_id: str) -> dict[str, Any]:
        if not _called(messages, "billing_get_invoice"):
            return _tool_call("call_get_invoice", "billing_get_invoice", {"invoice_id": invoice_id})
        if not _called(messages, "billing_retry_invoice"):
            return _tool_call("call_retry", "billing_retry_invoice", {"invoice_id": invoice_id})
        if not _called(messages, "support_add_reply"):
            return _tool_call(
                "call_reply",
                "support_add_reply",
                {"ticket_id": ticket_id, "body": "I retried the invoice payment and the retry succeeded."},
            )
        if not _called(messages, "support_close_ticket"):
            return _tool_call("call_close", "support_close_ticket", {"ticket_id": ticket_id})
        return {"role": "assistant", "content": "Retried the invoice payment and closed the ticket."}

    def _policy_failure_message(self, messages: list[dict[str, Any]], ticket_id: str, invoice_id: str) -> dict[str, Any]:
        if not _called(messages, "billing_get_invoice"):
            return _tool_call("call_get_invoice", "billing_get_invoice", {"invoice_id": invoice_id})

        invoice = _tool_result(messages, "billing_get_invoice")["data"]
        payment = invoice["payments"][0]
        if not _called(messages, "billing_create_refund"):
            return _tool_call(
                "call_refund",
                "billing_create_refund",
                {
                    "payment_id": payment["id"],
                    "amount": payment["amount"],
                    "reason": "requested_by_customer",
                    "ticket_id": ticket_id,
                },
            )
        return {"role": "assistant", "content": "The refund attempt failed, so I stopped without updating the ticket."}


def _tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
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


def _called(messages: list[dict[str, Any]], name: str) -> bool:
    return any(tool_call["function"]["name"] == name for tool_call in _assistant_tool_calls(messages))


def _assistant_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "assistant":
            tool_calls.extend(message.get("tool_calls") or [])
    return tool_calls


def _tool_result(messages: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("role") == "tool" and message.get("name") == name:
            return json.loads(str(message["content"]))
    raise AssertionError(f"Missing tool result for {name}")


def _user_prompt(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if message.get("role") == "user":
            return str(message["content"])
    raise AssertionError("Missing user prompt")


def _extract_id(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    assert match is not None, text
    return match.group(1)
