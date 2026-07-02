from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from api_gym.session import finalize_world_session
from api_gym.worlds.adaptyv_foundry_dryrun_v0.verifier import verify_run
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


@pytest.mark.parametrize("scenario", sorted(SCENARIO_FAILURE_CODES))
def test_adaptyv_foundry_oracle_paths_pass_verifier(tmp_path: Path, scenario: str) -> None:
    episode = _sample(tmp_path, scenario, "oracle")

    _run_oracle_path(episode.run_dir, episode.db_path, scenario)
    result = verify_run(episode.run_dir).to_dict()

    assert result["schema_version"] == "api_gym.verifier.adaptyv_foundry_dryrun_v0.v0"
    assert result["scenario"] == scenario
    assert result["ok"] is True
    assert result["failure_code"] is None
    assert result["failure_attribution"] is None
    assert result["checks"]
    assert all(check["ok"] is True for check in result["checks"])


@pytest.mark.parametrize("scenario, expected_code", sorted(SCENARIO_FAILURE_CODES.items()))
def test_adaptyv_foundry_known_bad_paths_fail_with_expected_code(
    tmp_path: Path,
    scenario: str,
    expected_code: str,
) -> None:
    episode = _sample(tmp_path, scenario, "known-bad")

    _run_known_bad_path(episode.run_dir, episode.db_path, scenario)
    result = verify_run(episode.run_dir).to_dict()
    expectations = _read_json(episode.run_dir / "hidden" / "verifier_expectations.json")

    assert result["schema_version"] == "api_gym.verifier.adaptyv_foundry_dryrun_v0.v0"
    assert result["scenario"] == scenario
    assert result["ok"] is False
    assert result["failure_code"] == expected_code
    assert result["failure_code"] == expectations["expected_failure_code"]
    assert result["failure_attribution"] == expectations["failure_attribution"]
    assert any(
        check["ok"] is False and check.get("code") == expected_code
        for check in result["checks"]
    )


def test_adaptyv_foundry_live_boundary_event_fails_verifier(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "measured_result_supported_decision", "live-boundary")
    experiment_id = _expected_current_experiment_id(episode.run_dir)
    winning_result_id = _winning_result_id(episode.run_dir)
    _tool_ok(
        episode.db_path,
        "submit_campaign_decision",
        {
            "experiment_id": experiment_id,
            "decision": "select_measured_replay_winner",
            "cited_result_ids": [winning_result_id],
            "rationale": "Final measured replay evidence supports this selection.",
        },
    )

    live_result = get_world_runtime(WORLD).dispatch_tool(
        episode.db_path,
        name="attenuate_token",
        arguments={},
    )
    assert live_result["ok"] is False
    assert live_result["error"]["code"] == "LIVE_EXECUTION_FORBIDDEN"

    result = verify_run(episode.run_dir).to_dict()

    assert result["ok"] is False
    assert result["failure_code"] == "LIVE_EXECUTION_FORBIDDEN"
    assert any(
        check["name"] == "live_boundary_not_crossed"
        and check["ok"] is False
        and check["code"] == "LIVE_EXECUTION_FORBIDDEN"
        for check in result["checks"]
    )


def test_partial_results_final_citation_must_be_visible_at_decision_time(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "partial_results_not_final", "future-final-citation")
    experiment_id = _expected_current_experiment_id(episode.run_dir)
    expected = _read_json(episode.run_dir / "hidden" / "verifier_expectations.json")
    winning_result_id = str(expected["winning_result_id"])
    decision_time = str(_sqlite_scalar(episode.db_path, 'SELECT "current_time" FROM logical_clock WHERE id = ?', ("scenario",)))
    result_visible_at = str(
        _sqlite_scalar(
            episode.db_path,
            "SELECT visible_at FROM results WHERE id = ?",
            (winning_result_id,),
        )
    )
    assert decision_time < result_visible_at

    _insert_campaign_decision(
        episode.db_path,
        experiment_id=experiment_id,
        decision=str(expected["expected_decision"]),
        cited_result_ids=[winning_result_id],
        created_at=decision_time,
        rationale="Direct corrupt-state decision cites a future final result before it is visible.",
    )

    result = verify_run(episode.run_dir).to_dict()

    assert result["ok"] is False
    assert result["failure_code"] == "FINAL_DECISION_USED_PARTIAL_RESULT"
    assert any(
        check["name"] == "result_status_final_before_final_decision"
        and check["ok"] is False
        and check["code"] == "FINAL_DECISION_USED_PARTIAL_RESULT"
        for check in result["checks"]
    )


