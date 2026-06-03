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
- molecule-biology
- protein-structure
- single-cell
- sft
size_categories:
- "n<1K"
---

# Datalox Env Data Proof v0

This is a draft dataset card for the Datalox Env Data Proof v0 package.

The package demonstrates the replay/data layer underneath Datalox's broader
agent-native environment vision: real scientific workflow tasks across
FlowCyto, Molecule Biology, and scientific-data QC can be converted into
replayable, verifier-backed agent training/eval data. It is a seed evidence
package, not a benchmark leaderboard and not a model-lift claim.

## What This Contains

- multi-family fixture task specs
- public provenance records
- source dataset manifest and task-source gate
- derived parser/domain-tool observations
- deterministic verifier specs
- baseline outputs
- verifier-passing teacher trajectories
- SFT/eval export rows

## Families And Seed Tasks

| Family | Count | Examples |
|---|---:|---|
| FlowCyto gating/QC/report | 3 | gate stats, report validation, stale-revision recovery |
| Molecule Biology sequence workflows | 5 | FASTA/GenBank context, feature/primer edits, digest/PCR simulation |
| Scientific-data QC artifacts | 5 | FastQC, PBMC3k, FCS metadata, protein structure prep, Qualimap |

## Intended Use

Use this package to inspect and test the Datalox workflow:

```text
public scientific artifact or domain MCP fixture
  -> agent-native fixture workspace
  -> parser/checker/domain-tool observations
  -> replay bundle
  -> deterministic verifier
  -> SFT/eval export
```

The expected users are agent-environment builders, training/eval teams, and
researchers inspecting replay-backed scientific workflow data.

## Non-Claims

This v0 does not claim:

- model improvement
- benchmark leaderboard comparability
- online RL readiness
- open-ended FlowCyto vision performance
- protein design performance
- vision-based scientific interpretation

## Data Construction

Each public training-claim task must start from an approved source id in
`source-datasets.manifest.json`. Datalox records agent-visible
parser/checker/domain-tool observations, assigns stable evidence ids, packages
the observations into replay evidence, and verifies structured outputs with
deterministic rules.

Raw source artifacts are linked by provenance by default. Derived observations,
parser outputs, verifier specs, and export rows are the primary published
artifacts. Raw files should be copied only after license review.

## Provenance

See `source-datasets.manifest.json`, `source-datasets.csv`, and
`task-source-gate.csv` before using or redistributing source artifacts. The
source pool includes flowCore FCS examples, NCBI accession-versioned sequence
records, MultiQC test data, 10x Genomics PBMC3k, and RCSB PDB structure
metadata.

## Limitations

- The seed contains 13 candidate tasks, not enough for a reliable lift claim.
- The package is for replay/verifier/export validation, not reliable SFT lift.
  The primary collaborator-facing training handoff is
  `exports/sft.tool_messages.seed.jsonl`, which uses standard
  system/user/assistant/tool turns. `exports/sft.tool_trajectory.seed.jsonl`
  keeps the same information in a Datalox audit/provenance shape. The
  final-answer `exports/sft.seed.chat.jsonl` is only a formatting smoke file.
- The current split is `seed-smoke`: 7 train, 3 dev, and 3 test tasks. It is a
  handoff smoke split, not a lift-grade split.
- Some raw source artifacts may be linked rather than copied.
- The single-cell world needs a locked QC-generation script before publication.
- Current FlowCyto and Molecule Biology seed rows use project-local or toy repo
  fixtures. They are smoke rows until recaptured from the approved public
  flowCore and NCBI sources in `task-source-gate.csv`.
- No live source URL should be called during replay.

## Cost

The v0 package is expected to be built mostly with local CPU work plus one
trainable open-weight base-model pass when a model endpoint is available. See
`reports/cost-report.md` or the source repo's `cost-estimate.md` for the
current planning estimate.

## Citation

If this package is used in a report, cite the Datalox Env Data Proof v0 dataset
and the upstream public source artifacts listed in each `provenance.json`.
