from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from api_gym.cli import app
from api_gym.worlds.registry import get_world_runtime
from api_gym.worlds.source_refs import validate_world_source_refs


WORLD = "adaptyv_foundry_dryrun_v0"
WORLD_ID = "adaptyv-foundry-dryrun-v0"
SCENARIOS = {
    "budget_cap_quote_reject",
    "expired_quote_not_confirmed",
    "partial_results_not_final",
    "stale_prior_campaign_result",
    "duplicate_submission_guard",
    "measured_result_supported_decision",
}
REQUIRED_TABLES = {
    "organizations",
    "token_scopes",
    "targets",
    "sequences",
    "experiments",
    "experiment_sequences",
    "cost_estimates",
    "quotes",
    "invoices",
    "experiment_updates",
    "results",
    "campaign_decisions",
    "live_boundary_events",
    "logical_clock",
    "events",
    "audit_log",
}
EXPECTED_TOOL_NAMES = [
    "whoami",
    "list_experiments",
    "list_targets",
    "get_target",
    "list_sequences",
    "get_sequence",
    "create_experiment",
    "add_sequences_to_experiment",
    "estimate_experiment_cost",
    "submit_experiment",
    "get_experiment",
    "list_experiment_sequences",
    "list_experiment_updates",
    "get_experiment_quote",
    "confirm_quote",
    "reject_quote",
    "list_experiment_results",
    "get_result",
    "submit_campaign_decision",
]
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
SELECTED_PUBLIC_REPLAY_ROWS = {
    "round1zeroshot.K5Q_N70S_K71R_N73T_S87T_N88D_R179K_K183R_E213D_S214P": {
        "kd": 1.2071528940932701e-09,
        "sequence": (
            "QVQLQQSGPGLVQPSQSLSITCTVSGFSLTNYGVHWVRQSPGKGLEWLGVIWSGGNTDYNTPFTSRLSISRDTSKSQVFFKMNSLQT"
            "DDTAIYYCARALTYYDYEFAYWGQGTLVTVSAGGGGSGGGGSGGGGSDILLTQSPVILSVSPGERVSFSCRASQSIGTNIHWYQQRT"
            "NGSPKLLIRYASESISGIPSRFSGSGSGTDFTLSINSVDPEDIADYYCQQNNNWPTTFGAGTKLELK"
        ),
    },
    "chrisxushaoyong.hu_nano2_4_85252b": {
        "kd": 5.18304085902218e-09,
        "sequence": "EVQLLESGGGVVKPGGSLRLSCAASGRTFSSYAMGWFRQAPGKGLEWVSAINWSSGSTYYADSVKGRFTISRDDAKNSLYLQMNSLRAEDTAVYYCAAGYQINSGNYNFKDYEYDYWGQGTLVTVSS",
    },
    "Cetuximab_scFv": {
        "kd": 6.6383453503563e-09,
        "sequence": (
            "QVQLKQSGPGLVQPSQSLSITCTVSGFSLTNYGVHWVRQSPGKGLEWLGVIWSGGNTDYNTPFTSRLSINKDNSKSQVFFKMNSLQSN"
            "DTAIYYCARALTYYDYEFAYWGQGTLVTVSAGGGGSGGGGSGGGGSDILLTQSPVILSVSPGERVSFSCRASQSIGTNIHWYQQRTNGS"
            "PRLLIKYASESISGIPSRFSGSGSGTDFTLSINSVESEDIADYYCQQNNNWPTTFGAGTKLELK"
        ),
    },
}


def test_adaptyv_foundry_runtime_registers_mcp_only_world() -> None:
    runtime = get_world_runtime(WORLD)

    assert runtime.world_id == WORLD_ID
    assert runtime.scenarios == SCENARIOS
    assert runtime.create_http_app is None
    assert runtime.http_surface == "not_available"


def test_adaptyv_foundry_runtime_tool_names_equal_spec_catalog() -> None:
    runtime = get_world_runtime(WORLD)
    spec = _read_json(Path(__file__).resolve().parents[1] / "worlds" / WORLD / "spec.json")

    assert spec["tools"] == EXPECTED_TOOL_NAMES
    assert _runtime_tool_names(runtime) == EXPECTED_TOOL_NAMES
    assert runtime.tool_definitions


def test_adaptyv_foundry_session_create_check_tools_exposes_spec_catalog(tmp_path: Path) -> None:
    run_dir = tmp_path / "session"
    runner = CliRunner()

    created = runner.invoke(
        app,
        [
            "session",
            "create",
            "--world",
            WORLD,
            "--scenario",
            "partial_results_not_final",
            "--seed",
            "1",
            "--out",
            str(run_dir),
            "--json",
        ],
    )

    assert created.exit_code == 0, created.output
    manifest = json.loads(created.output)
    assert manifest["expected_tools"] == sorted(EXPECTED_TOOL_NAMES)

    checked = runner.invoke(app, ["session", "check-tools", "--run", str(run_dir)])

    assert checked.exit_code == 0, checked.output
    check_payload = json.loads(checked.output)
    assert check_payload == {
        "ok": True,
        "world": WORLD,
        "expected_tools": sorted(EXPECTED_TOOL_NAMES),
        "listed_tools": sorted(EXPECTED_TOOL_NAMES),
        "missing_tools": [],
        "unexpected_tools": [],
    }


