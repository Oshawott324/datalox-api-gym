# Env Data Proof v0 Hugging Face Publication Implementation Report

Updated: 2026-06-02

Status: implementation in progress. Seed task specs, pre-bundle agent-visible
tool observations, and deterministic verifier fixtures now pass local
validation. Do not publish until canonical replay bundles, baseline failures,
teacher trajectories, and exports pass their acceptance gates.

## Executive Summary

The next implementation step is to turn the multi-family seed task set into a
small, publishable Datalox evidence package. This package is not a FlowCyto-only
benchmark and not a model-lift claim by itself; it is the replay/data layer
underneath the larger agent-native environment vision.

```text
public scientific artifact or domain MCP fixture
  -> local fixture workspace
  -> parser/checker tool observations
  -> replay_bundle.v1
  -> deterministic verifier result
  -> baseline failure
  -> verifier-passing teacher trajectory
  -> sft_frame.v1 / eval rows
  -> Hugging Face dataset repository
```

The first public claim should be:

> Datalox can turn real scientific workflow tasks across multiple environment
> families into replayable, verifier-backed agent training/eval data.

The stronger product claim should be:

> Datalox turns traditional scientific workflows into agent-native
> environments, then packages replay evidence into training/eval data.

Do not claim model improvement yet. Model lift requires a larger locked split.
This v0 should prove source quality, replayability, verifier determinism, and
export shape. Source quality is now gated separately from trajectory/export
plumbing.

## Current Passed Artifacts

As of 2026-06-01, the seed handoff has moved past task-spec design and into
captured tool observations:

- `source-datasets.manifest.json` records 14 public source records across
  FlowCyto, Molecule Biology, scientific-data QC, and protein-structure
  readiness.
- `task-source-gate.csv` marks which current rows are source-backed and which
  remain smoke rows until recaptured from public sources.
- 13 `task.spec.json` files validate against
  `schema/agent-native-seed-task-spec.schema.json`.
- 13 `tools/tool-observations.jsonl` files validate against
  `schema/agent-visible-tool-observation.schema.json`.
- 67 total agent-visible observations are captured.
- 41 observations come from live sibling domain tools:
  `datalox-flow-cyto-mcp` and `datalox-molecule-biology`.
- 26 observations come from existing deterministic scientific-data fixture
  worlds.
- Published observation rows use `${DATALOX_AGENT_REPLAY}`,
  `${DATALOX_FLOWCYTO_REPO}`, and `${DATALOX_MOLECULE_REPO}` path tokens, not
  local absolute machine paths.
- 13 `verifier/verifier.spec.json` files validate against
  `schema/verifier-spec.schema.json`.
- 13 known-good answers pass and 13 known-bad answers fail under
  `tools/verify-seed-answers.mjs`.
- `exports/split.seed-smoke.json` records the deterministic 7/3/3 train/dev/test
  smoke split.
- `exports/eval.seed.jsonl` contains 13 context-eval smoke rows.
- `exports/eval.tool_env.seed.jsonl` contains 13 tool-env eval rows where the
  agent must call tools instead of reading preloaded observations.
- `exports/sft.seed.chat.jsonl` contains 7 train-only final-answer SFT smoke
  rows.
- `exports/sft.tool_messages.seed.jsonl` contains 7 train-only
  system/user/assistant/tool SFT rows for collaborator loaders that expect
  standard tool-chat turns.
- `exports/sft.tool_trajectory.seed.jsonl` contains 7 train-only
  tool-trajectory SFT rows in the richer Datalox audit/provenance shape.
- `exports/eval_command.md` records the trainable-base baseline command.
- `exports/eval.baseline.smoke.jsonl` passes the local verifier-smoke baseline:
  13/13 rows parse and 13/13 fail the verifier as expected.

This verifier currently runs against the captured observation layer. The next
replay gate is to convert these observations into canonical `tool_io_record.v1`
records and package them into verified `replay_bundle.v1` artifacts.

