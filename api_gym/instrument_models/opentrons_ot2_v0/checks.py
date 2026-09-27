"""Pure ordered-path checks over native segments and trusted physical geometry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from importlib.metadata import version
from typing import Sequence

from api_gym.instrument_models.geometry.collision import (
    NUMERICAL_CONTACT_TOLERANCE_MM,
    CollisionComputationError,
    UnsupportedMotionError,
    sweep_solids,
)
from api_gym.instrument_models.geometry.solids import RepresentationCoverage

from .configuration import PhysicalComponent
from .motion import AnchoredTool, NativeMotionSegment, motion_for_segment


class CheckStatus(str, Enum):
    CLEAR = "clear"
    INTERSECTION = "intersection"
    INDETERMINATE = "indeterminate"
    UNSUPPORTED = "unsupported"
    COMPUTATION_ERROR = "computation_error"


class CoverageStatus(str, Enum):
    COMPLETE_EXACT = "complete_exact"
    COMPLETE_ENCLOSING = "complete_enclosing"
    INCOMPLETE_MISSING_GEOMETRY = "incomplete_missing_geometry"
    STALE_CONFIGURATION = "stale_configuration"
    UNSUPPORTED_MOTION = "unsupported_motion"
    COMPUTATION_ERROR = "computation_error"


@dataclass(frozen=True)
class SegmentCheck:
    """One checked prefix result and geometry coverage for the full scene.

    ``checked_component_ids`` includes broadphase-disjoint components. An exact
    intersection ends evaluation, and ``unchecked_component_ids`` records the
    remaining suffix. ``coverage`` still describes geometry availability across
    every supplied component, including that unchecked suffix.
    """

    command_id: str
    segment_index: int
    status: CheckStatus
    coverage: CoverageStatus
    reason_code: str | None
    intersecting_component_id: str | None
    checked_component_ids: tuple[str, ...]
    unchecked_component_ids: tuple[str, ...]
    checked_piece_pairs: tuple[tuple[str, str, str], ...]
    geometry_digests: tuple[str, ...]
    frame_digests: tuple[str, ...]


@dataclass(frozen=True)
class PathCheck:
    segment_checks: tuple[SegmentCheck, ...]
    status: CheckStatus
    coverage: CoverageStatus
    earliest_intersecting_segment_index: int | None
    numerical_contact_tolerance_mm: float
    solver: str
    method: str
    geometry_digests: tuple[str, ...]
    frame_digests: tuple[str, ...]
    declared_setup_revision: str
    physical_setup_revision: str


def _validate_path(segments: Sequence[NativeMotionSegment]) -> tuple[NativeMotionSegment, ...]:
    ordered = tuple(segments)
    if not ordered:
        raise ValueError("A native path must contain at least one segment")
    if not all(isinstance(segment, NativeMotionSegment) for segment in ordered):
        raise TypeError("segments must contain NativeMotionSegment records")
    first = ordered[0]
    for expected_index, segment in enumerate(ordered):
        if segment.command_id != first.command_id:
            raise ValueError("All path segments must belong to one command")
        if segment.segment_index != expected_index:
            raise ValueError("Native path segment indices must be contiguous and start at zero")
        if segment.native_frame != first.native_frame:
            raise ValueError("All path segments must use one native frame")
        if segment.native_critical_point != first.native_critical_point:
            raise ValueError("All path segments must use one native critical point")
        if segment.mount != first.mount:
            raise ValueError("All path segments must use one mount")
        if segment.configuration_revision != first.configuration_revision:
            raise ValueError("All path segments must use one configuration revision")
        if expected_index and ordered[expected_index - 1].end_mm != segment.start_mm:
            raise ValueError("Native path segments must be endpoint-continuous")
    return ordered


def _unevaluated(
    segments: tuple[NativeMotionSegment, ...],
    *,
    status: CheckStatus,
    coverage: CoverageStatus,
    reason_code: str,
) -> tuple[SegmentCheck, ...]:
    return tuple(
        SegmentCheck(
            segment.command_id,
            segment.segment_index,
            status,
            coverage,
            reason_code,
            None,
            (),
            (),
            (),
            (),
            (),
        )
        for segment in segments
    )


def _path_result(
    segment_checks: tuple[SegmentCheck, ...],
    *,
    status: CheckStatus,
    coverage: CoverageStatus,
    declared_setup_revision: str,
    physical_setup_revision: str,
) -> PathCheck:
    geometry_digests = tuple(
        dict.fromkeys(digest for check in segment_checks for digest in check.geometry_digests)
    )
    frame_digests = tuple(
        dict.fromkeys(digest for check in segment_checks for digest in check.frame_digests)
    )
    intersection = next(
        (check.segment_index for check in segment_checks if check.status is CheckStatus.INTERSECTION),
        None,
    )
    return PathCheck(
        segment_checks,
        status,
        coverage,
        intersection,
        NUMERICAL_CONTACT_TOLERANCE_MM,
        f"python-fcl:{version('python-fcl')}",
        "exact_fixed_orientation_union_sweep",
        geometry_digests,
        frame_digests,
        declared_setup_revision,
        physical_setup_revision,
    )


def check_native_path(
    segments: Sequence[NativeMotionSegment],
    *,
    moving_tool: AnchoredTool | None,
    static_components: Sequence[PhysicalComponent],
    declared_setup_revision: str,
    physical_setup_revision: str,
) -> PathCheck:
    """Evaluate ordered native segments against explicitly supplied trusted state."""
    ordered = _validate_path(segments)
    if not isinstance(declared_setup_revision, str) or not declared_setup_revision.strip():
        raise ValueError("declared_setup_revision must be a non-empty string")
    if not isinstance(physical_setup_revision, str) or not physical_setup_revision.strip():
        raise ValueError("physical_setup_revision must be a non-empty string")
    if moving_tool is not None and not isinstance(moving_tool, AnchoredTool):
        raise TypeError("moving_tool must be an AnchoredTool or None")
    if ordered[0].configuration_revision != declared_setup_revision:
        checks = _unevaluated(
            ordered,
            status=CheckStatus.INDETERMINATE,
            coverage=CoverageStatus.STALE_CONFIGURATION,
            reason_code="STALE_CONFIGURATION",
        )
        return _path_result(
            checks,
            status=CheckStatus.INDETERMINATE,
            coverage=CoverageStatus.STALE_CONFIGURATION,
            declared_setup_revision=declared_setup_revision,
            physical_setup_revision=physical_setup_revision,
        )
    if any(segment.motion_kind != "translation" for segment in ordered):
        checks = _unevaluated(
            ordered,
            status=CheckStatus.UNSUPPORTED,
            coverage=CoverageStatus.UNSUPPORTED_MOTION,
            reason_code="UNSUPPORTED_MOTION",
        )
        return _path_result(
            checks,
            status=CheckStatus.UNSUPPORTED,
            coverage=CoverageStatus.UNSUPPORTED_MOTION,
            declared_setup_revision=declared_setup_revision,
            physical_setup_revision=physical_setup_revision,
        )
    if moving_tool is None:
        checks = _unevaluated(
            ordered,
            status=CheckStatus.INDETERMINATE,
            coverage=CoverageStatus.INCOMPLETE_MISSING_GEOMETRY,
            reason_code="MISSING_MOVING_GEOMETRY",
        )
        return _path_result(
            checks,
            status=CheckStatus.INDETERMINATE,
            coverage=CoverageStatus.INCOMPLETE_MISSING_GEOMETRY,
            declared_setup_revision=declared_setup_revision,
            physical_setup_revision=physical_setup_revision,
        )

    components = tuple(static_components)
    if not all(isinstance(component, PhysicalComponent) for component in components):
        raise TypeError("static_components must contain PhysicalComponent records")
    if len({component.component_id for component in components}) != len(components):
        raise ValueError("Static component IDs must be unique")
    scene_has_missing_geometry = any(component.solid is None for component in components)
    scene_has_enclosing_geometry = (
        moving_tool.geometry.coverage is RepresentationCoverage.ENCLOSING
        or any(
            component.solid is not None
            and component.solid.geometry.coverage is RepresentationCoverage.ENCLOSING
            for component in components
        )
    )
    scene_geometry_digests = tuple(
        dict.fromkeys(
            (
                moving_tool.geometry.geometry_digest,
                *(
                    component.solid.geometry.geometry_digest
                    for component in components
                    if component.solid is not None
                ),
            )
        )
    )
    static_frame_digests = tuple(
        dict.fromkeys(
            component.solid.pose.digest
            for component in components
            if component.solid is not None
        )
    )
    segment_checks: list[SegmentCheck] = []
    path_coverage = CoverageStatus.COMPLETE_EXACT
    for segment in ordered:
        try:
            motion = motion_for_segment(segment, moving_tool)
            checked_pairs: list[tuple[str, str, str]] = []
            checked_component_ids: list[str] = []
            uncertain_overlap = False
            intersecting_component: str | None = None
            for component in components:
                checked_component_ids.append(component.component_id)
                if component.solid is None:
                    continue
                result = sweep_solids(motion.start_solid, motion.end_pose, component.solid)
                checked_pairs.extend(
                    (component.component_id, moving_piece, obstacle_piece)
                    for moving_piece, obstacle_piece in result.checked_piece_pairs
                )
                pair_is_enclosing = (
                    moving_tool.geometry.coverage is RepresentationCoverage.ENCLOSING
                    or component.solid.geometry.coverage is RepresentationCoverage.ENCLOSING
                )
                if result.intersects and pair_is_enclosing:
                    uncertain_overlap = True
                elif result.intersects:
                    intersecting_component = component.component_id
                    break

            unchecked_component_ids = tuple(
                component.component_id
                for component in components[len(checked_component_ids) :]
            )

            common = dict(
                command_id=segment.command_id,
                segment_index=segment.segment_index,
                checked_component_ids=tuple(checked_component_ids),
                unchecked_component_ids=unchecked_component_ids,
                checked_piece_pairs=tuple(checked_pairs),
                geometry_digests=scene_geometry_digests,
                frame_digests=tuple(
                    dict.fromkeys(
                        (motion.start_pose.digest, motion.end_pose.digest, *static_frame_digests)
                    )
                ),
            )
            if intersecting_component is not None:
                coverage = (
                    CoverageStatus.INCOMPLETE_MISSING_GEOMETRY
                    if scene_has_missing_geometry
                    else CoverageStatus.COMPLETE_ENCLOSING
                    if scene_has_enclosing_geometry
                    else CoverageStatus.COMPLETE_EXACT
                )
                segment_checks.append(
                    SegmentCheck(
                        status=CheckStatus.INTERSECTION,
                        coverage=coverage,
                        reason_code="PATH_INTERSECTION",
                        intersecting_component_id=intersecting_component,
                        **common,
                    )
                )
                return _path_result(
                    tuple(segment_checks),
                    status=CheckStatus.INTERSECTION,
                    coverage=coverage,
                    declared_setup_revision=declared_setup_revision,
                    physical_setup_revision=physical_setup_revision,
                )
            if uncertain_overlap or scene_has_missing_geometry:
                coverage = (
                    CoverageStatus.INCOMPLETE_MISSING_GEOMETRY
                    if scene_has_missing_geometry
                    else CoverageStatus.COMPLETE_ENCLOSING
                )
                reason = (
                    "MISSING_GEOMETRY"
                    if scene_has_missing_geometry
                    else "ENCLOSING_GEOMETRY_OVERLAP"
                )
                segment_checks.append(
                    SegmentCheck(
                        status=CheckStatus.INDETERMINATE,
                        coverage=coverage,
                        reason_code=reason,
                        intersecting_component_id=None,
                        **common,
                    )
                )
                return _path_result(
                    tuple(segment_checks),
                    status=CheckStatus.INDETERMINATE,
                    coverage=coverage,
                    declared_setup_revision=declared_setup_revision,
                    physical_setup_revision=physical_setup_revision,
                )
            coverage = (
                CoverageStatus.COMPLETE_ENCLOSING
                if scene_has_enclosing_geometry
                else CoverageStatus.COMPLETE_EXACT
            )
            if coverage is CoverageStatus.COMPLETE_ENCLOSING:
                path_coverage = coverage
            segment_checks.append(
                SegmentCheck(
                    status=CheckStatus.CLEAR,
                    coverage=coverage,
                    reason_code=None,
                    intersecting_component_id=None,
                    **common,
                )
            )
        except UnsupportedMotionError:
            segment_checks.extend(
                _unevaluated(
                    (segment,),
                    status=CheckStatus.UNSUPPORTED,
                    coverage=CoverageStatus.UNSUPPORTED_MOTION,
                    reason_code="UNSUPPORTED_MOTION",
                )
            )
            return _path_result(
                tuple(segment_checks),
                status=CheckStatus.UNSUPPORTED,
                coverage=CoverageStatus.UNSUPPORTED_MOTION,
                declared_setup_revision=declared_setup_revision,
                physical_setup_revision=physical_setup_revision,
            )
        except CollisionComputationError:
            segment_checks.extend(
                _unevaluated(
                    (segment,),
                    status=CheckStatus.COMPUTATION_ERROR,
                    coverage=CoverageStatus.COMPUTATION_ERROR,
                    reason_code="COLLISION_COMPUTATION_ERROR",
                )
            )
            return _path_result(
                tuple(segment_checks),
                status=CheckStatus.COMPUTATION_ERROR,
                coverage=CoverageStatus.COMPUTATION_ERROR,
                declared_setup_revision=declared_setup_revision,
                physical_setup_revision=physical_setup_revision,
            )

    return _path_result(
        tuple(segment_checks),
        status=CheckStatus.CLEAR,
        coverage=path_coverage,
        declared_setup_revision=declared_setup_revision,
        physical_setup_revision=physical_setup_revision,
    )
