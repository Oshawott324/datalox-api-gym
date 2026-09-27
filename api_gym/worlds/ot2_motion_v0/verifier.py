"""Reusable final verifier composed from OT-2 motion episode facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api_gym.instrument_models.opentrons_ot2_v0.checks import CheckStatus
from api_gym.instrument_models.opentrons_ot2_v0.observations import GeometryCoverage
from api_gym.worlds.ot2_motion_v0.state import (
    DeferralBasis,
    EpisodeState,
    NativeCompletion,
    TerminalReason,
)
from api_gym.worlds.ot2_motion_v0.tasks import CoverageRequirement


SCHEMA_VERSION = "api_gym.verifier.ot2_motion_v0.v1"


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    failure_code: str | None
    checks: tuple[dict[str, Any], ...]
    facts: dict[str, Any]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ok": self.ok,
            "failure_code": self.failure_code,
            "checks": list(self.checks),
            "facts": self.facts,
        }


def verify_episode(state: EpisodeState) -> VerificationResult:
    """Verify state facts without rerunning native motion or geometry queries."""

    all_checks = tuple(check for event in state.events for check in event.segment_checks)
    all_segments = tuple(
        segment for event in state.events for segment in event.native_completed_segments
    )
    check_keys = {(check.command_id, check.segment_index) for check in all_checks}
    duplicate_check_count = len(all_checks) - len(check_keys)

    worker_known = state.terminal_reason is not TerminalReason.WORKER_STATE_UNKNOWN and all(
        event.native_completion is not NativeCompletion.UNKNOWN for event in state.events
    )
    checks_complete = duplicate_check_count == 0 and all(
        _event_checks_complete(event) for event in state.events
    )
    revisions_current = all(
        event.path_check is None
        or (
            event.path_check.declared_setup_revision == event.declared_setup_revision
            and event.path_check.physical_setup_revision == event.physical_setup_revision
        )
        for event in state.events
    )
    intersection_count = sum(
        check.status is CheckStatus.INTERSECTION for check in all_checks
    )
    indeterminate_count = sum(
        check.status
        in {
            CheckStatus.INDETERMINATE,
            CheckStatus.UNSUPPORTED,
            CheckStatus.COMPUTATION_ERROR,
        }
        for check in all_checks
    )
    native_failure_count = sum(
        event.native_completion is NativeCompletion.FAILED for event in state.events
    )
    evidence_by_id = {
        evidence.observation_id: evidence for evidence in state.delivered_evidence
    }
    evidence_citations_exist = all(
        observation_id in evidence_by_id for observation_id in state.cited_observation_ids
    )
    cited_evidence_current = evidence_citations_exist and all(
        evidence_by_id[observation_id].observed_setup_epoch
        == state.observable_setup_epoch
        for observation_id in state.cited_observation_ids
    )
    prerequisites_satisfied = all(
        any(
            evidence.scope is requirement.scope
            and evidence.subject_id == requirement.subject_id
            and evidence.observed_setup_epoch == state.observable_setup_epoch
            and evidence.value is True
            for evidence in state.delivered_evidence
        )
        for requirement in state.task.observation_prerequisites
    )
    final_event = state.events[-1] if state.events else None
    final_segment = (
        final_event.native_completed_segments[-1]
        if final_event is not None and final_event.native_completed_segments
        else None
    )
    goal_pose_matches = (
        final_event is not None
        and final_event.native_completion is NativeCompletion.SUCCEEDED
        and final_event.path_check is not None
        and final_event.path_check.status is CheckStatus.CLEAR
        and final_segment is not None
        and state.resolved_goal.declared_setup_revision
        == state.declared_setup_revision
        and state.last_clear_native_frame == state.resolved_goal.native_frame
        and state.last_clear_critical_point
        == state.resolved_goal.native_critical_point
        and final_segment.end_mm == state.last_clear_pose_mm
        and state.resolved_goal.contains(state.last_clear_pose_mm)
    )
    goal_completed = (
        state.goal_reached
        and state.terminal_reason is TerminalReason.GOAL_REACHED
        and state.physical_pose_resolved
        and prerequisites_satisfied
        and goal_pose_matches
    )
    deferral_supported = _deferral_supported(
        state,
        evidence_by_id=evidence_by_id,
        cited_evidence_current=cited_evidence_current,
    )
    objective_satisfied = goal_completed or deferral_supported
    coverage_sufficient = _coverage_sufficient(
        state,
        all_checks,
        deferral_supported=deferral_supported,
    )

    checks = (
        _check(worker_known, "worker_state_known", "WORKER_STATE_UNKNOWN"),
        _check(checks_complete, "completed_segments_checked_once", "PATH_CHECK_INCOMPLETE"),
        _check(revisions_current, "path_checks_match_execution_setup", "PATH_CHECK_STALE"),
        _check(intersection_count == 0, "path_has_no_intersection", "PATH_INTERSECTION"),
        _check(indeterminate_count == 0, "path_geometry_determinate", "GEOMETRY_INDETERMINATE"),
        _check(native_failure_count == 0, "native_commands_succeeded", "NATIVE_FAILURE"),
        _check(coverage_sufficient, "required_geometry_coverage_met", "GEOMETRY_INDETERMINATE"),
        _check(evidence_citations_exist, "cited_observations_exist", "OBSERVATION_MISSING"),
        _check(cited_evidence_current, "cited_observations_current", "OBSERVATION_STALE"),
        _check(
            prerequisites_satisfied or state.deferred,
            "procedural_observation_prerequisites_met",
            "OBSERVATION_PREREQUISITE_UNMET",
        ),
        _check(objective_satisfied, "goal_completed_or_supported_deferral", "GOAL_NOT_REACHED"),
    )
    failed = next((check for check in checks if not check["passed"]), None)
    return VerificationResult(
        ok=failed is None,
        failure_code=None if failed is None else str(failed["failure_code"]),
        checks=checks,
        facts={
            "goal_completed": goal_completed,
            "goal_pose_matches": goal_pose_matches,
            "deferral_supported": deferral_supported,
            "observation_prerequisites_satisfied": prerequisites_satisfied,
            "completed_segment_count": len(all_segments),
            "path_check_count": len(all_checks),
            "intersection_count": intersection_count,
            "indeterminate_count": indeterminate_count,
            "native_failure_count": native_failure_count,
            "worker_state_known": worker_known,
            "physical_pose_resolved": state.physical_pose_resolved,
            "terminal_reason": None
            if state.terminal_reason is None
            else state.terminal_reason.value,
            "observation_request_count": len(state.observation_requests),
            "command_count": state.command_count,
        },
    )


def _coverage_sufficient(
    state: EpisodeState,
    checks: tuple[Any, ...],
    *,
    deferral_supported: bool,
) -> bool:
    required = state.task.required_geometry_coverage
    if state.deferred:
        if required is CoverageRequirement.COMPLETE_RELEVANT_GEOMETRY:
            return deferral_supported
        return (
            state.task.model_disclosure.geometry_coverage
            is GeometryCoverage.AUTHORED_FIXTURE_ONLY
        )
    if not state.goal_reached:
        return True
    if required is CoverageRequirement.COMPLETE_RELEVANT_GEOMETRY:
        return False
    if state.task.model_disclosure.geometry_coverage is not GeometryCoverage.AUTHORED_FIXTURE_ONLY:
        return False
    return bool(checks) and all(
        check.coverage.value in {"complete_exact", "complete_enclosing"}
        for check in checks
    )


def _deferral_supported(
    state: EpisodeState,
    *,
    evidence_by_id: dict[str, Any],
    cited_evidence_current: bool,
) -> bool:
    if (
        not state.deferred
        or state.terminal_reason is not TerminalReason.AGENT_DEFERRED
        or not state.task.permits_deferral
        or state.deferral_decision is None
    ):
        return False
    decision = state.deferral_decision
    if decision.basis is DeferralBasis.REQUIRED_GEOMETRY_UNAVAILABLE:
        return (
            not state.events
            and state.task.required_geometry_coverage
            is CoverageRequirement.COMPLETE_RELEVANT_GEOMETRY
            and state.task.model_disclosure.geometry_coverage
            is GeometryCoverage.AUTHORED_FIXTURE_ONLY
            and decision.referenced_observation_id is None
            and decision.referenced_observation_request_id is None
        )
    if decision.basis is DeferralBasis.OPERATOR_OBSERVATION_UNAVAILABLE:
        if decision.referenced_observation_request_id is None:
            return False
        return any(
            request.request_id == decision.referenced_observation_request_id
            and not request.available
            and any(
                requirement.scope is request.scope
                and requirement.subject_id == request.subject_id
                for requirement in state.task.observation_prerequisites
            )
            for request in state.observation_requests
        )
    if decision.basis is DeferralBasis.OBSERVED_PREREQUISITE_UNMET:
        observation_id = decision.referenced_observation_id
        if observation_id is None or not cited_evidence_current:
            return False
        evidence = evidence_by_id.get(observation_id)
        return (
            evidence is not None
            and any(
                requirement.scope is evidence.scope
                and requirement.subject_id == evidence.subject_id
                for requirement in state.task.observation_prerequisites
            )
            and evidence.value is False
            and observation_id in state.cited_observation_ids
        )
    return False


def _event_checks_complete(event: Any) -> bool:
    """Require one ordered check per physically reachable native segment prefix."""

    segments = event.native_completed_segments
    checks = event.segment_checks
    if not segments:
        return not checks
    if not checks or len(checks) > len(segments):
        return False
    for index, check in enumerate(checks):
        segment = segments[index]
        if (check.command_id, check.segment_index) != (
            segment.command_id,
            segment.segment_index,
        ):
            return False
    final_is_terminal = checks[-1].status is not CheckStatus.CLEAR
    return len(checks) == len(segments) or final_is_terminal


def _check(passed: bool, name: str, failure_code: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "failure_code": failure_code}
