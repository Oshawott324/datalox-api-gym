# Datalox Env Data Proof v0 Cost Report

Updated: 2026-05-29

This is a planning cost report for the five-world scientific-data seed. Replace
estimates with actual runtime and spend before public release.

## Scope

The v0 package contains five scientific-data fixture worlds:

- FASTQ sequencing QC
- single-cell RNA-seq QC
- flow cytometry metadata QC
- protein structure preparation QC
- RNA-seq alignment result QC

This seed is for replay/verifier/export validation. It is not a reliable model
lift experiment.

## Estimated Human Time

| Work Item | Estimate |
|---|---:|
| Source/pin/license review | 4-8 hours |
| Fixture artifact generation | 8-15 hours |
| Parser/checker implementation | 12-24 hours |
| Replay capture | 6-10 hours |
| Verifier design | 6-10 hours |
| Baseline run and failure report | 2-4 hours |
| Teacher trajectories | 6-10 hours |
| Dataset card and publish review | 3-6 hours |

Total planning range: 45-85 hours.

## Estimated Direct Spend

| Stage | Estimate |
|---|---:|
| Source plan only | $0 |
| Parser/checker and replay smoke | $0-$50 |
| Cheap baseline eval | $0-$100 |
| Minimal SFT LoRA, if attempted later | $50-$500 |

Expected direct spend for the v0 seed before training: $0-$150.

## Publication Note

The first public release should report actual:

- model name
- provider or local runtime
- GPU/CPU type if used
- wall-clock runtime
- API or compute spend
- number of replay bundles
- number of verifier-passing teacher rows
- number and type of baseline failures
