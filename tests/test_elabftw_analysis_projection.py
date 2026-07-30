from __future__ import annotations

import json

import pytest

from api_gym.provider_components.elabftw.analysis_projection import (
    ELabFTWAnalysisProjectionError,
    build_capture_facts,
    deterministic_experiment_id,
    render_experiment,
    validate_capture_facts,
    validate_patch_body,
)


def test_analysis_facts_are_derived_from_checked_complete_capture() -> None:
    facts = build_capture_facts()

    assert facts["schema_version"] == "api_gym.elabftw_analysis_projection_facts.v1"
    assert facts["provider_version"] == "5.6.10"
    assert facts["grounding"]["program_id"] == (
        "elabftw_experiments_patch_complete_v1"
    )
    assert facts["grounding"]["capture_sha256"] == (
        "sha256:f83ba0c58a078c332064e16f629084b8dcd7e341ef3d2861e2ff974790e6eca6"
    )
    assert facts["operations"] == {
        "create": {
            "body_kind": "empty",
            "request_fields": [],
            "status_code": 201,
        },
        "get": {"status_code": 200},
        "list": {
            "body_shape": "array",
            "body_sha256": (
                "sha256:"
                "cd0094f808a31b8f9452d55ec302ee7da95117cffefdf039efe1aa726b967796"
            ),
            "status_code": 200,
        },
        "patch": {
            "request_fields": ["body", "metadata", "title"],
            "status_code": 200,
        },
    }
    assert facts["response_headers"]["create"]["content-type"] == (
        "text/html; charset=UTF-8"
    )
    assert facts["response_headers"]["get"] == {
        "content-type": "application/json"
    }
    assert facts["response_headers"]["list"] == {
        "content-type": "application/json"
    }
    assert facts["response_headers"]["patch"] == {
        "content-type": "application/json"
    }
    assert facts["projection"] == {
        "dynamic_changelog": "G0_BENCHMARK_DEFINED",
        "dynamic_links": "G0_BENCHMARK_DEFINED",
        "dynamic_timestamps": "G0_BENCHMARK_DEFINED",
        "provider_response_shape": "G2_LOCAL_EXECUTED",
    }
    validate_capture_facts(facts)


def test_analysis_projection_renders_provider_shaped_records() -> None:
    facts = build_capture_facts()
    metadata = {
        "handoff_kind": "analysis-control/qualification",
        "source_experiment_id": 4100,
        "source_revision": 2,
    }

    response = render_experiment(
        facts,
        experiment_id=deterministic_experiment_id(seed=7, ordinal=3),
        title="Analysis-control qualification handoff",
        body="No biological inference is claimed.",
        metadata=metadata,
        created_at="2026-07-30T08:00:00+00:00",
        modified_at="2026-07-30T08:00:30+00:00",
        changelog_repetitions=2,
    )

    assert isinstance(response["id"], int)
    assert response["title"] == "Analysis-control qualification handoff"
    assert response["body"] == response["body_html"]
    assert json.loads(response["metadata"]) == metadata
    assert response["metadata_decoded"] == metadata
    assert response["team"] == 1
    assert response["state"] == 1
    assert response["created_at"] == "2026-07-30 08:00:00"
    assert response["modified_at"] == "2026-07-30 08:00:30"
    assert response["sharelink"].startswith("datalox-world://elabftw/")
    assert {entry["created_at"] for entry in response["changelog"]} <= {
        "2026-07-30 08:00:00",
        "2026-07-30 08:00:30",
    }
    assert "Antimicrobial resistance study" not in json.dumps(response)
    assert len(response["changelog"]) == (
        facts["templates"]["patched_experiment"]["captured_changelog_count"] + 2
    )


def test_analysis_projection_accepts_only_captured_patch_shape() -> None:
    facts = build_capture_facts()
    body = {
        "title": "Analysis-control qualification handoff",
        "body": "No biological inference is claimed.",
        "metadata": '{"source_revision":2}',
    }

    assert validate_patch_body(facts, body) == {
        "source_revision": 2,
    }

    with pytest.raises(
        ELabFTWAnalysisProjectionError,
        match="ELABFTW_INVALID_PATCH_PAYLOAD",
    ):
        validate_patch_body(facts, {**body, "unsupported": True})

    with pytest.raises(
        ELabFTWAnalysisProjectionError,
        match="ELABFTW_INVALID_METADATA_JSON",
    ):
        validate_patch_body(facts, {**body, "metadata": "not-json"})


def test_analysis_projection_facts_fail_closed_when_tampered() -> None:
    facts = build_capture_facts()
    facts["operations"]["create"]["status_code"] = 200

    with pytest.raises(
        ELabFTWAnalysisProjectionError,
        match="ELABFTW_CAPTURE_FACTS_INVALID",
    ):
        validate_capture_facts(facts)
