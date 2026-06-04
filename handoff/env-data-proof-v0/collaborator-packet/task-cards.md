# Task Cards

## Task 1: FASTQ QC Failure Triage

Task id: `fastq-qc-nanopore-fail-001`

Family: `scientific-data-qc`

Agent job:

```text
Inspect a frozen FastQC fixture, determine whether the sample passes QC, cite
the evidence ids for failed checks, and choose the next action.
```

Available tools:

- `workspace.list_files`
- `provenance.inspect`
- `artifact.read_text`
- `fastqc.parse_report`
- `qc_policy.evaluate`

Passing behavior:

- detects a QC failure;
- cites `metric:fastqc.parsed_report`;
- cites `metric:fastq.policy_result`;
- chooses `trim_or_filter_reads`;
- avoids live services and uncited evidence.

Why this matters:

This is a text-first scientific data task. It tests whether the agent can use
domain tools and evidence ids rather than guessing from prose.

## Task 2: Molecule Primer Validation

Task id: `molecule-primer-validation-001`

Family: `molecule-biology`

Agent job:

```text
Import a circular GenBank fixture, inspect sequence context, add the
verifier-specified primer through the domain tool, validate the workspace, and
report the final revision plus evidence refs.
```

Available tools:

- `open_sequence`
- `get_sequence_context`
- `upsert_primer`
- `validate_workspace`

Passing behavior:

- opens the sequence through the tool;
- reads current sequence context;
- calls `upsert_primer` instead of patching state directly;
- validates the workspace;
- cites molecule, primer, and tool-result evidence ids.

Why this matters:

This checks whether the world can represent a stateful scientific workflow:
tool calls mutate workspace state, the verifier checks the final state, and
the trajectory records how the state was reached.

