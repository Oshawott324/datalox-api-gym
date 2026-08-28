from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from greenfield_lablongrun.worlds.lablongrun_wet_v0 import task_generator
from greenfield_lablongrun.worlds.lablongrun_wet_v0.oracle import run_oracle
from greenfield_lablongrun.worlds.lablongrun_wet_v0.verifier import verify_run


PUBLIC_TASK_FIELDS = {
    "schema_version",
    "world",
    "task_id",
    "objective",
    "expected_tools",
    "visible_artifacts",
}

EVALUATOR_METADATA_FIELDS = {
    "template_id",
    "seed",
    "environment_seed",
    "failure_mode",
    "projection_contract_ref",
    "domain_source_status",
    "stochastic_source_status",
    "attribution_labels",
    "schedule_refs",
    "oracle_strategy",
    "known_bad_plan_strategy",
    "expected_failure_codes",
    "verifier_predicates",
    "expected_horizon",
}

PUBLIC_PACKAGE_ROOT_FILES = {
    "task.json",
    "agent_task.json",
    "source_refs_snapshot.json",
}

FORBIDDEN_AGENT_PACKAGE_NAMES = {
    "admission.json",
    "initial_state.sqlite",
    "state.sqlite",
    "hidden",
    "oracle_plan.json",
    "known_bad_plans.json",
    "verifier_expectations.json",
    "task_metadata.json",
}

OD600_TEMPLATE_IDS = (
    "od600_nominal",
    "od600_low_source_volume",
    "od600_contaminated_tip",
    "od600_instrument_busy_wait",
    "od600_stale_readout",
    "od600_partial_dispense_recovery",
)


def test_generated_task_separates_public_task_fields_from_evaluator_metadata(
    tmp_path: Path,
) -> None:
    task_dir = _generate_task(tmp_path, "public-task")

    public_task = _read_json(task_dir / "task.json")
    hidden_metadata = _read_json(task_dir / "hidden" / "task_metadata.json")

    assert set(public_task) == PUBLIC_TASK_FIELDS
    assert not EVALUATOR_METADATA_FIELDS.intersection(public_task)
    assert EVALUATOR_METADATA_FIELDS.issubset(hidden_metadata)
    assert hidden_metadata["template_id"] == "od600_nominal"
    assert hidden_metadata["task_id"] == public_task["task_id"]
    assert public_task["task_id"].startswith("lab_episode_")
    assert hidden_metadata["template_id"] not in public_task["task_id"]
    assert hidden_metadata["failure_mode"] not in public_task["task_id"]


