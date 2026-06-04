# Post-Training Collaborator Handoff

Updated: 2026-06-02

## Handoff Status

This package is ready for a post-training collaborator to review as a runnable
world preview plus experiment-design input. It is not ready for a model-lift
claim.

The collaborator should be asked to answer:

```text
Can you plug an agent into this runnable world preview and get a useful
trajectory? What workspace, tool, verifier, transcript, or environment-contract
changes are needed before a real 30/10/10 run?
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

He can now give useful feedback on runnable world fit, trajectory shape, row
format, model choice, eval harness, and minimum experiment design.

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

Do not lead with JSONL alone. The collaborator should see the runnable world
package first, then the SFT/eval rows as derivatives from world trajectories.

## Exact Message To Send

```text
We have a Datalox Env Data Proof v0 runnable world preview. This is not a
model-lift claim yet. The goal is to check whether an agent can plug into the
workspace, use local tools, submit an answer, and produce a useful trajectory
that your post-training workflow can consume.

Can you review:

1. Whether handoff/env-data-proof-v0/runnable-world/ is a usable environment
   package shape for your agent harness.
2. Whether the workspace interface is enough: README/task files, local
   ./datalox_tool calls, ./submit_answer, trajectory.jsonl, and
   verifier_result.json.
3. Which trainable open-weight base model you would choose for a small first
   run.
4. What environment API you would prefer for real runs. The current preview is:
   init_task(task_id) -> workspace;
   ./datalox_tool tool_name args_json -> observation;
   ./submit_answer answer.json -> verifier result and reward.
   If your stack wants reset/step, the equivalent contract is:
   reset(task_id) -> initial messages and tools;
   step(tool_call) -> tool observation;
   finalize(answer) -> verifier result and reward fields;
   export_messages() -> system/user/assistant/tool transcript.
5. Whether the source gate is enough to prevent us from overclaiming the
   current seed.
6. Whether exports/sft.tool_messages.seed.jsonl is usable as SFT/LoRA data in
   your normal system/user/assistant/tool turn format.

Important boundary: current FlowCyto and Molecule rows are plumbing-only until
recaptured from public flowCore/NCBI sources. The source gate is explicit in
task-source-gate.csv.

File boundary: exports/eval.seed.jsonl is not the training file. It is a
context-eval file that preloads replay observations in the prompt. For SFT,
start with exports/sft.tool_messages.seed.jsonl. It uses standard
system/user/assistant/tool turns. exports/sft.tool_evidence.seed.jsonl keeps
the same rollout in a richer Datalox audit shape.

The useful object is the runnable world package. The SFT/eval rows are
secondary examples and derivatives, not the environment itself.

The output we need from you is a short feasibility verdict:

- usable as-is / needs format changes / not compatible
- preferred base model
- preferred SFT runner
- preferred world/rollout/eval harness shape
- minimum dataset size before training
- blockers before you would run the first real LoRA
```

## Internal Validation Boundary

The runnable-world scripts are the preview workspace interface. The older seed
export/eval scripts are for our own reproducibility checks and should not be the
collaborator's first task unless he explicitly asks for implementation details.

The already-validated claims to include in the handoff are:

- runnable-world oracle runs pass for FASTQ QC and molecule primer validation;
- runnable-world bad-answer runs fail for both tasks;
- runnable-world emits `trajectory.jsonl` and `verifier_result.json`;
- source manifest and source gate are present;
- known-good and known-bad seed answers are verifier-checkable;
- tool-message SFT rows contain standard system/user/assistant/tool turns;
- tool-env eval rows do not preload observations;
- the current split is only a 7/3/3 smoke split, not lift-grade data.

## Acceptance Criteria For His Feedback

The handoff is successful if he returns answers to these five decisions:

1. Which base model should be used for the first trainable run?
2. Whether the runnable world can plug into his agent harness as-is.
3. Whether the standard tool-message SFT export matches his loader, or whether
   he needs a small adapter change such as `assistant.content: null`, sanitized
   function names, or a different `tool_calls` field shape.
4. What reset/tools/step/finalize/export contract his rollout harness needs.
5. What exact metadata is missing from the current world trajectories or rows?
6. What is the minimum dataset size he considers worth training on?

After that feedback, Datalox should not keep iterating abstractly. The next
implementation step should be one of:

- recapture FlowCyto/Molecule rows from public sources;
- expand the runnable world beyond two tasks;
- wrap the runnable world as HTTP/MCP/Python reset-step if his stack needs it;
- change export row shape to match his workflow;
- scale to 30/10/10.

## Definition Of Fully Training-Ready

The package becomes ready for an actual LoRA/SFT run only after:

- all train rows are source-backed or explicitly approved private-source rows;
- current FlowCyto rows are recaptured from public flowCore FCS files;
- current Molecule rows are recaptured from NCBI records;
- PBMC3k derivation is locked or the task is marked derived-table-only;
- canonical replay bundles exist for the rows used in training/eval;
- runnable-world or its successor can be executed by a tool-using agent harness;
- `sft.tool_messages.seed.jsonl` loads in the collaborator's SFT stack without
  manual conversion;
- split is at least 30 train / 10 dev / 10 test for a first signal test.

Until then, the correct collaborator ask is workflow review and experiment
design, not model-lift execution.