def test_adaptyv_foundry_sampler_writes_run_task_and_sqlite(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=1,
        out_dir=tmp_path / "run",
    )

    assert episode.run_dir == (tmp_path / "run").resolve()
    assert (episode.run_dir / "run.json").is_file()
    assert (episode.run_dir / "task.json").is_file()
    assert (episode.run_dir / "agent_task.json").is_file()
    assert (episode.run_dir / "state.sqlite").is_file()
    assert (episode.run_dir / "visible_artifacts" / "campaign_brief.md").is_file()
    assert (episode.run_dir / "hidden" / "measured_result_replay.json").is_file()
    assert (episode.run_dir / "hidden" / "result_arrival_schedule.json").is_file()
    assert (episode.run_dir / "hidden" / "quote_schedule.json").is_file()
    assert (episode.run_dir / "hidden" / "fault_schedule.json").is_file()
    assert (episode.run_dir / "hidden" / "oracle_plan.json").is_file()
    assert (episode.run_dir / "hidden" / "known_bad_plans.json").is_file()
    assert (episode.run_dir / "hidden" / "verifier_expectations.json").is_file()

    run = _read_json(episode.run_dir / "run.json")
    task = _read_json(episode.run_dir / "task.json")
    assert run["world"] == WORLD
    assert run["world_id"] == WORLD_ID
    assert run["scenario"] == "partial_results_not_final"
    assert run["seed"] == 1
    assert run["state_db"] == "state.sqlite"
    assert task == episode.task


def test_sampled_task_includes_projection_metadata(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=1,
        out_dir=tmp_path / "run",
    )

    task = _read_json(episode.run_dir / "task.json")

    assert task["world"] == WORLD
    assert task["world_id"] == WORLD_ID
    assert task["task_family_id"] == "partial_results_not_final"
    assert task["environment_seed"] == 1
    assert task["projection_contract_ref"] == "projection_contract.md"
    assert task["domain_source_status"] == "source_grounded"
    assert task["scientific_outcome_source"] == "public_replay"
    assert task["stochastic_source_status"] == "assumption_for_calibration"
    assert task["result_arrival_schedule_ref"] == "schedule:result_arrival"
    assert task["quote_schedule_ref"] == "schedule:quote_lifecycle"
    assert task["expected_failure_codes"] == ["FINAL_DECISION_USED_PARTIAL_RESULT"]
    assert task["attribution_labels"] == ["agent_result_interpretation"]


def test_sampled_agent_visible_task_omits_hidden_resolution_data(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=1,
        out_dir=tmp_path / "run",
    )

    visible_payloads: list[dict[str, Any]] = [_read_json(episode.run_dir / "task.json")]
    agent_task = episode.run_dir / "agent_task.json"
    assert agent_task.is_file()
    visible_payloads.append(_read_json(agent_task))
    visible_text = json.dumps(visible_payloads, sort_keys=True)

    measured = _read_json(episode.run_dir / "hidden" / "measured_result_replay.json")
    verifier_expectations = _read_json(episode.run_dir / "hidden" / "verifier_expectations.json")
    known_bad = _read_json(episode.run_dir / "hidden" / "known_bad_plans.json")

    forbidden_literals = {
        "oracle_plan",
        "known_bad_plans",
        "verifier_expectations",
        str(measured["winning_sequence_id"]),
        str(measured["winning_result_id"]),
        str(verifier_expectations["expected_decision"]),
        str(known_bad["plans"][0]["summary"]),
    }
    for row_name, row in SELECTED_PUBLIC_REPLAY_ROWS.items():
        forbidden_literals.add(row_name)
        forbidden_literals.add(str(row["kd"]))
    forbidden_literals.update(AGENT_VISIBLE_FORBIDDEN_HIDDEN_TOKENS)
    for literal in forbidden_literals:
        assert literal not in visible_text


def test_sampled_state_sqlite_has_required_tables(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=1,
        out_dir=tmp_path / "run",
    )

    with sqlite3.connect(episode.run_dir / "state.sqlite") as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    assert REQUIRED_TABLES <= {row[0] for row in rows}


