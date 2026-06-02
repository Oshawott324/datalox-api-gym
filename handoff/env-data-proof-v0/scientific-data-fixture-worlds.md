# Env Data Proof v0 Scientific Data Fixture Worlds

Updated: 2026-05-30

## Decision

These five scientific-data fixture worlds are now the cheap public scaling lane
inside the multi-family v0 seed. They are no longer the whole primary seed by
themselves. The full seed also includes FlowCyto gating/QC/report tasks and
Molecule Biology sequence-workflow tasks from sibling domain MCP repos.

The selected worlds are:

1. `fastq-qc-nanopore-fail-001`
2. `single-cell-pbmc3k-qc-summary-001`
3. `flowcyto-fcs-compensation-metadata-001`
4. `protein-structure-ap5a-prep-001`
5. `rnaseq-alignment-qualimap-low-mapq-001`

The machine-readable selection is in `selected-scientific-data-worlds.csv`.
The output contract is `schema/scientific-data-task-output.schema.json`.

## Why This Replaces Issue Triage As The Cheap Scaling Lane

The previous 10 GitHub issue tasks are useful as a workflow-debug reserve, but
they are still coding-adjacent. They mostly start from issue text and become
Datalox-relevant only if we add repo state, command output, and replayed logs.

The scientific-data lane starts from real scientific artifacts:

- FastQC report
- 10x PBMC3k matrix and derived single-cell QC table
- FCS file and compensation matrix
- RCSB mmCIF protein structure
- Qualimap BamQC report

This better matches the Datalox product claim:

```text
public scientific artifact
  -> file-backed fixture workspace
  -> tool calls compute or inspect domain metadata
  -> replayed observations
  -> structured diagnosis / next action
  -> deterministic verifier
  -> SFT/eval export
```

It is still cheap and text-first, but it is no longer just software debugging.

## Acceptance Gate

A world is accepted only if it passes all gates:

| Gate | Minimum |
|---|---:|
| Public provenance | source URL resolves and has a pinned commit, ETag, or stable release reference |
| Artifact types | at least 2 per world |
| Intended tool observations | at least 5 |
| Domain parser/checker | yes |
| Deterministic verifier | yes |
| Issue-only answer possible | no |
| Vision model required | no |
| Live service required during replay | no |

The task prompt must not leak the answer in the title. The agent should inspect
files through tools and cite evidence ids from replayed observations.

## Selected Worlds

### 1. FASTQ QC: `fastq-qc-nanopore-fail-001`

Source:

- `https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/fastqc/nan_reads/fastqc_data.txt`
- `MultiQC/test-data` HEAD verified at
  `84dc905e6edb97668b87660896dfd78f175008ca`
- raw ETag verified as
  `ab8d2041df37698afb21c147042360174aadbbe97e976c6cfbd677141bbb561f`

Live source check:

- sample filename: `sample1_S1_L001_R2_001.fastq.gz`
- total sequences: `82330`
- sequence length: `301`
- failed modules include per-base quality, per-tile quality, per-base sequence
  content, per-base N content, sequence duplication, and adapter content
- warning modules include per-sequence quality scores and overrepresented
  sequences

Intended tool path:

```text
list_workspace
  -> parse_fastqc_report
  -> inspect_failed_modules
  -> apply_fastq_qc_policy
  -> emit scientific-data output
  -> verifier checks required metric evidence ids
```

Expected class: `fastq_qc_decision`

Expected next action: `trim_or_filter_reads`

Why it matters: sequencing QC is a real scientific workflow step, and the task
tests whether the agent can reason over report modules and metrics rather than
debug code.

### 2. Single-Cell QC: `single-cell-pbmc3k-qc-summary-001`

Source:

- `https://cf.10xgenomics.com/samples/cell-exp/1.1.0/pbmc3k/pbmc3k_filtered_gene_bc_matrices.tar.gz`
- companion web summary verified:
  `https://cf.10xgenomics.com/samples/cell-exp/1.1.0/pbmc3k/pbmc3k_web_summary.html`
- 10x tarball verified with content length `7621991` and last modified date
  `2017-06-02`

Fixture plan:

- vendor or cache the 10x matrix once
- run a locked Scanpy script to produce a small QC table
- replay the generated QC table and script output, not the live 10x download

Intended tool path:

```text
list_workspace
  -> inspect_sample_metadata
  -> run_or_replay_scanpy_qc
  -> inspect_qc_table
  -> apply_single_cell_qc_policy
  -> emit scientific-data output
```

Expected class: `single_cell_qc_decision`

Expected next action: `exclude_sample`

Why it matters: single-cell QC is domain work over scientific data. The agent
must cite computed metrics and affected cell/sample ids.

Known risk: this world requires a locked fixture-generation script before it is
ready for baseline. Do not call the live 10x URL during replay.

### 3. Flow Cytometry Metadata QC: `flowcyto-fcs-compensation-metadata-001`

