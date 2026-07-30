from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("datalox_gated_runtime.world_v1.admission")

import datalox_gated_runtime
from datalox_gated_runtime.world_v1.admission import admit_world
from datalox_gated_runtime.world_v1.admission_runtime import (
    runtime_admission_callbacks,
)
from datalox_gated_runtime.world_v1.backend import (
    WorldBundleBackend,
    initialize_world_bundle_session,
)
from datalox_gated_runtime.world_v1.bundle import validate_world_bundle
from datalox_gated_runtime.world_v1.contracts import ActorContext
from datalox_gated_runtime.world_v1.contracts import TaskBrief

from api_gym.worlds.source_refs import validate_world_source_refs

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SRC = Path(datalox_gated_runtime.__file__).resolve().parents[1]
WORLD = REPO_ROOT / "worlds" / "science_elabftw_cromwell_v0"
BUILDER = (
    REPO_ROOT / "scripts" / "worlds" / "build_science_elabftw_cromwell.py"
)
TRAJECTORIES = WORLD / "tests" / "trajectories" / "analysis.json"
ELAB_SOURCE = (
    REPO_ROOT
    / "api_gym"
    / "provider_components"
    / "elabftw"
    / "analysis_projection.py"
)
CROMWELL_SOURCE = (
    REPO_ROOT
    / "api_gym"
    / "provider_components"
    / "cromwell"
    / "analysis_projection.py"
)
FAMILIES = {
    "analysis_nominal_v1",
    "analysis_transient_visibility_v1",
    "analysis_existing_run_resume_v1",
    "analysis_failure_recovery_v1",
    "analysis_superseded_abort_v1",
    "analysis_stale_revision_v1",
}
RESULT_TITLE = "Analysis-control qualification handoff"
RESULT_BODY = (
    "The captured Cromwell program qualified for evidence handoff. "
    "This record makes no biological or scientific inference."
)
COMMON_PUBLIC_REQUIREMENT_IDS = {
    f"SCI-PUB-{index:03d}" for index in range(1, 11)
}
TRANSIENT_PUBLIC_REQUIREMENT_ID = "SCI-PUB-TR-001"
FAMILY_PUBLIC_REQUIREMENT_IDS = {
    "analysis_transient_visibility_v1": TRANSIENT_PUBLIC_REQUIREMENT_ID,
    "analysis_existing_run_resume_v1": "SCI-PUB-ER-001",
    "analysis_failure_recovery_v1": "SCI-PUB-FR-001",
    "analysis_superseded_abort_v1": "SCI-PUB-SA-001",
    "analysis_stale_revision_v1": "SCI-PUB-SR-001",
}


def _subprocess_env() -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(RUNTIME_SRC), str(REPO_ROOT))),
    }


def _trajectory(trajectory_id: str) -> dict[str, object]:
    trajectories = json.loads(TRAJECTORIES.read_text())["trajectories"]
    return next(item for item in trajectories if item["id"] == trajectory_id)


def _run_steps(
    tmp_path: Path,
    *,
    run_name: str,
    episode_id: str,
    steps: list[dict[str, object]],
) -> WorldBundleBackend:
    run_dir = tmp_path / run_name
    initialize_world_bundle_session(
        source_bundle_dir=WORLD,
        run_dir=run_dir,
        episode_id=episode_id,
    )
    backend = WorldBundleBackend(run_dir=run_dir)
    actor = ActorContext("science-agent", "scientist_agent")
    try:
        for step in steps:
            response = backend.handle(
                backend.request_for_tool(
                    step["tool_name"],
                    step["arguments"],
                    actor=actor,
                )
            )
            assert response is not None
    except Exception:
        backend.close()
        raise
    return backend


def _run_reference(
    tmp_path: Path,
    trajectory_id: str,
) -> tuple[WorldBundleBackend, dict[str, object]]:
    trajectory = _trajectory(trajectory_id)
    backend = _run_steps(
        tmp_path,
        run_name=trajectory_id,
        episode_id=str(trajectory["episode_id"]),
        steps=trajectory["steps"],
    )
    return backend, trajectory