The current source gate is stricter than the export gate:

| Source Status | Count | Public Dataset Meaning |
|---|---:|---|
| `source_backed_seed_row` | 4 | Current deterministic observations can move to replay-bundle conversion. |
| `source_backed_but_derivation_not_locked` | 1 | Keep as source-backed smoke until the derivation script is locked. |
| `smoke_only_not_public_training_claim` | 8 | Keep for schema/export smoke; recapture from public sources before SFT claims. |

## Selected Seed Tasks

Machine-readable source file:
`handoff/env-data-proof-v0/selected-agent-native-seed-tasks.csv`.

Source gate files:

- `handoff/env-data-proof-v0/source-datasets.manifest.json`
- `handoff/env-data-proof-v0/source-datasets.csv`
- `handoff/env-data-proof-v0/task-source-gate.csv`
- `handoff/env-data-proof-v0/source-dataset-prep-report.md`

The seed contains 13 candidate tasks:

| Family | Count | Source |
|---|---:|---|
| FlowCyto gating/QC/report | 3 | Current smoke rows use `datalox-flow-cyto-mcp`; public recapture uses flowCore FCS sources |
| Molecule Biology sequence workflows | 5 | Current smoke rows use toy repo fixtures; public recapture uses NCBI records |
| Scientific-data QC artifacts | 5 | Public FastQC, PBMC3k, FCS metadata, mmCIF, and Qualimap sources |

No family should exceed 40% of the seed. If one task is rejected during replay
capture or baseline filtering, replace it within the same family first.

### Existing Scientific-Data Worlds

| World | Domain | Public Source | Required Tool Observations |
|---|---|---|---:|
| `fastq-qc-nanopore-fail-001` | FASTQ sequencing QC | MultiQC FastQC report | 5+ |
| `single-cell-pbmc3k-qc-summary-001` | single-cell RNA-seq QC | 10x PBMC3k matrix and derived Scanpy QC table | 5+ |
| `flowcyto-fcs-compensation-metadata-001` | flow cytometry metadata QC | flowCore FCS file and compensation matrix | 5+ |
| `protein-structure-ap5a-prep-001` | protein structure prep QC | RCSB 1AKE mmCIF and entry JSON | 5+ |
| `rnaseq-alignment-qualimap-low-mapq-001` | RNA-seq alignment result QC | MultiQC Qualimap BamQC report | 5+ |

Machine-readable source file:
`handoff/env-data-proof-v0/selected-scientific-data-worlds.csv`.

Output schemas:
`handoff/env-data-proof-v0/schema/task-output.schema.json`;
`handoff/env-data-proof-v0/schema/flowcyto-task-output.schema.json`;
`handoff/env-data-proof-v0/schema/molecule-biology-task-output.schema.json`;
`handoff/env-data-proof-v0/schema/scientific-data-task-output.schema.json`.

FlowCyto and Molecule Biology should use their native task schemas as
family-specific payloads inside the shared seed output envelope. Do not force
all families into the scientific-data QC schema.

## Implementation Worktree Layout

Create all v0 implementation artifacts under:

```text
handoff/env-data-proof-v0/
  selected-agent-native-seed-tasks.csv
  worlds/
    fastq-qc-nanopore-fail-001/
    single-cell-pbmc3k-qc-summary-001/
    flowcyto-fcs-compensation-metadata-001/
    protein-structure-ap5a-prep-001/
    rnaseq-alignment-qualimap-low-mapq-001/
  families/
    flowcyto/
      tasks/
    molecule-biology/
      tasks/
  exports/
    train.sft.jsonl
    eval.baseline.jsonl
    eval.teacher.jsonl
    verifier.results.jsonl
  hf/
    README.md
    dataset_info.json
    data/
```

Each task directory must use the same structure. Existing scientific-data
worlds may keep the current `worlds/<world_id>/` layout during migration, but
new FlowCyto and Molecule Biology tasks should use the family layout.

