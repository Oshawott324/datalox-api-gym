from __future__ import annotations

import math
import random

import pytest

pytest.importorskip("fcl", reason="Install probes/ot2_motion/requirements.lock")

from api_gym.instrument_models.geometry.collision import Body, Box, CollisionComputationError, Sphere, overlaps, sweep


@pytest.mark.parametrize("shape", [Sphere(0.5), Box((1, 1, 1))])
def test_thin_obstacle_between_clear_endpoints(shape):
    moving = Body(shape, (-5, 0, 0))
    wall = Body(Box((0.01, 10, 10)), (0, 0, 0))
    assert not overlaps(moving, wall)
    assert not overlaps(Body(shape, (5, 0, 0)), wall)
    result = sweep(moving, (5, 0, 0), wall)
    assert result.intersects
    assert result.method == "exact_translational_sweep"


@pytest.mark.parametrize("shape", [Sphere(0.5), Box((1, 1, 1))])
def test_clear_parallel_path(shape):
    assert not sweep(Body(shape, (-5, 6, 0)), (5, 6, 0), Body(Box((0.01, 10, 10)), (0, 0, 0))).intersects


def test_containment_and_stationary_overlap():
    result = sweep(Body(Sphere(0.5), (0, 0, 0)), (0, 0, 0), Body(Box((10, 10, 10)), (0, 0, 0)))
    assert result.intersects


def test_stationary_clear():
    assert not sweep(Body(Sphere(0.5), (10, 0, 0)), (10, 0, 0), Body(Box((1, 1, 1)), (0, 0, 0))).intersects


def test_contact_at_end_of_segment():
    result = sweep(Body(Box((1, 1, 1)), (-2, 0, 0)), (-1, 0, 0), Body(Box((1, 1, 1)), (0, 0, 0)))
    assert result.intersects


def test_translation_invariance_and_segment_subdivision():
    wall = Body(Box((0.01, 10, 10)), (0, 0, 0))
    whole = sweep(Body(Sphere(0.5), (-5, 0, 0)), (5, 0, 0), wall)
    translated = sweep(Body(Sphere(0.5), (95, 20, 30)), (105, 20, 30), Body(wall.shape, (100, 20, 30)))
    first_half = sweep(Body(Sphere(0.5), (-5, 0, 0)), (0, 0, 0), wall)
    assert translated.intersects and whole.intersects and first_half.intersects


@pytest.mark.parametrize("y, expected", [(0, True), (1, True), (1.000001, False)])
def test_head_on_and_grazing_contact(y, expected):
    assert sweep(Body(Box((1, 1, 1)), (-5, y, 0)), (5, y, 0), Body(Box((1, 1, 1)), (0, 0, 0))).intersects is expected


def test_open_cavity_is_not_a_solid_bounding_box():
    walls = [Body(Box((1, 10, 10)), (x, 0, 0)) for x in (-3, 3)]
    assert all(not sweep(Body(Sphere(0.5), (0, 0, 10)), (0, 0, -10), wall).intersects for wall in walls)
    assert sweep(Body(Sphere(0.5), (0, 0, 10)), (3, 0, 0), walls[1]).intersects


@pytest.mark.parametrize("value", [(0, 1, 1), (-1, 1, 1), (math.nan, 1, 1), (math.inf, 1, 1), (1, 2)])
def test_invalid_dimensions(value):
    with pytest.raises(ValueError):
        Box(value)


def test_invalid_path_and_unsupported_shape():
    with pytest.raises(ValueError):
        sweep(Body(Sphere(1), (0, 0, 0)), (math.nan, 0, 0), Body(Sphere(1), (5, 0, 0)))
    with pytest.raises(TypeError):
        Body(object(), (0, 0, 0))


def _analytical_box_sweep(start, end, dimensions, obstacle_center, obstacle_dimensions):
    """Independent slab intersection of the center segment with a Minkowski box."""
    lower_fraction, upper_fraction = 0.0, 1.0
    for a, b, size, center, other_size in zip(start, end, dimensions, obstacle_center, obstacle_dimensions):
        half_extent = (size + other_size) / 2
        low, high = center - half_extent, center + half_extent
        if a == b:
            if not low <= a <= high:
                return False
        else:
            entering, leaving = sorted(((low-a)/(b-a), (high-a)/(b-a)))
            lower_fraction = max(lower_fraction, entering)
            upper_fraction = min(upper_fraction, leaving)
    return lower_fraction <= upper_fraction


def test_random_box_sweeps_against_independent_analytical_oracle():
    rng = random.Random(4127)
    for _ in range(200):
        start = tuple(rng.uniform(-10, 10) for _ in range(3))
        end = tuple(rng.uniform(-10, 10) for _ in range(3))
        center = tuple(rng.uniform(-5, 5) for _ in range(3))
        dimensions = tuple(rng.uniform(0.1, 6) for _ in range(3))
        other = tuple(rng.uniform(0.1, 6) for _ in range(3))
        expected = _analytical_box_sweep(start, end, dimensions, center, other)
        obstacle = Body(Box(other), center)
        assert sweep(Body(Box(dimensions), start), end, obstacle).intersects == expected
        assert sweep(Body(Box(dimensions), end), start, obstacle).intersects == expected


def test_random_sphere_sweeps_against_analytical_closest_point():
    import numpy as np
    rng = random.Random(312)
    for _ in range(100):
        start = np.array([rng.uniform(-10, 10) for _ in range(3)])
        end = np.array([rng.uniform(-10, 10) for _ in range(3)])
        radius, other_radius = rng.uniform(0.1, 3), rng.uniform(0.1, 3)
        delta = end - start
        fraction = float(np.clip(-start.dot(delta) / delta.dot(delta), 0, 1))
        expected = np.linalg.norm(start + fraction * delta) <= radius + other_radius
        actual = sweep(Body(Sphere(radius), tuple(start)), tuple(end), Body(Sphere(other_radius), (0, 0, 0)))
        assert actual.intersects == expected


def test_invalid_solver_result_is_not_clear(monkeypatch):
    import fcl
    monkeypatch.setattr(fcl, "distance", lambda *args: math.nan)
    with pytest.raises(CollisionComputationError):
        sweep(Body(Sphere(1), (0, 0, 0)), (10, 0, 0), Body(Sphere(1), (20, 0, 0)))


@pytest.mark.parametrize("shape", [Sphere(0.5), Box((1, 1, 1))])
def test_endpoint_and_grazing_are_closed_contact(shape):
    obstacle = Body(Box((1, 1, 1)), (0, 0, 0))
    assert sweep(Body(shape, (-2, 0, 0)), (-1, 0, 0), obstacle).intersects
    assert sweep(Body(shape, (-5, 1, 0)), (5, 1, 0), obstacle).intersects
    assert not sweep(Body(shape, (-5, 1.000001, 0)), (5, 1.000001, 0), obstacle).intersects