def test_world_build_is_deterministic_self_contained_and_grounded() -> None:
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        WORLD / "world" / "v1" / "provider_elabftw.py"
    ).read_bytes() == ELAB_SOURCE.read_bytes()
    assert (
        WORLD / "world" / "v1" / "provider_cromwell.py"
    ).read_bytes() == CROMWELL_SOURCE.read_bytes()

    bundle = validate_world_bundle(WORLD)
    assert bundle.manifest.world_id == "science_elabftw_cromwell_v0"
    assert len(bundle.episodes) == 12
    assert {episode["family_id"] for episode in bundle.episodes} == FAMILIES
    assert {
        family: sum(episode["family_id"] == family for episode in bundle.episodes)
        for family in FAMILIES
    } == {family: 2 for family in FAMILIES}
    assert len(bundle.tools) == 10
    assert {source["grounding_level"] for source in bundle.sources} == {
        "G0_BENCHMARK_DEFINED",
        "G2_LOCAL_EXECUTED",
    }
    assert validate_world_source_refs(
        "science_elabftw_cromwell_v0",
        repo_root=REPO_ROOT,
    ) == {
        "ok": True,
        "world": "science_elabftw_cromwell_v0",
        "source_pack_count": 0,
        "world_evidence_count": 4,
        "missing_records": [],
        "missing_world_evidence": [],
    }
    compatibility = json.loads((WORLD / "compatibility.json").read_text())
    assert compatibility["runtime"]["tested_git_commit"] == "15689da"
    assert compatibility["providers"]["elabftw"]["captured_version"] == "5.6.10"
    assert compatibility["providers"]["cromwell"]["captured_version"] == "92"

    manifest = json.loads((WORLD / "world" / "manifest.json").read_text())
    assert set(manifest["content_hashes"]) == {
        path.relative_to(WORLD).as_posix()
        for path in WORLD.rglob("*")
        if path.is_file()
        and path != WORLD / "world" / "manifest.json"
        and "__pycache__" not in path.parts
        and path.name != "world_admission.json"
    }
    assert not any(
        key in json.dumps(bundle.episodes)
        for key in ("expected_failure_codes", "verifier_answers", "hidden_verifier")
    )