```text
families/<family>/tasks/<task_id>/
  task.spec.json
  provenance.json
  artifacts/
    manifest.json
    source/
    derived/
  tools/
    tool-catalog.json
    tool-observations.jsonl
  replay_bundle/
  verifier/
    verifier.spec.json
    expected.pass.json
    expected.fail.json
    result.teacher.json
    result.baseline.json
  runs/
    baseline.output.json
    teacher.output.json
    teacher.trajectory.json
```

Do not use live upstream calls during replay. Live URLs are provenance and
source-authoring inputs only.

## Per-Task Build Steps

### Step 1: Create `task.spec.json`

Each task spec must be self-contained. The example below is the scientific-data
lane. FlowCyto and Molecule Biology should use equivalent native fields plus
the shared Datalox envelope fields.

```json
{
  "schema_version": "scientific_data_task_spec.v0",
  "world_id": "fastq-qc-nanopore-fail-001",
  "split": "train",
  "task_family": "scientific-data-qc-basic",
  "prompt": "Inspect the fixture workspace and produce a structured QC decision. Cite evidence ids for every diagnosis and next action.",
  "output_schema": "../../schema/scientific-data-task-output.schema.json",
  "allowed_tools": [
    "workspace.list_files",
    "artifact.read_text",
    "fastqc.parse_report",
    "qc_policy.evaluate_fastq",
    "verifier.submit_answer"
  ],
  "forbidden_tools": [
    "web.open",
    "shell.live_download",
    "vision.inspect_image"
  ],
  "success_criteria": [
    "output validates against scientific-data-task-output.schema.json",
    "diagnosis.class matches expected class",
    "required computed checks cite replay evidence ids",
    "next_action.type matches verifier spec",
    "no forbidden action is claimed"
  ]
}
```

Rules:

- The prompt must not include the answer.
- The task must force file/tool inspection.
- A correct answer must require at least five replayed observations.
- Dev/test specs must not include hidden expected values outside the verifier.

### Step 2: Create `provenance.json`

Record the live source facts separately from copied artifacts:

```json
{
  "schema_version": "scientific_data_provenance.v0",
  "world_id": "fastq-qc-nanopore-fail-001",
  "sources": [
    {
      "source_id": "source:multiqc-fastqc-nan-reads",
      "url": "https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/fastqc/nan_reads/fastqc_data.txt",
      "kind": "raw_text_report",
      "license_review": "pending",
      "pin": {
        "repo": "MultiQC/test-data",
        "commit": "84dc905e6edb97668b87660896dfd78f175008ca",
        "etag": "ab8d2041df37698afb21c147042360174aadbbe97e976c6cfbd677141bbb561f"
      }
    }
  ],
  "publication_policy": {
    "copy_source_artifact": false,
    "publish_derived_observations": true,
    "reason": "Publish provenance URL and parser observations first; copy raw artifact only after license review."
  }
}
```

Rules:

- Use `copy_source_artifact: false` by default for v0.
- Publish derived parser observations and evidence ids first.
- Copy raw artifacts only after license review.
- Record checksums for any copied file.

### Step 3: Vendor Or Derive Fixture Artifacts

For v0, prefer small derived artifacts over raw source copies.

Required manifest:

```json
{
  "schema_version": "fixture_artifact_manifest.v0",
  "world_id": "fastq-qc-nanopore-fail-001",
  "artifacts": [
    {
      "artifact_id": "file:fastqc_data.txt",
      "path": "artifacts/derived/fastqc_data.excerpt.txt",
      "kind": "derived_excerpt",
      "source_id": "source:multiqc-fastqc-nan-reads",
      "sha256": "<fill-after-generation>",
      "publish": true
    },
    {
      "artifact_id": "file:fastqc_metrics.json",
      "path": "artifacts/derived/fastqc_metrics.json",
      "kind": "parser_output",
      "source_id": "source:multiqc-fastqc-nan-reads",
      "sha256": "<fill-after-generation>",
      "publish": true
    }
  ]
}
```

