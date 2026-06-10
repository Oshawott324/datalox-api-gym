#!/usr/bin/env python3
"""Capture Stripe test-mode refund behavior instances as raw JSONL.

The output is for agents designing billing_support_v0 fake-world behavior. It
records raw request/response/error instances and never writes the Stripe secret
key into the JSONL rows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_API_BASE = "https://api.stripe.com"
DEFAULT_KEY_ENV = "STRIPE_SECRET_KEY"
WORLD = "billing_support_v0"


class ProbeFailure(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class StripeResult:
    ok: bool
    case: str
    operation: str
    http_status: int | None
    body: Any
    record_id: str


def is_test_secret_key(value: str) -> bool:
    return value.startswith("sk_test_")


def default_raw_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "raw"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-env", default=DEFAULT_KEY_ENV, help="Environment variable containing the Stripe key.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="Stripe API base URL.")
    parser.add_argument("--out-dir", type=Path, default=default_raw_dir(), help="Directory for raw JSONL output.")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--unsafe-live-key",
        action="store_true",
        help="Allow non-test Stripe keys. This can mutate live-mode Stripe data.",
    )
    args = parser.parse_args(argv)

    key = os.environ.get(args.key_env, "").strip()
    if not key:
        _emit_agent_error(
            "missing_stripe_key",
            f"{args.key_env} is not set. Provide a Stripe test secret key such as sk_test_...",
        )
        return 2

    if not is_test_secret_key(key) and not args.unsafe_live_key:
        _emit_agent_error(
            "stripe_key_refused",
            "Refusing to run because the Stripe key does not start with sk_test_.",
            {"key_env": args.key_env, "override": "--unsafe-live-key"},
        )
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    run_id = _new_run_id()
    out_path = args.out_dir / f"stripe_refund_instances_{run_id}.jsonl"
    recorder = JsonlRecorder(out_path)
    client = StripeClient(
        api_base=args.api_base,
        secret_key=key,
        recorder=recorder,
        run_id=run_id,
        timeout=args.timeout,
    )

    try:
        results = run_probe(client)
    except ProbeFailure as exc:
        _emit_agent_error(exc.code, exc.message, exc.details | {"raw_output": str(out_path)})
        return 1

    summary = {
        "ok": True,
        "source_type": "live_probe",
        "provider": "stripe",
        "world": WORLD,
        "raw_output": str(out_path),
        "records_written": recorder.count,
        "successful_http_calls": sum(1 for result in results if result.ok),
        "error_http_calls": sum(1 for result in results if result.http_status is not None and not result.ok),
        "cases": [result.case for result in results],
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


def run_probe(client: "StripeClient") -> list[StripeResult]:
    results: list[StripeResult] = []

    full_payment = create_payment_intent(client, case="setup.full_refund_payment", amount=1000)
    full_refund = create_refund(
        client,
        case="full_refund",
        payment_intent_id=_body_id(full_payment),
        reason="requested_by_customer",
    )
    _require_success(full_refund, expected_object="refund")
    results.extend([full_payment, full_refund])

    partial_payment = create_payment_intent(client, case="setup.partial_refund_payment", amount=2000)
    partial_refund = create_refund(
        client,
        case="partial_refund",
        payment_intent_id=_body_id(partial_payment),
        amount=700,
        reason="requested_by_customer",
    )
    _require_success(partial_refund, expected_object="refund")
    over_refund = create_refund(
        client,
        case="over_refund_after_partial_refund",
        payment_intent_id=_body_id(partial_payment),
        amount=1400,
        reason="requested_by_customer",
    )
    results.extend([partial_payment, partial_refund, over_refund])

    original_payment = create_payment_intent(client, case="setup.duplicate_original_payment", amount=1200)
    duplicate_payment = create_payment_intent(
        client,
        case="setup.duplicate_like_second_payment",
        amount=1200,
        extra_metadata={"duplicate_of": _body_id(original_payment)},
    )
    duplicate_refund = create_refund(
        client,
        case="duplicate_like_second_payment_refund_reason",
        payment_intent_id=_body_id(duplicate_payment),
        reason="duplicate",
    )
    _require_success(duplicate_refund, expected_object="refund")
    results.extend([original_payment, duplicate_payment, duplicate_refund])

    invalid_reason_payment = create_payment_intent(client, case="setup.invalid_reason_payment", amount=1000)
    invalid_reason = create_refund(
        client,
        case="invalid_refund_reason",
        payment_intent_id=_body_id(invalid_reason_payment),
        reason="api_gym_invalid_reason",
    )
    results.extend([invalid_reason_payment, invalid_reason])

    return results


def create_payment_intent(
    client: "StripeClient",
    *,
    case: str,
    amount: int,
    extra_metadata: dict[str, str] | None = None,
) -> StripeResult:
    metadata = {
        "metadata[api_gym_world]": WORLD,
        "metadata[api_gym_probe]": "stripe_refund_instances",
        "metadata[api_gym_case]": case,
        **{f"metadata[{key}]": value for key, value in (extra_metadata or {}).items()},
    }
    result = client.post(
        "/v1/payment_intents",
        operation="payment_intent.create",
        case=case,
        form={
            "amount": amount,
            "currency": "usd",
            "payment_method": "pm_card_visa",
            "payment_method_types[]": "card",
            "confirm": "true",
            "description": f"api-gym {WORLD} Phase 5 probe {case}",
            **metadata,
        },
    )
    _require_success(result, expected_object="payment_intent")
    return result


def create_refund(
    client: "StripeClient",
    *,
    case: str,
    payment_intent_id: str,
    reason: str,
    amount: int | None = None,
) -> StripeResult:
    form: dict[str, Any] = {
        "payment_intent": payment_intent_id,
        "reason": reason,
        "metadata[api_gym_world]": WORLD,
        "metadata[api_gym_probe]": "stripe_refund_instances",
        "metadata[api_gym_case]": case,
    }
    if amount is not None:
        form["amount"] = amount
    return client.post("/v1/refunds", operation="refund.create", case=case, form=form)


class StripeClient:
    def __init__(
        self,
        *,
        api_base: str,
        secret_key: str,
        recorder: "JsonlRecorder",
        run_id: str,
        timeout: float,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.secret_key = secret_key
        self.recorder = recorder
        self.run_id = run_id
        self.timeout = timeout

    def post(self, path: str, *, operation: str, case: str, form: dict[str, Any]) -> StripeResult:
        normalized_form = _normalize_form(form)
        body = urllib.parse.urlencode(normalized_form, doseq=True).encode("utf-8")
        idempotency_key = f"api-gym-{self.run_id}-{case}".replace("_", "-")[:255]
        request = urllib.request.Request(
            f"{self.api_base}{path}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Idempotency-Key": idempotency_key,
            },
        )

        record_id = f"live.stripe.{case}.{uuid.uuid4().hex}"
        record: dict[str, Any] = {
            "id": record_id,
            "schema_version": "api_gym.raw_provider_probe_instance.v0",
            "source_type": "live_probe",
            "provider": "stripe",
            "world": WORLD,
            "operation": operation,
            "case": case,
            "observed_at": _now(),
            "request": {
                "method": "POST",
                "path": path,
                "form": normalized_form,
                "headers": {"Content-Type": "application/x-www-form-urlencoded", "Idempotency-Key": idempotency_key},
            },
        }

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                response_headers = dict(response.headers.items())
                response_body = _decode_response(response.read())
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_headers = dict(exc.headers.items())
            response_body = _decode_response(exc.read())
        except urllib.error.URLError as exc:
            record["transport_error"] = {"type": type(exc.reason).__name__, "message": str(exc.reason)}
            self.recorder.write(record)
            raise ProbeFailure(
                "stripe_transport_error",
                "Stripe request failed before an HTTP response was received.",
                {"case": case, "operation": operation},
            ) from exc

        record["response"] = {
            "http_status": status,
            "headers": _keep_response_headers(response_headers),
            "body": response_body,
        }
        if status >= 400:
            record["error"] = _extract_error(response_body)
        self.recorder.write(record)

        return StripeResult(
            ok=status < 400,
            case=case,
            operation=operation,
            http_status=status,
            body=response_body,
            record_id=record_id,
        )


class JsonlRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.count = 0

    def write(self, row: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        self.count += 1


def _require_success(result: StripeResult, *, expected_object: str) -> None:
    if not result.ok:
        raise ProbeFailure(
            "stripe_setup_request_failed",
            "A setup request needed for later refund observations failed.",
            {"case": result.case, "operation": result.operation, "record_id": result.record_id},
        )
    if not isinstance(result.body, dict) or result.body.get("object") != expected_object:
        raise ProbeFailure(
            "stripe_unexpected_response_shape",
            "Stripe returned a success response without the expected object shape.",
            {
                "case": result.case,
                "operation": result.operation,
                "expected_object": expected_object,
                "record_id": result.record_id,
            },
        )


def _body_id(result: StripeResult) -> str:
    if isinstance(result.body, dict) and isinstance(result.body.get("id"), str):
        return result.body["id"]
    raise ProbeFailure(
        "stripe_missing_response_id",
        "Stripe response did not include an id needed by a later probe request.",
        {"case": result.case, "operation": result.operation, "record_id": result.record_id},
    )


def _normalize_form(form: dict[str, Any]) -> dict[str, str | list[str]]:
    normalized: dict[str, str | list[str]] = {}
    for key, value in form.items():
        if isinstance(value, list):
            normalized[key] = [str(item) for item in value]
        else:
            normalized[key] = str(value)
    return normalized


def _decode_response(body: bytes) -> Any:
    text = body.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_body": text}


def _extract_error(response_body: Any) -> dict[str, Any]:
    if isinstance(response_body, dict) and isinstance(response_body.get("error"), dict):
        return response_body["error"]
    return {"raw_body": response_body}


def _keep_response_headers(headers: dict[str, str]) -> dict[str, str]:
    kept = {}
    for key in ("Request-Id", "Stripe-Version", "Content-Type"):
        if key in headers:
            kept[key] = headers[key]
    return kept


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_{uuid.uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _emit_agent_error(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    print(
        json.dumps(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                    "details": details or {},
                },
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
