"""FCL queries for admitted fixed-orientation convex solids in millimeters.

The original ``Body``/``Box``/``Sphere`` surface remains the primitive query
API. Solid-level queries add unions of convex pieces without replacing a
non-convex union or cavity with one overall convex hull.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import isfinite
from typing import Literal

import fcl
import numpy as np
import trimesh

from .frames import Rotation3, RigidTransform, Vec3, vector_mm
from .solids import Box, ConvexPolyhedron, ConvexShape, PlacedSolid, Sphere

NUMERICAL_CONTACT_TOLERANCE_MM = 1e-8


@dataclass(frozen=True)
class Body:
    shape: ConvexShape
    center_mm: Vec3
    rotation: Rotation3 = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )

    def __post_init__(self) -> None:
        if type(self.shape) not in (Box, Sphere, ConvexPolyhedron):
            raise TypeError("Only boxes, spheres, and convex polyhedra are admitted")
        object.__setattr__(self, "center_mm", vector_mm(self.center_mm))
        validated = RigidTransform("body", "query", self.rotation)
        object.__setattr__(self, "rotation", validated.rotation)


@dataclass(frozen=True)
class SweepResult:
    intersects: bool
    method: Literal["exact_translational_sweep"] = "exact_translational_sweep"
    numerical_contact_tolerance_mm: float = NUMERICAL_CONTACT_TOLERANCE_MM


class CollisionComputationError(RuntimeError):
    """The query produced no admissible result; callers must not assume clear."""


class UnsupportedMotionError(ValueError):
    """The requested motion is outside the admitted collision algorithm."""


@dataclass(frozen=True)
class SolidSweepResult:
    intersects: bool
    checked_piece_pairs: tuple[tuple[str, str], ...]
    method: Literal["exact_fixed_orientation_union_sweep"] = "exact_fixed_orientation_union_sweep"
    numerical_contact_tolerance_mm: float = NUMERICAL_CONTACT_TOLERANCE_MM


def _transform(center: Vec3, rotation: Rotation3 | None = None) -> fcl.Transform:
    if rotation is None:
        return fcl.Transform(np.asarray(center, dtype=np.float64))
    return fcl.Transform(np.asarray(rotation, dtype=np.float64), np.asarray(center, dtype=np.float64))


def _convex(shape: ConvexPolyhedron) -> fcl.Convex:
    faces = np.column_stack((np.full(len(shape.faces), 3), shape.faces)).ravel()
    return fcl.Convex(np.asarray(shape.vertices_mm), len(shape.faces), faces)


def _object(body: Body) -> fcl.CollisionObject:
    if isinstance(body.shape, Box):
        shape = fcl.Box(*body.shape.dimensions_mm)
    elif isinstance(body.shape, Sphere):
        shape = fcl.Sphere(body.shape.radius_mm)
    else:
        shape = _convex(body.shape)
    return fcl.CollisionObject(shape, _transform(body.center_mm, body.rotation))


def overlaps(first: Body, second: Body) -> bool:
    """Test solid overlap/contact within the stated numerical tolerance."""
    return _within_contact_tolerance(_object(first), _object(second))


def _within_contact_tolerance(first: fcl.CollisionObject, second: fcl.CollisionObject) -> bool:
    result = fcl.DistanceResult()
    distance = float(fcl.distance(first, second, fcl.DistanceRequest(), result))
    # Unsigned FCL distance reports -1 for overlapping supported solids.
    # This is the sole contact predicate, including tangent and endpoint cases.
    if not isfinite(distance) or distance == np.finfo(float).max or distance < -1:
        raise CollisionComputationError("FCL returned an invalid solid-distance result")
    return distance <= NUMERICAL_CONTACT_TOLERANCE_MM


def _swept_object(moving: Body, destination: Vec3) -> fcl.CollisionObject:
    start = np.asarray(moving.center_mm)
    delta = np.asarray(destination) - start
    length = float(np.linalg.norm(delta))
    if not isfinite(length):
        raise ValueError("Movement exceeds finite numerical range")
    if length == 0:
        return _object(moving)
    midpoint = start + delta / 2
    if isinstance(moving.shape, Sphere):
        # The Minkowski sum of a sphere and a line segment is a capsule.
        rotation = trimesh.geometry.align_vectors((0, 0, 1), delta / length)[:3, :3]
        return fcl.CollisionObject(
            fcl.Capsule(moving.shape.radius_mm, length), fcl.Transform(rotation, midpoint),
        )
    # A translated convex body's swept volume is the convex hull of its two
    # endpoint bodies. This identity requires fixed orientation and translation.
    if isinstance(moving.shape, Box):
        vertices = np.asarray(list(product((-0.5, 0.5), repeat=3))) * moving.shape.dimensions_mm
    else:
        vertices = np.asarray(moving.shape.vertices_mm)
    oriented_vertices = vertices @ np.asarray(moving.rotation).T
    mesh = trimesh.convex.convex_hull(
        np.concatenate((oriented_vertices - delta / 2, oriented_vertices + delta / 2))
    )
    if not mesh.is_volume or not np.isfinite(mesh.vertices).all():
        raise CollisionComputationError("Unable to construct a closed convex swept volume")
    faces = np.column_stack((np.full(len(mesh.faces), 3), mesh.faces)).ravel()
    return fcl.CollisionObject(
        fcl.Convex(mesh.vertices, len(mesh.faces), faces),
        _transform(vector_mm(midpoint)),
    )


def sweep(moving: Body, destination_mm: Vec3, obstacle: Body) -> SweepResult:
    """Test the entire closed segment's swept solid, including both endpoints.

    The solid construction is exact for the admitted shapes; numerical geometry
    still uses floating-point arithmetic. This does not calculate contact time,
    forces, minimum clearance, or coverage of unmodeled instrument parts.
    """
    destination = vector_mm(destination_mm)
    return SweepResult(_within_contact_tolerance(_swept_object(moving, destination), _object(obstacle)))


def _placed_bodies(solid: PlacedSolid) -> tuple[tuple[str, Body], ...]:
    bodies = []
    for piece in solid.geometry.pieces:
        world_from_piece = solid.pose.compose(piece.pose)
        bodies.append(
            (
                piece.piece_id,
                Body(piece.shape, world_from_piece.translation_mm, world_from_piece.rotation),
            )
        )
    return tuple(bodies)


def _shape_local_bounds(body: Body) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(body.shape, Sphere):
        radius = body.shape.radius_mm
        center = np.asarray(body.center_mm)
        return center - radius, center + radius
    if isinstance(body.shape, Box):
        vertices = np.asarray(list(product((-0.5, 0.5), repeat=3))) * body.shape.dimensions_mm
    else:
        vertices = np.asarray(body.shape.vertices_mm)
    world = vertices @ np.asarray(body.rotation).T + np.asarray(body.center_mm)
    return world.min(axis=0), world.max(axis=0)


def _sweep_bounds(body: Body, destination_mm: Vec3) -> tuple[np.ndarray, np.ndarray]:
    lower, upper = _shape_local_bounds(body)
    delta = np.asarray(destination_mm) - np.asarray(body.center_mm)
    return np.minimum(lower, lower + delta), np.maximum(upper, upper + delta)


def _bounds_may_overlap(
    first: tuple[np.ndarray, np.ndarray], second: tuple[np.ndarray, np.ndarray]
) -> bool:
    tolerance = NUMERICAL_CONTACT_TOLERANCE_MM
    return bool(np.all(first[0] <= second[1] + tolerance) and np.all(second[0] <= first[1] + tolerance))


def overlaps_solids(first: PlacedSolid, second: PlacedSolid) -> bool:
    """Return whether any convex material piece overlaps or contacts another."""
    if first.pose.target_frame != second.pose.target_frame:
        raise ValueError("Solid overlap requires both placements in the same world frame")
    for _, first_body in _placed_bodies(first):
        first_bounds = _shape_local_bounds(first_body)
        for _, second_body in _placed_bodies(second):
            if not _bounds_may_overlap(first_bounds, _shape_local_bounds(second_body)):
                continue
            if overlaps(first_body, second_body):
                return True
    return False


def sweep_solids(
    moving: PlacedSolid,
    destination_pose: RigidTransform,
    obstacle: PlacedSolid,
) -> SolidSweepResult:
    """Check an exact fixed-orientation translation of two convex-solid unions."""
    if destination_pose.source_frame != moving.geometry.frame:
        raise ValueError("Destination pose must start in the moving geometry frame")
    if destination_pose.target_frame != moving.pose.target_frame:
        raise ValueError("Start and destination poses must target the same world frame")
    if obstacle.pose.target_frame != moving.pose.target_frame:
        raise ValueError("Solid sweep requires the obstacle in the moving solid's world frame")
    if moving.pose.rotation != destination_pose.rotation:
        raise UnsupportedMotionError("Rotation within a motion segment is unsupported")

    delta = np.asarray(destination_pose.translation_mm) - np.asarray(moving.pose.translation_mm)
    obstacle_bodies = _placed_bodies(obstacle)
    checked_pairs: list[tuple[str, str]] = []
    for moving_piece_id, moving_body in _placed_bodies(moving):
        destination = vector_mm(np.asarray(moving_body.center_mm) + delta)
        swept_bounds = _sweep_bounds(moving_body, destination)
        for obstacle_piece_id, obstacle_body in obstacle_bodies:
            if not _bounds_may_overlap(swept_bounds, _shape_local_bounds(obstacle_body)):
                continue
            checked_pairs.append((moving_piece_id, obstacle_piece_id))
            if sweep(moving_body, destination, obstacle_body).intersects:
                return SolidSweepResult(True, tuple(checked_pairs))
    return SolidSweepResult(False, tuple(checked_pairs))