Per-world source policy:

| World | Raw Source Copy? | Preferred Published Artifact |
|---|---|---|
| FastQC | no by default | parser metrics JSON + small excerpt |
| Single-cell PBMC3k | no | generated QC table + script hash |
| FlowCyto FCS | no by default | parsed FCS keyword JSON + compensation matrix if license permits |
| Protein 1AKE | no by default | parsed mmCIF metadata JSON + RCSB URL |
| Qualimap | no by default | parser metrics JSON + small excerpt |

### Step 4: Implement Parser/Checker Tools

The first implementation should expose deterministic parser tools, not heavy
domain simulations.

Minimum tool catalog:

```json
{
  "schema_version": "scientific_data_tool_catalog.v0",
  "tools": [
    {
      "name": "workspace.list_files",
      "description": "List fixture files available to the agent."
    },
    {
      "name": "artifact.read_text",
      "description": "Read an approved fixture text artifact or excerpt."
    },
    {
      "name": "fastqc.parse_report",
      "description": "Parse FastQC modules, statuses, basic statistics, and failed checks."
    },
    {
      "name": "single_cell.inspect_qc_table",
      "description": "Inspect a locked single-cell QC summary table."
    },
    {
      "name": "flowcyto.parse_fcs_keywords",
      "description": "Parse FCS keyword metadata, channels, event count, and marker labels."
    },
    {
      "name": "protein.parse_mmcif_metadata",
      "description": "Parse structure id, method, resolution, polymer entities, nonpolymer ligands, and title."
    },
    {
      "name": "alignment.parse_qualimap",
      "description": "Parse mapped reads, aligned bases, mapping quality, coverage, and relevant warnings."
    },
    {
      "name": "qc_policy.evaluate",
      "description": "Apply a declared deterministic QC policy to parsed metrics."
    }
  ]
}
```

Each parser tool must return evidence ids:

```json
{
  "tool_name": "fastqc.parse_report",
  "observation": {
    "evidence_id": "metric:fastqc.failed_modules",
    "sample_id": "sample1_S1_L001_R2_001.fastq.gz",
    "failed_modules": [
      "Per base sequence quality",
      "Per tile sequence quality",
      "Per base sequence content",
      "Per base N content",
      "Sequence Duplication Levels",
      "Adapter Content"
    ]
  }
}
```

### Step 5: Capture Replay Evidence

For each task, capture at least these observations. Scientific-data tasks use
the metric-style examples below; FlowCyto and Molecule Biology should capture
their native domain-tool observations with the same replay primitive.

| Observation | Example Evidence Id |
|---|---|
| workspace file list | `tool_io:<world_id>/list-files/0` |
| source/provenance summary | `source:<world_id>/primary` |
| parser output | `metric:<world_id>/parsed-metrics` |
| policy evaluation | `metric:<world_id>/policy-result` |
| verifier result | `run:<world_id>/verifier-teacher` |

The captured observations should become `tool_io_record.v1` records, then a
`replay_bundle.v1`. Replay lookup must use `request_hash + sequence_index` and
must not fall back to live source URLs.

Implementation status, 2026-06-01:

- `tools/capture-live-observations.mjs` captures all 13 seed tasks.
- FlowCyto observations are produced by `openFcsArtifact`, `getPlotContext`,
  `upsertGate`, `computeGateStats`, `validateGateQc`, and `submitReport`.
- Molecule Biology observations are produced by the repo's tool handler for
  `open_sequence`, `get_sequence_context`, `upsert_feature`, `upsert_primer`,
  `find_restriction_sites`, `simulate_digest`, `simulate_pcr`, and
  `validate_workspace`.
- Scientific-data QC observations are imported from the existing deterministic
  fixture worlds.
