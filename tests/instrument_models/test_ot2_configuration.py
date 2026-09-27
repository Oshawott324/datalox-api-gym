from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

pytest.importorskip("fcl", reason="Install probes/ot2_motion/requirements.lock")

from api_gym.instrument_models.geometry.frames import RigidTransform
from api_gym.instrument_models.geometry.solids import (
    Box,
    ConvexPiece,
    PlacedSolid,
    RepresentationCoverage,
    SolidGeometry,
    Sphere,
)
from api_gym.instrument_models.opentrons_ot2_v0.checks import (
    CheckStatus,
    CoverageStatus,
    check_native_path,
)
from api_gym.instrument_models.opentrons_ot2_v0.configuration import (
    DeclaredLabware,
    DeclaredSetup,
    PhysicalComponent,
    PhysicalSetup,
)
from api_gym.instrument_models.opentrons_ot2_v0.motion import (
    AnchoredTool,
    NativeMotionSegment,
    critical_point_frame,
    motion_for_segment,
)

DIGEST = "b" * 64


def _geometry(geometry_id, frame, shape, coverage=RepresentationCoverage.EXACT):
    piece = ConvexPiece("material", shape, RigidTransform(f"{frame}-piece", frame))
    return SolidGeometry(geometry_id, frame, (piece,), coverage, DIGEST, "fixture-v1")


def _tool(critical_point="tip_end", anchor=(0, 0, 50)):
    geometry = _geometry("tool", "tool-geometry", Sphere(0.5))
    return AnchoredTool(
        geometry,
        critical_point,
        RigidTransform(
            "tool-geometry",
            critical_point_frame(critical_point),
            translation_mm=anchor,
        ),
    )


def _component(
    component_id="wall-1",
    center=(0, 0, 0),
    coverage=RepresentationCoverage.EXACT,
):
    geometry = _geometry("wall", "wall-geometry", Box((0.01, 10, 10)), coverage)
    solid = PlacedSolid(
        component_id,
        geometry,
        RigidTransform("wall-geometry", "deck", translation_mm=center),
    )
    return PhysicalComponent(component_id, solid)


def _declared(offset=(1, -2, 0.5), revision="declared-1"):
    return DeclaredSetup(
        "9.1.1",
        "p300_single_v2.1",
        "left",
        (DeclaredLabware("plate", "c" * 64, "1", offset),),
        True,
        revision,
    )


def _segment(
    start=(-5, 0, 0),
    end=(5, 0, 0),
    index=0,
    revision="declared-1",
    critical_point="tip_end",
    motion_kind="translation",
):
    return NativeMotionSegment(
        "command-1",
        index,
        "deck",
        critical_point,
        start,
        end,
        "left",
        revision,
        "opentrons-9.1.1",
        motion_kind,
    )


def test_declared_offset_update_does_not_move_physical_setup_or_native_path():
    declared = _declared()
    physical = PhysicalSetup((_component(center=(12, 4, 3)),), _tool(), "physical-1")
    physical_digest = physical.physical_digest
    segment = _segment(start=(101, 20, 30), end=(102, 20, 30))
    original_motion = motion_for_segment(segment, physical.moving_tool)

    updated = declared.with_labware_offset("plate", (9, 8, 7), revision="declared-2")
    same_native_motion = motion_for_segment(segment, physical.moving_tool)

    assert updated.labware[0].configured_offset_mm == (9.0, 8.0, 7.0)
    assert declared.labware[0].configured_offset_mm == (1.0, -2.0, 0.5)
    assert physical.physical_digest == physical_digest
    assert physical.static_components[0].solid.pose.translation_mm == (12.0, 4.0, 3.0)
    assert same_native_motion == original_motion
    assert original_motion.start_pose.translation_mm == (101.0, 20.0, 80.0)


def test_physical_placement_update_does_not_change_declared_configuration():
    declared = _declared()
    physical = PhysicalSetup((_component(center=(12, 4, 3)),), _tool(), "physical-1")
    declared_digest = declared.configuration_digest
    moved = physical.with_component_pose(
        "wall-1",
        RigidTransform("wall-geometry", "deck", translation_mm=(15, 6, 2)),
        revision="physical-2",
    )

    assert declared.configuration_digest == declared_digest
    assert moved.static_components[0].solid.pose.translation_mm == (15.0, 6.0, 2.0)
    assert physical.static_components[0].solid.pose.translation_mm == (12.0, 4.0, 3.0)
    assert moved.physical_digest != physical.physical_digest


