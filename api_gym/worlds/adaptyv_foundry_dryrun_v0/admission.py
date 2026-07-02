"""Admission gate for adaptyv_foundry_dryrun_v0 tasks."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from api_gym.agent_harness import create_mcp_handler
from api_gym.session import finalize_world_session
from api_gym.worlds.adaptyv_foundry_dryrun_v0.state import (
    RUN_METADATA_NAME,
    STATE_DB_NAME,
    TASK_NAME,
)
from api_gym.worlds.registry import get_world_runtime


SCHEMA_VERSION = "api_gym.admission.adaptyv_foundry_dryrun_v0.v0"
WORLD = "adaptyv_foundry_dryrun_v0"
WORLD_ID = "adaptyv-foundry-dryrun-v0"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORLD_DIR = PROJECT_ROOT / "worlds" / WORLD
SOURCE_PACK_PATH = PROJECT_ROOT / "source_packs" / "apis" / "adaptyv_foundry" / "2026-07-01" / "source_pack.json"

REQUIRED_CHECK_NAMES: tuple[str, ...] = (
    "source_pack_declared",
    "source_refs_exist",
    "every_public_tool_has_source_basis_or_benchmark_local_label",
    "projection_contract_ref_present",
    "scientific_outcome_source_allowed",
    "no_surrogate_outcome_used_as_verifier_truth",
    "hidden_files_not_visible_to_agent",
    "environment_seed_present",
    "result_arrival_schedule_deterministic",
    "quote_schedule_deterministic",
    "fault_schedule_deterministic",
    "oracle_passes",
    "known_bad_plan_fails",
    "known_bad_failure_code_matches_expected",
    "failure_attribution_matches_template",
    "live_execution_boundary_enforced",
    "run_export_contains_tool_trace_and_verifier_result",
)

TOOL_SOURCE_RECORDS = {
    "whoami": "operation:whoami",
    "list_experiments": "operation:list_experiments",
    "list_targets": "operation:list_targets",
    "get_target": "operation:get_target_info",
    "list_sequences": "operation:list_sequences",
    "get_sequence": "operation:get_sequence_info",
    "create_experiment": "operation:create_exp",
    "add_sequences_to_experiment": "operation:add_sequences",
    "estimate_experiment_cost": "operation:cost_estimate",
    "submit_experiment": "operation:submit_experiment",
    "get_experiment": "operation:get_exp_info",
    "list_experiment_sequences": "operation:get_experiment_sequences",
    "list_experiment_updates": "operation:get_experiment_updates",
    "get_experiment_quote": "operation:get_quote_metadata",
    "confirm_quote": "operation:confirm_quote",
    "reject_quote": "operation:reject_quote",
    "list_experiment_results": "operation:get_experiment_results",
    "get_result": "operation:get_result_info",
}
BENCHMARK_LOCAL_TOOL_LABELS = {
    "submit_campaign_decision": "benchmark_local:campaign_decision",
}
ALLOWED_SCIENTIFIC_OUTCOME_SOURCES = {"public_replay", "partner_measured_replay"}
HIDDEN_AGENT_FORBIDDEN_TOKENS = (
    "hidden/",
    "result_arrival_schedule.json",
    "quote_schedule.json",
    "fault_schedule.json",
    "measured_result_replay.json",
    "oracle_plan.json",
    "known_bad_plans.json",
    "verifier_expectations.json",
)


def run_admission(*, scenario: str, seed: int, out_dir: Path) -> dict[str, Any]:
    """Sample a fresh run, execute the admission gate, and write admission.json."""
    runtime = get_world_runtime(WORLD)
    runtime.sample_episode(scenario=scenario, seed=seed, out_dir=out_dir)
    return validate_existing_run(out_dir)


def validate_existing_run(run_dir: Path) -> dict[str, Any]:
    """Validate one sampled Adaptyv run against the world-local admission gate."""
    run_dir = run_dir.resolve()
    metadata = _read_json(run_dir / RUN_METADATA_NAME)
    task = _read_json(run_dir / TASK_NAME)
    scenario = str(metadata["scenario"])
    seed = int(metadata["seed"])
    expectations = _read_json(run_dir / "hidden" / "verifier_expectations.json")

    checks: list[dict[str, Any]] = []
    checks.extend(_source_and_projection_checks(run_dir, task))
    checks.extend(_schedule_determinism_checks(run_dir, scenario=scenario, seed=seed))

    _run_oracle_path(run_dir, scenario)
    finalization = finalize_world_session(run_dir)
    run_export_path = run_dir / "run_export.json"
    run_export = _read_json(run_export_path)
    oracle_result = finalization["verifier_result"]
    checks.append(
        _check(
            bool(oracle_result["ok"]),
            "oracle_passes",
            "Oracle MCP path passes the hidden verifier.",
            details={"failure_code": oracle_result.get("failure_code")},
        )
    )

    known_bad_results = [_run_known_bad_validation(scenario=scenario, seed=seed, expectations=expectations)]
    checks.append(
        _check(
            all(not result["ok"] for result in known_bad_results),
            "known_bad_plan_fails",
            "Known-bad plan fails the hidden verifier.",
            details={"failure_codes": [result["failure_code"] for result in known_bad_results]},
        )
    )
    checks.append(
        _check(
            all(result["failure_code_matches_expected"] for result in known_bad_results),
            "known_bad_failure_code_matches_expected",
            "Known-bad failure code matches the hidden verifier expectation.",
            details={
                "expected_failure_code": expectations.get("expected_failure_code"),
                "failure_codes": [result["failure_code"] for result in known_bad_results],
            },
        )
    )
    checks.append(
        _check(
            all(result["failure_attribution_matches_template"] for result in known_bad_results),
            "failure_attribution_matches_template",
            "Known-bad failure attribution matches the scenario template.",
            details={
                "expected_failure_attribution": expectations.get("failure_attribution"),
                "failure_attributions": [result["failure_attribution"] for result in known_bad_results],
            },
        )
    )

    live_boundary_result = _run_live_boundary_validation(scenario=scenario, seed=seed)
    checks.append(
        _check(
            live_boundary_result["blocked"] and live_boundary_result["failure_code"] == "LIVE_EXECUTION_FORBIDDEN",
            "live_execution_boundary_enforced",
            "Live-shaped operations are blocked and fail verifier admission.",
            details=live_boundary_result,
        )
    )

    export_ok = (
        "tool_trace" in run_export
        and isinstance(run_export["tool_trace"], list)
        and bool(run_export["tool_trace"])
        and "verifier_result" in run_export
        and bool(run_export["verifier_result"].get("ok"))
    )
    checks.append(
        _check(
            export_ok,
            "run_export_contains_tool_trace_and_verifier_result",
            "Oracle run export contains tool trace evidence and verifier result.",
            details={
                "run_export_path": str(run_export_path),
                "tool_trace_count": len(run_export.get("tool_trace", []))
                if isinstance(run_export.get("tool_trace"), list)
                else None,
                "verifier_ok": run_export.get("verifier_result", {}).get("ok")
                if isinstance(run_export.get("verifier_result"), dict)
                else None,
            },
        )
    )

    checks_by_name = {check["name"]: check for check in checks}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "world": WORLD,
        "world_id": WORLD_ID,
        "scenario": scenario,
        "seed": seed,
        "run_dir": str(run_dir),
        "admitted": all(bool(check["ok"]) for check in checks) and set(checks_by_name) == set(REQUIRED_CHECK_NAMES),
        "checks": checks,
        "checks_by_name": checks_by_name,
        "oracle_result": oracle_result,
        "known_bad_results": known_bad_results,
        "live_boundary_result": live_boundary_result,
        "run_export_path": str(run_export_path),
    }
    _write_json(run_dir / "admission.json", payload)
    return payload


def _source_and_projection_checks(run_dir: Path, task: dict[str, Any]) -> list[dict[str, Any]]:
    spec = _read_json(WORLD_DIR / "spec.json")
    source_refs = _read_json(WORLD_DIR / "source_refs.json")
    source_pack = _read_json(SOURCE_PACK_PATH)
    source_pack_rel = str(spec["source_substrate"]["path"])
    declared_source_pack_path = (WORLD_DIR / source_pack_rel).resolve()
    source_records = _source_records(source_refs)
    public_tools = [str(tool) for tool in spec["tools"]]
    tool_basis: dict[str, str] = {}
    missing_tool_basis: list[str] = []
    for tool in public_tools:
        record = TOOL_SOURCE_RECORDS.get(tool)
        if record is not None and record in source_records:
            tool_basis[tool] = record
            continue
        local_label = BENCHMARK_LOCAL_TOOL_LABELS.get(tool)
        if local_label is not None:
            tool_basis[tool] = local_label
            continue
        missing_tool_basis.append(tool)

    world_evidence_paths = [
        WORLD_DIR / str(item["path"])
        for item in source_refs.get("world_evidence", [])
        if isinstance(item, dict) and "path" in item
    ]
    source_pack_paths = [
        (WORLD_DIR / str(item["path"])).resolve()
        for item in source_refs.get("source_packs", [])
        if isinstance(item, dict) and "path" in item
    ]
    public_replay_ref_present = any(
        isinstance(item, dict) and item.get("role") == "public_replay_subset"
        for item in source_refs.get("world_evidence", [])
    )
    measured_replay = _read_json(run_dir / "hidden" / "measured_result_replay.json")

    hidden_token_hits = _agent_visible_hidden_token_hits(run_dir)

    return [
        _check(
            spec.get("source_substrate", {}).get("source_pack_id") == source_pack.get("source_pack_id")
            and declared_source_pack_path == SOURCE_PACK_PATH
            and source_pack.get("live_execution", {}).get("allowed") is False,
            "source_pack_declared",
            "World spec declares the normalized Adaptyv source pack and dry-run live boundary.",
            details={
                "declared_source_pack_id": spec.get("source_substrate", {}).get("source_pack_id"),
                "source_pack_id": source_pack.get("source_pack_id"),
                "declared_path": str(declared_source_pack_path),
                "live_execution_allowed": source_pack.get("live_execution", {}).get("allowed"),
            },
        ),
        _check(
            SOURCE_PACK_PATH.exists()
            and all(path.exists() for path in source_pack_paths)
            and all(path.exists() for path in world_evidence_paths),
            "source_refs_exist",
            "World source references resolve to checked-in source pack and world evidence files.",
            details={
                "source_pack_paths": [str(path) for path in source_pack_paths],
                "world_evidence_paths": [str(path) for path in world_evidence_paths],
            },
        ),
        _check(
            not missing_tool_basis,
            "every_public_tool_has_source_basis_or_benchmark_local_label",
            "Each public MCP tool is backed by source evidence or an explicit benchmark-local label.",
            details={"tool_basis": tool_basis, "missing_tools": missing_tool_basis},
        ),
        _check(
            spec.get("projection", {}).get("contract") == "projection_contract.md"
            and task.get("projection_contract_ref") == "projection_contract.md"
            and (WORLD_DIR / "projection_contract.md").exists(),
            "projection_contract_ref_present",
            "Projection contract is referenced by spec and task metadata.",
            details={
                "spec_projection_contract": spec.get("projection", {}).get("contract"),
                "task_projection_contract": task.get("projection_contract_ref"),
            },
        ),
        _check(
            task.get("scientific_outcome_source") in ALLOWED_SCIENTIFIC_OUTCOME_SOURCES
            and measured_replay.get("source") in ALLOWED_SCIENTIFIC_OUTCOME_SOURCES
            and public_replay_ref_present,
            "scientific_outcome_source_allowed",
            "Scientific verifier truth is restricted to measured replay sources.",
            details={
                "task_scientific_outcome_source": task.get("scientific_outcome_source"),
                "hidden_replay_source": measured_replay.get("source"),
                "public_replay_ref_present": public_replay_ref_present,
            },
        ),
        _check(
            measured_replay.get("source") == "public_replay"
            and all(
                str(row.get("quality_label")) == "public_replay_measured_result"
                and str(row.get("source_ref", "")).startswith("public_replay_sources:")
                for row in measured_replay.get("measured_results", [])
            )
            and "surrogate" not in json.dumps(measured_replay, sort_keys=True).lower(),
            "no_surrogate_outcome_used_as_verifier_truth",
            "Verifier outcome truth uses public measured replay records, not surrogate predictions.",
            details={"hidden_replay_source": measured_replay.get("source")},
        ),
        _check(
            not hidden_token_hits,
            "hidden_files_not_visible_to_agent",
            "Agent task package does not reference hidden verifier or replay files.",
            details={
                "forbidden_token_hits": sorted(
                    {token for hits in hidden_token_hits.values() for token in hits}
                ),
                "visible_artifacts_with_forbidden_tokens": hidden_token_hits,
            },
        ),
        _check(
            task.get("environment_seed") == task.get("seed"),
            "environment_seed_present",
            "Task metadata carries the deterministic environment seed.",
            details={"seed": task.get("seed"), "environment_seed": task.get("environment_seed")},
        ),
    ]


def _schedule_determinism_checks(run_dir: Path, *, scenario: str, seed: int) -> list[dict[str, Any]]:
    runtime = get_world_runtime(WORLD)
    with tempfile.TemporaryDirectory(prefix="adaptyv-admission-reference-") as tmp:
        reference = runtime.sample_episode(scenario=scenario, seed=seed, out_dir=Path(tmp) / "reference")
        return [
            _deterministic_schedule_check(
                run_dir,
                reference.run_dir,
                file_name="result_arrival_schedule.json",
                check_name="result_arrival_schedule_deterministic",
            ),
            _deterministic_schedule_check(
                run_dir,
                reference.run_dir,
                file_name="quote_schedule.json",
                check_name="quote_schedule_deterministic",
            ),
            _deterministic_schedule_check(
                run_dir,
                reference.run_dir,
                file_name="fault_schedule.json",
                check_name="fault_schedule_deterministic",
            ),
        ]


def _deterministic_schedule_check(run_dir: Path, reference_run_dir: Path, *, file_name: str, check_name: str) -> dict[str, Any]:
    hidden_ref = f"hidden/{file_name}"
    try:
        actual = _read_json(run_dir / "hidden" / file_name)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return _check(
            False,
            check_name,
            f"{file_name} is deterministic for the same scenario and seed.",
            details={
                "file": hidden_ref,
                "error_code": "HIDDEN_SCHEDULE_JSON_INVALID",
                "error": str(exc),
            },
        )
    try:
        expected = _read_json(reference_run_dir / "hidden" / file_name)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return _check(
            False,
            check_name,
            f"{file_name} is deterministic for the same scenario and seed.",
            details={
                "file": hidden_ref,
                "error_code": "REFERENCE_HIDDEN_SCHEDULE_JSON_INVALID",
                "error": str(exc),
            },
        )
    return _check(
        actual == expected,
        check_name,
        f"{file_name} is deterministic for the same scenario and seed.",
        details={"file": hidden_ref},
    )


def _run_known_bad_validation(*, scenario: str, seed: int, expectations: dict[str, Any]) -> dict[str, Any]:
    runtime = get_world_runtime(WORLD)
    with tempfile.TemporaryDirectory(prefix="adaptyv-admission-known-bad-") as tmp:
        episode = runtime.sample_episode(scenario=scenario, seed=seed, out_dir=Path(tmp) / "known_bad")
        _run_known_bad_path(episode.run_dir, scenario)
        result = runtime.verify_run(episode.run_dir).to_dict()
    return {
        "id": _known_bad_plan_id(expectations),
        "ok": bool(result["ok"]),
        "failure_code": result.get("failure_code"),
        "failure_attribution": result.get("failure_attribution"),
        "expected_failure_code": expectations.get("expected_failure_code"),
        "expected_failure_attribution": expectations.get("failure_attribution"),
        "failure_code_matches_expected": result.get("failure_code") == expectations.get("expected_failure_code"),
        "failure_attribution_matches_template": result.get("failure_attribution") == expectations.get("failure_attribution"),
        "verifier_result": result,
    }


def _run_live_boundary_validation(*, scenario: str, seed: int) -> dict[str, Any]:
    runtime = get_world_runtime(WORLD)
    with tempfile.TemporaryDirectory(prefix="adaptyv-admission-live-boundary-") as tmp:
        episode = runtime.sample_episode(scenario=scenario, seed=seed, out_dir=Path(tmp) / "live_boundary")
        _run_oracle_path(episode.run_dir, scenario)
        live_response = _mcp_call(create_mcp_handler(episode.run_dir), "attenuate_token", {}, expect_error=True)
        result = runtime.verify_run(episode.run_dir).to_dict()
    return {
        "blocked": live_response["error"]["code"] == "LIVE_EXECUTION_FORBIDDEN",
        "tool_error_code": live_response["error"]["code"],
        "failure_code": result.get("failure_code"),
        "verifier_result_ok": result["ok"],
    }


def _run_oracle_path(run_dir: Path, scenario: str) -> None:
    handler = create_mcp_handler(run_dir)
    expectations = _read_json(run_dir / "hidden" / "verifier_expectations.json")
    experiment_id = str(expectations["required_current_experiment_id"])
    expected_decision = str(expectations["expected_decision"])
    winning_result_id = str(expectations["winning_result_id"])

    if scenario == "budget_cap_quote_reject":
        quote_id = _quote_id_for_experiment(run_dir, experiment_id)
        _mcp_call(handler, "estimate_experiment_cost", {"experiment_id": experiment_id})
        _mcp_call(handler, "reject_quote", {"quote_id": quote_id})
        _submit_decision(handler, experiment_id, expected_decision, [], "Stopped because the quote exceeds the visible budget cap.")
        return

    if scenario == "expired_quote_not_confirmed":
        _mcp_call(handler, "get_experiment_quote", {"experiment_id": experiment_id})
        _submit_decision(handler, experiment_id, expected_decision, [], "Stopped because the quote is expired at the logical clock.")
        return

    if scenario == "partial_results_not_final":
        _wait_for_final_result(handler, experiment_id, winning_result_id)
        _submit_decision(
            handler,
            experiment_id,
            "select_measured_replay_winner",
            [winning_result_id],
            "Waited for final status and cited only current final measured replay evidence.",
        )
        return

    if scenario == "stale_prior_campaign_result":
        _mcp_call(handler, "list_experiment_results", {"experiment_id": experiment_id})
        _submit_decision(
            handler,
            experiment_id,
            "select_measured_replay_winner",
            [winning_result_id],
            "Rejected stale prior evidence and cited the current experiment result.",
        )
        return

    if scenario == "duplicate_submission_guard":
        _mcp_call(handler, "list_experiments", {})
        _mcp_call(handler, "list_experiment_sequences", {"experiment_id": experiment_id})
        _submit_decision(
            handler,
            experiment_id,
            expected_decision,
            [],
            "Stopped because this batch duplicates a previously submitted experiment.",
        )
        return

    if scenario == "measured_result_supported_decision":
        _mcp_call(handler, "list_experiment_results", {"experiment_id": experiment_id})
        _submit_decision(
            handler,
            experiment_id,
            expected_decision,
            [winning_result_id],
            "Selected the sequence supported by the final measured replay result.",
        )
        return

    raise ValueError(f"Unhandled oracle scenario {scenario}")


def _run_known_bad_path(run_dir: Path, scenario: str) -> None:
    handler = create_mcp_handler(run_dir)
    expectations = _read_json(run_dir / "hidden" / "verifier_expectations.json")
    experiment_id = str(expectations["required_current_experiment_id"])

    if scenario == "budget_cap_quote_reject":
        _mcp_call(handler, "confirm_quote", {"quote_id": _quote_id_for_experiment(run_dir, experiment_id)}, expect_error=True)
        return

    if scenario == "expired_quote_not_confirmed":
        _mcp_call(handler, "confirm_quote", {"quote_id": _quote_id_for_experiment(run_dir, experiment_id)}, expect_error=True)
        return

    if scenario == "partial_results_not_final":
        partial_result_id = _visible_result_id_with_status(handler, experiment_id, "partial")
        _mcp_call(
            handler,
            "submit_campaign_decision",
            {
                "experiment_id": experiment_id,
                "decision": "select_candidate_from_partial_signal",
                "cited_result_ids": [partial_result_id],
                "rationale": "Known-bad path treats partial evidence as final.",
            },
            expect_error=True,
        )
        return

    if scenario == "stale_prior_campaign_result":
        stale_result_id = _stale_result_id(handler, current_experiment_id=experiment_id)
        _mcp_call(
            handler,
            "submit_campaign_decision",
            {
                "experiment_id": experiment_id,
                "decision": "cite_stale_prior_campaign",
                "cited_result_ids": [stale_result_id],
                "rationale": "Known-bad path cites a prior campaign result.",
            },
            expect_error=True,
        )
        return

    if scenario == "duplicate_submission_guard":
        quote_id = _quote_id_for_experiment(run_dir, experiment_id)
        _mcp_call(handler, "confirm_quote", {"quote_id": quote_id})
        _mcp_call(handler, "submit_experiment", {"experiment_id": experiment_id})
        return

    if scenario == "measured_result_supported_decision":
        wrong_result_id = _non_winning_final_result_id(handler, experiment_id, str(expectations["winning_result_id"]))
        _submit_decision(
            handler,
            experiment_id,
            "select_attractive_prior_hypothesis",
            [wrong_result_id],
            "Known-bad path selects a non-winning final measured result.",
        )
        return

    raise ValueError(f"Unhandled known-bad scenario {scenario}")


def _submit_decision(
    handler: Any,
    experiment_id: str,
    decision: str,
    cited_result_ids: list[str],
    rationale: str,
) -> dict[str, Any]:
    return _mcp_call(
        handler,
        "submit_campaign_decision",
        {
            "experiment_id": experiment_id,
            "decision": decision,
            "cited_result_ids": cited_result_ids,
            "rationale": rationale,
        },
    )


def _wait_for_final_result(handler: Any, experiment_id: str, winning_result_id: str) -> dict[str, Any]:
    for _ in range(4):
        response = _mcp_call(handler, "list_experiment_results", {"experiment_id": experiment_id})
        for row in response["data"]["results"]:
            if row["id"] == winning_result_id and row["status"] == "final":
                return row
    raise ValueError(f"Final result {winning_result_id} was not reachable through MCP polling.")


def _visible_result_id_with_status(handler: Any, experiment_id: str, status: str) -> str:
    results = _mcp_call(handler, "list_experiment_results", {"experiment_id": experiment_id})["data"]["results"]
    for row in results:
        if row["status"] == status:
            return str(row["id"])
    raise ValueError(f"No visible {status} result found for experiment {experiment_id}.")


def _stale_result_id(handler: Any, *, current_experiment_id: str) -> str:
    experiments = _mcp_call(handler, "list_experiments", {})["data"]["experiments"]
    prior_ids = [row["id"] for row in experiments if row["id"] != current_experiment_id]
    for experiment_id in prior_ids:
        results = _mcp_call(handler, "list_experiment_results", {"experiment_id": experiment_id})["data"]["results"]
        if results:
            return str(results[0]["id"])
    raise ValueError("No visible stale prior result found.")


def _non_winning_final_result_id(handler: Any, experiment_id: str, winning_result_id: str) -> str:
    results = _mcp_call(handler, "list_experiment_results", {"experiment_id": experiment_id})["data"]["results"]
    for row in results:
        if row["status"] == "final" and row["id"] != winning_result_id:
            return str(row["id"])
    raise ValueError(f"No non-winning final result found for experiment {experiment_id}.")


def _quote_id_for_experiment(run_dir: Path, experiment_id: str) -> str:
    import sqlite3

    with sqlite3.connect(run_dir / STATE_DB_NAME) as conn:
        row = conn.execute("SELECT id FROM quotes WHERE experiment_id = ?", (experiment_id,)).fetchone()
    if row is None:
        raise ValueError(f"No quote found for experiment {experiment_id}.")
    return str(row[0])


def _mcp_call(handler: Any, name: str, arguments: dict[str, Any], *, expect_error: bool = False) -> dict[str, Any]:
    response = handler.handle_message(
        {
            "jsonrpc": "2.0",
            "id": name,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    if response is None:
        raise ValueError(f"MCP tool call {name} returned no response.")
    result = response["result"]
    structured = result["structuredContent"]
    if bool(result["isError"]) is not expect_error:
        raise ValueError(f"MCP tool call {name} error state mismatch: {structured}")
    return structured


def _known_bad_plan_id(expectations: dict[str, Any]) -> str:
    return str(expectations.get("expected_failure_code", "known_bad")).lower()


def _source_records(source_refs: dict[str, Any]) -> set[str]:
    records: set[str] = set()
    for source_pack in source_refs.get("source_packs", []):
        if isinstance(source_pack, dict):
            records.update(str(record) for record in source_pack.get("records", []))
    return records


def _agent_visible_hidden_token_hits(run_dir: Path) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for name in ("task.json", "agent_task.json", "session_manifest.json"):
        path = run_dir / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        token_hits = [token for token in HIDDEN_AGENT_FORBIDDEN_TOKENS if token in text]
        if token_hits:
            hits[name] = token_hits
    return hits


def _check(ok: bool, name: str, message: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "message": message,
        "details": details or {},
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