- Temporary capture workspaces are not published; the JSONL observation rows
  are the handoff artifact for the replay-bundle conversion step.

### Step 6: Write `verifier.spec.json`

Verifier specs must score only deterministic facts:

```json
{
  "schema_version": "scientific_data_verifier_spec.v0",
  "world_id": "fastq-qc-nanopore-fail-001",
  "output_schema": "../../schema/scientific-data-task-output.schema.json",
  "required": {
    "diagnosis.class": "fastq_qc_decision",
    "diagnosis.severity": "fail",
    "next_action.type": "trim_or_filter_reads",
    "affected_artifacts": [
      "sample:sample1_S1_L001_R2_001.fastq.gz"
    ],
    "evidence_ids": [
      "metric:fastqc.failed_modules",
      "metric:fastqc.basic_statistics"
    ],
    "computed_checks": [
      {
        "name": "adapter_content",
        "status": "fail"
      },
      {
        "name": "per_base_sequence_quality",
        "status": "fail"
      }
    ]
  },
  "forbid": [
    "invented_metric",
    "used_uncited_evidence",
    "used_vision_judgment",
    "called_live_service"
  ]
}
```

Verifier implementation rule:

- Validate JSON Schema first.
- Check enum fields exactly.
- Check required evidence ids exactly.
- Check required computed checks by `name` and `status`.
- Treat summary text as human-readable only; do not semantic-grade it in v0.

Implementation status, 2026-06-01:

- `schema/verifier-spec.schema.json` defines the deterministic verifier contract.
- `schema/verifier-result.schema.json` defines verifier output.
- `tools/verify-seed-answers.mjs` validates shared output schema, family payload
  schema, required evidence ids, required missing fields, forbidden-action
  acknowledgements, family-specific fields, and scientific computed checks.
- Each of the 13 seed tasks has `verifier/verifier.spec.json`,
  `expected.pass.json`, `expected.fail.json`, `result.pass.json`, and
  `result.fail.json`.
- The current verifier command is:

```bash
node handoff/env-data-proof-v0/tools/verify-seed-answers.mjs
```

### Step 7: Run Baseline

Run one baseline after the post-training workflow-facing eval rows exist. The
baseline must use the same trainable open-weight base model that will later
receive LoRA SFT. A closed API model can be a useful reference run, but it is
not the SFT baseline unless that exact model can be fine-tuned by the
post-training workflow. The model team should consume ordinary JSONL and a
normal OpenAI-compatible command; `tool_io_record.v1` and `replay_bundle.v1`
remain Datalox-internal provenance unless someone wants to audit the evidence.

Baseline command target:

```bash
node handoff/env-data-proof-v0/tools/run-seed-baseline.mjs \
  --input handoff/env-data-proof-v0/exports/eval.seed.jsonl \
  --out handoff/env-data-proof-v0/exports/eval.baseline.jsonl \
  --mode openai-compatible \
  --model Qwen/Qwen3-1.7B \
  --base-url http://127.0.0.1:8000/v1 \
  --api-key token \
  --min-failures 5
```

The command is recorded in `exports/eval_command.md`. The local verifier-smoke
command is also recorded there, but it proves only schemas, parsing, and
verifier wiring.

Current endpoint status, 2026-06-01:

- The local verifier-smoke baseline passes and writes
  `exports/eval.baseline.smoke.jsonl`.
- The real model command is ready, but no trainable open-weight model endpoint
  is running in this workspace. Do not publish `eval.baseline.jsonl` until the
  base model endpoint or the model team's inference stack runs.

Baseline acceptance:

- all outputs are schema-valid or have explicit parse failures
- each seed task has a verifier result
- enough held-out tasks fail for concrete reasons to leave improvement headroom
- failure reasons are concrete: missing evidence, wrong next action, invented
  metric, ignored threshold, or live-service claim

If the baseline passes most seed tasks, the tasks are too easy. Tighten prompts,
hide answer-bearing titles, or add harder tasks within the weakest family.