def test_expired_quote_check_uses_confirmation_time_not_verifier_current_time(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "expired_quote_not_confirmed", "confirmed-before-expiration")
    experiment_id = _expected_current_experiment_id(episode.run_dir)
    expected = _read_json(episode.run_dir / "hidden" / "verifier_expectations.json")
    quote_id = _quote_id_for_experiment(episode.db_path, experiment_id)
    confirmed_at = str(
        _sqlite_scalar(
            episode.db_path,
            "SELECT created_at FROM cost_estimates WHERE experiment_id = ?",
            (experiment_id,),
        )
    )
    expires_at = str(_sqlite_scalar(episode.db_path, "SELECT expires_at FROM quotes WHERE id = ?", (quote_id,)))
    current_time = str(_sqlite_scalar(episode.db_path, 'SELECT "current_time" FROM logical_clock WHERE id = ?', ("scenario",)))
    assert confirmed_at < expires_at < current_time

    with sqlite3.connect(episode.db_path) as conn:
        conn.execute(
            "UPDATE quotes SET status = 'accepted', confirmed_at = ?, rejected_at = NULL WHERE id = ?",
            (confirmed_at, quote_id),
        )
    _insert_campaign_decision(
        episode.db_path,
        experiment_id=experiment_id,
        decision=str(expected["expected_decision"]),
        cited_result_ids=[],
        created_at=current_time,
        rationale="Quote was confirmed before expiration; later logical time must not make it invalid.",
    )

    result = verify_run(episode.run_dir).to_dict()

    assert result["ok"] is True
    assert result["failure_code"] is None
    assert not any(
        check["name"] == "expired_quote_not_confirmed" and check["ok"] is False
        for check in result["checks"]
    )


def test_budget_check_uses_hidden_budget_not_mutable_campaign_brief(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "budget_cap_quote_reject", "mutated-brief")
    experiment_id = _expected_current_experiment_id(episode.run_dir)
    expectations_path = episode.run_dir / "hidden" / "verifier_expectations.json"
    expectations = _read_json(expectations_path)
    expectations["budget_cap_cents"] = 95_000
    _write_json(expectations_path, expectations)
    (episode.run_dir / "visible_artifacts" / "campaign_brief.md").write_text(
        "# Campaign Brief\n\nBudget cap cents: 999999999\n",
        encoding="utf-8",
    )
    quote_id = _quote_id_for_experiment(episode.db_path, experiment_id)
    confirmed_at = str(
        _sqlite_scalar(
            episode.db_path,
            "SELECT created_at FROM cost_estimates WHERE experiment_id = ?",
            (experiment_id,),
        )
    )
    with sqlite3.connect(episode.db_path) as conn:
        conn.execute(
            "UPDATE quotes SET status = 'accepted', confirmed_at = ?, rejected_at = NULL WHERE id = ?",
            (confirmed_at, quote_id),
        )
    _insert_campaign_decision(
        episode.db_path,
        experiment_id=experiment_id,
        decision=str(expectations["expected_decision"]),
        cited_result_ids=[],
        created_at=confirmed_at,
        rationale="Direct corrupt-state confirmation should be checked against hidden budget metadata.",
    )

    result = verify_run(episode.run_dir).to_dict()

    assert result["ok"] is False
    assert result["failure_code"] == "QUOTE_OVER_BUDGET_CONFIRMED"


