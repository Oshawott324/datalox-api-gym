from __future__ import annotations

import json
import time
from pathlib import Path

from api_gym.worlds.registry import get_world_runtime
from api_gym.worlds.synergy_h1_yeast_growth_v0.admission import run_admission_checks
from api_gym.worlds.synergy_h1_yeast_growth_v0.plans import MUTANTS, NEAR_MISSES
from api_gym.worlds.synergy_h1_yeast_growth_v0.sampler import SCENARIO, sample_episode
from api_gym.worlds.synergy_h1_yeast_growth_v0.tools import dispatch_tool


PLATE_ID = "yeast_growth_plate"


def test_registry_exposes_exact_world_and_scenario() -> None:
    runtime = get_world_runtime("synergy_h1_yeast_growth_v0")
    assert runtime.world_id == "synergy-h1-yeast-growth-v0"
    assert runtime.scenarios == {"yeast_growth_20h_kinetic"}
    assert {tool["function"]["name"] for tool in runtime.tool_definitions} >= {
        "reader_read_absorbance",
        "advance_logical_time",
        "submit_growth_decision",
    }


def test_oracle_mutants_near_misses_and_sources_are_admitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        time,
        "sleep",
        lambda *_: (_ for _ in ()).throw(AssertionError("wall-clock sleep called")),
    )
    result = run_admission_checks(out_dir=tmp_path / "admission")
    assert result["ok"] is True
    assert result["sources"]["ok"] is True
    assert result["summary"]["mutants"] == 7
    assert result["summary"]["near_misses"] == 3
    assert result["summary"]["tool_calls"] == 12_743

    cases = {case["case_id"]: case for case in result["cases"]}
    assert cases["oracle"]["verifier_ok"] is True
    assert cases["empty_plan"]["verifier_ok"] is False
    for declaration in MUTANTS:
        case = cases[declaration.case_id]
        assert case["ok"] is True
        assert case["failed_check_names"] == list(declaration.expected_failure_codes)
        assert declaration.requirement in declaration.expected_failure_codes
    for declaration in NEAR_MISSES:
        assert cases[declaration.case_id]["verifier_ok"] is True


def test_stable_read_errors_and_driver_gap_caveat(tmp_path: Path) -> None:
    episode = sample_episode(scenario=SCENARIO, seed=3, out_dir=tmp_path / "run")
    close_error = dispatch_tool(episode.run_dir, name="reader_close", arguments={})
    assert close_error["error"]["code"] == "plate_not_loaded"
    assert dispatch_tool(episode.run_dir, name="reader_open", arguments={})["ok"] is True
    assert dispatch_tool(
        episode.run_dir,
        name="reader_load_plate",
        arguments={"plate_id": PLATE_ID},
    )["ok"] is True
    door_error = dispatch_tool(
        episode.run_dir,
        name="reader_read_absorbance",
        arguments={"plate_id": PLATE_ID, "wells": ["A1"], "wavelength_nm": 600},
    )
    assert door_error["error"]["code"] == "reader_door_open"
    assert dispatch_tool(episode.run_dir, name="reader_close", arguments={})["ok"] is True
    wavelength_error = dispatch_tool(
        episode.run_dir,
        name="reader_read_absorbance",
        arguments={"plate_id": PLATE_ID, "wells": ["A1"], "wavelength_nm": 100},
    )
    assert wavelength_error["error"]["code"] == "wavelength_out_of_range"

    cooling_error = dispatch_tool(
        episode.run_dir,
        name="reader_set_temperature",
        arguments={"temperature_c": 20},
    )
    assert cooling_error["error"]["code"] == "cooling_unsupported"

    package = Path(__file__).parents[1] / "api_gym/worlds/synergy_h1_yeast_growth_v0"
    readme = (package / "README.md").read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.lower().split())
    assert "559 CPM and 1 mm" in readme
    assert "setting 3 to 567 CPM" in readme
    assert "does not expose or verify exact 1 mm" in normalized_readme
    spec = json.loads((package / "spec.json").read_text(encoding="utf-8"))
    assert spec["schedule"]["observations"] == 601
    assert spec["schedule"]["source_status"] == "benchmark_defined"


def test_mutants_are_requirement_scoped() -> None:
    assert {declaration.case_id for declaration in MUTANTS} == {
        "temperature_set_without_stabilization",
        "insufficient_incubation_exposure",
        "measurement_outside_cadence_window",
        "shaking_interrupted",
        "wrong_wavelength",
        "missing_replicate",
        "decision_from_incomplete_series",
    }
    assert all(declaration.operator for declaration in MUTANTS)
    assert all(declaration.requirement for declaration in MUTANTS)