def test_agent_visible_task_briefs_publish_complete_family_contracts() -> None:
    bundle = validate_world_bundle(WORLD)
    verifier = json.loads(
        (WORLD / "world" / "v1" / "verifier.json").read_text()
    )
    hidden_codes = {
        assertion["failure_code"] for assertion in verifier["assertions"]
    }
    common_mapping = {
        "analysis.source_inspected_before_action": {"SCI-PUB-001"},
        "analysis.submissions_match_source": {"SCI-PUB-001"},
        "analysis.current_terminal_success": {"SCI-PUB-003"},
        "analysis.success_outputs_metadata_inspected": {"SCI-PUB-003"},
        "analysis.result_record_lifecycle": {"SCI-PUB-007"},
        "analysis.result_record_content_contract": {"SCI-PUB-008"},
        "analysis.result_record_exact_join": {"SCI-PUB-005", "SCI-PUB-006", "SCI-PUB-009"},
        "analysis.writeback_source_current": {"SCI-PUB-004"},
        "analysis.cross_provider_ordering": {"SCI-PUB-004", "SCI-PUB-007"},
        "analysis.no_unnecessary_duplicate_submission": {"SCI-PUB-010"},
        "analysis.no_forbidden_collateral": {"SCI-PUB-010"},
    }
    family_mappings = {
        "analysis_nominal_v1": common_mapping,
        "analysis_transient_visibility_v1": {
            **common_mapping,
            "analysis.required_transient_observation": {
                TRANSIENT_PUBLIC_REQUIREMENT_ID
            },
        },
        "analysis_existing_run_resume_v1": {
            **common_mapping,
            "analysis.source_inspected_before_action": {
                "SCI-PUB-001",
                "SCI-PUB-ER-001",
            },
            "analysis.current_terminal_success": {
                "SCI-PUB-003",
                "SCI-PUB-ER-001",
            },
            "analysis.no_unnecessary_duplicate_submission": {
                "SCI-PUB-010",
                "SCI-PUB-ER-001",
            },
        },
        "analysis_failure_recovery_v1": {
            **common_mapping,
            "analysis.required_failure_recovery": {"SCI-PUB-FR-001"},
        },
        "analysis_superseded_abort_v1": {
            **common_mapping,
            "analysis.required_superseded_abort": {"SCI-PUB-SA-001"},
        },
        "analysis_stale_revision_v1": {
            **common_mapping,
            "analysis.required_stale_recovery": {"SCI-PUB-SR-001"},
        },
    }
    assert set(family_mappings) == FAMILIES
    assert (
        set().union(*(mapping.keys() for mapping in family_mappings.values()))
        == hidden_codes
    )

    for episode in bundle.episodes:
        task = TaskBrief(**episode["task"])
        visible = task.instructions + "\n" + "\n".join(task.success_criteria)
        requirement_ids = set(
            re.findall(r"SCI-PUB-(?:(?:TR|ER|FR|SA|SR)-)?\d{3}", visible)
        )
        assert COMMON_PUBLIC_REQUIREMENT_IDS <= requirement_ids
        expected_mapping = family_mappings[episode["family_id"]]
        for required_ids in expected_mapping.values():
            assert required_ids <= requirement_ids
        expected_family_id = FAMILY_PUBLIC_REQUIREMENT_IDS.get(
            episode["family_id"]
        )
        visible_family_ids = requirement_ids & set(
            FAMILY_PUBLIC_REQUIREMENT_IDS.values()
        )
        assert visible_family_ids == (
            {expected_family_id} if expected_family_id is not None else set()
        )

        assert "only through clock.advance" in visible
        assert "Repeated polling without clock.advance neither progresses" in visible
        assert "re-read the source immediately before creating or writing" in visible
        assert "outputs object inside the body returned" in visible
        assert "entire body returned by cromwell.get_workflow_metadata" in visible
        assert "exactly these eight keys and no others" in visible
        assert RESULT_TITLE in visible
        assert RESULT_BODY in visible
        assert "make no biological or scientific inference" in visible
        assert not any(code in visible for code in hidden_codes)
        assert not re.search(r"sha256:[0-9a-f]{64}", visible)
        assert not re.search(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{4}-[0-9a-f]{12}\b",
            visible,
        )
        assert not any(
            leak in visible
            for leak in (
                "expected_failure_codes",
                "failure_codes",
                "verifier_answers",
                "hidden_verifier",
                "expected_agent_submission_count",
            )
        )

        family_requirement_text = next(
            (
                criterion
                for criterion in task.success_criteria
                if expected_family_id is not None
                and expected_family_id in criterion
            ),
            "",
        )
        if episode["family_id"] == "analysis_transient_visibility_v1":
            assert "exactly one workflow submission" in family_requirement_text
            assert (
                "HTTP 404, then Submitted, then Succeeded"
                in family_requirement_text
            )
            assert "clock.advance between each" in family_requirement_text
        elif episode["family_id"] == "analysis_existing_run_resume_v1":
            assert "in-flight workflow referenced by the source" in family_requirement_text
            assert "no duplicate workflow submission" in family_requirement_text
        elif episode["family_id"] == "analysis_failure_recovery_v1":
            assert "explicitly observe the failed workflow in Failed" in family_requirement_text
            assert "both its logs and its entire metadata" in family_requirement_text
            assert "re-read the corrected current source" in family_requirement_text
            assert "before making a new workflow submission" in family_requirement_text
        elif episode["family_id"] == "analysis_superseded_abort_v1":
            assert "referenced by the source in Running" in family_requirement_text
            assert "then abort it" in family_requirement_text
            assert "observe it in Aborted" in family_requirement_text
            assert "then submit the current source" in family_requirement_text
        elif episode["family_id"] == "analysis_stale_revision_v1":
            assert (
                "older completed workflow in terminal Succeeded status"
                in family_requirement_text
            )
            assert "its outputs and its entire metadata" in family_requirement_text
            assert "re-read the current source" in family_requirement_text
            assert "exactly one current workflow submission" in family_requirement_text
            assert "do not attach evidence from the stale workflow" in family_requirement_text
        else:
            assert family_requirement_text == ""


