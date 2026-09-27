"""Ordered OT-2 motion transitions over native results and physical checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ulp
from typing import Any, Protocol, TypeVar

from api_gym.instrument_models.geometry.frames import Vec3

from .checks import CheckStatus, PathCheck, check_native_path
from .configuration import DeclaredSetup, PhysicalSetup
from .motion import NativeMotionSegment


RequestT = TypeVar("RequestT", contravariant=True)


class NativeCompletion(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class DynamicsTerminal(str, Enum):
    PATH_INTERSECTION = "path_intersection"
    GEOMETRY_INDETERMINATE = "geometry_indeterminate"
    NATIVE_FAILURE = "native_failure"
    WORKER_STATE_UNKNOWN = "worker_state_unknown"


@dataclass(frozen=True)
class NativeExecution:
    """Consumer-normalized native result; not a vendor response schema."""

    command_id: str
    generation_id: str
    completion: NativeCompletion
    completed_segments: tuple[NativeMotionSegment, ...]
    native_error_code: str | None = None
    native_error_message: str | None = None

    def __post_init__(self) -> None:
        if not self.command_id.strip() or not self.generation_id.strip():
            raise ValueError("Native command and generation IDs must be non-empty")
        segments = tuple(self.completed_segments)
        if any(segment.command_id != self.command_id for segment in segments):
            raise ValueError("Every completed segment must belong to the native command")
        if self.completion is NativeCompletion.SUCCEEDED and self.native_error_code is not None:
            raise ValueError("A successful native command cannot contain an error code")
        object.__setattr__(self, "completed_segments", segments)


class MotionBackend(Protocol[RequestT]):
    """Small consumer boundary implemented by the runtime adapter."""

    @property
    def generation_id(self) -> str: ...

    @property
    def valid(self) -> bool: ...

    def execute_motion(self, request: RequestT) -> NativeExecution: ...


@dataclass(frozen=True)
class DynamicsOutcome:
    native: NativeExecution
    path_check: PathCheck | None
    last_clear_pose_mm: Vec3
    last_clear_native_frame: str
    last_clear_critical_point: str
    physical_pose_resolved: bool
    terminal: DynamicsTerminal | None


def evaluate_native_execution(
    execution: NativeExecution,
    *,
    expected_generation_id: str,
    declared_setup: DeclaredSetup,
    physical_setup: PhysicalSetup,
    last_clear_pose_mm: Vec3,
    last_clear_native_frame: str,
    last_clear_critical_point: str,
) -> DynamicsOutcome:
    """Check one observed native segment sequence exactly once, in order."""

    if execution.generation_id != expected_generation_id:
        return DynamicsOutcome(
            native=execution,
            path_check=None,
            last_clear_pose_mm=last_clear_pose_mm,
            last_clear_native_frame=last_clear_native_frame,
            last_clear_critical_point=last_clear_critical_point,
            physical_pose_resolved=False,
            terminal=DynamicsTerminal.WORKER_STATE_UNKNOWN,
        )

    path_check = None
    current_pose = last_clear_pose_mm
    current_frame = last_clear_native_frame
    current_critical_point = last_clear_critical_point
    pose_resolved = True
    geometry_terminal: DynamicsTerminal | None = None
    if execution.completed_segments:
        first = execution.completed_segments[0]
        if (
            first.native_frame != last_clear_native_frame
            or first.native_critical_point != last_clear_critical_point
            or not _same_native_position(first.start_mm, last_clear_pose_mm)
        ):
            return DynamicsOutcome(
                native=execution,
                path_check=None,
                last_clear_pose_mm=last_clear_pose_mm,
                last_clear_native_frame=last_clear_native_frame,
                last_clear_critical_point=last_clear_critical_point,
                physical_pose_resolved=False,
                terminal=DynamicsTerminal.WORKER_STATE_UNKNOWN,
            )
        try:
            path_check = check_native_path(
                execution.completed_segments,
                moving_tool=physical_setup.moving_tool,
                static_components=physical_setup.static_components,
                declared_setup_revision=declared_setup.revision,
                physical_setup_revision=physical_setup.revision,
            )
        except ValueError:
            return DynamicsOutcome(
                native=execution,
                path_check=None,
                last_clear_pose_mm=last_clear_pose_mm,
                last_clear_native_frame=last_clear_native_frame,
                last_clear_critical_point=last_clear_critical_point,
                physical_pose_resolved=False,
                terminal=DynamicsTerminal.WORKER_STATE_UNKNOWN,
            )
        for segment, segment_check in zip(
            execution.completed_segments,
            path_check.segment_checks,
            strict=False,
        ):
            if segment_check.status is CheckStatus.CLEAR:
                current_pose = segment.end_mm
                current_frame = segment.native_frame
                current_critical_point = segment.native_critical_point
                continue
            pose_resolved = False
            geometry_terminal = (
                DynamicsTerminal.PATH_INTERSECTION
                if segment_check.status is CheckStatus.INTERSECTION
                else DynamicsTerminal.GEOMETRY_INDETERMINATE
            )
            break

    if execution.completion is NativeCompletion.UNKNOWN:
        return DynamicsOutcome(
            native=execution,
            path_check=path_check,
            last_clear_pose_mm=current_pose,
            last_clear_native_frame=current_frame,
            last_clear_critical_point=current_critical_point,
            physical_pose_resolved=False,
            terminal=DynamicsTerminal.WORKER_STATE_UNKNOWN,
        )
    if geometry_terminal is not None:
        return DynamicsOutcome(
            native=execution,
            path_check=path_check,
            last_clear_pose_mm=current_pose,
            last_clear_native_frame=current_frame,
            last_clear_critical_point=current_critical_point,
            physical_pose_resolved=pose_resolved,
            terminal=geometry_terminal,
        )
    if execution.completion is NativeCompletion.FAILED:
        return DynamicsOutcome(
            native=execution,
            path_check=path_check,
            last_clear_pose_mm=current_pose,
            last_clear_native_frame=current_frame,
            last_clear_critical_point=current_critical_point,
            physical_pose_resolved=pose_resolved,
            terminal=DynamicsTerminal.NATIVE_FAILURE,
        )
    if not execution.completed_segments or path_check is None:
        return DynamicsOutcome(
            native=execution,
            path_check=None,
            last_clear_pose_mm=current_pose,
            last_clear_native_frame=current_frame,
            last_clear_critical_point=current_critical_point,
            physical_pose_resolved=False,
            terminal=DynamicsTerminal.WORKER_STATE_UNKNOWN,
        )
    return DynamicsOutcome(
        native=execution,
        path_check=path_check,
        last_clear_pose_mm=current_pose,
        last_clear_native_frame=current_frame,
        last_clear_critical_point=current_critical_point,
        physical_pose_resolved=True,
        terminal=None,
    )


def project_native_outcome(outcome: DynamicsOutcome, *, goal_reached: bool) -> dict[str, Any]:
    """Expose bounded command status without geometric witnesses or hidden transforms."""

    return {
        "command_id": outcome.native.command_id,
        "native_completion": outcome.native.completion.value,
        "native_error": None
        if outcome.native.native_error_code is None
        else {
            "code": outcome.native.native_error_code,
            "message": outcome.native.native_error_message,
        },
        "completed_segment_count": len(outcome.native.completed_segments),
        "episode_terminal": outcome.terminal is not None or goal_reached,
        "terminal_reason": (
            "goal_reached"
            if goal_reached
            else None
            if outcome.terminal is None
            else outcome.terminal.value
        ),
        "goal_reached": goal_reached,
        "physical_pose_resolved": outcome.physical_pose_resolved,
    }


def _same_native_position(first: Vec3, second: Vec3) -> bool:
    """Compare native binary64 coordinates within one representation step."""

    return all(
        abs(left - right) <= max(ulp(left), ulp(right))
        for left, right in zip(first, second, strict=True)
    )