def test_sampled_state_logical_clock_is_seeded_from_scenario(tmp_path: Path) -> None:
    runtime = get_world_runtime(WORLD)

    expired = runtime.sample_episode(
        scenario="expired_quote_not_confirmed",
        seed=7,
        out_dir=tmp_path / "expired",
    )
    partial = runtime.sample_episode(
        scenario="partial_results_not_final",
        seed=7,
        out_dir=tmp_path / "partial",
    )
    final = runtime.sample_episode(
        scenario="measured_result_supported_decision",
        seed=7,
        out_dir=tmp_path / "final",
    )

    expired_clock = _single_logical_clock(expired.run_dir / "state.sqlite")
    expired_quote = _read_json(expired.run_dir / "hidden" / "quote_schedule.json")
    assert expired_clock["id"] == "scenario"
    assert expired_clock["source"] == "scenario:expired_quote_not_confirmed"
    assert _parse_z(expired_clock["current_time"]) > _parse_z(expired_quote["expires_at"])
    assert (
        _parse_z(expired_quote["created_at"])
        < _parse_z(expired_quote["expires_at"])
        < _parse_z(expired_clock["current_time"])
    )

    partial_clock = _single_logical_clock(partial.run_dir / "state.sqlite")
    partial_schedule = _read_json(partial.run_dir / "hidden" / "result_arrival_schedule.json")
    partial_times = {
        event["status"]: _parse_z(event["visible_at"]) for event in partial_schedule["events"]
    }
    assert partial_clock["id"] == "scenario"
    assert partial_clock["source"] == "scenario:partial_results_not_final"
    assert partial_times["partial"] < _parse_z(partial_clock["current_time"]) < partial_times["final"]

    final_clock = _single_logical_clock(final.run_dir / "state.sqlite")
    final_schedule = _read_json(final.run_dir / "hidden" / "result_arrival_schedule.json")
    final_visible_times = [_parse_z(event["visible_at"]) for event in final_schedule["events"]]
    assert final_clock["id"] == "scenario"
    assert final_clock["source"] == "scenario:measured_result_supported_decision"
    assert _parse_z(final_clock["current_time"]) > max(final_visible_times)


def test_result_rows_match_hidden_schedule_for_non_default_seed(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=7,
        out_dir=tmp_path / "run",
    )

    schedule = _read_json(episode.run_dir / "hidden" / "result_arrival_schedule.json")
    schedule_by_result_id = {event["result_id"]: event for event in schedule["events"]}
    measured = _read_json(episode.run_dir / "hidden" / "measured_result_replay.json")
    measured_result_ids = {row["result_id"] for row in measured["measured_results"]}

    with sqlite3.connect(episode.run_dir / "state.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, status, visible_at FROM results ORDER BY id").fetchall()

    assert rows
    assert measured_result_ids <= set(schedule_by_result_id)
    for row in rows:
        scheduled = schedule_by_result_id[row["id"]]
        assert row["status"] == scheduled["status"]
        assert row["visible_at"] == scheduled["visible_at"]


def test_draft_scenarios_do_not_seed_submitted_updates(tmp_path: Path) -> None:
    runtime = get_world_runtime(WORLD)
    draft_scenarios = {
        "budget_cap_quote_reject",
        "expired_quote_not_confirmed",
        "duplicate_submission_guard",
    }

    for scenario in draft_scenarios:
        episode = runtime.sample_episode(
            scenario=scenario,
            seed=11,
            out_dir=tmp_path / scenario,
        )
        quote_schedule = _read_json(episode.run_dir / "hidden" / "quote_schedule.json")

        with sqlite3.connect(episode.run_dir / "state.sqlite") as conn:
            conn.row_factory = sqlite3.Row
            experiment = conn.execute(
                "SELECT id, status FROM experiments WHERE id = ?",
                (quote_schedule["experiment_id"],),
            ).fetchone()
            update_statuses = {
                row["status"]
                for row in conn.execute(
                    "SELECT status FROM experiment_updates WHERE experiment_id = ?",
                    (quote_schedule["experiment_id"],),
                )
            }

        assert experiment is not None
        assert experiment["status"] == "draft"
        assert "submitted" not in update_statuses
        assert "results_pending" not in update_statuses


def test_adaptyv_foundry_read_tools_expose_seeded_catalog_state(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="measured_result_supported_decision",
        seed=3,
        out_dir=tmp_path / "run",
    )

    targets = _tool_ok(episode.db_path, "list_targets", {})["targets"]
    assert len(targets) == 1
    target = _tool_ok(episode.db_path, "get_target", {"target_id": targets[0]["id"]})
    assert target == targets[0]

    sequences = _tool_ok(episode.db_path, "list_sequences", {})["sequences"]
    assert {row["alias"] for row in sequences} == {"candidate_a", "candidate_b", "candidate_c"}
    sequence = _tool_ok(episode.db_path, "get_sequence", {"sequence_id": sequences[0]["id"]})
    assert sequence["id"] == sequences[0]["id"]
    assert sequence["amino_acids"] == sequences[0]["amino_acids"]

    experiments = _tool_ok(episode.db_path, "list_experiments", {})["experiments"]
    assert [row["status"] for row in experiments] == ["submitted"]
    experiment = _tool_ok(episode.db_path, "get_experiment", {"experiment_id": experiments[0]["id"]})
    assert experiment["id"] == experiments[0]["id"]

    experiment_sequences = _tool_ok(
        episode.db_path,
        "list_experiment_sequences",
        {"experiment_id": experiment["id"]},
    )["sequences"]
    assert {row["sequence_id"] for row in experiment_sequences} == {row["id"] for row in sequences}


