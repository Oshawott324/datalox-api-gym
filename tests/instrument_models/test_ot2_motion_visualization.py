from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256

import pytest

from api_gym.instrument_models.geometry.frames import RigidTransform
from api_gym.instrument_models.geometry.solids import (
    Box,
    ConvexPiece,
    PlacedSolid,
    RepresentationCoverage,
    SolidGeometry,
    Sphere,
)
from api_gym.instrument_models.opentrons_ot2_v0.configuration import (
    DeclaredLabware,
    DeclaredSetup,
    PhysicalComponent,
    PhysicalSetup,
)
from api_gym.instrument_models.opentrons_ot2_v0.dynamics import (
    NativeCompletion,
    NativeExecution,
)
from api_gym.instrument_models.opentrons_ot2_v0.motion import (
    AnchoredTool,
    NativeMotionSegment,
    critical_point_frame,
)
from api_gym.instrument_models.opentrons_ot2_v0.observations import ObservationCatalog
from api_gym.worlds.ot2_motion_v0.tasks import TASKS_BY_ID, ResolvedGoal
from api_gym.worlds.ot2_motion_v0.visualization import (
    GeometryPresentation,
    UnsupportedVisualizationExport,
    export_motion_visualization,
)
from api_gym.worlds.ot2_motion_v0.world import MotionAction, OT2MotionWorld


class _Backend:
    generation_id = "generation-visualization-test"
    valid = True

    def __init__(self, execution: NativeExecution) -> None:
        self.execution = execution

    def execute_motion(self, request: object) -> NativeExecution:
        del request
        return self.execution


def _declared() -> DeclaredSetup:
    return DeclaredSetup(
        "9.1.1",
        "p300_single_v2.1",
        "left",
        (DeclaredLabware("slot-3", "a" * 64, "3"),),
        True,
        "configuration-1",
    )


def _geometry(geometry_id: str, shape: Sphere | Box) -> SolidGeometry:
    frame = f"{geometry_id}-frame"
    return SolidGeometry(
        geometry_id,
        frame,
        (ConvexPiece(f"{geometry_id}-piece", shape, RigidTransform.identity(frame)),),
        RepresentationCoverage.EXACT,
        "b" * 64,
        "authored-fixture-v1",
    )


