"""Run sandbox for one generated task bundle."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenfield_lablongrun.core.schemas import read_json, write_json
from greenfield_lablongrun.core.trace import TraceRecorder


STATE_DB_NAME = "state.sqlite"


@dataclass(frozen=True)
class RunSandbox:
    run_dir: Path
    task_bundle_dir: Path
    db_path: Path
    trace: TraceRecorder

    def call_tool(self, name: str, **arguments: Any) -> dict[str, Any]:
        from greenfield_lablongrun.worlds.lablongrun_wet_v0.tools import dispatch_tool

        return dispatch_tool(self.db_path, self.trace, name=name, arguments=arguments)


def create_run_from_bundle(task_bundle_dir: Path, run_dir: Path, *, label: str, clean: bool = False) -> RunSandbox:
    task_bundle_dir = task_bundle_dir.resolve()
    run_dir = run_dir.resolve()
    if clean and run_dir.exists():
        shutil.rmtree(run_dir)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"Run directory already exists and is not empty: {run_dir}")

    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(task_bundle_dir / "initial_state.sqlite", run_dir / STATE_DB_NAME)
    for name in ("task.json", "agent_task.json", "source_refs_snapshot.json"):
        shutil.copy2(task_bundle_dir / name, run_dir / name)
    for directory in ("visible_artifacts", "hidden"):
        source = task_bundle_dir / directory
        if source.exists():
            shutil.copytree(source, run_dir / directory, dirs_exist_ok=True)

    task = read_json(task_bundle_dir / "task.json")
    run_metadata = {
        "schema_version": "greenfield_lablongrun.run.v0",
        "world": task["world"],
        "scenario": task["scenario"],
        "label": label,
        "task_bundle_dir": str(task_bundle_dir),
        "state_db": STATE_DB_NAME,
        "artifacts": {
            "task": "task.json",
            "agent_task": "agent_task.json",
            "tool_calls": "tool_calls.jsonl",
            "state_diffs": "state_diffs.jsonl",
            "verifier_result": "verifier_result.json",
            "run_export": "run_export.json",
        },
    }
    write_json(run_dir / "run.json", run_metadata)
    return RunSandbox(
        run_dir=run_dir,
        task_bundle_dir=task_bundle_dir,
        db_path=run_dir / STATE_DB_NAME,
        trace=TraceRecorder(run_dir),
    )

