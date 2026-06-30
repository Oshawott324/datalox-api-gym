"""Oracle execution for generated LabLongRun-Wet tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from greenfield_lablongrun.core.sandbox import RunSandbox, create_run_from_bundle
from greenfield_lablongrun.core.schemas import read_json


def run_oracle(task_bundle_dir: Path, run_dir: Path, *, clean: bool = True) -> RunSandbox:
    sandbox = create_run_from_bundle(task_bundle_dir, run_dir, label="oracle", clean=clean)
    plan = read_json(task_bundle_dir / "hidden" / "oracle_plan.json")["steps"]
    execute_plan(sandbox, plan)
    return sandbox


def run_known_bad_plan(
    task_bundle_dir: Path,
    run_dir: Path,
    *,
    plan_id: str | None = None,
    clean: bool = True,
) -> RunSandbox:
    plans = read_json(task_bundle_dir / "hidden" / "known_bad_plans.json")["plans"]
    if not plans:
        raise RuntimeError("Task bundle does not define any known-bad plans.")
    selected = next((plan for plan in plans if plan["plan_id"] == plan_id), None) if plan_id else plans[0]
    if selected is None:
        raise RuntimeError(f"Task bundle does not define known-bad plan {plan_id!r}.")

    sandbox = create_run_from_bundle(
        task_bundle_dir,
        run_dir,
        label=f"known_bad_{selected['plan_id']}",
        clean=clean,
    )
    plan = selected["steps"]
    execute_plan(sandbox, plan)
    return sandbox


def execute_plan(sandbox: RunSandbox, plan: list[dict[str, Any]]) -> None:
    last_readout_id: str | None = None
    for step in plan:
        arguments = _resolve_arguments(step.get("arguments", {}), last_readout_id)
        result = sandbox.call_tool(step["tool"], **arguments)
        if not result.get("ok"):
            raise RuntimeError(f"Oracle step failed for {step['tool']}: {result}")
        data = result.get("data") or {}
        if "readout_id" in data:
            last_readout_id = data["readout_id"]


def _resolve_arguments(arguments: dict[str, Any], last_readout_id: str | None) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for key, value in arguments.items():
        if value == "$last_readout_id":
            if last_readout_id is None:
                raise RuntimeError("Plan referenced $last_readout_id before any readout was created.")
            resolved[key] = last_readout_id
        else:
            resolved[key] = value
    return resolved
