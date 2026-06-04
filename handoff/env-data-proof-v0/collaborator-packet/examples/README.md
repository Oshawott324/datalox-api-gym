# Examples

This folder contains precomputed trajectories so the reviewer does not need to
run the world first.

## Runs

```text
runs/fastq-pass/
runs/fastq-fail/
runs/molecule-pass/
runs/molecule-fail/
```

Each run contains:

```text
run.json
trajectory.jsonl
answer.json
verifier_result.json
workspace/
```

The `workspace/` directory is included for reproducibility. For review, start
with `trajectory.jsonl` and `verifier_result.json`.

