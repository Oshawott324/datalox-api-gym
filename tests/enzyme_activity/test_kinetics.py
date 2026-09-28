from __future__ import annotations

import pytest

from api_gym.worlds.enzyme_activity_v0.chemistry import (
    ReactionParameters,
    advance_reaction,
    integrated_time_s,
)
from api_gym.worlds.enzyme_activity_v0.state import Mixture


PARAMETERS = ReactionParameters(kcat_per_s=0.08, km_mM=0.25)


def mixture(enzyme_mM: float) -> Mixture:
    return Mixture.pure(
        source_id="fixture",
        volume_ul=100,
        enzyme_concentration_mM=enzyme_mM,
        substrate_concentration_mM=1,
    )


def test_zero_enzyme_has_no_enzyme_dependent_reaction() -> None:
    initial = mixture(0)
    final = advance_reaction(initial, 300, PARAMETERS)
    assert final.substrate_nmol == initial.substrate_nmol
    assert final.product_nmol == 0


def test_increasing_enzyme_increases_early_product_rate() -> None:
    low = advance_reaction(mixture(0.0005), 10, PARAMETERS)
    high = advance_reaction(mixture(0.002), 10, PARAMETERS)
    assert high.product_nmol > low.product_nmol > 0


def test_integrator_matches_integrated_michaelis_menten_relation() -> None:
    initial = mixture(0.001)
    target_substrate_mM = 0.7
    elapsed = integrated_time_s(
        initial_substrate_mM=1,
        final_substrate_mM=target_substrate_mM,
        volume_ul=initial.volume_ul,
        enzyme_nmol=initial.enzyme_nmol,
        parameters=PARAMETERS,
    )
    final = advance_reaction(initial, elapsed, PARAMETERS)
    assert final.concentration_mM("substrate") == pytest.approx(
        target_substrate_mM, rel=2e-8, abs=1e-10
    )
    assert final.substrate_nmol + final.product_nmol == pytest.approx(
        initial.substrate_nmol, abs=1e-12
    )


def test_equivalent_time_partitions_agree_within_solver_tolerance() -> None:
    initial = mixture(0.001)
    one_step = advance_reaction(initial, 180, PARAMETERS)
    three_steps = initial
    for target in (60, 120, 180):
        three_steps = advance_reaction(three_steps, target, PARAMETERS)
    assert three_steps.substrate_nmol == pytest.approx(
        one_step.substrate_nmol, rel=1e-9, abs=1e-11
    )
    assert three_steps.product_nmol == pytest.approx(
        one_step.product_nmol, rel=1e-9, abs=1e-11
    )
