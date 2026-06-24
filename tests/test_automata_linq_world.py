from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from api_gym.session import create_world_session
from api_gym.source_packs import validate_source_pack
from api_gym.worlds.automata_linq_workflow_planning_v0.sampler import SCENARIOS, sample_episode
from api_gym.worlds.automata_linq_workflow_planning_v0.verifier import verify_run
from api_gym.worlds.registry import get_world_runtime
from api_gym.worlds.source_refs import validate_world_source_refs

REPO_ROOT = Path(__file__).resolve().parents[1]
WORLD = "automata_linq_workflow_planning_v0"
WORLD_ID = "automata-linq-workflow-planning-v0"
SCENARIO_NAMES = {
    "repair_invalid_workflow_plan",
    "stale_plan_recompute",
    "live_action_boundary",
}
REQUIRED_TABLES = {
    "organizations",
    "scheduler_versions",
    "drivers",
    "workcells",
    "devices",
    "workflows",
    "workflow_validations",
    "plans",
    "plan_results",
    "run_histories",
    "log_exports",
    "events",
    "audit_log",
}
EXPECTED_TOOL_NAMES = {
    "automata_linq_get_api_version",
    "automata_linq_get_organizations",
    "automata_linq_get_scheduler_versions",
    "automata_linq_get_all_drivers",
    "automata_linq_get_workcells",
    "automata_linq_get_device_status",
    "automata_linq_get_run_histories",
    "automata_linq_export_run_logs",
    "automata_linq_create_workflow",
    "automata_linq_list_workflows",
    "automata_linq_get_workflow",
    "automata_linq_validate_workflow",
    "automata_linq_plan_workflow",
    "automata_linq_get_plan_status",
    "automata_linq_get_plan_result",
    "automata_linq_reject_live_action",
}


def test_automata_linq_source_pack_validates() -> None:
    result = validate_source_pack(REPO_ROOT / "source_packs" / "apis" / "automata_linq" / "2026-06-22")

    assert result["ok"] is True
    assert result["source_pack_id"] == "api.automata_linq.2026-06-22"
    assert result["record_counts"]["operations"] == 15
    assert result["record_counts"]["response_cases"] == 18


def test_automata_linq_source_refs_validate() -> None:
    result = validate_world_source_refs(WORLD)

    assert result["ok"] is True
    assert result["world"] == WORLD
    assert result["source_pack_count"] == 1
    assert result["world_evidence_count"] == 2
    assert result["missing_records"] == []
    assert result["missing_world_evidence"] == []


def test_automata_linq_runtime_registry_exposes_adapters() -> None:
    runtime = get_world_runtime(WORLD)

    assert runtime.world == WORLD
    assert runtime.world_id == WORLD_ID
    assert runtime.scenarios == SCENARIO_NAMES
    assert runtime.http_surface == "available"
    assert runtime.create_http_app is not None
    assert {tool["function"]["name"] for tool in runtime.tool_definitions} == EXPECTED_TOOL_NAMES


def test_automata_linq_sample_episode_creates_run_files_and_state_tables(tmp_path: Path) -> None:
    episode = sample_episode(scenario="repair_invalid_workflow_plan", seed=17, out_dir=tmp_path / "run")

    assert episode.run_dir == (tmp_path / "run").resolve()
    assert episode.db_path.exists()
    assert episode.task_path.exists()
    assert episode.run_metadata_path.exists()
    assert (episode.run_dir / "artifacts").is_dir()
    assert (episode.run_dir / "traces").is_dir()

    run_metadata = json.loads((episode.run_dir / "run.json").read_text(encoding="utf-8"))
    task = json.loads((episode.run_dir / "task.json").read_text(encoding="utf-8"))
    assert run_metadata == {
        "mode": "dry_run",
        "scenario": "repair_invalid_workflow_plan",
        "seed": 17,
        "state_db": "state.sqlite",
        "task": "task.json",
        "world": WORLD,
        "world_id": WORLD_ID,
    }
    assert task["world"] == WORLD
    assert task["world_id"] == WORLD_ID
    assert task["scenario"] == "repair_invalid_workflow_plan"
    assert "metadata.repaired_from_workflow_id" in task["prompt"]
    assert "Validate the repaired workflow" in task["prompt"]

    with sqlite3.connect(episode.db_path) as conn:
        table_names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        scenario_event = conn.execute(
            "SELECT payload_json FROM events WHERE event_type = 'scenario.seeded'"
        ).fetchone()

    assert REQUIRED_TABLES <= table_names
    assert scenario_event is not None


def test_automata_linq_create_world_session_manifest_for_adapter_runtime(tmp_path: Path) -> None:
    manifest = create_world_session(
        world=WORLD,
        scenario="stale_plan_recompute",
        seed=23,
        out_dir=tmp_path / "session",
    )

    assert manifest["schema_version"] == "api_gym.world_session.v0"
    assert manifest["world"] == WORLD
    assert manifest["world_id"] == WORLD_ID
    assert manifest["scenario"] == "stale_plan_recompute"
    assert manifest["mode"] == "dry_run"
    assert manifest["expected_tools"] == sorted(EXPECTED_TOOL_NAMES)
    assert manifest["http"] == {
        "available": True,
        "recommended_command": ["api-gym", "serve", "--run", manifest["run_dir"]],
        "recommended_base_url": "http://127.0.0.1:8080",
        "trace_path": str(Path(manifest["run_dir"]) / "traces" / "http_requests.jsonl"),
    }
    assert list(manifest["mcp"]["mcpServers"]) == ["api-gym-automata-linq-workflow-planning-v0"]
    assert (Path(manifest["run_dir"]) / "agent_task.json").exists()


def test_automata_linq_fresh_sampled_run_verifier_is_false(tmp_path: Path) -> None:
    episode = sample_episode(scenario="live_action_boundary", seed=31, out_dir=tmp_path / "run")

    result = verify_run(episode.run_dir)

    assert result.ok is False
    assert result.scenario == "live_action_boundary"
    checks = result.to_dict()["checks"]
    assert any(check["name"] == "final_validation_valid" and check["ok"] is False for check in checks)
    assert any(check["name"] == "completed_plan_exists" and check["ok"] is False for check in checks)


def test_automata_linq_all_scenarios_sample(tmp_path: Path) -> None:
    assert set(SCENARIOS) == SCENARIO_NAMES
    for scenario in sorted(SCENARIOS):
        episode = sample_episode(scenario=scenario, seed=41, out_dir=tmp_path / scenario)
        assert episode.task["scenario"] == scenario
