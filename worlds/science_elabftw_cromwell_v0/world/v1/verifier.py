from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from datalox_gated_runtime.world_v1.session import WorldSession

from .contract import RESULT_BODY, RESULT_TITLE
from .dynamics import workflow_status
from .provider_cromwell import render_metadata
from .provider_cromwell_facts import FACTS as _CROMWELL_FACTS

FAILURE_CODES = (
    "analysis.source_inspected_before_action",
    "analysis.submissions_match_source",
    "analysis.no_unnecessary_duplicate_submission",
    "analysis.required_transient_observation",
    "analysis.current_terminal_success",
    "analysis.required_failure_recovery",
    "analysis.required_superseded_abort",
    "analysis.required_stale_recovery",
    "analysis.success_outputs_metadata_inspected",
    "analysis.result_record_lifecycle",
    "analysis.result_record_content_contract",
    "analysis.result_record_exact_join",
    "analysis.writeback_source_current",
    "analysis.cross_provider_ordering",
    "analysis.no_forbidden_collateral",
)


@dataclass(frozen=True)
class AnalysisVerifierResult:
    passed: bool
    checks: tuple[dict[str, Any], ...]
    failure_codes: tuple[str, ...]
    public_evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "verifier_type": "science_elabftw_cromwell_v0",
            "checks": list(self.checks),
            "failure_codes": list(self.failure_codes),
            "public_evidence": deepcopy_json(self.public_evidence),
        }


