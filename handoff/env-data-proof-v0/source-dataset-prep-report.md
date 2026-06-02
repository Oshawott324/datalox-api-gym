# Env Data Proof v0 Source Dataset Prep

Updated: 2026-06-02

## What Was Prepared

This step adds a source-dataset layer before any further SFT or eval claims.
The authoritative files are:

- `source-datasets.manifest.json`: machine-readable public source manifest.
- `source-datasets.csv`: quick review table for the same source pool.
- `task-source-gate.csv`: task-level gate that says whether current seed
  observations are source-backed or still smoke/proxy rows.
- `schema/source-dataset-manifest.schema.json`: schema for the manifest.
- `tools/verify-source-datasets.mjs`: live URL/schema verifier.

The public source pool now covers:

| Family | Prepared Sources | Role |
|---|---:|---|
| FlowCyto | 3 | Public flowCore FCS files and compensation matrix. |
| Molecule Biology | 4 | NCBI accession-versioned GenBank/FASTA records. |
| Scientific-data QC | 5 | MultiQC reports/tables and 10x PBMC3k matrix. |
| Protein structure | 2 | RCSB 1AKE mmCIF and entry JSON. |

## Source Boundary

This does not copy raw biological datasets into the repo. The default
publication policy is:

```text
publish source URL + pin + derived tool observations + verifier evidence
copy raw artifacts only after license/provider review
```

That is intentional. For Hugging Face, the first public package should publish
the Datalox task specs, replay evidence, verifier specs, and export rows. Raw
scientific files should be linked by provenance unless their redistribution
status is explicitly reviewed.

## Current Seed Reality

The current 13 seed tasks are not all equally ready for a public training
claim.

| Status | Count | Meaning |
|---|---:|---|
| `source_backed_seed_row` | 4 | Current deterministic observations are already tied to public sources; convert to canonical replay bundles before export. |
| `source_backed_but_derivation_not_locked` | 1 | Public sources exist, but the generation script from the raw source needs to be locked. |
| `smoke_only_not_public_training_claim` | 8 | Current observations use project-local FlowCyto or toy Molecule fixtures; recapture from approved public sources first. |

The eight smoke-only rows are still useful for schema, verifier, and export
plumbing. They should not be used to claim that Datalox has produced meaningful
public domain training data until recaptured from the approved source ids in
`task-source-gate.csv`.

## Recapture Targets

### FlowCyto

Current FlowCyto captures use:

```text
datalox-flow-cyto-mcp/testdata/fixtures/CFP_Well_A4.fcs
```

That is a project-local fixture. For public seed recapture, use:

- `flowcore-0877408774-e07-fcs`
- `flowcore-0877408774-b08-fcs`
- `flowcore-compmatrix`

These come from pinned `RGLab/flowCore` commit
`4935c7bf318697b3128ee50dae81018a6b246ab8`.

### Molecule Biology

Current Molecule Biology captures use toy fixtures:

```text
fixtures/fasta/single.fa       15 bp
fixtures/genbank/linear.gb     30 bp
fixtures/genbank/circular.gb   24 bp
```

For public seed recapture, use:

- `NC_005816.1`: circular plasmid pPCP1, GenBank and FASTA.
- `NC_001416.1`: bacteriophage lambda, GenBank and FASTA.

These are large enough to make primer, feature, digest, and PCR tasks feel like
real sequence-workflow tasks while staying cheap to parse.

### Scientific Data And Protein Structure

The existing scientific-data lane is closer to source-backed already:

- FastQC nanopore report from `MultiQC/test-data`.
- Qualimap low-mapQ report from `MultiQC/test-data`.
- flowCore FCS metadata/compensation examples.
- RCSB PDB `1AKE` mmCIF and entry metadata.

The PBMC3k task is the exception: it has public derived CheckAtlas tables, but
the stronger claim requires a locked QC-generation script from the 10x PBMC3k
matrix.

## Acceptance Gate For Future Seed Trajectories

A seed trajectory is eligible for the public training/demo dataset only if all
conditions hold:

1. The task lists one or more approved source ids from
   `source-datasets.manifest.json`.
2. The rollout was captured through the domain or fixture tools from those
   sources, not from a toy proxy.
3. The final answer passes the deterministic verifier.
4. The row has export permission and does not require publishing raw artifacts
   whose license/provider terms are unreviewed.
5. The trajectory is downstream of replay evidence; final-answer-only rows are
   smoke format rows, not the primary training handoff.

## Next Implementation Step

Recapture should happen before expanding SFT rows:

```text
approved source dataset
  -> domain/fixture workspace
  -> tool rollout
  -> tool_io_record.v1
  -> replay_bundle.v1
  -> verifier pass
  -> tool-trajectory SFT/eval export
```

The highest-value order is:

1. Recapture the three FlowCyto tasks from flowCore FCS files.
2. Recapture the five Molecule Biology tasks from NCBI records.
3. Lock the PBMC3k derivation script.
4. Convert the already source-backed scientific-data rows to canonical replay
   bundles.
