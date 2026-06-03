# Env Data Proof v0 Dataset Scale Plan

Updated: 2026-06-02

## Primary v0 Direction

The primary seed should now be a multi-family agent-native scientific workflow
fixture set, not a FlowCyto-only benchmark and not the previous GitHub-issue
workflow-debug set. FlowCyto is the anchor vertical, Molecule Biology is the
generalization proof, and scientific-data QC is the cheap public scaling lane.
The issue set remains useful as a reserve track, but it is coding-adjacent and
too close to generic issue triage unless each issue is converted into a
replay-rich workspace with files, logs, command outputs, and deterministic
verifier observations.

Primary v0 files:

- `selected-agent-native-seed-tasks.csv`
- `source-datasets.manifest.json`
- `source-datasets.csv`
- `task-source-gate.csv`
- `source-dataset-prep-report.md`
- `selected-scientific-data-worlds.csv`
- `scientific-data-fixture-worlds.md`
- `schema/source-dataset-manifest.schema.json`
- `schema/agent-native-seed-task-spec.schema.json`
- `schema/agent-visible-tool-observation.schema.json`
- `schema/task-output.schema.json`
- `schema/flowcyto-task-output.schema.json`
- `schema/molecule-biology-task-output.schema.json`
- `schema/scientific-data-task-output.schema.json`
- `tools/verify-source-datasets.mjs`
- `tools/capture-live-observations.mjs`

Primary v0 claim:

> Datalox turns real scientific workflow tasks into replayable,
> verifier-backed agent training/eval data across multiple environment
> families.

Broader product claim:

> Datalox turns traditional scientific workflows into agent-native
> environments, then packages replay evidence into training/eval data.

Do not claim model lift from this seed. The first claim is that the fixture
tasks are source-backed, tool-rich, deterministic, varied across families, and
exportable.

Do not claim all current seed trajectories are already source-backed. The
source gate is now explicit:

- `source-datasets.manifest.json` records approved public source artifacts.
- `task-source-gate.csv` maps each current task to its approved source ids and
  says whether recapture is required.
- Current FlowCyto and Molecule Biology rows are schema/export smoke until they
  are recaptured from the public FlowCore and NCBI sources in the manifest.

## Outcome Of The Current Task-Selection Step

The current primary seed is `selected-agent-native-seed-tasks.csv`: 13 candidate
tasks across FlowCyto, Molecule Biology, and scientific-data QC. The existing
five scientific-data worlds are still useful, but they are now one family
inside the broader seed rather than the whole public story.

Current primary seed mix:

- 3 FlowCyto gating/QC/report tasks from `datalox-flow-cyto-mcp`
- 5 Molecule Biology sequence-workspace tasks from `datalox-molecule-biology`
- 5 scientific-data QC worlds from public source artifacts

Current capture status:

- 13 seed task specs validate.
- 14 public source records are prepared in
  `source-datasets.manifest.json` and validate with
  `tools/verify-source-datasets.mjs`.
- `task-source-gate.csv` marks 4 tasks as `source_backed_seed_row`, 1 task as
  `source_backed_but_derivation_not_locked`, and 8 tasks as
  `smoke_only_not_public_training_claim`.
- 13 `tools/tool-observations.jsonl` files validate.
- 67 agent-visible observations are captured.
- 41 observations are live sibling-domain-tool captures.
- 26 observations are imported deterministic scientific-data fixture
  observations.
- Observation rows use repo tokens instead of local absolute paths, so they are
  ready for the replay-bundle conversion pass.
- 13 deterministic verifier specs exist.
- 13 known-good answers pass and 13 known-bad answers fail with
  `tools/verify-seed-answers.mjs`.
- `exports/split.seed-smoke.json` records the current deterministic 7/3/3
  train/dev/test smoke split.
- `exports/eval.seed.jsonl` has 13 context-eval smoke rows over that split.
- `exports/eval.tool_env.seed.jsonl` has 13 tool-env eval rows with no
  preloaded replay observations; this is the primary environment-facing eval
  contract.
- `exports/sft.seed.chat.jsonl` has 7 train-only final-answer SFT smoke rows
  derived from verifier-passing answers.
- `exports/sft.tool_messages.seed.jsonl` has 7 train-only
  system/user/assistant/tool SFT rows for normal post-training loaders.
- `exports/sft.tool_evidence.seed.jsonl` has the same 7 train-only
  tool-evidence SFT rows in the Datalox audit/provenance shape. Four rows are
  captured from sibling domain-tool runtimes
  (`flowcyto`/`molecule-biology`), and three rows are fixture-tool rollouts from
  scientific-data QC. The sibling-domain rows remain smoke rows for a public
  training claim until recaptured from the approved public sources.
