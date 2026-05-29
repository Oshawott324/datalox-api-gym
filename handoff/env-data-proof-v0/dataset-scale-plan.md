# Env Data Proof v0 Dataset Scale Plan

Updated: 2026-05-29

## Primary v0 Direction

The primary seed should now be five scientific-data fixture worlds, not the
GitHub-issue workflow-debug set. The issue set remains useful as a reserve
track, but it is coding-adjacent and too close to generic issue triage unless
each issue is converted into a replay-rich workspace with files, logs, command
outputs, and deterministic verifier observations.

Primary v0 files:

- `selected-scientific-data-worlds.csv`
- `scientific-data-fixture-worlds.md`
- `schema/scientific-data-task-output.schema.json`

Primary v0 claim:

> Datalox turns real scientific artifacts into replayable, verifier-backed
> agent training/eval data.

Do not claim model lift from this seed. The first claim is that the fixture
worlds are source-backed, tool-rich, deterministic, and exportable.

## Outcome Of The Current Task-Selection Step

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
| Seed handoff | 5 scientific-data worlds | Validate domain relevance, provenance, schema, parser/tool observations, and verifier feasibility | "We turned real scientific artifacts into replayable fixture worlds." |
| MVP lift test | 30 train / 10 dev / 10 test | Test whether SFT has any signal | "Small held-out signal, if present; no-lift is diagnostic." |
| Credible demo | 80 train / 20 dev / 20 test | Public traction demo with locked split and cost report | "Datalox environment data is reusable and can improve a small model." |
| Design-partner pilot | 200+ train / 50 dev / 50 test | Private or domain-specific proof | "Private environment traces can become useful training/eval data." |

## Expansion Quotas For MVP

Build the 50-task MVP from the same environment-adjacent sources:

| Source Family | Target Count | Notes |
|---|---:|---|
| Snakemake workflow failures | 8 | Parse/runtime/workflow-source-path issues. |
| Nextflow workflow failures | 8 | Parser, static typing, misleading error, process output issues. |
| Bioconda packaging/CI failures | 8 | Container tests, rate limits, architecture, host-specific failures. |
| Galaxy test/platform failures | 8 | Flaky tests and platform/tool dispatch issues. |
| nf-core lint/workflow-tool failures | 8 | Lint false positives, snapshot mismatch, schema/config issues. |
| Scientific Python analysis stack | 10 | Scanpy, AnnData, scverse, PyData-adjacent compatibility or CI failures. |

Split after final inclusion:

- train: 30
- dev: 10
- test: 10

The split should be stratified by source family and answer class so test is not
only one failure type.

## Expansion Quotas For Credible Demo

For the 120-task credible demo:

- train: 80
- dev: 20
- test: 20
- each source family should contribute at least 10 tasks
- no repository should dominate more than 30% of the held-out test split
- include at least three answer classes: `ci_failure_root_cause`, `real_regression`,
  and `flaky_test`

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
