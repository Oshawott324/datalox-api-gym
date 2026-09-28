from __future__ import annotations

import json
from pathlib import Path

from api_gym.worlds.enzyme_activity_v0.defaults import (
    MAX_ASSAY_PLATES,
    MAX_LOGICAL_TIME_S,
    MAX_PLATE_TRANSFERS,
)
from api_gym.worlds.enzyme_activity_v0.scenarios import SCENARIOS
from api_gym.worlds.enzyme_activity_v0.tasks import task_for_scenario


ROOT = Path(__file__).parents[2]


def test_six_frozen_scenario_families_have_unique_ids_and_seeds() -> None:
    assert [scenario.family for scenario in SCENARIOS] == [
        "nominal_measurement",
        "high_activity_unsuitable_range",
        "delayed_acquisition",
        "interrupted_series",
        "reagent_background",
        "sample_plate_lineage",
    ]
    assert len({scenario.scenario_id for scenario in SCENARIOS}) == 6
    assert len({scenario.seed for scenario in SCENARIOS}) == 6


def test_agent_tasks_state_every_requirement_used_by_verifier() -> None:
    sop = json.loads(
        (ROOT / "worlds/enzyme_activity_v0/contracts/assay_sop.json").read_text()
    )
    assert sop["controls"]["reference_control"] == "REF-AP coded reference stock"
    assert "ordinary least-squares" in sop["fit"]["method"]
    assert "combine them in quadrature" in sop["fit"]["uncertainty_rule"]
    assert "preparation-lineage dilution factor" in sop["fit"]["rate_rule"]
    for scenario in SCENARIOS:
        task = task_for_scenario(scenario)
        visible = " ".join((task.instructions, *task.success_criteria))
        for requirement in (
            "BLANK",
            "REF-AP",
            "same plate revision",
            "four acquired numeric observations",
            "90 seconds",
            "ordinary least squares",
            "standard errors in quadrature",
            "dilution factor",
            "delta_absorbance_per_minute",
            "0.01 through 0.08",
            "relative standard error no greater than 0.25",
            "1 assay plate",
            "1 operator transfer",
            "900 logical seconds",
            "missing or overrange",
        ):
            assert requirement in visible
        assert task.public_resources["assay_plates"] == MAX_ASSAY_PLATES
        assert task.public_resources["maximum_logical_time_s"] == MAX_LOGICAL_TIME_S
        assert task.public_resources["plate_transfers"] == MAX_PLATE_TRANSFERS


def test_private_scenario_truth_is_not_rendered_into_agent_task() -> None:
    for scenario in SCENARIOS:
        task = task_for_scenario(scenario)
        visible = json.dumps(task.__dict__, sort_keys=True)
        for hidden_value in scenario.private_initial_conditions.values():
            assert str(hidden_value) not in visible
        for key in scenario.private_events:
            assert key not in visible


def test_fixture_catalog_matches_frozen_scenarios_and_expected_mutant_codes() -> None:
    fixture = json.loads(
        (ROOT / "tests/enzyme_activity/fixtures/phase3_scenarios.json").read_text()
    )
    fixture_by_id = {item["scenario_id"]: item for item in fixture["scenarios"]}
    assert set(fixture_by_id) == {scenario.scenario_id for scenario in SCENARIOS}
    for scenario in SCENARIOS:
        item = fixture_by_id[scenario.scenario_id]
        assert item["family"] == scenario.family
        assert item["expected_failure_code"] == scenario.expected_mutant_failure_code


def test_world_episodes_are_exactly_the_frozen_scenario_catalog() -> None:
    episodes = [
        json.loads(line)
        for line in (ROOT / "worlds/enzyme_activity_v0/world/episodes.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [(item["id"], item["seed"]) for item in episodes] == [
        (scenario.scenario_id, scenario.seed) for scenario in SCENARIOS
    ]