def _physical(*, rotated_wall: bool = False) -> PhysicalSetup:
    probe = _geometry("probe", Sphere(0.5))
    tool = AnchoredTool(
        probe,
        "TIP",
        RigidTransform(probe.frame, critical_point_frame("TIP")),
    )
    wall = _geometry("wall-geometry", Box((0.1, 2.0, 20.0)))
    rotation = (
        (0.0, -1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
    ) if rotated_wall else RigidTransform.identity("deck").rotation
    placed = PlacedSolid(
        "wall",
        wall,
        RigidTransform(wall.frame, "deck", rotation=rotation),
    )
    return PhysicalSetup((PhysicalComponent("wall", placed),), tool, "physical-1")


def _segment(
    index: int,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> NativeMotionSegment:
    return NativeMotionSegment(
        command_id="command-1",
        segment_index=index,
        native_frame="deck",
        native_critical_point="TIP",
        start_mm=start,
        end_mm=end,
        mount="left",
        configuration_revision="configuration-1",
        native_source_version="9.1.1",
    )


def _world(
    segments: tuple[NativeMotionSegment, ...],
    *,
    physical: PhysicalSetup | None = None,
) -> OT2MotionWorld[object]:
    declared = _declared()
    execution = NativeExecution(
        "command-1",
        _Backend.generation_id,
        NativeCompletion.SUCCEEDED,
        segments,
    )
    return OT2MotionWorld(
        task=TASKS_BY_ID["engineering_control_01"],
        declared_setup=declared,
        physical_setup=physical or _physical(),
        backend=_Backend(execution),
        observation_catalog=ObservationCatalog(()),
        resolved_goal=ResolvedGoal(
            goal_id="goal-1",
            native_frame="deck",
            native_critical_point="TIP",
            target_mm=(5.0, 10.0, 0.0),
            position_tolerance_mm=0.0,
            declared_setup_revision=declared.revision,
            definition_digest="c" * 64,
            resolver_source_version="9.1.1",
            resolution_digest="d" * 64,
        ),
        observable_setup_epoch="visible-epoch-1",
        initial_pose_mm=(-5.0, 0.0, 0.0),
    )


def _presentations() -> dict[str, GeometryPresentation]:
    return {
        "probe": GeometryPresentation(
            "authored",
            "Authored probe sphere",
            "Authored geometric motion fixture",
        ),
        "wall-geometry": GeometryPresentation(
            "authored",
            "Authored wall",
            "Authored geometric motion fixture",
        ),
    }


def _export(world: OT2MotionWorld[object]) -> dict[str, object]:
    return export_motion_visualization(
        run_id="ot2-motion-interactive-example",
        state=world.state,
        declared_setup=world.declared_setup,
        physical_setup=world.physical_setup,
        geometry_presentations=_presentations(),
    )


def test_interactive_world_events_export_as_digest_bound_renderer_payload() -> None:
    world = _world(
        (
            _segment(0, (-5.0, 0.0, 0.0), (-5.0, 10.0, 0.0)),
            _segment(1, (-5.0, 10.0, 0.0), (5.0, 10.0, 0.0)),
        )
    )
    world.execute_motion(MotionAction(object()))

    document = _export(world)

    payload = document["renderer"]["payload"]
    assert payload["visibility"] == "researcher_only"
    assert [body["label"] for body in payload["bodies"]] == [
        "Authored probe sphere",
        "Authored wall",
    ]
    assert all(movement["speed_mm_s"] is None for movement in payload["movements"])
    assert [movement["check"]["intersects"] for movement in payload["movements"]] == [
        False,
        False,
    ]
    source = document["artifacts"][0]["data"]
    encoded = json.dumps(source, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    assert payload["source"]["record_sha256"] == sha256(encoded.encode()).hexdigest()
    assert source["events"][0]["path_check"]["method"] == (
        "exact_fixed_orientation_union_sweep"
    )
    assert source["events"][0]["path_check"]["geometry_digests"]
    assert source["events"][0]["path_check"]["frame_digests"]
    assert document["presentation"]["agent"] is None
    assert "/Users/" not in json.dumps(document)


def test_intersection_exports_only_checked_prefix_and_keeps_body_at_last_clear_pose() -> None:
    world = _world(
        (
            _segment(0, (-5.0, 0.0, 0.0), (5.0, 0.0, 0.0)),
            _segment(1, (5.0, 0.0, 0.0), (5.0, 10.0, 0.0)),
        )
    )
    world.execute_motion(MotionAction(object()))

    document = _export(world)

    payload = document["renderer"]["payload"]
    assert len(payload["movements"]) == 1
    movement = payload["movements"][0]
    assert movement["check"]["intersects"] is True
    assert payload["bodies"][0]["pose_mm"]["position"] == movement["start_mm"]
    state_change = document["steps"][0]["state_changes"][0]
    assert state_change["before"] == state_change["after"]
    source_event = document["artifacts"][0]["data"]["events"][0]
    assert len(source_event["native_completed_segments"]) == 2
    assert len(source_event["path_check"]["segment_checks"]) == 1
    assert source_event["path_check"]["segment_checks"][0]["exported_to_renderer"] is True
    assert document["outcome"]["label"] == "Path intersection"


def test_export_rejects_rotation_instead_of_dropping_orientation() -> None:
    physical = _physical(rotated_wall=True)
    world = _world(
        (_segment(0, (-5.0, 0.0, 0.0), (5.0, 10.0, 0.0)),),
        physical=physical,
    )
    world.execute_motion(MotionAction(object()))

    with pytest.raises(UnsupportedVisualizationExport, match="unsupported rotation"):
        _export(world)


def test_export_requires_explicit_labels_for_every_admitted_geometry() -> None:
    world = _world((_segment(0, (-5.0, 0.0, 0.0), (5.0, 10.0, 0.0)),))
    world.execute_motion(MotionAction(object()))

    with pytest.raises(ValueError, match="exactly label every admitted geometry_id"):
        export_motion_visualization(
            run_id="ot2-motion-interactive-example",
            state=world.state,
            declared_setup=world.declared_setup,
            physical_setup=world.physical_setup,
            geometry_presentations={"probe": _presentations()["probe"]},
        )


def test_export_rejects_non_clear_non_intersection_checks() -> None:
    world = _world((_segment(0, (-5.0, 0.0, 0.0), (5.0, 10.0, 0.0)),))
    world.execute_motion(MotionAction(object()))
    event = world.state.events[0]
    assert event.path_check is not None
    unsupported_check = replace(
        event.path_check.segment_checks[0],
        status=event.path_check.status.__class__.UNSUPPORTED,
    )
    path_check = replace(event.path_check, segment_checks=(unsupported_check,))
    world.state = replace(world.state, events=(replace(event, path_check=path_check),))

    with pytest.raises(UnsupportedVisualizationExport, match="unsupported by renderer v1"):
        _export(world)