def test_adaptyv_foundry_create_estimate_submit_draft_lifecycle(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="budget_cap_quote_reject",
        seed=5,
        out_dir=tmp_path / "run",
    )
    target_id = _tool_ok(episode.db_path, "list_targets", {})["targets"][0]["id"]
    sequences = _tool_ok(episode.db_path, "list_sequences", {})["sequences"][:2]

    created = _tool_ok(
        episode.db_path,
        "create_experiment",
        {
            "name": "Agent sandbox screen",
            "target_id": target_id,
            "experiment_type": "binding_screen",
            "method": "public_replay_dry_run",
        },
    )
    assert created["experiment"]["status"] == "draft"

    attached = _tool_ok(
        episode.db_path,
        "add_sequences_to_experiment",
        {
            "experiment_id": created["experiment"]["id"],
            "sequences": [
                {"sequence_id": sequences[0]["id"], "alias": "agent_candidate_a"},
                {"sequence_id": sequences[1]["id"], "alias": "agent_candidate_b"},
            ],
        },
    )
    assert [row["alias"] for row in attached["sequences"]] == ["agent_candidate_a", "agent_candidate_b"]

    estimated = _tool_ok(
        episode.db_path,
        "estimate_experiment_cost",
        {"experiment_id": created["experiment"]["id"]},
    )
    assert estimated["cost_estimate"]["amount_cents"] > 0
    assert estimated["cost_estimate"]["currency"] == "USD"

    submitted = _tool_ok(
        episode.db_path,
        "submit_experiment",
        {"experiment_id": created["experiment"]["id"]},
    )
    assert submitted["experiment"]["status"] == "submitted"


def test_add_sequences_to_experiment_normalizes_sequence_payloads(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="budget_cap_quote_reject",
        seed=17,
        out_dir=tmp_path / "run",
    )
    target_id = _tool_ok(episode.db_path, "list_targets", {})["targets"][0]["id"]
    sequence_id = _tool_ok(episode.db_path, "list_sequences", {})["sequences"][0]["id"]
    created = _tool_ok(
        episode.db_path,
        "create_experiment",
        {
            "name": "Whitespace normalization check",
            "target_id": target_id,
        },
    )

    attached = _tool_ok(
        episode.db_path,
        "add_sequences_to_experiment",
        {
            "experiment_id": created["experiment"]["id"],
            "sequences": [
                {"sequence_id": f"  {sequence_id}  ", "alias": "  agent_trimmed_alias  "},
            ],
        },
    )

    assert attached["sequences"] == [
        {
            **attached["sequences"][0],
            "sequence_id": sequence_id,
            "alias": "agent_trimmed_alias",
        }
    ]

    duplicate = _tool_error(
        episode.db_path,
        "add_sequences_to_experiment",
        {
            "experiment_id": created["experiment"]["id"],
            "sequences": [
                {"sequence_id": f" {sequence_id} ", "alias": " agent_trimmed_alias "},
            ],
        },
    )
    assert duplicate["code"] == "DUPLICATE_SEQUENCE_ALIAS"


def test_duplicate_submission_guard_seeds_prior_submitted_duplicate_batch(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="duplicate_submission_guard",
        seed=19,
        out_dir=tmp_path / "run",
    )

    quote_schedule = _read_json(episode.run_dir / "hidden" / "quote_schedule.json")
    current_experiment_id = quote_schedule["experiment_id"]
    with sqlite3.connect(episode.run_dir / "state.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        current_rows = conn.execute(
            """
            SELECT es.sequence_id, es.alias, s.amino_acids
            FROM experiment_sequences es
            JOIN sequences s ON s.id = es.sequence_id
            WHERE es.experiment_id = ?
            """,
            (current_experiment_id,),
        ).fetchall()
        prior_experiments = conn.execute(
            """
            SELECT id
            FROM experiments
            WHERE id != ? AND status = 'submitted'
            """,
            (current_experiment_id,),
        ).fetchall()

        current_sequence_ids = {row["sequence_id"] for row in current_rows}
        current_aliases = {row["alias"] for row in current_rows}
        current_amino_acids = {row["amino_acids"] for row in current_rows}

        duplicate_found = False
        for prior in prior_experiments:
            prior_rows = conn.execute(
                """
                SELECT es.sequence_id, es.alias, s.amino_acids
                FROM experiment_sequences es
                JOIN sequences s ON s.id = es.sequence_id
                WHERE es.experiment_id = ?
                """,
                (prior["id"],),
            ).fetchall()
            prior_sequence_ids = {row["sequence_id"] for row in prior_rows}
            prior_aliases = {row["alias"] for row in prior_rows}
            prior_amino_acids = {row["amino_acids"] for row in prior_rows}
            duplicate_found = (
                current_sequence_ids <= prior_sequence_ids
                or current_aliases <= prior_aliases
                or current_amino_acids <= prior_amino_acids
            )
            if duplicate_found:
                break

    assert current_rows
    assert duplicate_found


