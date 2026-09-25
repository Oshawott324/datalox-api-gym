"""FCL queries for fixed-orientation boxes and spheres in millimeters.

This is the Phase 0 admitted mathematical scope, not a full instrument checker.
Shapes describe solid occupied space. Meshes, rotations during movement, shape
uncertainty, and contact response require separate admission before use here.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import isfinite
from typing import Literal

import fcl
import numpy as np
import trimesh

Vec3 = tuple[float, float, float]
NUMERICAL_CONTACT_TOLERANCE_MM = 1e-8


def _vector(value: Vec3) -> Vec3:
    if len(value) != 3 or not all(isfinite(x) for x in value):
        raise ValueError("Expected three finite millimeter coordinates")
    return tuple(float(x) for x in value)


@dataclass(frozen=True)
class Box:
    dimensions_mm: Vec3

    def __post_init__(self) -> None:
        dimensions = _vector(self.dimensions_mm)
        if min(dimensions) <= 0:
            raise ValueError("Box dimensions must be positive")
        object.__setattr__(self, "dimensions_mm", dimensions)


@dataclass(frozen=True)
class Sphere:
    radius_mm: float

    def __post_init__(self) -> None:
        if not isfinite(self.radius_mm) or self.radius_mm <= 0:
            raise ValueError("Sphere radius must be finite and positive")


@dataclass(frozen=True)
class Body:
    shape: Box | Sphere
    center_mm: Vec3

    def __post_init__(self) -> None:
        if type(self.shape) not in (Box, Sphere):
            raise TypeError("Only boxes and spheres are admitted")
        object.__setattr__(self, "center_mm", _vector(self.center_mm))


@dataclass(frozen=True)
class SweepResult:
    intersects: bool
    method: Literal["exact_translational_sweep"] = "exact_translational_sweep"
    numerical_contact_tolerance_mm: float = NUMERICAL_CONTACT_TOLERANCE_MM


class CollisionComputationError(RuntimeError):
    """The query produced no admissible result; callers must not assume clear."""


def _transform(center: Vec3) -> fcl.Transform:
    return fcl.Transform(np.asarray(center, dtype=np.float64))


def _object(body: Body) -> fcl.CollisionObject:
    if isinstance(body.shape, Box):
        shape = fcl.Box(*body.shape.dimensions_mm)
    else:
        shape = fcl.Sphere(body.shape.radius_mm)
    return fcl.CollisionObject(shape, _transform(body.center_mm))


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
    corners = np.asarray(list(product((-0.5, 0.5), repeat=3))) * moving.shape.dimensions_mm
    mesh = trimesh.convex.convex_hull(np.concatenate((corners - delta / 2, corners + delta / 2)))
    if not mesh.is_volume or not np.isfinite(mesh.vertices).all():
        raise CollisionComputationError("Unable to construct a closed convex swept volume")
    faces = np.column_stack((np.full(len(mesh.faces), 3), mesh.faces)).ravel()
    return fcl.CollisionObject(fcl.Convex(mesh.vertices, len(mesh.faces), faces), _transform(tuple(midpoint)))


def sweep(moving: Body, destination_mm: Vec3, obstacle: Body) -> SweepResult:
    """Test the entire closed segment's swept solid, including both endpoints.

    The solid construction is exact for the admitted shapes; numerical geometry
    still uses floating-point arithmetic. This does not calculate contact time,
    forces, minimum clearance, or coverage of unmodeled instrument parts.
    """
    destination = _vector(destination_mm)
    return SweepResult(_within_contact_tolerance(_swept_object(moving, destination), _object(obstacle)))