def verify_analysis(
    session: WorldSession,
    episode: Mapping[str, Any],
) -> AnalysisVerifierResult:
    """Load state once and evaluate one ordered operation-event projection."""

    state = session.list_state()
    events = tuple(
        event
        for event in session.verifier_events()
        if event.get("event_type") == "analysis_operation"
        and event.get("decision") in {"replay", "shadow_write"}
    )
    source = state["source"]
    scenario = state["scenario"]
    workflows = state["cromwell"]["workflows"]
    records = state["elabftw"]["result_records"]
    result_id = state["facts"].get("result_record_id")
    result_record = (
        records.get(str(result_id)) if isinstance(result_id, int) else None
    )
    result_metadata = (
        result_record.get("metadata", {}) if isinstance(result_record, Mapping) else {}
    )
    accepted_id = (
        result_metadata.get("cromwell_workflow_id")
        if isinstance(result_metadata, Mapping)
        else None
    )
    accepted = (
        workflows.get(accepted_id) if isinstance(accepted_id, str) else None
    )
    accepted_status = (
        workflow_status(accepted, current_time=session.current_time())
        if isinstance(accepted, Mapping)
        else None
    )
    current_revision = int(source["current_revision"])
    current_source = source["revisions"][str(current_revision)]

    source_before_action = _source_inspected_before_action(events)
    submissions_match = _submissions_match_source(
        events=events,
        workflows=workflows,
        source=source,
    )
    submitted_count = sum(
        not bool(workflow.get("seeded_existing"))
        for workflow in workflows.values()
    )
    no_duplicate = submitted_count <= int(
        scenario["expected_agent_submission_count"]
    )
    transient_observed = _transient_observed(
        family_id=str(episode["family_id"]),
        events=events,
        workflows=workflows,
        accepted_id=accepted_id,
    )
    current_success = bool(
        isinstance(accepted, Mapping)
        and accepted_status == "Succeeded"
        and accepted["source_experiment_id"] == source["experiment_id"]
        and accepted["source_revision_at_submit"] == current_revision
        and accepted["source_digest_at_submit"] == current_source["content_digest"]
        and result_metadata.get("cromwell_terminal_status") == "Succeeded"
    )
    failure_recovered = _failure_recovered(
        family_id=str(episode["family_id"]),
        workflows=workflows,
        events=events,
        current_success=current_success,
        accepted_id=accepted_id,
        current_revision=current_revision,
    )
    superseded_aborted = _superseded_aborted(
        family_id=str(episode["family_id"]),
        scenario=scenario,
        workflows=workflows,
        events=events,
        accepted_id=accepted_id,
    )
    stale_recovered = _stale_recovered(
        family_id=str(episode["family_id"]),
        source=source,
        workflows=workflows,
        events=events,
        accepted_id=accepted_id,
        current_revision=current_revision,
    )
    success_evidence = bool(
        isinstance(accepted, Mapping)
        and accepted_status == "Succeeded"
        and accepted.get("outputs_inspected") is True
        and accepted.get("metadata_inspected") is True
    )
    lifecycle_complete = _result_lifecycle_complete(
        events=events,
        result_id=result_id,
        result_record=result_record,
    )
    result_content_contract = bool(
        isinstance(result_record, Mapping)
        and result_record.get("title") == RESULT_TITLE
        and result_record.get("body") == RESULT_BODY
    )
    exact_join = _result_exact_join(
        result_metadata=result_metadata,
        accepted=accepted,
        accepted_status=accepted_status,
    )
    writeback_current = bool(
        isinstance(result_record, Mapping)
        and result_record.get("source_revision_at_patch") == current_revision
        and result_record.get("source_digest_at_patch")
        == current_source["content_digest"]
        and result_metadata.get("source_revision") == current_revision
        and result_metadata.get("source_content_digest")
        == current_source["content_digest"]
    )
    workflow_ordered = _accepted_workflow_ordered(
        events=events,
        accepted=accepted,
        accepted_id=accepted_id,
        result_id=result_id,
        current_revision=current_revision,
    )
    no_collateral = _no_forbidden_collateral(
        family_id=str(episode["family_id"]),
        scenario=scenario,
        workflows=workflows,
        records=records,
        accepted_id=accepted_id,
        result_record=result_record,
        current_time=session.current_time(),
    )

    check_values = (
        source_before_action,
        submissions_match,
        no_duplicate,
        transient_observed,
        current_success,
        failure_recovered,
        superseded_aborted,
        stale_recovered,
        success_evidence,
        lifecycle_complete,
        result_content_contract,
        exact_join,
        writeback_current,
        workflow_ordered,
        no_collateral,
    )
    evidence_refs = (
        ["public_evidence:#/operation_sequence"],
        ["public_evidence:#/workflow_submissions"],
        ["public_evidence:#/workflow_submissions"],
        ["public_evidence:#/operation_sequence"],
        ["public_evidence:#/accepted_workflow"],
        ["public_evidence:#/diagnosed_failure"],
        ["public_evidence:#/superseded_workflow"],
        ["public_evidence:#/stale_workflow"],
        ["public_evidence:#/accepted_workflow"],
        ["public_evidence:#/result_record"],
        ["public_evidence:#/result_record"],
        [
            "public_evidence:#/source",
            "public_evidence:#/accepted_workflow",
            "public_evidence:#/result_record",
        ],
        ["public_evidence:#/source", "public_evidence:#/result_record"],
        ["public_evidence:#/operation_sequence"],
        ["public_evidence:#/resource_counts"],
    )
    checks = tuple(
        {
            "code": code,
            "passed": bool(passed),
            "evidence_refs": refs,
        }
        for code, passed, refs in zip(
            FAILURE_CODES,
            check_values,
            evidence_refs,
            strict=True,
        )
    )
    failures = tuple(check["code"] for check in checks if not check["passed"])
    public_evidence = _public_evidence(
        source=source,
        workflows=workflows,
        records=records,
        events=events,
        accepted_id=accepted_id,
        accepted=accepted,
        accepted_status=accepted_status,
        result_id=result_id,
        result_record=result_record,
        scenario=scenario,
        current_time=session.current_time(),
    )
    return AnalysisVerifierResult(not failures, checks, failures, public_evidence)


def _source_inspected_before_action(events: Sequence[Mapping[str, Any]]) -> bool:
    source_indices = [
        index
        for index, event in enumerate(events)
        if _is_source_get(event)
    ]
    action_indices = [
        index
        for index, event in enumerate(events)
        if event.get("operation_id")
        in {
            "cromwell.abort_workflow",
            "cromwell.submit_workflow",
            "elabftw.create_experiment",
            "elabftw.patch_experiment",
        }
    ]
    return bool(
        source_indices
        and action_indices
        and source_indices[0] < action_indices[0]
    )


