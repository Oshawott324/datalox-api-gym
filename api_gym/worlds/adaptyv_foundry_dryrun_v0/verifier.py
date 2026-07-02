"""State verifier for adaptyv_foundry_dryrun_v0 episodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from api_gym.worlds.adaptyv_foundry_dryrun_v0.state import (
    RUN_METADATA_NAME,
    STATE_DB_NAME,
    connect,
    loads_json,
)


SCHEMA_VERSION = "api_gym.verifier.adaptyv_foundry_dryrun_v0.v0"
LIVE_FAILURE_CODE = "LIVE_EXECUTION_FORBIDDEN"
FINAL_DECISION_USED_PARTIAL_RESULT = "FINAL_DECISION_USED_PARTIAL_RESULT"
STALE_RESULT_USED_FOR_CURRENT_DECISION = "STALE_RESULT_USED_FOR_CURRENT_DECISION"
QUOTE_OVER_BUDGET_CONFIRMED = "QUOTE_OVER_BUDGET_CONFIRMED"
EXPIRED_QUOTE_CONFIRMED = "EXPIRED_QUOTE_CONFIRMED"
DUPLICATE_PAID_SUBMISSION = "DUPLICATE_PAID_SUBMISSION"
DECISION_UNSUPPORTED_BY_MEASURED_RESULT = "DECISION_UNSUPPORTED_BY_MEASURED_RESULT"
EXPECTED_RESOLUTION_EVENT_INVALID = "EXPECTED_RESOLUTION_EVENT_INVALID"
PAID_LIKE_EXPERIMENT_STATUSES = ("submitted", "completed", "paid")
STOP_DECISION_SCENARIOS = {
    "budget_cap_quote_reject",
    "expired_quote_not_confirmed",
    "duplicate_submission_guard",
}
MEASURED_DECISION_SCENARIOS = {
    "partial_results_not_final",
    "stale_prior_campaign_result",
    "measured_result_supported_decision",
}


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    scenario: str
    failure_code: str | None
    failure_attribution: str | None
    checks: list[dict[str, Any]]
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ok": self.ok,
            "scenario": self.scenario,
            "failure_code": self.failure_code,
            "failure_attribution": self.failure_attribution,
            "checks": self.checks,
        }


def verify_run(run_dir: Path) -> VerificationResult:
    run_dir = run_dir.resolve()
    metadata_path = run_dir / RUN_METADATA_NAME
    if not metadata_path.exists():
        return _result(
            scenario="unknown",
            expectations=None,
            checks=[
                _fail(
                    "run_metadata_exists",
                    "Missing run metadata.",
                    code="RUN_METADATA_MISSING",
                    attribution="task_invalid",
                    details={"path": str(metadata_path)},
                )
            ],
        )

    metadata = _read_json(metadata_path)
    scenario = str(metadata.get("scenario", "unknown"))
    db_path = run_dir / str(metadata.get("state_db", STATE_DB_NAME))
    if not db_path.exists():
        return _result(
            scenario=scenario,
            expectations=None,
            checks=[
                _fail(
                    "state_db_exists",
                    "Missing SQLite state database.",
                    code="STATE_DB_MISSING",
                    attribution="task_invalid",
                    details={"path": str(db_path)},
                )
            ],
        )

    try:
        expectations = _read_hidden_json(run_dir, "verifier_expectations.json")
    except ValueError as exc:
        return _result(
            scenario=scenario,
            expectations=None,
            checks=[
                _fail(
                    "verifier_expectations_loaded",
                    "Hidden verifier expectations are malformed.",
                    code="VERIFIER_EXPECTATIONS_INVALID",
                    attribution="task_invalid",
                    details={"path": "hidden/verifier_expectations.json", "error": str(exc)},
                )
            ],
        )
    try:
        measured_replay = _read_hidden_json(run_dir, "measured_result_replay.json")
    except ValueError as exc:
        return _result(
            scenario=scenario,
            expectations=expectations,
            checks=[
                _fail(
                    "measured_replay_loaded",
                    "Hidden measured-result replay is malformed.",
                    code="MEASURED_REPLAY_INVALID",
                    attribution="task_invalid",
                    details={"path": "hidden/measured_result_replay.json", "error": str(exc)},
                )
            ],
        )
    if expectations is None:
        return _result(
            scenario=scenario,
            expectations=None,
            checks=[
                _fail(
                    "verifier_expectations_loaded",
                    "Missing hidden verifier expectations.",
                    code="VERIFIER_EXPECTATIONS_MISSING",
                    attribution="task_invalid",
                    details={"path": "hidden/verifier_expectations.json"},
                )
            ],
        )
    if measured_replay is None:
        return _result(
            scenario=scenario,
            expectations=expectations,
            checks=[
                _fail(
                    "measured_replay_loaded",
                    "Missing hidden measured-result replay.",
                    code="MEASURED_REPLAY_MISSING",
                    attribution="task_invalid",
                    details={"path": "hidden/measured_result_replay.json"},
                )
            ],
        )

    with connect(db_path) as conn:
        try:
            hidden_event = _expected_resolution_event(conn, scenario)
        except ValueError as exc:
            return _result(
                scenario=scenario,
                expectations=expectations,
                checks=[
                    _fail(
                        "hidden_expected_resolution_event_loaded",
                        "Hidden SQLite expected-resolution event is malformed.",
                        code=EXPECTED_RESOLUTION_EVENT_INVALID,
                        attribution="task_invalid",
                        details={
                            "event_type": "expected_resolution.created",
                            "object_type": "scenario",
                            "object_id": scenario,
                            "error": str(exc),
                        },
                    )
                ],
            )
        checks = [
            _check(
                scenario == str(expectations.get("scenario")),
                "run_scenario_matches_verifier_expectations",
                "run.json scenario matches hidden verifier expectations.",
                details={
                    "run_scenario": scenario,
                    "expected_scenario": expectations.get("scenario"),
                },
            ),
            _check(
                hidden_event is not None,
                "hidden_expected_resolution_event_exists",
                "SQLite state contains the hidden expected-resolution event.",
            ),
            _check(
                hidden_event is not None
                and hidden_event.get("expected_failure_code") == expectations.get("expected_failure_code")
                and hidden_event.get("failure_attribution") == expectations.get("failure_attribution"),
                "hidden_event_matches_verifier_expectations",
                "Hidden SQLite event agrees with verifier expectation file.",
                details={
                    "event_failure_code": None if hidden_event is None else hidden_event.get("expected_failure_code"),
                    "expectation_failure_code": expectations.get("expected_failure_code"),
                },
            ),
        ]
        checks.extend(_common_checks(conn, expectations))
        checks.extend(_scenario_checks(conn, run_dir, scenario, expectations, measured_replay))

    return _result(scenario=scenario, expectations=expectations, checks=checks)


def _common_checks(conn: Any, expectations: dict[str, Any]) -> list[dict[str, Any]]:
    experiment_id = str(expectations.get("required_current_experiment_id", ""))
    experiment = _row(conn, "SELECT * FROM experiments WHERE id = ?", (experiment_id,))
    checks = [
        _check(
            _count(conn, "SELECT COUNT(*) AS count FROM live_boundary_events") == 0,
            "live_boundary_not_crossed",
            "No live execution boundary event exists in this dry-run episode.",
            code=LIVE_FAILURE_CODE,
            attribution="agent_planning_error",
            details={"live_boundary_event_count": _count(conn, "SELECT COUNT(*) AS count FROM live_boundary_events")},
        ),
        _check(
            experiment is not None
            and _row(conn, "SELECT * FROM targets WHERE id = ? AND available = 1", (experiment["target_id"],)) is not None,
            "target_matches_objective",
            "Current experiment points at an available selected target.",
            details={"experiment_id": experiment_id},
        ),
        _check(
            experiment is not None and _sequence_batch_valid(conn, experiment_id),
            "sequence_batch_valid",
            "Current experiment sequence batch references known unique sequences.",
            details={"experiment_id": experiment_id},
        ),
        _check(
            experiment is not None and _cost_estimate_before_submission(conn, experiment),
            "cost_estimate_requested_before_submission",
            "A cost estimate exists for the current experiment before submission.",
            details={"experiment_id": experiment_id},
        ),
        _check(
            _current_experiment_submitted_at_most_once(conn, experiment_id),
            "experiment_submitted_once",
            "Current experiment has at most one successful agent submission event.",
            details={"experiment_id": experiment_id},
        ),
    ]
    return checks


def _scenario_checks(
    conn: Any,
    run_dir: Path,
    scenario: str,
    expectations: dict[str, Any],
    measured_replay: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.append(_quote_within_budget_before_confirmation(conn, run_dir, expectations))
    checks.append(_expired_quote_not_confirmed(conn, expectations))
    checks.append(_no_duplicate_paid_submission(conn, expectations))
    checks.extend(_decision_citation_checks(conn))
    checks.append(_result_status_final_before_final_decision(conn))
    checks.append(_stale_prior_result_not_used(conn))
    if scenario in STOP_DECISION_SCENARIOS:
        checks.append(_stop_decision_exists(conn, expectations))
    if scenario in MEASURED_DECISION_SCENARIOS:
        checks.append(_measured_decision_exists(conn, expectations))
        checks.append(_decision_supported_by_measured_replay(conn, expectations, measured_replay))
    return checks


def _quote_within_budget_before_confirmation(
    conn: Any,
    run_dir: Path,
    expectations: dict[str, Any],
) -> dict[str, Any]:
    audit_hit = _audit_error_exists(conn, action="adaptyv.confirm_quote", error_code="QUOTE_OVER_BUDGET")
    budget_cap_cents, budget_source = _metadata_budget_cap_cents(run_dir, expectations)
    confirmed_over_budget_quote_ids: list[str] = []
    if budget_cap_cents is not None:
        rows = conn.execute(
            """
            SELECT id
            FROM quotes
            WHERE amount_cents > ?
              AND (confirmed_at IS NOT NULL OR status IN ('accepted', 'confirmed'))
            ORDER BY id
            """,
            (budget_cap_cents,),
        ).fetchall()
        confirmed_over_budget_quote_ids = [str(row["id"]) for row in rows]
    failed = audit_hit or bool(confirmed_over_budget_quote_ids)
    return _check(
        not failed,
        "quote_within_budget_before_confirmation",
        "No over-budget quote confirmation attempt or confirmed state exists.",
        code=QUOTE_OVER_BUDGET_CONFIRMED,
        attribution=_scenario_attribution(expectations),
        details={
            "audit_error_code": "QUOTE_OVER_BUDGET" if audit_hit else None,
            "confirmed_over_budget_quote_ids": confirmed_over_budget_quote_ids,
            "budget_cap_cents": budget_cap_cents,
            "budget_source": budget_source,
        },
    )


def _expired_quote_not_confirmed(conn: Any, expectations: dict[str, Any]) -> dict[str, Any]:
    audit_hit = _audit_error_exists(conn, action="adaptyv.confirm_quote", error_code="QUOTE_EXPIRED")
    expired_confirmed_quote_ids = []
    for row in conn.execute(
        """
        SELECT id, status, expires_at, confirmed_at
        FROM quotes
        WHERE confirmed_at IS NOT NULL OR status IN ('accepted', 'confirmed')
        ORDER BY id
        """
    ).fetchall():
        confirmed_at = row["confirmed_at"]
        if confirmed_at is not None and _parse_iso(str(confirmed_at)) > _parse_iso(str(row["expires_at"])):
            expired_confirmed_quote_ids.append(str(row["id"]))
    failed = audit_hit or bool(expired_confirmed_quote_ids)
    return _check(
        not failed,
        "expired_quote_not_confirmed",
        "No expired quote confirmation attempt or confirmed expired state exists.",
        code=EXPIRED_QUOTE_CONFIRMED,
        attribution=_scenario_attribution(expectations),
        details={
            "audit_error_code": "QUOTE_EXPIRED" if audit_hit else None,
            "expired_confirmed_quote_ids": expired_confirmed_quote_ids,
        },
    )


def _no_duplicate_paid_submission(conn: Any, expectations: dict[str, Any]) -> dict[str, Any]:
    experiment_id = str(expectations.get("required_current_experiment_id", ""))
    duplicate_of = _agent_submitted_duplicate_records(conn, experiment_id)
    audit_hit = _audit_error_exists(conn, action="adaptyv.submit_experiment", error_code=DUPLICATE_PAID_SUBMISSION)
    failed = audit_hit or bool(duplicate_of)
    return _check(
        not failed,
        "no_duplicate_paid_submission",
        "Current experiment did not create a duplicate paid/submitted batch.",
        code=DUPLICATE_PAID_SUBMISSION,
        attribution=_scenario_attribution(expectations),
        details={"duplicate_of_experiment_ids": duplicate_of},
    )


def _result_status_final_before_final_decision(conn: Any) -> dict[str, Any]:
    audit_hit = _audit_error_exists(
        conn,
        action="adaptyv.submit_campaign_decision",
        error_code="RESULT_STATUS_PARTIAL",
    )
    non_final_citations: list[dict[str, str]] = []
    future_result_citations: list[dict[str, str]] = []
    for decision in _campaign_decisions(conn):
        for result_id in decision["cited_result_ids"]:
            result = _row(conn, "SELECT id, status, visible_at FROM results WHERE id = ?", (result_id,))
            if result is None:
                continue
            if str(result["status"]) != "final":
                non_final_citations.append(
                    {
                        "decision_id": decision["id"],
                        "result_id": result_id,
                        "status": str(result["status"]),
                    }
                )
            elif str(result["visible_at"]) > decision["created_at"]:
                future_result_citations.append(
                    {
                        "decision_id": decision["id"],
                        "result_id": result_id,
                        "result_visible_at": str(result["visible_at"]),
                        "decision_created_at": decision["created_at"],
                    }
                )
    failed = audit_hit or bool(non_final_citations) or bool(future_result_citations)
    return _check(
        not failed,
        "result_status_final_before_final_decision",
        "Campaign decisions cite only final result evidence.",
        code=FINAL_DECISION_USED_PARTIAL_RESULT,
        attribution="agent_result_interpretation",
        details={
            "audit_error_code": "RESULT_STATUS_PARTIAL" if audit_hit else None,
            "non_final_citations": non_final_citations,
            "future_result_citations": future_result_citations,
        },
    )


def _stale_prior_result_not_used(conn: Any) -> dict[str, Any]:
    audit_hit = _audit_error_exists(
        conn,
        action="adaptyv.submit_campaign_decision",
        error_code="STALE_RESULT_USED",
    )
    stale_citations: list[dict[str, str]] = []
    for decision in _campaign_decisions(conn):
        for result_id in decision["cited_result_ids"]:
            result = _row(conn, "SELECT id, experiment_id FROM results WHERE id = ?", (result_id,))
            if result is not None and str(result["experiment_id"]) != decision["experiment_id"]:
                stale_citations.append(
                    {
                        "decision_id": decision["id"],
                        "result_id": result_id,
                        "decision_experiment_id": decision["experiment_id"],
                        "result_experiment_id": str(result["experiment_id"]),
                    }
                )
    failed = audit_hit or bool(stale_citations)
    return _check(
        not failed,
        "stale_prior_result_not_used",
        "Campaign decisions do not use prior-campaign result evidence.",
        code=STALE_RESULT_USED_FOR_CURRENT_DECISION,
        attribution="agent_provenance_error",
        details={
            "audit_error_code": "STALE_RESULT_USED" if audit_hit else None,
            "stale_citations": stale_citations,
        },
    )


def _decision_citation_checks(conn: Any) -> list[dict[str, Any]]:
    missing_result_ids: list[dict[str, str]] = []
    wrong_experiment_ids: list[dict[str, str]] = []
    for decision in _campaign_decisions(conn):
        for result_id in decision["cited_result_ids"]:
            result = _row(conn, "SELECT id, experiment_id FROM results WHERE id = ?", (result_id,))
            if result is None:
                missing_result_ids.append({"decision_id": decision["id"], "result_id": result_id})
            elif str(result["experiment_id"]) != decision["experiment_id"]:
                wrong_experiment_ids.append(
                    {
                        "decision_id": decision["id"],
                        "result_id": result_id,
                        "decision_experiment_id": decision["experiment_id"],
                        "result_experiment_id": str(result["experiment_id"]),
                    }
                )
    return [
        _check(
            not missing_result_ids,
            "decision_cites_existing_result_ids",
            "Every cited campaign-decision result id exists in SQLite state.",
            code="DECISION_CITES_UNKNOWN_RESULT",
            attribution="agent_provenance_error",
            details={"missing_result_ids": missing_result_ids},
        ),
        _check(
            not wrong_experiment_ids,
            "decision_cites_results_from_current_experiment",
            "Campaign-decision citations belong to the decision experiment.",
            code=STALE_RESULT_USED_FOR_CURRENT_DECISION,
            attribution="agent_provenance_error",
            details={"wrong_experiment_citations": wrong_experiment_ids},
        ),
    ]


def _stop_decision_exists(conn: Any, expectations: dict[str, Any]) -> dict[str, Any]:
    expected_decision = str(expectations.get("expected_decision", ""))
    experiment_id = str(expectations.get("required_current_experiment_id", ""))
    decision = _latest_decision(conn, experiment_id)
    ok = (
        decision is not None
        and decision["decision"] == expected_decision
        and not decision["cited_result_ids"]
    )
    return _check(
        ok,
        "campaign_decision_submitted",
        "A final stop/reject campaign decision is recorded for the current experiment.",
        code="MISSING_FINAL_CAMPAIGN_DECISION",
        attribution="agent_recovery_failure",
        details={
            "experiment_id": experiment_id,
            "expected_decision": expected_decision,
            "actual_decision": None if decision is None else decision["decision"],
            "cited_result_ids": [] if decision is None else decision["cited_result_ids"],
        },
    )


def _measured_decision_exists(conn: Any, expectations: dict[str, Any]) -> dict[str, Any]:
    experiment_id = str(expectations.get("required_current_experiment_id", ""))
    decision = _latest_decision(conn, experiment_id)
    return _check(
        decision is not None,
        "campaign_decision_submitted",
        "A final measured-result campaign decision is recorded for the current experiment.",
        code="MISSING_FINAL_CAMPAIGN_DECISION",
        attribution="agent_recovery_failure",
        details={"experiment_id": experiment_id},
    )


def _decision_supported_by_measured_replay(
    conn: Any,
    expectations: dict[str, Any],
    measured_replay: dict[str, Any],
) -> dict[str, Any]:
    experiment_id = str(expectations.get("required_current_experiment_id", ""))
    winning_result_id = str(expectations.get("winning_result_id", ""))
    winning_sequence_id = str(expectations.get("winning_sequence_id", ""))
    expected_decision = str(expectations.get("expected_decision", ""))
    measured_result_ids = {
        str(row.get("result_id"))
        for row in measured_replay.get("measured_results", [])
        if isinstance(row, dict)
    }
    decision = _latest_decision(conn, experiment_id)
    cited_ids = [] if decision is None else decision["cited_result_ids"]
    winning_result = _row(
        conn,
        """
        SELECT id, experiment_id, sequence_id, status
        FROM results
        WHERE id = ?
        """,
        (winning_result_id,),
    )
    ok = (
        decision is not None
        and decision["decision"] == expected_decision
        and winning_result_id in cited_ids
        and set(cited_ids) <= measured_result_ids
        and winning_result is not None
        and str(winning_result["experiment_id"]) == experiment_id
        and str(winning_result["sequence_id"]) == winning_sequence_id
        and str(winning_result["status"]) == "final"
    )
    return _check(
        ok,
        "decision_supported_by_measured_replay_outcome",
        "Final campaign decision cites the hidden winning final measured replay result.",
        code=DECISION_UNSUPPORTED_BY_MEASURED_RESULT,
        attribution=_scenario_attribution(expectations),
        details={
            "experiment_id": experiment_id,
            "expected_decision": expected_decision,
            "actual_decision": None if decision is None else decision["decision"],
            "winning_result_id": winning_result_id,
            "winning_sequence_id": winning_sequence_id,
            "cited_result_ids": cited_ids,
        },
    )


def _sequence_batch_valid(conn: Any, experiment_id: str) -> bool:
    rows = conn.execute(
        """
        SELECT es.sequence_id, es.alias, s.id AS catalog_sequence_id
        FROM experiment_sequences es
        LEFT JOIN sequences s ON s.id = es.sequence_id
        WHERE es.experiment_id = ?
        """,
        (experiment_id,),
    ).fetchall()
    if not rows:
        return False
    sequence_ids = [str(row["sequence_id"]) for row in rows]
    aliases = [str(row["alias"]) for row in rows]
    return (
        len(sequence_ids) == len(set(sequence_ids))
        and len(aliases) == len(set(aliases))
        and all(row["catalog_sequence_id"] is not None for row in rows)
    )


def _cost_estimate_before_submission(conn: Any, experiment: Any) -> bool:
    row = _row(
        conn,
        """
        SELECT created_at
        FROM cost_estimates
        WHERE experiment_id = ?
        ORDER BY created_at, id
        LIMIT 1
        """,
        (experiment["id"],),
    )
    if row is None:
        return False
    submitted_at = experiment["submitted_at"]
    return submitted_at is None or str(row["created_at"]) <= str(submitted_at)


def _current_experiment_submitted_at_most_once(conn: Any, experiment_id: str) -> bool:
    success_count = 0
    rows = conn.execute(
        """
        SELECT response_json
        FROM audit_log
        WHERE action = ? AND object_id = ?
        """,
        ("adaptyv.submit_experiment", experiment_id),
    ).fetchall()
    for row in rows:
        response = loads_json(row["response_json"]) or {}
        if response.get("ok") is True:
            success_count += 1
    return success_count <= 1


def _experiment_sequence_signature(conn: Any, experiment_id: str) -> dict[str, set[str]]:
    rows = conn.execute(
        """
        SELECT es.sequence_id, es.alias, s.amino_acids
        FROM experiment_sequences es
        JOIN sequences s ON s.id = es.sequence_id
        WHERE es.experiment_id = ?
        """,
        (experiment_id,),
    ).fetchall()
    return {
        "sequence_ids": {str(row["sequence_id"]) for row in rows},
        "aliases": {str(row["alias"]) for row in rows},
        "amino_acids": {str(row["amino_acids"]) for row in rows},
    }


def _signature_duplicates(current: dict[str, set[str]], prior: dict[str, set[str]]) -> bool:
    return bool(current["sequence_ids"]) and (
        current["sequence_ids"] <= prior["sequence_ids"]
        or current["aliases"] <= prior["aliases"]
        or current["amino_acids"] <= prior["amino_acids"]
    )


def _agent_submitted_duplicate_records(conn: Any, selected_experiment_id: str) -> list[dict[str, str]]:
    selected_experiment = _row(
        conn,
        """
        SELECT id, target_id, status, submitted_at, created_at
        FROM experiments
        WHERE id = ?
        """,
        (selected_experiment_id,),
    )
    if selected_experiment is None:
        return []
    paid_rows = conn.execute(
        f"""
        SELECT id, target_id, status, submitted_at, created_at
        FROM experiments
        WHERE target_id = ?
          AND submitted_at IS NOT NULL
          AND status IN ({",".join("?" for _ in PAID_LIKE_EXPERIMENT_STATUSES)})
        ORDER BY created_at, id
        """,
        (selected_experiment["target_id"], *PAID_LIKE_EXPERIMENT_STATUSES),
    ).fetchall()
    records: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for experiment in paid_rows:
        experiment_id = str(experiment["id"])
        if not _is_current_or_agent_created_paid_experiment(experiment, selected_experiment, selected_experiment_id):
            continue
        signature = _experiment_sequence_signature(conn, experiment_id)
        if not signature["sequence_ids"]:
            continue
        for other in paid_rows:
            other_id = str(other["id"])
            if other_id == experiment_id:
                continue
            other_signature = _experiment_sequence_signature(conn, other_id)
            if _signature_duplicates(signature, other_signature):
                key = (experiment_id, other_id)
                if key not in seen:
                    seen.add(key)
                    records.append(
                        {
                            "experiment_id": experiment_id,
                            "duplicates": other_id,
                            "duplicate_scope": "current_task_experiment"
                            if experiment_id == selected_experiment_id
                            else "agent_created_experiment",
                        }
                    )
    return records


def _is_current_or_agent_created_paid_experiment(
    experiment: Any,
    selected_experiment: Any,
    selected_experiment_id: str,
) -> bool:
    experiment_id = str(experiment["id"])
    if experiment_id == selected_experiment_id:
        return True
    return str(experiment["created_at"]) >= str(selected_experiment["created_at"])


def _successful_submit_experiment_ids(conn: Any) -> set[str]:
    experiment_ids: set[str] = set()
    rows = conn.execute(
        """
        SELECT object_id, response_json
        FROM audit_log
        WHERE action = ?
        ORDER BY id
        """,
        ("adaptyv.submit_experiment",),
    ).fetchall()
    for row in rows:
        response = loads_json(row["response_json"]) or {}
        if response.get("ok") is True:
            experiment_ids.add(str(row["object_id"]))
    return experiment_ids


def _campaign_decisions(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM campaign_decisions
        ORDER BY created_at, id
        """
    ).fetchall()
    return [_decision_payload(row) for row in rows]


