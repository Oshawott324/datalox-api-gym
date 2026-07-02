import json
from pathlib import Path

from api_gym.source_packs import validate_source_pack


REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = REPO_ROOT / "source_packs" / "apis" / "adaptyv_foundry" / "2026-07-01"

EXPECTED_SOURCE_CHECK_OPERATION_IDS = {
    "add_sequences",
    "attenuate_token",
    "confirm_experiment_quote",
    "confirm_quote",
    "cost_estimate",
    "create_exp",
    "get_exp_info",
    "get_experiment_results",
    "get_experiment_sequences",
    "get_experiment_updates",
    "get_quote_info",
    "get_quote_metadata",
    "get_result_info",
    "get_sequence_info",
    "get_target_info",
    "list_experiments",
    "list_quotes",
    "list_results",
    "list_sequences",
    "list_targets",
    "modify_exp",
    "reject_quote",
    "revoke_token",
    "submit_experiment",
    "whoami",
}

EXPECTED_QUOTE_INFO_REQUIRED_FIELDS = {
    "id",
    "quote_number",
    "organization_id",
    "organization_name",
    "line_items",
    "subtotal_cents",
    "tax_cents",
    "total_cents",
    "currency",
    "status",
    "valid_until",
    "created_at",
    "notes",
    "terms_and_conditions",
    "stripe_quote_url",
}


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_adaptyv_foundry_source_pack_validates() -> None:
    result = validate_source_pack(PACK_ROOT)

    assert result["ok"] is True
    assert result["source_pack_id"] == "api.adaptyv_foundry.2026-07-01"
    assert result["provider"] == "adaptyv_foundry"
    assert result["record_counts"]["operations"] >= 20
    assert result["record_counts"]["response_cases"] >= result["record_counts"]["operations"]


def test_adaptyv_foundry_operations_include_source_check_ids() -> None:
    operation_ids = {row["operation_id"] for row in _read_jsonl(PACK_ROOT / "operations.jsonl")}

    assert operation_ids == EXPECTED_SOURCE_CHECK_OPERATION_IDS


def test_adaptyv_foundry_schemas_include_build_spec_names() -> None:
    schema_names = {row["name"] for row in _read_jsonl(PACK_ROOT / "schemas.jsonl")}

    required_names = {
        "ExperimentSpec",
        "ExperimentStatus",
        "ExperimentType",
        "CostEstimateRequest",
        "CostEstimateResponse",
        "ExperimentQuoteResponse",
        "QuoteInfo",
        "ResultInfo",
        "ResultSummary",
        "ResultsStatus",
        "SequenceEntry",
        "SequenceInfo",
        "StripeQuoteStatus",
        "TargetDetails",
        "TargetInfo",
        "TargetPricing",
        "WhoAmIResponse",
        "ErrorResponse",
    }

    assert required_names <= schema_names


def test_adaptyv_foundry_quote_info_schema_includes_openapi_required_fields() -> None:
    rows = _read_jsonl(PACK_ROOT / "schemas.jsonl")
    quote_info = next(row for row in rows if row["id"] == "schema:QuoteInfo")
    required_fields = {
        field["name"]
        for field in quote_info["fields"]
        if isinstance(field, dict) and field.get("required") is True
    }

    assert required_fields == EXPECTED_QUOTE_INFO_REQUIRED_FIELDS
    assert {
        "kind": "openapi",
        "url": "https://foundry-api-public.adaptyvbio.com/api/v1/openapi.json",
        "pointer": "/components/schemas/QuoteInfo",
    } in quote_info["source_refs"]


def test_adaptyv_foundry_response_cases_cover_build_spec_categories() -> None:
    rows = _read_jsonl(PACK_ROOT / "response_cases.jsonl")
    rows_by_case: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        case = row.get("case")
        if isinstance(case, str):
            rows_by_case.setdefault(case, []).append(row)

    expected_case_operations = {
        "target_available": {"operation:list_targets"},
        "cost_estimate_within_budget": {"operation:cost_estimate"},
        "cost_estimate_over_budget": {"operation:cost_estimate"},
        "draft_experiment": {"operation:create_exp", "operation:get_exp_info"},
        "submitted_experiment": {"operation:submit_experiment", "operation:get_exp_info"},
        "ready_quote": {"operation:get_quote_metadata", "operation:get_quote_info"},
        "expired_quote": {"operation:get_quote_metadata", "operation:get_quote_info"},
        "partial_results": {"operation:get_experiment_results", "operation:list_results"},
        "final_results": {"operation:get_experiment_results", "operation:list_results"},
        "stale_prior_result": {"operation:get_result_info", "operation:list_results"},
        "authorization_scope_denial": {
            "operation:create_exp",
            "operation:submit_experiment",
            "operation:confirm_quote",
            "operation:confirm_experiment_quote",
        },
    }

    assert set(expected_case_operations) <= set(rows_by_case)
    for case, operation_refs in expected_case_operations.items():
        assert any(row.get("operation_ref") in operation_refs for row in rows_by_case[case]), case

    assert any(
        row.get("response_mode") == "error_shape"
        and row.get("error_shape") == {"object": "ErrorResponse"}
        and any(
            isinstance(source_ref, dict)
            and source_ref.get("kind") == "openapi"
            and source_ref.get("pointer")
            in {
                "/components/schemas/ErrorResponse",
                "/paths/~1api~1v1~1experiments/post/responses/403",
                "/paths/~1api~1v1~1experiments~1{experiment_id}~1submit/post/responses/403",
                "/paths/~1api~1v1~1quotes~1{quote_id}~1confirm/post/responses/403",
                "/paths/~1api~1v1~1experiments~1{experiment_id}~1quote~1confirm/post/responses/403",
            }
            for source_ref in row.get("source_refs", [])
        )
        for row in rows_by_case["authorization_scope_denial"]
    )