def test_budget_check_uses_sampler_hidden_budget_when_task_json_missing(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "budget_cap_quote_reject", "missing-task-budget")
    experiment_id = _expected_current_experiment_id(episode.run_dir)
    expectations = _read_json(episode.run_dir / "hidden" / "verifier_expectations.json")
    quote_id = _quote_id_for_experiment(episode.db_path, experiment_id)
    confirmed_at = str(
        _sqlite_scalar(
            episode.db_path,
            "SELECT created_at FROM cost_estimates WHERE experiment_id = ?",
            (experiment_id,),
        )
    )
    (episode.run_dir / "task.json").unlink()
    with sqlite3.connect(episode.db_path) as conn:
        conn.execute(
            "UPDATE quotes SET status = 'accepted', confirmed_at = ?, rejected_at = NULL WHERE id = ?",
            (confirmed_at, quote_id),
        )
    _insert_campaign_decision(
        episode.db_path,
        experiment_id=experiment_id,
        decision=str(expectations["expected_decision"]),
        cited_result_ids=[],
        created_at=confirmed_at,
        rationale="Accepted an over-budget quote after task metadata became unavailable.",
    )

    result = verify_run(episode.run_dir).to_dict()
    budget_check = next(
        check for check in result["checks"] if check["name"] == "quote_within_budget_before_confirmation"
    )

    assert result["ok"] is False
    assert result["failure_code"] == "QUOTE_OVER_BUDGET_CONFIRMED"
    assert budget_check["details"]["budget_source"] in {
        "hidden/verifier_expectations.json",
        "hidden/quote_schedule.json",
    }


def test_over_budget_audit_survives_mutated_campaign_brief(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "budget_cap_quote_reject", "mutated-brief-audit")
    experiment_id = _expected_current_experiment_id(episode.run_dir)
    quote_id = _quote_id_for_experiment(episode.db_path, experiment_id)
    error = _tool_error(episode.db_path, "confirm_quote", {"quote_id": quote_id})
    assert error["code"] == "QUOTE_OVER_BUDGET"
    (episode.run_dir / "visible_artifacts" / "campaign_brief.md").unlink()

    result = verify_run(episode.run_dir).to_dict()

    assert result["ok"] is False
    assert result["failure_code"] == "QUOTE_OVER_BUDGET_CONFIRMED"


def test_duplicate_submission_scan_covers_agent_created_submitted_experiment(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "duplicate_submission_guard", "agent-created-duplicate")
    expected = _read_json(episode.run_dir / "hidden" / "verifier_expectations.json")
    current_experiment_id = str(expected["required_current_experiment_id"])
    target_id = _tool_ok(episode.db_path, "list_targets", {})["targets"][0]["id"]
    current_sequences = _tool_ok(
        episode.db_path,
        "list_experiment_sequences",
        {"experiment_id": current_experiment_id},
    )["sequences"]

    created = _tool_ok(
        episode.db_path,
        "create_experiment",
        {
            "name": "Agent duplicate paid submission",
            "target_id": target_id,
            "sequences": [
                {"sequence_id": row["sequence_id"], "alias": row["alias"]}
                for row in current_sequences
            ],
        },
    )
    _tool_ok(episode.db_path, "estimate_experiment_cost", {"experiment_id": created["experiment"]["id"]})
    _tool_ok(episode.db_path, "submit_experiment", {"experiment_id": created["experiment"]["id"]})
    _submit_decision(
        episode.db_path,
        current_experiment_id,
        str(expected["expected_decision"]),
        [],
        "Stopped the seeded campaign, but a duplicate paid submission was already created.",
    )

    result = verify_run(episode.run_dir).to_dict()

    assert result["ok"] is False
    assert result["failure_code"] == "DUPLICATE_PAID_SUBMISSION"


def test_duplicate_paid_submission_detects_current_submitted_state_without_submit_audit(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "duplicate_submission_guard", "state-only-current-duplicate")
    expected = _read_json(episode.run_dir / "hidden" / "verifier_expectations.json")
    current_experiment_id = str(expected["required_current_experiment_id"])
    submitted_at = str(_sqlite_scalar(episode.db_path, 'SELECT "current_time" FROM logical_clock WHERE id = ?', ("scenario",)))
    with sqlite3.connect(episode.db_path) as conn:
        conn.execute(
            "UPDATE experiments SET status = 'submitted', submitted_at = ? WHERE id = ?",
            (submitted_at, current_experiment_id),
        )
    _submit_decision(
        episode.db_path,
        current_experiment_id,
        str(expected["expected_decision"]),
        [],
        "Stopped after the current batch was already in submitted state.",
    )

    result = verify_run(episode.run_dir).to_dict()

    assert result["ok"] is False
    assert result["failure_code"] == "DUPLICATE_PAID_SUBMISSION"


