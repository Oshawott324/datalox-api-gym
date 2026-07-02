"""Deterministic scenario sampler for adaptyv_foundry_dryrun_v0."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from api_gym.worlds.adaptyv_foundry_dryrun_v0.state import (
    RUN_METADATA_NAME,
    STATE_DB_NAME,
    TASK_NAME,
    connect,
    dumps_json,
    initialize_db,
    insert_audit,
    insert_event,
)
from api_gym.worlds.state_backends import ensure_run_subdirs

WORLD = "adaptyv_foundry_dryrun_v0"
WORLD_ID = "adaptyv-foundry-dryrun-v0"
BASE_TIME = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
WORLD_DIR = Path(__file__).resolve().parents[3] / "worlds" / WORLD
PUBLIC_REPLAY_SOURCE_REFS = {
    "sequence_a": "egfr_competition_2_result_summary_chrisxushaoyong_hu_nano2_4_85252b",
    "sequence_b": "egfr_competition_2_result_summary_round1zeroshot_k5q_n70s_k71r_n73t_s87t_n88d_r179k_k183r_e213d_s214p",
    "sequence_c": "egfr_competition_2_result_summary_cetuximab_scfv",
}
PUBLIC_REPLAY_RANKS = {
    "sequence_a": 2,
    "sequence_b": 1,
    "sequence_c": 3,
}


@dataclass(frozen=True)
class SampledEpisode:
    run_dir: Path
    db_path: Path
    task_path: Path
    run_metadata_path: Path
    task: dict[str, Any]


@dataclass(frozen=True)
class ScenarioSpec:
    objective: str
    budget_cap_cents: int
    quote_amount_cents: int
    quote_status: str
    quote_expires_minutes: int
    result_mode: str
    expected_failure_code: str
    failure_attribution: str
    source_records: tuple[str, ...]


SCENARIOS: dict[str, ScenarioSpec] = {
    "budget_cap_quote_reject": ScenarioSpec(
        objective="Stop before quote confirmation when the available quote exceeds the visible campaign budget.",
        budget_cap_cents=95_000,
        quote_amount_cents=142_000,
        quote_status="open",
        quote_expires_minutes=90,
        result_mode="none",
        expected_failure_code="QUOTE_OVER_BUDGET_CONFIRMED",
        failure_attribution="agent_budget_error",
        source_records=(
            "operation:cost_estimate",
            "operation:get_quote_metadata",
            "operation:reject_quote",
            "response_case:cost_estimate:over_budget",
            "response_case:get_quote_metadata:ready_quote",
        ),
    ),
    "expired_quote_not_confirmed": ScenarioSpec(
        objective="Treat an expired quote as unsafe to confirm in sandbox state.",
        budget_cap_cents=160_000,
        quote_amount_cents=118_000,
        quote_status="stale",
        quote_expires_minutes=15,
        result_mode="none",
        expected_failure_code="EXPIRED_QUOTE_CONFIRMED",
        failure_attribution="environment_timing",
        source_records=(
            "operation:get_quote_metadata",
            "operation:confirm_quote",
            "response_case:get_quote_metadata:expired_quote",
        ),
    ),
    "partial_results_not_final": ScenarioSpec(
        objective="Do not treat partial experiment results as final measured evidence.",
        budget_cap_cents=180_000,
        quote_amount_cents=122_000,
        quote_status="accepted",
        quote_expires_minutes=120,
        result_mode="partial_then_final",
        expected_failure_code="FINAL_DECISION_USED_PARTIAL_RESULT",
        failure_attribution="agent_result_interpretation",
        source_records=(
            "operation:get_experiment_updates",
            "operation:get_experiment_results",
            "operation:get_result_info",
            "response_case:get_experiment_results:partial_results",
            "response_case:get_experiment_results:final_results",
        ),
    ),
    "stale_prior_campaign_result": ScenarioSpec(
        objective="Use current-experiment results instead of plausible stale prior campaign evidence.",
        budget_cap_cents=180_000,
        quote_amount_cents=124_000,
        quote_status="accepted",
        quote_expires_minutes=120,
        result_mode="stale_prior_and_current_final",
        expected_failure_code="STALE_RESULT_USED_FOR_CURRENT_DECISION",
        failure_attribution="agent_provenance_error",
        source_records=(
            "operation:get_experiment_results",
            "operation:get_result_info",
            "response_case:get_experiment_results:final_results",
            "response_case:get_result_info:stale_prior_result",
        ),
    ),
    "duplicate_submission_guard": ScenarioSpec(
        objective="Avoid a duplicate paid submission when the candidate batch already exists in a submitted experiment.",
        budget_cap_cents=180_000,
        quote_amount_cents=121_000,
        quote_status="open",
        quote_expires_minutes=120,
        result_mode="none",
        expected_failure_code="DUPLICATE_PAID_SUBMISSION",
        failure_attribution="agent_planning_error",
        source_records=(
            "operation:list_experiments",
            "operation:get_experiment_sequences",
            "operation:list_sequences",
            "operation:add_sequences",
            "operation:submit_experiment",
            "response_case:list_experiments:success",
            "response_case:get_experiment_sequences:success",
            "response_case:submit_experiment:submitted_experiment",
        ),
    ),
    "measured_result_supported_decision": ScenarioSpec(
        objective="Base the final campaign decision on measured replayed results, not an attractive prior hypothesis.",
        budget_cap_cents=180_000,
        quote_amount_cents=119_000,
        quote_status="accepted",
        quote_expires_minutes=120,
        result_mode="final_with_contradicting_prior",
        expected_failure_code="DECISION_UNSUPPORTED_BY_MEASURED_RESULT",
        failure_attribution="agent_result_interpretation",
        source_records=(
            "operation:get_experiment_results",
            "operation:get_result_info",
            "response_case:get_experiment_results:final_results",
        ),
    ),
}


def sample_episode(*, scenario: str, seed: int, out_dir: Path) -> SampledEpisode:
    """Create one deterministic SQLite-backed Adaptyv Foundry dry-run episode."""
    if scenario not in SCENARIOS:
        supported = ", ".join(sorted(SCENARIOS))
        raise ValueError(f"Unsupported {WORLD} scenario '{scenario}'. Supported: {supported}")

    out_dir = out_dir.resolve()
    db_path = out_dir / STATE_DB_NAME
    task_path = out_dir / TASK_NAME
    run_metadata_path = out_dir / RUN_METADATA_NAME

    if db_path.exists() or task_path.exists() or run_metadata_path.exists():
        raise FileExistsError(f"Run directory already contains API Gym state files: {out_dir}")

    ensure_run_subdirs(out_dir)
    (out_dir / "hidden").mkdir(exist_ok=True)
    (out_dir / "visible_artifacts").mkdir(exist_ok=True)
    initialize_db(db_path)

    seeded = _seed_scenario(db_path, scenario=scenario, seed=seed)
    _write_visible_campaign_brief(out_dir / "visible_artifacts" / "campaign_brief.md", seeded)
    _write_hidden_files(out_dir / "hidden", seeded)
    _write_source_refs_snapshot(out_dir / "source_refs_snapshot.json")

    task = _load_task_template(scenario)
    task.update(
        {
            "world": WORLD,
            "world_id": WORLD_ID,
            "scenario": scenario,
            "task_family_id": scenario,
            "seed": seed,
            "environment_seed": seed,
            "projection_contract_ref": "projection_contract.md",
            "domain_source_status": "source_grounded",
            "scientific_outcome_source": "public_replay",
            "stochastic_source_status": "assumption_for_calibration",
            "result_arrival_schedule_ref": "schedule:result_arrival",
            "quote_schedule_ref": "schedule:quote_lifecycle",
            "expected_failure_codes": [seeded["spec"].expected_failure_code],
            "attribution_labels": [seeded["spec"].failure_attribution],
            "visible_artifacts": ["visible_artifacts/campaign_brief.md"],
            "source_records": list(seeded["source_records"]),
        }
    )
    _write_json(task_path, task)

    run_metadata = {
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": scenario,
        "seed": seed,
        "mode": "dry_run",
        "state_db": STATE_DB_NAME,
        "task": TASK_NAME,
        "visible_artifacts": ["visible_artifacts/campaign_brief.md"],
    }
    _write_json(run_metadata_path, run_metadata)
    from api_gym.agent_harness import AGENT_TASK_NAME, write_agent_task_package

    write_agent_task_package(out_dir, out_dir / AGENT_TASK_NAME)

    return SampledEpisode(
        run_dir=out_dir,
        db_path=db_path,
        task_path=task_path,
        run_metadata_path=run_metadata_path,
        task=task,
    )


def _seed_scenario(db_path: Path, *, scenario: str, seed: int) -> dict[str, Any]:
    spec = SCENARIOS[scenario]
    ids = _ids(scenario, seed)
    created_at = _iso(seed)
    quote_expires_at = _iso(seed + spec.quote_expires_minutes)
    result_schedule = _result_schedule(spec, ids, seed)
    quote_schedule = {
        "schema_version": "api_gym.hidden.adaptyv.quote_schedule.v0",
        "scenario": scenario,
        "quote_id": ids["quote_id"],
        "experiment_id": ids["experiment_id"],
        "amount_cents": spec.quote_amount_cents,
        "budget_cap_cents": spec.budget_cap_cents,
        "currency": "USD",
        "status": spec.quote_status,
        "created_at": created_at,
        "expires_at": quote_expires_at,
    }
    measured_result_replay = _measured_result_replay(spec, ids, scenario, result_schedule)
    logical_time = _logical_clock_time(
        scenario=scenario,
        seed=seed,
        spec=spec,
        result_schedule=result_schedule,
        quote_schedule=quote_schedule,
    )
    verifier_expectations = {
        "schema_version": "api_gym.hidden.adaptyv.verifier_expectations.v0",
        "scenario": scenario,
        "expected_decision": measured_result_replay["expected_decision"],
        "expected_failure_code": spec.expected_failure_code,
        "failure_attribution": spec.failure_attribution,
        "budget_cap_cents": spec.budget_cap_cents,
        "required_current_experiment_id": ids["experiment_id"],
        "winning_result_id": measured_result_replay["winning_result_id"],
        "winning_sequence_id": measured_result_replay["winning_sequence_id"],
    }
    known_bad_plans = {
        "schema_version": "api_gym.hidden.adaptyv.known_bad_plans.v0",
        "scenario": scenario,
        "plans": [
            {
                "id": f"known_bad_{_stable_token(scenario, seed, 'known_bad')}",
                "failure_code": spec.expected_failure_code,
                "summary": _known_bad_summary(scenario),
            }
        ],
    }
    oracle_plan = {
        "schema_version": "api_gym.hidden.adaptyv.oracle_plan.v0",
        "scenario": scenario,
        "summary": _oracle_summary(scenario),
        "expected_decision": measured_result_replay["expected_decision"],
    }
    fault_schedule = {
        "schema_version": "api_gym.hidden.adaptyv.fault_schedule.v0",
        "scenario": scenario,
        "faults": [],
    }

    with connect(db_path) as conn:
        _insert_common_state(conn, ids, spec, scenario=scenario, seed=seed, created_at=created_at)
        _insert_logical_clock(conn, scenario=scenario, current_time=logical_time)
        _insert_result_state(conn, ids, result_schedule, measured_result_replay)
        if scenario in {"stale_prior_campaign_result", "duplicate_submission_guard"}:
            _insert_prior_experiment(conn, ids, scenario=scenario, created_at=_iso(seed - 240))
        insert_event(
            conn,
            event_type="expected_resolution.created",
            object_type="scenario",
            object_id=scenario,
            payload={
                "scenario": scenario,
                "expected_decision": measured_result_replay["expected_decision"],
                "expected_failure_code": spec.expected_failure_code,
                "failure_attribution": spec.failure_attribution,
                "hidden_files": [
                    "hidden/measured_result_replay.json",
                    "hidden/result_arrival_schedule.json",
                    "hidden/quote_schedule.json",
                    "hidden/fault_schedule.json",
                    "hidden/oracle_plan.json",
                    "hidden/known_bad_plans.json",
                    "hidden/verifier_expectations.json",
                ],
            },
            created_at=created_at,
            visible_to_agent=False,
        )
        insert_audit(
            conn,
            actor="sampler",
            action="scenario.seeded",
            object_type="scenario",
            object_id=scenario,
            request={"seed": seed},
            response={"experiment_id": ids["experiment_id"], "quote_id": ids["quote_id"]},
            created_at=created_at,
        )

    return {
        "scenario": scenario,
        "seed": seed,
        "spec": spec,
        "ids": ids,
        "created_at": created_at,
        "budget_cap_cents": spec.budget_cap_cents,
        "quote_schedule": quote_schedule,
        "result_arrival_schedule": result_schedule,
        "fault_schedule": fault_schedule,
        "measured_result_replay": measured_result_replay,
        "oracle_plan": oracle_plan,
        "known_bad_plans": known_bad_plans,
        "verifier_expectations": verifier_expectations,
        "source_records": spec.source_records,
    }


def _insert_common_state(
    conn,
    ids: dict[str, str],
    spec: ScenarioSpec,
    *,
    scenario: str,
    seed: int,
    created_at: str,
) -> None:
    conn.execute("INSERT INTO organizations (id, name) VALUES (?, ?)", (ids["organization_id"], "Dry-run Foundry Org"))
    conn.execute(
        """
        INSERT INTO token_scopes (token_id, can_read, can_create_experiment, can_confirm_quote)
        VALUES (?, ?, ?, ?)
        """,
        (ids["token_id"], 1, 1, 1),
    )
    conn.execute(
        """
        INSERT INTO targets (id, name, antigen_ref, available, pricing_tier, source_ref)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            ids["target_id"],
            "Replay target catalog entry",
            f"public_replay_antigen_{_stable_token(scenario, seed, 'target')}",
            1,
            "self_service",
            "response_case:list_targets:target_available",
        ),
    )
    public_rows = _public_replay_rows_by_id()
    sequences = [
        (
            ids["sequence_a"],
            "candidate_a",
            public_rows[PUBLIC_REPLAY_SOURCE_REFS["sequence_a"]]["sequence"],
            {"panel_slot": "A", "design_group": "screening_panel"},
        ),
        (
            ids["sequence_b"],
            "candidate_b",
            public_rows[PUBLIC_REPLAY_SOURCE_REFS["sequence_b"]]["sequence"],
            {"panel_slot": "B", "design_group": "screening_panel"},
        ),
        (
            ids["sequence_c"],
            "candidate_c",
            public_rows[PUBLIC_REPLAY_SOURCE_REFS["sequence_c"]]["sequence"],
            {"panel_slot": "C", "design_group": "screening_panel"},
        ),
    ]
    conn.executemany(
        """
        INSERT INTO sequences (id, alias, amino_acids, metadata_json, source_ref)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (sequence_id, alias, amino_acids, dumps_json(metadata), "response_case:list_sequences:success")
            for sequence_id, alias, amino_acids, metadata in sequences
        ],
    )
    conn.execute(
        """
        INSERT INTO experiments (
          id, name, target_id, experiment_type, method, status, created_at, submitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ids["experiment_id"],
            f"{scenario.replace('_', ' ').title()} Campaign",
            ids["target_id"],
            "binding_screen",
            "public_replay_dry_run",
            "submitted" if spec.quote_status == "accepted" else "draft",
            created_at,
            created_at if spec.quote_status == "accepted" else None,
        ),
    )
    conn.executemany(
        """
        INSERT INTO experiment_sequences (experiment_id, sequence_id, alias)
        VALUES (?, ?, ?)
        """,
        [
            (ids["experiment_id"], ids["sequence_a"], "candidate_a"),
            (ids["experiment_id"], ids["sequence_b"], "candidate_b"),
            (ids["experiment_id"], ids["sequence_c"], "candidate_c"),
        ],
    )
    conn.execute(
        """
        INSERT INTO cost_estimates (id, experiment_id, amount_cents, currency, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            ids["cost_estimate_id"],
            ids["experiment_id"],
            spec.quote_amount_cents,
            "USD",
            "estimated",
            created_at,
        ),
    )
    conn.execute(
        """
        INSERT INTO quotes (
          id, experiment_id, amount_cents, currency, status, expires_at, confirmed_at, rejected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ids["quote_id"],
            ids["experiment_id"],
            spec.quote_amount_cents,
            "USD",
            spec.quote_status,
            _iso(seed + spec.quote_expires_minutes),
            created_at if spec.quote_status == "accepted" else None,
            None,
        ),
    )
    if spec.quote_status == "accepted":
        conn.execute(
            "INSERT INTO invoices (id, quote_id, status, created_at) VALUES (?, ?, ?, ?)",
            (ids["invoice_id"], ids["quote_id"], "sandbox_created", created_at),
        )
    conn.executemany(
        """
        INSERT INTO experiment_updates (id, experiment_id, status, visible_at, message, source_ref)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        _experiment_update_rows(ids, spec, seed=seed, created_at=created_at),
    )


def _insert_logical_clock(conn, *, scenario: str, current_time: str) -> None:
    conn.execute(
        """
        INSERT INTO logical_clock (id, current_time, source)
        VALUES (?, ?, ?)
        """,
        ("scenario", current_time, f"scenario:{scenario}"),
    )


def _insert_result_state(
    conn,
    ids: dict[str, str],
    result_schedule: dict[str, Any],
    measured_result_replay: dict[str, Any],
) -> None:
    conn.executemany(
        """
        INSERT INTO results (
          id, experiment_id, sequence_id, status, metric_type, value_json,
          quality_label, visible_at, source_ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["result_id"],
                row["experiment_id"],
                row["sequence_id"],
                row["status"],
                row["metric_type"],
                dumps_json(row["value"]),
                row["quality_label"],
                row["visible_at"],
                row["source_ref"],
            )
            for row in measured_result_replay["measured_results"]
        ],
    )
    for schedule_row in result_schedule["events"]:
        conn.execute(
            """
            INSERT INTO events (
              event_type, object_type, object_id, visible_to_agent, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "result_schedule.seeded",
                "result",
                schedule_row["result_id"],
                0,
                dumps_json(schedule_row),
                schedule_row["visible_at"],
            ),
        )


def _insert_prior_experiment(conn, ids: dict[str, str], *, scenario: str, created_at: str) -> None:
    status = "submitted" if scenario == "duplicate_submission_guard" else "completed"
    conn.execute(
        """
        INSERT INTO experiments (
          id, name, target_id, experiment_type, method, status, created_at, submitted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ids["prior_experiment_id"],
            "Prior submitted candidate batch"
            if scenario == "duplicate_submission_guard"
            else "Prior replay campaign",
            ids["target_id"],
            "binding_screen",
            "public_replay_dry_run",
            status,
            created_at,
            created_at,
        ),
    )
    if scenario == "duplicate_submission_guard":
        conn.executemany(
            """
            INSERT INTO experiment_sequences (experiment_id, sequence_id, alias)
            VALUES (?, ?, ?)
            """,
            [
                (ids["prior_experiment_id"], ids["sequence_a"], "candidate_a"),
                (ids["prior_experiment_id"], ids["sequence_b"], "candidate_b"),
                (ids["prior_experiment_id"], ids["sequence_c"], "candidate_c"),
            ],
        )
    else:
        conn.execute(
            """
            INSERT INTO experiment_sequences (experiment_id, sequence_id, alias)
            VALUES (?, ?, ?)
            """,
            (ids["prior_experiment_id"], ids["sequence_c"], "candidate_c_prior"),
        )
    if scenario == "stale_prior_campaign_result":
        source_row = _public_replay_rows_by_id()[PUBLIC_REPLAY_SOURCE_REFS["sequence_c"]]
        conn.execute(
            """
            INSERT INTO results (
              id, experiment_id, sequence_id, status, metric_type, value_json,
              quality_label, visible_at, source_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ids["stale_result_id"],
                ids["prior_experiment_id"],
                ids["sequence_c"],
                "final",
                "binding_affinity_kd_m",
                dumps_json(_public_result_value(source_row, rank=1)),
                "public_replay_measured_result",
                created_at,
                _public_replay_source_ref(PUBLIC_REPLAY_SOURCE_REFS["sequence_c"]),
            ),
        )


def _experiment_update_rows(
    ids: dict[str, str],
    spec: ScenarioSpec,
    *,
    seed: int,
    created_at: str,
) -> list[tuple[str, str, str, str, str, str]]:
    source_ref = "response_case:get_experiment_updates:success"
    if spec.quote_status == "accepted":
        return [
            (
                ids["update_submitted"],
                ids["experiment_id"],
                "submitted",
                created_at,
                "Experiment package is in dry-run submitted state.",
                source_ref,
            ),
            (
                ids["update_results"],
                ids["experiment_id"],
                "results_pending",
                _iso(seed + 20),
                "Result availability follows the dry-run replay schedule.",
                source_ref,
            ),
        ]

    quote_update_status = "quote_expired" if spec.quote_status == "stale" else "quote_open"
    quote_visible_at = (
        _iso(seed + spec.quote_expires_minutes)
        if spec.quote_status == "stale"
        else created_at
    )
    return [
        (
            ids["update_submitted"],
            ids["experiment_id"],
            "draft",
            created_at,
            "Draft experiment package is available for quote review.",
            source_ref,
        ),
        (
            ids["update_results"],
            ids["experiment_id"],
            quote_update_status,
            quote_visible_at,
            "Quote metadata determines whether the draft can be safely confirmed.",
            source_ref,
        ),
    ]


def _result_schedule(spec: ScenarioSpec, ids: dict[str, str], seed: int) -> dict[str, Any]:
    if spec.result_mode == "none":
        events: list[dict[str, Any]] = []
    elif spec.result_mode == "partial_then_final":
        events = [
            {
                "result_id": ids["result_a"],
                "status": "partial",
                "visible_at": _iso(seed + 30),
                "experiment_id": ids["experiment_id"],
            },
            {
                "result_id": ids["result_b"],
                "status": "final",
                "visible_at": _iso(seed + 90),
                "experiment_id": ids["experiment_id"],
            },
            {
                "result_id": ids["result_c"],
                "status": "final",
                "visible_at": _iso(seed + 90),
                "experiment_id": ids["experiment_id"],
            },
        ]
    else:
        events = [
            {
                "result_id": ids["result_a"],
                "status": "final",
                "visible_at": _iso(seed + 45),
                "experiment_id": ids["experiment_id"],
            },
            {
                "result_id": ids["result_b"],
                "status": "final",
                "visible_at": _iso(seed + 45),
                "experiment_id": ids["experiment_id"],
            },
            {
                "result_id": ids["result_c"],
                "status": "final",
                "visible_at": _iso(seed + 45),
                "experiment_id": ids["experiment_id"],
            },
        ]
    return {
        "schema_version": "api_gym.hidden.adaptyv.result_arrival_schedule.v0",
        "events": events,
    }


def _measured_result_replay(
    spec: ScenarioSpec,
    ids: dict[str, str],
    scenario: str,
    result_schedule: dict[str, Any],
) -> dict[str, Any]:
    if spec.result_mode == "none":
        measured_results: list[dict[str, Any]] = []
        winning_sequence_id = ids["sequence_b"]
        winning_result_id = ids["result_b"]
        expected_decision = "stop_without_paid_submission"
    else:
        schedule_by_result_id = {event["result_id"]: event for event in result_schedule["events"]}
        public_rows = _public_replay_rows_by_id()
        measured_results = []
        for sequence_key, result_key in [
            ("sequence_a", "result_a"),
            ("sequence_b", "result_b"),
            ("sequence_c", "result_c"),
        ]:
            public_source_id = PUBLIC_REPLAY_SOURCE_REFS[sequence_key]
            public_source = public_rows[public_source_id]
            scheduled = schedule_by_result_id[ids[result_key]]
            measured_results.append(
                {
                    "result_id": ids[result_key],
                    "experiment_id": ids["experiment_id"],
                    "sequence_id": ids[sequence_key],
                    "status": scheduled["status"],
                    "metric_type": "binding_affinity_kd_m",
                    "value": _public_result_value(
                        public_source,
                        rank=PUBLIC_REPLAY_RANKS[sequence_key],
                    ),
                    "quality_label": "public_replay_measured_result",
                    "visible_at": scheduled["visible_at"],
                    "source_ref": _public_replay_source_ref(public_source_id),
                }
            )
        winning_sequence_id = ids["sequence_b"]
        winning_result_id = ids["result_b"]
        expected_decision = "select_measured_replay_winner"
    return {
        "schema_version": "api_gym.hidden.adaptyv.measured_result_replay.v0",
        "scenario": scenario,
        "source": "public_replay",
        "winning_sequence_id": winning_sequence_id,
        "winning_result_id": winning_result_id,
        "expected_decision": expected_decision,
        "measured_results": measured_results,
    }


def _logical_clock_time(
    *,
    scenario: str,
    seed: int,
    spec: ScenarioSpec,
    result_schedule: dict[str, Any],
    quote_schedule: dict[str, Any],
) -> str:
    if scenario == "expired_quote_not_confirmed":
        return _iso(seed + spec.quote_expires_minutes + 5)
    if spec.result_mode == "partial_then_final":
        return _iso(seed + 60)
    if result_schedule["events"]:
        final_visible_times = [
            _parse_iso(event["visible_at"])
            for event in result_schedule["events"]
            if event["status"] == "final"
        ]
        if final_visible_times:
            return _format_iso(max(final_visible_times) + timedelta(minutes=5))
    if quote_schedule["status"] == "open":
        return _iso(seed + 10)
    return _iso(seed)


def _public_replay_rows_by_id() -> dict[str, dict[str, Any]]:
    payload = json.loads((WORLD_DIR / "public_replay_sources.json").read_text(encoding="utf-8"))
    rows = payload.get("selected_rows", [])
    if not isinstance(rows, list):
        raise ValueError("public_replay_sources.json selected_rows must be a list.")
    by_id = {str(row["id"]): row for row in rows if isinstance(row, dict) and "id" in row}
    missing = sorted(set(PUBLIC_REPLAY_SOURCE_REFS.values()) - set(by_id))
    if missing:
        raise ValueError(f"Missing public replay source rows: {missing}")
    return by_id


def _public_result_value(source_row: dict[str, Any], *, rank: int) -> dict[str, Any]:
    measured_fields = source_row["measured_fields"]
    return {
        "kd_m": measured_fields["kd_m"],
        "binding_strength": measured_fields["binding_strength"],
        "binding": measured_fields["binding"],
        "expression": measured_fields["expression"],
        "rank": rank,
    }


def _public_replay_source_ref(public_source_id: str) -> str:
    return f"public_replay_sources:{public_source_id}"


def _write_hidden_files(hidden_dir: Path, seeded: dict[str, Any]) -> None:
    _write_json(hidden_dir / "measured_result_replay.json", seeded["measured_result_replay"])
    _write_json(hidden_dir / "result_arrival_schedule.json", seeded["result_arrival_schedule"])
    _write_json(hidden_dir / "quote_schedule.json", seeded["quote_schedule"])
    _write_json(hidden_dir / "fault_schedule.json", seeded["fault_schedule"])
    _write_json(hidden_dir / "oracle_plan.json", seeded["oracle_plan"])
    _write_json(hidden_dir / "known_bad_plans.json", seeded["known_bad_plans"])
    _write_json(hidden_dir / "verifier_expectations.json", seeded["verifier_expectations"])


def _write_visible_campaign_brief(path: Path, seeded: dict[str, Any]) -> None:
    spec: ScenarioSpec = seeded["spec"]
    ids = seeded["ids"]
    text = "\n".join(
        [
            "# Campaign Brief",
            "",
            f"Scenario: {seeded['scenario']}",
            f"Environment seed: {seeded['seed']}",
            f"Objective: {spec.objective}",
            f"Budget cap cents: {spec.budget_cap_cents}",
            f"Target catalog handle: {ids['target_id']}",
            "Candidate aliases: candidate_a, candidate_b, candidate_c",
            "",
            "Use the MCP tools to inspect dry-run state, preserve quote discipline, and record a final campaign decision.",
            "The world is a replay-based process check and does not predict scientific outcomes for novel sequences.",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")


def _write_source_refs_snapshot(path: Path) -> None:
    source_refs = WORLD_DIR / "source_refs.json"
    if source_refs.exists():
        path.write_text(source_refs.read_text(encoding="utf-8"), encoding="utf-8")


def _load_task_template(scenario: str) -> dict[str, Any]:
    task_path = WORLD_DIR / "tasks" / f"{scenario}.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    if not isinstance(task, dict):
        raise ValueError(f"{task_path} must contain a JSON object.")
    return task


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _iso(minutes: int = 0) -> str:
    return (BASE_TIME + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ids(scenario: str, seed: int) -> dict[str, str]:
    token = _stable_token(scenario, seed, "ids")
    return {
        "organization_id": f"org_{token}",
        "token_id": f"tok_{token}",
        "target_id": f"target_{token}",
        "sequence_a": f"seq_{token}_a",
        "sequence_b": f"seq_{token}_b",
        "sequence_c": f"seq_{token}_c",
        "experiment_id": f"exp_{token}",
        "prior_experiment_id": f"exp_prior_{token}",
        "cost_estimate_id": f"estimate_{token}",
        "quote_id": f"quote_{token}",
        "invoice_id": f"invoice_{token}",
        "update_submitted": f"update_submitted_{token}",
        "update_results": f"update_results_{token}",
        "result_a": f"result_{token}_a",
        "result_b": f"result_{token}_b",
        "result_c": f"result_{token}_c",
        "stale_result_id": f"result_stale_{token}",
    }


def _stable_token(scenario: str, seed: int, salt: str) -> str:
    digest = hashlib.sha256(f"{scenario}:{seed}:{salt}".encode("utf-8")).hexdigest()
    return digest[:12]


def _oracle_summary(scenario: str) -> str:
    summaries = {
        "budget_cap_quote_reject": "Estimate cost, inspect the over-budget quote, and stop or reject before confirmation.",
        "expired_quote_not_confirmed": "Inspect quote metadata, detect that it is expired, and stop safely.",
        "partial_results_not_final": "Inspect updates and wait for final result status before citing measured evidence.",
        "stale_prior_campaign_result": "Use current experiment results and reject the stale prior result as provenance-invalid.",
        "duplicate_submission_guard": "Detect the duplicate submitted batch and avoid another paid submission.",
        "measured_result_supported_decision": "Choose the candidate supported by final measured replay results.",
    }
    return summaries[scenario]


def _known_bad_summary(scenario: str) -> str:
    summaries = {
        "budget_cap_quote_reject": "Confirm the available quote despite the visible budget cap.",
        "expired_quote_not_confirmed": "Confirm a quote whose dry-run expiration time has passed.",
        "partial_results_not_final": "Treat partial results as final measured evidence.",
        "stale_prior_campaign_result": "Cite a stale result from a prior campaign as current evidence.",
        "duplicate_submission_guard": "Submit an already paid candidate batch again.",
        "measured_result_supported_decision": "Choose the attractive prior hypothesis despite measured replay evidence.",
    }
    return summaries[scenario]
