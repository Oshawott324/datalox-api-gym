from __future__ import annotations

import json
import uuid

import pytest

from api_gym.provider_components.cromwell.analysis_projection import (
    CromwellAnalysisProjectionError,
    build_capture_facts,
    canonical_digest,
    classify_program,
    deterministic_workflow_id,
    render_abort_response,
    render_logs,
    render_metadata,
    render_outputs,
    render_status,
    render_submit_response,
    validate_capture_facts,
)


def test_analysis_facts_are_derived_from_all_checked_cromwell_cases() -> None:
    facts = build_capture_facts()

    assert facts["schema_version"] == "api_gym.cromwell_analysis_projection_facts.v1"
    assert facts["provider_version"] == "92"
    assert facts["provider_statuses"] == [
        "Aborted",
        "Aborting",
        "Failed",
        "Running",
        "Submitted",
        "Succeeded",
    ]
    assert set(facts["programs"]) == {"abort", "failure", "success"}
    assert facts["programs"]["success"]["workflow_sha256"] == (
        "sha256:6e6d652e3ba12cd5be4f76733733bc7b3408879d2d0beaf24a405575e1013078"
    )
    assert facts["programs"]["failure"]["workflow_sha256"] == (
        "sha256:feaf458caad5621f5ce2ccd5b950d842033d86fc09078adfec7e084922b73f54"
    )
    assert facts["programs"]["abort"]["workflow_sha256"] == (
        "sha256:1f5b811ff2f381f464e42a47932bd845360548a9b4a9605890424081eb4dcc8f"
    )
    assert facts["programs"]["failure"]["terminal_status"] == "Failed"
    assert facts["programs"]["abort"]["terminal_status"] == "Aborted"
    assert facts["projection"] == {
        "dynamic_timestamps": "G0_BENCHMARK_DEFINED",
        "provider_response_shape": "G2_LOCAL_EXECUTED",
    }
    validate_capture_facts(facts)


def test_program_classification_is_exact_and_non_idempotent_ids_are_distinct() -> None:
    facts = build_capture_facts()
    success = facts["programs"]["success"]

    assert classify_program(
        facts,
        success["workflow_source"],
        success["workflow_inputs"],
    ) == "success"

    first_id = deterministic_workflow_id(seed=9, ordinal=0)
    second_id = deterministic_workflow_id(seed=9, ordinal=1)
    assert first_id != second_id
    assert str(uuid.UUID(first_id)) == first_id
    assert str(uuid.UUID(second_id)) == second_id
    assert render_submit_response(facts, first_id) == {
        "id": first_id,
        "status": "Submitted",
    }

    with pytest.raises(
        CromwellAnalysisProjectionError,
        match="CROMWELL_PROGRAM_NOT_ADMITTED",
    ):
        classify_program(
            facts,
            success["workflow_source"] + "\n# changed",
            success["workflow_inputs"],
        )


def test_status_and_abort_responses_preserve_captured_native_shapes() -> None:
    facts = build_capture_facts()
    workflow_id = deterministic_workflow_id(seed=11, ordinal=2)

    status_code, body = render_status(
        facts,
        workflow_id=workflow_id,
        provider_status=None,
    )
    assert status_code == 404
    assert body == {
        "message": f"Unrecognized workflow ID: {workflow_id}",
        "status": "fail",
    }
    assert render_status(
        facts,
        workflow_id=workflow_id,
        provider_status="Running",
    ) == (200, {"id": workflow_id, "status": "Running"})
    assert render_abort_response(
        facts,
        workflow_id=workflow_id,
        provider_status="Aborting",
    ) == (200, {"id": workflow_id, "status": "Aborting"})
    assert render_abort_response(
        facts,
        workflow_id=workflow_id,
        provider_status=None,
    ) == (
        404,
        {
            "message": (
                f"Couldn't abort {workflow_id} because no workflow with that ID "
                "is in progress"
            ),
            "status": "error",
        },
    )


def test_terminal_evidence_is_capture_derived_and_paths_are_sanitized() -> None:
    facts = build_capture_facts()
    workflow_id = deterministic_workflow_id(seed=13, ordinal=4)

    success_outputs = render_outputs(facts, "success", workflow_id)
    failure_outputs = render_outputs(facts, "failure", workflow_id)
    failure_metadata = render_metadata(facts, "failure", workflow_id)
    aborted_metadata = render_metadata(facts, "abort", workflow_id)
    success_logs = render_logs(facts, "success", workflow_id)

    assert success_outputs["id"] == workflow_id
    assert success_outputs["outputs"]["success_case.echoed"] == (
        "hello from cromwell 92"
    )
    assert failure_outputs == {"id": workflow_id, "outputs": {}}
    failure_call = failure_metadata["calls"]["failure_case.exit_nonzero"][0]
    assert failure_metadata["status"] == "Failed"
    assert failure_call["returnCode"] == 23
    assert failure_call["retryableFailure"] is False
    assert aborted_metadata["status"] == "Aborted"
    assert (
        aborted_metadata["calls"]["abort_case.wait_long_enough_to_abort"][0][
            "executionStatus"
        ]
        == "Aborted"
    )

    encoded = json.dumps(
        [success_outputs, failure_metadata, aborted_metadata, success_logs],
        sort_keys=True,
    )
    assert "/tmp/" not in encoded
    assert "datalox-world://cromwell/" in encoded
    assert canonical_digest(success_outputs["outputs"]).startswith("sha256:")


def test_metadata_timestamps_are_projected_to_the_episode_clock() -> None:
    facts = build_capture_facts()
    workflow_id = deterministic_workflow_id(seed=15, ordinal=2)
    timing = {
        "submitted_at": "2026-07-30T08:00:00+00:00",
        "started_at": "2026-07-30T08:00:10+00:00",
        "ended_at": "2026-07-30T08:00:30+00:00",
    }

    metadata = render_metadata(
        facts,
        "success",
        workflow_id,
        projected_timing=timing,
    )
    encoded = json.dumps(metadata, sort_keys=True)

    assert metadata["submission"] == "2026-07-30T08:00:00.000Z"
    assert metadata["start"] == "2026-07-30T08:00:10.000Z"
    assert metadata["end"] == "2026-07-30T08:00:30.000Z"
    assert "2026-07-30T11:" not in encoded


def test_cromwell_analysis_facts_fail_closed_when_tampered() -> None:
    facts = build_capture_facts()
    facts["programs"]["failure"]["terminal_status"] = "Succeeded"

    with pytest.raises(
        CromwellAnalysisProjectionError,
        match="CROMWELL_CAPTURE_FACTS_INVALID",
    ):
        validate_capture_facts(facts)
