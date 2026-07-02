from __future__ import annotations

import json
from pathlib import Path

import pytest

from api_gym.worlds.adaptyv_foundry_dryrun_v0.admission import (
    REQUIRED_CHECK_NAMES,
    run_admission,
    validate_existing_run,
)
from api_gym.worlds.registry import get_world_runtime


WORLD = "adaptyv_foundry_dryrun_v0"
SCENARIO_FAILURE_CODES = {
    "budget_cap_quote_reject": "QUOTE_OVER_BUDGET_CONFIRMED",
    "expired_quote_not_confirmed": "EXPIRED_QUOTE_CONFIRMED",
    "partial_results_not_final": "FINAL_DECISION_USED_PARTIAL_RESULT",
    "stale_prior_campaign_result": "STALE_RESULT_USED_FOR_CURRENT_DECISION",
    "duplicate_submission_guard": "DUPLICATE_PAID_SUBMISSION",
    "measured_result_supported_decision": "DECISION_UNSUPPORTED_BY_MEASURED_RESULT",
}
AGENT_VISIBLE_FORBIDDEN_HIDDEN_TOKENS = {
    "hidden/",
    "result_arrival_schedule.json",
    "quote_schedule.json",
    "fault_schedule.json",
    "measured_result_replay.json",
    "oracle_plan.json",
    "known_bad_plans.json",
    "verifier_expectations.json",
}


@pytest.mark.parametrize("scenario", sorted(SCENARIO_FAILURE_CODES))
def test_adaptyv_admission_admits_all_scenarios(tmp_path: Path, scenario: str) -> None:
    payload = run_admission(scenario=scenario, seed=71, out_dir=tmp_path / scenario)

    assert payload["schema_version"] == "api_gym.admission.adaptyv_foundry_dryrun_v0.v0"
    assert payload["world"] == WORLD
    assert payload["scenario"] == scenario
    assert payload["seed"] == 71
    assert payload["admitted"] is True
    assert payload["oracle_result"]["ok"] is True
    assert payload["run_export_path"] == str((tmp_path / scenario / "run_export.json").resolve())
    assert Path(payload["run_export_path"]).is_file()
    assert _read_json(tmp_path / scenario / "admission.json") == payload
    assert {check["name"] for check in payload["checks"]} == set(REQUIRED_CHECK_NAMES)
    assert all(check["ok"] is True for check in payload["checks"])


@pytest.mark.parametrize("scenario, expected_code", sorted(SCENARIO_FAILURE_CODES.items()))
def test_adaptyv_admission_known_bad_codes_match_expectations(
    tmp_path: Path,
    scenario: str,
    expected_code: str,
) -> None:
    payload = run_admission(scenario=scenario, seed=72, out_dir=tmp_path / scenario)
    known_bad = payload["known_bad_results"][0]

    assert known_bad["ok"] is False
    assert known_bad["failure_code"] == expected_code
    assert known_bad["failure_code_matches_expected"] is True
    assert known_bad["failure_attribution_matches_template"] is True
    assert payload["checks_by_name"]["known_bad_plan_fails"]["ok"] is True
    assert payload["checks_by_name"]["known_bad_failure_code_matches_expected"]["ok"] is True
    assert payload["checks_by_name"]["failure_attribution_matches_template"]["ok"] is True


def test_adaptyv_admission_writes_required_checks_and_export_evidence(tmp_path: Path) -> None:
    payload = run_admission(
        scenario="partial_results_not_final",
        seed=73,
        out_dir=tmp_path / "partial-admission",
    )
    run_export = _read_json(Path(payload["run_export_path"]))

    assert set(REQUIRED_CHECK_NAMES).issubset(payload["checks_by_name"])
    assert payload["checks_by_name"]["run_export_contains_tool_trace_and_verifier_result"]["ok"] is True
    assert "tool_trace" in run_export
    assert "verifier_result" in run_export
    assert run_export["tool_trace"]
    assert run_export["verifier_result"]["ok"] is True


def test_adaptyv_admission_hidden_replay_files_are_not_agent_visible(tmp_path: Path) -> None:
    payload = run_admission(
        scenario="measured_result_supported_decision",
        seed=74,
        out_dir=tmp_path / "hidden-check",
    )
    agent_task_text = (Path(payload["run_dir"]) / "agent_task.json").read_text(encoding="utf-8")

    assert payload["checks_by_name"]["hidden_files_not_visible_to_agent"]["ok"] is True
    for token in AGENT_VISIBLE_FORBIDDEN_HIDDEN_TOKENS:
        assert token not in agent_task_text


def test_adaptyv_admission_scans_task_json_for_hidden_file_refs(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="measured_result_supported_decision",
        seed=76,
        out_dir=tmp_path / "task-hidden-leak",
    )
    task_path = episode.run_dir / "task.json"
    task = _read_json(task_path)
    task["leaked_schedule"] = "hidden/result_arrival_schedule.json"
    _write_json(task_path, task)

    payload = validate_existing_run(episode.run_dir)

    assert payload["admitted"] is False
    hidden_check = payload["checks_by_name"]["hidden_files_not_visible_to_agent"]
    assert hidden_check["ok"] is False
    assert "task.json" in hidden_check["details"]["visible_artifacts_with_forbidden_tokens"]
    assert _read_json(episode.run_dir / "admission.json") == payload


def test_adaptyv_admission_detects_corrupted_hidden_schedule(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=75,
        out_dir=tmp_path / "corrupt-schedule",
    )
    schedule_path = episode.run_dir / "hidden" / "result_arrival_schedule.json"
    schedule = _read_json(schedule_path)
    schedule["events"][0]["visible_at"] = "2099-01-01T00:00:00Z"
    _write_json(schedule_path, schedule)

    payload = validate_existing_run(episode.run_dir)

    assert payload["admitted"] is False
    assert payload["checks_by_name"]["result_arrival_schedule_deterministic"]["ok"] is False
    assert _read_json(episode.run_dir / "admission.json") == payload


def test_adaptyv_admission_reports_malformed_hidden_schedule_without_raising(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=77,
        out_dir=tmp_path / "malformed-schedule",
    )
    schedule_path = episode.run_dir / "hidden" / "result_arrival_schedule.json"
    schedule_path.write_text("{not-json", encoding="utf-8")

    payload = validate_existing_run(episode.run_dir)

    assert payload["admitted"] is False
    schedule_check = payload["checks_by_name"]["result_arrival_schedule_deterministic"]
    assert schedule_check["ok"] is False
    assert schedule_check["details"]["error_code"] == "HIDDEN_SCHEDULE_JSON_INVALID"
    assert schedule_check["details"]["file"] == "hidden/result_arrival_schedule.json"
    assert _read_json(episode.run_dir / "admission.json") == payload


def _read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
