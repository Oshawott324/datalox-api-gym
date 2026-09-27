from __future__ import annotations

from collections import Counter
import math

import numpy as np
import pytest

pytest.importorskip("fcl", reason="Install probes/ot2_motion/requirements.lock")

from api_gym.instrument_models.geometry.collision import (
    Body,
    UnsupportedMotionError,
    overlaps,
    overlaps_solids,
    sweep,
    sweep_solids,
)
from api_gym.instrument_models.geometry.frames import RigidTransform
from api_gym.instrument_models.geometry.solids import (
    Box,
    ConvexPiece,
    ConvexPolyhedron,
    PlacedSolid,
    RepresentationCoverage,
    SolidGeometry,
    Sphere,
)

SOURCE = "a" * 64


def _piece(piece_id, shape, frame, translation=(0, 0, 0)):
    return ConvexPiece(
        piece_id,
        shape,
        RigidTransform(f"{piece_id}-local", frame, translation_mm=translation),
    )


def _geometry(geometry_id, frame, pieces, coverage=RepresentationCoverage.EXACT):
    return SolidGeometry(geometry_id, frame, tuple(pieces), coverage, SOURCE, "fixture-v1")


def _placed(geometry, instance_id, translation=(0, 0, 0), rotation=None, target="deck"):
    kwargs = {"translation_mm": translation}
    if rotation is not None:
        kwargs["rotation"] = rotation
    return PlacedSolid(instance_id, geometry, RigidTransform(geometry.frame, target, **kwargs))


def test_asymmetric_convex_faces_are_watertight_outward_and_positive_volume():
    polyhedron = ConvexPolyhedron(((0, 0, 0), (2, 0, 0), (0, 3, 0), (0, 0, 5)))
    vertices = np.asarray(polyhedron.vertices_mm)
    centroid = vertices.mean(axis=0)
    edge_uses = Counter()
    signed_six_volume = 0.0

    for a, b, c in polyhedron.faces:
        triangle = vertices[[a, b, c]]
        normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
        assert np.dot(normal, centroid - triangle.mean(axis=0)) < 0
        signed_six_volume += np.dot(triangle[0], np.cross(triangle[1], triangle[2]))
        edge_uses.update(
            (tuple(sorted(edge)) for edge in ((a, b), (b, c), (c, a)))
        )

    assert set(edge_uses.values()) == {2}
    assert signed_six_volume / 6 == pytest.approx(5.0)

    tetrahedron = Body(polyhedron, (0, 0, 0))
    contained = Body(Sphere(0.05), (0.2, 0.2, 0.2))
    assert overlaps(tetrahedron, contained)
    assert overlaps(contained, tetrahedron)


@pytest.mark.parametrize(
    "vertices",
    [
        ((0, 0, 0), (1, 0, 0), (0, 1, 0)),
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)),
        ((0, 0, 0), (1, 0, 0), (0, 1, 0), (math.nan, 0, 1)),
    ],
)
def test_invalid_convex_polyhedra_are_rejected(vertices):
    with pytest.raises(ValueError):
        ConvexPolyhedron(vertices)


def test_exact_union_preserves_open_cavity_and_detects_wall_and_bottom():
    frame = "well-material"
    well = _geometry(
        "well",
        frame,
        (
            _piece("left", Box((1, 6, 4)), frame, (-2.5, 0, 2.5)),
            _piece("right", Box((1, 6, 4)), frame, (2.5, 0, 2.5)),
            _piece("front", Box((4, 1, 4)), frame, (0, -2.5, 2.5)),
            _piece("back", Box((4, 1, 4)), frame, (0, 2.5, 2.5)),
            _piece("bottom", Box((6, 6, 1)), frame, (0, 0, 0)),
        ),
    )
    tool = _geometry("probe", "probe-frame", (_piece("tip", Sphere(0.4), "probe-frame"),))
    obstacle = _placed(well, "well-1")

    entry = _placed(tool, "probe-1", (0, 0, 6))
    assert not sweep_solids(
        entry,
        RigidTransform("probe-frame", "deck", translation_mm=(0, 0, 1)),
        obstacle,
    ).intersects

    inside = _placed(tool, "probe-1", (0, 0, 1))
    assert sweep_solids(
        inside,
        RigidTransform("probe-frame", "deck", translation_mm=(2.2, 0, 1)),
        obstacle,
    ).intersects
    assert sweep_solids(
        inside,
        RigidTransform("probe-frame", "deck", translation_mm=(0, 0, 0.2)),
        obstacle,
    ).intersects


def test_thin_wall_is_detected_for_convex_piece_between_clear_endpoints():
    tetra = ConvexPolyhedron(((-0.2, -0.2, -0.2), (0.3, -0.2, -0.2), (-0.2, 0.4, -0.2), (-0.2, -0.2, 0.5)))
    tool = _geometry("tool", "tool-frame", (_piece("tetra", tetra, "tool-frame"),))
    wall = _geometry("wall", "wall-frame", (_piece("wall", Box((0.01, 10, 10)), "wall-frame"),))
    moving = _placed(tool, "tool-1", (-5, 0, 0))
    obstacle = _placed(wall, "wall-1")

    assert sweep_solids(
        moving,
        RigidTransform("tool-frame", "deck", translation_mm=(5, 0, 0)),
        obstacle,
    ).intersects


def test_initial_containment_is_detected_in_both_solid_directions():
    small_geometry = _geometry("small", "small-frame", (_piece("small", Box((1, 1, 1)), "small-frame"),))
    large_geometry = _geometry("large", "large-frame", (_piece("large", Box((10, 10, 10)), "large-frame"),))
    small = _placed(small_geometry, "small-1")
    large = _placed(large_geometry, "large-1")

    assert sweep_solids(small, small.pose, large).intersects
    assert sweep_solids(large, large.pose, small).intersects