- `exports/eval_command.md` records the trainable-base baseline command. Closed
  API models are reference baselines only unless that same model can be
  fine-tuned by the post-training workflow.
- `exports/eval.baseline.smoke.jsonl` passes local verifier plumbing with
  13 expected verifier failures. A real model baseline still requires a
  reachable trainable open-weight model endpoint or the model team's own
  inference stack. The real training proof still requires a tool-using agent
  harness for `exports/eval.tool_env.seed.jsonl`.

The current `task-candidates.csv` is a workflow-debug reserve pool, not the
primary training dataset. Its job is to preserve public provenance candidates
for cheap replay/verifier smoke tests.

Current workflow-debug reserve pool:

- 18 public candidates
- 18 `include_candidate`
- all candidates are scientific workflow, bioinformatics tooling, workflow CI,
  or scientific Python ecosystem tasks
- no generic pytest/pandas/transformers CI candidates remain
- task ids are source-specific, for example `snakemake-*`, `nextflow-*`,
  `bioconda-*`, `galaxy-*`, `nfcore-*`, and `scanpy-*`

## Task Selection Rule

Include tasks only when they match the Datalox environment story:

- scientific data, scientific workflow, bioinformatics, scientific Python,
  tool/API, or MCP-style workflow task
- at least three families in the seed: FlowCyto, Molecule Biology, and
  scientific-data QC
- no family above 40% of the seed handoff
- text-first and replayable from artifact/log/doc/tool observations
- deterministic verifier can check diagnosis, evidence ids, next action, missing
  fields, and forbidden claims
- failure mode is useful for an agent environment, not just a generic benchmark
  puzzle
- issue-only classification is not enough for the primary v0

Reject tasks when:

- the task is a broad feature request with no concrete failure artifact
- the only success signal requires a human judge or vision model
- source provenance cannot be published or approved for private use
- the expected answer cannot be checked with evidence references
- the task can be solved from a GitHub issue title/body without inspecting
  files, logs, metrics, or tool outputs

## Dataset Size Rule

Do not expect reliable model improvement from the 10-20 seed pool. That pool is
only for handoff validation and task/verifier design.

| Stage | Size | Purpose | Expected Claim |
|---|---:|---|---|
| Seed handoff | 12-15 tasks across 3 families | Validate domain relevance, family variety, provenance, schema, tool observations, and verifier feasibility | "We turned multiple scientific workflow families into replayable fixture tasks." |
| MVP lift test | 30 train / 10 dev / 10 test | Test whether SFT has any signal without overfitting to one family | "Small held-out signal, if present; no-lift is diagnostic." |
| Credible demo | 80 train / 20 dev / 20 test | Public traction demo with locked split, family stratification, and cost report | "Datalox environment data is reusable and can improve a small model." |
| Design-partner pilot | 200+ train / 50 dev / 50 test | Private or domain-specific proof | "Private environment traces can become useful training/eval data." |

## Expansion Quotas For MVP

Build the 50-task MVP from the same environment-adjacent sources. Keep the split
stratified by family and answer class.

| Source Family | Target Count | Notes |
|---|---:|---|
| FlowCyto gating/QC/report | 12 | Gate stats, QC evidence, report validation, stale-revision recovery, metadata/compensation audit. |
| Molecule Biology sequence workflows | 12 | FASTA/GenBank import, feature/primer edits, restriction digest, PCR simulation, export validation. |
| Scientific-data QC artifacts | 16 | FastQC, Qualimap, single-cell QC, FCS metadata, mmCIF/protein-structure readiness, additional public reports. |
| Workflow-debug reserve | 10 | Snakemake, Nextflow, Bioconda, nf-core, Galaxy only when replay includes files/logs/tool observations. |

Split after final inclusion:

- train: 30
- dev: 10
- test: 10

The split should be stratified by source family and answer class so test is not
only one failure type. Keep issue-derived reserve tasks below 20% of the MVP
unless a design partner specifically wants workflow-debug data.

## Expansion Quotas For Credible Demo

For the 120-task credible demo:

- train: 80
- dev: 20
- test: 20
- each source family should contribute at least 10 tasks
- no repository should dominate more than 30% of the held-out test split
- include at least three answer classes per major family where possible:
  `validated_success`, `evidence_missing`, `stale_or_conflicting_state`,
  `metadata_or_qc_decision`, and `deterministic_tool_result`

## No-Lift Interpretation

No SFT lift does not automatically mean the environment is bad. The report must
diagnose:

- too few tasks
- task/environment mismatch
- SFT row format too noisy
- context too long
- baseline model too weak or too strong
- verifier too narrow
- split too difficult or not stratified

The primary Datalox success remains replayability, verifier evidence, and clean
exports. Model lift is downstream evidence, not the only pass/fail condition.
