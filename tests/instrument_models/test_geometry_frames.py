from __future__ import annotations

from dataclasses import FrozenInstanceError
import math

import numpy as np
import pytest

from api_gym.instrument_models.geometry.frames import RigidTransform


def _z_rotation(angle: float):
    return (
        (math.cos(angle), -math.sin(angle), 0.0),
        (math.sin(angle), math.cos(angle), 0.0),
        (0.0, 0.0, 1.0),
    )


def test_identity_inverse_and_composition_have_explicit_frames():
    local_from_part = RigidTransform("part", "local", _z_rotation(math.pi / 2), (1, 2, 3))
    deck_from_local = RigidTransform("local", "deck", translation_mm=(10, 20, 30))
    deck_from_part = deck_from_local.compose(local_from_part)

    point = (2, 0, 1)
    expected = deck_from_local.apply_point(local_from_part.apply_point(point))
    assert deck_from_part.apply_point(point) == pytest.approx(expected)
    assert deck_from_part.inverse().apply_point(expected) == pytest.approx(point)
    assert RigidTransform.identity("deck").compose(deck_from_part) == deck_from_part
    with pytest.raises(ValueError, match="Cannot compose"):
        local_from_part.compose(deck_from_local)


def test_homogeneous_constructor_and_immutable_matrix_output():
    transform = RigidTransform.from_homogeneous(
        "cad",
        "deck",
        (
            (0, -1, 0, 4),
            (1, 0, 0, 5),
            (0, 0, 1, 6),
            (0, 0, 0, 1),
        ),
    )
    assert transform.apply_point((2, 3, 7)) == pytest.approx((1, 7, 13))
    assert isinstance(transform.matrix, tuple)
    assert len(transform.digest) == 64
    with pytest.raises(FrozenInstanceError):
        transform.translation_mm = (0, 0, 0)


@pytest.mark.parametrize(
    "matrix, message",
    [
        (((1, 0), (0, 1)), "3 by 3"),
        (((2, 0, 0), (0, 1, 0), (0, 0, 1)), "orthonormal"),
        (((-1, 0, 0), (0, 1, 0), (0, 0, 1)), "determinant"),
        (((math.nan, 0, 0), (0, 1, 0), (0, 0, 1)), "finite"),
    ],
)
def test_invalid_rotation_is_rejected(matrix, message):
    with pytest.raises(ValueError, match=message):
        RigidTransform("a", "b", matrix)


def test_invalid_homogeneous_last_row_and_nonfinite_translation_are_rejected():
    with pytest.raises(ValueError, match="end with"):
        RigidTransform.from_homogeneous(
            "a",
            "b",
            ((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 1, 1)),
        )
    with pytest.raises(ValueError, match="finite"):
        RigidTransform("a", "b", translation_mm=(0, math.inf, 0))


def test_common_rigid_transform_preserves_distances_and_relative_geometry():
    points = np.asarray(((0.2, -4.0, 8.0), (7.0, 3.0, -2.0), (-1.0, 5.0, 0.5)))
    transform = RigidTransform("scene", "rotated-deck", _z_rotation(0.731), (81, -22, 9))
    transformed = np.asarray(transform.apply_points(points))
    original_distances = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    transformed_distances = np.linalg.norm(
        transformed[:, None, :] - transformed[None, :, :], axis=2
    )
    assert transformed_distances == pytest.approx(original_distances, abs=1e-12)