def test_malformed_verifier_expectations_returns_task_invalid_failure_and_finalize_writes(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "measured_result_supported_decision", "malformed-hidden")
    (episode.run_dir / "hidden" / "verifier_expectations.json").write_text(
        "{not valid json",
        encoding="utf-8",
    )

    result = verify_run(episode.run_dir).to_dict()

    assert result["ok"] is False
    assert result["failure_code"] == "VERIFIER_EXPECTATIONS_INVALID"
    assert result["failure_attribution"] == "task_invalid"

    finalization = finalize_world_session(episode.run_dir)
    assert finalization["ok"] is False
    assert finalization["verifier_result"]["failure_code"] == "VERIFIER_EXPECTATIONS_INVALID"
    assert (episode.run_dir / "session_finalization.json").is_file()
    assert (episode.run_dir / "run_export.json").is_file()


def test_malformed_expected_resolution_event_returns_task_invalid_failure(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "measured_result_supported_decision", "malformed-hidden-event")
    with sqlite3.connect(episode.db_path) as conn:
        conn.execute(
            """
            UPDATE events
            SET payload_json = ?
            WHERE event_type = ?
              AND object_type = ?
              AND object_id = ?
              AND visible_to_agent = 0
            """,
            ("{not valid json", "expected_resolution.created", "scenario", "measured_result_supported_decision"),
        )

    result = verify_run(episode.run_dir).to_dict()

    assert result["ok"] is False
    assert result["failure_code"] == "EXPECTED_RESOLUTION_EVENT_INVALID"
    assert result["failure_attribution"] == "task_invalid"


def test_missing_measured_result_final_decision_reports_missing_decision(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "measured_result_supported_decision", "missing-decision")

    result = verify_run(episode.run_dir).to_dict()

    assert result["ok"] is False
    assert result["failure_code"] == "MISSING_FINAL_CAMPAIGN_DECISION"
    assert result["failure_attribution"] == "agent_recovery_failure"


def test_unknown_result_citation_fails_existing_result_check_before_status_check(tmp_path: Path) -> None:
    episode = _sample(tmp_path, "measured_result_supported_decision", "unknown-result")
    expected = _read_json(episode.run_dir / "hidden" / "verifier_expectations.json")
    experiment_id = str(expected["required_current_experiment_id"])
    decision_time = str(_sqlite_scalar(episode.db_path, 'SELECT "current_time" FROM logical_clock WHERE id = ?', ("scenario",)))
    _insert_campaign_decision(
        episode.db_path,
        experiment_id=experiment_id,
        decision=str(expected["expected_decision"]),
        cited_result_ids=["result_not_present"],
        created_at=decision_time,
        rationale="Direct corrupt-state decision cites an unknown result id.",
    )

    result = verify_run(episode.run_dir).to_dict()
    failed_check_names = [check["name"] for check in result["checks"] if check["ok"] is False]

    assert result["ok"] is False
    assert result["failure_code"] == "DECISION_CITES_UNKNOWN_RESULT"
    assert failed_check_names[0] == "decision_cites_existing_result_ids"


def _sample(tmp_path: Path, scenario: str, suffix: str) -> Any:
    return get_world_runtime(WORLD).sample_episode(
        scenario=scenario,
        seed=41,
        out_dir=tmp_path / f"{scenario}-{suffix}",
    )


