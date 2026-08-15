from __future__ import annotations

from pathlib import Path

import pytest

from api_gym.worlds.pylabrobot_science_v0.contracts import (
    INCUBATOR_SCENARIO,
    POWDER_SCENARIO,
    THERMOCYCLER_SCENARIO,
)
from api_gym.worlds.pylabrobot_science_v0.plans import ORACLE_PLANS, run_plan
from api_gym.worlds.pylabrobot_science_v0.sampler import SCENARIOS, sample_episode
from api_gym.worlds.pylabrobot_science_v0.tools import HANDLERS, TOOL_DEFINITIONS, dispatch_tool
from api_gym.worlds.pylabrobot_science_v0.verifier import verify_run
from api_gym.worlds.pylabrobot_science_v0.visualization import export_science_visualization
from api_gym.worlds.registry import get_world_runtime


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_science_workflow_oracles_pass(tmp_path: Path, scenario: str) -> None:
    episode = sample_episode(scenario=scenario, seed=1, out_dir=tmp_path / scenario)
    results = run_plan(episode.run_dir, ORACLE_PLANS[scenario])

    assert results
    assert all(item["result"]["ok"] for item in results)
    assert verify_run(episode.run_dir).ok is True


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_empty_science_workflow_fails(tmp_path: Path, scenario: str) -> None:
    episode = sample_episode(scenario=scenario, seed=1, out_dir=tmp_path / scenario)

    result = verify_run(episode.run_dir)

    assert result.ok is False
    assert any(not check["ok"] for check in result.checks)


def test_thermocycler_enforces_lid_and_completion(tmp_path: Path) -> None:
    episode = sample_episode(
        scenario=THERMOCYCLER_SCENARIO,
        seed=1,
        out_dir=tmp_path / "thermocycler",
    )

    start = dispatch_tool(episode.run_dir, name="thermocycler_start_protocol", arguments={})
    read = dispatch_tool(episode.run_dir, name="qpcr_read_amplification", arguments={})

    assert start["ok"] is False
    assert start["error"]["code"] == "operation_rejected"
    assert read["ok"] is False
    assert read["error"]["code"] == "protocol_incomplete"


def test_incubator_counts_only_conditioned_stored_exposure(tmp_path: Path) -> None:
    episode = sample_episode(
        scenario=INCUBATOR_SCENARIO,
        seed=1,
        out_dir=tmp_path / "incubator",
    )
    dispatch_tool(
        episode.run_dir,
        name="incubator_set_temperature",
        arguments={"temperature_c": 30.0},
    )
    dispatch_tool(
        episode.run_dir,
        name="incubator_start_shaking",
        arguments={"rpm": 250.0},
    )

    unstored = dispatch_tool(
        episode.run_dir,
        name="incubator_advance_time",
        arguments={"seconds": 7200.0},
    )
    dispatch_tool(
        episode.run_dir,
        name="incubator_store_plate",
        arguments={"slot": "S04"},
    )
    stored = dispatch_tool(
        episode.run_dir,
        name="incubator_advance_time",
        arguments={"seconds": 7200.0},
    )

    assert unstored["data"]["conditioned_exposure_s"] == 0.0
    assert stored["data"]["conditioned_exposure_s"] == 7200.0
    blocked_read = dispatch_tool(episode.run_dir, name="reader_measure_od600", arguments={})
    assert blocked_read["ok"] is False
    assert blocked_read["error"]["code"] == "plate_not_at_reader"


def test_powder_workflow_requires_tare_and_station_custody(tmp_path: Path) -> None:
    episode = sample_episode(
        scenario=POWDER_SCENARIO,
        seed=1,
        out_dir=tmp_path / "powder",
    )

    wrong_station = dispatch_tool(
        episode.run_dir,
        name="powder_dispense_pulse",
        arguments={"amount_mg": 10.0},
    )
    dispatch_tool(
        episode.run_dir,
        name="formulation_move_vial",
        arguments={"destination": "powder_dispenser"},
    )
    not_tared = dispatch_tool(
        episode.run_dir,
        name="powder_dispense_pulse",
        arguments={"amount_mg": 10.0},
    )

    assert wrong_station["error"]["code"] == "vial_not_at_dispenser"
    assert not_tared["error"]["code"] == "balance_not_tared"


def test_world_registry_exposes_science_workflows() -> None:
    runtime = get_world_runtime("pylabrobot_science_v0")

    assert runtime.world_id == "pylabrobot-science-v0"
    assert runtime.scenarios == set(SCENARIOS)
    assert {item["function"]["name"] for item in runtime.tool_definitions} >= {
        "thermocycler_start_protocol",
        "incubator_advance_time",
        "powder_dispense_pulse",
    }
    assert {item["function"]["name"] for item in TOOL_DEFINITIONS} == set(HANDLERS)


@pytest.mark.parametrize(
    ("scenario", "variant"),
    [
        (THERMOCYCLER_SCENARIO, "thermocycler"),
        (INCUBATOR_SCENARIO, "incubator_shaker"),
        (POWDER_SCENARIO, "powder_balance"),
    ],
)
def test_science_visualizations_are_portable_and_instrument_specific(
    tmp_path: Path,
    scenario: str,
    variant: str,
) -> None:
    destination = tmp_path / f"{scenario}.json"

    document = export_science_visualization(scenario=scenario, destination=destination)

    assert destination.exists()
    assert document["steps"][0]["scene"]["kind"] == "instrument"
    assert document["steps"][0]["scene"]["data"]["variant"] == variant
    assert document["steps"][-1]["scene"]["kind"] == "evidence"
    artifact_ids = {artifact["id"] for artifact in document["artifacts"]}
    assert all(
        set(step["artifact_ids"]).issubset(artifact_ids)
        for step in document["steps"]
    )
    assert "/Users/" not in destination.read_text(encoding="utf-8")
    if scenario == INCUBATOR_SCENARIO:
        assert len(document["steps"][0]["scene"]["data"]["od600"]["points"]) == 1
    if scenario == POWDER_SCENARIO:
        assert document["steps"][0]["scene"]["data"]["dosing_pulses"] == []