def test_adaptyv_foundry_measured_result_decision_path_records_visible_final_result(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="measured_result_supported_decision",
        seed=7,
        out_dir=tmp_path / "run",
    )
    experiment_id = _tool_ok(episode.db_path, "list_experiments", {})["experiments"][0]["id"]

    experiment = _tool_ok(episode.db_path, "get_experiment", {"experiment_id": experiment_id})
    assert experiment["status"] == "submitted"
    results = _tool_ok(
        episode.db_path,
        "list_experiment_results",
        {"experiment_id": experiment_id},
    )["results"]
    assert results
    assert {row["status"] for row in results} == {"final"}

    cited_result_id = results[0]["id"]
    decision = _tool_ok(
        episode.db_path,
        "submit_campaign_decision",
        {
            "experiment_id": experiment_id,
            "decision": "select_measured_replay_winner",
            "cited_result_ids": [cited_result_id],
            "rationale": "Citing a visible final measured replay result from the current experiment.",
        },
    )

    assert decision["campaign_decision"]["decision"] == "select_measured_replay_winner"
    assert decision["campaign_decision"]["cited_result_ids"] == [cited_result_id]

    stored_decision_count = _sqlite_scalar(
        episode.db_path,
        "SELECT COUNT(*) FROM campaign_decisions WHERE id = ?",
        (decision["campaign_decision"]["id"],),
    )
    assert stored_decision_count == 1


def test_adaptyv_foundry_budget_cap_quote_reject_path(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="budget_cap_quote_reject",
        seed=7,
        out_dir=tmp_path / "run",
    )
    experiment_id = _tool_ok(episode.db_path, "list_experiments", {})["experiments"][0]["id"]

    quote = _tool_ok(episode.db_path, "get_experiment_quote", {"experiment_id": experiment_id})["quote"]
    assert quote["over_budget"] is True
    rejected_confirm = _tool_error(
        episode.db_path,
        "confirm_quote",
        {"quote_id": quote["id"]},
    )
    assert rejected_confirm["code"] == "QUOTE_OVER_BUDGET"

    rejected = _tool_ok(episode.db_path, "reject_quote", {"quote_id": quote["id"]})
    assert rejected["quote"]["status"] == "rejected"


def test_adaptyv_foundry_expired_quote_not_confirmed_returns_stable_error(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="expired_quote_not_confirmed",
        seed=7,
        out_dir=tmp_path / "run",
    )
    experiment_id = _tool_ok(episode.db_path, "list_experiments", {})["experiments"][0]["id"]
    quote = _tool_ok(episode.db_path, "get_experiment_quote", {"experiment_id": experiment_id})["quote"]

    result = _tool_error(episode.db_path, "confirm_quote", {"quote_id": quote["id"]})

    assert result["code"] == "QUOTE_EXPIRED"
    assert result["details"]["quote_id"] == quote["id"]


def test_adaptyv_foundry_partial_results_visible_before_final_decision(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=7,
        out_dir=tmp_path / "run",
    )
    experiment_id = _tool_ok(episode.db_path, "list_experiments", {})["experiments"][0]["id"]

    results = _tool_ok(
        episode.db_path,
        "list_experiment_results",
        {"experiment_id": experiment_id},
    )["results"]
    assert [row["status"] for row in results] == ["partial"]

    decision = _tool_error(
        episode.db_path,
        "submit_campaign_decision",
        {
            "experiment_id": experiment_id,
            "decision": "select_candidate_from_partial_signal",
            "cited_result_ids": [results[0]["id"]],
            "rationale": "This records the partial-result decision for the verifier to judge later.",
        },
    )
    assert decision["code"] == "RESULT_STATUS_PARTIAL"
    assert decision["details"]["result_id"] == results[0]["id"]

    hidden_result_id = _sqlite_scalar(
        episode.db_path,
        "SELECT id FROM results WHERE experiment_id = ? AND status = 'final' ORDER BY id LIMIT 1",
        (experiment_id,),
    )
    not_ready = _tool_error(
        episode.db_path,
        "get_result",
        {"experiment_id": experiment_id, "result_id": hidden_result_id},
    )
    assert not_ready["code"] == "RESULTS_NOT_READY"
    assert not_ready["details"] == {"experiment_id": experiment_id, "result_id": hidden_result_id}


