# Env Data Proof v0 Seed Task Selection

Updated: 2026-05-29

Status: reserve workflow-debug track. This is no longer the primary v0 seed.
Use `scientific-data-fixture-worlds.md` and
`selected-scientific-data-worlds.csv` for the primary scientific-data fixture
world plan.

## Decision

Keep these 10 tasks as reserve workflow-debug candidates:

1. `snakemake-workflow-current-basedir-001`
2. `snakemake-loop-newline-002`
3. `nextflow-no-output-return-004`
4. `nextflow-typed-workflow-parse-001`
5. `nfcore-snapshot-key-order-001`
6. `bioconda-test-source-files-002`
7. `bioconda-raw-github-rate-limit-001`
8. `nfcore-venv-merge-marker-002`
9. `snakemake-github-rate-limit-004`
10. `galaxy-skip-flakey-transient-001`

The machine-readable selection is in `selected-seed-tasks.csv`.

## Why These 10

The first seed package should prove that Datalox can turn real source artifacts
into replayable, verifier-backed agent data. It should not optimize for broad
benchmark coverage yet.

Selection criteria:

- public source URL resolves
- issue body or comments contain enough replayable evidence
- expected answer class fits the frozen schema
- deterministic verifier can check diagnosis class, evidence ids, next action,
  missing fields, and forbidden actions avoided
- task is environment-relevant: scientific workflow, bioinformatics tooling,
  workflow CI, or scientific Python infrastructure
- no vision model, live service, or judge model is needed for v0 verification
- source family mix is not dominated by one project

Selected mix:

| Family | Count | Tasks |
|---|---:|---|
| Snakemake | 3 | `snakemake-workflow-current-basedir-001`, `snakemake-loop-newline-002`, `snakemake-github-rate-limit-004` |
| Nextflow | 2 | `nextflow-no-output-return-004`, `nextflow-typed-workflow-parse-001` |
| Bioconda | 2 | `bioconda-test-source-files-002`, `bioconda-raw-github-rate-limit-001` |
| nf-core | 2 | `nfcore-snapshot-key-order-001`, `nfcore-venv-merge-marker-002` |
| Galaxy | 1 | `galaxy-skip-flakey-transient-001` |

Selected answer classes:

| Answer Class | Count |
|---|---:|
| `real_regression` | 5 |
| `ci_failure_root_cause` | 4 |
| `flaky_test` | 1 |

The Galaxy task is the weakest selected item, but it is intentionally kept to
exercise the `flaky_test` branch of the schema. Replace it if replay capture
cannot produce stable evidence ids.

## Live Source Checks

I fetched live GitHub issue metadata for all 18 candidates through the GitHub
API. The check recorded title, state, labels, comment count, issue body length,
code-fence count, and regex signals for trace/error text, repro snippets, and
resolution/action text. This is not a substitute for a baseline model run, but
it removes tasks that lack enough public evidence to verify.

Key live-source findings:

| Task | Live Evidence Signal |
|---|---|
| `snakemake-workflow-current-basedir-001` | Open bug; body length 1209; 8 code-fence markers; 4 comments; trace, repro, and resolution signals. |
| `snakemake-loop-newline-002` | Open bug; body length 4538; 10 code-fence markers; trace and repro signals. |
| `nextflow-no-output-return-004` | Open issue; body length 1340; 6 code-fence markers; trace and repro signals. |
| `nextflow-typed-workflow-parse-001` | Open issue; body length 1634; 4 code-fence markers; 3 comments; trace, repro, and resolution signals. |
| `nfcore-snapshot-key-order-001` | Open bug; body length 2347; 2 code-fence markers; trace, repro, and resolution signals. |
| `bioconda-test-source-files-002` | Open issue; body length 1366; 2 code-fence markers; 6 comments; trace, repro, and resolution signals. |
| `bioconda-raw-github-rate-limit-001` | Open bug with `bioconda-infrastructure` label; body length 2863; 2 code-fence markers; 6 comments; trace and resolution signals. |
| `nfcore-venv-merge-marker-002` | Open bug; body length 4629; 4 code-fence markers; 5 comments; trace and repro signals. |
| `snakemake-github-rate-limit-004` | Open bug/stale; body length 4941; 4 code-fence markers; 2 comments; trace, repro, and resolution signals. |
| `galaxy-skip-flakey-transient-001` | Open testing issue; body length 1477; 2 code-fence markers; trace and resolution signals. |

## Fresh-Agent Cross-Check

Two fresh agents independently reviewed the candidate pool and live GitHub
sources. Neither edited files. Neither ran reproduction code or a full baseline
LLM harness, so this is a selection cross-check, not an observed-failure claim.

Results:

- Agent A had 9/10 overlap with this selection. It preferred
  `nextflow-static-typing-include-003` over
  `snakemake-workflow-current-basedir-001`.
- Agent B had 10/10 overlap with this selection.
- Both agents rejected or deferred `snakemake-keepgoing-runtime-003`,
  `bioconda-circleci-build-003`, `galaxy-dataset-api-flaky-002`,
  `galaxy-composite-output-flaky-003`, and `scanpy-py314-prerelease-ci-001`.
- Agent B flagged `nextflow-static-typing-include-003` as a watchlist item
  because maintainer comments may make the `real_regression` label disputed.

Decision after cross-check:

- Keep the 10-task set above.
- Put `nextflow-static-typing-include-003` on the reserve list, not the seed
  set, until the expected answer class is clarified.

## Reserve List

Use these if one selected task fails replay capture:

| Reserve Task | Reason |
|---|---|
| `nextflow-static-typing-include-003` | Strong source body and comments, but expected class may be disputed because the behavior may be unsupported rather than a regression. |
| `nextflow-disk-space-message-002` | Good misleading-error shape, but live source has thin repro/output evidence. |
| `bioconda-vsearch-invalid-opcode-004` | Concrete old CI/runtime issue; useful if old Travis context can still be captured cleanly. |

## Reject For v0

| Task | Reason |
|---|---|
| `snakemake-keepgoing-runtime-003` | Labeled/framed as enhancement and less like a concrete failure triage task. |
| `bioconda-circleci-build-003` | Real CI failure, but root cause is unclear from the issue itself; verifier would reward guessing. |
| `galaxy-dataset-api-flaky-002` | Too little issue-body evidence and no rerun/history evidence for deterministic flaky-test verification. |
| `galaxy-composite-output-flaky-003` | Live issue body is empty; verifier would rely mostly on title text. |
| `scanpy-py314-prerelease-ci-001` | Body is too short and points to external logs; capture those logs first before using it. |

## What Is Still Untested

This selection does not yet prove that current agents actually fail these tasks.
The next step is to create task specs, replay observations, and a cheap baseline
run. If the baseline agent passes too many selected tasks, replace the easiest
tasks with reserve items before producing SFT rows.

Minimum baseline gate:

- run a fresh cheap model on the 10 frozen task specs
- require schema-valid output
- record verifier result and failure reason
- keep only tasks where the agent fails through missing evidence, wrong
  diagnosis, unsupported next action, or forbidden claim
