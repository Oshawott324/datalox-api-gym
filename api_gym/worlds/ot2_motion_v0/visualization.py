"""Researcher-only visualization export for recorded OT-2 motion events."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from math import dist
from typing import Any, Literal

from api_gym.instrument_models.geometry.frames import RigidTransform
from api_gym.instrument_models.geometry.solids import (
    Box,
    ConvexPiece,
    ConvexPolyhedron,
    Sphere,
)
from api_gym.instrument_models.opentrons_ot2_v0.checks import CheckStatus, SegmentCheck
from api_gym.instrument_models.opentrons_ot2_v0.configuration import (
    DeclaredSetup,
    PhysicalSetup,
)
from api_gym.worlds.ot2_motion_v0.state import EpisodeState, MotionEvent, SegmentRecord
from api_gym.worlds.ot2_motion_v0.tasks import native_binary64_goal_tolerance_mm

VISUALIZATION_SCHEMA_VERSION = "datalox_visualization_run_v1"
RENDERER_ID = "opentrons_motion_v1"
RENDERER_PROTOCOL_VERSION = "1.0.0"

_IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
_IDENTITY_ROTATION = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)


class UnsupportedVisualizationExport(ValueError):
    """The v1 viewer cannot represent a trusted world fact without information loss."""


@dataclass(frozen=True)
class GeometryPresentation:
    """Explicit researcher-facing labels for one admitted geometry source."""

    provenance_kind: Literal["sourced", "authored"]
    body_label: str
    provenance_label: str

    def __post_init__(self) -> None:
        if self.provenance_kind not in ("sourced", "authored"):
            raise ValueError("provenance_kind must be sourced or authored")
        if not self.body_label.strip() or not self.provenance_label.strip():
            raise ValueError("Geometry presentation labels must be non-empty")


def export_motion_visualization(
    *,
    run_id: str,
    state: EpisodeState,
    declared_setup: DeclaredSetup,
    physical_setup: PhysicalSetup,
    geometry_presentations: Mapping[str, GeometryPresentation],
) -> dict[str, Any]:
    """Build one strict visualization document from trusted world records.

    This is a researcher export. It is not an actor observation and must never be
    added to ``OT2MotionWorld.observe()``.
    """

    _require_identifier(run_id, "run_id")
    if not state.events:
        raise UnsupportedVisualizationExport("A motion visualization requires a recorded event")
    _validate_setup_scope(state, declared_setup, physical_setup)

    movements, cases, exported_checks = _export_movements(state.events)
    if not _same_native_position(state.initial_pose_mm, movements[0]["start_mm"]):
        raise UnsupportedVisualizationExport(
            "The moving geometry pose does not match the first recorded segment"
        )
    bodies, missing_components = _export_bodies(
        state,
        physical_setup,
        geometry_presentations,
        initial_position=tuple(movements[0]["start_mm"]),
    )
    last_movement = movements[-1]
    expected_last_clear = (
        last_movement["start_mm"]
        if last_movement["check"]["intersects"]
        else last_movement["end_mm"]
    )
    if not _same_native_position(state.last_clear_pose_mm, expected_last_clear):
        raise UnsupportedVisualizationExport(
            "The episode last-clear pose does not match its checked motion prefix"
        )
    if last_movement["check"]["intersects"] and state.physical_pose_resolved:
        raise UnsupportedVisualizationExport(
            "An intersecting terminal segment cannot have a resolved physical pose"
        )

    source_record = _source_record(state, declared_setup, physical_setup, exported_checks)
    record_digest = _canonical_digest(source_record)
    source_artifact_id = "trusted-motion-record"
    model = state.task.model_disclosure

    resources = [_resource(body) for body in bodies]
    workflow_stages = [
        {
            "id": case["id"],
            "label": f"Command {case['order']}",
            "kind": "recorded_motion_check",
            "provider": f"Opentrons {declared_setup.software_version}",
            "status": "completed",
        }
        for case in cases
    ]
    steps = _steps(movements, exported_checks, source_artifact_id)

    return {
        "schema_version": VISUALIZATION_SCHEMA_VERSION,
        "run_id": run_id,
        "world_id": "ot2_motion_v0",
        "presentation": {
            "title": "OT-2 recorded motion checks",
            "summary": (
                "Recorded native segments checked against the trusted geometry admitted "
                "for this episode."
            ),
            "subject": "Researcher motion evidence",
            "mode": "recorded_run",
            "status": "completed",
            "agent": None,
        },
        "workflow": {
            "stages": workflow_stages,
            "edges": [
                {"from": previous["id"], "to": current["id"]}
                for previous, current in zip(workflow_stages, workflow_stages[1:], strict=False)
            ],
        },
        "renderer": {
            "id": RENDERER_ID,
            "protocol_version": RENDERER_PROTOCOL_VERSION,
            "payload": {
                "visibility": "researcher_only",
                "source": {
                    "kind": "recorded_model_output",
                    "claim": model.fixture_label,
                    "record_sha256": record_digest,
                    "software_versions": {
                        "api_gym_world": "ot2_motion_v0",
                        "opentrons": declared_setup.software_version,
                    },
                    "digests": _source_digests(
                        record_digest,
                        declared_setup,
                        physical_setup,
                        state.events,
                    ),
                },
                "frame": {
                    "id": "deck",
                    "units": "mm",
                    "position_reference": (
                        "Recorded native critical-point coordinates; rendered geometry uses "
                        "fixed orientation only."
                    ),
                },
                "bodies": bodies,
                "cases": cases,
                "movements": movements,
                "coverage": {
                    "represented_body_ids": [body["id"] for body in bodies],
                    "missing_components": missing_components,
                    "geometry_admission": (
                        f"{model.fixture_label}; {model.geometry_coverage.value}"
                    ),
                    "physical_validation": model.physical_validation,
                },
            },
        },
        "resources": resources,
        "artifacts": [
            {
                "id": source_artifact_id,
                "label": "Trusted OT-2 motion record",
                "type": "researcher_motion_record",
                "summary": (
                    "Immutable native segments, ordered path checks, coverage, and digests "
                    "consumed by this visualization export."
                ),
                "data": source_record,
            }
        ],
        "steps": steps,
        "outcome": _outcome(state),
    }


def _validate_setup_scope(
    state: EpisodeState,
    declared_setup: DeclaredSetup,
    physical_setup: PhysicalSetup,
) -> None:
    if state.declared_setup_revision != declared_setup.revision:
        raise UnsupportedVisualizationExport(
            "The supplied declared setup does not match the episode state"
        )
    if state.physical_setup_revision != physical_setup.revision:
        raise UnsupportedVisualizationExport(
            "The supplied physical setup does not match the episode state"
        )
    if state.last_clear_native_frame != "deck":
        raise UnsupportedVisualizationExport("The v1 viewer supports only deck-frame motion")
    for event in state.events:
        if event.generation_id != state.generation_id:
            raise UnsupportedVisualizationExport(
                "A motion event belongs to a different worker generation"
            )
        if event.declared_setup_revision != declared_setup.revision:
            raise UnsupportedVisualizationExport(
                "The v1 export cannot combine historical declared setup revisions"
            )
        if event.physical_setup_revision != physical_setup.revision:
            raise UnsupportedVisualizationExport(
                "The v1 export cannot combine historical physical setup revisions"
            )


def _export_bodies(
    state: EpisodeState,
    physical_setup: PhysicalSetup,
    presentations: Mapping[str, GeometryPresentation],
    *,
    initial_position: tuple[float, float, float],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    tool = physical_setup.moving_tool
    if tool is None:
        raise UnsupportedVisualizationExport("The v1 viewer requires admitted moving geometry")
    if tool.native_critical_point != state.last_clear_critical_point:
        raise UnsupportedVisualizationExport(
            "The moving geometry anchor does not match the recorded critical point"
        )
    if len(tool.geometry.pieces) != 1:
        raise UnsupportedVisualizationExport(
            "The v1 viewer does not support moving multi-piece geometry"
        )

    admitted_geometries = {tool.geometry.geometry_id: tool.geometry}
    for component in physical_setup.static_components:
        if component.solid is not None:
            geometry = component.solid.geometry
            previous = admitted_geometries.get(geometry.geometry_id)
            if previous is not None and previous.geometry_digest != geometry.geometry_digest:
                raise UnsupportedVisualizationExport(
                    f"Geometry ID {geometry.geometry_id!r} has conflicting digests"
                )
            admitted_geometries[geometry.geometry_id] = geometry
    if set(presentations) != set(admitted_geometries):
        raise ValueError(
            "geometry_presentations must exactly label every admitted geometry_id"
        )

    moving_piece = tool.geometry.pieces[0]
    moving_piece_from_critical = tool.critical_from_geometry.compose(moving_piece.pose)
    _require_identity_pose(
        moving_piece_from_critical,
        "Moving geometry must be centered on the recorded critical point",
    )
    moving_presentation = presentations[tool.geometry.geometry_id]
    bodies = [
        _body(
            body_id="moving-body",
            label=moving_presentation.body_label,
            role="moving",
            presentation=moving_presentation,
            piece=moving_piece,
            position=initial_position,
        )
    ]

    for component_index, component in enumerate(physical_setup.static_components, start=1):
        if component.solid is None:
            continue
        solid = component.solid
        if solid.pose.target_frame != "deck":
            raise UnsupportedVisualizationExport(
                f"Static component {component.component_id!r} is not in the deck frame"
            )
        presentation = presentations[solid.geometry.geometry_id]
        for piece_index, piece in enumerate(solid.geometry.pieces, start=1):
            deck_from_piece = solid.pose.compose(piece.pose)
            _require_fixed_orientation(
                deck_from_piece,
                f"Static component {component.component_id!r} has unsupported rotation",
            )
            label = presentation.body_label
            if len(solid.geometry.pieces) > 1:
                label = f"{label} / {piece.piece_id}"
            bodies.append(
                _body(
                    body_id=f"body-{component_index:03d}-piece-{piece_index:03d}",
                    label=label,
                    role="obstacle",
                    presentation=presentation,
                    piece=piece,
                    position=deck_from_piece.translation_mm,
                )
            )

    missing = [
        {
            "id": f"missing-physical-{index:03d}",
            "label": component.component_id,
            "reason": component.missing_geometry_reason or "Geometry is unavailable.",
        }
        for index, component in enumerate(physical_setup.static_components, start=1)
        if component.solid is None
    ]
    model = state.task.model_disclosure
    missing.extend(
        (
            {
                "id": "model-scope-moving",
                "label": "Instrument geometry",
                "reason": model.moving_body_coverage,
            },
            {
                "id": "model-scope-static",
                "label": "Static workcell geometry",
                "reason": model.static_body_coverage,
            },
        )
    )
    return bodies, missing


def _body(
    *,
    body_id: str,
    label: str,
    role: str,
    presentation: GeometryPresentation,
    piece: ConvexPiece,
    position: tuple[float, float, float],
) -> dict[str, Any]:
    return {
        "id": body_id,
        "label": label,
        "role": role,
        "provenance": {
            "kind": presentation.provenance_kind,
            "label": presentation.provenance_label,
        },
        "shape": _shape(piece),
        "pose_mm": {"position": list(position)},
    }


def _shape(piece: ConvexPiece) -> dict[str, Any]:
    shape = piece.shape
    if isinstance(shape, Sphere):
        return {"kind": "sphere", "radius_mm": shape.radius_mm}
    if isinstance(shape, Box):
        return {"kind": "box", "dimensions_mm": list(shape.dimensions_mm)}
    if isinstance(shape, ConvexPolyhedron):
        return {
            "kind": "convex",
            "vertices_mm": [list(vertex) for vertex in shape.vertices_mm],
            "faces": [list(face) for face in shape.faces],
        }
    raise TypeError(f"Unsupported convex piece shape: {type(shape).__name__}")


def _require_fixed_orientation(transform: RigidTransform, message: str) -> None:
    if transform.rotation != _IDENTITY_ROTATION:
        raise UnsupportedVisualizationExport(message)


def _require_identity_pose(transform: RigidTransform, message: str) -> None:
    _require_fixed_orientation(transform, message)
    if transform.translation_mm != (0.0, 0.0, 0.0):
        raise UnsupportedVisualizationExport(message)


def _export_movements(
    events: tuple[MotionEvent, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[SegmentCheck]]:
    movements: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    exported_checks: list[SegmentCheck] = []
    terminal_intersection = False

    for event_order, event in enumerate(events, start=1):
        if terminal_intersection:
            raise UnsupportedVisualizationExport(
                "Motion events after an intersecting segment have unknown physical pose"
            )
        if event.path_check is None or not event.path_check.segment_checks:
            raise UnsupportedVisualizationExport(
                f"Motion event {event.command_id!r} has no visualizable path checks"
            )
        if (
            event.path_check.declared_setup_revision != event.declared_setup_revision
            or event.path_check.physical_setup_revision != event.physical_setup_revision
        ):
            raise UnsupportedVisualizationExport(
                "A path check does not match its motion event setup revisions"
            )
        segments = {segment.segment_index: segment for segment in event.native_completed_segments}
        case_id = f"case-{event_order:04d}"
        case_movement_ids: list[str] = []
        case_intersects = False
        for segment_order, check in enumerate(event.path_check.segment_checks, start=1):
            if check.segment_index != segment_order - 1:
                raise UnsupportedVisualizationExport(
                    "Path checks must be an ordered segment prefix starting at zero"
                )
            if check.status not in (CheckStatus.CLEAR, CheckStatus.INTERSECTION):
                raise UnsupportedVisualizationExport(
                    f"Segment check status {check.status.value!r} is unsupported by renderer v1"
                )
            segment = segments.get(check.segment_index)
            if segment is None or segment.command_id != check.command_id:
                raise UnsupportedVisualizationExport(
                    "Path checks do not match the recorded native segment identities"
                )
            if check.command_id != event.command_id:
                raise UnsupportedVisualizationExport(
                    "Path checks do not match the recorded motion event"
                )
            intersects = check.status is CheckStatus.INTERSECTION
            movement_id = f"movement-{len(movements) + 1:04d}"
            movement = {
                "id": movement_id,
                "case_id": case_id,
                "order": len(movements) + 1,
                "segment_order": segment_order,
                "moving_body_id": "moving-body",
                "start_mm": list(segment.start_mm),
                "end_mm": list(segment.end_mm),
                "speed_mm_s": None,
                "check": {
                    "intersects": intersects,
                    "method": event.path_check.method,
                    "numerical_contact_tolerance_mm": (
                        event.path_check.numerical_contact_tolerance_mm
                    ),
                },
            }
            if movements and movement["start_mm"] != movements[-1]["end_mm"]:
                raise UnsupportedVisualizationExport(
                    "Recorded checked motion segments are not endpoint-continuous"
                )
            movements.append(movement)
            exported_checks.append(check)
            case_movement_ids.append(movement_id)
            case_intersects = case_intersects or intersects
            if intersects:
                terminal_intersection = True
                if segment_order != len(event.path_check.segment_checks):
                    raise UnsupportedVisualizationExport(
                        "Path checks continue after an intersecting segment"
                    )
        cases.append(
            {
                "id": case_id,
                "order": event_order,
                "movement_ids": case_movement_ids,
                "check": {"intersects": case_intersects},
            }
        )
    return movements, cases, exported_checks


def _source_record(
    state: EpisodeState,
    declared_setup: DeclaredSetup,
    physical_setup: PhysicalSetup,
    exported_checks: list[SegmentCheck],
) -> dict[str, Any]:
    exported_keys = {(check.command_id, check.segment_index) for check in exported_checks}
    return {
        "schema_version": "api_gym.ot2_motion_visualization_source.v1",
        "visibility": "researcher_only",
        "task_id": state.task.task_id,
        "generation_id": state.generation_id,
        "declared_setup": {
            "revision": declared_setup.revision,
            "configuration_digest": declared_setup.configuration_digest,
            "software_version": declared_setup.software_version,
        },
        "physical_setup": {
            "revision": physical_setup.revision,
            "physical_digest": physical_setup.physical_digest,
        },
        "initial_pose_mm": list(state.initial_pose_mm),
        "last_clear_pose_mm": list(state.last_clear_pose_mm),
        "physical_pose_resolved": state.physical_pose_resolved,
        "terminal_reason": (
            None if state.terminal_reason is None else state.terminal_reason.value
        ),
        "events": [
            _source_event(event, exported_keys=exported_keys) for event in state.events
        ],
    }


def _source_event(
    event: MotionEvent,
    *,
    exported_keys: set[tuple[str, int]],
) -> dict[str, Any]:
    path_check = event.path_check
    return {
        "command_id": event.command_id,
        "generation_id": event.generation_id,
        "native_completion": event.native_completion.value,
        "native_error_code": event.native_error_code,
        "native_completed_segments": [
            _source_segment(segment) for segment in event.native_completed_segments
        ],
        "path_check": None
        if path_check is None
        else {
            "status": path_check.status.value,
            "coverage": path_check.coverage.value,
            "earliest_intersecting_segment_index": (
                path_check.earliest_intersecting_segment_index
            ),
            "numerical_contact_tolerance_mm": path_check.numerical_contact_tolerance_mm,
            "solver": path_check.solver,
            "method": path_check.method,
            "geometry_digests": list(path_check.geometry_digests),
            "frame_digests": list(path_check.frame_digests),
            "declared_setup_revision": path_check.declared_setup_revision,
            "physical_setup_revision": path_check.physical_setup_revision,
            "segment_checks": [
                _source_check(
                    check,
                    exported=(check.command_id, check.segment_index) in exported_keys,
                )
                for check in path_check.segment_checks
            ],
        },
    }


def _source_segment(segment: SegmentRecord) -> dict[str, Any]:
    return {
        "command_id": segment.command_id,
        "segment_index": segment.segment_index,
        "start_mm": list(segment.start_mm),
        "end_mm": list(segment.end_mm),
    }


def _source_check(check: SegmentCheck, *, exported: bool) -> dict[str, Any]:
    return {
        "command_id": check.command_id,
        "segment_index": check.segment_index,
        "status": check.status.value,
        "coverage": check.coverage.value,
        "reason_code": check.reason_code,
        "intersecting_component_id": check.intersecting_component_id,
        "checked_component_ids": list(check.checked_component_ids),
        "unchecked_component_ids": list(check.unchecked_component_ids),
        "checked_piece_pairs": [list(pair) for pair in check.checked_piece_pairs],
        "geometry_digests": list(check.geometry_digests),
        "frame_digests": list(check.frame_digests),
        "exported_to_renderer": exported,
    }


def _source_digests(
    record_digest: str,
    declared_setup: DeclaredSetup,
    physical_setup: PhysicalSetup,
    events: tuple[MotionEvent, ...],
) -> list[dict[str, str]]:
    values = [
        _digest_item("visualization-source-record", record_digest),
        _digest_item("declared-setup", declared_setup.configuration_digest),
        _digest_item("physical-setup", physical_setup.physical_digest),
    ]
    tool = physical_setup.moving_tool
    if tool is not None:
        values.extend(
            (
                _digest_item("moving-geometry", tool.geometry.geometry_digest),
                _digest_item("moving-anchor-frame", tool.critical_from_geometry.digest),
            )
        )
    for component_index, component in enumerate(physical_setup.static_components, start=1):
        if component.solid is None:
            continue
        values.extend(
            (
                _digest_item(
                    f"static-geometry-{component_index:03d}",
                    component.solid.geometry.geometry_digest,
                ),
                _digest_item(
                    f"static-placement-{component_index:03d}",
                    component.solid.placement_digest,
                ),
            )
        )
    for event_index, event in enumerate(events, start=1):
        if event.path_check is None:
            continue
        for digest_index, digest in enumerate(event.path_check.geometry_digests, start=1):
            values.append(
                _digest_item(
                    f"event-{event_index:03d}-geometry-{digest_index:03d}", digest
                )
            )
        for digest_index, digest in enumerate(event.path_check.frame_digests, start=1):
            values.append(
                _digest_item(f"event-{event_index:03d}-frame-{digest_index:03d}", digest)
            )
    return values


def _digest_item(subject: str, value: str) -> dict[str, str]:
    return {"subject": subject, "algorithm": "sha256", "value": value}


def _resource(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": body["id"],
        "label": body["label"],
        "type": f"{body['provenance']['kind']}_geometry",
        "status": "ready",
        "summary": body["provenance"]["label"],
        "attributes": {
            "role": body["role"],
            "shape": body["shape"],
            "pose_mm": body["pose_mm"],
        },
    }


def _steps(
    movements: list[dict[str, Any]],
    checks: list[SegmentCheck],
    source_artifact_id: str,
) -> list[dict[str, Any]]:
    steps = []
    for movement, check in zip(movements, checks, strict=True):
        start = movement["start_mm"]
        end = movement["end_mm"]
        intersects = movement["check"]["intersects"]
        displayed_end = start if intersects else end
        steps.append(
            {
                "sequence": movement["order"],
                "phase_id": movement["case_id"],
                "operation_id": movement["id"],
                "title": (
                    f"Command {int(movement['case_id'].removeprefix('case-'))} · "
                    f"segment {movement['segment_order']}"
                ),
                "description": (
                    f"Checked planned deck-frame segment from {_point(start)} to {_point(end)}; "
                    + (
                        "the displayed body remains at the last clear pose because the physical "
                        "pose is unknown after intersection."
                        if intersects
                        else "the recorded path check is clear."
                    )
                ),
                "simulated_at": f"record-order:{movement['order']:04d}",
                "duration_ms": 900,
                "status": "completed",
                "render": {
                    "commands": [
                        {
                            "event": "show_movement",
                            "data": {"movement_id": movement["id"]},
                        }
                    ]
                },
                "scene": {
                    "kind": "process",
                    "label": "Recorded native segment",
                    "data": {
                        "actor": "Recorded OT-2 native motion",
                        "action": "Show checked path segment",
                        "source": _point(start),
                        "target": _point(end),
                        "quantity": {
                            "value": f"{dist(start, end):.6g}",
                            "unit": "mm",
                        },
                        "detail": (
                            "The renderer shows the complete intersecting segment without "
                            "guessing a contact time."
                            if intersects
                            else "The renderer shows the recorded native critical-point path."
                        ),
                    },
                },
                "facts": [
                    {
                        "label": "Path check",
                        "value": check.status.value,
                        "unit": None,
                        "tone": "danger" if intersects else "success",
                    },
                    {
                        "label": "Coverage",
                        "value": check.coverage.value,
                        "unit": None,
                        "tone": "neutral",
                    },
                ],
                "state_changes": [
                    {
                        "resource_id": movement["moving_body_id"],
                        "field": "displayed_deck_position_mm",
                        "before": _point(start),
                        "after": _point(displayed_end),
                        "unit": None,
                    }
                ],
                "artifact_ids": [source_artifact_id],
            }
        )
    return steps


def _outcome(state: EpisodeState) -> dict[str, str] | None:
    if state.terminal_reason is None:
        return None
    if state.goal_reached:
        return {
            "label": "Goal reached",
            "summary": "The trusted episode verifier recorded the independently resolved goal.",
            "tone": "success",
        }
    if state.terminal_reason.value == "path_intersection":
        return {
            "label": "Path intersection",
            "summary": (
                "The checked path intersects admitted geometry; physical pose after the "
                "intersection remains unresolved."
            ),
            "tone": "warning",
        }
    return {
        "label": state.terminal_reason.value.replace("_", " ").title(),
        "summary": "The trusted episode ended without a resolved successful motion outcome.",
        "tone": "warning",
    }


def _point(value: list[float] | tuple[float, float, float]) -> str:
    return f"({value[0]:.6g}, {value[1]:.6g}, {value[2]:.6g}) mm"


def _canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _same_native_position(
    left: tuple[float, float, float],
    right: list[float] | tuple[float, float, float],
) -> bool:
    right_tuple = (float(right[0]), float(right[1]), float(right[2]))
    tolerance = max(
        native_binary64_goal_tolerance_mm(left),
        native_binary64_goal_tolerance_mm(right_tuple),
    )
    return dist(left, right_tuple) <= tolerance


def _require_identifier(value: str, field_name: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a stable identifier")
