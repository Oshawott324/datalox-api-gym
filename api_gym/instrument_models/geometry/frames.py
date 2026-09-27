"""Validated rigid transforms between named coordinate frames, in millimeters."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Iterable, Sequence

import numpy as np

Vec3 = tuple[float, float, float]
Rotation3 = tuple[Vec3, Vec3, Vec3]

_ROTATION_TOLERANCE = 1e-10
_IDENTITY_ROTATION: Rotation3 = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)


def _canonical_float(value: float) -> float:
    number = float(value)
    return 0.0 if number == 0.0 else number


def vector_mm(value: Sequence[float]) -> Vec3:
    """Return one immutable finite three-dimensional millimeter vector."""
    if len(value) != 3 or not all(isfinite(component) for component in value):
        raise ValueError("Expected three finite millimeter coordinates")
    return tuple(_canonical_float(component) for component in value)  # type: ignore[return-value]


def _frame_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Frame names must be non-empty strings")
    return value


def _rotation(value: Sequence[Sequence[float]]) -> Rotation3:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (3, 3) or not np.isfinite(array).all():
        raise ValueError("Rotation must be a finite 3 by 3 matrix")
    if not np.allclose(array.T @ array, np.eye(3), rtol=0.0, atol=_ROTATION_TOLERANCE):
        raise ValueError("Rotation must be orthonormal")
    determinant = float(np.linalg.det(array))
    if determinant <= 0 or not np.isclose(determinant, 1.0, rtol=0.0, atol=_ROTATION_TOLERANCE):
        raise ValueError("Rotation must be proper with determinant +1")
    return tuple(tuple(_canonical_float(component) for component in row) for row in array)  # type: ignore[return-value]


def _digest_values(values: Iterable[str]) -> str:
    digest = sha256()
    for value in values:
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


@dataclass(frozen=True)
class RigidTransform:
    """A proper rigid transform mapping ``source_frame`` into ``target_frame``.

    Coordinates and translations are millimeters. ``compose`` follows function
    composition: ``a.compose(b)`` applies ``b`` first, then ``a``.
    """

    source_frame: str
    target_frame: str
    rotation: Rotation3 = _IDENTITY_ROTATION
    translation_mm: Vec3 = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_frame", _frame_name(self.source_frame))
        object.__setattr__(self, "target_frame", _frame_name(self.target_frame))
        object.__setattr__(self, "rotation", _rotation(self.rotation))
        object.__setattr__(self, "translation_mm", vector_mm(self.translation_mm))

    @classmethod
    def identity(cls, frame: str) -> RigidTransform:
        return cls(frame, frame)

    @classmethod
    def from_homogeneous(
        cls,
        source_frame: str,
        target_frame: str,
        matrix: Sequence[Sequence[float]],
    ) -> RigidTransform:
        array = np.asarray(matrix, dtype=np.float64)
        if array.shape != (4, 4) or not np.isfinite(array).all():
            raise ValueError("Homogeneous transform must be a finite 4 by 4 matrix")
        if not np.allclose(array[3], (0.0, 0.0, 0.0, 1.0), rtol=0.0, atol=_ROTATION_TOLERANCE):
            raise ValueError("Homogeneous transform must end with [0, 0, 0, 1]")
        return cls(source_frame, target_frame, array[:3, :3], array[:3, 3])

    @property
    def matrix(self) -> tuple[tuple[float, float, float, float], ...]:
        rotation = self.rotation
        translation = self.translation_mm
        return (
            (*rotation[0], translation[0]),
            (*rotation[1], translation[1]),
            (*rotation[2], translation[2]),
            (0.0, 0.0, 0.0, 1.0),
        )

    @property
    def digest(self) -> str:
        return _digest_values(
            (
                "rigid-transform-v1",
                self.source_frame,
                self.target_frame,
                *(component.hex() for row in self.rotation for component in row),
                *(component.hex() for component in self.translation_mm),
            )
        )

    def apply_point(self, point_mm: Sequence[float]) -> Vec3:
        point = np.asarray(vector_mm(point_mm), dtype=np.float64)
        transformed = np.asarray(self.rotation) @ point + np.asarray(self.translation_mm)
        return vector_mm(transformed)

    def apply_points(self, points_mm: Iterable[Sequence[float]]) -> tuple[Vec3, ...]:
        return tuple(self.apply_point(point) for point in points_mm)

    def compose(self, other: RigidTransform) -> RigidTransform:
        if other.target_frame != self.source_frame:
            raise ValueError(
                f"Cannot compose {other.source_frame}->{other.target_frame} with "
                f"{self.source_frame}->{self.target_frame}"
            )
        first = np.asarray(self.rotation)
        second = np.asarray(other.rotation)
        rotation = first @ second
        translation = first @ np.asarray(other.translation_mm) + np.asarray(self.translation_mm)
        return RigidTransform(other.source_frame, self.target_frame, rotation, translation)

    def inverse(self) -> RigidTransform:
        rotation = np.asarray(self.rotation).T
        translation = -(rotation @ np.asarray(self.translation_mm))
        return RigidTransform(self.target_frame, self.source_frame, rotation, translation)
