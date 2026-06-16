from __future__ import annotations

import pytest

from api_gym.source_pack_gate import (
    SourcePackGateError,
    build_gate_response,
    choose_response_case,
    find_operation,
    list_providers,
    list_response_cases,
)


def test_list_providers_reads_checked_in_source_packs() -> None:
    providers = list_providers()

    assert "stripe" in providers
    assert "zendesk" in providers


def test_find_operation_matches_exact_path() -> None:
    operation = find_operation("stripe", "POST", "/v1/refunds")

    assert operation["id"] == "operation:createRefund"


def test_find_operation_matches_templated_path_segment() -> None:
    operation = find_operation("stripe", "POST", "/v1/invoices/in_123/pay")

    assert operation["id"] == "operation:payInvoice"


def test_choose_success_response_case_for_create_refund_returns_gate_payload() -> None:
    response_case = choose_response_case("stripe", "operation:createRefund", case="success")
    response = build_gate_response(response_case)

    assert response["status"] == "2xx"
    assert response["response_mode"] == "body_excerpt"
    assert response["body_excerpt"]["object"] == "refund"
    assert response["body_excerpt"]["status"] == "succeeded"


def test_list_response_cases_filters_by_operation_ref() -> None:
    cases = list_response_cases("stripe", "operation:createRefund")

    assert [case["id"] for case in cases] == [
        "response_case:createRefund:success",
        "response_case:createRefund:invalid_request_error",
    ]


def test_unsupported_provider_raises_stable_code() -> None:
    with pytest.raises(SourcePackGateError) as exc_info:
        find_operation("missing_provider", "POST", "/v1/refunds")

    assert exc_info.value.code == "source_pack_gate_provider_not_found"
    assert exc_info.value.details["provider"] == "missing_provider"


def test_provider_path_segment_traversal_raises_stable_code() -> None:
    with pytest.raises(SourcePackGateError) as exc_info:
        find_operation("../stripe", "POST", "/v1/refunds")

    assert exc_info.value.code == "source_pack_gate_path_segment_invalid"
    assert exc_info.value.details["segment_name"] == "provider"
    assert exc_info.value.details["segment_value"] == "../stripe"


def test_version_path_segment_traversal_raises_stable_code() -> None:
    with pytest.raises(SourcePackGateError) as exc_info:
        find_operation("stripe", "POST", "/v1/refunds", version="../2026-06-12")

    assert exc_info.value.code == "source_pack_gate_path_segment_invalid"
    assert exc_info.value.details["segment_name"] == "version"
    assert exc_info.value.details["segment_value"] == "../2026-06-12"


def test_unsupported_path_raises_stable_code() -> None:
    with pytest.raises(SourcePackGateError) as exc_info:
        find_operation("stripe", "POST", "/v1/not-a-real-operation")

    assert exc_info.value.code == "source_pack_gate_operation_not_found"
    assert exc_info.value.details["provider"] == "stripe"
    assert exc_info.value.details["method"] == "POST"
    assert exc_info.value.details["path"] == "/v1/not-a-real-operation"
