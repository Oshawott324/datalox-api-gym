# Post-Training Collaborator Handoff

Updated: 2026-06-02

## Handoff Status

This package is ready for a post-training collaborator to review as a World API
preview plus experiment-design input. It is not ready for a model-lift claim.

The collaborator should be asked to answer:

```text
Can your MCP harness plug into this World API preview and get a useful
trajectory? What lifecycle, tool, verifier, transcript, or environment-contract
changes are needed before an 80/20/20 run?
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
- A two-task runnable world preview exists.
- A reset/step/finalize/export World API preview exists.
- A minimal MCP stdio adapter exists over the World API.

He can now give useful feedback on World API fit, MCP adapter shape,
trajectory shape, row format, model choice, eval harness, and minimum
experiment design.

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

The runnable world preview is intentionally smaller than the full seed: it has
two tasks, local deterministic tools, answer submission, verifier results, and
trajectory logging. It is a packaging proof, not a lift-grade benchmark.

## Files To Send

Send these files first:

- `handoff/env-data-proof-v0/post-training-collaborator-handoff.md`
- `handoff/env-data-proof-v0/collaborator-packet/`
- `handoff/env-data-proof-v0/world-api/`
- `handoff/env-data-proof-v0/runnable-world/`
- `handoff/env-data-proof-v0/source-dataset-prep-report.md`
- `handoff/env-data-proof-v0/source-datasets.manifest.json`
- `handoff/env-data-proof-v0/task-source-gate.csv`

Send these as secondary training/export context:

- `handoff/env-data-proof-v0/exports/sft.tool_messages.seed.jsonl`
- `handoff/env-data-proof-v0/exports/sft.tool_evidence.seed.jsonl`
- `handoff/env-data-proof-v0/exports/eval.tool_env.seed.jsonl`
- `handoff/env-data-proof-v0/exports/eval.seed.jsonl`
- `handoff/env-data-proof-v0/world.spec.json`
- `handoff/env-data-proof-v0/families/`

Optional supporting files:

- `handoff/env-data-proof-v0/schema/tool-message-sft-row.schema.json`
- `handoff/env-data-proof-v0/schema/tool-evidence-sft-row.schema.json`
- `handoff/env-data-proof-v0/schema/tool-env-eval-row.schema.json`
- `handoff/env-data-proof-v0/hf/README.md`
- `handoff/env-data-proof-v0/huggingface-publication-implementation-report.md`
- `handoff/env-data-proof-v0/post-training-runbook.html`

Do not lead with JSONL alone. The collaborator should see the World API
contract and MCP adapter first, then the runnable world, then the SFT/eval rows
as derivatives from world trajectories.

## Exact Message To Send

```text
We have a Datalox Env Data Proof v0 World API preview. This is not a model-lift
claim yet. The goal is to check whether your MCP/agent harness can plug into a
reset/step/finalize/export world lifecycle, use current-task tools, submit an
answer, and produce a useful trajectory that your post-training workflow can
consume.

Can you review:

1. Whether handoff/env-data-proof-v0/world-api/ is a usable lifecycle contract:
   reset -> tools -> step -> finalize -> export.
2. Whether the MCP adapter shape fits your current harness.
3. Whether the workspace interface underneath is enough: README/task files,
   local tool calls, answer submit, trajectory.jsonl, and verifier_result.json.
4. Which trainable open-weight base model you would choose for a small first
   run.
5. What fields are missing from reset/step/finalize/export for SFT/eval/RL.
6. Whether the source gate is enough to prevent us from overclaiming the
   current seed.
7. Whether exports/sft.tool_messages.seed.jsonl is usable as SFT/LoRA data in
   your normal system/user/assistant/tool turn format.

Important boundary: current FlowCyto and Molecule rows are plumbing-only until
recaptured from public flowCore/NCBI sources. The source gate is explicit in
task-source-gate.csv.

File boundary: exports/eval.seed.jsonl is not the training file. It is a
context-eval file that preloads replay observations in the prompt. For SFT,
start with exports/sft.tool_messages.seed.jsonl. It uses standard
system/user/assistant/tool turns. exports/sft.tool_evidence.seed.jsonl keeps
the same rollout in a richer Datalox audit shape.

The useful object is the World API over a runnable world package. The SFT/eval
rows are secondary examples and derivatives, not the environment itself.

The output we need from you is a short feasibility verdict:

- usable as-is / needs format changes / not compatible
- preferred base model
- preferred SFT runner
- preferred MCP / Python / HTTP / internal world adapter shape
- minimum dataset size before training, with 80/20/20 as the current target
- blockers before you would run the first real LoRA
```

## Internal Validation Boundary

The World API scripts are the preview lifecycle interface. The runnable-world
scripts are the current runtime backend. The older seed export/eval scripts are
for our own reproducibility checks and should not be the collaborator's first
task unless he explicitly asks for implementation details.

The already-validated claims to include in the handoff are:

- runnable-world oracle runs pass for FASTQ QC and molecule primer validation;
- runnable-world bad-answer runs fail for both tasks;
- runnable-world emits `trajectory.jsonl` and `verifier_result.json`;
- World API smoke tests pass for reset/step/finalize/export;
- MCP stdio smoke test exposes current-task tools and routes tool calls;
- system-message exports include current-task tool descriptions and schemas;
- source manifest and source gate are present;
- known-good and known-bad seed answers are verifier-checkable;
- tool-message SFT rows contain standard system/user/assistant/tool turns;
- tool-env eval rows do not preload observations;
- the current split is only a 7/3/3 smoke split, not lift-grade data.

## Acceptance Criteria For His Feedback

The handoff is successful if he returns answers to these six decisions:

1. Which base model should be used for the first trainable run?
2. Whether the World API can plug into his agent harness through MCP as-is.
3. Whether the standard tool-message SFT export matches his loader, or whether
   he needs a small adapter change such as `assistant.content: null`, sanitized
   function names, or a different `tool_calls` field shape.
4. What fields his reset/tools/step/finalize/export contract needs.
5. What exact metadata is missing from the current world trajectories or rows?
6. Whether 80 train / 20 dev / 20 test is enough for the first signal test.

After that feedback, Datalox should not keep iterating abstractly. The next
implementation step should be one of:

- recapture FlowCyto/Molecule rows from public sources;
- expand the runnable world beyond two tasks;
- wrap the World API as HTTP or a different internal adapter if MCP is not enough;
- change export row shape to match his workflow;
- scale to 80/20/20.

## Definition Of Fully Training-Ready

The package becomes ready for an actual LoRA/SFT run only after:

- all train rows are source-backed or explicitly approved private-source rows;
- current FlowCyto rows are recaptured from public flowCore FCS files;
- current Molecule rows are recaptured from NCBI records;
- PBMC3k derivation is locked or the task is marked derived-table-only;
- canonical replay bundles exist for the rows used in training/eval;
- World API or its successor can be executed by a tool-using agent harness;
- `sft.tool_messages.seed.jsonl` loads in the collaborator's SFT stack without
  manual conversion;
- split is at least 80 train / 20 dev / 20 test for a first signal test.

Until then, the correct collaborator ask is workflow review and experiment
design, not model-lift execution.
