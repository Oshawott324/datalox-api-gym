"""Run the greenfield LabLongRun-Wet Phase 2 prototype."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from greenfield_lablongrun.core.schemas import read_json, write_json
from greenfield_lablongrun.worlds.lablongrun_wet_v0.oracle import run_known_bad_plan, run_oracle
from greenfield_lablongrun.worlds.lablongrun_wet_v0.task_generator import generate_task
from greenfield_lablongrun.worlds.lablongrun_wet_v0.verifier import verify_run


PHASE2_TEMPLATES = [
    "od600_nominal",
    "od600_low_source_volume",
    "od600_contaminated_tip",
    "od600_instrument_busy_wait",
    "od600_stale_readout",
    "od600_partial_dispense_recovery",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LabLongRun-Wet Phase 2 demo.")
    parser.add_argument("--out", type=Path, default=Path("runs/greenfield_lablongrun_phase2"))
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    out = args.out.resolve()
    if args.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    projection_check_names = {
        "domain_source_status_present",
        "projection_contract_ref_present",
        "stochastic_source_status_valid",
        "projection_contract_file_exists",
        "projection_metadata_matches_template",
        "fault_schedule_deterministic_for_environment_seed",
        "noise_schedule_deterministic_for_environment_seed",
        "stochastic_none_has_empty_schedules",
        "known_bad_expected_failure_codes_match",
    }
    template_results = []
    for seed, template_id in enumerate(PHASE2_TEMPLATES, start=1):
        generated_task = generate_task(
            template_id,
            seed=seed,
            difficulty="short",
            out=out / "generated" / template_id,
            clean=True,
        )
        task_bundle = generated_task.task_dir
        admission = read_json(task_bundle / "admission.json")
        oracle_run = run_oracle(task_bundle, out / "runs" / template_id / "oracle", clean=True)
        oracle_result = verify_run(oracle_run.run_dir)
        bad_run_dir = out / "runs" / template_id / "known_bad"
        known_bad_error = None
        try:
            bad_run = run_known_bad_plan(task_bundle, bad_run_dir, clean=True)
            bad_result = verify_run(bad_run.run_dir)
            known_bad_failed = not bad_result.ok
            known_bad_trace_counts = bad_run.trace.counts()
        except RuntimeError as exc:
            known_bad_error = repr(exc)
            known_bad_failed = True
            known_bad_trace_counts = _trace_counts(bad_run_dir)
        template_results.append(
            {
                "template_id": template_id,
                "task_bundle": str(task_bundle),
                "admission_passed": admission["admitted"],
                "projection": admission["projection"],
                "schedule_refs": admission["schedule_refs"],
                "projection_checks": {
                    check["name"]: check["ok"]
                    for check in admission["checks"]
                    if check["name"] in projection_check_names
                },
                "oracle_run": str(oracle_run.run_dir),
                "oracle_passed": oracle_result.ok,
                "known_bad_run": str(bad_run_dir),
                "known_bad_failed": known_bad_failed,
                "known_bad_error": known_bad_error,
                "oracle_trace_counts": oracle_run.trace.counts(),
                "known_bad_trace_counts": known_bad_trace_counts,
            }
        )

    all_admitted = all(item["admission_passed"] for item in template_results)
    all_oracles_passed = all(item["oracle_passed"] for item in template_results)
    all_known_bad_failed = all(item["known_bad_failed"] for item in template_results)
    summary = {
        "template_count": len(template_results),
        "all_admitted": all_admitted,
        "all_oracles_passed": all_oracles_passed,
        "all_known_bad_failed": all_known_bad_failed,
        "templates": template_results,
        "outputs": [
            "verifier_result.json",
            "run_export.json",
            "tool_calls.jsonl",
            "state_diffs.jsonl",
        ],
    }
    write_json(out / "summary.json", summary)
    print(f"Summary: {out / 'summary.json'}")
    print(f"Templates admitted: {sum(item['admission_passed'] for item in template_results)}/{len(template_results)}")
    print(f"Oracles passed: {sum(item['oracle_passed'] for item in template_results)}/{len(template_results)}")
    print(f"Known bad failed: {sum(item['known_bad_failed'] for item in template_results)}/{len(template_results)}")
    return 0 if all_admitted and all_oracles_passed and all_known_bad_failed else 1


def _trace_counts(run_dir: Path) -> dict[str, int]:
    tool_path = run_dir / "tool_calls.jsonl"
    diff_path = run_dir / "state_diffs.jsonl"
    tool_calls = _jsonl_count(tool_path)
    failed_tool_calls = 0
    if tool_path.exists():
        for line in tool_path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not json.loads(line).get("ok", False):
                failed_tool_calls += 1
    return {
        "tool_calls": tool_calls,
        "failed_tool_calls": failed_tool_calls,
        "state_diffs": _jsonl_count(diff_path),
    }


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


if __name__ == "__main__":
    raise SystemExit(main())