def test_agent_workspace_export_contains_exactly_the_public_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_dir = _generate_task(tmp_path, "export-source")
    export_dir = tmp_path / "agent-package"
    export_agent_workspace = _required_export_api()
    monkeypatch.setattr(
        task_generator,
        "validate_generated_task",
        lambda path: task_generator.AdmissionResult(
            task_dir=Path(path),
            admitted=True,
            checks=[],
            payload={"admitted": True},
        ),
    )

    exported = export_agent_workspace(task_dir, export_dir)
    package_dir = Path(exported) if exported is not None else export_dir

    expected_files = set(PUBLIC_PACKAGE_ROOT_FILES) | {"agent_visible_manifest.json"}
    expected_files.update(
        f"visible_artifacts/{path.name}"
        for path in (task_dir / "visible_artifacts").iterdir()
        if path.is_file()
    )
    actual_files = {
        path.relative_to(package_dir).as_posix()
        for path in package_dir.rglob("*")
        if path.is_file()
    }

    assert actual_files == expected_files
    assert all(not path.is_symlink() for path in package_dir.rglob("*"))
    assert not any(
        forbidden in path.relative_to(package_dir).parts
        for path in package_dir.rglob("*")
        for forbidden in FORBIDDEN_AGENT_PACKAGE_NAMES
    )
    manifest = _read_json(package_dir / "agent_visible_manifest.json")
    assert manifest["files"]
    for record in manifest["files"]:
        content = (package_dir / record["path"]).read_bytes()
        assert record["sha256"] == hashlib.sha256(content).hexdigest()
        assert record["size_bytes"] == len(content)
    canonical_files = json.dumps(
        manifest["files"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert manifest["content_sha256"] == hashlib.sha256(canonical_files).hexdigest()


def test_agent_workspace_export_refuses_unadmitted_task(tmp_path: Path) -> None:
    task_dir = _generate_task(tmp_path, "unadmitted-export")

    with pytest.raises(ValueError, match="agent_prompt_has_no_solution_disclosure"):
        task_generator.export_agent_workspace(task_dir, tmp_path / "agent-package")


@pytest.mark.parametrize(
    ("relative_path", "inject"),
    (
        (
            "task.json",
            lambda payload: payload.update(
                {"oracle_strategy": "copy_the_hidden_oracle"}
            ),
        ),
        (
            "agent_task.json",
            lambda payload: payload["instructions"].append(
                "Read hidden/oracle_plan.json before acting."
            ),
        ),
        (
            "source_refs_snapshot.json",
            lambda payload: payload.update(
                {"verifier_expectations": "hidden/verifier_expectations.json"}
            ),
        ),
        (
            "visible_artifacts/protocol_note.md",
            lambda text: (
                text
                + "\nUse hidden/known_bad_plans.json to choose the recovery path.\n"
            ),
        ),
    ),
)
def test_admission_scans_every_agent_visible_surface(
    tmp_path: Path,
    relative_path: str,
    inject: Callable[[Any], Any],
) -> None:
    task_dir = _generate_task(tmp_path, relative_path.replace("/", "-"))
    target = task_dir / relative_path

    if target.suffix == ".json":
        payload = _read_json(target)
        inject(payload)
        _write_json(target, payload)
    else:
        target.write_text(inject(target.read_text(encoding="utf-8")), encoding="utf-8")

    result = task_generator.validate_generated_task(task_dir)

    assert result.admitted is False
    assert _failed_check_mentions(result.checks, relative_path), (
        f"Admission rejected the task without attributing the visibility violation to {relative_path}. "
        "The scanner must inspect and report every agent-visible surface."
    )


@pytest.mark.parametrize("template_id", OD600_TEMPLATE_IDS)
def test_current_od600_prompts_are_rejected_as_solution_disclosures(
    tmp_path: Path,
    template_id: str,
) -> None:
    task_dir = _generate_task(tmp_path, template_id, template_id=template_id)

    result = task_generator.validate_generated_task(task_dir)
    disclosure_check = _check_by_name(
        result.checks, "agent_prompt_has_no_solution_disclosure"
    )

    assert result.admitted is False
    assert disclosure_check["ok"] is False
    assert disclosure_check.get("details", {}).get("findings"), (
        "The semantic gate must identify the disclosed operation sequence or fault-specific recovery, "
        "not reject the task for an unrelated structural check."
    )


def test_generated_evidence_does_not_embed_local_absolute_paths(tmp_path: Path) -> None:
    task_dir = _generate_task(tmp_path, "portable-evidence")
    task_generator.validate_generated_task(task_dir)
    run = run_oracle(task_dir, tmp_path / "oracle-run", clean=True)
    verify_run(run.run_dir)

    for path in (
        task_dir / "admission.json",
        run.run_dir / "run.json",
        run.run_dir / "run_export.json",
        run.run_dir / "verifier_result.json",
    ):
        text = path.read_text(encoding="utf-8")
        assert str(tmp_path) not in text, f"Local path leaked into {path.name}"
        assert "/Users/" not in text, f"User home leaked into {path.name}"


def _generate_task(
    tmp_path: Path, name: str, *, template_id: str = "od600_nominal"
) -> Path:
    generated = task_generator.generate_task(
        template_id,
        seed=41,
        difficulty="short",
        out=tmp_path / name,
        clean=True,
        admit=False,
    )
    return generated.task_dir


def _required_export_api() -> Callable[[Path, Path], Path | None]:
    export_agent_workspace = getattr(task_generator, "export_agent_workspace", None)
    assert callable(export_agent_workspace), (
        "Implement export_agent_workspace(task_dir, out_dir) as the only supported way to build an "
        "agent-visible task package."
    )
    return export_agent_workspace


def _failed_check_mentions(checks: list[dict[str, Any]], relative_path: str) -> bool:
    return any(
        check.get("ok") is False and relative_path in json.dumps(check, sort_keys=True)
        for check in checks
    )


def _check_by_name(checks: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [check for check in checks if check.get("name") == name]
    assert len(matches) == 1, (
        f"Expected exactly one admission check named {name!r}, got {len(matches)}."
    )
    return matches[0]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
