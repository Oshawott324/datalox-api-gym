"""Run the greenfield Lab Campaign Ops Step 5 prototype."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from greenfield_lab_campaign_ops.worlds.lab_campaign_ops_v0.task_generator import NOMINAL_TEMPLATE_ID, STALE_TEMPLATE_ID, generate_task


def main() -> int:
    parser = argparse.ArgumentParser(description="Run lab_campaign_ops_v0 Step 5 demo.")
    parser.add_argument("--out", type=Path, default=Path("runs/greenfield_lab_campaign_ops_step5"))
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    out = args.out.resolve()
    if args.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    task_summaries = []
    for template_id in (STALE_TEMPLATE_ID, NOMINAL_TEMPLATE_ID):
        task_dir = out / "generated" / f"{template_id}__seed_{args.seed:04d}"
        generated = generate_task(task_dir, seed=args.seed, clean=True, template_id=template_id)
        admission = json.loads(generated.admission_path.read_text(encoding="utf-8"))
        task_summaries.append(
            {
                **generated.to_dict(),
                "admitted": admission["admitted"],
                "check_count": len(admission["checks"]),
                "passed_checks": sum(check["ok"] for check in admission["checks"]),
                "run_traces": admission.get("run_traces", {}),
            }
        )

    summary = {
        "task_count": len(task_summaries),
        "all_admitted": all(item["admitted"] for item in task_summaries),
        "tasks": task_summaries,
    }
    summary_path = out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Summary: {summary_path}")
    print(f"Tasks admitted: {sum(item['admitted'] for item in task_summaries)}/{len(task_summaries)}")
    for item in task_summaries:
        task_dir = Path(item["task_dir"])
        print(f"Generated task: {task_dir}")
        print(f"Template: {item['template_id']}")
        print(f"Admitted: {item['admitted']}")
        print(f"Admission checks: {item['passed_checks']}/{item['check_count']}")
        run_traces = item.get("run_traces", {})
        oracle_trace = run_traces.get("oracle", {})
        known_bad_traces = run_traces.get("known_bad", [])
        print(f"Oracle tool calls: {task_dir / oracle_trace.get('tool_calls', '')}")
        print(f"Oracle state diffs: {task_dir / oracle_trace.get('state_diffs', '')}")
        for trace in known_bad_traces:
            print(f"Known-bad tool calls: {task_dir / trace.get('tool_calls', '')}")
            print(f"Known-bad state diffs: {task_dir / trace.get('state_diffs', '')}")
    return 0 if summary["all_admitted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