### Step 8: Create Teacher Trajectories

For each train task, create one verifier-passing teacher trajectory.

Teacher trajectory must include:

- task id
- split
- prompt
- tool calls
- replay evidence ids
- final structured output
- verifier result id
- export gate

Do not include dev/test reference answers when the dataset scales beyond seed.
For v0 seed, it is acceptable to publish representative examples, but label
them as `seed` rather than claiming a train/dev/test benchmark.

### Step 9: Export SFT/Eval Rows

There are two eval/export modes now:

- Context eval smoke: `exports/eval.seed.jsonl` and
  `exports/sft.seed.chat.jsonl`. These rows preload replay observations and
  test final-answer formatting and evidence citation.
- Tool-env eval and training: `exports/eval.tool_env.seed.jsonl` and
  `exports/sft.tool_messages.seed.jsonl`. The message file is the primary
  collaborator-facing SFT handoff because it uses standard
  system/user/assistant/tool turns. `exports/sft.tool_trajectory.seed.jsonl`
  keeps the same rollout in a richer Datalox audit/provenance shape.

Minimum `sft_frame.v1` fields:

```json
{
  "schema_version": "sft_frame.v1",
  "task_id": "fastq-qc-nanopore-fail-001",
  "split": "seed",
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "Inspect the fixture workspace and produce a structured QC decision."
      }
    ],
    "tool_context_ref": "replay_bundle:<bundle_id>"
  },
  "target": {
    "messages": [
      {
        "role": "assistant",
        "content": "<schema-valid JSON output>"
      }
    ]
  },
  "evidence": {
    "replay_bundle_id": "<bundle_id>",
    "verifier_result_id": "<result_id>",
    "source_ids": [
      "source:multiqc-fastqc-nan-reads"
    ]
  },
  "export": {
    "allowed": true,
    "redaction": "none_needed"
  }
}
```

Export rule:

- baseline failures go into eval rows, not SFT targets
- only verifier-passing teacher/tool trajectories become SFT rows
- every row must point to a replay bundle and verifier result

## Hugging Face Dataset Layout

HF dataset repos are Git repositories. The dataset `README.md` is rendered as
the dataset card, and YAML metadata at the top controls Hub display. Upload can
use `hf upload <repo> <folder> --repo-type dataset`.

Target dataset repo:

```text
datasets/<org>/datalox-env-data-proof-v0
```

Target HF file tree:

```text
README.md
LICENSE
schemas/
  scientific-data-task-output.schema.json
  task-output.schema.json
data/
  worlds.jsonl
  tasks.seed.jsonl
  sft.seed.jsonl
  eval.baseline.jsonl
  verifier.results.jsonl
worlds/
  fastq-qc-nanopore-fail-001/
    task.spec.json
    provenance.json
    artifacts.manifest.json
    tool-observations.jsonl
    verifier.spec.json
  single-cell-pbmc3k-qc-summary-001/
  flowcyto-fcs-compensation-metadata-001/
  protein-structure-ap5a-prep-001/
  rnaseq-alignment-qualimap-low-mapq-001/
reports/
  implementation-report.md
  cost-report.md
```

Do not upload raw source binaries by default. Link public sources and upload
derived observations, parser outputs, manifests, and verifier specs. Large or
licensed artifacts can be added only after license review.

## Draft Dataset Card

Create `handoff/env-data-proof-v0/hf/README.md` from this template:

