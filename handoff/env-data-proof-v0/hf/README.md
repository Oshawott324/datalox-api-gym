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
- "n<1K"
---

# Datalox Env Data Proof v0

This is a draft dataset card for the Datalox Env Data Proof v0 package.

The package demonstrates how real scientific artifacts can be converted into
replayable, verifier-backed agent training/eval data. It is a seed evidence
package, not a benchmark leaderboard and not a model-lift claim.

## What This Contains

- scientific-data fixture world specs
- public provenance records
- derived parser/tool observations
- deterministic verifier specs
- baseline outputs
- verifier-passing teacher trajectories
- SFT/eval export rows

## Worlds

| World | Domain |
|---|---|
| `fastq-qc-nanopore-fail-001` | FASTQ sequencing QC |
| `single-cell-pbmc3k-qc-summary-001` | single-cell RNA-seq QC |
| `flowcyto-fcs-compensation-metadata-001` | flow cytometry metadata QC |
| `protein-structure-ap5a-prep-001` | protein structure preparation QC |
| `rnaseq-alignment-qualimap-low-mapq-001` | RNA-seq alignment result QC |

## Intended Use

Use this package to inspect and test the Datalox workflow:

```text
public scientific artifact
  -> fixture workspace
  -> parser/checker tool observations
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
- full FlowCyto gating performance
- protein design performance
- vision-based scientific interpretation

## Data Construction

Each world starts from a public scientific source artifact. Datalox records
agent-visible parser/checker observations, assigns stable evidence ids, packages
the observations into replay evidence, and verifies structured outputs with
deterministic rules.

Raw source artifacts are linked by provenance by default. Derived observations,
parser outputs, verifier specs, and export rows are the primary published
artifacts. Raw files should be copied only after license review.

## Provenance

See each world's `provenance.json` before using or redistributing source
artifacts. The source families include MultiQC test data, 10x Genomics PBMC3k,
flowCore example FCS files, and RCSB PDB structure metadata.

## Limitations

- The seed contains five worlds.
- The package is for replay/verifier/export validation, not reliable SFT lift.
- Some raw source artifacts may be linked rather than copied.
- The single-cell world needs a locked QC-generation script before publication.
- No live source URL should be called during replay.

## Cost

The v0 package is expected to be built mostly with local CPU work plus one cheap
baseline model pass. See `reports/cost-report.md` or the source repo's
`cost-estimate.md` for the current planning estimate.

## Citation

If this package is used in a report, cite the Datalox Env Data Proof v0 dataset
and the upstream public source artifacts listed in each `provenance.json`.