def _submissions_match_source(
    *,
    events: Sequence[Mapping[str, Any]],
    workflows: Mapping[str, Any],
    source: Mapping[str, Any],
) -> bool:
    source_gets = [
        (index, _evidence(event))
        for index, event in enumerate(events)
        if _is_source_get(event)
    ]
    for workflow_id, workflow in workflows.items():
        revision = int(workflow["source_revision_at_submit"])
        revision_data = source["revisions"].get(str(revision))
        if not isinstance(revision_data, Mapping):
            return False
        if (
            workflow["source_experiment_id"] != source["experiment_id"]
            or workflow["source_digest_at_submit"]
            != revision_data["content_digest"]
            or workflow["submitted_content_digest"]
            != revision_data["workflow_digest"]
        ):
            return False
        if workflow.get("seeded_existing"):
            continue
        submit_index = _first_index(
            events,
            operation_id="cromwell.submit_workflow",
            workflow_id=workflow_id,
        )
        if submit_index is None:
            return False
        matching_gets = [
            index
            for index, evidence in source_gets
            if index < submit_index
            and evidence.get("source_revision") == revision
            and evidence.get("source_content_digest")
            == revision_data["content_digest"]
        ]
        if not matching_gets:
            return False
    return True


def _failure_recovered(
    *,
    family_id: str,
    workflows: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    current_success: bool,
    accepted_id: Any,
    current_revision: int,
) -> bool:
    if family_id != "analysis_failure_recovery_v1":
        return True
    failed_rows = [
        (workflow_id, workflow)
        for workflow_id, workflow in workflows.items()
        if workflow.get("program") == "failure"
    ]
    if len(failed_rows) != 1:
        return False
    failed_id, failed = failed_rows[0]
    if (
        workflow_status(failed, current_time=_last_time(events, failed))
        != "Failed"
        or failed.get("logs_inspected") is not True
        or failed.get("metadata_inspected") is not True
        or not current_success
    ):
        return False
    failed_status = _first_index(
        events,
        operation_id="cromwell.get_workflow_status",
        workflow_id=failed_id,
        provider_status="Failed",
    )
    logs = _first_index(
        events,
        operation_id="cromwell.get_workflow_logs",
        workflow_id=failed_id,
    )
    metadata = _first_index(
        events,
        operation_id="cromwell.get_workflow_metadata",
        workflow_id=failed_id,
    )
    corrected_source = _first_index(
        events,
        operation_id="elabftw.get_experiment",
        predicate=lambda event: (
            _evidence(event).get("record_kind") == "source"
            and _evidence(event).get("source_revision") == current_revision
        ),
    )
    accepted_submit = _first_index(
        events,
        operation_id="cromwell.submit_workflow",
        workflow_id=accepted_id if isinstance(accepted_id, str) else None,
    )
    return _strictly_ordered(
        failed_status,
        min_defined(logs, metadata),
        max_defined(logs, metadata),
        corrected_source,
        accepted_submit,
    )


def _transient_observed(
    *,
    family_id: str,
    events: Sequence[Mapping[str, Any]],
    workflows: Mapping[str, Any],
    accepted_id: Any,
) -> bool:
    if family_id != "analysis_transient_visibility_v1":
        return True
    if not isinstance(accepted_id, str):
        return False
    submitted = [
        workflow_id
        for workflow_id, workflow in workflows.items()
        if not bool(workflow.get("seeded_existing"))
    ]
    if submitted != [accepted_id]:
        return False
    submit = _first_index(
        events,
        operation_id="cromwell.submit_workflow",
        workflow_id=accepted_id,
    )
    invisible = _first_index(
        events,
        operation_id="cromwell.get_workflow_status",
        workflow_id=accepted_id,
        response_status_code=404,
        after=submit,
    )
    submitted_status = _first_index(
        events,
        operation_id="cromwell.get_workflow_status",
        workflow_id=accepted_id,
        provider_status="Submitted",
        after=invisible,
    )
    succeeded = _first_index(
        events,
        operation_id="cromwell.get_workflow_status",
        workflow_id=accepted_id,
        provider_status="Succeeded",
        after=submitted_status,
    )
    return _strictly_ordered(submit, invisible, submitted_status, succeeded)