```markdown
---
pretty_name: Datalox Env Data Proof v0
license: other
task_categories:
- text-generation
- question-answering
tags:
- agent-environment
- replay
- scientific-workflow
- bioinformatics
- flow-cytometry
- protein-structure
- single-cell
- sft
size_categories:
- n<1K
---

# Datalox Env Data Proof v0

This dataset is a seed evidence package for replayable scientific workflow
agent tasks across FlowCyto, Molecule Biology, and scientific-data QC. It
contains provenance links, fixture specs, parser/domain-tool observations,
deterministic verifier specs, baseline outputs, and verifier-passing teacher
trajectories.

## What This Is

The package demonstrates that real scientific artifacts and domain MCP fixtures
can be converted into replayable, verifier-backed agent training/eval data.

## What This Is Not

This is not a benchmark leaderboard and not evidence of model lift. The seed has
13 candidate tasks and is intended for schema, replay, verifier, family-variety,
and export validation.

## Families

- FlowCyto gating/QC/report
- Molecule Biology sequence workflows
- scientific-data QC artifacts

## Data Construction

Each task starts from a public scientific source artifact or a domain MCP repo
fixture. Datalox captures agent-visible parser/checker/domain-tool
observations, packages them into replay evidence, and verifies structured
outputs with deterministic rules.

## Limitations

- v0 is small.
- some raw source artifacts are linked rather than copied.
- no vision-based interpretation is included.
- no online RL environment is included.
- model improvement is not claimed.

## Intended Use

Use this package to inspect the Datalox replay/evidence/export workflow and to
test whether the exported rows are usable by training/eval teams.

## Provenance And Licensing

See each task's `provenance.json` or fixture reference. Raw source artifacts
are not copied unless license review permits redistribution.

## Cost

See `reports/cost-report.md`.
```

Before public upload, replace `license: other` with the correct license or keep
`other` and explain mixed provenance if raw artifacts are linked rather than
redistributed.

## Publication Gates

Publish only when all are true:

| Gate | Required Evidence |
|---|---|
| Source provenance | every task has `provenance.json` or repo fixture reference with pin/ETag and license review state |
| Replay determinism | replay bundle verifies and no live source URL is called during eval |
| Verifier determinism | known-good output passes and known-bad output fails |
| Baseline report | baseline output and verifier result exist for every task |
| Teacher trajectory | one verifier-passing teacher trajectory exists per train task |
| Export shape | `sft.seed.jsonl`, `eval.baseline.jsonl`, and `verifier.results.jsonl` validate |
| Privacy/security | no tokens, private data, credentials, or personal data |
| Dataset card | `README.md` includes intended use, limitations, provenance, cost, and non-claims |

## Concrete Work Order

1. Create or adapt `task.spec.json` for all 13 seed tasks.
2. Create `provenance.json` or fixture references with pins and license review state.
3. Generate small derived artifacts and `artifacts/manifest.json`.
4. Implement or wrap deterministic tools for FlowCyto, Molecule Biology,
   FastQC, Qualimap, FCS keywords, compensation matrix, mmCIF metadata, and
   single-cell QC table.
5. Record tool observations as `tool_io_record.v1`.
6. Pack one `replay_bundle.v1` per task or compact task group.
7. Write `verifier/verifier.spec.json` per task family and per task as needed.
8. Run known-good and known-bad verifier checks.
9. Run trainable-base baseline and save `eval.baseline.jsonl`.
10. Create one teacher trajectory per train task.
11. Export `sft.seed.jsonl`.
12. Generate `hf/README.md`, `reports/cost-report.md`, and `data/worlds.jsonl`.
13. Validate all JSON/JSONL, schemas, replay bundles, and checksums.
14. Create private HF dataset repo.
15. Upload with `hf upload <org>/datalox-env-data-proof-v0 handoff/env-data-proof-v0/hf --repo-type dataset`.
16. Review rendered dataset card before making the repo public.

## Source Anchors

- Hugging Face dataset cards:
  `https://huggingface.co/docs/hub/datasets-cards`
- Hugging Face dataset upload docs:
  `https://huggingface.co/docs/hub/en/datasets-adding`
- Hugging Face repository getting started docs:
  `https://huggingface.co/docs/hub/en/repositories-getting-started`
- Selected source artifacts:
  see `selected-scientific-data-worlds.csv`
