"""Immutable trusted episode facts for the OT-2 motion world."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from math import isfinite
from typing import Any

from api_gym.instrument_models.opentrons_ot2_v0.checks import PathCheck
from api_gym.instrument_models.opentrons_ot2_v0.observations import (
    ObservationScope,
    OperatorEvidence,
)
from api_gym.worlds.ot2_motion_v0.tasks import MotionTask, ResolvedGoal


Vec3 = tuple[float, float, float]


class NativeCompletion(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class TerminalReason(str, Enum):
    GOAL_REACHED = "goal_reached"
    AGENT_DEFERRED = "agent_deferred"
    PATH_INTERSECTION = "path_intersection"
    GEOMETRY_INDETERMINATE = "geometry_indeterminate"
    NATIVE_FAILURE = "native_failure"
    WORKER_STATE_UNKNOWN = "worker_state_unknown"


class DeferralBasis(str, Enum):
    REQUIRED_GEOMETRY_UNAVAILABLE = "required_geometry_unavailable"
    OPERATOR_OBSERVATION_UNAVAILABLE = "operator_observation_unavailable"
    OBSERVED_PREREQUISITE_UNMET = "observed_prerequisite_unmet"


@dataclass(frozen=True)
class ObservationRequestFact:
    request_id: str
    scope: ObservationScope
    subject_id: str
    available: bool
    observation_id: str | None

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.subject_id.strip():
            raise ValueError("Observation request identity and subject must be non-empty")
        if self.available != (self.observation_id is not None):
            raise ValueError("Available observation requests require an observation ID")


@dataclass(frozen=True)
class DeferralDecision:
    basis: DeferralBasis
    referenced_observation_id: str | None = None
    referenced_observation_request_id: str | None = None

    def __post_init__(self) -> None:
        if self.basis is DeferralBasis.REQUIRED_GEOMETRY_UNAVAILABLE:
            valid = (
                self.referenced_observation_id is None
                and self.referenced_observation_request_id is None
            )
        elif self.basis is DeferralBasis.OPERATOR_OBSERVATION_UNAVAILABLE:
            valid = (
                self.referenced_observation_id is None
                and self.referenced_observation_request_id is not None
                and bool(self.referenced_observation_request_id.strip())
            )
        else:
            valid = (
                self.referenced_observation_id is not None
                and bool(self.referenced_observation_id.strip())
                and self.referenced_observation_request_id is None
            )
        if not valid:
            raise ValueError("Deferral decision references do not match its typed basis")


@dataclass(frozen=True)
class SegmentRecord:
    command_id: str
    segment_index: int
    start_mm: Vec3
    end_mm: Vec3

    def __post_init__(self) -> None:
        if not self.command_id.strip() or self.segment_index < 0:
            raise ValueError("Segment identity must be non-empty and non-negative")
        if not all(isfinite(value) for value in (*self.start_mm, *self.end_mm)):
            raise ValueError("Segment coordinates must be finite")


@dataclass(frozen=True)
class MotionEvent:
    command_id: str
    generation_id: str
    native_completion: NativeCompletion
    native_completed_segments: tuple[SegmentRecord, ...]
    path_check: PathCheck | None
    declared_setup_revision: str
    physical_setup_revision: str
    native_error_code: str | None = None

    @property
    def segment_checks(self) -> tuple[Any, ...]:
        return () if self.path_check is None else self.path_check.segment_checks


@dataclass(frozen=True)
class EpisodeState:
    task: MotionTask
    resolved_goal: ResolvedGoal
    generation_id: str
    declared_setup_revision: str
    physical_setup_revision: str
    observable_setup_epoch: str
    initial_pose_mm: Vec3
    last_clear_pose_mm: Vec3
    last_clear_native_frame: str
    last_clear_critical_point: str
    physical_pose_resolved: bool = True
    events: tuple[MotionEvent, ...] = ()
    delivered_evidence: tuple[OperatorEvidence, ...] = ()
    observation_requests: tuple[ObservationRequestFact, ...] = ()
    cited_observation_ids: tuple[str, ...] = ()
    terminal_reason: TerminalReason | None = None
    goal_reached: bool = False
    deferred: bool = False
    deferral_decision: DeferralDecision | None = None

    def __post_init__(self) -> None:
        if not self.generation_id.strip():
            raise ValueError("generation_id must be non-empty")
        for name in (
            "declared_setup_revision",
            "physical_setup_revision",
            "observable_setup_epoch",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if not all(isfinite(value) for value in (*self.initial_pose_mm, *self.last_clear_pose_mm)):
            raise ValueError("Episode poses must be finite")
        if not self.last_clear_native_frame.strip() or not self.last_clear_critical_point.strip():
            raise ValueError("Last-clear native frame and critical point must be non-empty")
        if self.terminal_reason is None and (self.goal_reached or self.deferred):
            raise ValueError("Completed/deferred state must have a terminal reason")

    @property
    def terminal(self) -> bool:
        return self.terminal_reason is not None

    @property
    def command_count(self) -> int:
        return len(self.events)

    def with_delivered_evidence(self, evidence: OperatorEvidence) -> EpisodeState:
        if self.terminal:
            raise RuntimeError("Episode is terminal")
        if evidence.observation_id in {item.observation_id for item in self.delivered_evidence}:
            return self
        return replace(self, delivered_evidence=(*self.delivered_evidence, evidence))

    def with_observation_request(self, request: ObservationRequestFact) -> EpisodeState:
        if self.terminal:
            raise RuntimeError("Episode is terminal")
        if request.request_id in {item.request_id for item in self.observation_requests}:
            raise ValueError("Observation request IDs must be unique")
        return replace(self, observation_requests=(*self.observation_requests, request))

    def with_setup_notice(self, revision: str, observable_setup_epoch: str) -> EpisodeState:
        if self.terminal:
            raise RuntimeError("Episode is terminal")
        if not revision.strip() or revision == self.declared_setup_revision:
            raise ValueError("A setup change requires a new non-empty revision")
        if (
            not observable_setup_epoch.strip()
            or observable_setup_epoch == self.observable_setup_epoch
        ):
            raise ValueError("A visible setup change requires a new observable setup epoch")
        return replace(
            self,
            declared_setup_revision=revision,
            observable_setup_epoch=observable_setup_epoch,
        )

    def finish_deferred(
        self,
        *,
        decision: DeferralDecision,
        cited_observation_ids: tuple[str, ...] = (),
    ) -> EpisodeState:
        if self.terminal:
            raise RuntimeError("Episode is terminal")
        return replace(
            self,
            terminal_reason=TerminalReason.AGENT_DEFERRED,
            deferred=True,
            deferral_decision=decision,
            cited_observation_ids=tuple(cited_observation_ids),
        )

    def trusted_summary(self) -> dict[str, Any]:
        return {
            "task_id": self.task.task_id,
            "generation_id": self.generation_id,
            "declared_setup_revision": self.declared_setup_revision,
            "physical_setup_revision": self.physical_setup_revision,
            "observable_setup_epoch": self.observable_setup_epoch,
            "last_clear_pose_mm": list(self.last_clear_pose_mm),
            "physical_pose_resolved": self.physical_pose_resolved,
            "terminal_reason": None if self.terminal_reason is None else self.terminal_reason.value,
            "goal_reached": self.goal_reached,
            "deferred": self.deferred,
            "command_count": self.command_count,
        }


def initial_episode_state(
    *,
    task: MotionTask,
    resolved_goal: ResolvedGoal,
    generation_id: str,
    declared_setup_revision: str,
    physical_setup_revision: str,
    observable_setup_epoch: str,
    initial_pose_mm: Vec3,
    initial_native_frame: str,
    initial_critical_point: str,
) -> EpisodeState:
    return EpisodeState(
        task=task,
        resolved_goal=resolved_goal,
        generation_id=generation_id,
        declared_setup_revision=declared_setup_revision,
        physical_setup_revision=physical_setup_revision,
        observable_setup_epoch=observable_setup_epoch,
        initial_pose_mm=initial_pose_mm,
        last_clear_pose_mm=initial_pose_mm,
        last_clear_native_frame=initial_native_frame,
        last_clear_critical_point=initial_critical_point,
    )
