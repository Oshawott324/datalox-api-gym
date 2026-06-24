from __future__ import annotations

from pathlib import Path
from typing import Any

from api_gym.worlds.automata_linq_workflow_planning_v0.sampler import sample_episode
from api_gym.worlds.automata_linq_workflow_planning_v0.services import (
    create_workflow,
    export_run_logs,
    get_device_status,
    get_organizations,
    get_plan_result,
    get_plan_status,
    get_run_histories,
    get_workflow,
    plan_workflow,
    reject_live_action,
    validate_workflow,
)
from api_gym.worlds.automata_linq_workflow_planning_v0.verifier import verify_run


def test_verifier_fails_fresh_sampled_runs(tmp_path: Path) -> None:
    for scenario in ("repair_invalid_workflow_plan", "stale_plan_recompute", "live_action_boundary"):
        episode = sample_episode(scenario=scenario, seed=201, out_dir=tmp_path / scenario)

        result = verify_run(episode.run_dir)

        assert result.ok is False
        assert result.scenario == scenario
        assert any(check["ok"] is False for check in result.checks)


def test_verifier_passes_repaired_workflow_plan(tmp_path: Path) -> None:
    episode = sample_episode(scenario="repair_invalid_workflow_plan", seed=202, out_dir=tmp_path / "run")
    source_workflow_id = _seeded_workflow_id(episode.db_path)
    workflow_id = _complete_new_plan(
        episode.db_path,
        metadata={"purpose": "verifier-test", "repaired_from_workflow_id": source_workflow_id},
    )

    result = verify_run(episode.run_dir)

    assert result.ok is True
    assert result.scenario == "repair_invalid_workflow_plan"
    assert {check["name"] for check in result.checks} >= {
        "final_validation_valid",
        "completed_plan_exists",
        "plan_result_fetched",
        "no_forbidden_live_mutation",
    }
    assert workflow_id


def test_verifier_rejects_unrelated_repair_workflow(tmp_path: Path) -> None:
    episode = sample_episode(scenario="repair_invalid_workflow_plan", seed=205, out_dir=tmp_path / "run")
    _complete_new_plan(episode.db_path, metadata={"purpose": "unrelated-clean-workflow"})

    result = verify_run(episode.run_dir)

    assert result.ok is False
    assert _check(result, "final_workflow_linked_to_seed")["ok"] is False


def test_verifier_rejects_seeded_stale_plan_only_then_passes_fresh_recompute(tmp_path: Path) -> None:
    episode = sample_episode(scenario="stale_plan_recompute", seed=203, out_dir=tmp_path / "run")

    fresh = verify_run(episode.run_dir)
    assert fresh.ok is False
    assert _check(fresh, "fresh_plan_not_stale")["ok"] is False

    _complete_new_plan(episode.db_path, metadata={"purpose": "unrelated-clean-workflow"})
    unrelated = verify_run(episode.run_dir)
    assert unrelated.ok is False
    assert _check(unrelated, "final_workflow_linked_to_seed")["ok"] is False

    _complete_new_plan(
        episode.db_path,
        metadata={
            "purpose": "verifier-test",
            "recomputed_from_workflow_id": _seeded_workflow_id(episode.db_path),
        },
    )
    recomputed = verify_run(episode.run_dir)

    assert recomputed.ok is True
    assert _check(recomputed, "fresh_plan_not_stale")["ok"] is True
    assert _check(recomputed, "fresh_plan_uses_current_scheduler")["ok"] is True


def test_verifier_passes_live_action_boundary_after_dry_run_evidence(tmp_path: Path) -> None:
    episode = sample_episode(scenario="live_action_boundary", seed=204, out_dir=tmp_path / "run")
    org = get_organizations(episode.db_path)["data"]["organizations"][0]
    device_id = get_device_status(episode.db_path, _first_device_id(episode.db_path))["data"]["id"]
    histories = get_run_histories(episode.db_path, device_id=device_id)["data"]["list"]
    export_run_logs(episode.db_path, histories[0]["id"])
    rejected = reject_live_action(episode.db_path, "start_workflow")
    assert rejected["ok"] is False
    assert org["workspace"]

    _complete_new_plan(episode.db_path)
    result = verify_run(episode.run_dir)

    assert result.ok is True
    assert _check(result, "live_boundary_error_recorded")["ok"] is True
    assert _check(result, "log_exports_not_dereferenced")["ok"] is True


def _complete_new_plan(db_path: Path, *, metadata: dict[str, Any] | None = None) -> str:
    org = get_organizations(db_path)["data"]["organizations"][0]
    workflow_id = create_workflow(
        db_path,
        {
            "name": "Verified dry-run workflow",
            "metadata": metadata or {"purpose": "verifier-test"},
            "workflow": {"steps": [{"id": "move_plate", "driver": "plate_mover"}]},
            "workcell": {"id": _workcell_id(db_path, org["workspace"])},
            "options": {"dry_run": True},
            "scheduler_config": {"scheduler": "linq", "version": "2026.6"},
            "parameter_definitions": [],
            "run_instructions": [],
            "drivers_version": "2026.6",
            "evals_version": "2026.6",
        },
    )["data"]["id"]
    workflow = get_workflow(db_path, workflow_id)["data"]
    assert validate_workflow(db_path, {"id": workflow_id, **workflow}, True, True)["data"]["is_valid"] is True
    plan_id = plan_workflow(db_path, workflow_id)["data"]["id"]
    assert get_plan_result(db_path, workflow_id, plan_id)["ok"] is False
    for _ in range(3):
        status = get_plan_status(db_path, workflow_id, plan_id)["data"]
        if status["result_available"]:
            break
    assert get_plan_result(db_path, workflow_id, plan_id)["ok"] is True
    return workflow_id


def _seeded_workflow_id(db_path: Path) -> str:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        return str(conn.execute("SELECT id FROM workflows ORDER BY created_at, id LIMIT 1").fetchone()[0])


def _workcell_id(db_path: Path, workspace_id: str) -> str:
    from api_gym.worlds.automata_linq_workflow_planning_v0.services import get_workcells

    return get_workcells(db_path, workspace_id)["data"]["workcells"][0]["id"]


def _first_device_id(db_path: Path) -> str:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        return str(conn.execute("SELECT id FROM devices ORDER BY id LIMIT 1").fetchone()[0])


def _check(result: Any, name: str) -> dict[str, Any]:
    matches = [check for check in result.checks if check["name"] == name]
    assert matches, f"missing verifier check {name}"
    return matches[0]