def test_tip_end_and_nozzle_anchors_have_independent_expected_placements():
    native_tip = _segment(start=(10, 20, 30), end=(11, 20, 30), critical_point="tip_end")
    tip_motion = motion_for_segment(native_tip, _tool("tip_end", (0, 0, 50)))
    assert tip_motion.start_pose.translation_mm == (10.0, 20.0, 80.0)

    native_nozzle = _segment(start=(10, 20, 30), end=(11, 20, 30), critical_point="nozzle")
    nozzle_motion = motion_for_segment(native_nozzle, _tool("nozzle", (0, 0, 0)))
    assert nozzle_motion.start_pose.translation_mm == (10.0, 20.0, 30.0)
    with pytest.raises(ValueError, match="different critical points"):
        motion_for_segment(native_tip, _tool("nozzle", (0, 0, 0)))


def test_exact_path_result_records_order_status_digests_and_revisions():
    segments = (
        _segment(start=(-5, 6, 0), end=(0, 6, 0), index=0),
        _segment(start=(0, 6, 0), end=(5, 6, 0), index=1),
    )
    result = check_native_path(
        segments,
        moving_tool=_tool(anchor=(0, 0, 0)),
        static_components=(_component(),),
        declared_setup_revision="declared-1",
        physical_setup_revision="physical-1",
    )

    assert result.status is CheckStatus.CLEAR
    assert result.coverage is CoverageStatus.COMPLETE_EXACT
    assert [check.segment_index for check in result.segment_checks] == [0, 1]
    assert result.declared_setup_revision == "declared-1"
    assert result.physical_setup_revision == "physical-1"
    assert result.geometry_digests and result.frame_digests
    assert result.solver.startswith("python-fcl:")


def test_exact_intersection_reports_earliest_ordered_segment():
    segments = (
        _segment(start=(-5, 0, 0), end=(-2, 0, 0), index=0),
        _segment(start=(-2, 0, 0), end=(2, 0, 0), index=1),
        _segment(start=(2, 0, 0), end=(5, 0, 0), index=2),
    )
    result = check_native_path(
        segments,
        moving_tool=_tool(anchor=(0, 0, 0)),
        static_components=(_component(),),
        declared_setup_revision="declared-1",
        physical_setup_revision="physical-1",
    )
    assert result.status is CheckStatus.INTERSECTION
    assert result.earliest_intersecting_segment_index == 1
    assert [check.status for check in result.segment_checks] == [
        CheckStatus.CLEAR,
        CheckStatus.INTERSECTION,
    ]
    assert result.segment_checks[-1].intersecting_component_id == "wall-1"


def test_enclosing_overlap_is_indeterminate_but_disjoint_enclosure_is_clear():
    enclosing = _component(coverage=RepresentationCoverage.ENCLOSING)
    overlap = check_native_path(
        (_segment(),),
        moving_tool=_tool(anchor=(0, 0, 0)),
        static_components=(enclosing,),
        declared_setup_revision="declared-1",
        physical_setup_revision="physical-1",
    )
    assert overlap.status is CheckStatus.INDETERMINATE
    assert overlap.coverage is CoverageStatus.COMPLETE_ENCLOSING
    assert overlap.segment_checks[0].reason_code == "ENCLOSING_GEOMETRY_OVERLAP"

    clear = check_native_path(
        (_segment(start=(-5, 6, 0), end=(5, 6, 0)),),
        moving_tool=_tool(anchor=(0, 0, 0)),
        static_components=(enclosing,),
        declared_setup_revision="declared-1",
        physical_setup_revision="physical-1",
    )
    assert clear.status is CheckStatus.CLEAR
    assert clear.coverage is CoverageStatus.COMPLETE_ENCLOSING


