# Datalox Env Data Proof v0 Collaborator Packet

Prepared: 2026-06-04

## Start Here

This packet is for a post-training collaborator. It is designed to be reviewed
without reading source code first.

The decision we need is:

```text
Can this kind of runnable domain world generate trajectories that fit your
normal SFT / eval / RL workflow? If not, what minimum interface or data-shape
changes are needed before a first LoRA or rollout experiment?
```

## What This Is

- A small runnable world preview with two scientific workflow tasks.
- Precomputed pass/fail example trajectories for each task.
- A verifier result for every example trajectory.
- A two-row SFT-style system/user/assistant/tool message export from passing
  runs.
- Appendix material for running or inspecting the world only after the data
  shape is clear.

## What This Is Not

- Not a model-lift claim.
- Not a benchmark.
- Not asking you to inspect Datalox internals.
- Not asking you to accept the current JSONL schema as final.

## Review Order

1. Read `one-page-context.md`.
2. Read `task-cards.md`.
3. Read `trajectory-guide.md`.
4. Inspect `examples/runs/*/trajectory.jsonl` and
   `examples/runs/*/verifier_result.json`.
5. Inspect `exports/sft.messages.examples.jsonl`.
6. Answer `review-questions.md`.

The runnable world implementation is included under `appendix/runnable-world/`
only so the packet is reproducible.

## Included Files

```text
README.md
one-page-context.md
task-cards.md
trajectory-guide.md
review-questions.md
message-to-send.md
examples/
  README.md
  runs/
    fastq-pass/
    fastq-fail/
    molecule-pass/
    molecule-fail/
exports/
  README.md
  sft.messages.examples.jsonl
appendix/
  runnable-world/
  post-training-collaborator-handoff.md
  post-training-runbook.html
  source-dataset-prep-report.md
  source-datasets.manifest.json
  task-source-gate.csv
```

