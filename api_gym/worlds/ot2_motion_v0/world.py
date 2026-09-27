"""Consumer orchestration for one resettable OT-2 motion episode."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Generic, TypeVar

from api_gym.instrument_models.opentrons_ot2_v0.checks import CheckStatus
from api_gym.instrument_models.opentrons_ot2_v0.configuration import (
    DeclaredSetup,
    PhysicalSetup,
)
from api_gym.instrument_models.opentrons_ot2_v0.dynamics import (
    DynamicsTerminal,
    MotionBackend,
    NativeCompletion as DynamicsNativeCompletion,
    NativeExecution,
    evaluate_native_execution,
    project_native_outcome,
)
from api_gym.instrument_models.opentrons_ot2_v0.observations import (
    ObservationCatalog,
    ObservationScope,
    project_operator_evidence,
    project_pre_action_observation,
)
from api_gym.worlds.ot2_motion_v0.state import (
    DeferralDecision,
    EpisodeState,
    MotionEvent,
    NativeCompletion,
    ObservationRequestFact,
    SegmentRecord,
    TerminalReason,
    initial_episode_state,
)
from api_gym.worlds.ot2_motion_v0.tasks import MotionTask, ResolvedGoal


RequestT = TypeVar("RequestT")


@dataclass(frozen=True)
class MotionAction(Generic[RequestT]):
    native_request: RequestT


class OT2MotionWorld(Generic[RequestT]):
    """Stateful world shell over a runtime-owned native backend."""

    def __init__(
        self,
        *,
        task: MotionTask,
        declared_setup: DeclaredSetup,
        physical_setup: PhysicalSetup,
        backend: MotionBackend[RequestT],
        observation_catalog: ObservationCatalog,
        resolved_goal: ResolvedGoal,
        observable_setup_epoch: str,
        initial_pose_mm: tuple[float, float, float],
        initial_native_frame: str = "deck",
        initial_critical_point: str = "TIP",
    ) -> None:
        if not backend.valid:
            raise ValueError("Motion backend must be valid at episode construction")
        declared_subjects = {item.labware_id for item in declared_setup.labware}
        missing_subjects = {
            requirement.subject_id
            for requirement in task.observation_prerequisites
            if requirement.subject_id not in declared_subjects
            and requirement.subject_id != "mounted-tip"
        }
        if missing_subjects:
            raise ValueError(
                f"Task observation prerequisites are absent from declared setup: {sorted(missing_subjects)}"
            )
        self.task = task
        self.declared_setup = declared_setup
        self.physical_setup = physical_setup
        self.backend = backend
        self.observation_catalog = observation_catalog
        if resolved_goal.declared_setup_revision != declared_setup.revision:
            raise ValueError("Resolved goal must match the initial declared setup revision")
        self.resolved_goal = resolved_goal
        self.state = initial_episode_state(
            task=task,
            resolved_goal=resolved_goal,
            generation_id=backend.generation_id,
            declared_setup_revision=declared_setup.revision,
            physical_setup_revision=physical_setup.revision,
            observable_setup_epoch=observable_setup_epoch,
            initial_pose_mm=initial_pose_mm,
            initial_native_frame=initial_native_frame,
            initial_critical_point=initial_critical_point,
        )

    def observe(self) -> dict[str, Any]:
        return {
            "task": self.task.agent_payload(),
            "episode": project_pre_action_observation(
                self.declared_setup,
                model=self.task.model_disclosure,
                observable_setup_epoch=self.state.observable_setup_epoch,
                delivered_evidence=self.state.delivered_evidence,
            ),
        }

    def request_operator_observation(
        self,
        *,
        scope: ObservationScope,
        subject_id: str,
    ) -> dict[str, Any]:
        if self.state.terminal:
            raise RuntimeError("Episode is terminal")
        declared_subjects = {item.labware_id for item in self.declared_setup.labware}
        scope_subject_is_valid = (
            subject_id in declared_subjects
            if scope
            in {
                ObservationScope.LABWARE_SEATED,
                ObservationScope.OFFSET_LABEL_MATCHES_DECLARATION,
                ObservationScope.DIMENSION_MM,
            }
            else subject_id == "mounted-tip"
        )
        if not scope_subject_is_valid:
            raise PermissionError("Observation subject is outside the declared task setup")
        request_id = f"observation_request_{len(self.state.observation_requests) + 1:04d}"
        try:
            evidence = self.observation_catalog.request(
                scope=scope,
                subject_id=subject_id,
                allowed_scopes=self.task.allowed_observation_scopes,
                observable_setup_epoch=self.state.observable_setup_epoch,
            )
        except LookupError:
            self.state = self.state.with_observation_request(
                ObservationRequestFact(request_id, scope, subject_id, False, None)
            )
            return {
                "request_id": request_id,
                "scope": scope.value,
                "subject_id": subject_id,
                "available": False,
            }
        self.state = self.state.with_observation_request(
            ObservationRequestFact(
                request_id,
                scope,
                subject_id,
                True,
                evidence.observation_id,
            )
        )
        self.state = self.state.with_delivered_evidence(evidence)
        return {
            "request_id": request_id,
            "available": True,
            "observation": project_operator_evidence(
                evidence,
                current_observable_setup_epoch=self.state.observable_setup_epoch,
            ),
        }

    def execute_motion(self, action: MotionAction[RequestT]) -> dict[str, Any]:
        if self.state.terminal:
            raise RuntimeError("Episode is terminal")
        if not self.backend.valid or self.backend.generation_id != self.state.generation_id:
            execution = NativeExecution(
                command_id=f"unissued-command-{self.state.command_count + 1:08d}",
                generation_id=self.backend.generation_id,
                completion=DynamicsNativeCompletion.UNKNOWN,
                completed_segments=(),
                native_error_code="WORKER_STATE_UNKNOWN",
                native_error_message="Native worker is invalid or belongs to another generation.",
            )
        else:
            execution = self.backend.execute_motion(action.native_request)
        outcome = evaluate_native_execution(
            execution,
            expected_generation_id=self.state.generation_id,
            declared_setup=self.declared_setup,
            physical_setup=self.physical_setup,
            last_clear_pose_mm=self.state.last_clear_pose_mm,
            last_clear_native_frame=self.state.last_clear_native_frame,
            last_clear_critical_point=self.state.last_clear_critical_point,
        )
        goal_reached = self._goal_reached(outcome)
        event = _event_from_outcome(
            outcome,
            declared_setup_revision=self.declared_setup.revision,
            physical_setup_revision=self.physical_setup.revision,
        )
        terminal_reason = _terminal_reason(outcome.terminal)
        if goal_reached:
            terminal_reason = TerminalReason.GOAL_REACHED
        self.state = replace(
            self.state,
            events=(*self.state.events, event),
            last_clear_pose_mm=outcome.last_clear_pose_mm,
            last_clear_native_frame=outcome.last_clear_native_frame,
            last_clear_critical_point=outcome.last_clear_critical_point,
            physical_pose_resolved=outcome.physical_pose_resolved,
            terminal_reason=terminal_reason,
            goal_reached=goal_reached,
        )
        return project_native_outcome(outcome, goal_reached=goal_reached)

    def apply_declared_setup_update(
        self,
        setup: DeclaredSetup,
        *,
        resolved_goal: ResolvedGoal,
        observable_setup_epoch: str,
    ) -> dict[str, Any]:
        """Record an already-authorized native setup update without moving geometry."""

        if self.state.terminal:
            raise RuntimeError("Episode is terminal")
        if not self.task.offset_edit_authorized:
            raise PermissionError("This task does not authorize labware-offset edits")
        if setup.revision == self.declared_setup.revision:
            raise ValueError("A setup update requires a new revision")
        if setup.software_version != self.declared_setup.software_version:
            raise ValueError("A labware-offset update cannot change software version")
        if (
            setup.pipette_model != self.declared_setup.pipette_model
            or setup.mount != self.declared_setup.mount
            or setup.reported_tip_attached != self.declared_setup.reported_tip_attached
        ):
            raise ValueError("A labware-offset update cannot change the instrument declaration")
        previous_labware = {
            item.labware_id: (item.definition_digest, item.slot, item.configured_offset_mm)
            for item in self.declared_setup.labware
        }
        updated_labware = {
            item.labware_id: (item.definition_digest, item.slot, item.configured_offset_mm)
            for item in setup.labware
        }
        if {
            key: value[:2] for key, value in previous_labware.items()
        } != {
            key: value[:2] for key, value in updated_labware.items()
        }:
            raise ValueError("A labware-offset update cannot change loaded labware")
        if all(
            previous_labware[key][2] == updated_labware[key][2]
            for key in previous_labware
        ):
            raise ValueError("A labware-offset update must change at least one configured offset")
        if resolved_goal.declared_setup_revision != setup.revision:
            raise ValueError("Updated resolved goal must match the new setup revision")
        self.declared_setup = setup
        self.resolved_goal = resolved_goal
        self.state = self.state.with_setup_notice(
            setup.revision,
            observable_setup_epoch,
        )
        self.state = replace(self.state, resolved_goal=resolved_goal)
        return self.observe()["episode"]["declared_setup"]

    def apply_hidden_physical_setup_update(self, setup: PhysicalSetup) -> None:
        """Update trusted physical state without changing the actor-visible epoch."""

        if self.state.terminal:
            raise RuntimeError("Episode is terminal")
        if setup.revision == self.physical_setup.revision:
            raise ValueError("A physical setup change requires a new revision")
        self.physical_setup = setup
        self.state = replace(self.state, physical_setup_revision=setup.revision)

    def finish_deferred(
        self,
        *,
        decision: DeferralDecision,
        cited_observation_ids: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        self.state = self.state.finish_deferred(
            decision=decision,
            cited_observation_ids=cited_observation_ids,
        )
        return {
            "episode_terminal": True,
            "terminal_reason": TerminalReason.AGENT_DEFERRED.value,
            "goal_reached": False,
        }

    def _goal_reached(self, outcome: Any) -> bool:
        if (
            outcome.terminal is not None
            or outcome.native.completion is not DynamicsNativeCompletion.SUCCEEDED
            or outcome.path_check is None
            or outcome.path_check.status is not CheckStatus.CLEAR
            or not outcome.native.completed_segments
            or self.resolved_goal.declared_setup_revision != self.declared_setup.revision
        ):
            return False
        final_segment = outcome.native.completed_segments[-1]
        return (
            final_segment.native_frame == self.resolved_goal.native_frame
            and final_segment.native_critical_point
            == self.resolved_goal.native_critical_point
            and final_segment.end_mm == outcome.last_clear_pose_mm
            and self.resolved_goal.contains(outcome.last_clear_pose_mm)
        )


def _event_from_outcome(
    outcome: Any,
    *,
    declared_setup_revision: str,
    physical_setup_revision: str,
) -> MotionEvent:
    native = outcome.native
    return MotionEvent(
        command_id=native.command_id,
        generation_id=native.generation_id,
        native_completion=NativeCompletion(native.completion.value),
        native_completed_segments=tuple(
            SegmentRecord(
                segment.command_id,
                segment.segment_index,
                segment.start_mm,
                segment.end_mm,
            )
            for segment in native.completed_segments
        ),
        path_check=outcome.path_check,
        declared_setup_revision=declared_setup_revision,
        physical_setup_revision=physical_setup_revision,
        native_error_code=native.native_error_code,
    )


def _terminal_reason(value: DynamicsTerminal | None) -> TerminalReason | None:
    if value is None:
        return None
    return {
        DynamicsTerminal.PATH_INTERSECTION: TerminalReason.PATH_INTERSECTION,
        DynamicsTerminal.GEOMETRY_INDETERMINATE: TerminalReason.GEOMETRY_INDETERMINATE,
        DynamicsTerminal.NATIVE_FAILURE: TerminalReason.NATIVE_FAILURE,
        DynamicsTerminal.WORKER_STATE_UNKNOWN: TerminalReason.WORKER_STATE_UNKNOWN,
    }[value]
