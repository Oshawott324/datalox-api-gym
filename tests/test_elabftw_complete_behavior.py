from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from datalox_gated_runtime.behavior_harvest.engines import v2

from api_gym.provider_components.elabftw.complete_behavior import (
    AUTH_SECRET_NAME,
    CAPTURE_PATH,
    CASE_METADATA_PATH,
    CONNECTOR_PATH,
    ENGINE_IDENTITY,
    FIXTURE_RECEIPT_PATH,
    RECIPE_PATH,
    SUBJECT_ID,
    ELabFTWCompleteBehaviorTarget,
    build_connector,
    build_recipe,
    case_load_arguments,
    load_checked_case,
    sha256_bytes,
)

VALIDATION_SECRET = b"elabftw-validation-only-9f876abbc345"
CASE_PATHS = (
    CONNECTOR_PATH,
    RECIPE_PATH,
    FIXTURE_RECEIPT_PATH,
    CAPTURE_PATH,
    CASE_METADATA_PATH,
)


def _digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def test_case_reloads_with_exact_provider_engine_and_artifact_pins() -> None:
    metadata = json.loads(CASE_METADATA_PATH.read_text(encoding="utf-8"))

    assert v2.current_engine_identity() == ENGINE_IDENTITY
    assert metadata["engine"] == ENGINE_IDENTITY.to_dict()
    assert metadata["digests"] == {
        "capture": _digest(CAPTURE_PATH),
        "connector": _digest(CONNECTOR_PATH),
        "recipe": _digest(RECIPE_PATH),
        "fixture_receipt": _digest(FIXTURE_RECEIPT_PATH),
    }

    loaded = v2.load_capture(
        path=CAPTURE_PATH,
        expected_sha256=metadata["digests"]["capture"],
        connector_path=CONNECTOR_PATH,
        expected_connector_sha256=metadata["digests"]["connector"],
        recipe_path=RECIPE_PATH,
        expected_recipe_sha256=metadata["digests"]["recipe"],
        expected_engine=ENGINE_IDENTITY,
        sensitive_values={AUTH_SECRET_NAME: VALIDATION_SECRET},
        static_input_paths={"fixture_inspection": FIXTURE_RECEIPT_PATH},
        expected_static_input_sha256={
            "fixture_inspection": metadata["digests"]["fixture_receipt"]
        },
    )

    assert loaded.value.connector.provider_id == "elabftw"
    assert loaded.value.connector.provider_version == "5.6.10"
    assert loaded.value.connector.origin == "http://127.0.0.1:3148"
    assert loaded.value.connector.boundary.kind == "self_hosted_reference"
    assert loaded.value.connector.boundary.production_equivalence == "not_claimed"
    assert loaded.value.connector.isolation.reset_equivalence_claimed is False
    assert loaded.value.connector.driver_id == ENGINE_IDENTITY.engine_id
    assert loaded.value.connector.driver_version == ENGINE_IDENTITY.engine_version
    assert loaded.value.connector.driver_source_sha256 == ENGINE_IDENTITY.source_sha256


def test_checked_connector_and_recipe_match_provider_construction_code() -> None:
    receipt = json.loads(FIXTURE_RECEIPT_PATH.read_text(encoding="utf-8"))
    connector = v2.load_connector(
        CONNECTOR_PATH,
        expected_sha256=_digest(CONNECTOR_PATH),
    ).value
    recipe = v2.load_recipe(RECIPE_PATH, expected_sha256=_digest(RECIPE_PATH)).value

    assert connector == build_connector(receipt)
    assert recipe == build_recipe()
    assert receipt["services"]["web"]["content_digest"] == (
        "sha256:a4dd2264b6fa40bb250ca68d3845afa442bb15c29aed95cd444786084eb30e67"
    )
    assert receipt["services"]["mysql"]["content_digest"] == (
        "sha256:8dbcf531a03aade657e181b9cf2f1d1803ce621a1d55610cb44cb531ab7d7db6"
    )


def test_complete_program_roles_subject_and_observed_relations() -> None:
    loaded = v2.load_recipe(RECIPE_PATH, expected_sha256=_digest(RECIPE_PATH)).value
    required = {"before", "success", "duplicate", "native_failure", "resulting_state"}
    by_role = {step.role: step for step in loaded.steps}

    assert required <= set(by_role)
    assert all(by_role[role].subject_id == SUBJECT_ID for role in required)
    assert by_role["duplicate"].expected_outcome == "observe"
    assert by_role["resulting_state"].expected_outcome == "observe"

    capture = load_checked_case(VALIDATION_SECRET).value
    assert dict(capture.observed_relations) == {
        "resulting_experiment.observed_title_vs_before": "changed",
        "resulting_experiment.observed_title_vs_success": "equal",
    }


