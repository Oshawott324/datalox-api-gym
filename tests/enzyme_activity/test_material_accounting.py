from __future__ import annotations

import pytest

from api_gym.worlds.enzyme_activity_v0.chemistry import ReactionParameters
from api_gym.worlds.enzyme_activity_v0.state import ExperimentState, Mixture


PARAMETERS = ReactionParameters(kcat_per_s=0.08, km_mM=0.25)


def test_transfer_conserves_amounts_and_lineage() -> None:
    source = Mixture.pure(
        source_id="sample-stock",
        volume_ul=100,
        enzyme_concentration_mM=0.002,
        substrate_concentration_mM=1,
    )
    state = ExperimentState(0, PARAMETERS, {"1:A1": source, "3:A1": Mixture()})
    totals_before = (
        sum(item.volume_ul for item in state.wells.values()),
        sum(item.enzyme_nmol for item in state.wells.values()),
        sum(item.substrate_nmol for item in state.wells.values()),
        sum(item.product_nmol for item in state.wells.values()),
    )
    state.transfer("1:A1", "3:A1", 25)
    totals_after = (
        sum(item.volume_ul for item in state.wells.values()),
        sum(item.enzyme_nmol for item in state.wells.values()),
        sum(item.substrate_nmol for item in state.wells.values()),
        sum(item.product_nmol for item in state.wells.values()),
    )
    assert totals_after == pytest.approx(totals_before)
    assert state.wells["3:A1"].lineage_ul == pytest.approx({"sample-stock": 25})


def test_reaction_continues_in_tip_and_diluting_spent_material_does_not_refresh_it() -> None:
    mixture = Mixture.pure(
        source_id="reaction",
        volume_ul=100,
        enzyme_concentration_mM=0.002,
        substrate_concentration_mM=1,
    )
    state = ExperimentState(0, PARAMETERS, {"1:A1": mixture})
    state.aspirate("1:A1", 50)
    state.wait(120)
    assert state.tip.product_nmol > 0
    spent_substrate = state.tip.substrate_nmol
    state.wells["3:A1"] = Mixture.pure(
        source_id="buffer", volume_ul=50, at_s=state.clock_s
    )
    state.dispense("3:A1", 50)
    diluted = state.wells["3:A1"]
    assert diluted.substrate_nmol == pytest.approx(spent_substrate)
    fresh = Mixture.pure(
        source_id="fresh-reaction",
        volume_ul=100,
        enzyme_concentration_mM=0.001,
        substrate_concentration_mM=1,
        at_s=state.clock_s,
    )
    assert diluted.substrate_nmol < fresh.substrate_nmol
    assert diluted.product_nmol > fresh.product_nmol