def test_fresh_process_can_initialize_self_contained_bundle(
    tmp_path: Path,
) -> None:
    script = """
from pathlib import Path
from datalox_gated_runtime.world_v1.backend import (
    WorldBundleBackend,
    initialize_world_bundle_session,
)

world = Path({world!r})
run_dir = Path({run_dir!r})
initialize_world_bundle_session(
    source_bundle_dir=world,
    run_dir=run_dir,
    episode_id="science-analysis-000",
)
backend = WorldBundleBackend(run_dir=run_dir)
backend.close()
""".format(
        world=str(WORLD),
        run_dir=str(tmp_path / "fresh-process-run"),
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_world_trajectories_cover_all_families_and_exact_negative_sets() -> None:
    trajectories = json.loads(TRAJECTORIES.read_text())["trajectories"]
    references = [item for item in trajectories if item["kind"] == "reference"]
    negatives = [item for item in trajectories if item["kind"] == "negative"]
    parity = [item for item in trajectories if item["kind"] == "parity"]

    assert len(references) == 13
    assert len(negatives) == 12
    assert len(parity) == 3
    assert {item["family_id"] for item in references} == FAMILIES
    assert {
        item["family_id"]
        for item in negatives
        if item["id"].startswith("negative-empty-")
    } == FAMILIES
    assert {
        item["family_id"]
        for item in negatives
        if item["id"].startswith("negative-mutant-")
    } == FAMILIES
    assert any(item["id"] == "alternative-failure-recovery" for item in references)
    assert all(
        item["expected"]["passed"] is True
        and item["expected"]["failure_codes"] == []
        for item in references
    )
    assert all(
        item["expected"]["passed"] is False
        and item["expected"]["failure_codes"]
        for item in negatives
    )

    family_contracts = {
        path.stem: json.loads(path.read_text())
        for path in (WORLD / "family_contracts").glob("*.json")
    }
    for item in negatives:
        contract = family_contracts[item["family_id"]]
        expected_key = (
            "empty_failure_codes"
            if item["id"].startswith("negative-empty-")
            else "known_bad_failure_codes"
        )
        assert item["expected"]["failure_codes"] == contract["admission"][expected_key]


def test_world_full_runtime_admission_passes() -> None:
    report = admit_world(
        WORLD,
        callbacks=runtime_admission_callbacks(),
        admitted_at="2026-07-30T00:00:00+00:00",
    )

    assert report.admitted is True
    payload = report.to_dict()
    assert payload["coverage"] == {
        "episode_count": 12,
        "negative_trajectory_count": 12,
        "operation_families": [
            "analysis_record",
            "logical_time",
            "workflow_execution",
        ],
        "parity_case_count": 3,
        "reference_trajectory_count": 13,
        "role_count": 1,
        "tool_count": 10,
        "trajectory_count": 28,
    }
    assert all(check["passed"] for check in payload["checks"].values())


def test_transient_visibility_and_non_idempotent_submit_are_provider_shaped(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "transient"
    initialize_world_bundle_session(
        source_bundle_dir=WORLD,
        run_dir=run_dir,
        episode_id="science-analysis-002",
    )
    backend = WorldBundleBackend(run_dir=run_dir)
    actor = ActorContext("science-agent", "scientist_agent")
    try:
        source = backend.handle(
            backend.request_for_tool(
                "elabftw.get_experiment",
                {"experiment_id": 4102},
                actor=actor,
            )
        )
        assert source is not None
        metadata = source.body["metadata_decoded"]
        arguments = {
            "workflowSource": metadata["workflow_source"],
            "workflowInputs": metadata["workflow_inputs"],
        }
        first = backend.handle(
            backend.request_for_tool(
                "cromwell.submit_workflow",
                arguments,
                actor=actor,
            )
        )
        second = backend.handle(
            backend.request_for_tool(
                "cromwell.submit_workflow",
                arguments,
                actor=actor,
            )
        )
        assert first is not None and second is not None
        assert first.status_code == second.status_code == 201
        assert first.body["status"] == second.body["status"] == "Submitted"
        assert first.body["id"] != second.body["id"]

        status = backend.handle(
            backend.request_for_tool(
                "cromwell.get_workflow_status",
                {"workflow_id": first.body["id"]},
                actor=actor,
            )
        )
        assert status is not None
        assert status.status_code == 404
        assert status.body == {
            "message": f"Unrecognized workflow ID: {first.body['id']}",
            "status": "fail",
        }
    finally:
        backend.close()


def test_reference_handoff_has_exact_joins_and_vector_only_fast_verifier(
    tmp_path: Path,
) -> None:
    backend, _ = _run_reference(
        tmp_path,
        "reference-science-analysis-000",
    )
    actor = ActorContext("science-agent", "scientist_agent")
    try:
        result = backend.verify()
        payload = result.to_dict()
        assert payload["passed"] is True
        assert payload["failure_codes"] == []
        assert len(payload["checks"]) == 15
        assert "reward" not in payload
        assert "score" not in payload

        evidence = payload["public_evidence"]
        result_id = evidence["result_record"]["experiment_id"]
        readback = backend.handle(
            backend.request_for_tool(
                "elabftw.get_experiment",
                {"experiment_id": result_id},
                actor=actor,
            )
        )
        assert readback is not None
        assert readback.body["title"] == RESULT_TITLE
        assert readback.body["body"] == RESULT_BODY
        metadata = readback.body["metadata_decoded"]
        assert metadata == {
            "cromwell_terminal_status": "Succeeded",
            "cromwell_workflow_id": evidence["accepted_workflow"]["workflow_id"],
            "handoff_kind": "analysis-control/qualification",
            "metadata_digest": evidence["accepted_workflow"]["metadata_digest"],
            "outputs_digest": evidence["accepted_workflow"]["outputs_digest"],
            "source_content_digest": evidence["source"]["content_digest"],
            "source_experiment_id": evidence["source"]["experiment_id"],
            "source_revision": evidence["source"]["revision"],
        }

        timings = []
        for _ in range(40):
            started = time.perf_counter()
            assert backend.verify().passed is True
            timings.append((time.perf_counter() - started) * 1000)
        p95 = sorted(timings)[int(len(timings) * 0.95) - 1]
        assert p95 < 100
    finally:
        backend.close()


def test_failure_and_abort_evidence_is_native_and_never_exposes_physical_paths(
    tmp_path: Path,
) -> None:
    failure_backend, _ = _run_reference(
        tmp_path,
        "reference-science-analysis-006",
    )
    abort_backend, _ = _run_reference(
        tmp_path,
        "reference-science-analysis-008",
    )
    try:
        failure_evidence = failure_backend.verify().to_dict()["public_evidence"]
        failed = failure_evidence["diagnosed_failure"]
        assert failed["status"] == "Failed"
        assert failed["return_code"] == 23
        assert failed["retryable_failure"] is False

        abort_evidence = abort_backend.verify().to_dict()["public_evidence"]
        superseded = abort_evidence["superseded_workflow"]
        assert superseded["abort_requested"] is True
        assert superseded["aborted_observed"] is True
        assert superseded["status"] == "Aborted"

        exports = json.dumps(
            [
                failure_backend.session.export(),
                abort_backend.session.export(),
            ],
            sort_keys=True,
        )
        assert "/tmp/datalox-cromwell" not in exports
        assert "datalox-world://cromwell/" in exports
    finally:
        failure_backend.close()
        abort_backend.close()


def test_result_record_rejects_scientific_claim_text_even_with_exact_join(
    tmp_path: Path,
) -> None:
    trajectory = _trajectory("reference-science-analysis-000")
    steps = json.loads(json.dumps(trajectory["steps"]))
    patch = next(
        step
        for step in steps
        if step["tool_name"] == "elabftw.patch_experiment"
    )
    patch["arguments"]["title"] = "EGFR binding result"
    patch["arguments"]["body"] = "The tested sequence binds EGFR."

    backend = _run_steps(
        tmp_path,
        run_name="scientific-claim-exploit",
        episode_id=str(trajectory["episode_id"]),
        steps=steps,
    )
    try:
        result = backend.verify().to_dict()
        assert result["passed"] is False
        assert result["failure_codes"] == [
            "analysis.result_record_content_contract"
        ]
    finally:
        backend.close()


def test_stale_family_requires_inspection_of_distinct_seeded_revision(
    tmp_path: Path,
) -> None:
    trajectory = _trajectory("reference-science-analysis-010")
    episode = next(
        json.loads(line)
        for line in (
            WORLD / "world" / "v1" / "episodes.jsonl"
        ).read_text().splitlines()
        if json.loads(line)["id"] == trajectory["episode_id"]
    )
    revisions = episode["state"]["source"]["revisions"]
    assert revisions["1"]["content_digest"] != revisions["2"]["content_digest"]
    assert revisions["1"]["qualification_context"] != revisions["2"][
        "qualification_context"
    ]
    stale_id = episode["state"]["source"]["current_workflow_id"]
    shortcut = [
        step
        for step in trajectory["steps"]
        if step["arguments"].get("workflow_id") != stale_id
    ]

    backend = _run_steps(
        tmp_path,
        run_name="stale-current-only-exploit",
        episode_id=str(trajectory["episode_id"]),
        steps=shortcut,
    )
    try:
        result = backend.verify().to_dict()
        assert result["passed"] is False
        assert result["failure_codes"] == [
            "analysis.required_stale_recovery"
        ]
    finally:
        backend.close()


def test_transient_family_requires_404_and_submitted_observations(
    tmp_path: Path,
) -> None:
    trajectory = _trajectory("reference-science-analysis-002")
    skipped = []
    status_count = 0
    for step in trajectory["steps"]:
        if step["tool_name"] == "cromwell.get_workflow_status":
            status_count += 1
            if status_count <= 2:
                continue
        skipped.append(step)

    backend = _run_steps(
        tmp_path,
        run_name="transient-observation-exploit",
        episode_id=str(trajectory["episode_id"]),
        steps=skipped,
    )
    try:
        result = backend.verify().to_dict()
        assert result["passed"] is False
        assert result["failure_codes"] == [
            "analysis.required_transient_observation"
        ]
    finally:
        backend.close()


def test_agent_visible_provider_fields_are_coherent_projected_values(
    tmp_path: Path,
) -> None:
    backend, _ = _run_reference(
        tmp_path,
        "reference-science-analysis-000",
    )
    actor = ActorContext("science-agent", "scientist_agent")
    try:
        evidence = backend.verify().to_dict()["public_evidence"]
        source = backend.handle(
            backend.request_for_tool(
                "elabftw.get_experiment",
                {"experiment_id": evidence["source"]["experiment_id"]},
                actor=actor,
            )
        )
        result = backend.handle(
            backend.request_for_tool(
                "elabftw.get_experiment",
                {"experiment_id": evidence["result_record"]["experiment_id"]},
                actor=actor,
            )
        )
        metadata = backend.handle(
            backend.request_for_tool(
                "cromwell.get_workflow_metadata",
                {
                    "workflow_id": evidence["accepted_workflow"][
                        "workflow_id"
                    ]
                },
                actor=actor,
            )
        )
        assert source is not None and result is not None and metadata is not None
        visible = json.dumps(
            [source.body, result.body, metadata.body],
            sort_keys=True,
        )
        assert "localhost" not in visible
        assert "Antimicrobial resistance study" not in visible
        assert "2026-07-30T11:" not in visible
        assert "datalox-world://elabftw/" in visible
        assert metadata.body["submission"] == "2026-07-30T08:00:00.000Z"
        assert metadata.body["end"] == "2026-07-30T08:00:30.000Z"
    finally:
        backend.close()


def test_builder_check_fails_closed_without_mutating_or_adopting_files(
    tmp_path: Path,
) -> None:
    copied_world = tmp_path / "science_elabftw_cromwell_v0"
    shutil.copytree(WORLD, copied_world)
    unexpected = copied_world / "unexpected.json"
    unexpected.write_text('{"adopt_me":true}\n', encoding="utf-8")
    before_unexpected = {
        path.relative_to(copied_world): path.read_bytes()
        for path in copied_world.rglob("*")
        if path.is_file()
    }

    rejected = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--check",
            "--world-root",
            str(copied_world),
        ],
        cwd=REPO_ROOT,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    after_unexpected = {
        path.relative_to(copied_world): path.read_bytes()
        for path in copied_world.rglob("*")
        if path.is_file()
    }
    assert rejected.returncode == 2
    assert "unexpected files: unexpected.json" in rejected.stderr
    assert after_unexpected == before_unexpected

    unexpected.unlink()
    task = copied_world / "task.json"
    task.write_text('{"stale":true}\n', encoding="utf-8")
    before_stale = task.read_bytes()
    stale = subprocess.run(
        [
            sys.executable,
            str(BUILDER),
            "--check",
            "--world-root",
            str(copied_world),
        ],
        cwd=REPO_ROOT,
        env=_subprocess_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert stale.returncode == 1
    assert task.read_bytes() == before_stale
