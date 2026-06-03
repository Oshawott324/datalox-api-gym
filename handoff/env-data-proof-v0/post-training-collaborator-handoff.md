# Post-Training Collaborator Handoff

Updated: 2026-06-02

## Handoff Status

This package is ready for a post-training collaborator to review and turn into
an experiment design. It is not ready for a model-lift claim.

The collaborator should be asked to answer:

```text
Does this task schema, tool-message SFT format, and tool-env eval contract
fit your normal post-training workflow? What needs to change before a real
30/10/10 run?
```

The collaborator should not yet be asked to:

```text
Train now and prove model improvement.
```

That distinction is the handoff boundary. If we ask for model improvement now,
we will waste his time because the seed is still a 13-task handoff package and
some rows are plumbing-only rows.

## Why This Is Ready To Hand Off

The collaborator can inspect concrete artifacts instead of vague plans:

- Task/output schemas exist.
- Standard tool-message SFT rows exist.
- Tool-evidence SFT rows exist.
- Tool-env eval rows exist.
- Source dataset manifest exists.
- Task-source gate exists.
- Verifier-smoke baseline exists.
- Commands and runbook exist.

He can now give useful feedback on row format, model choice, eval harness, and
minimum experiment design.

## What Is Still Not Ready For Training

Training-run readiness requires more data and cleaner source capture.

Current task-source gate:

| Status | Count | Meaning |
|---|---:|---|
| `source_backed_seed_row` | 4 | Can proceed toward replay-bundle conversion. |
| `source_backed_but_derivation_not_locked` | 1 | Needs locked PBMC3k derivation. |
| `smoke_only_not_public_training_claim` | 8 | Needs public-source recapture before training claims. |

The 8 plumbing-only rows are useful for testing schema and export shape, but
not for claiming public scientific training data.

## Files To Send

Send these files first:

- `handoff/env-data-proof-v0/post-training-runbook.html`
- `handoff/env-data-proof-v0/post-training-collaborator-handoff.md`
- `handoff/env-data-proof-v0/source-dataset-prep-report.md`
- `handoff/env-data-proof-v0/source-datasets.manifest.json`
- `handoff/env-data-proof-v0/task-source-gate.csv`
- `handoff/env-data-proof-v0/exports/sft.tool_messages.seed.jsonl`
- `handoff/env-data-proof-v0/exports/sft.tool_evidence.seed.jsonl`
- `handoff/env-data-proof-v0/exports/eval.tool_env.seed.jsonl`
- `handoff/env-data-proof-v0/exports/eval.seed.jsonl`
- `handoff/env-data-proof-v0/exports/eval_command.md`

Optional supporting files:

- `handoff/env-data-proof-v0/schema/tool-message-sft-row.schema.json`
- `handoff/env-data-proof-v0/schema/tool-evidence-sft-row.schema.json`
- `handoff/env-data-proof-v0/schema/tool-env-eval-row.schema.json`
- `handoff/env-data-proof-v0/hf/README.md`
- `handoff/env-data-proof-v0/huggingface-publication-implementation-report.md`

## Exact Message To Send

```text
We have a Datalox Env Data Proof v0 handoff package. This is not a model-lift
claim yet. The goal is to check whether the schema/export/eval shape fits your
post-training workflow before we scale the dataset.

Can you review:

1. Whether exports/sft.tool_messages.seed.jsonl is usable as SFT/LoRA data in
   your normal system/user/assistant/tool turn format.
2. Whether exports/eval.tool_env.seed.jsonl matches the kind of tool-env eval
   harness you would normally use.
3. Which trainable open-weight base model you would choose for a small first
   run.
4. What row-format or metadata changes are needed before a real 30/10/10
   experiment.
5. Whether the source gate is enough to prevent us from overclaiming the
   current seed.

Important boundary: current FlowCyto and Molecule rows are plumbing-only until
recaptured from public flowCore/NCBI sources. The source gate is explicit in
task-source-gate.csv.

File boundary: exports/eval.seed.jsonl is not the training file. It is a
context-eval file that preloads replay observations in the prompt. For SFT,
start with exports/sft.tool_messages.seed.jsonl. It uses standard
system/user/assistant/tool turns. exports/sft.tool_evidence.seed.jsonl keeps
the same rollout in a richer Datalox audit shape.

The output we need from you is a short feasibility verdict:

- usable as-is / needs format changes / not compatible
- preferred base model
- preferred SFT runner
- preferred eval harness shape
- minimum dataset size before training
- blockers before you would run the first real LoRA
```

## Commands He Can Run

Validate public source URLs:

```bash
node handoff/env-data-proof-v0/tools/verify-source-datasets.mjs
```

Validate known-good and known-bad seed answers:

```bash
node handoff/env-data-proof-v0/tools/verify-seed-answers.mjs
```

Run local verifier plumbing baseline:

```bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \
  --out handoff/env-data-proof-v0/exports/eval.baseline.smoke.jsonl \
  --mode verifier-smoke \
  --model deterministic-weak-baseline \
  --min-failures 10
```

Inspect row counts:

```bash
wc -l handoff/env-data-proof-v0/exports/*.jsonl
```

## Acceptance Criteria For His Feedback

The handoff is successful if he returns answers to these five decisions:

1. Which base model should be used for the first trainable run?
2. Whether the standard tool-message SFT export matches his loader, or whether
   he needs a small adapter change such as `assistant.content: null`, sanitized
   function names, or a different `tool_calls` field shape.
3. What tool-env eval harness shape does he need?
4. What exact metadata is missing from the current rows?
5. What is the minimum dataset size he considers worth training on?

After that feedback, Datalox should not keep iterating abstractly. The next
implementation step should be one of:

- recapture FlowCyto/Molecule rows from public sources;
- build the tool-env eval harness;
- change export row shape to match his workflow;
- scale to 30/10/10.

## Definition Of Fully Training-Ready

The package becomes ready for an actual LoRA/SFT run only after:

- all train rows are source-backed or explicitly approved private-source rows;
- current FlowCyto rows are recaptured from public flowCore FCS files;
- current Molecule rows are recaptured from NCBI records;
- PBMC3k derivation is locked or the task is marked derived-table-only;
- canonical replay bundles exist for the rows used in training/eval;
- `eval.tool_env.seed.jsonl` can be executed by a tool-using agent harness;
- `sft.tool_messages.seed.jsonl` loads in the collaborator's SFT stack without
  manual conversion;
- split is at least 30 train / 10 dev / 10 test for a first signal test.

Until then, the correct collaborator ask is workflow review and experiment
design, not model-lift execution.