Sources:

- FCS file:
  `https://raw.githubusercontent.com/RGLab/flowCore/master/inst/extdata/0877408774.E07`
- compensation matrix:
  `https://raw.githubusercontent.com/RGLab/flowCore/master/inst/extdata/compdata/compmatrix`
- `RGLab/flowCore` HEAD verified at
  `4935c7bf318697b3128ee50dae81018a6b246ab8`
- FCS raw ETag verified as
  `9c15c60e305c825fca67aae73643cafedab83b1bcfcd4bbbdd0da865ce73ba9a`

Live source check:

- FCS metadata includes `10000` events and 8 parameters
- fluorescence channels include `FL1-H`, `FL2-H`, `FL3-H`, `FL4-H`, and
  `FL1-A`
- compensation matrix covers `FL1-H`, `FL2-H`, `FL3-H`, and `FL4-H`
- marker labels for fluorescence channels are empty in the inspected metadata

Intended tool path:

```text
list_workspace
  -> parse_fcs_metadata
  -> parse_compensation_matrix
  -> compare_channel_coverage
  -> inspect_marker_annotations
  -> emit scientific-data output
```

Expected class: `flowcyto_metadata_decision`

Expected next action: `repair_metadata`

Why it matters: this is the cheapest FlowCyto-adjacent task. It avoids vision
and gating judgment but still uses domain files, channel metadata, compensation
state, and deterministic checks.

### 4. Protein Structure Prep QC: `protein-structure-ap5a-prep-001`

Sources:

- mmCIF:
  `https://files.rcsb.org/download/1AKE.cif`
- optional entry JSON:
  `https://data.rcsb.org/rest/v1/core/entry/1AKE`

Live source check:

- RCSB mmCIF HTTP 200 verified on 2026-05-29
- data API reports method `X-RAY DIFFRACTION`
- data API reports `resolution_combined` as `[2]`
- title describes adenylate kinase complex with inhibitor AP5A
- mmCIF contains ligand `AP5`
- entry has one polymer entity and one non-polymer entity

Intended tool path:

```text
list_workspace
  -> parse_mmcif_metadata
  -> inspect_experimental_method_and_resolution
  -> inspect_polymer_and_ligand_entities
  -> apply_structure_prep_policy
  -> emit scientific-data output
```

Expected class: `protein_structure_prep_decision`

Expected next action: `prepare_structure`

Why it matters: this is protein-structure domain work without design-loop cost.
It tests whether an agent can cite chain/ligand/resolution evidence before
claiming a structure is suitable for downstream preparation.

Known risk: this is structure-readiness triage, not protein design. Later tasks
should add binding-site checks, mutation constraints, or design objectives.

### 5. RNA-Seq Alignment QC: `rnaseq-alignment-qualimap-low-mapq-001`

Source:

- `https://raw.githubusercontent.com/MultiQC/test-data/main/data/modules/qualimap/bam_qc/issue_2199_zero_aligned/genome_results.txt`
- `MultiQC/test-data` HEAD verified at
  `84dc905e6edb97668b87660896dfd78f175008ca`
- raw ETag verified as
  `de299db987e8c038368088c7584ef2fac900839e7353ebeb1a8c1a13b3bc647b`

Live source check:

- number of reads: `84125`
- mapped reads: `82635 (98.23%)`
- aligned bases: `0 bp`
- mean mapping quality: `0.1184`
- mean coverage: `0.0024X`

Intended tool path:

```text
list_workspace
  -> parse_qualimap_report
  -> extract_alignment_metrics
  -> apply_alignment_qc_policy
  -> identify misleading pass signal
  -> emit scientific-data output
```

Expected class: `workflow_result_qc_decision`

Expected next action: `rerun_analysis`

Why it matters: this tests scientific workflow result interpretation. A weak
agent may anchor on the 98.23% mapped-read rate and miss the near-zero mapping
quality, zero aligned bases, and negligible coverage.

## Relationship To The GitHub Issue Set

The previous selected GitHub issues are now the reserve workflow-debug track:

- use them for cheap replay/verifier smoke tests
- do not use them as the main public Datalox proof
- only promote an issue task if it becomes replay-rich with repo files, command
  output, logs, and deterministic verifier observations

The main v0 product claim should come from the multi-family seed: FlowCyto,
Molecule Biology, and the five scientific-data worlds above. These worlds
remain important because they are public, cheap, and text/table-first.

## Next Implementation Steps

For each scientific-data world:

1. Create `task.spec.json`.
2. Vendor or cache source artifacts with checksums.
3. Implement or stub the domain parser tool.
4. Capture at least five tool observations.
5. Write verifier spec against `scientific-data-task-output.schema.json`.
6. Run a trainable open-weight base-model baseline.
7. Keep the world only if the baseline failure is real and verifier evidence is
   deterministic.
8. Produce one verifier-passing teacher trajectory and one `sft_frame.v1` row.