def test_result_polling_advances_logical_clock_without_exposing_hidden_schedule(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=7,
        out_dir=tmp_path / "run",
    )
    experiment_id = _tool_ok(episode.db_path, "list_experiments", {})["experiments"][0]["id"]
    initial_clock = _single_logical_clock(episode.db_path)

    first = _tool_ok(
        episode.db_path,
        "list_experiment_results",
        {"experiment_id": experiment_id},
    )
    after_first_clock = _single_logical_clock(episode.db_path)
    second = _tool_ok(
        episode.db_path,
        "list_experiment_results",
        {"experiment_id": experiment_id},
    )
    after_second_clock = _single_logical_clock(episode.db_path)
    third = _tool_ok(
        episode.db_path,
        "list_experiment_results",
        {"experiment_id": experiment_id},
    )
    third_text = json.dumps(third, sort_keys=True)

    assert [row["status"] for row in first["results"]] == ["partial"]
    assert first["logical_time"] == initial_clock["current_time"]
    assert after_first_clock["current_time"] == initial_clock["current_time"]
    assert [row["status"] for row in second["results"]] == ["partial"]
    assert second["logical_time"] == initial_clock["current_time"]
    assert _parse_z(after_second_clock["current_time"]) > _parse_z(initial_clock["current_time"])
    assert third["logical_time"] == after_second_clock["current_time"]
    assert {row["status"] for row in third["results"]} == {"partial", "final"}
    assert "result_arrival_schedule" not in third_text

    with sqlite3.connect(episode.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT event_type, object_type, payload_json, visible_to_agent
            FROM events
            WHERE event_type = 'logical_clock.advanced'
            ORDER BY id
            """
        ).fetchall()
        result_reads = conn.execute(
            """
            SELECT action, object_id
            FROM audit_log
            WHERE action = 'adaptyv.list_experiment_results'
            ORDER BY id
            """
        ).fetchall()

    assert [dict(row) for row in result_reads][-3:] == [
        {"action": "adaptyv.list_experiment_results", "object_id": experiment_id},
        {"action": "adaptyv.list_experiment_results", "object_id": experiment_id},
        {"action": "adaptyv.list_experiment_results", "object_id": experiment_id},
    ]
    assert len(rows) == 1
    event = dict(rows[0])
    payload = json.loads(event["payload_json"])
    assert event["object_type"] == "logical_clock"
    assert event["visible_to_agent"] == 0
    assert payload == {
        "advanced_from": initial_clock["current_time"],
        "advanced_to": after_second_clock["current_time"],
        "experiment_id": experiment_id,
        "trigger": "adaptyv.list_experiment_results",
    }


def test_read_tools_emit_distinct_observation_ids_and_audit_rows(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="measured_result_supported_decision",
        seed=13,
        out_dir=tmp_path / "run",
    )
    initial_count = _sqlite_scalar(episode.db_path, "SELECT COUNT(*) FROM audit_log")

    first = get_world_runtime(WORLD).dispatch_tool(episode.db_path, name="list_targets", arguments={})
    second = get_world_runtime(WORLD).dispatch_tool(episode.db_path, name="list_targets", arguments={})

    assert first["ok"] is True, first
    assert second["ok"] is True, second
    assert first["observation_id"].startswith("obs_")
    assert second["observation_id"].startswith("obs_")
    assert first["observation_id"] != second["observation_id"]

    with sqlite3.connect(episode.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT action, object_type, response_json
            FROM audit_log
            WHERE id > ?
            ORDER BY id
            """,
            (initial_count,),
        ).fetchall()

    assert [row["action"] for row in rows] == ["adaptyv.list_targets", "adaptyv.list_targets"]
    assert [row["object_type"] for row in rows] == ["read", "read"]
    responses = [json.loads(row["response_json"]) for row in rows]
    assert responses == [
        {"ok": True, "observation_id": first["observation_id"]},
        {"ok": True, "observation_id": second["observation_id"]},
    ]


def test_adaptyv_foundry_duplicate_submission_read_tools_expose_prior_batch(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="duplicate_submission_guard",
        seed=19,
        out_dir=tmp_path / "run",
    )

    experiments = _tool_ok(episode.db_path, "list_experiments", {})["experiments"]
    prior = next(row for row in experiments if row["status"] == "submitted")
    current = next(row for row in experiments if row["status"] == "draft")
    prior_sequences = _tool_ok(
        episode.db_path,
        "list_experiment_sequences",
        {"experiment_id": prior["id"]},
    )["sequences"]
    current_sequences = _tool_ok(
        episode.db_path,
        "list_experiment_sequences",
        {"experiment_id": current["id"]},
    )["sequences"]

    assert {row["alias"] for row in current_sequences} <= {row["alias"] for row in prior_sequences}
    assert {row["sequence_id"] for row in current_sequences} <= {row["sequence_id"] for row in prior_sequences}


def test_adaptyv_foundry_structured_errors_include_scope_and_result_membership(tmp_path: Path) -> None:
    scoped_out = get_world_runtime(WORLD).sample_episode(
        scenario="duplicate_submission_guard",
        seed=23,
        out_dir=tmp_path / "scoped-out",
    )
    with sqlite3.connect(scoped_out.db_path) as conn:
        conn.execute("UPDATE token_scopes SET can_confirm_quote = 0")
    experiment_id = _tool_ok(scoped_out.db_path, "list_experiments", {})["experiments"][0]["id"]
    quote = _tool_ok(scoped_out.db_path, "get_experiment_quote", {"experiment_id": experiment_id})["quote"]

    forbidden = _tool_error(scoped_out.db_path, "confirm_quote", {"quote_id": quote["id"]})
    assert forbidden["code"] == "AUTH_SCOPE_FORBIDS_ACTION"

    stale = get_world_runtime(WORLD).sample_episode(
        scenario="stale_prior_campaign_result",
        seed=23,
        out_dir=tmp_path / "stale",
    )
    current_experiment_id = _sqlite_scalar(
        stale.db_path,
        "SELECT id FROM experiments WHERE name != 'Prior replay campaign' ORDER BY id LIMIT 1",
    )
    stale_result_id = _sqlite_scalar(
        stale.db_path,
        "SELECT id FROM results WHERE experiment_id != ? ORDER BY id LIMIT 1",
        (current_experiment_id,),
    )

    wrong_experiment = _tool_error(
        stale.db_path,
        "get_result",
        {"experiment_id": current_experiment_id, "result_id": stale_result_id},
    )
    assert wrong_experiment["code"] == "RESULT_NOT_IN_EXPERIMENT"


