# Datalox Runnable World Preview

This is a small CyberGym-style preview world for agent handoff testing.

It is intentionally not a trainer, sandbox engine, or model runner. It packages
task workspaces, local deterministic tools, answer submission, verifier results,
and trajectory logging so an external agent harness can plug in.

## Quick Start

```bash
python3 bin/init_task.py --task fastq-qc-nanopore-fail-001 --run runs/fastq-demo
cd runs/fastq-demo/workspace
./datalox_tool workspace.list_files '{}'
./datalox_tool fastqc.parse_report '{"path":"artifacts/fastqc_data.txt"}'
./datalox_tool qc_policy.evaluate '{"report_ref":"metric:fastqc.parsed_report"}'
```

Write an `answer.json`, then submit:

```bash
./submit_answer answer.json
```

Outputs are written under the run directory:

- `trajectory.jsonl`
- `verifier_result.json`
- `run.json`

## Boundary

The package is a runnable preview of environment packaging. Domain algorithms
should live in domain tools or MCP repos. This preview keeps only deterministic
local tools needed for two seed tasks.