def test_common_scene_rotation_and_translation_preserve_sweep_result():
    moving_geometry = _geometry("moving", "moving-frame", (_piece("body", Box((1, 2, 1)), "moving-frame"),))
    wall_geometry = _geometry("wall", "wall-frame", (_piece("wall", Box((0.02, 8, 8)), "wall-frame"),))
    moving = _placed(moving_geometry, "moving-1", (-4, 0, 0))
    destination = RigidTransform("moving-frame", "deck", translation_mm=(4, 0, 0))
    wall = _placed(wall_geometry, "wall-1")
    expected = sweep_solids(moving, destination, wall).intersects

    angle = 0.63
    rotation = (
        (math.cos(angle), -math.sin(angle), 0),
        (math.sin(angle), math.cos(angle), 0),
        (0, 0, 1),
    )
    transformed_from_deck = RigidTransform("deck", "rotated-deck", rotation, (30, -12, 5))
    transformed_moving = moving.with_pose(transformed_from_deck.compose(moving.pose))
    transformed_destination = transformed_from_deck.compose(destination)
    transformed_wall = wall.with_pose(transformed_from_deck.compose(wall.pose))

    assert sweep_solids(transformed_moving, transformed_destination, transformed_wall).intersects is expected


@pytest.mark.parametrize("angle", [math.pi / 2, 1e-12])
def test_rotation_within_segment_is_explicitly_unsupported(angle):
    geometry = _geometry("moving", "moving-frame", (_piece("body", Box((1, 1, 1)), "moving-frame"),))
    obstacle_geometry = _geometry("wall", "wall-frame", (_piece("wall", Box((1, 1, 1)), "wall-frame"),))
    moving = _placed(geometry, "moving-1")
    destination = RigidTransform(
        "moving-frame",
        "deck",
        (
            (math.cos(angle), -math.sin(angle), 0),
            (math.sin(angle), math.cos(angle), 0),
            (0, 0, 1),
        ),
        (1, 0, 0),
    )
    with pytest.raises(UnsupportedMotionError, match="Rotation"):
        sweep_solids(moving, destination, _placed(obstacle_geometry, "wall-1", (5, 0, 0)))


def test_solid_queries_reject_different_named_world_frames():
    first_geometry = _geometry("first", "first-frame", (_piece("first", Box((1, 1, 1)), "first-frame"),))
    second_geometry = _geometry("second", "second-frame", (_piece("second", Box((1, 1, 1)), "second-frame"),))
    first = _placed(first_geometry, "first-1", target="deck")
    second = _placed(second_geometry, "second-1", target="camera")

    with pytest.raises(ValueError, match="same world frame"):
        overlaps_solids(first, second)
    with pytest.raises(ValueError, match="obstacle"):
        sweep_solids(first, first.pose, second)


@pytest.mark.parametrize("path_y", [0.0, 20.0])
def test_broadphase_matches_exhaustive_narrowphase_for_rotated_boxes_and_thin_wall(path_y):
    def rotation(angle):
        return (
            (math.cos(angle), -math.sin(angle), 0),
            (math.sin(angle), math.cos(angle), 0),
            (0, 0, 1),
        )

    moving_frame = "moving-composite"
    moving_geometry = _geometry(
        "moving-composite",
        moving_frame,
        (
            ConvexPiece("rotated-body", Box((1.1, 2.3, 0.8)), RigidTransform("rb", moving_frame, rotation(0.37))),
            ConvexPiece(
                "offset-body",
                Box((0.4, 1.7, 0.6)),
                RigidTransform("ob", moving_frame, rotation(-0.29), (0.2, 2.8, 0.1)),
            ),
        ),
    )
    obstacle_frame = "obstacle-composite"
    obstacle_geometry = _geometry(
        "obstacle-composite",
        obstacle_frame,
        (
            ConvexPiece(
                "thin-wall",
                Box((0.01, 12, 8)),
                RigidTransform("tw", obstacle_frame, rotation(0.21)),
            ),
            ConvexPiece(
                "rotated-block",
                Box((1.5, 0.7, 1.2)),
                RigidTransform("block", obstacle_frame, rotation(-0.43), (8, -5, 0)),
            ),
        ),
    )
    moving = _placed(
        moving_geometry,
        "moving-1",
        (-5, path_y, 0),
        rotation(0.18),
    )
    destination = RigidTransform(
        moving_frame,
        "deck",
        rotation(0.18),
        (5, path_y, 0),
    )
    obstacle = _placed(obstacle_geometry, "obstacle-1", (0, 0, 0), rotation(-0.12))

    delta = np.asarray(destination.translation_mm) - np.asarray(moving.pose.translation_mm)
    exhaustive = False
    for moving_piece in moving.geometry.pieces:
        start = moving.pose.compose(moving_piece.pose)
        moving_body = Body(moving_piece.shape, start.translation_mm, start.rotation)
        end = tuple(np.asarray(start.translation_mm) + delta)
        for obstacle_piece in obstacle.geometry.pieces:
            obstacle_pose = obstacle.pose.compose(obstacle_piece.pose)
            obstacle_body = Body(
                obstacle_piece.shape,
                obstacle_pose.translation_mm,
                obstacle_pose.rotation,
            )
            exhaustive = exhaustive or sweep(moving_body, end, obstacle_body).intersects

    assert sweep_solids(moving, destination, obstacle).intersects is exhaustive
