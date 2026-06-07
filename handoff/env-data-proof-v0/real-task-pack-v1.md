# Real Task Pack v1

Updated: 2026-06-07

## Purpose

This pack is the next source-backed task set for Zheng review and later rollout
capture. It is not another schema step and it is not a model-lift claim.

The target is a small but meaningful domain-world seed:

```text
real public artifact
  -> resettable domain workspace
  -> tool-mediated state transition
  -> deterministic verifier
  -> trajectory export chosen by the post-training team
```

The machine-readable review table is
`handoff/env-data-proof-v0/real-task-pack-v1.csv`.

## Selected Mix

| Slot | Task | Status |
|---|---|---|
| FASTQ/RNA QC 1 | `fastq-qc-nanopore-fail-001` | Source-backed current world |
| FASTQ/RNA QC 2 | `rnaseq-alignment-qualimap-low-mapq-001` | Source-backed current world |
| Molecule sequence 1 | `molecule-primer-validation-001` | Public source ready; needs recapture |
| Molecule sequence 2 | `molecule-genbank-feature-annotation-001` | Public source ready; needs recapture |
| FlowCyto 1 | `flowcyto-fcs-compensation-metadata-001` | Source-backed current world |
| FlowCyto 2 | `flowcyto-gating-qc-stale-revision-failure` | Public source ready; needs FlowCyto recapture |
| Protein/PDB 1 | `protein-structure-ap5a-prep-001` | Source-backed current world |

This gives seven tasks. Four are already source-backed current worlds. Three
are better source choices for tasks that previously used toy or project-local
fixtures and must be recaptured before any public training claim.

## Why This Set

The previous two-task runnable packet was useful for interface review, but it
was too narrow. This set adds more domain variety without jumping to expensive
vision-heavy or protein-design workflows.

The important distinction is transition type:

| Transition type | Included tasks |
|---|---|
| Read-only artifact -> parsed domain state -> policy state | FASTQ QC, RNA alignment QC, FlowCyto metadata QC, protein prep QC |
| Workspace revision 0 -> tool write -> revision 1 -> verifier | molecule primer, molecule feature |
| State write -> verifier rejection -> recovery write | FlowCyto stale-revision recovery |

The strongest causal-mechanism tasks are the molecule and FlowCyto recovery
tasks because the world state actually changes and the verifier can reject a
wrong transition. The read-only QC tasks remain useful because they are cheap,
real, and source-backed.

## Task Cards

### 1. FASTQ QC Failure

Task id: `fastq-qc-nanopore-fail-001`

Source data:

- `multiqc-fastqc-nan-reads`
- Pinned URL:
  `https://raw.githubusercontent.com/MultiQC/test-data/84dc905e6edb97668b87660896dfd78f175008ca/data/modules/fastqc/nan_reads/fastqc_data.txt`
- Fresh check on 2026-06-07 returned HTTP 200 and ETag
  `ab8d2041df37698afb21c147042360174aadbbe97e976c6cfbd677141bbb561f`.

Agent job:

```text
Inspect the FastQC report, decide whether the sample passes QC, cite failed
modules, and choose the next action.
```

Transition:

```text
FastQC artifact
  -> fastqc.parse_report returns module status state
  -> qc_policy.evaluate returns fail/pass policy state
  -> verifier accepts only cited failed-module evidence and next action
```

Expected failure:

The agent anchors on one acceptable metric, misses failed modules, or submits a
diagnosis without evidence ids.

Next capture action:

Convert the current deterministic observations to a replay bundle, then run one
cheap baseline and one verifier-passing reference trajectory.

### 2. RNA-Seq Alignment QC

Task id: `rnaseq-alignment-qualimap-low-mapq-001`

Source data:

- `multiqc-qualimap-zero-aligned`
- Pinned URL:
  `https://raw.githubusercontent.com/MultiQC/test-data/84dc905e6edb97668b87660896dfd78f175008ca/data/modules/qualimap/bam_qc/issue_2199_zero_aligned/genome_results.txt`
- Fresh check on 2026-06-07 returned HTTP 200 and ETag
  `de299db987e8c038368088c7584ef2fac900839e7353ebeb1a8c1a13b3bc647b`.

Agent job:

```text
Inspect the Qualimap report and decide whether the RNA-seq alignment result is
acceptable despite a high mapped-read percentage.
```