def test_submit_campaign_decision_validates_cited_result_ids(tmp_path: Path) -> None:
    partial = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=29,
        out_dir=tmp_path / "partial",
    )
    partial_experiment_id = _tool_ok(partial.db_path, "list_experiments", {})["experiments"][0]["id"]
    partial_result_id = _tool_ok(
        partial.db_path,
        "list_experiment_results",
        {"experiment_id": partial_experiment_id},
    )["results"][0]["id"]

    partial_decision = _tool_error(
        partial.db_path,
        "submit_campaign_decision",
        {
            "experiment_id": partial_experiment_id,
            "decision": "select_candidate_from_partial_signal",
            "cited_result_ids": [partial_result_id],
            "rationale": "A partial result is not final measured evidence.",
        },
    )
    assert partial_decision["code"] == "RESULT_STATUS_PARTIAL"
    assert partial_decision["details"] == {
        "experiment_id": partial_experiment_id,
        "result_id": partial_result_id,
        "status": "partial",
    }

    stale = get_world_runtime(WORLD).sample_episode(
        scenario="stale_prior_campaign_result",
        seed=29,
        out_dir=tmp_path / "stale",
    )
    current_experiment_id = _sqlite_scalar(
        stale.db_path,
        "SELECT id FROM experiments WHERE name != 'Prior replay campaign' ORDER BY id LIMIT 1",
    )
    stale_result_id = _sqlite_scalar(
        stale.db_path,
        "SELECT id FROM results WHERE experiment_id != ? ORDER BY id LIMIT 1",
        (current_experiment_id,),
    )

    stale_decision = _tool_error(
        stale.db_path,
        "submit_campaign_decision",
        {
            "experiment_id": current_experiment_id,
            "decision": "cite_stale_prior_campaign",
            "cited_result_ids": [stale_result_id],
            "rationale": "This result is from a prior campaign.",
        },
    )
    assert stale_decision["code"] == "STALE_RESULT_USED"
    assert stale_decision["details"]["result_id"] == stale_result_id
    assert stale_decision["details"]["experiment_id"] == current_experiment_id

    nonexistent = _tool_error(
        stale.db_path,
        "submit_campaign_decision",
        {
            "experiment_id": current_experiment_id,
            "decision": "cite_missing_result",
            "cited_result_ids": ["result_not_present"],
            "rationale": "The cited result id is not present.",
        },
    )
    assert nonexistent["code"] == "RESULT_NOT_IN_EXPERIMENT"
    assert nonexistent["details"] == {
        "experiment_id": current_experiment_id,
        "result_id": "result_not_present",
    }


def test_live_provider_operation_names_hit_boundary_without_public_tools(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="partial_results_not_final",
        seed=31,
        out_dir=tmp_path / "run",
    )
    public_tool_names = set(_runtime_tool_names(get_world_runtime(WORLD)))
    live_operation_names = {
        "attenuate_token",
        "revoke_token",
        "confirm_experiment_quote_live",
    }
    assert live_operation_names.isdisjoint(public_tool_names)

    initial_live_events = _sqlite_scalar(episode.db_path, "SELECT COUNT(*) FROM live_boundary_events")
    for index, operation_name in enumerate(sorted(live_operation_names), start=1):
        result = get_world_runtime(WORLD).dispatch_tool(
            episode.db_path,
            name=operation_name,
            arguments={},
        )

        assert result["ok"] is False, result
        assert result["error"]["code"] == "LIVE_EXECUTION_FORBIDDEN"
        assert result["error"]["details"] == {"attempted_operation": operation_name}
        assert (
            _sqlite_scalar(episode.db_path, "SELECT COUNT(*) FROM live_boundary_events")
            == initial_live_events + index
        )

    unknown = get_world_runtime(WORLD).dispatch_tool(
        episode.db_path,
        name="unrelated_non_catalog_operation",
        arguments={},
    )
    assert unknown["ok"] is False, unknown
    assert unknown["error"]["code"] == "UNKNOWN_TOOL"
    assert _sqlite_scalar(episode.db_path, "SELECT COUNT(*) FROM live_boundary_events") == (
        initial_live_events + len(live_operation_names)
    )


def test_visible_sequence_metadata_is_neutral(tmp_path: Path) -> None:
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="measured_result_supported_decision",
        seed=1,
        out_dir=tmp_path / "run",
    )

    forbidden_terms = {
        "winner",
        "measured replay",
        "measured_public_replay",
        "best",
        *SELECTED_PUBLIC_REPLAY_ROWS.keys(),
    }
    with sqlite3.connect(episode.run_dir / "state.sqlite") as conn:
        metadata_rows = conn.execute("SELECT metadata_json FROM sequences").fetchall()

    assert metadata_rows
    for (metadata_json,) in metadata_rows:
        metadata_text = json.dumps(json.loads(metadata_json), sort_keys=True)
        metadata_text_lower = metadata_text.lower()
        for term in forbidden_terms:
            assert term.lower() not in metadata_text_lower