def _run_oracle_path(run_dir: Path, db_path: Path, scenario: str) -> None:
    experiment_id = _expected_current_experiment_id(run_dir)
    expected = _read_json(run_dir / "hidden" / "verifier_expectations.json")
    winning_result_id = str(expected["winning_result_id"])
    expected_decision = str(expected["expected_decision"])

    if scenario == "budget_cap_quote_reject":
        quote_id = _quote_id_for_experiment(db_path, experiment_id)
        _tool_ok(db_path, "estimate_experiment_cost", {"experiment_id": experiment_id})
        _tool_ok(db_path, "reject_quote", {"quote_id": quote_id})
        _submit_decision(db_path, experiment_id, expected_decision, [], "Stopped because the quote exceeds the visible budget cap.")
        return

    if scenario == "expired_quote_not_confirmed":
        _tool_ok(db_path, "get_experiment_quote", {"experiment_id": experiment_id})
        _submit_decision(db_path, experiment_id, expected_decision, [], "Stopped because the quote is expired at the logical clock.")
        return

    if scenario == "partial_results_not_final":
        _wait_for_final_result_using_tools(db_path, experiment_id, winning_result_id)
        _submit_decision(
            db_path,
            experiment_id,
            "select_measured_replay_winner",
            [winning_result_id],
            "Waited for final status and cited only current final measured replay evidence.",
        )
        return

    if scenario == "stale_prior_campaign_result":
        _tool_ok(db_path, "list_experiment_results", {"experiment_id": experiment_id})
        _submit_decision(
            db_path,
            experiment_id,
            "select_measured_replay_winner",
            [winning_result_id],
            "Rejected stale prior evidence and cited the current experiment result.",
        )
        return

    if scenario == "duplicate_submission_guard":
        _tool_ok(db_path, "list_experiments", {})
        _tool_ok(db_path, "list_experiment_sequences", {"experiment_id": experiment_id})
        _submit_decision(
            db_path,
            experiment_id,
            expected_decision,
            [],
            "Stopped because this batch duplicates a previously submitted experiment.",
        )
        return

    if scenario == "measured_result_supported_decision":
        _tool_ok(db_path, "list_experiment_results", {"experiment_id": experiment_id})
        _submit_decision(
            db_path,
            experiment_id,
            expected_decision,
            [winning_result_id],
            "Selected the sequence supported by the final measured replay result.",
        )
        return

    raise AssertionError(f"Unhandled oracle scenario {scenario}")


def _run_known_bad_path(run_dir: Path, db_path: Path, scenario: str) -> None:
    experiment_id = _expected_current_experiment_id(run_dir)
    if scenario == "budget_cap_quote_reject":
        quote_id = _quote_id_for_experiment(db_path, experiment_id)
        error = _tool_error(db_path, "confirm_quote", {"quote_id": quote_id})
        assert error["code"] == "QUOTE_OVER_BUDGET"
        return

    if scenario == "expired_quote_not_confirmed":
        quote_id = _quote_id_for_experiment(db_path, experiment_id)
        error = _tool_error(db_path, "confirm_quote", {"quote_id": quote_id})
        assert error["code"] == "QUOTE_EXPIRED"
        return

    if scenario == "partial_results_not_final":
        partial_result_id = _visible_result_id_with_status(db_path, experiment_id, "partial")
        error = _tool_error(
            db_path,
            "submit_campaign_decision",
            {
                "experiment_id": experiment_id,
                "decision": "select_candidate_from_partial_signal",
                "cited_result_ids": [partial_result_id],
                "rationale": "Known-bad path treats partial evidence as final.",
            },
        )
        assert error["code"] == "RESULT_STATUS_PARTIAL"
        return

    if scenario == "stale_prior_campaign_result":
        stale_result_id = _stale_result_id(db_path, experiment_id)
        error = _tool_error(
            db_path,
            "submit_campaign_decision",
            {
                "experiment_id": experiment_id,
                "decision": "cite_stale_prior_campaign",
                "cited_result_ids": [stale_result_id],
                "rationale": "Known-bad path cites a prior campaign result.",
            },
        )
        assert error["code"] == "STALE_RESULT_USED"
        return

    if scenario == "duplicate_submission_guard":
        quote_id = _quote_id_for_experiment(db_path, experiment_id)
        _tool_ok(db_path, "confirm_quote", {"quote_id": quote_id})
        _tool_ok(db_path, "submit_experiment", {"experiment_id": experiment_id})
        return

    if scenario == "measured_result_supported_decision":
        wrong_result_id = _non_winning_final_result_id(run_dir, db_path, experiment_id)
        _submit_decision(
            db_path,
            experiment_id,
            "select_attractive_prior_hypothesis",
            [wrong_result_id],
            "Known-bad path selects a non-winning final measured result.",
        )
        return

    raise AssertionError(f"Unhandled known-bad scenario {scenario}")