def test_capture_contains_no_secret_or_host_identity_material() -> None:
    combined = b"\n".join(path.read_bytes() for path in CASE_PATHS)
    forbidden = (
        VALIDATION_SECRET,
        base64.b64encode(VALIDATION_SECRET),
        hashlib.sha256(VALIDATION_SECRET).hexdigest().encode("ascii"),
        b"/Users/",
        b"set-cookie",
        b"datalox-fixture@example.invalid",
        b"datalox-bootstrap@example.invalid",
    )

    assert all(value not in combined for value in forbidden)
    assert b'"strategy_id":"opaque_authorization_header"' in CONNECTOR_PATH.read_bytes()
    assert b'"authorization"' not in CAPTURE_PATH.read_bytes().lower()


def test_exact_empty_create_duplicate_request_and_native_failure() -> None:
    capture = load_checked_case(VALIDATION_SECRET).value
    by_step = {exchange.step_id: exchange for exchange in capture.exchanges}
    create = by_step["create_experiment"]
    success = by_step["patch_experiment"]
    duplicate = by_step["duplicate_patch"]
    failure = by_step["invalid_patch"]

    assert create.status_code == 201
    assert create.body_kind == "empty"
    assert create.body_bytes == 0
    assert create.body_sha256 == (
        "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert duplicate.request_receipt == success.request_receipt
    assert duplicate.status_code == 200
    assert len(duplicate.body["changelog"]) == len(success.body["changelog"]) + 2
    assert failure.status_code == 400
    assert failure.body == {
        "code": 400,
        "description": "",
        "message": "Invalid update target.",
    }
    assert success.body["body_html"] == success.body["body"]
    assert success.body["metadata_decoded"]["extra_fields"]["isolate_id"]["value"] == (
        "AMR-ISO-001"
    )
    assert success.body["sharelink"].endswith("mode=view&id=1")


def test_integer_occurrences_do_not_replace_equal_unrelated_values() -> None:
    arguments = case_load_arguments(VALIDATION_SECRET)
    trace = v2.compile_reference_trace(**arguments)
    list_body = trace.steps[1].expected_body_template[0]

    assert list_body["id"] == {"$binding": "experiment_id"}
    assert list_body["team"] == 1
    assert list_body["state"] == 1
    assert list_body["id"] != list_body["team"]

    report = v2.run_compiled_behavior_trace(
        target=ELabFTWCompleteBehaviorTarget(generated_experiment_id=314),
        **arguments,
    )
    assert report.passed is True
    assert report.mismatches == ()


def test_checked_capture_compiles_and_projection_conforms() -> None:
    report = v2.run_compiled_behavior_trace(
        target=ELabFTWCompleteBehaviorTarget(),
        **case_load_arguments(VALIDATION_SECRET),
    )

    assert report.passed is True
    assert report.mismatches == ()
    assert report.target_id == "elabftw_complete_behavior_projection_v1"


def test_tampered_capture_and_recipe_fail_closed(tmp_path: Path) -> None:
    arguments = case_load_arguments(VALIDATION_SECRET)
    tampered_capture = tmp_path / "capture.json"
    raw_capture = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    raw_capture["exchanges"][5]["response"]["body"]["message"] = "tampered"
    tampered_capture.write_text(json.dumps(raw_capture), encoding="utf-8")

    with pytest.raises(v2.BehaviorContractError, match="SHA-256"):
        v2.load_capture(
            path=tampered_capture,
            expected_sha256=arguments["expected_capture_sha256"],
            connector_path=arguments["connector_path"],
            expected_connector_sha256=arguments["expected_connector_sha256"],
            recipe_path=arguments["recipe_path"],
            expected_recipe_sha256=arguments["expected_recipe_sha256"],
            expected_engine=arguments["expected_engine"],
            sensitive_values=arguments["sensitive_values"],
            static_input_paths=arguments["static_input_paths"],
            expected_static_input_sha256=arguments["expected_static_input_sha256"],
        )

    raw_recipe = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
    raw_recipe["steps"] = [
        step for step in raw_recipe["steps"] if step["role"] != "native_failure"
    ]
    tampered_recipe = tmp_path / "recipe.json"
    tampered_recipe.write_text(json.dumps(raw_recipe), encoding="utf-8")
    with pytest.raises(v2.BehaviorContractError, match="missing required roles"):
        v2.load_recipe(tampered_recipe, expected_sha256=_digest(tampered_recipe))