def test_pair_certainty_and_outcome_are_invariant_to_obstacle_order():
    clear_enclosure = _component(
        "enclosure",
        center=(0, 20, 0),
        coverage=RepresentationCoverage.ENCLOSING,
    )
    exact_intersection = _component("exact-wall")

    results = []
    for components in (
        (clear_enclosure, exact_intersection),
        (exact_intersection, clear_enclosure),
    ):
        results.append(
            check_native_path(
                (_segment(),),
                moving_tool=_tool(anchor=(0, 0, 0)),
                static_components=components,
                declared_setup_revision="declared-1",
                physical_setup_revision="physical-1",
            )
        )

    assert [result.status for result in results] == [
        CheckStatus.INTERSECTION,
        CheckStatus.INTERSECTION,
    ]
    assert all(result.coverage is CoverageStatus.COMPLETE_ENCLOSING for result in results)
    assert all(result.segment_checks[0].intersecting_component_id == "exact-wall" for result in results)
    assert results[1].segment_checks[0].unchecked_component_ids == ("enclosure",)


def test_missing_geometry_and_unsupported_motion_are_never_clear():
    missing = PhysicalComponent("rack", None, "No admitted rack solid")
    missing_result = check_native_path(
        (_segment(),),
        moving_tool=_tool(anchor=(0, 0, 0)),
        static_components=(missing,),
        declared_setup_revision="declared-1",
        physical_setup_revision="physical-1",
    )
    assert missing_result.status is CheckStatus.INDETERMINATE
    assert missing_result.coverage is CoverageStatus.INCOMPLETE_MISSING_GEOMETRY

    unsupported = check_native_path(
        (_segment(motion_kind="rotation"),),
        moving_tool=_tool(anchor=(0, 0, 0)),
        static_components=(_component(),),
        declared_setup_revision="declared-1",
        physical_setup_revision="physical-1",
    )
    assert unsupported.status is CheckStatus.UNSUPPORTED
    assert unsupported.coverage is CoverageStatus.UNSUPPORTED_MOTION


def test_missing_geometry_after_early_exact_contact_still_marks_total_coverage_incomplete():
    result = check_native_path(
        (_segment(),),
        moving_tool=_tool(anchor=(0, 0, 0)),
        static_components=(
            _component("exact-wall"),
            PhysicalComponent("missing-rack", None, "No admitted rack solid"),
        ),
        declared_setup_revision="declared-1",
        physical_setup_revision="physical-1",
    )
    assert result.status is CheckStatus.INTERSECTION
    assert result.coverage is CoverageStatus.INCOMPLETE_MISSING_GEOMETRY
    assert result.segment_checks[0].checked_component_ids == ("exact-wall",)
    assert result.segment_checks[0].unchecked_component_ids == ("missing-rack",)


def test_stale_configuration_and_invalid_path_order_are_explicit():
    stale = check_native_path(
        (_segment(revision="old"),),
        moving_tool=_tool(anchor=(0, 0, 0)),
        static_components=(_component(),),
        declared_setup_revision="new",
        physical_setup_revision="physical-1",
    )
    assert stale.status is CheckStatus.INDETERMINATE
    assert stale.coverage is CoverageStatus.STALE_CONFIGURATION

    with pytest.raises(ValueError, match="contiguous"):
        check_native_path(
            (_segment(index=1),),
            moving_tool=_tool(anchor=(0, 0, 0)),
            static_components=(),
            declared_setup_revision="declared-1",
            physical_setup_revision="physical-1",
        )


def test_configuration_records_are_immutable_and_validate_missing_geometry():
    declared = _declared()
    with pytest.raises(FrozenInstanceError):
        declared.revision = "changed"
    with pytest.raises(ValueError, match="missing-geometry reason"):
        PhysicalComponent("unknown", None)
    with pytest.raises(ValueError, match="cannot also be marked missing"):
        replace(_component(), missing_geometry_reason="incorrect")


def test_content_changes_require_new_revisions_but_exact_noops_may_retain_them():
    declared = _declared()
    with pytest.raises(ValueError, match="new setup revision"):
        declared.with_labware_offset("plate", (8, 9, 10), revision=declared.revision)
    assert (
        declared.with_labware_offset(
            "plate",
            declared.labware[0].configured_offset_mm,
            revision=declared.revision,
        )
        == declared
    )

    physical = PhysicalSetup((_component(center=(12, 4, 3)),), _tool(), "physical-1")
    current_pose = physical.static_components[0].solid.pose
    with pytest.raises(ValueError, match="new setup revision"):
        physical.with_component_pose("wall-1", RigidTransform("wall-geometry", "deck"), revision=physical.revision)
    assert physical.with_component_pose("wall-1", current_pose, revision=physical.revision) == physical
