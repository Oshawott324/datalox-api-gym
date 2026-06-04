#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from world_runtime import WORLD_ROOT, WorldError, create_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run oracle or bad-answer checks against the runnable-world preview.")
    parser.add_argument("--task", required=True, choices=["fastq-qc-nanopore-fail-001", "molecule-primer-validation-001"])
    parser.add_argument("--mode", required=True, choices=["oracle", "bad"])
    parser.add_argument("--run", help="Optional run directory. Defaults to a temporary directory.")
    args = parser.parse_args()
    try:
        with maybe_temp_run(args.run) as run_dir:
            create_run(args.task, run_dir)
            workspace = run_dir / "workspace"
            drive_task(workspace, args.task)
            answer_name = "expected.pass.json" if args.mode == "oracle" else "expected.fail.json"
            answer_path = WORLD_ROOT / "tasks" / args.task / "verifier" / answer_name
            completed = subprocess.run(
                [str(workspace / "submit_answer"), str(answer_path)],
                cwd=workspace,
                text=True,
                capture_output=True,
            )
            if completed.returncode != 0:
                raise WorldError(completed.stderr)
            result = json.loads(completed.stdout)
            ok = result["passed"] is True if args.mode == "oracle" else result["passed"] is False
            print(json.dumps({
                "ok": ok,
                "task_id": args.task,
                "mode": args.mode,
                "run_dir": str(run_dir),
                "verifier_passed": result["passed"],
                "reward": result["reward"],
            }, indent=2, sort_keys=True))
            return 0 if ok else 1
    except WorldError as error:
        print(str(error), file=sys.stderr)
        return 1


class maybe_temp_run:
    def __init__(self, requested: str | None):
        self.requested = requested
        self.tmp: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        if self.requested:
            return Path(self.requested).resolve()
        self.tmp = tempfile.TemporaryDirectory(prefix="datalox-runnable-world-")
        return Path(self.tmp.name) / "run"

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.tmp:
            self.tmp.cleanup()


def drive_task(workspace: Path, task_id: str) -> None:
    if task_id == "fastq-qc-nanopore-fail-001":
        call(workspace, "workspace.list_files", {})
        call(workspace, "artifact.read_text", {"path": "artifacts/fastqc_data.txt"})
        report = call(workspace, "fastqc.parse_report", {"path": "artifacts/fastqc_data.txt"})
        call(workspace, "qc_policy.evaluate", {"report_ref": report["evidence_id"]})
        return
    if task_id == "molecule-primer-validation-001":
        call(workspace, "open_sequence", {"path": "artifacts/circular.gb", "molecule_id": "mol_circular"})
        call(workspace, "get_sequence_context", {"molecule_id": "mol_circular", "include_sequence": True})
        call(workspace, "upsert_primer", {
            "expected_revision": 0,
            "primer": {
                "id": "primer_seed_fwd",
                "name": "seed forward primer",
                "sequence": "ACGT",
                "molecule_id": "mol_circular",
            },
        })
        call(workspace, "validate_workspace", {})
        return
    raise WorldError(f"Unhandled task: {task_id}")


def call(workspace: Path, tool_name: str, arguments: dict) -> dict:
    completed = subprocess.run(
        [str(workspace / "datalox_tool"), tool_name, json.dumps(arguments)],
        cwd=workspace,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise WorldError(completed.stderr)
    return json.loads(completed.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