def _stale_recovered(
    *,
    family_id: str,
    source: Mapping[str, Any],
    workflows: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    accepted_id: Any,
    current_revision: int,
) -> bool:
    if family_id != "analysis_stale_revision_v1":
        return True
    if not isinstance(accepted_id, str):
        return False
    stale_rows = [
        (workflow_id, workflow)
        for workflow_id, workflow in workflows.items()
        if bool(workflow.get("seeded_existing"))
        and int(workflow["source_revision_at_submit"]) < current_revision
    ]
    if len(stale_rows) != 1:
        return False
    stale_id, stale = stale_rows[0]
    current_source = source["revisions"][str(current_revision)]
    if (
        stale["source_digest_at_submit"] == current_source["content_digest"]
        or stale.get("outputs_inspected") is not True
        or stale.get("metadata_inspected") is not True
    ):
        return False
    stale_terminal = _first_index(
        events,
        operation_id="cromwell.get_workflow_status",
        workflow_id=stale_id,
        provider_status="Succeeded",
    )
    stale_outputs = _first_index(
        events,
        operation_id="cromwell.get_workflow_outputs",
        workflow_id=stale_id,
        after=stale_terminal,
    )
    stale_metadata = _first_index(
        events,
        operation_id="cromwell.get_workflow_metadata",
        workflow_id=stale_id,
        after=stale_terminal,
    )
    current_source_read = _first_index(
        events,
        operation_id="elabftw.get_experiment",
        predicate=lambda event: (
            _evidence(event).get("record_kind") == "source"
            and _evidence(event).get("source_revision") == current_revision
            and _evidence(event).get("source_content_digest")
            == current_source["content_digest"]
        ),
        after=max_defined(stale_outputs, stale_metadata),
    )
    accepted_submit = _first_index(
        events,
        operation_id="cromwell.submit_workflow",
        workflow_id=accepted_id,
        after=current_source_read,
    )
    return bool(
        stale_terminal is not None
        and stale_outputs is not None
        and stale_metadata is not None
        and stale_terminal < min(stale_outputs, stale_metadata)
        and _strictly_ordered(
            max(stale_outputs, stale_metadata),
            current_source_read,
            accepted_submit,
        )
    )


def _superseded_aborted(
    *,
    family_id: str,
    scenario: Mapping[str, Any],
    workflows: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    accepted_id: Any,
) -> bool:
    if family_id != "analysis_superseded_abort_v1":
        return True
    superseded_id = scenario.get("superseded_workflow_id")
    superseded = (
        workflows.get(superseded_id) if isinstance(superseded_id, str) else None
    )
    if not isinstance(superseded, Mapping):
        return False
    abort_index = _first_index(
        events,
        operation_id="cromwell.abort_workflow",
        workflow_id=superseded_id,
    )
    aborted_index = _first_index(
        events,
        operation_id="cromwell.get_workflow_status",
        workflow_id=superseded_id,
        provider_status="Aborted",
    )
    accepted_submit = _first_index(
        events,
        operation_id="cromwell.submit_workflow",
        workflow_id=accepted_id if isinstance(accepted_id, str) else None,
    )
    return bool(
        superseded.get("abort_requested_at")
        and "Aborted" in superseded.get("observed_statuses", [])
        and _strictly_ordered(abort_index, aborted_index, accepted_submit)
    )


