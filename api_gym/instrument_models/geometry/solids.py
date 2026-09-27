"""Immutable solid geometry admitted for exact fixed-orientation queries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from math import isfinite
from string import hexdigits
from typing import Iterable, Sequence, TypeAlias

import numpy as np
from scipy.spatial import ConvexHull, QhullError

from .frames import RigidTransform, Vec3, vector_mm


class RepresentationCoverage(str, Enum):
    """Relationship between represented material and the modeled object."""

    EXACT = "exact"
    ENCLOSING = "enclosing"


@dataclass(frozen=True)
class Box:
    dimensions_mm: Vec3

    def __post_init__(self) -> None:
        dimensions = vector_mm(self.dimensions_mm)
        if min(dimensions) <= 0:
            raise ValueError("Box dimensions must be positive")
        object.__setattr__(self, "dimensions_mm", dimensions)


@dataclass(frozen=True)
class Sphere:
    radius_mm: float

    def __post_init__(self) -> None:
        if not isfinite(self.radius_mm) or self.radius_mm <= 0:
            raise ValueError("Sphere radius must be finite and positive")
        object.__setattr__(self, "radius_mm", float(self.radius_mm))


@dataclass(frozen=True)
class ConvexPolyhedron:
    """A closed convex solid defined by the hull of finite input vertices."""

    vertices_mm: tuple[Vec3, ...]
    faces: tuple[tuple[int, int, int], ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        vertices = tuple(sorted(set(vector_mm(vertex) for vertex in self.vertices_mm)))
        if len(vertices) < 4:
            raise ValueError("A convex polyhedron needs at least four distinct vertices")
        try:
            hull = ConvexHull(np.asarray(vertices, dtype=np.float64))
        except QhullError as error:
            raise ValueError("Convex polyhedron vertices must span a finite volume") from error
        if not isfinite(float(hull.volume)) or hull.volume <= 0:
            raise ValueError("Convex polyhedron vertices must span a finite volume")
        hull_vertices = tuple(vertices[index] for index in sorted(hull.vertices))
        remap = {vertex: index for index, vertex in enumerate(hull_vertices)}
        faces = []
        for simplex, equation in zip(hull.simplices, hull.equations, strict=True):
            face = tuple(remap[vertices[index]] for index in simplex)
            points = np.asarray([hull_vertices[index] for index in face])
            normal = np.cross(points[1] - points[0], points[2] - points[0])
            if float(np.dot(normal, equation[:3])) < 0:
                face = (face[0], face[2], face[1])
            start = face.index(min(face))
            faces.append(face[start:] + face[:start])
        object.__setattr__(self, "vertices_mm", hull_vertices)
        object.__setattr__(self, "faces", tuple(sorted(faces)))


ConvexShape: TypeAlias = Box | Sphere | ConvexPolyhedron


def _name(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _source_digest(value: str) -> str:
    if len(value) != 64 or any(character not in hexdigits for character in value):
        raise ValueError("source_digest must be a 64-character hexadecimal digest")
    return value.lower()


def _hash(parts: Iterable[str]) -> str:
    result = sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        result.update(len(encoded).to_bytes(8, "big"))
        result.update(encoded)
    return result.hexdigest()


def _shape_values(shape: ConvexShape) -> tuple[str, ...]:
    if isinstance(shape, Box):
        return ("box", *(component.hex() for component in shape.dimensions_mm))
    if isinstance(shape, Sphere):
        return ("sphere", shape.radius_mm.hex())
    return ("convex-polyhedron", *(component.hex() for vertex in shape.vertices_mm for component in vertex))


@dataclass(frozen=True)
class ConvexPiece:
    """One convex material piece positioned in a solid geometry frame."""

    piece_id: str
    shape: ConvexShape
    pose: RigidTransform

    def __post_init__(self) -> None:
        object.__setattr__(self, "piece_id", _name(self.piece_id, "piece_id"))
        if type(self.shape) not in (Box, Sphere, ConvexPolyhedron):
            raise TypeError("Convex pieces support boxes, spheres, and convex polyhedra")
        if not isinstance(self.pose, RigidTransform):
            raise TypeError("Convex piece pose must be a RigidTransform")


@dataclass(frozen=True)
class SolidGeometry:
    """Material represented as the union of convex pieces.

    Cavities remain empty because the union contains only declared material;
    this class never replaces the union with its overall convex hull.
    """

    geometry_id: str
    frame: str
    pieces: tuple[ConvexPiece, ...]
    coverage: RepresentationCoverage
    source_digest: str
    representation_revision: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "geometry_id", _name(self.geometry_id, "geometry_id"))
        object.__setattr__(self, "frame", _name(self.frame, "frame"))
        pieces = tuple(self.pieces)
        if not pieces:
            raise ValueError("Solid geometry must contain at least one convex piece")
        if not all(isinstance(piece, ConvexPiece) for piece in pieces):
            raise TypeError("Solid geometry pieces must be ConvexPiece records")
        if len({piece.piece_id for piece in pieces}) != len(pieces):
            raise ValueError("Convex piece IDs must be unique within a solid")
        if any(piece.pose.target_frame != self.frame for piece in pieces):
            raise ValueError("Every convex piece pose must target the solid geometry frame")
        if not isinstance(self.coverage, RepresentationCoverage):
            raise TypeError("coverage must be a RepresentationCoverage")
        object.__setattr__(self, "pieces", tuple(sorted(pieces, key=lambda piece: piece.piece_id)))
        object.__setattr__(self, "source_digest", _source_digest(self.source_digest))
        object.__setattr__(
            self,
            "representation_revision",
            _name(self.representation_revision, "representation_revision"),
        )

    @property
    def geometry_digest(self) -> str:
        values: list[str] = [
            "union-of-convex-solids-v1",
            self.geometry_id,
            self.frame,
            self.coverage.value,
            self.source_digest,
            self.representation_revision,
        ]
        for piece in self.pieces:
            values.extend((piece.piece_id, *_shape_values(piece.shape), piece.pose.digest))
        return _hash(values)


@dataclass(frozen=True)
class PlacedSolid:
    """A solid geometry instance with a separate rigid world placement."""

    instance_id: str
    geometry: SolidGeometry
    pose: RigidTransform

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", _name(self.instance_id, "instance_id"))
        if not isinstance(self.geometry, SolidGeometry):
            raise TypeError("Placed solid geometry must be a SolidGeometry")
        if not isinstance(self.pose, RigidTransform):
            raise TypeError("Placed solid pose must be a RigidTransform")
        if self.pose.source_frame != self.geometry.frame:
            raise ValueError("Placed-solid pose must start in the solid geometry frame")

    @property
    def placement_digest(self) -> str:
        return _hash(("placed-solid-v1", self.instance_id, self.geometry.geometry_digest, self.pose.digest))

    def with_pose(self, pose: RigidTransform) -> PlacedSolid:
        return PlacedSolid(self.instance_id, self.geometry, pose)