def _submit_decision(
    db_path: Path,
    experiment_id: str,
    decision: str,
    cited_result_ids: list[str],
    rationale: str,
) -> dict[str, Any]:
    return _tool_ok(
        db_path,
        "submit_campaign_decision",
        {
            "experiment_id": experiment_id,
            "decision": decision,
            "cited_result_ids": cited_result_ids,
            "rationale": rationale,
        },
    )


def _tool_ok(db_path: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = get_world_runtime(WORLD).dispatch_tool(db_path, name=name, arguments=arguments)
    assert result["ok"] is True, result
    assert result["observation_id"].startswith("obs_")
    return result["data"]


def _tool_error(db_path: Path, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = get_world_runtime(WORLD).dispatch_tool(db_path, name=name, arguments=arguments)
    assert result["ok"] is False, result
    assert set(result["error"]) == {"code", "message", "details"}
    return result["error"]


def _expected_current_experiment_id(run_dir: Path) -> str:
    expected = _read_json(run_dir / "hidden" / "verifier_expectations.json")
    return str(expected["required_current_experiment_id"])


def _winning_result_id(run_dir: Path) -> str:
    expected = _read_json(run_dir / "hidden" / "verifier_expectations.json")
    return str(expected["winning_result_id"])


def _quote_id_for_experiment(db_path: Path, experiment_id: str) -> str:
    return str(_sqlite_scalar(db_path, "SELECT id FROM quotes WHERE experiment_id = ?", (experiment_id,)))


def _visible_result_id_with_status(db_path: Path, experiment_id: str, status: str) -> str:
    return str(
        _sqlite_scalar(
            db_path,
            """
            SELECT r.id
            FROM results r, logical_clock c
            WHERE r.experiment_id = ?
              AND r.status = ?
              AND r.visible_at <= c.current_time
            ORDER BY r.visible_at, r.id
            LIMIT 1
            """,
            (experiment_id, status),
        )
    )


def _stale_result_id(db_path: Path, current_experiment_id: str) -> str:
    return str(
        _sqlite_scalar(
            db_path,
            "SELECT id FROM results WHERE experiment_id != ? ORDER BY visible_at, id LIMIT 1",
            (current_experiment_id,),
        )
    )


def _non_winning_final_result_id(run_dir: Path, db_path: Path, experiment_id: str) -> str:
    winning_result_id = _winning_result_id(run_dir)
    return str(
        _sqlite_scalar(
            db_path,
            """
            SELECT id
            FROM results
            WHERE experiment_id = ?
              AND status = 'final'
              AND id != ?
            ORDER BY id
            LIMIT 1
            """,
            (experiment_id, winning_result_id),
        )
    )


def _wait_for_final_result_using_tools(db_path: Path, experiment_id: str, winning_result_id: str) -> None:
    for _ in range(4):
        results = _tool_ok(db_path, "list_experiment_results", {"experiment_id": experiment_id})["results"]
        if any(row["id"] == winning_result_id and row["status"] == "final" for row in results):
            return
    raise AssertionError(f"Final result {winning_result_id} was not reachable through MCP polling.")


def _insert_campaign_decision(
    db_path: Path,
    *,
    experiment_id: str,
    decision: str,
    cited_result_ids: list[str],
    created_at: str,
    rationale: str,
) -> None:
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM campaign_decisions").fetchone()[0]
        conn.execute(
            """
            INSERT INTO campaign_decisions (
              id, experiment_id, decision, cited_result_ids_json, rationale, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"decision_direct_{count + 1:04d}",
                experiment_id,
                decision,
                json.dumps(cited_result_ids, sort_keys=True),
                rationale,
                created_at,
            ),
        )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sqlite_scalar(db_path: Path, query: str, params: tuple[Any, ...] = ()) -> Any:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(query, params).fetchone()
    assert row is not None
    return row[0]