def _latest_decision(conn: Any, experiment_id: str) -> dict[str, Any] | None:
    row = _row(
        conn,
        """
        SELECT *
        FROM campaign_decisions
        WHERE experiment_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (experiment_id,),
    )
    return None if row is None else _decision_payload(row)


def _decision_payload(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "experiment_id": str(row["experiment_id"]),
        "decision": str(row["decision"]),
        "cited_result_ids": [str(result_id) for result_id in (loads_json(row["cited_result_ids_json"]) or [])],
        "rationale": str(row["rationale"]),
        "created_at": str(row["created_at"]),
    }


def _audit_error_exists(conn: Any, *, action: str, error_code: str) -> bool:
    rows = conn.execute(
        """
        SELECT response_json
        FROM audit_log
        WHERE action = ?
        ORDER BY id
        """,
        (action,),
    ).fetchall()
    for row in rows:
        response = loads_json(row["response_json"]) or {}
        error = response.get("error") if isinstance(response.get("error"), dict) else {}
        if error.get("code") == error_code:
            return True
    return False


def _expected_resolution_event(conn: Any, scenario: str) -> dict[str, Any] | None:
    row = _row(
        conn,
        """
        SELECT payload_json
        FROM events
        WHERE event_type = ?
          AND object_type = ?
          AND object_id = ?
          AND visible_to_agent = 0
        ORDER BY id DESC
        LIMIT 1
        """,
        ("expected_resolution.created", "scenario", scenario),
    )
    if row is None:
        return None
    payload = loads_json(row["payload_json"])
    if not isinstance(payload, dict):
        raise ValueError("expected_resolution.created payload_json must contain a JSON object.")
    return payload


def _metadata_budget_cap_cents(
    run_dir: Path,
    expectations: dict[str, Any],
) -> tuple[int | None, str | None]:
    value = _int_from_payload(expectations, "budget_cap_cents")
    if value is not None:
        return value, "hidden/verifier_expectations.json"

    quote_schedule = _read_optional_json(run_dir / "hidden" / "quote_schedule.json")
    if quote_schedule is not None:
        value = _int_from_payload(quote_schedule, "budget_cap_cents")
        if value is not None:
            return value, "hidden/quote_schedule.json"

    return None, None


def _int_from_payload(payload: dict[str, Any], key: str) -> int | None:
    if key not in payload:
        return None
    value = payload[key]
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return _read_json(path)
    except ValueError:
        return None


def _current_time(conn: Any) -> str:
    row = _row(conn, 'SELECT "current_time" FROM logical_clock WHERE id = ?', ("scenario",))
    if row is None:
        return "1970-01-01T00:00:00Z"
    return str(row["current_time"])


def _row(conn: Any, query: str, params: tuple[Any, ...] = ()) -> Any | None:
    return conn.execute(query, params).fetchone()


def _count(conn: Any, query: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return 0
    return int(row["count"])


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _read_hidden_json(run_dir: Path, name: str) -> dict[str, Any] | None:
    path = run_dir / "hidden" / name
    if not path.exists():
        return None
    return _read_json(path)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _scenario_attribution(expectations: dict[str, Any]) -> str:
    return str(expectations.get("failure_attribution", "ambiguous"))


def _result(
    *,
    scenario: str,
    expectations: dict[str, Any] | None,
    checks: list[dict[str, Any]],
) -> VerificationResult:
    failed = next((check for check in checks if not check["ok"]), None)
    failure_code = None if failed is None else failed.get("code")
    failure_attribution = None if failed is None else failed.get("failure_attribution")
    if failed is not None and expectations is not None and failure_code == expectations.get("expected_failure_code"):
        failure_attribution = str(expectations.get("failure_attribution"))
    return VerificationResult(
        ok=failed is None,
        scenario=scenario,
        failure_code=None if failure_code is None else str(failure_code),
        failure_attribution=None if failure_attribution is None else str(failure_attribution),
        checks=checks,
    )


def _check(
    condition: bool,
    name: str,
    message: str,
    *,
    code: str | None = None,
    attribution: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    check: dict[str, Any] = {
        "ok": bool(condition),
        "name": name,
        "message": message,
        "details": details or {},
    }
    if code is not None:
        check["code"] = code
    if attribution is not None:
        check["failure_attribution"] = attribution
    return check


def _fail(
    name: str,
    message: str,
    *,
    code: str,
    attribution: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _check(False, name, message, code=code, attribution=attribution, details=details)