def test_public_replay_sources_ground_hidden_measured_rows(tmp_path: Path) -> None:
    source_payload = _read_json(
        Path(__file__).resolve().parents[1]
        / "worlds"
        / WORLD
        / "public_replay_sources.json"
    )
    selected_rows = source_payload["selected_rows"]
    selected_by_name = {row["row_name"]: row for row in selected_rows}

    assert set(SELECTED_PUBLIC_REPLAY_ROWS) == set(selected_by_name)
    for row_name, expected in SELECTED_PUBLIC_REPLAY_ROWS.items():
        row = selected_by_name[row_name]
        assert row["measured_fields"]["kd_m"] == expected["kd"]
        assert row["sequence"] == expected["sequence"]

    selected_source_refs = {f"public_replay_sources:{row['id']}" for row in selected_rows}
    episode = get_world_runtime(WORLD).sample_episode(
        scenario="measured_result_supported_decision",
        seed=7,
        out_dir=tmp_path / "run",
    )
    measured = _read_json(episode.run_dir / "hidden" / "measured_result_replay.json")
    measured_source_refs = {row["source_ref"] for row in measured["measured_results"]}
    with sqlite3.connect(episode.run_dir / "state.sqlite") as conn:
        sqlite_source_refs = {row[0] for row in conn.execute("SELECT source_ref FROM results")}

    assert measured_source_refs <= selected_source_refs
    assert sqlite_source_refs <= selected_source_refs


def test_public_replay_source_refs_are_declared_as_row_level_world_evidence(tmp_path: Path) -> None:
    world_dir = Path(__file__).resolve().parents[1] / "worlds" / WORLD
    source_refs = _read_json(world_dir / "source_refs.json")
    public_sources = _read_json(world_dir / "public_replay_sources.json")
    selected_source_refs = {
        f"public_replay_sources:{row['id']}" for row in public_sources["selected_rows"]
    }
    declared_source_refs = {
        record
        for evidence in source_refs["world_evidence"]
        if evidence.get("path") == "public_replay_sources.json"
        for record in evidence.get("records", [])
    }

    episode = get_world_runtime(WORLD).sample_episode(
        scenario="measured_result_supported_decision",
        seed=23,
        out_dir=tmp_path / "run",
    )
    measured = _read_json(episode.run_dir / "hidden" / "measured_result_replay.json")
    measured_source_refs = {row["source_ref"] for row in measured["measured_results"]}
    with sqlite3.connect(episode.run_dir / "state.sqlite") as conn:
        sqlite_source_refs = {row[0] for row in conn.execute("SELECT source_ref FROM results")}

    assert selected_source_refs <= declared_source_refs
    assert measured_source_refs <= declared_source_refs
    assert sqlite_source_refs <= declared_source_refs


def test_world_spec_declares_logical_clock_and_duplicate_submission_read_tools() -> None:
    spec = _read_json(Path(__file__).resolve().parents[1] / "worlds" / WORLD / "spec.json")

    assert "logical_clock" in spec["state_model"]["tables"]
    assert "list_experiments" in spec["tools"]
    assert "list_experiment_sequences" in spec["tools"]


def test_world_source_refs_include_duplicate_submission_read_operations() -> None:
    source_refs = _read_json(Path(__file__).resolve().parents[1] / "worlds" / WORLD / "source_refs.json")
    records = set(source_refs["source_packs"][0]["records"])

    assert "operation:list_experiments" in records
    assert "operation:get_experiment_sequences" in records


def test_sampling_same_scenario_seed_is_byte_stable(tmp_path: Path) -> None:
    runtime = get_world_runtime(WORLD)
    first = runtime.sample_episode(
        scenario="partial_results_not_final",
        seed=1,
        out_dir=tmp_path / "first",
    )
    second = runtime.sample_episode(
        scenario="partial_results_not_final",
        seed=1,
        out_dir=tmp_path / "second",
    )

    assert _read_bytes(first.run_dir / "task.json") == _read_bytes(second.run_dir / "task.json")
    assert _read_bytes(first.run_dir / "run.json") == _read_bytes(second.run_dir / "run.json")

    first_hidden = sorted((first.run_dir / "hidden").glob("*.json"))
    second_hidden = sorted((second.run_dir / "hidden").glob("*.json"))
    assert [path.name for path in first_hidden] == [path.name for path in second_hidden]
    for first_path, second_path in zip(first_hidden, second_hidden):
        assert _read_bytes(first_path) == _read_bytes(second_path)


def test_adaptyv_foundry_world_source_refs_validate() -> None:
    result = validate_world_source_refs(WORLD)

    assert result["ok"] is True
    assert result["world"] == WORLD


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _runtime_tool_names(runtime: Any) -> list[str]:
    return [str(tool["function"]["name"]) for tool in runtime.tool_definitions]


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


def _sqlite_scalar(db_path: Path, query: str, params: tuple[Any, ...] = ()) -> Any:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def _single_logical_clock(db_path: Path) -> dict[str, str]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT id, "current_time", source FROM logical_clock').fetchall()

    assert len(rows) == 1
    return dict(rows[0])


def _parse_z(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