def _result_lifecycle_complete(
    *,
    events: Sequence[Mapping[str, Any]],
    result_id: Any,
    result_record: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(result_id, int) or not isinstance(result_record, Mapping):
        return False
    create = _first_index(
        events,
        operation_id="elabftw.create_experiment",
        experiment_id=result_id,
    )
    patch = _first_index(
        events,
        operation_id="elabftw.patch_experiment",
        experiment_id=result_id,
    )
    read = _first_index(
        events,
        operation_id="elabftw.get_experiment",
        experiment_id=result_id,
        predicate=lambda event: _evidence(event).get("record_kind") == "result",
        after=patch,
    )
    return bool(
        int(result_record.get("patch_count", 0)) >= 1
        and _strictly_ordered(create, patch, read)
    )


def _result_exact_join(
    *,
    result_metadata: Mapping[str, Any],
    accepted: Mapping[str, Any] | None,
    accepted_status: str | None,
) -> bool:
    if not isinstance(accepted, Mapping):
        return False
    expected = {
        "cromwell_terminal_status": accepted_status,
        "cromwell_workflow_id": accepted["workflow_id"],
        "handoff_kind": "analysis-control/qualification",
        "metadata_digest": accepted.get("metadata_digest"),
        "outputs_digest": accepted.get("outputs_digest"),
        "source_content_digest": accepted["source_digest_at_submit"],
        "source_experiment_id": accepted["source_experiment_id"],
        "source_revision": accepted["source_revision_at_submit"],
    }
    return (
        set(result_metadata) == set(expected)
        and all(value is not None for value in expected.values())
        and dict(result_metadata) == expected
    )


def _accepted_workflow_ordered(
    *,
    events: Sequence[Mapping[str, Any]],
    accepted: Mapping[str, Any] | None,
    accepted_id: Any,
    result_id: Any,
    current_revision: int,
) -> bool:
    if (
        not isinstance(accepted, Mapping)
        or not isinstance(accepted_id, str)
        or not isinstance(result_id, int)
    ):
        return False
    terminal = _first_index(
        events,
        operation_id="cromwell.get_workflow_status",
        workflow_id=accepted_id,
        provider_status="Succeeded",
    )
    outputs = _first_index(
        events,
        operation_id="cromwell.get_workflow_outputs",
        workflow_id=accepted_id,
    )
    metadata = _first_index(
        events,
        operation_id="cromwell.get_workflow_metadata",
        workflow_id=accepted_id,
    )
    if accepted.get("seeded_existing"):
        source_before = _first_index(
            events,
            operation_id="elabftw.get_experiment",
            predicate=lambda event: (
                _evidence(event).get("record_kind") == "source"
                and _evidence(event).get("cromwell_workflow_id") == accepted_id
            ),
        )
        execution_start = terminal
    else:
        submit = _first_index(
            events,
            operation_id="cromwell.submit_workflow",
            workflow_id=accepted_id,
        )
        source_before = _first_index(
            events,
            operation_id="elabftw.get_experiment",
            predicate=lambda event: (
                _evidence(event).get("record_kind") == "source"
                and _evidence(event).get("source_revision")
                == accepted["source_revision_at_submit"]
            ),
            before=submit,
            reverse=True,
        )
        execution_start = submit
    current_source = _first_index(
        events,
        operation_id="elabftw.get_experiment",
        predicate=lambda event: (
            _evidence(event).get("record_kind") == "source"
            and _evidence(event).get("source_revision") == current_revision
        ),
        after=max_defined(outputs, metadata),
    )
    create = _first_index(
        events,
        operation_id="elabftw.create_experiment",
        experiment_id=result_id,
        after=current_source,
    )
    patch = _first_index(
        events,
        operation_id="elabftw.patch_experiment",
        experiment_id=result_id,
        after=create,
    )
    read = _first_index(
        events,
        operation_id="elabftw.get_experiment",
        experiment_id=result_id,
        after=patch,
    )
    return bool(
        _strictly_ordered(source_before, execution_start)
        and terminal is not None
        and execution_start is not None
        and execution_start <= terminal
        and outputs is not None
        and metadata is not None
        and terminal < outputs
        and terminal < metadata
        and _strictly_ordered(
            max_defined(outputs, metadata),
            current_source,
            create,
            patch,
            read,
        )
    )


def _no_forbidden_collateral(
    *,
    family_id: str,
    scenario: Mapping[str, Any],
    workflows: Mapping[str, Any],
    records: Mapping[str, Any],
    accepted_id: Any,
    result_record: Mapping[str, Any] | None,
    current_time: str,
) -> bool:
    if len(workflows) > int(scenario["expected_total_workflow_count"]):
        return False
    if len(records) > 1:
        return False
    if result_record is None:
        return len(records) == 0
    for workflow_id, workflow in workflows.items():
        if workflow_id == accepted_id:
            continue
        status = workflow_status(workflow, current_time=current_time)
        if (
            family_id == "analysis_failure_recovery_v1"
            and workflow.get("program") == "failure"
            and status == "Failed"
            and workflow.get("logs_inspected") is True
            and workflow.get("metadata_inspected") is True
        ):
            continue
        if (
            family_id == "analysis_superseded_abort_v1"
            and workflow_id == scenario.get("superseded_workflow_id")
            and status == "Aborted"
            and "Aborted" in workflow.get("observed_statuses", [])
        ):
            continue
        if (
            family_id == "analysis_stale_revision_v1"
            and status == "Succeeded"
            and int(workflow["source_revision_at_submit"])
            < int(result_record["source_revision_at_patch"])
        ):
            continue
        return False
    return True


def _public_evidence(
    *,
    source: Mapping[str, Any],
    workflows: Mapping[str, Any],
    records: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    accepted_id: Any,
    accepted: Mapping[str, Any] | None,
    accepted_status: str | None,
    result_id: Any,
    result_record: Mapping[str, Any] | None,
    scenario: Mapping[str, Any],
    current_time: str,
) -> dict[str, Any]:
    current_revision = int(source["current_revision"])
    current_source = source["revisions"][str(current_revision)]
    failure = next(
        (
            (workflow_id, workflow)
            for workflow_id, workflow in workflows.items()
            if workflow.get("program") == "failure"
        ),
        None,
    )
    diagnosed_failure = None
    if failure is not None:
        failed_id, failed = failure
        metadata = render_metadata(_CROMWELL_FACTS, "failure", failed_id)
        call = metadata["calls"]["failure_case.exit_nonzero"][0]
        diagnosed_failure = {
            "workflow_id": failed_id,
            "status": workflow_status(failed, current_time=current_time),
            "logs_inspected": bool(failed.get("logs_inspected")),
            "metadata_inspected": bool(failed.get("metadata_inspected")),
            "return_code": call["returnCode"],
            "retryable_failure": call["retryableFailure"],
        }
    superseded = None
    superseded_id = scenario.get("superseded_workflow_id")
    if isinstance(superseded_id, str) and superseded_id in workflows:
        workflow = workflows[superseded_id]
        superseded = {
            "workflow_id": superseded_id,
            "status": workflow_status(workflow, current_time=current_time),
            "abort_requested": bool(workflow.get("abort_requested_at")),
            "aborted_observed": "Aborted"
            in workflow.get("observed_statuses", []),
        }
    stale_workflow = next(
        (
            {
                "workflow_id": workflow_id,
                "source_revision": workflow["source_revision_at_submit"],
                "source_content_digest": workflow["source_digest_at_submit"],
                "outputs_inspected": bool(workflow.get("outputs_inspected")),
                "metadata_inspected": bool(workflow.get("metadata_inspected")),
                "status": workflow_status(workflow, current_time=current_time),
            }
            for workflow_id, workflow in sorted(workflows.items())
            if bool(workflow.get("seeded_existing"))
            and int(workflow["source_revision_at_submit"]) < current_revision
        ),
        None,
    )
    return {
        "schema_version": "science_elabftw_cromwell_public_evidence_v1",
        "source": {
            "experiment_id": int(source["experiment_id"]),
            "revision": current_revision,
            "content_digest": current_source["content_digest"],
        },
        "workflow_submissions": [
            {
                "workflow_id": workflow_id,
                "program": workflow["program"],
                "source_revision": workflow["source_revision_at_submit"],
                "source_content_digest": workflow["source_digest_at_submit"],
                "seeded_existing": bool(workflow.get("seeded_existing")),
                "status": workflow_status(workflow, current_time=current_time),
            }
            for workflow_id, workflow in sorted(workflows.items())
        ],
        "accepted_workflow": (
            None
            if not isinstance(accepted, Mapping)
            else {
                "workflow_id": accepted_id,
                "status": accepted_status,
                "source_revision": accepted["source_revision_at_submit"],
                "source_content_digest": accepted["source_digest_at_submit"],
                "outputs_digest": accepted.get("outputs_digest"),
                "metadata_digest": accepted.get("metadata_digest"),
            }
        ),
        "diagnosed_failure": diagnosed_failure,
        "superseded_workflow": superseded,
        "stale_workflow": stale_workflow,
        "result_record": (
            None
            if not isinstance(result_record, Mapping)
            else {
                "experiment_id": result_id,
                "title": result_record.get("title"),
                "body": result_record.get("body"),
                "patch_count": result_record.get("patch_count"),
                "metadata": deepcopy_json(result_record.get("metadata", {})),
                "source_revision_at_patch": result_record.get(
                    "source_revision_at_patch"
                ),
                "source_digest_at_patch": result_record.get(
                    "source_digest_at_patch"
                ),
            }
        ),
        "operation_sequence": [
            {
                "operation_id": event.get("operation_id"),
                "workflow_id": _payload(event).get("workflow_id"),
                "provider_status": _payload(event).get("provider_status"),
                "response_status_code": _payload(event).get(
                    "response_status_code"
                ),
            }
            for event in events
        ],
        "resource_counts": {
            "workflow_count": len(workflows),
            "result_record_count": len(records),
        },
    }


def _first_index(
    events: Sequence[Mapping[str, Any]],
    *,
    operation_id: str,
    workflow_id: str | None = None,
    provider_status: str | None = None,
    response_status_code: int | None = None,
    experiment_id: int | None = None,
    predicate: Any = None,
    after: int | None = None,
    before: int | None = None,
    reverse: bool = False,
) -> int | None:
    indices = range(len(events) - 1, -1, -1) if reverse else range(len(events))
    for index in indices:
        if after is not None and index <= after:
            continue
        if before is not None and index >= before:
            continue
        event = events[index]
        payload = _payload(event)
        evidence = _evidence(event)
        if event.get("operation_id") != operation_id:
            continue
        if workflow_id is not None and payload.get("workflow_id") != workflow_id:
            continue
        if (
            provider_status is not None
            and payload.get("provider_status") != provider_status
        ):
            continue
        if (
            response_status_code is not None
            and payload.get("response_status_code") != response_status_code
        ):
            continue
        if experiment_id is not None and evidence.get("experiment_id") != experiment_id:
            continue
        if predicate is not None and not predicate(event):
            continue
        return index
    return None


def _is_source_get(event: Mapping[str, Any]) -> bool:
    return (
        event.get("operation_id") == "elabftw.get_experiment"
        and _evidence(event).get("record_kind") == "source"
    )


def _payload(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = event.get("payload")
    return value if isinstance(value, Mapping) else {}


def _evidence(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = _payload(event).get("evidence")
    return value if isinstance(value, Mapping) else {}


def _strictly_ordered(*indices: int | None) -> bool:
    return all(index is not None for index in indices) and list(indices) == sorted(
        indices
    ) and len(set(indices)) == len(indices)


def min_defined(*values: int | None) -> int | None:
    selected = [value for value in values if value is not None]
    return min(selected) if selected else None


def max_defined(*values: int | None) -> int | None:
    selected = [value for value in values if value is not None]
    return max(selected) if selected else None


def _last_time(
    events: Sequence[Mapping[str, Any]],
    workflow: Mapping[str, Any],
) -> str:
    if events:
        value = events[-1].get("simulated_at")
        if isinstance(value, str):
            return value
    return str(workflow["submitted_at"])


def deepcopy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))