Transition:

```text
Qualimap artifact
  -> alignment.parse_qualimap extracts mapped reads, aligned bases, mapQ, coverage
  -> qc_policy.evaluate flags zero aligned bases / low mapQ
  -> verifier checks rerun-analysis next action
```

Expected failure:

The agent overweights mapped-read percentage and misses aligned bases of `0 bp`
or mean mapping quality near zero.

Next capture action:

Convert the current deterministic observations to a replay bundle, then run one
cheap baseline and one verifier-passing reference trajectory.

### 3. Molecule Primer Validation

Task id: `molecule-primer-validation-001`

Source data:

- `ncbi-nc005816-genbank`
- Versioned accession: `NC_005816.1`
- URL:
  `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id=NC_005816.1&rettype=gb&retmode=text`
- Fresh check on 2026-06-07 resolved the record as plasmid pPCP1,
  `9609 bp`, circular DNA.

Concrete target:

```text
primer id: primer_pcp1_start_20
primer sequence: TGTAACGAACGGTGCAATAG
expected exact binding: NC_005816.1 bases 1..20 on the plus strand
```

Agent job:

```text
Import NC_005816.1, inspect sequence context, add the specified primer through
the tool, bind it to the molecule, validate the workspace, and report the final
revision with evidence ids.
```

Transition:

```text
GenBank source
  -> open_sequence creates molecule workspace at revision 0
  -> get_sequence_context gives molecule id, digest, sequence region, revision
  -> upsert_primer(expectedRevision=0, bindToMolecule=true) writes primer
  -> workspace revision becomes 1
  -> validate_workspace checks digest, alphabet, coordinates, and binding
```

Expected failure:

The agent patches workspace JSON directly, skips sequence context, uses a stale
revision, or adds a primer without binding evidence.

Next capture action:

Replace the toy circular fixture with `NC_005816.1` and recapture through
`datalox-molecule-biology`.

### 4. Molecule Feature Annotation

Task id: `molecule-genbank-feature-annotation-001`

Source data:

- `ncbi-nc001416-genbank`
- Versioned accession: `NC_001416.1`
- URL:
  `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id=NC_001416.1&rettype=gb&retmode=text`
- Fresh check on 2026-06-07 resolved the record as bacteriophage lambda,
  `48502 bp`, linear DNA.

Concrete target:

```text
feature id: feat_lambda_nu1_review
feature name: lambda nu1 terminase small subunit review region
feature type: misc_feature
segment: 191..736 on the plus strand
source evidence in GenBank: gene="nu1", product="terminase small subunit"
```

Agent job:

```text
Import NC_001416.1, inspect the nu1 region, add the review feature through the
tool, validate the workspace, and report the final revision with evidence ids.
```

Transition:

```text
GenBank source
  -> open_sequence creates molecule workspace at revision 0
  -> get_sequence_context(191..736) exposes imported gene/CDS context
  -> upsert_feature(expectedRevision=0) writes the review feature
  -> workspace revision becomes 1
  -> validate_workspace checks coordinate bounds and feature state
```

Expected failure:

The agent confuses gene and CDS coordinates, submits a prose-only annotation, or
ignores revision-safe writes.

Next capture action:

Replace the toy linear GenBank fixture with `NC_001416.1` and recapture through
`datalox-molecule-biology`.

### 5. FlowCyto Metadata And Compensation QC

Task id: `flowcyto-fcs-compensation-metadata-001`

Source data:

- `flowcore-0877408774-e07-fcs`
- `flowcore-compmatrix`
- Pinned URLs:
  `https://raw.githubusercontent.com/RGLab/flowCore/4935c7bf318697b3128ee50dae81018a6b246ab8/inst/extdata/0877408774.E07`
  and
  `https://raw.githubusercontent.com/RGLab/flowCore/4935c7bf318697b3128ee50dae81018a6b246ab8/inst/extdata/compdata/compmatrix`
- Fresh check on 2026-06-07 returned HTTP 200 for the FCS file and preserved
  ETag `9c15c60e305c825fca67aae73643cafedab83b1bcfcd4bbbdd0da865ce73ba9a`.

Agent job:

```text
Inspect FCS metadata and compensation matrix coverage, decide whether metadata
is ready for downstream analysis, and cite channel/compensation evidence.
```

Transition:

```text
FCS file + compensation matrix
  -> flowcyto.parse_fcs_keywords returns channels, parameters, labels
  -> flowcyto.parse_compensation_matrix returns covered fluorescence channels
  -> qc_policy.evaluate checks coverage and marker-label readiness
  -> verifier accepts repair-metadata next action
```

Expected failure:

The agent jumps to plot/gating claims, ignores empty marker labels, or does not
compare compensation coverage to channels.

Next capture action:

Convert the current deterministic observations to a replay bundle.

### 6. FlowCyto Stale-Revision Recovery

Task id: `flowcyto-gating-qc-stale-revision-failure`

Source data:

- `flowcore-0877408774-b08-fcs`
- Pinned URL:
  `https://raw.githubusercontent.com/RGLab/flowCore/4935c7bf318697b3128ee50dae81018a6b246ab8/inst/extdata/0877408774.B08`
- Fresh check on 2026-06-07 returned HTTP 200 and ETag
  `5efdb75e55b30fb443bdd5d0d330aa68c68a7f17db574026c3a17992b5465f68`.

Agent job:

```text
Open the FCS file, get plot context, create a main FSC/SSC gate, compute stats,
validate QC, intentionally submit a report with a stale revision, then recover
with the current revision.
```

Transition:

```text
FCS file
  -> open_fcs creates flowcyto workspace at revision 0
  -> upsert_gate(expected_revision=0) writes gate and moves workspace to revision 1
  -> compute_gate_stats creates stats evidence ref
  -> validate_gate_qc creates QC evidence ref and report nextAction
  -> submit_report(expected_revision=0) returns stale_revision and does not persist report
  -> get_workspace_revision or nextAction reveals revision 1
  -> submit_report(expected_revision=1) persists report
```

Expected failure:

The agent stops after `open_fcs`, submits a report without stats/QC refs, or
fails to recover after `stale_revision`.

Next capture action:

Recapture this from the public flowCore B08 fixture through
`datalox-flow-cyto-mcp`. The old task spec points to project-local
`CFP_Well_A4.fcs`, so it is not yet public-training eligible.

### 7. Protein Structure AP5A Prep

Task id: `protein-structure-ap5a-prep-001`

Source data:

- `rcsb-1ake-cif`
- `rcsb-1ake-entry-json`
- URLs:
  `https://files.rcsb.org/download/1AKE.cif`
  and
  `https://data.rcsb.org/rest/v1/core/entry/1AKE`
- Fresh check on 2026-06-07 returned HTTP 200 for the mmCIF. The mmCIF includes
  X-ray diffraction, resolution `2.0`, chains `A,B`, and AP5 ligand records.

Agent job:

```text
Inspect RCSB 1AKE and decide whether the structure is ready for preparation.
Do not claim docking, mutation design, or binding-design results.
```

Transition:

```text
RCSB mmCIF + entry JSON
  -> protein.parse_mmcif_metadata extracts method, resolution, chains, ligand
  -> qc_policy.evaluate checks preparation readiness
  -> verifier accepts prepare-structure next action only with evidence ids
```

Expected failure:

The agent claims downstream design or docking readiness without citing method,
resolution, AP5 ligand, and chain/entity evidence.

Next capture action:

Convert current deterministic observations to a replay bundle. A stronger later
protein task can use PyMOL viewer state, but this first task should stay cheap.

## Handoff Boundary

What Zheng should receive from this pack:

- the task IDs;
- the public source IDs and URLs;
- the intended tool path for each task;
- the concrete state transition each task should exercise;
- the expected small-model failure mode;
- whether the row is ready now or needs recapture.

What this pack does not claim yet:

- no seven-task model baseline has been run;
- no seven-task verifier-passing trajectory set exists yet;
- molecule and FlowCyto recovery tasks still require recapture from public
  sources before public training use.

## Next Step

Implement capture in this order:

1. Convert the four source-backed current worlds to replay bundles:
   FASTQ QC, RNA alignment QC, FlowCyto metadata QC, protein prep QC.
2. Recapture `molecule-primer-validation-001` from `NC_005816.1`.
3. Recapture `molecule-genbank-feature-annotation-001` from `NC_001416.1`.
4. Recapture `flowcyto-gating-qc-stale-revision-failure` from flowCore B08.
5. Run one cheap baseline per task and keep only observed failure modes.
6. Record one verifier-passing reference trajectory per task.
